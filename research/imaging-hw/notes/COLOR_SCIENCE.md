# SIGMA fp — 色彩科學完整反編譯

fp Ver.5.02。從感光元件 RAW 到成像的完整色彩管線。位址 base 0xC0000000,decomp `out/decomp/full/blk_c0X.c`,ROM 讀自 `out/seg0_c0000000.bin`(offset=VA−0xC0000000)/ `seg1_c2ef6e00.bin`(base 0xC2EF6E00)。信心逐節標。
相關硬體管線在 Milbeaut/Socionext "SIGPRO" `0x3011xxxx` 暫存器區。

═══════════════════════════════════════════════════════════════
## 總覽:管線順序(兩個 agent 交叉確認)
═══════════════════════════════════════════════════════════════
```
黑階/線性化 → 白平衡 gain(raw Bayer 域) → demosaic → IGAMMA 反gamma
  → CCM 色彩矩陣 RGBLMAT(linear RGB,0x30115000)   ⚠ 位址有誤,見下方更正
  → RGB→YCbCr YCMAT(Rec601 權重 1224/2403/469)
  → 主 TONE 曲線(88 條庫,0x30115a00) ← tone 在 CCM 之後、飽和之前
  → Y_GAMMA 微調(預設關) → 局部/色度(YUVIIR/CUVAREA/CKNEE/CUVLPF)
  → 飽和 C_SAT_C(0x30117280,YCbCr) → 對比/CEQ
```
**「SIGMA look」的本質**:colorimetric CCM 基本固定(per-unit 校準),創意調性在**下游**(tone 曲線 + 飽和 + toning)做。沒有 per-hue HSV LUT、沒有 hue 旋轉。

**★ 取得策略(三類)**:
- **通用可抄(在 ROM)**:4 個 DNG 參考矩陣、88 條 tone 曲線、mono tint 表、飽和/對比公式、YCbCr 權重、AWB locus 表。
- **機身特定(要 dump)**:運轉期 CCM、16 個 mode 矩陣、AWB 預設 gain、WB 工廠校準 —— 用 shell `prom read`/`mem save`(見 `SHELL_COMMANDS.md`)。
- **創意資源(要 dump)**:Teal&Orange/FCBlue/DuoTone 的 profile LUT(runtime 載入,tag 0xc6fa/fb/fc)。

═══════════════════════════════════════════════════════════════
## ① 白平衡(AwbMgr)— 信心:高
═══════════════════════════════════════════════════════════════
**演算法 = 加權 gray-world(在 raw RGGB 空間)**。核心 `FUN_c04d47e0`:
```
每 block i:  w = mask[i]  (256-block 權重遮罩 @awbmgr+0x164)
  rSum+=w·R[i]; gSum+=w·G[i]; bSum+=w·B[i]; g2Sum+=w·G2[i]
R_gain = 256·gSum/rSum (Q8);  G=512;  B_gain = 512·gSum/bSum;  G2_gain = 256·gSum/g2Sum
```
無白點搜尋、無 per-block 對 locus 投票 —— 選擇只靠 mask(門檻在校準)。

**色溫比對空間 = 投影後的 raw 色度平面**(非 CIE uv/xy)。`ColorPoint::v1 @c02b3a80`:`x_r≈2e7/gain_R`、`x_b≈2e7/gain_B`、`x_g=1e5−x_r−x_b` → `(X,Y,Z)=M·(x_r,x_b,x_g)>>12`,只用 (X,Y)。

**CCT 估計 = 到 Planckian locus 的垂距**(`get_kelvin` `ColorPoint::v2 @c02b3f70`):tint = 垂直距離(cross-product/段長),kelvin = 沿段弧長內插。教科書做法。

**ROM 表(實際值)**:
- **CCT locus `{kelvin,X,Y}` @0xC096DD7C**,20 點 2000–15000K:2000→(30502,35907)、3000→(25051,34768)、5000→(21150,32301)、6500→(20049,31032)、10000→(19025,29337)…(X,Y 單調)。
- **投影矩陣 M @0xC096DD54**(int32 Q12,shift12):row0 `[2607,386,695]` row1 `[1475,456,1723]` row2 `[14,3254,1678]`。
- **kelvin→R/B 綠/洋紅微調 `{kelvin,R,B}` @0xC096C96C**(Q10,16 點 2500–10000K/500K):2500→(1013,1097)、5000→(1053,1144)、10000→(1070,1150)。基底 `{1062,995}`@0xC096C964,朝中性 `{1024,1024}`@0xC096C95C 混合。
- **ColorTemp 校準斷點 @0xC096BD54**:12700,10000,7000,5400,4400,3700,3200,2800,2500,2400K。
- unity `{1024,1024}`@0xC096BD04(Q10)。

**定點**:locus/gain 層 unity=**1024(Q10)**;operand-G 層=512;chroma 另有 1/256 路。

**模式**(tag `FUN_c05bb4a0`):Daylight=1、Incand=2、Fluor=3、Overcast=4、Flash=5、Custom1=6、Shade=8、Custom2=0xf、Custom3=0x19、**Auto=0x29**、**ColorTemp=0x46**。mode→slot 表 @0xC096BD0C。
**⚠️ 預設 gain 是 RAM/校準(DevData tag 0x120,10 slot×3 float),非 ROM** —— per-body。ROM 只有 enum→slot、10 個 ColorTemp kelvin、unity、locus。

**時間平滑 = 距離自適應 slew 限制器**(`FUN_c04d3bd8`,state @0xC3409D14):距離門檻 @0xC096C190 `{10000,125,85,15}`、收斂時間 @0xC096C1A0 `{2000,2000,5000,5000}`(≈67–167 幀 @30/幀)。**大場景變化收斂快、小變化重阻尼**。

**無臉/場景感知 AWB 加權**(確認的負面結果)。

**★ CCI 更正**:lens CCI_R/G/B(+0xa0/a4/a8)**AWB 完全不用** —— 唯一 reader 是 `dumpLensData @c033ab88`(除錯列印),純診斷。(先前 §3 曾寫「CCI 用於白平衡補償」= 錯,已更正。實際鏡頭色校走 `cor_data`/shading 欄位 +0xc8+。)

**工廠 WB 校準**:在 "SensAdj" flash 分區(0x80000),RAM 指標 `0xC3074950`,WB ref R/G/B @+0x04/08/0c(+0x00=已校旗標)。per-unit,fallback ROM `{300,512,700}`。→ 可 `prom read`/`mem save` dump。

═══════════════════════════════════════════════════════════════
## ② 色彩矩陣 CCM — 信心:高
═══════════════════════════════════════════════════════════════
**架構:沒有 ROM 色溫內插 CCM 表。** 三層:
- **運轉期/JPEG**:硬體 3×3 RGBLMAT(@0x30115000),吃 **per-unit 工廠校準**(RAM);ROM 只有 identity 預設。→ 要 dump。
- **DNG 輸出**:標準雙光源方案 —— 兩個固定 ROM 矩陣(A + D65),色溫內插交給外部 DNG reader。相機內色溫只驅動 WB。

**★ 4 個 DNG 參考矩陣(ROM 唯一真色彩科學常數,IEEE-754 double,row-major,scale=1.0)**:
| | ROM VA | 係數 |
|---|---|---|
| CM1 光源A(2856K) | `0xC096FD2C` | `[1.5278,−0.7837,−0.5324; −0.3330,1.1711,−0.0605; −0.0763,0.1667,0.5981]` |
| CM1 A variant(0x24) | `0xC096FD74` | `[1.5548,−0.7376,−0.2392; −1.1734,2.2710,0.0503; 0.0873,−0.3202,1.6590]` |
| CM2 D65(6500K) | `0xC096FC9C` | `[0.8610,−0.2133,−0.1820; −0.4962,1.1649,0.0632; −0.1160,0.1612,0.3618]` |
| CM2 D65 variant(0x24) | `0xC096FCE4` | `[1.5951,−0.7567,−0.2454; −0.9693,1.8760,0.0416; 0.0361,−0.1324,0.6860]` |
CalibrationIlluminant1=17(Std A)、2=21(D65)。SRATIONAL 分母 10000。
**DNG ColorMatrix = inv(as-shot WB 對角) · ROM_Const**;as-shot WB = `diag(rawR/323, rawG/511, rawB/672)`;AsShotNeutral=`[256/wbR,1,256/wbB]`。writer `FUN_c02c4a50`,3×3 乘 `FUN_c02c9860`。

**16 個 Color Mode 矩陣**:emit 成 MakerNote tag 0x124/0x129,per-unit 校準 × ROM 模板算出(builder `FUN_c02c5948`/`c02c57c0`/`c02c55a0`)。**但硬體 RGBLMAT 不隨 mode 換** —— 創意調性在下游。
**HW CCM packer** `FUN_c0107250`(27×16-bit → shadow reg 0x30210c78…),ROM 預設 `DAT_c2f0c014` = identity ramp。

> **⚠ 2026-09-27 更正(§② 的兩處位址)**
> `FUN_c0107250` / shadow `0x30210C78` / MMIO `0x30115000` **是 IGAMMA,不是 RGBLMAT**。
> 交叉驗證:該函式打包 **27 個值**成 14 個字且無遮罩 —— 27 是 gamma knot 數,3×3 只需要 9 個。
> **RGBLMAT 實際在 shadow `0x30210CB0..CE4` / MMIO `0x30115100..34`**,由 `FUN_c0107490`
> 與 `FUN_c0107608` 各寫一組 9 個 11-bit(遮罩 `0x7FF`)係數 —— 即稽核所稱的「兩組係數」。
> 依據:[matrix-gamma-audit.md](/Users/dido/Developer.localized/SIGMAfp_re/research/liveview/matrix-gamma-audit.md)
> 的 descriptor 稽核(`FUN_c019c810`),以及
> [isp-colour-blocks-20260927](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/isp-colour-blocks-20260927/README.md)
> 的參數形狀驗證。

═══════════════════════════════════════════════════════════════
## ③ Tone / Gamma — 信心:高
═══════════════════════════════════════════════════════════════
**主 tone = 88 條全曲線庫 @ROM `0xC0971F34`**:
- 88 條,每條 **2048 點(11-bit 入 → 13-bit 出,max 0x1FFF),uint16**,stride 0x1000,總 0x58000 bytes。index 表 @`0xC0971118`(`{ptr,id}` id 1–88)。
- 形狀 = **scene-linear → 顯示 tone**(強陰影提升 + 高光肩部 + ~93.7% 硬剪),**非 sRGB/2.2、非 log**。曲線1:index 128→2680、512→5614(⅛→0.50、¼→0.685、½→0.878 全刻度);斜率 陰影≈2.6、中≈0.5、高光≈0.14。
- 分 8 個 family × 11 階(對比進程 −5..+5)。哪個 mode 用哪 base ID 未逐一釘死。
- 曲線選擇 `FUN_c047af40`(寫 PQ 物件 vtable +0x214)。**串曲線進 ISP 的函式未定位**(base 在 PictureQuality 算)。

**Tone Control(`CM_DNGDEV_ToneControl`)= 4 模式**:0 Off / 1,2 Auto / 3 Manual。
- Manual:Highlight+Shadow 各映射 **−5..+5 強度**(表 @0xC0CEEA54 key remap、@0xC0CEEB6C amount→強度)。
- Auto:場景高光/陰影均值比門檻 陰影 `{209,411,682}`@0xC0CEEBF0 / 高光 `{350,650,1024}`@0xC0CEEBFC → 選 **3×3 grid** 一條曲線(`FUN_c04bad50`)。

**ISP 暫存器 gamma 預設多為 identity/停用**(Y_GAMMA 18點 `DAT_c2f13228` linear+關;GAM_BAS `DAT_c2f13124` 全零 identity;IGAMMA `DAT_c2f0c008` identity)—— 真 tone 靠 88 曲線庫。
**CinemaDNG 無 log 曲線,scene-referred 線性**(tone 只在顯示/JPEG 路徑套)。

═══════════════════════════════════════════════════════════════
## ④ Color Mode(SIGMA look)— 信心:高
═══════════════════════════════════════════════════════════════
**完整 enum(內部儲存碼,三方確認,`FUN_c02cc408`/name 表 @0xC0970934)**:
`0`Standard `3`Vivid `5`Neutral `6`Portrait `7`Landscape `8`Cinema `9`WarmGold `10`Teal&Orange `11`SunsetRed `12`ForestGreen `13`PowderBlue `14`FCBlue `15`FCYellow;`1/2/16–23`Monochrome 家族(2=Sepia);`24–33`DuoTone 10 變體;`36(0x24)`特殊擷取(自帶 CCM/LUT)。MonoFlag 判定 `FUN_c02c41f8`。

**改色機制(五件事,無 HSV LUT、無 hue 旋轉)**:
1. **profile-id 選 tone+color LUT**(主調性載體)—— `FUN_c02c4228` 表 `DAT_c096fc48`:Cinema→0x0c、Teal&Orange→0x0d、WarmGold→0x11、FCBlue→8…。**profile LUT 是 runtime 載入資源(tag 0xc6fa/fb/fc),Teal&Orange/FCBlue/DuoTone 的實際色調不在 ROM** → 要 dump。
2. **色度平面飽和 gain**(`FUN_c010e118`,YCbCr,unity 256):idx<8 → `idx·0x10+0x80`(0.5–0.94)、idx8 → 1.0、idx>8 → boost。寫 reg +0x1a4。
3. **對比 tone 曲線**(luma piecewise slope,`FUN_c010e118` reg +0x70..)。
4. **RGB→YCbCr 矩陣**(`FUN_c0108140`,luma Q12 `1224/2403/469`,chroma `0x3aa/0x100/0x100/0x3d7`)。
5. **Monochrome 加 RGB tint**(`FUN_c02c4480`,Q15 gain):default `[1,1,1]`、Sepia(2) `[1.0,0.883,0.740]`、16 `[1.0,0.840,0.818]`、17 `[0.885,1.0,0.877]`、18 `[0.876,1.0,0.959]`、19 `[0.752,0.861,1.0]`、20 `[0.945,0.881,1.0]`、21 `[1.0,0.910,0.975]`、22 `[1.0,0.927,0.808]`、23 `[0.839,0.900,1.0]`。toning 強度 scaler `FUN_c02c4f50`(步 `-5..+5` @0xC096FE00 朝中性插值)。
- DuoTone 子變體 `FUN_c02c4320`(24–33 → index 1..10)。

**使用者調整(Contrast/Sharpness/Saturation/Toning)**:menu 綁定 → 各自 clamp 到 mode min/max → 存進 PictureParam 物件,**base(slot idx 0)與 user-offset(slot idx 1)分開存**(Toning +0x1ec/+0x1f0、Contrast +0x1f8/+0x208、Sharpness +0x1fc/+0x20c、Saturation +0x200/+0x210)。step 表 level1–10→signed `DAT_c096fc67/73/7f = [0,-10,-8,-6,-4,-2,+2,+4,+6,+8,+10]`。**組合規則 = combine-then-clamp**(base+offset 再夾;確切算式行未定位,推定)。三個 controller:COLAJ/COLFIX(拍攝照片)、CHGMOD(live)、DNGDEV(相機內 raw develop)。

═══════════════════════════════════════════════════════════════
## 關鍵位址速查
═══════════════════════════════════════════════════════════════
| 主題 | 位址 |
|---|---|
| AWB gray-world | kernel FUN_c04d47e0;driver FUN_c04d4580;get_kelvin FUN_c02b3f70;locus finder FUN_c02b3b20;平滑 FUN_c04d3bd8 |
| AWB ROM 表 | locus 0x96DD7C;矩陣 M 0x96DD54;kelvin trim 0x96C96C;ColorTemp 0x96BD54;mode→slot 0x96BD0C;平滑 0x96C190/0x96C1A0 |
| AWB 校準 | SensAdj flash 0x80000,RAM ptr 0xC3074950;讀取 FUN_c02ad018 |
| DNG CCM | writer FUN_c02c4a50;矩陣 0xC096FD2C/FC9C/FD74/FCE4;乘 FUN_c02c9860;per-shot WB FUN_c02b22a0 |
| HW CCM | packer FUN_c0107250;預設 DAT_c2f0c014;per-mode builder FUN_c02c5948/c02c55a0 |
| Tone 曲線 | 庫 0xC0971F34;index 0xC0971118;選擇 FUN_c047af40;ToneControl FUN_c04baa48/c04bad50;參數 0xC0CEEA54/B6C/BF0/BFC |
| Color Mode | enum name 0xC0970934;profile-id FUN_c02c4228/DAT_c096fc48;mono tint FUN_c02c4480;飽和/對比 FUN_c010e118;YCbCr FUN_c0108140;DuoTone FUN_c02c4320 |

**未解**:運轉期 CCM 數值(per-unit,要 dump)、profile LUT 資源內容(runtime 載入,要 dump)、88 曲線 per-mode base-ID 對應、combine-then-clamp 確切算式、mode 0x24 語意、AWB mask 門檻(校準)。
