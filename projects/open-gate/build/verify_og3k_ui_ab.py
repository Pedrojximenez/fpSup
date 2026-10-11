#!/usr/bin/env python3
"""Verify the strict full-UI versus core-only recording A/B packages.

This is project-coupled test verification.  It does not build or install
anything; it decodes the generated VSHL section maps exactly as the camera
loader sees them and rejects every difference outside the native UI runtime.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
A_DIR = HERE / "ui_runtime_candidate"
B_DIR = HERE / "ui_recording_ab" / "core_only"

sys.path.insert(0, str(HERE))
from og3k_plan import HOOKS as OG_HOOKS  # noqa: E402
from verify_og3k_ui_candidate import vshl_sections  # noqa: E402


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def words(sections: dict[int, bytes]) -> dict[int, int]:
    result: dict[int, int] = {}
    for destination, payload in sections.items():
        if len(payload) % 4:
            raise AssertionError(f"unaligned section at 0x{destination:08X}")
        for offset in range(0, len(payload), 4):
            address = destination + offset
            if address in result:
                raise AssertionError(f"overlapping word at 0x{address:08X}")
            result[address] = struct.unpack_from("<I", payload, offset)[0]
    return result


def address_words(start: int, size: int) -> set[int]:
    if start % 4 or size % 4:
        raise AssertionError("expected word-aligned UI range")
    return set(range(start, start + size, 4))


def main() -> int:
    manifest = json.loads((A_DIR / "MANIFEST.json").read_text())
    a_autorun = (A_DIR / "AutoRun.txt").read_bytes()
    b_autorun = (B_DIR / "AutoRun.txt").read_bytes()
    if a_autorun != b_autorun:
        raise AssertionError("A/B AutoRun files differ")

    a_blob = (A_DIR / "VSHL.BIN").read_bytes()
    b_blob = (B_DIR / "VSHL.BIN").read_bytes()
    a_entry, a_used, a_sections = vshl_sections(a_blob)
    b_entry, b_used, b_sections = vshl_sections(b_blob)
    if a_entry != b_entry or a_entry != 0xC072F188:
        raise AssertionError("A/B loader entries differ")

    a_words = words(a_sections)
    b_words = words(b_sections)
    common = set(a_words) & set(b_words)
    changed = sorted(address for address in common
                     if a_words[address] != b_words[address])
    if changed:
        raise AssertionError(f"{len(changed)} shared A/B words changed")
    b_only = sorted(set(b_words) - set(a_words))
    if b_only:
        raise AssertionError(f"B has {len(b_only)} words absent from A")

    ui = manifest["ui"]
    expected_a_only = set()
    expected_a_only |= address_words(int(ui["state_address"], 16), ui["state_bytes"])
    expected_a_only |= address_words(int(ui["code_address"], 16), ui["code_bytes"])
    expected_a_only |= address_words(int(ui["pack_address"], 16), ui["pack_bytes"])
    ui_hooks = [int(row["address"], 16) for row in ui["hooks"]]
    expected_a_only.update(ui_hooks)
    a_only = set(a_words) - set(b_words)
    if a_only != expected_a_only:
        missing = sorted(expected_a_only - a_only)
        extra = sorted(a_only - expected_a_only)
        raise AssertionError(
            f"unexpected A-only map: {len(missing)} missing, {len(extra)} extra"
        )

    section_order = list(a_sections)
    if section_order[-3:] != ui_hooks:
        raise AssertionError("the three UI hooks are not A's final sections")
    for site in ui_hooks:
        if len(a_sections[site]) != 4 or site in b_sections:
            raise AssertionError(f"UI hook isolation failed at 0x{site:08X}")

    core_hooks = [site for site, *_ in OG_HOOKS]
    for site in core_hooks:
        if a_words.get(site) != b_words.get(site):
            raise AssertionError(f"OpenGate hook differs at 0x{site:08X}")

    result = {
        "status": "PASS (strict generated-package A/B)",
        "autorun_sha256": sha256(a_autorun),
        "loader_entry": f"0x{a_entry:08X}",
        "A": {
            "vshl_sha256": sha256(a_blob),
            "sections": len(a_sections),
            "used_bytes": a_used,
        },
        "B": {
            "vshl_sha256": sha256(b_blob),
            "sections": len(b_sections),
            "used_bytes": b_used,
        },
        "shared_words_changed": len(changed),
        "B_only_words": len(b_only),
        "A_only_UI_words": len(a_only),
        "OpenGate_hooks_shared": len(core_hooks),
        "UI_hooks_A_only": [f"0x{site:08X}" for site in ui_hooks],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
