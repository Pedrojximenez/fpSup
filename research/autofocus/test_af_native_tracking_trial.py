"""Bounded native S1 trials with mocked camera replies; sockets are forbidden."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import af_native_tracking_trial as trial
from test_af_native_preflight import FakeIO as PreflightIO


EXPECTED = {"menu SetFocusPosition": "480 373 64 64", "menu SetFocusMode": "1",
            "menu SetFocusArea": "3", "menu SetFocusAreaSize": "2"}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, value):
        self.now += value


class Camera(PreflightIO):
    def __init__(self, clock):
        super().__init__()
        self.clock = clock
        self.replies.update(EXPECTED)
        self.edges = []
        self.edge_replies = {}
        self.during_failure_address = None
        self.after_release_exchange_count = 0
        for _, address, count in trial.RANGES:
            for index in range(count):
                self.memory.setdefault(address+4*index, 0)
        self.memory.update({0xC31AE3A8: 1, 0xC31C01B0: 0})

    def request(self, line, timeout=2.0):
        self.clock.now += 0.01
        if self.edges and self.edges[-1] == "key S1OFF":
            self.after_release_exchange_count += 1
        if line == "STATUS":
            return super().request(line, timeout)
        self.calls.append(("request", line, timeout))
        command = line.split(" SHL ", 1)[1]
        if command.startswith("key "):
            self.edges.append(command)
            response = self.edge_replies.get(command, b"OK \n")
            if isinstance(response, BaseException):
                self._latch_transport_fault()
                raise response
            return response
        if (self.during_failure_address is not None and self.edges == ["key S1ON"]
                and f"0x{self.during_failure_address:08X}" in command):
            self._latch_transport_fault()
            raise TimeoutError("mock stalled sample")
        return b"OKX "+super().shell(command).encode("latin1").hex().encode()+b"\n"


class TrialTests(unittest.TestCase):
    def setUp(self):
        guard = mock.patch("focus_bridge.socket.socket", side_effect=AssertionError("live I/O forbidden"))
        guard.start()
        self.addCleanup(guard.stop)
        self.clock = Clock()
        self.camera = Camera(self.clock)
        self.events = []

    def run_trial(self, **kwargs):
        return trial.run_trial(self.camera, EXPECTED, self.events.append,
                               clock=self.clock, sleep=self.clock.sleep, **kwargs)

    def expect_failure(self, **kwargs):
        with self.assertRaises(trial.TrialError) as caught:
            self.run_trial(**kwargs)
        return caught.exception.result

    def test_success_uses_real_preflight_parser_and_paired_edges(self):
        result = self.run_trial()
        self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])
        self.assertEqual(result["status"], "complete")
        self.assertGreater(result["complete_observations"], 0)
        self.assertTrue(result["release_transport_completed"])
        self.assertTrue(result["settings_restoration_permitted"])
        self.assertFalse(result["optical_focus_confirmed"])
        self.assertFalse(result["geometry_eligible"])
        for row in result["observations"]:
            self.assertFalse(row["coherent_snapshot"])
            self.assertFalse(row["geometry_eligible"])
        attempts = [e for e in self.events if e.get("event") == "key_edge" and e["phase"] == "attempt"]
        self.assertEqual([e["command"] for e in attempts], ["key S1ON", "key S1OFF"])
        self.assertAlmostEqual(attempts[1]["elapsed_s"]-attempts[0]["elapsed_s"], 2.0)
        for event in self.events:
            if event.get("event") == "memory_chunk":
                self.assertLessEqual(len(event["words"]), 8)
        for _, command, _ in self.camera.calls:
            self.assertNotRegex(command, r"mem set|S2|MOV|echo|setfpos|SetFocusMode 1")

    def test_no_aff1_snapshot_is_constructed(self):
        result = self.run_trial()
        self.assertNotIn("AFF1", json.dumps(result))
        self.assertNotIn("snapshot_coherent", json.dumps(result))

    def test_preflight_firmware_rejection_sends_no_key(self):
        self.camera.version = "unknown firmware"
        result = self.expect_failure()
        self.assertFalse(result["half_press_attempted"])
        self.assertEqual(self.camera.edges, [])

    def test_cine_rejected_before_probe_and_keys(self):
        self.camera.memory[0xC31C01B0] = 1
        result = self.expect_failure()
        self.assertEqual(self.camera.edges, [])
        self.assertNotIn("preflight_before", result)

    def test_invalid_storage_guard_rejected(self):
        self.camera.memory[0xC31AE3A8] = 0
        self.expect_failure()
        self.assertEqual(self.camera.edges, [])

    def test_expected_settings_cannot_authorize_other_modes(self):
        for key, value in (("menu SetFocusMode", "0"), ("menu SetFocusArea", "2")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                trial.run_trial(self.camera, dict(EXPECTED, **{key: value}))
        self.assertEqual(self.camera.calls, [])

    def test_actual_settings_mismatch_rejected(self):
        self.camera.replies["menu SetFocusArea"] = "0"
        self.expect_failure()
        self.assertEqual(self.camera.edges, [])

    def test_recording_busy_and_shutter_each_block_press(self):
        for address in (0xC30338C8, 0xC30338D0, 0xC3033A6C):
            with self.subTest(address=address):
                self.camera = Camera(self.clock)
                self.camera.memory[address] = 1
                self.expect_failure()
                self.assertEqual(self.camera.edges, [])

    def test_fresh_guard_catches_capture_change_after_preflight(self):
        def probe(io, emit):
            result = trial.preflight.probe(io, emit)
            io.memory[0xC30338D0] = 1
            return result
        self.expect_failure(probe=probe)
        self.assertEqual(self.camera.edges, [])

    def test_still_guard_rechecked_after_preflight(self):
        def probe(io, emit):
            result = trial.preflight.probe(io, emit)
            io.memory[0xC31C01B0] = 1
            return result
        self.expect_failure(probe=probe)
        self.assertEqual(self.camera.edges, [])

    def test_capture_transition_during_hold_releases(self):
        original = self.camera.request
        def changing(line, timeout=2):
            result = original(line, timeout)
            if line.endswith("key S1ON"):
                self.camera.memory[0xC30338D0] = 1
            return result
        self.camera.request = changing
        result = self.expect_failure()
        self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])
        self.assertTrue(result["release_transport_completed"])
        self.assertFalse(result["settings_restoration_permitted"])

    def test_movie_neighbor_byte_does_not_reject(self):
        self.camera.memory[0xC30338D0] = 0x10000
        self.assertEqual(self.run_trial()["status"], "complete")

    def test_own_half_press_shutter_state_one_is_expected_only_during_hold(self):
        original = self.camera.request
        def changing(line, timeout=2):
            result = original(line, timeout)
            if line.endswith("key S1ON"):
                self.camera.memory[0xC3033A6C] = 1
            elif line.endswith("key S1OFF"):
                self.camera.memory[0xC3033A6C] = 0
            return result
        self.camera.request = changing
        result = self.run_trial()
        self.assertEqual(result["status"], "complete")
        self.assertGreater(result["complete_observations"], 0)
        self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])

    def test_full_press_or_unknown_shutter_state_during_hold_releases(self):
        for state in (2, 3, 0xffffffff):
            with self.subTest(state=state):
                self.camera = Camera(self.clock)
                original = self.camera.request
                def changing(line, timeout=2):
                    result = original(line, timeout)
                    if line.endswith("key S1ON"):
                        self.camera.memory[0xC3033A6C] = state
                    return result
                self.camera.request = changing
                result = self.expect_failure()
                self.assertTrue(result["release_transport_completed"])
                self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])

    def test_half_press_state_not_cleared_after_release_fails_postcheck(self):
        original = self.camera.request
        def changing(line, timeout=2):
            result = original(line, timeout)
            if line.endswith("key S1ON"):
                self.camera.memory[0xC3033A6C] = 1
            return result
        self.camera.request = changing
        result = self.expect_failure()
        self.assertEqual(result["status"], "postcheck-failed")
        self.assertFalse(result["settings_restoration_permitted"])

    def test_uncertain_start_is_not_retried_and_releases(self):
        self.camera.edge_replies["key S1ON"] = TimeoutError("uncertain start")
        result = self.expect_failure()
        self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])
        self.assertTrue(result["release_transport_completed"])
        self.assertTrue(result["transport_faulted"])
        self.assertFalse(result["settings_restoration_permitted"])
        self.assertEqual(self.camera.after_release_exchange_count, 0)

    def test_malformed_start_ack_faults_and_releases(self):
        self.camera.edge_replies["key S1ON"] = b""
        result = self.expect_failure()
        self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])
        self.assertTrue(result["transport_faulted"])

    def test_failed_release_not_repeated_and_no_further_exchange(self):
        self.camera.edge_replies["key S1OFF"] = TimeoutError("release uncertain")
        result = self.expect_failure()
        self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])
        self.assertTrue(result["release_still_required"])
        self.assertFalse(result["release_transport_completed"])
        self.assertFalse(result["settings_restoration_permitted"])
        self.assertEqual(self.camera.after_release_exchange_count, 0)

    def test_sample_failure_releases_immediately(self):
        self.camera.during_failure_address = trial.RANGES[0][1]
        result = self.expect_failure()
        self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])
        self.assertTrue(result["release_transport_completed"])
        self.assertLess(self.clock(), 2.0)

    def test_intent_log_failure_prevents_start_but_still_releases(self):
        def sink(row):
            if row.get("event") == "key_edge":
                raise OSError("disk full")
        with self.assertRaises(trial.TrialError) as caught:
            trial.run_trial(self.camera, EXPECTED, sink, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(self.camera.edges, ["key S1OFF"])
        self.assertTrue(caught.exception.result["release_transport_completed"])
        self.assertTrue(caught.exception.result["control_logging_errors"])

    def test_reply_log_failure_releases_after_attempted_start(self):
        def sink(row):
            if row.get("event") == "key_edge" and row["phase"] == "reply":
                raise OSError("disk full")
        with self.assertRaises(trial.TrialError):
            trial.run_trial(self.camera, EXPECTED, sink, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])

    def test_sample_logging_failure_faults_and_releases(self):
        def sink(row):
            if self.camera.edges == ["key S1ON"] and row.get("event") == "memory_chunk":
                raise OSError("disk full")
        with self.assertRaises(trial.TrialError) as caught:
            trial.run_trial(self.camera, EXPECTED, sink, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])
        self.assertTrue(caught.exception.result["transport_faulted"])

    def test_postcheck_setting_change_reports_failure_after_release(self):
        original = self.camera.request
        def changing(line, timeout=2):
            result = original(line, timeout)
            if line.endswith("key S1OFF"):
                self.camera.replies["menu SetFocusPosition"] = "123 45 64 64"
            return result
        self.camera.request = changing
        result = self.expect_failure()
        self.assertEqual(result["status"], "postcheck-failed")
        self.assertTrue(result["release_transport_completed"])
        self.assertFalse(result["settings_restoration_permitted"])

    def test_transport_latch_prevents_new_press_but_allows_release(self):
        self.camera._latch_transport_fault()
        self.expect_failure()
        self.assertEqual(self.camera.edges, [])
        with self.assertRaises(RuntimeError):
            trial.send_key_edge(self.camera, "key S1ON")
        self.assertEqual(trial.send_key_edge(self.camera, "key S1OFF"), "OK \n")

    def test_control_wrapper_reuses_parent_and_enforces_single_attempt(self):
        self.assertIs(trial.NativeHalfPress._command, trial.HalfPressTrial._command)
        control = trial.NativeHalfPress(self.camera, self.events.append, clock=self.clock)
        control.press()
        with self.assertRaises(RuntimeError):
            control.press()
        control.release()
        control.release()
        self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])

    def test_deadline_stops_new_reads_prior_to_release(self):
        original = self.camera.request
        def slow_request(line, timeout=2):
            if self.camera.edges == ["key S1ON"] and "mem get" in line:
                self.clock.now += 0.11
            return original(line, timeout)
        self.camera.request = slow_request
        result = self.run_trial()
        self.assertTrue(result["observations"][-1]["stopped_for_release_deadline"])
        self.assertFalse(result["observations"][-1]["complete"])
        for _, line, timeout in self.camera.calls:
            if line.startswith("TMO 100 SHL mem"):
                self.assertLessEqual(timeout, 0.15)

    def test_keyboard_interrupt_still_releases(self):
        def interrupt(_):
            raise KeyboardInterrupt()
        with self.assertRaises(trial.TrialError) as caught:
            trial.run_trial(self.camera, EXPECTED, self.events.append,
                            clock=self.clock, sleep=interrupt)
        self.assertTrue(caught.exception.result["release_transport_completed"])
        self.assertEqual(self.camera.edges, ["key S1ON", "key S1OFF"])

    def test_cli_requires_explicit_motion_flag_before_opening_files(self):
        with tempfile.TemporaryDirectory() as path:
            out = Path(path)/"test.jsonl"
            with self.assertRaises(SystemExit):
                trial.main(["--expected-settings", str(Path(path)/"missing.json"), "--output", str(out)])
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
