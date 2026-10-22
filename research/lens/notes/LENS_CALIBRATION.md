# SIGMA fp — 鏡頭校正 / 感光元件校正資料 + AF log 「加密」澄清

## 一句話
校正的**程式碼與引擎**在韌體裡(可讀);校正的**實際數值**不在這個 `.bin`——
鏡頭光學校正住在**鏡頭 ROM**,機身/感光元件校正住在相機**NAND**(逐台出廠寫入)。

---

## A. 鏡頭光學校正(來源:鏡頭 ROM,開機下載)

程式:`src/hal/Lens/src/LensLmount/LmountData.cpp`、`LensData_factoryLmount.cpp`、`LmountMcData.cpp`
(轉接環)、`LmountMcOptData.cpp`、`LmountMcDataMtf.cpp`、`XC_LensData`、`DistConverter.cpp`。
套用引擎:`src/library/CameraController/OpticalCorrection/src/LmountTH/`
(`OpticalCorrectionLmount_TH.cpp`、`LmountL_THDistortion.cpp`、`LmountL_THShading_w71c1.cpp`、Mc 版)。

下載動作:`DownloadLensData`(log `%4dms DownloadLensData`)、`DownloadLensFirmVerData`、
shell `dumpLensData`。鏡頭攜帶的表(dump 會印各表位址/大小):
```
shading:            0x%06x %5d byte      周邊失光/暗角
distortion table:   0x%06x %5d byte      畸變
extra distortion:   0x%06x %5d byte      額外畸變(高階項)
extend_vignetting:  0x%06x %5d byte      延伸暗角
MTF:                       %6d byte      調變傳遞函數
Lateral Chromatic Aberration                倍率色差
T-Value                                     實際透光量(T 值)
distance correction: vertical H/L [stationary light]  距離相關校正
```
- 鏡頭需「允許」相機才可關閉:`CanDisableDistortionCompensation` / `CanDisableColorAberrationCompensation`。
- 套用結果會寫進 DNG:`MenuDngDevLensCorrectionHandler`、`CM_DNGDEV_Distortion`、`CM_DNGDEV_ColorShading`
  → CinemaDNG/DNG 內帶 lens correction 資訊。
- 選單控制:`SetLensDistortion`、`pic_distortion_mode`、`pic_chromatic_aberration_mode`、`pic_shading_mode`;
  測試模式 `distortion {default|force off|test mode}`、`aberration …`、`shading …`。

> ⚠️ 這些**數值不在韌體檔**,住在鏡頭 ROM。韌體只有「下載 + 套用」程式碼。

---

## B. 機身 / 感光元件校正(來源:相機 NAND,逐台出廠寫入)

程式:`src/library/CameraController/SensorAdjustment/`。管理器 `XC_AdjustDataMgrCore<T>`,
T ∈ {Sensor, Lens, IMU, BodyCommon, BodyOther};`LoadAdjustmentData` / `SaveAdjustmentData`
(每筆帶 `AdjustmentData ID = 0x%08X`);備份 `ImageDataBackup.cpp`。

校正項目(各一個 `SensorAdjustment*.cpp`):
| 項目 | 檔案 | 用途 |
|---|---|---|
| AGC | SensorAdjustmentAgc | 增益校正 |
| AWB | SensorAdjustmentAwb | 白平衡 |
| BDD | SensorAdjustmentBdd | (黑點/缺陷偵測類) |
| WDD | SensorAdjustmentWdd | (白點/缺陷偵測類) |
| Defectsort | SensorAdjustmentDefectsort | **壞點圖** |
| Shading | SensorAdjustmentShading(+CsCheck) | **暗/色 shading** |
| Acquired | SensorAdjustmentAcquired | 現場取得 shading |
| Custom | SensorAdjustmentCustom | 使用者色偏校正 |

Shading 硬體通道(XZ01 SIG0/SIG1 管線):`SIG0 DARK SHADING`、`SIG1 SHADING1`、
`SIG1 SHADING2_{GR,GB,R,B}` → 暗電流 + 各色板 shading。SRAM 載入:`XC_ShadingSram_w71c1`。

出廠校正 shell:`imager exe_shadingcheck` / `exe_acquired_shading` / `exe_shading`、
`ColorShadingCheck`、`CAM_SHADING_ADJ`、`ADJ_TIME SHADING:%03dsec`。

使用者可調 **Color Shading Adjustment**:10 組自訂(`set_colorShading_01..10`)、手動 index、
red/blue、依焦距/光圈(`SetLensColorShadingRed/Blue/FocalLength/Aperture`)。

AF 校正:`DefocusPerPulse` 表(每鏡頭)—— 見 `AF_DESIGN_REFERENCE.md` §2。

> ⚠️ 這些**逐台校正、住在 NAND**,不在韌體更新檔。韌體只有引擎 + 預設/fallback。

---

## C. 「加密檔」澄清 — 只是 AF 除錯 log 的擾亂

`src/library/CameraController/AfMgr/src/Measure/AfMgrEncryptLog.cpp` +
`XC_AfLogParser.cpp`(`XC_AfLogParserImpl`)。

- 對象 = **AF 執行期遙測 log**(前述 `[A1]…[B13]` 欄位),**不是韌體、不是校正資料**。
- shell:`af msr elog act`(啟動)/ `elog out`(輸出)/ `elog cnv [filename]`(解擾轉檔)。
- `wo_encryption` = 不加密選項;`Scramble Decoding` = 解擾。相關 `cinelog`/`cinelogone`/`cinelognow`。
- 性質 = **擾亂(scramble/obfuscation),非密碼學加密**。目的:避免現場 AF log 外流被讀出調校內幕。
- **不影響逆向 AF**:演算法程式碼是明碼(已讀出);擾亂只蓋住執行期 log 輸出。
- 這是全韌體唯一的「加密/擾亂」實作(其餘完整性只有 byte-sum / CRC32 / BCH-ECC,無簽章)。

---

## 對「改韌體 / 自製 AF」的意義
- 想拿**別家鏡頭的校正表** → 要從**鏡頭 ROM** 讀(L-mount `DownloadLensData` 協定),不在韌體。
- 想改**機身校正** → 動 NAND 的 AdjustmentData(逐台不同,風險高,改錯畫質壞)。
- 想參考**校正演算法**(如何套 distortion/shading)→ 讀 `OpticalCorrection*` / `DistConverter` 明碼即可。
- AF log 擾亂**不構成障礙**;要看 AF 內部數據可用 `cafdmp` + `elog cnv` 自行解。
