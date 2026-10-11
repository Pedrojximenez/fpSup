# fp AF Assist

**產品目標：CINE 錄影時的機內連續自動對焦。開發第一優先：多接點 hook＋USB 持續資料平台。**

先降低每次 AF 實驗的設定、資料擷取、回傳與分析成本：一次開始受限 session，持續收有序小批次，自動保存與重播。正常對焦的估計、判斷與鏡頭控制仍在機內；電腦即時 AF 控制原型維持擱置。

- [完整開發方向與待辦](PLAN.md)：P0 平台先行，其後 CINE 來源、AAT、幾何／CDAF 與錄影驗收。
- [第一個 AF hook／高速通道增量](notes/AF_FIRST_HOOK_CHANNEL_2026-09-27.md)：同 daemon EP83 host、有限 H/L probe 已有離線實作；相機離線，關機還原尚未閉合，live 預設封閉。
- [資料平台階段計畫](notes/AF_TELEMETRY_PLATFORM_PLAN_2026-09-27.md)：有限合成 → 真資料單源 → 多源 → 受限 session 連續批次／owner 回收 → 錄影負載與自動分析。
- [hook 事件清單](notes/AF_STREAM_HOOK_CATALOG_2026-09-27.md)／[USB 整合缺口](notes/AF_STREAM_TRANSPORT_GAP_2026-09-27.md)：已核對來源、待補因果事件與工程阻擋。
- [全部筆記索引](notes/README.md)／[接手入口](CONTINUE_HERE.md)。
- [最新 CINE 半按實測](notes/FP_CINE_BASELINE_2026-09-27.md)：六筆完整原生 shell 觀測，釋放／設定核對通過；AAT 未啟動，沒有錄影追焦或 EP83 串流效果結論。

**目前沒有可用的多來源持續串流。** 五個 recorder 來源有離線候選，但 camera binding 仍產生 synthetic、host 要求 `SYNT`；sender／camera／control／host session／host owner 的五層 single-use 尚未改成逐批狀態。舊 pool／loader 配置與現行 shell worker 不相容，專用 libusb owner 又與 fpshd 互斥；單一 owner、常駐 lease、真實收發與回收仍待閉合。完整細節以新平台計畫為準，歷史離線測試不升格為相機實收。

產品主線保留：原廠 CDAF 首次合焦 → 同主體錨點 → face／AAT 共用幾何方向 → 原廠 CDAF 確認；AAT-only 可以獨立改善，DFD 通過額外資訊與光學驗收後再加入。PDAF 仍無 fp 可用資料源；Z CAM 作程式參照，不作連續 AF 性能標竿。[算法階段規劃](notes/FP_AF_FIRMWARE_ROADMAP_2026-09-27.md)、[歷史盤點](notes/FP_AF_DEVELOPMENT_STATUS_2026-09-27.md)。

## 歷史 host 原型：以下保留原操作與試驗紀錄

以下「未錄影／AF-S／不改韌體」是 9/16 舊原型的限定，不是目前產品範圍或可直接重跑的現行部署方案；舊 RAM lease 不沿用到新平台。

SIGMA fp Ver.5.02 的單框、小範圍、實驗性對比對焦工具。**不是 PDAF，也不是已校準的 DFD。**
不改韌體／SD 卡／曝光或對焦框設定，不支援錄影追焦。

目前為 **0.1.0-pre1 開發原型**。20-pulse 控制、原生停止／完成流程與靜止 H 取樣已通過實機試驗；
完整 H-based 對焦流程尚未通過。新版相機端固定取樣與動作前取消已通過；後續整合完成四次
受限小步，但因傳輸短回覆仍反覆出現而人工取消，未完成最終確認。RAM／echo／設定已還原，
鏡頭最後停在 10807（起點10707）。不把部分試驗或離線展示當成可用實機版本。

9/16 的 [相機端 hook＋EP83 高速批次](highrate/README.md) 為現在 P0 平台的離線基礎；
其有限單批契約保留，連續 session、現行 owner 與實收驗證依最新平台計畫補齊。

## 操作

需要相機已有正常 USB shell；本程式不安裝卡片、不啟動 daemon、不搶占其他程式。
相機需未錄影、AF-S、單一對焦框，測試時保持場景與相機固定，不碰模式、快門或鏡頭。
沿用目前 ROI；單一 area 0 不是「畫面中心」的同義詞。

離線展示（沒有相機動作）：

```sh
python3 fp_af_assist.py --demo
```

打開程式印出的本機網址。展示跑的是真正受限搜尋演算法，但光學／鏡頭數值是模擬。
每次開始需手動勾選；原廠 AF 是獨立選項，不會在失敗後自動發動。

只檢查組譯，不連相機：

```sh
python3 fp_af_assist.py --inspect
```

經授權的只讀 native getter 驗證（會暫借 RAM、結束精確還原，不是零寫入）：

```sh
python3 fp_af_assist.py --probe --output captures/new-read-probe
```

`validate_motion.py` 是授權研究用的 20-pulse 控制驗證，不是一般操作入口。
`sample_probe.py --output NEWDIR` 只測 H 取樣，仍需暫借 RAM，不移動鏡頭。
`validate_assist.py --authorized-small-step-validation --output NEWDIR` 是完整受限流程的
**實驗室驗證入口，目前不建議重跑**，需先處理 USB 短回覆；不是已驗收的使用者版本。
`recover_upload.py` 只適用於**從未啟用 echo、從未執行 RAM handler** 的中斷載入，
而且每個當前字組必須吻合原值或此次載入值；不是任意覆寫其他工具的復原器。

## 搜尋與停止界線

- 一輪以開始位置為中心，最多 ±100 pulses；每步最多 100，最多 12 次請求（含正常返回）。
- 使用完成後、檢查 scheduler 進展的 H 標量；H/L 不是相位偵測的左右半像素。
- 一筆觀察最多 8 秒，至少等待 150 ms、觀察排程進展並取得三筆穩定樣本。
  現行 sampler 使用同次 camera-side phase/H/L/phase copy，全部 host 交換間隔至少 5 ms。
  舊四讀 burst 僅留作唯讀傳輸診斷；新 copy 仍不代表曝光同步或中斷原子性。
  這是慢速研究原型，尚無快於原廠 AF 的證據。
- 至少 3% 對比改善才改選位置；曲線合理時才試三點峰值提案，最後重新量測。
- Gain、ROI、曝光、producer、capture state 或位置不一致即停止，不自動回原位或改用原廠 AF。
- 本輪只要出現傳輸／回覆格式異常，即鎖住後續位移與新的原廠 AF 啟動；即使只讀重試成功也不解鎖。
  完成檢查、已擁有動作的一次停止及核對還原仍可進行，但不繞過 uncertain-execution quarantine。
- 「停止」是取消後續動作並嘗試原生 abort／完成確認，不是獨立硬體緊急停止。
  USB 中斷、原生函式等待或使用者改變 capture 狀態，都可能妨礙停止請求。
- 完成旗標與 cached position 不是獨立光學真值；不得把「contrast confirmed」解讀為保證合焦。
- 原廠 AF 按鈕可能做超過 ±100 的原生掃描，需另行明確選用；不拍照、不錄影。

## 記錄與已知限制

每輪保存 `events.jsonl`、`result.json`；失敗鎖定後先檢查紀錄，不能以重按啟動消除不確定狀態。
結果另記 `transport_faulted` 與 `transport_anomaly_count`；收尾中才出現的異常也會令工作標為 fault。
這是軟體防護，不是 USB 修復或跨程式重啟的持久鎖；不可靠重開程式繼續未診斷的硬體試驗。
RAM lease 為 echo `C0BAC2F8` 與 `C072F700..C072F9FF`；控制程式 504 bytes，固定取樣程式 152 bytes。
正常結束保存的 192 個 RAM 字組、echo 和四個對焦設定均讀回核對。
若無法確認執行已結束或 ownership，保留程式／參數供診斷，不假稱已完全還原。

[本次實測與中斷還原](notes/VALIDATION_2026-09-16.md)。
[本機診斷版與 PTP 短回覆證據](notes/TRANSPORT_AUDIT_2026-09-16.md)。
[歷史 producer hook 取樣方案](notes/HOOK_SAMPLING_PLAN_2026-09-16.md)；目前下一步以 [P0 平台計畫](notes/AF_TELEMETRY_PLATFORM_PLAN_2026-09-27.md) 為準。
相機通用事實按目錄規則放在：

- [native control 稽核](notes/research/FP_NATIVE_FOCUS_CONTROL_2026-09-16.md)
- [統計新鮮度稽核](notes/research/FP_AF_STATS_FRESHNESS_2026-09-16.md)
- [capture 欄位更正](notes/research/FP_AF_CAPTURE_GUARD_CORRECTION_2026-09-16.md)

只讀 bridge 與一次小位移／停止通過，不證明所有鏡頭、場景、光線或模式都支援。
沒有速度勝過原廠 AF 的測量，也沒有跨鏡頭 DFD 校準。
