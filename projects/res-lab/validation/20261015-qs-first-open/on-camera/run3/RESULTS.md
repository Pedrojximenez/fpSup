# FPS／QS 實機續測 — 2026-10-15

> **使用者指正後撤回外觀驗收：** 1910 是開關 QS 前的舊畫面，元件樹已更新不等於 LCD 已採用。重新開關 QS 後 1911 顯示新版較細、間距偏大且無黑描邊。下面原先「字形一致／外觀通過」只記錄當時誤判，不能再當成驗收結果。後續處理記於 `../run4/`。


本階段曾部署 **combined-fix4**，其三段元件存在已核對，但 59.94 外觀驗收無效；最新卡上版本與更新後畫面見 [run4](../run4/RESULTS.md)。本階段首次 QS 約 **6.12 秒，未解決**。測試後回到 LV_CINE_MEDIUM、非錄影待機，echo 與 GUI 診斷旗標均已還原。

## FPS 結果與實際成品

- `1910-20261015-fps-fix4-5994.jpg` 為 QS 更新前的舊原廠畫面，不能證明新版的完整文字或位置。
- 執行中樹快照 `fix4-fps-tree.json`：原 FrameRate 物件 926 的元件 3、8、9 均為 **drawText**，不是原廠 drawImage 回退。快照於 QS 開關回到 LV 後取得，三段元件仍在。
- `fix4-visual-comparison.json` 的像素比較取樣的是上述舊畫面；數值不能作為新版外觀驗收。元件樹存在也不能追溯證明較早照片已更新。
- 更新後 1911 可見 29.97／中尺寸 CINE LV 的新文字，字形偏窄、字距過大、缺描邊。其餘格率與四個版面只有離線驗證。
- 實際卡檔 230,016 B，SHA-256 `1584888ac0f52dc385cac77bd92d50bcf2362e5f68e3f12c8dc0368eba50fb4b`；整檔讀回相符。未帶使用者 CFG 的 builder 成品為 `536dcb46766f2d4b8940e14532893f604a959e4d838fba40b14bf0e43e5eab59`。
- CFG bytes 32..128 保留，SHA-256 `be62abbe2254b1c884c280a4352039f677bf7128bd81eea87dfb30990e855640`。部署／執行中 immutable code／來源雜湊見 `../deployment-combined-fix4.json`、`fix4-live-state.json`、`fix4-provenance.json`。

## 修正與未採用版本

1. 文字安裝器原 MAX_STRBASE=8 不足以返回 4 個選單＋29 個 LV 標籤，改成與同區塊 MAX_STRINGS=64 一致；與八個 CSV slots 分開。實際 C applier 與舊上限 mutation 已驗證。
2. fix1 只畫整數且 x=0；fix2 恢復原廠 X 曲線，仍缺小數與 FPS（1908）。
3. 確認 `reader+0x1c` 在 **成功註冊新資源**時也會被設為 1（C05E69AE..C05E69B4）。舊程式誤把它當作致命錯誤，提前停止同一替換記錄的後續解析。新回歸在舊版失敗（只解析第一段），移除判斷後通過；不清除原廠旗標。
4. fix3 保留新增子物件方案時整組 FPS 消失（1909），判定失敗。fix4 回到原物件、三個文字元件 3/8/9，保留原廠 X 曲線及完整解析；元件存在通過，外觀尚未符合原廠。
5. LV 記錄範圍外先拒絕，QS 不再掃描 LV 替換表；專用測試攔截所有表格讀取，371 筆 QS 均未讀該表。這項不代表總 QS 延遲已解決。

最終聚焦測試 6/6 通過（含四個原廠 LV parser），實際保存 BIN 加本卡 loader／AutoRun 的 371 筆 QS、16 筆 LV 替換（reader+1c=1）與關機 journal 還原通過。執行中樹快照另外 7 個合成案例通過，涵蓋無效／未對齊指標、缺物件、數量與深度界限、暫存器／堆疊保存。此快照唯讀樹，程式與結果使用命名 claim、完整讀回及 D/I publication，echo 最後還原。

`rejected-fix3-virtual-rcd` 是建置參數誤多帶一個 bootstrap row、被實際 BIN 驗證拒絕的候選，未寫卡；最終使用 plain 五格式。

## QS 量測

| 本次接回的卡之觀察 | 首次 QSON 回覆 | GUI Update | GUI Render |
|---|---:|---:|---:|
| RCUS 停用時 | 3.1554 s | 3055 ms | 98 ms |
| fix1 啟用 | 6.4730 s | 6375 ms | 95 ms |
| fix2 | 6.1219 s | — | — |
| fix3 | 6.1006 s | — | — |
| **fix4** | **6.1161 s** | **6015 ms** | **98 ms** |

每版僅一次重開後首次觀察；期間使用者有變更格率，停用／啟用資料不是嚴格控制所有設定的效能 A/B。數據不支持 QS 已改善。延遲仍集中在 Update；根因尚未確認。這張卡與更早 4.34／4.33／4.02 秒的卡不同，不能用那些數字與本表算改善比例。完整回覆及畫面確認在各 `*-profile/`、`../commands.jsonl`；未清 GUI 日誌，開啟後確認 QS，關閉後確認 LV，原診斷旗標已還原。計時不是 LCD 掃描或真人按鍵的機械時間。

## 卡片、連線與範圍

重新接回時發現 AutoRun 4666 B、LOADER 29276 B，與前張卡的 3561／8248 B 不同；`backup/manifest.json` 完整備份目前卡片。這張卡原 FSDS 停用 RCUS、沒有 RESCUS 目錄；五個標準 RCD 已加入，只移除 FSDS 的 RCUS 停用項，loader 程式與 envelope 未改。啟用後 loader SHA-256 `2535b983a03f12b54ca107bb9d59591506b928c60ee07835676020f261e311b3`，AutoRun 原件保留。

使用者明確表示沒有其他工作、授權接手 PID 38977。舊 daemon 只剩閒置 listener、socket 路徑已失聯；SIGTERM 因 accept 重啟未退出，核對 executable 與無 accepted client 後才終止確切 PID，未停止其他舊程序。首次空白／逾時後，PING 及後續 native 待機查詢恢復；沒有重送按鍵或不確定寫入。最終唯一使用的 socket owner 為 PID 40172，連線正常。

`fix4-module-status.json` 從已核對 SupManager 程式讀到十一個模組均 loaded／enabled、status=0、write_error=0。沒有錄影、刪除片段、發布、commit 或 push；240p 工作維持暫停。十輪實體電源／換卡與錄影驗收未做，不能由本次一次重開及離線還原推論通過。
