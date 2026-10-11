# fpLossless implementation — 2026-09-27

> **文件角色：歷史實作日誌。** 本檔按日期保留當時的實作狀態與措辭，內文較早結論可能已被
> 後續實機證據推翻。唯一 current status、架構、研究順序與 pass/fail gates 請讀
> [`PROGRESS_20260930.md`](PROGRESS_20260930.md)。特別是「scratch/encode 尚未上機」、「live 與 host 是同 tile
> geometry」、「source DNG byte-identical」、「2.3× 是端到端錄影餘裕」與「8 frames 已是
> sustained」都不可再當成目前結論。

Independent product `fpLossless`; future test package name
`fpsup-lossless-v0.1.0test`. It is not part of OG2K or OG3K. Only the existing
fp-Merge/card-composer generates combined cards. No release or merged artifact
was generated in this work.

Requested UI: SHOOT second page (CINE), alongside DC crop, recording settings
and audio recording. Add an OFF/ON row; do not repurpose any factory setting.
Default OFF. Persistent storage is not implemented yet.

Source: `fpSup/lossless`. Reusable codec/UI research stays in `research`.
This project directory holds integration notes, build/test evidence and captures.

## 9/30 文件收尾

當前入口統一至 [PROGRESS_20260930.md](PROGRESS_20260930.md)。同步可解碼寫卡與獨立 async
證據分開；補記現行來源／檔案身分、跨批次來源壽命、尾端與 release 等未驗門檻，保留原始 ledger。
建置遵守 [SUP_BUILD_RULES.md](../../../fpSup/SUP_BUILD_RULES.md)，上機前先通知並取得該輪授權。
本次未改 runtime、未建置或重跑 codec 測試、未連相機／寫卡／發布；沒有新產物或 live pass。
下方 9/27 工作順序保留歷史，不覆蓋最新入口。

## 當前開發指引對齊 — 2026-09-27（文件與離線核對）

新增 [`CURRENT_DEVELOPMENT.md`](CURRENT_DEVELOPMENT.md)，同步 ROADMAP、BUFFER_DESIGN、
LIVE_TEST_PACKAGE 與預判／原生緩存筆記。這段優先於下方較早的「下一步」：

- C1/C2 已於 9/26 留下實機紀錄：單幀 copy-back 成為基線，不先建 output pool。
  C2 的 13,753 µs 僅 encode；現行 source 的 `t_after` 尚無相機結果，不回填成已量 copy。
- PHASE 9 product geometry＋原生來源成功，但未觸界；同時換 geometry／來源不能隔離拒絕原因。
  9/27 ledger 的 tile sum=790,656 B、總長=790,528 B，差 128 B；未找到原始 dump，保留 evidence gap。
- `bound-probe-two` 已有 source，但第二區 provenance／回收與兩次 scratch 的 gate 尚未閉環。
  下一個 patch 只補這個離線工作包與 encode/size 失敗測試，不直接上機或做 zero-copy。
- 硬體宣告 length 不等於强制上限；即使會停寫，也不能解決 in-place 讀寫追撞、512 B
  allocation 外間隙與超限後 RAW 不可恢復。預測器的 -91.72% 反例更不能當安全 gate。
- 本輪 `test_single_frame_codec_probe` 94 項 OK；`test_codec_emulation` 第一項程序 exit 132，
  無 Python traceback，未完成、原因未定位，不列通過或 skip。保留 9/25 當時測試記錄，不混為同一輪。

未修改 runtime 或原始 ledger；未操作相機、改卡、部署、commit 或發布。
依 fp-usb-shell 的 buffer ownership／不明結果保留原則，雙區實驗仍須完成前置及另行授權。

## 模擬器:PHASE 7 真的跑起來,立刻抓到兩個缺陷 — 2026-09-25（離線）

證據：[`ledger-copyback-emulation-20260925.json`](../build/ledger-copyback-emulation-20260925.json)。
依 `fp-unicorn-emulation` skill 建的框架：
[`emulate_codec_probe.py`](../../../fpSup/raw/lossless_codec/emulate_codec_probe.py)、
測試 [`test_codec_emulation.py`](../../../fpSup/raw/lossless_codec/test_codec_emulation.py)。

**為什麼需要它：** PHASE 7 之前的每一個測試都在斷言**原始碼文字**。那能抓到被刪掉的行，
抓不到「組得起來、讀起來合理、但把錯的位元組複製到錯的地方」。copy-back 寫進的是
**相機自己的幀緩衝**，「listing 看起來對」不夠格帶去相機。

### 框架做了什麼

- 韌體映像**可寫**地映射在 `0xC0000000`，所以探針能就地還原自己的 hook 字組。
- arena(`0x45000000`)和 writer buffer(`0x53B00000`)**各映射兩次** ——
  handle 與 handle+`0x40000000`，用 `mem_map_ptr` 指向**同一塊**主機記憶體。
  這就是相機三個 DRAM alias 的行為；若用兩塊獨立區域，複製會「看起來成功」
  而其實寫到沒人讀的地方。
- 種下 host 會種的一切：`S_ALLOCATOR`、`S_HANDLE`、兩個 proof magic、
  scratch 階段留的三個 guard 字、1 KiB IFD template 與它的兩個表位移。
- buffer 裡放**真實的** stock header，所以 header copy 與 template patch
  操作的是真的相機 metadata。
- stub `F_INIT`/`F_ENC`/`F_SIZE`/`F_CLOCK` 與原始的 `FUN_c069ac88`；
  **其他任何韌體位址一律 raise** —— 未 mock 的呼叫要大聲失敗，
  不能讓映像裡的真碼跑起來回傳垃圾。

### 抓到的第一個缺陷:每次成功的 copy-back 都回報 ERR_SOURCE

`finish_source` 把 `buffer[PIXEL_OFF]` 和記錄的 BEFORE 值比較。
而 copy-back **刻意**把 `0x13400..0x13800` 換成新的 IFD 與 tile 表 ——
所以那個比較**永遠**失敗。

**若照原樣上機：** `release` 會拒絕釋放一個其實正常的區塊；更糟的是，
在「改動來源正是意圖」的那個 phase 上掛一個「來源被破壞」的錯誤，
**會掩蓋真正的錯誤**。

修法：PHASE 7 仍記錄 AFTER 值，但跳過判定，並把理由寫在旁邊——
BEFORE 值在 encode **之前**取、encode 在複製**之前**結束，
所以順序本身已經保證 codec 讀到的是未被破壞的來源。
取代它的是對落卡檔案跑 `verify_compressed_dng`，那是強得多的陳述。

### 抓到的第二個缺陷:`S_STAGE` 分不出「已複製」和「跳過」

`complete:` 在離開前無條件把 `S_STAGE` 設成 8，所以 stage 11/12 **從來不會到 host**。
我原本有個測試在斷言那兩個值——斷言的是讀者永遠看不到的東西。

修法：**`S_FIT` 才是判決欄位**（沒有別的東西寫它）；11/12 註明為
「只在 `complete` 之前發生故障時才倖存」的進度標記。

### 模擬器確立了什麼 [H]

- 放得下的幀被複製，**只有 `seg[1]` 改變**。原始函式被呼叫時 `seg[0]` 仍指向
  相機的 buffer(`0x53B00000`)，**從不是我們的 arena**。
- **落在 buffer 裡的位元組是合法的壓縮 CinemaDNG** ——
  `verify_compressed_dng.check` 通過，包含長度規則與原始 header
  第 8..78,848 bytes 的逐 byte 存活。**這是將來要對著卡片跑的同一個檢查器。**
- 複製範圍之外的位元組逐 byte 還是原幀：複製寫的是 `file_bytes`，不是整塊。
- **放不下的幀什麼都不碰**：buffer 事後逐 byte 相同、`seg[1]` 仍是 stock 長度、
  writer 拿到的也是 stock 長度。拒絕不是錯誤。
- 邊界正好是被交付的長度：剛好 `seg[1]` 長的檔案被接受，多一個複製單位就被拒絕。
- 兩條路都沒有 `F_ALLOC`/`F_GET`/`F_FREE`；hook 自我還原；堆疊回到原位。
- 錯的 ordering kind 以 `ERR_KIND` 拒絕且不碰幀。
- `compress` 仍然把**我們的 arena** 交給 writer，而 copy-back 留下相機的 buffer ——
  整個設計賴以成立的那個區別。

### 突變檢查,含一個誠實的缺口

| 突變 | 失敗數 |
|---|---:|
| 拿掉准入檢查 | 3 |
| 設了 `seg[1]` 但從不複製 | 1 |
| 跳過路徑照樣發布新長度 | 1 |
| **改走 cached alias 而非 uncached** | **0** |

最後一項是**缺口,而且模擬器修不了**：兩個 alias 映射到同一塊主機記憶體，
所以模擬器分不出來——aliasing 是硬體性質。
改由原始碼層的 `test_copyback_uses_the_uncached_alias_on_both_sides` 釘住，
那個測試對同一突變**確實會紅**。已驗證。

### 一個要更正的先前回報

9/24 我把 `verify_compressed_dng` 的 9 個與 `canonical_header` 的 13 個測試
**報告為通過。實際上 22 個全部跳過。**

原因：stock DNG fixture 在 repo 重組時從 `codex/evidence/...` 搬到
`projects/open-gate/captures/...`，而測試用 `skipTest` 處理缺檔，
`unittest` 就報 `OK (skipped=22)`——我只看了 `OK`。

是模擬器發現的：它需要同一個 fixture，而它**大聲地** `FileNotFoundError`，
測試一直在把同一件事吞掉。四個檔案的路徑已修，51 個 tools 測試現在**零跳過**。

**教訓：`OK` 不等於跑過。往後看測試結果要一併確認跳過數。**

### 模擬器不能告訴我的（不得當成已證明）

- 真實 codec 的行為。`F_ENC` 是寫入框架化填充資料的 Python stub，
  所以這證明的是**管線對了**，不是相機的位元流對了。
- 時間。clock 是固定遞增的 stub。
- writer 的 buffer 在相機上是否真的有 `+0x40000000` 的 alias。
  模擬器是靠建構假設它成立的；只有相機能否證它。
- 有沒有別人握著那塊 buffer。那是 C1 普查，仍然是任何 live copy-back 之前的閘門。

## 收斂:SD 錄影關不掉聚合,所以答案指回 copy-back — 2026-09-24（本日結論）

使用者指出 **Media Write Mode 是 SSD 的設定**。這一句把整天的追查定位了，並且和
韌體對得上：

```
settings + 0x98   ← Media Select        （SetMediaSelect）
settings + 0x9C   ← Media Write Mode    （SetMediaWriteMode）
```

兩者相鄰，而 `FUN_c0444698` 正是讀 `settings + 0x98` 決定媒體類型（回傳 1 或 5）。
所以這確實是「媒體／外接」那一組設定。

### 已量到的事實

**錄到 SD 卡時,批次聚合是開的,而且改不掉。** 選單值試過 1 → 0 → 2 → 1，
`settings+0x9C` 始終是 1，`manager+0x0D` 始終是 1，flush 始終是 ~365 µs
（372 / 365 / 356 / 368 四次）。

若這個項目在 SD 模式下是停用的，它的值就被釘住，`MenuItemMediaWriteMode::v3`
永遠算出 1 —— 那解釋得通，並且代表 **SD 錄影沒有關掉聚合的選項**。

因此
[`ledger-aggregation-off-path-20260924.json`](../build/ledger-aggregation-off-path-20260924.json)
的「單一 arena 就夠」那條路，**對 SD 錄影是死的**。不再追。

### 但這反過來指回 copy-back

批次關不掉 → 我們的 buffer 必須活過一整批。算術在
[`ledger-sd-aggregation-static`](../build/ledger-sd-aggregation-static-20260924.json)：

| | 每批幀數 | 需要的記憶體 |
|---|---:|---:|
| 自有 slot 陣列（壓縮幀，每格 4 MiB） | ~48 | **~196 MiB** — 拿不到 |
| **相機自己的 frame ring** | 28 格 × `0x31A400` | **87 MiB** — 已經存在 |

**相機的 ring 就是為了撐過一批才存在的**（28 格 vs stock 每批 20.7 幀，餘裕約 7 幀）。
這不是巧合，是同一個政策下的兩個數字。

所以結論反過來：**既然批次關不掉,就必須待在相機自己的緩衝紀律裡,
而唯一為此尺寸設計的池子就是相機自己的。** 也就是 copy-back —— 把壓好的檔案複製回
writer 交給我們的那個 `buf`，只改 `seg[1]`，不持有任何 buffer。

### copy-back 的容量障礙有解,而且不是猜的

先前把 copy-back 擋下來的硬條件是：最壞情況壓縮檔 4,037,760 B 大於 `buf` 的
3,244,544 B（[`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md) §4 第 3 點）。

但那有解：**壓不進去就不壓,那一幀照原樣寫 RAW。**

關鍵是這個判斷**不需要預測**。順序是：encode 完成 → 尺寸表已知 → 才決定要不要改
`seg[1]`。也就是說容量判斷發生在**確定知道**的時候，不是
[`COMPRESSION_PRECHECK.md`](COMPRESSION_PRECHECK.md) 講的事前抽樣估計。
這正是 ROADMAP 已經規劃的 adaptive mixed，只是觸發條件從「值不值得」換成「放不放得下」。

代價是那一幀白編一次（13.6 ms），但不影響正確性。

### 仍然未解決的（copy-back 的其餘四點）

[`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md) §4 列的其他四點都還在：

1. tapseg 的 28 格與 `0x31A400` spacing 是從位址範圍推的，不是量到的；
   在 descriptor 的 base/capacity 確認前，複製長度上限最多只能取原本的 `seg[1]`。
2. 74 幀 mark-only 只在 padding 寫了一個 word，不證明整段 RAW 被覆寫後沒有其他讀者。
   `C0374BF0` 的 owner/clone 機制證明**存在**共享引用。
3. G4a 是**反方向** mirror（讀 `buf` 寫 arena），用它的 72.3 MB/s 估 copy-back 只是
   成本假說。24p 一般內容約 79% 預算，29.97p 貼邊，60p 不行。
4. 那些 buffer 是 allocator class 10（RAW）—— 寫進去已驗證，但不可去動它的配置。

### 一個開放的產品決定

**SSD 錄影下 Media Write Mode 應該是有效的**，那可能意味著 SSD 路徑上批次可以關掉、
單一 buffer 就夠，路徑乾淨很多。而 SSD 本來也是高位元率錄影比較合理的目標。

所以需要先定：**產品目標是 SD、SSD,還是兩者。**

- 只要 SD → 直接往 copy-back +「壓不下就寫 RAW」設計
- SSD 也要 → 值得花一次上機確認「接 SSD 時 Media Write Mode 可不可改、改了 flush 會不會變長」

### 過程上的檢討

追「關掉批次」花了一整輪上機。使用者一句「那個是 SSD 的設定」就把它定位了。
**如果我早點問「這個選單項目在機身上長什麼樣」,會省掉那一輪。**
韌體能告訴我這個 byte 從哪裡來，但告訴不了我它在使用者眼中是什麼。

## 上機前的驗證工具與流程 — 2026-09-24（離線）

### `tools/verify_compressed_dng.py`（新增）

G4b 的驗證是**手做的、只做過一次**。copy-back 會常態產出這種檔案，檢查必須每次一致。
新工具把整套結構檢查變成一個指令，並加上 copy-back 專屬的兩項：

| 檢查 | 為什麼 |
|---|---|
| **檔案長度 == 79,872 + Σtile counts** | 這就是寫進 `seg[1]` 的數字。**長度與內容不一致正是 G5 的失敗形態**——每個檔都能解碼，內容卻是錯的 |
| **bytes 8..78,848 與 stock 逐 byte 相同** | owned header 是**擴充複製**，原始每個 tag、巢狀 IFD、MakerNote 都必須原封不動，只有 offset 4 的 root pointer 可變 |
| root pointer 已提交 | 沒提交的檔案會被當成**原始未壓縮影像**解碼——又一個靜默的錯答案 |
| Compression=7、strip tags 已移除、tile 幾何 | 格式合約 |
| 12 個 tile：宣告位移 == 實際 SOI、SOI+SOF3 開頭、EOI 結尾、彼此相接到檔尾 | 部分複製會在這裡被抓到 |

不自己解碼：解碼需要 LibRaw，所以它是分開的選項，
**沒有 LibRaw 的機器仍然拿得到全部結構檢查**。

測試 9 個全過，用 `canonical_header` 從**真實** stock header 合成測試檔
（tile 內容是假的但框架正確，所以不需要編碼器就能測檢查器）。
每個拒絕路徑都有對應的測試：截短／補長、tile 框架破壞、header 被改、
root pointer 未提交、strip tag 復活、宣告位移對不上。
拿真實 stock DNG 去跑會被正確拒絕（`root pointer is 0x8, expected 0x13400`）。

### `LIVE_TEST_PACKAGE.md` §3.5（新增）

把 copy-back 的上機流程寫成檢查表，C1（唯讀普查）→ C2（單幀）→ C3（連續八幀），
各自的進入條件、通過條件與中止條件都列出。

開頭寫了這次上機學到的**兩條硬規則**：

1. **每次 arm 後、錄影前,先確認探針狀態是全新的**（`not entered`、計時為 0）。
   `restore` **只還原 hook 字組,不清 cave**；cave 沒清時 arm 會**靜默失敗**，
   讀到的是上一次的舊資料。這就是 57,994 µs 假陽性的成因。
2. **被量測的錄影期間不得有任何 USB 流量。** 那次假陽性唯一與其他次不同的地方，
   就是它在錄影中做了兩次 `mem get`。

C1 的通過條件是四項全中：`frame_refcount == 1`、`frame_clones_made == 0`、
`frame_owner_id == 0`、`frame_buffer_is_seg0 == 1`。**任何一項不成立就停**——
不要因為「看起來只差一點」就往下走。

### 為什麼不再追 `dbfull`

`dbfull` 是 347 行、17 個呼叫點的狀態機，那個 clone 呼叫被
`iVar3` 對 1/6/8/0xB/0xC 以及 `FUN_c0397b30(...,0x13)` 的比較包著。
要定案得把整個擷取狀態機讀懂，代價太高——**而 C1 一次錄影就直接量到答案**。
這是刻意的取捨，不是放棄。

## 共用引用:clone 確實共用 buffer,但 movie 路徑讀不出來 — 2026-09-24（離線）

證據：[`ledger-frame-sharing-static-20260924.json`](../build/ledger-frame-sharing-static-20260924.json)。
回答 [`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md) §4 第 2 點：
copy-back 會覆寫整塊 `frame[0x68]`，還有沒有別人握著它？

### clone 共用,不是各自配置

```
Dup2 @ 0xC0374BF0
  └ FUN_c0380628  配置 0x111C bytes 的 frame 物件
      └ FUN_c0373dd0  逐欄複製,而它的迴圈把 +0x68 到 +0x128 整段抄過去
                      ← 那一段就是 RAW buffer 指標
  clone[0x1118] = owner[0x10FC]        clone 記住 owner
  owner[0x1114] += 1                   owner 引用數 +1
```

`FUN_c03777b8` 也是等最後一個引用歸還才釋放原配置。
**所以 clone 帶的是 owner 的 buffer 指標,沒有自己的配置。有 clone 存在時覆寫它就是破壞。**

### 會做幾個 clone

`FUN_c0374ee8`（Dup2 的唯一呼叫者）先呼叫 `FUN_c0397cd8`，然後
`for (i = 0; i < frame[0x1C0]; i++) Dup2(...)`。

而 `FUN_c0397cd8` **預設把 `frame[0x1C0]` 設成 1**，只有在 `frame[4]` 是 0 或 9 時
才依連拍／包圍設定調高。CinemaDNG 在 `FUN_c037a990` 走的是 `frame[4] == 2`——
不是 0 也不是 9，所以請求數停在預設的 **1,不是 0**。

### 但 movie 路徑到底走不走這條,讀不出來

`FUN_c0374ee8` 有兩個呼叫點，而且不一樣：

| 位置 | 條件 |
|---|---|
| `vbuf @ 0xC0379E08`（呼叫在 `0xC037A2D4`） | `if (param_1[0xA0] == 9)` — **有閘** |
| `dbfull @ 0xC0397E60`（呼叫在 `0xC03986D0`） | **沒有那個閘**；附近的 `if (frame[4] == 9)` 只包住它上面幾行 |

要用讀的定案，得追 `dbfull` 的控制流並證明 CinemaDNG movie 走不走到那裡。
那很貴，**而且答案在我們已經 hook 的地方可以直接觀察。**

### 所以改成一個唯讀的上機量測（已寫好,未執行）

`exact_flush_writer_probe.S` 加了一段 frame 引用普查，在 flush 之前執行。
它只做 load：

| 讀 | 意義 |
|---|---|
| `frame[0x04]` | capture kind——順便確認 movie 真的是 `frame[4] == 2` |
| `frame[0x68]` | RAW buffer |
| `frame[0x128]` | header bytes |
| `frame[0x10FC]` | frame id |
| `frame[0x1110]` | 已**做出**的 clone 數 |
| `frame[0x1114]` | **引用計數** |
| `frame[0x1118]` | owner id（0 = 自己就是 owner） |
| `frame[0x1C0]` | **請求**的 clone 數 |
| 衍生 | `frame[0x68] == seg[0]`？——writer 登記的是不是這個 frame 擁有的那塊 |

**判準：** 引用計數 1、已做 clone 0、owner id 0 → flush 時這塊 buffer 只有一個持有者，
copy-back 寫進去不會踩到別人。任何其他組合都代表 copy-back 需要不同的答案。

代價：**一次錄影,全程唯讀**。不跑 codec、不配置、不寫 frame、不寫 DNG，探針自我還原。

測試釘住兩件事，兩個都做過突變驗證：普查區段內**不得有任何寫到自有狀態以外的 store**
（在裡面塞一個 `str r2, [r5, #0x20]` 會讓兩個測試同時變紅），以及 null frame 時要跳過。

### 仍未確立

- CinemaDNG movie 走不走到 `dbfull` 那個沒有閘的呼叫
- `vbuf` 裡 `param_1[0xA0] == 9` 選的是什麼
- movie 的 `frame[4]` 實際值（由配置分支推論為 2，未觀測）
- 若有 clone，它是在我們的 hook **之後**才讀 buffer，還是只在之前

## PHASE 7 實作完成:copy-back — 2026-09-24（離線,未上機）

`single_frame_encode_discard_probe.S` 加了 `PHASE=7`，host 端加了 `copy-back` kind。
**尚未在相機上執行過。**

### 它做什麼

沿用 PHASE 5 的一切到「在自有 arena 裡把整個檔案組好」為止（header copy、
host 準備的 IFD template、tile offsets/counts、最後才寫 root pointer）。
之後分岔：

```
file_bytes = OUT_OFF + S_COMP_SIZE
copy_bytes = round_up(file_bytes, 16)          /* 四字複製迴圈的單位 */

if copy_bytes > seg[1]:                         /* seg[1] = 進場時捕獲的 S_LEN */
    什麼都不做                                   → S_FIT=0, stage 12
else:
    把 copy_bytes 從 arena+UNCACHED 複製到 S_BUF+UNCACHED
    dsb
    seg[1] = file_bytes                         /* 唯一改動的欄位 */
    dsb                                          → S_FIT=1, stage 11
```

**`seg[0]` 完全不碰。** 我們不把任何自己的 buffer 交給 writer，所以不管卡片何時讀、
也不管 64 MiB 的聚合批次把傳輸延後幾十幀，都不再是我們的問題——那是相機自己的
幀緩衝，相機本來就在管它的壽命，而它的 ring 正是為那個批次配的。

### 准入規則不假設任何東西

`seg[1]` 是 writer 在 `FUN_c069ac88` 親手交給我們的長度，那塊 buffer 確實裝著一個
那麼長的 DNG。所以那麼多 bytes 依定義可寫——不需要知道配置器、frame ring 或
spacing 的任何事。而 `FUN_c037a990` 的追蹤顯示真實容量**就是** `seg[1]`
（header + payload，不多一個 byte），所以這條規則是精確的而非僅僅保守。

放不下的那一幀**完全不動**：什麼都不寫、seg 不碰，stock 幀原樣送到卡片。
這就是 RAW fallback，而且判斷在 encode 之後、從尺寸表讀出，是**確定知道**的。
最壞情況 4,037,760 B 對上可用的 3,244,544 B，所以這條路徑是**必要的,不是優化**。

### 新增的狀態欄位

| 欄位 | 位移 | 意義 |
|---|---|---|
| `S_FILE_BYTES` | `0xDC` | `OUT_OFF + encoded` |
| `S_COPY_BYTES` | `0xE0` | 實際複製的 bytes（跳過時為 0） |
| `S_FIT` | `0xE4` | 1 = 已複製，0 = 留作 stock RAW |

G5 的失敗是**靜默**的。這幾個欄位加上 stage 11/12 的用意是：這次不會靜默。

### 測試（+6,共 129）

| 測試 | 退回什麼會紅（已實際突變驗證） |
|---|---|
| `test_copyback_never_hands_the_writer_our_buffer` | 在 PHASE 7 加回 `str r8, [r0]`（0xE5808000） |
| `test_copyback_bounds_the_copy_by_the_length_it_was_handed` | 把 `S_LEN` 換成 `DNG_LEN` 常數 |
| `test_copyback_skip_path_writes_nothing` | 跳過路徑寫到 `[r4, #S_*]` 以外的地方 |
| `test_copyback_reports_which_way_it_went` | 少了 `S_FIT` / stage 11 / stage 12 |
| `test_copyback_shares_the_compressed_layout_and_precheck` | 沒被納入 `COMPRESSED_KINDS` / `CODEC_KINDS` |
| `test_copyback_allocates_nothing_and_frees_nothing` | 出現 `F_ALLOC` 或 `F_FREE` |

前兩個是承重的，兩個突變都確實被抓到。

### 一個標註出來的推論

複製的兩端都走 `+UNCACHED` 視圖。G4a 證明了**自有 arena** 的 `0x8` 視圖對卡片 DMA
可見（只要一個 barrier，不需 cache 維護）；writer 的 buffer 也落在同一個
`0x4..0x7` 區間，所以套用了同一條 `+0x40000000` 規則。
**這是對 alias 的推論,不是量測** —— 註解裡寫明了，而第一幀上機就會決定它。

### 還沒做的

- **`seg[1]` 全寫對其他讀者是否安全**（NATIVE_BUFFER_PATTERNS §4 第 2 點）。
  `FUN_c0374bf0` 的 owner/clone 機制證明**存在**共享引用；74 幀 mark-only 只在
  padding 寫了一個 word。這必須在上機之前先有說法。
- **那個方向的複製成本**。G4a 是反方向。以 72.3 MB/s 估：1,396,736 B ≈ 19.3 ms，
  加 encode 13.6 ms = 24p 預算的 79%。未量測。
- 連續版本（PHASE 8 或 `copy-back-sustained`）。先讓一幀成立。

## 目標是 SD 與 SSD 兩者 → copy-back 的容量問題有確定答案 — 2026-09-24

證據：[`ledger-copyback-capacity-20260924.json`](../build/ledger-copyback-capacity-20260924.json)。

使用者定案：**產品目標是 SD 與 SSD 兩者。**

這直接選定了設計：**copy-back 是唯一同時覆蓋兩者的方案**，因為它不持有任何我們的
buffer，所以「SD 上關不掉聚合」這件事對它不成立為障礙。SSD 上若能關掉聚合，
那是額外的簡化，不是前提。

於是 copy-back 唯一的硬阻礙——容量——變成必須先答的問題。

### `buf` 到底有多大:正好是 stock DNG,一個 byte 都不多

`FUN_c037a990 @ 0xC037A990`：

```c
iVar5 = FUN_c02da770(frame + 0x10);                     // payload bytes
uVar4 = FUN_c001cf78(10);                                // class 10 = RAW
FUN_c001cfd8(uVar4, frame + 0x68,
             *(int *)(frame + 0x128) + ((iVar5 + 0x1ff) & ~0x1ff),
             0x400, 0);                                  // 0x400 是「位址」對齊
```

`size = header + round_up(payload, 512)`，FHD 就是
`78,848 + 3,165,696 = 3,244,544` —— 和實機四次量到的 node length
`0x318200` 完全一致。

**訂正一筆舊讀法：** `HW_LOSSLESS_JPEG_CODEC.md` 把
`0x31A400 - 0x318200 = 8,704` 讀成「frame ring 有 8,704 bytes 空隙」。
那是**配置器在區塊之間的粒度,不是我們那塊裡面的可寫空間**。沒有任何東西
證明寫進去是安全的。

### 由此得到一條不需要任何假設的規則

```
只有當 file_bytes <= seg[1] 時才複製回去
```

`seg[1]` 是 writer 在 `FUN_c069ac88` **親手交給我們**的長度，而那塊 buffer
確實裝著一個那麼長的 DNG。所以那麼多 bytes 依定義可寫——不需要知道配置器、
ring、spacing 或 descriptor 的任何事。

這正是這個 hook 從一開始就遵守的紀律：**只處理被交到手上的東西。**
而上面的配置追蹤顯示真實容量**就是** `seg[1]`，所以這條規則不只保守，是精確的。

### 因此「壓不下就寫 RAW」是必要的,不是選配

| | bytes |
|---|---:|
| 可用 | 3,244,544 |
| G4b 實測壓縮檔 | 1,396,736 ✓ 綽綽有餘 |
| 最壞情況壓縮檔 | 4,037,760 ✗ 放不進去 |

判斷點在 **encode 之後、改 `seg[1]` 之前**，從尺寸表讀出來，是**確定知道**的，
不是預測——這和 [`COMPRESSION_PRECHECK.md`](COMPRESSION_PRECHECK.md)
的事前抽樣估計是兩件不同的事，不可混用（後者絕不能拿來縮小緩衝區）。

放不下的那一幀代價是**白編一次約 13.6 ms**，正確性零風險：什麼都不改，
stock 幀就照原樣寫出去。這就是 ROADMAP 規劃的 adaptive mixed，
只是觸發條件從「值不值得壓」換成「放不放得下」。

### 仍然開放（copy-back 的其餘未知）

1. **寫滿 `seg[1]` 對其他讀者是否安全**——`FUN_c0374bf0` 的 owner/clone 機制證明
   **存在**共享引用；74 幀 mark-only 只在 padding 寫了一個 word。
   這是 NATIVE_BUFFER_PATTERNS §4 第 2 點，仍未解決。
2. **我們需要的那個方向的複製成本從未量過。** G4a 是反方向（讀 `buf` 寫 arena，
   72.3 MB/s）。以該速率估：1,396,736 B 約 19.3 ms，加上 encode 13.6 ms
   = 24p 預算的 **79%**，29.97p 貼邊，60p 不行。
3. SSD 錄影是否走同一條 frame 配置路徑。

## 下一步與本輪方法教訓 — 2026-09-24

### 下一步

目標已定為 **SD 與 SSD 兩者**，設計因此定為 **copy-back + 放不下就寫 RAW**。
容量問題已答（見上）。剩下的，依順序：

1. **實作 PHASE 7:copy-back**（離線）。在現有 `single_frame_encode_discard_probe.S`
   上加一個階段：encode 進自有 arena → 建當幀 header → **若
   `file_bytes <= seg[1]` 才**把整個檔案複製回 `S_BUF` → 改 `seg[1]`；
   否則什麼都不做，讓 stock 幀照原樣寫出去。不重導 node，不持有任何 buffer。
   host 端加上對應的 kind 與測試。
2. **量那個方向的複製成本**（上機，但只要一幀）。G4a 量的是反方向。
   這決定 24p／29.97p 是否真的在預算內，也決定 60p 要不要走抽幀。
3. **一幀 copy-back 的正確性驗證**（上機）。接著連續八幀——
   **這直接檢驗 G5 的失敗在 copy-back 下是否消失**，那是整個方向的判決點。
4. **NATIVE_BUFFER_PATTERNS §4 第 2 點**：寫滿 `seg[1]` 對其他讀者是否安全。
   這在第 3 步之前必須先有說法，不能只靠 74 幀 mark-only。

SSD 相關的仍可順手做：接上 SSD 後 Media Write Mode 是否可改、flush 會不會變長。
若可以，SSD 路徑上還有一條更簡單的備案（單一 arena），但**不作為主線**——
主線必須兩種媒體都成立。

**已退場：**

- 「關掉 SD 聚合讓寫入變同步」—— SD 上關不掉，四次 flush 量測不變。
- **自有 output slot 陣列** —— 要 ~196 MiB，超過相機自己的 ring（87 MiB）。

無關且隨時可做：COMPRESSION_PRECHECK §8 的 host prototype。

### 方法教訓（三條,都是被抓到的錯）

1. **靜態閱讀與實機量測衝突時,以實機為準。** 我從 `open → write → close → 返回`
   加上 `wai_sem` 無限逾時，推出「寫卡是同步的、`FUN_c069ade0` 返回就是釋放點」。
   G3 的 372 µs / 8.7 GB/s 早就否定了它。沒有回頭讀 ledger 的話，
   我會拿一個錯結論去改設計。

2. **n = 1 不算量測,而且要先驗證儀器是全新的。**
   `SetMediaWriteMode 2` 之後第一次量到 57,994 µs（= 55.9 MB/s，非常像
   「寫入變同步了」）。兩次重跑回報**一模一樣**的數字——因為 arm 在 cave 被佔用時
   靜默失敗，我讀的是同一筆舊資料。清乾淨、確認探針是
   `not entered / flush_elapsed_us 0` 之後，答案是 368 µs。
   那一次唯一不同的地方：**只有它在錄影進行中做了 `mem_get`**。
   規則：每次跑前驗證探針狀態全新；被量測的錄影期間不得有任何 USB 流量。

3. **韌體能告訴我一個值從哪裡來,告訴不了我它在使用者眼中是什麼。**
   我花了一整輪上機追「關掉批次」。使用者一句「那個是 SSD 的設定」就把它定位了。
   早點問「這個選單項目在機身上長什麼樣」會省掉那一輪。

## 原生緩存審閱與訂正 — 2026-09-24（接續下方更新，離線）

依「不要過度設計」，新增 [`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md)，
並同步 BUFFER_DESIGN／ROADMAP。這段訂正優先於本檔下方同日較早的靜態追蹤：

- 韌體映像證實 vtable `C0B972C4` 含兩個表頭 words，`+0x18` 是 `C03686C0`（v4），
  不是 `C03689C8`（v6）。真正 scatter 鏈經 `C063B898 -> C063F380`；舊
  `ledger-writer-chain-static-20260924.json` 原樣保留，但其錯誤下游結論不再採用。
- movie `C03A5348` 交給 `C069ADE0` 的 cookie 是當前 frame pointer，不是 0。
  原廠 `C03A55D0(frame,status)` 已有逐幀完成通知，優先查它能否承接自有 slot 回收。
- SD cache 主要保存 range descriptors，非整幀 payload 副本。初始化的 64 MiB 是
  聚合門檻，256 KiB 才是此處另配的輔助區。小 slot pool 與批次完成的進度須一起驗證；
  原生 stop/drain 已定位，不等於正常錄影時可任意要求 flush。
- 原生 RAW owner/clone 有引用計數。下方「約 28 幀 ring」「74 幀可寫」不能證明固定
  深度或完整 RAW 獨占；copy-back 必須過容量、其他讀者、metadata、copy 完成及批次進度 gate。
  `4,037,760 B` 不能塞入原 `3,244,544 B` 範圍，不只是慢的問題。
- 原生 AudioFileWriter／MPoolFixed 可借固定格數、busy 與明確歸還規律；回收訊息不等於
  回收其 payload。plain write 與 scatter 路徑不同，不能用 G3 斷言 gyro 只靠時間差安全。
  allocator class 不同亦不構成資源不競爭的證明。
- 下方容量入口修正已由現行 source 核對：codec kinds 共用 gate、ARM 扣 OUT_OFF、模型
  改整數 14 bits。仍不是硬體容量 proof；本輪未重跑下方所列測試。

本輪只改筆記；沒有改 runtime、操作相機、改卡或部署。下一步是驗證既有 completion +
batch policy，不新增通用緩衝框架。完整地址、映像 words、推論限制見新筆記。

## 容量入口修正 — 2026-09-24（離線，無相機）

做的是 [`BUFFER_DESIGN.md`](BUFFER_DESIGN.md) §4 指名的兩個前置修正，以及
[`BUFFER_RESEARCH.md`](BUFFER_RESEARCH.md) §4.3 附帶指出的 7 bytes drift。
全程離線，沒有碰相機，沒有 arm 任何 hook。

### 1. 裝置端的容量比較扣掉了 header

`single_frame_encode_discard_probe.S` 的 `sum_sizes` 把 12 個 tile 尺寸加總後，
無條件與整個 `WORK_CAP` 比較：

```
    LDA     r0, WORK_CAP          /* 修正前 */
    cmp     r1, r0
    bhi     encode_size_range
```

PHASE 5/6 的 payload 從 `base + OUT_OFF` 開始（自有 header 佔掉 `0x13800`），
真正的容量是 `WORK_CAP - OUT_OFF` = 4,048,896，不是 4,128,768。也就是說，落在這
79,872 bytes 區間內的輸出**會通過檢查**，而它已經蓋掉守衛字與尺寸表了。
現在比較 `WORK_CAP - OUT_OFF`；`OUT_OFF` 在其他 phase 是 0，所以同一式子對所有
phase 都正確，不需要條件編譯。

`S_WORK_END` / `S_WORK_GUARD`（第 394 行那個 `WORK_CAP`）是對的：守衛的絕對位置
與 payload 起點無關，維持 `base + WORK_CAP`。

這仍然是事後檢查。它不能撤銷已經跑完的 DMA，只能讓越界被發現而不是被當成成功。

### 2. `compress*` 根本沒走預檢

`build_image()` 只對 `("encode", "encode-live", "encode-sustained")` 呼叫
`require_safe_arena()`，而且沒有傳 `kind`。兩個後果：

- 壓縮 phase 完全跳過建置期 gate。`encode` 會拒絕的幾何，對**容量更小**的那個
  phase 反而照組不誤。
- 就算走到了，不傳 `kind` 會用整個 `WORK_CAP` 當容量。

現在有一個 `CODEC_KINDS`，所有跑 codec 的 kind 共用同一個
`require_safe_arena(kind=kind)`。`mirror` 刻意不在其中：它是 stock DNG 的等長複製，
套 codec 的最壞界只會碰巧通過，不構成論證。

順帶修掉兩件同一處的東西：

- `elif kind == "compress"` 與 `elif kind == "compress-sustained"` 各出現**兩次**
  （插入 `mirror` 分支時複製貼上）。第二組不可達。今天無害因為內容相同，但改了
  第二份永遠不會執行。已刪除重複，並加測試釘住每個 kind 只 dispatch 一次。
- `require_safe_arena(tile_w=TILE_W, tile_h=TILE_H, ...)` 的預設值在 import 時凍結，
  改動模組常數不會改變它驗證的幾何——正是 `TILE_H` 那個 bug 的形狀。改成呼叫時解析。

### 3. 7 bytes 的 drift：上界的兩份實作

§4.3 說「現有兩處 estimate 尚有 7 B drift，新 generator 要求整數公式 exact
equality，不接受『差 64 B 內』」。找到了，而且方向是錯的那一邊：

| | 512×368 上界 |
|---|---:|
| `tools/output_bound.py` | 3,957,839 |
| `single_frame_codec_probe.py` | 3,957,832 |

成因是兩個都往小捨的捨入疊加。數值搜尋的結果是 `13.999823879015727`：

1. 探針把它寫成字面常數 `13.9998`（**向下**捨去 2.39e-05）；
2. 再用 `int(padded_samples * 13.9998)` **截斷**而不是取上取。

低的那份正好是**建置 gate 在用的那份**。一個應該拒絕不安全幾何的閘門，用的是比
上界更寬鬆的數字；上界低於真值就不是上界。

改成單一整數公式，兩邊都呼叫它：

```
BOUND_BITS = 14                                  # 13.999823… 的整數上取
bound = padded_samples * BOUND_BITS // 8 + tiles * 96
```

`padded_samples * 14` 在這個幾何下正好被 8 整除，全程沒有任何捨入可以出錯。
512×368 的上界變成 **3,957,888**（比工具舊值高 49 B，比探針舊值高 56 B，保守方向）。
壓縮容量 4,048,896 下的餘裕仍是 **2.30%**。

模型沒有變，仍然不含 entropy 段的 `FF 00` byte stuffing，所以這個 2.30% 依舊偏樂觀。

舊的 `test_inlined_bound_matches_the_source_tool` 用的是
`assertLess(abs(theirs - mine), 64)`——字面上就是 §4.3 拒絕的那個容忍度，也正是讓
7 B 看起來「有被檢查」的東西。已刪除，由精確相等的測試取代。

`build/output-bound-20260923.json` 依 ROADMAP §13 未改任何原欄位。該檔記的是工具值
3,957,839，本來就沒錯，更正寫在 `corrections`。

### 測試

新增 6 個、刪除 1 個，`test_single_frame_codec_probe.py` 從 75 → **80**。
每個修正都做過突變檢查（把修正退回，確認對應測試確實失敗）：

| 測試 | 退回什麼會紅 |
|---|---|
| `test_device_checks_the_payload_against_the_shared_capacity` | ARM 改回比 `WORK_CAP` |
| `test_device_and_host_agree_on_every_kind_capacity` | 同上 |
| `test_every_codec_kind_goes_through_the_one_precheck` | 預檢改回三個 encode kind |
| `test_the_kind_dispatch_has_no_unreachable_duplicate` | 重複分支復原 |
| `test_bound_matches_the_tool_exactly_at_every_geometry` | 任一邊的 `BOUND_BITS` 變動 |
| `test_the_bound_is_above_every_size_the_camera_has_produced` | ledger 中出現超過上界的實測值 |

總計：codec 123、tools 42、native_port 23。
（`fpSup/lossless/native/test_native_variable.py` 需要 `--seg0 --shared-probe
--elf-helper` 與 unicorn，不能用 `unittest discover` 跑，其 23 個 error 為既有情況，
與本次無關。）

### 沒有做的

- §4.3 還要求「只有一個產生 layout 的來源，每種 phase 消費同一 descriptor」與
  `capacity_proof_id`。這次只讓兩個既有入口一致，沒有寫 layout generator。
- 命名仍是 `HDR_BYTES`(=0x13400，stock header copy)與 `OUT_OFF`(=0x13800，
  compressed header)。§4.3 要求改名為 `STOCK_HEADER_COPY_BYTES` /
  `COMPRESSED_HEADER_BYTES`，尚未做。
- `OUT_OFF = align_up(IFD_AT + ifd_size + 8*tile_count, 0x400)` 的推導式還沒接上；
  目前 `810 of 1024` 這個估計經 stock DNG 實算為**精確值**（59 entries，
  ifd_size 714 + 96 = 810，剩 214 B padding），但它是寫死的，tile 數改變時不會跟著動。

### 讀舊筆記翻出的一條可能繞道：寫回相機自己的幀緩衝

> **⚠ 收緊（2026-09-24 稍晚）。** 見
> [`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md) §4。本節把它寫得太像
> 一條已成立的捷徑。五點修正，其中第一點是我漏掉的硬條件：
>
> 1. **先被容量淘汰，不是先被時間淘汰。** 最壞情況檔案 4,037,760 B 大於原本的
>    3,244,544 B，根本放不進那個 `buf`。我整節都在算複製時間，卻沒先檢查裝不裝得下。
> 2. tapseg 的位址範圍與 `0x31A400` spacing 只能推測 pool 分布，**不能定案「固定 28 格」**，
>    更不能把 spacing 當成該 `buf` 的可寫容量。descriptor 的 base/capacity 未確認前，
>    上限最多只能取原本的 `seg[1]`。
> 3. 74 幀 mark-only 是在 padding 寫**一個 word**，不是「整段 RAW 被覆寫後仍無其他讀者」的證明。
>    `C0374BF0` 的 owner/clone 機制證明**存在**共享引用，不證明當前 movie 每幀都獨占。
> 4. G4a 是**反方向** mirror，用它的速率估 copy-back 只是成本假說，不是 24p 通過證據。
>    class 0 與 class 10 不同也不代表沒有 DRAM／頻寬／allocator 競爭。
> 5. 下游生命週期只是**轉由原生 frame 承擔，並未消失**；而且壓縮後檔案變小，
>    可能反而延後原廠的批次完成。
>
> 不排除，但不作預設解法。優先驗證原廠現成的 `C03A55D0` 完成回呼。


> 歷史提案，非目前已證明可行方案。固定 28 格、74 幀完整覆寫、24p 可行及不需 release
> 等推論已收緊，請先讀本檔頂端訂正與 NATIVE_BUFFER_PATTERNS §4；下文原樣保留追溯。

追 §8 第 1 項時重讀 [`research/imaging-hw/notes/HW_LOSSLESS_JPEG_CODEC.md`](../../../research/imaging-hw/notes/HW_LOSSLESS_JPEG_CODEC.md)，
其中 `raw/tapseg.S` 的實測有一項一直沒被接到緩衝區問題上：

```
buf=0x5C6A0000  len=3,244,544  arg3=2
buf=0x5C385C00  len=3,244,544  arg3=2      spacing 0x31A400
...  buffers 0x56FC1000 .. 0x5C6A0000，約 92 MB，約 28 幀深
```

**相機自己有一圈約 28 個幀緩衝，每幀一個不同的 `buf`。** 而同一份筆記另外記了
`raw/cdngcomp.S` 在 74 幀 clip 上每幀都寫入 `buf` 且每幀都有效——所以寫進 `buf`
是已經驗證過的。

這指向一條不需要更多記憶體的路：**不重導 node，把壓好的檔案複製回相機交給我們的
那個 `buf`，只改 `seg[1]`。** 這樣每一幀的資料落在相機自己的 ring buffer 裡，
壽命由相機管理——G5 的「八幀共用一塊 arena」問題直接消失，因為我們不再持有輸出。
我們的 4 MiB arena 退回成純 scratch，用完即可覆寫，不需要 release 通知。

代價是每幀多一次複製。唯一有實測的複製速率是 G4a mirror：
**3,244,544 B / 44,896 µs = 72.3 MB/s**（[ledger](../build/ledger-g4a-mirror-20260923.json)）。

| | bytes | copy µs | + encode 13,652 | 對 24p 41,708 µs |
|---|---:|---:|---:|---:|
| G4b 實測 file_bytes | 1,396,736 | 19,327 | 32,979 | **79.1%** |
| 最壞情況 file_bytes | 4,037,760 | 55,872 | 69,524 | 166.7% |

依幀率（用 G4b 的實測大小）：24p **79.1%**、25p 82.4%、29.97p **98.8%**、60p 197.7%。

所以這**不是**通解：它在 24p 一般內容下可行，29.97p 已經貼著邊，60p 與最壞情況內容
都不行。但它是目前唯一一條不需要 8 MB 雙緩衝、也不需要先解出 release 語意的路，
值得排在 §8 第 1 項的讀取追蹤旁邊，而不是之後。

**未證實的部分（不要當成結論）：**

- 72.3 MB/s 是**反方向**量的。mirror 是「讀 writer 的 `buf` → 寫我們 arena 的
  `0x8` uncached view」；寫回是「讀我們的 arena → 寫 `buf`」。同樣兩塊記憶體對調
  角色，速率相近是合理猜測，不是量測。
- codec 不能直接寫進 `buf`。輸出若放在 `buf + 0x13800`，它會蓋掉還沒讀到的
  source（source 在 `buf + 0x13400`，讀指標只比寫指標快約 2.3×，起點就已經落後）。
  ring 每幀只有 8,704 B 空隙，也放不下。所以 scratch arena 仍然需要，複製省不掉。
- `buf` 在 `FUN_c069ac88` 返回後由誰、在什麼時候讀，仍然是 §8 第 1 項要查的同一件事。
  差別在於：那是**相機原本就要回答的問題**，而不是我們新造的。

### 寫入鏈靜態追蹤 — BUFFER_DESIGN §8 第 1 項（離線）

> **⚠ 本節下游鏈已撤回（2026-09-24 稍晚）。** 見
> [`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md) §2 與
> [ledger 的 corrections](../build/ledger-writer-chain-static-20260924.json)。
>
> 我把 media vtable 當成從 `+0x00` 就是方法，但 `0xC0B972C4` 的前兩個 word 是表頭
> （`00000000` / `C0B9731C`），方法從 `+0x08` 起算；我又把反編的 `vN` 命名
> （依位址排序）當成 slot 編號。兩個錯都偏 8 bytes，於是 `+0x18` 追成 `C03689C8`，
> 實際是 **`C03686C0`**。
>
> 因此以下三項作廢：`SdCard::v6` 與 `FUN_c063c970` 那一段、
> 「`C063F380`/`C063F140` 不在這條鏈上」的結論（**它們就在鏈上**）、
> 以及「DNG 路徑 cookie 為 0」。**movie 的 cookie 是 frame 物件指標**，
> `C03A5348` 以 `mov r1,r4; add r0,sp,#0x20; bl C069ADE0` 傳入，
> 而 **`C03A55D0(frame, status)` 是原廠現成的逐幀完成回呼**。
>
> 諷刺的是證據就在我讀過的反編裡：`param_2 + 0x1104`、`param_2 + 0x10FC`
> 正是 frame 欄位，`C03A55D0` 設的就是 `frame+0x1104 = 0xD`。我沒有把它連起來。
>
> gyro 那條 `[I]` 推論也撤回：plain write 走的是
> `C03685B0 -> C063B818 -> C063F898`，與 scatter 不同路，可能先觸發 `C063F140`，
> 所以不能用 G3 的 scatter 延遲去斷言 gyro 只靠時間差安全。
>
> **仍然成立的**：register 半邊；`FUN_c069ade0` 一次呼叫開檔寫完關檔；
> register 與 submit 同 task／同堆疊／同一次呼叫；node 表在 submit 時被抄進
> 八組 {指標,長度} 的堆疊陣列，node 層沒有東西能跨 frame 持有；
> 我們要的是 allocator class 0 而非 class 10。
>
> 以下原文保留供追溯。


> 本節 vtable dispatch 算差 8 bytes，v6／C063C970／C06412A0 不是 movie scatter 鏈。
> 正確鏈與原生逐幀 callback 見本檔頂端訂正及 NATIVE_BUFFER_PATTERNS §2–3；本節保留歷史，
> 不用其下游推論作新的 hook 或釋放依據。

證據：[`build/ledger-writer-chain-static-20260924.json`](../build/ledger-writer-chain-static-20260924.json)。
讀 `out/decomp/full/` 既有的完整反編與 `out/seg0_c0000000.bin`，沒有跑 Ghidra，沒有碰相機。

#### 鏈的形狀

```
XC_StillFileFormatDng::v19 @ 0xC0722A68
  └ 0xC0722AFC  BL FUN_c069ac88        ← 我們的 hook。把 {buffer,len,kind} 存進 node 表
                                          不搬任何 bytes

FUN_c03a5348 @ 0xC03A5348             ← G3 打到的那個函式
  ├ FUN_c03813d0(auStack_b4, ...)       writer 物件，建在它自己的堆疊上
  ├ vtable+0x54(...)                    → 通到上面的 v19，登記 segment
  └ 0xC03A5490  BL FUN_c069ade0(auStack_b4, ...)
       ├ FUN_c0365e90   ctor
       ├ FUN_c0365fb0   open (0x406 / 0x806 / 0x1806)
       ├ 走 node 表，把每個 {ptr,len} 抄進 auStack_6c[16]
       ├ FUN_c0366168   scatter write   → vtable +0x18
       ├ FUN_c0366020   close
       └ dtor
            └ XC_MediaFileSdCard::v6 @ 0xC03689C8
                 └ FUN_c063c970
                      wai_sem(sem,1,無限) → FUN_c063ab60 建 request
                      → FUN_c06412a0 發出 → FUN_c063aef8 存狀態 → sig_sem
```

TK-OS 服務碼是從 image 直接讀出來的(每個 stub 在 +0x20 帶 32-bit service id)，
並用 gyro 筆記已確立的兩個值交叉驗證：`0xC01F8B74 = 0x80290300` (rcv_mbx)、
`0xC01F8D00 = 0x80130100` (slp_tsk) 都吻合。新的兩個：
**`0xC01F8E8C = 0x80190300` → service 0x19 `wai_sem(id,cnt,tmout)`**、
**`0xC01F8CDC = 0x80180200` → service 0x18 `sig_sem(id,cnt)`**。

#### 我一度得出錯的結論，被既有實測推翻

讀到 `open → write → close → 返回`，加上 `wai_sem` 用的是**無限逾時**，我一度認為
寫卡是同步的、`FUN_c069ade0` 返回就是釋放點。**這是錯的**，而 G3 的 ledger 早就寫了：

> 3,244,544 bytes 在 372 µs = **8.7 GB/s**，所以那是 submit 或 accept，不是寫卡

沒有 SD 卡跑得到那個速率。所以那把 semaphore 保護的是**提交**，不是傳輸；
`close` 也不代表落卡。BUFFER_DESIGN §5 拒絕把 372 µs 的返回當成可重用通知是對的，
而且現在對 `close` 一樣成立。

靜態閱讀與實機量測衝突時，以實機為準。這次如果沒回頭讀 G3 的 ledger，
我會拿一個「單一 arena 就夠」的錯誤結論去改設計。

#### 確實有進展的三件事

1. **register 和 submit 在同一個 task、同一個堆疊、同一次呼叫裡。** `FUN_c03a5348`
   把 writer 建在自己的堆疊上、填好、消費掉，然後返回。兩者之間**沒有跨 task 視窗**。
   所以問題不在「登記之後、提交之前有人插隊」。

2. **node 表在 submit 時就被抄進堆疊陣列,然後整個 writer 物件隨 frame 消失。**
   提交之後還握著我們 buffer 指標的，是**下層的 request**，不是 node 表。
   這把 BUFFER_DESIGN §2 裡「保留自有 seg」「generation 綁 request identity」那一整套
   往下推了一層：node 層沒有東西可以持有或釋放。

3. **那個堆疊陣列是 `auStack_6c[16]` = 八組 {指標,長度}。** 一個檔案最多八個 segment
   是硬結構上限，和先前記的「assert at eight」吻合。

#### 沒有追到的

- 佇列在哪。`FUN_c06412a0` 以下沒追；那裡 Ghidra 的參數型別是猜的
  （它把呼叫端傳的 request 結構當成路徑字串在讀 `param_2[1] == 0x3a`，也就是 `':'`）。
- 那個 queued request 的完成有沒有被回報、回報給誰。
- BUFFER_DESIGN §5 點名的兩個候選 `FUN_c063f380` / `FUN_c063f140`
  **完全沒有出現在這條鏈上**。它們仍未驗證，而且不是這裡追到的路徑。

### gyro 的緩衝設計:哪些可以抄,哪一條絕對不能

> **⚠ 最後一段的推論已撤回。** 「gyro 只靠 0.8 秒的時間餘裕才安全」這個說法，
> 是拿 G3 在 **scatter** 路徑量到的延遲去推 gyro 的 **plain** write。
> 兩者不同路：plain 是 `C03685B0 -> C063B818 -> C063F898`，而且可能先觸發
> `C063F140`。見 [`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md) §5。
>
> 「不要照抄 gyro 的釋放時機」這個**結論**仍然成立——但理由必須是
> 「plain 與 scatter 的完成語意尚未各自證明」，不是我原本寫的那個。
> 本節其餘部分（結構、class 10 界線）不受影響。


gyro logger 是這個專案裡唯一另一個從相機內部寫卡、而且長時間跑穩的東西。對照之後：

**同一組檔案 API。** gyro 的 `.equ F_OPEN, 0xC0365FB0` 就是 `FUN_c069ade0` 開檔用的
同一個函式；`F_WRITE = 0xC03660E8` 是 vtable +0x14，CinemaDNG 的 scatter write
`FUN_c0366168` 是 +0x18，兩者是**同一個 wrapper、同一把卡鎖**。所以 gyro 的經驗直接適用。

**可以抄的(BUFFER_DESIGN §2 想要的形狀,而且已經在這台相機上證明過):**

- **八個各自配置的 block，不是一大塊切開。** gyro 原本是「一大塊切成 16 份用算術分」，
  改掉的理由寫得很直接：那樣 "full" 還是一個計算，只是搬到 producer 外面。
  現在邊界就是配置本身的大小——沒有 index、沒有 mask、沒有 modulo。
- **job descriptor 帶「哪一格」**（`J_BLK`：*which block, so the writer can free it*），
  外加 `J_OFF` 檔案位置。`J_OFF` 不是裝飾：沒有它，一個拿不到 descriptor 的 job 會
  silently 消失，後面每筆記錄在檔案裡提早了一個洞的長度。
- **專用 task，優先權 6，無限逾時阻塞在 mailbox 上。** 抄 `AudioFileWriter::v1`，
  因為那是這台相機上唯一在錄影負載下證明不掉的路徑。gyro 原本 28 / 32 KiB 雙緩衝 /
  5 ms 輪詢，會掉。
- **descriptor 的第一個字是 kernel 的。** `J_MSGQ` 留空不碰；gyro 曾把 `J_PTR` 放在
  那個位置，於是我們往 kernel 的 list pointer 存環位址、kernel 往我們的環位址存
  list pointer，錄影五秒就凍結——**即使把所有卡片呼叫都拔掉還是凍結**，因為它從來
  不是卡片的問題。

**一條安全界線,已經查過,我們是對的:** gyro 花一週追的凍結，根因是 movRec 的
**class 10 配置失敗——10 是 RAW，CinemaDNG 的幀緩衝**。我們的探針要 `mov r0, #0`
= class 0 USER，和 gyro、AutoRun 同一個。沒有衝突。
（這也提醒:先前那條「寫回相機自己的 `buf`」，那些 buffer 正是 class 10 的。）

**絕對不能抄的:它的釋放規則。**

```
bl  writer_put        @ 寫卡
bl  writer_release    @ 立刻把該 block 標成不忙
```

gyro 在寫入呼叫**一返回**就歸還 block，它自己的註解說得很明白：
*block is safe to refill — and until it is told, it counts a drop rather than
writing over data the card has not seen.* 也就是說它**相信**「呼叫返回 = 卡片已看到」。

G3 的 372 µs / 8.7 GB/s 顯示這個信念不成立。

gyro 沒出事，是因為**時間餘裕，不是因為它解決了 fence**：它一格 0.8 秒、八格 6.6 秒，
queued write 早就排完了。我們是 41.7 ms 一幀。**同一條規則在我們的速率下就是 G5。**

這是這次對照最重要的一條：gyro 的**結構**可以抄，gyro 的**釋放時機**不行。

### SD 聚合與完成語意 — ROADMAP §16 第 1 項（離線）

證據：[`build/ledger-sd-aggregation-static-20260924.json`](../build/ledger-sd-aggregation-static-20260924.json)。
沿 [`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md) 訂正後的鏈，不是我撤回的那條。

#### 1. `C0646C60` 的返回語意:**0 = 成功,負值 = 失敗**

```
FUN_c0646c60  → 轉換位址後回傳 FUN_c0646580，參數錯誤回 -3
FUN_c0646580  → local_6c 初值 0；只在內層 != 1（即失敗）時提早回傳該值；
                 否則回傳 FUN_c0646248 的值
FUN_c0646248  → 結果變數只在內層 != 1 時被賦值，成功時保持初值 0
```

**為什麼要追這個:** `C03A55D0` 的兩個呼叫端一度看起來慣例相反。`FUN_c03a5348` 用
`0 = 成功 / -1 = 失敗`，而 `FUN_c063f140` 傳的是 `C0646C60` 的返回值——旁邊的
`FUN_c0646d38` 是 `1 = 成功`，若照那個推，**一次成功的批次到 `C03A55D0` 會被當成錯誤**。
讀函式本身得到 0，兩邊一致。這是一個被排除的疑慮，不是缺陷。

`C03A55D0(frame, status)` 的慣例：`status != 0` 會走嚴重度 3 的錯誤記錄，並以
`C03A52D0(manager, frame[0x10FC], 4, status != 0)` 當錯誤旗標傳出；
`frame[0x1104] = 0xD` 兩種情況都會設。

#### 2. status 是**整批共用**的

```c
for (i = 0; i < vol[0x4850]; i++)
    cb(vol[0x4854 + i*4], status);     // 同一個 status 給每個 cookie
```

**通知是逐幀的,判定是整批的。** 一批失敗，批內每一幀都被標成失敗；也沒辦法從 status
把某一幀和鄰居分開。

#### 3. 原廠的四個 flush 觸發（`FUN_c063f380`）

| 觸發 | 條件 |
|---|---|
| 實體不連續 | `vol[0x4a54] + vol[0x4a58]/sector != next_lba` |
| descriptor arena 取不到 | `vol[0x484c] == 0` |
| 累積到門檻 | `vol[0x4828] <= vol[0x4a58]` |
| cookie 陣列滿 | `vol[0x4850] == 0x80`（128 筆） |

`FUN_c063f310` **不是** per-frame flush，它是排空並**停用**聚合（清 `0x4828` / `0x484c`）。
第二個參數非 0 時會先把 `vol[0x4a54]` 清零，使 `FUN_c063f140` **完全跳過傳輸**、
對所有待處理 cookie 回報 status 0。

#### 4. 整個設計取決於一個 byte:`manager+0xD`

```c
// FUN_c03a5348
if (manager[0xD]) {                       // 聚合開啟
    frame[0x1104] = 0xC;                  // 標記「已提交」
    C03A52D0(manager, frame[0x10FC], 3, 0);
}
total = C069ADE0(writer, frame);
if (!manager[0xD]) {                      // 聚合關閉
    C03A55D0(frame, total == 0 ? -1 : 0); // 立刻回呼
}
```

- **旗標設起來** → `C03A55D0` 由 `FUN_c063f140` 在真正傳輸之後才送達。**這才是 fence。**
- **旗標清掉** → `C03A55D0` 在 submit 當下就送達，等同 G3 的 372 µs。**不是 fence。**

**這個旗標在錄 CinemaDNG 時是什麼值,尚未確立。** 一個 byte，決定整個設計。
G3／G5 當次的值也沒有被記錄下來。

#### 5. 批次算術:壓縮讓這件事更難,不是更容易

門檻 `0x04000000` = 64 MiB（再依 volume 幾何對齊）：

| | 每幀 bytes | 每批幀數 | @24p | 自有 slot 需求 |
|---|---:|---:|---:|---:|
| stock RAW | 3,244,544 | 20.7 | 0.86 s | 87 MiB |
| G4b 實測壓縮 | 1,396,736 | **48.0** | 2.00 s | **196 MiB** |
| 最壞情況壓縮 | 4,037,760 | 16.6 | 0.69 s | 70 MiB |

**檔案變小 → 每批累積更多幀 → 要撐過一批需要更多格。** 這是
NATIVE_BUFFER_PATTERNS §3 那句警告的具體數字。

而 tapseg 觀測到的原生 ring 約 28 格 × `0x31A400` = **86.9 MiB**，
對上 stock 的每批 20.7 幀，餘裕約 7 幀。**ring 看起來就是照批次政策配的。**
（格數是從位址範圍推的，不是量到的——§4 第 1 點已經提醒過。）

若聚合真的開著，自有 slot 陣列要 ~49 格才撐得過一批壓縮幀，比原生 ring 還大。
這反過來說明 copy-back 為什麼結構上說得通：**原生 ring 本來就是為了撐過批次而存在的。**
但 copy-back 仍卡在容量（最壞 4,037,760 > 3,244,544）與 §4 列的其餘四點。

#### 沒有解決的

- `manager+0xD` 的實際值。以上全部分支在它上面。
- **不連續觸發實際多常發生。** 如果每幀一個新檔就會打斷 LBA 連續性，批次會每幀 flush，
  `C03A55D0` 就變成延遲約一幀的可用 fence——但 G5 的八幀同內容說它沒有每幀 flush。
  **這兩個讀法我沒有調和。**
- `FUN_c063f140` 能不能從自有 context 安全呼叫（它動 volume 狀態與 descriptor arena，
  而且是在呼叫端的鎖底下）。
- 對齊後 `vol[0x4828]` 在實際卡片上的值。

### 那個 byte 是什麼:一個使用者選單設定（離線）

證據：[`build/ledger-aggregation-switch-static-20260924.json`](../build/ledger-aggregation-switch-static-20260924.json)。

```
MenuItemMediaWriteMode::v3 @ 0xC00AB8E8
    *(byte *)(param_2 + 0x9C) = 0 或 1
        ↑ param_2 是共用設定區塊，不是這個項目自己的狀態：
          blk_c00.c 裡 160 個 MenuItem*::v3 各自寫進 param_2 的不同位移
          （CinemaMode +0x44、DriveMode +0x48、AudioRecSupport +0xE0…）
          MediaWriteMode 佔 +0x9C

FUN_c03a5050（CinemaDNG init）讀同一格：
    manager[0xD] = *(byte *)(FUN_c0021c40() + 0x9C)
        FUN_c0021c00() → 單例 0xC30751D4
        FUN_c0021c40(obj) → *(obj + 0x5C)
    非 0 → FUN_c0366790 裝上聚合，表在 0xC0B9E5D8
           = {0x04000000, helper, 0x00040000, 0xC03A55D0}

FUN_c03a5348 以同一個 byte 分支（見上一節）
```

**它是選單設定「Media Write Mode」,不是內部能力偵測。** 字串 `SetMediaWriteMode`
在 `0xC0BBE2E0`，夾在 `SetMediaSelect`(`0xC0BBE2BC`) 與
`SetFilePrefixRule`(`0xC0BBE318`) 之間——全都是 `menu Set*` 的 shell 指令。

兩個選項的資源名：`CM_MediaWriteModeAj`(`0xC18CDA80`)、
`CM_MediaWriteModeFix`(`0xC18CDA94`)。

#### 兩個後果

1. **一行唯讀指令就能讀到**：`menu SetMediaWriteMode`（不帶參數）。
   不需要 mem get、不需要 arm、不寫任何東西。這大概是這個專案裡代價最低的相機事實。

2. **它是使用者可以動的設定。** 所以它不是韌體的固定性質——我們做的東西必須在兩個
   位置都能運作，或在不支援的位置**明確拒絕**。只在某個選單位置才成立的設計不是設計。

#### 沒有確立的（不要當成結論）

- **`Aj` 與 `Fix` 是什麼意思沒有追。** 它們只是一張 condition 名稱表裡的資源名後綴。
  「adjust / 固定大小配置」是明顯的讀法，但**這裡沒有任何東西支持它**。
- 哪個值對應 1、哪個對應 0。`MenuItemMediaWriteMode::v3` 是透過 `FUN_c006d530`
  與 `FUN_c006d630` 在兩個不同物件上推導出這個 byte 的，那段邏輯我沒有跟。
- G3／G5 當次的值。兩次都沒記，所以兩次都不能據此重新解釋。
- 如果其中一個選項真的是固定大小配置，它跟**變長**壓縮檔會不會衝突。
  這是個合理的疑慮，但這裡既不支持也不否定。

### 聚合關閉時是另一條路 —— 可能整個 blocker 就是一個選單設定（離線）

證據：[`build/ledger-aggregation-off-path-20260924.json`](../build/ledger-aggregation-off-path-20260924.json)。

#### 先確立:這個設定只有一個消費者

`FUN_c03a5050` 是**整個韌體裡唯一**讀 `settings[0x9C]` 的地方。方法：

- 設定區塊只能透過 `FUN_c0021c40(obj) = *(obj + 0x5C)` 取得；單例 `0xC30751D4`
  只在自己的存取器 `FUN_c0021c00` 裡被引用，所以所有存取都經過它。
- 303 個函式呼叫 `FUN_c0021c40`，其中 7 個函式體內提到 `+0x9c`；6 個讀的是**別的物件**
  （`FUN_c0017ac8` 的單例 `0xC3033834+0x18`，或無關結構）。只有 `FUN_c03a5050` 讀的是設定區塊。
- 另一次獨立掃描：整份反編裡 `+0x9c` 的 byte 存取共 19 個函式，除了
  `MenuItemMediaWriteMode::v3`（寫）與 `FUN_c03a5050`（讀）以外全是位移碰撞。

**所以「Media Write Mode」這個選單項目就是 CinemaDNG 的 SD 聚合開關,在這版韌體裡不做別的事。**

#### 聚合關閉時走的是完全不同的分支

`FUN_c063f380` 裡 `cVar5 = (vol[0x4828] == 0)`——**聚合關閉時 cVar5 = 1**。
`while (cVar5 == '\0')` 那個累積迴圈是聚合分支，關閉時整個跳過，走：

```c
local_6c = (**(code **)(vol + 0x4838))();        // 取得 descriptor arena
...
FUN_c063f048(&local_50);                         // 只建立「這一次」寫入的 range descriptors
uVar3 = FUN_c0646c60(vol, 4, ..., 5, lba, off, len, local_6c);   // 傳輸
(**(code **)(vol + 0x4848))();                   // ← 立刻歸還 descriptor arena
if ((int)uVar3 < 0) return uVar3;
```

`0x4838` 取得 / `0x4848` 歸還，這對由 `FUN_c063f140` 裡的同一對呼叫確認。

**對照聚合分支:它從不在這裡歸還 arena。** arena 被留在 `vol[0x484c]`，
一直到 `FUN_c063f140` 才 `(*vol[0x4848])()` 歸還並重新取得一個。

#### 推論 [I]

descriptor arena 裡放的是裝置要讀的實體指標。關閉路徑在傳輸呼叫的**下一行**就把它歸還；
若傳輸還在進行，那等於把 DMA 正在讀的結構交回去。而開啟路徑——傳輸依定義是延後的——
**不歸還**，整批期間都握著。兩條路的差別，剛好就是「一條同步、一條不同步」會產生的差別。

**這不是 [C] 而是 [I]:** `FUN_c0646c60` 理論上可以先把 descriptor 複製到裝置自有儲存
再返回，那樣歸還也是安全的。我沒有追到那一層。

#### 它同時解釋了 G3 與 G5

- **G3** 的 3,244,544 bytes / 372 µs = 8.7 GB/s。聚合開啟時 submit 只是把 range
  descriptor 接上去、**什麼都沒發出**，所以根本沒有傳輸需要花時間。
- **G5** 八幀累積成一批，直到批次 flush 前什麼都沒傳；那時單一 arena 只剩最後一幀的內容。
  於是每個檔案都拿到那份 payload、各自截到自己登記的長度——這**正是**量到的結果，
  包括第 4 幀是第 1 幀**乾淨的 1,024 bytes 短前綴**，而不是一次不同的 encode。

#### 如果成立,意味著什麼

**這個 blocker 可能是一個選單設定,不是記憶體問題。** 在非聚合的那個位置：

- **單一 arena 就是正確的。** 不需要 slot 陣列、不需要釋放通知、不需要 copy-back、不需要多記憶體。
- 批次算術的問題整個消失——沒有批次，壓縮幀 48 幀一批而不是 20.7 幀也就不再重要。

**代價是吞吐量。** 聚合存在必有原因，關掉它會改變每幀的寫入成本，24p 預算必須**重新量**，
不能假設。這可能才是真正的代價，而且目前完全未知。

#### 沒有確立的

- `FUN_c0646c60` 是不是同步的。上面是 `[I]`，不是追到的事實。
- 哪個選單位置對應哪個值。`MenuItemMediaWriteMode::v3` 是「某個 gating 項目的值為 0 →
  設 1，否則 →（本項目的值 == 1）」；gating 項目沒認出來，
  `CM_MediaWriteModeAj` / `CM_MediaWriteModeFix` 也沒解析成顯示標籤或 enum 值。
- **G3／G5 當時是哪個值。兩次都沒記錄**，所以上面的解釋與它們一致，但不是由它們證明的。
- 聚合關閉時的寫入吞吐量，因此也不知道壓縮錄影在那個位置是否還在預算內。

## 上機:`SetMediaWriteMode 2` — 被接受,但沒有效果 — 2026-09-24

證據：[ledger](../build/ledger-live-mediawritemode-2-20260924.json)。

| | 結果 |
|---|---|
| `menu SetMediaWriteMode 2` | **OK,讀回 2**——所以這個項目不只有 0/1 |
| `settings+0x9C` | 錄影前／中／後**始終是 1** |
| `manager+0x0D` | 始終是 1 |
| `manager+0x0C` | 錄影中 1、停止後 0 → **`FUN_c03a5050` 確實在錄影開始時跑了**，但它讀到的是 1 |
| flush 時間 | **368 µs**（對比 372 / 365 / 356）——寫入路徑沒有改變 |

**結論:shell 改不動 `MenuItemMediaWriteMode::v3` 讀的那個值。** `menu Set*` 寫的是別的
地方；v3 報出來的仍是 1，這也解釋了為什麼我手寫的 `settings[0x9C] = 0`
會在下一次錄影時被寫回 1。真要改這個設定，看來得走相機自己的選單 UI。

### 一次被抓到的假陽性 —— 值得記下來

設成 2 之後的**第一次**量測回報 `flush_elapsed_us = 57,994`。
3,244,544 bytes / 57,994 µs = **55.9 MB/s**，一個很真實的卡片速度，看起來
正是預測的「寫入變同步了」。

它是錯的：

- n = 1。接著兩次重跑都回報**一模一樣的 57,994**——因為 arm 在 cave 被佔用時
  靜默失敗了，錯誤訊息被 `tail -1` 截掉，我讀到的是同一筆舊狀態。
- 清乾淨 cave、並先驗證探針是 `not entered` / `flush_elapsed_us 0` 之後，
  乾淨的一次跑出 **368 µs**。
- 那一次唯一不同的地方：**只有它在錄影進行中做了 `mem_get`**，而且做了兩次。
  USB worker 與卡片 I/O 競爭是這台相機有記錄的已知風險。未經證實，但它是唯一的變因。

**教訓:每次跑之前必須驗證探針狀態是全新的,而且被量測的那段錄影期間不能有任何 USB 流量。**
如果我只跑一次就報告，這會是一個「關掉聚合讓寫入變同步」的錯誤結論——而且它會很有說服力。

### 仍然沒有確立

- `menu SetMediaWriteMode` 到底寫到哪裡，以及 v3 讀的值存在哪
- 從相機自己的選單 UI 改，會不會真的改變 `settings+0x9C`（**下一個測試**，需要手動操作）
- 這台相機到底能不能關掉 SD 聚合
- [`ledger-aggregation-off-path`](../build/ledger-aggregation-off-path-20260924.json)
  的推論仍然**完全未檢驗**——從來沒有真正進入非聚合狀態

相機已還原：選單值 1、設定格 1、hook 原值、未錄影，FlashValue 未動。

## 上機:試圖關掉聚合 — 2026-09-24（失敗,但原因已查明）

證據：[live](../build/ledger-live-mediawritemode-20260924.json)、
[gate 解析](../build/ledger-mediawritemode-gate-20260924.json)。

**結論:聚合沒關掉,所以
[ledger-aggregation-off-path](../build/ledger-aggregation-off-path-20260924.json)
的推論既沒被證實也沒被推翻——它根本沒被檢驗到。**

### 上機量到什麼

| | 結果 |
|---|---|
| `menu SetMediaWriteMode` | **1**（聚合位置,與 G3/G5 跑在這裡一致） |
| `menu SetMediaWriteMode 0` | 回 OK、讀回 0，**但 `settings+0x9C` 仍是 1** |
| 開關選單 | 那一格沒有更新 |
| 手動把 `settings+0x9C` 寫成 0 | **錄一次影之後自己變回 1** |
| flush 時間 | 365 / 356 µs（對比 9/23 的 372）——三次是同一個量測 |

順帶一個**真機確認**:`flush_arg1 = 0xC3540F94`，是 RAM 指標不是 0。
[`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md) §2 關於 movie cookie 的訂正
在硬體上成立，我原本「cookie 為 0」的讀法確實錯了。

建立的位址：CinemaDNG manager 單例 `0xC359BE4C`（`+0x0C` init、`+0x0D` 聚合旗標）；
設定區塊指標 `0xC3075230` → `0xC3074BE8`；Media Write Mode 那一格 `0xC3074C84`。

### 為什麼失敗 —— 我一開始把兩個項目搞反了

`MenuItemMediaWriteMode::v3` 透過 `_DAT_c31caa80` 的 vtable `+0x354` 取得一個項目。
`_DAT_c31caa80` 是 **MenuItemFactory**（typeinfo `MenuItemFactory_w71c1` @ `0xC07397A4`），
`+0x354` 是 `MenuItemFactory_w71c1::v212`，回傳 `factory + 0x1594`。

工廠建構子裡 `FUN_c00ab898(param_1 + 0x565, ...)` 建的就是它——`param_1` 是
`undefined4 *`，所以 `0x565` 個字 = `0x1594` bytes；而 `FUN_c00ab898` 設的 id 是 `0xFE`、
vtable 是 `&DAT_c07430b0`，**正是 MediaWriteMode 自己的 vtable**。

（隔壁 `param_1 + 0x56c` = `0x15B0` = v213 是 `MenuItemFilePrefixRule`。我一開始按位元組
把 `0x56c` 當成 MediaWriteMode，剛好差了一格。）

**所以沒有另一個 gating 項目,v3 查的是它自己。**
`MenuItemMediaWriteMode::v5`（vtable `+0x1C`）回傳 1，所以索引固定為 0，兩次讀同一個值：

```c
v = value(this, 0);
settings[0x9C] = (v == 0) ? 1 : (v == 1 ? 1 : 0);
```

| v | `settings[0x9C]` |
|---:|---:|
| 0 | 1 |
| 1 | 1 |
| **≥ 2** | **0** |

**0 和 1 給同一個結果。我設 0 是往錯的方向調。** 這精確解釋了「寫 0 之後又變回 1」。

### 待驗證的預測（需要相機,一行指令）

```
menu SetMediaWriteMode 2
```

- **被接受** → 下次錄影開始時 `settings+0x9C` 應變 0、`manager+0x0D` 變 0、
  `FUN_c03a5050` 不安裝聚合。屆時 `0xC03A5490` 的 flush 若遠大於 365 µs，
  那個 `[I]` 就成立。
- **被拒絕** → 這個項目只有 0/1，`settings[0x9C]` 永遠是 1，
  **這台相機根本關不掉 SD 聚合**。那也是決定性的答案，整條「關聚合」的路就此退場。

資源名有三個（`CM_MediaWriteMode`、`...Aj`、`...Fix`），和三個狀態一致，但不構成證明。

### 相機已還原

選單值 1、設定格 1、hook 原值、未錄影。全程沒有 `menu save`／`setting save`，
FlashValue 未動。**沒有跑 G5**——聚合開著時跑它只會重現已知失敗，為零新資訊寫壞一個 clip。

操作上的坑：`exact_flush_writer_probe.py restore` 只還原 hook 字組，cave 內容會留著，
第二次 arm 會被拒絕。清掉花了 145 次 `mem set`，其中 4 個字要重試才寫進去。
cave 是 bump 配置器、沒有釋放 API，claim 到重開機前都在。

### 下一步

離線能問的都問完了。現在最便宜的下一個事實是**一行唯讀 shell 指令**：

```
menu SetMediaWriteMode        # 不帶參數 = 讀取
```

它告訴我們 G3／G5 當時最可能跑在哪個位置。如果是聚合那一邊，
**在另一個位置重跑 G5 就是整個假說的直接檢驗**——而且不需要改任何程式碼，
現有的 `compress-sustained` 就是那個測試。

不列 clip 資料夾、不刪檔、不讀記憶體、不 arm 任何東西、不存設定。

**依使用者的長期指示,上機測試排到最後,而且要先提醒。這裡只是標出它是代價最低的那個,
沒有排程。**

純離線還能做的，價值已經明顯下降：

1. 追 `FUN_c0646c60` 到裝置層，把上面那個 `[I]` 變成 `[C]`。
2. 認出 `MenuItemMediaWriteMode::v3` 裡的 gating 項目，確定值對應。
3. COMPRESSION_PRECHECK §8 的 host prototype（與 buffer 無關）。

已經被這一節降級的：slot 陣列（若假說成立就不需要）、copy-back（同上，而且仍卡在容量）。
兩者都不該在那一行指令跑過之前再投入工作。

---

> **⚠ 資料遺失說明（2026-09-24）。** 我在編輯本檔時用
> `t.index('### 下一步')` 取到**檔尾**再整段取代，刪掉了該標題之後的全部內容
> （約 780 行）。這是我的錯誤，不是任何工具或流程造成的。
>
> **已從本次 session 的 transcript 救回**：以下 2026-09-16 的七個段落（238 行）。
>
> **未能救回**：2026-09-20 至 2026-09-23 的實作日誌段落，包括
> 「當前優先：精簡緩衝區寫入設計」「緩衝區設計審閱」「寫卡鏈完成，連續錄影卡在
> 緩衝區壽命」「G3 與 G2 實機通過，G4 標頭合約完成」「G1 partial」
> 工作包 2/4/5/6、「依空洞區使用規範重新設計」「G2 中止並改為重跑」
> 「尚未做的工作包項目」「相機狀態」「LIVE — first movie-path lossless encode,
> 2026-09-21」「Core-path pivot — 2026-09-21」「Binding-ops port milestone —
> 2026-09-20」。repo 裡沒有 git、bundle 早於本專案、transcript 只有片段。
>
> **證據本身沒有遺失**：那幾天的不可變證據全部在
> [`../build/`](../build/)（G2、G3、G4a、G4b、G5、camera-bitstream、
> live-20260921、core-encode-lifecycle 等 ledger），current status 在
> [`ROADMAP.md`](ROADMAP.md)，設計在 [`BUFFER_DESIGN.md`](BUFFER_DESIGN.md)、
> [`BUFFER_RESEARCH.md`](BUFFER_RESEARCH.md)、
> [`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md)、
> [`LIVE_TEST_PACKAGE.md`](LIVE_TEST_PACKAGE.md)、
> [`G4_WRITE_DESIGN.md`](G4_WRITE_DESIGN.md)、
> [`CAMERA_PAYLOAD_READBACK.md`](CAMERA_PAYLOAD_READBACK.md)。
> 失去的是敘事日誌，不是結論或量測。

## Native-call implementation milestone — 2026-09-16

Continued offline; no camera/USB, installation, commit, push or release.

- Added `fpSup/lossless/native/`: seven ARM32 C functions for private variable
  init/lookup/default-OFF registration/read/subscribe/canonical write/cancel.
  **23 tests** execute the compiled C into original native instructions, not
  just host mocks. Subscription replacement/removal is rejected before writes;
  independent review and regression passed. The call layer is not yet the
  complete `fpl_binding_ops` port.
- Shared strict ELF extractor passes **20 tests**. Exact native-call code is
  2690 bytes; test loads only verified relocation-free text into synthetic RX
  memory. No camera address is reserved and no deployable binary is produced.
- Lazy-loader probe passes **16 tests**. Actual selector is C05E82F1; first
  record call C05E834A. Cached root skips parsing. A nonzero parser result is
  not an error signal, and outer 0 is not sufficient success evidence.
- Choice-control probe passes **14 cases**. OFF/ON share one input widget;
  max=0 clamps the current value, and disabling new key events does not stop
  existing repeat events. Plan separate saved value/cursor/confirm permission;
  keep canonical restoration authoritative. No premature candidate change.
- Existing control/UI **32** and coordinator **30** tests were rerun and pass.

Reports: `build/native-variable-port-20260916.json`,
`build/native-page-boundary-20260916.json`,
`build/native-control-boundary-20260916.json`,
`build/native-layer-regression-20260916.json`.

Remaining implementation is native outer-loader failure containment, actual
callback-to-policy/permission/rendering wiring, serialized notification/source
event lifetime, and recording codec/header/writer/playback. The package is still
non-deployable. Ask before any camera session.

## Prior offline milestone — 2026-09-16

No camera or USB was used. Nothing was installed, committed, pushed or released.

- Default resource is now `pure-fixed-gated`: fixed 320-wide OFF/ON popup,
  no shared-width watcher, no stock sync request. Page 179725 bytes / 1538
  records / 214 objects; stock rows retained. Five runtime gates remain.
- `fpSup/lossless/binding/` coordinates private variable ownership, default OFF,
  explicit rejected-choice restoration, stale callbacks and safe retirement.
  Successful unsubscribe is not quiescence; exclusion must precede native pair
  freeing. A late native write or uncertain publication blocks ALL recording,
  including silent RAW fallback. Final repair redraw succeeds before unblocking.
- `fpSup/lossless/loader/` is a normalized, pinned reader-view lease; it is not
  an installed native parser adapter. It preserves private strings until all
  resource users are externally proven destroyed. Cached/partial/stale input
  is rejected rather than replayed.
- Canonical verification: control/UI **32**, binding **30**, menu **35**,
  fixed recipe **8**, reader lease **53 groups**, native binding probe **18**.
  All pass with no skipped cases. Host C/ARM compilation, sanitizers and bounded
  original-instruction emulation are distinct evidence, not camera testing.
- Evidence: `build/offline-integration-20260916.json`,
  `build/reader-lease-tests-20260916.json`,
  `build/native-binding-probe-20260916.json`,
  `build/fixed-popup-native-20260916.json`.
  New candidate: `build/mainb2-pure-fixed-20260916/`; old artifacts preserved.

Native page-selection/parse ABI, real variable/rendering ports, queue exclusion,
allocator/retained-resource lifetime and REC/codec/writer/playback integration
remain unfinished. No production readiness proof is supplied. No deployable
package exists; the user must be asked before any camera session.

The sections below retain the earlier baseline and host-format evidence.

## Implemented vs pending

- Implemented: freestanding control core, private state, guarded OFF/ON and REC
  transitions, frozen per-take mode, no mixed-format fallback and sticky errors.
- Implemented: UI lifecycle policy for MainB2/CINE, private owner/session/
  generation checks, explicit confirmation events and OFF/ON enabled-state
  calculation. A warm-reset session change rejects old callbacks even when
  owner addresses and generation numbers match. Actual native registration,
  event draining and session-token management are still adapter work.
- Implemented offline: a complete expanded MainB2 resource candidate with a
  fourth CINE row, literal Lossless RAW/OFF/ON and private references, using a
  generic two-choice MenuItem_Select donor. Existing rows remain byte-identical.
  The candidate is explicitly non-deployable and is not a displayed camera UI.
- Pending: native row installation, actual variable/rendering ports, REC interception,
  codec execution/unwind, persistent preference, writer/DNG integration and
  playback. The C core is not yet an installed camera menu switch.
- First target: FHD 1936×1090 RAW12 / 24000/1001 / SD, predictor 1, 512×368 tiles.
  This is not yet a validated sustained recording product.
- Future OG combinations must use actual producer descriptors, not labels or
  mode IDs; no such combination is currently approved.

## Native UI and merge boundary

Requested page: `UicGuiMenuB2` / `MainB2`. GUI page ID is 10; handler ID is 0x1F
(these are different namespaces). Attach `C05834D8`, detach `C0583538`.
Page-local binding would avoid replacing factory DC-crop/audio handlers, but
registering a callback alone does not construct a new visible menu row.
Full row/layout/variable ownership proof is required before installing a hook.

The requested layout is the three existing CINE rows followed by **Lossless RAW
OFF/ON**, not a new item inside recording settings. The page also contains
STILL-only rows; they must not be treated as free space. The initial Audio
`MenuItem_SelectJump` clone remains only a structural comparison. The preferred
candidate now uses MainY4's generic two-choice `MenuItem_Select`, avoiding the
Audio jump subtree. Its five ST_CableRelease references are rebound to the
private variable, and its labels/animations are replaced with literal text.
See `research/ui/MAINB2_ROW_EXTENSION.md` for reusable page structure evidence.

The fourth-row placement (y=243 after y=0/81/162) fits the serialized parent
height but is not yet a verified cursor/navigation or camera display result.
Adding the row expands the allocation header and object lookup budget; a
single-record byte replacement is insufficient. No deployable UI is emitted.

OpenGate UI owns shared hooks `C05E6400` (NBU), `C05E84D8` (NBR), `C05E5B58`
(strings). A second different branch at any of these addresses is incompatible;
never whitelist overlapping writes. If row construction requires shared
parsing, it needs a common dispatcher or an explicit merge refusal.

fp-Merge currently concatenates checked sections; it does not initialize
arbitrary new entrypoints or understand a feature-registration ABI. Neither
an unused code range nor a private module ID proves startup/merge compatibility.
No code cave, hook, global parser or loader entry is reserved by fpLossless yet.

## Offline validation

The new control/UI policy suite passes **31 unique tests**, executing the exact
C source on the host and compiling it for ARMv7 soft-float without FP/NEON.
This is not ARM emulation, a camera test, or proof that the new row is visible.
Independent review checked stale-session rejection and the explicit output
pointer ABI. The native UI parser and actual codec adapters remain separate
gates. The shared MainB2 audit tool additionally passes 15 tests with the exact
pinned firmware, including rejection of a same-size modified image. Evidence
is in `build/mainb2-audit-20260915.json` and `build/control-tests-20260915.txt`.

Shared audit: `research/ui/tools/native_ui_audit.py --seg0 <explicit seg0 path>`.
Its JSON has all deployment/navigation/private-binding readiness fields false.
It is not a fourth-row transform or an installable firmware file. A candidate
private-variable registration primitive (C05DB308) now passes 15 bounded
original-instruction tests with synthetic registry/RAM and explicit Lua/heap
substitutes. Its integer-call ABI and non-atomic failure publication are
confirmed; actual Lua, heap, timing, recovery and teardown remain pending.
Evidence: `build/native-variable-probe-20260915.json`.

The 18 component schemas used by the new row are independently checked by
`research/ui/tools/native_component_schema.py`: 14 original constructor-prefix
captures and four verified static argument windows, not 18 executed
constructors. Its 13 tests pass; evidence:
`build/component-schema-tests-20260915.json`. Drawable common fields and
five-byte string values are included, eliminating opaque property-body remaps.
Detailed donor and shared-page evidence is in `notes/NATIVE_ROW_DONOR.md`.

### Pure-select fourth-row resource candidate

Historical 2026-09-15 baseline: `fpSup/lossless/menu/` then defaulted
to `pure-select-gated`; both old profiles now remain explicit comparisons.
Artifacts: `build/mainb2-pure-select-20260915/` (page, private pool, manifest).
The page is 179826 bytes / 1540 records / 214 objects. Its new fourth CINE
row has 21 objects, literal Lossless RAW/OFF/ON, and a private binding. All
original row records are byte-identical; the only three modified stock records
are the allocation header, ModeChange and parent B2 child count.

The 26-test menu suite passes at the canonical path with no skips. It checks
typed and unaligned references, invalid masks, all original Audio bytes,
literal labels/animation keys, explicit binary choice bounds, precise external
animation allowlists, allocation reserves and overwrite refusal. An independent
rebuild produced identical page/pool bytes and verified source/tool/output
hashes. Evidence: `build/menu-tests-20260915.json`.

Six runtime gates remain: private row-state behavior, variable registration,
navigation, rendering, resource loader/lifetime and native allocation. The
`submenu_05` width entry is known to exist on MainB2, but full request dispatch
is not established; the candidate deliberately isolates that request. Native
registration's non-atomic failure paths also require recovery before use.
This candidate is **not installable**, does not enable recording compression,
and must not be included in an fp-Merge card. No camera or USB was used.

### FHD host-format trial

Canonical rerun: `build/host-trials/run-81xyojax/report.json`, alongside four new
compressed DNGs. All four pass independent LibRaw sample equality (2,110,240
samples each), non-layout tags/entries/values, nested metadata bytes and source
SHA checks. Existing builder/encoder source hashes were unchanged. This is a
host-format result, not camera encoding, playback or sustained recording.

| Fixture | Source bytes | Compressed bytes | Ratio |
| --- | ---: | ---: | ---: |
| A001_083 FHD f07 | 3244544 | 1261568 | 2.572:1 |
| pre-stage4 A001_001 f001 | 3244544 | 1329152 | 2.441:1 |
| pre-stage4 A001_002 f001 | 3244544 | 1398272 | 2.320:1 |
| stage4 A001_001 f249 | 3244544 | 1389056 | 2.336:1 |

The FHD-specific integration tools in `tools/` pass 11 additional TIFF guard
and no-overwrite tests. Explicit builder selection is required. The old
`research/slimRAW/mkcompressed.py` route was rejected on all four frames:
its intended zero-area insertion overlaps Exif MakerNote. Evidence is retained
in `build/legacy-header-rejection-20260915.json`; no DNG was generated by that
rejected run. It remains unmodified for comparison, not approved for metadata
preservation.

The separate `tools/mkcompressed_safe.py` keeps every original header byte
except the TIFF root pointer, appends the new IFD/tables at 78848, and starts
compressed data at 79872. **The 1024-byte header growth is not implemented in
the camera writer.** Pixel losslessness is not whole-file byte roundtrip;
12 stock non-pixel tail bytes are recorded by hash, not encoded as samples.
The four compression ratios are sample observations, not worst-case guarantees.

## Existing probe boundary

`fpSup/raw/lossless_codec` is newer than `research/imaging-hw/fhd_compression`.
The current probe suite passed 39 offline checks; the old research mirror's
default path still points to `research/fpSup` and fails after reorganization.
The mirror and other existing dirty files were not modified.

Live encode stays blocked: its old design allocates another 4 MiB rather than
consuming/freeing retained scratch, lacks bounded execution and stage-aware
unwind, and does not yet implement the complete producer/header gate. Do not
unlock it merely to make the menu appear functional.

No camera or USB access. Ask the user before the next camera session.

## Next integration gates

1. Bind the fixed-popup resource lease to proven native page selection/parse
   calls; verify rendering, cursor traversal, enabled state and page allocation.
   The offline resource candidate alone is not a runtime success.
2. Prove private variable registration/teardown, failure recovery and hook timing;
   establish single-owner UI injection compatible with future fp-Merge use.
3. Integrate safe header, REC/codec/writer cleanup and a playback strategy.
   Only after those gates, prepare a bounded camera test and ask the user first.
