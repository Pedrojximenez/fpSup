#!/usr/bin/env python3
"""解出 profile 欄位表 -> 畫布位移 的對照。

複製常式的樣式是:
    movw/movt r6, <欄位表基底>     載入某一欄的表
    ldr  rX, [r6, rIdx, lsl #2]    用 profile 列號索引
    str  rX, [r4, #off]            寫進畫布的某個位移
"""
import sys, struct, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import og3k_plan as P

p = P.Plan(); img = p.img; B = P.B
d = json.loads((P.ROOT / "research/other/external/FP3K-technical-handoff-2026-09-10"
                / "analysis/firmware/raw-profiles.json").read_text())
base2off = {c['table']: c['offset'] for c in d['columns']}

def imm16(w): return ((w >> 4) & 0xF000) | (w & 0xFFF)

lo, hi = 0xC0439D00, 0xC043A1A0
cur_base = None
print("profile欄位 -> 畫布位移")
i = lo
while i < hi:
    w = struct.unpack_from("<I", img, i - B)[0]
    if (w & 0x0FF00000) == 0x03000000:            # movw
        rd = (w >> 12) & 0xF
        w1 = struct.unpack_from("<I", img, i - B + 4)[0]
        if (w1 & 0x0FF00000) == 0x03400000 and ((w1 >> 12) & 0xF) == rd:
            cand = (imm16(w1) << 16) | imm16(w)
            if cand in base2off:
                cur_base = cand
    if (w & 0x0FF00000) == 0x05800000 and cur_base is not None:   # str Rd,[Rn,#imm]
        rn = (w >> 16) & 0xF
        off = w & 0xFFF
        if rn == 4:
            print("  +0x%03X  ->  畫布 +0x%03X" % (base2off[cur_base], off))
            cur_base = None
    i += 4
