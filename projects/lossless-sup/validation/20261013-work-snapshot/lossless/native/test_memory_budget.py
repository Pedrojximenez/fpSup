"""Real admission arithmetic, bounded RAW counter snapshot and pressure streams.

Media completions in the stream test are explicitly simulated; no wall-clock
or camera stability claims follow from these host tests.
"""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
MIB, UNKNOWN = 1 << 20, 0xffffffff
NAMES = ('enabled', 'frame_charge', 'raw_file_bytes', 'raw_batch_frames', 'fps_ceil',
         'latency_us', 'reserve_frames', 'reserve_bytes', 'checks', 'admitted',
         'pressure_raw', 'unknown_raw', 'last_free', 'min_free')


class Budget(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in NAMES]


def build(out, mutation=None):
    sources = [HERE / 'memory_budget.c', HERE / 'raw_headroom.c']
    if mutation:
        filename, old, new = mutation
        source = HERE / filename
        data = source.read_text()
        assert data.count(old) == 1, old
        changed = out / filename
        changed.write_text(data.replace(old, new))
        sources[sources.index(source)] = changed
    fixture = out / 'fixture.c'
    fixture.write_text('''#include <stdint.h>
static uint32_t mode, ptr, cls, total, used, depth, bad, reads;
void setup(uint32_t m, uint32_t p, uint32_t c, uint32_t t, uint32_t u) {
 mode=m; ptr=p; cls=c; total=t; used=u; depth=bad=reads=0;
}
uint32_t fpl_headroom_irq_off(void) { if(depth++) bad++; return 0x80; }
void fpl_headroom_irq_restore(uint32_t m) { if(depth!=1 || m!=0x80) bad++; depth--; }
uint32_t fpl_headroom_mode(void) { if(depth!=1) bad++; return mode; }
uint32_t fpl_headroom_read(uint32_t a) {
 reads++; if(depth!=1) bad++;
 if(a==0xc3073a04u) return ptr;
 if(a==ptr) return cls;
 if(a==ptr+8) return total;
 if(a==ptr+0x18) return used;
 bad++; return 0;
}
uint32_t probe(uint32_t n) { return n==0 ? bad : n==1 ? depth : reads; }
''')
    lib = out / 'budget.dylib'
    subprocess.run(['clang', '-shared', '-fPIC', '-O2', '-std=c11', '-Wall',
                    '-Wextra', '-Werror', '-DFPL_RAW_HEADROOM_HOST_TEST', '-I', str(HERE),
                    *map(str, sources), str(fixture), '-o', str(lib)],
                   check=True, capture_output=True, text=True)
    lib = C.CDLL(str(lib))
    lib.fpl_memory_begin.argtypes = [C.POINTER(Budget)] + [C.c_uint32] * 4
    lib.fpl_memory_allow.argtypes = [C.POINTER(Budget)] + [C.c_uint32] * 2
    lib.fpl_memory_allow.restype = lib.fpl_raw_headroom.restype = C.c_uint32
    lib.setup.argtypes = [C.c_uint32] * 5
    return lib


class MemoryBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='fpl-memory-')
        cls.lib = build(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def begin(self, raster=1008 * 672 * 12 // 8, fn=120000, fd=1001, us=500000, lib=None):
        p = Budget()
        (lib or self.lib).fpl_memory_begin(C.byref(p), raster, fn, fd, us)
        return p

    def test_geometry_fps_latency_and_whole_allocations(self):
        for w, h in [(1008, 672), (1936, 1090), (3024, 2010), (3840, 2160), (6016, 4000)]:
            for bits in (10, 12, 14):
                raster = (w * h * bits + 7) // 8
                packed = (raster + 511) // 512 * 512
                charge = (0x15400 + packed + 64 + 1023) // 1024 * 1024
                batch = (64 * MIB + 0x13400 + packed - 1) // (0x13400 + packed)
                for fn, fd in [(24000, 1001), (60000, 1001), (120000, 1001), (240000, 1001)]:
                    for us in (0, 100000, 469659, 1000000):
                        p = self.begin(raster, fn, fd, us)
                        arrivals = (((fn + fd - 1) // fd) * max(100000, us) + 999999) // 1000000
                        self.assertEqual((p.frame_charge, p.raw_batch_frames), (charge, batch))
                        self.assertEqual(p.reserve_frames, 2 * batch + arrivals + 6)
                        representable = p.reserve_frames * charge <= UNKNOWN
                        self.assertEqual(bool(p.enabled), representable)
                        if representable:
                            self.assertEqual(p.reserve_bytes, p.reserve_frames * charge)

    def test_boundary_and_unknown_force_raw_then_recover_when_free(self):
        p = self.begin()
        for free, expected in [(p.reserve_bytes + 1, 1), (p.reserve_bytes, 0),
                               (0, 0), (UNKNOWN, 0), (p.reserve_bytes + p.frame_charge, 1)]:
            self.assertEqual(self.lib.fpl_memory_allow(C.byref(p), free, 500000), expected)
        self.assertEqual((p.checks, p.admitted, p.pressure_raw, p.unknown_raw, p.min_free), (5, 2, 2, 1, 0))

    def test_longer_completion_increases_reserve_and_never_relaxes_during_take(self):
        p = self.begin(us=100000)
        before = p.reserve_bytes
        self.lib.fpl_memory_allow(C.byref(p), 700 * MIB, 500000)
        self.assertGreater(p.reserve_bytes, before)
        reserve = p.reserve_bytes
        self.lib.fpl_memory_allow(C.byref(p), 700 * MIB, 1)
        self.assertEqual(p.reserve_bytes, reserve)
        self.assertEqual(self.lib.fpl_memory_allow(C.byref(p), 700 * MIB, 1000001), 0)
        self.assertEqual(self.lib.fpl_memory_allow(C.byref(p), 700 * MIB, 1), 0)
        self.assertFalse(p.enabled)

    def test_invalid_and_overflowing_budgets_never_admit(self):
        for args in [(0, 60, 1, 100000), (UNKNOWN, 60, 1, 100000),
                     (1000, 0, 1, 100000), (1000, 60, 0, 100000),
                     (1000, 241, 1, 100000), (1000, UNKNOWN, 1, 100000),
                     (1000, 60, 1, UNKNOWN), (0x10000000, 240, 1, 1000000)]:
            p = self.begin(*args)
            self.assertEqual(self.lib.fpl_memory_allow(C.byref(p), 700 * MIB, 100000), 0)
        self.assertTrue(self.begin(fn=UNKNOWN, fd=UNKNOWN).enabled)

    def test_snapshot_is_primary_raw_only_bounded_and_irq_balanced(self):
        for mode, ptr, cls, total, used, expected in [
            (3, 0xc3100000, 10, 742520320, 75126144, 742520320-75126144-2048),
            (3, 0xc3100000, 10, 4096, 4096, 0),
            (3, 0xc3100000, 10, 4096, 4097, UNKNOWN),
            (3, 0xc3100000, 10, 0, 0, UNKNOWN),
            (3, 0xc3100000, 10, UNKNOWN, 0, UNKNOWN),
            (3, 0xc3100000, 11, 4096, 0, UNKNOWN),
            (3, 0, 10, 4096, 0, UNKNOWN),
            (3, 0xc3100001, 10, 4096, 0, UNKNOWN),
            (0, 0xc3100000, 10, 4096, 0, UNKNOWN)]:
            self.lib.setup(mode, ptr, cls, total, used)
            self.assertEqual(self.lib.fpl_raw_headroom(), expected)
            self.assertEqual((self.lib.probe(0), self.lib.probe(1)), (0, 0))
            self.assertLessEqual(self.lib.probe(2), 4)

    def test_extreme_compression_reaches_factory_byte_gate_before_ram_exhaustion(self):
        # Writer queues may begin with an in-flight full compressed batch.
        # Completion is delayed for the specified measured budget after
        # each 64-MiB threshold; the codec alternates tiny compressed/RAW.
        pressure_cases = 0
        for capacity in (256 * MIB, 708 * MIB):
            for fps in (30, 120, 240):
                for compressed in (1, 163520, 800000):
                    p = self.begin(fn=fps, fd=1)
                    allocated = batch_count = batch_bytes = flushed = 0
                    due = []
                    for tick in range(4000):
                        for when, frames in due[:]:
                            if when <= tick:
                                allocated -= frames * p.frame_charge
                                due.remove((when, frames))
                        allocated += p.frame_charge
                        self.assertLessEqual(allocated, capacity)
                        allow = self.lib.fpl_memory_allow(C.byref(p), capacity - allocated, 500000)
                        size = compressed if allow and tick % 97 else p.raw_file_bytes
                        batch_count += 1; batch_bytes += size
                        if batch_bytes >= 64 * MIB:
                            due.append((tick + (fps + 1) // 2, batch_count))
                            batch_count = batch_bytes = 0
                            flushed += 1
                    self.assertGreater(flushed, 0)
                    pressure_cases += bool(p.pressure_raw)
        self.assertGreaterEqual(pressure_cases, 12)

    def test_mutations_are_detected(self):
        mutations = [
            ('memory_budget.c', '2u * p->raw_batch_frames + arrivals + 6u',
             'p->raw_batch_frames + arrivals + 6u', 'two'),
            ('memory_budget.c', 'free_bytes <= p->reserve_bytes',
             'free_bytes < p->reserve_bytes', 'boundary'),
            ('memory_budget.c', 'free_bytes == UINT32_MAX', 'free_bytes == 0u', 'unknown'),
            ('raw_headroom.c', 'p + 0x18u', 'p + 0x1cu', 'counter'),
        ]
        for filename, old, new, name in mutations:
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix='fpl-memory-mut-') as tmp:
                lib = build(Path(tmp), (filename, old, new))
                p = self.begin(lib=lib)
                with self.assertRaises(AssertionError):
                    if name == 'two': self.assertEqual(p.reserve_frames, 2 * 62 + 60 + 6)
                    elif name == 'boundary': self.assertEqual(lib.fpl_memory_allow(C.byref(p), p.reserve_bytes, 500000), 0)
                    elif name == 'unknown': self.assertEqual(lib.fpl_memory_allow(C.byref(p), UNKNOWN, 500000), 0)
                    else:
                        lib.setup(3, 0xc3100000, 10, 742520320, 75126144)
                        self.assertEqual(lib.fpl_raw_headroom(), 742520320-75126144-2048)


if __name__ == '__main__': unittest.main()
