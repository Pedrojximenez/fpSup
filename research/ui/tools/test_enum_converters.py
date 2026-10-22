#!/usr/bin/env python3
"""Offline tests for the enum -> display-state converters."""
import struct
import unittest
from pathlib import Path

import enum_converters as E

FORMATS_BIN = (Path(__file__).resolve().parents[3] / "research" / "other" / "external"
               / "fpsup-formats-v0.3.0a" / "fpSup.BIN")
RESOLUTION = 0xC06BDA3C


def formats_sections() -> dict:
    data = FORMATS_BIN.read_bytes()
    count = struct.unpack_from("<I", data, 4)[0]
    table = [struct.unpack_from("<II", data, 16 + 8 * i) for i in range(count)]
    out, offset = {}, 16 + 8 * count
    for address, length in table:
        out[address] = data[offset:offset + length]
        offset += length
    return out


class Census(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = E.converters(E._image())
        cls.by_site = {r["movw"]: r for r in cls.rows}

    def test_there_is_a_whole_family_of_them(self):
        self.assertGreater(len(self.rows), 300)

    def test_the_resolution_one_matches_the_documented_table(self):
        # research/ui/README.md section 4: {3,0} {2,1} {4,2} at 0xC2E4020C
        row = self.by_site[RESOLUTION]
        self.assertEqual(row["table"], 0xC2E4020C)
        self.assertEqual(row["count"], 3)
        self.assertEqual(row["pairs"], [(3, 0), (2, 1), (4, 2)])

    def test_the_patch_sites_are_the_three_words_a_card_rewrites(self):
        row = self.by_site[RESOLUTION]
        self.assertEqual((row["movw"], row["movt"], row["count_at"]),
                         (0xC06BDA3C, 0xC06BDA40, 0xC06BDA48))

    def test_every_table_is_in_the_pair_table_region(self):
        for row in self.rows:
            self.assertTrue(E.TABLES[0] <= row["table"] < E.TABLES[1])

    def test_counts_fit_an_eight_bit_immediate(self):
        for row in self.rows:
            self.assertLess(row["count"], 64)


class Patch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.row = next(r for r in E.converters(E._image()) if r["movw"] == RESOLUTION)

    @unittest.skipUnless(FORMATS_BIN.exists(), "the fpSup-Formats card is not in the tree")
    def test_we_reproduce_the_three_words_that_card_really_writes(self):
        sections = formats_sections()
        got = E.patch(self.row, 0xC0731C40, 6)
        self.assertEqual(len(got), 3)
        for address, word in got:
            self.assertEqual(struct.pack("<I", word), sections[address],
                             f"at 0x{address:08X}")

    def test_the_rewritten_words_decode_back_to_what_we_asked_for(self):
        for table, count in ((0xC0731C40, 6), (0xC0740000, 3), (0xC0700004, 63)):
            words = dict(E.patch(self.row, table, count))
            low = E._movw(words[self.row["movw"]] & 0x0FFFFFFF | 0x03000000)
            high = E._movt(words[self.row["movt"]] & 0x0FFFFFFF | 0x03400000)
            self.assertEqual(low[0] | (high[0] << 16), table)
            self.assertEqual(words[self.row["count_at"]] & 0xFF, count)

    def test_it_keeps_the_destination_register(self):
        original = struct.unpack_from("<I", E._image(), self.row["movw"] - E.BASE)[0]
        words = dict(E.patch(self.row, 0xC0731C40, 6))
        self.assertEqual((words[self.row["movw"]] >> 12) & 0xF,
                         (original >> 12) & 0xF)

    def test_a_count_that_cannot_be_an_immediate_is_refused(self):
        for count in (0, 64, 300):
            with self.assertRaises(ValueError):
                E.patch(self.row, 0xC0731C40, count)


if __name__ == "__main__":
    unittest.main()
