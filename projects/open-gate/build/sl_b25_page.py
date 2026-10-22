#!/usr/bin/env python3
"""Sensor Lab: private B2_5 (錄影設定) page.

Now (2026-10-03, WITH_CLONES False): stock rows only, plus resolution CUSTOM ->
"› more options" -> the lab page (lab_jump).  Below: the MODE / SIZE clone rows,
kept behind WITH_CLONES.

Design: projects/open-gate/notes/IMX410_FULL_DESIGN.md §8.12.  Phase A (offline
only): clone the frame-rate row subtree (object 4433) twice from the r10 B2_5
page, remap every object ID, rename the row-specific strings to private ones,
place the clones at y=324 / y=405 (row pitch 81, Menu height 486 = 6 rows), and
extend Menu's child count and the allocation header.  Output is a page plus the
private strings it needs and every page offset that holds one of them (so the
runtime can patch them to the shared FSPL pool offsets).

No camera, no card.  The installer (phase B) and the private NBR with the two
.cvm lists (phase C) are separate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / "research/ui/tools/nbu_probe"), str(ROOT / "research/ui/tools"),
                str(ROOT / "fpSup/lossless/menu")]
import nbu_format as N                      # noqa: E402
import native_ui_audit as A                 # noqa: E402
import build_menu_candidate as BM           # noqa: E402
import imx410_rate_ui as U                  # noqa: E402

B = 0xC0000000
MENU, ROW = 89, 4433                       # Menu container; frame-rate row (B2_5_5)
ROW_PITCH = 81.0
# Per clone: y, and string renames (row-specific -> private).  Everything else
# (system variables, animation set names, shared text) stays shared.
CLONES = (
    dict(key="MODE", y=324.0, rename={
        "MV_FrameRate": "MV_SLMode", "EXCL_FrameRate": "EXCL_SLMode",
        "B2_n5_ListFocus4": "SL_ListFocusMode", "B2_5_5": "SL_MODE",
        **{v: "SL_MODE" for v in ("B2_5_5_excl", "B2_5_5_excl2", "B2_5_5_excl3",
                                  "B2_5_5_excl4", "B2_5_5_excl5")}},
         title="MODE", rows="mode"),
    dict(key="SIZE", y=405.0, rename={
        "MV_FrameRate": "MV_SLSize", "EXCL_FrameRate": "EXCL_SLSize",
        "B2_n5_ListFocus4": "SL_ListFocusSize", "B2_5_5": "SL_SIZE",
        **{v: "SL_SIZE" for v in ("B2_5_5_excl", "B2_5_5_excl2", "B2_5_5_excl3",
                                  "B2_5_5_excl4", "B2_5_5_excl5")}},
         title="SIZE", rows="size"),
)
# Rows of each clone's own list (sl_lists.py) and what the popup / summary need
# for them (fp-native-ui section 2 rules 7-9, imx410_rate_ui): one cursor pair
# per row past the donor's ten, ListItem instances = max(donor, rows), List cap
# = rows - 1, MenuItem_Select / IconChange caps = max(donor, rows - 1), and one
# summary IconText per row with the row's literal label.  Only with
# WITH_PRIVATE_LISTS (the stock-list step keeps the donor's frame-rate rows).
WITH_ROWS = True
# False (2026-10-03, the user: "外面的mode 與size 可以收掉了"): no MODE / Output rows on
# B2_5; their content lives on the lab page.  The clone machinery stays for tests.
WITH_CLONES = False
# Resolution = CUSTOM: "› more options", and the popup's Right opens SIZE_JUMP_TO (lab_jump).
WITH_LAB_JUMP = True
# SIZE's Right key jumps to a private page (sl_pages.py) instead of opening its popup.
WITH_SIZE_JUMP = True
LIST_ITEM, SELECT, ICON_CHANGE, ICON_TEXT = 4440, 4434, 4438, 4448
DONOR_ROWS = 10                            # r10 frame-rate row: v = 0..9
# False = keep the stock frame-rate list names (B2_5_5 and its _excl variants)
# on both clones: an on-camera step that tests the page, the switch and the
# private variables before the private lists exist (phase C).  The values the
# rows write stay in the private integers either way.
WITH_PRIVATE_LISTS = True
# CUSTOM-only lists (sl_lists.py): the frame-rate / bit-depth List's model clip
# gets one more frame (EXCL value 6 / 2, written by sl_excl.S under CUSTOM) that
# names the private list, and the same clip animates the List's controller cap
# (controlValue, component 3, "max-value") so stock lists keep stock caps.
WITH_CUSTOM_LISTS = True
CUSTOM_LISTS = (  # (List, clip, rows per stock frame -> cap, private frame, private name, cap, group owner, group)
    dict(list=4439, clip=17, frames=(0, 33, 66, 100, 133, 166), stock_cap=8.0,
         frame=200, name="SL_RATE", cap=9.0, group_owner=4434, group="ExclList"),
    dict(list=4302, clip=17, frames=(0, 33), stock_cap=2.0,
         frame=66, name="SL_BIT", cap=3.0, group_owner=4302, group="SetList"),
)
TITLE_ID = "0315"                          # stock frame-rate title string ID
B25_ENTRY_OFFSET = 0x19C130                # runtime entry +08 for B2_5 (from 0xC18C0460), read on camera
SWITCH_DONOR, SWITCH_PARENT = 3114, 1         # ControlModeChange (MV_RecordingFormat -> FormatChange)
SWITCH_NAME = "SL_CustomChange"
CUSTOM_ROW = 2                              # resolution row of CUSTOM (0xC2E4020C pairs (4,2))
TITLE_OWNER = 4447                         # Name object whose drawText shows the row title
# Native descriptors the lossless builder does not carry.  drawScrollbar (LE
# {kind, name, default} x 8 at 0xC2E03A50) holds the List it tracks in field 0
# (kind 14); it is a drawable, so rect + layout follow as for drawImage.
EXTRA_DESCRIPTORS = {
    "drawScrollbar": (0xC2E03A50, ["scrollable-object-id", "direction", "image-thumb", "color-thumb",
                                   "do-show-track", "image-track", "color-track", "minimum-thumb-size"]),
}
# Donor components without a descriptor here.  Allowed only because the whole
# native descriptor area (0xC2DFF000..0xC2E04000) has no kind-14 field outside
# the components we do decode, and the residue scan below must find nothing in them.
NO_SCHEMA_OK = {"scrollEvent", "toggleVisible"}
# r10 dropped Icon08 (4465) for space but its SelectLock group (owner 4434) still
# lists it; r10 runs with that on camera.  The clones inherit the same entry
# unchanged so they stay byte-for-byte the proven row.  Fix both together.
KNOWN_DANGLING = {4465}


class BuildError(ValueError):
    pass


def check(cond, msg):
    if not cond:
        raise BuildError(msg)


def u32(d, o):
    return struct.unpack_from(">I", d, o)[0]


def put(d, o, v):
    struct.pack_into(">I", d, o, v)


class Pool:
    """Stock pool + appended private strings (provisional offsets past the stock end)."""

    def __init__(self, stock):
        self.stock = stock
        self.data = bytearray(stock)
        self.added = {}

    def text(self, off):
        if off == 0xFFFFFFFF or off >= len(self.data):
            return None
        end = self.data.find(b"\0", off)
        return self.data[off:end].decode("utf-8", "replace")

    def find(self, s):
        i = self.stock.find(b"\0" + s.encode() + b"\0")
        return i + 1 if i >= 0 else None

    def intern(self, s):
        hit = self.find(s)
        if hit is not None:
            return hit, False
        if s not in self.added:
            self.added[s] = len(self.data)
            self.data.extend(s.encode() + b"\0")
        return self.added[s], True


def typed_fields(rec, pool, schemas):
    """[(offset in record bytes incl. 8-byte header, 'obj'|'str'|'text')] for one record."""
    tag = u32(rec, 0)
    out = []
    if tag == 0x10003:
        out += [(20, "obj"), (24, "obj"), (28, "str")]
    elif tag in BM.OWNER_OFFSETS and tag != 0x1000A:
        out.append((8, "str"))
        out.append((20 if tag == 0x10006 else 16, "str"))
        out.append((BM.OWNER_OFFSETS[tag], "obj"))
        comp = pool.text(u32(rec, 8))
        if comp in schemas:
            cur, mask = BM.MASK_OFFSETS[tag], 0
            for i, p in enumerate(schemas[comp]):
                if i % 32 == 0:
                    mask, cur = u32(rec, cur), cur + 4
                if not (mask >> (i % 32)) & 1:
                    continue
                k = p["kind"]
                if k in (9, 10, 12, 13):
                    out.append((cur, "str"))
                elif k == 11:
                    out.append((cur, "text"))       # pool offset + resolver flag byte
                elif k == 14:
                    out.append((cur, "obj"))
                cur += {0: 4, 1: 4, 2: 4, 3: 4, 4: 16, 5: 16, 6: 8, 7: 12, 8: 16, 9: 4,
                        10: 4, 11: 5, 12: 4, 13: 4, 14: 4}[k]
    elif tag == 0x1000B:
        # nbu_format.decode_image_array: nA,nB,nC, group name, owner; nA x 21 B
        # {name,a,b,c,d,e}; nB x {name,value,flag[,extra]}; nC x {object id, key}; name2, tail
        na, nb, nc = u32(rec, 8), u32(rec, 12), u32(rec, 16)
        out += [(20, "str"), (24, "obj")]
        cur = 28
        for _ in range(na):
            out.append((cur, "str"))
            cur += 21
        for _ in range(nb):
            out.append((cur, "str"))
            flag = rec[cur + 8]
            cur += 13 if flag else 9
        for _ in range(nc):
            out.append((cur, "obj"))
            cur += 8
        out.append((cur, "str"))
        check(cur + 8 == len(rec), "image array layout mismatch")
    elif tag == 0x1000A:
        out += [(8, "str"), (16, "str"), (20, "obj")]
        cur = 28
        for _ in range(u32(rec, 12)):
            count, kind, _c, _name, _dim = struct.unpack_from(">5I", rec, cur)
            out.append((cur + 12, "str"))
            if kind == 2:
                out += [(cur + 20 + 10 * i + 6, "str") for i in range(count)]
            cur += 20 + count * 10
    return out


def field_starts(rec, pool, schemas):
    """Every offset where a 4-byte value field begins (any kind), for the residue check."""
    tag = u32(rec, 0)
    starts = {o for o, _k in typed_fields(rec, pool, schemas)}
    if tag in BM.OWNER_OFFSETS and tag != 0x1000A:
        comp = pool.text(u32(rec, 8))
        starts.update(range(8, BM.MASK_OFFSETS[tag], 4))
        if comp in schemas:
            cur = BM.MASK_OFFSETS[tag]
            for i, p in enumerate(schemas[comp]):
                if i % 32 == 0:
                    mask, cur = u32(rec, cur), cur + 4
                if not (mask >> (i % 32)) & 1:
                    continue
                size = {0: 4, 1: 4, 2: 4, 3: 4, 4: 16, 5: 16, 6: 8, 7: 12, 8: 16, 9: 4,
                        10: 4, 11: 5, 12: 4, 13: 4, 14: 4}[p["kind"]]
                starts.update(range(cur, cur + size - 3, 4) if p["kind"] != 11 else (cur,))
                cur += size
        else:
            starts.update(range(8, len(rec) - 3))      # unknown layout: every byte counts
    elif tag == 0x1000A:
        starts.update(range(8, 28, 4))
        cur = 28
        for _ in range(u32(rec, 12)):
            count = u32(rec, cur)
            starts.update(range(cur, cur + 20, 4))
            starts.update(cur + 20 + 10 * i + d for i in range(count) for d in (0, 2, 6))
            cur += 20 + count * 10
    else:
        starts.update(range(8, len(rec) - 3))
    return starts


def load_schemas(img):
    schemas = BM.load_property_schemas(img[:0x03200000])
    saved = dict(BM.DESCRIPTORS)
    try:
        BM.DESCRIPTORS.clear()
        BM.DESCRIPTORS.update(EXTRA_DESCRIPTORS)
        extra = BM.load_property_schemas(img[:0x03200000])
    finally:
        BM.DESCRIPTORS.clear()
        BM.DESCRIPTORS.update(saved)
    for comp, fields in extra.items():
        schemas[comp] = fields + schemas["drawImage"][-2:]      # rect, layout
    return schemas


def custom_lists(recs, pool, refs):
    """Edit, in place, the two model clips and the frame-rate ExclList range.
    Returns {record index: new bytes} and the header growth (props, keys)."""
    edits, props, keys = {}, 0, 0
    max_off = pool.find("max-value")
    check(max_off is not None, "max-value not in the stock pool")
    for spec in CUSTOM_LISTS:
        i = next(i for i, r in enumerate(recs) if r.tag == 0x1000A
                 and u32(r.to_bytes(), 20) == spec["list"] and u32(r.to_bytes(), 24) == spec["clip"])
        d = bytearray(recs[i].to_bytes())
        c = A.parse_clip(A.Record(0, bytes(d)), pool.text)
        check([(p["name"], p["kind"], p["component_ref"]) for p in c["properties"]] == [("model", 2, 1)]
              and [k["time"] for k in c["properties"][0]["keys"]] == list(spec["frames"]),
              f"model clip of {spec['list']} changed")
        check(u32(d, 12) == 1, "clip property count")
        name_off, private = pool.intern(spec["name"])
        n = u32(d, 28)
        key = struct.pack(">BBII", 0, 0, spec["frame"], name_off)
        at = 28 + 20 + 10 * n
        d[at:at] = key
        if private:
            refs.append((d, at + 6, spec["name"]))
        struct.pack_into(">I", d, 28, n + 1)
        cap = struct.pack(">5I", len(spec["frames"]) + 1, 1, 3, max_off, 0)
        for t in spec["frames"]:
            cap += struct.pack(">BBIf", 1, 0, t, spec["stock_cap"])
        cap += struct.pack(">BBIf", 1, 0, spec["frame"], spec["cap"])
        d += cap
        struct.pack_into(">I", d, 12, 2)
        struct.pack_into(">I", d, 4, len(d))
        edits[i] = d
        props += 1
        keys += 1 + len(spec["frames"]) + 1
        # the group state must reach the new frame
        gi = next(i for i, r in enumerate(recs) if r.tag == 0x1000B
                  and pool.text(u32(r.to_bytes(), 20)) == spec["group"]
                  and u32(r.to_bytes(), 24) == spec["group_owner"])
        g = bytearray(recs[gi].to_bytes())
        check(u32(g, 8) == 1 and pool.text(u32(g, 28)) == "SetList", "list group layout")
        start, end = u32(g, 32), u32(g, 36)
        if end < spec["frame"]:
            check(start == 0 and end == spec["frames"][-1], "list group range")
            struct.pack_into(">I", g, 36, spec["frame"])
            edits[gi] = g
    return edits, props, keys


def custom_switch(recs, pool, roots, new_id, refs):
    """MODE/SIZE shown only while the resolution row is CUSTOM.

    Same mechanism as the stock bit-depth / MOV-quality swap on this page:
    object 3114 ControlModeChange binds MV_RecordingFormat to a controlValue
    and each controlValueEvent plays one state of Menu's FormatChange group,
    whose per-row clip key 1 keys is-visible (B2_5_3: hidden at t=0, shown at
    t=66).  Here: a copy of 3114 bound to MV_Resolution (row 2 = CUSTOM by the
    row<->value table 0xC2E4020C (4,2)), three events (rows 0/1 -> Off,
    row 2 -> On), a copy of FormatChange listing the two clone roots, and a
    copy of B2_5_3's clip 1 on each root.  Only stock strings except the
    object/group name."""
    by_owner = lambda tag, owner: [r for r in recs if r.tag == tag and
                                   u32(r.to_bytes(), BM.OWNER_OFFSETS.get(tag, 20)) == owner]
    i_obj = next(i for i, r in enumerate(recs) if r.tag == 0x10003 and r.words(7)[3] == SWITCH_DONOR)
    comps = []
    j = i_obj + 1
    while recs[j].tag != 0x10003:
        comps.append(bytearray(recs[j].to_bytes()))
        j += 1
    names = [pool.text(u32(c, 8)) for c in comps]
    check(names == ["objectBase", "controlValue", "appVariableEvent", "controlValueEvent",
                    "controlAnimation", "controlValueEvent", "controlAnimation"],
          "ControlModeChange layout changed")
    check(pool.text(u32(comps[2], 40)) == "MV_RecordingFormat" and comps[2][44] == 0,
          "ControlModeChange variable")
    name_off, private = pool.intern(SWITCH_NAME)
    obj = bytearray(recs[i_obj].to_bytes())
    check(obj[16:20] == b"\0\0\0\0" and u32(obj, 24) == SWITCH_PARENT, "ControlModeChange object")
    put(obj, 20, new_id)
    put(obj, 28, name_off)
    out = [obj]
    if private:
        refs.append((obj, 28, SWITCH_NAME))
    for c in comps:
        put(c, BM.OWNER_OFFSETS[u32(c, 0)], new_id)
    base, value, bind, ev, anim = comps[0], comps[1], comps[2], comps[5], comps[6]
    # controlValue max-value 1.0 -> 2.0 (mask at 28 = 2: only max-value)
    check(u32(value, 28) == 2 and struct.unpack_from(">f", value, 32)[0] == 1.0, "controlValue max")
    struct.pack_into(">f", value, 32, float(CUSTOM_ROW))
    put(bind, 40, pool.find("MV_Resolution"))
    out += [base, value, bind]
    off_on, off_off = pool.find("On"), pool.find("Off")
    for k, row in enumerate(range(CUSTOM_ROW + 1)):
        e, a = bytearray(ev), bytearray(anim)
        local = 3 + 2 * k                                  # stock: events 3, 5
        state = off_on if row == CUSTOM_ROW else off_off
        check(u32(e, 28) == 5 and u32(e, 32) == 3 and u32(a, 24) == 5, "event/action link")
        put(e, 20, pool.find(str(row)))                   # event tag = row, as stock does most
                                                           # (tags are unique per object in all stock sets)
        put(e, 28, local)
        struct.pack_into(">f", e, 40, float(row))          # equal-value
        put(a, 24, local)
        check(u32(a, 36) == MENU and u32(a, 40) == pool.find("FormatChange") and
              u32(a, 45) == pool.find("MOV"), "controlAnimation fields")
        put(a, 40, name_off)
        put(a, 45, state)
        if private:
            refs.append((a, 40, SWITCH_NAME))
        out += [e, a]
    # the Menu group
    i_grp = next(i for i, r in enumerate(recs) if r.tag == 0x1000B and
                 pool.text(u32(r.to_bytes(), 20)) == "FormatChange")
    g = bytearray(recs[i_grp].to_bytes())
    check((u32(g, 8), u32(g, 12), u32(g, 16), u32(g, 24)) == (2, 0, 2, MENU), "FormatChange layout")
    check(pool.text(u32(g, 28)) == "Cinema DNG" and pool.text(u32(g, 49)) == "MOV", "FormatChange states")
    put(g, 20, name_off)
    if private:
        refs.append((g, 20, SWITCH_NAME))
    put(g, 28, off_off)                                    # t=0..   : hidden
    put(g, 49, off_on)                                     # t=66..  : shown
    cur = 28 + 2 * 21
    check([u32(g, cur + 8 * n) for n in range(2)] == [91, 4361] and
          [u32(g, cur + 4 + 8 * n) for n in range(2)] == [1, 1], "FormatChange members")
    for n, root in enumerate(roots):
        put(g, cur + 8 * n, root)
    header_groups = A.parse_header(A.Record(0, recs[0].to_bytes()), pool.text)["groups"]
    budget = header_groups[[r for r in recs if r.tag == 0x1000B].index(recs[i_grp])]
    # the clip: B2_5_3's is-visible key 1 (hidden at 0, shown at 66)
    clip = next(r for r in by_owner(0x1000A, 4361) if u32(r.to_bytes(), 24) == 1)
    c = A.parse_clip(A.Record(0, clip.to_bytes()), pool.text)
    check([(p["name"], [(k["time"], k["value"]) for k in p["keys"]]) for p in c["properties"]] ==
          [("is-visible", [(0, 0), (66, 1)])], "B2_5_3 clip changed")
    clip_after = {}
    for root in roots:
        cc = bytearray(clip.to_bytes())
        put(cc, 20, root)
        clip_after[root] = [cc]
    return dict(id=new_id, records=out + [g] + [x for v in clip_after.values() for x in v],
                after={j - 1: out, i_grp: [g]}, clip_after_root=clip_after, group_budget=list(budget))


def clone_rows(spec):
    import sl_lists
    return sl_lists.mode_rows() if spec["rows"] == "mode" else list(sl_lists.SIZE_ROWS)


def local_ids(out, ks):
    """The local ids one object's events (+28) and clips (+24) use -- one space:
    an event numbered like a clip makes a played clip find the event (camera, d6)."""
    return ({u32(out[k], 28) for k in ks if u32(out[k], 0) == 0x10006} |
            {u32(out[k], 24) for k in ks if u32(out[k], 0) == 0x1000A})


def grow_rows(out, mapping, pool, refs, rows, new_id, static_cap=None):
    """Fit one clone (records `out`, ids `mapping`) to `rows`.  Returns the
    added records (for the allocation header) and the next free object id."""
    n = len(rows)
    lst, item, sel, ichg, itext = (mapping[k] for k in (4439, LIST_ITEM, SELECT, ICON_CHANGE, ICON_TEXT))
    owner, by_owner, objs = None, {}, {}
    for k, rec in enumerate(out):
        if u32(rec, 0) == 0x10003:
            owner = u32(rec, 20)
            objs[owner] = k
        by_owner.setdefault(owner, []).append(k)

    def ctrl(obj, prop, at, old, new):
        hits = [k for k in by_owner[obj] if u32(out[k], 0) == 0x1000E and u32(out[k], 28) == prop]
        check(len(hits) == 1, f"controller {prop:#x} of {obj}")
        rec = out[hits[0]]
        got = struct.unpack_from(">f", rec, at)[0]
        check(got in old, f"controller {prop:#x} of {obj} is {got}, not one of {old}")
        struct.pack_into(">f", rec, at, float(new))

    # The List cap is 8.0 (stock) on a card: WITH_SL_EXCL turns WITH_RATE_ROW off,
    # so the plan does not write 9.0 into B2_5 (the private SL_RATE gets its cap
    # from the model clip instead).  9.0 without it.  Either way: rows - 1.
    ctrl(lst, 0xA, 32, (DONOR_ROWS - 2, DONOR_ROWS - 1), n - 1 if static_cap is None else static_cap)
    ctrl(item, 3, 36, (DONOR_ROWS,), max(DONOR_ROWS, n))
    ctrl(sel, 0x12, 32, (DONOR_ROWS - 1,), max(DONOR_ROWS, n) - 1)
    ctrl(ichg, 0x12, 32, (DONOR_ROWS - 1,), max(DONOR_ROWS, n) - 1)

    added, inserts = [], {}
    # ---- cursor pairs v = 10 .. n-1 (rule 8) ----
    ev_name, fo_name = pool.find("controlValueEvent"), pool.find("controlFocus")
    events = {struct.unpack_from(">f", out[k], 40)[0]: k for k in by_owner[lst]
              if u32(out[k], 0) == 0x10006 and u32(out[k], 8) == ev_name and u32(out[k], 32) == 3}
    focus = {u32(out[k], 24): k for k in by_owner[lst]
             if u32(out[k], 0) == 0x10009 and u32(out[k], 8) == fo_name and u32(out[k], 40) == lst}
    check(sorted(events) == [float(v) for v in range(1, DONOR_ROWS)], "List cursor events changed")
    last_ev, last_fo = out[events[9.0]], out[focus[u32(out[events[9.0]], 28)]]
    tmpl_fo = out[focus[u32(out[events[8.0]], 28)]]          # v=9's focus carries a zero tail
    check(pool.text(u32(last_ev, 20)) == "10" and pool.text(u32(last_fo, 44)) == "9", "v=9 pair names")
    key = max(local_ids(out, by_owner[lst])) + 1          # events and clips share them
    pair = []
    for v in range(DONOR_ROWS, n):
        e, f = bytearray(last_ev), bytearray(tmpl_fo)
        # event tag "v+1" and focused instance "v": stock pool when it has them
        # (it lacks 53, 54, 63, 65, 66, 68, 69, 71), else private strings
        label, p1 = pool.intern(str(v + 1))
        name, p2 = pool.intern(str(v))
        put(e, 20, label); put(e, 28, key)
        struct.pack_into(">f", e, 40, float(v))
        put(f, 24, key); put(f, 44, name)
        if p1:
            refs.append((e, 20, str(v + 1)))
        if p2:
            refs.append((f, 44, str(v)))
        check(u32(f, 40) == lst, "focus target")
        pair += [e, f]
        key += 1
    if pair:
        inserts[focus[u32(last_ev, 28)]] = pair
        put(out[objs[lst]], 8, u32(out[objs[lst]], 8) + len(pair) // 2)
        added += pair
    # ---- summary: one literal IconText per row ----
    text_name = pool.find("drawText")
    children = [o for o, k in objs.items() if u32(out[k], 24) == itext]
    check(len(children) == DONOR_ROWS, "summary children changed")

    def draw_text(obj):
        hits = [k for k in by_owner[obj] if u32(out[k], 0) == 0x10005 and u32(out[k], 8) == text_name]
        check(len(hits) == 1, f"drawText of {obj}")
        return out[hits[0]]

    def literal(rec, s):
        off, private = pool.intern(s)
        put(rec, 32, off)
        rec[36] = 0
        if private:
            refs.append((rec, 32, s))

    for obj, row in zip(children, rows):
        literal(draw_text(obj), row["summary"])
    last = children[-1]
    tail = by_owner[last]
    check([u32(out[k], 0) for k in tail] == [0x10003, 0x10004, 0x10005, 0x1000A], "IconText10 shape")
    copies = []
    for v in range(DONOR_ROWS, n):
        recs = [bytearray(out[k]) for k in tail]
        put(recs[0], 20, new_id)
        # keep the donor's stock name (IconText10): names need not be unique (165 of
        # 220 stock sets have same-name siblings), and each private name costs the
        # installer a whole-pool search plus two cache flushes -- r13 on camera:
        # 59 of them stretched the boot by ~20 s at the third box.
        for r in recs[1:]:
            put(r, BM.OWNER_OFFSETS[u32(r, 0)], new_id)
        literal(recs[2], rows[v]["summary"])
        copies += recs
        new_id += 1
    if copies:
        inserts[tail[-1]] = copies
        put(out[objs[itext]], 16, len(children) + len(copies) // 4)
        added += copies
    grown = []
    for k, rec in enumerate(out):
        grown.append(rec)
        grown.extend(inserts.get(k, []))
    out[:] = grown
    return added, new_id


SET_LIMIT_SET, SET_LIMIT_ID = "B1_1", 7895     # stock: shutter-speed list count -> List cap
SET_LIMIT_VAR = "SL_ModeCount"


def set_limit(img, pool, refs, new_id, parent, target):
    """A copy of B1_1's SetLimit (object 7895, under MenuItem_ChangeListSelect):
    a controlValue bound to an app variable (appVariableEvent ... "value"),
    and on screen show (screenEvent) and on change (appVariableChangeEvent) a
    changePropertyByControl writing the target List's controlValue max-value
    as "value - 1".  Stock binds CM_ShutterSpeedItem, which the firmware sets
    to the list's item count, and targets two Lists; this binds the private
    SL_ModeCount (sl_menu/sl_modes.c sets it) and targets one."""
    sets = {r["name"]: r for r in N.load_sets()[2]}
    base = sets[SET_LIMIT_SET]["address"]
    recs = N.split(img[base - B:])
    i = next(k for k, r in enumerate(recs) if r.tag == 0x10003 and r.words(7)[3] == SET_LIMIT_ID)
    j = i + 1
    while recs[j].tag != 0x10003:
        j += 1
    src = [bytearray(r.to_bytes()) for r in recs[i:j]]
    names = [pool.text(u32(d, 8)) for d in src[1:]]
    check(pool.text(u32(src[0], 28)) == "SetLimit" and u32(src[0], 8) == 5 and u32(src[0], 16) == 0 and
          names == ["objectBase", "controlValue", "appVariableEvent", "screenEvent",
                    "changePropertyByControl", "changePropertyByControl", "appVariableChangeEvent",
                    "changePropertyByControl", "changePropertyByControl"], "B1_1 SetLimit changed")
    bind = src[3]
    check(pool.text(u32(bind, 40)) == "CM_ShutterSpeedItem" and pool.text(u32(bind, 45)) == "value",
          "SetLimit binding")
    for ev in (src[4], src[7]):
        check(u32(ev, 16) == 2, "SetLimit event action count")
        put(ev, 16, 1)                                    # one target
    for a in (src[5], src[8]):
        check([pool.text(u32(a, o)) for o in (40, 45, 50)] == ["controlValue", "max-value", "value - 1"],
              "SetLimit action")                          # byte-packed: a flag byte at 44 / 49
        put(a, 36, target)
    out = [src[0], src[1], src[2], src[3], src[4], src[5], src[7], src[8]]
    put(out[0], 20, new_id)
    put(out[0], 24, parent)
    for r in out[1:]:
        put(r, BM.OWNER_OFFSETS[u32(r, 0)], new_id)
    change = src[7]
    check(pool.text(u32(change, 36)) == "CM_ShutterSpeedItem", "SetLimit change binding")
    off, private = pool.intern(SET_LIMIT_VAR)
    for rec, at in ((bind, 40), (change, 36)):            # both bindings, or the change event
        put(rec, at, off)                                 # would follow the shutter speed
        if private:
            refs.append((rec, at, SET_LIMIT_VAR))
    return out

POPUP_PARTS = (4439, 4436)                     # the row's List and Scrolbar_onoff


def align_popup(out, mapping, row_y):
    """The popup is drawn from the List's objectBase y, relative to its row; stock's
    frame-rate row (y 243) carries -243, i.e. the popup starts at the Menu's top.
    A copy at another y must carry -y, or its popup leaves the screen (camera r18:
    the SIZE page's popups ran off the top)."""
    for part in POPUP_PARTS:
        rec = next(r for r in out if u32(r, 0) == 0x10004 and u32(r, 20) == mapping[part])
        pos = bytes(rec).find(struct.pack(">f", -243.0))
        check(pos > 0, f"popup offset of {part} not found")
        struct.pack_into(">f", rec, pos, -float(row_y))


SIZE_JUMP_TO = "SL_SIZE_PG"                    # sl_size_page.py (stage 1 was SL_TEST)
HELP_ROW, HELP_KEY = 4247, 0xF                  # this page's Right_Help -> sync-request 'SetupHelpMenu'


def size_jump(out, recs, mapping, pool, refs):
    """SIZE's Right key: instead of opening its popup (controlAppVariable +
    controlFocus), one controlAppState sync-request "<page>" -- a copy of this
    page's own Right_Help action (row 4247), so no record comes from another
    page.  OK still opens the popup.  Returns (removed, added) records."""
    sel = mapping[SELECT]
    right = pool.find("Right")
    i = next(k for k, r in enumerate(out) if u32(r, 0) == 0x10006 and u32(r, 24) == sel
             and pool.text(u32(r, 8)) == "keyEvent" and u32(r, 20) == right)
    ev = out[i]
    key = u32(ev, 28)
    check(u32(ev, 16) == 2, "SIZE Right key no longer has two actions")
    old = out[i + 1:i + 3]
    check([pool.text(u32(a, 8)) for a in old] == ["controlAppVariable", "controlFocus"] and
          all(u32(a, 20) == sel and u32(a, 24) == key for a in old), "SIZE Right key actions changed")
    owner, tmpl = None, None
    for r in recs:
        d = r.to_bytes()
        if r.tag == 0x10003:
            owner = r.words(7)[3]
        elif owner == HELP_ROW and r.tag == 0x10009 and u32(d, 24) == HELP_KEY:
            tmpl = bytearray(d)
    check(tmpl is not None and len(tmpl) == 41 and pool.text(u32(tmpl, 8)) == "controlAppState" and
          pool.text(u32(tmpl, 36)) == "SetupHelpMenu", "Right_Help template changed")
    act = bytearray(tmpl)
    put(act, 20, sel)
    put(act, 24, key)
    put(act, 28, 1)
    off, private = pool.intern(SIZE_JUMP_TO)
    put(act, 36, off)
    if private:
        refs.append((act, 36, SIZE_JUMP_TO))
    put(ev, 16, 1)
    out[i + 1:i + 3] = [act]
    gone = {id(a) for a in old}
    refs[:] = [r for r in refs if id(r[0]) not in gone]      # their private strings go with them
    return old, [act]

# Resolution = CUSTOM: "› more options" and Right -> the private page.
#   - the popup List's value events: CUSTOM -> Footer02 (more options), else Footer05;
#   - the popup's Right writes the focused item's own value (row + 1; stock's Check00
#     uses "value - 1" as the row) into a hidden JumpEvent's controlValue;
#   - JumpEvent: value-change + value-equal (CUSTOM_ROW + 1) -> sync-request "<page>".
# Every primitive here already runs on this page: value-change/equal events driven
# by changePropertyByControl (the List's own Up/Down), a sync-request from B2_5
# (r17/r18 SIZE row).  Stock's audio-record JumpEvent (MainB2 32736: a group plays
# is-visible 0 -> 1, "on-visible" events jump) did nothing here: r20, r21, and
# d1 (on-visible only, no value test) all stayed on B2_5 (2026-10-03, camera).
RES_SELECT, RES_LIST, RES_ITEM = 4254, 4259, 4260
FOOTER_EVENT, SPARE_EVENT = 0xE, 0xF            # List 4259: value <= 1 -> Footer05; an empty event
FOOTER_MORE = "Footer02"
JUMP_TYPE = 0x12                               # value-change + value-equal (the List's own events)
import os as _os
JUMP_DIAG = _os.environ.get("SL_JUMP_DIAG", "")  # "direct": diagnostic card only


def _object_records(recs, oid):
    i0 = next(i for i, r in enumerate(recs) if r.tag == 0x10003 and r.words(7)[3] == oid)
    i1 = i0 + 1
    while recs[i1].tag != 0x10003:
        i1 += 1
    return [bytearray(r.to_bytes()) for r in recs[i0:i1]]


def lab_jump(recs, pool, refs, new_id, target):
    """Records to edit / insert in the B2_5 page.  Returns dict(edits={i: bytes},
    after={i: [records]}, added=[...], removed=[...], objects)."""
    def name(d):
        return pool.text(u32(d, 8))

    data = [bytearray(r.to_bytes()) for r in recs]
    # -- JumpEvent: a copy of this page's ControlModeChange (3114, under Root; the
    #    r15 CUSTOM switch is one too and runs): objectBase + controlValue, then one
    #    of its own value events with this page's Right_Help sync-request as action.
    #    Not MainB2's JumpEvent: copied across pages it never fired (r20..d3).
    src = _object_records(recs, SWITCH_DONOR)
    check([name(d) if u32(d, 0) != 0x10003 else "obj" for d in src] ==
          ["obj", "objectBase", "controlValue", "appVariableEvent", "controlValueEvent", "controlAnimation",
           "controlValueEvent", "controlAnimation"], "ControlModeChange layout changed")
    obj, base, ctl, ev = src[0], src[1], src[2], src[6]
    check(u32(obj, 24) == SWITCH_PARENT and (u32(ctl, 28), struct.unpack_from(">f", ctl, 32)[0]) == (2, 1.0) and
          (u32(ev, 16), u32(ev, 32), u32(ev, 36), struct.unpack_from(">f", ev, 40)[0]) == (1, 3, 0x12, 1.0),
          "ControlModeChange records changed")
    st = None
    owner_ = None
    for r in recs:
        d = r.to_bytes()
        if r.tag == 0x10003:
            owner_ = r.words(7)[3]
        elif owner_ == HELP_ROW and r.tag == 0x10009 and u32(d, 24) == HELP_KEY:
            st = bytearray(d)
    check(st is not None and len(st) == 41 and pool.text(u32(st, 36)) == "SetupHelpMenu", "Right_Help changed")
    put(obj, 8, 3)                                  # objectBase, controlValue, one event
    put(obj, 20, new_id)
    name_off, private_name = pool.intern("SL_JumpEvent")
    put(obj, 28, name_off)
    if private_name:
        refs.append((obj, 28, "SL_JumpEvent"))
    for d in (base, ctl, ev):
        put(d, BM.OWNER_OFFSETS[u32(d, 0)], new_id)
    rows = 8.0                                      # the ListItem's own max (one per row)
    struct.pack_into(">f", ctl, 32, rows)
    put(ev, 36, JUMP_TYPE)
    struct.pack_into(">f", ev, 40, float(CUSTOM_ROW + 1))
    put(st, 20, new_id)
    put(st, 24, u32(ev, 28))
    put(st, 28, 1)
    off, private = pool.intern(target)
    put(st, 36, off)
    if private:
        refs.append((st, 36, target))
    jump = [obj, base, ctl, ev, st]

    # -- B2_5's own records
    owner, at = None, {}
    for i, d in enumerate(data):
        if u32(d, 0) == 0x10003:
            owner = u32(d, 20)
            at.setdefault(("obj", owner), i)
        elif u32(d, 0) == 0x10006 and owner in (RES_LIST, RES_ITEM):
            at[(owner, name(d), pool.text(u32(d, 20)) if name(d) == "keyEvent" else u32(d, 28))] = i
        elif u32(d, 0) == 0x1000E and owner == RES_ITEM:
            check(u32(d, 28) == 3 and struct.unpack_from(">ff", d, 32) == (1.0, rows),
                  "ListItem value range changed")
    edits, after, added, removed = {}, {}, [], []
    # the footer: the spare event -> value == CUSTOM -> Footer02 (the <= 1 event keeps Footer05)
    i = at[(RES_LIST, "controlValueEvent", FOOTER_EVENT)]
    footer_anim = data[i + 1]
    check((u32(data[i], 32), u32(data[i], 36), u32(data[i], 16)) == (0x21, 0x83, 1) and
          pool.text(u32(footer_anim, 45)) == "Footer05", "List footer event changed")
    i = at[(RES_LIST, "controlValueEvent", SPARE_EVENT)]
    spare, spare_anim = data[i], data[i + 1]
    check(len(spare) == 40 and (u32(spare, 16), u32(spare, 32), u32(spare, 36)) == (1, 1, 0) and
          name(spare_anim) == "controlAnimation" and len(spare_anim) == 36 and u32(spare_anim, 32) == 0,
          "List spare event changed")
    ev2 = bytearray(spare[:32]) + struct.pack(">IIf", 3, 0x13, float(CUSTOM_ROW))   # + on-visible
    put(ev2, 4, len(ev2))
    an2 = bytearray(footer_anim)
    put(an2, 24, SPARE_EVENT)
    more = pool.find(FOOTER_MORE)
    check(more is not None, "Footer02 not in the pool")
    put(an2, 45, more)
    edits[i], edits[i + 1] = ev2, an2
    removed += [spare, spare_anim]
    added += [ev2, an2]
    # the popup's Right: write -> JumpEvent value <- own value -> focus the row.
    # Action word +28 may be the run order (B2_5's Up lists focus 3 before change 2);
    # 6 sits between the write (5) and the focus (7) under either reading.
    i = at[(RES_ITEM, "keyEvent", "Right")]
    acts = list(range(i + 1, i + 1 + u32(data[i], 16)))
    check([name(data[k]) for k in acts] == ["controlAppVariable", "controlFocus"] and
          [u32(data[k], 28) for k in acts] == [5, 7], "popup Right changed")
    tmpl = None
    k = at[(RES_ITEM, "keyEvent", "Up")]
    for d in data[k + 1:k + 1 + u32(data[k], 16)]:
        if name(d) == "changePropertyByControl" and pool.text(u32(d, 50)) == "dst - 1":
            tmpl = d                                # this page's popup Up: List value <- "dst - 1"
    check(tmpl is not None and len(tmpl) == 55 and u32(tmpl, 32) == 0x1B, "popup Up action changed")
    copy = bytearray(tmpl)
    put(copy, 20, RES_ITEM)
    put(copy, 24, u32(data[i], 28))
    put(copy, 28, 6)
    put(copy, 36, new_id)
    put(copy, 50, pool.find(str(CUSTOM_ROW + 1)) if JUMP_DIAG == "const3" else pool.find("value"))
    key = data[i]
    put(key, 16, len(acts) + 1)
    edits[i] = key
    after.setdefault(acts[0], []).append(copy)
    added.append(copy)
    if JUMP_DIAG == "direct":
        # diagnostic: an unconditional sync-request from the popup's Right (this
        # page's own Right_Help action, as size_jump copies it), every row jumps
        owner_, tmpl2 = None, None
        for r in recs:
            d = r.to_bytes()
            if r.tag == 0x10003:
                owner_ = r.words(7)[3]
            elif owner_ == HELP_ROW and r.tag == 0x10009 and u32(d, 24) == HELP_KEY:
                tmpl2 = bytearray(d)
        act = bytearray(tmpl2)
        put(act, 20, RES_ITEM)
        put(act, 24, u32(data[i], 28))
        put(act, 28, 8)
        put(act, 36, off)
        if private:
            refs.append((act, 36, target))
        put(key, 16, len(acts) + 2)
        after[acts[-1]] = after.get(acts[-1], []) + [act]
        added.append(act)
    # JumpEvent right after ControlModeChange, under Root
    k = at[("obj", SWITCH_DONOR)] + len(src) - 1
    after.setdefault(k, []).extend(jump)
    added += jump
    root = data[at[("obj", SWITCH_PARENT)]]
    put(root, 16, u32(root, 16) + 1)
    edits[at[("obj", SWITCH_PARENT)]] = root
    return dict(id=new_id, edits=edits, after=after, added=added, removed=removed, objects=1)


def plan_words_in_set():
    """Every word the Sensor Lab plan writes inside the stock B2_5 set: (address, value, what).

    The private page replaces the set, so it has to carry all of them, not only
    imx410_rate_ui's rebuild: the first on-camera run (2026-10-02) left out the
    three list maxima (resolution 2.0 = CUSTOM, frame rate 9.0 = 239.76,
    bit depth 3.0 = 14-bit) and the cursor could not reach those rows."""
    import os
    import imx410_plan as PL
    before = os.getcwd()
    os.chdir(HERE)
    try:
        items = PL.plan()
    finally:
        os.chdir(before)
    return [(a, v, n) for a, v, n in items if U.SET_START <= a < U.SET_END]


def base_page(img):
    """The B2_5 set exactly as the Sensor Lab card leaves it in memory."""
    page = bytearray(U.rebuild(img))
    for a, v, _ in plan_words_in_set():
        o = a - U.SET_START
        b = struct.pack("<I", v)
        keep = max(0, min(4, len(page) - o))
        check(not any(b[keep:]), f"plan word {a:#x} spills nonzero bytes past the set")
        page[o:o + keep] = b[:keep]                  # the summary's zero tail straddles the end
    return bytes(page[:len(page) - (3 if U.WITH_SUMMARY else 0)])


def build(img=None):
    img = img if img is not None else (ROOT / "out/MAIN_c0000000.bin").read_bytes()
    stock_pool = img[U.POOL_START - B:U.POOL_START - B + U.POOL_SIZE]
    pool = Pool(stock_pool)
    schemas = load_schemas(img)
    page_r10 = base_page(img)
    recs = N.split(page_r10)
    objs = {}
    for i, r in enumerate(recs):
        if r.tag == 0x10003:
            w = r.words(7)
            objs[w[3]] = dict(parent=w[4], idx=i, n=w[2], name=pool.text(w[5]))
    check(objs[ROW]["parent"] == MENU and objs[MENU]["n"] == 6, "B2_5 layout changed")
    sub = {ROW}
    grew = True
    while grew:
        grew = False
        for k, v in objs.items():
            if v["parent"] in sub and k not in sub:
                sub.add(k)
                grew = True
    start = objs[ROW]["idx"]
    end = start + 1
    while end < len(recs) and not (recs[end].tag == 0x10003 and recs[end].words(7)[3] not in sub):
        end += 1
    donor = recs[start:end]
    for r in donor:
        d = r.to_bytes()
        if r.tag in BM.OWNER_OFFSETS and r.tag != 0x1000A:
            comp = pool.text(u32(d, 8))
            check(comp in schemas or comp in NO_SCHEMA_OK, f"no descriptor for donor component {comp}")
    check(len([r for r in donor if r.tag == 0x10003]) == len(sub), "row subtree is not contiguous")

    used = set(objs)
    next_id = max(used) + 1
    refs, clones, report, list_remaps, grown, removed = [], [], [], [], [], []
    for spec in (CLONES if WITH_CLONES else ()):
        mapping = {old: next_id + i for i, old in enumerate(sorted(sub))}
        next_id += len(sub)
        check(max(mapping.values()) < 0x10000, "ID space exhausted")
        rename = {}
        for old, new in spec["rename"].items():
            off_old = pool.find(old)
            if off_old is None:
                continue
            rename[off_old] = new
        title_off = pool.find(TITLE_ID)
        out = []
        for r in donor:
            rec = bytearray(r.to_bytes())
            for off, kind in typed_fields(bytes(rec), pool, schemas):
                v = u32(rec, off)
                if kind == "obj" and v in mapping:
                    put(rec, off, mapping[v])
                elif (kind in ("str", "text") and v in rename and
                      not (not WITH_PRIVATE_LISTS and u32(rec, 0) == 0x1000A)):
                    new_off, private = pool.intern(rename[v])
                    put(rec, off, new_off)
                    if private:
                        refs.append((rec, off, rename[v]))
                elif kind == "text" and v == title_off and u32(rec, 20) == mapping[TITLE_OWNER]:
                    new_off, private = pool.intern(spec["title"])
                    put(rec, off, new_off)
                    rec[off + 4] = 0                     # literal, not an .nloc ID
                    if private:
                        refs.append((rec, off, spec["title"]))
            if u32(rec, 0) == 0x10008:
                # 'list' template record: byte-packed, member object IDs at
                # unaligned offsets (no published layout).  Remap exact matches of
                # subtree IDs and keep the list for the manifest.
                for o in range(8, len(rec) - 3):
                    v = u32(rec, o)
                    if v in mapping and v > 64:
                        put(rec, o, mapping[v])
                        list_remaps.append((spec["key"], o, v))
            out.append(rec)
        # the row container's position (objectBase of the clone root)
        root_new = mapping[ROW]
        for rec in out:
            if u32(rec, 0) == 0x10004 and u32(rec, 20) == root_new:
                f = A.Record(0, bytes(rec))
                d = bytes(rec)
                pos = d.find(struct.pack(">f", 243.0))
                check(pos > 0, "row position field not found")
                struct.pack_into(">f", rec, pos, spec["y"])
        align_popup(out, mapping, spec["y"])
        # residual scan: any old subtree ID left at any byte offset is reported
        # A hit only counts where a value field starts; straddling hits (e.g. a
        # 0x12 key value followed by a count of 2 reads as 0x1200 = object 4608)
        # are listed separately so the count stays visible.
        residue, straddle = [], 0
        for i, rec in enumerate(out):
            starts = field_starts(bytes(rec), pool, schemas)
            for o in range(8, len(rec) - 3):
                v = u32(rec, o)
                if v in sub and v > 64:
                    if o in starts:
                        residue.append((i, u32(rec, 0), o, v))
                    else:
                        straddle += 1
        report.append(dict(key=spec["key"], root=mapping[ROW], ids=[min(mapping.values()), max(mapping.values())],
                           residue=residue, straddle=straddle))
        clones.append(out)
        if WITH_ROWS and WITH_PRIVATE_LISTS:
            rows = clone_rows(spec)
            first = next_id
            dynamic = spec["rows"] == "mode"
            # MODE's rows are written on the camera: the cap comes from SetLimit
            # (SL_ModeCount - 1) when the screen shows; 0 until then.
            add, next_id = grow_rows(out, mapping, pool, refs, rows, next_id,
                                     static_cap=0 if dynamic else None)
            grown += add
            if dynamic:
                lim = set_limit(img, pool, refs, next_id, mapping[SELECT], mapping[4439])
                sel = next(r for r in out if u32(r, 0) == 0x10003 and u32(r, 20) == mapping[SELECT])
                put(sel, 16, u32(sel, 16) + 1)
                out.extend(lim)
                grown += lim
                next_id += 1
            if spec["rows"] == "size" and WITH_SIZE_JUMP:
                gone, new = size_jump(out, recs, mapping, pool, refs)
                removed += gone
                grown += new
            report[-1].update(rows=len(rows), extra_ids=list(range(first, next_id)))

    # the CUSTOM switch: one object, one Menu group, one clip per clone root
    sw = dict(id=None, records=[], after={}, clip_after_root={}, group_budget=None)
    if WITH_CLONES:
        sw = custom_switch(recs, pool, [r["root"] for r in report], next_id + 0, refs)
        next_id += 1
    jump = dict(id=None, edits={}, after={}, added=[], removed=[], objects=0)
    if WITH_LAB_JUMP:
        jump = lab_jump(recs, pool, refs, next_id, SIZE_JUMP_TO)
        next_id += 1
    lists = custom_lists(recs, pool, refs) if WITH_CUSTOM_LISTS else ({}, 0, 0)

    # assemble: header extended, Menu 6 -> 8, Root +1, clones right after the donor subtree
    header = A.parse_header(A.Record(0, recs[0].to_bytes()), pool.text)
    counts = A.component_counts([A.Record(0, r.to_bytes()) for r in donor], pool.text)
    all_groups = [r for r in recs if r.tag == 0x1000B]
    gidx = [all_groups.index(r) for r in donor if r.tag == 0x1000B]
    donor_clips = [A.parse_clip(A.Record(0, r.to_bytes()), pool.text) for r in donor if r.tag == 0x1000A]
    added = [A.Record(0, bytes(x)) for x in sw["records"] + grown + jump["added"]]
    sw_counts = A.component_counts(added, pool.text)
    for k, v in A.component_counts([A.Record(0, bytes(x)) for x in removed + jump["removed"]],
                                   pool.text).items():
        sw_counts[k] = sw_counts.get(k, 0) - v
    sw_clips = [A.parse_clip(x, pool.text) for x in added if x.tag == 0x1000A]
    copies = len(clones)
    delta = {"objects": copies * len(sub) + (1 if WITH_CLONES else 0) + jump["objects"]
                        + sum(1 for x in grown if u32(x, 0) == 0x10003),
             "component_counts": {k: copies * counts.get(k, 0) + sw_counts.get(k, 0)
                                  for k in set(counts) | set(sw_counts)},
             "group_budgets": [header["groups"][i] for i in gidx] * copies
                              + [b for b in (sw["group_budget"],) if b],
             "clip_property_counts": [len(c["properties"]) for c in donor_clips] * copies
                                     + [len(c["properties"]) for c in sw_clips],
             "property_key_counts": [len(p["keys"]) for c in donor_clips for p in c["properties"]] * copies
                                    + [len(p["keys"]) for c in sw_clips for p in c["properties"]]}
    # the list clips grew in place: only the totals matter (C05E6400 sums them)
    header = dict(header, clip_property_counts=header["clip_property_counts"][:-1]
                  + [header["clip_property_counts"][-1] + lists[1]],
                  property_key_counts=header["property_key_counts"][:-1]
                  + [header["property_key_counts"][-1] + lists[2]])
    new_header = BM.extend_header(A.Record(0, recs[0].to_bytes()), header, delta)
    seq = []
    for i, r in enumerate(recs):
        data = bytearray(new_header if i == 0 else lists[0].get(i, r.to_bytes()))
        if i in lists[0]:
            data = lists[0][i]                    # same object the refs point at
        if i in jump["edits"]:
            check(i not in lists[0], "two edits of one record")
            data = jump["edits"][i]
        if r.tag == 0x10003 and r.words(7)[3] == MENU:
            put(data, 16, 6 + copies)
        if r.tag == 0x10003 and r.words(7)[3] == SWITCH_PARENT and WITH_CLONES:
            put(data, 16, u32(data, 16) + 1)          # on top of lab_jump's own +1
        seq.append(data)
        seq.extend(sw["after"].get(i, []))
        seq.extend(jump["after"].get(i, []))
        if i == end - 1:
            for out in clones:
                for k, x in enumerate(out):
                    seq.append(x)
                    if k == 1:                       # after the clone root's objectBase
                        seq.extend(sw["clip_after_root"].get(u32(out[0], 20), []))
    at, where = 0, {}
    for x in seq:
        where[id(x)] = at
        at += len(x)
    page = b"".join(bytes(x) for x in seq)
    check(len(page) == at, "assembly")
    # private-string fields as absolute page offsets, checked against the page:
    # each listed word holds that string's provisional offset, no other word does
    abs_refs = sorted({(where[id(rec)] + off, text) for rec, off, text in refs})
    for a, text in abs_refs:
        check(u32(page, a) == pool.added[text], f"ref at {a:#x} is not {text!r}")
    private, listed = set(pool.added.values()), {a for a, _ in abs_refs}
    stray = [a for a in range(len(page) - 3) if u32(page, a) in private and a not in listed]
    check(not stray, f"unlisted words equal to private offsets at {stray[:5]}")
    return dict(page=page, pool=pool, refs=refs, abs_refs=abs_refs, switch_id=sw["id"], jump_id=jump["id"],
                report=report, list_remaps=list_remaps, donor_records=len(donor),
                donor_bytes=sum(r.size for r in donor), sub=sorted(sub), base_len=len(page_r10))


def page_shape(page: bytes, pool) -> dict:
    """Header-vs-actual invariants and the object graph of one page."""
    recs = [A.Record(x.offset, x.to_bytes()) for x in N.split(page)]
    h = A.parse_header(recs[0], pool.text)
    objs = A.parse_objects(recs, pool.text)
    kids = {}
    for o in objs.values():
        kids[o["parent_id"]] = kids.get(o["parent_id"], 0) + 1
    actual = A.component_counts(recs, pool.text)
    # C05E6400 reduces these vectors to one arena byte total (no per-record
    # cursor; groups/keys are built from their own record's counts), so only
    # totals are compared -- MAINB2_ROW_EXTENSION.md "Allocation vector order".
    groups = [r for r in recs if r.tag == 0x1000B]
    clips = [A.parse_clip(r, pool.text) for r in recs if r.tag == 0x1000A]
    return dict(
        header_minus_actual=dict(
            objects=h["objects"] - len(objs),
            groups=len(h["groups"]) - len(groups),
            group_slots=[sum(g[i] for g in h["groups"]) - sum(r.word(8 + 4 * i) for r in groups)
                         for i in range(3)],
            clips=len(h["clip_property_counts"]) - len(clips),
            clip_properties=sum(h["clip_property_counts"]) - sum(len(c["properties"]) for c in clips),
            keys=sum(h["property_key_counts"]) - sum(len(p["keys"]) for c in clips
                                                     for p in c["properties"]),
            components={k: h["component_counts"].get(k, 0) - actual.get(k, 0)
                        for k in set(h["component_counts"]) | set(actual)}),
        orphans=sorted(i for i, o in objs.items() if o["parent_id"] and o["parent_id"] not in objs),
        bad_child_counts=sorted(i for i, o in objs.items() if o["child_count"] != kids.get(i, 0)),
        objects=objs)


def audit(res, img: bytes | None = None) -> dict:
    """Offline structure checks of a build() result against the r10 base page."""
    img = img if img is not None else (ROOT / "out/MAIN_c0000000.bin").read_bytes()
    pool, page = res["pool"], res["page"]
    base = U.rebuild(img)
    base = base[:len(base) - (3 if U.WITH_SUMMARY else 0)]
    old, new = page_shape(base, pool), page_shape(page, pool)
    hn, ho = dict(new["header_minus_actual"]), dict(old["header_minus_actual"])
    # clones copy the donor groups' budgets including their reserve, so slot
    # slack may grow, never shrink
    check(all(n >= o for n, o in zip(hn.pop("group_slots"), ho.pop("group_slots"))),
          "group slot budget below the page's needs")
    check(hn == ho, "allocation header no longer matches the page the way stock does")
    check(not new["orphans"] and not new["bad_child_counts"], "object graph broken")
    objs = new["objects"]
    for spec, r in zip(CLONES, res["report"]):
        root = objs[r["root"]]
        check(root["parent_id"] == MENU and root["name"] == spec["rename"][objs[ROW]["name"]],
              "clone root misplaced")
    check(objs[MENU]["child_count"] == 6 + len(res["report"]), "Menu child count")
    # every object-typed field in the page names an existing object
    schemas = load_schemas(img)
    for r in N.split(page):
        d = r.to_bytes()
        for off, kind in typed_fields(d, pool, schemas):
            v = u32(d, off)
            if kind == "obj" and v not in (0, 0xFFFFFFFF) and v not in KNOWN_DANGLING:
                check(v in objs, f"dangling object reference {v} in tag {r.tag:#x}")
    return dict(objects=len(objs), header_minus_actual=new["header_minus_actual"])


def native_parse(page: bytes, pool: bytes, img: bytes | None = None):
    """Run the original NBU interpreter (FUN_c05e6400) over the private page with the
    extended pool, record by record, under the same fixed construction allow-list
    imx410_rate_ui uses for the stock B2_5.  Returns the probe."""
    import nbu_probe as P
    img = img if img is not None else (ROOT / "out/MAIN_c0000000.bin").read_bytes()
    # Sidebar pages have more native objects than a stock single-panel page.
    # Reserve disjoint, measured source/pool/heap regions inside synthetic RAM.
    blob_max = max(P.NbuProbe.BLOB_MAX, (len(page)+0xFFFF)&~0xFFFF)
    heap = max(P.NbuProbe.HEAP, (P.NbuProbe.BLOB+blob_max+len(pool)+0xFFFF)&~0xFFFF)
    check(heap < P.NbuProbe.HEAP_END, "page and pool leave no probe heap")
    class PageProbe(P.NbuProbe):
        BLOB_MAX = blob_max
        HEAP = heap
    probe = PageProbe(img[:P.SEG0_SIZE])
    pool_at = probe.BLOB + probe.BLOB_MAX
    check(pool_at + len(pool) <= probe.HEAP, "pool does not fit below the probe heap")
    probe.install_arena()
    probe.allow(*probe.OBJECT_FACTORY, "stock object factory")
    for address in U._native_stock_services():
        probe.stub(address, "stock UI construction service")
    probe.write(pool_at, bytes(pool))
    probe.open(blob=page, magic=False, cursor=0, pool=(len(pool), pool_at), owner=True)
    for record in N.split(page):
        trace = probe.record()
        check((trace.token, trace.cursor_in, trace.consumed) == (record.tag, record.offset, record.size)
              and not probe.error_flag(), f"native parser disagrees at record {trace.index}")
    check(probe.traces[-1].result == 1 and not probe.survey and not probe.discovered,
          "native parse did not terminate under the fixed allow-list")
    return probe


def write(res, out: Path) -> dict:
    """page.bin, strings.bin (private strings, NUL-terminated, in provisional
    order) and manifest.json (page offset -> string, for the runtime patch)."""
    out.mkdir(parents=True, exist_ok=True)
    stock_len = len(res["pool"].stock)
    tail = bytes(res["pool"].data[stock_len:])
    (out / "page.bin").write_bytes(res["page"])
    (out / "strings.bin").write_bytes(tail)
    manifest = dict(
        page_bytes=len(res["page"]), page_sha256=hashlib.sha256(res["page"]).hexdigest(),
        stock_pool_bytes=stock_len,
        strings={t: o - stock_len for t, o in res["pool"].added.items()},
        refs=[dict(page_offset=a, text=t) for a, t in res["abs_refs"]],
        clones=[dict(key=r["key"], root=r["root"], ids=r["ids"]) for r in res["report"]],
        replaces=dict(page="B2_5", stock_entry_offset=B25_ENTRY_OFFSET))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    return manifest


SLMP_MAGIC, SLMP_VERSION = 0x504D4C53, 4     # sl_menu/sl_menu.h (4: refs into the pages pack)
SLMP_HEAD = 0x24                              # v3: + pages pack bytes at +0x20
SLMP_AT = 0xF000                              # SL_MENU_AT: past the loader's MAXLEN
SLMP_BYTES = 0x30000                          # the most a block may be (the installer's area);
                                              # written unpadded -- the installer reads by the
                                              # header's lengths, so a stale tail (putfile cannot
                                              # shorten) is ignored


def fnv(data, h=2166136261):
    for b in data:
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h


PAGES_REF = 0x80000000                         # a reference into the pages pack, not the page


def pack(res, nbr: bytes = b"", pages: bytes = b"", limit: int = SLMP_BYTES,
         pages_refs=()) -> bytes:
    """The "SLMP" block sl_menu.c reads from fpSup.BIN at SLMP_AT:
    +00 magic +04 version +08 page bytes +0C string bytes +10 refs
    +14 B2_5 offset +18 FNV-1a(body) +1C private NBR bytes (0 = none)
    +20 (v3) private pages pack bytes (0 = none), then the page, the private
    strings, {page offset, string offset} LE pairs, the private NBR (sl_lists.py)
    and the pages pack (sl_pages.py), each 4-aligned in the block; the FNV
    covers everything after the header."""
    stock_len = len(res["pool"].stock)
    strings = bytes(res["pool"].data[stock_len:])
    refs = b"".join(struct.pack("<II", a, res["pool"].added[t] - stock_len) for a, t in res["abs_refs"])
    # (v4) private strings in the pages pack: {pack offset | PAGES_REF, string offset}
    check(all(a < len(pages) for a, _ in pages_refs), "pages ref past the pack")
    refs += b"".join(struct.pack("<II", a | PAGES_REF, res["pool"].added[t] - stock_len) for a, t in pages_refs)
    n_refs = len(res["abs_refs"]) + len(pages_refs)
    body = res["page"] + strings + refs
    if nbr:
        check(nbr.startswith(b"NBR\0\x01\x05"), "not an NBR 1.5 pack")
        body += b"\0" * (-(SLMP_HEAD + len(body)) % 4) + nbr
    if pages:
        check(pages.startswith(b"NBR\0\x01\x09"), "not a version 1.9 pages pack")
        body += b"\0" * (-(SLMP_HEAD + len(body)) % 4) + pages
    head = struct.pack("<9I", SLMP_MAGIC, SLMP_VERSION, len(res["page"]), len(strings),
                       n_refs, B25_ENTRY_OFFSET, fnv(body), len(nbr), len(pages))
    data = head + body
    check(len(data) <= limit, f"{len(data)} bytes do not fit the {limit}-byte block")
    return data + b"\0" * (-len(data) % 4)

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, help="write page.bin / strings.bin / manifest.json here")
    ap.add_argument("--native", action="store_true", help="also run the original NBU interpreter")
    ap.add_argument("--pack", type=Path, help="write the SLMP block (for fpSup.BIN past 0xF000)")
    args = ap.parse_args(argv)
    img = (ROOT / "out/MAIN_c0000000.bin").read_bytes()
    res = build(img)
    page = res["page"]
    print("page", len(page), "bytes (r10 B2_5", res["base_len"], "+ 2 x", res["donor_bytes"], ")")
    for r in res["report"]:
        print(r["key"], "root", r["root"], "ids", r["ids"], "residual old-ID references", len(r["residue"]),
              "(straddling byte hits", r["straddle"], ")")
    print("private strings", list(res["pool"].added), "page refs", len(res["abs_refs"]))
    print("audit", audit(res, img)["header_minus_actual"])
    if args.native:
        probe = native_parse(page, res["pool"].data, img)
        print("native parse", len(probe.traces), "records, terminated cleanly")
    if args.out:
        m = write(res, args.out)
        print("wrote", args.out, m["page_sha256"][:16])
    if args.pack:
        import sl_lists
        args.pack.write_bytes(pack(res, sl_lists.build_pack(img) if WITH_CUSTOM_LISTS else b""))
        print("packed", args.pack)


if __name__ == "__main__":
    main()
