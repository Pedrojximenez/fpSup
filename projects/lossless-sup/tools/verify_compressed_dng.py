#!/usr/bin/env python3
"""Check a compressed CinemaDNG frame the CAMERA wrote, as a whole file.

verify_camera_payload.py checks a payload fragment read out of scratch. This
checks the other thing: a complete .DNG the camera itself put on the card.

It exists because G4b's verification was done by hand, once. Copy-back will
produce these frames routinely and the checks have to be the same every time,
including the ones that are specific to copy-back:

  * the file length must be exactly header_bytes + sum(tile byte counts).
    That is the number we write into seg[1], and a mismatch means the length
    and the content disagree - which is precisely how G5 failed while every
    frame still decoded.
  * bytes 8..ifd_at must be byte-identical to a stock frame's header. The
    owned header is an EXPANDED copy of the original, so every original tag,
    every nested IFD and the MakerNote must survive untouched. Only the root
    pointer at offset 4 changes.

Structural failures raise. Nothing here decodes by itself: decoding needs
LibRaw and is offered separately, so a machine without it still gets every
structural check.

Offline only: reads files, writes nothing, touches no camera.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True

SOI_SOF3 = bytes((0xFF, 0xD8, 0xFF, 0xC3))
EOI = bytes((0xFF, 0xD9))
COMPRESSION, TILE_W_TAG, TILE_H_TAG = 259, 322, 323
TILE_OFFSETS, TILE_COUNTS = 324, 325
STRIP_TAGS = (273, 278, 279)
LOSSLESS_JPEG = 7


class Rejected(Exception):
    """A frame that fails a check. Never downgraded to a warning."""


def require(condition, message):
    if not condition:
        raise Rejected(message)


def read_ifd(data, at):
    """The root IFD only. Values that do not fit inline are read out of line."""
    require(at + 2 <= len(data), f"IFD at 0x{at:X} is past the end of the file")
    count, = struct.unpack_from("<H", data, at)
    require(0 < count < 1000, f"implausible IFD entry count {count}")
    end = at + 2 + count * 12 + 4
    require(end <= len(data), "IFD runs past the end of the file")
    tags = {}
    for i in range(count):
        tag, kind, n, value = struct.unpack_from("<HHII", data, at + 2 + i * 12)
        tags[tag] = (kind, n, value)
    return tags, end


def read_long_array(data, kind, n, value):
    """A LONG array, inline when it is a single value and out of line when not."""
    require(kind == 4, f"expected LONG, got type {kind}")
    if n == 1:
        return [value]
    require(value + 4 * n <= len(data), "array runs past the end of the file")
    return list(struct.unpack_from("<" + "I" * n, data, value))


def differing(a, b, lo, hi):
    return [i for i in range(lo, hi) if a[i] != b[i]]


def check(path, stock=None, control=None, *, header_bytes=79872, ifd_at=78848,
          tile_w=512, tile_h=368, tile_count=12):
    data = Path(path).read_bytes()
    out = {"path": str(path), "file_bytes": len(data),
           "sha256": hashlib.sha256(data).hexdigest()}

    require(data[:2] == b"II" and data[2:4] == b"\x2a\x00",
            "not a little-endian TIFF")
    root, = struct.unpack_from("<I", data, 4)
    require(root == ifd_at,
            f"root pointer is 0x{root:X}, expected 0x{ifd_at:X}")
    out["root_ifd_at"] = root

    tags, ifd_end = read_ifd(data, root)
    # Which layout is this? A LEADING IFD sits inside an expanded segment 0 and
    # the payload follows it; a TRAILING IFD sits after the payload, so the
    # payload starts at header_bytes and the file ends with the IFD and its two
    # tables. The root pointer says which, and that is better than a flag the
    # caller could get wrong.
    trailing = root >= header_bytes
    out["layout"] = "trailing-ifd" if trailing else "leading-ifd"
    out["ifd_entries"] = len(tags)
    for tag in STRIP_TAGS:
        require(tag not in tags, f"strip tag {tag} survived in a tiled frame")
    require(COMPRESSION in tags, "no Compression tag")
    require(tags[COMPRESSION][2] == LOSSLESS_JPEG,
            f"Compression is {tags[COMPRESSION][2]}, expected {LOSSLESS_JPEG}")
    for tag, want, name in ((TILE_W_TAG, tile_w, "TileWidth"),
                            (TILE_H_TAG, tile_h, "TileLength")):
        require(tag in tags, f"no {name} tag")
        require(tags[tag][2] == want,
                f"{name} is {tags[tag][2]}, expected {want}")

    offsets = read_long_array(data, *tags[TILE_OFFSETS])
    counts = read_long_array(data, *tags[TILE_COUNTS])
    require(len(offsets) == len(counts) == tile_count,
            f"{len(offsets)} offsets and {len(counts)} counts, expected {tile_count}")
    out["tile_offsets"], out["tile_byte_counts"] = offsets, counts

    # THE length rule. This is the number written into seg[1].
    payload = sum(counts)
    out["payload_bytes"] = payload
    if trailing:
        # header, payload, then the IFD and both tables. The trailer is what
        # buys the layout its whole advantage, so its size is reported.
        trailer = (ifd_end - root) + 8 * tile_count
        expected = header_bytes + payload + trailer
        out["trailer_bytes"] = trailer
        require(root == header_bytes + payload,
                f"the IFD is at 0x{root:X}; header {header_bytes} plus payload "
                f"{payload} ends at 0x{header_bytes + payload:X}")
    else:
        expected = header_bytes + payload
    out["expected_file_bytes"] = expected
    require(len(data) == expected,
            f"file is {len(data)} bytes; expected {expected}. "
            "Length and content disagree.")

    # Tiles: contiguous from header_bytes, each framed, nothing between them.
    position, tile_padding = header_bytes, []
    for i, (offset, size) in enumerate(zip(offsets, counts)):
        require(offset == position,
                f"tile {i} is declared at 0x{offset:X}, follows at 0x{position:X}")
        require(size > 4, f"tile {i} is {size} bytes")
        blob = data[offset:offset + size]
        require(blob[:4] == SOI_SOF3,
                f"tile {i} does not start with SOI+SOF3: {blob[:4].hex()}")
        # A legal EOI, and only zero padding after it. The codec's reported
        # size for a tile can exceed its bitstream - measured on the camera
        # 2026-09-26, where tile 11 carried 457 zero bytes past its EOI - and
        # the project's rule has always been to keep that padding rather than
        # trim the reported length. Requiring the tile to END with EOI rejected
        # a frame that is correct, which is worse than not checking.
        end = blob.rfind(EOI)
        require(end >= 2, f"tile {i} has no EOI marker")
        padding = blob[end + 2:]
        require(padding == bytes(len(padding)),
                f"tile {i} has {len(padding)} non-zero bytes after its EOI")
        tile_padding.append(len(padding))
        position += size
    end_of_tiles = root if trailing else len(data)
    require(position == end_of_tiles,
            "tiles do not reach "
            + ("the IFD" if trailing else "the end of the file"))
    out["tile_padding"] = tile_padding
    out["padding_bytes"] = sum(tile_padding)

    if stock is not None:
        original = Path(stock).read_bytes()
        # The region of the ORIGINAL header that must survive. With a leading
        # IFD that is everything up to where the new IFD was inserted; with a
        # trailing IFD the header is not expanded at all, so it is the whole of
        # it. min() is right for both and needs no flag.
        original_span = min(ifd_at, header_bytes)
        require(len(original) >= original_span,
                "stock frame is shorter than the header")
        require(data[:4] == original[:4], "byte order mark changed")
        out["stock"] = str(stock)
        out["original_header_bytes_compared"] = original_span - 8
        changed = differing(data, original, 8, original_span)
        out["header_bytes_differing"] = len(changed)
        out["header_positions_differing"] = [f"0x{i:05X}" for i in changed]
        if control is None:
            # Only valid when `stock` is THIS frame's own original header.
            require(not changed,
                    "the original header changed below the new IFD; only the "
                    "root pointer at offset 4 may differ. If the stock frame is "
                    "a NEIGHBOUR rather than this frame's own original, pass a "
                    "second stock frame as the control instead of loosening this.")
            out["original_header_preserved"] = True
        else:
            # The honest comparison when the frame's own original is gone,
            # which is always the case after copy-back: the bytes that differ
            # must be bytes that differ between two STOCK frames anyway.
            # Measured 2026-09-26: seven such positions, carrying per-frame
            # counters that step by one from frame to frame. This is not a
            # tolerance - it is a control, and it names every position.
            other = Path(control).read_bytes()
            require(len(other) >= original_span,
                    "control frame is shorter than the header")
            per_frame = set(differing(original, other, 8, original_span))
            out["control"] = str(control)
            out["control_positions_differing"] = sorted(f"0x{i:05X}" for i in per_frame)
            unexplained = [i for i in changed if i not in per_frame]
            require(not unexplained,
                    "header bytes changed that two stock frames do NOT differ "
                    f"at: {[f'0x{i:05X}' for i in unexplained]}")
            out["header_changes_all_per_frame"] = True

    out["ok"] = True
    return out


def decode(path):
    """Optional: decode with LibRaw. Absent LibRaw this reports why, and the
    structural checks above stand on their own."""
    try:
        import rawpy
    except ImportError as exc:
        return {"decoded": False, "reason": f"rawpy unavailable: {exc}"}
    with rawpy.imread(str(path)) as raw:
        image = raw.raw_image_visible
        return {"decoded": True, "shape": list(image.shape),
                "samples": int(image.size),
                "mean": round(float(image.mean()), 2),
                "std": round(float(image.std()), 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frame", type=Path, help="the compressed .DNG to check")
    parser.add_argument("--stock", type=Path,
                        help="a stock frame whose header must survive byte for byte")
    parser.add_argument("--control", type=Path,
                        help="a SECOND stock frame. With it, differing header "
                             "bytes must be ones two stock frames differ at "
                             "anyway; without it, none may differ at all")
    parser.add_argument("--header-bytes", type=int, default=79872)
    parser.add_argument("--ifd-at", type=int, default=78848)
    parser.add_argument("--tile", default="512x368")
    parser.add_argument("--tiles", type=int, default=12)
    parser.add_argument("--decode", action="store_true")
    args = parser.parse_args()
    tw, th = (int(part) for part in args.tile.lower().split("x"))
    try:
        result = check(args.frame, args.stock, args.control,
                       header_bytes=args.header_bytes,
                       ifd_at=args.ifd_at, tile_w=tw, tile_h=th,
                       tile_count=args.tiles)
    except Rejected as exc:
        print(json.dumps({"ok": False, "rejected": str(exc)}, indent=2))
        return 1
    if args.decode:
        result["decode"] = decode(args.frame)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
