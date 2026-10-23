"""Unicorn: the real redraw round C0528700 with dirtyclean patched in.

What runs for real (firmware image): C0528700 itself, the layer methods
(getBuffer C0721328, commit C0721370 + ring C0721CD8, fill C0721480 ->
C0722490, pixelsToBytes C0721638, C0721110), the clear C0528B40, the
whole-layer memcpy C0528BA0 -> C001510C, UIC's +0x1C C05757F8, and our code.
Stubbed: locks, event flag (gives the per-slot dirty bits), trace log,
C0528E18/C0528178/C0528650/C0528C28/C05286D0, the full flush C000E91C
(modelled: every dirty line becomes clean), and the drawers' draw: the UIC
stub writes every byte of its rect into the back buffer and records the rect
in uicMgr's per-buffer record, as C0561198 does; the "other" drawer writes a
region it reports to nobody.

The check: at every commit (C0721370) no cache line of the buffer being
committed is still dirty.  Dirty = written by an emulated store or by a
drawer stub, and not cleaned since by DCCMVAC in our code or by C000E91C.

    python3 -B test_dirtyclean.py            # scenarios
    python3 -B test_dirtyclean.py --mutate   # every mutant must fail
"""
import pathlib, re, struct, sys, tempfile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import arm_const as A

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
SEG1 = ROOT / 'out' / 'seg1_c2ef6e00.bin'
SRC = HERE / 'dirtyclean.S'

CODE = 0xC5000000
VEN = 0xC072E100              # cave-like spot within BL range of C0528954
CTRL = 0xC3400000
LAYER0 = 0xC3410000
BUF0 = 0xC4000000
UICMGR = 0xC37B7048             # C055F0F0() = 0xC37B7034+0x14
STOP = 0xC5FFF000
OTHER_VT = 0xC3480000
OTHER_DRAW = 0xC5F00000
OTHER_1C = 0xC5F00010
LINE = 64
SITES = {'clean': (0xC0528954, 0xC000E91C), 'clear': (0xC05287F4, 0xC0528B40),
         'copy': (0xC0528AE0, 0xC0528BA0)}
UIC_VT = 0xC0D17780
SP_VT = 0xC2EF6280
W, H = 1024, 682

RET0 = {0xC0010298, 0xC00102D0, 0xC036D7E0, 0xC0019DC0, 0xC001A0D8,
        0xC0528E18, 0xC0528650, 0xC0528C28, 0xC05286D0}


def bl(at, to):
    return 0xEB000000 | (((to - (at + 8)) >> 2) & 0xFFFFFF)


class Rig:
    def __init__(self, src=SRC, patched=True, sp_mod=0, fmt=1):
        code = assemble(src)
        sym = symbols(src)
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A7)
        mu.mem_map(0xC0000000, 0x04000000)
        mu.mem_write(0xC0000000, SEG0.read_bytes())
        mu.mem_write(0xC2EF6E00, SEG1.read_bytes())
        mu.mem_map(BUF0, 0x01000000)
        mu.mem_map(CODE, 0x01000000)
        mu.mem_write(CODE, code)
        self.ctl = CODE + sym['dc_ctl']
        self.patched = patched
        if patched:
            for i, (name, ent) in enumerate((('clean', 'dc_clean'), ('clear', 'dc_clear_hook'),
                                              ('copy', 'dc_copy_hook'))):
                v = VEN + 8 * i
                self.w(v, 0xE51FF004); self.w(v + 4, CODE + sym[ent])
                site, orig = SITES[name]
                assert self.r(site) == bl(site, orig), name
                self.w(site, bl(site, v))
        self.mcr = [CODE + o for o in self._mcr_offsets(code)]
        self.fmt, self.sp_mod = fmt, sp_mod
        self.dirty = set()
        self.flushes = 0
        self.violations = []
        self.commits = 0
        self.slots = {}
        self.round_dirty_bits = 0
        # objects
        for s in range(4):
            L = LAYER0 + s * 0x100
            self.w(CTRL + 0x58 + 8 * s, L)
            self.w(L, SP_VT); self.w(L + 4, W); self.w(L + 8, H); self.w(L + 0x1C, fmt)
            for i in range(3):
                d = L + 0x80 + 0x10 * i
                self.w(d + 4, BUF0 + (s * 3 + i) * 0x100000)
                self.w(d + 8, L + 0xC0)
                self.w(L + 0x3C + 4 * i, d)
            self.w(L + 0xC0, W); self.w(L + 0xC4, H)
            self.w(L + 0x48, L + 0x80); self.w(L + 0x4C, L + 0x90); self.w(L + 0x50, 0)
        self.w(OTHER_VT + 0x0C, OTHER_DRAW); self.w(OTHER_VT + 0x1C, OTHER_1C)
        self.other_copy = False
        mu.hook_add(UC_HOOK_CODE, self._code)
        mu.hook_add(UC_HOOK_MEM_WRITE, self._wr, begin=BUF0, end=BUF0 + 0x01000000 - 1)

    @staticmethod
    def _mcr_offsets(code):
        out = []
        for o in range(0, len(code), 4):
            v = struct.unpack_from('<I', code, o)[0]
            if (v & 0x0FFF0FFF) == 0x0E070F3A:      # mcr p15,0,Rt,c7,c10,1
                out.append(o)
        assert out, 'no DCCMVAC in the code'
        return out

    def w(self, a, v):
        self.mu.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))

    def r(self, a):
        return struct.unpack('<I', self.mu.mem_read(a, 4))[0]

    def cr(self, off):
        return self.r(self.ctl + off)

    def bpp_bytes(self, n):
        return {0: n * 4, 1: n * 2, 2: n >> 1, 3: n}[self.fmt]

    def stride(self):
        return self.bpp_bytes(W)

    def back(self, s):
        L = LAYER0 + s * 0x100
        return self.r(self.r(L + 0x4C) + 4)

    def mark(self, a, n):
        for line in range(a // LINE, (a + n - 1) // LINE + 1):
            self.dirty.add(line)

    def _wr(self, mu, acc, addr, size, val, _):
        self.mark(addr, size)

    def ret(self, val=0):
        self.mu.reg_write(A.UC_ARM_REG_R0, val)
        self.mu.reg_write(A.UC_ARM_REG_PC, self.mu.reg_read(A.UC_ARM_REG_LR))

    def _code(self, mu, addr, size, _):
        reg = mu.reg_read
        if addr in self.mcr:
            self.dirty.discard(reg(A.UC_ARM_REG_R0) // LINE)
        elif addr == 0xC000E91C:
            self.flushes += 1; self.dirty.clear(); self.ret(0)
        elif addr in RET0:
            self.ret(0)
        elif addr == 0xC0528178:
            self.ret(1)
        elif addr == 0xC036D888:                    # event flag: per-slot dirty bits
            self.w(reg(A.UC_ARM_REG_R1) + 8, self.round_dirty_bits); self.ret(1)
        elif addr == 0xC06D1948 or addr == OTHER_DRAW:
            desc = reg(A.UC_ARM_REG_R1)
            base = self.r(desc + 4)
            slot = self.cur_slot(base)
            kind = 'uic' if addr == 0xC06D1948 else 'other'
            act = self.slots.get(slot, {}).get(kind)
            drew = 0
            if act:
                x, y, w, h = act
                if kind == 'uic':
                    self.uic_record(base, act)
                st = self.stride()
                for row in range(max(y, 0), min(y + h, H)):
                    b0 = self.bpp_bytes(max(x, 0)); b1 = self.bpp_bytes(min(x + w, W)) + (1 if self.fmt == 2 else 0)
                    self.mark(base + row * st + b0, max(b1 - b0, 1))
                drew = 1
            self.ret(drew)
        elif addr == OTHER_1C:
            self.ret(1 if self.other_copy else 0)
        elif addr == 0xC0721370:                    # commit: the buffer must be clean
            L = reg(A.UC_ARM_REG_R0)
            base = self.r(self.r(L + 0x4C) + 4)
            lo, hi = base // LINE, (base + self.stride() * H - 1) // LINE
            bad = [l for l in self.dirty if lo <= l <= hi]
            if bad:
                self.violations.append((hex(base), len(bad), hex(min(bad) * LINE)))
            self.commits += 1

    def cur_slot(self, base):
        for s in range(4):
            if self.back(s) == base:
                return s
        raise AssertionError(hex(base))

    def uic_record(self, base, rect):
        recs = UICMGR + 0x18
        for i in range(10):
            if self.r(recs + 0x20 * i + 4) in (0, base):
                self.w(recs + 0x20 * i + 4, base)
                for k, v in enumerate(rect):
                    self.w(recs + 0x20 * i + 8 + 4 * k, v)
                return
        raise AssertionError('records full')

    def set_drawers(self, s, kinds):
        objs = []
        for i, k in enumerate(kinds):
            o = 0xC3460000 + s * 0x100 + i * 0x20
            self.w(o, UIC_VT if k == 'uic' else OTHER_VT)
            objs.append(o)
        for i in range(3):
            self.w(CTRL + 12 * s + 4 * i, objs[i] if i < len(objs) else 0)

    def round(self, dirty_bits, acts=None, clear=None):
        self.round_dirty_bits = dirty_bits
        self.slots = acts or {}
        for s, mode in (clear or {}).items():
            self.w(CTRL + 0x38 + 4 * s, mode)
        mu = self.mu
        sp = 0xC3F00000 + self.sp_mod
        mu.reg_write(A.UC_ARM_REG_SP, sp)
        mu.reg_write(A.UC_ARM_REG_CPSR, 0x1D3)
        mu.reg_write(A.UC_ARM_REG_R0, CTRL)
        mu.reg_write(A.UC_ARM_REG_R1, 0)
        mu.reg_write(A.UC_ARM_REG_R2, 0)
        mu.reg_write(A.UC_ARM_REG_LR, STOP)
        for r in (A.UC_ARM_REG_R4, A.UC_ARM_REG_R5, A.UC_ARM_REG_R6, A.UC_ARM_REG_R7,
                  A.UC_ARM_REG_R8, A.UC_ARM_REG_R9, A.UC_ARM_REG_R10, A.UC_ARM_REG_R11):
            mu.reg_write(r, 0x11110000 + r)
        mu.emu_start(0xC0528700, STOP, count=50_000_000)
        assert mu.reg_read(A.UC_ARM_REG_SP) == sp, 'sp not restored'
        for r in (A.UC_ARM_REG_R4, A.UC_ARM_REG_R5, A.UC_ARM_REG_R6, A.UC_ARM_REG_R7,
                  A.UC_ARM_REG_R8, A.UC_ARM_REG_R9, A.UC_ARM_REG_R10, A.UC_ARM_REG_R11):
            assert mu.reg_read(r) == 0x11110000 + r, 'callee-saved reg clobbered'


TC = (251, 600, 58, 47)          # the two frame digits, roughly (TIMECODE_DISPLAY_COST)


def scenarios(src=SRC):
    """Each yields (name, rig, expectation dict) after running."""
    out = []

    def run(name, rounds, drawers, exp, **kw):
        g = Rig(src, **kw)
        for s, kinds in drawers.items():
            g.set_drawers(s, kinds)
        for rd in rounds:
            if callable(rd):
                rd(g); continue
            g.round(*rd)
        out.append((name, g, exp))

    run('uic small rect (timecode)', [(1, {0: {'uic': TC}})] * 3, {0: ['uic']},
        {'flushes': 0, 'fast': 3, 'max_lines': 47 * 4 * 3})
    run('uic small rect, sp=4 mod 8', [(1, {0: {'uic': TC}})], {0: ['uic']},
        {'flushes': 0, 'fast': 1}, sp_mod=4)
    run('uic full layer', [(1, {0: {'uic': (0, 0, W, H)}})], {0: ['uic']}, {'flushes': 0, 'fast': 1})
    run('uic rect off the left/top edge', [(1, {0: {'uic': (-20, -5, 60, 30)}})], {0: ['uic']},
        {'flushes': 0, 'fast': 1, 'max_lines': 50})
    run('uic rect past right/bottom edge', [(1, {0: {'uic': (1000, 670, 100, 100)}})], {0: ['uic']},
        {'flushes': 0, 'fast': 1, 'max_lines': 24})
    run('two uic slots', [(0b11, {0: {'uic': TC}, 1: {'uic': (10, 10, 300, 40)}})],
        {0: ['uic'], 1: ['uic']}, {'flushes': 0, 'fast': 1})
    run('clear then uic small rect', [(1, {0: {'uic': TC}}, {0: 2})], {0: ['uic']},
        {'flushes': 0, 'fast': 1, 'fulls': 1})
    run('other drawer -> stock flush', [(1, {0: {'other': (0, 0, 100, 100)}})], {0: ['other']},
        {'flushes': 1, 'fast': 0})
    run('uic + other in one slot -> stock flush', [(1, {0: {'uic': TC, 'other': (500, 0, 10, 10)}})],
        {0: ['uic', 'other']}, {'flushes': 1, 'fast': 0})

    def drop_other(g):
        g.other_copy = False
        g.set_drawers(0, ['uic'])
    run('memcpy by a drawer that then leaves',
        [lambda g: setattr(g, 'other_copy', True),
         (1, {0: {'uic': TC, 'other': (0, 0, 8, 8)}}), drop_other,
         (1, {0: {'uic': TC}}), (1, {0: {'uic': TC}})],
        {0: ['uic', 'other']}, {'flushes': 1, 'fast': 2, 'fulls': 1})
    run('copy mark survives a fast round of another slot',
        [lambda g: setattr(g, 'other_copy', True),
         (1, {0: {'uic': TC, 'other': (0, 0, 8, 8)}}), drop_other,
         (0b10, {1: {'uic': TC}}), (1, {0: {'uic': TC}})],
        {0: ['uic', 'other'], 1: ['uic']}, {'flushes': 1, 'fast': 2, 'fulls': 1})
    run('installer seeds C_COPY=0xF: first fast round per slot is whole-buffer',
        [lambda g: g.w(g.ctl + 0x0C, 0xF), (1, {0: {'uic': TC}}, {0: 2}), (1, {0: {'uic': TC}})],
        {0: ['uic']}, {'flushes': 0, 'fast': 2, 'fulls': 1})
    run('uic draws nothing, slot not dirty', [(1, {})], {0: ['uic']}, {'flushes': 0, 'fast': 0})
    run('disabled -> stock flush',
        [lambda g: g.w(g.ctl + 4, 0), (1, {0: {'uic': TC}})], {0: ['uic']}, {'flushes': 1, 'fast': 0})
    run('4bpp layer, last pixel opens a line', [(1, {0: {'uic': (200, 600, 57, 47)}})], {0: ['uic']},
        {'flushes': 0, 'fast': 1}, fmt=2)
    run('32bpp layer', [(1, {0: {'uic': TC}})], {0: ['uic']}, {'flushes': 0, 'fast': 1}, fmt=0)
    run('stock image, uic small rect', [(1, {0: {'uic': TC}})] * 2, {0: ['uic']},
        {'flushes': 2, 'fast': None}, patched=False)
    return out


def uic_object_from_image():
    """C055F0F0 = UIC singleton getter: movw/movt r4 = base, returns r4+0x14 (the r0 of C0561198)."""
    img = SEG0.read_bytes()
    wd = lambda a: struct.unpack_from('<I', img, a - 0xC0000000)[0]
    imm = lambda v: ((v >> 4) & 0xF000) | (v & 0xFFF)
    lo, hi, ret = wd(0xC055F0F4), wd(0xC055F0F8), wd(0xC055F180)
    assert (lo & 0x0FF0F000) == 0x03004000 and (hi & 0x0FF0F000) == 0x03404000, 'C055F0F4 movw/movt r4 changed'
    assert ret == 0xE2840014, 'C055F180 is no longer add r0, r4, #0x14'
    return ((imm(hi) << 16) | imm(lo)) + 0x14


def check(src=SRC, verbose=True):
    fails = []
    m = re.search(r'\.equ UIC_MGR,\s+(0x[0-9A-Fa-f]+)', pathlib.Path(src).read_text())
    if not m or int(m.group(1), 16) != uic_object_from_image() or UICMGR != uic_object_from_image():
        fails.append('UIC_MGR != C055F0F0() from the image')
        if verbose:
            print('BAD UIC_MGR', m and m.group(1), 'image says', hex(uic_object_from_image()))
    for name, g, exp in scenarios(src):
        problems = []
        if g.violations:
            problems.append(f'dirty at commit {g.violations[:2]}')
        if g.flushes != exp['flushes']:
            problems.append(f'flushes {g.flushes} != {exp["flushes"]}')
        if exp.get('fast') is not None and g.cr(0x14) != exp['fast']:
            problems.append(f'fast {g.cr(0x14)} != {exp["fast"]}')
        if 'fulls' in exp and g.cr(0x24) != exp['fulls']:
            problems.append(f'fulls {g.cr(0x24)} != {exp["fulls"]}')
        if 'max_lines' in exp and g.cr(0x1C) > exp['max_lines']:
            problems.append(f'lines {g.cr(0x1C)} > {exp["max_lines"]}')
        if verbose:
            lines = g.cr(0x1C) if g.patched else '-'
            print(f'{"ok " if not problems else "BAD"} {name:42s} commits={g.commits} '
                  f'flushes={g.flushes} lines={lines} why={g.cr(0x20) if g.patched else "-"}'
                  + ('' if not problems else '  ' + '; '.join(problems)))
        if problems:
            fails.append(name)
    return fails


MUTANTS = [
    ('one row short', r'subs    r2, r2, #1\n        bne     13b', 'subs    r2, r2, #1\n        cmp     r2, #1\n        bgt     13b'),
    ('end byte not +1', 'add     r3, r0, #1', 'mov     r3, r0'),
    ('ignore clear marks', 'ldr     r0, [r10, #C_CLEAR]\n        ldr     r1, [r10, #C_COPY]',
     'mov     r0, #0\n        ldr     r1, [r10, #C_COPY]'),
    ('ignore copy marks', 'ldr     r1, [r10, #C_COPY]\n        orr', 'mov     r1, #0\n        orr'),
    ('no drawer type check', 'movne   r0, #3\n        bne     fallback', 'movne   r0, #3\n        nop'),
    ('only slot 0', 'cmp     r5, #4\n        blt     10b', 'cmp     r5, #1\n        blt     10b'),
    ('clear hook marks nothing', 'str     r3, [ip, #C_CLEAR]', 'nop'),
    ('copy hook marks nothing', 'str     r3, [ip, #C_COPY]', 'nop'),
    ('copy marks consumed by fallback only', 'bic     r0, r0, r1\n        str     r0, [r10, #C_COPY]',
     'mov     r0, #0\n        str     r0, [r10, #C_COPY]'),
    ('x not clamped', 'addlt   r2, r2, r0\n        movlt   r0, #0', 'nop\n        nop'),
    ('w not clamped', 'cmp     r2, ip\n        movgt   r2, ip', 'cmp     r2, ip\n        nop'),
    ('h not clamped', 'cmp     r3, ip\n        movgt   r3, ip', 'cmp     r3, ip\n        nop'),
    ('old UIC object address', '.equ UIC_MGR,      0xC37B7048', '.equ UIC_MGR,      0xC37B7034'),
    ('row stride wrong', 'mla     r1, r1, ip, r8          @ row base', 'add     r1, r8, r1, lsl #11'),
]


def mutate():
    src = SRC.read_text()
    survivors = []
    for name, old, new in MUTANTS:
        n = len(re.findall(re.escape(old), src)) if not old.startswith('subs    r2, r2, #1\\n') else None
        body = src.replace(old.replace('\\n', '\n'), new, 1)
        assert body != src, f'mutant {name!r} did not apply'
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / 'm.S'
            p.write_text(body)
            try:
                fails = check(p, verbose=False)
            except BaseException as e:               # crash/assert/assemble error counts as caught
                fails = [f'exception {type(e).__name__}: {e}']
        print(f'{"caught  " if fails else "SURVIVED"} {name}: {fails[:2]}')
        if not fails:
            survivors.append(name)
    return survivors


if __name__ == '__main__':
    if '--mutate' in sys.argv:
        s = mutate()
        print('survivors:', s)
        sys.exit(1 if s else 0)
    f = check()
    print('FAILED:' if f else 'all scenarios pass', f)
    sys.exit(1 if f else 0)
