#!/usr/bin/env python3
"""Decode FCPROBE.BIN produced by the SIGMA fp counter probe."""

import struct
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/Volumes/fpFCtest/FCPROBE.BIN")
d = p.read_bytes()
if len(d) < 48:
    raise SystemExit(f"short probe file: {len(d)} bytes")
v = struct.unpack_from("<12I", d)
labels = (
    "magic", "raw_count", "last_raw_word_address", "last_raw_cpu_address",
    "min_raw_cpu_address", "max_raw_cpu_address", "draw_count",
    "last_draw_r0", "last_draw_r1", "last_draw_r2", "saved_draw_r3", "version",
)
for label, value in zip(labels, v):
    print(f"{label:24s} {value:10d}  0x{value:08x}")
