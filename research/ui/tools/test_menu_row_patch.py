#!/usr/bin/env python3
"""Offline tests for the data-only menu row.  No card, no camera."""
import struct
import unittest

import menu_row_patch as M
import nbr_stock as N


class Plan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nbr = N.load()
        cls.plan = M.plan(["3K 3008x2000"])

    def test_it_is_three_writes_and_nothing_else(self):
        self.assertEqual(len(self.plan["sections"]), 3)
        self.assertEqual([s["address"] for s in self.plan["sections"]],
                         [0xC12C7CF8, 0xC0D4DE04, 0xC1A709BC])

    def test_the_stock_list_really_has_two_rows(self):
        self.assertEqual(self.plan["rows_before"], 2)
        self.assertEqual(self.plan["rows_after"], 3)

    def test_the_new_csv_parses_back_through_the_stock_decoder(self):
        rows = N.parse_menu(self.plan["csv"], self.nbr.strings("English"))
        self.assertEqual([r["NO"] for r in rows], ["1", "2", "3"])
        self.assertEqual(rows[0]["text"], "UHD 3840x2160")     # id, resolved
        self.assertEqual(rows[2]["text"], "3K 3008x2000")      # literal
        self.assertEqual([r["Enabled"] for r in rows], ["1", "1", "1"])
        self.assertEqual([r["Enabled2"] for r in rows], ["2", "2", "2"])

    def test_it_keeps_the_stock_header_so_the_columns_still_line_up(self):
        stock = self.nbr.read(M.RESOLUTION_LIST).decode("utf-8-sig").splitlines()[0]
        mine = self.plan["csv"].decode("utf-8-sig").splitlines()[0]
        self.assertEqual(mine, stock)

    def test_the_repoint_is_the_one_nbr_stock_derives(self):
        address, words = self.nbr.repoint(M.RESOLUTION_LIST, 0xC12C7CF8,
                                          len(self.plan["csv"]))
        section = self.plan["sections"][1]
        self.assertEqual((section["address"], section["data"]), (address, words))

    def test_the_controller_max_is_rows_minus_one_as_a_big_endian_float(self):
        self.assertEqual(self.plan["stock_max"], 1.0)
        value = struct.unpack(">f", self.plan["sections"][2]["data"])[0]
        self.assertEqual(value, self.plan["rows_after"] - 1)
        self.assertEqual(self.plan["sections"][2]["data"], b"\x40\x00\x00\x00")

    def test_five_rows_would_need_a_max_of_four(self):
        five = M.plan(["a", "b", "c"])
        self.assertEqual(five["rows_after"], 5)
        self.assertEqual(struct.unpack(">f", five["sections"][2]["data"])[0], 4.0)

    def test_the_victim_has_room_and_is_not_the_list_itself(self):
        self.assertGreaterEqual(self.plan["victim"].size, len(self.plan["csv"]))
        self.assertNotEqual(self.plan["victim"].path, M.RESOLUTION_LIST)

    def test_the_three_writes_do_not_overlap(self):
        M.check_disjoint(self.plan["sections"])          # raises if they do


class OneWriteProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nbr = N.load()
        cls.probe = M.probe(1, "ZZZZ")

    def test_it_is_one_write_at_the_stock_address(self):
        self.assertEqual(len(self.probe["sections"]), 1)
        entry = self.nbr.find(M.RESOLUTION_LIST)
        self.assertEqual(self.probe["sections"][0]["address"], entry.data_address)

    def test_the_size_is_unchanged_so_no_repoint_is_needed(self):
        self.assertEqual(len(self.probe["csv"]), len(self.nbr.read(M.RESOLUTION_LIST)))

    def test_only_that_row_changed(self):
        rows = N.parse_menu(self.probe["csv"])
        stock = self.nbr.menu(M.RESOLUTION_LIST)
        self.assertEqual(rows[0]["TEXT"], "ZZZZ")
        self.assertEqual(rows[1:], stock[1:])
        self.assertEqual(len(rows), len(stock))

    def test_a_different_length_is_refused_by_the_length_check(self):
        # Checking only "it raises" would also pass if the length check were
        # gone and the later size check caught it -- so check which one fired.
        for text in ("ZZ", "ZZZZZ"):
            with self.assertRaises(M.PlanError) as caught:
                M.probe(1, text)
            self.assertIn("same length", str(caught.exception))

    def test_a_row_that_does_not_exist(self):
        with self.assertRaises(M.PlanError):
            M.probe(9, "ZZZZ")


class Refusals(unittest.TestCase):
    def test_a_victim_with_no_room(self):
        with self.assertRaises(M.PlanError):
            M.plan(["x" * 200], victim="../MenuB12/data/ListB12/B2_5_1.cvm")

    def test_writing_over_the_list_itself(self):
        with self.assertRaises(M.PlanError):
            M.plan(["x"], victim=M.RESOLUTION_LIST)

    def test_a_label_with_a_comma(self):
        with self.assertRaises(M.PlanError):
            M.plan(["3K, wide"])

    def test_a_list_that_is_not_a_NO_TEXT_list(self):
        with self.assertRaises(M.PlanError):
            # its header is NO,IMAGE,enable,Left,Right,FocusOn
            M.plan(["x"], target="../ButtonMenu/data/ListColorButtonMenu.cvm")


class AutoRunLines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nbr = N.load()
        cls.plan = M.plan(["3K 3008x2000"])

    def test_every_line_is_a_word_aligned_mem_set(self):
        for section in self.plan["sections"]:
            lines = M.autorun_lines(section, self.nbr.image)
            self.assertEqual(len(lines), (len(section["data"]) + 3) // 4
                             + (1 if section["address"] & 3 else 0))
            for line in lines:
                address = int(line.split()[2], 16)
                self.assertEqual(address & 3, 0)

    def test_replaying_the_lines_reproduces_the_bytes_and_keeps_the_neighbours(self):
        for section in self.plan["sections"]:
            start = section["address"] & ~3
            end = (section["address"] + len(section["data"]) + 3) & ~3
            memory = bytearray(self.nbr.image[start - N.BASE:end - N.BASE])
            for line in M.autorun_lines(section, self.nbr.image):
                _m, _s, addr, word = line.split()
                struct.pack_into("<I", memory, int(addr, 16) - start, int(word, 16))
            at = section["address"] - start
            self.assertEqual(bytes(memory[at:at + len(section["data"])]), section["data"])
            # every padding byte, before AND after, must still be the stock one
            self.assertEqual(bytes(memory), self.nbr.image[start - N.BASE:end - N.BASE]
                             [:at] + section["data"]
                             + self.nbr.image[section["address"] + len(section["data"]) - N.BASE:
                                              end - N.BASE])

    def test_an_unaligned_section_keeps_the_bytes_on_both_sides(self):
        # The three real writes all start word-aligned, so force the other case.
        section = {"address": 0xC12C7CF9, "data": b"\xAA\xBB\xCC", "what": "probe"}
        start, end = 0xC12C7CF8, 0xC12C7D00
        memory = bytearray(self.nbr.image[start - N.BASE:end - N.BASE])
        for line in M.autorun_lines(section, self.nbr.image):
            _m, _s, addr, word = line.split()
            struct.pack_into("<I", memory, int(addr, 16) - start, int(word, 16))
        stock = self.nbr.image[start - N.BASE:end - N.BASE]
        self.assertEqual(bytes(memory[1:4]), b"\xAA\xBB\xCC")
        self.assertEqual(memory[0], stock[0])
        self.assertEqual(bytes(memory[4:]), stock[4:])


if __name__ == "__main__":
    unittest.main()
