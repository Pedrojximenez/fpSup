#!/usr/bin/env python3
"""把 og3k_plan 的寫入計畫跟執行中的相機逐字比對。

這是出 AutoRun 之前最強的檢查:現況是使用者實測可用的,計畫若與它完全一致,
AutoRun 就會重現同一個狀態。
"""
import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from putfile import mem_get
from og3k_plan import plan


def runs(items):
    """把連續(位址每次 +4)的項目併成一段,好用一次 mem_get 讀完。"""
    out, cur = [], []
    for a, v, note in items:
        if cur and a == cur[-1][0] + 4 and len(cur) < 64:
            cur.append((a, v, note))
        else:
            if cur:
                out.append(cur)
            cur = [(a, v, note)]
    if cur:
        out.append(cur)
    return out


def rd(a, n, t=10):
    for _ in range(t):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return list(w)
    return None


items = plan()
bad, unread, nread = [], 0, 0
for seg in runs(items):
    got = rd(seg[0][0], len(seg))
    if got is None:
        unread += len(seg)
        continue
    nread += len(seg)
    for (a, v, note), g in zip(seg, got):
        if g != v:
            bad.append((a, v, g, note))

print(f"計畫 {len(items)} 筆   讀到 {nread}   讀取失敗 {unread}\n")
if bad:
    print(f"★ {len(bad)} 筆與相機現況不符:")
    for a, v, g, note in bad[:40]:
        print(f"   0x{a:08X}  計畫 0x{v:08X}  現況 0x{g:08X}   {note}")
    if len(bad) > 40:
        print(f"   …另外 {len(bad)-40} 筆")
    raise SystemExit(1)
print("★ 完全一致 —— 計畫可以固化成 AutoRun")
