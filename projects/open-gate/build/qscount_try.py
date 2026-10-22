#!/usr/bin/env python3
"""QS 解析度格:把 image 屬性的「條目數」從 2 改成 3。

    ./qscount_try.py read     只讀,和靜態映像比對
    ./qscount_try.py set      2 → 3(原值存到 qscount_orig.json)
    ./qscount_try.py revert   還原

條目數欄 = 第一筆條目位址 − 26,大端序 u32。值 2→3 只動最低位元組
(count+3),用 read-modify-write 改所屬的對齊字。

副作用:第 2 筆之後那 10 bytes 同時是下一個屬性(color)的表頭,
被當成第 3 筆條目讀之後 color 可能被誤讀。診斷用,量完還原。
"""
import json, pathlib, struct, sys

sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import mem_get, mem_set

IMG  = '/Users/dido/Developer/SIGMAfp_re/out/MAIN_c0000000.bin'
ORIG = pathlib.Path(__file__).resolve().parent / 'qscount_orig.json'

# image 屬性的條目數欄(18 份語言副本)
COUNTS = [0xC22A1785, 0xC22B8872, 0xC22CF95F, 0xC22E6A4C, 0xC22FDB39, 0xC2314C26,
          0xC232BD13, 0xC2342E00, 0xC23CA5A1, 0xC23E158C, 0xC24FD96A, 0xC25162CF,
          0xC252EC34, 0xC2547599, 0xC255FEFE, 0xC2578863, 0xC25911C8, 0xC25A9B2D]


def setw(a, v):
    for _ in range(6):
        if mem_get(a)[0] == v:
            return True
        mem_set(a, v)
    return mem_get(a)[0] == v


def lsb_of(count_addr):
    """大端序 u32 的最低位元組位址,以及它所屬的對齊字與字內位置。"""
    b = count_addr + 3
    w = b & ~3
    return b, w, b - w


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'read'
    img = open(IMG, 'rb').read()

    if cmd == 'read':
        same = 0
        for c in COUNTS:
            b, w, idx = lsb_of(c)
            live = mem_get(w)[0]
            stat = struct.unpack('<I', img[w - 0xC0000000:w - 0xC0000000 + 4])[0]
            print(f"  count@0x{c:08X}  word 0x{w:08X} live=0x{live:08X}"
                  f" static=0x{stat:08X}  byte{idx}=0x{(live >> (8*idx)) & 0xFF:02X}"
                  f"  {'=' if live == stat else '≠ 靜態'}")
            same += live == stat
        print(f"  {same}/{len(COUNTS)} 與靜態映像一致")
        return

    if cmd == 'set':
        orig = {}
        bad = 0
        for c in COUNTS:
            b, w, idx = lsb_of(c)
            cur = mem_get(w)[0]
            stat = struct.unpack('<I', img[w - 0xC0000000:w - 0xC0000000 + 4])[0]
            if cur != stat:
                raise SystemExit(f"0x{w:08X} 已非原廠值(0x{cur:08X}) —— 停手")
            if (cur >> (8 * idx)) & 0xFF != 2:
                raise SystemExit(f"0x{c:08X} 的條目數不是 2 —— 停手")
            orig[f"0x{w:08X}"] = cur
            new = (cur & ~(0xFF << (8 * idx))) | (0x03 << (8 * idx))
            if not setw(w, new):
                bad += 1
                print(f"  ✗ 0x{w:08X} 想要 0x{new:08X} 實得 0x{mem_get(w)[0]:08X}")
        ORIG.write_text(json.dumps(orig, indent=1))
        print(f"  條目數 2→3 寫入 {len(COUNTS)} 筆,失敗 {bad}。原值存於 {ORIG.name}")
        return

    if cmd == 'revert':
        if not ORIG.exists():
            raise SystemExit("找不到 qscount_orig.json —— 不知道原值,拒絕還原")
        orig = json.loads(ORIG.read_text())
        bad = sum(not setw(int(k, 16), v) for k, v in orig.items())
        print(f"  還原 {len(orig)} 筆,失敗 {bad}")
        return

    raise SystemExit(__doc__)


main()
