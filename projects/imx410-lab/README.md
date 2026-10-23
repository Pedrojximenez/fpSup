> 現況與筆記入口：[notes/INDEX.md](notes/INDEX.md)（2026-10-22）。以下為早期 IMXL 錄影攔截設計的說明。

# IMX410 Lab(IMXL)

設計：[DESIGN.md](DESIGN.md)。目前完成的是 **C-a**:錄影照常進行，但不寫卡，幀改存進相機 DRAM,停錄後由主機拉回。
**只做了離線部分，沒有上機、沒有寫卡。**

## 檔案

| 檔 | 內容 |
|---|---|
| `sup/ix_wr.[ch]` | 從 rec-core ULWR 的 `wr.[ch]` 分出(sha256 `2e83816d…` / `518de2ce…`),只多了 sink:`IX_SD`(= ULWR,預設)/ `IX_CAPTURE` / `IX_DISCARD` |
| `sup/ix_card.[cS]` | 從 `wr_card.[cS]` 分出：task/flag 改名 IMXL,fw 表多一個 `tick_us`(C002B6E0);組語只改註解 |
| `sup/build.py` | v3 patch_sup + inner,再換成 v4 標頭(`SL_F_CACHED_OK`,顯示名稱 "IMX410 Lab")→ `sup/build/IMXL.BIN` |
| `sup/imxl_records.py` | sink 結構與紀錄格式(主機與測試共用) |
| `sup/test_card.py` | unicorn:真 v4 loader + 真韌體檔案層 + 真 SD 驅動 arena,錄影跑完整個 sink |
| `imxl.py` | 主機工具:`status` / `arm` / `pull` / `disarm` |
| `test_host.py` | 主機端把紀錄拆成 DNG 的測試 |

bq.c/bq.h 直接用 rec-core 的檔案，沒有複製。

## sink 的規則

- 主機在**沒錄影時**借給它記憶體(韌體配置器，每塊 16 MiB,非快取別名)。先寫入塊清單、計數歸零，最後才寫 mode。
- 寫入 task 每一批讀一次 mode。capture 模式下，整批資料(就是 ULWR 原本要寫到 cluster `cl` 的位元組)被複製成一筆紀錄:
  `ix_rec` 32 B + 資料 + 補齊到 4 的倍數。存不下的批次整批不存(`n_full`),但幀照樣以 status 0 完成，所以錄影不會停。
- 來源一律經由**非快取別名**讀取，因為 SD 驅動也是不碰快取直接 DMA 的。
- 只接受 `0x40000000 ≤ 位址`、而且不碰 `0xC0000000` 以上的記憶體(防止寫到程式碼)。
- 卡上仍然會出現片段的目錄和檔案(原廠檔案系統照常運作)，但內容是空的，測完要刪掉。

## 測試(2026-10-20)

```sh
cd sup && python3 -B -m unittest test_card     # 10 項(含 3 個 mutant)，約 3 分鐘：全過
cd .. && python3 -B -m unittest test_host
```

## 上機計畫(還沒做;每一步之前先廣播相機使用權)

1. 卡片：v4 `LOADER.BIN` + `SHELL.BIN` + `IMXL.BIN`。**卡上不能有 ULWR**(兩者宣告同樣的三個位址，後載入的會被拒絕)。
   這也是 v4 第一次上機，所以先照 `fpSup/loader-v4/README.md` 的上機步驟 1–4 驗證 loader 本身。
2. 不 arm,錄一段 FHD 3 秒，確認跟 ULWR 一樣(sd 模式)。
3. `imxl.py arm --mode discard` → 錄 3 秒 → 等 10 秒 → `status`:`n_discard > 0`,卡上沒有資料。
4. 用 `fpSup/gyro/heap_survives.py` 的方法，確認借出的大塊記憶體在錄影期間不會被別人拿走。這一點目前**沒有證據**。
5. `imxl.py arm --mb 192` → 錄 3 秒 → 等 10 秒 → `pull` → 解碼 DNG,同時看 `copy_us`(非快取讀取的速度沒量過，追不上的話幀會排隊)。
