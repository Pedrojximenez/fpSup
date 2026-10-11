#!/usr/bin/env python3
"""讀 pairlog 的紀錄。格式是 12 bytes 一筆 {table, count, key},
不是 keylog 的 24 bytes,所以 ogdev.py log 解出來會錯位。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ogdev import rd, LOG

n = rd(LOG)[0]
print(f"已記錄 {n} 筆不同的 (table, count)")
if n:
    w = rd(LOG + 4, n * 3)
    for i in range(n):
        t, c, k = w[i*3:i*3+3]
        print(f"  table 0x{t:08X}   count {c:<4d} key {k}")
