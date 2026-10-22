# SIGMA fp Ver.5.02 內部陀螺儀／Gyroflow 研究歸檔

歸檔日期：2026-08-18（Asia/Taipei）  
狀態：Stage-5 實機擷取成功；Gyroflow 軸向、比例與單段時間偏移已由 CinemaDNG 光流實測校正。尚未完成鏡頭 profile、rolling-shutter readout、長片 clock drift 與正式自動同步。

## 一、結論摘要

- SIGMA fp 韌體內確實存在可用的三軸陀螺儀資料流，感測器識別為 TDK/InvenSense ICM20321。
- 主 ARM 可由 mailbox 描述子取得 sub-ARM shared RAM 中的 600-sample ring。
- 每筆樣本為 little-endian `int16 X, int16 Y, int16 padding=0, int16 Z`，共 8 bytes。
- 描述子數值 `2500` 經 Stage-5 單調微秒 TickTimer 實測，確定是約 **2500 samples/s**；每筆週期約 **400 us**。早期「2500 us/sample = 400 Hz」判斷已推翻。
- Stage-5 實拍取得 58,489 筆樣本，TickTimer span 23.378287 秒，實測約 2501.85 samples/s，檔案結構完整且 timestamp 無倒退。
- 672 組相鄰 CinemaDNG 光流對照結果：raw X／Y／Z 與畫面 yaw／pitch／roll 的絕對相關係數分別為 0.984／0.951／0.907。
- Gyroflow orientation 實測為 **`YxZ`**。
- 本次鏡頭／模式的實測 `gscale` 暫定 **0.000121385 rad/s/LSB**；早期依 131 LSB/dps 推算的 0.000133231 高約 9.8%。正式定值仍需更多旋轉速度與溫度樣本複核。
- 本次片段的 gyro→video 固定時間校正為約 **575 ms**；已烘入校正版 GCSV。此數值不能直接假定適用所有片段，長片 drift 與每段自動起點仍待驗證。
- 目前方案和尼影 A1 一樣屬於 gyro-assisted post stabilization，不是物理雲台；能校正三軸旋轉，不能完整消除相機平移與近景視差。

## 二、已驗證位址與資料結構

### Ring 位址鏈

```text
mailbox pointer variable  0xC31E3FCC
P                         *(0xC31E3FCC) = 0x2E006004（實機值）
ring_base                 *(P + 0x60) = 0x2E00644C（實機值）
ring_end                  0x2E007710
ring span                 0x12C4 bytes（4-byte head + 0x12C0 payload）
payload                   600 × 8-byte samples
descriptor value          *(P + 0x64) = 2500（ODR，約 2500 Hz）
```

### Sample layout

```c
struct gyro_sample_le {
    int16_t x;
    int16_t y;
    int16_t padding; // always 0 in all validated captures
    int16_t z;
};
```

### 相關韌體入口

- 原 gyro thread hook site：`0xC00D0794`
- 被替換原始呼叫：`FUN_c01ec6f8 @ 0xC01EC6F8/9`
- Stage-5 code cave：`0xC072DE64`，程式大小 `0x368` bytes
- Cinema path manager：`0xC3438400`
- 真正 MovieRecording singleton accessor：`FUN_c035b2d0 @ 0xC035B2D0`
- MovieRecording flag：accessor 回傳物件 `+0x157`
- 單調 TickTimer 微秒 accessor：`FUN_c002b6e0 @ 0xC002B6E0`
- Stage-4 誤用的 `FUN_c02083b0` 是 CameraController setting accessor，實測為 0，不是 VD clock。

## 三、Stage 演進與實機結果

### Stage-3：連續 ring drain

- 成功寫出固定名稱 `GYRO.BIN`，證明 hook、ring drain 與 8-byte framing 可行。
- 缺點：無錄影起點、無 timestamp、固定檔名造成舊檔混淆。

### Stage-4：批次 header、動態命名初版

- 格式：`GFS4` file header + `GFV1` batch header。
- 實機影片 `A001_001` 卻輸出 `A001_000.GYR`，確認 path manager clip 在該讀取時點落後一號。
- `FUN_c0375900(0xC351FF44)` 只代表電影模式，不是正在錄影，故 gyro 錄了 185.6025 秒而影片僅約 28.40 秒。
- 所有假定 VD tick 都為 0，證明時間來源選錯。
- Stage-4 檔案本身結構完整，錯的是狀態／時間語意。

### Stage-5：真正錄影狀態與微秒 timestamp

- 改用 MovieRecording flag，只在實際錄影期間啟停。
- clip number `+1`，影片與 GYR 均為 `A001_001`，配對成功。
- 格式：32-byte `GFS5` v2 header；每批為 16-byte `GFT1` header，欄位 `timestamp_us, sample_count, flags`，後接 raw samples。
- 實機結果：

```text
video                 A001_001, 673 DNG, frame numbers continuous
GYR                   A001_001.GYR, 486,664 bytes
batches               1,170
samples               58,489
TickTimer span        23.378287 s
nominal gyro duration 23.395600 s at 2500 Hz
measured rate         ~2501.85 Hz
timestamp regressions 0
ring-wrap batches     97
structural truncation none
```

## 四、Gyroflow 校正

校正工具以每對 DNG 估算 RANSAC affine motion，再將畫面中心 dx、dy、roll 與三軸 gyro 在不同時間偏移下做相關搜尋。

```text
image dx (yaw)   ↔ raw X  corr = -0.98436  best shift ≈ 0.575 s
image dy (pitch) ↔ raw Y  corr = +0.95120  best shift ≈ 0.575 s
image roll       ↔ raw Z  corr = -0.90661  best shift ≈ 0.570 s
```

由影像運動與相機旋轉的相反方向換算，Gyroflow orientation 為 `YxZ`。roll 是不依賴焦距的角度量，可用來估 `gscale`；本輪得到約 `0.000121385 rad/s/LSB`。由 yaw 位移反推的等效焦距亦與畫面尺寸／測試鏡頭量級一致，提供交叉驗證。

校正版檔案：`codex/captures/stage5_converted/A001_001_calibrated.gcsv`

- `orientation,YxZ`
- `gscale,0.000121385`
- `tscale,0.000001`
- 已移除前 575,000 us 並把時間重設接近 0
- 57,052 筆、末 timestamp 22.825422 秒、無 timestamp regression

建議 Gyroflow 初始設定：低通約 50 Hz、gyro offset 0（僅限上述校正版）、平滑度先 20%。目前尚無鏡頭 profile，因此不可用裁切、邊緣變形或最終觀感評判演算法上限。

## 五、已知限制與尚未完成

1. `GFS5` header 的欄位仍保存歷史 descriptor value 2500；解析器已相容地將大於等於 1000 的值視為 Hz 並換算 400 us，但下一版格式應明確區分 `sample_rate_hz` 與 `sample_period_us`。
2. batch timestamp 是排空時間，逐樣本 timestamp 以 400 us 向前插值；尚未取得 IMU data-ready 的逐樣本硬體 timestamp。
3. 目前 TickTimer 與影格起點仍靠光流求固定 offset，尚未證明與 CinemaDNG frame clock 同域。
4. 尚未完成 2–30 分鐘長片首尾 drift 測試。
5. 尚未校正各拍攝模式的 rolling-shutter readout time。
6. 尚未建立鏡頭 profile；變焦鏡需按焦段分別處理。
7. `gscale`、bias、溫漂、飽和量程需用更多受控旋轉測試複核。
8. 未混入 MMA8452Q accelerometer；在兩顆感測器座標與時間未對齊前不應輸出 accel。
9. Gyroflow 只能以全域相機模型修正旋轉與 rolling shutter，不能完整修復平移、景深相關視差或已寫入影格的運動模糊。

## 六、安全與操作紀錄

- AutoRun 是 RAM-only ARM code injection；開機先還原 hook site，再寫 cave，最後安裝 branch。
- 彩條單閃表示 AutoRun 啟動；雙閃表示 hook 已安裝。
- 避免盲讀大範圍 `0xC3xxxxxx`；未映射位置曾造成相機凍結。只追蹤韌體實際 dereference 的有效指標。
- SD 卡測試寫入後必須 `sync` 並安全退卡。
- Stage-3、Stage-4 舊資料分別保留在 SD 卡 `STAGE3_ARCHIVE`、`STAGE4_ARCHIVE`；另有電腦備份。
- 本次歸檔時 SD 卡仍掛載，但本歸檔操作未修改卡片內容。

## 七、檔案索引

### 核心來源與工具

- `codex/stage5_gyro_timestamp_hook.S` — Stage-5 ARM hook
- `codex/build_stage5_autorun.py` — 組譯、relocation、cave 大小檢查與 AutoRun 產生器
- `codex/autorun_gyro_stage5.txt` — 已實機使用的 Stage-5 AutoRun
- `codex/decode_sigma_fp_gyro_stage5.py` — GFS5/GFT1 驗證與 GCSV 轉換器
- `codex/calibrate_sigma_fp_gyro.py` — DNG 光流／gyro 軸向、offset、比例校正工具
- `notes/projects/gyro-sup/GYRO_IMU_GYROFLOW.md` — 演進型研究筆記；含早期假設，閱讀時以本歸檔為準

### 擷取與轉換資料

- `codex/captures/fpGFTest_pre_stage4_20260817_2207/` — Stage-3 前卡片備份
- `codex/captures/fpGFTest_stage4_20260817_2226/` — Stage-4 實拍完整備份
- `codex/captures/stage5_converted/A001_001.gcsv` — 初始 Stage-5 轉換
- `codex/captures/stage5_converted/A001_001_calibrated.gcsv` — 光流校正版

## 八、核心檔案 SHA-256

```text
2d6a8ca62488fd8ea490d0312b789dd0b59104f6f3df1f8a44a741e6bc37b87e  stage5_gyro_timestamp_hook.S
7002f2918a4db8555bfdcc0ef76bc94e49d032387feec2d68a5b9a97c1fef0f2  build_stage5_autorun.py
2f0cee1f9bdc63ecb218633edefc3d14aa522bae304c2324c3df6257b753facb  autorun_gyro_stage5.txt
ce895352323937afd7b2d0d2e01ae16f94ebfcf2f0046a2a3d97a19a1268015e  decode_sigma_fp_gyro_stage5.py
e6b3ba509517a00896f515b34698bd883005c10b2734ba48c3f6d66e26b6fc36  calibrate_sigma_fp_gyro.py
76d36ff093e41fe0eb256869a36072e5fab4912f141b42c2bfd06cea3c19355a  A001_001_calibrated.gcsv
```

## 九、下一階段驗收順序

1. Stage-6 格式語意改正為 2500 Hz／400 us，預設輸出校正後 `YxZ` 與 `gscale`。
2. 建立指定鏡頭／解析度的 Gyroflow lens profile。
3. 以垂直線快速 pan 校正 rolling-shutter readout time。
4. 2–3 分鐘片段做首尾同步脈衝，量 clock drift。
5. 若 drift 可忽略，將每段起點 offset 自動化；否則建立線性 time-scale correction。
6. 完成短片、走動、長片與快速 pan 的實際效果驗收，再與尼影 A1 同場比較。

## 十、Stage-6 開發續記

2026-08-18 已完成 Stage-6 雙 256 KiB buffer、獨立 writer thread、GFS6/GFB6 block、CRC-32、GFE6 footer、drop/error diagnostics、AutoRun 建置器與 host-side parser。靜態與合成壓力測試通過；因 `fpGfTest` 在部署階段未掛載，尚未進行實機寫卡。詳細設計與首輪驗收見 `codex/STAGE6_DOUBLE_BUFFER_DESIGN_2026-08-18.md`。相機內停止後 GCSV conversion 尚未加入，必須先驗證背景 writer 不干擾 CinemaDNG。
