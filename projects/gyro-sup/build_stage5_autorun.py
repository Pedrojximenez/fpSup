#!/usr/bin/env python3
"""Assemble and emit the SIGMA fp Stage-5 AutoRun memory-write script."""

from __future__ import annotations

import argparse
import struct
import subprocess
import tempfile
from pathlib import Path

LOAD_ADDRESS = 0xC072DE64
HOOK_SITE = 0xC00D0794
ORIGINAL_HOOK_WORD = 0xFA046FD7
PATH_TEMPLATE_ADDRESS = 0xC072EF00
GCSV_PATH_ADDRESS = 0xC072EF40
# 0xC072E4D4 是 v3 新增的 accel 一次性初始化旗標,必須歸零否則 init 會被跳過。
STATE_ADDRESSES = (0xC072EE80, 0xC072EE84, 0xC072EE88, 0xC072EE8C, 0xC072EE90, 0xC072EE94)


def elf_sections(data: bytes):
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", data, 0)
    section_offset, entry_size, count, names_index = header[6], header[11], header[12], header[13]
    sections = [
        struct.unpack_from("<IIIIIIIIII", data, section_offset + i * entry_size)
        for i in range(count)
    ]
    names_section = sections[names_index]
    names = data[names_section[4] : names_section[4] + names_section[5]]
    result = {}
    for index, section in enumerate(sections):
        start = section[0]
        end = names.find(b"\0", start)
        name = names[start:end].decode() if start else ""
        result[name] = (index, section)
    return sections, result


def extract_and_relocate(obj: Path) -> bytes:
    data = obj.read_bytes()
    sections, by_name = elf_sections(data)
    _, text_section = by_name[".text"]
    text = bytearray(data[text_section[4] : text_section[4] + text_section[5]])

    _, sym_section = by_name[".symtab"]
    string_section = sections[sym_section[6]]
    strings = data[string_section[4] : string_section[4] + string_section[5]]
    symbols = []
    for offset in range(
        sym_section[4], sym_section[4] + sym_section[5], sym_section[9]
    ):
        name_offset, value, size, info, other, section_index = struct.unpack_from(
            "<IIIBBH", data, offset
        )
        end = strings.find(b"\0", name_offset)
        name = strings[name_offset:end].decode() if name_offset else ""
        symbols.append((name, value, section_index))

    if ".rel.text" in by_name:
        _, rel_section = by_name[".rel.text"]
        for offset in range(
            rel_section[4], rel_section[4] + rel_section[5], rel_section[9]
        ):
            place, info = struct.unpack_from("<II", data, offset)
            rel_type, symbol_index = info & 0xFF, info >> 8
            if rel_type != 28:  # R_ARM_CALL
                raise ValueError(f"unsupported relocation type {rel_type} at {place:#x}")
            _, symbol_value, symbol_section = symbols[symbol_index]
            if symbol_section != by_name[".text"][0]:
                raise ValueError("R_ARM_CALL target is not in .text")
            displacement = symbol_value - place - 8
            if displacement % 4:
                raise ValueError("unaligned ARM call target")
            instruction = struct.unpack_from("<I", text, place)[0]
            instruction = (instruction & 0xFF000000) | ((displacement >> 2) & 0xFFFFFF)
            struct.pack_into("<I", text, place, instruction)
    return bytes(text)


def arm_branch(source: int, target: int, link: bool = True) -> int:
    displacement = target - source - 8
    if displacement % 4:
        raise ValueError("unaligned branch")
    return (0xEB000000 if link else 0xEA000000) | ((displacement >> 2) & 0xFFFFFF)


def words(data: bytes):
    if len(data) % 4:
        data += b"\0" * (-len(data) % 4)
    return struct.unpack(f"<{len(data) // 4}I", data)


def emit_autorun(code: bytes) -> str:
    lines = [
        "# SIGMA fp Ver.5.02 - Stage 5 gyro logger, microsecond timestamps + accelerometer",
        "# The colorbar is up for the whole load and clears the moment the hook is",
        "# armed: record once it DISAPPEARS. A colorbar that never clears = failed load.",
        "# Output: root sidecar such as \\A001_003.GYR, paired with CINEMA/A001_003.",
        "# GYR = GFS5 header (version 4) + GFT2 batches + raw X,Y,0,Z gyro samples.",
        "# GFT2 carries one accelerometer triple per batch under the batch's own",
        "# TickTimer stamp, so gyro and accel share a single clock domain - that is",
        "# what Gyroflow horizon lock needs. A one-shot init lifts the MMA8452Q out",
        "# of its 6.25 Hz auto-sleep default to 100 Hz (observed ~47 Hz: the firmware",
        "# poll rate, not the sensor - raising ODR further changes nothing).",
        "# v4 also records the exposure time each clip was shot at (FUN_c030c7f0).",
        "# This was originally labelled rolling-shutter readout and that was wrong:",
        "# it only ever returns shutter speeds. Rolling shutter comes from the IMX410",
        "# mode tables instead. Lens identity is a SEPARATE program: it needs an",
        "# L-mount bus transaction and has no business on the 2500 Hz gyro thread.",
        "# On stop the camera ALSO writes \\A001_003.CSV, a Gyroflow .gcsv ready to open",
        "# with no host step: the columns are raw integers with the scale factors in the",
        "# header, so only integer-to-ASCII is needed on camera.",
        "# codex/decode_sigma_fp_gyro_stage5.py still reads the .GYR if you want to",
        "# re-derive it (and it handles the older GFT1 captures).",
        "# RAM-only. If the camera freezes: remove BATTERY and card.",
        f"mem set {HOOK_SITE:#010x} {ORIGINAL_HOOK_WORD:#010x}",
        "display monitor 0 1",
        # Colorbar goes up before the load and comes down only once the hook is
        # armed. The load itself is the slow part -- several seconds of mem set --
        # so this is on-screen the whole time and cannot be missed, at no cost in
        # extra waiting. It also fails usefully: a colorbar that never clears means
        # the load stopped part way, rather than looking identical to success.
        "display colorbar 1 0",
        "memmgr bufmem get 0 0x800000",
        "mem save \\HANDLE5.BIN 0xC3757A7C,,0xC",
        "mem save \\PATHMGR5.BIN 0xC3438400,,0x68",
    ]
    for index, word in enumerate(words(code)):
        lines.append(f"mem set {LOAD_ADDRESS + index * 4:#010x} {word:#010x}")

    # Template: \\A000_000.GYR\0. Hook replaces camera/reel/clip fields at record start.
    template = b"\\A000_000.GYR\0\0\0"
    for index, word in enumerate(words(template)):
        lines.append(f"mem set {PATH_TEMPLATE_ADDRESS + index * 4:#010x} {word:#010x}")
    gcsv_template = b"\\A000_000.GCSV\0\0"
    for index, word in enumerate(words(gcsv_template)):
        lines.append(f"mem set {GCSV_PATH_ADDRESS + index * 4:#010x} {word:#010x}")
    for address in STATE_ADDRESSES:
        lines.append(f"mem set {address:#010x} 0x00000000")
    lines.extend(
        [
            f"mem save \\CAVE5.BIN {LOAD_ADDRESS:#010x},,{len(code):#x}",
            f"mem set {HOOK_SITE:#010x} {arm_branch(HOOK_SITE, LOAD_ADDRESS):#010x}",
            "ctrl sleep 400",
            "display colorbar 0 0",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("stage5_gyro_timestamp_hook.S"))
    parser.add_argument("--output", type=Path, default=Path("autorun_gyro_stage5.txt"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        obj = Path(directory) / "stage5.o"
        subprocess.run(
            ["clang", "-target", "armv7-none-eabi", "-c", str(args.source), "-o", str(obj)],
            check=True,
        )
        code = extract_and_relocate(obj)
    if len(code) > 0xF9C:
        raise ValueError(f"code cave overflow: {len(code):#x} bytes")
    args.output.write_text(emit_autorun(code), encoding="ascii")
    print(f"code_size={len(code):#x}")
    print(f"hook_word={arm_branch(HOOK_SITE, LOAD_ADDRESS):#010x}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
