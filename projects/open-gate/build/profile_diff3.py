#!/usr/bin/env python3
"""三方對比:原廠 120p profile、OG3K 的 donor、HSW 的 donor。
找出「原廠有填、兩個 donor 都空著、而且我們不寫」的欄位。"""
import sys, struct, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import og3k_plan as P

p = P.Plan()
d = json.loads((P.ROOT / "research/other/external/FP3K-technical-handoff-2026-09-10"
                / "analysis/firmware/raw-profiles.json").read_text())
cols = {c['offset']: c['table'] for c in d['columns']}
rows = {}
for r in d['rows']:
    for pid in r['profile_ids']:
        rows[pid] = r['index']

IDS = [(187, "FHD120 8bit"), (177, "FHD120 12bit"), (173, "FHD60 12bit"),
       (83, "p83 OG3K"), (13, "p13 HSW")]
written = set(P.CANVAS_REC) | {0x80, 0x84}

def val(pid, off): return p.word(cols[off] + rows[pid] * 4)
def s(v):
    f = struct.unpack('<f', struct.pack('<I', v))[0]
    return f"{v}" + (f"({f:g}f)" if 1e-3 < abs(f) < 1e6 and v > 0x30000000 else "")

print("%6s  %14s %14s %14s %14s %14s  %s" % ("off", *[n for _, n in IDS], "我們"))
for off in sorted(cols):
    vs = [val(i, off) for i, _ in IDS]
    if len(set(vs)) == 1: continue
    tag = "寫" if off in written else "**沒寫**"
    print("%#06x  %14s %14s %14s %14s %14s  %s"
          % (off, *[s(v) for v in vs], tag))
