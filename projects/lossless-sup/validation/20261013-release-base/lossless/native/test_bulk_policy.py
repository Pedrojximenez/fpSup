"""Compile the production policy; bounded arithmetic, mixed streams and mutations.

Media completion is simulated here. The exact native insertion path is covered
separately by test_bulk_native.py; neither suite proves camera timing.
"""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
MIB = 1 << 20


class Policy(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in (
        'enabled', 'fps_ceil', 'start_free', 'latency_us', 'arrival_reserve',
        'frame_limit', 'free_watermark', 'budget_exhausted', 'checks',
        'count_flushes', 'pressure_flushes', 'unknown_pool', 'submitted',
        'compressed', 'raw', 'failed_returns', 'window_frames',
        'window_compressed', 'window_bytes', 'sample_frames', 'sample_compressed',
        'sample_bytes', 'mean_bytes', 'predicted_frames')]


def build(out, mutation=None):
    source = HERE / 'bulk_policy.c'
    if mutation:
        old, new = mutation
        text = source.read_text()
        if text.count(old) != 1:
            raise AssertionError('mutation seam is not unique')
        source = out / 'mutant.c'
        source.write_text(text.replace(old, new))
    lib = out / 'policy.dylib'
    subprocess.run(['clang', '-shared', '-fPIC', '-O2', '-std=c11', '-Wall',
                    '-Wextra', '-Werror', '-I', str(HERE), str(source), '-o', str(lib)],
                   check=True, capture_output=True, text=True)
    lib = C.CDLL(str(lib))
    for name, nargs, result in [('reset', 0, None), ('begin', 3, None),
                                ('should_flush', 2, C.c_uint32), ('observe', 4, None)]:
        fn = getattr(lib, 'fpl_bulk_' + name)
        fn.argtypes = [C.POINTER(Policy)] + [C.c_uint32] * nargs
        fn.restype = result
    return lib


class BulkPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='fpl-bulk-')
        cls.lib = build(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def begin(self, num=60000, den=1001, free=96, lib=None):
        p = Policy()
        (lib or self.lib).fpl_bulk_begin(C.byref(p), num, den, free)
        return p

    def flush(self, p, pending, free=90):
        return self.lib.fpl_bulk_should_flush(C.byref(p), pending, free)

    def test_fps_and_two_batches_leave_explicit_headroom(self):
        for num, den in [(24000, 1001), (25, 1), (30000, 1001), (48, 1),
                         (60000, 1001), (120, 1), (240, 1)]:
            for free in (96, 80, 48):
                p = self.begin(num, den, free)
                self.assertFalse(p.budget_exhausted)
                self.assertLessEqual(2 * p.frame_limit + 4 + p.arrival_reserve + 2, free)
        self.assertEqual(self.begin(24000, 1001).frame_limit, 43)
        self.assertEqual(self.begin(60000, 1001).frame_limit, 42)
        self.assertLess(self.begin(240, 1).frame_limit, self.begin(24, 1).frame_limit)

    def test_count_includes_current_file_before_cookie_append(self):
        p = self.begin()
        self.assertEqual(self.flush(p, p.frame_limit - 2), 0)
        self.assertEqual(self.flush(p, p.frame_limit - 1), 1)
        self.assertEqual(self.flush(p, 128), 1)

    def test_pressure_can_send_a_single_file(self):
        p = self.begin()
        self.assertEqual(self.flush(p, 0, p.free_watermark + 1), 0)
        self.assertEqual(self.flush(p, 0, p.free_watermark), 1)
        self.assertEqual(p.pressure_flushes, 1)

    def test_unknown_pool_never_allows_waiting(self):
        p = self.begin()
        self.assertEqual(self.flush(p, 0, 0xffff), 1)
        self.assertEqual(p.unknown_pool, 1)

    def test_missing_or_exhausted_budget_sends_each_file(self):
        for num, den, free in [(0, 1, 96), (60, 0, 96), (241, 1, 96),
                                (60, 1, 0), (60, 1, 0xffff), (60, 1, 12),
                                (0xffffffff, 1, 96)]:
            p = self.begin(num, den, free)
            self.assertEqual((p.frame_limit, p.budget_exhausted), (1, 1))
            self.assertEqual(self.flush(p, 0), 1)
        self.assertEqual(self.begin(0xffffffff, 0xffffffff).fps_ceil, 1)

    def test_longer_native_return_tightens_cap_and_never_reopens_it(self):
        p = self.begin(60, 1)
        self.lib.fpl_bulk_observe(C.byref(p), MIB, 0, 1, 500000)
        self.assertEqual((p.arrival_reserve, p.frame_limit), (30, 30))
        self.lib.fpl_bulk_observe(C.byref(p), MIB, 0, 1, 1000)
        self.assertEqual((p.latency_us, p.frame_limit), (500000, 30))
        self.lib.fpl_bulk_observe(C.byref(p), MIB, 0, 1, 0xffffffff)
        self.assertEqual((p.frame_limit, p.budget_exhausted), (1, 1))

    def test_mixed_output_uses_actual_raw_and_compressed_sizes(self):
        p = self.begin()
        for _ in range(16):
            self.lib.fpl_bulk_observe(C.byref(p), 3 * MIB, 0, 0, 1000)
            self.lib.fpl_bulk_observe(C.byref(p), MIB, 0, 1, 1000)
        self.assertEqual((p.submitted, p.raw, p.compressed), (32, 16, 16))
        self.assertEqual((p.mean_bytes, p.predicted_frames), (2 * MIB, 32))
        self.assertEqual((p.sample_frames, p.sample_compressed), (32, 16))
        self.lib.fpl_bulk_observe(C.byref(p), MIB // 2, 0, 1, 1000)
        self.assertEqual((p.sample_frames, p.predicted_frames), (1, 128))
        self.assertEqual(p.frame_limit, 42, 'an estimate must not relax the count guard')

    def test_bad_writer_returns_do_not_become_compression_samples(self):
        p = self.begin()
        for low, high in [(0, 0), (MIB, 1), (0xffffffff, 0)]:
            self.lib.fpl_bulk_observe(C.byref(p), low, high, 1, 2000)
        self.assertEqual((p.failed_returns, p.submitted, p.sample_frames), (3, 0, 0))

    def test_sample_byte_sum_cannot_wrap(self):
        p = self.begin()
        for _ in range(32):
            self.lib.fpl_bulk_observe(C.byref(p), 256 * MIB, 0, 0, 1000)
        self.assertEqual(p.mean_bytes, 256 * MIB)
        self.assertEqual(p.predicted_frames, 1)

    def test_off_reset_and_null_follow_native_predicate(self):
        p = self.begin()
        self.lib.fpl_bulk_reset(C.byref(p))
        self.assertEqual(bytes(p), bytes(C.sizeof(p)))
        for pending in (0, 42, 127, 128):
            self.assertEqual(self.flush(p, pending, 0), pending == 128)
            self.assertEqual(self.lib.fpl_bulk_should_flush(None, pending, 0), pending == 128)

    def test_mixed_stream_never_waits_for_more_than_the_frame_budget(self):
        # Actual byte threshold and frame threshold race, as in the native
        # path. Returning slots/media here is an explicit simulation.
        for sizes in ([MIB // 2] * 500, [9 * MIB] * 500,
                      [MIB, 3 * MIB] * 250, [MIB // 2] * 100 + [9 * MIB] * 100):
            p = self.begin()
            count = data = peak = flushes = 0
            for size in sizes:
                count += 1
                data += size
                peak = max(peak, count)
                if data >= 64 * MIB or self.flush(p, count - 1, 96 - count - 4):
                    count = data = 0
                    flushes += 1
            self.assertLessEqual(peak, p.frame_limit)
            self.assertGreater(flushes, 0)

    def test_mutations_are_detected(self):
        mutants = [
            ('(p->start_free - used) / 2u', '(p->start_free - used)', 'two'),
            ('pending >= p->frame_limit - 1u', 'pending >= p->frame_limit', 'current'),
            ('free_slots <= p->free_watermark', 'free_slots == 0u', 'pressure'),
        ]
        for old, new, name in mutants:
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix='fpl-bulk-mut-') as tmp:
                lib = build(Path(tmp), (old, new))
                p = self.begin(lib=lib)
                with self.assertRaises(AssertionError):
                    if name == 'two':
                        self.assertLessEqual(2 * p.frame_limit + 4 + p.arrival_reserve + 2, 96)
                    elif name == 'current':
                        self.assertEqual(lib.fpl_bulk_should_flush(C.byref(p), p.frame_limit - 1, 90), 1)
                    else:
                        self.assertEqual(lib.fpl_bulk_should_flush(C.byref(p), 0, p.free_watermark), 1)


if __name__ == '__main__':
    unittest.main()
