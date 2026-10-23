# 2026-10-14 單獨發布「快取別名」版本（正式版 v0.2.0test ＋ 第 1 步）：準備

使用者：「改快取的版本可以先單獨出一個版本」。

## 原始碼（`source/`）

10/13 的第 1 步原始碼沒有另外保存，這裡從正式版原始碼（`../20261013-release-base/lossless`）重組，只換 3 個檔：

| 檔 | 做法 | SHA-256（＝ `../20261013-cached-alias/plain/build.json` 記錄的值） |
|---|---|---|
| `native/card.S` | 目前工作版去掉 `#ifdef FPL_SLOT_EXPANSION` 區塊 | `90d737c1…` |
| `native/card.c` | 正式版＋3 段 `FPL_DIAG_FLUSH_TIME`（只在 `--time-flush` 診斷建置編入） | `2fa44e7b…` |
| `build_v3_lossless.py` | 正式版＋`--time-flush` 選項 | `b6e507a6…` |

另放目前的 `card_status.py`（主機工具，認得 0xC… 常駐基底；不進 BIN）。

## 建置

工作目錄 `fpSup/lossless` 沒有動（覆蓋它的指令被權限擋下）。改在 scratchpad 建 fpSup 鏡像：
`lossless` = `source/`，`uishare` 複製，`fp_usb_shell`／`out`／`research`／`projects` 連結到原處。

`build-plain/10LOSS.BIN` = **`ccf1bf23dc0dbc160e044356f6b1613dad32ba6569a0c1fe35cd5fcbdc9a141d`**，
與 10/13 上機的一般版逐位元組相同。

## 離線測試（鏡像中，`source/` ＋ 目前的 `test_v3_lossless.py`／`test_card_emulation.py`）

test_v3_lossless 23、test_card_emulation 26、test_trailer 9、test_frame_hold 147、test_codec_job 34、test_play_decode 34+1＝35，全部 OK。

## 這組位元組在相機上驗證過的範圍

只有 `../20261013-cached-alias`：FHD 59.94p ON 3 段（總 CPU 90.4 → 85.7）、208 幀機內回放、抽 3 幀主機解碼。
`../20261013-regression` 的回歸矩陣（FHD 29.97p、UHD、OG3K、HS280 119.88p、OFF CPU、選單存檔）是在「第 1＋2 步」`0ba4cd52…` 上跑的，**不是這組位元組**。

## 工作備份

`work-backup/`＋`work-backup.sha256`：本輪開始時 `fpSup/lossless` 的完整複本（未被修改，留作保險）。
