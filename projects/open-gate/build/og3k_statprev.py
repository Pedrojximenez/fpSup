#!/usr/bin/env python3
"""驗證假設:是否有消費端直接讀靜態 profile 表的預覽欄位(而非 canvas 副本)。

把 OG3K 八個格式所用的 profile(= FHD 的 173/174/175/176/178/180/430/431)
的預覽欄位改成與 canvas 一致。不帶旗標守衛 —— 只為驗證,會暫時影響真正的
FHD 預覽。抽電池即還原。

    ./og3k_statprev.py on     套用
    ./og3k_statprev.py off    還原原廠
    ./og3k_statprev.py check  只看現值
"""
import json, struct, sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from putfile import mem_get, mem_set

ROOT = HERE.parent.parent
IMG = (ROOT / "out" / "MAIN_c0000000.bin").read_bytes()
B = 0xC0000000
d = json.loads((ROOT / "FP3K-technical-handoff-2026-09-10"
                / "analysis/firmware/raw-profiles.json").read_text())
col = {c['offset']: c['table'] for c in d['columns']}
rowof = {}
for r in d['rows']:
    for p in r['profile_ids']:
        rowof[p] = r

PROFILES = [173, 174, 175, 176, 178, 180, 430, 431]
#  偏移   canvas 值   說明
FIELDS = [(0x0C, 2024, "預覽柵格W"), (0x10, 1341, "預覽柵格H"),
          (0x20, 2000, "預覽可見W"), (0x28, 1334, "預覽可見H"),
          (0x60, 1536, "預覽比例"),  (0xD0, 1536, "預覽比例2"),
          (0xD8, 0,    "柵格覆寫W"), (0xE0, 0,    "柵格覆寫H")]


def stock(off, i):
    return struct.unpack_from('<I', IMG, col[off] + i * 4 - B)[0]


def rd(a):
    for _ in range(10):
        w = mem_get(a)
        if w and w[0] is not None:
            return w[0]
    raise SystemExit(f"read failed 0x{a:08X}")


def wr(a, v):
    for _ in range(12):
        if rd(a) == v:
            return True
        mem_set(a, v)
    return rd(a) == v


cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
bad = 0
for off, onval, nm in FIELDS:
    cur = []
    for p in PROFILES:
        i = rowof[p]['index']
        a = col[off] + i * 4
        want = onval if cmd == "on" else stock(off, i) if cmd == "off" else None
        if want is None:
            cur.append(rd(a))
        else:
            ok = wr(a, want)
            bad += not ok
            cur.append(rd(a))
    st = stock(off, rowof[PROFILES[0]]['index'])
    print(f"  +{off:02X} {nm:<10} 原廠 {st:<6} → 現值 {sorted(set(cur))}")
print(f"\n{'★ %d 項失敗' % bad if bad else '★ 完成'}   (指令: {cmd})")
