# SIGMA fp — AF/AE 內部演算法完整反編譯(六題彙整 + ⑦驅動細節十題 + ⑧CAF 觸發模型 + ⑨驅動/框/PTP 補充 + ⑩YLevel網格/低對比/waypoint)

> 2026-09-27 幾何用途補充：本文「框 size 變＝深度變」屬設計解讀；程式只證明框變化可觸發重驅，未證明變化一定來自主體深度。AAT 自適應窗／模型更新也會改尺度。最新主線先合焦建立錨點，再驗 face／AAT 幾何方向，見 [融合規劃](FP_GEOMETRY_DFD_FUSION_2026-09-27.md)。

給復刻 AF/AE 用。位址 base 0xC0000000,檔在 `out/decomp/full/blk_c0X.c`。信心度逐節標註。
六題:①DefocusPerPulse ②多頻帶 HPF 係數 ③能力旗標+CCI ④EV/APEX 計算 ⑤AF-C 運動預測 ⑥六種驅動策略。

═══════════════════════════════════════════════════════════════
## ① DefocusPerPulse(每脈衝離焦量)— 信心:高
═══════════════════════════════════════════════════════════════

**★ 抽取位置(實機 dump 驗證,SOP win)**:解析後的展開表就在**標準四段 dump** 裡 —— `lens_data +0x10c58`(28mm VA `0xC34755D8` = `HEAP34.bin` 偏移 `0x755D8`)。工具 `tools/extract_defocus_table.py`。
展開表佈局(全 little-endian u32):
```
+0x00  n_focal (定焦=1, ≤20)      +0x04  n_step (≤22)
+0x08  focal_axis[n_focal] u32 (焦距, 0.1mm; 28mm→280, 40mm→400)  [固定保留 20 格]
+0x58  grid 開始 (= lens_data+0x10cb0);  cell={u32 step_pos, u32 defocus_raw}, stride 8, 每列 22 格(0xB0)
```
**縮放**:`defocus_per_pulse = defocus_raw / 65536.0`(**16.16 定點**,消費端 55470 行常數 `DAT_c0354bfc = 2⁻¹⁶`;先前誤標 DAT_c03376e8=0)。

**★ 語意/量綱(RE 確認)**:
- **每位置的「率」,不是累積值**。解析器 `FUN_c0338510` 純反序列化(不累加);getter(`c0353e..`,54919)對 `value(step_pos)` 做 piecewise-linear **內插後直接除**(`pulses = defocus / DPP`),從不差分/累加。雙向(還有 `position(value)` 反查)。
- 值 = **每脈衝像面「縱向」位移(longitudinal defocus per pulse)**。**非**波前誤差、**非**景深單位、**未**預乘 Fno。Fno 由消費端 `FUN_c034fe50` 在分子外加:`(CoC[FUN_c032c960] × effFno[FUN_c034ff20] × 2) / (DPP×256×1000×1000) × 20`,即先把橫向 CoC 換成縱向離焦(ΔL=2·N·c)再除 DPP。
- 率隨對焦位置變大:28mm ∞≈0.53 → 近攝≈6.43 µm/pulse(12×,縱向放大率效應)= 使用者觀察到的非線性。`raw≈37.5×step_pos` 的近線性 = 率隨位置近線性成長,**不是**累積跡象。
- ⚠️ 絕對 µm 校準未完全鎖死(256×1000²×20 常數 + CoC 因子單位);相對曲線形狀可直接用,絕對值建議實測定標。

**wire 來源(為何 +0x2268 抓不到)**:`*(lens_data+0x2268)` = `0x356BB`、`+0x226c` = `136` **不是相機指標**,是**鏡頭內部 ROM 位址/大小**;韌體 `FUN_c0338510` 呼叫 `CmdRead`(`FUN_c0355be0`)走 L-mount 匯流排把 136 bytes(big-endian wire,`{u16 step, u32 raw}`,解碼器 `FUN_c06ae6e8`/`FUN_c06ae7b8`)拉進 stack,再展開到 `+0x10c58`。→ wire base 永遠不在相機記憶體,**只能用展開後的表**。136 = 頭2B+focal 2B+22×6B ✓。
解析器 `FUN_c0338510`(caller `FUN_c03341c8`,隨後 `dumpLensData`)。
- 實測 28mm:1×22,dpp 0→6.43 µm/pulse(近攝端每脈衝離焦量最大)。40mm:1×12,dpp 0→7.74。**近攝非線性 = 你觀察到的現象,數字在 `defocus_table_*.json`。**
(相關:場曲/頻率表用 1/512;有效開放 Fno 用 1/256=AV 單位。)

**AF 怎麼用**(`FUN_c034fe50`,實為「景深容差 → 脈衝」核心。注意:正常路徑 param_1 被 DPP 覆寫,它回傳的是 **2·N·c/DPP = 景深容差脈衝數**,不是任意離焦→脈衝):
```
pixel_factor = *( *(0xc343b588) + 0x50 )           // = 容許 CoC / 像素間距 (nm), 感光模式相依
effFno       = 256 · N                             // N=光圈值; ctx+0x37 = Av×8(1/8-EV步); FUN_c034ff20
DPP          = FUN_c034ff90(ctx, mode)             // DefocusPerPulse (µm/pulse), 縱向像面
pulses = (pixel_factor × effFno × 2) / (DPP × 256 × 1000 × 1000) × 20
       ≈ 2·N·c / DPP  (量綱收斂後), 殘留常數 ×1/50
```
**★ 實際值(ROM 確認)**:
- `pixel_factor` = ROM `0xc0b5f908`:**模式0(主靜態)=5940 nm = 5.94µm**(= fp 全幅像素間距,1-pixel 模糊判準)、模式1=3760 nm。感光模式相依,`FUN_c0322e48(mode)` 選。
- `effFno` = **256·N**:f/1.4→360、f/2.8→721、f/5.6→1446、f/8→2048(APEX 路徑;per-zone 表 +0x25b8 對 28mm 全 0、旗標=0 不走)。`ctx+0x37`=有效光圈 Av×8。
- 常數:256、1000、1000、20 皆 ROM 確認。展開 = `pulses = 40·N·c[nm] / (DPP[µm/pulse]·1e6)`。
- **⚠️ 殘留 ×1/50 校準**:代 N=1.414、c=5940nm、DPP=6.43 → 韌體輸出 0.052,教科書景深=2.61 脈衝,比值**恰 50**。即 `實際脈衝 = 50 × 韌體輸出`,**或**運轉期 DPP 其實 ≈0.13µm/pulse(非 6.43)。→ **建議實測定標 K**:驅已知脈衝數、量像面離焦,即可鎖定 K(等同確認 runtime DPP 是 0.13 還是 6.43)。這是「一步到位」還缺的唯一一個常數。

`FUN_c034c958`:逐 31 個像高點,`slope_metric += (Δeval·100)/(pulses/2)` → 把對比斜率正規化成「每脈衝對比變化」。
第二條路(即時 float):8×8「thin」表(lens 物件 `+0x100`)插值(`FUN_c034b088` 線性),依 zone(`ctx+0x22`)/距離(`ctx+0x20`)索引:max `+0xb78`、min `+0xc38`、ave `+0xcf8`、now(2D)`+0xdb8`。getter `FUN_c034ff90`。

═══════════════════════════════════════════════════════════════
## ② 多頻帶 HPF = 串接 IIR biquad 帶通(不是盒狀模糊!)— 信心:很高
═══════════════════════════════════════════════════════════════

主表 `DAT_c2f1e918`(seg1 offset 0x27B18):40 個 key,每筆 0x1C bytes = `{u32 key, u32 shift, 10×int16 coeff}`。係數 **Q8(256=1.0)**。
每一階段選**一對 key**:HIGH 頻帶 + LOW 頻帶並行 → `saf_jdat_h`/`saf_jdat_l`。

**★ key → 真實截止頻率**(legend `DAT_c0918f20`,ROM 字串 `f_60KHZ`…`f_35MHZ`,對照 master 表極點單調驗證,信心很高):
| key | 39 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 19 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 頻率 | 60k | 100k | 200k | 300k | 400k | 500k | 600k | 700k | 800k | 900k | 1M | 1.2M | 1.5M | 2M | 3.5M |
> 這是 fp 感光元件讀出時脈域的頻率;移植到你的系統要換算成 cycles/pixel(用你的像素率)。相對帶位與 biquad 形狀才是可直接照抄的。

**★ 校正**:`DAT_c0918f20` **不是** per-mode 配對表(先前誤判),它是上面這張 **key→頻率 legend**(15 筆),也兼做 debug/工廠介面的預設填充(`FUN_c022db58` 拷貝前 0x3C bytes 進 AfParam `+0x50`、count `+0x114`)。
**真正的運轉期選擇是演算法**,不是靜態 ROM 表 —— C++ 虛擬方法 **`FUN_c02a4580`**(AfMgrModel_w71c1.cpp,AF-model 單例 `0xc34046a4`,vtable slot +0xC)。輸入 `(mode 0–5, flag, LV bits4/5)` → `out[0]=HIGH key、out[1]=LOW key`,再 `FUN_c023b748(ctx,0/1,key)` 套用。

**運轉期配對表**(`out[0]`=HIGH、`out[1]`=LOW,已由暫存器路徑+物理雙重確認):
```
flag=0(靜態/連續AF 基底,常見):          flag≠0(驅動/步進;A=一般讀出 bits4,5=0 / B=裁切高速讀出):
 mode0(預設) HIGH k10(1M) LOW k2(200k)     mode0  A:k10/k4 (1M/400k)   B:k8/k3
 mode1        k6(600k)     k2(200k)          mode1  A:k6/k3  (600k/300k) B:k4/k2
 mode2        k13(2M)      k8(800k)          mode2  A:k13/k10(2M/1M)     B:k13/k10
 mode3        k13(2M)      k8(800k)          mode3  A:k13/k10(2M/1M)     B:k13/k10
 mode4        k8(800k)     k2(200k)          mode4  A:k8/k3  (800k/300k) B:k6/k3
 mode5        k4(400k)     k2(200k)          mode5  A:k4/k2  (400k/200k) B:k4/k2
```
- **最常見 `(mode0,flag0)` = HIGH key10(1MHz)/ LOW key2(200kHz)** = AF 預設帶。
- 運轉期**只用 keys {2,3,4,6,8,10,13}**(200k–2M);key14–34/40 那批高頻二階/雙biquad 出貨 AF **從不選用**(只在工廠掃描工具出現)。
- 成對消費(`idx+=2`)= 「必須偶數」的原因(H/L 配對)。
- **★ mode 0–5 = AF 掃描相位/步進粒度,不是解析度/fps**(由 `AfMgrModelSingleOem_Sig__v13 @c02a8a10` 產生,`FUN_c02a4580` 的除錯名 `非加算判定`):
  - **mode4 = 對焦搜尋中**(`FUN_c0254b28≠0`,粗掃全程)、**mode2/3 = 高頻鎖定階段**(step-state `_DAT_c3291518`∈{2}/{3,5,7})、**mode1 = 精** / **mode5 = 精(另區)**、**mode0 = 穩態/基底**。
  - step 粒度 `_DAT_c3291518` 命名(工廠命令 `single_af_offset_option`):highest=8/high=6/middlehigh=4/middle=0/low=1。
  - **LV bits4/5 = 感光元件 binning/降解析讀出** → selector 降到更低 AF 頻帶(mode0: 1M/400k → 800k/300k)。位元抽取確認;crop-vs-高速 的物理標籤 中信心。
  - 完整 (mode × flag × LV) → (HIGH,LOW) 表已列上方。

**★ 訊號鏈其餘係數(ROM 確認,dispatcher `FUN_c022da28`)**:六陣列**全 int32 LE**,`set default`/`set selection` 可調。
- **sens[20]@+0x00**(count 7):`{100,200,400,800,1600,3200,6400}` = 數位增益梯 ×100(1×…64×,`(1<<n)·100`)。對應 AF 增益暫存 `0x30050464`(12-bit)。
- **hpf[20]@+0x50**(count 15):`{39,1,2,3,4,5,6,7,8,9,10,11,12,13,19}` = 預設「掃全 15 帶」的 band key(即 legend keys)。
- **gup[16]@+0xa0 / lpf[5]@+0xe0 / sft[5]@+0xf4 / mdn[2]@+0x108**:預設為 index ramp `{0..15}/{0..3}/{0..4}/{0,1}`(除錯名 `af_register_*_data`)。**⚠️ 這四個是「硬體預設選擇索引」不是原始係數** —— 實際 lpf FIR/biquad tap、gup 增益值在 **AF 硬體暫存器 preset 區**,不在 AfParam,未 dump(未解)。sft=每級輸出右移位元數;mdn=中值級 on/off+視窗對(`+0x108==1||==3` 選中值行為)。

**差分方程**(每 section):`y[n] = (Σb·x[n-k] − Σa·y[n-k]) / 256`,再 `>> shift`。整流累加於 AF 區 = **AF 對比評價值**(`saf_jdat_h/l`,CDAF 爬山對象)。⚠️ 命名:這**不是** "YLevel" —— "YLevel" 專指 AE 測光亮度均值(§4),被 AF 借用做低對比/低光 gating(`GetCafLowconByYLevelFlg`),兩者不同物。
兩 section (b0,b1,b2 / a1,a2) × 2 = 10 係數。硬體暫存器 0x30050220–238(HIGH)/260–278(LOW),13-bit 打包。

**兩濾波族**:
- key 1–13,35–39:分子 (-256,256,0)=(-1,+1,0) 一階差分 × IIR 共振器;極點隨 key 移(key1 r≈0.98@3.6° 低頻 → key13 r≈0.36@52°)= **粗定位低頻帶**。key38/39 高增益版(shift 2/3)。
- key 14–34:分子 (128,-257,128)≈(1,-2,1)·128 二階差分/Laplacian 帶通,中心頻率隨 key 升 = **精定位高頻帶**。
- key 40:雙 biquad 全開,最銳。

**全 40 組係數(key sh | SecA b0,b1,b2,a1,a2 | SecB b0,b1,b2,a1,a2):**
```
 1 0 -256 256 0 -502 247 | -256 256 0 0 0      21 0  103 -207 103 -87 62 | 256 0 0 0 0
 2 0 -256 256 0 -496 242 | -256 256 0 0 0      22 0   99 -199  99 -73 62 | 256 0 0 0 0
 3 0 -256 256 0 -488 236 | -256 256 0 0 0      23 0   95 -191  95 -59 62 | 256 0 0 0 0
 4 0 -256 256 0 -476 226 | -256 256 0 0 0      24 0   91 -183  91 -45 62 | 256 0 0 0 0
 5 0 -256 256 0 -458 216 | -256 256 0 0 0      25 0   87 -175  87 -31 62 | 0 0 0 0 0
 6 0 -256 256 0 -448 208 | -256 256 0 0 0      26 0   83 -167  83 -17 62 | 0 0 0 0 0
 7 0 -256 256 0 -418 193 | -256 256 0 0 0      27 0   80 -160  80  -2 62 | 0 0 0 0 0
 8 0 -256 256 0 -396 182 | -256 256 0 0 0      28 0   76 -152  76  11 62 | 0 0 0 0 0
 9 0 -256 256 0 -374 170 | -256 256 0 0 0      29 0   72 -145  72  27 62 | 0 0 0 0 0
10 0 -256 256 0 -352 160 | -256 256 0 0 0      30 0   69 -138  69  63 42 | 0 0 0 0 0
11 0 -256 256 0 -320 140 | -256 256 0 0 0      31 0   65 -131  65  57 64 | 0 0 0 0 0
12 0 -256 256 0 -234  97 | -256 256 0 0 0      32 0   61 -123  61  73 65 | 0 0 0 0 0
13 0 -256 256 0 -114  33 | -256 256 0 0 0      33 0   58 -116  58  89 67 | 0 0 0 0 0
14 0  128 -257 128 -178 81 | 256 0 0 0 0       34 0   54 -109  54 105 68 | 256 0 0 0 0
15 0  127 -255 127 -171 62 | 256 0 0 0 0       35 0 -256 256 0 -499 244 | -256 256 0 0 0
16 0  123 -247 123 -157 62 | 256 0 0 0 0       36 0 -256 256 0 -457 230 | -256 256 0 0 0
17 0  119 -239 119 -143 62 | 256 0 0 0 0       37 0 -256 256 0 -511 255 | -256 256 0 0 0
18 0  115 -231 115 -129 62 | 256 0 0 0 0       38 3 -2048 2048 0 -4024 1929 | -2048 2048 0 0 0
19 0  111 -223 111 -115 62 | 256 0 0 0 0       39 2 -1024 1024 0 -2012 989 | -1024 1024 0 0 0
20 0  107 -215 107 -101 62 | 256 0 0 0 0       40 2  200 -401 200 962 742 | 70 -140 70 1131 389
```

**濾波鏈** sens→lpf→hpf→gup→sft→mdn:
1. **sens** 數位增益(`af_digital_gain = base×sens%/100`,reg 0x30050464)——先做,曝光無關。
2. **lpf** 低通預濾(降噪)。 3. **hpf** 帶通組(HIGH+LOW 並行)。 4. **gup** 增益。 5. **sft** 輸出位移。 6. **mdn** 中值濾波。
AfParam 結構:sens[20]@+0x00、hpf[20]@+0x50、gup[16]@+0xa0、lpf[5]@+0xe0、sft[5]@+0xf4、mdn[2]@+0x108。

═══════════════════════════════════════════════════════════════
## ③ lens_data +0x64 能力旗標 + CCI 浮點 — 信心:高
═══════════════════════════════════════════════════════════════

`+0x64` = 32-bit bitfield,`(*(u32*)(base+0x64) >> N) & 1`(`FUN_c033a848`)。
```
0 Zoom Sensor   1 Zoom motor   2 縮短對焦範圍   3 Macro   4 OIS(T機身忽略)
8 支援CMD_Focus(drive5)  9 OIS on/off開關  10 AF-MF選擇開關  14 有光圈環  15 光圈環解析度切換
16 Focus MO開關  17 OIS Panning開關  19 對焦限位開關  20 AF功能設定開關  21 AF功能鈕
22 對焦預設鈕  23 延伸對焦速度  24 固定角度MF  25 支援T-Value  28 Multi focus limit
5,6,7,11,12,13,18,26,27 = 保留/內部
```
28mm(0x04011CA0)= bits{5,7,10,11,12,16,26}:bit10 AF-MF開關、bit16 Focus MO鈕,餘為保留。

**`+0xa0/a4/a8` = CCI_R/G/B**(Color Contribution Index,鏡頭每通道**色偏指數**,ISO 標準)。
⚠️ **更正(色彩科學 RE 確認)**:CCI **AWB 完全不用**,唯一 reader 是 `dumpLensData @c033ab88`(除錯列印)= 純診斷。鏡頭實際色校走 `cor_data`/shading 欄位(+0xc8+),非 CCI。見 `COLOR_SCIENCE.md` ①。
28mm:CCI_R=8.8、CCI_G=7.4、CCI_B=0。**用途:色彩/白平衡補償,非對焦。**
(其他:focus_pps min/max/movie @+0x78/7c/80;aperture_pps @+0x94/98/9c;reduce_distance @+0xb4。)

═══════════════════════════════════════════════════════════════
## ④ 機身 EV / APEX 計算 — 信心:很高
═══════════════════════════════════════════════════════════════

**編碼**:Av/Tv/Sv/Bv/Ev 皆 signed int32,單位 **EV×1024**(1格=1024,shell 字串 `[APEX x1024]`)。
恆等式 **Ev = Av + Tv = Bv + Sv**(整數相加)。log2/exp2/round:`c01f6d24/c01f6a3c/c067e2ac`。

**測光→亮度→Bv**(`FUN_c0219f88`):
```
Bv = Bv_施加中 + round( 1024 · log2( YLevel / 8522.363 ) )
```
`8522.363` = 正確曝光目標 YLevel(參考中灰)。YLevel = 亮度網格區域**平均**(`FUN_c0210d88`/`FUN_c0211098`,非累加器):`Σ(Y·w)/Σw`,權重 w∈0..63(6-bit);測光模式:全平均/中央aveq/ave4(2×2)/多分割加權。
**★ 刻度 ↔ 8-bit luma**:區塊 Y 是 **16-bit ushort**(測光緩衝),YLevel 為其正規化均值(無 `>>` 位移,除以 count/權重和)。`YLevel_8bit ≈ YLevel_16bit >> 8`(推定;區塊 Y 全刻度由測光硬體定,decomp 未證)。只影響絕對值不影響 AF 峰比較。(注意 `YLevelTargetTH::v3 @c02135a0` 另有 `×0x1AD>>8 = ×1.676` 目標/gamma 因子,非 8-bit 換算。)

**APEX 換算**(常數 binary 驗證):
```
ISO→Sv:  round(1024·log2(ISO/3.125))            [FUN_c04d01f8]
Fno→Av:  round(2048·log2(Fno))                   [FUN_c04cfdd0]
時間µs→Tv: round(1024·log2(1e6/t_µs))            [FUN_c04cffa0]
通用linear→APEX: round(1024·log2(x))             [FUN_c04d04d0]
反向 exp2 版對應 FUN_c04d0138/c04cfd18/c04cfe30
```
驗算:ISO100→Sv5120、f/2.8→Av3042、1/60s→Tv6049 → Ev9091。

**補償/偏移疊加**(`FUN_c0226f58`):`Bv + 測光模式偏置(0x33d9基準) + TargetBvShift + 臉/AF區偏移 − ExpComp(1/3EV=341) − PLine限制`。
**AE↔AF**:AF 用同組 APEX 換算把對比評價值除增益、按 shutter/fno 正規化(`aft: gain/shutter/fno`,`UpdateGainAllowance @c0286798`)。

═══════════════════════════════════════════════════════════════
## ⑤ AF-C 主體移動判定 + 運動預測 — 信心:高
═══════════════════════════════════════════════════════════════

峰位環形緩衝(10 筆,每筆 0x20B:`+0x18 pos, +0x1c dist, +0x14 time, +0x10 dir, +0x08 area, +0x0c mode`)。

**判定**(`JudgeSubjectMoveByPeakData @0xC02766A8`):
- 收集有效峰位(`now-time ≤ 10000ms`,area/mode 相符),index0=最新;dir==0 加背隙 offset。
- 相鄰差分(最多 3 個):`DiffTime=max(1,Δt)`、`DiffPos`、`DiffDist`。
- 方向一致性(`FUN_c02772b8`):`|DiffPos|<staticThr`→靜止;反向剔除;否則距離外插 `pred=dist+Δt·ΔDist/ΔTime`,實測落 **±30%帶**(×0.703~×1.297)→ forward/backward++。
- 結果:static≥nDiff→1(靜止);forward≥nDiff−1→2(接近);backward≥…→3(遠離);else 0。只有 2/3 才預測。

**運動預測**(`CorePeakPosEstimateSubjectMove @0xC0277580`,8.8 定點):
```
speed = (ΔDist<<8)/ΔTime
avgSpeed = (2·avgSpeed + speed)/3            // 指數平滑
若 avgSpeed/speed > 2 → 加速模式,丟歷史只用當下
avgSpeed = avgSpeed · gain(speed) >> 8       // gain: <131→272, ~171→320, ≥171→368, else256
predDist = avgSpeed · DiffTime_predict >> 8
DiffTime_predict = 快門延遲常數(45~270ms) + (now − 樣本時刻)   // 預測到下一格曝光
```
**套用**(`SAF_EstimateCore_NearAfAfterSearchPeak @0xC0277CE8`):`correctedPeak = currentPeak + predDist·posGain(dist)>>8`(posGain 依距離 0x70~0x160),再**夾限到鏡頭近/遠極限**(超出保持原值)。
線性外插(非拋物線)。[Focus/Scale Tracking table] 是**鏡頭校正表**(距離↔脈衝,Scale 32點,1000000=∞),非 runtime 變數。

═══════════════════════════════════════════════════════════════
## ⑥ 六種驅動策略 — 信心:高(架構)/中(逐 lens 係數)
═══════════════════════════════════════════════════════════════

**架構**:`AfMgrProcess*`(狀態機,vtable v1–v16)→ `AfMgrDrive{Scan,Intermittent}`(馬達控制)→ 共用驅動數學。
per-frame 狀態機 `FUN_c0259d50`:`mgr+0x18`=state(0–6)、`+0x1c`=**NextRoute**、`+0x38`=現用策略。回傳 3=完成/4=續跑/5=鏡頭忙。
vtable:v1 init、v2 timing閘、v3 首脈衝、v4/v5/v6 驅動階段、v7 afterProc(選峰+判定+微修)、v8 重試、v9 翻向、v10/v11 步幅/數/限位、v14/v15/v16(Near&Hybrid共用)峰掃+近端優先+katayama。
NextRoute 值:0 正常、2 續往限位、3 換區重搜、4 二次重試、8 交棒 SlowAF、9 katayama 終止、0xD 反向對比重搜、0xE Hybrid 初始。

- **Fast**(0xEC):大固定步爬山;`step` 來自 lens vslot+0x58(key 0x77)或 min(DoF/10, lensStep);還在上升就延伸(`counter max update`);重失焦重試;峰值用 sub-step LUT(`-0x3cd6e9bc`)修正。
- **Slow**(0x48,route 8):視窗置中現位置;**步幅固定**,靠取樣找對比最大;近遠邊還在升就 +1 步;外部峰偵測(vslot+0x154)觸發截斷。
- **Near**(0x98):首步一個 g_afstep;內層迴圈跑 **sweep waypoint 樣本(非空間區)**;v16 接受**從 seed 最近**且過門檻的峰、confirmations≤5(或 3);katayama → route 3/9。接受門檻(v16):`span (max−min)>min/32+16`、`tail-drop (max−last)>max/128+70`、`max≥256`(v15 另需>288)、非遠端邊界。**運動預測 posGain(★更正,非 0x60/0x50)= `FUN_c0277c48`:非伺服 0x70;AF-C dist<150→0xd8/<1000→0x110/<1500→0xd8/else→0xa0;特殊+0x145→0x160** = {0x70,0xa0,0xd8,0x110,0x160}。seed `correctedPeak=peak+(predDist·posGain)>>8`(僅 approaching(2)/receding(3) 套),夾鏡頭 near/far,位移上限 mode-3{350,500,∞}。
- **Rocking**(0x54,route 0xE):擺幅=1 步;擺數 4(前次決定與現向一致則 6);peak-hold(`+0x50`)判方向,掉出峰值+遲滯(需 peak−current > lens 門檻)才反向;定向後交棒。
- **Hybrid**(0x10C,route 0xE):`[0x29]` 0→1→2 兩階段。**Stage1**:選最可靠 PD 區、快驅向 `+0x40` 目標,近目標 overshoot clamp;**Stage2**:對比在 PD 錨定窗 `[target±margin]` 內用 v14/v15/v16 精找;主體移動則重加速;失敗 → route 3/0xD;v7 交棒 SlowAF(除非 isDontSlowAf)。
- **ContShooting**(0x40):用**上一格** pos/step(`start continuous shooting af: pos/step/prev_frame`);按剩餘脈衝預算 clip(`clip drive pulse: cnt_/max_cnt`)。

**共用驅動數學(★ 實際值 + 重要澄清)**:
- **key `0x77` 是 sentinel 不是鏡頭值** —— runtime 換成當前鏡頭 profile key = **8**(28mm 與 40mm 兩顆從 dump 讀出**都是 8**)。所以 step 表是 **ROM-global,這兩顆共用**;真正 per-lens 差異在 FocsPred/lens_data(名字/距離曲線),不在這張表。
- 步幅:**脈衝單位 `FUN_c032c7b8(0x77)` = 16683**(ROM key-8 record,`(330·(3640−1)+330)·1000/72000`);**g_afstep raw = 60**(0x64-record +0x40);`FUN_c025b190`:route==8 時 `step/=2`,否則對 16683 取下限。Fast/Slow/Rocking 共用此 min-step clamp。

**CDAF 逼近/掃描/重對焦機制(★ live,對比式跟焦該復刻的就是這些)**:
- **Q1 峰值逼近 = 單次 move-to-vertex + 條件式重掃,非 settle 迴圈(HIGH)**:`calIntrPolAreaAfPeakPoint` 純在掃描樣本上算頂點(寫 `_DAT_c32914e0`,不下馬達、不重取樣);`AfMgrProcessFast::v7` 套一次 Fast sub-step 修正 → **提交目標一次 → 選下一 route**,Fast route 內**無 measure→compare→nudge 迴圈**。是否重掃依信心 `isDontSlowAf @c023ac48`:**跳細掃 iff `peakDelta < 0.55·DOF` 且峰內部乾淨且前置未否決**。`peakDelta = max(|mpos[peak]−mpos[peak±1]|)` = **粗掃峰兩側較寬的 waypoint 間距(脈衝)**(mpos=位置陣列 `param_3+0x4c`,peak=對比 argmax `_DAT_c32915f2`;index0→sentinel→失敗);`step`=`param_1[7]`,28mm=`2×304=608` —— **★不是光學景深,是原廠 EEPROM 容差常數(原始脈衝)**:28mm(comm-state 0xb≠5)走 `FUN_c0332878` else 分支 `*(0xc347df60)<<1`,**零光學輸入(無 CoC/Fno/焦距/距離)**,靜態(dump=304)。CoC-based 光學算法(`FUN_c034fe50`,5940nm 像素 CoC)只在 PDAF/state-5 分支,28mm 不走。608 與 mposm 同域(1:1 脈衝),全行程 0→11127,608=5.5%。判式 `iVar4=peakΔ·2000/608; floor(iVar4/100)·100≤1000`(=`peakΔ<0.55·608=334 脈衝 ≈ 一個粗掃步 341`)。前置否決:`param_1+0x29` bits4/5 或 `**(param_2+0x2218)` 非 0→強制全掃。**這是「粗掃密度 vs AF 容差」的檢查(非光學景深):粗掃步 <334 脈衝 → 信任粗峰跳細掃。★復刻端:閘用 608 脈衝直接算,不換 µm、不套 CoC、不套光學 umCalibration —— 光學焦深(≈0.19–0.30 校準)是另一個具名量,別和這個 AF 容差混用。** 弱峰/katayama → route 8 交 `AfMgrProcessSlow` = 對頂點開窗的**全新精細再掃**(非 nudge)。→ 復刻:單移動+等 drive-end;**開不開細掃取決於你粗掃密度÷DOF**,密掃(<0.55·DOF)本來就該跳、現況即韌體行為;**不要 settle 迴圈**(會被距離夾限掩蓋成假綠,實測迴圈更差:+散布2、慢0.1s vs 單次+1散布0)。
- **Q2 DriveScan(等速) vs DriveIntermittent(走停)selector(HIGH)**:**Fast + Hybrid stage-1 硬接 DriveScan 等速,每顆鏡頭**(`FUN_c022c1b0`,不進 selector)→ 粗掃一律等速。只有 Slow/Near/Rocking 由 `FUN_c02a3780` 依 `ratio=(鏡頭metric·20)/掃描cadence` 選:Slow/Near `ratio>9∥metric<0→Intermittent`、Rocking `ratio>2→Intermittent`,否則 Scan。28mm movie:粗掃等速;精細/伺服僅慢快門/大行程(ratio 超門檻)才走停。ratio runtime(快門/fps/鏡頭 metric),靜態無常數。DriveScan mgr `0xc32069cc`/vtable `0xc091c50c`(v2=`c0238a28`);Intermittent mgr `0xc3206aec`/vtable `0xc091c4e0`(v2=`c0237fb0`→`FUN_c035ffc0(pos±(backlash+1)·pulses)`)。
- **Q3 重對焦非陀螺 gate(見 ⑧ 修正)**:漂移監視器 `FUN_c028a360`(框移動/場景 luma/計時)觸發普通重驅;Rocking 伺服才是陀螺專屬。
- **★ 重對焦策略 = Near(局部)不是 Fast(全掃),+ 兩個每幀早退(決定 AF UX,HIGH)**:兩路徑 —— (A) body-motion→**Rocking**(±1 步,不經 picker/不重掃,CAF 主力);(B) 漂移重驅→picker `FUN_c028d2b0`(狀態重置,`_DAT_c32914e0=FUN_c035fd48()` seed 當前位)。picker case1:ContShooting→**Near**(`FUN_c0257080==1`)→Fast→Hybrid(死碼)。**AF-C(`+0x20c8==4`)把 Fast 票(2)降成 Near(1)**(`FUN_c0257080` @57349)→ 影片走 Near,靜態才 Fast。**Fast**=全機械行程(near→far,341 步,30 wp,終止於 interior 越峰);**Near**=首步 g_afstep、跑 sweep waypoint(非空間區)、**接受「從 seed 最近且過門檻」的峰就停**(不到限位)、**seed=上次峰+運動預測** `correctedPeak=peak+(predDist·posGain)>>8`(posGain={0x70,0xa0,0xd8,0x110,0x160},見 Near 段)。**兩個方向早退(不等限位)**:①每幀越峰 `FUN_c0263078`(Fast::v5):對比比 running-max 掉 **>1/32(>>5≈3.1%)** 且**過絕對對比地板** `scanDesc+0x34`(=判斷閾 peak/128+70)才宣告越峰(rising re-arm 假峰恢復);**雙向各記 max**;②`FUN_c02637a8`(每幀,debug `"reverse..."`)committed 方向但位置沒越過起點且非限位→回 3 反向。**(`FUN_c0263e60`+minPeakIndex 29 是 sweep 後的 mode-2 邊界分類,非越峰早退 —— 見 ①)**無 pre-commit wobble(方向感測內嵌 sweep)。→ 復刻:重對焦用 Near+seed 上次峰、對比掉 3% 終止、無進展反向,勿驅到 bound。
- **★ 掃描 lag = 韌體有補償(曝光中心相位項,HIGH)**:`mposm[k]`（`DAT_c3291958`）存的是**該幀曝光中心時**的馬達位置,非讀出時位置。`FUN_c0239118`/`FUN_c0238560`:`delay_removed=(delayConst×frame_period_µs)/100 + readout/2`,`mposm=interp(3-tap 真實 LDAFR 位置, 曝光中心時間 − delay_removed)`(velocity 內嵌於真實位置內插)。字串 `"...exposure_timing_just_center..."`。→ **韌體偵測峰已 lag-補償、落真峰**;固定 rate 下未補償會偏 `lag·rate`(實測 175 單位@lag≈0.13s)。常數 runtime(sensor-timing vtable +0xec 延遲%、+0x3c readout;readout 模式相依,無 28mm 字面值)。復刻:補回 velocity×[sensor延遲+½readout],**是忠實復刻非改良**。

> ⚠️⚠️ **以下 `lensScale` / `CalcCafDriveSpeed`(Phase A–D)/ pkcnt 累積 / ×3/10 近峰減速 = PdCaf(相位偵測)路徑,在 fp 上是死碼(Q43,獨立反編譯驗證)。** fp 是 **CDAF-only**:AF-model 子類 vtable(`0xc092b8d0`)**slot 0x184 = `0xc029ba08` 無條件 `return 0`**,而 `CalcCafDriveSpeed` 唯一呼叫點(blk_c02.c:48953)前一行 `if (slot0x184()!=0)` → **永不執行**;同閘也 gate 掉 pkcnt 寫入、PdCaf setup、PDAF 可用性 `FUN_c028f3c0`。`measured_defocus`(0x7d240)是相位→脈衝,fp 無 PDAF → 恆 `-0x80000000` sentinel。
> **保留下列刻畫僅作「PdCaf 路徑長怎樣 / 什麼不該對比式復刻」的記錄。對比式跟焦要復刻的是上方 Fast/Near/Rocking + 拋物線峰插值 `calIntrPolAreaAfPeakPoint @c0263ff8` + move-to-vertex,不是 ×3/10 減速。** getter 真實位置/drive-end 取樣、divisor/cadence 是 generic 仍有效(fp 上 observer 驅動的是 CDAF servo)。
- **`lensScale`(param_3+0x98)= `_DAT_c33c80e8`,實際**恆等於 60**(★二次更正:不是「~16–60」、不隨幀率變、更不是電壓)。**
  - 算式 `lensScale = min( FUN_c035fec8(0)/10=60 , FUN_c035fda8(FUN_c023c9b8()) )`。
  - `FUN_c023c9b8` 比 `FUN_c0125ca8()` = **幀週期 µs**(H×V×1000/72000),依帶給 `<9→8333…else→33333`(9/15/18/21/22 **ms** 帶)。
  - `FUN_c035fda8(x)=x/(1000000/K1)`,`K1=*(0xc3464980+0x7c)`=鏡頭 pulses/s(28mm=37000→x/27)。逐帶 fda8:8333→308…16666→617…33333→1234。
  - **min 永遠取 60**:任何 fp 幀率(8–33ms)fda8 輸出都 ≥308 ≫ 60(60fps→617、30fps→1234,皆 `min(60,·)=60`);結論對「fda8 在 cap 前/後」免疫。
  - → **驅動代 `lensScale=60`**:`index=|defocus|/6`、`raw=rate·3.75`、近峰上限 `60·coeff2`。**舊「電壓帶」「16 純猜」「~16–60」皆誤;讀 sensor timing 但結果恆 60。** K1>~1800 pulses/s(全部真實鏡)都 pin 在 60。
- **★ `CalcCafDriveSpeed` 的回傳 `out` 是「每次評價的脈衝步進」,不是 pps 速度(Q39,HIGH,追消費端證實)。** 消費:`out` 被夾成 `|current−target|−1`(距離夾限,只對位移有意義)→ `target = current_pos + sign·out`(current=`FUN_c035fd48()` 位置 getter vtable +0xb4)→ move-to-absolute(vtable +0xb8/+0xbc);移動速度是**另外分開算**的參數,無速度暫存器收 `out`。**每 tick 走 `out` 脈衝,τ = tick/0.3**。呼叫頻率:每連續 AF 觀察通知一次,**Ver.5.02 可達 CAF divisor 只有 1(每 Vd~17ms)或 2(每 2 Vd~33ms,readout 9/10 模式);divisor-6(mode5)從不設定**(見下 Q divisor)。→ τ≈0.056s(divisor-1)或 0.11s(divisor-2)。**(舊註「~106ms=divisor-6」錯 —— 那是外部復刻端自己的 sleep,非韌體。)****`pk`/`target` 皆 encoder 脈衝、與輸出同域、零換算。** `3`=韌體結構欄位 `FUN_c0298460[0x12]=3`、`10`=硬編字面(非 /lensScale、非粗表 key 的 ·10)。
- **★ `FUN_c035fd48` getter 回「真實/量測位置」但只在 drive-END 取樣(Q41,HIGH)** —— `LmountFocusL::v3=*(obj+4)`,+4 是鏡頭經 SPI「LDAFR」封包回報實測對焦位的快照(checksum 驗證),指令目標在**另一** field `+0x18`。+4 只在 `focusDriveTaskProc` 驅動-END 刷新 → CAF 每 tick `target=getter()+sign·step` 錨在「上次已完成驅動的真實結束位」,驅動進行中 stale、不回中途進度。→ 原廠用真實位置卻不「快 cadence 停更遠」的原因:**move-boundary 取樣、非 mid-move**;落點精度靠「drive-end 錨定 + pkcnt 連續小離焦 gate」而非 tick 快慢。閉環(機身持續輪詢鏡頭實測脈衝),28mm 走 native-L(`_DAT_c3476408=1`,dump 確認)。
- `CalcCafDriveSpeed @c027eeb0`:`defocus=(curPos+areaOffset)−target`;**遠距**:`rate=FUN_c02982c0(粗查表)` → `raw=rate·lensScale/16`,搜尋中×2/3,`speed=(prev+raw)/2` 單極低通(state `_DAT_c33d5148`);**近峰**:步進 `out=|remaining|·3/10`(近距)、`·1/10`(中距),上限 `lensScale·5=300`。lensScale=**恆 60**。輸入 defocus/thr=脈衝、reliab=PDAF 可靠度、**輸出=脈衝步進/評價**。(gate/coeff 見下 Q37/Q38/Q39)
- **`FUN_c02982c0` 粗查表(Q37,直讀 ROM,方向:key 大→rate 大)**:`key=(|defocus|·10)/lensScale`(**abs 有套用**,恆非負;負門檻只是恆真地板)。選表:`area+0xC==2`→area2 表;`reliab<0x3d(61)`→**全 0 表(不驅動)**;僅 reliab≥61 有非零。
  - Table B(非area2,reliab≥61):`key≥1500→320、≥1000→256、≥700→80、else→0`。
  - Table D(area2,reliab≥61):`key≥1000→320、≥500→80、else→0`。ROM:desc `0xc0925530/38/40/48`→data `…50/80/b0/d8`,每格 `{int 門檻,int 值}`。
  - **@lensScale 60:rate 80 需 |defocus|≥4200 脈衝、256 需 ≥6000、320 需 ≥9000**。→ 粗表是「遠距快驅」,小誤差(如 565→key 94)**正確地回 0**;近距合焦靠下面的近峰線性減速分支。舊轉述「1500→0…400→320」是**去重且反向**,誤。
- **`CalcCafDriveSpeed` 完整結構(Q38,四相,HIGH)** —— tuning 常數由 `FUN_c0298460` 填(非 `FUN_c02983c8`):
  - **A 分類(Q Phase-A,HIGH)**:defocus=`(curPos+areaOffset)−target` 符號+焦限 → idle / searching(srchIdx) / committed(cmtIdx)。鏡像結構:searchState==1 用遠限 `desc+0x8c`+「落後 `defocus<−120` 只搜」;!=1 用近限 `desc+0x90`+「`defocus<=120` 才候選」。**`FUN_c0360048()`=「isAbs 絕對定位?」= `(driveType!=0x21)`;28mm=0x20→isAbs=1→永遠走數值焦限分支。** `FUN_c0360058()`=end-stop/方向旗標,僅相對鏡(type==5)有意義,28mm=0(且 abs 不讀)。commit 條件(abs):預測位 `curPos+areaOffset` 在限內 且 `|areaOffset|<600+|limit−curPos|`。COMMIT_CONFIRM:封套 `|dCmt|<=960 且 desc+4<0`→撤銷;PD veto `FUN_c0281c40`(區status∉{4,5}且+0x7dcd8旗標)。LIMIT_POST:貼行程末端且 `|dCmt|>12000`→清 cmt+srch。替代「符號穩定+在限內」分岔點:落後cutoff、限位鄰近(600規則)、預測vs當前位、封套、PD veto、末端大離焦清除。
  - **B 粗速+LPF**:`raw=rate·60/16`;**搜尋(未commit)才 ×2/3**,committed 用滿 raw;`speed=(LPF+raw)/2`,`LPF(_DAT_c33d5148)`=**全域單一 state**,idle 時歸零;`speed==0→prevSpeed`(唯一 0 地板)。
  - **C 近峰覆寫(★走不到目標的關鍵)**:gate `pkcnt=*(afctx+0x7d98c+area*8+8)`。`pkcnt<2`→用粗速;`pkcnt≥2` 進近峰,但**減速公式只在「接近側 且 pkcnt>5」才接手**(過衝側只有 300-cap)。`remaining=pk−target`(pk=`+…+4` 儲存峰位,encoder 脈衝)。桶(順序 near-first,已字面確認):①過衝側 且 `|rem|>3000`→cap `300`;②接近側 pkcnt>5 `|rem|<3000` 且 `(3|rem|)/10<現速`→`×3/10`(0.3·err);③接近側 pkcnt>5 `3000≤|rem|≤360+7·speed` 且 `|rem|/10<現速`→`×1/10`;④其餘不變。`×3/10` **在** `×1/10` **之前**,後者只見 `|rem|≥3000`。**`2≤pkcnt≤5` 或過衝側小 rem →不接手=stall(復刻 AF「走不到」根因,實機證實 pkcnt 卡 0 時 stall)。**
  - **D 安全閘 = PDAF 路徑專屬(Q40,對比/CDAF 到不了)**:`desc+4/+8/+0x40` 由 PDAF/sensor vtable 每幀填;`CalcCafDriveSpeed` 對非 PDAF 態在 `desc+0x58!=0`/「Impossible Image」早退。閘:`q1(+4)<10 ∥ q2(+8)<3000/1000 ∥ thr>1 ∥ |dir(+0x40)|≥3`→hold。末 `out<param_4→param_4` 是**本幀內地板、非跨-tick 棘輪**(`param_4`=caller 每幀重算的粗候選,非持久 prevSpeed;持久平滑 state 是另一個 `_DAT_c33d5148` LPF,不鎖高)→ decel 可逐 tick 下降。
  - **不要在近峰分支加最小速度地板** —— `|rem|·3/10` 本身是防 stall,故意可趨 0 好精準停峰;要修的是讓 pkcnt 過 5。**從靜止 stall 是因粗候選=0→`min(0.3·err,0)=0`;韌體從精掃帶著非零粗候選接手(handoff),故不 stall。** Worked(step 語意):565@pkcnt>5→步進 169 脈衝→~10 步收斂;實機全 fwaf ≈6.8s、停峰後 +17~19(DoF/2 內)。
  - **pkcnt 遞增機制(Q42,HIGH,寫在另一函式 `FUN_c027faa8`,`CalcCafDriveSpeed` 只讀)**:SEED = 某區首次 `metric>60` 且 pkcnt==0 → `pk=target(=current_pos+defocus); pkcnt=1`。INCREMENT(+1)需同時:①`metric>60` ②**`|defocus|≤50·scale`(≈3000 脈衝,與近峰 `|rem|<3000` 同界)** ③峰穩定 `|Δpeak|≤(|defocus|/10+1)·scale+6·scale`;`pk=(target+old_pk)/2`(跑動平均,非 argmax)。RESET→0:`metric≤60`/defocus 無效(`-0x80000000`)/出限位/AF 重啟。HYSTERESIS:單壞幀但 metric 可靠→**hold(pkcnt 不變)**,只有不可靠/無效才歸 0。**同一條「小離焦且穩定」謂詞既是自然累積(趨近~6 幀爬過 5→減速接手)又是防 mid-move-lag 騙閘**(落後樣本殘餘離焦大→②fail→不進);故復刻端 **pkcnt 要「賺」不要強拉**。scale=`*(desc+0x98)`(runtime pulses/DOF)。metric=PDAF 可靠度→對比系統需換等效(峰 SNR/曲率),唯一「概念對應非照抄」點。
- `CalcPdCafDriveDir @c027e3e8`:**遲滯投票** `_DAT_c33d5144`,band **[−2,+2]** → **需 ≥3 連續同向票**才翻向。常數(`FUN_c02983c8`):peak-reached 門檻 **100×lensScale**、slope factor **11(/10)**、可靠度地板 30、遠限 200×lensScale。翻向條件 `|pos−target| ≤ 100·lensScale 或 (slope·11)/10 ≤ |pos−target|`。
- **Fast sub-step「LUT」`-0x3cd6e9bc` = `0xC3291644`,不是 ROM LUT** —— 是 RAM scratch(int32×~17,PDAF 相位樣本)。每幀寫 `|peak − phase[i]|`,讀時按方向累加進驅動目標累加器 `_DAT_c32914e0` → 粗峰細修。runtime-only,無 ROM 初值。
- `CafPdDriveMain @c024a230`:state 6=續驅/2=停(停因 bits `_DAT_c32918d8`);pipeline CafMode5_CheckPdaf→JudgeDrive→CalcDrivePulse/LastDrivePulse;**peak=連續 N 格小離焦**。
- **DriveScan vs Intermittent**(vtable slot 8 區分):Intermittent=固定脈衝走停(`FUN_c035ffc0(pos±(backlash+1)·pulses)`,步進+沉降,3-deep 位置歷史);Scan=一次等速驅動不停(`speed=pulses·2000/((backlash+1)·shutter·(fps+1))`),算**曝光中心對應的移動中位置**。

═══════════════════════════════════════════════════════════════
## 關鍵位址速查
═══════════════════════════════════════════════════════════════
| 主題 | 函式 |
|---|---|
| DefocusPerPulse | 展開表 lens_data+0x10c58(dump 內!);解析 FUN_c0338510←FUN_c03341c8;wire read CmdRead FUN_c0355be0;縮放 DAT_c03376e8(2⁻¹⁶);defocus→脈衝 FUN_c034fe50 |
| HPF 主表 | DAT_c2f1e918(seg1+0x27B18,40×0x1C;runtime 只查前 36 筆→key15-18 不可達);key→頻率 legend DAT_c0918f20 |
| HPF 運轉選對 | **FUN_c02a4580**(算 HIGH/LOW,AF-model 0xc34046a4 vtable+0xC);套用 FUN_c023b748;key→係數 FUN_c032ce30;HW 寫 FUN_c06371e0(HIGH)/c0637290(LOW) |
| 能力旗標 | +0x64 bitfield,FUN_c033a848;CCI +0xa0/a4/a8;dumpLensData @c033ab88 |
| EV/APEX | YLevel→Bv FUN_c0219f88;主測光 FUN_c020a3c0;APEX FUN_c04d01f8/c04cfdd0/c04cffa0/c04d04d0;偏移 FUN_c0226f58 |
| AF-C 預測 | Judge FUN_c02766a8;預測 FUN_c0277580;套用 FUN_c0277ce8 |
| 六策略 | 狀態機 FUN_c0259d50;Fast c025c230;Slow c026fd60;Near c026a688;Rocking c026e998;Hybrid c0265960;ContShoot c025b980 |
| 共用驅動 | CalcCafDriveSpeed c027eeb0;CalcPdCafDriveDir c027e3e8;CafPdDriveMain c024a230;DriveScan c0238a28;DriveIntermittent c0237fb0 |

═══════════════════════════════════════════════════════════════
## ⑦ 驅動細節十題(反編譯 + 28mm dump 交叉驗證)
═══════════════════════════════════════════════════════════════
基準:ROM `out/seg0_c0000000.bin`(base 0xC0000000);28mm 活體 dump `dumps/28mm_sigma/HEAP34.bin`(base 0xC3400000,offset=addr−0xC3400000)。物件身分已驗:`*0xc347fa6c=0xc3464850`(LmountFocusL,vtbl 0xc0b8da14)、propObj `*0xc343b7cc` vtbl 0xc0b8d730、FocsPred `*0xc3476414` vtbl 0xc0b8eeec、`*0xc347df60=0x130(304)`、`*0xc347cb8c=0xb`(鏡頭通訊 state)、lens_data=0xC3464980。

### 一、會改變行為
**① `FUN_c0263e60` param_3[1] = waypoint_count−1 = 29 —— ★ 只 gate mode-2 邊界分類,不是「掃到底才判峰」。** 信心 HIGH(更正)。
`FUN_c0263e60` 是 **sweep 後的峰確認**(Fast::v7,掃完一次,呼叫 `calIntrPolAreaAfPeakPoint`),**不是**每幀越峰。字面:插值(return 1)僅當 NOT `(count<3 ∥ mode==1 ∥ (mode==2 && (peakIdx<29 ∥ (peakIdx<=29 && peakIdx==count−1))))`。`mode`(`+0x68`,0 clean/1 still-rising/2 rolled-over)由 v5 每幀依對比斜率趨勢寫。**`+0x6c=29` 只用在 mode==2 分支**:mode2 且 peakIdx<29 → 拒;因 29=count−1,mode2 永遠拒 = 「掃到遠端仍升=邊界無 interior 峰」終止。→ **不是「越峰前必須到達的最小索引」、不是掃到底的原因。** 每幀越峰早退是 `FUN_c0263078`(見 ⑥)。呼叫者 v7/v3(param_3=this+0x68)。

**② YLevel/peak 量級 ≈ 1e4(1e4–2.5e4)。** 信心:1e4 量級 HIGH,上界 MEDIUM。
**2026-09-16 更正：** HIGH `DAT_c32985e8[]`／LOW `DAT_c32986b4[]` 是經分帶縮放、條件修正、32-bit 飽和的 u32 累加量；mode 1 加 256，其他 mode 加 0。`FUN_c023ec28` 寫 AF-ctx `+0x21c0/+0x21c4` 時只減該固定 offset，**不是掃描最小值或物理 noise floor**。來源 `blk_c02.c:44236–44271,44363–44448`，詳見 [方向與訊號診斷](FP_AF_DIRECTION_DIAGNOSTICS_2026-09-16.md)。原廠判定常數仍為:SIGMA 鏡 judge `FUN_c02a2f18`(28mm profile-key=8)的 `saf_jdat_l` 分級 **0x300=768 / 0x1000=4096 / 10000**,area0(`_DAT_c32914fc`)參考 **25000**、強判 gate 24999。這些是分支門檻，不是通用幅度上界或跨增益不變性的證明；移植至其他指標須重校。
- 門檻 `v26 @c0299b80` case5 = `peak/128 + 0x46(70)`(存 ctx+0x34);`v25` = `peak/16+16`(ctx+0x30)。`peak/128` 比例項尺度不變 → 可直接移植;**`+70` 地板**在 peak≈8960 時等於比例項,對焦清楚(~1e4)時佔 ~0.7%。**換算亮度正規化指標**:保留 `M/128`,把 `+70` 換成 `70·(M*/1e4)`(M*=你指標對焦典型峰值)。

**③ drive-mode(ctx+0x20c8)/ state(ctx+0x21f4)—— body RAM,不在鏡頭 dump。** 信心:邏輯 HIGH。
ctx 建構子 `FUN_c022bfe8`;`ctx+0x21f4` 是指標(→`&DAT_c32915b0`),state 值=`**(ctx+0x21f4)`;`ctx+0x20c8`=drive-mode=`ctx+0x2258` 之副本(`FUN_c022b118`)。搜遍 HEAP34/35/37/38 零命中(0xc329/0xc320 body RAM)。**從碼可判**:Hybrid AF `FUN_c0269108` 設 state=**0xc(12)**→ `FUN_c029fe38`/`FUN_c029ff28` 都不落特殊分支 → **選 base-step 91,不走 617**。

**④ lensScale = CalcCafDriveSpeed `@c027eeb0` param_3+0x98 = `_DAT_c33c80e8`。** 信心:HIGH(★更正:值可推,見 ⑩Q9)。
是**回驅速度的脈衝域步進乘數**(raw=rate·lensScale/16,78048/78063/78085)。desc+0x98 = `*(0xc33c80c4+0x24)=_DAT_c33c80e8`,**每幀由 sensor 幀時序算,~16–60,cap 60**(非靜態 16、非電壓)。詳 ⑩Q9。

### 二、會改數值不改行為
**⑤ 28mm 背隙 A=0、DoF-pulses B=608 —— 已驗證 ✅。**
A=`FUN_c0331140`(propObj vtbl+0x68,經 `FUN_c03627f8`):state==5 才回背隙脈衝,否則 0;28mm state=0xb → **A=0**。B=`FUN_c0332878`(motor vtbl+0xf0),state≠5 路徑 `*(FUN_c035b310(*(obj+0x1c))+0x24)<<1`=`*0xc347df60(304)<<1`=**608**。**焦點位置索引的步幅/pps 表**在 **`0xc346d138`** = `523,558,617,703,820,512,523,558,617,703…`(**617 是表裡一格,不是 base step**);motor block base≈0xc347df3c(+0x24=304)。

**⑥ 掃描速度公式:用 base 91,不是 617。** 信心:公式/step 源 HIGH。
`DriveScan::v2 @c0238a28`:`speed = param_2×2000 / ((A+1)·B·(C+1))`。實際 **step=91**(`FUN_c029fe38=((608×15)/10+5)/10=91`)、**A+1=1**、**B=2**(`FUN_c02a5420`,非 608)、**C=live fps 暫存器**(`FUN_c0126010`=`_DAT_30100048`)。→ `91000/(C+1)`,C+1≈7 → ≈13,000 pps,被 **movie cap 12000**(lens_data+0x80=`0xc3464a00`,getter `FUN_c033de90`)封頂。step 源=Hybrid `FUN_c0269108`(scanDescriptor+0xc)。

**⑦ posGain 的 dist = 原始脈衝/位置單位(不是 8.8 定點）。** 信心 HIGH。
階梯 `FUN_c0277c48`:`dist<150→0xd8;<1000→0x110;<1500→0xd8;else→0xa0/0x70`。dist 源 `JudgeSubjectMoveByPeakData @c02766a8`;修正 `corr=(dist×gain)>>8`,**直接加到脈衝位置**(`SAF_EstimateCore_NearAfAfterSearchPeak @c0277ce8`)。dist=1500、gain=160 → 937 脈衝(對 ~11128 行程合理);8.8 定點只 3.7 脈衝(荒謬)→ **150/1000/1500 是脈衝量級**。

**⑧ Rocking 擺幅 ctx[0xc] = 鏡頭單驅動步(g_afstep 家族),不是 (遠−近)/(count−1)。** 信心:機制 HIGH。
寫入 `FUN_c026f738`:`ctx[0xc]=FUN_c023d0f0(…,0x77,…)`(讀鏡頭 drive-step,與 Fast 同源),再經 `FUN_c025b190` min-clamp(脈衝單位 `FUN_c032c7b8(0x77)`=16683);`ctx+8`=count=4(或6)。**反證**:`(遠−近)/(count−1)` 那條 `FUN_c025a918` **只被 Near/Slow 呼叫,Rocking 從不碰**;28mm 全程 4096→13369 套進去=3091/1854 位置單位,荒謬。→ 擺一整步,故實測 60 太大時退化成純隨方向交替。

### 三、確認性
**⑨ Rocking 是活的,「死碼」說法錯誤。** 信心:很高。
vtable `0xc091f6a0` 由 **movw/movt @`0xc026e950`** 組出(故 literal 掃不到,已確認 literal-pool 零引用);建構子 `FUN_c026e940` 在 **7 個呼叫點**用與 Near 等策略相同的 lazy-singleton 工廠建於 `0xc32068b4`,經 **route 0xE** 派發(狀態機 `FUN_c0259d50` 讀 mgr+0x38);含 `AfMgrProcessRocking` / `"ROCKING %s step=%d, g_b_afpos=%d..."` 字串。singleton 在 0xC320xxxx,不在 dump(但確定活的 Fast/Near 也不在,非反證)。

**⑩ 0x902F CloseApplication 的 10 bytes = 確定被無視。** 信心 HIGH。
handler `0xC04F10B0`(15 條直線指令、無資料相依分支):把資料緩衝指標(r3/param_4)存入暫存器後**從不 dereference**,無條件呼叫 `FUN_c04f4af0(obj,0)`(mode-exit)、設 `obj+0x6f5=1`、回 `0x2001`(RC_OK)。對比 `0x9035 api_open @0xC0502F88` 會 `ldr r1,[r3]` 走 `FUN_c0500f58` container-reader 解析酬載 —— **api_close 完全略過那條路徑**。→ **內容無關,送任何 10 bytes(含全零)都接受**;那 10 bytes 只是 sigma-ptpy 客戶端固定送的 data-phase 框架,韌體丟棄不看。

═══════════════════════════════════════════════════════════════
## ⑧ 連續 AF(CAF）觸發模型 = 陀螺儀「體動」→ Rocking 伺服 — 信心:高
═══════════════════════════════════════════════════════════════
**定論:fp 的連續 AF「再取得對焦」不是每輪重掃,也不是盯對比評價值掉了才動 —— 而是由陀螺儀「體動偵測」觸發。** 反編譯 + 28mm dump 實測確認。

**呼叫鏈**:序列器 `FUN_c028c620`(blk_c02.c:86372)每輪對 AF-model 物件做虛擬呼叫 `cVar2 = (*obj->vtbl[0x180])(obj, ctx)`:
- 物件 = `0xc3404678`(由 `FUN_c02a4398`→`FUN_c02a4528` 取得),vtable = **`0xc092b8d0`**(HEAP34 offset 0x4698 實測即此,確認活的)。
- vtbl **+0x180 = `FUN_c02a42f8`**(子類 AfMgrModelSingleOem_Sig **覆寫**)。純基類 `AfMgrModelSingleBase::v94 @0xc029b9e8` 是 `return 0` —— **活的物件綁的是覆寫,不是 v94**。

**覆寫做什麼(`FUN_c02a42f8 @c02a42f8`)= 體動謂詞,非掃描非評價值**:
```c
uVar1 = 0;
if (ctx[0x20c8] == 4)          // 只有 AF-C 模式(0x20c8 由 ctx+0x2258 複製,blk_c02.c:32647)
    uVar1 = FUN_c00d0800();    // 讀陀螺儀體動旗標
this[1] = uVar1; return uVar1;
```
- `FUN_c00d0800 @c00d0800` = `(obj+0x1c != 0) || (obj+0x1d != 0)`,obj = 體動偵測器 singleton **`0xc31cc42c`**（`FUN_c00d06a8`,字串 `src/library/BodyMotionDitector`;旗標由陀螺 thread `FUN_c00d0738` 從 `DAT_c074a070/74/78` 寫）。
- **完全不讀 `saf_jdat`/peak/評價值,不重掃。靜止時每輪回 0。**

**state==6 誰設**:就是 `FUN_c028c620` 自己(case 0 @86452、case 1 @86478),**當 `cVar2 != 0`(偵測到體動)時** → `*param_1 = 6`,並 arm Rocking 策略 singleton:`FUN_c026e940(0xc32068b4)`、`_DAT_c33d520c = 0xc32068b4`(route 0xE,per-frame 派發器 `FUN_c0259d50`）。
→ **state 6 = 「用 Rocking 連續伺服」,由體動觸發**;進 servo 後才用 v25/v26 的 `peak/128+70` 門檻做收斂判定(不是再取得的觸發)。

**c028c620 依 cVar2 分支**:case0/1(取得中)`cVar2!=0`→state 6 + Rocking;case4(驅動中)`cVar2!=0`→`FUN_c035fee8();*param_1=0`(中止重來);case6(伺服)收斂(回 3)後 `cVar2==0`→state1、`!=0`→state0。

**⚠️ 關鍵限制 / 自建 AF 的可乘之機(★Q3 修正:原「全盲」太強)**:陀螺體動只 gate **Rocking 伺服**這一條;**「重對焦」本身不是陀螺 gate 的**。靜態機位下 fp 仍會重對焦:①正常驅動迴圈自己 re-cycle;②**漂移監視器 `M=0xc33d1958`(`FUN_c028a360`,CAF state-0 查詢,回 0=重驅)** 在對比/場景謂詞觸發。路徑選擇 `sel=(scene+0x5c==4‖area0.count==0)?scene+0x5c:3`;sel∈{3,4}→BOX 路徑、{0,1,2,5}→LUMA+TIMER 路徑(scene 0x5c/0x58 由 AF-area-mode `afctx+0x1cc` 定)。**五觸發(確切門檻)**:
- **#1 框 SIZE 變**(`FUN_c028ab20`,★不是平移):`dW%=|refW−curW|·100/curW`、dH% 同,`>thr` 重驅,thr=**2%(subj_sel==3 緊)/10%**。語意=主體視角大小變=深度變=重對焦。
- **#2 框邊 in/out**(`FUN_c028ac80`,純符號無門檻):任一邊向外移。
- **#3 mode-group 變**:`scene+0x58 != M+0x208`(group 0 單點/1 MF/3 追蹤/5 全域)。
- **#4a luma-grid**(`FUN_c0289e78`,16×16 grid 在 **`M+0x0`**,來源 AE buffer `0xc3201b14+4`):每格模糊-luma `match%`;hold 需 `avg≥82 且 min≥70 且 M+0x218==0`。
- **#4b 偵測區清單**(僅 sel==5):`M+0x220` 256×16B 矩形逐個 exact-equal,任一差→重驅。
- **#5 逾時/漂移**:`elapsed=VD_tick−M+0x21c ≤ 307(0x133) 且 M+0x20c(AF-eval 漂移%)≤12`;307 tick≈**5.1s@60fps/10.2s@30fps**(VD 率 runtime)。
- **#6 體動**:`M+0x218`(驅動/大主體移動)→BOX 無條件重驅;`0xc3404678+1`(陀螺)→luma 門檻→100/100、漂移→−1(極易重驅)。
- **#7 重驅**:state 0→1→2 對比重掃;移動主體位元設→state 6 預測追蹤。
→ **主體被 AAT 追到使框變/偵測 rect 變 → 普通重對焦,不盲。** 真窄縫隙 = **置中、未偵測、純沿景深移動且框大小不變**的主體 → 只剩 #5 計時兜底(5–10s)。**外接 AI 切入點是這個窄 case。standalone 可直接復刻:#3/#4a/#5/#6(無需主體框);#1/#2/#4b 需主體偵測餵框。**
- **★ AAT 色彩追蹤如何驅動對焦(Q1,HIGH)**:`FUN_c0275e60` 建 area0,三互斥分支選一(優先序):①主臉`ctx+0xe8==1` ②可選臉/眼`==2` ③**AAT `FUN_c02761c8`**(條件:**無臉/眼 且 AF-C 伺服 `param_2+0x20c8∈{4,8}` 且 AAT 啟用 `ctx+0x1cc==3`**)。AAT 分支走 `FUN_c02763c0(param_6=1)`=**2.5×W/1.5×H reshape**,寫 `[L,T,R,B]@area0+0x1014`+`count@area0+4` → 正是漂移監視器 #1/#2 讀的。**閉環:AAT 主體視角大小變(深度變)→ 框 size 變 → #1 觸發重對焦 = AAT 對對焦的作用。** AAT 結果 buffer `0xc3033e00{x,y,w,h}`,採用需**品質閘 `0xc3033e26>19`(confidence lock;<20 不鎖不採,對上 FACE_EYE §④)**。**臉/眼絕對優先**(在框時 AAT 脫鉤)。AAT tracker 每 LV 幀跑(`FUN_c05abec8`),閘:`FUN_c0423e48()==3`(LV streaming)且 `FUN_c05ad648()==0`(臉模組非偵測態)。→ 復刻需三件:漂移監視器接重驅、AAT 框餵 area0(含品質閘+reshape)、條件 gate(無臉+AAT+AF-C)。

| 項目 | 位址 |
|---|---|
| 序列器 | `FUN_c028c620 @c028c620` |
| vtbl+0x180 覆寫(體動謂詞) | `FUN_c02a42f8 @c02a42f8`;vtable `0xc092b8d0`;物件 `0xc3404678` |
| 基類 v94(return 0) | `0xc029b9e8` |
| 體動偵測 | `FUN_c00d0800 @c00d0800`;singleton `0xc31cc42c`;thread `FUN_c00d0738` |
| state6 / Rocking | 設定 @blk_c02.c:86452/86478;Rocking ctor `FUN_c026e940`,singleton `0xc32068b4`,route 0xE |

═══════════════════════════════════════════════════════════════
## ⑨ 驅動/對焦框/PTP 補充四題(復刻實作端問，反編譯確認)
═══════════════════════════════════════════════════════════════
**Q12 — 合焦判定:N = 3 連續小離焦幀。** 信心 HIGH。
`CafPdDriveMain @c024a230 → CafMode5_CheckPdaf @c02804c8`（per-area PDAF 狀態機，peak = state **6**）。常數 `{200,150,20,100,2,30}`（`FUN_c0298038`）。`iVar5=*(param_3+0x18)`=defocus→pulse scale（per-lens/runtime），`local_64`=|defocus|：
- 小離焦門檻：`|defocus| < 200·scale`。
- 極小+可靠（`≤150·scale`）：counter 直接設 3 → **一幀確認 state 6**（合焦即停）。
- 中等（150–200·scale）：每幀 counter+1，到 **3** → state 6。→ **N = 3**（門檻 `local_2c=2`）。
counter 在 per-area struct `+0x50`（word0），state `+0x60`（word4）。可靠度閘 `FUN_c0285378`。另有 keep-driving 遲滯 `CafMode5_JudgeDrive @c0280970`（counter `+0x34`，常數 `{3,2,10,1}`）。

**Q15 — AF 對焦框尺寸（兩族，正規化 1024×682 工作空間）。** 信心 HIGH（尺寸/空間/aspect）、MEDIUM（S/M/L 對應）。
尺寸表 ROM **`0xc073b034`**（列 `[modeKey, sizeKey, w, h]`，stride 0x10），選擇器 `FUN_c008e8c8`；工作空間 `{1024,682}` @`0xc073b0a4`。
- **單點框(正方)**:**32×32 / 64×64 / 128×128**。
- **區域框(長寬比 ≈1.630:1,非正方非 3:2)**:**119×73 / 357×219 / 595×365 / 833×511**;裁切變體 833×365(`0xc073b024`)、595×511(`0xc073b02c`)依 aspect 選 → **框帶長寬比**。
框存 FocusArea rect `+0xc8..0xd4`(幀 dims `+0xc0/c4`),`FUN_c0021c40` 取物件(`*(this+0x5c)`);同一 `+0xc8` 框既是 CDAF 評價區、又經 `FUN_c0686040`(per-axis `out=in·dst/src`)seed AAT SetTarget(`FUN_c05ac248`)。menu `MenuItem_eXC_MenuFocusAreaSize::v2 @c0080458`,enum `eXC_MenuFocusAreaSize`。

**Q17 — PTP `0x9401 GIMBAL_OpenApplication` 有資料相位(YES,data-in)。** 信心 HIGH。
分類器 `FUN_c04e4a60`(switch @c04e4ac0)把 **0x9401 路由到 GET/data-in**(`FUN_c04e4868`);只有 **0x9402–0x9405 是 no-data**(EXE,`FUN_c04e4a30`)。「0x9401–0x9405 全 no-data」是誤讀。handler `c04eecc8` 建 ~79-byte identity IFD(版本/序號/vtable/float,serializer `FUN_c0500f58`),存進輸出描述子 `param_4[1]`;egress `FUN_c04e4868` 設 **container type=2(DATA)**、寫 12-byte PTP header、USB bulk-in 傳出。→ host 讀的 79 bytes 是真 PTP 資料相位。

**Q18 — `AfMgrDriveScan @c0238a28` 掃描評價 = 每個 sensor 幀。** 信心 HIGH(事件/節奏)、MEDIUM(絕對 ms)。
3-tap 移位暫存器(`v6 @c0238b78`:`[0x1d]=[0x1c];[0x1c]=[0x1b];[0x1b]=*p`)每掃描步進一次。鏈:AF 執行緒 `FUN_c028c620`(阻塞於 AfMgr 事件旗標 `0xc33d51c8` bit0)→ 每幀喚醒 → `FUN_c0259d50` → `AfMgrProcessFast::v7 @c025e170` → **`FUN_c0263e60` 每幀一次** + 移位一格。喚醒源 = **sensor Vd 幀中斷 IRQ 0x79**(`FUN_c0125478`,綁 `FUN_c0016a7c(0x79,…)`,pri 0x37)經 scheduler 派發。幀 divisor 表 `0xc090f0ac`(still)/`0xc090f2ec`(movie)是 **9 observer × 7 scheduler-mode × {divisor,phase}** 的 2-D 排程表(每 observer 0x40 bytes),**不是**平坦 1/2/6 表。CAF=**observer slot 0 `AfContinuousObserver`**(vtable `0xc09185a4`,notify `AfContinuousObserver::v1 @c022c7e8`),divisor 由 **CameraMgrScheduler mode(schedObj+4,0–6)** 選,非 AF 粗/精子態。obs0 divisor by mode=`{0,1,0,1,2,6,0}`;**mode5(div-6)Ver.5.02 從不設定 → 可達 CAF divisor 只有 1 和 2**。mode 1/3→**div-1(每 Vd)**、mode 4→**div-2(每 2 Vd)**,mode 由 readout 決定:`FUN_c039dde8/f8c8` 中 `readout(+0x14)==9||10 → mode4 → div-2`,否則 mode3 → div-1。近峰減速與粗掃**同一 observer 同 divisor**。設計為**常數牆鐘**(divisor 隨 readout 率成比例,tick 維持~固定)。dispatch `FUN_c0207620`,registrar `FUN_c02072b8`(常數 `idx*0x40−0x3f6f0f54` 故 ROM 無字面位址),still/movie 選 `FUN_c0126010`。**單次 AF=slot 1(vtable `DAT_c0918564`)。**

═══════════════════════════════════════════════════════════════
## ⑩ YLevel 網格 / 低對比 flag / 粗掃 waypoint / lensScale（Q6–Q9）
═══════════════════════════════════════════════════════════════
**Q7 — YLevel 測光網格 = 16×16 = 256 區,等分。** 信心 HIGH。
網格程式器 `FUN_c0320370`,**所有呼叫端都傳 `0x10,0x10`**(16×16);測光區 = 中央 **60%×60%**(pct=0x3c)。per-cell 讀取 `FUN_c024f608` loop `0x100`。
- 每格 = **固定等分、置中**:`cellW=((regionW·pct/100)+cols/2)/cols`、cellH 同(取偶)。像素尺寸隨 aspect/crop(regionW:regionH 跟 sensor readout),但**格數/等分固定**。
- 模式:aveq=中央 **8×8**(row/col 4..11)、ave4=中央 **2×2**(7..8)、center-weight `FUN_c0211098`、full-avg `FUN_c0210e80`。
- HW `FUN_c0126a58` 寫 **`0x30058000`**:`_DAT_30058014=(cols-1)|(rows-1)<<16`、`_DAT_30058018=cellW|cellH<<16`、`_DAT_3005801c=0x20002`(2×2 子採樣);cols/rows≤32。descriptor byte0=cols/byte1=rows/+4=Y平面;sw ptr `DAT_c2f1e2c0`。主測光 `FUN_c020a3c0`→descriptor `FUN_c0311740`→平均 `FUN_c0210d88`。
- 臉區 AF(§⑥)按臉框覆蓋比加權混合此網格(覆蓋比 `boxArea·0x1000/frameArea`,權表 `@0xC0911580`)。

**Q8 — 「低對比」flag ⚠️ 實為「時間變化率」+ 低光,非空間對比。** 信心 HIGH。
`GetCafLowconByYLevelFlg` 是 **CSV 除錯欄名字串**,flag 由 `FUN_c024f708`(→`DAT_c2f185a0`)算,讀整張 16×16(`FUN_c024f608`):
- `meanY=(ΣY)>>8`(亮度權重,`_DAT_c33cff68`);**`diff_rate = Σ max(0, |Y_t−Y_{t-1}| − refBright/100)`**(`_DAT_c33cff64`;前幀 Y @`0xC33CFF6C` 256×u32;refBright=`FUN_c030c8a8` runtime AGC)。
- **比的是 diff_rate(時間變化),非空間對比/均值**。3 個亮度縮放門檻:`T1=clamp(meanY/100·2+80,[60,1000])`、`T2=clamp(meanY/100·8+{380|800},[200,6000])`、`T3=clamp(meanY/100·{15|20}+{1500|3200},[2000,13000])`({..}=infinity-search flag)。分類 `DAT_c2f185a0∈{1,3,5}`(`<T1`hold/`>T3`→5/`>T2`→3/else 1),5 幀遲滯。硬低光閘 per-area YLevel `≤0x1e(30)`(`FUN_c0299108`)、`<100`、`≤100`。
- ⟹ **靜態白牆/天空的「空間平坦」不靠這個 flag 剔**(白牆非低光;靜態→diff<T1→hold);空間低對比剔除在 **CDAF 峰值 `saf_jdat`** 本身(太低=低對比,靠 §②/`v26` 的 `peak/128+70` +70 地板)。實務兩道並用。

**Q6 — 粗掃 waypoint 數 `DAT_c2f172d4` = 動態,上限 30;28mm = 30(index 29)。** 信心 HIGH。
`FUN_c020d0d0`:從 near 以 step **0x155=341**(position 域)逐步到 far,`for(n=1;n<0x1e;n++)`,waypoint 陣列 `@0xC32020E4/E8`;尾段 gap<0xAB(171) 併最後兩點 n−1;`DAT_c2f172d4=clamp(count,1,30)`。`FUN_c020d320` 設 `*(this+0x6c)=DAT_c2f172d4−1`。**28mm(near 3168/far 14296,span 11128)→ 飽和 30 → index 29**。**★ 更正(前註「粗掃跑完整條才判越峰、minPeakIndex 用 29」是誤歸屬)**:粗掃**不是**掃到底 —— 越峰早退在別的函式。`minPeakIndex=29` **只** gate `FUN_c0263e60` 的 **mode==2(over-peak/翻越邊界)分類**(`mode2 && peakIdx<29→拒插值`;因 29=count−1 故 mode2 永遠拒 = 「掃到遠端仍升=邊界」終止),**不在 sweep/越峰路徑讀**。真正的每幀越峰是 `FUN_c0263078`(見下 ⑥ 修正)。復刻:**越峰用對比地板不用索引;29 只屬 mode-2 邊界分類器**。

**Q9 — `lensScale`(CalcCafDriveSpeed `+0x98`)= `_DAT_c33c80e8`,實際**恆等於 60(★更正:非「16 純猜」、也非「~16–60 隨幀率」)。** 信心 HIGH。經 `min(60, FUN_c035fda8(band))`,而 fda8(band)對任何 fp 幀率都 ≥308 ≫ 60 → **pin 在 60**。詳見上方 ⑨ 驅動段完整算式。
- **身分鎖定**:`desc+0x98 = *(0xc33c80c4+0x24) = *(0xc33c80e8) = _DAT_c33c80e8`(caller `FUN_c0245ef0(...,&DAT_c33c80c4)` → `FUN_c0247910` param_3=0xc33c80c4,算式精確)。**不是**靜態 16、也不是隨機。
- **值來源**:`_DAT_c33c80e8 = min(FUN_c035fec8(0)/10=60, FUN_c023c9b8)`,`FUN_c023c9b8` 依**幀/曝光週期 µs**(`FUN_c0125ca8`=H-total×V-total×1000/72000)選帶 `9/15/18/21/22 ms` → `8333/…/33333` → `FUN_c035fda8`(x/(1e6/K1),28mm K1=37000→x/27)→ **min(60,·)**。fda8 逐帶 308…1234,全 ≫60。
- **結論:恆 60**。任何 fp 幀率 fda8 輸出都 ≥308,min 永遠取 60。復刻直接 `lensScale=60`,不必逐 fps 算、不必實測。(舊「16 純猜/隨電壓變/~16–60」皆誤。)

> 相關:AUTOFOCUS.md、AF_DESIGN_REFERENCE.md、AF_COMPLETE.md、FOCUS_DISTANCE_PRINCIPLE.md、LENS_CALIBRATION.md、PTP_READ_USER_EXPOSURE.md、FACE_EYE_AF.md、GIMBAL_MANUAL.md。
