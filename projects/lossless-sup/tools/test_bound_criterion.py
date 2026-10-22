#!/usr/bin/env python3
"""The bound criterion, and the encoder it rests on.

The verdict tests are the point: each one takes a record that would otherwise
read as a pass and requires a refusal. A criterion that cannot refuse is not a
criterion.
"""
import copy
import json
import pathlib
import struct
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bound_criterion as bound

PROBE = (pathlib.Path(__file__).resolve().parents[3]
         / "fpSup" / "raw" / "lossless_codec"
         / "single_frame_encode_discard_probe.S")
GUARD = 0xA55AA55A


class SourceTests(unittest.TestCase):

    def test_the_generator_matches_the_arm_fill_loop_constants(self):
        """If the probe's constants change, the host is encoding a different
        pattern than the camera generated, and the demand says nothing."""
        source = PROBE.read_text()
        self.assertIn(f"LDA     r7, 0x{bound.LCG_SEED:08X}", source)
        self.assertIn(f"LDA     r2, {bound.LCG_MUL}", source)
        self.assertIn(f"LDA     r3, {bound.LCG_ADD}", source)
        self.assertIn("eor     r0, r7, r7, lsr #16", source)
        self.assertIn(f".equ PROBE_DECLARED,  0x{bound.DECLARED:X}", source)

    def test_the_first_words_are_the_sequence_computed_by_hand(self):
        x = bound.LCG_SEED
        expected = []
        for _ in range(3):
            x = (x * bound.LCG_MUL + bound.LCG_ADD) & 0xFFFFFFFF
            expected.append(x ^ (x >> 16))
        got = struct.unpack("<3I", bound.generate_source(12))
        self.assertEqual(list(got), expected)

    def test_the_source_is_the_length_the_engine_reads(self):
        self.assertEqual(bound.SOURCE_BYTES, 0x304CB0)
        self.assertEqual(len(bound.generate_source()), bound.SOURCE_BYTES)
        self.assertEqual(bound.DECLARED,
                         (bound.SOURCE_BYTES + 0x3FF) & ~0x3FF)

    def test_unpacking_is_three_bytes_to_two_samples_high_first(self):
        data = bytes([0xAB, 0xCD, 0xEF]) * 2
        image = bound.unpack12(data, width=2, height=2)
        self.assertEqual(image[0, 0], 0xABC)
        self.assertEqual(image[0, 1], 0xDEF)

    def test_a_short_source_is_refused_rather_than_padded(self):
        with self.assertRaises(ValueError):
            bound.unpack12(b"\x00" * 30, width=100, height=100)


class EncoderTests(unittest.TestCase):
    """The encoder is imported, not reimplemented, so it gets checked here."""

    def setUp(self):
        try:
            self.ljenc, self.ljcost, self.ljpeg = bound.load_encoder()
        except ImportError as exc:                     # numpy or the encoder
            self.skipTest(f"encoder unavailable: {exc}")

    def test_a_tile_round_trips_through_the_projects_own_decoder(self):
        """Encode, decode, compare. Without this the byte counts below are the
        output of a program nothing has checked."""
        import numpy as np
        rng = np.random.default_rng(7)
        tile = rng.integers(0, 4096, size=(16, 32), dtype=np.uint16)
        blob = self.ljenc.encode_tile(tile, bound.SAMPLE_BITS, bound.PREDICTOR)
        # decode_tile returns (P, X, Y, Nf, rows) and the rows are already
        # interleaved back into CFA order, which is the layout it was handed.
        P, X, Y, Nf, rows = self.ljpeg.decode_tile(blob)
        self.assertEqual((P, Nf), (bound.SAMPLE_BITS, 2))
        rebuilt = np.array(rows, dtype=np.uint16)
        self.assertEqual(rebuilt.shape, tile.shape)
        self.assertEqual((Y, X * Nf), tile.shape)
        self.assertTrue((rebuilt == tile).all(), "the encoder is not lossless")

    def test_the_generated_pattern_demands_more_than_the_declared_length(self):
        """The measurement the whole criterion turns on."""
        demand = bound.host_demand()
        self.assertEqual(demand["tiles"], 12)
        self.assertEqual(demand["whole_tiles"], 6, "the grid does not divide")
        self.assertEqual(demand["samples_counted"], 1936 * 1090)
        self.assertTrue(demand["demand_exceeds_declared"])
        self.assertGreater(demand["encoded_bytes"], bound.DECLARED)
        self.assertGreater(demand["demand_margin_bytes"], 0)
        # An incompressible 12-bit source costs a little over 12 bits a sample:
        # the magnitude category plus its extra bits, with nothing to predict.
        self.assertGreater(demand["bits_per_sample"], 12.0)
        self.assertLess(demand["bits_per_sample"], 14.0)

    def test_the_real_encoder_and_the_cost_model_agree_closely(self):
        """They are independent implementations of the same format. Reported
        separately rather than averaged, and required to be close."""
        demand = bound.host_demand()
        gap = abs(demand["encoded_bytes"] - demand["modelled_bytes"])
        self.assertLess(gap / demand["encoded_bytes"], 0.01, "they disagree")

    def test_clipping_is_a_lower_bound_not_a_padding_assumption(self):
        """Every sample of the active area is counted once and none twice."""
        boxes, whole = bound.tile_grid()
        covered = sum((y1 - y0) * (x1 - x0) for x0, y0, x1, y1 in boxes)
        self.assertEqual(covered, bound.WIDTH * bound.HEIGHT)
        self.assertEqual(len(boxes), 12)
        self.assertEqual(whole, 6)


class VerdictTests(unittest.TestCase):
    """Each test takes a record that would read as a pass and breaks one thing."""

    DEMAND = {"demand_exceeds_declared": True, "encoded_bytes": 3_392_834,
              "source_sha256": "abc123"}

    def clean(self):
        return {"init_ret": 1, "enc_ret": 1, "size_ret": 1, "error": 0,
                "tile_sizes": [260_000] * 12, "compressed_size": 3_120_000,
                "guards": [GUARD] * 5, "variant": "bound-probe-two",
                "source_sha256": "abc123", "image_sha256": "def456"}

    def judge(self, **changes):
        record = self.clean()
        record.update(changes)
        return bound.verdict(record, copy.deepcopy(self.DEMAND))

    def test_a_clean_run_that_reached_the_limit_is_the_only_pass(self):
        out = self.judge()
        self.assertEqual(out["verdict"], "bound_enforced")
        self.assertIn("does not authorise encoding in place", out["note"])

    def test_a_missing_field_is_undecidable_not_a_refusal(self):
        record = self.clean()
        del record["guards"]
        with self.assertRaises(bound.Undecidable):
            bound.verdict(record, self.DEMAND)

    def test_an_error_word_is_not_a_pass(self):
        self.assertEqual(self.judge(error=26)["verdict"], "refused")

    def test_a_refused_call_is_not_a_pass(self):
        for call in ("init_ret", "enc_ret", "size_ret"):
            out = self.judge(**{call: 0})
            self.assertEqual(out["verdict"], "refused")
            self.assertTrue(any(call in reason for reason in out["reasons"]))

    def test_a_zero_tile_size_is_not_a_pass(self):
        sizes = [260_000] * 12
        sizes[4] = 0
        out = self.judge(tile_sizes=sizes, compressed_size=sum(sizes))
        self.assertEqual(out["verdict"], "refused")

    def test_an_accounting_discrepancy_is_not_a_pass(self):
        """The 128-byte gap in the 9/27 ledger is exactly this shape."""
        out = self.judge(compressed_size=3_120_128)
        self.assertEqual(out["verdict"], "refused")
        self.assertTrue(any("accounting discrepancy" in r for r in out["reasons"]))

    def test_unchanged_guards_alone_are_not_a_pass(self):
        """The output stopped far short, so the guards were never reached."""
        out = self.judge(tile_sizes=[50_000] * 12, compressed_size=600_000)
        self.assertEqual(out["verdict"], "refused")
        self.assertTrue(any("nothing reached them" in r for r in out["reasons"]))

    def test_a_pattern_the_limit_can_absorb_is_not_a_pass(self):
        record = self.clean()
        demand = dict(self.DEMAND, demand_exceeds_declared=False)
        out = bound.verdict(record, demand)
        self.assertEqual(out["verdict"], "refused")
        self.assertTrue(any("under any pressure" in r for r in out["reasons"]))

    def test_a_different_pattern_on_each_side_is_not_a_pass(self):
        out = self.judge(source_sha256="something else")
        self.assertEqual(out["verdict"], "refused")

    def test_a_changed_guard_is_a_result_of_its_own(self):
        guards = [GUARD] * 5
        guards[0] = 0xEEEEEEEE
        out = self.judge(guards=guards)
        self.assertEqual(out["verdict"], "bound_exceeded")
        self.assertIn("sized from a bound", out["note"])

    def test_a_far_overshoot_is_told_from_a_near_one(self):
        guards = [GUARD] * 4 + [0xEEEEEEEE]
        out = self.judge(guards=guards)
        self.assertEqual(out["verdict"], "bound_exceeded")
        self.assertTrue(any("guard 4" in r for r in out["reasons"]))

    def test_the_wrong_number_of_guards_is_not_a_pass(self):
        out = self.judge(guards=[GUARD] * 4)
        self.assertEqual(out["verdict"], "refused")


if __name__ == "__main__":
    unittest.main()
