#!/usr/bin/env python3
"""Offline fp 5.02 speed audit; reads saved dumps/ROM, never opens USB."""
import hashlib
import json
import struct
from pathlib import Path

from capstone import CS_ARCH_ARM, CS_MODE_ARM, Cs


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
ROM_PATH = ROOT / "out/seg0_c0000000.bin"
ROM_BASE = 0xC0000000
HEAP_BASE = 0xC3400000
FOCUS = 0xC3476414


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def capture(folder, identity_file):
    path = ROOT / "research/lens/captures" / folder / "HEAP34.bin"
    data = path.read_bytes()
    identity = json.loads((path.parent / identity_file).read_text())
    read = lambda address: u32(data, address - HEAP_BASE)
    assert read(FOCUS) == 0xC0B8EEEC
    lens = read(FOCUS + 0x54)
    sync = read(FOCUS + 0x58)
    offset = lens - HEAP_BASE
    name = data[offset + 0x24:offset + 0x60].split(b"\0")[0].decode().strip()
    assert name == identity["name"]
    assert read(lens + 0x1C) == int(identity["type_code"], 16)
    assert read(lens + 0x18) == identity["serial"]
    flags = read(lens + 0x64)
    extended = bool(flags & (1 << 23))
    standard = {key: read(lens + off) for key, off in
                (("minimum", 0x78), ("maximum", 0x7C), ("movie", 0x80))}
    extension = {key: read(lens + off) for key, off in
                 (("minimum", 0x13C), ("maximum", 0x140), ("movie", 0x144))}
    active = extension if extended else standard
    bits = 24 if extended else 16
    assert 0 < active["minimum"] <= active["movie"] <= active["maximum"] < (1 << bits)
    return {
        "input": str(path.relative_to(ROOT)), "sha256": sha256(data),
        "bytes": len(data), "name": name, "type_code": identity["type_code"],
        "native_vtable": hex(read(FOCUS)), "lens_data": hex(lens),
        "lens_data_file_offset": hex(offset), "sync_data": hex(sync),
        "sync_data_plus_0x24_raw": read(sync + 0x24),
        "equipment_flags": hex(flags), "extended_speed_supported": extended,
        "standard_speed_fields": standard, "extended_speed_fields": extension,
        "selected_speed_fields_pps": active, "wire_speed_bits": bits,
        "normal_maximum_divided_by_movie": active["maximum"] / active["movie"],
        "current_attached_lens_confirmed": False,
        "actual_motor_speed_measured": False, "physical_safety_verified": False,
    }


def main():
    rom = ROM_PATH.read_bytes()
    tables = {
        "scan_drive_slot_0x18": (0xC091C50C + 0x18, 0xC0238B58),
        "controller_slot_0xbc": (0xC0B8DA14 + 0xBC, 0xC0332520),
        "native_l_slot_0x18": (0xC0B8EEEC + 0x18, 0xC033EC80),
        "native_l_slot_0x1c": (0xC0B8EEEC + 0x1C, 0xC033EF90),
    }
    for address, expected in tables.values():
        assert u32(rom, address - ROM_BASE) == expected
    ranges = (
        (0xC0238A28, 0xC0238B78),  # Scan request and forwarding method.
        (0xC033DE20, 0xC033DEC8),  # Normal/minimum/movie getters.
        (0xC033EC80, 0xC033EE78),  # Default branch and conversion/clamp.
        (0xC033EF90, 0xC033F050),  # Explicit scan-drive conversion.
        (0xC0357E58, 0xC0357F30),  # Command focus wire serialization.
    )
    disassembler = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    listing = []
    for start, end in ranges:
        listing.append(f"\n; {start:08X}..{end:08X} (end exclusive)")
        for ins in disassembler.disasm(rom[start - ROM_BASE:end - ROM_BASE], start):
            listing.append(f"{ins.address:08X}: {ins.bytes.hex():8s}  {ins.mnemonic:8s} {ins.op_str}")
    result = {
        "schema": 1, "date": "2026-10-21", "offline_only": True,
        "rom": {"input": str(ROM_PATH.relative_to(ROOT)), "bytes": len(rom), "sha256": sha256(rom)},
        "rom_vtable_checks": {key: {"address": hex(a), "value": hex(v)} for key, (a, v) in tables.items()},
        "captures": [
            capture("28mm_sigma", "lens_28mm_F1_4_DG_HSM_Art_019.json"),
            capture("40mm_lumix", "lens_LUMIX_S_40_F2.json"),
        ],
        "scope": "Historical advertised speed fields and ROM control flow; no live speed, thermal, optical or stop validation.",
    }
    (OUT / "audit.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    (OUT / "rom-speed.asm").write_text("\n".join(listing) + "\n")
    print(json.dumps({"offline_only": True, "captures": [
        {"name": c["name"], "pps": c["selected_speed_fields_pps"], "wire_bits": c["wire_speed_bits"]}
        for c in result["captures"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
