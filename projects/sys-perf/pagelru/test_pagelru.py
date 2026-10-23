"""unicorn test for pagelru.

    python3 -B test_pagelru.py            # scenarios
    python3 -B test_pagelru.py --mutate   # every mutation must be caught

Real image (seg0) at C0000000 with the two real Thumb sites rewritten to the
real BLX encodings (build.thumb_blx) -> real veneers -> pagelru body.  Each
screen switch executes the firmware's own site instructions in Thumb state:
C05DD5CA (load next) and C05DD670 (unload old), stopping at the following
instruction, exactly as C05DD540.. does.

The stock C05D90F0 / C05D91A0 / C00178D8 are replaced by a Python model of
what their disassembly does to layout objects (README §2):
  load:   tree==0 -> parse (new tree, refcount 1, init) ; else refcount+1 (reuse)
  unload: tree!=0 -> refcount==1 -> teardown + free, tree=0 ; else refcount-1
The full UI parse cannot run outside the camera; screen pixels are NOT
compared here — the invariants are on the layout objects the screen manager
sees.
"""
import struct, sys, random, pathlib
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402

B = 0xC0000000
SEG0 = build.SEG0.read_bytes()
BODY = 0x45000000
VEN = 0xC072E400                     # inside the cave arena: BLX range check is real
STACK = 0x46000000
OBJ = 0x47000000
SYS = 0x48000000
FW_LOAD, FW_UNLOAD, FW_SYS = 0xC05D90F0, 0xC05D91A0, 0xC00178D8
SITE_LOAD, SITE_UNLOAD = 0xC05DD5CA, 0xC05DD670
QS_NAMES = ['QS_CINE', 'QS_STILL', 'QS_STILLlike']


class Model:
    def __init__(self):
        self.next_tree = OBJ + 0x100000
        self.parses = 0
        self.frees = 0
        self.events = []
        self.fail = set()
        self.rec = 0


class Cam:
    def __init__(self, patched=True, defines=(), cap=2, enable=1):
        self.m = Model()
        self.patched = patched
        code, self.sym = build.build(defines)
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.mem_map(B, 0x3000000)
        img = bytearray(SEG0)
        if patched:
            for name, at, fw, entry in build.SITES:
                v = VEN + (0 if name == 'load' else 8)
                h1, h2 = build.thumb_blx(at, v)
                struct.pack_into('<HH', img, at - B, h1, h2)
        mu.mem_write(B, bytes(img[:0x3000000]))
        mu.mem_write(VEN, build.veneer(BODY + self.sym['pl_load']) + build.veneer(BODY + self.sym['pl_unload']))
        mu.mem_map(BODY, 0x10000)
        mu.mem_write(BODY, code)
        for base in (STACK, OBJ, SYS):
            mu.mem_map(base, 0x200000)
        self.w32(BODY + 4, enable)
        self.w32(BODY + 8, cap)
        self.layouts = {}
        self.stops = set()
        mu.hook_add(UC_HOOK_CODE, self._hook, begin=B, end=B + 0x3000000)

    def w32(self, a, v):
        self.mu.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))

    def r32(self, a):
        return struct.unpack('<I', self.mu.mem_read(a, 4))[0]

    def ctl(self, off):
        return self.r32(BODY + off)

    def layout(self, name):
        if name not in self.layouts:
            n = len(self.layouts)
            L = OBJ + n * 0x100
            self.mu.mem_write(L + 0x40, name.encode() + b'\0')
            self.w32(L + 8, L + 0x40)
            self.w32(L + 0xC, 0)
            self.layouts[name] = L
        return self.layouts[name]

    def tree(self, L):
        return self.r32(L + 0xC)

    def refs(self, L):
        t = self.tree(L)
        return self.r32(t + 0xC) if t else 0

    # stock functions, modelled
    def _ret(self, uc, r0):
        lr = uc.reg_read(UC_ARM_REG_LR)
        uc.reg_write(UC_ARM_REG_R0, r0)
        uc.reg_write(UC_ARM_REG_PC, lr)          # bit 0 selects Thumb

    def _hook(self, uc, addr, size, _):
        m = self.m
        if addr in self.stops:
            uc.emu_stop()
            return
        if addr == FW_LOAD:
            L = uc.reg_read(UC_ARM_REG_R0)
            name = self.name_of(L)
            if L in m.fail:
                m.events.append(('loadfail', name)); return self._ret(uc, 5)
            t = self.tree(L)
            if t == 0:
                t = m.next_tree; m.next_tree += 0x100
                self.w32(L + 0xC, t); self.w32(t + 0xC, 1)
                m.parses += 1; m.events.append(('parse', name))
            else:
                self.w32(t + 0xC, self.r32(t + 0xC) + 1); m.events.append(('reuse', name))
            return self._ret(uc, 0)
        if addr == FW_UNLOAD:
            L = uc.reg_read(UC_ARM_REG_R0)
            name = self.name_of(L)
            t = self.tree(L)
            sp = uc.reg_read(UC_ARM_REG_SP)
            m.events.append(('sp_aligned', sp % 8 == 0))
            if t:
                r = self.r32(t + 0xC)
                assert r >= 1, f'unload of {name} with refcount {r}'
                if r == 1:
                    self.w32(L + 0xC, 0); m.frees += 1; m.events.append(('free', name))
                else:
                    self.w32(t + 0xC, r - 1); m.events.append(('drop', name))
            else:
                m.events.append(('unload_empty', name))
            return self._ret(uc, 0)
        if addr == FW_SYS:
            self.mu.mem_write(SYS + 0x18 + 0x84, bytes([m.rec]))
            return self._ret(uc, SYS)

    def name_of(self, L):
        for k, v in self.layouts.items():
            if v == L:
                return k
        return hex(L)

    def site(self, at, r0):
        """Execute the firmware's site instruction in Thumb state, stop after it."""
        mu = self.mu
        self.stops = {at + 4}
        mu.reg_write(UC_ARM_REG_SP, STACK + 0x100000 - 4)       # sp = 4 mod 8 on purpose
        mu.reg_write(UC_ARM_REG_R0, r0)
        for r in (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
                  UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11):
            mu.reg_write(r, 0x1111 * (r - UC_ARM_REG_R4 + 1))
        mu.emu_start(at | 1, at + 4, count=200000)
        assert mu.reg_read(UC_ARM_REG_PC) == at + 4, hex(mu.reg_read(UC_ARM_REG_PC))
        assert mu.reg_read(UC_ARM_REG_CPSR) & 0x20, 'did not return to Thumb'
        assert mu.reg_read(UC_ARM_REG_SP) == STACK + 0x100000 - 4, 'sp not restored'
        for r in (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
                  UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11):
            assert mu.reg_read(r) == 0x1111 * (r - UC_ARM_REG_R4 + 1), 'callee-saved clobbered'
        return mu.reg_read(UC_ARM_REG_R0)


class Screen:
    """C05DD540's switch: load next (site 1); on success unload current (site 2)."""
    def __init__(self, cam):
        self.cam, self.cur = cam, None

    def go(self, name):
        cam = self.cam
        L = cam.layout(name)
        if self.cur == L:
            return
        if cam.site(SITE_LOAD, L) != 0:
            return False
        if self.cur:
            cam.site(SITE_UNLOAD, self.cur)
        self.cur = L
        # the screen manager's view: current screen has a live, initialised tree
        assert cam.tree(L) and cam.refs(L) >= 1, f'current {name} has no tree'
        return True


def held(cam):
    n = cam.ctl(12)
    return [cam.ctl(40 + 4 * i) for i in range(n)]


def check_invariants(cam, scr):
    hs = held(cam)
    assert len(hs) <= max(0, min(cam.ctl(8), 4)), 'over capacity'
    assert len(set(hs)) == len(hs), 'duplicate slot'
    for L in hs:
        assert cam.tree(L) and cam.refs(L) == 1 + (L == scr.cur), 'held layout refcount wrong'
        assert not cam.name_of(L).startswith('QS_'), 'QS layout held'
    for name, L in cam.layouts.items():
        if L != scr.cur and L not in hs and not name.startswith('_pin'):
            assert cam.tree(L) == 0, f'{name} leaked a tree'
    if cam.patched:
        assert all(ok for ev, ok in cam.m.events if ev == 'sp_aligned'), 'firmware called with sp not 8-aligned'


def run(seq, **kw):
    cam = Cam(**kw)
    scr = Screen(cam)
    for s in seq:
        scr.go(s)
        check_invariants(cam, scr)
    return cam, scr


def flush(cam, scr):
    """enable=0, then one more screen switch releases everything."""
    cam.w32(BODY + 4, 0)
    scr.go('_end')
    check_invariants(cam, scr)
    assert held(cam) == []


T = []
def test(f):
    T.append(f); return f


@test
def aba_hit():
    cam, scr = run(['LV', 'MENU', 'LV'])
    assert cam.m.parses == 2, cam.m.parses
    assert cam.ctl(16) == 1, 'no hit'
    stock, _ = run(['LV', 'MENU', 'LV'], patched=False)
    assert stock.m.parses == 3


@test
def lru_order_and_evict():
    cam, scr = run(['A', 'B', 'C', 'D', 'B'], cap=2)   # held after D: C,B -> B hit
    assert cam.ctl(16) == 1 and cam.ctl(24) == 1, (cam.ctl(16), cam.ctl(24))
    assert cam.m.parses == 4
    cam, scr = run(['A', 'B', 'C', 'D', 'A'], cap=2)   # A evicted -> parse again
    assert cam.ctl(16) == 0 and cam.m.parses == 5


@test
def qs_never_held():
    cam, scr = run(['LV', 'QS_CINE', 'LV', 'QS_STILL', 'MENU', 'QS_STILLlike', 'LV'])
    for n in QS_NAMES:
        assert cam.layouts[n] not in held(cam)
        assert cam.tree(cam.layouts[n]) == 0, f'{n} kept'
    assert cam.ctl(32) in (6,) or cam.ctl(28) >= 3


@test
def shared_layout_not_held():
    cam = Cam(); scr = Screen(cam)
    P = cam.layout('_pinX')
    cam.site(SITE_LOAD, P)                              # someone else holds a reference
    scr.go('_pinX'); scr.go('LV')
    assert P not in held(cam), 'held a layout with refcount > 1'
    assert cam.refs(P) == 1 and cam.ctl(32) == 5


@test
def recording_flushes():
    cam, scr = run(['A', 'B', 'C'])
    assert len(held(cam)) == 2
    cam.m.rec = 1
    scr.go('D')
    check_invariants(cam, scr)
    assert held(cam) == [] and cam.ctl(32) == 2


@test
def disabled_is_stock():
    seq = ['A', 'B', 'A', 'C', 'B', 'A', 'QS_CINE', 'A']
    cam, _ = run(seq, enable=0)
    stock, _ = run(seq, patched=False)
    strip = lambda ev: [e for e in ev if e[0] != 'sp_aligned']
    assert strip(cam.m.events) == strip(stock.m.events), 'disabled run differs from stock'
    assert cam.m.parses == stock.m.parses and held(cam) == []


@test
def disable_releases_all():
    cam, scr = run(['A', 'B', 'C', 'D'], cap=3)
    assert len(held(cam)) == 3
    flush(cam, scr)


@test
def failed_load_keeps_reference():
    cam, scr = run(['A', 'B'])
    A = cam.layout('A')
    cam.m.fail.add(A)
    assert scr.go('A') is False
    assert A in held(cam) and cam.refs(A) == 1
    cam.m.fail.clear()
    scr.go('A'); check_invariants(cam, scr)
    assert A not in held(cam) and cam.refs(A) == 1


@test
def cap_zero_and_cap_over():
    cam, scr = run(['A', 'B', 'C'], cap=0)
    assert held(cam) == [] and cam.ctl(32) == 8
    cam, scr = run(['A', 'B', 'C', 'D', 'E', 'F', 'G'], cap=9)
    assert len(held(cam)) == 4


@test
def random_walks():
    rnd = random.Random(7)
    names = ['A', 'B', 'C', 'D', 'E', 'QS_CINE', 'QS_STILL']
    for it in range(60):
        seq = [rnd.choice(names) for _ in range(rnd.randint(5, 40))]
        cap = rnd.randint(0, 5)
        cam, scr = run(seq, cap=cap)
        stock, sscr = run(seq, patched=False)
        assert cam.m.parses <= stock.m.parses
        assert scr.cur == cam.layouts[seq[-1]] or seq[-1] == seq[-2]
        flush(cam, scr)
        # after the flush only the current screen has a tree, like stock
        sscr.go('_end')
        live = sorted(n for n, L in cam.layouts.items() if cam.tree(L))
        slive = sorted(n for n, L in stock.layouts.items() if stock.tree(L))
        assert live == slive == ['_end'], (live, slive)


MUTS = ['MUT_NOQS', 'MUT_NOREF', 'MUT_NODROP', 'MUT_LOADORDER', 'MUT_NOEVICT', 'MUT_NOREC', 'MUT_CAPOFF']


def run_all(defines=()):
    global Cam
    fails = []
    orig = Cam.__init__
    def init(self, patched=True, defines_=defines, cap=2, enable=1):
        orig(self, patched, defines_ if patched else (), cap, enable)
    Cam.__init__ = init
    try:
        for t in T:
            try:
                t()
            except Exception as e:  # noqa: BLE001
                fails.append((t.__name__, repr(e)[:100]))
    finally:
        Cam.__init__ = orig
    return fails


if __name__ == '__main__':
    if '--mutate' in sys.argv:
        bad = 0
        for m in MUTS:
            f = run_all((m,))
            print(f'{m:16s} caught by {len(f)} test(s)' + ('' if f else '   <-- NOT CAUGHT'))
            bad += not f
        print('mutations caught', len(MUTS) - bad, '/', len(MUTS))
        sys.exit(1 if bad else 0)
    f = run_all()
    for t in T:
        print(('FAIL ' if any(n == t.__name__ for n, _ in f) else 'ok   ') + t.__name__)
    for n, e in f:
        print(' ', n, e)
    print(len(T) - len(f), '/', len(T))
    sys.exit(1 if f else 0)
