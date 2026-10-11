# SIGMA fp：Gyroflow 與 NiYien A1 外接陀螺儀研究

更新日期：2026-08-17  
研究對象：SIGMA fp Ver.5.02、NiYien Senseflow A1、Gyroflow  
狀態：外接 A1 文件研究完成；fp 內部 ICM20321 已取得 ring 與連續 raw dump，正在驗證時基／座標／GCSV

## 結論摘要

1. **SIGMA fp 目前不是 Gyroflow 官方列出的內建 gyro source。** Gyroflow 官方支援來源清單列有 Sony、GoPro、Insta360、Blackmagic RAW、RED RAW、Canon 等，但沒有 SIGMA fp。官方對未內建或未輸出陀螺資料的相機，建議把手機、運動相機或外接 logger 固定在主相機上。
2. **NiYien A1 是目前與 fp 最直接的現成方案。** Gyroflow 官方文件把 A1 定義為專用外接陀螺儀；NiYien 的相機清單明列 Sigma fp 與 fp L。
3. **A1 與 Gyroflow 是互補關係。** A1 記錄角速度／加速度資料；NiYien Tool 負責素材配對、批次同步及產生 `.gyroflow` 專案；真正的穩定、鏡頭模型與 rolling-shutter 校正由 Gyroflow 核心流程完成。
4. **已確認 fp 機內有可用候選 gyro raw path。** Ver.5.02 韌體與實機 dump 指向 TDK/InvenSense ICM20321；共享 RAM ring 有 600 筆三軸樣本，Stage-3 hook 已連續擷取 11,748 筆。這仍不等於 Gyroflow 已可直接使用：sample rate、相機座標軸、影片共同時基與長片 drift 尚待驗證。
5. **對 CinemaDNG 工作流可行，但要先建立可靠同步。** Gyroflow 本身支援 CinemaDNG image sequence；A1 使用者也有將整個 DNG sequence folder 與 gyro data folder 載入 NiYien Tool，再輸出已同步 `.gyroflow` 專案供 Resolve 使用的實例。這部分仍屬社群實測，應以我們自己的素材驗證。

## 產品與軟體定位

### NiYien Senseflow A1

NiYien 官網目前公布的硬體規格：

- 尺寸：33 × 28.5 × 26 mm
- 重量：30 g
- 續航：35 小時
- 安裝：冷靴／熱靴
- 陀螺儀採樣率：1 kHz
- 儲存：4 GB
- 連接：USB Type-C

Gyroflow 官方文件另描述其操作模式為：先與相機做一次同步設定，之後 A1 可持續記錄；NiYien Tool 可批次調整 Gyroflow 參數、輸出穩定影片或 `.gyroflow` 專案。

### Gyroflow

Gyroflow 使用陀螺儀角速度（可選加速度計）重建相機姿態，再結合鏡頭畸變模型、影格時間戳與 sensor readout time 做畫面反向變換。對本專案最重要的能力包括：

- CinemaDNG、PNG、OpenEXR image sequence 輸入
- rolling-shutter correction
- optical-flow 輔助的時間同步
- gyro low-pass filter、IMU 軸向／任意旋轉校正
- adaptive zoom、zoom limit、horizon lock
- DaVinci Resolve OpenFX 與 Adobe 外掛流程
- `.gcsv` 外部資料格式與 `.gyroflow` 專案輸出

## SIGMA fp 相容性判斷

### 已確認

- NiYien 2026-08-11 產生的官方相機清單包含 `Sigma → fp L, fp`。
- NiYien 自動模式教程把「適馬相機＋自動對焦鏡頭」列為適用情境。
- NiYien 官網宣稱支援 DNG sequence、10/12-bit 與 Log 素材。
- Gyroflow 主程式官方功能表明確包含 CinemaDNG image sequence。
- SIGMA 官方早期 fp FAQ 明確表示機身沒有機械式防震機構，並以電子防震作為機內選項；該 FAQ 沒有說明是否會把 IMU metadata 寫入影片。

### 尚未確認

- A1 原始資料的實際檔案格式、欄位、時間基準與 timestamp 精度。
- A1 是否使用 RTC、USB 檔案時間、相機音訊／畫面動作，或其他訊號完成「自動匹配」。
- fp 各 CinemaDNG 模式的精確 sensor readout time；rolling-shutter 校正對此數值非常敏感。
- NiYien Tool 對 fp 的鏡頭資訊取得方式；手動鏡、轉接鏡、變形鏡很可能需要手動模式與自建 lens profile。
- fp 的機內 EIS 或鏡頭 OS 是否會破壞 gyro 與像素運動的一致性。

## 建議拍攝設定

### 必做

1. A1 必須剛性固定在 fp 機身／cage，不能相對滑動；記錄安裝方向。
2. 關閉 fp 電子防震與鏡頭 OS，先建立最單純的「剛體相機＋外接 IMU」基準。
3. 使用固定焦距；變焦鏡在單段錄影中不要改變焦距。NiYien 官網也註明同一影片一般不支援變焦（其說明另稱 RAW video 不受此限制，但仍應實測）。
4. 每個拍攝日先錄短同步片：同時開始／停止相機與 A1，並加入數次清楚、短促、各軸可辨識的旋轉動作。
5. 保存原始 DNG sequence、A1 原始 log、NiYien 配對結果與 `.gyroflow` 專案，不要只留下渲染影片。

### 快門取捨

NiYien 教程建議：靜止拍攝不慢於 1/50、一般拍攝不慢於 1/120、快走／跑動不慢於 1/200，焦段小於 150 mm。對 fp 的第一輪測試，建議用 24–35 mm，依序測：

- 1/50 或 180°：保留自然 motion blur，觀察大幅修正時的拖影／抖動殘影。
- 1/120：作為手持折衷基準。
- 1/200 或更快：驗證穩定與 rolling-shutter 校正上限，後期再決定是否補 motion blur。

較快快門能讓幾何穩定後的影格更乾淨，但不會消除裁切需求，也不會把 gyro 穩定真正變成光學雲台。

## 最小驗證矩陣

| 測項 | 固定條件 | 變因 | 驗收 |
|---|---|---|---|
| 時間同步 | 4K、24p、24–35 mm | 3 次獨立短片 | 自動同步偏移可重現，gyro 與 optical flow 峰值對齊 |
| IMU 軸向 | 同一安裝方向 | 單獨 yaw／pitch／roll | 三軸方向與幅度一致，無軸交換或正負號錯誤 |
| 快門 | 同一路徑與焦距 | 1/50、1/120、1/200 | 比較殘影、裁切、邊角扭曲 |
| rolling shutter | 快速水平 pan | 多組 readout time | 直線最直且沒有反向彎曲；記錄最佳 ms |
| CinemaDNG | 相同場景 | DNG sequence／轉碼 ProRes | 同步、色彩與輸出影格數一致 |
| 長錄穩定性 | 固定 4K 模式 | 10、30、60 分鐘 | 無 timestamp drift；尾段仍能對齊 |
| EIS／OS 影響 | 同一手持動作 | 全關、只開 OS、只開 EIS | 確認是否出現雙重補償或局部非剛體運動 |

## 與目前韌體研究的連接點

外接 A1 可先解決實際拍攝需求，但也提供一組很有價值的 ground truth，可反過來協助 fp 韌體研究：

1. 同時記錄 A1 與相機內部候選資料區。
2. 在三個軸分別做已知方向的短促旋轉。
3. 對 RAM dump／事件 log 搜尋與 A1 角速度高度相關的三軸時間序列。
4. 若找到候選 ring buffer，再確認採樣率、比例因子、座標系、bias 與 timestamp。
5. 最終將候選資料轉成 Gyroflow `.gcsv`，以 optical-flow 同步分數作為客觀驗證。

這比只搜尋「看起來像三個 16-bit 數」更可靠；A1 資料可以提供時間、方向與波形對照。

### 2026-08-17 內部 gyro 實機進展

- runtime pointer `0xC31E3FCC` 指到 sub-ARM shared RAM；ring base 實測為 `0x2E00644C`。
- ring 為 600 筆 × 8 bytes，正確 little-endian layout 是 `X, Y, 0, Z`；舊筆記的 `X,Y,Z,w` 軸位次已修正。
- 描述子值 2500 經同拍 CinemaDNG 複核後，較合理的解釋是 2500 微秒／樣本，即暫定 400 Hz、`tscale=0.0025`；仍應以 VD tick 做最終精確驗證。
- ICM20321 ±250 dps 暫用 131 LSB/dps，GCSV `gscale=(pi/180)/131 ≈ 0.000133202 rad/s/LSB`。
- 已新增 `decode_sigma_fp_gyro.py`，可檢查 8-byte framing、輸出統計並產生明標 provisional 的 GCSV。
- 兩份連續測試檔 `GYRO.BIN` 與 `GYRO_shake.BIN` 完全相同，第二次 shake 測試目前無效，不能用來判定軸向。

## 下一步

1. 取得 A1 實機或一組 fp + A1 原始測試檔（DNG sequence、gyro log、`.gyroflow`）。
2. 檢查 A1 儲存目錄與原始 log 格式，確認是否可直接解析或轉 `.gcsv`。
3. 用 24–35 mm 定焦鏡完成最小驗證矩陣。
4. 實測 fp 各模式的 rolling-shutter readout time，建立可重用 preset。
5. 以 A1 波形作 ground truth，另開「fp 內部 IMU／姿態資料搜尋」分支；不要把外接方案與內部資料存在性混為同一結論。

## 來源

- [NiYien A1 中文官網](https://www.niyien.com/v2/zh/index.html)
- [NiYien A1 技術參數](https://www.niyien.com/v2/zh/specs.html)
- [NiYien A1 相機支援清單](https://www.niyien.com/v2/zh/cameras.html)
- [NiYien A1 教程與拍攝限制](https://www.niyien.com/v2/zh/tutorials.html)
- [Gyroflow：NiYien A1 外接 gyro source](https://docs.gyroflow.xyz/app/advanced-usage/using-external-gyro-source/niyien-a1)
- [Gyroflow 官方專案與支援來源](https://github.com/gyroflow/gyroflow)
- [Gyroflow GCSV 格式](https://docs.gyroflow.xyz/app/technical-details/gcsv-format)
- [SIGMA fp FAQ Ver.2](https://www.sigma-italia.it/files/files/fp_faq_291119_041749.pdf)
- [SIGMA fp + A1 + CinemaDNG 社群實測討論](https://www.reddit.com/r/sigmafp/comments/1q4d08g/fp_travel_short_full_frame_in_an_extremely_shaky/)

> 證據分級：產品規格、軟體能力與支援清單以官方來源為主；CinemaDNG 的具體 A1 操作流程與實拍效果目前只有社群證據，尚未在本專案硬體上重現。
