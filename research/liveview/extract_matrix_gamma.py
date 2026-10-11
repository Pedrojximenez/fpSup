#!/usr/bin/env python3
"""Extract static fp Ver.5.02 matrix/gamma evidence; never opens camera transport."""

import argparse
import hashlib
import json
import struct
from pathlib import Path


DEFAULTS = (
    ("IGAMMA_control", 0xC2F0C008, 3),
    ("IGAMMA_knots", 0xC2F0C014, 27),
    ("RGBLMAT", 0xC2F0C080, 22),
    ("PSTIGAM_knots", 0xC2F0C0D8, 27),
    ("GAM_GS_GAMDEC", 0xC2F13094, 36),
    ("GAM_BAS", 0xC2F13124, 65),
)
ROOTS = (0xC0B38ACC, 0xC0B3EFDC, 0xC0B3F83C)
SELECTED_IDS = {0x29, 0x2B, 0x2C, 0x2D, 0x32, 0x33, 0x34}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path,
                        default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    files = [(0xC0000000, args.project_root / "out/seg0_c0000000.bin"),
             (0xC2EF6E00, args.project_root / "out/seg1_c2ef6e00.bin")]
    segments = [(base, path.resolve(), path.read_bytes()) for base, path in files]

    def raw(address, size):
        for base, _, blob in segments:
            offset = address - base
            if 0 <= offset and offset + size <= len(blob):
                return blob[offset:offset + size]
        return None

    def word(address):
        data = raw(address, 4)
        if data is None:
            raise ValueError(f"Address {address:#x} is outside static input segments")
        return struct.unpack("<I", data)[0]

    result = {
        "scope": "offline static bytes, not live active register snapshot",
        "sources": {str(path): hashlib.sha256(blob).hexdigest()
                    for _, path, blob in segments},
        "defaults": {},
        "pq_resources": [],
    }
    for name, address, count in DEFAULTS:
        values = list(struct.unpack("<" + "I" * count, raw(address, count * 4)))
        result["defaults"][name] = {"address": hex(address), "uint32": values}
    for address in ROOTS:
        item = {"root": hex(address), "fields": {}}
        for offset in (0x100, 0x108, 0x180):
            pointer, count = word(address + offset), word(address + offset + 4)
            field = {"pointer": hex(pointer), "count": count}
            if count > 4096:
                raise ValueError(f"Implausible resource count {count} at {address+offset:#x}")
            block = raw(pointer, count * 8)
            if block is None:
                field["note"] = "RAM pointer; initializer provenance in report; not captured"
            elif offset == 0x180:
                field["selected_rows"] = [
                    {"id": row[0], "enabled_byte": row[1],
                     "update_byte": row[2], "reserved": row[3]}
                    for row in struct.iter_unpack("<IBBH", block)
                    if row[0] in SELECTED_IDS
                ]
            else:
                field["rows"] = [
                    {"address": hex(pointer + i * 8),
                     "threshold": word(pointer + i * 8),
                     "bytes": list(raw(pointer + i * 8 + 4, 4))}
                    for i in range(count)
                ]
            item["fields"][hex(offset)] = field
        result["pq_resources"].append(item)
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "matrix-gamma-static-data.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(target.resolve())


if __name__ == "__main__":
    main()
