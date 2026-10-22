"""Offline sticky transport-health and not-dispatched motion regressions.

All sockets are replaced or forbidden. No USB, daemon, firmware execution,
lost-ACK recovery, or physical movement is performed by these tests.
"""

from pathlib import Path
import tempfile
import unittest
from unittest import mock

import focus_bridge as b
from test_focus_bridge import FakeTransport
from test_native_control import FakeNativeTransport
from test_transport_pacing import Clock, Connection
import test_transport_pacing as pacing


class StickyTransportTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.connections = []
        self.socket_calls = 0
        for patcher in (mock.patch.object(b.time, 'monotonic', self.clock.monotonic),
                        mock.patch.object(b.time, 'sleep', self.clock.sleep),
                        mock.patch.object(b.socket, 'socket', self.socket)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.transport = b.Transport()

    def socket(self, *args):
        self.socket_calls += 1
        if not self.connections:
            raise AssertionError('unplanned socket/retry forbidden')
        return self.connections.pop(0)

    def connection(self, **kwargs):
        connection = Connection(self.clock, **kwargs)
        self.connections.append(connection)
        return connection

    def memory_connection(self, address, words):
        return self.connection(reply=pacing.TransportPacingTests.memory_reply(address, words))

    def assert_faulted(self, count=1):
        self.assertTrue(self.transport.transport_faulted)
        self.assertEqual(self.transport.anomaly_count, count)
        before = self.socket_calls
        with self.assertRaisesRegex(b.BridgeError, 'new motion prohibited'):
            self.transport.assert_motion_transport_healthy()
        self.assertEqual(self.socket_calls, before)

    def test_health_initially_clear_and_public_properties_cannot_reset_it(self):
        self.assertFalse(self.transport.transport_faulted)
        self.assertEqual(self.transport.anomaly_count, 0)
        self.transport.assert_motion_transport_healthy()
        self.connection(fail='receive')
        with self.assertRaises(TimeoutError):
            self.transport.request('uncertain')
        for name, value in (('transport_faulted', False), ('anomaly_count', 0)):
            with self.subTest(name=name), self.assertRaises(AttributeError):
                setattr(self.transport, name, value)
        self.assert_faulted()

    def test_each_exchange_failure_latches_once_without_retry(self):
        for failure in ('connect', 'send', 'receive'):
            with self.subTest(failure=failure):
                self.transport = b.Transport()
                self.connection(fail=failure)
                before = self.socket_calls
                with self.assertRaises(OSError):
                    self.transport.request('uncertain')
                self.assertEqual(self.socket_calls, before + 1)
                self.assert_faulted()

    def test_raw_error_reply_latches_even_without_shell_decoder(self):
        self.connection(reply=b'ERR mock firmware/transport error\n')
        with self.assertRaises(b.BridgeError):
            self.transport.request('one request')
        self.assert_faulted()
        self.assertEqual(self.socket_calls, 1)

    def test_shell_error_is_counted_once_not_again_by_decoder(self):
        self.connection(reply=b'ERR mock shell error\n')
        with self.assertRaises(b.BridgeError):
            self.transport.shell('echo')
        self.assert_faulted()

    def test_oversized_reply_and_deadline_failure_are_sticky(self):
        for kwargs in ({'reply': b'x' * 16385}, {'latency': 1.1}):
            with self.subTest(kwargs=list(kwargs)):
                self.transport = b.Transport()
                self.connection(**kwargs)
                with self.assertRaises((b.BridgeError, TimeoutError)):
                    self.transport.request('once', timeout=1.0)
                self.assert_faulted()

    def test_shell_decode_errors_latch_and_are_not_retried(self):
        for raw in (b'OKX nothex\n', b'OKX 0\n', b'OK \xff\n', b'', b'garbage\n'):
            with self.subTest(raw=raw):
                self.transport = b.Transport()
                self.connection(reply=raw)
                before = self.socket_calls
                with self.assertRaises((b.BridgeError, UnicodeError)):
                    self.transport.shell('echo')
                self.assertEqual(self.socket_calls, before + 1)
                self.assert_faulted()

    def test_successful_diagnostics_never_clear_prior_failure_or_count(self):
        self.connection(fail='receive')
        with self.assertRaises(TimeoutError):
            self.transport.request('uncertain')
        self.memory_connection(b.P, [42])
        self.assertEqual(self.transport.read(b.P), [42])
        self.connection(reply=b'OK read-only version\n')
        self.assertEqual(self.transport.shell('version'), 'read-only version')
        self.assert_faulted()

    def test_each_new_anomaly_increments_count_after_success(self):
        self.connection(reply=b'ERR first\n')
        self.connection(reply=b'OK success\n')
        self.connection(reply=b'ERR second\n')
        with self.assertRaises(b.BridgeError):
            self.transport.request('one')
        self.transport.request('diagnostic')
        with self.assertRaises(b.BridgeError):
            self.transport.request('two')
        self.assert_faulted(2)

    def test_successful_idempotent_read_retry_does_not_restore_health(self):
        self.connection(fail='receive')
        self.memory_connection(b.P, [42])
        self.assertEqual(self.transport.read(b.P), [42])
        self.assertEqual(self.socket_calls, 2)
        self.assert_faulted()

    def test_ensure_rechecks_uncertain_write_without_blind_resend_or_health_reset(self):
        self.memory_connection(b.P, [0])
        failed_write = self.connection(fail='receive')
        self.memory_connection(b.P, [42])
        self.transport.ensure(b.P, 42)
        self.assertEqual(failed_write.sent, [b'TMO 1000 SHL mem set 0xC072F700 0x0000002A\n'])
        self.assertEqual(self.socket_calls, 3)
        self.assert_faulted()

    def test_ensure_remains_available_after_fault_for_verified_restoration(self):
        self.connection(reply=b'ERR prior\n')
        with self.assertRaises(b.BridgeError):
            self.transport.request('diagnostic')
        self.memory_connection(b.ECHO, [b.CODE])
        self.connection(reply=b'OK \n')
        self.memory_connection(b.ECHO, [b.ORIGINAL])
        self.transport.ensure(b.ECHO, b.ORIGINAL)
        self.assert_faulted()

    def test_unrepaired_word_readback_failure_latches_without_extra_writes(self):
        for _ in range(3):
            self.memory_connection(b.P, [0])
            self.connection(reply=b'OK \n')
        self.memory_connection(b.P, [0])
        with self.assertRaisesRegex(b.BridgeError, 'RAM readback failed'):
            self.transport.ensure(b.P, 42)
        self.assertEqual(self.socket_calls, 7)
        self.assert_faulted()

    def test_memory_format_errors_latch_without_parse_retry(self):
        bad = [b'OK \n', b'OK A:0xc072f704, D:0x1\\n\n',
               b'OK A:0xc072f700, D:0x100000000\\n\n',
               b'OK A:0xc072f700, D:0x1 extra\\n\n',
               b'OK A:0xc072f700, D:0x1\\nA:0xc072f700, D:0x1\\n\n']
        for raw in bad:
            with self.subTest(raw=raw):
                self.transport = b.Transport()
                self.connection(reply=raw)
                before = self.socket_calls
                with self.assertRaises(b.BridgeError):
                    self.transport.read(b.P)
                self.assertEqual(self.socket_calls, before + 1)
                self.assert_faulted()

    def test_fixed_legacy_bracket_parse_failure_latches_without_following_reads(self):
        self.memory_connection(0xC31F8CB4, [1, 1])
        self.connection(reply=b'OK malformed H word\n')
        with self.assertRaises(b.BridgeError):
            self.transport.read_h_bracket()
        self.assertEqual(self.socket_calls, 2)
        self.assert_faulted()

    def test_failed_event_sink_latches_and_does_not_mask_original_io_failure(self):
        self.transport.event = mock.Mock(side_effect=ValueError('log failure'))
        self.connection(fail='receive')
        with self.assertRaisesRegex(TimeoutError, 'mock uncertain receive'):
            self.transport.request('once')
        self.assert_faulted()

    def test_failed_event_sink_after_reply_is_also_sticky(self):
        self.transport.event = mock.Mock(side_effect=ValueError('log failure'))
        self.connection()
        with self.assertRaisesRegex(ValueError, 'log failure'):
            self.transport.request('once')
        self.assert_faulted()

    def test_invalid_local_arguments_do_not_claim_transport_anomaly(self):
        with self.assertRaises(ValueError):
            self.transport.read(b.P, 0)
        with self.assertRaises(ValueError):
            self.transport.ensure(0, 1)
        self.assertFalse(self.transport.transport_faulted)
        self.assertEqual(self.transport.anomaly_count, 0)
        self.assertEqual(self.socket_calls, 0)


class MotionTransportGuardTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(b.socket, 'socket',
                                    side_effect=AssertionError('USB/socket forbidden'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.io = FakeNativeTransport()
        self.io.transport_faulted = False
        self.io.anomaly_count = 0
        self.bridge = b.FocusBridge(self.io, b'\0' * 16)
        self.bridge.leased = True
        self.bridge.motion_enabled = True
        self.bridge.baseline = self.bridge.settings()

    def fault(self):
        self.io.transport_faulted = True
        self.io.anomaly_count += 1

    def assert_not_dispatched(self):
        with self.assertRaises(b.MotionNotDispatched) as raised:
            self.bridge.submit_validation_move(10020)
        self.assertEqual(raised.exception.dispatch_state, 'NOT_DISPATCHED')
        self.assertEqual(self.io.movement_exchanges, [])
        self.assertFalse(self.bridge.movement_owned)
        self.assertTrue(self.bridge.control_fault)
        self.assertFalse(self.bridge.quarantined)
        with self.assertRaisesRegex(b.BridgeError, 'no owned'):
            self.bridge.request_validation_stop()
        self.assertEqual(self.io.movement_exchanges, [])

    def during_move_dispatch(self, function):
        dispatch = self.bridge._dispatch

        def wrapper(operation, *args):
            if operation == 7:
                return function(lambda: dispatch(operation, *args))
            return dispatch(operation, *args)

        patcher = mock.patch.object(self.bridge, '_dispatch', side_effect=wrapper)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_initial_fault_blocks_before_any_preflight_io(self):
        self.fault()
        with mock.patch.object(self.bridge, 'read_state') as state:
            with self.assertRaisesRegex(b.BridgeError, 'new motion prohibited'):
                self.bridge.submit_validation_move(10020)
        state.assert_not_called()
        self.assertEqual(self.io.exchanges, [])
        self.assertEqual(self.io.writes, [])
        self.assertFalse(self.bridge.movement_owned)

    def test_public_health_guard_supports_existing_transport_fakes(self):
        del self.io.transport_faulted
        self.bridge.assert_motion_transport_healthy()
        self.bridge.submit_validation_move(10020)
        self.assertEqual([item[0] for item in self.io.movement_exchanges], [7])

    def test_recovered_preflight_fault_blocks_final_dispatch(self):
        state = self.bridge.read_state

        def recovered_state():
            result = state()
            self.fault()
            return result

        with mock.patch.object(self.bridge, 'read_state', side_effect=recovered_state):
            self.assert_not_dispatched()

    def test_recovered_parameter_write_fault_never_executes_motion(self):
        ensure = self.io.ensure

        def run(dispatch):
            def write(address, value):
                ensure(address, value)
                if address == b.P + 12:
                    self.fault()  # Idempotent ensure recovered, but stays unhealthy.
            with mock.patch.object(self.io, 'ensure', side_effect=write):
                return dispatch()

        self.during_move_dispatch(run)
        self.assert_not_dispatched()
        self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)

    def test_parameter_write_exception_is_not_dispatched_and_cannot_abort(self):
        ensure = self.io.ensure

        def run(dispatch):
            def write(address, value):
                if address == b.P + 12:
                    self.fault()
                    raise OSError('parameter preparation failed')
                ensure(address, value)
            with mock.patch.object(self.io, 'ensure', side_effect=write):
                return dispatch()

        self.during_move_dispatch(run)
        self.assert_not_dispatched()
        self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)

    def test_request_readback_exception_is_not_dispatched(self):
        read = self.io.read

        def run(dispatch):
            def memory(address, count=1):
                if address == b.P and count == 12:
                    self.fault()
                    raise OSError('request readback failed')
                return read(address, count)
            with mock.patch.object(self.io, 'read', side_effect=memory):
                return dispatch()

        self.during_move_dispatch(run)
        self.assert_not_dispatched()

    def test_request_readback_mismatch_is_not_dispatched(self):
        read = self.io.read

        def run(dispatch):
            def memory(address, count=1):
                result = read(address, count)
                if address == b.P and count == 12:
                    result[0] ^= 1
                return result
            with mock.patch.object(self.io, 'read', side_effect=memory):
                return dispatch()

        self.during_move_dispatch(run)
        self.assert_not_dispatched()

    def test_recovered_echo_pointer_write_fault_is_checked_after_preparation(self):
        ensure = self.io.ensure

        def run(dispatch):
            def write(address, value):
                ensure(address, value)
                if address == b.ECHO and value == b.CODE:
                    self.fault()
            with mock.patch.object(self.io, 'ensure', side_effect=write):
                return dispatch()

        self.during_move_dispatch(run)
        self.assert_not_dispatched()
        self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)

    def test_uncertain_echo_pointer_write_is_not_a_lens_dispatch(self):
        ensure = self.io.ensure

        def run(dispatch):
            def write(address, value):
                ensure(address, value)
                if address == b.ECHO and value == b.CODE:
                    self.fault()
                    raise TimeoutError('pointer write ACK missing, echo not called')
            with mock.patch.object(self.io, 'ensure', side_effect=write):
                return dispatch()

        self.during_move_dispatch(run)
        self.assert_not_dispatched()
        self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)

    def test_unknown_echo_owner_preparation_never_aborts_or_overwrites_it(self):
        def run(dispatch):
            self.io.memory[b.ECHO] = 0xDEADBEEF
            return dispatch()

        self.during_move_dispatch(run)
        self.assert_not_dispatched()
        self.assertEqual(self.io.memory[b.ECHO], 0xDEADBEEF)

    def test_actual_echo_timeout_keeps_uncertain_ownership_and_quarantine(self):
        self.io.timeout_motion = True
        with self.assertRaises(TimeoutError) as raised:
            self.bridge.submit_validation_move(10020)
        self.assertNotIsInstance(raised.exception, b.MotionNotDispatched)
        self.assertTrue(self.bridge.movement_owned)
        self.assertTrue(self.bridge.quarantined)
        self.assertEqual([item[0] for item in self.io.movement_exchanges], [7])
        with self.assertRaises(b.BridgeError):
            self.bridge.request_validation_stop()
        self.assertEqual([item[0] for item in self.io.movement_exchanges], [7])

    def test_owned_stop_and_getters_remain_available_after_fault(self):
        self.bridge.submit_validation_move(10020)
        self.fault()
        self.assertEqual(self.bridge.call(0)[0], 10000)
        result = self.bridge.request_validation_stop()
        self.assertTrue(result['native_abort_accepted'])
        self.assertFalse(result['physical_stop_confirmed'])
        self.assertEqual([item[0] for item in self.io.movement_exchanges], [7, 8])
        with self.assertRaisesRegex(b.BridgeError, 'already attempted'):
            self.bridge.request_validation_stop()
        self.assertTrue(self.io.transport_faulted)

    def test_fault_after_successful_motion_forbids_next_move_even_after_completion(self):
        self.bridge.submit_validation_move(10020)
        self.io.position = 10020
        self.fault()
        with mock.patch.object(b.time, 'sleep'):
            self.assertTrue(self.bridge.confirm_done(expected=10020)['native_done'])
        self.assertFalse(self.bridge.movement_owned)
        before = list(self.io.exchanges)
        with self.assertRaisesRegex(b.BridgeError, 'new motion prohibited'):
            self.bridge.submit_validation_move(10000)
        self.assertEqual(self.io.exchanges, before)
        self.assertTrue(self.io.transport_faulted)

    def test_faulted_lease_can_restore_exact_scratch_without_clearing_health(self):
        io = FakeTransport()
        io.transport_faulted = False
        io.anomaly_count = 0
        bridge = b.FocusBridge(io, b'\0' * 16)
        original = dict(io.memory)
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(b, 'LOCK', str(Path(directory) / 'offline.lock')):
                with bridge.lease():
                    io.transport_faulted = True
                    io.anomaly_count = 1
                    self.assertEqual(bridge.call(0)[0], 123)
        self.assertEqual(io.memory, original)
        self.assertTrue(bridge.cleanup_complete)
        self.assertTrue(io.transport_faulted)
        self.assertEqual(io.anomaly_count, 1)
        with self.assertRaisesRegex(b.BridgeError, 'new motion prohibited'):
            bridge.assert_motion_transport_healthy()


if __name__ == '__main__':
    unittest.main()
