#!/usr/bin/env python3
"""Reproduce the archived r80 cave overwrite with the offline Unicorn loader.

Run with host cache-line sysctl access: ``python3 -B -m unittest -v
test_res_lab_warm_cave``. The harness stubs the card's payload entry;
this tests loader, journal, and power-off behavior, not Sensor Lab UI code.
"""

import hashlib
from pathlib import Path
import re
import struct
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "fpSup/fp_usb_shell"))
import test_loader_hook as loader

CARD = ROOT / "projects/res-lab/cards/20261004-b25-menu-r80-ratiomax/fast-debug"
CARD_SHA256 = "a98c1e9e60d9a6a9a3fd7b2648df23be115c3f9a60acdf4329b6d1d3773e4e08"
AUTORUN_SHA256 = "b00ce0dc23fbee33d46267798c417c43800818d951b4da0d3e671de7809d9665"
FIRMWARE_SHA256 = "92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4"
RATE_CAVE = (0xC0732A40, 0xC0732C84)


class ArchivedResLabCaveTest(unittest.TestCase):
    def test_r80_rate_cave_survives_both_poweroff_callbacks(self):
        self.assertIsNotNone(loader.Uc, "Unicorn is required for this test")
        self.assertTrue(loader.IMAGE.is_file(), "factory firmware image is required")
        blob = (CARD / "fpSup.BIN").read_bytes()
        self.assertEqual(hashlib.sha256(blob).hexdigest(), CARD_SHA256)
        autorun = (CARD / "AutoRun.txt").read_bytes()
        self.assertEqual(hashlib.sha256(autorun).hexdigest(), AUTORUN_SHA256)
        text = autorun.decode()
        words = {int(address, 16): int(value, 16) for address, value in
                 re.findall(r"^mem set (0x[0-9A-Fa-f]+) (0x[0-9A-Fa-f]+)", text, re.M)
                 if loader.CAVE_LOW <= int(address, 16) < loader.CAVE_LOW + 0x200}
        self.assertEqual(len(words), 79)

        cam = loader.Camera(words, blob)
        self.assertEqual(hashlib.sha256(cam.stock).hexdigest(), FIRMWARE_SHA256)
        branch = 0xEB000000 | (((loader.CAVE_LOW + 4 - loader.SITE - 8) >> 2) & 0xFFFFFF)
        cam.mu.mem_write(loader.SITE, struct.pack("<I", branch))
        r0, sp = cam.call(loader.CAVE_LOW + 4, r0=0xC0BABDD8, r1=1,
                          lr=loader.AR_RET, sp=loader.STACK - 0x1004)
        self.assertEqual((r0, sp), (0, loader.STACK - 0x1004))
        self.assertIsNone(cam.ar_started)
        self.assertIn("ENTRY", cam.calls)
        self.assertEqual([flag for _, flag in cam.registered], [0, 1])

        # Stage2 journals each non-cave VBIN section plus its splash draw patch.
        expected = [(address, (size + 3) & ~3) for address, size in cam.sections()
                    if address >= 0x40000000 and not loader.CAVE_LO <= address < loader.CAVE_HI]
        self.assertEqual(len(expected), 296)
        expected.append((loader.DRAW, 4))
        context = cam.word(loader.MARK + 8)
        journal = cam.word(context + 8)
        for address, size in expected:
            self.assertEqual((cam.word(journal), cam.word(journal + 4)),
                             (address, size))
            original = bytes(cam.mu.mem_read(journal + 8, size))
            self.assertEqual(original, cam.stock[address - 0xC0000000:
                                                 address - 0xC0000000 + size])
            journal += 8 + size
        self.assertEqual(cam.word(journal), 0)

        low, high = RATE_CAVE
        stock = cam.stock[low - 0xC0000000:high - 0xC0000000]
        installed = bytes(cam.mu.mem_read(low, high - low))
        self.assertEqual(sum(a != b for a, b in zip(stock, installed)), 317)
        self.assertEqual(sum(a != b and a != 0 for a, b in zip(stock, installed)), 67)

        callback = cam.word(context + 4)
        for _ in range(2):
            cam.call(callback, r0=context, r1=4)
            for address, size in expected:
                restored = bytes(cam.mu.mem_read(address, size))
                self.assertEqual(restored, cam.stock[address - 0xC0000000:
                                                     address - 0xC0000000 + size])
            self.assertEqual(bytes(cam.mu.mem_read(low, high - low)), installed)
        self.assertEqual(cam.word(loader.MARK), 2)


if __name__ == "__main__":
    unittest.main()
