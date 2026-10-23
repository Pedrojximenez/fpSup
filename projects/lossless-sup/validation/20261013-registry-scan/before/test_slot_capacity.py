"""Production capacity arithmetic against an independent integer reference."""
import ctypes as C
import pathlib
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent


class Plan(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in
                ('file_floor', 'batch_frames', 'arrival_slots', 'slots', 'descriptor_bytes')]


class CapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='fpl-capacity-')
        lib = pathlib.Path(cls.tmp.name) / 'policy.dylib'
        subprocess.run(['clang', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(HERE / 'slot_capacity.c'), '-o', str(lib)], check=True)
        cls.lib = C.CDLL(str(lib))
        cls.fn = cls.lib.fpl_slot_plan
        cls.fn.argtypes = [C.c_uint32] * 7 + [C.POINTER(Plan)]
        cls.fn.restype = C.c_uint32

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_two_full_batches_plus_fractional_fps_and_latency(self):
        for w, h in [(1008, 672), (1936, 1090), (3024, 2010), (3840, 2160), (6016, 4000)]:
            for fn, fd in [(24000, 1001), (60000, 1001), (100, 1), (240, 1)]:
                for bits in (10, 12, 14):
                    for on in (0, 1):
                        for us in (100000, 300000, 1000000):
                            p = Plan(); result = self.fn(w, h, bits, on, fn, fd, us, C.byref(p))
                            floor = 0x13400 + (w * h * (1 if on else bits) + 7) // 8
                            batch = ((64 << 20) + floor - 1) // floor
                            arrivals = (((fn + fd - 1) // fd) * us + 999999) // 1000000
                            want = max(96, ((2 * batch + arrivals + 6 + 3) // 4) * 4)
                            self.assertEqual((p.file_floor, p.batch_frames, p.arrival_slots, p.slots),
                                             (floor, batch, arrivals, want))
                            self.assertEqual(bool(result), want <= 1016)
                            self.assertEqual(p.descriptor_bytes, 0x1130 + want * 0x1128)

    def test_unknown_or_unbounded_input_is_refused(self):
        base = [1936, 1090, 12, 1, 60, 1, 100000]
        for index, bad in [(0, 0), (1, 0xffffffff), (2, 8), (3, 2), (4, 0),
                           (4, 0xffffffff), (5, 0), (6, 0), (6, 1000001)]:
            args = base[:]; args[index] = bad; p = Plan()
            self.assertEqual(self.fn(*args, C.byref(p)), 0)

    def test_small_frames_report_capacity_shortage_instead_of_lowering_batch(self):
        p = Plan()
        self.assertEqual(self.fn(320, 240, 12, 1, 60, 1, 100000, C.byref(p)), 0)
        self.assertGreater(p.slots, 1016)
        self.assertGreaterEqual(p.batch_frames * p.file_floor, 64 << 20)

    def test_raw_fallback_never_needs_more_positions_than_minimum_compressed_size(self):
        raw, compressed = Plan(), Plan()
        self.fn(1936, 1090, 12, 0, 60, 1, 100000, C.byref(raw))
        self.fn(1936, 1090, 12, 1, 60, 1, 100000, C.byref(compressed))
        self.assertEqual((raw.slots, compressed.slots), (96, 404))
        self.assertGreater(compressed.batch_frames, raw.batch_frames)

    def test_m12240_low_fps_and_completion_latency_bound(self):
        for fn, fd, us, want, accepted in [
                (30000, 1001, 100000, 832, True),
                (240000, 1001, 100000, 852, True),
                (240000, 1001, 487069, 948, True),
                (240000, 1001, 783333, 1016, True),
                (240000, 1001, 783334, 1020, False),
                (240000, 1001, 1000000, 1068, False)]:
            p = Plan()
            result = self.fn(1008, 672, 12, 1, fn, fd, us, C.byref(p))
            self.assertEqual((p.file_floor, p.batch_frames, p.slots), (163520, 411, want))
            self.assertEqual(bool(result), accepted)


if __name__ == '__main__': unittest.main()
