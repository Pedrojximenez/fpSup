# 一個新 UI 要多少錢 —— 看你要到哪一層

2026-09-29。給「我想加一個機上設定」的人估價用。
基準是 OG3K 那一次的實帳(`projects/open-gate/notes/UI_STATE2_HAS_NO_ICON.md` §AB)。

## OG3K 的實帳:360 筆記錄

| 類型 | 筆數 | 用途 |
|---|---:|---|
| `layout-keys` | **315** | 18 組大 QS + 18 組小 QS 的完整 companion properties |
| `state-end` | 36 | 各組 timeline 終點 **33 → 66** |
| `literal-delta` | 6 | 底部 UHD/FHD/OG3K footer、第三格、cursor 範圍 |
| `summary-label` | 1 | `0xC1A7246B` 收合摘要 |
| `QS-limit` | 2 | `0xC237249F` / `0xC25E405A` 最大索引 1 → 2 |
| **合計** | **360** | 外加 3 個 XCI(86x49 / 86x74 / 150x38)與私有 NBR |

**獨立交叉驗證**:用字串池反查「哪些記錄提到 `20_/21_/MV_Resolution`」得到 **218 筆**
(`nbu_format.py group 20_MV_Resolution`),其中 **152 筆在 QS_CINE / QS_STILLlike / QS_Common**,
`B2_5`(Settings)只有 **6** 筆。兩份帳的結構完全一致:**錢都花在 Quick Set。**

## 為什麼那麼貴

因為 OG3K 做的是「**在一個既有的 enum 控制項上多加一個狀態**」,
而解析度這個控制項同時出現在 Quick Set(大圖磚、小圖磚、底列)、HUD、Settings。
每一個出現的地方、每一個 companion 屬性(visibility / rectangle / position /
collapse / cursor / timeline)都要跟著多一個狀態,少一個就疊在一起。

**這跟「在清單裡多一列」是兩件完全不同的事。**

## 四層價目表

| 層 | 做得到什麼 | 代價 | 驗證狀態 |
|---|---|---|---|
| **1. OSD 文字** | 在畫面角落寫我們自己的字 | `display text` + `display osd 1`(×3,三重緩衝);版面是寫死的立即值,`mem set` 可改;顏色是 **256 筆 AYUV 調色盤的索引**(`0xC0B520BC`,低位元組在 `0xC0BB1208`) | ✅ 實機,245/256 索引量過 |
| **2. 清單多一列** | Settings 裡多一個可選項,有文字,**選得到** | **原地改那份 CSV(等長)+ controller 最大值**。repoint 是死的,不要用 | ✅ 位元深度 3→4 實機定案 2026-09-29。⚠ **格率 9→10 並沒有**:那張 popup 只有九個文字子物件,要另外原地補一個(`projects/open-gate/notes/IMX410_FULL_DESIGN.md` §8.11,仍不用 hook) |
| **3. 多一個設定項** | 全新的一列設定,有自己的變數 | donor 列改嫁 + 私有變數註冊 + 配置標頭 | ❌ 只有離線配方 |
| **4. 既有控制項多一個狀態** | 像 OG3K 那樣,QS 圖磚也跟著對 | **≈360 筆記錄 + 3 張圖 + 私有 NBR + 3 個 Thumb hook** | ✅ 實機(OG3K / Formats / FP3K) |

**第 4 層的價錢幾乎全在 Quick Set。只要不需要 QS 圖磚,就掉到第 2 層。**

## 對到 fpSensor Lab

路線圖(`SIGMA_FP_PRODUCT_ROADMAP.md`)給 fpSensor Lab 的兩個 UI 里程碑:

| 里程碑 | 落在哪一層 | 代價 |
|---|---|---|
| 「runtime 顯示目前 mode」 | **第 1 層** | OSD 文字,已經會了 |
| 「建立安全候選清單」 | **第 2 層** | 一個 CSV + 8 bytes + controller max |
| 「相機端安全控制介面未完成」 | 第 2 層就夠,**除非**要 QS 圖磚 | — |

而且清單長度不是問題:原廠 `.cvm` 有 10 個檔正好 7 列、`B3_1` 白平衡 **12 列**、
光圈 **129 列**,韌體還會按長度挑模板(`_4_and_Under` / `_10_and_Over`)。
**一個 10 個 sensor mode 的候選清單,原廠規格內。**

要注意的只有兩件:

1. **選了之後要有東西吃它。** 我們的第 2 層補丁**只動 UI**,沒有格式註冊、沒有畫布、
   沒有感測器模式切換 —— 那是 OG3K 那 1005 words 的 core 在做的事,跟 UI 無關。
   Sensor Lab 本來就有 mode 控制核心,要接的是「選單的值 → 那個核心」。
2. **生效時機**:CSV 是開那一頁時才讀的,AutoRun 之後打補丁來得及;
   但 controller 最大值是 NBU 記錄(在資源集 `B2_5` 第 1368 筆),
   詳見 [`HOW_CHANGES_TAKE_EFFECT.md`](HOW_CHANGES_TAKE_EFFECT.md)。

## ⚠ 兩個對外頁面已經過期

- **`fpSup/projects/ui-sup.md`** 的「未解」還寫著「文字顏色的編碼格式…只確定兩個值,
  其餘是外推不可信」。**已經解掉了**:顏色是 256 筆 AYUV CLUT 的索引,表在
  `0xC0B520BC`,逐索引拍照驗過 **245/256 在 4 階以內**;前兩次量錯是因為拿細筆畫量顏色。
  見 `research/display/notes/CENTER_LINE.md` §9。
- **`fpSup/projects/sensor-lab-sup.md`** 仍把 `0xC37CE210` 當錄影幾何。
  那個位址**已被推翻**(UHD 讀 0),真正的來源是 CameraMgrSetting +0x40 再 +16/+10。

兩個都是公開站上的頁面,**沒有改,等你決定**。
