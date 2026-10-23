# RES-Custom：重開後首次 QS 開啟緩慢 — 2026-10-15

使用者確認只有重開機後第一次開 QS 很慢；尚未測試先前的 FPS 文字樣式候選。這次提供獨立 QS 候選，保留 FPS 樣式修改前的顯示，供比較首次開啟時間。未取得秒數或實機分段量測，因此下列來源分析不能當作已確認的全部耗時原因。

**後續已上機：** 先前 plain 五格式版首次 4.3424 → 4.3268 s，第二次約 0.53 s，沒有明顯改善。
之後重新接回的卡具有不同 AutoRun／loader，不能與先前數字當成同卡 A/B。
目前卡上為 `combined-fix12`：黑框往外加厚約 3 px，保留白字本身與 fix10 的間距；開關 QS 後實拍完整 `29.97 FPS`，對比色驗證後已還原黑色。字形仍有差異。
先前 1910 是更新前原廠畫面，據此作出的「59.94 外觀一致」判定撤回。
首次 QS 延遲未解決；最後正式數據為 fix4 的 **6.1161 s**，fix12 未重新計時。
設定區保留、完整檔案讀回及十一個模組載入均核對。
成品與範圍見 [最新 run7 結果](on-camera/run7/RESULTS.md)、[上機階段記錄](on-camera/RESULTS.md)。
下面「本輪未上機」指最初離線候選階段，不能代表最新部署狀態。

## 已查明的路徑

- FPS 修改前後的 QS 初始化、圖片 pack 註冊與 cache 重建邏輯相同；首次延遲不能歸因於使用者尚未安裝測試的 FPS 候選。
- 現行程式在每次啟動後必要時重建先前已快取的 QS 版面一次。只有 tree 可釋放、沒有其他持有者且不在載入自身時，才呼叫原廠 cache 的釋放及重建；後續沿用 cache。這與使用者的首次開啟現象一致，但實際延遲各階段的占比仍未知。
- CINE QS 資源集約 1.19 MB、14,285 筆記錄、955 個物件；原廠版面解析與整棵 tree 的圖片載入仍需實機量測。STILLlike 為 1.30 MB、15,769 筆記錄、1,036 個物件。
- 自訂 QS 配方有 371 筆目標記錄，其中 315 筆 clone 記錄原先會為每個格式重複複製整份、逐漸增大的資料。
- 抽查現存 release 與 download-check 的 AutoRun，沒有舊問題中過長的填充行；本輪未改共用 loader 或 AutoRun。

## 本輪調整

`qs_clone` 改成一次寫入所有自訂格式的 key。各 property 的原始內容只複製一次，依原本 slot 順序附加時間和圖片 ID；記錄大小、屬性與 key 數仍受界限檢查。原本的 hook、cache 生命週期、資源註冊及重建時機保留。

以下是對 315 筆 clone 記錄的 `copy8` 複製量計算，不是相機測速，也不是整體 QS 開啟時間的改善比例。詳見 `clone-copy-work.json`。

| 自訂 QS 格式數 | 原複製量 | 新複製量 | 複製量減少 |
|---|---:|---:|---:|
| 1 | 33,660 B | 33,660 B | 0% |
| 2 | 73,260 B | 39,600 B | 45.95% |
| 5 | 227,700 B | 57,420 B | 74.78% |
| 6 | 291,060 B | 63,360 B | 78.23% |

這只減少 consumer 自訂記錄組裝的工作。不能推論它已解決全部等待，也不能排除原廠解析、圖片載入或其他首次初始化才是主要耗時。

## 成品與來源

- 成品：[`qs-only/32RESCUS.BIN`](qs-only/32RESCUS.BIN)，187,520 B。
- SHA-256：`ef4580991a7487d0ad1472ad028f107862cff6bac33309a5b71f1fe4e6070b5f`。
- 使用 Virtual RCD consumer v21 的 FPS 樣式修改前來源，僅加入本輪 QS clone 調整；沒有新增 LV_RECORDS／三段字級。保留原 loader、設定 ABI 與格式資料流程。
- FPS 原廠風格候選 [`../20261015-fps-text-style/final/32RESCUS.BIN`](../20261015-fps-text-style/final/32RESCUS.BIN) 的檔案保持原樣。維護中的來源則同時包含 FPS 及本輪 QS 調整，不能把一般新建 BIN 當成這份 QS-only 成品。
- `legacy-fps-root/projects/open-gate/build/res-custom` 保存 QS-only 建置來源，其周邊目錄透過 symlink 使用既有工具、韌體及共用 loader。沒有建立另一套 loader。
- 建置：`python3 -B projects/res-lab/validation/20261015-qs-first-open/legacy-fps-root/projects/open-gate/build/res-custom/build_v3_rescustom.py --virtual-rcd --out projects/res-lab/validation/20261015-qs-first-open/qs-only`。
- `source-before/` 保存本輪 QS 調整前的維護來源；`qs-source-change.diff` 記錄這次 QS 變更；`provenance.json` 記錄來源與成品雜湊。

## 離線驗證

維護來源與 QS-only 來源各跑相同 5 個聚焦測試，均 5／5 通過（36.340 s、36.131 s）。涵蓋一個格式的既有參考配方、兩個與六個格式的全部 371 筆參考記錄、非自有記錄透傳、每個 context 只註冊一次圖片 pack／失敗列排除，以及開機後安全地只重建一次 cache。

另以準備交付的實際 BIN 與同目錄五個 RCD 執行 `verify_candidate.py`，不是用測試重建的 consumer 代替成品。Virtual row 加上五個 RCD 的六個 QS 格式、371 筆記錄全部符合獨立參考資料，reader 的原始 base／cursor 還原，關機後 hook 與舊 FPS 的 LV journal 皆還原；成品雜湊與 build.json 相符。結果在 `candidate-verification.json`。

模擬執行真實 loader、ARM hook 與 consumer 程式；GUI、原廠記錄解析下層、cache、圖片載入與硬體服務使用既有 harness 的替身。這些測試驗證內容與還原，不驗證 LCD 畫面或硬體耗時。Unicorn 的 macOS 執行記憶體需要權限，因此使用已核准的離線模擬執行；沒有連線相機。

## 待實機驗收

本輪未寫卡、操作或重開相機，也未更新發布品。仍需在相同啟用格式數與模式下，比較重開後首次 QS 的等待秒數，以及立即關閉再開的第二次等待。若總等待變化很小，應量測原廠 cache 重建／版面解析／圖片載入各段，再決定下一步；不能用上述複製量推估總改善幅度。240p 工作維持暫停。
