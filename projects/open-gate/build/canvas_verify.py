#!/usr/bin/env python3
"""確認相機上的 og3kcanvas payload 與本地組譯結果逐字相同。"""
import sys, pathlib, struct
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import og3k_plan as P
from ogdev import rd

p = P.Plan()
blob = p.blobs["og3kcanvas"]
want = struct.unpack(f"<{len(blob)//4}I", blob)
got = rd(P.ROW_CODE, len(want))
bad = [(i, w, g) for i, (w, g) in enumerate(zip(want, got)) if w != g]
print(f"og3kcanvas @0x{P.ROW_CODE:08X}  {len(want)} 字  不同 {len(bad)}")
for i, w, g in bad[:8]:
    print(f"  +0x{i*4:03X}  相機 0x{g:08X}  應為 0x{w:08X}")
# 找出 PUT 0xF4 / 0xF8 的那兩組指令是否在相機上
seq = [0xE30003F4, 0xE30003F8]
print("PUT 0xF4 / 0xF8 的 movw r0,#off 指令是否出現在相機的 payload 裡:")
for s in seq:
    print(f"  0x{s:08X}  {'在' if s in got else '不在'}")
