#!/usr/bin/env python3
"""Offline-only planner for the IMX410 RAW14 + 2x OpenGate experiment.

This module reads the reference firmware and research CSVs.  It has no camera,
USB-shell, serial, network, or live-memory backend.  In particular, the two
RAW14 stages deliberately remain non-executable until their missing gates are
resolved.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ROM_BASE = 0xC0000000
EXPECTED_FIRMWARE_SIZE = 49_482_954
EXPECTED_FIRMWARE_SHA256 = (
    "92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4"
)
EXPECTED_MODE_CSV_SHA256 = (
    "e64d025341edc9d3d619fb96e4cfe28119b7a3d9079fc12e07c66ad066d315db"
)
EXPECTED_REGISTER_ORDER_SHA256 = (
    "7a8369088223dd941ed4eff3a1a5f1886017bac237a59c9eb5e7bc2dd7402bb5"
)

MODE_COUNT = 70
SENSOR_REGISTER_COUNT = 161
TIMING_TABLE = 0xC0B59500
TIMING_STRIDE = 0x20
METADATA_TABLE = 0xC0B59DC0
METADATA_STRIDE = 0x64
RECEIVER_TABLE = 0xC0B5C638
RECEIVER_STRIDE = 0x38
SENSOR_TABLE = 0xC0B5FDAC
SENSOR_STRIDE = 0x288

M6 = 6
M98 = 98
M141 = 141
M142 = 142
M143 = 143

# Four actual sibling transitions.  The fifth MONIT comparison once used here
# was not an ACQ sibling and incorrectly shrank the common reduction set.
Q12_1X_TO_2X_SIBLINGS: Tuple[Tuple[int, int], ...] = (
    (97, 98),
    (142, 143),
    (130, 131),
    (145, 146),
)

# Every sibling pair above changes these registers to the same target values.
# reg 0x0001 is excluded: it is the one overlap between the depth and reduction
# blocks, and no RAW14+2x value exists in either known firmware dataset.
PROVEN_2X_CORE: Tuple[int, ...] = (
    0x0005,
    0x001C,
    0x0056,
    0x0057,
    0x0058,
    0x0717,
    0x071E,
    0x0720,
    0x0722,
    0x0723,
    0x0724,
    0x0725,
    0x0726,
    0x0728,
    0x072A,
    0x072B,
    0x072C,
    0x0734,
    0x0735,
    0x0737,
    0x0738,
    0x0739,
    0x073A,
    0x0790,
    0x0792,
    0x0793,
    0x0794,
    0x079C,
)

RAW14_1X_MODE_CODE = 0x29
RAW12_1X_MODE_CODE = 0x2A
RAW12_2X_MODE_CODE = 0x39

TARGET_TIMING_W0 = 0x077B038F  # HMAX 911, tail 1915
TARGET_TIMING_W1 = 0x00040A4C  # VMAX 2636, x=4
TARGET_WINDOW_W2 = 0x00140BDC  # y=20, x_end=3036
TARGET_WINDOW_W3 = 0x000007F0  # y_end=2032

RECORD_WIDTH = 3024
RECORD_HEIGHT = 2010
ACTIVE_WIDTH = 3008
ACTIVE_HEIGHT = 2000
RAW14_PREVIEW_FORMAT = 10
RAW14_RAW_PLANE_FORMAT = 8
RAW14_DMA_SELECTOR = 1


def _find_workspace(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "out" / "MAIN_c0000000.bin").is_file() and (
            candidate / "research" / "imx410" / "analysis" / "imx410_modes.csv"
        ).is_file():
            return candidate
    raise FileNotFoundError("cannot locate SIGMAfp_re workspace")


HERE = Path(__file__).resolve().parent
WORKSPACE = _find_workspace(HERE)
FIRMWARE = WORKSPACE / "out" / "MAIN_c0000000.bin"
MODE_CSV = WORKSPACE / "research" / "imx410" / "analysis" / "imx410_modes.csv"


@dataclass(frozen=True)
class Patch:
    address: int
    expected: int
    replacement: int
    region: str
    reason: str
    confidence: str = "confirmed"


class Firmware:
    def __init__(self, path: Path = FIRMWARE, mode_csv: Path = MODE_CSV):
        self.path = Path(path)
        self.mode_csv_path = Path(mode_csv)
        self.image = self.path.read_bytes()
        self.sha256 = hashlib.sha256(self.image).hexdigest()
        if len(self.image) != EXPECTED_FIRMWARE_SIZE:
            raise ValueError(
                f"firmware size {len(self.image)} != {EXPECTED_FIRMWARE_SIZE}"
            )
        if self.sha256 != EXPECTED_FIRMWARE_SHA256:
            raise ValueError(
                f"firmware sha256 {self.sha256} != {EXPECTED_FIRMWARE_SHA256}"
            )
        self.mode_order = [
            self.word(TIMING_TABLE + index * TIMING_STRIDE)
            for index in range(MODE_COUNT)
        ]
        if len(set(self.mode_order)) != MODE_COUNT:
            raise ValueError("timing table mode IDs are not unique")
        self.mode_index = {mode: index for index, mode in enumerate(self.mode_order)}

        csv_image = self.mode_csv_path.read_bytes()
        self.mode_csv_sha256 = hashlib.sha256(csv_image).hexdigest()
        if self.mode_csv_sha256 != EXPECTED_MODE_CSV_SHA256:
            raise ValueError(
                f"mode CSV sha256 {self.mode_csv_sha256} != "
                f"{EXPECTED_MODE_CSV_SHA256}"
            )
        with self.mode_csv_path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ValueError("mode CSV has no header")
            fieldnames = reader.fieldnames
            if fieldnames[:2] != ["index", "mode_id"]:
                raise ValueError("mode CSV must begin with index,mode_id")
            if any(not name.startswith("reg_0x") for name in fieldnames[2:]):
                raise ValueError("mode CSV has unexpected non-register columns")
            fields = fieldnames[2:]
            rows = list(reader)
        if len(rows) != MODE_COUNT:
            raise ValueError(f"mode CSV has {len(rows)} rows, expected {MODE_COUNT}")
        if len(fields) != SENSOR_REGISTER_COUNT:
            raise ValueError(
                f"mode CSV has {len(fields)} sensor registers, "
                f"expected {SENSOR_REGISTER_COUNT}"
            )
        self.register_order_sha256 = hashlib.sha256(
            ",".join(fields).encode("ascii")
        ).hexdigest()
        if self.register_order_sha256 != EXPECTED_REGISTER_ORDER_SHA256:
            raise ValueError(
                f"sensor-register order sha256 {self.register_order_sha256} != "
                f"{EXPECTED_REGISTER_ORDER_SHA256}"
            )
        self.registers = tuple(int(field.removeprefix("reg_0x"), 16) for field in fields)
        self.register_index = {register: i for i, register in enumerate(self.registers)}
        if len(self.register_index) != SENSOR_REGISTER_COUNT:
            raise ValueError("mode CSV repeats a sensor-register column")

        # The CSV is only accepted as an index into this exact ROM.  Check every
        # mode ID and every register word, rather than trusting a matching row
        # count or a separately generated CSV.
        self.csv_rom_crosscheck_count = 0
        self.csv_mode_order: Tuple[int, ...] = tuple(int(row["mode_id"]) for row in rows)
        for index, row in enumerate(rows):
            csv_index = int(row["index"])
            csv_mode = int(row["mode_id"])
            if csv_index != index:
                raise ValueError(f"mode CSV row {index} declares index {csv_index}")
            if csv_mode != self.mode_order[index]:
                raise ValueError(
                    f"mode CSV row {index} mode {csv_mode} != ROM mode "
                    f"{self.mode_order[index]}"
                )
            sensor_base = SENSOR_TABLE + index * SENSOR_STRIDE + 4
            for register_index, field in enumerate(fields):
                csv_value = int(row[field])
                rom_value = self.word(sensor_base + register_index * 4)
                if csv_value != rom_value:
                    raise ValueError(
                        f"mode CSV M{csv_mode} {field}={csv_value} != "
                        f"ROM {rom_value}"
                    )
                self.csv_rom_crosscheck_count += 1

    def word(self, address: int) -> int:
        offset = address - ROM_BASE
        if offset < 0 or offset + 4 > len(self.image):
            raise ValueError(f"address outside firmware: 0x{address:08X}")
        return struct.unpack_from("<I", self.image, offset)[0]

    def bytes(self, address: int, size: int) -> bytes:
        offset = address - ROM_BASE
        if offset < 0 or offset + size > len(self.image):
            raise ValueError(f"range outside firmware: 0x{address:08X}+0x{size:X}")
        return self.image[offset : offset + size]

    def table_address(self, table: int, stride: int, mode: int) -> int:
        return table + self.mode_index[mode] * stride

    def timing_address(self, mode: int) -> int:
        return self.table_address(TIMING_TABLE, TIMING_STRIDE, mode)

    def metadata_address(self, mode: int) -> int:
        return self.table_address(METADATA_TABLE, METADATA_STRIDE, mode)

    def receiver_address(self, mode: int) -> int:
        return self.table_address(RECEIVER_TABLE, RECEIVER_STRIDE, mode)

    def sensor_address(self, mode: int) -> int:
        return self.table_address(SENSOR_TABLE, SENSOR_STRIDE, mode)

    def record_words(self, address: int, size: int) -> Tuple[int, ...]:
        return tuple(self.word(address + offset) for offset in range(0, size, 4))

    def timing_words(self, mode: int) -> Tuple[int, ...]:
        return self.record_words(self.timing_address(mode), TIMING_STRIDE)

    def metadata_words(self, mode: int) -> Tuple[int, ...]:
        return self.record_words(self.metadata_address(mode), METADATA_STRIDE)

    def receiver_words(self, mode: int) -> Tuple[int, ...]:
        return self.record_words(self.receiver_address(mode), RECEIVER_STRIDE)

    def sensor_register(self, mode: int, register: int) -> int:
        index = self.register_index[register]
        return self.word(self.sensor_address(mode) + 4 + index * 4)

    def sensor_register_address(self, mode: int, register: int) -> int:
        return self.sensor_address(mode) + 4 + self.register_index[register] * 4


def exact_fps(hmax: int, tail: int, vmax: int) -> float:
    return 72_000_000 / (hmax * (vmax - 1) + tail)


def decode_timing(words: Sequence[int]) -> Dict[str, object]:
    w0, w1, w2, w3 = words[1:5]
    hmax, tail = w0 & 0xFFFF, w0 >> 16
    vmax, x = w1 & 0xFFFF, w1 >> 16
    y, x_end = w2 >> 16, w2 & 0xFFFF
    y_end = w3 & 0xFFFF
    frame_cycles = hmax * (vmax - 1) + tail
    return {
        "hmax": hmax,
        "tail": tail,
        "vmax": vmax,
        "input_window": {"x": x, "y": y, "x_end": x_end, "y_end": y_end},
        "frame_cycles": frame_cycles,
        "fps": 72_000_000 / frame_cycles,
    }


def _sensor_delta(firmware: Firmware, one_x: int, two_x: int) -> Dict[int, Tuple[int, int]]:
    result: Dict[int, Tuple[int, int]] = {}
    for register in firmware.registers:
        old = firmware.sensor_register(one_x, register)
        new = firmware.sensor_register(two_x, register)
        if old != new:
            result[register] = (old, new)
    return result


def validate_reduction_evidence(firmware: Firmware) -> Dict[str, object]:
    deltas = {
        f"M{one_x}->M{two_x}": _sensor_delta(firmware, one_x, two_x)
        for one_x, two_x in Q12_1X_TO_2X_SIBLINGS
    }
    common = set.intersection(*(set(delta) for delta in deltas.values()))
    expected = {0x0001, *PROVEN_2X_CORE}
    if common != expected:
        raise AssertionError(
            f"Q12 sibling intersection {sorted(common)} != {sorted(expected)}"
        )
    for register in common:
        transitions = {delta[register] for delta in deltas.values()}
        if len(transitions) != 1:
            raise AssertionError(
                f"reg 0x{register:04X} has inconsistent sibling transitions: "
                f"{transitions}"
            )
    if next(iter({delta[0x0001] for delta in deltas.values()})) != (
        RAW12_1X_MODE_CODE,
        RAW12_2X_MODE_CODE,
    ):
        raise AssertionError("unexpected Q12 1x->2x reg 0x0001 transition")
    return {
        "sibling_pairs": [list(pair) for pair in Q12_1X_TO_2X_SIBLINGS],
        "common_delta_count_including_selector": len(common),
        "proven_2x_core_count_excluding_selector": len(PROVEN_2X_CORE),
        "common_registers": [f"0x{register:04X}" for register in sorted(common)],
        "selector_transition": "0x2A -> 0x39 (RAW12 only)",
    }


def validate_raw14_mode_code(candidate: int) -> None:
    if candidate == RAW12_2X_MODE_CODE:
        raise ValueError("0x39 is the stock RAW12+2x selector, not RAW14+2x")
    if candidate == RAW14_1X_MODE_CODE:
        raise ValueError("0x29 is the stock RAW14+1x selector, not RAW14+2x")
    raise ValueError(
        f"0x{candidate:02X} has no RAW14+2x precedent; executable hybrid plans "
        "remain disabled"
    )


def _patch_if_changed(
    patches: List[Patch],
    firmware: Firmware,
    address: int,
    replacement: int,
    region: str,
    reason: str,
    confidence: str = "confirmed",
) -> None:
    expected = firmware.word(address)
    if expected != replacement:
        patches.append(
            Patch(address, expected, replacement, region, reason, confidence)
        )


def _reference_delta_public(firmware: Firmware, delta: Patch) -> Dict[str, object]:
    """Return a symbolic ROM-table delta, never a live-memory write record."""

    if delta.region == "M141 sensor row":
        base = firmware.sensor_address(M141) + 4
        index, remainder = divmod(delta.address - base, 4)
        if remainder or not 0 <= index < len(firmware.registers):
            raise AssertionError("sensor delta is outside M141")
        field = f"reg 0x{firmware.registers[index]:04X}"
        table = "sensor"
    elif delta.region == "M141 metadata":
        field = f"+0x{delta.address - firmware.metadata_address(M141):02X}"
        table = "metadata"
    elif delta.region == "M141 timing":
        field = f"+0x{delta.address - firmware.timing_address(M141):02X}"
        table = "timing"
    elif delta.region == "M141 receiver":
        field = f"+0x{delta.address - firmware.receiver_address(M141):02X}"
        table = "receiver"
    else:
        raise AssertionError(f"unexpected reference-delta region {delta.region}")
    return {
        "table": table,
        "base_mode": "M141",
        "field": field,
        "stock": f"0x{delta.expected:08X}",
        "reference": f"0x{delta.replacement:08X}",
        "reason": delta.reason,
        "confidence": delta.confidence,
    }


def raw14_packing_model(width: int, height: int) -> Dict[str, object]:
    """Source-derived model of ``FUN_c0630e90`` RAW14 pitch outputs.

    The primary path stores a floor-divided 32-bit pitch.  Width 3032 therefore
    describes 5306 packed bytes but programs only 5304, losing two bytes per
    row.  The 3024 record width is exact and follows the existing 16-pixel
    alignment rule.  The secondary pitch is the 32-byte-aligned row expressed
    in 64-bit units.
    """

    if width <= 0 or height <= 0:
        raise ValueError("RAW14 dimensions must be positive")
    row_bits = width * 14
    if row_bits % 8:
        raise ValueError("RAW14 row is not byte-addressable")
    packed_row_bytes = row_bits // 8
    primary_pitch_dwords = row_bits // 32
    primary_pitch_bytes = primary_pitch_dwords * 4
    truncated_bytes = packed_row_bytes - primary_pitch_bytes
    aligned_row_bytes = (packed_row_bytes + 31) & ~31
    secondary_pitch_qwords = aligned_row_bytes // 8
    safe = width % 16 == 0 and truncated_bytes == 0
    return {
        "width": width,
        "height": height,
        "packed_row_bytes": packed_row_bytes,
        "packed_frame_bytes": packed_row_bytes * height,
        "primary_pitch_dwords": primary_pitch_dwords,
        "primary_pitch_dwords_hex": f"0x{primary_pitch_dwords:X}",
        "primary_pitch_bytes": primary_pitch_bytes,
        "secondary_pitch_qwords": secondary_pitch_qwords,
        "secondary_pitch_qwords_hex": f"0x{secondary_pitch_qwords:X}",
        "secondary_pitch_bytes": aligned_row_bytes,
        "dma_selector": RAW14_DMA_SELECTOR,
        "width_multiple_of_16": width % 16 == 0,
        "primary_truncated_bytes_per_row": truncated_bytes,
        "accepted": safe,
        "rejection": (
            None
            if safe
            else "primary 32-bit pitch truncates the RAW14 row or width is not 16-pixel aligned"
        ),
    }


def require_safe_raw14_width(width: int, height: int) -> Dict[str, object]:
    model = raw14_packing_model(width, height)
    if not model["accepted"]:
        raise ValueError(
            f"RAW14 {width}x{height} is unsafe: {model['rejection']} "
            f"({model['primary_truncated_bytes_per_row']} truncated bytes/row)"
        )
    return model


def q12_control_report(firmware: Firmware, stage: str = "q12_control_2997") -> Dict[str, object]:
    if stage not in {"q12_control_18", "q12_control_2997"}:
        raise ValueError(stage)
    stock = firmware.timing_words(M143)
    if stage == "q12_control_18":
        desired = stock
    else:
        desired = (
            M143,
            TARGET_TIMING_W0,
            TARGET_TIMING_W1,
            TARGET_WINDOW_W2,
            TARGET_WINDOW_W3,
            *stock[5:],
        )
    timing_fields = []
    for offset in range(4, 20, 4):
        index = offset // 4
        timing_fields.append(
            {
                "field": f"timing-row +0x{offset:02X}",
                "stock": f"0x{stock[index]:08X}",
                "reference": f"0x{desired[index]:08X}",
                "changed": stock[index] != desired[index],
            }
        )

    return {
        "stage": stage,
        "status": "BLOCKED_REFERENCE_ONLY",
        "armable": False,
        "scope": "reference_emulator_only",
        "mutation_output": False,
        "camera_touched": False,
        "prerequisite": (
            None
            if stage == "q12_control_18"
            else "q12_control_18 passes in the bounded one-frame RAM sink"
        ),
        "purpose": (
            "Validate the all-stock continuous-family M143 2x sensor/receiver path "
            + (
                "at its stock 18.001530p timing"
                if stage == "q12_control_18"
                else "at exact 30000/1001 timing"
            )
            + " without mixing RAW12 and RAW14. This is not evidence of RAW14+2x."
        ),
        "candidate_base": (
            "stock M143 RAW12 2x at 18.001530p"
            if stage == "q12_control_18"
            else "stock M143 RAW12 2x with M6-derived exact-30000/1001 timing"
        ),
        "pipeline_identity": {
            "sensor_mode": "M143 stock RAW12 2x",
            "metadata_raw_enum": 0,
            "runtime_raw_plane_format": 7,
            "movie_gain_state": 7,
            "profile": 83,
        },
        "timing": decode_timing(desired),
        "unchanged": [
            "all 161 M143 sensor-register values",
            "all M143 metadata words",
            "all M143 receiver words",
            "global eRawBitType=0, p83 runtime RAW format=7, gain state=7",
        ],
        "reference_overlay": {
            "kind": "symbolic_timing_overlay",
            "base_mode": "M143",
            "fields": timing_fields,
            "live_addresses_included": False,
            "publication_and_restore": "not implemented or modeled",
        },
        "blockers": [
            {
                "id": "bounded_record_engine",
                "hard_gate": True,
                "required": "one-frame RAM sink, writer-off gate, watchdog, and cleanup",
            },
            {
                "id": "isolated_overlay_lifecycle",
                "hard_gate": True,
                "required": (
                    "implement and review a non-shared overlay plus atomic publish, "
                    "mode-exit cleanup, and forced-timeout restore"
                ),
            },
        ],
        "hardware_gate": [
            "a bounded one-frame RAM sink, independent watchdog, writer-off gate, and cleanup state machine exist",
            "the same harness passes a forced-timeout fault test without hanging",
            "an isolated overlay lifecycle is implemented; this report intentionally supplies no live write transaction",
            "user explicitly says the camera is free after being warned",
            "all later live-memory reads receive separate address-specific approval",
        ],
    }


def _hybrid_sensor_patches(firmware: Firmware) -> List[Patch]:
    patches: List[Patch] = []
    for register in PROVEN_2X_CORE:
        address = firmware.sensor_register_address(M141, register)
        expected = firmware.sensor_register(M141, register)
        replacement = firmware.sensor_register(M143, register)
        if expected == replacement:
            raise AssertionError(f"reg 0x{register:04X} is not a M141->M143 change")
        patches.append(
            Patch(
                address,
                expected,
                replacement,
                "M141 sensor row",
                f"Q12 sibling-proven 2x register 0x{register:04X}",
                "confirmed reduction delta; RAW14 combination unproven",
            )
        )
    return patches


def _hybrid_metadata_patches(firmware: Firmware, nominal_fps: int) -> List[Patch]:
    patches: List[Patch] = []
    m141 = firmware.metadata_address(M141)
    m143 = firmware.metadata_address(M143)
    geometry_offsets = (
        0x04,
        0x08,
        0x14,
        0x18,
        0x24,
        0x28,
        0x2C,
        0x30,
        0x34,
        0x38,
        0x44,
        0x48,
        0x4C,
        0x50,
    )
    for offset in geometry_offsets:
        _patch_if_changed(
            patches,
            firmware,
            m141 + offset,
            firmware.word(m143 + offset),
            "M141 metadata",
            f"copy M143 2x geometry field +0x{offset:02X}",
            "table precedent; RAW14 combination unproven",
        )
    _patch_if_changed(
        patches,
        firmware,
        m141 + 0x40,
        nominal_fps,
        "M141 metadata",
        "nominal fps class",
    )
    return patches


def _hybrid_timing_patches(firmware: Firmware, stage: str) -> List[Patch]:
    base = firmware.timing_address(M141)
    desired = {
        0x04: 0x038F038F if stage == "r14x2_18" else TARGET_TIMING_W0,
        0x08: 0x00041126 if stage == "r14x2_18" else TARGET_TIMING_W1,
        0x0C: TARGET_WINDOW_W2,
        0x10: TARGET_WINDOW_W3,
    }
    patches: List[Patch] = []
    for offset, value in desired.items():
        _patch_if_changed(
            patches,
            firmware,
            base + offset,
            value,
            "M141 timing",
            "M143 2x input window with M141 line timing"
            if stage == "r14x2_18"
            else "M143 2x input window with M6 exact-29.97 timing",
            "hybrid; not hardware-proven",
        )
    return patches


def _hybrid_receiver_patches(firmware: Firmware) -> List[Patch]:
    patches: List[Patch] = []
    m141 = firmware.receiver_address(M141)
    m143 = firmware.receiver_address(M143)
    for offset in range(4, RECEIVER_STRIDE, 4):
        _patch_if_changed(
            patches,
            firmware,
            m141 + offset,
            firmware.word(m143 + offset),
            "M141 receiver",
            f"copy M143 continuous-family receiver field +0x{offset:02X}",
            "best donor; RAW14 transport unproven",
        )
    return patches


def receiver_argument_model(record: bytes, config: bytes = bytes(0x3C)) -> bytes:
    """Model the 68-byte argument assembled by firmware FUN_c032d5e0.

    This is a source-level model, not instruction emulation.  It exists so the
    in-memory candidate can be compared with M143 even when Unicorn is absent.
    """

    if len(record) != RECEIVER_STRIDE:
        raise ValueError("receiver record must be 56 bytes")
    if len(config) < 0x3C:
        raise ValueError("config model must cover offsets through +0x38")
    out = bytearray(0x44)
    out[0] = 1
    mappings = (
        (0x02, 0x06, 2),
        (0x04, 0x08, 2),
        (0x06, 0x0A, 2),
        (0x08, 0x0C, 2),
        (0x0B, 0x19, 1),
        (0x11, 0x04, 1),
        (0x18, 0x10, 2),
        (0x1A, 0x1A, 2),
        (0x1C, 0x24, 2),
        (0x1E, 0x2E, 2),
        (0x20, 0x12, 2),
        (0x22, 0x1C, 2),
        (0x24, 0x26, 2),
        (0x26, 0x30, 2),
        (0x28, 0x14, 2),
        (0x2A, 0x1E, 2),
        (0x2C, 0x28, 2),
        (0x2E, 0x32, 2),
        (0x30, 0x16, 2),
        (0x32, 0x20, 2),
        (0x34, 0x2A, 2),
        (0x36, 0x34, 2),
        (0x38, 0x18, 1),
        (0x39, 0x22, 1),
        (0x3A, 0x2C, 1),
        (0x3B, 0x36, 1),
    )
    for destination, source, size in mappings:
        out[destination : destination + size] = record[source : source + size]
    config_mappings = (
        (0x0A, 0x2C, 1),
        (0x0C, 0x2E, 2),
        (0x0E, 0x30, 1),
        (0x0F, 0x31, 1),
        (0x10, 0x32, 1),
        (0x12, 0x33, 1),
        (0x14, 0x34, 2),
        (0x16, 0x36, 2),
        (0x3C, 0x38, 4),
    )
    for destination, source, size in config_mappings:
        out[destination : destination + size] = config[source : source + size]
    return bytes(out)


def _candidate_receiver_record(firmware: Firmware) -> bytes:
    base = firmware.receiver_address(M141)
    record = bytearray(firmware.bytes(base, RECEIVER_STRIDE))
    for patch in _hybrid_receiver_patches(firmware):
        struct.pack_into("<I", record, patch.address - base, patch.replacement)
    return bytes(record)


def hybrid_report(firmware: Firmware, stage: str) -> Dict[str, object]:
    if stage not in {"r14x2_18", "r14x2_2997"}:
        raise ValueError(stage)
    nominal = 18 if stage == "r14x2_18" else 30
    patches = [
        *_hybrid_sensor_patches(firmware),
        *_hybrid_metadata_patches(firmware, nominal),
        *_hybrid_timing_patches(firmware, stage),
        *_hybrid_receiver_patches(firmware),
    ]
    timing = list(firmware.timing_words(M141))
    for patch in _hybrid_timing_patches(firmware, stage):
        timing[(patch.address - firmware.timing_address(M141)) // 4] = patch.replacement

    candidate_receiver = _candidate_receiver_record(firmware)
    m143_receiver = firmware.bytes(firmware.receiver_address(M143), RECEIVER_STRIDE)
    receiver_matches = receiver_argument_model(candidate_receiver) == receiver_argument_model(
        m143_receiver
    )
    if not receiver_matches:
        raise AssertionError("candidate receiver argument does not match stock M143")

    packing = require_safe_raw14_width(RECORD_WIDTH, RECORD_HEIGHT)
    rejected_sensor_width = raw14_packing_model(3032, RECORD_HEIGHT)
    if (
        packing["primary_pitch_dwords"] != 0x52B
        or packing["secondary_pitch_qwords"] != 0x298
        or packing["dma_selector"] != 1
    ):
        raise AssertionError("3024-wide RAW14 pitch model drifted from known constants")
    if rejected_sensor_width["accepted"] or (
        rejected_sensor_width["primary_truncated_bytes_per_row"] != 2
    ):
        raise AssertionError("3032-wide RAW14 must remain rejected")
    packed14 = int(packing["packed_frame_bytes"])
    code8_capacity = RECORD_WIDTH * RECORD_HEIGHT * 2
    code7_capacity = RECORD_WIDTH * RECORD_HEIGHT * 12 // 8
    prerequisite = "physical RAW14+2x proof at 18p" if stage == "r14x2_2997" else None
    return {
        "stage": stage,
        "status": "BLOCKED_REFERENCE_ONLY",
        "armable": False,
        "scope": "reference_emulator_only",
        "mutation_output": False,
        "camera_touched": False,
        "prerequisite": prerequisite,
        "candidate_base": (
            "M141 RAW14 continuous 18.003196p timing + M143 2x geometry"
            if stage == "r14x2_18"
            else "M141 RAW14 identity + M143 2x geometry + M6-derived exact-30000/1001 timing"
        ),
        "timing": decode_timing(timing),
        "reference_delta_model": {
            "kind": "symbolic_rom_table_deltas",
            "live_addresses_included": False,
            "shared_table_write_transaction": False,
            "deltas": [_reference_delta_public(firmware, patch) for patch in patches],
        },
        "unresolved": [
            {
                "location": "M141 sensor row / reg 0x0001",
                "field": "sensor reg 0x0001",
                "stock": "0x29 (RAW14+1x)",
                "required": "unknown RAW14+2x selector",
                "hard_gate": True,
            },
            {
                "location": "M141 sensor row / reg 0x0016",
                "field": "sensor reg 0x0016",
                "stock": "0x19",
                "required": "retain provisionally; no universal depth/reduction meaning",
                "hard_gate": False,
            },
            {
                "location": "M141 metadata row / +0x60",
                "field": "metadata +0x60 readout cluster",
                "stock": "16 (RAW14+1x)",
                "required": "identify a valid RAW14+2x class; no published donor exists",
                "hard_gate": True,
            },
        ],
        "receiver_model": {
            "function": "source model of FUN_c032d5e0",
            "source_model_match": receiver_matches,
            "native_report_verified": False,
            "limitation": "table/packing only; no electrical or RAW14 transport behavior",
        },
        "record_pipeline": {
            "sensor_input": [3032, 2012],
            "record_plane": [RECORD_WIDTH, RECORD_HEIGHT],
            "active_crop": [ACTIVE_WIDTH, ACTIVE_HEIGHT],
            "packed14_bytes_per_frame": packed14,
            "format_code_8_payload_capacity": code8_capacity,
            "format_code_8_allocator_bytes": code8_capacity + 24,
            "format_code_7_payload_capacity": code7_capacity,
            "format_code_7_allocator_bytes": code7_capacity + 24,
            "format_code_7_payload_shortfall": packed14 - code7_capacity,
            "raw14_packing": packing,
            "rejected_3032_width": rejected_sensor_width,
            "required_runtime_values": {
                "capture_eRawBitType": 1,
                "capture_descriptor_+0x20": 1,
                "capture_descriptor_check": (
                    "the same runtime descriptor reads +0x20=1 at both packer callsites"
                ),
                "private_latch": 1,
                "runtime_profile_+0x80": RAW14_PREVIEW_FORMAT,
                "runtime_profile_+0x84": RAW14_RAW_PLANE_FORMAT,
                "raw14_dma_selector": RAW14_DMA_SELECTOR,
            },
        },
        "pipeline_blockers": [
            {
                "id": "enum1_canvas_selection",
                "hard_gate": True,
                "observed_behavior": (
                    "FUN_c043b828 special-cases enum 4 and enum 3 only; enum 1 "
                    "falls into the stock RAW12 picker table"
                ),
                "required": (
                    "a private enum1 profile/latch transaction whose runtime copy "
                    "keeps preview +0x80=10 and sets RAW plane +0x84=8"
                ),
            },
            {
                "id": "enum1_gain_dispatch",
                "hard_gate": True,
                "observed_behavior": (
                    "FUN_c039dde8 routes enum 1 to movie gain state 5 (movie_raw_8bit), "
                    "not the stock RAW12 movie state"
                ),
                "required": (
                    "an explicit RAW14 movie gain policy; ISO100 can inspect link "
                    "plumbing only and cannot validate dynamic range"
                ),
            },
        ],
        "hard_gates": [
            "find a sensor reg 0x0001 RAW14+2x value from primary evidence or a bounded discovery method",
            "resolve metadata +0x60 for RAW14+2x; retaining the M141 RAW14+1x class is not accepted as proof",
            "build a private enum1 picker/latch path; the stock picker routes enum1 through the RAW12 table",
            "set only the runtime p83 copy to preview format 10 and RAW-plane format 8; never patch static p83",
            "validate or override enum1 movie gain state 5 before REC",
            "build bounded frame telemetry or a no-writer dry-run; idle live view is not record-mode proof",
            "prove real low-bit entropy rather than a 12-bit payload labeled as 14-bit",
            "repair/forbid RAW14 playback before exposing the mode",
        ],
        "prohibited": [
            "0x39 as a RAW14+2x selector",
            "imager createraw (known unbounded wait/hang path)",
            "direct sensor I2C writes",
            "REC before the 18p stage proves physical RAW14+2x",
            "global static p83 modification",
            "3032-wide RAW14 record plane (primary pitch truncates two bytes per row)",
        ],
    }


def summary_report(firmware: Firmware) -> Dict[str, object]:
    evidence = validate_reduction_evidence(firmware)
    return {
        "tool": "RAW14+2x OpenGate offline experiment planner",
        "firmware": {
            "path": str(firmware.path),
            "size": len(firmware.image),
            "sha256": firmware.sha256,
        },
        "camera_touched": False,
        "evidence": evidence,
        "stages": {
            "q12_control_18": q12_control_report(firmware, "q12_control_18")["status"],
            "q12_control_2997": q12_control_report(firmware, "q12_control_2997")["status"],
            "r14x2_18": hybrid_report(firmware, "r14x2_18")["status"],
            "r14x2_2997": hybrid_report(firmware, "r14x2_2997")["status"],
        },
        "decision": (
            "No record-mode stage may touch hardware until the bounded one-frame "
            "RAM-sink harness passes stock and forced-timeout tests."
        ),
    }


def build_report(stage: str, firmware: Optional[Firmware] = None) -> Dict[str, object]:
    fw = firmware or Firmware()
    validate_reduction_evidence(fw)
    if stage == "summary":
        return summary_report(fw)
    if stage in {"q12_control_18", "q12_control_2997"}:
        return q12_control_report(fw, stage)
    return hybrid_report(fw, stage)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        nargs="?",
        default="summary",
        choices=(
            "summary",
            "q12_control_18",
            "q12_control_2997",
            "r14x2_18",
            "r14x2_2997",
        ),
    )
    parser.add_argument("--compact", action="store_true")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return exit 2 when the selected stage is intentionally blocked",
    )
    args = parser.parse_args(argv)
    report = build_report(args.stage)
    print(json.dumps(report, ensure_ascii=False, indent=None if args.compact else 2))
    if args.require_ready and str(report.get("status", "")).startswith("BLOCKED"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
