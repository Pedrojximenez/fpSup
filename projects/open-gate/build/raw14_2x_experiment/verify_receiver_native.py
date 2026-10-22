#!/usr/bin/env python3
"""Run the firmware's native receiver builder in Unicorn, without a camera.

Only memset, the sensor singleton lookup, and the two receiver-driver calls are
mocked.  The firmware's own C0320AB0 -> C0320F60 -> C032D5E0 path performs the
mode lookup and builds both 68-byte driver arguments.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

import raw14_2x_plan as plan

try:
    import unicorn
    from unicorn import (
        UC_ARCH_ARM,
        UC_HOOK_CODE,
        UC_HOOK_MEM_INVALID,
        UC_MODE_ARM,
        UC_PROT_READ,
        UC_PROT_EXEC,
        Uc,
    )
    from unicorn.arm_const import (
        UC_ARM_REG_LR,
        UC_ARM_REG_PC,
        UC_ARM_REG_R0,
        UC_ARM_REG_R1,
        UC_ARM_REG_R2,
        UC_ARM_REG_R3,
        UC_ARM_REG_SP,
    )
except ImportError as error:  # pragma: no cover - exercised only without optional dependency
    unicorn = None
    _UNICORN_IMPORT_ERROR = error
else:
    _UNICORN_IMPORT_ERROR = None


NATIVE_RECEIVER_BUILDER = 0xC0320AB0
NATIVE_MODE_LOOKUP = 0xC0320F60
NATIVE_MODE_LOOKUP_RETURN = 0xC0320AD0
MEMSET = 0xC0015058
SENSOR_SINGLETON = 0xC0322E48
RECEIVER_A = 0xC0635D40
RECEIVER_B = 0xC0635D58

OBJECT = 0x10000000
CONFIG = 0x10001000
STACK = 0x10010000
STOP = plan.ROM_BASE

# These bytes stand in only for per-camera runtime fields at config +0x2c..+0x38.
# Nonzero, non-repeating data ensures the model/native comparison covers those
# mappings instead of silently succeeding because both sides were zero-filled.
SYNTHETIC_CONFIG = bytes((0xA5 + index * 37) & 0xFF for index in range(0x3C))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def require_unicorn() -> None:
    if unicorn is None:  # pragma: no cover - depends on optional host package
        raise SystemExit(
            "SKIP: optional dependency 'unicorn' is not installed; "
            "the source-level receiver model remains covered by unit tests"
        ) from _UNICORN_IMPORT_ERROR


def validate_receiver_patches(firmware: plan.Firmware, mode: int, patches):
    """Validate an emulator-only overlay before it is copied into emulated ROM."""

    base = firmware.receiver_address(mode)
    validated = []
    seen = set()
    for patch in patches:
        if patch.address & 3:
            raise ValueError(f"unaligned receiver patch 0x{patch.address:08X}")
        if not base + 4 <= patch.address < base + plan.RECEIVER_STRIDE:
            raise ValueError(
                f"receiver patch 0x{patch.address:08X} is outside M{mode} non-ID fields"
            )
        if patch.address in seen:
            raise ValueError(f"duplicate receiver patch 0x{patch.address:08X}")
        seen.add(patch.address)
        actual = firmware.word(patch.address)
        if patch.expected != actual:
            raise ValueError(
                f"receiver patch 0x{patch.address:08X} expected "
                f"0x{patch.expected:08X}, firmware has 0x{actual:08X}"
            )
        if not 0 <= patch.replacement <= 0xFFFFFFFF:
            raise ValueError("receiver replacement is outside uint32")
        if patch.replacement == patch.expected:
            raise ValueError(f"no-op receiver patch 0x{patch.address:08X}")
        validated.append(patch)
    return tuple(validated)


def align_up(value: int, alignment: int = 0x1000) -> int:
    return (value + alignment - 1) & -alignment


def emulate(firmware: plan.Firmware, mode: int, receiver_patches=()):
    require_unicorn()
    if mode not in firmware.mode_index:
        raise ValueError(f"mode M{mode} is absent from the receiver table")
    expected_index = firmware.mode_index[mode]
    receiver_base = firmware.receiver_address(mode)
    if firmware.word(receiver_base) != mode:
        raise AssertionError(f"receiver row {expected_index} does not identify M{mode}")
    receiver_patches = validate_receiver_patches(firmware, mode, receiver_patches)

    machine = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    rom_size = align_up(len(firmware.image))
    machine.mem_map(plan.ROM_BASE, rom_size)
    machine.mem_write(plan.ROM_BASE, firmware.image)
    for patch in receiver_patches:
        machine.mem_write(patch.address, struct.pack("<I", patch.replacement))
        actual = struct.unpack("<I", machine.mem_read(patch.address, 4))[0]
        if actual != patch.replacement:
            raise AssertionError(f"emulator overlay readback failed at 0x{patch.address:08X}")
    machine.mem_protect(plan.ROM_BASE, rom_size, UC_PROT_READ | UC_PROT_EXEC)
    machine.mem_map(OBJECT, 0x2000)
    machine.mem_map(STACK, 0x4000)
    machine.mem_write(OBJECT, struct.pack("<I", CONFIG))
    machine.mem_write(CONFIG, SYNTHETIC_CONFIG)
    machine.mem_write(CONFIG + 0x40, struct.pack("<I", plan.RECEIVER_TABLE))
    machine.mem_write(CONFIG + 0x44, struct.pack("<I", plan.MODE_COUNT))

    calls = []
    lookup_entries = []
    lookup_returns = []

    def return_from_mock(result=0):
        machine.reg_write(UC_ARM_REG_R0, result)
        machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))

    def code_hook(_machine, address, _size, _data):
        if address == NATIVE_MODE_LOOKUP:
            lookup_entries.append(
                {
                    "object": machine.reg_read(UC_ARM_REG_R0),
                    "requested_mode": machine.reg_read(UC_ARM_REG_R1),
                }
            )
        elif address == NATIVE_MODE_LOOKUP_RETURN:
            lookup_returns.append(machine.reg_read(UC_ARM_REG_R0))
        elif address == MEMSET:
            destination = machine.reg_read(UC_ARM_REG_R0)
            value = machine.reg_read(UC_ARM_REG_R1) & 0xFF
            length = machine.reg_read(UC_ARM_REG_R2)
            machine.mem_write(destination, bytes([value]) * length)
            return_from_mock(destination)
        elif address == SENSOR_SINGLETON:
            return_from_mock(OBJECT)
        elif address in (RECEIVER_A, RECEIVER_B):
            channel = machine.reg_read(UC_ARM_REG_R0)
            pointer = machine.reg_read(UC_ARM_REG_R1)
            calls.append(
                {
                    "consumer": "A" if address == RECEIVER_A else "B",
                    "channel": channel,
                    "argument": bytes(machine.mem_read(pointer, 0x44)),
                }
            )
            return_from_mock(0)

    for address in (
        NATIVE_MODE_LOOKUP,
        NATIVE_MODE_LOOKUP_RETURN,
        MEMSET,
        SENSOR_SINGLETON,
        RECEIVER_A,
        RECEIVER_B,
    ):
        machine.hook_add(UC_HOOK_CODE, code_hook, begin=address, end=address)

    def invalid_hook(_machine, access, address, size, value, _data):
        raise AssertionError(
            f"invalid emulated memory access type={access} "
            f"address=0x{address:08X} size={size} value=0x{value:X}"
        )

    machine.hook_add(UC_HOOK_MEM_INVALID, invalid_hook)
    machine.reg_write(UC_ARM_REG_SP, STACK + 0x3FF0)
    machine.reg_write(UC_ARM_REG_LR, STOP)
    for register, value in zip(
        (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3),
        (OBJECT, mode, 1, 0),
    ):
        machine.reg_write(register, value)
    machine.emu_start(NATIVE_RECEIVER_BUILDER, STOP, count=20_000)
    if machine.reg_read(UC_ARM_REG_PC) != STOP:
        raise AssertionError(f"native builder stopped at 0x{machine.reg_read(UC_ARM_REG_PC):08X}")
    if [call["consumer"] for call in calls] != ["A", "B"]:
        raise AssertionError(f"unexpected receiver calls: {calls}")
    if lookup_entries != [{"object": OBJECT, "requested_mode": mode}]:
        raise AssertionError(f"native mode lookup entry mismatch: {lookup_entries}")
    if lookup_returns != [expected_index]:
        raise AssertionError(
            f"native lookup for M{mode} returned {lookup_returns}, expected [{expected_index}]"
        )
    return {
        "calls": calls,
        "lookup": {
            "requested_mode": mode,
            "expected_index": expected_index,
            "native_index": lookup_returns[0],
            "hit": True,
        },
    }


def main() -> int:
    firmware = plan.Firmware()
    native_m143 = emulate(firmware, plan.M143)
    receiver_patches = plan._hybrid_receiver_patches(firmware)
    candidate = emulate(firmware, plan.M141, receiver_patches)
    candidate_record = plan._candidate_receiver_record(firmware)
    stock_record = firmware.bytes(
        firmware.receiver_address(plan.M143), plan.RECEIVER_STRIDE
    )
    source_model = plan.receiver_argument_model(candidate_record, SYNTHETIC_CONFIG)
    for stock_call, candidate_call in zip(native_m143["calls"], candidate["calls"]):
        if stock_call["argument"] != candidate_call["argument"]:
            raise AssertionError(
                f"receiver {stock_call['consumer']} candidate differs from stock M143"
            )
        if candidate_call["argument"] != source_model:
            raise AssertionError(
                f"receiver {candidate_call['consumer']} differs from source-level model"
            )
    patch_fixture = [
        {
            "offset": patch.address - firmware.receiver_address(plan.M141),
            "expected": patch.expected,
            "replacement": patch.replacement,
        }
        for patch in receiver_patches
    ]
    inputs = {
        "firmware_sha256": firmware.sha256,
        "mode_csv_sha256": firmware.mode_csv_sha256,
        "register_order_sha256": firmware.register_order_sha256,
        "planner_sha256": sha256_path(Path(plan.__file__)),
        "verifier_sha256": sha256_path(Path(__file__)),
        "synthetic_config_sha256": sha256_bytes(SYNTHETIC_CONFIG),
        "stock_m143_receiver_record_sha256": sha256_bytes(stock_record),
        "candidate_m141_receiver_record_sha256": sha256_bytes(candidate_record),
        "receiver_patch_fixture_sha256": sha256_bytes(
            json.dumps(patch_fixture, sort_keys=True, separators=(",", ":")).encode()
        ),
    }
    bundle_sha256 = sha256_bytes(
        json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    )
    report = {
        "emulator": f"Unicorn {unicorn.__version__}",
        "native_function": "0xC0320AB0",
        "native_mode_lookup": "0xC0320F60",
        "inputs": inputs,
        "verification_bundle_sha256": bundle_sha256,
        "synthetic_config": {
            "kind": "deterministic nonzero emulator fixture; not a camera capture",
            "bytes": len(SYNTHETIC_CONFIG),
        },
        "cases": [native_m143["lookup"], candidate["lookup"]],
        "consumers": [
            {
                "name": call["consumer"],
                "channel": call["channel"],
                "argument_hex": call["argument"].hex(),
            }
            for call in candidate["calls"]
        ],
        "source_model_match": True,
        "native_report_verified": True,
        "result": (
            "PASS: native mode lookup hit the exact M143/M141 rows; under the same "
            "synthetic config, both consumers' 68-byte arguments match the source "
            "model and the candidate receiver-derived bytes match stock M143"
        ),
        "limitations": [
            "Config-derived bytes use a synthetic fixture, not stock or camera-captured state.",
            "Only receiver lookup and argument construction are exercised.",
            "Sensor writes, timing, input windows, electrical link, transition concurrency, RAW packing, allocation, and writer behavior are not emulated.",
        ],
        "camera_touched": False,
    }
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
