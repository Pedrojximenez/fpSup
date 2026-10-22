#!/usr/bin/env python3
"""重開前把所有 payload 的執行期計數抓下來 —— 這些一拔電就沒了。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ogdev import rd

def show(label, addr, n=1):
    try:
        v = rd(addr, n)
        print(f"  {label:38s} 0x{addr:08X}  " + " ".join(f"{x}" for x in v))
    except SystemExit as e:
        print(f"  {label:38s} 0x{addr:08X}  讀取失敗")

print("旗標與鎖存")
show("FLAG (HSW 生效)",            0xC0731C08)
show("PBFLAG (回放中是我們的片)",   0xC0731C0C)
show("BITLATCH (0=12 3=10 4=8)",   0xC0731C14)
print("計數")
show("fmttable 命中",              0xC0730700)
show("og3ksel LOG(次數/最後 enum)", 0xC0731C00, 2)
show("og3kcanvas LOG 錄影/回放/pid", 0xC0732A00, 3)
show("og3kout 命中 / 拒絕",         0xC0732060)
show("og3kout 拒絕",               0xC0732070)
show("og3kgs LOG",                 0xC07328C0)
show("og3kpbsel LOG",              0xC0732380, 2)
show("og3kpbsel 要回傳的表項",      0xC0732390)
print("感測器")
show("最後使用的模式 0xC343B590",   0xC343B590)
w = rd(0xC0B59A40 + 4, 2)
hm, tl, vm, x = w[0] & 0xFFFF, w[0] >> 16, w[1] & 0xFFFF, w[1] >> 16
print(f"  mode 12 timing                        {hm}/{tl}/{vm} x={x} -> {72e6/(hm*(vm-1)+tl):.3f} fps")
