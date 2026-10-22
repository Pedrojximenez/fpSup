#!/usr/bin/env python3
"""Offline OG4K sizing evidence from pinned fp V5.02 firmware.

No camera transport is imported. The native checks execute original ARM/Thumb
instructions in Unicorn with read-only firmware and bounded private RAM.
FieldAngle sizing is not the recording pixel allocator: stock p429 +0x3C=0
explicitly excludes the recording plane from its total. The report preserves
that distinction and never claims that a live camera has sufficient RAM.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import warnings


ROOT = Path(__file__).resolve().parents[4]
FIRMWARE = ROOT / "out/MAIN_c0000000.bin"
SIZE_MODEL = ROOT / "projects/open-gate/build/sizesim.py"
IMAGE_BASE = 0xC0000000
SHA256 = "92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4"
PROFILE_MAP = 0xC0BD05D4
PROFILE_COUNT = 506
ROW_COUNT = 306  # Column stride 0x4C8 / sizeof(uint32_t).
CANVAS_BYTES = 0x10C  # 65 table columns plus two constants, C0439D18.
RASTER = (4016, 2676)
ACTIVE = (4000, 2666)
RAW_OVERRIDES = {
    0x00: 4016, 0x04: 2676,
    0x24: 4000, 0x2C: 2666,
    0xDC: 4016, 0xE4: 2676,
    0x64: 1536, 0xD4: 1536,
}
RAW_STOCK = {
    0x00: 3856, 0x04: 2170,
    0x24: 3840, 0x2C: 2160,
    0xDC: 3856, 0xE4: 2170,
    0x64: 1600, 0xD4: 1600,
}
RAW_COLUMN_ADDRESSES = {
    0x00: 0xC0BE3F54, 0x04: 0xC0BE441C,
    0x24: 0xC0BE2C34, 0x2C: 0xC0BE30FC,
    0xDC: 0xC0BE35C4, 0xE4: 0xC0BE3A8C,
    0x64: 0xC0BE1914, 0xD4: 0xC0BE1DDC,
}
PLAYBACK_OVERRIDES = {
    0x1C: 2,
    0x0C: 4016, 0x10: 2676, 0xD8: 4016, 0xE0: 2676,
    0x20: 4000, 0x28: 2666, 0xF4: 4016, 0xF8: 2676,
    0x60: 1024, 0xD0: 1024, 0x64: 1024, 0xD4: 1024,
}


class SizingError(RuntimeError):
    pass


def load_firmware(path: Path = FIRMWARE) -> bytes:
    image = path.read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    if digest != SHA256:
        raise SizingError(f"firmware SHA-256 mismatch: {digest}")
    return image


def word(image: bytes, address: int) -> int:
    offset = address - IMAGE_BASE
    if offset < 0 or offset + 4 > len(image):
        raise SizingError(f"word outside firmware: 0x{address:08X}")
    return struct.unpack_from("<I", image, offset)[0]


def get(canvas: list[int], offset: int) -> int:
    return canvas[offset // 4]


def apply_overrides(canvas: list[int], overrides: dict[int, int]) -> list[int]:
    updated = list(canvas)
    for offset, value in overrides.items():
        if offset < 0 or offset >= CANVAS_BYTES or offset % 4:
            raise SizingError(f"invalid canvas offset 0x{offset:X}")
        updated[offset // 4] = value
    return updated


def load_model():
    """Reuse the existing decompilation model, then independently cross-check it."""
    spec = importlib.util.spec_from_file_location("og4k_stock_sizesim", SIZE_MODEL)
    if spec is None or spec.loader is None:
        raise SizingError("cannot load existing FieldAngle arithmetic model")
    module = importlib.util.module_from_spec(spec)
    # The existing module uses a one-expression open().read(); keep that file
    # unchanged, including suppressing only its harmless ResourceWarning.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        spec.loader.exec_module(module)
    if hashlib.sha256(module.IMG).hexdigest() != SHA256:
        raise SizingError("FieldAngle arithmetic model loaded an unpinned image")
    return module


def profile_canvas(image: bytes, model, profile: int) -> list[int]:
    if not 0 <= profile < PROFILE_COUNT:
        raise SizingError("profile outside pinned table")
    row = word(image, PROFILE_MAP + profile * 4)
    if row >= ROW_COUNT:
        raise SizingError(f"profile {profile} has no canvas row (0x{row:08X})")
    return [word(image, base + row * 4) for base in model.COL] + [0x17B0, 0xFCA]


def check_p429_columns(image: bytes, model) -> None:
    row = word(image, PROFILE_MAP + 429 * 4)
    if row != 286:
        raise SizingError(f"p429 maps to unexpected row {row}")
    for offset, address in RAW_COLUMN_ADDRESSES.items():
        if model.COL[offset // 4] + row * 4 != address:
            raise SizingError(f"column mismatch at canvas+0x{offset:02X}")
        if word(image, address) != RAW_STOCK[offset]:
            raise SizingError(f"stock value mismatch at 0x{address:08X}")


def raw12_bytes(width: int, height: int) -> dict[str, int]:
    """Format 0 path of C03D9630 -> C01AAA30 -> C0135D40/C0135DB8."""
    if width < 0 or height < 0:
        raise SizingError("negative dimensions")
    row = ((width * 3 // 2) + 3) & ~3
    final_width = ((width + 11) // 12) * 12
    final_row = ((final_width * 3 // 2) + 3) & ~3
    payload = (height - 1) * row + final_row if width and height else 0
    if payload >= 0x80000000:
        raise SizingError("RAW byte count exceeds signed firmware arithmetic range")
    return {
        "packed_pixels": width * height * 3 // 2,
        "row_stride": row,
        "final_row_bytes": final_row,
        "strip_byte_counts": payload,
        "write_payload_512": (payload + 511) & ~511,
    }


def playback_file_capacity(file_bytes: int) -> int:
    """Exact C05C2D10 request; pool availability/count are not inferred."""
    if file_bytes < 0 or file_bytes > 0xFFFFFFFF - 0x1FFF:
        raise SizingError("invalid playback file byte count")
    return (file_bytes + 0x1FFF) & ~0xFFF


def canvas_mismatches(canvas: list[int]) -> list[str]:
    errors = []
    base = get(canvas, 0x00), get(canvas, 0x04)
    override = get(canvas, 0xDC) or base[0], get(canvas, 0xE4) or base[1]
    if base != override:
        errors.append(f"RAW allocation dimensions {base} differ from getters {override}")
    if base != RASTER:
        errors.append(f"RAW dimensions {base} differ from OG4K {RASTER}")
    if (get(canvas, 0x24), get(canvas, 0x2C)) != ACTIVE:
        errors.append("active crop differs from 4000x2666")
    if (get(canvas, 0x64), get(canvas, 0xD4)) != (1536, 1536):
        errors.append("RAW RWZM differs from 1536/1536")
    if (get(canvas, 0x80), get(canvas, 0x84)) != (7, 7):
        errors.append("candidate does not retain stock RAW12 plane formats")
    return errors


class NativeSizing:
    """Bounded emulator, never a hardware transport.

    C0435588 runs only through its completed arithmetic at C043566C; execution
    stops before its logging call and reads r5. No sizing function is stubbed.
    Writes are allowed only to stack, object, descriptor, or gather destination.
    """

    RAM = 0x10000000
    RAM_BYTES = 0x10000
    OBJ = RAM
    CANVAS = RAM + 0x1000
    DESC = RAM + 0x2000
    STACK = RAM + 0xC000
    STOP = IMAGE_BASE

    def __init__(self, image: bytes):
        import unicorn
        import unicorn.arm_const as arm
        if hashlib.sha256(image).hexdigest() != SHA256:
            raise SizingError("native emulator requires pinned firmware")
        self.arm, self.unicorn = arm, unicorn
        self.uc = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_ARM)
        mapped = (len(image) + 4095) & ~4095
        self.uc.mem_map(IMAGE_BASE, mapped)
        self.uc.mem_write(IMAGE_BASE, image)
        self.uc.mem_protect(IMAGE_BASE, mapped, unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC)
        self.uc.mem_map(self.RAM, self.RAM_BYTES)
        self.uc.reg_write(arm.UC_ARM_REG_C1_C0_2, 0xF << 20)
        self.uc.reg_write(arm.UC_ARM_REG_FPEXC, 1 << 30)
        self.allowed = []
        self.writes = []
        self.uc.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._guard_write)

    def _guard_write(self, uc, access, address, size, value, data):
        if not any(begin <= address and address + size <= end for begin, end in self.allowed):
            raise SizingError(f"native write outside allowed region: 0x{address:08X}+{size}")
        self.writes.append((address, size))

    def _run(self, entry: int, args: tuple[int, ...], *, end=None, writes=()):
        arm = self.arm
        for reg, value in zip((arm.UC_ARM_REG_R0, arm.UC_ARM_REG_R1,
                               arm.UC_ARM_REG_R2, arm.UC_ARM_REG_R3), args):
            self.uc.reg_write(reg, value)
        self.uc.reg_write(arm.UC_ARM_REG_SP, self.RAM + self.RAM_BYTES - 16)
        self.uc.reg_write(arm.UC_ARM_REG_LR, self.STOP)
        self.allowed = [(self.STACK, self.RAM + self.RAM_BYTES), *writes]
        self.writes = []
        stop = self.STOP if end is None else end
        self.uc.emu_start(entry, stop, count=50_000)
        if self.uc.reg_read(arm.UC_ARM_REG_PC) != stop:
            raise SizingError("native instruction bound exceeded")
        return self.uc.reg_read(arm.UC_ARM_REG_R0)

    def gather(self, row: int) -> list[int]:
        if not 0 <= row < ROW_COUNT:
            raise SizingError("native gather row outside pinned columns")
        self.uc.mem_write(self.CANVAS, bytes(CANVAS_BYTES))
        self._run(0xC0439D18, (self.CANVAS, row),
                  writes=((self.CANVAS, self.CANVAS + CANVAS_BYTES),))
        return list(struct.unpack("<67I", self.uc.mem_read(self.CANVAS, CANVAS_BYTES)))

    def raw12(self, width: int, height: int) -> int:
        desc = bytearray(0x48)
        struct.pack_into("<II", desc, 0, width, height)
        struct.pack_into("<I", desc, 0x20, 0)  # stock 12-bit enum.
        self.uc.mem_write(self.DESC, bytes(desc))
        return self._run(0xC03D9630, (self.DESC,))

    def _set_canvas(self, canvas: list[int], dims: tuple[int, int]):
        self.uc.mem_write(self.CANVAS, struct.pack("<67I", *canvas))
        obj = bytearray(0x170)
        struct.pack_into("<4I", obj, 0, 429, self.CANVAS, *dims)
        self.uc.mem_write(self.OBJ, bytes(obj))

    def plane(self, canvas: list[int], which: int) -> int:
        self._set_canvas(canvas, (1024, 682))
        return self._run(0xC04356B0, (self.OBJ, which))

    def fieldangle(self, canvas: list[int], dims: tuple[int, int]) -> dict:
        if min(dims) <= 0:
            raise SizingError("FieldAngle caller dimensions must be positive")
        self._set_canvas(canvas, dims)
        self._run(0xC0435428, (self.OBJ,), writes=((self.OBJ + 0x10, self.OBJ + 0x58),))
        fields = struct.unpack("<22I", self.uc.mem_read(self.OBJ, 0x58))
        self._run(0xC0435588, (self.OBJ,), end=0xC043566C)
        total = self.uc.reg_read(self.arm.UC_ARM_REG_R5)
        return {
            "total_bytes": total,
            "preview_count": fields[4], "preview_plane_bytes": fields[5],
            "recording_count_in_total": fields[6], "recording_plane_in_total": fields[7],
            "decoder_bytes": fields[9], "display_plane_bytes": fields[19],
        }


def build_report(*, native: bool = True) -> dict:
    image = load_firmware()
    model = load_model()
    check_p429_columns(image, model)
    stock = profile_canvas(image, model, 429)
    record = apply_overrides(stock, RAW_OVERRIDES)
    playback_stock = profile_canvas(image, model, 71)
    playback = apply_overrides(playback_stock, PLAYBACK_OVERRIDES)
    errors = canvas_mismatches(record)
    if errors:
        raise SizingError("; ".join(errors))
    raw = raw12_bytes(*RASTER)
    emulator = NativeSizing(image) if native else None
    reports = []
    for label, canvas in (("stock_p429", stock), ("og4k_p429_raw_overrides", record),
                           ("stock_p71", playback_stock), ("og4k_p71_playback", playback)):
        sizes = []
        for dims in ((1024, 682), (1620, 911), (1620, 1080)):
            arithmetic = model.total(canvas, *dims)
            result = emulator.fieldangle(canvas, dims) if emulator else {}
            if result and result["total_bytes"] != arithmetic:
                raise SizingError(f"native/model FieldAngle mismatch: {label}, {dims}")
            sizes.append({"caller_dimensions": dims, "arithmetic_total": arithmetic, "native": result})
        reports.append({"label": label, "raw_plane_helper": model.c04356b0(canvas, 1),
                        "canvas_3c": get(canvas, 0x3C), "sizes": sizes})
    if emulator:
        for pid in (429, 71, 73, 51):
            row = word(image, PROFILE_MAP + pid * 4)
            if emulator.gather(row) != profile_canvas(image, model, pid):
                raise SizingError(f"native gather mismatch: p{pid}")
        if emulator.raw12(*RASTER) != raw["strip_byte_counts"]:
            raise SizingError("native RAW callback mismatch")
        if emulator.plane(record, 1) != model.c04356b0(record, 1):
            raise SizingError("native RAW plane helper mismatch")
    assumed_header = 78_848
    assumed_file = assumed_header + raw["write_payload_512"]
    return {
        "firmware_sha256": SHA256,
        "verification": "original firmware arithmetic executed" if native else "arithmetic model only",
        "raster": RASTER, "active": ACTIVE, "raw12": raw,
        "canvas_offsets": {f"0x{k:02X}": v for k, v in RAW_OVERRIDES.items()},
        "fieldangle": reports,
        "conditional_file_example": {
            "assumed_header_bytes_not_verified_for_og4k": assumed_header,
            "file_bytes": assumed_file,
            "playback_capacity_per_frame": playback_file_capacity(assumed_file),
            "playback_descriptor_array": 0x6F090,
            "playback_descriptor_stride": 0x5EC,
            "playback_frame_count": "depends on actual pool allocation success; not established",
        },
        "not_proven": [
            "recording RAW pixel pool: p429 canvas+0x3C=0 excludes its RAW plane from FieldAngle total",
            "full-height RAW source uses current sensor geometry; retained canvas+0xF8=3412 feeds separate preview processing, whose hardware behavior remains unverified",
            "RWZM hardware output, stride, border coverage and Bayer phase",
            "actual OG4K DNG header size and all descriptor copies",
            "available recording/playback RAM, live scheduling, and recording throughput",
        ],
        "camera_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arithmetic-only", action="store_true", help="explicitly omit native ARM verification")
    args = parser.parse_args()
    print(json.dumps(build_report(native=not args.arithmetic_only), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
