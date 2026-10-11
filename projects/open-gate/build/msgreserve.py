#!/usr/bin/env python3
"""停止訊息的保留量:1 -> 32(或還原)。純 RAM,一個字。

`vbuf` 抽乾描述子時不是直接停止,而是送一則 id 0x2B 的訊息(0x168 bytes),
由 `FUN_c03A9580` 從 `MPoolFixed<360U, 384U>` 配一塊出來送。那支的閘門是

    c03a95a4  mov r5, #0
    c03a95ac  cmp r0, #0x2b          ← 停止訊息
    c03a95b0  cmpne r0, #0x30
    c03a95b4  beq +8                 ← 是的話 r5 留 0
    c03a95b8  mov r5, #1             ← 其他訊息 r5 = 1      ★ 就是這個字
    c03a95d8  cmp r0, r5             ← r0 = 訊息池剩餘塊數
    c03a95dc  bhi post               ← 剩的比 r5 多才送,否則丟掉並記在 0xC35A8F38

也就是原廠只替停止訊息留**一塊**。把普通訊息的門檻抬到 32,停止訊息就幾乎
不可能再被丟掉 —— 而停止訊息一旦被丟掉,錄影就永遠結束不了(REC 關不掉)。

    ./msgreserve.py show|on|off
"""
import sys, pathlib
SHELL = pathlib.Path(__file__).resolve().parents[3] / "fpSup" / "fp_usb_shell"
sys.path.insert(0, str(SHELL))
from putfile import mem_get, mem_set

GATE, STOCK, NEW = 0xC03A95B8, 0xE3A05001, 0xE3A05020   # mov r5,#1 / mov r5,#32
DROPS = 0xC35A8F38                                       # 被丟掉的訊息計數


def rd(a):
    for _ in range(8):
        w = mem_get(a, 1)[0]
        if w is not None:
            return w
    raise SystemExit(f"讀不到 0x{a:08X}")


def wr(a, v):
    for _ in range(10):
        if rd(a) == v:
            return
        mem_set(a, v)
    raise SystemExit(f"寫不進 0x{a:08X}")


cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
cur = rd(GATE)
name = {STOCK: "原廠(保留 1)", NEW: "已加大(保留 32)"}.get(cur, "不認得")
print(f"0x{GATE:08X} = {cur:08X}  {name}")
print(f"訊息丟棄計數 0x{DROPS:08X} = {rd(DROPS)}")
if cmd == "on":
    wr(GATE, NEW)
    print("-> 保留 32")
elif cmd == "off":
    wr(GATE, STOCK)
    print("-> 還原成原廠")
