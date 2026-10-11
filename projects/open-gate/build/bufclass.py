#!/usr/bin/env python3
"""在 RAM 裡開關 og3kcanvas 的 `PUT +0x0A4, 0x29`(OG_BUFCLASS=29)。

那一筆是這個專案自己加的(§60),把畫布的緩衝類別碼從原廠的 0 改成 0x29,
好讓 `FUN_c0435E38` 走到「8 張」那條路。§62 判定它「沒有幫助」,但兩段樣本
本身都不正常,所以**從來沒有被當成退步的原因測過** —— 而 SSD 上唯一一次
跑滿 1177 格(A001_120)正是在這個選項還不存在的 build 上錄的。

錄影路徑上的三條指令(位址由掃描確定,不是寫死的):

    movw r3, #0x29
    movw r0, #0xa4
    str  r3, [r1, r0]      <- 換成 nop 就等於回到原廠的 +0xA4 = 0

只動這一個字,幾何、時序、其他欄位一個位元都不變。

    ./bufclass.py show|off|on
"""
import sys, pathlib, struct
SHELL = pathlib.Path(__file__).resolve().parents[3] / "fpSup" / "fp_usb_shell"
sys.path.insert(0, str(SHELL))
from putfile import mem_get, mem_set

ROW_CODE = 0xC0732400
SPAN = 0x300
STR_AA4 = 0xE7813000        # str r3, [r1, r0]
NOP     = 0xE320F000
MOVW_R3_29 = 0xE3003029
MOVW_R0_A4 = 0xE30000A4


def rd(a, n=1):
    for _ in range(8):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return w
    raise SystemExit(f"讀不到 0x{a:08X}")


def find():
    """找 movw r3,#0x29 / movw r0,#0xa4 / (str|nop) 這個序列。"""
    words, base = [], ROW_CODE
    for off in range(0, SPAN, 256):
        words += rd(base + off, 64)
    for i in range(len(words) - 2):
        if words[i] == MOVW_R3_29 and words[i + 1] == MOVW_R0_A4:
            return base + (i + 2) * 4, words[i + 2]
    raise SystemExit("在錄影路徑裡找不到 BUFCLASS 那一筆")


addr, cur = find()
state = {STR_AA4: "開著(+0xA4 = 0x29)", NOP: "關著(+0xA4 維持原廠 0)"}.get(cur, "不認得")
print(f"0x{addr:08X} = {cur:08X}  {state}")

cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
if cmd in ("off", "on"):
    want = NOP if cmd == "off" else STR_AA4
    for _ in range(10):
        if rd(addr)[0] == want:
            break
        mem_set(addr, want)
    got = rd(addr)[0]
    if got != want:
        raise SystemExit(f"寫入失敗,讀回 {got:08X}")
    print(f"-> {got:08X}  " + ("關掉了" if cmd == "off" else "開回來了"))
