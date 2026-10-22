"""Offline native-control contract tests; no camera or USB access.

FakeNativeTransport models request/results, not ARM execution or lens physics.
The assembly checks compile the real source and inspect structural safeguards;
they are explicitly not instruction emulation or hardware validation.
"""

from collections import deque
from pathlib import Path
import re
import struct
import unittest
from unittest import mock

import assist_controller
import focus_bridge as b


class FakeNativeTransport:
    def __init__(self):
        self.memory = {b.ECHO: b.ORIGINAL, 0xC3476408: 1,
                       0xC3476414: 0xC0B8EEEC, 0xC32915B0: 14}
        self.position = 10000
        self.minimum = 9000
        self.maximum = 11000
        self.ready = 1
        self.property_predicate = 0
        self.focus_flags = 3
        self.sync_flags = 1
        self.reference_rc = 1
        self.positions = deque()
        self.flags_script = deque()
        self.settings_changed = False
        self.motion_rc = 1
        self.reject_motion = False
        self.timeout_motion = False
        self.stale_nonce = False
        self.exchanges = []
        self.writes = []

    def read(self, address, count=1):
        return [self.memory.get(address + 4 * i, 0) for i in range(count)]

    def ensure(self, address, value):
        self.writes.append((address, value))
        self.memory[address] = value

    def shell(self, command, timeout_ms=1000):
        if command in b.SETTINGS:
            return command + (' changed' if self.settings_changed else ' baseline')
        if command != 'echo' or self.memory[b.ECHO] != b.CODE:
            raise AssertionError('unexpected fake shell request: ' + command)
        if self.memory.get(b.P) != b.MAGIC:
            raise AssertionError('request must be armed exactly once')
        operation = self.memory[b.P + 8]
        target = b.signed(self.memory[b.P + 12])
        expected = b.signed(self.memory[b.P + 16])
        self.exchanges.append((operation, target, expected, timeout_ms))
        self.memory[b.P] = 0
        nonce = self.memory[b.P + 4]
        self.memory[b.P + 0x18] = nonce + int(self.stale_nonce)
        self.memory[b.P + 0x1c] = 1
        if operation >= 7 and self.timeout_motion:
            raise TimeoutError('fake uncertain native wrapper')
        if operation == 0:
            result = self.positions.popleft() if self.positions else self.position
        elif operation in (1, 2, 3, 4):
            result = {1: self.minimum, 2: self.maximum, 3: self.ready,
                      4: self.property_predicate}[operation]
        elif operation in (5, 6):
            result = self.reference_rc
            pattern = (self.flags_script.popleft() if self.flags_script
                       else self.focus_flags) if operation == 5 else self.sync_flags
            if result == 1:
                self.memory[b.P + 0x24] = 0
                self.memory[b.P + 0x28] = 0
                self.memory[b.P + 0x2c] = pattern
        elif operation in (7, 8):
            result = self.motion_rc
        else:
            raise AssertionError('unexpected operation')
        self.memory[b.P + 0x20] = result & 0xffffffff
        self.memory[b.P + 0x1c] = 3 if operation >= 7 and self.reject_motion else 2
        return ''

    @property
    def movement_exchanges(self):
        return [item for item in self.exchanges if item[0] >= 7]


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        if duration < 0:
            raise AssertionError('negative polling sleep')
        self.sleeps.append(duration)
        self.now += duration


class NativeControlTests(unittest.TestCase):
    def setUp(self):
        # A mistaken use of the real transport fails before opening a socket.
        self.socket_guard = mock.patch.object(
            b.socket, 'socket', side_effect=AssertionError('USB/socket access forbidden in tests'))
        self.socket_guard.start()
        self.addCleanup(self.socket_guard.stop)
        self.new_bridge()

    def new_bridge(self):
        self.io = FakeNativeTransport()
        self.events = []
        self.bridge = b.FocusBridge(self.io, b'\0' * 16, self.events.append)
        # Synthetic lease avoids installation, filesystem locks and USB entirely.
        self.bridge.leased = True
        self.bridge.baseline = self.bridge.settings()
        self.bridge.motion_enabled = True

    def assert_no_move(self):
        self.assertEqual(self.io.movement_exchanges, [])

    def test_motion_is_disabled_by_default(self):
        bridge = b.FocusBridge(self.io, b'\0' * 16)
        self.assertFalse(bridge.motion_enabled)
        with self.assertRaises(b.BridgeError):
            bridge.submit_validation_move(10020)
        self.assertEqual(self.io.exchanges, [])

    def test_only_integer_target_is_accepted(self):
        for value in (True, False, 10020.0, '10020', None):
            with self.subTest(target=value), self.assertRaises(b.BridgeError):
                self.bridge.submit_validation_move(value)
        self.assertEqual(self.io.exchanges, [])

    def test_small_move_passes_fresh_expected_position_without_completion_claim(self):
        result = self.bridge.submit_validation_move(10020)
        self.assertEqual(self.io.movement_exchanges, [(7, 10020, 10000, 10000)])
        self.assertEqual(result['from'], 10000)
        self.assertFalse(result['completion_confirmed'])
        self.assertTrue(self.bridge.movement_owned)
        self.assertEqual(self.bridge.motion_origin, 10000)
        self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)

    def test_positive_and_negative_hundred_pulse_edges_are_allowed(self):
        for target in (9900, 10100):
            with self.subTest(target=target):
                self.new_bridge()
                self.bridge.submit_validation_move(target)
                self.assertEqual(self.io.movement_exchanges[0][1], target)

    def test_zero_and_more_than_hundred_pulses_are_rejected(self):
        for target in (10000, 9899, 10101, -(1 << 31), 1 << 31):
            with self.subTest(target=target):
                self.new_bridge()
                with self.assertRaisesRegex(b.BridgeError, 'guard rejected target'):
                    self.bridge.submit_validation_move(target)
                self.assert_no_move()

    def test_native_minimum_and_maximum_are_inclusive(self):
        for target in (9990, 10010):
            with self.subTest(target=target):
                self.new_bridge()
                self.io.minimum, self.io.maximum = 9990, 10010
                self.bridge.submit_validation_move(target)
                self.assertEqual(self.io.movement_exchanges[0][1], target)

    def test_native_limits_reject_small_out_of_range_targets(self):
        for target in (9989, 10011):
            with self.subTest(target=target):
                self.new_bridge()
                self.io.minimum, self.io.maximum = 9990, 10010
                with self.assertRaises(b.BridgeError):
                    self.bridge.submit_validation_move(target)
                self.assert_no_move()

    def test_origin_radius_rejects_small_step_beyond_start_radius(self):
        self.bridge.motion_origin = 10000
        self.io.position = 10080
        with self.assertRaisesRegex(b.BridgeError, 'guard rejected target'):
            self.bridge.submit_validation_move(10110)
        self.assert_no_move()

    def test_signed_negative_position_is_preserved_in_request(self):
        self.io.position, self.io.minimum, self.io.maximum = -100, -300, 300
        result = self.bridge.submit_validation_move(-80)
        self.assertEqual(result['from'], -100)
        self.assertEqual(self.io.movement_exchanges, [(7, -80, -100, 10000)])

    def test_position_changed_after_done_snapshot_is_rejected(self):
        self.io.positions.extend((10000, 10001))
        with self.assertRaisesRegex(b.BridgeError, 'position changed during preflight'):
            self.bridge.submit_validation_move(10020)
        self.assert_no_move()

    def test_each_capture_flag_and_full_shutter_sequence_rejects_move(self):
        cases = [(0xC30338C8, value) for value in (1, 0x100, 0x10000, 0x1000000)]
        cases += [(0xC30338D0, 1), (0xC3033A6C, 1), (0xC3033A6C, 0x10000)]
        for address, value in cases:
            with self.subTest(address=hex(address), value=value):
                self.new_bridge()
                self.io.memory[address] = value
                with self.assertRaisesRegex(b.BridgeError, 'pre-move state'):
                    self.bridge.submit_validation_move(10020)
                self.assert_no_move()

    def test_driver_property_af_route_and_ready_gates(self):
        cases = [('focus_flags', 2), ('sync_flags', 0), ('property_predicate', 1),
                 ('ready', 0), ('reference_rc', 0)]
        for name, value in cases:
            with self.subTest(field=name):
                self.new_bridge()
                setattr(self.io, name, value)
                with self.assertRaises(b.BridgeError):
                    self.bridge.submit_validation_move(10020)
                self.assert_no_move()
        self.new_bridge()
        self.io.memory[0xC32915B0] = 13
        with self.assertRaises(b.BridgeError):
            self.bridge.submit_validation_move(10020)
        self.assert_no_move()

    def test_wrong_native_selector_or_vtable_rejects_before_bridge_calls(self):
        for address in (0xC3476408, 0xC3476414):
            with self.subTest(address=hex(address)):
                self.new_bridge()
                self.io.memory[address] = 0
                with self.assertRaisesRegex(b.BridgeError, 'native-L'):
                    self.bridge.submit_validation_move(10020)
                self.assertEqual(self.io.exchanges, [])

    def test_changed_settings_reject_before_move_without_repair(self):
        self.io.settings_changed = True
        with self.assertRaisesRegex(b.BridgeError, 'pre-move state'):
            self.bridge.submit_validation_move(10020)
        self.assert_no_move()
        self.assertTrue(self.io.settings_changed)

    def test_camera_guard_rejection_clears_ownership_without_retry(self):
        self.io.reject_motion = True
        with self.assertRaises(b.GuardRejected):
            self.bridge.submit_validation_move(10020)
        self.assertEqual(len(self.io.movement_exchanges), 1)
        self.assertFalse(self.bridge.movement_owned)
        self.assertFalse(self.bridge.quarantined)
        self.assertTrue(self.bridge.control_fault)
        with self.assertRaises(b.BridgeError):
            self.bridge.submit_validation_move(10020)
        self.assertEqual(len(self.io.movement_exchanges), 1)

    def test_unconfirmed_owned_move_blocks_submission_even_if_flags_now_done(self):
        self.bridge.movement_owned = True
        self.io.focus_flags = 3
        with self.assertRaises(b.BridgeError):
            self.bridge.submit_validation_move(10020)
        self.assertEqual(self.io.exchanges, [])

    def test_latched_control_fault_blocks_submission_before_any_request(self):
        self.bridge.control_fault = True
        with self.assertRaises(b.BridgeError):
            self.bridge.submit_validation_move(10020)
        self.assertEqual(self.io.exchanges, [])

    def test_uncertain_move_is_quarantined_and_never_redispatched(self):
        self.io.timeout_motion = True
        with self.assertRaises(TimeoutError):
            self.bridge.submit_validation_move(10020)
        self.assertTrue(self.bridge.quarantined)
        self.assertTrue(self.bridge.movement_owned)
        self.assertTrue(self.bridge.control_fault)
        self.assertEqual(len(self.io.movement_exchanges), 1)
        with self.assertRaises(b.BridgeError):
            self.bridge.submit_validation_move(10020)
        with self.assertRaises(b.BridgeError):
            self.bridge.request_validation_stop()
        self.assertEqual(len(self.io.movement_exchanges), 1)
        self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)

    def test_mismatched_nonce_quarantines_a_returned_request(self):
        self.io.stale_nonce = True
        with self.assertRaisesRegex(b.BridgeError, 'matching completion nonce'):
            self.bridge.submit_validation_move(10020)
        self.assertTrue(self.bridge.quarantined)
        self.assert_no_move()

    def test_stop_requires_owned_enabled_movement(self):
        for enabled, owned in ((False, False), (False, True), (True, False)):
            with self.subTest(enabled=enabled, owned=owned):
                self.bridge.motion_enabled, self.bridge.movement_owned = enabled, owned
                with self.assertRaisesRegex(b.BridgeError, 'no owned'):
                    self.bridge.request_validation_stop()
        self.assertEqual(self.io.exchanges, [])

    def test_stop_only_requests_abort_and_never_claims_physical_stop(self):
        self.bridge.movement_owned = True
        result = self.bridge.request_validation_stop()
        self.assertEqual(self.io.movement_exchanges, [(8, 0, 0, 10000)])
        self.assertTrue(result['abort_wrapper_returned'])
        self.assertFalse(result['physical_stop_confirmed'])
        self.assertTrue(self.bridge.movement_owned)

    def test_stop_checks_native_identity_before_dispatch(self):
        self.bridge.movement_owned = True
        self.io.memory[0xC3476408] = 2
        with self.assertRaisesRegex(b.BridgeError, 'native-L'):
            self.bridge.request_validation_stop()
        self.assertEqual(self.io.exchanges, [])

    def test_owned_nonquarantined_fault_still_allows_one_stop_request(self):
        self.bridge.movement_owned = True
        self.bridge.control_fault = True
        result = self.bridge.request_validation_stop()
        self.assertEqual(self.io.movement_exchanges, [(8, 0, 0, 10000)])
        self.assertFalse(result['physical_stop_confirmed'])
        self.assertTrue(self.bridge.control_fault)

    def test_completion_polls_busy_then_requires_two_stable_done_samples(self):
        self.bridge.movement_owned = True
        self.io.position = 10020
        self.io.flags_script.extend((0, 1, 2, 3, 3))
        clock = FakeClock()
        with mock.patch.object(b, 'time', clock):
            result = self.bridge.confirm_done(expected=10020, timeout=1)
        self.assertEqual([poll['flags'] for poll in result['polls']], [0, 1, 2, 3])
        self.assertEqual(result['position'], 10020)
        self.assertTrue(result['native_done'])
        self.assertFalse(result['optical_focus_verified'])
        self.assertFalse(self.bridge.movement_owned)
        self.assert_no_move()

    def test_completion_repolls_when_position_is_not_yet_stable(self):
        self.bridge.movement_owned = True
        self.io.positions.extend((10020, 10021, 10021, 10021))
        with mock.patch.object(b, 'time', FakeClock()):
            result = self.bridge.confirm_done(expected=10021, timeout=1)
        self.assertEqual(len(result['polls']), 2)
        self.assertEqual(result['position'], 10021)

    def test_completion_timeout_requires_finite_positive_number_before_io(self):
        for timeout in (True, False, 0, -1, float('nan'), float('inf'),
                        float('-inf'), '2', None, 10 ** 400):
            with self.subTest(timeout=repr(timeout)):
                self.new_bridge()
                self.bridge.movement_owned = True
                cancel = mock.Mock(return_value=False)
                with mock.patch.object(b, 'time', FakeClock()):
                    with self.assertRaisesRegex(b.BridgeError, 'timeout must be finite and positive'):
                        self.bridge.confirm_done(timeout=timeout, cancel=cancel)
                cancel.assert_not_called()
                self.assertEqual(self.io.exchanges, [])
                self.assertTrue(self.bridge.movement_owned)
                self.assertFalse(self.bridge.control_fault)

    def test_completion_rejects_unrepresentable_deadline_before_io(self):
        clock = FakeClock()
        clock.now = 1e308
        with mock.patch.object(b, 'time', clock):
            with self.assertRaisesRegex(b.BridgeError, 'representable host deadline'):
                self.bridge.confirm_done(timeout=1e308)
        self.assertEqual(self.io.exchanges, [])

    def test_completion_positive_timeout_has_no_new_arbitrary_upper_limit(self):
        with mock.patch.object(b, 'time', FakeClock()):
            result = self.bridge.confirm_done(timeout=60)
        self.assertTrue(result['native_done'])

    def test_slow_successful_flag_or_position_return_is_never_accepted_or_followed(self):
        expected_operations = [5, 0, 5, 0]
        for slow_index in range(1, 5):
            for late_at in (0.1, 0.100001):
                with self.subTest(slow_index=slow_index, late_at=late_at):
                    self.new_bridge()
                    self.bridge.movement_owned = True
                    clock = FakeClock()
                    original_call = self.bridge.call
                    calls = []

                    def slow_call(operation):
                        calls.append(operation)
                        result = original_call(operation)
                        if len(calls) == slow_index:
                            clock.now = late_at
                        return result

                    with mock.patch.object(b, 'time', clock), \
                            mock.patch.object(self.bridge, 'call', side_effect=slow_call):
                        with self.assertRaisesRegex(b.BridgeError, 'host deadline'):
                            self.bridge.confirm_done(expected=10000, timeout=0.1)
                    self.assertEqual(calls, expected_operations[:slow_index])
                    self.assertEqual([item[0] for item in self.io.exchanges], calls)
                    self.assertTrue(self.bridge.control_fault)
                    self.assertTrue(self.bridge.movement_owned)
                    self.assertFalse(any(event['event'] == 'native_completion_observed'
                                         for event in self.events))
                    self.assert_no_move()

    def test_slow_failed_read_preserves_error_but_also_latches_expired_deadline(self):
        self.bridge.movement_owned = True
        clock = FakeClock()
        error = b.BridgeError('fake failed flag reference')

        def failed_flags(operation):
            clock.now = 0.1
            raise error

        with mock.patch.object(b, 'time', clock), \
                mock.patch.object(self.bridge, 'flags', side_effect=failed_flags) as flags:
            with self.assertRaises(b.BridgeError) as raised:
                self.bridge.confirm_done(timeout=0.1)
        self.assertIs(raised.exception, error)
        flags.assert_called_once_with(5)
        self.assertEqual(self.io.exchanges, [])
        self.assertTrue(self.bridge.control_fault)
        self.assertTrue(self.bridge.movement_owned)

    def test_deadline_rechecked_before_first_flag_read(self):
        # Deadline creation and loop-entry check fit, but the pre-call check
        # reaches the deadline. No operation may begin at that point.
        clock = mock.Mock()
        clock.monotonic.side_effect = [0.0, 0.09, 0.1]
        self.bridge.movement_owned = True
        with mock.patch.object(b, 'time', clock):
            with self.assertRaisesRegex(b.BridgeError, 'host deadline'):
                self.bridge.confirm_done(timeout=0.1)
        clock.sleep.assert_not_called()
        self.assertEqual(self.io.exchanges, [])
        self.assertTrue(self.bridge.control_fault)
        self.assertTrue(self.bridge.movement_owned)

    def test_deadline_during_settle_sleep_prevents_second_pair(self):
        self.bridge.movement_owned = True
        clock = FakeClock()
        with mock.patch.object(b, 'time', clock):
            with self.assertRaisesRegex(b.BridgeError, 'host deadline'):
                self.bridge.confirm_done(expected=10000, timeout=0.02)
        self.assertEqual([item[0] for item in self.io.exchanges], [5, 0])
        self.assertEqual(clock.sleeps, [0.02])
        self.assertTrue(self.bridge.control_fault)
        self.assertTrue(self.bridge.movement_owned)

    def test_overslept_settle_is_rejected_before_any_further_read(self):
        self.bridge.movement_owned = True
        clock = FakeClock()

        def oversleep(duration):
            clock.sleeps.append(duration)
            clock.now += duration + 1.0

        clock.sleep = oversleep
        with mock.patch.object(b, 'time', clock):
            with self.assertRaisesRegex(b.BridgeError, 'host deadline'):
                self.bridge.confirm_done(timeout=0.1)
        self.assertEqual([item[0] for item in self.io.exchanges], [5, 0])
        self.assertEqual(clock.sleeps, [0.03])
        self.assertTrue(self.bridge.control_fault)

    def test_busy_pause_uses_remaining_budget_then_stops_without_extra_reads(self):
        self.bridge.movement_owned = True
        self.io.focus_flags = 2
        clock = FakeClock()
        with mock.patch.object(b, 'time', clock):
            with self.assertRaisesRegex(b.BridgeError, 'host deadline'):
                self.bridge.confirm_done(timeout=0.015)
        self.assertEqual([item[0] for item in self.io.exchanges], [5, 0, 5, 0])
        self.assertAlmostEqual(sum(clock.sleeps), 0.015)
        self.assertTrue(all(duration <= 0.01 for duration in clock.sleeps))
        self.assertTrue(self.bridge.control_fault)

    def test_slow_cancel_predicate_cannot_dispatch_abort_after_deadline(self):
        self.bridge.movement_owned = True
        clock = FakeClock()

        def slow_cancel():
            clock.now = 0.1
            return True

        with mock.patch.object(b, 'time', clock):
            with self.assertRaisesRegex(b.BridgeError, 'host deadline'):
                self.bridge.confirm_done(timeout=0.1, cancel=slow_cancel)
        self.assertEqual(self.io.exchanges, [])
        self.assertFalse(self.bridge.abort_attempted)
        self.assertTrue(self.bridge.control_fault)

    def test_late_abort_return_is_not_followed_by_completion_reads(self):
        self.bridge.movement_owned = True
        clock = FakeClock()
        original_stop = self.bridge.request_validation_stop

        def slow_stop():
            result = original_stop()
            clock.now = 0.1
            return result

        with mock.patch.object(b, 'time', clock), \
                mock.patch.object(self.bridge, 'request_validation_stop', side_effect=slow_stop):
            with self.assertRaisesRegex(b.BridgeError, 'host deadline'):
                self.bridge.confirm_done(timeout=0.1, cancel=lambda: True)
        self.assertEqual([item[0] for item in self.io.exchanges], [8])
        self.assertTrue(self.bridge.abort_attempted)
        self.assertTrue(self.bridge.movement_owned)
        self.assertTrue(self.bridge.control_fault)

    def test_done_at_wrong_target_remains_unconfirmed_without_recovery_move(self):
        self.bridge.movement_owned = True
        with mock.patch.object(b, 'time', FakeClock()):
            with self.assertRaisesRegex(b.BridgeError, 'does not match target'):
                self.bridge.confirm_done(expected=10020, timeout=1)
        self.assertTrue(self.bridge.movement_owned)
        self.assertTrue(self.bridge.control_fault)
        self.assert_no_move()
        self.assertFalse(any(event['event'] == 'native_completion_observed'
                             for event in self.events))

    def test_busy_deadline_never_calls_native_wait_or_automatic_abort(self):
        self.bridge.movement_owned = True
        self.io.focus_flags = 2
        clock = FakeClock()
        with mock.patch.object(b, 'time', clock):
            with self.assertRaisesRegex(b.BridgeError, 'host deadline'):
                self.bridge.confirm_done(expected=10020, timeout=0.04)
        self.assertTrue(self.bridge.movement_owned)
        self.assertTrue(self.bridge.control_fault)
        self.assertEqual({operation for operation, *_ in self.io.exchanges}, {0, 5})
        self.assertLessEqual(len(self.io.exchanges), 10)
        self.assert_no_move()

    def test_confirming_later_stop_does_not_clear_prior_fault_latch(self):
        self.bridge.movement_owned = True
        self.io.focus_flags = 2
        with mock.patch.object(b, 'time', FakeClock()):
            with self.assertRaises(b.BridgeError):
                self.bridge.confirm_done(timeout=0.02)
        self.io.focus_flags = 3
        with mock.patch.object(b, 'time', FakeClock()):
            self.bridge.confirm_done(timeout=1)
        self.assertFalse(self.bridge.movement_owned)
        self.assertTrue(self.bridge.control_fault)
        before = list(self.io.exchanges)
        with self.assertRaises(b.BridgeError):
            self.bridge.submit_validation_move(10020)
        self.assertEqual(self.io.exchanges, before)

    def test_other_set_event_bits_do_not_count_as_exact_done_pattern(self):
        self.bridge.movement_owned = True
        self.io.focus_flags = 7
        with mock.patch.object(b, 'time', FakeClock()):
            with self.assertRaisesRegex(b.BridgeError, 'host deadline'):
                self.bridge.confirm_done(timeout=0.02)
        self.assertTrue(self.bridge.movement_owned)
        self.assert_no_move()

    def test_native_zero_return_is_not_mistaken_for_target_completion(self):
        self.io.motion_rc = 0
        submitted = self.bridge.submit_validation_move(10020)
        self.assertFalse(submitted['completion_confirmed'])
        # The wrapper's return is not acceptance/completion proof; the cached
        # position remains at the old target and must fail confirmation.
        with mock.patch.object(b, 'time', FakeClock()):
            with self.assertRaisesRegex(b.BridgeError, 'does not match target'):
                self.bridge.confirm_done(expected=10020, timeout=1)
        self.assertTrue(self.bridge.control_fault)
        self.assertEqual(len(self.io.movement_exchanges), 1)

    def test_failed_event_reference_never_means_completion(self):
        self.bridge.movement_owned = True
        self.io.reference_rc = 0
        with mock.patch.object(b, 'time', FakeClock()):
            with self.assertRaisesRegex(b.BridgeError, 'event-reference failed'):
                self.bridge.confirm_done(timeout=1)
        self.assertTrue(self.bridge.movement_owned)
        self.assert_no_move()


class GainContextContractTests(unittest.TestCase):
    def test_changed_gain_or_capture_context_faults_without_return_motion(self):
        # The native LAB API does not collect gain; this is the controller's
        # settled-observation contract, not an invented native gain guard.
        for field in ('gain', 'context'):
            with self.subTest(field=field):
                class Backend:
                    def __init__(self):
                        self.position = 10000
                        self.moves = []
                        self.stops = 0

                    def observe(self):
                        sample = {'position': self.position, 'h': 1000, 'l': 500,
                                  'gain': [117, 985, 131, 0],
                                  'context': ['capture-idle', 'same-roi'], 'valid': True,
                                  'min_position': 9000, 'max_position': 11000}
                        if self.moves:
                            sample[field] = ['changed']
                        return sample

                    def move_to(self, target):
                        self.moves.append(target)
                        self.position = target
                        return self.observe()

                    def stop(self):
                        self.stops += 1
                        return {'verified': False, 'synthetic': True}

                backend = Backend()
                result = assist_controller.run(backend)
                self.assertEqual(result['status'], 'fault')
                self.assertIn('gain_or_context_changed', result['reason'])
                self.assertEqual(len(backend.moves), 1)
                self.assertEqual(backend.stops, 1)
                self.assertFalse(result['confirmed'])


class RealAssemblyStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.code = b.assemble(root / 'fpSup' / 'fp_usb_shell')
        source = b.SOURCE.read_text()
        cls.instructions = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
        cls.instructions = re.sub(r'\s+', ' ', cls.instructions).lower()

    def test_real_arm_image_is_504_bytes_inside_reserved_512(self):
        self.assertEqual(len(self.code), 504)
        self.assertLessEqual(len(self.code), b.END - b.CODE)
        self.assertEqual(len(self.code) % 4, 0)

    def test_real_image_contains_only_expected_native_motion_entries(self):
        words = struct.unpack('<%dI' % (len(self.code) // 4), self.code)
        for address in (0xC035FFC0, 0xC035FEE8, 0xC036D888, 0xC02DFFB0, 0xC02DFFD0):
            self.assertIn(address, words)
        for forbidden in (0xC035FF08, 0xC04EF7D0, 0xC04EE890):
            self.assertNotIn(forbidden, words)

    def test_single_use_request_and_fixed_operation_bound_are_present(self):
        self.assertIn('str r0, [r4] ldr r5, [r4, #4]', self.instructions)
        self.assertIn('cmp r6, #8 bhi reject', self.instructions)

    def test_overflow_zero_step_bounds_and_expected_position_guards_are_present(self):
        self.assertIn('cmp r0, r1 bne reject subs r0, r7, r0 bvs reject beq reject',
                      self.instructions)
        self.assertIn('rsbmi r0, r0, #0 cmp r0, #100 bhi reject', self.instructions)
        self.assertIn('cmp r7, r0 blt reject', self.instructions)
        self.assertIn('cmp r7, r0 bgt reject', self.instructions)

    def test_capture_ready_and_initialized_flags_guards_are_present(self):
        for text in ('ldr r0, =0xc303384c', 'ldr r1, [r0, #0x7c]',
                     'ldrbeq r1, [r0, #0x84]', 'ldreq r1, [r0, #0x220]',
                     'bl flags cmp r0, #1 bne reject', 'tst r0, #1 beq reject'):
            self.assertIn(text, self.instructions)
        self.assertIn('str r2, [r4, #0x24] str r2, [r4, #0x28] str r2, [r4, #0x2c]',
                      self.instructions)

    def test_both_native_call_sites_keep_stack_eight_byte_aligned(self):
        self.assertIn('push {r4, r5, r6, r7, r8, lr}', self.instructions)
        self.assertIn('push {r8, lr}', self.instructions)
        self.assertIn('pop {r8, pc}', self.instructions)
        self.assertIn('pop {r4, r5, r6, r7, r8, pc}', self.instructions)


if __name__ == '__main__':
    unittest.main()
