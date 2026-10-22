# fpLossless 固定無損、非同步管線與動態降載研究路徑

## 現行入口 — 2026-10-04

Lossless 已出貨。現行進度與下一步以 [PROGRESS_20261004.md](PROGRESS_20261004.md) 為準；[10/03](PROGRESS_20261003.md) 留有發布與選單／合併整合歷史。下方「development-only／僅 FHD／無選單／無整合 BIN」是舊快照，不再描述已出貨產品。

本輪保持雙 lane、單 codec 與原生 writer，完成 HELD 取消／codec FAILED 隔離／REC ABI 最小修正，加上固定 1,068-byte 的原生 error／FIFO discard／writer 返回診斷。普通、debug、Fast 三個 r2 候選離線通過；尚無本輪實機結果，不能宣稱網友的 SD 停錄缺幀已解決。

後續先通知使用者並遵守 build 規範做啟停及 ON/OFF 對照，找出異常清 FIFO 的觸發原因。有壓力證據才考慮提前請求正常 stop、讓原生非同步排空。暫不搬壓縮到 writer、不擴 RAW buffer、不跳過原廠 cleanup、不加複雜預測器。

## 2026-09-30 入口快照（以下保留歷史）

入口更新：2026-09-30；下方 §0–15 為 9/27 研究快照，保留當時證據與提案。  
適用機種／韌體：SIGMA fp `w71c1`, Ver.5.02.0.V91  
產品狀態：`development-only`, `camera_ready=false`  
首輪產品目標（非全部 geometry 已驗收）：FHD 1936×1090、RAW12、24000/1001、SD、predictor 1、512×368 tiles

**當前進度、阻擋項及執行順序以 [PROGRESS_20260930.md](PROGRESS_20260930.md) 為準。**
本頁保留研究路線／歷史 gates，不再把 9/27 的「下一個 patch」當現行指令。

9/29 同步版已有可解碼寫卡證據；舊非同步探針的跨幀覆寫不符合需求，driver arm 已停用。
9/30 新增單一待壓幀 policy 的主機／ARM 離線實作，沒有原生 hold／defer／handoff adapter；
舊同步寫卡與獨立 async 實驗不能合併成現行整合版通過。未準備好直接上機。

**範圍收斂（使用者：不要過度設計）：** 單一工作槽，忙時 RAW 通過、空閒接下一個到來的幀，
有效但不更小的輸出交回原幀 RAW；沒有丟幀／VFR 或新增預測器。
下文 §5–11 的完整多池／VFR 與複雜預測器仍是參考，不因已有 async 探針就整套實作。
近期順序見 PROGRESS §12：**直接啟用壓縮＋現行 USB shell＋Fast Start 2；選單暫緩，不含 OG／gyro**。
已新增獨立的無選單 REC 入口，只省 UI proof，不能省來源持有、codec 靜止或寫檔證明。
上機前通知使用者，build 遵守專案規範；尚無可上機的整合 BIN。

新增開發約束見 PROGRESS §13：每次 REC 在 CDNG map 就緒後、原生錄影開始配置來源前，先預留
RAW/class 10 的單一工作區；整段重用，排空後釋放。16 MiB 只限先前 USER 測試，不作全機上限。
§14 已實作 RAW 配置器、格式容量算法與 REC adapter，完成主機整合／RAW descriptor ARM 測試
及 ARM object 建置；不是只留設計。真正 REC hook、producer facts／來源餘裕 provider 與
停止／取消接線仍未安裝，codec 寫界亦未證明；不是已驗證的錄影餘裕。先走正式 RAW 預留，
分帶方案暫不優先。

- [`IMPLEMENTATION.md`](IMPLEMENTATION.md) 保留逐日實作歷史；其中較早的「目前狀態」不覆蓋本文。
- [`BUFFER_DESIGN.md`](BUFFER_DESIGN.md) 首節連到現行記憶體／生命週期門檻，其後保留舊同步基線與 slots 備案；
  先前完整多池／動態框架留在 [`BUFFER_RESEARCH.md`](BUFFER_RESEARCH.md) 備查。
- [`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md) 記錄可借用的原生緩存機制，
  訂正 9/24 舊 writer-chain 的 vtable 位移與 movie cookie；優先驗證既有完成回呼及批次進度。
- [`COMPRESSION_PRECHECK.md`](COMPRESSION_PRECHECK.md) 已有 host 原型與反例，尚無可用門檻；
  不是容量 proof，也不授權 zero-copy 或 fixed mode 靜默改 RAW。
- 通用 codec／格式研究仍在
  [`INCAMERA_LOSSLESS.md`](../../../research/slimRAW/notes/INCAMERA_LOSSLESS.md) 與
  [`HW_LOSSLESS_JPEG_CODEC.md`](../../../research/imaging-hw/notes/HW_LOSSLESS_JPEG_CODEC.md)。
- 不可變實機證據在 [`../build/`](../build/)；工具與 host trials 在 [`../tools/`](../tools/)。
- 建立本文件時只做離線讀取、稽核與測試；沒有連線、操作相機、改卡、部署或發布產物。

## 0. 證據標記與閱讀規則

本文使用下列標記：

- **[L] Live**：真機或真實相機檔案的量測結果。
- **[H] Host**：主機工具、fixture、decoder 或單元測試結果。
- **[C] Code**：現行 source、反編或 ABI 的直接事實。
- **[I] Inference**：由現有證據推導，但尚未由目標路徑直接驗證。
- **[P] Proposal**：設計方向或待實驗假說。

證據優先順序：

1. 最新、不可變的 live evidence，加上能重建它的 binary/source hash。
2. 現行 source 與其離線測試。
3. 本文件的 current verdict。
4. 研究筆記中的成本模型與歷史發現。
5. 逐日實作日誌與舊 README；它們只代表當時狀態。

任何「passed」必須同時說清楚：通過哪個層級、在哪個環境、證明什麼、沒有證明什麼。

## 1. 執行摘要與開發定案

### 1.1 目前真正成立的事

1. **[L] 正式 512×368、predictor 1 已在 movie writer context 編碼。**
   G2 室內 fixture：13,652 µs、1,386,496 B；G5 八次 encode 為 13,640–13,657 µs。
   這是 encode call 時間，不是 end-to-end 錄影餘裕。見
   [`ledger-g2`](../build/ledger-g2-20260923.json)。
2. **[L/H] 相機產生的位元流已對同來源 sample bit-exact。**
   retained payload 經 host 封裝解碼，2,110,240 個 samples 的 SHA-256 與來源相同。
   見 [`camera-bitstream ledger`](../build/ledger-camera-bitstream-20260923.json)。
3. **[L/H] 自有 arena 已寫出單幀 compressed DNG。**
   G4a 鏡像水印證實重導向與該 SD path 的 uncached CPU writes 可見；G4b 寫出
   1,396,736 B DNG，79,872 B header + payload，單 node、12 tiles、可解碼。
   G4b 鄰幀比較不是同幀 bit-exact；不是整個 G4 gate 完成。見
   [`G4a`](../build/ledger-g4a-mirror-20260923.json)、
   [`G4b`](../build/ledger-g4b-compressed-20260923.json)。
4. **[C/H] clip-level fail-closed control core 已存在。**
   精確 eligibility、七項 readiness、錄影中禁止切換、sticky fault、不做片中靜默 RAW
   fallback；離線 32 tests 通過。見
   [`control.h`](../../../fpSup/lossless/control.h) 與
   [`control.c`](../../../fpSup/lossless/control.c)。
5. **[L] G3 writer submit/accept 已量到返回，但不是已證明的 buffer-release fence。**
   此 seam 的歷史名稱為 final-flush，下文沿用地址／工具名時不代表 durability。
   `0xC03A5490 -> FUN_c069ade0` 處理 3,244,544 B 的一次 call 為 372 µs；不能解釋為
   同量資料已完成實體 SD 傳輸。見 [`G3`](../build/ledger-g3-20260923.json)。
6. **[L] G5 完整性 FAIL：目前 arena／註冊路徑未保存逐幀 identity。**
   八次 encode 的來源 buffers 不同；讀回 frame 1、2、4、8 卻 byte-identical。
   需要 output ownership／最後讀者 fence，不能只增加固定 sleep 或猜 ring 深度。
   見 [`G5`](../build/ledger-g5-sustained-20260923.json)。
   第四次 encode 預期長度與讀回 frame 4 亦不一致；node/descriptor lifetime 或人工對應
   仍需查證，不能宣稱 payload 是唯一原因。
7. **[C] 原生 CinemaDNG 已有逐幀完成回呼，還不是自有 arena 的已驗證 release fence。**
   movie scatter cookie 是 frame pointer；正確 dispatch 為 `C03686C0 -> C063B898 ->
   C063F380`，經 `C063F140` 完成批次後呼叫 `C03A55D0(frame,status)`。
   SD aggregation 保留 range descriptors，不是整幀副本；約 64 MiB 批次門檻與少量 slots
   是否相容尚待驗證，不能只接 callback 就開始長跑。此為自有 output 方案的備案研究；
   copy-back 不把 scratch 交給 SD，不需先完成自有 slot callback 才能前進。
8. **[L/H] 9/26 C2 單幀 copy-back 成立。** 原生 `seg[0]` 不變，只改長度為 1,476,608 B；
   落卡可解碼。encode 13,753 µs 不含 copy；鄰幀比較不是同幀 bit-exact。見
   [`C2`](../build/ledger-c2-copyback-20260926.json)。

### 1.2 尚未成立的事

- 每幀獨立且可回收的 output lifetime、連續寫卡完整性與 stop/drain。
- output buffer 的硬體最壞容量上界；4 MiB 仍是受限實驗配置。
- 每幀 live metadata 保留；reference IFD template 不能直接當作不變 metadata。
- 動態場景、高 ISO、高熵、長時間與熱穩定。
- stock CinemaDngPlay 對 tiled `Compression=7` 的回放。
- source ring 的 lease/release，以及非同步 writer descriptor ownership。
- mixed `Compression=1/7` 的 NLE／相機相容矩陣。
- true frame dropping 的時間軸、sidecar、音訊同步與匯出工具。

### 1.3 產品順序

正式方向定為：

1. **固定全幀 FHD23.976 lossless，先做 export-only。**
2. 完成 end-to-end 寫卡與長跑後，再測 FHD29.97。
3. **先延伸 C2 copy-back，補足容量、copy 時間與逐幀完整性。** 只有恢復 writer 指向自有
   output 的方案，才需要自有 slot release fence；C3 八幀仍是有界驗證，不是長跑。
4. pipeline 穩定後才研究 adaptive mixed compression。
5. sidecar、host conform 與音訊契約完成後，才研究 true VFR dropping。
6. motion/scene-aware policy 最後加入，不作第一版 scheduler。

UI、持久化與卡片包裝排在 recording core 之後。`ON` 在所有必要 readiness 未成立前維持不可用。

## 2. 目前證據帳與必要訂正

### 2.1 精確數字

| 項目 | 數值 | 證據邊界 |
|---|---:|---|
| FHD active pixels | 2,110,240 | 1936×1090 |
| packed RAW12 pixel bytes | 3,165,360 (`0x304CB0`) | 不含 header 與 12-byte 非像素尾端 |
| stock DNG segment bytes | 3,244,544 (`0x318200`) | 整個單一 writer segment |
| stock pixel offset/header | 78,848 (`0x13400`) | 154×512 |
| safe expanded header | 79,872 | 156×512，較 stock 增加 1,024 bytes |
| 9/21 舊 tile encode | 18,138–18,229 µs | 512×512 的歷史 burst；不是 current geometry |
| 9/23 G2 encode | 13,652 µs / 1,386,496 B | 512×368、室內 fixture，僅 encode |
| 9/23 G5 encode | 13,640–13,657 µs | 八次 encode 成功，但輸出重複，完整性 FAIL |
| G3 flush call | 372 µs | 一次 call return，非已證明的 RAM release 或 durability |
| G4a whole-DNG copy | 44,896 µs | 已超過 23.976 frame budget |
| 23.976 frame budget | 41,708 µs | 完整一幀的 deadline |
| current/product tile | 512×368 / 12 tiles | 已有 live、camera bitstream 與寫卡證據 |

### 2.2 已修正項目與目前 P0

#### P0-1：tile height wiring

[`single_frame_encode_discard_probe.S`](../../../fpSup/raw/lossless_codec/single_frame_encode_discard_probe.S)
原先 height 寫入 `TILE_W` 的問題已修正；9/23 live 與讀回 DNG 證實 512×368、12 tiles。
保留 width/height 獨立斷言與 probe hash。最後一 tile 的 count 含 EOI 後零 padding，
總 payload 512-byte 對齊；不可把合法尾 padding 誤判為沒有 EOI，或任意裁去。

#### P0-2：`source_dng_byte_identical` 過度宣稱

source marker probe 只比較 TIFF 第一個 word、首 pixel word、末 pixel word與 segment length。
正確措辭是 **sampled source markers unchanged**，不是 full-buffer byte-identical。
相機 payload 的同來源 sample equality 是獨立證據，不可回填成每次 source 全檔 hash。

完整證明至少需要：

- encode 前後對整個 3,244,544-byte source 做同一演算法的 hash／CRC；或
- 在 source ownership 允許下完整讀回，在 host 比對 hash；
- 同時記錄 buffer identity，避免前後其實讀到不同 ring slot。

#### P0-3：output capacity 是事後偵測，不是事前保護

目前已改為 4 MiB arena、`WORK_CAP=0x3F0000`、`OUT_OFF=0x13800`，compressed payload
實際容量為 4,048,896 B。舊的 848-byte margin 已非現況，但安全問題尚未完成：

- 9/24 現行模型已改為整數 14 bits/sample，512×368 為 3,957,888 B；仍未含 entropy
  `FF 00` stuffing，marker overhead 亦是模型假設，不是 hardware bound。
- **容量入口已修正 [C]**：所有 codec kinds 共用 `require_safe_arena(kind=kind)`，runtime sum
  比較 `WORK_CAP - OUT_OFF`。本次核對現行 source，未重跑 IMPLEMENTATION 所列測試。
- 事後 canary／size 檢查不能防止先发生的 DMA overrun。
- 9/26–27 定位的 engine 宣告長度 `0x305000`（3,166,208 B）是否由硬體強制仍未知。
  encode 拒絕或小輸出未觸界都不是 bound proof；舊「高熵已衝破 guard」是離線風險描述，
  沒有該越界的 live 證據。PHASE 9 及帳差詳見 CURRENT_DEVELOPMENT §2–3。
- [`BUFFER_DESIGN.md §4`](BUFFER_DESIGN.md#4-output-slot-的具體版面) 定義現行 layout 與容量缺口；
  條件式 16 MiB 推導在 BUFFER_RESEARCH §4，不代表該配置已可部署。

#### P0-4：output release fence 與 frame identity

G5 已證明單區重用會產生可解碼的重複影像。每個 accepted frame 的 output 必須保持 immutable，
直到同 token 的最後讀者 release；submit return、REC stop、`frames_done` 都不足以證明可回收。
9/24 已定位原生 `C03A55D0` 候選；先驗證其最後讀者語意與 batch 進度。保留原 frame cookie，
不可改塞 slot index；原生 stop/drain 已定位，但正常錄影低水位自動 flush 尚未證明。

### 2.3 其他必須固定的措辭

- 18.146–18.229 ms 是 **encode call latency**，不是 header + writer + SD 的端到端時間。
- 8 frames 應稱 **encode burst**，不能稱 sustained recording。
- 8 個 buffer 與 5 種首 pixel 值只證明不是同一 frame 被重編，不能證明完整內容差異。
- 2.574:1、2.555:1 是特定低變化場景，不是壓縮率下限或容量上界。
- guard intact、hook restored、block freed、camera responsive 只描述成功路徑。
- host pixel equality 不代表 MakerNote/檔案 byte-for-byte 不變；TIFF layout 本來就會改變。
- G4b 已證明 variable-length payload 寫卡，但不等於 sustained 或 stock playback 成立。

## 3. 產品範圍與 profile 語意

### 3.1 第一版固定邊界

- CinemaDNG、1936×1090、RAW12、24000/1001、SD。
- predictor 1、標準 512×368 tiles。
- 每個來源 frame 都壓縮、都輸出；CFR。
- 不修改 sensor mode、crop、hbin/vbin、RWZM 或 OpenGate。
- 不與 8-bit route 疊加。硬體 codec 接受 10/12/14/16-bit，沒有 8-bit code。
- 幾何縮減發生在 codec 之前；compressed Huffman stream 不能再做 hbin/vbin/RWZM。

### 3.2 建議 profile 分層 [P]

現行 `FPL_RAW/FPL_LOSSLESS/FPL_STOP` 保持 fixed-lossless 的嚴格語意。未來不要把動態行為偷塞進
`FPL_LOSSLESS`；應新增明確 profile：

- `FIXED_LOSSLESS_EXPORT`：每幀 `Compression=7`，host/export contract。
- `FIXED_LOSSLESS_PLAYBACK`：額外要求 stock 或替代 player readiness。
- `ADAPTIVE_MIXED_EXPORT`：每幀保留，但允許 `Compression=1/7`。
- `VFR_DROP_EXPORT`：允許真正不輸出來源 frame，sidecar 為格式契約的一部分。

現有 `FPL_READY_ALL` 包含 playback。若 MVP 採 export-only，不可假裝 playback bit 已成立；應引入
profile-specific required mask 或新的 export readiness，否則就繼續拒絕 `ON`。

## 4. Stock path 與固定 lossless 參考架構

### 4.1 已知資料路徑

```text
Sensor
  -> CRCT reductions / RWZM
  -> packed RAW12 CinemaDNG buffer in DRAM
  -> FUN_c069ac88 registers one writer segment
  -> FileSplitWriter list
  -> 0xC03A5490 calls FUN_c069ade0 final flush
  -> SD
```

final-flush 的 `r0` 由 stack-local writer descriptor 形成。因此它很適合同步 wrapper，卻不能把
writer pointer 丟給 async worker 後立即返回。非同步版本必須深拷 descriptor，或改在有持久
frame object 與已證明 lease 的更早掛點。

### 4.2 當前基線：同步 encode → copy-back → 原生 writer

- G3 final-flush 是已驗證的觀測 seam；G4 實際在 segment-register seam 重導向 pointer/length。
- 維持当幀 call context 內 encode 與 header snapshot，不先導入來源 async queue。
- 寫卡採已成功的單 node、contiguous header+payload；在 scratch 組好後，確定完整檔案
  不超過原 `seg[1]` 才複製回原生 DNG 區域，只改 `seg[1]`，不改 `seg[0]`。
- **撤回「flush 同步等待最後讀者、一個 scratch 足夠」假設。** G3/G5 不支持此 ownership。
- scratch 不交給下游；codec/header/copy 完成後才能重用，連續重用尚未 live-proven。
  自有 output pool 降為備案；若恢復 pointer redirect，仍須滿足 release fence 與 batch gate。

### 4.3 精確 writer gate

wrapper 必須在任何變更前拒絕所有非預期形狀：

- firmware/build、CINE、RAW12、FHD、24000/1001、SD profile 全部吻合。
- writer count 為 1，head 是 writer arena 內精確 node，16-byte aligned。
- `next==NULL`、`kind==2`、buffer 非空、length `0x318200`。
- TIFF magic、dimensions、bit depth、`Compression=1`、`StripOffsets=78848` 全吻合。
- source、header、scratch、table range 合法且互不重疊。
- codec lock、engine idle、output capacity、guard 與 cache path 已 ready。

任何不符在第一次 commit 前直接 pass-through stock writer 或拒絕 REC，依 clip state 決定；不可半改。

### 4.4 Canonical compressed DNG layout

舊的「在 zero-run 放新 IFD」已被推翻：MakerNote 宣告範圍涵蓋舊工具選中的零區。完整保護
root/nested IFD 與 out-of-line values 後，原 header 只剩 92 bytes 合法空間，但新 IFD 與兩個
tile arrays 需要 810 bytes。

已實測的機身 layout：

```text
single segment: owned contiguous output arena
  0 .. 78,847       copy of original header, except root pointer committed last
  78,848 .. 79,657  new IFD + TileOffsets + TileByteCounts (810 bytes)
  79,658 .. 79,871  zero padding

  79,872 ..        codec payload, exact declared length
  outside submitted range: guarded work tables / control tail
```

新 root IFD：

- 從當幀 live header 保留所有非 layout root entries；template 僅作 patch plan，不能凍結 inline values。
- 移除 `StripOffsets/RowsPerStrip/StripByteCounts`。
- 設 `Compression=7`。
- 新增 `TileWidth/TileLength/TileOffsets/TileByteCounts`。
- 所有 offsets/counts 在 bounds、overflow、overlap 驗證後才寫入。
- 完整寫好 IFD/tables，按已驗證 alias 做 visibility/barrier，最後才更新 TIFF offset 4 的 root pointer。

只提交 header+declared payload。保留相機已回報的合法尾端零 padding，不任意另加資料。
兩個 segment 的零拷貝 header/payload 仍是替代 proposal，不是 G4 live-proven layout。

### 4.5 自有 output slot 備案的 fixed frame sequence（非目前 C2 路徑）

```text
1. validate clip profile and exact writer shape
2. reserve ticket/output slot/control credits; acquire codec ownership; verify idle
3. validate source/header/scratch/table ranges and guards
4. run init -> encode -> size query with per-stage ownership bits
5. validate every tile size, sum, output bound and guard
6. build owned 79,872-byte expanded header
7. publish header/tables for DMA; commit root pointer last
8. register one owned header+payload node; publish submission token and caller hold
9. submit through original writer; preserve original return semantics
10. end caller hold; do not interpret return as buffer-release
11. release each resource only at its own proven last-reader fence
12. publish per-frame telemetry; advance clip state
```

產品版應安裝一次 stable wrapper，由 runtime state 決定 pass-through／lossless；不要像量測 probe 一樣
每幀 self-unhook/re-arm，減少 stale-I-cache 與 fetch-window 風險。

## 5. Ownership、cache 與 engine lifecycle

### 5.1 需要被明確擁有的資源

- vendor source DNG buffer，以及它的 lease 或 owned input copy。
- codec output slot 與精確 capacity。
- expanded-header slot。
- size tables、guards 與 codec stage state。
- writer descriptor copy／segment nodes。
- queue descriptor。
- timeline/journal record。

每項資源都要有唯一 owner、最後讀者與恰好一次 release；不能用「地址仍非零」當有效 ownership。

### 5.2 Source ring 不是免費 queue

觀察到的多幀 ring 屬於原廠 recorder。未找到 retain/release primitive 前，async worker 不能假設
上游不會重用 buffer。兩個合法選項：

1. 找到並證明 source frame lease/release。
2. 在同步掛點立即複製完整 3,244,544-byte DNG 至自有 input slot，保留 metadata 與未來 RAW bypass。

G4a 的完整 uncached copy 實測 44.896 ms，超過單幀預算；不能把 copy 當作已可持續的預設。
先保留同步 encode，再找 lease 或量測另一個經驗證的快速 copy path。

### 5.3 Cache/DMA 規則

- `DSB` 不是 D-cache clean。
- 新 RAM code／hook 必須先完整寫入並 readback，再依維護路徑做 D-cache publication 與 I-cache
  invalidation，最後才 arm hook。
- G4a 證明該 allocator/SD path 的 `0x8` uncached CPU writes + `dsb` 可見；可沿用此契約。
- 若改用 cached alias，仍需適當 clean；不得同時留下同一 physical slot 的 dirty cached copy。
- 若 codec output 使用 uncached/DMA alias，必須由現行 allocator/ABI 證明，不能猜 alias。
- 避免每幀全 cache clean；使用已驗證的 uncached buffer 或 bounded targeted maintenance。

### 5.4 Codec engine arbitration

0x300D 是單一 global engine，韌體沒有可直接重用的 mutex。產品需要：

- atomic try-lock 與 owner generation。
- 每次 kick 前 engine-idle check。
- still/movie 排他策略；本地 lock 本身不會阻止 stock still path。
- resource bitmap：LOCKED、POWERED、CLOCKED、ENCODING、COMPLETE、UNWINDING、QUARANTINED。
- reverse-order stage-aware unwind。
- codec 已進入而結果不明時保留 scratch，sticky-disable，必要時要求 power cycle；不可 free/retry。

### 5.5 Warm restart

每次 loader/boot 都先使舊 epoch 失效並清除所有 runtime pointers、queue、busy/completion、cached
header plan 與 ownership token。所有 allocation 重新取得、重新驗證；hook 永遠最後安裝。這不是清除
固定程式碼，而是避免把上一個 allocator epoch 的地址誤認為仍有效。

## 6. 非同步 codec/storage pipeline [P]

### 6.1 啟用前置條件

此處的 async 指 **codec/source worker 非同步化**；output lease/pool 是 G5 之前就要完成的工作。
只有下列條件全部成立後才讓 codec 延後讀來源：

- 同步 encode + completion-linked output pool 的 fixed FHD 已通過完整性與長跑。
- source lease 或 copy path 已證明。
- writer descriptor 可深拷／重建，沒有 stack lifetime。
- output/header slots 的 allocator 餘裕與 alignment 已量測。
- stop/drain/error ownership 可由離線 state-machine tests 覆蓋。

### 6.2 元件邊界

```text
capture_adapter -> identity/time + small journal reservation -> early policy
  -> DROP: journal record/span; no image allocation/copy/encode
  -> KEEP: all-or-none resource reservation -> bounded input/lease queue
  -> codec worker
  -> header builder
  -> ordered ready queue
  -> storage worker
  -> completion/release
  -> binary journal
```

`fpl_control` 繼續只管 clip lifecycle；per-frame scheduler、queue 與 DMA ownership 放在獨立模組。

### 6.3 Frame job sketch

```c
struct fpl_slot_ref { uint32_t pool, slot, generation, boot_epoch; };
struct fpl_frame_job { /* proposal, not a frozen binary ABI */
    uint32_t magic, abi, clip_epoch, state;
    uint64_t source_seq, output_seq;
    uint64_t writer_tick_us, nominal_pts;
    uint32_t duration_units, action, reason, flags;
    struct fpl_slot_ref source_lease, input, output;
    uint32_t source_bytes, output_capacity, encoded_bytes, header_bytes;
    uint32_t submit_id, hold_bits, journal_credits, completion_cell;
    uint16_t tile_w, tile_h, tile_count, predictor;
    uint32_t encode_us, header_us, flush_us;
    uint16_t codec_q_depth, storage_q_depth;
    uint32_t codec_result, writer_result, record_crc;
};
```

header 第一版是 output child region，同 generation 與 fence。裸指標只在 adapter 驗證 handle 後解析。
`writer_tick_us` 目前只能稱 writer-ready 時間；尚未證明等於 exposure timestamp。精確 PTS 使用
`fps_num/fps_den` 的 rational timebase，23.976p 以 timescale 24000、duration 1001 表示，避免長片逐幀
微秒四捨五入漂移。

### 6.4 State machines

Clip：

```text
OFF/IDLE -> PREFLIGHT -> ARMED -> RUNNING -> DRAINING -> IDLE
                  any uncertain ownership -> STOP_ERROR / QUARANTINED
```

Per frame：

```text
FREE -> CAPTURED -> CLASSIFIED
  |-> RAW_READY                                      [adaptive profile only]
  |-> CODEC_QUEUED -> ENCODING -> CODED -> HEADER_READY
  `-> DROP_RECORDED_IN_RAM                           [VFR profile only]
KEEP -> READY_ORDERED -> SUBMITTING
  submit/release/request-result 分成正交狀態；holds 清零且 release/reject contract 成立才 FREE
DROP -> journal-owned record/span -> release small ticket/source
```

Invariants：

- `source_seq` 唯一且單調，warm restart 的舊 epoch 永遠無效。
- 後幀不得越過尚未決定的前幀；用 commit cursor reorder。
- `DROP` 必須移交 journal record/span ownership 才能推進 cursor；不等每幀 durable flush。
- `SUBMIT_ACCEPTED`、`BUFFER_RELEASED` 與 `DURABLE` 不可混用。
- `REQUEST_COMPLETE(result)` 另追蹤寫入終態；payload 先 release 後仍可能 I/O 失敗。
- completion 可早於 submit return；caller hold 未清前不可回池。generation/epoch 防止晚到事件誤釋放。
- 已開始 codec 的 frame 不得再改判 RAW/DROP。
- 已開始 flush 的 frame 不得 retry 成另一份非冪等輸出。
- 每個 slot 的 source/output/header/descriptor 恰好釋放一次。

### 6.5 Queue 與 worker lifecycle

使用 fixed descriptor pool；pool empty 就是 queue full/backpressure，並保留 guard、high-water 與 failed
allocation counters。可沿用 gyro 的
[`mpool.inc.S`](../../../fpSup/gyro/mpool.inc.S) 與
[`writer_core.inc.S`](../../../fpSup/gyro/writer_core.inc.S) 生命週期：

- resident worker 使用 firmware thread pool，而非忙輪詢。
- `XT_CREATE 0xC036E108` -> `XT_ATTACH 0xC036E1B8`。
- body object 必須傳「保存 vtable pointer 的 word 的地址」，不是該 word 的內容。
- STOP/EOS 使用獨立保留 token／control lane，以 final source watermark 排在已接受資料之後；
  不能依賴可能耗盡的普通 data pool。
- drain -> `XT_JOIN 0xC036E1F8` -> delete mailbox -> `XT_DESTROY 0xC036E168` -> close。

2 slots 僅作最小 ownership 實驗，不是 production 最低足夠數。以 acquisition→release 的 hold
time、peak keep rate、burst margin 與 allocator 餘裕規劃 N；詳見 `BUFFER_DESIGN.md §6`。

### 6.6 Pipeline timing

CPU call cost（不等於完整 frame lifetime）：

```text
Tcall = Tinit + Tencode + Tsize + Theader + Tsubmit_call + Toverhead
Lhold = t_buffer_released - t_slot_acquired
```

只有 backend service/overlap 實測後才可近似 pipeline 穩態：

```text
Tsteady ~= max(Tcodec_stage, Tstorage_stage)
```

短 ring 能吸收 burst 不代表長期穩定；真正判定看 queue backlog slope、high-water 與 drain completion。

## 7. 「動態抽幀」必須拆成兩個獨立 profile

### 7.1 Adaptive mixed compression：不丟 frame

語意：每個 source frame 都輸出一個 DNG；codec 有餘裕時寫 `Compression=7`，否則寫原始
`Compression=1`。時間軸仍為 CFR，所以它不是 frame dropping。

限制：

- `RAW_PASS` 必須是明示 profile decision，只能在 codec enter 前決定，不是錯誤 fallback。
- mixed sequence 必須另做 LibRaw、Resolve、Adobe、目標 NLE 與 stock camera matrix。
- 它只降低平均 byte rate；RAW frames 的瞬間峰值仍存在，慢卡不一定因此穩定。
- 跳過 codec 不一定更快，因 RAW write 較大。policy 必須比較 action 的完整 service cost。
- codec result ambiguous、guard 壞或 DMA ownership 不明時，一律 stop，不可 RAW_PASS。

比較模型：

```text
Tcompressed = Tencode + Theader + compressed_bytes / storage_rate
Traw        = raw_dng_bytes / storage_rate
```

policy 必須先聲明目標是省容量、守 deadline，還是降低 peak；三者不是同一問題。
可加壓縮前低成本抽樣：每 tile 的同 component residual/category histogram，粗估完整檔案
大小並分為值得／不值得／不確定。見 [`COMPRESSION_PRECHECK.md`](COMPRESSION_PRECHECK.md)。
預判不能取代 output bound、source ownership 或 mixed compatibility gate。

### 7.2 True frame dropping / VFR：真的不輸出 frame

語意：部分 `source_seq` 沒有 DNG。固定 fps CinemaDNG 序列沒有 gap/duration 語意：

- 把輸出重新連號會讓缺掉的時間消失、動作加速。
- 保留檔號缺口的 reader/player 行為未定，不能當協定。
- 寫一份完整重複 DNG 可保 cadence，但失去主要 I/O 收益。

因此 VFR profile 必須是 export-only 或有理解 sidecar 的 player/importer；不得對使用者宣稱是普通
固定 fps CinemaDNG。

### 7.3 第一版 VFR scheduler

先做 deterministic，不先做內容分析：

- Bresenham/deficit accumulator 維持目標平均輸出率。
- `max_gap`、first/last 是 policy 目標；無界 storage stall 時不能保證，應停止並標示 incomplete。
- 每個 observed source_seq 由一個 record 或無重疊 DROP_SPAN 恰好覆蓋。
- queue 壓力策略預先定義 newest-wins 或 oldest-pending；不能覆蓋已進 codec／已 commit frame。
- 曝光、AF 或 scene discontinuity 保留規則須有可測的輸入，否則不假裝 motion-aware。

只有 deterministic scheduler、timeline reconstruction、power-cut recovery 與 audio drift 都通過後，才加
thumbnail/SAD、gyro、AE/AF 或 scene-cut 權重。

### 7.4 Binary sidecar/journal

相機 hot path 使用固定大小 binary append records + CRC，不直接寫 JSON。建議 header：

```text
magic, version, record_size, clip_epoch, firmware,
width, height, bits, fps_num, fps_den, profile, flags, header_crc
```

每個來源 frame 的 record：

```text
source_seq, output_seq, writer_tick_us64, pts, duration,
action(KEEP_COMP/KEEP_RAW/DROP), reason,
raw_bytes, output_bytes, encode_us, flush_us,
codec_q_depth, storage_q_depth, timecode_digest,
error_stage, record_crc
```

要求：

- DNG filename 保持連續；sidecar 映射 output -> source/PTS，不用檔名 gap 表示時間。
- dropped source frame 也有 record。
- small decision ring、immutable append blocks、EOS/ERROR reserve 分別計數；DROP 不取 image slot。
- 在 RAM 記錄後批次 append，不在每次 DROP 同步寫同一張壅塞 SD；durable CRC prefix 與
  尚在 RAM 的 tail 清楚區分。append blocks 也要等 storage release 才可重用。
- 32-bit 1 MHz tick 展開為 64-bit，處理 wrap；仍標記為 writer-ready time。
- record-level CRC，截斷尾端可忽略；clip footer 保存 aggregate 與 clean-close 狀態。
- sidecar failure 立即停止 VFR profile，不能繼續產生不可還原時間軸。
- host 工具負責轉 JSON/CSV、重建 VFR，或依明示策略 conform 成 CFR 並處理音訊。

## 8. Admission control 與 backpressure

每個 action 的預估完成時間：

```text
finish(action) = now
               + queue_wait_p99
               + action_cost_p99
               + storage_backlog_time
               + safety_margin
```

- p99/max 用於規劃與 circuit breaker，不當作未來永不超過的硬上界；ownership 不依時間猜測。
- EWMA 只追蹤趨勢，不能取代 worst-case gate。
- 使用 high/low watermarks 與 hysteresis，避免逐幀在 RAW/lossless/drop 間抖動。
- fixed lossless：無法保證期限就 stop/error，不能偷改 RAW。
- adaptive mix：codec enter 前，RAW source ownership 合法且不能超越較早 COMP，才可 `RAW_PASS`。
- VFR：只有 sidecar/timeline contract 可推進時才可 `DROP`。
- queue 永遠有界；不覆蓋最舊未完成 slot，不保存 stack-local writer pointer。

## 9. Failure policy matrix

| Failure phase | Fixed lossless | Adaptive mixed | VFR drop |
|---|---|---|---|
| REC preflight/readiness 不足 | 拒絕 REC | 拒絕 REC | 拒絕 REC |
| writer shape/source/header 不符，尚未寫 compressed frame | 整段鎖定 RAW 或拒絕 REC；不可半改 | RAW_PASS 僅限 policy 合法且 source 未改 | DROP 需 timeline policy；否則停止 |
| codec busy，尚未 enter | 停止／報錯 | 可預先 RAW_PASS | 可依 policy KEEP_RAW/DROP |
| init clean failure、可證明 engine idle | clip 首幀前可整段 RAW；之後停止 | circuit-break 至 RAW 需 mixed matrix 已通過 | 依 policy，但保留錯誤 record |
| encode 已 enter、timeout／結果不明 | 停止、保留 scratch、sticky-disable | 同左，不可 RAW_PASS | 同左，不可 DROP 已進 codec frame |
| output bound／guard 失敗 | 停止、quarantine | 停止、quarantine | 停止、quarantine |
| header commit 前失敗 | 首幀前可整段 RAW；已有 compressed frame 則停止 | 可 RAW_PASS 只限 source 未改、engine clean | 可 DROP 只限 journal 合法 |
| header commit 後、flush 前失敗 | rollback 只限可證明尚未寫且首幀；否則停止 | 不可盲目補 RAW | 不可盲目改 DROP |
| flush 已開始／部分寫入／回錯 | 停止、保留原錯誤；不可 retry RAW | 同左 | 同左 |
| queue overflow | stop/error | hysteresis/circuit breaker；不得無界成長 | journaled drop 或 stop |
| sidecar failure | telemetry 可失效但 fixed clip 規則需明定 | 若 sidecar 只是診斷可報錯；不可冒充完整記錄 | 必須停止 |
| warm restart／epoch mismatch | 使全部舊 ownership 失效；重新配置後才可 arm | 同左 | 同左 |

「首幀前可整段 RAW」表示 clip contract 尚未產生 compressed output；不是片中 silent fallback。

## 10. 效能判定

### 10.1 目前可用的 budget

| Mode | Frame budget | 現有 codec 證據 | 判定 |
|---|---:|---:|---|
| FHD 23.976 | 41.708 ms | G5 512×368 `F_ENC` max 13.657 ms | 首目標；完整性 FAIL，尚缺 lifetime/service 分布 |
| FHD 29.97 | 33.367 ms | 同上，非該 mode 實測 | 23.976 通過後再測，不以相減餘裕宣稱支援 |
| OG3K 23.976 | 41.708 ms | 舊模型約 34.33 ms codec | 暫緩；舊串行 SD 模型需以新 backend trace 重審 |
| UHD 23.976 | 41.708 ms | 舊模型約 44.91 ms codec | codec 本身超 budget，暫不做產品目標 |

FHD23.976 的 13.657 ms 尚非高熵/高 ISO/熱穩態最壞時間。G3 的 0.372 ms call 不能當作
SD service time，也不能直接加進舊模型後宣布 throughput 支援；需量出真正 backend completion。

### 10.2 Go/no-go 看哪些數字

- `init/encode/size/header/submit_call/buffer_hold/backend_service` 的 max、p50、p95、p99。
- output bytes/ratio 的 min/max 與高 ISO／高熵 tail。
- queue high-water、failed allocation、backlog slope、drain time。
- frame requested/finished/gap/duplicate，source -> output mapping。
- guard、source full hash、engine stage、cleanup 與 hook restoration。
- card latency、空間、溫度與連續 clip／warm restart。

平均吞吐只作描述；安全 gate 以 worst observed、p99、容量 bound 與「backlog 是否淨成長」決定。

## 11. 研究 gates

9/23 狀態：G1 部分（容量 proof 未成立）；G2 部分（少量 live fixtures）；G3 部分（一次
submit call）；G4 部分（單幀寫卡與獨立 codec bit-exact）；G5 完整性 FAIL。G7 的 **output
ownership 子集前移為 G5 前置**，不可等 sustained 通過後才處理。當前最小驗證見 BUFFER_DESIGN §8；
較完整 B0–B4 留在 BUFFER_RESEARCH 備查。

### G0 — Canonical baseline與證據衛生

工作：

- 本文件成為 current source；舊 README／日誌標示歷史狀態。
- 建立 machine-readable evidence ledger。
- 每次 run 記錄 firmware、source commit、dirty state、probe binary hash、tile/predictor、arena、media、
  scene、完整 state dump hash。

通過：每份證據都可由 source + binary hash 重建，且清楚列出「已證明／未證明」。

### G1 — Probe safety 修正

工作：

- 修 tile-H wiring 與對應 tests。
- 將 fixed-address/zero-survey probe 遷移到現行 dynamic cave claim／ownership。
- code/data readback；D-cache publication 後 I-cache invalidation；hook 最後 arm。
- 建立 output worst-case bound，隔離 output/table/guards。
- source full hash/readback。

通過：無未宣告固定 scratch/code ownership；安裝／卸載 byte-for-byte restoration；高熵測試不可能先越界。

### G2 — 正式 512×368 live encode-discard

場景：暗場、一般自然場景、正確曝光高 ISO、高頻細節、快速 motion/scene cut；高熵合成資料先 host。

量測：init、encode、size、wrapper total、tile sizes、total bytes、ratio、full source hash、guards、cleanup。

通過：所有 fixture 以 512×368/predictor 1 成功；tile sum 與 total 相符；零 guard／source mismatch；
engine 回 idle；output bound 有正 margin。

### G3 — Read-only writer submit/accept（歷史工具名 exact final-flush）

量測多張 frame 與多張 SD card的 writer shape、flush p50/p95/p99/max、64-bit return、requested/finished、
backlog與溫度。此 gate 仍不改 DNG。

通過：精確 shape 穩定；requested==finished；無 backlog 成長、漏完成、雙重完成或 hook residue。

### G4 — Host artifact 與單幀寫卡

先讓 host artifact 與預定相機 writer 的 79,872-byte header + payload 逐 byte 對應，再做：

1. 單 frame 新 clip。
2. 極短 fixed-lossless clip。
3. codec/header/flush/cleanup 各 stage fault injection。

通過：每張 DNG 可解析、2,110,240 samples 全相等、metadata 除批准 layout fields 外不變、命名／timecode
正確；任何錯誤 fail closed，無 source overwrite 或同 take silent RAW fallback。

### G5 — Fixed FHD23.976 sustained

前置：先證明 buffer release、獨立 slots、每幀 metadata 與 identity。先做 K-slot 不重用有界
實驗，再做 completion-linked reuse。不能直接重跑舊單 arena sustained probe。

第一階段利用 4096-frame ceiling，約 171 秒；之後做 10 s、60 s 與長時間 thermal/media runs，
包含動態場景與正確曝光高 ISO。

通過：零 gap/duplicate、requested==finished、所有 queue 最終歸零、guard/source/metadata 全正確、
backlog 無淨成長、stop/drain/連續 clips/warm restart 正常。未通過前不得稱 sustained recording supported。

### G6 — Export/playback contract與相容矩陣

- MVP 預設選 export-only；UI/metadata 明確不承諾機內 playback。
- 測第一幀很小、後續幀很大的 capacity case。
- fixed compressed DNG：LibRaw、Resolve、Adobe與目標 reader matrix。
- 另外研究 stock player patch、proxy 或 sidecar-aware player；不與 writer gate 混為一談。

### G7 — Async ownership與 FHD pipeline

工作：source lease/copy、owned slots、codec/storage workers、ordered commit、stop marker、drain與 fault injection。

通過：two-slot lifecycle 實驗後，按 latency/memory 設定正式容量；所有 transition acquire/release
恰好一次；無 reorder/use-after-release；長跑 backlog
穩定；同步 baseline 的影像／metadata結果完全一致。之後才測 FHD29.97，再評估 OG3K18/23.976。

### G8 — Adaptive mixed compression

前置：mixed NLE/player matrix、variable capacity、profile-specific readiness、clean codec skip path。

通過：每個 source frame 均有輸出與 record；CFR timing 不變；RAW/COMP 決策可重播；queue bounded；
不能在 ambiguous codec/error 後偷轉 RAW。

### G9 — True VFR dropping

前置：sidecar schema frozen、host importer/conformer、audio sync、power-cut recovery、export-only contract。

通過：每個 source frame 有可驗證 decision；PTS/duration 單調；max-gap 有界；截斷 journal 可復原；
長片音訊 drift 在既定規格內；使用者不會把輸出誤認為普通 CFR CinemaDNG。

### G10 — Motion-aware policy、UI與包裝

比較 deterministic scheduler 與 motion-aware 的效益／CPU／DRAM overhead；只有實質收益才保留。
最後才接 native row、持久設定、installer/card-composer 與 release gates，預設仍為 OFF。

## 12. 離線驗證與實機實驗矩陣

### 12.1 2026-09-23 早期離線 baseline（歷史記錄）

```text
fpSup/raw/lossless_codec:
  test_single_frame_codec_probe.py
  test_exact_flush_writer_probe.py
  test_exact_dng_writer_probe.py
  55/55 passed

fpSup/lossless:
  python3 -B -m unittest discover -s tests -v
  32/32 passed
```

這 87 tests 證明 host builder、control logic 與 assembly/source invariants；不是 ARM execution、camera writer、
storage、playback或 sustained 證據。
稍後 IMPLEMENTATION 記錄 153 tests；本次緩衝區設計審阅沒有重跑該 suite，亦未實作新 pool。

### 12.2 必須新增的離線 tests

- tile width/height 獨立 wiring 與 edge-tile property tests。
- worst-case encoder patterns、output expansion 與 capacity rejection。
- recursive TIFF graph／MakerNote guard、offset/count overflow、metadata preservation。
- slot state machine property tests：單調 seq、bounded queue、exactly-once release、warm epoch、stop/drain。
- scheduler trace replay：現有 8-frame timing、slow-card burst、codec contention、queue saturation。
- 32-bit tick wrap、rational PTS、max-gap、deterministic decision replay。
- sidecar CRC、truncation、power-cut、schema version與 parser fuzz。
- mixed sequence與 VFR conform 的 host reader matrix。

### 12.3 實機階段順序

任何實機步驟都需另行明確授權，且每次只增加一個變因：

1. 先通過 CURRENT_DEVELOPMENT §3 雙區 ownership／失敗判定離線門檻，再另行核准 bound 實驗。
2. C2 已有單幀證據；補量 post-encode/copy 與完整檔案驗證，不拿 G3 當容量證明。
3. 容量／時間／原生 frame 條件確認後，才實作與核准 C3 八幀，核對逐幀身分及 batch 進度。
4. 如改回自有 slots，再做 callback／batch／N sizing；不是 copy-back 的共同前置。
5. 1 s -> 10 s -> 60 s -> 4096 frames -> thermal fixed run。
6. source lease 或可負擔 copy proof。
7. async codec/input workers。
8. mixed sequence。
9. VFR sidecar。
10. motion-aware。

每階段預先寫清楚 entry conditions、arm/abort、expected evidence、cleanup、恢復與不得重試的 uncertain outcome。

## 13. Evidence ledger schema [P]

建議每個 immutable evidence artifact 至少包含：

```text
kind, date, operator_scope
camera model, firmware, media/backend
source commit, worktree_dirty, source paths
probe binary sha256, build command/toolchain
hook site/original/installed/restored words
code/data cave lease and bounds
profile, geometry, bit depth, fps, tile, predictor
scene/ISO/exposure description
frames requested/entered/finished/written
per-stage timing distribution and max
per-frame bytes/ratio/queue depth mapping
source hash, output hash, guards, engine/cleanup state
explicitly_established[]
explicitly_not_established[]
```

早期 `source_dng_byte_identical` 曾過度宣稱；現有資料已加入 sampled-marker 訂正，讀取時必須
檢查 correction／established 邊界。後續保存原始 capture、另建帶 provenance 的 ledger；本次不改 evidence。

## 14. Open questions register

| ID | 問題 | 風險 | 下一個最小實驗 |
|---|---|---|---|
| OQ-01 | lossless JPEG worst-case output bound | 越界破壞 table/記憶體 | host 合成 pattern + ABI 上界推導，之後才 bounded live |
| OQ-02 | 512×368 scene/thermal tails | 基本 live 已有、分布未全 | 正確曝光高 ISO/動態場景矩陣 |
| OQ-03 | storage 最後讀者與 hold distribution | 單 arena 產生重複幀 | 關聯 register/submit/backend release，不只量 flush call |
| OQ-04 | source buffer lease | async use-after-reuse | 找 producer/release primitive或量 owned copy |
| OQ-05 | writer descriptor lifetime | async stack pointer失效 | 更早 persistent hook或完整深拷 proof |
| OQ-06 | still/movie codec arbitration | 單引擎碰撞可 freeze | 證明 CINE REC 排他或 gate still path |
| OQ-07 | 每幀 live header/metadata | reference IFD inline fields 可陳舊 | 變動 metadata fixtures 與 live root patch plan |
| OQ-08 | stock playback | 合法 DNG 不代表能播 | export-only decision + independent player probe |
| OQ-09 | player first-selected-frame capacity | 寫卡成功不能排除 playback assert | small-first/large-later 的獨立播放驗證 |
| OQ-10 | high ISO/time/ratio tails | buffer/card budget未知 | 正確曝光 ISO scene matrix |
| OQ-11 | exposure-aligned frame ID | VFR timing語意不足 | 對照 TimeCodes/sensor counter/writer tick |
| OQ-12 | SSD completion semantics | 任一 SD alias/release 契約不可外推 | SSD-specific observer，另立 gate |

## 15. 已拒絕或暫緩的設計

- 把 OpenGate／sensor geometry 修改混進 lossless 第一版。
- 8-bit companded data 再送 0x300D lossless codec。
- 在 MakerNote 的 zero-run 偷放 IFD。
- 用尚未證明的 4 MiB／optimal-Huffman estimate 直接測未知高熵輸出。
- 以 submit return、固定 sleep、REC stop 或 modulo ring 代替 release fence。
- 把 vendor ring 當自有 async queue。
- 保存 final-flush stack-local writer pointer。
- codec ambiguous 後 free、retry 或 silent RAW fallback。
- 用檔名缺口或重新連號暗示 VFR。
- 在 stock DNG 內做 partial-frame raw/lossless 混合；單一 IFD 無合法表示法。
- 用 8-frame burst 宣稱 sustained。
- 用 mean latency 取代 p99/max/backlog gate。
- writer/playback 未完成前先發布 UI `ON`。

## 16. 近期最小工作包

以 [PROGRESS §7–9](PROGRESS_20260930.md) 為唯一當前清單：先閉合跨幀來源持有、
來源／檔案／metadata 對應、尾端完整性與 release 判定，再交接有界 FHD 儀器測試。
新 build 依 [SUP_BUILD_RULES.md](../../../fpSup/SUP_BUILD_RULES.md)，新上機先通知並取得授權。
6K 分帶及合併配置留後；不加通用 pool、UI ON、SSD 或動態抽幀框架。
探針的 RAW pass-through／前幀寫後幀不默認改掉 fixed-lossless 產品契約。

## 17. 來源地圖

- Product control/UI：[`../../../fpSup/lossless/`](../../../fpSup/lossless/)
- Buffer/lifetime contract：[`BUFFER_DESIGN.md`](BUFFER_DESIGN.md)
- Native cache/completion donors：[`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md)
- Codec/writer probes：[`../../../fpSup/raw/lossless_codec/`](../../../fpSup/raw/lossless_codec/)
- One-shot live evidence：[`../build/live-encode-20260921.json`](../build/live-encode-20260921.json)
- 8-frame burst evidence：[`../build/sustained-encode-20260921.json`](../build/sustained-encode-20260921.json)
- Safe host builder：[`../tools/mkcompressed_safe.py`](../tools/mkcompressed_safe.py)
- TIFF guard：[`../tools/tiff_guard.py`](../tools/tiff_guard.py)
- Codec/format research：[`../../../research/slimRAW/notes/INCAMERA_LOSSLESS.md`](../../../research/slimRAW/notes/INCAMERA_LOSSLESS.md)
- Cost/status snapshot：[`../../../research/imaging-hw/notes/LOSSLESS_DEVELOPMENT_SUMMARY.md`](../../../research/imaging-hw/notes/LOSSLESS_DEVELOPMENT_SUMMARY.md)
- Dynamic mixed concept：[`../../../research/imaging-hw/notes/ADAPTIVE_FRAME_COMPRESSION.md`](../../../research/imaging-hw/notes/ADAPTIVE_FRAME_COMPRESSION.md)
- Queue/thread reference：[`../../../fpSup/gyro/mpool.inc.S`](../../../fpSup/gyro/mpool.inc.S),
  [`../../../fpSup/gyro/writer_core.inc.S`](../../../fpSup/gyro/writer_core.inc.S)
