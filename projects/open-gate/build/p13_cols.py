#!/usr/bin/env python3
"""比對 donor profile 在幾何相關欄位的原廠值,對上這個目標實際要的幾何。"""
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import og3k_plan as P

p = P.Plan()
OFFS = [0x00,0x04, 0x0C,0x10, 0x1C, 0x20,0x24,0x28,0x2C, 0x30,
        0x80,0x84, 0x88, 0xA4, 0xB0, 0xC0, 0xCC,
        0xD8,0xDC, 0xE0,0xE4, 0xF0, 0xF4,0xF8]
NAMES = {0x00:"記錄矩陣 W",0x04:"記錄矩陣 H",0x0C:"預覽柵格 W",0x10:"預覽柵格 H",
         0x1C:"長寬比旗標",0x20:"預覽可見 W",0x24:"active W",0x28:"預覽可見 H",
         0x2C:"active H",0x30:"標稱 fps(float)",0x80:"預覽平面格式",0x84:"RAW 平面格式",
         0x88:"?",0xA4:"?",0xB0:"?",0xC0:"?",0xCC:"?",
         0xD8:"producer W",0xDC:"producer W2",0xE0:"producer H",0xE4:"producer H2",
         0xF0:"?",0xF4:"感測器視窗 W",0xF8:"感測器視窗 H"}

import struct
def col(prof, off):
    base, rows = p.profile_col(off)
    return p.word(base + rows[prof] * 4)

want = dict(P.CANVAS_REC)
print(f"目標 {P.T['label']}  donor p{P.OG_PROFILE}  rec={P.T['rec']} act={P.T['act']}")
print(f"{'off':>5} {'欄位':<18} {'p13 原廠':>12} {'p83 原廠':>12}  {'我們寫':>8}")
for o in OFFS:
    try: a = col(13, o)
    except Exception: a = None
    try: b = col(83, o)
    except Exception: b = None
    w = want.get(o)
    fa = struct.unpack('<f', struct.pack('<I', a))[0] if o == 0x30 and a is not None else a
    fb = struct.unpack('<f', struct.pack('<I', b))[0] if o == 0x30 and b is not None else b
    mark = ""
    if w is not None and a is not None and a != w: mark = "  <- 我們覆寫"
    if w is None and a is not None and a in (1344, 2016) and o in (0xDC,0xE4,0xF4,0xF8):
        mark = "  ★ 不寫,留著 p13 的值"
    print(f"{o:#05x} {NAMES.get(o,'?'):<18} {str(fa):>12} {str(fb):>12}  {str(w):>8}{mark}")
