"""Bit-exactness tests: stock span/fill vs neonblit.S, both run in unicorn on
the real firmware image (out/seg0_c0000000.bin).

    python3 -B test_neonblit.py            # all cases + instruction counts
    python3 -B test_neonblit.py --mutate   # every mutation must fail a case
    python3 -B test_neonblit.py --quick    # fewer random cases

For each case the stock Thumb function and the replacement run from identical
memory; the whole destination area (with guard bytes around it) must match,
r4-r11 / sp / d8-d15 / FPSCR must be preserved, d16-d31 must be untouched.
"""
import pathlib, random, struct, sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402
sys.path.insert(0, str(HERE))
import xci  # noqa: E402

SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
SRC = HERE / 'neonblit.S'
CODE = 0x46000000          # replacement code (heap-like address, ARM)
STOP = 0x45F00000          # return address
STACK = 0x47000000         # stack top region
DST = 0x48000000           # destination buffer
SRCB = 0x49000000          # source buffer
LUT = 0x4A000000
PARAM = 0x4A100000         # span parameter block (r3)
DESC = 0x4A200000          # source descriptor copy (r1)
LAYER = 0x4A300000         # fake layer object + vtable + stubs
GUARD = 64

STOCK = {                  # driver 6, span table 1 (0xC2EB3F5C)
    'p32_blend': 0xC06FB9A9,   # idx 0
    'p32_opaque': 0xC06FBBA9,  # idx 1
    '565_opaque': 0xC06FC039,  # idx 2
    'lut8_blend': 0xC06FBC09,  # idx 3, 6, 11-14
    'a4_blend': 0xC06FBCD9,    # idx 7 (ARGB4444 source, font_M_* glyphs)
}
BPP = {'p32_blend': 4, 'p32_opaque': 4, '565_opaque': 2, 'lut8_blend': 1, 'a4_blend': 2}
GLYPHS = []                # decoded 29x47 font_M_* digits (ARGB4444), filled in main()
FILL_STOCK = 0xC0721480    # ARM, layer vtable slot


class Rig:
    def __init__(self, defines=()):
        self.code = assemble(SRC, defines)
        self.sym = symbols(SRC, defines)
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A7)
        mu.mem_map(0xC0000000, 0x02F00000)
        img = SEG0.read_bytes()
        mu.mem_write(0xC0000000, img[:0x02F00000])
        for base in (CODE, STOP, STACK - 0x100000, DST, SRCB, LUT, PARAM, DESC, LAYER):
            mu.mem_map(base & ~0xFFFFF, 0x100000)
        mu.mem_write(CODE, self.code)
        mu.mem_write(STOP, struct.pack('<I', 0xEAFFFFFE))   # b .
        mu.reg_write(A.UC_ARM_REG_C1_C0_2, 0x00F00000)       # CPACR cp10/11
        mu.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        self.count = 0
        self.counting = False
        # one permanent hook: unicorn does not apply hooks added later to
        # blocks it has already translated
        mu.hook_add(UC_HOOK_CODE, self._cnt)

    def w(self, a, v):
        self.mu.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))

    def r(self, a):
        return struct.unpack('<I', self.mu.mem_read(a, 4))[0]

    def call(self, addr, args, count=False):
        mu = self.mu
        for i, v in enumerate(args):
            mu.reg_write(A.UC_ARM_REG_R0 + i, v & 0xFFFFFFFF)
        rnd = random.Random(addr ^ len(args))
        saved = {}
        for reg in range(4, 12):
            v = rnd.getrandbits(32)
            mu.reg_write(A.UC_ARM_REG_R4 + reg - 4, v)
            saved['r%d' % reg] = v
        dregs = {}
        for d in range(32):
            v = rnd.getrandbits(64)
            mu.reg_write(A.UC_ARM_REG_D0 + d, v)
            dregs[d] = v
        mu.reg_write(A.UC_ARM_REG_FPSCR, 0)
        sp = STACK - 0x100 - (rnd.getrandbits(1) * 4)   # also the sp = 4 mod 8 case
        mu.reg_write(A.UC_ARM_REG_SP, sp)
        mu.reg_write(A.UC_ARM_REG_LR, STOP)
        self.count = 0
        self.counting = count
        mu.emu_start(addr, STOP, count=50_000_000)
        self.counting = False
        bad = []
        for reg in range(4, 12):
            if mu.reg_read(A.UC_ARM_REG_R4 + reg - 4) != saved['r%d' % reg]:
                bad.append('r%d' % reg)
        if mu.reg_read(A.UC_ARM_REG_SP) != sp:
            bad.append('sp')
        for d in list(range(8, 16)) + list(range(16, 32)):
            if mu.reg_read(A.UC_ARM_REG_D0 + d) != dregs[d]:
                bad.append('d%d' % d)
        if mu.reg_read(A.UC_ARM_REG_FPSCR) != 0:
            bad.append('fpscr')
        return bad

    def _cnt(self, mu, addr, size, _):
        if self.counting:
            self.count += 1


def setup_span(rig, kind, width, rows, sstride, dstride, src_off, dst_bytes, src_bytes, lut):
    mu = rig.mu
    assert len(dst_bytes) >= 2 * GUARD and len(src_bytes) >= 2 * GUARD and len(lut) == 1024
    mu.mem_write(DST, dst_bytes)
    mu.mem_write(SRCB, src_bytes)
    mu.mem_write(LUT, lut)
    src_ptr = SRCB + GUARD + src_off
    rig.w(DESC + 0x24, src_ptr)
    rig.w(DESC + 0x1c, sstride)
    rig.w(PARAM + 4, LUT)
    rig.w(PARAM + 8, dstride)
    rig.w(PARAM + 0xc, rows)
    return [DST + GUARD, DESC, width, PARAM]


def run_span(rig, kind, case, which, count=False):
    args = setup_span(rig, kind, *case)
    addr = STOCK[kind] if which == 'stock' else CODE + rig.sym['nb_' + kind]
    bad = rig.call(addr, args, count)
    size = len(case[6])
    return bytes(rig.mu.mem_read(DST, size)), (bad if which != 'stock' else []), rig.count


EDGE_A = [0, 1, 2, 126, 127, 128, 129, 253, 254, 255]


def make_case(rnd, kind, icons, width=None, rows=None):
    bpp = BPP[kind]
    if width is None:
        width = rnd.choice([0, 1, 2, 3, 7, 8, 9, 15, 16, 17, 23, 31, 33, 64, 65, rnd.randint(0, 80)])
    if rows is None:
        rows = rnd.choice([0, 1, 1, 2, 3, 4])
    sstride = width + rnd.choice([0, 0, 1, 3, 8])
    dstride = width + rnd.choice([0, 0, 1, 2, 5])
    if kind == 'lut8_blend':
        src_off = rnd.randint(0, 7)
    else:
        src_off = rnd.randint(0, 3) * bpp
    dst_len = GUARD * 2 + max(rows, 1) * max(dstride, 1) * 2 + 32
    src_len = GUARD * 2 + max(rows, 1) * max(sstride, 1) * bpp + 64
    mode = rnd.random()
    if icons and mode < 0.4:
        ic = rnd.choice(icons)
        s0 = rnd.randrange(len(ic) // 2) * 2
        dst = bytes(ic[(s0 + i) % len(ic)] for i in range(dst_len))
    else:
        dst = bytes(rnd.getrandbits(8) for _ in range(dst_len))
    src = bytearray(rnd.getrandbits(8) for _ in range(src_len))
    lut = bytearray(rnd.getrandbits(8) for _ in range(1024))
    if mode < 0.7 and bpp == 4:
        # premultiplied, edge alphas; sometimes from a real icon's colours
        for i in range(0, src_len - 3, 4):
            a = rnd.choice(EDGE_A + [rnd.getrandbits(8)])
            if icons and mode < 0.4:
                ic = rnd.choice(icons)
                p = struct.unpack_from('<H', ic, rnd.randrange(len(ic) // 2) * 2)[0]
                c = [((p >> s) & 15) * 17 for s in (8, 4, 0)]
            else:
                c = [rnd.getrandbits(8) for _ in range(3)]
            src[i:i + 4] = bytes([x * a // 255 for x in c] + [a])
    if kind == 'a4_blend' and GLYPHS and mode < 0.5:
        g = rnd.choice(GLYPHS)
        s0 = rnd.randrange(len(g) // 2) * 2
        src = bytearray(g[(s0 + i) % len(g)] for i in range(src_len))
    elif kind == 'a4_blend' and mode < 0.8:
        for i in range(0, src_len - 1, 2):     # every alpha nibble, random colour
            p = (rnd.randrange(16) << 12) | rnd.getrandbits(12)
            src[i:i + 2] = struct.pack('<H', p)
    if mode < 0.7:
        for i in range(0, 1024, 4):
            a = rnd.choice(EDGE_A + [rnd.getrandbits(8)])
            c = [rnd.getrandbits(8) * a // 255 for _ in range(3)]
            lut[i:i + 4] = bytes(c + [a])
    return (width, rows, sstride, dstride, src_off, bytes(dst), bytes(src), bytes(lut))


def check_span(rig, kind, case):
    a, _, _ = run_span(rig, kind, case, 'stock')
    try:
        b, bad, _ = run_span(rig, kind, case, 'new')
    except Exception as e:              # a crash is a failure, not a pass
        return False, [repr(e)]
    return a == b and not bad, bad


# --- layer fill ------------------------------------------------------------
STUB30 = LAYER + 0x800      # vt+0x30: return [LAYER+0x700]
STUB10 = LAYER + 0x900      # vt+0x10: return LAYER+0x600 (buffer holder)


def setup_fill(rig, fmt, width, height, buf, ok, dst_bytes):
    mu = rig.mu
    vt = LAYER + 0x400
    rig.w(LAYER, vt)
    rig.w(LAYER + 4, width)
    rig.w(LAYER + 8, height)
    for k in range(3, 7):
        rig.w(LAYER + 4 * k, 0x11110000 + k)
    rig.w(LAYER + 0x1c, fmt)
    rig.w(vt + 0x30, STUB30)
    rig.w(vt + 0x10, STUB10)
    rig.w(LAYER + 0x700, ok)
    rig.w(LAYER + 0x604, buf)
    # ldr r0,[pc,#..] / bx lr stubs (ARM)
    mu.mem_write(STUB30, struct.pack('<III', 0xE59F0000, 0xE12FFF1E, ok))
    mu.mem_write(STUB10, struct.pack('<III', 0xE59F0000, 0xE12FFF1E, LAYER + 0x600))
    mu.mem_write(DST, dst_bytes)


def run_fill(rig, case, which, count=False):
    fmt, width, height, off, ok, value, dst = case
    setup_fill(rig, fmt, width, height, DST + GUARD + off, ok, dst)
    addr = FILL_STOCK if which == 'stock' else CODE + rig.sym['nb_layer_fill']
    bad = rig.call(addr, [LAYER, value], count)
    r0 = rig.mu.reg_read(A.UC_ARM_REG_R0)
    return bytes(rig.mu.mem_read(DST, len(dst))), r0, (bad if which != 'stock' else []), rig.count


def make_fill(rnd, fmt=1):
    width = rnd.choice([0, 1, 2, 3, 5, 7, 8, 9, 16, 31, 33, 64, rnd.randint(0, 200)])
    height = rnd.choice([0, 1, 2, 3, rnd.randint(0, 6)])
    off = rnd.randint(0, 15) & ~1 if rnd.random() < 0.8 else rnd.randint(0, 15)
    ok = rnd.choice([1, 1, 1, 0])
    value = rnd.getrandbits(32)
    n = GUARD * 2 + 2 * width * height + 64
    dst = bytes(rnd.getrandbits(8) for _ in range(n))
    return (fmt, width, height, off, ok, value, dst)


def check_fill(rig, case):
    a, ra, _, _ = run_fill(rig, case, 'stock')
    try:
        b, rb, bad, _ = run_fill(rig, case, 'new')
    except Exception as e:
        return False, [repr(e)]
    return a == b and ra == rb and not bad, bad + ([] if ra == rb else ['r0'])


# --- driver ----------------------------------------------------------------
def all_cases(rig, n, icons, stop_on_fail=False):
    rnd = random.Random(20261019)
    fails = []
    for kind in STOCK:
        for i in range(n):
            case = make_case(rnd, kind, icons)
            ok, bad = check_span(rig, kind, case)
            if not ok:
                fails.append((kind, case[:5], bad))
                if stop_on_fail:
                    return fails
    for i in range(n):
        case = make_fill(rnd)
        ok, bad = check_fill(rig, case)
        if not ok:
            fails.append(('fill', case[:6], bad))
            if stop_on_fail:
                return fails
    # non-16bpp fill must reach the stock function untouched
    for fmt in (0, 3, 2):
        case = make_fill(rnd, fmt=fmt)
        case = (fmt,) + case[1:]
        try:
            ok, bad = check_fill(rig, case)
        except Exception as e:          # both paths run the same stock code
            ok, bad = False, [repr(e)]
        if not ok:
            fails.append(('fill-fmt%d' % fmt, case[:6], bad))
    return fails


def counts(rig, icons):
    rnd = random.Random(7)
    print('instructions per pixel (one 1024-pixel row, stock vs neon):')
    for kind in STOCK:
        case = make_case(rnd, kind, icons, width=1024, rows=1)
        _, _, cs = run_span(rig, kind, case, 'stock', count=True)
        _, _, cn = run_span(rig, kind, case, 'new', count=True)
        print('  %-11s %6.2f -> %5.2f  (x%.1f)' % (kind, cs / 1024, cn / 1024, cs / cn))
    case = (1, 1024, 64, 0, 1, 0xF000F000, bytes(GUARD * 2 + 2 * 1024 * 64 + 64))
    _, _, _, cs = run_fill(rig, case, 'stock', count=True)
    _, _, _, cn = run_fill(rig, case, 'new', count=True)
    print('  %-11s %6.2f -> %5.2f  (x%.1f)' % ('layer_fill', cs / 65536, cn / 65536, cs / cn))


MUTATIONS = ['MUT_ROUND', 'MUT_OR_ADD', 'MUT_TAIL', 'MUT_OPQ', 'MUT_565', 'MUT_LUT', 'MUT_FILL', 'MUT_SAVE',
             'MUT_A4', 'MUT_A4T', 'MUT_A4S']


def load_glyphs():
    import xci as _x
    rom = SEG0.read_bytes()
    i = rom.find(b'XC\x00\x00', 0x1000000)
    while 0 <= i < 0x1800000:
        if struct.unpack_from('<HH', rom, i + 8) == (29, 47):
            d = _x.decode(rom, i)
            if d and len(d[2]) == 29 * 47 * 2:
                GLYPHS.append(d[2])
        i = rom.find(b'XC\x00\x00', i + 4)
    return len(GLYPHS)


def main():
    quick = '--quick' in sys.argv
    n = 60 if quick else 400
    icons = xci.sample_icons(12)
    print('font_M_ glyphs (29x47 ARGB4444):', load_glyphs())
    if '--mutate' in sys.argv:
        survivors = []
        for m in MUTATIONS:
            rig = Rig((m,))
            fails = all_cases(rig, 80, icons, stop_on_fail=True)
            print('%-10s %s' % (m, 'caught' if fails else 'SURVIVED'))
            if not fails:
                survivors.append(m)
        sys.exit(1 if survivors else 0)
    rig = Rig()
    fails = all_cases(rig, n, icons)
    total = n * (len(STOCK) + 1) + 3
    print('cases: %d, failures: %d' % (total, len(fails)))
    for f in fails[:10]:
        print('  FAIL', f)
    counts(rig, icons)
    ef = e2e(40 if quick else 150)
    worst = bench(Rig(), icons)
    sys.exit(1 if fails or ef or worst > 1.0 else 0)


# --- end to end through the stock 1:1 dispatcher C07080D0 -------------------
# Builds a fake engine context / surface / image, sets the two span pointers
# the selector (C06E0970) would have stored, and runs the real C07080D0 once
# with the stock spans and once with ours.  Covers the run-table path
# (opaque / blend / skip runs with partial widths), clipping and strides.
CTX = 0x4B000000            # engine context; r5 = CTX + 0x8188
SURF = 0x4B100000
IMG = 0x4B200000
RUNS = 0x4B300000
SBUF = 0x4C000000           # surface pixels (ARGB4444)
IBUF = 0x4D000000           # image pixels
DISPATCH = 0xC07080D1
PAIR = {   # main span (blend runs / no table) and opaque-run span, per source
    'p32': ('p32_blend', 'p32_opaque', 0x20, 4),
    '565': ('565_opaque', '565_opaque', 0x10, 2),
    'lut8': ('lut8_blend', 'lut8_blend', 0x00, 1),
    'a4': ('a4_blend', 'a4_blend', 0x10, 2),
}


def e2e_case(rig, rnd, src, which):
    main_k, opq_k, flag, bpp = PAIR[src]
    mu = rig.mu
    for base in (CTX, SURF, IMG, RUNS, SBUF, IBUF):
        try:
            mu.mem_map(base, 0x100000 if base < SBUF else 0x400000)
        except Exception:
            pass
    sw, sh = rnd.randint(8, 120), rnd.randint(4, 40)
    sstride = sw + rnd.randint(0, 9)
    iw, ih = rnd.randint(1, 100), rnd.randint(1, 30)
    istride = iw + rnd.randint(0, 9)
    surf = bytes(rnd.getrandbits(8) for _ in range(2 * sstride * (sh + 2)))
    img = bytearray(rnd.getrandbits(8) for _ in range(bpp * istride * (ih + 2)))
    if bpp == 4:
        for i in range(0, len(img) - 3, 4):
            a = rnd.choice(EDGE_A)
            img[i:i + 4] = bytes([rnd.getrandbits(8) * a // 255 for _ in range(3)] + [a])
    if src == 'a4' and GLYPHS:
        g = rnd.choice(GLYPHS)
        img = bytearray(g[i % len(g)] for i in range(len(img)))
    lut = bytearray(1024)
    for i in range(0, 1024, 4):
        a = rnd.choice(EDGE_A)
        lut[i:i + 4] = bytes([rnd.getrandbits(8) * a // 255 for _ in range(3)] + [a])
    mu.mem_write(SBUF, surf); mu.mem_write(IBUF, bytes(img)); mu.mem_write(LUT, bytes(lut))
    r5 = CTX + 0x8188
    w = rig.w
    w(r5, SURF)
    cx, cy = rnd.randint(0, 6), rnd.randint(0, 4)
    w(r5 + 8, cx); w(r5 + 0xc, cy); w(r5 + 0x10, sw - cx - rnd.randint(0, 6)); w(r5 + 0x14, sh - cy - rnd.randint(0, 4))
    stock = {k: STOCK[k] for k in STOCK}
    new = {k: CODE + rig.sym['nb_' + k] for k in STOCK}
    tab = stock if which == 'stock' else new
    w(r5 + 0x4e0, tab[opq_k]); w(r5 + 0x4e4, tab[main_k])
    w(r5 + 0x4d8, LUT); w(r5 + 0x4dc, LUT); w(r5 + 0xc8, 0)
    w(SURF + 8, 0x10); w(SURF + 0x1c, sstride); w(SURF + 0x24, SBUF); w(SURF + 0x18, 0)
    w(IMG + 0x14, iw); w(IMG + 0x18, ih); w(IMG + 0x1c, istride); w(IMG + 0x24, IBUF)
    w(IMG + 0x48, flag)
    use_runs = rnd.random() < 0.6
    w(IMG + 0x10, 1 if use_runs else 0); w(IMG + 0x28, RUNS if use_runs else 0)
    if use_runs:
        tbl = bytearray()
        for _ in range(ih):
            x, row = 0, []
            for k in range(4):
                if x >= iw or rnd.random() < 0.15:
                    row.append(3 << 14); break
                n = rnd.randint(1, iw - x)
                row.append((rnd.choice([0, 1, 2]) << 14) | n); x += n
            row += [3 << 14] * (4 - len(row))
            tbl += struct.pack('<4H', *row)
        mu.mem_write(RUNS, bytes(tbl))
    px, py = rnd.randint(-10, sw), rnd.randint(-6, sh)
    w(IMG + 0x80, px << 16); w(IMG + 0x84, py << 16)
    bad = rig.call(DISPATCH, [CTX, IMG + 0x80, IMG, 0], count=True)
    rig.last = rig.count
    return bytes(mu.mem_read(SBUF, len(surf))), bad


def e2e(n=150):
    rig = Rig()
    fails = 0
    for src in PAIR:
        for i in range(n):
            ra = random.Random(i * 7 + len(src))
            a, _ = e2e_case(rig, ra, src, 'stock')
            rb = random.Random(i * 7 + len(src))
            b, _ = e2e_case(rig, rb, src, 'new')
            if a != b:
                fails += 1
    print('end-to-end through C07080D0: %d cases, failures: %d' % (n * len(PAIR), fails))
    return fails



# --- realistic speed: whole C07080D0 calls, stock spans vs ours ----------------
def runs_from_alpha(pix, w, h):
    """Run table like the 4-entry rows C07080D0 reads: A==0 skip(2), A==F
    opaque(0), else blend(1); more than 4 runs in a row -> tail merged as blend."""
    tbl = bytearray()
    for y in range(h):
        segs = []
        for x in range(w):
            a = pix[y * w + x] >> 12
            t = 2 if a == 0 else (0 if a == 15 else 1)
            if segs and segs[-1][0] == t:
                segs[-1][1] += 1
            else:
                segs.append([t, 1])
        while len(segs) > 4:
            t2, n2 = segs.pop(); t1, n1 = segs.pop()
            segs.append([1, n1 + n2])
        row = [(t << 14) | n for t, n in segs] + [3 << 14] * (4 - len(segs))
        tbl += struct.pack('<4H', *row)
    return bytes(tbl)


def bench_case(rig, kind, img_pix, iw, ih, use_runs, rnd, which):
    """One C07080D0 call drawing an iw x ih ARGB4444 (or other) image fully
    inside a surface; returns (surface bytes, instruction count)."""
    mu = rig.mu
    for base in (CTX, SURF, IMG, RUNS, SBUF, IBUF):
        try:
            mu.mem_map(base, 0x100000 if base < SBUF else 0x400000)
        except Exception:
            pass
    main_k, opq_k, flag, bpp = PAIR[kind]
    sw, sh = iw + 20, ih + 10
    surf = bytes(rnd.getrandbits(8) for _ in range(2 * sw * (sh + 2)))
    mu.mem_write(SBUF, surf); mu.mem_write(IBUF, img_pix)
    r5 = CTX + 0x8188
    w = rig.w
    w(r5, SURF); w(r5 + 8, 0); w(r5 + 0xc, 0); w(r5 + 0x10, sw); w(r5 + 0x14, sh)
    tab = STOCK if which == 'stock' else {k: CODE + rig.sym['nb_' + k] for k in STOCK}
    w(r5 + 0x4e0, tab[opq_k]); w(r5 + 0x4e4, tab[main_k])
    w(r5 + 0x4d8, LUT); w(r5 + 0x4dc, LUT); w(r5 + 0xc8, 0)
    w(SURF + 8, 0x10); w(SURF + 0x1c, sw); w(SURF + 0x24, SBUF); w(SURF + 0x18, 0)
    w(IMG + 0x14, iw); w(IMG + 0x18, ih); w(IMG + 0x1c, iw); w(IMG + 0x24, IBUF)
    w(IMG + 0x48, flag)
    if use_runs:
        pix = struct.unpack('<%dH' % (iw * ih), img_pix[:2 * iw * ih])
        mu.mem_write(RUNS, runs_from_alpha(pix, iw, ih))
    w(IMG + 0x10, 1 if use_runs else 0); w(IMG + 0x28, RUNS if use_runs else 0)
    px, py = rnd.randint(0, sw - iw), rnd.randint(0, sh - ih)
    w(IMG + 0x80, px << 16); w(IMG + 0x84, py << 16)
    rig.call(DISPATCH, [CTX, IMG + 0x80, IMG, 0], count=True)
    return bytes(mu.mem_read(SBUF, len(surf))), rig.count


def bench(rig, icons):
    print('whole-draw instructions through C07080D0 (stock -> new), real data:')
    worst = 0.0
    scen = []
    for gi, g in enumerate(GLYPHS):
        scen.append(('glyph%02d' % gi, g, 29, 47))
    ic16 = [ic for ic in icons if len(ic) >= 2 * 32 * 32][:6]
    for k, ic in enumerate(ic16):
        scen.append(('icon%d' % k, ic[:2 * 32 * 32], 32, 32))
    rnd0 = random.Random(5)
    rnd_img = b''.join(struct.pack('<H', (rnd0.randrange(16) << 12) | rnd0.getrandbits(12)) for _ in range(40 * 20))
    scen.append(('random-alpha', rnd_img, 40, 20))
    tot = {}
    for runs in (True, False):
        ts = tn = 0
        for name, pix, iw, ih in scen:
            ra = random.Random(hash(name) & 0xFFFF)
            a, cs = bench_case(rig, 'a4', pix, iw, ih, runs, ra, 'stock')
            rb = random.Random(hash(name) & 0xFFFF)
            b, cn = bench_case(rig, 'a4', pix, iw, ih, runs, rb, 'new')
            assert a == b, ('bench mismatch', name, runs)
            ts += cs; tn += cn
            worst = max(worst, cn / cs)
            if name in ('glyph00', 'glyph05', 'icon0', 'random-alpha'):
                print('  a4 %-13s runs=%d  %8d -> %8d  (x%.2f)' % (name, runs, cs, cn, cs / cn))
        tot[runs] = (ts, tn)
        print('  a4 ALL %d images  runs=%d  %8d -> %8d  (x%.2f)' % (len(scen), runs, ts, tn, ts / tn))
    # other spans: the e2e random scenes (clipping, run tables with short runs)
    for src in ('p32', '565', 'lut8'):
        ts = tn = 0
        for i in range(60):
            ra = random.Random(i * 13 + len(src))
            rig.count = 0
            e2e_case_count = []
            a, _ = e2e_case(rig, ra, src, 'stock'); cs = rig.last
            rb = random.Random(i * 13 + len(src))
            b, _ = e2e_case(rig, rb, src, 'new'); cn = rig.last
            assert a == b
            ts += cs; tn += cn
            worst = max(worst, cn / cs if cs else 1)
        print('  %-4s 60 random scenes            %8d -> %8d  (x%.2f)' % (src, ts, tn, ts / tn))
    print('  worst single draw new/stock = %.3f' % worst)
    return worst


if __name__ == '__main__':
    main()
