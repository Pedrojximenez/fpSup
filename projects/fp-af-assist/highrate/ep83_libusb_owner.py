"""Actual, explicit libusb binding for the single-use EP83 session.

Importing this module performs no I/O. There is deliberately no automatic
daemon shutdown, kernel-driver detach, clear-halt, device reset, retry or drain.
Closing a host handle is NOT evidence that the camera's DMA has stopped.
The caller must first arrange the dedicated, reviewed cold-boot camera image.
"""
import contextlib
import ctypes as C
import fcntl
import os
from pathlib import Path
import secrets
import stat
import time


VID, PID = 0x1003, 0xC432
LOCK = '/tmp/fp-af-fusion.lock'
DAEMON_SOCKET = '/tmp/fpshd.sock'
# The maintained copy travels with the USB shell tooling, and is the one the
# daemon is linked and rpath'd against. `parents[2]/'lib'` named a directory that
# has not existed since the repository was restructured, so every lease failed on
# a missing file rather than on anything about the camera.
LIBRARY_CANDIDATES = (Path(__file__).resolve().parents[2] / 'usb-shell-sup/lib/libusb-1.0.dylib',)
DEFAULT_LIBRARY = LIBRARY_CANDIDATES[0]
MAX_TRANSFER = 32896


class USBError(RuntimeError):
    pass


class DeviceDescriptor(C.Structure):
    _fields_ = [(n, t) for n, t in (
        ('bLength', C.c_uint8), ('bDescriptorType', C.c_uint8),
        ('bcdUSB', C.c_uint16), ('bDeviceClass', C.c_uint8),
        ('bDeviceSubClass', C.c_uint8), ('bDeviceProtocol', C.c_uint8),
        ('bMaxPacketSize0', C.c_uint8), ('idVendor', C.c_uint16),
        ('idProduct', C.c_uint16), ('bcdDevice', C.c_uint16),
        ('iManufacturer', C.c_uint8), ('iProduct', C.c_uint8),
        ('iSerialNumber', C.c_uint8), ('bNumConfigurations', C.c_uint8))]


class EndpointDescriptor(C.Structure):
    _fields_ = [(n, C.c_uint8) for n in
                ('bLength', 'bDescriptorType', 'bEndpointAddress', 'bmAttributes')]
    _fields_ += [('wMaxPacketSize', C.c_uint16)]
    _fields_ += [(n, C.c_uint8) for n in ('bInterval', 'bRefresh', 'bSynchAddress')]
    _fields_ += [('extra', C.c_void_p), ('extra_length', C.c_int)]


class InterfaceDescriptor(C.Structure):
    _fields_ = [(n, C.c_uint8) for n in (
        'bLength', 'bDescriptorType', 'bInterfaceNumber', 'bAlternateSetting',
        'bNumEndpoints', 'bInterfaceClass', 'bInterfaceSubClass',
        'bInterfaceProtocol', 'iInterface')]
    _fields_ += [('endpoint', C.POINTER(EndpointDescriptor)),
                ('extra', C.c_void_p), ('extra_length', C.c_int)]


class Interface(C.Structure):
    _fields_ = [('altsetting', C.POINTER(InterfaceDescriptor)),
                ('num_altsetting', C.c_int)]


class ConfigDescriptor(C.Structure):
    _fields_ = [('bLength', C.c_uint8), ('bDescriptorType', C.c_uint8),
                ('wTotalLength', C.c_uint16)]
    _fields_ += [(n, C.c_uint8) for n in (
        'bNumInterfaces', 'bConfigurationValue', 'iConfiguration',
        'bmAttributes', 'MaxPower')]
    _fields_ += [('interface', C.POINTER(Interface)),
                ('extra', C.c_void_p), ('extra_length', C.c_int)]


class LibUSBBackend:
    """Small synchronous C-ABI binding, opened only inside owner.lease()."""
    def __init__(self, library=DEFAULT_LIBRARY):
        # Say which path was tried. A missing library is a host packaging
        # problem, and must not be reported as a camera or transport failure.
        if not Path(library).is_file():
            raise USBError(f'libusb not found at {library}; '
                           'no lease attempted, nothing was opened')
        self.lib = C.CDLL(str(library))
        self.ctx, self.handle = C.c_void_p(), C.c_void_p()
        self.claimed = False
        ptr = C.c_void_p
        specs = {
            'init': (C.c_int, [C.POINTER(ptr)]),
            'exit': (None, [ptr]),
            'get_device_list': (C.c_ssize_t, [ptr, C.POINTER(C.POINTER(ptr))]),
            'free_device_list': (None, [C.POINTER(ptr), C.c_int]),
            'get_device_descriptor': (C.c_int, [ptr, C.POINTER(DeviceDescriptor)]),
            'open': (C.c_int, [ptr, C.POINTER(ptr)]),
            'close': (None, [ptr]),
            'get_device': (ptr, [ptr]),
            'claim_interface': (C.c_int, [ptr, C.c_int]),
            'release_interface': (C.c_int, [ptr, C.c_int]),
            'get_configuration': (C.c_int, [ptr, C.POINTER(C.c_int)]),
            'get_active_config_descriptor': (C.c_int, [ptr, C.POINTER(C.POINTER(ConfigDescriptor))]),
            'free_config_descriptor': (None, [C.POINTER(ConfigDescriptor)]),
            'control_transfer': (C.c_int, [ptr, C.c_uint8, C.c_uint8, C.c_uint16,
                                          C.c_uint16, ptr, C.c_uint16, C.c_uint]),
            'bulk_transfer': (C.c_int, [ptr, C.c_uint8, ptr, C.c_int,
                                       C.POINTER(C.c_int), C.c_uint]),
        }
        for name, (result, args) in specs.items():
            fn = getattr(self.lib, 'libusb_' + name)
            fn.restype, fn.argtypes = result, args

    @staticmethod
    def _check(rc, label):
        if rc != 0:
            raise USBError(f'{label}: libusb error {rc}; no retry')

    def open(self):
        self._check(self.lib.libusb_init(C.byref(self.ctx)), 'init')
        devices = C.POINTER(C.c_void_p)()
        count = self.lib.libusb_get_device_list(self.ctx, C.byref(devices))
        if count < 0:
            raise USBError(f'enumeration: libusb error {count}')
        try:
            matches = []
            for i in range(count):
                d = DeviceDescriptor()
                self._check(self.lib.libusb_get_device_descriptor(devices[i], C.byref(d)),
                            'device descriptor')
                if (d.idVendor, d.idProduct) == (VID, PID):
                    matches.append(devices[i])
            if len(matches) != 1:
                raise USBError(f'expected exactly one fp, found {len(matches)}')
            self._check(self.lib.libusb_open(matches[0], C.byref(self.handle)), 'open')
        finally:
            self.lib.libusb_free_device_list(devices, 1)
        self._check(self.lib.libusb_claim_interface(self.handle, 0), 'claim interface 0')
        self.claimed = True

    def descriptor(self, timeout_ms):
        active = C.c_int()
        self._check(self.lib.libusb_get_configuration(self.handle, C.byref(active)), 'configuration')
        alt = (C.c_uint8 * 1)()
        rc = self.lib.libusb_control_transfer(self.handle, 0x81, 0x0A, 0, 0, alt, 1, timeout_ms)
        if rc != 1 or active.value != 1 or alt[0] != 0:
            raise USBError('expected active configuration 1 / interface 0 / alternate 0')
        config = C.POINTER(ConfigDescriptor)()
        device = self.lib.libusb_get_device(self.handle)
        self._check(self.lib.libusb_get_active_config_descriptor(device, C.byref(config)),
                    'active descriptors')
        try:
            c = config.contents
            if c.bConfigurationValue != active.value or not 1 <= c.bNumInterfaces <= 16:
                raise USBError('inconsistent active configuration')
            candidates = []
            for i in range(c.bNumInterfaces):
                interface = c.interface[i]
                if not 1 <= interface.num_altsetting <= 32:
                    raise USBError('invalid alternate settings')
                for j in range(interface.num_altsetting):
                    a = interface.altsetting[j]
                    if (a.bInterfaceNumber, a.bAlternateSetting) == (0, 0):
                        candidates.append(a)
            if len(candidates) != 1:
                raise USBError('ambiguous active interface')
            a = candidates[0]
            if a.bInterfaceClass != 0xFF or not 3 <= a.bNumEndpoints <= 16:
                raise USBError('dedicated vendor interface is not present')
            endpoints = {}
            for i in range(a.bNumEndpoints):
                e = a.endpoint[i]
                if e.bEndpointAddress in endpoints:
                    raise USBError('duplicate endpoint descriptor')
                endpoints[e.bEndpointAddress] = (int(e.bmAttributes), int(e.wMaxPacketSize))
            for ep in (0x01, 0x82, 0x83):
                if ep not in endpoints:
                    raise USBError(f'missing endpoint {ep:#04x}')
                attributes, mps = endpoints[ep]
                if attributes & 3 != 2 or mps not in (64, 512, 1024):
                    raise USBError(f'endpoint {ep:#04x} is not supported bulk')
            return {'configuration_value': active.value, 'interface_number': 0,
                    'alternate_setting': int(alt[0]), 'endpoint_address': 0x83,
                    'attributes': endpoints[0x83][0],
                    'max_packet_size': endpoints[0x83][1]}, endpoints
        finally:
            self.lib.libusb_free_config_descriptor(config)

    def transfer(self, endpoint, value, timeout_ms):
        length = value if type(value) is int else len(value)
        buffer = (C.c_uint8 * length)()
        if not endpoint & 0x80:
            C.memmove(buffer, bytes(value), length)
        actual = C.c_int()
        rc = self.lib.libusb_bulk_transfer(self.handle, endpoint, buffer, length,
                                          C.byref(actual), timeout_ms)
        data = bytes(buffer[:max(0, min(actual.value, length))])
        return rc, actual.value, data

    def close(self):
        try:
            if self.claimed:
                self.claimed = False
                self._check(self.lib.libusb_release_interface(self.handle, 0), 'release interface')
        finally:
            if self.handle:
                self.lib.libusb_close(self.handle)
                self.handle = C.c_void_p()
            if self.ctx:
                self.lib.libusb_exit(self.ctx)
                self.ctx = C.c_void_p()


class LibusbOwner:
    """One handle, one claim, one trigger, no reuse even after success.

    ``audit`` receives intent/result dictionaries (including raw bytes as hex).
    Caller should persist them before/after transfers. A logger error aborts.
    The lock excludes cooperative AF tools; it does not stop unknown clients.
    Read-only process checks and explicit old-daemon shutdown remain required
    operator preconditions. Socket presence is rejected, including stale paths.
    """
    def __init__(self, *, backend_factory=LibUSBBackend, audit=None,
                 lock_path=LOCK, daemon_socket=DAEMON_SOCKET):
        self._factory, self._audit = backend_factory, audit or (lambda event: None)
        self._lock_path, self._socket = str(lock_path), str(daemon_socket)
        self._backend = None
        self._used = self._leased = self._triggered = self._terminal = self._reserved = False
        self._endpoints = None
        self.faulted = False

    def _event(self, **data):
        self._audit(dict(monotonic=time.monotonic(), **data))

    def _check(self, timeout_ms):
        if not self._leased or self.faulted:
            raise USBError('owner is not leased or is quarantined')
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 0x7FFFFFFF:
            raise ValueError('finite positive timeout required')

    @contextlib.contextmanager
    def lease(self, timeout_ms):
        if self._used:
            raise USBError('owner is single-use')
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 0x7FFFFFFF:
            raise ValueError('finite positive timeout required')
        self._used = True
        fd = None
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise USBError('lease lock is not a regular file')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if os.path.lexists(self._socket):
                raise USBError('fpshd socket exists: cleanly stop the old owner first; not done automatically')
            self._backend = self._factory()
            self._backend.open()
            self._leased = True
            self._event(operation='lease', result='claimed')
            yield self
        except BaseException:
            self.faulted = True
            raise
        finally:
            self._leased = False
            try:
                if self._backend is not None:
                    self._backend.close()
            except BaseException:
                self.faulted = True
                raise
            finally:
                if fd is not None:
                    os.close(fd)

    def reserve_sequence(self):
        self._check(1)
        if self._reserved:
            raise USBError('sequence already reserved')
        self._reserved = True
        return secrets.randbelow(0xFFFFFFFF) + 1

    def read_ep83_descriptor(self, timeout_ms):
        self._check(timeout_ms)
        if self._endpoints is not None or self._triggered:
            raise USBError('descriptor inspection is single-use and precedes trigger')
        descriptor, self._endpoints = self._backend.descriptor(timeout_ms)
        self._event(operation='descriptor', descriptor=descriptor, endpoints=self._endpoints)
        return descriptor

    def _transfer(self, endpoint, value, timeout_ms):
        self._check(timeout_ms)
        length = value if type(value) is int else len(value)
        self._event(operation='transfer-intent', endpoint=endpoint, requested=length,
                    timeout_ms=timeout_ms, data_hex=None if type(value) is int else bytes(value).hex())
        try:
            rc, actual, data = self._backend.transfer(endpoint, value, timeout_ms)
            self._event(operation='transfer-result', endpoint=endpoint, requested=length,
                        actual=actual, libusb_rc=rc, data_hex=data.hex())
            if rc != 0 or not 0 < actual <= length or len(data) != actual:
                raise USBError(f'endpoint {endpoint:#04x}: rc={rc}, bytes={actual}/{length}; quarantined')
            return actual, data
        except BaseException:
            self.faulted = True
            raise

    def send_trigger(self, frame, timeout_ms):
        self._check(timeout_ms)
        if self._triggered or not self._reserved or self._endpoints is None or len(frame) != 64:
            raise USBError('one exact trigger requires sequence and inspected endpoints')
        self._triggered = True  # latch BEFORE possible USB submission
        actual, _ = self._transfer(0x01, frame, timeout_ms)
        if actual != 64:
            self.faulted = True
            raise USBError('short trigger; execution unknown; no retry')
        return actual

    def usb_read(self, endpoint, length, timeout_ms):
        self._check(timeout_ms)
        if not self._triggered or self._terminal or endpoint != 0x83:
            raise USBError('only EP83 is readable after the trigger and before terminal')
        mps = self._endpoints[0x83][1]
        if type(length) is not int or not mps <= length <= MAX_TRANSFER or length % mps:
            raise USBError('EP83 read must use bounded whole-packet buffer')
        return self._transfer(endpoint, length, timeout_ms)[1]

    def read_terminal(self, endpoint, length, timeout_ms):
        self._check(timeout_ms)
        if not self._triggered or self._terminal or endpoint != 0x82 or length != 64:
            raise USBError('one exact EP82 terminal is permitted')
        self._terminal = True
        # USB buffer is MPS-sized; logical protocol response is exactly 64 bytes.
        actual, data = self._transfer(endpoint, self._endpoints[0x82][1], timeout_ms)
        if actual != 64:
            self.faulted = True
            raise USBError('terminal is not exactly 64 bytes; no drain')
        return data
