"""Offline AF publication capture format and high-speed batch framing.

No camera, socket, shell, memory access or installer. Local sequence counts CPU
producer returns, not sensor exposures. CRCs protect transfer integrity only.
"""
import struct
import zlib

MAGIC = 0x31464841
SCHEMA = 2
HEADER_BYTES = 64
RECORD_BYTES = 128
MAX_CAPACITY = 256
CALLSITE = 0xC022C858
ORIGINAL_WORD = 0xEB00485C
PRODUCER = 0xC023E9D0
CONTINUATION = 0xC022C85C
MODEL = 0xC32044D8
# Staged bring-up, host-written, read by the hook on every invocation. Only the
# host writes it; the hook must never store to that word.
LEVEL_OFF, LEVEL_COUNT, LEVEL_RECORD = 0, 1, 3
LEVELS = (LEVEL_OFF, LEVEL_COUNT, LEVEL_RECORD)
BATCH_MAGIC = b'AFB1'
BATCH_HEADER_BYTES = 64
MAX_CAPTURE_BYTES = HEADER_BYTES + MAX_CAPACITY * RECORD_BYTES
MAX_BATCH_BYTES = BATCH_HEADER_BYTES + MAX_CAPTURE_BYTES

FIELDS = (
    'commit', 'nonce', 'sequence', 'model', 'h', 'l', 'cached_lens_position_raw',
    'phase_before', 'mode_before', 'chosen_area', 'reference_area', 'route',
    'relative_gain', 'analog_code', 'analog_ratio_raw', 'hcg', 'af_rgb_gain',
    'af_sensitivity', 'af_shutter', 'af_f_number', 'capture_busy_word',
    'movie_recording', 'shutter_sequence', 'af_area_mode', 'af_drive_mode',
    'roi_count', 'hpf_0', 'hpf_1', 'phase_after', 'mode_after',
    'af_manager_position_raw', 'commit_complement',
)
CONTEXT_FIELDS = ('model', 'mode_before', 'chosen_area', 'reference_area', 'route',
                  'relative_gain', 'analog_code', 'analog_ratio_raw', 'hcg',
                  'af_rgb_gain', 'af_sensitivity', 'af_shutter', 'af_f_number',
                  'af_area_mode', 'af_drive_mode', 'roi_count', 'hpf_0', 'hpf_1')


class CaptureError(ValueError):
    pass


def _u32(value, name, *, nonzero=False):
    if type(value) is not int or not (int(nonzero) <= value <= 0xffffffff):
        raise CaptureError(f'invalid {name}')
    return value


def initial_capture(capacity, nonce, level=LEVEL_RECORD):
    _u32(nonce, 'capture nonce', nonzero=True)
    if type(capacity) is not int or not 1 <= capacity <= MAX_CAPACITY:
        raise CaptureError('capacity must be 1..256')
    if level not in LEVELS:
        raise CaptureError('level must be 0 (off), 1 (count) or 3 (record)')
    header = [MAGIC, SCHEMA, RECORD_BYTES, capacity, nonce, 1, 0, 0,
              CALLSITE, PRODUCER, CONTINUATION, HEADER_BYTES,
              level, 0, 0, 0]
    return struct.pack('<16I', *header) + bytes(capacity * RECORD_BYTES)


def decode_capture(data, *, expected_nonce, require_full=False):
    """Decode the committed prefix of a capture; `require_full` demands all of it.

    A committed prefix is exported in ONE bulk read, so nothing has to poll the
    header waiting for the buffer to fill. Decoding it does NOT prove the hook is
    detached or that its code/storage can be reclaimed, and a non-zero `overlaps`
    means the producer was re-entered: the sequence and rate are then void.
    """
    _u32(expected_nonce, 'expected nonce', nonzero=True)
    if not HEADER_BYTES <= len(data) <= MAX_CAPTURE_BYTES:
        raise CaptureError('invalid capture length')
    h = struct.unpack_from('<16I', data)
    magic, schema, record_bytes, capacity, nonce, enabled, count, full = h[:8]
    level, hits, in_body, overlaps = h[12:]
    if (magic, schema, record_bytes) != (MAGIC, SCHEMA, RECORD_BYTES):
        raise CaptureError('unsupported capture format')
    if not 1 <= capacity <= MAX_CAPACITY or len(data) != HEADER_BYTES + capacity * RECORD_BYTES:
        raise CaptureError('capture size/capacity mismatch')
    if nonce != expected_nonce:
        raise CaptureError('capture nonce mismatch')
    if h[8:12] != (CALLSITE, PRODUCER, CONTINUATION, HEADER_BYTES):
        raise CaptureError('source identity mismatch')
    if level not in LEVELS:
        raise CaptureError('unsupported staged level')
    if count > capacity:
        raise CaptureError('committed prefix exceeds capacity')
    if full:
        if full != 1 or enabled != 0 or count != capacity:
            raise CaptureError('inconsistent full marker')
    elif enabled != 1 and count != capacity:
        # enabled is cleared a few instructions before the full marker is set;
        # a read landing in that window is legitimate, not a corrupt header.
        raise CaptureError('not full and not enabled: inconsistent header')
    if level != LEVEL_RECORD and count:
        raise CaptureError('records committed below the record level')
    if hits < count:
        raise CaptureError('fewer producer returns than committed records')
    if require_full and not full:
        raise CaptureError('finite capture has not completed')
    records = []
    for i in range(count):
        words = struct.unpack_from('<32I', data, HEADER_BYTES + i * RECORD_BYTES)
        r = dict(zip(FIELDS, words))
        if (r['commit'] != i + 1 or r['sequence'] != i + 1 or
                r['commit_complement'] != ((i + 1) ^ 0xffffffff) or r['nonce'] != nonce):
            raise CaptureError(f'uncommitted, stale or out-of-order record {i}')
        reasons = []
        if r['model'] != MODEL:
            reasons.append('unsupported_model')
        if r['mode_before'] not in (1, 3) or r['mode_after'] != r['mode_before']:
            reasons.append('unsupported_or_changed_scheduler_mode')
        if r['phase_before'] > 2 or r['phase_after'] > 2:
            reasons.append('unsupported_scheduler_phase')
        if r['phase_before'] != r['phase_after']:
            reasons.append('visible_scheduler_boundary')
        if r['chosen_area'] or r['reference_area'] or r['route'] != 14:
            reasons.append('unsupported_area_or_route')
        if r['capture_busy_word'] or r['movie_recording'] or r['shutter_sequence']:
            reasons.append('capture_busy')
        if r['af_area_mode'] or r['af_drive_mode'] or not 1 <= r['roi_count'] <= 51:
            reasons.append('unsupported_focus_context')
        if (not r['relative_gain'] or r['analog_code'] > 0xfff or
                not r['analog_ratio_raw'] or r['hcg'] not in (0, 1) or
                not all(r[f] for f in ('af_rgb_gain', 'af_sensitivity', 'af_shutter', 'af_f_number'))):
            reasons.append('invalid_gain_or_exposure_context')
        r['context_issues'] = reasons
        records.append(r)
    changed = []
    if records:
        first = records[0]
        changed = [f for f in CONTEXT_FIELDS if any(r[f] != first[f] for r in records[1:])]
    return dict(schema=SCHEMA, nonce=nonce, count=count, records=records,
                capacity=capacity, full=bool(full), level=level, hits=hits,
                # in_body is the producer's own "a body is running" mark. Zero
                # after the site is restored is a hint, never a quiescence proof.
                in_body=in_body, overlaps=overlaps,
                serialization_verified=overlaps == 0 and in_body == 0,
                missed_by_level=hits - count,
                source='background_producer_return', producer_mode=0,
                statistic_area=0, position_kind='native_L_cached_drive_end',
                native_l_identity_verified=False,
                changed_context_fields=changed,
                source_rate_hz=None, sensor_frame_identity_verified=False,
                optical_alignment_verified=False, usable_for_af_control=False,
                usable_for_dfd=False, detach_verified=False)


def pack_batch(capture, *, expected_nonce):
    """Reference encoder for a future task-context EP83 sender, not the hook.

    Little-endian 64-byte header: magic, version, header bytes, nonce, count,
    record bytes, capture bytes, CRC32(capture), terminal flag=1, header CRC32,
    six zero words. Header CRC treats its word at offset 36 as zero.
    """
    capture = bytes(capture)
    decoded = decode_capture(capture, expected_nonce=expected_nonce, require_full=True)
    header = bytearray(struct.pack('<4s15I', BATCH_MAGIC, 1, BATCH_HEADER_BYTES,
                                   expected_nonce, decoded['count'], RECORD_BYTES,
                                   len(capture), zlib.crc32(capture), 1, 0,
                                   0, 0, 0, 0, 0, 0))
    struct.pack_into('<I', header, 36, zlib.crc32(header))
    return bytes(header) + bytes(capture)


class BatchReceiver:
    """Incremental bounded decoder for ONE finite EP83 batch, arbitrary chunks.

    The future USB reader must impose its own absolute deadline and stop on
    disconnect/timeout. feed() does no polling and cannot change the camera.
    Any framing error latches fault; no magic scanning, resync or retry.
    """
    def __init__(self, *, expected_nonce):
        self.nonce = _u32(expected_nonce, 'expected nonce', nonzero=True)
        self.buffer = bytearray()
        self.expected = None
        self.header = None
        self.faulted = False
        self.done = False

    def invalidate(self):
        self.faulted = True

    def feed(self, chunk):
        try:
            if self.done or self.faulted:
                raise CaptureError('receiver is closed')
            if not isinstance(chunk, (bytes, bytearray, memoryview)):
                raise CaptureError('empty or invalid transport chunk')
            chunk_size = chunk.nbytes if isinstance(chunk, memoryview) else len(chunk)
            if not chunk_size:
                raise CaptureError('empty or invalid transport chunk')
            if len(self.buffer) + chunk_size > MAX_BATCH_BYTES:
                raise CaptureError('batch exceeds bounded allocation')
            self.buffer.extend(bytes(chunk))
            if self.expected is None and len(self.buffer) >= BATCH_HEADER_BYTES:
                header = bytearray(self.buffer[:BATCH_HEADER_BYTES])
                h = struct.unpack('<4s15I', header)
                struct.pack_into('<I', header, 36, 0)
                if h[0:4] != (BATCH_MAGIC, 1, BATCH_HEADER_BYTES, self.nonce):
                    raise CaptureError('batch identity mismatch')
                if not 1 <= h[4] <= MAX_CAPACITY or h[5] != RECORD_BYTES:
                    raise CaptureError('batch record count/size invalid')
                if h[6] != HEADER_BYTES + h[4] * RECORD_BYTES:
                    raise CaptureError('batch body length invalid')
                if h[8] != 1 or any(h[10:]) or zlib.crc32(header) != h[9]:
                    raise CaptureError('batch flags/reserved/header CRC invalid')
                self.header = h
                self.expected = BATCH_HEADER_BYTES + h[6]
            if self.expected is None or len(self.buffer) < self.expected:
                return None
            if len(self.buffer) != self.expected:
                raise CaptureError('extra bytes after finite batch')
            capture = self.buffer[BATCH_HEADER_BYTES:]
            if zlib.crc32(capture) != self.header[7]:
                raise CaptureError('batch body checksum mismatch')
            result = decode_capture(capture, expected_nonce=self.nonce)
            if result['count'] != self.header[4]:
                raise CaptureError('batch/capture count mismatch')
            self.done = True
            return result
        except (ValueError, TypeError, struct.error) as exc:
            self.faulted = True
            if isinstance(exc, CaptureError):
                raise
            raise CaptureError(str(exc)) from exc

    def finish(self):
        if not self.done or self.faulted:
            self.faulted = True
            raise CaptureError('incomplete or failed finite batch')
