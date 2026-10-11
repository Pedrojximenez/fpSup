#!/usr/bin/env python3
"""The trailing-IFD compressed DNG layout, as executable contract.

The leading-IFD layout copy-back uses needs an EXPANDED header: the new IFD and
its two tile arrays need 810 bytes and the original header has only 92 bytes of
legal space, so segment 0 grows from 78,848 to 79,872 and the payload starts at
0x13800. That 0x400 shift is exactly why the codec cannot write in place - its
output would start ahead of the source it has not read yet.

A TIFF's root pointer can point anywhere, so the IFD can go AFTER the image
data instead:

    0        .. 0x13400      the original header, byte for byte, except the
                             root pointer at offset 4
    0x13400  .. ifd_at       the codec's output, starting exactly where the
                             stock pixels started
    ifd_at   .. +ifd_size    the new IFD
             .. +8*tiles     TileOffsets then TileByteCounts

Verified 2026-09-26: a file built this way from the camera's own payload decodes
to the identical 2,110,240 samples as the leading-IFD version, max difference 0.

The reason this module exists rather than a second copy of the arithmetic in the
device code: ifd_at depends on the payload size, which is not known until the
encode is done, so tags 324 and 325 carry file offsets that must be patched at
runtime. The device needs to be told WHERE in the template those two value
fields are, and getting that from the same code that writes the template is the
only way it cannot drift.

Offline only.
"""
import struct
import sys

sys.dont_write_bytecode = True
from tiff_guard import require
import canonical_header as ch

HEADER_BYTES = 0x13400          # the original header, unexpanded
PIXEL_OFF = 0x13400             # where the stock pixels start, and our payload
TILE_COUNT = 12


def build(original_header, tile_byte_counts, tile_w, tile_h,
          *, pixel_off=PIXEL_OFF):
    """The trailing IFD for these tile sizes, and everything the device needs.

    Returns the IFD block to write at `ifd_at`, the two tables, and the byte
    offsets WITHIN that block of the two value fields the device must patch.
    """
    require(len(original_header) == pixel_off,
            f"original header must be exactly {pixel_off} bytes, "
            f"got {len(original_header)}")
    require(len(tile_byte_counts) == TILE_COUNT,
            f"expected {TILE_COUNT} tiles, got {len(tile_byte_counts)}")
    require(all(n > 0 for n in tile_byte_counts), "a tile of zero bytes")

    tree = ch.ClassicTIFF(original_header)
    tags = tree.root["tags"]
    for tag in ch.LAYOUT_TAGS_REMOVED:
        require(tag in tags, f"source is missing layout tag {tag}")
    require(ch.TILE_OFFSETS not in tags and ch.TILE_COUNTS not in tags,
            "source already carries tile tags")
    require(ch.scalar(tags, ch.COMPRESSION) == 1, "source is not uncompressed")

    entries = {t: e["entry"] for t, e in tags.items()
               if t not in ch.LAYOUT_TAGS_REMOVED}
    count = len(entries) + 4
    ifd_size = 2 + count * 12 + 4
    payload = sum(tile_byte_counts)
    ifd_at = pixel_off + payload
    offset_table = ifd_at + ifd_size
    count_table = offset_table + 4 * TILE_COUNT
    file_bytes = count_table + 4 * TILE_COUNT

    def entry(tag, kind, n, value):
        return struct.pack("<HHII", tag, kind, n, value)

    entries[ch.COMPRESSION] = entry(ch.COMPRESSION, 3, 1, ch.LOSSLESS_JPEG)
    entries[ch.TILE_W] = entry(ch.TILE_W, 4, 1, tile_w)
    entries[ch.TILE_H] = entry(ch.TILE_H, 4, 1, tile_h)
    entries[ch.TILE_OFFSETS] = entry(ch.TILE_OFFSETS, 4, TILE_COUNT, offset_table)
    entries[ch.TILE_COUNTS] = entry(ch.TILE_COUNTS, 4, TILE_COUNT, count_table)

    order = sorted(entries)
    ifd = struct.pack("<H", count) + b"".join(entries[t] for t in order) + bytes(4)
    require(len(ifd) == ifd_size, "IFD size mismatch")

    # Where the device has to patch, as byte offsets into `ifd`. The value
    # field of a 12-byte entry is its last four bytes.
    patch = {}
    for tag in (ch.TILE_OFFSETS, ch.TILE_COUNTS):
        patch[tag] = 2 + order.index(tag) * 12 + 8
        packed, = struct.unpack_from("<I", ifd, patch[tag])
        require(packed == (offset_table if tag == ch.TILE_OFFSETS else count_table),
                f"patch offset for tag {tag} does not point at its value")

    offsets, position = [], pixel_off
    for size in tile_byte_counts:
        offsets.append(position)
        position += size
    require(position == ifd_at, "tiles do not reach the IFD")

    tables = (struct.pack("<" + "I" * TILE_COUNT, *offsets)
              + struct.pack("<" + "I" * TILE_COUNT, *tile_byte_counts))

    return {"ifd": ifd, "tables": tables, "ifd_at": ifd_at,
            "ifd_size": ifd_size, "entries": count,
            "offset_table": offset_table, "count_table": count_table,
            "patch_offset_table_at": patch[ch.TILE_OFFSETS],
            "patch_count_table_at": patch[ch.TILE_COUNTS],
            "root_pointer": ifd_at, "payload_bytes": payload,
            "file_bytes": file_bytes,
            "trailer_bytes": ifd_size + 8 * TILE_COUNT}


def assemble(original_header, payload, tile_byte_counts, tile_w, tile_h):
    """The whole file, for host-side checking. The device never does this: it
    writes the trailer in place and changes the root pointer."""
    built = build(original_header, tile_byte_counts, tile_w, tile_h)
    require(len(payload) == built["payload_bytes"], "payload length mismatch")
    out = bytearray(original_header)
    struct.pack_into("<I", out, 4, built["root_pointer"])
    out += payload
    out += built["ifd"]
    out += built["tables"]
    require(len(out) == built["file_bytes"], "assembled size mismatch")
    require(bytes(out[8:PIXEL_OFF]) == original_header[8:PIXEL_OFF],
            "the original header changed outside its root pointer")
    return bytes(out), built
