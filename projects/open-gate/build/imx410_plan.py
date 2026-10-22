#!/usr/bin/env python3
"""IMX410 全功能版的寫入計畫 —— 只含**新的那一套**。

og3k_plan.py 一個字都不動:它是 OG3K/OG2K/OG6K/HSW 四個出貨目標的承重牆,
而且有 EXPECTED_PLAN_WORDS 那條刻意的絆線。全功能版的形狀不一樣(沒有靜態
格式表、多三個資料表、少一顆畫布 payload),所以另立一份。

負責資料、動態配方、畫布、選單連動、顯示與入口的單一寫入計畫。
長寬比已由 imx410_aspect 依配方計算;格率與位深跟隨原廠選單。
**目前仍是測試產品。** 本機卡片由 build_res_lab_card.py 呼叫共用
build_autorun.py 封裝,未完成項目見 MISSING。

    ./imx410_plan.py            印出配置與計畫摘要
    ./imx410_plan.py --map      只印位址配置
"""
from __future__ import annotations

import argparse
import struct
import sys

from armasm import assemble
import imx410_rate_native as RATE_NATIVE
import sl_excl as SLX
import imx410_bit14 as BIT14
import imx410_sellog as SELLOG
import imx410_binfilt as BINFILT
import imx410_rate_ui as RATE_UI
import imx410_rate_lv as RATE_LV
from imx410_block import (ratestr_table,  # noqa: F401
                          AXIS_WORDS, CANVAS_MAX_PAIRS, CANVAS_TEMPLATE,
                          RECIPE_WORDS, aspect_q_table, axis_words,
                          canvas_template, rate_table, ratnum_table,
                          timing_table)
from imx410_full import FIRMWARE, RWZM_UNITY, Registry

B = 0xC0000000

# ---- 歷史固定位址配置；不可直接建卡或安裝 ----------------------------------
# 2026-10-04 的最終 BIN 稽核證實本計畫會覆寫原廠非零資料，且所有固定
# Sensor Lab payload 均不符 CAVE_BUMP 只放 veneer 的現行規則。
# 以下常數保留作打包器的來源位址與歷史解析；build_res_lab_card.py
# 先搬到 USER 區塊，再由 res_lab_cave_audit 稽核最終 BIN。
# 直接使用本計畫的固定位址安裝仍必須拒絕。
# og3k_plan 用的開發 cave 是 0xC0730000..0xC0732A00(映像裡為零),UI 套件另外
# 佔 0xC0732700..0xC0734C84。**不要越過 0xC0732700** —— 那是 UI 的狀態區。
#
# 兩個絕對不能碰的:
#   0xC072F800..0xC072FE00   USB shell 的檔案傳輸暫存區。2026-09-12 畫布 hook
#                            指著那裡,每一次 getfile/putfile 都覆寫它 -> 凍結。
#   0xC072E064..0xC072EFB4   cave.py 的 arena,shell 端探針在用。
# cave 的上界是 **UI_CODE**(0xC0732C84),不是 UI_STATE —— og3k_plan 自己的
# GS_LOG/GS_CODE/ROW_LOG 就住在 0xC0732880..0xC0732C84 那一段。UI 的狀態區
# (0xC0732700..0xC0732880)另外列成禁區。
CAVE_LO, CAVE_HI = 0xC0730000, 0xC0732C84
_HARD = ((0xC072E064, 0xC072EFB4),     # cave.py 的 arena
         (0xC072F800, 0xC072FE00),     # USB shell 檔案傳輸暫存區
         (0xC0732700, 0xC0732880),     # UI 狀態 / diag / req / llog
         (0xC0732C84, 0xC0734C84))     # UI code


def _reused_regions():
    """og3k_plan 那些**我們不碰**的區域。

    全功能版現在把 sel/name/out/fmt/restore/gs/range/fps 都自己擺了,所以它們
    不再是禁區 —— 一個東西不能既是「我要放在這裡」又是「這裡不准放」。
    剩下的只有回放那一組:還沒接(MISSING),但位置要留著,免得之後接的時候
    發現被佔走。
    """
    import og3k_plan as P
    keep = {"PBSEL_CODE": 384, "PBSEL_LOG": 32, "PBSEL_ENT": 16, "PB_CODE": 128}
    return tuple((getattr(P, n), getattr(P, n) + sz)
                 for n, sz in keep.items() if isinstance(getattr(P, n, None), int))


FORBIDDEN = _HARD + _reused_regions()

# ---- 位址配置 --------------------------------------------------------------
# 全功能版不需要靜態格式表(og3k_plan 的 TABLE,432 bytes),也不需要
# og3kcanvas(119 字);空出來的位置就是這裡用的。
# 全功能版用的是**靜態版空出來的那幾個槽**:
#   0xC0730400/0500  RATE_CODE / POOLINIT_CODE —— 只有 HSW 240 與 OG_POOLDEPTH
#                    會用,全功能版兩個都不開
#   0xC0730800       CODE —— 原本的 fmttable payload,被 imx410_fmt 取代
#   0xC0730E00..1400 NAME 的尾巴 + TABLE —— 靜態格式表沒有了
#   0xC0732400       ROW_CODE —— 原本的 og3kcanvas,被 imx410_canvas 取代
RATETAB     = 0xC0730400     # 132 B
# imx410_fps 到 0xC0730A98,名稱字串從 0xC0730C00 起 —— 中間 360 B 是空的。
RATNUM      = 0xC0730AA0     # 88 B,CinemaDNG FrameRate 的有理數表
RATE_CODE   = 0xC0730B00     # imx410_rate,容器格率 hook
TMGTAB      = 0xC0730490     # 264 B
CTMPL       = 0xC07305A0     #  88 B
ASPTAB      = 0xC0730620     #  20 B,五個 enum 的定點比例
ASP_CODE    = 0xC0730640     # imx410_aspect(第一個點),96 B
ASP2_CODE   = 0xC07306B0     # imx410_aspect(第二個點),96 B
FPS_CODE    = 0xC0730A00     # imx410_fps,取代 og3kfps 的槽
NAME        = 0xC0730C00     # "CUST" 字串(og3kname 讀它)
SEL_CODE    = 0xC0731800     # og3ksel(動態 donor 還原版)
NAME_CODE   = 0xC0731A00     # og3kname
OGFMT_CODE  = 0xC0731400     # og3kfmt
RESTORE_CODE = 0xC0731600    # og3krestore
# ⛔ 第一守則的 14-bit 例外(research/SETTINGS_AREA_FIRST_RULE.md,使用者 2026-10-01):
#   執行時原廠真的是 14-bit,關機時改回 12。imx410_poff 是卡片唯一的入口:
#   註冊 PowerOffMgr 第一清單的回呼,再照 stage2 的方式呼叫 RESTORE_CODE。
WITH_BIT_POFF = False   # 暫停(2026-10-02 使用者):關機回呼可能晚於 SaveOn 的 v2 序列化,未完成
# 位置:同時避開 regions() 與 og3k 禁區(0xC0732200 起是 og3k_plan 的,不能用)。
POFF_CODE  = 0xC0730260       # imx410_poff(入口 + 回呼,49 字)
POFF_OBJ   = 0xC0730330       # 回呼物件 {vtbl}
POFF_STATE = 0xC0730340       # 註冊結果 / 執行次數 / 改回次數 / 最後讀值
SL_MENU_MARK = 0xC0730380     # sl_menu 啟動器寫的 {"SLMS", 區塊, 狀態, 結果}(只在 --b25-menu 卡)
OUT_CODE    = 0xC0731D00     # og3kout
GTAB        = 0xC0732100     # 分組表(1 組:六個預覽 profile 的可見高)
FMT_CODE    = 0xC0734C84     # source-only label (SOURCE_ONLY): packed into USER, never installed here; was 0xC0730740
# og3krecipe 的上限是 og3kfmt 的槽 0xC0731400,所以這裡只有 2016 B。
# 目前 1552 B,餘 464 B。超過的話 layout_errors() 會擋(2026-09-28 加長寬比
# 之後就撞過一次)。
RECIPE_CODE = 0xC0730C20     # og3krecipe
CANVAS_CODE = 0xC0732400     # imx410_canvas,132 B
AXIS        = 0xC0732490     # 9 字
RECIPE      = 0xC07324C0     # 27 字 = RECIPE_WORDS(區塊 108 B)
ENTRY_ADDR  = 0xC0732530     # picker 表項,48 B
CANVAS      = 0xC0732560     # 1 + 24*2 字
HITS        = 0xC0732668     # 命中計數
PROFILE_ID  = 0xC073266C     # 我們宣告的 profile id(imx410_fmt 寫進 ENTRY、imx410_canvas 的守衛都讀它)
COLTAB      = 0xC0732670     # 29 字:宣告列那 29 欄的欄表位址(imx410_profile.DECLARED_BY_PANEL 的順序)
# 與 og3k_plan 共用的鎖存(值域與語意完全相同,所以沿用同一批位址)
BITLATCH = 0xC0731C14
FPSLATCH = 0xC0731C40
PICKOK   = 0xC0731C44
LOG      = 0xC0732A00            # imx410_canvas 的計次,在 cave 之外但 og3k 也用

# ---- hook ------------------------------------------------------------------
PIK_HOOK, PIK_STOCK = 0xC043CCF8, 0xE92D4CF0     # picker 查表
ROW_HOOK, ROW_STOCK = 0xC043A19C, 0xE1A00004     # 畫布,位移 mov r0,r4
# 全韌體只有這兩個點把長寬比寫死成 3(16:9),兩個都在
# XC_DisplayZoomParameterW71C1 裡,位移的都是那條 mov r0,#3。
ASP_HOOK,  ASP_STOCK  = 0xC0306EA0, 0xE3A00003
ASP2_HOOK, ASP2_STOCK = 0xC0306EEC, 0xE3A00003
# 增益分派的「是不是 raw movie」判斷。p13 落在它的 raw movie 帶 131..190 之外,
# 而那一段**沒有空 id**(§13.4 查過),所以這顆非武裝不可 —— 不然 ISO 640 以上
# 會少掉約 2.7 檔高光餘裕。
GS_HOOK,  GS_STOCK  = 0xC03A6DD8, 0xE92D4010
# CinemaDNG FrameRate 標籤的有理數來源(FUN_c00c9bd0)。
# 原廠第一條是 push {r4-r8,lr};payload 的 pass 路徑要補回去。
RAT_HOOK, RAT_STOCK = 0xC00C9BD0, 0xE92D41F0
# 配置器 v3 的範圍檢查,讓它認得我們的表項指標。不改的話回放會用 FHD 的幾何
# 去解我們的檔案。
RNG_HOOK, RNG_STOCK = 0xC043D258, 0xE92D0030
# og3k_plan 的 payload 位址,原樣沿用(它們在 _reused_regions() 的禁區裡,
# 所以這裡要明確排除自己)。
GS_CODE  = 0xC0732900
RNG_CODE = 0xC0731F00
# ★ 範圍檢查(og3krange)。**預設關,與 OG3K 出貨一致。**
#
# 2026-09-28:我們與 OG3K 的武裝清單逐一比對,**唯一多出來的就是這一顆**,
# 而唯一失敗的步驟就是錄影。OG3K 的 WITH_RANGE 是 False(「全拆再回頭」之後
# 留下的狀態)而它錄得起來。
#
# 反編譯:0xC043D258 是管線分派器十六個範圍測試之一(FUN_c043c5f0 那條鏈),
# **第一個命中的決定用哪一條管線**(param_1 + 0x268 / 0x4CC / 0x4F0 / 0x514 …)。
# 讓自己的表項命中 TAB3 那一支,等於把分派結果換掉 —— 那是錄影路徑也會走的。
#
# 它存在的理由是回放(讓分派器認得我們的表),而回放本來就還沒接。
# 要做回放時再打開,並且單獨驗。
WITH_RANGE = False

# ★ 容器格率 hook(FUN_c00c9bd0)。OG3K 沒有武裝這個站點,所以它會讓
#   `test_armed_hooks_are_a_subset_of_og3k` 失敗 —— 那條規矩是對的:
#   「要多加一顆就要有明確的旗標和單獨的驗證,不能順手打開。」這就是那個旗標。
#
#   為什麼非加不可:CinemaDNG 的 FrameRate 標籤唯一來源就是這個函式,而它的
#   switch 最高只到 120000/1001。2026-09-29 上機(A001_170)感測器跑 239.760
#   而標籤寫 30000/1001。原廠 enum 補不到 240(選單最高 120),所以 §5.3 說的
#   「容器格率用最接近的合法 enum」在這裡做不到。
#
#   單獨的驗證:錄一段 240,DNG 的 FrameRate 必須是 240000/1001。
#   關掉它(False)就回到「感測器 240、標籤 30」的狀態,其餘功能不受影響。
WITH_RATE = True
WITH_BIT_FROM_MENU = True  # 原廠同次 picker 呼叫的 config +0x20,含 RAW14

# ★ 選單第十列 239.76 fps，2026-09-30 現況：
#   CSV 整欄移除 IMAGE 並保留結尾 CRLF；控制器上限 8.0 -> 9.0。
#   摘要配對表已搬到 cave,第十筆是 (11, 9):export 11 = 原廠 picker 的 240。
#   ⚠ 舊版寫「加入 (5, 9),實機能識別第十列為 240」,兩句都錯 —— export 5 會進
#     原廠 assert、internal 5 是 59.94;而配對表只管收合摘要,選列輸入另有一條。
#     完整鏈是 row 9 -> internal 8 -> export 11 -> "240" -> CUST240 -> state 9(§8.11)。
#   六個 CSV 變體的第十列繼承第九列 Enabled。新增列的收合摘要與最新配方連動另待驗收。
WITH_RATE_ROW = True

# ★ 格率全開(2026-09-30,使用者「先全開」):六個變體每一列都寫成 `1,2`。
#   實機兩點對照定案(res-lab/validation/20260930-rate-reject-ab):
#   反灰與「因以下的狀態無法選擇」對話框**只**由變體 CSV 的 Enabled 決定,
#   而挑哪個變體是 NBU 腳本依媒體決定的 —— `C04A121C` 類別 hook 管不到。
#   CSV 開了之後值能不能留住是另一層:原廠正規化器(`C00A87E4` hook)。
#     只開 CSV            選 119.88 -> 被壓成 59.94
#     開 CSV + 正規化 hook  選 119.88 -> 保持 119.88
#   ⚠ CSV 是全機共用的,**不分 CUSTOM**:原廠 UHD/FHD 或 MOV 下也會全亮,
#     但那裡正規化 hook 不放行,選超過上限的格率會被原廠默默壓回去。
#   關掉就回到「第十列繼承第九列」的原廠反灰。
# ★ 2026-10-02 關掉:FHD/UHD 重新可選後,全開讓它們也全亮(使用者:「只有 custom 要全部打開」)。
#   實機讀值(SD):EXCL_FrameRate 在 CUSTOM = 0(原廠就挑全開的 B2_5_5)、FHD = 4、UHD = 3,
#   變體本來就跟著解析度走;CUSTOM 不需要改 CSV。239.76 / 14-bit 的「只在 CUSTOM」另做私有清單。
WITH_RATE_ALL_OPEN = False

# (資源位址, 描述子位址, 原廠長度)。描述子是 BE {key, 檔名位移, 資源位移, 長度},
# 資源位址 = 0xC0D22400 + 資源位移,檔名 = ../MenuB12/data/ListB12/<name>.cvm
RATE_ROW_CSV = ((0xC0F8E848, 0xC0D50A1C, "B2_5_5"),        # 全開
                (0xC0F8E94C, 0xC0D5351C, "B2_5_5_excl"),   # 只到 29.97
                (0xC0F8EA50, 0xC0D5584C, "B2_5_5_excl2"),  # 只到 24
                (0xC0F8EB54, 0xC0D54F7C, "B2_5_5_excl3"),  # 只到 25
                (0xC0F8EC58, 0xC0D4F87C, "B2_5_5_excl4"),  # 只到 59.94
                (0xC0F8ED5C, 0xC0D4E25C, "B2_5_5_excl5"))  # 只到 100
RATE_ROW_LEN = 257                  # 原廠實際用量(BOM 3 + 標頭 38 + 九列 x 24)
# 槽距 260(257 + 3 bytes 間隙),六個都一樣。補 NUL 到 260 是為了字對齊,
# 而且最後一個槽 +260 正好抵到下一個資源的起點,不越界。
RATE_ROW_SLOT = 260
RATE_ROW_CAP = 0xC1A74B44           # B2_5_5 清單控制器上限
RATE_ROW_CAP_STOCK = 0x00000041     # BE float 8.0
RATE_ROW_CAP_NEW = 0x00001041       # BE float 9.0
# 實際格率 240000/1001,與原廠列「119.88 fps」同一格式(使用者 2026-10-01:「240 fps 不是真的240」)。
# 收合摘要/LV 仍用原廠池的 "240" —— 池裡沒有 "239.76",要走共用字串池(uis_intern)才能改。
RATE_ROW_TEXT = b"239.76 fps"       # CSV 的 TEXT 欄可以直接放字面字串


def rate_row_csv(img, res):
    """九列 -> 十列。移除整個 IMAGE 欄,第十列繼承第九列的 Enabled。"""
    raw = img[res - B: res - B + RATE_ROW_LEN]
    bom, body = raw[:3], raw[3:]
    lines = [l for l in body.split(b"\r\n") if l]
    if len(lines) != 10:
        raise SystemExit(f"{res:#x} 不是標頭 + 九列,而是 {len(lines)} 行")
    last = lines[-1].split(b",")
    if len(last) != 6:
        raise SystemExit(f"{res:#x} 欄數不是 6:{lines[-1]!r}")
    lines = lines + [b",".join([b"10", RATE_ROW_TEXT, last[2], last[3],
                                last[4], last[5]])]
    out = drop_image_column(lines)          # ★ 整欄拿掉,不是留空 —— 見 §8.9
    new = bom + b"\r\n".join(out) + b"\r\n"
    if len(new) > RATE_ROW_LEN:
        raise SystemExit(f"{res:#x} 十列 {len(new)} B 超過原槽 {RATE_ROW_LEN}")
    if WITH_RATE_ALL_OPEN:
        new = csv_set_enabled(new, (True,) * (len(out) - 1))   # 等長改寫
    return new

# ---- 選單第四列 14 bit -----------------------------------------------------
# 2026-09-29。位元深度選單 `B2_5_2` 原廠三列(8/10/12 bit),但**下游原廠就備齊了**:
#   · enum<->列 配對表 0xC2E401CC 有 **四筆**:(4,0) (3,1) (0,2) **(1,3)**
#     —— 第四筆就是 eRawBitType 1 = 14-bit。不用 §8.3 那招搬表。
#   · 字串 ID **0308 = "14 bit"** 原廠就在語言表裡,緊接 0305/0306/0307 之後。
#   · Qual:14bit 字串在 0xC2E44F2C 那張六筆表裡(§4 舊版說只有三個,錯的)。
#   · BitsPerSample 由 FUN_c02da870(enum 1) 直接給 14,原廠就對。
# 也就是 SIGMA 做好了 14-bit CINE 又把選單那一列收掉。我們只要補**一列 CSV**
# 加**清單上限**。比 240 fps 那一列省掉整個搬表的工。見 §4.1 / §8.4。
#
# 兩個變體:B2_5_2(全開)與 B2_5_2_excl(第 2/3 列反灰)。第四列**繼承第三列
# 的 Enabled**,和第十列格率的做法一致 —— excl 變體裡 12-bit 已經是 0,0,
# 14-bit 只會更嚴格,反灰是誠實的。
WITH_BIT_ROW = True
BIT_ROW_CSV = ((0xC0F8E6A8, 0xC0D4FA6C, "B2_5_2"),        # 全開
               (0xC0F8E71C, 0xC0D4DD9C, "B2_5_2_excl"))   # 第 2/3 列反灰
BIT_ROW_LEN = 113                   # 原廠用量(BOM 3 + 標頭 38 + 三列 x 24)
BIT_ROW_SLOT = 116                  # 槽距,只剩 3 B
BIT_ROW_TEXT = b"0308"              # 現成字串 ID,不用字面字串
# ★ 空間:把 **IMAGE 整欄拿掉**(不是留空)之後四列只要 107 B,槽 116 還剩 9 B,
#   而且**結尾 CRLF 保留得住** —— 那兩件事 2026-09-29 都上機驗過,見 §8.9。
#   先前的版本把 IMAGE 留空又拿掉 CRLF,兩個都是錯的形式。
# 清單控制器上限。記錄在 0xC1A690B7(+0x20 = max,BE float),
# 用的是與 B2_5_4 / B2_5_5 相同的 20 byte 簽名;五筆記錄的 max 指紋
# (1.0, 2.0, 1.0, 1.0, 8.0)逐一對上五個選單的列數(2,3,2,2,9)。
# ⚠ **這一顆沒有字對齊**(跨 0xC1A690D4 與 0xC1A690D8 兩個字),要讀改寫。
BIT_ROW_CAP = 0xC1A690D7
BIT_ROW_CAP_STOCK = b"\x40\x00\x00\x00"      # BE float 2.0
BIT_ROW_CAP_NEW = b"\x40\x40\x00\x00"        # BE float 3.0


def drop_image_column(lines):
    """`NO,TEXT,Popup,IMAGE,Enabled,Enabled2` -> `NO,TEXT,Popup,Enabled,Enabled2`。

    ★ **整欄拿掉,不是留空。** 2026-09-29 上機分辨出來的:
    `1,0305,Popup,,1,2`(留空)那一列**不會被畫出來**;
    `1,0305,Popup,1,2`(整欄拿掉)會。格率第十列先前的失敗就是留空造成的。

    `.cvm` 的欄位由第一行決定(全機 13 種表頭),所以少一欄是合法的形狀 ——
    fpSup-Formats 自己的 CSV 連 `Popup` 欄都沒有。
    """
    hdr = lines[0].split(b",")
    try:
        col = hdr.index(b"IMAGE")
    except ValueError:
        return lines
    out = []
    for r in lines:
        f = r.split(b",")
        out.append(b",".join(f[:col] + f[col + 1:]))
    return out


def bit_row_csv(img, res):
    """三列 -> 四列。拿掉 IMAGE 欄騰空間,第四列繼承第三列的 Enabled。

    ★ **結尾 CRLF 不能省。** 2026-09-29 上機:少了它最後一列不會被 parse,
    畫面上就只有三列。先前為了把 117 B 塞進 116 B 的槽把它拿掉了,
    那就是「選得到但看不見」的真正原因 —— 不是 NBU,是這兩個位元組。
    """
    raw = img[res - B: res - B + BIT_ROW_LEN]
    bom, body = raw[:3], raw[3:]
    lines = [l for l in body.split(b"\r\n") if l]
    if len(lines) != 4:
        raise SystemExit(f"{res:#x} 不是標頭 + 三列,而是 {len(lines)} 行")
    last = lines[-1].split(b",")
    if len(last) != 6:
        raise SystemExit(f"{res:#x} 欄數不是 6:{lines[-1]!r}")
    lines = lines + [b",".join([b"4", BIT_ROW_TEXT, last[2], last[3],
                                last[4], last[5]])]
    out = drop_image_column(lines)
    new = bom + b"\r\n".join(out) + b"\r\n"
    if len(new) > BIT_ROW_SLOT:
        raise SystemExit(f"{res:#x} 四列 {len(new)} B 超過槽 {BIT_ROW_SLOT}")
    return new


def csv_set_enabled(csv, flags):
    """把選單 CSV 的 Enabled / Enabled2 欄依 `flags` 改寫(True = 開,False = 灰)。

    反灰的唯一機制就是這兩欄:`1,2` = 可選、`0,0` = 反灰。原廠的六個
    `B2_5_5` 變體與 `B2_5_2_excl` 就是同一份列表的不同 Enabled 組合(§8.5)。

    ★ 這個函式是「mode 決定其他軸」那個設計的落點(§8.6):主機端拿它產生
      每個 mode 對應的列表,相機端之後要做的是**同一件事、在 RAM 裡**。
      **長度不變** —— 改寫只動那兩欄的值,不增刪位元組,所以槽與描述子長度
      都不用跟著動。
    """
    bom, body = csv[:3], csv[3:]
    lines = body.split(b"\r\n")
    rows = [i for i, l in enumerate(lines) if l]
    if len(rows) - 1 != len(flags):
        raise SystemExit(f"CSV 有 {len(rows) - 1} 列,flags 給了 {len(flags)} 個")
    # ★ 欄位**由表頭決定**,不能寫死索引 —— 全機 13 種表頭,而我們自己也會
    #   把 IMAGE 整欄拿掉(§8.9),寫死的話就會改到隔壁欄。
    hdr = lines[rows[0]].split(b",")
    try:
        c1, c2 = hdr.index(b"Enabled"), hdr.index(b"Enabled2")
    except ValueError:
        raise SystemExit(f"表頭沒有 Enabled / Enabled2:{lines[rows[0]]!r}")
    for i, on in zip(rows[1:], flags):
        f = lines[i].split(b",")
        f[c1], f[c2] = (b"1", b"2") if on else (b"0", b"0")
        lines[i] = b",".join(f)
    out = bom + b"\r\n".join(lines)
    if len(out) != len(csv):
        raise SystemExit(f"改寫後長度變了:{len(csv)} -> {len(out)}")
    return out


# ---- 選單的格率 -> AXIS ------------------------------------------------------
# picker 的鍵是「標籤 + 格率字串」,而格率字串是**選單選的那一個**。
# `imx410_fmt` 一直只比對標籤、把尾碼丟掉,所以 AXIS 的格率只能從主機改。
# 比對尾碼就接回來了,**零新增 hook**(那支 hook 已經掛著、鍵已經在手上)。
#
# ⚠ 接上之後**選單說了算**:先前 --axis-preset 設 240 而選單停在 120 時錄出
#   240,現在會變成 120。要測 240 就得把選單也切到第十列。見 §8.10。
WITH_RATE_FROM_MENU = True
RATESTR = 0xC0730160                # 11 筆 x 8 bytes

# ---- 收合摘要的 export enum <-> 狀態配對表 -------------------------------
# 2026-09-30 原生路徑核對：這是摘要轉換器，不是清單輸入表。
# 第十筆必須是 (export 11, state 9)。export 5 在原廠 picker suffix
# C043CAF0 會走 assert；internal 5 則是 59.94，兩者不能混為新 240。
# 真正 row/internal/export/rank 與媒體限制由 imx410_rate_native 提供；
# 三個 movw/movt/count 字仍負責把原廠九筆摘要表搬到私人區。
WITH_RATE_PAIR = True
RATE_PAIR = 0xC0730100              # 10 筆 x {列舉值, 列索引} = 80 B
RATE_PAIR_STOCK_TBL = 0xC2E44EE4
RATE_PAIR_STOCK_N = 9
RATE_PAIR_N = 10
RATE_PAIR_NEW_ENUM = 11             # 原廠 picker 的 240 export enum
# 三個要改的指令(位址, 原廠字)
RATE_PAIR_LO = 0xC06CB6DC           # movw r2, #0x4ee4
RATE_PAIR_HI = 0xC06CB6E0           # movt r2, #0xc2e4
RATE_PAIR_CNT = 0xC06CB6E8          # mov  r2, #9
RATE_PAIR_STOCK = (0xE3042EE4, 0xE34C22E4, 0xE3A02009)


def _movw(rd, imm):
    return 0xE3000000 | ((imm >> 12) & 0xF) << 16 | (rd << 12) | (imm & 0xFFF)


def _movt(rd, imm):
    return 0xE3400000 | ((imm >> 12) & 0xF) << 16 | (rd << 12) | (imm & 0xFFF)


def _mov_imm(rd, val):
    if not 0 <= val <= 0xFF:
        raise SystemExit(f"mov r{rd},#{val} 不是單一 rotate-immediate")
    return 0xE3A00000 | (rd << 12) | val


def rate_pair_table(img):
    """原廠九筆 + 第十筆 `(11, 9)`,小端位元組。

    原廠那九筆**逐字照抄**,不重新產生 —— 抄比算安全,而且抄的時候順便
    驗證它真的是 `(enum, 索引)` 且索引是 0..8 連號。
    """
    raw = img[RATE_PAIR_STOCK_TBL - B:
              RATE_PAIR_STOCK_TBL - B + RATE_PAIR_STOCK_N * 8]
    pairs = [struct.unpack_from("<II", raw, i * 8)
             for i in range(RATE_PAIR_STOCK_N)]
    if [p[1] for p in pairs] != list(range(RATE_PAIR_STOCK_N)):
        raise SystemExit(f"原廠配對表的列索引不是 0..8 連號:{pairs}")
    if RATE_PAIR_NEW_ENUM in {p[0] for p in pairs}:
        raise SystemExit(f"列舉值 {RATE_PAIR_NEW_ENUM} 原廠已經在用了")
    pairs.append((RATE_PAIR_NEW_ENUM, RATE_PAIR_STOCK_N))
    return b"".join(struct.pack("<II", *p) for p in pairs)


# Native row/internal/export conversion, CUSTOM CinemaDNG list and cap gates.
# Individually pinned hooks, exercised by test_imx410_rate_native against
# original firmware functions; stock behavior is retained outside FLAG=1/FMT=0.
WITH_RATE_NATIVE = True
# ★ 2026-10-02 只在 --b25-menu 卡(私有 B2_5 頁)才開:CUSTOM 下格率 / 位元深度改用私有清單
#   SL_RATE / SL_BIT(sl_lists.py、sl_excl.S),原廠清單保持原廠(不加 239.76 / 14-bit 列、
#   不改上限)。開了它就必須同時關 WITH_RATE_ROW / WITH_BIT_ROW(card builder 一起設)。
WITH_SL_EXCL = False
WITH_RATE_UI = True
WITH_RATE_LV = True
FRCLASS_HOOK, FRCLASS_STOCK = 0xC04A121C, 0xE1A00001
WITH_FRCLASS = WITH_RATE_NATIVE

SEL_HOOK, SEL_STOCK = 0xC005C020, 0xE92D4070     # 解析度 setter
NAM_HOOK, NAM_STOCK = 0xC0437B48, 0xE92D4BF0     # 解析度名發射器
OFM_HOOK, OFM_STOCK = 0xC005BE58, 0xE92D4070     # 錄影格式 setter
OUT_HOOK, OUT_STOCK = 0xC0437E98, 0xE92D4030     # 主輸出描述子
# 快門角度的四條路徑,各一條本地 BL FUN_c032c750。
FPS_HOOKS = ((0xC02092CC, 0xEB048D1F, "主要 exposure property"),
             (0xC0218AEC, 0xEB044F17, "angle metadata path A"),
             (0xC0219260, 0xEB044D3A, "angle metadata path B"),
             (0xC03AA568, 0xEBFE0878, "resolution reconfiguration sync"))

# ---- 預覽 profile 的可見高 ----------------------------------------------
# 六個 PARAM +0x28(可見高)。來源 og3k_plan.PREV —— 待機用 profile 5,
# 半按與錄影切到別的兄弟,所以六個都要補。
PREV_PROFILES = (0xC0BDB9CC, 0xC0BDBC28, 0xC0BDBC60,
                 0xC0BDBC8C, 0xC0BDBC90, 0xC0BDBC94)
PREV_STOCK_H = 1125          # 原廠 16:9
# 同樣六列的 +0x20(可見寬),原廠 2000。2026-10-04:待機可見範圍要等於錄影中 LV
# 顯示的區域(imx410_profile.standby_visible),寬也要跟著改 —— 否則按下錄影畫面
# 放大 ~10 px(M12 AUTO 實機)。GTAB 第二組。
PREV_STOCK_W = 2000
PREV_RASTER_W, PREV_RASTER_H = 2016, 1344
PREV_VISIBLE_W = 2000
PREV_MAX_H = PREV_RASTER_H - 10      # 與原廠邊距同構(寬 16 / 高 10)


def preview_visible_height(axis=None):
    """待機預覽的可見高,由配方的**顯示比**算出來。

    3:2 -> 1334(= 上限)、16:9 -> 1125(= 原廠)、21:9 -> 857。
    比 3:2 更方的(4:3、1:1)算出來會超過光柵,夾在上限 —— 那時畫面會左右
    留黑,而不是被拉長。
    """
    from imx410_block import ASPECT_TABLE, R_ASPECT, expected_recipe
    r = expected_recipe(Registry(), axis or INITIAL_AXIS)
    x, y = ASPECT_TABLE.get(r[R_ASPECT], (3, 2))
    # **不要強制偶數** —— 原廠的 16:9 值 1125 本身就是奇數,進位成 1126 就
    # 偏離了唯一一個已知good的值。
    h = min(PREV_MAX_H, PREV_VISIBLE_W * y // x)
    # 3:2 純算比例是 1333,但 og3k 驗證過的是 **1334** —— 那個值不是比例算的,
    # 是邊距慣例(2016-2000=16、1344-1334=10,與原廠同構)。差一像素,但 1334
    # 是唯一已知good的,靠近上限就吸附過去。
    return PREV_MAX_H if PREV_MAX_H - h <= 4 else h


# ---- 選單 ------------------------------------------------------------------
CSV_ADDR = 0xC0F8E7EC            # 解析度清單的 CSV,原廠 89 B / 槽 92 B
CSV_SLOT = 92
CTRL_CAP = 0xC1A709BC            # 清單控制器上限,BE float 1.0 -> 2.0
# 使用者要「刪掉 FHD/UHD,只留 CUSTOM」。**用 Enabled 欄關掉,不是刪列** ——
# 刪列會讓 enum 重新編號(enum<->列 配對表 0xC2E4020C 是照列數建的),
# og3ksel 的 `cmp r1,#4` 就會選到別的東西。B2_5_5 的六個變體本來就是用
# Enabled=0,0 做閘門的,同一個機制。
# ⚠ 「游標會不會卡在被關掉的第一列」還沒上機驗過。
# ★ 2026-09-30 修掉三個格式錯誤。舊版是 og3k 時代留下來的:
#   · 第 1、2 列用 `\n` 不是 `\r\n`
#   · **沒有結尾 CRLF** —— §8.9 上機證實最後一列不會被 parse
#   · IMAGE 欄留空(`,,`)—— §8.9 上機證實那一列畫不出來,要給實值或整欄拿掉
#   再加上寫入時保留了原廠尾巴,所以相機上讀到的是 `3,CUSTOM,,1,2k,1,2`。
#   現在每列都給 `blank`、每列都以 CRLF 結尾,槽內其餘補 NUL。
# ★ 2026-10-02 使用者改主意:「有辦法保留 fhd uhd 嗎?」—— 保留。關掉它們從來
#   不是技術需要(hook 只在 CUSTOM 下接手,其餘走原廠;OG3K 一直是三列並存)。
#   關掉的代價在實機看到了:用 QS 改成 FHD/UHD 之後,選單裡游標停在被關掉的列。
#   False 回到「只留 CUSTOM」。
WITH_RES_STOCK_ROWS = True
_RES_STOCK = b"1,2" if WITH_RES_STOCK_ROWS else b"0,0"
_CSV = (b"\xef\xbb\xbfNO,TEXT,IMAGE,Enabled,Enabled2\r\n"
        b"1,0313,blank," + _RES_STOCK + b"\r\n"
        b"2,0314,blank," + _RES_STOCK + b"\r\n"
        b"3,CUSTOM,blank,1,2\r\n")
assert len(_CSV) <= 92, len(_CSV)
assert _CSV.endswith(b"\r\n"), "最後一列沒有 CRLF 就不會被 parse(§8.9)"
assert b",," not in _CSV, "留空的欄位那一列畫不出來(§8.9)"

# 初始配方。載入之後選單停在 CUSTOM 就是這一組;之後由 AXIS 決定。
INITIAL_AXIS = axis_words(bit=12, rate="30", raster=(3032, 2012))

# 畫布模板的長度上限:全部閘門都開 + 表尾。CTMPL 區塊照這個宣告,
# 這樣不管用哪一組軸安裝,區塊圖都是誠實的。
CTMPL_MAX = len(CANVAS_TEMPLATE) * 4 + 4
def _profile():
    """donor PARAM profile —— **由引擎依配方的幾何挑**,不是寫死。

    2026-09-28 三次錄影凍結的根因就是寫死 13:p13 的 rec/act 是 0x0(空殼),
    而我又把「填滿空殼」的那六欄關掉了。見 imx410_block.pick_profile。
    """
    from imx410_block import R_RECH, R_RECW, expected_recipe, pick_profile
    r = expected_recipe(Registry(), INITIAL_AXIS)
    return pick_profile((r[R_RECW], r[R_RECH]))[0]


PROFILE = _profile()          # 底列:私有 id 指向它那一列(預設 = p83,OG3K 已驗證)

# ★ 我們自己的 profile id(2026-10-04)。原本直接用原廠 id(p83),但 p83 也被
#   拍照表 0xC0BE5D70 引用,畫布守衛只看 id,等於連 S 尺寸 12-bit 拍照都會被改寫;
#   而且 id 寫死在兩個立即值裡。改成:
#     - 列對照表 mapping[0xC0BD05D4 + id*4] 的空槽 87 指向底列(安裝時寫一個字),
#     - id 放在 RAM 字 PROFILE_ID,picker 表項與畫布守衛都讀它。
#   87 原廠是空槽(0xFFFFFFFF,沒有人會載入它);FUN_c043a1c8 依 id 數值分類,
#   87 與 83 同屬「全部旗標 0」那一類(17..28 / 29..40 / 101..129 / 131..190 …
#   都不含它),所以增益等分類行為不變。預設組態的列位元組與 p83 時代逐字相同。
MAPPING = 0xC0BD05D4
PRIVATE_PROFILE = 87
DECL_ROWS = (6, 7)            # 宣告列的雙緩衝:p13 / p14 的列,全韌體沒有別的 id 指向它們


def prev_width_addrs(img=None):
    """六個待機 profile 的 +0x20 位址:+0x28 欄表上的列號 -> +0x20 欄表。"""
    img = img if img is not None else FIRMWARE.read_bytes()
    cols = column_tables(img)
    col28, col20 = cols[0x28 // 4], cols[0x20 // 4]
    out = []
    for a in PREV_PROFILES:
        row, rem = divmod(a - col28, 4)
        if rem or not 0 <= row < 306:
            raise SystemExit(f"{a:#x} 不在 +0x28 欄表上")
        w = col20 + row * 4
        if _img_word(img, w) != PREV_STOCK_W or _img_word(img, a) != PREV_STOCK_H:
            raise SystemExit(f"待機 profile 列 {row}:+0x20 = {_img_word(img, w)},+0x28 = {_img_word(img, a)}")
        out.append(w)
    return tuple(out)


def _declared():
    from imx410_profile import DECLARED_BY_PANEL
    return DECLARED_BY_PANEL


def column_tables(img=None):
    """65 張欄表的位址,依欄位位移排(FUN_c0439d18 從它們組出一列 profile)。

    來源是外部分析的 raw-profiles.json;這裡用映像逐欄驗證:每張表在 p83 的列
    (以及兩個宣告列)讀到的字,必須等於 json 裡那一列的值。對不上就不准建卡。"""
    import json
    from imx410_block import _PROFILE_JSON
    img = img if img is not None else FIRMWARE.read_bytes()
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent.parent.parent
    d = json.loads((root / _PROFILE_JSON).read_text())
    cols = sorted(d["columns"], key=lambda c: c["offset"])
    assert [c["offset"] for c in cols] == list(range(0, 65 * 4, 4))
    rows = {r["index"]: r["words"] for r in d["rows"]}
    for row in (d["mapping"][83],) + DECL_ROWS:
        for c in cols:
            got = _img_word(img, c["table"] + row * 4)
            if got != rows[row][c["offset"] // 4]:
                raise SystemExit(f"欄表 {c['table']:#x}(欄 {c['offset']:#x})列 {row} = {got:#x},"
                                 f"json 說 {rows[row][c['offset'] // 4]:#x}")
    return [c["table"] for c in cols]
PICKOK = 0xC0731C44
FPSLATCH = 0xC0731C40


def _og3k_defines():
    """沿用 og3k_plan 的那幾顆要的 -D。幾何取初始配方的值。

    ⚠ TARGET_AW/AH 是**編譯期**的,og3kname 的回放辨識路徑會拿它比對尺寸。
    配方換了之後那條路就對不上 —— 回放本來就還沒接(MISSING),一併記著。
    """
    reg = Registry()
    from imx410_block import expected_recipe, R_ACTW, R_ACTH, R_RECW, R_RECH
    r = expected_recipe(reg, INITIAL_AXIS)
    return [f"TARGET_PROF={PROFILE}",
            f"TARGET_W={r[R_RECW]}", f"TARGET_H={r[R_RECH]}",
            f"TARGET_AW={r[R_ACTW]}", f"TARGET_AH={r[R_ACTH]}",
            "TARGET_MODE=0", "TARGET_MODE_TIMING=0xC0B59500",
            "TARGET_MODE_W0=0", "TARGET_MODE_W1=0",
            "TARGET_FMT_GUARD=1", f"TARGET_MATCH={PICKOK:#x}",
            f"TARGET_LABEL={int.from_bytes(b'CUST', 'little'):#x}",
            f"TARGET_ENGFPS={FPSLATCH:#x}"]


def payloads():
    """位址要**當場**從模組全域讀,不能在 import 時捕捉成常數。

    第一版寫成 module-level tuple,結果「檢查器自己會不會抓」那兩個測試改了
    位址卻毫無作用 —— 檢查器看起來很乾淨,其實測不到。
    """
    return (("og3krecipe",     "og3krecipe.S",    RECIPE_CODE),
            ("imx410_fmt",     "imx410_fmt.S",    FMT_CODE),
            ("imx410_canvas",  "imx410_canvas.S", CANVAS_CODE),
            ("imx410_aspect",  "imx410_aspect.S", ASP_CODE),
            ("imx410_aspect2", "imx410_aspect.S", ASP2_CODE),
            # 這兩顆原始碼原樣沿用 og3k_plan 的。og3kgs 只看 FLAG,與目標無關;
            # og3krange 只換範圍(單一 ENTRY,不是九筆的靜態表)。
            ("imx410_fps",     "imx410_fps.S",    FPS_CODE),
            *((("imx410_rate", "imx410_rate.S", RATE_CODE),) if WITH_RATE else ()),
            ("og3kgs",         "og3kgs.S",        GS_CODE),
            *((("og3krange", "og3krange.S", RNG_CODE),) if WITH_RANGE else ()),
            ("og3ksel",        "og3ksel.S",       SEL_CODE),
            ("og3kname",       "og3kname.S",      NAME_CODE),
            ("og3kfmt",        "og3kfmt.S",       OGFMT_CODE),
            ("og3krestore",    "og3krestore.S",   RESTORE_CODE),
            ("og3kout",        "og3kout.S",       OUT_CODE),
            *((("imx410_poff", "imx410_poff.S", POFF_CODE),) if WITH_BIT_POFF else ()),
            *(RATE_NATIVE.payloads() if WITH_RATE_NATIVE else ()),
            *(SLX.payloads() if WITH_SL_EXCL else ()),
            *(BIT14.payloads() if _with_bit14() else ()),
            *(SELLOG.payloads() if WITH_SEL_LOG else ()),
            *(BINFILT.payloads() if _with_binfilt() else ()))


def _with_binfilt():
    return WITH_SL_EXCL and WITH_BINFILT


def _with_bit14():
    """14-bit as a RAM marker needs sl_excl ROLE 14 (the bit-depth setter)."""
    return WITH_SL_EXCL and SLX.WITH_BIT14


def entry_point():
    """卡片的 BIN 入口:有 14-bit 關機改回時是 imx410_poff(它會再呼叫 RESTORE_CODE)。"""
    return POFF_CODE if WITH_BIT_POFF else RESTORE_CODE


def defines():
    return {
        **({k: v + ([f"LIVE={SLX.LIVE_TARGETS[int(k.rsplit('_', 1)[1])]:#x}"]
                    if WITH_SL_EXCL and int(k.rsplit('_', 1)[1]) in SLX.LIVE_TARGETS else [])
            for k, v in RATE_NATIVE.defines().items()} if WITH_RATE_NATIVE else {}),
        **({name: SLX.defines(int(name.rsplit("_", 1)[1])) for name, _, _ in SLX.payloads()}
           if WITH_SL_EXCL else {}),
        **(BIT14.defines() if _with_bit14() else {}),
        **(SELLOG.defines(_with_binfilt()) if WITH_SEL_LOG else {}),
        **(BINFILT.defines(0xC0731C08, AXIS) if _with_binfilt() else {}),
        "og3krecipe": [f"AXIS={AXIS:#x}", f"RECIPE={RECIPE:#x}",
                       f"RATETAB={RATETAB:#x}", f"TMGTAB={TMGTAB:#x}",
                       f"CTMPL={CTMPL:#x}", f"CANVAS={CANVAS:#x}",
                       f"ASPTAB={ASPTAB:#x}"],
        "imx410_fmt": [f"RECIPE={RECIPE:#x}", f"RECIPE_CODE={RECIPE_CODE:#x}",
                       f"ENTRY={ENTRY_ADDR:#x}", f"HITS={HITS:#x}",
                       f"PROFILE_ID={PROFILE_ID:#x}", f"AXIS={AXIS:#x}"]
                      + (["WITH_BIT_FROM_MENU=1"] if WITH_BIT_FROM_MENU else [])
                      + ([f"BIT14={BIT14.BIT14:#x}"] if WITH_BIT_FROM_MENU and _with_bit14() else [])
                      + ([f"RATESTR={RATESTR:#x}",
                         "WITH_RATE_FROM_MENU=1"]
                         + ([f"RATE240={RATE_NATIVE.RATE240:#x}"] if WITH_RATE_NATIVE else [])
                         if WITH_RATE_FROM_MENU else []),
        "imx410_canvas": [f"CANVAS={CANVAS:#x}", f"PROFILE_ID={PROFILE_ID:#x}"],
        # 同一份原始碼組兩次,只有回跳位址不同。
        "imx410_aspect": [f"RECIPE={RECIPE:#x}", f"BACK={ASP_HOOK + 4:#x}"],
        **({"imx410_rate": [f"RECIPE={RECIPE:#x}", f"AXIS={AXIS:#x}",
                            f"RATNUM={RATNUM:#x}",
                            f"BACK={RAT_HOOK + 4:#x}"]} if WITH_RATE else {}),
        "imx410_aspect2": [f"RECIPE={RECIPE:#x}", f"BACK={ASP2_HOOK + 4:#x}"],
        "imx410_fps": [f"RECIPE={RECIPE:#x}"],
        "og3kgs": [],
        # og3ksel:動態 donor 還原 + 錄影格式守衛。
        "og3ksel": _og3k_defines() + [f"TARGET_DYN_DONOR={RECIPE:#x}",
                                      "TARGET_DYN_IMAGER=0xC343B588"],
        "og3kname": _og3k_defines(),
        "og3kfmt": _og3k_defines(),
        "og3krestore": _og3k_defines(),
        "og3kout": _og3k_defines(),
        **({"imx410_poff": [f"CODE={POFF_CODE:#x}", f"OBJ={POFF_OBJ:#x}",
                            f"STATE={POFF_STATE:#x}", f"RESTORE={RESTORE_CODE:#x}"]}
           if WITH_BIT_POFF else {}),
        **({"og3krange": [f"OURLO={ENTRY_ADDR:#x}",
                          f"OURHI={ENTRY_ADDR + 48:#x}"]} if WITH_RANGE else {}),
    }


# Loader v3 (og_pic.inc; projects/usb-shell-sup/notes/LOADER_V3.md step 6): the
# same payloads, assembled position-independent against the old cave layout.
# A cave address handed in as a -D becomes a layout coordinate (OGA), each
# payload learns its own coordinate (OG_ORG).  Without OG_V3, nothing changes.
import os as _os
V3 = _os.environ.get("OG_V3") == "1"
V3_CAVE0, V3_SPAN = 0xC0730000, 0x8000
V3_OGV = int(_os.environ.get("OG_V3_OGV", hex(V3_CAVE0)), 0)


def ogv(address):
    """A cave address as the OG_V3 assembly sees it (og_pic.inc OGA)."""
    return address - V3_CAVE0 + V3_OGV if V3 else address


def _v3_defines(defs, base):
    if not V3:
        return defs
    out = []
    for d in defs:
        k, _, v = d.partition("=")
        try:
            n = int(v, 0)
        except ValueError:
            out.append(d)
            continue
        out.append(f"{k}={ogv(n):#x}" if V3_CAVE0 <= n < V3_CAVE0 + V3_SPAN else d)
    return out + ["OG_V3=1", "OG_V3_PAIR=1", f"OGV={V3_OGV:#x}", f"OG_ORG={ogv(base):#x}"]


V3_PAIRS = {}            # payload -> pairs og_pic.py rewrote (the last blobs())


def blobs():
    d = defines()
    out = {name: assemble(src, defines=_v3_defines(d[name], base))
           for name, src, base in payloads()}
    if V3:
        from og_pic import pc_relative
        for name, _, base in payloads():
            out[name], V3_PAIRS[name] = pc_relative(out[name], ogv(base), V3_OGV,
                                                    V3_OGV + V3_SPAN)
    return out


def regions(bl=None):
    """(起, 迄, 名稱) —— 這份計畫會寫到的每一塊。"""
    bl = bl or blobs()
    out = [(addr, addr + len(bl[name]), name) for name, _, addr in payloads()]
    if WITH_RATE_NATIVE:
        out += [(a, a + len(data), name)
                for name, a, data in RATE_NATIVE.tables(FIRMWARE.read_bytes())]
    out += [(AXIS, AXIS + AXIS_WORDS * 4, "AXIS"),
            (RECIPE, RECIPE + RECIPE_WORDS * 4, "RECIPE"),
            (ENTRY_ADDR, ENTRY_ADDR + 48, "ENTRY"),
            (CANVAS, CANVAS + 4 + CANVAS_MAX_PAIRS * 8, "CANVAS"),
            (RATETAB, RATETAB + len(rate_table()), "RATETAB"),
            (RATNUM, RATNUM + len(ratnum_table()), "RATNUM"),
            (TMGTAB, TMGTAB + len(timing_table()), "TMGTAB"),
            # ★ 照**上限**宣告,不是照 INITIAL_AXIS。模板的長度由安裝時的軸
            #   決定(閘門在 canvas_template 裡就解掉了):預設軸 56 B,但
            #   RWZM/bin 非預設的軸會長到 72 B,全閘門開是 120 B。照初始軸宣告
            #   等於換軸安裝時區塊圖是假的,layout_errors() 也就擋不住越界。
            (CTMPL, CTMPL + CTMPL_MAX, "CTMPL"),
            (ASPTAB, ASPTAB + len(aspect_q_table()), "ASPTAB"),
            (HITS, HITS + 4, "HITS"),
            (PROFILE_ID, PROFILE_ID + 4, "PROFILE_ID"),
            (COLTAB, COLTAB + len(_declared()) * 4, "COLTAB"),
            *([(RATE_PAIR, RATE_PAIR + RATE_PAIR_N * 8, "RATE_PAIR")]
              if WITH_RATE_PAIR else []),
            *([(RATESTR, RATESTR + len(ratestr_table()), "RATESTR")]
              if WITH_RATE_FROM_MENU else []),
            # 共用鎖存與紀錄。它們不是 payload 也不是資料區塊,但 payload 會
            # 指向它們,所以稽核要認得(test_payloads_only_touch_owned_cave)。
            (NAME, NAME + 8, "名稱字串"),
            (0xC0731C00, 0xC0731C10, "og3ksel 紀錄 / FLAG / PBFLAG"),
            (0xC0731C14, 0xC0731C18, "BITLATCH"),
            (0xC0731C20, 0xC0731C24, "FMTLATCH"),
            (0xC0731C24, 0xC0731C40, "og3krestore 紀錄"),
            (FPSLATCH, FPSLATCH + 4, "FPSLATCH"),
            (PICKOK, PICKOK + 4, "PICKOK"),
            *([(POFF_OBJ, POFF_OBJ + 4, "POFF 物件"), (POFF_STATE, POFF_STATE + 16, "POFF 紀錄")]
              if WITH_BIT_POFF else []),
            *([(RATE_NATIVE.RATE240, RATE_NATIVE.RATE240 + 4, "RATE240 記號(只在記憶體)")]
              if WITH_RATE_NATIVE else []),
            (SL_MENU_MARK, SL_MENU_MARK + SLX.MARK_BYTES, "sl_menu / sl_excl 紀錄"),
            *(BIT14.regions() if _with_bit14() else []),
            *([(SELLOG.LOG, SELLOG.LOG + SELLOG.LOG_BYTES, "SELLOG")] if WITH_SEL_LOG else []),
            *([(BINFILT.BINFILT, BINFILT.BINFILT + 4, "BINFILT x3 縮減核模式")] if _with_binfilt() else []),
            (GTAB, GTAB + 0x100, "GTAB"),
            (0xC0732000, 0xC0732080, "og3kout 模板與計數"),
            (0xC07328C0, 0xC07328C4, "og3kgs 紀錄"),
            (0xC0732A00, 0xC0732A14, "畫布紀錄")]
    return sorted(out)


# Source-only coordinates: stock non-zero words live here, so nothing may ever
# be written at these addresses.  Only the listed payloads use them, and only
# as labels the USER packer maps (res_lab_user_pack.OLD_HIGH = 0xC0736000).
SOURCE_ONLY_LO, SOURCE_ONLY_HI = 0xC0734C84, 0xC0736000
SOURCE_ONLY_PAYLOADS = {"imx410_fmt", "sl_excl_14", "imx410_sellog", "SELLOG",
                        "imx410_binfilt_1", "imx410_binfilt_2"}
# hbin/vbin x3 的縮減核 Box / Std / Sharp(imx410_binfilt),選單卡
WITH_BINFILT = True
# 診斷:路徑選擇器紀錄(imx410_sellog);產品卡關掉
WITH_SEL_LOG = True


def layout_errors(bl=None):
    """配置自我檢查。位址是用手挑的,所以每一條都要有東西擋著。"""
    bad = []
    rs = regions(bl)
    for (a0, a1, n0), (b0, b1, n1) in zip(rs, rs[1:]):
        if b0 < a1:
            bad.append(f"{n0} [{a0:#x},{a1:#x}) 與 {n1} [{b0:#x},{b1:#x}) 重疊")
    for a0, a1, n in rs:
        if n in SOURCE_ONLY_PAYLOADS and SOURCE_ONLY_LO <= a0 and a1 <= SOURCE_ONLY_HI:
            pass                     # never installed here: the packer moves it to USER
        elif not (CAVE_LO <= a0 and a1 <= CAVE_HI):
            bad.append(f"{n} [{a0:#x},{a1:#x}) 超出 cave "
                       f"[{CAVE_LO:#x},{CAVE_HI:#x})")
        for f0, f1 in FORBIDDEN:
            if a0 < f1 and f0 < a1:
                bad.append(f"{n} [{a0:#x},{a1:#x}) 撞到禁區 [{f0:#x},{f1:#x})")
    return bad


def hook_errors(img=None):
    """套用之前:每個 hook 點在參考映像裡必須還是原廠指令。"""
    img = img if img is not None else FIRMWARE.read_bytes()
    bad = []
    for addr, stock, name in ((PIK_HOOK, PIK_STOCK, "picker"),
                              (ROW_HOOK, ROW_STOCK, "畫布"),
                              (ASP_HOOK, ASP_STOCK, "長寬比1"),
                              (ASP2_HOOK, ASP2_STOCK, "長寬比2"),
                              (GS_HOOK, GS_STOCK, "增益分派"),
                              *(((RAT_HOOK, RAT_STOCK, "容器格率"),)
                                if WITH_RATE else ()),
                              *(((RNG_HOOK, RNG_STOCK, "範圍檢查"),)
                                if WITH_RANGE else ()),
                              (SEL_HOOK, SEL_STOCK, "解析度 setter"),
                              (NAM_HOOK, NAM_STOCK, "解析度名"),
                              (OFM_HOOK, OFM_STOCK, "錄影格式 setter"),
                              (OUT_HOOK, OUT_STOCK, "主輸出描述子")):
        got = int.from_bytes(img[addr - B: addr - B + 4], "little")
        if got != stock:
            bad.append(f"{name} hook {addr:#x} 是 {got:#010x},預期 {stock:#010x}")
    if WITH_RATE_NATIVE:
        try:
            RATE_NATIVE.patches(img)  # validates every native bridge site
        except ValueError as error:
            bad.append(str(error))
    for addr, stock, note in FPS_HOOKS:
        got = int.from_bytes(img[addr - B: addr - B + 4], "little")
        if got != stock:
            bad.append(f"快門角度 {note} {addr:#x} 是 {got:#010x},預期 {stock:#010x}")
    return bad


def _bl(src, dst):
    """ARM BL src -> dst。"""
    off = (dst - (src + 8)) >> 2
    return 0xEB000000 | (off & 0xFFFFFF)


def _b(src, dst):
    """ARM B src -> dst(不動 lr)。"""
    off = (dst - (src + 8)) >> 2
    return 0xEA000000 | (off & 0xFFFFFF)


HOOK_STAGES = None      # _stages() 的快取,由下面補上


def _fill_for(recipe_axis=None):
    """這個配方的 donor 是不是空殼(要不要填滿那六欄)。"""
    from imx410_block import R_RECH, R_RECW, expected_recipe, pick_profile
    r = expected_recipe(Registry(), recipe_axis or INITIAL_AXIS)
    return pick_profile((r[R_RECW], r[R_RECH]))[1]


def _img_word(img, addr):
    return struct.unpack_from("<I", img, addr - 0xC0000000)[0]


def plan(recipe_axis=None, stages=None):
    """(位址, 值, 註解) 的串列,順序就是安全的套用順序。

    ★ payload 一律在指著它的 hook 之前。2026-09-12 踩過:把指向 payload 的
      函式指標排在 payload 之前,相機下一次畫解析度名就跳進未初始化記憶體,
      載入中途凍結(notes/OG3K_RWZM_AND_BUILD_PIPELINE.md §4)。
    """
    bl = blobs()
    img = FIRMWARE.read_bytes()
    items = []

    def words(addr, data, note):
        for i, v in enumerate(struct.unpack(f"<{len(data)//4}I", data)):
            items.append((addr + i * 4, v, note))

    def put(addr, value, note):
        items.append((addr, value, note))

    def put_bytes(addr, data, note):
        """任意對齊的位元組寫入 —— 對涵蓋的每個字做讀改寫。

        UI pack 是位元組緊湊排列的,清單上限不保證落在字邊界上
        (B2_5_2 的就跨兩個字)。mem_set 只寫字,所以這裡從映像把原字讀出來、
        換掉要改的位元組、整字寫回。只碰指定的範圍,其餘位元組逐一保留。
        """
        lo = addr & ~3
        hi = (addr + len(data) + 3) & ~3
        buf = bytearray(img[lo - B: hi - B])
        buf[addr - lo: addr - lo + len(data)] = data
        for i, v in enumerate(struct.unpack(f"<{len(buf) // 4}I", bytes(buf))):
            items.append((lo + i * 4, v, note))

    # 1. 資料表(hook 還沒武裝,先寫什麼都安全)
    words(RATETAB, rate_table(), "格率常數表")
    words(RATNUM, ratnum_table(), "容器格率有理數表")
    if WITH_RATE_NATIVE:
        for name, address, data in RATE_NATIVE.tables(img):
            words(address, data, name)
    if WITH_RATE_UI:
        items.extend(RATE_UI.patches(img))
    if WITH_RATE_LV:
        items.extend(RATE_LV.patches(img))

    # ---- 選單第十列 239.76 fps ------------------------------------------
    if WITH_RATE_ROW:
        for res, desc, nm in RATE_ROW_CSV:
            csv = rate_row_csv(img, res)
            # 補 NUL 到原槽長度 —— 不留舊內容的尾巴,也不越過原本的佔用範圍。
            words(res, csv + b"\0" * (RATE_ROW_SLOT - len(csv)), f"{nm} CSV 十列")
            # 描述子的長度欄是 **BE**,在 +12。
            put(desc + 12,
                int.from_bytes(len(csv).to_bytes(4, "big"), "little"),
                f"{nm} 描述子長度 {RATE_ROW_LEN} -> {len(csv)}")
        put(RATE_ROW_CAP, RATE_ROW_CAP_NEW, "格率清單控制器上限 8.0 -> 9.0")

    # ---- 選單第四列 14 bit ----------------------------------------------
    if WITH_BIT_ROW:
        got = img[BIT_ROW_CAP - B: BIT_ROW_CAP - B + 4]
        if got != BIT_ROW_CAP_STOCK:
            raise SystemExit(f"位元深度清單上限 {BIT_ROW_CAP:#x} = {got.hex()},"
                             f"預期原廠 BE float 2.0")
        for res, desc, nm in BIT_ROW_CSV:
            csv = bit_row_csv(img, res)
            words(res, csv + b"\0" * (BIT_ROW_SLOT - len(csv)), f"{nm} CSV 四列")
            put(desc + 12,
                int.from_bytes(len(csv).to_bytes(4, "big"), "little"),
                f"{nm} 描述子長度 {BIT_ROW_LEN} -> {len(csv)}")
        put_bytes(BIT_ROW_CAP, BIT_ROW_CAP_NEW,
                  "位元深度清單控制器上限 2.0 -> 3.0")
    if WITH_RATE_PAIR:
        for a, stock in zip((RATE_PAIR_LO, RATE_PAIR_HI, RATE_PAIR_CNT),
                            RATE_PAIR_STOCK):
            got = int.from_bytes(img[a - B: a - B + 4], "little")
            if got != stock:
                raise SystemExit(f"配對表轉換器 {a:#x} = {got:#010x},"
                                 f"預期原廠 {stock:#010x}")
        words(RATE_PAIR, rate_pair_table(img), "格率 enum<->列 配對表(十筆)")
    if WITH_RATE_FROM_MENU:
        words(RATESTR, ratestr_table(), "格率鍵尾碼字串表")
    if WITH_BIT_POFF:
        words(POFF_STATE, b"\x00" * 16, "POFF 紀錄清零")
    if WITH_RATE_NATIVE:
        # ⛔ 第一守則:239.76 只存在這個記憶體記號,原廠設定只會是 119.88。
        #   loader 每次開機寫 0 —— 冷開機與保留 RAM 的熱開機都從 119.88 開始。
        put(RATE_NATIVE.RATE240, 0, "RATE240 記號歸零")
    if _with_bit14():
        # ⛔ 第一守則:14-bit 只存在 BIT14 這個記憶體記號,原廠設定只會是 12-bit。
        words(BIT14.BIT_PAIR, BIT14.pairs(img), "位深 enum<->列 配對表(第 4 列交 12-bit)")
        put(BIT14.BIT14, 0, "BIT14 記號歸零")
    if _with_binfilt():
        BINFILT.check(img)
        put(BINFILT.BINFILT, 0, "BINFILT = 0 Box")
    if WITH_SEL_LOG:
        SELLOG.check(img)
        words(SELLOG.LOG, b"\0" * SELLOG.LOG_BYTES, "路徑選擇器紀錄清零")
    words(TMGTAB, timing_table(), "時序預算表")
    words(ASPTAB, aspect_q_table(), "長寬比定點表")

    # 2. AXIS 初值。**必須在 payload 之前**:og3krecipe 一被叫到就會讀它。
    ax = recipe_axis or INITIAL_AXIS
    words(CTMPL, canvas_template(_fill_for(recipe_axis), ax), "畫布模板")
    words(AXIS, struct.pack(f"<{AXIS_WORDS}I", *ax), "AXIS 初值")

    # 3. 結果區清零。故障安全:valid=0、畫布對數 0 = 「還沒算出配方」,
    #    imx410_fmt 會走 FHD fallback、imx410_canvas 一個字都不碰。
    words(RECIPE, b"\x00" * (RECIPE_WORDS * 4), "RECIPE 清零")
    words(ENTRY_ADDR, b"\x00" * 48, "ENTRY 清零")
    words(CANVAS, b"\x00" * (4 + CANVAS_MAX_PAIRS * 8), "CANVAS 清零")
    items.append((HITS, 0, "命中計數清零"))

    # 3b. 我們的 profile:私有 id 的列對照指向底列,再公布 id。**在 payload 之前**:
    #     picker 一命中就會把 PROFILE_ID 寫進 ENTRY,韌體隨即用 mapping 找列。
    slot, base = MAPPING + PRIVATE_PROFILE * 4, MAPPING + PROFILE * 4
    if _img_word(img, slot) != 0xFFFFFFFF:
        raise SystemExit(f"mapping[{PRIVATE_PROFILE}] = {_img_word(img, slot):#x},預期原廠空槽 0xFFFFFFFF")
    put(slot, _img_word(img, base), f"mapping[{PRIVATE_PROFILE}] -> p{PROFILE} 的列(私有 profile)")
    put(PROFILE_ID, PRIVATE_PROFILE, "PROFILE_ID = 私有 profile id")
    cols = column_tables(img)
    words(COLTAB, struct.pack(f"<{len(_declared())}I", *(cols[o // 4] for o in _declared())),
          "欄表位址(宣告列那 29 欄)")

    # 4. payload
    for name, _, addr in payloads():
        words(addr, bl[name], f"{name} payload")
    if WITH_BIT_POFF:
        # 物件指向 payload 內的 vtbl,所以排在 payload 之後(順序檢查器要求)。
        from armasm import symbols
        vt = symbols("imx410_poff.S", defines()["imx410_poff"])["obj_vtbl"]
        put(POFF_OBJ, POFF_CODE + vt, "POFF 回呼物件 -> vtbl")

    # 5. 名稱字串、分組表、選單
    nm = b"CUST" + b"\x00" * 4
    words(NAME, nm, "名稱字串 CUST")
    # 分組表:一組,六個預覽 profile 的可見高,跟著旗標切換。
    #
    # ★ 2026-09-28 上機:原本設 0 組,結果**畫面被拉長** —— 長寬比 hook 在
    #   FLAG 立起來時回報 3:2,而那六個預覽 profile 仍宣告 2000x1125(16:9),
    #   16:9 的畫面被撐滿 3:2 的框。那是我用註解打發掉的東西到期了。
    #
    #   og3k 寫死 1334 是因為它永遠是 3:2;全功能版的比例是算出來的,所以
    #   這個值要跟著配方走。那六個 profile 是 FHD 共用的,所以**一定**要
    #   跟著旗標還原,不能寫死。
    #
    #   預覽光柵固定 2016x1344、可見寬固定 2000,所以可見高 = 2000 / 顯示比,
    #   上限 1334(= 光柵扣掉與原廠同構的邊距 16/10)。
    ph = preview_visible_height()
    items.append((GTAB, 2, "分組表:2 組(可見高、可見寬)"))
    items.append((GTAB + 4, len(PREV_PROFILES), "群組 0 筆數"))
    items.append((GTAB + 8, ph, f"群組 0 選中值(可見高 {ph})"))
    items.append((GTAB + 12, PREV_STOCK_H, "群組 0 未選值(原廠 16:9)"))
    for i, a in enumerate(PREV_PROFILES):
        items.append((GTAB + 16 + i * 4, a, f"群組 0 位址 [{i}]"))
    g1 = GTAB + 16 + len(PREV_PROFILES) * 4
    items.append((g1, len(PREV_PROFILES), "群組 1 筆數"))
    items.append((g1 + 4, PREV_STOCK_W, "群組 1 選中值(可見寬,面板改)"))
    items.append((g1 + 8, PREV_STOCK_W, "群組 1 未選值(原廠 2000)"))
    for i, a in enumerate(prev_width_addrs(img)):
        items.append((g1 + 12 + i * 4, a, f"群組 1 位址 [{i}]"))
    # ★ 補 NUL 到整個槽,**不要留原廠尾巴** —— 舊版只覆蓋前 len(_CSV) 個
    #   位元組,於是最後一列後面接著原廠殘留(相機上讀到 `3,CUSTOM,,1,2k,1,2`)。
    words(CSV_ADDR, _CSV + b"\0" * (CSV_SLOT - len(_CSV)), "選單 CSV")
    items.append((CTRL_CAP, 0x00000040, "控制器上限 BE float 2.0"))

    # 6. 狀態字。開機值全部是故障安全的那一邊。
    for addr, val, note in (
            (0xC0731C00, 0, "og3ksel 計次"), (0xC0731C04, 0, "最後 enum"),
            (0xC0731C08, 0, "FLAG = 0"),
            (0xC0731C0C, 0, "PBFLAG = 0"),
            (0xC0731C14, 0, "位元深度鎖存 = 12-bit"),
            (0xC0731C20, 0xFFFFFFFF, "錄影格式鎖存 = UNKNOWN"),
            (FPSLATCH, 0, "引擎格率鎖存"), (PICKOK, 1, "picker 同意 = 1"),
            (0xC0732000, 0, "og3kout idx0 模板未建置"),
            (0xC0732030, 0, "og3kout idx2 模板未建置"),
            (0xC0732060, 0, "og3kout 命中數"), (0xC0732070, 0, "og3kout 拒絕環"),
            (0xC07328C0, 0, "og3kgs 介入次數")):
        items.append((addr, val, note))
    for i in range(7):
        items.append((0xC0731C24 + i * 4, 0, "og3krestore 紀錄"))
    for i in range(5):
        items.append((0xC0732A00 + i * 4, 0, "畫布紀錄"))

    # 7a. 配對表轉換器改指到 cave。**要在表寫完之後** —— 中間那一瞬間
    #     轉換器若已改指而表還沒寫,就會發出一張全 0 的配對表。
    if WITH_RATE_PAIR:
        put(RATE_PAIR_LO, _movw(2, RATE_PAIR & 0xFFFF),
            f"配對表指標 lo -> {RATE_PAIR:#x}")
        put(RATE_PAIR_HI, _movt(2, RATE_PAIR >> 16), "配對表指標 hi")
        put(RATE_PAIR_CNT, _mov_imm(2, RATE_PAIR_N),
            f"配對表筆數 {RATE_PAIR_STOCK_N} -> {RATE_PAIR_N}")

    if WITH_SL_EXCL:
        if WITH_RATE_ROW or WITH_BIT_ROW:
            raise SystemExit("WITH_SL_EXCL 需要原廠清單保持原廠:關掉 WITH_RATE_ROW / WITH_BIT_ROW")
        SLX.patches(img)                        # 每個 hook 點都還是原廠開頭
        for a, v, n in SLX.state_words():
            put(a, v, n)

    if WITH_RATE_NATIVE:
        native_hooks = {site for site, _, _, _, _ in RATE_NATIVE.HOOKS}
        items.extend(patch for patch in RATE_NATIVE.patches(img)
                     if patch[0] not in native_hooks)
    if _with_bit14():
        items.extend(BIT14.patches(img))

    # 7. hook —— 最後才武裝
    # ★ 順序:**依賴端先、picker 最後**。og3k_plan 的 HOOKS 註解就是這麼寫的,
    # og3k_load 還特地註明「不要排序」。picker 是唯一會讓整組活起來的那一顆 ——
    # 它一掛,imx410_fmt 就開始發放我們的表項,而此時畫布、長寬比、增益都必須
    # 已經就位。第一版把 picker 放第一個,等於在最糟的時間點暴露。
    #
    # 分組是為了分段武裝(--stage):死掉時知道是哪一顆。
    for _name, group in (stages if stages is not None else _stages()):
        for site, target, op, note in group:
            items.append((site, (_bl if op == "bl" else _b)(site, target), note))
    # sl_excl hooks last: five ARM `B` and one Thumb `B.W` (page parser), words from sl_excl
    if WITH_SL_EXCL:
        items.extend(SLX.patches(img))
    return items


# (階段名, [(hook, 目標, 指令, 說明)])。前面的階段全部有守衛,在 FLAG=0 /
# profile 沒載入的狀態下應該整路不動作 —— 所以它們可以先掛上去確認相機沒事。
def volatile_addresses():
    """**執行期會變的槽。** 安裝時寫初值,之後由 payload 自己改。

    分類「相機現在是不是我們裝的」時必須排除它們 —— 畫布 payload 一跑就把
    「最後看到的 profile」寫進紀錄槽,拿它跟初值比,任何已經在跑的安裝都會
    被判成 foreign。og3k_load 的 §8c 記過同一個坑:「9 個不同的字被當成
    log 槽打發掉」—— 那次是反過來,把真的壞掉當成 log。所以這張表要**明確
    列出**,不能用「反正 cave 裡的都不算」帶過。
    """
    out = set()
    for lo, n in ((AXIS, AXIS_WORDS), (RECIPE, RECIPE_WORDS), (ENTRY_ADDR, 12),
                  (CANVAS, 1 + CANVAS_MAX_PAIRS * 2), (HITS, 1),
                  (0xC0731C00, 2),          # og3ksel 計次 / 最後 enum
                  (0xC0731C08, 1),          # FLAG
                  (0xC0731C14, 1),          # BITLATCH
                  (0xC0731C20, 1),          # FMTLATCH
                  (0xC0731C24, 7),          # og3krestore 紀錄
                  (FPSLATCH, 1), (PICKOK, 1),
                  (0xC0732000, 1), (0xC0732030, 1),   # og3kout 模板建置旗標
                  (0xC0732060, 1), (0xC0732070, 1),   # og3kout 命中 / 拒絕
                  (0xC07328C0, 1),          # og3kgs 介入次數
                  (0xC0732A00, 5),          # 畫布紀錄
                  (SL_MENU_MARK, SLX.MARK_BYTES // 4)):   # sl_menu / sl_excl 紀錄
        out |= {lo + i * 4 for i in range(n)}
    if _with_bit14():                       # sl_excl ROLE 14 rewrites both
        out |= {BIT14.BIT14} | {BIT14.BIT_PAIR + 0x14, BIT14.BIT_PAIR + 0x1C}
    return out


def _stages():
    return (
        ("canvas", [(ROW_HOOK, CANVAS_CODE, "bl", "畫布 hook")]),
        ("display", [(ASP_HOOK, ASP_CODE, "b", "長寬比 hook 1"),
                     (ASP2_HOOK, ASP2_CODE, "b", "長寬比 hook 2"),
                     (GS_HOOK, GS_CODE, "b", "增益分派 hook"),
                     *((( RNG_HOOK, RNG_CODE, "b", "範圍檢查 hook"),)
                       if WITH_RANGE else ())]),
        ("fps", [(a, FPS_CODE, "bl", f"快門角度 hook:{n}")
                 for a, _, n in FPS_HOOKS]
                + ([(RAT_HOOK, RATE_CODE, "b", "容器格率 hook")]
                   if WITH_RATE else [])),
        ("menu", [(SEL_HOOK, SEL_CODE, "b", "解析度 setter hook"),
                  (NAM_HOOK, NAME_CODE, "b", "解析度名 hook"),
                  (OFM_HOOK, OGFMT_CODE, "b", "錄影格式 setter hook"),
                  (OUT_HOOK, OUT_CODE, "b", "主輸出描述子 hook"),
                  *([(site, target, op.lower(), note + " hook")
                     for site, target, _stock, op, note in RATE_NATIVE.HOOKS
                     if site not in RATE_NATIVE.DISARM | RATE_NATIVE.NOT_ARMED]
                    if WITH_RATE_NATIVE else []),
                  *([(BIT14.GET_SITE, BIT14.GET_CODE, "b", "位深 getter:CUSTOM + BIT14 回 14-bit")]
                    + [(a, BIT14.BLACK_CODE, "bl", "DNG BlackLevel 位深:BIT14 視為 14-bit")
                       for a, _ in BIT14.BLACK_SITES]
                    if _with_bit14() else []),
                  *([(SELLOG.SITE, SELLOG.CODE, "b", "診斷:路徑選擇器紀錄")] if WITH_SEL_LOG else []),
                  *(BINFILT.hooks() if _with_binfilt() else []),
                  ]),
        # ★ picker 是 **B 不是 BL**。og3k_plan.HOOKS 寫的就是 "b"。
        # BL 會把 lr 蓋成 0xC043CCFC;pass 路徑把它還原之後,位移的原廠 push
        # 就把「跳回自己第二條指令」存成返回位址,原廠函式結尾 pop {...,pc}
        # 跳回自己中間 —— 每一次 picker 查詢都如此。2026-09-28 上機:
        # 掛上去 3 秒內死。命中路徑的 `bx lr` 也是靠 B 才會回到真正的呼叫端。
        ("picker", [(PIK_HOOK, FMT_CODE, "b", "picker hook")]),
    )



def order_errors(items=None):
    """任何「值指向某個 payload」的寫入都不能排在該 payload 寫完之前。"""
    items = items or plan()
    bl = blobs()
    spans = {name: (addr, addr + len(bl[name])) for name, _, addr in payloads()}
    done_at = {}
    for i, (addr, _v, _n) in enumerate(items):
        for name, (lo, hi) in spans.items():
            if lo <= addr < hi:
                done_at[name] = i
    bad = []
    for i, (addr, v, note) in enumerate(items):
        # payload 內部的字不算「指標」—— ARM 的 GT 條件碼就是 0xC,條件指令
        # 的位元樣式長得像 cave 位址。規則管的是**payload 之外**指進來的寫入。
        if any(lo <= addr < hi for lo, hi in spans.values()):
            continue
        tgt = None
        # **B 與 BL 都要認。** 只認 BL 的話,長寬比那兩個 hook(用 B,因為
        # payload 靠 bx ip 自己回去)排到 payload 前面不會被擋 —— 2026-09-28
        # 「檢查器自己會不會抓」那個測試抓到的。
        if (v & 0xFE000000) == 0xEA000000:            # B / BL
            off = v & 0xFFFFFF
            off -= 0x1000000 if off & 0x800000 else 0
            tgt = addr + 8 + off * 4
        elif 0xC0700000 <= v < 0xC0740000:
            tgt = v
        if tgt is None:
            continue
        for name, (lo, hi) in spans.items():
            if lo <= tgt < hi and i < done_at.get(name, -1):
                bad.append(f"第 {i} 筆({note})指向 {name},但它到第 "
                           f"{done_at[name]} 筆才寫完")
    return bad


# ---- MISSING ---------------------------------------------------------------
# Current open items only. Historical experiments remain in IMX410_FULL_DESIGN.
MISSING = (
    "舊固定位址計畫仍不可直接安裝;建卡器已搬到 USER 並完成精確離線驗證，實機冷/暖啟動和關機還待驗。",
    "r79 是最近一次記錄的實機操作;r80 未上機，r81 搬遷卡目前也只有離線驗證。",
    "FILTER/MODE/OUTPUT 分頁已能控制 AXIS;SAVE 分頁仍不可進入,持久預設未實作;Any 篩選仍受目前格率限制。",
    "UHD 由 8-bit 切至 12-bit 會凍結;任意比例的 LV 顯示框尚未完成。",
    "RAW14 的增益政策、實錄與 CinemaDNG 14/16 bpp 封裝未驗;donor 可求解及選單可選不代表可出貨。",
    "回放須依每段素材自己的幾何重建;目前回放 hooks 尚未接,og3kname 仍使用初始尺寸。",
    "CRCT 的 I0/I 成對驗證未做;x5 沒有係數證據;高格率 SSD 與音訊/時間碼同步仍待驗。",
    "原生 6K 曾在 16 格後因緩衝滿自行停錄;RAW 緩衝容量與長時間錄影能力仍需量測,不能由短片推定。",
    "240 容器 FrameRate 有先前 H2 實錄證據;新版面板組合、QS 圖示/動畫與設定生命週期仍待驗收。",
    "mode 0 與自動選擇哨兵共用值;全高 RAW14 低於選單最低格率,暫不可強制選 ACQ。",
    "無解仍退回固定 FHD30;不跟選單格率,也不表示 RAW14 無解時能產生正確 14-bit 素材。",
    "仍須以修正後成品驗證開機/不錄影/關機/再開約十輪及跨卡暖啟動;Fast 寫持久設定且僅作開發,多產品合併未開放。",
)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", action="store_true")
    a = ap.parse_args(argv)

    bl = blobs()
    print("位址配置:")
    for lo, hi, name in regions(bl):
        print(f"  {lo:#010x} .. {hi:#010x}  {hi - lo:5d} B  {name}")
    bad = layout_errors(bl) + hook_errors()
    for b in bad:
        print("  ✗", b)
    if a.map:
        return 1 if bad else 0

    items = plan()
    bad += order_errors(items)
    print(f"\n計畫 {len(items)} 筆寫入")
    for b in bad:
        print("  ✗", b)
    print("\n還缺(見 MISSING):")
    for m in MISSING:
        print("  ·", m)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
