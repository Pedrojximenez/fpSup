"""FSG2 blocks on the host: find, check and decode, as the plugin does.

The layout is the plugin's (gyroflow-plugins common/src/cdng.rs for the outer
frame, common/src/fsg2.rs for payload kind 2).  Kept separate from both so the
camera's bytes are checked by a third reading, not by the code that wrote them.

Two carriers:
  block version 2 (since 2026-10-15): at the first word boundary of Gyro2's own
      MakerNote tag GTAG, no CRC; bytes 6..8 = the writing sup's build.
  block version 1 (before): anywhere in the MakerNote tag-0x0200 zero tail,
      followed by a CRC-32.
"""
import struct, zlib

MAGIC = b'FSG2'
GTAG = 0x4653
F_LOST, F_TRUNC, F_FIRST, F_LENS = 1, 2, 4, 0x40


def ifd_entries(buf, off):
    n = struct.unpack_from('<H', buf, off)[0]
    return {t: (ty, c, v) for t, ty, c, v in
            (struct.unpack_from('<HHII', buf, off + 2 + 12 * k) for k in range(n))}


def maker_note(buf):
    """(MakerNote offset, its IFD entries), from the stock IFD0 at 8 when the
    root points past the bytes we have (a lossless frame's head)."""
    root_at = struct.unpack_from('<I', buf, 4)[0]
    if root_at + 2 > len(buf):
        root_at = 8
    root = ifd_entries(buf, root_at)
    exif = ifd_entries(buf, root[0x8769][2])
    _, mn_len, mn_off = exif[0x927C]
    return mn_off, ifd_entries(buf, mn_off + 10)


def area_0x200(buf):
    """(start, end) of the MakerNote tag-0x0200 area."""
    _, mn = maker_note(buf)
    _, a_len, a_off = mn[0x200]
    return a_off, a_off + a_len


def gtag_area(buf):
    """(block start, value end) of our tag, or None."""
    _, mn = maker_note(buf)
    if GTAG not in mn:
        return None
    ty, n, off = mn[GTAG]
    if ty != 7 or n <= 4:
        raise ValueError(f'GTAG has type {ty}, count {n}')
    return (off + 3) & ~3, off + n


def find_block(buf, start=0, end=None):
    """(offset, kind, payload) of the one valid version 1 block in buf[start:end], else raises."""
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


def tag_block(buf, at, end):
    """(kind, writer build, payload) of the version 2 block at `at`, else raises."""
    if buf[at:at + 4] != MAGIC:
        raise ValueError('no block in GTAG')
    ver, kind, writer, n = struct.unpack_from('<BBHI', buf, at + 4)
    if ver != 2 or n == 0 or at + 12 + n > end:
        raise ValueError(f'bad block in GTAG: version {ver}, length {n}')
    return kind, writer, buf[at + 12:at + 12 + n]


KEYS1 = ['fmt', 'orientation', 'flags', 'clip_id', 'frame_seq', 'period_ps', 'gscale', 'ascale',
         'readout_ns', 'mode_id', 'crop_x', 'crop_y', 'crop_w', 'crop_h', 'frame_mark',
         'base_idx', 'n_samples', 'n_events']
KEYS2 = ['fmt', 'orientation', 'flags', 'clip_id', 'frame_seq', 'period_ps', 'gscale', 'ascale',
         'mode_id', 'hmax', 'read_w', 'lines', 'bin_h', 'bin_v', 'calib_focal', 'frame_mark',
         'base_idx', 'n_samples', 'n_events']


def decode_kind2(payload):
    if payload[0] == 1:
        h = dict(zip(KEYS1, struct.unpack_from('<BBHIIIffIHHHHHHIHH', payload, 0)))
    else:
        h = dict(zip(KEYS2, struct.unpack_from('<BBHIIIffHHHHHHHHIHH', payload, 0)))
        # what version 1 stored, worked out as the plugin does
        w = min(h['read_w'] * max(h['bin_h'], 1), 6000)
        ht = min(h['lines'] * max(h['bin_v'], 1), 4000)
        if h['mode_id']:
            h['readout_ns'] = round(h['hmax'] * h['lines'] * 1e9 / 72e6)
            h['crop_x'], h['crop_y'], h['crop_w'], h['crop_h'] = (6000 - w) // 2, (4000 - ht) // 2, w, ht
        else:
            h['readout_ns'] = h['crop_x'] = h['crop_y'] = h['crop_w'] = h['crop_h'] = 0
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
    if h['fmt'] == 1 and h['flags'] & F_LENS:
        focal = struct.unpack_from('<I', payload, at)[0]
        axis = struct.unpack_from('<5I', payload, at + 4)
        nodes = struct.unpack_from('<60d', payload, at + 24)
        h['lens'] = (focal, axis, nodes)
        at += 504
    h['rest'] = len(payload) - at
    return h


def read_frame(buf):
    """Decode the kind 2 record in one DNG's bytes (whole file or its head)."""
    area = gtag_area(buf)
    if area is not None:
        at, end = area
        kind, writer, payload = tag_block(buf, at, end)
    else:
        start, end = area_0x200(buf)
        at, kind, payload = find_block(buf, start, end)
        writer = None
    if kind != 2:
        raise ValueError(f'payload kind {kind}')
    rec = decode_kind2(payload)
    rec['at'] = at
    rec['writer'] = writer
    return rec
