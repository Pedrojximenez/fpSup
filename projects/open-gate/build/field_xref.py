#!/usr/bin/env python3
"""找出誰讀 PARAM 的某個欄位表。

profile 是「每欄一張表、用 profile 列號索引」的版面,所以要找的是
「誰把那張表的基底位址載進暫存器」——  movw/movt 對,或字面池。
"""
import sys, struct, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import og3k_plan as P

p = P.Plan()
img = p.img
B = P.B
d = json.loads((P.ROOT / "research/other/external/FP3K-technical-handoff-2026-09-10"
                / "analysis/firmware/raw-profiles.json").read_text())
cols = {c['offset']: c['table'] for c in d['columns']}

def imm16(w): return ((w >> 4) & 0xF000) | (w & 0xFFF)

for off in [int(x, 0) for x in sys.argv[1:]] or [0xB0]:
    base = cols[off]
    print(f"\n=== PARAM +0x{off:03X} 的欄位表基底 0x{base:08X} ===")
    hits = []
    # 1) 字面池(LE 32-bit)
    pat = struct.pack("<I", base)
    for i in range(0, len(img) - 4, 4):
        if img[i:i+4] == pat:
            hits.append((B + i, "字面池"))
    # 2) movw/movt 對
    lo, hi = base & 0xFFFF, base >> 16
    for i in range(0, len(img) - 8, 4):
        w0 = struct.unpack_from("<I", img, i)[0]
        if (w0 & 0x0FF00000) != 0x03000000 or imm16(w0) != lo: continue
        rd = (w0 >> 12) & 0xF
        for j in (i + 4, i + 8, i + 12):
            w1 = struct.unpack_from("<I", img, j)[0]
            if (w1 & 0x0FF00000) == 0x03400000 and ((w1 >> 12) & 0xF) == rd \
               and imm16(w1) == hi:
                hits.append((B + i, f"movw/movt r{rd}"))
                break
    print(f"  {len(hits)} 個引用")
    for a, kind in hits[:8]:
        print(f"    0x{a:08X}  {kind}")
