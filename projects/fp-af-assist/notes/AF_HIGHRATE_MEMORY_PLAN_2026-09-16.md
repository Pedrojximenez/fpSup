# fp AF high-rate：RAM／pool 版圖候選

日期：2026-09-16。這是 **離線、未取得 lease 的配置審查**；沒有讀寫相機或 USB。
所有 `+offset` 都相對於 runtime 從 `C3757A7C` 讀出的 DMA-pool base，絕不是固定實體位址。

## 結論：候選窗口

第一版可把 `pool +0x50000..+0x65000`（`0x15000`／86,016 bytes）送交 ownership 審查：

| pool offset | 大小 | 候選用途 |
|---:|---:|---|
| `+0x50000..+0x502D4` | 724 | 現行 recorder bytes |
| `+0x502D4..+0x50400` | 300 | alignment／禁止使用 |
| `+0x50400..+0x50BE8` | 2,024 | 現行 freestanding sender core + completion checker |
| `+0x50BE8..+0x50C00` | 24 | alignment／禁止使用 |
| `+0x50C00..+0x54000` | `0x3400` | 尚未完成的 firmware adapter 預留；不是已證足夠 |
| `+0x54000..+0x54040` | 64 | capture state，64-byte aligned |
| `+0x54040..+0x54080` | 64 | records alignment guard |
| `+0x54080..+0x5C080` | `0x8000` | 256 × 128-byte records |
| `+0x5C080..+0x5C400` | `0x380` | DMA alignment guard |
| `+0x5C400..+0x64480` | `0x8080` | 完整 AFB1 DMA frame；絕對地址須至少 64-byte aligned |
| `+0x64480..+0x64800` | `0x380` | guard |
| `+0x64800..+0x64820` | 32 | `af_tx_request` |
| `+0x64820..+0x64840` | 32 | `af_tx_result` |
| `+0x64840..+0x64858` | 24 | `af_tx_ops`（ARM32 pointers） |
| `+0x64858..+0x64880` | 40 | `af_ep83_receipt` 一致 completion snapshot |
| `+0x64880..+0x65000` | `0x780` | adapter private state／guard；尚未分配 |

`0x8080` 是 `64-byte AFB1 header + 64-byte capture header + 0x8000 records`。
這個窗口與目前已知 gcsv writer 結尾之間仍有 `0x96C8` bytes，但這只是 source-level
不重疊，不是 runtime ownership。

## 現行 source／build 可直接證明的邊界

- AutoRun 要求一個 1 MiB pool，base 存在 `C3757A7C`；live 時不得以危險的
  `memmgr bufmem get`／`bufchk` 重新探測大小。
- shell 使用 `+0x0000` frame、`+0x2000..+0x6000` 16 KiB capture，另有
  `+0x6800` fault counters。`putfile.py` 的 staging 從 `+0x10000` 開始，會隨檔案長度
  延伸，因此可以覆蓋本候選；AF lease 期間禁止 put/get/direct-dump/memprobe 等共享工具。
- loader 的 file object／read window 是 `+0x7000..+0x28000`；stage2 在其中執行並複製
  sections。本候選從 `+0x50000` 開始，不與 boot-time staging 重疊。
- 現行 gyro runtime 保留 `+0x42000..+0x43000` file object、
  `+0x43000..+0x43414` job pool。最大 gcsv writer section 是 10,552 bytes，
  位於 `+0x44000..+0x46938`；本候選不與它們重疊。
- 現行 loader 只有 copy sections，`VSHL.BIN` 固定 pad 32 KiB，沒有 BSS reservation。
  不能把 records 與 DMA 的 65 KiB 零資料硬塞成 sections；card 路徑需要小型 runtime
  initializer 或明確的 BSS/lease 描述，不能靠「未出現在 VSHL」推定空閒。

## 必須先解的 code-entry 限制

`C022C858` 的 ARM `BL` 只有約 ±32 MiB；它無法直接跳到位於 `0x4...` 的 pool code。
`build_publication.py` 的預設 direct-BL 模式會拒絕此配置；本輪已新增顯式 `veneer_base`
選項與離線測試，分開記錄／驗證真正 code base 與 hook entry，但仍不提供 installer 或 lease。

最小候選是另借一個近端 8-byte veneer，例如 `C072FC00`：

```text
ldr pc, [pc, #-4]
.word pool_base + 0x50000
```

hook 的 `BL` 指向 veneer，veneer 不改 registers／SP／flags，再跳 pool recorder。這仍不是 lease：
若 veneer 確定為 `C072FC00`，離線編碼的候選 hook word 是 `0xEB140CE8`（原字仍須是
`0xEB00485C`）；地址或 before-image 任一不符都不可使用。
`C072FC00..C072FFFF` 是 `dumpdirect` 與 AF collector 共用的 1 KiB slot；hook 還掛著時 veneer
不可被覆寫。若不願長期排他借此 slot，就必須另找已授權近端 code slot，或把 recorder 留在
近端 cave。installer 也必須把「實際 code base」與「hook entry」分開驗證及記錄。

現行 recorder 內嵌 state／records 絕對地址。live installer 必須在讀出穩定 pool base 後組譯，
或先把 recorder 改成 pool-relative；目前 card build 尚不能對這些 literals 做 runtime relocation。

## 上機前只讀證據（仍不等於 lease）

1. 核對 fp 5.02 身分、`C022C858 == 0xEB00485C` 及鄰近 audited words；未知 hook owner 立即停止。
2. 連續讀 `C3757A7C` 至少三次：值相同、非零、合理對齊且在已知 pool address class；再以
   **實際正在執行的 AutoRun/VSHL build identity** 證明它配置 1 MiB，不能套用歷史 base。
3. 解析該 build 的 VSHL section table並核對 resident code hashes；確認沒有額外 pool-relative
   section 落入 `+0x50000..+0x65000`。候選 before-image 在兩個靜止時點相同只能算
   non-interference evidence，不能自行創造 ownership。
4. 對 veneer slot 核對完整 before-image、`echo` slot `C0BAC2F8 == C03D99A0`、
   `/tmp/fp-af-fusion.lock` 排他，且沒有 collector／dumpdirect／另一 installer owner。
5. EP83 需另核對 host descriptor 的 bulk MPS、DALEPENA physical-7、`C31E3270` 的 TRB pointer
   與 idle/HWO 狀態、無 stale completion，以及唯一 USB session owner。read-only snapshot 無法排除
   隱藏 owner；preflight 仍需明確 lease，不能只回傳常數 true。
   新 ABI 稽核已證有 native PTP event producer 共用 ctx3；還須核對 controller runtime mode，
   不能只看 descriptor。見 [EP83_SENDER_ABI](EP83_SENDER_ABI_2026-09-16.md)。
6. DMA bus mapping必須針對本次 pool base獨立核對。現行 worker 使用
   `bus = cpu - 0x40000000` 是參考實作，不得未經驗證直接泛化。

## 尚需明確批准／未完成

- 先取得使用者對新 hook **`C022C858`** 的明確批准；先前只涵蓋
  `C072F700..C072F9FF` 的同意不包含它，也不包含 veneer 或本 pool window。
- 明確批准並 lease veneer 的實際地址、`pool +0x50000..+0x65000`、EP83 TRB ownership，
  以及必要的 D-cache clean／I-cache invalidate。所有寫入都要 read-back，失敗不得盲重試 hook。
- sender 的 firmware adapter、task execution context、8-byte stack alignment、completion identity
  尚未完成；本表沒有配置新 task stack，也不宣稱 `+0x3400` adapter reserve 一定足夠。
- detach 必須在 AF-task quiescence 下核對 owner、還原原字並發布 cache；`full=1` 不釋放
  code/state/records，未知 EP83 結果也不釋放 DMA frame。

因此這份配置只把下一步縮成一個可審查窗口；在 runtime identity、排他 owner 與使用者授權成立前，
不得把它標成 `deployment_ready`，也不得操作相機。

## 後續限定唯讀檢查

2026-09-16 使用者同意後，native version 与兩項固定 mem get 成功：
pool pointer=`0x44F6FE00`，故候選窗口是 `0x44FBFE00..0x44FD4DFF`（end-exclusive `0x44FD4E00`）。
原始證據：`../highrate/runtime-read-20260916-a.jsonl`。只读一次，不聲稱穩定性／映射／lease 成立。
實測 pool base 為 512-byte 而非 1,024-byte aligned；DMA frame 候選 `0x44FCC200` 仍符合 sender
要求的 64-byte alignment。USB MPS 為 1,024 不表示 DMA payload 起點也必須 1,024 aligned；
上表已更正先前把 relative offset 對齊誤寫成 absolute alignment 的說法。
