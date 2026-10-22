"""Offline EP83 finite-batch receiver tests; no USB or camera access."""
import array
import struct
import unittest
import zlib

from highrate import af_batch
from highrate import ep83_receiver as ep83


NONCE = 0x13579BDF


def valid_batch(nonce=NONCE, capacity=1):
    capture = bytearray(af_batch.initial_capture(capacity, nonce))
    struct.pack_into('<III', capture, 20, 0, capacity, 1)  # disabled, count, full
    struct.pack_into('<I', capture, 52, capacity)          # hits, schema 2
    for index in range(capacity):
        sequence = index + 1
        record = [
            sequence, nonce, sequence, af_batch.MODEL, 200, 100, 1234,
            1, 1, 0, 0, 14, 1, 0x100, 1, 0, 1, 1, 1, 1,
            0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1234,
            sequence ^ 0xFFFFFFFF,
        ]
        struct.pack_into('<32I', capture,
                         af_batch.HEADER_BYTES + index * af_batch.RECORD_BYTES,
                         *record)
    return af_batch.pack_batch(capture, expected_nonce=nonce)


def repair_header_crc(header):
    header = bytearray(header)
    struct.pack_into('<I', header, 36, 0)
    struct.pack_into('<I', header, 36, zlib.crc32(header))
    return bytes(header)


def expected_reads(batch, packet=1024):
    """Return (request size, returned bytes) for the strict packet algorithm."""
    result = []
    offset = 0
    request = packet
    while offset < len(batch):
        moved = min(request, len(batch) - offset)
        result.append((request, batch[offset:offset + moved]))
        offset += moved
        if offset == len(batch):
            break
        remaining = len(batch) - offset
        request = packet if remaining < packet else (remaining // packet) * packet
    return result


class FakeClock:
    def __init__(self, now=10.0):
        self.now = now

    def monotonic(self):
        return self.now


class ScriptedRead:
    def __init__(self, clock, *events):
        self.clock = clock
        self.events = list(events)
        self.calls = []

    def __call__(self, endpoint, length, timeout_ms):
        self.calls.append((endpoint, length, timeout_ms))
        if not self.events:
            raise AssertionError('unexpected extra EP83 read')
        delay, value = self.events.pop(0)
        self.clock.now += delay
        if isinstance(value, BaseException):
            raise value
        return value


class EP83ReceiverTests(unittest.TestCase):
    def test_timeout_overflow_is_rejected_before_io(self):
        for value in (1e308, 10**1000, float('nan'), float('inf')):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    ep83.EP83Receiver(lambda *args: self.fail('unexpected I/O'),
                                     expected_nonce=NONCE, total_timeout_s=value)

    def test_backwards_clock_faults_without_second_read(self):
        clock = FakeClock()
        read = ScriptedRead(clock, (-1, valid_batch()))
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'backwards'):
            receiver.receive()
        self.assertTrue(receiver.faulted)
        self.assertEqual(len(read.calls), 1)

    def test_unrepresentable_deadline_faults_before_io(self):
        clock = FakeClock(now=1e308)
        read = ScriptedRead(clock)
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'cannot be represented'):
            receiver.receive()
        self.assertTrue(receiver.faulted)
        self.assertFalse(read.calls)

    def receiver(self, reader, clock, **kwargs):
        return ep83.EP83Receiver(
            reader,
            expected_nonce=kwargs.get('nonce', NONCE),
            total_timeout_s=kwargs.get('timeout', 1.0),
            max_packet_size=kwargs.get('packet', 1024),
            monotonic=clock.monotonic,
        )

    def scripted_batch(self, capacity, *, packet=1024, delays=None):
        batch = valid_batch(capacity=capacity)
        plan = expected_reads(batch, packet)
        delays = delays or [0] * len(plan)
        self.assertEqual(len(delays), len(plan))
        clock = FakeClock()
        read = ScriptedRead(clock, *((delay, payload)
                                     for delay, (_, payload) in zip(delays, plan)))
        return batch, plan, clock, read

    def test_capacity_edges_use_packet_safe_request_sizes(self):
        cases = {
            1: [1024],                 # total 256: terminal short in first read
            7: [1024],                 # total 1024: exact packet, no ZLP read
            31: [1024, 3072],          # total 4096: no oversized first buffer
            256: [1024, 31744, 1024],  # total 32896: final 128-byte short
        }
        for capacity, requests in cases.items():
            with self.subTest(capacity=capacity):
                batch, plan, clock, read = self.scripted_batch(capacity)
                receiver = self.receiver(read, clock)
                result = receiver.receive()
                self.assertEqual(result['count'], capacity)
                self.assertEqual([call[0] for call in read.calls], [0x83] * len(plan))
                self.assertEqual([call[1] for call in read.calls], requests)
                self.assertEqual(sum(len(payload) for _, payload in plan), len(batch))
                self.assertTrue(receiver.closed)
                self.assertFalse(receiver.faulted)

    def test_exact_packet_multiple_finishes_without_waiting_for_zlp(self):
        for capacity in (7, 31):
            with self.subTest(capacity=capacity):
                _, plan, clock, read = self.scripted_batch(capacity)
                self.receiver(read, clock).receive()
                self.assertEqual(len(read.calls), len(plan))
                self.assertFalse(read.events)

    def test_injected_legal_packet_sizes_drive_every_request(self):
        cases = ((64, [64, 960]), (512, [512, 512]), (1024, [1024]))
        for packet, requests in cases:
            with self.subTest(packet=packet):
                _, _, clock, read = self.scripted_batch(7, packet=packet)
                result = self.receiver(read, clock, packet=packet).receive()
                self.assertEqual(result['count'], 7)
                self.assertEqual([call[1] for call in read.calls], requests)

    def test_zero_or_non_bytes_first_read_faults_without_retry(self):
        for payload in (b'', None, 'not bytes', 17):
            with self.subTest(payload=payload):
                clock = FakeClock()
                read = ScriptedRead(clock, (0, payload))
                receiver = self.receiver(read, clock)
                with self.assertRaises(ep83.EP83ReceiveError):
                    receiver.receive()
                self.assertEqual(len(read.calls), 1)
                self.assertTrue(receiver.faulted)

    def test_transport_error_preserves_cause_and_never_retries(self):
        clock = FakeClock()
        read = ScriptedRead(clock, (0, TimeoutError('usb timeout')))
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'EP83 read failed') as caught:
            receiver.receive()
        self.assertIsInstance(caught.exception.__cause__, TimeoutError)
        self.assertEqual(len(read.calls), 1)

    def test_nonterminal_short_first_packet_faults_without_completion_read(self):
        batch = valid_batch(capacity=31)
        clock = FakeClock()
        read = ScriptedRead(clock, (0, batch[:512]))
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError,
                                    'nonterminal short EP83 read 512/1024'):
            receiver.receive()
        self.assertEqual(len(read.calls), 1)

    def test_nonterminal_short_later_packet_faults_without_patch_read(self):
        batch = valid_batch(capacity=31)
        clock = FakeClock()
        read = ScriptedRead(clock, (0, batch[:1024]), (0, batch[1024:2048]))
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError,
                                    'nonterminal short EP83 read 1024/3072'):
            receiver.receive()
        self.assertEqual(len(read.calls), 2)

    def test_overlong_result_faults_before_decoder_or_more_reads(self):
        batch = valid_batch(capacity=7)
        clock = FakeClock()
        read = ScriptedRead(clock, (0, memoryview(batch + b'x')))
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'over requested'):
            receiver.receive()
        self.assertEqual(len(read.calls), 1)
        self.assertEqual(receiver._decoder.buffer, b'')

    def test_released_memoryview_faults_without_retry(self):
        released = memoryview(valid_batch())
        released.release()
        clock = FakeClock()
        read = ScriptedRead(clock, (0, released))
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'non-bytes result'):
            receiver.receive()
        self.assertEqual(len(read.calls), 1)
        self.assertTrue(receiver.faulted)

    def test_bad_header_identity_stops_after_first_packet(self):
        batch = bytearray(valid_batch(capacity=31))
        batch[0] ^= 0x20
        clock = FakeClock()
        read = ScriptedRead(clock, (0, batch[:1024]))
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'invalid AFB1 batch'):
            receiver.receive()
        self.assertEqual(len(read.calls), 1)

    def test_each_header_contract_error_stops_after_first_packet(self):
        batch = valid_batch(capacity=31)
        cases = (
            (4, 2, 'version'), (8, 60, 'header bytes'),
            (12, NONCE + 1, 'nonce'), (16, 0, 'count'),
            (20, af_batch.RECORD_BYTES + 4, 'record bytes'),
            (24, af_batch.HEADER_BYTES, 'capture bytes'),
            (32, 0, 'terminal'), (40, 1, 'reserved'),
        )
        for offset, value, name in cases:
            with self.subTest(name=name):
                changed = bytearray(batch)
                struct.pack_into('<I', changed, offset, value)
                changed[:64] = repair_header_crc(changed[:64])
                clock = FakeClock()
                read = ScriptedRead(clock, (0, changed[:1024]))
                receiver = self.receiver(read, clock)
                with self.assertRaisesRegex(ep83.EP83ReceiveError,
                                            'invalid AFB1 batch'):
                    receiver.receive()
                self.assertEqual(len(read.calls), 1)

    def test_corrupt_body_faults_at_declared_end_without_retry(self):
        batch = bytearray(valid_batch(capacity=31))
        batch[-8] ^= 1
        plan = expected_reads(batch)
        clock = FakeClock()
        read = ScriptedRead(clock, *((0, payload) for _, payload in plan))
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'invalid AFB1 batch'):
            receiver.receive()
        self.assertEqual(len(read.calls), len(plan))

    def test_later_transport_error_faults_without_retry(self):
        batch = valid_batch(capacity=31)
        clock = FakeClock()
        read = ScriptedRead(clock, (0, batch[:1024]),
                            (0, OSError('device disconnected')))
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'EP83 read failed') as caught:
            receiver.receive()
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertEqual(len(read.calls), 2)

    def test_one_absolute_deadline_supplies_only_remaining_time(self):
        _, _, clock, read = self.scripted_batch(31, delays=[0.25, 0.50])
        result = self.receiver(read, clock).receive()
        self.assertEqual(result['count'], 31)
        self.assertEqual([call[2] for call in read.calls], [1000, 750])

    def test_deadline_near_expiry_prevents_next_usb_read(self):
        batch = valid_batch(capacity=31)
        clock = FakeClock()
        read = ScriptedRead(clock, (0.9995, batch[:1024]))
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'less than 1 ms'):
            receiver.receive()
        self.assertEqual(len(read.calls), 1)

    def test_complete_read_returned_at_or_after_deadline_is_rejected(self):
        batch = valid_batch()
        for delay in (1.0, 1.001):
            with self.subTest(delay=delay):
                clock = FakeClock()
                read = ScriptedRead(clock, (delay, batch))
                receiver = self.receiver(read, clock)
                with self.assertRaisesRegex(ep83.EP83ReceiveError,
                                            'exceeded total deadline'):
                    receiver.receive()
                self.assertEqual(len(read.calls), 1)

    def test_later_complete_read_returned_after_deadline_is_rejected(self):
        batch = valid_batch(capacity=31)
        clock = FakeClock()
        read = ScriptedRead(clock, (0.20, batch[:1024]), (0.81, batch[1024:]))
        receiver = self.receiver(read, clock)
        with self.assertRaisesRegex(ep83.EP83ReceiveError,
                                    'exceeded total deadline'):
            receiver.receive()
        self.assertEqual(len(read.calls), 2)

    def test_sub_millisecond_initial_budget_performs_no_usb_read(self):
        clock = FakeClock()
        read = ScriptedRead(clock)
        receiver = self.receiver(read, clock, timeout=0.0005)
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'less than 1 ms'):
            receiver.receive()
        self.assertEqual(read.calls, [])

    def test_bytes_like_result_is_copied_before_validation(self):
        batch = valid_batch()
        returned = array.array('B', batch)
        clock = FakeClock()
        read = ScriptedRead(clock, (0, returned))
        result = self.receiver(read, clock).receive()
        returned[0] = 0
        self.assertEqual(result['nonce'], NONCE)

    def test_receiver_is_single_use_after_success_or_failure(self):
        batch = valid_batch()
        clock = FakeClock()
        read = ScriptedRead(clock, (0, batch))
        receiver = self.receiver(read, clock)
        receiver.receive()
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'single-use'):
            receiver.receive()
        self.assertEqual(len(read.calls), 1)

        clock = FakeClock()
        read = ScriptedRead(clock, (0, b''))
        receiver = self.receiver(read, clock)
        with self.assertRaises(ep83.EP83ReceiveError):
            receiver.receive()
        with self.assertRaisesRegex(ep83.EP83ReceiveError, 'single-use'):
            receiver.receive()
        self.assertEqual(len(read.calls), 1)

    def test_invalid_configuration_performs_no_read(self):
        clock = FakeClock()
        read = ScriptedRead(clock)
        for timeout in (0, -1, True, float('inf'), float('nan'), '1'):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.receiver(read, clock, timeout=timeout)
        for packet in (0, 1, 128, 1023, True, '1024'):
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                self.receiver(read, clock, packet=packet)
        with self.assertRaises(af_batch.CaptureError):
            self.receiver(read, clock, nonce=0)
        self.assertEqual(read.calls, [])

    def test_convenience_function_uses_the_same_packet_contract(self):
        batch = valid_batch(capacity=7)
        clock = FakeClock()
        read = ScriptedRead(clock, (0, batch))
        result = ep83.receive_batch(read, expected_nonce=NONCE,
                                    total_timeout_s=1, max_packet_size=1024,
                                    monotonic=clock.monotonic)
        self.assertEqual(result['count'], 7)
        self.assertEqual(read.calls, [(0x83, 1024, 1000)])


if __name__ == '__main__':
    unittest.main()
