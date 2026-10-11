"""Strict FPSH v1 candidate codec. Pure bytes; no socket, USB or device access.

Use only with the reviewed native-owner adapter, never as a retry wrapper for
the current worker. One daemon per cold boot; sequence starts at 1, never wraps.
"""
import struct
import zlib

FRAME_SIZE = 64
PAYLOAD_SIZE = 44
REPLY_CAP = 128


class ProtocolError(ValueError):
    pass


def _frame(command, sequence, payload=b''):
    if not 1 <= sequence <= 0xffffffff:
        raise ProtocolError('sequence outside non-wrapping session')
    data = bytearray(struct.pack('<4sBBHIHHI', b'FPSH', 1, command, 0,
                                 sequence, len(payload), 0, 0))
    data.extend(payload)
    data.extend(bytes(FRAME_SIZE - len(data)))
    struct.pack_into('<I', data, 16, zlib.crc32(data))
    return bytes(data)


def request(sequence, operation):
    if operation == 'ping':
        return _frame(1, sequence)
    if operation == 'version':
        return _frame(3, sequence, b'shl version')
    raise ProtocolError('only ping and fixed read-only version are supported')


class Reply:
    """Bounded one-exchange accumulator. Any error permanently closes it.

    Every transport error must call invalidate(); retrying accept() cannot
    recover an uncertain exchange. The owner of this object must also latch its
    whole session; creating another Reply is not a recovery procedure.
    """
    def __init__(self, sequence, operation):
        encoded = request(sequence, operation)
        self.sequence = sequence
        self.command = encoded[5]
        self.operation = operation
        self.frames = 0
        self.data = bytearray()
        self.done = False
        self.faulted = False

    def invalidate(self):
        self.faulted = True

    def accept(self, frame):
        try:
            if self.done or self.faulted:
                raise ProtocolError('exchange already closed')
            if len(frame) != FRAME_SIZE:
                raise ProtocolError('expected a complete 64-byte reply')
            magic, ver, cmd, flags, seq, length, status, crc = struct.unpack_from(
                '<4sBBHIHHI', frame)
            data = bytearray(frame)
            data[16:20] = bytes(4)
            if magic != b'FPSH' or ver != 1 or zlib.crc32(data) != crc:
                raise ProtocolError('invalid reply identity or checksum')
            if cmd != self.command or seq != self.sequence:
                raise ProtocolError('reply belongs to another command')
            if flags not in (0, 1) or length > PAYLOAD_SIZE:
                raise ProtocolError('unsupported reply flags or length')
            if status != 0:
                raise ProtocolError(f'camera rejected command, status={status}')
            if any(data[20 + length:]):
                raise ProtocolError('nonzero reply padding')
            if (flags and length != PAYLOAD_SIZE) or not length:
                raise ProtocolError('empty or short nonterminal reply')
            self.frames += 1
            if self.frames > 3 or len(self.data) + length > REPLY_CAP:
                raise ProtocolError('reply exceeds fixed bound')
            self.data.extend(data[20:20 + length])
            if not flags:
                if self.operation == 'ping' and bytes(self.data) != b'pong':
                    raise ProtocolError('unexpected ping result')
                self.done = True
                return bytes(self.data)
            if self.frames == 3:
                raise ProtocolError('continuation exceeds frame bound')
            return None
        except (ValueError, TypeError, struct.error) as exc:
            self.faulted = True
            if isinstance(exc, ProtocolError):
                raise
            raise ProtocolError(str(exc)) from exc
