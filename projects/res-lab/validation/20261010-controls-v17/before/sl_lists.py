#!/usr/bin/env python3
"""Sensor Lab: CUSTOM-only menu lists, as a private NBR pack.

The stock frame-rate / bit-depth lists stay exactly stock (FHD/UHD get stock
greying and no 239.76 / 14-bit rows).  Under CUSTOM the page picks these
instead (sl_excl.S writes EXCL_FrameRate = 6 / EXCL_CinemaDNGQuality = 2 and
the private page maps those frames to SL_RATE / SL_BIT):

  SL_RATE  the stock B2_5_5 nine rows + 239.76, all selectable
  SL_BIT   the stock B2_5_2 three rows + 14 bit

and the two CUSTOM rows' own lists (sl_b25_page.py, design §8.12):

  SL_MODE  statically one greyed "No matching" row; rewritten on the camera
           (sl_menu/sl_modes.c) to modes solvable at the current bit depth and
           any supported rate; FILTER FPS narrows them, "M<id>". Value = row, in the private
           MV_SLMode only (memory, never a setting).
  SL_SIZE  AUTO (= the family's raster) and two presets, until the size editor
           exists.  Not one row: no stock List has a cap of 0 (smallest 1.0,
           22 of them; scan of every stock set, 2026-10-02).

Format: identical to the stock NBR's .cvm declarations (decoded 2026-10-02 from
0xC0D22400, record 0x20001): plugin "modelCSV", one variant, property record
{0x20002, 20, 1, 1, filename}.  The lookup is by resource NAME, so the filename
only has to be unique and FNV-sorted.  Registered on the UI thread by sl_excl.S
through the stock NBR loader C05E84D8(reader, pack, bytes, 0), as OpenGate does.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / "research/ui/tools")]
import imx410_plan as PL       # noqa: E402
import nbr as NBR              # noqa: E402

RATE_NAME, BIT_NAME = "SL_RATE", "SL_BIT"
MODE_NAME, SIZE_NAME = "SL_MODE", "SL_SIZE"
RATE_INDEX, BIT_INDEX = 6, 2      # EXCL value under CUSTOM: one past the stock variants
MAGIC = NBR.MAGIC


def rate_csv(img: bytes) -> bytes:
    res = next(r for r, _d, n in PL.RATE_ROW_CSV if n == "B2_5_5")
    saved = PL.WITH_RATE_ALL_OPEN
    PL.WITH_RATE_ALL_OPEN = True
    try:
        csv = PL.rate_row_csv(img, res)
    finally:
        PL.WITH_RATE_ALL_OPEN = saved
    return csv


def bit_csv(img: bytes) -> bytes:
    res = next(r for r, _d, n in PL.BIT_ROW_CSV if n == "B2_5_2")
    return PL.bit_row_csv(img, res)


MODE_ROWS_MAX = 70                 # the registry's sensor modes: the page's cursor pairs


def mode_rows() -> list[dict]:
    """The MODE popup as the PAGE sees it: up to 70 rows.  Their contents are
    written on the camera (sl_menu/sl_modes.c: the modes the recipe can solve
    at the current bit depth and any supported rate, narrowed by FILTER FPS,
    "M<id>"); the collapsed summary
    shows the row number until it is made dynamic too (step 2)."""
    return [dict(summary=str(i + 1)) for i in range(MODE_ROWS_MAX)]


def lab_mode_rows() -> list[dict]:
    """The lab page's MODE row: 70 row slots, blank summaries (SL_M_Text is the
    summary), texts written on the camera."""
    return [dict(text=" ", summary=" ") for _ in range(MODE_ROWS_MAX)]


# The static SL_MODE: what stock parses, and what stays if the camera-side
# rewrite fails -- one greyed row, safe and recognisable.
MODE_STATIC = (dict(text="No matching", summary="", enabled=(0, 0)),)


SIZE_ROWS = (dict(text="AUTO", summary="AUTO"),
             dict(text="3840x2160", summary="3840x2160"),
             dict(text="1920x1080", summary="1920x1080"))


# ---- the SIZE sub page (sl_size_page.py), static for now -----------------
# summaries show the stock row numbers ("1".."8"): each private summary string
# would cost boot time (fp-native-ui section 8e)
SCALE_NAME, WH_NAME, BIN_NAME, RWZM_NAME = "SL_SCALE", "SL_WH", "SL_BINS", "SL_RWZM"


def _numbered(texts):
    return tuple(dict(text=t, summary=str(i + 1)) for i, t in enumerate(texts))


def _titled(texts):
    """The summary is the option itself ("3:2", the user 2026-10-03).  Each text
    the stock pool lacks is a private string; the installer adds them all in
    one batch (uis_intern_many: one cache-clean pair, no stock scan)."""
    return tuple(dict(text=t, summary=t) for t in texts)


# OUTPUT's ratio row (the user 2026-10-03: "幾比幾", and it really holds W:H --
# sl_modes.c ratio_of(); the order is its row numbers).  A ratio and an
# anamorphic squeeze are one choice ("只能擇一"): AUTO = the readout's shape,
# RAW = the largest the binning gives, Nx = AUTO with the width stretched N
# (desqueezed in camera).  The W:H rows are the widescreen ones (3:2 / 16:9 /
# 17:9 went, the user 2026-10-03).  Kept on the SL_SCALE list / MV_SLScale.
SCALE_ROWS = _titled(("AUTO", "RAW", "1.85:1", "2:1", "2.35:1", "2.39:1", "2.40:1", "2.76:1",
                      "1.25x", "1.33x", "1.5x", "1.55x", "1.6x", "1.65x", "1.8x", "2.0x", "Free"))
# OUTPUT's Data rate row: which rate the MB/s is for (sl_modes.c rate_post: 0 =
# the frame-rate setting, k = rate_index k - 1; the user 2026-10-03: "every
# rate's result").  The summary is SL_O_Rate's text, so these summaries are blank.
RATE_SEL_NAME = "SL_RFPS"
RATE_SEL_ROWS = tuple(dict(text=t, summary=" ") for t in (
    "Setting", "23.98p", "24p", "25p", "29.97p", "48p", "50p", "59.94p", "100p", "119.88p", "239.76p"))
# NAME's Preset row: which of the four CUSTOM presets the tab shows / saves
# (the user 2026-10-03: CUSTOM1, CUSTOM2 ... told apart by a name, kept on SD)
N_PRESET_NAME = "SL_N_PRESET"
N_PRESET_ROWS = _titled(("CUSTOM1", "CUSTOM2", "CUSTOM3", "CUSTOM4"))
# OUTPUT's Crop row edits in place (sl_lab_page.crop_editor): its list is never
# opened; two blank rows (no stock list has a cap of 0)
CROP_O_NAME = "SL_O_CROP"
CROP_O_ROWS = (dict(text=" ", summary=" "), dict(text=" ", summary=" "))
SIDEBAR_LISTS = {
    SCALE_NAME: _titled(('AUTO restore', 'Keep native', 'Custom W/H')),
    'SL_LOCK': _titled(('Free crop', 'Keep shape')),
    'SL_LENS': _titled(('Off', 'On')),
}
WH_ROWS = _numbered(("AUTO", "3840x2160", "1920x1080"))
BIN_ROWS = _numbered(("1 x 1", "3 x 1", "5 x 1", "1 x 3", "3 x 3", "5 x 3"))
RWZM_ROWS = _numbered(("W 1.00 / H 1.00", "-"))         # display only; two rows: no stock list has a cap of 0


# ---- the Sensor Lab page (sl_lab_page.py): FILTER tab, MODE placeholder --
F_BIT_NAME, F_FPS_NAME, F_WIDTH_NAME, F_PROP_NAME, M_PH_NAME = (
    "SL_F_BIT", "SL_F_FPS", "SL_F_WIDTH", "SL_F_PROP", "SL_M_PH")
F_BIT_ROWS = _titled(("Any", "12-bit (8/10/12)", "14-bit"))
# "N+" = at least N.  Not ">= N": the stock text renderer reads <...> as markup
# (<!font_G_minus,CENTER>); r24 / r26 lost the camera (UI and USB shell) right
# after focusing these two rows, the only lists with a bare '>'.
F_FPS_ROWS = _titled(("Any", "23.98p+", "24p+", "25p+", "29.97p+", "48p+", "50p+",
                        "59.94p+", "100p+", "119.88p+", "239.76p+"))
F_WIDTH_ROWS = _titled(("Any", "1920+", "2048+", "3840+", "4096+", "6064+"))
F_PROP_ROWS = _titled(("Any", "3:2", "16:9", "1.85:1", "2:1", "2.39:1"))
# the sensor area a mode covers (raster x reduction), by its width: Full frame
# 6048-6064 (35.9 mm; M95's 5712 = 33.8 mm counted with it), Super35 4176
# (24.7 mm), APS-C 3968 x 2640 (23.5 x 15.6 mm) -- the user 2026-10-03
F_CROP_NAME = "SL_F_CROP"
F_CROP_ROWS = _titled(("Any", "Full frame", "Super35", "APS-C"))
M_PH_ROWS = _titled(("AUTO", "(mode list: next step)"))
import os as _os
if _os.environ.get("SL_LAB_DIAG") == "rows":          # diagnostic card: a 5-item list
    F_PROP_ROWS = F_PROP_ROWS[:5]


def rows_csv(rows, lab: bool = False) -> bytes:
    """Same shape as the stock lists: UTF-8 BOM, CRLF after every line (the last
    one too, or it is not parsed -- skill fp-native-ui section 2).  `lab`: the
    lab page's donor list's own columns (B5_4_1_01.cvm: Popup "xx", an IMAGE
    column) -- its ListItem draws a ListIcon from IMAGE; r23 froze on opening a
    lab popup whose list had none."""
    en = lambda r: r.get('enabled', (1, 2))
    if lab:
        lines = ["NO,TEXT,Popup,IMAGE,Enabled,Enabled2"]
        lines += [f"{i},{r['text']},xx,blank,{en(r)[0]},{en(r)[1]}" for i, r in enumerate(rows, 1)]
    else:
        lines = ["NO,TEXT,Popup,Enabled,Enabled2"]
        lines += [f"{i},{r['text']},Popup,{en(r)[0]},{en(r)[1]}" for i, r in enumerate(rows, 1)]
    for r in rows:
        if "," in r["text"] or not r["text"].isascii() or set("<>") & set(r["text"]):
            raise ValueError(f"row text {r['text']!r}")
    return b"\xef\xbb\xbf" + ("\r\n".join(lines) + "\r\n").encode()


def build_pack(img: bytes, rows: bool = True, calc: bool = False) -> bytes:
    """The private NBR: modelCSV resources (with `rows`: SL_MODE / SL_SIZE too)."""
    items = [] if calc else [(RATE_NAME, rate_csv(img)), (BIT_NAME, bit_csv(img))]
    if rows:
        # SL_MODE in the lab list's columns: the lab MODE row's (sl_modes.c
        # writes the same six)
        items += [(MODE_NAME, rows_csv(MODE_STATIC, lab=True)), (SIZE_NAME, rows_csv(SIZE_ROWS))]
        # the lab page's lists (sl_lab_page.rows_spec), in its donor list's columns
        items += [(n, rows_csv(r, lab=True)) for n, r in (
            (SCALE_NAME, SCALE_ROWS), (WH_NAME, WH_ROWS), (BIN_NAME, BIN_ROWS), (RWZM_NAME, RWZM_ROWS),
            (F_BIT_NAME, F_BIT_ROWS), (F_FPS_NAME, F_FPS_ROWS), (F_WIDTH_NAME, F_WIDTH_ROWS),
            (F_PROP_NAME, F_PROP_ROWS), (F_CROP_NAME, F_CROP_ROWS), (RATE_SEL_NAME, RATE_SEL_ROWS),
            (CROP_O_NAME, CROP_O_ROWS), (N_PRESET_NAME, N_PRESET_ROWS))]
    if calc:
        items = [(n, rows_csv(SIDEBAR_LISTS[n], lab=True) if n in SIDEBAR_LISTS else d) for n,d in items]
        items += [(n, rows_csv(r,lab=True)) for n,r in SIDEBAR_LISTS.items() if n != SCALE_NAME]
        items = [(n, d) for n, d in items if n not in (SIZE_NAME, WH_NAME, BIN_NAME, RWZM_NAME, N_PRESET_NAME)]
        # Calculator defaults to its own 23.98p input, never to a camera setting.
        items = [(n, rows_csv((dict(text="23.98p", summary=" "),) + RATE_SEL_ROWS[1:], lab=True) if n == RATE_SEL_NAME else d) for n, d in items]
    pool = bytearray(4)
    offs: dict[str, int] = {}

    def intern(v: str) -> int:
        if v not in offs:
            offs[v] = len(pool)
            pool.extend(v.encode() + b"\0")
            pool.extend(bytes((-len(pool)) % 4))
        return offs[v]

    for name, _ in items:
        intern("modelCSV"); intern(name); intern(f"{name}.cvm")
    out = bytearray(MAGIC)
    out += struct.pack(">II", 1, 8 + len(pool)) + pool
    table = len(out)
    out += bytes(12 + 16 * len(items))
    files = []
    for name, data in items:
        fn = f"{name}.cvm"
        files.append((NBR.fnv1a(fn), intern(fn), len(out), len(data)))
        out += data + bytes((-len(data)) % 4)
    struct.pack_into(">III", out, table, 2, len(out) - table, len(items))
    for i, e in enumerate(sorted(files)):
        struct.pack_into(">4I", out, table + 12 + 16 * i, *e)
    decl = len(out)
    out += struct.pack(">4I", 0x20001, 16 + 36 * len(items), len(items), len(items))
    defs = len(out)
    out += bytes(36 * len(items))
    out += struct.pack(">II", 0xFFFFFFFF, 8)
    for i, (name, _) in enumerate(items):
        prop = len(out)
        struct.pack_into(">9I", out, defs + 36 * i, intern(name), intern("modelCSV"), 0,
                         0xFFFFFFFF, 0, 1, 0xFFFFFFFF, 0xFFFFFFFF, prop)
        out += struct.pack(">5I", 0x20002, 20, 1, 1, intern(f"{name}.cvm"))
    out += struct.pack(">II", 0xFFFFFFFF, 8)
    return bytes(out)


def inspect_pack(pack: bytes) -> dict:
    """Bounds/consistency check of a modelCSV pack (nbr.inspect assumes xcimage props)."""
    u = lambda o: struct.unpack_from(">I", pack, o)[0]
    assert pack.startswith(MAGIC)
    pool_end = 12 + u(16)
    s = lambda o: pack[20 + o:pack.index(b"\0", 20 + o)].decode()
    table = pool_end
    assert u(table) == 2
    n = u(table + 8)
    files = {}
    keys = []
    for i in range(n):
        k, no, do, ln = struct.unpack_from(">4I", pack, table + 12 + 16 * i)
        assert k == NBR.fnv1a(s(no)) and do + ln <= table + u(table + 4)
        files[s(no)] = pack[do:do + ln]
        keys.append(k)
    assert keys == sorted(keys)
    decl = table + u(table + 4)
    tag, total, cnt, var = struct.unpack_from(">4I", pack, decl)
    assert tag == 0x20001 and total == 16 + 36 * cnt and cnt == var == n
    out = {}
    for i in range(cnt):
        f = struct.unpack_from(">9I", pack, decl + 16 + 36 * i)
        prop = struct.unpack_from(">5I", pack, f[8])
        assert s(f[1]) == "modelCSV" and f[5] == 1 and prop[:4] == (0x20002, 20, 1, 1)
        out[s(f[0])] = files[s(prop[4])]
    return out


if __name__ == "__main__":
    img = PL.FIRMWARE.read_bytes()
    pack = build_pack(img)
    got = inspect_pack(pack)
    print(len(pack), "bytes")
    for k, v in got.items():
        print(k); print(v.decode("utf-8-sig"))
