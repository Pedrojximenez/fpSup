#!/usr/bin/env python3
"""pbobs 的安裝/讀取。0xC043A19C 必須用 BL(那裡的 lr 正好是 0xC043A19C,
用 B 會無限迴圈),ogdev.py 的 arm 只會下 B,所以自己來。

    ./pbobs_ctl.py on     先解除 hook,寫 payload,再用 BL 武裝
    ./pbobs_ctl.py read   讀紀錄
    ./pbobs_ctl.py off    還原原廠指令
"""
import pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from armasm import assemble
from putfile import mem_get, mem_set

SITE, STOCK = 0xC043A19C, 0xE1A00004        # mov r0, r4
CODE, LOG, END = 0xC0732400, 0xC0732600, 0xC0732800
SLOTS = 12

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
    blob = assemble(HERE / "pbobs.S")
    if CODE + len(blob) > LOG:
        raise SystemExit("payload 會蓋到 LOG")
    # 規則:payload 不能邊跑邊改 —— 先解除 hook。
    if not wr(SITE, STOCK):
        raise SystemExit("解除 hook 失敗")
    print(f"  hook 已解除,0x{SITE:08X} = 0x{rd(SITE)[0]:08X}")
    words = struct.unpack(f"<{len(blob)//4}I", blob)
    for i, v in enumerate(words):
        if not wr(CODE + i * 4, v):
            raise SystemExit(f"寫不進 0x{CODE + i*4:08X}")
    for a in range(LOG, END, 4):
        wr(a, 0)
    print(f"  payload {len(blob)}B @0x{CODE:08X},LOG 已清空")
    bl = 0xEB000000 | (((CODE - SITE - 8) >> 2) & 0xFFFFFF)
    if not wr(SITE, bl):
        raise SystemExit("武裝失敗")
    print(f"  已武裝 0x{SITE:08X} = 0x{bl:08X}  (BL 到 0x{CODE:08X})")

elif cmd == "off":
    wr(SITE, STOCK)
    print(f"  0x{SITE:08X} = 0x{rd(SITE)[0]:08X}  (原廠 0x{STOCK:08X})")

else:
    h = rd(LOG, 3)
    print(f"  總呼叫次數      {h[0]}")
    print(f"  影片回放類次數  {h[1]}")
    print(f"  已用格數        {h[2]}")
    if not h[2]:
        print("\n  ★ 回放期間沒有任何『壓縮位元流』的畫布經過 0xC043A19C")
    for k in range(min(h[2], SLOTS)):
        s = rd(LOG + 0x10 + k * 32, 8)
        print(f"    [{k}] profile {s[0]:<4} +0x44={s[1]}  +0x80=0x{s[2]:X}  "
              f"柵格 {s[3]}x{s[4]}  +0x1C={s[5]}  呼叫端尺寸 {s[6]}x{s[7]}")
