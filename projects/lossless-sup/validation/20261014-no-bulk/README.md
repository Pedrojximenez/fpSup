# 2026-10-14 從 LOSS 移除 64 MiB 批次調整

使用者決定（同日）：LOSS 只採用「快取別名」與「observer tag 檔頭機制」；1016 格、共用檔頭（預先準備 IFD）、
寫入器防護、M12 修正都不採用；**64 MiB 的修正也從 lossless sup 移除**。批次大小交給 rec-core 寫入層（`vol+0x4828`）。

## 基底

`fpSup/lossless` 先換成正式版 v0.2.0test＋快取別名（`../20261014-step1-release/source/`，建出 `ccf1bf23…`）。
換之前的完整工作版：`../20261014-step1-release/work-backup/`（hash 清單核對過）。

## 改動

| 檔 | 改動 |
|---|---|
| `native/card.c` | 刪 `FPL_BULK_*`／`FPL_FILE_HEAD`、`card_bulk()`、`card_bulk_for()`、狀態欄 `bulk`／`bulk_writer_open`；REC 不再寫 `0xC0B9E5D8` |
| `native/card.S` | claims 14 → 13：刪 `0xC0B9E5D8 SL_EXCL` |
| `build_v3_lossless.py` | `SITE_COUNT` 13；`WANT_KIND` 刪 `0xC0B9E5D8` |
| `build_card.py` | `SITES` 刪 `0xC0B9E5D8`；`FIELDS` 刪 `bulk`、`bulk_writer_open` |
| `test_card_emulation.py` | 原測試「OFF 時寫回 64 MB」改為「REC 不碰這個字」（舊程式會把它寫成 0x04000000，所以這項測試抓得到回退） |

沒動：`native/bulk_policy.c/h`（正式版就有、沒編進 BIN 的閒置檔）、`card_status.py`（`bulk` 欄位不存在時本來就不印）。

## 結果

`build-plain/10LOSS.BIN` = `47b15e079cb218dd15c82a3c101c9e11ec7efe08465e4f59897a4f938a17c295`。
test_v3_lossless 23＋test_card_emulation 26 = 49 項 OK。未上機。

## 已知後果

單獨使用 LOSS（沒有 rec-core 寫入層）時回到 EARLY_STOP_94 的行為：壓縮片段要累積 64 MiB 才交出一批，
在途幀到 94 會停錄（FHD 59.94p 約 1.6 s）。要等寫入層把 `vol+0x4828` 設成 RU 倍數後才解除。
