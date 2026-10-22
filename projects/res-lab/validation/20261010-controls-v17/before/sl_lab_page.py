#!/usr/bin/env python3
"""Sensor Lab: the tabbed settings page (design §8.12 "設計定案"), a private page.

Base: the stock frame-guide page B5_4_2, whose three inner tabs (FORMAT /
OFFSET / STYLE) switch on the page itself (MenuItem_Tab_Item3 35010: Left/Right
'--'/'++' on its controlValue, groups Tab and SubTab, MENU_FrameGuideTabNo).
A whole stock page, because camera r16 showed a private page needs one.

  tab 1 (container 92)  FILTER  Bit depth / Frame rate / Width / Proportion
  tab 2 (container 93)  MODE    placeholder row (in-row switching + preview: step 3)
  tab 3 (container 101) OUTPUT  Resolution / Binning / Squeeze / Scale (display only)

Every row is a copy of STYLE's first row (object 90, a MenuItem_Select with a
popup list -- same page, as the camera wants), grown to its list's length the
way sl_b25_page.grow_rows grows the frame-rate row.  The stock rows go: FORMAT's
and OFFSET's jump to the native digit page B5_4_2_1 (whose handler writes the
stock frame-guide settings), STYLE's four write MV_FRMGUIDE_*.  Every variable
the page writes is private -- MENU_FrameGuideTabNo -> SL_LabTab, MENU_Level3 ->
SL_LabFocus (it holds the focused OBJECT id: camera r17), the rows' values ->
SL_F_* / reused MV_SL* -- and the build refuses a page that still names any
MV_FRMGUIDE_* (SETTINGS_AREA_FIRST_RULE).  The tab captions are still the stock
images (FORMAT / OFFSET / STYLE) in this step.  Offline only.
"""
from __future__ import annotations

import struct

import sl_b25_page as P
import sl_size_page as SZ
from sl_b25_page import A, BM, N, U, check, local_ids, put, u32

PAGE_NAME = "SL_LAB"
CALC_ONLY = False
VIRTUAL_APPLY = False
BASE_SET = "B5_4_2"
TAB_ITEM = 35010                                   # MenuItem_Tab_Item3
TAB_CONTAINERS = (92, 93, 101, 49000)              # SubTab members: FILTER, MODE, OUTPUT, NAME (tabs4)
OLD_ROWS = {92: (35533, 34731, 38191), 93: (38722, 38711), 101: (90, 34730, 4413, 4441)}
# also goes: FORMAT's BG 5039 (y 81, h 162, opaque 222222) -- the backdrop of the
# stock two-row item; it covered FILTER's rows 1-2 on camera (r23)
OLD_EXTRA = {92: (5039,)}
# Stock FORMAT objects that move to OUTPUT (same page) instead of going:
# BG 5039 + panel 35533 (the 2-row info area), and 34732 (寬度/高度, a stock
# MenuItem_Jump row at y 324, inside the dropped 38191).
OUTPUT_TAB = 101
OUTPUT_PANEL = (5039, 35533)
OUTPUT_JUMP = 34732
JUMP_TITLE_OWNER, JUMP_TITLE = 38161, "Width / Height"
# the panel editor (sl_modes.c panel_key): key -> code written to SL_O_Key
PANEL_KEY_VAR = "SL_O_Key"
KEY_EDIT_ON = 5
EDITOR_KEYS = (("Left", 1), ("Right", 2), ("Up", 3), ("Down", 4), ("OK", 6), ("Menu", 6),
               ("FDial_R", 7), ("FDial_L", 8))
PANEL_ROW_Y = 121.0                    # the panel row's highlight behind the numbers
ARROW_UP, ARROW_DOWN = 38747, 38746    # OFFSET's Cursor_Up / Cursor_Down (that tab's rows go)
ARROW_Y = {"up": -30.0, "down": 55.0}
DIAL_OWNER = 42035                     # DialKeyEvent: FDial_R / FDial_L
WRITE_VALUE_AT, FOCUS_TARGET_AT = 41, 40    # controlAppVariable value / controlFocus object-id     # its Name (stock text 1702 = 寬度 / 高度)
# the panel's own variables: the line switch and two animated glyphs -> private
# integers (sl_menu.c names 2..4); the text / width bindings of its number fields
# go until the string variables exist (step 2)
# The panel's line reads "W x H   binH x binV   scaleW x scaleH %": integer app
# variables (sl_modes.c sl_menu_panel posts them) shown with %d by stock's
# drawImageLayout number fields (QS_Digits glyphs: digits and '.' only, so the
# x / % are their own glyph objects, as stock's are).  Stock's line is
# W x H mm  H : V  NNN %; mm, the animated V digit and the animated scaling
# digits go, the ':' becomes x, three number fields and one x are copied from the
# line's own objects.  The second line (aspect-ratio input) goes too.
PANEL_RENAME = {"MV_FRMGUIDE_Input": "SL_O_In", "MV_FRMGUIDE_Width": "SL_O_W",
                "MV_FRMGUIDE_Height": "SL_O_H", "MV_FRMGUIDE_HorizontalRatio": "SL_O_BH"}
PANEL_UNBIND = ("MV_FRMGUIDE_WidthW", "MV_FRMGUIDE_HeightW", "MV_FRMGUIDE_HorizontalRatioW")
PANEL_VARS = ("SL_O_W", "SL_O_H", "SL_O_In", "SL_O_BH", "SL_O_BV", "SL_O_SW", "SL_O_SH")
PANEL_LINE, PANEL_LINE2 = 35534, 37640
PANEL_DROP = (37104, 37110, 35541, 40374, 40375, 40376)       # mm, V digit, scaling + its digits
PANEL_PERCENT, PANEL_COLON, PANEL_X, PANEL_ASPECT = 40652, 37105, 35538, 35540
PANEL_SELECT_OWNER = 35533
# field widths (QS_Digits: a digit is 34 px): 4 digits, 1 digit; the RWZM scale
# "0.32" (text variables: the user 2026-10-03, "503 %" read as 5x) 4 glyphs
# "0.32" = three digits and the 12 px '.' (kigou_01): exactly 114, or the slack
# shows as a space on one side of the x only (camera r39)
PANEL_WIDTH = {39544: 136.0, 35539: 136.0, 35540: 34.0, "BV": 34.0, "SW": 114.0, "SH": 114.0}
PANEL_SPACES = (39820, 39821)          # the gaps either side of W x H's x: copied round RWZM's
PANEL_GREY = struct.pack(">f", 0.5334330201148987)   # stock's dimmed colour key
PANEL_X_W = 35.0                       # the x glyph's box (35538); the ':' it replaces is 43
DONOR = dict(row=90, select=4247, lst=14, item=15, iconchange=872, icontext=677, icon=10,
             title_owner=4250, scrollbar=4248, rows=4)
DONOR_VAR, DONOR_LIST, DONOR_ROOT_NAME = "MV_FRMGUIDE_Style", "B5_4_1_01", "B5_4_1"
PAGE_RENAME = {"MENU_Level3": "SL_LabFocus", "MENU_FrameGuideTabNo": "SL_LabTab"}
FORBIDDEN_PREFIXES = ("MV_FRMGUIDE_", "CM_ZBRHIL_")
ROW_Y = (81.0, 162.0, 243.0, 324.0, 405.0)
WIDTH_OBJECTS = ("submenu_width_01", "submenu_width_02")
LIST_TEMPLATE_IDS = (20, 65, 77, 97, 117, 137, 157, 177, 197, 217, 237)   # object ids in a 0x10008


def rows_spec():
    import sl_lists as L
    lit = lambda t: dict(text=t)
    spec = {
        # literal titles: B2_5's own IDs (0315 frame rate, 0312 resolution) drew
        # nothing on this page (r23) -- the .nloc lookup seems scoped to its screen
        92: [dict(key="BIT", var="SL_F_Bit", list=L.F_BIT_NAME, title=lit("Bit depth"), rows=L.F_BIT_ROWS, step=True),
             dict(key="FPS", var="SL_F_Fps", list=L.F_FPS_NAME, title=lit("Frame rate"), rows=L.F_FPS_ROWS, step=True),
             dict(key="WIDTH", var="SL_F_Width", list=L.F_WIDTH_NAME, title=lit("Width"), rows=L.F_WIDTH_ROWS,
                  step=True),
             dict(key="PROP", var="SL_F_Prop", list=L.F_PROP_NAME, title=lit("Proportion"), rows=L.F_PROP_ROWS,
                  step=True),
             dict(key="CROP", var="SL_F_Crop", list=L.F_CROP_NAME, title=lit("Crop"), rows=L.F_CROP_ROWS,
                  step=True)],
        # MODE: the sensor modes the recipe solves for the menu's bit depth x
        # rate, best guessed quality first, written on the camera (sl_modes.c);
        # its caps and summary follow SL_ModeMax / SL_M_Text
        93: [dict(key="MODE", var="SL_M_Sel", list=L.MODE_NAME, title=lit("MODE"), rows=L.lab_mode_rows(),
                  step=True, max_var="SL_ModeMax", summary_var="SL_M_Text")],
        # OUTPUT copies the stock custom-frame FORMAT layout (camera screenshot
        # 2026-10-03): the stock info panel on top (OUTPUT_PANEL), then 比例,
        # 寬度/高度 (the stock jump row, OUTPUT_JUMP), Binning.
        101: [dict(key="SQZ", var="MV_SLScale", list=L.SCALE_NAME, title=lit("Ratio"), rows=L.SCALE_ROWS, y=243.0,
                   step=True),
              # pixels cut from the readout, edited in place (sl_modes.c crop_key);
              # its list is never shown (Right / OK open the editor instead)
              dict(key="CROP_O", var="SL_O_In", list=L.CROP_O_NAME, title=lit("Crop"), rows=L.CROP_O_ROWS,
                   y=324.0, summary_var="SL_C_Text", crop_editor=True),
              # the MB/s for the setting or any rate (sl_modes.c rate_post)
              dict(key="RATE", var="SL_O_RFps", list=L.RATE_SEL_NAME, title=lit("Data rate"),
                   rows=L.RATE_SEL_ROWS, y=405.0, step=True, summary_var="SL_O_Rate")],
        # NAME (the fourth tab, tabs4): which CUSTOM preset; its name and Save next
        NAME_TAB: [dict(key="PRESET", var="SL_N_Sel", list=L.N_PRESET_NAME, title=lit("Preset"),
                        rows=L.N_PRESET_ROWS, step=True)],
    }
    if CALC_ONLY:
        del spec[NAME_TAB]
        spec[OUTPUT_TAB].append(dict(key="EXPORT", var="SL_E_Button", list=L.CROP_O_NAME,
                                    title=lit("Apply" if VIRTUAL_APPLY else "Save RCD"), rows=L.CROP_O_ROWS, y=486.0,
                                    summary_var="SL_E_Text", export=True))
    return spec



def key_diag(rows, pool):
    """SL_KEY_DIAG (diagnostic card only): which keyEvent form repeats while a
    key is held (the user 2026-10-03: holding Left / Right on MODE steps once;
    USB-injected keys never repeat, so only a hand on the camera can tell).
    FILTER's rows get four forms of their Right key: Bit depth = stock's date
    fields' (args 0x27), Frame rate = type 2 + args, Width = type 1 + args,
    Proportion = unchanged (no fields: the control)."""
    forms = ((0x8, b""), (0x9, (2).to_bytes(4, "big")), (0x9, (1).to_bytes(4, "big")), None)
    for out, form in zip(rows, forms):
        if form is None:
            continue
        sel = next(u32(r, 20) for r in out if u32(r, 0) == 0x10003 and pool.text(u32(r, 28)) == "MenuItem_Select")
        hits = [r for r in out if u32(r, 0) == 0x10006 and u32(r, 24) == sel
                and pool.text(u32(r, 8)) == "keyEvent" and pool.text(u32(r, 20)) == "Right"]
        check(len(hits) == 1 and len(hits[0]) == 36 and u32(hits[0], 32) == 0, "step Right key")
        mask, typ = form
        new = bytearray(hits[0][:32]) + mask.to_bytes(4, "big") + typ + (0x27).to_bytes(4, "big")
        put(new, 4, len(new))
        hits[0][:] = new


def diag_rows_spec(spec):
    """SL_LAB_DIAG=rows (diagnostic card only): FILTER's rows become 3 / 5 / 6 / 11
    items, safest first, to find the size at which focusing a row takes the camera
    down (r24 / r26 / r27)."""
    import sl_lists as L
    # d6: 3 items as is; then 5 items with only one of the three growth parts
    plan = ((0, 3, GROW_ALL, "3 items"), (3, 5, {"cap"}, "5 cap only"),
            (3, 5, {"pair"}, "5 pair only"), (3, 5, {"text"}, "5 text only"))
    out = []
    for src, n, parts, title in plan:
        s = dict(spec[92][src])
        check(len(s["rows"]) >= n, "diag rows")
        s.update(rows=s["rows"][:n], grow=frozenset(parts), title=dict(text=title))
        out.append(s)
    spec[92] = out
    return spec


def base_page():
    import sl_pages
    return sl_pages.set_bytes(BASE_SET)


def private_vars():
    """(name, initial) of every private variable this page adds (sl_menu.c)."""
    names = []
    for specs in rows_spec().values():
        for s in specs:
            if not s["var"].startswith("MV_SL"):          # MV_SL* are registered already
                names.append(s["var"])
    return [(n, 0) for n in names] + [("SL_LabTab", 0), ("SL_LabFocus", TAB_ITEM)]


# ---- one row --------------------------------------------------------------
def _obj_name(donor, oid):
    return next(u32(r.to_bytes(), 28) for r in donor if r.tag == 0x10003 and r.words(7)[3] == oid)


def clone_row(donor, sub, spec, row_y, parent, pool, schemas, next_id, refs):
    mapping = {old: next_id + i for i, old in enumerate(sorted(sub))}
    next_id += len(sub)
    rename = {pool.find(DONOR_VAR): spec["var"], pool.find(DONOR_LIST): spec["list"]}
    check(None not in rename, "donor strings")
    title_rec = None
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
        if u32(rec, 0) == 0x10008:
            # the List's item template.  Its object ids sit at fixed offsets (read off
            # B2_5's five 269-byte templates, whose ids are all > 64).  Here the donor's
            # List / ListItem / Text are 14 / 15 / 16: a "> 64" scan left them, and the
            # popup pointed at the removed stock ListItem -- r23/r24 froze on Right.
            check(len(rec) == 269, "list template size")
            for o in LIST_TEMPLATE_IDS:
                if u32(rec, o) in mapping:
                    put(rec, o, mapping[u32(rec, o)])
        if (u32(rec, 0) == 0x10005 and pool.text(u32(rec, 8)) == "drawText"
                and u32(rec, 20) == mapping[DONOR["title_owner"]]):
            title_rec = rec
        out.append(rec)
    # the collapsed summary: stock shows the frame-guide icons (Icon 10) and hides
    # the text (IconText 677) -- r23 showed an empty box on every row.  Text on,
    # icons drawn with the stock "blank" image (the IconChange still toggles both).
    icons = {o for o in sub if any(u32(r.to_bytes(), 0) == 0x10003 and u32(r.to_bytes(), 20) == o and
                                   u32(r.to_bytes(), 24) == DONOR["icon"] for r in donor)}
    blank = pool.find("blank")
    shown = 0
    for rec in out:
        if u32(rec, 0) == 0x10004 and u32(rec, 20) == mapping[DONOR["icontext"]]:
            check(u32(rec, 28) == 0x43 and rec[-1] == 0, "summary text objectBase")
            rec[-1] = 1                                   # is-visible
            shown += 1
        elif (u32(rec, 0) == 0x10005 and pool.text(u32(rec, 8)) == "drawImage"
              and u32(rec, 20) in {mapping[o] for o in icons}):
            put(rec, 32, blank)
    check(shown == 1 and len(icons) == 8, "summary layers")
    # the popup width: stock sizes this List from the app variable submenu_width
    # (objects submenu_width_01 / _02: List position X = 1024 - w, size X = w, item
    # rects), set for its icon-only lists -- on camera (r25) our popups came out
    # ~240 px wide, text squeezed to a line.  Without them the List keeps its own
    # objectBase: x 77, width 947, as on B2_5.
    gone = {mapping[o] for o in sub if pool.text(_obj_name(donor, o)) in WIDTH_OBJECTS}
    check(len(gone) == 2, "submenu_width objects")
    keep, owner = [], None
    for rec in out:
        if u32(rec, 0) == 0x10003:
            owner = u32(rec, 20)
            check(owner in gone or u32(rec, 24) not in gone, "submenu_width has children")
        if owner not in gone:
            keep.append(rec)
    for rec in keep:
        if u32(rec, 0) == 0x10003:
            lost = sum(1 for g in out if u32(g, 0) == 0x10003 and u32(g, 20) in gone and u32(g, 24) == u32(rec, 20))
            put(rec, 16, u32(rec, 16) - lost)
    out[:] = keep
    # the title
    check(title_rec is not None, "row title drawText")
    t = spec["title"]
    text = t.get("nloc") or t.get("text")
    off, private = pool.intern(text)
    put(title_rec, 32, off)
    title_rec[36] = 1 if "nloc" in t else 0
    if private:
        refs.append((title_rec, 32, text))
    # position in the container, and the popup at the container's top
    root = mapping[DONOR["row"]]
    obj = next(r for r in out if u32(r, 0) == 0x10003 and u32(r, 20) == root)
    put(obj, 24, parent)
    base = next(r for r in out if u32(r, 0) == 0x10004 and u32(r, 20) == root)
    pos = bytes(base).find(struct.pack(">f", 81.0))
    check(pos > 0, "row y not found")
    struct.pack_into(">f", base, pos, row_y)
    for part, x in ((DONOR["lst"], 77.0), (DONOR["scrollbar"], 1014.0)):
        rec = next(r for r in out if u32(r, 0) == 0x10004 and u32(r, 20) == mapping[part])
        check(struct.unpack_from(">f", rec, 32)[0] == x and struct.unpack_from(">f", rec, 36)[0] == 0.0,
              f"popup position of {part}")
        struct.pack_into(">f", rec, 36, ROW_Y[0] - row_y)   # top at the first row, under the tabs
    added, next_id = grow(out, mapping, pool, refs, spec["rows"], next_id, spec.get("grow", GROW_ALL))
    if spec.get("display_only"):
        gone = display_only(out, mapping, pool)
        added = [a for a in added if not any(a is g for g in gone)]
    if spec.get("step"):
        step_keys(out, mapping, spec, pool, refs)
    if spec.get("max_var"):
        bind_max(out, mapping, spec["max_var"], pool, refs)
    if spec.get("summary_var"):
        next_id = summary_text(out, mapping, spec["summary_var"], pool, refs, next_id)
    return out, mapping, next_id


def _binding(owner, local, var, component, prop, pool, refs, kind):
    """An appVariableEvent naming its component, in stock's 58-byte form: mask
    0x2f; type 1 in stock's max-value bindings (owner 0x118C), 0 in its drawText
    ones (CM_WBText) -- `kind` copies whichever."""
    rec = bytearray(58)
    put(rec, 0, 0x10006); put(rec, 4, 58); put(rec, 8, pool.find("appVariableEvent"))
    put(rec, 12, 6); put(rec, 16, 0); put(rec, 20, 0xFFFFFFFF)
    put(rec, 24, owner); put(rec, 28, local); put(rec, 32, 0x2F); put(rec, 36, kind)
    _intern_at(rec, 40, var, pool, refs)
    put(rec, 45, component)
    put(rec, 49, pool.find(prop))
    put(rec, 54, 6)
    return rec


def _insert_component(out, obj, after, rec):
    """`rec` into object `obj`'s components right after record `after`; its count +1."""
    k = next(i for i, r in enumerate(out) if r is after)
    out.insert(k + 1, rec)
    o = next(r for r in out if u32(r, 0) == 0x10003 and u32(r, 20) == obj)
    put(o, 8, u32(o, 8) + 1)


# A list whose rows are written on the camera (MODE: sl_modes.c, up to 70): its
# caps follow SL_ModeMax = rows - 1 -- the List (cursor), the MenuItem_Select
# (Left / Right steps, the summary) and the IconChange, each controlValue's
# max-value bound like stock's (no cross-page SetLimit: B2_5's froze)
def bind_max(out, mapping, var, pool, refs):
    for part in ("select", "lst", "iconchange"):
        obj = mapping[DONOR[part]]
        ctl = [r for r in out if u32(r, 0) == 0x1000E and u32(r, 20) == obj
               and pool.text(u32(r, 8)) == "controlValue"]
        check(len(ctl) == 1, f"controlValue of {part}")
        mine = [k for k, r in enumerate(out) if u32(r, 0) != 0x10003 and
                u32(r, P.BM.OWNER_OFFSETS.get(u32(r, 0), 20)) == obj]
        local = max(P.local_ids(out, mine)) + 1
        _insert_component(out, obj, ctl[0], _binding(obj, local, var, u32(ctl[0], 24), "max-value", pool, refs, 1))


# The summary of such a list: the stock IconTexts are blank and a copy of the
# row's Name, right-aligned in the summary column, shows `var` (sl_modes.c
# SL_M_Text) -- a child of the MenuItem_Select, so it draws as the title does
# (under the popup, over the focus bar)
def summary_text(out, mapping, var, pool, refs, next_id):
    name = mapping[DONOR["title_owner"]]
    ks = [k for k, r in enumerate(out) if (u32(r, 0) == 0x10003 and u32(r, 20) == name) or
          (u32(r, 0) != 0x10003 and u32(r, P.BM.OWNER_OFFSETS.get(u32(r, 0), 20)) == name)]
    src = [out[k] for k in ks]
    check([u32(x, 0) for x in src] == [0x10003, 0x10004, 0x10005, 0x1000A], "Name shape")
    obj, base, text, clip = (bytearray(x) for x in src)
    oid = next_id
    put(obj, 20, oid); put(obj, 16, 0); put(obj, 8, 4)
    for x in (base, text, clip):
        put(x, 20, oid)
    check(u32(base, 28) == 3, "Name position and size")
    y = struct.unpack_from(">f", base, 36)[0]
    struct.pack_into(">fff", base, 32, RATE_VALUE_X, y, RATE_VALUE_W)
    check(u32(text, 28) == 0x40000011 and len(text) == 57, "Name drawText fields")
    text = text[:28] + struct.pack(">I", 0x40000001) + text[32:37] + text[41:]   # right-aligned
    put(text, 4, len(text))
    struct.pack_into(">f", text, len(text) - 8, RATE_VALUE_W)
    _intern_at(text, 32, " ", pool, refs)
    text[36] = 0
    bind = _binding(oid, 3, var, u32(text, 24), "text", pool, refs, 0)
    at = ks[-1] + 1
    out[at:at] = [obj, base, text, clip, bind]
    return next_id + 1


STEP_DONOR = 42315          # STYLE's MenuItem_Step popup ("SubMenu"): dst +/- 1, write, Left


def step_templates(recs, pool):
    """This page's own records for Left / Right stepping (SubMenu 42315)."""
    owner, out = None, {}
    for r in recs:
        d = r.to_bytes()
        if r.tag == 0x10003:
            owner = r.words(7)[3]
            continue
        if owner != STEP_DONOR or len(d) < 24:
            continue
        name = pool.text(u32(d, 8))
        if r.tag == 0x10006 and name == "keyEvent" and pool.text(u32(d, 20)) == "Left":
            out["Left"] = d
        elif r.tag == 0x10009 and name == "changePropertyByControl" and len(d) >= 55:
            out.setdefault(pool.text(u32(d, 50)), d)
        elif r.tag == 0x10009 and name == "controlAppVariable" and len(d) >= 49 and u32(d, 45) != 0:
            out.setdefault("write", d)
    check({"Left", "dst + 1", "dst - 1", "write"} <= set(out), f"step templates {sorted(out)}")
    return out


STEP_TM = {}


def step_keys(out, mapping, spec, pool, refs):
    """Left / Right change the row's value in place (the user, 2026-10-03): the
    row's own controlValue 'dst -/+ 1' (capped at the last option), then the
    variable written from it.  OK still opens the popup."""
    tm = STEP_TM
    sel = mapping[DONOR["select"]]
    n = len(spec["rows"])
    right = pool.find("Right")
    by = [k for k, r in enumerate(out) if (u32(r, 0) in BM.OWNER_OFFSETS
                                           and u32(r, BM.OWNER_OFFSETS[u32(r, 0)]) == sel)]
    ctl = [out[k] for k in by if u32(out[k], 0) == 0x1000E and pool.text(u32(out[k], 8)) == "controlValue"]
    check(len(ctl) == 1 and u32(ctl[0], 28) == 0x12, "row controlValue")
    struct.pack_into(">f", ctl[0], 32, float(n - 1))           # exactly the options: Right stops at the last

    def actions(event, formula):
        step = bytearray(tm[formula])
        put(step, 20, sel); put(step, 24, event); put(step, 28, 1); put(step, 36, sel)
        write = bytearray(tm["write"])
        put(write, 20, sel); put(write, 24, event); put(write, 28, 2)
        _intern_at(write, 36, spec["var"], pool, refs)
        put(write, 45, sel)
        return [step, write]

    k = next(k for k in by if u32(out[k], 0) == 0x10006 and pool.text(u32(out[k], 8)) == "keyEvent"
             and u32(out[k], 20) == right)
    key = out[k]
    nact = u32(key, 16)
    acts = actions(u32(key, 28), "dst + 1")
    put(key, 16, 2)
    out[k + 1:k + 1 + nact] = acts
    # Left: a new key event right after Right's actions
    left = bytearray(tm["Left"])
    local = max(local_ids(out, [i for i, r in enumerate(out) if u32(r, 0) in BM.OWNER_OFFSETS
                                and u32(r, BM.OWNER_OFFSETS[u32(r, 0)]) == sel])) + 1
    put(left, 24, sel); put(left, 28, local); put(left, 16, 2)
    out[k + 3:k + 3] = [left] + actions(local, "dst - 1")
    obj = next(r for r in out if u32(r, 0) == 0x10003 and u32(r, 20) == sel)
    put(obj, 8, u32(obj, 8) + 1)


GROW_ALL = frozenset(("cap", "pair", "text"))


def grow(out, mapping, pool, refs, rows, new_id, parts=GROW_ALL):
    """Fit the copy to `rows` (fp-native-ui section 2 rules 7-9): one cursor pair
    per row, the List cap rows-1, the summary maxima, one summary IconText per row
    labelled with the row number (stock strings)."""
    n = len(rows)
    lst, item, sel, ichg, itext = (mapping[DONOR[k]] for k in ("lst", "item", "select", "iconchange", "icontext"))
    owner, by_owner, objs = None, {}, {}
    for k, rec in enumerate(out):
        if u32(rec, 0) == 0x10003:
            owner = u32(rec, 20)
            objs[owner] = k
        by_owner.setdefault(owner, []).append(k)

    def ctrl(obj, prop, at, value, at_least=False):
        hits = [k for k in by_owner[obj] if u32(out[k], 0) == 0x1000E and u32(out[k], 28) == prop]
        check(len(hits) == 1, f"controller {prop:#x} of {obj}")
        rec = out[hits[0]]
        old = struct.unpack_from(">f", rec, at)[0]
        struct.pack_into(">f", rec, at, max(old, value) if at_least else value)

    d0 = DONOR["rows"]
    if "cap" in parts:
        ctrl(lst, 0xA, 32, n - 1)
    ctrl(item, 3, 36, n, at_least=True)
    ctrl(sel, 0x12, 32, n - 1, at_least=True)
    ctrl(ichg, 0x12, 32, n - 1, at_least=True)
    ev_name, fo_name = pool.find("controlValueEvent"), pool.find("controlFocus")
    events = {struct.unpack_from(">f", out[k], 40)[0]: k for k in by_owner[lst]
              if u32(out[k], 0) == 0x10006 and u32(out[k], 8) == ev_name and u32(out[k], 32) == 3}
    focus = {u32(out[k], 24): k for k in by_owner[lst]
             if u32(out[k], 0) == 0x10009 and u32(out[k], 8) == fo_name and u32(out[k], 40) == lst}
    check(sorted(events) == [float(v) for v in range(1, d0)], f"List cursor events {sorted(events)}")
    last = float(d0 - 1)
    last_ev = out[events[last]]
    last_fo_k = focus[u32(last_ev, 28)]
    # this page names its events with two digits ("01".."04"; B2_5 uses "1".."10")
    check(pool.text(u32(last_ev, 20)) == f"{d0:02d}" and pool.text(u32(out[last_fo_k], 44)) == str(d0 - 1),
          "last pair names")
    # local ids: events (+28) and clips (+24) share one space per object.  B5_4_2's
    # List has its model clip at 17 and events up to 16: "events + 1" gave the new
    # pair 17 and focusing the row took the camera down (r24..r27, d5/d6).
    key = max(local_ids(out, by_owner[lst])) + 1
    pair, added = [], []
    for v in range(d0, n if "pair" in parts else d0):
        e, f = bytearray(last_ev), bytearray(out[last_fo_k])
        label, p1 = pool.intern(f"{v + 1:02d}")
        name, p2 = pool.intern(str(v))
        put(e, 20, label); put(e, 28, key)
        struct.pack_into(">f", e, 40, float(v))
        put(f, 24, key); put(f, 44, name)
        if p1:
            refs.append((e, 20, f"{v + 1:02d}"))
        if p2:
            refs.append((f, 44, str(v)))
        pair += [e, f]
        key += 1
    inserts = {}
    if pair:
        inserts[last_fo_k] = pair
        put(out[objs[lst]], 8, u32(out[objs[lst]], 8) + len(pair) // 2)
        added += pair
    # summary: one IconText per row, labelled with the row number
    text_name = pool.find("drawText")
    children = [o for o, k in objs.items() if u32(out[k], 24) == itext]

    def draw_text(obj):
        hits = [k for k in by_owner[obj] if u32(out[k], 0) == 0x10005 and u32(out[k], 8) == text_name]
        check(len(hits) == 1, f"drawText of {obj}")
        return out[hits[0]]

    for obj, row in zip(children, rows):
        rec = draw_text(obj)
        off, private = pool.intern(row["summary"])
        put(rec, 32, off)
        rec[36] = 0
        if private:
            refs.append((rec, 32, row["summary"]))
    tail = by_owner[children[-1]]
    copies = []
    for v in range(len(children), n if "text" in parts else len(children)):
        recs = [bytearray(out[k]) for k in tail]
        put(recs[0], 20, new_id)
        for r in recs[1:]:
            put(r, BM.OWNER_OFFSETS[u32(r, 0)], new_id)
        rec = next(r for r in recs if u32(r, 0) == 0x10005 and u32(r, 8) == text_name)
        off, private = pool.intern(rows[v]["summary"])
        put(rec, 32, off)
        rec[36] = 0
        if private:
            refs.append((rec, 32, rows[v]["summary"]))
        copies += recs
        new_id += 1
    if copies:
        inserts[tail[-1]] = copies
        put(out[objs[itext]], 16, len(children) + (n - len(children)))
        added += copies
    grown = []
    for k, rec in enumerate(out):
        grown.append(rec)
        grown.extend(inserts.get(k, []))
    out[:] = grown
    return added, new_id


def display_only(out, mapping, pool):
    sel = mapping[DONOR["select"]]
    keys = {pool.find("Right"), pool.find("OK")}
    gone, i = [], 0
    while i < len(out):
        r = out[i]
        if (u32(r, 0) == 0x10006 and u32(r, 24) == sel and pool.text(u32(r, 8)) == "keyEvent"
                and u32(r, 20) in keys):
            n = u32(r, 16)
            acts = out[i + 1:i + 1 + n]
            check(all(u32(a, 0) == 0x10009 and u32(a, 20) == sel for a in acts), "key actions")
            gone += [r] + acts
            del out[i:i + 1 + n]
            continue
        i += 1
    check(len([g for g in gone if u32(g, 0) == 0x10006]) == 2, "Right / OK keyEvents")
    obj = next(r for r in out if u32(r, 0) == 0x10003 and u32(r, 20) == sel)
    put(obj, 8, u32(obj, 8) - 2)
    return gone


def output_moves(recs, objs, pool, schemas, refs, next_id):
    """The stock objects OUTPUT takes from FORMAT: {root: [records]} with the root
    re-parented to OUTPUT, the panel's variables made private (PANEL_RENAME) or
    unbound (PANEL_UNBIND), and the jump row's Right / OK removed (they write
    MV_FRMGUIDE_InputType / SoftKeyboard_* and open the stock digit page, whose
    handler writes the stock frame-guide settings -- step 3 brings a private one).
    Also returns the records taken out, for the allocation header."""
    rename = {pool.find(k): v for k, v in PANEL_RENAME.items()}
    unbind = {pool.find(k) for k in PANEL_UNBIND}
    check(None not in rename and None not in unbind, "panel variables")
    moved, gone = {}, []
    for root in OUTPUT_PANEL + (OUTPUT_JUMP,):
        a, b = SZ.span(recs, objs, SZ.subtree(objs, root), root)
        out, owner_k = [], {}
        for r in recs[a:b]:
            d = bytearray(r.to_bytes())
            if r.tag == 0x10003:
                owner_k[u32(d, 20)] = len(out)
            if (r.tag == 0x10006 and pool.text(u32(d, 8)) == "appVariableEvent"
                    and any(u32(d, o) in unbind for o, k in P.typed_fields(bytes(d), pool, schemas)
                            if k in ("str", "text"))):
                check(u32(d, 16) == 0, "an unbound appVariableEvent with actions")
                gone.append(A.Record(0, bytes(d)))
                obj = out[max(v for v in owner_k.values())]
                put(obj, 8, u32(obj, 8) - 1)
                continue
            for off, kind in P.typed_fields(bytes(d), pool, schemas):
                if kind in ("str", "text") and u32(d, off) in rename:
                    new_off, private = pool.intern(rename[u32(d, off)])
                    put(d, off, new_off)
                    if private:
                        refs.append((d, off, _added_name(pool, new_off)))
            out.append(d)
        check(u32(out[0], 0) == 0x10003 and u32(out[0], 20) == root, "moved root")
        put(out[0], 24, OUTPUT_TAB)
        moved[root] = out
    arrows = {k: [bytearray(r.to_bytes()) for r in recs[a:b]] for k, (a, b) in (
        ("up", SZ.span(recs, objs, {ARROW_UP}, ARROW_UP)), ("down", SZ.span(recs, objs, {ARROW_DOWN}, ARROW_DOWN)))}
    arrows["bind"] = next(bytearray(r.to_bytes()) for r in recs if r.tag == 0x10006
                          and pool.text(u32(r.to_bytes(), 8)) == "appVariableEvent"
                          and pool.text(u32(r.to_bytes(), 40)) == "MV_FRMGUIDE_WidthW")
    moved[35533], more_gone, next_id, added = panel_line(moved[35533], pool, schemas, refs, next_id, arrows)
    gone += more_gone
    # The stock jump row becomes the panel's own row (date / time page style,
    # the user 2026-10-03): it sits behind the numbers (after the panel, before
    # its BG: an earlier record draws on top), no title, no "...".  Right / OK
    # start editing: a key code to sl_modes.c, focus to the invisible editor E.
    jump, sel = moved[OUTPUT_JUMP], 38159
    base = next(d for d in jump if u32(d, 0) == 0x10004 and u32(d, 20) == OUTPUT_JUMP)
    check(u32(base, 28) == 1 and struct.unpack_from(">f", base, 36)[0] == 324.0, "jump row position")
    struct.pack_into(">f", base, 36, PANEL_ROW_Y)
    title = [d for d in jump if u32(d, 0) == 0x10005 and pool.text(u32(d, 8)) == "drawText"
             and u32(d, 20) == JUMP_TITLE_OWNER]
    check(len(title) == 1 and pool.text(u32(title[0], 32)) == "1702", "jump row title")
    _intern_at(title[0], 32, " ", pool, refs)
    title[0][36] = 0
    dots = [d for d in jump if u32(d, 0) == 0x10005 and pool.text(u32(d, 8)) == "drawImage"
            and pool.text(u32(d, 32)) == "font_G_3dot"]
    check(len(dots) == 1, "jump row dots")
    put(dots[0], 32, pool.find("blank"))
    tm = editor_templates(recs, jump, pool, schemas, refs)
    editor = next_id
    next_id += 1
    keys = {pool.find("Right"), pool.find("OK")}
    i, n_done = 0, 0
    while i < len(jump):
        d = jump[i]
        if (u32(d, 0) == 0x10006 and u32(d, 24) == sel and pool.text(u32(d, 8)) == "keyEvent"
                and u32(d, 20) in keys):
            n = u32(d, 16)
            gone += [A.Record(0, bytes(x)) for x in jump[i + 1:i + 1 + n]]
            acts = [tm.write(sel, u32(d, 28), 1, KEY_EDIT_ON), tm.focus(sel, u32(d, 28), 2, editor)]
            put(d, 16, len(acts))
            jump[i + 1:i + 1 + n] = acts
            added += acts
            n_done += 1
        i += 1
    check(n_done == 2, "panel row Right / OK")
    e_recs = tm.editor(editor, OUTPUT_JUMP, sel)
    jump += e_recs
    added += e_recs
    return moved, gone, next_id, added


def _blocks(records):
    """[(object id, [records])] in stream order: each object with its components."""
    out = []
    for d in records:
        if u32(d, 0) == 0x10003:
            out.append((u32(d, 20), [d]))
        else:
            out[-1][1].append(d)
    return out


def _intern_at(rec, off, text, pool, refs):
    o, private = pool.intern(text)
    put(rec, off, o)
    if private:
        refs.append((rec, off, text))


# ---- the MODE tab's diagram (the user 2026-10-03) ---------------------------
# White = the sensor, green = what the chosen mode reads, red = the output; the
# green and red sizes labelled, then the mode's rate and rolling shutter.  Frame
# rects and texts follow sl_modes.c diagram_post (SL_D_*: tab pixels).  Frames:
# this page's outline drawRect (B5_4_2 Cursor 36: color, no fill, border width,
# rect), each rect component bound (x / y / w / h: property-subindex 0..3);
# texts: the row's Name with a colour field.  Drawn green over red over the
# sensor (an earlier record draws on top).
DIAG_X, DIAG_Y, DIAG_W, DIAG_H = 40.0, 180.0, 420.0, 280.0      # sl_modes.c DIAG_*
DIAG_TEXT_X, DIAG_TEXT_Y, DIAG_TEXT_DY = 485.0, 190.0, 50.0
DIAG_FONT = 40              # drawText font-size: stock's rows use 54 (the user: smaller)
DIAG_WHITE, DIAG_GREEN, DIAG_RED = 0xFFFFFFFF, 0x30D158FF, 0xFF453AFF
# the sensor is a filled block, not a frame (the user 2026-10-03, option A): a
# frame on the sensor's edge and a green on the same edge covered each other
DIAG_SENSOR = 0x505050FF
DIAG_CROP = 0xFFD60AFF      # yellow: what the OUTPUT Crop row leaves (SL_D_C*)
# border widths: red wider than green, green drawn over red (the user
# 2026-10-03), so a 1x mode's red (its largest output = its area) shows inside
# the green; both drawn inside their rects (the true areas, sl_modes.c
# diagram_post) over the sensor's filled block
DIAG_BORDER = {"G": 2.0, "R": 6.0, "C": 2.0}


def _binding_sub(owner, local, var, component, prop, subindex, pool, refs):
    """A 62-byte appVariableEvent with property-subindex (stock's mask 0x3f form,
    ListStepItem): one component of a vector property."""
    rec = bytearray(62)
    put(rec, 0, 0x10006); put(rec, 4, 62); put(rec, 8, pool.find("appVariableEvent"))
    put(rec, 12, 6); put(rec, 16, 0); put(rec, 20, 0xFFFFFFFF)
    put(rec, 24, owner); put(rec, 28, local); put(rec, 32, 0x3F); put(rec, 36, 0)
    _intern_at(rec, 40, var, pool, refs)
    put(rec, 45, component)
    put(rec, 49, pool.find(prop))
    put(rec, 54, subindex)
    put(rec, 58, 6)
    return rec


def diagram(row, recs, parent, pool, refs, next_id):
    """The records of the diagram objects, children of `parent` (MODE's tab)."""
    outline = [bytearray(r.to_bytes()) for r in recs if r.tag == 0x10005
               and pool.text(u32(r.to_bytes(), 8)) == "drawRect" and u32(r.to_bytes(), 28) == 0x20B]
    check(len(outline) == 1 and len(outline[0]) == 60, "outline drawRect (Cursor 36)")
    name = [k for k, r in enumerate(row) if u32(r, 0) == 0x10003 and pool.text(u32(r, 28)) == "Name"]
    check(name, "row Name")
    obj_t, base_t, text_t = (bytes(row[name[0] + i]) for i in range(3))
    check(u32(base_t, 0) == 0x10004 and u32(base_t, 28) == 3 and u32(text_t, 28) == 0x40000011
          and len(text_t) == 57, "Name shape")
    out = []

    def obj(count, x, y, w, h):
        nonlocal next_id
        o, b = bytearray(obj_t), bytearray(base_t)
        oid = next_id
        next_id += 1
        put(o, 20, oid); put(o, 24, parent); put(o, 16, 0); put(o, 8, count)
        put(b, 20, oid)
        struct.pack_into(">ffff", b, 32, x, y, w, h)
        return oid, o, b

    def frame(color, var, key):
        oid, o, b = obj(2 + (4 if var else 0), 0.0, 0.0, 1024.0, 600.0)
        r = bytearray(outline[0])
        put(r, 20, oid); put(r, 24, 1)
        put(r, 32, color)
        if key is None:                            # the sensor: a filled block, its true rect
            put(r, 36, 1)
            struct.pack_into(">f", r, 40, 0.0)
            struct.pack_into(">ffff", r, 44, DIAG_X, DIAG_Y, DIAG_W, DIAG_H)
        else:
            struct.pack_into(">f", r, 40, DIAG_BORDER[key])   # drawn inside its rect (the true area)
            struct.pack_into(">ffff", r, 44, DIAG_X, DIAG_Y, DIAG_W, DIAG_H)
        recs_ = [o, b, r]
        if var:
            for k, axis in enumerate("XYWH"):
                recs_.append(_binding_sub(oid, 2 + k, f"SL_D_{var}{axis}", 1, "rect", k, pool, refs))
        return recs_

    def text(var, color, line):
        oid, o, b = obj(3, DIAG_TEXT_X, DIAG_TEXT_Y + DIAG_TEXT_DY * line, 530.0, 54.0)
        t = bytearray(text_t)
        put(t, 20, oid)
        # fields: text (5 B), font-size (u32), horz-align, color, rect (mask bits 0, 2, 4, 13, 30)
        t = t[:28] + struct.pack(">I", 0x40002015) + t[32:37] + struct.pack(">I", DIAG_FONT) + t[37:41] + \
            struct.pack(">I", color) + t[41:]
        put(t, 4, len(t))
        struct.pack_into(">f", t, len(t) - 8, 530.0)
        _intern_at(t, 32, " ", pool, refs)
        t[36] = 0
        return [o, b, t, _binding(oid, 3, var, u32(t, 24), "text", pool, refs, 0)]

    out += frame(DIAG_CROP, "C", "C") + frame(DIAG_GREEN, "G", "G") + frame(DIAG_RED, "R", "R") + \
        frame(DIAG_SENSOR, None, None)
    out += text("SL_D_GTxt", DIAG_GREEN, 0) + text("SL_D_RTxt", DIAG_RED, 1)
    out += text("SL_D_Fps", DIAG_WHITE, 2) + text("SL_D_Rs", DIAG_WHITE, 3) + text("SL_D_CTxt", DIAG_CROP, 4)
    return out, next_id


# ---- OUTPUT panel captions (the user 2026-10-05: "vbin/hbin rwzm 可以標示在上面") ----
# The panel's number font has digits only (letters drew as boxes, camera r96),
# so the fields say what they are in small text above them, in the rows' font.
# Tab-container pixels, measured on the camera screenshot (r97).
CAPTION_FONT = 24
CAPTION_COLOR = 0x9A9A9AFF
# (literal, bound text variable, x): the bin field's names its kernel (SL_O_BTxt,
# sl_modes.c caption_bin: "bin" / "H(1,6,1) soft" / "(1,1,1)x(1,14,1) std")
CAPTIONS = (("W x H", None, 60.0), (None, "SL_O_BTxt", 455.0), ("RWZM", None, 615.0))   # left edges of the numbers (the user)
CAPTION_Y, CAPTION_W, CAPTION_H = 78.0, 260.0, 30.0   # r98: the edit arrow sits under y 82


def captions(row, parent, pool, refs, next_id):
    """Static drawTexts above the OUTPUT panel's fields (the row Name's shape,
    a literal text, no binding).  Records, children of `parent`."""
    name = [k for k, r in enumerate(row) if u32(r, 0) == 0x10003 and pool.text(u32(r, 28)) == "Name"]
    check(name, "row Name")
    obj_t, base_t, text_t = (bytes(row[name[0] + i]) for i in range(3))
    check(u32(base_t, 0) == 0x10004 and u32(base_t, 28) == 3 and u32(text_t, 28) == 0x40000011
          and len(text_t) == 57, "Name shape")
    out = []
    for text, var, x in CAPTIONS:
        o, b = bytearray(obj_t), bytearray(base_t)
        oid = next_id
        next_id += 1
        put(o, 20, oid); put(o, 24, parent); put(o, 16, 0); put(o, 8, 3 if var else 2)
        put(b, 20, oid)
        struct.pack_into(">ffff", b, 32, x, CAPTION_Y, CAPTION_W, CAPTION_H)
        t = bytearray(text_t)
        put(t, 20, oid)
        t = t[:28] + struct.pack(">I", 0x40002015) + t[32:37] + struct.pack(">I", CAPTION_FONT) + t[37:41] + \
            struct.pack(">I", CAPTION_COLOR) + t[41:]
        put(t, 4, len(t))
        struct.pack_into(">f", t, len(t) - 8, CAPTION_W)
        _intern_at(t, 32, text or " ", pool, refs)
        t[36] = 0                                  # a literal, not a string id
        out += [o, b, t] + ([_binding(oid, 3, var, u32(t, 24), "text", pool, refs, 0)] if var else [])
    return out, next_id


# ---- a fourth tab: NAME (the user 2026-10-03) ---------------------------------
# Stock has no four-tab bar (MenuItem_Tab_Item2 / _Item3 only): the three-tab one
# grows.  Its value 0..2 plays Tab "01".."03" (caption colours at frames 0 / 66 /
# 133, the cursor's x) and the Menu's SubTab "1".."3" (one container visible);
# a fourth value, state (frames 200..233), caption, cursor stop and container are
# added, and every clip keyed by tab gets a frame-200 key.  Records of the stock
# page that change are returned as (removed, added) for the allocation header.
# Camera d9 (2026-10-03): value 3's controlValueEvent never fires (it played
# stock's "03" and the bar stayed on FILTER) -- why is open; the fourth tab
# shows but cannot be reached.  The user put presets on hold ("SAVE" for now).
NAME_TAB = 49000                       # the fourth (SAVE) container (no stock object uses it)
TAB_SAVE_REACHABLE = False             # SAVE shown, not selectable, until value 3's event works
NAME_CAPTION = 49001
TAB_W = 256.0                          # 1024 / 4
# each state's frames: stock's three as they are, the fourth in the gap after the
# first (camera r61 / r62: a state at 200..233 played as the first -- the
# timeline seems to end at stock's 166); every clip holds a state's value over
# its whole span (a single key at its start slid towards the next one)
TAB_SPANS = ((0, 33), (66, 100), (133, 166), (40, 55))
TAB_FRAMES = tuple(a for a, _ in TAB_SPANS)


def _held(values):
    """[(frame, value)] holding each state's value over its whole span, in time order."""
    return sorted(k for (a, b), v in zip(TAB_SPANS, values) for k in ((a, v), (b, v)))
DIM = 0x3F088F11                       # the captions' dimmed channel value (0.5334)
BRIGHT = 0x3F800000


def _clip(head, props):
    """An animationClip from its 28-byte head and [(kind, component, name, dim,
    [(time, raw value)])] -- native_ui_audit.parse_clip's layout; the first key
    a = 0, later ones a = 1 (as stock's)."""
    body = bytearray()
    for kind, comp, name, dim, keys in props:
        body += struct.pack(">5I", len(keys), kind, comp, name, dim)
        for k, (time, raw) in enumerate(keys):
            body += bytes((0 if k == 0 else 1, 0)) + struct.pack(">II", time, raw)
    rec = bytearray(head[:28]) + body
    put(rec, 4, len(rec)); put(rec, 12, len(props))
    return rec


def _clip_props(rec, pool):
    c = A.parse_clip(A.Record(0, bytes(rec)), lambda o: o)
    out = []
    for p in c["properties"]:
        keys = [(k["time"], struct.unpack(">I", struct.pack(">f", k["value"]))[0] if p["kind"] == 1 else k["value"])
                for k in p["keys"]]
        out.append([p["kind"], p["component_ref"], p["name"], p["dimension"], keys])
    return out


def _group_add(rec, state_name, member, pool, refs):
    """One more state (copied from the last, frames 200..233) and one member."""
    nst, n = u32(rec, 8), u32(rec, 16)
    at = 28 + 21 * nst
    st = bytearray(rec[at - 21:at])
    _intern_at(st, 0, state_name, pool, refs)
    put(st, 4, TAB_SPANS[3][0]); put(st, 8, TAB_SPANS[3][1])
    members = bytes(rec[at:at + 8 * n])
    new = bytearray(rec[:at]) + st + members + struct.pack(">II", *member) + bytes(rec[at + 8 * n:])
    put(new, 8, nst + 1); put(new, 16, n + 1); put(new, 4, len(new))
    return new


def tabs4(seq, pool, refs, fresh=()):
    """Grow the tab bar to four.  Records change in place (string refs keep
    pointing at them); a stock one's old bytes go to `removed` and the record to
    `added`, one already new (`fresh`: tab_titles') is just rewritten.  Returns
    (records removed, records added, the NAME container's own records)."""
    removed, added = [], []
    fresh_ids = {id(x) for x in fresh}

    def swap(old, new):
        if id(old) not in fresh_ids and not any(old is a for a in added):
            removed.append(bytearray(old)); added.append(old)
        old[:] = new
        return old

    def recs(owner):
        return [r for r in seq if len(r) >= 28 and u32(r, 0) in P.BM.OWNER_OFFSETS
                and u32(r, P.BM.OWNER_OFFSETS[u32(r, 0)]) == owner]
    # the value 0..3
    cv = next(r for r in recs(TAB_ITEM) if u32(r, 0) == 0x1000E)
    check(struct.unpack_from(">f", cv, 32)[0] == 2.0, "tab bar max")
    # the cap stays 2 (the user: SAVE is a preview of what comes): Left / Right
    # cycle the three working tabs; value 3's event never fired anyway (d9)
    new = bytearray(cv); struct.pack_into(">f", new, 32, 3.0 if TAB_SAVE_REACHABLE else 2.0); swap(cv, new)
    # value 3's event and its two animations: copies of value 2's
    evs = [k for k, r in enumerate(seq) if u32(r, 0) == 0x10006 and u32(r, 24) == TAB_ITEM
           and pool.text(u32(r, 8)) == "controlValueEvent"]
    k2 = next(k for k in evs if u32(seq[k], 32) == 3 and struct.unpack_from(">f", seq[k], 40)[0] == 2.0)
    ev = bytearray(seq[k2]); struct.pack_into(">f", ev, 40, 3.0)
    local = max(P.local_ids(seq, [k for k, r in enumerate(seq) if len(r) >= 28 and u32(r, 0) in P.BM.OWNER_OFFSETS
                                  and u32(r, P.BM.OWNER_OFFSETS[u32(r, 0)]) == TAB_ITEM])) + 1
    put(ev, 28, local)
    acts = []
    import os                                   # SL_TAB_DIAG (diagnostic card): play stock's 3rd
    diag = os.environ.get("SL_TAB_DIAG")        # state -- does value 3's event fire at all?
    for j, name in ((1, "03" if diag else "04"), (2, "3" if diag else "4")):
        a = bytearray(seq[k2 + j])
        check(pool.text(u32(a, 8)) == "controlAnimation", "tab animation")
        put(a, 24, local)
        _intern_at(a, 44, name, pool, refs)
        acts.append(a)
    seq[k2 + 3:k2 + 3] = [ev] + acts
    added += [ev] + acts
    obj = next(r for r in seq if u32(r, 0) == 0x10003 and u32(r, 20) == TAB_ITEM)
    new = bytearray(obj); put(new, 8, u32(obj, 8) + 1); swap(obj, new)
    # the groups
    for owner, name, state, member in ((TAB_ITEM, "Tab", "04", (NAME_CAPTION, 3)), (83, "SubTab", "4", (NAME_TAB, 1))):
        g = next(r for r in seq if u32(r, 0) == 0x1000B and u32(r, 24) == owner and pool.text(u32(r, 20)) == name)
        check(u32(g, 8) == 3, f"{name} states")
        swap(g, _group_add(g, state, member, pool, refs))
    # captions: four 256 wide; each bright at its own frame
    caps = list(TAB_TITLES) + [NAME_CAPTION]
    src = [r for r in seq if u32(r, 0) == 0x10003 and u32(r, 20) == caps[2]]
    cap_recs = [bytearray(r) for r in recs(caps[2])]
    o = bytearray(src[0]); put(o, 20, NAME_CAPTION); _intern_at(o, 28, "4", pool, refs)
    new_cap = [o]
    for r in cap_recs:
        r = bytearray(r); put(r, P.BM.OWNER_OFFSETS[u32(r, 0)], NAME_CAPTION)
        if u32(r, 0) == 0x10005:
            _intern_at(r, 32, "EXPORT" if CALC_ONLY else "SAVE", pool, refs)     # the user: NAME -> SAVE (presets on hold)
        if u32(r, 0) == 0x10006:          # MODES' binding is not on OUTPUT; nothing else to drop
            continue
        new_cap.append(r)
    put(new_cap[0], 8, len(new_cap) - 1)
    k_after = max(k for k, r in enumerate(seq) if len(r) >= 24 and (
        (u32(r, 0) == 0x10003 and u32(r, 20) == caps[2]) or
        (u32(r, 0) in P.BM.OWNER_OFFSETS and u32(r, P.BM.OWNER_OFFSETS[u32(r, 0)]) == caps[2])))
    seq[k_after + 1:k_after + 1] = new_cap
    added += new_cap
    for i, c in enumerate(caps):
        for r in recs(c):
            if u32(r, 0) == 0x10004:
                new = bytearray(r); struct.pack_into(">ff", new, 32, TAB_W * i, struct.unpack_from(">f", r, 36)[0])
                struct.pack_into(">f", new, 40, TAB_W)
                swap(r, new)
            elif u32(r, 0) == 0x10005:
                new = bytearray(r); struct.pack_into(">ff", new, len(new) - 16, 0.0, struct.unpack_from(">f", r, len(r) - 12)[0])
                struct.pack_into(">f", new, len(new) - 8, TAB_W)
                swap(r, new)
            elif u32(r, 0) == 0x1000A:
                props = _clip_props(r, pool)
                for p_ in props:
                    p_[4] = _held([BRIGHT if (j == i or p_[3] == 3) else DIM for j in range(4)])
                swap(r, _clip(r, props))
    # the cursor: x 0 / 256 / 512 / 768, width 256
    cur = next(r for r in recs(35014) if u32(r, 0) == 0x1000A and u32(r, 24) == 3)
    props = _clip_props(cur, pool)
    for p_ in props:
        if pool.text(p_[2]) == "position":
            p_[4] = _held([struct.unpack(">I", struct.pack(">f", TAB_W * i))[0] for i in range(4)])
        else:
            p_[4] = _held([struct.unpack(">I", struct.pack(">f", TAB_W - 2))[0]] * 4)
    swap(cur, _clip(cur, props))
    for r in recs(35014):
        if u32(r, 0) in (0x10004, 0x10005):
            new = bytearray(r)
            off = 32 if u32(r, 0) == 0x10004 else len(r) - 8
            if u32(r, 0) == 0x10004:
                struct.pack_into(">f", new, 32 + (8 if u32(r, 28) & 1 else 0), TAB_W - 2)
            else:
                struct.pack_into(">f", new, off, TAB_W - 2)
            swap(r, new)
    # each container shown over its own state only
    for i, c in enumerate((92, 93, 101)):
        clip = next(r for r in recs(c) if u32(r, 0) == 0x1000A)
        props = _clip_props(clip, pool)
        props[0][4] = _held([1 if j == i else 0 for j in range(4)])
        swap(clip, _clip(clip, props))
    box = [bytearray(r) for r in seq if u32(r, 0) == 0x10003 and u32(r, 20) == 101]
    box += [bytearray(r) for r in recs(101) if u32(r, 0) in (0x10004, 0x1000A)]
    put(box[0], 20, NAME_TAB); _intern_at(box[0], 28, "4", pool, refs); put(box[0], 8, 2)
    for r in box[1:]:
        put(r, P.BM.OWNER_OFFSETS[u32(r, 0)], NAME_TAB)
    props = _clip_props(box[2], pool)
    props[0][4] = _held([0, 0, 0, 1])
    box[2] = _clip(box[2], props)
    return removed, added, box


# ---- the tab captions --------------------------------------------------------
# Stock's are images (font_menu_MB_tab_format / offset / style); they become
# text naming what each tab does (the user 2026-10-03), MODES with its count
# (SL_M_Tab, sl_modes.c mode_post).  The drawImage is swapped for a drawText
# with the same local id and colour, so the tab bar's clips (colour only:
# 888888 off, white on) still dim / light it.  horz-align 2 = center.
TAB_TITLES = {35011: ("FILTER", None), 35012: ("MODES", "SL_M_Tab"), 35013: ("OUTPUT", None)}


def tab_titles(seq, row, pool, refs):
    """Swap the three caption images for text.  Returns (records added, removed)."""
    name = next(r for r in row if u32(r, 0) == 0x10005 and pool.text(u32(r, 8)) == "drawText"
                and u32(r, 28) == 0x40000011)
    check(len(name) == 57, "Name drawText")
    added, removed = [], []
    for k, d in enumerate(list(seq)):
        if not (u32(d, 0) == 0x10005 and u32(d, 20) in TAB_TITLES and pool.text(u32(d, 8)) == "drawImage"):
            continue
        check(u32(d, 28) == 0x85 and len(d) == 56, "tab caption drawImage")
        owner = u32(d, 20)
        text, var = TAB_TITLES[owner]
        color = u32(d, 36)
        x, y, w, h = struct.unpack_from(">ffff", d, 40)
        cx = x + w / 2
        t = bytearray(name[:28]) + struct.pack(">I", 0x40002011) + bytes(name[32:37]) + \
            struct.pack(">II", 2, color) + struct.pack(">ffff", cx - 170.0, y - 8.0, 340.0, h + 16.0)
        put(t, 4, len(t)); put(t, 20, owner); put(t, 24, u32(d, 24))
        _intern_at(t, 32, text, pool, refs)
        t[36] = 0
        i = seq.index(d)
        seq[i] = t
        added.append(t); removed.append(d)
        if var:
            mine = [j for j, r in enumerate(seq) if len(r) >= 28 and u32(r, 0) in P.BM.OWNER_OFFSETS
                    and u32(r, P.BM.OWNER_OFFSETS[u32(r, 0)]) == owner]
            local = max(P.local_ids(seq, mine)) + 1
            b = _binding(owner, local, var, u32(t, 24), "text", pool, refs, 0)
            _insert_component(seq, owner, t, b)
            added.append(b)
    check(len(removed) == 3, "three tab captions")
    return added, removed


# A summary bound to a text variable (summary_text): right-aligned in the summary
# column (the stock IconText's x and width)
RATE_VALUE_X, RATE_VALUE_W = 433.0, 532.0


def panel_line(records, pool, schemas, refs, next_id, arrows):
    """OUTPUT's info line (see PANEL_RENAME).  Returns (records, records gone, next id)."""
    blocks = _blocks(records)
    ids = [b[0] for b in blocks]
    parent = {b[0]: u32(b[1][0], 24) for b in blocks}
    line2 = {PANEL_LINE2}
    for oid in ids:
        if parent[oid] in line2:
            line2.add(oid)
    drop = set(PANEL_DROP) | line2
    check(all(o in ids for o in PANEL_DROP), "panel objects changed")
    gone = [A.Record(0, bytes(x)) for oid, recs in blocks if oid in drop for x in recs]
    by_id = {oid: recs for oid, recs in blocks}

    def copy_of(src, var):
        nonlocal next_id
        out = [bytearray(x) for x in by_id[src]]
        put(out[0], 20, next_id)
        for x in out[1:]:
            put(x, BM.OWNER_OFFSETS[u32(x, 0)], next_id)
        if var:
            hits = [x for x in out if u32(x, 0) == 0x10006 and pool.text(u32(x, 8)) == "appVariableEvent"
                    and pool.text(u32(x, 40)) == "SL_O_BH"]
            check(len(hits) == 1, "number field binding")
            _intern_at(hits[0], 40, var, pool, refs)
        next_id += 1
        return out

    def width(recs, w):
        base = recs[1]
        check(u32(base, 0) == 0x10004 and pool.text(u32(base, 8)) == "objectBase" and u32(base, 28) & 2,
              "field objectBase")
        at = 32 + (8 if u32(base, 28) & 1 else 0)          # position (8 bytes) precedes size
        struct.pack_into(">f", base, at, w)

    # stock's ratio field and ':' dim at the Select group's frame 66 (the row
    # focused: camera r38 showed "1x1" grey), W / H do not: that key -> white,
    # before the copies take the clip
    for oid in (PANEL_ASPECT, PANEL_COLON):
        clips = [x for x in by_id[oid] if u32(x, 0) == 0x1000A]
        check(clips and all(PANEL_GREY in x for x in clips), "dimmed clip")
        for x in clips:
            x[:] = bytes(x).replace(PANEL_GREY, struct.pack(">f", 1.0))
    bv, sw, sh = copy_of(PANEL_ASPECT, "SL_O_BV"), copy_of(PANEL_ASPECT, "SL_O_SW"), copy_of(PANEL_ASPECT, "SL_O_SH")
    x2 = copy_of(PANEL_X, None)
    gaps = [copy_of(o, None) for o in PANEL_SPACES]
    for recs, key in ((by_id[39544], 39544), (by_id[35539], 35539), (by_id[35540], 35540),
                      (bv, "BV"), (sw, "SW"), (sh, "SH")):
        width(recs, PANEL_WIDTH[key])
    # ':' -> x
    img = [x for x in by_id[PANEL_COLON] if u32(x, 0) == 0x10005 and pool.text(u32(x, 8)) == "drawImage"]
    check(len(img) == 1 and pool.text(u32(img[0], 32)) == "font_menu_LB_kigou_02", "colon glyph")
    put(img[0], 32, pool.find("font_menu_LB_kigou_09"))
    width(by_id[PANEL_COLON], PANEL_X_W)              # the x's own box, not the ':''s wider one
    rect = bytes(img[0]).find(struct.pack(">ff", 43.0, 51.0))
    check(rect > 0, "colon rect")
    struct.pack_into(">f", img[0], rect, PANEL_X_W)
    # '%' goes: the scale is a factor now ("0.32 x 0.27"); kept in the tree under
    # the line (its owner, the scaling object, is dropped) but drawn blank
    put(by_id[PANEL_PERCENT][0], 24, PANEL_LINE)
    pct = [x for x in by_id[PANEL_PERCENT] if u32(x, 0) == 0x10005 and pool.text(u32(x, 8)) == "drawImage"]
    check(len(pct) == 1, "percent glyph")
    put(pct[0], 32, pool.find("blank"))
    # the Select group (the jump rows' highlight) keeps only members that remain
    out = []
    for oid, recs in blocks:
        if oid in drop:
            continue
        for x in recs:
            if u32(x, 0) == 0x1000B and pool.text(u32(x, 20)) == "Select" and u32(x, 24) == PANEL_SELECT_OWNER:
                nst, n = u32(x, 8), u32(x, 16)
                at = 28 + 21 * nst
                pairs = [bytes(x[at + 8 * i:at + 8 * i + 8]) for i in range(n)]
                keep = [p for p in pairs if struct.unpack(">I", p[:4])[0] not in drop]
                g = bytearray(x[:at]) + b"".join(keep) + bytes(x[at + 8 * n:])
                put(g, 16, len(keep))
                put(g, 4, len(g))
                x[:] = g
        if oid == PANEL_PERCENT:
            out.extend(sw + gaps[0] + x2 + gaps[1] + sh)
        out.extend(recs)
        if oid == PANEL_COLON:
            out.extend(bv)
    added = bv + sw + sh + x2 + gaps[0] + gaps[1]
    # the editing arrows: an up / down pair on each editable field, shown by
    # SL_O_A<k> (sl_modes.c: 1 on the field being edited)
    fields = {39544: 0, 35539: 1, 35540: 2, u32(bv[0], 20): 3}
    final = []
    for x in out:
        final.append(x)
    out = []
    i = 0
    while i < len(final):
        x = final[i]
        out.append(x)
        if u32(x, 0) == 0x10003 and u32(x, 20) in fields:
            j = i + 1
            while j < len(final) and u32(final[j], 0) != 0x10003:
                out.append(final[j])
                j += 1
            f = u32(x, 20)
            width = PANEL_WIDTH[{39544: 39544, 35539: 35539, 35540: 35540}.get(f, "BV")]
            for kind in ("up", "down"):
                arrow, next_id = make_arrow(arrows, kind, f, width, f"SL_O_A{fields[f]}", next_id, pool, refs)
                out += arrow
                added += arrow
            i = j
            continue
        i += 1
    return out, gone, next_id, added


def make_arrow(arrows, kind, field, width, var, next_id, pool, refs):
    """One editing arrow: a copy of this page's Cursor_Up / Cursor_Down (OFFSET's,
    dropped), under a panel field, shown while SL_O_A<k> is 1 (objectBase
    opacity bound like the stock WidthW -> size binding)."""
    src = arrows[kind]
    check([u32(x, 0) for x in src] == [0x10003, 0x10004, 0x10005, 0x1000A], f"{kind} arrow shape")
    src = src[:3]                                 # its colour clip belongs to OFFSET's cursor group
    obj, base, img = (bytearray(x) for x in src)
    down = arrows["down"][1]                      # its objectBase carries a position
    check(u32(down, 28) == 3, "arrow position")
    base = bytearray(down)
    oid = next_id
    put(obj, 20, oid)
    put(obj, 24, field)
    put(obj, 8, 3)
    put(obj, 16, 0)
    for x in (base, img):
        put(x, 20, oid)
    struct.pack_into(">ff", base, 32, width / 2 - 13.0, ARROW_Y[kind])
    bind = bytearray(arrows["bind"])
    check(pool.text(u32(bind, 49)) == "size" and u32(bind, 45) == 0, "visibility binding template")
    put(bind, 24, oid)
    put(bind, 28, 3)
    _intern_at(bind, 40, var, pool, refs)
    # opacity, not is-visible: d7 (2026-10-03) showed a bound is-visible never
    # hides / shows; an int bound to a float property converts (WidthW -> size)
    put(bind, 49, pool.find("opacity"))
    import os
    if os.environ.get("SL_ARROW_DIAG"):
        # diagnostic card d7: always shown; up stays outside the field, down inside
        struct.pack_into(">ff", base, 32, width / 2 - 13.0, -30.0 if kind == "up" else 10.0)
        put(obj, 8, 2)
        return [obj, base, img], next_id + 1
    return [obj, base, img, bind], next_id + 1


CROP_KEY_BASE = 10          # sl_modes.c K_CROP: the Crop editor writes 10 + EDITOR_KEYS' codes


def crop_editor(row, tm, pool, next_id):
    """The Crop row edits in place like the panel row: Right / OK write 15 (edit)
    and focus its own invisible editor E2, whose keys write 11..18 and whose OK /
    MENU hand focus back to the row (sl_modes.c crop_key).  The row is a copy:
    the actions it drops were never in the page's header, so nothing to remove."""
    sel = next(u32(r, 20) for r in row if u32(r, 0) == 0x10003 and pool.text(u32(r, 28)) == "MenuItem_Select")
    root = u32(row[0], 20)
    editor = next_id
    keys = {pool.find("Right"), pool.find("OK")}
    i, done = 0, 0
    while i < len(row):
        d = row[i]
        if (u32(d, 0) == 0x10006 and u32(d, 24) == sel and pool.text(u32(d, 8)) == "keyEvent"
                and u32(d, 20) in keys):
            n = u32(d, 16)
            acts = [tm.write(sel, u32(d, 28), 1, CROP_KEY_BASE + KEY_EDIT_ON), tm.focus(sel, u32(d, 28), 2, editor)]
            put(d, 16, len(acts))
            row[i + 1:i + 1 + n] = acts
            done += 1
        i += 1
    check(done == 2, "Crop row Right / OK")
    row += tm.editor(editor, root, sel, code_base=CROP_KEY_BASE)
    return next_id + 1


class EditorTemplates:
    """This page's own records the panel editor is made of."""

    def __init__(self, keys, write, focus, obj, base, pool, refs):
        self.keys, self.w, self.f, self.obj, self.base = keys, write, focus, obj, base
        self.pool, self.refs = pool, refs

    def write(self, owner, event, index, code):
        a = bytearray(self.w)
        put(a, 20, owner); put(a, 24, event); put(a, 28, index)
        _intern_at(a, 36, PANEL_KEY_VAR, self.pool, self.refs)
        _intern_at(a, WRITE_VALUE_AT, str(code), self.pool, self.refs)
        return a

    def focus(self, owner, event, index, target):
        a = bytearray(self.f)
        put(a, 20, owner); put(a, 24, event); put(a, 28, index)
        put(a, FOCUS_TARGET_AT, target)
        return a

    def editor(self, oid, parent, row, code_base=0):
        """E: no drawing, one key event per editor key, each writing its code
        (+ `code_base`: the Crop row's editor writes 10 + them); OK / MENU also hand
        focus back to the row."""
        obj, base = bytearray(self.obj), bytearray(self.base)
        put(obj, 20, oid); put(obj, 24, parent); put(obj, 16, 0); put(obj, 12, 0)
        put(base, 20, oid)
        out = [obj, base]
        for local, (key, code) in enumerate(EDITOR_KEYS, start=2):
            k = bytearray(self.keys[key])
            put(k, 24, oid); put(k, 28, local)
            acts = [self.write(oid, local, 1, code_base + code)]
            if key in ("OK", "Menu"):
                acts.append(self.focus(oid, local, 2, row))
            put(k, 16, len(acts))
            out += [k] + acts
        put(obj, 8, 1 + len(EDITOR_KEYS))
        return out


def editor_templates(recs, jump, pool, schemas, refs):
    def comps(oid):
        owner, out = None, []
        for r in recs:
            d = r.to_bytes()
            if r.tag == 0x10003:
                owner = u32(d, 20)
                if owner == oid:
                    out.append(d)
            elif owner == oid:
                out.append(d)
        return out

    keys = {}
    for oid, names in ((38159, ("Up", "Down", "Right", "OK", "Menu")), (DONOR["item"], ("Left",)),
                       (DIAL_OWNER, ("FDial_R", "FDial_L"))):
        for d in comps(oid):
            if u32(d, 0) == 0x10006 and pool.text(u32(d, 8)) == "keyEvent" and pool.text(u32(d, 20)) in names:
                keys.setdefault(pool.text(u32(d, 20)), d)
    check(set(keys) == {k for k, _ in EDITOR_KEYS}, f"editor keys {sorted(keys)}")
    write = next(d for d in comps(38181) if u32(d, 0) == 0x10009 and pool.text(u32(d, 8)) == "controlAppVariable"
                 and pool.text(u32(d, 36)) == "SoftKeyboard_InputID")
    check(pool.text(u32(write, WRITE_VALUE_AT)) == "4", "write template value")
    focus = next(d for d in comps(DONOR["item"]) if u32(d, 0) == 0x10009
                 and pool.text(u32(d, 8)) == "controlFocus" and len(d) >= FOCUS_TARGET_AT + 4
                 and u32(d, FOCUS_TARGET_AT) == DONOR["select"])
    up = comps(ARROW_UP)
    return EditorTemplates(keys, write, focus, up[0], up[1], pool, refs)


def _added_name(pool, off):
    return next(t for t, o in pool.added.items() if o == off)


# ---- the page -------------------------------------------------------------
def build_lab_page(img, pool, refs):
    if CALC_ONLY:
        import sl_lab_sidebar
        return sl_lab_sidebar.build(img, pool, refs)
    schemas = P.load_schemas(img)
    recs = N.split(base_page())
    objs = SZ.objects(recs, pool)
    for c, rows in OLD_ROWS.items():
        kids = [k for k, v in objs.items() if v["parent"] == c]
        check(all(r in kids for r in rows), f"tab {c} rows changed: {kids}")
    STEP_TM.clear()
    STEP_TM.update(step_templates(recs, pool))
    donor_sub = SZ.subtree(objs, DONOR["row"])
    d0, d1 = SZ.span(recs, objs, donor_sub, DONOR["row"])
    donor = recs[d0:d1]
    check(pool.text(u32(donor[0].to_bytes(), 28)) == DONOR_ROOT_NAME, "donor row")
    next_id = max(objs) + 1
    per_container = {}
    import os
    spec_all = rows_spec()
    if os.environ.get("SL_LAB_DIAG") == "rows":
        spec_all = diag_rows_spec(spec_all)
    for c, specs in spec_all.items():
        outs = []
        for j, spec in enumerate(specs):
            y = ROW_Y[j] if j < len(ROW_Y) else 486.0
            out, _m, next_id = clone_row(donor, donor_sub, spec, spec.get("y", y), c, pool, schemas,
                                         next_id, refs)
            outs.append(out)
        per_container[c] = outs
    moved, unbound, next_id, panel_added = output_moves(recs, objs, pool, schemas, refs, next_id)
    # OUTPUT: panel, its BG, then Squeeze, Width / Height, Binning (focus follows
    # record order).  An earlier record draws ON TOP of a later one (r24: FORMAT's
    # BG hid rows inserted after it; r30: the panel under its own BG), so the BG
    # follows the panel, as in stock.
    pic, next_id = diagram(per_container[93][0], recs, 93, pool, refs, next_id)
    per_container[93] = per_container[93] + [pic]
    if os.environ.get("SL_KEY_DIAG"):
        key_diag(per_container[92], pool)
    output_rows = per_container[OUTPUT_TAB]
    sqz, crop, rate = output_rows[:3]
    next_id = crop_editor(crop, editor_templates(recs, moved[OUTPUT_JUMP], pool, schemas, refs), pool, next_id)
    if CALC_ONLY:
        tm = editor_templates(recs, moved[OUTPUT_JUMP], pool, schemas, refs)
        row = output_rows[3]
        sel = next(u32(r, 20) for r in row if u32(r, 0) == 0x10003 and pool.text(u32(r, 28)) == "MenuItem_Select")
        i = 0
        while i < len(row):
            d = row[i]
            if u32(d, 0) == 0x10006 and u32(d, 24) == sel and pool.text(u32(d, 8)) == "keyEvent" and pool.text(u32(d, 20)) in ("Right", "OK"):
                n = u32(d, 16)
                gone = {id(a) for a in row[i + 1:i + 1 + n]}
                refs[:] = [r for r in refs if id(r[0]) not in gone]
                row[i + 1:i + 1 + n] = [tm.write(sel, u32(d, 28), 1, 21 if VIRTUAL_APPLY else 20)]
                put(d, 16, 1)
            i += 1
    caps, next_id = captions(per_container[93][0], OUTPUT_TAB, pool, refs, next_id)
    # captions first: an earlier record draws on top (over the panel's BG)
    per_container[OUTPUT_TAB] = [caps, moved[35533], moved[OUTPUT_JUMP], moved[5039], sqz, crop, rate] + output_rows[3:]
    # remove the stock rows
    drop = set()
    for c, rows in OLD_ROWS.items():
        for root in rows + OLD_EXTRA.get(c, ()):
            check(objs[root]["parent"] == c, f"{root} not in tab {c}")
            a, b = SZ.span(recs, objs, SZ.subtree(objs, root), root)
            drop.update(range(a, b))
    keep_spans = set()
    for root in OUTPUT_PANEL + (OUTPUT_JUMP,):
        a, b = SZ.span(recs, objs, SZ.subtree(objs, root), root)
        keep_spans.update(range(a, b))
        drop.update(range(a, b))
    removed = [recs[i] for i in sorted(drop - keep_spans)] + unbound
    # assemble: each container's new rows after everything it keeps (later siblings
    # draw on top: FILTER's container keeps a BG that must stay underneath)
    seq, inserted = [], set()
    after = {}
    for c in OLD_ROWS:
        a, b = SZ.span(recs, objs, SZ.subtree(objs, c), c)
        after[b] = c                                    # first record past the container
    for i, r in enumerate(recs + [None]):
        if i in after:
            for out in per_container[after[i]]:
                seq.extend(out)
            inserted.add(after[i])
        if r is None:
            break
        if i in drop:
            continue
        seq.append(bytearray(r.to_bytes()))
    check(inserted == set(OLD_ROWS), "not every container got its rows")
    tab_added, tab_removed = tab_titles(seq, per_container[92][0], pool, refs)
    if CALC_ONLY:
        t4_removed, t4_added, name_box = [], [], []
    else:
        t4_removed, t4_added, name_box = tabs4(seq, pool, refs, fresh=tab_added)
    # the NAME container and its rows go before OUTPUT's (same parent, one shown at a time)
    k101 = next(k for k, r in enumerate(seq) if u32(r, 0) == 0x10003 and u32(r, 20) == 101)
    name_rows = [x for out in per_container.get(NAME_TAB, []) for x in out]
    seq[k101:k101] = name_box + name_rows
    tab_added += t4_added + name_box
    removed = removed + [A.Record(0, bytes(x)) for x in tab_removed + t4_removed]
    kids = {}
    for d in seq:
        if u32(d, 0) == 0x10003:
            kids[u32(d, 24)] = kids.get(u32(d, 24), 0) + 1
    for d in seq:                      # every object: moves, drops and copies change them
        if u32(d, 0) == 0x10003:
            put(d, 16, kids.get(u32(d, 20), 0))
    # page-wide private variables
    for old, new in PAGE_RENAME.items():
        o = pool.find(old)
        n_off, private = pool.intern(new)
        for d in seq:
            for off, kind in P.typed_fields(bytes(d), pool, schemas):
                if kind in ("str", "text") and u32(d, off) == o:
                    put(d, off, n_off)
                    if private:
                        refs.append((d, off, new))
    # header
    header = A.parse_header(A.Record(0, recs[0].to_bytes()), pool.text)
    new_ids = {id(x) for x in panel_added}                              # copies inside the panel
    moved_ids = {id(x) for out in moved.values() for x in out if id(x) not in new_ids}   # already budgeted
    plus = [A.Record(0, bytes(x)) for outs in per_container.values() for out in outs for x in out
            if id(x) not in moved_ids]
    plus += [A.Record(0, bytes(x)) for x in tab_added]
    minus = [r if isinstance(r, A.Record) else A.Record(0, r.to_bytes()) for r in removed]
    cc = A.component_counts(plus, pool.text)
    for k, v in A.component_counts(minus, pool.text).items():
        cc[k] = cc.get(k, 0) - v
    unknown = set(cc) - set(header["component_counts"])
    check(not [k for k in unknown if cc[k] > 0], f"new component kinds {unknown}")
    cc = {k: v for k, v in cc.items() if k in header["component_counts"]}
    all_groups = [r for r in recs if r.tag == 0x1000B]
    donor_groups = [header["groups"][all_groups.index(r)] for r in donor if r.tag == 0x1000B]
    n_rows = sum(len(specs) for specs in spec_all.values())
    plus_clips = [A.parse_clip(x, pool.text) for x in plus if x.tag == 0x1000A]
    delta = {"objects": sum(1 for x in plus if x.tag == 0x10003) - sum(1 for x in minus if x.tag == 0x10003),
             "component_counts": cc, "group_budgets": donor_groups * n_rows,
             "clip_property_counts": [len(c["properties"]) for c in plus_clips],
             "property_key_counts": [len(p["keys"]) for c in plus_clips for p in c["properties"]]}
    seq[0] = bytearray(BM.extend_header(A.Record(0, recs[0].to_bytes()), header, delta))
    return seq


def check_settings_free(page, pool, schemas):
    """No field of the page names a stock frame-guide / zebra variable, and no
    word anywhere equals such a string's pool offset (first rule)."""
    bad = {o: s for s in _forbidden(pool) for o in [pool.find(s)] if o is not None}
    for r in N.split(page):
        d = r.to_bytes()
        for off, kind in P.typed_fields(d, pool, schemas):
            check(u32(d, off) not in bad, f"page still names {bad.get(u32(d, off))}")
    stray = [a for a in range(0, len(page) - 3) if u32(page, a) in bad]
    return stray


def _forbidden(pool):
    data = bytes(pool.stock)
    out, i = set(), 0
    for pre in FORBIDDEN_PREFIXES:
        i = 0
        while True:
            j = data.find(pre.encode(), i)
            if j < 0:
                break
            if data[j - 1] == 0:
                out.add(data[j:data.index(b"\0", j)].decode())
            i = j + 1
    return out


def check_page(page, pool, img):
    shape = P.page_shape(page, pool)
    h = shape["header_minus_actual"]
    base = P.page_shape(base_page(), pool)["header_minus_actual"]
    check(h["objects"] == base["objects"] and not shape["orphans"] and not shape["bad_child_counts"],
          f"object graph {h} orphans {shape['orphans'][:5]} bad {shape['bad_child_counts'][:5]}")
    check(all(v >= 0 for v in h["components"].values()) and h["groups"] >= 0 and
          all(x >= 0 for x in h["group_slots"]) and h["clips"] >= 0 and h["clip_properties"] >= 0 and
          h["keys"] >= 0, f"header below the page's needs: {h}")
    objs = shape["objects"]
    schemas = P.load_schemas(img)
    for r in N.split(page):
        d = r.to_bytes()
        for off, kind in P.typed_fields(d, pool, schemas):
            v = u32(d, off)
            if kind == "obj" and v not in (0, 0xFFFFFFFF):
                check(v in objs, f"dangling object reference {v} in tag {r.tag:#x} at {r.offset:#x}")
        if r.tag == 0x10008:
            for o in LIST_TEMPLATE_IDS:
                v = u32(d, o)
                check(v in (0, 0xFFFFFFFF) or v in objs, f"list template names missing object {v} at {o}")
    dup = duplicate_local_ids(page)
    check(not dup, f"objects with an event and a clip on one local id: {dup[:5]}")
    P.native_parse(page, pool.data, img)
    return shape


def duplicate_local_ids(page):
    """(object, id) where two of one object's events / clips share a local id."""
    owner, seen, dup = None, set(), []
    for r in N.split(page):
        d = r.to_bytes()
        if r.tag == 0x10003:
            owner, seen = u32(d, 20), set()
            continue
        loc = u32(d, 28) if r.tag == 0x10006 else u32(d, 24) if r.tag == 0x1000A else None
        if loc is None:
            continue
        if loc in seen:
            dup.append((owner, loc))
        seen.add(loc)
    return dup


if __name__ == "__main__":
    import imx410_plan as PL
    PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = True, False, False
    img = (P.ROOT / "out/MAIN_c0000000.bin").read_bytes()
    pool = P.Pool(img[U.POOL_START - P.B:U.POOL_START - P.B + U.POOL_SIZE])
    refs = []
    seq = build_lab_page(img, pool, refs)
    page, abs_refs = SZ.assemble(seq, refs)
    stray = check_settings_free(page, pool, P.load_schemas(img))
    print("stray words equal to frame-guide strings:", len(stray))
    shape = check_page(page, pool, img)
    SZ.check_refs(page, abs_refs, pool)
    print(len(page), "bytes", len(abs_refs), "refs", list(pool.added))
    for c in TAB_CONTAINERS:
        print(c, [(k, v["name"]) for k, v in shape["objects"].items() if v["parent_id"] == c])
