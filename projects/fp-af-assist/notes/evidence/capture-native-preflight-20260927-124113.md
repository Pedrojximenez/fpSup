# fp 5.02：辨識來源與顯示路徑診斷

原程式／證據目錄：[research/autofocus/captures/native-preflight/20260927-124113](../../../../research/autofocus/captures/native-preflight/20260927-124113/)。筆記已集中至 fp-af-assist；下文歷史結果與限制保留。

2026-09-27，使用者回覆「開始」後續作。範圍為既有 USB shell 原生唯讀查詢；没有 RAM 注入、hook、鏡頭命令、設定變更、daemon 啟停或卡片操作。

## 連線與第一輪讀取

初次 host STATUS 報 `camera=open`，但 native `version` 回 `LIBUSB_ERROR_NO_DEVICE`，OUT `moved=0/64`；停止該次 preflight，保留失敗原始紀錄。macOS 仍列出 SIGMA fp。核對現行 `fpshd.c` 後，確認 NO_DEVICE 會關閉舊 handle；同一 daemon PID 69735 的新 STATUS 已報 closed。其後只做一次 native version 身分重新確認，成功後另存新的完整 preflight。沒有啟停 daemon、reset 或自動重試 loop。

重新核對的韌體仍為 `w71c1 / 5.02.0.V91 / 13aa621060efff11aaba9b21ad925005302605cf`。完整 preflight 的 64 次交換成功、零失敗；4 個 callsite 和 12 個 code guards 符合 ROM。Echo 前後原廠，前後 capture gate idle，四個 focus getter 在該次讀取前後相同。

與 12:10 的前次擷取相比，focus rectangle 由 `480 373 64 64` 成為 `144 373 64 64`；本工具沒有變更設定，不將跨擷取差異歸因於工具。Boot stamp、worker pool/code publication 均相同。

本輪 face group0、AAT backend/model/publication 仍全零。這只能表示此輪未見填入的主體資料，不能據此判定選單關閉、畫面沒有人臉，或幾何方法不可行。

## 使用者觀測與下一步

使用者先回報已有人臉框，稍後更正「很難判斷有沒有人臉筐」。**畫面是否有框維持未確認**；不把前一句當光學或 UI 真值，也不據此宣稱 UI 與 manager 資料矛盾。

接續已直接核對固定辨識設定、原始結果、SysStatus、Display observer 與 renderer 副本。新增 `--subject-path` 僅做固定 RAM 讀取，不呼叫 face menu getter，不改設定。`--subject-samples 8` 做有限短時觀測。這些序列讀取不是原子快照或曝光同步樣本，所有 geometry／motion authority 維持 false。

## 後續實測結果

- 第二階段 `subject-path-preflight.jsonl`：102 次交換完成，取得辨識設定與三份顯示副本。第三階段 `subject-watch-preflight.jsonl`：在相同檢查後，再觀測 8 次，共 166 次交換完成。各段內沒有重試或失敗。
- 短時觀測的首筆開始至末筆結束為 **2.388 秒**。8/8 的 Detections 物件 identity／guard 正確，runtime bytes 全為 **face=1、eye=1、tracking=0**：人臉／眼睛路徑開啟，AAT 未開啟。這是 runtime gate 證據，沒有把 stored menu raw `2` 直接當 applied enum。
- 8/8 的原始 packet face count=0、group0 face-valid=0；manager、SysStatus、renderer 的 face-present=0、ready=1。原始 packet 第二 word 會變化，但意義未解，**不把它當 exposure counter 或 freshness 證明**。
- SysStatus、observer、renderer 的首 `0xA8` bytes 在擷取時相同。renderer buffer／vtable identity 正確，提交框計數=0。讀取位置與顯示消費路徑吻合；當下沒有可採用的人臉尺度。
- eye 子槽留有 `6×6` 小矩形與 valid byte，但 face-present／face-valid 不成立，原廠 AF selected-eye 分支也不能採用。這些殘留值不能當有效眼部結果或幾何輸入。
- debug/config guard／vtable 正確，publication override bytes 為 0。AAT backend、model、publication 仍為零；配合 runtime tracking=0，不能把零值宣稱為 AAT 跟丟或演算法失效。
- 後兩段 focus getter 為 rectangle `215 158 595 365`、mode `0`、area `2`、size `3`，各段內前後一致。與更早擷取不同的設定由原始 evidence 保留，本工具沒有 setter。不能將不同設定下的資料合併成相同情境的性能比較。

目前僅完成資料來源與有效性診斷，沒有量測辨識率、追焦性能、光學合焦或幾何方向準確率。後續需要可靠的主體尺度樣本及原廠合焦事件；face 遺失時保持 UNKNOWN，AAT 在另行啟用且驗證後才能研究其連續性，不能靠目前殘留框填補有效旗標。

離線驗證 **40 tests 通過、0 skip**，包含既有 subject decoder 與 preflight 的固定讀取範圍、0..16 次上限、失敗即停／不重試、pointer 不追讀、非零 raw 不取得幾何權限。見 `subject-watch-validation.json`。

「沒有 RAM 寫入」的範圍更正：本工具沒有直接 `mem set` 或注入 payload；原廠 no-arg menu handler 仍可能更新內部 cache／lock。新 transcript 明示 `camera_ram_writes_scope`，不將它宣称為整個相機完全沒有內部 RAM 更新。詳細來源：[啟用與設定欄位](../research/FP_FACE_ENABLE_STATE_2026-09-27.md)、[顯示路徑](../research/FP_FACE_DISPLAY_SOURCE_2026-09-27.md)。

## 原始證據

- `native-preflight.jsonl`：首次失敗，止於 version；`preflight-summary.json` 是該次空 stdout。
- `connection-revalidation.jsonl`：同一 daemon closed 狀態及一次 native version 重新確認。
- `native-preflight-revalidated.jsonl`、`preflight-revalidated-summary.json`：其後完整 64 次交換。
- `native-subject-decoded.json`：以既有 decoder 離線解碼的主體原值。
- `analysis.json`：衍生比較、限制與原始檔 SHA-256；不是原子觀測證明。
- `subject-path-preflight.jsonl`、`subject-path-summary.json`：固定設定與 display 路徑。
- `subject-watch-preflight.jsonl`、`subject-watch-summary.json`：8 次有限觀測與完整前後檢查。
- `subject-watch-analysis.json`、`subject-watch-decoded.json`：離線解讀；保留未知與 false gates。
- `subject-watch-validation.json`、`subject-watch-offline-tests.log`：40 項測試及當次原始碼 SHA-256。
