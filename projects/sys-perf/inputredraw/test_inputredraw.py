"""Unicorn tests for inputredraw (real firmware image).

Runs for real: UicContentsIfBase::v1 C06D13A0 with the site C06D1418 patched
to our veneer (plus C055DB10 / C055DB98 / C055DFD0 / C06D14D8 that it calls),
our hook, and the CYC_DRAW handler body C05276F0.
Stubbed (recorded): GUI queue C055E0F0 / C055E1E8, DrawMgr C05278F8, pending
C0527F30, ReqForceDraw C0527E68, sysstat C00178D8, logs, the CYC_DRAW
helpers (guards C0013090/C00131E4, tick C0527E28, locks C001CCE0/C001CD18,
slot query C0528120, mark dirty C0527E08, wake-if-dirty C0527E40).

    python3 -B test_inputredraw.py            # tests
    python3 -B test_inputredraw.py --mutate   # every mutant must fail
"""
import pathlib, re, struct, sys, tempfile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
SEG1 = ROOT / 'out' / 'seg1_c2ef6e00.bin'
SRC = HERE / 'inputredraw.S'
SITE, ENQ = 0xC06D1418, 0xC055E1E8
CODE = 0xC5000000
VEN = 0xC072E200
OBJ = 0xC5100000          # fake GUI object
VT = 0xC5100100           # its vtable
KEYLIST = 0xC5100400
SYS = 0xC5100800          # fake sysstat object
MGR = 0xC5100A00
QUEUE = 0xC5100C00
STOP = 0xC5FFF000
STUB = 0xC5F00000         # stub targets for our fake vtable
CUR_MS, CYC = 0xC301EAE4, 0xC3782F98


def bl(at, to):
    return 0xEB000000 | (((to - (at + 8)) >> 2) & 0xFFFFFF)


class Rig:
    def __init__(self, src=SRC, patched=True):
        code = assemble(src); sym = symbols(src)
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A7)
        mu.mem_map(0xC0000000, 0x04000000)
        mu.mem_write(0xC0000000, SEG0.read_bytes())
        mu.mem_write(0xC2EF6E00, SEG1.read_bytes())
        mu.mem_map(0xC5000000, 0x01000000)
        mu.mem_write(CODE, code)
        self.base = CODE + sym['ir_base']
        self.events = []
        self.pending = 0
        self.recording = 0
        self.inlist = False
        self.sp_bad = []
        if patched:
            assert self.r(SITE) == bl(SITE, ENQ)
            self.w(VEN, 0xE51FF004); self.w(VEN + 4, CODE + sym['ir_enq_hook'])
            self.w(SITE, bl(SITE, VEN))
        # fake object: vt+0x4C -> 1, vt+0x64 -> char-key list, vt+0x68 -> force-key list
        self.w(OBJ, VT)
        self.w(VT + 0x4C, STUB + 0x00); self.w(VT + 0x64, STUB + 0x10); self.w(VT + 0x68, STUB + 0x20)
        self.w(KEYLIST, 0x27)
        self.w(KEYLIST + 0x40, 0xB); self.w(KEYLIST + 0x44, 0x27)   # list holding key 0xB
        self.w(CYC + 8, 3); self.w(CYC + 0xC, 3); self.w(CYC, 0); self.w(CYC + 4, 0)
        self.stubs = {
            STUB + 0x00: lambda: 1,
            STUB + 0x10: lambda: 0xC0D0CDE8,                          # stock base char-key list
            STUB + 0x20: lambda: KEYLIST + (0x40 if self.inlist else 0),
            0xC055E0F0: lambda: QUEUE,
            ENQ: self._enq,
            0xC05278F8: lambda: MGR,
            0xC0527F30: lambda: self.pending,
            0xC0527E68: self._req,
            0xC00178D8: self._sys,
            0xC0019DC0: lambda: 0, 0xC001A288: lambda: 0, 0xC001A048: lambda: 0,
            0xC0013090: lambda: 0, 0xC00131E4: lambda: 0,
            0xC0527E28: lambda: self.ev('tick'),
            0xC001CCE0: lambda: 0, 0xC001CD18: lambda: 0,
            0xC0528120: lambda: 1,
            0xC0527E08: lambda: self.ev('dirty'),
            0xC0527E40: lambda: self.ev('wake'),
        }
        mu.hook_add(UC_HOOK_CODE, self._code)

    def r(self, a): return struct.unpack('<I', self.mu.mem_read(a, 4))[0]
    def w(self, a, v): self.mu.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))
    def ctl(self, off): return self.r(self.base + off)
    def setctl(self, off, v): self.w(self.base + off, v)

    def ev(self, name, extra=None):
        self.events.append((name, extra)); return 0

    def _enq(self):
        return self.ev('enq', (self.mu.reg_read(A.UC_ARM_REG_R0), self.mu.reg_read(A.UC_ARM_REG_R1)))

    def _req(self):
        r1 = self.mu.reg_read(A.UC_ARM_REG_R1)
        self.pending = 1
        return self.ev('req', (self.mu.reg_read(A.UC_ARM_REG_R0), bytes(self.mu.mem_read(r1, 12))))

    def _sys(self):
        self.mu.mem_write(SYS + 0x9C, bytes([self.recording])); return SYS

    def _code(self, mu, addr, size, user):
        f = self.stubs.get(addr)
        if f is None:
            return
        if addr < CODE and mu.reg_read(A.UC_ARM_REG_SP) & 7 and addr not in (STUB, STUB + 0x10, STUB + 0x20):
            self.sp_bad.append(hex(addr))
        mu.reg_write(A.UC_ARM_REG_R0, f() & 0xFFFFFFFF)
        mu.reg_write(A.UC_ARM_REG_PC, mu.reg_read(A.UC_ARM_REG_LR))

    def call(self, fn, args=(), sp_mod=0):
        mu = self.mu
        for i, v in enumerate(args):
            mu.reg_write(A.UC_ARM_REG_R0 + i, v)
        for i, v in enumerate(range(4, 12)):
            mu.reg_write(getattr(A, f'UC_ARM_REG_R{v}'), 0x1000 + v)
        sp = 0xC5800000 - sp_mod
        mu.reg_write(A.UC_ARM_REG_SP, sp)
        mu.reg_write(A.UC_ARM_REG_LR, STOP)
        mu.emu_start(fn, STOP, count=200000)
        saved = [mu.reg_read(getattr(A, f'UC_ARM_REG_R{v}')) for v in range(4, 12)]
        assert saved == [0x1000 + v for v in range(4, 12)], 'callee-saved clobbered'
        assert mu.reg_read(A.UC_ARM_REG_SP) == sp, 'sp not restored'
        return mu.reg_read(A.UC_ARM_REG_R0)

    def key(self, code=0xB, on=1, now=None, sp_mod=0):
        if now is not None:
            self.w(CUR_MS, now)
        return self.call(0xC06D13A0, (OBJ, code, on), sp_mod)

    def names(self): return [e[0] for e in self.events]


REQ = bytes([1, 1, 0, 0]) + b'\xff' * 4 + b'\0' * 4


def t_site_and_order(src):
    g = Rig(src)
    g.key(on=1, now=1000)
    n = g.names()
    assert n[:2] == ['enq', 'req'], n
    assert g.events[1][1] == (MGR, REQ), g.events[1]
    assert g.events[0][1][0] == QUEUE
    assert g.ctl(0x18) == 1 and g.ctl(0x28) == 1000


def t_key_up_also(src):
    g = Rig(src)
    g.key(on=0, now=500)
    assert g.names() == ['enq', 'req'], g.names()


def t_disabled(src):
    g = Rig(src); g.setctl(0x08, 0)
    g.key(now=1000)
    assert g.names() == ['enq'], g.names()
    assert g.r(CYC) == 0 and g.r(CYC + 4) == 0


def t_unpatched_is_stock(src):
    g = Rig(src, patched=False)
    g.key(now=1000)
    assert g.names() == ['enq'], g.names()


def t_recording(src):
    g = Rig(src); g.recording = 1
    g.key(now=1000)
    assert g.names() == ['enq'] and g.ctl(0x20) == 1, (g.names(), g.ctl(0x20))
    g.setctl(0x0C, 1)
    g.key(now=2000)
    assert g.names()[-1] == 'req', g.names()


def t_pending(src):
    g = Rig(src); g.pending = 1
    g.key(now=1000)
    assert g.names() == ['enq'] and g.ctl(0x24) == 1


def t_stock_list_dedup(src):
    # key in the class's force list: we kick first, stock sees pending and skips
    g = Rig(src); g.inlist = True
    g.key(on=1, now=1000)
    assert g.names().count('req') == 1, g.names()
    # stock alone (unpatched) does its own request on key-down
    s = Rig(src, patched=False); s.inlist = True
    s.key(on=1, now=1000)
    assert s.names() == ['enq', 'req'], s.names()


def t_min_interval_preload(src):
    g = Rig(src)
    g.key(now=1000); g.pending = 0          # round drawn
    g.key(now=1010)                          # 10 ms later: too soon
    assert g.names().count('req') == 1, g.names()
    assert g.ctl(0x1C) == 1
    assert g.r(CYC) == 2 and g.r(CYC + 4) == 2, (g.r(CYC), g.r(CYC + 4))
    # the real CYC_DRAW handler fires both paths on its very next tick
    g.events.clear()
    g.call(0xC05276F0)
    assert g.names() == ['tick', 'dirty', 'dirty', 'dirty', 'dirty', 'wake'], g.names()
    g.key(now=1016); g.pending = 0
    assert g.names().count('req') == 1
    g.key(now=1032)
    assert g.names().count('req') == 2


def t_preload_never_lowers(src):
    g = Rig(src)
    g.w(CYC, 2); g.w(CYC + 4, 1)
    g.setctl(0x28, 1000)
    g.key(now=1005)
    assert g.r(CYC) == 2 and g.r(CYC + 4) == 2


def t_stock_cyc_does_not_fire_early(src):
    g = Rig(src)
    g.call(0xC05276F0)
    assert g.names() == [], g.names()
    g.call(0xC05276F0); g.call(0xC05276F0)
    assert 'wake' in g.names() and 'tick' in g.names()


def t_stack_alignment(src):
    g = Rig(src)
    g.key(now=1000, sp_mod=4)
    assert g.names()[:2] == ['enq', 'req']
    assert not g.sp_bad, g.sp_bad


def latency(src, patched):
    """16 ms CYC_DRAW ticks, keys at 1 ms steps over 3 periods; latency = key -> first draw request/wake."""
    g = Rig(src, patched=patched)
    res = []
    for k in range(0, 48):
        g.events.clear(); g.pending = 0
        g.w(CYC, 0); g.w(CYC + 4, 0); g.setctl(0x28, 0)
        # boundary phase: ticks at 16*n; dirty fires every 3rd tick, at 48 ms multiples
        t, phase = 10000 + k, k % 48
        g.w(CUR_MS, t)
        g.w(CYC, (phase // 16) % 3); g.w(CYC + 4, (phase // 16) % 3)
        g.key(now=t)
        if 'req' in g.names():
            res.append(0); continue
        nxt = (t // 16 + 1) * 16
        for i in range(4):
            g.call(0xC05276F0)
            if 'wake' in g.names():
                res.append(nxt + 16 * i - t); break
    return max(res), sum(res) / len(res)


def dirtyclean_forced_rounds():
    """Forced rounds (all 4 slots dirty, C0528550 = 0xF) back to back through dirtyclean's own rig."""
    sys.path.insert(0, str(HERE.parent / 'dirtyclean'))
    import test_dirtyclean as dc
    g = dc.Rig(dc.SRC)
    for s in range(2):                                      # UIC draws in 1-2 slots on the camera
        g.set_drawers(s, ['uic'])
    g.w(g.ctl + 0x0C, 0xF)                                  # installer seed, as 70PERF does
    for i in range(12):
        acts = {s: {'uic': (10 + 7 * i, 600, 58, 47)} for s in range(2) if (i + s) % 2 == 0}
        g.round(0xF, acts, {i % 2: 2} if i % 5 == 0 else None)
    assert not g.violations, g.violations[:3]
    return g.r(g.ctl + 0x14), g.r(g.ctl + 0x18)


def main():
    tests = [t_site_and_order, t_key_up_also, t_disabled, t_unpatched_is_stock, t_recording, t_pending,
             t_stock_list_dedup, t_min_interval_preload, t_preload_never_lowers, t_stock_cyc_does_not_fire_early,
             t_stack_alignment]
    if '--mutate' in sys.argv:
        return mutate(tests)
    bad = 0
    for t in tests:
        try:
            t(SRC); print('ok  ', t.__name__)
        except AssertionError as e:
            bad += 1; print('FAIL', t.__name__, e)
    s = latency(SRC, False); p = latency(SRC, True)
    print('dirtyclean, 12 forced rounds (fast, fallback):', dirtyclean_forced_rounds())
    print(f'key -> draw request, ms (worst, mean): stock {s[0]}, {s[1]:.1f}   patched {p[0]}, {p[1]:.1f}')
    assert s[0] >= 40 and p[0] == 0
    print('all passed' if not bad else f'{bad} failed')
    return bad


MUTANTS = [
    ('enqueue after kick', r'        ldr     ip, =FW_ENQ\n        blx     ip\n', '        nop\n', 'b ir_end\n'),
    ('no enable check', r'        ldr     r0, \[r4, #0x08\]\n        cmp     r0, #0\n        beq     9f\n', '', None),
    ('no recording check', r'        ldrb    r0, \[r0, #0x18 \+ 0x84\]', '        mov     r0, #0', None),
    ('rec_ok ignored', r'        ldr     r0, \[r4, #0x0C\]\n        cmp     r0, #0\n        bne     1f\n', '', None),
    ('no pending check', r'        cmp     r0, #0\n        beq     2f\n', '        b       2f\n', None),
    ('min interval reversed', r'        blo     3f', '        bhs     3f', None),
    ('no min interval', r'        blo     3f\n', '', None),
    ('last not stored', r'        str     r6, \[r4, #0x28\]\n', '', None),
    ('preload to divisor-2', r'        ldr     r1, \[r0, #0x08\]\n        sub     r1, r1, #1',
     '        ldr     r1, [r0, #0x08]\n        sub     r1, r1, #2', None),
    ('preload req counter missing', r'        strlo   r1, \[r0, #0x04\]', '        nop', None),
    ('no stack realign', r'        bic     sp, sp, #7[^\n]*\n', '', None),
    ('wrong request (b0=0)', r'        \.byte   1, 1, 0, 0', '        .byte   0, 1, 0, 0', None),
]


def mutate(tests):
    src = SRC.read_text(); caught = 0
    for name, pat, rep, _ in MUTANTS:
        if name == 'enqueue after kick':
            m = src.replace('        ldr     ip, =FW_ENQ\n        blx     ip                              @ r0, r1 as the caller gave them\n', '', 1)
            m = m.replace('9:\n        mov     sp, r7', '9:\n        ldr     ip, =FW_ENQ\n        blx     ip\n        mov     sp, r7', 1)
        else:
            m, n = re.subn(pat, rep, src, count=1)
            assert n == 1, name
        assert m != src, name
        with tempfile.NamedTemporaryFile('w', suffix='.S', dir=HERE, delete=False) as f:
            f.write(m); p = pathlib.Path(f.name)
        try:
            failed = False
            for t in tests:
                try:
                    t(p)
                except Exception:
                    failed = True; break
            if not failed:
                try:
                    assert latency(p, True)[0] == 0
                except Exception:
                    failed = True
        finally:
            p.unlink()
        caught += failed
        print('caught ' if failed else 'MISSED ', name)
    print(f'{caught}/{len(MUTANTS)} mutants caught')
    return len(MUTANTS) - caught


if __name__ == '__main__':
    sys.exit(main())
