# 2026-10-15 拿掉每幀同步（使用者同意）

依據：
- `../20261014-observer-tag/A001_002-frames`：第 1 與第 657 幀的 IFD0 59 項（其中 inline 25 項）完全相同。
- 上機的 `tag_sync_writes` 一直是 0。
- `HDR_CDNG.md` §2：原廠每幀改寫的 IFD0 值都在 IFD 外、兩個 IFD 共用；這套機制不分模式。
- `../20261015-camsch`：observer 每幀 45–62 µs（MRecMgr）。

改動：
- `header_tag.c/h`：刪 `fpl_header_tag_sync`、同步表（`sync_src/dst`，每份 1 KiB）、`FPL_HEADER_TAG_SYNC`、`type_bytes`；
  壓縮 IFD 的 entry 照原樣複製。
- `card.c`：observer 只處理 mode 0（加 tag）與 mode 2（建 IFD）；每幀 mode 3 只讀事件就返回。刪 `tag_syncs`、`tag_sync_writes`。
- 測試：刪 3 項同步測試與 1 個同步變異；模擬測試改為「每幀通知不寫任何東西」。

測試：test_header_tag、test_frame_hold、test_card_emulation、test_v3_lossless 全部 OK。
建置：`build-plain/10LOSS.BIN` = `4057e2aec15b3de10544bd6b02bf4b5ba3a797d63bc5cd29d57d68a0965beca3`（取代 `e82c1e12…`）。未上機。

## 上機（2026-10-15 01:50，FHD 29.97p，UHS-II，FCAP 生效）

部署 `deploy-on/fpSup/10LOSS.BIN`（ON 副本，`420c231f…`），重開機，observer 在第 7 格。`cpu_short.py` 錄 2 段（第 1–3 s 量，第 4 s 停）：

| 段 | 總 CPU | CamSch | MRecMgr | SRecFile | FPLCODE |
|---|---|---|---|---|---|
| A001_028 | 20.7 | 5.8 | 2.4 | 1.1 | 1.1 |
| A001_029 | 20.6 | 6.0 | 2.4 | 1.0 | 1.0 |

（對照 `../20261015-camsch` 同條件：OFF 19.2–19.3／MRecMgr 2.2–2.4；舊 tag 診斷版 ON 20.9–21.2／MRecMgr 2.6。）

計數（`status.txt`）：`tag_added 2`、`tag_prepared 2`、`tag_head 0x13800`、`flush.applied 205`、`tag_failed 0`。

A001_029（`A001_029-frames/`）：第 1 幀 RAW，第 2、50、104（最後）幀壓縮，996,352 B，壓縮 IFD 在 tag 內，LibRaw 1090×1936；
經壓縮 IFD 讀到的 TimeCodes（0xC763）、RawDataUniqueID（0xC65D）逐幀不同且是該幀自己的值，與 IFD0 同一位址——不需同步。

相機最後：此版 ON（`420c231f…`）＋FCAP，29.97p。
