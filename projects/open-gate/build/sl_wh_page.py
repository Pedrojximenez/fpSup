#!/usr/bin/env python3
"""Sensor Lab: the Width / Height digit page (a private page under SL_LAB).

Base: the stock frame-guide digit page B5_4_2_1, its 幅/高さ editor (object
4635): "dd.dd x dd.dd mm", four digit objects per side.  Here the same eight
digit objects are thousands / hundreds / tens / ones of a pixel width and
height ("1920 x 1080"); the dots and "mm" go, and so do the page's other three
editors (offset, aspect ratio, ratio / scaling).

Stock's digits do nothing themselves: Up / Down send sync-requests
(FrameGuide_W_TensPlace_Inc ...) to the native frame-guide handler, which
writes the stock frame-guide settings (MV_FRMGUIDE_*) -- the first rule keeps
both out.  Each digit here counts on its own, with this page's own records:

  Up / Down   controlValue 'dst + 1' / 'dst - 1' (0..9, looping; FooterSelect's
              changePropertyByControl), then controlAppVariable  digit var <-
              controlValue (FooterSelect's)
  digit var   -> controlValue (an appVariableEvent like HeaderActiveTab's), so a
              digit starts from the value shown
  OK / MENU   sync-request "Return" (the digit's own controlAppState, re-aimed)
  MODE, the min/max arrows: gone

The digit variables (SL_W_3 .. SL_H_0, sl_menu.c) drive stock's glyph
animations unchanged; sl_modes.c subscribes to them and posts W / H to
SL_LAB's info panel.  Offline only.
"""
from __future__ import annotations

import struct

import sl_b25_page as P
import sl_size_page as SZ
from sl_b25_page import A, BM, N, check, local_ids, put, u32

PAGE_NAME, PARENT, BASE_SET = "SL_WH", "SL_LAB", "B5_4_2_1"
INPUT_TYPE, EDITOR = 4631, 4635
OTHER_EDITORS = (4632, 4633, 4634)                    # offset, aspect, aspect / scaling
EDITOR_DROP = (4636, 4666, 4681)                      # the two dots, "mm"
# digit object -> (stock variable, private variable); the private ones are
# thousands .. ones (sl_menu.c names 18..25)
DIGITS = {96: ("MV_FRMGUIDE_WidthTens", "SL_W_3"), 100: ("MV_FRMGUIDE_WidthOnes", "SL_W_2"),
          4637: ("MV_FRMGUIDE_Width1st", "SL_W_1"), 4644: ("MV_FRMGUIDE_Width2nd", "SL_W_0"),
          4652: ("MV_FRMGUIDE_HeightTens", "SL_H_3"), 4659: ("MV_FRMGUIDE_HeightOnes", "SL_H_2"),
          4667: ("MV_FRMGUIDE_Height1st", "SL_H_1"), 4674: ("MV_FRMGUIDE_Height2nd", "SL_H_0")}
DIGIT_VARS = tuple(v for _, v in DIGITS.values())
# Root's screenEvent focuses the object in MENU_Level4, which stock's native
# handler filled; here a private variable starting at the first digit (r32: no
# focus at all, keys went nowhere)
RENAME = {**{s: v for s, v in DIGITS.values()}, "MV_FRMGUIDE_InputType": "SL_O_In",
          "MENU_Level4": "SL_WhFocus"}
FIRST_DIGIT = 96
TEMPLATE_OWNER, BIND_OWNER, LOOP_DIGIT = 31, 55, 4674  # FooterSelect, HeaderActiveTab, H_2nd
# W_Tens' glyph only has 0..3 (mm tens); H_Tens' has 0..9
GLYPH_SHORT, GLYPH_FULL, GLYPH_CLIP = 94, 4654, 2
FORBIDDEN = ("MV_FRMGUIDE_", "FrameGuide_", "CM_ZBRHIL_")


def base_page():
    import sl_pages
    return sl_pages.set_bytes(BASE_SET)


def _name(d, pool):
    return pool.text(u32(d, 8))


def _templates(recs, pool):
    by = {}
    owner = None
    for r in recs:
        d = r.to_bytes()
        if r.tag == 0x10003:
            owner = u32(d, 20)
            continue
        if owner == TEMPLATE_OWNER and r.tag == 0x10009:
            n = _name(d, pool)
            if n == "changePropertyByControl" and u32(d, 32) == 0x1B:
                by.setdefault(pool.text(u32(d, 50)), bytes(d))
            elif n == "controlAppVariable" and pool.text(u32(d, 36)) == "AppVariable0000":
                by["write"] = bytes(d)
        elif owner == BIND_OWNER and r.tag == 0x10006 and _name(d, pool) == "appVariableEvent" \
                and pool.text(u32(d, 49)) == "value":
            by["bind"] = bytes(d)
        elif owner == LOOP_DIGIT and r.tag == 0x1000E:
            by["counter"] = bytes(d)
        elif owner == GLYPH_FULL and r.tag == 0x1000A and u32(d, 24) == GLYPH_CLIP:
            by["glyph"] = bytes(d)
    check({"dst + 1", "dst - 1", "write", "bind", "counter", "glyph"} <= set(by), f"templates {sorted(by)}")
    check(len(by["write"]) == 59 and u32(by["write"], 45) == TEMPLATE_OWNER, "write template")
    check(u32(by["counter"], 28) == 0xA and struct.unpack_from(">f", by["counter"], 32)[0] == 59.0, "counter")
    return by


def _digit(blocks, d, stock_var, var, tm, pool, refs):
    """One digit object's records, rewritten.  Returns (records, records gone)."""
    recs = [bytearray(x) for x in blocks]
    gone, out = [], []
    ids = local_ids(recs, range(len(recs)))
    i = 0
    obj = recs[0]
    # controlValue: 0..9, looping
    for k, x in enumerate(recs):
        if u32(x, 0) == 0x1000E and _name(x, pool) == "controlValue":
            c = bytearray(tm["counter"])
            put(c, 20, d)
            put(c, 24, u32(x, 24))
            struct.pack_into(">f", c, 32, 9.0)
            check(u32(x, 24) == 2, "digit controlValue local id")
            recs[k] = c

    def action(tmpl, event, index):
        a = bytearray(tmpl)
        put(a, 20, d)
        put(a, 24, event)
        put(a, 28, index)
        return a

    var_off, private = pool.intern(var)
    ret_off = pool.find("Return")
    new = []
    while i < len(recs):
        x = recs[i]
        if u32(x, 0) == 0x10006:
            n = u32(x, 16)
            acts = recs[i + 1:i + 1 + n]
            name = _name(x, pool)
            key = pool.text(u32(x, 20)) if name == "keyEvent" else None
            watched = pool.text(u32(x, 36)) if name == "appVariableChangeEvent" else None
            if key in ("Up", "Down"):
                check(n == 1 and _name(acts[0], pool) == "controlAppState", f"{d} {key}")
                step = action(tm["dst + 1" if key == "Up" else "dst - 1"], u32(x, 28), 1)
                put(step, 36, d)
                write = action(tm["write"], u32(x, 28), 2)
                put(write, 36, var_off)
                if private:
                    refs.append((write, 36, var))
                put(write, 45, d)
                put(x, 16, 2)
                out += [x, step, write]
                new += [step, write]
                gone += [A.Record(0, bytes(acts[0]))]
            elif key in ("OK", "Menu"):
                check(n == 1 and _name(acts[0], pool) == "controlAppState", f"{d} {key}")
                up_state = next(a for a in recs if u32(a, 0) == 0x10009 and _name(a, pool) == "controlAppState"
                                and len(a) == 41)
                back = action(up_state, u32(x, 28), 1)
                put(back, 36, ret_off)
                out += [x, back]
                new.append(back)
                gone += [A.Record(0, bytes(acts[0]))]
            elif key == "MODE" or (watched and watched.endswith("Arrow")):
                gone += [A.Record(0, bytes(y)) for y in [x] + acts]
                put(obj, 8, u32(obj, 8) - 1)
            else:
                out += [x] + acts
            i += 1 + n
            continue
        out.append(x)
        i += 1
    # digit var -> controlValue (local id 2), so a digit starts from the value shown
    bind = bytearray(tm["bind"])
    put(bind, 24, d)
    put(bind, 28, max(ids) + 1)
    put(bind, 40, var_off)
    if private:
        refs.append((bind, 40, var))
    put(bind, 45, 2)
    out.insert(2, bind)                                  # after objectBase, controlValue
    put(obj, 8, u32(obj, 8) + 1)
    return out, gone, [bind] + new


def build_wh_page(img, pool, refs):
    schemas = P.load_schemas(img)
    recs = N.split(base_page())
    objs = SZ.objects(recs, pool)
    tm = _templates(recs, pool)
    check(objs[EDITOR]["parent"] == INPUT_TYPE and all(objs[o]["parent"] == INPUT_TYPE for o in OTHER_EDITORS),
          "InputType editors changed")
    drop = set()
    for root in OTHER_EDITORS + EDITOR_DROP:
        a, b = SZ.span(recs, objs, SZ.subtree(objs, root), root)
        drop.update(range(a, b))
    removed = [A.Record(0, recs[i].to_bytes()) for i in sorted(drop)]
    # per object blocks of the kept stream
    seq, k, added = [], 0, []
    digit_at = {}
    while k < len(recs):
        if k in drop:
            k += 1
            continue
        r = recs[k]
        if r.tag == 0x10003 and r.words(7)[3] in DIGITS:
            d = r.words(7)[3]
            j = k + 1
            while recs[j].tag != 0x10003:
                j += 1
            out, gone, add = _digit([x.to_bytes() for x in recs[k:j]], d, *DIGITS[d], tm, pool, refs)
            seq += out
            removed += gone
            added += add
            k = j
            continue
        x = bytearray(r.to_bytes())
        if r.tag == 0x1000A and u32(x, 20) == GLYPH_SHORT and u32(x, 24) == GLYPH_CLIP:
            g = bytearray(tm["glyph"])
            put(g, 20, GLYPH_SHORT)
            removed.append(A.Record(0, bytes(x)))
            added.append(g)
            x = g
        seq.append(x)
        k += 1
    # page-wide renames (digit variables, the editor switch)
    rename = {pool.find(a): b for a, b in RENAME.items()}
    check(None not in rename, "rename strings")
    for x in seq:
        for off, kind in P.typed_fields(bytes(x), pool, schemas):
            if kind in ("str", "text") and u32(x, off) in rename:
                new = rename[u32(x, off)]
                o, private = pool.intern(new)
                put(x, off, o)
                if private:
                    refs.append((x, off, new))
    # child counts
    kids = {}
    for x in seq:
        if u32(x, 0) == 0x10003:
            kids[u32(x, 24)] = kids.get(u32(x, 24), 0) + 1
    for x in seq:
        if u32(x, 0) == 0x10003:
            put(x, 16, kids.get(u32(x, 20), 0))
    # header
    header = A.parse_header(A.Record(0, recs[0].to_bytes()), pool.text)
    plus = [A.Record(0, bytes(x)) for x in added]
    cc = A.component_counts(plus, pool.text)
    for kk, v in A.component_counts(removed, pool.text).items():
        cc[kk] = cc.get(kk, 0) - v
    check(not [kk for kk in set(cc) - set(header["component_counts"]) if cc[kk] > 0], "new component kinds")
    cc = {kk: v for kk, v in cc.items() if kk in header["component_counts"]}
    plus_clips = [A.parse_clip(x, pool.text) for x in plus if x.tag == 0x1000A]
    delta = {"objects": -sum(1 for x in removed if x.tag == 0x10003), "component_counts": cc,
             "group_budgets": [],
             "clip_property_counts": [len(c["properties"]) for c in plus_clips],
             "property_key_counts": [len(p["keys"]) for c in plus_clips for p in c["properties"]]}
    seq[0] = bytearray(BM.extend_header(A.Record(0, recs[0].to_bytes()), header, delta))
    return seq


def forbidden_left(page, pool, schemas):
    """Every field naming a stock frame-guide variable / request (first rule)."""
    out = []
    for r in N.split(page):
        d = r.to_bytes()
        for off, kind in P.typed_fields(d, pool, schemas):
            t = pool.text(u32(d, off)) if kind in ("str", "text") else None
            if t and t.startswith(FORBIDDEN):
                out.append((r.offset + off, t))
    return out


def check_page(page, pool, img):
    import sl_lab_page as LAB
    shape = P.page_shape(page, pool)
    check(not shape["orphans"] and not shape["bad_child_counts"], "object graph")
    h = shape["header_minus_actual"]
    check(all(v >= 0 for v in h["components"].values()) and h["objects"] >= 0 and h["clips"] >= 0
          and h["clip_properties"] >= 0 and h["keys"] >= 0, f"header below the page's needs: {h}")
    objs = shape["objects"]
    schemas = P.load_schemas(img)
    for r in N.split(page):
        d = r.to_bytes()
        for off, kind in P.typed_fields(d, pool, schemas):
            v = u32(d, off)
            if kind == "obj" and v not in (0, 0xFFFFFFFF):
                check(v in objs, f"dangling object reference {v} in tag {r.tag:#x}")
    check(not forbidden_left(page, pool, schemas), f"stock frame-guide names left: {forbidden_left(page, pool, schemas)[:4]}")
    check(not LAB.duplicate_local_ids(page), "duplicate local ids")
    P.native_parse(page, pool.data, img)
    return shape


if __name__ == "__main__":
    import imx410_plan as PL
    PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = True, False, False
    img = (P.ROOT / "out/MAIN_c0000000.bin").read_bytes()
    pool = P.Pool(img[P.U.POOL_START - P.B:P.U.POOL_START - P.B + P.U.POOL_SIZE])
    refs = []
    seq = build_wh_page(img, pool, refs)
    page, abs_refs = SZ.assemble(seq, refs)
    shape = check_page(page, pool, img)
    print(len(page), "bytes", len(abs_refs), "refs", list(pool.added))
