#!/usr/bin/env python3
"""Loader v4's UI data files (FT4S): the home page \\fpSup\\UI\\FPSUP.BIN, and
the generic writer a sup's own pages use (fpSup/fpsup-ui).

    python3 -B fpSup/uishare/tab/build_fp4.py [-o DIR]     # DIR/FPSUP.BIN, DIR/SUPMGR.BIN

Format: fpSup/fpsup-ui/fpsup_ui.c struct fpui_file -- v3's FT6 data file
(build_ft6.data_file) without the allsups-specific words, plus a first value
for every variable.  The private strings are a table of offsets to text the
file already holds; fpsup-ui gives each reference the string's own address as
its id when the file is installed -- no uishare layers, no copies, no search,
no limits (the user, 2026-10-21):

    [header][strings, texts, variable names][string table][refs][vars]
    [image pack][NBR page pack]           (the page pack last, as in v3)

Design: projects/loader-v4/DESIGN.md §14.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_ft6 as FT                      # noqa: E402  (sets sys.path for the rest)
import nbr as NBR                           # noqa: E402
import sl_pages as SL                       # noqa: E402

FT4_MAGIC = 0x53345446                      # "FT4S": strings as a table (no FPUI blocks)
HEADER_WORDS = 17                           # fpSup/fpsup-ui/fpsup_ui.c struct fpui_file
VAR_INT, VAR_TEXT = FT.VAR_INT, FT.VAR_TEXT
HOME_MACHINE = FT.MACHINE                   # "TransFtTab"
HOME_PAGE = FT.PAGE                         # "FT_Y6", SYSTEM's sixth page
HOME_TABS = 7                               # fpsup_home.c HOME_TABS = manage_page.PAGE_TABS
HOME_SLOTS = FT.VISIBLE + 1                 # fpsup_home.c HOME_SLOTS: slot 0 .. 5
HEADER_FOCUS = 3451
GROUPS = ('N', 'A', 'Ia', 'Ib', 'Ic', 'Visible', 'Lock', 'Default', 'Choice', 'Max', 'PopH', 'Jump',
          'Tog', 'TOff', 'TOn')        # fpsup_home.c G_TOG..G_TON: a TOGGLE's stock Off / On
TEXT_GROUPS = {'N', 'A', 'Ia', 'Ib', 'Ic'}
from home4_page import GO_TEXT, GO_VAR     # noqa: E402  (a JUMP row's request, fpsup_home.c T_GO / V_GO)
HOME_TEXTS = (' ', FT.NATIVE_ENGLISH['Footer01'], FT.NATIVE_ENGLISH['Footer05'],
              '<!font_G_bt_rightleft_K153,CENTER>Page<!28sp,CENTER><!font_G_bt_menu_K153,CENTER>Back',
              'Loader v4', 'Off', 'On', GO_TEXT)    # fpsup_home.c T_BLANK .. T_GO


def open_transitions(*pages):
    """A sup pack's way in from the fpSup page: the row's request names the page
    (fpsup-ui fpui_open), so FT_Y6 -> page on request = page."""
    return tuple((HOME_PAGE, p, p) for p in pages)


def slot_var(group, k):
    """home4_page's names: FT_N1, FT_I1a, FT_Visible1 ..."""
    if group.startswith('I') and len(group) == 2:
        return f'FT_I{k}{group[1]}'
    return f'FT_{group}{k}'


def home_vars(row0=0):
    """(type, name, first value) in fpsup_home.c's V_ order; a text's first
    value is one of HOME_TEXTS (the core writes the real ones at boot).
    FT_Row0 is bound to nothing: its first value tells the core slot 0's
    focus id (home4_page.build_home)."""
    out = [(VAR_INT, 'FT_Key', 0), (VAR_TEXT, 'FT_OK', HOME_TEXTS[1]), (VAR_TEXT, 'FT_PageText', ' '),
           (VAR_TEXT, 'FT_Version', 'Loader v4'), (VAR_INT, 'FT_Focus', HEADER_FOCUS),
           (VAR_INT, 'FT_Title', 1), (VAR_INT, 'FT_Row0', row0), (VAR_INT, 'FT_HeadOn', 0)]
    for g in GROUPS:
        for k in range(HOME_SLOTS):
            out.append((VAR_TEXT, slot_var(g, k), ' ') if g in TEXT_GROUPS else
                       (VAR_INT, slot_var(g, k), 255 if g == 'Choice' else 0))
    for part in ('TabVisible', 'TabActive', 'TabX', 'TabWidth'):
        for k in range(1, HOME_TABS + 1):
            out.append((VAR_INT, f'FT_{part}{k}', 0))
    return out


def home_file_vars(row0=0):
    """FPSUP.BIN's variables: home_vars(), then GO_VAR (fpsup_home.c V_GO)."""
    return home_vars(row0) + [(VAR_INT, GO_VAR, 0)]


def ft4_file(pages, trans, machine, variables, texts, logo_pack=b''):
    """One FT4P file: `pages` = [(name, (page bytes, refs))], `variables` =
    [(type, name, first value)] (a text's value is a string), `texts` the
    fixed strings the code indexes."""
    pack = FT.build_pack([(n, p[0]) for n, p in pages], machine=machine, trans=trans)
    rows = {n: o for n, o, _h in SL.native_rows(pack)}
    refs = [(rows[n] + o, t) for n, (_p, rs) in pages for o, t in rs]
    strings = list(dict.fromkeys(t for _o, t in refs))
    out = bytearray(4 * HEADER_WORDS)
    out += b'\0' * (-len(out) % 8)

    def place(data, align=4):
        nonlocal out
        out += b'\0' * (-len(out) % align)
        at = len(out)
        out += data
        return at
    pooled = {}

    def text_at(s):
        if s not in pooled:
            pooled[s] = place(s.encode() + b'\0', 1)
        return pooled[s]
    strs_off = place(b''.join(struct.pack('<I', text_at(t)) for t in strings))
    txt = [text_at(t) for t in texts]
    texts_off = place(b''.join(struct.pack('<I', t) for t in txt))
    var_rows = []
    for ty, name, first in variables:
        n = place(name.encode() + b'\0', 1)
        var_rows.append((ty, n, text_at(first) if ty == VAR_TEXT else first))
    refs_off = place(b''.join(struct.pack('<II', o, strings.index(t)) for o, t in refs))
    vars_off = place(b''.join(struct.pack('<3I', *v) for v in var_rows))
    logo_off = place(logo_pack, 8) if logo_pack else 0
    pack_off = place(pack, 8)
    hdr = struct.pack('<13I', FT4_MAGIC, pack_off, len(pack), strs_off, len(strings),
                      len(refs), refs_off, len(variables), vars_off, logo_off, len(logo_pack),
                      texts_off, len(texts))
    hdr += machine.encode().ljust(12, b'\0')[:12]
    hdr += struct.pack('<I', len(out))
    assert len(hdr) == 4 * HEADER_WORDS
    out[:len(hdr)] = hdr
    return bytes(out), {'pack': len(pack), 'strings': strings, 'refs': len(refs), 'file': len(out),
                        'pages': {n: len(p[0]) for n, p in pages}}


def home_file():
    """\\fpSup\\UI\\FPSUP.BIN: FT_Y6, its neighbours MainY5 / MainB1 (v3's)."""
    import ft6_page as FP
    import home4_page as H
    import manager_logo
    img = (FT.ROOT / 'out/MAIN_c0000000.bin').read_bytes()
    if SL.gui_id(img, FT.BASE) != FT.GUI_ID:
        raise SystemExit(f'{FT.BASE} GUI id is not {FT.GUI_ID}')
    _img, pool = FP.stock_pool()
    page, refs, row0 = H.build_home(img, pool)
    logo = NBR.build([NBR.Resource(name, name + '.xci', blob) for name, _c, blob in manager_logo.images()])
    return ft4_file([(HOME_PAGE, (page, refs))], FT.TRANSITIONS, HOME_MACHINE,
                    home_file_vars(row0), HOME_TEXTS, logo)


SUPMGR_MACHINE = 'TransSmTab'
SUPMGR_PAGE = 'FT_LIST'
# a paged list's one footer (supmgr.c / ogc_files.c T_PAGE_HINT): never switched, since
# each redraw of an icon footer costs ~55 ms (camera, 2026-10-25)
SUPMGR_PAGED_FOOTER = ('<!font_G_bt_ok_K153,CENTER>OK<!28sp,CENTER>' + HOME_TEXTS[3])
SUPMGR_TEXTS = (' ', 'Unload on restart', 'Load on restart', 'Load failed', 'Write failed',
                FT.NATIVE_ENGLISH['Footer01'], FT.NATIVE_ENGLISH['Footer05'], SUPMGR_PAGED_FOOTER,
                'Loader v4', SUPMGR_PAGE)     # supmgr.c T_BLANK .. T_PAGE


def sm_name(name):
    return 'SM_' + name[3:]


def supmgr_extra(row0=0):
    """After v3's: slot 0 (under the title row: six sups or fewer do not
    page), then FT_Title, FT_Row0 (slot 0's focus id), FT_HeadOn, then
    FT_TOff0..5, FT_TOn0..5, FT_GShow0..5, FT_RShow0..5 -- supmgr.c V_X0 onwards, in this order."""
    import manage_page as MP
    return ([(VAR_TEXT, MP.var(p, 0)) for p in FT.VAR_PARTS] +
            [(VAR_INT, MP.var(p, 0)) for p in ('Visible', 'Lock', 'Selected', 'More', 'Default', 'Choice',
                                              'VersionX')] +
            [(VAR_INT, 'FT_Title'), (VAR_INT, 'FT_Row0'), (VAR_INT, 'FT_HeadOn')] +
            # the stock On / Off in the right column (manage_page native rows), slots 0..5
            [(VAR_INT, MP.var(g, k)) for g in ('TOff', 'TOn', 'GShow', 'RShow') for k in range(FT.VISIBLE + 1)])


def supmgr_vars(row0=0):
    """v3 build_ft6.variables() (allsups.c's indices, kept by supmgr.c) and
    supmgr_extra(), with SM_ for FT_ so they do not meet the home page's."""
    out = []
    for ty, name in FT.variables() + supmgr_extra():
        first = (' ' if ty == VAR_TEXT else 255 if name.startswith('FT_Choice')
                 else HEADER_FOCUS if name == 'FT_Focus' else 1 if name == 'FT_Title'
                 else row0 if name == 'FT_Row0' else 0)
        out.append((ty, sm_name(name), first))
    return out


def supmgr_file():
    """\\fpSup\\UI\\SUPMGR.BIN: v3's management page FT_LIST, its variables
    renamed SM_; MENU goes back to the fpSup page.  The logo images are the
    home page's (FPSUP.BIN registers them)."""
    import ft6_page as FP
    import manage_page as MP
    img = (FT.ROOT / 'out/MAIN_c0000000.bin').read_bytes()
    _img, pool = FP.stock_pool()
    page, refs, row0 = MP.build_manage(img, pool, v4=True)
    names = {n for _t, n in FT.variables() + supmgr_extra()}
    refs = [(o, sm_name(t) if t in names else t) for o, t in refs]
    return ft4_file([(SUPMGR_PAGE, (page, refs))], ((SUPMGR_PAGE, HOME_PAGE, 'Return'),) + open_transitions(SUPMGR_PAGE),
                    SUPMGR_MACHINE, supmgr_vars(row0), SUPMGR_TEXTS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-o', type=Path, default=HERE / 'out', help='directory: FPSUP.BIN, SUPMGR.BIN')
    a = ap.parse_args()
    a.o.mkdir(parents=True, exist_ok=True)
    for name, make in (('FPSUP.BIN', home_file), ('SUPMGR.BIN', supmgr_file)):
        data, info = make()
        (a.o / name).write_bytes(data)
        print(a.o / name, {k: v for k, v in info.items() if k != 'strings'})


if __name__ == '__main__':
    main()
