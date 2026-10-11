#!/usr/bin/env python3
"""The Width / Height digit page (sl_wh_page.py), offline.

Asserted: the page passes the structure checks and the original interpreter and
names no stock frame-guide variable or request (first rule); only the W/H
editor is left under InputType, without dots and "mm"; every digit counts on
its own (Up / Down: 'dst +/- 1' then write its variable; 0..9 looping), starts
from its variable, and OK / MENU go back (sync-request Return); the MODE reset
and the arrows are gone; the thousands digit's glyph covers 0..9.  A build
that leaves one stock request in is caught.  No camera.
"""
import struct
import unittest

import imx410_plan as PL
PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = True, False, False
import sl_b25_page as P
import sl_size_page as SZ
import sl_wh_page as WH
from sl_b25_page import N, u32

IMG = (P.ROOT / "out/MAIN_c0000000.bin").read_bytes()
SCHEMAS = P.load_schemas(IMG)


def build():
    pool = P.Pool(IMG[P.U.POOL_START - P.B:P.U.POOL_START - P.B + P.U.POOL_SIZE])
    refs = []
    page, abs_refs = SZ.assemble(WH.build_wh_page(IMG, pool, refs), refs)
    return page, abs_refs, pool


PAGE, REFS, POOL = build()
SHAPE = WH.check_page(PAGE, POOL, IMG)


def components(obj):
    out, owner = [], None
    for r in N.split(PAGE):
        d = r.to_bytes()
        if r.tag == 0x10003:
            owner = u32(d, 20)
        elif owner == obj:
            out.append(d)
    return out


class WhPage(unittest.TestCase):
    def test_refs(self):
        SZ.check_refs(PAGE, REFS, POOL)

    def test_only_the_wh_editor(self):
        objs = SHAPE["objects"]
        self.assertEqual([k for k, v in objs.items() if v["parent_id"] == WH.INPUT_TYPE], [WH.EDITOR])
        kids = [v["name"] for k, v in objs.items() if v["parent_id"] == WH.EDITOR]
        self.assertEqual(kids, ["W_Tens", "W_Ones", "W_1st", "W_2nd", "X", "H_Tens", "H_Ones", "H_1st", "H_2nd"])

    def test_each_digit_counts_on_its_own(self):
        for d, (_stock, var) in WH.DIGITS.items():
            with self.subTest(digit=d):
                recs = components(d)
                keys, i = {}, 0
                while i < len(recs):
                    x = recs[i]
                    if POOL.text(u32(x, 8)) == "keyEvent":
                        n = u32(x, 16)
                        keys[POOL.text(u32(x, 20))] = recs[i + 1:i + 1 + n]
                        i += 1 + n
                        continue
                    i += 1
                self.assertNotIn("MODE", keys)
                for key, formula in (("Up", "dst + 1"), ("Down", "dst - 1")):
                    step, write = keys[key]
                    self.assertEqual((POOL.text(u32(step, 8)), u32(step, 36), POOL.text(u32(step, 50))),
                                     ("changePropertyByControl", d, formula))
                    self.assertEqual((POOL.text(u32(write, 8)), POOL.text(u32(write, 36)), u32(write, 45)),
                                     ("controlAppVariable", var, d))
                for key in ("OK", "Menu"):
                    (back,) = keys[key]
                    self.assertEqual((POOL.text(u32(back, 8)), POOL.text(u32(back, 36))), ("controlAppState", "Return"))
                ctl = next(x for x in recs if u32(x, 0) == 0x1000E and POOL.text(u32(x, 8)) == "controlValue")
                self.assertEqual((u32(ctl, 28), struct.unpack_from(">f", ctl, 32)[0]), (0xA, 9.0))   # max 9, looping
                bind = [x for x in recs if POOL.text(u32(x, 8)) == "appVariableEvent"]
                self.assertEqual([(POOL.text(u32(b, 40)), u32(b, 45), POOL.text(u32(b, 49))) for b in bind],
                                 [(var, 2, "value")])
                watched = [POOL.text(u32(x, 36)) for x in recs if POOL.text(u32(x, 8)) == "appVariableChangeEvent"]
                self.assertEqual(watched, [var])                                       # no arrows

    def test_thousands_glyph_has_all_digits(self):
        clip = next(d for d in components(WH.GLYPH_SHORT) if u32(d, 0) == 0x1000A and u32(d, 24) == WH.GLYPH_CLIP)
        c = P.A.parse_clip(P.A.Record(0, clip), POOL.text)
        imgs = [POOL.text(k["value"]) for p in c["properties"] if p["name"] == "image" for k in p["keys"]]
        self.assertEqual(imgs, [f"font_menu_LB_{i}" for i in range(10)])

    def test_nothing_stock_left(self):
        self.assertEqual(WH.forbidden_left(PAGE, POOL, SCHEMAS), [])
        names = set(POOL.added)
        self.assertEqual(names, set(WH.DIGIT_VARS) | {"SL_O_In", "SL_WhFocus"})

    def test_a_stock_request_left_in_is_caught(self):
        page = bytearray(PAGE)
        o = POOL.find("FrameGuide_ResetSize")
        rec = next(r for r in N.split(PAGE) if POOL.text(u32(r.to_bytes(), 8)) == "controlAppState"
                   and POOL.text(u32(r.to_bytes(), 36)) == "Return")
        struct.pack_into(">I", page, rec.offset + 36, o)
        self.assertTrue(WH.forbidden_left(bytes(page), POOL, SCHEMAS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
