#!/usr/bin/env python3
"""Offline tests for uinav.  They read the pinned firmware image and the map;
nothing here touches a camera.  Run with `python3 -B -m unittest`."""
import io
import json
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import uinav

MAP = uinav.load_map()
IMAGE = uinav.Image(MAP)


def run(*argv) -> str:
    out = io.StringIO()
    with redirect_stdout(out):
        uinav.main(list(argv))
    return out.getvalue()


class MapIntegrity(unittest.TestCase):
    def test_every_entry_cites_a_source(self):
        for key in ("regions", "funcs"):
            for entry in MAP[key]:
                self.assertTrue(entry.get("source"), f"{key} entry without a source: {entry}")

    def test_regions_are_ordered_and_non_empty(self):
        for region in MAP["regions"]:
            start = uinav.parse_addr(region["start"])
            end = uinav.parse_addr(region["end"])
            self.assertLess(start, end, region["name"])

    def test_hook_owners_exist(self):
        known = {owner["id"] for owner in MAP["owners"]}
        for site in MAP["hook_sites"]:
            for owner in site["owners"]:
                self.assertIn(owner, known, site["addr"])

    def test_addresses_are_uppercase_hex(self):
        pattern = re.compile(r"^0x[0-9A-F]{8}$")
        for key in ("funcs", "hook_sites"):
            for entry in MAP[key]:
                self.assertRegex(entry["addr"], pattern)


class GeneratedIndexes(unittest.TestCase):
    def test_image_hash_is_the_pinned_one(self):
        self.assertEqual(IMAGE.verify(), MAP["firmware"]["sha256"])

    def test_page_table_has_196_entries_and_mainb2_is_10(self):
        pages = IMAGE.pages()
        self.assertEqual(len(pages), 196)
        by_name = {name: page_id for _addr, name, page_id in pages}
        self.assertEqual(by_name["MainB2"], 10)   # MAINB2_ROW_EXTENSION.md
        self.assertEqual(by_name["MainY4"], 20)   # holds the fpLossless donor

    def test_pool_offsets_resolve_back_to_the_string(self):
        pool = IMAGE.pool()
        self.assertEqual(len(pool), 14470)
        for offset, text in pool[::1500]:
            self.assertEqual(IMAGE.cstr(uinav.POOL_START + offset), text)

    def test_pool_base_is_anchored_by_an_independent_offset(self):
        # MAINB2_ROW_EXTENSION.md read pool offset 0x1A3B8 out of the NBU screen
        # declaration and says it names MainB2.  That only holds if the pool base
        # really is 0xC18C0474 -- so this catches a wrong base, which a test
        # written against uinav's own arithmetic cannot.
        self.assertEqual(IMAGE.cstr(uinav.POOL_START + 0x1A3B8), "MainB2")
        self.assertEqual(dict(IMAGE.pool()).get(0x1A3B8), "MainB2")

    def test_the_known_resolution_groups_are_in_the_pool(self):
        names = {text for _o, text in IMAGE.pool()}
        self.assertIn("20_MV_Resolution", names)
        self.assertIn("21_MV_Resolution", names)
        self.assertIn("1_03_CINE", names)

    def test_icon_manifest_and_archive_counts(self):
        self.assertEqual(len(IMAGE.icons()), 2006)
        self.assertEqual(len(IMAGE.blobs()), 2004)

    def test_resolution_icon_families_have_exactly_two_members(self):
        names = [path.rsplit("/", 1)[-1] for _a, path in IMAGE.icons()]
        for family in ("qs_resolution", "set_resolution", "font_menu_MB_resolution"):
            members = [n for n in names if n.startswith(family + "_")]
            self.assertEqual(len(members), 2, f"{family}: {members}")


class Commands(unittest.TestCase):
    def test_at_a_known_hook_names_its_owners(self):
        text = run("at", "0xC05E6400")
        self.assertIn("NBU record interpreter", text)
        self.assertIn("fpsup-formats", text)

    def test_at_an_unmapped_pool_address_says_where_it_is(self):
        text = run("at", "0xC18C4848")
        self.assertIn("string pool", text)
        self.assertIn("20_MV_Resolution", text)

    def test_pool_search_is_case_insensitive(self):
        self.assertIn("MV_Resolution", run("pool", "mv_resolution"))

    def test_who_lists_the_hooks_of_a_product(self):
        text = run("who", "fpsup-og3k")
        self.assertIn("0xC05D90F0", text)

    def test_routes_and_traps_print_every_entry(self):
        self.assertEqual(run("routes").count("how:"), len(MAP["routes"]))
        self.assertEqual(run("traps").count("*"), len(MAP["traps"]))


class MutationGuard(unittest.TestCase):
    """A test suite that cannot fail proves nothing (RE verification discipline)."""

    def test_a_wrong_page_id_would_be_caught(self):
        pages = {name: page_id for _a, name, page_id in IMAGE.pages()}
        self.assertNotEqual(pages["MainB2"], 11)

    def test_a_truncated_pool_would_be_caught(self):
        self.assertNotEqual(len(IMAGE.pool()), 0)

    def test_map_json_is_the_file_next_to_the_tool(self):
        self.assertEqual(uinav.UI_MAP.name, "ui_map.json")
        json.loads(Path(uinav.UI_MAP).read_text())


if __name__ == "__main__":
    unittest.main()
