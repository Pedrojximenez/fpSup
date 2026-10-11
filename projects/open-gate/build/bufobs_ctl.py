#!/usr/bin/env python3
"""bufobs 的安裝/讀取(0xC05C2D10,B hook)。 on / read / off"""
import pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from armasm import assemble
from putfile import mem_get, mem_set

SITE, STOCK = 0xC05C2D10, 0xE92D44F0      # push {r4,r5,r6,r7,sl,lr}
CODE, LOG, END = 0xC0732280, 0xC0732300, 0xC0732320
SLOTS = 6
REF = {3165360: "FHD 1936x1090", 9150576: "OG3K 3032x2012",
       12551280: "UHD 3856x2170", 12441600: "UHD 3840x2160"}

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

cmd = sys.argv[1] if len(sys.argv) > 1 else "read"

if cmd == "on":
    blob = assemble(HERE / "bufobs.S")
    if CODE + len(blob) > LOG:
        raise SystemExit(f"payload {len(blob)}B 會蓋到 LOG")
    cur = rd(SITE)[0]
    if cur != STOCK:
        raise SystemExit(f"0x{SITE:08X} 是 0x{cur:08X},不是原廠 0x{STOCK:08X} —— 停手")
    for i, v in enumerate(struct.unpack(f"<{len(blob)//4}I", blob)):
        if not wr(CODE + i * 4, v):
            raise SystemExit(f"寫不進 0x{CODE + i*4:08X}")
    for a in range(LOG, END, 4):
        wr(a, 0)
    print(f"  payload {len(blob)}B @0x{CODE:08X},LOG 已清空")
    br = 0xEA000000 | (((CODE - SITE - 8) >> 2) & 0xFFFFFF)
    if not wr(SITE, br):
        raise SystemExit("武裝失敗")
    print(f"  已武裝 0x{SITE:08X} = 0x{br:08X}")

elif cmd == "off":
    wr(SITE, STOCK)
    print(f"  0x{SITE:08X} = 0x{rd(SITE)[0]:08X}  (原廠 0x{STOCK:08X})")

else:
    w = rd(LOG, 1 + SLOTS)
    print(f"  FUN_c05c2d10 被呼叫 {w[0]} 次")
    for k in range(SLOTS):
        v = w[1 + k]
        if not v:
            continue
        page = (v + 0x1fff) & 0xfffff000
        print(f"    nbytes = {v:>12,}  → 實配 {page:>12,}   {REF.get(v,'')}")
    if w[0] and not any(w[1:]):
        print("    (呼叫過但 nbytes 全是 0 —— 那本身就是答案)")
