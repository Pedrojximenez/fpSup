#!/usr/bin/env python3
"""Decode ordered ACCnnn.BIN snapshots from the MMA8452Q candidate globals."""

from __future__ import annotations

import argparse
import csv
import struct
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--nominal-period-ms", type=float, default=100.0)
    args = parser.parse_args()

    paths = sorted(args.directory.glob("ACC[0-9][0-9][0-9].BIN"))
    if not paths:
        raise SystemExit("no ACCnnn.BIN snapshots found")

    rows: list[tuple[int, float, int, int, int]] = []
    for index, path in enumerate(paths):
        data = path.read_bytes()
        if len(data) < 6:
            raise SystemExit(f"{path.name}: expected at least 6 bytes, got {len(data)}")
        x, y, z = struct.unpack_from("<hhh", data)
        rows.append((index, index * args.nominal_period_ms, x, y, z))

    print(f"snapshots: {len(rows)}")
    for axis, column in zip("xyz", range(2, 5)):
        values = [row[column] for row in rows]
        print(f"{axis}: min={min(values)} max={max(values)} span={max(values)-min(values)}")
    print("note: timestamps are nominal; SD write latency makes this probe unsuitable for fusion")

    if args.csv:
        with args.csv.open("w", newline="", encoding="ascii") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["sample", "nominal_ms", "ax_raw", "ay_raw", "az_raw"])
            writer.writerows(rows)
        print(f"wrote: {args.csv}")


if __name__ == "__main__":
    main()

