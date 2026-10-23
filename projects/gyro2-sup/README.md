# Gyro2 sup（loader v3）

每張 CinemaDNG 帶自己那一幀的陀螺資料（FSG2，寫在 MakerNote 0x0200 的零尾），
由 fork 的 Gyroflow OFX 外掛讀取。設計見
[`../gyro-sup/notes/GYRO2_CAMERA_DESIGN.md`](../gyro-sup/notes/GYRO2_CAMERA_DESIGN.md)（§11 韌體、§12 實作）。

照 loader v3 從零寫（`../usb-shell-sup/notes/LOADER_V3.md`），不改也不遷移 Gyro1。
只**讀**用 fpSup 的 v3 工具（`fpSup/fp_usb_shell/v3/`：`make_sup`、測試框架、組譯器），不寫 fpSup。

## 現況（2026-10-15）：格式 v2，build 6 已上機驗證

build 6 不再修補 `C038C77C`。每幀的區塊改由 tag observer 在韌體的每幀通知（mode 3，`C038C700`，在 DMA 之前）寫入；tag 位置在模板序列化後的 mode 2 通知（`C0378F70`）就找好，每幀不解析 IFD。修補位置只剩水平儀和 Vd 兩處。

上機（59.94p FHD，lossless 開）：

| 片段 | 版本 | 長度 | 幀數 | 結果 |
|---|---|---|---|---|
| A001_060 | build 5 | 5 秒 | 282 | 每幀有 v2 區塊、首尾相接、無遺失 |
| A001_061 | build 5 | 35 秒 | 2,081 | 同上 |
| A001_066 | build 5 | 3 秒 | 162 | 同上 |
| A001_069 | build 6 | 5 秒 | 284 | 同上，`writer` = 6 |

- 表頭都是 0x14000，在上限 0x15400 以內。
- lossless：`tag_head` = 0x14000，表頭 DMA 拒絕 0 次。
- 外掛讀取正常。

hook 每幀耗時（量測版，TickTimer，兩段 3 秒）：

| | build 4（v1） | build 5 | build 6 |
|---|---|---|---|
| 一般幀中位數 | 1,544 µs | 95 µs | 94 µs |
| 開錄第一幀 | 17,000 µs | 600～701 µs | 381～391 µs |

`fetch_heads.py` 改在同一個程序裡連續抓，每張 34 ms（原本 0.6 秒）。

## build 5（同日）：格式 v2，模擬 37 測試全過

v2 改了四件事：
- **A1** 不再算 CRC。改成先清 magic、最後寫 magic。
- **A2** 不再帶鏡頭表。每幀改帶校正焦距（`0xC307CDF0`，4 B 降為 u16）；畸變用每張 DNG 自己的 `WarpRectilinear`。
- **A3** 感測器模式改存原始值：mode、hmax、寬、行數、binning。讀出時間和裁切範圍交給外掛計算。
- **A4** 不再寫進 0x200 零尾，改用自有 MakerNote tag `0x4653`。tag 由 tag observer（掛在 Subject `FUN_c00577f0`，開錄時 mode 0／type 3 觸發）加進 builder：
  - 大小按 `C00C9BD0` 的幀率算成 4 幀份，上限 4 KB。原因：每幀表頭空間固定 0x15400，lossless 的 tag 也要分用。
  - hook 每段只找一次 tag。
  - Subject 沒有空槽時整個 sup 放棄。

另外 **A5**：一幀該帶的樣本超過 tag 容量時（開錄的 250 筆回補、卡頓），這一幀先帶最舊的，之後幾幀補上，區塊仍然首尾相接。

外掛（`feature/cdng-makernote`）向下相容：沒有新 tag 時照舊掃零尾的 v1 區塊。研究紀錄在 session scratchpad 的 `a4_observer.md`、`a4_headerlen.md`、`a4_fps.md`。

## 前一版（2026-10-07）：Vd 計時版已上卡、開機確認（模擬 32 測試、突變 43/43）；錄影實測來自同設計的探針版（A001_012/016）。設計見筆記 §14

P0 探針（`src/p0_probe.S`）已在機身驗證寫入點，見下方 P0 紀錄。

| 檔案 | 內容 |
|---|---|
| `src/gyr2.S` | v3 sup。claim 表頭 DMA `C038C77C`、水平儀 `0xC050D4C8`（CHAIN）、Vd `0xC0125480`（EXCL，Thumb BLX）。entry：claim 水平儀和 Vd → 跳板 → 註冊 tag observer → 寫 `bl` → publish。observer：mode 0 加 MakerNote tag `0x4653`；mode 2 找 tag；mode 3 每幀讀 gbuf／ring，寫 FSG2 v2 kind 2（先清 magic、最後寫 magic），逐行 DCCMVAC + dsb |
| `src/p0_probe.S` | P0 探針（歷史） |
| `fsg2.py` | 主機端 FSG2 解碼（第三方讀法，對照外掛 `fsg2.rs`） |
| `build.py` | → `build/40GYR2.BIN`（v2：4,040 B，id `GYR2`，build 6；`20GYR2_VD.BIN` 為 v1 上機版）；核對 stock 字 = 映像 |
| `test_gyr2.py` | 真的 sloader 載入；真實 fp DNG 表頭（FHD、OG2K 最小零尾、OG3K120 移位的 MakerNote）跑 hook；與 v3 lossless 同卡 |
| `mutate.py` | 突變測試（`python3 -B mutate.py [名稱片段]` 可只跑部分） |
| `verify_probe.py` | 上機後檢查錄到的 DNG 序列 |
| `fetch_heads.py` | 從相機逐幀抓表頭（不 `dir` 片段資料夾） |
| `vd_report.py` | 片段的 Vd 週期、抖動、hook 落後量 |

```
python3 -B build.py
python3 -B -m unittest test_gyr2     # 38 tests
python3 -B mutate.py                 # all mutants must be caught
```

### 探針資料塊（64 B，零尾起點 + 64）
`'FSGP'`、版本 1、tag 管理器幀計數 `[r6+0x174]`、request 幀號 `[r5+0x10FC]`、TickTimer µs、
本段已寫幀數、零尾位移/長度、src/dst/len、boot id、圖樣 A0..AF。

### 模擬證實／不能證實
- 證實（模擬）：v3 claim/chain/跳板/journal 正確；過期 hook 會被修復後重掛；EXCL 擁有者存在時放棄且不寫；
  與 v3 lossless（`10LOSS.BIN`）同卡都載入、不共用位置——lossless 掛在 `C038BFF0`（存檔呼叫），
  在 Gyro2 的 `C038C77C`（表頭 DMA）之後；位置與獨立解析一致；暫存器、堆疊還原；壞模板跳過但 DMA 照做。
- 不能證實（要上機）：DMA 是否看到 clean 過的行；`[r6+0x174]`、`[r5+0x10FC]` 的實際語意；
  「RAW 完成」事件是否照幀序；lossless 掉幀時的行為；MovRec 任務內的耗時。

## 上機測試（P0）——**執行前先問使用者**（有其他 agent 在用相機）

1. 卡：`fpSup/fp_usb_shell/v3/build_v3.py --out CARD --sup build/40GYR2.BIN`（可加 `--shell`），
   開 lossless 版本再加 `10LOSS.BIN`；`deploy_v3.py CARD` 部署。
2. 錄短片：FHD 與 OG2K 各一段；再開 lossless 錄一段（DATA-）。
3. `python3 -B verify_probe.py <片段資料夾> <fps>`：每幀都有塊、計數與幀號逐幀 +1、位置不變、tick ≈ 幀間隔。
4. 看 `\fpSup\LOAD.LOG`：`40GYR2.BIN` LOADED。

### 上機結果（2026-10-06）
`A001_027`（59.94p，138 幀）、`A001_028`（29.97p，23 幀）、`A001_029`（同一開機第二段，30 幀）全部 PASS：
每幀都有塊、位置一致、DMA 帶進幀。tag 計數器每段從 3 開始逐幀 +1；request `+0x10FC` 是 0–95 循環槽位。
`A001_030`（lossless 開，54/55 幀被壓縮）也 PASS；完整壓縮幀從 lossless 的新根 IFD 走得到塊。
詳見設計筆記 §12.5。

### P1 上機結果（2026-10-06 18:00）
`A001_033`（64 幀）、`A001_034`（73 幀），FHD 29.97p、lossless ON：每幀有效 FSG2 kind 2 塊、樣本序號接續、每幀 83–84 筆。
外掛 `FP_CLIP_DIR=... cargo test real_fp_clip_dir -- --ignored` → gyroflow-core 5,481／6,232 筆、2,499.5 Hz。

### 動作測試（2026-10-06 18:06，OG3K + lossless）
`A001_036`（474 幀）：水平搖 → X、俯仰 → Y、傾斜 → Z，三軸對應正確；外掛 39,686 筆、2,499.5 Hz。
找到並修正「寫入位置停在 ring 結尾」被當越界的 bug（第 404 幀 n=0），修正版尚未部署。

### P2/P3 上機結果（2026-10-06 19:50）
`A001_040`（145 幀，lossless ON）：讀出 10.556 ms／模式 106（同 Gyro1）、鏡頭表 = LUMIX S 40/F2 機身表、水平儀約 45 次／秒（驅動發布 47.2 Hz）。
外掛 → gyroflow-core：讀出時間、逐幀鏡頭參數、水平儀（|a| ≈ g）都到位。
