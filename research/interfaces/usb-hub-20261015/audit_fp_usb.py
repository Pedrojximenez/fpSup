#!/usr/bin/env python3
"""Offline evidence for fp 5.02 USB roles and host slot restrictions.

Reads an extracted seg0 image only. Does not import camera tools, open USB,
create a deployable patch, or infer hardware MaxSlots from software limits.
"""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BASE = 0xC0000000
KNOWN_SHA256 = "aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622"

# Thumb instruction bytes checked against the ROM, not just decompiler output.
# C066EDF0's reset polling is incorrectly collapsed by the saved decompilation;
# the instructions after that poll really do configure CONFIG.MaxSlotsEn = 1.
SITES = (
    ("host_gctl_address", 0xC066D41C, "4cf21012c2f20012",
     "Constructs GCTL address 0x2100C110."),
    ("host_role", 0xC066D452, "41f20000c1f270701060",
     "Writes GCTL=0x17701000; PRTCAPDIR[13:12]=1 (host)."),
    ("device_gctl_address_low", 0xC01E3178, "4cf21015",
     "Low half of gadget GCTL address is 0xC110."),
    ("device_gctl_address_high", 0xC01E3180, "c2f20015",
     "High half of gadget GCTL address is 0x2100."),
    ("device_role", 0xC01E31B6, "4ff400564ff440572c6824ea070030432860",
     "Gadget init's conditional role-change path clears 0x3000 and sets 0x2000 (device)."),
    ("host_enabled_slots", 0xC066EE96, "0121caf85810",
     "Writes 1 to xHCI CONFIG at 0x21000058 (MaxSlotsEn). This is not hardware MaxSlots."),
    ("device_state_slot_bound", 0xC066E56A, "621e002a01dd002107e0",
     "For valid positive IDs, software state lookup accepts only Slot ID 1; stride is 0xE58."),
    ("descriptor_slot_bound", 0xC066E59A, "621e002a01dd002107e0",
     "For valid positive IDs, descriptor lookup accepts only Slot ID 1; stride is 0x25C."),
    ("device_context_slot_bound", 0xC067079C, "0cb1012c01d9002117e0",
     "DMA device-context helper rejects zero and Slot IDs above 1."),
    ("input_context_slot_bound", 0xC06707EC, "0cb1012c01d9002118e0",
     "DMA input-context helper also rejects zero and Slot IDs above 1."),
    ("hub_class_rejection", 0xC01F4B48, "22689278092a03d10620fff799ff02e0",
     "After class driver rejects a device, bDeviceClass=9 selects error event 6."),
    ("host_class_callbacks", 0xC2E351E8, "012967c0192c67c0292c67c0392c67c0",
     "Class callback table points to MSC selection C0672900 and C0672C18/28/38."),
)


def audit(image_path):
    image = image_path.read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    checks = []
    for name, address, expected_hex, meaning in SITES:
        expected = bytes.fromhex(expected_hex)
        offset = address - BASE
        actual = image[offset:offset + len(expected)]
        checks.append({
            "name": name, "address": f"0x{address:08X}",
            "expected_hex": expected_hex, "actual_hex": actual.hex(),
            "matches": actual == expected, "meaning_if_matched": meaning,
        })
    verified = digest == KNOWN_SHA256 and all(c["matches"] for c in checks)
    result = {
        "scope": "offline static audit; no camera contact or deployment",
        "image": str(image_path.resolve()), "bytes": len(image),
        "sha256": digest, "known_seg0_sha256": KNOWN_SHA256,
        "verified_known_image": verified, "checks": checks,
    }
    if verified:
        result["assessment"] = {
            "requested_use": "SSD recording plus computer USB shell through a normal USB hub",
            "ordinary_hub_sufficient": False,
            "reason": "SSD uses fp as USB host; the existing shell uses fp as a USB device. Both select the same controller's GCTL role field. A normal hub does not bridge two hosts.",
            "stock_host_software_slots": 1,
            "hardware_max_slots": None,
            "hardware_max_slots_status": "Not measured. HCSPARAMS1 at 0x21000004, bits 7:0. Do not confuse with CONFIG.MaxSlotsEn=1.",
            "hub_patch_alone_preserves_existing_shell": False,
            "development_route": "Keep fp in host mode; add multi-device host state, hub class management and downstream routing; connect a USB-device bridge to the PC and implement a host-side shell transport. The PC-facing bridge needs its own independent USB connection/controller.",
            "driver_requirements": [
                "Own additional device/input contexts, control buffers and transfer rings; do not just relax Slot ID bounds.",
                "Implement hub descriptors, port power/reset/status changes and child attach/detach.",
                "Supply child speed, route string, root-port and applicable transaction-translator context.",
                "Account for separate USB2 and SuperSpeed hub devices in a mixed-speed USB3 hub.",
                "Serialize native shell execution and establish DMA ownership/completion; retain uncertain-command outcomes across reconnects.",
                "Validate concurrent SSD recording, bridge traffic, unplug and power transitions before claiming support.",
            ],
            "not_proven": [
                "fp silicon MaxSlots capacity or complete board USB topology",
                "A second independent controller routed to the external USB-C connector",
                "Concurrent host/device operation on fp's external connector",
                "A working hub driver, bridge transport or deployable build",
            ],
        }
    result["local_sources"] = [
        "out/decomp/full/blk_c01.c: FUN_c01e3170, FUN_c01f46a8, FUN_c01f4b20",
        "out/decomp/full/blk_c06.c: FUN_c066d418, FUN_c066edf0 (use ROM instructions), FUN_c066e560, FUN_c066e590, FUN_c066f210, FUN_c0670790, FUN_c06707e0, FUN_c0672900",
        "fpSup/fp_usb_shell/camera/worker.S: PTP gadget bulk transport and native shell dispatcher",
        "fpSup/fp_usb_shell/host/fpshd.c: interface 0, EP01 OUT and EP82 IN",
    ]
    result["primary_references"] = [
        {"url": "https://github.com/torvalds/linux/blob/master/drivers/usb/dwc3/core.h",
         "scope": "DWC3_GCTL_PRTCAPDIR and HOST=1, DEVICE=2 role definitions"},
        {"url": "https://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/extensible-host-controler-interface-usb-xhci.pdf",
         "scope": "xHCI 1.22 sections 5.3.3 (hardware MaxSlots), 5.4.7 (enabled slots), 6.2.2 (Slot Context)"},
    ]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=ROOT / "out/seg0_c0000000.bin")
    parser.add_argument("--output", type=Path, help="Save evidence JSON; otherwise print it.")
    args = parser.parse_args()
    result = audit(args.image)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if result["verified_known_image"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
