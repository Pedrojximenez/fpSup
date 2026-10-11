"""Host-executed C sender tests + ARM cross-build; no hardware/USB access."""
import ctypes as c
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from highrate import af_batch, build_sender, ep83_receiver
from test_ep83_receiver import valid_batch

U8P = c.POINTER(c.c_uint8)
U32 = c.c_uint32
I32 = c.c_int32
NONCE = 0x13579BDF


class Request(c.Structure):
    _fields_ = [('state', U8P), ('records', U8P), ('dma_cpu', U8P),
                ('records_bytes', U32), ('dma_capacity', U32), ('dma_bus', U32),
                ('nonce', U32), ('wait_ms', U32)]


class Result(c.Structure):
    _fields_ = [('phase', U32), ('nonce', U32), ('batch_bytes', U32),
                ('batch_crc', U32), ('error', I32), ('platform_rc', I32),
                ('dma_may_be_owned', U32), ('dma_reclaimable', U32)]


class Receipt(c.Structure):
    _fields_ = [('wait_rc', I32)] + [(name, U32) for name in (
        'active', 'owned_trb', 'current_trb', 'expected_bus', 'requested_bytes',
        'word0', 'word1', 'word2', 'word3')]


PREFLIGHT = c.CFUNCTYPE(I32, c.c_void_p, c.POINTER(Request))
PUBLISH = c.CFUNCTYPE(I32, c.c_void_p, U8P, U32)
START = c.CFUNCTYPE(I32, c.c_void_p, U32, U32, U32)
WAIT = c.CFUNCTYPE(I32, c.c_void_p, U32, U32)
COMPLETION = c.CFUNCTYPE(I32, c.c_void_p, U32, U32)


class Ops(c.Structure):
    _fields_ = [('ctx', c.c_void_p), ('preflight', PREFLIGHT), ('publish', PUBLISH),
                ('start', START), ('wait', WAIT), ('completion', COMPLETION)]


class Fixture:
    def __init__(self, capacity=1, failures=None):
        self.expected = valid_batch(capacity=capacity)
        self.capture = self.expected[64:]
        self.state = (c.c_uint8 * 64).from_buffer_copy(self.capture[:64])
        self.records = (c.c_uint8 * (capacity * 128)).from_buffer_copy(self.capture[64:])
        self.storage = (c.c_uint8 * (len(self.expected) + 128))()
        c.memset(c.addressof(self.storage), 0xa5, len(self.storage))
        self.dma_address = (c.addressof(self.storage) + 63) & ~63
        self.request = Request(self.state, self.records, c.cast(self.dma_address, U8P),
                               capacity * 128, len(self.expected), 0x48040000, NONCE, 2000)
        self.result = Result()
        self.calls = []
        self.failures = failures or {}
        self.start_image = None
        self.callback_error = None
        self.on_preflight = None

        def preflight(ctx, q):
            self.calls.append(('preflight',))
            if self.on_preflight:
                self.on_preflight()
            return self.failures.get('preflight', 1)

        def publish(ctx, pointer, size):
            self.calls.append(('publish', c.cast(pointer, c.c_void_p).value, size))
            return self.failures.get('publish', 1)

        def start(ctx, ep, bus, size):
            self.calls.append(('start', ep, bus, size))
            self.start_image = self.frame()
            if (self.result.phase, self.result.dma_may_be_owned,
                    self.result.dma_reclaimable) != (3, 1, 0):
                self.callback_error = 'ownership not marked before Start'
            return self.failures.get('start', 0)

        def wait(ctx, ep, ms):
            self.calls.append(('wait', ep, ms))
            if self.frame() != self.start_image:
                self.callback_error = 'frame changed in flight'
            return self.failures.get('wait', 0)

        def completion(ctx, nonce, size):
            self.calls.append(('completion', nonce, size))
            return self.failures.get('completion', 1)

        self.callbacks = (PREFLIGHT(preflight), PUBLISH(publish), START(start),
                          WAIT(wait), COMPLETION(completion))
        self.ops = Ops(None, *self.callbacks)

    def frame(self):
        return c.string_at(self.dma_address, len(self.expected))


class SenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='fp-af-sender-test-')
        cls.addClassCleanup(cls.temp.cleanup)
        lib = Path(cls.temp.name) / 'sender.dylib'
        flags = ['-dynamiclib'] if sys.platform == 'darwin' else ['-shared', '-fPIC']
        subprocess.run(['clang', *flags, '-O2', '-std=c11', '-ffreestanding',
                        '-fno-builtin', '-Wall', '-Wextra', '-Werror',
                        str(build_sender.SOURCE), '-o', str(lib)],
                       check=True, capture_output=True)
        cls.lib = c.CDLL(str(lib))
        cls.lib.af_tx_send.argtypes = [c.POINTER(Request), c.POINTER(Result), c.POINTER(Ops)]
        cls.lib.af_tx_send.restype = I32
        cls.lib.af_crc32.argtypes = [U8P, U32]
        cls.lib.af_crc32.restype = U32
        cls.lib.af_ep83_completion_ok.argtypes = [c.POINTER(Receipt)]
        cls.lib.af_ep83_completion_ok.restype = I32

    def send(self, f):
        return self.lib.af_tx_send(c.byref(f.request), c.byref(f.result), c.byref(f.ops))

    def test_c_encoder_matches_python_all_capacity_edges(self):
        for count in (1, 7, 31, 256):
            with self.subTest(count=count):
                f = Fixture(count)
                before_state, before_records = bytes(f.state), bytes(f.records)
                self.assertEqual(self.send(f), 0)
                self.assertEqual(f.frame(), f.expected)
                self.assertEqual(f.result.batch_crc, zlib.crc32(f.expected))
                self.assertEqual(f.result.phase, 4)
                self.assertEqual(f.result.dma_reclaimable, 1)
                self.assertEqual(f.result.dma_may_be_owned, 0)
                self.assertEqual(bytes(f.state), before_state)
                self.assertEqual(bytes(f.records), before_records)
                self.assertIsNone(f.callback_error)
                self.assertEqual(f.calls, [('preflight',),
                    ('publish', f.dma_address, len(f.expected)),
                    ('start', 7, 0x48040000, len(f.expected)), ('wait', 3, 2000),
                    ('completion', NONCE, len(f.expected))])
                start = f.dma_address - c.addressof(f.storage)
                self.assertEqual(bytes(f.storage[:start]), b'\xa5' * start)
                tail = bytes(f.storage[start + len(f.expected):])
                self.assertEqual(tail, b'\xa5' * len(tail))

    def test_c_bytes_roundtrip_through_packet_safe_ep83_receiver(self):
        for count in (1, 7, 31, 256):
            f = Fixture(count)
            self.assertEqual(self.send(f), 0)
            blob = f.frame()
            cursor = 0
            def read(ep, size, timeout):
                nonlocal cursor
                self.assertEqual(ep, 0x83)
                self.assertEqual(size % 1024, 0)
                result = blob[cursor:cursor+size]
                cursor += len(result)
                return result
            result = ep83_receiver.receive_batch(read, expected_nonce=NONCE, total_timeout_s=1)
            self.assertEqual(result['count'], count)
            self.assertEqual(cursor, len(blob))
            self.assertFalse(result['usable_for_af_control'])

    def test_crc_known_vectors(self):
        for data in (b'', b'123456789', bytes(range(256))):
            buf = (c.c_uint8 * len(data)).from_buffer_copy(data)
            self.assertEqual(self.lib.af_crc32(buf, len(data)), zlib.crc32(data))

    def test_source_backed_completion_rejects_synthetic_wake_and_residue(self):
        good = Receipt(0, 0, 0x48000000, 0x48000000, 0x48040000, 32896,
                       0x48040000, 0, 0, 0x812)
        self.assertEqual(self.lib.af_ep83_completion_ok(c.byref(good)), 1)
        for name, value in (
            ('wait_rc', -5), ('active', 1), ('active', 2), ('owned_trb', 0),
            ('owned_trb', 0x48000001), ('current_trb', 0x48000010),
            ('expected_bus', 0), ('expected_bus', 0x48040001),
            ('requested_bytes', 0), ('requested_bytes', 128), ('requested_bytes', 32897),
            ('word0', 0x48040040), ('word1', 1), ('word2', 1),
            ('word2', 0x10000000), ('word3', 0x813), ('word3', 0x810),
        ):
            receipt = Receipt.from_buffer_copy(bytes(good))
            setattr(receipt, name, value)
            with self.subTest(name=name, value=value):
                self.assertEqual(self.lib.af_ep83_completion_ok(c.byref(receipt)), 0)
        self.assertEqual(self.lib.af_ep83_completion_ok(None), 0)

    def test_platform_failures_stop_at_exact_stage_and_quarantine(self):
        for stage, rc, error, phase, owned, reclaim, calls in (
            ('preflight', 0, -3, 5, 0, 0, 1),
            ('publish', 0, -5, 5, 0, 1, 2),
            ('start', -1, -6, 6, 1, 0, 3),
            ('wait', -5, -7, 6, 1, 0, 4),
            ('wait', -4, -7, 6, 1, 0, 4),
            ('completion', 0, -8, 6, 1, 0, 5),
        ):
            with self.subTest(stage=stage, rc=rc):
                f = Fixture(failures={stage: rc})
                before = f.frame()
                self.assertEqual(self.send(f), error)
                self.assertEqual((f.result.phase, f.result.dma_may_be_owned,
                                  f.result.dma_reclaimable), (phase, owned, reclaim))
                self.assertEqual(f.result.platform_rc, rc)
                self.assertEqual(len(f.calls), calls)
                if stage == 'preflight':
                    self.assertEqual(f.frame(), before)
                saved_frame = f.frame()
                saved_result = bytes(f.result)
                self.assertEqual(self.send(f), -2)
                self.assertEqual(f.frame(), saved_frame)
                self.assertEqual(bytes(f.result), saved_result)
                self.assertEqual(len(f.calls), calls)

    def test_success_cannot_be_retriggered(self):
        f = Fixture()
        self.assertEqual(self.send(f), 0)
        self.assertEqual(self.send(f), -2)
        self.assertEqual(len(f.calls), 5)

    def test_every_header_identity_word_is_validated_before_dma_writes(self):
        for offset in range(0, 64, 4):
            f = Fixture()
            f.state[offset] ^= 1
            before = f.frame()
            with self.subTest(offset=offset):
                self.assertEqual(self.send(f), -4)
                self.assertEqual(f.calls, [('preflight',)])
                self.assertEqual(f.frame(), before)

    def test_a_re_entered_or_unfinished_producer_is_never_sent(self):
        # Schema 2: the sender refuses a capture whose producer was re-entered,
        # whose body is still marked, or that saw fewer returns than records.
        for offset, value in ((52, 0), (56, 1), (60, 1), (48, 1)):
            f = Fixture(2)
            struct.pack_into('<I', f.state, offset, value)
            with self.subTest(offset=offset, value=value):
                self.assertEqual(self.send(f), -4)
                self.assertEqual(f.calls, [('preflight',)])

    def test_commits_sequence_nonce_complement_checked_for_each_record(self):
        for index in (0, 255):
            for offset in (0, 4, 8, 124):
                f = Fixture(256)
                f.records[index * 128 + offset] ^= 1
                with self.subTest(index=index, offset=offset):
                    self.assertEqual(self.send(f), -4)
                    self.assertEqual(f.calls, [('preflight',)])

    def test_preflight_change_of_capture_is_not_silently_accepted(self):
        f = Fixture()
        def mutate():
            f.state[20] = 1
        f.on_preflight = mutate
        self.assertEqual(self.send(f), -4)
        self.assertEqual(f.calls, [('preflight',)])

    def test_reentrant_call_is_refused_before_another_platform_operation(self):
        f = Fixture()
        nested = []
        f.on_preflight = lambda: nested.append(self.send(f))
        self.assertEqual(self.send(f), 0)
        self.assertEqual(nested, [-2])
        self.assertEqual(len(f.calls), 5)

    def test_bad_argument_sizes_mapping_and_timeout_do_no_io(self):
        for name, value in (
            ('nonce', 0), ('records_bytes', 0), ('records_bytes', 127),
            ('records_bytes', 32769), ('dma_capacity', 255), ('dma_capacity', 32897),
            ('dma_bus', 0), ('dma_bus', 0x48040001), ('dma_bus', 0xffffffc0),
            ('wait_ms', 0), ('wait_ms', 2001),
        ):
            f = Fixture()
            setattr(f.request, name, value)
            with self.subTest(name=name, value=value):
                self.assertEqual(self.send(f), -1)
                self.assertEqual(f.calls, [])
                self.assertEqual(f.result.phase, 0)

    def test_alias_and_missing_callbacks_do_no_io(self):
        f = Fixture()
        f.request.state = f.request.dma_cpu
        self.assertEqual(self.send(f), -1)
        self.assertEqual(f.calls, [])
        f = Fixture()
        f.request.records = f.request.state
        self.assertEqual(self.send(f), -1)
        self.assertEqual(f.calls, [])
        f = Fixture()
        f.ops.start = START()
        self.assertEqual(self.send(f), -1)
        self.assertEqual(f.calls, [])

    def test_arm_core_has_no_external_runtime_or_allocated_data_dependency(self):
        code, assembly, manifest = build_sender.assemble()
        self.assertGreater(len(code), 0)
        self.assertEqual(len(code) % 4, 0)
        self.assertEqual(manifest['required_stack_alignment'], 8)
        self.assertFalse(manifest['deployment_ready'])
        self.assertFalse(manifest['firmware_adapter_complete'])
        self.assertIn('af_tx_send:', assembly)
        self.assertNotIn('memcpy', assembly)


if __name__ == '__main__':
    unittest.main()
