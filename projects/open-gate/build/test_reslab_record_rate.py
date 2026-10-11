"""Execute the CinemaDNG rate getter through the real card hook and ROM.

Settings getters are modeled. This tests metadata and ABI, not DMA or storage.
"""
import struct
import unittest

import test_virtual_rcd as V
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                               UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9,
                               UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_SP)

RATE = 0xC00C9BD0
SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


class RecordRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out, cls.f = V.built()

    boot = V.VirtualTests.boot

    def camera(self):
        cam = self.boot(fr=7)
        cam.geometry(12, 992, 662)
        self.assertEqual(cam.apply(), 0)
        # Keep the installed first instruction. Execute the exact native body
        # on the pass-through path, with only the two settings getters stubbed.
        cam.mu.mem_write(RATE + 4, cam.img[RATE + 4 - 0xC0000000:0xC00C9CF0 - 0xC0000000])
        cam.test_code.update(range(RATE, 0xC00C9CF0, 4))
        cam.rate_settings = V.RC.KEYBUF + 0x3000
        for addr in (0xC0021C00, 0xC0021C40):
            code = struct.pack('<3I', 0xE59F0000, 0xE12FFF1E, cam.rate_settings)
            cam.mu.mem_write(addr, code)
            cam.by_addr.pop(addr, None)
            cam.test_code.update(range(addr, addr + len(code), 4))
        return cam

    def pick(self, cam, rank, internal=7, export=10, key=b'VRC000120'):
        cam.fr = internal
        cam.put(cam.rate_settings + 0x14, export)
        cam.put(cam.s() + V.L.S['VRATE'], rank)
        cam.mu.mem_write(V.RC.KEYBUF, key.ljust(16, b'\0'))
        hit, _ = cam.call(V.RC.PICKER, r1=V.RC.TAB3, r2=V.RC.KEYBUF)
        self.assertNotEqual(hit, 0)
        return hit

    def rate(self, cam):
        dest = V.RC.KEYBUF + 0x3104
        cam.mu.mem_write(dest - 4, b'\xa5' * 16)
        seeds = [0x76540000 + i for i in range(len(SAVED))]
        for reg, value in zip(SAVED, seeds):
            cam.mu.reg_write(reg, value)
        cam.call(RATE, r0=dest, sp=V.T.STACK - 0x1000)
        self.assertEqual([cam.r(r) for r in SAVED], seeds)
        self.assertEqual(cam.r(UC_ARM_REG_SP), V.T.STACK - 0x1000)
        self.assertEqual(bytes(cam.mu.mem_read(dest - 4, 4)), b'\xa5' * 4)
        self.assertEqual(bytes(cam.mu.mem_read(dest + 8, 4)), b'\xa5' * 4)
        self.assertEqual(cam.misaligned, [])
        return struct.unpack('<2I', cam.mu.mem_read(dest, 8))

    def test_selected_sensor_cadence_reaches_dng_rational(self):
        cam = self.camera()
        for rank, nominal, vmax in ((0, 120, 1820), (23976, 240, 910),
                                    (27972, 280, 780), (0, 120, 1820)):
            with self.subTest(rank=rank):
                hit = self.pick(cam, rank)
                self.assertEqual(cam.w(hit + V.L.ENT['W0']), 330 | (330 << 16))
                self.assertEqual(cam.w(hit + V.L.ENT['W1']) & 0xFFFF, vmax)
                self.assertEqual(self.rate(cam), (nominal * 1000, 1001))
        self.pick(cam, 1798, internal=1, export=1, key=b'VRC00023_98')
        self.assertEqual(self.rate(cam), (18000, 1001))
        cam.assert_tables(self)

    def test_unpicked_inactive_and_changed_carrier_keep_native_rate(self):
        cam = self.camera()
        self.pick(cam, 23976)
        for name, value in (('PICKOK', 0), ('FLAG', 0), ('LAST_ENT', 0), ('CUR', 0)):
            with self.subTest(guard=name):
                addr = cam.s() + V.L.S[name]
                old = cam.w(addr)
                cam.put(addr, value)
                self.assertEqual(self.rate(cam), (120000, 1001))
                cam.put(addr, old)
        # A menu change before the matching picker hit must not label a frame
        # with the newly selected rate while it still belongs to the old one.
        cam.put(cam.s() + V.L.S['VRATE'], 27972)
        self.assertEqual(self.rate(cam), (120000, 1001))
        self.pick(cam, 23976)
        cam.fr = 3
        cam.put(cam.rate_settings + 0x14, 4)
        self.assertEqual(self.rate(cam), (30000, 1001))
        self.pick(cam, 0, internal=12, export=2, key=b'VRC00024')
        self.assertEqual(self.rate(cam), (24000, 1000))

    def test_record_header_does_not_enter_interactive_settings(self):
        cam = self.camera()
        self.pick(cam, 23976)
        calls = []
        def observe(mu, address, size, data):
            if address in (0xC0057AE8, 0xC005C0F0):
                calls.append(address)
        hook = cam.mu.hook_add(UC_HOOK_CODE, observe)
        try:
            self.assertEqual(self.rate(cam), (240000, 1001))
        finally:
            cam.mu.hook_del(hook)
        self.assertEqual(calls, [], 'record-header path entered interactive settings')

    def test_hook_is_journalled_restored_and_missing_hook_is_detected(self):
        cam = self.camera()
        self.pick(cam, 27972)
        self.assertEqual(self.rate(cam), (280000, 1001))
        covered = {a + i for a, n, _ in cam.journal() for i in range(n)}
        self.assertTrue(all(RATE + i in covered for i in range(4)))
        armed = cam.w(RATE)
        cam.put(RATE, V.T.word(cam.img, RATE))
        cam.mu.ctl_remove_cache(RATE, RATE + 4)
        with self.assertRaises(AssertionError):
            self.assertEqual(self.rate(cam), (280000, 1001))
        self.assertEqual(self.rate(cam), (120000, 1001))
        cam.put(RATE, armed)
        cam.mu.ctl_remove_cache(RATE, RATE + 4)
        cam.power_off()
        self.assertEqual(cam.w(RATE), V.T.word(cam.img, RATE))


if __name__ == '__main__':
    unittest.main()
