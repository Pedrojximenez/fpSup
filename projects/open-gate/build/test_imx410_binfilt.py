"""imx410_binfilt: per-axis CRCT kernels written into the driver struct, in Unicorn."""
import struct
import unittest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_PC, UC_ARM_REG_CPSR)
import imx410_binfilt as BF
import imx410_plan as PL

PL.WITH_SL_EXCL = True
FLAG = 0xC0731C08
STRUCT = 0x9000
REC0_H, REC0_V = (16, 32, 16), (1024, 2048, 1024)


_BLOBS = {}


def blob(name):
    if not _BLOBS:
        _BLOBS.update(PL.blobs())
    return _BLOBS[name]


class BinFilt(unittest.TestCase):
    def run_role(self, role, flag, hbin, vbin, mode=0):
        site, target, code = BF.SITES[role - 1]
        uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        uc.mem_map(0, 0x20000); uc.mem_map(0xC0730000, 0x6000); uc.mem_map(0xC0635000, 0x1000)
        name = f'imx410_binfilt_{role}'
        uc.mem_write(code, blob(name))
        uc.mem_write(FLAG, struct.pack('<I', flag))
        uc.mem_write(PL.AXIS + 16, struct.pack('<I', hbin | vbin << 16))
        uc.mem_write(BF.BINFILT, struct.pack('<I', mode))
        rec = bytearray(0x34)                                  # record 0 as FUN_c032d9a0 leaves it
        struct.pack_into('<9H', rec, 8, *(REC0_V * 3))
        rec[0x1C:0x28] = bytes(REC0_H * 4); rec[0x29:0x2C] = bytes(REC0_H)
        uc.mem_write(STRUCT, bytes(rec))
        uc.mem_write(target, b'\x00\xbf\x00\xbf')              # Thumb nops: we only want to arrive
        uc.reg_write(UC_ARM_REG_R0, 7); uc.reg_write(UC_ARM_REG_R1, STRUCT)
        uc.reg_write(UC_ARM_REG_SP, 0x8000); uc.reg_write(UC_ARM_REG_LR, site + 4)
        uc.emu_start(code, target, count=300)
        self.assertEqual(uc.reg_read(UC_ARM_REG_PC), target)
        self.assertTrue(uc.reg_read(UC_ARM_REG_CPSR) & 0x20)   # arrived in Thumb
        self.assertEqual((uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1),
                          uc.reg_read(UC_ARM_REG_LR), uc.reg_read(UC_ARM_REG_SP)), (7, STRUCT, site + 4, 0x8000))
        out = bytes(uc.mem_read(STRUCT, 0x34))
        return struct.unpack_from('<9H', out, 8), tuple(out[0x1C:0x28]), tuple(out[0x29:0x2C])

    def test_kernels(self):
        for role in (1, 2):
            for kh in range(6):
                for kv in range(6):
                    for hbin, vbin in ((3, 3), (3, 1), (1, 3)):
                        v, h1, h2 = self.run_role(role, 1, hbin, vbin, mode=kh | kv << 4 | 0x100 * (kh & 1))
                        wh = BF.KERNELS[kh][1] if hbin == 3 else REC0_H
                        wv = BF.KERNELS[kv][2] if vbin == 3 else REC0_V
                        self.assertEqual(h2, wh, (role, kh, kv, hbin, vbin))
                        self.assertEqual(h1, wh * 4)
                        self.assertEqual(v, wv * 3)

    def test_stock_outside_custom(self):
        v, h1, h2 = self.run_role(1, 0, 3, 3)
        self.assertEqual((v, h1, h2), (REC0_V * 3, REC0_H * 4, REC0_H))

    def test_kernels_sum_to_unity(self):
        for name, h, v in BF.KERNELS:
            self.assertEqual((sum(h), sum(v)), (64, 4096), name)

    def test_sites_are_stock(self):
        BF.check(PL.FIRMWARE.read_bytes())


if __name__ == '__main__':
    unittest.main()
