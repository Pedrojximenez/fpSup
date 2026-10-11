#!/usr/bin/env python3
"""找出誰讀「畫布」結構的某個位移 —— 也就是 ldr Rd,[Rn,#off] / ldrb 等。

畫布是 profile 複製出來的 RAM 結構,消費端用固定位移存取。
"""
import sys, struct, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import og3k_plan as P

p = P.Plan(); img = p.img; B = P.B
offs = [int(x, 0) for x in sys.argv[1:]] or [0xB0]
for off in offs:
    print(f"\n=== 讀畫布 +0x{off:03X} 的指令 ===")
    hits = []
    for i in range(0, len(img) - 4, 4):
        w = struct.unpack_from("<I", img, i)[0]
        # ldr Rd,[Rn,#imm12]  cond 010 1 1001 Rn Rd imm12   (P=1,U=1,B=0,W=0,L=1)
        if (w & 0x0FF00000) == 0x05900000 and (w & 0xFFF) == off:
            rn, rd = (w >> 16) & 0xF, (w >> 12) & 0xF
            hits.append((B + i, f"ldr  r{rd}, [r{rn}, #0x{off:X}]"))
        # ldrb
        elif (w & 0x0FF00000) == 0x05D00000 and (w & 0xFFF) == off:
            rn, rd = (w >> 16) & 0xF, (w >> 12) & 0xF
            hits.append((B + i, f"ldrb r{rd}, [r{rn}, #0x{off:X}]"))
    print(f"  {len(hits)} 個")
    for a, t in hits:
        region = ""
        if 0xC0430000 <= a < 0xC0440000: region = "  <- 畫布/格式區"
        elif 0xC0300000 <= a < 0xC0400000: region = "  <- 影像管線區"
        print(f"    0x{a:08X}  {t}{region}")
