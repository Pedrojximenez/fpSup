#!/usr/bin/env python3
"""ratelog 的安裝/讀取/拆除(格率 setter 0xC005C0B8,B hook)。

    ./ratelog_ctl.py on / read / off

量的是「119.88 / 100 fps 的選單 enum」。SD 卡上選不到那兩個格率,SSD 才行,
而 SSD 佔住 USB 口 -> 沒有 shell;拔掉 SSD 設定又被打回合法值。**RAM 不受
換媒體影響**,所以:on -> 接 SSD 選那兩格 -> 換回 USB -> read -> off。

位址由 cave.claim() 給,**不是挑的** —— setlog.S 寫死的 0xC0731400 在現行
OG3K 建置裡是 og3kfmt 的 payload。
"""
import pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from armasm import assemble
from putfile import mem_get, mem_set
import cave

SITE, STOCK = 0xC005C0B8, 0xE92D4070        # push {r4,r5,r6,lr}
NEED, LOGOFF, SLOTS = 0x120, 0xA0, 6
# SD 卡上實測的選單 enum -> 我們表裡的鍵(2026-09-27)
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
    return cave.claim("ratelog.code", NEED)


cmd = sys.argv[1] if len(sys.argv) > 1 else "read"

if cmd == "on":
    P = block()
    blob = assemble(HERE / "ratelog.S", defines=[f"P={P:#x}"])
    if len(blob) > LOGOFF:
        raise SystemExit(f"payload {len(blob)} bytes 會蓋到 LOG(+0x{LOGOFF:X})")
    # payload 先、hook 後 —— 反過來會讓 setter 跳進還沒寫完的記憶體。
    for i, v in enumerate(struct.unpack(f"<{len(blob)//4}I", blob)):
        if not wr(P + i * 4, v):
            raise SystemExit(f"payload 第 {i} 字寫不進去")
    for i in range(1 + SLOTS * 4):
        if not wr(P + LOGOFF + i * 4, 0):
            raise SystemExit("LOG 歸零失敗")
    if rd(SITE)[0] != STOCK:
        raise SystemExit(f"hook 點 0x{SITE:08X} 不是原廠值 "
                         f"0x{STOCK:08X}(讀到 0x{rd(SITE)[0]:08X})—— 先拆乾淨")
    off = (P - (SITE + 8)) >> 2
    br = 0xEA000000 | (off & 0xFFFFFF)
    if not wr(SITE, br):
        raise SystemExit("hook 武裝失敗")
    print(f"★ ratelog 已裝 payload 0x{P:08X}  LOG 0x{P + LOGOFF:08X}  "
          f"hook 0x{SITE:08X} = 0x{br:08X}")
    print("  現在:接 SSD -> 選 100 fps -> 選 119.88 -> 拔 SSD 接 USB -> ./ratelog_ctl.py read")

elif cmd == "read":
    P = block()
    n = rd(P + LOGOFF)[0]
    print(f"hook 0x{SITE:08X} = 0x{rd(SITE)[0]:08X}"
          f"({'武裝中' if rd(SITE)[0] != STOCK else '已拆'})   記到 {n} 筆")
    for i in range(min(n, SLOTS)):
        r0, r1, r2, _ = rd(P + LOGOFF + 4 + i * 16, 4)
        tag = KNOWN.get(r1, "★ 未知 —— 可能就是 100 或 119.88")
        print(f"  [{i}] obj 0x{r0:08X}  enum {r1:>3}  flag 0x{r2:08X}   {tag}")

elif cmd == "off":
    P = block()
    if not wr(SITE, STOCK):
        raise SystemExit("還原 hook 點失敗 —— 不要重開機,再試一次")
    for i in range(NEED // 4):
        wr(P + i * 4, 0)
    print(f"✓ hook 點已還原 0x{SITE:08X} = 0x{rd(SITE)[0]:08X}   cave 已歸零")
else:
    raise SystemExit(__doc__)
