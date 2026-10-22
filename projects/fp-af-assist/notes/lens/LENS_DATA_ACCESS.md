# SIGMA fp — 鏡頭資料:關鍵參數 + PTP/GIMBAL 可讀性

原程式／證據目錄：[research/lens/notes](../../../../research/lens/notes/)。筆記已集中至 fp-af-assist；下文歷史結果與限制保留。

問題:鏡頭給相機的資料裡哪些關鍵?哪些能用 PTP / GIMBAL 抓?

## 鏡頭經 L-mount 提供的完整資料(shell `dumpLensData` 可印)

來源:`LmountData.cpp` / `LensData_factoryLmount.cpp` / `LmountProtocol.cpp` / `LmountSpi.cpp`。
- **身份**:lens id(0x%04x)、type code(0x%04X)、serial、fw ver(%d-%d-%d-%d / hex)、
  sys ver、name、maker name、LensType。
- **能力旗標**:OIS on/off 開關、光圈環、OIS Panning 開關、**支援 T-Value 資料**。
- **焦段/光圈**:wide/tele focal length、current focal length、aperture open limit。
- **校正表**(逐鏡頭,Q15 定點,開機下載進 RAM):distortion、extra distortion、shading、
  extend_vignetting、MTF、**T-value**、distance correction(center/horizontal/vertical × H/L ×
  stationary/af light)。
- **AF 標定**:**DefocusPerPulse**(thin/max/min/ave/now)、距離支撐點表(mpos,focus_pos,distance,
  af_d600/d300 min/max)。
- **PDAF 資料**:`LmountPdaf.cpp`(共用庫,fp/fp L 停用)。

---

## 分兩層看「能不能抓」

### 第一層 — 即時狀態:PTP / GIMBAL **可讀** ✅

經 `GetCamDataGrp1..6` / `GetCamDataGroupFocus` / GIMBAL getter:

| 參數 | PTP/GIMBAL 管道 | 備註 |
|---|---|---|
| **focus_pos**(對焦位置,16-bit 抽象值) | `GetCamDataGroupFocus`→`[Foc]focus_pos`;`GIMBAL_GetFocusPosition`(0x9405) | 讀;寫用 0x9412 絕對 / 0x9411 相對 → **可閉迴路** |
| focus_driving | `[Foc]focus_driving` | 是否驅動中 |
| CurrentLensFocalLength | `GetCamDataGrp1`(%04x) | 變焦位置 |
| LensWide/TeleFocalLength | `GetCamDataGrp3`(%04x) | 焦段範圍 |
| Aperture / ApertureOpenLimit | `GetCamDataGrp1` + `LensApertureOpenLimitChangedObserver` | 光圈 |
| Opt_crct_{distortion,Mag_col,diffraction,Light_intensity,shading} | `GetCamDataGrp4` | **只有開/關,無係數** |
| AFMode/AFAreaMode/AFLock/FocusArea/**FocusLimit** | Grp2 / [Foc] | AF 設定 |
| DNG_image_quality | `GetCamDataGrp4` | 影響 bit depth |

`GIMBAL_GetFocusPosition`(0x9405,`FUN_c04eef50`)實作:需 mode==2(LiveView)否則回 `0x200f`;
回 `param[0]=1`(有效旗標)、`param[1]=focus_pos`(`FUN_c035fd48`,與 shell `setfpos` 同一抽象位置)。

### 第二層 — 校正係數表:PTP / GIMBAL **抓不到** ❌

不在任何 CamDataGroup,只存在鏡頭 ROM / 內部 RAM:
- **DefocusPerPulse**、**距離校正表(mpos↔距離)**、對焦近/遠端限位
- distortion / shading / extend_vignetting / MTF / **T-value** / distance correction 係數
- PDAF 資料
- lens serial / type code / fw ver / **name** / maker(身份資訊也不在 CamDataGroup)

> ⚠️ 對「自製 AF」**最關鍵的三個(DefocusPerPulse、距離表、近/遠限位)正好都在第二層**。
> 且 PTP 的 `focus_pos` 是**抽象正規化值**——非距離、非原始 mpos;要換算公尺得靠讀不到的距離表。

---

## 拿第二層的三條路

1. **Shell `dumpLensData`**(UART/debug 口)—— 直接印各表位址/大小/內容。最省事。
   (相關:`dumpLensInitTime`、`_LENS_DATA_:` header。)
2. **Tap L-mount SPI 匯流排**(`LmountSpi.cpp` / `LmountProtocol.cpp` / `LmountSync.cpp`)——
   body↔鏡頭原始協定,`DownloadLensData` 開機就走這條。硬體層,最完整;需接匯流排 + 解協定。
3. **自己實測反推**:驅動 N 脈衝、量對比峰位移 → 建自己的「脈衝↔離焦↔距離」校正表
   （這本來就是自製 AF 該做的標定;用 §第一層可讀的 focus_pos 當回授)。

---

## 給自製 AF 的實務結論
- **可用 PTP/GIMBAL 做的**:讀 `focus_pos` + 寫絕對/相對驅動 = **完整閉迴路對焦控制**(位置域)。
  加上焦距、光圈、AF 狀態,足以外部驅動一套對焦系統。
- **PTP 做不到的**:拿到原廠 DefocusPerPulse / 距離公尺數 / 近遠限位 —— 這些要靠 dumpLensData 或
  SPI tap 或自己標定。
- 若只在**位置域(focus_pos)**閉迴路(對比爬山用相機回授的 focus_pos),PTP/GIMBAL 就夠;
  只有要**距離域(公尺、超焦距、DOF 絕對值)**才被第二層卡住。
