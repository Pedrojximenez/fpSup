#!/usr/bin/env python3
"""Native p429 FieldAngle -> experimental ARM core -> RAW descriptor.

Offline only: no transport or camera access.  The pinned firmware constructs
the actual FieldAngle object and descriptor.  Only heap allocation and logging
are mocked.  The settings/profile selector above C04362B8 in C0437140 is NOT
emulated: p429 is an explicit input, and the two request-context words are zero.
This proves the descriptor for that profile, not that any camera state selects
it, nor that a live camera can allocate or record the resulting frame.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from og4k_sizes import CANVAS_BYTES, NativeSizing, SizingError, load_firmware

ROOT = Path(__file__).resolve().parents[4]
CORE_DIR = ROOT / "fpSup/opengate/og4k"
sys.path.insert(0, str(CORE_DIR))
import core_build

DESCRIPTOR_BYTES = 0xC0


def words(blob: bytes) -> tuple[int, ...]:
    return struct.unpack(f"<{len(blob) // 4}I", blob)


class NativeDescriptor(NativeSizing):
    """Preserve all geometry/format instructions and use guarded private RAM."""

    CODE = 0x11000000
    RESULT = NativeSizing.RAM + 0x3000
    CONTEXT = NativeSizing.RAM + 0x4000
    FRAME_DESC = NativeSizing.RAM + 0x5000
    ANGLE_BYTES = 0x16C

    def __init__(self, image: bytes):
        super().__init__(image)
        self.blob, self.symbols = core_build.build()
        self.uc.mem_map(self.CODE, 0x1000)
        self.uc.mem_write(self.CODE, self.blob)
        self.uc.mem_protect(self.CODE, 0x1000,
                            self.unicorn.UC_PROT_READ | self.unicorn.UC_PROT_EXEC)
        self.mock_calls = []
        self.native_entries = set()
        self.uc.hook_add(self.unicorn.UC_HOOK_CODE, self._instruction)

    def _instruction(self, uc, address, size, data):
        self.native_entries.add(address)
        allocation = {
            0xC0439C10: (self.ANGLE_BYTES, self.OBJ),
            0xC0438980: (DESCRIPTOR_BYTES, self.DESC),
        }
        if address in allocation:
            expected, pointer = allocation[address]
            requested = uc.reg_read(self.arm.UC_ARM_REG_R0)
            if requested != expected:
                raise SizingError(f"unexpected object allocation: {requested:#x}")
            result = pointer
        elif address in (0xC0019DC0, 0xC001A0D8):
            result = 0  # Logger handle and logger emission only.
        else:
            return
        self.mock_calls.append(address)
        uc.reg_write(self.arm.UC_ARM_REG_R0, result)
        uc.reg_write(self.arm.UC_ARM_REG_PC, uc.reg_read(self.arm.UC_ARM_REG_LR))

    def _native_call(self, entry, args, writes=()):
        self.uc.reg_write(self.arm.UC_ARM_REG_CPSR, 0x13)
        return self._run(entry, args, writes=writes)

    def construct(self, *, candidate=True) -> bytes:
        """Return the real 0xC0 native descriptor, with stock preview intact."""
        self.mock_calls = []
        self.native_entries = set()
        self.uc.mem_write(self.OBJ, bytes(self.ANGLE_BYTES))
        self.uc.mem_write(self.DESC, bytes(DESCRIPTOR_BYTES))
        self.uc.mem_write(self.RESULT, bytes(8))
        self.uc.mem_write(self.CONTEXT, bytes(9 * 4))
        # C0437140 calls this factory after its settings-driven profile lookup.
        self._native_call(0xC04362B8, (self.RESULT, 429, 3),
                          ((self.OBJ, self.OBJ + self.ANGLE_BYTES),
                           (self.RESULT, self.RESULT + 8)))
        if words(bytes(self.uc.mem_read(self.RESULT, 4)))[0] != self.OBJ:
            raise SizingError("FieldAngle factory did not return its allocated object")
        if words(bytes(self.uc.mem_read(self.OBJ, 16))) != (
                429, self.OBJ + 0x5C, 0, 0):
            raise SizingError("native FieldAngle identity/default dimensions changed")
        self.stock_canvas = words(bytes(self.uc.mem_read(self.OBJ + 0x5C, CANVAS_BYTES)))
        if candidate:
            self.uc.mem_write(self.CONTEXT, struct.pack("<9I", *core_build.RECORD_REQUEST))
            result = self._native_call(self.CODE + self.symbols["record_canvas"],
                                       (self.OBJ + 0x5C, self.CONTEXT),
                                       ((self.OBJ + 0x5C, self.OBJ + 0x5C + CANVAS_BYTES),))
            if result != 1:
                raise SizingError("actual ARM record_canvas did not accept native p429")
        self.canvas = words(bytes(self.uc.mem_read(self.OBJ + 0x5C, CANVAS_BYTES)))
        self.uc.mem_write(self.CONTEXT, bytes(8))
        # Original unique-object wrapper includes C0438A78 -> C0438018.
        self._native_call(0xC0438B60, (self.RESULT + 4, self.OBJ, self.CONTEXT),
                          ((self.DESC, self.DESC + DESCRIPTOR_BYTES),
                           (self.RESULT, self.RESULT + 8)))
        if words(bytes(self.uc.mem_read(self.RESULT + 4, 4)))[0] != self.DESC:
            raise SizingError("RAW factory did not return its allocated object")
        self.descriptor = bytes(self.uc.mem_read(self.DESC, DESCRIPTOR_BYTES))
        return self.descriptor

    def recording_copy(self) -> bytes:
        """Run the original C0374268 frame-descriptor copy, C02E5B78."""
        self.uc.mem_write(self.FRAME_DESC, bytes(0x48))
        self._native_call(0xC02E5B78, (self.FRAME_DESC, self.DESC),
                          ((self.FRAME_DESC, self.FRAME_DESC + 0x48),))
        return bytes(self.uc.mem_read(self.FRAME_DESC, 0x48))

    def strip_bytes(self) -> int:
        return self._native_call(0xC03D9630, (self.DESC,))


def native_record_descriptor(image: bytes, *, candidate: bool = True) -> bytes:
    """Public allocator-fixture API; no synthetic width/height/format fields."""
    return NativeDescriptor(image).construct(candidate=candidate)


def describe(machine: NativeDescriptor, descriptor: bytes) -> dict:
    d = words(descriptor)
    return {
        "raster": list(d[0:2]),
        "active_origin": list(d[6:8]),
        "format": d[8],
        "raw_zoom": list(d[18:20]),
        "preview_descriptor_hex": descriptor[0x58:0xB0].hex(),
        "profile": d[46],
        "strip_byte_count_native": machine.strip_bytes(),
        "descriptor_sha256": hashlib.sha256(descriptor).hexdigest(),
        "descriptor_hex": descriptor.hex(),
        "mocked_entries": [f"0x{x:08X}" for x in machine.mock_calls],
        "native_chain_entries": [f"0x{x:08X}" for x in (
            0xC04362B8, 0xC0439668, 0xC0439740, 0xC0439CC8,
            0xC043A158, 0xC0439D18, 0xC0438B60, 0xC0438A78,
            0xC0438018, 0xC04381E8, 0xC0438268, 0xC03D9630)
            if x in machine.native_entries],
    }


def verify(image: bytes) -> dict:
    stock = NativeDescriptor(image)
    stock_desc = stock.construct(candidate=False)
    changed = NativeDescriptor(image)
    og_desc = changed.construct(candidate=True)
    if stock_desc[0x58:0xB0] != og_desc[0x58:0xB0]:
        raise SizingError("record_canvas unexpectedly changed the native preview descriptor")
    expected_offsets = {0x00, 0x04, 0x24, 0x2C, 0x64, 0xD4, 0xDC, 0xE4}
    actual_offsets = {4 * i for i, (a, b) in enumerate(zip(changed.stock_canvas, changed.canvas))
                      if a != b}
    if actual_offsets != expected_offsets:
        raise SizingError(f"native canvas write set differs: {actual_offsets}")
    for machine, descriptor, dimensions, zoom, strip in (
        (stock, stock_desc, (3856, 2170), (1600, 1600), 12_551_292),
        (changed, og_desc, (4016, 2676), (1536, 1536), 16_120_232),
    ):
        d = words(descriptor)
        if d[0:2] != dimensions or d[6:8] != (8, 5) or d[8] != 0:
            raise SizingError("native RAW dimensions/crop/format mismatch")
        if d[18:20] != zoom or d[46] != 429 or machine.strip_bytes() != strip:
            raise SizingError("native RAW zoom/profile/bytes mismatch")
        if machine.recording_copy() != descriptor[:0x48]:
            raise SizingError("recording descriptor copy altered the native RAW descriptor")
    return {
        "firmware_sha256": hashlib.sha256(image).hexdigest(),
        "core_sha256": hashlib.sha256(changed.blob).hexdigest(),
        "camera_accessed": False,
        "camera_ready": False,
        "profile_selection_emulated": False,
        "request_context_words": [0, 0],
        "limits": ["p429 is explicit, not selected by settings/profile dispatch",
                   "heap objects and logger are mocked; live RAW pool capacity is not proven",
                   "no receiver, sensor, recording, DMA, writer or image-quality measurement"],
        "preview_unchanged": True,
        "canvas_changed_offsets": [f"0x{x:02X}" for x in sorted(actual_offsets)],
        "stock": describe(stock, stock_desc),
        "og4k": describe(changed, og_desc),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = verify(load_firmware())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Native FieldAngle -> actual ARM record_canvas -> native RAW descriptor: PASS")
        print("Stock: 3856x2170 RAW12; candidate: 4016x2676 RAW12, origin 8,5, zoom 1536/1536")
        print("Native candidate strip bytes: 16,120,232; preview unchanged")
        print("Offline only; settings/profile selection and live-camera capacity are NOT proven")


if __name__ == "__main__":
    main()
