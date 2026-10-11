# AF 開發資料平台：多接點 hook 與 USB 持續觀測

更新：2026-09-27。**P0 第一優先是把 AF 開發所需資料持續送回電腦，降低每次實驗的設定、讀取與整理成本。** 目標工作流為一次啟動受限 session，接收有序的小批次，自動保存來源與缺失，停止後產生可重播報告。正常產品的估計、判斷與鏡頭控制仍全部在機內；電腦只是開發觀測、校準及分析端。

本頁是最新平台計畫，取代舊文件把 EP83 列為可有可無「開發支線」的優先序。既有有限批次設計保留為第一個可驗收增量；不把每次重啟、重裝、等滿大緩衝再讀回定為最終操作方式。AF 演算法工作與依賴仍見 [完整計畫](../PLAN.md)。

## 現有能力與三個整合缺口

- 五個來源已有指定 ROM／ABI 候選：AF terminal、native-L final event、face publication、AAT color Run 與背景 H/L。四路 observer 是 256-byte finite record，H/L 是另一套 128-byte record，尚未有共同可循環串流格式。[接點清單](AF_STREAM_HOOK_CATALOG_2026-09-27.md)
- sender／receiver、camera binding、control、memory 與 host owner 有離線原型及測試。**camera binding 目前呼叫 `af_ep83_camera_make_synthetic`，host 還要求 `camera_state=SYNT`；沒有真實 hook 資料的 EP83 實收或連續串流證據。** 歷史 Start 成功與 CINE shell 唯讀資料不等於 EP83 byte delivery。
- 現有協定跨五層 single-use：sender 的 fresh result、camera private phase／nonce consume、camera control persistent phase、host session sequence/trigger、host LibusbOwner 的 claim/descriptor/trigger/terminal 使用。不能靠 host while-loop、新建 Python 物件或清零狀態變成連續 session；上一批 EP83 DMA **及 EP82 terminal** 完成都需明確交接。
- **載入與記憶體：** guarded loader 仍鎖舊來源 hash；現行共用 loader 的 64 KiB staging 返回前釋放，payload 要自己保留常駐配置。highrate memory/camera binding 沿用 `C3757A7C` 的舊 1 MiB pool 假設；現行 shell worker 改為 `C072F050/F054/F058` 發布自己的 pool/code。更新 hash 或換一個 pointer 不會取得 AF lease。
- **host／camera owner：** fpshd 現行 EP01/EP82 shell 路徑沒有 EP83 consumer／AF83 CMD4；專用 LibusbOwner 拒絕已有 `/tmp/fpshd.sock`，不能同時 claim interface 0。相機端也不能讓文字 shell worker 與 native mode-5 CMD4 adapter 競爭同一 control path。優先整合維護中的單一 host owner，並明確選定相機控制 owner。
- **endpoint：** native PTP event sender 與新 sender 共用 EP83／TRB；descriptor bulk patch 不代表 controller mode、native admission、enumeration/reset/teardown 已解。直接 RTOS wait 候選避開舊 WaitIn 的 EP01 rearm 副作用，仍不等於 ownership 完成。

精確程式對照與歷史來源差異見 [transport gap](AF_STREAM_TRANSPORT_GAP_2026-09-27.md)。這些是具體工程工作，不以新增 retry、固定 sleep 或取消 guards 取代。

## 平台資料路徑與最低契約

```text
原廠多個 producer
  → 每來源有界 copy/commit + sequence/loss
  → 有限 bank/queue（明確 producer/consumer ownership）
  → 獨立 task 封包、CRC、DMA publish
  → 相機端單一 USB owner → EP83
  → 同一 host owner 接收、有限落檔隊列
  → 原始二進位 + session manifest + 可重播分析
```

控制通道負責 start/status/stop 與 terminal，不逐筆輪詢 AF RAM。hook 不做 USB、等待、配置或檔案工作，原廠 AF 不等待電腦。沒有可用 bank 時按既定規則略過額外觀測並記缺失，不覆寫 producer／DMA／consumer 持有的資料。

session nonce、batch sequence、source observed/committed sequence 分開；封包有 schema/source ID、payload 長度、完整性與 loss 統計。timer/count 門檻可封送已 commit 的短批次，低頻來源不必等滿容量。這需要新格式及 ownership 契約，不能改現有 finite header 後當作已相容。

事件按 [catalog](AF_STREAM_HOOK_CATALOG_2026-09-27.md) 分級：T0 保存 request／decision／實際 ROI／mode／target lifecycle／lens begin-end 等轉移；T1 保存 compact H/L 與 subject；T2 才做較大 history／model 明細。T0 不固定抽掉，每次調整 T1/T2 decimation 都記配置與略過數。現有 sticky loss 不冒充精確丟樣率。

共同機內 CPU 時鐘、wrap/reset 與 generation 關聯另驗。完成前可交付分來源有序 raw stream，不能依 USB 抵達順序輸出跨 task 因果、AF latency 或曝光同步；錄影時間、sensor exposure 與 hook CPU 時间分開。

## 分階段交付與退出條件

下面是上線驗收順序。共同時鐘、multi-bank ownership、host service／camera owner 整合可從第一階段並行設計；不必等前一個實機 trial 結束才開始查下一個工程缺口。各阶段對應一次具體證據交付，全部目前待完成。

| 階段 | 最小交付 | 通過所需證據 |
|---|---|---|
| P0-A：有限合成資料 | 選定現行共用 loader／常駐 lease 與唯一收發 owner；一個有界合成 batch，hook 尚不接入 | 實際收到完整 bytes，descriptor／nonce／長度／CRC／EP83 completion／EP82 terminal 一致，保留原資料與收尾證據。mock、Start return、唯讀 context 均不能通過此項 |
| P0-B：真資料單 source | 一個已核對 native producer，先有限記錄與封批；producer copy 和 task sender 分離 | 正確 decoder 可讀真實 raw payload；native identity／原 callee 效果、commit／缺失、成本、停止／detach 可核對；source 不可達要明列。單一來源可先驗交付，不冒充跨來源 timeline |
| P0-C：真資料多 source | 四路 observer 加 H/L 分 schema 接入，各來源 sequence、T0 缺口／source mask 可見 | 不同 payload 不互解；並行 producer 不共用未同步索引；亂序、缺失、未初始化、inactive 都可區分。common clock 與關聯通過才另授予 causal timeline 資格 |
| P0-D：受限 session 連續小批次 | 一次 start，有限 credits／總時間／總量，bank 可連續填寫及交接；五層 single-use 改為明確逐批狀態機 | 同 session 多批，不重裝、不逐批重啟；確認 EP83 與 EP82 完成後才回收相應 bank。量慢讀、host 退出／拔線、CRC/長度錯誤、terminal 遺失、stop/fault；未知 DMA 不回收／重送，producer quiescence 前不卸載 |
| P0-E：錄影負載與自動分析 | CINE 待機與實際錄影分組，完整 session 自動出 manifest／來源覆蓋／缺失／成本／已驗關聯摘要 | 驗原廠 AF、畫面／錄影穩定性、控制通道公平性、USB 故障下原廠進展；只在具備時間資格時報 latency。host 分析可重跑、保留原始失敗，不用結果挑成功片段 |

P0-A 的最初實收可用單批隔離 USB 問題，P0-D 才是降低日常實驗成本的主要交付。有限 bank、有限 session 並不等於整段資料都等到最後一次回傳；原廠 producer 產生資料時 sender 逐批持續送出。

## 每階段都要保留的失敗處理

1. 新版 launcher 依 [SUP_BUILD_RULES](../../../fpSup/SUP_BUILD_RULES.md) 使用維護中的 loader／stage2／entry／journal，entry 返回；code/state/records/DMA 的生命週期分開，不借用 shell pool 或未知 cave。
2. batch start／completion／terminal 任一結果不明，session fault 並保留不確定資源；不用自動重試、新 nonce、EndTransfer、clear-halt、global reset 或相機重啟把它包成成功。
3. 觀測故障不新增 S1、REC 或鏡頭命令。stop intake、停止 sender 與卸載 hook 是不同階段；host 關閉不等於 producer／DMA 已退出。
4. 每來源報 eligible、committed、decimated、full drop、contention、guard rejection；無法精確計的項目保持未知／sticky。transport gap、source drop、inactive source 與解碼失敗分開。
5. 原始 binary、工具／韌體 hash、source mask、session/batch 身分、context、receipt 與 terminal 保存後再產生衍生 JSON／圖表；不改寫歷史 captures 或 checksum。

## 自動分析與實驗成本驗收

每個 session 自動產生：來源啟用／可達覆蓋、收送筆數與缺失、bank 水位／等待、原始 AF request/state/ROI/result、lens request/end、face/AAT init/update/lost，以及仍無法關聯的事件原因。資料不足時報 unknown，不能自動把 native success、缓存位置或固定框升格為光學成功／幾何尺度。

平台成功先看可重跑性與成本：一次開始能連續收資料、停止可核對、原始資料不散失、同一分析可重建結果；再比較每次實驗的人工步驟、啟動到首批時間、保存／分析時間及中斷恢復負擔。先量基線再設定數值門檻，不預設已達速率或時間改善。最終 AF 光學品質仍由 [M4 錄影 A/B](../PLAN.md) 獨立驗收。

平台真資料可用後，M1 的 CINE 來源／時序、M1-S 的 face／AAT lifecycle、M1-F 的合焦配對會共同消費這條資料鏈。逆向、schema、合成反例與離線算法可並行；新動態控制結論不得跨過所需資料與光學驗收。DFD 仍是可選增量，PDAF 仍依有界新證據推進。

本次僅規劃與文件整合，沒有改 recorder／sender／loader／USB 程式、沒有相機操作，也没有新增串流實測結果。
