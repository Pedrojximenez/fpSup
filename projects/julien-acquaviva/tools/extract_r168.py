#!/usr/bin/env python3
"""Replay the pinned R168 planner offline; translate its results to RCD3 rows.

Only the upstream planner and canvas builder execute. Stock firmware execution
is forbidden; the settings-object accessor is the sole declared stub. No USB,
camera, loader, upstream installation or native code execution is involved.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
ROOT = PROJECT.parents[1]
RC = ROOT / 'projects/open-gate/build/res-custom'
sys.path.insert(0, str(RC))
import ogc_layout as L

COMMIT = '3d60d0f7d3ecbc09843d87a80e35e6adf735abe2'
BIN = PROJECT / 'upstream/release/R168/FPOG.BIN'
PUBLIC = PROJECT / 'upstream/tools/modes_v45.json'
IMAGE = ROOT / 'out/MAIN_c0000000.bin'
PIN = 'f4cddac261c47021ce666449cdab3deb6c12f1467b019113b6d70909b854fd98'
PUBLIC_PIN = '55490af681ffb6b530e4085be62255c251b1fafeb2c328255ba626fa71cbb98b'
MEDIA = ('SSD', 'v90', 'v60', 'v30')
MEDIA_CODE = ('F', 'R', 'M', 'S')
RATIO = ('3:2', '16:9', '2:1')
SELECTOR = ((4000, 2666), (4000, 2250), (4320, 2160))
TABLES = ((0xC0B59500, 32), (0xC0B59DC0, 100), (0xC0B5BB48, 40),
          (0xC0B5C638, 56), (0xC0B5D588, 20), (0xC0B5DB00, 104), (0xC0B5FDAC, 648))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sections(data):
    """FRM1 stores destination/length/old/new/kind/reserved, not a VBIN."""
    if len(data) < 48:
        raise ValueError('short FRM1')
    magic, ver, size, _, _, count, table, _, _, _, z0, z1 = struct.unpack_from('<12I', data)
    if magic != 0x314D5246 or ver != 1 or size != len(data) or z0 or z1 or \
            not 0 < count < 4096 or table < 48 or table + count * 24 > size:
        raise ValueError('invalid FRM1 header')
    out = []
    for i in range(count):
        dest, length, old, new, kind, reserved = struct.unpack_from('<6I', data, table + i * 24)
        if not length or not 0xC0000000 <= dest < dest + length <= 0xC4000000 or \
                old < table + count * 24 or new < table + count * 24 or \
                max(old, new) + length > size or kind not in (1, 2, 3) or reserved:
            raise ValueError(f'invalid section {i}')
        out.append((dest, data[new:new + length]))
    spans = sorted((a, a + len(b)) for a, b in out)
    if any(end > nxt for (_, end), (nxt, _) in zip(spans, spans[1:])):
        raise ValueError('overlapping destinations')
    return out


class Planner:
    # Named, audited upstream code paths. These never permit stock firmware or
    # scratch execution; kind 3 in FRM1 is not an instruction-set selector.
    CODE = ((0xC07942D4, 0xC0794CC8), (0xC0795340, 0xC07956F0),
            (0xC0733274, 0xC07332A4), (0xC073460C, 0xC073465C),
            (0xC0734838, 0xC0734A24))

    def __init__(self):
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
        from unicorn import arm_const as A
        self.A = A
        data = BIN.read_bytes()
        if sha(data) != PIN or sha(PUBLIC.read_bytes()) != PUBLIC_PIN:
            raise ValueError('upstream differs from the pinned R168 inputs')
        self.image = IMAGE.read_bytes()
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.mem_map(0xC0000000, 0x4000000)
        self.u.mem_write(0xC0000000, self.image)
        self.sections = sections(data)
        for address, body in self.sections:
            self.u.mem_write(address, body)
        self.done, self.sp, self.state, self.buf = 0xC3FF0000, 0xC3FE0000, 0xC3E01000, 0xC3E02000
        self.visited, self.stub_calls = set(), 0
        self.u.hook_add(UC_HOOK_CODE, self._hook)
        self.put(0xC3075234, 1)                 # a valid acquisition configuration
        self.put(0xC3075230, 0xC3074BE8)
        self.ids = [struct.unpack_from('<I', self.image, 0xB59500 + i * 32)[0] for i in range(70)]

    def _hook(self, u, address, size, data):
        A = self.A
        if address == self.done:
            u.emu_stop()
            return
        if address == 0xC0732FCE:
            # Returns the explicitly initialized media settings object; no
            # arithmetic, geometry, stock function or planner result is stubbed.
            self.stub_calls += 1
            u.reg_write(A.UC_ARM_REG_R0, self.state)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
            return
        if not any(lo <= address < hi for lo, hi in self.CODE):
            raise RuntimeError(f'unapproved execution at {address:08X}')
        self.visited.add(address)

    def read(self, address, size):
        return bytes(self.u.mem_read(address, size))

    def words(self, address, count):
        return struct.unpack(f'<{count}I', self.read(address, count * 4))

    def put(self, address, *values):
        self.u.mem_write(address, struct.pack(f'<{len(values)}I', *values))

    def call(self, address, *args):
        A = self.A
        self.u.reg_write(A.UC_ARM_REG_CPSR, 0x10)
        self.u.reg_write(A.UC_ARM_REG_SP, self.sp)
        self.u.reg_write(A.UC_ARM_REG_LR, self.done)
        for i, value in enumerate(args):
            self.u.reg_write(A.UC_ARM_REG_R0 + i, value)
        self.u.emu_start(address, self.done, count=100000)
        if self.u.reg_read(A.UC_ARM_REG_PC) != self.done or self.u.reg_read(A.UC_ARM_REG_SP) != self.sp:
            raise RuntimeError('planner did not return with its stack restored')
        return self.u.reg_read(A.UC_ARM_REG_R0)

    def mode(self, fps_index):
        profile, donor, ti, orig_i = self.words(0xC0793A40 + fps_index * 16, 4)
        if donor != self.ids[orig_i] or profile != (449 + fps_index if fps_index < 7 else 470 + fps_index):
            raise ValueError('unexpected upstream mode reference')
        timing = self.words(0xC0793060 + ti * 32, 8)
        overrides = []
        for kind, (base, stride) in enumerate(TABLES):
            address = base + orig_i * stride
            if self.words(address, 1)[0] != donor:
                raise ValueError('upstream mode table order changed')
            for off in range(4, stride, 4):
                # Use the appended frame's geometry, and let res-custom solve
                # timing. Other tables come from the upstream overlay exactly.
                if kind == 0 and off in (4, 8):
                    continue
                value = timing[off // 4] if kind == 0 else self.words(address + off, 1)[0]
                stock = struct.unpack_from('<I', self.image, address + off - 0xC0000000)[0]
                if value != stock:
                    overrides.append((donor, kind, off, value))
        # Descriptor +0x10 has the mode in the second word. It selects an
        # additional readout attribute and must be cloned too.
        r10 = self.words(0xC0B5B918 + orig_i * 8, 2)
        stock10 = struct.unpack_from('<2I', self.image, 0xB5B918 + orig_i * 8)
        if r10[1] != donor or stock10[1] != donor:
            raise ValueError('R10 mode order changed')
        if r10[0] != stock10[0]:
            overrides.append((donor, 7, 0, r10[0]))
        return dict(profile=profile, donor=donor, timing=list(timing), overrides=overrides)

    def extract(self):
        public = json.loads(PUBLIC.read_text())
        states, modes = [], [self.mode(i) for i in range(9)]
        for mi, media in enumerate(MEDIA):
            table = public[media]
            self.put(self.state + 8, 0xA0000000 | mi << 5)
            for ri, ratio in enumerate(table['ratios']):
                if ratio['ratio'] != RATIO[ri] or len(ratio['crops']) != 19:
                    raise ValueError('unexpected ratio/crop table')
                for ci, crop in enumerate(ratio['crops']):
                    idx = ri * 19 + ci
                    x, y = SELECTOR[ri]
                    self.put(0xC3074BE8, x, y + 2 * ci)
                    for s in crop['states']:
                        fi = table['fps'].index(s['fps'])
                        self.u.mem_write(self.buf, bytes(0x200))
                        if self.call(0xC0794A11, self.buf, idx, fi) != 1:
                            raise ValueError(f'planner refused {media}/{idx}/{fi}')
                        plan = self.words(self.buf, 12)
                        self.call(0xC079453F, idx, fi, self.buf + 0x300, self.buf + 0x304)
                        window = list(self.words(self.buf + 0x300, 1) + self.words(self.buf + 0x304, 1))
                        self.put(self.buf, modes[fi]['profile'])
                        if self.call(0xC0734838, self.buf) != 8:
                            raise ValueError('record canvas not generated')
                        canvas = list(self.words(self.buf + 0x5C, 67))
                        if list(plan[:2]) != s['out'] or max(1024, canvas[0x64 // 4]) != s['k']:
                            raise ValueError('binary/public output or RWZM disagreement')
                        if window != s.get('window', crop['window']):
                            raise ValueError(f'binary/public nominal window disagreement {window}')
                        if canvas[0x108 // 4] != 4042 or plan[6] != modes[fi]['donor']:
                            raise ValueError('unexpected full sensor window or donor')
                        rate_group = self.read(0xC0794254 + fi, 1)[0]
                        width_limit = self.call(0xC079569F, ri, rate_group, idx)
                        states.append(dict(media=media, media_index=mi, ratio=RATIO[ri], ratio_index=ri,
                                           crop=crop['crop'], crop_index=idx, fps=s['fps'], fps_index=fi,
                                           output=s['out'], nominal_window=window,
                                           quantized_window=list(plan[2:4]), rwzm_raw=canvas[25],
                                           one=s['one'], mbps=s['mbps'], readout_us=plan[4],
                                           output_width_limit=width_limit,
                                           donor=modes[fi]['donor'], native_timing=modes[fi]['timing'],
                                           canvas=canvas))
        return states, modes


def rows(states, modes):
    """One fixed RCD format per native geometry, media target and crop.

    RCD3's mode ceiling intentionally makes lower rates selectable too. Source
    matched rates and these extra fixed-geometry rates are recorded separately.
    """
    grouped = {}
    for state in states:
        canvas = tuple(v for i, v in enumerate(state['canvas']) if i != 0x30 // 4)
        key = state['media_index'], state['crop_index'], canvas
        grouped.setdefault(key, []).append(state)
    letters, result = {}, []
    for (mi, ci, _), group in grouped.items():
        first = group[0]
        ri = first['ratio_index']
        group_no = letters.get((mi, ci), 0)
        letters[mi, ci] = group_no + 1
        label = f'J{MEDIA_CODE[mi]}{"ABC"[ri]}{ci % 19 + 10:02d}{chr(65 + group_no)}'
        aspect = (2, 3, 9)[ri]
        fi = max(s['fps_index'] for s in group)
        mode = modes[fi]
        if len({s['donor'] for s in group}) != 1:
            raise ValueError('same canvas with different donor: needs explicit mode grouping')
        cv = first['canvas']
        w, h = first['output']
        rec = [(i * 4, v) for i, v in enumerate(cv[:66]) if i * 4 not in (0x30, 0x80, 0x84)]
        pb = {0x1C: aspect, 0x0C: cv[0], 0x10: cv[1], 0xD8: cv[0], 0xE0: cv[1],
              0x20: w, 0x28: h, 0xF4: cv[0], 0xF8: cv[1],
              0x60: 1024, 0xD0: 1024, 0x64: 1024, 0xD4: 1024}
        row = dict(label=label, stock_value=3, aspect=aspect, flags=0, enum=4, profile=83,
                   act=[w, h], prev_h=cv[0x28 // 4] if aspect == 2 else 0,
                   canvas_rec=rec, canvas_pb=sorted(pb.items()),
                   row_text=f'{MEDIA_CODE[mi]} {RATIO[ri]} {first["crop"]:.1f}x {w}x{h}',
                   summary=f'{w}x{h}', tile_text=str(w),
                   modes=[(mode['donor'], L.RATES[fi][7], mode['timing'][1] & 65535, 0,
                           mode['timing'][2] >> 16)], overrides=mode['overrides'])
        entries = L.gen_entries(label, row['modes'], 0)
        matched = {L.RATES[s['fps_index']][7] for s in group}
        result.append(dict(row=row, media=MEDIA[mi], ratio=RATIO[ri], crop=first['crop'],
                           source_fps=[s['fps'] for s in group],
                           extra_rate_ranks=[e['rank'] for e in entries if e['rank'] not in matched],
                           states=[states.index(s) for s in group]))
    return result


def main():
    out = PROJECT / 'extracted'
    out.mkdir(exist_ok=True)
    planner = Planner()
    states, modes = planner.extract()
    formats = rows(states, modes)
    doc = dict(commit=COMMIT, release='R168', binary_sha256=PIN, public_sha256=PUBLIC_PIN,
               image_sha256=sha(planner.image), states=states, modes=modes, formats=formats,
               execution=dict(stub='C0732FCE: settings object', stub_calls=planner.stub_calls,
                              stock_firmware_executed=False,
                              instruction_addresses=len(planner.visited)))
    (out / 'r168.json').write_text(json.dumps(doc, indent=2) + '\n')
    # The host calculator needs only these small rule tables, no firmware,
    # Unicorn, copied hooks, or precomputed output dimensions.
    model = dict(commit=COMMIT, release='R168', binary_sha256=PIN,
                 media=list(MEDIA), ratios=list(RATIO),
                 fps=[23.976, 24, 25, 29.97, 48, 50, 59.94, 100, 119.88],
                 settings=[[s['media_index'], s['ratio_index'], s['crop_index'] % 19, s['fps_index'],
                            *s['nominal_window'], s['output_width_limit']] for s in states])
    (out / 'planner-data.json').write_text(json.dumps(model, separators=(',', ':')) + '\n')
    print(f'{len(states)} states, {len(formats)} fixed RCD formats; all outputs/windows/RWZM matched')


if __name__ == '__main__':
    main()
