# SIGMA fp — DistConverter 畸變校正的內插數學(反編譯還原)

核心函式:`FUN_c05ba6c8` @ `0xC05BA6C8`(在 `out/decomp/full/blk_c05.c:141449`)。
輔助(已反組譯確認):`FUN_c01f69a4=sqrt`(`vsqrt.f64`)、`FUN_c01f77d0=atan`、
`FUN_c067e480=cos`、`FUN_c01f69b8=sin`。

## 模型:徑向(rotationally-symmetric)畸變,保角、只重映射半徑

輸入 `param_2=(x,y)` 像素、`param_3=(W,H)` 影像尺寸;輸出 `param_1=(x',y')` 校正後像素。

### 步驟
1. **相對光學中心的位移**:`dx = x − W/2`,`dy = y − H/2`。
2. **半徑與正規化**:
   ```
   r      = sqrt(dx² + dy²)                     # 到中心距離
   r_max  = sqrt((W/2)² + (H/2)²)               # 到角落距離 = 正規化基準
   ρ      = r / r_max   ∈ [0,1]                 # 「相對像高」rilative image height
   ```
3. **支撐點軸(uniform,17 點)**:`ρ_out[k] = k/16`,k = 0..16(常數 `DAT_c05baa2c = 0.0625 = 1/16`)。
   查表值 `S[k]`(distorted 半徑)= `table[k] (uint16) × k × (1/16) × (1/32768)`
   (`DAT_c05baa34 = 1/32768 = 2⁻¹⁵` → 表是 **Q15 定點**)。
   → 支撐點把「均勻的校正後半徑 ρ_out=k/16」對應到「非均勻的原始(畸變)半徑 S[k]」。
4. **找區間 + 分段線性內插**(loop k=1..15,找第一個 `ρ < S[k+1]` 的 k):
   ```
   ρ' = ρ_out[k] − ( (ρ_out[k] − ρ_out[k−1]) × (S[k+1] − ρ) ) / ( S[k+1] − S[k] )
      = (k/16)   − ( (1/16)               × (S[k+1] − ρ) ) / ( S[k+1] − S[k] )
   ```
   **純分段線性(piecewise-linear)內插**——不是多項式、不是樣條。(反編譯 blk_c05.c:141619)
   保護:若相鄰支撐點量化後相同(`S[k+1]==S[k]`)則跳過內插,避免除零/平段。
   超出最後支撐點:走 clamp 分支(dVar12 起始 = `DAT_c05baa3c = 0.0`)。
5. **重建像素(保角)**:
   ```
   θ  = atan(dy / dx)
   x' = W/2 + ρ' · r_max · cos(θ)
   y' = H/2 + ρ' · r_max · sin(θ)
   ```
   三分支處理象限:`x>cx`(cos 正)、`x<cx`(cos ×−1)、`x==cx`(純垂直,只用 sin)。
   末端再做一次整數格鄰點取樣(`auStack` 小網格,`+0.5` 四捨五入 → 定點回整)= 次像素落地。
   定點縮放:`DAT_c05baa44=32768=2¹⁵`、`DAT_c05baa4c=65536=2¹⁶`。

## 係數來源:執行期,不在韌體

支撐點表 `DAT_c2f2d87a`(17×uint16)位於 `0xC2F2D87A` — **超出 seg0 尾端 `0xC2EF6E00`**,
即 `.bss`/RAM 區,**開機時從鏡頭 ROM 下載**(`DownloadLensData`)後填入。
→ 韌體只有**內插引擎**(本函式),真實畸變係數逐鏡頭、在鏡頭裡。

## 外層維度:同樣手法的 3D 支撐點網格

上面那張 17 點徑向表,本身是從三維網格挑/內插出來的(見 lens data dumper `blk_c03.c:36090+`):
```
total_number_image_height  ×  total_number_distance  ×  total_number_focal_length
```
- **image_height** 軸:上述 17 點(meridional/sagittal 兩套)。
- **distance** 軸:`distance Supporting-points`(對焦距離支撐點)。
- **focal_length** 軸:`Focal-length Supporting-points`(變焦鏡才有多點)。
- 每格存 `lower/upper limit`(容差帶,對應 `chief/upper/lower`)。
- 先依「當下對焦距離 + 當下焦距」在 distance/focal_length 軸做內插(同為分段線性),
  得到當前的 17 點徑向表,再跑上面步驟 4/5 的逐像素徑向校正。

## SIGMA 的「house style」= 分段線性 over 支撐點 + 定點

整個光學/距離校正都是這套:
- **不用解析公式、不用高階多項式**,而是**校正取樣點(knot)+ 分段線性內插**。
- **用取樣點的疏密控制精度**:畸變表把「輸出半徑」取均勻(k/16)、把「輸入半徑」存成非均勻查表值;
  距離表則把支撐點取非均勻(近攝密、遠景疏)以吃掉 1/距離 的非線性。
- 全程 **Q15/Q16 定點**(無浮點依賴的部分),可攜、快。

## 對「做自己的 AF / 距離估算」的直接啟示
1. **mpos↔distance 也是這套**(`convert_mpos2distance` + `distance Supporting-points`):
   建**非均勻支撐點 LUT + 分段線性內插**即可,別套單一比例或多項式。
2. 支撐點放在**屈光度(1/距離)均勻**、或**近攝密遠景疏**,精度/記憶體最划算。
3. 變焦鏡務必上 **2D(focal_length × mpos)**。
4. 需要的話用 **Q15 定點**就夠,不必浮點。
5. 分段線性的最大好處:**單調、無 overshoot、易標定**——比樣條/多項式更適合硬體即時對焦回路。

## 信心
- 徑向模型、正規化像高、17 點均勻支撐點、**分段線性內插**、atan/sin/cos 重建、Q15 定點
  —— **反編譯 + 反組譯確認**。
- 係數來自鏡頭 ROM(位址超出 seg0)—— **確認**。
- 外層 distance/focal_length 軸「同為分段線性」—— **強推論**(同一資料結構與 house style;
  dumper 證實網格與支撐點存在,逐軸內插器未逐行反編譯)。
