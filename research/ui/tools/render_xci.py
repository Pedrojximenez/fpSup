#!/usr/bin/env python3
"""Render a Sigma XCI file, including ``display capture`` output, to PNG.

Normal UI resources contain one little-endian L8/A8 pair per pixel.  The
camera's ``display capture ... both`` command may also emit an 8-bit companion
plane.  This tool handles both without knowing anything about a particular
project or screen.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from xci import HDR, MAGIC, _lz4_block


def decode_plane(blob: bytes) -> tuple[int, int, np.ndarray, str]:
    if blob[:4] != MAGIC:
        raise ValueError("not an XCI file")
    if len(blob) < HDR + 4:
        raise ValueError("truncated XCI header")

    width, height = struct.unpack_from("<HH", blob, 8)
    block_size = struct.unpack_from("<I", blob, 0x2F)[0] & 0x7FFFFFFF
    block_end = HDR + block_size
    if block_end + 4 > len(blob):
        raise ValueError("XCI compressed block exceeds the file")

    raw = _lz4_block(blob[HDR:block_end])
    pixels = width * height
    if len(raw) == pixels * 2:
        values = np.frombuffer(raw, dtype="<u2").reshape(height, width)
        luminance = (values & 0xFF).astype(np.uint8)
        alpha = ((values >> 8) & 0xFF).astype(np.uint8)
        rgba = np.dstack((luminance, luminance, luminance, alpha))
        return width, height, rgba, "L8A8"
    if len(raw) == pixels:
        plane = np.frombuffer(raw, dtype=np.uint8).reshape(height, width)
        return width, height, plane, "L8"
    raise ValueError(
        f"decoded payload is {len(raw)} bytes; expected {pixels} or {pixels * 2}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()

    output = args.output or args.input.with_suffix(".png")
    width, height, pixels, encoding = decode_plane(args.input.read_bytes())
    Image.fromarray(pixels).save(output)
    print(f"{args.input}: {width}x{height} {encoding} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
