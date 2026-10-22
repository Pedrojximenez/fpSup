#!/usr/bin/env python3
"""Project integration checks for the OG4K full-height transplant, host only."""

from __future__ import annotations

import dataclasses
import json
import struct
import unittest
from pathlib import Path

import verify_frontend as verify


class FrontendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.firmware = verify.evidence.Firmware()
        cls.overlay = verify.make_overlay(cls.firmware)

    def test_complete_transplant_preserves_exact24_and_sensor_words(self):
        report = verify.static_checks(self.firmware, self.overlay)
        self.assertEqual(report["modified_words"], 10)
        self.assertEqual(report["timing"]["fps"], 24)
        self.assertEqual(report["timing"]["frame_cycles"], 3_000_000)
        self.assertEqual(report["source_index"], 64)
        self.assertEqual(report["donor_index"], 3)

    def test_rejects_missing_extra_reordered_and_altered_patch(self):
        patches = verify.candidate.FRONTEND_PATCHES
        mutations = (
            patches[:-1],
            (*patches, patches[0]),
            tuple(reversed(patches)),
            (dataclasses.replace(patches[0], expected=patches[0].expected ^ 1), *patches[1:]),
            (dataclasses.replace(patches[0], replacement=patches[0].replacement ^ 1), *patches[1:]),
        )
        for mutation in mutations:
            with self.subTest(patches=mutation):
                with self.assertRaisesRegex(ValueError, "complete reviewed"):
                    verify.make_overlay(self.firmware, mutation)

    def test_donor_nominal_fps_copy_is_detected(self):
        image = bytearray(self.overlay.image)
        address = self.firmware.metadata_address(151) + 0x40
        struct.pack_into("<I", image, address - verify.evidence.ROM_BASE, 30)
        changed = dataclasses.replace(self.overlay, image=bytes(image))
        with self.assertRaisesRegex(AssertionError, "metadata donor differences"):
            verify.static_checks(self.firmware, changed)

    def test_donor_timing_copy_is_detected(self):
        image = bytearray(self.overlay.image)
        target = self.firmware.timing_address(151)
        for offset in (4, 8):
            word = self.firmware.word(self.firmware.timing_address(3) + offset)
            struct.pack_into("<I", image, target + offset - verify.evidence.ROM_BASE, word)
        changed = dataclasses.replace(self.overlay, image=bytes(image))
        with self.assertRaisesRegex(AssertionError, "timing donor differences"):
            verify.static_checks(self.firmware, changed)

    def test_checked_report_matches_current_firmware_and_sources(self):
        report = json.loads(Path(verify.__file__).with_name("frontend_report.json").read_text())
        self.assertTrue(report["native_report_verified"])
        self.assertFalse(report["camera_touched"])
        expected = {
            "firmware_sha256": self.firmware.sha256,
            "overlay_sha256": verify.sha256(self.overlay.image),
            "mode_csv_sha256": self.firmware.mode_csv_sha256,
            "og4k_plan_sha256": verify.sha256(Path(verify.candidate.__file__).read_bytes()),
            "firmware_model_sha256": verify.sha256(Path(verify.evidence.__file__).read_bytes()),
            "native_emulator_sha256": verify.sha256(Path(verify.native.__file__).read_bytes()),
            "verifier_sha256": verify.sha256(Path(verify.__file__).read_bytes()),
        }
        self.assertEqual(report["inputs"], expected)
        bundle = verify.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":")).encode())
        self.assertEqual(report["verification_bundle_sha256"], bundle)

    @unittest.skipIf(verify.native.unicorn is None, "optional Unicorn dependency unavailable")
    def test_native_receiver_arguments_equal_m3(self):
        report = verify.native_checks(self.firmware, self.overlay)
        self.assertEqual([r["native_index"] for r in report["lookups"]], [64, 3, 64])
        self.assertEqual([c["name"] for c in report["consumers"]], ["A", "B"])
        for consumer in report["consumers"]:
            self.assertEqual(consumer["argument_bytes"], 68)
            self.assertTrue(consumer["native_m3_equal"])
            self.assertTrue(consumer["source_model_equal"])

    @unittest.skipIf(verify.native.unicorn is None, "optional Unicorn dependency unavailable")
    def test_each_receiver_word_is_required_by_native_builder(self):
        native = verify.native
        base = self.firmware.receiver_address(151)
        patches = tuple(p for p in verify.candidate.FRONTEND_PATCHES if base < p.address < base + 0x38)
        self.assertEqual(len(patches), 4)
        expected = native.emulate(self.firmware, 3)["calls"]
        for omitted in patches:
            with self.subTest(omitted=f"0x{omitted.address:08X}"):
                partial = [p for p in patches if p != omitted]
                actual = native.emulate(self.firmware, 151, partial)["calls"]
                for before, after in zip(expected, actual):
                    self.assertNotEqual(before["argument"], after["argument"])


if __name__ == "__main__":
    unittest.main()
