#!/usr/bin/env python3
"""讀執行期真正的畫布內容,並在兩種狀態之間比對。

    ./canvas_dump.py save 29p      錄完 29.97 之後存一份
    ./canvas_dump.py save 120p     錄完 119.88(或凍結)之後存一份
    ./canvas_dump.py diff 29p 120p 逐欄比對

畫布位址由 og3kcanvas 在每次錄影命中時寫進 LOG+0x14(TARGET_CANVAS_PTR_LOG)。
"""
import sys, json, pathlib, struct
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ogdev import rd

LOG = 0xC0732A00
OUT = pathlib.Path(__file__).resolve().parent / "canvas_dumps"
SIZE = 0x110 // 4          # 68 個字,涵蓋到 +0x10C

def snap():
    hits, _, pid, rw, rh = rd(LOG, 5)
    ptr = rd(LOG + 0x14)[0]
    if not ptr:
        raise SystemExit("LOG+0x14 是 0 —— 畫布 hook 的錄影分支還沒命中過")
    words = rd(ptr, SIZE)
    return dict(hits=hits, pid=pid, req=[rw, rh], ptr=ptr, words=words)

def show(tag, d):
    print(f"{tag}: 畫布 @0x{d['ptr']:08X}  錄影命中 {d['hits']}  pid {d['pid']}  "
          f"要求 {d['req'][0]}x{d['req'][1]}")

cmd = sys.argv[1]
OUT.mkdir(exist_ok=True)
if cmd == "save":
    d = snap(); show(sys.argv[2], d)
    (OUT / f"{sys.argv[2]}.json").write_text(json.dumps(d))
    print("已存", OUT / f"{sys.argv[2]}.json")
elif cmd == "show":
    show("now", snap())
elif cmd == "diff":
    a = json.loads((OUT / f"{sys.argv[2]}.json").read_text())
    b = json.loads((OUT / f"{sys.argv[3]}.json").read_text())
    show(sys.argv[2], a); show(sys.argv[3], b)
    print(f"\n{'off':>6} {sys.argv[2]:>14} {sys.argv[3]:>14}")
    n = 0
    for i, (x, y) in enumerate(zip(a["words"], b["words"])):
        if x == y: continue
        n += 1
        def s(v):
            f = struct.unpack('<f', struct.pack('<I', v))[0]
            return f"{v}" + (f"({f:g}f)" if 0x30000000 < v < 0x50000000 else "")
        print(f"{i*4:#06x} {s(x):>14} {s(y):>14}")
    print(f"\n{n} 欄不同")
