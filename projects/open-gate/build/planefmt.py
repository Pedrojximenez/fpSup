#!/usr/bin/env python3
"""改 og3kcanvas 的 8-bit 分支寫進畫布 +0x80 / +0x84 的平面格式碼。

`og3kcanvas.S` 的三條位元深度分支依據的是原廠**照片** profile 三胞胎
(p131/p151/p171 …),8-bit 那一條寫 10 / 10。但原廠的**影片** profile
FHD120 8-bit(p187)寫的是 **7 / 7** —— 而那正是 2026-09-21 在同一顆 SSD 上
472 格位移零缺陷的那個格式,我們的 8-bit 卻有 31-61% 的格子被推位。

    +0x80 / +0x84   平面格式碼(bpp 對照 FUN_c04356B0:7=12bit、9=10bit、10=8bit)
    8-bit   我們 10/10      原廠影片 7/7      ← 本工具切換這一組
    10-bit  我們 10/ 9      (乾淨,不動)
    12-bit  我們  7/ 7      (乾淨,不動)

位址由掃描 8-bit 分支的兩筆 `movw r3,#值 / movw r0,#欄位 / str` 決定。

    ./planefmt.py show|stock|ours
"""
import sys, pathlib, struct
SHELL = pathlib.Path(__file__).resolve().parents[3] / "fpSup" / "fp_usb_shell"
sys.path.insert(0, str(SHELL))
from putfile import mem_get, mem_set
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

BASE, SPAN = 0xC0732600, 0x100
MOVW_R3 = lambda v: 0xE3003000 | ((v >> 12) << 16) | (v & 0xFFF)


def rd(a):
    for _ in range(8):
        w = mem_get(a, 1)[0]
        if w is not None:
            return w
    raise SystemExit(f"讀不到 0x{a:08X}")


def find():
    """8-bit 分支 = 最後一組連續寫 +0x80 與 +0x84 的 movw/movw/str。"""
    words = mem_get(BASE, SPAN // 4)
    blob = struct.pack("<%dI" % (SPAN // 4), *[w or 0 for w in words])
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    ins = list(md.disasm(blob, BASE))
    out = []
    for i, x in enumerate(ins[:-2]):
        if (x.mnemonic == "movw" and x.op_str.startswith("r3,")
                and ins[i + 1].mnemonic == "movw"
                and ins[i + 1].op_str in ("r0, #0x80", "r0, #0x84")
                and ins[i + 2].mnemonic == "str"):
            out.append((int(ins[i + 1].op_str.split("#")[1], 0), x.address,
                        int(x.op_str.split("#")[1], 0)))
    return out[-2:]          # 最後一組就是 8-bit


rows = find()
print("  8-bit 分支:", ", ".join(f"+0x{f:02X} @0x{a:08X} = {v}" for f, a, v in rows))
cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
if cmd in ("stock", "ours"):
    want = 7 if cmd == "stock" else 10
    for f, a, _ in rows:
        for _ in range(10):
            if rd(a) == MOVW_R3(want):
                break
            mem_set(a, MOVW_R3(want))
        got = rd(a)
        ok = got == MOVW_R3(want)
        print(f"  +0x{f:02X} -> {want}" + ("" if ok else "  ★ 寫入失敗"))
