# OpenGate 2K / 3K / 4K 畫質路線

2026-09-15。這份只放 fp/OpenGate 的組合、位址、輸出幾何與測試順序。
可重用的 IMX410 mode 分類留在
`research/imx410/notes/SENSOR_MODE_METADATA.md`。

狀態標記:

- **proven**:已有相機實錄或原廠錄影路徑。
- **precedent**:組件在原廠或既有實驗中個別用過,新組合未實錄。
- **proposal**:合理候選,仍需相機驗證。

---

## 1. 決策摘要

| 目標 | 出貨/第一版 | 畫質研究支線 | 不採用 |
|---|---|---|---|
| OG2K | **M139 direct**(2026-09-23 確認為預設) | M98+RWZM1.5(只為近-Nyquist 週期紋理) | M131 crop、M140 3x6、**M3+RWZM3(已翻掉)** |
| OG3K | M98 direct | full-height24+RWZM2 | M117 作低格率常態基底 |
| OG4K | full-height24+RWZM1.5 | RWZM1500 的 DCI 寬版本 | 猜 sensor 1.5x、3968x2640 crop 冒充 OG |

目前開發主線選 **OG4K-4000 / 24.000p / RAW12**。理由不是它研究量最少,而是它最有機會
直接形成可用功能:full-height 前端已有 F1 實錄先例,RWZM1536 有原廠 profile 先例,而輸出
資料率只比 stock UHD29.97 高 2.85%。14-bit full OpenGate 的讀出上限只有 19.55p;
機身無損壓縮則先卡在影片回放不解析 tiled Compression=7,若再加動態抽幀還要另做時間軸。
壓縮與 14-bit 都保留為共用研究,但不阻塞 OG4K 主線。

4K **不是只能錄 6K 再由電腦後製**。最實際的架構是:

```
IMX410 full 6064x4042
    → 機內 RAW-domain RWZM
    → 約 4K 3:2 CinemaDNG
```

這仍是 full-read supersampling,只是縮圖發生在寫檔前。直接寫 6K RAW 再後製
需要的資料率超過 fp 的 USB 3.1 Gen1。

---

## 2. OG2K

### 2.1 第一版:M139 direct

```
M139 MONIT1_60_LOWP5
2016x1344 RAW12,full,3x3,Q12
rolling shutter 8.307 ms
DefaultCrop 2000x1334 @(8,5)
```

M139 是唯一 full 2016x1344 quiet 候選。M8/56/147–150 同幾何但屬 fast
fingerprint;只有捲簾/高速優先時才選。M139 與 M8 的噪聲差應做配對量測,
不能把 M98/M117 的 DN 數字直接套上。

電影格率只改 timing;÷3 家族 timing `+0x0A` 必須保留 `6`:

| fps | HMAX | tail | VMAX |
|---:|---:|---:|---:|
| 23.976 | 445 | 585 | 6748 |
| 24.000 | 445 | 1145 | 6740 |
| 25.000 | 450 | 450 | 6400 |
| 29.970 | 445 | 735 | 5398 |
| 48.000 | 445 | 795 | 3370 |
| 50.000 | 450 | 450 | 3200 |
| 59.940 | 445 | 1035 | 2698 |

2016x1344 packed RAW12 資料率:

| fps | MB/s |
|---:|---:|
| 23.976 | 97.4 |
| 24 | 97.5 |
| 25 | 101.6 |
| 29.97 | 121.8 |
| 48 | 195.1 |
| 50 | 203.2 |
| 59.94 | 243.6 |

### 2.2 畫質研究

| 路線 | 上游 | RWZM | RS | 證據 |
|---|---|---:|---:|---|
| HQ | M98 3032x2012 Q12 | 1536 | 12.44 ms | p83 預覽已有 2024x1341 / active2000x1334 |
| MaxIQ | M3 6064x4042 Q12 | 3072 | 24.98 ms | p41/42/81/82 預覽已有2016x1344 / active2000x1334 |

兩條都可能改善細節與 aliasing,但不能先承諾降噪。HQ 的 recording 1.5x、
MaxIQ 的 recording 3x 都還沒有這個精確組合的實錄。

---

## 3. OG3K

### 3.1 出貨基底:M98 direct

```
M98 ACQ_12BIT_MIX
3032x2012 RAW12,full,2x2,Q12
現行 raster 3024x2010
DefaultCrop 3008x2000 @(8,5)
rolling shutter 12.435 ms
```

M98 對 M117 的可逆實測已量到 0.551 對 0.965 DN 讀出雜訊。23.976–59.94p
維持 M98 readout,只借 quiet ÷2 timing;100p 才使用 M117。M98 是 ACQ mode,
錄影時必須保留 raw-movie gain-state 修正,否則 HCG/高光比較會失真。

### 3.2 畫質研究:full-height24 + RWZM2

```
M151-full24
6064x4042 RAW12,Q12,exact 24p
RWZM 2048
→ 3032x2020 / active3000x2000
rolling shutter 24.982 ms
```

這條不是純離線猜測。既有 FP3K F1 實錄了 **207 張連續 DNG / 8.625 s**,
固定機位對完整 6000x4000 still 的配準提供強的 full-FOV 證據。它仍不證明
每個 photosite 都參與 RWZM,也還沒有成對 MTF、aliasing、讀噪結論。

> **2026-09-22 補 —— 見 `REDUCTION_KERNEL_MEASURED.md`。** 成對的 MTF、aliasing
> 與讀噪結論有了,RWZM 的核也解出來了(`OG3K → FHD` 直接擬合,r²=0.99923):
> **半寬約 1.2 的三角核,等向,而且不隨比例縮放。** 直接後果:
> 固定寬度的核拿去做 ÷3 幾乎等於沒有前濾波,但拿去做「÷2 之後的 ÷1.5」剛剛好。
> 所以本節第 19 行列的 **M98+RWZM1.5** 在模擬裡明顯優於 M139 direct
> (舊數字 疊紋 6.5% vs 31.4%、N_eff 10.24 vs 5.33)。
> ⚠ 但那是從 25/16 外推到 1.5 的,**尚未跨比例驗證**,先別改基底決策。
>
> **2026-09-23 再補 —— 見 `REDUCTION_KERNEL_MEASURED.md` §7.5。** 上面的數字是用
> **單一混合原型核**算的,錯了。改用 16 個逐相位核重算:**疊紋 10.4% vs 24.0%、
> N_eff 10.34 vs 5.34**。**結論方向不變,M98+RWZM1.5 仍然勝過 M139 direct**,
> 而且跨比例風險比原本以為的小:3/2 只叫得動 16 條核裡的第 0 和第 8 條,兩條都量過。
> 同一節也翻掉了 §2.2 的 **MaxIQ(M3 6064 + RWZM3072)**:RWZM 不做前濾波,
> 全讀出再 ÷3 的疊紋是 **35.3%**,全表最差,而且 N_eff 只有 2.64(比 M139 direct 更吵)。
> §4 的 OG4K 主線則被支持:**full + RWZM 3/2 的疊紋 4.6/3.1/0.5,優於現行 UHD 的 6.8/3.1/1.0**,
> 且 3/2 只用 2 個相位,不會出現 FHD 那種週期 16 的橫紋。

證據:

- `research/other/external/FP3K-technical-handoff-2026-09-10/analysis/fullheight-f1.md`
- `research/other/external/FP3K-technical-handoff-2026-09-10/analysis/fullheight-static-findings.md`
- `research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/fullheight-f1-plan.json`

---

## 4. OG4K

### 4.1 不建立未知的 sensor 4032x2688 mode

IMX410/SIGMA 現有表只出現 sensor geometry scale 1x、2x、3x 與 Y=6,
沒有 1.5x。M129/M130 的 3968x2640 是中央 crop。因而:

- 改 metadata 寬高不會創造 fractional sensor readout。
- RAW bit enum、full/crop enum 也不是硬體開關。
- 現在沒有依據安全外插一組「sensor 直接 4032x2688」私有暫存器。

可稱為自製 4K mode 的部分,應是「原廠 full-height 前端 + 新的下游 4K profile」,
不是一個虛構的 IMX410 1.5x mode。

### 4.2 第一候選:OG4K-4000

| 項目 | 值 |
|---|---|
| sensor 前端 | M151-full24 |
| 輸入 | 6064x4042 RAW12,exact 24p |
| RWZM H/V | 1536 / 1536 = 1.5x |
| CinemaDNG raster | **4016x2676** |
| DefaultCrop | **4000x2666 @(8,5)** |
| packed RAW12 | **386.9 MB/s @24p** |
| 狀態 | **offline-validated proposal**;18 個 stock word、完整前端 donor、精確24p與尺寸/頻寬已由 `build/og4k_plan.py` 驗證,尚未上機 |

這沿用 fp 影片 `raw = active +16/+10` 的邊界慣例,並接近
6000x4000 active 的精確 1.5x 縮圖。2666 是偶數 Bayer 高度;
實際縮放捨入、Bayer phase、邊緣 coverage 必須由第一支 DNG/readback 定案。

離線 verifier 固定在 V5.02 SHA-256,從 firmware tables 自動導出 M151→M3 的 10 個
full-height 前端差異,再逐字比對 8 個新 output/RWZM words。7 項 contract tests 已通過;
`camera_ready()` 刻意維持 false。尚未解完的硬閘門是 private profile transaction、
4016×2676 的 producer/consumer allocation/stride、DNG header/packing、回放畫布與暖重開 rollback。

後續離線實作已在 `fpSup/opengate/og4k/` 加入可執行ARM核心：10字前端transaction、
私有p429 RAW畫布、p71回放畫布與boot recovery。原廠receiver、byte-count及記憶體尺寸
函式也已在模擬器驗證。詳見 `OG4K_IMPLEMENTATION.md`／`OG4K_SIZING.md`。
這完成部分底層實作；UI、真實狀態adapter、hook生命週期與實際pool餘量仍未完成。
特別是16,120,224為packed像素量，韌體末列補8bytes後的StripByteCounts是16,120,232。

### 4.3 第二候選:OG4K-DCI

| 項目 | 值 |
|---|---|
| RWZM H/V | 1500 / 1500 |
| CinemaDNG raster | 4112x2740 |
| DefaultCrop | 4096x2730 @(8,5) |
| packed RAW12 | 約405.6 MB/s @24p |
| 優點 | ratio1500 已由 stock p365 DCI4K24 RAW 路徑使用 |
| 缺點 | 比第一案多約4.8%寫入量,且是非常小幅的邊緣裁切 |

p365 是 WithRaw/format11,不是 table3 CinemaDNG/format7。它只能作 ratio1500
與幾何的原廠證據,**不能整個借來**。實作仍以 p429 的 private runtime copy 為基底。

### 4.4 24p full-height 前端:重用 F1,不要少抄 receiver

M151 與 M3 的 161 個 table-fed sensor register 完全相同。保留 M151 的
精確24p timing:

```
HMAX=445,tail=1145,VMAX=6740
frame cycles=3,000,000
```

把 M151 的 metadata、receiver 與 input window 對齊 stock M3 full-height。
只改 metadata/timing **不夠**,56-byte receiver record 的四個差異也必須同步:

| 區塊 | 位址 | stock M151 | full-height |
|---|---|---:|---:|
| metadata height 1 | `0xC0B5B6C8` | 3412 | 4042 |
| metadata height 2 | `0xC0B5B6D8` | 3412 | 4042 |
| metadata height 3 | `0xC0B5B6E8` | 3412 | 4042 |
| metadata aspect | `0xC0B5B714` | 1 | 2 |
| receiver | `0xC0B5D43C` | 8 | 0 |
| receiver | `0xC0B5D440` | `0x016001FB` | `0x002601FB` |
| receiver | `0xC0B5D444` | 3768 | 4084 |
| receiver | `0xC0B5D450` | `0x0004C003` | `0x00040003` |
| timing/input window | `0xC0B59D0C` | `0x016217B8` | `0x002817B8` |
| timing/input window | `0xC0B59D10` | 3766 | 4082 |

完整 F1 有 18 個 guarded words:上表 10 個 full-height 前端 words,另有
p429 的六個輸出 geometry words與兩個 RWZM words。OG4K 重用前 10 個,
後 8 個必須改為新的 4K 值,不可直接照抄 3K F1。

### 4.5 頻寬

| fps | 4016x2676 RAW12 | 6064x4042 RAW12 |
|---:|---:|---:|
| 23.976 | 386.5 MB/s | 881.5 MB/s |
| 24 | 386.9 MB/s | 882.4 MB/s |
| 25 | 403.0 MB/s | 919.2 MB/s |
| 29.97 | 483.1 MB/s | 1101.9 MB/s |

Stock UHD 3856x2170 RAW12/29.97p 約 376.2 MB/s。OG4K-4000 24p 只高約
2.8%,是合理的第一輪;29.97p 高約28.4%,不要先測。

完整 6K RAW 24p 的 882.4 MB/s 已高於
[SIGMA 官方規格](https://www.sigma-global.com/en/cameras/fp/)所列 USB 3.1 Gen1
的 625 MB/s gross
上限,還沒算協定與檔案系統開銷。因此「先錄完整 6K,回電腦軟體超採樣」
不適用標準影片格率;只適合 still、低格率,或未來先完成有效的無損壓縮錄影。

---

## 5. 實作隔離

- 以 **p429 private runtime copy** 作 CinemaDNG profile;不要永久改共享 ROM/RAM row。
- 所有 word 都做 expected-value guard、套用後 readback、失敗 rollback。
- M151 是 stock UHD24 共用資源。只有 OG4K flag 成立時才選 full-height copy;
  其他格式必須走原廠路徑。
- 暖重開不能假設 RAM 已清。退出/重載時要明確恢復 metadata、receiver、
  timing、profile copy 與 hooks;否則共享狀態可能殘留。
- preview 第一版仍可維持 16:9。錄影 3:2、LCD 取景、回放與格式名稱是四個
  不同問題,不要為了第一支影像同時改完。

---

## 6. 最小實驗矩陣

固定鏡位、燈光、快門、光圈與 ISO:

1. 離線 verifier 先確認 M151-full24 的 input-window 與 68-byte receiver arguments
   仍逐 byte 等同 native M3。
2. 冷開後先做選擇狀態、mode、timing、RWZM、producer geometry readback;
   idle live view 與 ±EV 即可先看出曝光/模式切換異常。
3. 第一支只測 **24p、RAW12、crop off、外接 SSD、錄 1 秒**。不要先用 SD,
   不要先測29.97p。
4. 驗 DNG raster、DefaultCrop、stride、StripByteCounts、每列邊界與 frame count。
5. 再錄同場景 M139 direct / M98 direct / full-read RWZM,每支 1 秒;
   ISO100、800、3200 分開,避免 HCG/LCG 切換污染結論。
6. 平場/暗場量 8–12 組相鄰幀的 read-noise R 與 shot slope a;
   zone plate、布料、斜邊量 MTF、aliasing 與 RWZM phase pattern。
7. OG4K-4000 穩定後才比較 RWZM1536 與1500;最後才拉長時間或測25/29.97p。

遇到 self-stop、花屏、DNG stride 不合或 USB 消失就停止重試、拔電池冷開;
不要在未確認 producer/consumer geometry 前只放大 canvas。

---

## 7. 14-bit OpenGate 29.97p

**結論:已知模式與 full-read/downstream 路線不可行,現階段沒有可交付版本。**

```
RAW14 full active read
= 911 cycles/line × 4042 lines / 72 MHz
= 51.14 ms

zero-blanking ceiling = 19.55 fps
stock M0              = 19.127 fps
```

29.97p 每格只有 33.37 ms;RWZM/CRCT 都在讀出後,不能縮短這 51.14 ms。
M6 sensor/receiver mode 可達 4176x2174 RAW14 @29.97p,但它是 16:9 crop;
這不等於14-bit CinemaDNG writer 已驗證。現有 2x/3x sensor
reduction 全是 RAW12;沒有完整的 RAW14 reduced donor。

唯一還能研究的是未證實的 sensor-side RAW14 2x reduction。以M0/M141的full-FOV
RAW14前端為基底,若能採用M6的HMAX=911 / VMAX=2636 / tail=1915時序,並把
M98的2x register、geometry與receiver設定安全移植,3032x2012的active read約
25.46 ms,29.97p仍有約7.91 ms blank,
理論 packed RAW14 payload 約319.95 MB/s。數學成立不等於 sensor 支援;
M6↔M98有70/161個table-fed register不同,receiver也沒有獨立的RAW14 transport
block。Sony與SIGMA的所有既有reduced mode都是RAW12,所以只能說沒有已知/已發布
支援;這條只列guarded discovery experiment,不可出貨。

可實際延續的 14-bit OG 研究案是 M141 full RAW14 約18p後接 RWZM,並驗證
generic movie_raw gain state 4、packing、DNG 與回放。它不能靠下游縮放延伸成
29.97p;29.97p只剩上述未證實的 sensor-side 2x 實驗。
詳見 `OG14_FEASIBILITY.md`。

---

## 2026-09-23 最終校正 —— 見 `REDUCTION_KERNEL_MEASURED.md` §7.6–7.9

三件事改變了本檔的決策:

1. **RWZM 從不做前濾波。** 每個相位都只是 2 抽頭級別的內插核,寬度不隨比例改變。
   → §2.2 的 **MaxIQ(M3 6064 + RWZM3072)翻掉**:全讀出再 ÷3 的織紋疊紋 35.3%,
   量過最差,而且 N_eff 只有 2.64(比 M139 direct 更吵)。
2. **一般素材上,沒有重取樣器的路線贏所有有重取樣器的。**
   M139 direct 2.7%,M98+RWZM1.5 是 7.3%(量過最差)。
   → **OG2K 預設回到 M139 direct**;M98+RWZM1.5 只在主體有近-Nyquist 週期紋理時才選。
3. **「低光用 FHD / 用 N_eff 高的路線」翻掉。** 那半級是模糊不是光:
   銳利度對齊後持平(×1.01)。N_eff 不能單獨當降噪理由。

§4 的 **OG4K 主線被支持**:full + RWZM **3/2** 的織紋疊紋 4.9%、優於現行 UHD 的 7.1%,
而且 3/2 只叫得動 16 格相位裡的第 0、8 格,不會出現 FHD 那種週期 16 的橫向痕跡
(FHD 在那一項是全頁唯一的 F)。**比例不要用 25/16,挑分母 ≤5 的。**

---

## 2026-09-26 補:3K 有沒有更好的感測器設定(三家韌體對照,`REDUCTION_KERNEL_MEASURED.md` §7.63)

**沒有更好的 ÷2 設定。** fp、A7 III、Z CAM 的 ÷2 家族只有一組(`0734`=5、深度 2),依 §7.63 模型,
偶數倍率垂直合併必然差 1 物理列 = 1/4 平面列(即 OG3K 的成對列錯位),換 `0734` 只能換方向,不能歸零。

| 路線 | 前端 | 捲簾 | 幾何 | 狀態 |
|---|---|---:|---|---|
| **M98 direct**(現行) | ÷2 合併 3032×2012,≤77p | 12.4 ms | 1/4 平面列成對列錯位,需後製 | proven |
| **full + RWZM2** | 不合併 6064×4042(fp mode_id 3,29.97p;mode 97 可到 39.16p) | 25.0 ms | 不合併讀出本身均勻;RWZM 是否保持均勻 CFA 未量 [?] | proposal |

- **Z CAM 的 2.8K / 1080p≤60 正是「不合併全寬讀出 + ISP 縮小」**,全片幅 6064×4040 可到 39p,從不用 ÷2。
  這是 full+RWZM2 路線的原廠旁證(Z CAM 在 YUV 端縮,fp 要在 RAW 端縮,不完全等同)。
- 若維持 M98:後製改用 §7.62 的**鏡像 Lanczos-6 兩邊各半**(±0.125),取代 Catmull-Rom;
  現行 `rowfix.py` 的 split 已是兩邊各半,雜訊平衡應無問題,但高頻保真度可改善 [?,未量]。
- 下一步:(1) 量 RWZM2 輸出的 CFA 幾何(奇偶差、分頻帶);(2) M98 成對列修正換 Lanczos-6 的分頻帶比較。

---

## 2026-10-05 使用者實拍目視:2K 清晰度排名

使用者在相機上實際比較後回報(目視,未附量測數字):

> **RWZM 0.33×0.33(全讀出再 ÷3)> bin3x3 銳利設定 > M139**,最清晰的是 RWZM 0.33×0.33。

和 2026-09-23 的量測並不矛盾,而是同一件事的兩面:RWZM 不做前濾波(`REDUCTION_KERNEL_MEASURED.md` §7.6),
所以全讀出 ÷3 保留了最多高頻 —— 目視「最清晰」;代價是同一份量測裡的
**織紋疊紋 35.3%(全表最差)與 N_eff 2.64(比 M139 更吵)**。M139 direct 疊紋 2.7%,是三者裡最乾淨、最軟的。

決策含意(待使用者定):若 OG2K 以清晰度為優先,RWZM 0.33 是候選;
上機前應在有細密週期紋理(布料、磚牆、螢幕)的場景再看一次疊紋,並在暗部比較噪聲,
否則「清晰」可能部分來自混疊的假細節。本檔 §1 的 OG2K 預設(M139 direct)尚未改。
