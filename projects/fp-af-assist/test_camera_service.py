"""Offline service/backend lifecycle tests; no USB or camera operations.

Modules are loaded privately with a temporary sampler import stub. This keeps
the unfinished sampler and sys.modules untouched outside the import context.
Actual sampling and optical focus are deliberately outside these tests.
"""

import contextlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

import focus_bridge as b
from test_native_control import FakeClock, FakeNativeTransport


def private_module(name, filename, imports):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, imports):
        spec.loader.exec_module(module)
    return module


sampler_stub = types.ModuleType('settled_sampler')
sampler_stub.SettledSampler = mock.Mock(name='unconfigured_sampler')
backend_module = private_module('_test_camera_backend_private', 'camera_backend.py',
                                {'settled_sampler': sampler_stub})
service_module = private_module('_test_camera_service_private', 'camera_service.py',
                                {'camera_backend': backend_module})


class FakeIO:
    def __init__(self, socket_path=None, event=None):
        self.event = event or (lambda item: None)
        self.requests = []
        self.responses = {}
        self.transport_faulted = False
        self.anomaly_count = 0

    def request(self, line):
        self.requests.append(line)
        response = self.responses.get(line, b'OK \n')
        if isinstance(response, BaseException):
            raise response
        # A logging error can happen after the command was dispatched.
        self.event({'event': 'exchange', 'request': line})
        return response


class FakeJobBridge:
    instances = []
    cleanup_succeeds = True

    def __init__(self, io, code, event=None, *, snapshot_code=None):
        self.io = io
        self.code = code
        self.event = event
        self.baseline = {'menu SetFocusMode': '0', 'menu SetFocusArea': '0'}
        self.state = {'capture_idle': True, 'native_done': True, 'af_route': 14}
        self.cleanup_complete = False
        self.quarantined = False
        self.motion_enabled = False
        self.confirmations = []
        type(self).instances.append(self)

    @contextlib.contextmanager
    def lease(self):
        try:
            yield self
        finally:
            self.cleanup_complete = type(self).cleanup_succeeds

    def read_state(self):
        return dict(self.state)

    def assert_motion_transport_healthy(self):
        if self.io.transport_faulted:
            raise b.BridgeError('transport anomaly latched')

    def confirm_done(self, **kwargs):
        self.confirmations.append(kwargs)
        return {'native_done': True, 'position': 10000, 'optical_focus_verified': False}


class OfflineCase(unittest.TestCase):
    def setUp(self):
        guard = mock.patch.object(b.socket, 'socket',
                                 side_effect=AssertionError('USB/socket access forbidden'))
        guard.start()
        self.addCleanup(guard.stop)


class CameraServiceTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for patcher in (mock.patch.object(b, 'assemble', return_value=b'\0' * 16),
                        mock.patch.object(b, 'Transport', FakeIO),
                        mock.patch.object(b, 'FocusBridge', FakeJobBridge)):
            patcher.start()
            self.addCleanup(patcher.stop)
        FakeJobBridge.instances = []
        FakeJobBridge.cleanup_succeeds = True
        self.service = service_module.CameraService('/unused', self.directory.name)

    def join_job(self):
        self.service.worker.join(2)
        self.assertFalse(self.service.worker.is_alive(), 'fake job did not finish')

    def test_start_admits_exactly_one_job_during_concurrent_requests(self):
        entered, release = threading.Event(), threading.Event()

        def run(*args):
            entered.set()
            if not release.wait(1):
                raise AssertionError('test failed to release job')
            return {'status': 'completed'}

        with mock.patch.object(service_module, 'CameraBackend'), \
                mock.patch.object(service_module.assist_controller, 'run', side_effect=run):
            self.assertTrue(self.service.start('assist')['ok'])
            try:
                self.assertTrue(entered.wait(1))
                answers = []
                callers = [threading.Thread(target=lambda: answers.append(
                    self.service.start('native'))) for _ in range(8)]
                for caller in callers:
                    caller.start()
                for caller in callers:
                    caller.join(1)
                self.assertEqual(len(answers), 8)
                self.assertTrue(all(answer['ok'] is False for answer in answers))
                self.assertTrue(self.service.status()['busy'])
            finally:
                release.set()
                self.join_job()
        self.assertEqual(len(FakeJobBridge.instances), 1)
        self.assertEqual(FakeJobBridge.instances[0].io.requests, [])

    def test_unknown_kind_does_not_construct_job(self):
        self.assertFalse(self.service.start('fallback')['ok'])
        self.assertIsNone(self.service.worker)
        self.assertEqual(FakeJobBridge.instances, [])

    def test_thread_start_failure_latches_without_permanent_busy_or_invalid_join(self):
        worker = mock.Mock()
        worker.start.side_effect = RuntimeError('fake thread unavailable')
        with mock.patch.object(service_module.threading, 'Thread', return_value=worker):
            result = self.service.start()
        state = self.service.status()
        self.assertFalse(result['ok'])
        self.assertEqual(state['state'], 'fault')
        self.assertEqual(state['outcome']['phase'], 'job_start')
        self.assertFalse(state['busy'])
        self.assertFalse(state['available'])
        self.assertTrue(self.service.fault_latched)
        self.assertTrue(self.service.cancel.is_set())
        self.assertIsNone(self.service.worker)
        self.assertFalse(self.service.start('native')['ok'])
        self.service.close()
        worker.start.assert_called_once_with()
        worker.join.assert_not_called()
        self.assertEqual(FakeJobBridge.instances, [])

    def test_thread_construction_failure_also_commits_terminal_fault(self):
        with mock.patch.object(service_module.threading, 'Thread',
                               side_effect=MemoryError('fake allocation failure')):
            self.assertFalse(self.service.start()['ok'])
        self.assertFalse(self.service.status()['busy'])
        self.assertTrue(self.service.fault_latched)
        self.assertIsNone(self.service.worker)
        self.assertEqual(FakeJobBridge.instances, [])

    def test_private_import_does_not_install_sampler_or_backend_stubs_globally(self):
        self.assertIsNot(sys.modules.get('settled_sampler'), sampler_stub)
        self.assertIsNot(sys.modules.get('camera_backend'), backend_module)

    def test_status_is_a_detached_snapshot_and_has_no_io(self):
        snapshot = self.service.status()
        snapshot['message'] = 'changed'
        self.assertNotEqual(snapshot['message'], self.service.status()['message'])
        self.assertEqual(FakeJobBridge.instances, [])

    def test_http_stop_only_sets_cancel_and_never_dispatches_io(self):
        self.assertTrue(self.service.stop()['ok'])
        self.assertTrue(self.service.cancel.is_set())
        self.assertEqual(FakeJobBridge.instances, [])

    def test_assist_failure_latches_and_never_falls_back_to_original_af(self):
        with mock.patch.object(service_module, 'CameraBackend'), \
                mock.patch.object(service_module.assist_controller, 'run',
                                  side_effect=b.BridgeError('fake failure')), \
                mock.patch.object(self.service, '_original_af') as original:
            self.assertTrue(self.service.start('assist')['ok'])
            self.join_job()
            original.assert_not_called()
        self.assertTrue(self.service.fault_latched)
        self.assertFalse(self.service.status()['available'])
        self.assertFalse(self.service.start('native')['ok'])
        self.assertEqual(FakeJobBridge.instances[0].io.requests, [])

    def test_failed_cleanup_latches_even_after_completed_algorithm(self):
        FakeJobBridge.cleanup_succeeds = False
        with mock.patch.object(service_module, 'CameraBackend'), \
                mock.patch.object(service_module.assist_controller, 'run',
                                  return_value={'status': 'completed'}):
            self.service.start()
            self.join_job()
        self.assertTrue(self.service.fault_latched)
        self.assertFalse(self.service.start()['ok'])

    def test_cancelled_but_unverified_stop_remains_fault_latched(self):
        with mock.patch.object(service_module, 'CameraBackend'), \
                mock.patch.object(service_module.assist_controller, 'run', return_value={
                    'status': 'cancelled', 'stop': {'verified': False}}):
            self.service.start()
            self.join_job()
        self.assertTrue(self.service.fault_latched)
        self.assertFalse(self.service.status()['available'])
        self.assertFalse(self.service.start()['ok'])

    def test_confirmed_cancel_and_cleanup_allow_next_explicit_job(self):
        with mock.patch.object(service_module, 'CameraBackend'), \
                mock.patch.object(service_module.assist_controller, 'run', return_value={
                    'status': 'cancelled', 'stop': {'verified': True}}):
            self.service.start()
            self.join_job()
        self.assertFalse(self.service.fault_latched)
        self.assertTrue(self.service.status()['available'])

    def test_recovered_transport_anomaly_latches_service_even_after_successful_cleanup(self):
        def observed_anomaly(*args, **kwargs):
            io = FakeJobBridge.instances[-1].io
            io.transport_faulted = True
            io.anomaly_count = 1
            return {'status': 'completed', 'confirmed': True}

        with mock.patch.object(service_module, 'CameraBackend'), \
                mock.patch.object(service_module.assist_controller, 'run', side_effect=observed_anomaly):
            self.service.start()
            self.join_job()
        state = self.service.status()
        self.assertEqual(state['outcome']['status'], 'fault')
        self.assertEqual(state['outcome']['status_before_transport_fault'], 'completed')
        self.assertTrue(state['outcome']['cleanup_complete'])
        self.assertTrue(state['outcome']['transport_faulted'])
        self.assertEqual(state['outcome']['transport_anomaly_count'], 1)
        self.assertTrue(self.service.fault_latched)
        self.assertFalse(self.service.start('native')['ok'])
        saved = json.loads((Path(state['capture_path']) / 'result.json').read_text())
        self.assertEqual(saved, state['outcome'])

    def test_explicit_native_job_does_not_enable_assist_motion_or_controller(self):
        with mock.patch.object(self.service, '_original_af',
                               return_value={'status': 'completed'}) as original, \
                mock.patch.object(service_module.assist_controller, 'run') as controller:
            self.service.start('native')
            self.join_job()
            original.assert_called_once()
            controller.assert_not_called()
        self.assertFalse(FakeJobBridge.instances[0].motion_enabled)

    def test_final_notification_failure_preserves_committed_outcome_and_fault_latch(self):
        for status in ('completed', 'fault'):
            with self.subTest(status=status):
                observed = []

                def broken_notification(item):
                    snapshot = self.service.status()
                    observed.append((item['event'], snapshot['state'], snapshot['busy']))
                    self.assertTrue(FakeJobBridge.instances[-1].cleanup_complete)
                    item['outcome']['status'] = 'callback-mutated'
                    raise OSError('fake final notification failure')

                self.service.external_event = broken_notification
                with mock.patch.object(service_module, 'CameraBackend'), \
                        mock.patch.object(service_module.assist_controller, 'run',
                                          return_value={'status': status}):
                    # Direct fake execution exposes an escaping exception to the
                    # test instead of losing it in a background thread warning.
                    self.service._run('assist')
                state = self.service.status()
                self.assertEqual(observed, [('job_finished', status, False)])
                self.assertEqual(state['outcome']['status'], status)
                self.assertEqual(self.service.fault_latched, status == 'fault')
                self.assertEqual(state['available'], status != 'fault')
                self.assertIn('final notification failure', state['notification_error'])
                saved = json.loads((Path(state['capture_path']) / 'result.json').read_text())
                self.assertEqual(saved['status'], status)

    def test_successful_final_callback_cannot_mutate_committed_outcome(self):
        def mutate_notification(item):
            item['outcome']['status'] = 'callback-mutated'

        self.service.external_event = mutate_notification
        with mock.patch.object(service_module, 'CameraBackend'), \
                mock.patch.object(service_module.assist_controller, 'run',
                                  return_value={'status': 'completed'}):
            self.service._run('assist')
        self.assertEqual(self.service.status()['outcome']['status'], 'completed')
        self.assertFalse(self.service.fault_latched)

    def test_late_notification_failure_is_not_attached_to_newer_job(self):
        def replaced_job(item):
            with self.service.lock:
                self.service.state.update(state='checking', busy=True, outcome=None)
            raise OSError('old job notification failed')

        self.service.external_event = replaced_job
        with mock.patch.object(service_module, 'CameraBackend'), \
                mock.patch.object(service_module.assist_controller, 'run',
                                  return_value={'status': 'completed'}):
            self.service._run('assist')
        state = self.service.status()
        self.assertEqual(state['state'], 'checking')
        self.assertNotIn('notification_error', state)


class OriginalAfPairingTests(OfflineCase):
    def setUp(self):
        super().setUp()
        with mock.patch.object(b, 'assemble', return_value=b'\0' * 16):
            self.service = service_module.CameraService('/unused', '/unused')
        self.io = FakeIO()
        self.bridge = FakeJobBridge(self.io, b'')
        self.wait = mock.patch.object(self.service.cancel, 'wait', return_value=False)
        self.wait.start()
        self.addCleanup(self.wait.stop)

    def assert_pair(self):
        self.assertEqual(self.io.requests, ['TMO 1000 SHL key S1ON', 'TMO 1000 SHL key S1OFF'])

    def test_normal_original_af_pairs_press_release_without_focus_claim(self):
        result = self.service._original_af(self.bridge)
        self.assert_pair()
        self.assertTrue(result['half_press_released'])
        self.assertFalse(result['optical_focus_verified'])
        self.assertEqual(self.bridge.confirmations, [{'timeout': 2.0}])

    def test_cancel_before_press_does_not_dispatch_a_key(self):
        self.service.cancel.set()
        result = self.service._original_af(self.bridge)
        self.assertEqual(result, {'status': 'cancelled', 'half_press_sent': False})
        self.assertEqual(self.io.requests, [])

    def test_prior_transport_anomaly_blocks_native_af_before_preflight(self):
        self.io.transport_faulted = True
        with mock.patch.object(self.bridge, 'read_state') as read_state:
            with self.assertRaisesRegex(b.BridgeError, 'transport anomaly'):
                self.service._original_af(self.bridge)
            read_state.assert_not_called()
        self.assertEqual(self.io.requests, [])

    def test_anomaly_recovered_during_preflight_blocks_press_without_spurious_release(self):
        def state_after_error():
            self.io.transport_faulted = True
            self.io.anomaly_count = 1
            return dict(self.bridge.state)

        with mock.patch.object(self.bridge, 'read_state', side_effect=state_after_error):
            with self.assertRaisesRegex(b.BridgeError, 'transport anomaly'):
                self.service._original_af(self.bridge)
        self.assertEqual(self.io.requests, [])

    def test_transport_latch_after_press_does_not_prevent_release(self):
        def mark_after_press(item):
            if item.get('request') == 'TMO 1000 SHL key S1ON':
                self.io.transport_faulted = True
                self.io.anomaly_count = 1

        self.io.event = mark_after_press
        result = self.service._original_af(self.bridge)
        self.assert_pair()
        self.assertTrue(result['half_press_released'])
        self.assertTrue(self.io.transport_faulted)

    def test_cancel_while_holding_still_releases_exactly_once(self):
        self.service.cancel.wait.side_effect = lambda timeout: self.service.cancel.set()
        result = self.service._original_af(self.bridge)
        self.assert_pair()
        self.assertEqual(result['status'], 'cancelled')
        self.assertTrue(result['half_press_released'])

    def test_uncertain_press_is_not_retried_and_release_is_attempted(self):
        for response in (TimeoutError('lost reply'), b'ERR timeout\n', b'OKX 20\n'):
            with self.subTest(response=repr(response)):
                self.io.requests.clear()
                self.io.responses['TMO 1000 SHL key S1ON'] = response
                with self.assertRaises((TimeoutError, b.BridgeError)):
                    self.service._original_af(self.bridge)
                self.assert_pair()
                self.assertEqual(self.bridge.confirmations, [])

    def test_log_failure_after_press_cannot_prevent_release_dispatch(self):
        def broken_log(item):
            raise OSError('fake log unavailable after dispatch')

        self.io.event = broken_log
        with self.assertRaises(OSError):
            self.service._original_af(self.bridge)
        self.assert_pair()
        self.assertEqual(self.bridge.confirmations, [])

    def test_interrupt_during_half_press_wait_still_releases(self):
        self.service.cancel.wait.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.service._original_af(self.bridge)
        self.assert_pair()
        self.assertEqual(self.bridge.confirmations, [])

    def test_unacknowledged_release_is_not_retried_or_reported_completed(self):
        self.io.responses['TMO 1000 SHL key S1OFF'] = b'ERR timeout\n'
        with self.assertRaisesRegex(b.BridgeError, 'S1OFF not acknowledged'):
            self.service._original_af(self.bridge)
        self.assert_pair()
        self.assertEqual(self.bridge.confirmations, [])

    def test_unsupported_capture_af_mode_area_or_busy_rejects_before_press(self):
        cases = [('state', 'capture_idle', False), ('state', 'native_done', False),
                 ('state', 'af_route', 13), ('baseline', 'menu SetFocusMode', '1'),
                 ('baseline', 'menu SetFocusArea', '1')]
        for section, key, value in cases:
            with self.subTest(section=section, field=key):
                bridge = FakeJobBridge(self.io, b'')
                getattr(bridge, section)[key] = value
                with self.assertRaisesRegex(b.BridgeError, 'supported idle'):
                    self.service._original_af(bridge)
                self.assertEqual(self.io.requests, [])


class CameraBackendTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.bridge = mock.Mock()
        self.bridge.io = object()
        self.bridge.quarantined = False
        self.bridge.movement_owned = False
        self.bridge.abort_attempted = False
        self.cancelled = False
        self.cancel = lambda: self.cancelled
        self.sampler = mock.Mock()
        self.sampler.observe.return_value = {'valid': True, 'position': 10000}
        with mock.patch.object(backend_module, 'SettledSampler', return_value=self.sampler):
            self.backend = backend_module.CameraBackend(self.bridge, self.cancel)

    def test_cancel_before_observe_or_move_has_no_device_calls(self):
        self.cancelled = True
        for action in (self.backend.observe, lambda: self.backend.move_to(10020)):
            with self.assertRaises(b.BridgeError):
                action()
        self.bridge.submit_validation_move.assert_not_called()
        self.sampler.observe.assert_not_called()

    def test_move_waits_for_target_with_cancel_then_observes(self):
        self.bridge.confirm_done.return_value = {'native_done': True}
        result = self.backend.move_to(10020)
        self.bridge.submit_validation_move.assert_called_once_with(10020)
        self.bridge.confirm_done.assert_called_once_with(expected=10020, cancel=self.cancel)
        self.assertEqual(result, self.sampler.observe.return_value)

    def test_cancel_after_completion_never_takes_another_sample(self):
        def finish(**kwargs):
            self.cancelled = True
            return {'native_done': True}

        self.bridge.confirm_done.side_effect = finish
        with self.assertRaisesRegex(b.BridgeError, 'cancelled after'):
            self.backend.move_to(10020)
        self.sampler.observe.assert_not_called()

    def test_quarantine_prevents_stop_redispatch(self):
        self.bridge.quarantined = True
        self.bridge.movement_owned = True
        result = self.backend.stop()
        self.assertFalse(result['verified'])
        self.bridge.request_validation_stop.assert_not_called()
        self.bridge.confirm_done.assert_not_called()

    def test_owned_stop_requests_abort_and_confirms_without_position_target(self):
        self.bridge.movement_owned = True
        self.bridge.confirm_done.return_value = {'native_done': True, 'position': 10007}
        result = self.backend.stop()
        self.bridge.request_validation_stop.assert_called_once_with()
        self.bridge.confirm_done.assert_called_once_with()
        self.assertTrue(result['verified'])
        self.assertFalse(result['optical_stop_verified'])

    def test_unowned_stop_only_reads_flags_and_position(self):
        self.bridge.flags.return_value = 3
        self.bridge.call.return_value = (10000, [])
        result = self.backend.stop()
        self.bridge.request_validation_stop.assert_not_called()
        self.bridge.flags.assert_called_once_with(5)
        self.bridge.call.assert_called_once_with(0)
        self.assertTrue(result['verified'])


class CancellationPollingTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.io = FakeNativeTransport()
        self.bridge = b.FocusBridge(self.io, b'\0' * 16)
        self.bridge.leased = True
        self.bridge.motion_enabled = True
        self.bridge.movement_owned = True

    def test_cancel_sends_one_abort_then_confirms_any_stable_stop_position(self):
        self.io.flags_script.extend((2, 2, 3, 3))
        with mock.patch.object(b, 'time', FakeClock()):
            result = self.bridge.confirm_done(expected=10020, timeout=1, cancel=lambda: True)
        self.assertEqual([item[0] for item in self.io.movement_exchanges], [8])
        self.assertTrue(result['cancel_stop_requested'])
        self.assertEqual(result['position'], 10000)
        self.assertFalse(self.bridge.movement_owned)

    def test_cancel_does_not_abort_an_unowned_movement(self):
        self.bridge.movement_owned = False
        with mock.patch.object(b, 'time', FakeClock()):
            result = self.bridge.confirm_done(timeout=1, cancel=lambda: True)
        self.assertEqual(self.io.movement_exchanges, [])
        self.assertFalse(result['cancel_stop_requested'])

    def test_uncertain_cancel_abort_is_quarantined_without_second_attempt(self):
        self.io.timeout_motion = True
        with mock.patch.object(b, 'time', FakeClock()):
            with self.assertRaises(TimeoutError):
                self.bridge.confirm_done(timeout=1, cancel=lambda: True)
        with mock.patch.object(backend_module, 'SettledSampler'):
            backend = backend_module.CameraBackend(self.bridge)
        result = backend.stop()
        self.assertFalse(result['verified'])
        self.assertEqual([item[0] for item in self.io.movement_exchanges], [8])

    def test_timeout_after_cancel_abort_does_not_redispatch_abort_in_backend_stop(self):
        self.io.focus_flags = 2
        with mock.patch.object(b, 'time', FakeClock()):
            with self.assertRaisesRegex(b.BridgeError, 'host deadline'):
                self.bridge.confirm_done(timeout=0.02, cancel=lambda: True)
        self.io.focus_flags = 3
        with mock.patch.object(backend_module, 'SettledSampler'):
            backend = backend_module.CameraBackend(self.bridge)
        with mock.patch.object(b, 'time', FakeClock()):
            result = backend.stop()
        self.assertTrue(result['verified'])
        self.assertEqual([item[0] for item in self.io.movement_exchanges], [8])

    def test_log_failure_after_abort_dispatch_does_not_cause_second_abort(self):
        def fail_abort_log(item):
            if item.get('event') == 'bridge_call_returned' and item.get('operation') == 8:
                raise OSError('fake log failure after acknowledged abort')

        self.bridge.event = fail_abort_log
        with mock.patch.object(b, 'time', FakeClock()):
            with self.assertRaises(OSError):
                self.bridge.confirm_done(timeout=1, cancel=lambda: True)
        self.assertTrue(self.bridge.abort_attempted)
        self.assertFalse(self.bridge.quarantined)
        with mock.patch.object(backend_module, 'SettledSampler'):
            backend = backend_module.CameraBackend(self.bridge)
        with mock.patch.object(b, 'time', FakeClock()):
            result = backend.stop()
        self.assertTrue(result['verified'])
        self.assertEqual([item[0] for item in self.io.movement_exchanges], [8])


if __name__ == '__main__':
    unittest.main()
