"""Host mocks for the EP83 kernel-event wait; no firmware or USB access."""

import ctypes as c
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


U32 = c.c_uint32
I32 = c.c_int32
VP = c.c_void_p
COMPLETE = 0x00100000
NOT_READY = 0x00000100
MASK = COMPLETE | NOT_READY


class State(c.Structure):
    _fields_ = [('phase', U32), ('reference', U32), ('observed', U32),
                ('kernel_rc', I32), ('quarantine', U32)]


CLEAR = c.CFUNCTYPE(I32, VP, U32)
ENTER = c.CFUNCTYPE(U32, VP)
EXIT = c.CFUNCTYPE(None, VP, U32)
LOAD = c.CFUNCTYPE(U32, VP)
STORE = c.CFUNCTYPE(None, VP, U32)
ENABLE = c.CFUNCTYPE(None, VP)
WAIT = c.CFUNCTYPE(I32, VP, U32, U32, c.POINTER(U32), U32)
START = c.CFUNCTYPE(I32, VP)


class Ops(c.Structure):
    _fields_ = [('ctx', VP), ('clear_flags', CLEAR),
                ('critical_enter', ENTER), ('critical_exit', EXIT),
                ('interest_load', LOAD), ('interest_store', STORE),
                ('irq_reenable', ENABLE), ('wait_flags', WAIT)]


class Mock:
    def __init__(self, *, interest=0x40, start_rc=0, wait_rc=0,
                 observed=COMPLETE, clear_rc=0):
        self.interest = interest
        self.start_rc = start_rc
        self.wait_rc = wait_rc
        self.observed = observed
        self.clear_rc = clear_rc
        self.calls = []
        self.in_critical = False

        def clear(ctx, keep):
            self.calls.append(('clear', keep))
            return self.clear_rc
        def enter(ctx):
            self.assert_false(self.in_critical)
            self.in_critical = True
            self.calls.append(('enter',))
            return 0xC0
        def exit_(ctx, token):
            self.assert_true(self.in_critical)
            self.assert_equal(token, 0xC0)
            self.in_critical = False
            self.calls.append(('exit', token))
        def load(ctx):
            self.assert_true(self.in_critical)
            self.calls.append(('load', self.interest))
            return self.interest
        def store(ctx, value):
            self.assert_true(self.in_critical)
            self.interest = value
            self.calls.append(('store', value))
        def enable(ctx):
            self.assert_false(self.in_critical)
            self.calls.append(('enable',))
        def wait(ctx, mask, mode, out, timeout):
            self.assert_equal((mask, mode), (MASK, 0x21))
            self.assert_true(bool(self.interest & MASK))
            out[0] = self.observed
            self.calls.append(('wait', mask, mode, timeout))
            return self.wait_rc
        def start(ctx):
            self.assert_true(bool(self.interest & MASK))
            self.calls.append(('start',))
            return self.start_rc

        self.callbacks = (CLEAR(clear), ENTER(enter), EXIT(exit_), LOAD(load),
                          STORE(store), ENABLE(enable), WAIT(wait), START(start))
        self.ops = Ops(None, *self.callbacks[:-1])
        self.start = self.callbacks[-1]

    @staticmethod
    def assert_true(value):
        if not value:
            raise AssertionError('mock invariant false')
    @staticmethod
    def assert_false(value):
        if value:
            raise AssertionError('mock invariant true')
    @staticmethod
    def assert_equal(a, b):
        if a != b:
            raise AssertionError(f'{a!r} != {b!r}')


class Ep83WaitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='fp-af-ep83-wait-')
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(__file__).with_name('af_ep83_wait.c')
        lib = Path(cls.temp.name) / 'wait.dylib'
        flags = ['-dynamiclib'] if sys.platform == 'darwin' else ['-shared', '-fPIC']
        subprocess.run(['clang', *flags, '-O2', '-std=c11', '-ffreestanding',
                        '-fno-builtin', '-Wall', '-Wextra', '-Werror',
                        str(source), '-o', str(lib)], check=True, capture_output=True)
        cls.lib = c.CDLL(str(lib))
        cls.lib.af_ep83_wait_start.argtypes = [c.POINTER(State), c.POINTER(Ops),
                                               U32, START, VP]
        cls.lib.af_ep83_wait_start.restype = I32
        cls.lib.af_ep83_wait_once.argtypes = [c.POINTER(State), c.POINTER(Ops),
                                              U32, U32]
        cls.lib.af_ep83_wait_once.restype = I32

    def arm(self, mock, reference=0x1234):
        state = State()
        rc = self.lib.af_ep83_wait_start(c.byref(state), c.byref(mock.ops),
                                         reference, mock.start, None)
        return state, rc

    def test_success_claims_before_start_and_restores_interest_and_irq(self):
        mock = Mock(interest=0x40, observed=COMPLETE | 0x8)
        state, rc = self.arm(mock)
        self.assertEqual(rc, 0)
        self.assertEqual(state.phase, 1)
        self.assertEqual(mock.interest, 0x40 | MASK)
        self.assertEqual(self.lib.af_ep83_wait_once(
            c.byref(state), c.byref(mock.ops), 0x1234, 2000), 0)
        self.assertEqual((state.phase, state.quarantine), (2, 0))
        self.assertEqual(state.observed, COMPLETE | 0x8)
        self.assertEqual(mock.interest, 0x40)
        self.assertEqual(mock.calls.count(('enable',)), 2)
        self.assertLess(mock.calls.index(('store', 0x40 | MASK)),
                        mock.calls.index(('start',)))
        self.assertFalse(mock.in_critical)

    def test_overlap_is_rejected_before_clear_or_start(self):
        mock = Mock(interest=COMPLETE)
        state, rc = self.arm(mock)
        self.assertEqual(rc, -102)
        self.assertEqual((state.phase, state.quarantine), (3, 1))
        self.assertNotIn(('start',), mock.calls)
        self.assertFalse(any(call[0] == 'clear' for call in mock.calls))
        self.assertEqual(mock.interest, COMPLETE)

    def test_start_failure_releases_bookkeeping_but_quarantines(self):
        mock = Mock(start_rc=-7)
        state, rc = self.arm(mock)
        self.assertEqual(rc, -7)
        self.assertEqual((state.phase, state.quarantine), (3, 1))
        self.assertEqual(mock.interest, 0x40)
        self.assertEqual(mock.calls.count(('enable',)), 2)

    def test_clear_failure_restores_interest_and_irq_without_start(self):
        mock = Mock(clear_rc=-9)
        state, rc = self.arm(mock)
        self.assertEqual(rc, -9)
        self.assertEqual((state.phase, state.quarantine), (3, 1))
        self.assertEqual(mock.interest, 0x40)
        self.assertEqual(mock.calls.count(('enable',)), 1)
        self.assertNotIn(('start',), mock.calls)

    def test_timeout_does_not_clear_again_or_reuse(self):
        mock = Mock(wait_rc=-50, observed=0)
        state, rc = self.arm(mock)
        self.assertEqual(rc, 0)
        self.assertEqual(self.lib.af_ep83_wait_once(
            c.byref(state), c.byref(mock.ops), 0x1234, 25), -50)
        self.assertEqual((state.phase, state.quarantine), (3, 1))
        self.assertEqual(sum(call[0] == 'clear' for call in mock.calls), 1)
        self.assertEqual(self.lib.af_ep83_wait_once(
            c.byref(state), c.byref(mock.ops), 0x1234, 25), -104)

    def test_timeout_bounds_release_without_entering_kernel_wait(self):
        for timeout in (0, 2001):
            with self.subTest(timeout=timeout):
                mock = Mock()
                state, rc = self.arm(mock)
                self.assertEqual(rc, 0)
                self.assertEqual(self.lib.af_ep83_wait_once(
                    c.byref(state), c.byref(mock.ops), 0x1234, timeout), -101)
                self.assertEqual((state.phase, state.quarantine), (3, 1))
                self.assertFalse(any(call[0] == 'wait' for call in mock.calls))
                self.assertEqual(mock.interest, 0x40)

    def test_not_ready_or_mixed_local_event_is_never_success(self):
        for observed in (NOT_READY, COMPLETE | NOT_READY, 0):
            with self.subTest(observed=hex(observed)):
                mock = Mock(observed=observed)
                state, rc = self.arm(mock)
                self.assertEqual(rc, 0)
                self.assertEqual(self.lib.af_ep83_wait_once(
                    c.byref(state), c.byref(mock.ops), 0x1234, 100), -103)
                self.assertEqual((state.phase, state.quarantine), (3, 1))

    def test_reference_mismatch_releases_interest_without_waiting(self):
        mock = Mock()
        state, rc = self.arm(mock)
        self.assertEqual(rc, 0)
        self.assertEqual(self.lib.af_ep83_wait_once(
            c.byref(state), c.byref(mock.ops), 0x9999, 100), -104)
        self.assertEqual((state.phase, state.quarantine), (3, 1))
        self.assertFalse(any(call[0] == 'wait' for call in mock.calls))
        self.assertEqual(mock.interest, 0x40)


if __name__ == '__main__':
    unittest.main()
