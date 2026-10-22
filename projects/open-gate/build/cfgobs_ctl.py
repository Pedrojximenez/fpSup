#!/usr/bin/env python3
"""cfgobs 的安裝/讀取(0xC043BE68,B hook)。

    ./cfgobs_ctl.py on / read / off
"""
import pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from armasm import assemble
from putfile import mem_get, mem_set

SITE, STOCK = 0xC043BE68, 0xE92D4070        # push {r4,r5,r6,lr}
CODE, LOG, END = 0xC0732400, 0xC0732600, 0xC0732800
SLOTS = 7
MODE = {0: "live 0", 1: "live 1", 2: "live 2",
        3: "照片(檢視表 0xC0BE5CF0)", 4: "照片(拍攝表 0xC0BE5D70)",
        5: "影片回放(0xC0BE4508/4548/4588)", 6: "assert"}
TABLE = {4: "0xC0BE4508  8-bit (+0x80=0x1000A)",
         3: "0xC0BE4548 10-bit (+0x80=0x10009)"}

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
    blob = assemble(HERE / "cfgobs.S")
    if CODE + len(blob) > LOG:
        raise SystemExit("payload 會蓋到 LOG")
    if not wr(SITE, STOCK):
        raise SystemExit("先還原 hook 點失敗")
    for i, v in enumerate(struct.unpack(f"<{len(blob)//4}I", blob)):
        if not wr(CODE + i * 4, v):
            raise SystemExit(f"寫不進 0x{CODE + i*4:08X}")
    for a in range(LOG, END, 4):
        wr(a, 0)
    print(f"  payload {len(blob)}B @0x{CODE:08X},LOG 已清空")
    br = 0xEA000000 | (((CODE - SITE - 8) >> 2) & 0xFFFFFF)
    if not wr(SITE, br):
        raise SystemExit("武裝失敗")
    print(f"  已武裝 0x{SITE:08X} = 0x{br:08X}  (B 到 0x{CODE:08X})")

elif cmd == "off":
    wr(SITE, STOCK)
    print(f"  0x{SITE:08X} = 0x{rd(SITE)[0]:08X}  (原廠 0x{STOCK:08X})")

else:
    h = rd(LOG, 2)
    print(f"  總呼叫次數 {h[0]}   已用格數 {h[1]}")
    for k in range(min(h[1], SLOTS)):
        s = rd(LOG + 0x10 + k * 64, 12)
        pid, p2 = s[0], s[1:]
        mode = p2[0]
        print(f"\n  [{k}] param_1 = 0x{pid:08X}   mode = {mode}  ({MODE.get(mode,'?')})")
        if mode == 5:
            t = TABLE.get(p2[8], "0xC0BE4588 12-bit (+0x80=0x10007)")
            print(f"       param_2+0x20 = {p2[8]}  → 表 {t}")
        else:
            print(f"       param_2+0x20 = {p2[8]}")
        print("       " + "  ".join(f"+{i*4:02X}={v}" for i, v in enumerate(p2)))
        b = struct.pack("<11I", *p2)
        print(f"       位元組:+0x0F={b[0x0F]} +0x17={b[0x17]} "
              f"+0x25={b[0x25]} +0x26={b[0x26]}")
        print(f"       +0x18={struct.unpack_from('<i', b, 0x18)[0]} "
              f"+0x1C={struct.unpack_from('<i', b, 0x1C)[0]}  "
              f"(FUN_c043bdb0 比的就是這兩個:3008 / 2000)")
