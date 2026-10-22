#!/usr/bin/env python3
"""Offline tests for the AF-fusion binary framing and JSON schema."""

import io
import struct
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import af_fusion_collector as collector


class RecordTests(unittest.TestCase):
    def test_fixture_decodes_with_correct_domains(self):
        record = collector.parse_record(
            collector.build_mock_record(), host_before_ns=1_000_000, host_after_ns=2_000_000
        )
        self.assertEqual(record["schema"], collector.SCHEMA)
        self.assertEqual(record["transport"]["session_nonce"], 0x12345678)
        self.assertEqual(record["indices"]["af_area_used"], 3)
        self.assertEqual(record["indices"]["sweep_sample_used"], 12)
        self.assertEqual(record["af"]["saf_h"], 12000)
        self.assertEqual(record["af"]["mposm"], 5311)
        self.assertEqual(record["subject"]["coordinate_space"], {"width": 320, "height": 213})
        self.assertAlmostEqual(record["subject"]["face"]["w_norm"], 0.2)
        self.assertEqual(record["record_version"], 2)
        self.assertEqual(record["exposure"]["imx410_gain"]["analog_ratio_x100"], 250)
        self.assertTrue(record["exposure"]["imx410_gain"]["hcg"])
        self.assertTrue(record["integrity"]["snapshot_coherent"])
        self.assertIsNone(record["integrity"]["usable_for_dfd"])
        self.assertEqual(record["time"]["usb_round_trip_ms"], 1.0)

    def test_changed_index_is_not_usable_for_dfd(self):
        record = collector.parse_record(collector.build_mock_record(stable=False))
        self.assertFalse(record["integrity"]["indices_stable"])
        self.assertFalse(record["integrity"]["snapshot_coherent"])
        self.assertIsNone(record["integrity"]["usable_for_dfd"])

    def test_bad_magic_is_rejected(self):
        blob = bytearray(collector.build_mock_record())
        blob[0] ^= 0xFF
        with self.assertRaises(collector.RecordError):
            collector.parse_record(bytes(blob))

    def test_bad_sequence_complement_is_rejected(self):
        blob = bytearray(collector.build_mock_record())
        blob[0xC8] ^= 1
        with self.assertRaises(collector.RecordError):
            collector.parse_record(bytes(blob))

    def test_legacy_v1_gain_fields_stay_explicitly_legacy(self):
        blob = bytearray(collector.build_mock_record())
        struct.pack_into("<H", blob, 4, 1)
        record = collector.parse_record(bytes(blob))
        self.assertEqual(record["schema"], collector.LEGACY_SCHEMA)
        self.assertIn("legacy_gain_helper_raw", record["exposure"])
        self.assertNotIn("imx410_gain", record["exposure"])

    def test_truncated_binary_tail_is_rejected(self):
        stream = io.BytesIO(collector.build_mock_record() + b"short")
        iterator = collector.iter_binary_records(stream)
        self.assertEqual(len(next(iterator)), collector.RECORD_SIZE)
        with self.assertRaises(collector.RecordError):
            next(iterator)


class FakeShell:
    def __init__(self):
        self.words = {collector.ECHO_SLOT: collector.ECHO_ORIGINAL,
                      collector.FRAMEBUF_POINTER: 0x41000000}

    def mem_get(self, address, count, tries=8):
        return [self.words.get(address + i * 4, 0) for i in range(count)]

    def mem_set(self, address, value):
        self.words[address] = value

    def put(self, address, blob, _label):
        for i, value in enumerate(struct.unpack(f"<{len(blob) // 4}I", blob)):
            self.words[address + i * 4] = value


class HandlerLeaseTests(unittest.TestCase):
    def test_echo_is_restored_after_success(self):
        shell = FakeShell()
        code = b"\x01\x02\x03\x04" * 4
        with collector.installed_snapshot_handler(shell, code, 0xA5A55A5A):
            self.assertEqual(shell.words[collector.ECHO_SLOT], collector.CODE_ADDRESS)
            self.assertEqual(
                shell.words[collector.SESSION_NONCE_ADDRESS], 0xA5A55A5A
            )
            self.assertEqual(shell.words.get(collector.RECORD_ADDRESS + 0xCC, 0), 0)
        self.assertEqual(shell.words[collector.ECHO_SLOT], collector.ECHO_ORIGINAL)

    def test_echo_is_restored_after_failure(self):
        shell = FakeShell()
        code = b"\x01\x02\x03\x04" * 4
        with self.assertRaisesRegex(RuntimeError, "synthetic"):
            with collector.installed_snapshot_handler(shell, code, 0xA5A55A5A):
                raise RuntimeError("synthetic")
        self.assertEqual(shell.words[collector.ECHO_SLOT], collector.ECHO_ORIGINAL)

    def test_unknown_echo_borrower_is_refused(self):
        shell = FakeShell()
        shell.words[collector.ECHO_SLOT] = 0xDEADBEEF
        with self.assertRaises(SystemExit):
            with collector.installed_snapshot_handler(shell, b"\0" * 4, 0xA5A55A5A):
                pass

    def test_invalid_dma_pool_is_refused_before_install(self):
        shell = FakeShell()
        shell.words[collector.FRAMEBUF_POINTER] = 0
        with self.assertRaises(SystemExit):
            with collector.installed_snapshot_handler(shell, b"\0" * 4, 123):
                pass
        self.assertEqual(shell.words[collector.ECHO_SLOT], collector.ECHO_ORIGINAL)


class ControlTransportTests(unittest.TestCase):
    def test_silent_framed_success_is_accepted(self):
        with patch.object(collector, "_daemon_request", return_value=b"OK \n"):
            self.assertEqual(collector._send_key_edge(None, "key S1OFF"), "OK \n")

    def test_empty_eof_and_stale_text_are_rejected(self):
        for reply in (b"", b"OK get : A:0xC0000000, D:0x1\n", b"ERR timeout\n", b"OKX zz\n"):
            with self.subTest(reply=reply), patch.object(collector, "_daemon_request", return_value=reply):
                with self.assertRaises(RuntimeError):
                    collector._send_key_edge(None, "key S1ON")

    def test_full_press_not_allowed(self):
        with self.assertRaises(ValueError):
            collector._send_key_edge(None, "key S2ON")

    def test_raw_snapshot_decode(self):
        blob = collector.build_mock_record()
        with patch.object(collector, "_daemon_request", return_value=b"OKX " + blob.hex().encode() + b"\n"):
            self.assertEqual(collector._trial_snapshot_reply(None, 200).encode("latin1"), blob)


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.key_patch = patch.object(collector, "_send_key_edge",
                                      side_effect=lambda shell, command: shell.sh(command, retries=0))
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def trial(self, fail_on=None):
        self.now = 0.0
        self.events = []
        self.commands = []
        def sh(command, **kwargs):
            self.commands.append((command, kwargs))
            if command == fail_on:
                raise RuntimeError("synthetic dispatch failure")
            return ""
        shell = SimpleNamespace(sh=sh)
        trial = collector.HalfPressTrial(shell, 1.0, 2.0, self.events.append,
                                        clock=lambda: self.now)
        return trial, shell

    def test_serial_one_start_and_one_release(self):
        trial, _ = self.trial()
        record = collector.parse_record(collector.build_mock_record())
        record["exposure"]["movie_recording"] = False
        self.now = 1.1
        trial.step(9, record)
        self.assertFalse(self.commands)
        trial.step(10, record)
        trial.step(11, record)
        self.now = 3.2
        trial.step(12, record)
        trial.release()
        self.assertEqual([x[0] for x in self.commands], ["key S1ON", "key S1OFF"])
        self.assertTrue(all(x[1]["retries"] == 0 for x in self.commands))

    def test_start_exception_still_releases(self):
        _, shell = self.trial(fail_on="key S1ON")
        manifest = {}
        args = SimpleNamespace(half_press_after=1.0, half_press_hold=2.0)
        record = collector.parse_record(collector.build_mock_record())
        record["exposure"]["movie_recording"] = False
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                with collector._trial_controls(shell, args, Path(directory), manifest) as trial:
                    trial.started -= 2.0
                    trial.step(10, record)
        self.assertEqual([x[0] for x in self.commands], ["key S1ON", "key S1OFF"])
        self.assertTrue(manifest["release_transport_completed"])
        self.assertFalse(manifest["release_still_required"])

    def test_recording_refused_without_start(self):
        trial, _ = self.trial()
        self.now = 2.0
        record = collector.parse_record(collector.build_mock_record())
        with self.assertRaisesRegex(RuntimeError, "recording"):
            trial.step(10, record)
        self.assertFalse(self.commands)
        self.assertFalse(trial.release_needed)

    def test_failed_release_stays_required(self):
        trial, _ = self.trial(fail_on="key S1OFF")
        trial.release_needed = True
        with self.assertRaises(RuntimeError):
            trial.release()
        self.assertTrue(trial.release_needed)
        self.assertFalse(trial.released)

    def test_failed_logging_does_not_prevent_release(self):
        trial, _ = self.trial()
        def broken_log(event):
            raise OSError("disk full")
        trial.event_sink = broken_log
        trial.release_needed = True
        trial.release()
        self.assertEqual(self.commands[0][0], "key S1OFF")
        self.assertTrue(trial.released)
        self.assertTrue(trial.logging_errors)

    def test_insufficient_remaining_time_does_not_press(self):
        trial, _ = self.trial()
        record = collector.parse_record(collector.build_mock_record())
        record["exposure"]["movie_recording"] = False
        self.now = 3.0
        trial.step(100, record, remaining_s=2.0)
        self.assertFalse(self.commands)

    def test_read_only_has_no_control_file(self):
        _, shell = self.trial()
        with tempfile.TemporaryDirectory() as directory:
            with collector._trial_controls(shell, SimpleNamespace(), Path(directory), {}) as trial:
                self.assertIsNone(trial)
            self.assertFalse(list(Path(directory).iterdir()))
        self.assertFalse(self.commands)


if __name__ == "__main__":
    unittest.main()
