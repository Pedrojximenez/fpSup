"""CINE acquisition state transitions with mocked native I/O only."""
import copy
import unittest
from unittest import mock

import af_cine_acquisition_trial as trial
from test_af_native_tracking_trial import Camera, Clock
from test_af_cine_baseline import CineIO

SETTINGS = {"menu SetFocusPosition": "215 158 595 365", "menu SetFocusMode": "0",
            "menu SetFocusArea": "2", "menu SetFocusAreaSize": "3"}


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        patch = mock.patch("focus_bridge.socket.socket", side_effect=AssertionError("no live I/O"))
        patch.start()
        self.addCleanup(patch.stop)
        self.clock = Clock()
        self.io = Camera(self.clock)
        self.io.replies.update(SETTINGS)
        self.io.memory.update({0xC31C01B0: 1, 0xC31F86E0: 1})
        for _, address, count in trial.RANGES:
            for i in range(count):
                self.io.memory.setdefault(address+4*i, 0)
        original = self.io.request
        def native_keys(line, timeout=2):
            raw = original(line, timeout)
            if line.endswith("key S1ON"):
                self.io.memory[0xC3033A6C] = 1
            elif line.endswith("key S1OFF"):
                self.io.memory[0xC3033A6C] = 0
            return raw
        self.io.request = native_keys
        self.events = []

    def probe(self, io, emit):
        return dict(cine_baseline_verified=True, status="read-complete",
                    settings=copy.deepcopy(io.replies), settings_after=copy.deepcopy(io.replies))

    def run_trial(self, **kw):
        return trial.run_trial(self.io, self.events.append, probe=kw.pop("probe", self.probe),
                               clock=self.clock, sleep=self.clock.sleep, **kw)

    def failure(self, **kw):
        with self.assertRaises(trial.AcquisitionError) as caught:
            self.run_trial(**kw)
        return caught.exception.result

    def test_cine_acquisition_pairs_edges_without_setting_or_record_command(self):
        result = self.run_trial()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(self.io.edges, ["key S1ON", "key S1OFF"])
        self.assertTrue(result["settings_equal"])
        self.assertGreater(result["complete_observations"], 0)
        self.assertFalse(result["geometry_eligible"])
        self.assertFalse(result["optical_focus_confirmed"])
        for _, line, _ in self.io.calls:
            self.assertNotRegex(line, r"mem set|S2|MOV|echo|setfpos|menu .+ [0-9]")
        for event in self.events:
            if event.get("event") == "memory_chunk":
                self.assertLessEqual(len(event["words"]), 8)

    def test_integration_uses_real_cine_and_native_preflight_guards(self):
        self.io.memory.update(CineIO().memory)
        result = self.run_trial(probe=trial.baseline.probe)
        self.assertTrue(result["before"]["cine_baseline_verified"])
        self.assertTrue(result["after"]["cine_baseline_verified"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(self.io.edges, ["key S1ON", "key S1OFF"])

    def test_cine_guard_and_preexisting_press_block_new_press(self):
        for address, value in ((0xC31C01B0, 0), (0xC31F86E0, 0),
                               (0xC31AE3A8, 0), (0xC30338D0, 1),
                               (0xC30338C8, 0x100), (0xC3033A6C, 1),
                               (trial.preflight.ECHO, 0)):
            with self.subTest(address=hex(address)):
                before = self.io.memory[address]
                self.io.memory[address] = value
                self.failure()
                self.assertEqual(self.io.edges, [])
                self.io.memory[address] = before

    def test_baseline_rejection_does_not_send_keys(self):
        self.failure(probe=lambda io, emit: dict(status="read-complete", cine_baseline_verified=False))
        self.assertEqual(self.io.edges, [])

    def test_cine_change_during_hold_stops_and_releases(self):
        original = self.io.request
        def changing(line, timeout=2):
            raw = original(line, timeout)
            if line.endswith("key S1ON"):
                self.io.memory[0xC31C01B0] = 0
            return raw
        self.io.request = changing
        result = self.failure()
        self.assertTrue(result["release_transport_completed"])
        self.assertEqual(self.io.edges, ["key S1ON", "key S1OFF"])

    def test_uncertain_start_once_and_cleanup_once(self):
        self.io.edge_replies["key S1ON"] = TimeoutError("unknown start")
        result = self.failure()
        self.assertTrue(result["release_transport_completed"])
        self.assertEqual(self.io.edges, ["key S1ON", "key S1OFF"])
        self.assertEqual(self.io.after_release_exchange_count, 0)

    def test_failed_release_prevents_postcheck_and_retry(self):
        self.io.edge_replies["key S1OFF"] = TimeoutError("unknown release")
        result = self.failure()
        self.assertTrue(result["release_still_required"])
        self.assertEqual(self.io.edges, ["key S1ON", "key S1OFF"])
        self.assertEqual(self.io.after_release_exchange_count, 0)

    def test_half_press_log_failure_still_releases(self):
        def emit(row):
            if row.get("event") == "key_edge":
                raise OSError("disk full")
        with self.assertRaises(trial.AcquisitionError) as caught:
            trial.run_trial(self.io, emit, probe=self.probe, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(self.io.edges, ["key S1OFF"])
        self.assertTrue(caught.exception.result["release_transport_completed"])

    def test_sample_error_preserves_partial_and_releases(self):
        self.io.during_failure_address = trial.RANGES[2][1]
        result = self.failure()
        self.assertTrue(result["release_transport_completed"])
        self.assertTrue(result["observations"][0]["blocks"])
        self.assertFalse(result["observations"][0]["complete"])

    def test_postcheck_change_reported_without_blind_restoration(self):
        calls = 0
        def changing_probe(io, emit):
            nonlocal calls
            calls += 1
            if calls == 2:
                io.replies["menu SetFocusPosition"] = "100 100 64 64"
            return self.probe(io, emit)
        result = self.failure(probe=changing_probe)
        self.assertEqual(result["status"], "postcheck-failed")
        self.assertTrue(result["release_transport_completed"])
        self.assertFalse(result["settings_equal"])

    def test_async_release_observed_without_repeating_key(self):
        original = self.io.request
        pending = 0
        def delayed(line, timeout=2):
            nonlocal pending
            if self.io.edges == ["key S1ON", "key S1OFF"] and "0xC3033A6C" in line:
                pending -= 1
                if pending == 0:
                    self.io.memory[0xC3033A6C] = 0
            raw = original(line, timeout)
            if line.endswith("key S1OFF"):
                self.io.memory[0xC3033A6C] = 1
                pending = 3
            return raw
        self.io.request = delayed
        result = self.run_trial()
        self.assertEqual(result["release_shutter_observations"], [1, 1, 0])
        self.assertEqual(self.io.edges, ["key S1ON", "key S1OFF"])

    def test_release_state_never_clears_is_reported_with_no_new_keys(self):
        original = self.io.request
        def stuck(line, timeout=2):
            raw = original(line, timeout)
            if line.endswith("key S1OFF"):
                self.io.memory[0xC3033A6C] = 1
            return raw
        self.io.request = stuck
        result = self.failure()
        self.assertEqual(result["status"], "postcheck-failed")
        self.assertTrue(result["release_transport_completed"])
        self.assertNotIn("after", result)
        self.assertLessEqual(len(result["release_shutter_observations"]), 10)
        self.assertEqual(self.io.edges, ["key S1ON", "key S1OFF"])


if __name__ == "__main__":
    unittest.main()
