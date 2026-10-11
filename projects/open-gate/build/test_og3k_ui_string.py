"""OG3K's NBU string hook (og3k_ui.S ui_string) under unicorn.

The hook turns OpenGate's synthetic string offsets FFFFFFF2..FFFFFFF6 into its
own labels. It may only do so when the reader's pool is one those offsets were
made for: the stock pool, or a pool made by the shared convention
(fpSup/uishare: a copy of the stock pool announced by "FSPL", version 1, in the
16 bytes before it). Anything else goes to the stock resolver C05E5B58, which
is executed from the real firmware image here.

The payload is the one build_og3k_ui_candidate.build() writes; the hook's
address comes from the branch it plants at C05E5B58.
"""
import pathlib
import struct
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_ALL  # noqa: E402
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,  # noqa: E402
                               UC_ARM_REG_LR, UC_ARM_REG_SP, UC_ARM_REG_PC)

SEG0 = ROOT / 'out/seg0_c0000000.bin'
STOCK_POOL, STOCK_LEN = 0xC18C0474, 176152
RAM, RAM_SIZE = 0x10000000, 0x100000
DONE = 0x20000000
STACK = 0x30000000


def decode_thumb_bw(site, lo, hi):
    """Target of a Thumb-2 B.W at `site` (halfwords lo, hi)."""
    s = (lo >> 10) & 1
    imm10 = lo & 0x3FF
    j1, j2, imm11 = (hi >> 13) & 1, (hi >> 11) & 1, hi & 0x7FF
    i1, i2 = 1 - (j1 ^ s), 1 - (j2 ^ s)
    off = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if s:
        off -= 1 << 25
    return site + 4 + off


class UiStringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_og3k_ui_candidate as B
        cls.tmp = tempfile.TemporaryDirectory(prefix='og3k-uistring-')
        B.build(out=pathlib.Path(cls.tmp.name) / 'card')
        blob = (pathlib.Path(cls.tmp.name) / 'card' / 'fpSup.BIN').read_bytes()
        count = struct.unpack_from('<I', blob, 4)[0]
        off, sections = 16 + 8 * count, {}
        for i in range(count):
            dst, ln = struct.unpack_from('<II', blob, 16 + 8 * i)
            sections[dst] = blob[off:off + ln]
            off += ln + (-ln % 4)
        cls.code = sections[B.UI_CODE]
        cls.ui_code = B.UI_CODE
        site = sections[0xC05E5B58]
        lo, hi = struct.unpack('<HH', site[:4])
        cls.entry = decode_thumb_bw(0xC05E5B58, lo, hi)
        cls.seg0 = SEG0.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def call(self, reader_pool, reader_len, offset, header=None):
        mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.mem_map(0xC0000000, (len(self.seg0) + 0xFFF) & ~0xFFF, UC_PROT_ALL)
        mu.mem_write(0xC0000000, self.seg0)
        mu.mem_write(self.ui_code, self.code)
        mu.mem_map(RAM, RAM_SIZE, UC_PROT_ALL)
        mu.mem_map(DONE, 0x1000, UC_PROT_ALL)
        mu.mem_map(STACK - 0x10000, 0x10000, UC_PROT_ALL)
        reader = RAM + 0x100
        mu.mem_write(reader + 0x10, struct.pack('<II', reader_len, reader_pool))
        if header is not None:
            mu.mem_write(reader_pool - 16, struct.pack('<4I', *header))
        mu.reg_write(UC_ARM_REG_R0, reader)
        mu.reg_write(UC_ARM_REG_R1, offset)
        mu.reg_write(UC_ARM_REG_R2, 0x2222)
        mu.reg_write(UC_ARM_REG_LR, DONE)
        mu.reg_write(UC_ARM_REG_SP, STACK - 0x100)
        mu.emu_start(self.entry, DONE, count=20000)
        self.assertEqual(mu.reg_read(UC_ARM_REG_PC), DONE)
        self.assertEqual(mu.reg_read(UC_ARM_REG_SP), STACK - 0x100, 'stack not restored')
        return mu.reg_read(UC_ARM_REG_R0)

    def alias(self):
        a = self.call(STOCK_POOL, STOCK_LEN, 0xFFFFFFF2)
        self.assertNotEqual(a, 0)
        return a

    SHARED = RAM + 0x8000
    FSPL = (0x4C505346, 1, STOCK_LEN + 0x4000, 0)

    def test_stock_pool_gives_the_alias(self):
        self.assertTrue(self.ui_code <= self.alias() < 0xC0800000)

    def test_a_shared_pool_gives_the_same_alias(self):
        for off in range(0xFFFFFFF2, 0xFFFFFFF7):
            self.assertEqual(self.call(self.SHARED, STOCK_LEN + 90, off, self.FSPL),
                             self.call(STOCK_POOL, STOCK_LEN, off))

    def test_a_pool_without_the_header_gets_the_stock_answer(self):
        self.assertEqual(self.call(self.SHARED, STOCK_LEN + 90, 0xFFFFFFF2, (0, 0, 0, 0)), 0)

    def test_a_version_1_word_without_the_magic_gets_the_stock_answer(self):
        self.assertEqual(self.call(self.SHARED, STOCK_LEN + 90, 0xFFFFFFF2,
                                   (0x4C505347, 1, STOCK_LEN + 0x4000, 0)), 0)

    def test_a_header_of_another_version_gets_the_stock_answer(self):
        self.assertEqual(self.call(self.SHARED, STOCK_LEN + 90, 0xFFFFFFF2,
                                   (0x4C505346, 2, STOCK_LEN + 0x4000, 0)), 0)

    def test_an_unaligned_pool_gets_the_stock_answer(self):
        self.assertEqual(self.call(self.SHARED + 2, STOCK_LEN + 90, 0xFFFFFFF2, self.FSPL), 0)

    def test_ordinary_offsets_resolve_as_stock_in_any_pool(self):
        self.assertEqual(self.call(STOCK_POOL, STOCK_LEN, 1000), STOCK_POOL + 1000)
        self.assertEqual(self.call(self.SHARED, STOCK_LEN + 90, STOCK_LEN + 20, self.FSPL),
                         self.SHARED + STOCK_LEN + 20)
        self.assertEqual(self.call(self.SHARED, STOCK_LEN + 90, STOCK_LEN + 90, self.FSPL), 0)


if __name__ == '__main__':
    unittest.main()
