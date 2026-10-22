"""Offline host snapshot lease/protocol and sampler-selection regressions.

No USB, daemon, native firmware call or ACK recovery is performed. The fake
handler models result publication only; test_focus_snapshot separately checks
the compiled ARM instruction stream and its restricted instruction model.
"""

import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

import focus_bridge as b
import settled_sampler as sampler
from test_focus_bridge import FakeTransport
from test_settled_sampler import Clock, FakeBridge, FakeIO


class SnapshotTransport(FakeTransport):
    def __init__(self):
        super().__init__()
        self.snapshot_values = [1, 1, 20536, 48700, 1, 1]
        self.snapshot_calls = 0
        self.completion_overrides = {}
        self.corrupt_image_read = None
        self.fail_snapshot_reply = False
        self.fail_result_read = False
        self.fail_cache_owner = None

    def read(self, address, count=1):
        self.calls.append(('read', address, count))
        if self.fail_result_read and address == b.P and count == 15 and self.snapshot_calls:
            raise OSError('fake snapshot result read failed')
        result = super().read(address, count)
        if address == self.corrupt_image_read:
            self.corrupt_image_read = None
            result[0] ^= 1
        return result

    def shell(self, command, timeout_ms=1000):
        owner = self.memory[b.ECHO]
        if command == 'echo' and owner == self.fail_cache_owner:
            self.calls.append(('shell', command, owner))
            raise TimeoutError('fake cache-publication reply failure')
        if command != 'echo' or owner != b.SNAPSHOT:
            return super().shell(command, timeout_ms)
        self.calls.append(('shell', command, owner))
        self.snapshot_calls += 1
        if self.memory[b.P] != b.MAGIC or self.memory[b.P + 8] != 9:
            raise AssertionError('host did not arm the fixed snapshot operation')
        # Published in the same fixed P+00..38 region as the actual helper.
        self.memory[b.P] = 0
        self.memory[b.P + 0x18] = self.memory[b.P + 4]
        self.memory[b.P + 0x1c] = 1
        self.memory[b.P + 0x20] = 0
        for index, value in enumerate(self.snapshot_values):
            self.memory[b.P + 0x24 + 4 * index] = value
        self.memory[b.P + 0x1c] = 2
        self.memory.update({b.P + offset: value
                            for offset, value in self.completion_overrides.items()})
        if self.fail_snapshot_reply:
            # Even valid result words must not turn an uncertain ACK into
            # acceptance or trigger another echo in this implementation.
            raise TimeoutError('fake missing snapshot echo ACK')
        return ''


class SnapshotBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shell_dir = Path(__file__).resolve().parents[2] / 'fpSup' / 'fp_usb_shell'
        cls.control_code = b.assemble(shell_dir)
        cls.snapshot_code = b.assemble(shell_dir, source=b.SNAPSHOT_SOURCE,
                                       max_bytes=b.CODE - b.SNAPSHOT)

    def setUp(self):
        guard = mock.patch.object(b.socket, 'socket',
                                 side_effect=AssertionError('socket/USB forbidden'))
        guard.start()
        self.addCleanup(guard.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Never contend with the actual AF lease while running offline tests.
        lock = mock.patch.object(b, 'LOCK', str(Path(self.temp.name) / 'offline.lock'))
        lock.start()
        self.addCleanup(lock.stop)
        self.make_bridge()

    def make_bridge(self, snapshot=True):
        self.io = SnapshotTransport()
        self.events = []
        self.bridge = b.FocusBridge(self.io, self.control_code, self.events.append,
                                    snapshot_code=self.snapshot_code if snapshot else None)
        self.original = dict(self.io.memory)

    def echoes(self):
        return [item[2] for item in self.io.calls if item[:2] == ('shell', 'echo')]

    def test_images_fit_distinct_approved_subregions(self):
        self.assertEqual(b.SNAPSHOT, 0xC072F740)
        self.assertEqual(b.CODE, 0xC072F800)
        self.assertEqual(len(self.snapshot_code), 152)
        self.assertEqual(len(self.control_code), 504)
        self.assertLessEqual(b.P + 15 * 4, b.SNAPSHOT)
        self.assertLessEqual(b.SNAPSHOT + len(self.snapshot_code), b.CODE)
        self.assertLessEqual(b.CODE + len(self.control_code), b.END)

    def test_snapshot_constructor_rejects_empty_unaligned_and_oversized_images(self):
        for blob in (b'', b'abc', b'\0' * (b.CODE - b.SNAPSHOT + 4)):
            with self.subTest(length=len(blob)), self.assertRaises(b.BridgeError):
                b.FocusBridge(self.io, self.control_code, snapshot_code=blob)
        self.assertEqual(self.io.calls, [])

    def test_lease_upload_verifies_both_images_before_cache_publication(self):
        with self.bridge.lease():
            self.assertEqual(self.io.read(b.CODE, len(self.control_code) // 4),
                             list(struct.unpack('<126I', self.control_code)))
            self.assertEqual(self.io.read(b.SNAPSHOT, len(self.snapshot_code) // 4),
                             list(struct.unpack('<38I', self.snapshot_code)))
            first_publish = self.io.calls.index(('shell', 'echo', b.DCACHE))
            self.assertLess(self.io.calls.index(('read', b.CODE, 126)), first_publish)
            self.assertLess(self.io.calls.index(('read', b.SNAPSHOT, 38)), first_publish)
            self.assertEqual(self.echoes(), [b.DCACHE, b.ICACHE])
            self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)
        self.assertEqual(self.io.memory, self.original)
        self.assertEqual(self.echoes(), [b.DCACHE, b.ICACHE, b.DCACHE, b.ICACHE])
        self.assertTrue(self.bridge.cleanup_complete)
        prepared = next(item for item in self.events if item['event'] == 'lease_prepared')
        self.assertEqual(prepared['snapshot_sha256'], hashlib.sha256(self.snapshot_code).hexdigest())
        self.assertEqual(prepared['code_sha256'], hashlib.sha256(self.control_code).hexdigest())
        self.assertEqual(len(prepared['original_words']), (b.END - b.P) // 4)

    def test_fixed_snapshot_uses_f740_and_preserves_f800_entry_for_public_getters(self):
        with self.bridge.lease():
            self.assertEqual(self.bridge.call(0)[0], 123)
            bracket = self.bridge.read_h_bracket()
            self.assertEqual([bracket[key] for key in ('phase_before', 'mode_before', 'h', 'l',
                                                       'phase_after', 'mode_after')],
                             self.io.snapshot_values)
            self.assertEqual(bracket['method'], 'camera_fixed_copy')
            self.assertEqual(bracket['timing_scope'], 'whole_host_rpc')
            self.assertLessEqual(bracket['started_at'], bracket['finished_at'])
            self.assertEqual(self.echoes(), [b.DCACHE, b.ICACHE, b.CODE, b.SNAPSHOT])
            self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)
        self.assertEqual(self.io.memory, self.original)

    def test_fifteen_word_request_and_result_do_not_touch_gap_or_snapshot_code(self):
        with self.bridge.lease():
            before = dict(self.io.memory)
            offset = len(self.io.calls)
            self.bridge.read_h_bracket()
            calls = self.io.calls[offset:]
            parameter_writes = [item[1] for item in calls if item[0] == 'write' and item[1] != b.ECHO]
            self.assertEqual(parameter_writes, list(range(b.P, b.P + 15 * 4, 4)) + [b.P])
            self.assertEqual([item for item in calls if item[0] == 'read' and item[1] == b.P],
                             [('read', b.P, 15), ('read', b.P, 15)])
            self.assertEqual(self.io.memory[b.P + 8], 9)
            self.assertEqual(self.io.memory[b.P], 0)
            self.assertEqual(self.io.memory[b.P + 0x18], self.io.memory[b.P + 4])
            self.assertEqual(self.io.memory[b.P + 0x1c], 2)
            for address in range(b.P + 0x3c, b.END, 4):
                self.assertEqual(self.io.memory[address], before[address], hex(address))
        self.assertEqual(self.io.memory, self.original)

    def test_public_call_remains_zero_through_six_even_with_snapshot_installed(self):
        with self.bridge.lease():
            for operation in (-1, 7, 8, 9, 10, True, 9.0, '9'):
                before = list(self.io.calls)
                with self.subTest(operation=operation), self.assertRaises(b.BridgeError):
                    self.bridge.call(operation)
                self.assertEqual(self.io.calls, before)
            for operation in range(7):
                self.assertEqual(self.bridge.call(operation)[0], 123)
        self.assertNotIn(b.SNAPSHOT, self.echoes())

    def test_default_bridge_cannot_dispatch_snapshot_or_accept_snapshot_owner(self):
        self.make_bridge(snapshot=False)
        self.assertNotIn(b.SNAPSHOT, self.bridge.known_owners())
        with self.bridge.lease():
            before = list(self.io.calls)
            for operation in (lambda: self.bridge.read_h_bracket(),
                              lambda: self.bridge._dispatch(9), lambda: self.bridge.call(9)):
                with self.assertRaises(b.BridgeError):
                    operation()
            self.assertEqual(self.io.calls, before)
        self.assertEqual(self.io.memory, self.original)
        self.assertNotIn(b.SNAPSHOT, self.echoes())

    def test_snapshot_outside_lease_is_rejected_before_any_io(self):
        with self.assertRaises(b.BridgeError):
            self.bridge.read_h_bracket()
        self.assertEqual(self.io.calls, [])

    def test_corrupt_code_readback_is_not_executed_and_full_lease_is_restored(self):
        for address in (b.CODE, b.SNAPSHOT):
            with self.subTest(address=hex(address)):
                self.make_bridge()
                self.io.corrupt_image_read = address
                with self.assertRaisesRegex(b.BridgeError, 'code verification failed'):
                    with self.bridge.lease():
                        self.fail('unverified image reached leased body')
                self.assertNotIn(b.CODE, self.echoes())
                self.assertNotIn(b.SNAPSHOT, self.echoes())
                self.assertEqual(self.io.memory, self.original)
                self.assertTrue(self.bridge.cleanup_complete)

    def test_cache_publication_failure_quarantines_before_any_snapshot_execution(self):
        self.io.fail_cache_owner = b.ICACHE
        with self.assertRaisesRegex(b.BridgeError, 'scratch retained'):
            with self.bridge.lease():
                self.fail('failed cache publication reached leased body')
        self.assertTrue(self.bridge.quarantined)
        self.assertFalse(self.bridge.cleanup_complete)
        self.assertEqual(self.io.snapshot_calls, 0)
        self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)
        self.assertNotEqual(self.io.memory, self.original)

    def test_nonce_magic_and_invalid_state_results_quarantine_without_repeating_echo(self):
        for override in ({0x18: 0}, {0: b.MAGIC}, {0x1c: 0}, {0x1c: 1},
                         {0x1c: 3}, {0x1c: 4}):
            with self.subTest(override=override):
                self.make_bridge()
                self.io.completion_overrides = override
                with self.assertRaisesRegex(b.BridgeError, 'scratch retained'):
                    with self.bridge.lease():
                        with self.assertRaisesRegex(b.BridgeError, 'matching completion nonce'):
                            self.bridge.read_h_bracket()
                        self.assertTrue(self.bridge.quarantined)
                        with self.assertRaises(b.BridgeError):
                            self.bridge.read_h_bracket()
                self.assertEqual(self.io.snapshot_calls, 1)
                self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)
                self.assertFalse(self.bridge.cleanup_complete)
                self.assertNotEqual(self.io.memory, self.original)

    def test_lost_echo_ack_never_accepts_even_valid_completed_memory_or_retries(self):
        self.io.fail_snapshot_reply = True
        with self.assertRaisesRegex(b.BridgeError, 'scratch retained'):
            with self.bridge.lease():
                with self.assertRaises(TimeoutError):
                    self.bridge.read_h_bracket()
                self.assertEqual(self.io.memory[b.P], 0)
                self.assertEqual(self.io.memory[b.P + 0x18], self.io.memory[b.P + 4])
                self.assertEqual(self.io.memory[b.P + 0x1c], 2)
                self.assertTrue(self.bridge.quarantined)
                with self.assertRaises(b.BridgeError):
                    self.bridge.read_h_bracket()
        self.assertEqual(self.io.snapshot_calls, 1)
        after_echo = self.io.calls[self.io.calls.index(('shell', 'echo', b.SNAPSHOT)) + 1:]
        self.assertNotIn(('read', b.P, 15), after_echo)
        self.assertTrue(all(item[1] == b.ECHO for item in after_echo if item[0] == 'write'))
        self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)

    def test_result_read_failure_quarantines_without_another_echo(self):
        self.io.fail_result_read = True
        with self.assertRaisesRegex(b.BridgeError, 'scratch retained'):
            with self.bridge.lease():
                with self.assertRaises(OSError):
                    self.bridge.read_h_bracket()
                self.assertTrue(self.bridge.quarantined)
        self.assertEqual(self.io.snapshot_calls, 1)
        self.assertFalse(self.bridge.cleanup_complete)

    def test_nonzero_snapshot_return_quarantines_without_retry(self):
        self.io.completion_overrides = {0x20: 1}
        with self.assertRaisesRegex(b.BridgeError, 'scratch retained'):
            with self.bridge.lease():
                with self.assertRaisesRegex(b.BridgeError, 'invalid native snapshot result'):
                    self.bridge.read_h_bracket()
                self.assertTrue(self.bridge.quarantined)
                with self.assertRaises(b.BridgeError):
                    self.bridge.read_h_bracket()
        self.assertEqual(self.io.snapshot_calls, 1)
        self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)
        self.assertFalse(self.bridge.cleanup_complete)
        self.assertNotEqual(self.io.memory, self.original)

    def test_snapshot_wrapper_rejects_wrong_value_count_and_quarantines(self):
        # A malformed dispatcher result must also fail closed, independently
        # of the fixed image's normal six-value publication contract.
        with mock.patch.object(self.bridge, '_dispatch', return_value=(0, [1] * 5)) as dispatch:
            with self.assertRaisesRegex(b.BridgeError, 'invalid native snapshot result'):
                self.bridge.read_h_bracket()
        dispatch.assert_called_once_with(9)
        self.assertTrue(self.bridge.quarantined)
        self.assertEqual(self.io.calls, [])

    def test_unknown_echo_owner_is_not_overwritten_during_snapshot_lease_cleanup(self):
        with self.assertRaisesRegex(b.BridgeError, 'unknown echo'):
            with self.bridge.lease():
                self.io.memory[b.ECHO] = 0xDEADBEEF
        self.assertEqual(self.io.memory[b.ECHO], 0xDEADBEEF)
        self.assertTrue(self.bridge.quarantined)
        self.assertFalse(self.bridge.cleanup_complete)


class SnapshotSamplerSelectionTests(unittest.TestCase):
    def setUp(self):
        guard = mock.patch.object(b.socket, 'socket',
                                 side_effect=AssertionError('socket/USB forbidden'))
        guard.start()
        self.addCleanup(guard.stop)
        self.clock = Clock()
        self.io = FakeIO(self.clock)
        self.bridge = FakeBridge(self.clock)
        self.bridge.snapshot_code = b'installed test image'
        self.camera_calls = []
        self.bridge.read_h_bracket = mock.Mock(side_effect=self.camera_bracket)
        self.io.read_h_bracket = mock.Mock(side_effect=AssertionError('legacy burst must not run'))
        self.subject = sampler.SettledSampler(self.io, self.bridge,
                                              clock=self.clock, sleep=self.clock.sleep)

    def camera_bracket(self):
        started = self.clock.now
        phase = int(started / 0.020) % 3
        self.clock.now += 0.0001
        result = {'phase_before': phase, 'mode_before': 1, 'h': 1000, 'l': 5000,
                  'phase_after': phase, 'mode_after': 1,
                  'started_at': started, 'finished_at': self.clock.now,
                  'method': 'camera_fixed_copy', 'timing_scope': 'whole_host_rpc'}
        self.camera_calls.append(result)
        return result

    def assert_no_scalar_reads(self):
        self.assertEqual(self.io.h_reads, 0)
        self.assertEqual(self.io.l_reads, 0)
        self.assertNotIn((sampler.SCHEDULER, 2), self.io.reads)

    def test_snapshot_preferred_over_legacy_burst_with_method_evidence(self):
        result = self.subject.observe()
        self.assertTrue(result['valid'])
        self.assertEqual(self.bridge.read_h_bracket.call_count, 3)
        self.io.read_h_bracket.assert_not_called()
        self.assert_no_scalar_reads()
        self.assertEqual(result['h'], 1000)
        for sample in result['evidence']['samples']:
            self.assertEqual(sample['capture_method'], 'camera_fixed_copy')
            self.assertEqual(sample['bracket_timing_scope'], 'whole_host_rpc')
        self.assertFalse(result['optical_focus_verified'])
        self.assertFalse(result['exposure_alignment_verified'])

    def test_snapshot_error_never_falls_back_or_retries(self):
        error = b.BridgeError('snapshot completion uncertain')
        self.bridge.read_h_bracket.side_effect = error
        with self.assertRaises(sampler.SamplingError) as raised:
            self.subject.observe()
        self.assertIs(raised.exception.__cause__, error)
        self.bridge.read_h_bracket.assert_called_once_with()
        self.io.read_h_bracket.assert_not_called()
        self.assert_no_scalar_reads()
        self.assertEqual(raised.exception.evidence['samples'], [])

    def test_invalid_snapshot_payload_never_downgrades_to_legacy_burst(self):
        self.bridge.read_h_bracket.side_effect = lambda: dict(self.camera_bracket(), h=True)
        with self.assertRaises(sampler.UnsupportedObservation):
            self.subject.observe()
        self.bridge.read_h_bracket.assert_called_once_with()
        self.io.read_h_bracket.assert_not_called()
        self.assert_no_scalar_reads()

    def test_snapshot_absent_keeps_explicit_legacy_adapter_path(self):
        self.bridge.snapshot_code = None
        self.bridge.read_h_bracket.side_effect = AssertionError('snapshot is not installed')
        self.io.read_h_bracket.side_effect = self.camera_bracket
        result = self.subject.observe()
        self.assertTrue(result['valid'])
        self.bridge.read_h_bracket.assert_not_called()
        self.assertEqual(self.io.read_h_bracket.call_count, 3)
        self.assert_no_scalar_reads()


if __name__ == '__main__':
    unittest.main()
