#!/usr/bin/env python3
"""Host-only safety checks for the optional Unicorn receiver verifier."""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

import raw14_2x_plan as plan
import verify_receiver_native as native


class NativeVerifierStaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.firmware = plan.Firmware()

    def test_synthetic_config_is_deterministic_and_nonzero(self):
        self.assertEqual(len(native.SYNTHETIC_CONFIG), 0x3C)
        self.assertGreater(len(set(native.SYNTHETIC_CONFIG)), 32)
        self.assertTrue(all(value != 0 for value in native.SYNTHETIC_CONFIG))
        self.assertEqual(
            native.sha256_bytes(native.SYNTHETIC_CONFIG),
            "e1cc6ba7bf322dcc40ab47273a6839e365e8a5efac089bff5c17b766dfff59c0",
        )

    def test_candidate_receiver_overlay_is_strictly_validated(self):
        patches = plan._hybrid_receiver_patches(self.firmware)
        validated = native.validate_receiver_patches(
            self.firmware, plan.M141, patches
        )
        self.assertEqual(validated, tuple(patches))
        self.assertEqual(len(validated), 6)

    def test_rejects_wrong_expected_value(self):
        patch = plan._hybrid_receiver_patches(self.firmware)[0]
        bad = plan.Patch(
            patch.address,
            patch.expected ^ 1,
            patch.replacement,
            patch.region,
            patch.reason,
        )
        with self.assertRaisesRegex(ValueError, "firmware has"):
            native.validate_receiver_patches(self.firmware, plan.M141, [bad])

    def test_rejects_duplicate_unaligned_id_and_other_row_writes(self):
        patch = plan._hybrid_receiver_patches(self.firmware)[0]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            native.validate_receiver_patches(
                self.firmware, plan.M141, [patch, patch]
            )

        unaligned = plan.Patch(
            patch.address + 1,
            patch.expected,
            patch.replacement,
            patch.region,
            patch.reason,
        )
        with self.assertRaisesRegex(ValueError, "unaligned"):
            native.validate_receiver_patches(
                self.firmware, plan.M141, [unaligned]
            )

        base = self.firmware.receiver_address(plan.M141)
        identity = plan.Patch(base, plan.M141, plan.M143, "test", "must reject")
        with self.assertRaisesRegex(ValueError, "outside M141 non-ID fields"):
            native.validate_receiver_patches(
                self.firmware, plan.M141, [identity]
            )

        other = plan.Patch(
            self.firmware.receiver_address(plan.M143) + 4,
            self.firmware.word(self.firmware.receiver_address(plan.M143) + 4),
            0,
            "test",
            "must reject",
        )
        with self.assertRaisesRegex(ValueError, "outside M141 non-ID fields"):
            native.validate_receiver_patches(self.firmware, plan.M141, [other])

    def test_native_lookup_return_site_is_pinned(self):
        # C0320ACC is the BL to C0320F60; C0320AD0 is where R0 contains its
        # returned table index before the receiver builder consumes it.
        self.assertEqual(self.firmware.word(0xC0320ACC), 0xEB000123)
        self.assertEqual(native.NATIVE_MODE_LOOKUP, 0xC0320F60)
        self.assertEqual(native.NATIVE_MODE_LOOKUP_RETURN, 0xC0320AD0)
        self.assertEqual(self.firmware.mode_index[plan.M141], 54)
        self.assertEqual(self.firmware.mode_index[plan.M143], 56)

    def test_verifier_has_no_camera_or_network_backend(self):
        source = Path(native.__file__).read_text()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {
            "ctypes",
            "hid",
            "http",
            "paramiko",
            "pexpect",
            "requests",
            "serial",
            "socket",
            "ssl",
            "subprocess",
            "urllib",
            "usb",
        }
        self.assertTrue(forbidden.isdisjoint(imported))
        for token in ("fpsh", "callfn", "livepatch", "write32"):
            self.assertNotIn(token, source.lower())

    def test_checked_native_report_is_bound_to_current_inputs(self):
        report_path = Path(native.__file__).with_name("receiver_native_report.json")
        report = json.loads(report_path.read_text())
        inputs = report["inputs"]
        self.assertTrue(report["native_report_verified"])
        self.assertTrue(report["source_model_match"])
        self.assertFalse(report["camera_touched"])
        self.assertEqual(inputs["firmware_sha256"], self.firmware.sha256)
        self.assertEqual(inputs["mode_csv_sha256"], self.firmware.mode_csv_sha256)
        self.assertEqual(
            inputs["register_order_sha256"], self.firmware.register_order_sha256
        )
        self.assertEqual(inputs["planner_sha256"], native.sha256_path(Path(plan.__file__)))
        self.assertEqual(inputs["verifier_sha256"], native.sha256_path(Path(native.__file__)))
        bundle = native.sha256_bytes(
            json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
        )
        self.assertEqual(report["verification_bundle_sha256"], bundle)
        self.assertEqual(
            [(item["requested_mode"], item["native_index"], item["hit"]) for item in report["cases"]],
            [(plan.M143, 56, True), (plan.M141, 54, True)],
        )


if __name__ == "__main__":
    unittest.main()
