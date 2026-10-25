#!/usr/bin/env python3
"""Emit an offline LCD brightness audit and guarded patch plan, never a card."""
import argparse
import json
from pathlib import Path

from firmware import Firmware, make_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    firmware = Firmware()
    plan = make_plan(firmware)
    audit = {
        "firmware": firmware.identity,
        "coarse_manual_table": [{"index": i, "command_bytes": firmware.coarse(i),
            "matching_native_fine_values": [v for v in range(1, 100)
                if firmware.fine(v) == firmware.coarse(i)]} for i in range(7)],
        "native_fine_table": [{"value": v, "command_bytes": firmware.fine(v)}
                              for v in range(1, 100)],
        "candidate": plan,
        "physical_luminance_measured": False,
        "camera_access_performed": False,
        "emulation_performed_by_this_builder": False,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    for name, content in (("audit.json", audit), ("unused-lut100-candidate.patch.json", plan)):
        (args.out / name).write_text(json.dumps(content, indent=2) + "\n")
    print(f"Offline audit and guarded patch plan saved to {args.out.resolve()}")
    print("Stock maximum equals native fine 99; candidate uses the REJECTED fine-100 LUT entry.")
    print("No measured nits, deployable card, or camera operation.")


if __name__ == "__main__":
    main()
