#!/usr/bin/env python3
"""Sensor Lab: the SIZE sub page (design §8.12), a private page (sl_pages.py).

The camera taught how a private page must look (r16, 2026-10-03): a whole stock
page works (B2_6_2's copy: keys, focus, MENU back), a bare Root with one key
event does not.  The only stock sub pages with a Menu of popup rows are B2_5 and
B3_5, so this page is B2_5 itself:

  - the stock rows (B2_5_1..B2_5_5, objects 90 / 91 / 4361 / 4253 / 4433) and the
    format swap (ControlModeChange 3114 + Menu's FormatChange group) go;
  - four copies of the frame-rate row 4433 take their places (y 0 / 81 / 162 /
    243), each with its own private value and list, as the MODE / SIZE rows on
    the private B2_5 are made (sl_b25_page.py, camera-proven):
        SCALE  AUTO SCALE / RAW SCALE / anamorphic 1.33x..2.0x / CUSTOM SCALE
        SIZE   width x height (static for now; on the camera later)
        BIN    hbin x vbin
        RWZM   display only: its Right / OK do not open the popup
  - what pointed at the old rows is pointed at the new: Root's LoopEvent group
    (the Up/Down wrap order), EnterFocusEvent (focus on entry),
    EnterSubmenuWidth (the popup lists).
The two lock / focus variables are shared by the four rows (EXCL_SLSize always
0, SL_ListFocusSize); each private string costs boot time (fp-native-ui §8e), so
the collapsed summaries show stock row numbers for now.  Memory only: no
setting is read or written.  Offline only.
"""
from __future__ import annotations

import struct

import sl_b25_page as P
from sl_b25_page import A, BM, N, U, check, put, u32

PAGE_NAME = "SL_SIZE_PG"
DONOR_ROW, DONOR_SELECT, DONOR_LIST = 4433, 4434, 4439
OLD_ROWS = (90, 91, 4361, 4253, 4433)            # B2_5_1..B2_5_5 under Menu 89
FORMAT_SWITCH = 3114                             # ControlModeChange (MV_RecordingFormat)
LOOP_GROUP_OWNER, LOOP_GROUP = 1, "LoopEvent"
ENTER_FOCUS, SUBMENU_WIDTH = 29769, 29879
SHARED = {"EXCL_FrameRate": "EXCL_SLSize", "B2_n5_ListFocus4": "SL_ListFocusSize"}
# MENU_Level2 holds the OBJECT ID of the focused row (camera r17, 2026-10-03: 30053
# = the private B2_5's SIZE row): every row writes it on focus, EnterFocusEvent
# focuses whatever it names.  On this page that id is no row -> nothing had focus,
# Up/Down/MENU dead.  The page gets its own variable, set before first use to the
# SCALE row (sl_menu.c registers it with FOCUS0); B2_5's MENU_Level2 is left alone,
# so back on B2_5 the cursor is still on SIZE.
FOCUS_VAR = "SL_SizeFocus"
RATE_LISTS = ("B2_5_5", "B2_5_5_excl", "B2_5_5_excl2", "B2_5_5_excl3", "B2_5_5_excl4", "B2_5_5_excl5")


def rows_spec():
    import sl_lists as L
    return [
        dict(key="SCALE", y=0.0, var="MV_SLScale", list=L.SCALE_NAME, title="SCALE", rows=L.SCALE_ROWS),
        dict(key="SIZE", y=81.0, var="MV_SLWH", list=L.WH_NAME, title="SIZE", rows=L.WH_ROWS),
        dict(key="BIN", y=162.0, var="MV_SLBin", list=L.BIN_NAME, title="BIN", rows=L.BIN_ROWS),
        dict(key="RWZM", y=243.0, var="MV_SLRwzm", list=L.RWZM_NAME, title="RWZM", rows=L.RWZM_ROWS,
             display_only=True),
    ]


def objects(recs, pool):
    objs = {}
    for i, r in enumerate(recs):
        if r.tag == 0x10003:
            w = r.words(7)
            objs[w[3]] = dict(parent=w[4], idx=i, n=w[2], name=pool.text(w[5]))
    return objs


def subtree(objs, root):
    sub, grew = {root}, True
    while grew:
        grew = False
        for k, v in objs.items():
            if v["parent"] in sub and k not in sub:
                sub.add(k)
                grew = True
    return sub


def span(recs, objs, sub, root):
    """Record indices [start, end) of a contiguous object subtree."""
    start = objs[root]["idx"]
    end = start + 1
    while end < len(recs) and not (recs[end].tag == 0x10003 and recs[end].words(7)[3] not in sub):
        end += 1
    check(len([r for r in recs[start:end] if r.tag == 0x10003]) == len(sub), f"subtree {root} not contiguous")
    return start, end


def clone(donor, sub, spec, pool, schemas, next_id, refs):
    """One copy of the frame-rate row, renamed to the spec (sl_b25_page.build's way)."""
    mapping = {old: next_id + i for i, old in enumerate(sorted(sub))}
    rename = {"MV_FrameRate": spec["var"], **SHARED, **{n: spec["list"] for n in RATE_LISTS}}
    rename = {pool.find(old): new for old, new in rename.items() if pool.find(old) is not None}
    title_off = pool.find(P.TITLE_ID)
    out = []
    for r in donor:
        rec = bytearray(r.to_bytes())
        for off, kind in P.typed_fields(bytes(rec), pool, schemas):
            v = u32(rec, off)
            if kind == "obj" and v in mapping:
                put(rec, off, mapping[v])
            elif kind in ("str", "text") and v in rename:
                new_off, private = pool.intern(rename[v])
                put(rec, off, new_off)
                if private:
                    refs.append((rec, off, rename[v]))
            elif kind == "text" and v == title_off and u32(rec, 20) == mapping[P.TITLE_OWNER]:
                new_off, private = pool.intern(spec["title"])
                put(rec, off, new_off)
                rec[off + 4] = 0
                if private:
                    refs.append((rec, off, spec["title"]))
        if u32(rec, 0) == 0x10008:
            for o in range(8, len(rec) - 3):
                if u32(rec, o) in mapping and u32(rec, o) > 64:
                    put(rec, o, mapping[u32(rec, o)])
        out.append(rec)
    root = mapping[DONOR_ROW]
    base = next(r for r in out if u32(r, 0) == 0x10004 and u32(r, 20) == root)
    pos = bytes(base).find(struct.pack(">f", 243.0))
    check(pos > 0, "row position field not found")
    struct.pack_into(">f", base, pos, spec["y"])
    P.align_popup(out, mapping, spec["y"])
    added, next_id = P.grow_rows(out, mapping, pool, refs, spec["rows"], next_id + len(sub))
    return out, mapping, added, next_id


def display_only(out, mapping, pool):
    """Right and OK on the row no longer open its popup: both keyEvents and their
    actions go.  Returns the removed records."""
    sel = mapping[DONOR_SELECT]
    keys = {pool.find("Right"), pool.find("OK")}
    gone = []
    i = 0
    while i < len(out):
        r = out[i]
        if (u32(r, 0) == 0x10006 and u32(r, 24) == sel and pool.text(u32(r, 8)) == "keyEvent"
                and u32(r, 20) in keys):
            n = u32(r, 16)
            acts = out[i + 1:i + 1 + n]
            check(all(u32(a, 0) == 0x10009 and u32(a, 20) == sel and u32(a, 24) == u32(r, 28) for a in acts),
                  "key actions not where expected")
            gone += [r] + acts
            del out[i:i + 1 + n]
            continue
        i += 1
    check(len([g for g in gone if u32(g, 0) == 0x10006]) == 2, "Right / OK keyEvents not found")
    obj = next(r for r in out if u32(r, 0) == 0x10003 and u32(r, 20) == sel)
    put(obj, 8, u32(obj, 8) - 2)                       # w0 counts the events
    return gone


def retarget_loop(rec, pool, old_ids, new_ids):
    """Root's LoopEvent group: its member list in row order -> the new rows."""
    d = bytearray(rec)
    hits = [o for o in range(8, len(d) - 3) if u32(d, o) in old_ids]
    found = [u32(d, o) for o in hits]
    check(found == [4247, 4297, 4362, 4254, 4434], f"LoopEvent members changed: {found}")
    # five {id, flag} pairs -> four: drop B2_5_3's (4362, the format swap's other half)
    at = hits[2]
    del d[at:at + 8]
    hits = [o for o in range(8, len(d) - 3) if u32(d, o) in old_ids]
    for o, new in zip(hits, new_ids):
        put(d, o, new)
    # group layout (as FormatChange in sl_b25_page.custom_switch): +8 states,
    # +16 members, +20 name, +24 owner, 21-byte states, then {id, flag} members
    check(u32(d, 16) == 5, "LoopEvent member count")
    put(d, 16, 4)
    put(d, 4, len(d))
    return d


def focus0(img):
    """The SCALE row's MenuItem_Select id: what SL_SizeFocus starts at."""
    import imx410_rate_ui as U2
    pool = P.Pool(img[U2.POOL_START - P.B:U2.POOL_START - P.B + U2.POOL_SIZE])
    objs = objects(N.split(P.base_page(img)), pool)
    sub = sorted(subtree(objs, DONOR_ROW))
    return max(objs) + 1 + sub.index(DONOR_SELECT)


def build_size_page(img, pool, refs):
    """The page bytes; private strings are interned into `pool` and their page
    fields appended to `refs` as (record, offset, text)."""
    schemas = P.load_schemas(img)
    recs = N.split(P.base_page(img))
    objs = objects(recs, pool)
    check(objs[P.MENU]["n"] == 6 and [k for k, v in objs.items() if v["parent"] == P.MENU] ==
          [1346, 90, 91, 4361, 4253, 4433], "B2_5 Menu changed")
    donor_sub = subtree(objs, DONOR_ROW)
    d0, d1 = span(recs, objs, donor_sub, DONOR_ROW)
    donor = recs[d0:d1]
    next_id = max(objs) + 1
    clones, maps, added = [], [], []
    for spec in rows_spec():
        out, mapping, grown, next_id = clone(donor, donor_sub, spec, pool, P.load_schemas(img), next_id, refs)
        if spec.get("display_only"):
            gone = display_only(out, mapping, pool)
            added += [("-", g) for g in gone]
        clones.append(out)
        maps.append(mapping)
        added += [("+", g) for g in grown]
    # what goes: the old rows, the format switch, Menu's FormatChange group
    drop = set()
    for root in OLD_ROWS + (FORMAT_SWITCH,):
        s = subtree(objs, root)
        a, b = span(recs, objs, s, root)
        drop.update(range(a, b))
    fmt = [i for i, r in enumerate(recs) if r.tag == 0x1000B and P.Pool.text(pool, u32(r.to_bytes(), 20)) == "FormatChange"]
    check(len(fmt) == 1, "FormatChange group")
    drop.update(fmt)
    removed = [recs[i] for i in sorted(drop)]
    first_row = objs[90]["idx"]
    new_sel = [m[DONOR_SELECT] for m in maps]
    new_list = [m[DONOR_LIST] for m in maps]
    seq = []
    for i, r in enumerate(recs):
        if i == first_row:
            for out in clones:
                seq.extend(out)
        if i in drop:
            continue
        d = bytearray(r.to_bytes())
        if r.tag == 0x10003:
            w = r.words(7)
            if w[3] == P.MENU:
                put(d, 16, 1 + len(clones))               # Blind + the rows
            elif w[3] == FORMAT_SWITCH:
                pass
            elif w[3] == 1:
                put(d, 16, w[2] - 1)                      # Root lost 3114
        elif r.tag == 0x1000B and pool.text(u32(d, 20)) == LOOP_GROUP and u32(d, 24) == LOOP_GROUP_OWNER:
            d = retarget_loop(d, pool, {4247, 4297, 4362, 4254, 4434}, new_sel)
        seq.append(d)
    # focus targets outside the rows
    owner = None
    for d in seq:
        if u32(d, 0) == 0x10003:
            owner = u32(d, 20)
            continue
        if u32(d, 0) == 0x10009 and pool.text(u32(d, 8)) == "controlFocus":
            if owner == ENTER_FOCUS and u32(d, 40) == 4254:
                put(d, 40, new_sel[0])
            elif owner == SUBMENU_WIDTH and u32(d, 40) in (4302, 4439):
                put(d, 40, new_list[0] if u32(d, 40) == 4302 else new_list[1])
    # the page's own focus variable instead of MENU_Level2, everywhere
    level2 = pool.find("MENU_Level2")
    focus_off, private = pool.intern(FOCUS_VAR)
    renamed = 0
    for d in seq:
        for off, kind in P.typed_fields(bytes(d), pool, schemas):
            if kind in ("str", "text") and u32(d, off) == level2:
                put(d, off, focus_off)
                renamed += 1
                if private:
                    refs.append((d, off, FOCUS_VAR))
    check(renamed >= 5, f"MENU_Level2 found {renamed} times")
    # allocation header: + four clones (and their growth), - what went
    header = A.parse_header(A.Record(0, recs[0].to_bytes()), pool.text)
    plus = [A.Record(0, bytes(x)) for out in clones for x in out]
    minus = [A.Record(0, r.to_bytes()) for r in removed]
    # `plus` is the clones as they end (grown, display-only keys already gone)
    cc = A.component_counts(plus, pool.text)
    for k, v in A.component_counts(minus, pool.text).items():
        cc[k] = cc.get(k, 0) - v
    plus_clips = [A.parse_clip(x, pool.text) for x in plus if x.tag == 0x1000A]
    all_groups = [r for r in recs if r.tag == 0x1000B]
    donor_groups = [header["groups"][all_groups.index(r)] for r in donor if r.tag == 0x1000B]
    delta = {"objects": sum(1 for x in plus if x.tag == 0x10003) - sum(1 for x in minus if x.tag == 0x10003),
             "component_counts": cc,
             "group_budgets": donor_groups * len(clones),
             "clip_property_counts": [len(c["properties"]) for c in plus_clips],
             "property_key_counts": [len(p["keys"]) for c in plus_clips for p in c["properties"]]}
    seq[0] = bytearray(BM.extend_header(A.Record(0, recs[0].to_bytes()), header, delta))
    return seq


def assemble(seq, refs):
    """Page bytes and its private-string fields as page offsets."""
    at, where = 0, {}
    for x in seq:
        where[id(x)] = at
        at += len(x)
    page = b"".join(bytes(x) for x in seq)
    abs_refs = sorted({(where[id(rec)] + off, text) for rec, off, text in refs if id(rec) in where})
    return page, abs_refs


def check_refs(page, abs_refs, pool):
    """Each listed word holds its string's provisional offset, and no other word
    equals a private offset (a missed string field would not be patched)."""
    for a, text in abs_refs:
        check(u32(page, a) == pool.added[text], f"ref at {a:#x} is not {text!r}")
    private, listed = set(pool.added.values()), {a for a, _ in abs_refs}
    stray = [a for a in range(0, len(page) - 3) if u32(page, a) in private and a not in listed]
    check(not stray, f"unlisted words equal to private offsets at {stray[:5]}")


def check_page(page, pool, img):
    """Structure: exact objects, no orphans, child counts right, every typed
    object field resolves, header totals cover the page; then the original
    interpreter parses it to the end."""
    shape = P.page_shape(page, pool)
    h = shape["header_minus_actual"]
    # objects: the r10 base declares one more than it holds (Icon08 4465 dropped,
    # header kept -- camera-proven); the same holds here
    base = P.page_shape(P.base_page(img), pool)["header_minus_actual"]
    check(h["objects"] == base["objects"] and not shape["orphans"] and not shape["bad_child_counts"],
          f"object graph {h}")
    check(all(v >= 0 for v in h["components"].values()) and h["groups"] >= 0 and
          all(x >= 0 for x in h["group_slots"]) and h["clips"] >= 0 and h["clip_properties"] >= 0 and
          h["keys"] >= 0, f"header below the page's needs: {h}")
    objs = shape["objects"]
    schemas = P.load_schemas(img)
    for r in N.split(page):
        d = r.to_bytes()
        for off, kind in P.typed_fields(d, pool, schemas):
            v = u32(d, off)
            if kind == "obj" and v not in (0, 0xFFFFFFFF) and v not in P.KNOWN_DANGLING:
                check(v in objs, f"dangling object reference {v} in tag {r.tag:#x}")
    P.native_parse(page, pool.data, img)
    return shape


if __name__ == "__main__":
    import imx410_plan as PL
    PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = True, False, False
    img = (P.ROOT / "out/MAIN_c0000000.bin").read_bytes()
    pool = P.Pool(img[U.POOL_START - P.B:U.POOL_START - P.B + U.POOL_SIZE])
    refs = []
    seq = build_size_page(img, pool, refs)
    page, abs_refs = assemble(seq, refs)
    shape = check_page(page, pool, img)
    check_refs(page, abs_refs, pool)
    print(len(page), "bytes", len(abs_refs), "refs", list(pool.added))
    print("menu", [(k, v["name"]) for k, v in shape["objects"].items() if v["parent_id"] == P.MENU])
    print("focus0", focus0(img))
