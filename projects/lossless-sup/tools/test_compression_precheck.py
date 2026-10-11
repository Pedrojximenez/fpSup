#!/usr/bin/env python3
"""Offline tests for the compression predictor.

The point of most of these is the DIRECTION of the error, not its size. A
predictor that over-estimates sends a frame down the slower but recoverable
path; one that under-estimates would send an expanding frame down a path where
being wrong destroys it. Only the second is a defect.
"""
import pathlib
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, "/Users/dido/Developer.localized/SIGMAfp_re/research/slimRAW")
import compression_precheck as pc

try:
    import numpy as np
except ImportError:                                   # pragma: no cover
    np = None


@unittest.skipIf(np is None, "numpy unavailable")
class PrecheckTests(unittest.TestCase):

    def frame(self, fill=512, shape=(1104, 2048)):
        return np.full(shape, fill, dtype=np.uint16)

    def test_category_matches_the_jpeg_definition(self):
        self.assertEqual(pc.category(0), 0)
        for d, k in ((1, 1), (-1, 1), (2, 2), (3, 2), (4, 3), (255, 8),
                     (4095, 12), (-4095, 12)):
            self.assertEqual(pc.category(d), k, f"d={d}")

    def test_huffman_lengths_are_a_real_code(self):
        """Kraft's inequality, and a single symbol still costs one bit."""
        counts = [100, 50, 25, 12, 6, 3, 1, 0, 0, 0, 0, 0, 0]
        lengths = pc.huffman_lengths(counts)
        used = [n for n, c in zip(lengths, counts) if c]
        self.assertAlmostEqual(sum(2.0 ** -n for n in used), 1.0, places=9)
        self.assertEqual(pc.huffman_lengths([7] + [0] * 12)[0], 1)
        self.assertEqual(pc.huffman_lengths([0] * 13), [0] * 13)

    def test_a_flat_frame_scores_one_bit_per_sample(self):
        """Every difference is zero, so one Huffman symbol and no magnitude
        bits. Anything else would mean the sampler is not reading what it
        thinks it is."""
        got = pc.predict(self.frame())
        self.assertEqual(got["score_bits_per_sample"], 1.0)
        self.assertEqual(got["fraction_zero"], 1.0)

    def test_noise_scores_near_the_modelled_maximum(self):
        rng = np.random.default_rng(7)
        pixels = rng.integers(0, 4096, size=(1104, 2048), dtype=np.uint16)
        got = pc.predict(pixels)
        self.assertGreater(got["score_bits_per_sample"], 12.0)
        self.assertLess(got["score_bits_per_sample"], 14.0,
                        "above 14 would exceed the bound output_bound.py uses")
        self.assertGreater(got["fraction_ge_10"], 0.5)

    def test_it_differences_against_two_columns_left_not_one(self):
        """Adjacent columns are different CFA components. A frame where the two
        components are far apart but each is constant must still look flat; if
        the sampler used x-1 it would see a huge difference on every sample."""
        pixels = np.empty((1104, 2048), dtype=np.uint16)
        pixels[:, 0::2] = 300
        pixels[:, 1::2] = 3000
        got = pc.predict(pixels)
        self.assertEqual(got["fraction_zero"], 1.0,
                         "differencing against x-1 would make this look noisy")
        self.assertEqual(got["score_bits_per_sample"], 1.0)

    def test_the_sample_is_small_and_covers_every_tile(self):
        got = pc.predict(self.frame())
        self.assertEqual(got["tiles"], 12)
        self.assertEqual(got["samples_taken"],
                         12 * pc.WINDOWS_PER_TILE * pc.ROWS_PER_WINDOW
                         * pc.SAMPLES_PER_ROW)
        self.assertLess(got["sample_fraction"], 0.01)

    def test_windows_stay_inside_the_tile_and_leave_room_for_x_minus_2(self):
        for seq in range(12):
            for x, y in pc.window_origins(512, 368, seq):
                self.assertGreaterEqual(x, 2, "needs two pixels to its left")
                self.assertLessEqual(x + pc.SAMPLES_PER_ROW, 512)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(y + pc.ROWS_PER_WINDOW, 368)

    def test_the_rotation_actually_moves_the_sample_set(self):
        """It did not. fy came from ((i + seq) % 4), which as i runs 0..3 covers
        the same four positions for every seq, so the sampler read identical
        rows on every frame. An adversarial frame - noise everywhere except
        those rows - scored a perfect 1.000 on all six seq values tried."""
        sets = [frozenset(pc.window_origins(512, 368, s)) for s in range(6)]
        self.assertEqual(len(set(sets)), 6, "every seq must sample differently")
        ys = [frozenset(y for _x, y in pc.window_origins(512, 368, s))
              for s in range(6)]
        self.assertEqual(len(set(ys)), 6, "the ROWS must move, not just columns")

    def test_it_is_blind_to_content_aligned_against_its_own_sample_rows(self):
        """THE KNOWN FAILURE, kept as a test so it cannot be forgotten.

        Noise everywhere except the rows this seq reads scores a perfect 1.000
        bits per sample - a total, confident under-estimate. That is why this
        predictor must not authorise an operation that cannot be undone: it is
        fit to choose between two recoverable paths and nothing more.
        """
        rng = np.random.default_rng(11)
        pixels = rng.integers(0, 4096, size=(1104, 2048), dtype=np.uint16)
        rows = set()
        for ty in range(1104 // 368):
            for _x, wy in pc.window_origins(512, 368, 0):
                for dy in range(pc.ROWS_PER_WINDOW):
                    rows.add(ty * 368 + wy + dy)
        for r in rows:
            pixels[r, :] = 512
        got = pc.predict(pixels, seq=0)
        self.assertEqual(got["score_bits_per_sample"], 1.0,
                         "the failure is total, and this test records it")
        # and the rotation is what limits the exposure: another seq catches it
        other = pc.predict(pixels, seq=3)
        self.assertGreater(other["score_bits_per_sample"], 12.0,
                           "a different seq must see the noise")


if __name__ == "__main__":
    unittest.main()
