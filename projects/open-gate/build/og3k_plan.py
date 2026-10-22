#!/usr/bin/env python3
"""OG3K 的單一寫入計畫 —— USB 載入器與 AutoRun 產生器都用這一份。

只從韌體映像與 .S 原始碼推導,不需要相機。回傳 (位址, 值, 註解) 的串列,
順序就是安全的套用順序:payload 一律在它的 hook 之前,所有 hook 最後才武裝。

    from og3k_plan import plan, ITEMS
    for addr, val, note in plan():
        ...
"""
import hashlib, pathlib, re, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from armasm import assemble

# ---- 建置目標 -------------------------------------------------------------
# 一份程式碼兩張卡。選單只放得下三個選項(CSV block 92 bytes,原廠佔 89,
# 解析器按欄位名稱對欄所以標頭不能縮),所以 OG3K 與 OG2K 不能共存於同一
# 張卡 —— 見 notes/OG2K_PLAN.md §A。
#
#     OG_TARGET=og3k  ./og3k_plan.py      (預設)
#     OG_TARGET=og2k  ./og3k_plan.py
#     OG_TARGET=hsw   ./og3k_plan.py      高速模式,見 notes/HSW_240FPS_MODE12.md
import os
TARGET = os.environ.get("OG_TARGET", "og3k")

# 錄影格式守衛(og3kfmt)+ 開機還原(og3krestore)。
#
# 2026-09-21 實機:選了 OG3K/OG2K 之後把錄影格式切成 MOV 再按錄影,
# 相機**硬凍結**(shell 與 mem_get 一起死,只能抽電池)。兩個目標都會,
# 徵狀逐項相同;差分證明是同一狀態下 FLAG=1 凍、FLAG=0 乾淨。
# 見 notes/FLAG_AND_PICKER_DISAGREE.md §10 §12 §38。
#
# 這一組可以整組關掉做 A/B —— 關掉時 og3ksel 也會逐位元組回到
# 2026-09-21 之前的樣子(靠 TARGET_FMT_GUARD 這個 define):
#     OG_FMT_GUARD=0 ./build_og3k_ui_candidate.py ...
# 必須放在 _defines() 被呼叫之前。
WITH_FMTGUARD = os.environ.get("OG_FMT_GUARD", "1") != "0"

# OG2K 垂直三抽頭(真 3×3)。只給 og2k,預設關。
#
# M139 原廠是 (3,2,3,3):水平 3 抽頭,垂直只併 2 列、每三條同色列丟一條
# (notes/REDUCTION_KERNEL_MEASURED.md §3.1)。§7.48 的三暫存器配方
#     0x0737 / 0x0738   2 → 4     垂直深度,編碼 2×(抽頭數−1)
#     0x0734            3 → 5     不混色的取樣窗
# 用 imager mode_reg_add 實錄過多批,逐平面雜訊 −9~−15%。
# 旁證:Z CAM E2-F6 的 IMX410 表裡唯一的原廠垂直三抽頭設定(readout 12,
# 2020×336)寫的正是這三格同樣的值(zcam_e2f6/notes/ZCAM_E2F6_FIRMWARE.md)。
#
# 這裡改成寫 M139 暫存器列的 RAM 複本,掛在 og3ksel / og3kfmt 的 GTAB 交易上:
# 選中時寫 4/4/5,離開時寫回 2/2/3,與 donor 時序同進退。
#
# ⚠ 相機內沒有修掉奇偶錯位:G2/B 平面比 R/G1 低約 1/3 平面列,要在解拜耳前
#   後製補償(§7.46.4、§7.51)。最後一列 1343 會壞,但在 DefaultCrop
#   (8,5)+2000×1334 之外。
#     OG_V3TAP=1 OG_TARGET=og2k ./build_og3k_ui_candidate.py ...
WITH_V3TAP = os.environ.get("OG_V3TAP", "0") != "0"
if WITH_V3TAP and TARGET != "og2k":
    raise SystemExit(f"OG_V3TAP 只適用 og2k(M139),不是 {TARGET!r}")

ROOT = HERE.parent.parent.parent      # projects/open-gate/build -> SIGMA_re
# Loader v3 (2026-10-06, og_pic.inc / build_v3_og.py): the same payloads as one
# position-independent block. OG_V3=1 assembles every reference into the cave
# layout PC-relative; OG_V3_OGV moves the layout's origin, which the v3 builder
# does once more to prove nothing absolute into it is left. Without OG_V3 the
# assembled bytes are the AutoRun card's, unchanged.
V3 = os.environ.get("OG_V3") == "1"
OG_CAVE0 = 0xC0730000
V3_OGV = int(os.environ.get("OG_V3_OGV", hex(OG_CAVE0)), 0)


def ogv(address):
    """A cave address as the payloads are assembled to see it (og_pic.inc OGA)."""
    return address - OG_CAVE0 + V3_OGV if V3 else address


# OG_CHAIN (Loader v3, 2026-10-07: OG3K and OG2K on one card): every hook is a
# layer; a payload goes down through its word in this table (og_pic.inc
# OG_PASS), which the entry fills.  0xC0730100.. is unused by every target's
# plan (og3k/og2k; hsw's hswrate/poolinit sit at 0x400/0x500).  The four
# shutter-angle sites share og3kfps, so they share its word.
CHAIN = V3 and os.environ.get("OG_CHAIN") == "1"
CHAIN_NEXT0 = 0xC0730100
# Words OG_CHAIN adds beyond its ways down (each counted on purpose):
#   og3kaspect/2  the one exit split in two (mov, movw, movt, bx)
#   og3ksel/fmt   "leave only if this layer was active": ldr, cmp, beq + movw, movt
CHAIN_EXTRA = {"og3kaspect": 4, "og3kaspect2": 4, "og3ksel": 5, "og3kfmt": 5}
# OG_SAVE_ENUM (2026-10-07) is in the legacy defines too, so its +13 words in
# og3ksel are not v3 growth; the plan-word tripwire below counts them
# (OG_SAVE_ENUM_WORDS).
# The resolution value each OG target stores, from uishare's one registry
# (ui/enums.py): OG3K 4, OG2K 7, so the two can sit on one card.
OG_ENUMS = {"og3k": 4, "og2k": 7}
# ---- video clamp (2026-10-07; v3 OG_CHAIN only) ---------------------------
# Each sensor mode has a clamp record (the sensor mode table's "digital clamp"
# row) at CLAMP_BASE + 0x38 * (the mode's index in the timing table TT); +0 is
# the mode id.  Every stock *video* mode has +0x04 bit 3 and +0x18 bits 14-15
# set (the video clamp); the stills / live-view modes OpenGate records with
# (98, 117, 139) have them clear, and at high ISO their black moves by one
# level from frame to frame while the DNG keeps BlackLevel 256 (Jose Hurtado,
# fpSup-Formats v0.6.1; projects/jose-hurtado/notes/JOSE_VS_OURS.md §5.1).
# While an OG is live (FLAG = 1) og3ksel / og3kfmt set those bits on every
# donor mode of the target; leaving puts the stock words back.  Modes 3/98 are
# also the camera's AF / magnifier modes: they only change while the OG is live.
# The words are private GTAB groups after the shared preview group; leaving for
# another OG (OGSAVE = its enum) skips only the shared group (OG_GTAB_SHARED).
CLAMP_BASE, CLAMP_STRIDE = 0xC0B5C638, 0x38
CLAMP_FIELDS = ((0x04, 0x00000008), (0x18, 0x0000C000))
WITH_CLAMP = CHAIN and os.environ.get("OG_CLAMP", "1") != "0"
GTAB_SHARED_GROUPS = 1          # the six preview heights; checked in groups()
CHAIN_SLOT = {"fmttable": 0, "og3kfps": 1, "og3kname": 2, "og3ksel": 3, "og3kaspect": 4,
              "og3kaspect2": 5, "og3kout": 6, "og3kcanvas": 7, "og3kpbsel": 8, "og3kgs": 9,
              "og3kfmt": 10}


FIRMWARE = ROOT / "out" / "MAIN_c0000000.bin"
B = 0xC0000000
# 這是刻意的絆線:core 的字數只能在「知道為什麼」的時候改。
#   710 → 749  (2026-09-15) 8/10-bit CinemaDNG 支援:
#     fmttable 接三張 picker table 並鎖存位元深度、og3kcanvas 依鎖存值寫
#     平面格式碼 +0x080/+0x084、多一個 BITLATCH 初始化字。
#   HSW(2026-09-20)789 -> 1141:donor mode 12 出廠就是 239.760 fps,時序
#     一個字都不改,所以它沒有角度修正的四顆 BL —— 789 曾是最終數字。
#     +352 是選單第十列 239.76 fps:六個 B2_5_5 變體各 53 個字(212B 的
#     CSV)加一個描述子長度欄、控制器上限一個字、hswrate payload 14 個字、
#     格式表多一列 12 個字、它的 hook 一個字。
_BASE_PLAN_WORDS = {"og3k": 772, "og3k_p221": 751, "og2k": 805,
                    "og6k": 698, "hsw": 1183}
#   og3k 749 -> 772 (2026-09-27):write_hirate 打開,而 _BASE_PLAN_WORDS 的
#     約定是「七欄全開」的基準,所以 +23;實際只挑 90/C0,下面那個 -= 會把
#     另外五欄的 17 個字扣回去 -> 755。OG_HIRATE=none 就回到 749,逐位元組
#     等於 2026-09-26 的建置(A/B 對照組)。
#   og2k 782 -> 805 (2026-09-27):同上,write_hirate 打開所以 +23。
#     只挑 90/C0 -> 788,WITH_ENGFPS 再 +10 -> 798。
#     OG_HIRATE=none OG_ENGFPS=0 回到 782 = 改動前。
#   WITH_ENGFPS 另外 +10,見下面那個 +=。
#     1183 是**七欄 hirate 全寫**的基準;OG_HIRATE 少挑一欄就少 3 或 4 個字,
#     EXPECTED_PLAN_WORDS 會自己扣(見 _HIRATE_WORDS)。
#     1171 -> 1183(2026-09-20):og3kcanvas 當場抄下 +0xA4/+0xB0/+0xC0/+0xFC。
#     畫布緩衝會被即時取景覆寫,事後讀指標拿到的是取景那份,不是錄影當下的。
#     1148 -> 1171(2026-09-20):og3kcanvas 補寫 >60 fps 需要的七欄
#     (+0x90/+0xB0/+0xC0/+0xDC/+0xE4/+0xFC/+0x100)。五個 PUT 各三條指令、
#     兩個 PUTW 各四條 = 23 個字。沒有它 119.88 會讓錄影凍結(實機證明)。
#     1147 -> 1148(2026-09-20):og3kcanvas 多記一個字 —— 執行期的畫布位址,
#     讓 shell 能直接讀真正的畫布內容,不必再從 profile 的靜態表推論。
#     1141 -> 1147(2026-09-20 第一次實機之後):og3kcanvas 的錄影路徑補寫
#     感測器視窗 +0x0F4/+0x0F8。p13 宣告 2016x1344,而 mode 12 只讀 672 行 ——
#     不補的話 22 格請求永遠不會完成,錄影結束不了。兩個 PUT 各三條指令 = 6 字。

# ---- 程式碼與資料的落點(全部在 RAM 的空洞裡,抽電池即還原) ----------------
# 2026-09-12:原本在 0xC072F800,那是 **USB shell 的檔案傳輸工作暫存區**
# (putfile.CODE = 0xC072F800 .. CODE_END = 0xC072FA00)。gyro/build_card.py 的
# 註解說那裡「at boot 沒人用」—— 開機時確實沒人用,但執行期每一次
# getfile/putfile 都會覆寫它,而畫布 hook 正指著那裡 → 相機凍結。
# 抓截圖時就踩到過。搬到 0xC0732400。
ROW_CODE  = 0xC0732400      # 畫布 hook 的 payload
ROW_LOG   = 0xC0732A00   # 2026-09-15 從 0x2600 挪開:畫布 payload 加了預覽欄位
                         # 之後要 528 bytes,0x2600 只給 512。0x2700 之前全是零區。
POOLINIT_CODE = 0xC0730500  # poolinit payload(268B,止於 0xC073060C)
RATE_CODE = 0xC0730400      # hswrate payload(0xC0730000-0700 映像裡全是零)
CODE      = 0xC0730800      # fmttable payload
HITS      = 0xC0730700
FPS_CODE  = 0xC0730A00      # og3kfps payload
NAME      = 0xC0730C00      # "OG3K" 字串
TABLE     = 0xC0731000      # 八個格式的表,每筆 48 bytes
SEL_CODE  = 0xC0731800      # og3ksel payload
NAME_CODE = 0xC0731A00      # og3kname payload
ASP_CODE  = 0xC0731B00      # og3kaspect payload
AS2_CODE  = 0xC0731B40      # og3kaspect2 payload
if CHAIN:
    # The layered aspect payloads (100 B: their own way down, og3kaspect.S) do not
    # fit the AutoRun card's 0x40 slots; in the v3 block the layout is ours.
    ASP_CODE, AS2_CODE = 0xC0730200, 0xC0730280
LOG       = 0xC0731C00      # og3ksel 的計次 / 最後 enum
FLAG      = 0xC0731C08      # 1 = OG3K 生效
PBFLAG    = 0xC0731C0C      # 1 = 目前顯示的內容是 3008x2000(回放)
PBENT     = 0xC0731C10      # 我們的回放表項 {6, 43, 222, "OG3K"}
# fmttable 命中 OG3K 時,把命中的是哪一張 picker table 鎖存成 eRawBitType
# (0 = 12-bit / 3 = 10-bit / 4 = 8-bit),og3kcanvas 據此寫平面格式碼。
# 見 notes/OG3K_8BIT_10BIT_FALLS_BACK_TO_UHD.md。
BITLATCH  = 0xC0731C14
# 2026-09-21:FLAG 的意思收緊成「選了本目標 **而且** 錄影格式是 CinemaDNG」。
# MOV 不走 CinemaDNG picker,所以有 profile 守衛的 fmttable / og3kcanvas 完全
# 不動作,但只看 FLAG 的那組(og3kout / aspect / aspect2 / fps / gs)仍開著,
# H.264 編碼器拿到 3:2 CinemaDNG 的輸出描述子 → **硬凍結**。
# OG3K(p83/mode98)與 OG2K(p13/mode139)都實測確認,徵狀逐項相同;
# 差分證明是同一狀態下 FLAG=1 凍、FLAG=0 乾淨。
# 見 notes/FLAG_AND_PICKER_DISAGREE.md §10 §12 §38。
FMTLATCH  = 0xC0731C20      # 0 = CinemaDNG,由 og3kfmt / og3krestore 寫
# 開機值:格式尚未讀取。og3ksel 把任何非 0 當成「非 CinemaDNG、不生效」,
# 所以 restore 讀到真值之前選 OG 只會記住偏好,不會發布 FLAG。
FMTLATCH_UNKNOWN = 0xFFFFFFFF
# 引擎格率鎖存。fmttable 命中時把「原廠在同一個 picker slot 上宣告的格率」
# (float bits)寫進來,og3kcanvas 的錄影 case 再寫進畫布 +0x030。
# 0xC0731C40 起是空的:RLOG 七個字止於 0xC0731C40,下一個 payload 是
# OUT_CODE 0xC0731D00。刻意不用 0xC0731C18/1C —— 那兩個字是 POOLFLAG/POOLSLOT。
FPSLATCH  = 0xC0731C40
# picker 是否同意。2026-09-27:選了 OG3K 但格率是表裡沒有的(唯一的例子是
# 119.88 —— OG3K120 物理上不可能,3032x2012 的上限約 108 fps),鍵會是
# `OG3K120`,我們的表與原廠表都查不到 -> 原廠退回 TAB3[0] = UHD30。
# 而 og3kout/aspect/aspect2 **只看 FLAG**,於是顯示鏈被強制成 3:2 而錄影是
# UHD -> **畫面拉長、檔案是 UHD**(使用者 2026-09-27 回報)。
#
# fmttable 命中就寫 1、看到自家標籤但查不到就寫 0;那三個顯示 hook 的條件
# 收緊成 FLAG && MATCH。這實現的是 FLAG_AND_PICKER_DISAGREE.md 立的不變量:
# **顯示鏈要聽 picker,不要聽選單**。不支援的格率 -> 整組 OG3K 顯示效果關掉
# -> 行為等同原廠 UHD(16:9)。
#
# 開機值 **1**:在看到壞鍵之前行為與 2026-09-26 的建置逐位元組相同。
# 刻意不動 og3ksel/og3kfmt —— 那兩個是修硬凍結的關鍵 payload。
MATCH     = 0xC0731C44
RLOG      = 0xC0731C24      # og3krestore:+0 次數 +4 OGSAVE +8 格式 +C 結果碼 +10 讀回 FLAG +14 LV 重讀 +18 CamSch1 狀態
RLOG_WORDS = 7
# 兩個新 payload 放在格式表之後的大空洞(0xC07311B0..0xC0731800)。
# 起點取 0xC0731400,因為格式表的長度隨目標而變 —— HSW 十列會到
# 0xC0731210,這樣三個目標都清得開。
FMT_CODE  = 0xC0731400      # og3kfmt payload,268 bytes
RESTORE_CODE = 0xC0731600   # og3krestore payload,由 loader 的 VSHL entry 呼叫
# 使用者上次選的是不是本目標。XC_CommonSaveData +0x290 —— 實測 60/60 跨電源
# 循環存活,而且**不需要任何存檔命令**,相機自己存、開機自己載回。
# 那一段也不在快速啟動 loader 佔用的 +0x028..+0x200 裡。
# 見 research/firmware/notes/PERSISTENT_STORE_COMMONSAVE.md。
# ⚠️ 這個字**不可以**放進 state():它要跨電源循環,歸零就失去意義。
OGSAVE    = 0xC30754CC
OUT_CODE  = 0xC0731D00      # og3kout payload
TPL0      = 0xC0732000      # og3kout 的兩份私有模板
TPL2      = 0xC0732030
OHITS     = 0xC0732060
OREJ      = 0xC0732070
GTAB      = 0xC0732100      # og3ksel 的分組表(跟著旗標切換的靜態表欄位)
GS_CODE = 0xC0732900        # og3kgs payload(增益分派)
GS_LOG  = 0xC07328C0
PBSEL_CODE = 0xC0732200     # og3kpbsel payload
PBSEL_LOG  = 0xC0732380
PBSEL_ENT  = 0xC0732390     # og3kpbsel 要回傳的表項指標(0 = 不介入)
# **預設 0 = 不介入**,這是故障安全值。
# 2026-09-13:預設曾放 0xC0BE5690(WithRaw,+0x538),一進回放就黑屏凍結 ——
# 那條管線屬於錄影路徑,回放模式下沒被填值,消費端拿到空描述子。
# 教訓:載入後的狀態必須永遠是安全的,要換管線用 pbsel_try.py 當場轉,
# 這樣凍結最多損失一次重播,不會卡在「一開機就凍」。
PBSEL_ENT_VALUE = 0

# ---- hook 點與原廠指令 ------------------------------------------------------
ROW_HOOK, ROW_STOCK = 0xC043A19C, 0xE1A00004        # BL,會回放位移指令
SEL_HOOK, SEL_STOCK = 0xC005C020, 0xE92D4070
# 錄影格式 setter。與解析度 setter 逐條同構,連進入指令都是同一個字。
# 由 shell 的 menu 指令表推導:0xC0BBB5C0 起每筆 12 bytes
# (名稱字串, 用法字串, 處理函式),"SetMovRecFormat" 的處理函式 0xC03FD960
# 裡的 set 呼叫就是它;同一個方法對 "SetMovRecSize" 推出 0xC005C020,
# 與 SEL_HOOK 相符,所以這個推導是驗證過的。
FMT_HOOK, FMT_STOCK = 0xC005BE58, 0xE92D4070
ASP_HOOK, ASP_STOCK = 0xC0306EA0, 0xE3A00003
AS2_HOOK, AS2_STOCK = 0xC0306EEC, 0xE3A00003
OUT_HOOK, OUT_STOCK = 0xC0437E98, 0xE92D4030
PIK_HOOK, PIK_STOCK = 0xC043CCF8, 0xE92D4CF0
NAM_HOOK, NAM_STOCK = 0xC0437B48, 0xE92D4BF0   # 解析度名發射器的進入點
PB_HOOK,  PB_STOCK  = 0xC0437AF8, 0xE92D4070   # entry → canvas,只讀 entry+4
PB_CODE = 0xC0731F80
GS_HOOK, GS_STOCK = 0xC03A6DD8, 0xE92D4010     # 增益分派的「是不是 raw movie」判斷
PBSEL_HOOK, PBSEL_STOCK = 0xC043BE68, 0xE92D4070   # 配置器 v3(管線選擇器)
RNG_HOOK, RNG_STOCK = 0xC043D258, 0xE92D0030   # 範圍檢查:讓分派器認得我們的表
RNG_CODE = 0xC0731F00
# 四條快門角度換算/同步路徑各自查一次 nominal fps。不能只補 UI property
# 路徑的第一顆：解析度重組會從 C03AA568 再算一次並覆寫中央 exposure state。
# 全域 getter 有數十個 caller，而 mode 98 又與照片共用，所以四顆 BL 都導向
# 同一個窄 wrapper，不動 getter 本體。
# 快門角度修正的四個 callsite。**可以整組關掉做 A/B 診斷**:
#     OG_FPS_FIX=0 ./build_og3k_ui_candidate.py ...
# 2026-09-15:社群回報 25p/180° 在螢光燈下錄影會閃(快門速度模式不閃),
# 而且說「v0.2.1a 之前的版本沒這問題」—— v0.2.1a 正是引入這個修正的版本。
# 關掉它可以直接證實或排除,不用猜。
#
# **HSW 不需要這個修正,四顆 BL 一律不武裝。** 角度修正存在的前提是
# 「donor 的 metadata +0x40 不等於我們實際在錄的格率」—— mode 98 是 78 而
# 我們在錄 29.97。HSW 的 donor 是 mode 12,它的 +0x40 原廠就是 **240**,
# 而我們寫進它 timing record 的就是它自己的原廠 330/330/910 = 239.760 fps。
# stock getter 回傳的已經是真實擷取率,沒有東西要更正;武裝四顆 BL 只會多
# 四個風險點換零收益。
# 選單第十列(239.76 fps)只有 HSW 需要,而且它動的是**共用**的格率清單 ——
# 六個 B2_5_5 變體、控制器上限、有理數表全是全機共用的。所以整組可以關掉做
# A/B:  OG_RATE240=0 OG_TARGET=hsw ./og3k_plan.py
WITH_RATE240 = (TARGET == "hsw"
                and os.environ.get("OG_HSW_FPS", "per-rate") == "240"
                and os.environ.get("OG_RATE240", "1") != "0")
# 診斷用:把六個格率清單變體的 Enabled 欄全部打開。
#
# 2026-09-20:使用者發現「沒接 SSD 就選不到 100p」—— 那六個變體是**依儲存媒體**
# 閘控的。但 100p 正是即時取景亮度會變、也就是感測器模式疑似被切的那一格,
# 而要驗那件事**只需要選得到,不需要錄影**。接了 SSD 就沒有 USB shell,
# 所以改從 CSV 這一側把閘門打開,才能在 SD 卡上做這個唯讀量測。
#
#     OG_RATE_UNGATE=1 OG_TARGET=hsw ./og3k_plan.py
WITH_RATE_UNGATE = (TARGET == "hsw"
                    and os.environ.get("OG_RATE_UNGATE", "0") != "0")
WITH_RATE_CSV = WITH_RATE240 or WITH_RATE_UNGATE

_ANGLE_FIX_TARGETS = {"og3k", "og3k_p221", "og2k", "og6k"}
WITH_FPS = (os.environ.get("OG_FPS_FIX", "1") != "0"
            and TARGET in _ANGLE_FIX_TARGETS)

_FPS_HOOKS_ALL = (
    (0xC02092CC, 0xEB048D1F, "主要 exposure property"),
    (0xC0218AEC, 0xEB044F17, "angle metadata path A"),
    (0xC0219260, 0xEB044D3A, "angle metadata path B"),
    (0xC03AA568, 0xEBFE0878, "resolution reconfiguration sync"),
)
# 還可以只武裝其中幾個 callsite,用來二分到底是哪一條造成問題:
#     OG_FPS_SITES=0,1,2  ./build_og3k_ui_candidate.py ...   (不含 reconfiguration sync)
# index 對應 _FPS_HOOKS_ALL 的順序。
_sites = os.environ.get("OG_FPS_SITES")
if not WITH_FPS:
    FPS_HOOKS = ()
elif _sites:
    _keep = {int(x) for x in _sites.split(",") if x.strip() != ""}
    if not _keep <= set(range(len(_FPS_HOOKS_ALL))):
        raise SystemExit(f"OG_FPS_SITES={_sites!r} 超出 0..{len(_FPS_HOOKS_ALL)-1}")
    FPS_HOOKS = tuple(h for i, h in enumerate(_FPS_HOOKS_ALL) if i in _keep)
else:
    FPS_HOOKS = _FPS_HOOKS_ALL
# 不做角度修正的目標(HSW)本來就沒有那四顆 BL,所以它的基準數字就是
# 最終數字,不再扣。會做角度修正的目標維持原本的「基準扣掉未武裝的顆數」,
# 這樣 OG_FPS_SITES 的二分診斷還是能用。
# OG_RATE240=0 的 A/B 診斷會少掉這些字:六個 B2_5_5 變體各 53 個 CSV 字加
# 一個描述子長度欄(324)、控制器上限(1)、hswrate payload 14 個字、它的
# hook(1)。格式表的第十列不在內 —— 那一列留著也無害,沒有東西會發出它的鍵。
_RATE240_WORDS = 6 * (53 + 1) + 1 + 14 + 1
# 解除閘門版:六個變體各 47 個 CSV 字加一個描述子長度欄,不動上限、不加 payload。
_RATE_UNGATE_WORDS = 6 * (47 + 1)
# 錄影格式守衛整組的字數,五個目標都一樣:
#     og3kfmt payload      67   (與 og3ksel 同一段交易,只換 r5 的算法與回跳)
#     og3krestore payload 124   (09-23:36 → 72 忙碌檢查與結果碼;09-24:→ 124 開機後讓 LV 重讀顯示 profile;上限 128)
#     og3ksel 長出來的      11   (格式條件 + 寫 OGSAVE)
#     og3kfmt 的 hook        1
#     FMTLATCH + RLOG x7     8   (RLOG 多 +0xC 結果碼、+0x10 讀回 FLAG、+0x14 LV 重讀、+0x18 CamSch1 狀態)
#                         ----
#                          211
# 實測(119 那一版):OG_FMT_GUARD=0 時 og3k/og2k/og6k 的字數分別回到
# 749/782/698,與這一版之前的基準逐字相同 —— 所以 A/B 是乾淨的。
_FMTGUARD_WORDS = 211
# ⚠️ 這裡原本是一個跨行的三元運算式,而 `a - b if c else d - e + f` 的
# 結合方式會把 `+ f` 只掛在 else 那一支上 —— 新增的調整項若照原樣接在尾巴,
# 對 _ANGLE_FIX_TARGETS 那一支**不會生效**(2026-09-21 踩過)。拆開寫。
if TARGET in _ANGLE_FIX_TARGETS:
    EXPECTED_PLAN_WORDS = (_BASE_PLAN_WORDS[TARGET]
                           - (len(_FPS_HOOKS_ALL) - len(FPS_HOOKS)))
else:
    EXPECTED_PLAN_WORDS = (_BASE_PLAN_WORDS[TARGET]
                           - (0 if WITH_RATE240 or TARGET != "hsw"
                              else _RATE240_WORDS)
                           + (_RATE_UNGATE_WORDS if WITH_RATE_UNGATE else 0))
if WITH_FMTGUARD:
    EXPECTED_PLAN_WORDS += _FMTGUARD_WORDS
# 保留第一顆的舊名稱，讓既有報表可指出原始發現點；驗證與 hook 清單一律
# 使用 FPS_HOOKS，不能再把它誤當成唯一 callsite。
FPS_HOOK, FPS_STOCK = _FPS_HOOKS_ALL[0][:2]
FPS_ORIGINAL = 0xC032C750

# ---- 韌體裡被改寫的位址 ----------------------------------------------------
EMIT_W, EMIT_H  = 0xC0BCFE80, 0xC0BCFE84    # 發射器比對表裡原本的 1280x720 那筆
STRLO, STRHI    = 0xC0437C34, 0xC0437C38            # 原函式的字串指標
EMIT_FN         = 0xC0BE44DC                        # 解析度名的函式指標
# OG_UISHARE=1 (2026-10-03): the resolution row, its List max and its summary
# text are added by fpSup/uishare (ui/options.py resolution()) through a UI
# section, so OpenGate can share the list with other sups. The CSV and the
# controller max are then not written here. Default off: other builders
# importing this plan (Sensor Lab) are unchanged.
UISHARE = os.environ.get("OG_UISHARE") == "1"
if UISHARE:
    EXPECTED_PLAN_WORDS -= 1 + 92 // 4      # CTRL_CAP and the 92-byte CSV slot (menu_csv)
CTRL_CAP        = 0xC1A709BC                        # 控制器上限 BE float 2.0
CSV             = 0xC0F8E7EC                        # 選單 CSV
TT, T3          = 0xC0B59500, 0xC0BE5B50            # 時序表 / picker 表3

# ---- 選單第十列 239.76 fps(只有 HSW 需要)--------------------------------
# 2026-09-20。原廠 CINE 格率清單是 **九列**(23.98/24/25/29.97/48/50/59.94/
# 100/119.88),資源是 `../MenuB12/data/ListB12/B2_5_5*.cvm`,六個變體就是
# 「哪個解析度能選哪幾格」的閘門。加第十列要四件事,三件已離線證明:
#
#   ① picker 鍵發射器 **不用改**。FUN_c043caf0 的界線原廠就是 `cmp r3,#12`,
#      跳表十三筆,enum 11 -> "240"、enum 12 -> "400"(字串在 0xC0BE4800:
#      '400\0240\0120\0100\023_98\0...')。列舉空間本來就留了這兩格,
#      只是沒有有理數也沒有選單列。所以鍵自然就是 "HSW240"。
#   ② 有理數:FUN_c00c9bd0 被 `cmp r2,#10` 夾住,enum 11 會落到 default
#      (29.97)。hswrate.S 掛在那顆 cmp 上補 240000/1001。
#   ③ 清單控制器上限:0xC1A74B44,BE float 8.0 -> 9.0。**這一顆是這次解開的**
#      —— 用 handoff 的 UI 記錄解析法把三個候選記錄解回祖先鏈:
#          0xC1A7099C obj 0x10A3 max 1.0  List/MenuItem_Select/B2_5_4  解析度
#          0xC1A74B24 obj 0x1157 max 8.0  List/MenuItem_Select/B2_5_5  **格率**
#          0xC2B53E14 obj 0x00D7 max 8.0  List/.../2_01                無關
#      不改的話第十列會「看得見但游標移不下去」,與 FORMAT_REGISTRY_DESIGN
#      §7② 記載的失敗相同。
#   ④ **尚未解決**:enum<->列 配對表 0xC2E44EE4 剛好九筆,後面緊接別的表,
#      沒有預留空位,而且沒有任何字面引用可以重指。解析度那張
#      (0xC2E4020C)原廠就預留了第三筆 {4,2} —— OG3K 第三列當年之所以
#      那麼順,就是因為這個。格率沒有這個運氣。見 notes §10。
#      缺它的後果未知(可能只影響摘要顯示,也可能影響選取),但整條路是
#      fail-open:送進來的 enum 不是 11,hswrate 不動作、鍵也不會是 HSW240。
RATE_CAP        = 0xC1A74B44       # B2_5_5 清單控制器上限 BE float 8.0
RATE_CAP_STOCK  = 0x00000041       # = BE float 8.0
RATE_CAP_NEW    = 0x00001041       # = BE float 9.0
RATE_HOOK       = 0xC00C9BF8       # FUN_c00c9bd0 的 `cmp r2, #10`
RATE_STOCK      = 0xE352000A
# 六個 B2_5_5 變體:(資源位址, 描述子位址, 原廠長度)
RATE_CSV = (
    (0xC0F8E848, 0xC0D50A1C, 257, "B2_5_5"),        # 全開
    (0xC0F8E94C, 0xC0D5351C, 257, "B2_5_5_excl"),   # 只到 29.97
    (0xC0F8EA50, 0xC0D5584C, 257, "B2_5_5_excl2"),  # 只到 24
    (0xC0F8EB54, 0xC0D54F7C, 257, "B2_5_5_excl3"),  # 只到 25
    (0xC0F8EC58, 0xC0D4F87C, 257, "B2_5_5_excl4"),  # 只到 59.94
    (0xC0F8ED5C, 0xC0D4E25C, 257, "B2_5_5_excl5"),  # 只到 100
)

# 每筆 (鍵, donor 感測器模式, 時序抄自哪個模式, picker slot)。
# 時序寫成 None 代表「自己算」,值由 TARGETS[...]["timing"] 提供。
FMT_OG3K = [("OG3K23_98",  98, 109, 10), ("OG3K24",   98, 218,  9),
            ("OG3K25",     98, 125,  8), ("OG3K30",   98, 106,  7),
            ("OG3K48",     98, 220,  6), ("OG3K50",   98, 115,  5),
            ("OG3K60",     98,  27,  4), ("OG3K100", 117,  89, 12)]

# OG2K:八個格率全部掛在 **mode 139**(MONIT1_60_LOWP5,quiet 指紋)。
# hmax 一律用 M139 原廠的 445 —— 換 hmax 就換了線時,也就換了指紋,
# 而 quiet 指紋正是選 M139 的全部理由。vmax/tail 由 72MHz 反推,八個
# 格率誤差全部是 0.000 ppm,最緊的 100p 仍留 273 行空白 > vblank code 100。
# 119.88p 不行(445x1344 = 598,080 of 600,600,只剩約 5.7 行),不列入。
FMT_OG2K = [("OG2K23_98", 139, None, 10), ("OG2K24",  139, None,  9),
            ("OG2K25",    139, None,  8), ("OG2K30",  139, None,  7),
            ("OG2K48",    139, None,  6), ("OG2K50",  139, None,  5),
            ("OG2K60",    139, None,  4), ("OG2K100", 139, None, 12)]

# 445 = M139 stock hmax;x = 6 = M139 stock。(vmax, tail) 見上。
OG2K_TIMING = {"OG2K23_98": (445, 585, 6748, 6), "OG2K24":  (445, 700, 6741, 6),
               "OG2K25":    (445, 850, 6471, 6), "OG2K30":  (445, 735, 5398, 6),
               "OG2K48":    (445, 795, 3370, 6), "OG2K50":  (445, 870, 3235, 6),
               "OG2K60":    (445, 590, 2699, 6), "OG2K100": (445, 880, 1617, 6)}

# ---- OG6K:全幅 3:2 ÷1,給 HDMI RAW 用 -------------------------------------
# donor 感測器模式 = M3 `MONIT1_30`(6064x4042 RAW12,MONIT class,和 OG2K 借
# M139 `MONIT1_60` 同一個做法)。感測器視窗 x[8,6072) y[40,4082)。
#
# **格率上限是感測器的**:有效讀出 = 445 x 4042 / 72 MHz = 24.982 ms,
# 所以最高 40.03 fps。48/50/60 在這個畫幅上不存在,不要加。
FMT_OG6K = [("OG6K23_98", 3, None, 10), ("OG6K24", 3, None,  9),
            ("OG6K25",    3, None,  8), ("OG6K30", 3, None,  7)]

# 445 = M3 stock hmax;x = 8 = M3 stock x_start。四個都是零誤差的精確格率。
# 注意 "OG6K30" 和 OG2K 一樣其實是 29.97003(沿用既有命名慣例)。
OG6K_TIMING = {"OG6K23_98": (445, 585, 6748, 8), "OG6K24": (445, 700, 6741, 8),
               "OG6K25":    (445, 405, 6472, 8), "OG6K30": (445, 735, 5398, 8)}

# ---- HSW:高速模式,donor = mode 12 `MONIT1_240` ---------------------------
# 2026-09-20。**這是全部四個目標裡唯一不改感測器時序的一個。**
#
# mode 12 出廠就是我們要的東西,而且沒有被任何 picker 引用:
#     光柵 2016x672   3x6 非對稱縮減的**全片幅 3:2**(crop = 0)
#     hmax 330  tail 330  vmax 910  x 6
#     330 x 909 + 330 = 300,300 cycles @72 MHz = **239.760240 fps**(0 ppm)
#     捲簾 330 x 672 / 72 MHz = **3.080 ms**(OG3K/mode98 是 12.435)
#     metadata +0x40 標稱 fps = **240**,+0x3C = RAW12,+0x54 = 2(3:2)
#     cluster 23 = 「330 快」類比指紋、**MONIT 類**(不是 ACQ)
#
# MONIT 類消掉的是 mode 98 那個「把拍照擷取模式塞進錄影 picker」的跨類別賭注
# (FRAME_RATE_IS_VMAX.md §2)。**但 og3kgs 仍然要武裝** —— 增益分派讀的是
# profile id 的數值範圍(FUN_c043a1c8),不是感測器模式,而 p13 和 p83 一樣
# 落在 raw movie 的 131..190 之外。這一點與 OG2K 完全相同。
#
# 所以 HSW_TIMING 寫回去的 (330, 330, 910, 6) **逐位元等於 mode 12 的原廠字**
# 0x014A014A / 0x0006038E:fmttable 的 timing transaction 是 no-op,
# og3ksel 的「離開時還原」也是 no-op,角度 wrapper 更是沒有東西要更正。
#
# ★ 3x6 是**非對稱**縮減:水平 3x、垂直 6x。光柵 2016x672 因此是
#   **2:1 垂直壓縮的非方形像素**,涵蓋的視野仍是完整的 3:2 全片幅。
#   後製要垂直拉伸 2x 才是正確比例(2000x662 -> 2000x1324)。
#   研究筆記 SENSOR_MODE_METADATA.md §4 尾註對這件事有明文警告。
#
# ★ 選單格率 vs 感測器格率:感測器**恆為 239.76**,九個格率鍵全部指向同一組
#   時序。選單上那個數字只決定容器/播放格率。兩種可能的實機結果都有價值,
#   而且是同一份 build:
#     (a) writer 由 VSYNC 驅動 -> 每格都寫 -> 選 119.88 = 2x 慢動作、
#         選 23.976 = 10x 慢動作;
#     (b) writer 由格率計時器驅動 -> 抽格 -> 正常速度、但快門上限 1/240、
#         捲簾 3.08 ms = 名副其實的「高速快門」。
#   錄一秒數格數就知道是哪一個。見 notes/HSW_240FPS_MODE12.md。
#
# 九個鍵全列是**可達性保險**:新的解析度 enum 4 能選到哪幾個格率沒有離線
# 證據(2026-09 的紀錄裡使用者回報過「100 fps 在 SD 卡路徑選不到」),
# 全列上去就不必賭。每一列都是純資料,不增加新的失效模式。
#
# 第十列 "HSW240" 是選單新增的 239.76 那一格(格率 enum 11)。它是**唯一
# 容器格率等於感測器格率**的一列 —— 其餘九列都是把 239.76 裝進較慢的容器。
FMT_HSW = [("HSW23_98", 12, None, 10), ("HSW24",  12, None,  9),
           ("HSW25",    12, None,  8), ("HSW30",  12, None,  7),
           ("HSW48",    12, None,  6), ("HSW50",  12, None,  5),
           ("HSW60",    12, None,  4), ("HSW100", 12, None, 12),
           ("HSW120",   12, None, 11), ("HSW240", 12, None, 11)]

# ---- HSW 的格率 ---------------------------------------------------------
# 2026-09-20 實機:239.76 fps 在 SD 卡上跑不動。12-bit 要 476 MB/s,實測卡只給
# 約 104 MB/s,而且**只要收尾時 fin_cnt < req_cnt 就會卡住錄影**(四段 take:
# 94/94 沒卡,94/92、94/72、94/70 都卡)。見 notes §22 §25。
#
# 所以預設降到 29.97003。**捲簾不變** —— hmax 與有效行數都沒動,只有 vmax 拉長:
#     捲簾 = 330 x 672 / 72 MHz = 3.080 ms(OG3K/mode98 是 12.435)
# 也就是「正常格率、四分之一捲簾」,這才是「高速快門」真正有意義的那個版本。
#
#     OG_HSW_FPS=240  ./og3k_plan.py    回到 239.760(需要外接 SSD,卡上會卡住)
# ★ 2026-09-20 第二次實機之後改成**每個格率各自的 vmax**。
#
# 先前十個鍵共用一組時序,結果是「容器宣告的格率」與「感測器實際格率」脫鉤:
#   A001_112/113 容器標 100 / 119.88,用檔案時間戳量出實際只有 28.7 fps。
# 而管線的緩衝配置是照**宣告的格率**算的,感測器卻以別的速度灌進來 ——
# 這是最可能造成錄影凍結的來源:
#   A001_007  選單 23.976  感測器 239.76  10x 超供  -> 寫出 93 格
#   A001_114  選單 119.88  感測器 239.76   2x 超供  -> 一格都沒有,硬凍結
#
# hmax 一律 330(= mode 12 出廠值,捲簾恆為 330 x 672 / 72 MHz = 3.080 ms),
# 只調 tail 與 vmax。十個都是 0 ppm。
#     frame_cycles = hmax x (vmax - 1) + tail,時脈 72 MHz
_HSW_PER_RATE = {           # 後綴: (hmax, tail, vmax, x)
    "23_98": (330, 330, 9100, 6),   # 23.97602
    "24":    (330, 630, 9090, 6),   # 24.00000
    "25":    (330, 420, 8727, 6),   # 25.00000
    "30":    (330, 330, 7280, 6),   # 29.97003  (330/7280 = 韌體 mode 111 的出貨組合)
    "48":    (330, 480, 4545, 6),   # 48.00000
    "50":    (330, 540, 4363, 6),   # 50.00000
    "60":    (330, 330, 3640, 6),   # 59.94006
    "100":   (330, 600, 2181, 6),   # 100.00000
    "120":   (330, 330, 1820, 6),   # 119.88012
    # 180 是 2026-09-20 為了「格率 vs 資料率」的判別實驗加的,選單上沒有這一格,
    # 只能透過 OG_HSW_TOP=180 掛到別的格。挑 180 的理由是資料率剛好撞上
    # 12-bit @ 119.88:8-bit x 180.018 = 243.9 MB/s、12-bit x 119.880 = 243.6 MB/s,
    # 差 0.15%。兩段一個凍一個不凍就能把「中斷率」和「位元組」分開。
    "180":   (330, 330, 1212, 6),   # 180.01800
    "240":   (330, 330,  910, 6),   # 239.76024 (= mode 12 的原廠字)
    # 2026-09-26:只給 OG_HSW_WIN(感測器視窗 336 列)用,掛在 OG_HSW_TOP=480。
    # 讀出 330 x 336 / 72 MHz = 1.54 ms;672 列全讀時不可能(>324.7 fps 上限)。
    "480":   (330, 330,  455, 6),   # 479.52048
}
# 診斷用:把全部鍵壓成同一個格率,拿來隔離「宣告 vs 實際」這個變數。
#     OG_HSW_FPS=per-rate  (預設)  每個鍵各自的 vmax,宣告與實際一致
#     OG_HSW_FPS=240                全部 239.76(已知會凍結,保留供對照)
#     OG_HSW_FPS=30                 全部 29.97
_HSW_FPS = os.environ.get("OG_HSW_FPS", "per-rate")
# 選單最高只到 119.88(enum 11 被設定層擋掉,見 §18),所以要拿到 239.76
# 只能讓某一格的**感測器**跑 239.76 而容器仍標它自己的值。
#     OG_HSW_TOP=240   把 "120" 那一格的時序換成 239.76
#     OG_HSW_TOP=180   同理,換成 180.018(判別實驗用,見 _HSW_PER_RATE 的說明)
# 這就是高速模式的標準用法:容器 119.88、實拍 239.76 -> 2x 慢動作。
# 掛在哪一格由 OG_HSW_TOP_SLOT 決定,預設 120。
#
# **診斷時要用 30**:119.88 在 SD 卡上選不到(設定層的允許清單由媒體決定),
# 而接了 SSD 就沒有 USB shell,`rec log-out` 讀不到 req_cnt/fin_cnt。
# 把 239.76 掛到 29.97 那一格,就能在 SD 卡上、有 shell 的狀態下量 240。
#     OG_HSW_TOP=240 OG_HSW_TOP_SLOT=30 ./og3k_plan.py
# ---- >60 fps 的七欄:每一欄各自一個開關,供二分最小集合 ------------------
# §39 的七欄是「原廠影片 profile 有、p13 沒有、非幾何/非 RWZM」的全部差異,
# 整組寫進去 119.88 就不凍結了(A001_120),但**沒有二分過**。
#     OG_HIRATE=all        (預設)七欄全寫 = 已實機驗證的那一組
#     OG_HIRATE=90,DC,E4   只寫列出的那幾欄(十六進位位移,不分大小寫)
#     OG_HIRATE=none       一欄都不寫 = 回到會凍結的狀態(對照組)
# 只有 write_hirate 的目標(HSW)會用到;其他目標本來就不寫這七欄。
# ---- 畫布類別碼 +0x0A4:多要一整類緩衝(2026-09-21)------------------------
# 原廠沒有任何錄影 profile 走 FUN_c0435E38 的「8 張 / 6 張」那條,因為原廠
# 沒有任何模式超過 119.88。OG_BUFCLASS=29 把 +0x0A4 寫成 0x29,配合我們已經
# 在寫的 +0x0B0 = 1,拿到 8 張(顯示寬 x 高 x 2 = 1,396,736 B 一張)。
#     OG_BUFCLASS=off (預設)   不寫,維持原廠的 0 -> 這一類 0 張
#     OG_BUFCLASS=29           寫 0x29 -> 8 張,總配置 7.5 MB -> 18.6 MB
# 安全性分析與 sizesim 的數字見 og3kcanvas.S 裡那一段。
_BUFCLASS_ENV = os.environ.get("OG_BUFCLASS", "off").strip().lower()
if _BUFCLASS_ENV in ("off", "", "0", "none"):
    BUFCLASS = None
else:
    BUFCLASS = int(_BUFCLASS_ENV.removeprefix("0x"), 16)
    if BUFCLASS not in (0x18, 0x29):
        raise SystemExit(f"OG_BUFCLASS={_BUFCLASS_ENV!r} —— FUN_c0435E38 只有 "
                         f"0x18 與 0x29 會走到「8 張 / 6 張」那條")

_HIRATE_ALL = ("90", "B0", "C0", "DC", "E4", "FC", "100")
# 每一欄組出來的字數:PUT 是 movw/movw/str 三字,PUTW(32-bit 浮點常數)
# 多一個 movt = 四字。七欄全寫 = 5x3 + 2x4 = 23 字。
_HIRATE_WORDS = {f: (4 if f in ("FC", "100") else 3) for f in _HIRATE_ALL}
# ---------------------------------------------------------------- 池深
# 2026-09-21:240 fps 停在 150-200 格,原因不是吞吐(236 MB/s 需求 vs 實測
# >=317),是**寫入端的延遲尖峰**:A001_171 有一筆寫了 126 ms、前面空了 183 ms,
# 那段時間累積 48 格請求,描述子池從 82 掉到 15。一次停頓吃掉約 67 個描述子,
# 而 MPoolFixed<4380U,96U> 只有 96 —— 撐得過一次,撐不過第二次。
#
#     OG_POOLDEPTH=300   靜態改 v2/v4 的界線常數 + og3kcanvas 執行期換池子
#
# 每格在途成本 983,040 + 87,040 ≈ 1.02 MB,300 格 = 306 MB,RAW 有 708 MB。
POOLDEPTH = os.environ.get("OG_POOLDEPTH", "off").strip().lower()
POOLDEPTH = None if POOLDEPTH in ("off", "0", "") else int(POOLDEPTH)
if POOLDEPTH is not None and not 96 < POOLDEPTH <= 1024:
    raise SystemExit("OG_POOLDEPTH 要在 97..1024 之間")
# (位址, 立即數暫存器) —— movw/movt 對,值都是 (N-1) * 0x1128
POOL_BOUNDS = ((0xC0380CB8, 0xC0380CBC, "MPoolFixed::v2 釋放界線"),
               (0xC0380EF0, 0xC0380EF4, "MPoolFixed::v4 範圍界線"))

# OG_HIRATE 沒設時用目標自己的預設(TARGETS 的 "hirate")。HSW 要七欄全開
# (>60 fps 不凍結的那一組),OG3K 只要 90/C0 —— 它的問題不是凍結,是 live view
# 被當成照片管線在跑(見 2026-09-27 那一段)。空字串刻意不再等於 none,
# 不然「沒設環境變數」與「明確要求一欄都不寫」會分不出來。
_HIRATE_ENV = os.environ.get("OG_HIRATE", "").strip()
def _hirate_fields(default):
    env = _HIRATE_ENV
    if env == "":
        return [f for f in _HIRATE_ALL if f in default]
    if env.lower() == "all":
        return list(_HIRATE_ALL)
    if env.lower() == "none":
        return []
    want = [f.strip().upper().removeprefix("0X") for f in env.split(",") if f.strip()]
    bad = [f for f in want if f not in _HIRATE_ALL]
    if bad:
        raise SystemExit(f"OG_HIRATE 裡的 {bad} 不是 {list(_HIRATE_ALL)}")
    return [f for f in _HIRATE_ALL if f in want]
HIRATE_FIELDS = []              # 真正的值在 T 解出來之後才知道(見下面)

_HSW_TOP = os.environ.get("OG_HSW_TOP", "")
_HSW_TOP_SLOT = os.environ.get("OG_HSW_TOP_SLOT", "120")
if _HSW_FPS == "per-rate":
    HSW_TIMING = {k: _HSW_PER_RATE[k[3:]] for k, *_ in FMT_HSW}
    if _HSW_TOP:
        if _HSW_TOP not in _HSW_PER_RATE:
            raise SystemExit(f"OG_HSW_TOP={_HSW_TOP!r} 不是 "
                             f"{sorted(_HSW_PER_RATE)}")
        if _HSW_TOP_SLOT not in _HSW_PER_RATE:
            raise SystemExit(f"OG_HSW_TOP_SLOT={_HSW_TOP_SLOT!r} 不是 "
                             f"{sorted(_HSW_PER_RATE)}")
        HSW_TIMING["HSW" + _HSW_TOP_SLOT] = _HSW_PER_RATE[_HSW_TOP]
    _HSW_NOMINAL = None                      # 用 _RATE 的後綴對照
elif _HSW_FPS in _HSW_PER_RATE:
    HSW_TIMING = {k: _HSW_PER_RATE[_HSW_FPS] for k, *_ in FMT_HSW}
    _HSW_NOMINAL = {"23_98": 24, "24": 24, "25": 25, "30": 30, "48": 48,
                    "50": 50, "60": 60, "100": 100, "120": 120, "180": 180,
                    "240": 240}[_HSW_FPS]
else:
    raise SystemExit(f"OG_HSW_FPS={_HSW_FPS!r} 不是 per-rate 或 "
                     f"{sorted(_HSW_PER_RATE)}")

# ---------------------------------------------------------------- 記錄高度
# 2026-09-21:8-bit 的 CinemaDNG 在**外接**上有 30-80% 的格子,DNG 被往後推
# 7,168 或 65,536 位元組,尾巴因此被截掉(notes/HSW_240FPS_MODE12.md §67)。
# 10-bit、12-bit、原廠 FHD 8-bit 全部 0%,SD 上的 8-bit 也 0% —— 只有
# 「8-bit + 外接」會壞。而
#
#     每格檔案 = 79,872(標頭) + 2016 x 672 = 1,434,624
#     64 KB − (1,434,624 mod 64 KB) = 7,168     ← 正好是那個位移量
#
# 寫入快取(模式 2)是 64 KB 粒度的,所以幀長不是 64 KB 整數倍時會補零。
# 裁到整除是 2026-09-10「3032 -> 3024 裁到 16 對齊」的同一招:
#
#     2016 x 448 -> 79,872 + 903,168 = 983,040 = 15 x 65,536   零餘數
#     裁切 2000 x 438 仍然是 +16 寬 / +10 高的原廠慣例
#     順帶把 240 fps 的資料率從 344 MB/s 降到 236 MB/s(天花板實測 >=317)
#
# 代價:垂直視野剩 2/3,垂直拉伸 2x 之後是 2.25:1 的寬螢幕。
#
#     OG_HSW_ROWS=448   啟用;預設 672 = 原本的行為,逐位元組不變
#
# ★ 高度是由 **producer**(+0xE0/+0xE4)決定的,不是記錄矩陣 +0x04 ——
#   2026-09-21 在 RAM 裡逐欄實測出來的(改 +0x04 對 DNG 沒有任何影響)。
#   write_producer 本來就用 rec 去填那兩欄,所以改 rec 這個 tuple 就到位。
_HSW_ROWS = int(os.environ.get("OG_HSW_ROWS", "672"))
if _HSW_ROWS not in (672, 448, 336):
    raise SystemExit("OG_HSW_ROWS 只支援 672(原始)、448(幀長 64 KB 整除)或 336(配 OG_HSW_WIN)")

# ---------------------------------------------------------------- 感測器視窗
# 2026-09-26:讓 mode 12 的**感測器**只讀 _HSW_ROWS 列(OG_HSW_ROWS 本身只裁記錄端,
# 感測器仍讀 672 列,格率上限不變)。視窗暫存器由 fp/Z CAM 所有開窗模式擬合:
#     0x0003 = 1                    開窗(M58/M134/Z CAM 27 等)
#     0x0024/25 = 輸出列數 / 2      九個 fp 例子全中
#     0x0022/23 = 物理起點 + ~59    全讀出八例 58–60(notes: SENSOR_MODE_METADATA §8)
# mode 12 = 預設 48(3x6),**預設 48 沒有任何開窗先例** —— 第一次上機只驗證
# 感測器是否照窗輸出,格率先維持 240(見 notes/HSW_240FPS_MODE12.md §74)。
# 寫在 mode 12 暫存器列的 RAM 複本上,掛 og3ksel/og3kfmt 的 GTAB,選中寫、離開寫回 0。
#     OG_HSW_ROWS=336 OG_HSW_WIN=1 OG_TARGET=hsw ...
WITH_HSW_WIN = os.environ.get("OG_HSW_WIN", "0") != "0"
if WITH_HSW_WIN and (TARGET != "hsw" or _HSW_ROWS == 672):
    raise SystemExit("OG_HSW_WIN 只適用 hsw,而且要配 OG_HSW_ROWS < 672")
_HSW_WIN_START = 59 + (672 - _HSW_ROWS) // 2 * 6     # 置中;預設 48 每輸出列 = 6 物理列
HSW_WIN_MODE = 12
#                 暫存器  word  位址          原廠  開窗
HSW_WIN_REGS = ((0x0003, 2,  0xC0B66804, 0, 1),
                (0x0022, 6,  0xC0B66814, 0, _HSW_WIN_START & 0xFF),
                (0x0023, 7,  0xC0B66818, 0, _HSW_WIN_START >> 8),
                (0x0024, 8,  0xC0B6681C, 0, (_HSW_ROWS // 2) & 0xFF),
                (0x0025, 9,  0xC0B66820, 0, (_HSW_ROWS // 2) >> 8))
HSW_WIN_SPAN = (0xC0B66804, 0xC0B66824)
_HSW_ACT_H = _HSW_ROWS - 10

TARGETS = {
    # 2026-09-15 **回退**:donor 退回 p83。
    #
    # 我先前說「p221 與 p83 逐格相同」是錯的 —— 那只比了 sizing 模型會分支的
    # 12 個欄位就概括成整列。全 65 欄比對是 **9 欄不同**:
    #     +0x000/+0x004  記錄矩陣      p83 3032x2012   p221 0x0
    #     +0x024/+0x02C  active        p83 3008x2000   p221 0x0   ← 沒補
    #     +0x030         標稱 fps      18.0            50.0
    #     +0x084         RAW 平面格式  7               10
    #     +0x088         4             0                          ← 沒補
    #     +0x0B0         0             1                          ← 沒補
    #     +0x0C0         1             0                          ← 沒補
    # 我們只補了記錄矩陣與平面格式碼,active 仍是 0x0 → DefaultCropSize 為 0。
    # 實機結果:**回放當機、相機失去列舉**(2026-09-15,使用者回報)。
    #
    # p221 仍然值得追(它消掉 p83 與照片拍攝的共用),但要先把 +0x024/+0x02C、
    # +0x088、+0x0B0、+0x0C0 都弄清楚才能再上機。目標保留在下面的 og3k_p221,
    # **預設回到已驗證的 p83**。
    "og3k": dict(
        label="OG3K", profile=83, rec=(3024, 2010), act=(3008, 2000),
        write_active=False, write_producer=False,
        # 2026-09-27:錄影時 live view 在陰影處閃爍(輸出的 CDNG 正常)。
        # p83 是照片 profile,交給訊號處理引擎的畫布有三欄與原廠**影片**
        # profile 不同,而這三欄我們本來一欄都沒補:
        #     +0x0C0  p83 = 1、八個原廠影片 profile 全是 0
        #             -> 組態 +0x6C -> FUN_c01d3bc0 -> FUN_c01d7a88 回 2 而非 3。
        #             消費端把它當「往回退幾格」用(FUN_c00ce770(&ts, -N)、
        #             FUN_c00f7ed8、blk_c07 的 for i<N+1 -> FUN_c07254a8),
        #             也就是管線延遲。差一格 -> 影像與每格參數配錯格,
        #             陰影處最明顯、靜止時看不見。**與格率無關**,
        #             對得上「很多格率都會閃」。
        #     +0x090  p83 = 0、原廠影片全是 1 -> 組態 +0x84 -> FUN_c01d3558。
        #     +0x030  p83 = 18.0(照片的連拍張數用的格率),而原廠八個格率
        #             各自宣告 24/24/25/30/48/50/60/50 -> 組態 +0x10。
        #             FUN_c01caba0 的 `fps < 30` 分支在 29.97 上就分岔了
        #             (原廠 30.0 走 ÷100、我們 18.0 走 ÷33)。
        # 前兩欄借 hirate 的既有開關(值與原廠影片相同),第三欄走 write_engfps。
        write_hirate=True, hirate=("90", "C0"), write_engfps=True,
        fmt=FMT_OG3K, timing=None,
        mode=98, mode_timing=0xC0B59540, mode_stock=(0x01BD01BD, 0x0004082E),
        stock_nominal_fps=78,
        nominal_fps_addr=0xC0B59EC8, buffer_count_addr=0xC0BD47AC,
        csv=b"3,OG3K 3008x2000,,1,2",
        # 角度 wrapper 的白名單 tuple:OG3K100 走 mode117,不在 mode98 的表裡
        angle_exclude={"OG3K100"},
    ),
    # **作廢,不要再試**(2026-09-15 第五輪)。
    # p221 不是自由 profile —— 它是 `FHD24CROP` / `FHD48CROP` 的 profile B,
    # 出現在另一種 16-byte 表型 {profileA, profileB, key_ptr, class} 裡,
    # 那種表整片排在 picker 表前面的 0xC0BE4xxx-0xC0BE5xxx。
    # 借它除了要補齊九個欄位,還會跟 FHD 48p CROP 錄影直接衝突。
    # 兩種表型一起掃的結果:306 個有效 profile 裡真正沒人引用的只有 p13/p14。
    # 見 notes/OG2K_PLAN.md §Q-§S。
    "og3k_p221": dict(
        label="OG3K", profile=221, rec=(3024, 2010), act=(3008, 2000),
        write_active=True, write_producer=False,
        fmt=FMT_OG3K, timing=None,
        mode=98, mode_timing=0xC0B59540, mode_stock=(0x01BD01BD, 0x0004082E),
        stock_nominal_fps=78,
        nominal_fps_addr=0xC0B59EC8, buffer_count_addr=0xC0BD4988,
        csv=b"3,OG3K 3008x2000,,1,2",
        angle_exclude={"OG3K100"},
    ),
    "og2k": dict(
        label="OG2K", profile=13, rec=(2016, 1344), act=(2000, 1334),
        # 2026-09-27:與 OG3K 同一組缺陷。p13 交給訊號處理引擎的三欄與八個
        # 原廠影片 profile 不符,逐欄與 p83 同病(連 +0x0AC/+0x0A4 都一樣是 0,
        # 所以 og3kcanvas.S 那段安全分析原封不動適用):
        #     +0x030  p13 = 60.0    原廠各格率 24/24/25/30/48/50/60/50
        #     +0x090  p13 = 0       原廠影片 = 1
        #     +0x0C0  p13 = 1       原廠影片 = 0
        # **OG2K 的錯是反方向的**:引擎對每一個格率都被告知 60,所以
        # FUN_c01caba0 的 `fps < 30` 分支在 23.98/24/25 **永遠不會**走到,
        # 而原廠在那些格率是會走的;100p 被告知 60 而原廠說 50。
        # 見 notes/OG3K_ENGINE_CONFIG_THREE_FIELDS.md。
        write_hirate=True, hirate=("90", "C0"), write_engfps=True,
        # 生產者對 +0xD8/+0xE0 **不寫**。2026-09-15 第六輪追 FUN_c04358d0:
        #     預覽平面高 = (+0xE0 ? +0xE0 : +0x10) + [+0x88] + [+0x8C]
        # 它影響的是**預覽**平面,不是錄影平面(錄影平面走 +0x00/+0x04)。
        # p83 是 0/0(= 用柵格 2024x1341),p13 是 1920x1280 **正好等於它自己
        # 的柵格** —— 兩者都已經自洽。寫 2016x1344 進去會變成「寬 1920、
        # 高 1344」的錯配,正是 2026-09-12 那個失敗模式。
        write_active=True, write_producer=True, write_preview=True,
        fmt=FMT_OG2K, timing=OG2K_TIMING,
        mode=139, mode_timing=0xC0B599A0, mode_stock=(0x01BD01BD, 0x00060A8C),
        stock_nominal_fps=60,
        nominal_fps_addr=0xC0B5AC74, buffer_count_addr=0xC0BD471C,
        csv=b"3,OG2K 2000x1334,,1,2",
        angle_exclude=set(),
    ),
    # 2026-09-17 新增。**這一版是給 HDMI RAW 的**,不是給卡的。
    # HDMI RAW 的格式表與註冊方式見 notes/HDMI_RAW_PATH.md —— 它有專屬的
    # 26 筆表 0xC0BE5450,const 欄是 3 不是 5,profile 空間也和 CinemaDNG
    # 不同(0x16D-0x184 / 0x1BB-0x1C0),所以下面的 p14 稽核**不適用**於
    # HDMI RAW 那條路,要另外挑捐贈者。下面這組是錄影側的參數。
    # 12-bit 每格 6064x4042x1.5 = 36.76 MB,24p 要 882 MB/s,任何 SD 都不可能。
    #
    # donor profile = p14。全 65 欄對 p13(OG2K 已實機驗證)只差六欄,
    # 而那六欄正好是 write_preview / write_producer 會全部覆寫的預覽與生產者
    # 幾何(+0x00C/+0x010/+0x020/+0x028/+0x0D8/+0x0E0)。
    # 記錄矩陣、active、標稱 fps、平面格式碼,以及害 p221 回放當機的
    # +0x088/+0x0B0/+0x0C0,p13 與 p14 **完全相同**。
    #
    # act = rec - (16,10),和 OG3K/OG2K 同一個慣例。rec 直接用感測器視窗
    # (和 OG2K 一樣,不像 OG3K 要修寬度)—— 6064 的三種位深列距都是整數:
    #     x1.5 = 9096   x1.25 = 7580   x1.0 = 6064
    # 6048x4032 正好是 OG2K 2016x1344 的三倍。
    "og6k": dict(
        label="OG6K", profile=14, rec=(6064, 4042), act=(6048, 4032),
        write_active=True, write_producer=True, write_preview=True,
        fmt=FMT_OG6K, timing=OG6K_TIMING,
        mode=3, mode_timing=0xC0B59560, mode_stock=(0x01BD01BD, 0x00081516),
        stock_nominal_fps=30,
        nominal_fps_addr=0xC0B59F2C, buffer_count_addr=0xC0BD4720,
        csv=b"3,OG6K 6048x4032,,1,2",
        angle_exclude=set(),
    ),
    # 2026-09-20 新增。donor 感測器模式 = M12 `MONIT1_240`,2016x672 @ 239.760。
    #
    # profile = **p13**,和 OG2K 同一個(兩者是不同的卡,不會同時存在)。
    # p13 沒有被任何表引用、+0x1C = 2(3:2)、+0x030 是正值(張數 3),
    # 而它與幾何有關的欄位全部由 write_active / write_producer / write_preview
    # 覆寫 —— 這正是 OG2K 已實機驗證過的用法。
    #
    # rec 直接用感測器光柵 2016x672,act = rec - (16,10),和 OG2K/OG6K 同慣例。
    # 2016 是 16 的整數倍,672 也是,列距三種位深都是整數:
    #     x1.5 = 3024   x1.25 = 2520   x1.0 = 2016
    #
    # ★ 已知不符:畫布的**感測器視窗** +0x0F4/+0x0F8 錄影路徑不寫,所以會留著
    #   p13 原廠的 2016x1344,而 mode 12 實際只讀 672 行。這不是 HSW 獨有 ——
    #   OG6K 拿同族的 p14(視窗一樣 2016x1344)去錄 6064x4042,錯得更多,
    #   而 OG3K 只是剛好 p83 的視窗就等於它的光柵。四個目標裡三個不符,
    #   所以先照既有設計一個位元都不寫;若第一段素材的幾何是錯的,
    #   這是第一個該翻的開關(見 notes/HSW_240FPS_MODE12.md §5)。
    #
    # stock_nominal_fps = 240:mode 12 的 metadata +0x40 原廠就是真實格率,
    # 所以角度修正整組關掉(見 _ANGLE_FIX_TARGETS)。angle_exclude 因此無作用,
    # 但仍留空集合,好讓 check() 的「格式 vs nominal-fps 集合」等式成立。
    "hsw": dict(
        label="HSW", profile=13, rec=(2016, _HSW_ROWS), act=(2000, _HSW_ACT_H),
        write_active=True, write_producer=True, write_preview=True,
        # 2026-09-20 實機之後加上:p13 的感測器視窗是 2016x1344,而 mode 12
        # 只讀 672 行。不寫它 -> 22 格請求永不完成、錄影結束不了。
        write_window=True,
        # 診斷用:把執行期的畫布位址記進 LOG+0x14,讓 shell 能直接讀真正的
        # 畫布內容。先前從 profile 的靜態欄位表推論 +0xA4/+0xB0 失敗了。
        canvas_ptr_log=True,
        # >60 fps 的關鍵。沒有它,119.88/239.76 會讓錄影凍結(實機證明)。
        write_hirate=True,
        fmt=FMT_HSW, timing=HSW_TIMING,
        mode=12, mode_timing=0xC0B59A40, mode_stock=(0x014A014A, 0x0006038E),
        stock_nominal_fps=240,
        nominal_fps_addr=0xC0B5AE68, buffer_count_addr=0xC0BD471C,
        csv=b"3,HSW 2000x662,,1,2",
        angle_exclude=set(),
        # 十個格率鍵全部指向同一組時序,所以 nominal class 是**感測器實際格率**,
        # 不是選單上那個數字。check() 會用 round(實際 fps) 驗這一點。
        nominal_fps_fixed=_HSW_NOMINAL,
    ),
}
# 傳給 clang 前處理器的目標參數(.S 是大寫,所以前處理器有跑)。
def _defines(t):
    d = [f"TARGET_PROF={t['profile']}", f"TARGET_W={t['rec'][0]}",
         f"TARGET_H={t['rec'][1]}", f"TARGET_AW={t['act'][0]}",
         f"TARGET_AH={t['act'][1]}", f"TARGET_MODE={t['mode']}",
         f"TARGET_MODE_TIMING={t['mode_timing']:#x}",
         f"TARGET_MODE_W0={t['mode_stock'][0]:#x}",
         f"TARGET_MODE_W1={t['mode_stock'][1]:#x}"]
    if t["write_active"]:
        d.append("TARGET_WRITE_ACTIVE=1")
    if t["write_producer"]:
        d.append("TARGET_WRITE_PRODUCER=1")
    if t.get("write_preview"):
        d.append("TARGET_WRITE_PREVIEW=1")
    if t.get("write_window"):
        d.append("TARGET_WRITE_WINDOW=1")
    if t.get("canvas_ptr_log"):
        d.append("TARGET_CANVAS_PTR_LOG=1")
    if t.get("write_hirate"):
        d += [f"TARGET_HIRATE_{f}=1" for f in HIRATE_FIELDS]
    if BUFCLASS is not None:
        d.append(f"TARGET_BUFCLASS={BUFCLASS:#x}")
    if POOLDEPTH is not None:
        d.append(f"TARGET_POOLDEPTH={POOLDEPTH}")
    # og3ksel 的格式條件要跟著整組開關 —— 關掉時 og3ksel 必須逐位元組回到
    # 2026-09-21 之前的樣子,A/B 才乾淨。
    if WITH_FMTGUARD:
        d.append("TARGET_FMT_GUARD=1")
    if WITH_ENGFPS:
        d.append(f"TARGET_ENGFPS={ogv(FPSLATCH):#x}")
    if WITH_MATCH:
        d += [f"TARGET_MATCH={ogv(MATCH):#x}",
              f"TARGET_LABEL={int.from_bytes(t['label'].encode(), 'little'):#x}"]
    if V3:
        d += ["OG_V3=1", f"OGV={V3_OGV:#x}"]
    if CHAIN:
        if TARGET not in OG_ENUMS:
            raise SystemExit(f"OG_CHAIN: no resolution enum for {TARGET!r}")
        d += [f"OG_ENUM={OG_ENUMS[TARGET]}", "OG_SAVE_ENUM=1"]
    if WITH_CLAMP:
        d.append(f"OG_GTAB_SHARED={GTAB_SHARED_GROUPS}")
    return d


if TARGET not in TARGETS:
    raise SystemExit(f"OG_TARGET={TARGET!r} 不是 {sorted(TARGETS)}")
T = TARGETS[TARGET]
FMT = T["fmt"]
if T.get("write_hirate"):
    HIRATE_FIELDS = _hirate_fields(T.get("hirate", _HIRATE_ALL))
# 引擎格率鎖存(畫布 +0x030)。donor 是照片 profile 或自由 profile 時,它原廠
# 帶的格率與我們實際在錄的格率無關,而訊號處理引擎就靠這一欄。
#     OG_ENGFPS=0   不鎖存(對照組:引擎繼續看到 donor 原廠的值)
#     OG_ENGFPS=1   鎖存,即使目標的預設是關
WITH_ENGFPS = os.environ.get("OG_ENGFPS", "1" if T.get("write_engfps") else "0") != "0"
# 顯示鏈跟著 picker(見 MATCH 的說明)。OG_MATCH=0 回到「只看 FLAG」= 改動前。
WITH_MATCH = os.environ.get("OG_MATCH", "1") != "0"
DEFINES = _defines(T)
# 少寫一欄 hirate 就少那幾個字。_BASE_PLAN_WORDS 記的是七欄全開的基準。
if T.get("write_hirate"):
    EXPECTED_PLAN_WORDS -= sum(w for f, w in _HIRATE_WORDS.items()
                               if f not in HIRATE_FIELDS)
if WITH_MATCH:
    # 實測(2026-09-27):
    #   fmttable        64 -> 77 字   命中寫 1、表尾比對標籤並清 0
    #   og3kaspect       9 -> 14 字   beq + LDA + ldr + cmp + 標籤
    #   og3kaspect2      9 -> 14 字
    #   og3kout        112 -> 117 字  只收緊 FLAG 那一支,PBFLAG 不碰
    #   state()          +1 字        MATCH 開機值 1
    EXPECTED_PLAN_WORDS += 13 + 5 * 3 + 1
if WITH_ENGFPS:
    # fmttable 的鎖存 4 字(LDA 兩字 + ldr + str)、og3kcanvas 的寫入 5 字
    # (LDA 兩字 + ldr + cmp + strne)、state() 把 FPSLATCH 歸零 1 字。
    EXPECTED_PLAN_WORDS += 10
if CHAIN:
    # OG_SAVE_ENUM (2026-10-07, OG3K and OG2K on one card), og3ksel:
    #   OGSAVE keeps the chosen OG's enum: str -> ldr/cmp/movne/bne/cmp/moveq/str  +6
    #   leaving for another OG skips the shared preview heights:
    #     LDA 2 + ldr/cmp/cmpne/bne                                               +6
    # (OG_V3 turns the LDA's movw/movt into 3 words; that +1 is v3_growth.)
    EXPECTED_PLAN_WORDS += 12
if WITH_CLAMP:
    # og3ksel: mov r7,#0 + (movne for bne) + cmp/streq for str + cmp/subne  +4
    # GTAB: one group per clamp word (count, on, off, address)              +4 each
    EXPECTED_PLAN_WORDS += 4 + 4 * len(CLAMP_FIELDS) * len({d for _, d, _, _ in FMT})
if BUFCLASS is not None:
    EXPECTED_PLAN_WORDS += 3        # PUT 0xA4 = movw/movw/str
if POOLDEPTH is not None:
    # 4 個靜態界線字 + og3kcanvas 的呼叫(12 字)+ poolinit payload(67 字)。
    # 字數與 N 無關(塊數是立即數),所以是常數。
    EXPECTED_PLAN_WORDS += 83
if WITH_V3TAP:
    # 兩個 GTAB 群組:(筆數, 選中值, 未選值) x2 + 三個位址。
    EXPECTED_PLAN_WORDS += 9
if WITH_HSW_WIN:
    # 每個視窗暫存器一個 GTAB 群組:(筆數, 選中值, 未選值) + 一個位址。
    EXPECTED_PLAN_WORDS += 4 * len(HSW_WIN_REGS)


# 預覽可見高:同一組「PARAM+1C == 1」的兄弟 profile 的 PARAM+0x28。
# 待機用 profile 5,半按與錄影會切到其他幾個,所以全部都要跟著旗標切換。
PREV = [0xC0BDB9CC,   # profile 5
        0xC0BDBC28,   # profile 210
        0xC0BDBC60,   # profile 227
        0xC0BDBC8C,   # profile 257
        0xC0BDBC90,   # profile 258
        0xC0BDBC94]   # profile 259

# RWZM —— open gate 的關鍵,而且是 2026-09-12 那次「錄出來只有左上一塊有畫面」
# 的真正原因。0x640 = 1600 = 1.5625x 的實質縮小會把 producer 的有效區釘在
# 1936 寬;unity 0x400 才填滿 3032x2012。
#
# 八個格率用八個不同的 profile,四個欄位(PARAM +0x60/+0x64/+0xD0/+0xD4)
# 全都要補 —— 舊 AutoRun 只補了 profile 175 那四欄(它的列號 122 曾被誤記為
# 「profile 122」),所以其他七個格率本來就是壞的。
#
# 這些 profile 與 FHD 共用,所以由 og3ksel 跟著旗標切換,不能寫死。
RW_PROFILES = [173, 174, 175, 176, 178, 180, 430, 431]
# 四個欄位其實分兩組:
#   +0x60 / +0xD0   預覽(live)RWZM
#   +0x64 / +0xD4   RAW(錄影)RWZM
# 舊筆記說「四個都要 unity」,但那個實驗沒有分離變數。錄影要填滿 3032x2012
# 需要的只是 RAW 那一對。
#
# 2026-09-12 試驗:預覽那一對留在原廠 1600。理由是使用者觀察到「上下閃爍只在
# 錄影時出現,而且換 SSD 樣子會變」—— 跟儲存媒體有關就不是幾何錯誤,是頻寬。
# 預覽走 unity 會讓 producer 從 1936x1090 變成產出 3032x2012(資料量 2.9 倍),
# 錄影時與 RAW writer 搶頻寬,預覽來不及完整更新。
# 待機正常(截圖 SS__0408 證實),所以預覽本來就不需要 unity。
# 2026-09-12 試驗結果:只讓 RAW 那一對 unity → **錄影變花屏**,而且相機隨後凍結。
# 所以預覽那一對確實也影響 producer,舊筆記說的「四個都要 unity」是對的。
# 這一組是 A001_002 / A001_003 / A001_082 解檔驗證過的,不要再拆。
RW_OFFSETS  = [0x60, 0x64, 0xD0, 0xD4]
RW_ON, RW_OFF = 0x400, 0x640
PREV_ON, PREV_OFF = 1334, 1125

# 感測器暫存器表:描述子 {table, count} 在 0xC0B5FDA4,每列 162 字 = 648 bytes,
# word 0 是模式 enum,word k 由 FUN_c03258c8 第 k 次呼叫寫到它的 movw 立即數
# (0xC03258F8 + (k-1)*32 + 24;research/imaging-hw/notes/SENSOR_REGISTER_DECODE.md)。
# 位址寫死是為了讓 OWNED 在模組層就能用,check() 會從映像重新導出並比對。
SREG_DESC, SREG_STRIDE, SREG_CALLS = 0xC0B5FDA4, 648, 0xC03258F8
V3TAP_MODE = 139
#            暫存器  word  位址         原廠 → 3 抽頭
V3TAP_REGS = ((0x0737, 143, 0xC0B65D90, 2, 4),
              (0x0738, 144, 0xC0B65D94, 2, 4),
              (0x0734, 140, 0xC0B65D84, 3, 5))
V3TAP_SPAN = (0xC0B65D84, 0xC0B65D98)

# 2026-09-12 試驗:改用韌體原生的 3:2 profile,而不是借 FHD 的。
#
# profile 43(列 30)與 83(列 42)是重複的兩份,而且沒有被任何 movie picker
# 引用。它們本來就是:
#     +000/+004  3032x2012     RAW 幾何
#     +024/+02C  3008x2000     active
#     +0F4/+0F8  3032x2012     感測器視窗
#     +064/+0D4  1023          RAW RWZM 已是 unity
#     +00C/+010  2024x1341     預覽柵格
#     +020/+028  2000x1334     預覽可見
#     +01C       2             3:2 標記(借 FHD 的是 1)
#
# 也就是說我們整晚在 FHD profile 上補出來的東西,韌體本來就有一份。
# 唯讀重用 —— 不改那個 profile,只在格式表裡引用它。
#
# 2026-09-12 實測結果:**沒有帶來預期的好處,而且多了一個缺陷。**
#   - 回放仍然花屏,HUD 仍然寫 FHD。原因是回放走 LiveViewModeMgr 的常數池
#     比對(0xC0BCFE70 起:4096x2160 / 3840x2160 / 1280x720,FHD 是回退值),
#     跟錄影 profile 完全無關。
#   - 錄影結束時多出一禎花屏。
# 所以退回 None(沿用捐贈 slot 的 profile)= A001_008/009/010 驗證過的組態。
#
# 要再試的話:profile 83 是 43 的重複份;另外 +0x030 那個浮點兩者不同
# (p43 = 3212836864,p175 = 1106247680),還沒查清楚是什麼。
# 2026-09-13:改用 **p83**,不是 p43。
#
# 照片表有兩張,幾何成對相同,只差「張數」(也就是 +0x030):
#     檢視表 0xC0BE5CF0  {1, 43, 98, "12BLOW"}  +0x030 = -1.0   張數 0
#     拍攝表 0xC0BE5D70  {1, 83, 143, "12BLOW"} +0x030 = 18.0   張數 3
# 兩列 65 個字裡**只有 +0x030 不同**,其餘完全一致
# (3032x2012 / 3008x2000 / 視窗 3032x2012 / +1C = 2 / RAW RWZM unity)。
#
# 用 p43 的代價:它是照片「檢視」profile,張數原廠是 0。錄影需要張數 3,
# 所以 fmttable 要把畫格率寫進它的 +0x030 —— 而那一寫就讓 S 尺寸 12-bit
# 照片的檢視突然要求三張原本不配置的 3032x2012 RAW 緩衝。
# 2026-09-13 使用者拍一張 S 尺寸照片,相機當場凍結。
#
# 用 p83:張數原廠就是 3,**一個原廠欄位都不用改**,p43 保持原封不動。
# 2026-09-15:p83 → **p221**。
#
# p83 是 S 尺寸照片的「拍攝」profile,照片拍攝表 0xC0BE5D70 引用它。借它就
# 必須用 FLAG 守衛畫布 hook,而 FLAG 是選單狀態 —— 選了 OG3K 再去拍照時
# 旗標仍然立著,那是 og3kcanvas.S 檔頭自己寫下的已知缺口。
#
# 全映像掃描所有 {1|5|6, profile, mode, key_ptr} 表項後,306 個有效 profile
# 裡有 132 個**沒有被任何表引用**;其中 +0x1C == 2(3:2)的只有 p13/p14
# (視窗 2016x1344)與 p221/p222(視窗 3032x2012)。
#
# p221 與 p83 在**每一個會影響分支的欄位上逐格相同**:
#     +0x1C +0x3C +0x44 +0x7C +0xA4 +0xB4 +0xCC +0xD8 +0xE0 +0xF0 +0xF4 +0xF8
# 畫布要寫的 PUT 完全一樣(錄影矩陣 + 平面格式碼),離線模擬的總配置還少
# 52,960 bytes(15,014,704 對 15,067,664),RAW 平面同為 9,117,384。
#
# 換過去之後「選著 OG3K 拍照」這個衝突**不存在**,不需要驗證。
# 詳見 notes/OG2K_PLAN.md §I。
OG_PROFILE = T["profile"]

#  鍵          donor  時序抄自  picker 表3 slot
# donor = **感測器模式**(imager mode_list 的 enum),不是 PARAM profile。
# 2026-09-14 用 `imager mode_list` 讀出 3032x2012 / 3:2 / full 的模式只有四個:
#     0098 ACQ_12BIT_MIX              30fps   ← 擷取(拍照)類
#     0011 MONIT1_120                105fps   ← 監看(影片)類
#     0117 MONIT1_100                100fps   ← 監看(影片)類
#     0143 ACQ_12BIT_CONTINUOUS_MIX   18fps   ← 擷取類
#
# 原本七個格率用 98(ACQ),而 ACQ 是**拍照擷取**的感測器模式 →
# imager 給 gain_state = acq(1)→ 雙原生 HCG 門檻 **640**,
# 而 12-bit CinemaDNG 應該是 gain_state 7 → 門檻 **3200**。
# 後果不只是機內回放過亮:ISO 640 以上會**少掉約 2.7 檔高光餘裕**
# (實測 raw 比原廠 FHD 亮 2.675 EV,BaselineExposure 只有 +0.322 而非 +3.0)。
#
# 改用 11(MONIT1_120)—— 同樣 3032x2012 / 3:2 / full,但是**影片類**。
# 時序仍然各自取自 MONIT1_*_HD 那一欄,donor 只提供格式編號與 TT 指標。
#
# 預測:117 本來就是 MONIT 類,所以 OG3K100 原本就不該過曝;
#       只有用 98 的那七個格率會。這一點可以用來驗證這個假設。
#  鍵          donor  時序抄自  picker 表3 slot
# 2026-09-14 訂正:donor 曾改成 11(MONIT1_120)測試,當時**看起來沒有效果**,
# 因為那條路被 FUN_c03a66b0 的提前返回擋住了。等到補上旗標 bit3 之後,
# FUN_c03a66b0 會繼續執行到
#     FUN_c030ce00(imager_mgr, FUN_c03a67a8())   // = 名稱表表項的第三欄 = donor
# 於是 donor 真的被送去設定感測器 —— 而 11 是 **105 fps** 的模式,
# 我們卻在錄 29.97,讀出組態不匹配 → 錄影預覽又暗又綠、雜訊很重。
# 兩個改動單獨都無害,合在一起才出事。
# 改回 98 = ACQ_12BIT_MIX(3032x2012 @30fps),與我們的用法相符。

# mode 98 的 metadata +0x40 原廠是 78。快門角度 AE 把它當成 nominal fps，
# 因而把 29.97/180° 算成 1/156（約 -1.38 EV）。同一 mode 承載七個 OG3K
# 格率，不能把 mode 98 的共用欄位硬改成 30；改由格式表每次命中時鎖存目前
# 選項的整數 nominal class，只在四條已確認的角度換算／同步
# callsites 使用；不改共用 getter 或 mode metadata。
_RATE = {"23_98": 24, "24": 24, "25": 25, "30": 30,
         "48": 48, "50": 50, "60": 60, "100": 100, "120": 120,
         "240": 240}
# HSW 這種「感測器格率與選單格率刻意不同」的目標用 nominal_fps_fixed 覆寫:
# 角度 AE 要的是**真實擷取率**,不是容器格率。
_FIXED_FPS = T.get("nominal_fps_fixed")
NOMINAL_FPS = {k: (_FIXED_FPS if _FIXED_FPS is not None
                   else _RATE[k[len(T["label"]):]]) for k, *_ in FMT}
DONOR_FPS_VALUES = frozenset(
    NOMINAL_FPS[k] for k, *_ in FMT if k not in T["angle_exclude"])
DONOR_NOMINAL_FPS_ADDR = T["nominal_fps_addr"]
DONOR_TIMING_ADDR = T["mode_timing"]
DONOR_TIMING_STOCK = T["mode_stock"]
BUFFER_COUNT_ADDR = T["buffer_count_addr"]   # donor PARAM+0x030；一個位元都不寫
# 上面這組常數 2026-09-20 從 MODE98_* 改名成 DONOR_*。原名是 OG3K 留下的:
# 它們指的一直是**當前目標的 donor**,在 OG2K 上是 mode 139、OG6K 是 mode 3、
# HSW 是 mode 12 —— 叫 MODE98 是字面上的錯誤。符號改名不影響組出來的位元組。

# 2026-09-13 實驗:分辨「欄位數不對」與「TEXT 必須是字串資源 ID」哪一個
# 造成選單顯示索引 `3`。
#
# 原廠是 6 欄、\r\n:
#     NO,TEXT,Popup,IMAGE,Enabled,Enabled2
#     1,0313,Popup,blank,1,2
#     2,0314,Popup,blank,1,2
# 這塊空間只有 92 bytes(原廠區塊就佔 89),用原廠標頭再加第三列要 111,
# 放不下 —— 所以把**標頭名稱**縮短,欄位數與順序保持 6 欄不變。
# 這同時也在賭「解析器按位置對欄,不按名稱」。
#
# 如果選單顯示 "OG3K" → TEXT 可以放字面字串,問題只是欄位數。
# 如果還是顯示 "3"    → TEXT 必須是字串資源 ID,得去追那個資源系統。
# 如果整列消失        → 解析器按名稱對欄,標頭不能縮。
# 2026-09-13 實驗結果:用原廠的 6 欄格式但把**標頭名稱縮短**,
# 那一列直接**消失** → 解析器是**按名稱對欄**的,標頭不能動。
# 而用原廠標頭再加第三列需要 111 bytes,這塊空間只有 92(原廠就佔 89)。
# 所以「在原地加一列格式正確的」是不可能的。
#
# 退回 5 欄版:格式不完全合(少了 Popup 欄、用 \n),但那一列**存在而且可選**,
# 只是 TEXT 解析不到就退回顯示 NO 欄的 `3`。
# 功能完整,只有標籤不好看。
# CSV 的 TEXT 欄放的是**字串資源 ID**。對照表在 0xC0D0xxxx 起的本地化字串區,
# 格式是 `"NNNN\0" + 文字\0`,每種語言一份:
#     0313 → "UHD 3840x2160"      0314 → "FHD 1920x1080"
# 我們原本塞字面字串,解析不到就退回顯示 NO 欄的 `3`。
#
# 2026-09-13:整個韌體裡含 "3008x2000" 的字串只有兩個 ID,都是
#     0257 / 0865 → "LOW 6M 3008x2000"     (S 尺寸照片的標籤)
# 不完美(前綴是 LOW 6M),但**解析度是對的,而且是現成的原廠資源**,
# 完全可加性 —— 比顯示 `3` 好得多。
#
# 空間仍然只有 92 bytes,所以 Popup 欄還是放不回去(加回去要 111),
# 但改用 ID 之後省下的空間夠把換行換回原廠的 \r\n。
# CSV 的 TEXT 欄**可以直接放字面字串** —— 下拉清單會照著顯示。
#
# 2026-09-13 我一度以為那一欄必須是字串資源 ID(原廠用 0313/0314,對照表在
# 0xC0D0xxxx 的本地化字串區),因為**收合的摘要那一行**顯示 `3`。
# 那個推論是錯的:收合摘要與下拉清單是兩個不同的來源,下拉清單一直都好好地
# 顯示 "OG3K 3008x2000"。把 TEXT 換成現成的資源 ID 0257 之後,清單變成
# "LOW 6M 3008x2000"(S 尺寸照片的標籤)—— 解析度對但更難懂,是退步。
#
# 所以維持字面字串。剩下的兩個外觀問題(收合摘要顯示 `3`、QS 的格子與選項條)
# 與這一欄無關。
# CSV 的 TEXT 欄**可以直接放字面字串**,下拉清單會照著顯示 ——
# 2026-09-13 我一度以為必須是字串資源 ID,那是錯的(下拉清單一直都好)。
#
# 沒解決的是**收合的摘要那一行顯示 `3`**。唯一具體的差異是 IMAGE 欄:
# 原廠兩列是 `blank`,我們那一列是空的。先前的筆記說那一欄是
# 「外層摘要用圖片資源還是文字」的開關,所以這一版把它補成 `blank` 測試。
#
# 空間只有 92 bytes,補上 blank 之後標籤最多 12 字,所以用 "OG3K 3:2"。
# 若摘要因此顯示正常,再回頭權衡標籤長度。
# TEXT 欄可以直接放字面字串,下拉清單會照著顯示。
# IMAGE 欄補成 blank 測過,收合的摘要仍然顯示 `3`,而且標籤被迫縮短成
# "OG3K 3:2" 反而難懂 —— 那個測試是失敗的,退回較長也較清楚的標籤。
NEW_CSV = (b'\xef\xbb\xbfNO,TEXT,IMAGE,Enabled,Enabled2\n'
           b'1,0313,blank,1,2\n'
           b'2,0314,blank,1,2\n'
           + T["csv"])

# 2026-09-12 拆解第 1 步:改用 p43 之後,畫布 hook 命中 0 次而錄影仍然完整
# (A001_013/014,相關 0.97-0.99)。p43 本身就是 3032x2012 / 3008x2000,
# 所以 rowpatch 的 14 個 PUT 全部多餘。拆掉它也順帶解掉「canvas 分不出
# OG3K 和 FHD」而需要旗標守衛的問題。
# 要退回就把這個設 True。
WITH_ROWPATCH = False

# 2026-09-12 拆解第 2 步「全拆再回頭」:p43 帶著 +1C = 2 的 3:2 標記、
# RAW RWZM 原廠就是 unity、預覽欄位原廠就是 2024x1341 / 2000x1334,
# 所以下面這些可能全部多餘。一次全關,不行再逐項打開。
# 拆成兩個,才知道哪一半真的需要:
WITH_PREV    = True     # 六個預覽 profile 的可見高 1125 → 1334
WITH_RWZM    = False    # 八個 profile 的 RWZM → unity(p43 的 RAW 那對原廠就是 0x3FF)
WITH_ASPECT  = True     # C0306EA0 / C0306EEC 的長寬比 enum 3 → 2
WITH_OUT     = True
WITH_RANGE   = False
# v2:不改原廠名稱表,改成 hook FUN_c0437af8 換指標(見 og3kpb.S)。
WITH_PLAYBACK = False
# og3kpbrow:給 12-bit 影片回放的畫布加一個 3:2 的 case(不換 profile)。
# 與 rowpatch 共用 0xC043A19C,兩者互斥。
# 2026-09-13 實測:hook 確實命中 33 次改了 p51 的畫布,**畫面完全沒變**。
# 所以 FUN_c043a158 載入的 PARAM 幾何只餵 FUN_c0434ec0 的緩衝尺寸,
# 不是回放顯示幾何的來源。關掉,留著 payload 與計數器供下次用。
WITH_PBROW = False

# og3kcanvas —— 2026-09-13 **回放解決了**。一個 hook(0xC043A19C)兩個 case,
# 都只改畫布的 RAM 複本,原廠 PARAM 列一個位元都不動。
#
#   錄影:記錄尺寸 3032x2012 → 3024x2010
#     原廠三個影片錄影 profile 全是「裁切 +16 寬 / +10 高」而且寬度 16 對齊:
#         p171 3856x2170 / 3840x2160      p173 1936x1090 / 1920x1080
#     p83 是**照片** profile,用的是感測器視窗 3032x2012(+24/+12),
#     而 3032 = 8 x 379 只有 8 對齊 —— 不符合影片的慣例。
#
#   回放:把柵格設成與片子記錄尺寸**完全相同**的 3024x2010
#     原廠回放 profile 的柵格正好等於該格式片子的記錄尺寸
#     (p53 1936x1090 = FHD 片子;p51 3856x2170 = UHD 片子),
#     所以柵格就是「來源列距」。我們的片子沒有對應 profile,
#     退回 p51(3856)或 p53(1936),都與實際寬度不符 → 花屏。
#
# 驗證:A001_036 解檔(標頭 3024x2010、裁切 3008x2000 @ (8,5)、
# StripByteCounts 9,117,360 = 3024x2010x1.5,整幅清晰無剪切);
# A001_037 機內回放截圖 SS__0426 完全正常。
WITH_CANVAS = True

# og3kgs —— 2026-09-14。OG3K 的擷取原本拿到 gain_state 3(HCG 門檻 640),
# 在 ISO 640 以上就切到高轉換增益,**少掉約 2.7 檔高光餘裕**,而且因為
# 機內回放固定補 +3 EV,回放會過曝 2.7 檔。原廠 12-bit CinemaDNG 是
# gain_state 7(門檻 3200)。
#
# 決定它的是 FUN_c043a1c8(pid) 依 pid 數值範圍算出的旗標,而 131..190
# 裡沒有任何空的 pid,所以不能換 pid;補旗標 bit3 又會連帶讓
# FUN_c03a66b0 在錄影中重設感測器模式 → 預覽綠色閃爍。
# 所以只 hook 增益分派那一路的判斷 FUN_c03a6dd8,讓它在 OG3K 被選中時回 1。
WITH_GS = True
assert sum((WITH_ROWPATCH, WITH_PBROW, WITH_CANVAS)) <= 1, "三者共用 0xC043A19C"

# og3kcanvas 會寫進畫布的每一格。check() 會比對 .S 裡的 PUT。
CANVAS_REC = {0x00: T["rec"][0], 0x04: T["rec"][1], 0x80: 7}
if T["write_active"]:
    CANVAS_REC.update({0x24: T["act"][0], 0x2C: T["act"][1]})
if T["write_producer"]:
    CANVAS_REC.update({0xD8: T["rec"][0], 0xE0: T["rec"][1]})
if T.get("write_preview"):
    CANVAS_REC.update({0x0C: T["rec"][0], 0x10: T["rec"][1],
                       0x20: T["act"][0], 0x28: T["act"][1]})
# 感測器視窗。donor 的原廠值與實際讀出不符時才寫 —— 見 og3kcanvas.S 的說明。
if T.get("write_window"):
    CANVAS_REC.update({0xF4: T["rec"][0], 0xF8: T["rec"][1]})
# >60 fps 需要的那一組(2026-09-20 實機證明)。見 og3kcanvas.S 的說明。
if T.get("write_hirate"):
    _HIRATE_VALS = {"90": (0x90, 1), "B0": (0xB0, 1), "C0": (0xC0, 0),
                    "DC": (0xDC, T["rec"][0]), "E4": (0xE4, T["rec"][1]),
                    "FC": (0xFC, 0x40000000), "100": (0x100, 0x40000000)}
    CANVAS_REC.update(dict(_HIRATE_VALS[f] for f in HIRATE_FIELDS))
# 畫布類別碼。只有錄影路徑寫,回放不碰。
if BUFCLASS is not None:
    CANVAS_REC[0xA4] = BUFCLASS
# 平面格式碼 eRawBitType -> (+0x080 預覽平面, +0x084 RAW 平面)。
# 值域見 FUN_c04356b0 的 bpp_of:7 -> 12-bit、9 -> 10-bit、10 -> 8-bit。
# 這三列就是原廠三胞胎 (p131/p151/p171 等) 65 欄裡唯一不同的兩欄。
CANVAS_PLANE = {0: (7, 7), 3: (10, 9), 4: (10, 10)}
# 回放:柵格 = 片子的記錄尺寸,可見 = DNG 裁切,視窗 = 柵格(縮放 unity)。
CANVAS_PB  = {0x1C: 2, 0x0C: T["rec"][0], 0x10: T["rec"][1],
              0xD8: T["rec"][0], 0xE0: T["rec"][1],
              0x20: T["act"][0], 0x28: T["act"][1],
              0xF4: T["rec"][0], 0xF8: T["rec"][1],
              0x60: 1024, 0xD0: 1024, 0x64: 1024, 0xD4: 1024}

# og3kpbsel:回放時讓 v3 回傳照片檢視那一筆現成的表項,v5 就會選到
# param_1+0x268 的照片管線(3:2,已經能正確顯示 3032x2012 12-bit)。
# 見 og3kpbsel.S 的檔頭與筆記第 9 節。
# 2026-09-13 實測:機制正確(40 命中 / 36 放行,原廠 FHD 片子完全沒被碰到),
# 但**照片管線放不出我們的影格**。S 尺寸照片的 DNG 是:主 IFD = 160x120 縮圖、
# 影像在 SubIFD(Compression=7,tile 256x256),而且另外帶一張
# **3008x2000 的 RGB JPEG 全尺寸預覽**。照片檢視顯示的是那張 JPEG,
# 根本不解 RAW。CinemaDNG 的影格沒有內嵌預覽,所以照片管線找不到來源,
# 畫出緩衝殘留 = 粉綠斑點(截圖 SS__0422)。
#
# 反過來說,影片回放管線(+0x514 等)才是真的會解未壓縮 12-bit RAW 的,
# 它對 1936x1090 完全正確,問題只在幾何。幾何在 XC_LiveViewDispParam 的
# 描述子槽裡,而那個取用點(XC_LiveViewDispParam::v5 = 0xC0437E98)
# og3kout 已經掛著了。先量出回放用的描述子再說。
WITH_PBSEL = True
assert not (WITH_ROWPATCH and WITH_PBROW), "rowpatch 與 og3kpbrow 共用 0xC043A19C"

# og3kpbrow 寫進畫布的每一格,以及它抄自 p43 的哪一格。
# check() 會對著韌體映像驗證這些常數確實等於 p43 的欄位值 ——
# 預覽柵格的四捨五入方式每個模式都不同,算出來的一定錯,只能抄。
PBROW_FROM_P43 = {0x1C: 0x1C, 0x0C: 0x0C, 0x10: 0x10, 0xD8: 0x0C, 0xE0: 0x10,
                  0x20: 0x20, 0x28: 0x28, 0x60: 0x60, 0xD0: 0x60,
                  0xF4: 0xF4, 0xF8: 0xF8}
# 2026-09-13 兩種做法都驗證過,都是黑屏:
#   v1 改原廠名稱表的 profile id      → 破壞該 profile 的反向查詢,且引入 p43
#   v2 hook FUN_c0437af8 換指標(乾淨) → 替換確實發生(PBFLAG 從 0 變成有效),
#                                       畫面一樣黑
#
# 結論 **p43 不能當影片回放 profile** 是對的,但我先後給的兩個原因都是錯的,
# 已經收回(見 notes/OG3K_PLAYBACK_PROFILE_CLASSES.md):
#   × 「緩衝池爆掉」—— 照 FUN_c0435588 重算(sizesim.py):p43 要 15.7 MB,
#      而回放正在服務的 p51 要 22.0 MB。尺寸從來不是問題。
#   × 「RAW 半部讓配置器多了不預期的欄位」—— +0x3C == 0,RAW 維度沒被讀。
#
# 真正的原因是 **profile 有類別**,由 (+0x44, +0x80) 決定:
#   照片檢視類(p41-46,3:2 純預覽): +0x44 = 0      +0x80 = 0xA
#   影片回放類(12 個,全 16:9)   : +0x44 = 1      +0x80 = 0x1000A/9/7
# +0x44 == 0 時 FUN_c0435af8 直接 return 0 —— 那是**壓縮位元流的解碼緩衝**。
# p43 宣告「不需要解碼緩衝」,壓縮禎沒有地方解碼 → 黑屏。
#
# 名稱表的「三組 × 四筆」= 位元深度(8/10/12-bit)× 解析度(UHD/FHD/*CROP)。
# 十二格全滿,沒有備用的,所以沒有現成的 3:2 影片回放 profile 可以選。
#
# 依設計的延伸點:OG3K 是 12-bit,落到 group 2 的 FHD = **p73**,而 p73 的
# 感測器視窗原廠就是 3032x1708(寬度已經對了)。畫布是每次載入複製到 RAM 的
# 一份,在 0xC043A19C(c0439d18 之後、c0434ec0 之前)改那份複本、值全部從 p43
# 抄、+0x44/+0x80 不動,模擬總量 9.8 MB。守衛用 r5==73 且 r4+8 的來源寬度是
# 3008/3032,不需要旗標。尚未上機驗證。

PAYLOADS = ((("rowpatch_og3k", "rowpatch_og3k.S", ROW_CODE),) if WITH_ROWPATCH else ()) + (
            ("fmttable",      "fmttable.S",      CODE),
            ("og3kfps",       "og3kfps.S",       FPS_CODE),
            ("og3kname",      "og3kname.S",      NAME_CODE),
            ("og3ksel",       "og3ksel.S",       SEL_CODE),
            ) + ((("og3kaspect",  "og3kaspect.S",  ASP_CODE),
                  ("og3kaspect2", "og3kaspect2.S", AS2_CODE)) if WITH_ASPECT else ()) \
              + ((("og3kout",     "og3kout.S",     OUT_CODE),) if WITH_OUT else ()) \
              + ((("og3krange",   "og3krange.S",   RNG_CODE),) if WITH_RANGE else ()) \
              + ((("og3kpb",       "og3kpb.S",      PB_CODE),) if WITH_PLAYBACK else ()) \
              + ((("og3kpbrow",   "og3kpbrow.S",   ROW_CODE),) if WITH_PBROW else ()) \
              + ((("og3kcanvas",  "og3kcanvas.S",  ROW_CODE),) if WITH_CANVAS else ()) \
              + ((("og3kpbsel",   "og3kpbsel.S",   PBSEL_CODE),) if WITH_PBSEL else ()) \
              + ((("og3kgs",      "og3kgs.S",      GS_CODE),) if WITH_GS else ()) \
              + ((("og3kfmt",     "og3kfmt.S",     FMT_CODE),
                  ("og3krestore", "og3krestore.S", RESTORE_CODE)) if WITH_FMTGUARD else ()) \
              + ((("hswrate",     "hswrate.S",     RATE_CODE),) if WITH_RATE240 else ()) \
              + ((("poolinit",    "poolinit.S",    POOLINIT_CODE),) if POOLDEPTH is not None else ())

# 每個 hook「擁有」的記憶體區域:它的 payload,加上它在執行期會讀的資料。
# 載入器在改動其中任何一個字之前,必須先解除那個 hook。
#
# 2026-09-12:我在 picker hook 武裝的情況下改寫格式表(0xC0731000),
# picker 立刻開始發放新的 profile,相機在重組中途凍結。
# 「payload 不能邊跑邊改」的規則,對 hook 讀的資料同樣成立。
# 格式表佔 len(FMT) x 48 再加 48 bytes 的終止列。原本寫死 0x1E0(八列),
# HSW 有十列就不夠了 —— 少算會讓載入器在 picker 武裝著的時候改到表尾。
_TABLE_SPAN = (len(FMT_OG3K if TARGET.startswith("og3k") else
               FMT_OG2K if TARGET == "og2k" else
               FMT_OG6K if TARGET == "og6k" else FMT_HSW) + 1) * 48
_ENGFPS_OWNED = [(FPSLATCH, FPSLATCH + 4)] if WITH_ENGFPS else []
OWNED = {0xC043CCF8: [(CODE, FPS_CODE), (TABLE, TABLE + _TABLE_SPAN),
                      (BITLATCH, BITLATCH + 4)] + _ENGFPS_OWNED,
         **{site: [(FPS_CODE, NAME), (FLAG, FLAG + 4),
                   (DONOR_TIMING_ADDR + 4, DONOR_TIMING_ADDR + 12)]
            for site, _, _ in FPS_HOOKS},
         # 0xC0731940:og3ksel 加了格式條件與 OGSAVE 之後是 304 bytes,
         # 止於 0xC0731930。上界跟著放大,不然載入器會以為尾巴不屬於它。
         0xC005C020: [(0xC0731800, 0xC0731940), (0xC0732100, 0xC0732200),
                      (FLAG, FLAG + 4), (FMTLATCH, FMTLATCH + 4),
                      (DONOR_TIMING_ADDR + 4, DONOR_TIMING_ADDR + 12)]
                     + ([V3TAP_SPAN] if WITH_V3TAP else [])
                     + ([HSW_WIN_SPAN] if WITH_HSW_WIN else []),
         # og3kfmt 與 og3ksel 走同一段交易,所以擁有同一批資料。
         # 兩邊都列出來是對的:載入器在動其中任何一個字之前,兩個 hook 都要先拆。
         **({FMT_HOOK: [(FMT_CODE, FMT_CODE + 0x100), (0xC0732100, 0xC0732200),
                        (FLAG, FLAG + 4), (FMTLATCH, FMTLATCH + 4),
                        (DONOR_TIMING_ADDR + 4, DONOR_TIMING_ADDR + 12)]
                       + ([V3TAP_SPAN] if WITH_V3TAP else [])
                       + ([HSW_WIN_SPAN] if WITH_HSW_WIN else [])}
            if WITH_FMTGUARD else {}),
         0xC0437E98: [(0xC0731D00, 0xC0731E90), (0xC0732000, 0xC0732080)],  # og3kout + 模板
         0xC043A19C: [(0xC0732400, 0xC0732A20), (0xC0731C0C, 0xC0731C10),
                      (BITLATCH, BITLATCH + 4)]
                     + _ENGFPS_OWNED,             # rowpatch / pbrow / canvas
         0xC0306EA0: [(0xC0731B00, 0xC0731B28)],
         0xC0306EEC: [(0xC0731B40, 0xC0731B68)],
         0xC0437B48: [(0xC0731A00, 0xC0731B00), (0xC0731C0C, 0xC0731C10)],
         0xC043D258: [(0xC0731F00, 0xC0731F60)],
         0xC0437AF8: [(0xC0731F80, 0xC0731FE0), (0xC0731C0C, 0xC0731C20)],
         0xC043BE68: [(PBSEL_CODE, PBSEL_CODE + 0x100), (PBSEL_LOG, PBSEL_ENT + 4)],
         0xC03A6DD8: [(GS_CODE, GS_CODE + 0x80), (GS_LOG, GS_LOG + 4)],
         RATE_HOOK:  [(RATE_CODE, RATE_CODE + 0x80)]}                                        # og3kname

HOOKS = (((ROW_HOOK, ROW_CODE, ROW_STOCK, "bl", "畫布幾何"),) if WITH_ROWPATCH else ()) \
       + (((ROW_HOOK, ROW_CODE, ROW_STOCK, "bl", "回放畫布 3:2 case"),) if WITH_PBROW else ()) \
       + (((ROW_HOOK, ROW_CODE, ROW_STOCK, "bl", "畫布:錄影對齊 + 回放柵格"),) if WITH_CANVAS else ()) + (
         (NAM_HOOK, NAME_CODE, NAM_STOCK, "b", "解析度名發射器"),
         (SEL_HOOK, SEL_CODE, SEL_STOCK, "b",  "解析度 setter"),
         ) + (((FMT_HOOK, FMT_CODE, FMT_STOCK, "b",
                "錄影格式 setter(MOV 時撤旗標)"),) if WITH_FMTGUARD else ()) + (((ASP_HOOK, ASP_CODE, ASP_STOCK, "b", "長寬比 C0306EA0"),
               (AS2_HOOK, AS2_CODE, AS2_STOCK, "b", "長寬比 C0306EEC")) if WITH_ASPECT else ()) \
           + (((OUT_HOOK, OUT_CODE, OUT_STOCK, "b", "主輸出描述子"),) if WITH_OUT else ()) \
           + (((RNG_HOOK, RNG_CODE, RNG_STOCK, "b", "表範圍檢查"),) if WITH_RANGE else ()) \
           + (((PB_HOOK, PB_CODE, PB_STOCK, "b", "回放 profile 替換"),) if WITH_PLAYBACK else ()) \
           + (((PBSEL_HOOK, PBSEL_CODE, PBSEL_STOCK, "b", "回放管線選擇"),) if WITH_PBSEL else ()) \
           + (((GS_HOOK, GS_CODE, GS_STOCK, "b", "增益分派:當成 raw movie"),) if WITH_GS else ()) \
           + tuple((site, FPS_CODE, stock, "bl", f"快門角度 nominal fps：{role}")
                   for site, stock, role in FPS_HOOKS) \
           + (((RATE_HOOK, RATE_CODE, RATE_STOCK, "b",
                "格率 enum 11 -> 240000/1001"),) if WITH_RATE240 else ()) \
           + ((PIK_HOOK, CODE, PIK_STOCK, "b", "picker(最後 arm)"),)


# A001_002 解檔驗證過的錄影幾何。動它之前先讀 rowpatch_og3k.S 的檔頭。
VERIFIED = {0x000: 3032, 0x004: 2012, 0x024: 3008, 0x02C: 2000,
            0x0D8: 3032, 0x0E0: 2012, 0x0DC: 3032, 0x0E4: 2012,
            0x0F4: 3032, 0x0F8: 2012,
            # 2026-09-12 升級:預覽的 producer 與可見窗口。
            # A001_008/009/010 解檔完整(含最底部 1900..2010 行),
            # 截圖 SS__0413 對比待機 SS__0408:水平 1.000x、垂直 1.000x、
            # 異向比 1.0000、相關 0.9787 —— 錄影期 live view 與待機完全一致。
            0x00C: 3032, 0x010: 2012,    # producer 實際產出
            0x020: 3000, 0x028: 2000}    # 可見窗口 = DNG 裁切,所見即所錄

# 試驗中的預覽欄位。RWZM unity 之後 producer 會產出 3032x2012,預覽的描述子
# 必須跟著變成全尺寸,否則消費端會從 3032 寬的緩衝按 1:1 取 1920x1080 ——
# 就是「從中心放大約 1.58 倍、上下兩條閃爍」。
# 每次改這裡都必須錄一段並解 DNG,不能只看 live view。
# 2026-09-12 截圖量測(SS__0411,錄影中):畫面分三帶,中間是影像、上下是未初始化
# 記憶體。影像帶佔非 HUD 區的 0.5630,對上 1090/2012 = 0.5417。
# → 錄影時 producer 只寫 1090 行,消費端顯示 2012 行。
#
# 所以兩個欄位的角色是:
#     +0x0C/+0x10   producer 實際產出   ← 現在是原廠 1936x1090
#     +0xD8/+0xE0   消費端讀取(覆寫)   ← rowpatch 已設 3032x2012
# 兩邊不一致,所以中間 1090 行有影像、上下是空的,而且每列 1936 筆資料被當成
# 3032 讀,水平也被拉開。
#
# 下一個試驗:只改 producer 那一對,讓兩邊一致。可見尺寸先不動
# (上次同時改可見 + 把 +0xD8/+0xE0 關成 0,結果毀掉素材 —— 一次只動一個變數)。
# 目前沒有試驗中的欄位。要試新的預覽欄位就加進這裡:允許用 og3k_load.py
# 走 USB 測,但 AutoRun 產生器會拒絕,直到錄一段解 DNG 確認無損才能升級。
TRIAL = {}


def _source(name):
    """A payload's source as the static checks read it: the layout coordinates
    of og_pic.inc (OGA/OGP, Loader v3) spelled as the cave addresses they are
    on an AutoRun card, so every check sees the same numbers as before."""
    return re.sub(r"\bOG[AP]\((0x[0-9A-Fa-f]+)\)", r"\1", (HERE / name).read_text())


def branch(kind, code, site):
    op = 0xEB000000 if kind == "bl" else 0xEA000000
    return op | (((code - site - 8) >> 2) & 0xFFFFFF)


class Plan:
    def __init__(self, image=None):
        self.img = image if image is not None else FIRMWARE.read_bytes()
        self.sha = hashlib.sha256(self.img).hexdigest()
        self.order = [self.word(TT + i * 0x20) for i in range(70)]
        self.idx = {m: i for i, m in enumerate(self.order)}
        # 角度 wrapper 的白名單 tuple 要讀韌體的時序表,所以在這裡才補齊。
        # 順序就是 FMT 的順序,排除走別的感測器模式的那些(OG3K100)。
        self.defines = list(DEFINES)
        for i, key in enumerate(k for k, *_ in FMT if k not in T["angle_exclude"]):
            hm, tl, vm, x = self.fmt_timing(key)
            self.defines += [f"TARGET_T{i}_W0={hm | (tl << 16):#010x}",
                             f"TARGET_T{i}_W1={vm | (x << 16):#010x}",
                             f"TARGET_T{i}_FPS={NOMINAL_FPS[key]}"]
        # OG_V3: each payload also gets its own place in the layout (og_pic.inc).
        self.pdefs = {n: self.defines + ([f"OG_ORG={ogv(base):#x}"] if V3 else [])
                         + (["OG_CHAIN=1", f"OG_NEXT={ogv(CHAIN_NEXT0 + 4 * CHAIN_SLOT[n]):#x}"]
                            if CHAIN and n in CHAIN_SLOT else [])
                      for n, f, base in PAYLOADS}
        self.blobs = {n: assemble(HERE / f, self.pdefs[n]) for n, f, _ in PAYLOADS}
        # The word-count tripwire still holds under OG_V3: each payload may grow
        # only by its PC-relative loads, one `add rd, pc, rd` each (og_pic.inc).
        self.v3_growth = 0
        if V3:
            legacy = [d for d in self.defines if not d.startswith(("OG_V3=", "OGV="))]
            for n, f, _ in PAYLOADS:
                grow = len(self.blobs[n]) - len(assemble(HERE / f, legacy))
                words = [w for (w,) in struct.iter_unpack("<I", self.blobs[n])]
                adds = sum(1 for w in words if w & 0xFFFF0FF0 == 0xE08F0000
                           and (w >> 12) & 15 == w & 15)
                # OG_CHAIN: each way down is `movw, movt, add pc, ldr ip, [ip], bx ip`
                # (the add is counted above); the aspect payloads also split their
                # one exit into two (+4 words: mov, movw, movt, bx).
                passes = sum(1 for a, b in zip(words, words[1:])
                             if a == 0xE59CC000 and b == 0xE12FFF1C)
                calls = sum(1 for a, b in zip(words, words[1:])      # og3kfps: ldr ip, [ip]; blx ip
                            if a == 0xE59CC000 and b == 0xE12FFF3C)
                extra = 4 * passes + calls + (CHAIN_EXTRA.get(n, 0) if passes else 0)
                if grow != 4 * (adds + extra):
                    raise SystemExit(f"OG_V3 {n}: grew {grow} bytes, {adds} PC-relative "
                                     f"loads, {passes} ways down, {calls} calls down")
                self.v3_growth += adds + extra

    def fmt_timing(self, key):
        """這個格率最後真的會被寫進 donor timing record 的四個值。"""
        for k, donor, src, _slot in FMT:
            if k != key:
                continue
            if T["timing"] is not None:
                return T["timing"][key]
            hm, tl, vm, x = self.timing(src)
            if key == "OG3K100":
                hm, tl, vm = 330, 270, 2182
            return hm, tl, vm, x
        raise KeyError(key)

    def word(self, a):
        return struct.unpack_from("<I", self.img, a - B)[0]

    def timing(self, m):
        return struct.unpack_from("<HHHH", self.img, TT - B + self.idx[m] * 0x20 + 4)

    def check(self):
        """套用前的靜態檢查:每個 hook 點在參考映像裡必須是原廠指令。"""
        bad = []
        if WITH_V3TAP:
            bad += self.v3tap_errors()
        if WITH_HSW_WIN:
            bad += self.sreg_errors(HSW_WIN_MODE, HSW_WIN_REGS)
        # 2026-09-12 事故:把 canvas 的 +0xD8/+0xE0(producer-side 寬高對)改成 0
        # 之後,producer 改讀 +0x0C/+0x10,錄出來的 DNG 只有左上一塊有畫面,
        # 後來連 strip 都縮成 3032x1341。毀掉數十段素材。
        #
        # VERIFIED = A001_002(RWZM unity 之後)實際解檔驗證過的組合。
        # TRIAL    = 還在試的預覽欄位。允許用 USB 載入測試,但 build_og3k_v2
        #            會拒絕把它打進 AutoRun,直到解過 DNG 為止。
        src = _source("rowpatch_og3k.S")
        puts = dict((int(m[1], 16), int(m[2]))
                    for m in re.finditer(r"PUT\s+0x([0-9A-Fa-f]+),\s*(\d+)", src))
        for off, want in VERIFIED.items():
            if puts.get(off) != want:
                bad.append(f"rowpatch PUT +0x{off:03X} = {puts.get(off)},"
                           f"必須是 {want}(錄影路徑,見檔頭的事故說明)")
        if WITH_CANVAS:
            src = _source("og3kcanvas.S")
            # 只看這個目標真的會組進去的部分:把未定義的 #ifdef 區塊拿掉。
            # 前處理器是 clang 跑的,這裡只是讓靜態檢查看見同一份程式。
            defined = {d.split("=")[0] for d in self.defines}
            out, skip = [], 0
            for line in src.splitlines(True):
                t = line.strip()
                if t.startswith("#ifdef") or t.startswith("#ifndef"):
                    name = t.split()[1]
                    on = (name in defined) if t.startswith("#ifdef") else \
                         (name not in defined)
                    skip += 0 if on else 1
                    if skip:
                        continue
                    out.append(line)
                    continue
                if t.startswith("#endif"):
                    if skip:
                        skip -= 1
                        continue
                if not skip:
                    out.append(line)
            src = "".join(out)
            # PUT 的值可能是 .equ 定義的符號,而 .equ 本身又可能指向
            # 前處理器的 TARGET_* 巨集。先把 DEFINES 展開,再解 .equ。
            equ = {d.split("=")[0]: int(d.split("=")[1], 0)
                   for d in self.defines if "=" in d}
            for m in re.finditer(r"^\.equ\s+(\w+),\s*(\w+)", src, re.M):
                v = m[2]
                if v in equ:
                    equ[m[1]] = equ[v]
                else:
                    try:
                        equ[m[1]] = int(v, 0)
                    except ValueError:
                        pass
            got = {}
            for m in re.finditer(r"PUTW?\s+0x([0-9A-Fa-f]+),\s*(\w+)", src):
                v = m[2]
                got[int(m[1], 16)] = (int(v, 0) if v.isdigit() or
                                      v.lower().startswith("0x") else equ.get(v))
            want = dict(CANVAS_REC); want.update(CANVAS_PB)
            if got != want:
                for k in sorted(set(got) | set(want)):
                    if got.get(k) != want.get(k):
                        bad.append(f"og3kcanvas PUT +0x{k:02X} = {got.get(k)},"
                                   f"計畫要求 {want.get(k)}")
            # 記錄尺寸是解檔驗證過的,動它必須重新解檔
            if (got.get(0x00), got.get(0x04)) != T["rec"]:
                bad.append(f"og3kcanvas 的記錄尺寸不是 {T['rec']} —— "
                           "OG3K 的 3024x2010 是 A001_036 解檔驗證過的值")

            # 平面格式碼:PFMT 三條路必須剛好覆蓋 CANVAS_PLANE。
            # 12-bit 的 +0x080 走 PUT(它同時是 CANVAS_REC 驗的那一筆),
            # 所以這裡把它補回去再比。
            cur, plane = 0, {0: {}, 3: {}, 4: {}}
            for m in re.finditer(r"^(?:(bd8|bd10):|\s*PFMT\s+0x([0-9A-Fa-f]+),"
                                 r"\s*(\d+))\s*$", src, re.M):
                if m[1]:
                    cur = 4 if m[1] == "bd8" else 3
                else:
                    plane[cur][int(m[2], 16)] = int(m[3])
            plane[0][0x80] = got.get(0x80)
            want_plane = {k: {0x80: v[0], 0x84: v[1]}
                          for k, v in CANVAS_PLANE.items()}
            if plane != want_plane:
                bad.append(f"og3kcanvas 平面格式碼 {plane} != {want_plane}")

            # 引擎格率:錄影路徑必須把 FPSLATCH 寫進畫布 +0x030,而且要有
            # 「鎖存為 0 就不寫」的守衛(否則沒命中過時會寫出 0.0 fps,
            # FUN_c04357e0 的 plane count 只在 -1.0 時歸零,但 0.0 對
            # FUN_c01caba0 的分支一樣是錯的)。
            has = re.search(r"strne\s+r2,\s*\[r1,\s*#0x30\]", src) is not None
            if has != WITH_ENGFPS:
                bad.append(f"og3kcanvas 寫畫布 +0x030 = {has},"
                           f"但 WITH_ENGFPS = {WITH_ENGFPS}")
            if WITH_ENGFPS and "cmp     r2, #0" not in src:
                bad.append("og3kcanvas 少了「鎖存為 0 就不寫 +0x030」的守衛")

        if WITH_PBROW:
            src = _source("og3kpbrow.S")
            got = dict((int(m[1], 16), int(m[2]))
                       for m in re.finditer(r"PUT\s+0x([0-9A-Fa-f]+),\s*(\d+)", src))
            if set(got) != set(PBROW_FROM_P43):
                bad.append(f"og3kpbrow 的 PUT 集合 {sorted(got)} 與 "
                           f"PBROW_FROM_P43 {sorted(PBROW_FROM_P43)} 不符")
            _, rows = self.profile_col(0x1C)
            for dst, srcoff in PBROW_FROM_P43.items():
                base, _ = self.profile_col(srcoff)
                want = self.word(base + rows[43] * 4)
                if got.get(dst) != want:
                    bad.append(f"og3kpbrow PUT +0x{dst:02X} = {got.get(dst)},"
                               f"但 p43 的 +0x{srcoff:02X} 是 {want} —— 值必須抄 p43,"
                               f"不能自己算")

        # donor 方案的前提:它原廠的 +0x030 必須是正值。FUN_c04357e0 的
        # plane count 是「+0xA4 == 1 → 2;+0xA4 in {9,10} 或 +0x030 == -1.0
        # → 0;否則 3」,所以 +0x030 一旦是 -1.0(p43 就是)張數就變 0,
        # 而把畫格率寫進去才變 3 —— 「拍一張 S 尺寸照片就凍結」就是這條。
        # 我們一個位元都不寫 +0x030,所以它原廠就必須是正值。
        import struct as _s
        _v = _s.unpack('<f', _s.pack('<I', self.word(BUFFER_COUNT_ADDR)))[0]
        if not _v > 0:
            bad.append(f"p{OG_PROFILE} 的 PARAM+0x030 是 {_v},必須是正值"
                       "(否則 plane count 會是 0)")
        if True:
            # picker 同意閘門(MATCH)。三個顯示 payload 與 fmttable 必須同進退,
            # 而且標籤必須真的是本目標的四個位元組 —— 不是猜的。
            # **檢查組出來的位元組,不是原始碼文字** —— PICKOK 不論 #ifdef
            # 開關都在檔案裡(2026-09-27 第一版規則就是這樣寫錯的)。
            # 把 MATCH 的 define 拿掉重組一次:有閘門就一定不同。
            for name, src in (("og3kaspect", "og3kaspect.S"),
                              ("og3kaspect2", "og3kaspect2.S"),
                              ("og3kout", "og3kout.S"),
                              ("fmttable", "fmttable.S")):
                if name not in self.blobs:
                    continue
                plain = [d for d in self.pdefs[name]
                         if not d.startswith(("TARGET_MATCH", "TARGET_LABEL"))]
                gated = self.blobs[name] != assemble(HERE / src, plain)
                if gated != WITH_MATCH:
                    bad.append(f"{src} 的 MATCH 閘門 = {gated},"
                               f"但 WITH_MATCH = {WITH_MATCH}")
            if WITH_MATCH:
                lbl = int.from_bytes(T["label"].encode(), "little")
                if f"TARGET_LABEL={lbl:#x}" not in self.defines:
                    bad.append(f"TARGET_LABEL 不是 {T['label']!r} 的四個位元組")
                if MATCH == FPSLATCH or MATCH in (FLAG, PBFLAG, BITLATCH,
                                                  FMTLATCH, PBENT, LOG):
                    bad.append(f"MATCH 0x{MATCH:08X} 與別的 cave 字重疊")
                # fmttable 只能在**表尾**清它,不能在「不是我們的表」那條早退清掉
                fsrc2 = _source("fmttable.S")
                if fsrc2.index("tailend:") < fsrc2.index("search:"):
                    bad.append("fmttable 的 tailend 排在 search 之前 —— "
                               "非本表的查詢會被誤判成壞鍵")

        if WITH_ENGFPS:
            fsrc = _source("fmttable.S")
            if "FPSLATCH" not in fsrc:
                bad.append("WITH_ENGFPS 開著,但 fmttable.S 沒有鎖存引擎格率")
            for key, donor, src_, slot in FMT:
                _f = _s.unpack('<f', _s.pack('<I', self.engine_fps(slot)))[0]
                if not 0 < _f <= 240:
                    bad.append(f"{key} 的引擎格率 {_f} 不在 (0, 240] —— "
                               "非正值會讓 FUN_c04357e0 的 plane count 歸零")

        # donor 白名單。p83 被照片拍攝表引用,所以畫布 hook 必須有 FLAG 守衛
        # (og3kcanvas.S 檔頭寫了這個已知缺口);p13/p221 沒有被任何表引用,
        # 但它們原廠有整排 0x0 的幾何欄位,補不齊就會當機 —— 2026-09-15 的
        # p221 回放當機就是 active 沒補。要換 donor 必須先全 65 欄比對。
        # 2026-09-17 加入 p14(OG6K)。全 65 欄對 p13 比對過,只差六欄:
        #     +0x00C/+0x010  預覽柵格   p13 1920x1280   p14 1236x824
        #     +0x020/+0x028  預覽可見   p13 1904x1270   p14 1220x814
        #     +0x0D8/+0x0E0  生產者     p13 1920x1280   p14 1236x824
        # 那六欄正好被 write_preview / write_producer 全部覆寫。記錄矩陣、
        # active、標稱 fps、平面格式碼,以及害 p221 當機的 +0x088/+0x0B0/
        # +0x0C0,p13 與 p14 完全相同 —— p13 已實機驗證,p14 直接繼承。
        if OG_PROFILE not in (83, 13, 14):
            bad.append(f"donor p{OG_PROFILE} 不在已審查過的白名單內")

        # 快門角度修正只允許介入四條已確認的本地 callsite。共享
        # mode98 metadata 與 p83 照片欄位都保持原廠值；runtime 只接受
        # 完整、精確的 mode98 timing tuple。
        fmt_keys = {key for key, *_ in FMT}
        if set(NOMINAL_FPS) != fmt_keys:
            bad.append("NOMINAL_FPS 與 FMT 的 key 集合不一致")
        if {key for key, donor, *_ in FMT if donor == T["mode"]} != {
                key for key, fps in NOMINAL_FPS.items() if fps in DONOR_FPS_VALUES}:
            bad.append(f"mode{T['mode']} 格式與可接受的 nominal-fps 集合不一致")
        # donor 模式的 metadata +0x40 是共用的標稱 fps。角度修正的整個前提
        # 就是「它不等於我們實際在錄的格率」,所以只確認它仍是原廠值,
        # 一個位元都不寫。
        if self.word(DONOR_NOMINAL_FPS_ADDR) != T["stock_nominal_fps"]:
            bad.append(f"mode{T['mode']} metadata +0x40 已不是原廠 "
                       f"{T['stock_nominal_fps']}，角度修正前提失效")
        if TT + self.idx[T["mode"]] * 0x20 != DONOR_TIMING_ADDR:
            bad.append(f"mode{T['mode']} timing record 位址與韌體索引不一致")
        stock_timing = (self.word(DONOR_TIMING_ADDR + 4),
                        self.word(DONOR_TIMING_ADDR + 8))
        if stock_timing != DONOR_TIMING_STOCK:
            bad.append(f"mode{T['mode']} stock timing words {stock_timing} != "
                       f"{DONOR_TIMING_STOCK}")
        for site, stock_word, role in FPS_HOOKS:
            if self.word(site) != stock_word:
                bad.append(f"快門角度 {role} 的 stock word 不符: "
                           f"0x{self.word(site):08X} != 0x{stock_word:08X}")
            if branch("bl", FPS_ORIGINAL, site) != stock_word:
                bad.append(f"快門角度 {role} 的 stock BL 無法解回 FUN_c032c750")
        _caves = [(FPS_CODE, len(self.blobs["og3kfps"]), "FPS code")]
        if WITH_RATE240:
            _caves.append((RATE_CODE, len(self.blobs["hswrate"]), "rate code"))
        for start, size, label in _caves:
            region = self.img[start - B:start - B + size]
            if len(region) != size or any(region):
                bad.append(f"{label} cave 在 0x{start:08X} 不是原廠全零")

        timing_fps = {}
        for key, _, _src_mode, _ in FMT:
            hm, tl, vm, x = self.fmt_timing(key)
            actual = 72_000_000 / (hm * (vm - 1) + tl)
            # OG_HSW_TOP=240 是**刻意**讓容器與感測器不同的高速模式,
            # 那一格不適用「實際 = 宣告」這條護欄。
            _intentional = (TARGET == "hsw" and bool(_HSW_TOP)
                            and key == "HSW" + _HSW_TOP_SLOT)
            if not _intentional and round(actual) != NOMINAL_FPS.get(key):
                bad.append(f"{key} 實際 {actual:.6f}fps 與 nominal class "
                           f"{NOMINAL_FPS.get(key)} 不一致")
            # 有效讀出行必須放得進 vmax,否則感測器會吃掉畫面
            if vm - T["rec"][1] < 1:
                bad.append(f"{key}: vmax {vm} 放不下 {T['rec'][1]} 行")
            # 這個「一組時序只能對應一個 nominal fps」的護欄是為了角度 wrapper
            # 的白名單。不武裝那四顆 BL 的目標(HSW)沒有白名單,而且
            # OG_HSW_TOP=240 會**刻意**讓兩個鍵共用同一組時序。
            if FPS_HOOKS and key not in T["angle_exclude"]:
                pair = (hm | (tl << 16), vm | (x << 16))
                if pair in timing_fps and timing_fps[pair] != NOMINAL_FPS[key]:
                    bad.append(f"mode{T['mode']} timing tuple {pair} 對應兩個 nominal fps")
                timing_fps[pair] = NOMINAL_FPS[key]

        # og3kfps 的原始碼驗證只在**這個目標真的武裝那四顆 BL** 時才有意義。
        # 不改 donor 時序的目標(HSW)不武裝它,而且十個格率各自有自己的時序
        # tuple,數量超過 .S 裡的 MATCH 槽 —— 那不是缺陷,是這支 payload
        # 根本不參與。與 verify_og3k_angle_fps.py 的拒絕執行同一個理由。
        if FPS_HOOKS:
            fps_src = _source("og3kfps.S")
            fps_code = re.sub(r"/\*.*?\*/", "", fps_src, flags=re.S)
            fps_code = re.sub(r"@.*$", "", fps_code, flags=re.M)
            fps_code = _active(fps_code, self.defines)
            sym = _symbols(fps_code, self.defines)
            fps_equ = {k: sym.get(k) for k in ("FLAG", "DONOR_TIMING", "ORIGINAL")}
            expected_equ = {"FLAG": FLAG, "DONOR_TIMING": DONOR_TIMING_ADDR,
                            "ORIGINAL": FPS_ORIGINAL}
            if fps_equ != expected_equ:
                bad.append(f"og3kfps constants {fps_equ} != {expected_equ}")
            asm_pairs = {}
            for w0, w1, fps in re.findall(
                    r"^\s+MATCH\s+(\w+),\s*(\w+),\s*(\w+)", fps_code, re.M):
                if w0 not in sym or w1 not in sym or fps not in sym:
                    bad.append(f"og3kfps MATCH 參照不到常數 {w0}/{w1}/{fps}")
                    continue
                asm_pairs[(sym[w0], sym[w1])] = sym[fps]
            if asm_pairs != timing_fps:
                bad.append(f"og3kfps timing map {asm_pairs} != {timing_fps}")
            if not re.search(rf"cmp\s+r4,\s*#(TARGET_MODE|{T['mode']})\b", fps_code):
                bad.append(f"og3kfps 沒有精確守衛 mode {T['mode']}")
            if len(re.findall(r"\bblx\s+ip\b", fps_code)) != 1:
                bad.append("og3kfps 必須精確呼叫一次原 getter")
            if re.search(r"\b(?:str|stm)\w*\b", fps_code):
                bad.append("og3kfps 必須是 read-only")
            if not re.search(r"push\s+\{r4,\s*r5,\s*r6,\s*lr\}", fps_code) or not \
                    re.search(r"pop\s+\{r4,\s*r5,\s*r6,\s*pc\}", fps_code):
                bad.append("og3kfps 沒有保存/恢復 callee-saved registers 或 LR")
            if "dmb     ish" not in fps_src:
                bad.append("og3kfps 缺少 timing acquire barrier")

            if WITH_RATE240:
                # 上限、有理數表的界線、六個資源描述子,全部必須是原廠值。
                if self.word(RATE_CAP) != RATE_CAP_STOCK:
                    bad.append(f"格率清單上限 0x{RATE_CAP:08X} = "
                               f"0x{self.word(RATE_CAP):08X},預期原廠 BE float 8.0")
                for res, desc, size, name in RATE_CSV:
                    key, nm, off, sz = struct.unpack_from(">4I", self.img, desc - B)
                    if sz != size or B + 0xD22400 + off != res:
                        bad.append(f"{name} 描述子 0x{desc:08X} 不符:"
                                   f"off=0x{off:X} size={sz},預期 0x{res-0xC0D22400:X}/{size}")
                    fn = self.img[0xD22414 + nm:].split(b"\0", 1)[0]
                    if fn != f"../MenuB12/data/ListB12/{name}.cvm".encode():
                        bad.append(f"{name} 描述子指向 {fn!r}")
                # picker 鍵發射器**不能**被改:enum 11 -> "240" 是原廠就有的,
                # 整個第十列的鍵 "HSW240" 完全靠它。
                if self.word(0xC043CB04) != 0xE353000C:
                    bad.append("格率字串發射器的界線不是原廠 cmp r3,#12")
                tblptr = 0xC043CB18
                if self.img[tblptr - B + 11] != 0x09:
                    bad.append("格率字串發射器跳表的 enum 11 不是原廠 0x09")
                ptr = 0xC0BE4804
                if self.img[ptr - B: ptr - B + 4] != b"240\x00":
                    bad.append(f"0x{ptr:08X} 不是原廠字串 '240'")
                # enum<->列 配對表沒有預留空位,這是已知未解項(notes §10)。
                pairs = struct.unpack_from("<18I", self.img, 0xC2E44EE4 - B)
                if pairs != (1,0, 2,1, 3,2, 4,3, 6,4, 7,5, 8,6, 9,7, 10,8):
                    bad.append("格率 enum<->列 配對表 0xC2E44EE4 已不是原廠九筆")

        fmt_src = _source("fmttable.S")
        # 三張 picker table 都是 CinemaDNG,差的是位元深度。必須三張都接,
        # 而且只接這三張 —— 照片那幾張表不能拿到 p83/mode98。
        fmt_equ = {name: int(value, 0) for name, value in re.findall(
            r"^\.equ\s+(TAB[123]|BITLATCH|BD8|BD10|BD12),\s*(\S+)",
            fmt_src, flags=re.M)}
        want_fmt_equ = {"TAB1": 0xC0BE5810, "TAB2": 0xC0BE59B0,
                        "TAB3": 0xC0BE5B50, "BITLATCH": BITLATCH,
                        "BD12": 0, "BD10": 3, "BD8": 4}
        if fmt_equ != want_fmt_equ:
            bad.append(f"fmttable picker table 常數 {fmt_equ} != {want_fmt_equ}")
        if len(re.findall(r"cmp\s+r1,\s*ip", fmt_src)) != 3:
            bad.append("fmttable 必須精確比對三張 picker table")
        if not re.search(r"str\s+r5,\s*\[r4\]", fmt_src):
            bad.append("fmttable 沒有把位元深度鎖存給 og3kcanvas")
        if fmt_src.index("BITLATCH\n    str     r5") < fmt_src.index("hit:"):
            bad.append("fmttable 的位元深度鎖存必須只在命中 OG3K 時寫")
        # ★ 2026-09-15 回歸守衛:pass 會跳回原廠 lookup 的第二條指令,
        # 而 r1 就是它的 table 參數。v0.2.2a 借了 r1 當位元深度暫存器,
        # 於是每一次「進了我們的表但鍵不符」的查詢都讓原廠從位址 0 開始掃。
        # entry 到 pass 之間一個字都不准寫 r1。
        head = fmt_src[fmt_src.index("entry:"):fmt_src.index("hit:")]
        # cmp/tst/str 的第一個運算元是來源,不是目的地
        if re.search(r"^\s+(?!cmp|cmn|tst|teq|str|stm|push)\w+\s+r1\s*,",
                     head, re.M):
            bad.append("fmttable 在 pass 之前寫了 r1 —— 那是原廠 lookup 的 "
                       "table 參數,會讓它從位址 0 開始掃")
        for token in ("mrs     r2, cpsr", "msr     cpsr_c, r1", "dmb     ish"):
            if token not in fmt_src:
                bad.append(f"fmttable timing transaction 缺少 {token.strip()}")

        sel_src = _source("og3ksel.S")
        sel_equ = {k: v for k, v in _symbols(sel_src, self.defines).items()
                   if k in ("DONOR_TIMING", "DONOR_W0", "DONOR_W1")}
        want_sel_equ = {"DONOR_TIMING": DONOR_TIMING_ADDR,
                        "DONOR_W0": DONOR_TIMING_STOCK[0],
                        "DONOR_W1": DONOR_TIMING_STOCK[1]}
        if sel_equ != want_sel_equ:
            bad.append(f"og3ksel stock timing constants {sel_equ} != {want_sel_equ}")
        clear_at = sel_src.find("str     r3, [ip]\n    dmb     ish")
        restore_at = sel_src.find("LDA     ip, DONOR_TIMING")
        publish_at = sel_src.rfind("str     r3, [ip]")
        if not (0 <= clear_at < restore_at < publish_at):
            bad.append("og3ksel 沒有先撤 FLAG、還原 timing、最後發布 FLAG 的順序")

        self.trial = {}
        for off, v in puts.items():
            if off in VERIFIED:
                continue
            if off in TRIAL and v == TRIAL[off]:
                self.trial[off] = v
            else:
                bad.append(f"rowpatch 多了 PUT +0x{off:03X} = {v} —— 不在已驗證"
                           f"也不在試驗清單,canvas 只放錄影幾何")
        # 順序守衛:任何「值等於某個 payload 的起始位址」或「是跳到 payload 的
        # 分支」的寫入,都必須排在那個 payload 的最後一個字之後。
        # 否則載入中途就會有東西跳進尚未寫入的記憶體 —— 當場凍結。
        items = list(self.all())
        if len(items) != EXPECTED_PLAN_WORDS + self.v3_growth:
            bad.append(f"OpenGate plan 有 {len(items)} words，預期固定的 "
                       f"{EXPECTED_PLAN_WORDS} + {self.v3_growth}(OG_V3)")
        shared_writes = sorted({a for a, _, _ in items}
                               & {DONOR_NOMINAL_FPS_ADDR, BUFFER_COUNT_ADDR,
                                  DONOR_TIMING_ADDR + 4, DONOR_TIMING_ADDR + 8})
        if shared_writes:
            bad.append("角度修正寫到共享 firmware 欄位: "
                       + ", ".join(f"0x{a:08X}" for a in shared_writes))
        span = {}
        for name, _, base in PAYLOADS:
            span[base] = (base + len(self.blobs[name]), name)
        last = {}
        for i, (a, v, _) in enumerate(items):
            for base, (end, nm) in span.items():
                if base <= a < end:
                    last[base] = i
        for i, (a, v, note) in enumerate(items):
            for base, (end, nm) in span.items():
                arms = (v == base) or (
                    (v >> 24) in (0xEA, 0xEB)
                    and a + 8 + (((v & 0xFFFFFF) ^ 0x800000) - 0x800000) * 4 == base)
                if arms and i < last.get(base, -1):
                    bad.append(f"順序錯誤:0x{a:08X} 在 {nm} 的 payload 寫完前就"
                               f"指向它(第 {i} 筆 vs 第 {last[base]} 筆)")

        for site, code, stock, kind, name in HOOKS:
            got = self.word(site)
            if got != stock:
                bad.append(f"hook {name} 0x{site:08X} = 0x{got:08X},預期 0x{stock:08X}")
        for name, _, base in PAYLOADS:
            n = len(self.blobs[name])
            if base + n > {ROW_CODE: ROW_LOG, CODE: FPS_CODE, FPS_CODE: NAME,
                           NAME_CODE: 0xC0731B00,     # where og3kaspect sits on the AutoRun card
                           SEL_CODE: NAME_CODE, ASP_CODE: AS2_CODE,
                           AS2_CODE: 0xC0730300 if CHAIN else LOG, OUT_CODE: TPL0,
                           RNG_CODE: 0xC0732000,
                           PBSEL_CODE: PBSEL_LOG,
                           GS_CODE: 0xC0732980,
                           PB_CODE: 0xC0732000,
                           RATE_CODE: POOLINIT_CODE,
                           # 兩個新 payload 共用格式表之後的大空洞。
                           # og3kfmt 的上界就是 og3krestore 的起點,
                           # og3krestore 的上界是 SEL_CODE —— 誰長大都會被擋下。
                           FMT_CODE: RESTORE_CODE,
                           RESTORE_CODE: SEL_CODE,
                           POOLINIT_CODE: HITS}[base]:
                bad.append(f"payload {name} ({n}B @0x{base:08X}) 溢出它的區段")
        if (self.word(EMIT_W), self.word(EMIT_H)) != (1280, 720):
            bad.append("發射器比對的一對尺寸不是原廠 1280x720")
        return bad

    # ---- 各區段 ----------------------------------------------------------
    def emitter(self):
        # 2026-09-13 移除。原本這裡把 0xC0BCFE80/84(真實的 720p 格式比對對)
        # 改成我們的尺寸,又把 0xC0437C34/38 的 "HD" 字串指標改指向 "OG3K" ——
        # 挪用一個仍在服役的格式槽,動了四個原廠位置。
        # og3kname v2 自己呼叫原函式用的輸出函式,所以這些全部不需要了。
        return
        yield  # pragma: no cover
        # 舊註解保留:改成裁切尺寸 3008x2000,而不是柵格 3032x2012。
        # 回放把片子識別成格式時,比對的是 DNG 的裁切尺寸;識別失敗就回退到
        # "FHD",於是合成鍵 "FHD30" 去查 picker,拿到 FHD 的幾何(柵格 1936),
        # 而檔案是 3032 寬 —— 行距差 1644 bytes,就是回放的水平條紋雜訊。
        # 兩邊統一成 3008x2000 之後,回放合成的鍵會是 "OG3K30",正好命中格式表。
        yield EMIT_W, T["act"][0], "發射器比對:寬(= DNG 裁切)"
        yield EMIT_H, T["act"][1], "發射器比對:高"

    def name_string(self):
        kb = T["label"].encode() + b"\x00" * (8 - len(T["label"]))
        for i in range(2):
            yield NAME + i * 4, struct.unpack_from("<I", kb, i * 4)[0], "名稱字串"
        # 不再改 0xC0437C34/38 的字串指標 —— og3kname v2 自己輸出。

    def playback(self):
        """回放:hook FUN_c0437af8,把名稱表的表項換成我們自己的一筆。

        原廠的名稱表(0xC0BE4508 三組各 4 筆)**一個字都不動**。
        2026-09-12 的 v1 改了 FHDCROP 那一筆的 profile id,破壞了 373 的
        反向查詢(FUN_c043d840 以 profile id 為鍵搜表),畫面直接黑掉。
        """
        if not WITH_PLAYBACK:
            yield PB_HOOK, PB_STOCK, "回放 hook 還原原廠"
            if WITH_PBROW:
                # og3kname 寫、og3kpbrow 讀:載入時必須歸零,否則沿用上次的值。
                yield PBFLAG, 0, "PBFLAG 歸零(og3kpbrow 的片源守衛)"
            return
        yield PBFLAG, 0, "回放旗標歸零"
        for k, v in enumerate((6, 43, 222, NAME)):
            yield PBENT + k * 4, v, '回放表項 {6, 43, 222, "OG3K"}'

    def cleanup(self):
        # 拆掉的元件要主動還原,不然上一次載入留下的 hook 會繼續掛著。
        if not WITH_ROWPATCH and not WITH_PBROW and not WITH_CANVAS:
            yield ROW_HOOK, ROW_STOCK, "畫布 hook 還原原廠(三個 case 都已拆)"
        if not WITH_GS:
            yield GS_HOOK, GS_STOCK, "增益分派 hook 還原原廠"
        if not WITH_PBSEL:
            yield PBSEL_HOOK, PBSEL_STOCK, "回放管線選擇 hook 還原原廠"
        if not WITH_ASPECT:
            yield ASP_HOOK, ASP_STOCK, "長寬比 hook 還原原廠"
            yield AS2_HOOK, AS2_STOCK, "長寬比2 hook 還原原廠"
        if not WITH_OUT:
            yield OUT_HOOK, OUT_STOCK, "主輸出 hook 還原原廠"
        if not WITH_RANGE:
            yield RNG_HOOK, RNG_STOCK, "範圍檢查 hook 還原原廠"
        if not WITH_PREV:
            for a in PREV:
                yield a, PREV_OFF, "預覽可見高還原原廠"
        if not WITH_RWZM:
            for a in self.rwzm():
                yield a, RW_OFF, "RWZM 還原原廠"

    def misc(self):
        if UISHARE:          # the List max is +1 in the B2_5 copy (uishare add_option)
            return
        yield CTRL_CAP, 0x00000040, "控制器上限 BE float 2.0"

    def menu_csv(self):
        if UISHARE:          # the row is appended to a CSV copy (uishare add_option)
            return
        span = (len(NEW_CSV) + 3) // 4 * 4
        cur = bytearray(self.img[CSV - B: CSV - B + span])
        cur[:len(NEW_CSV)] = NEW_CSV
        for k in range(span // 4):
            yield CSV + k * 4, struct.unpack_from("<I", bytes(cur), k * 4)[0], "選單 CSV"

    def rate_menu(self):
        """選單第十列 239.76 fps:六個 B2_5_5 變體 + 描述子長度 + 控制器上限。

        每個變體都重排成「拿掉 Popup 欄、資料列用裸 \n」—— 這是解析度那塊
        已經實機驗證過的手法(FORMAT_REGISTRY_DESIGN §29):標頭名稱不能動
        (解析器按名稱對欄),但**整欄拿掉**是可以的。

        原廠 257 bytes 重排後只要 211,所以不必動資源的配置位置,只把描述子
        的長度欄改成新長度 —— 不改的話解析器會多讀 46 bytes 的舊內容殘留。
        """
        if not WITH_RATE_CSV:
            return
        for res, desc, size, name in RATE_CSV:
            body = self.img[res - B: res - B + size]
            assert body.startswith(b"\xef\xbb\xbf"), name
            lines = body[3:].replace(b"\r\n", b"\n").rstrip(b"\n").split(b"\n")
            head, rows = lines[0], lines[1:]
            assert head == b"NO,TEXT,Popup,IMAGE,Enabled,Enabled2", (name, head)
            assert len(rows) == 9, (name, len(rows))
            out = [b"\xef\xbb\xbfNO,TEXT,IMAGE,Enabled,Enabled2"]
            for r in rows:
                no, text, _popup, image, en, en2 = r.split(b",")
                if WITH_RATE_UNGATE:
                    en, en2 = b"1", b"2"       # 解除媒體閘門,純診斷用
                out.append(b",".join((no, text, image, en, en2)))
            # 第十列。標籤照原廠的寫法("119.88 fps"),IMAGE 補 blank ——
            # 空的 IMAGE 欄會把那一列切成文字算繪,解析度那塊試過,是退步。
            if WITH_RATE240:
                out.append(b"10,239.76 fps,blank,1,2")
            new = out[0] + b"\r\n" + b"\n".join(out[1:])
            if len(new) > size:
                raise SystemExit(f"{name}: 新 CSV {len(new)}B 放不進 {size}B")
            span = (len(new) + 3) // 4 * 4
            cur = bytearray(self.img[res - B: res - B + span])
            cur[:len(new)] = new
            for k in range(span // 4):
                yield res + k * 4, struct.unpack_from("<I", bytes(cur), k * 4)[0], \
                      f"格率選單 {name}"
            # 描述子的長度欄是**大端序**,所以寫進去的 LE 字要位元組反轉。
            yield desc + 12, int.from_bytes(len(new).to_bytes(4, "big"), "little"), \
                  f"格率選單 {name} 描述子長度 {size} -> {len(new)}"
        if WITH_RATE240:
            # 只有加了第十列才需要把游標上限放寬;純解除閘門不必動它。
            yield RATE_CAP, RATE_CAP_NEW, "格率清單控制器上限 BE float 8.0 -> 9.0"

    def engine_fps(self, slot):
        """原廠在同一個 picker slot 上宣告的格率 —— 畫布 +0x030 的 float bits。

        **不要自己算。** FHD100 那一格原廠宣告的是 50.0,不是 100;
        FHD23_98 宣告 24.0。值直接從映像裡那個 profile 的 +0x030 讀出來,
        所以「引擎看到的格率」逐位元組等於原廠在同一格上餵給它的東西。
        """
        prof = self.word(T3 + slot * 0x10 + 4)
        base, rows = self.profile_col(0x30)
        return self.word(base + rows[prof] * 4)

    def fmt_table(self):
        for n, (key, donor, src, slot) in enumerate(FMT):
            hm, tl, vm, x = self.fmt_timing(key)
            if hm * T["rec"][1] >= hm * (vm - 1) + tl:
                raise SystemExit(f"{key}: 2010 行放不進 vmax {vm}")
            base = TABLE + n * 48
            kb = key.encode() + b"\x00" * (16 - len(key))
            prof = OG_PROFILE if OG_PROFILE is not None else self.word(T3 + slot * 0x10 + 4)
            rec = ([5, prof, donor, base + 0x14,
                    TT + self.idx[donor] * 0x20]
                   + list(struct.unpack("<4I", kb))
                   + [hm | (tl << 16), vm | (x << 16),
                      self.engine_fps(slot) if WITH_ENGFPS
                      else NOMINAL_FPS[key]])
            for i, v in enumerate(rec):
                yield base + i * 4, v, f"格式表 {key}"
        for i in range(12):
            yield TABLE + len(FMT) * 48 + i * 4, 0, "格式表終止"

    def payloads(self):
        for name, _, base in PAYLOADS:
            blob = self.blobs[name]
            for i, v in enumerate(struct.unpack(f"<{len(blob)//4}I", blob)):
                yield base + i * 4, v, f"{name} payload"

    def profile_col(self, off):
        import json
        if not hasattr(self, "_col"):
            d = json.loads((ROOT / "research/other/external/FP3K-technical-handoff-2026-09-10"
                            / "analysis/firmware/raw-profiles.json").read_text())
            self._col = {c['offset']: c['table'] for c in d['columns']}
            self._row = {}
            for r in d['rows']:
                for p in r['profile_ids']:
                    self._row[p] = r['index']
        return self._col[off], self._row

    def rwzm(self):
        col, row = self.profile_col(0x60)[0], self.profile_col(0x60)[1]
        out = []
        for p in RW_PROFILES:
            for o in RW_OFFSETS:
                base, _ = self.profile_col(o)
                a = base + row[p] * 4
                if self.word(a) != RW_OFF:
                    raise SystemExit(f"RWZM 0x{a:08X}(profile {p} +0x{o:02X})"
                                     f" 原廠值是 0x{self.word(a):X},預期 0x{RW_OFF:X}")
                out.append(a)
        return out

    def groups(self):
        g = []
        # 2026-09-13:不再有畫格率群組。p83 原廠張數就是 3,我們什麼都不寫,
        # 所以也沒有東西需要還原 —— 照片路徑完全不受影響。
        if WITH_PREV:
            g.append((PREV, PREV_ON, PREV_OFF))
        if WITH_RWZM:
            g.append((self.rwzm(), RW_ON, RW_OFF))
        if WITH_V3TAP:
            # 一個群組只有一對值,所以深度與取樣窗分兩組。
            g.append(([a for r, _, a, *_ in V3TAP_REGS if r != 0x0734], 4, 2))
            g.append(([a for r, _, a, *_ in V3TAP_REGS if r == 0x0734], 5, 3))
        if WITH_HSW_WIN:
            for _, _, a, stock, on in HSW_WIN_REGS:
                g.append(([a], on, stock))
        if CHAIN and not WITH_CLAMP and [a for a, _, _ in g] != [PREV]:
            # og3ksel (OG_SAVE_ENUM) skips *every* group when leaving for another
            # OG; that is only right while the one group is the preview heights
            # every OG target shares.  A private group would be left modified.
            raise SystemExit("OG_CHAIN: GTAB must be exactly the shared preview group")
        if WITH_CLAMP:
            # og3ksel (OG_GTAB_SHARED) skips only the first group when leaving for
            # another OG: it must be exactly the shared preview heights, and no
            # private group may touch them.
            if [a for a, _, _ in g] != [PREV]:
                raise SystemExit("OG_CLAMP: GTAB before the clamp must be exactly the preview group")
            g += self.clamp_groups()
        return g

    def clamp_record(self, mode):
        """The clamp record of a sensor mode (see CLAMP_BASE), checked: +0 = mode."""
        rec = CLAMP_BASE + CLAMP_STRIDE * self.idx[mode]
        if self.word(rec) != mode:
            raise SystemExit(f"clamp record 0x{rec:08X}: +0 = {self.word(rec)}, not mode {mode}")
        return rec

    def clamp_groups(self):
        """One private GTAB group per clamp word of every donor mode of the target:
        on = stock | the video-clamp bits, off = stock.  The bits must be clear in
        the image (a mode that already has the video clamp is not ours to touch),
        and a stock video mode must have exactly these bits set (the reference)."""
        ref = self.clamp_record(106)                       # FHD30's mode: a stock video mode
        for off, bits in CLAMP_FIELDS:
            if self.word(ref + off) & bits != bits:
                raise SystemExit(f"mode 106 clamp +0x{off:02X} lacks 0x{bits:X}: the layout moved")
        out = []
        for mode in sorted({d for _, d, _, _ in FMT}):
            rec = self.clamp_record(mode)
            for off, bits in CLAMP_FIELDS:
                stock = self.word(rec + off)
                if stock & bits:
                    raise SystemExit(f"mode {mode} clamp +0x{off:02X} = 0x{stock:08X} "
                                     f"already has 0x{bits:X}")
                out.append(([rec + off], stock | bits, stock))
        return out

    def sreg_errors(self, mode, regs):
        """從映像重新導出某模式的暫存器列,確認每格的位址、暫存器與原廠值。"""
        bad = []
        table, count = struct.unpack_from("<2I", self.img, SREG_DESC - B)
        rows = [table + i * SREG_STRIDE for i in range(count)]
        hit = [a for a in rows if self.word(a) == mode]
        if count != 70 or len(hit) != 1:
            return [f"感測器暫存器表 count={count},mode {mode} 命中 {len(hit)} 列"]
        row = hit[0]
        for reg, k, addr, stock, on in regs:
            ins = self.word(SREG_CALLS + (k - 1) * 32 + 24)
            if ins & 0xFFF0F000 == 0xE3000000:      # movw r0, #imm16
                got = ((ins >> 4) & 0xF000) | (ins & 0xFFF)
            elif ins & 0xFFFFF000 == 0xE3A00000:    # mov r0, #imm8 ror 2*rot(小位址用這個)
                rot, imm = (ins >> 8) & 0xF, ins & 0xFF
                got = ((imm >> (2 * rot)) | (imm << (32 - 2 * rot))) & 0xFFFFFFFF if rot else imm
            else:
                bad.append(f"word {k} 的寫入點不是 mov/movw r0 (0x{ins:08X})")
                continue
            if got != reg:
                bad.append(f"word {k} 寫的是 0x{got:04X},預期 0x{reg:04X}")
            if row + 4 * k != addr:
                bad.append(f"0x{reg:04X} 在 0x{row + 4 * k:08X},不是寫死的 0x{addr:08X}")
            if self.word(addr) != stock:
                bad.append(f"M{mode} 0x{reg:04X} 原廠值 {self.word(addr)},預期 {stock}")
        gtab_end = GTAB + 4 + sum(12 + 4 * len(a) for a, _, _ in self.groups())
        if gtab_end > 0xC0732200:
            bad.append(f"GTAB 到 0x{gtab_end:08X},超出 og3ksel 擁有的 0xC0732200")
        return bad

    def v3tap_errors(self):
        """從映像重新導出 M139 那三格,確認位址、暫存器與原廠值。"""
        bad = []
        table, count = struct.unpack_from("<2I", self.img, SREG_DESC - B)
        rows = [table + i * SREG_STRIDE for i in range(count)]
        hit = [a for a in rows if self.word(a) == V3TAP_MODE]
        if count != 70 or len(hit) != 1:
            return [f"感測器暫存器表 count={count},mode {V3TAP_MODE} 命中 {len(hit)} 列"]
        row = hit[0]
        for reg, k, addr, stock, on in V3TAP_REGS:
            ins = self.word(SREG_CALLS + (k - 1) * 32 + 24)
            if ins & 0xFFF0F000 != 0xE3000000:      # movw r0, #imm16
                bad.append(f"word {k} 的寫入點不是 movw r0 (0x{ins:08X})")
                continue
            got = ((ins >> 4) & 0xF000) | (ins & 0xFFF)
            if got != reg:
                bad.append(f"word {k} 寫的是 0x{got:04X},預期 0x{reg:04X}")
            if row + 4 * k != addr:
                bad.append(f"0x{reg:04X} 在 0x{row + 4 * k:08X},不是寫死的 0x{addr:08X}")
            if self.word(addr) != stock:
                bad.append(f"M139 0x{reg:04X} 原廠值 {self.word(addr)},預期 {stock}")
        gtab_end = GTAB + 4 + sum(12 + 4 * len(a) for a, _, _ in self.groups())
        if gtab_end > 0xC0732200:
            bad.append(f"GTAB 到 0x{gtab_end:08X},超出 og3ksel 擁有的 0xC0732200")
        return bad

    def state(self):
        yield LOG, 0, "og3ksel 計次歸零"
        yield LOG + 4, 0, "og3ksel 最後 enum 歸零"
        yield FLAG, 0, "OG3K 旗標 = 0(開機時未選)"
        yield BITLATCH, 0, "位元深度鎖存 = 12-bit(fmttable 命中時覆寫)"
        if WITH_MATCH:
            # 1 = 尚未看到壞鍵。開機值 1 讓行為與改動前相同,只有 fmttable
            # 真的看到「自家標籤但查不到」時才會落下。
            yield MATCH, 1, "picker 同意 = 1(fmttable 看到壞鍵時清 0)"
        if WITH_ENGFPS:
            # 0 = 還沒命中過。og3kcanvas 看到 0 就不寫畫布 +0x030,
            # 留著 donor 原廠的值 —— 故障安全值,不會寫出 0.0 fps。
            yield FPSLATCH, 0, "引擎格率鎖存 = 未知(fmttable 命中時覆寫)"
        if WITH_FMTGUARD:
            # 開機值 UNKNOWN,不是 0(CinemaDNG)。restore 跑之前只有 og3kfmt
            # (使用者改格式時)會寫它;若開機時實際是 MOV 又沒改格式,舊的
            # 初值 0 會讓 restore 之前選 OG 的 og3ksel 發布 FLAG=1,FLAG=1+MOV
            # 就是 FLAG_AND_PICKER_DISAGREE.md §38 那條硬凍結。UNKNOWN 在 og3ksel
            # 眼裡是「非 CinemaDNG」,那一刻只記住偏好、不生效。
            # 見 notes/OG_BOOT_RESTORE_STABILITY_REVIEW_2026-09-23.md §2。
            yield FMTLATCH, FMTLATCH_UNKNOWN, "錄影格式鎖存 = UNKNOWN(og3krestore 會覆寫成真值)"
            yield RLOG, 0, "og3krestore 次數歸零"
            yield RLOG + 4, 0, "og3krestore 看到的 OGSAVE 歸零"
            yield RLOG + 8, 0, "og3krestore 看到的錄影格式歸零"
            yield RLOG + 0xC, 0, "og3krestore 結果碼 = 0(沒跑到)"
            yield RLOG + 0x10, 0, "og3krestore 讀回的 FLAG 歸零"
            yield RLOG + 0x14, 0, "og3krestore LV 重讀結果 = 0(沒試)"
            yield RLOG + 0x18, 0, "og3krestore 重讀時的 CamSch1 狀態歸零"
            # OGSAVE(0xC30754CC)**刻意不在這裡** —— 它要跨電源循環。
        yield TPL0, 0, "og3kout idx0 模板未建置"
        yield TPL2, 0, "og3kout idx2 模板未建置"
        yield OHITS, 0, "og3kout 命中數歸零"
        yield OREJ, 0, "og3kout 拒絕環歸零"
        yield HITS, 0, "格式表命中數歸零"
        if WITH_GS:
            yield GS_LOG, 0, "og3kgs 介入次數歸零"
        if WITH_PBSEL:
            yield PBSEL_LOG, 0, "og3kpbsel 命中次數歸零"
            yield PBSEL_LOG + 4, 0, "og3kpbsel mode5 次數歸零"
            yield PBSEL_ENT, PBSEL_ENT_VALUE, "og3kpbsel 要回傳的表項"
        yield ROW_LOG, 0, "畫布計次歸零"
        if WITH_CANVAS:
            yield ROW_LOG + 4, 0, "og3kcanvas 回放命中歸零"
            yield ROW_LOG + 8, 0, "og3kcanvas 最後 profile id 歸零"
            yield ROW_LOG + 12, 0, "og3kcanvas 呼叫端寬歸零"
            yield ROW_LOG + 16, 0, "og3kcanvas 呼叫端高歸零"
        if WITH_PBROW:
            yield ROW_LOG + 4, 0, "og3kpbrow 最後 profile id 歸零"
            yield ROW_LOG + 8, 0, "og3kpbrow 退回次數歸零"
            yield ROW_LOG + 12, 0, "og3kpbrow 最後退回寬度歸零"
        gs = self.groups()
        a = GTAB
        yield a, len(gs), "分組表:群組數"
        a += 4
        for n, (addrs, on, off) in enumerate(gs):
            yield a, len(addrs), f"群組 {n}:筆數"
            yield a + 4, on, f"群組 {n}:選中值"
            yield a + 8, off, f"群組 {n}:未選值"
            a += 12
            for k, ad in enumerate(addrs):
                yield a, ad, f"群組 {n} 位址 [{k}]"
                a += 4

    def hooks(self):
        # 0xC0BE44DC 是靜態函式指標表的一格,實質上就是一個 hook ——
        # 它一被寫進去,相機下次畫解析度名就會跳進 og3kname。所以它必須
        # 排在 payload 之後。2026-09-12 我把它放在 misc() 裡(payload 之前),
        # 相機在載入中途凍結。下面的 check() 會擋住這類順序錯誤。
        # 不再改函式指標表 0xC0BE44DC —— 直接 hook 函式進入點(見 HOOKS)。
        for site, code, stock, kind, name in HOOKS:
            yield site, branch(kind, code, site), f"hook {name}"

    def pooldepth(self):
        """把 MPoolFixed<4380U,96U> 的兩對界線常數放大到新的塊數。

        v2(釋放)與 v4(範圍)各用一對 movw/movt 組出 `(N-1) * 0x1128`,
        而那是**相對物件基底的位移**,所以搬家之後仍然正確,只要把值放大。
        """
        if POOLDEPTH is None:
            return
        span = (POOLDEPTH - 1) * 0x1128

        def imm16(word, value):
            return (word & ~0x000F0FFF) | (((value >> 12) & 0xF) << 16) | (value & 0xFFF)

        for lo, hi, what in POOL_BOUNDS:
            yield lo, imm16(self.word(lo), span & 0xFFFF), f"{what} lo"
            yield hi, imm16(self.word(hi), (span >> 16) & 0xFFFF), f"{what} hi"

    def all(self):
        for section in (self.pooldepth, self.cleanup, self.playback, self.emitter, self.name_string, self.misc, self.menu_csv,
                        self.rate_menu, self.fmt_table, self.payloads, self.state, self.hooks):
            yield from section()


def _active(src, defines):
    """只留下這個目標真的會組進去的行。

    前處理器是 clang 跑的;靜態檢查必須看見同一份程式,否則會把另一個
    目標的程式碼當成本目標的錯誤。
    """
    defined = {d.split("=")[0] for d in defines}
    out, skip = [], 0
    for line in src.splitlines(True):
        t = line.strip()
        if t.startswith("#ifdef") or t.startswith("#ifndef"):
            name = t.split()[1]
            on = (name in defined) if t.startswith("#ifdef") else (name not in defined)
            skip += 0 if on else 1
            continue
        if t.startswith("#else"):
            skip = 1 - skip if skip <= 1 else skip
            continue
        if t.startswith("#endif"):
            skip = max(0, skip - 1)
            continue
        if not skip:
            out.append(line)
    return "".join(out)


def _symbols(src, defines):
    """把 -D 巨集與 .equ 串起來解成數值。

    .S 的常數現在可能是 TARGET_* 前處理器巨集,所以靜態檢查不能再
    直接 int() 那個字串 —— 必須先解析,否則檢查會在重構後假性失敗。
    """
    sym = {d.split("=")[0]: int(d.split("=")[1], 0) for d in defines if "=" in d}
    for _ in range(4):                       # .equ 可能鏈兩層
        for name, value in re.findall(r"^\.equ\s+(\w+),\s*(\w+)", src, re.M):
            if name in sym:
                continue
            if value in sym:
                sym[name] = sym[value]
            else:
                try:
                    sym[name] = int(value, 0)
                except ValueError:
                    pass
    return sym


def plan(image=None):
    return list(Plan(image).all())


if __name__ == "__main__":
    p = Plan()
    bad = p.check()
    items = list(p.all())
    print(f"參考韌體 sha256 {p.sha[:16]}…")
    for name, _, base in PAYLOADS:
        print(f"  {name:<15} {len(p.blobs[name]):>4}B @0x{base:08X}")
    print(f"\n共 {len(items)} 筆寫入")
    if bad:
        print("\n★ 靜態檢查失敗:")
        for b in bad:
            print("   " + b)
        raise SystemExit(1)
    print("★ 靜態檢查通過")
