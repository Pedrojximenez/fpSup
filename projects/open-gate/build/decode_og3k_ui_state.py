#!/usr/bin/env python3
"""Decode a local 72-byte OG3K UI state dump.

This tool never talks to the camera.  Acquire a fresh state dump separately,
with the per-read consent required by the camera-control workflow, then pass the
local file here.  The bitmap distinguishes a loaded private NBR from the target
NBU records actually arriving after the slower current AutoRun.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

from build_og3k_ui_candidate import (
    UI_HIT_BITMAP_BYTES,
    UI_HIT_BITMAP_OFFSET,
    UI_RECORD_COUNT,
    UI_STATE_BYTES,
    selected_plans,
)


def decode(blob: bytes) -> dict:
    if len(blob) != UI_STATE_BYTES:
        raise ValueError(f"state dump is {len(blob)} bytes; expected {UI_STATE_BYTES}")

    context, status, native_result, stock_calls, exact_calls, last_address = (
        struct.unpack_from("<6I", blob)
    )
    bitmap = blob[
        UI_HIT_BITMAP_OFFSET:UI_HIT_BITMAP_OFFSET + UI_HIT_BITMAP_BYTES
    ]
    plans, selection = selected_plans()
    if len(plans) != UI_RECORD_COUNT:
        raise AssertionError("record plan and resident bitmap disagree")

    hit_indices = [
        index for index in range(len(plans))
        if bitmap[index >> 3] & (1 << (index & 7))
    ]
    hit_set = set(hit_indices)
    kinds = {}
    for index, plan in enumerate(plans):
        row = kinds.setdefault(plan["kind"], {"hit": 0, "expected": 0})
        row["expected"] += 1
        row["hit"] += index in hit_set

    address_to_index = {
        int(plan["address"], 16): index for index, plan in enumerate(plans)
    }
    groups = []
    for group in selection["groups"]:
        addresses = [int(group["address"], 16)]
        addresses.extend(int(address, 16) for address in group["clips"])
        indices = [address_to_index[address] for address in addresses]
        hits = sum(index in hit_set for index in indices)
        groups.append({
            "name": group["name"],
            "address": group["address"],
            "hit": hits,
            "expected": len(indices),
            "complete": hits == len(indices),
        })

    unique_hits = len(hit_indices)
    if unique_hits == UI_RECORD_COUNT:
        conclusion = "all selected records arrived after installation"
    elif unique_hits:
        conclusion = "partial target replay; inspect missing records before judging drawing"
    else:
        conclusion = "no selected record arrived after installation; parser-copy UI is a no-op"

    missing = [
        {"index": index, "address": plan["address"], "kind": plan["kind"]}
        for index, plan in enumerate(plans) if index not in hit_set
    ]
    return {
        "resource_context": f"0x{context:08X}",
        "pack_status": status,
        "pack_native_result": f"0x{native_result:08X}",
        "post_install_stock_records": stock_calls,
        "exact_copy_calls": exact_calls,
        "last_stock_record_address": f"0x{last_address:08X}",
        "unique_exact_hits": unique_hits,
        "expected_exact_hits": UI_RECORD_COUNT,
        "by_kind": kinds,
        "groups": groups,
        "missing_records": missing,
        "timing_conclusion": conclusion,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state_dump", type=Path, help="local 72-byte state dump")
    parser.add_argument("--summary", action="store_true", help="omit missing-record list")
    args = parser.parse_args()
    report = decode(args.state_dump.read_bytes())
    if args.summary:
        report.pop("missing_records")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
