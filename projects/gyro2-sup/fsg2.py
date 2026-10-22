"""FSG2 blocks on the host: find, check and decode, as the plugin does.

The layout is the plugin's (gyroflow-plugins common/src/cdng.rs for the outer
frame, common/src/fsg2.rs for payload kind 2).  Kept separate from both so the
camera's bytes are checked by a third reading, not by the code that wrote them.
"""
import struct, zlib

MAGIC = b'FSG2'
F_LOST, F_TRUNC, F_FIRST, F_LENS = 1, 2, 4, 0x40


def ifd_entries(buf, off):
    n = struct.unpack_from('<H', buf, off)[0]
    return {t: (ty, c, v) for t, ty, c, v in
            (struct.unpack_from('<HHII', buf, off + 2 + 12 * k) for k in range(n))}


def area_0x200(buf):
    """(start, end) of the MakerNote tag-0x0200 area, from the stock IFD0 at 8
    when the root points past the bytes we have (a lossless frame's head)."""
    root_at = struct.unpack_from('<I', buf, 4)[0]
    if root_at + 2 > len(buf):
        root_at = 8
    root = ifd_entries(buf, root_at)
    exif = ifd_entries(buf, root[0x8769][2])
    _, mn_len, mn_off = exif[0x927C]
    mn = ifd_entries(buf, mn_off + 10)
    _, a_len, a_off = mn[0x200]
    return a_off, a_off + a_len


def find_block(buf, start=0, end=None):
    """(offset, kind, payload) of the one valid block in buf[start:end], else raises."""
    end = len(buf) if end is None else end
    found, i = [], buf.find(MAGIC, start, end)
    while i >= 0:
        try:
            ver, kind, res, n = struct.unpack_from('<BBHI', buf, i + 4)
            body_end = i + 12 + n
            if ver == 1 and res == 0 and body_end + 4 <= end:
                crc = struct.unpack_from('<I', buf, body_end)[0]
                if zlib.crc32(buf[i:body_end]) == crc:
                    found.append((i, kind, buf[i + 12:body_end]))
        except struct.error:
            pass
        i = buf.find(MAGIC, i + 1, end)
    if len(found) != 1:
        raise ValueError(f'{len(found)} valid FSG2 blocks')
    return found[0]


KEYS = ['fmt', 'orientation', 'flags', 'clip_id', 'frame_seq', 'period_ps', 'gscale', 'ascale',
        'readout_ns', 'mode_id', 'crop_x', 'crop_y', 'crop_w', 'crop_h', 'frame_mark',
        'base_idx', 'n_samples', 'n_events']


def decode_kind2(payload):
    h = dict(zip(KEYS, struct.unpack_from('<BBHIIIffIHHHHHHIHH', payload, 0)))
    n = h['n_samples']
    h['samples'] = [struct.unpack_from('<3h', payload, 48 + 6 * k) for k in range(n)]
    at = 48 + 6 * n
    events = []
    for _ in range(h['n_events']):
        pos, kind, ln = struct.unpack_from('<HBB', payload, at)
        events.append((pos, kind, payload[at + 4:at + 4 + ln]))
        at += 4 + ln
    h['events'] = events
    h['lens'] = None
    if h['flags'] & F_LENS:
        focal = struct.unpack_from('<I', payload, at)[0]
        axis = struct.unpack_from('<5I', payload, at + 4)
        nodes = struct.unpack_from('<60d', payload, at + 24)
        h['lens'] = (focal, axis, nodes)
        at += 504
    h['rest'] = len(payload) - at
    return h


def read_frame(buf):
    """Decode the kind 2 record in one DNG's bytes (whole file or its head)."""
    start, end = area_0x200(buf)
    at, kind, payload = find_block(buf, start, end)
    if kind != 2:
        raise ValueError(f'payload kind {kind}')
    rec = decode_kind2(payload)
    rec['at'] = at
    return rec
