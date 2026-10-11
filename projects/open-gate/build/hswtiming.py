#!/usr/bin/env python3
"""讀/改 HSW 格式表裡某一列的感測器時序 —— 純 RAM,一個字。

格式表在 0xC0731000,每列 48 bytes(`og3k_plan.fmt_table`):

    +0x14..0x20  鍵字串("HSW30" …)
    +0x24        hmax | tail<<16
    +0x28        vmax | x<<16          ★ 這一個字決定感測器格率
    +0x2C        nominal fps

    fps = 72e6 / (hmax * vmax)

這份 build 的 HSW30 那一列裝的是 240 的時序(OG_HSW_TOP=240 OG_HSW_TOP_SLOT=30),
所以選單上的 29.97 實際跑 239.76。把 vmax 換掉就能在不重建卡的情況下改感測器
格率,用來問「外接寫入路徑的崩塌跟 fps 是不是連續的」。

    ./hswtiming.py show
    ./hswtiming.py set HSW30 1212      # 180.018
    ./hswtiming.py set HSW30 910       # 239.760(原值)
"""
import sys, pathlib, struct
SHELL = pathlib.Path(__file__).resolve().parents[3] / "fpSup" / "fp_usb_shell"
sys.path.insert(0, str(SHELL))
from putfile import mem_get, mem_set

TABLE, ROW, NROW = 0xC0731000, 48, 10


def rd(a, n=1):
    for _ in range(8):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return w
    raise SystemExit(f"讀不到 0x{a:08X}")


def rows():
    for i in range(NROW):
        base = TABLE + i * ROW
        w = rd(base, 12)
        if w[0] != 5:
            break
        key = struct.pack("<4I", *w[5:9]).rstrip(b"\x00").decode("latin1")
        hmax, tail = w[9] & 0xFFFF, w[9] >> 16
        vmax, x = w[10] & 0xFFFF, w[10] >> 16
        yield base, key, hmax, tail, vmax, x, w[10]


def show():
    for base, key, hmax, tail, vmax, x, word in rows():
        fps = 72e6 / (hmax * vmax)
        print(f"  {key:<10} 0x{base:08X}+0x28 = {word:08X}  hmax {hmax} "
              f"tail {tail} vmax {vmax:<5} -> {fps:9.3f} fps")


def setv(want_key, vmax):
    for base, key, hmax, tail, old, x, word in rows():
        if key != want_key:
            continue
        new = (vmax & 0xFFFF) | (x << 16)
        for _ in range(10):
            if rd(base + 0x28)[0] == new:
                break
            mem_set(base + 0x28, new)
        got = rd(base + 0x28)[0]
        if got != new:
            raise SystemExit(f"寫入失敗,讀回 {got:08X}")
        print(f"  {key}: vmax {old} -> {vmax}   "
              f"{72e6/(hmax*old):.3f} -> {72e6/(hmax*vmax):.3f} fps")
        return
    raise SystemExit(f"表裡沒有 {want_key}")


if len(sys.argv) > 1 and sys.argv[1] == "set":
    setv(sys.argv[2], int(sys.argv[3], 0))
else:
    show()
