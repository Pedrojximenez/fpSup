#!/usr/bin/env python3
"""Offline negative checks for the Sensor Lab cave safety gates."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import build_res_lab_card as CARD
import imx410_plan as PLAN
import res_lab_cave_audit as AUDIT


ROOT = Path(__file__).resolve().parents[3]
R80 = ROOT / "projects/res-lab/cards/20261004-b25-menu-r80-ratiomax/fast-debug/fpSup.BIN"


class CavePlanTests(unittest.TestCase):
    def test_zero_stock_word_passes_but_occupied_word_fails_even_if_value_matches(self):
        image = bytearray(0x100)
        struct.pack_into("<I", image, 0x20, 0xF00D)
        args = dict(image_base=0x1000, cave_lo=0x1000, cave_hi=0x1100)
        self.assertEqual(AUDIT.assert_pristine_cave_plan([(0x101C, 0xBEEF, "free")], image, **args), 1)
        with self.assertRaisesRegex(ValueError, "0x00001020 stock=0x0000f00d"):
            AUDIT.assert_pristine_cave_plan([(0x1020, 0, "overwrite")], image, **args)
        with self.assertRaisesRegex(ValueError, "occupied factory cave words"):
            AUDIT.assert_pristine_cave_plan([(0x1020, 0xF00D, "same value")], image, **args)

    def test_plan_checks_actual_image_bounds_and_full_journal_exclusion(self):
        self.assertEqual((AUDIT.JOURNAL_EXCLUDED_LO, AUDIT.JOURNAL_EXCLUDED_HI),
                         (0xC072D000, 0xC0735000))
        with self.assertRaisesRegex(ValueError, "firmware image does not cover"):
            AUDIT.assert_pristine_cave_plan([(0x1020, 1, "missing")], b"\0" * 4,
                                            image_base=0x1000, cave_lo=0x1000, cave_hi=0x1100)


class CaveSectionsTests(unittest.TestCase):
    def test_failed_final_verification_leaves_no_card_directory(self):
        with tempfile.TemporaryDirectory(prefix="res-lab-atomic-build-") as parent:
            output = Path(parent) / "candidate"
            with patch.object(CARD, "_build", side_effect=RuntimeError("final verification failed")):
                with self.assertRaisesRegex(RuntimeError, "final verification failed"):
                    CARD.build(output, b25_menu=True)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(parent).iterdir()), [])

    def test_builder_relocates_legacy_layout_without_static_cave_writes(self):
        with tempfile.TemporaryDirectory(prefix="res-lab-cave-gate-") as parent:
            output = Path(parent) / "candidate"
            with CARD.source_directory():
                source = CARD.card_items()
            with self.assertRaisesRegex(ValueError, "occupied factory cave words"):
                AUDIT.assert_pristine_cave_plan(source, PLAN.FIRMWARE.read_bytes())
            built = CARD.build(output, b25_menu=True, debug=True, fast=True)
            packed = (output / "fpSup.BIN").read_bytes()
            _, records = CARD.decode(packed[:0xF000])
            self.assertGreater(AUDIT.assert_pristine_cave_sections(
                records, PLAN.FIRMWARE.read_bytes()), 0)  # shared abort/debug words
            AUDIT.assert_no_res_lab_static_cave_sections(records)
            # + imx410_bit14: getter hook, 2 BlackLevel bl, the pair-table MOVW/MOVT
            self.assertEqual(len(built["core"]["dynamic_stock_sites"]), 35 + 5 * PLAN.SLX.WITH_BIT14 + PLAN.WITH_SEL_LOG + 2 * PLAN.WITH_BINFILT)

    def test_strict_guard_rejects_fixed_sensor_payload_and_crossing_section(self):
        for address, size in ((0xC0730000, 4), (0xC072FFFC, 8),
                              (0xC0734FFC, 8)):
            with self.subTest(address=hex(address)):
                with self.assertRaisesRegex(ValueError, "fixed Sensor Lab cave"):
                    AUDIT.assert_no_res_lab_static_cave_sections([(address, 0x40, b"X" * size)])

    def test_strict_guard_rejects_static_arena_fill(self):
        with self.assertRaisesRegex(ValueError, "pre-fills CAVE_BUMP arena"):
            AUDIT.assert_no_res_lab_static_cave_sections(
                [(AUDIT.CAVE_ARENA_LO, 0x40, b"X" * 8)])

    def test_product_plan_rejects_full_unjournaled_cave_even_when_stock_is_zero(self):
        for address in (AUDIT.JOURNAL_EXCLUDED_LO,
                        AUDIT.CAVE_ARENA_LO,
                        0xC072F000,
                        AUDIT.RES_LAB_STATIC_LO,
                        AUDIT.JOURNAL_EXCLUDED_HI - 4):
            with self.subTest(address=hex(address)):
                with self.assertRaisesRegex(ValueError, "fixed Sensor Lab cave"):
                    AUDIT.assert_no_res_lab_static_cave_plan(
                        [(address, 0, "zero stock still forbidden")])

    def test_strict_guard_permits_staging_pool_and_stock_hooks(self):
        records = [(0, 0x20, b"A" * 16), (0x100, 0x30, b"B" * 16),
                   (0xC043CCF8, 0x40, b"C" * 4),
                   (0xC072F000, 0x50, b"D" * 4)]  # maintained USB worker ABI
        self.assertEqual(AUDIT.assert_no_res_lab_static_cave_sections(records), 2)

    def test_archived_r80_fails_both_pristine_and_strict_gates(self):
        self.assertTrue(R80.is_file(), f"archived r80 card missing: {R80}")
        packed = R80.read_bytes()
        magic, count, _, length = struct.unpack_from("<4sIII", packed)
        self.assertEqual(magic, b"VBIN")
        # r80 appends the private menu pack after the loader's declared VBIN.
        _, records = CARD.decode(packed[:16 + count * 8 + length])
        image = PLAN.FIRMWARE.read_bytes()
        with self.assertRaisesRegex(ValueError, "0xc0732a40 stock=0xffffffff"):
            AUDIT.assert_pristine_cave_sections(records, image)
        # Reconstruct the fixed writes from the archived bytes.  This is the
        # exact prebuild plan shape, independent of today's evolving plan.
        items = [(address + index * 4, word, "archived r80")
                 for address, _, data in records if address >= 0x40000000
                 for index, (word,) in enumerate(struct.iter_unpack("<I", data))]
        with self.assertRaisesRegex(ValueError, "0xc0732a40 stock=0xffffffff"):
            AUDIT.assert_pristine_cave_plan(items, image)
        with self.assertRaisesRegex(ValueError, "fixed Sensor Lab cave"):
            AUDIT.assert_no_res_lab_static_cave_sections(records)


if __name__ == "__main__":
    unittest.main()
