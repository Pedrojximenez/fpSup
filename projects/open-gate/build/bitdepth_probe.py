#!/usr/bin/env python3
"""不用錄影就掃出 CinemaDNG 位元深度的選單列舉。

fmttable 在 live view 期間每秒被呼叫約 60 次,每次命中 HSW 都會把命中的是哪一張
picker table 鎖存進 BITLATCH(0=12-bit 3=10-bit 4=8-bit)。所以改設定、等一下、
讀回來就知道那個列舉值代表什麼。
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "fpSup" / "fp_usb_shell"))
from putfile import sh
from ogdev import rd

BITLATCH, FMT_HITS, FLAG = 0xC0731C14, 0xC0730700, 0xC0731C08
NAME = {0: "12-bit", 3: "10-bit", 4: "8-bit"}

def g(c):
    try: return sh(c).strip()
    except Exception: return "ERR"

g("menu SetMovRecSize 4"); time.sleep(0.8)
print("FLAG =", rd(FLAG)[0], " (要 1,否則 fmttable 不會命中 HSW)")
base = rd(FMT_HITS)[0]
for v in range(6):
    g("menu SetMovCinemaDNGQuality %d" % v)
    time.sleep(1.2)
    b, h = rd(BITLATCH)[0], rd(FMT_HITS)[0]
    print("  Quality %d -> BITLATCH %d = %-7s   (fmttable +%d)"
          % (v, b, NAME.get(b, "?"), h - base))
    base = h
