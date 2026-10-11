#!/usr/bin/env python3
"""一次讀完整條 LCD 顯示鏈。dispchain.py [標籤]"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent
                      / "fpSup" / "fp_usb_shell"))
from putfile import mem_get

def rd(a, n=1, t=14):
    for _ in range(t):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return list(w)
    return None

def ratio(w, h):
    if not h: return "—"
    r = w / h
    for nm, v in (("3:2", 1.5), ("16:9", 1.7778), ("4:3", 1.3333), ("1:1", 1.0)):
        if abs(r - v) < 0.02: return f"{r:.4f} {nm}"
    return f"{r:.4f} ?"

tag = sys.argv[1] if len(sys.argv) > 1 else ""
print(f"=== 顯示鏈 {tag} ===")

for ch in (0, 1):
    b = 0xC31DF564 + ch * 0x1B0
    w = rd(b + 0x30, 4)
    if w is None: print(f"  引擎 ch{ch}  讀取失敗"); continue
    print(f"  引擎匯出 ch{ch} @0x{b+0x30:08X}  可見 {w[0]}x{w[1]} ({ratio(w[0],w[1])})"
          f"   來源 {w[2]}x{w[3]} ({ratio(w[2],w[3])})")

e = rd(0xC31E10E4 + 0x320, 4)
if e: print(f"  引擎輸出維度                      {e[1]}x{e[2]} ({ratio(e[1],e[2])})")

m = rd(0xC375D840, 16)
if m:
    print(f"  主管理器 owner                    0x{m[5]:08X}")
    print(f"  管理器幾何 +1C/+20                {m[7]}x{m[8]} ({ratio(m[7],m[8])})"
          f"   +2C/+30 {m[11]}x{m[12]} ({ratio(m[11],m[12])})")
    o = m[5]
    if 0xC0000000 <= o < 0xC4000000:
        d = rd(o)
        if d and 0xC0000000 <= d[0] < 0xC4000000:
            t = rd(d[0], 11)
            if t:
                print(f"  idx0 描述子 0x{d[0]:08X}           {t[0]}x{t[1]} ({ratio(t[0],t[1])})"
                      f"   +10 {t[4]}x{t[5]}   fmt {t[7]}  lim 0x{t[8]:X}")

for nm, obj in (("STILL", 0xC375EB44), ("CINE ", 0xC375EB68)):
    print(f"  --- {nm} 物件 0x{obj:08X} 的四個插槽 ---")
    sl = rd(obj, 8)
    if sl is None:
        print("      讀取失敗"); continue
    for i in range(4):
        d = sl[i * 2]
        if not (0xC0000000 <= d < 0xC4000000):
            print(f"      idx{i}  0x{d:08X}  (非指標)"); continue
        t = rd(d, 11)
        if t is None:
            print(f"      idx{i}  0x{d:08X}  讀取失敗"); continue
        print(f"      idx{i}  0x{d:08X}  {t[0]:>5}x{t[1]:<5} ({ratio(t[0],t[1])})"
              f"  +10 {t[4]:>5}x{t[5]:<5}  fmt {t[7]}  lim 0x{t[8]:X}")

p5 = rd(0xC0BDB9CC)
fl = rd(0xC0731C08)
hk = rd(0xC0306EA0)
ok = rd(0xC0437E98)
tp = rd(0xC0732060)
print(f"  profile5 可見高 {p5[0] if p5 else '?'}   OG3K 旗標 {fl[0] if fl else '?'}"
      f"   模板命中 {tp[0] if tp else '?'}")
print(f"  長寬比 hook 0x{hk[0]:08X} ({'我們的' if hk and hk[0]!=0xE3A00003 else '原廠'})"
      f"   主輸出 hook 0x{ok[0]:08X} ({'我們的' if ok and ok[0]!=0xE92D4030 else '原廠'})")
