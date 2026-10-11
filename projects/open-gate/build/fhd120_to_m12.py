#!/usr/bin/env python3
"""把原廠 FHD120 這一格的感測器模式換成 mode 12,並把 mode 12 調到 119.88。

用意:借原廠 120p 自己的 profile(p187 8-bit / p177 12-bit)—— 它的 >60 相關
欄位本來就是對的 —— 只換感測器模式。若不凍結,就證明問題出在我們的 donor
profile(p13),而不是 mode 12 或格率本身。

    ./fhd120_to_m12.py on      套用(RAM,拔電池還原)
    ./fhd120_to_m12.py off     還原
    ./fhd120_to_m12.py show
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ogdev import rd, wr

SLOT = 11                       # picker 表的 FHD120
TABLES = {"表1 8-bit": 0xC0BE5810, "表2 10-bit": 0xC0BE59B0, "表3 12-bit": 0xC0BE5B50}
STOCK_MODE = {"表1 8-bit": 58, "表2 10-bit": 58, "表3 12-bit": 58}
M12_TIMING = 0xC0B59A40         # mode 12 的 timing record
# 119.88012 fps:330 x 1819 + 330 = 600,600 = 72e6 / (120000/1001)
T_119 = (330 | (330 << 16), 1820 | (6 << 16))
T_240 = (330 | (330 << 16),  910 | (6 << 16))   # mode 12 出廠值

what = sys.argv[1] if len(sys.argv) > 1 else "show"
print("picker 表的 FHD120(slot %d)的感測器模式欄:" % SLOT)
for name, base in TABLES.items():
    a = base + SLOT * 0x10 + 8
    print("  %-12s 0x%08X = %d" % (name, a, rd(a)[0]))
w = rd(M12_TIMING + 4, 2)
hm, tl, vm = w[0] & 0xFFFF, w[0] >> 16, w[1] & 0xFFFF
print("mode 12 timing  %d/%d/%d -> %.5f fps" % (hm, tl, vm, 72e6 / (hm * (vm - 1) + tl)))

if what == "on":
    for name, base in TABLES.items():
        a = base + SLOT * 0x10 + 8
        print("  %-12s -> 12 :" % name, "OK" if wr(a, 12) else "失敗")
    print("  mode 12 timing -> 330/330/1820 (119.88) :",
          "OK" if (wr(M12_TIMING + 4, T_119[0]) and wr(M12_TIMING + 8, T_119[1])) else "失敗")
elif what == "off":
    for name, base in TABLES.items():
        a = base + SLOT * 0x10 + 8
        print("  %-12s -> %d :" % (name, STOCK_MODE[name]),
              "OK" if wr(a, STOCK_MODE[name]) else "失敗")
    print("  mode 12 timing -> 原廠 330/330/910 :",
          "OK" if (wr(M12_TIMING + 4, T_240[0]) and wr(M12_TIMING + 8, T_240[1])) else "失敗")
