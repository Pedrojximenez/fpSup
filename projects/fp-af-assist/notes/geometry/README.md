# 機內幾何方向核心

2026-09-27：已完成幾何核心、首次合焦事件配對、串接重播與四個 raw observer 的離線候選。`geometry.c` 是供機內使用的同一份 C 核心，電腦只負責編譯、重播與驗證。後續 USB 接上後完成 [原生唯讀環境核對](../evidence/capture-native-preflight-20260927-121028.md)，仍未安裝 hook。尚無可信 native 輸入 adapter、installer、鏡頭命令或可安裝韌體。

主線：**原廠 CDAF 首次合焦 → 建立主體／尺度／位置基準 → 幾何判接近、遠離或靜止 → 後續由原廠 AF 決策**。DFD 的離焦量／位移估計另行驗證。主體移動方向不等於當前修焦方向，這份核心不輸出馬達修正量，`motion_authorized` 固定為 0。

## 已完成

- `geometry.c/.h`：整數 Q16 倒數尺寸、最多 32 點的短窗線性擬合、相對速率與殘差；狀態完全由呼叫端持有，不配置記憶體、不呼叫系統或相機 API。
- 首次光學合焦確認、事件防重播、目標／來源／成像條件換代、時序及尺度有效性檢查。未合焦或基準失效時回 UNKNOWN。
- 鏡頭移動時清除趨勢，保留未過期基準；停止後重新累積樣本，避免把對焦呼吸接進同一窗口。**本版不能在持續移動鏡頭時持續估方向**，後續須驗證排程或呼吸補償。
- `geometry.py`、`replay.py`：本機編譯並執行上述 C 核心；嚴格 JSONL 輸入、拒絕舊 snapshot 冒充可信新資料。
- `build.py`：Cortex-A9 ARMv7 soft-float relocatable object、組語與來源雜湊；拒絕外部 runtime 符號與可變全域狀態。這不是 SUP／AutoRun payload。
- [native 輸入稽核](NATIVE_INPUT_AUDIT.md)：指出現有採樣器三項 subject 命名／offset／型別問題，列出真正接入所需證據。
- 同日後續：採樣器 JSON v7 已修正舊資料的誤標，新增完整 [native subject 解碼](../../../../research/autofocus/af_subject_observation.py)；只保留可證實的 raw tuple，未知來源條件仍不會產生幾何旗標。[合焦事件稽核](NATIVE_CONFIRMATION_AUDIT.md)另外處理 AF 結果可能早於最後鏡頭完成的時序。
- `confirm_join.c/.h`：同 episode／final drive 的 AF 成功、最終完成、新鮮同主體尺度配對；每輪最多產生一次 shadow candidate。中途停止、取消、fault、漏事件、換主體及過期要求重新開始；不呼叫 `fg_confirm()`。
- `join.py`、`join_replay.py`：執行上述 C 與幾何 C；只有明確標為 synthetic 的回放可模擬接受候選。真實或 annotated 資料只能產生候選，不能因此建立已驗證光學基準。
- `native_hook_sites.json`、`verify_hook_sites.py`：核對 fp 5.02 ROM 身分、四個 ARM BL 接點、callee 與 continuation 指令；ABI 依據見 [NATIVE_HOOK_PLAN](NATIVE_HOOK_PLAN.md)。
- `native_observer.S`、`build_observer.py`：AF callback 前、lens event-set 後、face publication 後、AAT Run 後的有界 raw 記錄。四個來源各持有有限陣列；滿載不覆寫、忙碌不等待，沒有 timer 或 USB 呼叫。產物位址**僅供模擬器**，不產生可安裝 patch／卡片。
- `observer_decode.py`：驗證 copied snapshot 的格式、nonce、commit/trailer 與計數，保存完整 raw bytes；face／AAT 沿用 native subject decoder。四條來源沒有共用時間／曝光身份，不自動轉為配對事件或幾何樣本。

## 離線使用

需要 Python 3.10+ 及支援 ARM target 的 clang。以下在 [程式目錄 `fpSup/focus/geometry`](../../../../fpSup/focus/geometry/) 執行；輸出目錄必須尚不存在，工具不覆寫舊結果。筆記已集中到本專案，程式沒有搬移。

```sh
python3 -m unittest discover -s . -p 'test_*.py' -v
python3 replay.py fixtures/synthetic_motion.jsonl --output /private/tmp/fp-geometry-replay
python3 build.py --output /private/tmp/fp-geometry-arm
python3 join_replay.py fixtures/join-synthetic-v1.jsonl --output /private/tmp/fp-join-replay
python3 build_join.py --output /private/tmp/fp-join-arm
python3 verify_hook_sites.py
python3 build_observer.py --output /private/tmp/fp-observer-emulator
```

可用 `make_demo.py --output <新檔名>` 重新產生 fixture。它包含人工指定的合焦、靜止、接近、反向、鏡頭移動、換主體與失效事件，**沒有相機量測資料**。`replay.py --config <JSON>` 可覆寫開發參數，核心會核對範圍。

`decisions.jsonl` 保存每筆判定；`summary.json` 同時報 UNKNOWN、錯誤與正確的 caller-supplied label 計數，並另外計算應保持 UNKNOWN 卻輸出方向的事件。合成資料不構成實機準確率，呼叫者填入的 flags 也不會因此獲得獨立驗證。建置結果含 `geometry.o`、`geometry.S`、`manifest.json`；不能把 `.o` 直接交給既有 loader。

## 輸入與計算契約

完整欄位、範圍與 enum 在 [geometry.h](../../../../fpSup/focus/geometry/geometry.h)。第一筆 JSONL 必須是：

```json
{"type":"metadata","schema":"fp.geometry.events","version":1,"provenance":"synthetic","clock":"common_epoch_ms","scale_semantics":"normalized_linear_size"}
```

`provenance` 可為 `synthetic`、`annotated_replay` 或 `camera_capture`；這是來源宣告，並非驗證結果。後續事件有 `sample`、`focus_confirmed`、`invalidate`。`sample` 物件的全部十個欄位都必填，例如：

```json
{"type":"focus_confirmed","focus_event_seq":1,"confirmation_flags":3,"sample":{"now_ms":1000,"sample_ms":1000,"source_seq":1,"target_generation":1,"context_generation":1,"scale_generation":1,"source_kind":1,"flags":31,"scale_q16":16384,"lens_position":10000}}
```

這是**示範假設**，不能為了通過檢查而把實機未知條件填成 31／3。

| 欄位 | 必須成立的語意 |
|---|---|
| `sample_ms`、`now_ms` | 同一 uint32 毫秒 epoch 的來源完成／現在時間；模數前向差小於 2³¹。不是 USB 讀取時間冒充來源時間 |
| `source_seq` | 同一 context 中每個新來源發布遞增；新 context 可重設。重讀同一資料不能遞增冒充新樣本 |
| 三個 `generation` | adapter 維護的非零 token：目標身份、鏡頭／readout／crop／尺度定義、尺度來源換代；不是直接複製 native tracking ID |
| `scale_q16` | 線性主體尺寸／有效影像寬度 × 65536，範圍 64..131072；不是面積、AAT 搜尋窗或 AF ROI |
| `source_kind` | 1=face，2=AAT。AAT 另須 `FG_AAT_SCALE_VALIDATED`，現有資料尚不能設定 |
| `flags` | 尺度有效、身份有效、來源時間有效、投影穩定、鏡頭停止五個獨立 gate；缺任一條件不輸出趨勢 |
| `lens_position` | 診斷及確認基準的位置域，int32；核心不推斷此值是否代表實際馬達位置 |
| `focus_event_seq` | 獨立合焦事件序號，必須前進；`confirmation_flags` 明確具備 CDAF 成功與有效位置。鏡頭停止、H 最大、AF 函式返回都不能單獨充當成功 |

每次採樣計算 `q = anchor_scale / current_scale` 的 Q16 值，再對 `q` 與時間做短窗線性擬合。`relative_rate = slope / mean(q)`，每秒為單位；正值代表遠離，負值代表接近。這不是 m/s、絕對距離或當前離焦量。`residual_q16` 是對窗口平均 q 正規化的最大擬合殘差；`confidence_permille` 只是殘差餘裕及窗口覆蓋率的 heuristic，並非概率。

預設窗口 300 ms，至少 5 點及 120 ms；來源 age ≤100 ms、gap ≤150 ms、基準期限 5 s，速率門檻約 2%/s、殘差約 2%、單點尺寸跳變上限 25%。**都是開發起始值，沒有相機校準**。轉向時窗口會保留舊趨勢；本次合成反向有三筆錯向，應見 [驗證紀錄](VALIDATION.md)，不能直接拿去驅動鏡頭。

## 狀態及接入要求

`fg_init` 每個 state lifetime 呼叫一次，成功回 1；它會清除防重播紀錄。操作中的 reset 使用 `fg_invalidate`，保留時間／事件高水位。單一 owner 序列化呼叫，狀態不可由 producer 與 consumer 無同步並行改寫。

`fg_confirm` 只有在可信光學確認與新鮮同主體尺度配對後建立／更新基準，成功也只進入 WARMUP。`fg_update` 要累積足夠資料才進入 TRACKING；舊時序拒絕且不污染歷史，換主體、無效尺度、過期或跳變會要求重新合焦。短 gap 清趨勢；基準壽命檢查仍有效。被拒絕的確認不刷新基準，也不產生方向。

下一階段先完成 [native adapter 清單](NATIVE_INPUT_AUDIT.md#4-最小下一步-native-adapter-工作)：正確 face tuple、AAT 各階段資料分離、來源發布時點、目標 generation、原廠成功合焦事件與獨立鏡頭完成狀態。首輪機內僅記錄方向，以 EP83 做研究資料回傳。取得實際來源與動態真值後再評估 AAT 尺度、轉向遲滯、呼吸干擾及 DFD 增量。

參考方向：[機內開發階段](../FP_AF_FIRMWARE_ROADMAP_2026-09-27.md)（位於 SIGMAfp_re 工作區的 `projects/`；fpSup 單獨 checkout 不包含該研究目錄）。
