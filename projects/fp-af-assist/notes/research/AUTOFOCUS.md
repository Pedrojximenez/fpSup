# SIGMA fp / fp L — 自動對焦(AF)系統反編譯細節

模組:`src/library/CameraController/AfMgr/`(核心)+ `src/library/DetectionMgr/`(臉/眼/追蹤)
+ `src/hal/Lens/src/LensLmount/LmountFocus*.cpp`(鏡頭驅動)+ `src/driver/AF/src/af_common.cpp`。
反編譯位址:AF 核心函式在 **blk_c02.c**(0xC0200000–0xC02FFFFF 區),已具名。

## 1. AF 原理:對比偵測爬山(CDAF)+ 「每脈衝離焦量」預測

fp/fp L 感光元件(IMX410/IMX455)**無片上相位對焦**,AF 是**對比爬山**:
- **對焦評價值 = YLevel**(亮度/對比,經 HPF)。計算器:`YLevelCalculatorTH` / `YLevelTargetTH` /
  `YLevelFaceCalculatorTH`。可用 shell `ae ylevel {current|center|spot|multi|ave4|aveq}` 即時顯示。
- 演算法非單純盲爬山,而是用**斜率 → 每脈衝離焦量(DefocusPerPulse)**預測要驅動多遠,
  模擬相位對焦的「一步到位」。關鍵函式:
  - `CalcCafDriveSpeed`(@blk_c02:77963)— 依離焦/斜率算驅動速度
  - `CalcPdCafDriveDir` / `CafPdDriveMain`(@blk_c02:50093)— 算方向並驅動
  - 峰值判定:`"peak detect! contrast search"` / `"...reverse direction retry"`(找到峰值後反向微調)
  - 近端估計:`SAF_EstimateCore_NearAfAfterSearchPeak`、`NEAR_AF step=… NextRoute=…`

### 每顆鏡頭的離焦標定
- 鏡頭回報 `DefocusPerPulse`(thin/max/min/ave/now 五種),韌體據此把「對比斜率」換算成「要送幾個脈衝」。
- `"[Defocus Per Pls]"` / `"[Scale Defocus Per Pls]"` / `"defocus data table public: %d 0x%06x %5d byte"`
  → 有一張**每鏡頭離焦資料表**。

## 2. 六種驅動策略(AfMgrProcess*)

依情境切換不同爬山策略(`src/.../AfMgr/src/Process/`):

| Process | 用途 |
|---|---|
| `AfMgrProcessFast` | 快速大步搜尋 |
| `AfMgrProcessSlow` | 精細小步收斂 |
| `AfMgrProcessNear` | 近端優先搜尋 |
| `AfMgrProcessRocking` | **搖擺(wobble)判方向**——先小幅來回確定對比往哪邊升 |
| `AfMgrProcessHybrid` | 混合 |
| `AfMgrProcessContShooting` | 連拍中的 AF |

驅動底層(`AfMgrDriveBase`):`AfMgrDriveScan`(全程掃描)/ `AfMgrDriveIntermittent`(間歇驅動)。
連續 AF:`AfMgrContinuous`;單次:`AfMgrSingle` / `AfMgrModelSingleBase`。

## 3. ★ 意外發現:韌體帶有 PDAF(相位對焦)程式碼

儘管 fp/fp L 官方是**純對比 AF**,韌體卻含完整相位對焦路徑:
- `AfMgrPhaseDetection.cpp`、`AfMgrMeasurePdafDefocus.cpp`
- `CafMode5_CheckPdaf` / `CafMode5_JudgeDrive` / `CafMode5_CalcDrivePulse` / `CafMode5_LastDrivePulse`
- log:`"###### not drive pdaf . do near af"`(**PDAF 不可用時 → 退回近端對比掃描**)

**判讀**:`AfMgr` 是 SIGMA 跨機種共用的 CameraController 函式庫,PDAF 路徑為**具 PDAF 之機種**而寫;
在 fp/fp L 上 `CafMode5_CheckPdaf` 走「無 PDAF → do near af」分支,實際仍是對比 AF。
即:**這是共用庫的相位對焦能力,在本機被停用/退化**,不代表 fp 能做相位對焦。

## 4. 臉 / 眼 / 追蹤偵測(DetectionMgr)

fp 有完整主體偵測(`src/library/DetectionMgr/`):
- **臉+眼**:`FaceAndEyeDetectionFunc.cpp`、`EyeDetectionFunc.cpp`;支援 **360° 臉偵測**
  (`"360 deg Face Detection = %d"`);眼偵測有時序遙測(`eye_detection:Freq=…,detect=…ms`)。
- **追蹤**:`AutoTracking.cpp`;兩種追蹤器並存——
  `AatInterfaceColorTracking`(色彩)與 `AatInterfaceHistTracking`(直方圖,`AAT_HIST_TRACKING_OPTIMIZED.cpp`)。
- 選單:`FaceDetectionAFButtonMenu`、`SetFaceDetectMode`;LiveView 疊圖 `LV_FaceDetectPos*`。
- 偵測結果回饋 AF:`ControlFaceDetectionAF` → 把臉/眼框餵給 `YLevelFaceCalculator` 當對焦區。

## 5. 運動預測(AF-C 追焦)

`AfMgrMortionPredict.cpp`:對移動主體外插下一格對焦位置。
- `"motion prediction peak correction....pos=%d >> %d"`、`"out of peak correct range in motion predict"`
- 有 `[Focus Tracking table]` / `[Scale Tracking table]`(追焦速度標定表)。
- 可 shell `predict` 輸出、`predict_dis` 停用。

## 6. ★ 意外發現:AF 量測 log 是加密/擾亂的

`src/library/CameraController/AfMgr/src/Measure/AfMgrEncryptLog.cpp` —
- 字串 `"encrypt log."`、`"[encrypt log option]"`、`"Scramble Decoding"`、`"wo_encryption"`(不加密選項)。
- shell:`af msr elog act`(啟動記錄)/ `elog out`(輸出)/ `elog cnv [filename]`(解碼轉檔)。
- **這是整份韌體裡唯一實作「加密/擾亂」之處**(其餘只有 byte-sum/CRC/BCH)。SIGMA 用它保護
  AF 調校資料不被讀出。是擾亂(scramble)非強加密,但值得記一筆。

## 7. AF 遙測欄位(加密 log 的記錄結構)

`cafdmp`(dump CAF running data to card)輸出的 A/B 索引欄位:
```
[A1] cal_caf_pulse_route      [A2] cal_caf_pulse_route_b   [A3] cal_caf_climb_pulse_route
[A4] drive_dir_chgpass        [A5] peak_count_chgpass      [A6] dir_count_chgpass
[A7] data_slope(/max)         [A8] data_slope_diff / slope_dec_rate
[A9] caf_mpos_inf             [A10] caf_mpos_near          [A11] agc_gain_monit / convert_mpos2distance
[A12] GetAfDistance / peak_dist  [A13] Prev2Pos/Prev4Pos/GetCcdMode  [A14] peak_count_clr_chgpass
[B1] {start/max/over}_pulse_at_caf_mtr_sync, opposite_dir_count
[B2] cal_caf_pulse_(oem_)result, (abs)af_pulse   [B3] not_climb/predict flags, judge_area/hpf
[B4-B9] peak-check 資料(now/max/min/peak/pos/reverse_pos/prev2)  [B10] caf_area_ylevel
[B11] drive_ctrl_at_mtr_ctrl  [B12] Fno   [B13] judge_states_pass
```
→ 內含 motor position(mpos)inf/near 端點、距離換算、AGC 增益、Fno、峰值統計。

## 8. 鏡頭對焦驅動介面(L-mount)

`LmountFocus.cpp` / `LmountFocusL`(L 鏡)/ `LmountFocusMc`(Mount Converter 轉接)/ `LmountFocusNone`(無鏡)。
- 驅動指令:**`CMD_Focus`(L-mount drive command 5)**,以**脈衝(pulse)增量**驅動。
- 鏡頭回報停止:`"counter update because the lens stop. end point or target position reached"`。
- PTP 外部驅動觀察者:`XC_LensFocusDriveSubject` / `PtpLensFocusDriveObserver`
  → 這就是 PTP/GIMBAL 對焦指令最終落到的鏡頭層(見 `PTP_FOCUS.md`)。

## 9. 完整 AF shell 調試指令(`af msr …`)

```
af msr set arg1 arg2 arg3 (arg4)     設定 AF 參數
af msr setspd arg1 ...               設定驅動速度
af msr offset / moffset / adjoffset / safoffset   各種對焦偏移標定
af msr cafwob arg1 arg2              CAF 搖擺(wobbling)測試
af msr cafdmp arg1                   dump CAF 運行資料到卡
af msr safarea arg1 (arg2)(arg3)     單次 AF 區域
af msr elog act|out|cnv [file]       加密 log 啟動/輸出/解碼
saf_decel                            掃描減速資訊
focus bracket                        對焦包圍資訊
predict / predict_dis                運動預測輸出/停用
print_tracking                       追蹤除錯
(face)(eye)(tracking) 0=off 1=on     臉/眼/追蹤除錯開關
ae ylevel {current|center|spot|multi|ave4|aveq}   即時對比評價值顯示
```
`AfEvt disp:%d comp:%d succeed:%d drive:%d tracking:%d` = AF 事件狀態回報格式。

## 信心
- CDAF 爬山 + DefocusPerPulse 預測、六種 Process 策略、臉/眼/追蹤、運動預測、加密 log、
  脈衝驅動介面 —— **反編譯 + 字串確認**。
- 「PDAF 程式碼存在但在 fp/fp L 停用(走 do-near-af 分支)」—— **強推論**(有 `not drive pdaf . do near af`
  的 fallback,且感光元件無片上 PDAF);確切每機啟用與否需比對機身識別碼分支。
