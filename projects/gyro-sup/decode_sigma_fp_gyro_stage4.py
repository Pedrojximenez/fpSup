#!/usr/bin/env python3
"""Validate a Stage-4 .GYR sidecar and optionally convert it to Gyroflow GCSV."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import struct
from dataclasses import dataclass
from pathlib import Path

FILE_HEADER = struct.Struct("<4s7I")
BATCH_HEADER = struct.Struct("<4sIII")
SAMPLE = struct.Struct("<hhhh")
GYRO_SCALE_RAD_S = math.pi / (180.0 * 131.0)


@dataclass
class Batch:
    vd_tick: int
    flags: int
    samples: list[tuple[int, int, int]]


@dataclass
class Capture:
    version: int
    period_us: int
    start_vd: int
    camera_id: int
    reel_no: int
    clip_no: int
    initial_head: int
    batches: list[Batch]

    @property
    def clip_name(self) -> str:
        camera = chr(self.camera_id) if 0x20 <= self.camera_id < 0x7F else "?"
        return f"{camera}{self.reel_no:03d}_{self.clip_no:03d}"

    @property
    def samples(self) -> list[tuple[int, int, int]]:
        return [sample for batch in self.batches for sample in batch.samples]


def read_capture(path: Path) -> Capture:
    data = path.read_bytes()
    if len(data) < FILE_HEADER.size:
        raise ValueError("file is shorter than the Stage-4 header")
    magic, version, period_us, start_vd, camera_id, reel, clip, head = FILE_HEADER.unpack_from(data)
    if magic != b"GFS4":
        raise ValueError(f"bad file magic: {magic!r}")
    if version != 1 or period_us == 0:
        raise ValueError(f"unsupported version/period: {version}/{period_us}")
    offset = FILE_HEADER.size
    batches = []
    while offset < len(data):
        if offset + BATCH_HEADER.size > len(data):
            raise ValueError(f"truncated batch header at {offset:#x}")
        batch_magic, vd_tick, count, flags = BATCH_HEADER.unpack_from(data, offset)
        if batch_magic != b"GFV1":
            raise ValueError(f"bad batch magic at {offset:#x}: {batch_magic!r}")
        offset += BATCH_HEADER.size
        byte_count = count * SAMPLE.size
        if offset + byte_count > len(data):
            raise ValueError(f"truncated batch payload at {offset:#x}")
        samples = []
        for x, y, pad, z in SAMPLE.iter_unpack(data[offset : offset + byte_count]):
            if pad != 0:
                raise ValueError(f"non-zero padding at file offset {offset:#x}")
            samples.append((x, y, z))
        batches.append(Batch(vd_tick, flags, samples))
        offset += byte_count
    return Capture(version, period_us, start_vd, camera_id, reel, clip, head, batches)


def print_report(capture: Capture) -> None:
    samples = capture.samples
    print(f"clip: {capture.clip_name}")
    print(f"version: {capture.version}")
    print(f"sample_period_us: {capture.period_us}")
    print(f"nominal_rate_hz: {1_000_000 / capture.period_us:.6f}")
    print(f"start_vd: {capture.start_vd}")
    print(f"batches: {len(capture.batches)}")
    print(f"samples: {len(samples)}")
    print(f"duration_s: {len(samples) * capture.period_us / 1_000_000:.6f}")
    print(f"wrap_batches: {sum(bool(batch.flags & 1) for batch in capture.batches)}")
    if capture.batches:
        ticks = [batch.vd_tick for batch in capture.batches]
        print(f"vd_range: {ticks[0]}..{ticks[-1]}")
        print(f"vd_regressions: {sum(b < a for a, b in zip(ticks, ticks[1:]))}")
        counts = [len(batch.samples) for batch in capture.batches]
        print(
            "batch_samples: "
            f"min={min(counts)} max={max(counts)} "
            f"mean={statistics.fmean(counts):.3f}"
        )
    if samples:
        for axis, values in zip("xyz", zip(*samples)):
            values = list(values)
            print(
                f"{axis}: min={min(values)} max={max(values)} "
                f"mean={statistics.fmean(values):.6f} "
                f"std={statistics.pstdev(values):.6f}"
            )


def write_gcsv(path: Path, capture: Capture, orientation: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["GYROFLOW IMU LOG"])
        writer.writerow(["version", "1.3"])
        writer.writerow(["id", "sigma_fp_v502_internal_icm20321"])
        writer.writerow(["orientation", orientation])
        writer.writerow(["note", f"Stage-4 clip={capture.clip_name} start_vd={capture.start_vd}"])
        writer.writerow(["fwversion", "SIGMA fp 5.02"])
        writer.writerow(["videofilename", capture.clip_name])
        writer.writerow(["tscale", format(capture.period_us / 1_000_000, ".12g")])
        writer.writerow(["gscale", format(GYRO_SCALE_RAD_S, ".12g")])
        writer.writerow(["t", "gx", "gy", "gz"])
        for index, (x, y, z) in enumerate(capture.samples):
            writer.writerow([index, x, y, z])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--gcsv", type=Path)
    parser.add_argument("--orientation", default="XYZ")
    args = parser.parse_args()
    capture = read_capture(args.input)
    print_report(capture)
    if args.gcsv:
        write_gcsv(args.gcsv, capture, args.orientation)
        print(f"wrote: {args.gcsv}")


if __name__ == "__main__":
    main()
