#!/usr/bin/env python3
"""逐筆開關 og3kcanvas 錄影分支的畫布寫入 —— 純 RAM,用來二分找出缺陷來源。

`og3kcanvas` 在錄影時往畫布寫一串欄位。2026-09-21 發現 HSW 錄出來的 CinemaDNG
有 30-80% 的格子,DNG 在檔案裡被往後推了 7168 或 65536 個位元組(尾巴因此被截掉),
而同一顆 SSD、同一次連線的**原廠 FHD 472 格全乾淨**。所以嫌疑在這些寫入。

每一筆都是 `movw r3,#值 / movw r0,#欄位 / str r3,[r1,r0]`,把那個 `str` 換成 nop
就等於不寫該欄。位址由掃描決定,不寫死。

    ./canvasbisect.py show
    ./canvasbisect.py off 90,B0,C0,DC,E4,FC,100
    ./canvasbisect.py on all
"""
import sys, pathlib, struct
SHELL = pathlib.Path(__file__).resolve().parents[3] / "fpSup" / "fp_usb_shell"
sys.path.insert(0, str(SHELL))
from putfile import mem_get, mem_set
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

BASE, SPAN = 0xC0732400, 0x300
STR_OP, NOP = 0xE7813000, 0xE320F000


def rd(a, n=1):
    for _ in range(8):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return w
    raise SystemExit(f"讀不到 0x{a:08X}")


def scan():
    """回傳 [(欄位, str 位址, 目前的字)],只取錄影分支(第一個 +0x00 寫入之後)。"""
    words = []
    for off in range(0, SPAN, 256):
        words += rd(BASE + off, 64)
    blob = struct.pack("<%dI" % len(words), *words)
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    out, field, started = [], None, False
    for x in md.disasm(blob, BASE):
        if x.mnemonic == "movw" and x.op_str.startswith("r0,"):
            field = int(x.op_str.split("#")[1], 0)
        if x.mnemonic == "str" and x.op_str == "r1, [ip, #0x14]":
            started = True                       # LOG 那一筆之後才是錄影欄位
        if x.mnemonic in ("str", "nop") and field is not None:
            w = struct.unpack_from("<I", blob, x.address - BASE)[0]
            if w in (STR_OP, NOP) and started:
                out.append((field, x.address, w))
                field = None
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    rows = scan()
    if cmd == "show":
        for f, a, w in rows:
            print(f"  +0x{f:03X}  0x{a:08X}  {'寫' if w == STR_OP else '★ nop'}")
        return
    want = sys.argv[2] if len(sys.argv) > 2 else ""
    sel = None if want.lower() == "all" else {int(s, 16) for s in want.split(",")}
    tgt = NOP if cmd == "off" else STR_OP
    for f, a, w in rows:
        if sel is not None and f not in sel:
            continue
        for _ in range(10):
            if rd(a)[0] == tgt:
                break
            mem_set(a, tgt)
        got = rd(a)[0]
        print(f"  +0x{f:03X}  0x{a:08X}  -> {'nop' if got == NOP else '寫'}"
              + ("" if got == tgt else "  ★ 寫入失敗"))


main()
