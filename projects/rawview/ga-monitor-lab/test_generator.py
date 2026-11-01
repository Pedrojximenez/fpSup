#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-only tests; no firmware, LUT or derivative data fixture is needed."""
import math
import struct
import unittest
import build as B


class GeneratorTests(unittest.TestCase):
    def test_pins_reject_wrong_baseline_and_cube(self):
        with self.assertRaises(ValueError):
            B.build_all(bytes(38644), b'not a cube')
        with self.assertRaises(ValueError):
            B.neutral_axis(b'LUT_3D_SIZE 33\n')

    def test_lift2_domain_and_anchors(self):
        for x in (-1, 8171, math.nan, math.inf):
            with self.subTest(x=x), self.assertRaises(ValueError):
                B.lift2(x)
        for x in (0, B.GRAY, B.LIMIT):
            self.assertEqual(B.lift2(x), x)
        self.assertAlmostEqual(B.lift2(B.GRAY/4)-B.GRAY/4, 350)

    def test_lift2_entire_domain(self):
        before = -1
        for c in range(8171):
            out = round(B.lift2(c))
            self.assertLessEqual(before, out)
            self.assertLessEqual(c, out)
            self.assertLessEqual(out-c, 350)
            self.assertLessEqual(out, 8170)
            if c >= B.GRAY:
                self.assertEqual(c, out)
            before = out

    def test_lift2_independent_polynomial_dense(self):
        factor = 350*256/27/B.GRAY
        self.assertGreater(1-factor/4, 0)
        for i in range(10001):
            c = i*B.GRAY/10000
            t = c/B.GRAY
            reference = c+(350*256/27)*(t-3*t*t+3*t**3-t**4)
            self.assertAlmostEqual(B.lift2(c), reference, places=9)

    def test_rows_only_and_highlights_exact_with_synthetic_data(self):
        # Distinct sentinels catch accidental writes into SAT, CM or code.
        data = bytes((i*37) % 256 for i in range(38776))
        row = [min(8170, round(i*8170/145)) for i in range(146)]
        data = B.set_rows(data, row)
        out = B.rewrite_rows(data, B.lift2)
        self.assertNotEqual(data, out)
        self.assertEqual(data[:B.ROW_BASE], out[:B.ROW_BASE])
        self.assertEqual(data[B.ROW_END:], out[B.ROW_END:])
        for i in range(31):
            actual = struct.unpack_from('<146H', out, B.ROW_BASE+i*B.STRIDE)
            for x, y in zip(row, actual):
                if x >= B.GRAY:
                    self.assertEqual(x, y)

    def test_preview_q9_preserves_neutrals_and_source(self):
        data = bytearray(38644)
        for level, matrix in enumerate(((512,0,0,512,0,0,512,0,0), (706,-298,104,627,-50,-65,706,31,-225))):
            struct.pack_into('<I9hH', data, 0x1374+24*level, 0x24, *matrix, 0)
        original = bytes(data)
        tables = B.preview_tables(data)
        self.assertEqual(bytes(data), original)
        self.assertEqual(len(tables), 48)
        for offset in (0, 24):
            rec = struct.unpack_from('<I9hH', tables, offset)
            self.assertEqual(rec[0], 0x24)
            for start in (1, 4, 7):
                self.assertEqual(sum(rec[start:start+3]), 512)
        self.assertNotEqual(tables, data[0x1374:0x13A4])

    def test_interpolation_and_calibration(self):
        self.assertEqual(B.interpolate([0,1], 0), 0)
        self.assertEqual(B.interpolate([0,1], 1), 1)
        self.assertAlmostEqual(B.interpolate([0,1], .27), .27)
        for x in (-.1, 1.1, math.nan):
            with self.assertRaises(ValueError):
                B.interpolate([0,1], x)
        for c in range(8171):
            self.assertEqual(B.encode(B.decode(c)), c)


if __name__ == '__main__':
    unittest.main(verbosity=2)
