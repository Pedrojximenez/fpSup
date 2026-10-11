"""Read S16 / OG3.5K / OG4K out of Jose Hurtado's fpSup-Formats v0.6.1 packages
(projects/jose-hurtado/formats-v0.6.1/original), as res-custom row data.

    python3 -I -B jose_extract.py            # prints the rows as JSON

Data only: the packages are untrusted binaries, read as bytes (vbin.parse),
never run.  Nothing is invented here -- every number is a word of his:

  picker entries   C072FB00 + 0x180 * (slot - 1), 8 x 48 B: key, donor
                   timing record, +0x24/+0x28 the timing words, +0x2C nominal fps
  registry row     C0731240 + 0x40 * slot: +04 profile, +08 aspect, +10 the 48
                   PARAM values, +14/+18 record/playback canvas lists, +1C/+20
                   the DNG size, +30/+34 the readout window (timing +0x0C/+0x10)
  48 PARAM cells   C0730C10: p13 and p171 fields, then the six preview heights
  S16 mode tables  his value patches on mode 121's rows (META/R28/R38/R68/REG)

res-custom keeps stock profiles and stock modes untouched, so what he wrote
into p13/p171 becomes canvas pairs of our virtual profile (the PARAM column
offset IS the canvas offset), and what he wrote into mode 121's rows becomes
overrides of our virtual mode.  jose_formats.py holds the result as literals;
test_v3_rescustom checks them against this when the packages are present.
"""
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TOOLS = ROOT / 'projects' / 'jose-hurtado' / 'formats' / 'tools'
IMAGE = ROOT / 'out' / 'MAIN_c0000000.bin'
PROFILES = (ROOT / 'research/other/external/FP3K-technical-handoff-2026-09-10'
            / 'analysis/firmware/raw-profiles.json')
SLOTS = {'s16': 1, 'og35k': 4, 'og4k': 5}
CROP_SLOTS = {'og35k': 8, 'og4k': 7}      # registry +0x38: the Crop Mode variant's row
SUFFIX = {24: None}
RATES = ('23_98', '24', '25', '30', '48', '50', '60', '100')
TT = 0xC0B59500
TABLES = [('TIM', 0xC0B59500, 0x20), ('META', 0xC0B59DC0, 100), ('R28', 0xC0B5BB48, 0x28),
          ('R38', 0xC0B5C638, 0x38), ('R14', 0xC0B5D588, 0x14), ('R68', 0xC0B5DB00, 0x68),
          ('REG', 0xC0B5FDAC, 0x288)]           # ogc_layout.TABLES order: override kind = index


def available():
    return (TOOLS / 'vbin.py').exists() and IMAGE.exists()


class Mem:
    def __init__(self):
        sys.path.insert(0, str(TOOLS))
        import vbin
        self.img = IMAGE.read_bytes()
        self.mem, self.secs = {}, {}
        for n in SLOTS:
            _, secs, _ = vbin.load(n)
            self.secs[n] = secs
            for d, b in secs:
                for i, x in enumerate(b):
                    self.mem[d + i] = x

    def b(self, a):
        return self.mem.get(a, self.img[a - 0xC0000000])

    def w(self, a):
        return self.b(a) | self.b(a + 1) << 8 | self.b(a + 2) << 16 | self.b(a + 3) << 24

    def sw(self, a):
        return struct.unpack_from('<I', self.img, a - 0xC0000000)[0]

    def text(self, a, n):
        return bytes(self.b(a + i) for i in range(n)).split(b'\0')[0].decode()

    def pairs(self, a, stop_at_rate=True):
        """{off, val} until -1; -2 (+ one word) = 'the rest only at 100p': cut there."""
        out = []
        while self.w(a) != 0xFFFFFFFF:
            if self.w(a) == 0xFFFFFFFE:
                if stop_at_rate:
                    break
                a += 8
                continue
            out.append((self.w(a), self.w(a + 4)))
            a += 8
        return out


def param_cells():
    d = json.loads(PROFILES.read_text())
    col = {c['offset']: (int(c['table'], 16) if isinstance(c['table'], str) else c['table'])
           for c in d['columns']}
    row = {p: r['index'] for r in d['rows'] for p in r['profile_ids']}
    return col, row


def extract(name):
    m = Mem()
    slot = SLOTS[name]
    reg = 0xC0731240 + 0x40 * slot
    profile, aspect = m.w(reg + 4), m.w(reg + 8)
    col, row = param_cells()
    # his PARAM values for the base profile -> canvas pairs where they differ from stock
    cells = [m.w(0xC0730C10 + 4 * i) for i in range(48)]
    vals = [m.w(m.w(reg + 0x10) + 4 * i) for i in range(48)]
    canvas = {}
    prev = set()
    for a, v in zip(cells, vals):
        hit = [(off, p) for off, base in col.items() for p, r in row.items()
               if base + 4 * r == a]
        offs = {off for off, p in hit if p == profile}
        if offs and v != m.sw(a):
            canvas[offs.pop()] = v
        elif any(p in (5, 210, 227, 257, 258, 259) and off == 0x28 for off, p in hit):
            prev.add(v)
    for off, v in m.pairs(m.w(reg + 0x14)):
        canvas[off] = v
    if len(prev) != 1:
        raise SystemExit(f'{name}: preview heights differ {prev}')
    prev_h = prev.pop()
    entries = []
    base = 0xC072FB00 + 0x180 * (slot - 1)
    label = m.text(m.w(reg + 0x0C), 8)
    for i in range(8):
        e = base + 48 * i
        key = m.text(e + 0x14, 12)
        donor = m.sw(m.w(e + 0x10))
        if m.w(e + 8) != donor or m.w(e + 4) != profile or not key.startswith(label):
            raise SystemExit(f'{name}: entry {i} is not what this reader expects')
        entries.append({'key': key, 'donor': donor, 'w0': m.w(e + 0x24), 'w1': m.w(e + 0x28),
                        'nominal': m.w(e + 0x2C)})
    donor = entries[0]['donor']
    di = [m.sw(TT + 0x20 * i) for i in range(70)].index(donor)
    overrides = [(donor, 0, 0x0C, m.w(reg + 0x30)), (donor, 0, 0x10, m.w(reg + 0x34))]
    for kind, (tname, tbase, stride) in enumerate(TABLES):
        if tname == 'TIM':
            continue
        r = tbase + stride * di
        if m.sw(r) != donor:
            raise SystemExit(f'{name}: {tname} row order')
        for off in range(4, stride, 4):
            if m.w(r + off) != m.sw(r + off):
                overrides.append((donor, kind, off, m.w(r + off)))
    hirate = [] if name != 's16' else _after_stop(m, m.w(reg + 0x14))
    crop = None
    if m.w(reg + 0x38):
        creg = 0xC0731240 + 0x40 * m.w(reg + 0x38)
        if creg != 0xC0731240 + 0x40 * CROP_SLOTS[name]:
            raise SystemExit(f'{name}: crop row')
        cvals = [m.w(m.w(creg + 0x10) + 4 * i) for i in range(48)]
        pairs = []
        for a, v, cv in zip(cells, vals, cvals):
            hit = [(off, p) for off, base in col.items() for p, r in row.items() if base + 4 * r == a]
            offs = {off for off, p in hit if p == profile}
            if offs and cv != v:
                pairs.append((offs.pop(), cv))
        if m.pairs(m.w(creg + 0x14)) != m.pairs(m.w(reg + 0x14)) or \
                m.pairs(m.w(creg + 0x18)) != m.pairs(m.w(reg + 0x18)) or \
                (m.w(creg + 0x30), m.w(creg + 0x34)) != (m.w(reg + 0x30), m.w(reg + 0x34)):
            raise SystemExit(f'{name}: the crop row differs in more than PARAM and standby')
        crop = {'canvas': sorted(pairs), 'standby': m.pairs(m.w(creg + 0x2C))}
    sby = m.pairs(m.w(reg + 0x2C)) if m.w(reg + 0x2C) else []
    return {'label': label, 'profile': profile, 'aspect': aspect,
            'act': [m.w(reg + 0x1C), m.w(reg + 0x20)],
            'canvas_rec': sorted(canvas.items()), 'canvas_pb': m.pairs(m.w(reg + 0x18)),
            'standby': sby, 'crop': crop,
            # his magnifier hook: MAG8 at 4x while the standby list is narrower than 1024
            'mag8': bool(sby) and sby[0][1] < 1024,
            'prev_h': prev_h, 'entries': entries, 'overrides': overrides,
            'max_rate_enum': m.w(reg + 0x28), 'crop_row': m.w(reg + 0x38),
            'hirate_100p': hirate}


def _after_stop(m, a):
    while m.w(a) != 0xFFFFFFFE:
        a += 8
    return m.pairs(a + 8)


if __name__ == '__main__':
    json.dump({n: extract(n) for n in SLOTS}, sys.stdout, indent=1)
