# RAW Live：SIGMA fp 的 RAW 即時監看還原

`projects/rawlive` 用於實作與驗證從 RAW 來源到 LCD 的即時顯影。研究證據與截斷問題分析集中於 [`research/liveview`](../../research/liveview/README.md)，相機端工具與 fp 快照見 [`projects/rawview`](../rawview/README.md)。

目前狀態：**研究與驗證方案已整理，尚未完成 prototype，尚未確認可用的 RAW 監看來源、實際第一個截斷位置或即時處理效能。**

## 目標與邊界

讓來源 RAW 仍有差異的高光與飽和色，在 LCD 上保留可辨階調及平滑色相變化；正常曝光的灰階與色彩則依可驗證的顯影與顯示轉換還原。

- RAW 是輸入依據；已經剪平的 YUV／RGB 預覽不能當成 RAW，也不能靠末端曲線恢復失去的差異。
- 來源已飽和的通道無法保證恢復正確色彩，需區分來源飽和與監看處理造成的截斷。
- 超出 LCD 亮度或色域的訊號需平滑映射；目標不是讓有限顯示碼值逐一呈現所有 RAW code。
- Identity／linear tone 用於定位問題。最終觀看仍需正確的高光、色域與顯示編碼。
- 第一版限定一種經確認的 RAW 模式與 LCD 路由；擴充模式以前，先證明監看修改與 RAW 採集／錄製隔離。

## 預定處理流程

```text
經證明的 RAW／線性監看來源
  → 黑位校正、線性增益、白平衡與去馬賽克
  → 相機色彩校準與工作色域轉換（保留高光餘量及必要的負值）
  → 平滑高光映射與顯示色域壓縮
  → LCD 顯示曲線、正確訊號範圍與輸出轉換
  → LCD 白點／灰階校正與面板
```

這是設計需求，還不是已確認的 fp 硬體處理順序。白平衡、矩陣與各級限幅的位置必須逐一核實；共同縮小正值並不能解決矩陣後負值被裁切的問題。面板色準需量測實體 LCD，不能以電腦顯示截圖代替。

優先評估原生 ISP、RAWBLT、tone／matrix 與顯示端可否完成所需流程，再決定需要新增哪些處理。**不預設 CPU 能對全解析 RAW 即時顯影**；降採樣、緩衝、記憶體頻寬與可用處理時間都要由量測決定。

## 實作階段與完成條件

### 1. 證明來源與原生硬體可行性

2026-09-24 更新：優先沿 **liveview／small_raw 的 bin／vbin 分支**定位可用來源。[上游追查](../../research/liveview/upstream-clip-audit.md) 已核到獨立 preview／record 設定；部分 UHD template 為 preview3×3，但既有待機為1×1。必須依實際 sensor enum、profile 與待機／錄影狀態判定，不能將錄製 `CrctVbinToBufA` 抽頭直接當成 LCD RAW 來源。

- 同步保存 preview／record bins與zoom、main／sub reduction record、來源descriptor／幀序號、packing與gain state；先找來源是否已平台。
- 原生 `C032EFA8` 只縮放第一組矩陣的三項及第二組全部九項；採用前須驗證對所有顏色的效果，不能預設為保色的共同衰減。

- 確認候選來源的格式、位深、黑白位準、幾何、更新時機及緩衝區生命週期，區分 RAW、線性 RGB 與已處理預覽。
- 建立監看來源與錄製 RAW 的對應；兩者可能使用不同 readout，不能僅以錄製 RAW 未爆推定監看來源也未爆。
- 追查活動 gain／matrix／tone context、當幀表內容及 LCD 路由，定位第一個像素差異消失的位置。
- 以來源漸層與飽和色證明可保留餘量，列出原生硬體可完成及尚缺的處理，再選定 prototype 路線。

### 2. 建立離線顯影參考

- 對已確認格式的樣本建立黑位、白平衡、色彩校準、高光與色域映射的可重算參考。
- 固定光源、曝光、ISO 與手動白平衡，包含灰階、高光漸層、色卡及高飽和紅／藍／洋紅。
- 量化平台區段、色相變化與中性灰偏移；先定義可接受誤差，保留各處理階段的數值以便定位差異。

BMCC 6K 已補入 [Gen 5／Rec.709／33³ LUT 離線對照](../../bmcc6k/notes/FP_LIVEVIEW_COMPARISON.md)。它可提供高光與跨通道映射的可重算參考；使用前須先以 fp 自身校準建立正確工作色域和 Film 輸入，不直接移植 Blackmagic 校準矩陣、ISO 曲線或硬體封裝。

### 3. 監看隔離與實機 prototype

- 在已確認的監看 context 上實作最小改動，驗證活動表、更新排程、緩衝區所有權與 cache／DMA 一致性。
- 不直接沿用舊實驗的 `C3414DA8` 作為私人曲線記憶體；原廠另一 context 會使用該區域。
- 對照原廠、舊 stretched ID83、真正 identity 診斷與限幅前共同衰減，依證據逐步加入顯示映射。
- 確認 RAW／錄製資料及 metadata、AF／AE、overlay、模式切換與恢復行為沒有非預期變化。
- 核實影像擷取點；既有 `display capture` 取得的是 OSD，不能作為完整 live image 的證據。

### 4. 效能與顯示驗證

- 量測幀率、端到端延遲、掉幀、記憶體頻寬與處理負載，再決定解析度與品質取捨。
- 確認長時間運作、模式切換、待機／錄影均穩定；通過後才擴到其他 ISO、WB、模式及 HDMI 路由。
- 來源保有差異時，監看不出現不必要的大段平台；飽和色隨曝光增加平滑過渡。
- 以實體面板量測完成白點、灰階與色彩校準，並記錄適用的亮度設定及環境。

## 研究依據

- [rawview 相機端實作與 SIGMA fp 快照](../rawview/README.md)
- [BMCC 6K Live View／Rec.709 對照與完整資料入口](../../bmcc6k/notes/FP_LIVEVIEW_COMPARISON.md)

- [Live View 研究總報告與 A/B 驗證設計](../../research/liveview/README.md)
- [bin／vbin、RAW 前端與上游截斷追查](../../research/liveview/upstream-clip-audit.md)
- [歷史曲線實驗與修正](../../research/liveview/prior-evidence.md)
- [ISP、tone 與增益路徑稽核](../../research/liveview/isp-path-audit.md)
- [LCD 矩陣、gamma 與輸出路由](../../research/liveview/display-route-audit.md)
