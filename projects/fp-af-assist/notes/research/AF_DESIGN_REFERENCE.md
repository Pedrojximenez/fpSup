# SIGMA fp CDAF 演算法設計拆解 — 給「自製自動對焦」的參考

> **2026-09-27 可達性更正：本文是早期綜合設計參考。** 第 2／4 節的 `CalcCafDriveSpeed`、PdCaf 等在 fp 5.02 被 capability gate 關閉，不能當成原廠 CDAF 已執行的 DFD／近峰減速。新的機內規劃以 [可達程式接點圖](FP_AF_FIRMWARE_INTERVENTION_MAP_2026-09-27.md) 與 `AF_AE_INTERNALS.md` 後續核對為準；原廠 608 容差也不能當作實測光學景深。下文保留歷史參考。

從韌體反編譯還原 SIGMA 的對比對焦(CDAF)設計原則。目的:讓你在做自己的 AF 時能借鏡
「怎麼把對比對焦做到接近相位對焦的速度與穩定度」。每節先講**原理**,再給**韌體證據/函式**。

---

## 0. 全貌:一句話

> 在對焦評價區內,對影像做**多頻帶高通濾波**取得對比值 → 用**每脈衝離焦量模型**把「對比曲線斜率」
> 換算成「該驅動多少」→ 邊驅動邊監測,**通過峰值後用三點拋物線內插**回推真正合焦位置 →
> 全程配合**速度規劃(近峰減速)**、**主體移動判定**與**運動預測**。

這幾招缺一不可,尤其「離焦量預測 + 峰值內插」是把 CDAF 從慢吞吞變快的關鍵。

---

## 1. 對焦評價值(contrast metric)— 訊號鏈

SIGMA 稱這套暫存器為 "AF register"。評價值 = YLevel。訊號鏈參數(shell 可調):
`sens / hpf / gup / lpf / sft / mdn`

順序(推定,依名稱與慣例):
```
評價區像素(Y 或 RGB) 
  → 每通道增益 af_sens / RGBgain / af_digital_gain   (補償不同色板)
  → LPF (lpf)      低通:先降噪,避免雜訊被當成邊緣
  → HPF (hpf)      高通:抽出邊緣能量 = 對比        ← 核心
  → median (mdn)   中值:壓掉脈衝雜訊尖點
  → shift (sft)    位移/縮放
  → 區內累加(EvalLineInArea,逐行) → YLevel
  → AGC 正規化(除以 gain/shutter/fno 的影響)
```

### ★ 關鍵招數 A:多頻帶 HPF(同時量粗細兩個頻帶)
韌體同時保有 **HPF_HIGH 與 HPF_LOW 兩組截止**(`HPF_H`/`HPF_L`, `hpf_high`/`hpf_low`,
`measure all hpf`, per sensor mode 一張表)。原理:
- **低頻 HPF**:即使嚴重失焦、畫面很糊時仍有響應 → 用來**判方向、粗定位**(遠離峰值也不會平掉)。
- **高頻 HPF**:只有接近合焦才有強響應、峰銳利 → 用來**精定位、找真峰**。
- 兩頻帶並用 = 遠處靠低頻拉近、近處靠高頻收斂。**這是你自製 AF 最該抄的一點。**
- 注意韌體註記:`the number of hpf setting should be set to an even number`(HPF tap 數需偶數,線性相位)。

### ★ 關鍵招數 B:評價值必須對曝光正規化
`aft: gain=%d shutter=%d fno=%d ... (now->)` — 每次量測記錄當下 gain/shutter/Fno。
對比原始值會隨曝光/增益漂移,**不正規化就會誤判斜率**。做自己的 AF 一定要把 AE 狀態一起帶進來補償。

### 評價區
多區(`AreaNum`)、逐行累加(`EvalLineInArea`);臉/眼偵測會把偵測框當評價區
(`YLevelFaceCalculator`)。shell `ae ylevel {center|spot|multi|ave4|aveq}` 可即時看評價值。

---

## 2. ★ 關鍵招數 C:每脈衝離焦量預測(讓 CDAF 快起來的核心)

純爬山的缺點:不知道「離峰多遠、該走多快」,只能一步步試。SIGMA 用一個**離焦模型**解掉:
- 每顆鏡頭標定 `DefocusPerPulse`(thin/max/min/ave/now 五態,存於每鏡頭離焦表
  `defocus data table public: … byte`)。
- 由**對比曲線斜率(data_slope)+ 斜率遞減率(slope_dec_rate)**估計「現在離峰還有多少離焦量」,
  再除以 DefocusPerPulse → **直接算出要驅動幾個脈衝**,而不是盲目小步。
  函式:`CalcCafDriveSpeed`、`CalcPdCafDriveDir`、`CafPdDriveMain`、`CafMode5_CalcDrivePulse`。
- 驅動量會**夾限**:`clip drive pulse: cnt_=%d, max_cnt=%d`(避免衝過頭撞端點)。

> 自製 AF 對應做法:先跑一次校正掃描,建你自己鏡頭/馬達的「對比斜率 ↔ 離焦距離 ↔ 步數」對照,
> 之後就能用單次量測估算驅動量,而非逐步試探。

---

## 3. 峰值搜尋狀態機

流程(從 log 還原):
1. **判方向**:先動一小步看評價值升降;分不清就用 **Rocking/wobble**(`AfMgrProcessRocking`,
   `caf drive wobbling`)小幅來回,靠低頻 HPF 響應定方向。
2. **爬升驅動**:朝評價值上升方向以第 2 節算出的步數驅動(`AfMgrProcessFast` 大步 →
   接近時 `AfMgrProcessSlow` 小步)。
3. **越峰確認**:監測評價值開始下降(`down_chk`、`detect peak... pos, max, min`);
   確認已過峰才停(不能一升就停,可能是雜訊/局部)。
4. **★ 關鍵招數 D:三點拋物線內插求真峰**(`calIntrPolAreaAfPeakPoint`):
   真峰幾乎不落在取樣點上。取峰值鄰近 3 點(邊界時取 [0,1,2] 或末三點,否則 [peak-1,peak,peak+1]),
   擬合拋物線求頂點 → **次脈衝精度**的合焦位置(`AF_CalcInitPosToPeakPos` / `AF_CalcStopPosToPeakPos`
   從起點/停點回推峰位)。**這步決定最終銳利度,務必做。**
5. **回驅**:算出真峰後把馬達開回該位置(考慮**背隙 backlash**:`start_pulse/max_pulse/over_pulse
   _at_caf_mtr_sync`、`opposite_dir_count` 記錄反向次數做背隙補償)。
6. **合焦判定**:`settled` / `CafStable`;`CafTime To1stPeak / ToStable` 記錄首峰與穩定耗時。

### 找不到峰的退場
- `peak not detect! reverse direction retry`(反向再找)
- `peak not detect! scan drive. rate=%d, dof=%d, subject_move=%d`(全程掃描,參考景深 DOF 與主體移動)
- `katayama`(片山 = 單邊斜率:峰在搜尋範圍外)→ 判定需往某端繼續。
- 最終失敗:`ng no peak`。

---

## 4. ★ 關鍵招數 E:速度規劃(近峰減速)

不是等速驅動。`CalcCafDriveSpeed` 依離焦量給速度:遠時快、近峰減速(`saf_decel`
"deceleration info during scanning")。太快會**衝過峰又量不到細節**;近峰慢才抓得到內插所需的密集取樣。
速度以 `speed ratio to maximum speed [x256]`(定點分數)表示。

---

## 5. 連續 AF / 動態主體(AF-C)

- **主體移動判定**:`JudgeSubjectMoveByPeakData` / `CorePeakPosEstimateSubjectMove` —
  比較歷次峰位(`l_CorePos`, `PeakPos`, `l_AvgSpeed`, `DiffTime`)判斷主體是往前/往後移動還是靜止。
- **運動預測**:`AfMgrMortionPredict` — 對移動主體外插「下一格拍攝時」的對焦位置
  (`motion prediction peak correction pos=%d >> %d`),並夾限在合理範圍
  (`out of peak correct range in motion predict`)。
- **連拍中對焦**:`AfMgrProcessContShooting`(`start continuous shooting af: pos step prev_frame`)
  用上一格資訊預測本格,不從頭搜。
- 歷史位置緩衝:遙測有 `Prev2Pos` / `Prev4Pos`(保留前 2/前 4 幀位置做外插)。

---

## 6. 臉/眼/追蹤如何餵給 AF

`DetectionMgr`:臉+眼(`FaceAndEyeDetectionFunc`,360° 臉)、色彩追蹤 + 直方圖追蹤
(`AatInterfaceColorTracking` / `AatInterfaceHistTracking`,`AAT_HIST_TRACKING_OPTIMIZED`)。
偵測框 → `ControlFaceDetectionAF` → 設成 AF 評價區 → 之後照第 1–5 節跑對比對焦。
即:**偵測只負責「對哪裡」,合焦仍是 CDAF**。

---

## 7. 給你自製 AF 的抄作業清單(優先序)

1. **多頻帶 HPF**(粗頻帶判方向/防迷路 + 細頻帶找銳峰)—— CP 值最高。
2. **三點拋物線峰值內插** —— 決定最終銳利度,實作簡單。
3. **評價值對 AE(gain/shutter/fno)正規化** —— 否則斜率會被曝光變化污染。
4. **離焦量預測驅動**(先建 斜率↔步數 校正表)—— 把「逐步試」變「一次估到位」。
5. **近峰減速的速度規劃** —— 兼顧快與準。
6. **越峰才停 + backlash 回驅補償** —— 穩定度。
7. AF-C 才需要:**主體移動判定 + 運動預測 + 前幀位置緩衝**。

---

## 附:關鍵函式/位址(seg0,反編譯在 blk_c02.c)
| 函式 | 作用 |
|---|---|
| `CalcCafDriveSpeed` @blk_c02:77963 | 依離焦/斜率算驅動速度 |
| `CafPdDriveMain` @blk_c02:50093 | 主驅動(算方向+步數並下驅動) |
| `CalcPdCafDriveDir` | 算驅動方向 |
| `calIntrPolAreaAfPeakPoint` @blk_c02:63894 | 三點峰值內插 |
| `AF_CalcInitPosToPeakPos` @blk_c02:73441 | 由起點回推峰位 |
| `JudgeSubjectMoveByPeakData` @blk_c02:72815 | 主體移動判定 |
| `CorePeakPosEstimateSubjectMove` @blk_c02:73319 | 主體移動速度估計 |
| `CafMode5_CalcDrivePulse` / `CafMode5_JudgeDrive` @blk_c02:79165 | (共用庫)含 PDAF 分支的驅動 |

> 相關筆記:對焦硬體/指令面見 `AUTOFOCUS.md`;錄影中對焦閘控見 `PTP_FOCUS.md`;鏡頭脈衝驅動見 `LmountFocus`。
