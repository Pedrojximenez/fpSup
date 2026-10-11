#!/usr/bin/env python3
"""關掉每格 DNG 建檔的「全 512 對齊」快速路徑。

`FUN_c069ADE0`(每格檔案的完整寫入器)依 `FUN_c069AD80(段串列)` 的結果選開檔模式:

    全部段 512 對齊 -> 0x1806 -> 檔案系統開檔型別 10 -> 建檔旗標 bit2
                    -> FUN_c0646BF8(fs, 4, dirent+0x5C8, 2) 換掉該檔的寫入快取模式
    否則            -> 0x806  -> 型別 4(10-bit / 12-bit 走的就是這條,實測全乾淨)

2026-09-21 實測:HSW 8-bit 有 31-61% 的格子,DNG 被整塊往後推 7,168 或 65,536
位元組(尾巴因此被截掉);10-bit、12-bit、原廠 FHD 8-bit 都是 0%。8-bit 的影像
位元組 1,354,752 是 512 的整數倍,正好讓它落進快速路徑。

把 FUN_c069AD80 改成無條件回 0,8-bit 就走和 10-bit 一樣的路。

    ./fastpath.py show|off|on
"""
import sys, pathlib
SHELL = pathlib.Path(__file__).resolve().parents[3] / "fpSup" / "fp_usb_shell"
sys.path.insert(0, str(SHELL))
from putfile import mem_get, mem_set

FN = 0xC069AD80
STOCK = (0x000050E3, 0x0000A0E3)      # 佔位,實際由讀取決定
PATCH = (0xE3A00000, 0xE12FFF1E)      # mov r0, #0 ; bx lr
SAVE = pathlib.Path(__file__).resolve().parent / ".fastpath_orig.txt"


def rd(a, n=2):
    for _ in range(8):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return w
    raise SystemExit(f"讀不到 0x{a:08X}")


cur = rd(FN)
patched = tuple(cur) == PATCH
print(f"0x{FN:08X}  {cur[0]:08X} {cur[1]:08X}  " +
      ("★ 已關掉快速路徑(mov r0,#0 / bx lr)" if patched else "原廠"))

cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
if cmd == "off":
    if not patched:
        SAVE.write_text(f"{cur[0]:08X} {cur[1]:08X}")
    for i, v in enumerate(PATCH):
        for _ in range(10):
            if rd(FN + i * 4, 1)[0] == v:
                break
            mem_set(FN + i * 4, v)
    got = rd(FN)
    print("-> %08X %08X  %s" % (*got, "關掉了" if tuple(got) == PATCH else "★ 寫入失敗"))
elif cmd == "on":
    if not SAVE.is_file():
        raise SystemExit("沒有存檔,不知道原值 —— 拔電池即可還原")
    orig = [int(x, 16) for x in SAVE.read_text().split()]
    for i, v in enumerate(orig):
        for _ in range(10):
            if rd(FN + i * 4, 1)[0] == v:
                break
            mem_set(FN + i * 4, v)
    print("-> %08X %08X  還原" % tuple(rd(FN)))
