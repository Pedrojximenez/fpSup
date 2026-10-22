"""CINE preview source guards and read-only boundaries; no camera/socket I/O."""
import tempfile
from pathlib import Path
import unittest
from unittest import mock

import af_cine_baseline as cine
from test_af_native_preflight import FakeIO


class CineIO(FakeIO):
    def __init__(self):
        super().__init__()
        for _, address, count in (*cine.IDENTITY_RANGES, *cine.WATCH_RANGES):
            for index in range(count):
                self.memory.setdefault(address+4*index, 0)
        for name, address, count in cine.IDENTITY_RANGES:
            if name.endswith("guard"):
                self.memory[address] = 1
        self.memory.update({0xC31C01B0: 1, 0xC31F86E0: 1, 0xC31F8698: 0xC090EF10,
                            0xC3075230: 0x41123400, 0xC35A8F40: 0x41123400,
                            0xC35A8F44: 0xC31F869C})


class CineTests(unittest.TestCase):
    def setUp(self):
        guard = mock.patch("focus_bridge.socket.socket", side_effect=AssertionError("socket forbidden"))
        guard.start()
        self.addCleanup(guard.stop)
        self.io = CineIO()
        self.events = []

    def run_probe(self, **kwargs):
        return cine.collect(self.io, self.events.append, samples=2, sleep=lambda _: None, **kwargs)

    def test_verified_read_only_baseline_does_not_authorize_focus(self):
        result = self.run_probe()
        self.assertEqual(result["status"], "read-complete")
        self.assertTrue(result["cine_baseline_verified"])
        self.assertEqual(result["settings"], result["settings_after"])
        self.assertEqual(len(result["observations"]), 2)
        for field in ("source_coherence_verified", "optical_focus_confirmed",
                      "continuous_af_activity_proven", "recorded_stream_test",
                      "geometry_eligible", "motion_authorized", "pointer_chasing_performed"):
            self.assertFalse(result[field])
        for _, command, _ in self.io.calls:
            self.assertNotRegex(command, r"key |mem set|echo|alloc|SetFocusMode [0-9]")
        for row in self.events:
            if row.get("event") == "memory_chunk":
                self.assertLessEqual(len(row["words"]), 8)

    def test_public_probe_defaults_to_one_sample(self):
        result = cine.probe(self.io)
        self.assertEqual(len(result["observations"]), 1)

    def test_no_ram_pointer_is_dereferenced(self):
        self.io.memory[0xC3075230] = 0x4ABCDEF0
        self.io.memory[0xC35A8F40] = 0x4ABCDEF0
        self.run_probe()
        self.assertFalse(any("4ABCDEF0" in line for _, line, _ in self.io.calls))

    def test_unknown_build_rejected_before_new_ranges(self):
        self.io.version = "unknown"
        with self.assertRaises(cine.BaselineError) as caught:
            self.run_probe()
        self.assertFalse(caught.exception.result["cine_baseline_verified"])
        self.assertFalse(any("C31F8858" in line for _, line, _ in self.io.calls))

    def test_stored_or_applied_still_rejected(self):
        for address in (0xC31C01B0, 0xC31F86E0):
            self.io = CineIO()
            self.io.memory[address] = 0
            with self.subTest(address=address), self.assertRaises(cine.BaselineError):
                self.run_probe()

    def test_all_initialization_guards_required(self):
        for name, address, _ in cine.IDENTITY_RANGES:
            if name.endswith("guard"):
                self.io = CineIO()
                self.io.memory[address] = 0
                with self.subTest(name=name), self.assertRaises(cine.BaselineError):
                    self.run_probe()

    def test_destination_or_source_mismatch_rejected_without_following(self):
        for address in (0xC35A8F40, 0xC35A8F44, 0xC31F8698):
            self.io = CineIO()
            self.io.memory[address] = 0x4ABCDEF0
            with self.subTest(address=address), self.assertRaises(cine.BaselineError):
                self.run_probe()
            self.assertFalse(any("4ABCDEF0" in line for _, line, _ in self.io.calls))

    def test_capture_busy_recording_or_shutter_rejected(self):
        for address in (0xC30338C8, 0xC30338D0, 0xC3033A6C):
            self.io = CineIO()
            self.io.memory[address] = 1
            with self.subTest(address=address), self.assertRaises(cine.BaselineError):
                self.run_probe()

    def test_recording_neighbor_byte_does_not_invalidate(self):
        self.io.memory[0xC30338D0] = 0x10000
        self.assertTrue(self.run_probe()["cine_baseline_verified"])

    def test_preaf_byte_is_not_proof_of_continuous_activity(self):
        self.io.memory[0xC31F885C] = 0xABCD0101
        result = self.run_probe()
        for row in result["observations"]:
            self.assertEqual(row["raw_interpretation"]["effective_full_time_preaf_byte"], 1)
        self.assertFalse(result["continuous_af_activity_proven"])

    def test_changed_mode_after_samples_rejected(self):
        def emit(row):
            self.events.append(row)
            if row.get("event") == "observation":
                self.io.memory[0xC31C01B0] = 0
        with self.assertRaises(cine.BaselineError) as caught:
            cine.collect(self.io, emit, samples=1)
        self.assertFalse(caught.exception.result["cine_baseline_verified"])

    def test_changed_settings_after_samples_rejected(self):
        def emit(row):
            if row.get("event") == "observation":
                self.io.replies["menu SetFocusMode"] = "2"
        with self.assertRaises(cine.BaselineError):
            cine.collect(self.io, emit, samples=1)

    def test_transport_fault_latch_stops_additional_reads(self):
        def emit(row):
            if row.get("event") == "observation":
                self.io._latch_transport_fault()
        with self.assertRaises(cine.BaselineError) as caught:
            cine.collect(self.io, emit, samples=2, sleep=lambda _: None)
        self.assertTrue(caught.exception.result["transport_faulted"])
        self.assertEqual(len(caught.exception.result["observations"]), 1)

    def test_invalid_sample_count_no_io(self):
        for value in (0, 17, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cine.collect(self.io, samples=value)
        self.assertEqual(self.io.calls, [])

    def test_cli_requires_live_flag(self):
        with tempfile.TemporaryDirectory() as path:
            dest = Path(path)/"test.jsonl"
            with self.assertRaises(SystemExit):
                cine.main(["--output", str(dest)])
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
