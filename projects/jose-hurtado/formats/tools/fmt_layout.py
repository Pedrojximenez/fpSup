"""Jose Hurtado's fpSup-Formats v0.6.0 as one relocatable layout.

Reads the three original fpSup.BIN (VBIN) files, keeps their shared core once
plus each chosen format's slot, and works out -- from the bytes alone, there is
no source -- everything a move of the layout from its fixed addresses into a
Loader v3 block has to change:

  pieces   the layout coordinates that hold anything, three runs:
           cave 0xC072FB00.., private pack 0xC0793060.., icon packs 0xC07A4BF0..
  code     found by recursive descent from every firmware hook, the compositor
           entry, the refresh task and every register call into the layout
  fixups   MOVW/MOVT pairs and 32-bit words that name a layout coordinate:
           made absolute at load time (block address - coordinate origin)
  branches B/BL inside the code whose target is in another piece (rewritten
           here, the pieces keep their places in the block) or in the firmware
           (rewritten here to a veneer in the block: the block is ~48 MB away)
  firmware every section outside the layout: hooks (branches into the layout),
           value patches, stock words (the old cards' cleaners), and the firmware
           words that hold a layout address (C06BDA3C/40 MOVW/MOVT, C07426F8)

Everything here is checked by assertion; a surprise stops the build.
"""
import collections
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vbin                                                    # noqa: E402
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB  # noqa: E402
from capstone.arm import (ARM_INS_B, ARM_INS_BL, ARM_INS_BLX, ARM_INS_BX,   # noqa: E402
                          ARM_INS_POP, ARM_INS_LDM, ARM_INS_LDR, ARM_INS_MOV,
                          ARM_INS_ORR, ARM_INS_CBZ, ARM_INS_CBNZ, ARM_OP_IMM,
                          ARM_OP_MEM, ARM_OP_REG, ARM_REG_PC, ARM_CC_AL,
                          ARM_CC_INVALID)

ROOT = HERE.parents[3]
IMAGE = ROOT / 'out' / 'MAIN_c0000000.bin'

PIECES = [(0xC072FB00, 0xC0735000), (0xC0793060, 0xC0794EA0), (0xC07A4BF0, 0xC07A67F4)]
ENTRY = 0xC0793C30                 # the menu compositor (the VBIN entry)
TASK = 0xC0794034                  # the boot-refresh task (adr in the compositor)
FW_LAYOUT_WORDS = {                # firmware words that hold a layout address
    0xC07426F8: 'abs',             # a function pointer: the crop no-cache stub
}
FW_MOVW_MOVT = [(0xC06BDA3C, 0xC06BDA40)]   # movw/movt r2 = the enum pair table
FORMATS = ('s16', 'og35k', 'og4k')
SLOTS = {'s16': 1, 'og35k': 4, 'og4k': 5}

ARM = Cs(CS_ARCH_ARM, CS_MODE_ARM); ARM.detail = True
THUMB = Cs(CS_ARCH_ARM, CS_MODE_THUMB); THUMB.detail = True


class LayoutError(RuntimeError):
    pass


def piece_of(v):
    for i, (a, b) in enumerate(PIECES):
        if a <= v < b:
            return i
    return None


def u32(v):
    return v & 0xFFFFFFFF


def load(formats=FORMATS):
    """{address: bytes} of the chosen packages, the core once, and the stage2
    bytes (identical in all three)."""
    secs, owner, stage2 = {}, collections.defaultdict(set), set()
    for n in FORMATS:
        entry, s, _ = vbin.load(n)
        if entry != ENTRY:
            raise LayoutError(f'{n}: entry {entry:#x}')
        stage2.add(s[0][1])
        for a, b in s[1:]:
            owner[a].add(n)
            if a in secs and secs[a] != b:
                raise LayoutError(f'{a:#x}: the packages disagree')
            secs[a] = b
    if len(stage2) != 1:
        raise LayoutError('the stage2 copies differ')
    core = {a for a, o in owner.items() if o == set(FORMATS)}
    chosen = {a: b for a, b in secs.items()
              if a in core or owner[a] & set(formats)}
    kinds = {a: ('core' if a in core else '+'.join(sorted(owner[a]))) for a in chosen}
    return chosen, kinds


class Image:
    """The layout sections as one sparse memory."""
    def __init__(self, secs):
        self.secs = sorted((a, b) for a, b in secs.items() if piece_of(a) is not None)
        for a, b in self.secs:
            if piece_of(a + len(b) - 1) != piece_of(a):
                raise LayoutError(f'section {a:#x} crosses a piece boundary')

    def read(self, a, n):
        for s, b in self.secs:
            if s <= a and a + n <= s + len(b):
                return b[a - s:a - s + n]
        return None

    def word(self, a):
        r = self.read(a, 4)
        return struct.unpack('<I', r)[0] if r else None


def _hook_targets(secs):
    out = []
    for a, b in secs.items():
        if piece_of(a) is not None:
            continue
        for i in range(0, len(b) - 3, 4):
            w, = struct.unpack_from('<I', b, i)
            t = arm_branch(a + i, w)
            if t and piece_of(t[1]) is not None:
                out.append((t[1], False))
            t = thumb_bw(a + i, w)
            if t and piece_of(t[1]) is not None:
                out.append((t[1], True))
    return out


def arm_branch(site, w):
    if (w >> 25) & 7 != 5 or w >> 28 == 0xF:
        return None
    off = w & 0xFFFFFF
    if off & 0x800000:
        off -= 1 << 24
    return ('BL' if w >> 24 & 1 else 'B', u32(site + 8 + 4 * off), w >> 28)


def thumb_bw(site, w):
    h1, h2 = w & 0xFFFF, w >> 16
    if h1 >> 11 != 0x1E or (h2 & 0xD000) != 0x9000:
        return None
    s, j1, j2 = h1 >> 10 & 1, h2 >> 13 & 1, h2 >> 11 & 1
    i1, i2 = 1 - (j1 ^ s), 1 - (j2 ^ s)
    off = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    if s:
        off -= 1 << 25
    return ('B.W', u32(site + 4 + off), None)


def _walk(img, roots):
    seen, lits, todo = {}, set(), list(roots)
    while todo:
        a, th = todo.pop()
        while a not in seen and piece_of(a) is not None:
            raw = img.read(a, 4) or img.read(a, 2)
            if raw is None:
                raise LayoutError(f'code runs into a hole at {a:#x}')
            ins = next((THUMB if th else ARM).disasm(raw, a, 1), None)
            if ins is None:
                raise LayoutError(f'undecodable code at {a:#x}')
            seen[a] = (ins, th)
            iid, ops = ins.id, ins.operands
            uncond = ins.cc in (ARM_CC_AL, ARM_CC_INVALID)
            for o in ops:
                if o.type == ARM_OP_MEM and o.mem.base == ARM_REG_PC:
                    lits.add(((a + (4 if th else 8)) & ~3) + o.mem.disp)
            if iid in (ARM_INS_B, ARM_INS_BL, ARM_INS_BLX) and ops and ops[0].type == ARM_OP_IMM:
                t = u32(ops[0].imm)
                if piece_of(t) is not None:
                    todo.append((t, th if iid != ARM_INS_BLX else not th))
                if iid == ARM_INS_B and uncond:
                    break
            if iid in (ARM_INS_CBZ, ARM_INS_CBNZ):
                todo.append((u32(ops[1].imm), th))
            if iid == ARM_INS_BX and uncond:
                if ops[0].reg == ARM_REG_PC:
                    todo.append(((a + 4) & ~3, False))
                break
            if uncond and iid in (ARM_INS_POP, ARM_INS_LDM) and \
                    any(o.type == ARM_OP_REG and o.reg == ARM_REG_PC for o in ops):
                break
            if uncond and iid in (ARM_INS_LDR, ARM_INS_MOV) and ops[0].reg == ARM_REG_PC:
                break
            a += ins.size
    return seen, lits


def _pairs(seen):
    """MOVW/MOVT pairs: [(movw addr, movt addr, value)]."""
    out = []
    order = sorted(seen)
    for i, a in enumerate(order):
        ins, th = seen[a]
        if not ins.mnemonic.startswith('movt'):
            continue
        reg = ins.operands[0].reg
        for j in range(i - 1, max(-1, i - 12), -1):
            p, _ = seen[order[j]]
            if p.mnemonic.startswith('movw') and p.operands[0].reg == reg:
                v = ((ins.operands[1].imm & 0xFFFF) << 16) | (p.operands[1].imm & 0xFFFF)
                out.append((order[j], a, v, th))
                break
            if reg in _writes(p):
                raise LayoutError(f'movt at {a:#x}: its movw is not the last write')
        else:
            raise LayoutError(f'movt at {a:#x} without a movw')
    return out


def _writes(ins):
    try:
        return ins.regs_access()[1]
    except Exception:
        return ()


def _reg_calls(img, seen):
    out = set()
    order = sorted(seen)
    pairs = {t: v for _, t, v, _ in _pairs(seen)}
    for i, a in enumerate(order):
        ins, th = seen[a]
        val = reg = None
        if a in pairs:
            val, reg = pairs[a], ins.operands[0].reg
        elif ins.id == ARM_INS_LDR and ins.operands[1].type == ARM_OP_MEM and \
                ins.operands[1].mem.base == ARM_REG_PC:
            reg = ins.operands[0].reg
            val = img.word(((a + (4 if th else 8)) & ~3) + ins.operands[1].mem.disp)
        if val is None or piece_of(val & ~1) is None:
            continue
        thumb = bool(val & 1)
        for j in range(i + 1, min(len(order), i + 8)):
            n, _ = seen[order[j]]
            if n.id == ARM_INS_ORR and n.operands[0].reg == reg and \
                    n.operands[-1].type == ARM_OP_IMM and n.operands[-1].imm == 1:
                thumb = True
                continue
            if n.id in (ARM_INS_BLX, ARM_INS_BX) and n.operands[0].type == ARM_OP_REG \
                    and n.operands[0].reg == reg:
                out.add((val & ~1, thumb))
                break
            if reg in _writes(n):
                break
    return out


class Layout:
    def __init__(self, formats=FORMATS):
        self.formats = tuple(formats)
        self.secs, self.kinds = load(self.formats)
        self.img = Image(self.secs)
        roots = set(_hook_targets(self.secs)) | {(ENTRY, False), (TASK, False)}
        roots |= {(v & ~1, False) for a, k in FW_LAYOUT_WORDS.items()
                  for v in [struct.unpack('<I', self.secs[a])[0]]}
        while True:
            self.code, self.lits = _walk(self.img, sorted(roots))
            new = _reg_calls(self.img, self.code) - roots
            if not new:
                break
            roots |= new
        self.roots = roots
        self._classify()

    # -- what the move changes ------------------------------------------------
    def _classify(self):
        covered = set()
        for a, (ins, _) in self.code.items():
            covered.update(range(a, a + ins.size))
        self.covered = covered
        self.pairs = [(w, t, v, th) for w, t, v, th in _pairs(self.code)
                      if piece_of(v & ~1) is not None]
        for w, t, v, th in self.pairs:
            if th:
                raise LayoutError(f'Thumb MOVW/MOVT of a layout address at {w:#x}')
        self.abs = []                  # (address, value) data words naming the layout
        for s, b in self.img.secs:
            for i in range(0, len(b) - 3, 4):
                a = s + i
                if a in covered:
                    continue
                v, = struct.unpack_from('<I', b, i)
                if piece_of(v & ~1) is not None:
                    self.abs.append((a, v))
        self.branches = []             # (site, kind, target, cond, thumb)
        for a, (ins, th) in self.code.items():
            if ins.id in (ARM_INS_B, ARM_INS_BL, ARM_INS_BLX) and ins.operands and \
                    ins.operands[0].type == ARM_OP_IMM:
                t = u32(ins.operands[0].imm)
                same = piece_of(t) == piece_of(a)
                if same:
                    continue
                if th:
                    raise LayoutError(f'Thumb branch out of its piece at {a:#x}')
                if ins.id == ARM_INS_BLX:
                    raise LayoutError(f'BLX immediate at {a:#x}')
                w = struct.unpack('<I', bytes(ins.bytes))[0]
                kind = 'xpiece' if piece_of(t) is not None else 'firmware'
                self.branches.append((a, kind, t, w))

    def firmware_sections(self):
        """[(address, bytes, role)] of everything outside the layout."""
        img = IMAGE.read_bytes()
        out = []
        for a in sorted(self.secs):
            if piece_of(a) is not None:
                continue
            b = self.secs[a]
            stock = img[a - 0xC0000000:a - 0xC0000000 + len(b)]
            if len(b) == 4:
                w, = struct.unpack('<I', b)
                br, tb = arm_branch(a, w), thumb_bw(a, w)
                if br and piece_of(br[1]) is not None:
                    out.append((a, b, ('hook', br[0], br[1])))
                    continue
                if tb and piece_of(tb[1]) is not None:
                    out.append((a, b, ('hook', 'B.W', tb[1])))
                    continue
            if b == stock:
                out.append((a, b, ('stock',)))
            elif a in FW_LAYOUT_WORDS:
                out.append((a, b, ('fw_abs', struct.unpack('<I', b)[0])))
            elif any(m <= a < t + 4 for m, t in FW_MOVW_MOVT):
                out.append((a, b, ('fw_movw_movt',)))
            else:
                out.append((a, b, ('value',)))
        return out

    def summary(self):
        c = collections.Counter(k for _, k, _, _ in self.branches)
        return {'sections': len(self.secs), 'layout_sections': len(self.img.secs),
                'code_insns': len(self.code), 'roots': len(self.roots),
                'movw_movt': len(self.pairs), 'abs_words': len(self.abs),
                'branch_xpiece': c['xpiece'], 'branch_firmware': c['firmware']}


if __name__ == '__main__':
    L = Layout(sys.argv[1:] or FORMATS)
    print(L.summary())
    for a, b, r in L.firmware_sections():
        print(f'{a:08x} {len(b):4d} {r}')
    for a, v in L.abs:
        print(f'abs {a:08x} -> {v:08x}')
