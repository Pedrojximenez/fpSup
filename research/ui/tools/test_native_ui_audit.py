"""Pure parser tests; optional explicit pinned-seg0 integration tests."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_ui_audit as audit

SEG0 = None


def words(*values):
    return struct.pack(">%dI" % len(values), *values)


def record(tag, payload=b""):
    return words(tag, len(payload) + 8) + payload


class ParserTests(unittest.TestCase):
    def test_records_accept_unaligned_lengths(self):
        source = record(1, b"x") + record(2, b"yy")
        result = audit.records(source, 0, len(source))
        self.assertEqual([r.offset for r in result], [0, 9])
        self.assertEqual([r.tag for r in result], [1, 2])

    def test_bad_record_bounds_fail_closed(self):
        for source in (b"\0", words(1, 0), words(1, 7), words(1, 9)):
            with self.subTest(source=source), self.assertRaises(audit.AuditError):
                audit.records(source, 0, len(source))

    def test_u32_bounds(self):
        for offset in (-1, 1, 4):
            with self.subTest(offset=offset), self.assertRaises(audit.AuditError):
                audit.u32(b"\0" * 4, offset)

    def test_header_preserves_budget_arrays(self):
        payload = words(2, 0, 1, 99, 3, 1, 2, 0, 7, 2, 0, 1, 1, 2, 0)
        parsed = audit.parse_header(audit.Record(0, record(0x10002, payload)), str)
        self.assertEqual(parsed["component_counts"], {"99": 3})
        self.assertEqual(parsed["groups"], [[2, 0, 7]])
        self.assertEqual(parsed["clip_property_counts"], [0, 1])
        self.assertEqual(parsed["property_key_counts"], [2])
        self.assertEqual(parsed["trailing_budget"], [])

    def test_header_rejects_oversized_vector_and_trailing_data(self):
        for payload in (words(1, 0, 0xFFFFFFFF), words(1, 0, 0, 0, 0, 0, 0, 123)):
            with self.subTest(payload=payload), self.assertRaises(audit.AuditError):
                audit.parse_header(audit.Record(0, record(0x10002, payload)), str)

    def test_duplicate_objects_fail(self):
        obj = record(0x10003, words(0, 0, 0, 122, 116, 0, 0))
        with self.assertRaisesRegex(audit.AuditError, "duplicate object"):
            audit.parse_objects(audit.records(obj + obj, 0, len(obj) * 2), str)

    def test_clip_key_and_length_validation(self):
        # One visibility property, one integer key at CINE time 66.
        payload = words(0, 1, 0xFFFFFFFF, 122, 1, 1, 0, 0, 7, 0)
        payload += b"\0\0" + words(66, 1)
        clip = audit.parse_clip(audit.Record(0, record(0x1000A, payload)), str)
        self.assertEqual(clip["properties"][0]["keys"], [{"time": 66, "value": 1}])
        for malformed in (payload[:-1], payload + b"x"):
            with self.subTest(malformed=malformed), self.assertRaises(audit.AuditError):
                audit.parse_clip(audit.Record(0, record(0x1000A, malformed)), str)

    def test_mode_change_exact_reference_shape(self):
        payload = words(2, 0, 1, 0, 1) + b"\0" * 42 + words(122, 1) + b"\0" * 8
        result = audit.parse_mode_change(audit.Record(0, record(0x1000B, payload)))
        self.assertEqual(result, [[122, 1]])
        with self.assertRaises(audit.AuditError):
            audit.parse_mode_change(audit.Record(0, record(0x1000B, payload[:-1])))

    def test_wrong_input_rejected_before_extraction(self):
        with self.assertRaisesRegex(audit.AuditError, "size"):
            audit.audit_bytes(b"not a firmware")

    def test_cli_requires_explicit_input(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            audit.main([])
        self.assertEqual(exc.exception.code, 2)

    def test_cli_missing_file_has_no_json_output(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = audit.main(["--seg0", str(Path(__file__) / "not-a-directory")])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("audit failed", stderr.getvalue())


class PinnedFirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SEG0 is None:
            raise unittest.SkipTest("pass --seg0 for pinned-firmware integration tests")
        cls.source = SEG0.read_bytes()
        cls.result = audit.audit_bytes(cls.source)

    def test_pinned_fingerprints_and_counts(self):
        self.assertEqual(self.result["page"]["sha256"], audit.PAGE_SHA256)
        self.assertEqual(self.result["page"]["record_count"], 1392)
        self.assertEqual(self.result["page"]["object_count"], 193)
        self.assertEqual(self.result["audio_donor"]["sha256"], audit.DONOR_SHA256)
        self.assertEqual(self.result["audio_donor"]["record_count"], 187)
        self.assertEqual(self.result["allocation_header"]["sha256"], audit.HEADER_SHA256)

    def test_stock_cine_rows_and_capacity(self):
        self.assertEqual(self.result["b2_root"]["child_count"], 6)
        self.assertEqual([row["id"] for row in self.result["cine_rows"]], [21878, 121, 122])
        mode = self.result["mode_change"]
        self.assertEqual(mode["references"], [[117, 1], [21878, 2], [33942, 2], [120, 1], [121, 1], [122, 1]])
        self.assertEqual(mode["actual_clip_references"], 6)
        self.assertEqual(mode["allocation_budget"], [2, 0, 7])
        self.assertEqual(mode["unused_clip_reference_capacity"], 1)

    def test_full_clone_budget_is_evidence_not_deployment(self):
        donor = self.result["audio_donor"]["allocation_delta_for_unmodified_full_clone"]
        self.assertEqual(donor["objects"], 23)
        self.assertEqual(donor["source_group_budget_indexes"], list(range(41, 49)))
        self.assertEqual(len(donor["component_counts"]), 19)
        self.assertEqual(donor["component_counts"]["objectBase"], 23)
        self.assertEqual(donor["component_counts"]["animationClip"], 20)
        self.assertEqual(len(donor["property_key_counts"]), 37)
        self.assertEqual(sum(donor["property_key_counts"]), 1839)
        full = self.result["hypothetical_full_clone_budget_only"]
        self.assertEqual((full["header_length"], full["objects"], full["groups"],
                          full["clip_budget_entries"], full["property_budget_entries"]),
                         (3352, 216, 60, 200, 403))
        self.assertTrue(full["not_a_transform_or_deployment_plan"])
        self.assertFalse(any(self.result["readiness"].values()))

    def test_same_size_wrong_hash_fails(self):
        modified = bytearray(self.source)
        modified[0] ^= 1
        with self.assertRaisesRegex(audit.AuditError, "SHA-256"):
            audit.audit_bytes(modified)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--seg0", type=Path)
    args, rest = parser.parse_known_args()
    SEG0 = args.seg0
    unittest.main(argv=[sys.argv[0]] + rest)
