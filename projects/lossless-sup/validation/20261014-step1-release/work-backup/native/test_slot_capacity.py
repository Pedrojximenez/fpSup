"""Production capacity arithmetic against an independent integer reference."""
import ctypes as C
import pathlib
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent


class Plan(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in
                ('file_floor', 'batch_frames', 'arrival_slots', 'slots', 'descriptor_bytes',
                 'ram_frames', 'frame_limit')]


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

    @staticmethod
    def reference(w, h, bits, on, fn, fd, us):
        """Independent integer reference for slot_capacity.h."""
        fps = (fn + fd - 1) // fd
        raster = (w * h * bits + 7) // 8
        alloc = 0x15400 + (raster + 511) // 512 * 512
        floor = 0x13400 + (w * h * (2 if on else bits) + 7) // 8
        batch = ((64 << 20) + floor - 1) // floor
        arrivals = (fps * us + 999999) // 1000000
        ram = 742520320 // alloc
        want = min(2 * batch + arrivals, ram)
        slots = min(1016, max(96, (want + 6 + 3) // 4 * 4))
        held = arrivals + 6
        limit = (slots - held) // 2 if slots > held + 2 else 1
        return floor, batch, arrivals, slots, ram, min(limit, batch)

    def test_matches_reference_over_modes_rates_depths_and_latency(self):
        for w, h in [(1008, 672), (1936, 1090), (3024, 2010), (3840, 2160), (6016, 4000), (320, 240)]:
            for fn, fd in [(24000, 1001), (60000, 1001), (100, 1), (120000, 1001), (240000, 1001)]:
                for bits in (10, 12, 14):
                    for on in (0, 1):
                        for us in (100000, 300000, 1000000):
                            p = Plan()
                            self.assertEqual(self.fn(w, h, bits, on, fn, fd, us, C.byref(p)), 1)
                            got = (p.file_floor, p.batch_frames, p.arrival_slots, p.slots,
                                   p.ram_frames, p.frame_limit)
                            self.assertEqual(got, self.reference(w, h, bits, on, fn, fd, us))
                            self.assertEqual(p.descriptor_bytes, 0x1130 + p.slots * 0x1128)
                            # Two count-closed batches plus arrivals and margin fit.
                            if p.frame_limit > 1:
                                self.assertLessEqual(2 * p.frame_limit + p.arrival_slots + 6, p.slots)

    def test_unknown_or_unbounded_input_is_refused(self):
        base = [1936, 1090, 12, 1, 60, 1, 100000]
        for index, bad in [(0, 0), (1, 0xffffffff), (2, 8), (3, 2), (4, 0),
                           (4, 0xffffffff), (5, 0), (6, 0), (6, 1000001)]:
            args = base[:]; args[index] = bad; p = Plan()
            self.assertEqual(self.fn(*args, C.byref(p)), 0)

    def test_small_frames_clamp_and_close_batches_by_count(self):
        p = Plan()
        self.assertEqual(self.fn(320, 240, 12, 1, 60, 1, 100000, C.byref(p)), 1)
        self.assertEqual(p.slots, 1016)
        self.assertLess(p.frame_limit, p.batch_frames)

    def test_known_modes(self):
        # (w, h, fps num/den) -> slots, frame_limit at 12-bit ON, 100 ms
        for w, h, fn, fd, slots, limit in [
                (1936, 1090, 30000, 1001, 232, 111),   # RAM holds 228 frames; was 404
                (1936, 1090, 60000, 1001, 236, 111),
                (1008, 672, 30000, 1001, 552, 271),    # was 832
                (1008, 672, 120000, 1001, 560, 271),
                (1008, 672, 240000, 1001, 572, 271),   # was 852
                (3024, 2010, 30000, 1001, 96, 42)]:    # OG3K stays stock
            p = Plan(); self.fn(w, h, 12, 1, fn, fd, 100000, C.byref(p))
            self.assertEqual((p.slots, p.frame_limit), (slots, limit), (w, h, fn))

    def test_raw_takes_need_no_more_than_compressed(self):
        raw, compressed = Plan(), Plan()
        self.fn(1936, 1090, 12, 0, 60, 1, 100000, C.byref(raw))
        self.fn(1936, 1090, 12, 1, 60, 1, 100000, C.byref(compressed))
        self.assertEqual(raw.slots, 96)
        self.assertLessEqual(raw.slots, compressed.slots)


if __name__ == '__main__': unittest.main()
