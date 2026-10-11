"""Strict offline receiver for one finite AFB1 batch on USB EP83.

The injected ``usb_read`` callable has the shape
``usb_read(endpoint, length, timeout_ms) -> bytes-like``.  It must perform one
bulk-IN attempt and raise on a transport error.  This module never opens USB,
sends a trigger, drains an endpoint, retries a read, or starts another batch.

Reads respect the endpoint's USB packet size.  The first request is one whole
packet, never a 64-byte header buffer on a 1024-byte SuperSpeed endpoint.  Once
that packet validates the AFB1 header, subsequent requests never exceed the
declared batch remainder: complete packet multiples first, then one final
packet-sized request when less than a packet remains.  A short transfer is
accepted only when it completes the declared batch exactly; a zero or
nonterminal short transfer faults permanently.

Recovery belongs to the owner of the USB session.  This receiver never scans,
drains, or silently reads on after a fault, because that could consume bytes
from an unknown or later transmission.
"""
import math
import time

if __package__:
    from . import af_batch
else:
    import af_batch


EP83 = 0x83
MAX_USB_TIMEOUT_MS = 0x7FFFFFFF
VALID_BULK_PACKET_SIZES = frozenset((64, 512, 1024))


class EP83ReceiveError(RuntimeError):
    """One EP83 receive attempt is unusable and must not be continued."""


class EP83Receiver:
    """Receive exactly one bounded AFB1 batch using an injected USB read.

    Successful validation proves only that the bytes received are one complete,
    internally consistent AFB1 batch.  It does not prove that EP83 has no queued
    packets, that the camera-side Wait returned success, or that the sender used
    the intended length.  A declared length ending on a packet boundary
    completes immediately; no extra read waits for a ZLP.  The same session
    owner must verify the EP82 terminal completion and sender result before
    allowing a new batch, and an unknown pending transfer forbids that next
    batch.  This receiver deliberately performs no speculative drain.
    """

    def __init__(self, usb_read, *, expected_nonce, total_timeout_s,
                 max_packet_size=1024,
                 monotonic=time.monotonic):
        if not callable(usb_read):
            raise TypeError('usb_read must be callable')
        if not callable(monotonic):
            raise TypeError('monotonic must be callable')
        if (isinstance(total_timeout_s, bool) or
                not isinstance(total_timeout_s, (int, float)) or
                not 0 < total_timeout_s <= MAX_USB_TIMEOUT_MS / 1000.0):
            raise ValueError('total_timeout_s must fit a positive USB timeout')
        if (type(max_packet_size) is not int or
                max_packet_size not in VALID_BULK_PACKET_SIZES):
            raise ValueError('max_packet_size must be USB bulk MPS 64, 512, or 1024')

        # BatchReceiver validates the nonce before any transport operation.
        self._decoder = af_batch.BatchReceiver(expected_nonce=expected_nonce)
        self._read = usb_read
        self._clock = monotonic
        self._timeout = float(total_timeout_s)
        self._packet = max_packet_size
        self._last_clock = None
        self.attempted = False
        self.closed = False
        self.faulted = False

    def _fail(self, message, cause=None):
        self.faulted = True
        self.closed = True
        self._decoder.invalidate()
        error = EP83ReceiveError(message)
        if cause is None:
            raise error
        raise error from cause

    def _now(self):
        try:
            value = float(self._clock())
        except Exception as exc:
            self._fail('monotonic clock failed', exc)
        if not math.isfinite(value):
            self._fail('monotonic clock returned a non-finite value')
        if self._last_clock is not None and value < self._last_clock:
            self._fail('monotonic clock moved backwards')
        self._last_clock = value
        return value

    def _read_once(self, length, deadline):
        remaining = deadline - self._now()
        if remaining <= 0:
            self._fail('total deadline expired before EP83 read')
        # libusb's timeout has millisecond resolution. Rounding up could let a
        # read outlive the one absolute deadline, so refuse a sub-ms remainder.
        timeout_ms = min(MAX_USB_TIMEOUT_MS, int(remaining * 1000.0))
        if timeout_ms < 1:
            self._fail('total deadline has less than 1 ms before EP83 read')
        try:
            chunk = self._read(EP83, length, timeout_ms)
        except Exception as exc:
            self._fail('EP83 read failed', exc)

        if self._now() >= deadline:
            self._fail('EP83 read exceeded total deadline')
        try:
            view = memoryview(chunk)
            chunk_size = view.nbytes
        except (TypeError, ValueError):
            self._fail('EP83 read returned a non-bytes result')
        if not chunk_size:
            self._fail('EP83 read returned zero bytes')
        if chunk_size > length:
            self._fail(f'EP83 read returned {chunk_size} over requested {length} bytes')
        try:
            chunk = view.tobytes()
        except (TypeError, ValueError):
            self._fail('EP83 read returned an unusable bytes view')
        return chunk

    def receive(self):
        """Return a validated decoded capture, or fault without another read."""
        if self.attempted or self.closed:
            raise EP83ReceiveError('receiver is single-use')
        self.attempted = True
        start = self._now()
        deadline = start + self._timeout
        if not math.isfinite(deadline) or deadline <= start:
            self._fail('total deadline cannot be represented by this clock')

        request = self._packet
        while True:
            chunk = self._read_once(request, deadline)
            short = len(chunk) < request
            try:
                result = self._decoder.feed(chunk)
            except af_batch.CaptureError as exc:
                self._fail('invalid AFB1 batch', exc)

            if result is not None:
                try:
                    self._decoder.finish()
                except af_batch.CaptureError as exc:
                    self._fail('invalid AFB1 batch', exc)
                self.closed = True
                return result

            # A short USB bulk transfer terminates the device transfer.  If the
            # declared batch is not complete, no later read may be used to patch
            # over it.
            if short:
                self._fail(f'nonterminal short EP83 read {len(chunk)}/{request}')

            total = self._decoder.expected
            buffered = len(self._decoder.buffer)
            if (type(total) is not int or
                    not af_batch.BATCH_HEADER_BYTES < total <= af_batch.MAX_BATCH_BYTES or
                    not 0 < buffered < total):
                self._fail('AFB1 header did not establish a bounded remainder')
            remaining_bytes = total - buffered
            if remaining_bytes < self._packet:
                request = self._packet
            else:
                request = (remaining_bytes // self._packet) * self._packet


def receive_batch(usb_read, *, expected_nonce, total_timeout_s,
                  max_packet_size=1024,
                  monotonic=time.monotonic):
    """Convenience wrapper for one single-use :class:`EP83Receiver`."""
    return EP83Receiver(usb_read, expected_nonce=expected_nonce,
                        total_timeout_s=total_timeout_s,
                        max_packet_size=max_packet_size,
                        monotonic=monotonic).receive()
