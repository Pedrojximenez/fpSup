"""Offline mock tests for the single-owner EP83 one-shot host session."""
import contextlib
import math
import unittest
import zlib

from highrate import ep83_host_session as host
from test_ep83_receiver import valid_batch


NONCE = 0x2468ACE1
SEQUENCE = 0x10203040


class FakeClock:
    def __init__(self, now=10.0):
        self.now = now

    def __call__(self):
        return self.now


class MockOwner:
    """One injected owner; every operation asserts the lease is held."""

    def __init__(self, clock, *, count=31, packet=1024):
        self.clock = clock
        self.count = count
        self.batch = valid_batch(nonce=NONCE, capacity=count)
        self.packet = packet
        self.sequence = SEQUENCE
        self.offset = 0
        self.events = []
        self.trigger_frames = []
        self.timeouts = []
        self.active = False
        self.descriptor = {
            "configuration_value": 1,
            "interface_number": 0,
            "alternate_setting": 0,
            "endpoint_address": 0x83,
            "attributes": 2,
            "max_packet_size": packet,
        }
        self.delays = {}
        self.failures = {}
        self.moved = 64
        self.terminal_changes = {}
        self.terminal_mutator = None

    def _step(self, name, timeout_ms=None):
        self.events.append(name)
        if timeout_ms is not None:
            self.timeouts.append((name, timeout_ms))
        self.clock.now += self.delays.get(name, 0)
        failure = self.failures.get(name)
        if failure:
            raise failure

    @contextlib.contextmanager
    def lease(self, timeout_ms):
        self._step("lease", timeout_ms)
        if "lease_enter" in self.failures:
            raise self.failures["lease_enter"]
        if self.active:
            raise AssertionError("lease re-entered")
        self.active = True
        self.events.append("lease_enter")
        try:
            yield self
        finally:
            self.events.append("lease_exit")
            self.active = False
            if "lease_exit" in self.failures:
                raise self.failures["lease_exit"]

    def _held(self):
        if not self.active:
            raise AssertionError("owner operation outside lease")

    def read_ep83_descriptor(self, timeout_ms):
        self._held()
        self._step("descriptor", timeout_ms)
        return dict(self.descriptor)

    def reserve_sequence(self):
        self._held()
        self._step("sequence")
        return self.sequence

    def send_trigger(self, frame, timeout_ms):
        self._held()
        self.trigger_frames.append(bytes(frame))
        self._step("trigger", timeout_ms)
        return self.moved

    def usb_read(self, endpoint, length, timeout_ms):
        self._held()
        self.events.append(("ep83", endpoint, length))
        self.timeouts.append(("ep83", timeout_ms))
        self.clock.now += self.delays.get("ep83", 0)
        failure = self.failures.get("ep83")
        if failure:
            raise failure
        chunk = self.batch[self.offset:self.offset + length]
        self.offset += len(chunk)
        return chunk

    def read_terminal(self, endpoint, length, timeout_ms):
        self._held()
        self.events.append(("terminal", endpoint, length))
        self.timeouts.append(("terminal", timeout_ms))
        self.clock.now += self.delays.get("terminal", 0)
        failure = self.failures.get("terminal")
        if failure:
            raise failure
        values = dict(
            sequence=self.sequence, nonce=NONCE, count=self.count,
            actual_batch_bytes=len(self.batch), batch_crc=zlib.crc32(self.batch),
        )
        values.update(self.terminal_changes)
        frame = host.encode_terminal_frame(**values)
        if self.terminal_mutator:
            frame = self.terminal_mutator(frame)
        return frame


def run(owner, clock, *, count=None, timeout=1.0):
    return host.EP83HostSession(
        owner, nonce=NONCE, count=owner.count if count is None else count,
        total_timeout_s=timeout, monotonic=clock).run()


class EP83HostSessionTests(unittest.TestCase):
    def test_success_is_one_lease_one_trigger_one_terminal_and_conservative(self):
        clock = FakeClock()
        owner = MockOwner(clock, count=31)
        session = host.EP83HostSession(
            owner, nonce=NONCE, count=31, total_timeout_s=1,
            monotonic=clock)
        result = session.run()

        self.assertEqual(session.state, host.STATE_COMPLETE)
        self.assertTrue(session.closed)
        self.assertFalse(session.quarantined)
        self.assertEqual(owner.events[:4],
                         ["lease", "lease_enter", "descriptor", "sequence"])
        self.assertEqual(owner.events.count("trigger"), 1)
        self.assertEqual([event for event in owner.events
                          if isinstance(event, tuple) and event[0] == "terminal"],
                         [("terminal", 0x82, 64)])
        self.assertEqual(owner.events[-1], "lease_exit")
        self.assertEqual(len(owner.trigger_frames), 1)
        trigger = host.decode_trigger_frame(
            owner.trigger_frames[0], expected_sequence=SEQUENCE)
        self.assertEqual((trigger.nonce, trigger.count, trigger.expected_batch_bytes),
                         (NONCE, 31, len(owner.batch)))

        self.assertEqual(result["actual_batch_bytes"], len(owner.batch))
        self.assertEqual(result["batch_crc"], zlib.crc32(owner.batch))
        self.assertEqual(result["terminal"]["phase"], host.AF_TX_COMPLETE)
        self.assertEqual(result["terminal"]["camera_state"],
                         host.CAMERA_STATE_SYNTHETIC)
        self.assertTrue(result["producer_not_installed"])
        self.assertFalse(result["hardware_validated"])
        self.assertFalse(result["usable_for_af_control"])
        self.assertFalse(result["usable_for_dfd"])
        self.assertTrue(result["owner_lease_released"])
        self.assertFalse(result["quarantined"])

        event_count = len(owner.events)
        with self.assertRaisesRegex(host.EP83HostSessionError, "single-use"):
            session.run()
        self.assertEqual(len(owner.events), event_count)

    def test_active_descriptor_mps_controls_packet_safe_ep83_requests(self):
        expected = {
            64: [64, 960],
            512: [512, 512],
            1024: [1024],
        }
        for packet, requests in expected.items():
            with self.subTest(packet=packet):
                clock = FakeClock()
                owner = MockOwner(clock, count=7, packet=packet)
                result = run(owner, clock)
                reads = [event[2] for event in owner.events
                         if isinstance(event, tuple) and event[0] == "ep83"]
                self.assertEqual(reads, requests)
                self.assertEqual(result["max_packet_size"], packet)
                self.assertEqual(result["descriptor"]["endpoint_address"], 0x83)

    def test_bad_active_descriptor_rejects_before_sequence_or_trigger(self):
        changes = (
            ("configuration_value", 2), ("interface_number", 1),
            ("alternate_setting", 1), ("endpoint_address", 0x82),
            ("attributes", 3), ("max_packet_size", 256),
        )
        for key, value in changes:
            with self.subTest(key=key):
                clock = FakeClock()
                owner = MockOwner(clock)
                owner.descriptor[key] = value
                session = host.EP83HostSession(
                    owner, nonce=NONCE, count=31, total_timeout_s=1,
                    monotonic=clock)
                with self.assertRaisesRegex(host.EP83HostSessionError,
                                            "descriptor") as caught:
                    session.run()
                self.assertFalse(caught.exception.quarantined)
                self.assertEqual(session.state, host.STATE_REJECTED)
                self.assertFalse(owner.trigger_frames)
                self.assertNotIn("sequence", owner.events)
                self.assertEqual(owner.events[-1], "lease_exit")

    def test_trigger_exception_or_partial_write_quarantines_without_retry(self):
        for failure, moved in ((TimeoutError("uncertain"), 64), (None, 63)):
            with self.subTest(failure=failure, moved=moved):
                clock = FakeClock()
                owner = MockOwner(clock)
                owner.moved = moved
                if failure:
                    owner.failures["trigger"] = failure
                session = host.EP83HostSession(
                    owner, nonce=NONCE, count=31, total_timeout_s=1,
                    monotonic=clock)
                with self.assertRaises(host.EP83HostSessionError) as caught:
                    session.run()
                self.assertTrue(caught.exception.quarantined)
                self.assertEqual(session.state, host.STATE_QUARANTINED)
                self.assertEqual(len(owner.trigger_frames), 1)
                self.assertFalse(any(isinstance(event, tuple) for event in owner.events))
                before = list(owner.events)
                with self.assertRaisesRegex(host.EP83HostSessionError, "single-use"):
                    session.run()
                self.assertEqual(owner.events, before)

    def test_ep83_fault_quarantines_and_never_reads_terminal_or_retries(self):
        clock = FakeClock()
        owner = MockOwner(clock, count=31)
        owner.batch = bytes([owner.batch[0] ^ 1]) + owner.batch[1:]
        session = host.EP83HostSession(
            owner, nonce=NONCE, count=31, total_timeout_s=1,
            monotonic=clock)
        with self.assertRaisesRegex(host.EP83HostSessionError,
                                    "EP83 batch receive failed") as caught:
            session.run()
        self.assertTrue(caught.exception.quarantined)
        reads = [event for event in owner.events
                 if isinstance(event, tuple) and event[0] == "ep83"]
        self.assertEqual(len(reads), 1)
        self.assertFalse(any(isinstance(event, tuple) and event[0] == "terminal"
                             for event in owner.events))

    def test_terminal_must_match_every_identity_and_success_field(self):
        changes = (
            {"nonce": NONCE + 1}, {"count": 30},
            {"actual_batch_bytes": len(valid_batch(nonce=NONCE, capacity=31)) - 1},
            {"batch_crc": 1}, {"phase": 3},
            {"camera_state": 0x434F4D50}, {"error": -7},
            {"platform_rc": -1},
            {"result_flags": host.TERMINAL_FLAG_DMA_MAY_BE_OWNED},
        )
        for change in changes:
            with self.subTest(change=change):
                clock = FakeClock()
                owner = MockOwner(clock, count=31)
                owner.terminal_changes = change
                session = host.EP83HostSession(
                    owner, nonce=NONCE, count=31, total_timeout_s=1,
                    monotonic=clock)
                with self.assertRaisesRegex(host.EP83HostSessionError,
                                            "does not match") as caught:
                    session.run()
                self.assertTrue(caught.exception.quarantined)
                terminals = [event for event in owner.events
                             if isinstance(event, tuple) and event[0] == "terminal"]
                self.assertEqual(len(terminals), 1)

    def test_terminal_outer_sequence_crc_and_exact_size_are_verified(self):
        def wrong_sequence(frame):
            terminal = host.decode_terminal_frame(frame, expected_sequence=SEQUENCE)
            return host.encode_terminal_frame(
                sequence=SEQUENCE + 1, nonce=terminal.nonce,
                count=terminal.count, actual_batch_bytes=terminal.actual_batch_bytes,
                batch_crc=terminal.batch_crc)

        def bad_crc(frame):
            changed = bytearray(frame)
            changed[-1] ^= 1
            return bytes(changed)

        for mutate in (wrong_sequence, bad_crc, lambda frame: frame[:-1]):
            with self.subTest(mutate=mutate.__name__):
                clock = FakeClock()
                owner = MockOwner(clock)
                owner.terminal_mutator = mutate
                with self.assertRaisesRegex(host.EP83HostSessionError,
                                            "invalid EP82") as caught:
                    run(owner, clock)
                self.assertTrue(caught.exception.quarantined)

    def test_terminal_read_error_is_single_and_quarantined(self):
        clock = FakeClock()
        owner = MockOwner(clock)
        owner.failures["terminal"] = TimeoutError("late terminal")
        with self.assertRaisesRegex(host.EP83HostSessionError,
                                    "terminal read failed") as caught:
            run(owner, clock)
        self.assertTrue(caught.exception.quarantined)
        terminals = [event for event in owner.events
                     if isinstance(event, tuple) and event[0] == "terminal"]
        self.assertEqual(len(terminals), 1)

    def test_one_absolute_budget_decreases_and_stops_after_trigger_expiry(self):
        clock = FakeClock()
        owner = MockOwner(clock, count=31)
        owner.delays.update(descriptor=0.10, trigger=0.10, ep83=0.10,
                            terminal=0.10)
        run(owner, clock, timeout=1.0)
        timeouts = [value for _, value in owner.timeouts]
        self.assertTrue(all(value >= 1 for value in timeouts))
        self.assertEqual(timeouts, sorted(timeouts, reverse=True))
        self.assertLess(clock.now, 11.0)

        clock = FakeClock()
        owner = MockOwner(clock)
        owner.delays["trigger"] = 1.0
        with self.assertRaisesRegex(host.EP83HostSessionError,
                                    "deadline") as caught:
            run(owner, clock, timeout=1.0)
        self.assertTrue(caught.exception.quarantined)
        self.assertFalse(any(isinstance(event, tuple) for event in owner.events))

    def test_lease_failures_are_rejected_before_trigger_and_quarantined_after(self):
        clock = FakeClock()
        owner = MockOwner(clock)
        owner.failures["lease_enter"] = RuntimeError("busy")
        with self.assertRaises(host.EP83HostSessionError) as caught:
            run(owner, clock)
        self.assertFalse(caught.exception.quarantined)
        self.assertFalse(owner.trigger_frames)

        clock = FakeClock()
        owner = MockOwner(clock)
        owner.failures["lease_exit"] = RuntimeError("release uncertain")
        with self.assertRaisesRegex(host.EP83HostSessionError,
                                    "lease/session") as caught:
            run(owner, clock)
        self.assertTrue(caught.exception.quarantined)
        self.assertEqual(len(owner.trigger_frames), 1)

    def test_codec_rejects_bad_trigger_crc_sequence_reserved_and_values(self):
        frame = host.encode_trigger_frame(
            sequence=SEQUENCE, nonce=NONCE, count=1)
        parsed = host.decode_trigger_frame(frame, expected_sequence=SEQUENCE)
        self.assertEqual((parsed.nonce, parsed.count), (NONCE, 1))
        corrupt = bytearray(frame)
        corrupt[25] ^= 1
        with self.assertRaisesRegex(host.EP83WireError, "checksum"):
            host.decode_trigger_frame(corrupt, expected_sequence=SEQUENCE)
        with self.assertRaisesRegex(host.EP83WireError, "sequence"):
            host.decode_trigger_frame(frame, expected_sequence=SEQUENCE + 1)
        for nonce, count in ((0, 1), (True, 1), (NONCE, 0), (NONCE, 257)):
            with self.subTest(nonce=nonce, count=count):
                with self.assertRaises(host.EP83WireError):
                    host.encode_trigger_frame(
                        sequence=SEQUENCE, nonce=nonce, count=count)

    def test_invalid_construction_performs_no_owner_operation(self):
        clock = FakeClock()
        owner = MockOwner(clock)
        for nonce, count, timeout in (
                (0, 1, 1), (NONCE, 0, 1), (NONCE, 257, 1),
                (NONCE, 1, 0), (NONCE, 1, True),
                (NONCE, 1, math.inf)):
            with self.subTest(nonce=nonce, count=count, timeout=timeout):
                with self.assertRaises((ValueError, host.EP83WireError)):
                    host.EP83HostSession(
                        owner, nonce=nonce, count=count,
                        total_timeout_s=timeout, monotonic=clock)
        self.assertFalse(owner.events)


if __name__ == "__main__":
    unittest.main()
