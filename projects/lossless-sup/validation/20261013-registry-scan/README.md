# Registry 掃描終點＋格數公式：實作與上機（2026-10-13）

## 改了什麼（`fpSup/lossless`，修改前來源在 `before/`）

1. **原廠 registry 全表迴圈的終點跟著 active 格數**（`slot_patches.py` → `native/slot_patches.h`）。
   11 個 `ends` 站點原本固定改成 `#0xFE0`（1016 格）；現在由 `slot_patch_count(n)` 寫 `#(n*4)`，
   n=96 時寫回原廠字組。lookup 上界（`counts`）仍是 1016。
2. **格數公式**（`native/slot_capacity.[ch]`）：
   - 壓縮檔的規劃大小由 1 bit/sample 改為 2 bits/sample（FHD 鏡頭蓋最小檔 606 KB 即在此）。
   - 加 RAM 上限：在途幀不可能超過 MOVIE_REC_DNG RAW 池 742,520,320 B ÷ 每幀配置。
   - 不足時不再拒錄，改以 `frame_limit` 依檔數提前結算；64 MiB 門檻不變。
   - `card.c` 擴充模式的 `bulk_policy.frame_limit` 由 1016 改為公式值。

| 模式（12-bit ON、100 ms） | 舊格數 | 新格數 | 批次上限 |
|---|---:|---:|---:|
| FHD 29.97／59.94p | 404 | 232／236 | 111 |
| M12240 29.97／59.94／119.88／239.76p | 832／836／840／852 | 552／556／560／572 | 271 |
| OG3K 29.97p | 96 | 96 | 42 |

## 離線驗證

- `native.test_slot_capacity`：5 項，含獨立參考 540 組與「兩批＋到達＋餘裕放得下」。
- `test_slot_expansion`（實際 BIN 在 Unicorn 執行原廠迴圈）：18 項，新增
  `FUN_c0375900/C0375BE0/C0375DE8` 只讀 n 格、n=96 寫回原廠字組，以及改回 `#0xFE0` 的 mutation（會讀到 1016 格）。
  存檔 BIN 以 `FPL_SLOT_CANDIDATE` 重跑同樣 18 項通過（`candidate-exact-tests.log`）。
- `test_v3_lossless`、`test_card_emulation`、`test_bulk_native` 60 項通過；STOPFX 整合 6 項通過。
- native 全部 478 項中 25 項錯誤，全部在 `test_native_variable`（`BINDING` probe 模組載入失敗，與本次修改無關，未修）。

候選 `candidate/10LOSS.BIN`：81,760 B，SHA-256 `28773635a23059a077545030f1268b11ada30dea0d16df94ec8d82c5bd75d558`。

## 上機（M12240 1008×672 12-bit，SD UHS-II，ISO 6400）

只換 `10LOSS.BIN`。原卡檔（`3e96ed0c…`）與 `fe35400b` 只差 BIN 內保存的設定位元組；備份在 `deploy-candidate/`。
寫入 ACK 遺失，依既有程序未重送，完整讀回核對一致後才重開（boot 11850934）。

1.1–2.1 s 窗口的 CPU（`window_cpu.py`，與相機摘要差 <0.1%）：

| 錄影 | 版本 | 格數 | CPU | MRecMgr | FPLCODE | 幀 |
|---|---|---:|---:|---:|---:|---|
| A001_169 59.94p ON | 舊（`fe35400b`） | 836 | 65.3% | 14.4% | 3.2% | 91 RAW |
| A001_170 59.94p ON | 候選 | 556 | 64.9% | 14.3% | 3.6% | 92 RAW |
| A001_171 119.88p ON | 候選 | 580 | 94.9% | 23.9% | 6.7% | 196/196，全 RAW |
| A001_172 119.88p OFF | 候選 | 580 | 86.9% | 21.5% | 0.6% | 194/194 |

結論：

- **registry 掃描在這個條件下不是主要成本**：59.94p 新舊版幾乎相同。此前的靜態推論（補記 2）在 M12240 不成立；
  FHD 壓縮幀會讓在途幀變多，尚未在 FHD 驗證。
- 119.88p 正常錄完、正常停止，沒有重現上次的鎖死；只有一段，不能據此宣稱已修好。
- **M12240 每一幀都是 `no_benefit`**：壓縮輸出不小於 RAW 檔（1,095,168 B），全部寫 RAW。
  LOSS 在 119.88p 多出的約 8 個百分點（FPLCODE +6.1、MRecMgr +2.5）全花在不會被採用的壓縮上。
  引擎在 M12240 每幀拒絕（pattern 4）；主機同幀可壓 3.5:1，見文末補充。
- OFF 本身在 119.88p 已 87%，剩餘餘裕很小。

## 收尾

相機：CINE 待機、119.88p、LOSS ON（恢復原設定）、writer 閒置。**卡上留著候選 BIN**；要回復請用
`deploy-candidate/before-10LOSS.BIN`。未 commit、未發布。

## 補充：M12240 為何壓不小（同日）

- 抽回 A001_171 第 100 幀（`cand-120p-frames/000100.DNG`，平均 272.7，黑位 256，值域 180–339）。
- 主機 `research/slimRAW/mkcompressed.py`，同樣 512×336、4 tiles、predictor 1：1,095,168 → **311,909 B（3.51:1）**，
  LibRaw 解回與原檔逐像素相同（`host-512x336.DNG`）。資料本身很好壓。
- 相機最後一次壓縮工作（`last-job.json`）：`pattern=4`、`total=0`，即**引擎拒絕**（判定輸出放不進 1,016,832 B），
  不是壓完才發現變大。`hold.refused = hold.no_benefit = 150`。tile 表內容是錄後殘值，不採用。
- 同一引擎在 FHD 正常；9/26 縮小 geometry 也出現過同類拒絕。推測是 geometry 條件，而非硬體上限，尚未證實。
  FHD 高 1090 以 368 切有垂直補白；M12240 高 672 以 336 剛好整除，是目前最明顯的差異。
- 下一步：以 `tile_force` 試 512×352（有垂直補白）與 512×224（整除），各錄 2 s 看 `hold.compressed`。
  寫 LOSS 狀態區被權限擋下，待使用者同意。

## 後續（10/13 晚）

相機換成正式版 v0.2.0test 後，以 HS280 做的切法測試（`tile_trial.py`、`tile-*.json`）結果與拒絕閘門，
見 [20261013-refusal-gate](../20261013-refusal-gate/README.md)。`set_tile_force.py` 只適用本資料夾的候選版欄位表，
正式版的 `tile_force` 位置不同（+180224），請改用 `tile_trial.py`。
