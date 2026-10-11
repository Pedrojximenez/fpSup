# fpLossless 實機測試紀錄與後續門檻

## 當前上機 gate — 2026-09-30

**上機測試前先通知使用者，取得該輪明確授權後才執行。** 此文件及歷史測試均不構成授權。
當前進度與順序以 [PROGRESS §10](PROGRESS_20260930.md) 為準；下方是 9/27 及更早 runbook，
不直接沿用舊 handle／claim／命令或把舊版結果視為新版通過。

目前 `camera_ready=false`：跨幀來源持有、前幀→後幀的影像／metadata 對應、來源尾端與 release
尚未閉環。9/30 callback 的 raw status／end-position 是待驗診斷，不是容量根因的判定器。
driver 現已分開 processed steps 與實際 writeback，並無條件停用舊 arm。新增單工作槽 policy
有主機／ARM 離線測試，但沒有原生 adapter／可交付 BIN 或新的 live pass；不可用舊探針繞過。

後續先依 [SUP_BUILD_RULES.md](../../../fpSup/SUP_BUILD_RULES.md) 完成與修改範圍相符的離線驗證，
記錄建置命令、新輸出目錄、精確 source／binary hash、通過／失敗／未做項目及是否需更換 AutoRun。
通知中須說明測試目的、有限範圍與停止／復原方式；來源或 DMA／IRQ 所有權不明時不可逕行 free／重 arm。

## 9/27 及更早的測試紀錄

最後更新：2026-09-27（本輪只更新文件）  
狀態：G2/G3、C1 與單幀 C2 已有歷史實機證據；C3／硬體 bound 尚未成立。  
適用：SIGMA fp `w71c1`, Ver.5.02.0.V91；每輪須另存 source/binary hash，舊 git hash 不代表現行 dirty source。

**當前順序先看 [`CURRENT_DEVELOPMENT.md`](CURRENT_DEVELOPMENT.md)。** 下方 G2/G3 是舊輪次
的程序紀錄，不是要求重做。`bound-probe-two` 雖已存在，兩區所有權／回收與失敗測試仍未完整，
目前不把它列成可直接執行的上機命令。不得將五個 guards 完整、小輸出或 encode 拒絕判作 bound PASS。

> **每一階段都需要使用者另行明確授權。** 本文件不構成授權，也不得在未經同意下執行。
> §12.3：「每次只增加一個變因。」

---

## 0. 先決條件（所有階段共用）

### 0.1 歷史 incident，不是目前相機狀態

2026-09-21 session 結束時相機端 USB worker 在 flush 探針 armed 期間與卡片 I/O 互鎖：

- `fpsh ping` 回 `ERR`，`mem get` 回 `LIBUSB_ERROR_TIMEOUT moved=0/64`
- 主機 daemon 已重啟並重新取得 interface，相機端未恢復
- 另有一塊 **4 MiB scratch 未釋放**，handle `0x452B9000`、allocator `0xC3073A5C`
  （sustained 探針從未觸發，所以沒走到 free）

以上地址只屬於該次 session，不得拿來 free 或推測今天的狀態。USB 重接不保證相機 DRAM／
allocation 已清除；復原須另行授權並核對 boot、hook 與 ownership，不能把舊 handle 當新配置。

### 0.2 入場檢查

```sh
fpsh ping                      # 主機 daemon，不證明機身身分
fpsh version                   # 必須是 5.02.0.V91 / w71c1
fpsh status get app_current    # 必須是 2 (CINE)
fpsh mem get 0xC072F6F8,,0x4   # LOAD_DONE_US 非零，否則 cave claim 無法進行
fpsh mem get 0xC072E060,,0x4   # CAVE_BUMP 必須落在 0xC072E064..0xC072EFB4
```

`app_current` 不是 2 時**停止**。CINE/STILL 是實體撥桿，shell 無法切換
（`key STILLON`、`key CINESWON` 都只動設定不動 app），必須請使用者撥。

錄影設定必須是 FHD CinemaDNG RAW12 / 24000/1001 / SD。探針若看到其他 segment 形狀
應以 `ERR_KIND`／`ERR_LENGTH` 拒絕並自行還原；這不是對未知模式的整體安全保證。

### 0.3 絕對禁止

- **armed 期間不得執行 `getfile.py`、`putfile.py`、bulk-loader、`dump`、任何 template helper。**
  使用 `--placed` 後探針已不在 template 區，但 `callfn` 仍會用到 `0xC072F700`，
  且快取發佈本身就走 `callfn`——所以發佈必須在 arm **之前**完成，不可在 armed 期間呼叫。
- 不得 `dir \CINEMA\A001_nnn`、`delCinemaDng`、`deloneimg`、`delall`。
- 不得 `menu save`／`setting save`／`setting write`。
- **不得在高熵內容上執行未經 host 驗證的幾何**（見 §2.4）。

### 0.4 精確位址

| 用途 | 位址 | 原始值／說明 |
|---|---|---|
| codec hook site | `0xC0722AFC` | `0xEBFDE061`（BL → `0xC069AC88`） |
| codec context guard | `0xC0722AF0..0xC0722B04` | `E1A0100D E1A0000A E3A02002 EBFDE061 E28DD008 E8BD84F0` |
| flush hook site | `0xC03A5490` | `0xEB0BD652`（BL → `0xC069ADE0`） |
| flush context guard | `0xC03A5484..0xC03A54A0` | `E320F000 E1A01004 E28D0020 EB0BD652 E1A06000 E1A07001 E5DB300D E3530000` |
| cave bump | `0xC072E060` | arena `0xC072E064..0xC072EFB4`（3,920 B） |
| boot id | `0xC072F6F8` | `LOAD_DONE_US` |
| D-cache clean/invalidate | `0xC000E91C` | set/way，無參數 |
| I-cache invalidate | `0xC000EABC` | 無參數 |
| 微秒時鐘 | `0xC002B6E0` | 自由運行 1 MHz，32-bit 會繞回 |
| codec init/encode/size | `0xC05A6890` / `0xC05A6920` / `0xC05A6990` | |
| allocator get/free | `0xC001D038` / `0xC001D2B8` | |
| 24p frame budget | — | 41,708 µs |

---

## 1. 階段一（G3）：read-only exact final-flush

**這是第一個要跑的。** 它不呼叫 codec、不配置記憶體、不改 DNG，只觀察 writer 名單形狀
與 flush 時間。§12.3 把它排第一，因為它引入的變因最少。

### 1.1 目的

回答一個直接影響架構的問題：**flush 是否在本幀內同步完成？**
`FUN_c069ac88` 只登記 `{buffer, length}` 指標、不搬資料，名單最多 8 筆。若 flush 在
下一幀之前結束，一塊 scratch 就夠；若跨幀，注入壓縮輸出就需要雙緩衝。

### 1.2 進入條件

- §0.2 全部通過
- `exact_flush_writer_probe.py survey` 顯示 claim 目標區域為 clear
- codec 探針**未** armed（`0xC0722AFC` 讀回 `0xEBFDE061`）

### 1.3 程序

```sh
python3 exact_flush_writer_probe.py survey            # 唯讀
python3 exact_flush_writer_probe.py arm --placed      # claim + 發佈 + arm
# 錄影 2–3 秒後停止
python3 exact_flush_writer_probe.py status
python3 exact_flush_writer_probe.py restore           # 若 status 顯示仍 armed
```

`--placed` 會 claim `lossless.flush.code`(480 B) 與 `lossless.flush.state`(256 B)，
並在 arm 前依序呼叫 `0xC000E91C`、`0xC000EABC`。

### 1.4 預期證據

writer shape（`S_WRITER_*`、`S_HEAD`、`S_NODE_*`、`S_NODE_COUNT`）、`S_DNG_MAGIC`、
`S_SHAPE_FLAGS`、`S_T0`/`S_T1`（夾住 flush 呼叫）、64-bit 回傳 `S_RET_LO`/`S_RET_HI`、
`S_ENTERED`、`S_RESTORED`。

**通過條件**（G3）：shape 穩定；requested == finished；無 backlog 成長、漏完成、
雙重完成或 hook 殘留。

### 1.5 中止與復原

| 情況 | 動作 |
|---|---|
| arm 後 shell 無回應 | 拔插 USB。**這正是 2026-09-21 發生的事。** |
| 拔插無效 | 拔電池。RAM 全清，claim 全失效。 |
| `status` 顯示仍 armed | 跑 `restore`；它只接受本探針 armed 的字且會檢查周圍 context |
| hook 變成非預期值 | **不要**手動寫回。記錄該值後拔電池。 |

### 1.6 不得重試的不確定結果

- `S_ENTERED` 已設但 `S_DONE` 未設：探針進去了沒回來。**不得重新 arm**，
  拔電池後由新 boot 重來。
- flush 回傳值異常或 `S_NODE_COUNT` > 8：記錄後停止本階段，不進入階段二。

---

## 2. 階段二（G2）：corrected 512×368 encode-discard

**必須在階段一通過之後。** 引入的新變因：呼叫 codec。

### 2.1 當時為何重跑（G2 已於 9/23 留下證據）

2026-09-21 的所有量測都是 **512×512** tiles——`TILE_H` 宣告後從未接線。
当時產品目標 512×368 尚未在相機上跑過；9/23 G2 已補實測。而且舊 arena 只比 packed raster 多
848 bytes，在高熵內容下並不安全。兩者都已在 2026-09-23 離線修正。

### 2.2 進入條件

- 階段一通過
- `python3 single_frame_codec_probe.py encode-live --dry-run` 逐字顯示：

  ```text
  tile   : 512x368, predictor 1, 1936x1090
  layout : work [base,+0x3F0000), table +0x3F1000, temporary table +0x3F1400, allocation 0x400000
  bound  : worst case 3,957,888 B, capacity 4,128,768 B, margin 170,880 B (4.32%)
  ```

  壓縮 phase（`compress` / `compress-sustained`）多印一行 header，且 capacity 不同
  ——自有 header 與 payload 共用同一塊 arena：

  ```text
  header : 78,848 B copied per frame, payload at +0x13800
  bound  : worst case 3,957,888 B, capacity 4,048,896 B, margin 91,008 B (2.30%)
  ```

  這幾行由常數推導而非寫死（2026-09-23 修正：arena 搬家後該行仍印舊值一整天，
  而這正是實機進入條件會去讀的那行）。對不上就**停止**。

  上面的數字是 2026-09-24 的：arena 已從 `0x3E0000` 搬到 `0x3F0000`，上界由
  `13.9998` 浮點改為 `BOUND_BITS = 14` 的整數公式（3,957,832 → 3,957,888）。
  若手上的輸出仍印舊值，表示跑的不是現行版本。
- 離線測試全過（95 tests）
- flush 探針已 restore，`0xC03A5490` 讀回 `0xEB0BD652`

### 2.3 三段鏈（每段各一次錄影）

```sh
python3 single_frame_codec_probe.py preflight --placed   # PPWR
# 錄影 2 秒 → status，確認 power_preflight PASS
python3 single_frame_codec_probe.py scratch --placed     # ALOC，保留 4 MiB
# 錄影 2 秒 → status，確認 scratch_preflight PASS
python3 single_frame_codec_probe.py encode-live --placed # 接手、編碼、釋放
# 錄影 2 秒 → status，讀取結果
```

`status` 之後必須檢查 `hook_state`。**`--placed` 與 cache publication 至今沒有任何
live 驗證**，若行為異常，退回不加 `--placed` 的固定位址路徑（已有三次實機成功紀錄）。

### 2.4 場景 fixture 與風險分級

§12.3 要求「先低風險內容」。高熵**合成**資料只在 host 做，不上機。

| 順序 | 場景 | 預期 bits/sample | 風險 |
|---|---|---|---|
| 1 | 暗場（蓋鏡頭） | 低 | 最低 |
| 2 | 一般自然場景、正確曝光 | 中 | 低 |
| 3 | 高頻細節（織物、樹葉） | 中高 | 中 |
| 4 | 正確曝光高 ISO | 高 | 中高 |
| 5 | 快速 motion／scene cut | 變動 | 中高 |

**每一種場景都先確認 `max_compressed_bytes` 對 arena 仍有正 margin 才進入下一種。**
host 上界是 3,957,888 B。**非壓縮 phase** 的 capacity 是 4,128,768 B，margin
170,880 B（4.32%）；**壓縮 phase** 要扣掉 `OUT_OFF` 的 79,872 B 自有 header，
capacity 只有 4,048,896 B，margin 91,008 B（2.30%）。用錯那一個，就是裝置端
`sum_sizes` 在 2026-09-24 之前犯的錯。
**任何一次 `compressed_bytes` 超過上界，立即停止**——那代表相機的 Huffman 表與
模型不符，上界必須重算。

### 2.5 量測與通過條件

量測：`init_return`、`encode_return`、`size_return`、wrapper total、12 個 tile sizes、
總 bytes、ratio、guards、cleanup、engine idle。

通過（G2）：所有 fixture 以 512×368 / predictor 1 成功；**tile sum 與 total 相符**；
零 guard 或 source mismatch；engine 回 idle；output bound 有正 margin。

### 2.6 已知會失敗的檢查（這是好事）

`source_dng_byte_identical` 這個宣稱已被撤回。探針只比對 4 個取樣字加 segment length
（16 / 3,244,544 bytes）。**G2 不會產生完整 source hash**；那需要 source ownership，
屬於後續 gate。證據欄位必須寫 `sampled source markers unchanged`。

### 2.7 中止與復原

| 情況 | 動作 |
|---|---|
| `error != 0` | 停止。記錄 error code 與 stage。不重試。 |
| `encode_entered=1` 且 `encode_return != 1` | **4 MiB 會被刻意保留**（codec 可能仍持有 DMA）。拔電池回收。不得手動 free。 |
| guard 被破壞 | 區塊不編碼也不釋放。拔電池。**重算 output bound 後才可再試。** |
| 相機凍結 | 拔插 USB → 拔電池 |
| 靜態拍攝壓縮壞掉（照片變大） | 2026-08-30 發生過。拔電池即復原。 |

### 2.8 不得重試的不確定結果

- codec 已進入而結果不明：**保留 scratch、sticky-disable、要求 power cycle**。
  不得 free、不得 retry（ROADMAP §5.4）。
- `frames_done` 與 hook 進入次數不一致：記錄後停止。

---

## 3. 每階段結束後

用 [`tools/evidence_ledger.py`](../tools/evidence_ledger.py) 產生條目：

```sh
python3 tools/evidence_ledger.py spec.json --out build/ledger-<stage>-<date>.json
```

`explicitly_not_established` 不得為空，generator 會拒絕。已存在的檔案不會被覆寫。
**歷史證據不回寫**（§13）。

---

## 3.5 階段 C1／C2（copy-back）：9/26 已執行，9/27 訂正門檻

證據：[C1](../build/ledger-c1-frame-survey-20260926.json)、[C2](../build/ledger-c2-copyback-20260926.json)。
以下命令保留為程序參考，不是當前已批准的自動執行流程；任何新一輪都要重新核對配置、版本及授權。

**本輪從上一次上機學到的兩條硬規則：**

1. **每次 arm 之後、錄影之前,先確認探針狀態是全新的。**
   `status` 必須顯示 `entered → not entered` 且計時欄位為 0。
   `restore` **只還原 hook 字組,不清 cave**；cave 沒清時 arm 會**靜默失敗**，
   於是讀到的是上一次的舊資料。2026-09-24 就是這樣得出一個 57,994 µs 的假陽性。
2. **被量測的那段錄影期間不得有任何 USB 流量。** 不 `mem get`、不 `status`、
   不 `menu`。唯一的例外是 `key MOVON/MOVOFF` 本身。
   那次假陽性唯一與其他次不同的地方，就是它在錄影中做了兩次 `mem get`。

### 3.5.1 階段 C1：frame 引用普查（唯讀,先做這個）

**目的：** 排查 copy-back 的 clone 共享風險。copy-back 只覆寫原 `seg` 交付範圍，**不是整塊 allocation**；
而 clone **共用**那個指標（`FUN_c0373dd0` 抄 `+0x68..+0x128`）。
所以要知道 writer 要消費它時，那塊 buffer 有幾個持有者。

**風險：** 唯讀。不跑 codec、不配置、不寫 frame、不寫 DNG，探針自我還原。

```sh
python3 exact_flush_writer_probe.py survey      # code/state 必須 clear
python3 exact_flush_writer_probe.py arm
python3 exact_flush_writer_probe.py status      # 必須 "not entered"
#   錄影約 3 秒（期間不下任何其他指令）
python3 exact_flush_writer_probe.py status
```

**同模式實測後的檢查條件：**

| 欄位 | 必須是 | 意義 |
|---|---|---|
| `frame_refcount` | 0 | clone 引用數為零，不是「持有者總數為 1」 |
| `frame_clones_made` | 0 | 沒有 clone 被做出來 |
| `frame_owner_id` | `0xFFFFFFFF` | 這個 frame 是 owner，不是 clone |
| buffer 關係 | `seg[0] = frame_buffer + 0x2000` | `frame_buffer_is_seg0=0` 是此路徑的正常結果；pixel 起點亦須吻合 |

**任何一項不成立就先停止該試驗並核對。** 這些是當前 profile 的門檻，不把變更解讀成必然可寫。
兩次取樣支持本次 clone 路徑判讀，不代表所有模式、每一幀或全部潛在讀者都已排除。

順便記下 `frame_kind`（本次實測 1）與 `frame_clones_requested`（本次實測 1）。
請求 1 而做出 0，代表那條 clone 路徑在 movie 上沒有被走到——這正是靜態讀不出來的部分。

### 3.5.2 階段 C2：單幀 copy-back（破壞性）

**進入條件：** 訂正後的 C1 條件、scratch ownership／容量、當幀 header 與版本均通過；另獲上機授權。

```sh
python3 single_frame_codec_probe.py copy-back --reference-frame <stock.DNG>
#   錄影一小段（期間不下任何其他指令）
python3 single_frame_codec_probe.py status
```

**狀態必須顯示：**

| 欄位 | 意義 |
|---|---|
| `stage` = 8 | 完成；11/12 只是中途標記，不作最終判決 |
| `fit` = 1 | 已 copy-back；0 為未複製、原幀留 RAW，僅是研究探針 mixed 結果 |
| `file_bytes` | `0x13800 + 壓縮 bytes` |
| `copy_bytes` | `file_bytes` 向上取到 16 的倍數 |
| `len_after` | 等於 `file_bytes` |
| `error` = 0 | |

**然後把那一幀讀回來驗證**（hook 已自我還原之後才做，armed 期間不得 getfile）：

```sh
python3 getfile.py '\CINEMA\A001_nnn\A001_nnn_..._000001.DNG' frame.DNG --size <file_bytes>
python3 /Users/dido/Developer.localized/SIGMAfp_re/projects/lossless-sup/tools/verify_compressed_dng.py frame.DNG \
        --stock <stock-neighbour.DNG> --control <second-stock-neighbour.DNG> --decode
```

`verify_compressed_dng.py` 會檢查：root pointer 已提交、Compression=7、
strip tags 已移除、12 個 tile 的宣告位移與實際 SOI 相符、每個 tile 以 SOI+SOF3 開頭
有合法 EOI（其後只允許已宣告的零 padding）、**檔案長度正好等於 79,872 + Σtile counts**，
以及原始 header 的保留。若有同幀原始 header，才可要求第 8..78,848 bytes 逐 byte 相同。

用鄰幀時加 stock/control，列出所有差異位置，要求落在兩張 stock 的變動位置內；
這不是任意誤差容忍，也不是同幀原始像素／完整 metadata 語意的證明。

**計時訂正：** `t1 - t0` 只有 encode，C2 的 13,753 µs 不含 copy。
現行 source 已加入 `t_after`；`t_after - t1` 包含 size/header/copy 到該取樣點的後處理，
不是單獨 memcpy 時間，也不含之後的 `seg[1]` 提交與原 writer。它尚未取得實機結果。
完整 frame 預算仍要另外量 wrapper 全程；G4a 是反方向，不能代替。23.976 約 41,708 µs。

### 3.5.3 階段 C3：連續八幀

**C2 單幀已通過檔案驗證，但 copy 成本、容量與連續生命週期仍須先補。**
八幀須逐幀匹配記錄、長度、metadata、內容及讀回檔案；不以「每張 hash 必不同」作必要條件，
靜態場景可能相同。亦須觀察原生 aggregation 回收進度，八幀不等於 sustained。

尚未實作（目前沒有 `copy-back-sustained` 命令）。先完成 CURRENT_DEVELOPMENT 的前置。

---

## 4. 本包尚未涵蓋

- G4 與 C2 單幀寫卡已有紀錄；尚缺 C3／長跑、完整 copy 成本與一般內容容量證明。
- 完整 source hash / source ownership。
- async pipeline、mixed compression、VFR：G7 以後。
