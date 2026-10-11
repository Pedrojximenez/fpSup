#!/usr/bin/env python3
"""enum → 顯示狀態的配對表 @0xC2E4020C:把 OG3K 的 {4,2} 改成 {4,N}。

    ./statemap_try.py read
    ./statemap_try.py set 1     OG3K 顯示成 FHD 的狀態
    ./statemap_try.py revert

這張表是 MenuValueConverterBase__v21 回傳的 (表位址, 筆數=3),
由 FUN_c06ccd10 在**每次求值**時線性查表 —— 和 widget 的序列化 blob 不同,
它應該是活的。這個實驗同時驗證那一點。

表(小端序 u32 配對):
  0xC2E4020C {3, 0}   UHD
  0xC2E40214 {2, 1}   FHD
  0xC2E4021C {4, 2}   OG3K   ← 要動的是 0xC2E40220 這個值
"""
import json, pathlib, sys

sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import mem_get, mem_set

ORIG  = pathlib.Path(__file__).resolve().parent / 'statemap_orig.json'
TABLE = 0xC2E4020C
VAL4  = 0xC2E40220          # 第三筆 {4, ?} 的 value 欄


def setw(a, v):
    for _ in range(6):
        if mem_get(a)[0] == v:
            return True
        mem_set(a, v)
    return mem_get(a)[0] == v


def show():
    for i in range(3):
        k = mem_get(TABLE + i * 8)[0]
        v = mem_get(TABLE + i * 8 + 4)[0]
        print(f"  0x{TABLE + i*8:08X}  {{enum {k}, 狀態 {v}}}")


cmd = sys.argv[1] if len(sys.argv) > 1 else 'read'

if cmd == 'read':
    show()
elif cmd == 'set':
    want = int(sys.argv[2])
    cur = mem_get(VAL4)[0]
    if not ORIG.exists():
        ORIG.write_text(json.dumps({f"0x{VAL4:08X}": cur}))
    if not setw(VAL4, want):
        raise SystemExit(f"寫入失敗,實得 0x{mem_get(VAL4)[0]:08X}")
    print(f"  0x{VAL4:08X}: {cur} → {want}")
    show()
elif cmd == 'revert':
    if not ORIG.exists():
        raise SystemExit("找不到 statemap_orig.json")
    for k, v in json.loads(ORIG.read_text()).items():
        setw(int(k, 16), v)
    print("  已還原")
    show()
else:
    raise SystemExit(__doc__)
