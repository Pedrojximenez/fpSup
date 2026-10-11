#!/usr/bin/env python3
"""Offline invariants for the RAW14+2x experiment planner."""

from __future__ import annotations

import ast
import json
import struct
import unittest
from pathlib import Path

import raw14_2x_plan as plan


def as_int(value: str) -> int:
    return int(value, 16)


def assert_reference_only(testcase: unittest.TestCase, report):
    testcase.assertEqual(report["status"], "BLOCKED_REFERENCE_ONLY")
    testcase.assertFalse(report["armable"])
    testcase.assertEqual(report["scope"], "reference_emulator_only")
    testcase.assertFalse(report["mutation_output"])
    testcase.assertFalse(report["camera_touched"])
    encoded = json.dumps(report, sort_keys=True)
    testcase.assertNotIn('"address"', encoded)
    testcase.assertNotIn("apply_transaction", report)
    testcase.assertNotIn("rollback_transaction", report)
    testcase.assertNotIn("manifest", report)


class OfflinePlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.firmware = plan.Firmware()

    def test_reference_firmware_and_table_identity(self):
        self.assertEqual(self.firmware.sha256, plan.EXPECTED_FIRMWARE_SHA256)
        self.assertEqual(len(self.firmware.mode_order), 70)
        self.assertEqual(self.firmware.mode_index[plan.M6], 5)
        self.assertEqual(self.firmware.mode_index[plan.M141], 54)
        self.assertEqual(self.firmware.mode_index[plan.M142], 55)
        self.assertEqual(self.firmware.mode_index[plan.M143], 56)
        self.assertEqual(self.firmware.sensor_address(plan.M141), 0xC0B6865C)
        self.assertEqual(self.firmware.metadata_address(plan.M141), 0xC0B5B2D8)
        self.assertEqual(self.firmware.timing_address(plan.M141), 0xC0B59BC0)
        self.assertEqual(self.firmware.receiver_address(plan.M141), 0xC0B5D208)
        self.assertEqual(self.firmware.mode_csv_sha256, plan.EXPECTED_MODE_CSV_SHA256)
        self.assertEqual(
            self.firmware.register_order_sha256,
            plan.EXPECTED_REGISTER_ORDER_SHA256,
        )
        self.assertEqual(
            self.firmware.csv_rom_crosscheck_count,
            plan.MODE_COUNT * plan.SENSOR_REGISTER_COUNT,
        )

    def test_only_true_acq_siblings_define_the_2x_core(self):
        evidence = plan.validate_reduction_evidence(self.firmware)
        self.assertEqual(evidence["sibling_pairs"], [[97, 98], [142, 143], [130, 131], [145, 146]])
        self.assertEqual(evidence["common_delta_count_including_selector"], 29)
        self.assertEqual(evidence["proven_2x_core_count_excluding_selector"], 28)
        self.assertIn("0x0056", evidence["common_registers"])
        self.assertIn("0x0057", evidence["common_registers"])
        self.assertNotIn("0x0016", evidence["common_registers"])
        counts = [
            len(plan._sensor_delta(self.firmware, one_x, two_x))
            for one_x, two_x in plan.Q12_1X_TO_2X_SIBLINGS
        ]
        self.assertEqual(counts, [30, 30, 29, 29])

    def test_reg0016_is_not_a_universal_2x_switch(self):
        changes = [
            0x0016 in plan._sensor_delta(self.firmware, one_x, two_x)
            for one_x, two_x in plan.Q12_1X_TO_2X_SIBLINGS
        ]
        self.assertEqual(changes, [True, True, False, False])

    def test_2x_core_transitions_are_identical_in_all_siblings(self):
        registers = {0x0001, *plan.PROVEN_2X_CORE}
        for register in registers:
            transitions = {
                (
                    self.firmware.sensor_register(one_x, register),
                    self.firmware.sensor_register(two_x, register),
                )
                for one_x, two_x in plan.Q12_1X_TO_2X_SIBLINGS
            }
            self.assertEqual(len(transitions), 1, f"reg 0x{register:04X}")

    def test_raw12_selector_cannot_be_labeled_raw14(self):
        with self.assertRaisesRegex(ValueError, "RAW12\\+2x"):
            plan.validate_raw14_mode_code(0x39)
        with self.assertRaisesRegex(ValueError, "RAW14\\+1x"):
            plan.validate_raw14_mode_code(0x29)
        with self.assertRaisesRegex(ValueError, "no RAW14\\+2x precedent"):
            plan.validate_raw14_mode_code(0x38)

    def test_q12_control_keeps_a_consistent_stock_pipeline(self):
        report = plan.q12_control_report(self.firmware)
        assert_reference_only(self, report)
        self.assertEqual(report["pipeline_identity"]["sensor_mode"], "M143 stock RAW12 2x")
        self.assertEqual(report["pipeline_identity"]["metadata_raw_enum"], 0)
        self.assertEqual(report["pipeline_identity"]["runtime_raw_plane_format"], 7)
        self.assertEqual(report["pipeline_identity"]["movie_gain_state"], 7)
        self.assertFalse(report["reference_overlay"]["live_addresses_included"])
        self.assertEqual(
            {item["id"] for item in report["blockers"]},
            {"bounded_record_engine", "isolated_overlay_lifecycle"},
        )

    def test_q12_18_precedes_q12_2997(self):
        first = plan.q12_control_report(self.firmware, "q12_control_18")
        second = plan.q12_control_report(self.firmware, "q12_control_2997")
        self.assertIsNone(first["prerequisite"])
        self.assertEqual(
            second["prerequisite"],
            "q12_control_18 passes in the bounded one-frame RAM sink",
        )
        self.assertAlmostEqual(first["timing"]["fps"], 18.001530130061056)
        self.assertEqual(second["timing"]["frame_cycles"], 2_402_400)

    def test_q12_report_exports_no_live_transaction(self):
        report = plan.q12_control_report(self.firmware)
        assert_reference_only(self, report)
        self.assertEqual(report["reference_overlay"]["kind"], "symbolic_timing_overlay")
        self.assertEqual(report["reference_overlay"]["base_mode"], "M143")
        self.assertEqual(
            [item["field"] for item in report["reference_overlay"]["fields"]],
            [
                "timing-row +0x04",
                "timing-row +0x08",
                "timing-row +0x0C",
                "timing-row +0x10",
            ],
        )

    def test_q12_reference_does_not_claim_publication_or_restore(self):
        report = plan.q12_control_report(self.firmware)
        self.assertEqual(
            report["reference_overlay"]["publication_and_restore"],
            "not implemented or modeled",
        )
        self.assertTrue(all(item["hard_gate"] for item in report["blockers"]))

    def test_hybrid_18p_has_m141_line_timing_and_m143_window(self):
        report = plan.hybrid_report(self.firmware, "r14x2_18")
        timing = report["timing"]
        self.assertEqual((timing["hmax"], timing["tail"], timing["vmax"]), (911, 911, 4390))
        self.assertEqual(timing["input_window"], {"x": 4, "y": 20, "x_end": 3036, "y_end": 2032})
        self.assertAlmostEqual(timing["fps"], 18.00319556721318)
        assert_reference_only(self, report)
        self.assertNotIn("M6", report["candidate_base"])

    def test_final_timing_is_exact_30000_over_1001(self):
        report = plan.hybrid_report(self.firmware, "r14x2_2997")
        timing = report["timing"]
        self.assertEqual(timing["frame_cycles"], 2_402_400)
        self.assertAlmostEqual(timing["fps"], 30_000 / 1001)
        self.assertEqual(report["prerequisite"], "physical RAW14+2x proof at 18p")

    def test_hybrid_preserves_raw14_identity_guards(self):
        report = plan.hybrid_report(self.firmware, "r14x2_18")
        assert_reference_only(self, report)
        fields = {
            (item["table"], item["field"])
            for item in report["reference_delta_model"]["deltas"]
        }
        self.assertNotIn(("sensor", "reg 0x0001"), fields)
        self.assertNotIn(("sensor", "reg 0x0016"), fields)
        self.assertNotIn(("metadata", "+0x3C"), fields)
        self.assertNotIn(("metadata", "+0x60"), fields)
        self.assertFalse(report["reference_delta_model"]["live_addresses_included"])
        self.assertFalse(report["reference_delta_model"]["shared_table_write_transaction"])
        unresolved = {item["field"] for item in report["unresolved"]}
        self.assertIn("sensor reg 0x0001", unresolved)
        self.assertIn("sensor reg 0x0016", unresolved)
        self.assertIn("metadata +0x60 readout cluster", unresolved)
        hard = {item["field"]: item["hard_gate"] for item in report["unresolved"]}
        self.assertTrue(hard["sensor reg 0x0001"])
        self.assertTrue(hard["metadata +0x60 readout cluster"])

    def test_receiver_source_model_matches_stock_m143(self):
        report = plan.hybrid_report(self.firmware, "r14x2_18")
        self.assertTrue(report["receiver_model"]["source_model_match"])
        self.assertFalse(report["receiver_model"]["native_report_verified"])
        candidate = plan._candidate_receiver_record(self.firmware)
        stock = self.firmware.bytes(self.firmware.receiver_address(plan.M143), plan.RECEIVER_STRIDE)
        self.assertNotEqual(candidate[:4], stock[:4])
        self.assertEqual(candidate[4:], stock[4:])

    def test_receiver_model_against_independent_fixture(self):
        record = bytes(range(plan.RECEIVER_STRIDE))
        config = bytes((0xA0 + index) & 0xFF for index in range(0x3C))
        expected_hex = (
            "0100060708090a0b0c0dcc19cecfd0d1d204d300d4d5d6d7"
            "10111a1b24252e2f12131c1d2627303114151e1f28293233"
            "161720212a2b343518222c36d8d9dadb00000000"
        )
        self.assertEqual(plan.receiver_argument_model(record, config).hex(), expected_hex)

    def test_raw14_width_alignment_and_capacity(self):
        report = plan.hybrid_report(self.firmware, "r14x2_18")
        pipe = report["record_pipeline"]
        packing = pipe["raw14_packing"]
        rejected = pipe["rejected_3032_width"]
        self.assertTrue(packing["accepted"])
        self.assertEqual(packing["primary_pitch_dwords"], 0x52B)
        self.assertEqual(packing["secondary_pitch_qwords"], 0x298)
        self.assertEqual(packing["dma_selector"], 1)
        self.assertFalse(rejected["accepted"])
        self.assertEqual(rejected["primary_truncated_bytes_per_row"], 2)
        with self.assertRaisesRegex(ValueError, "2 truncated bytes/row"):
            plan.require_safe_raw14_width(3032, plan.RECORD_HEIGHT)
        self.assertEqual(pipe["packed14_bytes_per_frame"], 10_636_920)
        self.assertEqual(pipe["format_code_8_payload_capacity"], 12_156_480)
        self.assertEqual(pipe["format_code_8_allocator_bytes"], 12_156_504)
        self.assertEqual(pipe["format_code_7_payload_capacity"], 9_117_360)
        self.assertEqual(pipe["format_code_7_allocator_bytes"], 9_117_384)
        self.assertEqual(pipe["format_code_7_payload_shortfall"], 1_519_560)
        self.assertGreater(pipe["format_code_8_payload_capacity"], pipe["packed14_bytes_per_frame"])
        self.assertLess(pipe["format_code_7_payload_capacity"], pipe["packed14_bytes_per_frame"])
        self.assertEqual(pipe["sensor_input"], [3032, 2012])
        self.assertEqual(pipe["record_plane"], [3024, 2010])
        self.assertEqual(pipe["active_crop"], [3008, 2000])
        required = pipe["required_runtime_values"]
        self.assertEqual(required["capture_descriptor_+0x20"], 1)
        self.assertNotIn("capture_descriptor_+0x24", required)
        self.assertEqual(required["runtime_profile_+0x80"], 10)
        self.assertEqual(required["runtime_profile_+0x84"], 8)

    def test_all_reports_are_machine_blocked(self):
        for stage in (
            "q12_control_18",
            "q12_control_2997",
            "r14x2_18",
            "r14x2_2997",
        ):
            assert_reference_only(self, plan.build_report(stage, self.firmware))

    def test_planner_has_no_live_io_imports(self):
        source = Path(plan.__file__).read_text()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden_modules = {
            "asyncio",
            "ctypes",
            "fcntl",
            "hid",
            "http",
            "os",
            "paramiko",
            "pexpect",
            "requests",
            "serial",
            "socket",
            "ssl",
            "subprocess",
            "termios",
            "urllib",
            "usb",
        }
        self.assertTrue(forbidden_modules.isdisjoint(imported))
        for token in ("fpsh", "callfn", "livepatch", "memwrite", "write32"):
            self.assertNotIn(token, source.lower())


if __name__ == "__main__":
    unittest.main()
