#!/usr/bin/env python3
"""實驗:把 HSW 的 donor profile p13 的 +0x0B0 從 0 改成 1。

FUN_c0435e38:
    if (canvas[0xA4] in (0x18, 0x2B))
        return canvas[0xB0] == 1 ? 8 : 6;
而 profile -> 畫布是同位移複製(0xC0439FE8 反組譯確認)。
原廠只在 FHD120 的 profile 設 1,FHD60 是 0;我們兩個 donor 都是 0。

RAM 寫入,拔電池即還原。  ./b0_experiment.py [on|off|show]
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ogdev import rd, wr

ADDR = 0xC0BD7BB4          # p13 的 +0x0B0 欄位
STOCK = 0

what = sys.argv[1] if len(sys.argv) > 1 else "show"
cur = rd(ADDR)[0]
print("p13 +0x0B0 @0x%08X 目前 = %d" % (ADDR, cur))
if what == "on":
    ok = wr(ADDR, 1)
    print("寫入 1 ->", "成功" if ok else "失敗", " 讀回", rd(ADDR)[0])
elif what == "off":
    ok = wr(ADDR, STOCK)
    print("還原 %d ->" % STOCK, "成功" if ok else "失敗", " 讀回", rd(ADDR)[0])
