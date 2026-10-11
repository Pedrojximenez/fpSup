# Res Lab／Virtual RCD v1 — 2026-10-09

依使用者「先做 res lab」實作第一個 Virtual RCD producer。本輪只修改本機來源、
建置與離線驗證；沒有操作相機、寫實體卡、commit／push 或發布。

## 完成的流程

CINE 錄影設定 Help → Res Lab FILTER／MODES／OUTPUT → Apply。
Res Lab 的 ARM encoder 在記憶體產生完整 RCD1 v3，透過唯一的共用介面交給
res-custom 驗證、編譯與套用，同一個 Custom 列立即使用新配方。
無須 `.RCD` 檔案或 RESCUS 目錄，也不需要重開機。

consumer 不認 Res Lab／Julien 的專用參數。已測試 16 個 producer 註冊、第三個
id 經同一個 Apply 使用真正的 encoder，動態列仍只有一列。
普通磁碟 RCD 與動態列共存，重新編譯後原列的 UI 身分、圖示與 picker 保持可用。
Julien style 接入、工具啟用清單與參數持久儲存尚未實作。

詳見 [介面與資料壽命](../../../open-gate/build/res-custom/VIRTUAL_RCD.md)。
本版限 CinemaDNG 8／10／12-bit；RAW14 可以計算但拒絕套用。
Res Lab 設定與配方只存在本次開機，關機後需重新設定／Apply。
16 個 producer、一個共用動態列；每次開機最多 32 份不同圖示 pack／合計 4 MiB，
相同內容去重。已發布 NBR 不覆寫或回收，保留原生 reader 的資料壽命。

## 精確成品

[普通卡](../../cards/20261009-virtual-rcd-v1/plain/)與
[debug 卡](../../cards/20261009-virtual-rcd-v1/debug/)使用相同產品 BIN。
debug 另帶既有 `00SHELL.BIN`。兩者的 AutoRun、LOADER.BIN 與前版純計算卡逐 byte 相同；
沒有新增 loader ABI、固定位址服務指標或 payload／AutoRun 版本配對。

| 檔案 | 大小 | 常駐配置 | SHA-256 |
|---|---:|---:|---|
| `32RESCUS.BIN`，RCUS v2／min_svc 3 | 73,216 B | 743,616 B | `7031bfc9109e9186cd639d43d899de4b311568281e1246b522d69d6d19e62f5b` |
| `50RESLAB.BIN`，RLAB v3／min_svc 3 | 450,976 B | 719,104 B | `65074c7467eaafb8cfe8bd1562176aa6993bd023a585b98da1c0f2b333e5d83c` |

manifest 及 build.json 記錄的來源 hash 均獨立核對，見 [artifact-audit.json](artifact-audit.json)。
最後只補正 header 的借用資料壽命註解；重新建置的 BIN／AutoRun 逐 byte 相同，
保存的 build.json 與 manifest 使用該次 builder 原生產出的新來源 metadata。

## 離線結果

| 範圍 | 結果 | 證據 |
|---|---|---|
| 精確普通卡，Virtual RCD 與原生設定頁 | 19 項通過 | [plain-tests.log](plain-tests.log) |
| 精確 debug 卡，實際 shell entry／套用／GUI／還原 | 3 項通過 | [debug-tests.log](debug-tests.log) |
| 原有 res-custom 全套 | 65 項通過 | [rescustom-regression.log](rescustom-regression.log) |
| 舊 Res Lab 與選單 | 首輪 90 項中的 89 項通過，1 項 import 錯誤修正後補驗通過；另補驗更新後幾何、圖示與原生頁面 | [首輪](legacy-menu-initial.log)、[import 補驗](legacy-import-followup.log)、[最終 3 項補驗](legacy-followup.log) |
| 共用 boot entry 建置矩陣 | 14 配置、3 組 AutoRun 比對、8 個 catalogue reference 通過 | [日誌](boot-entry-chain.log)、[report](boot-entry-chain.json) |
| 移除 recording guard | 行為 assertion 抓到，無 emulator error | [日誌](mutation-recording-guard.log) |
| 移除 RCD 校驗拒絕 | 行為 assertion 抓到，無 emulator error | [日誌](mutation-rcd-checksum.log)、[mutations.json](mutations.json) |

測試執行保存卡的 AutoRun loader words、LOADER.BIN、兩個產品 ARM entry、服務註冊、
真正 encoder／validator／table compiler、recording picker、canvas、resolution setter shim、
原生 Apply key 回呼、GUI hook 與關機還原。沒有 skipped 測試。

幾何驗證包含 3008×2000、M139／M98／bin3 的連續切換與 2:1；直接讀取 picker 的
virtual profile，再執行 canvas callback 核對實際寬高，並非只核對 success flag。
保留舊 NBR bytes、相同 pack 去重、provider owner、防重入、ABI／status、錯誤 checksum、
RAW14／非法幾何／格率／MOV、所有三個 busy 來源、配置失敗及提交前再次 busy 均有獨立 assertions。
忙碌失敗保留原表；已停止的 live view 必須重啟並還原 scheduler。
UHD → 動態 FHD backing value 經真正 setter shim；不在提交中途嵌套 live-view reload。

原生 `ui_apply.c` 另在 host fixture 上執行，共用 Help alias 的最終 B2_5 bytes
與 typed reference applier 完全一致，原格率 page variants 保留，stock pool／NBU 沒有改寫。
真正兩層 GUI hook 核對 `VRC_SETTINGS`、Res Lab 私有名稱、無可用 producer 時回原廠 Help、
其他名稱的原生續接。Res Lab 未取代 res-custom 的錄影設定頁。

原廠感測器表 `0xC0B00000..0xC0D00000` 保持原樣。debug 只允許 shell 本身的精確
USB interface 補丁；關機後該字也還原。consumer 使用自己的表複本與常駐資料。

## 首輪失敗與修正

保留首輪失敗日誌，不將其改寫成通過：

- 新 checksum fixture 最初把 Python bytearray 交給要求 bytes 的 Unicorn API，轉成 bytes 後通過。
- 原生 GUI host fixture 的 stock 字串須回原 stock pool，未綁定的 action value `0xFFFFFFFF`
  不代表頁面名稱；修正解碼 fixture 後，實際 C page bytes 比對通過。
- debug 首輪把 shell 自己的 USB interface 字也當成感測器表變更；改按 shell 精確 patch
  與已啟用狀態核對，仍逐 byte 比對整個區域。
- standalone res-custom builder 新增 sizeof probe 時缺少 sl_menu 模組路徑；補正路徑，原匯出載入補驗通過。
- Jose register 等價測試遇到既有 Unicorn memory-write observer 的 dropped-store 問題。
  經獨立「先跑真正 register lookup、再裝 observer」對照確認；與原先 timing clone 的 workaround
  一致。register clone bytes 與每筆 sensor write 仍全部比較，修正 fixture 後完整 65 項通過。

## 實機界線

OS、配置、檔案系統、變數／modelCSV、原生 getter／setter body、live-view 操作、
資源註冊與硬體 register writer 使用維護中的 fixture。整卡 ARM harness 的 uia_apply
由替身處理，該新增設定頁操作另以正式 C applier／typed model 驗證。
debug 執行 shell entry 並核對建立 worker 後返回，沒有執行 USB worker 傳輸。
Unicorn 在 macOS sandbox 內 SIGILL；ARM 驗證在已獲准的本機 sandbox 外執行。

這些結果不代表真實 LCD／圖示快取、GUI reader 壽命、排程、暖開機或錄影品質已通過。
本輪沒有操作相機或寫入實體卡。
