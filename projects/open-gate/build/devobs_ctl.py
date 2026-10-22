#!/usr/bin/env python3
"""devobs 的安裝/讀取/傾印(0xC05BB4A0)。 on / read / dump / off"""
import pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from armasm import assemble
from putfile import mem_get, mem_set

SITE, STOCK = 0xC05BB4A0, 0xE92D49F0       # push {r4,r5,r6,r7,r8,fp,lr}
# 0xC0732280 會撞到 og3kpbsel 的 payload 尾端(0xC0732200 + 132 = 0xC0732284)
# og3kpbsel 佔 0xC0732200..0284;改用 ROW_CODE/ROW_LOG 這兩塊
# (WITH_PBROW=False,所以計畫沒有用它們)
CODE, LOG, END = 0xC0732400, 0xC0732600, 0xC0732630

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
    blob = assemble(HERE / "devobs.S")
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

elif cmd == "dump":
    w = rd(LOG, 4)
    if not w[0] or not w[1]:
        raise SystemExit("還沒有描述子")
    d = w[1]
    print(f"  影格描述子 0x{d:08X}")
    head = rd(d + 0x10, 4)
    print(f"    +0x10 StripOffsets = {head[0]}")
    print(f"    +0x14 緩衝指標     = 0x{head[1]:08X}")
    print(f"    +0x18 緩衝大小     = {head[2]:,}")
    print(f"\n  顯像參數 +0x24 起 612 bytes,找幾何用的數值:")
    LOOK = {3032:"OG3K 全寬",2012:"OG3K 全高",3008:"OG3K 裁切寬",2000:"OG3K 裁切高",
            1936:"FHD 全寬",1090:"FHD 全高",1920:"FHD 裁切寬",1080:"FHD 裁切高",
            3856:"UHD 柵格寬",2170:"UHD 柵格高",6064:"感測器全寬",4042:"感測器全高"}
    words = rd(d + 0x24, 153)
    hits = []
    for i, v in enumerate(words):
        if v in LOOK:
            hits.append((i, v, LOOK[v]))
    for i, v, what in hits:
        print(f"    +0x{0x24 + i*4:03X} = {v:<6} {what}")
    if not hits:
        print("    (沒有認得的尺寸)")
    print(f"\n  前 24 個字:")
    for r in range(6):
        print("    " + "  ".join(f"{words[r*4+c]:>10}" for c in range(4)))

else:
    w = rd(LOG, 12)
    print(f"  呼叫次數     {w[0]}")
    print(f"  cur 描述子   0x{w[1]:08X}")
    print(f"  prev 描述子  0x{w[2]:08X}")
    print(f"  顯像引擎     0x{w[3]:08X}")
    if not w[0]:
        raise SystemExit("  (還沒被呼叫)")
    print("\n  提交當下的 cur 描述子欄位:")
    print(f"    +0x010 StripOffsets = {w[4]:,}" +
          ("   ★ 應該是 78848" if w[4] != 78848 else "   ✓"))
    print(f"    +0x014 緩衝指標     = 0x{w[5]:08X}")
    print(f"    +0x018 緩衝大小     = {w[6]:,}")
    print(f"    +0x020 解析器       = 0x{w[7]:08X}")
    print(f"    +0x260 寬           = {w[8]}")
    print(f"    +0x264 高           = {w[9]}")
    print(f"    +0x268 位元深度     = {w[10]}")
    print(f"    +0x26C              = {w[11]}")
