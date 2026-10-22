"""One-shot EP83 host coordinator with an injected, already-open USB owner.

This module never opens a device or socket and has no SHL, memory, file,
installer, retry, reconnect, or drain path.  The injected owner must serialize
the existing interface under one lease and provide exactly these methods::

    lease(timeout_ms) -> context manager
    read_ep83_descriptor(timeout_ms) -> active-descriptor mapping
    reserve_sequence() -> fresh nonzero FPSH sequence
    send_trigger(frame64, timeout_ms) -> bytes transferred
    usb_read(endpoint, length, timeout_ms) -> bytes-like
    read_terminal(endpoint, frame_length, timeout_ms) -> bytes-like

``read_terminal(0x82, 64, ...)`` describes the exact logical frame required by
this codec.  A libusb implementation must allocate/request at least the real
EP82 maximum packet size internally and then return exactly one 64-byte frame;
it must not use an undersized 64-byte libusb buffer on a larger-packet endpoint.

The current first-test contract deliberately accepts only synthetic camera
source state ``SYNT``.  A successful report therefore remains
``producer_not_installed`` and is never hardware or AF validation.
"""
from collections.abc import Mapping
from dataclasses import asdict, dataclass
import math
import struct
import time
import zlib

if __package__:
    from . import af_batch
    from . import ep83_receiver
else:
    import af_batch
    import ep83_receiver


EP82 = 0x82
EP83 = 0x83
USB_INTERFACE = 0
USB_CONFIGURATION = 1
USB_ALT_SETTING = 0
USB_TRANSFER_TYPE_BULK = 2

FPSH_MAGIC = b"FPSH"
FPSH_VERSION = 1
FPSH_COMMAND_AF83 = 4
FPSH_FRAME_BYTES = 64
FPSH_PAYLOAD_BYTES = 44
FPSH_CHECKSUM_OFFSET = 16
FPSH_FRAME = struct.Struct("<4sBBHIHHI44s")

TRIGGER_MAGIC = b"AF83"
TRIGGER_VERSION = 1
TRIGGER_PAYLOAD = struct.Struct("<4sHH6I")
TRIGGER_PAYLOAD_BYTES = TRIGGER_PAYLOAD.size

TERMINAL_MAGIC = b"AFT1"
TERMINAL_VERSION = 1
TERMINAL_PAYLOAD = struct.Struct("<4sHH6IiiI")
TERMINAL_PAYLOAD_BYTES = TERMINAL_PAYLOAD.size

AF_TX_COMPLETE = 4
CAMERA_STATE_SYNTHETIC = 0x53594E54  # 'SYNT' as an explicit u32 identity.
TERMINAL_FLAG_DMA_RECLAIMABLE = 1 << 0
TERMINAL_FLAG_DMA_MAY_BE_OWNED = 1 << 1
TERMINAL_KNOWN_FLAGS = (TERMINAL_FLAG_DMA_RECLAIMABLE |
                        TERMINAL_FLAG_DMA_MAY_BE_OWNED)

MAX_USB_TIMEOUT_MS = ep83_receiver.MAX_USB_TIMEOUT_MS
VALID_PACKET_SIZES = ep83_receiver.VALID_BULK_PACKET_SIZES

STATE_FRESH = "fresh"
STATE_LEASING = "leasing"
STATE_PREFLIGHT = "preflight"
STATE_IN_FLIGHT = "in_flight"
STATE_RECEIVING = "receiving"
STATE_TERMINAL = "terminal"
STATE_VERIFYING = "verifying"
STATE_COMPLETE = "complete"
STATE_REJECTED = "rejected"
STATE_QUARANTINED = "quarantined"


class EP83WireError(ValueError):
    """An FPSH CMD4 trigger or terminal frame violates the fixed wire ABI."""


class EP83HostSessionError(RuntimeError):
    """The one-shot session failed and exposes whether reuse is forbidden."""

    def __init__(self, message, *, state, quarantined):
        super().__init__(message)
        self.state = state
        self.quarantined = quarantined


@dataclass(frozen=True)
class Trigger:
    sequence: int
    nonce: int
    count: int
    expected_batch_bytes: int
    flags: int


@dataclass(frozen=True)
class Terminal:
    sequence: int
    nonce: int
    count: int
    actual_batch_bytes: int
    batch_crc: int
    phase: int
    camera_state: int
    error: int
    platform_rc: int
    result_flags: int


def _u32(value, name, *, nonzero=False):
    if (type(value) is not int or value < int(nonzero) or
            value > 0xFFFFFFFF):
        raise EP83WireError(f"invalid {name}")
    return value


def _i32(value, name):
    if type(value) is not int or not -(1 << 31) <= value < (1 << 31):
        raise EP83WireError(f"invalid {name}")
    return value


def expected_batch_bytes(count):
    if type(count) is not int or not 1 <= count <= af_batch.MAX_CAPACITY:
        raise EP83WireError("count must be 1..256")
    return af_batch.BATCH_HEADER_BYTES + af_batch.HEADER_BYTES + count * af_batch.RECORD_BYTES


def _frame(*, sequence, payload, payload_length):
    _u32(sequence, "FPSH sequence", nonzero=True)
    if (type(payload) is not bytes or type(payload_length) is not int or
            payload_length != len(payload) or payload_length > FPSH_PAYLOAD_BYTES):
        raise EP83WireError("invalid FPSH payload")
    padded = payload + bytes(FPSH_PAYLOAD_BYTES - payload_length)
    frame = bytearray(FPSH_FRAME.pack(
        FPSH_MAGIC, FPSH_VERSION, FPSH_COMMAND_AF83, 0, sequence,
        payload_length, 0, 0, padded))
    struct.pack_into("<I", frame, FPSH_CHECKSUM_OFFSET, zlib.crc32(frame))
    return bytes(frame)


def _decode_frame(frame, *, expected_sequence, expected_payload_bytes):
    _u32(expected_sequence, "expected FPSH sequence", nonzero=True)
    try:
        raw = memoryview(frame).tobytes()
    except (TypeError, ValueError) as exc:
        raise EP83WireError("FPSH frame is not usable bytes") from exc
    if len(raw) != FPSH_FRAME_BYTES:
        raise EP83WireError("FPSH frame must be exactly 64 bytes")
    try:
        magic, version, command, flags, sequence, payload_length, status, checksum, payload = (
            FPSH_FRAME.unpack(raw))
    except struct.error as exc:
        raise EP83WireError("malformed FPSH frame") from exc
    check = bytearray(raw)
    struct.pack_into("<I", check, FPSH_CHECKSUM_OFFSET, 0)
    if zlib.crc32(check) != checksum:
        raise EP83WireError("FPSH frame checksum mismatch")
    if (magic != FPSH_MAGIC or version != FPSH_VERSION or
            command != FPSH_COMMAND_AF83 or flags != 0 or status != 0):
        raise EP83WireError("FPSH CMD4 identity/status mismatch")
    if sequence != expected_sequence:
        raise EP83WireError("FPSH terminal sequence mismatch")
    if payload_length != expected_payload_bytes:
        raise EP83WireError("FPSH payload length mismatch")
    if any(payload[payload_length:]):
        raise EP83WireError("FPSH payload padding is not zero")
    return payload[:payload_length]


def encode_trigger_frame(*, sequence, nonce, count):
    """Encode one exact 64-byte FPSH CMD4 trigger frame."""
    _u32(nonce, "nonce", nonzero=True)
    total = expected_batch_bytes(count)
    payload = TRIGGER_PAYLOAD.pack(
        TRIGGER_MAGIC, TRIGGER_VERSION, TRIGGER_PAYLOAD_BYTES,
        nonce, count, total, 0, 0, 0)
    return _frame(sequence=sequence, payload=payload,
                  payload_length=TRIGGER_PAYLOAD_BYTES)


def decode_trigger_frame(frame, *, expected_sequence):
    payload = _decode_frame(frame, expected_sequence=expected_sequence,
                            expected_payload_bytes=TRIGGER_PAYLOAD_BYTES)
    try:
        magic, version, size, nonce, count, total, flags, reserved0, reserved1 = (
            TRIGGER_PAYLOAD.unpack(payload))
    except struct.error as exc:
        raise EP83WireError("malformed AF83 trigger payload") from exc
    if (magic != TRIGGER_MAGIC or version != TRIGGER_VERSION or
            size != TRIGGER_PAYLOAD_BYTES or flags or reserved0 or reserved1):
        raise EP83WireError("AF83 trigger identity/reserved mismatch")
    _u32(nonce, "trigger nonce", nonzero=True)
    if total != expected_batch_bytes(count):
        raise EP83WireError("AF83 trigger batch length mismatch")
    return Trigger(expected_sequence, nonce, count, total, flags)


def encode_terminal_frame(*, sequence, nonce, count, actual_batch_bytes,
                          batch_crc, phase=AF_TX_COMPLETE,
                          camera_state=CAMERA_STATE_SYNTHETIC,
                          error=0, platform_rc=0,
                          result_flags=TERMINAL_FLAG_DMA_RECLAIMABLE):
    """Encode the fixed first-test terminal frame for mocks/adapters."""
    _u32(nonce, "nonce", nonzero=True)
    expected_batch_bytes(count)
    _u32(actual_batch_bytes, "actual batch bytes", nonzero=True)
    _u32(batch_crc, "batch CRC")
    _u32(phase, "sender phase")
    _u32(camera_state, "camera state")
    _i32(error, "sender error")
    _i32(platform_rc, "platform rc")
    _u32(result_flags, "terminal result flags")
    payload = TERMINAL_PAYLOAD.pack(
        TERMINAL_MAGIC, TERMINAL_VERSION, TERMINAL_PAYLOAD_BYTES,
        nonce, count, actual_batch_bytes, batch_crc, phase, camera_state,
        error, platform_rc, result_flags)
    return _frame(sequence=sequence, payload=payload,
                  payload_length=TERMINAL_PAYLOAD_BYTES)


def decode_terminal_frame(frame, *, expected_sequence):
    payload = _decode_frame(frame, expected_sequence=expected_sequence,
                            expected_payload_bytes=TERMINAL_PAYLOAD_BYTES)
    try:
        values = TERMINAL_PAYLOAD.unpack(payload)
    except struct.error as exc:
        raise EP83WireError("malformed AFT1 terminal payload") from exc
    (magic, version, size, nonce, count, actual, batch_crc, phase,
     camera_state, error, platform_rc, result_flags) = values
    if (magic != TERMINAL_MAGIC or version != TERMINAL_VERSION or
            size != TERMINAL_PAYLOAD_BYTES):
        raise EP83WireError("AFT1 terminal identity mismatch")
    _u32(nonce, "terminal nonce", nonzero=True)
    expected_batch_bytes(count)
    _u32(actual, "terminal actual batch bytes", nonzero=True)
    if result_flags & ~TERMINAL_KNOWN_FLAGS:
        raise EP83WireError("AFT1 terminal has unknown result flags")
    return Terminal(expected_sequence, nonce, count, actual, batch_crc, phase,
                    camera_state, error, platform_rc, result_flags)


class _TrackedRead:
    def __init__(self, owner):
        self.owner = owner
        self.actual_bytes = 0
        self.batch_crc = 0

    def __call__(self, endpoint, length, timeout_ms):
        chunk = self.owner.usb_read(endpoint, length, timeout_ms)
        try:
            blob = memoryview(chunk).tobytes()
        except (TypeError, ValueError):
            # Preserve the original result so EP83Receiver owns the canonical
            # bytes-like validation and error classification.
            return chunk
        self.actual_bytes += len(blob)
        self.batch_crc = zlib.crc32(blob, self.batch_crc)
        return chunk


class EP83HostSession:
    """Coordinate exactly one trigger, EP83 batch and EP82 terminal frame."""

    REQUIRED_OWNER_METHODS = (
        "lease", "read_ep83_descriptor", "reserve_sequence",
        "send_trigger", "usb_read", "read_terminal",
    )

    def __init__(self, owner, *, nonce, count, total_timeout_s,
                 monotonic=time.monotonic):
        for name in self.REQUIRED_OWNER_METHODS:
            if not callable(getattr(owner, name, None)):
                raise TypeError(f"owner.{name} must be callable")
        _u32(nonce, "nonce", nonzero=True)
        expected_batch_bytes(count)
        if (isinstance(total_timeout_s, bool) or
                not isinstance(total_timeout_s, (int, float)) or
                not 0 < total_timeout_s <= MAX_USB_TIMEOUT_MS / 1000.0):
            raise ValueError("total_timeout_s must fit a positive USB timeout")
        if not callable(monotonic):
            raise TypeError("monotonic must be callable")
        self.owner = owner
        self.nonce = nonce
        self.count = count
        self.total_timeout_s = float(total_timeout_s)
        self.monotonic = monotonic
        self.state = STATE_FRESH
        self.attempted = False
        self.closed = False
        self.trigger_attempted = False
        self.quarantined = False
        self.last_error = None
        self._last_clock = None

    def _fail(self, message, cause=None):
        self.quarantined = self.trigger_attempted
        self.state = STATE_QUARANTINED if self.quarantined else STATE_REJECTED
        self.closed = True
        self.last_error = message
        error = EP83HostSessionError(
            message, state=self.state, quarantined=self.quarantined)
        if cause is None:
            raise error
        raise error from cause

    def _now(self):
        try:
            value = float(self.monotonic())
        except Exception as exc:
            self._fail("monotonic clock failed", exc)
        if not math.isfinite(value):
            self._fail("monotonic clock returned a non-finite value")
        if self._last_clock is not None and value < self._last_clock:
            self._fail("monotonic clock moved backwards")
        self._last_clock = value
        return value

    def _remaining(self, deadline, *, usb_operation):
        remaining = deadline - self._now()
        if remaining <= 0:
            self._fail("one-shot deadline expired")
        if usb_operation and int(remaining * 1000.0) < 1:
            self._fail("one-shot deadline has less than 1 ms")
        return remaining

    def _timeout_ms(self, deadline):
        remaining = self._remaining(deadline, usb_operation=True)
        return min(MAX_USB_TIMEOUT_MS, int(remaining * 1000.0))

    def _descriptor(self, value):
        required = {
            "configuration_value", "interface_number", "alternate_setting",
            "endpoint_address", "attributes", "max_packet_size",
        }
        if not isinstance(value, Mapping) or not required <= set(value):
            self._fail("owner did not return the required active EP83 descriptor")
        for name in required:
            if type(value[name]) is not int:
                self._fail(f"EP83 descriptor {name} is not an integer")
        if (value["configuration_value"] != USB_CONFIGURATION or
                value["interface_number"] != USB_INTERFACE or
                value["alternate_setting"] != USB_ALT_SETTING or
                value["endpoint_address"] != EP83 or
                value["attributes"] & 3 != USB_TRANSFER_TYPE_BULK or
                value["max_packet_size"] not in VALID_PACKET_SIZES):
            self._fail("active EP83 descriptor identity/MPS mismatch")
        return {name: value[name] for name in sorted(required)}

    def _run_leased(self, deadline):
        self.state = STATE_PREFLIGHT
        try:
            descriptor_raw = self.owner.read_ep83_descriptor(self._timeout_ms(deadline))
        except EP83HostSessionError:
            raise
        except Exception as exc:
            self._fail("active EP83 descriptor read failed", exc)
        descriptor = self._descriptor(descriptor_raw)

        try:
            sequence = self.owner.reserve_sequence()
        except Exception as exc:
            self._fail("FPSH sequence reservation failed", exc)
        try:
            _u32(sequence, "reserved FPSH sequence", nonzero=True)
            trigger = encode_trigger_frame(
                sequence=sequence, nonce=self.nonce, count=self.count)
        except EP83WireError as exc:
            self._fail("owner returned an invalid FPSH sequence", exc)

        # From immediately before dispatch onward every failure is uncertain.
        self.state = STATE_IN_FLIGHT
        self.trigger_attempted = True
        self.quarantined = True
        try:
            moved = self.owner.send_trigger(trigger, self._timeout_ms(deadline))
        except EP83HostSessionError:
            raise
        except Exception as exc:
            self._fail("AF83 trigger outcome is uncertain", exc)
        if type(moved) is not int or moved != FPSH_FRAME_BYTES:
            self._fail("AF83 trigger was not exactly one 64-byte transfer")

        self.state = STATE_RECEIVING
        tracked = _TrackedRead(self.owner)
        try:
            receiver = ep83_receiver.EP83Receiver(
                tracked, expected_nonce=self.nonce,
                total_timeout_s=self._remaining(deadline, usb_operation=True),
                max_packet_size=descriptor["max_packet_size"],
                monotonic=self.monotonic)
            decoded = receiver.receive()
        except EP83HostSessionError:
            raise
        except Exception as exc:
            self._fail("EP83 batch receive failed", exc)
        expected = expected_batch_bytes(self.count)
        if (decoded.get("nonce") != self.nonce or
                decoded.get("count") != self.count or
                tracked.actual_bytes != expected or
                decoded.get("usable_for_af_control") is not False or
                decoded.get("usable_for_dfd") is not False):
            self._fail("EP83 decoded batch identity/size/safety mismatch")

        self.state = STATE_TERMINAL
        try:
            terminal_raw = self.owner.read_terminal(
                EP82, FPSH_FRAME_BYTES, self._timeout_ms(deadline))
        except EP83HostSessionError:
            raise
        except Exception as exc:
            self._fail("EP82 AFT1 terminal read failed", exc)
        try:
            terminal = decode_terminal_frame(
                terminal_raw, expected_sequence=sequence)
        except EP83WireError as exc:
            self._fail("invalid EP82 AFT1 terminal", exc)

        self.state = STATE_VERIFYING
        if (terminal.nonce != self.nonce or terminal.count != self.count or
                terminal.actual_batch_bytes != tracked.actual_bytes or
                terminal.batch_crc != tracked.batch_crc or
                terminal.phase != AF_TX_COMPLETE or
                terminal.camera_state != CAMERA_STATE_SYNTHETIC or
                terminal.error != 0 or terminal.platform_rc != 0 or
                terminal.result_flags != TERMINAL_FLAG_DMA_RECLAIMABLE):
            self._fail("AFT1 terminal does not match the completed EP83 batch")
        self._remaining(deadline, usb_operation=False)
        return {
            "schema": "fp-af-ep83-host-session-v1",
            "sequence": sequence,
            "nonce": self.nonce,
            "count": self.count,
            "actual_batch_bytes": tracked.actual_bytes,
            "batch_crc": tracked.batch_crc,
            "max_packet_size": descriptor["max_packet_size"],
            "descriptor": descriptor,
            "terminal": asdict(terminal),
            "capture": decoded,
            "producer_not_installed": True,
            "hardware_validated": False,
            "usable_for_af_control": False,
            "usable_for_dfd": False,
        }

    def run(self):
        if self.attempted or self.closed:
            raise EP83HostSessionError(
                "host session is single-use", state=self.state,
                quarantined=self.quarantined)
        self.attempted = True
        self.state = STATE_LEASING
        start = self._now()
        deadline = start + self.total_timeout_s
        if not math.isfinite(deadline) or deadline <= start:
            self._fail("one-shot deadline cannot be represented")
        report = None
        try:
            with self.owner.lease(self._timeout_ms(deadline)):
                report = self._run_leased(deadline)
        except EP83HostSessionError:
            raise
        except Exception as exc:
            self._fail("owner lease/session operation failed", exc)
        if report is None:
            self._fail("owner lease suppressed a session failure")
        self._remaining(deadline, usb_operation=False)
        self.state = STATE_COMPLETE
        self.closed = True
        self.quarantined = False
        report["owner_lease_released"] = True
        report["quarantined"] = False
        return report


def run_one_shot(owner, *, nonce, count, total_timeout_s,
                 monotonic=time.monotonic):
    """Convenience wrapper for one single-use :class:`EP83HostSession`."""
    return EP83HostSession(
        owner, nonce=nonce, count=count, total_timeout_s=total_timeout_s,
        monotonic=monotonic).run()
