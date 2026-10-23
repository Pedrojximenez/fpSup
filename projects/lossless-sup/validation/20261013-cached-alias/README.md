# 2026-10-13: LOSS 改從快取別名執行（逐項改善第 1 步，已上機、採用）

## 發現

Loader v3 用 `C001CF78(0)`（USER／NonCacheBuffer）配置每個 sup 的塊，LOSS 位在 VA `0x45153FA0`。
相機上即時讀 MMU 表（TTBR0 `0x44300040`，只讀）：

| VA | 描述子 | 意義 |
|---|---|---|
| `0x40000000..0x7FFFFFFF` | `0x4n044C02` | PA 相同，Normal **非快取**（TEX=100, C=B=0），可執行 |
| `0xC0000000..0xFFFFFFFF` | `0x4n045C06` | PA `0x40000000..0x7FFFFFFF`，Normal **write-back 快取**（TEX=101, B=1），RW、可執行 |

原廠程式（0xC0..）與 heap（0xC3..）走的是後者。LOSS 的程式、狀態、常駐字全部在前者，**每條指令都從 DRAM 取**。
這解釋了正式版 trailer 約 9.5k 條指令、計時 1.18 ms／幀，也解釋了指令數翻倍的「字組化」版本（step 2）反而更慢。

## 修改（只動 `native/card.S` V3 路徑，約 15 行）

- 所有拒絕判斷都通過、寫常駐字之前：`C000E91C`（D-cache 全部 clean+invalidate），然後 `r5 += 0x80000000`、`r11 = 0x80000000`。
  之後所有交給韌體的位址（veneer 目標、C 入口、狀態、codec 任務入口、主機紀錄 +36/+40）都是快取別名 `0xC5……`。
- `out`（RELEASE）先 clean+invalidate，避免已釋放的塊留下 dirty line。
- 塊內沒有任何東西交給 DMA（codec 的 source/destination/table 在 frame 配置；header DMA 的參數在堆疊）；
  frame 仍以 `+0x40000000` 非快取別名存取，與以前相同。
- `card_status.py`：接受 `0xC4……` 以上的常駐基底；trace／elog 對快取位址改用 `mem get`（CPU 讀，與快取一致），
  不再對它用 `read_direct`（USB DMA 只能到 CPU−0x40000000 的位址）。
- 非 V3（舊 build_card）路徑不變。

## 離線驗證

- `test_v3_lossless.py` 23 項 OK。模型把 heap 以同一塊緩衝映射在 `0x45000000` 與 `0xC5000000`（`mem_map_ptr`）。
  載入測試改為要求 veneer、狀態、任務入口、主機紀錄都在快取別名；新增「第一次經快取別名存取之前有 D-cache 清除、返回前最後一次是 D-cache 清除」。
  變異：拿掉切換前那次清除，新測試**仍通過**，因為 loader 在呼叫 entry 前已做 D/I，期間沒有人碰快取別名；這次清除是額外保險，不是唯一保證。
- `test_card_emulation.py` 26 項 OK。

## 上機（FHD 1936×1090 59.94p，UHS-II，LOSS ON，`cpu_take.py`，1–3 s 的 tskmon 窗口）

候選 BIN 內含「LOSS 開啟」的設定紀錄（從卡上讀回的正式版複製 16 B），部署後讀回核對，重開機後常駐基底 `0xC5153FA0`。

| 版本 | 總 CPU | CamSch | MRecMgr | SRecFile | FPLCODE |
|---|---|---|---|---|---|
| LOSS OFF（正式版） | 76.6 | 43.3 | 13.4 | 3.7 | — |
| 正式版 ON，3 段 | 91.3／89.5／90.5（90.4） | 46.3／43.8／43.8 | 15.2／15.2／15.8 | 8.7／8.9／9.2（8.9） | 6.1／6.4／6.1 |
| **快取別名 ON，3 段（一般版 `ccf1bf23…`）** | **86.3／85.2／85.7（85.7）** | 50.4／47.0／47.7 | 13.1／14.1／14.2 | **5.0／5.4／5.3（5.2）** | **2.0／2.1／2.2** |
| 快取別名 ON，計時版（`fbab7be7…`） | 86.1 | 49.7 | 13.3 | 5.1 | 2.3 |

- LOSS 帶來的總 CPU 增量 13.8 → **9.1** 個百分點。
- 每幀 trailer（計時版 writer hook）：**1,178 µs → 394 µs**（208 幀全部套用，最長 2.2 ms，失敗 0）。
- 每段 207–211 幀全部壓縮，refused／no_benefit／passed 0，`req_cnt = fin_cnt`。
- CamSch 高了約 3–4 點（三段一致）。推測是 LOSS 的程式與狀態現在佔用快取，擠掉原廠的快取行；未證實。總量仍淨降約 4.7 點。

檔案（A001_215，計時版）：第 2、100、208 幀取回主機，12 tiles 的 SOI/EOI 齊全，rawpy 解碼 1090×1936；
壓縮 IFD 除 259/273/278/279 及新增 322–325 外，與原 IFD 逐 entry 相同（`A001_215-frames/validation.json`）。
機內回放：208 個壓縮幀由 LOSS 解碼（`play.decoded` 208，最近 21.3 ms、最長 38.3 ms，失敗 0）。

## 狀態

- `fpSup/lossless` = 正式版 + 本項 + `--time-flush` 診斷選項（只在該選項下編入）。
- 卡上：一般版 `deploy-plain/fpSup/10LOSS.BIN`（`fbc488ce…`，含 ON 設定），LOSS ON，CINE 待機。
- 還原正式版：`../20261013-refusal-gate/restore-card`。

## 下一步

剩下的 trailer 394 µs／幀（約 2.4% @ 59.94p）是逐 byte 讀寫**非快取的 frame 檔頭**，現在才是共用檔頭要消除的部分。
另外可查 CamSch 的增加是否來自快取擠壓（例如 128 格 commit ring 的線性掃描）。
