# Stage-6 雙緩衝 gyro logger 測試設計

狀態：程式、AutoRun、GFS6 解析器與合成壓力測試完成；尚未部署實機（檢查時 `fpGfTest` 未掛載）。

## 資料路徑

```text
ICM20321 ring (600 samples)
  -> gyro hook（只複製）
  -> Buffer A / Buffer B（各 256 KiB）
  -> READY
  -> 獨立低優先權 writer thread
  -> GFS6/GFB6 .GYR on SD
  -> GFE6 footer
  -> 停止後轉 GCSV
```

## 記憶體

- 8 MiB USER allocation：`0x44F6ADC0..0x456EADC0`
- Buffer A：`0x44F6ADC0`，256 KiB
- Buffer B：`0x44FAADC0`，256 KiB
- 每塊 32-byte header + 最多 `0x3FFE0` payload，約 13.1 秒 raw gyro
- state/path/header/file object 位於 allocation 最末 64 KiB 內
- ARM code：`0xC072DE64`，目前 `0x654` bytes；原韌體對應範圍全零

## 狀態機

- Buffer：`EMPTY -> FILLING -> READY -> WRITING -> EMPTY`
- File：`CLOSED -> OPEN_REQUEST -> OPEN`
- Stop flag 與 file state 分離，避免短錄影時 close 覆蓋 open request
- A/B 同時 READY 時依 block sequence 寫入，避免固定 A 優先造成反序
- 兩個 buffer 都不可用時丟棄該批並累積 `dropped_samples`

## GFS6 格式

- 64-byte `GFS6` v3 file header：2500 Hz、400 us、start timestamp、clip、`YxZ`、float gscale
- 32-byte `GFB6` block header：sequence、first/last timestamp、sample count、flags、payload bytes、CRC-32
- payload：`int16 X,Y,0,Z`
- 32-byte `GFE6` footer：block count、dropped samples、error flags、end timestamp
- 解析器拒絕：缺 footer、CRC mismatch、block sequence gap、payload/count mismatch、非零 padding

## 已完成驗證

- code size：`0x654`
- direct branch：49，全部留在 code region
- 原韌體 code region 非零 byte：0
- 兩個 buffer literal：正確
- 合成 GFS6：3 blocks、CRC、footer、GCSV 轉換通過
- 壓力模型：10,000 seeds、每次 30 分鐘、writer latency 隨機 1 ms–5 s，零 drop

## 實機首輪驗收

1. 只錄一段約 35 秒 CinemaDNG，確保跨越至少兩次 buffer publish。
2. 停止後等待 20 秒，讓最後 block、footer 與 close 完成。
3. 關機、讀卡；檢查同名 GYR、GFE6 footer、CRC、sequence、dropped=0。
4. 比對影片幀數、gyro timestamp span 與 sample rate。
5. 通過後才加入停止錄影後的相機內 GCSV conversion；首輪不在相機執行文字轉換。

## 風險

- firmware thread descriptor 與 media API 雖由既有程式逆向並沿用，仍需實機確認跨 thread 使用安全。
- CRC-32 計算在 writer thread，每約 13.1 秒處理 256 KiB；thread priority 低於 gyro thread。
- 首輪若凍結：移除電池與 SD 卡；AutoRun 為 RAM-only，斷電即還原。
