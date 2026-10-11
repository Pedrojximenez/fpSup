#!/usr/bin/env python3
"""The Sensor Lab tabbed page (sl_lab_page.py), offline.

Asserted: the page passes the structure checks and the original interpreter;
it names no stock frame-guide / zebra variable anywhere (first rule) -- and a
build that skips one rename is caught; the focus / tab variables are private;
each tab holds its rows, each row's list fits its CSV (FILTER's frame rate: 11);
popups start at the tab's top; the display-only row has no Right / OK.
No camera.
"""
import struct
import unittest

import imx410_plan as PL
PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = True, False, False
import sl_b25_page as P
import sl_lab_page as LAB
import sl_size_page as SZ
from sl_b25_page import N, U, u32

IMG = (P.ROOT / "out/MAIN_c0000000.bin").read_bytes()


def fresh_pool():
    return P.Pool(IMG[U.POOL_START - P.B:U.POOL_START - P.B + U.POOL_SIZE])


def build(pool=None):
    pool = pool or fresh_pool()
    refs = []
    seq = LAB.build_lab_page(IMG, pool, refs)
    page, abs_refs = SZ.assemble(seq, refs)
    return page, abs_refs, pool


PAGE, REFS, POOL = build()
SHAPE = LAB.check_page(PAGE, POOL, IMG)
SCHEMAS = P.load_schemas(IMG)


class LabPage(unittest.TestCase):
    def test_refs(self):
        SZ.check_refs(PAGE, REFS, POOL)

    def test_no_stock_frame_guide_variable(self):
        self.assertEqual(LAB.check_settings_free(PAGE, POOL, SCHEMAS), [])
        names = {POOL.text(u32(r.to_bytes(), o)) for r in N.split(PAGE)
                 for o, k in P.typed_fields(r.to_bytes(), POOL, SCHEMAS) if k in ("str", "text")}
        self.assertFalse({n for n in names if n and n.startswith(LAB.FORBIDDEN_PREFIXES)})
        self.assertFalse({"MENU_Level3", "MENU_FrameGuideTabNo"} & names)
        self.assertTrue({"SL_LabFocus", "SL_LabTab"} <= names)

    def test_a_missed_rename_is_caught(self):
        saved = LAB.DONOR_VAR
        LAB.DONOR_VAR = "MV_FRMGUIDE_Color"           # rows would keep MV_FRMGUIDE_Style
        try:
            page, _r, pool = build()
        finally:
            LAB.DONOR_VAR = saved
        with self.assertRaises(P.BuildError):
            LAB.check_settings_free(page, pool, SCHEMAS)

    def test_tabs_hold_their_rows(self):
        objs = SHAPE["objects"]
        rows = {c: [k for k, v in objs.items() if v["parent_id"] == c and v["name"] == "B5_4_1"]
                for c in LAB.TAB_CONTAINERS}
        self.assertEqual([len(rows[c]) for c in LAB.TAB_CONTAINERS], [5, 1, 3, 1])
        # OUTPUT: the panel's captions (over everything), the info panel, its row (the
        # editing highlight: under the numbers, over the BG -- an earlier record draws
        # on top), the BG, Ratio, Data rate
        caps = [k for k, v in objs.items() if v["parent_id"] == LAB.OUTPUT_TAB and v["name"] == "Name"]
        self.assertEqual(len(caps), len(LAB.CAPTIONS))
        self.assertEqual([(k, v["name"]) for k, v in objs.items() if v["parent_id"] == LAB.OUTPUT_TAB],
                         [(k, "Name") for k in caps] + [(35533, "1_01"), (34732, "1_03"), (5039, "BG"), (rows[101][0], "B5_4_1"),
                          (rows[101][1], "B5_4_1"), (rows[101][2], "B5_4_1")])
        # FILTER's stock BG 5039 (y 81, h 162, opaque) covered rows 1-2 on camera (r23): gone
        self.assertEqual(objs[5039]["parent_id"], LAB.OUTPUT_TAB)       # moved to OUTPUT, its own panel's backdrop
        self.assertEqual([v["name"] for k, v in objs.items() if v["parent_id"] == 92], ["B5_4_1"] * 5)

    def test_list_templates_name_their_own_row(self):
        """r23/r24: the item template still named the stock List 14 / ListItem 15
        (ids <= 64 were skipped) and every popup froze."""
        objs = SHAPE["objects"]

        def row_of(o):
            while objs[o]["parent_id"] not in LAB.TAB_CONTAINERS:
                o = objs[o]["parent_id"]
            return o
        n = 0
        for r in N.split(PAGE):
            if r.tag == 0x10008:
                d = r.to_bytes()
                ids = [u32(d, o) for o in LAB.LIST_TEMPLATE_IDS if u32(d, o) not in (0, 0xFFFFFFFF)]
                self.assertTrue(all(i in objs for i in ids), ids)
                self.assertEqual(len({row_of(i) for i in ids}), 1)
                n += 1
        self.assertEqual(n, 10)

    def test_local_ids_unique_per_object(self):
        """d6: a grown cursor pair took local id 17 = the List's model clip; focusing
        the row took the camera down.  Stock pages have no such duplicate either."""
        import sl_pages
        self.assertEqual(LAB.duplicate_local_ids(PAGE), [])
        for name in ("B5_4_2", "B2_5", "MainB2"):
            self.assertEqual(LAB.duplicate_local_ids(sl_pages.set_bytes(name)), [], name)

    def test_no_markup_characters_in_list_text(self):
        """r24 / r26: focusing a row whose list read ">= 23.98p" took the camera down."""
        import sl_lists as L
        with self.assertRaises(ValueError):
            L.rows_csv([dict(text=">= 24p")], lab=True)
        for spec in [s for specs in LAB.rows_spec().values() for s in specs]:
            self.assertFalse([r for r in spec["rows"] if set("<>") & set(r["text"])], spec["key"])

    def test_no_submenu_width(self):
        """r25: stock's submenu_width objects sized the popups ~240 px wide."""
        names = {v["name"] for v in SHAPE["objects"].values()}
        self.assertFalse(set(LAB.WIDTH_OBJECTS) & names)

    def test_titles_are_literal(self):
        objs = SHAPE["objects"]
        titles = []
        for c in LAB.TAB_CONTAINERS:
            for row in [k for k, v in objs.items() if v["parent_id"] == c and v["name"] == "B5_4_1"]:
                sel = next(k for k, v in objs.items() if v["parent_id"] == row)
                name = next(k for k, v in objs.items() if v["parent_id"] == sel and v["name"] == "Name")
                d = next(r.to_bytes() for r in N.split(PAGE) if r.tag == 0x10005 and u32(r.to_bytes(), 20) == name
                         and POOL.text(u32(r.to_bytes(), 8)) == "drawText")
                titles.append((POOL.text(u32(d, 32)), d[36]))
        self.assertEqual(titles, [("Bit depth", 0), ("Frame rate", 0), ("Width", 0), ("Proportion", 0), ("Crop", 0),
                                  ("MODE", 0), ("Ratio", 0), ("Crop", 0), ("Data rate", 0), ("Preset", 0)])

    def test_summary_shows_text_not_icons(self):
        """r23: every row's summary was the frame-guide icon (an empty box)."""
        objs = SHAPE["objects"]
        blank = POOL.find("blank")
        texts = [k for k, v in objs.items() if v["name"] == "IconText" and objs[v["parent_id"]]["name"] == "MenuItem_Select"]
        icons = [k for k, v in objs.items() if v["name"] == "Icon" and objs[v["parent_id"]]["name"] == "MenuItem_Select"]
        self.assertEqual((len(texts), len(icons)), (10, 10))
        for r in N.split(PAGE):
            d = r.to_bytes()
            if r.tag == 0x10004 and u32(d, 20) in texts:
                self.assertEqual(d[-1], 1)                               # is-visible
            if (r.tag == 0x10005 and POOL.text(u32(d, 8)) == "drawImage"
                    and objs.get(u32(d, 20), {}).get("parent_id") in icons):
                self.assertEqual(u32(d, 32), blank)

    def test_lab_lists_carry_the_donor_columns(self):
        import sl_lists as L
        for spec in [s for specs in LAB.rows_spec().values() for s in specs]:
            csv = L.rows_csv(spec["rows"], lab=True).decode("utf-8-sig").split("\r\n")
            self.assertEqual(csv[0], "NO,TEXT,Popup,IMAGE,Enabled,Enabled2")
            self.assertTrue(all(line.split(",")[2:4] == ["xx", "blank"] for line in csv[1:-1]))

    def test_lists_fit_and_popups_start_at_the_top(self):
        recs = N.split(PAGE)
        spec = LAB.rows_spec()
        owner, lists = None, []
        name = {o: v["name"] for o, v in SHAPE["objects"].items()}
        for r in recs:
            d = r.to_bytes()
            if r.tag == 0x10003:
                owner = u32(d, 20)
            elif r.tag == 0x1000E and name.get(owner) == "List" and u32(d, 28) == 0xA:
                lists.append(struct.unpack_from(">f", d, 32)[0])
            elif r.tag == 0x10004 and name.get(owner) in ("List", "Scrolbar_onoff") and owner > 42000:
                # r25: aligned to the container top the popup covered the tabs; first row now
                self.assertIn(struct.unpack_from(">f", d, 36)[0], [81.0 - y for y in (81, 162, 243, 324, 405)])
        want = [float(len(s["rows"]) - 1) for c in LAB.TAB_CONTAINERS for s in spec[c]]
        self.assertEqual(sorted(lists), sorted(want))
        self.assertIn(10.0, lists)                                   # FILTER frame rate: 11 rows

    def test_panel_row_edits_in_place(self):
        """The date / time page's way (the user, 2026-10-03): the panel row's Right / OK
        write the edit code and hand focus to the invisible editor E; E's keys each
        write their code to SL_O_Key; OK / MENU also hand focus back."""
        recs = [r.to_bytes() for r in N.split(PAGE)]
        objs = SHAPE["objects"]

        def keys_of(oid):
            out = {}
            for i, d in enumerate(recs):
                if u32(d, 0) == 0x10006 and u32(d, 24) == oid and POOL.text(u32(d, 8)) == "keyEvent":
                    acts = []
                    for a in recs[i + 1:i + 1 + u32(d, 16)]:
                        n = POOL.text(u32(a, 8))
                        acts.append((n, POOL.text(u32(a, 36)), POOL.text(u32(a, 41))) if n == "controlAppVariable"
                                    else (n, u32(a, 40) if len(a) >= 44 else None))
                    out[POOL.text(u32(d, 20))] = acts
            return out
        editor = next(k for k, v in objs.items() if v["parent_id"] == LAB.OUTPUT_JUMP and k != 38159)
        row = keys_of(38159)
        for key in ("Right", "OK"):
            self.assertEqual(row[key], [("controlAppVariable", "SL_O_Key", "5"), ("controlFocus", editor)])
        want = {k: [("controlAppVariable", "SL_O_Key", str(c))] for k, c in LAB.EDITOR_KEYS}
        for k in ("OK", "Menu"):
            want[k] = want[k] + [("controlFocus", 38159)]
        self.assertEqual(keys_of(editor), want)
        texts = {POOL.text(u32(r.to_bytes(), o)) for r in N.split(PAGE)
                 for o, k in P.typed_fields(r.to_bytes(), POOL, SCHEMAS) if k in ("str", "text")}
        self.assertFalse({"B5_4_2_1", "SoftKeyboard_InputID", "SoftKeyboard_MenuName", "SL_WH"} & texts)

    def test_each_field_has_its_arrows(self):
        objs = SHAPE["objects"]
        fields = [39544, 35539, 35540] + [k for k, v in objs.items() if v["parent_id"] == LAB.PANEL_LINE
                                          and v["name"] == "Aspect" and k > 40000][:1]
        for k, f in enumerate(fields):
            kids = [o for o, v in objs.items() if v["parent_id"] == f]
            self.assertEqual(len(kids), 2, f)
            for o in kids:
                recs = [r.to_bytes() for r in N.split(PAGE) if r.tag in P.BM.OWNER_OFFSETS
                        and u32(r.to_bytes(), P.BM.OWNER_OFFSETS[r.tag]) == o]
                img = [POOL.text(u32(d, 32)) for d in recs if POOL.text(u32(d, 8)) == "drawImage"]
                bind = [(POOL.text(u32(d, 40)), u32(d, 45), POOL.text(u32(d, 49))) for d in recs
                        if POOL.text(u32(d, 8)) == "appVariableEvent"]
                self.assertIn(img[0], ("menu_arrow_M_up", "menu_arrow_M_down"))
                self.assertEqual(bind, [(f"SL_O_A{k}", 0, "opacity")])

    def test_the_panel_line_reads_evenly(self):
        """Camera r38/r39: "1x1" dimmed while the row was focused (stock's ratio
        field and ':' dim at frame 66; W / H do not), its x was the ':''s 43 px
        box, and RWZM's x had no gaps.  No field dims, every x is 35 px, the
        RWZM x has W x H's gaps, and "0.32" is its exact 114 px."""
        objs = SHAPE["objects"]
        line = [o for o, v in objs.items() if v["parent_id"] == LAB.PANEL_LINE]

        def recs(o):
            return [r.to_bytes() for r in N.split(PAGE) if r.tag in P.BM.OWNER_OFFSETS
                    and u32(r.to_bytes(), P.BM.OWNER_OFFSETS[r.tag]) == o]
        for o in line:
            if objs[o]["name"] in ("Aspect", ":"):
                self.assertFalse(any(LAB.PANEL_GREY in d for d in recs(o) if u32(d, 0) == 0x1000A), o)

        def size_w(o):
            base = next(d for d in recs(o) if POOL.text(u32(d, 8)) == "objectBase")
            return struct.unpack_from(">f", base, 32 + (8 if u32(base, 28) & 1 else 0))[0]
        xs = [o for o in line if objs[o]["name"] in ("X", ":")]
        self.assertEqual([size_w(o) for o in xs], [35.0] * 3)
        order = [r for r in N.split(PAGE) if r.tag == 0x10003 and u32(r.to_bytes(), 24) == LAB.PANEL_LINE]
        names = [objs[u32(r.to_bytes(), 20)]["name"] for r in order]
        sw = [u32(r.to_bytes(), 20) for r in order][-6]
        self.assertEqual(names[-6:], ["Aspect", "space", "X", "space", "Aspect", "%"])
        self.assertEqual(size_w(sw), 114.0)

    def test_the_data_rate_row(self):
        """Under Ratio: a step row over the rates (SL_O_RFps), its summary a
        right-aligned Name copy bound to SL_O_Rate ("29.97p 1101 MB/s")."""
        objs = SHAPE["objects"]

        def recs(o):
            return [r.to_bytes() for r in N.split(PAGE) if r.tag in P.BM.OWNER_OFFSETS
                    and u32(r.to_bytes(), P.BM.OWNER_OFFSETS[r.tag]) == o]
        boxes = [k for k, v in objs.items() if v["parent_id"] == LAB.OUTPUT_TAB and v["name"] == "B5_4_1"]
        sels = [next(k for k, v in objs.items() if v["parent_id"] == b and v["name"] == "MenuItem_Select")
                for b in boxes]
        titles = {}
        for sel in sels:
            names = [k for k, v in objs.items() if v["parent_id"] == sel and v["name"] == "Name"]
            t = next(d for d in recs(names[0]) if POOL.text(u32(d, 8)) == "drawText")
            titles[POOL.text(u32(t, 32))] = (sel, names)
        sel, names = titles["Data rate"]
        self.assertEqual(len(names), 2)
        value = recs(names[1])
        text = next(d for d in value if POOL.text(u32(d, 8)) == "drawText")
        self.assertEqual((len(text), u32(text, 28)), (53, 0x40000001))          # IconText01's shape
        self.assertEqual(struct.unpack(">ff", text[-8:]), (LAB.RATE_VALUE_W, 54.0))
        bind = [(POOL.text(u32(d, 40)), u32(d, 45), POOL.text(u32(d, 49))) for d in value
                if POOL.text(u32(d, 8)) == "appVariableEvent"]
        self.assertEqual(bind, [("SL_O_Rate", u32(text, 24), "text")])        # component: the drawText
        ctl = next(d for d in recs(sel) if u32(d, 0) == 0x1000E)
        import sl_lists as L
        self.assertEqual(struct.unpack_from(">f", ctl, 32)[0], len(L.RATE_SEL_ROWS) - 1)

    def test_the_mode_row_follows_the_camera(self):
        """MODE: the SL_MODE list (written on the camera); the List, MenuItem_Select
        and IconChange caps bound to SL_ModeMax (each its own controlValue), and a
        right-aligned Name copy bound to SL_M_Text as the summary."""
        objs = SHAPE["objects"]

        def recs(o):
            return [r.to_bytes() for r in N.split(PAGE) if r.tag in P.BM.OWNER_OFFSETS
                    and u32(r.to_bytes(), P.BM.OWNER_OFFSETS[r.tag]) == o]
        tab = [k for k, v in objs.items() if v["parent_id"] == 93]
        rows = [k for k, v in objs.items() if v["name"] == "MenuItem_Select" and v["parent_id"] in tab]
        self.assertEqual(len(rows), 1)
        sel = rows[0]
        sub, todo = set(), [sel]
        while todo:
            o = todo.pop()
            sub.add(o)
            todo += [k for k, v in objs.items() if v["parent_id"] == o]
        caps = []
        for o in sorted(sub):
            rs = recs(o)
            ctl = {u32(d, 24) for d in rs if POOL.text(u32(d, 8)) == "controlValue"}
            for d in rs:
                if POOL.text(u32(d, 8)) == "appVariableEvent" and POOL.text(u32(d, 40)) == "SL_ModeMax":
                    self.assertEqual((len(d), u32(d, 32), u32(d, 36), POOL.text(u32(d, 49))), (58, 0x2F, 1, "max-value"))
                    self.assertIn(u32(d, 45), ctl)
                    caps.append(objs[o]["name"])
        self.assertEqual(sorted(caps), ["IconChange", "List", "MenuItem_Select"])
        names = [k for k, v in objs.items() if v["parent_id"] == sel and v["name"] == "Name"]
        self.assertEqual(len(names), 2)
        value = recs(names[1])
        text = next(d for d in value if POOL.text(u32(d, 8)) == "drawText")
        self.assertEqual((len(text), u32(text, 28)), (53, 0x40000001))
        bind = [(POOL.text(u32(d, 40)), u32(d, 45), POOL.text(u32(d, 49)), u32(d, 36)) for d in value
                if POOL.text(u32(d, 8)) == "appVariableEvent"]
        self.assertEqual(bind, [("SL_M_Text", u32(text, 24), "text", 0)])

    def test_the_mode_diagram(self):
        """MODE's tab: green over red outlines over the sensor's filled block, the green /
        red rects' x / y / w / h bound to SL_D_* (subindex 0..3 of the drawRect's
        rect), four coloured texts bound to the labels."""
        objs = SHAPE["objects"]

        def recs(o):
            return [r.to_bytes() for r in N.split(PAGE) if r.tag in P.BM.OWNER_OFFSETS
                    and u32(r.to_bytes(), P.BM.OWNER_OFFSETS[r.tag]) == o]
        kids = [k for k, v in objs.items() if v["parent_id"] == 93]
        frames, texts, widths, fills = [], [], [], []
        for k in kids:
            rs = recs(k)
            kinds = [POOL.text(u32(d, 8)) for d in rs]
            if "drawRect" in kinds:
                dr = next(d for d in rs if POOL.text(u32(d, 8)) == "drawRect")
                binds = [(POOL.text(u32(d, 40)), u32(d, 45), POOL.text(u32(d, 49)), u32(d, 54)) for d in rs
                         if POOL.text(u32(d, 8)) == "appVariableEvent"]
                frames.append((u32(dr, 32), binds))
                widths.append(struct.unpack_from(">f", dr, 40)[0])
                fills.append(u32(dr, 36))
            elif "drawText" in kinds:
                texts.append([POOL.text(u32(d, 40)) for d in rs if POOL.text(u32(d, 8)) == "appVariableEvent"])
                dt = next(d for d in rs if POOL.text(u32(d, 8)) == "drawText")
                self.assertEqual((u32(dt, 28), u32(dt, 37), len(dt)), (0x40002015, LAB.DIAG_FONT, 65))   # smaller
        self.assertEqual([c for c, _ in frames], [LAB.DIAG_CROP, LAB.DIAG_GREEN, LAB.DIAG_RED, LAB.DIAG_SENSOR])
        self.assertEqual(fills, [0, 0, 0, 1])               # outlines over the sensor's filled block
        for (c, binds), v in zip(frames, "CGR"):
            self.assertEqual(binds, [(f"SL_D_{v}{a}", 1, "rect", k) for k, a in enumerate("XYWH")])
        self.assertEqual(frames[3][1], [])
        self.assertTrue(widths[2] > widths[1])              # red wider than green, green on top: both show
        self.assertEqual(texts, [["SL_D_GTxt"], ["SL_D_RTxt"], ["SL_D_Fps"], ["SL_D_Rs"], ["SL_D_CTxt"]])

    def test_tab_captions_are_text(self):
        """FILTER / MODES / OUTPUT replace stock's caption images: centred drawTexts
        with the image's local id and colour (the tab clips animate colour); MODES
        bound to SL_M_Tab ("MODES (62)")."""
        def recs(o):
            return [r.to_bytes() for r in N.split(PAGE) if r.tag in P.BM.OWNER_OFFSETS
                    and u32(r.to_bytes(), P.BM.OWNER_OFFSETS[r.tag]) == o]
        for o, (text, var) in LAB.TAB_TITLES.items():
            rs = recs(o)
            kinds = [POOL.text(u32(d, 8)) for d in rs]
            self.assertNotIn("drawImage", kinds)
            t = next(d for d in rs if POOL.text(u32(d, 8)) == "drawText")
            self.assertEqual((POOL.text(u32(t, 32)), u32(t, 24), u32(t, 28), u32(t, 37), u32(t, 41)),
                             (text, 1, 0x40002011, 2, 0x888888FF))
            binds = [(POOL.text(u32(d, 40)), u32(d, 45), POOL.text(u32(d, 49))) for d in rs
                     if POOL.text(u32(d, 8)) == "appVariableEvent"]
            self.assertEqual(binds, [(var, 1, "text")] if var else [])

    def test_the_crop_row_edits_in_place(self):
        """OUTPUT's Crop row: Right / OK write SL_O_Key 15 and focus its editor E2,
        whose keys write 11..18 (10 + the panel's codes) and whose OK / MENU give
        the focus back; the summary is SL_C_Text."""
        objs = SHAPE["objects"]
        recs = [r.to_bytes() for r in N.split(PAGE)]
        boxes = [k for k, v in objs.items() if v["parent_id"] == LAB.OUTPUT_TAB and v["name"] == "B5_4_1"]
        sel = next(k for k, v in objs.items() if v["parent_id"] == boxes[1] and v["name"] == "MenuItem_Select")

        def keys_of(o):
            out = {}
            for i, d in enumerate(recs):
                if u32(d, 0) == 0x10006 and u32(d, 24) == o and POOL.text(u32(d, 8)) == "keyEvent":
                    out[POOL.text(u32(d, 20))] = recs[i + 1:i + 1 + u32(d, 16)]
            return out
        row = keys_of(sel)
        editors = set()
        for k in ("Right", "OK"):
            write, focus = row[k]
            self.assertEqual((POOL.text(u32(write, 36)), POOL.text(u32(write, 41))), ("SL_O_Key", "15"))
            editors.add(u32(focus, LAB.FOCUS_TARGET_AT))
        (e,) = editors
        self.assertEqual(objs[e]["parent_id"], boxes[1])
        codes = {k: POOL.text(u32(a[0], 41)) for k, a in keys_of(e).items()}
        self.assertEqual(codes, {k: str(10 + c) for k, c in LAB.EDITOR_KEYS})
        for k in ("OK", "Menu"):
            self.assertEqual(u32(keys_of(e)[k][1], LAB.FOCUS_TARGET_AT), sel)

    def test_four_tabs(self):
        """The tab bar grows to FILTER / MODES / OUTPUT / NAME (tabs4): value 0..3,
        Tab and SubTab with four states (frames 0 / 66 / 133 / 200), four 256-wide
        captions each bright at its own frame, the cursor at x 0 / 256 / 512 / 768,
        the NAME container shown only at frame 200 and OUTPUT hidden there."""
        recs = [r.to_bytes() for r in N.split(PAGE)]
        cv = next(d for d in recs if u32(d, 0) == 0x1000E and u32(d, 20) == LAB.TAB_ITEM)
        self.assertEqual(struct.unpack_from(">f", cv, 32)[0], 2.0)          # SAVE: a preview, not reachable
        for owner, name in ((LAB.TAB_ITEM, "Tab"), (83, "SubTab")):
            g = next(d for d in recs if u32(d, 0) == 0x1000B and u32(d, 24) == owner and POOL.text(u32(d, 20)) == name)
            self.assertEqual((u32(g, 8), u32(g, 16)), (4, 5 if name == "Tab" else 4))   # Tab: + the cursor
            self.assertEqual([(u32(g, 28 + 21 * i + 4), u32(g, 28 + 21 * i + 8)) for i in range(4)], list(LAB.TAB_SPANS))
        evs = [struct.unpack_from(">f", d, 40)[0] if u32(d, 32) == 3 else 0.0 for d in recs
               if u32(d, 0) == 0x10006 and u32(d, 24) == LAB.TAB_ITEM and POOL.text(u32(d, 8)) == "controlValueEvent"]
        self.assertEqual(sorted(evs), [0.0, 1.0, 2.0, 3.0])

        def clip(o, cid=None):
            d = next(d for d in recs if u32(d, 0) == 0x1000A and u32(d, 20) == o and (cid is None or u32(d, 24) == cid))
            return P.A.parse_clip(P.A.Record(0, d), POOL.text)["properties"]
        for i, o in enumerate(list(LAB.TAB_TITLES) + [LAB.NAME_CAPTION]):
            red = clip(o)[0]["keys"]
            at = {k["time"]: round(k["value"], 2) for k in red}
            for j, (a, b) in enumerate(LAB.TAB_SPANS):          # held over each state's span
                self.assertEqual((at[a], at[b]), (1.0, 1.0) if j == i else (0.53, 0.53))
            base = next(d for d in recs if u32(d, 0) == 0x10004 and u32(d, 20) == o)
            self.assertEqual(struct.unpack_from(">ff", base, 32)[0], 256.0 * i)
        pos = next(p for p in clip(35014, 3) if p["name"] == "position")["keys"]
        at = {k["time"]: k["value"] for k in pos}
        self.assertEqual([at[a] for a, _ in LAB.TAB_SPANS], [0.0, 256.0, 512.0, 768.0])
        self.assertLessEqual(max(b for _, b in LAB.TAB_SPANS), 166)          # stock's timeline
        for i, c in enumerate((92, 93, 101, LAB.NAME_TAB)):     # each shown over its own state only
            at = {k["time"]: k["value"] for k in clip(c)[0]["keys"]}
            for j, (a, b) in enumerate(LAB.TAB_SPANS):
                self.assertEqual((at[a], at[b]), (1, 1) if j == i else (0, 0))
        text = next(d for d in recs if u32(d, 0) == 0x10005 and u32(d, 20) == LAB.NAME_CAPTION)
        self.assertEqual(POOL.text(u32(text, 32)), "SAVE")

    def test_step_rows_change_in_place(self):
        """FILTER's four rows, MODE and Ratio (the user, 2026-10-03): Right 'dst + 1' and
        Left 'dst - 1' on the row's own value, then the variable written from it;
        the value stops at the last option; OK still opens the popup."""
        objs = SHAPE["objects"]
        recs = [r.to_bytes() for r in N.split(PAGE)]
        steps = [s for specs in LAB.rows_spec().values() for s in specs if s.get("step")]
        self.assertEqual([s["key"] for s in steps], ["BIT", "FPS", "WIDTH", "PROP", "CROP", "MODE", "SQZ", "RATE", "PRESET"])
        sels = []
        for c in LAB.TAB_CONTAINERS:
            for row in [k for k, v in objs.items() if v["parent_id"] == c and v["name"] == "B5_4_1"]:
                sels.append(next(k for k, v in objs.items() if v["parent_id"] == row and v["name"] == "MenuItem_Select"))
        rows = dict(zip(["BIT", "FPS", "WIDTH", "PROP", "CROP", "MODE", "SQZ", "CROP_O", "RATE", "PRESET"], sels))
        for spec in steps:
            sel = rows[spec["key"]]
            keys = {}
            for i, d in enumerate(recs):
                if u32(d, 0) == 0x10006 and u32(d, 24) == sel and POOL.text(u32(d, 8)) == "keyEvent":
                    keys[POOL.text(u32(d, 20))] = recs[i + 1:i + 1 + u32(d, 16)]
            for key, formula in (("Right", "dst + 1"), ("Left", "dst - 1")):
                step, write = keys[key]
                self.assertEqual((POOL.text(u32(step, 8)), u32(step, 36), POOL.text(u32(step, 50))),
                                 ("changePropertyByControl", sel, formula), spec["key"])
                self.assertEqual((POOL.text(u32(write, 8)), POOL.text(u32(write, 36)), u32(write, 45)),
                                 ("controlAppVariable", spec["var"], sel), spec["key"])
            self.assertEqual([POOL.text(u32(a, 8)) for a in keys["OK"]][:1], ["controlFocus"])   # popup
            ctl = next(d for d in recs if u32(d, 0) == 0x1000E and u32(d, 20) == sel)
            self.assertEqual(struct.unpack_from(">f", ctl, 32)[0], len(spec["rows"]) - 1)

    def test_summaries_are_the_options(self):
        import sl_lists as L
        for rows in (L.F_BIT_ROWS, L.F_PROP_ROWS, L.SCALE_ROWS):
            self.assertEqual([r["summary"] for r in rows], [r["text"] for r in rows])

    def test_panel_variables_are_private(self):
        texts = {POOL.text(u32(r.to_bytes(), o)) for r in N.split(PAGE)
                 for o, k in P.typed_fields(r.to_bytes(), POOL, SCHEMAS) if k in ("str", "text")}
        self.assertTrue(set(LAB.PANEL_VARS) <= texts)
        src = open(P.HERE / "sl_menu/sl_menu.c").read()
        for name in LAB.PANEL_VARS:                          # registered by the installer
            self.assertIn(f"/* {name} */", src)

if __name__ == "__main__":
    unittest.main(verbosity=2)
