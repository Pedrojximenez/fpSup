# fp-af-assist 筆記總索引

更新：2026-09-28。AF 相關筆記正文集中於本專案；57 份外部筆記已搬入。旧位置只留轉向入口，其中兩個行號引用使用相對連結。程式、原始 captures、tool-sources、校驗清單及不可變封存仍在原位。

產品交付目標為 **CINE 錄影時的機內連續對焦**；目前 P0 開發交付先建立 **多接點 hook＋USB 持續資料平台**，降低反覆實驗成本。後續新增計畫、研究或測試結論請直接寫在本專案；舊版本的假設、指令及歷史成績不自動成為目前實作狀態。

## 先讀這些

- [完整後續開發清單](../PLAN.md)
- [P0 多接點資料平台計畫](AF_TELEMETRY_PLATFORM_PLAN_2026-09-27.md)
- [第一個 AF hook／高速通道增量](AF_FIRST_HOOK_CHANNEL_2026-09-27.md) — 同 daemon EP83 host、ARM helper、有限 H/L probe；USB 離線及 shutdown journal 缺口
- [事件／hook 清單](AF_STREAM_HOOK_CATALOG_2026-09-27.md)／[transport 整合缺口](AF_STREAM_TRANSPORT_GAP_2026-09-27.md)
- [高速通道現況核對](AF_CHANNEL_STATE_VERIFY_2026-09-28.md) — EP82 已完善上機（73 MB/s）、EP83 未接通；執行中 daemon 無 EP83
- [關機還原 power-off 物件](AF_POFF_RESTORE_GUARD_2026-09-28.md) — loader journal 不覆蓋執行期字；探針自帶還原物件並雙表驗證，live gate 不再無條件封閉
- [hook 分級、重入偵測與不輪詢匯出](AF_HOOK_STAGED_NOPOLL_2026-09-28.md) — count/record 兩級、`in_body`/`overlaps`、一次視窗一次 bulk；**cache 同步仍是 arming 前置**
- [舊 hook 核對與取用](AF_PRIOR_HOOK_REVIEW_2026-09-28.md) — 同接點的 stage1 子系統、取與不取什麼、尚未納入的位址與 vtable preflight
- [關機還原改走 loader journal](AF_LOADER_CONVENTION_FINDING_2026-09-28.md) — 自帶 power-off 物件已退役；hook 接點以 4-byte 卡片區段宣告，驗證共用 journal
- [I-cache 同步：單核證據](AF_CACHE_COHERENCY_2026-09-28.md) — 舊 stage1 的 live 硬停理由在本機不成立；發布順序仍必要
- [EP83 T0：單一 owner 的一次有界傳輸](EP83_T0_2026-09-29.md) — worker 保有 EP01/EP82，sender 只碰 EP83；332-byte 送出常式與主機 runner，尚未上機
- [最新 CINE 原廠半按基線](FP_CINE_BASELINE_2026-09-27.md)
- [CINE AAT／S1／FullTime AF 路徑](research/FP_CINE_AAT_ACTIVATION_2026-09-27.md)
- [face／AAT 共用幾何與鏡頭呼吸限制](research/FP_CINE_GEOMETRY_INPUTS_2026-09-27.md)
- [接手入口](../CONTINUE_HERE.md)

## 開發、量測與接入稽核（24 份）

- [AF_TELEMETRY_PLATFORM_PLAN_2026-09-27.md](AF_TELEMETRY_PLATFORM_PLAN_2026-09-27.md) — P0 階段、單一 owner、連續 session 與錄影／分析驗收
- [AF_STREAM_HOOK_CATALOG_2026-09-27.md](AF_STREAM_HOOK_CATALOG_2026-09-27.md) — 五個既有來源、最小因果事件、時鐘與丟樣契約
- [AF_STREAM_TRANSPORT_GAP_2026-09-27.md](AF_STREAM_TRANSPORT_GAP_2026-09-27.md) — synthetic-only、五層 single-use、legacy pool 與 host 整合缺口
- [AF_CHANNEL_STATE_VERIFY_2026-09-28.md](AF_CHANNEL_STATE_VERIFY_2026-09-28.md) — 兩條通道分開核對：EP82 實機吞吐 vs EP83 未實收；逐列驗證 hook 增量界線
- [AF_POFF_RESTORE_GUARD_2026-09-28.md](AF_POFF_RESTORE_GUARD_2026-09-28.md) — POFF manager 兩表結構、468-byte 還原物件、武裝前後雙重驗證與突變對照
- [AF_HOOK_STAGED_NOPOLL_2026-09-28.md](AF_HOOK_STAGED_NOPOLL_2026-09-28.md) — capture schema 2：分級、重入偵測、已提交前綴一次匯出與 7 個突變對照
- [AF_PRIOR_HOOK_REVIEW_2026-09-28.md](AF_PRIOR_HOOK_REVIEW_2026-09-28.md) — 舊 stage1／控制台核對：cache 同步 blocker、cave 位址衝突、未納入的來源
- [AF_LOADER_CONVENTION_FINDING_2026-09-28.md](AF_LOADER_CONVENTION_FINDING_2026-09-28.md) — 維護規範：loader 擁有關機還原；兩張清單實際占用；改用卡片區段＋journal 驗證
- [AF_CACHE_COHERENCY_2026-09-28.md](AF_CACHE_COHERENCY_2026-09-28.md) — ICIALLU／MPIDR／SCU／set/way 掃描：單核，因此 shell task 的發布對 AF observer 有效
- [EP83_T0_2026-09-29.md](EP83_T0_2026-09-29.md) — EP83 TRB／physical 7／logical 3、單一 owner 決定、6 個突變對照、上機前缺口
- [AF_HIGHRATE_MEMORY_PLAN_2026-09-16.md](AF_HIGHRATE_MEMORY_PLAN_2026-09-16.md) — fp AF high-rate：RAM／pool 版圖候選
- [AF_HIGHRATE_RECORDER_CONTRACT_2026-09-16.md](AF_HIGHRATE_RECORDER_CONTRACT_2026-09-16.md) — fp 5.02 AF producer 高速 recorder：固定 ABI 與 payload 契約
- [EP83_MEMORY_MAPPING_2026-09-16.md](EP83_MEMORY_MAPPING_2026-09-16.md) — EP83 noncached pool mapping guard
- [EP83_SENDER_ABI_2026-09-16.md](EP83_SENDER_ABI_2026-09-16.md) — EP83 task-context sender ABI / ownership contract (fp 5.02)
- [FP_AF_DEVELOPMENT_STATUS_2026-09-27.md](FP_AF_DEVELOPMENT_STATUS_2026-09-27.md) — SIGMA fp 自動對焦開發：進度與方向
- [FP_AF_FIRMWARE_ROADMAP_2026-09-27.md](FP_AF_FIRMWARE_ROADMAP_2026-09-27.md) — fp 機內 AF：跨機型重審後的開發方向與階段目標
- [FP_CINE_BASELINE_2026-09-27.md](FP_CINE_BASELINE_2026-09-27.md) — CINE 原廠半按基線：2026-09-27
- [HOOK_ABI_AUDIT_2026-09-16.md](HOOK_ABI_AUDIT_2026-09-16.md) — C022C858 背景 H/L publication hook：ABI 與 stack 離線審核
- [HOOK_LIFECYCLE_AUDIT_2026-09-16.md](HOOK_LIFECYCLE_AUDIT_2026-09-16.md) — AF publication hook：離線 lifecycle / quiescence 稽核
- [HOOK_OWNER_AUDIT_2026-09-16.md](HOOK_OWNER_AUDIT_2026-09-16.md) — AF publication hook：owner／重新註冊路徑的有界離線稽核
- [HOOK_SAMPLING_PLAN_2026-09-16.md](HOOK_SAMPLING_PLAN_2026-09-16.md) — AF Assist：轉向 producer hook 取樣
- [TRANSPORT_AUDIT_2026-09-16.md](TRANSPORT_AUDIT_2026-09-16.md) — fp AF Assist：USB 傳輸停頓審核
- [USB_ROUTING_REPAIR_AUDIT_2026-09-16.md](USB_ROUTING_REPAIR_AUDIT_2026-09-16.md) — USB routing repair audit — single native owner, not ACK recovery
- [VALIDATION_2026-09-16.md](VALIDATION_2026-09-16.md) — fp AF Assist：驗證紀錄

## AF／face／AAT／PDAF 研究（36 份）

- [AF_AE_INTERNALS.md](research/AF_AE_INTERNALS.md) — SIGMA fp — AF/AE 內部演算法完整反編譯(六題彙整 + ⑦驅動細節十題 + ⑧CAF 觸發模型 + ⑨驅動/框/PTP 補充 + ⑩YLevel網格/低對比/waypoint)
- [AF_COMPLETE.md](research/AF_COMPLETE.md) — SIGMA fp — 對焦系統完整說明(方法、細節、用到的鏡頭資料)
- [AF_DESIGN_REFERENCE.md](research/AF_DESIGN_REFERENCE.md) — SIGMA fp CDAF 演算法設計拆解 — 給「自製自動對焦」的參考
- [AF_FUSION_TOOL_USAGE.md](research/AF_FUSION_TOOL_USAGE.md) — SIGMA fp AF-fusion 工具使用方式
- [AF_LIVE_STATE_MAP.md](research/AF_LIVE_STATE_MAP.md) — SIGMA fp Ver.5.02 — AF / Tracking / Face LIVE-STATE Address Map
- [AUTOFOCUS.md](research/AUTOFOCUS.md) — SIGMA fp / fp L — 自動對焦(AF)系統反編譯細節
- [CROSSCAM_PDAF_FEASIBILITY_2026-09-27.md](research/CROSSCAM_PDAF_FEASIBILITY_2026-09-27.md) — 跨機身重審：fp 能否靠韌體取得可用 PDAF
- [DFD_VIA_AF_STATS.md](research/DFD_VIA_AF_STATS.md) — SIGMA fp Ver 5.02 — DFD via the hardware AF-statistics engine (Bayer-green HF energy)
- [FACE_EYE_AF.md](research/FACE_EYE_AF.md) — SIGMA fp — 人臉 / 眼睛 / 主體追蹤 AF 完整反編譯
- [FOCUS_DISTANCE_PRINCIPLE.md](research/FOCUS_DISTANCE_PRINCIPLE.md) — 對焦位置 ↔ 距離 換算原理(SIGMA fp,從韌體反編譯還原)
- [FOCUS_POSITION_DOMAIN.md](research/FOCUS_POSITION_DOMAIN.md) — SIGMA fp — 對焦位置域:PTP vs GIMBAL 單位關係(反組譯確認)
- [FP_AAT_ACTIVATION_2026-09-27.md](research/FP_AAT_ACTIVATION_2026-09-27.md) — AAT 觸發、選定目標與幾何錨點
- [FP_AF_CAPTURE_GUARD_CORRECTION_2026-09-16.md](research/FP_AF_CAPTURE_GUARD_CORRECTION_2026-09-16.md) — AF collector capture-state correction — offline-verified, live validation pending
- [FP_AF_COLLECTOR_WORKER_POOL_GUARD_2026-09-27.md](research/FP_AF_COLLECTOR_WORKER_POOL_GUARD_2026-09-27.md) — AF collector：現行 worker pool 與 live lease 阻擋
- [FP_AF_DIRECTION_DIAGNOSTICS_2026-09-16.md](research/FP_AF_DIRECTION_DIAGNOSTICS_2026-09-16.md) — fp AF：H/L 方向診斷與訊號語義更正
- [FP_AF_FIRMWARE_INTERVENTION_MAP_2026-09-27.md](research/FP_AF_FIRMWARE_INTERVENTION_MAP_2026-09-27.md) — fp 5.02：機內 AF／AAT 改進的程式接點
- [FP_AF_PUBLICATION_HOOK_CANDIDATES_2026-09-16.md](research/FP_AF_PUBLICATION_HOOK_CANDIDATES_2026-09-16.md) — SIGMA fp 5.02：AF publication hook 候選的 bounded offline audit
- [FP_AF_REPEATABILITY_2026-09-16.md](research/FP_AF_REPEATABILITY_2026-09-16.md) — fp 原廠 AF：三輪重複性與完成歷史的離線驗證
- [FP_AF_STATS_FRESHNESS_2026-09-16.md](research/FP_AF_STATS_FRESHNESS_2026-09-16.md) — fp AF 輔助：H 統計更新與 scheduler mode 1 的靜態稽核
- [FP_AUTOFOCUS_GEOMETRY_DFD_PLAN_2026-09-16.md](research/FP_AUTOFOCUS_GEOMETRY_DFD_PLAN_2026-09-16.md) — fpFocus：幾何估距 + DFD + CDAF 的自動對焦改進方案
- [FP_CINE_AAT_ACTIVATION_2026-09-27.md](research/FP_CINE_AAT_ACTIVATION_2026-09-27.md) — CINE 原廠半按、FullTimeAF 與 AAT 啟動邊界
- [FP_CINE_GEOMETRY_INPUTS_2026-09-27.md](research/FP_CINE_GEOMETRY_INPUTS_2026-09-27.md) — CINE 連續 AF：face／AAT 共用幾何輸入稽核
- [FP_FACE_DISPLAY_SOURCE_2026-09-27.md](research/FP_FACE_DISPLAY_SOURCE_2026-09-27.md) — fp Ver.5.02 人臉顯示資料路徑離線稽核（2026-09-27）
- [FP_FACE_ENABLE_STATE_2026-09-27.md](research/FP_FACE_ENABLE_STATE_2026-09-27.md) — Face 啟用與結果來源的固定地址稽核
- [FP_FOCUS_DRIVE_GATE_AUDIT_2026-09-16.md](research/FP_FOCUS_DRIVE_GATE_AUDIT_2026-09-16.md) — fp 5.02：Focus drive gate、完成／停止與唯讀查詢
- [FP_GEOMETRY_DFD_FUSION_2026-09-27.md](research/FP_GEOMETRY_DFD_FUSION_2026-09-27.md) — fp 機內融合：幾何判運動方向，DFD 估離焦量
- [FP_NATIVE_FOCUS_CONTROL_2026-09-16.md](research/FP_NATIVE_FOCUS_CONTROL_2026-09-16.md) — fp 5.02 native-L focus control audit
- [FP_NATIVE_TASK_STACK_DIAGNOSTIC_2026-09-27.md](research/FP_NATIVE_TASK_STACK_DIAGNOSTIC_2026-09-27.md) — fp 5.02：原生 task 診斷的 ABI 差異與 stack 證據界限
- [FP_ORIGINAL_AF_TRIAL_2026-09-16.md](research/FP_ORIGINAL_AF_TRIAL_2026-09-16.md) — fp 原廠 AF 實測：自動半按、DMA 傳輸修正、原生掃焦曲線
- [FP_TRACKING_SETTINGS_LEASE_2026-09-27.md](research/FP_TRACKING_SETTINGS_LEASE_2026-09-27.md) — 原廠 Tracking baseline：設定、模式與還原邊界
- [NON_PDAF_CAMERA_REFERENCE_2026-09-27.md](research/NON_PDAF_CAMERA_REFERENCE_2026-09-27.md) — fp 機內 DFD／AAT：無 PDAF 與其他機身的參考價值
- [PDAF_RAW_PATTERN_ANALYSIS_2026-08-17.md](research/PDAF_RAW_PATTERN_ANALYSIS_2026-08-17.md) — SIGMA fp pre-Still RAW PDAF pattern analysis
- [PTP_FOCUS.md](research/PTP_FOCUS.md) — SIGMA fp — PTP 對焦控制在錄影時失效：原因與可能解法
- [PTP_FOCUS_RECORDING.md](research/PTP_FOCUS_RECORDING.md) — PTP/GIMBAL 錄影中控焦 — session 閘研究 (待續)
- [SIGMA_FP_PDAF_INVESTIGATION_REPORT_2026-08-18.md](research/SIGMA_FP_PDAF_INVESTIGATION_REPORT_2026-08-18.md) — SIGMA fp 相位像素／PDAF 原始資料調查報告
- [ZCAM_AF_REFERENCE_2026-09-27.md](research/ZCAM_AF_REFERENCE_2026-09-27.md) — Z CAM E2-F6 AF：可讀實作與失敗機制參考（2026-09-27）

## 幾何核心、輸入與合焦配對（6 份）

- [NATIVE_CONFIRMATION_AUDIT.md](geometry/NATIVE_CONFIRMATION_AUDIT.md) — 原廠 AF 結果與鏡頭完成：fg_confirm 來源稽核
- [NATIVE_HOOK_PLAN.md](geometry/NATIVE_HOOK_PLAN.md) — fp 5.02 native observation hook：離線接點與 ABI 契約
- [NATIVE_INPUT_AUDIT.md](geometry/NATIVE_INPUT_AUDIT.md) — 幾何方向器的 native 輸入稽核
- [OFFLINE_INTEGRATION.md](geometry/OFFLINE_INTEGRATION.md) — 合焦配對與 raw observer：上機前離線交接
- [README.md](geometry/README.md) — 機內幾何方向核心
- [VALIDATION.md](geometry/VALIDATION.md) — 幾何核心離線驗證紀錄

## DFD 歷史方法與採樣（2 份）

- [HOOKPUSH.md](dfd/HOOKPUSH.md) — DFD hook-push — 相機主動推綠通道 AF-band 資料(高速、零 stall)
- [README.md](dfd/README.md) — DFD — depth from defocus, without extracting a single frame

## 鏡頭資料與查詢（5 份）

- [AUTORUN_LENSDUMP.md](lens/AUTORUN_LENSDUMP.md) — AutoRun.txt — 用 mem save 把鏡頭資料 dump 到 SD 卡
- [LENS_BLOCK_API.md](lens/LENS_BLOCK_API.md) — 鏡頭資料存取 — 借用韌體自己的 API（含握手）
- [LENS_DATA_ACCESS.md](lens/LENS_DATA_ACCESS.md) — SIGMA fp — 鏡頭資料:關鍵參數 + PTP/GIMBAL 可讀性
- [LENS_QUERY.md](lens/LENS_QUERY.md) — L-mount lens register query over USB
- [SOP_LENS_EXTRACT.md](lens/SOP_LENS_EXTRACT.md) — SOP — 任意鏡頭資料擷取(給 AI 對焦程式用)

## 韌體專案歷史入口（2 份）

- [FOCUS_OVERVIEW.md](firmware/FOCUS_OVERVIEW.md) — focus
- [FOCUS_SUP.md](firmware/FOCUS_SUP.md) — focus sup

## 既有實測與分析說明（5 份）

- [analysis-native_subject_20260927.md](evidence/analysis-native_subject_20260927.md) — Native subject 輸入契約：第二個離線增量
- [analysis-zcam_af_20260927.md](evidence/analysis-zcam_af_20260927.md) — Z CAM AF 離線反編譯存檔（2026-09-27）
- [capture-af-fusion-2026-09-16-iso100-v5.md](evidence/capture-af-fusion-2026-09-16-iso100-v5.md) — ISO 100 return baseline — 2026-09-16
- [capture-native-preflight-20260927-121028.md](evidence/capture-native-preflight-20260927-121028.md) — fp 5.02：首次原生唯讀環境核對
- [capture-native-preflight-20260927-124113.md](evidence/capture-native-preflight-20260927-124113.md) — fp 5.02：辨識來源與顯示路徑診斷

## 舊工具說明（1 份）

- [FP_AF_EXPLAINER.md](legacy/FP_AF_EXPLAINER.md) — vinext-starter

## 同專案其他說明與共用依據

- [host 控制稽核](../CONTROL_AUDIT.md)、[新鮮度稽核](../AF_FRESHNESS_AUDIT.md)
- [EP83 工具](../highrate/README.md)、[transport 原型](../transport_native/README.md)、[diagnostics](../diagnostics/README.md)
- [歷史交接及其備份](../handoff/INDEX.md)；備份內容不改写
- [共用 USB／PTP 證據](../../../research/interfaces/notes/FP_USB_PTP_SHARED_PATH_2026-09-16.md)、[鏡頭／感光元件校準](../../../research/lens/notes/LENS_CALIBRATION.md)
- [57 份筆記搬移對照與雜湊](relocation-20260927.json)
- [Claude Code skills 匯入與驗證](CLAUDE_SKILLS_IMPORT_2026-09-27.md)／[安裝來源雜湊](claude-skill-import-20260927.json)

## 程式與原始資料

- [幾何程式](../../../fpSup/focus/geometry/)、[AF 量測工具](../../../research/autofocus/)
- [所有原始量測](../../../research/autofocus/captures/)、[13:36 CINE 原始資料](../../../research/autofocus/captures/cine-af/20260927-cine-baseline/)
