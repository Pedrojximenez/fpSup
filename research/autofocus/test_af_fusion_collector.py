#!/usr/bin/env python3
"""Offline tests for the AF-fusion binary framing and JSON schema."""

import io
import contextlib
import json
import struct
import subprocess
import sys
import unittest
import tempfile
import time
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
        self.assertIsNone(record["subject"]["coordinate_space"])
        self.assertIsNone(record["subject"]["face"]["w_norm"])
        self.assertEqual(record["record_version"], 3)
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
        record = collector.parse_record(collector.build_mock_record(version=1))
        self.assertEqual(record["schema"], collector.LEGACY_SCHEMA)
        self.assertIn("legacy_gain_helper_raw", record["exposure"])
        self.assertNotIn("imx410_gain", record["exposure"])

    def test_legacy_v1_v2_capture_is_unknown_not_false_or_true(self):
        for version in (1, 2):
            for recording in (False, True):
                with self.subTest(version=version, recording=recording):
                    record = collector.parse_record(collector.build_mock_record(
                        version=version, recording=recording, ptp_state=0))
                    exposure = record["exposure"]
                    self.assertIsNone(exposure["movie_recording"])
                    self.assertIsNone(exposure["ptp_capture_state_raw"])
                    self.assertIsNone(exposure["capture_idle_for_af"])
                    self.assertFalse(exposure["capture_guard_known"])
                    self.assertNotIn("capture_state_raw", exposure)
                    self.assertEqual(int(recording), exposure["legacy_capture_raw"]["c347e08f_u8"])
                    if version == 2:
                        self.assertEqual(collector.LEGACY_V2_SCHEMA, record["schema"])
                        self.assertIn("imx410_gain", exposure)

    def test_v3_idle_requires_all_five_bytes_and_ptp_gate_zero(self):
        exposure = collector.parse_record(collector.build_mock_record(
            recording=False, ptp_state=0))["exposure"]
        self.assertFalse(exposure["movie_recording"])
        self.assertFalse(exposure["capture_busy"])
        self.assertTrue(exposure["capture_idle_for_af"])
        self.assertTrue(exposure["capture_guard_known"])

    def test_v3_busy_bytes_keep_their_actual_little_endian_mapping(self):
        exposure = collector.parse_record(collector.build_mock_record(
            recording=False, ptp_state=0, busy_word=0x04030201))["exposure"]
        self.assertEqual(exposure["capture_flags_raw"], {
            "still_exposing": 1, "still_saving": 2,
            "movie_saving": 3, "still_image_processing": 4,
        })
        self.assertTrue(exposure["capture_busy"])
        self.assertFalse(exposure["capture_idle_for_af"])

    def test_v3_ptp_guard_is_full_u32_not_u16(self):
        exposure = collector.parse_record(collector.build_mock_record(
            recording=False, ptp_state=0x10000))["exposure"]
        self.assertEqual(0x10000, exposure["ptp_capture_state_raw"])
        self.assertFalse(exposure["capture_busy"])
        self.assertFalse(exposure["capture_idle_for_af"])

    def test_v3_recording_flag_mismatch_rejected(self):
        blob = bytearray(collector.build_mock_record())
        struct.pack_into("<I", blob, 0xC0, 0)
        with self.assertRaisesRegex(collector.RecordError, "mismatch"):
            collector.parse_record(bytes(blob))

    def test_v3_recording_byte_out_of_range_rejected(self):
        blob = bytearray(collector.build_mock_record())
        struct.pack_into("<I", blob, 0xC0, 256)
        with self.assertRaises(collector.RecordError):
            collector.parse_record(bytes(blob))

    def test_mixed_version_stream_preserves_record_boundaries(self):
        records = [collector.build_mock_record(version=v) for v in (1, 3, 2, 3)]
        decoded = list(collector.iter_binary_records(io.BytesIO(b"".join(records))))
        self.assertEqual(records, decoded)
        self.assertEqual([1, 3, 2, 3], [collector.parse_record(b)["record_version"] for b in decoded])

    def test_legacy_record_relabelled_as_v3_is_rejected(self):
        blob = bytearray(collector.build_mock_record(version=2))
        struct.pack_into("<H", blob, 4, 3)
        with self.assertRaises(collector.RecordError):
            collector.parse_record(bytes(blob))

    def test_unknown_version_and_wrong_size_rejected_before_length_allocation(self):
        for version, size in ((4, 212), (3, 208), (2, 212), (3, 65535)):
            header = struct.pack("<4sHH", b"AFF1", version, size)
            with self.subTest(version=version, size=size):
                with self.assertRaises(collector.RecordError):
                    list(collector.iter_binary_records(io.BytesIO(header)))

    def test_new_nonce_seed_is_outside_new_record(self):
        self.assertEqual(212, collector.RECORD_SIZE)
        self.assertEqual(0xC072F7D4, collector.SESSION_NONCE_ADDRESS)
        self.assertLessEqual(collector.SESSION_NONCE_ADDRESS + 4, 0xC072F800)

    def test_truncated_binary_tail_is_rejected(self):
        stream = io.BytesIO(collector.build_mock_record() + b"short")
        iterator = collector.iter_binary_records(stream)
        self.assertEqual(len(next(iterator)), collector.RECORD_SIZE)
        with self.assertRaises(collector.RecordError):
            next(iterator)


class SubjectEvidenceTests(unittest.TestCase):
    def test_positive_legacy_rectangles_and_flags_never_authorize_geometry(self):
        schemas = {1: "sigma-fp-af-fusion/v7/legacy-record-v1",
                   2: "sigma-fp-af-fusion/v7/legacy-record-v2",
                   3: "sigma-fp-af-fusion/v7"}
        for version in (1, 2, 3):
            with self.subTest(version=version):
                blob = bytearray(collector.build_mock_record(version=version))
                # Both of the old rectangle interpretations look plausible;
                # high quality and all old flags still prove neither source.
                struct.pack_into("<hhhh", blob, 0x74, 30, 40, 100, 80)
                struct.pack_into("<I", blob, 0x7C, 0xFFFFFFFF)
                struct.pack_into("<IiiiiII", blob, 0x80, 1, 50, 20, 64, 64, 42, 1)
                self.assertEqual(struct.unpack_from("<I", blob, 0x0C)[0], 0x3F)
                record = collector.parse_record(bytes(blob))
                self.assertEqual(record["schema"], schemas[version])
                subject = record["subject"]
                self.assertEqual(subject["schema"], "sigma-fp-aff1-subject/v1")
                for key in ("coordinate_space", "cue_source", "roi", "roi_confidence", "track_id"):
                    self.assertIsNone(subject[key], key)
                for key in ("geometry_eligible", "source_completion_known", "optical_anchor_available"):
                    self.assertIs(subject[key], False, key)
                self.assertIs(subject["face"]["available"], False)
                self.assertIs(subject["face"]["valid"], False)
                for key in ("w_norm", "face0_tracking_id", "face0_valid"):
                    self.assertIsNone(subject["face"][key], key)
                for key in ("available", "valid", "locked"):
                    self.assertIs(subject["aat"][key], False, key)
                self.assertIsNone(record["estimates"]["geometry_target"])
                self.assertIsNone(record["estimates"]["geometry_confidence"])

    def test_every_subject_byte_and_legacy_flag_bit_is_preserved(self):
        evidence = bytes(range(40))
        for version in (1, 2, 3):
            for subject_flags in (0, 0x08, 0x10, 0x18):
                with self.subTest(version=version, subject_flags=subject_flags):
                    blob = bytearray(collector.build_mock_record(version=version))
                    blob[0x74:0x9C] = evidence
                    flags = struct.unpack_from("<I", blob, 0x0C)[0]
                    struct.pack_into("<I", blob, 0x0C, (flags & ~0x18) | subject_flags)
                    legacy = collector.parse_record(bytes(blob))["subject"]["legacy_evidence"]
                    self.assertEqual(bytes.fromhex(legacy["record_0x74_to_0x9b_hex"]), evidence)
                    self.assertEqual(legacy["subject_flag_bits_raw"], subject_flags)
                    self.assertEqual(legacy["old_packed_i16_interpretation"],
                                     list(struct.unpack("<hhhh", evidence[:8])))
                    self.assertEqual(legacy["old_coordinate_assumption"], {"width": 320, "height": 213})

    def test_counter_coordinate_and_wrong_offset_id_keep_raw_domains(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                blob = bytearray(collector.build_mock_record(version=version))
                struct.pack_into("<IiI", blob, 0x74, 0x80010002, -123456, 0xFFFFFFFF)
                struct.pack_into("<IiiiiII", blob, 0x80, 0x80000001,
                                 -123, 456, 789, -321, 0xDEADBEEF, 0xCAFEBABE)
                subject = collector.parse_record(bytes(blob))["subject"]
                raw = subject["raw_sources"]
                prefix = raw["aat_publication_prefix"]
                self.assertEqual(prefix["source_address"], "0xC3033E00")
                self.assertEqual(prefix["call_count_raw"], 0x80010002)
                self.assertEqual(prefix["result_x_i32"], -123456)
                self.assertEqual(prefix["quality_raw"], 0xFFFFFFFF)
                self.assertEqual(prefix["quality_source_address"], "0xC3033E26")
                self.assertIs(prefix["is_exposure_sequence"], False)
                self.assertIs(prefix["rectangle_complete"], False)
                result = raw["aat_get_result"]
                self.assertEqual(result["mode_source_address"], "0xC37CCE6C")
                self.assertEqual(result["rectangle_source_address"], "0xC37CCE7C")
                self.assertEqual(result["mode_raw"], 0x80000001)
                self.assertEqual(result["rectangle_i32"], {"x": -123, "y": 456, "w": 789, "h": -321})
                self.assertIs(result["producer_valid_known"], False)
                self.assertIs(result["scale_validated"], False)
                face = raw["face_group0_partial"]
                self.assertEqual(face["valid_source_address"], "0xC37CCADC")
                self.assertEqual(face["valid_raw"], 0xCAFEBABE)
                self.assertEqual(face["group_0x34_source_address"], "0xC37CCAE0")
                self.assertEqual(face["group_0x34_word_raw"], 0xDEADBEEF)
                self.assertIsNone(face["tracking_id"])
                self.assertIsNone(subject["track_id"])

    def test_subject_reinterpretation_cannot_change_capture_or_af_domains(self):
        for version in (1, 2, 3):
            for options in ({"recording": False, "ptp_state": 0},
                            {"recording": True, "ptp_state": 0},
                            {"recording": False, "ptp_state": 0x10000},
                            {"recording": False, "ptp_state": 0, "busy_word": 0x04030201}):
                with self.subTest(version=version, options=options):
                    original = collector.build_mock_record(version=version, **options)
                    changed = bytearray(original)
                    changed[0x74:0x9C] = b"\xFF" * 40
                    flags = struct.unpack_from("<I", changed, 0x0C)[0]
                    struct.pack_into("<I", changed, 0x0C, flags & ~0x18)
                    before, after = (collector.parse_record(b) for b in (original, bytes(changed)))
                    before.pop("subject")
                    after.pop("subject")
                    self.assertEqual(before, after)


class OfflineDecodeTests(unittest.TestCase):
    def test_decode_new_jsonl_preserves_mixed_binary_source(self):
        binary = b"".join(collector.build_mock_record(version=v) for v in (1, 2, 3))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "samples.bin"
            target = Path(directory) / "decoded-v7.jsonl"
            source.write_bytes(binary)
            with patch.object(collector, "_load_shell", side_effect=AssertionError("offline only")):
                self.assertEqual(collector.main(["decode", str(source), "--jsonl", str(target)]), 0)
            self.assertEqual(source.read_bytes(), binary)
            records = [json.loads(line) for line in target.read_text().splitlines()]
            self.assertEqual([r["record_version"] for r in records], [1, 2, 3])
            self.assertTrue(all(r["subject"]["geometry_eligible"] is False for r in records))
            self.assertTrue(all(r["time"]["host_after_ns"] is None for r in records))

    def test_decode_refuses_existing_capture_jsonl_without_overwriting_either_file(self):
        binary = collector.build_mock_record()
        original_jsonl = b'{"schema":"historical","time":{"host_after_ns":123}}\n'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "samples.bin"
            target = Path(directory) / "samples.jsonl"
            source.write_bytes(binary)
            target.write_bytes(original_jsonl)
            with self.assertRaisesRegex(SystemExit, "decode failed"):
                collector.main(["decode", str(source), "--jsonl", str(target)])
            self.assertEqual(source.read_bytes(), binary)
            self.assertEqual(target.read_bytes(), original_jsonl)

    def test_decode_refuses_binary_source_as_output(self):
        binary = collector.build_mock_record()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "samples.bin"
            source.write_bytes(binary)
            with self.assertRaisesRegex(SystemExit, "decode failed"):
                collector.main(["decode", str(source), "--jsonl", str(source)])
            self.assertEqual(source.read_bytes(), binary)


class FakeShell:
    def __init__(self):
        self.words = {collector.ECHO_SLOT: collector.ECHO_ORIGINAL,
                      collector.FRAMEBUF_POINTER: 0x41000000}
        self.reads = []
        self.writes = []
        self.drop_at = None
        self.after_write = None

    def mem_get(self, address, count, tries=8):
        self.reads.append((address, count))
        return [self.words.get(address + i * 4, 0) for i in range(count)]

    def mem_set(self, address, value):
        self.writes.append((address, value))
        if address != self.drop_at:
            self.words[address] = value
        if self.after_write:
            self.after_write(address, value)

    def put(self, address, blob, _label):
        raise AssertionError("fresh RAM bulk loader must never execute during installation")


class CurrentWorkerLeaseGuardTests(unittest.TestCase):
    def test_collect_is_blocked_before_socket_import_or_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            with patch.object(collector, "_load_shell", side_effect=AssertionError("no I/O")):
                with self.assertRaisesRegex(SystemExit, "live AF collector disabled"):
                    collector.main(["collect", "--output", str(output)])
            self.assertFalse(output.exists())

    def test_direct_installer_is_also_blocked_before_any_camera_read_or_write(self):
        shell = FakeShell()
        with self.assertRaisesRegex(SystemExit, "ownership lease"):
            with collector.installed_snapshot_handler(shell, b"1234", 123):
                self.fail("no live lease exists")
        self.assertFalse(shell.reads)
        self.assertFalse(shell.writes)

    def test_inspect_selects_explicit_current_worker_abi_and_reports_blocked_live(self):
        calls = []
        shell = SimpleNamespace(assemble=lambda source, defines: calls.append(
            (source, defines)) or b"1234")
        output = io.StringIO()
        with patch.object(collector, "_load_shell", return_value=shell):
            with contextlib.redirect_stdout(output):
                self.assertEqual(collector.main(["inspect"]), 0)
        self.assertEqual(calls, [(collector.SOURCE, ["AF_WORKER_POOL_POINTER=0xC072F050"])])
        self.assertIn("live_collection_enabled=false", output.getvalue())
        self.assertIn("live_camera_touched=false", output.getvalue())

    def test_snapshot_assembly_refuses_missing_or_legacy_pool_selection(self):
        shell = collector._load_shell(collector.DEFAULT_SHELL_DIR, collector.DEFAULT_SOCKET)
        for defines in ([], ["AF_WORKER_POOL_POINTER=0xC3757A7C"]):
            with self.subTest(defines=defines), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    shell.assemble(collector.SOURCE, defines)

    def test_arm_snapshot_copies_worker_reply_buffer_and_preserves_logger_pool(self):
        # Execute the actual assembled candidate, with a fake tick getter and
        # disjoint current worker/logger pools. This caught the historical bug:
        # writing the logger pool while CAP_PTR=0 asks USB for the worker pool.
        try:
            from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
            from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR
        except ImportError:
            self.skipTest("Unicorn is unavailable; live gate tests still run")
        # On macOS the restricted sandbox can SIGILL at Unicorn's first
        # mem_map. Probe in a child so an unavailable JIT does not kill all
        # binary/guard tests. A skipped emulation is never a hardware result.
        probe = subprocess.run([sys.executable, "-c", "import unicorn; "
            "u=unicorn.Uc(unicorn.UC_ARCH_ARM,unicorn.UC_MODE_ARM); "
            "u.mem_map(0x1000,0x1000)"], capture_output=True, timeout=10)
        if probe.returncode:
            self.skipTest(f"Unicorn JIT unavailable (probe exit {probe.returncode})")
        shell = collector._load_shell(collector.DEFAULT_SHELL_DIR, collector.DEFAULT_SOCKET)
        code = collector._assemble(shell)
        self.assertLessEqual(len(code), collector.CODE_END - collector.CODE_ADDRESS)
        uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        uc.mem_map(0xC0000000, 0x04000000)
        uc.mem_map(0x41000000, 0x10000)
        uc.mem_map(0x42000000, 0x10000)
        uc.mem_map(0x10000000, 0x10000)
        uc.mem_write(collector.CODE_ADDRESS, code)
        uc.mem_write(0xC002B6E0, struct.pack("<II", 0xE3A00001, 0xE12FFF1E))
        uc.mem_write(collector.FRAMEBUF_POINTER, struct.pack("<I", 0x41000000))
        uc.mem_write(0xC3757A7C, struct.pack("<I", 0x42000000))
        uc.mem_write(collector.SESSION_NONCE_ADDRESS, struct.pack("<I", 0x12345678))
        old_pool = b"\xA7" * 0x10000
        uc.mem_write(0x42000000, old_pool)
        uc.mem_write(0x41002000, b"\xB8" * (collector.RECORD_SIZE + 4))
        uc.reg_write(UC_ARM_REG_SP, 0x1000F000)
        uc.reg_write(UC_ARM_REG_LR, 0x10000000)
        uc.emu_start(collector.CODE_ADDRESS, 0x10000000, count=10000)
        record = bytes(uc.mem_read(collector.RECORD_ADDRESS, collector.RECORD_SIZE))
        self.assertEqual(bytes(uc.mem_read(0x41002000, collector.RECORD_SIZE)), record)
        self.assertEqual(bytes(uc.mem_read(0x42000000, 0x10000)), old_pool)
        self.assertEqual(bytes(uc.mem_read(0x41002000 + collector.RECORD_SIZE, 4)), b"\xB8" * 4)
        self.assertEqual(struct.unpack("<I", uc.mem_read(0xC072F04C, 4))[0], 0)
        self.assertEqual(struct.unpack("<I", uc.mem_read(0xC072F040, 4))[0], collector.RECORD_SIZE)
        self.assertEqual(collector.parse_record(record)["transport"]["session_nonce"], 0x12345678)


class HandlerLeaseTests(unittest.TestCase):
    def setUp(self):
        # Exercise the historical installer implementation without implying it
        # has a current camera-memory lease. Public live entry points remain
        # unconditionally blocked and are tested separately below.
        lease_gate = patch.object(collector, "_require_reviewed_live_lease")
        lease_gate.start()
        self.addCleanup(lease_gate.stop)
        self.cache_calls = []
        def reply(shell, command):
            self.cache_calls.append((shell.words[collector.ECHO_SLOT], command))
            return b"OK \n"
        self.cache_patch = patch.object(collector, "_daemon_request", side_effect=reply)
        self.cache_request = self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)

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
        self.assertEqual(self.cache_calls, [
            (collector.DCACHE_MAINTENANCE, "TMO 1000 SHL echo"),
            (collector.ICACHE_INVALIDATE, "TMO 1000 SHL echo"),
        ])
        self.assertEqual([value for address, value in shell.writes if address == collector.ECHO_SLOT], [
            collector.DCACHE_MAINTENANCE, collector.ECHO_ORIGINAL,
            collector.ICACHE_INVALIDATE, collector.ECHO_ORIGINAL,
            collector.CODE_ADDRESS, collector.ECHO_ORIGINAL,
        ])

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
        self.assertEqual(shell.words[collector.ECHO_SLOT], 0xDEADBEEF)
        self.assertFalse(shell.writes)

    def test_invalid_dma_pool_is_refused_before_install(self):
        shell = FakeShell()
        shell.words[collector.FRAMEBUF_POINTER] = 0
        with self.assertRaises(SystemExit):
            with collector.installed_snapshot_handler(shell, b"\0" * 4, 123):
                pass
        self.assertEqual(shell.words[collector.ECHO_SLOT], collector.ECHO_ORIGINAL)

    def test_invalid_code_or_nonce_is_rejected_before_io(self):
        for code, nonce in ((b"", 1), (b"123", 1), (b"1" * 1028, 1),
                            (b"1234", 0), (b"1234", True), (b"1234", 0x100000000)):
            with self.subTest(code_length=len(code), nonce=nonce):
                shell = FakeShell()
                with self.assertRaises(ValueError):
                    with collector.installed_snapshot_handler(shell, code, nonce):
                        self.fail("must not enter invalid lease")
                self.assertFalse(shell.reads)
                self.assertFalse(shell.writes)

    def test_partial_upload_failure_never_calls_ram_or_cache(self):
        shell = FakeShell()
        shell.drop_at = collector.CODE_ADDRESS + 8
        with self.assertRaisesRegex(RuntimeError, "could not set"):
            with collector.installed_snapshot_handler(shell, b"1234" * 4, 123):
                self.fail("must not enter failed upload")
        self.assertEqual(shell.words[collector.ECHO_SLOT], collector.ECHO_ORIGINAL)
        self.assertFalse(self.cache_calls)
        self.assertEqual(sum(a == shell.drop_at for a, _ in shell.writes), 10)
        self.assertFalse(any(a == collector.ECHO_SLOT for a, _ in shell.writes))

    def test_parameter_failure_is_inside_cleanup_scope(self):
        for address in (collector.RECORD_ADDRESS, collector.SESSION_NONCE_ADDRESS):
            with self.subTest(address=address):
                shell = FakeShell()
                shell.words[collector.RECORD_ADDRESS] = 0x12345678
                shell.drop_at = address
                with self.assertRaisesRegex(RuntimeError, "could not set"):
                    with collector.installed_snapshot_handler(shell, b"1234" * 4, 123):
                        self.fail("must not enter failed parameter write")
                self.assertEqual(shell.words[collector.ECHO_SLOT], collector.ECHO_ORIGINAL)
                self.assertFalse(self.cache_calls)

    def test_cache_timeout_restores_echo_and_is_never_retried(self):
        for failing_index in (0, 1):
            with self.subTest(failing_index=failing_index):
                shell = FakeShell()
                responses = [b"OK \n"] * failing_index + [TimeoutError("cache timeout")]
                with patch.object(collector, "_daemon_request", side_effect=responses) as request:
                    with self.assertRaisesRegex(TimeoutError, "cache timeout"):
                        with collector.installed_snapshot_handler(shell, b"1234" * 4, 123):
                            self.fail("must not arm after uncertain publication")
                    self.assertEqual(failing_index + 1, request.call_count)
                self.assertEqual(shell.words[collector.ECHO_SLOT], collector.ECHO_ORIGINAL)
                self.assertNotIn((collector.ECHO_SLOT, collector.CODE_ADDRESS), shell.writes)

    def test_cache_response_must_be_exact_success(self):
        for reply in (b"", b"OK\n", b"OK stale\n", b"OKX 00\n", b"ERR timeout\n"):
            with self.subTest(reply=reply):
                shell = FakeShell()
                with patch.object(collector, "_daemon_request", return_value=reply) as request:
                    with self.assertRaisesRegex(RuntimeError, "uncertain ROM"):
                        collector._call_cache_maintenance(shell, collector.DCACHE_MAINTENANCE)
                    self.assertEqual(1, request.call_count)
                self.assertEqual(shell.words[collector.ECHO_SLOT], collector.ECHO_ORIGINAL)

    def test_cache_function_whitelist_rejects_arbitrary_address_before_io(self):
        for function in (collector.CODE_ADDRESS, float(collector.DCACHE_MAINTENANCE), True):
            with self.subTest(function=function):
                shell = FakeShell()
                with self.assertRaises(ValueError):
                    collector._call_cache_maintenance(shell, function)
                self.assertFalse(shell.reads)
                self.assertFalse(shell.writes)
                self.assertFalse(self.cache_calls)

    def test_cache_function_requires_original_owner_before_borrow(self):
        shell = FakeShell()
        shell.words[collector.ECHO_SLOT] = collector.DCACHE_MAINTENANCE
        with self.assertRaisesRegex(RuntimeError, "unknown echo owner"):
            collector._call_cache_maintenance(shell, collector.DCACHE_MAINTENANCE)
        self.assertFalse(shell.writes)
        self.assertFalse(self.cache_calls)

    def test_unknown_owner_during_cleanup_is_never_overwritten(self):
        shell = FakeShell()
        with self.assertRaisesRegex(RuntimeError, "unknown echo owner"):
            with collector.installed_snapshot_handler(shell, b"1234" * 4, 123):
                shell.words[collector.ECHO_SLOT] = 0xDEADBEEF
                writes_before_cleanup = list(shell.writes)
        self.assertEqual(shell.words[collector.ECHO_SLOT], 0xDEADBEEF)
        self.assertEqual(writes_before_cleanup, shell.writes)

    def test_unknown_owner_during_cache_call_preserves_foreign_slot(self):
        shell = FakeShell()
        def conflict(shell, command):
            shell.words[collector.ECHO_SLOT] = 0xDEADBEEF
            return b"OK \n"
        with patch.object(collector, "_daemon_request", side_effect=conflict) as request:
            with self.assertRaisesRegex(RuntimeError, "unknown echo owner"):
                with collector.installed_snapshot_handler(shell, b"1234" * 4, 123):
                    self.fail("must not arm with foreign owner")
            self.assertEqual(1, request.call_count)
        self.assertEqual(shell.words[collector.ECHO_SLOT], 0xDEADBEEF)
        self.assertEqual((collector.ECHO_SLOT, collector.DCACHE_MAINTENANCE), shell.writes[-1])

    def test_uncertain_arming_write_still_restores_echo(self):
        shell = FakeShell()
        def fault_after_write(address, value):
            if address == collector.ECHO_SLOT and value == collector.CODE_ADDRESS:
                raise TimeoutError("arming reply lost")
        shell.after_write = fault_after_write
        with self.assertRaisesRegex(TimeoutError, "arming reply lost"):
            with collector.installed_snapshot_handler(shell, b"1234" * 4, 123):
                self.fail("must not enter uncertain lease")
        self.assertEqual(shell.words[collector.ECHO_SLOT], collector.ECHO_ORIGINAL)
        self.assertEqual(2, len(self.cache_calls))

    def test_matching_existing_snapshot_is_restored_and_republished_before_rearm(self):
        shell = FakeShell()
        code = b"1234" * 4
        value = struct.unpack("<I", code[:4])[0]
        for offset in range(0, len(code), 4):
            shell.words[collector.CODE_ADDRESS + offset] = value
        shell.words[collector.ECHO_SLOT] = collector.CODE_ADDRESS
        with collector.installed_snapshot_handler(shell, code, 123):
            self.assertEqual(shell.words[collector.ECHO_SLOT], collector.CODE_ADDRESS)
        self.assertEqual(shell.writes[0], (collector.ECHO_SLOT, collector.ECHO_ORIGINAL))
        self.assertEqual([function for function, _ in self.cache_calls],
                         list(collector.CACHE_PUBLICATION_FUNCTIONS))

    def test_unknown_code_at_same_slot_is_not_assumed_owned(self):
        shell = FakeShell()
        shell.words[collector.ECHO_SLOT] = collector.CODE_ADDRESS
        with self.assertRaises(SystemExit):
            with collector.installed_snapshot_handler(shell, b"1234" * 4, 123):
                self.fail("unknown snapshot bytes")
        self.assertEqual(shell.words[collector.ECHO_SLOT], collector.CODE_ADDRESS)
        self.assertFalse(shell.writes)

    def test_corruption_after_cache_publication_prevents_arming(self):
        shell = FakeShell()
        def corrupt(shell, command):
            if shell.words[collector.ECHO_SLOT] == collector.ICACHE_INVALIDATE:
                shell.words[collector.SESSION_NONCE_ADDRESS] = 99
            return b"OK \n"
        with patch.object(collector, "_daemon_request", side_effect=corrupt):
            with self.assertRaisesRegex(RuntimeError, "changed before"):
                with collector.installed_snapshot_handler(shell, b"1234" * 4, 123):
                    self.fail("must not arm corrupted parameters")
        self.assertEqual(shell.words[collector.ECHO_SLOT], collector.ECHO_ORIGINAL)
        self.assertNotIn((collector.ECHO_SLOT, collector.CODE_ADDRESS), shell.writes)

    def test_failed_final_restoration_is_fatal_and_bounded(self):
        shell = FakeShell()
        with self.assertRaisesRegex(RuntimeError, "restoration/transition failed"):
            with collector.installed_snapshot_handler(shell, b"1234" * 4, 123):
                shell.drop_at = collector.ECHO_SLOT
                before = len(shell.writes)
        self.assertEqual(collector.CODE_ADDRESS, shell.words[collector.ECHO_SLOT])
        self.assertEqual(10, len(shell.writes) - before)

    def test_failed_rom_restoration_remains_fatal_without_arming_ram(self):
        shell = FakeShell()
        def prevent_restore(shell, command):
            shell.drop_at = collector.ECHO_SLOT
            return b"OK \n"
        with patch.object(collector, "_daemon_request", side_effect=prevent_restore) as request:
            with self.assertRaisesRegex(RuntimeError, "restoration/transition failed"):
                with collector.installed_snapshot_handler(shell, b"1234" * 4, 123):
                    self.fail("cannot arm after failed ROM restoration")
            self.assertEqual(1, request.call_count)
        self.assertEqual(collector.DCACHE_MAINTENANCE, shell.words[collector.ECHO_SLOT])
        self.assertNotIn((collector.ECHO_SLOT, collector.CODE_ADDRESS), shell.writes)
        self.assertEqual(20, sum(a == collector.ECHO_SLOT and v == collector.ECHO_ORIGINAL
                                 for a, v in shell.writes))

    def test_last_bounded_word_repair_success_is_accepted(self):
        shell = FakeShell()
        collector._ensure_word(shell, collector.RECORD_ADDRESS, 123, attempts=1)
        self.assertEqual(123, shell.words[collector.RECORD_ADDRESS])


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

    def record(self, **kwargs):
        options = dict(recording=False, ptp_state=0)
        options.update(kwargs)
        now = time.time_ns()
        return collector.parse_record(collector.build_mock_record(**options),
                                      host_before_ns=now, host_after_ns=now)

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
        record = self.record()
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
        record = self.record()
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
        record = self.record(recording=True)
        with self.assertRaisesRegex(RuntimeError, "recording"):
            trial.step(10, record)
        self.assertFalse(self.commands)
        self.assertFalse(trial.release_needed)

    def test_each_busy_byte_and_ptp_gate_refuses_start(self):
        for options in ({"busy_word": 1}, {"busy_word": 0x100},
                        {"busy_word": 0x10000}, {"busy_word": 0x1000000},
                        {"ptp_state": 1}, {"ptp_state": 0x10000}):
            with self.subTest(options=options):
                trial, _ = self.trial()
                self.now = 2.0
                with self.assertRaisesRegex(RuntimeError, "busy"):
                    trial.step(10, self.record(**options))
                self.assertFalse(self.commands)
                self.assertFalse(trial.release_needed)

    def test_legacy_unknown_recording_refuses_start(self):
        for version in (1, 2):
            with self.subTest(version=version):
                trial, _ = self.trial()
                self.now = 2.0
                with self.assertRaisesRegex(RuntimeError, "unknown"):
                    trial.step(10, self.record(version=version))
                self.assertFalse(self.commands)

    def test_absent_stale_or_future_host_sample_cannot_start(self):
        for observed_ns in (None, True, time.time_ns() - 300_000_000,
                            time.time_ns() + 10_000_000_000):
            with self.subTest(observed_ns=observed_ns):
                trial, _ = self.trial()
                self.now = 2.0
                record = self.record()
                record["time"]["host_after_ns"] = observed_ns
                trial.step(10, record)
                self.assertFalse(self.commands)

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
        record = self.record()
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
