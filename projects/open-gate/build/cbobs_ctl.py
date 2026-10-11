#!/usr/bin/env python3
"""cbobs 的安裝/讀取(包住 0xC05C2744 的 blx r3)。 on / read / off"""
import pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from armasm import assemble
from putfile import mem_get, mem_set

SITE, STOCK = 0xC05C2744, 0xE12FFF33       # blx r3
CODE, LOG, END = 0xC0732200, 0xC0732300, 0xC0732340

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
    blob = assemble(HERE / "cbobs.S")
    if CODE + len(blob) > LOG:
        raise SystemExit(f"payload {len(blob)}B 會蓋到 LOG")
    cur = rd(SITE)[0]
    if cur != STOCK:
        raise SystemExit(f"0x{SITE:08X} 是 0x{cur:08X},不是原廠 blx r3 "
                         f"(0x{STOCK:08X}) —— 停手")
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
    w = rd(LOG, 13)
    print(f"  呼叫次數      {w[0]}")
    if not w[0]:
        print("  (還沒被呼叫過)")
        raise SystemExit
    print(f"  callback 位址 0x{w[1]:08X}")
    print(f"  影格索引      {w[2]}")
    print(f"  context       0x{w[3]:08X}")
    print(f"  結構指標      0x{w[4]:08X}")
    print(f"  回傳值        {w[5]}")
    print("  結構內容(呼叫後,28 bytes):")
    for k in range(7):
        v = w[6 + k]
        print(f"    +0x{k*4:02X} = {v:>12}  (0x{v:08X})")
