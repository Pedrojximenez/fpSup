# CinemaDNG RAW 寫入路徑：已確認的末端與尚未閉合的上游

2026-09-24，僅離線閱讀既有反編譯、韌體映像與歷史測試紀錄；本輪未連接相機、未執行 probe、未修改韌體或素材。

## 結論

已追到 FHD CinemaDNG 實際使用過的末端寫檔路徑：它取得 RAW descriptor，將緩衝區起點移到已準備的標頭之前，計算長度／對齊，再登記整個檔案區段供輸出。**在下列已檢查的封裝函式中，沒有對有效 Bayer 像素作 ColorMatrix／創作模式的色彩運算。**

這與「同一種 RAW 訊號搭配不同 OFF／normal metadata」相容，但不是從感光元件到 RAW 緩衝區的全鏈證明：影像資料抵達這個階段之前的 ISP、位深／讀出模式、增益及硬體設定尚未全部排除模式依賴。

因此，搭配 [現有 OFF／正常模式實拍 RAW 比較](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/native-calibration-20260924/existing-raw-capture-comparison.md)，可提高將 fp normal CM 用於 OFF 素材的合理性；仍不能稱為所有 CinemaDNG 模式的 RAW 等價證明或絕對色準驗證。

## 1. 已有實機紀錄定位真正的 FHD 寫檔呼叫

既有紀錄：[fhd_compression/README.md](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/fhd_compression/README.md:41)，2026-08-31 的 1920×1080、12-bit CinemaDNG 測試。

- 真正執行的呼叫是 `C0722AFC → C069AC88`，return address `C0722B00`。
- 登記區段起點 `53B02C00`，長度 `00318200`，即 3,244,544 bytes。
- 同文件後續測試記錄 RAW 起點 `53B16000`，與區段起點相差 `0x13400`，即 78,848 bytes。
- 較早猜測的 `C0722A58` 是另一個 v18 路徑，不能用它代表已確認的 FHD 路徑。

這些是本專案先前的觀測紀錄，本輪沒有重做實機測試。A_original.DNG 的檔案長度與 RAW strip offset 也分別是 3,244,544 與 78,848；相符的版型不表示它就是歷史 probe 所記錄的同一幀。

## 2. descriptor → 完整 DNG 區段

反編譯根目錄：`/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/`。

| 函式 | 可直接看到的行為 | 定位 |
| --- | --- | --- |
| `XC_StillCreateFile__v4 @ C037E0F8` | request `+4 == 1` 分支取得 CinemaDNG format；將 request `+4C` 指標減去 `+14C` 標頭長度，呼叫 format `+4C` setter，再交給 `C03A5348` | [blk_c03.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:85433) |
| `FUN_c0010cb8` | 純粹回傳第一個參數減第二個參數；上一步不是把 RAW 做數值減法 | [blk_c00.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:13160) |
| `XC_StillFileFormatDng__v17 @ C06A5C98` | 呼叫 descriptor copy 到 format `+18` | [blk_c06.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c06.c:134209) |
| `FUN_c02e5b78` | 複製 18 個 32-bit 欄位，即 72-byte descriptor，不是逐像素處理 | [blk_c02.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:147704) |
| `FUN_c03a5348` | format `+48` 取得 descriptor；有 buffer 時呼叫 format `+54`，帶入標頭長度及 `0x200` 對齊；最後交給 `C069ADE0` 輸出 | [blk_c03.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:113399) |
| `XC_StillFileFormatDng__v19 @ C0722A68` | 用 format `+54` 的 buffer 位址與 header + RAW size 建立區段；有 compression flag 時改採壓縮長度；呼叫 `C069AC88` 登記 type 2 區段 | [blk_c07.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c07.c:29752) |
| `FUN_c0699390` | 將長度向上對齊，在有效資料尾端之後補零 | [blk_c06.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c06.c:124901) |
| `FUN_c069ac88` | 保存 buffer／length／type 到最多 8 個區段的鏈表，不解讀像素 | [blk_c06.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c06.c:126329) |

注意兩個 `+54` 不同：vtable 的 `+54` 是函式槽；format 物件的 `+54 = +18 +3C` 是 descriptor 內的 buffer 欄位，不是色彩模式值。

本輪直接讀取 `seg0_c0000000.bin` 核對 vtable，而非只憑反編譯的類別名稱：

| vtable | slot +48 | slot +4C | slot +54 | slot +58 |
| --- | --- | --- | --- | --- |
| `C2EF6578` | `C06A5C88` | `C06A5C98` | `C0722A68` | `C06A5CB8` |
| `C2E3A938` | `C06A5C88` | `C06A5C98` | `C0722A68` | `C06A5CB8` |

Segment SHA256：`aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`。這些位址均在此 segment 的映射範圍，不使用超出 MAIN 映射的任意偏移推算。

## 3. metadata 準備與 RAW 來源的界線

`FUN_c0378a50 @ C0378A50`：[blk_c03.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:82816)。

初始化會建立 CinemaDNG metadata 物件，呼叫 `FUN_c02b8e38(6,4,...)` 與 `(3,4,...)` 傳入當前設定；建立 format、掛入 RAW descriptor、準備標頭，將標頭長度存到 request `+14C`。它另外準備錄影配置，最後啟動 `FUN_c030cf98` 的影像來源路徑。

這說明標頭與影像緩衝區可分開追蹤。已另行確認的 `FUN_c02c4a50` 負責 OFF／normal ColorMatrix 標籤選擇，不能據此推論影像來源端完全沒有其他處理。

尚未閉合的問題是：**每種 CinemaDNG 讀出／位深設定下，色彩模式是否會改變 RAW buffer 生成之前的任一硬體狀態或處理。** 末端 writer 不做色彩矩陣，不能代替這項上游證明。

## 4. 機內 DNG 再顯影的補充證據

- `XC_PlayFuncSeqDngDeveloping__v32 @ C03C8350`：[blk_c03.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:140864)。讀取影像尺寸、位深、compression、tile／strip offsets 與 byte counts；compression 7 路徑呼叫解壓縮 helper，未壓縮路徑讀 strip 並複製／引用 RAW 緩衝區。之後另行做 RAW 預覽準備與 metadata 通知。
- `XC_PlayFuncSeqDngDeveloping__v34 @ C03C9558`：[blk_c03.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:141396)。`dngPreview` 階段重新套入當前顯影設定 `FUN_c02b8e38(0xB,3,...)`，再呼叫 `FUN_c04250e8` 生成預覽。

這是「載入 RAW」與「套設定顯影」分開的結構證據，不是 Sigma Photo Pro／Resolve 的行為證明，也不等於已逆向完整 ISP。

## 對目前候選檔的意義

`C_firmware_normal.DNG` 仍是最小改動候選：使用 fp 原廠 normal 雙光源 CM 與本機身校準，保留原 RAW、AsShotNeutral、黑白位準，以及 OFF 的 identity HSM／tone。它既不把 RAW 變成 BMD，也不烘焙 gamma。

目前證據支持把 C 作為受控試用的輸入描述基線；不支持稱它為完整 Standard look、已測得的光譜校準、所有機身通用的固定矩陣，或已完成所有 CinemaDNG 模式驗收的修復。沒有批次改寫任何原始素材。
