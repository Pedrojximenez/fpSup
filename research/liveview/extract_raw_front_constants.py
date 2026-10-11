#!/usr/bin/env python3
"""Read-only fp 5.02 RAW-front ROM extraction; does not communicate with a camera."""
from pathlib import Path
import argparse
import hashlib
import json
import struct


def main():
    ap = argparse.ArgumentParser()
    default_root = next((p for p in Path(__file__).resolve().parents
                         if (p / "out" / "seg0_c0000000.bin").is_file()), None)
    ap.add_argument("--root", type=Path, default=default_root)
    ap.add_argument("--output", type=Path, default=Path(__file__).with_name("raw-front-constants.json"))
    args = ap.parse_args()
    if args.root is None:
        ap.error("Repository root not found; provide --root with the firmware out/ directory parent")
    segments = []
    for name, base in (("seg0_c0000000.bin", 0xC0000000), ("seg1_c2ef6e00.bin", 0xC2EF6E00)):
        path = args.root / "out" / name
        blob = path.read_bytes()
        segments.append((base, blob, path))

    def read(address, length):
        for base, blob, _ in segments:
            if base <= address and address + length <= base + len(blob):
                return blob[address - base:address - base + length]
        raise ValueError(f"Out of segment: {address:#x}+{length:#x}")

    def words(address, length):
        raw = read(address, length)
        return {f"0x{i:03X}": f"0x{struct.unpack_from('<I', raw, i)[0]:08X}" for i in range(0, length, 4)}

    result = {
        "scope": "Offline ROM defaults only; not a live snapshot or proof of pixel clipping",
        "segments": [{"name": p.name, "base": f"0x{a:08X}", "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for a, b, p in segments],
        "block_names": {f"0x{a:08X}": read(a, 80).split(b"\0", 1)[0].decode("utf-8").strip() for a in (0xC07D3870, 0xC07D3A80, 0xC07D38C8, 0xC07D375C)},
        "rwapknee_C2F12E74": words(0xC2F12E74, 0x84),
        "rawblt_C2F12A3C": words(0xC2F12A3C, 300),
        "apknee_pstapknee_C2F0BF90": words(0xC2F0BF90, 0x78),
        "sig1_unknown_C2F0BDE8": words(0xC2F0BDE8, 4),
        "bin_records": [],
    }
    for address in (0xC0B5F770, 0xC0B5F7A8):
        raw = read(address, 0x38)
        coeff16 = list(struct.unpack_from("<9H", raw, 8))
        coeff8 = list(raw[0x1C:0x28])
        result["bin_records"].append({"address": f"0x{address:08X}", "bytes": raw.hex(), "u16_values": coeff16,
                                      "u16_group_sums": [sum(coeff16[i:i+3]) for i in range(0,9,3)],
                                      "u8_values": coeff8, "u8_group_sums": [sum(coeff8[i:i+3]) for i in range(0,12,3)]})
    assert result["block_names"]["0xC07D3870"] == "SIG0＿TBLSD"
    assert result["rwapknee_C2F12E74"]["0x000"] == "0x00000000"
    assert result["sig1_unknown_C2F0BDE8"]["0x000"] == "0x00000FFF"
    for record in result["bin_records"]:
        assert record["u16_group_sums"] == [4096] * 3
        assert record["u8_group_sums"] == [64] * 4
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"Verified ROM constants; wrote {args.output}")


if __name__ == "__main__":
    main()
