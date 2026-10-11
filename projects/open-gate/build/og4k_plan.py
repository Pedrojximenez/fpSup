#!/usr/bin/env python3
"""Offline OG4K-4000/24p candidate plan for SIGMA fp V5.02.

This module never imports the USB shell and has no camera actions.  It turns
the proven full-height F1 front end into an explicit 4016x2676 / RWZM 1.5x
candidate, validates every stock word against the pinned firmware, and keeps
camera arming blocked until the runtime-copy, allocation, and playback gates
are implemented.
"""

from __future__ import annotations

import csv
import hashlib
import pathlib
import struct
from dataclasses import dataclass


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
FIRMWARE = ROOT / "out" / "MAIN_c0000000.bin"
MODE_CSV = ROOT / "research" / "imx410" / "analysis" / "imx410_modes.csv"

IMAGE_BASE = 0xC0000000
FIRMWARE_SHA256 = "92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4"

MODE_COUNT = 70
TIMING_BASE = 0xC0B59500
TIMING_STRIDE = 0x20
GEOMETRY_BASE = 0xC0B59DC0
GEOMETRY_STRIDE = 0x64
RECEIVER_BASE = 0xC0B5C638
RECEIVER_STRIDE = 0x38

SOURCE_MODE = 151
FULL_HEIGHT_DONOR = 3
PROFILE = 429
FPS = 24
SENSOR_CLOCK = 72_000_000

SENSOR_RASTER = (6064, 4042)
RASTER = (4016, 2676)
ACTIVE = (4000, 2666)
CROP_ORIGIN = (8, 5)
RWZM = 1536
BITS_PER_SAMPLE = 12


@dataclass(frozen=True)
class Patch:
    address: int
    expected: int
    replacement: int
    role: str


# These are the profile429 columns modified by the proven 3K F1 experiment,
# with only the output geometry and reduction changed for OG4K-4000.
OUTPUT_PATCHES = (
    Patch(0xC0BE3F54, 3856, RASTER[0], "profile429 RAW raster width"),
    Patch(0xC0BE441C, 2170, RASTER[1], "profile429 RAW raster height"),
    Patch(0xC0BE2C34, 3840, ACTIVE[0], "profile429 active width"),
    Patch(0xC0BE30FC, 2160, ACTIVE[1], "profile429 active height"),
    Patch(0xC0BE35C4, 3856, RASTER[0], "profile429 RAW override width"),
    Patch(0xC0BE3A8C, 2170, RASTER[1], "profile429 RAW override height"),
    Patch(0xC0BE1914, 1600, RWZM, "profile429 RAW horizontal RWZM"),
    Patch(0xC0BE1DDC, 1600, RWZM, "profile429 RAW vertical RWZM"),
)

# Expected output of deriving the M151 -> native M3 full-height transplant
# directly from V5.02.  Keeping this explicit prevents a table-layout mistake
# from silently redefining the candidate.
FRONTEND_PATCHES = (
    Patch(0xC0B5B6C8, 3412, 4042, "M151 geometry height 1 from M3"),
    Patch(0xC0B5B6D8, 3412, 4042, "M151 geometry height 2 from M3"),
    Patch(0xC0B5B6E8, 3412, 4042, "M151 geometry height 3 from M3"),
    Patch(0xC0B5B714, 1, 2, "M151 geometry class from M3"),
    Patch(0xC0B5D43C, 8, 0, "M151 receiver word +0x04 from M3"),
    Patch(0xC0B5D440, 0x016001FB, 0x002601FB, "M151 receiver word +0x08 from M3"),
    Patch(0xC0B5D444, 3768, 4084, "M151 receiver word +0x0C from M3"),
    Patch(0xC0B5D450, 0x0004C003, 0x00040003, "M151 receiver word +0x18 from M3"),
    Patch(0xC0B59D0C, 0x016217B8, 0x002817B8, "M151 full-height input window word 0"),
    Patch(0xC0B59D10, 3766, 4082, "M151 full-height input window word 1"),
)

PATCHES = OUTPUT_PATCHES + FRONTEND_PATCHES

# A valid offline table is intentionally not enough to arm a camera.  These
# are implementation gates, not suggestions for the operator to waive.
HARD_GATES = (
    "select OG4K through a private runtime profile/canvas transaction; do not leave profile429 globally modified",
    "make the M151 full-height geometry/receiver/input-window change conditional on the OG4K selection and restore it before stock UHD",
    "emulate and bound every 4016x2676 producer/consumer allocation, stride, file-size, and ring-buffer calculation",
    "verify CinemaDNG header raster/crop/StripByteCounts and the 12-bit packing path before a live build",
    "extend the movie playback canvas/profile guards to the exact 4016x2676 raster and 4000x2666 crop",
    "add warm-restart cleanup and all-or-nothing rollback/readback for data and hooks",
)


class PlanError(RuntimeError):
    pass


def read_word(image: bytes, address: int) -> int:
    offset = address - IMAGE_BASE
    if offset < 0 or offset + 4 > len(image):
        raise PlanError(f"address 0x{address:08X} is outside the firmware image")
    return struct.unpack_from("<I", image, offset)[0]


def load_firmware(path: pathlib.Path = FIRMWARE) -> bytes:
    image = path.read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    if digest != FIRMWARE_SHA256:
        raise PlanError(f"firmware sha256 {digest} != pinned V5.02 {FIRMWARE_SHA256}")
    return image


def mode_indices(image: bytes) -> dict[int, int]:
    result: dict[int, int] = {}
    for index in range(MODE_COUNT):
        mode = read_word(image, TIMING_BASE + index * TIMING_STRIDE)
        if mode in result:
            raise PlanError(f"duplicate timing mode id {mode}")
        result[mode] = index
    return result


def _record_words(image: bytes, base: int, stride: int, index: int) -> tuple[int, ...]:
    address = base + stride * index
    return tuple(read_word(image, address + offset) for offset in range(0, stride, 4))


def derive_frontend_patches(image: bytes) -> tuple[Patch, ...]:
    """Derive the narrow M151 transplant; keep exact24 timing words intact."""
    indices = mode_indices(image)
    try:
        source_index = indices[SOURCE_MODE]
        donor_index = indices[FULL_HEIGHT_DONOR]
    except KeyError as exc:
        raise PlanError(f"missing sensor mode {exc.args[0]}") from exc

    patches: list[Patch] = []
    for base, stride, excluded, label in (
        (GEOMETRY_BASE, GEOMETRY_STRIDE, {0x40}, "geometry"),
        (RECEIVER_BASE, RECEIVER_STRIDE, set(), "receiver"),
    ):
        source = _record_words(image, base, stride, source_index)
        donor = _record_words(image, base, stride, donor_index)
        if source[0] != SOURCE_MODE or donor[0] != FULL_HEIGHT_DONOR:
            raise PlanError(f"{label} table id/index mismatch")
        for offset in range(4, stride, 4):
            if offset in excluded:
                continue
            old, new = source[offset // 4], donor[offset // 4]
            if old != new:
                patches.append(
                    Patch(
                        base + source_index * stride + offset,
                        old,
                        new,
                        f"M151 {label} +0x{offset:02X} from M3",
                    )
                )

    timing_source = TIMING_BASE + source_index * TIMING_STRIDE
    timing_donor = TIMING_BASE + donor_index * TIMING_STRIDE
    for offset in (0x0C, 0x10):
        old = read_word(image, timing_source + offset)
        new = read_word(image, timing_donor + offset)
        if old != new:
            patches.append(
                Patch(
                    timing_source + offset,
                    old,
                    new,
                    f"M151 input window +0x{offset:02X} from M3",
                )
            )
    return tuple(patches)


def sensor_fingerprints_equal(path: pathlib.Path = MODE_CSV) -> bool:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_mode = {int(row["mode_id"]): row for row in rows}
    if SOURCE_MODE not in by_mode or FULL_HEIGHT_DONOR not in by_mode:
        raise PlanError("mode CSV does not contain M151 and M3")
    columns = [name for name in rows[0] if name.startswith("reg_0x")]
    if len(columns) != 161:
        raise PlanError(f"mode CSV has {len(columns)} sensor-register columns, want 161")
    return all(
        by_mode[SOURCE_MODE][column] == by_mode[FULL_HEIGHT_DONOR][column]
        for column in columns
    )


def timing(image: bytes) -> tuple[int, int, int, int]:
    index = mode_indices(image)[SOURCE_MODE]
    address = TIMING_BASE + index * TIMING_STRIDE + 4
    return struct.unpack_from("<4H", image, address - IMAGE_BASE)


def frame_cycles(image: bytes) -> int:
    hmax, tail, vmax, _ = timing(image)
    return hmax * (vmax - 1) + tail


def packed_row_bytes() -> int:
    bits = RASTER[0] * BITS_PER_SAMPLE
    if bits % 8:
        raise PlanError("candidate packed row is not byte aligned")
    return bits // 8


def raw_frame_bytes() -> int:
    return packed_row_bytes() * RASTER[1]


def raw_rate_bytes_per_second() -> int:
    return raw_frame_bytes() * FPS


def stock_uhd_rate_bytes_per_second() -> float:
    return 3856 * 2170 * 12 / 8 * 29.97


def validate(image: bytes) -> list[str]:
    errors: list[str] = []
    digest = hashlib.sha256(image).hexdigest()
    if digest != FIRMWARE_SHA256:
        errors.append(f"firmware sha256 {digest} is not pinned V5.02")

    if len(PATCHES) != 18 or len({patch.address for patch in PATCHES}) != 18:
        errors.append("candidate must contain exactly 18 unique patch words")
    for patch in PATCHES:
        if patch.address & 3:
            errors.append(f"unaligned patch address 0x{patch.address:08X}")
            continue
        try:
            actual = read_word(image, patch.address)
        except PlanError as exc:
            errors.append(str(exc))
            continue
        if actual != patch.expected:
            errors.append(
                f"0x{patch.address:08X}=0x{actual:08X}, expected 0x{patch.expected:08X}"
            )

    try:
        derived = derive_frontend_patches(image)
        derived_triplets = tuple((p.address, p.expected, p.replacement) for p in derived)
        expected_triplets = tuple(
            (p.address, p.expected, p.replacement) for p in FRONTEND_PATCHES
        )
        if derived_triplets != expected_triplets:
            errors.append("derived M151->M3 front-end transplant differs from the reviewed 10 words")
    except PlanError as exc:
        errors.append(str(exc))

    try:
        hmax, tail, vmax, x = timing(image)
        if (hmax, tail, vmax, x) != (445, 1145, 6740, 8):
            errors.append(f"M151 timing {(hmax, tail, vmax, x)} is not exact-24 baseline")
        if frame_cycles(image) != 3_000_000:
            errors.append(f"M151 frame cycle count {frame_cycles(image)} != 3000000")
    except (KeyError, PlanError, struct.error) as exc:
        errors.append(f"cannot validate M151 timing: {exc}")

    if RASTER[0] - ACTIVE[0] != 16 or RASTER[1] - ACTIVE[1] != 10:
        errors.append("candidate does not preserve the +16/+10 CinemaDNG border")
    if CROP_ORIGIN != ((RASTER[0] - ACTIVE[0]) // 2, (RASTER[1] - ACTIVE[1]) // 2):
        errors.append("candidate crop origin is not centered in the raster border")
    if RASTER[0] % 16 or RASTER[1] % 2 or ACTIVE[0] % 2 or ACTIVE[1] % 2:
        errors.append("candidate violates width/Bayer-even geometry constraints")
    try:
        if packed_row_bytes() != 6024 or raw_frame_bytes() != 16_120_224:
            errors.append("packed RAW12 geometry does not match the reviewed byte counts")
    except PlanError as exc:
        errors.append(str(exc))

    try:
        if not sensor_fingerprints_equal():
            errors.append("M151 and M3 do not have identical 161-register fingerprints")
    except (OSError, KeyError, PlanError) as exc:
        errors.append(f"cannot validate sensor fingerprints: {exc}")
    return errors


def camera_ready() -> bool:
    """The current artifact is deliberately an offline plan, never armable."""
    return False


def main() -> int:
    try:
        image = load_firmware()
    except (OSError, PlanError) as exc:
        print(f"error: {exc}")
        return 1
    errors = validate(image)
    print("OG4K-4000 / exact 24p offline candidate")
    print(f"firmware  {FIRMWARE_SHA256[:16]}…")
    print(f"sensor    {SENSOR_RASTER[0]}x{SENSOR_RASTER[1]} M151-full-height")
    print(f"output    {RASTER[0]}x{RASTER[1]}, crop {ACTIVE[0]}x{ACTIVE[1]} @ {CROP_ORIGIN}")
    print(f"RWZM      {RWZM}/1024 = {RWZM / 1024:.3f}x")
    print(f"RAW12     {packed_row_bytes()} bytes/row, {raw_frame_bytes():,} bytes/frame")
    print(f"rate      {raw_rate_bytes_per_second() / 1e6:.1f} MB/s")
    overhead = raw_rate_bytes_per_second() / stock_uhd_rate_bytes_per_second() - 1
    print(f"vs UHD30  {overhead * 100:+.2f}%")
    print(f"patches   {len(PATCHES)} reviewed words")
    if errors:
        print("offline validation: FAIL")
        for error in errors:
            print("  - " + error)
        return 1
    print("offline validation: PASS")
    print("camera build: BLOCKED")
    for gate in HARD_GATES:
        print("  - " + gate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
