#!/usr/bin/env python3
"""Offline fp RAW/ISP/movie handoff evidence. Never contacts a camera.

Profile values are reread from the hash-pinned ROM and compared with the
existing profile extraction. Register calculations describe driver writes,
not emulated hardware behavior or measured output precision.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = 0xC0000000
EXPECTED = "aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622"
FUNCTIONS = {
    "blk_c01.c": [
        0xC010C9D0, 0xC01199C0, 0xC011AB80,
        0xC014AA70, 0xC01570D0, 0xC01597B8, 0xC015C230,
        0xC0179B38, 0xC01822B8, 0xC019C810,
        0xC01CB9B8, 0xC01CEF08, 0xC01CF940, 0xC01D1630,
        0xC01D3558, 0xC01D3580, 0xC01D51C8, 0xC01D5200,
        0xC01D61E8, 0xC01D69D0, 0xC01D7248, 0xC01D7638,
    ],
    "blk_c04.c": [
        0xC0428628, 0xC0428690, 0xC0429470, 0xC0429910,
        0xC0434EF8, 0xC0435428, 0xC0435D78, 0xC0436F00,
    ],
    "blk_c06.c": [0xC0690618, 0xC06978A0],
    "blk_c07.c": [0xC070AB40, 0xC070D638, 0xC07254E0],
}


def main() -> None:
    rom = (ROOT / "out/seg0_c0000000.bin").read_bytes()
    assert hashlib.sha256(rom).hexdigest() == EXPECTED, "Unexpected firmware"
    source_functions = {}
    index, excerpts = [], []
    for filename, addresses in FUNCTIONS.items():
        path = ROOT / "out/decomp/full" / filename
        source = path.read_text()
        for address in addresses:
            match = re.search(r"/\* ==== ([^\n]+) @ " + f"{address:08x}" +
                              r" ==== \*/.*?(?=\n/\* ==== |\Z)", source, re.S)
            assert match, f"Missing function {address:08x}"
            line = source.count("\n", 0, match.start()) + 1
            item = dict(address=hex(address), name=match[1],
                        source=str(path.relative_to(ROOT)), line=line)
            index.append(item)
            source_functions[address] = match[0]
            excerpts.append(f"/* {item['source']}:{line} */\n{match[0]}")

    profile_path = ROOT / "research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json"
    profiles = json.loads(profile_path.read_text())
    rows = []
    checked = 0
    for old in profiles["rows"]:
        words = []
        for col in profiles["columns"]:
            address = col["table"] + old["index"] * 4
            value = struct.unpack_from("<I", rom, address - BASE)[0]
            assert value == old["words"][col["offset"] // 4], (old["index"], col)
            words.append(value)
            checked += 1
        rows.append(dict(index=old["index"], profile_ids=old["profile_ids"],
                         fields={hex(o): words[o // 4] for o in
                                 (0x80, 0x84, 0x90, 0x94, 0xA4, 0xB4, 0xF0)}))
    counts = Counter(row["fields"]["0x94"] for row in rows)

    # These are the exact p[0] values supplied to C01570D0 in the
    # C0179B38 branch for descriptor+0x2c low nibble == 1.
    packer = []
    for selector, p0 in [(0, 0), (2, 0x280000), (3, 0x680000)]:
        reg = ((p0 & 0xFFFFF) >> 19) | ((p0 & 0x100000) >> 16) | ((p0 & 0x600000) >> 13)
        packer.append(dict(descriptor_101=selector, setter_word0=hex(p0),
                           shadow_30212374=hex(reg), mapped_mmio="0x3011e00c"))
    descriptor = source_functions[0xC019C810]
    assert "0x3011e004,7,iVar1 + 0x3021236c" in descriptor
    assert "0x30116580,2,iVar1 + 0x3021100c" in descriptor
    names = {}
    for address, expected in [(0xC07D39B4, "YUV_PACK"), (0xC07D37BC, "PST_TOP DITHER")]:
        name = rom[address - BASE:].split(b"\0", 1)[0].decode("ascii").rstrip("\n")
        assert name == expected
        names[hex(address)] = name
    context_offsets = list(struct.unpack_from("<2I", rom, 0xC07D4360 - BASE))

    report = dict(
        firmware_sha256=EXPECTED, scope="offline ROM/source analysis; no camera I/O",
        functions=index, diagnostic_names=names,
        context_offset_table=dict(address="0xc07d4360", first_two_words=context_offsets),
        isp_blocks=[
            dict(name="YUV_PACK", mmio="0x3011e004", words=7,
                 shadow="0x3021236c", setter="0xc01570d0"),
            dict(name="PST_TOP DITHER", mmio="0x30116580", words=2,
                 shadow="0x3021100c", setter="0xc010c9d0",
                 limitation="quantization bit depth and pipeline placement not established"),
        ],
        profile_audit=dict(reference=str(profile_path.relative_to(ROOT)),
                           checked_rom_words=checked, rows=len(rows),
                           canvas_94_counts=dict(counts), values=rows,
                           route="canvas+0x94 -> config+0x60 -> C31DF5C4 -> C01D3580 -> conditional descriptor+0x101",
                           limitation="stock table values only; runtime changes and high-depth support not proven"),
        packer_branch=packer,
        findings=[
            "CDNG 12-bit Bayer source is established separately; this audit follows ISP output and MOV descriptors.",
            "descriptor+0x101 > 1 halves height calculations and changes packing; bit-depth semantics unproven.",
            "All 306 extracted stock canvas rows have +0x94 == 0; special +0x101=2/3 branch has no stock table donor.",
            "C0428628 maps flags from descriptor[12] bits 0/1/5 to 1/2/4; this is not a demonstrated bit-depth field.",
            "CNRO YUV debug dump writes width*height*2 bytes without consulting its depth field; this is a dumper convention, not a silicon precision limit.",
            "C070AB40 controls 300C02C0 bits 4:3 from a native fixed value 2; input packing/endian/depth semantics remain unknown.",
        ],
        verdict="No verified high-depth ISP-to-codec handoff or H.264 10-bit enable found.",
    )
    (HERE / "raw-to-codec.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (HERE / "raw-to-codec-evidence.c").write_text("\n".join(excerpts))

    lines = []
    for start, stop, mode in [
        (0xC010C9D0, 0xC010CA30, CS_MODE_THUMB),
        (0xC01570D0, 0xC0157268, CS_MODE_THUMB),
        (0xC01D3580, 0xC01D35A8, CS_MODE_THUMB),
        (0xC01CB9B8, 0xC01CBB00, CS_MODE_THUMB),
        (0xC0428628, 0xC0428690, CS_MODE_ARM),
        (0xC0434EF8, 0xC0434F80, CS_MODE_ARM),
    ]:
        lines.append(f"\n/* ROM {start:08x}..{stop:08x}; {'Thumb' if mode == CS_MODE_THUMB else 'ARM'} */")
        for insn in Cs(CS_ARCH_ARM, mode).disasm(rom[start-BASE:stop-BASE], start):
            lines.append(f"{insn.address:08x} {insn.bytes.hex():10} {insn.mnemonic:10} {insn.op_str}")
    (HERE / "raw-to-codec-disassembly.txt").write_text("\n".join(lines) + "\n")
    print(json.dumps(dict(functions=len(index), profile_rows=len(rows),
                          checked_rom_words=checked, canvas_94_counts=dict(counts),
                          report=str(HERE / "raw-to-codec.json"))))


if __name__ == "__main__":
    main()
