#!/usr/bin/env python3
"""錄完一段之後,確認 picker 有沒有命中我們的格式表、用了哪個感測器模式。"""
import sys, pathlib, struct
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ogdev import rd

print("fmttable 命中次數 0xC0730700 =", rd(0xC0730700)[0])
print("BITLATCH       0xC0731C14 =", rd(0xC0731C14)[0], " (0=12bit 3=10bit 4=8bit)")
print("FLAG           0xC0731C08 =", rd(0xC0731C08)[0])
print("最後使用的感測器模式 0xC343B590 =", rd(0xC343B590)[0])
w = rd(0xC0B59A40 + 4, 2)
hm, tl = w[0] & 0xFFFF, w[0] >> 16
vm, x = w[1] & 0xFFFF, w[1] >> 16
fc = hm * (vm - 1) + tl
print(f"mode 12 timing record: hmax={hm} tail={tl} vmax={vm} x={x} -> {72e6/fc:.3f} fps")
