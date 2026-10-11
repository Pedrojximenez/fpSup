#!/usr/bin/env python3
"""fmtsub 的安裝/讀取(0xC0437060)。 on / read / off"""
import pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from armasm import assemble
from putfile import mem_get, mem_set

SITE, STOCK = 0xC0437060, 0xE1A0C000        # mov ip, r0
CODE, LOG, END = 0xC0732400, 0xC0732600, 0xC073260C

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
    blob = assemble(HERE / "fmtsub.S")
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
    br = 0xEA000000 | (((CODE - SITE - 8) >> 2) & 0xFFFFFF)
    if not wr(SITE, br):
        raise SystemExit("武裝失敗")
    print(f"  payload {len(blob)}B @0x{CODE:08X},已武裝 0x{SITE:08X} = 0x{br:08X}")

elif cmd == "off":
    wr(SITE, STOCK)
    print(f"  0x{SITE:08X} = 0x{rd(SITE)[0]:08X}  (原廠)")

else:
    w = rd(LOG, 3)
    print(f"  呼叫次數      {w[0]}")
    print(f"  換成 98 的次數 {w[1]}")
    print(f"  最後看到的原值 {w[2]}   (回放表項是 222)")
    print(f"  PBFLAG        {rd(0xC0731C0C)[0]}")
