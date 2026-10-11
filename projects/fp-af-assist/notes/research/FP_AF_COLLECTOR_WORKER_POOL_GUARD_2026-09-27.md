# AF collector：現行 worker pool 與 live lease 阻擋

2026-09-27。本修正與驗證完全離線；沒有連 socket／USB、上傳、換 worker 或移動鏡頭。

## 已確認的來源差異

`fpSup/fp_usb_shell/camera/worker.S` 的 `spawn` 分別配置 buffer pool 與常駐 code，發布於
`C072F050`（pool）、`C072F054`（配置大小）及 `C072F058`（code）。`CAP_PTR=C072F04C`
為 0 時，`serve` 從 `*C072F050+0x2000` 送回資料；`CAP_LEN=C072F040` 指定長度。
`putfile.py` 與 `asm/dumpraw.S` 使用此 ABI。

歷史 collector／snapshot 仍讀 `C3757A7C`，此處在現行分離配置設計是 logger pool。
snapshot 先將 212 bytes 寫到 `*C3757A7C+0x2000`，又清 `CAP_PTR=0`，會使目前 worker
回傳另一個 buffer。只改 host 的 pool 檢查常數不能修復 ARM handler 的實際寫入目的地。
亦不能只設 `CAP_PTR` 指向 logger pool：那仍未取得 logger 記憶體所有權。

## 最小修正

- ARM 候選必須由 builder 明確提供 `AF_WORKER_POOL_POINTER=0xC072F050`；缺值或 legacy
  `C3757A7C` 都拒絕組譯。host／ARM 共用同一候選 ABI，binary v1／v2／v3 格式與 JSON v7 不變。
- `collect` 及 `installed_snapshot_handler` 於任何相機 I/O 前無條件 fail closed；無 CLI／env
  bypass。`inspect` 明列 `live_collection_enabled=false`，離線 decode／mock 保持可用。
- 原因不只 DMA：`F700` 也是 `store_boot.S` 的啟動碼位置；現行 host 工具採用 `cave.claim`。
  echo 原值不能證明歷史 record／nonce `C072F700..C072F7D7` 或 code
  `C072FC00..C072FFFF` 的所有權。worker 身分、pool／code 配置範圍及完整記憶體租用
  尚待接入審核；本次沒有以指標值看似合理來重新開放舊 installer。

離線 handler 為 1000 bytes，SHA-256
`cded290f04b2a7ec14715255292a8036258aad1ca3eb7e8e905979f0b61fec22`。
這是候選的 binary 身分，不是正在執行版本的證明。

## 驗證與界限

`test_af_fusion_collector.py` 保留歷史 framing／echo cleanup 測試（其中 installer 測試
明確 mock live gate），並新增入口零 I/O 阻擋、明確 ABI 與 ARM 模擬。
ARM 測試使用不同的 worker／logger pool，執行實際 snapshot 指令，驗證資料只複製到
worker capture buffer、logger pool 不變、邊界 sentinel 不變、CAP_PTR=0／CAP_LEN=212，
且結果仍可用 v3 decoder 解碼。時鐘 getter 是模擬；這不是實機時序或 DMA coherency 驗證。
Unicorn JIT 若被執行環境阻擋，此項明列 skipped，不能算已完成 ARM 驗證。

2026-09-27 已在允許 JIT 的離線測試環境跑完 **62 項，無 skipped**；沒有相機 I/O。
後續先建立可核對的 running worker 身分與 owned-memory lease，再另行審核是否重新開放 live。
