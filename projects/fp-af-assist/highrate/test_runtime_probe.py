import unittest
from unittest.mock import Mock

from .runtime_probe import BUILD_ID, CONTEXT_BASE, POOL_POINTER, probe


class RuntimeProbeTests(unittest.TestCase):
    def io(self):
        io = Mock()
        io.request.return_value = b'OK name=fpshd camera=open seq=1\n'
        io.shell.side_effect = [f'w71c1 5.02.0.V91 {BUILD_ID}', 'contexts', 'pool']
        io._memory_words.side_effect = [list(range(28)), [0x41000000]]
        return io

    def test_exact_reads_without_retry_or_write(self):
        io = self.io()
        result = probe(io)
        self.assertEqual([c.args[0] for c in io.shell.call_args_list],
                         ['version', 'mem get 0xC31E3888,,0x70',
                          'mem get 0xC3757A7C,,0x4'])
        self.assertEqual([c.args[1:] for c in io._memory_words.call_args_list],
                         [(CONTEXT_BASE, 28), (POOL_POINTER, 1)])
        self.assertEqual(result['contexts'][3]['mode'], 12)
        self.assertEqual(result['pool_pointer_raw'], 0x41000000)
        self.assertFalse(result['pool_lease_verified'])
        self.assertEqual(result['camera_ram_writes'], 0)

    def test_wrong_build_stops_before_memory(self):
        io = self.io()
        io.shell.side_effect = ['w71c1 5.02.0.V91 wrong-build']
        with self.assertRaises(RuntimeError):
            probe(io)
        self.assertEqual(io.shell.call_count, 1)

    def test_no_open_camera_stops_before_version(self):
        io = self.io()
        io.request.return_value = b'OK camera=closed\n'
        with self.assertRaises(RuntimeError):
            probe(io)
        io.shell.assert_not_called()

    def test_first_read_fault_stops_without_retry(self):
        io = self.io()
        io.shell.side_effect = [f'w71c1 5.02.0.V91 {BUILD_ID}', TimeoutError('fault')]
        with self.assertRaises(TimeoutError):
            probe(io)
        self.assertEqual(io.shell.call_count, 2)

    def test_malformed_context_stops_before_pool(self):
        io = self.io()
        io._memory_words.side_effect = ValueError('bad response')
        with self.assertRaises(ValueError):
            probe(io)
        self.assertEqual(io.shell.call_count, 2)


if __name__ == '__main__':
    unittest.main()
