"""Test real firmware descriptor construction; no camera transport."""

import hashlib
import struct
import unittest

from og4k_sizes import RAW_COLUMN_ADDRESSES, RAW_STOCK, SHA256, SizingError, load_firmware
from verify_descriptor_native import NativeDescriptor, native_record_descriptor, verify, words


class DescriptorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = load_firmware()
        cls.stock = NativeDescriptor(cls.image)
        cls.stock_desc = cls.stock.construct(candidate=False)
        cls.og = NativeDescriptor(cls.image)
        cls.og_desc = cls.og.construct(candidate=True)

    def test_actual_native_factory_and_geometry_chain_executed(self):
        native_chain = {0xC04362B8, 0xC0439668, 0xC0439740, 0xC0439CC8,
                        0xC043A158, 0xC0439D18, 0xC0438B60, 0xC0438A78,
                        0xC0438018, 0xC04381E8, 0xC0438268}
        for machine in (self.stock, self.og):
            self.assertTrue(native_chain <= machine.native_entries)
            self.assertEqual(machine.mock_calls,
                             [0xC0439C10, 0xC0019DC0, 0xC001A0D8, 0xC0438980])
        self.assertIn(self.og.CODE + self.og.symbols["record_canvas"], self.og.native_entries)

    def test_native_recording_descriptor_exact_bytes_and_stock_preview(self):
        # Pin the whole native result, not only synthetic width/height fields.
        self.assertEqual(hashlib.sha256(self.stock_desc).hexdigest(),
                         "28f1f845d79d79f16b6d1d32dc224db4093faa1bf04c92f46ca54d400bd84d13")
        self.assertEqual(hashlib.sha256(self.og_desc).hexdigest(),
                         "3943058cb47da5c27dd2596feca6d1121461edec29cb89639ce1b52bb035df13")
        self.assertEqual(self.stock_desc[0x58:0xB0], self.og_desc[0x58:0xB0])
        for machine, descriptor in ((self.stock, self.stock_desc), (self.og, self.og_desc)):
            self.assertEqual(machine.recording_copy(), descriptor[:0x48])

    def test_canvas_core_private_copy_does_not_patch_firmware_tables(self):
        changed = {4 * i for i, (a, b) in enumerate(zip(self.og.stock_canvas, self.og.canvas))
                   if a != b}
        self.assertEqual(changed, set(RAW_COLUMN_ADDRESSES))
        self.assertEqual(self.og.canvas[0xF4 // 4:0xFC // 4], (6064, 3412))
        for offset, address in RAW_COLUMN_ADDRESSES.items():
            value = struct.unpack("<I", self.og.uc.mem_read(address, 4))[0]
            self.assertEqual(value, RAW_STOCK[offset])
        self.assertEqual(hashlib.sha256(self.image).hexdigest(), SHA256)

    def test_native_strip_bytes_and_public_api(self):
        self.assertEqual(self.stock.strip_bytes(), 12_551_292)
        self.assertEqual(self.og.strip_bytes(), 16_120_232)
        self.assertEqual(native_record_descriptor(self.image), self.og_desc)
        self.assertEqual(native_record_descriptor(self.image, candidate=False), self.stock_desc)

    def test_report_preserves_offline_scope_and_profile_selection_limit(self):
        report = verify(self.image)
        self.assertFalse(report["camera_accessed"])
        self.assertFalse(report["camera_ready"])
        self.assertFalse(report["profile_selection_emulated"])
        self.assertTrue(report["preview_unchanged"])
        self.assertEqual(report["og4k"]["raster"], [4016, 2676])
        self.assertEqual(report["og4k"]["raw_zoom"], [1536, 1536])
        self.assertEqual(report["og4k"]["strip_byte_count_native"], 16_120_232)

    def test_unpinned_firmware_rejected_before_native_execution(self):
        altered = bytearray(self.image)
        altered[0] ^= 1
        with self.assertRaises(SizingError):
            NativeDescriptor(bytes(altered))


if __name__ == "__main__":
    unittest.main()
