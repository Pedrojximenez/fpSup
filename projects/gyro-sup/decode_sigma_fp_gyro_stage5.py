#!/usr/bin/env python3
"""Validate Stage-5 GYR and convert timestamped samples to Gyroflow GCSV.

Handles both capture formats:
  version 2 / GFT1 -- gyro only, 16-byte batch header
  version 3 / GFT2 -- adds the MMA8452Q accelerometer, 24-byte batch header

Accel arrives once per batch rather than once per sample: the firmware refreshes
its cache at only ~47 Hz against the gyro's 2500 Hz, so a per-sample copy would be
padding. Each batch's triple carries that batch's own TickTimer stamp, which is the
same clock the gyro samples are interpolated from, so both sensors share one time
base. Rows in between hold the last value -- correct enough for a gravity vector,
which is what Gyroflow uses the accelerometer for (horizon lock).
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import struct
from dataclasses import dataclass
from pathlib import Path

FILE_HEADER = struct.Struct("<4s7I")        # v2/v3: 32 bytes
FILE_HEADER_V4 = struct.Struct("<4s11I")   # v4: adds frame_readout_us + 3 reserved
BATCH_HEADER = struct.Struct("<4sIII")        # v2: GFT1
BATCH_HEADER_V3 = struct.Struct("<4sIII4h")   # v3: GFT2, trailing accel x/y/z/pad
SAMPLE = struct.Struct("<hhhh")
GYRO_SCALE_RAD_S = math.pi / (180.0 * 131.0)     # nominal, from the 131 LSB/dps datasheet figure

# Defaults that make the output usable as-is, all measured rather than assumed.
#
# ORIENTATION: "xyz" -- all three axes negated, i.e. the gyro chip is mounted
# rotated 180 degrees relative to the camera. Verified one column at a time on three
# single-axis takes: a pure pan (98% of signal on sensor X), a pure tilt (sensor Y),
# and a pure roll (sensor Z). Each column was decided on the take where that axis
# dominates, so all three are measured rather than inferred.
#
# The archive lists "YxZ" as confirmed; it is wrong and amplifies shake ~1.9x. That
# value came from *absolute* correlation coefficients, which fix the axis pairing and
# say nothing about sign. Several intermediate guesses here (YXZ, XzY, Xyz) were wrong
# for a subtler reason worth remembering: the orientation string is applied to the
# accelerometer as well, and gravity means the accelerometer carries signal in *every*
# take. So while a pan take isolates the gyro's X axis, it does not isolate the string
# -- columns 2 and 3 still act on the accel and feed the VQF fusion. A/B results only
# became reproducible after dropping accel from the file.
DEFAULT_ORIENTATION = "xyz"

# GSCALE: what optical flow actually measures is the product focal_px * gscale, since
# that is what turns a gyro reading into pixels of image motion. Splitting it needs a
# focal length, and the earlier 0.000121385 was split using one fitted from the same
# data (2451 px), which let a focal error hide inside gscale.
#
# The firmware's IMX410 mode tables settle the focal independently: 1080p/29.97 is mode
# 111, geometry 3032x1708 = 6064/2, i.e. 2x2 binned across the full sensor width rather
# than cropped, so focal_px = 1936 * 40 / 35.9 = 2157. Re-splitting the measured product
# by that gives 0.000137923 -- 3.5% off the 131 LSB/dps datasheet figure instead of the
# 13.6% the old split implied, which is the more believable of the two.
DEFAULT_GSCALE = 0.000137923

# TIME SHIFT: leave it at zero and let Gyroflow's auto-sync find it per clip.
#
# It is tempting to bake in a constant -- an early clip measured 570 ms and an
# earlier session independently measured 575 ms, which looks like a fixed pipeline
# latency. It is not. Three single-axis clips shot back to back measured 515, 470
# and 470 ms, so the offset moves by ~100 ms (three frames) from take to take and
# any hard-coded value is wrong for most clips. The 570/575 agreement was luck.
#
# Per-frame anchoring (hooking FrameExpos_s at 0xC0315C10 and logging a TickTimer
# stamp per exposure) would make this exact instead of estimated.
DEFAULT_TIME_SHIFT_US = 0
ACCEL_SCALE_G = 1.0 / 1024.0                  # MMA8452Q at +/-2 g

# The accel needs no extra rotation: leave Gyroflow's accelerometer rotation at 0 and
# let imu_orientation = "xyz" serve both sensors.
#
# The two chips are separate and independently mounted, so in principle one string
# cannot describe both -- Gyroflow provides acc_rotation for exactly that case. But the
# firmware already normalises the accelerometer: IMUDev_ACCEL_MMA8452Q__v7 switches on
# an orientation code (cases 0-6) and permutes/negates the axes before storing to the
# cache at 0xC377790C. What we read is therefore already in the camera's canonical
# frame, the same one the gyro ring uses.
#
# Confirmed the hard way. An offline solve -- which axis map makes measured gravity
# rotate the way the integrated gyro predicts -- nominated an extra +90 deg about Z, and
# applying it rotated the whole picture 90 deg. That solve had weak discrimination, with
# several candidates scoring within noise of each other, and wrapping a marginal result
# in a tidy determinant argument only made it look sounder than it was.

@dataclass
class Batch:
    timestamp_us: int
    flags: int
    samples: list[tuple[int, int, int]]
    accel: tuple[int, int, int] | None = None


@dataclass
class Capture:
    period_us: int
    start_us: int
    camera_id: int
    reel_no: int
    clip_no: int
    initial_head: int
    batches: list[Batch]
    version: int = 2
    exposure_us: int = 0
    mode_a: int = 0
    mode_b: int = 0

    @property
    def has_accel(self) -> bool:
        return any(batch.accel is not None for batch in self.batches)

    @property
    def clip_name(self) -> str:
        camera = chr(self.camera_id) if 0x20 <= self.camera_id < 0x7f else "?"
        return f"{camera}{self.reel_no:03d}_{self.clip_no:03d}"

    @property
    def effective_period_us(self) -> int:
        # Firmware descriptor value 2500 is the output data rate in Hz.
        # Stage-5 initially stored it in the period field before this was
        # confirmed by the monotonic TickTimer capture.
        return round(1_000_000 / self.period_us) if self.period_us >= 1000 else self.period_us


def delta32(value: int, origin: int) -> int:
    return (value - origin) & 0xffffffff


def read_capture(path: Path) -> Capture:
    data = path.read_bytes()
    if len(data) < FILE_HEADER.size:
        raise ValueError("檔案短於 Stage-5 header")
    magic, version, period, start, camera, reel, clip, head = FILE_HEADER.unpack_from(data)
    if magic != b"GFS5" or version not in (2, 3, 4) or not period:
        raise ValueError(f"不支援的 header: {magic!r}, version={version}, period={period}")
    exposure_us = 0
    header_size = FILE_HEADER.size
    if version >= 4:
        header_size = FILE_HEADER_V4.size
        f = FILE_HEADER_V4.unpack_from(data)
        exposure_us, mode_a, mode_b = f[8], f[9], f[10]
    batches, offset = [], header_size
    while offset < len(data):
        if offset + BATCH_HEADER.size > len(data):
            raise ValueError(f"batch header 截斷於 {offset:#x}")
        magic = data[offset:offset + 4]
        accel = None
        if magic == b"GFT2":
            if offset + BATCH_HEADER_V3.size > len(data):
                raise ValueError(f"batch header 截斷於 {offset:#x}")
            _, timestamp, count, flags, ax, ay, az, _pad = BATCH_HEADER_V3.unpack_from(data, offset)
            accel = (ax, ay, az)
            offset += BATCH_HEADER_V3.size
        elif magic == b"GFT1":
            _, timestamp, count, flags = BATCH_HEADER.unpack_from(data, offset)
            offset += BATCH_HEADER.size
        else:
            raise ValueError(f"batch magic 錯誤於 {offset:#x}: {magic!r}")
        end = offset + count * SAMPLE.size
        if end > len(data):
            raise ValueError(f"batch payload 截斷於 {offset:#x}")
        samples = []
        for x, y, pad, z in SAMPLE.iter_unpack(data[offset:end]):
            if pad:
                raise ValueError(f"非零 padding 於 {offset:#x}")
            samples.append((x, y, z))
        batches.append(Batch(timestamp, flags, samples, accel))
        offset = end
    return Capture(period, start, camera, reel, clip, head, batches, version, exposure_us, mode_a, mode_b)


def timestamped_samples(capture: Capture):
    """Interpolate each sample backwards from its batch-drain timestamp.

    Yields (timestamp_us, gyro, accel). Accel holds the most recent batch triple,
    or None until the first batch that carries one.
    """
    last = -1
    accel = None
    for batch in capture.batches:
        if batch.accel is not None:
            accel = batch.accel
        batch_end = delta32(batch.timestamp_us, capture.start_us)
        first = batch_end - (len(batch.samples) - 1) * capture.effective_period_us
        for index, sample in enumerate(batch.samples):
            timestamp = max(first + index * capture.effective_period_us, last + 1)
            last = timestamp
            yield timestamp, sample, accel


def print_report(capture: Capture) -> None:
    rows = list(timestamped_samples(capture))
    print(f"version: {capture.version}  accel: {'yes' if capture.has_accel else 'no'}")
    if capture.exposure_us:
        print(f"exposure_us: {capture.exposure_us}  ({capture.exposure_us / 1000:.2f} ms"
              f" = 1/{1e6 / capture.exposure_us:.0f} s)")
    if capture.mode_a or capture.mode_b:
        print(f"sensor mode indices: {capture.mode_a}, {capture.mode_b}"
              f"  (feeds make_gyroflow_lens_profile.py, which cannot tell modes apart"
              f" from resolution and frame rate alone)")
    counts = [len(batch.samples) for batch in capture.batches]
    ticks = [delta32(batch.timestamp_us, capture.start_us) for batch in capture.batches]
    print(f"clip: {capture.clip_name}")
    print(f"descriptor_value: {capture.period_us}")
    print(f"sample_period_us: {capture.effective_period_us}")
    print(f"nominal_rate_hz: {1_000_000 / capture.effective_period_us:.6f}")
    print(f"start_timestamp_us: {capture.start_us}")
    print(f"batches: {len(capture.batches)}")
    print(f"samples: {len(rows)}")
    print(f"duration_s: {len(rows) * capture.effective_period_us / 1_000_000:.6f}")
    print(f"wrap_batches: {sum(bool(batch.flags & 1) for batch in capture.batches)}")
    if ticks:
        print(f"timestamp_span_s: {(ticks[-1] - ticks[0]) / 1_000_000:.6f}")
        print(f"timestamp_regressions: {sum(b < a for a, b in zip(ticks, ticks[1:]))}")
        print(f"batch_samples: min={min(counts)} max={max(counts)} mean={statistics.fmean(counts):.3f}")


def write_gcsv(
    path: Path, capture: Capture, orientation: str, gscale: float,
    time_shift_us: int, ascale: float = ACCEL_SCALE_G, want_accel: bool = False,
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows([
            ["GYROFLOW IMU LOG"], ["version", "1.3"],
            ["id", "sigma_fp_v502_internal_icm20321"], ["orientation", orientation],
            ["note", f"Stage-5 calibrated clip={capture.clip_name}; shift={time_shift_us}us"],
            ["fwversion", "SIGMA fp 5.02"], ["videofilename", capture.clip_name],
            ["tscale", "0.000001"], ["gscale", format(gscale, ".12g")],
        ])
        use_accel = want_accel and capture.has_accel
        if use_accel:
            writer.writerows([["ascale", format(ascale, ".12g")],
                              ["t", "gx", "gy", "gz", "ax", "ay", "az"]])
        else:
            writer.writerow(["t", "gx", "gy", "gz"])
        for timestamp, (x, y, z), accel in timestamped_samples(capture):
            timestamp -= time_shift_us
            if timestamp < 0:
                continue
            if use_accel:
                ax, ay, az = accel if accel else (0, 0, 0)
                writer.writerow([timestamp, x, y, z, ax, ay, az])
            else:
                writer.writerow([timestamp, x, y, z])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--gcsv", type=Path)
    parser.add_argument("--orientation", default=DEFAULT_ORIENTATION)
    parser.add_argument("--gscale", type=float, default=DEFAULT_GSCALE)
    parser.add_argument("--time-shift-us", type=int, default=DEFAULT_TIME_SHIFT_US)
    # Accel is on by default now that its frame is settled. It costs nothing in the file
    # and most of Gyroflow's integrators fuse it for drift correction, plus horizon lock
    # needs it. --no-accel is there for isolating it during debugging: when an A/B on the
    # orientation string refuses to reproduce, gravity means the accel carries signal in
    # every take, so it is worth ruling out first.
    parser.add_argument("--no-accel", dest="accel", action="store_false",
                        help="omit accelerometer columns (useful when debugging orientation)")
    parser.set_defaults(accel=True)
    args = parser.parse_args()
    capture = read_capture(args.input)
    print_report(capture)
    if args.gcsv:
        write_gcsv(args.gcsv, capture, args.orientation, args.gscale, args.time_shift_us,
                   want_accel=args.accel)
        print(f"wrote: {args.gcsv}")
        print(f"  orientation={args.orientation} gscale={args.gscale} shift={args.time_shift_us}us"
              + (" accel=on (leave Gyroflow acc_rotation at 0)" if args.accel else " accel=off (--no-accel)"))


if __name__ == "__main__":
    main()
