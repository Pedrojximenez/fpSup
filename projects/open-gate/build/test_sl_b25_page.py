#!/usr/bin/env python3
"""Offline checks for the private B2_5 page with MODE/SIZE rows (phase A).

The native interpreter's UI construction services are stubs; passing this
suite does not mean the camera has drawn the page.
"""
from __future__ import annotations

import struct
import unittest

import imx410_plan as PL
# The page as a --b25-menu card builds it (build_res_lab_card.build): stock
# frame-rate / bit-depth rows stay stock, the CUSTOM lists are private.
PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = True, False, False
import sl_b25_page as S
from sl_b25_page import N, u32, put

IMAGE = (S.ROOT / "out/MAIN_c0000000.bin").read_bytes()
SCHEMAS = S.load_schemas(IMAGE)


def build(clones):
    saved = S.WITH_CLONES
    S.WITH_CLONES = clones
    try:
        return S.build(IMAGE)
    finally:
        S.WITH_CLONES = saved


# The card's page (2026-10-03): no MODE / Output rows, resolution CUSTOM jumps.
CARD = build(False)
# The MODE / Output clone machinery, kept tested for the lab page's rows.
S.WITH_CLONES = True
RES = S.build(IMAGE)


def objects(page):
    return {r.words(7)[3]: r for r in N.split(page) if r.tag == 0x10003}


def with_page(page):
    return dict(RES, page=page)


class Page(unittest.TestCase):
    def test_no_old_ids_at_field_starts(self):
        for r in RES["report"]:
            self.assertEqual(r["residue"], [], r["key"])

    def test_audit(self):
        S.audit(RES, IMAGE)

    def test_layout(self):
        objs = objects(RES["page"])
        self.assertEqual(objs[S.MENU].words(7)[2], 8)
        kids = [i for i, r in objs.items() if r.words(7)[4] == S.MENU]
        roots = [r["root"] for r in RES["report"]]
        self.assertEqual(kids[-3:], [S.ROW] + roots)       # sibling (= focus) order
        for spec, root in zip(S.CLONES, roots):
            rec = next(r.to_bytes() for r in N.split(RES["page"])
                       if r.tag == 0x10004 and u32(r.to_bytes(), 20) == root)
            self.assertIn(struct.pack(">f", spec["y"]), rec)

    def test_scrollbar_tracks_its_own_list(self):
        pool = RES["pool"]
        targets = []
        for r in N.split(RES["page"]):
            d = r.to_bytes()
            if r.tag == 0x10005 and pool.text(u32(d, 8)) == "drawScrollbar":
                targets.append(u32(d, 32))
        objs = objects(RES["page"])
        self.assertIn(4439, targets)
        for r in RES["report"]:
            lo, hi = r["ids"]
            mine = [t for t in targets if lo <= t <= hi]
            self.assertEqual(len(mine), 1, r["key"])
            self.assertEqual(objs[mine[0]].words(7)[5], objs[4439].words(7)[5])   # same class/name

    def test_titles_are_literal(self):
        pool = RES["pool"]
        for spec in S.CLONES:
            off = pool.find(spec["title"]) or pool.added[spec["title"]]
            owner = next(r for r in RES["report"] if r["key"] == spec["key"])
            found = []
            for r in N.split(RES["page"]):
                d = r.to_bytes()
                if r.tag == 0x10005 and pool.text(u32(d, 8)) == "drawText" and \
                        owner["ids"][0] <= u32(d, 20) <= owner["ids"][1]:
                    for o, kind in S.typed_fields(d, pool, SCHEMAS):
                        if kind == "text" and u32(d, o) == off:
                            found.append(d[o + 4])
            self.assertEqual(found, [0], spec["title"])                # literal, once
        title = pool.find(S.TITLE_ID)
        stock = [r for r in N.split(RES["page"]) if r.tag == 0x10005
                 and u32(r.to_bytes(), 20) == S.TITLE_OWNER and u32(r.to_bytes(), 32) == title]
        self.assertEqual(len(stock), 1)                                  # frame-rate title untouched

    def test_refs_hold_private_offsets(self):
        # pinned: a change in how many page words name private strings is a question
        # (phase A 46, custom lists 2, MODE's 70-row pairs / summary / SetLimit, SIZE labels,
        #  the resolution row's jump)
        self.assertEqual(len(RES["abs_refs"]), 75)
        self.assertEqual(sorted(t for _, t in CARD["abs_refs"]),
                         sorted(["SL_RATE", "SL_BIT", S.SIZE_JUMP_TO, "SL_JumpEvent"]))
        # every private string costs the installer a pool search and two cache
        # flushes at boot (r13: 132 refs, ~20 s at the third box) -- keep them few
        self.assertLessEqual(len(RES["pool"].added), 25)
        for a, text in RES["abs_refs"]:
            self.assertEqual(u32(RES["page"], a), RES["pool"].added[text])

    def test_custom_switch(self):
        pool, page = RES["pool"], RES["page"]
        sid = RES["switch_id"]
        objs = objects(page)
        self.assertEqual(objs[sid].words(7)[4], S.SWITCH_PARENT)
        self.assertEqual(objs[S.SWITCH_PARENT].words(7)[2], objects(S.U.rebuild(IMAGE)[:-3] if S.U.WITH_SUMMARY
                                                                  else S.U.rebuild(IMAGE))[1].words(7)[2]
                         + 1 + S.WITH_LAB_JUMP)                    # the switch, the jump object
        mine = [r.to_bytes() for r in N.split(page) if r.tag in S.BM.OWNER_OFFSETS
                and u32(r.to_bytes(), S.BM.OWNER_OFFSETS[r.tag]) == sid]
        comp = [pool.text(u32(d, 8)) for d in mine]
        self.assertEqual(comp.count("controlValueEvent"), 3)
        bind = mine[comp.index("appVariableEvent")]
        self.assertEqual(pool.text(u32(bind, 40)), "MV_Resolution")
        events = {u32(d, 28): (pool.text(u32(d, 20)), struct.unpack_from(">f", d, 40)[0])
                  for d in mine if pool.text(u32(d, 8)) == "controlValueEvent"}
        actions = {u32(d, 24): (u32(d, 36), pool.text(u32(d, 40)), pool.text(u32(d, 45)))
                   for d in mine if pool.text(u32(d, 8)) == "controlAnimation"}
        played = {events[k][1]: actions[k] for k in events}
        self.assertEqual(played, {0.0: (S.MENU, S.SWITCH_NAME, "Off"), 1.0: (S.MENU, S.SWITCH_NAME, "Off"),
                                  2.0: (S.MENU, S.SWITCH_NAME, "On")})
        self.assertEqual(sorted(t for t, _ in events.values()), ["0", "1", "2"])
        grp = [r.to_bytes() for r in N.split(page) if r.tag == 0x1000B
               and pool.text(u32(r.to_bytes(), 20)) == S.SWITCH_NAME]
        self.assertEqual(len(grp), 1)
        g = grp[0]
        self.assertEqual((pool.text(u32(g, 28)), pool.text(u32(g, 49))), ("Off", "On"))
        self.assertEqual([u32(g, 70 + 4 * i) for i in range(4)],
                         [RES["report"][0]["root"], 1, RES["report"][1]["root"], 1])
        for r in RES["report"]:
            clips = [d for d in (x.to_bytes() for x in N.split(page)) if u32(d, 0) == 0x1000A
                     and u32(d, 20) == r["root"]]
            self.assertEqual(len(clips), 1)
            c = S.A.parse_clip(S.A.Record(0, clips[0]), pool.text)
            self.assertEqual((c["clip_id"], [(k["time"], k["value"]) for k in c["properties"][0]["keys"]]),
                             (1, [(0, 0), (66, 1)]))

    def test_every_plan_word_in_b2_5_is_in_the_page_base(self):
        base = S.base_page(IMAGE)
        words = S.plan_words_in_set()
        self.assertGreater(len(words), 4000)
        for a, v, what in words:
            o = a - S.U.SET_START
            if o + 4 <= len(base):
                self.assertEqual(struct.unpack_from("<I", base, o)[0], v, what)
        # the three maxima the first camera run missed.  With the CUSTOM-only
        # lists (r4 on, the card's setting) the stock frame-rate / bit-depth
        # lists keep their stock caps; the private lists' caps ride the model clip.
        maxima = {}
        for addr in (0xC1A709BC, 0xC1A74B44, 0xC1A690D7):
            maxima[addr] = struct.unpack(">f", base[addr - S.U.SET_START:addr - S.U.SET_START + 4])[0]
        stock = PL.WITH_SL_EXCL
        self.assertEqual(maxima, {0xC1A709BC: 2.0, 0xC1A74B44: 8.0 if stock else 9.0,
                                  0xC1A690D7: 2.0 if stock else 3.0})

    def test_custom_list_frames_and_caps(self):
        pool = RES["pool"]
        clips = {}
        for r in N.split(RES["page"]):
            d = r.to_bytes()
            if r.tag == 0x1000A and u32(d, 20) in (4439, 4302) and u32(d, 24) == 17:
                c = S.A.parse_clip(S.A.Record(0, d), pool.text)
                clips[u32(d, 20)] = {p["name"]: [(k["time"], pool.text(k["value"]) if p["kind"] == 2
                                                  else k["value"]) for k in p["keys"]]
                                     for p in c["properties"]}
        stock = ["B2_5_5", "B2_5_5_excl", "B2_5_5_excl2", "B2_5_5_excl3", "B2_5_5_excl4", "B2_5_5_excl5"]
        self.assertEqual(clips[4439]["model"], list(zip((0, 33, 66, 100, 133, 166, 200), stock + ["SL_RATE"])))
        self.assertEqual(clips[4439]["max-value"], [(t, 8.0) for t in (0, 33, 66, 100, 133, 166)] + [(200, 9.0)])
        self.assertEqual(clips[4302]["model"], [(0, "B2_5_2"), (33, "B2_5_2_excl"), (66, "SL_BIT")])
        self.assertEqual(clips[4302]["max-value"], [(0, 2.0), (33, 2.0), (66, 3.0)])
        # frame = EXCL value x 33.3: the sl_excl.S indices land on the private frames
        import sl_excl
        self.assertEqual(round(sl_excl.RATE_INDEX * 100 / 3), 200)
        self.assertEqual(int(sl_excl.BIT_INDEX * 100 / 3), 66)
        groups = {(pool.text(u32(r.to_bytes(), 20)), u32(r.to_bytes(), 24)): (u32(r.to_bytes(), 32), u32(r.to_bytes(), 36))
                  for r in N.split(RES["page"]) if r.tag == 0x1000B}
        self.assertEqual(groups[("ExclList", 4434)], (0, 200))
        self.assertGreaterEqual(groups[("SetList", 4302)][1], 66)

    def test_native_interpreter(self):
        S.native_parse(RES["page"], RES["pool"].data, IMAGE)


def jump_wiring(page, pool):
    """What resolution CUSTOM does on a built page: {List value event: footer},
    the popup's Right actions, JumpEvent's {value: (type, sync-request)}."""
    owner, ev, out = None, None, dict(list={}, right=[], jump={})
    jid = next(r.words(7)[3] for r in N.split(page) if r.tag == 0x10003
               and pool.text(r.words(7)[5]) == "SL_JumpEvent")
    for r in N.split(page):
        d = r.to_bytes()
        if r.tag == 0x10003:
            owner = u32(d, 20)
            continue
        if len(d) < 24:
            continue
        name = pool.text(u32(d, 8))
        if r.tag == 0x10006:
            word = lambda o: u32(d, o) if len(d) >= o + 4 else None
            ev = (owner, name, word(32), word(36), struct.unpack_from(">f", d, 40)[0] if len(d) >= 44 else None,
                  pool.text(u32(d, 20)))
            continue
        if r.tag != 0x10009 or ev is None:
            continue
        if owner == S.RES_LIST and ev[2] in (3, 0x21) and ev[3] in (0x13, 0x83):
            key = ("<=", ev[4]) if ev[2] == 0x21 else ("==", ev[4])
            out["list"].setdefault(key, []).append(pool.text(u32(d, 45)) if name == "controlAnimation" else name)
        elif owner == S.RES_ITEM and ev[1] == "keyEvent" and ev[5] == "Right":
            out["right"].append((name, u32(d, 28)) if name != "changePropertyByControl" else
                                (name, u32(d, 28), u32(d, 36), pool.text(u32(d, 40)), pool.text(u32(d, 50))))
        elif owner == jid and name == "controlAppState":
            out["jump"][ev[4]] = (ev[3], pool.text(u32(d, 36)))
    return jid, out


class LabJump(unittest.TestCase):
    """The card's B2_5: MODE / Output rows gone; resolution = CUSTOM shows
    "› more options" and the popup's Right opens the lab page."""

    def test_structure(self):
        S.audit(CARD, IMAGE)
        S.native_parse(CARD["page"], CARD["pool"].data, IMAGE)
        self.assertEqual(objects(CARD["page"])[S.MENU].words(7)[2], 6)
        self.assertEqual(CARD["report"], [])
        self.assertFalse({"MV_SLMode", "MV_SLSize", "SL_MODE", "SL_SIZE", "MODE", "SIZE"} & set(CARD["pool"].added))
        self.assertLess(len(CARD["page"]), len(RES["page"]) - 50_000)

    def test_custom_jumps_and_says_more_options(self):
        jid, w = jump_wiring(CARD["page"], CARD["pool"])
        self.assertEqual(objects(CARD["page"])[jid].words(7)[4], S.SWITCH_PARENT)
        self.assertEqual(w["list"], {("<=", 1.0): ["Footer05"], ("==", 2.0): ["Footer02"]})
        # write (5), JumpEvent value <- the item's own value (6), focus back (7)
        self.assertEqual(w["right"], [("controlAppVariable", 5),
                                      ("changePropertyByControl", 6, jid, "controlValue", "value"),
                                      ("controlFocus", 7)])
        # value-change + value-equal (the List's own kind): item value = row + 1
        self.assertEqual(w["jump"], {3.0: (0x12, S.SIZE_JUMP_TO)})
        self.assertEqual(S.CUSTOM_ROW, 2)

    def test_a_wrong_jump_value_is_seen(self):
        """Mutation: JumpEvent's event set to 2.0 (FHD's item would jump)."""
        page = bytearray(CARD["page"])
        jid, _ = jump_wiring(CARD["page"], CARD["pool"])
        owner = None
        for r in N.split(CARD["page"]):
            d = r.to_bytes()
            if r.tag == 0x10003:
                owner = u32(d, 20)
            elif owner == jid and r.tag == 0x10006 and u32(d, 32) == 3:
                struct.pack_into(">f", page, r.offset + 40, 2.0)
        _, w = jump_wiring(bytes(page), CARD["pool"])
        self.assertNotIn(3.0, w["jump"])


class Mutants(unittest.TestCase):
    def test_without_scrollbar_schema_residue_appears(self):
        saved = dict(S.EXTRA_DESCRIPTORS)
        S.EXTRA_DESCRIPTORS.clear()
        S.NO_SCHEMA_OK.add("drawScrollbar")
        try:
            res = S.build(IMAGE)
        finally:
            S.EXTRA_DESCRIPTORS.update(saved)
            S.NO_SCHEMA_OK.discard("drawScrollbar")
        self.assertTrue(all(r["residue"] for r in res["report"]))

    def test_unknown_component_refused(self):
        S.NO_SCHEMA_OK.discard("scrollEvent")
        try:
            with self.assertRaisesRegex(S.BuildError, "no descriptor"):
                S.build(IMAGE)
        finally:
            S.NO_SCHEMA_OK.add("scrollEvent")

    def test_menu_child_count(self):
        page = bytearray(RES["page"])
        r = objects(RES["page"])[S.MENU]
        put(page, r.offset + 16, 6)
        with self.assertRaisesRegex(S.BuildError, "graph"):
            S.audit(with_page(bytes(page)), IMAGE)

    def test_dangling_reference(self):
        page = bytearray(RES["page"])
        lo = RES["report"][1]["ids"][0]
        rec = next(r for r in N.split(RES["page"])
                   if r.tag == 0x10005 and RES["pool"].text(u32(r.to_bytes(), 8)) == "drawScrollbar"
                   and u32(r.to_bytes(), 32) >= lo)
        put(page, rec.offset + 32, 4439 + 100000)
        with self.assertRaisesRegex(S.BuildError, "dangling"):
            S.audit(with_page(bytes(page)), IMAGE)

    def test_header_budget(self):
        page = bytearray(RES["page"])
        put(page, 8, u32(page, 8) - 1)                   # objects
        with self.assertRaisesRegex(S.BuildError, "allocation header"):
            S.audit(with_page(bytes(page)), IMAGE)

    def test_native_rejects_broken_record(self):
        page = bytearray(RES["page"])
        a = RES["abs_refs"][0][0]
        rec = next(r for r in N.split(RES["page"]) if r.offset <= a < r.offset + r.size)
        put(page, rec.offset + 4, u32(page, rec.offset + 4) + 4)   # record length lies
        with self.assertRaises(Exception):
            S.native_parse(bytes(page), RES["pool"].data, IMAGE)


def clone(page, report):
    """{object id: [record bytes]} for one clone (ids from the build report)."""
    lo, hi = report["ids"]
    extra = set(report.get("extra_ids", ()))
    out, owner = {}, None
    for r in N.split(page):
        d = r.to_bytes()
        if r.tag == 0x10003:
            owner = u32(d, 20)
        if owner is not None and (lo <= owner <= hi or owner in extra):
            out.setdefault(owner, []).append(d)
    return out


def ids(report):
    """donor id -> clone id (build() maps the sorted donor subtree in order)."""
    lo, _ = report["ids"]
    return {old: lo + i for i, old in enumerate(RES["sub"])}


class Rows(unittest.TestCase):
    """Each clone fits its own list: fp-native-ui section 2 rules 7-9."""
    POOL = RES["pool"]

    def rows(self, spec):
        return S.clone_rows(spec)

    def cursor_pairs(self, recs, lst):
        pool = self.POOL
        ev, fo = {}, {}
        for d in recs[lst]:
            name = pool.text(u32(d, 8))
            if d[3] == 0x06 and name == "controlValueEvent" and u32(d, 32) in (1, 3):
                ev[u32(d, 28)] = 0.0 if u32(d, 32) == 1 else struct.unpack_from(">f", d, 40)[0]
            elif d[3] == 0x09 and name == "controlFocus" and u32(d, 40) == lst:
                fo[u32(d, 24)] = pool.text(u32(d, 44))
        return {int(v): fo.get(k) for k, v in ev.items()}

    def cap(self, recs, obj, prop, at):
        hits = [d for d in recs[obj] if d[3] == 0x0E and u32(d, 28) == prop]
        self.assertEqual(len(hits), 1)
        return struct.unpack_from(">f", hits[0], at)[0]

    def check_clone(self, page, spec, report):
        m = ids(report)
        recs = clone(page, report)
        n = len(self.rows(spec))
        lst = m[4439]
        pairs = self.cursor_pairs(recs, lst)
        self.assertEqual(pairs, {v: str(v) for v in range(max(n, S.DONOR_ROWS))}, spec["key"])
        self.assertEqual(u32(recs[lst][0], 8), 17 + max(0, n - S.DONOR_ROWS))
        # MODE's rows are written on the camera: static cap 0, SetLimit sets it on show
        self.assertEqual(self.cap(recs, lst, 0xA, 32), 0 if spec["rows"] == "mode" else n - 1)
        self.assertEqual(self.cap(recs, m[S.LIST_ITEM], 3, 36), max(S.DONOR_ROWS, n))
        for obj in (S.SELECT, S.ICON_CHANGE):
            self.assertEqual(self.cap(recs, m[obj], 0x12, 32), max(S.DONOR_ROWS, n) - 1)
        # summary children, in parse order, carry the rows' literal labels
        kids = [o for o, rs in recs.items() if u32(rs[0], 24) == m[S.ICON_TEXT]]
        self.assertEqual(len(kids), max(S.DONOR_ROWS, n))
        self.assertEqual(u32(recs[m[S.ICON_TEXT]][0], 16), len(kids))
        for kid, row in zip(kids, self.rows(spec)):
            text = next(d for d in recs[kid] if self.POOL.text(u32(d, 8)) == "drawText")
            self.assertEqual((self.POOL.text(u32(text, 32)), text[36]), (row["summary"], 0))

    def test_mode_and_size_fit_their_lists(self):
        for spec, report in zip(S.CLONES, RES["report"]):
            with self.subTest(spec["key"]):
                self.check_clone(RES["page"], spec, report)

    def test_mode_has_room_for_every_sensor_mode_and_size_three(self):
        self.assertEqual([len(self.rows(s)) for s in S.CLONES], [70, 3])

    def test_set_limit_drives_modes_cap_from_sl_modecount(self):
        report = RES["report"][0]
        m = ids(report)
        recs = clone(RES["page"], report)
        lim = [o for o, rs in recs.items() if self.POOL.text(u32(rs[0], 28)) == "SetLimit"]
        self.assertEqual(len(lim), 1)
        rs = recs[lim[0]]
        self.assertEqual(u32(rs[0], 24), m[S.SELECT])                       # under MenuItem_Select
        names = [self.POOL.text(u32(d, 8)) for d in rs[1:]]
        self.assertEqual(names, ["objectBase", "controlValue", "appVariableEvent", "screenEvent",
                                 "changePropertyByControl", "appVariableChangeEvent",
                                 "changePropertyByControl"])
        bind, show, act1, change, act2 = rs[3], rs[4], rs[5], rs[6], rs[7]
        self.assertEqual((self.POOL.text(u32(bind, 40)), self.POOL.text(u32(change, 36))),
                         ("SL_ModeCount", "SL_ModeCount"))
        self.assertEqual((u32(show, 16), u32(change, 16)), (1, 1))
        for a in (act1, act2):
            self.assertEqual(u32(a, 36), m[4439])                            # MODE's own List
            self.assertEqual([self.POOL.text(u32(a, o)) for o in (40, 45, 50)],
                             ["controlValue", "max-value", "value - 1"])
        sel = recs[m[S.SELECT]][0]
        kids = [o for o, r2 in recs.items() if u32(r2[0], 24) == m[S.SELECT]]
        self.assertEqual(u32(sel, 16), len(kids))

    def test_a_missing_cursor_pair_is_caught(self):
        """Mutation: drop MODE's last cursor event (v = 11)."""
        page = bytearray(RES["page"])
        report = RES["report"][0]
        lst = ids(report)[4439]
        owner = None
        for r in N.split(RES["page"]):
            d = r.to_bytes()
            if r.tag == 0x10003:
                owner = u32(d, 20)
            if owner == lst and r.tag == 0x10006 and self.POOL.text(u32(d, 8)) == "controlValueEvent" \
                    and u32(d, 32) == 3 and struct.unpack_from(">f", d, 40)[0] == 11.0:
                struct.pack_into(">f", page, r.offset + 40, 99.0)
        with self.assertRaises(AssertionError):
            self.check_clone(bytes(page), S.CLONES[0], report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
