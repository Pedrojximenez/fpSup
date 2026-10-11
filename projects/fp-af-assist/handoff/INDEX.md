# SIGMA fp RE — 總索引

> **給之後的 session:先讀這份。**

## 這棵樹怎麼分

唯一的判準是**壽命**:這份知識在專案結束之後還有用嗎?

```
research/<主題>/   有 —— 相機本身的事實,換個專案還是成立
projects/<專案>/   沒有 —— 只在那件工作的脈絡裡有意義
```

每個分類底下:

```
notes/       結論與過程
captures/    素材 —— 支持那些結論的證據
<散檔>       當初拿到證據的腳本、探針、AutoRun 卡片(不另立資料夾)
<專屬>/      build/ assets/ releases/ analysis/ …
```

**素材跟引用它的筆記放在同一層是刻意的** —— 主張跟證據不分家。

判邊界的四個推論:事故跟著它發生的專案;發現的場合不決定歸屬;
工具跟著它服務的對象;`other/` 要小,長大就是分類該調整了。

## research —— 個別研究

### `research/autofocus/` — 自動對焦 —— CDAF、人臉/眼睛、DFD、PDAF、對焦距離
14 份筆記 · 4 個腳本/卡片 · `fp-af-explainer/` 737 MB

- [`AF_AE_INTERNALS.md`](projects/fp-af-assist/notes/research/AF_AE_INTERNALS.md) — SIGMA fp — AF/AE 內部演算法完整反編譯(六題彙整 + ⑦驅動細節十題 + ⑧CAF 觸發模型 + ⑨驅動/框
- [`AF_COMPLETE.md`](projects/fp-af-assist/notes/research/AF_COMPLETE.md) — SIGMA fp — 對焦系統完整說明(方法、細節、用到的鏡頭資料)
- [`AF_DESIGN_REFERENCE.md`](projects/fp-af-assist/notes/research/AF_DESIGN_REFERENCE.md) — SIGMA fp CDAF 演算法設計拆解 — 給「自製自動對焦」的參考
- [`AF_LIVE_STATE_MAP.md`](projects/fp-af-assist/notes/research/AF_LIVE_STATE_MAP.md) — SIGMA fp Ver.5.02 — AF / Tracking / Face LIVE-STATE Address Ma
- [`AUTOFOCUS.md`](projects/fp-af-assist/notes/research/AUTOFOCUS.md) — SIGMA fp / fp L — 自動對焦(AF)系統反編譯細節
- [`DFD_VIA_AF_STATS.md`](projects/fp-af-assist/notes/research/DFD_VIA_AF_STATS.md) — SIGMA fp Ver 5.02 — DFD via the hardware AF-statistics engine 
- [`FACE_EYE_AF.md`](projects/fp-af-assist/notes/research/FACE_EYE_AF.md) — SIGMA fp — 人臉 / 眼睛 / 主體追蹤 AF 完整反編譯
- [`FP_AUTOFOCUS_GEOMETRY_DFD_PLAN_2026-09-16.md`](projects/fp-af-assist/notes/research/FP_AUTOFOCUS_GEOMETRY_DFD_PLAN_2026-09-16.md) — fpFocus：幾何估距 + DFD + CDAF 的自動對焦改進方案
- [`FP_ORIGINAL_AF_TRIAL_2026-09-16.md`](projects/fp-af-assist/notes/research/FP_ORIGINAL_AF_TRIAL_2026-09-16.md) — 原廠半按 AF 實測、100 Hz DMA 傳輸修正、六點原生掃焦曲線與峰值交叉驗證
- [`FP_AF_REPEATABILITY_2026-09-16.md`](projects/fp-af-assist/notes/research/FP_AF_REPEATABILITY_2026-09-16.md) — 三輪原廠 AF 重複性、六點峰值吻合、即時統計例外與離線驗證界線
- [`FP_AF_DIRECTION_DIAGNOSTICS_2026-09-16.md`](projects/fp-af-assist/notes/research/FP_AF_DIRECTION_DIAGNOSTICS_2026-09-16.md) — H/L 單值歧義、已知移動下的梯度重播、固定 offset 與 aggregate 欄位更正
- [`FP_FOCUS_DRIVE_GATE_AUDIT_2026-09-16.md`](projects/fp-af-assist/notes/research/FP_FOCUS_DRIVE_GATE_AUDIT_2026-09-16.md) — 驅動 gate／完成／abort 審核、原廠只讀換算及近端邊界拒絕紀錄
- [`FP_NATIVE_FOCUS_CONTROL_2026-09-16.md`](projects/fp-af-assist/notes/research/FP_NATIVE_FOCUS_CONTROL_2026-09-16.md) — 正確 capture flags、native-L move/abort/event ABI、PTP worker 壽命與 ROM cache publication
- [`FP_AF_STATS_FRESHNESS_2026-09-16.md`](projects/fp-af-assist/notes/research/FP_AF_STATS_FRESHNESS_2026-09-16.md) — mode 1/3 背景 H/L 更新條件、scheduler witness 與非曝光對齊的限制
- [`FP_AF_PUBLICATION_HOOK_CANDIDATES_2026-09-16.md`](projects/fp-af-assist/notes/research/FP_AF_PUBLICATION_HOOK_CANDIDATES_2026-09-16.md) — 背景 producer 返回／Near history commit 掛點、task 脈絡與曝光位置語意限制
- [`FP_AF_CAPTURE_GUARD_CORRECTION_2026-09-16.md`](projects/fp-af-assist/notes/research/FP_AF_CAPTURE_GUARD_CORRECTION_2026-09-16.md) — collector v3/v6 格式、安全 guard、舊記錄 unknown 與安裝修正
- [`AF_FUSION_TOOL_USAGE.md`](projects/fp-af-assist/notes/research/AF_FUSION_TOOL_USAGE.md) — AF-fusion 工具操作教學：離線重播、即時收集、授權半按、歷史配對與失敗處理；對應 sigma-fp-af-research skill
- [`FOCUS_DISTANCE_PRINCIPLE.md`](projects/fp-af-assist/notes/research/FOCUS_DISTANCE_PRINCIPLE.md) — 對焦位置 ↔ 距離 換算原理(SIGMA fp,從韌體反編譯還原)
- [`FOCUS_POSITION_DOMAIN.md`](projects/fp-af-assist/notes/research/FOCUS_POSITION_DOMAIN.md) — SIGMA fp — 對焦位置域:PTP vs GIMBAL 單位關係(反組譯確認)
- [`PDAF_RAW_PATTERN_ANALYSIS_2026-08-17.md`](projects/fp-af-assist/notes/research/PDAF_RAW_PATTERN_ANALYSIS_2026-08-17.md) — SIGMA fp pre-Still RAW PDAF pattern analysis
- [`PTP_FOCUS.md`](projects/fp-af-assist/notes/research/PTP_FOCUS.md) — SIGMA fp — PTP 對焦控制在錄影時失效：原因與可能解法
- [`PTP_FOCUS_RECORDING.md`](projects/fp-af-assist/notes/research/PTP_FOCUS_RECORDING.md) — PTP/GIMBAL 錄影中控焦 — session 閘研究 (待續)
- [`SIGMA_FP_PDAF_INVESTIGATION_REPORT_2026-08-18.md`](projects/fp-af-assist/notes/research/SIGMA_FP_PDAF_INVESTIGATION_REPORT_2026-08-18.md) — SIGMA fp 相位像素／PDAF 原始資料調查報告
- [`af_fusion_collector.py`](research/autofocus/af_fusion_collector.py) — 預設只讀 AF-fusion snapshot；可明確選用一次原廠半按／釋放測試、JSONL 保存與離線 replay
- [`af_fusion_history_probe.py`](research/autofocus/af_fusion_history_probe.py) — 原廠 AF 完成後，只讀雙次核對 native sweep metadata 與 H/L/position 歷史
- [`af_fusion_history_analyze.py`](research/autofocus/af_fusion_history_analyze.py) — 純離線 completed Near / area-0 歷史檢查、有效前綴與候選峰值重算
- [`test_af_fusion_history_analyze.py`](research/autofocus/test_af_fusion_history_analyze.py) — 歷史 metadata、差異、索引、signed position 與插值邊界測試
- [`af_fusion_direction_replay.py`](research/autofocus/af_fusion_direction_replay.py) — 離線 H、L、H/L 方向與峰值歧義診斷；不是 DFD 控制器
- [`af_fusion_lens_readout.py`](research/autofocus/af_fusion_lens_readout.py) — 原廠 cached focus getter／distance conversion；不移動鏡頭
- [`test_af_fusion_direction_replay.py`](research/autofocus/test_af_fusion_direction_replay.py) — 方向重播、交點、未知值與來源／輸出保護測試
- [`test_af_fusion_lens_readout.py`](research/autofocus/test_af_fusion_lens_readout.py) — 完全 mock 的唯讀命令白名單、回覆與邊界停止測試
- [`af_fusion_snapshot.S`](research/autofocus/af_fusion_snapshot.S) — 同一次 handler 讀取 H/L、曝光中心 `mposm`、320×213 ROI、AE 與 drive state
- [`test_af_fusion_collector.py`](research/autofocus/test_af_fusion_collector.py) — AF-fusion record/schema 的離線回歸測試

### `research/display/` — 顯示 —— OSD 繪製、false color
2 份筆記 · 23 個腳本/卡片 · `captures/` 20 KB

- [`DISPLAY_OSD_MAP.md`](research/display/notes/DISPLAY_OSD_MAP.md) — SIGMA fp Ver.5.02 — Display / OSD drawing map
- [`OSD_PERSISTENT_MARKER.md`](research/display/notes/OSD_PERSISTENT_MARKER.md) — 螢幕常態標示（持久 OSD marker）— 為何失敗 + 正解配方

### `research/firmware/` — 韌體本體 —— 格式、簽章、隱藏功能、開機
5 份筆記

- [`BOOT_OPENING_LOGO.md`](research/firmware/notes/BOOT_OPENING_LOGO.md) — SIGMA fp Ver 5.02 — Startup / Boot / Opening Animation (RE rec
- [`FIRMWARE_INVENTORY.md`](research/firmware/notes/FIRMWARE_INVENTORY.md) — SIGMA fp Ver.5.02 — 韌體完整清單 / 全量反編譯存底
- [`FORMAT.md`](research/firmware/notes/FORMAT.md) — SIGMA fp — FP__V502.BIN 韌體格式 (Ver.5.02, 2023-08-03)
- [`HIDDEN_FEATURES.md`](research/firmware/notes/HIDDEN_FEATURES.md) — SIGMA fp Ver.5.02 — 韌體隱藏 / 未公開功能調查
- [`SECURITY.md`](research/firmware/notes/SECURITY.md) — SIGMA fp Ver.5.02 — 韌體完整性 / 簽章分析

### `research/imaging-hw/` — 影像處理硬體 —— 無損 JPEG、RAW 壓縮、縮減路徑、影像通道、色彩
8 份筆記 · `captures/` 38 MB · `color-characterisation/` 780 MB · `dctl/` 18 KB · `fhd_compression/` 98 KB

- [`ADAPTIVE_FRAME_COMPRESSION.md`](research/imaging-hw/notes/ADAPTIVE_FRAME_COMPRESSION.md) — 抽幀壓縮 — 可行性與「能否和 OpenGate 拆開」的評估
- [`CRCT_REDUCTION_PATHS.md`](research/imaging-hw/notes/CRCT_REDUCTION_PATHS.md) — CRCT 的縮減路徑:Hbin / Hbin2 / Vbin 與 RWZM 不是同一組
- [`REDUCTION_INVENTORY.md`](research/imaging-hw/notes/REDUCTION_INVENTORY.md) — fp 的縮減手段完整清單(感測器 / hbin-vbin / RWZM 三層)
- [`CHAR_TIFF_HOWTO.md`](research/imaging-hw/notes/CHAR_TIFF_HOWTO.md) — DaVinci 解碼特徵化 — 操作說明(回讀 16-bit TIFF)
- [`COLOR_SCIENCE.md`](research/imaging-hw/notes/COLOR_SCIENCE.md) — SIGMA fp — 色彩科學完整反編譯
- [`HW_LOSSLESS_JPEG_CODEC.md`](research/imaging-hw/notes/HW_LOSSLESS_JPEG_CODEC.md) — SIGMA fp Ver5.02 — Hardware Lossless-JPEG codec (standalone-ca
- [`IMAGE_CHANNELS.md`](research/imaging-hw/notes/IMAGE_CHANNELS.md) — fp 影像通道地圖 — 哪塊 buffer 能解、哪塊不能
- [`RAW_COMPRESSION_RESEARCH.md`](research/imaging-hw/notes/RAW_COMPRESSION_RESEARCH.md) — SIGMA fp Ver 5.02 — 相機端 RAW 壓縮開發研究

### `research/imx410/` — 感光元件 —— ISO/增益、讀出雜訊、時序、SLVS-EC
6 份筆記 · 20 個腳本/卡片 · `analysis/` 122 KB · `captures/` 942 MB

- [`SENSOR_MODE_METADATA.md`](research/imx410/notes/SENSOR_MODE_METADATA.md) — IMX410 70 modes:欄位、16 geometry 家族、24 register 指紋與 2K/3K/4K OG 畫質路線 — 含時序記錄的感測器視窗欄位與 mode 131/98 比對 (2026-09-15)
- [`FRAME_RATE_IS_VMAX.md`](research/imx410/notes/FRAME_RATE_IS_VMAX.md) — 幀率是 vmax,不是模式 (2026-09-10, USB shell 實機驗證)
- [`ISO_DR_UNDERSTANDING.md`](research/imx410/notes/ISO_DR_UNDERSTANDING.md) — SIGMA fp — ISO / 增益 / 動態範圍:理解與實務
- [`ISO_FIRMWARE_COMPLETE.md`](research/imx410/notes/ISO_FIRMWARE_COMPLETE.md) — SIGMA fp (Ver.5.02, Sony IMX410) — ISO / Gain Firmware, Comple
- [`ISO_HANDLING.md`](research/imx410/notes/ISO_HANDLING.md) — SIGMA fp — ISO / 增益處理完整反編譯
- [`SENSOR_READOUT_NOISE_2026-09-11.md`](research/imx410/notes/SENSOR_READOUT_NOISE_2026-09-11.md) — 讀出雜訊、縮減方式、以及一個沒解開的矛盾

### `research/interfaces/` — 介面硬體 —— 熱靴、USB、HDMI、PTP、GIMBAL
13 份筆記 · 1 個腳本/卡片

- [`EGRESS_MAP.md`](research/interfaces/notes/EGRESS_MAP.md) — SIGMA fp Ver.5.02 — 控制與資料出口總表（EGRESS MAP）
- [`FP_USB_PTP_SHARED_PATH_2026-09-16.md`](research/interfaces/notes/FP_USB_PTP_SHARED_PATH_2026-09-16.md) — 12-byte PTP SessionNotOpen、native/worker 共用 TRB 路徑及不可推論命令未執行的界線
- [`GIMBAL_MANUAL.md`](research/interfaces/notes/GIMBAL_MANUAL.md) — SIGMA fp — GIMBAL 外控指令說明書
- [`HDMI_RAW.md`](research/interfaces/notes/HDMI_RAW.md) — SIGMA fp Ver.5.02 — HDMI RAW 輸出路徑分析
- [`HDMI_RAW_FORMAT.md`](research/interfaces/notes/HDMI_RAW_FORMAT.md) — SIGMA fp Ver.5.02 — HDMI RAW 外錄格式（模式矩陣 / 連結層 / 酬載）
- [`HOT_SHOE.md`](research/interfaces/notes/HOT_SHOE.md) — 熱靴:觸點、匯流排與協定
- [`PTP_CINEMADNG.md`](research/interfaces/notes/PTP_CINEMADNG.md) — SIGMA fp — 用 PTP 傳輸 CinemaDNG 影片？調查結果
- [`PTP_OPCODES.md`](research/interfaces/notes/PTP_OPCODES.md) — SIGMA fp — PTP vendor 指令 opcode / 參數格式 / GIMBAL 流程
- [`PTP_READ_USER_EXPOSURE.md`](research/interfaces/notes/PTP_READ_USER_EXPOSURE.md) — 說明書 — 透過 USB/PTP 讀取使用者原本的 Av/Tv/ISO(路線 A:ePtpSaveMode)
- [`USB_COMPLETION_PATHS.md`](research/interfaces/notes/USB_COMPLETION_PATHS.md) — USB bulk-transfer completion delivery — EP05 OUT / EP84 IN (fp
- [`USB_COMPOSITE_MAP.md`](research/interfaces/notes/USB_COMPOSITE_MAP.md) — SIGMA fp Ver.5.02 — USB composite / mode map (PTP vs vendor co
- [`USB_COMPOSITE_RECIPE.md`](research/interfaces/notes/USB_COMPOSITE_RECIPE.md) — SIGMA fp Ver.5.02 — USB COMPOSITE RECIPE (PTP class-0x06 + ven
- [`USB_GADGET_REGISTRATION.md`](research/interfaces/notes/USB_GADGET_REGISTRATION.md) — USB gadget 正規註冊路徑 — RE 進行中 (2026-08-25)
- [`USB_MODES_COMPLETE.md`](research/interfaces/notes/USB_MODES_COMPLETE.md) — SIGMA fp USB 模式完整解析 (Ver 5.02) — 2026-08-25

### `research/lens/` — 鏡頭 —— 資料存取、校正、畸變表
7 份筆記 · 1 個腳本/卡片 · `captures/` 10 MB

- [`AUTORUN_LENSDUMP.md`](projects/fp-af-assist/notes/lens/AUTORUN_LENSDUMP.md) — AutoRun.txt — 用 mem save 把鏡頭資料 dump 到 SD 卡
- [`DISTCONVERTER_MATH.md`](research/lens/notes/DISTCONVERTER_MATH.md) — SIGMA fp — DistConverter 畸變校正的內插數學(反編譯還原)
- [`LENS_BLOCK_API.md`](projects/fp-af-assist/notes/lens/LENS_BLOCK_API.md) — 鏡頭資料存取 — 借用韌體自己的 API（含握手）
- [`LENS_CALIBRATION.md`](research/lens/notes/LENS_CALIBRATION.md) — SIGMA fp — 鏡頭校正 / 感光元件校正資料 + AF log 「加密」澄清
- [`LENS_DATA_ACCESS.md`](projects/fp-af-assist/notes/lens/LENS_DATA_ACCESS.md) — SIGMA fp — 鏡頭資料:關鍵參數 + PTP/GIMBAL 可讀性
- [`LENS_DISTORTION_TABLE.md`](research/lens/notes/LENS_DISTORTION_TABLE.md) — 鏡頭畸變表 — 相機端取得畸變係數 (2026-09-05)
- [`SOP_LENS_EXTRACT.md`](projects/fp-af-assist/notes/lens/SOP_LENS_EXTRACT.md) — SOP — 任意鏡頭資料擷取(給 AI 對焦程式用)

### `research/other/` — 其他 —— 不屬於上面任何一類;長大就代表分類該調整
3 份筆記 · `external/` 4 MB

- [`CAMERA_STATE_SOURCES.md`](research/other/notes/CAMERA_STATE_SOURCES.md) — SIGMA fp Ver.5.02 — Live Camera-State Sources for the USB Shel
- [`GHIDRA_GIMBAL_CHECKLIST.md`](research/other/notes/GHIDRA_GIMBAL_CHECKLIST.md) — 互動式 Ghidra 追 GIMBAL opcode / 對焦 dispatch — 操作 Checklist
- [`TODO_NEXT.md`](research/other/notes/TODO_NEXT.md) — 明天任務列表（SIGMA fp — USB shell / DFD）

### `research/rtos/` — TK-OS —— 任務 ABI、優先權、子系統
3 份筆記

- [`SUBSYSTEMS.md`](research/rtos/notes/SUBSYSTEMS.md) — SIGMA fp Ver.5.02 — 子系統分析
- [`TASK_ABI_VERIFIED.md`](research/rtos/notes/TASK_ABI_VERIFIED.md) — SIGMA fp (Ver.5.02) TK-OS Task-Creation ABI — VERIFIED
- [`TASK_PRIORITY_MAP.md`](research/rtos/notes/TASK_PRIORITY_MAP.md) — SIGMA fp (Ver.5.02) TK-OS Task PRIORITY Map

### `research/slimRAW/` — 機身端無損壓縮 —— 編碼器規格、tile 幾何、尺寸帳
1 份筆記 · 7 個腳本 · 3 組上機探針(在 `fpSup/raw/`)· `captures/` 1.3 MB

- [`INCAMERA_LOSSLESS.md`](research/slimRAW/notes/INCAMERA_LOSSLESS.md) — fp 錄影中的機身無損壓縮 —— 編碼器規格與尺寸帳(引擎成本函數上機實測 ±2 µs:201.8 Mpix/s + 40.9 µs/tile + 2.18 ms/呼叫;tile 幾何值 21–32%;壓縮比 2.525:1 由引擎 size table 直接量出、滿載可消除 65–145 MB/s;主機端端到端壓出 bit-exact 的 Compression=7)

### `research/storage/` — 儲存 —— SD/SSD 速度與延遲
2 份筆記

- [`SD_WRITE_LATENCY_MEASURED.md`](research/storage/notes/SD_WRITE_LATENCY_MEASURED.md) — 錄影中 SD 寫入延遲 —— 實測 692 ms (2026-08-25)
- [`STORAGE_SPEED.md`](research/storage/notes/STORAGE_SPEED.md) — 儲存速度:韌體自帶的跑分,與實測數字 (2026-09-13)

### `research/ui/` — GUI 共用機械 —— 資源解析、XCI/NBR、Thumb hook
1 份總覽 · 11 個通用工具 · `captures/` 25 KB

- [`README.md`](research/ui/README.md) — GUI 資源系統、L8A8/LZ4 XCI、NBR 1.5、逐筆 timing gate、無干擾 display capture 與後解析圖塊備援

## projects —— 專案耦合

### `projects/fp-af-assist/` — 單框、小範圍實驗性對比對焦

- [`README.md`](projects/fp-af-assist/README.md) — 第一版進度、操作方式、驗證與限制
- [`notes/VALIDATION_2026-09-16.md`](projects/fp-af-assist/notes/VALIDATION_2026-09-16.md) — 只讀 bridge、20-pulse／停止流程、USB 中斷與 RAM 還原證據
- [`notes/TRANSPORT_AUDIT_2026-09-16.md`](projects/fp-af-assist/notes/TRANSPORT_AUDIT_2026-09-16.md) — 原始錯誤封包、本機 diagnostic daemon 與慢速取樣實驗
- [`notes/HOOK_SAMPLING_PLAN_2026-09-16.md`](projects/fp-af-assist/notes/HOOK_SAMPLING_PLAN_2026-09-16.md) — 有界相機端記錄、批次讀回與新掛點／安全卸載待辦（未部署）
- [`notes/HOOK_ABI_AUDIT_2026-09-16.md`](projects/fp-af-assist/notes/HOOK_ABI_AUDIT_2026-09-16.md) — 固定 publication callsite 的 SP／LR、live registers 與最小 leaf recorder 契約
- [`notes/HOOK_LIFECYCLE_AUDIT_2026-09-16.md`](projects/fp-af-assist/notes/HOOK_LIFECYCLE_AUDIT_2026-09-16.md) — 原廠 slot disable／scheduler ready 配對與 hook 安裝卸載前提
- [`fp_af_assist.py`](projects/fp-af-assist/fp_af_assist.py) — 明確分開離線展示、只讀實機探測與 AF 介面

### `projects/gyro-sup/` — 機身端陀螺儀記錄器
7 份筆記 · 49 個腳本/卡片 · `archives/` 543 KB · `assets/` 18 MB · `captures/` 5.43 GB · `releases/` 962 KB · `releases-dev/` 4 MB

- [`GYROFLOW_ORIENTATION_SOLVED.md`](projects/gyro-sup/notes/GYROFLOW_ORIENTATION_SOLVED.md) — Gyroflow 朝向字串 — 定案 `xyz`(三軸各自驗證)
- [`GYRO_FOLLOW_THE_FACTORY.md`](projects/gyro-sup/notes/GYRO_FOLLOW_THE_FACTORY.md) — 照抄原廠:錄影開始、緩衝、寫入(2026-09-05 定案的方向)
- [`GYRO_IMU_GYROFLOW.md`](projects/gyro-sup/notes/GYRO_IMU_GYROFLOW.md) — SIGMA fp Ver.5.02 — IMU (gyro/accel) data path + Gyroflow feas
- [`GYRO_RESEARCH.md`](projects/gyro-sup/notes/GYRO_RESEARCH.md) — fpGyroSup 陀螺儀研究總整理
- [`ONCAMERA_GCSV_AND_LENS_PROFILE.md`](projects/gyro-sup/notes/ONCAMERA_GCSV_AND_LENS_PROFILE.md) — 機身端 GCSV 產生 + 主機端 lens profile 產生器 (2026-08-24)
- [`SIGMA_FP_INTERNAL_GYRO_ARCHIVE_2026-08-18.md`](projects/gyro-sup/notes/SIGMA_FP_INTERNAL_GYRO_ARCHIVE_2026-08-18.md) — SIGMA fp Ver.5.02 內部陀螺儀／Gyroflow 研究歸檔
- [`STREAM_DROP_INVESTIGATION.md`](projects/gyro-sup/notes/STREAM_DROP_INVESTIGATION.md) — GCSV-stream 掉針調查日誌 (2026-09-02)

### `projects/hdmi-recorder/` — 自製 HDMI RAW 錄影機
2 份筆記

- [`HDMI_RAW_RECORDER_BUILD.md`](projects/hdmi-recorder/notes/HDMI_RAW_RECORDER_BUILD.md) — SIGMA fp — 自製 HDMI RAW → CinemaDNG 錄影機 建置 SOP
- [`RECORDER_SPEC.md`](projects/hdmi-recorder/notes/RECORDER_SPEC.md) — SIGMA fp — 自製 HDMI RAW → CinemaDNG 錄影機 規格書

### `projects/open-gate/` — 2K / 3K / 4K OpenGate
16 份筆記 · `build/` 38 MB · `test-build/` 3 MB

- [`CANVAS_IS_NOT_THE_SETTINGS_BLOCK.md`](projects/open-gate/notes/CANVAS_IS_NOT_THE_SETTINGS_BLOCK.md) — 畫布不是設定 block (2026-09-10, USB shell 實機驗證)
- [`CANVAS_MOVED_AT_C043A19C.md`](projects/open-gate/notes/CANVAS_MOVED_AT_C043A19C.md) — 畫布動了 —— hook 在 `0xC043A19C` (2026-09-10, USB shell 實機驗證)
- [`FORMAT_REGISTRY_DESIGN.md`](projects/open-gate/notes/FORMAT_REGISTRY_DESIGN.md) — 格式註冊架構 —— 讓 OG3K 成為真正的第三個選項
- [`LIVE_VIEW_DISPLAY_CHAIN.md`](projects/open-gate/notes/LIVE_VIEW_DISPLAY_CHAIN.md) — LCD 顯示鏈:OG3K 的 3:2 取景是怎麼修好的
- [`OG14_FEASIBILITY.md`](projects/open-gate/notes/OG14_FEASIBILITY.md) — 14-bit OG:full-read約19.2p上限、29.97p已知路線不可交付、RAW14 2x高風險研究
- [`OG2K_PLAN.md`](projects/open-gate/notes/OG2K_PLAN.md) — OG2K:M139 quiet 基底、幾何、格率與整合步驟
- [`FLICKER_25P_INVESTIGATION.md`](projects/open-gate/notes/FLICKER_25P_INVESTIGATION.md) — 25p 螢光燈閃爍回報:量到 1/60(=150°),我方重現不了;附 OG3K+Super35 錄影失敗 (2026-09-15)
- [`OG3K_8BIT_10BIT_FALLS_BACK_TO_UHD.md`](projects/open-gate/notes/OG3K_8BIT_10BIT_FALLS_BACK_TO_UHD.md) — v0.2.1a 缺陷:8/10-bit 品質下 OG3K 退回 UHD30 (2026-09-15)
- [`OG3K_IS_THE_STILLS_PATH.md`](projects/open-gate/notes/OG3K_IS_THE_STILLS_PATH.md) — 韌體本來就有 3K:那是 S 尺寸 12-bit 靜態照片的路徑
- [`OG3K_PLAYBACK_PROFILE_CLASSES.md`](projects/open-gate/notes/OG3K_PLAYBACK_PROFILE_CLASSES.md) — OG3K 回放:profile 的「類別」才是關鍵(2026-09-13,讀源碼)
- [`OG3K_RWZM_AND_BUILD_PIPELINE.md`](projects/open-gate/notes/OG3K_RWZM_AND_BUILD_PIPELINE.md) — RWZM 是 open gate 的關鍵,以及建置流程的四個教訓
- [`OG3K_WHAT_WAS_WRONG.md`](projects/open-gate/notes/OG3K_WHAT_WAS_WRONG.md) — OG3K:這次調查的答案,以及我錯在哪裡
- [`OG_2K_3K_4K_QUALITY_OPTIONS.md`](projects/open-gate/notes/OG_2K_3K_4K_QUALITY_OPTIONS.md) — 三種 OG 畫質階梯、M151-full24 4K 組合、頻寬與測試矩陣
- [`OPEN_GATE_EXPLORATION_ARCHIVE.md`](projects/open-gate/notes/OPEN_GATE_EXPLORATION_ARCHIVE.md) — open gate
- [`RECORDING_GEOMETRY_AND_LENS_PROGRAM.md`](projects/open-gate/notes/RECORDING_GEOMETRY_AND_LENS_PROGRAM.md) — 錄影幾何位址 + 機內鏡頭程式 (2026-08-25, USB shell 實機驗證)
- [`RECORDING_REGRESSION_2026-09-12.md`](projects/open-gate/notes/RECORDING_REGRESSION_2026-09-12.md) — 事故:改 live view 毀掉數十段錄影素材
- [`SHUTTER_ANGLE_EXPOSURE_2026-09-15.md`](projects/open-gate/notes/SHUTTER_ANGLE_EXPOSURE_2026-09-15.md) — OG3K 快門角度/速度曝光差異、根因與修正
- [`UI_STATE2_HAS_NO_ICON.md`](projects/open-gate/notes/UI_STATE2_HAS_NO_ICON.md) — OG3K UI:360-record 候選、AutoRun exact-hit bitmap、舊探針互斥與實機 gate

### `projects/usb-shell-sup/` — USB shell 平台本身
12 份筆記 · 5 個腳本/卡片 · `_retired_2026-08-25/` 565 KB · `captures/` 33 KB · `cards/` 50 KB · `fpshell_tool/` 793 KB · `lib/` 161 KB · `usbshell/` 163 KB

- [`HOOKPUSH_PACING.md`](projects/usb-shell-sup/notes/HOOKPUSH_PACING.md) — hook-push 的節奏規則 — BATCHPUSH 靜默期
- [`RAW_GRAB.md`](projects/usb-shell-sup/notes/RAW_GRAB.md) — fp — 用 AutoRun/mem save 抓 RAW 幀(全幅 / live-view)
- [`RAW_PUSH.md`](projects/usb-shell-sup/notes/RAW_PUSH.md) — SIGMA fp Ver.5.02 — RAW FRAME PUSH channel (camera-push raw ov
- [`RECORD_SHELL_COEXIST_RESOLVED.md`](projects/usb-shell-sup/notes/RECORD_SHELL_COEXIST_RESOLVED.md) — 錄影 + USB shell 共存 — 已解決(真因訂正)
- [`SHELL_COEXIST.md`](projects/usb-shell-sup/notes/SHELL_COEXIST.md) — SIGMA fp Ver.5.02 — USB Shell Worker ↔ Normal-Operation Coexis
- [`SHELL_COMMANDS.md`](projects/usb-shell-sup/notes/SHELL_COMMANDS.md) — SIGMA fp — Debug/Factory Shell 指令表(AutoRun 能玩什麼)
- [`SHELL_MEM_RANGE_LIMITS.md`](projects/usb-shell-sup/notes/SHELL_MEM_RANGE_LIMITS.md) — ⚠️ USB shell 的 mem 讀寫有位址範圍限制 (2026-08-25)
- [`TELEMETRY_HOOK.md`](projects/usb-shell-sup/notes/TELEMETRY_HOOK.md) — SIGMA fp Ver.5.02 — TELEMETRY HOOK design (per-frame fast-stat
- [`USB_SHELL.md`](projects/usb-shell-sup/notes/USB_SHELL.md) — USB shell — 挾持 PTP gadget 的端點 (2026-08-25 實機驗證通過)
- [`USB_SHELL_HOOK_WORK_POSTMORTEM.md`](projects/usb-shell-sup/notes/USB_SHELL_HOOK_WORK_POSTMORTEM.md) — USB shell 做 hook 工作 —— 一輪五次凍結的檢討 (2026-08-25)
- [`USB_SHELL_INDEX.md`](projects/usb-shell-sup/notes/USB_SHELL_INDEX.md) — USB shell 筆記索引 — 哪一份還算數 (2026-09-09)
- [`V27_FREEZE_ROOTCAUSE.md`](projects/usb-shell-sup/notes/V27_FREEZE_ROOTCAUSE.md) — SIGMA fp Ver 5.02 — v27 USB-shell 凍結根因(完整分析)

## 兩棵樹之外

```
fpSup/            產品與工具。**唯一發佈到 GitHub(ijigen/fpSup)的資料夾**
firmware/         FP__V502.bin —— 一切的源頭
out/              反編譯輸出。衍生,可從 firmware/ 重建
ghidra_proj/      Ghidra 專案。衍生
tools/            Ghidra / JDK / 下載。第三方,不是我們的東西
worktrees/        三個別的 session 的 clone,有未提交的工作,還沒收拾
lenscorrect-ofx/  獨立的 OFX 外掛,自己的 repo
notes-history-before-restructure.bundle   舊 notes repo 的完整 git 歷史
```

分界:`research/` 與 `projects/` 裡的東西刪了就沒了;上面這些要嘛能重建、要嘛是別人的。

## 版控

| | 範圍 | 去處 |
|---|---|---|
| **GitHub** `ijigen/fpSup` | 只有 `fpSup/` | 公開 |
| **git:3000** | `research/` `projects/` `fpSup/` `firmware/`(排除衍生物與第三方) | 私有 |

---

110 份筆記 · 素材 2.51 GB + 5.51 GB。
