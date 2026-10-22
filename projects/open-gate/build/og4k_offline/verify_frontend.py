#!/usr/bin/env python3
"""Verify the OG4K full-height M151 front end using the stock ARM builder.

All writes target a host bytearray or Unicorn memory. The hardware driver calls
are mocked by the existing RAW14 receiver verifier; no hardware backend exists.
The metadata, timing and sensor-table comparisons are static checks, distinct
from the instruction-emulated receiver argument construction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[3]
BUILD = WORKSPACE / "projects" / "open-gate" / "build"
sys.path.insert(0, str(BUILD))
sys.path.insert(0, str(BUILD / "raw14_2x_experiment"))

import og4k_plan as candidate
import raw14_2x_plan as evidence
import verify_receiver_native as native


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class EmulatedFirmware:
    """Minimal firmware view consumed by the existing receiver emulator."""

    image: bytes
    mode_index: dict[int, int]

    def word(self, address: int) -> int:
        return candidate.read_word(self.image, address)

    def receiver_address(self, mode: int) -> int:
        return evidence.RECEIVER_TABLE + self.mode_index[mode] * evidence.RECEIVER_STRIDE

    def bytes(self, address: int, size: int) -> bytes:
        offset = address - evidence.ROM_BASE
        if offset < 0 or offset + size > len(self.image):
            raise ValueError("overlay range outside pinned firmware")
        return self.image[offset : offset + size]


def make_overlay(firmware: evidence.Firmware, patches=None) -> EmulatedFirmware:
    """Require the complete reviewed transplant before changing emulated ROM."""

    if patches is None:
        patches = candidate.FRONTEND_PATCHES
    patches = tuple(patches)
    reviewed = tuple(
        (p.address, p.expected, p.replacement) for p in candidate.FRONTEND_PATCHES
    )
    supplied = tuple((p.address, p.expected, p.replacement) for p in patches)
    if supplied != reviewed:
        raise ValueError("overlay must be the complete reviewed 10-word front end")
    errors = candidate.validate(firmware.image)
    if errors:
        raise ValueError("invalid stock firmware: " + "; ".join(errors))
    image = bytearray(firmware.image)
    for patch in patches:
        struct.pack_into("<I", image, patch.address - evidence.ROM_BASE, patch.replacement)
    return EmulatedFirmware(bytes(image), dict(firmware.mode_index))


def differing_words(first: bytes, second: bytes) -> list[int]:
    if len(first) != len(second) or len(first) % 4:
        raise ValueError("word comparison requires equal, word-aligned records")
    return [
        offset
        for offset in range(0, len(first), 4)
        if first[offset : offset + 4] != second[offset : offset + 4]
    ]


def static_checks(firmware: evidence.Firmware, overlay: EmulatedFirmware) -> dict:
    source, donor = candidate.SOURCE_MODE, candidate.FULL_HEIGHT_DONOR
    geometry_address = firmware.metadata_address(source)
    geometry = overlay.bytes(geometry_address, evidence.METADATA_STRIDE)
    donor_geometry = firmware.bytes(firmware.metadata_address(donor), evidence.METADATA_STRIDE)
    geometry_differences = differing_words(geometry, donor_geometry)
    if geometry_differences != [0, 0x40]:
        raise AssertionError(f"unexpected metadata donor differences: {geometry_differences}")
    if struct.unpack_from("<I", geometry, 0x40)[0] != 24:
        raise AssertionError("M151 nominal fps field was not retained as 24")

    receiver = overlay.bytes(firmware.receiver_address(source), evidence.RECEIVER_STRIDE)
    donor_receiver = firmware.bytes(firmware.receiver_address(donor), evidence.RECEIVER_STRIDE)
    receiver_differences = differing_words(receiver, donor_receiver)
    if receiver_differences != [0]:
        raise AssertionError(f"unexpected receiver donor differences: {receiver_differences}")

    timing_address = firmware.timing_address(source)
    timing_record = overlay.bytes(timing_address, evidence.TIMING_STRIDE)
    donor_timing = firmware.bytes(firmware.timing_address(donor), evidence.TIMING_STRIDE)
    timing_differences = differing_words(timing_record, donor_timing)
    if timing_differences != [0, 4, 8]:
        raise AssertionError(f"unexpected timing donor differences: {timing_differences}")
    stock_timing = firmware.bytes(timing_address, evidence.TIMING_STRIDE)
    if timing_record[:0x0C] != stock_timing[:0x0C] or timing_record[0x14:] != stock_timing[0x14:]:
        raise AssertionError("M151 identity or frame timing changed")
    decoded = evidence.decode_timing(struct.unpack("<8I", timing_record))
    if decoded["frame_cycles"] != 3_000_000 or decoded["fps"] != 24:
        raise AssertionError("full-height candidate is not exact 24p")
    if decoded["input_window"] != {"x": 8, "y": 40, "x_end": 6072, "y_end": 4082}:
        raise AssertionError("full-height input window differs from native M3")

    sensor = overlay.bytes(firmware.sensor_address(source), evidence.SENSOR_STRIDE)
    stock_sensor = firmware.bytes(firmware.sensor_address(source), evidence.SENSOR_STRIDE)
    donor_sensor = firmware.bytes(firmware.sensor_address(donor), evidence.SENSOR_STRIDE)
    if sensor != stock_sensor or sensor[4:] != donor_sensor[4:]:
        raise AssertionError("M151/M3 161-register identity or untouched sensor table failed")
    changed_words = differing_words(
        firmware.image[: len(firmware.image) & ~3],
        overlay.image[: len(overlay.image) & ~3],
    )
    if [evidence.ROM_BASE + offset for offset in changed_words] != sorted(
        patch.address for patch in candidate.FRONTEND_PATCHES
    ):
        raise AssertionError("emulated firmware has edits outside the reviewed transplant")

    return {
        "source_mode": source,
        "donor_mode": donor,
        "source_index": firmware.mode_index[source],
        "donor_index": firmware.mode_index[donor],
        "modified_words": len(changed_words),
        "timing": decoded,
        "sensor_registers_unchanged_and_equal_to_donor": 161,
        "remaining_donor_differences": {
            "metadata": {"0x00": "M151 identity", "0x40": "nominal fps retained at 24, donor 30"},
            "receiver": {"0x00": "M151 identity"},
            "timing": {"0x00": "M151 identity", "0x04": "exact-24 HMAX/tail", "0x08": "exact-24 VMAX; unchanged x=8"},
        },
    }


def native_checks(firmware: evidence.Firmware, overlay: EmulatedFirmware) -> dict:
    native.require_unicorn()
    source, donor = candidate.SOURCE_MODE, candidate.FULL_HEIGHT_DONOR
    stock = native.emulate(firmware, source)
    reference = native.emulate(firmware, donor)
    full_height = native.emulate(overlay, source)
    record = overlay.bytes(firmware.receiver_address(source), evidence.RECEIVER_STRIDE)
    model = evidence.receiver_argument_model(record, native.SYNTHETIC_CONFIG)
    consumers = []
    for before, expected, actual in zip(stock["calls"], reference["calls"], full_height["calls"]):
        if (actual["consumer"], actual["channel"]) != (expected["consumer"], expected["channel"]):
            raise AssertionError("receiver consumer/channel mismatch")
        if actual["argument"] != expected["argument"] or actual["argument"] != model:
            raise AssertionError(f"consumer {actual['consumer']} differs from native M3 or model")
        differences = [
            offset for offset, (a, b) in enumerate(zip(before["argument"], actual["argument"])) if a != b
        ]
        if not differences:
            raise AssertionError("full-height check failed to distinguish stock M151")
        consumers.append({
            "name": actual["consumer"],
            "channel": actual["channel"],
            "argument_bytes": len(actual["argument"]),
            "argument_hex": actual["argument"].hex(),
            "argument_sha256": sha256(actual["argument"]),
            "changed_byte_offsets_from_stock_m151": differences,
            "native_m3_equal": True,
            "source_model_equal": True,
        })
    return {
        "emulator": f"Unicorn {native.unicorn.__version__}",
        "entry": f"0x{native.NATIVE_RECEIVER_BUILDER:08X}",
        "mode_lookup": f"0x{native.NATIVE_MODE_LOOKUP:08X}",
        "lookups": [stock["lookup"], reference["lookup"], full_height["lookup"]],
        "consumers": consumers,
        "config_fixture": "deterministic nonzero bytes; identical for all three cases",
        "config_sha256": sha256(native.SYNTHETIC_CONFIG),
    }


def verify(include_native: bool = True) -> dict:
    firmware = evidence.Firmware()
    overlay = make_overlay(firmware)
    inputs = {
        "firmware_sha256": firmware.sha256,
        "overlay_sha256": sha256(overlay.image),
        "mode_csv_sha256": firmware.mode_csv_sha256,
        "og4k_plan_sha256": sha256(Path(candidate.__file__).read_bytes()),
        "firmware_model_sha256": sha256(Path(evidence.__file__).read_bytes()),
        "native_emulator_sha256": sha256(Path(native.__file__).read_bytes()),
        "verifier_sha256": sha256(Path(__file__).read_bytes()),
    }
    report = {
        "result": "PASS",
        "scope": "OG4K M151 full-height front end only",
        "inputs": inputs,
        "verification_bundle_sha256": sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()),
        "static": static_checks(firmware, overlay),
        "native_report_verified": include_native,
        "camera_touched": False,
        "limitations": [
            "Geometry, input window, exact frame timing and sensor tables are compared statically, not executed.",
            "Only the receiver lookup and 68-byte argument builder are instruction-emulated; driver effects are mocked.",
            "Config-dependent bytes use a synthetic fixture, not captured camera state.",
            "Sensor electrical behavior, exposure, image quality, 4K scaling, allocations, recording, playback and transitions are not covered.",
        ],
    }
    if include_native:
        report["native"] = native_checks(firmware, overlay)
    else:
        report["scope"] += " (static comparisons only; native emulator not run)"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static-only", action="store_true", help="explicitly omit instruction emulation")
    args = parser.parse_args()
    json.dump(verify(include_native=not args.static_only), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
