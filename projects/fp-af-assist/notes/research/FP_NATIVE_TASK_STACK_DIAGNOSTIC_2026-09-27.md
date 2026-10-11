# fp 5.02：原生 task 診斷的 ABI 差異與 stack 證據界限

2026-09-27。唯讀離線核對 ROM、反編譯與 root 已收集的原生 shell 回覆；本次分析沒有相機／USB／socket 操作，也沒有寫入相機 RAM。此文件不批准 observer 安裝或新增 64-byte frame。

ROM：`out/seg0_c0000000.bin`，base `0xC0000000`，49,245,696 bytes，SHA-256 `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`。

本次資料：[native-preflight.jsonl](../../../../research/autofocus/captures/native-preflight/20260927-121028/native-preflight.jsonl)。原生指令固定為 `tkos skdump <name> 0`，五個名稱：AfMgr、LensFocs、Tracking、FdTsk、EyeDtctn。尾參數 0 抑制 stack body dump，不抑制 metadata／register 列印。

## 已證明：skdump 列印了 getter 沒有寫入的欄位

Shell handler `C0411520` 在 `C0411630..C0411640` 傳入：

```text
r0 = task ID
r1 = shell SP + 0x30   # general-register output buffer
r2 = shell SP + 0x24   # execution-information output buffer
r3 = shell SP + 0x1C   # control-register output buffer
BL C0682FEC
```

`C0682FEC` 的 service literal `C068300C = 0x800D0400`。Dispatcher `C00011D0` 使用 `C0001568` 指向的表 base `C0021040`，signed high-half index 得 table slot `C0001074 → C0001990`。後者在 `C0001A40` 呼叫 **`C0001938`**，由目標 TCB `+0x78` 取得保存 context-frame 指標。

`C0001938..C0001988` 的 ARM 指令實際寫入：

| output | 寫入位置 | 來源／證據 |
|---|---|---|
| r1 | offsets `0x00..0x2C`，恰好 12 words | `C000194C..C000195C` loop，index `< 0xC` |
| r2 | `+0x00` | saved context `+0xCC`，`C0001968/C000196C` |
| r2 | `+0x08` | saved context `+0x30`，`C0001970/C0001974` |
| r3 | `+0x00` | TCB `+0x78` 的 saved-context pointer，`C000197C` |
| r3 | `+0x04` | saved context `+0x34`，`C0001980/C0001984` |

但 shell 沒有預先清零這三塊 output，並且：

- `C04116F8..C041171C` 列印 **13** 個 `r[]`，其中 `r[12]` 是 r1+0x30，getter 沒有寫入。
- `C0411738` 從 shell SP+0x28 讀 `cpsr`，即 r2+0x04，getter 沒有寫入。
- `C0411760` 從 shell SP+0x64 讀 `lr`，即 r1+0x34，getter 沒有寫入。

因此這三欄是 shell local stack 殘值，不能當目標 task 的 CPU register。這是原生 shell 顯示端與 getter 的 layout 不一致，不是此次 host parser 把列錯置。

反編譯對應：[blk_c00.c:795](../../../../out/decomp/full/blk_c00.c#L795)、[blk_c00.c:823](../../../../out/decomp/full/blk_c00.c#L823)、[blk_c04.c:11209](../../../../out/decomp/full/blk_c04.c#L11209)。结論以以上實際 ROM 指令為準。

## 本次回覆與解讀限制

| task | ID | stksz | istk | printed ssp | printed r[12] |
|---|---:|---:|---|---|---|
| AfMgr | 108 | `0x4000` | `C3B265CC` | `C3B262AC` | `45039982` |
| LensFocs | 25 | `0x2000` | `C3A1D4AC` | `C3A1D328` | `45039980` |
| Tracking | 64 | `0x2000` | `C3AAC2EC` | `C3AAC148` | `45039980` |
| FdTsk | 63 | `0x1400` | `C3AAA2E4` | `C3AAA214` | `45039980` |
| EyeDtctn | 62 | `0x1000` | `C3AA8EDC` | `C3AA8D6C` | `45039980` |

五者 printed `cpsr=7A7A7A7A`、`lr=C01E77B5`。前者符合 task-ID 122 的 byte-fill 形狀；後續同次開機的 stkchk 確實列出 `122/0x7A _VSHL`，支持它是 shell worker stack 殘值的解釋。後者只可視為 local 殘值。FdTsk 的 r[0..11] 全為 `3F3F3F3F`，符合其 ID 63 的 sentinel；各 task 的其他 sentinel 也與自身 ID 不同，進一步區分保存 context 的資料與 shell 未填欄位。

**printed ssp 有實際寫入來源**：它是 debugger 擷取的目標 TCB `+0x78` 保存 context-frame pointer。它不是保存前程式執行點的原始 SP，也不是同一時刻 running task 的 live SP，更不是歷史 stack 最大深度。`istk - ssp` 可保留為兩個 raw 值的差，不能命名為 observer 可用餘量或據以批准多 64 bytes。

printed `pc`、`mode`、`usp` 的 output slots 有寫入，但本文件沒有擴大解讀完整保存 frame；特別是「mode」只是 getter 的 r2+8，不據其值推斷 CPU mode 或重建完整寄存器集。

`C0001990` 使用 `C000EC14/C000EC24` 在內部暫時 mask／restore IRQ/FIQ，完成有限 context 複製；沒有改目標保存 context。shell 列印發生於返回後，metadata 與 context 兩次查詢之間不是原子 snapshot。

## stkchk：歷史 sentinel 掃描，沒有單 task 選項

Command table `C0BC5AD8 → C04117F8`，handler 把 argc/argv 保存於 local 後不再使用。即使提供 task 名稱，仍固定呼叫 `C0682ED8(ids, 500)`，然後遍歷所有回傳 ID；**不可把 `tkos stkchk AfMgr` 當限制範圍的方式**。

每個有效 task：`td_ref_tsk` 取得 `istk/stksz`，從 `istk-stksz` 起讀取 32-bit word，直到不等於 `(task_id & 0xFF) * 0x01010101` 或抵達 `istk`。輸出的 `max_use` 是 `istk-first_non_sentinel`（向下取整至 4-byte），不是目前 SP。這是歷史使用的估計：未被實際寫入的 stack reservation／碰巧等於 sentinel 的資料可能使它低估，尚未走過的深路徑也不包含在內。

沒有 stack memset、目標 task 暫停、priority 修改或 lens command；有全 task 記憶體掃描、kernel query 與大量 shell 列印。handler 自身在 `C04117F8/C0411804` PUSH 32 bytes 並 SUB `0x82C`，合計 **`0x84C` bytes**，不含子呼叫。這是執行診斷的 task 的成本，不是被查 task 的成本。

原始文字輸出可由固定 ROM format strings 精確估計：

- Header `C0BC56AC` 長度 52 bytes。
- 一列通常 78 bytes（task ID <256、stack size ≤`0xFFFFF`），較大 ID 增至 79。
- task ID≤500、32-bit stack size／max_use、正常 0..100% 下，每列最多 85 bytes。
- 最多 500 列，保守 raw 上界 **42,552 bytes**。無分頁、無 limit 參數。

維護中的 worker `camera/worker.S` 的 `CAP_MAX=0x4000`，shell capture 上限 **16,384 raw bytes**。`fpshd` 對長回覆輸出 `OKX `＋hex，因此 wire 最大約 **32,774 bytes**（含 prefix／newline）。目前 `focus_bridge.Transport._exchange` 的 16,384-byte wire 上限，約 105 列便可能碰到；不能直接用它執行此全 task 輸出而期待收完整。

若 root 決定做一次此原生唯讀查詢，接收器應只允許固定命令、維持單 owner／整段 deadline／不重試，並有約 40 KiB wire cap。**增大 host cap 不會增大 camera capture**；收到恰好／接近 16 KiB raw、最後一列不完整或缺少所需 task 時，標為可能截斷，不能認定完整全表。無需改既有 Transport 或 daemon，也不應以串接 shell pipe 假設 camera 有 filter 功能。

這次先保留 `stack_headroom_verified=false`。一次 stkchk 可補 sentinel 高水位證據；仍需覆蓋相關 AF／face／AAT 執行路徑以及 observer 額外成本，不能單靠 idle 結果宣稱正式 stack 安全。

## 本次一次性 stkchk 結果

root 在上述分析後，於 2026-09-27 12:25:52 +08:00 執行一次原生 `tkos stkchk`，使用既有 fpsh client、AF 排他鎖、5 秒 host 上限與不重試。沒有 task control／lens command／camera RAM 寫入；本文件作者仍只分析已存在資料。

完整回覆保存在 [native-stack-check.json](../../../../research/autofocus/captures/native-preflight/20260927-121028/native-stack-check.json)。exit 0、stderr 空、**9,490 raw-text bytes**，小於 worker 16 KiB capture 上限；含 122 行（header 加 121 task 列），所需五列完整，沒有以缺失列推估。

| task | stksz | sentinel max_use | 表面剩餘量 | 使用率 |
|---|---:|---:|---:|---:|
| LensFocs | `0x2000` | `0x364` | `0x1C9C` | 11% |
| EyeDtctn | `0x1000` | `0x170` | `0xE90` | 9% |
| FdTsk | `0x1400` | `0xA0` | `0x1360` | 4% |
| Tracking | `0x2000` | `0x1A4` | `0x1E5C` | 6% |
| AfMgr | `0x4000` | `0x2390` | `0x1C70` | 56% |

`_VSHL` 自身為 ID 122、stack `0x2000`、sentinel max_use `0xA9C`，這包含診斷曾走過的路徑。表面剩餘量只是 `stksz-max_use`，尚非 observer 可用量保證。

尤其 FdTsk／Tracking 在此次觀察中未證明正執行 active detector／tracker workload；低使用量不能證明 face parser／完整 AAT Run 的最壞深度，更不能直接批准新增 64-byte frame。未藉此原生查詢啟用 AF／face／AAT、初始化後端或更改模式；`stack_headroom_verified=false` 維持不變。
