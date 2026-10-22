# SIGMA fp RE — 總索引

> **給之後的 session:先讀這份。**

> **不公開的東西放哪裡**(2026-10-23 定;`research/`、`projects/`、`fpSup/` 都會上 GitHub)
> - fp 韌體映像、反編譯、Ghidra → 根目錄 `out/`、`firmware/`、`ghidra_proj/`
> - 其他廠牌的資料,**包括拿 fp 跟它對照的筆記** → 根目錄該廠牌的資料夾(`zcam_e2f6/`、`bmcc6k/`…)
> - 夾帶韌體的 dump、私人內容、別人沒說可公開的資料 → **該專案底下的 `private/`**(任何深度都不會被 commit)
> - 筆記引用 `private/` 的檔案時寫明「不公開、怎麼自己取得」
> - commit 前有自動檢查,夾帶韌體程式碼或反編譯輸出會被擋下

> **參考:設定區的風險**(原「第一守則」,2026-10-01 訂、2026-10-22 起只當參考)
> 相機設定區會跨關機保存,寫入原廠不支援的值前請先調查清楚。
> 過去的分析見 [research/SETTINGS_AREA_FIRST_RULE.md](research/SETTINGS_AREA_FIRST_RULE.md)。

2026-09-27 使用者指定 AF 筆記集中於 **[projects/fp-af-assist](projects/fp-af-assist/README.md)**。
先讀 [完整開發清單](projects/fp-af-assist/PLAN.md) 與 [全部筆記索引](projects/fp-af-assist/notes/README.md)。
此項優先於下方研究／專案的通用分類；AF 程式與原始證據仍留原位，舊筆記路徑只作轉向入口。

## ⚠ 公開頁面核對(2026-10-04 更新)

`fpSup/` 是公開站；本機文件修正不等於已發布。

- **`fpSup/projects/ui-sup.md`** —— 「未解」仍寫著文字顏色編碼不明、只確定兩個值。
  樹裡已解:顏色是 **256 筆 AYUV 調色盤的索引**(表 `0xC0B520BC`、索引在 `0xC0BB1208`
  低位元組),逐索引拍照驗過 245/256 在 4 階以內。見
  [`research/display/notes/CENTER_LINE.md`](research/display/notes/CENTER_LINE.md) §9。
- **Sensor Lab 本機文件已更新，未發布。** 封存 r80 的固定 cave 配置已確認
  覆寫原廠資料；舊配置的 USB 安裝與 AXIS 實機推送仍封鎖。新建卡器將
  核心搬入 USER 記憶體，cave 只放執行期 veneer；整卡離線模擬還原
  普通版 290 筆、debug 版 297 筆 journal 記錄，20,480 B 原廠 C073 資料
  保持原樣。已寫卡的 r81 按 REC 立即凍結，成品錄影 picker 讀錯 profile ID；
  [r83 修正候選](projects/res-lab/cards/20261004-b25-menu-r83-picker-reloc/debug/)
  通過離線檢查，尚未寫卡或重新上機錄影。MODE 格率篩選也已改為只取 FILTER。
  原頁的「研究完成」已改成原型，
  `0xC37CE210` 改列下游快取；反證見
  [CANVAS_IS_NOT_THE_SETTINGS_BLOCK §13](projects/open-gate/notes/CANVAS_IS_NOT_THE_SETTINGS_BLOCK.md)。
  最新 Custom Sensor 狀態、歷史測試卡與未完成工作集中於
  **[projects/res-lab](projects/res-lab/README.md)**；程式仍沿用 `projects/open-gate/build/imx410_*`。

## 這棵樹怎麼分

唯一的判準是**壽命**:這份知識在專案結束之後還有用嗎?

```
research/<主題>/   有 —— 相機本身的事實,換個專案還是成立
projects/<專案>/   沒有 —— 只在那件工作的脈絡裡有意義
<他牌相機>/        bmcc6k/ bmd_gen1/ sony_a7m3/ zcam_e2f6/ —— 別台相機的韌體與反編譯,放最外層
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
此目錄保留量測／重播工具與原始證據；AF 筆記正文已集中至 `projects/fp-af-assist/notes/`。`fp-af-explainer/` 為歷史說明工具。

- [`CROSSCAM_PDAF_FEASIBILITY_2026-09-27.md`](projects/fp-af-assist/notes/research/CROSSCAM_PDAF_FEASIBILITY_2026-09-27.md) — ★ PDAF 原始資料重審：fp dispatch／RAW、Sony A7III／A7C、Nikon；四個門檻及停止規則
- [`ZCAM_AF_REFERENCE_2026-09-27.md`](zcam_e2f6/notes/ZCAM_AF_REFERENCE_2026-09-27.fp-af-assist.md) — Z CAM 可讀 CAF／SAF、ISP→FV、重搜與 ROI：失敗機制參考，不作性能標竿
- [`NON_PDAF_CAMERA_REFERENCE_2026-09-27.md`](projects/fp-af-assist/notes/research/NON_PDAF_CAMERA_REFERENCE_2026-09-27.md) — Panasonic／Leica 方法與加密限制；BMCC 6K 新版 PDAF 分類及可讀控制契約
- [`FP_AF_FIRMWARE_INTERVENTION_MAP_2026-09-27.md`](projects/fp-af-assist/notes/research/FP_AF_FIRMWARE_INTERVENTION_MAP_2026-09-27.md) — fp 可達 CDAF／AAT 接點、觀測欄位、時間語意與首版決策介面
- [`FP_GEOMETRY_DFD_FUSION_2026-09-27.md`](projects/fp-af-assist/notes/research/FP_GEOMETRY_DFD_FUSION_2026-09-27.md) — ★ 最新分工：首次合焦建立錨點，face／AAT 幾何判接近／遠離，DFD 若成立估離焦量，CDAF 確認

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
3 份筆記 · 23 個腳本/卡片 · `captures/` 20 KB

- [`DISPLAY_OSD_MAP.md`](research/display/notes/DISPLAY_OSD_MAP.md) — SIGMA fp Ver.5.02 — Display / OSD drawing map
- [`OSD_PERSISTENT_MARKER.md`](research/display/notes/OSD_PERSISTENT_MARKER.md) — 螢幕常態標示（持久 OSD marker）— 為何失敗 + 正解配方
- [`SPLASH_BAND.md`](research/display/notes/SPLASH_BAND.md) — 開機橫幅:主層 ARGB4444 三重緩衝,`display osdfile` 貼原始點陣到左上角、`offset` 就是翻頁;蓋 UI 成立,留電池要把它烤進圖裡
- [`four-box-splash-20260924/`](research/display/four-box-splash-20260924/README.md) — 透明四框載入畫面的離線候選、卡片、預覽與 hash(`BOOT_BANNER.md` 引用的產物)

### `research/firmware/` — 韌體本體 —— 格式、簽章、隱藏功能、開機
9 份筆記

- [`AUTORUN_INTERPRETER_AND_ABORT.md`](research/firmware/notes/AUTORUN_INTERPRETER_AND_ABORT.md) — AutoRun 解譯器,以及怎麼從命令裡把它停掉(含 2026-09-18 實機更正)
- [`BOOT_OPENING_LOGO.md`](research/firmware/notes/BOOT_OPENING_LOGO.md) — SIGMA fp Ver 5.02 — Startup / Boot / Opening Animation (RE rec
- [`COMPRESSION_AND_QR_INSTALL.md`](research/firmware/notes/COMPRESSION_AND_QR_INSTALL.md) — 沒有 LZMA/LZSS 硬體(LZSS 是 IPL 軟體迴圈、壓縮率 49.5%);原廠 QR 只讀設定碼;**計畫:QR 碼接收器**(更新 sup 免電腦,首裝仍需寫卡)
- [`DRAM_SELF_REFRESH_AND_WARM_BOOT.md`](research/firmware/notes/DRAM_SELF_REFRESH_AND_WARM_BOOT.md) — DRAM self-refresh 與暖開機 —— 12 MB 留得住,但位址每次不同;最後沒走這條
- [`FIRMWARE_INVENTORY.md`](research/firmware/notes/FIRMWARE_INVENTORY.md) — SIGMA fp Ver.5.02 — 韌體完整清單 / 全量反編譯存底
- [`FORMAT.md`](research/firmware/notes/FORMAT.md) — SIGMA fp — FP__V502.BIN 韌體格式 (Ver.5.02, 2023-08-03)
- [`HIDDEN_FEATURES.md`](research/firmware/notes/HIDDEN_FEATURES.md) — SIGMA fp Ver.5.02 — 韌體隱藏 / 未公開功能調查
- [`PERSISTENT_STORE_COMMONSAVE.md`](research/firmware/notes/PERSISTENT_STORE_COMMONSAVE.md) — 824 bytes 可以跨電源循環存活的地方 —— XC_CommonSaveData
- [`DIR_ENUM_API.md`](research/firmware/notes/DIR_ENUM_API.md) — 列目錄 API(從 shell `dir` 反組譯):dir_ctor/open/next/dtor、entry 0x238 B、UTF-16 長檔名;2026-10-06 上機驗證(未排序、無 ./..、要跳過 ._*)
- [`SECURITY.md`](research/firmware/notes/SECURITY.md) — SIGMA fp Ver.5.02 — 韌體完整性 / 簽章分析

### `research/imaging-hw/` — 影像處理硬體 —— 無損 JPEG、RAW 壓縮、縮減路徑、影像通道、色彩
8 份筆記 · `captures/` 38 MB · `color-characterisation/` 780 MB · `dctl/` 18 KB · `fhd_compression/` 98 KB

- [`LOSSLESS_DEVELOPMENT_SUMMARY.md`](research/imaging-hw/notes/LOSSLESS_DEVELOPMENT_SUMMARY.md) — ★ lossless 開發資料彙整:管線位置(壓縮之後不能再 hbin/vbin/RWZM)、三項成本模型、串行架構、判定總表;網頁模擬器的計算定義
- [`ADAPTIVE_FRAME_COMPRESSION.md`](research/imaging-hw/notes/ADAPTIVE_FRAME_COMPRESSION.md) — 抽幀壓縮 — 可行性與「能否和 OpenGate 拆開」的評估
- [`SENSOR_REGISTER_DECODE.md`](research/imaging-hw/notes/SENSOR_REGISTER_DECODE.md) — ★ IMX410 模式暫存器:161 筆直線 I²C 寫入(程式碼證實 word k → 固定位址),150/161 已解出用途(合併選擇 0x001C、vblank÷2 0x0016、位深群、讀出速度三檔);幀幾何與時序**不在**這些暫存器裡;更正「98/117 差在合併」——兩者合併暫存器完全相同;**306 個 profile 的 CRCT binning 全部關閉**,合併是感光元件+RWZM 兩級,解掉 PIXEL_MERGE_MEASURED 的「哪一級」未決
- [`CRCT_PATH_SELECTOR_SOLVED.md`](research/imaging-hw/notes/CRCT_PATH_SELECTOR_SOLVED.md) — ★ 選擇器八分支全解;Hbin2 是唯一活著的抽頭、原廠 36 筆在用;hbin 與 RWZM 在 17 個 UHD profile 同時作用
- [`CRCT_REDUCTION_PATHS.md`](research/imaging-hw/notes/CRCT_REDUCTION_PATHS.md) — CRCT 的縮減路徑:Hbin / Hbin2 / Vbin 與 RWZM 不是同一組(⚠ §1b/§1c/§5.6 已被上一份推翻)
- [`REDUCTION_INVENTORY.md`](research/imaging-hw/notes/REDUCTION_INVENTORY.md) — fp 的縮減手段完整清單(感測器 / hbin-vbin / RWZM 三層)(⚠ §4 已被推翻,見上一份)
- [`CHAR_TIFF_HOWTO.md`](research/imaging-hw/notes/CHAR_TIFF_HOWTO.md) — DaVinci 解碼特徵化 — 操作說明(回讀 16-bit TIFF)
- [`COLOR_SCIENCE.md`](research/imaging-hw/notes/COLOR_SCIENCE.md) — SIGMA fp — 色彩科學完整反編譯
- [`HW_LOSSLESS_JPEG_CODEC.md`](research/imaging-hw/notes/HW_LOSSLESS_JPEG_CODEC.md) — SIGMA fp Ver5.02 — Hardware Lossless-JPEG codec (standalone-ca
- [`IMAGE_CHANNELS.md`](research/imaging-hw/notes/IMAGE_CHANNELS.md) — fp 影像通道地圖 — 哪塊 buffer 能解、哪塊不能
- [`RAW_COMPRESSION_RESEARCH.md`](research/imaging-hw/notes/RAW_COMPRESSION_RESEARCH.md) — SIGMA fp Ver 5.02 — 相機端 RAW 壓縮開發研究
- [`color-firmware-20260924/`](research/imaging-hw/color-firmware-20260924/README.md) — fp 私有色彩資料:OFF 模式刻意用單位矩陣(程式+metadata 互證)、矩陣稽核;Sony 對照在 `sony_a7m3/`
- [`colormatrix-ab-20260923/`](research/imaging-hw/colormatrix-ab-20260923/README.md) — CinemaDNG ColorMatrix1/2 A/B 探針:Resolve 解碼是否吃嵌入矩陣(含 A–D 四個 DNG)
- [`native-calibration-20260924/`](research/imaging-hw/native-calibration-20260924/README.md) — 原廠 normal ColorMatrix 用途、SensAdj／白平衡／writer 來源鏈、Resolve A/C 實測、CDNG 297/298
- [`profile-tags-ab-20260925/`](research/imaging-hw/profile-tags-ab-20260925/README.md) — ★ Resolve 實測吃哪幾個 DNG profile tag:**ToneCurve 與 HueSatMap 都有套用**(推翻「只吃 ColorMatrix」);換矩陣只佔 OFF↔Standard 差異的 4%,五個 tag 整組移植才等同用 Standard 錄;矩陣只動飽和色(飽和 0.2–0.35 的 ΔE p99 = 10.2);並對照 Michael Garrett 2023 意見書,附 OFF→ACES/P3/2020 的修正矩陣
- [`off-matrix-firmware-patch-20260926/`](research/imaging-hw/off-matrix-firmware-patch-20260926/README.md) — ★ **OFF 色彩還原 = 2 個 byte 的韌體補丁**(`0x2C4BE4` 74→2C、`0x2C4C98` E4→9C);全 ROM 稽核四個矩陣常數各只被引用一次;靜態與 cDNG 共用 writer;藍 LED 實拍 ΔE ~10、韌體補丁與位元組補丁等價(1.61)
- [`isp-colour-blocks-20260927/`](research/imaging-hw/isp-colour-blocks-20260927/README.md) — ★ ISP 色彩硬體地圖；2026-10-09 補正：具名診斷引用＋descriptor 已釘出 RGBMAT_PL、CUVAREA、CUVCONT、CSUP/ECSUP、C_SAT_C 的 MMIO/shadow；120 筆路由可重現，TMAP 尚不能直接稱 tone mapping。尚未確認任意 3D LUT runtime，不能由缺少名稱否定整顆 ISP 能力。開發入口：[LUT sup](projects/lut-sup/README.md)。

### `research/imx410/` — 感光元件 —— ISO/增益、讀出雜訊、時序、SLVS-EC、像素合併
7 份筆記 · 24 個腳本/卡片 · `analysis/` 122 KB · `captures/` 942 MB

- [`PIXEL_MERGE_MEASURED.md`](research/imx410/notes/PIXEL_MERGE_MEASURED.md) — 感光元件怎麼合併像素 —— 從 RAW 反推(原廠 FHD 用滿 9 個同色感光點,OG2K build 只用 4 個,差 0.53 格)
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

### `research/liveview/` — Live View 色彩、截斷位置與 RAW 監看還原研究


- [`view-lut-format-20260927/`](research/liveview/view-lut-format-20260927/README.md) — ★ fpScope Custom View LUT 的**可載入格式與安全切換協議**:索引表 `0xC0971118`(88×{ptr,id}、間距 4096)、曲線 2048×uint16、值域 0–8190、原廠全部 93.7% 硬切;含 `fpcurve.py`(產生/驗證/比對)、韌體指紋檢查、5 階驗證梯、以及「當前生效是哪條 id」的二分定位法
- [`README.md`](research/liveview/README.md) — LCD 色彩截斷研究結論、linear／stretched tone 訂正、驗證方案；對應 `projects/rawlive/`
- [`upstream-clip-audit.md`](research/liveview/upstream-clip-audit.md) — tone 前截斷追查：preview bin/vbin、gain／matrix、排除錯誤clip候選與下一步來源量測
- [`preview-reduction-audit.md`](research/liveview/preview-reduction-audit.md) — preview／record 分支、306列ROM核對與bin核精度界限
- [`prior-evidence.md`](research/liveview/prior-evidence.md) — 2026-08-16 原始 tone 實驗回查與證據限制
- [`isp-path-audit.md`](research/liveview/isp-path-audit.md) — ISP 區塊訂正、tone 排程、matrix／gain 與待驗證 clipping
- [`display-route-audit.md`](research/liveview/display-route-audit.md) — LCD 末端 CSC、RGB gamma、輸出路由與面板量測界線
- [`bmcc6k-reference.md`](bmcc6k/notes/FP_LIVEVIEW_COMPARISON.md) — BMCC 6K 的 Rec.709／Gen 5／跨通道 LUT 對照；接入 rawview 時的輸入與校準邊界。
- [`zcam-e2f6-reference.md`](zcam_e2f6/notes/FP_LIVEVIEW_COMPARISON.md) — 對照組:Z CAM E2-F6(IMX410)的 LCD shader 全鏈;+3.65 檔硬切、單一矩陣、每台機器的面板校正
- [`audit_tone_curves.py`](research/liveview/audit_tone_curves.py) — 純離線 88 條 ROM 曲線與歷史 2048 點表稽核；JSON／CSV 證據同目錄

### `research/other/` — 其他 —— 不屬於上面任何一類;長大就代表分類該調整
3 份筆記 · `external/` 4 MB(FP3K 交付 + `fpsup-formats-v0.3.0a/` 六列解析度選單卡,2026-09-29 收入;`sigma-fp-supmod-R120/` Julien 的機內無損 cDNG sup + 拆解 [ANALYSIS.md](research/other/external/sigma-fp-supmod-R120/ANALYSIS.md)、解析度與 14-bit [JULIEN_14BIT_AND_MODES.md](research/other/external/sigma-fp-supmod-R120/JULIEN_14BIT_AND_MODES.md),2026-10-03 收入)

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
3 份筆記 · 14 個通用工具 · `captures/` 25 KB

- [`UI_NAVIGATOR.md`](research/ui/UI_NAVIGATOR.md) — ★ **原生 UI 的進入點**:五層與「讀取時機才重要」、六條介入路線與代價、九個陷阱、模擬器現況與最大槓桿(`0xC05E6400` 尚未離線化);附 `ui_map.json` 與 `tools/uinav.py`(位址／頁表／字串池／圖示／owner 一次查,19 項離線測試)
- [`UI_MODS_INVENTORY.md`](research/ui/UI_MODS_INVENTORY.md) — 誰改過 UI 的全部清單:原生 UI(OG3K／OG2K、**Formats 六列 v0.3.0a**、fpLossless 離線、FP3K)、疊圖(display 指令、lachgil module platform、sigma-fp-lab FC)、只讀狀態(wjhrdy Indoor PR)
- [`NBU_RECORD_FORMAT.md`](research/ui/NBU_RECORD_FORMAT.md) — ★ **格式參考**:NBU(`0xC18C0460` v1.9)與 NBR(`0xC0D22400` v1.5)同格式;記錄都是 `{BE tag, BE size, body}`;解析 context 欄位表、四個讀取方法;逐 tag token 文法(`0x1000B` 已逐欄,全 UI 11,383 筆零剩餘);每條標註證據等級
- [`RESOURCE_REPLACEMENT.md`](research/ui/RESOURCE_REPLACEMENT.md) — ★★ **2026-09-29 實機定案:加一列完全不用 hook**(位元深度 3→4、格率 9→10 已上機,畫得出也選得到);做法是**原地改那份 CSV**,⚠ **repoint 與長度欄在執行期都是死的**(handle 開機就解析完發出去了);失敗真因是 CSV 形式 —— **最後一列的結尾 CRLF 不能省**、騰空間要整欄拿掉;原文:`0xC0D22400` 的 NBR 容器、`0xC0D4D9BC` 起 2259 筆排序目錄 `{fnv1a(路徑), 名稱池位移, 資料位移, 長度}`;**整個選單是 195 個 `.cvm` CSV**,解析度列表就是 89 bytes 的 `B2_5_4.cvm`(兩列);工具算出的補丁與 fpSup-Formats 實機寫的逐位元組相同;**整條資料鏈已解**:CSV 欄位由表頭決定(13 種)、`Enabled=0,0` 就是灰掉、`_excl` 是烤好的灰掉版、`.nloc` 17 語 46,376 筆字串 key 全對、**TEXT 可以直接寫字面文字所以加一列不用動字串表**
- [`BLANK_AFTER_SELECT.md`](research/ui/BLANK_AFTER_SELECT.md) — ★ **選完空白的解法,不用 hook**:enum→display state 靠 326 支小 ARM 葉函式,改**三個立即值**(movw/movt 指到自己的配對表 + `mov r2,#N` 改組數)就好;工具算出的三個字與 fpSup-Formats 實機寫的**逐位元組相同**;配對表每次求值都重讀所以立刻生效
- [`WHY_NOTHING_CHANGED.md`](research/ui/WHY_NOTHING_CHANGED.md) — ★ **補丁下去了畫面沒變**:六個原因按機率排、每個都附「怎麼分辨」;最小實驗是先把某一列文字換成 `ZZZ`(等長、不動目錄與最大值)證明 CSV 真的被讀;「列出現但選不到」=只差 controller 最大值
- [`UI_COST_BY_SCOPE.md`](research/ui/UI_COST_BY_SCOPE.md) — ★ **估價表**:OG3K 的實帳 360 筆記錄(315 筆是 QS companion properties),獨立交叉驗證 218 筆裡 152 筆在 QS、Settings 只有 6;四層價目(OSD 文字 / 清單多一列 3 個寫入 / 多一個設定項 / 既有控制項多一個狀態);對到 fpSensor Lab 的兩個 UI 里程碑;**點出兩個過期的公開頁面**
- [`HOW_CHANGES_TAKE_EFFECT.md`](research/ui/HOW_CHANGES_TAKE_EFFECT.md) — ★ **改完什麼時候生效**:配對表立刻、NBR 資源(CSV/字串/圖示)**開畫面時才讀所以 AutoRun 來得及**、NBU 記錄**每組只解析一次**(target bitmap 全 0 = 遲到不是畫錯);三個寫入各屬哪一層、`0xC1A709BC` 在資源集 `B2_5` 第 1368 筆;journal 關機寫回
- [`MENU_LAYOUT.md`](research/ui/MENU_LAYOUT.md) — ★ 一頁幾格、第七格能不能捲:**清單早就超過六列**(10 個檔案 7 列、12 列的白平衡、129 列的光圈),韌體按長度挑模板(`_4_and_Under` / `_10_and_Over`);**分頁的格數 = `flexBoxItem` 數**(MainB1=5、MainB2=6,完全吻合)所以 6 是資料不是常數,**但原廠沒有超過 6 的 flexbox 分頁,捲不捲是未知**
- [`SUBMENUS.md`](research/ui/SUBMENUS.md) — ★ 按右鍵進子選單:CSV 的 `Popup` 欄就是目的地頁名(123 列、33 個目的地);目的地要同時在 196 筆 GUI 頁表與 221 筆資源集裡(`B5_7` 其實是 `B5_7S`/`B5_7C`);列本身要是 `MenuItem_Jump`／`MenuItem_SelectJump` 並帶 `JumpEvent`,那寫在 tag `0x10003` 物件記錄裡不在 CSV
- [`tools/menu_row_patch.py`](research/ui/RESOURCE_REPLACEMENT.md) — ★ **資料做出第三列:三個寫入、133 bytes、零 hook**(新 CSV + 8 bytes 改指標 + `0xC1A709BC` controller max = 列數−1 的 BE float);只到 Settings,QS 圖磚要另外 152 筆
- [`QUICK_SET.md`](research/ui/QUICK_SET.md) — ★ QS 選單:**沒有 CSV**,四個資源集(`QS_CINE` 14,285 筆記錄);tag `0x1000B` 逐欄解開(全 UI 11,383 筆零剩餘),解析度群組 `b=33` 就是「兩狀態終點」;「多一個解析度狀態」全樹要碰 **218 筆記錄,152 筆在 QS**、Settings 只有 6 筆;訂正 FP3K「QS footer 記錄」其實是資源集起點
- [`tools/nbu_probe/`](research/ui/tools/nbu_probe/README.md) — ★ **記錄格式已解開,可以直接改資料**(32 測試 + 八次變異):每筆記錄都是 `{BE tag, BE size, body}`,純 Python 的 `nbu_format.py` 0.4 秒拆完**221 個資源集／303,597 筆記錄**,**220 個集合首尾相接零誤差**,MainB2 逐位元組往返相同;tag 目錄已定(`0x10003` 物件、**`0x1000B` 影像陣列 11,383 筆**、`0x10002` 配置標頭);`FUN_c05e6400` 本體在 unicorn 裡跑,負責證明解碼正確
- [`README.md`](research/ui/README.md) — GUI 資源系統、L8A8/LZ4 XCI、NBR 1.5、逐筆 timing gate、無干擾 display capture 與後解析圖塊備援

## 他牌相機 —— 最外層

反編譯、韌體、Ghidra 專案都跟著相機放在根目錄;**拿 fp 跟它們對照的筆記也一樣放在各廠牌的資料夾**(例如 `bmcc6k/notes/FP_LIVEVIEW_COMPARISON.md`),不放 `research/`,因為 `research/` 會公開。

### `bmcc6k/` — BMCC 6K：外層、色彩資料已解；核心程式仍受保護

- [`README.md`](bmcc6k/README.md) — 三輪研究的正式入口；樣本為 Camera Setup 10.3 內的相機韌體 10.2.2。
- [`BMCC6K_FIRMWARE.md`](bmcc6k/notes/BMCC6K_FIRMWARE.md) — PID／容器、359 檔解包、MCU 反編譯，並訂正早期「更新檔不可解」的結論。
- [`analysis-20260924/`](bmcc6k/analysis-20260924/README.md) — 完整報告、還原資料、曲線、LUT、工具及雜湊清單。
- [`Live View／Rec.709`](bmcc6k/analysis-20260924/bmcc6k-liveview-rec709-20260924/README.md) — 專屬色彩設定、91 條 ISO 曲線、Gen 5 比對與監看 LUT。
- [`BRAW／CDNG`](bmcc6k/analysis-20260924/bmcc6k-braw-cdng-20260924/README.md) — 控制流程與 FPGA 資產；encoder／writer 尚未還原，未見可信的可見 CDNG writer 證據。

### `bmd_gen1/` — 他牌對照:Blackmagic Design Film Gen 1 色域
1 份筆記 · `matrices.txt` · BMPCC／BMCC 韌體 `res*/`(`.elf`)

- [`BMD_FILM_GEN1_GAMUT.md`](bmd_gen1/notes/BMD_FILM_GEN1_GAMUT.md) — 從 Resolve 本體找到的 Gen1 原色,並用 BMCC Film→Rec709 v2 LUT 驗證(差 0.004);Gen1→XYZ/709/AP0/DWG 矩陣

### `sony_a7m3/` — 他牌對照:Sony ILCE-7M3(A7 III)4.04 `av-cam.bin`

- [`color-firmware-20260924/README.md`](sony_a7m3/color-firmware-20260924/README.md) — 色域／transfer 識別碼、色彩與 gamma 資產稽核;`logs/` 是 Ghidra 反編譯紀錄
- `ghidra/a7m3_v404.gpr` — Ghidra 專案(560 MB)
- fp 這一半的結論在 [`research/imaging-hw/color-firmware-20260924/`](research/imaging-hw/color-firmware-20260924/README.md)
- [`a7m3-re-20260904/`](sony_a7m3/a7m3-re-20260904/work/evidence_audit.md) — 早期完整 A7 III 反編譯(約 5 GB):韌體 `work/firmware/`、解包 `work/unpacked/`、Ghidra `work/ghidra-projects/`、PDAF／IMX410 模式表結果 `outputs/`;2026-09-25 從 `~/Documents/Codex/2026-09-04/` 搬入

### `zcam_e2f6/` — 他牌對照:Z CAM E2-F6(IMX410)—— 韌體完全解開
1 份筆記 · `zcam_fw.py`(解包)、`cube.py`、`elfmap.py`、`xref.py` · `imx410_zcam_tables.json`

- [`ZCAM_E2F6_FIRMWARE.md`](zcam_e2f6/notes/ZCAM_E2F6_FIRMWARE.md) — AES-CFB+ZIP 解包;ZLog2 曲線/原生色域(對官方 DCTL 驗證);IMX410 模式表與暫存器表;2020×1080 = 3×3 合併,和 fp 模式 134 只差 3 個暫存器
- [`color-firmware-20260924/`](zcam_e2f6/color-firmware-20260924/README.md) — DNG ColorMatrix1/2、A／D65 光源、IMX410 多色溫 CCM 表的反編譯與提取(原 `codex/zcam-color-firmware-20260924`;重複的 Ghidra 副本已刪,用 `ghidra/`)

## projects —— 專案耦合

### `projects/lossless-sup/` — fpLossless 固定無損與動態降載研究

- [`notes/PROGRESS_20260930.md`](projects/lossless-sup/notes/PROGRESS_20260930.md) — ★ 當前入口 §10：單工作槽動態壓縮離線實作／ARM 驗證；原生 hold/defer/handoff、全格式容量與選單仍待整合；build 與上機 gate
- [`notes/CURRENT_DEVELOPMENT.md`](projects/lossless-sup/notes/CURRENT_DEVELOPMENT.md) — 9/27 歷史工作快照，已由 9/30 進度取代
- [`notes/ROADMAP.md`](projects/lossless-sup/notes/ROADMAP.md) — 研究 gates 與歷史路線；當前執行順序轉向 9/30 進度
- [`notes/BUFFER_DESIGN.md`](projects/lossless-sup/notes/BUFFER_DESIGN.md) — 單一待壓幀、忙時 RAW、同幀 handoff／無收益 RAW；不建多池，原生所有權尚未證明
- [`notes/NATIVE_BUFFER_PATTERNS.md`](projects/lossless-sup/notes/NATIVE_BUFFER_PATTERNS.md) — 原生 SD descriptor 聚合、CinemaDNG 逐幀完成回呼、RAW 引用計數與 AudioFileWriter 可借規律；訂正舊 writer-chain
- [`notes/COMPRESSION_PRECHECK.md`](projects/lossless-sup/notes/COMPRESSION_PRECHECK.md) — host 抽樣原型與 -91.72% 反例；尚無門檻，不作覆寫／容量安全判斷
- [`notes/IMPLEMENTATION.md`](projects/lossless-sup/notes/IMPLEMENTATION.md) — 逐日歷史實作紀錄
- [`notes/NATIVE_ROW_DONOR.md`](projects/lossless-sup/notes/NATIVE_ROW_DONOR.md) — 原廠選單列 donor 結構
- [`notes/FIXED_POPUP.md`](projects/lossless-sup/notes/FIXED_POPUP.md) — 固定寬度 popup 設計取捨
- [`tools/README.md`](projects/lossless-sup/tools/README.md) — safe host DNG builder、TIFF guard 與四個 fixture 證據
- `probes/` — fplossless 各輪探針與測試(binding、component schema、host trial、menu／row／page／render／registry／variable 邊界);原 `codex/fplossless_*`

### `projects/fp-af-assist/` — CINE 機內連續 AF 與集中研究筆記

- [完整開發清單](projects/fp-af-assist/PLAN.md) — ★ 後續方向、優先序、依賴與驗收，以錄影連續對焦為唯一目標
- [全部筆記索引](projects/fp-af-assist/notes/README.md) — 研究、幾何、DFD、鏡頭、實測與歷史文件

- [`notes/FP_AF_FIRMWARE_ROADMAP_2026-09-27.md`](projects/fp-af-assist/notes/FP_AF_FIRMWARE_ROADMAP_2026-09-27.md) — ★ 最新規劃：合焦錨點、機內幾何方向／AAT／DFD，M0–M5 含 M2-G 主線；EP83 開發觀測
- [`notes/FP_AF_DEVELOPMENT_STATUS_2026-09-27.md`](projects/fp-af-assist/notes/FP_AF_DEVELOPMENT_STATUS_2026-09-27.md) — 三代 AF 開發進度、歷史測量、工具現況與已知限制
- [`README.md`](projects/fp-af-assist/README.md) — 第一版進度、操作方式、驗證與限制
- [`notes/VALIDATION_2026-09-16.md`](projects/fp-af-assist/notes/VALIDATION_2026-09-16.md) — 只讀 bridge、20-pulse／停止流程、USB 中斷與 RAM 還原證據
- [`notes/TRANSPORT_AUDIT_2026-09-16.md`](projects/fp-af-assist/notes/TRANSPORT_AUDIT_2026-09-16.md) — 原始錯誤封包、本機 diagnostic daemon 與慢速取樣實驗
- [`notes/HOOK_SAMPLING_PLAN_2026-09-16.md`](projects/fp-af-assist/notes/HOOK_SAMPLING_PLAN_2026-09-16.md) — 有界相機端記錄、批次讀回與新掛點／安全卸載待辦（未部署）
- [`fp_af_assist.py`](projects/fp-af-assist/fp_af_assist.py) — 明確分開離線展示、只讀實機探測與 AF 介面
- [`CONTINUE_HERE.md`](projects/fp-af-assist/CONTINUE_HERE.md) — 接手入口：機內韌體主線、hook／EP83 開發觀測分工，下文保留歷史交接
- [`highrate/README.md`](projects/fp-af-assist/highrate/README.md) — hook／EP83 資料擷取與研究驗證（未部署）：sender／camera／wait C 碼、boot plan 與離線產物
- `notes/` 另有 `AF_HIGHRATE_*`、`EP83_*`、`HOOK_OWNER_AUDIT`、`USB_ROUTING_REPAIR_AUDIT`(2026-09-16);`transport_native/`、`handoff/`(舊 INDEX 與 skill 備份)

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
16 份筆記 · `build/` 38 MB · `test-build/` 3 MB · `releases/` · `captures/opengate_ev_bug_20260914/` 52 MB(FHD／OG3K 曝光對照 DNG,`research/liveview`、`research/slimRAW` 引用)

- [`releases/og3k-v0.2.2b-rc1/`](projects/open-gate/releases/og3k-v0.2.2b-rc1/README.md) — RC1 卡片、上機測試紀錄與測試前的相機卡備份
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

### `projects/rawlive/` — RAW 的 Live View 即時還原

- [`README.md`](projects/rawlive/README.md) — 從 RAW 來源還原 LCD 色彩與階調；來源驗證、離線參考、機內路徑與效能驗證階段。現況：研究完成，尚無即時原型。
- 通用事實與實驗證據維護於 [`research/liveview/`](research/liveview/README.md)。

### `projects/rawview/` — fp 相機端監看實作與快照

- [`README.md`](projects/rawview/README.md) — rawlive 的相機端實作；已有快照／離線解讀工具與待機記錄，尚無顯示轉換 patch。
- `tools/rv_snapshot.py`、`tools/rv_decode.py` 與 `captures/` 保持 SIGMA fp 的來源與實測資料；BMCC／Z CAM 對照由 [`research/liveview`](research/liveview/README.md) 統一引用。

### `projects/bcolor/` — bCOLOR：fp 監看套 BMCC 6K 色彩

- [`README.md`](projects/bcolor/README.md) — 2026-10-02 由 rawview fork；COLOR 第 17 列 bCOLOR，FC／BC 兩種校準 × BMCC Video／Extended 曲線，DNG 寫對應 ColorMatrix。離線建置與模擬通過，未上機；與 rawview 暫不相容。

### `projects/fc-scale/` — sigma-fp-lab False Color / EL Zone 移植成可合併 payload
- [`FC_SCALE_CARD_AS_VBIN.md`](projects/fc-scale/notes/FC_SCALE_CARD_AS_VBIN.md) — 第三方純 AutoRun 卡(sigma-fp-lab 的 False Color/EL Zone)變成可合併的 payload:cave 沒有 3 KB 可搬,正解是跟分配器要、cave 只留 188 B 錨點;unicorn 驗過 entry 的順序,跟 shell/陀螺/開閘都能合

### `projects/jose-hurtado/` — Jose Hurtado 的 fpSup-Formats(S16/OG3.5K/OG4K)與 Loader v3 版
- [`FORMATS_V3.md`](projects/jose-hurtado/notes/FORMATS_V3.md) — 無原始碼,v0.6.1 二進位搬進 v3 塊成 `31FMT.BIN`(120 MOVW/MOVT + 143 字 fixup、136 筆 claim,含 video clamp 8 字);字串改成標準 uishare 層(檔名 `31FMT`),和 10LOSS 兩種順序同卡;雙胞胎 528 次執行逐事件相同;離線,未上機;工具在 `formats/`,原版在 `formats-v0.6.0|0.6.1/original/`

### `projects/screenflip/` — 螢幕翻轉 sup 的開發卡
原始碼在 `fpSup/screenflip/`;這裡只放上機用的卡(`cards/screenflip-2026-10-04/`)。

### `projects/uishare/` — UI 添加式合併的測試卡
原始碼在 `fpSup/uishare/`;`cards/uishare-2026-10-03/` 是 lossless/rawview/og3k/合併 四組離線卡。

### `projects/usb-shell-sup/` — USB shell 平台本身
14 份筆記 · 3 個腳本/卡片(2026-10-06 已把別的產品搬出,見下) · `_retired_2026-08-25/` 565 KB · `captures/` 33 KB · `cards/` 50 KB · `fpshell_tool/` 793 KB · `lib/` 161 KB · `usbshell/` 163 KB

- [`TODO.md`](projects/usb-shell-sup/notes/TODO.md) — USB shell 代辦 —— 開機配置次數、退路卡撞位址、進度條要量不要猜
- [`FAST_START_2.md`](projects/usb-shell-sup/notes/FAST_START_2.md) — ★ Fast Start 2 技術筆記(英文):瞬開 loader hook `0xC03DA420`、設定區快開、關機寫回 journal、四格畫面、讀回開機路徑、未決問題
- [`AUTORUN_STORE_BOOT.md`](projects/usb-shell-sup/notes/AUTORUN_STORE_BOOT.md) — 開機加速:loader 住在設定區(store-boot)—— 穩態 66 條命令,實機通過
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
archive/          codex/ 整合後剩下的東西:codex-worklog/(各輪 staging／before 快照,只留獨有檔案;MOVES.tsv 記錄每一次搬移與刪除)、misc/
notes-history-before-restructure.bundle   舊 notes repo 的完整 git 歷史
```

分界:`research/` 與 `projects/` 裡的東西刪了就沒了;上面這些要嘛能重建、要嘛是別人的。

## 版控

| | 範圍 | 去處 |
|---|---|---|
| **GitHub** `ijigen/fpSup` | 只有 `fpSup/` | 公開 |
| **git:3000** | `research/` `projects/` `fpSup/` `firmware/`(排除衍生物與第三方) | 私有 |

---

111 份筆記 · 素材 2.51 GB + 5.51 GB。
