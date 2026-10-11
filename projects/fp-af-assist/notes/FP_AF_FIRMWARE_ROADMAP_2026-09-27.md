# fp 機內 AF：跨機型重審後的開發方向與階段目標

更新：2026-09-27，SIGMA fp Ver.5.02。本文件取代以電腦即時控制 AF 為交付目標的舊排程；歷史成果仍見 [開發進度盤點](FP_AF_DEVELOPMENT_STATUS_2026-09-27.md)。這次完成的是原始資料重審與開發規劃，尚未安裝新 hook 或驗收新的機內 AF 功能。

同日後續已推進離線實作：幾何 C、同 episode／final drive 合焦配對、完整 synthetic 回放，以及四個 source 的 ARM raw observer 候選；詳見 [上機前離線交接](geometry/OFFLINE_INTEGRATION.md)與 [最新驗證](geometry/VALIDATION.md)。目前停在需要核對實機執行環境與資源的邊界；原生來源 adapter、安裝生命週期及光學／AF 改善尚未驗收。

## 1. 開發決定

**使用者後續限定：交付範圍只包含 CINE 錄影時的連續對焦。** 保留 CINE，取消原擬 STILL AF-C／Tracking 實驗。CINE 待機可先核對來源與首次合焦，但不是錄影 CAF 驗收；M1 即納入錄影排程、FullTime AF、主體來源與鏡頭呼吸問題。STILL 路徑只作靜態程式對照，不再是里程碑前提。幾何核心共用 face／AAT，來源切换、尺度定義或目標變更須建立新 generation；沒有可靠 AAT 尺度時可保留追蹤身分用途，不把固定模板／AF ROI 當距離。

**主線修訂為：原廠 CDAF 首次合焦建立基準 → 臉部辨識／AAT 的幾何運算判斷接近或遠離 → DFD 若成立則估離焦量／所需位移 → 原廠 CDAF 確認。** 幾何沿用使用者在其他專案驗證的經驗，提升為本輪核心；AAT 同時負責主體連續性與可靠尺度。使用者另明確指出此方法需先合焦一次，因此本輪先改善合焦後的追焦，不把它稱為已解決冷啟動。目前不以解鎖 PDAF 為交付前提。

舊幾何方案以尺度推估距離／鏡頭位置；新版優先把它拆成方向層，位移量交給通過驗證的 DFD。幾何估距保留為校準有效時的比較／備援，**方向研究與幾何＋CDAF 版本都不必等待 DFD 成功**。詳見 [幾何／DFD 分工與首次合焦前提](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_GEOMETRY_DFD_FUSION_2026-09-27.md)。

PDAF 重審的結果是「fp 的可用性仍未證實，現有原廠路徑也沒有提供可直接使用的相位資料」，不是已找到開關，更不是證明晶圓絕對沒有相位結構。依本次研究方向，資源轉向無 PDAF 的成像／對焦方法與 fp 可達程式。PDAF 只有取得新的 fp-specific 輸出或感測器身分證據才重開。

**Z CAM E2-F6 不作連續 AF 的性能標竿。** 使用者已指出其連續 AF 並不理想。它的價值是有可讀程式，能研究統計取得、反轉後樣本處理、重搜與失敗機制；有 CAF 程式不代表好 CAF，也不把照搬其控制器列為目標。DFD 方法對照以 Panasonic S5／S1H／S1 為主，但本地核心程式尚未解開，不能稱已移植其 DFD。

正常使用時，估計、決策、鏡頭控制都在機內。**hook → 有限緩衝 → EP83 → 電腦**是主動推進的開發觀測路線；電腦用於離線分析、校準、重播與 A/B。暫停的是 USB 電腦參與即時 AF 閉環。

## 2. 跨機型的研究排序

「IMX410 機型」沿用本機資料分類，不表示每款都已證實相同 Sony part number、variant 或 phase pixel 配置。另要區分無 PDAF 的產品功能與物理上沒有 phase pixels。

| 對象／本地版本 | 目前能研究什麼 | 新定位 |
|---|---|---|
| **fp 5.02** | 可讀反編譯與 ROM、真實 CDAF／AAT 路徑、完成掃描歷史、既有鏡頭資料 | 第一優先實作依據與原廠 A/B 基準；不是從零重寫整套 AF |
| **Z CAM E2-F6 1.0.13** | 可讀 AF 主體、ISP focus statistics、多頻帶 FV、CAF／SAF、ROI、AE／IMU 連結 | 第一優先的外部程式對照；研究 hunting／重觸發與異常處理，不作 CAF 性能範本 |
| **Panasonic S5 2.9／S1H 2.8／S1 2.4** | 官方 Contrast AF + DFD 方法與行為、UPD 分區；AF 主程式仍加密 | 第一優先的無 PDAF 方法參考；有限追查可讀入口，無新線索則回到 fp 實驗，不等待解密才開發 |
| **Leica SL2-S 6.3** | 官方 contrast + depth mapping、追蹤與模式；NOT 後 UPD 主程式仍加密 | 次級方法對照；不能推論與 Panasonic 共用相同算法或光學模型 |
| **BMCC 全片幅 Cinema Camera 6K，包 10.3／內層 10.2.2** | 可讀 LensControl／狀態／ROI／能力契約；主 Autofocus app 未解 | 移出無 PDAF 組；接口與狀態架構旁證、PDAF 功能對照 |
| **Sony A7 III 4.04／A7C 2.03** | IMX410 driver／register 表、Sony phase routing；部分鏈仍未閉合 | PDAF 有界證據研究，不能直接轉換為 fp phase payload |
| **Nikon Z6 3.80／Z6 II 1.70** | 已解包程式、Nikon 尺寸表；感測器 writer／精確 variant 未閉合 | 次級 PDAF 線索，幾何不能代替可用相位資料 |
| **S5II／S5IIX、Nikon Zf、其他未解資料** | 新 phase 系統或仍不可讀 | 不列入本輪無 PDAF 算法移植任務；有新可讀證據才提高排序 |

分類的重要更正：Blackmagic 官方在 Camera 10.2.2（2026-08-10）為 **Cinema Camera 6K 全片幅**宣告新增 phase detection AF，不能混成 Pocket 6K 或舊版對比 AF。[官方版本說明](https://www.blackmagicdesign.com/mx/developer/partial/camera/sdk-and-software)。Panasonic S5 與 S1H 的官方資料明確描述 Contrast AF + DFD，這支持方法對照，沒有證明 fp 也能達到相同速度。[S5](https://na.panasonic.com/news/new-hybrid-full-frame-mirrorless-camera-the-lumix-s5)、[S1H](https://na.panasonic.com/news/panasonic-launches-a-new-full-frame-mirrorless-camera-the-lumix-s1h-with-cinema-quality-video-and-the-worlds-first-6k-24p-321-recording-capability)。

本地完整證據：[PDAF 重審](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/CROSSCAM_PDAF_FEASIBILITY_2026-09-27.md)、[Z CAM 程式研究](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/ZCAM_AF_REFERENCE_2026-09-27.md)、[Panasonic／Leica／BMCC 分類](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/NON_PDAF_CAMERA_REFERENCE_2026-09-27.md)。

本次 Z CAM 的實際程式分析帶來三個可測問題：

- ISP focus statistics 經 tile FV、IMU／AE 送進 CAF／SAF，反向後會丟棄一筆 FV。對 fp 應驗證自己的曝光／位置延遲，不能照搬「丟一筆」。
- 爬坡、回峰驗證、假峰重搜與 NG 回監看都已定位；初始搜尋 budget 75 可在重搜時加 50，不是全程硬上限。這提供檢查反覆抽動的路徑，但沒有動態 trace 能證明使用者遇到的具體原因。
- tracking→AF 有 ROI deadband、未變不重送與連續三次遺失後 fallback。可與 fp 的 AAT→AF 重驅鏈比較；不搬用它的像素門檻、幀數或海思 AI 模型。已讀範圍也沒有得到可直接移植的 DFD 反演。

## 3. PDAF 研究的繼續與停止條件

不能把「別家同系列 sensor 有 PDAF」視為 fp 可用。完整功能至少需要：

1. **fp 本機可取得有效的相位原始訊號**，或已驗證的硬體能力及可達輸出路徑。
2. **像素／遮罩／左右或上下配對與模式映射**，能區分相位、一般影像、黑位和缺陷資料。
3. **相位校準、鏡頭／光圈適用條件及品質判定**，能由離焦得到可重複的帶符號訊號。
4. **fp 可達的運算與控制整合**，以相機實際資料證明前後焦、零點和失敗退回。

目前不能給出這條完整鏈。fp 原廠 capability 返回 0、sensor correction 分支不提供對應能力，正常可觀察 RAW 也未找到可用 phase pair。Sony 的 VC1 線索是 DFE 的輸出格式器，不能直接當 sensor 相位副通道。

**本輪停止投入：**反覆掃同一批普通 DNG、盲試 Sony sensor 設定、只改 capability gate、因某字串／函式存在就推論可解鎖。

**重開條件：**新取得 fp sensor variant／OTP 的有效能力證據、fp sensor ingress 或專用 buffer 的候選 phase payload、可確認其來源的原廠校準／映射，或他機可讀 driver 提供能在 fp 靜態資料核對的新鏈。先驗證來源與模式，再安排有限實驗；即使觸發重開，也不阻擋機內 CDAF／DFD／AAT 主線。

## 4. 從 fp 可達程式選改進項目

本次重讀的「fp 程式」是反編譯 C 與 ROM，不是廠商原始碼。新 [機內接點圖](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AF_FIRMWARE_INTERVENTION_MAP_2026-09-27.md)把以下三層分開：

| 層級 | 第一個研究問題 | 候選入口 | 首版原則 |
|---|---|---|---|
| 幾何運動方向（主線） | 首次合焦後，同一主體的可靠尺度能否及時判接近／遠離？ | 原始 face size、AAT 命中點尺度／模型狀態、來源 generation、合焦錨點 | 抽出舊尺寸倒數斜率方法；先只觀測，沒有錨點不控制；AAT 自適應窗不當物理尺度 |
| DFD／光學量（並行） | 能否估當前離焦量／峰區間，提供幾何方向之外的位移資訊？ | H/L producer 返回、Near history commit；AF process state／route | 先旁路估計；有號／無號分開，不把幾何運動方向直接當當前修焦符號 |
| AAT 本體 | 沒有足夠特徵、同色背景或遮擋時，是否誤鎖／錯跟？ | `C05B6BA0`、`C05B6CF8`、模型更新與結果提交 | 先量原廠；框尺寸調整和低命中凍結已存在，評分品質仍可研究 |
| AAT → AF | 哪些框變化真代表距離改變，哪些只是抖動或換主體？ | `C0275E60` 採用分支、`C02761C8` quality gate、`C028A360` 重驅 | 記錄實際 AF ROI 與原因，再加條件式持續性／遲滯 |

原廠已具備 Fast／Slow／Near、峰位內插、越峰判定、條件式省略細掃，以及峰歷史的運動預測。**改進要證明相對這些既有能力的增益。** 不能把原廠 PdCaf 的不可達減速函式當作現成 DFD，也不能讓新模組與原廠同時直接下鏡頭命令。

DFD 的研究分兩級：先驗證多頻帶與已知位移提供的光學訊息；只有在鏡頭／光圈／成像條件校準後，證明影像模糊能估離焦，才稱已驗證的 DFD。幾何估的是主體運動，DFD 估的是當前焦平面誤差；兩者可能因過衝、延遲或換主體而方向不同，不能直接相乘。若 DFD 不成立，先完成有實證的幾何＋CDAF／AAT 改進。

## 5. 階段目標與完成條件

每階段以產物與通過條件判定，不用完成百分比，也不預估尚無依據的日期。M1 的工具工作、M2-G／M2-A／M2-D 的離線研究可以並行；未閉合的即時時序不得帶入動作版本。

9/27 實機來源診斷後補充：M1 的 AAT baseline 必須先證明 tracking gate、目標初始化、Run／GetResult 與停止流程。原廠 STILL Tracking 入口已查明，但使用者只做 CINE，因此不執行該入口；改查 CINE continuous-AF 與 AAT 的可達性及缺少的接點。先前 tracking=0、model=0 的讀取不能列成 AAT 失敗樣本。機內自動 face→AAT 初始化仍是待實作／驗證的接點；新目標或 reseed 要更新 generation，不能沿用舊幾何錨點。見 [啟動條件與交接](research/FP_AAT_ACTIVATION_2026-09-27.md)。

| 階段 | 要交付的具體成果 | 完成條件 | 當前狀態 |
|---|---|---|---|
| **M0 研究收斂** | 跨機型證據分級、PDAF 四條件、fp 可達接點、優先序與停止規則 | 機型／版本／sensor 證據分開，禁止以死碼或加密檔名當算法成果 | 本次完成判定與文件；Z CAM 控制細節可繼續有界擴充 |
| **M1 原廠觀測與合焦錨點** | telemetry、face／AAT 尺度來源、AF 採用 ROI、首次合焦位置／尺度／時間、hook 與重播 | 能追溯每筆來源；分開未合焦／錨點有效／追焦／失效重取得；觀測不改原廠行為；未知時序不用於動態控制 | JSON v7/native bytes 修正、同輪事件配對、四接點 raw observer 與 ROM 核對已完成離線候選；可信時間／身份、installer、實機 hook／EP83 尚未驗收 |
| **M2-A AAT 單項改進** | 原廠失敗案例集；可追蹤性／失去目標／模型凍結或重驅遲滯中，選一項有證據的改動 | 減少指定失敗，且不延長錯跟、不以拒絕真主體換表面穩定；另量真實距離變化的反應延遲 | 可立即以既有程式建立觀測與離線驗證 |
| **M2-G 幾何方向（主線）** | 抽出不依賴絕對距離曲線的尺度方向器；合焦後受控前後移動及固定主體的干擾測試 | 同報方向錯誤、未知比例、靜止誤判、反向延遲；驗證 face／AAT 尺度，沒有錨點時只能旁路 | C 核心、配對→幾何 JSONL 重播、ARM objects 已完成；完整離線結果見最新 VALIDATION。合成反向仍有短窗錯向，尚無可信 native 來源或光學驗收 |
| **M2-D DFD 位移候選（並行）** | 單鏡頭固定條件的離焦量／峰區間、符號有效性與信心；機內只記錄版本 | 留出資料證明相對簡單梯度的額外價值；獨立光學驗證，拒絕與誤判同報 | 尚無通過驗收的機內 DFD；不阻擋 M2-G |
| **M3 CINE 幾何＋CDAF，再加入 DFD** | 首次合焦→錨點→幾何方向輔助→CDAF 確認／失效重取得；DFD 通過後另加入位移量 | CINE 受控前後移動，先待機核對再實際錄影；不接電腦運作；原廠保持鏡頭控制權；量移動中方向可用率及呼吸干擾 | 幾何版依賴 M1／M2-G；目前鏡頭移動即清趨勢，尚不滿足連續錄影追焦 |
| **M4 CINE 聯合動態驗證** | 原廠、AAT、幾何＋CDAF、DFD＋CDAF、完整融合逐項比較；錄影負載下的自然動態 | 分開首次合焦、追焦與失效重取得；量清晰度、pumping、錯跟、延遲、漏樣及錄影開始／停止共存 | 待前階段；CINE 待機成功不代替實際錄影追焦 |
| **M5 可使用版本** | 機內功能、適用鏡頭／光圈／模式清單、可停用與恢復、重播資料及結果報告 | 只發布已驗證組合；未知鏡頭／模式回原廠；診斷 USB 斷線不影響 AF | 未開始發布驗收 |

### M1 的 EP83 子目標

1. 先定研究資料：face 原始尺寸／來源、AAT 命中點尺度與各階段框、合焦錨點、H/L history、gain／readout、strategy／drive branch、採用 ROI、quality、重驅原因。128-byte 現有 record 不代表全都已具備；可採有型別的小記錄。
2. 重新整合維護中 loader 的記憶體契約，修正 libusb 預設路徑；舊 guarded-loader 的來源 hash 拒絕不能只靠換 hash 消除。
3. 驗證有限合成批次的筆數、順序、CRC、重複／遺失與結束狀態，再取機內真資料；原廠也使用 EP83，必須證明傳送所有權與正常事件共存。
4. 量 hook 本身及 USB 傳送對 AF 的影響。hook 只記錄，其他合適任務才送 USB；最後比較觀測開／關與 USB 拔除。

現有可用的 completed-history、離線重播和其他有限記錄仍可先支援研究。EP83 未實收以前，不報預測吞吐為成績；EP83 通了以後，也不把收到一筆當成一張新曝光。

### M2-A 的取捨

依原廠樣本選一個可重現問題再修改，優先順序是：**錯誤接受目標／失去身分 → 模型被背景污染 → 框抖動造成不必要重驅**。對每項都有反例：灰色但有紋理的真主體、短暫遮擋後回來、真實沿光軸移動、face／eye 優先切入切出。

AAT 不能用「框更不動」驗收。至少保存每次目標切換、誤鎖、失鎖、重新取得、AF 採用分支，以及誤重驅／分鐘與真實深度變化的反應延遲。任何平滑、hold、凍結都要有最長有效期與失效原因。

### M2-D 的比較對象與退出方式

基準包含：原廠搜尋、已知位移下的 H 梯度、H/L 多頻帶特徵、局部曲線模型。先使用原廠已有的探測位移，避免為新算法額外加大量 wobble。DFD 重點是幾何運動方向以外的離焦量／焦點區間；其光學前後焦符號、峰位、清晰度分開評分。不能預設 DFD 能獨立完成冷啟動。

第一個校準組合優先使用已有距離表與掃描資料的 SIGMA 28mm Art，固定一個光圈、readout 與曝光條件；具體條件在 M1 基線記錄中凍結。已有距離表的 LUMIX 40mm 留作後續跨鏡頭檢查，不能共用未驗證的光學曲線。

若控制 ROI／曝光／gain 與位置對齊後，多頻帶仍無法在新場景穩定勝過簡單梯度，停止擴大該模型：先交付已證實的幾何＋CDAF／AAT 改善。不得用同一條 H 曲線定義真值又宣告自己有獨立 DFD 準確率。

## 6. 共用的驗收設計

以下是**建議的首輪驗收規格，尚未達成**。M1 先量基準與噪聲，再在看修改版結果前凍結正式門檻；保留失敗與拒絕資料。

| 項目 | 設計 |
|---|---|
| 獨立合焦基準 | 在固定成像條件與靜態標靶上，使用高解析影像的邊緣／細節品質和局部 focus bracket 定義最佳點及可接受焦點區間；避免只用 AF H/L 自我驗證 |
| 誤差尺度 | 以獨立最佳點 p* 到可接受區間左／右界的半寬 U−／U+ 為尺度；點估計依偏移側計算 abs(p−p*)/U。清晰度門檻先由基線凍結，不能用原廠 608 常數代替；非對稱曲線保留左右界線 |
| 幾何方向 | 以已知主體接近／遠離／靜止作參考，報錯誤率、未知比例、靜止誤觸發與反向延遲；另測鏡頭改焦但主體不動、轉頭／遮擋／裁切等干擾，不能用 H 峰代替運動真值 |
| 光學方向／區間 | 光學修焦方向與主體運動分開；在同覆蓋率對比簡單梯度。峰區間同報獨立最佳焦點涵蓋率及區間寬度，防止用過寬區間或大量拒絕過關 |
| 後續點位置版本 | 只有開始輸出單一峰位置後，才使用上述標準化誤差的中位 ≤0.5、95th ≤1.0 作候選目標；同報拒絕比例與適用條件，與方向版分開驗收 |
| 場景矩陣 | 前／後離焦 × 小／大離焦；高／低紋理、低光、高亮點、同色背景、灰色有紋理、遮擋、雙主體、沿光軸移動；後續才擴鏡頭／光圈／readout |
| 資料切分 | 以完整 trial／場次／主體分組留出；相鄰幀不能分到訓練和測試兩側。先做小批配對試驗，再跨至少兩場次重測 |
| 正式比較 | 建議每個聲稱支援的主要條件至少 30 組配對 AF trial，報中位／95th、失敗率、置信區間；樣本不足明列不確定，不宣稱罕見錯誤已消失 |
| 成功門檻 | 合焦成功率與最終影像品質不退步，且合焦時間、鏡頭總行程、可見反向／pumping 至少一項有可重現收益；不得只挑成功案例或把提前停止當加速 |
| 動態／AAT／錨點 | 分開首次合焦、已有錨點的追焦、失效後重取得；量失焦時間、錯跟、誤重驅及真實深度變化延遲，保存畫面與實際 ROI；錨點只由光學確認更新 |
| 機內預算 | 量估計／hook 耗時分佈與最壞值、記憶體、漏樣；在允許的 AF 排程餘裕內預先設定 deadline，逾時撤回建議；不能沿用電腦或他機的頻率當 fp 預算 |
| 模式與恢復 | AF-S／AF-C、鏡頭更換、光圈／裁切切換、手動介入、錄影開始停止、USB 斷線；未驗證模式回原廠流程 |

幾何追焦已提前到 M2-G 主線：重用 [sigma-fp-bridge 研究](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/FINDINGS.md)的主體尺度、來源正規化與倒數尺度趨勢；先合焦一次建立控制基準，並重新驗證機內 face／AAT 尺度。舊幾何估距可在校準有效時比較，不沿用舊延遲或四點精度作新版本保證。

## 7. 接下來三份最小交付

1. **M1 資料與錨點契約**：face／AAT 原始尺度、合焦位置／尺度／時間、採用 ROI、H/L 與資料有效條件；記錄未合焦到追焦的狀態轉換。
2. **幾何方向器及 AAT 尺度回放**：抽出舊趨勢方法，區分主體真移動與算法調框／鏡頭呼吸；先證明合焦後方向可信，再接有限控制。
3. **單鏡頭 DFD 旁路報告**：比較光學離焦／峰區間候選，包含跨場次失敗、拒絕與獨立確認；成果作為幾何＋CDAF 的可選增量。

三份交付可在 EP83 整合與既有資料研究間並行。首個可用成果可以是 AAT-only 或首次合焦後的幾何＋CDAF；DFD 位移輔助須獨立驗收，不能以他牌功能或同系列 sensor 代替。
