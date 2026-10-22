#!/usr/bin/env python3
"""Replay a recording picker hit from two exact Sensor Lab card binaries.

The archived r81 card is a known regression: its packed picker stores a
COLTAB pointer in ENTRY+4.  Boot each supplied fpSup.BIN through the real
loader, stage2, USER launcher and installed picker hook, then compare that
observable result with the repaired card.  This does not operate a camera.

    python3 -B test_res_lab_exact_picker.py /path/to/fixed-card
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R2

import imx410_plan as PL
from test_imx410_fmt import OG3K, TAB
from test_res_lab_migrated_boot import LOADER, MigratedCamera


HERE = Path(__file__).resolve().parent
KNOWN_BAD = HERE.parents[1] / "res-lab/cards/20261004-b25-menu-r81-user-relocated/debug"
KEY = 0x45300000  # free space in the emulator's mapped heap
DESCRIPTOR = 0xC2F1E654
IMAGER = 0xC343B588
BACK = 0xC043CCFC


def _replay(card: Path) -> dict:
    manifest = json.loads((card / "MANIFEST.json").read_text())
    assert manifest["b25_menu"], "expected a Sensor Lab B2_5 card"
    for name in ("AutoRun.txt", "fpSup.BIN"):
        got = sha256((card / name).read_bytes()).hexdigest()
        assert got == manifest["artifacts"][name], f"{name} differs from its manifest"

    camera = MigratedCamera(card)
    camera.boot()
    core_base = camera.user_allocs[1]
    offsets = manifest["core"]["core_offsets"]
    # The profile word itself is correct in both cards.  The regression is
    # the picker's address arithmetic after compacting the cave layout.
    assert camera.word(core_base + offsets["coltab"] - 4) == PL.PRIVATE_PROFILE

    camera.mu.mem_write(DESCRIPTOR,
                        struct.pack("<4I", 0xC0B59500, 70, 0xC0B59DC0, 70))
    camera.mu.mem_write(IMAGER, struct.pack("<I", DESCRIPTOR))
    camera.mu.mem_write(KEY, b"CUST30\0")
    camera.mu.mem_write(core_base + offsets["axis"],
                        struct.pack(f"<{len(OG3K)}I", *OG3K))
    # Model the first hit after a new selection; the recipe must be computed.
    camera.mu.mem_write(core_base + offsets["recipe"],
                        bytes(PL.RECIPE_WORDS * 4))

    fell_back = []

    def stop_at_stock(mu, address, _size, _data):
        if address == BACK:
            fell_back.append(address)
            mu.emu_stop()

    camera.mu.hook_add(UC_HOOK_CODE, stop_at_stock)
    camera.mu.reg_write(UC_ARM_REG_R2, KEY)
    entry, stack = camera.call(PL.PIK_HOOK, r0=0xAAAA0000, r1=TAB[12],
                               sp=LOADER.STACK - 0x1004)
    assert not fell_back, "the installed picker fell through to the stock path"
    assert stack == LOADER.STACK - 0x1004, "picker damaged the caller's stack"
    assert core_base <= entry < core_base + manifest["core"]["core_bytes"] - 48, \
        "picker did not return its USER entry"
    assert camera.word(entry) == 5
    assert camera.word(entry + 12) == entry + 20
    assert bytes(camera.mu.mem_read(entry + 20, 7)) == b"CUST30\0"
    return {"card": str(card), "bin_sha256": manifest["artifacts"]["fpSup.BIN"],
            "entry": f"0x{entry:08X}", "entry_profile": camera.word(entry + 4)}


def verify(fixed_card: Path, known_bad: Path = KNOWN_BAD) -> dict:
    old, fixed = _replay(known_bad), _replay(fixed_card)
    assert old["entry_profile"] == 0xC0BE3FA4, \
        "archived r81 no longer reproduces the known COLTAB pointer"
    assert fixed["entry_profile"] == PL.PRIVATE_PROFILE, \
        "fixed card still publishes the wrong recording profile"
    assert old["bin_sha256"] != fixed["bin_sha256"]
    return {"known_bad": old, "fixed": fixed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixed_card", type=Path)
    parser.add_argument("--known-bad", type=Path, default=KNOWN_BAD)
    args = parser.parse_args()
    print(json.dumps(verify(args.fixed_card, args.known_bad), indent=2))
