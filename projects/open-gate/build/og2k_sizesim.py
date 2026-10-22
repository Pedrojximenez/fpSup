#!/usr/bin/env python3
"""OG2K donor 的離線平面尺寸模擬。

沒有任何 profile 以 2016x1344 錄影,所以 OG2K 必須像早期 rowpatch 那樣
在畫布 RAM 複本裡補上錄影幾何。上機前唯一能先排掉的風險,就是確認
FUN_c04356b0 / FUN_c0435588 在「原廠 rec = 0x0、我們補上 2016x1344」的
組合下算出來的平面大小是合理的。

比較基準:
  p83 + OG3K 補丁   —— 實機驗證過,正在跑
  p175 原廠          —— 原廠 FHD 12-bit 錄影
"""
import importlib.util, struct, sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sz", HERE / "sizesim.py")
sz = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(sz)
except SystemExit:
    pass

CAND = [1, 202, 225, 251, 252, 253]
PLANE = {12: (7, 7), 10: (10, 9), 8: (10, 10)}          # eRawBitType -> +0x80/+0x84
DISP = (1024, 682)                                       # LCD


def canvas(profile):
    row = sz.w32(sz.MAP + profile * 4)
    return [sz.w32(b + row * 4) for b in sz.COL] + [0x17b0, 0xfca]


def patch(c, rec, act, depth):
    c = list(c)
    c[0x00 // 4], c[0x04 // 4] = rec
    c[0x24 // 4], c[0x2C // 4] = act
    c[0x80 // 4], c[0x84 // 4] = PLANE[depth]
    return c


def raw_plane(c):
    return sz.c04356b0(c, 1)


def report(label, c, depth, expect_frame=None):
    planes = sz.c04357e0(c)
    rp = raw_plane(c)
    tot = sz.total(c, *DISP)
    ok = "" if expect_frame is None else (
        "  ✔" if rp >= expect_frame else f"  ✘ 小於資料 {expect_frame:,}")
    print(f"  {label:<26} planes={planes}  RAW平面={rp:>12,}  總配置={tot:>13,}{ok}")
    return planes, rp, tot


def main():
    print(__doc__)
    print("=" * 78)
    print("\n基準(已知良好)")
    c83 = patch(canvas(83), (3024, 2010), (3008, 2000), 12)
    report("p83 + OG3K 12-bit", c83, 12, 3024 * 2010 * 3 // 2)
    report("p175 原廠 FHD 12-bit", canvas(175), 12, 1936 * 1090 * 3 // 2)

    for depth in (12, 10, 8):
        need = 2016 * 1344 * depth // 8
        print(f"\nOG2K {depth}-bit   2016x1344 / 裁切 2000x1334   "
              f"資料 {need:,} B/幀")
        for p in CAND:
            base = canvas(p)
            c = patch(base, (2016, 1344), (2000, 1334), depth)
            fps = struct.unpack('<f', struct.pack('<I', base[0x30 // 4]))[0]
            report(f"p{p}  (+0x30 = {fps:g} fps)", c, depth, need)

    print("\n欄位檢查(補丁不會動到的):")
    hdr = ('+0x3C', '+0xA4', '+0xB4', '+0xCC', '+0xF0', '+0x44', '+0x7C', '+0xE0')
    offs = (0x3C, 0xA4, 0xB4, 0xCC, 0xF0, 0x44, 0x7C, 0xE0)
    print("  " + "prof ".ljust(8) + "".join(f"{h:>8}" for h in hdr))
    for p in CAND + [83, 175]:
        c = canvas(p)
        print(f"  p{p:<7}" + "".join(f"{c[o // 4]:>8}" for o in offs))


main()
