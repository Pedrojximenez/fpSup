#!/usr/bin/env python3
"""把「原廠 120p profile 有、而 p13 沒有」的欄位寫進 p13。

2026-09-20 實驗證明:mode 12 @119.88 配原廠 120p 的 profile **不凍結**
(A001_118:620 幀 / 5 秒 = 實際 120 fps、271 MB/s),配 p13 則凍結。
所以原因在 profile。以下是 p177/p137 與 p13 的差異裡,我們從不寫、
而且不是幾何/RWZM 的那幾欄。

    ./p13_hirate.py on | off | show
"""
import sys, struct, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import og3k_plan as P
from ogdev import rd, wr

p = P.Plan()
d = json.loads((P.ROOT / "research/other/external/FP3K-technical-handoff-2026-09-10"
                / "analysis/firmware/raw-profiles.json").read_text())
cols = {c['offset']: c['table'] for c in d['columns']}
rows = {}
for r in d['rows']:
    for pid in r['profile_ids']: rows[pid] = r['index']

F2 = struct.unpack('<I', struct.pack('<f', 2.0))[0]
# (位移, p13 原廠, 原廠 120p 的值, 說明)
FIELDS = [
    (0x090, 0, 1,      "三個原廠影片 profile 都是 1"),
    (0x0B0, 0, 1,      "原廠 120p = 1,60p = 0"),
    (0x0C0, 1, 0,      "原廠影片 = 0,兩個 donor = 1"),
    (0x0DC, 0, 2016,   "producer W2,原廠有填(這裡填我們的寬)"),
    (0x0E4, 0, 672,    "producer H2,原廠有填(這裡填我們的高)"),
    (0x0FC, None, F2,  "原廠與 p83 都是 2.0f,只有 p13 是 3.0f"),
    (0x100, None, F2,  "同上"),
]
what = sys.argv[1] if len(sys.argv) > 1 else "show"
print("p13 的高格率相關欄位:")
for off, stock, want, note in FIELDS:
    a = cols[off] + rows[13] * 4
    cur = rd(a)[0]
    if stock is None: stock = p.word(a)
    tgt = want if what == "on" else stock
    line = "  +0x%03X @0x%08X  現在 %-11d" % (off, a, cur)
    if what in ("on", "off"):
        ok = wr(a, tgt)
        line += " -> %-11d %s" % (tgt, "OK" if ok else "失敗")
    line += "   " + note
    print(line)
