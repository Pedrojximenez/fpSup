# SIGMA fp Ver.5.02 — IMU (gyro/accel) data path + Gyroflow feasibility

> **2026-08-18 歸檔提示：** 本檔保留研究演進與早期假設，其中「2500 us/sample = 400 Hz」已被 Stage-5 微秒 TickTimer 實測推翻。最新確認值為約 **2500 Hz（400 us/sample）**、Gyroflow orientation **`YxZ`**、本輪實測 `gscale ≈ 0.000121385`。權威彙整請讀 `SIGMA_FP_INTERNAL_GYRO_ARCHIVE_2026-08-18.md`。

**判決:Gyroflow 可行(推翻早期「不可行」)。** 早期判不可行是**看錯 buffer**(當時看的是 AF 用的 10 元素 body-motion 決策 ring)。真正的陀螺 ring 有 **600 樣本、3 軸原始**,已實機 dump + 解碼,你的 pan 動作在資料裡看得到。

## 硬體
- **陀螺 = TDK/InvenSense ICM20321**,±250 dps,**131 LSB/dps → `dps = raw_int16/131`**。在 OIS 協處理器(sub-ARM)後面,主 ARM 透過 mailbox 指標讀。符號 `IMUDevInterface_ICM20321`,accessor `FUN_c01ec8c0`。
- **加速度計 = NXP MMA8452Q**,±2g,**1024 LSB/g → `g = raw/1024`**,I2C bus 2 addr 0x1C,~100Hz(水平儀用);最新值快取在 `0xC377790C/0E/10`。無 FIFO。
- 校正塊 `_DAT_c31e3fd4 = 0xC307B548`(0x244 bytes):陀螺 offset +0x11C/120/124(magic 0x76321743@+0xD8)、accel offset +0x1E4(magic 0x48974694@+0x180)、9-way 軸重映。

## ★ 陀螺 ring 的位址鏈(實機驗證)
```
mailbox 指標變數 @ 0xC31E3FCC  →  P = *(0xC31E3FCC) = 0x2E006004   (sub-ARM 共享 RAM,0x2E000000 區!)
ring_base = *(P+0x60) = *(0x2E006064) = 0x2E00644C
ring end  = 0x2E007710  (= 描述子 0xC31E3FD0 存的另一指標)
ring 大小 = 0x2E007710 − 0x2E00644C = 0x12C4 ≈ 0x12C0 = 4800 bytes = 600 樣本
*ring_base(第一字)= head/write 指標(會動 → ring 是活的)
*(P+0x64) = 0x9C4 = 2500  → 2026-08-17 新實測支持這是 **2500 us/sample**，即 400 Hz，而不是 2500 Hz；600 筆 ring 可保存約 1.5 秒。
```
- **樣本佈局（2026-08-17 複核修正）**：little-endian 每樣本 8 bytes，依序為 `int16 X, int16 Y, int16 padding, int16 Z`；即 `word0=(Y<<16)|X`、`word1=(Z<<16)|0`。samples 從 `ring_base+4`（0x2E006450）起。
- **第 3 個 int16 padding 恆 0**；真正的 Z 是第 4 個 int16。600 筆 ring 與 11,748 筆 Stage-3 連續檔都符合。因沒有逐樣本 timestamp/序號，ODR 仍須用共用時鐘或錄影時長外部量測。

## 實機確認(GRING.BIN,600 樣本)
- 全 600 樣本解出真實平滑 3 軸陀螺;**Y(yaw)平滑掃 -56→-63→-9→-47 dps = 使用者的 pan**;只有 1 個大跳變(wrap 點)。scale `raw/131=dps` 給合理量級(~40-60 dps 中等手搖)。

## dump 方法(唯讀,安全,實測可行)
`mem save \FILE.BIN <addr>,,<len>`(len hex)。**必須逐步:先從韌體會 deref 的位址解指標,再逼近 —— 不可盲掃**(見下「教訓」)。
- step1: `mem save \GDESC.BIN 0xC31E3FCC,,0x40`(解 P)+ `mem save \GCAL.BIN 0xC307B548,,0x244`
- step2: `mem save \GP.BIN 0x2E006000,,0x800`(P 附近,拿 ring_base)
- step3: `mem save \GRING.BIN 0x2E006400,,0x1400`(全 ring)
- ⚠️ **FAT32 卡也會觸發 AutoRun**(NIKON D80 卡實測);觸發 = restart+插卡。

## ⚠️ 教訓(記憶體讀取也能當機)
第一版盲掃 `0xC31C0000–0xC31F0000`(推測 ring 在那)→ **相機當機、無資料**。真因:ring 在 **`0x2E000000`(sub-ARM 另一塊 RAM)**,不在 0xC3xxxxxx;0xC31Cxxxx 有未映射位址,`mem save` 一讀就凍結開機。恢復 = 拔電池+移卡。**正解:只讀「韌體自己會 deref」的位址(保證映射),從指標逐步解出真位址,不基於推測大範圍動手。**

## Stage-3 logging hook 現況
- 已成功取得 `GYRO.BIN`：93,984 bytes = 11,748 個連續樣本，padding 全為 0，證明 ring drain 與 8-byte framing 成功。
- 舊分析曾把描述子 `*(P+0x64)=2500` 當成 2500 Hz；新同拍 CinemaDNG 實測支持其單位是微秒，因此暫定 ODR 為 400 Hz、`tscale=0.0025`。
- `GYRO.BIN` 和後來的 `GYRO_shake.BIN` SHA-256／內容完全相同，後一次測試沒有產生新的可比較資料（可能是同名輸出未覆寫或舊檔被重新拷回）；因此不可把它當作第二次 motion response 驗證。
- 現有連續檔三軸 raw 統計（X/Y/Z）約為 mean `3.40/-77.66/-16.89`、std `9.73/13.75/8.63`，動態範圍小，較像靜置/輕微運動，不能用來解相機座標軸。
- 解析／暫定 GCSV 轉換工具：`codex/decode_sigma_fp_gyro.py`。輸出預設明標 orientation 與 sample rate 為 provisional，避免誤當完成校正。

## 下一步：讓 Gyroflow 真正可用
- ring 每約 1.5 秒 wrap；hook 每 VD 幀排空已成功。下一版應在輸出中加入批次 header（VD tick、ring head、copy count），用 `FUN_c02083b0` 的共用 clock 精確驗證 400 Hz、檢查漏樣與 drift。
- 輸出 **Gyroflow `.gcsv`**：`gscale=(π/180)/131≈1.33202e-4 rad/s/LSB`、`tscale=1/ODR`。加速度計是另一顆感測器，未完成座標對齊前先只輸出 gyro，不應直接混入 accel。
- sidecar 放 DNG 序列旁，靠 DNG TimeCodes/共用 VD 時鐘對齊；再用 Gyroflow optical-flow sync 解固定 offset 並檢查長片 drift。

## 同步問題與 Stage-4 設計（2026-08-17）
- 同拍測試為 358 幀、DNG `FrameRate=30000/1001`，影片長 11.9446 秒；gyro 為 3785 筆。按描述子 2500 us/sample（400 Hz）計算，gyro 只覆蓋 9.4625 秒，比影片少 2.4821 秒。故 Stage-3 raw stream **沒有可推導的錄影起點**，不能靠首尾硬對齊。
- 短期可用方案：錄影開始後做一次短促、清楚的旋轉脈衝，Gyroflow 用 optical flow 解固定 offset；片尾再做一次相同脈衝，首尾 offset 差用來驗證 400 Hz 與 clock drift。
- 正式方案：Stage-4 不再只串接 raw sample；每次 VD callback 寫一筆固定 header，再跟該批新增樣本。建議 header：`magic='GFV1'`、`vd_tick`、`ring_head`、`sample_count`、`flags(record_start/stop/wrap)`。VD tick 與 CinemaDNG frame index 同域後，可為每批樣本插值 timestamp。
- 若 `FUN_c02083b0` 確認為單調 VD tick，直接在 hook 內讀取；在完全確認 calling convention 前不得注入呼叫。保守替代是 hook 內自行累加 callback sequence，並另存 record start/stop 的 DNG frame counter。
- 驗收標準：開頭與結尾兩個同步脈衝對齊誤差皆小於 0.5 frame；30 分鐘測試首尾 offset 差小於 1 frame；所有相鄰 batch 的 sample count 符合 400 Hz / 29.97 fps（主要為 13 或 14 筆）。

### Stage-4 實作狀態
- 已完成 ARM hook：`codex/stage4_gyro_sync_hook.S`，load `0xC072DE64`，大小 `0x368` bytes；全段位於韌體原始全零 code cave。
- 每段檔案有 32-byte `GFS4` header：版本、2500 us/sample、record-start VD、camera/reel/clip、initial ring head。
- 每次 ring drain 有 16-byte `GFV1` header：VD tick、sample count、wrap flags，後接 `sample_count × 8` bytes 的 `X,Y,0,Z`。
- 呼叫 `FUN_c02083b0` 取得單調 VD counter；下一次實機以 batch tick 是否不倒退、29.97 fps 每 VD 約 13/14 gyro samples 驗證其時間域。
- SD Cinema path manager 位址 `0xC3438400`；hook 讀 camera id/reel/clip 並生成根目錄 sidecar（例如 `A001_003.GYR`）。同時由 AutoRun dump `PATHMGR.BIN`，首輪先核對片段號是否正確，若 off-by-one 再調整，不直接假定完成。
- Stage-4 實機結果：影片 `A001_001` 對應到 `A001_000.GYR`，確認 path manager 的 clip 是前一號；Stage-5 命名時加 1。
- Stage-4 使用的 `FUN_c0375900(0xC351FF44)` 僅表示電影模式，導致待機也持續收集；Stage-5 改用韌體 `ChangeMovieRecording` 實際寫入的狀態：`FUN_c035b2d0()` 回傳 `0xC347DF38`，byte `+0x157` 為 MovieRecording。
- `FUN_c02083b0()` 實為 CameraController 設定值 accessor，Stage-4 實測永遠為 0，並非 VD clock。Stage-5 改用 TickTimer `FUN_c002b6e0()`，其反編譯明確把 64-bit tick 換算為微秒並回傳低 32-bit 單調時間；約 71.6 分鐘 wrap，以 unsigned delta 處理。
- Stage-5 格式：`GFS5` v2 header 的 offset `0x0C` 是 record-start `timestamp_us`；每批使用 `GFT1, timestamp_us, sample_count, flags`。解碼器以每批排空時間向前按 2500 us 插值每個樣本，GCSV 使用 `tscale=0.000001`。
- 建置器：`codex/build_stage4_autorun.py` → `codex/autorun_gyro_stage4.txt`；解析器：`codex/decode_sigma_fp_gyro_stage4.py`。建置器會套用 ARM local-call relocations、檢查 cave 大小並重算 hook branch。
- Resolve:CinemaDNG + **Gyroflow OFX**(讀 .gcsv 同步好的專案)+ 調色,同一時間軸。DaVinci 原生穩定器是光學的、不吃陀螺。
- hook 是 code 注入(寫可執行 RAM):每條 ARM 指令 + branch 位移先算好審核再寫,逐步、只碰驗證過的位址。
