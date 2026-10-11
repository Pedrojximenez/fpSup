#!/usr/bin/env python3
"""讀/改 og3kcanvas 錄影分支寫進畫布的某個欄位值(純 RAM,改立即數)。

每一筆是 `movw r3,#值 / movw r0,#欄位 / str r3,[r1,r0]`,本工具換第一條的立即數。
位址由掃描決定,不寫死。

    ./canvasval.py show
    ./canvasval.py set 04 448        # 記錄矩陣高度 672 -> 448
"""
import sys, pathlib, struct
SHELL = pathlib.Path(__file__).resolve().parents[3] / "fpSup" / "fp_usb_shell"
sys.path.insert(0, str(SHELL))
from putfile import mem_get, mem_set
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

BASE, SPAN = 0xC0732400, 0x300
MOVW_R3 = lambda v: 0xE3003000 | ((v >> 12) << 16) | (v & 0xFFF)


def rd(a, n=1):
    for _ in range(8):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return w
    raise SystemExit(f"讀不到 0x{a:08X}")


def scan():
    words = []
    for off in range(0, SPAN, 256):
        words += rd(BASE + off, 64)
    blob = struct.pack("<%dI" % len(words), *words)
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    ins = list(md.disasm(blob, BASE))
    out, started = [], False
    for i, x in enumerate(ins[:-2]):
        if x.mnemonic == "str" and x.op_str == "r1, [ip, #0x14]":
            started = True
        if (started and x.mnemonic == "movw" and x.op_str.startswith("r3,")
                and ins[i + 1].mnemonic == "movw" and ins[i + 1].op_str.startswith("r0,")
                and ins[i + 2].mnemonic in ("str", "nop")):
            out.append((int(ins[i + 1].op_str.split("#")[1], 0),   # 欄位
                        x.address,                                  # movw r3 的位址
                        int(x.op_str.split("#")[1], 0)))            # 目前值
    return out


rows = scan()
if len(sys.argv) < 2 or sys.argv[1] == "show":
    for f, a, v in rows:
        print(f"  +0x{f:03X}  movw @0x{a:08X}  = {v}")
    sys.exit()

field, want = int(sys.argv[2], 16), int(sys.argv[3], 0)
for f, a, v in rows:
    if f != field:
        continue
    for _ in range(10):
        if rd(a)[0] == MOVW_R3(want):
            break
        mem_set(a, MOVW_R3(want))
    got = rd(a)[0]
    ok = got == MOVW_R3(want)
    print(f"  +0x{field:03X}  {v} -> {want}" + ("" if ok else "  ★ 寫入失敗"))
    sys.exit(0 if ok else 1)
raise SystemExit(f"錄影分支裡沒有 +0x{field:03X}")
