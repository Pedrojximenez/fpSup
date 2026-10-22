#!/usr/bin/env python3
"""Offline tests for verify_compressed_dng.

The frames are synthesised from the real stock header via canonical_header, so
the header checks run against genuine camera metadata. The tile payloads are
fake but correctly framed, which is what the structural checks look at - no
encoder is needed to test the checker.
"""
import pathlib
import struct
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import canonical_header
import verify_compressed_dng as verify

FIXTURES = pathlib.Path("/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/"
                        "captures/opengate_ev_bug_20260914/dng")
STOCK = FIXTURES / "A001_083_FHD_f07.DNG"
SIZES = [100016, 99984, 100000, 100032, 99968, 100048,
         100016, 99984, 100000, 100032, 99968, 100048]


def tile(size, pad=0):
    """SOI + SOF3, filler, EOI, then `pad` zero bytes.

    The codec's reported size for a tile can exceed its bitstream - measured on
    the camera - so the padded shape has to be representable here.
    """
    body = bytes((i * 7 + 3) & 0xFF for i in range(size - 6 - pad))
    return verify.SOI_SOF3 + body + verify.EOI + bytes(pad)


def build(sizes=SIZES, *, commit_root=True, pads=None):
    original = STOCK.read_bytes()[:canonical_header.IFD_AT]
    built = canonical_header.build(original, sizes, 512, 368)
    segment0 = bytearray(built["segment0"])
    if commit_root:
        struct.pack_into("<I", segment0, 4, built["root_pointer"])
    pads = pads or [0] * len(sizes)
    payload = b"".join(tile(n, p) for n, p in zip(sizes, pads))
    return bytes(segment0) + payload, original


class VerifyCompressedDngTests(unittest.TestCase):
    def setUp(self):
        if not STOCK.is_file():
            self.skipTest(f"fixture missing: {STOCK}")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, blob, name="frame.DNG"):
        path = pathlib.Path(self.tmp.name) / name
        path.write_bytes(blob)
        return path

    def test_a_well_formed_frame_passes_every_check(self):
        blob, original = build()
        stock = self.write(original + bytes(16), "stock.DNG")
        result = verify.check(self.write(blob), stock)
        self.assertTrue(result["ok"])
        self.assertEqual(result["payload_bytes"], sum(SIZES))
        self.assertEqual(result["file_bytes"], 79872 + sum(SIZES))
        self.assertEqual(result["root_ifd_at"], 78848)
        self.assertTrue(result["original_header_preserved"])
        self.assertEqual(result["original_header_bytes_compared"], 78848 - 8)

    def test_length_and_content_must_agree(self):
        """G5 failed with every length right and every content wrong. The
        mirror image - a length that does not match the tiles - is the failure
        copy-back could produce, and it must not pass."""
        blob, _ = build()
        for delta, why in ((-1024, "truncated"), (+1024, "padded")):
            with self.subTest(why=why):
                damaged = blob[:len(blob) + delta] if delta < 0 else blob + bytes(delta)
                with self.assertRaises(verify.Rejected) as caught:
                    verify.check(self.write(damaged, f"{why}.DNG"))
                self.assertIn("Length and content disagree", str(caught.exception))

    def test_zero_padding_after_a_legal_eoi_is_accepted(self):
        """Measured on the camera 2026-09-26: tile 11 carried 457 zero bytes
        past its EOI. Requiring the tile to END with EOI rejected a frame that
        was correct, which is worse than not checking at all."""
        pads = [0] * 12
        pads[-1] = 464
        blob, _ = build(pads=pads)
        result = verify.check(self.write(blob, "padded.DNG"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["padding_bytes"], 464)
        self.assertEqual(result["tile_padding"][-1], 464)

    def test_non_zero_bytes_after_the_eoi_are_rejected(self):
        pads = [0] * 12
        pads[-1] = 16
        blob = bytearray(build(pads=pads)[0])
        blob[-1] = 0x5A                       # one byte of rubbish in the padding
        with self.assertRaises(verify.Rejected) as caught:
            verify.check(self.write(bytes(blob), "dirty.DNG"))
        self.assertIn("non-zero bytes after its EOI", str(caught.exception))

    def test_a_neighbour_needs_a_control_and_the_control_bounds_it(self):
        """After copy-back the frame's OWN original header is gone, so the only
        stock frame available is a neighbour - and neighbours legitimately
        differ in per-frame counters. The control makes that checkable without
        becoming a tolerance: the bytes that differ must be bytes two STOCK
        frames differ at, and every position is named."""
        blob, original = build()
        frame = self.write(blob)
        # two "stock" frames differing at one per-frame position
        a = bytearray(original + bytes(16)); a[0x500] = 0x11
        b = bytearray(original + bytes(16)); b[0x500] = 0x22
        stock = self.write(bytes(a), "stockA.DNG")
        control = self.write(bytes(b), "stockB.DNG")
        # without a control, any difference is refused
        with self.assertRaises(verify.Rejected):
            verify.check(frame, stock)
        # with one, the difference is explained and named
        result = verify.check(frame, stock, control)
        self.assertTrue(result["ok"])
        self.assertTrue(result["header_changes_all_per_frame"])
        self.assertEqual(result["header_positions_differing"], ["0x00500"])
        self.assertEqual(result["control_positions_differing"], ["0x00500"])

    def test_a_control_does_not_excuse_an_unexplained_change(self):
        """The control must not become a blanket tolerance."""
        blob, original = build()
        damaged = bytearray(blob)
        damaged[0x900] ^= 0xFF                 # a position the controls agree on
        a = bytearray(original + bytes(16)); a[0x500] = 0x11
        b = bytearray(original + bytes(16)); b[0x500] = 0x22
        with self.assertRaises(verify.Rejected) as caught:
            verify.check(self.write(bytes(damaged), "bad.DNG"),
                         self.write(bytes(a), "sA.DNG"),
                         self.write(bytes(b), "sB.DNG"))
        self.assertIn("0x00900", str(caught.exception))
        self.assertIn("two stock frames do NOT differ", str(caught.exception))

    def test_an_unframed_tile_is_rejected(self):
        blob, _ = build()
        for offset, why in ((79872, "start"), (len(blob) - 1, "end")):
            with self.subTest(why=why):
                damaged = bytearray(blob)
                damaged[offset] ^= 0xFF
                with self.assertRaises(verify.Rejected):
                    verify.check(self.write(bytes(damaged), f"{why}.DNG"))

    def test_a_changed_original_header_is_rejected(self):
        """The owned header is an EXPANDED copy. Every original tag, nested
        IFD and the MakerNote must survive; only offset 4 may differ."""
        blob, original = build()
        stock = self.write(original + bytes(16), "stock.DNG")
        damaged = bytearray(blob)
        damaged[1024] ^= 0xFF               # somewhere inside the original header
        with self.assertRaises(verify.Rejected) as caught:
            verify.check(self.write(bytes(damaged), "hdr.DNG"), stock)
        self.assertIn("original header changed", str(caught.exception))

    def test_an_uncommitted_root_pointer_is_rejected(self):
        """The root pointer is committed LAST. A frame that reached the card
        without it still decodes as the ORIGINAL uncompressed image, which is
        exactly the kind of silent wrong answer this project keeps hitting."""
        blob, _ = build(commit_root=False)
        with self.assertRaises(verify.Rejected) as caught:
            verify.check(self.write(blob, "uncommitted.DNG"))
        self.assertIn("root pointer", str(caught.exception))

    def test_strip_tags_must_be_gone(self):
        blob, _ = build()
        data = bytearray(blob)
        count, = struct.unpack_from("<H", data, 78848)
        # rewrite the first entry's tag as StripOffsets
        struct.pack_into("<H", data, 78848 + 2, 273)
        with self.assertRaises(verify.Rejected) as caught:
            verify.check(self.write(bytes(data), "strip.DNG"))
        self.assertIn("strip tag", str(caught.exception))
        self.assertGreater(count, 0)

    def test_a_declared_offset_that_does_not_match_is_rejected(self):
        """Declared offsets matching the actual SOI positions is the check that
        would have caught a partial copy."""
        blob, _ = build()
        data = bytearray(blob)
        tags, _ = verify.read_ifd(bytes(data), 78848)
        _, n, table = tags[verify.TILE_OFFSETS]
        self.assertEqual(n, 12)
        struct.pack_into("<I", data, table + 4, 79872)   # tile 1 points at tile 0
        with self.assertRaises(verify.Rejected) as caught:
            verify.check(self.write(bytes(data), "offset.DNG"))
        self.assertIn("declared at", str(caught.exception))

    def test_decode_reports_why_when_libraw_is_absent(self):
        blob, _ = build()
        result = verify.decode(self.write(blob))
        self.assertIn("decoded", result)
        if not result["decoded"]:
            self.assertIn("reason", result)

    def test_it_writes_nothing(self):
        blob, original = build()
        frame = self.write(blob)
        stock = self.write(original + bytes(16), "stock.DNG")
        before = (frame.read_bytes(), stock.read_bytes())
        verify.check(frame, stock)
        self.assertEqual((frame.read_bytes(), stock.read_bytes()), before)


if __name__ == "__main__":
    unittest.main()
