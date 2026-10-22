# res-lab 純計算／RCD 匯出 — 2026-10-09

本次依使用者要求拔除 res-lab（原 Sensor Lab）的錄影核心，只保留計算、編輯與
res-custom 格式匯出。修改本機來源、建置與離線模擬；沒有操作相機、寫實體卡、
commit／push 或發布。2026-10-08 的錄影核心卡仍保存於原目錄供歷史追溯。

## 現行架構

`50RESLAB.BIN` 是 Loader v3 FSB1 產品，id `RLAB`、version 2、min_svc 3。
自己的常駐區塊包含計算表、SLMP 私有選單、狀態、XCI 字模、128 KiB 匯出與
128 KiB 讀回緩衝。不再包含舊的 PIC recording core、25 個核心 hook、
10 個後期錄影／列表 hook、原廠表指標切換或靜態感測器補丁。

兩個自有 CHAIN claim 是 GUI-id `0xC056461C` 與頁面入口 `0xC05E82F0`。
uishare 負責字串池共享；loader 負責 claims、veneer 與關機 journal。
MODE 列表只讀描述子；OUTPUT 的 AXIS／29 欄 canvas 計算結果只寫自己的記憶體。
錄影設定的 FPS／位深不再驅動計算器，也不重寫原廠 EXCL 列表。

在 CINE 錄影設定 B2_5 按右側 Help 進入 FILTER／MODES／OUTPUT。
OUTPUT 的 Save RCD 列按 Right／OK，以原生 UI 回呼匯出
`\fpSup\RESCUS\LABnnn.RCD`。編號跳過既有檔名，大小寫不敏感。
沒有使用舊版不可到達的第四分頁；Private page 通過原廠頁面解析器與配置預算檢查。

## 匯出契約

RCD1 version 3，標頭常數由 res-custom `ogc_layout.py` 產生，沒有第二份標頭座標。
六個 sections 是 MODES、CANVAS、UI、STANDBY、RATECANVAS、PACK：

- 一個 stock donor 與原廠時序計算的最高格率；res-custom 生成實際支援的錄影格率。
- 29 個錄影幾何欄位、13 個回放欄位、六個待機 profile 的可見寬高。
- 預設與高格率的 `+0xB0` 旗標。
- 每份檔案的 LABnnn QS／Settings／Font XCI，與寬高數字圖示。尺寸相等時第二個數字資源改名以保持 NBR 名稱唯一。

寫入使用新檔名，再重新開檔核對實際長度與所有 bytes。缺資料夾、無可用檔名、
不支援的幾何／RAW14、寫入或讀回不符都顯示失敗；不以部分匹配視為成功。
res-custom 現行支援 CinemaDNG 8／10／12-bit，RAW14 可計算但匯出明確拒絕。
CRCT bin 保留 1／3；舊核心專用的 kernel 與 soft／std 不再出現在純計算介面。

`.RCD` 放入 res-custom 卡的 `fpSup/RESCUS/`，下次啟動由 `32RESCUS.BIN` 載入。
現行 consumer 最多檢查 16 份 RCD、同時啟用 6 個格式；此輪未驗證兩套選單同卡顯示。

## 精確成品

[普通卡](../../cards/20261009-calculator-v3/plain/)與
[debug 卡](../../cards/20261009-calculator-v3/debug/)共用完全相同的產品 bytes。
`50RESLAB.BIN` 444,480 B，常駐塊 712,576 B，SLMP 361,288 B，狀態 1,764 B。
普通卡不含 shell；debug 另帶 `00SHELL.BIN`。兩份 manifest 與 17 個建置來源
SHA-256 逐項核對通過，詳見 [verification.json](verification.json)。

| 檔案 | SHA-256 |
|---|---|
| `fpSup/50RESLAB.BIN` | `d224f8dc2e5002ddf1293dd8946963b7f94efd23128602d44ba60913204fb66b` |

建到全新目錄：

```sh
python3 -B projects/open-gate/build/build_v3_reslab.py --card --no-shell --out /tmp/reslab-calc-plain-new
python3 -B projects/open-gate/build/build_v3_reslab.py --card --out /tmp/reslab-calc-debug-new
```

## 驗證結果

| 範圍 | 最終結果 | 證據 |
|---|---|---|
| 精確普通卡 | 13 個不同案例的最新結果均通過 | [首輪 12 項](plain-tests.log)、[補驗 2 項](plain-followup.log)、[彙整](verification.json) |
| 精確 debug 卡與實際 shell entry | 3 項通過 | [日誌](debug-tests.log) |
| 舊選單、私有頁面、模式計算及既有 mutations | 99 項通過 | [日誌](menu-regression.log) |
| 注入未 claim 感測器寫入 | assertion 抓到，沒有 emulator exception | [日誌](mutation-unclaimed-sensor-write.log) |
| 移除逐 byte 讀回核對 | assertion 抓到，沒有 emulator exception | [日誌](mutation-unchecked-readback.log)、[mutations.json](mutations.json) |

普通卡首輪有一項測試呼叫的 SP 為 4 mod 8，與原生 C／UI 回呼要求的 8-byte
對齊不符，alignment assertion 報錯。測試改用正確 C 呼叫對齊後補驗通過；
另加實際頁面 hook 從 4 mod 8 入口保存 SP／暫存器、對齊呼叫並回原廠 push 的驗證。
debug 測試把 shell 自己的已 claim USB interface 補丁與 res-lab 計算後的感測器表分開比較。
兩個舊 host mutation 的替換位置亦隨新增條件分支更新，99 項回歸已完整重跑通過。
這些首輪失敗保留在日誌，未改列通過。

驗證實跑保存卡片的 AutoRun loader words、LOADER.BIN、res-lab ARM entry、
選單安裝、計算、原生匯出回呼、檔案 encoder、GUI／頁面 hook 與關機還原。
測試覆蓋檔名避撞、五種尺寸／binning、方形資源去重、2:1 aspect、缺資料夾、
非法尺寸、RAW14 拒絕、寫入失敗、內容損壞、額外尾 byte、NBR 拒絕、互斥 claim、
殘留 hook 修復、堆疊／暫存器保存與兩次關機。
韌體區每次寫入都須在 loader journal 覆蓋範圍內，共用 cave／交接區除外。
普通卡 entry 與計算／匯出前後，感測器表區 `0xC0B00000..0xC0D00000` 保持原樣。

res-custom 的實際 ARM core 在後續模擬開機中讀取原生產生的 LAB001.RCD，
建立自己的虛擬 profile，picker 回傳該 profile，canvas 的實際寬高為 3008×2000。
此流程未以 Python 產生的資料檔代替原生匯出。

Unicorn 在 macOS sandbox 內會 SIGILL；ARM 驗證於獲准的本機 sandbox 外執行。
沒有 skipped 測試。兩個 mutation 只編譯臨時 C 副本，沒有修改維護中的來源。

## 實機界線

原廠檔案／目錄、配置、快取、OS、modelCSV、變數與 pack 註冊由模型代替；
頁面內容另外經原廠解析器驗證。res-custom 的 uia_apply 與硬體相關呼叫沿用既有 harness 替身。
debug 只執行 shell entry，確認建立 worker 並返回，未執行 USB worker 的硬體傳輸。
真實 LCD／選單生命週期、SD 寫入時機、快取、排程、跨卡暖啟動與錄影品質仍需實機驗證。
