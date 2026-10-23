#!/usr/bin/env python3
"""The whole sup, installed by its own entry, inside the real redraw round.

Runs for real (firmware image): C0528700 (the redraw round), the layer methods
(getBuffer C0721328, commit C0721370, C0721638, C0721110), the clear C0528B40
(-> the layer vtable fill slot = our dispatcher), the whole-layer memcpy
C0528BA0, the stock fill C0721480 -> C0722490, the Fill DMA driver
C00DB188/C00DAFF8, the stock span functions, and every byte of 70PERF.BIN
(entry, dispatcher, gates, dirtyclean, filldma, neonblit, lz4fast stays idle).

Stubbed: locks, the event flag (per-slot dirty bits), trace, the OS
semaphores/IRQ enable, the system status (not recording), the range
invalidate C000EB28 and the whole flush C000E91C (cache model, below), and the
drawers' draw: a UIC drawer draws its rect by calling the ARGB4444 span table 1
entry the firmware would use (so the installed pointer -> gate -> NEON or stock
runs), records the rect in uicMgr like C0561198; an "other" drawer writes bytes
it reports to nobody.  The Fill DMA block is a model of what C00DAFF8 programs.

Cache model (lines of 64 B):  dirty = CPU-written, not cleaned;  cached =
touched by the CPU since its last invalidate;  stale = cached when a DMA wrote
it.  Violations:  a commit with dirty lines in the committed buffer;  a DMA
start over dirty lines (they would later be written back over the DMA data);
a CPU read or write of a stale line.

Each scenario runs once on the stock image (reference) and once per switch
combination; every buffer must match the reference byte for byte.

    python3 -B test_perf_render.py              # all combos
    python3 -B test_perf_render.py --mutate     # perf_core.S mutants must fail
"""
import itertools, os, pathlib, random, re, struct, sys, tempfile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ
from unicorn import arm_const as A

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
sys.path.insert(0, str(HERE))
import build_perf as P                                   # noqa: E402

SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'
SEG1 = ROOT / 'out' / 'seg1_c2ef6e00.bin'

BLOCK = 0xC8000000               # the sup block (file image, header first)
VEN = 0xC072E100                 # cave_alloc result
SVC = 0xC8F00000                 # fake service table + stubs
SVC_FN = {8: 'claim', 12: 'claim_res', 16: 'chain_next', 20: 'cave', 24: 'publish', 28: 'log'}
CTRL = 0xC3400000
LAYER0 = 0xC3410000
BUF0 = 0xC5000000                # 4 slots x 3 buffers x 2 MiB
BUFSTEP = 0x200000
SRCB, DESC, PARAM, LUT = 0xC7000000, 0xC7100000, 0xC7100100, 0xC7100200
THUNK = 0xC7200000
STOP = 0xC7FFF000
UICMGR = 0xC37B7034
UIC_VT, SP_VT, OSD_VT = 0xC0D17780, 0xC2EF6280, 0xC2E38E5C
OTHER_VT, OTHER_DRAW, OTHER_1C = 0xC3480000, 0xC7300000, 0xC7300010
SPAN_TBL = 0xC2EB3F5C
LINE = 64
W, H = 256, 64                   # 32 KiB 16bpp layers: above filldma's 16 KiB threshold
RET0 = {0xC0010298, 0xC00102D0, 0xC036D7E0, 0xC0019DC0, 0xC001A0D8,
        0xC0528E18, 0xC0528650, 0xC0528C28, 0xC05286D0}
# filldma's OS view
FILL_INITED, SEM_MUTEX_P, SEM_DONE_P = 0xC31D25B4, 0xC301FEC4, 0xC301FEC0
WAI_SEM, SIG_SEM, INT_ENA = 0xC01F8E8C, 0xC01F8CDC, 0xC000FCA0
DCIMVAC, FULL_FLUSH, SYSSTAT, STATUS = 0xC000EB28, 0xC000E91C, 0xC00178D8, 0xC7400000
DMA_BASE, CLKGATE = 0x30041000, 0x300022A4
SPAN_BPP = {0: 4, 1: 4, 2: 2, 3: 1}


class Violation(Exception):
    pass


class Rig:
    def __init__(self, blob=None, sym=None, info=None, switches=None):
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A7)
        mu.mem_map(0xC0000000, 0x04000000)
        mu.mem_write(0xC0000000, SEG0.read_bytes())
        mu.mem_write(0xC2EF6E00, SEG1.read_bytes())
        mu.mem_map(BUF0, 0x02000000)
        mu.mem_map(SRCB, 0x01000000)
        mu.mem_map(BLOCK, 0x01000000)
        mu.mem_map(0x30000000, 0x00100000)
        mu.reg_write(A.UC_ARM_REG_C1_C0_2, 0x00F00000)
        mu.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        self.dirty, self.cached, self.stale = set(), set(), set()
        self.violations, self.events = [], []
        self.flushes = self.commits = self.dma_starts = 0
        self.pending = 0
        self.mutex = False
        self.saved_lr = None
        self.slots, self.round_bits = {}, 0
        self.round_no = 0
        self.installed = blob is not None
        self.claims_seen, self.logs = [], []
        self.w(SEM_MUTEX_P, 7); self.w(SEM_DONE_P, 8); self.w(FILL_INITED, 1)
        for s in range(4):
            L = LAYER0 + s * 0x100
            self.w(CTRL + 0x58 + 8 * s, L)
            self.w(L, OSD_VT if s == 1 else SP_VT)
            self.w(L + 4, W); self.w(L + 8, H); self.w(L + 0x1C, 1)
            for i in range(3):
                d = L + 0x80 + 0x10 * i
                self.w(d + 4, BUF0 + (s * 3 + i) * BUFSTEP)
                self.w(d + 8, L + 0xC0)
                self.w(L + 0x3C + 4 * i, d)
            self.w(L + 0xC0, W); self.w(L + 0xC4, H)
            self.w(L + 0x48, L + 0x80); self.w(L + 0x4C, L + 0x90); self.w(L + 0x50, 0)
        self.w(OTHER_VT + 0x0C, OTHER_DRAW); self.w(OTHER_VT + 0x1C, OTHER_1C)
        rnd = random.Random(7)
        mu.mem_write(BUF0, bytes(rnd.getrandbits(8) for _ in range(4096)) * (0x02000000 // 4096))
        mu.mem_write(LUT, bytes(rnd.getrandbits(8) for _ in range(1024)))
        mu.hook_add(UC_HOOK_CODE, self._code)
        mu.hook_add(UC_HOOK_MEM_WRITE, self._wr, begin=BUF0, end=BUF0 + 0x02000000 - 1)
        mu.hook_add(UC_HOOK_MEM_READ, self._rd, begin=BUF0, end=BUF0 + 0x02000000 - 1)
        mu.hook_add(UC_HOOK_MEM_WRITE, self._mmio, begin=DMA_BASE, end=DMA_BASE + 0xFFF)
        self.mcr = set()
        if blob is not None:
            self.install(blob, sym, info, switches)

    # ------------------------------------------------------------ memory
    def w(self, a, v):
        self.mu.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))

    def r(self, a):
        return struct.unpack('<I', self.mu.mem_read(a, 4))[0]

    def lines(self, a, n):
        return range(a // LINE, (a + n - 1) // LINE + 1)

    def _wr(self, mu, acc, addr, size, val, _):
        for ln in self.lines(addr, size):
            if ln in self.stale:
                self.violations.append(('write-to-stale', hex(ln * LINE)))
            self.dirty.add(ln); self.cached.add(ln)

    def _rd(self, mu, acc, addr, size, val, _):
        for ln in self.lines(addr, size):
            if ln in self.stale:
                self.violations.append(('stale-read', hex(ln * LINE)))
            self.cached.add(ln)

    def cpu_write(self, a, data):          # a stubbed drawer's stores
        self._wr(None, 0, a, len(data), 0, None)
        self.mu.mem_write(a, data)

    # ------------------------------------------------------------ install
    def install(self, blob, sym, info, switches):
        mu = self.mu
        mu.mem_write(BLOCK, blob)
        self.body = BLOCK + 32
        for off, name in SVC_FN.items():
            self.w(SVC + off, SVC + 0x100 + off)
        self.w(SVC, 3)
        self.svc_stub = {SVC + 0x100 + off: name for off, name in SVC_FN.items()}
        # DCCMVAC sites anywhere in the block (dirtyclean's clean loop)
        for o in range(0, len(blob), 4):
            v = struct.unpack_from('<I', blob, o)[0]
            if (v & 0x0FFF0FFF) == 0x0E070F3A:
                self.mcr.add(BLOCK + o)
        entry = BLOCK + struct.unpack_from('<I', blob, 16)[0]
        r0 = self.call(entry, BLOCK, SVC, 0)
        if r0 != 0:
            raise Violation(f'entry returned {r0}, pf_state {self.r(self.body + 0x14):#x}')
        if switches is not None:
            self.set_switches(sym, switches)

    def set_switches(self, sym, sw):
        b = self.body
        self.w(b + 0x08, sw.get('master', 1))
        self.w(b + 0x0C, sw.get('nb', 0))
        self.w(b + 0x10, sw.get('lz', 0))
        self.w(b + sym['dc_mod'] + 4, sw.get('dc', 0))
        self.w(b + sym['fd_mod'] + 8, sw.get('fd', 0))
        for k, off in (('ir', 8), ('ic', 4), ('pl', 4), ('al', 8), ('wf', 4)):
            if f'{k}_mod' in sym:
                self.w(b + sym[f'{k}_mod'] + off, sw.get(k, 0))

    # ------------------------------------------------------------ stubs
    def ret(self, val=None):
        if val is not None:
            self.mu.reg_write(A.UC_ARM_REG_R0, val & 0xFFFFFFFF)
        self.mu.reg_write(A.UC_ARM_REG_PC, self.mu.reg_read(A.UC_ARM_REG_LR))

    def _code(self, mu, addr, size, _):
        reg = lambda r: mu.reg_read(r)
        if addr in self.mcr:
            self.dirty.discard(reg(A.UC_ARM_REG_R0) // LINE)
            return
        name = getattr(self, 'svc_stub', {}).get(addr)
        if name:
            return self._svc(name)
        if addr == FULL_FLUSH:
            self.flushes += 1
            self.dirty.clear(); self.cached.clear(); self.stale.clear()
            return self.ret(0)
        if addr == DCIMVAC:
            lo, hi = reg(A.UC_ARM_REG_R0), reg(A.UC_ARM_REG_R1)
            for ln in range(lo // LINE, hi // LINE + 1):
                self.dirty.discard(ln); self.cached.discard(ln); self.stale.discard(ln)
            return self.ret()
        if addr in RET0:
            return self.ret(0)
        if addr == 0xC0528178:
            return self.ret(1)
        if addr == 0xC036D888:
            self.w(reg(A.UC_ARM_REG_R1) + 8, self.round_bits)
            return self.ret(1)
        if addr == WAI_SEM:
            sem = reg(A.UC_ARM_REG_R0)
            if sem == 7:
                assert not self.mutex; self.mutex = True
            elif sem == 8:
                if not self.pending:
                    raise Violation('driver waits for a DMA never started')
                self.pending -= 1
            return self.ret(0)
        if addr == SIG_SEM:
            assert self.mutex; self.mutex = False
            return self.ret(0)
        if addr == INT_ENA:
            return self.ret(0)
        if addr == SYSSTAT:
            self.mu.mem_write(STATUS + 0x18 + 0x84, b'\0')
            return self.ret(STATUS)
        if addr == 0xC06D1948 or addr == OTHER_DRAW:
            return self._draw(addr == 0xC06D1948)
        if addr == THUNK:
            mu.reg_write(A.UC_ARM_REG_R0, 1)
            mu.reg_write(A.UC_ARM_REG_PC, self.saved_lr)
            self.saved_lr = None
            return
        if addr == OTHER_1C:
            return self.ret(0)
        if addr == 0xC0721370:                       # commit
            L = reg(A.UC_ARM_REG_R0)
            base = self.r(self.r(L + 0x4C) + 4)
            bad = [ln for ln in self.lines(base, W * H * 2) if ln in self.dirty]
            if bad:
                self.violations.append(('dirty-at-commit', hex(base), len(bad)))
            self.commits += 1

    def _svc(self, name):
        reg = lambda r: self.mu.reg_read(r)
        if name == 'claim':
            a, n, stock = reg(A.UC_ARM_REG_R1), reg(A.UC_ARM_REG_R2), reg(A.UC_ARM_REG_R3)
            kind = self.r(reg(A.UC_ARM_REG_SP))
            want = bytes(self.mu.mem_read(stock, n))
            if bytes(self.mu.mem_read(a, n)) != want:
                raise Violation(f'claim {a:#x}: memory is not the declared stock')
            self.claims_seen.append((a, n, kind))
            return self.ret(0)
        if name == 'cave':
            return self.ret(VEN)
        if name == 'publish':
            return self.ret(0)
        if name == 'log':
            p, s = reg(A.UC_ARM_REG_R1), b''
            while True:
                c = bytes(self.mu.mem_read(p + len(s), 1))
                if c == b'\0':
                    break
                s += c
            self.logs.append(s.decode())
            return self.ret(0)
        raise Violation(f'unexpected service {name}')

    def _mmio(self, mu, acc, addr, size, val, _):
        if addr != DMA_BASE or not val & 1:
            return
        rg = {o: self.r(DMA_BASE + o) for o in (0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28)}
        if not self.r(CLKGATE) & 0x100 or rg[0x28] & 3:
            raise Violation('DMA programmed wrong')
        va = 0xC0000000 + rg[0x10] * 4
        width, rows, stride = rg[0x18], rg[0x1C], rg[0x14]
        pat = struct.pack('<I', rg[0x20]) * width
        for r in range(rows):
            a = va + r * stride * 4
            for ln in self.lines(a, width * 4):
                if ln in self.dirty:
                    self.violations.append(('dirty-under-dma', hex(ln * LINE)))
                if ln in self.cached:
                    self.stale.add(ln)
            mu.mem_write(a, pat)
        self.pending += 1
        self.dma_starts += 1

    # ------------------------------------------------------------ drawers
    def back(self, s):
        return self.r(self.r(LAYER0 + s * 0x100 + 0x4C) + 4)

    def slot_of(self, base):
        return next(s for s in range(4) if self.back(s) == base)

    def uic_record(self, base, rect):
        recs = UICMGR + 0x18
        for i in range(10):
            if self.r(recs + 0x20 * i + 4) in (0, base):
                self.w(recs + 0x20 * i + 4, base)
                for k, v in enumerate(rect):
                    self.w(recs + 0x20 * i + 8 + 4 * k, v)
                return
        raise Violation('records full')

    def _draw(self, uic):
        mu = self.mu
        base = self.r(mu.reg_read(A.UC_ARM_REG_R1) + 4)
        slot = self.slot_of(base)
        act = self.slots.get(slot, {}).get('uic' if uic else 'other')
        if not act:
            return self.ret(0)
        if not uic:
            x, y, w, h = act
            rnd = random.Random(hash((self.round_no, slot, 'o')))
            for row in range(y, y + h):
                self.cpu_write(base + row * W * 2 + x * 2, bytes(rnd.getrandbits(8) for _ in range(w * 2)))
            return self.ret(1)
        x, y, w, h, idx = act
        self.uic_record(base, (x, y, w, h))
        bpp = SPAN_BPP[idx]
        sstride = w * bpp + 8
        rnd = random.Random(hash((self.round_no, slot, idx)))
        mu.mem_write(SRCB, bytes(rnd.getrandbits(8) for _ in range(sstride * h + 64)))
        self.w(DESC + 0x24, SRCB + 4)
        self.w(DESC + 0x1C, sstride)
        self.w(PARAM + 4, LUT); self.w(PARAM + 8, W)            # dst stride in pixels; self.w(PARAM + 0xC, h)
        fn = self.r(SPAN_TBL + 4 * idx)
        self.saved_lr = mu.reg_read(A.UC_ARM_REG_LR)
        for r_, v in ((A.UC_ARM_REG_R0, base + y * W * 2 + x * 2), (A.UC_ARM_REG_R1, DESC),
                      (A.UC_ARM_REG_R2, w), (A.UC_ARM_REG_R3, PARAM), (A.UC_ARM_REG_LR, THUNK)):
            mu.reg_write(r_, v)
        mu.reg_write(A.UC_ARM_REG_PC, fn)            # bit 0 = Thumb (stock) / ARM (ours)

    def set_drawers(self, s, kinds):
        objs = []
        for i, k in enumerate(kinds):
            o = 0xC3460000 + s * 0x100 + i * 0x20
            self.w(o, UIC_VT if k == 'uic' else OTHER_VT)
            objs.append(o)
        for i in range(3):
            self.w(CTRL + 12 * s + 4 * i, objs[i] if i < len(objs) else 0)

    # ------------------------------------------------------------ run
    def call(self, pc, r0, r1, r2, sp=0xC3F00000):
        mu = self.mu
        for r_, v in ((A.UC_ARM_REG_R0, r0), (A.UC_ARM_REG_R1, r1), (A.UC_ARM_REG_R2, r2),
                      (A.UC_ARM_REG_SP, sp), (A.UC_ARM_REG_LR, STOP)):
            mu.reg_write(r_, v)
        mu.reg_write(A.UC_ARM_REG_CPSR, 0x1D3)
        cs = [A.UC_ARM_REG_R4 + i for i in range(8)]
        for i, r_ in enumerate(cs):
            mu.reg_write(r_, 0x11110000 + i)
        mu.emu_start(pc, STOP, count=80_000_000)
        if mu.reg_read(A.UC_ARM_REG_PC) != STOP:
            raise Violation(f'did not return, pc={mu.reg_read(A.UC_ARM_REG_PC):#x}')
        if mu.reg_read(A.UC_ARM_REG_SP) != sp or [mu.reg_read(r_) for r_ in cs] != \
                [0x11110000 + i for i in range(8)]:
            raise Violation('sp / callee-saved registers not restored')
        return mu.reg_read(A.UC_ARM_REG_R0)

    def round(self, bits, acts, clear=None):
        self.round_bits, self.slots = bits, acts
        for s in range(4):
            self.w(CTRL + 0x38 + 4 * s, (clear or {}).get(s, 0))
        self.call(0xC0528700, CTRL, 0, 0)
        self.round_no += 1

    def buffers(self):
        return bytes(self.mu.mem_read(BUF0, 12 * BUFSTEP))


TC = (40, 20, 58, 30)
SCENARIOS = {
    'clear + uic blend, 3 rounds': (
        {0: ['uic']},
        [(1, {0: {'uic': TC + (0,)}}, {0: 2}), (1, {0: {'uic': TC + (0,)}}), (1, {0: {'uic': (0, 0, W, H, 1)}})]),
    'two slots (both vtables), every span kind': (
        {0: ['uic'], 1: ['uic']},
        [(0b11, {0: {'uic': (3, 5, 77, 9, 2)}, 1: {'uic': (100, 30, 120, 20, 3)}}, {0: 3, 1: 2}),
         (0b11, {0: {'uic': (0, 0, 31, 64, 0)}, 1: {'uic': (17, 1, 200, 40, 1)}}),
         (0b10, {1: {'uic': TC + (0,)}}, {1: 2})]),
    # what inputredraw produces: forced rounds back to back, every slot dirty,
    # whole-layer clears each round (its README: 12 consecutive forced rounds)
    'forced rounds back to back (input redraw)': (
        {0: ['uic'], 1: ['uic']},
        [(0b11, {0: {'uic': TC + (i % 4,)}, 1: {'uic': (17 + i, 1, 200, 40, (i + 1) % 4)}}, {0: 2, 1: 3})
         for i in range(6)]),
    'other drawer -> stock flush path': (
        {0: ['uic', 'other']},
        [(1, {0: {'uic': TC + (1,), 'other': (100, 10, 40, 8)}}, {0: 2}), (1, {0: {'uic': TC + (0,)}})]),
}
WITHOUT = {x for x in os.environ.get('PERF_WITHOUT', '').split(',') if x}   # ic,pl = lean build
COMBOS = [dict(master=1, dc=dc, nb=nb, fd=fd) for dc, nb, fd in itertools.product((0, 1), repeat=3)] + \
         [dict(master=0, dc=1, nb=1, fd=1),
          dict(master=1, dc=1, nb=0, fd=0, ir=1),                    # ir + dirtyclean coexist
          dict(master=1, dc=1, nb=1, fd=1, ir=1, ic=1, pl=1, al=1, wf=1),   # everything on
          dict(master=0, dc=1, nb=1, fd=1, ir=1, ic=1, pl=1, al=1, wf=1)]   # everything on, master off
COMBOS = [{k: v for k, v in c.items() if k not in WITHOUT} for c in COMBOS]


def run(scn, blob=None, sym=None, info=None, sw=None):
    drawers, rounds = SCENARIOS[scn]
    g = Rig(blob, sym, info, sw)
    for s, k in drawers.items():
        g.set_drawers(s, k)
    for rd in rounds:
        g.round(*rd)
    return g


def check(core=None, verbose=True, gen_patch=None):
    kw = {'core': core} if core else {}
    blob, info, sym = P.build(set(), 1, gen_patch=gen_patch, without=WITHOUT, **kw)
    nb_syms = {sym['nb_mod'] + v for k, v in P.module_neonblit()[1].items() if k != 'nb_layer_fill'}
    fails = []
    for scn in SCENARIOS:
        ref = run(scn)
        assert not ref.violations, ref.violations
        refbuf = ref.buffers()
        for sw in COMBOS:
            tag = f'{scn:42s} {sw}'
            try:
                g = Rig(blob, sym, info, sw)
                hits = {'neon': 0}
                neon = {BLOCK + 32 + a for a in nb_syms}
                g.mu.hook_add(UC_HOOK_CODE, lambda mu, a, s, _: hits.__setitem__('neon', hits['neon'] + (a in neon)))
                drawers, rounds = SCENARIOS[scn]
                for s, k in drawers.items():
                    g.set_drawers(s, k)
                for rd in rounds:
                    g.round(*rd)
                probs = []
                if g.violations:
                    probs.append(f'violations {g.violations[:3]}')
                if g.buffers() != refbuf:
                    probs.append('buffers differ from stock')
                on = sw['master']
                body = BLOCK + 32
                dma = g.r(body + sym['fd_mod'] + 0x18)
                if bool(dma) != bool(on and sw['fd']):
                    probs.append(f'dma fills {dma} with fd={sw["fd"]} master={on}')
                if bool(hits['neon']) != bool(on and sw['nb']):
                    probs.append(f'neon spans ran {hits["neon"]} with nb={sw["nb"]}')
                fast = g.r(body + sym['dc_mod'] + 0x14)
                if 'other' not in scn and bool(fast) != bool(on and sw['dc']):
                    probs.append(f'dirtyclean fast rounds {fast} with dc={sw["dc"]}')
                if not on and g.flushes != ref.flushes:
                    probs.append(f'master off: {g.flushes} flushes, stock {ref.flushes}')
                n = {k: g.r(body + o) for k, o in (('dma', 0x20), ('neon', 0x24), ('stock', 0x28))}
                want = 'dma' if on and sw['fd'] else 'neon' if on and sw['nb'] else 'stock'
                if not n[want] or any(n[k] for k in n if k != want):
                    probs.append(f'fill paths {n}, expected only {want}')
                if not any('PERF ctl' in s for s in g.logs):
                    probs.append('no PERF log line')
            except Exception as e:                    # noqa: BLE001
                probs = [f'{type(e).__name__}: {e}']
            if verbose:
                print(('ok  ' if not probs else 'BAD ') + tag + ('' if not probs else '  ' + '; '.join(probs)))
            if probs:
                fails.append(tag)
    return fails


MUTANTS = [
    ('dispatcher ignores filldma result', '        bl      fd_layer_fill               @ checks its own fd_enable\n        cmp     r0, #0\n        bne     1f',
     '        bl      fd_layer_fill               @ checks its own fd_enable\n        cmp     r0, #0\n        b       1f'),
    ('dispatcher skips the master check', '        ldr     r0, [ip, #0x08]             @ master\n        cmp     r0, #0\n        beq     3f',
     '        ldr     r0, [ip, #0x08]             @ master\n        cmp     r0, #0\n        nop'),
    ('neon fill without switch', '        ldr     r0, [ip, #0x0C]             @ neonblit switch\n        cmp     r0, #0\n        beq     3f',
     '        ldr     r0, [ip, #0x0C]             @ neonblit switch\n        cmp     r0, #0\n        nop'),
    ('no C_COPY seed', '        mov     r1, #0xF\n        str     r1, [r0, #0x0C]', '        mov     r1, #0\n        str     r1, [r0, #0x0C]'),
    ('dc gate ignores master', '        cmp     r0, #0\n        bne     dc_clean\n        ldr     pc, =FW_FLUSH',
     '        cmp     r0, #0\n        b       dc_clean\n        ldr     pc, =FW_FLUSH'),
    ('neon gate ignores pf_nb', '        ldrne   ip, pf_nb', '        movne   ip, #1'),
    ('lz gate ignores pf_lz', '        ldrne   ip, pf_lz', '        movne   ip, #1'),
    ('gates ignore master', '        ldr     ip, pf_master', '        mov     ip, #1'),
    ('veneer to wrong target', '        str     r1, [r2, #4]', '        add     r1, r1, #4\n        str     r1, [r2, #4]'),
    ('only phase 1 written', '        cmp     r10, #3\n        blt     5b', '        cmp     r10, #2\n        blt     5b'),
    ('ir gate ignores master', '        bne     ir_enq_hook', '        b       ir_enq_hook'),
    ('pl load gate ignores master', '        bne     pl_load', '        b       pl_load'),
    ('ic1 replay drops mov r0, r11', '        mov     r0, r11', '        mov     r0, r0'),
    ('ic2 replay loses the flags', '        adds    r2, r2, #4', '        add     r2, r2, #4'),
    ('ic1 resumes at the wrong address', '1:      .word   0xC06021A1', '1:      .word   0xC06021A3'),
    ('thumb branch J2 wrong', '        eor     r6, r6, r4                  @ J2', '        nop'),
    ('thumb blx writes one halfword', '        strhne  ip, [r0]', '        nop'),
    ('thumb veneer is an ARM one', '        ldreq   r3, =0xF000F8DF', '        ldreq   r3, =0xE51FF004'),
    ('iconcache arena not set', '        str     r1, [r0, #0x08]             @ ARENA (absolute)', '        nop'),
    ('inputredraw ships enabled', '        mov     r1, #IR_EN_INIT', '        mov     r1, #1'),
    ('claims skipped', '        ldr     r7, [r6], #4\n1:      cmp     r7, #0', '        mov     r7, #0\n        add     r6, r6, #4\n1:      cmp     r7, #0'),
    ('al gate ignores master', '        bne     al_unpremul', '        b       al_unpremul'),
    ('al gate stock target wrong', '1:      .word   0xc0563ba8', '1:      .word   0xc0563bac'),
    ('alphalut ships enabled', '        mov     r1, #AL_EN_INIT', '        mov     r1, #1'),
    ('al offset not at +40', '        .word   AL_MOD_OFF', '        .word   0'),
    ('wf gate ignores master', '        bne     wf_method', '        b       wf_method'),
    ('wf gate stock target wrong', '1:      .word   0xc05a3728', '1:      .word   0xc05a372c'),
    ('waveform ships enabled', '        mov     r1, #WF_EN_INIT', '        mov     r1, #1'),
    ('wf offset not at +44', '        .word   WF_MOD_OFF', '        .word   0'),
]


def mutate():
    src = (HERE / 'perf_core.S').read_text()
    survivors = []
    for name, old, new in MUTANTS:
        gen = old not in src                      # a generated-stub mutant
        if not gen and src.count(old) != 1:
            raise SystemExit(f'mutant {name!r}: pattern found {src.count(old)} times')
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / 'perf_core.S'
            p.write_text(src if gen else src.replace(old, new))
            gp = (old, new) if gen else None
            try:
                fails = check(p, verbose=False, gen_patch=gp)
            except BaseException as e:               # noqa: BLE001
                fails = [f'{type(e).__name__}: {e}']
            if not fails:                            # claim/phase mutants: the loader tests
                fails = loader_fails(p, gp)
            if not fails:                            # new-module gates: their unit tests
                fails = gates_fails(p, gp)
            if not fails:                            # lz4fast gate mutants: its icon test
                import test_perf_lz
                try:
                    fails = ['lz'] if test_perf_lz.main(8, core=p, gen_patch=gp) else []
                except BaseException as e:           # noqa: BLE001
                    fails = [f'{type(e).__name__}: {e}']
        print(('caught   ' if fails else 'SURVIVED ') + name, fails[:1])
        if not fails:
            survivors.append(name)
    return survivors


def gates_fails(core, gen_patch=None):
    import unittest, test_perf_gates as TG
    orig = P.build
    TG.P.build = lambda en, m, **k: orig(en, m, core=core, gen_patch=gen_patch, without=k.get('without', ()))
    try:
        suite = unittest.defaultTestLoader.loadTestsFromModule(TG)
        res = unittest.TextTestRunner(stream=open('/dev/null', 'w'), verbosity=0).run(suite)
        return [str(x[0]) for x in res.failures + res.errors]
    finally:
        TG.P.build = orig


def loader_fails(core, gen_patch=None):
    import unittest, test_perf_loader as TL
    orig = P.build
    TL.P.build = lambda en, m, **k: orig(en, m, core=core, gen_patch=gen_patch, without=k.get('without', ()))
    try:
        TL.PerfThroughLoader.setUpClass()
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(TL.PerfThroughLoader)
        res = unittest.TextTestRunner(stream=open('/dev/null', 'w'), verbosity=0).run(suite)
        return [str(x[0]) for x in res.failures + res.errors]
    finally:
        TL.P.build = orig


if __name__ == '__main__':
    if '--mutate' in sys.argv:
        s = mutate()
        print('survivors:', s)
        sys.exit(1 if s else 0)
    f = check()
    print(f'{len(f)} failures' if f else 'all combos pass')
    sys.exit(1 if f else 0)
