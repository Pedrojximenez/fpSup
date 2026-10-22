# fp LUT 原生處理區塊補查

2026-10-09。離線讀既有 Ver.5.02 韌體與反編譯，未連相機、未寫卡。
目的：接續使用者的 `.cube`／Live View／CDNG 需求，確認機內多個色彩區塊能否組合使用。

## 修正前提

9 月 27 日筆記的「名稱表未被程式引用，只能實機找 CUVAREA」不成立。
`blk_c01.c` 的 **`FUN_c01597b8`** 是具名硬體 dump：先印區塊名，再列出 MMIO。
**`FUN_c019c810`** 另有 MMIO、word 數和 shadow 的 descriptor。
兩條直接證據可交叉核對，不用依名稱排列猜位址。

`extract_isp_map.py` 現在輸出 120 筆具名診斷路由，附來源 SHA-256。
名稱存在／缺少不證明完整像素管線或 GPU／3D LUT 有無。

## 具體落點

| 原生區塊 | MMIO | Shadow | 直接證據 |
|---|---|---|---|
| RGBLMAT | `30115100` 起 | `30210CB0` 起 | 已有兩組係數與 scale fallback 稽核 |
| RGBMAT_PL | `30115B80..BA0` | `30210EE0..F00` | `FUN_c01083d8` 原樣寫九個 word |
| CUVAREA CARE_SEL | `30116600..640` | `30211024..1064` | descriptor 17 words；`FUN_c010b958`、`FUN_c010baf0` |
| CUVCONT | `30116700..71C` | `30211068..1084` | descriptor 8 words，與 CUVAREA 相關 setter 交疊 |
| CSUP | `30116800..82C` | `30211088..10B4` | descriptor 12 words |
| ECSUP | `30116900..904` | `302110B8..10BC` | descriptor 2 words |
| C_SAT_C | `30117B00..B5C` | `3021127C..12D8` | descriptor 24 words；先前 `30117280` 實際被 dump 標成 BLT_NLM |
| TMAP（語意未定） | `30130600..640` | `30212828..868` | descriptor 17 words；已有尺寸／格點設定，不能直接稱 tone mapping |
| LCD/輸出 CSC＋RGB gamma | `301908xx/90Cxx` | 獨立顯示 driver 狀態 | 沿用 [display-route-audit](../../liveview/display-route-audit.md) |

這些是 XZ01 的處理區塊，並非數顆獨立 GPU。各區塊是否可用於同一張影像、能否與其他產品並存，尚未上機確認。

## CUVAREA 已找到的欄位與 native 路徑

`FUN_c010b7e0` 接收 10-byte 資料：前兩 byte 與四個 signed short。
兩對向量依正負號各產生四個象限旗標，向量分量保留 10 bits。
`FUN_c010baf0` 把它們寫到：

- `30211024`：結構 `+24/+28`，各 10-bit，對應 `30116600`。
- `30211030`：`+3C/+40/+44/+48`，四個 byte，對應 `3011660C`。
- `30211034`：第二對 `+4C/+50`，對應 `30116610`。
- `30211040`：第二組象限旗標，對應 `3011661C`。
- `30210FDC`：前兩 byte 的控制，位於鄰接 APSUP 區塊，表示 setter 跨區塊，不能只讀 CUVAREA 起點。

原生資源鏈：`PictureQualityCommonPrePst__v14 @ C068FF90` 選 resource **0x17**，
呼叫 `FUN_c0101028` → `FUN_c010b7e0` → `FUN_c010baf0`；
`PictureQualityCommonPrePst__v17 @ C0690098` 選 **0x18**，處理同一族其他欄位。
context 由 `param_2+F8` 傳入；更新／強制路徑另看 `+11C/+11F`。
目前尚未將這個 context 的數值與 LV／MOV／STILL 的實際工作狀態一一對上。

**這證明可設定色度區域，尚未證明它能做任意 per-hue RGB 映射。**
`FUN_c06948b0` 的選擇鍵是 `param_2+FC`：在 `param_3+90/+98` 指向的兩張表中，
由尾往前找第一筆門檻不大於此鍵的記錄，分別複製 12／20 bytes；步距為 16／24 bytes。
`FUN_c06949f8` 對 `param_3+A0` 的表做同類選擇，步距 12、複製 8 bytes。
這些是門檻表選擇，**尚未證明鍵是色彩 mode、ISO 或其他狀態**；不能據此寫入模式 enum。
`FUN_c06979b8` 只在 `param_3+180` 的 8-byte resource 描述中找 ID；找不到會回 index 0，
因此後續 native adapter 不能把它的返回值當作「ID 必定存在」。
下一步追這兩個物件的來源、實際 context 與像素結果。

## TMAP 的名稱不是 tone mapping 證據

`FUN_c01597b8` 的 TMAP dump 為 `FUN_c015c1d8(0x30130600,0x30160640)`。
第二個 decompiler 參數不能直接當作同一區塊尾址；descriptor 明列起點 `30130600`、17 words。
本次 extractor 修正為取第一個參數，避免多參數形式漏掉整條路由。

`FUN_c0158558` 將 10-word packed 結構寫入／讀回這 17 個 shadow word；
`FUN_c01588b8` 也可排入前五個 MMIO 寫入。
`FUN_c013fee0` 的使用包含尺寸減一、格點數除四、`4096/(格點數-1)`，
以及多組座標與 `2048/(兩值之差)`。這是可核對的欄位運算，
更像尺寸／格點映射候選；完整硬體功能仍未證明。
舊 README 將 TMAP 直接展開為 tone mapping 已撤回；不能拿這個縮寫承諾 3D 色彩 LUT。

## RGBMAT_PL 不能直接當成第二級 RGB look

`PictureQualityCommonPrePst__v71 @ C0691AD8` 選 resource **0x3E**；
更新時 `FUN_c011a8b0` 填九字，`FUN_c01083d8` 寫 shadow。
原廠初值為：`[128,0,179,128,468,421,128,227,0]`。
若後兩列的交叉項按 9-bit signed、尺度 128 解讀，
數值與 601 類 YUV→RGB 相符。**這是數值假說，不是已量到的硬體公式。**
因此多矩陣／gamma 的組合值得研究，但不能先把每一個名稱含 RGBMAT 的區塊串成 RGB→RGB look。

## 對 fpSup LUT 的影響

完整 `.cube` 的匯入與取樣基準先保留全部 RGB 節點，不默默降成矩陣。
機內 backend 需要比較至少兩條路徑：輸出 CSC＋RGB gamma、原生 ISP 多區塊組合。
每條都要記錄對 full LUT 的誤差、吞吐、LV/REC/STILL 路由、RAW 是否不變及 OSD 影響。
未取得這些證據前，不宣稱任意 `.cube` 已能在 fp 即時執行，也不排除它。

CDNG 分開處理：保存完整 `.cube` 與選擇設定，不以 look 修改 `ColorMatrix`／白點來冒充 LUT。
離線工具和下一階段驗收見 [LUT sup](../../../projects/lut-sup/README.md)。
