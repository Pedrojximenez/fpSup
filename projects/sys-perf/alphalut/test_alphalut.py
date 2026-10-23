"""Bit-exactness: stock C0563BA8 vs alphalut.S al_unpremul, unicorn on the real image.

    python3 -B test_alphalut.py            # all cases + instruction counts
    python3 -B test_alphalut.py --mutate   # every mutation must fail some case

Each case runs stock and replacement from identical memory; the whole buffer
(with guards) must match; r4-r11/sp/d8-d15/FPSCR preserved; d16-d31 untouched.
A separate unicorn instance runs the patched call site C0561734 (code written
before any execution there, so no stale translated block).
"""
import pathlib, random, struct, sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
SRC = HERE / 'alphalut.S'
STOCK = 0xC0563BA8
TBL = 0xC0D0D684
CALLSITE = 0xC0561734
CODE = 0x46000000
STOP = 0x45F00000
STACK = 0x47000000
BUF = 0x48000000
RECT = 0x4A000000
GUARD = 256
VENEER = 0xC072EF00          # inside the image map, within BL range of C0561734
K = [0, 3840, 1920, 1280, 960, 768, 640, 549, 480, 427, 384, 350, 320, 296, 275, 256]


class Rig:
    def __init__(self, defines=(), patch_callsite=False):
        self.code = assemble(SRC, defines)
        self.sym = symbols(SRC, defines)
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A7)
        mu.mem_map(0xC0000000, 0x02F00000)
        mu.mem_write(0xC0000000, SEG0.read_bytes()[:0x02F00000])
        for base in (CODE, STOP, STACK - 0x100000, RECT):
            mu.mem_map(base, 0x100000)
        mu.mem_map(BUF, 0x01000000)
        mu.mem_write(CODE, self.code)
        mu.mem_write(STOP, struct.pack('<I', 0xEAFFFFFE))
        mu.reg_write(A.UC_ARM_REG_C1_C0_2, 0x00F00000)
        mu.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        if patch_callsite:
            ent = CODE + self.sym['al_unpremul']
            mu.mem_write(VENEER, struct.pack('<II', 0xE51FF004, ent))      # ldr pc, [pc, #-4]
            off = (VENEER - (CALLSITE + 8)) >> 2
            mu.mem_write(CALLSITE, struct.pack('<I', 0xEB000000 | (off & 0xFFFFFF)))
        self.n = 0
        self.lo, self.hi = 0, 0
        mu.hook_add(UC_HOOK_CODE, self._cnt)

    def _cnt(self, mu, addr, size, ud):
        if self.lo <= addr < self.hi:
            self.n += 1

    def ctl(self, off, v=None):
        a = CODE + off
        if v is None:
            return struct.unpack('<I', self.mu.mem_read(a, 4))[0]
        self.mu.mem_write(a, struct.pack('<I', v))

    def run(self, fn, buf_img, rect, stride, seed, count_range=None):
        mu = self.mu
        mu.mem_write(BUF, buf_img)
        mu.mem_write(RECT, struct.pack('<4i', *rect))
        rnd = random.Random(seed)
        keep = {r: rnd.getrandbits(32) for r in range(A.UC_ARM_REG_R4, A.UC_ARM_REG_R11 + 1)}
        for r, v in keep.items():
            mu.reg_write(r, v)
        dkeep = {}
        for i in range(32):
            v = rnd.getrandbits(64)
            mu.reg_write(A.UC_ARM_REG_D0 + i, v)
            dkeep[i] = v
        mu.reg_write(A.UC_ARM_REG_FPSCR, 0)
        sp = STACK - 0x40
        mu.reg_write(A.UC_ARM_REG_SP, sp)
        mu.reg_write(A.UC_ARM_REG_R0, BUF + GUARD)
        mu.reg_write(A.UC_ARM_REG_R1, RECT)
        mu.reg_write(A.UC_ARM_REG_R2, stride & 0xFFFFFFFF)
        mu.reg_write(A.UC_ARM_REG_LR, STOP)
        self.n = 0
        self.lo, self.hi = count_range or (0, 0)
        mu.emu_start(fn, STOP, count=50_000_000)
        out = bytes(mu.mem_read(BUF, len(buf_img)))
        bad = [r for r, v in keep.items() if mu.reg_read(r) != v]
        if mu.reg_read(A.UC_ARM_REG_SP) != sp:
            bad.append('sp')
        bad += [f'd{i}' for i in range(8, 32) if mu.reg_read(A.UC_ARM_REG_D0 + i) != dkeep[i]]
        if mu.reg_read(A.UC_ARM_REG_FPSCR) & 0xF8000000:
            bad.append('fpscr')
        return out, bad, self.n


def cases(rnd):
    c = []
    # every pixel value once: 256 x 256, aligned and unaligned start
    allpx = b''.join(struct.pack('<H', v) for v in range(65536))
    c.append(('all-values', allpx, (0, 0, 256, 256), 256))
    c.append(('all-values-odd-x', b'\0\0' + allpx[:-2], (1, 0, 255, 256), 256))
    for i in range(400):
        w = rnd.choice([1, 2, 3, 7, 8, 9, 15, 16, 17, 31, 33, rnd.randint(1, 80), 1024])
        h = rnd.randint(1, 4)
        x = rnd.randint(0, 9)
        y = rnd.randint(0, 3)
        stride = x + w + rnd.randint(0, 9)
        n = stride * (y + h) + 8
        kind = i % 5
        px = []
        for _ in range(n):
            if kind == 0:
                px.append(rnd.getrandbits(16))
            elif kind == 1:                     # UI-like: zero, opaque, a few blends
                px.append(rnd.choice([0, 0, 0, 0xF000 | rnd.getrandbits(12), rnd.getrandbits(16)]))
            elif kind == 2:                     # runs of equal words (stock cache path)
                px.append(px[-1] if px and rnd.random() < 0.8 else rnd.getrandbits(16))
            elif kind == 3:                     # each alpha, random colour
                px.append((rnd.randint(0, 15) << 12) | rnd.getrandbits(12))
            else:                               # long zero spans with islands
                px.append(0 if rnd.random() < 0.7 else rnd.getrandbits(16))
        c.append((f'rand{i}-k{kind}-w{w}h{h}x{x}', struct.pack(f'<{n}H', *px), (x, y, w, h), stride))
    # odd geometry: stock handles these itself (fallback)
    base = bytes(rnd.getrandbits(8) for _ in range(512))
    for r in [(1, 0, 0, 2), (0, 0, 0, 2), (0, 0, 5, 0), (0, 0, 5, -3), (2, 0, -3, 2)]:
        c.append((f'fallback{r}', base, r, 20))
    return c


def check(defines=(), quiet=False):
    rnd = random.Random(1234)
    rig = Rig(defines)
    ent = CODE + rig.sym['al_unpremul']
    fails = 0
    for name, img, rect, stride in cases(rnd):
        buf = b'\xA5' * GUARD + img + b'\x5A' * GUARD
        ref, bad0, _ = rig.run(STOCK, buf, rect, stride, 7)
        got, bad, _ = rig.run(ent, buf, rect, stride, 7)
        if bad0:
            raise SystemExit(f'stock clobbered {bad0}?')
        if got != ref or bad:
            fails += 1
            if not quiet and fails <= 3:
                diff = next(i for i in range(len(ref)) if got[i] != ref[i]) if got != ref else None
                print(f'  FAIL {name}: first diff byte {diff}, regs {bad}')
    # enable = 0 -> stock path, same bytes
    rig.ctl(0x08, 0)
    img = bytes(random.Random(5).getrandbits(8) for _ in range(4000))
    buf = b'\xA5' * GUARD + img + b'\x5A' * GUARD
    ref, _, _ = rig.run(STOCK, buf, (1, 1, 30, 3), 40, 3)
    got, bad, _ = rig.run(ent, buf, (1, 1, 30, 3), 40, 3)
    if got != ref or bad:
        fails += 1
    rig.ctl(0x08, 1)
    # table identity: K reproduces the image table for all 256 cells
    tbl = bytes(rig.mu.mem_read(TBL, 256))
    if not all(tbl[a * 16 + c] == min(15, (c * K[a]) >> 8) for a in range(16) for c in range(16)):
        fails += 1
    # patched call site, separate instance
    rig2 = Rig(defines, patch_callsite=True)
    img = bytes(random.Random(9).getrandbits(8) for _ in range(30000))
    buf = b'\xA5' * GUARD + img + b'\x5A' * GUARD
    ref, _, _ = rig.run(STOCK, buf, (3, 2, 100, 20), 120, 4)
    # run only the patched bl: start at CALLSITE with LR=STOP semantics -> bl returns to C0561738
    mu = rig2.mu
    mu.mem_write(STOP, struct.pack('<I', 0xEAFFFFFE))
    mu.mem_write(BUF, buf)
    mu.mem_write(RECT, struct.pack('<4i', 3, 2, 100, 20))
    mu.reg_write(A.UC_ARM_REG_SP, STACK - 0x40)
    mu.reg_write(A.UC_ARM_REG_R0, BUF + GUARD)
    mu.reg_write(A.UC_ARM_REG_R1, RECT)
    mu.reg_write(A.UC_ARM_REG_R2, 120)
    mu.emu_start(CALLSITE, CALLSITE + 4, count=50_000_000)
    if bytes(mu.mem_read(BUF, len(buf))) != ref or rig2.ctl(0x0C) != 1:
        fails += 1
        if not quiet:
            print('  FAIL call-site patch')
    return fails, rig


def counts(rig):
    ent = CODE + rig.sym['al_unpremul']
    rnd = random.Random(42)
    out = []
    for label, gen in [('random', lambda: rnd.getrandbits(16)),
                       ('UI-like', lambda: rnd.choice([0, 0, 0, 0xF000 | rnd.getrandbits(12), rnd.getrandbits(16)])),
                       ('all-zero', lambda: 0)]:
        px = [gen() for _ in range(1024 * 4)]
        buf = b'\xA5' * GUARD + struct.pack(f'<{len(px)}H', *px) + b'\x5A' * GUARD
        _, _, n0 = rig.run(STOCK, buf, (0, 0, 1024, 4), 1024, 1, (STOCK, STOCK + 0x1A8))
        _, _, n1 = rig.run(ent, buf, (0, 0, 1024, 4), 1024, 1, (CODE, CODE + len(rig.code)))
        out.append((label, n0 / 4096, n1 / 4096))
    return out


def main():
    if '--mutate' in sys.argv:
        muts = ['MUT_K', 'MUT_MIN', 'MUT_TAIL', 'MUT_ZERO', 'MUT_STRIDE', 'MUT_SAVE']
        caught = 0
        for m in muts:
            f, _ = check((m,), quiet=True)
            print(f'  {m}: {"caught" if f else "NOT CAUGHT"} ({f} failing)')
            caught += bool(f)
        print(f'mutations caught {caught}/{len(muts)}')
        sys.exit(0 if caught == len(muts) else 1)
    fails, rig = check()
    n = len(cases(random.Random(1234))) + 3
    print(f'{n - fails}/{n} pass')
    for label, a, b in counts(rig):
        print(f'  {label:9s} stock {a:6.2f} insn/px   alphalut {b:5.2f} insn/px   x{a / b:.1f}')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
