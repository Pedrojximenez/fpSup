#!/usr/bin/env python3
"""Offline tests: the camera-payload path, exercised with host-encoded bytes.

The camera dump is the one piece that needs a camera. Everything either side
of it -- finding the frame, slicing the arena, assembling, decoding, comparing
-- is tested here by standing host-encoded tiles in for the camera's.
"""
import json
import pathlib
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import canonical_header as ch
import verify_camera_payload as vcp
from tiff_guard import Rejected

FIXTURES = pathlib.Path("/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/"
                        "captures/opengate_ev_bug_20260914/dng")
STOCK = FIXTURES / "A001_083_FHD_f07.DNG"
ENCODER = pathlib.Path("/Users/dido/Developer.localized/SIGMAfp_re/research/slimRAW")


def host_payload(source):
    """Tile blobs and sizes, as the camera's arena would hold them."""
    import mkcompressed_safe as safe
    safe.configure_encoder(ENCODER)
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "trial.DNG"
        safe.build(source, out)
        data = out.read_bytes()
        tags = ch.ClassicTIFF(data).root["tags"]
        n = tags[325]["count"]
        at_off = struct.unpack("<I", tags[324]["entry"][8:12])[0]
        at_cnt = struct.unpack("<I", tags[325]["entry"][8:12])[0]
        counts = list(struct.unpack_from(f"<{n}I", data, at_cnt))
        offsets = struct.unpack_from(f"<{n}I", data, at_off)
        return b"".join(data[o:o + c] for o, c in zip(offsets, counts)), counts


class MarkerTests(unittest.TestCase):
    def setUp(self):
        if not STOCK.is_file():
            self.skipTest("stock fixture missing")

    def test_markers_are_the_words_the_probe_records(self):
        first, last = vcp.pixel_markers(STOCK.read_bytes())
        data = STOCK.read_bytes()
        self.assertEqual(first, struct.unpack_from("<I", data, 0x13400)[0])
        self.assertEqual(last, struct.unpack_from("<I", data, 0x13400 + 0x304CB0 - 4)[0])

    def test_frame_is_found_by_its_markers_not_by_order(self):
        first, last = vcp.pixel_markers(STOCK.read_bytes())
        found = vcp.find_frame(FIXTURES, first, last)
        self.assertEqual(found, STOCK)

    def test_absent_markers_refuse_rather_than_guess(self):
        with self.assertRaises(Rejected):
            vcp.find_frame(FIXTURES, 0xDEADBEEF, 0xFEEDFACE)


class SliceTests(unittest.TestCase):
    def test_short_payload_refused(self):
        with self.assertRaises(Rejected):
            vcp.slice_tiles(b"\x00" * 10, [4, 8])

    def test_trailing_bytes_are_ignored_not_appended(self):
        blobs, used = vcp.slice_tiles(b"\x01" * 20, [4, 8])
        self.assertEqual([len(b) for b in blobs], [4, 8])
        self.assertEqual(used, 12)


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        if not STOCK.is_file() or not (ENCODER / "ljenc.py").is_file():
            self.skipTest("fixture or encoder missing")
        try:
            import numpy, rawpy  # noqa: F401
        except ImportError:
            self.skipTest("rawpy/numpy not available")

    def test_a_payload_plus_the_contract_decodes_sample_exact(self):
        payload, sizes = host_payload(STOCK)
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "assembled.DNG"
            blob, used = vcp.assemble(STOCK, payload, sizes)
            out.write_bytes(blob)
            self.assertEqual(used, sum(sizes))
            report = vcp.compare(STOCK, out)
            self.assertEqual(report["samples"], 2110240)
            self.assertTrue(report["samples_equal"])
            self.assertEqual(report["source_sample_sha256"],
                             report["decoded_sample_sha256"])

    def test_a_corrupted_payload_is_caught_by_the_comparison(self):
        """The point of decoding is to catch a wrong bitstream."""
        payload, sizes = host_payload(STOCK)
        broken = bytearray(payload)
        broken[len(broken) // 2] ^= 0xFF
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "assembled.DNG"
            blob, _ = vcp.assemble(STOCK, bytes(broken), sizes)
            out.write_bytes(blob)
            try:
                report = vcp.compare(STOCK, out)
            except Exception:
                return          # refusing to decode is also a catch
            self.assertFalse(report["samples_equal"],
                             "a flipped payload byte decoded as the original")

    def test_decoding_does_not_validate_the_tile_table(self):
        """Measured on 2026-09-23, and the reason framing is checked.

        Shifting the declared boundary by 16 bytes leaves every sample equal:
        each tile is a whole SOI..EOI stream and LibRaw resynchronises on SOI.
        A successful decode therefore says nothing about the table.
        """
        payload, sizes = host_payload(STOCK)
        shifted = list(sizes)
        shifted[0] += 16
        shifted[-1] -= 16
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "raw_assembled.DNG"
            built = ch.build(STOCK.read_bytes()[:ch.IFD_AT], shifted, 512, 368)
            seg0 = bytearray(built["segment0"])
            struct.pack_into("<I", seg0, 4, built["root_pointer"])
            blobs, _ = vcp.slice_tiles(payload, shifted)
            out.write_bytes(bytes(seg0) + b"".join(blobs))
            report = vcp.compare(STOCK, out)
            self.assertTrue(report["samples_equal"],
                            "if this ever fails, LibRaw stopped resynchronising")

    def test_framing_is_what_catches_a_wrong_tile_table(self):
        payload, sizes = host_payload(STOCK)
        shifted = list(sizes)
        shifted[0] += 16
        shifted[-1] -= 16
        with self.assertRaises(Rejected):
            vcp.check_tile_framing(payload, shifted)
        # the correct table frames cleanly
        report = vcp.check_tile_framing(payload, sizes)
        self.assertEqual(len(report), len(sizes))
        self.assertEqual(report[0]["at"], 0)

    def test_assemble_refuses_a_payload_that_does_not_frame(self):
        payload, sizes = host_payload(STOCK)
        with self.assertRaises(Rejected):
            vcp.assemble(STOCK, b"\x00" * len(payload), sizes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
