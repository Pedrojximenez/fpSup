"""The refusal gate's real C: when it closes, probes, reopens, and what it never does.

Streams below are simulated lane totals; the camera numbers they mirror are in
validation/20261013-registry-scan (HS280 every frame refused, FHD 274/275).
"""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
NAMES = ('streak_limit', 'probe_every', 'seen_compressed', 'seen_failed', 'streak', 'closed',
         'since_probe', 'closes', 'reopens', 'probes', 'skipped')
STREAK, PROBE = 8, 120


class Gate(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in NAMES]


def build(out, mutation=None):
    source = HERE / 'refusal_gate.c'
    if mutation:
        old, new = mutation
        data = source.read_text()
        assert data.count(old) == 1, old
        source = out / 'refusal_gate.c'
        source.write_text(data.replace(old, new))
    lib = out / ('gate-%d.dylib' % len(list(out.iterdir())))
    # A mutant may leave a variable set but unused; only the real file must be clean.
    strict = [] if mutation else ['-Werror']
    subprocess.run(['clang', '-shared', '-fPIC', '-O2', '-std=c11', '-Wall', '-Wextra',
                    *strict, '-I', str(HERE), str(source), '-o', str(lib)],
                   check=True, capture_output=True, text=True)
    lib = C.CDLL(str(lib))
    lib.fpl_gate_begin.argtypes = [C.POINTER(Gate), C.c_uint32, C.c_uint32]
    lib.fpl_gate_allow.argtypes = [C.POINTER(Gate), C.c_uint32, C.c_uint32]
    lib.fpl_gate_allow.restype = C.c_uint32
    return lib


def run(lib, outcomes, start=(0, 0)):
    """outcomes: per admitted frame, 'c' compressed or 'f' failed; a frame's
    result is visible at the next arrival (one engine, lanes lag at least one).
    Returns the allow decisions and the gate."""
    g = Gate()
    lib.fpl_gate_begin(C.byref(g), *start)
    comp, fail = start
    pending, decisions = None, []
    for outcome in outcomes:
        if pending == 'c':
            comp += 1
        elif pending == 'f':
            fail += 1
        allowed = lib.fpl_gate_allow(C.byref(g), comp, fail)
        decisions.append(allowed)
        pending = outcome if allowed else None
    return decisions, g


class RefusalGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='fpl-gate-')
        cls.lib = build(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_refused_closes_after_the_streak_and_probes(self):
        n = 960                                  # 8 s at 119.88p
        d, g = run(self.lib, 'f' * n)
        # a result is seen one arrival late: STREAK frames go, the next does not
        self.assertEqual(d[:STREAK + 1], [1] * STREAK + [0])
        engine = sum(d)
        # streak frames (+1 in flight) then one probe per PROBE arrivals
        self.assertLessEqual(engine, STREAK + 1 + n // PROBE + 1)
        self.assertEqual(g.closes, 1)
        self.assertEqual(g.reopens, 0)
        self.assertEqual(g.closed, 1)
        self.assertEqual(g.skipped + engine, n)

    def test_all_compressed_never_closes(self):
        d, g = run(self.lib, 'c' * 960)
        self.assertEqual(d, [1] * 960)
        self.assertEqual((g.closes, g.skipped), (0, 0))

    def test_fhd_like_rare_refusals_never_close(self):
        # 274 of 275 compressed, the one refusal alone (camera, fhd60-5s)
        stream = 'c' * 137 + 'f' + 'c' * 137
        d, g = run(self.lib, stream)
        self.assertEqual(d, [1] * len(stream))
        self.assertEqual(g.closes, 0)

    def test_short_failure_runs_reset_on_success(self):
        stream = ('f' * (STREAK - 2) + 'c') * 50
        d, g = run(self.lib, stream)
        self.assertEqual(d, [1] * len(stream))
        self.assertEqual(g.closes, 0)

    def test_a_probe_that_compresses_reopens(self):
        # refused until the scene changes, then compressible
        stream = 'f' * 300 + 'c' * 600
        d, g = run(self.lib, stream)
        self.assertEqual(g.reopens, 1)
        self.assertEqual(g.closed, 0)
        reopened = max(i for i in range(len(d)) if not d[i]) + 1
        self.assertLessEqual(reopened, 300 + PROBE + 2)
        self.assertEqual(d[reopened:], [1] * (len(d) - reopened))

    def test_begin_takes_the_lanes_current_totals(self):
        d, g = run(self.lib, 'c' * 20, start=(5000, 7000))
        self.assertEqual(d, [1] * 20)
        self.assertEqual(g.closes, 0)

    def test_a_counter_going_back_is_not_a_huge_streak(self):
        g = Gate()
        self.lib.fpl_gate_begin(C.byref(g), 100, 100)
        self.assertEqual(self.lib.fpl_gate_allow(C.byref(g), 0, 3), 1)   # lane reset
        self.assertEqual(g.streak, 0)
        self.assertEqual(g.closed, 0)

    def test_a_compressed_counter_going_back_is_not_a_success(self):
        g = Gate()
        self.lib.fpl_gate_begin(C.byref(g), 100, 0)
        for n in range(1, STREAK + 1):                     # exactly STREAK failures
            self.lib.fpl_gate_allow(C.byref(g), 0, n)
        self.assertEqual(g.closed, 1)

    def test_zeroed_state_allows_everything(self):
        g = Gate()                                        # before any take
        for n in range(500):
            self.assertEqual(self.lib.fpl_gate_allow(C.byref(g), 0, n), 1)
        self.assertEqual(g.closed, 0)

    def test_null_gate_allows(self):
        self.assertEqual(self.lib.fpl_gate_allow(None, 0, 1000), 1)


class RefusalGateMutationTests(unittest.TestCase):
    """Each mutant must be caught by the tests above."""
    MUTANTS = [
        ('if (won) {', 'if (0) {'),                                   # never reopens
        ('g->streak >= g->streak_limit', 'g->streak > 1000000u'),     # never closes
        ('++g->since_probe >= g->probe_every', '0'),                  # never probes
        ('g->streak = 0;\n        if (g->closed)', 'if (g->closed)'),  # success does not reset
        ('compressed - g->seen_compressed : 0', 'compressed - g->seen_compressed : 1'),
    ]

    def test_mutants_are_caught(self):
        with tempfile.TemporaryDirectory(prefix='fpl-gate-mut-') as tmp:
            for mutation in self.MUTANTS:
                with self.subTest(mutation=mutation[0]):
                    lib = build(Path(tmp), mutation)
                    saved = getattr(RefusalGateTests, 'lib', None)
                    RefusalGateTests.lib = lib
                    result = unittest.TestResult()
                    try:
                        # TestCase.run, not a suite: no setUpClass rebuilding
                        # the good library behind the mutant's back.
                        for name in unittest.TestLoader().getTestCaseNames(RefusalGateTests):
                            RefusalGateTests(name).run(result)
                    finally:
                        RefusalGateTests.lib = saved
                    self.assertTrue(result.failures or result.errors,
                                    f'mutant survived: {mutation}')


if __name__ == '__main__':
    unittest.main()
