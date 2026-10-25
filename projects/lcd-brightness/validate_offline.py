#!/usr/bin/env python3
"""Run real-firmware emulation and save reproducible local evidence."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import unittest

from firmware import Firmware, make_plan
from emulate import CameraModel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    firmware = Firmware()
    plan = make_plan(firmware)
    suite = unittest.defaultTestLoader.loadTestsFromName("test_brightness")
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    text = stream.getvalue()
    print(text, end="")
    passed = result.wasSuccessful() and result.testsRun == 11 and not result.skipped
    import unicorn
    report = {
        "status": "passed" if passed else "failed_or_unverified",
        "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped),
        "firmware": firmware.identity,
        "python": platform.python_version(), "unicorn": unicorn.__version__,
        "sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(Path(__file__).parent.glob("*.py"))},
        "camera_access_performed": False,
        "physical_luminance_measured": False,
        "measured_nits": None,
        "emulation_boundary": {
            "executed": "original Thumb coarse/fine/HAL brightness routines and cache resets",
            "stubbed": "c00f4560 command dispatcher; arguments and original command sequence checked",
            "seeded": "runtime descriptor root c2eff150; ready state 2; zeroed BSS",
            "not_executed": "complete menu, boot/init, native transport, panel electronics or automatic-mode thread",
            "abi_checked": "r4-r11 preservation and SP restoration; no claim about stock call-site 8-byte alignment",
        },
    }
    if passed:
        report["samples"] = {
            "stock_maximum": CameraModel(firmware).run("coarse", 6),
            "stock_fine99": CameraModel(firmware).run("fine", 99),
            "stock_fine100_rejected": CameraModel(firmware).run("fine", 100),
            "stock_hal100_false_success": CameraModel(firmware).run("hal_fine", 100),
            "candidate_maximum": CameraModel(firmware, plan).run("coarse", 6),
        }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "emulation.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out / "test-results.txt").write_text(text)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
