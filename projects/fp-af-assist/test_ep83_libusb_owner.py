"""Offline host ownership and exact-transfer checks. Never loads libusb."""
import ctypes
from pathlib import Path
import tempfile
import unittest

from highrate import ep83_libusb_owner as usb


class FakeBackend:
    def __init__(self):
        self.calls = []
        self.next_result = None

    def open(self):
        self.calls.append(('open',))

    def close(self):
        self.calls.append(('close',))

    def descriptor(self, timeout):
        self.calls.append(('descriptor', timeout))
        return (dict(configuration_value=1, interface_number=0, alternate_setting=0,
                     endpoint_address=0x83, attributes=2, max_packet_size=1024),
                {1: (2, 1024), 0x82: (2, 1024), 0x83: (2, 1024)})

    def transfer(self, ep, value, timeout):
        self.calls.append(('transfer', ep, value, timeout))
        if self.next_result is not None:
            return self.next_result
        length = (64 if ep == 0x82 else value) if type(value) is int else len(value)
        return 0, length, bytes(length)


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = FakeBackend()
        self.events = []
        self.owner = self.make_owner()

    def make_owner(self):
        return usb.LibusbOwner(backend_factory=lambda: self.backend,
                               audit=self.events.append,
                               lock_path=self.root / 'lock',
                               daemon_socket=self.root / 'fpshd.sock')

    def prime(self):
        self.assertGreater(self.owner.reserve_sequence(), 0)
        self.owner.read_ep83_descriptor(100)
        self.assertEqual(self.owner.send_trigger(bytes(64), 100), 64)

    def test_one_owner_one_trigger_packet_sized_terminal(self):
        self.assertEqual(self.backend.calls, [])
        with self.owner.lease(100):
            self.prime()
            self.assertEqual(len(self.owner.usb_read(0x83, 1024, 100)), 1024)
            self.assertEqual(len(self.owner.read_terminal(0x82, 64, 100)), 64)
            with self.assertRaises(usb.USBError):
                self.owner.send_trigger(bytes(64), 100)
        self.assertEqual(self.backend.calls[-2], ('transfer', 0x82, 1024, 100))
        self.assertEqual(self.backend.calls[-1], ('close',))
        with self.assertRaises(usb.USBError), self.owner.lease(100):
            self.fail('owner reused')

    def test_partial_error_is_logged_once_and_quarantines(self):
        with self.owner.lease(100):
            self.prime()
            self.backend.next_result = (-7, 16, bytes(16))
            with self.assertRaises(usb.USBError):
                self.owner.usb_read(0x83, 1024, 100)
            self.assertTrue(self.owner.faulted)
            count = len(self.backend.calls)
            with self.assertRaises(usb.USBError):
                self.owner.usb_read(0x83, 1024, 100)
            self.assertEqual(len(self.backend.calls), count)
        self.assertEqual(self.events[-1]['actual'], 16)
        self.assertEqual(self.events[-1]['libusb_rc'], -7)

    def test_short_trigger_cannot_retry(self):
        with self.owner.lease(100):
            self.owner.reserve_sequence()
            self.owner.read_ep83_descriptor(100)
            self.backend.next_result = (0, 12, bytes(12))
            with self.assertRaises(usb.USBError):
                self.owner.send_trigger(bytes(64), 100)
            self.assertTrue(self.owner.faulted)
            with self.assertRaises(usb.USBError):
                self.owner.send_trigger(bytes(64), 100)
        self.assertEqual(sum(c[0] == 'transfer' for c in self.backend.calls), 1)

    def test_no_small_usb_buffers_or_wrong_endpoint(self):
        with self.owner.lease(100):
            self.prime()
            for ep, length in ((0x83, 64), (0x82, 1024), (0x83, 32897), (0x83, 2049)):
                with self.assertRaises(usb.USBError):
                    self.owner.usb_read(ep, length, 100)
            self.assertEqual(sum(c[0] == 'transfer' for c in self.backend.calls), 1)

    def test_long_terminal_no_drain(self):
        with self.owner.lease(100):
            self.prime()
            self.backend.next_result = (0, 128, bytes(128))
            with self.assertRaises(usb.USBError):
                self.owner.read_terminal(0x82, 64, 100)
            with self.assertRaises(usb.USBError):
                self.owner.read_terminal(0x82, 64, 100)
        self.assertEqual(sum(c[0] == 'transfer' for c in self.backend.calls), 2)

    def test_existing_socket_and_symlink_stop_before_usb(self):
        (self.root / 'fpshd.sock').symlink_to(self.root / 'nonexistent')
        with self.assertRaises(usb.USBError), self.owner.lease(100):
            self.fail('existing socket accepted')
        self.assertEqual(self.backend.calls, [])
        (self.root / 'fpshd.sock').unlink()
        (self.root / 'lock').unlink()
        (self.root / 'lock').symlink_to(self.root / 'target')
        with self.assertRaises(OSError), self.make_owner().lease(100):
            self.fail('symlink lock accepted')
        self.assertEqual(self.backend.calls, [])

    def test_concurrent_lease_rejected_before_second_open(self):
        with self.owner.lease(100):
            with self.assertRaises(BlockingIOError), self.make_owner().lease(100):
                self.fail('second owner')
        self.assertEqual(self.backend.calls, [('open',), ('close',)])

    def test_audit_failure_before_trigger_stops_submission(self):
        with self.owner.lease(100):
            self.owner.reserve_sequence()
            self.owner.read_ep83_descriptor(100)
            def broken(_):
                raise OSError('log failed')
            self.owner._audit = broken
            with self.assertRaises(OSError):
                self.owner.send_trigger(bytes(64), 100)
            with self.assertRaises(usb.USBError):
                self.owner.send_trigger(bytes(64), 100)
        self.assertEqual(sum(c[0] == 'transfer' for c in self.backend.calls), 0)

    def test_descriptor_native_abi_layout_64bit(self):
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            self.skipTest('64-bit host layout')
        self.assertEqual(ctypes.sizeof(usb.DeviceDescriptor), 18)
        self.assertEqual(ctypes.sizeof(usb.EndpointDescriptor), 32)
        self.assertEqual(usb.EndpointDescriptor.extra.offset, 16)
        self.assertEqual(ctypes.sizeof(usb.InterfaceDescriptor), 40)
        self.assertEqual(usb.InterfaceDescriptor.endpoint.offset, 16)
        self.assertEqual(ctypes.sizeof(usb.Interface), 16)
        self.assertEqual(ctypes.sizeof(usb.ConfigDescriptor), 40)
        self.assertEqual(usb.ConfigDescriptor.interface.offset, 16)


if __name__ == '__main__':
    unittest.main()
