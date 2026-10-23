# 2026-10-13: 預先準備的壓縮 IFD（共用檔頭，逐項改善第 2 步，已上機、採用）

基於第 1 步（[快取別名](../20261013-cached-alias/README.md)）。

## 依據

同一段錄影內，主 IFD 的 inline 值逐幀不變。逐幀變化的只有 IFD 外部資料：TimeCodes 51043、RawDataUniqueID 50781，
有時還有 BlackLevel 50714。壓縮 IFD 本來就共用這些外部資料。比對過的實拍：A001_250（FHD）、M12240 30p 的第 1 與 169 幀。

## 做法（`native/trailer.c` 的 `fpl_trailer_write_prepared`，由 `flush_site.c` 呼叫）

- 狀態裡有一份快照，涵蓋檔頭到主 IFD 結尾，以及由它建出的壓縮 IFD 影像。兩者都在快取記憶體。
- 每幀依序：
  1. 用對齊的字讀取該幀檔頭的同一段（FHD 約 178 字），和快照比對。最後一個字只比屬於 IFD 的位元組。
  2. 不同，或切塊數、尺寸改變 → 從剛讀到的內容重建。建表檢查沿用 `fpl_trailer_plan`。
  3. 在影像中填入本幀的 TileOffsets／TileByteCounts 位置和兩張表。
  4. 在 1 KiB 對齊的 `ifd_at` 以整字寫出（約 203 字），**最後**才寫根指標。
- 寫出的位元組和 `fpl_trailer_write_all` 相同，最多在最後一張表之後多出 3 個 0。這些位元組在 `capacity` 內，也在 writer 本來就會補齊的 1 KiB 範圍內。
- 做不到時一律交回原本的 `fpl_trailer_write_all`，結果和正式版相同。包括：主 IFD 超過快照上限（132 entries）、`ifd_at` 未對齊、空間不夠寫最後一個整字、切塊長度對不上、檔頭無法辨識。
- 不 hook 原廠檔頭產生、不改檔頭長度（仍是 0x13400）、不動回放路徑。這是和「把壓縮 IFD 放進原廠模板」相比的取捨：
  每幀多寫約 200 個字，換掉 3 個新的原廠接點。

## 離線驗證

- `test_trailer.py` 16 項 OK，新增 `PreparedTrailerTests` 6 項：
  - 用真實 FHD 檔頭，連續多幀都和正式版逐位元組相同；
  - 只建一次，之後重用；
  - 寫入全部對齊、都在範圍內，根指標最後寫；寫入次數不到正式版的 1/3，讀取 ≤ 200 次；
  - inline 值（WhiteLevel）改變會重建，改回來也會重建；
  - IFD 外部資料（TimeCodes，以及和 IFD 結尾共用最後一個字的位元組）改變不會重建；
  - 切塊數改變會重建；
  - 無法處理的情況交回原路徑，結果相同。
- 5 個變異全部被抓到：不比對檔頭、根指標先寫、不更新表的位置、忽略切塊數改變、最後一個字不遮罩。
- ARM freestanding 編譯，沒有 memset／memcpy。
- `test_frame_hold.py` 147、`test_card_emulation.py` 26、`test_v3_lossless.py` 23 項 OK。
  `FlushMutationTests` 的 seam 字串已改成新的呼叫。

## 上機（FHD 59.94p，UHS-II，LOSS ON，`cpu_take.py`）

| 版本 | 總 CPU | CamSch | MRecMgr | SRecFile | FPLCODE |
|---|---|---|---|---|---|
| LOSS OFF（正式版） | 76.6 | 43.3 | 13.4 | 3.7 | — |
| 正式版 ON，3 段 | 90.4（平均） | 43.8–46.3 | 15.2–15.8 | 8.9 | 6.2 |
| 第 1 步 快取別名，3 段 | 85.7 | 47.0–50.4 | 13.1–14.2 | 5.2 | 2.1 |
| **第 2 步 本項，一般版 `0ba4cd52…`，3 段** | **84.3／84.6／82.8（83.9）** | 49.8／50.0／47.3 | 13.8／13.6／14.1 | **2.9／3.0／3.0** | 2.0–2.2 |
| 本項，計時版 `9cb83ae2…` | 85.9 | 51.9 | 12.7 | 2.9 | 2.0 |

- 每幀 trailer（計時版）：394 → **56 µs**（最長 114 µs）。194 幀全部套用：建 1 次、重用 193 次、退回 0 次、失敗 0 次。
- SRecFile 已經低於 LOSS OFF（3.7），因為壓縮後要寫的檔案變小了。
- LOSS 帶來的總 CPU 增量：正式版 13.8 → 第 1 步 9.1 → **本項 7.3** 個百分點。
- CamSch 仍比正式版高約 3–5 點，和第 1 步相同，原因未查。

檔案（A001_219，計時版）：取回第 2（建立）、3（第一次重用）、97、195 幀。
四幀都和主機參考實作 `tools/trailing_ifd.assemble`（由該幀自己的檔頭、payload、切塊長度重建）**逐位元組相同**；
12 tiles 的 SOI/EOI 齊全，rawpy 解碼 1090×1936（`A001_219-frames/validation.json`）。
機內回放：192 個壓縮幀由 LOSS 解碼（最近 19.5 ms、最長 36.8 ms）。

部署時 `fl del` 回應逾時一次。依程序沒有重送，`dir \fpSup` 確認舊檔已刪除後才寫入，deploy_v3 讀回核對通過。

## 狀態

- `fpSup/lossless` = 正式版 + 第 1 步 + 第 2 步 + `--time-flush` 診斷選項。
- 卡上：`deploy-plain/fpSup/10LOSS.BIN`（`013cb0fd…`，含 ON 設定），LOSS ON，CINE 待機。
- 還原正式版：`../20261013-refusal-gate/restore-card`。
