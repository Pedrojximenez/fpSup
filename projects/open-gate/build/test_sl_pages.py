#!/usr/bin/env python3
"""The private pages pack (sl_pages.py), offline, against the original interpreter.

Asserted:
  - the top level walks pool, index, state machine, end; case 0 builds one row
    per page at the right offset (screen + runtime entry on the camera);
  - the 0x50002 counts equal the 0x50003 / 0x50004 records that follow (stock
    carves the machine's memory by those counts);
  - with the stock matcher (FUN_c05ecf10 / c05ecce0 really run): B2_5 + "SL_TEST"
    -> SL_TEST, SL_TEST + "Return" -> B2_5, and nothing else is claimed --
    B2_5 + "Return" stays stock's, other screens do not jump;
  - a pack without the Return transition is caught.
No camera.  (Camera r14, 2026-10-02: pages registered, screen 222 built, but the
jump did nothing -- no transition existed.)
"""
import struct
import unittest

import sl_pages as S
from sl_pages import N

IMG = (S.ROOT / "out/MAIN_c0000000.bin").read_bytes()
PAGES = S.test_pages(IMG)
PACK = S.build_pack(PAGES)
QUERIES = [("B2_5", "SL_TEST"), ("SL_TEST", "Return"), ("B2_5", "Return"), ("MainB2", "SL_TEST"),
           ("SL_TEST", "SL_TEST"), ("B2_6_2", "Return")]


class Pack(unittest.TestCase):
    def test_small(self):
        self.assertLess(len(PACK), 1024)            # the user: keep files small

    def test_python_reading(self):
        self.assertEqual(S.inspect_pack(PACK), {"SL_TEST": PAGES[0][1]})

    def test_machine_counts_match_its_records(self):
        recs = N.split(PACK[12:])
        tags = [r.tag for r in recs]
        i = tags.index(0x50002)
        counts = struct.unpack_from(">8I", recs[i].body, 0)
        self.assertEqual(counts[1:7], (0,) * 6)
        self.assertEqual((counts[0], counts[7]), (tags.count(0x50003), tags.count(0x50004)))
        self.assertEqual(tags[:2] + [tags[-1]], [1, 0x10001, 0xFFFFFFFF])

    def test_native_index(self):
        rows, calls = S.native_index(PACK, IMG)
        self.assertEqual([(n, o) for n, o, _ in rows], [("SL_TEST", PACK.index(PAGES[0][1]))])
        self.assertIn("stub_C05E0CC8", calls)          # the screen added
        self.assertIn("stub_C05DE938", calls)          # the state machine added (app+0xF4)

    def test_native_switches(self):
        got = S.native_switch(PACK, QUERIES, IMG)
        self.assertEqual(got, {("B2_5", "SL_TEST"): ("SL_TEST", 0), ("SL_TEST", "Return"): ("B2_5", 0),
                               ("B2_5", "Return"): None, ("MainB2", "SL_TEST"): None,
                               ("SL_TEST", "SL_TEST"): None, ("B2_6_2", "Return"): None})

    def test_a_missing_return_is_caught(self):
        """Mutation: build without the Return transition."""
        saved = S.transitions

        def no_return(pages):
            states, trans = saved(pages)
            return states, [t for t in trans if t[2] != "Return"]
        S.transitions = no_return
        try:
            bad = S.build_pack(PAGES)
        finally:
            S.transitions = saved
        got = S.native_switch(bad, QUERIES, IMG)
        self.assertIsNone(got[("SL_TEST", "Return")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
