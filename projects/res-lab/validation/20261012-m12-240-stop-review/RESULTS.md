# 新版緩存規則下的 M12240 秒停檢查 — 2026-10-12

**已確認新版規則生效，但秒停仍發生在完成通知尚未及時回收描述子的情況下。**
最新 SSD 日誌為94／94、vbuf；本輪同模式 SD 普通短錄和原生 DEBUG 診斷各為104／104、vbuf。
診斷段停止之前已有15張完成通知，MRecMgr只處理10張，另5張仍在等待；104張到達減10張回收，
恰好達到原廠94張在途上限。不是停止後資源未釋放，也不是新版批次判斷完全沒有執行。
本輪沒有修改或部署產品 BIN，持續240p仍未修復。

## 實機身份與最新 SSD 證據

沿用 dido 所有的 fpshd14207／3.2.0／同一socket，每次操作持有 `/tmp/fp-af-fusion.lock`。
首次 getter 發生 NO_DEVICE 時停止；主機重新列出 SIGMA fp 後，同一 daemon 從closed重新開啟，
重新讀取待機狀態，沒有重播按鍵、沒有重開機或另起服務。

`current-before-reconnected.json` 保存既有 SSD 試錄：

- 原生日誌時間2026/10/12 08:20:41，volume slot5、1907GB、exFAT、5000Mbps。
  `req_cnt=94, fin_cnt=94, vbuf/94/534172, raw1`。
- 当前M12240、mode231 donor12、p13 base6、RAW1008×672、crop992×662、12-bit、239.76p，
  Lossless原生選單為ON，producer facts格率240000/1001。
- consumer19完整53,912 B immutable C body相符；新版LOSS完整38,588 B immutable C body也相符
  已部署獨立版本。LOSS code SHA256為`12ca7ef58d74b979d9fd8567a33387cb3c116b2b738377e32d614af8c0f716f1`。
  使用精確建置的 `layout.json`，先驗證owned record、base、state及blob長度，再讀scalar欄位。
- STOPFX `C0377118=EA000160`，新版批次hook `C063F828=BC4EF0EE`。
- 新策略`enabled=1`、`checks=94`、`count_flushes=2`、`pressure_flushes=23`，
  最終`frame_limit=29`、`latency_us=130666`。因此這段確實使用新規則。
- 全94張API交付皆為RAW，compressed0、writer非零返回94、failed_returns0；
  兩條codec lane的stall與fault皆0。93個編碼工作被拒絕並回到RAW，沒有藉壓縮降低輸出資料量。
- 停後descriptor96/96、registry0、movie／XMP／writer busy皆0。

源码確實只在LOSS take admitted後啟用策略；OFF會保持原廠判斷。
最初提出的「該段也許沒有用到新規則」假設，已被上述實機數據排除。
各次手動SSD片段之間是否改模式或重開機仍需使用者補充；此處不把舊590張SSD檔案的錯位統計
當成新版規則下的檔案結果。本輪SSD原檔尚未接回主機重新核對。

## 本輪 SD 重現

保持實際已選M12240／239.76p／12-bit／LOSS ON，未改選單或幾何、未關gyro、未更換載入器。
每段開始前驗證兩個完整immutable C body、正確活動配方、96/96 descriptor、registry0及三項busy0，
取得原生LCD綠STBY。各一對MOVON／MOVOFF啟動，2秒期間不查USB；目標時均已REC0，沒有再送停止。
收尾後重新驗證同一模式、資源及LCDSTBY。片段原檔保留，沒有列舉clip子目錄或刪片。

| 試錄 | 片段 | req／fin | 結果 | 最終每批上限 | count／pressure結算 | 停後位置 |
|---|---|---:|---|---:|---:|---:|
| 普通版、原生WARNING紀錄 | A001_116 |104／104|自動vbuf／raw1|20|2／36|96／96|
| 同BIN、原生DEBUG診斷 | A001_117 |104／104|自動vbuf／raw1|20|2／33|96／96|

两段各104 RAW／0 compressed，codec stall0、failed writer return0、registry0。
普通段最慢writer返回204.411ms，診斷段206.135ms。這是API返回等待，不等於媒體完成或RAW回收等待。
`bulk-size=64MiB`日誌欄仍保留原廠容量值，不能據此認定提早結算沒有生效。

證據在兩段的 `trial.json`、`native-before.json`、`native-after.json`與LCD截圖。
這些計數不是所有DNG逐張解碼的宣稱。

## 原生事件的直接證據

使用既有Logger與已核對的T_LOGGERMEMORY ABI，未安裝ARM probe或新hook。
先凍結並保存兩組舊256筆環，再由原廠 `log expand`配置各4096筆診斷環，
僅啟用RECMGR／RECMGR2的DEBUG。在待機後凍結、以每次64 words完整讀取，
驗證讀前／後descriptor與cursor相同；未使用已截斷的console輸出做時序分析。

- RECMGR1861筆、RECMGR2 1282筆，兩環overwrite0，原始BIN及JSON全部保留。
- Logger已還原原來的256筆環與完全相同8個設定字，
  `logger-before.json`與`logger-restored.json`逐位元組相同。
- `native-lifecycle-analysis.json`以slot、RAW位址及各次event5世代配對104張。
  每張event8／9、writer返回、完成及歸還分支皆唯一配對。

| 事件 | 全段數量 | vbuf之前數量 |
|---|---:|---:|
| 開始準備檔頭（event5） |104|89|
| writer進入／I/O前 |104|16|
| 完成回呼及event9發出 |104|15|
| 管理工作處理event9 |104|10|
| 這些影格進入RAW歸還／描述子釋放 |104|10|

全段另有一筆收尾釋放，因此未按世代篩選的release總數是105；表中為104張配對影格。
通知發出15、處理10的差額5，直接證實停止時尚有已完成影格等待管理工作回收。
prepare、event8處理、event9處理均由同一thread45執行；writer為thread61。
原生FIFO契約已由先前原廠機器碼核對，不是只凭thread號推測。

首張（slot58、RAW53D33000），以下相對本輪診斷ring origin：

| 時間／區間 | 原生事件 |
|---|---|
|801.566ms|writer進入|
|802.096ms|writer返回：僅0.530ms，尚未完成媒體批次|
|1112.517ms|完成回呼：距writer進入310.951ms|
|1112.521ms|event9發出|
|1162.216ms|event9處理：通知等待49.695ms，期間又準備11張檔頭|
|1162.613ms|RAW歸還分支：距writer進入361.047ms|
|1205.264ms|vbuf：94張在途位置用滿|

停止前15筆完成通知等待約49.7–72.0ms；首16筆event8的等待中位約41.3ms。
因此不只是最後一個free呼叫慢，下一張交給writer也受到同一工作中其他事件的等待影響。
沒有事件池配置不足警告；此trace的通知最終皆被處理，不是永遠遺失。

全部104張檔頭準備區間中位4.4315ms；其中檔頭複製區間中位2.8505ms。
239.76p每幀預算約4.1708ms。**DEBUG會改變排程，區間亦包含被其他工作打斷的時間，
不能把這些數字直接視為普通模式的CPU函式成本或唯一退化根因。**
普通段同樣104幀vbuf支持重現，但仍需以較低擾動方式量普通模式成本。

## 為何調批次仍秒停

新策略確實讓未滿64MiB的批次提早送出；它沒有改变MRecMgr中event5／8／9共享FIFO的處理方式。
回呼發出並不立即歸還RAW：已完成影格仍須等同一管理工作處理event9。
本輪在停止邊界已完成但等待回收的5張，證明單純再調批次門檻不足以涵蓋這個問題。

另一個需要改進的觀察量是 `fpl_card_written`，目前以C069ADE0的API返回時間更新latency。
首張0.530ms返回、310.951ms才完成、361.047ms才進入RAW歸還，是三個不同的生命週期時點。
兩批餘裕與FPS保留量是有效保護，但不能把返回時間當作整個寫出／通知／回收等待的實測值。

STOPFX負責停止後原廠清理路徑，這輪資源每次回到96/96；它不解決錄影中的回收排程。
下一項修復應針對檔頭準備耗時、event8／9處理延遲及真實回收等待。
不能直接提前釋放仍被writer／SSD引用的RAW，也不能只擴大池子掩蓋延遲。

## 驗證與範圍

- 現行 `test_bulk_policy` 12項離線C策略測試通過，包括兩批預算、當前檔案計數、壓力、混合RAW與mutations。
- 本輪讀取實機、原生LCD截图及上述兩段錄影；未改產品source／BIN、未寫更新卡、未重開機，未commit／push／發布。
- 最新SSD日誌已保存；完整SSD事件與新版SSD DNG完整性尚未取得，SD診斷不能冒充SSD trace。
- 已把相機留在本輪M12240／239.76p／12-bit／LOSS ON、CINE待機，三項busy0、descriptor96/96、registry0，
  原生Logger設定完整還原。
