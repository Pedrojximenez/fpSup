# fp CinemaDNG profile tag A/B:Resolve 到底吃哪幾個標籤

2026-09-25。在既有素材上就地改 DNG tag、用 Resolve 實際渲染回讀。沒有連相機、沒有修改原始素材、RAW 像素一個 byte 都沒動。

## 結論

1. **Resolve 的 CinemaDNG 路徑會套用 `ProfileToneCurve` 和 `ProfileHueSatMapData1/2`** —— 兩種專案設定下都成立。先前「Resolve 只吃 ColorMatrix」的假設,被這輪推翻。
2. **只換 `ColorMatrix1/2` 不等同用 Standard 錄。** 矩陣只佔 OFF↔Standard 全部差異的 **約 4%**(你的專案設定:0.0028 / 0.0704)。
3. **五個 tag 整組移植就等同了。** `ColorMatrix1/2` + `HueSatMapData1/2` + `ProfileToneCurve`(1221 bytes)搬過去之後,與真的用 Standard 錄的差距落在「兩支不同 take」的底線之內。
4. **矩陣的差異雖小但性質不同:它只動飽和色、且難以事後復原。** 整幀平均 ΔE 被近六成的近中性像素稀釋;飽和度 0.20–0.35 那一段 ΔE 平均 3.3、p99 10.2。tone 曲線則是全畫面一致位移,一條曲線就能拉回來。

## 素材與變體

同機身(SN 91411817)、同鏡頭(LUMIX S 40/F2)、同 ISO 800 / 1/60 / f2、同 `AsShotNeutral`、同 `BaselineExposure`,相隔 111 秒錄的兩段 FHD 12-bit CinemaDNG:

- `A001_297` — PictureMode **OFF**,98 幀
- `A001_298` — PictureMode **Standard**,122 幀

五個 profile tag 在兩支素材的第 1 幀裡 **offset 與長度完全相同**,所以能就地覆寫:

| tag | 名稱 | offset | bytes |
|---|---|---|---|
| 50721 | ColorMatrix1 | 1042 | 72 |
| 50722 | ColorMatrix2 | 1114 | 72 |
| 50938 | ProfileHueSatMapData1 | 1320 | 864 |
| 50939 | ProfileHueSatMapData2 | 2184 | 864 |
| 50940 | ProfileToneCurve | 3048 | 1024 |

`build_variants.py` 產生七個變體,每個都驗過 RAW strip 的 SHA-256 與來源一致:

| | 底圖 | 換了什麼 | 改動 bytes |
|---|---|---|---|
| A | 298 Standard | —(對照) | 0 |
| B | 298 Standard | ToneCurve ← OFF 的 identity | 281 |
| C | 298 Standard | HueSatMap1/2 ← OFF 的 identity | 894 |
| D | 298 Standard | 上面兩者都換 | 1175 |
| E | 297 OFF | —(對照) | 0 |
| F | 297 OFF | ColorMatrix1/2 ← Standard 的 | **46** |
| G | 297 OFF | 五個 tag 全部 ← Standard 的 | 1221 |

F 就是 `colormatrix-ab-20260923/C_firmware_normal.DNG` 的配方,套在真正的 OFF cDNG 上。

## 兩支素材的 profile 內容(直接解 IFD)

| | HueSatMap(72 格) | ToneCurve(128 點) |
|---|---|---|
| OFF | 全部 `(0°, 1.000, 1.000)` = identity | `y == x` 完全線性 |
| Standard | 色相位移 −20°..+10°、飽和 ×0.887–1.300、明度 ×0.986–1.332 | 非線性,最大偏離 +0.272 |

Standard 的 tone 曲線取樣:`0.18→0.306`、`0.50→0.772`、`0.90→0.995`。

⚠ `exiftool -b` 會把這些 tag 轉成文字輸出,長度和數值都不對;要直接解 IFD。

## 渲染方法

`resolve_render.py`。每個變體單獨下一個 render job,只渲該片段的第 49 幀,輸出 TIFF RGB16。

兩組設定各跑一次:

- **default_project** — 新建空專案,`davinciYRGB`(非色彩管理),1920×1080
- **user_project** — 把使用者當時開著的專案 `ExportProject` 成 .drp 再 `ImportProject` 成副本。`davinciYRGBColorManagedv2`、時間軸 DaVinci WG / DaVinci Intermediate、輸出 Rec.709、2000×1334

用副本的理由:**Camera Raw 面板的狀態(解碼色域/Gamma、預製色調曲線、高光恢復)沒有暴露在 scripting API 的 `GetSetting()` 裡**(158 個 key 掃過,沒有任何 camera raw 項目),只能整個專案複製才能保證設定一致。原專案未被修改,跑完切回。

## 量測結果

完整數字在 `results.json`(含每組的 frame means、飽和度分佈、ΔE 分層、擬合矩陣)。

平均絕對差(輸出域 0–1)與 CIELAB ΔE76:

| 比較 | 內容 | user_project | default_project |
|---|---|---|---|
| A→B | 只差 ToneCurve | meanΔ **0.0706** / ΔE 6.71 | 0.1256 / ΔE 12.34 |
| A→C | 只差 HueSatMap | 0.0033 / ΔE 0.78 | 0.0072 / ΔE 1.68 |
| A→D | 兩個 look 標籤合計 | 0.0723 / ΔE 7.04 | 0.1287 / ΔE 13.01 |
| **E→F** | **只換 ColorMatrix** | **0.0028** / ΔE 0.96 | 0.0047 / ΔE 1.66 |
| E→A | OFF 原樣 vs Standard | 0.0704 / ΔE 7.26 | 0.1263 / ΔE 13.61 |
| **A→G** | **完整移植 vs 真 Standard** | **0.0044** / ΔE 0.79 | 0.0100 / ΔE 1.72 |
| D→F | 兩支不同 take 的底線 | 0.0038 / ΔE 0.64 | 0.0071 / ΔE 1.14 |

矩陣佔比:`0.0028 / 0.0704 = 4.0%`(user)、`0.0047 / 0.1263 = 3.7%`(default)。兩組一致。

**A→G 的 0.0044 與底線 D→F 的 0.0038 同量級** → 完整移植成立:剩下的差就是兩次按錄影鍵的差別。

### E→F 是乾淨的線性矩陣

user_project 擬合出來:

```
 1.2623  -0.4284   0.1652
-0.1050   1.2299  -0.1249
 0.0672  -0.5451   1.4786     列和 0.9991 / 1.0000 / 1.0008
```

殘差 mean **0.00022** —— 在 DWG/DI 管線裡依然是一個純矩陣,而且中性精確不動。這是「normal 矩陣 = 一層列和為 1 的跨通道修正」在實機渲染上的直接證實。

### 為什麼整幀平均看起來很小

user_project 的畫面飽和度:p50 = 0.038、p90 = 0.156、max = 0.589 —— **58.6% 的像素飽和度低於 0.05**,而矩陣照定義不動中性。分層之後:

| 飽和度 | 佔畫面 | E→F 的 ΔE76 mean / p99 |
|---|---|---|
| 0.00–0.05 | 58.6% | 0.46 / 1.4 |
| 0.05–0.10 | 22.6% | 1.12 / 2.0 |
| 0.10–0.20 | 12.7% | 1.88 / 4.2 |
| 0.20–0.35 | 4.4% | **3.33 / 10.2** |
| 0.35+ | 1.8% | 3.01 / 5.9 |

`matrix_on_swatches.py` 把實測矩陣套在代表性色塊上(結果在 `swatch_demo.json`):中性灰 ΔE 0.1、膚色 4.7、紅衣 15.6、淡綠葉 25.6、洋紅 30.1、飽和藍 36.5。

**這張圖經 DRT 後最高飽和度只有 0.589,所以 12.4 的整幀最大 ΔE 是下限不是上限。**

## 跟舊筆記對不上的一點

`native-calibration-20260924/README.md` 記錄使用者當時的 Camera Raw 是「預製色調曲線**未**勾選」。本輪用該專案的副本實測,`ProfileToneCurve` 明確有作用(A→B meanΔ 0.0706,遠高於任何雜訊水位)。

可能是設定之後被改過,或當初讀到的是另一個狀態。**這個勾選框決定「OFF 換矩陣」補的是 4% 還是絕大部分**,建議直接開面板確認。本筆記不替它下結論。

## 對照 Michael Garrett《SIGMA fp color workflow in film production》(2023-10-14)

來源:`~/Downloads/954594137-SIGMA-Fp-Color-Workflow-Feedback-sm.pdf`,12 頁,作者 Michael Garrett
(https://superposition.work),寫給 SIGMA 的業界意見書,基於 Ver.5.0 韌體。

### 一致的部分

- OFF 錄的就是相機原生色域/白點(他說 SIGMA 已公開確認);我們從 RAW 層測到 OFF 與其他模式
  的 Bayer 差 <0.11%,同一件事。
- Resolve 依 DNG metadata 建的輸入轉換,對 OFF 來說等於沒轉 → 畫面偏淡。我們把這件事算到底:
  OFF 的 CM = `diag(g)·inv(S_sRGB_D65)`,殘差 5e-7,所以 camera→XYZ→709 這兩步精確互相抵消。
- 曝光/中灰是對的(他量到 18% 灰正確)。兩支素材的 `BaselineExposure` 都是 3,一致。

### 可以補正的兩點

1. **不是「SIGMA 沒有做特徵化」,是「OFF 沒有把已經有的特徵化寫進去」。**
   他推測是加 OFF 功能時忘了更新矩陣標籤。實際情況更明確:韌體裡**同時存在**兩組 ROM 常數,
   writer `FUN_c02c4a50` 對 mode `0x24`(OFF)走專用分支選其中的 identity 那組;非 OFF 模式用的
   normal 組就是 SIGMA 自己的特徵化,而且每次用 Standard 錄都寫得出來。**要的資料不必等 SIGMA 量,
   它已經在同一顆 ROM 裡、也已經在你手上的 Standard 檔裡。**
2. **他建議的 Adobe DNG Converter / "Adobe Standard" 繞道,可以換成相機自己的矩陣。**
   他自己也指出 Adobe profile 在飽和高光會 out-of-gamut(霓虹、紅外套偏洋紅)。用 fp 的 normal
   矩陣不需要引入第三方的色彩取向;本輪實測它是中性精確守恆(列和 1.0000)的純線性矩陣。

### 他第 11 頁要的那張矩陣

> "What would also be helpful is if a matrix was published that encompassed a gamut and white point
> transform from fp OFF imported into Resolve as P3D60/Linear to something like ACES AP0/D60 or
> Rec2020/D65. It could be made available as a DCTL."

`correction_matrix.py` 就是從實拍檔的 ColorMatrix 直接推出來的那張(線性域,`正確 = M · 目前`,
列和恆為 1)。完整四個輸出空間 × 兩個光源端點在 `correction_matrices.json`,節錄:

| 輸出空間 | 光源 | M |
|---|---|---|
| Rec.709 (D65) | D65 | `1.3174 −0.5340 0.2166 / −0.0950 1.2237 −0.1287 / 0.0541 −0.4409 1.3868` |
| Rec.709 (D65) | A | `0.6996 −0.1961 0.4965 / −0.1309 1.1795 −0.0486 / −0.0077 −0.6209 1.6286` |
| P3-D60 | D65 | `1.3111 −0.4769 0.1658 / −0.1077 1.2356 −0.1279 / 0.0697 −0.4509 1.3812` |
| ACES AP0 (D60) | D65 | `1.3454 −0.4575 0.1120 / −0.1343 1.1820 −0.0478 / 0.2029 −0.6034 1.4004` |
| Rec.2020 (D65) | D65 | `1.3156 −0.4289 0.1133 / −0.1262 1.2335 −0.1074 / 0.1169 −0.4956 1.3788` |

Rec.709/D65 那一列與本輪從渲染結果擬合出來的 `1.2623 −0.4284 0.1652 / −0.1050 1.2299 −0.1249 /
0.0672 −0.5451 1.4786` 形狀一致(差異來自當次白平衡落在兩端點之間,以及擬合是在非線性輸出域做的)。

**⚠ 但「公布一張矩陣」這個要求本身有問題:A 與 D65 兩個端點差非常多**(Rec.709 的第一列從
`0.6996 −0.1961 0.4965` 變成 `1.3174 −0.5340 0.2166`)。正確的修法是雙光源 profile 依當次白平衡內插,
單一 DCTL 只在它被推導的那個色溫附近成立。這也是為什麼把 `ColorMatrix1/2` 直接換回檔案裡
(F / `C_firmware_normal.DNG` 的做法)比事後掛一張 DCTL 更正確 —— 內插交給解碼器做。

### 他文件裡本輪沒有驗證的部分

- 相機螢幕/QuickTime 是「P3D60 + sRGB gamma、超過 1.0 直接截掉」—— 這是他從錄 QuickTime 反推的,
  我們的韌體反編譯(`notes/COLOR_SCIENCE.md`)走的是 88 條 tone 曲線庫 + YCbCr 那條路,兩邊還沒對上。
- ACES 輸出轉換下的高光 tone mapping 差異、Filmbox 色域壓縮的效果:沒有重現。
- 他的 Macbeth 比對是在非受控光源下拍的,他自己也註明了。

> **2026-09-26 後續**:OFF 只換矩陣這件事已經做進韌體(2 個 byte),補丁點定位、全 ROM 副作用稽核與
> 藍色 LED 的飽和色實測見 [`off-matrix-firmware-patch-20260926/`](../off-matrix-firmware-patch-20260926/README.md)。
> 該輪也補上了本筆記缺的飽和色量級:LED 燈芯 ΔE76 mean 9.69 / max 19.9。

## 界線

- 297/298 是**兩次錄影**,不是同一段 RAW;D→F 的 0.0038 是這個底線,不是誤差上限。
- 每支只比了**一張**(第 49 幀),不是整段。
- ΔE76 是在 Rec.709 顯示域上換算的量級指標,不是絕對色度量測;沒有色卡、沒有已知光源。
- 沒有測 Adobe Camera Raw / Lightroom 等其他解碼器。Resolve 吃這些標籤,不代表別的解碼器也吃,反之亦然。
- 沒有驗證絕對色準。「換上 normal 矩陣比較對」的根據來自韌體來源鏈(見 `native-calibration-20260924/`),不是本輪的實測。
- Resolve Studio 21.0.4.5、macOS、fp Ver.5.02.0.V91。

## 檔案

本目錄:

- `build_variants.py` — 產生 A–G 七個 DNG(冪等,可重跑,輸出 sha256 一致)
- `resolve_render.py` — `new` / `copy "<專案名>"` 兩種跑法
- `analyze.py` — 回讀 16-bit TIFF、算 ΔE 與擬合矩陣 → `results.json`
- `matrix_on_swatches.py` — 色塊示範 → `swatch_demo.json`
- `correction_matrix.py` — 從實拍檔的 ColorMatrix 推導 OFF→正確渲染的修正矩陣 → `correction_matrices.json`
- `results.json`、`swatch_demo.json`、`correction_matrices.json`

素材與渲染輸出(體積大,不在 repo 內):

- `/Users/dido/Movies/fpSup/color area/looktag_ab/` — A–G 各一個子資料夾 + `manifest.json`(每個檔的 sha256、改動 tag、RAW strip 驗證)
- 同目錄 `renders_default/`、`renders_user/` — 兩組各 7 張 16-bit TIFF
- 來源:`/Users/dido/Movies/fpSup/color area/A001_297`、`A001_298`

Resolve 裡留下兩個測試用專案 `fp_looktag_AB`、`fp_looktag_AB_userSettings`,可直接刪除,不影響原專案。
