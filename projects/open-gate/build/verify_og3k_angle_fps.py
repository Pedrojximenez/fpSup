#!/usr/bin/env python3
"""Offline invariants for the OG3K shutter-angle nominal-FPS fix."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct

from og3k_plan import (BUFFER_COUNT_ADDR, EXPECTED_PLAN_WORDS, FMT, FPS_CODE,
                       FPS_HOOK, FPS_HOOKS, FPS_ORIGINAL, HOOKS, DONOR_FPS_VALUES,
                       DONOR_NOMINAL_FPS_ADDR, DONOR_TIMING_ADDR,
                       DONOR_TIMING_STOCK, NOMINAL_FPS, TARGET, WITH_FPS, Plan)


def arm_branch_target(site: int, word: int) -> int:
    assert word >> 24 in (0xEA, 0xEB)
    displacement = word & 0xFFFFFF
    if displacement & 0x800000:
        displacement -= 1 << 24
    return site + 8 + displacement * 4


def mode98_timing_map(plan: Plan) -> dict[tuple[int, int], int]:
    result = {}
    for key, donor, source_mode, _ in FMT:
        if donor != 98:
            continue
        hmax, tail, vmax, x = plan.timing(source_mode)
        pair = (hmax | tail << 16, vmax | x << 16)
        assert pair not in result or result[pair] == NOMINAL_FPS[key]
        result[pair] = NOMINAL_FPS[key]
    return result


def selected_result(mode: int, flag: int, timing: tuple[int, int], stock: int,
                    timing_map: dict[tuple[int, int], int]) -> int:
    if mode == 98 and flag == 1:
        return timing_map.get(timing, stock)
    return stock


def package_words(path: Path) -> tuple[dict[int, int], list[int], dict]:
    blob = (path / "VSHL.BIN").read_bytes()
    json_manifest = path / "MANIFEST.json"
    if json_manifest.is_file():
        manifest = json.loads(json_manifest.read_text())
    else:
        text = (path / "MANIFEST.txt").read_text()
        count_match = re.search(r"OpenGate core (\d+) words", text)
        sha_match = re.search(r"VSHL\.BIN\s+\S+B\s+sha256=([0-9a-f]{64})", text)
        assert count_match and sha_match
        manifest = {
            "base_opengate_writes": int(count_match.group(1)),
            "package": {"vshl_sha256": sha_match.group(1)},
        }
    assert hashlib.sha256(blob).hexdigest() == manifest["package"]["vshl_sha256"]
    magic, count, _, body_bytes = struct.unpack_from("<4sIII", blob)
    assert magic == b"VBIN"
    offset = 16 + count * 8
    words = {}
    order = []
    for index in range(count):
        destination, length = struct.unpack_from("<II", blob, 16 + index * 8)
        payload = blob[offset:offset + length]
        assert len(payload) == length
        offset += length + (-length % 4)
        if destination < 0x40000000:
            continue
        assert length % 4 == 0
        for inner in range(0, length, 4):
            address = destination + inner
            assert address not in words, f"duplicate package write 0x{address:08X}"
            words[address] = struct.unpack_from("<I", payload, inner)[0]
            order.append(address)
    assert offset == 16 + count * 8 + body_bytes
    assert not any(blob[offset:])
    return words, order, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path,
                        help="also verify a generated UI VSHL/MANIFEST package")
    args = parser.parse_args(argv)
    # This suite is the mode-98 shutter-angle acceptance suite: it asserts
    # OG3K-shaped facts (seven distinct <=60 fps timing tuples sharing one
    # donor whose stock nominal FPS is a lie).  A target that does not patch
    # the donor's timing has no angle fix to verify -- HSW writes mode 12's
    # own stock 330/330/910 and mode 12's stock nominal FPS is already the
    # true 240 -- so refuse rather than assert-fail on an unrelated shape.
    if not WITH_FPS or not FPS_HOOKS:
        raise SystemExit(
            f"OG_TARGET={TARGET} does not arm the shutter-angle callsites, so "
            f"there is nothing here to verify.  Use og3k_plan.Plan().check() "
            f"and verify_og3k_ui_candidate.py for that target."
        )
    plan = Plan()
    errors = plan.check()
    assert not errors, "\n".join(errors)
    items = list(plan.all())
    assert len(items) == EXPECTED_PLAN_WORDS
    writes = {address: value for address, value, _ in items}
    assert len(writes) == len(items)

    for site, stock_word, _ in FPS_HOOKS:
        assert plan.word(site) == stock_word
        assert arm_branch_target(site, stock_word) == FPS_ORIGINAL
        assert arm_branch_target(site, writes[site]) == FPS_CODE
    assert DONOR_NOMINAL_FPS_ADDR not in writes
    assert BUFFER_COUNT_ADDR not in writes
    assert DONOR_TIMING_ADDR + 4 not in writes
    assert DONOR_TIMING_ADDR + 8 not in writes
    assert (plan.word(DONOR_TIMING_ADDR + 4),
            plan.word(DONOR_TIMING_ADDR + 8)) == DONOR_TIMING_STOCK

    # Inspect the emitted ARM words, not only the source/model: aligned save,
    # exactly one BLX ip to the stock getter, one acquire barrier, no memory
    # stores in the wrapper body, and a restoring return.
    fps_blob = plan.blobs["og3kfps"]
    fps_words = struct.unpack(f"<{len(fps_blob) // 4}I", fps_blob)
    assert fps_words[0] == 0xE92D4070       # push {r4,r5,r6,lr}
    assert fps_words[-1] == 0xE8BD8070      # pop {r4,r5,r6,pc}
    assert fps_words.count(0xE12FFF3C) == 1 # blx ip
    assert fps_words.count(0xF57FF05B) == 1 # dmb ish
    for index, word in enumerate(fps_words[1:-1], 1):
        single_store = ((word >> 26) & 0x3) == 0x1 and not (word & (1 << 20))
        block_store = ((word >> 25) & 0x7) == 0x4 and not (word & (1 << 20))
        assert not single_store and not block_store, (
            f"og3kfps emitted a memory store at word {index}: 0x{word:08X}"
        )

    timing_map = mode98_timing_map(plan)
    assert set(timing_map.values()) == DONOR_FPS_VALUES
    assert len(timing_map) == 7                 # 23.976 and 24 share class, not tuple

    table = {}
    for index, (key, donor, source_mode, _) in enumerate(FMT):
        value = writes[0xC0731000 + index * 48 + 0x2C]
        assert value == NOMINAL_FPS[key]
        table[key] = {"mode": donor, "source_mode": source_mode,
                      "nominal_fps": value}

    # Exercise every exact tuple and every possible cross-pair hybrid. A hybrid
    # must never accidentally decode as a different valid FPS.
    word0 = {DONOR_TIMING_STOCK[0], 0, 0xFFFFFFFF}
    word1 = {DONOR_TIMING_STOCK[1], 0, 0xFFFFFFFF}
    for first, second in timing_map:
        word0.add(first)
        word1.add(second)
    for mode in (0, 53, 98, 106, 117, 143):
        for flag in (0, 1, 2):
            for first in word0:
                for second in word1:
                    pair = (first, second)
                    stock = 1000 + mode
                    got = selected_result(mode, flag, pair, stock, timing_map)
                    expected = timing_map.get(pair, stock) if mode == 98 and flag == 1 else stock
                    assert got == expected

    # A transition writes word0 then word1 while interrupts are masked. Even for
    # a hypothetical other PE, the two intermediate cross-pairs fail open.
    pairs = list(timing_map)
    for old in pairs:
        for new in pairs:
            if old == new:
                continue
            for intermediate in ((new[0], old[1]), (old[0], new[1])):
                got = selected_result(98, 1, intermediate, 78, timing_map)
                if intermediate in timing_map:
                    assert intermediate in (old, new)
                    assert got in (timing_map[old], timing_map[new])
                else:
                    assert got == 78

    before_after = {}
    for key, donor, source_mode, _ in FMT:
        hmax, tail, vmax, _ = plan.timing(source_mode)
        if key == "OG3K100":
            hmax, tail, vmax = 330, 270, 2182
        actual = 72_000_000 / (hmax * (vmax - 1) + tail)
        stock = 78 if donor == 98 else NOMINAL_FPS[key]
        before_after[key] = {
            "actual_fps": actual,
            "nominal_fps": NOMINAL_FPS[key],
            "before_ev": -math.log2(stock / actual),
            "after_ev": -math.log2(NOMINAL_FPS[key] / actual),
        }

    package = None
    if args.package:
        packaged, order, manifest = package_words(args.package)
        assert manifest["base_opengate_writes"] == EXPECTED_PLAN_WORDS
        assert all(packaged.get(address) == value for address, value, _ in items)
        positions = {address: index for index, address in enumerate(order)}
        hook_sites = {site for site, *_ in HOOKS}
        body_order = [positions[address] for address, _, _ in items
                      if address not in hook_sites]
        hook_order = [positions[site] for site, *_ in HOOKS]
        assert body_order == sorted(body_order)
        assert hook_order == sorted(hook_order)
        assert max(body_order) < min(hook_order)
        protected = ({site for site, _, _ in FPS_HOOKS} |
                     {DONOR_NOMINAL_FPS_ADDR, BUFFER_COUNT_ADDR,
                      DONOR_TIMING_ADDR + 4, DONOR_TIMING_ADDR + 8} |
                     set(range(FPS_CODE, FPS_CODE + len(fps_blob), 4)))
        assert not (set(packaged) & protected - set(writes))
        package = {
            "path": str(args.package.resolve()),
            "base_opengate_writes": manifest["base_opengate_writes"],
            "vshl_sha256": manifest["package"]["vshl_sha256"],
            "core_order_verified": True,
        }

    print(json.dumps({
        "status": "PASS (offline angle-FPS invariants)",
        "plan_words": len(items),
        "hooks": [
            {"address": f"0x{site:08X}", "role": role}
            for site, _, role in FPS_HOOKS
        ],
        "payload": f"0x{FPS_CODE:08X}",
        "payload_bytes": len(fps_blob),
        "runtime_source": {
            "active_flag": "0xC0731C08 == 1",
            "mode98_timing": f"0x{DONOR_TIMING_ADDR:08X} +4/+8",
            "policy": "exact tuple only; mixed/unknown tuples fail open after stock getter",
        },
        "formats": table,
        "predicted_ev": before_after,
        "static_shared_firmware_writes": [],
        "package": package,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
