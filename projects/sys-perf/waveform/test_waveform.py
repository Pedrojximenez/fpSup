"""Bit-exactness: stock waveform method C05A3728 vs waveform.S wf_method,
both run in unicorn on the real firmware image (out/seg0_c0000000.bin).

    python3 -B test_waveform.py            # all cases + instruction counts
    python3 -B test_waveform.py --quick
    python3 -B test_waveform.py --mutate   # every mutation must fail

Stock helpers run for real (C0023030 address map, C001510C memcpy, C04D10D8
NEON fill, C05A34B8 / C05A35A0).  The two calls that reach the display layer
are stubbed to `bx lr` and recorded: C0529D98(ctx, this+8, arg) and
C0529D10(ctx, &pt, colour) with pt read at call time.  Compared per case:
the recorded call sequence, the sample buffer [this+0x30] with guards, r0,
r4-r11/sp, d8-d31, and FPSCR (must equal stock's, both run the same VFP ops).
"""
import os, pathlib, random, struct, sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
SRC = HERE / 'waveform.S'
STOCK = 0xC05A3728
F_SETUP, F_POINT = 0xC0529D98, 0xC0529D10
CODE = 0x46000000
STOP = 0x45F00000
STACK = 0x47000000
OBJ, CTX, IMG = 0x4A000000, 0x4A001000, 0x4A002000
SBUF = 0x4B000000            # sample buffer (V x 330) + guards
FRAME_PHYS = 0x43000000      # C0023030 maps it to 0xC3000000
FRAME_VA = 0xC3000000
FRAME_SZ = 0x800000
GUARD = 64


class Rig:
    def __init__(self, defines=()):
        self.code = assemble(SRC, defines)
        self.sym = symbols(SRC, defines)
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A7)
        mu.mem_map(0xC0000000, 0x02F00000)
        mu.mem_write(0xC0000000, SEG0.read_bytes()[:0x02F00000])
        mu.mem_map(FRAME_VA, FRAME_SZ)
        for base in (CODE, STOP, STACK - 0x100000, OBJ, SBUF):
            mu.mem_map(base & ~0xFFFFF, 0x100000)
        mu.mem_write(CODE, self.code)
        mu.mem_write(STOP, struct.pack('<I', 0xEAFFFFFE))
        for f in (F_SETUP, F_POINT):
            mu.mem_write(f, struct.pack('<I', 0xE12FFF1E))   # bx lr
        mu.reg_write(A.UC_ARM_REG_C1_C0_2, 0x00F00000)
        mu.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        self.calls = []
        self.count = 0
        self.counting = False
        self.stop_at_stock = False
        self.hit_stock = False
        mu.hook_add(UC_HOOK_CODE, self._hook)

    def _hook(self, mu, addr, size, _):
        if self.counting:
            self.count += 1
        if addr == STOCK and self.stop_at_stock:
            self.hit_stock = True
            mu.emu_stop()
            return
        if addr == F_POINT:
            r1 = mu.reg_read(A.UC_ARM_REG_R1)
            x, y = struct.unpack('<ii', mu.mem_read(r1, 8))
            self.calls.append(('pt', mu.reg_read(A.UC_ARM_REG_R0), x, y, mu.reg_read(A.UC_ARM_REG_R2)))
        elif addr == F_SETUP:
            self.calls.append(('setup', mu.reg_read(A.UC_ARM_REG_R0), mu.reg_read(A.UC_ARM_REG_R1),
                               mu.reg_read(A.UC_ARM_REG_R2)))

    def w(self, a, v):
        self.mu.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))

    def r(self, a):
        return struct.unpack('<I', self.mu.mem_read(a, 4))[0]

    def call(self, addr, args, count=False, sp_odd=False):
        mu = self.mu
        for i, v in enumerate(args):
            mu.reg_write(A.UC_ARM_REG_R0 + i, v & 0xFFFFFFFF)
        rnd = random.Random(1234)
        saved = {}
        for reg in range(4, 12):
            saved[reg] = rnd.getrandbits(32)
            mu.reg_write(A.UC_ARM_REG_R4 + reg - 4, saved[reg])
        dregs = {}
        for d in range(32):
            dregs[d] = rnd.getrandbits(64)
            mu.reg_write(A.UC_ARM_REG_D0 + d, dregs[d])
        mu.reg_write(A.UC_ARM_REG_FPSCR, 0)
        sp = STACK - 0x100 - (4 if sp_odd else 0)
        mu.reg_write(A.UC_ARM_REG_SP, sp)
        mu.reg_write(A.UC_ARM_REG_LR, STOP)
        self.calls = []
        self.count = 0
        self.counting = count
        mu.emu_start(addr, STOP, count=200_000_000)
        self.counting = False
        bad = [f'r{reg}' for reg in range(4, 12) if mu.reg_read(A.UC_ARM_REG_R4 + reg - 4) != saved[reg]]
        if mu.reg_read(A.UC_ARM_REG_SP) != sp:
            bad.append('sp')
        bad += [f'd{d}' for d in range(8, 32) if mu.reg_read(A.UC_ARM_REG_D0 + d) != dregs[d]]
        return bad, mu.reg_read(A.UC_ARM_REG_R0), mu.reg_read(A.UC_ARM_REG_FPSCR)


def make_case(rnd, kind=None):
    c = {}
    c['W'] = rnd.choice([330, 330, 330, 1, 2, 100, 331, 500])
    c['H'] = rnd.choice([1, 2, 64, 128, 130, 130, 200, 330])
    c['V'] = rnd.choice([1, 2, 3, 100, 255, 256, 256, 256])  # V=0: stock reads out of bounds
    width = rnd.choice([640, 1024, 1280, 1920])
    c['img'] = dict(stride=width + rnd.choice([0, 0, 64]), x=rnd.randrange(0, 64) * 2,
                    y=rnd.randrange(0, 32), width=width, height=rnd.choice([360, 480, 720, 1080]),
                    addr=FRAME_PHYS)
    c['x0'], c['y0'] = rnd.randrange(0, 700), rnd.randrange(0, 400)
    thr = sorted(rnd.randrange(0, 260) for _ in range(16))
    if rnd.random() < 0.3:
        rnd.shuffle(thr)
    if rnd.random() < 0.2:
        thr = [rnd.getrandbits(32) for _ in range(16)]
    c['thr'] = thr
    c['frame'] = kind or rnd.choice(['random', 'random', 'black', 'white', 'const', 'gradient', 'few'])
    c['seed'] = rnd.getrandbits(32)
    return c


def frame_bytes(c):
    im = c['img']
    n = im['stride'] * 2 * (im['y'] + im['height'] + 2) + 4096
    n = min(n, FRAME_SZ)
    r = random.Random(c['seed'])
    k = c['frame']
    if k == 'random':
        return r.randbytes(n)
    if k == 'black':
        return bytes(n)
    if k == 'white':
        return b'\xff' * n
    if k == 'const':
        return bytes([r.randrange(256)]) * n
    if k == 'few':
        return bytes(r.choice([16, 128, 235]) for _ in range(n))
    return bytes((i // 7) & 0xFF for i in range(n))


def setup(rig, c, fb):
    rig.mu.mem_write(FRAME_VA, fb)
    rig.mu.mem_write(OBJ, bytes(0x100))
    rig.w(OBJ + 0x18, 0x1234)
    rig.w(OBJ + 0x1c, c['x0'])
    rig.w(OBJ + 0x20, c['y0'])
    rig.w(OBJ + 0x24, c['W'])
    rig.w(OBJ + 0x28, c['H'])
    rig.w(OBJ + 0x30, SBUF + GUARD)
    for j, t in enumerate(c['thr']):
        rig.w(OBJ + 0x34 + 4 * j, t)
    rig.w(OBJ + 0x74, c['V'])
    im = c['img']
    for off, k in ((0, 'stride'), (8, 'x'), (0xc, 'y'), (0x10, 'width'), (0x14, 'height'), (0x1c, 'addr')):
        rig.w(IMG + off, im[k])
    n = max(c['V'], 1) * 330 + 2 * GUARD
    rig.mu.mem_write(SBUF, bytes([0xA5]) * n)


def run(rig, c, fb, which, count=False):
    setup(rig, c, fb)
    addr = STOCK if which == 'stock' else CODE + rig.sym['wf_method']
    bad, r0, fpscr = rig.call(addr, [OBJ, CTX, IMG], count=count, sp_odd=c['seed'] & 1)
    n = max(c['V'], 1) * 330 + 2 * GUARD
    return dict(bad=bad, r0=r0, fpscr=fpscr, calls=list(rig.calls),
                sbuf=bytes(rig.mu.mem_read(SBUF, n)), count=rig.count)


def compare(rig, c):
    fb = frame_bytes(c)
    s = run(rig, c, fb, 'stock')
    n = run(rig, c, fb, 'new')
    errs = []
    if n['bad']:
        errs.append(f"clobbered {n['bad']}")
    for k in ('r0', 'fpscr', 'sbuf'):
        if s[k] != n[k]:
            errs.append(k)
    if s['calls'] != n['calls']:
        i = next((i for i, (a, b) in enumerate(zip(s['calls'], n['calls'])) if a != b),
                 min(len(s['calls']), len(n['calls'])))
        errs.append(f"calls differ at {i}: stock {len(s['calls'])} new {len(n['calls'])}"
                    f" {s['calls'][i:i+1]} vs {n['calls'][i:i+1]}")
    return errs, s, n


def cases(n, seed=1):
    rnd = random.Random(seed)
    out = [make_case(rnd) for _ in range(n)]
    # realistic: 330 columns, 256 levels, ~130 rows, ascending thresholds
    for k in ('random', 'gradient', 'black', 'white', 'few'):
        c = make_case(rnd, k)
        c.update(W=330, H=130, V=256, thr=[1, 2, 3, 4, 6, 8, 11, 16, 22, 32, 45, 64, 90, 128, 181, 256])
        out.append(c)
    # img addr 0 (stock returns 0 early)
    c = make_case(rnd)
    c['img']['addr'] = 0
    out.append(c)
    return out


def run_all(rig, cs, stop=False):
    fails = 0
    # same rig, consecutive calls with different thresholds -> stale memo shows
    for i, c in enumerate(cs):
        errs, _, _ = compare(rig, c)
        if errs:
            fails += 1
            if fails <= 5:
                print(f'  case {i} W={c["W"]} H={c["H"]} V={c["V"]} {c["frame"]}: {errs}')
            if stop:
                return fails
    return fails


def main():
    quick = '--quick' in sys.argv
    if '--mutate' in sys.argv:
        muts = ['MUT_HB', 'MUT_LEVEL', 'MUT_Y', 'MUT_TAIL', 'MUT_MEMO', 'MUT_STEP', 'MUT_ODD']
        caught = 0
        for m in muts:
            f = run_all(Rig((m,)), cases(25, seed=7), stop=True)
            print(f'{m}: {"caught" if f else "NOT CAUGHT"}')
            caught += bool(f)
        print(f'mutations caught {caught}/{len(muts)}')
        sys.exit(0 if caught == len(muts) else 1)
    rig = Rig()
    cs = cases(40 if quick else 160)
    fails = run_all(rig, cs)
    # fallback paths: stock itself reads out of bounds there, so only check that
    # wf_method hands over to C05A3728 untouched (registers/args) and counts it
    rnd = random.Random(5)
    for upd, en in ((dict(V=0), 1), (dict(V=257), 1), (dict(V=1000), 1), (dict(H=331), 1), ({}, 0)):
        c = make_case(rnd)
        c.update(upd)
        setup(rig, c, b'')
        rig.w(CODE + rig.sym['wf_ctl'] + 4, en)
        before = rig.r(CODE + rig.sym['wf_ctl'] + 12)
        rig.stop_at_stock = True
        rig.hit_stock = False
        mu = rig.mu
        for i, v in enumerate((OBJ, CTX, IMG)):
            mu.reg_write(A.UC_ARM_REG_R0 + i, v)
        mu.reg_write(A.UC_ARM_REG_SP, STACK - 0x100)
        mu.reg_write(A.UC_ARM_REG_LR, STOP)
        mu.emu_start(CODE + rig.sym['wf_method'], STOP, count=1000)
        rig.stop_at_stock = False
        ok = (rig.hit_stock and [mu.reg_read(A.UC_ARM_REG_R0 + i) for i in range(3)] == [OBJ, CTX, IMG]
              and mu.reg_read(A.UC_ARM_REG_SP) == STACK - 0x100 and mu.reg_read(A.UC_ARM_REG_LR) == STOP
              and rig.r(CODE + rig.sym['wf_ctl'] + 12) == before + (1 if en else 0))
        print(f'fallback {upd or "enable=0"}: {"ok" if ok else "FAIL"}')
        fails += not ok
        rig.w(CODE + rig.sym['wf_ctl'] + 4, 1)
    print(f'{len(cs)} cases, {fails} failures')
    # fallback counters
    print('ctl calls/fallbacks', rig.r(CODE + rig.sym['wf_ctl'] + 8), rig.r(CODE + rig.sym['wf_ctl'] + 12))
    # instruction counts on the realistic case
    rnd = random.Random(99)
    c = make_case(rnd, 'random')
    c.update(W=330, H=130, V=256, thr=[1, 2, 3, 4, 6, 8, 11, 16, 22, 32, 45, 64, 90, 128, 181, 256])
    fb = frame_bytes(c)
    s = run(rig, c, fb, 'stock', count=True)
    n = run(rig, c, fb, 'new', count=True)
    print(f"instructions (W=330 H=130 V=256, random frame, {len([x for x in s['calls'] if x[0]=='pt'])} points):"
          f" stock {s['count']:,}  new {n['count']:,}  x{s['count']/n['count']:.2f}")
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
