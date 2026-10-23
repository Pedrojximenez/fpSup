"""Unicorn tests for filldma.S (fd_layer_fill) against the real firmware image.

A layer object is built in memory with the real vtable 0xC2E38E5C, so the
stock fill C0721480 -> C0722490 runs unmodified as the reference.  For every
case fd_layer_fill runs on an identical buffer:
  r0 == 0  -> the buffer (with 64-byte guards) must equal the stock result;
  r0 != 0  -> nothing may have changed (buffer, no invalidate, no driver call),
              then the stock fill runs -- what the dispatcher does -- and the
              result must equal the stock result.
On the DMA path the real driver C00DB188 / C00DAFF8 runs; only the OS calls
(semaphores, IRQ enable), the range invalidate and the system-status getter
are stubbed, and the Fill DMA block at 0x30041000 is a model of what C00DAFF8
programs:  +00 bit0 start  +10 dst (DRAM offset/4)  +14 stride (words)
+18 width (words)  +1C rows  +20/+24 pattern  +28 bits1:0 mode (0 = fill).
Completion is signalled by giving the driver's done-semaphore.

    python3 -B -m unittest test_filldma          (FILLDMA_SRC=... to test a copy)
"""
import ctypes, os, pathlib, struct, sys, unittest

from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4, UC_ARM_REG_R5,
                               UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9,
                               UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_PC)

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SRC = pathlib.Path(os.environ.get('FILLDMA_SRC', HERE / 'filldma.S'))
IMAGE = (ROOT / 'out' / 'MAIN_c0000000.bin').read_bytes()

STOCK_FILL = 0xC0721480
VTABLE = 0xC2E38E5C          # DisplayOsdLayer_ARGB_Idx256; fill at +0x20 = 0xC2E38E7C
BLOCK = 0xC5800000
STACK_TOP = 0xC7100000
RET = 0xC7F00000
LAYER = 0xC7200000
BUFOBJ = 0xC7200100
STATUS = 0xC7200200
FAKE_VT = 0xC7200400
ZERO_FN = 0xC7200800
CACHED_BUF = 0xC6000000
UNCACHED_BUF = 0x46000000
BUFSZ = 0x00800000

FILL_INITED = 0xC31D25B4
SEM_MUTEX_P, SEM_DONE_P = 0xC301FEC4, 0xC301FEC0
MUTEX_ID, DONE_ID = 7, 8
WAI_SEM, SIG_SEM, INT_ENA = 0xC01F8E8C, 0xC01F8CDC, 0xC000FCA0
DCIMVAC, FULL_FLUSH, SYSSTAT = 0xC000EB28, 0xC000E91C, 0xC00178D8
UNEXPECTED = {0xC000E9B8: 'full clean', 0xC000EA54: 'range clean+inv', 0xC000EB90: 'range clean',
              0xC00DBC80: 'driver init (creates a task)'}
DMA_BASE, CLKGATE = 0x30041000, 0x300022A4
DRIVER = 0xC00DB188


class Fail(Exception):
    pass


class Emu:
    def __init__(self, src=SRC):
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        size = (len(IMAGE) + 0xFFFF) & ~0xFFFF
        mu.mem_map(0xC0000000, size)
        mu.mem_write(0xC0000000, IMAGE)
        mu.mem_map(0xC3000000, 0x01000000)                     # BSS, zero
        # one DRAM buffer, seen through both aliases like the real page table
        self.dram = ctypes.create_string_buffer(BUFSZ)
        mu.mem_map_ptr(CACHED_BUF, BUFSZ, 7, ctypes.addressof(self.dram))
        mu.mem_map_ptr(UNCACHED_BUF, BUFSZ, 7, ctypes.addressof(self.dram))
        for base, sz in ((BLOCK, 0x100000),
                         (STACK_TOP - 0x100000, 0x100000), (LAYER, 0x1000), (RET, 0x1000),
                         (0x30000000, 0x100000)):
            mu.mem_map(base, sz)
        mu.mem_write(RET, struct.pack('<I', 0xE320F000))      # nop; we stop here
        self.events, self.pending, self.mutex_fail, self.bad_sp = [], 0, False, []
        self.mutex_held = False
        self.w32(SEM_MUTEX_P, MUTEX_ID)
        self.w32(SEM_DONE_P, DONE_ID)
        self.w32(FILL_INITED, 1)
        self.code = assemble(src)
        self.sym = symbols(src)
        mu.mem_write(BLOCK, self.code)
        mu.mem_write(ZERO_FN, struct.pack('<II', 0xE3A00000, 0xE12FFF1E))   # mov r0,#0; bx lr
        self.recording = 0
        stubs = {WAI_SEM: self.s_wai, SIG_SEM: self.s_sig, INT_ENA: self.s_int,
                 DCIMVAC: self.s_inval, FULL_FLUSH: self.s_full, SYSSTAT: self.s_sysstat}
        for a in UNEXPECTED:
            stubs[a] = self.s_unexpected
        self.stubs = stubs
        for a in stubs:
            mu.hook_add(UC_HOOK_CODE, self.on_stub, begin=a, end=a)
        mu.hook_add(UC_HOOK_CODE, self.on_driver, begin=DRIVER, end=DRIVER)
        mu.hook_add(UC_HOOK_MEM_WRITE, self.on_mmio, begin=DMA_BASE, end=DMA_BASE + 0xFFF)

    # ------------------------------------------------------------ memory
    def r32(self, a):
        return struct.unpack('<I', self.mu.mem_read(a, 4))[0]

    def w32(self, a, v):
        self.mu.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))

    def reg(self, r):
        return self.mu.reg_read(r)

    # ------------------------------------------------------------ stubs
    def ret(self, r0=None):
        if r0 is not None:
            self.mu.reg_write(UC_ARM_REG_R0, r0 & 0xFFFFFFFF)
        self.mu.reg_write(UC_ARM_REG_PC, self.reg(UC_ARM_REG_LR))

    def on_stub(self, mu, addr, size, _):
        # only our own calls are checked: the stock driver itself runs with sp = 4 mod 8
        sp = self.reg(UC_ARM_REG_SP)
        if addr == DCIMVAC and sp % 8:
            self.bad_sp.append((hex(addr), hex(sp)))
        self.stubs[addr](addr)

    def on_driver(self, mu, addr, size, _):
        sp = self.reg(UC_ARM_REG_SP)
        if sp % 8:
            self.bad_sp.append(('driver', hex(sp)))
        self.events.append(('driver',))

    def s_wai(self, a):
        sem = self.reg(UC_ARM_REG_R0)
        if sem == MUTEX_ID:
            if self.mutex_fail:
                if self.mutex_fail == 'once':
                    self.mutex_fail = False
                self.events.append(('lock-failed',))
                return self.ret(-25)
            assert not self.mutex_held
            self.mutex_held = True
            self.events.append(('lock',))
            return self.ret(0)
        if sem == DONE_ID:
            if not self.pending:
                raise Fail('driver waits for a DMA that was never started (would hang)')
            self.pending -= 1
            self.events.append(('done',))
            return self.ret(0)
        raise Fail(f'wai_sem on unknown semaphore {sem}')

    def s_sig(self, a):
        sem = self.reg(UC_ARM_REG_R0)
        assert sem == MUTEX_ID and self.mutex_held
        self.mutex_held = False
        self.events.append(('unlock',))
        self.ret(0)

    def s_int(self, a):
        self.events.append(('irq', self.reg(UC_ARM_REG_R0), self.reg(UC_ARM_REG_R1)))
        self.ret(0)

    def s_inval(self, a):
        lo, hi = self.reg(UC_ARM_REG_R0), self.reg(UC_ARM_REG_R1)
        self.events.append(('inval', lo, hi))
        self.ret()

    def s_full(self, a):
        raise Fail('whole-cache flush C000E91C called')

    def s_sysstat(self, a):
        self.events.append(('sysstat',))
        self.mu.mem_write(STATUS + 0x18 + 0x84, bytes([self.recording]))
        self.ret(STATUS)

    def s_unexpected(self, a):
        raise Fail(f'unexpected call {UNEXPECTED[a]} {a:#x}')

    # ------------------------------------------------------------ DMA model
    def on_mmio(self, mu, access, addr, size, value, _):
        if addr != DMA_BASE or not value & 1:
            return
        regs = {o: self.r32(DMA_BASE + o) for o in (0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28)}
        if not self.r32(CLKGATE) & 0x100:
            raise Fail('DMA started with its clock gate off')
        if regs[0x28] & 3:
            raise Fail(f'mode {regs[0x28] & 3} is not fill')
        if regs[0x20] != regs[0x24]:
            raise Fail('two different pattern words')
        off = regs[0x10] * 4
        width, rows, stride = regs[0x18], regs[0x1C], regs[0x14]
        if not (0 < width < 0x4000 and 0 < rows < 0x4000 and stride < 0x4000):
            raise Fail(f'register out of range {regs}')
        pat = struct.pack('<I', regs[0x20]) * width
        va = 0xC0000000 + off                       # either alias: same DRAM
        if not CACHED_BUF <= va < CACHED_BUF + BUFSZ:
            raise Fail(f'DMA to unmapped DRAM offset {off:#x}')
        for r in range(rows):
            mu.mem_write(va + r * stride * 4, pat)
        self.pending += 1
        self.events.append(('start', va, width, rows, stride, regs[0x20]))

    # ------------------------------------------------------------ run
    def call(self, addr, r0, r1, sp_off=0):
        sp = STACK_TOP - 0x100 - sp_off
        for r, v in ((UC_ARM_REG_R0, r0), (UC_ARM_REG_R1, r1), (UC_ARM_REG_SP, sp),
                     (UC_ARM_REG_LR, RET)):
            self.mu.reg_write(r, v)
        cs = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
              UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11]
        for i, r in enumerate(cs):
            self.mu.reg_write(r, 0x11110000 + i)
        try:
            self.mu.emu_start(addr, RET, count=60_000_000)
        except UcError as e:
            raise Fail(f'{e} at pc={self.reg(UC_ARM_REG_PC):#x}')
        if self.reg(UC_ARM_REG_PC) != RET:
            raise Fail(f'did not return (pc={self.reg(UC_ARM_REG_PC):#x})')
        saved = [self.reg(r) for r in cs]
        assert saved == [0x11110000 + i for i in range(8)], 'callee-saved registers changed'
        assert self.reg(UC_ARM_REG_SP) == sp, 'sp not restored'
        return self.reg(UC_ARM_REG_R0)


GUARD = 64


def layer(emu, w, h, base, fmt=1, vtable=VTABLE):
    """A layer object as C0721480 reads it: vt, w at +4, h at +8, format at
    +0x1C, back-buffer object at +0x4C (C0721CC8 reads [+0x24+0x28]) with
    the pixel address at its +4."""
    words = [0] * 0x20
    words[0], words[1], words[2], words[7] = vtable, w, h, fmt
    words[0x4C // 4] = BUFOBJ
    emu.mu.mem_write(LAYER, struct.pack('<32I', *words))
    emu.w32(BUFOBJ + 4, base)
    return LAYER


def size_of(w, h, fmt):
    return w * h * (2 if fmt == 1 else 4 if fmt == 0 else 1)


def noise(n):
    return bytes((i * 37 + 11) & 0xFF for i in range(n))


def stock(w, h, value, base, fmt=1, setup=None, vtable=VTABLE):
    emu = Emu()
    if setup:
        setup(emu)
    n = size_of(w, h, fmt) + 2 * GUARD
    emu.mu.mem_write(base - GUARD, noise(n))
    emu.call(STOCK_FILL, layer(emu, w, h, base, fmt, vtable), value)
    return bytes(emu.mu.mem_read(base - GUARD, n))


def ours(w, h, value, base, fmt=1, setup=None, sp_off=0, vtable=VTABLE, src=SRC):
    """fd_layer_fill, then the stock fill if it declined (the dispatcher)."""
    emu = Emu(src)
    if setup:
        setup(emu)
    n = size_of(w, h, fmt) + 2 * GUARD
    emu.mu.mem_write(base - GUARD, noise(n))
    lay = layer(emu, w, h, base, fmt, vtable)
    code = emu.call(BLOCK + emu.sym['fd_layer_fill'], lay, value, sp_off)
    untouched = bytes(emu.mu.mem_read(base - GUARD, n)) == noise(n)
    events_at_return = list(emu.events)
    if code:
        emu.call(STOCK_FILL, lay, value)
    return bytes(emu.mu.mem_read(base - GUARD, n)), code, untouched, events_at_return, emu


class FillDma(unittest.TestCase):
    BASE = CACHED_BUF + 0x1000

    def check(self, w, h, value, base=None, fmt=1, setup=None, sp_off=0, vtable=VTABLE,
              expect=0):
        base = self.BASE if base is None else base
        ref = stock(w, h, value, base, fmt, setup, vtable)
        got, code, untouched, ev, emu = ours(w, h, value, base, fmt, setup, sp_off, vtable)
        self.assertEqual(code, expect, f'return code {code}, expected {expect}')
        self.assertEqual(ref, got, 'buffer differs from the stock fill')
        self.assertFalse(emu.bad_sp, f'unaligned sp at our firmware calls: {emu.bad_sp}')
        self.assertFalse(emu.mutex_held, 'driver mutex left held')
        self.assertEqual(self.ctr(emu, 'fd_last_code'), code)
        if code:
            self.assertTrue(untouched, 'declined but the buffer changed')
            self.assertFalse([e for e in ev if e[0] in ('inval', 'driver', 'start')],
                             f'declined after touching cache/driver: {ev}')
            self.assertEqual(self.ctr(emu, 'fd_declined'), 1)
        return emu, ev

    def starts(self, ev):
        return [e for e in ev if e[0] == 'start']

    def ctr(self, emu, name):
        return emu.r32(BLOCK + emu.sym[name])

    # ---------------------------------------------------- taken
    def test_full_layer_by_dma(self):
        base = self.BASE
        emu, ev = self.check(1024, 682, 0xF000)
        st = self.starts(ev)
        size = 1024 * 682 * 2
        words = size // 4
        self.assertEqual(len(st), 2, 'full rows + remainder')
        self.assertEqual(st[0][1:6], (base, 0x2000, words >> 13, 0x2000, 0xF000F000))
        self.assertEqual(st[1][1:5], (base + (words >> 13) * 0x8000, words & 0x1FFF, 1, words & 0x1FFF))
        kinds = [e[0] for e in ev]
        first, last = kinds.index('start'), len(kinds) - 1 - kinds[::-1].index('start')
        before = [e for e in ev[:first] if e[0] == 'inval']
        after = [e for e in ev[last:] if e[0] == 'inval']
        for group in (before, after):
            self.assertEqual(group[0][1], base)
            self.assertEqual(group[-1][2], base + size - 1)
            for (_, lo, hi), (_, lo2, _) in zip(group, group[1:]):
                self.assertEqual(hi + 1, lo2, 'gap in the invalidated range')
            self.assertTrue(all(hi - lo + 1 <= 0x10000 for _, lo, hi in group), 'chunk too big')
        core = [k for k in kinds if k not in ('inval', 'sysstat')]
        self.assertEqual(core, ['driver', 'lock', 'irq', 'start', 'done', 'irq', 'unlock'] * 2)
        self.assertLess(max(i for i, k in enumerate(kinds) if k == 'inval' and i < first),
                        kinds.index('driver'))
        self.assertGreater(min(i for i, k in enumerate(kinds) if k == 'inval' and i > last),
                           len(kinds) - 1 - kinds[::-1].index('unlock'))
        self.assertLess(kinds.index('sysstat'), kinds.index('inval'), 'recording checked late')
        self.assertIn(('irq', 0x24, 1), ev)
        self.assertIn(('irq', 0x24, 0), ev)
        self.assertEqual(self.ctr(emu, 'fd_dma_ok'), 1)
        self.assertEqual(self.ctr(emu, 'fd_dma_bytes'), size)
        self.assertEqual(self.ctr(emu, 'fd_last_base'), base)
        self.assertEqual(self.ctr(emu, 'fd_last_size'), size)

    def test_value_high_bits_ignored(self):
        emu, ev = self.check(512, 64, 0xDEAD1234)
        self.assertEqual(self.starts(ev)[0][5], 0x12341234)

    def test_exact_rows_no_remainder(self):
        emu, ev = self.check(1024, 64, 0x0102)               # 128 KB = 4 rows of 0x2000 words
        self.assertEqual(len(self.starts(ev)), 1)

    def test_uncached_alias_no_cache_ops(self):
        emu, ev = self.check(1024, 64, 0x0F0F, base=UNCACHED_BUF + 0x2000)
        self.assertTrue(self.starts(ev))
        self.assertFalse([e for e in ev if e[0] == 'inval'])

    def test_caller_sp_4_mod_8(self):
        emu, ev = self.check(1024, 64, 0x1111, sp_off=4)
        self.assertTrue(self.starts(ev))

    def test_threshold_is_a_variable(self):
        emu, ev = self.check(64, 64, 0x2222,
                             setup=lambda e: e.w32(BLOCK + e.sym['fd_thresh'], 0x1000))
        self.assertTrue(self.starts(ev))

    def test_recording_allowed_by_flag(self):
        def setup(e):
            e.recording = 1
            e.w32(BLOCK + e.sym['fd_rec_ok'], 1)
        emu, ev = self.check(1024, 64, 0x2468, setup=setup)
        self.assertTrue(self.starts(ev))
        self.assertNotIn(('sysstat',), ev, 'status read although recording is allowed')

    # ---------------------------------------------------- driver fails after commit
    def test_driver_error_cpu_completes(self):
        def setup(e):
            e.mutex_fail = True
        emu, ev = self.check(1024, 682, 0x8888, setup=setup)
        self.assertEqual(self.ctr(emu, 'fd_cpu_done'), 1)
        self.assertEqual(self.ctr(emu, 'fd_dma_ok'), 0)
        invs = [e for e in ev if e[0] == 'inval']
        self.assertEqual(invs[-1][2], self.BASE + 1024 * 682 * 2 - 1)
        self.assertGreater([e[0] for e in ev].index('inval', 1 + [e[0] for e in ev].index('lock-failed')), 0)

    def test_first_chunk_error_stops(self):
        def setup(e):
            e.mutex_fail = 'once'          # first DMA refused, second would succeed
        emu, ev = self.check(1024, 682, 0x9999, setup=setup)
        self.assertEqual(self.ctr(emu, 'fd_cpu_done'), 1)
        self.assertFalse(self.starts(ev), 'kept going after the first chunk failed')

    # ---------------------------------------------------- declined: nothing touched
    def test_small(self):
        self.check(64, 64, 0x2222, expect=4)                  # 8 KB < 16 KB

    def test_disabled(self):
        self.check(1024, 682, 0x3333, expect=1,
                   setup=lambda e: e.w32(BLOCK + e.sym['fd_enable'], 0))

    def test_not_16bpp(self):
        self.check(640, 64, 0x80FF2211, fmt=0, expect=2)

    def test_invalid_layer(self):
        def setup(e):
            vt = bytearray(e.mu.mem_read(VTABLE, 0x40))
            struct.pack_into('<I', vt, 0x30, ZERO_FN)
            e.mu.mem_write(FAKE_VT, bytes(vt))
        emu, ev = self.check(1024, 64, 0x1212, setup=setup, vtable=FAKE_VT, expect=3)
        self.assertEqual(stock(1024, 64, 0x1212, self.BASE, 1, setup, FAKE_VT)[GUARD:GUARD + 8],
                         noise(GUARD + 8)[GUARD:], 'stock fills an invalid layer?')

    def test_driver_not_initialised(self):
        self.check(1024, 682, 0x4444, expect=5, setup=lambda e: e.w32(FILL_INITED, 0))

    def test_misaligned_base(self):
        self.check(1024, 64, 0x5555, base=CACHED_BUF + 0x1002, expect=6)

    def test_size_not_whole_lines(self):
        self.check(1000, 33, 0x6666, expect=6)                # 66000 bytes, 16 mod 64

    def test_not_dram(self):
        self.check(1024, 16, 0x7777, base=0x2E001000, expect=6,
                   setup=lambda e: e.mu.mem_map(0x2E000000, 0x100000))

    def test_uncached_range_past_1gb(self):
        self.check(1024, 32, 0x1357, base=0x7FFF8000, expect=6,
                   setup=lambda e: e.mu.mem_map(0x7FFF0000, 0x30000))

    def test_recording(self):
        def setup(e):
            e.recording = 1
        self.check(1024, 682, 0xABCD, setup=setup, expect=7)

    # ---------------------------------------------------- image facts this relies on
    def test_image_facts(self):
        w = lambda a: struct.unpack_from('<I', IMAGE, a - 0xC0000000)[0]
        self.assertEqual(w(VTABLE + 0x20), STOCK_FILL)
        self.assertEqual(w(0xC2EF6280 + 0x20), STOCK_FILL)
        self.assertEqual(w(VTABLE + 0x10), w(0xC2EF6280 + 0x10))    # same getBuffer
        self.assertEqual(w(0xC0722490), 0xE92D44F0)


if __name__ == '__main__':
    unittest.main()
