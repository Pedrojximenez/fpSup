#!/usr/bin/env python3
"""把原廠某個 profile 與我們的 donor 逐欄對比,標出我們有沒有覆寫。

    ./profile_diff.py 177 13      原廠 FHD120(12-bit)對 HSW 的 donor
"""
import sys, struct, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import og3k_plan as P

a_id, b_id = int(sys.argv[1]), int(sys.argv[2])
p = P.Plan()
d = json.loads((P.ROOT / "research/other/external/FP3K-technical-handoff-2026-09-10"
                / "analysis/firmware/raw-profiles.json").read_text())
cols = {c['offset']: c['table'] for c in d['columns']}
rows = {}
for r in d['rows']:
    for pid in r['profile_ids']:
        rows[pid] = r['index']

written = dict(P.CANVAS_REC)
plane = P.CANVAS_PLANE
diff = []
for off in sorted(cols):
    va = p.word(cols[off] + rows[a_id] * 4)
    vb = p.word(cols[off] + rows[b_id] * 4)
    if va == vb: continue
    def show(v):
        f = struct.unpack('<f', struct.pack('<I', v))[0]
        return f"{v}" + (f" ({f:g}f)" if 1e-3 < abs(f) < 1e6 else "")
    mark = ""
    if off in written:          mark = f"我們寫 {written[off]}"
    elif off in (0x80, 0x84):   mark = f"我們寫(依位元深度)"
    diff.append((off, va, vb, mark, show(va), show(vb)))

print(f"p{a_id}(原廠)對 p{b_id}(我們的 donor):{len(diff)} 欄不同,共 {len(cols)} 欄")
print(f"{'off':>6}  {'p'+str(a_id):>20} {'p'+str(b_id):>20}   我們有沒有覆寫")
for off, va, vb, mark, sa, sb in diff:
    flag = "  " if mark else "  ← **沒寫**"
    print(f"{off:#06x}  {sa:>20} {sb:>20}   {mark or ''}{flag}")
