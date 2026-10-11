# SIGMA fp 自動對焦開發：進度與方向

整理日期：2026-09-27（台北時間）。目標機身：SIGMA fp Ver.5.02。

**同日使用者澄清：幾何列為主線。先由原廠 CDAF 合焦一次建立錨點，再以機內 face／AAT 幾何判接近／遠離；DFD 若成立則提供離焦與位移，CDAF 確認。這先改善合焦後追焦，不能當成冷啟動已解。** [最新融合分工](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_GEOMETRY_DFD_FUSION_2026-09-27.md)。

**同日後續更新：**依跨機型原始資料與 fp 程式重審，後續方向與驗收以 [新版機內開發規劃](FP_AF_FIRMWARE_ROADMAP_2026-09-27.md) 為準。本文件保留各代進度。PDAF 可用性仍未知；Z CAM 不作連續 AF 性能範本；Panasonic／Leica AF 核心仍未解；BMCC 全片幅 Cinema Camera 6K 新版已有 PDAF，不能列為無 PDAF 反例。

這份是跨專案進度快照，整合本機 `sigma-fp-bridge`、`sigma-fp-gimbal-ai`、`SIGMAfp_re/research`、`projects/fp-af-assist` 與 `fpSup/focus`。依據是現有程式、實測紀錄、原始資料摘要與相關任務交接；本次只有文件盤點及離線元件測試，沒有相機操作。歷史數字保留其測試條件，不當作目前效能。

## 1. 現在站在哪裡

**已經有原廠 AF 的深入逆向、幾何估焦與舊外部 AF 的實測基礎，以及可重播的機內 AF 統計；目前機內 DFD 輔助與 AAT 修改仍待實作及驗收。** USB／電腦 AF Assist 停留在 0.1.0-pre1，現在暫時擱置，該版本號不代表新機內方案的進度。

不能把所有工作都說成「AF 還沒寫」：早期 HDMI／GIMBAL 原型確實完成過單次對焦與局部重對焦。這些成果可供原理、資料與測試方法參考；新主線要將估計、決策與控制整合到機身韌體，機內整合的成效仍待驗證。

**依使用者 2026-09-27 最新指示，目前已可修改韌體，研究主線為「首次合焦建立錨點，機內 face／AAT 幾何判方向，DFD 若成立補位移，原廠 CDAF 確認」；USB 連接電腦輔助運算的路線暫時擱置。** 估計、決策與控制均以機內執行為目標，正常使用不依賴電腦或 USB 連線。機內統計、既有 AF manager 和鏡頭控制是整合對象；先評估如何改善原廠的方向、行程及近峰判斷，再由原廠 CDAF 確認。這是當前目標，尚不是已完成的機內功能。

暫時擱置的是電腦參與即時 AF 估計、決策與鏡頭控制的 host AF Assist 路線。**機內 hook → 緩衝 → EP83 快速傳回 AF／AAT 資料，保留為研究與驗證的開發路線**；電腦可做資料視覺化、離線重播、模型校準及原廠／修改版比較。EP83 是觀測工具，不承擔正常 AF 閉環；其資料取得能力與實際速度仍待驗收。幾何追焦提升為機內方向主線，沿用歷史方法並驗證新的 face／AAT 尺度來源；PDAF 保留為低優先底層支線。

| 工作線 | 已有成果 | 當前界線／下一步 |
|---|---|---|
| 原廠 AF 逆向 | CDAF 多頻帶、Fast／Slow／Near 等策略、峰值內插、回驅、AF-C 與偵測框耦合已有詳細筆記 | 靜態可達性、實機量測及共用韌體死碼須分開；不是所有函式都在 fp 執行 |
| 幾何方向（主線） | `sigma-fp-bridge/focus-ai` 有臉／人體尺度模型、延遲補償、倒數尺寸預測及量測筆記 | 可沿用模型方法；本機缺原始 data，不能把最佳舊數字當已重現成績 |
| 舊 HDMI／GIMBAL AF | 復刻 AF 有約 1.7 s 單次對焦、後续 Near 約 1.60–1.73 s 的局部實測 | 停止維護；HDMI 銳度受影像處理影響，新的減速控制器未接完 |
| 人臉／眼睛／AAT（主線） | 已解結果結構、選擇優先序、ROI 座標與 AF 連結；舊 AAT 復刻有追蹤實測 | 機內 AAT 改進尚未落地驗收；重點是低紋理誤鎖、目標漂移及丟失恢復 |
| 鏡頭位置與距離 | SIGMA 28mm Art 的 19 點、LUMIX S 40/F2 的 10 點距離表已取出 | 要區分 native／PTP／鏡頭表的位置域；不等於已有完整 DFD 光學校準庫 |
| 原廠 AF 量測工具 | collector、completed-history probe、analyzer、direction replay、lens readout 均存在 | 有效歷史配對已驗；即時曝光與位置對齊仍未閉合 |
| 電腦端 bounded AF（暫時擱置） | UI、受限 H 搜尋、native move／abort／getter、取消及還原已實作 | 保留研究資產；未完成的 host 閉環不列為機內方案前置 |
| hook／EP83 開發觀測路線 | recorder、封包、sender、receiver、camera/control adapter 候選均有原始碼與離線測試 | 用於擷取機內 AF／AAT 資料；需解決 loader／libusb 與收發整合，尚未實機驗收 |
| 機內 DFD 輔助（主線） | 舊 HDMI 曲線模型、新 H/L 方向診斷、native AF 及發布路徑均已有研究 | 尚無已整合原廠 AF 的機內 DFD 輔助器；跨鏡頭／光圈／場景未標定 |
| 錄影追焦 | 阻擋外控的路徑、mode／session 限制已有逆向與歷史經驗 | 新版先限定非錄影 Live View；錄影期間的控制、取樣及恢復需另驗 |
| PDAF／IMX410 | fp RAW 否定證據、Sony phase 路徑與其他 IMX410 機身對照已累積 | 尚無 fp 可用 phase payload、座標圖或單一 enable bit |

## 2. 三代開發的成果應分開看

### 幾何追焦：sigma-fp-bridge

使用者指定的原始參考是 [focus-ai](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/README.md) 與 [FINDINGS](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/FINDINGS.md)。這條路線利用同一主體的臉／人體在畫面中的尺度，估計焦點位置，並補償畫面及馬達延遲。

可沿用的核心是：固定物體尺度下，影像大小約與距離倒數成正比；主體沿光軸近似等速時，在 `1/size` 上估速度較合理，再由鏡頭曲線換成焦點位置。模型只能用已被光學確認的合焦點更新，不能把自己的目標位置拿來當真值。

原始 repo HEAD 為 `1bca1b9`（2026-08-26），README 已標示停止開發。舊筆記報告 8/8 同一人、28mm、單場次四點校正的線性留一中位／最壞誤差為 **35／53 個位置單位**；9/16 融合計畫引用為約 **0.2／0.4 個局部景深**。但本次用文中四個整數點重算約 **29.9／45.2**，未能精確重現舊報值；可能與原始精度不同有關，原因未確認。本機缺 `focus-ai/data/` 原始素材，故應把 35／53 標為歷史筆記值。[原始四點與數字](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/FINDINGS.md:711)

跨場次表現明顯較差：同人同鏡頭隔兩天互相預測，中位 **143–228**、最壞 **250–444** 個單位。兩次約 100 秒自然跟焦亦未自行建立完整模型；專案另提供校正程式。幾何可作先驗，但跨場次穩定與自然自學不能視為已解。[跨場次](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/FINDINGS.md:768)、[冷啟動限制](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/FINDINGS.md:1027)

移植時需要保留的修正：尺寸正規化、同一主體身分、側臉信心限制、臉／人體線索的尺度對齊、留出資料驗證，以及重新量測影像到驅動的總延遲。小範圍少量校正點不應盲目增加二次項；舊延遲與馬達速度不能直接當作新機內路線常數。

現行模型實作為至少 3 點、跨度 ≥1.5× 才擬合；至少 5 點、跨度 ≥5× 才使用二次式，其餘用線性。更新時目前檢查的是樣本數、跨度及樣本內 RMS，LOO 是離線工具，不是每次更新都有自動執行。[model.py](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/focus/model.py:85)

另外，五秒線索換手平滑已在原始程式設為 `RATIO_BLEND_S=0`，按 yaw 切人體亦預設停用；臉／身體融合是預設關閉的選項。不能把舊研究計畫裡「保留平滑」當作已驗證改善，因實拍曾出現很久才合焦。重用時需同時量收斂時間，而非只看鏡頭行程變少。[subject.py](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/focus/subject.py:87)

### HDMI／GIMBAL：已有可運作的歷史對比 AF

[`sigma-fp-gimbal-ai`](/Users/dido/Developer.localized/sigma-fp-gimbal-ai/README.md:37) 留下的單次對焦結果是 **5.4 s／500+ 次量測 → 1.7 s／20 次**，落點散布約 0.4 個焦深。這是該外部復刻實作優化前後的比較，**不是與機身原廠 AF 的 A/B 勝負**。

之後修正評價值「每像素平均」與韌體「總和」單位不一致，局部 Near 重對焦由約 4.94 s 改為 **1.60–1.73 s**，但只驗過一個場景。[後續實測](/Users/dido/Developer.localized/sigma-fp-gimbal-ai/DECISIONS.md:3958)

曲線模型方面，舊 HDMI 資料在四個距離的 Lorentzian 擬合 R² 約 **0.983–0.997**，提供了比遠端三點拋物線外插更合理的候選。這不否定原廠在峰附近做三點局部內插；兩者用途不同。舊資料受 HDMI 銳化／降噪影響，且相關實驗在 f/1.4，不能直接把寬度與參數搬到 native H/L。[研究與未完項目](/Users/dido/Developer.localized/sigma-fp-gimbal-ai/AI_AF.md:191)

此 repo 已明確停止開發並轉向 fpSup。可重用的是曲線估計、AAT 追蹤的正規化及模型更新、漂移判斷、量測紀律；未完成的是新 AF 的減速驅動整合、多場景／跨光圈確認，以及接入機內資料。[轉向理由](/Users/dido/Developer.localized/sigma-fp-gimbal-ai/README.md:155)

### 電腦端 AF Assist：機內統計與 native 控制原型，現暫時擱置

當前 [原型](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/README.md) 已實作單一 ROI、起點 ±100 pulses 範圍、最多 12 次請求的 H 搜尋，具備取消、記錄與還原。

實機證據包括 20-pulse 控制、原生完成／停止流程、靜止 H 取樣及動作前取消。最後一輪完整整合只完成四次受限小步，因 USB 短回覆反覆發生而人工取消，結果為 fault，未完成最終對比確認。當次 RAM／echo／設定已還原；鏡頭停在 10807、起點 10707，這只是歷史位置。[驗證紀錄](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/VALIDATION_2026-09-16.md:164)

後續加入傳輸異常鎖：同一輪出錯，即使讀取恢復也不再發新位移或新原廠 AF 啟動。這是控制防護，並非 USB 問題已修好。程式仍維持 [`HARDWARE_MOTION_VERIFIED = False`](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/fp_af_assist.py:21)。

## 3. 原廠 AF 量測已證明什麼

9/16 已有四輪完成的 Near 歷史，每輪 6 點，共 **24 個 H/L–position 樣本**。其中三輪重複共 1795 snapshots，重算峰值 **9996／10011／10013** 與原廠儲存值吻合，峰位範圍 17 個單位。[重複性](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AF_REPEATABILITY_2026-09-16.md:33)

這證明我們理解該完成歷史的索引與峰值演算法，尚未提供獨立光學真值。可靠協定目前收斂在 completed Near／area 0，不能直接擴展至所有策略、即時背景取樣或其他 ROI。

H/L 方向診斷已確認：**同一比值能出現在峰兩側**。已知位移的 16 個同側配對中，梯度方向 16/16 符合以 H 峰定義的方向，但這是同資料內檢查，不是獨立 100% 對焦準確率。ratio 峰也可能偏離 H 峰一個 134-unit 步距。[方向診斷](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AF_DIRECTION_DIAGNOSTICS_2026-09-16.md:21)

因此下一階段的資料要求是：區分發布、曝光及鏡頭位置的時間；記錄實際 gain、ROI 與模式；取得可驗證的雙向掃描與獨立合焦參考。固定 UI ISO、snapshot 索引穩定、USB 收到資料，皆不能單獨代替這些條件。

## 4. hook／EP83：取得機內 AF 資料的開發與驗證路線

本路線保留供開發研究：在所需 AF／AAT 資料產生或提交的位置 hook，機內有限緩衝，再由 EP83 傳回電腦。目的是取得原廠流程、資料時序、估計結果與改版效益的證據；正常拍攝時的 AF 估計與控制仍全部留在機內。

以下問題是這條觀測工具路線的實際待辦，並不等同機內 DFD 演算法本身的阻礙。先定義研究所需欄位與時間語意，再決定掛點及頻寬；不以更高 USB 數字代替有效 AF 樣本。

兩筆異常已辨識為與 FPSH sequence 相符的 PTP `SessionNotOpen`；原廠 usbTask 和自訂 worker 可到達同一 USB 傳輸描述子、完成及重新啟用路徑。這支持傳輸資源競爭的診斷，但未證明每一筆歷史 timeout 都來自同一動態原因。[傳輸稽核](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/TRANSPORT_AUDIT_2026-09-16.md:109)

高速候選已有 **724-byte recorder、256 筆 × 128 bytes 有限記錄、AFB1 framing／CRC／nonce、32,896-byte 完整批次、sender 及 receiver**。後續原始碼另有 camera binding、native mode-5 CMD4 adapter、單次 RTOS Wait、MMU／noncache 檢查及 libusb owner。這些比 README「adapter 尚未寫完」的敘述更進一步，但仍是未部署候選。

EP83 原本也被原廠事件發送使用；只修改 USB descriptor 或端點號碼不足以取得排他使用。原先 mode-1 Wait 還可能重新啟動 EP01；新候選用另一個單次 RTOS event wait 避開此路徑，仍須完成整體 boot／ownership 驗證。builder 現仍明列 `deployment_ready=false`、`adapter_complete=false`、`loader_integration_complete=false`、`single_usb_owner_verified=false`。[最新 builder](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/highrate/build_ep83_camera.py:301)

**本次離線核對找到此路線的兩個未解問題：**

1. **AF guarded-loader 與維護中的新 loader 已不相容。** AF builder 鎖定 `e43b274…` 舊來源 hash；目前 loader 是 `53991350…`，測試在 setup 階段以 `maintained loader source identity changed` 拒絕。維護 loader 已改用 `fpSup.BIN`、64 KiB 暫存後釋放、payload 自行配置記憶體；AF 的 1 MiB 常駐 pool 假設必須重新整合，不能只換 hash。[AF guard](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/highrate/build_guarded_loader.py:17)、[新記憶體契約](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/asm/loader.S:49)
2. **目錄搬遷留下 libusb 預設路徑錯誤。** `ep83_libusb_owner.py` 現解析到不存在的 `projects/lib/libusb-1.0.dylib`，本機檔案位於 `projects/usb-shell-sup/lib/libusb-1.0.dylib`。mock 測試未涵蓋這個預設路徑。[來源](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/highrate/ep83_libusb_owner.py:21)

本次嘗試九組最新元件測試，**63 項執行並通過；guarded-loader 的 setUpClass 失敗，該組 4 項未開始**。涵蓋 camera build／camera／wait／control／memory／host session／libusb owner／card backup，以及失敗的 guarded-loader。未重跑全專案 suite；交接文件的 **386/386** 是歷史成績，不能當作今日全數通過。

AF 這批較晚元件的檔案時間仍在 9/16；9/25 文件變更包含搬移路徑，而維護 loader 同日有實質更新。未找到新的 AF 實機閉環或 EP83 實收證據。觀測工具仍有整合工作，不能只寫「等待插測試卡」。

## 5. PDAF、鏡頭資料、人臉與錄影的定位

**PDAF：保留研究，未取得可用功能。** fp 的 capability gate 為 0，IMX410 的 PDAF geometry 實作為空。已擷取 pre-StillCreateRaw 的 6064×4042 RAW14，與同曝光 DNG 相關係數 0.99998646，仍未見可用相位點圖樣；correction bypass 亦無新增週期遮罩。正確結論是「正常可觀測 readout 未找到可用 PDAF pair」，不能推成物理晶圓絕對不存在相位結構，更不能把 fp L 混為一談。[fp 調查](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/SIGMA_FP_PDAF_INVESTIGATION_REPORT_2026-08-18.md:8)

同日重審補充：上段 0.99998646 是舊報告值，本次獨立解碼重算為 **0.9999658557**，兩個 green plane 與 DNG 逐點一致；未精確重現舊係數，原因保留未知。另修正舊 sensor dispatch 編號：runtime vtable `C0B5FCC0 + A8` 實際指向 **v40 `C0322228`（return 0）**，不是舊報告的 v42。這不改變「尚無可用 phase pair」的工程判斷。[原始資料重審與四個門檻](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/CROSSCAM_PDAF_FEASIBILITY_2026-09-27.md)

Sony α7 III 研究已追到 ZAF、ZpdPre、FOPD／AFMAP 路徑，但 **VC1 的關鍵線索屬 DFE output formatter，尚非感測器直接輸出的 PDAF 副通道證明**。9/26 α7C 的 19×349 register table、Nikon AF per-mode 幾何提供新對照，仍沒有 fp phase payload 或 enable bit。後續應針對 sensor ingress、variant／OTP、phase calibration 等缺口；不宜盲移 Sony 表或反覆拍 DNG 尋找相同圖樣。[Sony 後續](/Users/dido/Developer.localized/SIGMAfp_re/sony_a7m3/a7m3-re-20260904/outputs/sony_a7iii_phase_data_route_followup.md:17)、[跨機身彙整](/Users/dido/Developer.localized/SIGMAfp_re/research/imx410/notes/OTHER_CAMERAS_IMX410_2026-09-26.md:12)

**鏡頭資料：已有實用的距離曲線，DFD 光學庫仍是另一件事。** SIGMA 28mm／LUMIX 40mm 都有非線性的距離－位置支撐點，應在倒數距離空間內插。先核對位置域、端點與取整；距離表、DPP 相關量並不直接提供由影像失焦反推距離的完整校準。[鏡頭資料](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/lens/SOP_LENS_EXTRACT.md:56)

**人臉／眼睛：選對主體與把焦點移準應分開驗證。** 原廠結果結構、固定參考座標、AAT 模型更新與選區規則可用於幾何先驗；偵測框穩定不代表光學合焦。內部 detector 的 320×213 參考域可減少外部影像解析度變動的混淆，仍須核對裁切及座標轉換。[偵測管線](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FACE_EYE_AF.md:113)

**錄影：放在非錄影整輪閉環之後。** 舊 tethering／GIMBAL 經驗各有不同 session、按鍵及資料路由限制；新 native 路線的錄影控制尚未驗收。不能因找到內部 drive 函式就宣稱錄影追焦已解鎖，也不應繞過目前 guard 取得表面成功。

## 6. 機內 DFD／AAT 技術基礎（幾何與合焦錨點的最新階段見新版規劃）

韌體可修改是目前的工程前提。優先工作是確定原廠可達的 AF／AAT 執行點、機內資料時序、運算及記憶體預算，將改進納入既有管線。電腦可用於離線分析與建置，但不參與正常 AF 的即時控制迴圈。

**A. 機內 DFD 輔助：先驗證估計，再有限介入原廠 AF。**

1. 建立原廠正常 AF 的基準：同時觀察 H/L、完成歷史、ROI、實際 gain、AF 策略與位置；先把曝光／位置配對及可用區間弄清楚。
2. 用離線及機內旁路估算比較候選模型。此時估計器只記錄方向、峰位／離焦量與信心，不影響鏡頭；核對它是否比原廠更早取得可信判斷。H/L 局部曲線估峰不應直接宣稱為已校準的光學 DFD。
3. 找出 fp 真正可達的原廠 AF 決策入口，先選一項受限協助：縮小搜尋範圍、方向提示、步距／減速建議。原廠保留鏡頭控制權與最終合焦確認；信心不足、ROI／gain 改變、曲線失效時撤回建議，讓原廠既有流程繼續，不另自動觸發一次半按 AF。fp 上被 capability gate 關閉的 PdCaf／PDAF 減速程式不能直接當作 CDAF 接點。
4. 對照未修改的原廠基準，量完成率、合焦時間、峰位誤差、可見反向／pumping、失敗恢復。先單 ROI／靜態／非錄影，再擴展動態主體及錄影。

這是新的機內整合方向；現有 `fp-af-assist` 的受限搜尋控制器在主機端，尚不等於此機內輔助器。可重用的是統計格式、測量資料、native 控制語意與狀態檢查。新的執行點、計算預算、AF manager 所有權及模式切換生命週期仍需設計驗證；若採用可動態安裝的 hook，再另外驗證啟停／卸載。

原始碼也明確區分：[`assist_controller.py`](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/assist_controller.py:1) 是對比輔助、不是 DFD；publication recorder 目前只記錄，沒有機內 estimator 或原廠 decision adapter。

**B. AAT 優化：先減少誤鎖與漂移，再驗證它帶來的 AF 改善。**

- 先觀察 AAT 原始框、搜尋窗、輸出框、hits／confidence、模型狀態、原廠實際採用的 face／eye／AAT 分支及 AF 重驅原因。`2.5×W/1.5×H` 是輸出重塑，不是搜尋窗；CAF CSV 的 `FaceTopX…` 也不能當真臉框。畫面上應標記真正採用的 AF ROI。
- 低紋理、低飽和或沒有有效主色候選時，原廠 setTarget 可能仍回成功；值得研究加入可量測的目標可追蹤性檢查，並測試灰色但有紋理的真實主體，避免用單一飽和門檻全部拒絕。
- 原廠已有框大小負回饋正規化、低命中凍結、色彩模型更新限制。舊外部復刻的框飽和曾是漏掉這些機制，不應直接當成原廠缺少機制；先核對原廠基準，再調整具體失敗情境。
- 分別量測目標丟失、遮擋、近似背景、尺度變化、換主體的行為。任何平滑或 hold 都需同時量追蹤延遲、錯跟持續時間與重新取得目標時間，避免「框不動」被當成穩定。
- 檢查框抖動是否造成靜止主體誤重對焦，再研究有條件的時間持續性／遲滯。原廠已有框變化、luma、模式、timer 等重驅機制；比較每分鐘誤重驅與真實景深移動的檢出延遲，不能只減少重驅數。
- 將 AAT 可信度、ROI 變動及目標切換與 AF／DFD 曲線有效性連結：換目標或 ROI 失效時不沿用舊峰；這個橋接規則尚待實作與 A/B。

原廠可參考的關鍵證據是 [AAT 色彩與框更新](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FACE_EYE_AF.md:67) 和 [AF-C 耦合](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FACE_EYE_AF.md:159)。AAT 改善與 DFD 模型研究可以並行，先各自量準，再做聯合 AF 驗收。

**C. 機內實作優先序與驗收。**

| 順序 | 交付 | 用來解決什麼 |
|---|---|---|
| 1 | 核對原廠 AF／AAT 可達執行點、資料來源與韌體修改位置 | 分開背景統計、原廠掃焦歷史及實際採用 ROI，確定機內介入層 |
| 2 | 機內只估算並記錄的 DFD 候選，以及 AAT 基準觀測 | 核對時序、估計誤差、主體連續性、運算耗時及記憶體需求 |
| 3 | 一項受限 DFD 輔助與一項有證據支持的 AAT 改進，分別可停用 | 分別驗證收益，避免同時修改多項後無法歸因 |
| 4 | 不接電腦完成原廠／修改版 A/B | 比較合焦時間、清晰度、反向、誤重驅、失鎖恢復及模式共存 |

**D. 並行的開發觀測路線：hook → 機內緩衝 → EP83 → 電腦研究。**

1. 定義需觀察的 H/L、原廠位置歷史／cached position、AF 策略與完成狀態、實際 gain、AAT 原始框與採用 ROI、confidence／hits、重驅原因；逐欄確認可取得性，現有 recorder 不代表已涵蓋全部欄位。
2. 依原廠資料發布／history commit 點設計有限取樣，標記序號、時間及上下文。發布序號不是曝光 ID，不同資料若不同步要保留這項差異。
3. 修復所需 EP83 元件的建置及路徑問題，先證明有限合成批次完整實收，再取得真實機內資料；hook 只做有界記錄，USB 發送放在合適任務中，量測對原廠 AF 時序的擾動。
4. 電腦端做圖表、離線重播、校準及 A/B；比較漏樣、重複、資料一致性、實際吞吐與時間配對，最後將驗證過的 AF／AAT 改進留在韌體內。

診斷也可依需要使用記錄檔或既有讀取工具。開發時連接電腦觀測，與產品運作時不依賴電腦，是相容的兩個目標。

同日最新澄清已把幾何提升為 M2-G 主線：首次合焦建立基準後，以 face／AAT 尺度判方向，DFD 若成立再補離焦量；這不恢復電腦即時控制路線。新階段以機內規劃為準，PDAF 不作交付前提。

既有融合計畫的中位峰位誤差 ≤0.5、95th ≤1.0 個局部景深，以及「零／一次細修正」，可留作候選目標；需重新套用到機內輔助的可達能力與測試條件，不能視為已達成或直接承諾。[舊驗收計畫](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AUTOFOCUS_GEOMETRY_DFD_PLAN_2026-09-16.md:255)

## 7. 哪些舊說法不要繼續沿用

| 舊說法 | 本次應採用的表述 |
|---|---|
| fpFocus 完成 48% | 舊產品路線圖的主觀估計，缺乏可對照驗收分母；以本文件各里程碑表示 |
| 擱置電腦輔助運算等於擱置 EP83 | 擱置的是電腦參與即時控制；hook／EP83 保留為機內 AF 資料擷取與研究驗證路線 |
| 收集器／外部 AF 尚未實作 | `projects/fp-af-assist/notes/firmware/FOCUS_SUP.md` 已落後；研究 collector、新 AF 原型及舊 GIMBAL 實作都存在 |
| 386/386，所以目前全數通過 | 是 9/16 歷史成績；本次 loader setup 已失敗 |
| H/L 是左右相位，或比值就能判前後焦 | 它們是處理後的 CDAF 雙頻帶；單比值兩側重疊 |
| H/L 是 bandval 減 scan-min，ratio 自動消增益 | 現有反編譯確認獨立縮放、修正、飽和與模式 offset；不能如此簡化 |
| `peak_now/max/min` 是峰值極值 | 舊欄位別名錯誤，實為 aggregate small-H／main-H／small-L |
| `mposm` 是任何時候都更新的即時位置 | 它是策略相關的 sweep 歷史；Near 可以指到未填下一格，idle 可以 stale |
| 100 Hz 讀取，或 0.125 ms／幀，就有相同頻率的新曝光 | 主機頻率／舊通道傳輸耗時不等於 sensor 或統計更新率；舊 EP84 成績也不代表新 EP83 已通 |
| 固定 ISO、索引一致即可做 DFD | 實際 AF gain 會變；快照完整性不等於曝光與位置對齊 |
| v1/v2 capture 記錄的 false 證明未錄影 | 舊 guard 位址不正確，重播應為 unknown；新版 v3／JSON v6 有修正但該 collector 版本待實機驗證 |
| 相同 IMX410、或有 PDAF 符號就能解鎖 | variant、輸出、可達路徑與 payload 都需證明；尚無 fp 可用 PDAF 證據 |
| 幾何 35／53 units 是通用已重現精度 | 是單場次四點舊筆記值；原始 data 不在本機，列印點重算約 30／45，跨場次誤差更大 |
| 五秒線索平滑已證明有效 | 原始程式已停用，需同時量收斂時間，不能只看行程減少 |
| 原廠 AAT 缺框大小正規化、會無界發散 | 原廠已有 normalizer；舊復刻漏掉它才出現飽和。FACE_EYE_AF 的灰區發散舊句需與緊接的更正合讀 |

關鍵更正來源：[方向診斷](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AF_DIRECTION_DIAGNOSTICS_2026-09-16.md:47)、[capture 格式更正](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AF_CAPTURE_GUARD_CORRECTION_2026-09-16.md:33)、[高速通道](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/highrate/README.md:78)。

## 8. 後續工作入口

- 本文件：跨專案總進度、最新阻礙與優先序。
- [幾何原始研究](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/FINDINGS.md)：模型、校正、延遲與失敗假說。
- [舊 GIMBAL AF 研究](/Users/dido/Developer.localized/sigma-fp-gimbal-ai/DECISIONS.md)：復刻、曲線、AAT 及單位錯誤的實測。
- [AF Assist 接手入口](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/CONTINUE_HERE.md)：頂部載明機內主線；下文保留暫時擱置的 9/16 host 原型交接。
- [高速通道程式](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/highrate/README.md)：機內 hook／EP83 開發觀測元件及契約；整合時核對原始碼與 builder manifest。
- [AF-fusion 工具說明](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/AF_FUSION_TOOL_USAGE.md)：量測、離線重播與已知語意限制。
- [融合研究計畫](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AUTOFOCUS_GEOMETRY_DFD_PLAN_2026-09-16.md)：幾何、沿路曲線、CDAF 的實驗設計。

原始資料和舊結論沒有覆寫；本次發現的建置／路徑問題尚未修復。後續進度應更新至新的驗證紀錄，避免把這份日期快照當成永久狀態。
