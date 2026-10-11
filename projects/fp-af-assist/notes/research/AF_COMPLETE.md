# SIGMA fp — 對焦系統完整說明(方法、細節、用到的鏡頭資料)

彙整自韌體反編譯(fp Ver.5.02)+ 實機 dump(SIGMA 28mm Art、Panasonic LUMIX S 40/F2)。
相關:`AUTOFOCUS.md`(模組地圖)、`AF_DESIGN_REFERENCE.md`(演算法設計)、`LENS_DATA_ACCESS.md`。

---

## 第一部分:對焦方法與細節

### 1. 原理:對比偵測爬山(CDAF)+ 離焦量預測
fp/fp L 感光元件(IMX410/455)**無片上相位對焦**。對焦靠**影像對比**:
- **評價值 YLevel** = 評價區像素經濾波鏈的邊緣能量:
  `每通道增益 → LPF(降噪) → HPF(抽邊緣=對比) → median(去脈衝雜訊) → 區內逐行累加 → 對曝光正規化`。
- **多頻帶 HPF**(HIGH + LOW 兩組截止):低頻在嚴重失焦時仍有響應(判方向/粗定位),
  高頻只在近合焦銳利(精定位)。per sensor mode 一張 HPF 表。
- **評價值對 AE 正規化**:每次量測帶當下 gain/shutter/Fno,補償曝光漂移。
- 核心函式(blk_c02):`CalcCafDriveSpeed`、`CalcPdCafDriveDir`、`CafPdDriveMain`。

### 2. 六種驅動策略(AfMgrProcess*)
`Fast`(大步)/`Slow`(小步收斂)/`Near`(近端優先)/`Rocking`(搖擺判方向)/
`Hybrid`/`ContShooting`(連拍中)。底層:`DriveScan`(全掃)/`DriveIntermittent`(間歇)。

### 3. 峰值搜尋狀態機
1. 判方向(小步或 Rocking 搖擺,靠低頻 HPF)。
2. 爬升驅動(離焦量預測算步數;`Fast`→接近時`Slow`)。
3. 越峰確認(監測對比下降 `down_chk`,確認過峰才停)。
4. **三點拋物線內插求真峰**(`calIntrPolAreaAfPeakPoint`)→ 次脈衝精度合焦位置。
5. 回驅(含 **backlash 背隙補償**:記錄反向次數)。
6. 合焦判定(`settled` / `CafStable`)。
- 找不到峰:反向重試 → 全程掃描(參考 DOF、主體移動)→ `ng no peak`。

### 4. 連續 AF / 動態(AF-C)
- **主體移動判定**:`JudgeSubjectMoveByPeakData`(比較歷次峰位)。
- **運動預測**:`AfMgrMortionPredict`(外插下一格對焦位置)。
- 前幀位置緩衝:`Prev2Pos`/`Prev4Pos`。

### 5. 主體偵測(餵給 AF「對哪裡」)
`DetectionMgr`:臉+眼(360° 臉偵測)、色彩追蹤 + 直方圖追蹤。偵測框 → `YLevelFaceCalculator`
當對焦評價區。**偵測只負責選區,合焦仍是 CDAF**。

### 6. AF 遙測(加密 log)
`AfMgrEncryptLog`(擾亂/scramble,非強加密)記錄 `[A1]…[B13]` 欄位(mpos 端點、距離、AGC 增益、
Fno、峰值統計等)。shell `af msr elog act/out/cnv`、`cafdmp`。

### 7. 鏡頭驅動介面
L-mount `CMD_Focus`(drive command 5),**脈衝(pulse)增量**驅動。鏡頭回報停止
(端點/目標到達)。PTP/GIMBAL 對焦最終落到 `PtpLensFocusDriveObserver`。

---

## 第二部分:AF 用到的「外部鏡頭資料」

### 8. AF 核心 vs 鏡頭資料:誰是必要
- **合焦回授(對比 YLevel)= 來自感光元件,不靠鏡頭。** 這是 AF 的最小可運作核心。
- **鏡頭給的資料是「加速/精度先驗」**:讓 CDAF 快、準、穩,但**非不可或缺**(有 `use default param` fallback)。

### 9. AF 實際消費的鏡頭參數(dumpLensData 欄位,struct offset)
| 參數 | offset | AF 用途 |
|---|---|---|
| **focus pps min / max / movie** | +0x78 / +0x7c / +0x80 | 對焦馬達速度上下限 |
| **DefocusPerPulse**(thin/max/min/ave/now) | 鏡頭資料表 | 把對比斜率換算成「該驅動幾脈衝」= 快速一步到位的關鍵 |
| **focus backlash** | 鏡頭資料 | 反向驅動背隙補償 |
| **對焦端點 / EndPointInformation** | 能力旗標 | 找/重設位置參考原點 |
| **NeedFocusPlsReset / IsFarEdgeResetLens** | 能力旗標 | 是否需脈衝歸零、遠端重設 |
| **CanAutoFocus / AfPossible / FocusSpeedControl** | 能力旗標(+0x64) | 能不能 AF、能否控速 |
| **open effective fno** | 鏡頭資料 | 離焦/景深計算 |
| **對焦距離支撐點表**(位置↔距離) | lens_data **+0x348c**(距離)/ **+0x3564**(位置),點數 **+0x3488** | 距離顯示、DOF、AF 離焦量先驗 |

### 10. ★ 對焦距離支撐點表(實機 dump 證實)
鏡頭資料塊(magic `_LENS_DATA_:`)含**兩條同 index 配對的支撐點陣列**:距離 `D[]`（mm，遞減，首值=∞）
與內部位置 `P[]`（遞增）。換算 = **在 1/距離(倒數/屈光度)空間做分段線性內插**(韌體 `XC_Linear` / `FUN_c033e0d8`)。

| 鏡頭 | 對焦表(來源 +0x348c/+0x3564) |
|---|---|
| **SIGMA 28mm F1.4 DG HSM Art** (0x6010) | 19 點,距離 ∞→278mm,位置 4096→13369 |
| **Panasonic LUMIX S 40/F2** (0x4027) | 10 點,距離 ∞→300mm,位置 6276→10706 |

- **兩家(含第三方)都提供真實的距離校正曲線**,只是支撐點數不同。
- ⚠️ 更正:早前曾寫「SIGMA 非線性、Panasonic 只給線性」——那是抽到韌體**中間域錯表**(9000–37000)
  的誤判。正確表在 `+0x348c/+0x3564`。原理見 `FOCUS_DISTANCE_PRINCIPLE.md`。
- ⚠️ 表裡「位置」是鏡頭**內部域**(≠ PTP focus_pos),中間差一層線性換刻度。

### 11. 這些鏡頭資料哪裡來、怎麼拿
- **來源**:鏡頭 ROM,開機時 `DownloadLensData` 經 L-mount 下載進相機 RAM(不在韌體檔內)。
- **PTP/GIMBAL 可讀**:目前 focus_pos、focal length、光圈、AF 狀態(即時)。
- **PTP/GIMBAL 讀不到**:DefocusPerPulse、距離表、pps、backlash、端點(校準表層)。
- **要拿校準表** → 用 SOP:`AutoRun` + `mem save` dump 記憶體 → parser(見 `SOP_LENS_EXTRACT.md`)。

### 12. 對「自製 AF」的結論
- **必要**:影像對比 + 位置讀/驅動。有這兩個就能做(盲爬山)。
- **可自校**:DefocusPerPulse / pps / backlash —— 驅 N 脈衝量對比峰位移即可自建。
- **距離曲線**:原廠與副廠鏡頭**都有提供**(見 §10),可直接用;要純自製也能自校。
- **抄 SIGMA 的招**(見 `AF_DESIGN_REFERENCE.md`):多頻帶 HPF、三點峰值內插、評價值對曝光正規化、
  離焦量預測、近峰減速、越峰才停+背隙回驅。
