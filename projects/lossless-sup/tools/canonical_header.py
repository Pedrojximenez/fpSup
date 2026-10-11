#!/usr/bin/env python3
"""The compressed-DNG segment 0 the camera writer has to emit, as code.

ROADMAP section 4.4 fixes the layout, and the reason it is an OWNED EXPANDED
header rather than an in-place edit is a correction worth keeping visible: the
old approach put the new IFD in a zero run, and the MakerNote's declared range
covers that run. Once every root and nested IFD and every out-of-line value is
protected, the original header has 92 bytes of legal space and the new IFD plus
two tile arrays need 810.

    segment 0: 79,872 bytes
      0 .. 78,847      the original header, byte for byte, except the root
                       pointer at offset 4, which is committed LAST
      78,848 ..        new IFD, TileOffsets, TileByteCounts
      .. 79,871        zero padding
    segment 1: the codec's output, at its exact length, never padded

This module builds and checks that, from tile BYTE COUNTS alone. It does not
encode anything: the camera has the blobs, the host trial has its own encoder,
and both must produce the same header for the same sizes. Keeping the header
separate from the encoder is what makes that comparable.

The root pointer is returned beside the bytes instead of being written into
them, because "write the IFD and tables, make them visible, and only then
commit the pointer" is an ordering rule. A caller that cannot get the order
wrong is better than a comment saying not to.
"""
import struct

from tiff_guard import require, ClassicTIFF, scalar

HEADER_BYTES = 79872
IFD_AT = 78848
LAYOUT_TAGS_REMOVED = (273, 278, 279)      # StripOffsets, RowsPerStrip, StripByteCounts
COMPRESSION, TILE_W, TILE_H, TILE_OFFSETS, TILE_COUNTS = 259, 322, 323, 324, 325
LOSSLESS_JPEG = 7


def build(original_header, tile_byte_counts, tile_w, tile_h,
          header_bytes=HEADER_BYTES, ifd_at=IFD_AT):
    """Return {segment0, root_pointer, tile_offsets, payload_bytes}.

    `original_header` is the stock header up to its raster, i.e. the first
    `ifd_at` bytes of a stock FHD DNG. segment0 still carries the ORIGINAL
    root pointer; `root_pointer` is what to commit once segment0 is visible.
    """
    require(len(original_header) == ifd_at,
            f'original header must be exactly {ifd_at} bytes, got {len(original_header)}')
    require(tile_byte_counts and all(isinstance(n, int) and 0 < n < 1 << 31
                                     for n in tile_byte_counts),
            'tile byte counts must be positive 32-bit integers')
    tree = ClassicTIFF(original_header + bytes(4))
    tags = tree.root['tags']
    require(not ({TILE_W, TILE_H, TILE_OFFSETS, TILE_COUNTS} & tags.keys()),
            'source already carries tile tags')
    require(scalar(tags, COMPRESSION) == 1, 'source is not uncompressed')

    tile_count = len(tile_byte_counts)
    entries = {tag: entry['entry'] for tag, entry in tags.items()
               if tag not in LAYOUT_TAGS_REMOVED}
    for tag in LAYOUT_TAGS_REMOVED:
        require(tag not in entries, f'layout tag {tag} survived removal')
    count = len(entries) + 4
    ifd_size = 2 + count * 12 + 4
    offset_table = ifd_at + ifd_size
    count_table = offset_table + 4 * tile_count
    tables_end = count_table + 4 * tile_count
    require(tables_end <= header_bytes,
            f'IFD and tile tables need {tables_end - ifd_at} bytes, '
            f'{header_bytes - ifd_at} available')

    offsets, position = [], header_bytes
    for size in tile_byte_counts:
        offsets.append(position)
        position += size
        require(position < 1 << 31, 'tile offsets overflow 32 bits')

    def entry(tag, kind, n, value):
        return struct.pack('<HHII', tag, kind, n, value)

    entries[COMPRESSION] = entry(COMPRESSION, 3, 1, LOSSLESS_JPEG)
    entries[TILE_W] = entry(TILE_W, 4, 1, tile_w)
    entries[TILE_H] = entry(TILE_H, 4, 1, tile_h)
    entries[TILE_OFFSETS] = entry(TILE_OFFSETS, 4, tile_count, offset_table)
    entries[TILE_COUNTS] = entry(TILE_COUNTS, 4, tile_count, count_table)
    require(len(entries) == count, 'entry count changed while building')

    segment0 = bytearray(original_header)
    segment0.extend(bytes(header_bytes - ifd_at))
    ifd = struct.pack('<H', count) + b''.join(entries[t] for t in sorted(entries)) + bytes(4)
    require(len(ifd) == ifd_size, 'IFD size mismatch')
    segment0[ifd_at:ifd_at + ifd_size] = ifd
    struct.pack_into(f'<{tile_count}I', segment0, offset_table, *offsets)
    struct.pack_into(f'<{tile_count}I', segment0, count_table, *tile_byte_counts)

    require(bytes(segment0[:4]) == original_header[:4], 'byte order mark changed')
    require(bytes(segment0[8:ifd_at]) == original_header[8:ifd_at],
            'original header changed below the new IFD')
    require(bytes(segment0[4:8]) == original_header[4:8],
            'root pointer must still be the original until it is committed')
    require(len(segment0) == header_bytes, 'segment 0 is not the fixed size')
    return {'segment0': bytes(segment0), 'root_pointer': ifd_at,
            'tile_offsets': offsets, 'payload_bytes': position - header_bytes,
            'ifd_size': ifd_size, 'tables_end': tables_end,
            'entries': count, 'tile_count': tile_count}


def verify(segment0, original_header, tile_byte_counts, tile_w, tile_h,
           root_committed=False, ifd_at=IFD_AT):
    """Check a built segment 0 against every rule in section 4.4."""
    require(len(segment0) == HEADER_BYTES, 'wrong segment 0 size')
    require(segment0[8:ifd_at] == original_header[8:ifd_at],
            'original header bytes changed')
    expected_pointer = ifd_at if root_committed else struct.unpack_from(
        '<I', original_header, 4)[0]
    require(struct.unpack_from('<I', segment0, 4)[0] == expected_pointer,
            'root pointer is not in the expected state')

    tree = ClassicTIFF(segment0[:4] + struct.pack('<I', ifd_at) + segment0[8:])
    tags = tree.root['tags']
    for tag in LAYOUT_TAGS_REMOVED:
        require(tag not in tags, f'strip tag {tag} is still present')
    require(scalar(tags, COMPRESSION) == LOSSLESS_JPEG, 'Compression is not 7')
    require(scalar(tags, TILE_W) == tile_w and scalar(tags, TILE_H) == tile_h,
            'tile dimensions do not match')
    require(tags[TILE_OFFSETS]['count'] == len(tile_byte_counts) and
            tags[TILE_COUNTS]['count'] == len(tile_byte_counts),
            'tile array lengths do not match the tile count')

    offset_table = tags[TILE_OFFSETS]['entry'][8:12]
    count_table = tags[TILE_COUNTS]['entry'][8:12]
    at_offsets = struct.unpack('<I', offset_table)[0]
    at_counts = struct.unpack('<I', count_table)[0]
    n = len(tile_byte_counts)
    offsets = struct.unpack_from(f'<{n}I', segment0, at_offsets)
    counts = struct.unpack_from(f'<{n}I', segment0, at_counts)
    require(list(counts) == list(tile_byte_counts), 'tile byte counts differ')
    require(all(o >= HEADER_BYTES for o in offsets),
            'a tile starts inside the header')
    spans = sorted(zip(offsets, counts))
    for (a_at, a_len), (b_at, _) in zip(spans, spans[1:]):
        require(a_at + a_len <= b_at, 'tiles overlap')
    require(all(a + b < 1 << 31 for a, b in spans), 'tile span overflows')
    require(not any(segment0[max(tables_end_of(tags, n, at_counts), 0):]),
            'padding after the tile tables is not zero')
    return {'tiles': n, 'payload_bytes': spans[-1][0] + spans[-1][1] - HEADER_BYTES}


def tables_end_of(tags, n, at_counts):
    return at_counts + 4 * n
