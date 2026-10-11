#!/usr/bin/env python3
"""快速切換 og3kpbsel 回傳的表項 = 切換回放走哪一條管線。

    ./pbsel_try.py            列出候選與現值
    ./pbsel_try.py 0xC0BE5690 換成那一筆
    ./pbsel_try.py 0          不介入(完全原廠行為)
"""
import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from putfile import mem_get, mem_set

ENT, LOG = 0xC0732390, 0xC0732380
CAND = [
    (0x00000000, "不介入(原廠回放管線 +0x4CC/4F0/514)", ""),
    (0xC0BE5D20, '{1, p43, 98, "12BLOW"}   柵格 2024x1341', "+0x268 照片(已試:有結構但斑點)"),
    (0xC0BE5690, '{4, p331, 106, "FHD30"}  柵格 3032x1708', "+0x538 WithRaw ★寬度正好 3032"),
    (0xC0BE5BC0, '{5, p175, 106, "FHD30"}  柵格 1936x1090', "+0x460 錄影管線"),
    (0xC0BE4C50, '{1, p29, ?, "MAG4"}      柵格 6064x2022', "+0x340 家族"),
    (0xC0BE5610, '{4, p321, 7, "UHD30"}    柵格 3888x2184', "+0x484/4A8"),
]

def rd(a, n=1):
    for _ in range(8):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return w
    raise SystemExit(f"讀不到 0x{a:08X}")

def wr(a, v):
    for _ in range(10):
        if rd(a)[0] == v:
            return True
        mem_set(a, v)
    return rd(a)[0] == v

cur = rd(ENT)[0]
if len(sys.argv) > 1:
    v = int(sys.argv[1], 0)
    if not wr(ENT, v):
        raise SystemExit("寫入失敗")
    wr(LOG, 0); wr(LOG + 4, 0)
    print(f"  表項 → 0x{v:08X}   計數器已歸零")
    cur = v
else:
    print(f"  現值 0x{cur:08X}")
    h = rd(LOG, 2)
    print(f"  命中 {h[0]} / mode5 {h[1]}")
print("\n  候選:")
for v, what, pipe in CAND:
    mark = " ←現在" if v == cur else ""
    print(f"    0x{v:08X}  {what:<40} {pipe}{mark}")
