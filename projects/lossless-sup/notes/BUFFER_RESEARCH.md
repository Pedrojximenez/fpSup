# fpLossless 緩衝區研究備查（非目前實作清單）

目前採用的精簡設計已整理到 [`BUFFER_DESIGN.md`](BUFFER_DESIGN.md)。本檔保留先前的
容量推導、證據審閱與未來 async／VFR 討論，避免丟失研究；不要求首版實作下列完整框架。

9/24 訂正：movie cookie 不是 0，原生 `C03A55D0` 逐幀完成回呼已定位；正確 scatter 鏈與
SD descriptor aggregation 見 [`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md)。
本檔舊的「未找到通知」及 cookie 判讀不再採用。容量入口已修正，整數 14-bit 模型值
為 3,957,888 B；硬體最壞界仍未證明。現行最小下一步以 BUFFER_DESIGN §8 為準。

日期：2026-09-23，納入當日 G2/G3/G4/G5 新證據。  
狀態：離線設計；依「不要過度設計」收斂首版，未實作或部署。  
範圍：FHD RAW12 首版；預留 adaptive mixed compression 與 true frame dropping。  
產品順序與全域 gates：[`ROADMAP.md`](ROADMAP.md)。本文件擁有緩衝區／釋放協定的細節。

## 1. 設計決策

**首版只解決 G5 的逐幀內容重用問題，不先搭完整動態框架。**

- 保留現有同步 encode、單 node 的 header+payload 寫入方式。
- 使用固定數量的獨立 output slots，先以簡單陣列記錄地址、容量、有效長度、幀號、使用中狀態。
- 查清 payload 與 descriptor 何時不再被使用，再釋放／重用；沒有空 slot 就停止，不覆寫。
- 未來抽幀只先預留來源幀號、時間戳，以及 encode 前的決策位置；目前不實作 DROP。

slot 數量由實際 hold time 與可配置記憶體決定。**2、4 或 8 slots 都不是目前已證實足夠的數量。**
容量邊界、每幀 metadata 與不提早重用仍是必要條件；不要求先建立通用 allocator／framework。

**下文多池、ticket、journal、async worker、VFR 等完整設計保留備查，不是首版前置。**
等實際功能需要時才選用；先前提出的 pool 數字與 ABI 不作定案。下一步以 §14 為準。

## 2. 新證據如何改變設計

| 證據 | 目前成立的內容 | 對設計的影響 |
|---|---|---|
| [G2](../build/ledger-g2-20260923.json) | 512×368 已 live encode；一個室內 fixture 為 13,652 µs | 可用正式 tile 做 baseline；scene matrix 尚未完成 |
| [camera bitstream](../build/ledger-camera-bitstream-20260923.json) | 相機輸出對同來源 2,110,240 samples 完全相等；sample SHA-256 一致 | codec 像素無損有直接證據 |
| [G3](../build/ledger-g3-20260923.json) | 一個 3,244,544-byte node 的 flush call 372 µs 返回 | call return 不能當作卡片完成，也尚未證明 source 可重用 |
| [G4a](../build/ledger-g4a-mirror-20260923.json) | 自有 buffer 重導向、水印及 `0x8` alias CPU writes + `dsb` 在該測試成立 | 自有完整 frame slot 可交給原 writer；alias 用法可沿用於同契約 |
| [G4b](../build/ledger-g4b-compressed-20260923.json) | 一張 1,396,736-byte compressed DNG 寫卡且可解碼 | contiguous header+payload、single-node 路線優先 |
| [G5](../build/ledger-g5-sustained-20260923.json) | 8 次 encode 完成；讀回的 frame 1、2、4、8 完全相同 | 目前單區重用未維持 frame identity；G5 integrity FAIL |

G5 的 ledger 僅列出四張已讀回檢查的 frame，不能擴寫成八張都經完整比對。這是非常強的共享
buffer 壽命問題證據；但尚未找到最後一次讀取／copy／DMA completion，因此不能把「最後一幀被
共用」直接解釋為整段結束才寫卡，也不能據此選定八個 slots。
不同 source pointer 也不等於已量到不同 source-content hash。0-based log row 3 對應第四次
encode，預期檔案應為 1,301,504 B，但 checked frame 4 是 1,302,528 B；不是改 0/1-based
即可解釋。descriptor/node 被重用或人工關聯錯誤都仍可能，不能只歸因於 payload。下一次需要
`source_seq -> slot/generation -> pre-submit hash/length -> filename/size/hash` manifest。

372 µs 對 3.24 MB 隱含約 8.7 GB/s，排除了「這次返回前已完成相同量的實體 SD 傳輸」解讀。
仍需區分「只收 pointer」、「copy 到下游 buffer」、「async DMA」等情形；安全 reuse 只要求原
buffer 已無讀者，不必等同於資料已耐斷電保存。

另外兩個重要邊界：

- G4b 與相鄰 stock frame 的差異是跨幀比較，不能作為該輸出幀的 bit-exact 證明；bit-exact
  證據來自另外的 retained-camera-payload run。
- mixed 大小可寫卡，沒有驗證 CinemaDngPlay。播放器 first-selected-frame capacity 與 writer
  接受可變 node length 是不同問題；playback gate 保留。

## 3. 資源分池，彼此獨立計數

| Pool／資源 | 建議起始設計 | 誰占用／何時歸還 |
|---|---|---|
| Output pool | N 個完整 contiguous DNG slabs，N 由量測選定 | encoder/header builder -> storage reader；最後讀者 release 後歸還 |
| Optional input pool | 第一階段為 0；async codec 才增加 | source lease 或完整 stock DNG copy；codec/source readers 完成後歸還 |
| Ticket pool | 64 個 × 256 B = 16 KiB，proposal | 每個仍待決定／提交／收 completion 的 frame 一筆；資料欄位不得存在 stack |
| Decision journal ring | 256 個 × 64 B = 16 KiB，proposal | 每幀最多兩筆 canonical records；copy 入 immutable batch 後才釋放 |
| Journal batch pool | 獨立 immutable append blocks，數量／block size 待 latency 設定 | decision copy 到 block 後可還 ring；block 等自身 storage release 才歸還 |
| Request contexts | 有界、每 submission 一份，與 output slot 分離 | 保存不可變 token/result；直到 backend 保證不再 callback 才歸還 |
| Control／completion | 獨立 4 KiB control reserve + 每 slot completion cell | STOP/ERROR/EOS、延迟 completion；不與普通 frame 爭最後一個 queue entry |

數字為初始 host model／ABI 預算，並非相機 allocation 成功證據。ticket 數、journal 深度與 output
slot 數不能綁成同一常數；DROP 不應占用一個數 MiB 的影像區，也不應等前面的 SD frame 完成才
能釋放小型 ticket。可把 DROP 轉成 journal-owned record／span 後立即回收 ticket。

引擎 init/final/temporary table 第一版仍跟各 output slot 放一起，避免另引入 table lifetime 假設。
將來證明 engine idle 後不再讀 table，才可共用一份 engine work area；immutable DNG header 裡的
TileByteCounts/TileOffsets 則永遠屬於該 frame，不能共用。

## 4. Output slot 的具體版面

### 4.1 沿用已寫卡成功的 contiguous layout

每 slot 由 allocator 給出獨立 handle，至少 1 KiB alignment；pool 保存 handles 陣列，不要求
所有 slots 位於同一個巨型連續 allocation。不要在 REC hot path 反覆 alloc/free。

以 slot size `S`、尾區 `T=0x10000` 定義：

```text
relative offset         contents
0x000000 .. 0x0133FF     live source header copy (78,848 B)
0x013400 .. 0x0137FF     rebuilt root IFD + tile arrays + padding (1,024 B)
0x013800 .. S-T-1        codec payload capacity C = S-T-0x13800
S-T                     output canary
S-T+0x1000              final codec size table + canary
S-T+0x1400              temporary codec size table + canary
S-T+0x2000              template / patch-plan region, optional
S-T+0x2400              template metadata, bounded
S-4                     allocation-end canary
```

這與現行 4 MiB source 的 `WORK_CAP=0x3F0000`、`TABLE_OFF=0x3F1000`、
`TABLE_TMP_OFF=0x3F1400`、`OUT_OFF=0x13800` 一致。control descriptors 另放 CPU-owned
pool，不把敏感 lifecycle state 貼在可能被 codec overrun 的 payload 後。

| S | Header | Payload capacity C | 尾區 | 定位 |
|---|---:|---:|---:|---|
| 4 MiB | 79,872 B | 4,048,896 B | 65,536 B | 現行實驗配置；一般輸入硬上界未證明 |
| 16 MiB | 79,872 B | 16,631,808 B | 65,536 B | 下節條件式保守配置候選；allocator/硬體契約待證 |

實际提交一個 `{base_handle, 0x13800 + encoded_bytes, kind=2}` node。**只提交有效長度**，
尾區、canaries、template 不進 DNG。每個 tile 的結束須檢查 EOI 與允許的尾端零 padding；
相機實測最後一 tile 包含使總 payload 512-byte 對齊的 padding，不能任意截短其 count。

### 4.2 容量證明必須重新開啟

[`output_bound.py`](../tools/output_bound.py) 自己已聲明：`13.9998 bits/sample` 使用
optimal-Huffman 模型，**不是硬體保證**。此外：

- [`ljcost.py`](../../../research/slimRAW/ljcost.py) 計算 entropy bits + 約 96 bytes marker，
  未計入 entropy byte 為 `0xFF` 時插入 `0x00`。
- [`ljenc.py`](../../../research/slimRAW/ljenc.py) 的 `_BW.put()` 有實際 stuffing。
- 96 bytes 是近似 marker budget；DHT 可變，不能直接作固定最壞上界。
- 單次數值搜索、取整與加 2–3% 餘裕都不會把條件式模型變成 hardware safety proof。

因此不能沿用「table 放在模型上界後，overrun 就不可能碰到」的結論。

一個可供 memory planning 的**條件式**保守 envelope：

```text
Npadded = 2048 * 1104 = 2,260,992 samples
假設：RAW12、predictor 1，magnitude bits <= 12
假設：每 sample 一個 Huffman code，length <= 16
假設：entropy byte stuffing 最壞增加至 2 倍
假設：每 tile 所有非 entropy marker/restart 額外用量 <= 4,096 B
假設：全 frame 尾 padding <= 511 B，沒有未知 DMA scratch 寫入

payload_bound = 12 * (2 * ceil((512*368)*(16+12)/8) + 4096) + 511
              = 15,876,607 B
header + payload_bound + control_tail = 16,022,015 B < 16 MiB
```

16-bit code 限制與 stuffing 來自主機 encoder 的現有 contract；相機 DHT、restart、marker與
DMA write footprint 必須另證。16 MiB 是在上述條件下可容納的設計選項，不是立即部署指令。
其他 bit depth、predictor、tile或解析度要重新計算，不能照搬。
一般式應逐 tile 取整 `sum(2*ceil(tile_bits/8)+marker_budget)`，不可先把所有 bits 合併後
只取整一次。此例每 tile 上限恰為 512 倍數，所以逐 tile 對齊不再增加；其他 geometry 另算。

容量收斂路徑：解析 retained camera payload 的所有 DHT／SOS／marker；檢查實際 code length
與 per-tile bytes；host 使用真正 byte writer 做 adversarial patterns；以可證明的 codec contract
建立整數上界。只有這個 proof 支持時才縮回 4/8 MiB。若無法證明、也配不到足夠空間，該
profile 不啟用；事後 canary 只負責偵測，無法防止已發生的 DMA 越界。

### 4.3 Source review 發現的容量入口缺口

目前 source 的 `build_image()` 僅對 `encode/encode-live/encode-sustained` 呼叫
`require_safe_arena()`；`compress/compress-sustained` 未共用該建置 gate。assembly 的輸出
加總也比較整個 `WORK_CAP`，未扣除 `OUT_OFF`。

下一個實作應只有一個產生 layout 的來源，並讓每種 phase 都消費同一 descriptor。共同檢查：

```text
payload_base = base + OUT_OFF
payload_end  = base + WORK_CAP
0 < encoded_bytes <= payload_end - payload_base
file_bytes = OUT_OFF + encoded_bytes            # checked arithmetic
each tile offset/count lies inside file_bytes
every table/template/guard range lies inside S and outside output
```

build-time gate 應要求有效的 `capacity_proof_id`，不是只比某個未證明的 estimate。runtime
size check仍保留，作為 contract violation 的診斷；兩者用途不同。
命名要區分 `STOCK_HEADER_COPY_BYTES=0x13400` 與 `COMPRESSED_HEADER_BYTES=OUT_OFF=0x13800`；
現行 source 的 `HDR_BYTES` 指前者，不能誤用作 file length。現有兩處 estimate 尚有 7 B drift，
新 generator 要求整數公式 exact equality，不接受「差 64 B 內」。未來 tile count 改變時，
`OUT_OFF=align_up(IFD_AT + ifd_size + 8*tile_count, 0x400)`；tables/template 也按數量推導。

## 5. 完成事件與 token

定義必須固定，不再共用 `DONE`：

1. `ENCODE_DONE`：codec 不再讀 source／寫 output；不表示 storage 不再读 output。
2. `SUBMIT_ACCEPTED`：writer 接受 `{pointer,length}`；不表示 buffer 可修改。
3. `BUFFER_RELEASED`：最後的 DMA／copy／writer reader 已放棄該 payload，允許 reuse。
4. `REQUEST_COMPLETE(result, transferred_bytes)`：這筆寫入 request 的終態；成功仍不等於 durable。

`FILE_CLOSED`／`DURABLE` 是另一路儲存狀態。若下游已把 bytes 複製到自己的 buffer，可以在
實體寫卡前 release 原 slot；反之，函式很快返回不能證明這個 copy 已完成。
如果下游 copy 後先 release 原 slot、稍後 I/O 失敗，slot 可以已被安全重用，但 frame 仍須
標 ERROR。request context／ticket 不得隨 output slot 提早回收；兩種 completion 分開追蹤。

每次租用使用：

```text
ticket = (boot_epoch, clip_epoch, source_seq)
slot_token = (boot_epoch, pool_id, slot_id, generation)
submission = (ticket, slot_token, submit_id, submitted_length)
```

completion 要比對完整 token，不可只比指標或 slot index。slot generation 每次 reuse 增加，
detect wrap 並在 quiescence 後換 epoch；stale／duplicate completion 不得減少新租用的 refcount。
新 clip 不可為了清 state 而使仍在途的 storage callback 失去 owner；先 drain，或隔離舊 epoch。

adapter 的硬前提：backend 必須原樣帶回每次 submission 的 immutable callback context 或
唯一 request id，且有「不會再 callback」的契約。只有相同 pointer／slot index 的事件不能
憑空還原 generation；若無法可靠關聯，reuse gate 仍不成立。context 不能在最後 callback 前
重用，即使其 payload 已 release。每個 context 另保留 callback/trampoline code 的 lifetime hold。

## 6. Ownership 狀態機與並發

```text
build axis: FREE -> RESERVED -> ENCODING -> HEADER_BUILD -> IMMUTABLE
submit axis: NOT_STARTED -> SUBMITTING -> ACCEPTED / REJECTED_NOT_TAKEN / AMBIGUOUS
release axis: NOT_ARMED -> PENDING -> SEEN
request axis: PENDING -> SUCCEEDED / FAILED

pre-submit clean cancellation -> return resources
unknown codec/storage outcome -> QUARANTINED
```

slot 上有獨立 hold bits：`CPU_BUILD`、`CODEC_DMA`、`SUBMIT_CALLER`、`STORAGE_READER`、
`VERIFY_READER`。只有所有 hold 清空、terminal state 合法、guard正常且 token相符時才能回池。
metadata journal 記錄先複製出去，避免只為等待 journal 寫卡而長期扣住影像 slot。
上述 axes 是正交狀態，不要求 callback 先後固定。`release=SEEN` 可以早於 submit 返回；
submit 返回只更新 submit axis，不能將 release 倒退為 PENDING。slot 的 free predicate：

```text
token valid && guards valid && all slot holds == 0 && !quarantined
&& (submit == ACCEPTED && release == SEEN
    || submit == REJECTED_NOT_TAKEN && reader ownership revoked
    || clean pre-submit cancellation)
```

request success 不阻擋已安全 release 的 payload 重用，但 request context 仍須保留至終態與
callback retirement；AMBIGUOUS 即使碰巧先收到 release 也先 quarantine，等待契約釐清。

提交流程需處理 **completion 在 submit 返回前同步發生**：

1. 將 token、長度、completion cell 初始化；設定 `SUBMIT_CALLER | STORAGE_READER`。
2. publish `SUBMITTING`，再呼叫 writer。
3. callback 可以清 `STORAGE_READER`，但 `SUBMIT_CALLER` 仍在，slot不能提前回池。
4. submit 返回後記 accept/reject。只有已證明 reject 不會保留 pointer，才可撤銷 storage hold。
5. 清 caller hold；owner檢查所有條件後回收。

IRQ callback 僅寫預留 completion cell、喚醒 owner task，不分配、不阻塞、不做 file I/O。
每個 in-flight slot 一個 release cell，另由 request context 接 I/O result；防止普通 telemetry
queue 滿時丟掉任一 completion。old request 的 late result 不得寫入該 slot 新 generation 的 cell。
多個 producer 用已驗證 MPSC mailbox 或短 critical section；不把它誤稱為 SPSC。

單一 coordinator 管理 free list、policy 與 ordered submission。encoder/storage workers 經
firmware mailbox/events 協調；共用指標與 64-bit timestamp 在 ARM32 上不能假設原子，需明確
critical section／sequence publication。`volatile` 本身不足以建立 ordering。

## 7. 首版與未來 async 的來源所有權

### 7.1 首版：同步 encode + 非同步 output leases

在當幀 source仍由原 call chain持有時，encode並複製 live metadata至 output slot，之後只把
owned output交給 writer。這避免現在就支付完整 raster copy，也避免先加入另一個 codec worker。

source 在 callback duration內可讀與未被上游改寫仍須由 frame-context gate維持；不得把 source
pointer放進 deferred queue就提前返回。

### 7.2 下一版：獨立 input與output pool

若要讓 codec worker延後處理來源，必須有 vendor retain/release，或立即複製完整 stock DNG。
建議 owned input copy保存完整 `0x318200` bytes，使未來 RAW bypass也能使用同一份資料。

候選 input slab：`align_up(0x318200 + 0x1000, 0x400) = 0x319400`，即 3,249,152 B；
包含完整 DNG及 4 KiB guard/padding餘裕。geometry或 stock shape改變時重新計算。

G4a 已量到 uncached full-frame copy 約 44.896 ms，超過 FHD23.976單幀 budget，因此 copy route
目前只可作研究備案；不能預設每幀 copy後仍可持續。先找 lease，或另量已驗證的快速 copy path。

source lease的兩條释放規則不同：

- KEEP_COMP：codec不再讀source，且 header／frame metadata已snapshotted後釋放。
- KEEP_RAW：storage尚在讀原 source，必須等該 source對應的 `BUFFER_RELEASED`。

因此 codec忙時 RAW bypass未必省記憶體，它可能讓 source lease持有更久。RAW與COMP必須
進同一個按 `source_seq`排序的提交佇列；不能讓後面的RAW直接越過前面的COMP。

## 8. 為動態抽幀預留的 admission contract

### 8.1 先配置小資源，再決定大資源

```text
observe source -> reserve ticket + journal credits -> snapshot identity/time
  -> KEEP_COMP: reserve output + codec admission; then read/copy/encode
  -> KEEP_RAW : reserve source lease or owned copy + ordered submit credit
  -> DROP     : append decision metadata; do not allocate output or run codec
```

reservation是transaction：任一步失敗，回收本次取得且無consumer的資源。固定lossless
不能取得slot時stop；adaptive mixed只有RAW路徑自己的資源也足夠才可RAW_PASS；VFR才能DROP。

「不寫某幀」需要 recorder層合法的 skip/cancel及source-release接口；不能在目前 segment-register
hook偽造成功返回或提交零長 node，否則可能留下空DNG、錯誤檔號或不平衡completion。
目前真正drop的接點尚未證明，先保留介面：`accept_frame`、`cancel_unsubmitted_frame`、
`release_source`、`report_frame_result`。

### 8.2 Journal與control必須在pool full時仍可用

初版每個 accepted frame 原子預留固定 `K=2` canonical credits：DECISION 與 TERMINAL；
DROP 的 terminal 可併入 decision，確定後歸還未用 credit。可丟失的詳細 trace telemetry 另設
ring，不消耗 correctness credits。journal 與 output 分池；completion 不依賴 journal 是否可寫。
命名保留 EOS、ERROR、ABORT、CLEAN_FOOTER、emergency DROP_SPAN cells，data 不可借用。

DROP紀錄可立即append到RAM ring或合併為連續 `DROP_SPAN(first_seq,last_seq,pts,reason)`，
再釋放ticket/source。**不要求每丟一幀就同步flush sidecar**：那會在同一張壅塞SD上新增等待。
emergency span 只能延伸連續、同 reason／timebase 的 DROP；不是普通 credit 耗盡後任意補帳。
classify 前必須有普通 credits 或可原子延伸的 span coverage。下一個 KEEP 之前，先把該 span
放入有序 journal；做不到就停止 admission，不能用一個 span 掩蓋交錯 KEEP/DROP。

DecisionRing consumer 將 records 複製到獨立 `JournalBatchPool` block，封好
`{epoch,batch_seq,first_seq,count,payload_len,CRC}` 後 immutable。decision cells 可在 copy 後
回收；batch block 只能在自己的 storage buffer-release 後回收，不以 submit return 回收。
batch 有獨立 token/request context，I/O result 與 durability 分離，遵循 §5–6 同一契約。

要明確區分 `DECISION_RECORDED_IN_RAM` 與 `JOURNAL_DURABLE`。批次journal保證的是帶CRC的
可復原durable prefix；斷電後未落卡的tail必須標記unknown/incomplete，不能補造精確drop史。
若產品要求每次drop都耐斷電，需額外持久化協定與效能預算，現設計不宣稱已達成。

journal高水位時提早停止admission、drain或切入預先保留的drop-span記錄；超出控制reserve仍
無法記錄時stop。sidecar與DNG共享同一SD，額外一條queue不會創造頻寬。

### 8.3 時間軸與策略邊界

- `source_seq`在任何selection之前分配；`output_seq`只對真正輸出的DNG分配。
- `source_seq`現階段代表此掛點觀察到的來源序列，不宣稱涵蓋上游已丟失的感測器幀。
- 23.976p使用 timescale=24000、每來源幀1001 ticks；writer-ready的1MHz clock另外保存。
- recorder epoch、原始TimeCodes、RawDataUniqueID都保存；writer tick不是曝光timestamp。
- 若下一個kept frame尚未知，上一幀duration暫未定；host由後續PTS及EOS求得，避免回改已提交DNG。
- mixed mode仍為CFR；VFR音訊保留原時間進度，host依同一origin同步，不能刪去drop期間的音訊。
- first/last、max_gap屬policy目標；storage持續停滯時可能無法同時滿足。此時stop並記incomplete，
  不可為了「保證最後一幀」覆寫in-flight slot或無界保存latest frame。
- 先做deterministic cadence/hysteresis，後加motion／gyro／AE/AF權重；cheap decision在pixel copy前完成。

## 9. Pool大小與壅塞預算

`Lhold = t_buffer_released - t_slot_acquired`，包含編碼、排隊、提交及下游讀取時間。
若採固定間隔來源且另留一個burst margin，可用下式作初始容量規劃：

```text
Nout_plan = ceil(f_keep_peak * Lhold_design) + 1
Mtotal = Nout*Sout + Nin*Sin + Nticket*256 + Njournal*64
         + journal batch pool + request contexts + completion/control
         + worker stacks + allocator overhead
```

這不是安全釋放規則；真正回收仍靠completion token。`Lhold_design`由replay/stall容忍目標決定，
觀察到的p99/max不是永遠不超過的硬界。VFR的平均keep率也不是peak admission rate；需token
bucket/cadence限制burst或按來源24fps預留。

24fps設計例（尚非量測）：

| Lhold_design | Nout（含1個margin） | 4 MiB實驗slabs | 16 MiB條件式slabs |
|---:|---:|---:|---:|
| 50 ms | 3 | 12 MiB | 48 MiB |
| 100 ms | 4 | 16 MiB | 64 MiB |
| 250 ms | 7 | 28 MiB | 112 MiB |
| 700 ms | 18 | 72 MiB | 288 MiB |

上述不含原廠recorder自身記憶體，也不代表allocator可配置成功。2-slot適合最小ownership試验，
預期可以很快滿；4-slot是有限burst候選；8-slot也只在實测hold/backlog支持時採用。

啟動時先取得所有必要slabs、queue、completion cells與control reserve，再arm。配置不足時在
REC之前選擇另一個已驗證profile或維持OFF；錄影中不可臨時借用原廠ring／其他專案arena。

雙重水位：同時監控free slots與queued bytes/time。單看frame數無法區分4張RAW與4張小lossless。
初始可用 `free<=1` 為high pressure、`free>=ceil(N/2)` 為恢復條件，持續幾幀後才退出壓力模式；
具體threshold需trace replay調整。永遠保留unbounded stall時的有限stop/drop語意。

## 10. Metadata、cache與共享資源

### 10.1 每幀header必須来自每幀

現行G4以reference DNG預建整個新root IFD，再每幀只更新tile arrays。即使旧header被逐幀複製，
新root裡的inline value或pointer仍可能来自reference。任何多幀 fixed run 前就必須改為：

- template只保存layout skeleton／tag patch plan。
- 每幀從live root複製所有非layout entries與引用關係，再替換layout tags。
- 保護並驗證TimeCodes、RawDataUniqueID、Exposure/ISO等會變的值；不只比較保留的旧header bytes。
- 格式metadata與frame ticket的source identity可交叉驗證，才能抓到G5這類「可解碼卻是別幀」。

現有 fixtures 的 TimeCodes、RawDataUniqueID 是 out-of-line 值且 offset 恰好相同，複製 live
舊 header 可保留它們；本審阅沒有證明目前這些值已凍結。缺口是 inline value 改變或 referenced
offset 改變時仍使用 reference entry，需用這兩類 synthetic fixtures 明確驗收。

### 10.2 Alias與cache

G4a支持同一allocator契約下的CPU `0x8`視窗寫入 + `dsb`，由`0x4`handle交writer。這是
目前首选data path；不需因先前筆記寫過clean就每幀做全cache清除。

但cached `0xC` alias不得同時dirty同一physical slot；跨alias重用要先消除已知dirty副本。
新arena/SSD/backend仍需驗證。code publication維持D-cache後I-cache的獨立流程；payload
可見性成功不會取消新RAM code的cache要求。alias轉換由已驗證allocator contract執行，不作任意OR。

### 10.3 共享codec

一個codec worker／engine owner，並與stock still path排他。codec IRQ completion與storage
completion各自清自己的hold，不得混用。未知結果將slot移至QUARANTINED；固定pool少一格可觸發
stop，但不可把quarantine當FREE繼續錄。

## 11. Stop、取消與reset

1. 原子 `RUNNING -> CLOSING` 關閉 ingress gate；等待已持有入口 ref 的 producer publish 或
   rollback，再 freeze `final_source_seq`。先寫 watermark 再等 producer 會留下競態與漏幀。
2. 所有 `source_seq <= watermark` 必須有 terminal record 或唯一 DROP_SPAN coverage。
   已接受但未提交者取消也要標 CANCEL/INCOMPLETE；只有未對外 admission 者可純 rollback。
3. ordered drain codec/storage；所有 kept DNG request 必須 terminal-success，output release
   則另等。任一 I/O error 即使 buffer 已 release，也不能將 clip 標成功。
4. 排出全部有序 journal batches；依實際結果產生 CLEAN_FOOTER 或 ABORT/ERROR_FOOTER。
5. dedicated control lane + wake flag（或 data 不可占用的 queue 保留格）送出帶 watermark 的
   EOS。不能只預留 descriptor 卻讓 mailbox 已滿。codec/storage/journal 各 worker 在處理完
   watermark 前所有工作後才 ACK，由 coordinator 收齊；control lane 不得超車後提早退出。
6. 按已驗證 firmware 順序 close/flush/join；durability barrier 成功才標 clean。
   callback sources unregister/drained、所有 reader/code holds=0，才可 free pool／卸載 hook。

所有等待都有研究時明訂的 deadline。逾時走 `ABORT_INCOMPLETE`，保留／quarantine 所有
MAYBE_TAKEN buffers、request contexts、completion cells 與 callback code；不能無界 join。
只有證明 backend abort/reset 且硬體 quiescent 才可收回；否則保留至安全 reboot，不偽裝 clean close。

STOP按鍵返回、codec成功、`frames_done==N`、host讀完status或檔案出現都不是storage release。
`release_retained_scratch()`目前只檢查codec狀態；在mirror/compress類phase還需要storage
quiescence證明，否則可free仍被讀取的記憶體。設計上的release API應要求completion token／
backend drain證據，不能用固定sleep取代。

暖重開只有在真正硬體／allocator epoch重建且無舊DMA後才可丟棄舊句柄；user-space flags reset
不能中止硬體。allocator pointer非零不代表仍有效，舊callback也不能操作新epoch。

## 12. 找到 release fence 的最小研究路徑

### B0：離線instrumentation contract

新增trace事件：`SOURCE_OBSERVED`, `ENCODE_DONE`, `SEGMENT_REGISTERED`, `FLUSH_ENTER`,
`FLUSH_RETURN`, `DOWNSTREAM_READ/COPY_ENTER`, `DOWNSTREAM_COMPLETE`, `SOURCE_RELEASE`,
`REC_STOP`, `BACKEND_DRAIN`。每筆包含64-bit展開tick、source_seq、slot token、request id、
實際buffer pointer、length、result與task/context id。

register/flush兩個已知掛點先關聯同一frame；後續沿queue/backend找到「不再讀該pointer」的事件。
只追加多幀flush timing仍不足以找到release。若backend拿到descriptor copy，要保存其request id
與slot token映射；不能事後讀stack pointer猜關係。

靜態追蹤起點：`out/decomp/full/blk_c03.c` 的 `0xC03A5490` call 與
`out/decomp/full/blk_c06.c` 的 `FUN_c069ac88`（複製 pointer/length 到 node）、
`FUN_c069ade0`（形成 scatter list 後呼叫 media）。`FUN_c063f380/FUN_c063f140` 有
callback/token 候選路徑，但目前 C03A call 的 param2=0，尚未證明能拿到逐幀 callback。
這些只作靜態研究候選，不是可直接接線的 release API。
下一個離線 trace 包解析 SD vtable、內部 `+0x483c` reader/copy method、`FUN_c063f140`
的 callers/close/drain，以及 callback 設定鏈 `FUN_c063b908 -> FUN_c063f220`；建立
scatter `{pairs,count,cookie}` ABI 與 0x80-cookie FIFO 的 lifetime。callback 能 inline 或排隊，
只有證明其晚於最後可能讀取，才能升級為 release fence。node/descriptor 本身也須納入 token
追蹤；只有 N 份 payload 並不能保證 N 個註冊內容仍各自獨立。

### B1：有界不重用驗證

先以每個來源一個獨立output slot跑K幀，K由已核准可配置容量決定。第K+1幀停止admission，
所有K個slots保留，不用modulo輪轉；等已證明的drain／quiescence後才回收。這可以隔離G5的
「同地址共用」問題，但本身仍不是長跑或release fence證明。

記錄當幀payload與header digest，讀回每張DNG驗證source對映與tile邊界；decode success只是
其中一項。若要同幀pixel equality，需保留對應stock source／sample hash，不能拿鄰幀代替。

### B2：Completion-linked reuse

以兩個slots驗證：submit不釋放；completion先後不同、早於submit return、重复／舊generation
事件都正確；有reader的slot永遠不可寫。小pool满時要可觀測stop，不能出現重複影像。

### B3：容量與延遲收斂

scene matrix、不同卡、card stalls、連續clips與溫度測試，量`Lhold`分布、in-flight峰值、queued
bytes與backlog slope；才選N與標示可支持的profile。無completion時保持不能重用的判定。

### B4：動態策略

先離線trace replay mixed/true-drop；再接合法skip hook、journal、exact timebase與audio。
從first frame開始所有模式使用相同ticket／generation／metrics，未來啟用policy不用改pool ABI。

## 13. 必要驗收情境

| 情境 | 必須成立 |
|---|---|
| 連續N+1個submit，無completion | 只接受N個slot；第N+1個依profile拒絕或drop；既有bytes不變 |
| submit返回成功但DMA未讀完 | 不回池、不覆寫 |
| completion在submit返回前發生 | caller hold阻止過早reuse |
| inline release後submit結果ambiguous | 不倒退狀態；quarantine而非直接FREE |
| buffer先release、稍後request失敗 | payload可已安全reuse，但clip仍ERROR；context保留 |
| 舊generation／重複completion | 拒絕／記錄；不釋放新frame |
| callback只有重用pointer、沒有request identity | gate拒絕reuse，不自行猜generation |
| RAW ready先於前一COMP | 不越序；RAW source仍被保留 |
| output pool已滿但允許VFR | DROP只耗小型timeline record，不分配image slot |
| journal高水位且SD停滯 | 使用reserve/span或stop；不能無記錄drop與無界排隊 |
| STOP時queue滿 | control reserve可發出stop；in-flight slots仍保留 |
| close同時有producer進入口 | 等ingress refs歸零再freeze watermark；coverage無洞 |
| journal batch submit後consumer繼續 | 未release的immutable batch不被覆寫 |
| drain逾時／late callback | quarantine資料與callback code，不free/unhook |
| sidecar只寫到一半斷電 | CRC有效prefix可復原；tail明確incomplete |
| header inline metadata每幀變動 | 新root与原始當幀metadata一致，非reference frame值 |
| encoded size剛好C與C+1 | 前者可容納，後者拒絕；header/table不重疊 |
| 新geometry／bit depth | 沒有新capacity proof就拒絕 |

本次驗證為離線source/evidence審閱、整數容量核算與文件連結檢查；不將上述尚待實作情境
計為已通過tests。過往153項tests是當日實作日誌記錄，不能替代本ownership contract的驗收。

## 14. 下一個最小工作包（收斂後）

1. 查明逐幀 pointer/length 與最後讀者的關係，找出 G5 重複原因；不先猜要幾個 buffer。
2. 修正現有容量檢查與當幀 metadata；在已確認安全容量內做少量獨立、不重用 slot 的驗證。
3. 釋放時機證明成立後，才加簡單的空閒 slot 選取與重用；驗證不重複、不越界、可停止。

暫不做通用 layout generator、獨立 ticket/journal pools、async codec worker、完整 VFR framework。
壓縮前預判另作小型離線實驗，不阻擋修復基本錄影。後續有量測需求再增加結構。

## 15. 壓縮前收益預判

可在 KEEP 決策前增加小型 RAW residual 抽樣，不需要完整 input copy；DROP 已由 cadence/壓力
確定時連抽樣也略過。預測只選 policy，不降低 output capacity。完整簡易三區判斷、sample
budget 的早期推導見 [`COMPRESSION_PRECHECK.md`](COMPRESSION_PRECHECK.md)；當前只採該文件
§1 的「一個分數、一個門檻」最小方案，不先實作完整三區模型。
