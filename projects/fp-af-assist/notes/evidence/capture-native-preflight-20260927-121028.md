# fp 5.02：首次原生唯讀環境核對

原程式／證據目錄：[research/autofocus/captures/native-preflight/20260927-121028](../../../../research/autofocus/captures/native-preflight/20260927-121028/)。筆記已集中至 fp-af-assist；下文歷史結果與限制保留。

2026-09-27，使用者接上既有 USB shell 後執行。沒有自訂 RAM 寫入、hook 安裝、鏡頭命令、設定變更、daemon 啟停或卡片操作。

## 實測結果

- 型號 `w71c1`、`5.02.0.V91`、build `13aa621060efff11aaba9b21ad925005302605cf`，既有 daemon 3.0.0。
- `af_native_preflight.py` 的 **64 次交換完成，0 失敗／0 重試**。四個 callsite word 和 12 個鄰近／callee guard 全部符合 ROM；echo 前後維持原廠 `C03D99A0`。
- 前後兩次捕捉狀態未見 recording／busy／shutter gate；這不是整段期間的原子 interlock。四個 focus getter 前後一致：rectangle `480 373 64 64`、mode `0`、area `0`、size `2`，保留原生值，不臆測未核對 enum。
- Native-L selector/vtable 符合；cached lens position raw `10663` 只作診斷，沒有下鏡頭命令或證明光學合焦。
- Worker pool=`0x45037980`、size=`0x100000`、code=`0x451379C0`；舊 `C3757A7C=0`。不能把舊 collector 的 DMA 地址直接沿用。這些指標也不代表可供新 observer 占用。
- Cave bump=`0xC072E064`；live boot stamp=`15340463`，host register=`14652409`，所以保存的 host claims 屬於不同 boot，不能沿用。本輪未 claim／重設 register。`F700`／`FC00` 前 16 bytes 為零，不構成所有權證據。
- Face manager 已初始化、vtable 符合；本次 group0 全零。AAT backend vtables／model／publication 也全零，沒有可用主體樣本。沒有呼叫帶 lazy-init 副作用的 getter，也未自動切換設定。

## Task stack

另以現有 `fpsh`、AF 專用 lock、5 秒主機上限執行一次唯讀 `tkos stkchk`，收到 9,490 bytes，未達 worker 的 16 KiB capture 上限。保存原始回覆，不重試。

| Task | 原廠 stack bytes | sentinel 推算最大使用 | 剩餘 sentinel bytes |
|---|---:|---:|---:|
| AfMgr | 16384 | 9104 | 7280 |
| LensFocs | 8192 | 868 | 7324 |
| Tracking | 8192 | 420 | 7772 |
| FdTsk | 5120 | 160 | 4960 |
| EyeDtctn | 4096 | 368 | 3728 |

這是當次已走過路徑的 sentinel 統計。FdTsk／Tracking 沒有證明經歷有效主體負載，不能據此核准額外 64 bytes 或認證最壞 stack。`stack_headroom_verified` 維持 false。

`skdump NAME 0` 的 metadata 原樣保存，但原廠 shell 與 debug API 的 struct 佈局不合：印出的 `r12/cpsr/lr` 含未初始化 stack 內容，`ssp` 也只是保存 context frame。未把这些欄位用來估算餘量；詳細證據見 [task stack 診斷](../research/FP_NATIVE_TASK_STACK_DIAGNOSTIC_2026-09-27.md)。

## 本輪軟體修正與下一步

舊 collector 在現行 shell 具有兩個不同問題：CPU-copy 目的地不是 worker 真正回傳的 buffer；固定 `F700/FC00` scratch 已無可沿用的 lease。已把離線 handler 改為明確 current worker ABI，並讓 collect／直接 installer 在任何 I/O 前拒絕，沒有繞過旗標。inspect／decode／mock 保留；binary v1–v3、JSON v7 不變。[修正紀錄](../research/FP_AF_COLLECTOR_WORKER_POOL_GUARD_2026-09-27.md)

本輪 autofocus 工具 **173 tests 全過，無 skip**，包括 19 項固定唯讀 preflight 測試與實際 ARM 模擬的 worker/logger pool 分離。這不是 173 次相機測試。

下一輪先取得啟用臉部辨識且主體入鏡的 raw 資料，仍以只讀檢查來源為主。Live installer 必須另建目前 boot 的 owned-memory lease、核對 resident worker、採用共用載入／快取／journal／停止生命週期。尚未安裝四路 observer，沒有 AF／AAT 光學或追焦性能結論。

## 檔案

- `connection.json`：最初 STATUS／version 原始回覆。
- `native-preflight.jsonl`：逐次 request／reply、固定範圍 raw words、前後設定与結果。
- `native-stack-check.json`：單次原廠 stack 統計完整原始輸出。
- `host-cave-register.json`：唯讀保存當時 host register，不代表 live claims。
- `native-subject-decoded.json`：從原始 bytes 另行解碼，所有 geometry gates 保持 false。
- `analysis.json`：本輪結論與證據 SHA-256；不修改原始回覆。
- `offline-regression.json`／`.log`：173 項離線測試與當次來源 SHA-256。
