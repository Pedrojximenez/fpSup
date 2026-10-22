#!/usr/bin/env python3
"""Offline tests for the compressed-DNG segment 0 contract."""
import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import canonical_header as ch
from tiff_guard import Rejected

FIXTURES = pathlib.Path("/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/"
                        "captures/opengate_ev_bug_20260914/dng")
STOCK = FIXTURES / "A001_083_FHD_f07.DNG"
# The twelve tile sizes the camera produced at 512x368 on 2026-09-23, from
# build/ledger-g2-20260923.json. Using the real ones keeps this test honest
# about the geometry the product actually targets.
LIVE_TILES = [71288, 123173, 133359, 88116, 91305, 131008,
              165622, 120042, 102725, 113451, 136318, 110089]


def stock_header():
    return STOCK.read_bytes()[:ch.IFD_AT]


class LayoutTests(unittest.TestCase):
    def setUp(self):
        if not STOCK.is_file():
            self.skipTest(f"stock fixture missing: {STOCK}")
        self.header = stock_header()

    def test_segment0_is_the_fixed_size_and_the_tables_fit(self):
        built = ch.build(self.header, LIVE_TILES, 512, 368)
        self.assertEqual(len(built["segment0"]), 79872)
        self.assertEqual(built["tables_end"] - ch.IFD_AT, 810,
                         "ROADMAP 4.4 says the IFD and two tile arrays are 810 bytes")
        self.assertLessEqual(built["tables_end"], ch.HEADER_BYTES)

    def test_original_header_survives_byte_for_byte(self):
        built = ch.build(self.header, LIVE_TILES, 512, 368)
        self.assertEqual(built["segment0"][8:ch.IFD_AT], self.header[8:ch.IFD_AT])
        self.assertEqual(built["segment0"][:4], self.header[:4])

    def test_root_pointer_is_not_committed_by_build(self):
        """It is the last write, after the tables are visible."""
        built = ch.build(self.header, LIVE_TILES, 512, 368)
        self.assertEqual(built["segment0"][4:8], self.header[4:8])
        self.assertEqual(built["root_pointer"], ch.IFD_AT)
        self.assertNotEqual(struct.unpack_from("<I", self.header, 4)[0], ch.IFD_AT)

    def test_strip_tags_removed_and_tile_tags_added(self):
        built = ch.build(self.header, LIVE_TILES, 512, 368)
        report = ch.verify(built["segment0"], self.header, LIVE_TILES, 512, 368)
        self.assertEqual(report["tiles"], 12)
        self.assertEqual(report["payload_bytes"], sum(LIVE_TILES))

    def test_payload_starts_after_the_header_and_is_not_padded(self):
        built = ch.build(self.header, LIVE_TILES, 512, 368)
        self.assertEqual(built["tile_offsets"][0], ch.HEADER_BYTES)
        for at, size, nxt in zip(built["tile_offsets"], LIVE_TILES,
                                 built["tile_offsets"][1:]):
            self.assertEqual(at + size, nxt, "a gap means padding between tiles")
        self.assertEqual(built["payload_bytes"], sum(LIVE_TILES))


class RefusalTests(unittest.TestCase):
    def setUp(self):
        if not STOCK.is_file():
            self.skipTest("stock fixture missing")
        self.header = stock_header()

    def test_wrong_header_length_refused(self):
        with self.assertRaises(Rejected):
            ch.build(self.header[:-4], LIVE_TILES, 512, 368)

    def test_bad_tile_counts_refused(self):
        for bad in ([], [0] + LIVE_TILES[1:], [-1] + LIVE_TILES[1:]):
            with self.assertRaises(Rejected):
                ch.build(self.header, bad, 512, 368)

    def test_tables_that_do_not_fit_are_refused(self):
        """Enough tiles and the arrays run past the fixed header."""
        with self.assertRaises(Rejected):
            ch.build(self.header, [1000] * 200, 512, 368)

    def test_verify_catches_a_tampered_payload_layout(self):
        built = ch.build(self.header, LIVE_TILES, 512, 368)
        blob = bytearray(built["segment0"])
        # point the second tile back inside the header
        entry = None
        tree = ch.ClassicTIFF(blob[:4] + struct.pack("<I", ch.IFD_AT) + blob[8:])
        at = struct.unpack("<I", tree.root["tags"][324]["entry"][8:12])[0]
        struct.pack_into("<I", blob, at + 4, 1024)
        with self.assertRaises(Rejected):
            ch.verify(bytes(blob), self.header, LIVE_TILES, 512, 368)

    def test_verify_catches_overlapping_tiles(self):
        built = ch.build(self.header, LIVE_TILES, 512, 368)
        blob = bytearray(built["segment0"])
        tree = ch.ClassicTIFF(blob[:4] + struct.pack("<I", ch.IFD_AT) + blob[8:])
        at = struct.unpack("<I", tree.root["tags"][324]["entry"][8:12])[0]
        struct.pack_into("<I", blob, at + 4, built["tile_offsets"][0])
        with self.assertRaises(Rejected):
            ch.verify(bytes(blob), self.header, LIVE_TILES, 512, 368)

    def test_verify_catches_a_changed_original_header(self):
        built = ch.build(self.header, LIVE_TILES, 512, 368)
        blob = bytearray(built["segment0"])
        blob[1000] ^= 0xFF
        with self.assertRaises(Rejected):
            ch.verify(bytes(blob), self.header, LIVE_TILES, 512, 368)


class BuilderAgreementTests(unittest.TestCase):
    """The host trial builder and this contract must emit the same header.

    They are two implementations of one layout: if they disagree, the camera
    writer has no single thing to match.
    """

    def test_mkcompressed_safe_header_matches(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy not available")
        if not STOCK.is_file():
            self.skipTest("stock fixture missing")
        import tempfile
        import mkcompressed_safe as safe
        encoder_dir = pathlib.Path("/Users/dido/Developer.localized/SIGMAfp_re/"
                                   "research/slimRAW")
        if not (encoder_dir / "ljenc.py").is_file():
            self.skipTest("encoder directory missing")
        safe.configure_encoder(encoder_dir)
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "built.DNG"
            info = safe.build(STOCK, out)
            produced = out.read_bytes()
            self.assertEqual(info["output_raw_offset"], ch.HEADER_BYTES)
            counts = []
            tree = ch.ClassicTIFF(produced)
            tags = tree.root["tags"]
            n = tags[325]["count"]
            at = struct.unpack("<I", tags[325]["entry"][8:12])[0]
            counts = list(struct.unpack_from(f"<{n}I", produced, at))

            built = ch.build(stock_header(), counts, 512, 368)
            mine = bytearray(built["segment0"])
            struct.pack_into("<I", mine, 4, built["root_pointer"])
            self.assertEqual(bytes(mine), produced[:ch.HEADER_BYTES],
                             "the two builders disagree on segment 0")

    def test_a_contract_built_file_decodes_sample_exact(self):
        """The contract's own output must decode, not just match a builder.

        Header equality alone would still allow a file nothing can read. This
        assembles segment 0 from the contract plus the encoder's blobs, decodes
        it with LibRaw, and compares every sample to the source.
        """
        try:
            import numpy as np
            import rawpy
        except ImportError:
            self.skipTest("rawpy/numpy not available")
        if not STOCK.is_file():
            self.skipTest("stock fixture missing")
        import tempfile
        import mkcompressed_safe as safe
        encoder_dir = pathlib.Path("/Users/dido/Developer.localized/SIGMAfp_re/"
                                   "research/slimRAW")
        if not (encoder_dir / "ljenc.py").is_file():
            self.skipTest("encoder directory missing")
        safe.configure_encoder(encoder_dir)
        with tempfile.TemporaryDirectory() as tmp:
            trial = pathlib.Path(tmp) / "trial.DNG"
            safe.build(STOCK, trial)
            data = trial.read_bytes()
            tree = ch.ClassicTIFF(data)
            tags = tree.root["tags"]
            n = tags[325]["count"]
            at_off = struct.unpack("<I", tags[324]["entry"][8:12])[0]
            at_cnt = struct.unpack("<I", tags[325]["entry"][8:12])[0]
            counts = list(struct.unpack_from(f"<{n}I", data, at_cnt))
            offsets = struct.unpack_from(f"<{n}I", data, at_off)
            blobs = [data[o:o + c] for o, c in zip(offsets, counts)]

            built = ch.build(stock_header(), counts, 512, 368)
            ch.verify(built["segment0"], stock_header(), counts, 512, 368)
            seg0 = bytearray(built["segment0"])
            struct.pack_into("<I", seg0, 4, built["root_pointer"])
            contract = pathlib.Path(tmp) / "contract.DNG"
            contract.write_bytes(bytes(seg0) + b"".join(blobs))

            # the contract does not pad; the host trial does, for its own reasons
            self.assertLess(contract.stat().st_size, trial.stat().st_size)
            with rawpy.imread(str(STOCK)) as raw:
                original = raw.raw_image.copy()
            with rawpy.imread(str(contract)) as raw:
                decoded = raw.raw_image.copy()
            self.assertEqual(original.shape, decoded.shape)
            self.assertEqual(original.size, 2110240)
            self.assertTrue(np.array_equal(original, decoded),
                            "LibRaw decoded samples differ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
