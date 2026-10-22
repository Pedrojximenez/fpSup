#!/usr/bin/env python3
"""Read a bounded native AF sweep-history prefix after original AF has stopped.

No code injection, lens movement, mode/exposure setter, or capture command.
The Near object and descriptor are preserved raw: do not infer valid sample
count from C329153C alone. Pointers and counts require per-strategy analysis.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

import af_fusion_collector as collector


RANGES = {
    "near_object": (0xC3206BE4, 0x98 // 4),
    "sweep_descriptor": (0xC320680C, 0x60 // 4),
    "af_globals": (0xC32914E0, 0x60 // 4),
}
ARRAYS = {
    "mposm": 0xC3291958,
    "aggregate_contrast": 0xC32938A8,
    "area0_h_history": 0xC329B128,
    "area0_l_history": 0xC32CCE08,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usb-shell", type=Path, default=collector.DEFAULT_SHELL_DIR)
    parser.add_argument("--socket", default=collector.DEFAULT_SOCKET)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=32)
    args = parser.parse_args()
    if not 1 <= args.count <= 128:
        parser.error("count must be 1..128 (bounded history prefix)")
    if args.output.exists():
        parser.error("output already exists")
    shell = collector._load_shell(args.usb_shell, args.socket)
    evidence = {"started_at": dt.datetime.now().astimezone().isoformat(),
                "mode": "read-only-native-history", "passes": []}
    with collector._exclusive_host_lock():
        slot = collector._read_exact_words(shell, collector.ECHO_SLOT, 1)[0]
        if slot != collector.ECHO_ORIGINAL:
            raise SystemExit("another tool owns echo; do not interleave the history probe")
        for _ in range(2):
            snapshot = {}
            for name, (address, count) in RANGES.items():
                snapshot[name] = {"address": f"0x{address:08X}",
                                  "words": collector._read_exact_words(shell, address, count)}
            for name, address in ARRAYS.items():
                snapshot[name] = {"address": f"0x{address:08X}",
                                  "words": collector._read_exact_words(shell, address, args.count)}
            evidence["passes"].append(snapshot)
        evidence["two_passes_equal"] = evidence["passes"][0] == evidence["passes"][1]
        evidence["settings_getters"] = {
            command: shell.sh(command, retries=0, timeout_ms=1000)
            for command in ("menu SetFocusPosition", "menu SetFocusMode",
                            "menu SetFocusArea", "menu SetFocusAreaSize")
        }
        evidence["echo_slot_after"] = f"0x{collector._read_exact_words(shell, collector.ECHO_SLOT, 1)[0]:08X}"
    evidence["finished_at"] = dt.datetime.now().astimezone().isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(evidence, output, indent=2)
        output.write("\n")
    print(args.output)
    print("two_passes_equal=" + str(evidence["two_passes_equal"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
