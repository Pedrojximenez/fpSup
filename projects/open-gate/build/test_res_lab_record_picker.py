#!/usr/bin/env python3
"""Exercise the first recording picker hit from the compact USER image.

The standalone imx410_fmt test places PROFILE_ID at the historical distance
from RECIPE.  This test runs the bytes after Sensor Lab packing so
cross-region address arithmetic must follow the actual USER layout.
"""
from __future__ import annotations

import struct
import unittest

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1,
                               UC_ARM_REG_R2, UC_ARM_REG_SP)

import imx410_plan as PL
import build_res_lab_card as CARD
from res_lab_user_pack import res_lab_pack
from test_imx410_fmt import OG3K, TAB


USER_BASE = 0x45010000
KEY = USER_BASE + 0x10000
STACK = USER_BASE + 0x20000
DONE = USER_BASE + 0x30000
BACK = 0xC043CCFC
IMAGER = 0xC343B588
DESCRIPTOR = 0xC2F1E654


class RecordPickerTests(unittest.TestCase):
    def _pack(self, private_menu):
        image = PL.FIRMWARE.read_bytes()
        saved = PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW
        try:
            PL.WITH_SL_EXCL = private_menu
            PL.WITH_RATE_ROW = PL.WITH_BIT_ROW = not private_menu
            with CARD.source_directory():
                return res_lab_pack(CARD.card_items(), firmware=image), image
        finally:
            PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = saved

    def _run_picker(self, pack, image, body):
        mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        for address, size in ((0x45000000, 0x40000), (0xC0430000, 0x10000),
                              (0xC0700000, 0x100000), (0xC0B00000, 0x200000),
                              (0xC2F00000, 0x100000), (0xC3400000, 0x100000)):
            mu.mem_map(address, size)
        mu.mem_write(0xC0B00000, image[0xC0B00000 - PL.B:0xC0D00000 - PL.B])
        mu.mem_write(USER_BASE, body)
        mu.mem_write(DESCRIPTOR, struct.pack("<4I", 0xC0B59500, 70,
                                             0xC0B59DC0, 70))
        mu.mem_write(IMAGER, struct.pack("<I", DESCRIPTOR))
        mu.mem_write(KEY, b"CUST30\0")
        axis = pack.address_map(PL.AXIS)
        mu.mem_write(USER_BASE + axis, struct.pack(f"<{len(OG3K)}I", *OG3K))
        # Force recipe calculation on this first hit, as on a fresh boot.
        mu.mem_write(USER_BASE + pack.address_map(PL.RECIPE),
                     bytes(PL.RECIPE_WORDS * 4))
        stopped_at_back = []
        mu.hook_add(UC_HOOK_CODE,
                    lambda emu, address, _size, _data:
                    (stopped_at_back.append(address), emu.emu_stop())
                    if address == BACK else None)
        mu.reg_write(UC_ARM_REG_R0, 0xAAAA0000)
        mu.reg_write(UC_ARM_REG_R1, TAB[12])
        mu.reg_write(UC_ARM_REG_R2, KEY)
        mu.reg_write(UC_ARM_REG_SP, STACK)
        mu.reg_write(UC_ARM_REG_LR, DONE)
        mu.emu_start(USER_BASE + pack.address_map(PL.FMT_CODE), DONE,
                     count=2_000_000)
        self.assertFalse(stopped_at_back, "picker unexpectedly used stock entry")
        entry = USER_BASE + pack.address_map(PL.ENTRY_ADDR)
        self.assertEqual(mu.reg_read(UC_ARM_REG_R0), entry)
        return struct.unpack("<I", mu.mem_read(entry + 4, 4))[0]

    def test_relocated_picker_publishes_the_declared_profile_id(self):
        for private_menu in (False, True):
            with self.subTest(private_menu=private_menu):
                pack, image = self._pack(private_menu)
                body = pack.materialize(USER_BASE)
                self.assertEqual(self._run_picker(pack, image, body),
                                 PL.PRIVATE_PROFILE,
                                 "recording picker stored a USER table pointer as profile ID")

    def test_old_fixed_offset_mutation_is_detected(self):
        """Replay the r81 LDR against the compact image; it reads COLTAB."""
        for private_menu in (False, True):
            with self.subTest(private_menu=private_menu):
                pack, image = self._pack(private_menu)
                body = bytearray(pack.materialize(USER_BASE))
                fmt = next(s for s in pack.spans if s.name == "imx410_fmt")
                lo, hi = fmt.offset, fmt.offset + fmt.old_end - fmt.old_start
                stores = [offset for offset in range(lo, hi, 4)
                          if struct.unpack_from("<I", body, offset)[0] == 0xE581C004]
                self.assertEqual(len(stores), 1)
                store = stores[0]
                self.assertEqual(struct.unpack_from("<I", body, store - 4)[0],
                                 0xE59CC000)  # LDR ip, [ip]
                # Historical r81 was LDR ip, [r7, #(PROFILE_ID - RECIPE)].
                # Replace the now-relocatable absolute load with that instruction.
                struct.pack_into("<3I", body, store - 12,
                                 0xE1A00000, 0xE1A00000,
                                 0xE597C000 | (PL.PROFILE_ID - PL.RECIPE))
                old_delta = PL.PROFILE_ID - PL.RECIPE
                actual_offset = pack.address_map(PL.RECIPE) + old_delta
                wrong_value = struct.unpack_from("<I", body, actual_offset)[0]
                self.assertNotEqual(wrong_value, PL.PRIVATE_PROFILE)
                self.assertEqual(self._run_picker(pack, image, bytes(body)), wrong_value)


if __name__ == "__main__":
    unittest.main()
