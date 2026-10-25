#!/usr/bin/env python3
"""Save offline current-control findings, optional real-ARM tests and evidence."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import unittest

from firmware import Firmware
from pmic import (DATASHEET, INIT_TABLES, INIT_SIZE, INIT, SET_DIM, ENABLE,
                  POWER_TEST_INIT, LCD_ENABLE_CALLBACK, PmicModel,
                  init_entries, make_current_plan)


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--emulate", action="store_true")
    args = parser.parse_args()
    firmware = Firmware()
    args.out.mkdir(parents=True, exist_ok=True)
    plans = [make_current_plan(firmware, dim) for dim in range(19, 32)]
    audit = {
        "status": "offline_source_and_datasheet_analysis",
        "date": "2026-10-25", "firmware": firmware.identity,
        "camera_access_performed": False, "measured_nits": None,
        "live_dim7": None, "external_sense_resistance_ohms": None,
        "source": {"url": DATASHEET, "document": "DS5035C/D-01, February 2020",
                   "printed_pages": [21, 28, 32], "kind": "manufacturer datasheet"},
        "pmic": {"model": "RT5035C", "channel": 7,
                 "dim7_register": 4, "dim7_mask": 31,
                 "shared_vout8_mask": 224, "stock_vout8_bits": 160,
                 "enable_register": 14, "enable_mask": 4,
                 "nominal_current_fraction": "(DIM7 + 1) / 32",
                 "absolute_current_formula_amps": "0.3 V / REXT_ohms * (DIM7 + 1) / 32"},
        "init_tables": [{"base": hex(base), "size": INIT_SIZE,
                         "entries": [{"register": r, "value": v} for r, v in init_entries(firmware, base)]}
                        for base in INIT_TABLES],
        "source_facts": [
            "Both native initialization branches write register 4 = 0xb2, DIM7 = 18.",
            "Native set_dim accepts 0..31 and writes register 4 = 0xa0 | dim.",
            "LCD callback c0308520 calls PMIC EN7 control via its native vtable.",
            "Native power-test initialization c0042f30 separately writes DIM7 = 31.",
            "BootGui calls normal initialization c0020958; a later conditional path calls c0043040 (power test).",
        ],
        "inferences": [
            "The normal init tables leave 13 higher nominal CH7 current codes (19..31).",
            "The LCD EN7 callback strongly links CH7 to the LCD backlight; PCB wiring is not measured.",
            "At an unchanged external resistor, DIM7 31/18 gives nominal current ratio 32/19, about 1.6842.",
        ],
        "unresolved": [
            "Actual running DIM7 value and any path-specific or external writes.",
            "Panel command A3 indexed-register meanings and interaction with current dimming.",
            "Physical REXT, LED ratings, optical gain, power, temperature and sustained behavior.",
            "No panel command or current code establishes a measured nit value.",
        ],
        "deployment": "No runnable camera/card artifact is emitted.",
    }
    save_json(args.out / "backlight-current-audit.json", audit)
    save_json(args.out / "current-candidates.json", {"schema": "fp-backlight-current-candidates-v1",
              "scope": "13 offline candidates; not a recommendation to apply maximum current", "candidates": plans})
    # Preserve exact instructions used for the principal findings, independently
    # of the decompiler's pretty-printed C. Capstone is analysis-only here.
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    listing = []
    for label, address, size in (("normal_init", INIT, 0xD8), ("set_dim", SET_DIM, 0x90),
            ("enable", ENABLE, 0x90), ("power_test_init", POWER_TEST_INIT, 0x70),
            ("lcd_enable_callback", LCD_ENABLE_CALLBACK, 0x58)):
        listing.append(f"{label} @ {address:#x}")
        for insn in md.disasm(firmware.read(address, size), address):
            listing.append(f"{insn.address:08x}  {insn.bytes.hex():8s}  {insn.mnemonic:8s} {insn.op_str}")
        listing.append("")
    (args.out / "native-pmic.asm.txt").write_text("\n".join(listing))
    if not args.emulate:
        print("Saved static offline evidence; ARM emulation was not requested.")
        return
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name)
                               for name in ("test_brightness", "test_pmic"))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    output = stream.getvalue()
    print(output, end="")
    verified = result.wasSuccessful() and result.testsRun == 22 and not result.skipped
    import unicorn
    report = {"status": "passed" if verified else "failed_or_unverified",
        "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "firmware": firmware.identity,
        "python": platform.python_version(), "unicorn": unicorn.__version__,
        "sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(Path(__file__).parent.glob("*.py"))},
        "camera_access_performed": False, "physical_luminance_measured": False,
        "emulation_boundary": {
            "executed": "native ARM PMIC init, setter, enable, masked helper, power-test init and LCD callback; prior Thumb brightness routines",
            "stubbed": "I2C reads/writes, branch selector and LCD command dispatcher",
            "fixtures": "native PMIC vtable; synthetic adapter pointers; dictionary registers; zeroed BSS",
            "not_proven": "complete boot path, physical I2C, PCB wiring/current/luminance/thermal suitability or live register state",
            "abi": "SP and r4-r11 preservation; no new injected ARM code is built",
        }}
    if verified:
        report["samples"] = {
            "normal_init_selector0": PmicModel(firmware, selector=0).run("init"),
            "normal_init_selector1": PmicModel(firmware, selector=1).run("init"),
            "candidate_dim20_init": PmicModel(firmware, plan=make_current_plan(firmware, 20)).run("init"),
            "native_set_dim31": PmicModel(firmware).run("set_dim", 31),
            "native_lcd_enable": PmicModel(firmware).run("lcd_enable", 1),
            "native_power_test_init": PmicModel(firmware).run("power_test_init"),
        }
    save_json(args.out / "pmic-emulation.json", report)
    (args.out / "test-results.txt").write_text(output)
    raise SystemExit(0 if verified else 1)


if __name__ == "__main__":
    main()
