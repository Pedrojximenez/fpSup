#!/usr/bin/env python3
"""pcsample.py's install/start/read/uninstall against an emulated camera.

The fake camera is test_pcsample.Rig: the real image under unicorn.  `call`
runs firmware routines for real (C0016210 timer_start, C00163F8 timer_stop,
the cache routines); only the allocator is Python.  `wait` is time passing:
channel 0 fires every ms and any channel the firmware has started fires at
the count C0016210 programmed (ctrl >> 8), each as a full IRQ through
C00014A0 with all of take_irq's register checks.  `mem set` drops one write in
five, as the real shell does.

    python3 -B test_host.py
    python3 -B test_host.py --mutate     # host-side mutations must fail
"""
import json, pathlib, random, struct, sys, tempfile
from unicorn import arm_const as A

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_pcsample as T  # noqa: E402
import pcsample as P  # noqa: E402

SENTINEL = 0xC0FFFFF0
TASK_X = [0xC0100000, 0xC0200040, 0xC0300080, 0xC000E970]


class FakeCam:
    def __init__(self, drop=0.2, seed=1):
        self.g = T.Rig(T.HERE / 'pcsample.S', mode=None)
        self.rnd = random.Random(seed)
        self.drop = drop
        self.claims = {}
        self.next_claim = 0xC072E400
        self.heap = T.RING
        self.allocs = {}
        self.acc = {}
        self.sh_log = []
        self.x = 0
        self.calls = []
        self.events = []

    # -- the Camera interface
    def get(self, addr, n=1):
        return [self.g.r(addr + 4 * i) for i in range(n)]

    def set(self, addr, value, tries=8):
        for _ in range(tries):
            if self.rnd.random() >= self.drop:
                self.g.w(addr, value)
            if self.g.r(addr) == value:
                return
        raise SystemExit('drop')

    def put(self, addr, blob, label):
        self.events.append(('put', label))
        self.g.mu.mem_write(addr, bytes(blob))

    def claim(self, name, size):
        if name not in self.claims:
            self.claims[name] = self.next_claim
            self.next_claim += (size + 63) & ~63
        return self.claims[name]

    def boot_id(self):
        return 12345

    def sh(self, line):
        self.sh_log.append(line)
        if line == 'status get is_recording':
            return 'is_recording -> 0\n'
        return ''

    def read(self, addr, n):
        return bytes(self.g.mu.mem_read(addr, n))

    def call(self, fn, r0=0, r1=0, r2=0, r3=0):
        if fn == P.ALLOC_REQ:
            self.allocs[r0] = ('req', r2)
            return True, 0
        if fn == P.ALLOC_GET:
            kind, size = self.allocs[r0]
            self.allocs[r0] = ('got', size)
            return True, self.heap
        if fn == P.ALLOC_FREE:
            assert self.allocs.pop(r0)[0] == 'got', 'freed twice'
            return True, 0
        self.calls.append(fn)
        if fn in (P.DCACHE_ALL, P.ICACHE_ALL):   # no cache in the emulator; order is checked
            self.events.append(('cache', fn))
            return True, 0
        mu = self.g.mu
        mu.reg_write(A.UC_ARM_REG_CPSR, 0x13)
        mu.reg_write(A.UC_ARM_REG_SP, 0xC4FF7000)
        for i, v in enumerate((r0, r1, r2, r3)):
            mu.reg_write(getattr(A, f'UC_ARM_REG_R{i}'), v)
        mu.reg_write(A.UC_ARM_REG_LR, SENTINEL)
        mu.emu_start(fn, SENTINEL, count=200000)
        assert mu.reg_read(A.UC_ARM_REG_PC) == SENTINEL, f'call {fn:#x} did not return'
        return True, mu.reg_read(A.UC_ARM_REG_R0)

    def wait(self, seconds):
        g = self.g
        regs = g.r(0xC30337F0)
        for _ in range(int(seconds * 1000)):
            pend = 0
            for ch in range(8):
                ctrl, run = g.r(regs + ch * 16), g.r(regs + ch * 16 + 8)
                if ch == 0:
                    pend |= 1
                elif run:
                    period = ctrl >> 8
                    self.acc[ch] = self.acc.get(ch, 0) + 12000
                    if self.acc[ch] >= period:
                        self.acc[ch] -= period
                        pend |= 1 << ch
            if not pend:
                continue
            g.pend = pend
            self.x = (self.x + 1) % len(TASK_X)
            g.take_irq(TASK_X[self.x])

    def ring(self):
        return self.g


def run_flow(via, ch=3, drop=0.2):
    cam = FakeCam(drop=drop)
    with tempfile.TemporaryDirectory() as tmp:
        P.STATE = pathlib.Path(tmp) / 'state.json'
        P.CAPS = pathlib.Path(tmp) / 'captures'
        P.main(['install', '--via', via, '--ch', str(ch), '--records', '256'], cam)
        st = json.loads(P.STATE.read_text())
        assert st['stage'] == 'armed'
        ev = cam.events
        i = ev.index(('put', 'pcsample'))
        assert ev[i + 1:i + 3] == [('cache', P.DCACHE_ALL), ('cache', P.ICACHE_ALL)], \
            f'code must be cleaned to memory and the I-cache dropped before arming: {ev}'
        if via == 'A':
            assert cam.get(P.TMR_HANDLERS)[0] == st['entry']
        else:
            assert cam.get(P.TMR_HANDLERS + ch * 4)[0] == st['entry']
            assert cam.get(P.TMR_HANDLERS)[0] == P.TICK, 'B must leave the OS tick alone'
        P.main(['start'], cam)
        cam.wait(0.1)
        P.main(['stop'], cam)
        c = P.ctl(cam, st)
        assert 50 <= c['idx'] <= 120, c
        P.main(['read', 'x'], cam)
        meta = json.loads((P.CAPS / 'x.json').read_text())
        raw = (P.CAPS / 'x.ring').read_bytes()
        pcs = {struct.unpack_from('<I', raw, 16 * i)[0] for i in range(c['idx'])}
        assert pcs <= set(TASK_X) and len(pcs) > 1, [hex(p) for p in pcs]
        assert meta['ctl']['idx'] == c['idx']
        import analyze
        meta2, recs = analyze.load(P.CAPS / 'x')
        assert len(recs) == c['idx']
        sym = analyze.Symbolizer()
        labels = {sym.label(r[0]) for r in recs}
        assert 'dcache_clean_inv_all(L1+L2,irq off)' in labels, labels
        assert all(r[2] >> 8 == T.TID for r in recs)
        t0 = cam.get(P.CURTIME)[0]
        P.main(['uninstall'], cam)
        if via == 'A':
            assert cam.get(P.TMR_HANDLERS)[0] == P.TICK
        else:
            assert cam.get(P.TMR_HANDLERS + ch * 4)[0] == 0
            regs = cam.get(P.TMR_REGS_P)[0]
            assert cam.get(regs + ch * 16 + 8)[0] == 0, 'channel still running'
        assert not cam.allocs, 'ring not freed'
        assert not P.STATE.exists()
        calls = cam.get(st['ctl'] + P.C['calls'])[0]
        cam.wait(0.05)
        assert cam.get(st['ctl'] + P.C['calls'])[0] == calls, 'still called after uninstall'
        assert cam.get(P.CURTIME)[0] > t0, 'OS clock stopped'
    return True


def case_A():
    run_flow('A')


def case_B():
    run_flow('B', ch=3)


def case_B_busy_channel_refused():
    cam = FakeCam(drop=0)
    with tempfile.TemporaryDirectory() as tmp:
        P.STATE = pathlib.Path(tmp) / 'state.json'
        cam.g.w(P.TMR_HANDLERS + 4 * 4, 0xC0123456)
        try:
            P.main(['install', '--via', 'B', '--ch', '4'], cam)
        except SystemExit as e:
            assert 'in use' in str(e), e
            assert not cam.allocs and not P.STATE.exists()
            return
        raise AssertionError('busy channel accepted')


def case_refuse_while_recording():
    cam = FakeCam(drop=0)
    cam.sh = lambda line: 'is_recording -> 1\n'
    with tempfile.TemporaryDirectory() as tmp:
        P.STATE = pathlib.Path(tmp) / 'state.json'
        try:
            P.main(['install', '--via', 'A'], cam)
        except SystemExit as e:
            assert 'recording' in str(e)
            assert cam.get(P.TMR_HANDLERS)[0] == P.TICK
            return
        raise AssertionError('installed while recording')


def case_A_interrupted_install_is_undone():
    """The link dies right after the hook word lands: uninstall must still unhook."""
    cam = FakeCam(drop=0)
    real_set = cam.set

    def dying_set(addr, value, tries=8):
        real_set(addr, value, tries)
        if addr == P.TMR_HANDLERS and value != P.TICK:
            raise SystemExit('link lost')
    cam.set = dying_set
    with tempfile.TemporaryDirectory() as tmp:
        P.STATE = pathlib.Path(tmp) / 'state.json'
        try:
            P.main(['install', '--via', 'A'], cam)
        except SystemExit:
            pass
        assert cam.get(P.TMR_HANDLERS)[0] != P.TICK, 'precondition: hook landed'
        cam.set = real_set
        P.main(['uninstall'], cam)
        assert cam.get(P.TMR_HANDLERS)[0] == P.TICK and not cam.allocs


CASES = [case_A, case_B, case_B_busy_channel_refused, case_refuse_while_recording,
         case_A_interrupted_install_is_undone]


def run(quiet=False):
    bad = []
    for f in CASES:
        try:
            f()
            quiet or print(f'  ok   {f.__name__}')
        except (AssertionError, SystemExit, Exception) as e:
            bad.append(f.__name__)
            quiet or print(f'  FAIL {f.__name__}: {type(e).__name__} {e}')
    return bad


HOST_MUTATIONS = [
    ('A writes nothing', "        cam.set(TMR_HANDLERS, st['entry'])\n", "        pass\n"),
    ('uninstall leaves A hooked', "            cam.set(TMR_HANDLERS, TICK)\n", "            pass\n"),
    ('uninstall does not stop B', "            ok, ret = cam.call(TIMER_STOP, st['ch'])\n",
     "            ok, ret = True, 0\n"),
    ('ring never freed', "        cam.call(ALLOC_FREE, st['desc'], 2)\n    STATE.unlink()",
     "        pass\n    STATE.unlink()"),
    ('B handler not passed', "struct.pack('<IIII', a.period, st['entry'], 0x37, 0)",
     "struct.pack('<IIII', a.period, 0, 0x37, 0)"),
    ('orig not set for A', "('orig', TICK if a.via == 'A' else 0)", "('orig', 0)"),
    ('no I-cache drop', "    cam.call(ICACHE_ALL)\n", "    pass\n"),
    ('arming not recorded', "    st['stage'] = 'arming'", "    st['stage'] = 'claimed'"),
    ('start never enables', "    cam.set(base + C['en'], 1)\n", "    pass\n"),
    ('no recording guard', "    if recording(cam):\n        raise", "    if False:\n        raise"),
    ('busy check skipped', "        if any(busy):\n", "        if False:\n"),
    ('mem set not verified', "            if self.pf.mem_get(addr)[0] == value:", None),
]


def mutate():
    src = (HERE / 'pcsample.py').read_text()
    survived = []
    import importlib
    for name, old, new in HOST_MUTATIONS:
        if new is None:
            continue          # only the live Camera class; FakeCam has its own
        assert src.count(old) == 1, f'{name}: anchor x{src.count(old)}'
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / 'pcsample.py'
            p.write_text(src.replace(old, new))
            spec = importlib.util.spec_from_file_location('pcsample', p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            m.SRC = HERE / 'pcsample.S'
            global P
            keep, P = P, m
            try:
                bad = run(quiet=True)
            finally:
                P = keep
        print(f'  {"caught " if bad else "SURVIVED"} {name:30s} {bad}')
        if not bad:
            survived.append(name)
    return survived


if __name__ == '__main__':
    import importlib.util  # noqa: F401
    if '--mutate' in sys.argv:
        s = mutate()
        print('mutations survived:', s or 'none')
        sys.exit(1 if s else 0)
    bad = run()
    print('all passed' if not bad else f'{len(bad)} failed')
    sys.exit(1 if bad else 0)
