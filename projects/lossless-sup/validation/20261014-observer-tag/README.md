# 2026-10-14 LOSS 改用 observer＋私有 tag 預放壓縮 IFD：開工前查證

方向（使用者，2026-10-14）：照 Gyro2 的最新研究，開錄時用原廠 observer 在檔頭模板裡註冊 LOSS 自己的 tag，
壓縮 IFD 預先放在裡面，隨原廠 DMA 進每一幀；完成時只寫 25 字。LOSS 與 Gyro2 **各用自己的 tag**（使用者同意）。
韌體背景：`research/firmware/notes/cinemadng-header/`（Gyro2 工作階段的三份報告）。

本輪只做查證：靜態讀反編譯＋一次相機唯讀記憶體讀取。沒有改程式、沒有建置、沒有寫相機。

## 1. sup 能不能在 mode 0 通知時加 tag —— 靜態看可以 [V]，實際呼叫未驗證

- 開錄 `FUN_c0378a50` → `FUN_c038a138` → `FUN_c00558f8` 建 DataPool 後，`FUN_c00559f0(Subject 0xC31AC4EC, 0, 3, dp)` 通知 9 個 slot
  （`FUN_c0055fe0`：逐一呼叫 `obs->vt+0xC(obs, dp)`，**回 0 會被移除**）。
- 原廠 lens observer 的加 tag 寫法（`FUN_c0364020`，blk_c03.c:67709）：
  `builder = dp->vt+0x2C(dp)`；`ev = dp->vt+0x40(dp)`，`ev[0] == 0`（mode 0）才加；
  每個 tag 一次 `FUN_c00ba378(builder, ifd, tag, type, count, &value)`（例：`FUN_c0364810` → `(b, 2, 0x9206, 5, 1, &v)`）。
- `FUN_c00ba378` 只做 `FUN_c00bfdc0(type,count)` → `FUN_c00bd340` → `FUN_c00ba290(builder, ifd, 0, tag, type, …)`，
  沒有呼叫端限制。LOSS 照同樣形狀呼叫即可：`ifd 0`（IFD0），私有 tag，type 7 UNDEFINED，count = 預留位元組。
- 加已存在的 tag 會覆寫（`TiffIfd::v5`，見 HDR_PRODUCERS §0-4）：tag 號要避開原廠與 Gyro2。
- 拍照也會走 observer：handler 只在 LOSS 自己的 REC hook（`C03A33C8`，事件 3／0x23）標記「本段要壓縮」後、mode 0 時才加，
  用一次就清掉。REC hook 早於 `FUN_c0378a50` 是推論 [I]（前者在 CameraFunction 派送，後者在 request kind 1 的處理裡）。

## 2. observer 空位 —— 相機上確認 [V]

`mem_get(0xC31AC4EC, 9)`（2026-10-14，相機上是 writer-guard 候選版 LOSS）：

| slot | 物件 | vptr | |
|---|---|---|---|
| 0 | C3498D5C | C0B960D8 | lens |
| 1 | C34142C0 | C096EA1C | 色彩／DNG（`FUN_c02b9010`） |
| 2 | C3206868 | C0918348 | AF |
| 3 | C320447C | C0917A30 | AE |
| 4 | C3409C7C | C096BFCC | AWB |
| 5 | C31CC7E4 | C074A528 | 第 6 個（報告推為 GPS，未核對） |
| 6–8 | 0 | | **空** |

3 格空，LOSS＋Gyro2 各用一格後剩 1 格。**`FUN_c00d2958` 沒有空位時直接 assert（`FUN_c0011100`）＝當機**：
sup 註冊前必須自己讀 9 格確認有空位，沒有就不註冊、整個功能退回現行做法。

## 3. LOSS 哪裡假設檔頭 0x13400 —— 要改 6 處 [V]

原廠框架：frame `+0x128` 檔頭保留 = **0x15400**（kind 1），raster = handle + 0x15400，DMA 目的地 = raster − `[req+0x14C]`。
所以檔頭變長時檔案起點往前移，**上限是 0x15400**（現在 0x13400，剩 8 KB；有 LinearizationTable 的模式已用掉 1 KB）。
這 8 KB 是所有加 tag 的 sup 共用的預算，要在建置／執行期檢查。

| 位置 | 現況 | 要改成 |
|---|---|---|
| `frame_hold.c:38-40,193` | `FRAME_HEADER == 0x13400` 才接手，否則該幀走 RAW | 讀 `frame+0x14C`；檔案位移 = 0x15400 − 檔頭長 |
| `frame_hold.c:242,290,399` | `PIXELS_IN_FILE` 常數 | 同上，每段算一次 |
| `trailer.h:26`、`trailer.c:50,53,73,143,250,274,284` | `FPL_TRAILER_PIXELS 0x13400` | 每段的檔頭長 |
| `card.c:61,498` | 批次大小用 `FPL_FILE_HEAD` | 每段的檔頭長 |
| `slot_capacity.h:14` | `FPL_SLOT_HEADER_BYTES` | 同上（只在擴充槽建置） |
| `play_decode.c` | 沒有寫死 | 不用改，但要上機確認原廠回放與 LOSS 回放 |

現況的好處：檔頭不是 0x13400 時 LOSS 不會出錯，只是整段不壓縮（安全退回）。

## 還沒驗證、上機前要做的

1. Unicorn：以真實 `FUN_c00ba378`／序列化（`C06A4C48`）跑一次 mode 0 加 tag，看檔頭長度與 tag 位移。
2. 原廠 DMA `C00FBB90` 是否自己做 cache 維護（LOSS 只在開錄寫一次模板，保險起見自己 clean 那一段）。
3. 每幀原廠會改 IFD0 的哪些 **inline** 值（≤4 B 存在 entry 內的）：若有，壓縮 IFD 那份要在 LOSS observer（每幀，排在原廠 observer 之後、DMA 之前）同步。
4. 保留 MN 0x33（少了會在錄影中 assert）。

---

# 實作（2026-10-15，離線完成，未上機）

基底：`fpSup/lossless` = 正式版＋快取別名－64 MiB 調整（`../20261014-no-bulk`）。

## 流程

| 時點 | 誰 | 做什麼 |
|---|---|---|
| 載入 | `card.S` 最後（所有 hook 武裝之後） | `fpl_card_observer`：照 `FUN_c00d2958` 的做法（關中斷、第一個空格）把 observer 放進 Subject `0xC31AC4EC`；**不呼叫它**（滿了會 assert）。滿了就不註冊，整機退回尾表 |
| REC（`C03A33C8`） | `fpl_card_rec` | 每段先 `tag_live = 0`；壓縮段被接受後 `tag_want = 1` |
| 模板建構 mode 0 | `obs_shim` → `fpl_card_observe` | `tag_want` 時對 builder（DataPool vt+0x2C）呼叫 `FUN_c00ba378(b, 0, 0xFD4C, 7, 0xA00, zeros)` |
| 序列化後 mode 2（`C0378F70`） | 同上 | `fpl_header_tag_prepare`：在模板（`[0xC358DBA8]`，長度 `[0xC358DBA4]`）裡 tag 的值區建壓縮 IFD＋兩張表的位置；clean D-cache；兩份輪替後發布 `tag_live`（前有 `dmb`） |
| 每幀 mode 3（`C038C700`，DMA 前） | 同上 | `fpl_header_tag_sync`：主 IFD 的 inline 值（≤4 B）有變才寫進副本，寫了才 clean |
| 完成（`C03A5490`，送出前） | `fpl_flush_before` | `c->head == tag->head` 且幀檔頭確實是那份模板 → `fpl_header_tag_complete`：tile 寬高、兩個表 entry、兩張表，**最後**根指標；否則照舊寫尾表（像素起點改用該幀的檔頭長） |

## 改動檔案

- 新：`native/header_tag.c/h`、`native/header_tag_fixture.c`、`native/test_header_tag.py`。
- `native/trailer.c/h`：像素起點改參數 `pixels`（上限 0x15400）。
- `native/frame_hold.c/h`：檔頭長度改讀 `frame+0x14C`（≥0x400、≤0x15400、4 對齊，否則不接手），檔案起點 = handle + 0x15400 − head；commit 記 `head`。
- `native/flush_site.c/h`：先試 tag 路徑，再退尾表；新計數 `flush.tagged`。
- `native/card.c`、`native/card.S`：observer、shim、註冊；`build_card.py`：UNITS／ENTRIES／FIELDS。
- 測試：`test_frame_hold.py`（fixture 檔頭長可設；加長檔頭端到端；不合法檔頭不接手）、`test_card_emulation.py`（observer 6 項）。

## 測試

| 套件 | 結果 |
|---|---|
| test_header_tag（真實 FHD 幀，LibRaw 解碼＝原廠樣本；RAW 幀仍可解；只寫 tile 欄位與表、根指標最後；同步；拒絕情況；10 個變異） | 16 OK |
| test_frame_hold | 153 OK |
| test_trailer | OK |
| test_card_emulation（含 observer：註冊在最後、清單滿不動、加 tag／建 IFD／同步、未接受的段不碰、無 tag 的模板退回、新段清掉） | 32 OK |
| test_v3_lossless | 23 OK |
| test_codec_job、test_play_decode | OK |
| card 變異：拿掉 REC 重置、不看 `tag_want`、shim 回 0 | 都被抓到 |

建置：`build-plain/10LOSS.BIN` = `6990128d25daed1c0ab9cd555b133c1b169c8919b1f31e1a18ab3e29cea2cd86`。

## 上機要確認的（離線證明不了）

1. REC hook（`C03A33C8`）是否早於模板建構：看 `tag_added`；若 `tag_mode0` 增加而 `tag_added` 為 0，就是晚了。
2. `FUN_c00ba378` 真的把 tag 加進 IFD0，序列化後檔頭變長：看 `tag_head`（預期 0x13400 → 約 0x13C00）、`tag_prepared`。
3. 原廠 DMA 帶過去的是我們 clean 過的內容：看 `flush.tagged` 與抽幀主機解碼。
4. 機內回放（根指標不是 8 就讀壓縮 IFD，表在檔頭內）、Resolve。
5. CPU：FHD 59.94p 與目前版本（`47b15e07…`，尾表約 394 µs／幀）比較。

私有 tag 號 `0xFD4C` 已被 LOSS 使用，Gyro2 加自己的 tag 時要避開。

---

# 修訂（2026-10-15，使用者：「拿掉尾表，tag 改小」）

- **尾表整個移除**：刪 `trailer.c/h`、`trailer_fixture.c`、`test_trailer.py`（舊版在 `../20261014-step1-release/work-backup/`）。
  是否壓縮在接手時決定：`frame_hold` 新增 `require_head`，REC 時設 0xFFFFFFFF（不接手），
  IFD 準備好才設成該模板的長度；長度不同的幀不接手（`refused_by[7]`），照原樣存 RAW。
  flush 只走 tag 路徑；對不上記 `flush.tag_failed`（舊名 trailer_failed）。沒有 observer 或 tag 準備失敗 → 整段 RAW。
- **tag 依該段切塊數配置**：`FPL_HEADER_TAG_BYTES(tiles)` = IFD 上限 80 entry＋該段切塊表，FHD 12 塊 = 1,068 B
  （原 2,560 B）。實際 FHD 檔頭預期 0x13400 → 0x13800（每幀 +1 KiB；原本會到 0x14000）。
- `frame_hold` 的 `file_bytes` 不再加尾表保留量；測試的「沒省空間」payload 改為 0x46400。

測試：header_tag 17、frame_hold 157（新增：模板不符不接手）、card_emulation＋v3 55、codec_job、play_decode、tile_grid 全部 OK。
建置：`build-plain/10LOSS.BIN` = `e82c1e12d52841469159b2aa626a9b5faed98dc4401e3a3cb1bfea7683ebbcb9`（取代 `6990128d…`）。

---

# 部署（2026-10-15）

- 部署檔：`deploy-on/fpSup/10LOSS.BIN` = `e82c1e12…` 把設定紀錄（blob +2876，16 B）改成 ON，
  `75b02a9bec44c0b34b19bc46fbb832ecd5ada35411c6f8bbdc6cc27a2734c301`（75,296 B）。原始碼預設仍是 OFF。
- 部署前卡上 `\fpSup` 只有 `LOADER.BIN`、`00SHELL.BIN`、`UI\`、`LOAD.LOG`（10/14 05:01 在 Mac 上寫的卡，沒有 STOPFX、沒有舊 LOSS）。
  只新增 `\fpSup\10LOSS.BIN`（`deploy_v3.py --only`，讀回一致），AutoRun 未動。`deploy-on.log`。
- USB `reboot`，11.7 s 回應。`LOAD-after-deploy.LOG`：`10LOSS.BIN` LOADED（block 0x45147A00），10 個 site 武裝。
- Subject `0xC31AC4EC`：原廠 6 格不變，第 7 格 = `0xC5186CBC`（LOSS 的 observer，快取別名）。
- `card_status.py`：`settings_on 1`、`observer_slot 7`、`observer_calls 0`（還沒錄影）。
- 修了 `card_status.py`：換回認得快取別名常駐基底的版本（第 1 步時漏換），欄位改名 `flush.tag_failed`。

---

# 第一次上機（2026-10-15 00:57，使用者錄兩段，A001_001／A001_002）

計數（`status-take1.txt`）：`rec_admitted 2`、`tag_mode0 2`、`tag_added 2`（`tag_add_result 1`）、`tag_prepared 2`、失敗 0；
**`tag_head` = 0x13800**（預測值）；`tag_bytes 1068`、`tag_tiles 12`；`hold.require_head 0x13800`。
`hold.compressed 655`＋`hold_b 1` = `flush.applied 656`，`flush.tag_failed 0`、`length_mismatch 0`；`tag_syncs 658`、`tag_sync_writes 0`
（這段沒有 inline 值在變）。`stops 2`、`finishes 2`。

→ 上機前的未知全部成立：REC hook 早於模板建構；`FUN_c00ba378` 把 tag 加進 IFD0、檔頭長度 +1 KiB；
原廠 DMA 帶進每幀的是我們準備好的 IFD。

取回 A001_002（`A001_002-frames/`，`validation.txt`）：

| 幀 | 大小 | 根指標 | 結果 |
|---|---|---|---|
| 1 | 3,245,568（RAW，0x13800＋raster） | 8 | IFD0 59 entry，含 tag 0xFD4C（UNDEFINED×1068，值在 0x4130），StripOffsets 0x13800；LibRaw 1090×1936 |
| 2、3 | 1,102,848 | 0x4130 | 壓縮 IFD 60 entry、Compression 7、512×368、12 tiles，第 1 塊在 0x13800，最後一塊結束＝檔尾；IFD 在 tag 的值區內；LibRaw 1090×1936 |
| 657（最後一幀，000658 不存在） | 1,069,056 | 0x4130 | 同上；LibRaw 1090×1936 |

與第 1 幀（RAW）比較的平均絕對差 1.5–2.9 DN（不同幀的雜訊量級，暗場 256–533）。

- 原廠把 tag 的值放在 IFD0 值區前段（0x4130），不在檔頭尾端；`fpl_header_tag_prepare` 本來就靠解析位置，沒有影響。
- 657 幀沒有在 94 幀停：這段壓縮後約 1.1 MB／幀（原廠的 34%），64 MiB 一批約 60 檔 < 94。畫面更好壓時仍可能碰到。
- A001_001：用 `A001_001_20261015_00000{1,2}.DNG` 開檔失敗，內容未確認（沒有 `dir` 片段資料夾）；壓縮計數全屬 A001_002。

未做：CPU 量測、機內回放、Resolve。

## DaVinci Resolve（2026-10-15，使用者）

tag 版錄的片段（卡上 `75b02a9b…` ON，含 FCAP 那段）在 DaVinci Resolve **可以播放**。（使用者回報，未記錄 Resolve 版本與檢查細節。）
