# AAT 觸發、選定目標與幾何錨點

2026-09-27。使用者提醒「AAT 似乎要點擊螢幕才觸發」後，核對官方手冊、本地反編譯與 ROM。本輪沒有相機 I/O、設定變更或鏡頭命令。

## 原廠操作與內部演算法分開看

[SIGMA fp FW 5.0 官方手冊](https://www.sigma-global.com/en/support/download/fp_Manual_FW_Ver.5.0_EN_2.pdf) 的印刷頁 55–56 說明：Tracking 為 STILL 的 AF-C 選項，將主體放入對焦框並半按快門，合焦後追蹤該主體。頁 63–64、152 將 Touch AF、移動對焦框、Touch Shutter 列為不同觸控設定。因此不能把「點螢幕」當作 AAT 唯一必要條件，也不能把單次 Touch AF 等同持續 Tracking。

手冊描述的是對使用者開放的模式，不證明同一 backend 在其他韌體呼叫路徑不存在。錄影中的機內 AAT 另驗 native 控制流程，不由 STILL 限制推導硬體不能執行。

## ROM 與本地來源確認

ROM：`out/seg0_c0000000.bin`，base `C0000000`，SHA-256 `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`。

| 階段 | 原生路徑 | 已證明的條件 |
|---|---|---|
| 開啟 tracking 工作路徑 | `C05A8850 → C05A8810 → C05A8BE0` | `C05A88C4..D8`：呼叫者參數非零，且 applied 設定 `+1CC==3`，才將 tracking byte 設為 1。face／eye 是另兩個 bytes。 |
| 準備初始目標 | `C05AC248` | `C05AC304..33C`：讀取 applied reference `+C0/+C4` 與 AF ROI `+C8`，轉成 tracker 影像座標；`C05AC348..37C` 寫初始 xs/xe/ys/ye。此函式沒有直接讀取觸控座標。 |
| 建立模型或延續 | `C05AC388` | 原有 state 不是 2 時重新準備目標；可同步呼叫 backend SetTarget，或透過 worker message。state 2 的延續分支不能一律描述成重新選定目標。 |
| 非同步投遞 | `C05ABB70` | `C05ABB98..BD0` 建立 0x2C-byte message，command=2、byte+6 表示是否帶新目標，後接 9 words 目標資料，再投遞 queue。 |
| 執行模型初始化 | `C05ABD90 → C05ABEC8` | worker 收到新目標後，`C05ABFBC..FEC` 以一次 pending flag 呼叫 backend vtable+0C SetTarget，隨後清 pending；其他迭代走 Run。 |
| color backend | `C05AB9B0 → C05B6BA0` | 初始化的是目標色彩／空間模型；SetTarget 成功不等於光學合焦。 |

來源函式均在 `out/decomp/full/blk_c05.c`。上述關鍵 offset／指令已用 ROM ARM 解碼核對，不以單一反編譯變數名稱推定觸控事件。

上游控制層亦有 `C039FB88 → C05A8850 → Detections::v2`，以及 `C039FA58 → C05A8850(...,1) → Detections::v7 → v2` 兩條可讀路徑（`blk_c03.c:109665`、`:109612`）。`C039FB88` 的參數 3 是內部控制狀態，不直接命名為 CINE 模式。command 2 的 worker 分支还會等目前影像指標不同才進入工作；gate=1／START 已入 queue 都不代表 SetTarget 已完成或結果有效，影像指標變化也不等同已驗證曝光序號。

## 本輪實測應如何解讀

[12:53 有限觀測](../evidence/capture-native-preflight-20260927-124113.md) 的 runtime `face=1, eye=1, tracking=0` 與 AAT backend/model/publication 全零，只能證明擷取當時未進入 tracking 工作路徑。這不是已啟動 AAT 後的失敗樣本，不能納入 AAT 性能統計。

下一個原廠 AAT baseline 應包含：選定 Tracking 模式與初始目標、明確啟動原廠 AF、觀測 tracking gate／模型初始化／Run／GetResult、釋放／停止與設定核對。觸控只是一種選定區域／AF 入口；半按流程是官方明示的另一入口。現有 collector live installer 仍受記憶體 lease 阻擋，本筆記不是呼叫 raw SetTarget 或改寫 gate 的工具。

## 機內開發方向

韌體可沿著「選定主體區域 → 初始化 AAT → 持續追蹤」設計接點，不必把電腦或使用者反覆觸控放進正式追焦迴圈。這是來源支持的實作方向，尚未部署。

- 初始區域來源可分為原廠使用者選定區域，以及之後經驗證的 face／eye 主體區域。現行 `C05AC248` 讀的是 applied AF ROI，尚未證明自動將有效 face 框交給 AAT；不可宣稱已有自動 face→AAT handover。
- 新選定或 reseed 必須建立新的 subject／scale generation，不能把前一主體的幾何合焦錨點沿用到新模型。
- AAT 模型建立不代表首次合焦；仍需同主體的原廠 AF 成功、最後鏡頭完成與有效尺度配對才能建立幾何基準。
- AAT 用於保持主體連續性需先測；其自適應模型／輸出框尺寸不能直接當距離。尺度未驗證或辨識失效時保留 UNKNOWN。

本階段的驗收先分清「尚未觸發」「已初始化但無結果」「有結果但不可信尺度」，再談 AAT 或連續 AF 改善。
