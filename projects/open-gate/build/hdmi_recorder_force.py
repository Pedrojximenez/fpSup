#!/usr/bin/env python3
"""把「HDMI 接的是已知錄影機」的 getter 改成永遠回傳真。

背景:`TSBMDAJA @ 0xC00EC948` 比對 HDMI 接收端的三字元廠商識別碼,
表在 `0xC07C04E0` = "ATS"(Atomos)/"BMD"(Blackmagic)/"AJA"。
結果存成一個位元組 `DAT_c31d5e72`,由 `FUN_c00eca10` 讀出。

實測(2026-09-17,沒接錄影機):
    0xC31D5E72 認出旗標    = 0
    0xC31D5E74 廠商遮罩    = 0x00000000
    0xC31D5E78 能力遮罩    = 0x00000003   bit0 ATS + bit1 BMD(AJA 沒有)
    0xC2EFCE38 允許遮罩    = 0xFFFFFFFF

`FUN_c00eca10` 是 Thumb,四道指令:
    F84D 8D04   str.w r8, [sp,#-4]!
    F645 6172   movw r1, #0x5E72
    F2CC 311D   movt r1, #0xC31D        -> r1 = 0xC31D5E72
    7808        ldrb r0, [r1]

補丁是**一個字**:`movs r0,#1 ; bx lr`。改 getter 而不是改變數,是因為
`TSBMDAJA()` 在 HDMI 熱插拔時會重算那個變數,把直接寫進去的值蓋掉。

目的:讓普通 HDMI 擷取卡也能讓相機以為錄影機在場。擷取卡解不了 raw
(畫面會是垃圾),但它會報出**收到的畫幅與時序** —— 那就是我們要的答案。

全部在 RAM。還原:`--restore`,或拔電池。

用法:
    python3 hdmi_recorder_force.py            # 套用
    python3 hdmi_recorder_force.py --check    # 只讀,不寫
    python3 hdmi_recorder_force.py --restore  # 寫回原值
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import og3k_load as L  # noqa: E402

ADDR = 0xC00ECA10
STOCK = 0x8D04F84D          # str.w r8,[sp,#-4]! + movw r1,#0x5E72 的前半
PATCH = 0x47702001          # movs r0,#1 ; bx lr   (Thumb)
SAVE = Path("/tmp/hdmi_getter_restore.json")

# 這四個只讀,用來記錄套用前後的狀態
WATCH = [(0xC31D5E70, "含認出旗標的字(+0x72)"),
         (0xC31D5E74, "比對到的廠商遮罩"),
         (0xC31D5E78, "每家能力遮罩"),
         (0xC2EFCE38, "允許遮罩")]


def survey(tag):
    print(f"-- {tag} --")
    for a, n in WATCH:
        print("   %#010x  %-22s = %#010x" % (a, n, L.rd(a)))


def main() -> int:
    check = "--check" in sys.argv
    restore = "--restore" in sys.argv

    cur = L.rd(ADDR)
    print("getter %#010x = %#010x  (原廠 %#010x / 補丁 %#010x)"
          % (ADDR, cur, STOCK, PATCH))
    survey("目前狀態")

    if check:
        return 0

    if restore:
        if cur == STOCK:
            print("已經是原廠值,不動作")
            return 0
        if cur != PATCH:
            print("!! 現值既不是原廠也不是我們的補丁,拒絕還原")
            return 1
        L.write_verified(ADDR, STOCK)
        L.sync_code()
        print("已還原 %#010x = %#010x,快取已同步" % (ADDR, L.rd(ADDR)))
        return 0

    if cur == PATCH:
        print("已經套用過,不重複寫")
        return 0
    if cur != STOCK:
        print("!! %#010x 不是原廠值,停止(可能韌體不同或已被其他東西改過)" % ADDR)
        return 1

    SAVE.write_text(json.dumps({"addr": ADDR, "stock": STOCK}))
    print(f"原值已存 {SAVE}")
    L.write_verified(ADDR, PATCH)
    L.sync_code()
    print("已寫入 %#010x = %#010x,D-cache + I-cache 已同步" % (ADDR, L.rd(ADDR)))
    survey("套用後")
    print("\n底層變數不會變 —— 我們改的是 getter,不是它。接上擷取卡後再看訊號。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
