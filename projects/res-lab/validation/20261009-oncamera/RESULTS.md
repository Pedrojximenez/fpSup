# 2026-10-09 — Res Lab Virtual RCD v5 上機紀錄

> 後續狀態：使用者確認凍結後已實際重開。本輪公式修正版 v6 已完成兩組問題案例實錄、連續九份檔案讀回及待機確認，見 [公式排查與恢復紀錄](../20261009-formula-audit/RESULTS.md)。以下保留 v5 測試及當時事件的歷史狀態。


SIGMA fp Ver.5.02。Res Lab 與 res-custom 的獨立入口、記憶體配方、原生 Apply、返回管理頁，以及兩種尺寸的短片實錄已通過。
**最後的額外讀回核對遇到診斷工具快取錯誤，USB worker 無回應；尚待使用者實際重開後完成恢復與最後核對。**
這份紀錄將錄影證據、已完成的成品核對及未完成的恢復分開列出。

## 兩個獨立 Sup

| 卡上檔案 | Sup id／版本 | 大小 | SHA-256 |
|---|---|---:|---|
| `fpSup/32RESCUS.BIN` | `RCUS`／2，最低 service 3 | 73,344 B | `95247f2cff9094f78bd3a829293ad2bf6d5a849b73fdbd05c7b9182a0abca2cd` |
| `fpSup/50RESLAB.BIN` | `RLAB`／4，最低 service 3 | 451,296 B | `fbb17ce0e8156d09d13427e5e08cc6433589f7f15ef314e793b33a59df665ef6` |

兩份 BIN 已在各次寫入後完整讀回並逐位元組核對，見
[consumer](v4-installed-verification.json)、[producer](v5-installed-verification.json)。
最新 [plain 卡](../../cards/20261009-virtual-rcd-v5/plain/)與
[debug 卡](../../cards/20261009-virtual-rcd-v5/debug/)的產品 BIN 相同；兩張卡的 manifest 及所記錄來源雜湊均通過
[最後建置核對](final-build-verification.json)。

實機使用原有 AllSups 管理頁及 Loader service 4。只更新兩個產品 BIN 與五份既有 RCD 的格式版本，
沒有改寫原有 AutoRun、Loader 或其他 Sup。原始檔案及 Loader 的設定資料保存在
[backup-before](backup-before/)與[備份清單](backup-manifest.json)。
最終額外稽核僅完成 AutoRun 的新讀回；其他檔案的最後稽核仍未完成，不能以此宣稱整張卡最終核對通過。

Res Lab 以自己的 SupManager 項目提供 `Enable → Right / More Settings`。
res-custom 不提供 Res Lab 的設定入口。producer 只計算與產生共同 RCD1 v3 配方，
consumer 負責驗證、套用、格率限制與錄影。共同 Virtual RCD ABI 為 2。

## 實機操作與記憶體核對

1. 從 `MainB1 → FT_Y6 → FT_LIST`，在第二頁 Res Lab 項目開啟 `SL_LAB`。
2. 在 MODES 以完整原生按鍵脈衝選 M98，OUTPUT 顯示 3008×1996，按 OK 套用。
3. 原生 Apply 前後，producer 的輸出寬高、crop、ratio 均相同；consumer Custom 列同為 3008×1996。
4. 相同配方再按 OK，世代由 1 升至 2，pack 數保持 1、圖示用量保持 47,104 B。
5. MENU 返回 `FT_LIST → FT_Y6 → LV_CINE_MEDIUM`，短片啟動與停止均由 `is_recording` 實際觀察。
6. 重新開啟自己的 Res Lab 設定後，寬高仍是 3008×1996、OUTPUT 焦點正確。
7. 換成 M139，套用 2000×1334；世代升至 3，pack 數為 2、圖示用量 94,208 B。
   consumer 仍是同一個 Custom 列（row index 5／current 6），總列數保持 6。
8. 返回待機並完成第二段短片。

逐次證據：
[第一次 Apply](apply-v5-m98-first.json)、[相同配方重用](apply-v5-m98-repeat.json)、
[第二種尺寸](apply-v5-m139.json)。
實際相機截圖：[3008×1996 Applied](screenshots/1583-v5-m98-applied.jpg)、
[2000×1334 Applied](screenshots/1584-v5-m139-applied.jpg)。
兩個尺寸的 producer／consumer 一致性在原生 UI 回呼後核對，沒有從 USB 直接呼叫私有 Apply。

五份普通磁碟格式和 Custom 均成功安裝（`on=1`、`ui_result=1`），原生選單 slots 2 至 7。
沒有因註冊產生器或換模式增加新的解析度列。

## 實錄 DNG 證據

每段測試都先確認 CINE 待機及活動 provider，再用一次完整 MOVON／MOVOFF 脈衝啟動，
觀察錄影中，另一次完整脈衝停止，觀察待機。只列出 CINEMA 根目錄確認恰好新增一段，
沒有列出 clip 內部目錄、刪除片段或重播結果不明的錄影按鍵。

| 成品／模式 | 新片段 | 有效尺寸 `DefaultCropSize` | 完整 raster | 位深／格率 | 啟停 |
|---|---|---|---|---|---|
| v5／M98 | `A001_004` | 3008×1996 | 3024×2006 | 12-bit，30000/1001 | 通過 |
| v5／M139 | `A001_005` | 2000×1334 | 2016×1344 | 12-bit，30000/1001 | 通過 |

兩段的 `DefaultCropOrigin` 均為 (8,5)，Compression=1、WhiteLevel=4095。
完整 raster 包含邊界，驗收尺寸使用有效裁切尺寸。
[M98 證據](record-v5-m98.json)、[M139 證據](record-v5-m139.json)包含首幀路徑、主 IFD、
套用狀態及新增片段前後的證明；實際首幀標頭為
[A001_004](A001_004-first-frame-header.dng)與[A001_005](A001_005-first-frame-header.dng)。
只下載首幀標頭，沒有驗收整段所有影格或解碼後畫質。

早期 v4 的 `A001_003` 也有相同 M98 尺寸的成功實錄。
當時核對器錯把完整 raster 當成有效輸出，已依 DNG 的 DefaultCropSize 更正，
[原始紀錄](record-m98.json)保留此更正。

## 上機中修正的產品問題

- 設定入口需要同時送原生 application request 與 view-state event；SupManager 的按鈕由 Res Lab 自己註冊。
- 私有設定頁返回目標改為實際呼叫者 FT_LIST。只返回 B2_5 會遇到未初始化的原生錄影設定焦點。
- 移除虛擬列對 stock Help action 的變更。先前第一列安裝後，後續列的原生 guard 會不匹配；
  現在五份普通格式與 Custom 均能連續安裝，stock Help 與格率 variants 保留。
- Custom 原生列未就緒時 Apply 明確拒絕，避免顯示 Applied 卻沒有啟用列。
- Apply 命令碼與原生按鈕值分開：`SL_O_Key` 負責命令，`SL_E_Button` 負責按鈕值。
  v4 套用後畫面幾何多變動一步，但已提交配方及 DNG 正確；v5 已在實機核對套用前後幾何不再變動。

## RCD 相容與離線測試

原卡五份 RCD1 v2 均先完整備份，再由正式 builder 根據解碼內容重建為 RCD1 v3，
不是直接更改版本欄位。五份 v3 都在部署時完整讀回核對。
見 [重建清單](rcd-v3/verification.json)、[部署核對](v2-installed-verification.json)。
原名稱仍是 S16、OG2K、OG3K、OG4K、OG35K；沒有產生 LABnnn.RCD。

最新 [24 項回歸](v5-full-tests.log)全部通過（452.500 s）：21 項 Virtual RCD 與 3 項 Native UI。
涵蓋真正的產出 ARM 安裝器／回呼、共同 registry 可超過兩個 provider、單一列更新、
圖示不可變與重用、錄影 busy、兩階段 busy／配置失敗、記憶體預算、校驗錯誤、
不合法幾何／RAW14／格率／格式拒絕、遺失 consumer、設定入口與拒絕、RAM 配方不從列名恢復，以及 journal 還原。
原生 UI 測試連續安裝六列並對照 reference，核對格率 variants、私有狀態機返回及 Apply 按鈕綁定。
這些是離線測試，不等同於全部模式已完成實錄。

## USB 與最後讀回工具事件

部署期間使用者曾實際重開相機，造成 USB 消失；使用者明確回覆「剛重開」。
該次不能記為產品崩潰。各次開機的 ACCESS 錯誤均先檢查實際 interface owner，
只釋放已確認占用 SIGMA 介面的 ptpcamerad，再使用既有測試 daemon。

兩段 v5 實錄完成後，額外 `final_audit.py` 在同一 Python 程序連續讀檔。
第一份 AutoRun 完成且完全相同；第二份 Loader 已讀入 27,668 B，
在呼叫釋放緩衝區時 echo 逾時，還原 echo slot 及後續 getter 也逾時。
USB 介面仍由已知 fpshd PID 70672 持有。
[事件日誌](final-audit.log)及[中止前狀態](final-audit.json)保留。

已定位的工具缺陷：`getfile` 與 `callfn` 共用 CODE 執行區；`callfn` 的程序內 `_loaded` 快取
只記錄曾載入，無法察覺後續 `getfile` 覆寫。第二次釋放呼叫可用 callfn 參數執行到 getfile 程式。
`callfn.py` 已改為每次呼叫先寫入並核對自己的程式。
[兩項離線回歸](shared-callfn-tests.log)包含一次 getfile 覆寫後再呼叫的情況，
以及故意省略第二次載入、確實重現舊錯誤的 mutation。
相機失去回應後沒有再次 echo、重播 free、覆寫在途 CODE／參數或繼續卡片操作。
此診斷工具問題與產品的兩段成功實錄證據分開；實際恢復仍待確認。

## 本次驗證邊界

- 配方與 Res Lab 參數仍只存在本次開機的 RAM；關機後須重新設定／Apply。
- 實錄只驗證 M98、M139 在 CinemaDNG 12-bit／29.97p 的短片。未驗證其餘模式、其他格率、8／10-bit、長時間錄影或完整影像品質。
- RAW14 尚未接入 consumer，Julien style 尚未實作。共同 ABI 可供後續產生器沿用。
- 未完成十次實際電源暖開機；native reboot 與使用者個別重開不冒充該項驗收。
- 最後可觀察的產品狀態為 M139 2000×1334、CINE 待機、Custom 活動、世代 3。
  診斷事件後的即時狀態與最後卡片稽核尚待實際重開及恢復確認。
