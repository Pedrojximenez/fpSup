#!/usr/bin/env python3
"""Offline tests for the stock NBR directory.

The strongest one reproduces, from the format alone, the exact 8 bytes that a
third party's camera-verified card writes.  Nothing here touches a camera.

    cd research/ui/tools && python3 -B -m unittest test_nbr_stock
"""
import struct
import unittest
from pathlib import Path

import nbr_stock as N

RESOLUTION_LIST = "../MenuB12/data/ListB12/B2_5_4.cvm"
FORMATS_BIN = (Path(__file__).resolve().parents[3] / "research" / "other" / "external"
               / "fpsup-formats-v0.3.0a" / "fpSup.BIN")


def formats_sections() -> dict:
    """{address: bytes} for every section of the fpSup-Formats payload."""
    data = FORMATS_BIN.read_bytes()
    count = struct.unpack_from("<I", data, 4)[0]
    table = [struct.unpack_from("<II", data, 16 + 8 * i) for i in range(count)]
    out, offset = {}, 16 + 8 * count
    for address, length in table:
        out[address] = data[offset:offset + length]
        offset += length
    return out


class Container(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nbr = N.load()

    def test_the_container_is_nbr_1_5(self):
        self.assertEqual(self.nbr.container, 0xC0D22400)
        self.assertEqual(self.nbr.version, 0x01050000)

    def test_it_splits_into_four_records_and_closes(self):
        tags = [tag for tag, _a, _s in self.nbr.records]
        self.assertEqual(tags, [1, 2, 0x20001, 0xFFFFFFFF])
        self.assertEqual(self.nbr.records[-1][2], 8)

    def test_the_directory_has_2259_entries_sorted_by_key(self):
        report = self.nbr.verify()
        self.assertEqual(report["entries"], 2259)
        self.assertTrue(report["sorted_by_key"])

    def test_every_key_is_the_fnv1a_of_the_path_it_points_at(self):
        report = self.nbr.verify()
        self.assertEqual(report["keys_agree"], 2259)

    def test_every_xci_entry_points_at_an_xci_blob(self):
        report = self.nbr.verify()
        self.assertEqual(report["xci"], 2005)
        self.assertEqual(report["xci_blob_at_data_address"], 2005)

    def test_the_menu_is_195_csv_resources(self):
        cvm = [e for e in self.nbr.entries if e.extension == "cvm"]
        self.assertEqual(len(cvm), 195)
        self.assertIn(RESOLUTION_LIST, {e.path for e in cvm})


class ResolutionRowList(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nbr = N.load()
        cls.entry = cls.nbr.find(RESOLUTION_LIST)

    def test_the_stock_list_has_two_rows(self):
        text = self.nbr.read(RESOLUTION_LIST).decode("utf-8-sig")
        rows = [line for line in text.splitlines() if line]
        self.assertEqual(rows[0], "NO,TEXT,Popup,IMAGE,Enabled,Enabled2")
        self.assertEqual(rows[1], "1,0313,Popup,blank,1,2")
        self.assertEqual(rows[2], "2,0314,Popup,blank,1,2")
        self.assertEqual(len(rows), 3)          # header + UHD + FHD

    def test_it_is_entry_68_and_its_repoint_word_is_the_patched_address(self):
        self.assertEqual(self.entry.index, 68)
        self.assertEqual(self.entry.entry_address, 0xC0D4DDFC)
        self.assertEqual(self.entry.patch_address, 0xC0D4DE04)
        self.assertEqual(self.entry.data_address, 0xC0F8E7EC)
        self.assertEqual(self.entry.size, 89)

    @unittest.skipUnless(FORMATS_BIN.exists(), "the fpSup-Formats card is not in the tree")
    def test_we_reproduce_the_bytes_that_card_really_writes(self):
        sections = formats_sections()
        self.assertIn(0xC0D4DE04, sections)
        # The card puts its six-row CSV at 0xC12C7CF8 and says it is 156 bytes.
        self.assertIn(0xC12C7CF8, sections)
        new_csv = sections[0xC12C7CF8]
        address, words = self.nbr.repoint(RESOLUTION_LIST, 0xC12C7CF8, len(new_csv))
        self.assertEqual(address, 0xC0D4DE04)
        self.assertEqual(words, sections[0xC0D4DE04])

    @unittest.skipUnless(FORMATS_BIN.exists(), "the fpSup-Formats card is not in the tree")
    def test_the_replacement_csv_really_is_a_six_row_list(self):
        new_csv = formats_sections()[0xC12C7CF8].decode("utf-8-sig")
        rows = [line for line in new_csv.splitlines() if line]
        self.assertEqual(len(rows), 7)          # header + six rows
        self.assertTrue(rows[0].startswith("NO,TEXT,"))


class MenuTextIsData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nbr = N.load()
        cls.english = cls.nbr.strings("English")

    def test_english_has_2728_strings_and_every_key_checks(self):
        # strings() raises if any key is not fnv1a(id), so getting here is the check
        self.assertEqual(len(self.english), 2728)

    def test_all_seventeen_languages_decode(self):
        langs = [e.path.rsplit("/", 1)[-1][:-5] for e in self.nbr.entries
                 if e.extension == "nloc"]
        self.assertEqual(len(langs), 17)
        for language in langs:
            table = self.nbr.strings(language)
            self.assertGreater(len(table), 2000, language)
            self.assertIn("0313", table, language)

    def test_the_resolution_rows_resolve_to_their_visible_text(self):
        self.assertEqual(self.english["0313"], "UHD 3840x2160")
        self.assertEqual(self.english["0314"], "FHD 1920x1080")

    def test_the_frame_rate_list_is_the_nine_rates(self):
        rows = self.nbr.menu("../MenuB12/data/ListB12/B2_5_5.cvm", self.english)
        self.assertEqual([r["text"] for r in rows],
                         ["23.98 fps", "24 fps", "25 fps", "29.97 fps", "48 fps",
                          "50 fps", "59.94 fps", "100 fps", "119.88 fps"])

    def test_the_excl_variant_greys_the_top_five_rates_in_data(self):
        rows = self.nbr.menu("../MenuB12/data/ListB12/B2_5_5_excl.cvm", self.english)
        enabled = [r["Enabled"] for r in rows]
        self.assertEqual(enabled, ["1", "1", "1", "1", "0", "0", "0", "0", "0"])

    def test_a_corrupt_key_is_rejected(self):
        # Without this the fnv check could be deleted and every test still pass.
        data = bytearray(self.nbr.read("../Common/Strings/English.nloc"))
        data[12] ^= 0xFF
        with self.assertRaises(N.NbrError):
            N.parse_nloc(bytes(data))

    def test_columns_come_from_the_header_not_from_a_fixed_list(self):
        # A stock file with a different header: NO,ID,IMAGE,KEY,memo.
        other = next(e for e in self.nbr.entries if e.extension == "cvm"
                     and N.parse_menu(self.nbr.read(e.path)) and
                     "ID" in N.parse_menu(self.nbr.read(e.path))[0])
        rows = self.nbr.menu(other.path)
        self.assertIn("ID", rows[0])
        self.assertNotIn("Popup", rows[0])

    @unittest.skipUnless(FORMATS_BIN.exists(), "the fpSup-Formats card is not in the tree")
    def test_the_replacement_csv_parses_through_the_same_decoder(self):
        rows = N.parse_menu(formats_sections()[0xC12C7CF8], self.english)
        self.assertEqual(len(rows), 6)
        self.assertNotIn("Popup", rows[0])                    # its header has none
        self.assertEqual(rows[0]["text"], "UHD 3840x2160")    # id, resolved
        self.assertEqual(rows[2]["text"], "S16 2096x1238")    # literal, as written
        self.assertEqual([r["Enabled"] for r in rows], ["1"] * 6)

    def test_a_translated_table_differs(self):
        japanese = self.nbr.strings("Japanese")
        self.assertNotEqual(japanese["0004"], self.english["0004"])

    @unittest.skipUnless(FORMATS_BIN.exists(), "the fpSup-Formats card is not in the tree")
    def test_the_replacement_csv_uses_literal_text_and_its_own_header(self):
        csv = formats_sections()[0xC12C7CF8].decode("utf-8-sig")
        lines = [line for line in csv.replace("\r\n", "\n").split("\n") if line.strip()]
        self.assertEqual(lines[0], "NO,TEXT,IMAGE,Enabled,Enabled2")   # no Popup column
        self.assertTrue(lines[1].startswith("1,0313,"))                 # stock id kept
        self.assertIn("S16 2096x1238", lines[3])                        # literal, no nloc
        # the literals are not ids in the stock table, which is the point
        self.assertNotIn("S16 2096x1238", self.english)


class Submenus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nbr = N.load()
        cls.rows = cls.nbr.submenus()

    def test_the_quoted_cell_does_not_invent_a_destination(self):
        # B4_1_3_4_1.cvm has `1,"90<!font_G_degree,CENTER>",xx,...`; a naive
        # split made `CENTER>"` look like a page.
        self.assertNotIn('CENTER>"', {row["target"] for row in self.rows})

    def test_there_are_123_jumping_rows_to_33_destinations(self):
        self.assertEqual(len(self.rows), 123)
        self.assertEqual(len({row["target"] for row in self.rows}), 33)

    def test_almost_every_destination_is_both_a_page_and_a_resource_set(self):
        import json
        sets = {s["name"] for s in json.loads(
            (Path(__file__).resolve().parent.parent / "nbu_sets.json").read_text())["sets"]}
        targets = {row["target"] for row in self.rows}
        missing = sorted(t for t in targets if t not in sets)
        # B5_7 is really the pair B5_7S / B5_7C; B2_2_1 is only a pool string.
        self.assertEqual(missing, ["B2_2_1", "B5_7"])
        self.assertIn("B5_7S", sets)
        self.assertIn("B5_7C", sets)


class NoRoomLeft(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nbr = N.load()

    def test_the_container_is_packed(self):
        gaps = self.nbr.free_space()
        self.assertEqual(sum(length for _a, length in gaps), 3486)
        self.assertEqual(max(length for _a, length in gaps), 3)

    def test_the_card_writes_over_an_icon_not_over_free_space(self):
        owner = self.nbr.owner_of(0xC12C7CF8)
        self.assertIsNotNone(owner)
        self.assertTrue(owner.path.endswith("L_resolution_480p.xci"))
        self.assertEqual(owner.data_address, 0xC12C7CF8)
        self.assertEqual(owner.size, 3314)


class Refusals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nbr = N.load()

    def test_an_unknown_path(self):
        with self.assertRaises(N.NbrError):
            self.nbr.find("../nope/nope.cvm")

    def test_a_size_of_zero(self):
        with self.assertRaises(N.NbrError):
            self.nbr.repoint(RESOLUTION_LIST, 0xC12C7CF8, 0)

    def test_an_address_below_the_container(self):
        with self.assertRaises(N.NbrError):
            self.nbr.repoint(RESOLUTION_LIST, 0xC0000000, 16)

    def test_a_wrong_container_base(self):
        image = N.load().image
        with self.assertRaises(N.NbrError):
            N.StockNbr(image, container=0xC0D22404)


class MutationGuard(unittest.TestCase):
    """These checks have to be able to fail."""

    @classmethod
    def setUpClass(cls):
        cls.nbr = N.load()

    def test_a_little_endian_entry_read_would_not_be_sorted(self):
        entries = self.nbr.entries_address
        keys = [struct.unpack_from("<I", self.nbr.image, entries + 16 * i - N.BASE)[0]
                for i in range(200)]
        self.assertNotEqual(keys, sorted(keys))

    def test_offsets_are_relative_to_the_container_not_absolute(self):
        entry = self.nbr.find(RESOLUTION_LIST)
        raw = struct.unpack_from(">I", self.nbr.image, entry.entry_address + 8 - N.BASE)[0]
        self.assertEqual(raw, entry.data_address - self.nbr.container)
        self.assertNotEqual(raw, entry.data_address)

    def test_the_nloc_offset_needs_the_three_byte_field(self):
        # Reading the offset as a plain LE u32 at +4 gives a value 256x too big,
        # so a decoder that skipped the shift would index far outside the file.
        data = self.nbr.read("../Common/Strings/English.nloc")
        entry = 12
        wrong = struct.unpack_from("<I", data, entry + 4)[0]
        right = int.from_bytes(data[entry + 5:entry + 8], "little")
        self.assertEqual(wrong >> 8, right)
        self.assertGreater(wrong, len(data))
        self.assertLess(right, len(data))

    def test_a_big_endian_nloc_key_would_not_be_the_fnv(self):
        data = self.nbr.read("../Common/Strings/English.nloc")
        little = struct.unpack_from("<I", data, 12)[0]
        big = struct.unpack_from(">I", data, 12)[0]
        offset = int.from_bytes(data[17:20], "little")
        id_at = struct.unpack_from("<I", data, offset)[0]
        ident = data[offset + id_at:data.index(b"\0", offset + id_at)].decode()
        self.assertEqual(N.fnv1a(ident), little)
        self.assertNotEqual(N.fnv1a(ident), big)

    def test_a_different_stride_would_break_the_key_agreement(self):
        # With a 12- or 20-byte stride the keys stop being FNV-1a of the paths.
        for stride in (12, 20):
            agree = 0
            for index in range(300):
                address = self.nbr.entries_address + index * stride
                key, name = struct.unpack_from(">II", self.nbr.image, address - N.BASE)
                try:
                    if N.fnv1a(self.nbr._string(name)) == key:
                        agree += 1
                except N.NbrError:
                    pass
            self.assertLess(agree, 300, f"stride {stride} should not agree")


if __name__ == "__main__":
    unittest.main()
