#!/usr/bin/env python3
"""讀回 rowprobe 的紀錄。只用 mem get,hook 生效期間可安全使用。"""
import sys
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import mem_get

LOG = 0xC072FA60
w = mem_get(LOG, 1 + 8 * 2)
n = w[0]
if n == 0:
    print("  探針還沒命中——CINE 進去選一次格式,或錄一小段。")
    raise SystemExit(0)
print(f"  {n} 組不同的幾何,依第一次出現的順序:\n")
print(f"  {'#':>2}  {'寬':>6} x {'高':<6}  {'selector':>10}")
for i in range(min(n, 8)):
    key, sel = w[1 + i * 2], w[2 + i * 2]
    print(f"  {i:>2}  {key >> 16:>6} x {key & 0xFFFF:<6}  {sel:>10}  (0x{sel:08X})")
print("\n  1936x1090 = 原廠 FHD。選第三列之後若出現別的組合,那一組就是")
print("  rowpatch 守衛該比對的值。")
