import contextlib
import unittest
from unittest import mock

import focus_bridge as b


class FakeTransport:
    def __init__(self):
        self.memory = {a: a ^ 0x1234 for a in range(b.P, b.END, 4)}
        self.memory[b.ECHO] = b.ORIGINAL
        self.memory[0xC3476408] = 1
        self.memory[0xC3476414] = 0xC0B8EEEC
        self.calls = []
        self.fail_echo = False
        self.changed_settings = False

    def read(self, address, count=1):
        return [self.memory.get(address + 4 * i, 0) for i in range(count)]

    def ensure(self, address, value):
        self.calls.append(('write', address, value))
        self.memory[address] = value

    def shell(self, command, timeout_ms=1000):
        self.calls.append(('shell', command, self.memory[b.ECHO]))
        if command == 'version':
            return 'w71c1 5.02.0.V91 13aa621060efff11aaba9b21ad925005302605cf'
        if command in b.SETTINGS:
            return command + (' changed' if self.changed_settings else ' baseline')
        if command == 'echo' and self.memory[b.ECHO] == b.CODE:
            if self.fail_echo:
                raise TimeoutError('uncertain')
            if self.memory[b.P] == b.MAGIC:
                self.memory[b.P] = 0
                self.memory[b.P + 0x18] = self.memory[b.P + 4]
                self.memory[b.P + 0x1c] = 2
                self.memory[b.P + 0x20] = 123
        return ''


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.io = FakeTransport()
        self.bridge = b.FocusBridge(self.io, b'\0' * 16)
        self.original = dict(self.io.memory)

    def test_exact_scratch_and_echo_restored(self):
        with self.bridge.lease():
            self.assertEqual(self.bridge.call(0)[0], 123)
        self.assertEqual(self.io.memory, self.original)

    def test_cache_publication_order(self):
        with self.bridge.lease():
            self.bridge.call(0)
        echoes = [row[2] for row in self.io.calls if row[:2] == ('shell', 'echo')]
        self.assertEqual(echoes, [b.DCACHE, b.ICACHE, b.CODE, b.DCACHE, b.ICACHE])

    def test_unknown_owner_never_written(self):
        self.io.memory[b.ECHO] = 0xdeadbeef
        with self.assertRaisesRegex(b.BridgeError, 'unknown echo'):
            with self.bridge.lease():
                pass
        self.assertFalse(any(row[0] == 'write' for row in self.io.calls))

    def test_uncertain_call_not_retried_and_scratch_quarantined(self):
        self.io.fail_echo = True
        with self.assertRaisesRegex(b.BridgeError, 'scratch retained'):
            with self.bridge.lease():
                self.bridge.call(0)
        echoes = [row for row in self.io.calls if row == ('shell', 'echo', b.CODE)]
        self.assertEqual(len(echoes), 1)
        self.assertEqual(self.io.memory[b.ECHO], b.ORIGINAL)
        self.assertNotEqual(self.io.memory, self.original)
        self.assertTrue(self.bridge.quarantined)
        echo_index = next(i for i, row in enumerate(self.io.calls)
                          if row == ('shell', 'echo', b.CODE))
        later_writes = [row[1] for row in self.io.calls[echo_index + 1:] if row[0] == 'write']
        self.assertTrue(later_writes)
        self.assertTrue(all(address == b.ECHO for address in later_writes))

    def test_settings_changes_reported_not_silently_repaired(self):
        with self.assertRaisesRegex(b.BridgeError, 'settings changed'):
            with self.bridge.lease():
                self.io.changed_settings = True
        self.assertEqual(self.io.memory, self.original)

    def test_unknown_owner_on_exit_not_clobbered(self):
        with self.assertRaisesRegex(b.BridgeError, 'unknown echo'):
            with self.bridge.lease():
                self.io.memory[b.ECHO] = 0xdeadbeef
        self.assertEqual(self.io.memory[b.ECHO], 0xdeadbeef)

    def test_scope_is_readonly(self):
        with self.bridge.lease():
            for operation in (-1, 7, 8, True, '0', 0xC035FFC0):
                with self.assertRaises(b.BridgeError):
                    self.bridge.call(operation)

    def test_outside_lease_refused(self):
        with self.assertRaises(b.BridgeError):
            self.bridge.call(0)

    def test_nonce_rejects_stale_result(self):
        original_shell = self.io.shell
        def no_completion(command, timeout_ms=1000):
            if command == 'echo' and self.io.memory[b.ECHO] == b.CODE:
                return ''
            return original_shell(command)
        self.io.shell = no_completion
        with self.assertRaisesRegex(b.BridgeError, 'scratch retained'):
            with self.bridge.lease():
                self.bridge.call(0)

    def test_wrong_native_driver_rejected_before_writes(self):
        self.io.memory[0xC3476414] = 0
        with self.assertRaisesRegex(b.BridgeError, 'native-L'):
            with self.bridge.lease():
                pass
        self.assertFalse(any(row[0] == 'write' for row in self.io.calls))

    def test_all_five_capture_flags_and_full_sequence_gate(self):
        self.assertTrue(self.bridge.capture_state()['capture_idle'])
        for value in (1, 0x100, 0x10000, 0x1000000):
            self.io.memory[0xC30338C8] = value
            self.assertFalse(self.bridge.capture_state()['capture_idle'])
        self.io.memory[0xC30338C8] = 0
        self.io.memory[0xC30338D0] = 1
        self.assertTrue(self.bridge.capture_state()['movie_recording'])
        self.io.memory[0xC30338D0] = 0
        self.io.memory[0xC3033A6C] = 0x10000
        self.assertFalse(self.bridge.capture_state()['capture_idle'])

    def test_failed_flag_reference_is_not_done(self):
        with self.bridge.lease():
            with self.assertRaisesRegex(b.BridgeError, 'event-reference failed'):
                self.bridge.flags(5)

    def test_signed_conversion(self):
        self.assertEqual(b.signed(0xffffffff), -1)
        self.assertEqual(b.signed(0x7fffffff), 0x7fffffff)


class TransportTests(unittest.TestCase):
    def test_parse_requires_exact_addresses(self):
        transport = b.Transport()
        transport.shell = lambda _: 'get : A:0xc072f700, D:0x00000001\n'
        self.assertEqual(transport.read(b.P), [1])
        with self.assertRaises(b.BridgeError):
            transport.read(b.P, 2)
        with self.assertRaises(b.BridgeError):
            transport.read(b.P + 4)

    def test_duplicate_read_rejected(self):
        transport = b.Transport()
        transport.shell = lambda _: 'A:0xc072f700, D:0x1\nA:0xc072f700, D:0x1'
        with self.assertRaises(b.BridgeError):
            transport.read(b.P, 2)

    def test_write_scope(self):
        transport = b.Transport()
        for address in (0, b.P - 4, b.END, b.ECHO + 4, b.P + 1):
            with self.assertRaises(ValueError):
                transport.ensure(address, 0)

    def test_read_scope(self):
        transport = b.Transport()
        for count in (0, 193, True):
            with self.assertRaises(ValueError):
                transport.read(b.P, count)


if __name__ == '__main__':
    unittest.main()
