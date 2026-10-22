#!/usr/bin/env python3
"""Check a CinemaDNG clip recorded with the Gyro2 P0 probe.

    python3 -B verify_probe.py /Volumes/SD/DCIM/.../A001_123      (a clip folder)

For every DNG, in file order: find the probe block in the MakerNote's 0x0200
area, and check what the camera test is for --

  * every frame carries a block (the hook ran for every frame, and the DMA
    took the CPU's writes with it);
  * the tag manager's counter advances by one per file, and the request
    index by one modulo 96 (it is a slot, not a frame number), so the block belongs to the frame it sits in, even when the
    lossless sup reordered or held frames;
  * the TickTimer advances by about one frame interval;
  * the block sits at the same place in every frame of the take.

Exit status 0 when all of that holds.
"""
import pathlib, struct, sys

MAGIC = b'FSGP'
REQ_SLOTS = 96          # [request+0x10FC] wraps 95 -> 0 (measured, A001_027)


def ifd_entries(hdr, off):
    n = struct.unpack_from('<H', hdr, off)[0]
    return {t: (ty, c, v) for t, ty, c, v in
            (struct.unpack_from('<HHII', hdr, off + 2 + 12 * k) for k in range(n))}


def read_block(path):
    """(block dict or None, the 0x200 area's (start, end))."""
    data = path.read_bytes()
    if data[:4] != b'II*\0':
        return None, None
    root_at = struct.unpack_from('<I', data, 4)[0]
    # A frame the lossless sup compressed keeps the stock header byte for byte
    # and points the root at a new IFD after the payload; with only the head
    # of the file fetched, read the stock IFD0 that is still at 8.
    if root_at + 2 > len(data):
        root_at = 8
    root = ifd_entries(data, root_at)
    exif = ifd_entries(data, root[0x8769][2])
    _, mn_len, mn_off = exif[0x927C]
    mn = ifd_entries(data, mn_off + 10)
    _, a_len, a_off = mn[0x200]
    area = data[a_off:a_off + a_len]
    i = area.find(MAGIC)
    if i < 0:
        return None, (a_off, a_off + a_len)
    f = struct.unpack_from('<4s11I16s', area, i)
    keys = ['magic', 'version', 'tag_count', 'req_frame', 'tick', 'frames', 'toff', 'tlen',
            'src', 'dst', 'len', 'boot', 'pattern']
    b = dict(zip(keys, f))
    b['at'] = a_off + i
    b['fps'] = None
    return b, (a_off, a_off + a_len)


def check(paths, fps=None):
    """List of problems (empty = pass) and the per-frame rows."""
    rows, problems = [], []
    for p in paths:
        b, _ = read_block(p)
        rows.append((p.name, b))
        if b is None:
            problems.append(f'{p.name}: no probe block')
        elif b['pattern'] != bytes(range(0xA0, 0xB0)) or b['version'] != 1:
            problems.append(f'{p.name}: block present but malformed')
    good = [(n, b) for n, b in rows if b]
    for (n0, a), (n1, b) in zip(good, good[1:]):
        if b['tag_count'] != a['tag_count'] + 1:
            problems.append(f'{n1}: tag counter {a["tag_count"]} -> {b["tag_count"]}')
        if b['req_frame'] != (a['req_frame'] + 1) % REQ_SLOTS:
            problems.append(f'{n1}: request index {a["req_frame"]} -> {b["req_frame"]}')
        if b['frames'] != a['frames'] + 1:
            problems.append(f'{n1}: frames written {a["frames"]} -> {b["frames"]}')
        if b['at'] != a['at']:
            problems.append(f'{n1}: block moved {a["at"]:#x} -> {b["at"]:#x}')
        if b['boot'] != a['boot']:
            problems.append(f'{n1}: boot id changed')
        dt = (b['tick'] - a['tick']) & 0xFFFFFFFF
        # The first interval of a take is short on the camera (5.2 ms at
        # 59.94p, A001_027): the first two frames are handled back to back.
        if fps and a is not good[0][1] and not 0.5e6 / fps < dt < 1.5e6 / fps:
            problems.append(f'{n1}: {dt} us since the last frame at {fps} fps')
    if good and good[0][1]['frames'] != 1:
        problems.append(f'{good[0][0]}: the first frame is not the first the probe wrote this take')
    return problems, rows


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    folder = pathlib.Path(argv[1])
    fps = float(argv[2]) if len(argv) > 2 else None
    paths = sorted(p for p in folder.iterdir() if p.suffix.upper() == '.DNG' and not p.name.startswith('._'))
    problems, rows = check(paths, fps)
    for name, b in rows[:3] + ([('...', None)] if len(rows) > 6 else []) + rows[-3:]:
        if b:
            print(f'{name}: at {b["at"]:#x} tag {b["tag_count"]} req {b["req_frame"]} '
                  f'frames {b["frames"]} tick {b["tick"]} tail {b["toff"]:#x}+{b["tlen"]}')
        else:
            print(name)
    print(f'{len(paths)} frames, {sum(1 for _, b in rows if b)} with a block')
    for p in problems[:40]:
        print('  ' + p)
    print('PASS' if not problems else f'FAIL ({len(problems)} problems)')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
