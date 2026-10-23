"""Run the built LOSS hook and original Thumb aggregation / callback loop.

The volume and writer are synthetic. Media transfer, descriptor arena get/free
and the final completion callback are explicit substitutes. The native cookie
loop, current-cookie ordering and counter reset execute real firmware bytes.
This proves the insertion ABI and scoped decisions, not hardware timing.
"""
import pathlib
import struct
import tempfile
import unittest

import test_v3_lossless as V
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5,
                               UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
                               UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_CPSR)

VOLUME, SCATTER, FRAME, WRITER = 0x45610000, 0x45602000, 0x45604000, 0x45600000
POOL = 0xC2A00000
TRANSFER, CALLBACK, ARENA_FREE, ARENA_GET = 0xC0646C60, 0xC03A55D0, 0xC0100100, 0xC0100120
PENDING = [0x45640000 + 4 * n for n in range(128)]
REGS = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
        UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
        UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


class BulkCamera(V.LosslessCamera):
    def __init__(self, *args, **kwargs):
        self.testing_bulk = False
        self.completed, self.transfers, self.continuations = [], [], []
        self.reached_end = False
        super().__init__(*args, **kwargs)

    def _hook(self, mu, addr, size, data):
        if self.testing_bulk:
            if addr == self.bulk_c:
                if self.r(UC_ARM_REG_SP) & 7:
                    raise AssertionError('new C call is not aligned')
                self.bulk_args = tuple(self.r(r) for r in REGS[:4])
            if addr in (0xC063F82C, 0xC063F830):
                self.continuations.append((addr, tuple(self.r(r) for r in REGS),
                                           self.r(UC_ARM_REG_SP), self.r(UC_ARM_REG_LR),
                                           self.r(UC_ARM_REG_CPSR) & 0xF0000000))
            if addr == TRANSFER:
                self.transfers.append((self.r(UC_ARM_REG_R0), self.w(VOLUME + 0x4850)))
                return self._ret(0)
            if addr == CALLBACK:
                self.completed.append((self.r(UC_ARM_REG_R0), self.r(UC_ARM_REG_R1)))
                return self._ret(0)
            if addr == ARENA_FREE:
                return self._ret(0)
            if addr == ARENA_GET:
                return self._ret(0x45603000)
            if addr == 0xC063F888:
                self.reached_end = True
                mu.emu_stop()
                return
            allowed = (0xC063F140 <= addr < 0xC063F220 or
                       0xC063F81C <= addr < 0xC063F888 or
                       self.blob <= addr < self.blob_end or
                       self.cave <= addr < self.cave + 104)
            if not allowed:
                raise AssertionError(f'unexpected native execution {addr:#x}')
        return super()._hook(mu, addr, size, data)


class BulkNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory(prefix='fpl-bulk-native-') as tmp:
            cls.sup, cls.facts = V.L.sup_file(pathlib.Path(tmp))
        from armasm import symbols
        cls.sym = symbols(V.HERE / 'native/card.S', cls.facts['defines'])

    def boot(self):
        cam = BulkCamera(*V.T.card(('10LOSS.BIN', self.sup)))
        cam.boot()
        block = next(a for kind, a, _, name in cam.log()
                     if kind == 'LOADED' and name == '10LOSS.BIN')
        cam.blob = block + V.B.SL_HEADER_LEN
        cam.blob_end = cam.blob + self.facts['blob_len']
        cam.card_state = cam.blob + self.facts['state_off']
        cam.cave = cam.w(V.T.cave.CAVE_BUMP) - 104
        cam.bulk_c = cam.blob + self.facts['c_base'] + (self.facts['entries']['fpl_card_bulk'] & ~1)
        self.assertLess(cam.heap_next, WRITER)
        for at in (TRANSFER, CALLBACK, ARENA_FREE, ARENA_GET):
            cam.put(at, 0xE12FFF1E)
        cam.put(VOLUME + 0x4834, CALLBACK)
        cam.put(VOLUME + 0x4838, ARENA_GET)
        cam.put(VOLUME + 0x4848, ARENA_FREE)
        cam.put(VOLUME + 0x484C, 0x45603000)
        cam.put(VOLUME + 0x4A54, 1024)
        cam.put(VOLUME + 0x4A58, 1 << 20)
        cam.put(SCATTER + 8, FRAME)
        cam.put(0xC2F1F3D8, POOL)
        cam.put(POOL + 0x112C, 90)
        for name, value in [('enabled', 1), ('fps_ceil', 60), ('start_free', 96),
                            ('latency_us', 100000), ('arrival_reserve', 6),
                            ('frame_limit', 42), ('free_watermark', 12)]:
            self.set_field(cam, 'bulk_policy.' + name, value)
        self.set_field(cam, 'bulk_writer_frame', FRAME)
        return cam

    def set_field(self, cam, name, value):
        cam.put(cam.card_state + self.facts['layout'][name], value)

    def field(self, cam, name):
        return cam.w(cam.card_state + self.facts['layout'][name])

    def enter(self, cam, pending, delta=0):
        cam.put(VOLUME + 0x4850, pending)
        for i in range(pending):
            cam.put(VOLUME + 0x4854 + 4 * i, PENDING[i])
        sp = V.T.STACK - 0x1000 - delta
        cam.put(sp + 20, VOLUME)
        for n, reg in enumerate(REGS):
            cam.mu.reg_write(reg, 0x11000000 + n)
        cam.mu.reg_write(UC_ARM_REG_R11, SCATTER)
        cam.mu.reg_write(UC_ARM_REG_SP, sp)
        cam.mu.reg_write(UC_ARM_REG_LR, 0x47000080)
        cam.testing_bulk = True
        try:
            cam.mu.emu_start(0xC063F81D, 0, count=100000)
        finally:
            cam.testing_bulk = False
            if cam.error:
                raise cam.error
        self.assertTrue(cam.reached_end, 'native path did not reach its bounded end')
        at, regs, after_sp, lr, flags = cam.continuations[0]
        self.assertEqual(after_sp, sp)
        self.assertEqual(lr, 0x47000080)
        self.assertEqual(flags, 0x60000000 if pending == 128 else 0x80000000)
        self.assertEqual(regs[1:4], (0x11000001, pending, 0x11000003))
        self.assertEqual(regs[4:8], tuple(0x11000000 + n for n in range(4, 8)))
        self.assertEqual(regs[8:], (0x4850, 0x11000009, 0x1100000A, SCATTER))
        self.assertEqual(regs[0], VOLUME if at == 0xC063F82C else 0x11000000)
        self.assertEqual(cam.bulk_args, (VOLUME, FRAME, pending, cam.card_state))
        self.assertEqual(cam.r(UC_ARM_REG_SP), sp)

    def assert_sent(self, cam, pending):
        self.assertEqual(cam.transfers, [(VOLUME, pending)])
        self.assertEqual(cam.completed, [(f, 0) for f in PENDING[:pending]] + [(FRAME, 0)])
        self.assertEqual((cam.w(VOLUME + 0x4850), cam.w(VOLUME + 0x4A58)), (0, 0))

    def test_limit_sends_prior_cookies_then_current_exactly_once(self):
        cam = self.boot()
        self.enter(cam, 41)
        self.assert_sent(cam, 41)
        self.assertEqual(self.field(cam, 'bulk_policy.count_flushes'), 1)

    def test_below_limit_appends_current_cookie_without_transfer(self):
        cam = self.boot()
        self.enter(cam, 40)
        self.assertEqual((cam.transfers, cam.completed), ([], []))
        self.assertEqual(cam.w(VOLUME + 0x4850), 41)
        self.assertEqual(cam.w(VOLUME + 0x4854 + 40 * 4), FRAME)

    def test_pressure_sends_current_with_no_prior_cookie(self):
        cam = self.boot()
        cam.put(POOL + 0x112C, 12)
        self.enter(cam, 0)
        self.assert_sent(cam, 0)

    def test_misaligned_native_stack_is_aligned_for_new_c(self):
        cam = self.boot()
        self.enter(cam, 41, delta=4)
        self.assert_sent(cam, 41)

    def test_off_or_foreign_frame_keeps_native_128_rule(self):
        for field in ('bulk_policy.enabled', 'bulk_writer_frame'):
            for pending in (41, 128):
                with self.subTest(field=field, pending=pending):
                    cam = self.boot()
                    self.set_field(cam, field, 0)
                    self.enter(cam, pending)
                    if pending == 128:
                        self.assert_sent(cam, pending)
                    else:
                        self.assertEqual(cam.transfers, [])
                        self.assertEqual(cam.w(VOLUME + 0x4850), pending + 1)

    def test_foreign_volume_callback_keeps_native_rule(self):
        cam = self.boot()
        cam.put(VOLUME + 0x4834, 0)
        self.enter(cam, 41)
        self.assertEqual(cam.transfers, [])

    def test_writer_scope_and_elapsed_return_are_connected(self):
        cam = self.boot()
        self.set_field(cam, 'bulk_writer_frame', 0)
        before = cam.blob + self.facts['c_base'] + self.facts['entries']['fpl_card_flush']
        after = cam.blob + self.facts['c_base'] + self.facts['entries']['fpl_card_written']
        cam.call(before, r0=WRITER, r1=FRAME, r2=cam.card_state, sp=V.T.STACK - 0x1000,
                 thumb=True)
        self.assertEqual(self.field(cam, 'bulk_writer_frame'), FRAME)
        self.enter(cam, 41)
        cam.now += 500000
        cam.call(after, r0=cam.card_state, r1=3 << 20, r2=0, sp=V.T.STACK - 0x1000,
                 thumb=True)
        self.assertEqual(self.field(cam, 'bulk_writer_frame'), 0)
        self.assertEqual(self.field(cam, 'bulk_policy.raw'), 1)
        self.assertGreaterEqual(self.field(cam, 'bulk_policy.latency_us'), 500000)
        self.assertLess(self.field(cam, 'bulk_policy.frame_limit'), 42)

    def test_mutation_omitting_new_gate_is_detected(self):
        cam = self.boot()
        cam.put(V.BULK_GATE, V.SITES[V.BULK_GATE][0])
        # The old native predicate cannot send 42 small files. Run without
        # shim ABI assertions, then prove the expected release assertion fails.
        cam.put(VOLUME + 0x4850, 41)
        sp = V.T.STACK - 0x1000
        cam.put(sp + 20, VOLUME)
        cam.mu.reg_write(UC_ARM_REG_SP, sp)
        cam.mu.reg_write(UC_ARM_REG_R11, SCATTER)
        cam.testing_bulk = True
        try:
            cam.mu.emu_start(0xC063F81D, 0, count=100000)
        finally:
            cam.testing_bulk = False
        if cam.error:
            raise cam.error
        with self.assertRaises(AssertionError):
            self.assert_sent(cam, 41)
        self.assertEqual(cam.w(VOLUME + 0x4850), 42)


if __name__ == '__main__':
    unittest.main()
