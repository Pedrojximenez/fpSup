# CINE 原廠半按、FullTimeAF 與 AAT 啟動邊界

2026-09-27。使用者明確指定維持 CINE、只研究影片連續 AF。這是離線 decomp＋ROM 稽核；沒有相機 I/O、setter、patch 或 raw detection 呼叫。前一份 STILL Tracking baseline 的 mode=1／area=3 準備程序不適用目前範圍。

ROM：`out/seg0_c0000000.bin`，base C0000000，SHA-256 `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`。

## CINE 的 continuous 開關不是 STILL 的 AF-C enum

`MenuItemFocusMode_w71c1::v8 C008B310` 的 ROM `C008B3DC..3EC` 在 CinemaMode=1 時將要求的 FocusMode=1 轉回 0。`MenuItemFocusArea_w71c1::v8 C008B520` 在 effective FocusMode=0 時把 Tracking area=3 限制成 2。因此不能為影片研究強設 STILL AF-C=1，或把 CINE 的 FocusMode=0 解讀為「沒有影片連續 AF」。

真正的不同選單路徑：

| native menu item | 適用模式 | applied 欄位 |
|---|---|---|
| `MenuItemIsPreAf::v3 C00A3438` | `C008CCE8` 回 CinemaMode=0 | byte +1C0 |
| `MenuItemFullTimeAfSupport::v3 C00A34B8` | CinemaMode=1 | byte +1C0 |
| `MenuItemHalfReleaseAFSupport::v3 C00A5088` | 半按功能獨立設定 | byte +1D8 |

前兩項還經 `C00A2DA0` 的有效性處理，且 +58C 特殊模式可強制 +1C0=0。影片 continuous 基線應同時保存 CINE、effective AF mode、FullTimeAfSupport、HalfReleaseAFSupport 與 applied/runtime AF 狀態；一個 menu 值不是完整狀態。

## CINE 預覽的 S1ON／S1OFF：確定可觀測的範圍

已稽核的原生 `key S1ON`／`key S1OFF` 是按鍵事件 4／5，見 [原廠 AF 試驗](FP_ORIGINAL_AF_TRIAL_2026-09-16.md)。它們不送 S2 或 MOV。此處再核對共用的 live-view 半按處理路徑，不能把 shell ACK 當成合焦完成。

`StandbyEventHandler_w71c1::v3 C0482188` 將 half-press/release payload 交 live-view state vtable+14；normal state 的 `StandbyLiveViewZoomStateNormal::v3 C0480968` 呼叫 `C0480390`。該函式的按／放分支已用 ROM 核對：

| 階段 | ROM 路徑 | 可證明的效果 |
|---|---|---|
| press payload 非零 | `C04803AC..3B4 → C0370CF8 → C0370D08` | RecMgr v1 `C0371770` 建立 command=1，進原廠 request queue；不是 record toggle |
| press 被 RecMgr 接受 | `C04803EC..3F4 → C04A4C68(...,1)` | 原廠 UI 狀態 S+220 進入 1 |
| release payload 為零 | `C0480460..464 → C0370D40` | RecMgr v2 `C0371838` 建立 command=2 |
| release 被接受且 S+220==1 | `C048049C..4B0 → C04A4C68(...,0)` | 原廠 UI 狀態 S+220 回 0 |

這條路徑與 S2 處理 `C04804E0`／normal state v4 `C0480A18` 分開。不能由此推論所有 UI 狀態／重映射都相同；本輪應保留原生 key dispatch、CINE 預覽、非錄影 guard，並限制一次有界按／放。

### 修正 held-phase guard 的解讀

**S+220=C3033A6C 在自己的半按期間可以正常是 1**，不是所有非零值都代表外來拍照或錄影。

`C04A4C68` 讀 S+220，狀態改變時經 `C04A4D0C → C00172C0` 發布。ROM `C00172D8..2F0` 複製 S+1F4..238；`C001733C` 將輸入狀態寫到 local+2C（即原始 S+220）；`C0017348 → C0017F08` 套用完整小結構。0→1 也增加同結構的 sequence 欄位。

因此未持有 S1 前仍要求 S+220=0；成功派發自己唯一一次 S1ON 後，held phase 可接受 0 或 1（0 不證明已執行），2 或未知值停止觀測並進釋放。不要全域刪除這個 guard、接受任意非零值，或把事前的 1 歸為自己的狀態。釋放後需有限觀測確認回到 0；未回復不能宣稱清理完成。busy bytes C30338C8..CB 和 MovieRecording byte C30338D0 仍需各自檢查。

### 取得對焦與影片 continuous 必須分開

已證明 S1 進入原廠 AF request/release 狀態機；未發現此按鍵路徑直接改 FullTimeAfSupport menu。RecMgr 的 `C039F008`／`C039F578` 等路徑會依 HalfReleaseAFSupport(+1D8)、當前排程／AF 狀態停止、改派或恢復 native AF 工作。這表示半按可能暫時改變原來的 full-time 排程，但本次窄範圍稽核**尚未完整證明 CINE 預覽各狀態下抑制與恢復條件**，不能概括成「一直半按就是 continuous」或「放開一定停止所有 AF」。

一次 S1 試驗適合取得 **CINE 原廠半按取得／釋放基線**：比較前、按住、釋放後的 native AF 狀態、鏡頭完成與來源。影片 continuous 性能要另以 full-time 設定、自然主體移動及較長 runtime 觀測判定；不得把反覆半按当作正式持續追焦迴圈。

## 原廠 AAT gate 與 Touch AF

`C05A8850` 使用 active UserSetting；ROM `C05A88C4..D8` 只有呼叫參數非零且 **applied +1CC==3** 才設 tracking byte。face／eye 與 tracking 是分開的 bytes。上游 `C039FB88` 對內部參數3還要求 effective FocusMode +1BC==1，且 face enabled 或 applied area3；ROM `C039FC28..6C`。其參數3是內部控制狀態，不是 CinemaMode。

`C039FA58` 另一入口可以經 `C05A8850(...,1)`→Detections v7；但是它仍受 `C05A8850` 的 applied-area gate，不因 CINE 或半按而自動開 AAT。

原廠 Touch AF 的確有独立設定目標區域的入口：`TouchAf C04839D8 → C0483870 → C04BB028 → C03711F0 → RecMgr v27 C03725C8`，後者建立 command=0F 並複製 0x5C AF request。前端有 native LV、AF/MF、touch-mode 及場景狀態檢查，不應在 shell dispatcher 直接裸呼叫。

**Touch AF 不等於 AAT Tracking 啟動。** `C0483870` 先複製 reference +C0/+C4、ROI +C8..D4，以及 AF settings +1BC..1FC；ROM `C04838EC..3F8` 隨即強制該 request 的 FocusMode=0、applied Area=1。它可使用原廠 getter ROI 或已處理的 touch rectangle，並將 xywh 轉為 inclusive endpoints。因此這條是指定 ROI 的 native 取得對焦請求，沒有把 area 設為 AAT gate 所需3。

## Backend 是否在 CINE 不可行

目前的證據只否定「直接使用 STILL menu Tracking 流程作為 CINE AAT 啟動方式」，**沒有證明 CINE 執行 AAT 演算法在硬體上不可能**。

在已讀取的 Detections/AAT backend 中：

- `C05A8810 → C05A8BE0` 接收三個 runtime gate bytes；它沒有 CinemaMode 分支。
- `Detections::v2 C05A8EA8` 在 tracking gate 非零時走 AAT facade；需要原廠 state、鎖、目標／影像與通知管理。
- AAT `C05AC248` 以 reference尺寸／applied ROI 建立 initial target；`C05AC388` 決定新模型或延續；worker `C05ABEC8` 以 pending target 呼叫 SetTarget，其餘影像迭代 Run。這些局部函式沒有以 CINE enum 拒絕執行，見 [啟動條件](FP_AAT_ACTIVATION_2026-09-27.md)。
- native debug handler `C03E0A50` 可直接設定 face/eye/tracking；`C03E06A0` 可以初始化／開始 detector。這證明有低層入口，**不是已驗證安全的 CINE 操作方案**：會改 global detector、可能 lazy-init，尚未建立它與 RecMgr 的 ownership、停止／恢復、callback quiescence 關係。本次不呼叫、不把它包成替代 live CLI。

下一步應在 CINE 自己的生命週期下設計受控 detector 啟動／停止與 observer，先做 shadow-only 觀測。原廠 AF 保持唯一鏡頭控制者。不是先改 applied +1CC 或 runtime gate 再看是否卡住。

## 目標框、尺度與幾何用途

AAT initial target 來自已驗證來源的 ROI；它代表初始化追蹤的區域，並不代表已光學合焦。新目標／reseed 應換 generation，直到同主體 native AF 成功、最後鏡頭完成與可用尺度配對後才建立幾何錨點。

publication `C05AC690` 依 backend selector 決定框：selector=0 由 xs/xe/ys/ye 算寬高，selector非零可明確改成 **0x40×0x40** 固定框（decomp 的 `C05A8B30(...,0x40,0x40)`）。因此並非每個 AAT AF-facing rectangle 都可拿來估距或判斷接近／遠離；即便可變框也受自適應模型、遮擋與 ROI 更新影響，需先證明尺度語意和 freshness。

本次結果支持的開發方向是：CINE FullTimeAF baseline → 有效臉／指定主體初始化與追蹤生命週期 → 可信主體尺度或其他方向特徵 → 幾何方向 shadow 驗證；DFD 若獲得獨立可信殘差，另負責距離／位移。前述機內接點尚未部署。

來源：`out/decomp/full/blk_c00.c`（menu、S+220 publisher）、`blk_c03.c`（RecMgr/detector debug）、`blk_c04.c`（live-view S1、Touch AF）、`blk_c05.c`（Detections/AAT）。S1 writer、Touch AF request overwrite、tracking gate 的關鍵指令已以 ROM ARM disassembly 交叉核對；完整 CINE CAF／recording 狀態機沒有宣稱已窮盡。
