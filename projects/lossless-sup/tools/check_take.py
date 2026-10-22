#!/usr/bin/env python3
"""Check one lossless take: the shell's `dir` of the clip folder, and frames.

    python3 check_take.py DIR_LISTING.txt [FRAME.DNG ...] [--stock FIRST.DNG]

From the listing: DNG count, numbering gaps, sizes (stock-sized vs smaller).
For each frame given: the trailing-IFD layout the card writes now
(trailing_ifd.py) -- root IFD anywhere, Compression 7 or 1, every tile
offset+count inside the file and each compressed tile SOI..EOI -- then a
rawpy decode, compared with the stock frame when --stock is given (same
size, mean |difference| of the raw values; consecutive frames of a still scene
differ only by noise).

Offline only: reads files, writes nothing.
"""
import argparse
import json
import re
import struct
import sys
from collections import Counter

NAME = re.compile(r'_(\d{6})\.DNG$')


def listing(path):
    rows = {}
    for line in open(path, encoding='utf-8', errors='replace'):
        parts = line.split()
        if len(parts) >= 4 and NAME.search(parts[-1]) and parts[-2].isdigit():
            rows[int(NAME.search(parts[-1]).group(1))] = int(parts[-2])
    if not rows:
        return {'dng': 0}
    last = max(rows)
    gaps = sorted(set(range(1, last + 1)) - set(rows))
    first = rows.get(1)
    return {'dng': len(rows), 'first': min(rows), 'last': last, 'gaps': gaps,
            'first_bytes': first,
            'smaller_than_first': sum(1 for n, s in rows.items() if first and s < first * 0.9),
            'first_size_count': sum(1 for s in rows.values() if s == first),
            'sizes': Counter(rows.values()).most_common(5)}


def ifd(data):
    order = data[:2]
    if order != b'II':
        raise ValueError('not little-endian TIFF')
    at, = struct.unpack_from('<I', data, 4)
    n, = struct.unpack_from('<H', data, at)
    tags = {}
    for i in range(n):
        tag, kind, count, value = struct.unpack_from('<HHII', data, at + 2 + 12 * i)
        size = {3: 2, 4: 4}.get(kind, 1) * count
        if size <= 4:
            raw = struct.pack('<I', value)[:size]
        else:
            raw = data[value:value + size]
        fmt = {3: 'H', 4: 'I'}.get(kind)
        tags[tag] = list(struct.unpack(f'<{count}{fmt}', raw)) if fmt else raw
    return at, tags


def frame(path, stock_raw=None):
    data = open(path, 'rb').read()
    at, tags = ifd(data)
    comp = tags.get(259, [None])[0]
    out = {'file': path.rsplit('/', 1)[-1], 'bytes': len(data), 'ifd_at': at,
           'compression': comp}
    if 324 in tags:
        offs, counts = tags[324], tags[325]
        out['tiles'] = len(offs)
        bad = [i for i, (o, c) in enumerate(zip(offs, counts)) if o + c > len(data)]
        if bad:
            raise ValueError(f'tiles past the end: {bad[:5]}')
        if comp == 7:
            soi = sum(data[o:o + 2] == b'\xff\xd8' for o in offs)
            # the last tile's count runs to the 1 KiB-aligned IFD: EOI, then zeros
            eoi, pad = 0, 0
            for o, c in zip(offs, counts):
                seg = data[o:o + c]
                e = seg.rfind(b'\xff\xd9') + 2
                if e >= 2 and not any(seg[e:]):
                    eoi += 1
                    pad += c - e
            out['soi_ok'], out['eoi_ok'], out['zero_pad'] = soi, eoi, pad
            if soi != len(offs) or eoi != len(offs):
                raise ValueError(f'tile markers: SOI {soi}/{len(offs)}, EOI {eoi}/{len(offs)}')
    import numpy as np
    import rawpy
    with rawpy.imread(path) as r:
        raw = r.raw_image.astype(np.int32).copy()
    out['decoded'] = list(raw.shape)
    out['raw_mean'] = round(float(raw.mean()), 2)
    if stock_raw is not None:
        if stock_raw.shape != raw.shape:
            raise ValueError(f'shape {raw.shape} != stock {stock_raw.shape}')
        out['mean_abs_diff_vs_stock'] = round(float(np.abs(raw - stock_raw).mean()), 3)
    return out, raw


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('listing')
    ap.add_argument('frames', nargs='*')
    ap.add_argument('--stock')
    a = ap.parse_args()
    report = {'listing': listing(a.listing), 'frames': []}
    stock_raw = None
    if a.stock:
        info, stock_raw = frame(a.stock)
        report['stock'] = info
    ok = True
    for f in a.frames:
        try:
            info, _ = frame(f, stock_raw)
        except Exception as e:                       # one bad frame must not hide the rest
            info, ok = {'file': f, 'error': str(e)}, False
        report['frames'].append(info)
    report['ok'] = ok and not report['listing'].get('gaps')
    print(json.dumps(report, indent=1))
    sys.exit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
