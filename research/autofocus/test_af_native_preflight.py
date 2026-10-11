"""Offline preflight authorization and failure-boundary tests; no camera I/O."""

import re
import struct
import unittest
from unittest import mock

import af_native_preflight as preflight


def mem_command(address, count):
    return f"mem get 0x{address:08X},,0x{count * 4:X}"


class FakeIO(preflight.Transport):
    """Use the production memory parser, never the socket/exchange methods."""

    def __init__(self):
        super().__init__()
        self.calls = []
        self.memory = {}
        self.replies = {}
        self.occurrences = {}
        self.status = b"OK camera=open\n"
        self.version = f"w71c1 5.02.0.V91 {preflight.BUILD_ID}"
        for _, address, count in (*preflight.RANGES, *preflight.SUBJECT_PATH_RANGES,
                                  *preflight.SUBJECT_WATCH_RANGES):
            self.memory.update({address + 4 * i: 0 for i in range(count)})
        for _, address, word in preflight.SITES:
            self.memory[address] = word
        for _, address, data in preflight.static_guards():
            for index, (word,) in enumerate(struct.iter_unpack("<I", data)):
                self.memory[address + 4 * index] = word
        self.memory.update({preflight.ECHO: preflight.ORIGINAL_ECHO,
                            0xC30338C8: 0, 0xC30338CC: 0,
                            0xC30338D0: 0, 0xC3033A6C: 0,
                            0xC3476408: 1, 0xC3476414: 0xC0B8EEEC,
                            0xC37CCA9C: 0xC2DFAB00,
                            0xC37CD340: 0xC2DFC59C,
                            0xC37CD344: 0xC2DFC5B8,
                            0xC37CD364: 0})

    def request(self, line, timeout=2.0):
        self.calls.append(("request", line, timeout))
        if line != "STATUS":
            raise AssertionError(f"unexpected host request: {line}")
        if isinstance(self.status, Exception):
            raise self.status
        return self.status

    def shell(self, command, timeout_ms=1000):
        self.calls.append(("shell", command, timeout_ms))
        index = self.occurrences.get(command, 0)
        self.occurrences[command] = index + 1
        override = self.replies.get((command, index), self.replies.get(command))
        if isinstance(override, Exception):
            raise override
        if override is not None:
            return override
        if command == "version":
            return self.version
        if command in preflight.SETTINGS:
            return "0"
        if command in tuple(f"tkos skdump {name} 0" for name in preflight.TASKS):
            return "id    26\nstksz 0x4000\nistk  41234000\nssp   41233000\n====== stack dump 0 byte ======\n"
        match = re.fullmatch(r"mem get 0x([0-9A-F]{8}),,0x([0-9A-F]+)", command)
        if match is None:
            raise AssertionError(f"non-read or unexpected command: {command}")
        address, size = (int(part, 16) for part in match.groups())
        if size % 4 or not 4 <= size <= 32:
            raise AssertionError("unbounded/unaligned memory command")
        return "\n".join(f"get : A:0x{a:08X}, D:0x{self.memory[a]:08X}"
                         for a in range(address, address + size, 4))


class PreflightTests(unittest.TestCase):
    def setUp(self):
        # Also catches future accidental use of a real Transport inside probe.
        self.socket_guard = mock.patch("focus_bridge.socket.socket",
                                       side_effect=AssertionError("test attempted camera I/O"))
        self.socket_guard.start()
        self.addCleanup(self.socket_guard.stop)
        self.io = FakeIO()

    def commands(self):
        return [line for kind, line, _ in self.io.calls if kind == "shell"]

    def test_success_is_read_only_and_retains_unknown_authority(self):
        events = []
        result = preflight.probe(self.io, events.append)
        self.assertEqual(result["status"], "read-complete")
        self.assertEqual(result["camera_ram_writes"], 0)
        self.assertEqual(result["camera_ram_writes_scope"], "direct host writes and injected payloads only")
        self.assertIs(result["native_handler_internal_writes_audited"], False)
        self.assertEqual(result["lens_commands"], 0)
        self.assertEqual(result["retries"], 0)
        for field in ("installation_performed", "deployment_ready", "memory_ownership_verified",
                      "stack_headroom_verified", "source_coherence_verified", "geometry_eligible",
                      "confirmation_authorized", "motion_authorized"):
            self.assertIs(result[field], False, field)
        self.assertTrue(result["native_l_layout_matches"])
        self.assertTrue(result["settings_equal"])
        self.assertEqual(self.io.calls[0], ("request", "STATUS", 2.0))
        for command in self.commands():
            self.assertNotRegex(command, r"(?:^| )(?:set|echo|call|alloc|chgpri|abort|key|move)(?: |$)")
        chunks = [row for row in events if row["event"] == "memory_chunk"]
        self.assertTrue(chunks)
        for row in chunks:
            self.assertLessEqual(len(row["words"]), 8)
            self.assertLessEqual(row["host_before_ns"], row["host_after_ns"])
        self.assertTrue(all(block["coherent_snapshot"] is False
                            for block in result["blocks"].values()))

    def test_only_fixed_getters_and_zero_body_task_queries(self):
        preflight.probe(self.io)
        non_memory = [c for c in self.commands() if not c.startswith("mem get ")]
        expected_settings = ["menu SetFocusPosition", "menu SetFocusMode",
                             "menu SetFocusArea", "menu SetFocusAreaSize"]
        expected_tasks = [f"tkos skdump {name} 0" for name in
                          ("AfMgr", "LensFocs", "Tracking", "FdTsk", "EyeDtctn")]
        self.assertEqual(non_memory, ["version", *expected_settings,
                                      *expected_tasks, *expected_settings])
        self.assertTrue(all(timeout == 1000 for kind, _, timeout in self.io.calls if kind == "shell"))

    def test_subject_diagnostics_are_opt_in(self):
        result = preflight.probe(self.io)
        self.assertIs(result["subject_path_checked"], False)
        for label, address, _ in preflight.SUBJECT_PATH_RANGES:
            self.assertNotIn(label, result["blocks"])
            self.assertFalse(any(c.startswith(f"mem get 0x{address:08X},") for c in self.commands()))

    def test_subject_path_fixed_ranges_and_no_added_native_getters(self):
        baseline = FakeIO()
        preflight.probe(baseline)
        result = preflight.probe(self.io, subject_path=True)
        extra = [c for c in self.commands() if c not in [v for _, v, _ in baseline.calls]]
        # Independent allowlist: even plausible pointer fields must never be followed.
        allowed = ((0xC31AE3A8, 4), (0xC31B954C, 4),
                   (0xC31B3758, 4), (0xC31B9020, 4),
                   (0xC358E260, 0x50), (0xC358E2B8, 4),
                   (0xC37CCDB8, 0x20), (0xC37CCF10, 0x28),
                   (0xC3033AC4, 0xA8), (0xC3033DDC, 0x20),
                   (0xC3433C58, 0xA8), (0xC3433F70, 0x20),
                   (0xC3434474, 0xA8), (0xC343478C, 0x20),
                   (0xC34348E4, 4), (0xC3435A54, 0x24), (0xC30338E8, 4),
                   (0xC3426318, 0xC),
                   (0xC31B954C, 4))
        expected = [mem_command(start + offset, min(8, (size - offset) // 4))
                    for start, size in allowed for offset in range(0, size, 32)]
        self.assertEqual(extra, expected)
        self.assertEqual(len(extra), 38)
        self.assertIs(result["subject_path_checked"], True)
        for field in ("geometry_eligible", "source_coherence_verified", "motion_authorized",
                      "confirmation_authorized", "deployment_ready"):
            self.assertIs(result[field], False)

    def test_subject_path_identity_failure_prevents_additional_reads(self):
        self.io.version = "unsupported"
        with self.assertRaises(RuntimeError):
            preflight.probe(self.io, subject_path=True)
        self.assertEqual(self.commands(), ["version"])

    def test_subject_path_short_reply_stops_without_retry_or_later_reads(self):
        command = mem_command(0xC3434474, 8)
        self.io.replies[command] = ""
        with self.assertRaises(Exception):
            preflight.probe(self.io, subject_path=True)
        self.assertEqual(self.io.occurrences[command], 1)
        self.assertEqual(self.commands()[-1], command)
        self.assertIs(self.io.transport_faulted, True)

    def test_display_flags_and_pointers_do_not_confer_subject_validity(self):
        self.io.memory[0xC343447C] = 0xFFFF0101
        self.io.memory[0xC3435A6C] = 0x45678900  # not the expected copy; do not follow
        result = preflight.probe(self.io, subject_path=True)
        self.assertEqual(result["blocks"]["face_renderer_head"]["words"][2], 0xFFFF0101)
        self.assertEqual(result["blocks"]["face_renderer_object"]["words"][6], 0x45678900)
        self.assertFalse(any("45678900" in c for c in self.commands()))
        self.assertIs(result["geometry_eligible"], False)
        self.assertTrue(all(not b["coherent_snapshot"] for b in result["blocks"].values()))

    def test_watch_bounds_and_dependency_checked_before_any_io(self):
        for count in (-1, 17, True, 1.0, "1"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                preflight.probe(self.io, subject_path=True, subject_samples=count)
        with self.assertRaises(ValueError):
            preflight.probe(self.io, subject_samples=1)
        self.assertEqual(self.io.calls, [])

    def test_watch_is_bounded_paced_fixed_reads_and_retains_unknowns(self):
        self.io.memory[0xC37CCA10] = 0x010101  # all three runtime gate bytes
        self.io.memory[0xC37CCAA8] = 0x00000101
        self.io.memory[0xC37CCAB4] = 100
        events = []
        with mock.patch.object(preflight.time, "sleep") as sleep:
            result = preflight.probe(self.io, events.append, subject_path=True, subject_samples=16)
        self.assertEqual(sleep.call_args_list, [mock.call(0.25)] * 15)
        observations = result["subject_observations"]
        self.assertEqual(len(observations), 16)
        self.assertEqual(sum(e["event"] == "subject_observation" for e in events), 16)
        ranges = {"runtime_gate": (0xC37CCA04, 20), "runtime_guard": (0xC37CCA18, 4),
                  "raw_header": (0xC37CCF10, 8), "manager_header": (0xC37CCA9C, 16),
                  "face_slot": (0xC37CCAAC, 52), "status_header": (0xC3033AC4, 12),
                  "renderer_header": (0xC3434474, 12)}
        for index, observation in enumerate(observations):
            self.assertEqual(observation["index"], index)
            self.assertLessEqual(observation["host_before_ns"], observation["host_after_ns"])
            self.assertEqual(set(observation["blocks"]), set(ranges))
            for label, (address, size) in ranges.items():
                block = observation["blocks"][label]
                self.assertEqual(int(block["address"], 16), address)
                self.assertEqual(len(bytes.fromhex(block["bytes_hex"])), size)
                self.assertIs(block["coherent_snapshot"], False)
            self.assertIs(observation["geometry_eligible"], False)
            self.assertIs(observation["source_coherence_verified"], False)
        watch_commands = [e["command"] for e in events if e["event"] == "native_reply"]
        self.assertEqual(watch_commands.count(mem_command(0xC37CCA04, 5)), 16)
        self.assertIs(result["motion_authorized"], False)

    def test_watch_failure_does_not_retry_or_continue_observations(self):
        command = mem_command(0xC37CCA04, 5)
        self.io.replies[(command, 1)] = OSError("lost transport")
        events = []
        with mock.patch.object(preflight.time, "sleep"), self.assertRaises(OSError):
            preflight.probe(self.io, events.append, subject_path=True, subject_samples=8)
        self.assertEqual(self.io.occurrences[command], 2)
        self.assertEqual(self.commands()[-1], command)
        self.assertEqual(sum(e["event"] == "subject_observation" for e in events), 1)

    def test_fixed_memory_ranges_no_pointer_chasing_even_plausible_values(self):
        self.io.memory[0xC072F050] = 0x44440000
        self.io.memory[0xC072F054] = 0x100000
        self.io.memory[0xC072F058] = 0x44550000
        self.io.memory[0xC3757A7C] = 0x44660000
        result = preflight.probe(self.io)
        # Independent address allowlist, not derived from the implementation's RANGES.
        intervals = ((0xC0BAC2F8, 4), (0xC30338C8, 12), (0xC3033A6C, 4),
                     (0xC028E310, 4), (0xC0340458, 4), (0xC05AB348, 4), (0xC05AB8C8, 4),
                     (0xC072F050, 12), (0xC3757A7C, 4), (0xC072E060, 4),
                     (0xC3476408, 4), (0xC3476414, 92), (0xC37CCA9C, 16),
                     (0xC37CCAAC, 156), (0xC37CDFA8, 48), (0xC3033E00, 40),
                     (0xC37CCA8C, 4), (0xC37CD340, 40),
                     (0xC072F6F4, 8), (0xC072F700, 16), (0xC072FC00, 16),
                     (0xC028E2F8, 48), (0xC022B720, 16), (0xC022B79C, 4),
                     (0xC0340448, 48), (0xC036D758, 16), (0xC036D788, 4),
                     (0xC05AB32C, 52), (0xC05A9900, 16), (0xC05A99C4, 4),
                     (0xC05AB8B8, 40), (0xC05B6CF8, 16), (0xC05B7364, 4))
        for command in self.commands():
            match = re.fullmatch(r"mem get 0x([0-9A-F]{8}),,0x([0-9A-F]+)", command)
            if match:
                address, size = (int(part, 16) for part in match.groups())
                self.assertTrue(any(start <= address and address + size <= start + length
                                    for start, length in intervals), command)
        self.assertEqual(result["worker_publication_raw"],
                         dict(pool=0x44440000, size=0x100000, code=0x44550000))
        self.assertTrue(result["worker_and_legacy_pool_differ"])
        self.assertIs(result["memory_ownership_verified"], False)

    def test_host_not_open_stops_before_version(self):
        for status in (b"OK camera=closed\n", b"ERR no daemon", b"bad camera=open"):
            with self.subTest(status=status):
                io = FakeIO()
                io.status = status
                with self.assertRaises(RuntimeError):
                    preflight.probe(io)
                self.assertEqual(io.calls, [("request", "STATUS", 2.0)])

    def test_each_identity_token_required_before_memory(self):
        for token in ("w71c1", "5.02.0.V91", preflight.BUILD_ID):
            with self.subTest(token=token):
                io = FakeIO()
                io.version = io.version.replace(token, "wrong")
                with self.assertRaisesRegex(RuntimeError, "unsupported"):
                    preflight.probe(io)
                self.assertEqual([line for _, line, _ in io.calls], ["STATUS", "version"])

    def test_unknown_echo_owner_stops_before_capture_or_hooks(self):
        self.io.memory[preflight.ECHO] = 0xC072FC00
        with self.assertRaisesRegex(RuntimeError, "unknown echo borrower"):
            preflight.probe(self.io)
        self.assertEqual(self.commands(), ["version", mem_command(preflight.ECHO, 1)])

    def test_each_capture_busy_byte_movie_and_shutter_stop_before_hooks(self):
        cases = [(0xC30338C8, 1 << shift) for shift in (0, 8, 16, 24)]
        cases += [(0xC30338D0, 1), (0xC3033A6C, 1)]
        for address, value in cases:
            with self.subTest(address=hex(address), value=value):
                io = FakeIO()
                io.memory[address] = value
                with self.assertRaisesRegex(RuntimeError, "guard active"):
                    preflight.probe(io)
                self.assertEqual([line for _, line, _ in io.calls][-1], mem_command(0xC3033A6C, 1))
                self.assertNotIn(mem_command(0xC028E310, 1), [line for _, line, _ in io.calls])

    def test_movie_guard_is_low_byte_not_adjacent_bytes(self):
        self.io.memory[0xC30338D0] = 0xAABBCC00
        self.assertEqual(preflight.probe(self.io)["status"], "read-complete")

    def test_each_hook_mismatch_stops_on_that_exact_read(self):
        for name, address, word in preflight.SITES:
            with self.subTest(name=name):
                io = FakeIO()
                io.memory[address] = word ^ 1
                with self.assertRaisesRegex(RuntimeError, f"{name} callsite"):
                    preflight.probe(io)
                commands = [line for _, line, _ in io.calls]
                self.assertEqual(commands[-1], mem_command(address, 1))
                self.assertNotIn(mem_command(0xC072F050, 3), commands)

    def test_transport_exception_never_retries_or_continues(self):
        for command in ("version", mem_command(preflight.ECHO, 1),
                        mem_command(0xC37CCAAC, 8), "menu SetFocusMode",
                        "tkos skdump FdTsk 0"):
            with self.subTest(command=command):
                io = FakeIO()
                io.replies[command] = TimeoutError("uncertain response")
                with self.assertRaises(TimeoutError):
                    preflight.probe(io)
                commands = [line for _, line, _ in io.calls]
                self.assertEqual(commands[-1], command)
                self.assertEqual(commands.count(command), 1)

    def test_each_context_entry_return_mismatch_stops_on_that_block(self):
        guards = preflight.static_guards()
        self.assertEqual(len(guards), 12)
        for name, address, data in guards:
            with self.subTest(name=name):
                io = FakeIO()
                # Last word avoids accidentally changing the separately checked callsite.
                last = address + len(data) - 4
                io.memory[last] ^= 1
                with self.assertRaisesRegex(RuntimeError, "firmware context mismatch"):
                    preflight.probe(io)
                offset = ((len(data) // 4 - 1) // 8) * 8
                self.assertEqual(io.calls[-1][1], mem_command(address + offset * 4,
                                                             len(data) // 4 - offset))
                self.assertNotIn(mem_command(0xC072F050, 3), [line for _, line, _ in io.calls])

    def test_invalid_local_contract_stops_before_any_io(self):
        with mock.patch.object(preflight, "static_guards", side_effect=ValueError("bad contract")):
            with self.assertRaises(ValueError):
                preflight.probe(self.io)
        self.assertEqual(self.io.calls, [])

    def test_capture_becomes_busy_is_reported_without_inventing_continuous_idle(self):
        command = mem_command(0xC30338C8, 3)
        self.io.replies[(command, 1)] = "\n".join(
            f"A:0x{address:08X}, D:0x{value:08X}" for address, value in
            ((0xC30338C8, 0), (0xC30338CC, 0), (0xC30338D0, 1)))
        result = preflight.probe(self.io)
        self.assertIs(result["capture_idle_at_both_observations"], False)
        self.assertIs(result["deployment_ready"], False)

    def test_echo_owner_change_at_end_is_failure(self):
        command = mem_command(preflight.ECHO, 1)
        self.io.replies[(command, 1)] = "A:0xC0BAC2F8, D:0xC072FC00"
        with self.assertRaisesRegex(RuntimeError, "echo owner changed"):
            preflight.probe(self.io)
        self.assertEqual(self.commands()[-1], command)
        self.assertEqual(self.commands().count(command), 2)
        self.assertEqual(self.commands().count("menu SetFocusMode"), 1)

    def test_setting_changed_during_read_is_evidence_not_authority(self):
        self.io.replies[("menu SetFocusMode", 1)] = "1"
        result = preflight.probe(self.io)
        self.assertIs(result["settings_equal"], False)
        self.assertIs(result["geometry_eligible"], False)
        self.assertIs(result["motion_authorized"], False)

    def test_inactive_or_uninitialized_sources_never_become_valid(self):
        self.io.memory[0xC3476408] = 0
        self.io.memory[0xC3476414] = 0
        self.io.memory[0xC37CCA9C] = 0
        self.io.memory[0xC37CD340] = 0
        result = preflight.probe(self.io)
        self.assertIs(result["native_l_layout_matches"], False)
        for field in ("geometry_eligible", "confirmation_authorized", "motion_authorized",
                      "memory_ownership_verified", "stack_headroom_verified"):
            self.assertIs(result[field], False)

    def test_no_producer_completion_inferred_from_task_metadata(self):
        result = preflight.probe(self.io)
        self.assertEqual(set(result["tasks"]), set(preflight.TASKS))
        self.assertIs(result["stack_headroom_verified"], False)
        self.assertIs(result["source_coherence_verified"], False)

    def test_strict_parser_rejects_missing_extra_bad_or_duplicate_addresses(self):
        command = mem_command(0xC072F050, 3)
        good = [f"A:0x{0xC072F050 + i * 4:08X}, D:0x00000000" for i in range(3)]
        malformed = ["\n".join(good[:2]), "\n".join(good + good[-1:]),
                     "\n".join([good[0], good[0], good[2]]),
                     "\n".join([good[1], good[0], good[2]]),
                     "\n".join(good).replace("D:0x00000000", "D:0x100000000", 1),
                     "\n".join(good).replace("A:0xC072F050", "A:0xC072F04C", 1),
                     "\n".join(good) + "\ntrailer", "", "0 0 0"]
        for reply in malformed:
            with self.subTest(reply=reply):
                io = FakeIO()
                io.replies[command] = reply
                with self.assertRaises(Exception):
                    preflight.probe(io)
                self.assertTrue(io.transport_faulted)
                self.assertEqual(io.occurrences[command], 1)
                self.assertEqual(io.calls[-1][1], command)

    def test_production_parser_keeps_u32_bytes_without_semantic_coercion(self):
        self.io.memory[0xC37CCAAC] = 0xFFFFFFFF
        self.io.memory[0xC37CCAB0] = 0x80000000
        result = preflight.probe(self.io)
        block = result["blocks"]["face_group0"]
        self.assertEqual(block["words"][:2], [0xFFFFFFFF, 0x80000000])
        self.assertTrue(block["bytes_hex"].startswith("ffffffff00000080"))
        self.assertIs(block["coherent_snapshot"], False)


if __name__ == "__main__":
    unittest.main()
