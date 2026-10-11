#!/usr/bin/env python3
"""Host-only contract tests for the OG4K-4000 candidate."""

from __future__ import annotations

import unittest

import og4k_plan as plan


class Og4kPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = plan.load_firmware()

    def test_pinned_firmware_and_complete_offline_validation(self):
        self.assertEqual(plan.validate(self.image), [])

    def test_exact_18_word_scope_and_stock_guards(self):
        self.assertEqual(len(plan.PATCHES), 18)
        self.assertEqual(len({patch.address for patch in plan.PATCHES}), 18)
        for patch in plan.PATCHES:
            self.assertEqual(plan.read_word(self.image, patch.address), patch.expected)
            self.assertNotEqual(patch.expected, patch.replacement)

    def test_frontend_is_derived_from_native_m3(self):
        derived = plan.derive_frontend_patches(self.image)
        self.assertEqual(
            [(p.address, p.expected, p.replacement) for p in derived],
            [(p.address, p.expected, p.replacement) for p in plan.FRONTEND_PATCHES],
        )
        self.assertTrue(plan.sensor_fingerprints_equal())

    def test_exact_24p_timing_is_retained(self):
        self.assertEqual(plan.timing(self.image), (445, 1145, 6740, 8))
        self.assertEqual(plan.frame_cycles(self.image), 3_000_000)
        self.assertEqual(plan.SENSOR_CLOCK / plan.frame_cycles(self.image), 24.0)
        timing_record = plan.TIMING_BASE + plan.mode_indices(self.image)[plan.SOURCE_MODE] * plan.TIMING_STRIDE
        touched = {patch.address for patch in plan.FRONTEND_PATCHES}
        self.assertNotIn(timing_record + 4, touched)
        self.assertNotIn(timing_record + 8, touched)

    def test_output_geometry_and_bandwidth(self):
        self.assertEqual(plan.RASTER, (4016, 2676))
        self.assertEqual(plan.ACTIVE, (4000, 2666))
        self.assertEqual(plan.CROP_ORIGIN, (8, 5))
        self.assertEqual(plan.RWZM, 1536)
        self.assertEqual(plan.packed_row_bytes(), 6024)
        self.assertEqual(plan.raw_frame_bytes(), 16_120_224)
        self.assertEqual(plan.raw_rate_bytes_per_second(), 386_885_376)
        overhead = plan.raw_rate_bytes_per_second() / plan.stock_uhd_rate_bytes_per_second() - 1
        self.assertAlmostEqual(overhead * 100, 2.85077, places=4)

    def test_each_stock_word_mismatch_is_detected(self):
        for patch in plan.PATCHES:
            with self.subTest(address=f"0x{patch.address:08X}"):
                broken = bytearray(self.image)
                offset = patch.address - plan.IMAGE_BASE
                broken[offset] ^= 1
                errors = plan.validate(bytes(broken))
                self.assertTrue(
                    any(f"0x{patch.address:08X}" in error for error in errors), errors
                )

    def test_hard_gates_prevent_accidental_camera_claim(self):
        self.assertFalse(plan.camera_ready())
        self.assertGreaterEqual(len(plan.HARD_GATES), 6)
        gates = " ".join(plan.HARD_GATES).lower()
        for required in ("private", "restore", "allocation", "playback", "warm"):
            self.assertIn(required, gates)


if __name__ == "__main__":
    unittest.main()
