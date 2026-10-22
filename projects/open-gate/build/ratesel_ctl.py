#!/usr/bin/env python3
"""ratesel 的安裝/讀取/拆除(MenuItemSelector<eXC_MenuFrameRate>::v1,B hook)。

    ./ratesel_ctl.py on / read / off

讀出格率選單的**值陣列**與**游標界線**,確認最後一項是不是 119.88。
需要:選了 OG3K、接著 SSD(否則清單只有七項)、在格率清單裡把游標移動一次。

物件版面由 ::v2 的位移導出(大小 0x1C):
    +0x04 設定物件  +0x08 值陣列  +0x0C 游標  +0x14 最大索引  +0x18 環繞旗標
"""
import pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from armasm import assemble
from putfile import mem_get, mem_set
import cave

SITE, STOCK = 0xC00B20E8, 0xE92D4070        # push {r4,r5,r6,lr}
NEED, LOGOFF = 0x110, 0xC0
FIELD = {0: "vtable", 1: "設定物件", 2: "值陣列", 3: "游標",
         4: "+0x10", 5: "★ 最大索引", 6: "環繞旗標"}
# SD 卡上實測的選單 enum -> 格率(2026-09-27)
KNOWN = {1: "23.98", 2: "25", 3: "29.97", 4: "50", 5: "59.94", 12: "24", 13: "48"}


def rd(a, n=1):
    for _ in range(8):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return w
    raise SystemExit(f"讀不到 0x{a:08X}")


def wr(a, v):
    for _ in range(10):
        if rd(a)[0] == v:
            return True
        mem_set(a, v)
    return rd(a)[0] == v


def block():
    return cave.claim("ratesel.code", NEED)


cmd = sys.argv[1] if len(sys.argv) > 1 else "read"

if cmd == "on":
    P = block()
    blob = assemble(HERE / "ratesel.S", defines=[f"P={P:#x}"])
    if len(blob) > LOGOFF:
        raise SystemExit(f"payload {len(blob)} bytes 會蓋到 LOG(+0x{LOGOFF:X})")
    for i, v in enumerate(struct.unpack(f"<{len(blob)//4}I", blob)):
        if not wr(P + i * 4, v):
            raise SystemExit(f"payload 第 {i} 字寫不進去")
    for i in range((NEED - LOGOFF) // 4):
        if not wr(P + LOGOFF + i * 4, 0):
            raise SystemExit("LOG 歸零失敗")
    if rd(SITE)[0] != STOCK:
        raise SystemExit(f"hook 點 0x{SITE:08X} 不是原廠 0x{STOCK:08X} —— 先拆乾淨")
    br = 0xEA000000 | (((P - (SITE + 8)) >> 2) & 0xFFFFFF)
    if not wr(SITE, br):
        raise SystemExit("hook 武裝失敗")
    print(f"★ ratesel 已裝 payload 0x{P:08X}  LOG 0x{P+LOGOFF:08X}  "
          f"hook 0x{SITE:08X} = 0x{br:08X}")
    print("  現在:選 OG3K -> 接 SSD -> 進格率清單 -> 游標移動一次 -> 接回 USB -> read")

elif cmd == "read":
    P = block()
    L = P + LOGOFF
    n = rd(L)[0]
    print(f"hook 0x{SITE:08X} = 0x{rd(SITE)[0]:08X}"
          f"({'武裝中' if rd(SITE)[0] != STOCK else '已拆'})   抄到 {n} 次")
    if not n:
        raise SystemExit("還沒抄到 —— 格率清單的游標沒有被移動過")
    obj = rd(L + 4, 7)
    for i, v in enumerate(obj):
        print(f"  [{i}] +0x{i*4:02X}  0x{v:08X} ({v:>6})  {FIELD[i]}")
    arr = rd(L + 0x20, 12)
    top = obj[5]
    print(f"\n  值陣列(前 12 筆,最大索引 = {top} -> 共 {top+1} 項):")
    for i, v in enumerate(arr):
        mark = ""
        if i == top:
            mark = "  ← 最後一項(要擋的就是它)"
        elif i == top - 1:
            mark = "  ← 倒數第二"
        elif i > top:
            mark = "  (界線外)"
        cur = " ←游標" if i == obj[3] else ""
        print(f"    [{i:>2}] enum {v:>3}  {KNOWN.get(v,'★ 未知'):<8}{cur}{mark}")

elif cmd == "off":
    P = block()
    if not wr(SITE, STOCK):
        raise SystemExit("還原 hook 點失敗 —— 不要重開機,再試一次")
    for i in range(NEED // 4):
        wr(P + i * 4, 0)
    print(f"✓ hook 點已還原 0x{SITE:08X} = 0x{rd(SITE)[0]:08X}   cave 已歸零")
else:
    raise SystemExit(__doc__)
