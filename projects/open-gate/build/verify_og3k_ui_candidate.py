#!/usr/bin/env python3
"""Independent structural checks for the coupled OG3K UI test package.

This verifier does not rebuild or install anything.  It reads the generated
package back as the camera loader will see it, decodes the three Thumb B.W
hooks independently, and checks that their destinations are the intended
mixed-ISA entry stubs inside OG3KUI.BIN.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
DEFAULT_OUT = HERE / "ui_runtime_candidate"
RESEARCH_UI = ROOT / "research" / "ui"

sys.path.insert(0, str(RESEARCH_UI / "tools"))
from nbr import inspect as inspect_nbr  # noqa: E402
from xci import decode as decode_xci  # noqa: E402


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def decode_thumb_bw(site: int, word: int) -> int:
    """Decode a Thumb-2 unconditional B.W T4 word to its aligned target."""
    first, second = word & 0xFFFF, word >> 16
    if first & 0xF800 != 0xF000 or second & 0xD000 != 0x9000:
        raise AssertionError(f"0x{word:08X} is not an unconditional Thumb B.W")
    sign = (first >> 10) & 1
    j1, j2 = (second >> 13) & 1, (second >> 11) & 1
    i1, i2 = (~j1 ^ sign) & 1, (~j2 ^ sign) & 1
    delta = (sign << 24) | (i1 << 23) | (i2 << 22)
    delta |= (first & 0x3FF) << 12 | (second & 0x7FF) << 1
    if sign:
        delta -= 1 << 25
    return site + 4 + delta


def vshl_sections(blob: bytes) -> tuple[int, int, dict[int, bytes]]:
    magic, count, entry, body_bytes = struct.unpack_from("<4sIII", blob)
    if magic != b"VBIN":
        raise AssertionError("bad VSHL magic")
    offset = 16 + count * 8
    sections: dict[int, bytes] = {}
    for index in range(count):
        destination, length = struct.unpack_from("<II", blob, 16 + index * 8)
        if destination in sections:
            raise AssertionError(f"duplicate VSHL destination 0x{destination:08X}")
        sections[destination] = blob[offset:offset + length]
        if len(sections[destination]) != length:
            raise AssertionError("truncated VSHL section")
        offset += length + (-length % 4)
    if offset != 16 + count * 8 + body_bytes:
        raise AssertionError("VSHL body length disagrees with section table")
    if any(blob[offset:]):
        raise AssertionError("non-zero data follows the declared VSHL body")
    return entry, offset, sections


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"candidate package directory (default: {DEFAULT_OUT})")
    args = parser.parse_args(argv)
    out = args.out
    manifest = json.loads((out / "MANIFEST.json").read_text())
    code = (out / "OG3KUI.BIN").read_bytes()
    pack = (out / "OG3KUI.NBR").read_bytes()
    autorun = (out / "AutoRun.txt").read_bytes()
    vshl = (out / "VSHL.BIN").read_bytes()

    assert sha256(code) == manifest["ui"]["code_sha256"]
    assert sha256(pack) == manifest["ui"]["pack_sha256"]
    assert sha256(autorun) == manifest["package"]["autorun_sha256"]
    assert sha256(vshl) == manifest["package"]["vshl_sha256"]

    entry, used, sections = vshl_sections(vshl)
    assert used == manifest["package"]["vshl_used_bytes"]
    assert len(sections) == manifest["package"]["vshl_sections"]

    code_address = int(manifest["ui"]["code_address"], 16)
    state_address = int(manifest["ui"]["state_address"], 16)
    pack_address = int(manifest["ui"]["pack_address"], 16)
    assert sections[code_address] == code
    assert len(sections[state_address]) == manifest["ui"]["state_bytes"] == 72
    assert sections[state_address] == bytes(72)
    assert sections[pack_address] == pack
    assert code.count(struct.pack("<I", 0xE38CC001)) == 5  # orr ip, ip, #1
    assert struct.pack("<I", 0xE28CC001) not in code       # never add/toggle bit 0

    hook_results = []
    section_order = list(sections)
    hook_order = []
    for hook in manifest["ui"]["hooks"]:
        site = int(hook["address"], 16)
        hook_order.append(site)
        target = int(hook["target"], 16)
        payload = sections[site]
        assert len(payload) == 4
        word = struct.unpack("<I", payload)[0]
        decoded = decode_thumb_bw(site, word)
        assert decoded == target
        offset = target - code_address
        assert code[offset:offset + 4] == b"\x78\x47\x00\xBF"  # bx pc; nop
        original = int(hook["original"], 16)
        original_offset = original - code_address
        assert code[original_offset:original_offset + 4] == struct.pack(
            "<I", int(hook["stock"], 16)
        )
        hook_results.append({
            "site": f"0x{site:08X}",
            "word": f"0x{word:08X}",
            "target": f"0x{decoded:08X}",
            "stock_resume_stub": f"0x{original:08X}|1",
        })
    assert hook_order == [0xC05E5B58, 0xC05E84D8, 0xC05E6400, 0xC05D90F0]
    assert [section_order.index(site) for site in hook_order] == sorted(
        section_order.index(site) for site in hook_order
    )
    assert section_order[-1] == 0xC05D90F0

    ownership = manifest["validation"]["runtime_ownership"]
    assert ownership["safe_draw_measurement"] == "firmware built-in `gui image log`"
    assert ownership["safe_screen_capture"] == "firmware built-in `display capture`"
    conflicts = "\n".join(ownership["incompatible_diagnostics"])
    for required in ("size_ctl.py", "appendobs_ctl.py", "xcitrace_ctl.py", "zoomlog.S"):
        assert required in conflicts

    inventory = inspect_nbr(pack)
    expected_assets = {row["name"]: row for row in manifest["ui"]["assets"]}
    assert {row["name"] for row in inventory["resources"]} == set(expected_assets)
    files = {row["filename"]: row for row in inventory["files"]}
    for row in inventory["resources"]:
        file_row = files[row["filename"]]
        data = pack[file_row["offset"]:file_row["offset"] + file_row["bytes"]]
        width, height, _, _ = decode_xci(data)
        expected = expected_assets[row["name"]]
        assert (width, height) == (expected["width"], expected["height"])
        assert sha256(data) == expected["sha256"]

    print(json.dumps({
        "status": "PASS (offline structural verification only)",
        "loader_entry": f"0x{entry:08X}",
        "vshl_used_bytes": used,
        "records": manifest["ui"]["records"]["records"],
        "resources": sorted(expected_assets),
        "thumb_hooks": hook_results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
