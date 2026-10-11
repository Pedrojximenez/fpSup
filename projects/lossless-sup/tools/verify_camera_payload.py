#!/usr/bin/env python3
"""Decode a payload the CAMERA encoded and prove it is sample-exact.

Everything measured so far shows the camera CAN encode, how long it takes and
how big the result is. Nothing shows the result is CORRECT: only host-encoded
bitstreams have ever been decoded. The probe discards the camera's output, so
its tile sizes are known and its tile bytes are not.

The check this makes possible: the camera writes the uncompressed DNG of the
same frame to the card, so a payload read back out of scratch can be compared
against that frame sample for sample.

    payload (camera scratch)  +  canonical segment 0  ->  decode  ->  compare
                                                                      with the
                                                                clip's own DNG

Two things are deliberately not assumed:

  * WHICH frame was encoded. The probe records the first and last pixel words
    of the source it read; the frame is found by matching those, not by
    picking the first file in the folder.
  * That the tiles sit end to end from the arena base. They are sliced that
    way, and a wrong layout shows up as a decode failure rather than as a
    silently wrong image, but the assumption is named in the report.

Offline: reads files, writes nothing to any camera.
"""
import argparse
import hashlib
import json
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import canonical_header as ch
from tiff_guard import require, ClassicTIFF, scalar

PIXEL_OFFSET = 0x13400
RAW_BYTES = 0x304CB0


def pixel_markers(dng_bytes):
    """The first and last pixel words, as the probe reads them."""
    require(len(dng_bytes) > PIXEL_OFFSET + RAW_BYTES, 'file too small for FHD raster')
    first = struct.unpack_from('<I', dng_bytes, PIXEL_OFFSET)[0]
    last = struct.unpack_from('<I', dng_bytes, PIXEL_OFFSET + RAW_BYTES - 4)[0]
    return first, last


def find_frame(folder, first_word, last_word):
    """The clip frame the probe encoded, identified by its pixel markers."""
    folder = pathlib.Path(folder)
    hits = []
    for path in sorted(folder.rglob('*.DNG')) + sorted(folder.rglob('*.dng')):
        if path.stat().st_size != 3244544:
            continue
        data = path.read_bytes()
        if pixel_markers(data) == (first_word, last_word):
            hits.append(path)
    require(hits, 'no frame in that folder matches the recorded pixel markers')
    require(len(hits) == 1,
            f'{len(hits)} frames share those markers; the probe cannot tell them apart')
    return hits[0]


SOI, SOF3, EOI = b'\xff\xd8', b'\xff\xc3', b'\xff\xd9'


def check_tile_framing(payload, tile_byte_counts):
    """Every declared span must be a whole lossless-JPEG stream.

    Decoding does NOT check the tile table. Each tile is SOI..EOI, and LibRaw
    resynchronises by finding SOI, so a table whose offsets are wrong by a few
    bytes still decodes every sample correctly -- measured, +/-16 bytes, on
    2026-09-23. Framing is what catches it, so the table is checked here and
    never inferred from a successful decode.
    """
    at, report = 0, []
    for index, size in enumerate(tile_byte_counts):
        span = payload[at:at + size]
        require(len(span) == size, f'tile {index} runs past the payload')
        require(span[:2] == SOI, f'tile {index} does not begin with SOI at its '
                                 f'declared offset {at}')
        require(span[2:4] == SOF3, f'tile {index} is not lossless JPEG (SOF3)')
        end = span.rfind(EOI)
        require(end >= 0, f'tile {index} contains no EOI within its declared '
                          f'length {size}')
        tail = span[end + 2:]
        require(not any(tail),
                f'tile {index} has {len(tail)} non-zero bytes after its EOI; '
                'the declared length covers something other than padding')
        # The camera rounds the LAST tile up so the payload total is 512-byte
        # aligned: measured 2026-09-23, 11 zero bytes after the final EOI.
        # Padding inside the declared span is fine; anything else is not.
        report.append({'tile': index, 'at': at, 'bytes': size,
                       'stream_bytes': end + 2, 'padding': len(tail)})
        at += size
    return report


def slice_tiles(payload, tile_byte_counts):
    require(len(payload) >= sum(tile_byte_counts),
            f'payload is {len(payload)} bytes, tiles need {sum(tile_byte_counts)}')
    blobs, at = [], 0
    for size in tile_byte_counts:
        blobs.append(payload[at:at + size])
        at += size
    return blobs, at


def assemble(stock_frame, payload, tile_byte_counts, tile_w=512, tile_h=368):
    data = pathlib.Path(stock_frame).read_bytes()
    built = ch.build(data[:ch.IFD_AT], list(tile_byte_counts), tile_w, tile_h)
    ch.verify(built['segment0'], data[:ch.IFD_AT], list(tile_byte_counts), tile_w, tile_h)
    segment0 = bytearray(built['segment0'])
    struct.pack_into('<I', segment0, 4, built['root_pointer'])
    check_tile_framing(payload, tile_byte_counts)
    blobs, used = slice_tiles(payload, tile_byte_counts)
    return bytes(segment0) + b''.join(blobs), used


def compare(stock_frame, assembled_path):
    import numpy as np
    import rawpy
    with rawpy.imread(str(stock_frame)) as raw:
        original = raw.raw_image.copy()
    with rawpy.imread(str(assembled_path)) as raw:
        decoded = raw.raw_image.copy()
    require(original.shape == decoded.shape, 'decoded raster shape differs')
    equal = bool(np.array_equal(original, decoded))
    return {'samples': int(original.size), 'shape': list(original.shape),
            'samples_equal': equal,
            'source_sample_sha256': hashlib.sha256(
                original.astype('<u2').tobytes()).hexdigest(),
            'decoded_sample_sha256': hashlib.sha256(
                decoded.astype('<u2').tobytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=pathlib.Path, required=True,
                        help='bytes read back from the codec arena')
    parser.add_argument('--tile-sizes', required=True,
                        help='comma separated, or a JSON file with a list')
    parser.add_argument('--stock-frame', type=pathlib.Path,
                        help='the clip DNG of the same frame')
    parser.add_argument('--clip-folder', type=pathlib.Path,
                        help='find the frame by the recorded pixel markers instead')
    parser.add_argument('--first-pixel-word', type=lambda v: int(v, 0))
    parser.add_argument('--last-pixel-word', type=lambda v: int(v, 0))
    parser.add_argument('--out', type=pathlib.Path, required=True)
    args = parser.parse_args()

    text = args.tile_sizes
    sizes = (json.loads(pathlib.Path(text).read_text())
             if pathlib.Path(text).is_file() else
             [int(v, 0) for v in text.split(',')])
    frame = args.stock_frame
    if frame is None:
        require(args.clip_folder and args.first_pixel_word is not None
                and args.last_pixel_word is not None,
                'give --stock-frame, or --clip-folder with both pixel words')
        frame = find_frame(args.clip_folder, args.first_pixel_word,
                           args.last_pixel_word)
    require(not args.out.exists(), 'refusing to overwrite the output')
    payload = args.payload.read_bytes()
    blob, used = assemble(frame, payload, sizes)
    args.out.write_bytes(blob)
    report = {'stock_frame': str(frame), 'tiles': len(sizes),
              'payload_bytes_used': used, 'payload_bytes_read': len(payload),
              'trailing_bytes_ignored': len(payload) - used,
              'assembled': str(args.out), 'assembled_bytes': len(blob),
              'tiles_assumed_contiguous_from_arena_base': True}
    report.update(compare(frame, args.out))
    print(json.dumps(report, indent=2))
    return 0 if report['samples_equal'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
