# 2026-10-13 M12/HS280 引擎拒絕：上機診斷

診斷建置：`build_v3_lossless.py --expand-slots --sample-source`（`FPL_DIAG_SOURCE`；不加旗標時建出的 BIN 與 `7e920525…` 逐位元組相同）。
v1 `92d4b13d`（來源取樣）→ v2 `58e758ab`（加 cached/uncached 視窗）→ v3 `730a62df`（加引擎暫存器 0x300D0000..FC，在 CLOSE 前）。
卡上目前是 v3 診斷版。SD 匯流排需是 UHS-II（`sdcard sdmode`）；今天曾退回 UHS-I，實體關機後恢復。

## 已排除

| 推測 | 證據 | 檔案 |
|---|---|---|
| 到達 hook 時幀尚未寫完（RWZM） | 214 幀在到達／送出／收回三時點取樣完全相同 | `src-hs280-2s.json` |
| CPU 快取未寫回 | 219 幀到達與收回時 cached(0xD) 與 uncached(0x9) 視窗相同 | `src-hs280-views.json` |
| 來源位址對齊 | FHD 的 source 末碼 000/400/800/C00 都壓縮成功 | `src-fhd-2s.json` |
| 資料排列／檔頭長度 | HS、FHD 的 DNG 像素起點都是 0x13400；緩衝區都是 DNG 12-bit 大端（FHD 的中點取樣因 raster 3,165,372 非 3 的倍數而錯相，已核對） | — |
| 輸出放不下 | 拒絕時引擎暫存器 0x7C～0x90 約 0x4EC00～0x51F00，與主機同幀 311,909 B 相近，遠小於 1 MB | `regs-hs280.json` |
| 只是最後一列切塊高度 0 | 預設 512×336 時 0x54 = `000000A8`（最後列 0）；但 512×352 時 0x54 = `00A000B0`（正確）仍同樣錯誤 | `regs-hs280-512x352.json` |

## 引擎暫存器（成功 FHD vs 拒絕 HS）

- 0x04：FHD 0、HS **4**（錯誤狀態）。
- 0x4C：(tiles_x−1)<<8 | (tiles_y−1)；0x50：最後一欄寬/2 <<8 | 0x10；0x54：最後一列高/2 <<16 | 切塊高/2；0x6C：列寬位元組/2。
- HS 結束時 0xC4～0xF8（FHD 成功後的收尾統計、0xF8 end position）全為 0。
- 不論切塊 4～48 個，HS 都在約一半時間（~2.2 ms／完整約 4.5 ms）出錯 → 與畫面位置有關，不像與切法有關。尚未解釋。

## 根因（已上機證實）

原廠 submit `C062FFF8` 把輸出上限暫存器 0x90 寫成 `(dst + 告知長度 − 0x40100000) >> 10`，即**目的地＋長度−1 MiB**
（原廠呼叫者只用於數十 MiB 的整張靜態影像）。HS280 一幀 raster 0xF8100 < 1 MiB，告知長度 0xF8400 時上限落在起點之前
（實測 0x90 = 0x4EC93 < 0x7C = 0x4ECB2），每幀錯誤 4。FHD 3 MB 時上限在起點之後，所以正常。靜態分析見子代理報告（本 README 摘要）。

驗證：把告知長度加 1 MiB 後，同一 HS 幀引擎完成（pattern 1、0x04 = 0、end position 0x46758 ≈ 288,600 B）。`fix-regs-hs280-120p.json`

## 第一版修正的問題（已撤回）

第一版讓 1 MiB 以下的畫面改寫進含 1 MiB 餘裕的 workspace output，再複製回幀。上機：壓縮成功 113 幀，但
複製回幀走 uncached 兩端，~288 KB 約 30 ms，卡在到達 hook 裡；逐幀 trace（`trace-hs280-1s.csv`）顯示到達間隔 ~30 ms、
寫入器 5 秒只處理 3～6 幀 → RAW 池滿 `vbuf/558`、相機自停 → 收尾卡死（需拔電池）。workspace／rec_workspace／frame_hold 的改動已全部還原。

## 現行修正（codec_job.c 一處；未上機）

`request[8]`：房間 ≥ 2 MiB 時照原廠（上限仍在房間內 1 MiB，FHD 不變）；小於 2 MiB 時告知 `房間 + 1 MiB − align1K(房間/4)`，
上限落在自有 spare 的 3/4 處，後 1/4 為保護區（原廠是 1 MiB）；輸出超過原檔 3/4 的幀被引擎拒絕→原檔寫出（省不了多少）。
走與 FHD 相同的零複製交換，無複製回幀。9/28 實測引擎拒絕時不寫出任何位元組。

- 測試：`test_codec_job` 37 項（含新增 2 項、變異 2 項）、frame_hold／workspace／rec_workspace、整合 78 項全部 OK。
- 建置：診斷版 `candidate/` `12482814…`（--sample-source）、一般候選 `fix-candidate/` `83d2b9fc…`。
- 上機計畫：拔電池重開 → 部署診斷版 → HS280 59.94p 1 秒 → 119.88p 2 秒，每段確認 req_cnt = fin_cnt 與寫入器閒置後才進下一段。

## 寫入慢造成的卡死：已修（未上機）

卡死當下的 registry 證實是寫入器重複派送耗光訊息票（99 幀 0xB 孤兒）。修正 (d) 見 `../20261013-refusal-gate/STOP_HANG_ANALYSIS.md` 文末。
現行建置（含 M12 上限修正＋寫入器修正）：診斷 `candidate/` `c4103595…`、一般 `fix-candidate/` `a0462d71…`。
