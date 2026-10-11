# SIGMA fp 六軸記錄與後期融合研究

更新日期：2026-08-19  
目標：保留 ICM20321 Gyro 與 MMA8452Q Accel 的獨立原始資料，以共同單調時鐘對時，離線建立 500 Hz 融合狀態。

## 已確認的韌體證據

- 韌體類別／裝置名稱包含 `IMUDevInterface_ICM20321`、`IMUDev_GYRO_ICM20321`。
- 韌體類別／裝置名稱包含 `IMUDevInterface_MMA8452Q`、`IMUDev_ACCEL_MMA8452Q`。
- MMA8452Q 讀取函式位於 `0xC050D250`。
- 該函式以 6-byte burst 取得三軸 12-bit signed samples，逐軸做 byte swap 後 arithmetic shift right 4。
- 韌體依方向代碼 0..8 做軸交換與正負號轉換。
- 方向轉換後的最新值存於：
  - X: `0xC377790C` (`int16`)
  - Y: `0xC377790E` (`int16`)
  - Z: `0xC3777910` (`int16`)
- 另一個介面函式 `0xC050D1E8` 會從同一組 globals 輸出三軸值，表示它們是韌體正式資料路徑，不只是診斷字串。

## 尚未確認

- globals 的實際更新頻率是否恆定為 100 Hz。
- 相機 Ver.5.02 使用的 MMA8452Q 量程與實際 LSB/g。
- 韌體方向代碼的當前值，以及 Accel 座標和 Stage-5 Gyro `YxZ` 的固定轉換。
- Accel 內部濾波與 Gyro 的固定群延遲差。
- Accel 更新執行緒可安全掛接的位置與優先權。

## 實作原則

1. Gyro 2500 Hz 與 Accel 約 100 Hz 分開保存，不在相機端插值。
2. 每批／每筆資料使用和影片、Stage-6 相同的 monotonic microsecond clock。
3. 加速度資料不得只以「第 n 筆 × 10 ms」推算時間。
4. 原始值、方向代碼、量程、校正矩陣和 offset 都要寫入檔頭。
5. 500 Hz 是離線融合狀態，不冒充真實 500 Hz Accel measurement。
6. 每個預測點保留 measured/predicted 標記與 confidence。

## 分階段驗證

### A0：非侵入快照（目前已建立）

使用 `autorun_accel_snapshot_probe.txt` 讀取上述 globals。目的只在確認靜止重力與三軸移動會造成合理變化。因 SD 寫入延遲不固定，這批資料不能拿來融合。

驗收：

- 25 個檔案都存在且至少 6 bytes。
- 靜放時有一軸呈現穩定的主要重力分量。
- 將機身依三軸翻轉時，相應軸的符號／幅度改變。
- 靜放後的雜訊顯著小於翻轉造成的 span。

### A1：100 Hz RAM ring

確認 A0 後，在既有 IMU sampling path 只複製 `timestamp + xyz + status` 到獨立 ring。此階段不寫 GFS6、不改變 MMA8452Q 暫存器。

### A2：Stage-7 六軸雙緩衝

將 Gyro 與 Accel 保持為兩條獨立 stream，共用 clip start clock。writer thread 寫入 CRC block，footer 分別報告兩條 stream 的 sample count、drop 與時間跨度。

### A3：離線 500 Hz 融合

- 用全部 2500 Hz Gyro 積分高頻姿態。
- 將前後 Accel samples 轉到共同座標後做雙向平滑。
- 分離預測重力與線性加速度。
- 先輸出 500 Hz 狀態與 confidence，再與 30 fps optical flow 比較。

## 第一輪實機操作

1. 備份 SD 卡現有 `AutoRun.txt`。
2. 將 `autorun_accel_snapshot_probe.txt` 複製成卡根目錄 `AutoRun.txt`。
3. 開機後在彩條顯示期間緩慢做一次左右、前後翻轉；看到結束雙閃。
4. 關機後退出 SD 卡再讀卡。
5. 執行 `decode_sigma_fp_accel_probe.py <card-path> --csv accel_probe.csv`。
6. 測試結束立即移除這個 probe AutoRun，避免每次開機重寫快照檔。

