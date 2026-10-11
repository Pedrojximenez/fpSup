#!/usr/bin/env python3
"""讀 dngblk hook 記下的每格標頭區塊長度。

    ./dngblk.py          印出環的內容與分布
    ./dngblk.py clear    歸零,準備下一段

安裝(hook 本身):
    ./ogdev.py up dngblk.S 0xC0730600
    ./ogdev.py arm 0xC03A53D0 0xC0730600
移除:
    ./ogdev.py off 0xC03A53D0
"""
import sys, pathlib, collections
SHELL = pathlib.Path(__file__).resolve().parents[3] / "fpSup" / "fp_usb_shell"
sys.path.insert(0, str(SHELL))
from putfile import mem_get, mem_set

RING, SLOTS = 0xC0730000, 128
KNOWN = {0x13800: "0x13800 實際標頭 -> 位移 0",
         0x15400: "0x15400 保留量   -> 位移 7,168",
         0x23800: "0x23800 標頭+64K -> 位移 65,536"}


def rd(a, n):
    for _ in range(8):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return w
    raise SystemExit(f"讀不到 0x{a:08X}")


if len(sys.argv) > 1 and sys.argv[1] == "clear":
    for i in range(2 + SLOTS):
        mem_set(RING + i * 4, 0)
    print("環已歸零")
    sys.exit()

idx, total = rd(RING, 2)
print(f"累計格數 {total}   寫入索引 {idx}")
if total == 0:
    print("hook 還沒命中過 —— 是不是沒 arm,或還沒錄影?")
    sys.exit()

vals = []
for base in range(0, SLOTS, 16):
    vals += rd(RING + 0x10 + base * 4, 16)
n = min(total, SLOTS)
order = [(idx - 1 - k) % SLOTS for k in range(n)][::-1]      # 舊 -> 新
seq = [vals[i] for i in order]

hist = collections.Counter(seq)
print("分布:")
for v, c in sorted(hist.items()):
    print(f"  0x{v:06X} = {v:>7}  x{c:<4}  {KNOWN.get(v, '')}")

runs, cur, cnt = [], seq[0], 0
for v in seq:
    if v == cur:
        cnt += 1
    else:
        runs.append((cur, cnt))
        cur, cnt = v, 1
runs.append((cur, cnt))
print("連續段(舊 -> 新):")
print("  " + "  ".join(f"0x{v:X}x{c}" for v, c in runs[:24]))
