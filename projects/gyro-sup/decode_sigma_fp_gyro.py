#!/usr/bin/env python3
"""Inspect or convert SIGMA fp Ver.5.02 internal gyro captures.

The Stage-3 hook writes consecutive 8-byte records copied from the OIS
co-processor ring.  Each little-endian record is four int16 values:

    sensor_x, sensor_y, padding_zero, sensor_z

The sample rate and camera-body orientation are still provisional and must be
verified against video/optical flow before a generated GCSV is production-ready.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import statistics
import struct
from pathlib import Path

RECORD = struct.Struct("<hhhh")
GYRO_SCALE_RAD_S = math.pi / (180.0 * 131.0)


def read_records(path: Path) -> list[tuple[int, int, int]]:
    data = path.read_bytes()
    if len(data) % RECORD.size:
        raise ValueError(f"{path}: size {len(data)} is not divisible by 8")
    records = []
    for x, y, pad, z in RECORD.iter_unpack(data):
        if pad != 0:
            raise ValueError(
                f"{path}: non-zero padding at sample {len(records)}: {pad}"
            )
        records.append((x, y, z))
    return records


def print_info(path: Path, records: list[tuple[int, int, int]], rate: float) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"file: {path}")
    print(f"sha256: {digest}")
    print(f"samples: {len(records)}")
    print(f"assumed_rate_hz: {rate:g}")
    print(f"assumed_duration_s: {len(records) / rate:.6f}")
    for axis, values in zip("xyz", zip(*records)):
        vals = list(values)
        print(
            f"{axis}: min={min(vals)} max={max(vals)} "
            f"mean={statistics.fmean(vals):.6f} "
            f"std={statistics.pstdev(vals):.6f}"
        )


def parse_axis_map(value: str) -> tuple[tuple[int, int], ...]:
    tokens = value.replace(" ", "").split(",")
    if len(tokens) != 3:
        raise argparse.ArgumentTypeError("axis map must contain 3 items, e.g. x,-z,y")
    indices = {"x": 0, "y": 1, "z": 2}
    parsed = []
    used = set()
    for token in tokens:
        sign = -1 if token.startswith("-") else 1
        name = token.lstrip("+-").lower()
        if name not in indices or name in used:
            raise argparse.ArgumentTypeError("axis map must use x, y and z once each")
        used.add(name)
        parsed.append((indices[name], sign))
    return tuple(parsed)


def write_gcsv(
    output: Path,
    records: list[tuple[int, int, int]],
    rate: float,
    orientation: str,
    axis_map: tuple[tuple[int, int], ...],
) -> None:
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["GYROFLOW IMU LOG"])
        writer.writerow(["version", "1.3"])
        writer.writerow(["id", "sigma_fp_v502_internal_icm20321"])
        writer.writerow(["orientation", orientation])
        writer.writerow(["note", "provisional sample rate and orientation"])
        writer.writerow(["fwversion", "SIGMA fp 5.02"])
        writer.writerow(["tscale", format(1.0 / rate, ".12g")])
        writer.writerow(["gscale", format(GYRO_SCALE_RAD_S, ".12g")])
        writer.writerow(["t", "gx", "gy", "gz"])
        for timestamp, sample in enumerate(records):
            mapped = [sample[index] * sign for index, sign in axis_map]
            writer.writerow([timestamp, *mapped])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--rate", type=float, default=400.0,
                        help="provisional sample rate in Hz (default: 400; descriptor period is 2500 us)")
    parser.add_argument("--gcsv", type=Path, help="write a provisional Gyroflow GCSV")
    parser.add_argument("--orientation", default="XYZ",
                        help="Gyroflow IMU orientation string (default: XYZ)")
    parser.add_argument("--axis-map", type=parse_axis_map, default=parse_axis_map("x,y,z"),
                        help="output mapping, e.g. x,-z,y (default: x,y,z)")
    args = parser.parse_args()
    if args.rate <= 0:
        parser.error("--rate must be positive")
    records = read_records(args.input)
    print_info(args.input, records, args.rate)
    if args.gcsv:
        write_gcsv(args.gcsv, records, args.rate, args.orientation, args.axis_map)
        print(f"wrote: {args.gcsv}")


if __name__ == "__main__":
    main()
