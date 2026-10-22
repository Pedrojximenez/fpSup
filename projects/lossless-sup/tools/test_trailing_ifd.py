#!/usr/bin/env python3
"""Offline tests for the trailing-IFD layout."""
import pathlib
import struct
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import trailing_ifd as trailing
import verify_compressed_dng as verify
from tiff_guard import Rejected

FIXTURES = pathlib.Path("/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/"
                        "captures/opengate_ev_bug_20260914/dng")
STOCK = FIXTURES / "A001_083_FHD_f07.DNG"
SIZES = [101092, 132491, 134406, 91072, 107101, 146445,
         130598, 100076, 113746, 133191, 121510, 84554]


def tile(size):
    return verify.SOI_SOF3 + bytes((i * 7 + 3) & 0xFF for i in range(size - 6)) + verify.EOI


class TrailingIfdTests(unittest.TestCase):
    def setUp(self):
        if not STOCK.is_file():
            self.skipTest(f"fixture missing: {STOCK}")
        self.header = STOCK.read_bytes()[:trailing.PIXEL_OFF]
        self.payload = b"".join(tile(n) for n in SIZES)

    def test_the_payload_starts_where_the_stock_pixels_did(self):
        """This is the whole point: no 0x400 shift, so the codec's output can
        begin exactly where its source begins."""
        built = trailing.build(self.header, SIZES, 512, 368)
        offsets = struct.unpack_from("<" + "I" * 12, built["tables"], 0)
        self.assertEqual(offsets[0], trailing.PIXEL_OFF)
        self.assertEqual(trailing.PIXEL_OFF, 0x13400)
        self.assertEqual(built["ifd_at"], trailing.PIXEL_OFF + sum(SIZES))

    def test_the_header_is_not_expanded(self):
        built = trailing.build(self.header, SIZES, 512, 368)
        self.assertEqual(built["file_bytes"],
                         trailing.PIXEL_OFF + sum(SIZES) + built["trailer_bytes"])
        # the leading-IFD layout costs 79,872 of header for the same payload
        self.assertLess(built["file_bytes"], 79872 + sum(SIZES))

    def test_the_trailer_is_small_enough_to_be_worth_it(self):
        """810 bytes against a 1.4 MB copy is the entire argument for this
        layout, so the number is pinned."""
        built = trailing.build(self.header, SIZES, 512, 368)
        self.assertEqual(built["trailer_bytes"], built["ifd_size"] + 96)
        self.assertLess(built["trailer_bytes"], 1024)

    def test_the_patch_offsets_point_at_the_two_value_fields(self):
        """ifd_at moves with the payload, so the device patches tags 324 and
        325 at runtime. If these offsets were wrong it would corrupt an entry
        rather than a value, which is the kind of error that still decodes."""
        built = trailing.build(self.header, SIZES, 512, 368)
        for key, want in (("patch_offset_table_at", built["offset_table"]),
                          ("patch_count_table_at", built["count_table"])):
            at = built[key]
            got, = struct.unpack_from("<I", built["ifd"], at)
            self.assertEqual(got, want, key)
            # and the four bytes before it must be the count, not a tag
            tag, kind, n = struct.unpack_from("<HHI", built["ifd"], at - 8)
            self.assertIn(tag, (324, 325))
            self.assertEqual((kind, n), (4, 12))

    def test_it_assembles_into_a_file_that_verifies(self):
        blob, built = trailing.assemble(self.header, self.payload, SIZES, 512, 368)
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "trailing.DNG"
            path.write_bytes(blob)
            stock = pathlib.Path(tmp) / "stock.DNG"
            stock.write_bytes(self.header + bytes(16))
            result = verify.check(path, stock, header_bytes=trailing.PIXEL_OFF,
                                  ifd_at=built["ifd_at"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["payload_bytes"], sum(SIZES))

    def test_the_original_header_survives_except_the_root_pointer(self):
        blob, built = trailing.assemble(self.header, self.payload, SIZES, 512, 368)
        self.assertEqual(blob[:4], self.header[:4])
        self.assertEqual(blob[8:trailing.PIXEL_OFF], self.header[8:trailing.PIXEL_OFF])
        root, = struct.unpack_from("<I", blob, 4)
        self.assertEqual(root, built["ifd_at"])
        self.assertNotEqual(root, struct.unpack_from("<I", self.header, 4)[0])

    def test_it_refuses_a_header_of_the_wrong_length(self):
        with self.assertRaises(Rejected):
            trailing.build(self.header[:-4], SIZES, 512, 368)

    def test_it_refuses_the_wrong_tile_count_or_an_empty_tile(self):
        with self.assertRaises(Rejected):
            trailing.build(self.header, SIZES[:11], 512, 368)
        bad = list(SIZES)
        bad[3] = 0
        with self.assertRaises(Rejected):
            trailing.build(self.header, bad, 512, 368)

    def test_it_refuses_a_payload_of_the_wrong_length(self):
        with self.assertRaises(Rejected):
            trailing.assemble(self.header, self.payload[:-1], SIZES, 512, 368)


if __name__ == "__main__":
    unittest.main()
