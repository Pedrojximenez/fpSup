"""Real card/shims/core: virtual rate commit must notify a shared carrier.

Native menu/OS boundaries are modeled; this does not emulate sensor or DMA.
"""
import struct
import unittest

import test_virtual_rcd as V
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5,
                               UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
                               UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
                               UC_ARM_REG_SP)

SITES = (0xC057A6F8, 0xC05821B8)
LV_CYCLE = [('schedule', 6), 'LV_STOP', 'LV_START', ('schedule', 3)]
SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


class RateCommitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out, cls.f = V.built()

    boot = V.VirtualTests.boot

    def camera(self, fr=7):
        cam = self.boot(fr=fr)
        cam.geometry(12, 992, 662)
        self.assertEqual(cam.apply(), 0)
        cam.running = True
        cam.native_commits = []
        cam.native_override = None
        cam.busy_at_native = False
        cam.external_alignment = []

        def native(mu, addr, size, data):
            var = cam.r(UC_ARM_REG_R0)
            row = cam.w(var + 8)
            st = cam.s()
            pairs = [(cam.w(st + V.L.S['RPAIRS'] + 8 * i),
                      cam.w(st + V.L.S['RPAIRS'] + 8 * i + 4))
                     for i in range(cam.w(st + V.L.S['RPAIRN']))]
            enum = next(e for e, r in pairs if r == row)
            # The callback sees the new rank and table before native conversion.
            cam.native_commits.append((addr, row, enum, cam.w(st + V.L.S['VRATE']),
                                       tuple(cam.r(r) for r in (UC_ARM_REG_R1,
                                                               UC_ARM_REG_R2,
                                                               UC_ARM_REG_R3)),
                                       len(cam.lv)))
            cam.fr = enum if cam.native_override is None else cam.native_override
            if cam.busy_at_native:
                cam.put(0xC35A952c, 1)

        for site in SITES:
            body = site + 4
            # Replay pushes {r4-r7,lr}; the modeled native body returns 0x55.
            cam.mu.mem_write(body, struct.pack('<2I', 0xE3A00055, V.RC.POP4567))
            cam.test_code.update((body, body + 4))
            cam.mu.hook_add(UC_HOOK_CODE, native, begin=body, end=body)

        def alignment(mu, addr, size, data):
            cam.external_alignment.append(cam.r(UC_ARM_REG_SP) & 7)

        for name in ('LV_HOLDER', 'CAMSCH1', 'CS_GET', 'CS_SET', 'LV_STOP', 'LV_START'):
            addr = V.RC.FW[name]
            cam.mu.hook_add(UC_HOOK_CODE, alignment, begin=addr, end=addr)
        return cam

    def commit(self, cam, site, row):
        var = V.RC.KEYBUF + 0x900
        cam.put(var + 8, row)
        seeds = [0x12340000 + i for i in range(len(SAVED))]
        for reg, value in zip(SAVED, seeds):
            cam.mu.reg_write(reg, value)
        result = cam.callr(site, r0=var, r1=0x1111, r2=0x2222, r3=0x3333,
                           sp=V.T.STACK - 0x1000)
        self.assertEqual(result['r0'], 0x55, 'must preserve native return value')
        self.assertEqual([cam.r(r) for r in SAVED], seeds)
        self.assertEqual(cam.native_commits[-1][4], (0x1111, 0x2222, 0x3333))
        self.assertEqual(cam.r(UC_ARM_REG_SP), V.T.STACK - 0x1000)
        self.assertEqual(cam.w(cam.s() + V.L.S['RATE_LVOWED']), 0)
        self.assertFalse(any(cam.external_alignment))
        self.assertEqual(cam.misaligned, [])

    def test_same_carrier_round_trip_reloads_after_both_native_callbacks(self):
        for site in SITES:
            with self.subTest(site=hex(site)):
                cam = self.camera()
                before = cam.snapshot()
                for count, row, rank in ((1, 9, 23976), (2, 10, 27972), (3, 8, 0)):
                    self.commit(cam, site, row)
                    self.assertEqual(cam.fr, 7)
                    self.assertEqual(cam.w(cam.s() + V.L.S['VRATE']), rank)
                    self.assertEqual(cam.native_commits[-1][3], rank)
                    self.assertEqual(cam.native_commits[-1][5], 4 * (count - 1),
                                     'reload must happen after native callback')
                    self.assertEqual(cam.lv, LV_CYCLE * count)
                    self.assertEqual(cam.w(cam.s() + V.L.S['RATE_LV_RELOADS']), count)
                self.assertEqual(cam.w(cam.s() + V.L.S['VR_COMMITS']), 3)
                self.assertEqual(cam.schedule, 3)
                self.assertEqual(cam.snapshot(), before, 'timing/geometry entries stay intact')
                self.assertEqual(cam.written, cam.written_baseline)
                cam.assert_tables(self)

    def test_repeating_a_rate_and_changing_native_carrier_do_not_extra_reload(self):
        cam = self.camera(fr=3)
        self.commit(cam, SITES[0], 9)  # 30 -> 240: native enum changes, original owns notification.
        self.assertEqual(cam.fr, 7)
        self.assertEqual(cam.lv, [])
        self.commit(cam, SITES[1], 9)  # same 240 selection.
        self.assertEqual(cam.lv, [])
        self.commit(cam, SITES[1], 3)  # 240 -> 30: different carrier again.
        self.assertEqual(cam.fr, 3)
        self.assertEqual(cam.lv, [])
        self.assertEqual(cam.w(cam.s() + V.L.S['RATE_LV_RELOADS']), 0)

    def test_post_commit_guards_consume_pending_reload(self):
        for guard in ('recording', 'busy_at_native', 'virtual_commit', 'native_override', 'not_running'):
            with self.subTest(guard=guard):
                cam = self.camera()
                if guard == 'recording':
                    cam.put(0xC35A952c, 1)
                elif guard == 'virtual_commit':
                    cam.put(cam.service() + 8, 1)
                elif guard == 'native_override':
                    cam.native_override = 12
                elif guard == 'not_running':
                    cam.running = False
                else:
                    cam.busy_at_native = True
                self.commit(cam, SITES[1], 9)
                self.assertEqual(cam.lv, [])
                self.assertEqual(cam.w(cam.s() + V.L.S['RATE_LV_RELOADS']), 0)

    def test_shutdown_restores_rate_hook_sites(self):
        cam = self.camera()
        self.commit(cam, SITES[0], 9)
        covered = {a + i for a, n, _ in cam.journal() for i in range(n)}
        for site in SITES:
            self.assertTrue(all(site + i in covered for i in range(4)))
        cam.power_off()
        for site in SITES:
            self.assertEqual(cam.w(site), V.T.word(cam.img, site))

    def test_native_setter_only_notifies_when_carrier_changes(self):
        cam = self.camera()
        obj, table, stub = (V.RC.KEYBUF + x for x in (0x2800, 0x2900, 0x2C00))
        cam.put(obj + 12, table)
        cam.put(obj + 24, 7)

        def code(addr, words):
            cam.mu.mem_write(addr, struct.pack(f'<{len(words)}I', *words))
            cam.by_addr.pop(addr, None)
            cam.test_code.update(range(addr, addr + 4 * len(words), 4))

        # Model only the getter/setter/notification boundaries. The equality
        # decision and callback order execute exact FUN_c0074d78 ROM bytes.
        code(stub, (0xE3A00000, 0xE12FFF1E))
        code(stub + 16, (0xE5801018, 0xE12FFF1E))
        code(stub + 32, (0xE590301C, 0xE2833001, 0xE580301C, 0xE12FFF1E))
        cam.put(table + 0x1C, stub)
        cam.put(table + 0x2C, stub + 16)
        cam.put(table + 0x30, stub + 32)
        code(0xC00913F8, (0xE3A00000, 0xE12FFF1E))
        code(0xC006C230, (0xE5900018, 0xE12FFF1E))
        code(0xC00911A0, (0xE5903020, 0xE2833001, 0xE5803020, 0xE12FFF1E))
        start, end = 0xC0074D78, 0xC0074EC8
        cam.mu.mem_write(start, cam.img[start - 0xC0000000:end - 0xC0000000])
        cam.test_code.update(range(start, end, 4))
        for enum, notifications in ((7, 0), (12, 1), (12, 1), (7, 2)):
            cam.callr(start, r0=obj, r1=enum, r2=0, r3=0, sp=V.T.STACK - 0x1000)
            self.assertEqual(cam.w(obj + 24), enum)
            self.assertEqual((cam.w(obj + 28), cam.w(obj + 32)),
                             (notifications, notifications))

    def test_missing_post_commit_phase_is_detected(self):
        cam = self.camera()
        slot = cam.s() + V.L.S['FN'] + 4 * V.L.FNS.index('RCMT')
        original = cam.w(slot)
        wrapper = V.RC.KEYBUF + 0x1800
        # Only mutate emulated memory: phase 0 still calls real C; phase 1 returns.
        code = (0xE3520001, 0x012FFF1E, 0xE59FC000, 0xE12FFF1C, original)
        cam.mu.mem_write(wrapper, struct.pack('<5I', *code))
        cam.put(slot, wrapper)
        self.commit_without_pending_assert(cam, SITES[1], 9)
        self.assertEqual(cam.w(cam.s() + V.L.S['VRATE']), 23976)
        with self.assertRaises(AssertionError):
            self.assertEqual(cam.lv, LV_CYCLE)
        self.assertEqual(cam.w(cam.s() + V.L.S['RATE_LVOWED']), 8)

    def commit_without_pending_assert(self, cam, site, row):
        var = V.RC.KEYBUF + 0x900
        cam.put(var + 8, row)
        result = cam.callr(site, r0=var, sp=V.T.STACK - 0x1000)
        self.assertEqual(result['r0'], 0x55)


if __name__ == '__main__':
    unittest.main()
