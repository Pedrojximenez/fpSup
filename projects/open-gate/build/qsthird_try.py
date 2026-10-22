#!/usr/bin/env python3
"""QS 解析度格:硬塞第三筆條目 {qs_resolution_2_S, 狀態 2},並把條目數改成 3。

    ./qsthird_try.py read     只讀,和靜態映像比對
    ./qsthird_try.py set      寫入(原值存到 qsthird_orig.json)
    ./qsthird_try.py revert   還原

★ 這是破壞性的診斷。第三筆條目要 10 bytes,但最後一筆與下一個屬性
  (color)的 key 之間只有 6 bytes —— 所以會蓋掉 color 的 key 前 4 bytes。
  那個格子的顏色會壞掉。量完就還原。

目的只有一個:證明「條目數 + 有效條目 = 圖示會被載入」。
"""
import json, pathlib, struct, sys

sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import mem_get, mem_set

IMG  = '/Users/dido/Developer/SIGMAfp_re/out/MAIN_c0000000.bin'
ORIG = pathlib.Path(__file__).resolve().parent / 'qsthird_orig.json'

# 18 份語言副本的第一筆條目位址(= qs_resolution_1_S 的引用處)
ENTRY1 = [0xC22A179F, 0xC22B888C, 0xC22CF979, 0xC22E6A66, 0xC22FDB53, 0xC2314C40,
          0xC232BD2D, 0xC2342E1A, 0xC23CA5BB, 0xC23E15A6, 0xC24FD984, 0xC25162E9,
          0xC252EC4E, 0xC25475B3, 0xC255FF18, 0xC257887D, 0xC25911E2, 0xC25A9B47]

# 條目 = [ref:u32][last:u32][tail:u16]。last 非零 = 走訪到此為止。
# 陣列索引就是狀態,所以第三筆 = 狀態 2。
# 第二筆的 last 要清成 0,否則走訪停在它那裡(前一次實驗就是敗在這)。
ENTRY2_LAST_OFF = 4                       # 第二筆的 last 欄:entry1 + 10 + 4
NEW_ENTRY = struct.pack('>IIH', 0x00028E7C, 0x00000001, 0x0000)


def setw(a, v):
    for _ in range(6):
        if mem_get(a)[0] == v:
            return True
        mem_set(a, v)
    return mem_get(a)[0] == v


def patch_bytes(addr, data, orig, dry=False):
    """把 data 寫到 addr(可能不對齊),以對齊字 read-modify-write。"""
    lo = addr & ~3
    hi = (addr + len(data) + 3) & ~3
    words = []
    for w in range(lo, hi, 4):
        cur = mem_get(w)[0]
        orig.setdefault(f"0x{w:08X}", cur)
        words.append(cur)
    buf = bytearray(b''.join(struct.pack('<I', v) for v in words))
    buf[addr - lo:addr - lo + len(data)] = data
    ok = True
    for i, w in enumerate(range(lo, hi, 4)):
        new = struct.unpack_from('<I', buf, i * 4)[0]
        if new != words[i] and not dry:
            if not setw(w, new):
                print(f"  ✗ 0x{w:08X} 寫入失敗")
                ok = False
    return ok


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'read'
    img = open(IMG, 'rb').read()

    if cmd == 'read':
        same = 0
        for e1 in ENTRY1:
            e3 = e1 + 20
            live = b''.join(struct.pack('<I', mem_get((e3 & ~3) + 4 * i)[0]) for i in range(4))
            base = e3 & ~3
            cut = live[e3 - base:e3 - base + 10]
            stat = img[e3 - 0xC0000000:e3 - 0xC0000000 + 10]
            print(f"  entry3 位置 0x{e3:08X}  live={cut.hex(' ')}  {'=' if cut == stat else '≠ 靜態'}")
            same += cut == stat
        print(f"  {same}/{len(ENTRY1)} 與靜態映像一致")
        return

    if cmd == 'set':
        orig = {}
        bad = 0
        for e1 in ENTRY1:
            cnt = e1 - 26
            # 1) 第二筆不再是最後一筆
            if not patch_bytes(e1 + 10 + ENTRY2_LAST_OFF, struct.pack('>I', 0), orig):
                bad += 1
            # 2) 寫入第三筆(狀態 2),它成為最後一筆
            if not patch_bytes(e1 + 20, NEW_ENTRY, orig):
                bad += 1
            # 3) 條目數 2 → 3
            if not patch_bytes(cnt, struct.pack('>I', 3), orig):
                bad += 1
        ORIG.write_text(json.dumps(orig, indent=1))
        print(f"  第三筆 + 條目數=3 寫入 {len(ENTRY1)} 份,失敗 {bad}。"
              f"原值 {len(orig)} 個字存於 {ORIG.name}")
        return

    if cmd == 'revert':
        if not ORIG.exists():
            raise SystemExit("找不到 qsthird_orig.json —— 不知道原值,拒絕還原")
        orig = json.loads(ORIG.read_text())
        bad = sum(not setw(int(k, 16), v) for k, v in orig.items())
        print(f"  還原 {len(orig)} 個字,失敗 {bad}")
        return

    raise SystemExit(__doc__)


main()
