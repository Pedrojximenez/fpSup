#!/usr/bin/env python3
"""QS 解析度格:把 qs_resolution_2_S 的「狀態」欄 1 → 2,證明那個陣列是控制點。

    ./qsres_try.py read     只讀,和靜態映像比對
    ./qsres_try.py set      1 → 2(原值存到 qsres_orig.json)
    ./qsres_try.py revert   還原

診斷用,不是出貨的改法。動到的是原廠資源資料,只在 RAM,拔電池即還原。
"""
import json, pathlib, struct, sys

sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import mem_get, mem_set

IMG   = '/Users/dido/Developer/SIGMAfp_re/out/MAIN_c0000000.bin'
ORIG  = pathlib.Path(__file__).resolve().parent / 'qsres_orig.json'

# 18 份語言副本。WORD = 所屬對齊字,BYTE = 狀態欄最低位元組(= ref+7)
WORDS = [0xC22A17B0, 0xC22B889C, 0xC22CF988, 0xC22E6A74, 0xC22FDB64, 0xC2314C50,
         0xC232BD3C, 0xC2342E28, 0xC23CA5CC, 0xC23E15B4, 0xC24FD994, 0xC25162F8,
         0xC252EC5C, 0xC25475C4, 0xC255FF28, 0xC257888C, 0xC25911F0, 0xC25A9B58]
BYTES = [0xC22A17B0, 0xC22B889D, 0xC22CF98A, 0xC22E6A77, 0xC22FDB64, 0xC2314C51,
         0xC232BD3E, 0xC2342E2B, 0xC23CA5CC, 0xC23E15B7, 0xC24FD995, 0xC25162FA,
         0xC252EC5F, 0xC25475C4, 0xC255FF29, 0xC257888E, 0xC25911F3, 0xC25A9B58]


def setw(a, v):
    for _ in range(6):
        if mem_get(a)[0] == v:
            return True
        mem_set(a, v)
    return mem_get(a)[0] == v


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'read'
    img = open(IMG, 'rb').read()

    if cmd == 'read':
        same = 0
        for w, b in zip(WORDS, BYTES):
            live = mem_get(w)[0]
            stat = struct.unpack('<I', img[w - 0xC0000000:w - 0xC0000000 + 4])[0]
            idx = b - w
            print(f"  0x{w:08X}  live=0x{live:08X}  static=0x{stat:08X}"
                  f"  byte{idx}=0x{(live >> (8 * idx)) & 0xFF:02X}"
                  f"  {'=' if live == stat else '≠ 靜態'}")
            same += live == stat
        print(f"  {same}/18 與靜態映像一致")
        return

    if cmd == 'set':
        orig, bad = {}, 0
        for w, b in zip(WORDS, BYTES):
            cur = mem_get(w)[0]
            stat = struct.unpack('<I', img[w - 0xC0000000:w - 0xC0000000 + 4])[0]
            if cur != stat:
                raise SystemExit(f"0x{w:08X} 已經不是原廠值(0x{cur:08X}) —— 停手")
            orig[f"0x{w:08X}"] = cur
            idx = b - w
            new = (cur & ~(0xFF << (8 * idx))) | (0x02 << (8 * idx))
            if not setw(w, new):
                bad += 1
                print(f"  ✗ 0x{w:08X} 想要 0x{new:08X} 實得 0x{mem_get(w)[0]:08X}")
        ORIG.write_text(json.dumps(orig, indent=1))
        print(f"  寫入 18 筆,失敗 {bad}。原值存於 {ORIG.name}")
        return

    if cmd == 'revert':
        if not ORIG.exists():
            raise SystemExit("找不到 qsres_orig.json —— 不知道原值,拒絕還原")
        orig = json.loads(ORIG.read_text())
        bad = 0
        for k, v in orig.items():
            if not setw(int(k, 16), v):
                bad += 1
                print(f"  ✗ {k} 還原失敗")
        print(f"  還原 {len(orig)} 筆,失敗 {bad}")
        return

    raise SystemExit(__doc__)


main()
