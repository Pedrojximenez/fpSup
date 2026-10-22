"""imx410_bit14: the getter hook and sl_excl ROLE 14's marker, run in Unicorn."""
import struct
import unittest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
import imx410_bit14 as BIT14
import sl_excl as SLX

STOP = 0x10000
STOCK = 0xC005BF2C          # the getter after the displaced push: we model "return VALUE"


class Bit14(unittest.TestCase):
    def setUp(self):
        self.uc = uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        uc.mem_map(0x0, 0x20000)
        uc.mem_map(0xC0000000 + 0x5B000, 0x2000)
        uc.mem_map(0xC0730000, 0x5000)
        uc.mem_map(0xC0570000, 0x20000)
        # stock getter tail: mov r0, VALUE ; pop {r4, r5, pc}
        self.value = 0

    def w(self, a, v):
        self.uc.mem_write(a, struct.pack('<I', v))

    def r(self, a):
        return struct.unpack('<I', self.uc.mem_read(a, 4))[0]

    def get(self, value, bit14, flag=1, fmt=0):
        uc = self.uc
        # stock: mov r0, #0x100 ; ldr r0, [r0] ; pop {r4, r5, pc} (the value is data:
        # rewriting an immediate would hit Unicorn's cached translation)
        uc.mem_write(STOCK, struct.pack('<III', 0xE3A00C01, 0xE5900000, 0xE8BD8030))
        self.w(0x100, value)
        blob = BIT14.blobs()['imx410_bit14_1']
        uc.mem_write(BIT14.GET_CODE, blob)
        self.w(BIT14.BIT14, bit14); self.w(BIT14.FLAG, flag); self.w(BIT14.FMTLATCH, fmt)
        uc.reg_write(UC_ARM_REG_SP, 0x8000); uc.reg_write(UC_ARM_REG_LR, STOP)
        uc.emu_start(BIT14.GET_CODE, STOP, count=200)
        self.assertEqual(uc.reg_read(UC_ARM_REG_SP), 0x8000)
        return uc.reg_read(UC_ARM_REG_R0)

    def test_getter(self):
        self.assertEqual(self.get(0, 1), 1)                 # CUSTOM + DNG + marker: 14
        self.assertEqual(self.get(0, 0), 0)                 # no marker: stock 12
        self.assertEqual(self.get(0, 1, flag=0), 0)         # not CUSTOM
        self.assertEqual(self.get(0, 1, fmt=1), 0)          # MOV
        for v in (3, 4):                                    # 10 / 8 bit never become 14
            self.assertEqual(self.get(v, 1), v)

    def test_setter_marker_and_pair_order(self):
        uc = self.uc
        blob = SLX.blobs()['sl_excl_14']
        uc.mem_write(SLX.DNG_CODE, blob)
        # stock callback FUN_c057a5f0+4: return 0 (pop {r4-r7, pc})
        uc.mem_write(0xC057A5F4, struct.pack('<II', 0xE3A00000, 0xE8BD80F0))
        self.w(SLX.MARK + 0x54, 0)                          # no sl_menu_live recorded
        # the notification replay: count calls (ldr r0,[pc,#4]; ldr r1,[r0]; b +; .word; add; str; bx lr)
        uc.mem_write(BIT14.NOTIFY_CODE, struct.pack('<6I', 0xE3A00C02, 0xE5901000, 0xE2811001,
                                                    0xE5801000, 0xE12FFF1E, 0))
        self.w(0x200, 0); self.w(BIT14.BIT14, 0)
        calls = 0
        for row, marker, order in ((3, 1, (3, 2)), (3, 1, (3, 2)), (2, 0, (2, 3)), (0, 0, (2, 3)), (3, 1, (3, 2))):
            was = self.r(BIT14.BIT14)
            self.uc.mem_write(BIT14.BIT_PAIR, struct.pack('<8I', 4, 0, 3, 1, 0, 2, 0, 3))
            self.w(0x9000 + 8, row)
            uc.reg_write(UC_ARM_REG_R0, 0x9000)
            uc.reg_write(UC_ARM_REG_SP, 0x8000); uc.reg_write(UC_ARM_REG_LR, STOP)
            uc.emu_start(SLX.DNG_CODE, STOP, count=400)
            self.assertEqual(self.r(BIT14.BIT14), marker)
            self.assertEqual((self.r(BIT14.BIT_PAIR + 0x14), self.r(BIT14.BIT_PAIR + 0x1C)), order)
            self.assertEqual(uc.reg_read(UC_ARM_REG_SP), 0x8000)
            calls += BIT14.WITH_NOTIFY and was != marker     # only a change is replayed
            self.assertEqual(self.r(0x200), calls)
            self.assertEqual(self.r(BIT14.PENDING), 0)

    def test_black_level_bits(self):
        uc = self.uc
        uc.mem_map(0xC02DA000, 0x1000)
        uc.mem_write(0xC02DA870, struct.pack('<I', 0xE12FFF1E))          # stock: bx lr (r0 = enum)
        uc.mem_write(BIT14.BLACK_CODE, BIT14.blobs()['imx410_bit14_3'])
        for enum, bit14, flag, fmt, want in ((0, 1, 1, 0, 1), (0, 0, 1, 0, 0), (0, 1, 0, 0, 0),
                                             (0, 1, 1, 1, 0), (3, 1, 1, 0, 3), (4, 1, 1, 0, 4)):
            self.w(BIT14.BIT14, bit14); self.w(BIT14.FLAG, flag); self.w(BIT14.FMTLATCH, fmt)
            uc.reg_write(UC_ARM_REG_R0, enum)
            uc.reg_write(UC_ARM_REG_SP, 0x8000); uc.reg_write(UC_ARM_REG_LR, STOP)
            uc.emu_start(BIT14.BLACK_CODE, STOP, count=100)
            self.assertEqual(uc.reg_read(UC_ARM_REG_R0), want, (enum, bit14, flag, fmt))
            self.assertEqual(uc.reg_read(UC_ARM_REG_SP), 0x8000)

    def test_table_hands_stock_12_for_row_3(self):
        import imx410_plan as PL
        t = struct.unpack('<8I', BIT14.pairs(PL.FIRMWARE.read_bytes()))
        self.assertEqual(t, (4, 0, 3, 1, 0, 2, 0, 3))
        self.assertNotIn(1, t[0::2])                        # eRawBitType 1 never reaches stock


if __name__ == '__main__':
    unittest.main()
