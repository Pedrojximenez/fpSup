#!/usr/bin/env python3
"""Offline tests for the evidence ledger generator."""
import json
import pathlib
import tempfile
import unittest

import evidence_ledger as ledger

ROOT = pathlib.Path(__file__).resolve().parents[3]


def spec(**overrides):
    base = {
        "kind": "offline_unit",
        "operator_scope": "offline; no camera",
        "camera": {"model": "w71c1", "firmware": "5.02.0.V91"},
        "source": ["fpSup/raw/lossless_codec/probe_placement.py"],
        "explicitly_established": [{"level": "H", "claim": "the suite passes"}],
        "explicitly_not_established": ["anything on the camera"],
    }
    base.update(overrides)
    return base


class SchemaTests(unittest.TestCase):
    def test_builds_and_binds_sources_to_hashes(self):
        entry = ledger.build(spec(), ROOT)
        self.assertEqual(entry["schema_version"], ledger.SCHEMA_VERSION)
        files = entry["source"]["files"]
        self.assertEqual(len(files), 1)
        digest = next(iter(files.values()))
        self.assertEqual(len(digest), 64)
        actual = (ROOT / next(iter(files))).read_bytes()
        import hashlib
        self.assertEqual(digest, hashlib.sha256(actual).hexdigest())

    def test_every_required_field_is_required(self):
        for field in ledger.REQUIRED:
            broken = {k: v for k, v in spec().items() if k != field}
            with self.assertRaises(ledger.LedgerError, msg=field):
                ledger.build(broken, ROOT)

    def test_a_boundary_is_mandatory(self):
        """An entry that claims no limits is the failure this exists to stop."""
        with self.assertRaises(ledger.LedgerError):
            ledger.build(spec(explicitly_not_established=[]), ROOT)

    def test_claims_carry_an_evidence_level(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.build(spec(explicitly_established=[{"claim": "no level"}]), ROOT)
        with self.assertRaises(ledger.LedgerError):
            ledger.build(spec(explicitly_established=[
                {"level": "LIVE", "claim": "wrong tag"}]), ROOT)
        for level in sorted(ledger.LEVELS):
            entry = ledger.build(spec(explicitly_established=[
                {"level": level, "claim": "x"}]), ROOT)
            self.assertEqual(entry["explicitly_established"][0]["level"], level)

    def test_missing_source_file_is_refused(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.build(spec(source=["no/such/file.py"]), ROOT)

    def test_optional_sections_pass_through_only_when_given(self):
        entry = ledger.build(spec(), ROOT)
        for optional in ("timing", "frames", "hook", "corrections"):
            self.assertNotIn(optional, entry)
        entry = ledger.build(spec(timing={"max_us": 18229},
                                  corrections=[{"field": "x"}]), ROOT)
        self.assertEqual(entry["timing"]["max_us"], 18229)
        self.assertEqual(len(entry["corrections"]), 1)

    def test_records_whether_the_tree_was_dirty(self):
        entry = ledger.build(spec(), ROOT)
        source = entry["source"]
        self.assertIn("git_available", source)
        self.assertIn("worktree_dirty", source)
        if source["git_available"]:
            self.assertIsInstance(source["worktree_dirty"], bool)


class ImmutabilityTests(unittest.TestCase):
    def test_existing_entries_are_never_overwritten(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "entry.json"
            spec_path = pathlib.Path(tmp) / "spec.json"
            spec_path.write_text(json.dumps(spec()))
            cmd = [sys.executable, str(pathlib.Path(ledger.__file__)),
                   str(spec_path), "--root", str(ROOT), "--out", str(out)]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue(out.is_file())
            second = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("immutable", second.stderr + second.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
