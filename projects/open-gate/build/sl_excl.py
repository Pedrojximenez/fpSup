"""Sensor Lab CUSTOM-only lists: the notifier hooks (sl_excl.S) and their state.

Only built into a --b25-menu card (imx410_plan.WITH_SL_EXCL).  Each hook site
is a stock `push {r4, r5, r6, lr}` (E92D4070), checked before arming.
"""
from pathlib import Path
import struct
from armasm import assemble
import imx410_bit14 as BIT14

WITH_BIT14 = True          # imx410_bit14: 14-bit as a RAM marker (setting stays 12)

B = 0xC0000000
MARK = 0xC0730380             # sl_menu/build_sl_menu.MARK; layout in sl_excl.S (M_*)
MARK_BYTES = 0x58           # +0x50: sl_menu_ui, +0x54: sl_menu_live (both from the launcher)
RATE_INDEX, BIT_INDEX = 6, 2  # sl_lists
PROLOGUE = 0xE92D4070         # push {r4, r5, r6, lr}
PAGE_SITE, PAGE_PROLOGUE = 0xC05E82F0, 0x48F0E92D   # Thumb push.w {r4-r7, fp, lr}
HOOKS = (  # (site, code, what) -- ARM sites, B
    (0xC059B2F8, 0xC0731310, 'EXCL_FrameRate notifier: SL_RATE under CUSTOM'),
    (0xC059BA10, 0xC0731510, 'EXCL_CinemaDNGQuality notifier: SL_BIT under CUSTOM'),
    (0xC05931D0, 0xC0730B80, 'MV_Resolution notifier: re-apply the two'),
    (0xC059C640, 0xC0730BB8, 'LV_Resolution notifier (standby): re-apply'),
    (0xC059C9F0, 0xC0731C50, 'LV_Resolution notifier (standby 2): re-apply'),
)
READY = 0xC0730260            # ROLE 6, custom_ready (no site); READY+8 = the page parser's entry
                              # (moved from 0xC0731AB0 when it outgrew 0xC8 B, 2026-10-02)
REAPPLY = 0xC0731968          # ROLE 8, reapply both variables (no site)
AFTER = 0xC0731B78            # ROLE 11, after a resolution change: 14 -> 12 off CUSTOM, then ROLE 8
SETTER_PROLOGUE = 0xE92D40F0  # push {r4, r5, r6, r7, lr}
SETTER_HOOKS = (  # (site, code, what) -- the MV_Resolution GUI setter callbacks
    (0xC057A6A0, 0xC07309C8, 'MV_Resolution setter (movie record): reapply CUSTOM lists'),
    (0xC05824D0, 0xC0731CC0, 'MV_Resolution setter (Settings page): reapply CUSTOM lists'),
)
# ROLE 12/13: continuations of imx410_rate_native ROLE 6/7 (the MV_FrameRate
# callbacks are its sites); ROLE 14: the MV_DNGQuality callback, our site.
LIVE_TARGETS = {6: 0xC0731ED8, 7: 0xC0731F28}   # rate_native role -> our wrapper
DNG_SITE, DNG_CODE = 0xC057A5F0, (0xC0734F40 if WITH_BIT14 else 0xC0732080)   # with bit14: source-only (imx410_plan.SOURCE_ONLY)
# ROLE 15: the GUI page-id lookup's only call site (bl FUN_c0564638 in FUN_c05645e8).
GUI_SITE, GUI_SITE_STOCK, GUI_CODE = 0xC056461C, 0xEB000005, 0xC0732960
PAGE_CODE = 0xC0731AB0        # ROLE 7, the page parser (Thumb site, B.W); READY's old slot
                              # (0xC0731ED8 had 0xA8 B before the forbidden 0xC0731F80)
LIMITS = {1: 0xF0, 2: 0xF0, 3: 0x38, 4: 0x48, 5: 0x6C, 6: 0x118, 7: 0xC8, 8: 0x98, 9: 0x38, 10: 0x40, 11: 0x88,
          12: 0x50, 13: 0x50, 14: 0x100 if WITH_BIT14 else 0x50, 15: 0x40}


_gui_parent = None


def gui_parent():
    """GUI id the private pages borrow (sl_pages.gui_parent_id), from the image."""
    global _gui_parent
    if _gui_parent is None:
        import sl_pages
        import imx410_plan as PL
        img = PL.FIRMWARE.read_bytes()
        _gui_parent = sl_pages.gui_parent_id(img, [(n, b"", p) for n, _pg, p in
                                                    [("SL_TEST", None, "B2_5")]])
    return _gui_parent


# Loader v3 (build_v3_reslab.py): ROLE 15's site is shared (CHAIN); a page that is
# not ours goes to the word at GUI_NEXT, which the entry fills from
# svc->chain_next().  The second-to-last word of the v3 layout (the last is
# CORE_MAGIC); not in any region of the AutoRun card.
GUI_NEXT = 0xC0737FF8


def defines(role):
    import os
    v3 = os.environ.get("OG_V3") == "1"
    return [f'ROLE={role}', *( [f'GUI_PARENT={gui_parent()}'] if role == 15 else []),
            *([f'GUI_NEXT={GUI_NEXT:#x}'] if role == 15 and v3 else []), f'MARK={MARK:#x}', f'RATE_INDEX={RATE_INDEX}', f'BIT_INDEX={BIT_INDEX}',
            f'READY={READY:#x}', f'REAPPLY_CODE={REAPPLY:#x}', f'AFTER_CODE={AFTER:#x}',
            *([f'BIT14={BIT14.BIT14:#x}', f'BIT_PAIR={BIT14.BIT_PAIR:#x}',
               f'PENDING={BIT14.PENDING:#x}', f'NOTIFY_CODE={BIT14.NOTIFY_CODE:#x}',
               *(['WITH_NOTIFY=1'] if BIT14.WITH_NOTIFY else [])]
              if role == 14 and WITH_BIT14 else [])]


def payloads():
    src = str(Path(__file__).with_suffix('.S'))
    return [(f'sl_excl_{role}', src, code) for role, (_, code, _) in enumerate(HOOKS, 1)] + \
        [('sl_excl_6', src, READY), ('sl_excl_7', src, PAGE_CODE), ('sl_excl_8', src, REAPPLY)] + \
        [(f'sl_excl_{9 + i}', src, code) for i, (_, code, _) in enumerate(SETTER_HOOKS)] + \
        [('sl_excl_11', src, AFTER)] + \
        [('sl_excl_12', src, LIVE_TARGETS[6]), ('sl_excl_13', src, LIVE_TARGETS[7]),
         ('sl_excl_14', src, DNG_CODE), ('sl_excl_15', src, GUI_CODE)]


def blobs():
    out = {name: assemble(src, defines=defines(int(name.rsplit('_', 1)[1])))
           for name, src, _ in payloads()}
    for name, blob in out.items():
        role = int(name.rsplit('_', 1)[1])
        limit = LIMITS[role]
        if len(blob) > limit:
            raise ValueError(f'{name} is {len(blob)} bytes, slot {limit}')
    return out


def _b(site, target):
    delta = target - site - 8
    if delta % 4 or not -(1 << 25) <= delta < (1 << 25):
        raise ValueError('branch out of range')
    return 0xEA000000 | ((delta >> 2) & 0xFFFFFF)


def _bl(site, target):
    delta = target - site - 8
    if delta % 4 or not -(1 << 25) <= delta < (1 << 25):
        raise ValueError('branch out of range')
    return 0xEB000000 | ((delta >> 2) & 0xFFFFFF)


def _bw(site, target):
    """Thumb B.W (T4) at site -> target (target in Thumb state)."""
    off = target - (site + 4)
    if off % 2 or not -(1 << 24) <= off < (1 << 24):
        raise ValueError('B.W out of range')
    s = (off >> 24) & 1
    i1, i2 = (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (~(i1 ^ s)) & 1, (~(i2 ^ s)) & 1
    h1 = 0xF000 | (s << 10) | ((off >> 12) & 0x3FF)
    h2 = 0x9000 | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7FF)
    return h1 | (h2 << 16)                     # little-endian word: first halfword low


def patches(img):
    out = []
    for site, code, what in HOOKS:
        if struct.unpack_from('<I', img, site - B)[0] != PROLOGUE:
            raise ValueError(f'{what}: {site:#x} is not the stock prologue')
        out.append((site, _b(site, code), what))
    for site, code, what in SETTER_HOOKS:
        if struct.unpack_from('<I', img, site - B)[0] != SETTER_PROLOGUE:
            raise ValueError(f'{what}: {site:#x} is not the stock prologue')
        out.append((site, _b(site, code), what))
    if struct.unpack_from('<I', img, DNG_SITE - B)[0] != SETTER_PROLOGUE:
        raise ValueError('MV_DNGQuality callback C057A5F0 is not the stock prologue')
    out.append((DNG_SITE, _b(DNG_SITE, DNG_CODE), 'MV_DNGQuality setter: MODE list follows the bit depth'))
    if struct.unpack_from('<I', img, GUI_SITE - B)[0] != GUI_SITE_STOCK:
        raise ValueError('C056461C is not the stock bl FUN_c0564638')
    out.append((GUI_SITE, _bl(GUI_SITE, GUI_CODE), 'GUI page id: SL_ pages borrow their parent\'s'))
    if struct.unpack_from('<I', img, PAGE_SITE - B)[0] != PAGE_PROLOGUE:
        raise ValueError('page parser C05E82F0 is not the stock push.w')
    out.append((PAGE_SITE, _bw(PAGE_SITE, PAGE_CODE), 'page parser: CUSTOM lists before a page is built'))
    return out


def state_words():
    """Loader-time initial state, before the installer and any notifier:
    everything 0 except the two 'last seen' states (-1 = never)."""
    w = [0] * (MARK_BYTES // 4)
    for off in (0x20, 0x24, 0x3C, 0x40):    # last states, saved stock values: none
        w[off // 4] = 0xFFFFFFFF
    return [(MARK + 4 * i, v, 'sl_excl state') for i, v in enumerate(w)]
