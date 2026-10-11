"""Transport pacing tests: entirely fake clock/socket, no camera or daemon."""
import unittest
from unittest import mock

import focus_bridge as bridge


class Clock:
    def __init__(self):
        self.now = 10.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        if duration < 0:
            raise AssertionError("negative sleep")
        self.sleeps.append(duration)
        self.now += duration


class Connection:
    def __init__(self, clock, *, fail=None, reply=b"OK \n", latency=0.001):
        self.clock = clock
        self.fail = fail
        self.reply = reply
        self.latency = latency
        self.connected_at = None
        self.closed_at = None
        self.sent = []
        self.timeouts = []
        self.receives = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed_at = self.clock.now

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def connect(self, path):
        self.connected_at = self.clock.now
        if self.fail == "connect":
            self.clock.now += self.latency
            raise OSError("mock connect failure")

    def sendall(self, data):
        self.sent.append(data)
        if self.fail == "send":
            self.clock.now += self.latency
            raise OSError("mock send failure")

    def recv(self, size):
        self.receives += 1
        self.clock.now += self.latency
        if self.fail == "receive":
            raise TimeoutError("mock uncertain receive")
        return self.reply if self.receives == 1 else b""


class TransportPacingTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.events = []
        self.connections = []
        self.socket_calls = []
        self.monotonic_patch = mock.patch.object(bridge.time, "monotonic", self.clock.monotonic)
        self.sleep_patch = mock.patch.object(bridge.time, "sleep", self.clock.sleep)
        self.socket_patch = mock.patch.object(bridge.socket, "socket", self.socket)
        for patch in (self.monotonic_patch, self.sleep_patch, self.socket_patch):
            patch.start()
            self.addCleanup(patch.stop)

    def socket(self, *args):
        self.socket_calls.append(args)
        if not self.connections:
            raise AssertionError("unexpected socket creation / retry")
        return self.connections.pop(0)

    def connection(self, **kwargs):
        item = Connection(self.clock, **kwargs)
        self.connections.append(item)
        return item

    def transport(self, **kwargs):
        return bridge.Transport(event=self.events.append, **kwargs)

    def test_first_exchange_has_no_artificial_wait(self):
        connection = self.connection()
        transport = self.transport()
        self.assertEqual(transport.request("PING"), b"OK \n")
        self.assertEqual(connection.connected_at, 10.0)
        self.assertEqual(self.clock.sleeps, [])
        self.assertEqual(connection.sent, [b"PING\n"])
        self.assertEqual(len(self.socket_calls), 1)

    def test_success_gap_measured_from_completion_not_start(self):
        first = self.connection(latency=0.008)
        second = self.connection()
        transport = self.transport(spacing_s=0.005)
        transport.request("first")
        transport.request("second")
        self.assertAlmostEqual(second.connected_at - first.closed_at, 0.005)
        self.assertGreater(second.connected_at - first.connected_at, 0.016)

    def test_partial_existing_gap_only_sleeps_remainder(self):
        first = self.connection()
        second = self.connection()
        transport = self.transport(spacing_s=0.010)
        transport.request("first")
        self.clock.now += 0.004
        transport.request("second")
        self.assertAlmostEqual(self.clock.sleeps[-1], 0.006)
        self.assertAlmostEqual(second.connected_at - first.closed_at, 0.010)

    def test_completed_gap_does_not_add_another_full_interval(self):
        self.connection()
        second = self.connection()
        transport = self.transport(spacing_s=0.005)
        transport.request("first")
        self.clock.now += 0.020
        before = self.clock.now
        transport.request("second")
        self.assertEqual(second.connected_at, before)
        self.assertEqual(self.clock.sleeps[-1], 0)

    def test_failure_preserves_gap_and_never_retries_request(self):
        for failure in ("connect", "send", "receive"):
            with self.subTest(failure=failure):
                failed = self.connection(fail=failure)
                second = self.connection()
                transport = self.transport(spacing_s=0.010)
                calls_before = len(self.socket_calls)
                with self.assertRaises(OSError):
                    transport.request("uncertain")
                self.assertEqual(len(self.socket_calls) - calls_before, 1)
                self.assertEqual(self.events[-1]["event"], "exchange_uncertain")
                transport.request("independent read")
                self.assertAlmostEqual(second.connected_at - failed.closed_at, 0.010)
                self.assertLessEqual(len(failed.sent), 1)

    def test_uncertain_echo_shell_is_not_redispatched(self):
        connection = self.connection(fail="receive")
        transport = self.transport()
        with self.assertRaises(TimeoutError):
            transport.shell("echo")
        self.assertEqual(connection.sent, [b"TMO 1000 SHL echo\n"])
        self.assertEqual(len(self.socket_calls), 1)

    def test_error_reply_keeps_spacing_without_request_retry(self):
        first = self.connection(reply=b"ERR mock rejection\n")
        second = self.connection()
        transport = self.transport()
        with self.assertRaises(bridge.BridgeError):
            transport.shell("echo")
        self.assertEqual(len(self.socket_calls), 1)
        transport.request("next")
        self.assertAlmostEqual(second.connected_at - first.closed_at, 0.005)

    def test_oversized_reply_fails_once_then_paces_next_request(self):
        first = self.connection(reply=b"x" * 16385)
        second = self.connection()
        transport = self.transport()
        with self.assertRaisesRegex(bridge.BridgeError, "oversized"):
            transport.request("large reply")
        self.assertEqual(first.receives, 1)
        self.assertEqual(len(self.socket_calls), 1)
        transport.request("next")
        self.assertAlmostEqual(second.connected_at - first.closed_at, 0.005)

    def test_deadline_failure_is_not_retried_and_next_exchange_paced(self):
        first = self.connection(latency=0.03)
        second = self.connection()
        transport = self.transport()
        with self.assertRaisesRegex(TimeoutError, "outcome uncertain"):
            transport.request("slow reply", timeout=0.02)
        self.assertEqual(len(self.socket_calls), 1)
        transport.request("next")
        self.assertAlmostEqual(second.connected_at - first.closed_at, 0.005)

    def test_pacing_wait_is_outside_exchange_timeout(self):
        self.connection()
        second = self.connection(latency=0.0001)
        transport = self.transport(spacing_s=0.020)
        transport.request("first")
        transport.request("second", timeout=0.001)
        self.assertEqual(second.timeouts[0], 0.001)
        self.assertLess(self.events[-1]["elapsed_s"], 0.001)

    def test_failed_event_sink_does_not_hide_original_transport_error(self):
        self.connection(fail="receive")
        transport = bridge.Transport(event=lambda _: (_ for _ in ()).throw(ValueError("log")))
        with self.assertRaisesRegex(TimeoutError, "mock uncertain receive"):
            transport.request("once")
        self.assertEqual(len(self.socket_calls), 1)
        self.assertIsNotNone(transport._last_exchange_end)

    def test_spacing_bounds_and_types(self):
        for value in (0.005, 0.020, 0.012):
            self.assertEqual(self.transport(spacing_s=value).spacing_s, value)
        for value in (0, -1, 0.004999, 0.020001, True, False, "0.005", None,
                      float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.transport(spacing_s=value)
        self.assertEqual(self.socket_calls, [])

    @staticmethod
    def memory_reply(address, words, *, hex_encoded=False):
        text = ''.join('get : A:0x%08x, D:0x%08X\n' % (address + i * 4, word)
                       for i, word in enumerate(words))
        if hex_encoded:
            return b'OKX ' + text.encode().hex().encode() + b'\n'
        return b'OK ' + text.replace('\n', '\\n').encode() + b'\n'

    def bracket_connections(self, *, fail_index=None, replies=None):
        defaults = [self.memory_reply(0xC31F8CB4, [1, 1], hex_encoded=True),
                    self.memory_reply(0xC32985E8, [20536]),
                    self.memory_reply(0xC32986B4, [48700]),
                    self.memory_reply(0xC31F8CB4, [1, 1], hex_encoded=True)]
        if replies:
            for index, reply in replies.items():
                defaults[index] = reply
        return [self.connection(reply=reply, fail='receive' if index == fail_index else None)
                for index, reply in enumerate(defaults)]

    def test_h_bracket_is_exactly_four_fixed_native_reads(self):
        connections = self.bracket_connections()
        result = self.transport().read_h_bracket()
        self.assertEqual(result, {'phase_before': 1, 'mode_before': 1, 'h': 20536, 'l': 48700,
                                  'phase_after': 1, 'mode_after': 1,
                                  'started_at': 10.0, 'finished_at': self.clock.now})
        self.assertEqual([item.sent for item in connections], [
            [b'TMO 1000 SHL mem get 0xC31F8CB4,,0x8\n'],
            [b'TMO 1000 SHL mem get 0xC32985E8,,0x4\n'],
            [b'TMO 1000 SHL mem get 0xC32986B4,,0x4\n'],
            [b'TMO 1000 SHL mem get 0xC31F8CB4,,0x8\n']])
        self.assertEqual(len(self.socket_calls), 4)
        self.assertEqual(self.clock.sleeps, [])

    def test_h_bracket_has_normal_gaps_before_after_but_none_inside(self):
        first = self.connection()
        burst = self.bracket_connections()
        final = self.connection()
        transport = self.transport(spacing_s=0.010)
        transport.request('before')
        result = transport.read_h_bracket()
        transport.request('after')
        self.assertAlmostEqual(burst[0].connected_at - first.closed_at, 0.010)
        for left, right in zip(burst, burst[1:]):
            self.assertEqual(right.connected_at, left.closed_at)
        self.assertAlmostEqual(final.connected_at - burst[-1].closed_at, 0.010)
        self.assertEqual(result['started_at'], burst[0].connected_at)
        self.assertEqual(result['finished_at'], burst[-1].closed_at)

    def test_consecutive_h_brackets_are_separately_paced(self):
        first = self.bracket_connections()
        second = self.bracket_connections()
        transport = self.transport()
        transport.read_h_bracket()
        transport.read_h_bracket()
        self.assertAlmostEqual(second[0].connected_at - first[-1].closed_at, 0.005)
        self.assertEqual(len(self.socket_calls), 8)

    def test_each_burst_exchange_failure_stops_without_retry(self):
        for failed_index in range(4):
            with self.subTest(failed_index=failed_index):
                burst = self.bracket_connections(fail_index=failed_index)
                transport = self.transport()
                before_calls = len(self.socket_calls)
                with self.assertRaises(TimeoutError):
                    transport.read_h_bracket()
                self.assertEqual(len(self.socket_calls) - before_calls, failed_index + 1)
                self.assertTrue(all(not item.sent for item in burst[failed_index + 1:]))
                self.connections.clear()
                next_request = self.connection()
                transport.request('independent next request')
                self.assertAlmostEqual(next_request.connected_at - burst[failed_index].closed_at, 0.005)

    def test_invalid_burst_reply_aborts_without_later_reads(self):
        invalid = [b'ERR failed\n', b'OK \n', b'OKX nothex\n',
                   self.memory_reply(0xC32985EC, [20536]),
                   self.memory_reply(0xC32985E8, [20536, 1]),
                   b'OK get : A:0xc32985e8, D:0x100000000\\n\n',
                   b'OK get : A:0xc32985e8, D:0x00005038 extra\\n\n']
        for reply in invalid:
            with self.subTest(reply=reply):
                burst = self.bracket_connections(replies={1: reply})
                before_calls = len(self.socket_calls)
                with self.assertRaises(bridge.BridgeError):
                    self.transport().read_h_bracket()
                self.assertEqual(len(self.socket_calls) - before_calls, 2)
                self.assertFalse(burst[2].sent)
                self.connections.clear()

    def test_burst_rejects_duplicate_phase_addresses(self):
        reply = b'OK get : A:0xc31f8cb4, D:0x1\\nget : A:0xc31f8cb4, D:0x1\\n\n'
        self.bracket_connections(replies={0: reply})
        with self.assertRaises(bridge.BridgeError):
            self.transport().read_h_bracket()
        self.assertEqual(len(self.socket_calls), 1)

    def test_burst_reports_changed_phase_mode_without_claiming_validity(self):
        self.bracket_connections(replies={3: self.memory_reply(0xC31F8CB4, [2, 3])})
        result = self.transport().read_h_bracket()
        self.assertEqual((result['phase_before'], result['phase_after']), (1, 2))
        self.assertEqual((result['mode_before'], result['mode_after']), (1, 3))
        self.assertNotIn('valid', result)

    def test_burst_does_not_accept_arbitrary_addresses_or_unpaced_options(self):
        transport = self.transport()
        with self.assertRaises(TypeError):
            transport.read_h_bracket(0xC072F700)
        with self.assertRaises(TypeError):
            transport.read_h_bracket(address=0xC072F700)
        with self.assertRaises(TypeError):
            transport.request('echo', paced=False)
        self.assertEqual(self.socket_calls, [])


if __name__ == "__main__":
    unittest.main()
