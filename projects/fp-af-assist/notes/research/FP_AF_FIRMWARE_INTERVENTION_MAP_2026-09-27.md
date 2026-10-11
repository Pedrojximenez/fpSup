# fp 5.02：機內 AF／AAT 改進的程式接點

日期：2026-09-27。用途：支援機內幾何方向、DFD 位移輔助與 AAT 的開發接點。最新分工為先由原廠首次合焦建立錨點，再做幾何追焦；見 [融合與首次合焦前提](FP_GEOMETRY_DFD_FUSION_2026-09-27.md)。

本文的「程式」指本機 `out/decomp/full/` 的反編譯 C、原始 ROM 與既有反組譯核對，**不是 SIGMA 提供的原始碼**。函式名稱有原廠字串還原名，也有分析命名；反編譯型別、參數及區域變數不等於原始 ABI。下列接點是研究入口，尚未完成所有 wrapper、機內時序與效益驗收。

## 1. 本次直接重讀得到的決策

**應把改進接到 fp 真正執行的 CDAF 策略、AAT 結果採用及重對焦判定。** 現有資料不支持把共用韌體中的 PdCaf 程式直接打開，當作已具備 DFD 的近峰控制器。

| 層級 | 程式證據 | 開發用途與限制 |
|---|---|---|
| AF 策略狀態機 | `C0259D50` 依 process `+18` 狀態與 `+38` strategy vtable 呼叫初始化、評價、完成；`C025A4C0` 寫 `+1C` route | 觀察原廠選擇和完成原因；新建議須在策略適用的決策邊界消費，不能直接從另一個 task 改共享 route |
| 搜尋驅動 | `C022C1B0` 的 Fast 初始化；`C02A3780` 依鏡頭參數與 cadence 選 Scan／Intermittent | 同一策略未必使用同一位置補償分支；記錄實際 drive object/vtable，再研究範圍、方向或步距建議 |
| 是否需要細掃 | `isDontSlowAf C023AC48` 使用峰兩側 waypoint 間距與第一參數 `C3288508` context `+1C` 容差，並受前置否決條件影響；此 context 不是上一列的 process 物件 | 現有原廠已會省略細掃；先量「多掃發生在哪些場景」，不能把跳細掃本身當新功能 |
| 越峰／轉向 | `C0263078` 維護升降、1/32 相對變化與絕對評價門檻；`C02637A8` 為無進展／反向研究入口 | 新估計器需比這些已存在的訊號更早且可靠，才值得控制介入；不要直接調低全部門檻 |
| 峰位計算 | `calIntrPolAreaAfPeakPoint C0263FF8` | 原廠峰附近內插保留；歷史峰位重算吻合只驗證理解，不能作自己的光學正確率 |
| 原廠預測 | `CorePeakPosEstimateSubjectMove C0277580`、`SAF_EstimateCore_NearAfAfterSearchPeak C0277CE8` | 已有由峰歷史推測主體位移的機制；本輪幾何方向模組需與其分開比較，避免重複補償 |
| 不可直接使用的 PdCaf | `CalcCafDriveSpeed` 唯一呼叫前查 model vtable `+184`；fp 覆寫 `C029BA08` 返回 0 | 這條路徑缺有效 phase 輸入且在 fp 不可達；不能只改 capability gate 就當作機內 DFD |

本次直接閱讀：[狀態機](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:59046)、[Fast 初始化](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:33230)、[Scan／Intermittent 選擇](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:101930)、[細掃閘](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:41464)、[峰變化判定](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:63405)、[PdCaf 呼叫閘](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:48943)。峰值／預測的既有深入分析見 [AF_AE_INTERNALS](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/AF_AE_INTERNALS.md:182)。

28mm 舊實測使用的 **608 是原廠 EEPROM 衍生的 AF 容差常數**，不能當成每個鏡頭／光圈／距離的光學景深。新的誤差與合焦驗收必須另定影像品質的可接受焦點區間。

## 2. AAT 的三個接點應分開

### A. 追蹤器本體

- `C05B6BA0` 初始化、`C05B6CF8` 每輪追蹤；後者先複製追蹤狀態到區域工作資料，執行正規化、候選評價、框與色彩模型更新，再回寫結果。可在前後觀察 input/search/result，不能只讀最後顯示框。
- `C05B2DC0` 已存在大小相依的框尺寸調整（舊筆記稱 normalizer）與最小 20 的 clamp。本次反編譯直接確認。因此「補上原廠缺少的框尺寸調整」不是正確任務；這不表示 confidence、色彩或紋理評分的所有正規化問題都已解決。
- `C05B2910` 已有零命中參考恢復、低命中變化判定與模型混合更新。優先檢查這些條件何時誤把背景接受為主體，再決定是否加可追蹤性、凍結或重新取得規則。
- 初始化成功與可追蹤主體不是同一件事。先觀察有效候選／色彩與空間分離度／框內紋理／背景相似性；若紋理來源尚未取得，就不能把「加入紋理 gate」列成已可直接修改的一個常數。

直接程式：[初始化](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:139210)、[追蹤](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:139267)、[正規化](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:136637)、[模型更新](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:136527)。

### B. 追蹤結果是否成為實際 AF 區

`C0275E60` 先嘗試 face／eye；沒有成功採用時，才在指定 AF-C 伺服狀態與 AAT 區模式下呼叫 `C02761C8`。後者检查有效旗標、quality > 19、參考尺寸非零，再走 `C02763C0` 形成結果區。`C05C3D28` 的 2.5×W／1.5×H 是這條輸出框轉換，不是 AAT 搜尋窗。

**觀測必須同時保留「追蹤輸出」和「原廠真正採用的 AF ROI／分支」。** 有 AAT 框不代表該幀用它對焦；face／eye 切入切出也應使 estimator 的舊資料失效。

直接程式：[選擇器](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:72461)、[AAT 採用閘](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:72601)、[AF 區轉換](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:72679)。

### C. ROI 如何觸發重對焦

`C028A360` 根據區模式、有效框、框尺寸／邊界、評價漂移與模式變化等選擇是否重驅。新規則優先針對已量到的「框抖動造成無謂重掃」；同時保留對真實深度變化的反應，不能只延長 timer 或一律平滑框。

這一層是 AAT 與 AF 的首要整合位置：先輸出重驅原因與當前採用 ROI，再評估有條件的持續性／遲滯；只有把視覺錯跟與光學失焦拆開，才知道改進来自追蹤還是 AF。

直接程式：[重驅判定](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:85100)。注意舊筆記把 `C02083B0` 標為 VD tick；9/16 深入核對只確認它讀 AE singleton，不能直接換算為曝光 ID 或固定秒數。見 [時間欄位更正](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AF_PUBLICATION_HOOK_CANDIDATES_2026-09-16.md:142)。

## 3. 開發觀測的最小資料契約

以下是**需要取得的欄位**，不是宣稱現有 128-byte recorder 全都已提供。

| 資料群 | 必要欄位 | 缺少時的處理 |
|---|---|---|
| 出處與時序 | record version、source hook、local sequence、CPU time、可取得的 DMA／曝光 generation、validity flags | 曝光 generation 未閉合就保留 unknown，不能用 publication sequence 代填 |
| 原廠 AF | strategy、state、route、drive branch、H/L 及尺度、history n/delay/k、有效前綴、重驅／失敗原因 | 不支援的策略不得套用 Near 配對解讀 |
| 鏡頭與成像 | lens identity、focus position domain、cached position、native compensated position、光圈、焦段、readout/crop、實際 gain/HCG／曝光 | 改變條件時結束一段估計；缺資料不沿用之前的光學校準 |
| AAT／採用 ROI | target generation、原始框、搜尋窗、結果框、hits/quality、模型狀態、face/eye/AAT 採用分支、採用 ROI 與座標域 | target generation 是新設計欄位，不能把未證明穩定的 tracking ID 當全域身分 |
| 新演算法 | 幾何運動方向、光學修焦符號／離焦量／峰區間各自的信心，合焦錨點位置／尺度／時間與狀態、拒絕原因、估計耗時 | 原始 face 尺度／AAT 擬合尺度與搜尋窗分開；所有拒絕與失敗也保存 |

`source hook + event type + validity` 可用多種小型記錄串聯；先量需要的頻率與容量，不盲目放大每筆記錄或預設所有欄位同曝光。

兩個已有 ROM 核對的觀測候選：

1. **背景 H/L 發布完成**：`C022C858 → C023E9D0` 返回後。能證明 CPU 發布完成，不能直接證明新曝光。
2. **Near history commit 完成**：dispatcher `C025A660` 確認 virtual target 為 Near v5，返回後、v6 前。讀 `H[k],L[k],mposm[k]` 並保留 n/delay/k；`mposm` 是原廠補償位置估計。

背景 observer 與 Near 分屬不同 task。hook 僅有界複製，不做 USB 傳送、阻塞或動態配置；緩衝所有權、ABI、重入、快取與生命週期另行驗收。[完整候選審核](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AF_PUBLICATION_HOOK_CANDIDATES_2026-09-16.md)

EP83 是資料送出手段；缺少 sensor generation 或獨立合焦參考時，加快傳輸不會補足科學證據。既有 completed-history 重播、有限記錄與 EP83 整合可以並行。

## 4. 第一版的決策介面

建議將幾何與光學 estimator 分開：幾何輸出 `{target_generation, scale_source, sample_age, motion_direction, relative_rate, confidence, reject_reason}`；光學輸出 `{roi_generation, sample_age, defocus_or_peak_interval, sign_valid, confidence, reject_reason}`。融合另存 `focus_anchor(position, scale, timestamp, validity)`。先只旁路計算與記錄；這是設計建議，尚未實作。

首個動作版本先由原廠 CDAF 首次合焦建立錨點，再在已驗證的策略邊界使用幾何趨勢提出有限方向建議；DFD 位移量通過後另行加入。沒有錨點、過衝或目標更換時，不以主體運動方向代替修焦方向。原廠 manager 保持執行與確認；`isDontSlowAf` 不是通用的目標位置 API。

ROI／目標世代／曝光條件／readout／鏡頭狀態變動、樣本太舊、雙峰或資料品質不佳時，撤回新建議並讓原廠現行狀態機繼續。不能直接偽造合焦、強制細掃通過，或在另一個 task 另發鏡頭命令。

AAT 改進、幾何與 DFD 應可分開關閉，以原廠、AAT、幾何＋CDAF、DFD＋CDAF、完整融合逐項比較。若只讓框更平滑，卻延遲真實深度變化或延長錯跟，就不能算改善；首次合焦與後續追焦收益分開。

## 5. 程式閱讀的界線

- `AF_DESIGN_REFERENCE.md` 是早期綜合設計參考，部分 PdCaf 算法被當成 fp 可執行 CDAF。以本次接點圖、`AF_AE_INTERNALS` 的後續可達性更正及 ROM 核對為準。
- 高反編譯信心不等於光學效果已驗證；觀測掛點成立不等於所有資料已同曝光。
- 本次只更新研究與規劃，未安裝 hook、改 AF 常數、改 loader、連線或驅動相機。
