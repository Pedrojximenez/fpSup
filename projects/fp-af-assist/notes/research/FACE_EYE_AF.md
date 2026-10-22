# SIGMA fp — 人臉 / 眼睛 / 主體追蹤 AF 完整反編譯

給復刻臉/眼 AF 用。fp Ver.5.02。位址 base 0xC0000000,decomp `out/decomp/full/blk_c0X.c`(偵測/追蹤在 blk_c05,AF 整合在 blk_c02)。信心逐節標。
相關:`AF_AE_INTERNALS.md`(AF/AE 內核)、`AF_COMPLETE.md`。

═══════════════════════════════════════════════════════════════
## 總覽:三段式管線
═══════════════════════════════════════════════════════════════
```
[偵測] 硬體ISP臉框 + CPU眼landmark  →  [選擇] 加權評分選主體  →  [追蹤] 色彩AAT跨幀鎖定
                                                        ↓
                        [座標] 偵測框 → AF評價區 xs/xe/ys/ye  →  [CDAF] YLevel爬山
```
**核心分工**:偵測「哪裡有臉/眼」是**不透明硬體 ISP**(不可移植);「選誰對焦 / 座標轉換 / 追蹤 / CDAF」全部可復刻。你自己的系統把臉框換成你的偵測器,後半照抄即可。

═══════════════════════════════════════════════════════════════
## ① 偵測引擎 — 信心:高
═══════════════════════════════════════════════════════════════

**臉偵測 = 硬體/ISP 驅動**(不是 CPU 演算法、不是 CPU 神經網路):
- `FaceAndEyeDetection::v2 @FUN_c05aa190`(vtable 0xC2DFAB44 slot 0x10):取 ISP 縮圖平面(`FUN_c0436f28(desc,0x20)`)→ 把偵測 ROI 寫進成像驅動暫存器 **`+0x82C=(xStart<<16)|yStart`、`+0x830=(xEnd<<16)|yEnd`** → ISP **非同步**產出結果緩衝,軟體只解析。內部演算法 = 不透明矽晶片。
- 偵測區預設 `@0xC2DFC540` = **臉 640×480、眼 320×240**。輸入上限 `pixels·4 ≤ 0x15400`。

**眼偵測 = CPU / 函式庫**(可參考):
- 自己一條執行緒 `XC_EyeThreadHandler → FUN_c05adb08`;執行器 `FUN_c05add48` 對選定臉做 320×240 crop → landmark 偵測器 `FUN_c05b9a68 → FUN_c05b9be8` 吐 **12 個特徵點 + 各點信心**(結果 0xA4 bytes:+0x00..0x5F=12點 x,y、+0x60..0x8F=12信心)。按需執行(非每幀),`FUN_c05adfb8` 轉成兩眼框。

**觸發節奏**:`Detections::v2 @FUN_c05a8ea8`,由 LiveView/CAF loop 驅動,`FUN_c05a9650` 節流到 **~1/3 幀**(對應 `FACECYC`)。
**工作記憶體**:`FD_WORK` 0x38400 @0xC37CD754(臉/眼)、`AAT_WORK` 0x25800 @0xC37CD3A0(追蹤)。
**⚠️ 更正**:`DETECTABLE/UNDETECTABLE/DETECTING` 是**防閃爍(50/60Hz)**狀態字串(ROM 緊鄰 "60Hz"),與臉偵測無關。

**狀態機**(結果管理器 `FUN_c05a9e10` 單例 @0xC37CCA9C):臉模組狀態 `+0x334`；`+0x3D0` 是 AAT 狀態（setter `C05AC5C0`），不是先前標示的眼狀態。不要把不同 setter 的值域混用。2026-09-27 更正依據見 [native 輸入稽核](../geometry/NATIVE_INPUT_AUDIT.md)。

═══════════════════════════════════════════════════════════════
## ② 結果資料結構 — 信心:高
═══════════════════════════════════════════════════════════════

**原始 ISP record**(解析器 `FUN_c05aaff8` 輸入,每筆 **0x20 bytes**):+0x08 中心X、+0x0C 中心Y、+0x10 size(方形邊長 px)、+0x14 score(`<4` 或 `==0x80000000` 無效)、**+0x18 角度(16-bit,支援 360° 臉)**、+0x1C tracking ID。

**解析後**(最多 **5 張臉**,每張 = **0x9C group = 3×0x34 = [臉框 | 眼A | 眼B]**,base 結果管理器 +0x10 stride 0x9C)。face 子記錄:+0x10 X(左上)、+0x14 Y、+0x18 W、+0x1C H(方形,W=H=原始 size)、+0x20 原生角度 u16、**+0x24 tracking ID u32**、+0x28 score u32、+0x2C 原始 size u32、+0x30 valid(byte)。先前 group+0x34 tracking ID 標示有誤：`C05AAFF8` 寫入 manager+0x34，即 group+0x24；group+0x34 不可當 ID。依據 `blk_c05.c:131621–131639` 及 ROM ARM。

**座標系**:`FUN_c05a9af0`(scaler `FUN_c05bac90`)依 mode 選 reference，且有略過轉換分支。face parser 的此次呼叫轉換 group+0/+4，但直接複製原始 size 到 +8/+C/+18/+1C/+2C；不能將整個 tuple 無條件視為 320×213，或直接用 size/320 當物理尺度。需連同 readout/reference/crop 驗證。感光元件像素轉換在 AF 端(見 ⑤)。

═══════════════════════════════════════════════════════════════
## ③ 選臉 / 選眼優先權 — 信心:高(★ 精華,可直接照抄)
═══════════════════════════════════════════════════════════════

多臉 → 加權評分排序取 top-5,index 0 = 主目標。
先 gate:`FUN_c05aaa38` 剔除不與 AF 區重疊的臉(4 角 point-in-region),並套長寬比修正表 `@0xC2DFC330`(ID1-8→4:3,3:2,16:9,1:1,21:9,7:6,1.248,√2)。

**★ 評分函式 `FUN_c05aad68`**:
```
score = size²·2·W1  −  (dx_ref² + dy_ref²)·W2  −  distToPrev²·W3  −  (size−prevSize)²·2·W4 ,  >>8
權重 @0xC2DFCF60 = W1=512, W2=256, W3=128, W4=64
```
- **W1=512**:臉越大分越高。**W2=256**:越靠近「參考點」(= 使用者 AF 框位置 `ref+0x14/+0x18`)越高。**W3=128**:越靠近前幀目標越高(連續性)。**W4=64**:大小越穩越高。
- 綜合:**偏好大臉、靠近使用者 AF 點、與前幀連續、大小穩定**。排序 `FUN_c067c4e0` 降序。

**眼睛左右優先**:選定臉後 `FUN_c05aa7b8 → FUN_c05ad9b0(engine, whichEye, faceId)`(whichEye 0/1),依眼結果有效性 + 設定旗標(`obj+4`)挑。眼找不到 → 用臉框(眼子記錄保持 0)。Auto vs Manual 眼模式來自偵測模式設定(`FUN_c03a0410` 旗標,+0x12 眼致能、+0xd fallback 翻轉)。選單 `CM_FaceDetectionAF`,`FaceEyeAuto` vs `FaceOnly`,setter `SetFaceDetectMode`。

═══════════════════════════════════════════════════════════════
## ④ 主體追蹤(AAT = AutoTracking)— 信心:高
═══════════════════════════════════════════════════════════════

**出貨機只跑「色彩」後端**(直方圖後端編進去但 `DAT_c37cd364=0` 關掉,全 image 無寫入點)。三層:`AutoTracking` 門面 → `XC_AutoTrackingThreadHandler`(每幀一步)→ `AatInterfaceColorTracking`(色彩,預設)/ `AatInterfaceHistTracking`(直方圖,停用)。
後端 dispatch `FUN_c05ab650`;vtable:v1 SetTarget、v2 Track、v3 Reset、v4 GetResult。thread 單例 0xc37cd704,per-frame entry `FUN_c05abec8`。指令 0=STOP/1=RUN/2=START。

### 色彩後端(預設)`FUN_c05b6ba0`(init)/`c05b6cf8`(track)/`c05b7458`(result)

> 2026-09-27 幾何用途更正：AAT 框是自適應色彩命中點與搜尋窗處理的結果，框大小變化本身不證明深度變化；下文「回歸約 60≈目標」不能當物理尺度校準。`C05B7D98` 直接確認 `+0x0C` 為 hits 映射信心，`+0x0D` 為半軸面積比例，不是前景命中密度。機內幾何需先合焦建立基準，並另驗尺度語意，見 [融合規劃](FP_GEOMETRY_DFD_FUSION_2026-09-27.md)。
model 單例 base `_DAT_c37cdfa8`(0x2c bytes),像素 YCbCr 4:4:4,色度中心 128。
model 圖:+4/+6 半軸[10,299]·+0xc 信心0–100·+0xd 半軸面積比例·+0x12 參考sat·+0x14/15/16 參考Y/Cb/Cr(=`_DAT_c37cdfbc`)·+0x18/19/1a snapshot·+0x20/21/22 候選Y/Cb/Cr·+0x24 候選bin數·+0x26 Δhue·+0x28 Δsat·+0x29 ΔY·+0x2a 複合偏移D。
- **模型 = 單一自適應參考色**(非保留直方圖)。init:32×32 Cb–Cr 直方圖(~1600 取樣)找主色(門檻 bin count 19)→ 32-bin 亮度直方圖 → 參考色 (Y,Cb,Cr)。

**每幀定位 = 逐像素色距分類**(`FUN_c05b1168`,1600 取樣、加寬 3600),**命中 = `color_cost + spatial_penalty < 0x400`**:
```
color_cost = ( normY·|ΔY|·w_Y + normC·|Δ色度|·w_c + hue項·w_hue ) >>8       // 權重和 256
  normY = (0x400 + tolY/2)/tolY ,  normC = (0x400 + tolC/2)/tolC             // 各項先正規化到 ~0–1024
  |Δ色度| = | max(|ΔCb|,|ΔCr|)_pixel − 參考sat |
```
- **三權重(依飽和度每目標算,`FUN_c05b3298`,非固定常數)**:`ref_mag = max(|Cb−128|,|Cr−128|)` →
  `w_hue = 0(mag<8) | (mag−8)·179/16(8–24) | 179(≥24)`;`w_c = ceil((256−w_hue)/2)`;`w_Y = floor((256−w_hue)/2)`。
  例:飽和(≥24)→ hue179/c39/Y38;mag16→89/84/83;近灰(<8)→ hue0/c128/Y128。飽和色 hue 佔 ~70%,灰色 hue 消失。
- **命中前有三道硬閘(capstone 逐分支確認,`FUN_c05b1168`)—— 真正 gate 是後兩道,與容差無關**:
  1. **Gate 1 容差**(c05b1890):`|pix_mag−ref_mag| > tolC` 或 `|ΔY| > tolY` → 硬 reject。
  2. **Gate 2 灰/彩 XOR**(c05b18b0):`(ref_mag>8) XOR (pix_mag>8)` → 硬 reject。**⟹ 彩色目標下,灰/低飽和背景像素在此被完全剔除(不是拿罰分)**。
  3. **Gate 3 hue 楔形方向**(c05b1924,ref chroma mag≥9 才建,半角 θ `_DAT_c37cdf74` 預設 35°=`_DAT_c37cdf7a`=0x23,tan via ROM 3.1415/180/1024):**彩色像素方向落楔形外 → 硬 reject**;內部取投影 Chebyshev 距離×正規化 = hue項(0..1024,楔緣≈1024)。
  過三閘才算 color_cost。`hue項=1024`(c05b1a40)**只在「灰色 model(ref_mag≤8)」才走到** —— 彩色 model 的灰像素早在 Gate 2 被剔。⚠️ 舊筆記「任一 mag<9→hue項=1024 罰分」是**誤讀**,正解:灰像素對彩色目標=硬 reject。這就是為何 6× 容差掃描命中數只差 0.07%(gate 靠 Gate2/3 二值硬 reject,非軟容差),也是「對彩色主體才收斂、對均勻牆發散」的機制根源。
- **容差 tolY=`_DAT_c37cdf72` / tolC=`_DAT_c37cdf70`(per-target,每幀重算 `FUN_c05b2f68`,由 ref sat 驅動)**:fallback(命中<7 且 chroma>8)=**tolC 64 / tolY 128**;相位備援 **50/45** 或 **30/25**。量級 25–128 → norm 倍率 8–41,夠緊不會全命中。⚠️ 容差過鬆 → cost 封頂 1024 = 門檻 → 什麼都命中(見下發散陷阱)。
- **空間罰**(`FUN_c05b1168`):距離**對半軸正規化,非絕對格**:`d=max(|Δx|,|Δy|); d=(d·1024+semi/2)/semi`(1024=一個半軸)。罰 = 3 段分段線性(取三線中位數):
  斜率 `FUN_c05b3520` = **常數 32(=0.25),與 D/semi 無關**;折點 `FUN_c05b35b8`(interp2clamp `FUN_c05b2ee0`):
  `x0 = interp({0,255,inner0,614},D)`,`inner0 = interp({25,72,614,307},semi)`;`x2 = interp({0,255,inner2,1024},D)`,`inner2 = interp({25,72,1024,614},semi)` → **x0∈[307,614]、x2∈[614,1024]**(大框→小、大 D→大;例 semi48/D128 → 538/923)。off2=768。
  `penalty(d) = 0.25d (d≤x0) | 0.25d+768(d−x0)/(x2−x0) (x0≤d≤x2) | 0.25d+768 (d≥x2)`;命中 = `penalty(d)+color_cost < 1024`。
  🔴 **完美色像素(cost≈0)空間截止 = d≈1024 = 整個半軸**(尾段 0.25d+768=1024,對所有 semi/D 皆然)—— 折點只改中段斜率,**不動截止**。所以命中可延伸到滿半軸,**收斂靠「色彩 gate」不靠空間**。
- 🔴 **無「無特徵/低飽和」拒絕閘**(`FUN_c05b6ba0` setTarget 全路徑 + 每幀 adapt 都沒有):主色門檻 19 只擋取樣不足;均勻灰牆無 bin 過門檻時**靜默寫零候選→抓 `candidate[0]`（退化近零 chroma）→回成功**。無飽和下限/無密度(+0xd)閘/無對比檢查。→ **均勻低飽和區被接受 + 空間截止到 1.0 半軸 → 框無界脹大 = 韌體 intended 行為,非 bug**。真實有主色主體才收斂(主體 cost 低→命中、背景 cost 高→不命中,σ=主體大小 → 4.5σ 收斂到主體)。**若要比原廠 robust,可在 `FUN_c05b6858` 後自加閘:主導 chroma 幅值/參考飽和 model+0x12 低於門檻 或 候選數=0 → 拒絕 setTarget(5.02 沒有)。**

**框更新 = 命中像素質心 + 共變異數橢圓擬合**(`FUN_c05b1e28`):對**逆協方差(precision)矩陣**特徵分解 λ,**半軸 = 4.5·√λ_cov = 4.5·σ**(常數 9.0×0.5,VFP 立即數 `0xc05b2174`/`0xc05b1e3c`),寫 model +4(major,μ_min)/+6(minor)、+8 角度、夾限 **[10,299]**(`_DAT_c37cdf5e`)。命中<7 → early-return、框凍結。橢圓擬合本身**無 IIR 前後框平滑**。
- **★ 但每幀有負回饋正規化器 `FUN_c05b2dc0`(幀首,`FUN_c05afdf8`→它;防飽和/保持緊框的真正機制)**:對**上一幀框**套大小相依增益形成這幀搜尋窗:`gain=FUN_c05b43c8(axis, lostFlag); axis=(gain·axis)>>7; clamp[20,299]; aspect≤2.5:1`。ROM 增益表 `0xC2DFCCC8`(÷128):`axis 10→220(×1.72)、50→140(×1.09)、80→100(×0.78)、200→8(×0.06)`。**固定點 semi≈60(gain=128):小框長、大框狠壓 → 每幀均值回歸 ~60,框到不了 299 飽和。** 衝到 200 → 下幀 200×0.06=12→floor 20。命中<7 用恢復表 `0xC2DFCCBC`(長小框=重抓,大軸端 held ~1.09× 保持寬搜尋)。**floor 是 20 不是 10。** → 復刻若框飽和卡死(299 吸收態,`dW%≡0` 使漂移監視器 #1 恆不觸發),根因是**缺這個正規化器**:無增益回復力 → 框無界長到硬夾限。加它 → 框回歸 ~60 ≈ 目標、#1 可用。無「鎖定+飽和」專用重置(`FUN_c05b7f20` 只在 hits<7+兩軸299 時 widen 取樣 1600→3600);正規化器一個就夠。
- **色彩模型更新紀律 `FUN_c05b2910`(讓飽和可逆的次要機制,HIGH)**:①命中0→硬還原參考色(不學垃圾);②命中不穩(10 格歷史 `avg|Δhits|≥0x15` 且 hits<7)→凍 α 跳 blend;③`new=(prev·(128−α)+meas·α)>>7`,`α=interp{D:0→0x1a,256→0x80}`(小 D 幾乎不學=防漂移)。**★ measured 只用 `weight=max(0,128−cost)` 像素(門檻 128 ≫ 命中門檻 1024)→ 只有靠參考色的低 cost 像素更新模型,背景高 cost 貢獻 0 即使落在脹大框裡** → 色彩參考不被背景拖走 = 飽和可逆。復刻需連這個一起抄,否則框脹大時模型會被污染。
> 🔴 **發散陷阱(必讀)**:(1) **Ghidra 反編譯把第二個 sqrt(`FUN_c01f69a4` @0xc05b216c/21b8)藏進 CONCAT44**,C 面看起來像 `9.0/λ·0.5`(正比 variance,二次映射→指數爆);真值是 `9.0/√μ·0.5 = 4.5·√λ`。(2) 但 **4.5·√λ 在「整框均勻命中」下每幀爆 2.6×** —— 韌體不在均勻填滿下運作:**命中=主體本身(色彩+空間雙 gate),不是整框**;框長超過主體時命中仍落主體 → σ≈主體 → 4.5·σ 收斂到主體尺寸。**復刻若發散,根因八成是容差太鬆讓什麼都命中→退化均勻填滿→任何 k 都爆;先修容差+距離半軸正規化,再用 k=4.5。**

**鎖定 / 信心**(`FUN_c05b7d98`,輸入命中數 h):`h<7→0`;`7≤h<20 → (h−7)·80/13`(h7→0,h19→73);`20≤h<50 → (h−20)·20/30 + 80`(h20→80,h49→99);`h≥50→100`。19→20 有 73→80 跳階。**取樣加寬**(`FUN_c05b7f20`):命中<7 **且**兩半軸都飽和 299 → 下幀取樣 1600→3600。

**每幀自適應**:參考色 = 命中像素加權平均(權 `max(0,128−cost)` — 注意此門檻 128 比命中門檻 1024 嚴,追蹤容忍變化、更新只信最有把握證據)+ 時間混合 `new=(prev·(128−α)+cur·α)>>7`。
- **α 依「複合色彩偏移 D」(非信心!)**(`FUN_c05b2910`/D 由 `FUN_c05b3388`):`α = 0x1a + ((D·408)>>10) ∈ [0x1a,0x80]`;`D = (w_hue·f(|Δhue|) + w_c·f(|Δsat|) + w_Y·f(|ΔY|))>>8`,`f`=同一個 interp2clamp `FUN_c05b2ee0`(三通道各表,y0=0/y1=255,折點 x0=knee·8/10、x1=knee·12/10,knee 在 `FUN_c05b2f68`)。**色彩偏移大 → α 大 → 學得快**(追色變);色彩穩 → α≈0x1a 幾乎不學(防漂)。信心只當閘(零命中→硬拷貝、<7→snapshot),**不決定 α 值**。⚠️ D 在幀首算但讀的 Δ 當幀稍後才更新 → **α 落後一幀**。
- ⚠️ **2.5×/1.5× 重塑框 `FUN_c05c3d28` 是「輸出端」不是搜尋區**:只被 AAT 座標轉換(§⑤ `FUN_c02763c0` param_6=1)和對焦框顯示(blk_c04)呼叫,追蹤迴圈不碰。**每幀搜尋/取樣區 = 上面那個橢圓框本身**(半軸[10,299]),別把 2.5×/1.5× 當搜尋範圍(會「主體快移就丟」)。臉/眼走 `FUN_c0276288` 皆 param_6=0 → 不套此重塑。

### 直方圖後端(停用,備參)`FUN_c05b4a30`/`c05b4bf8`/`c05b4d88`
- YUYV 4:2:2,**Y/U/V 各 32 bin = 96 bin**(top-5-bit);**度量 = SSD `Σ(model−cand)²` + 空間罰 `dx²+dy²`**;**exhaustive 滑窗**(增量直方圖滑動);框大小固定;信心二值(SSD<2400→100 否則 0)。

### Tap 追蹤 / 輸出
- AAT 不讀 `SYS_TapCoordinate` —— tap 由上游 AF/CoordinateMgr 先轉成對焦區框(`FUN_c05ac248`:AF 焦點區 `FUN_c0021c40`+0xc8 → `FUN_c0686040` 縮放到 LV 像素),AAT 讀那框當初始目標(START 訊息 → v1 SetTarget 取模型)。
- 輸出:v4 GetResult → `{xs,xe,ys,ye,found}` → `DetectionResultMgr`(+0x3e0 xs/+0x3e4 ys/+0x3e8 w/+0x3ec h);AF 面向模式 `+0x3d0`:**1 追蹤/2 丟失續預測/3 停止**。丟失保持模式 2(靠 AF-C 撐)。

═══════════════════════════════════════════════════════════════
## ⑤ 座標管線:框 → AF 評價區 xs/xe/ys/ye — 信心:高
═══════════════════════════════════════════════════════════════

偵測輸出塊 `R = obj+0x278`(size 0x470,`FUN_c0014dac` 快照)。子記錄 stride 0x34,框 `{x,y,w,h}`@rec+0x10/14/18/1c,valid@rec+0x30。type 表 `DAT_c092011c={1,2,2}`:index0=臉(type1)、1&2=眼(type2)、AAT=type3。REF 表頭 `R+0x318`:+0x10/+0x14 = REF_det 寬/高(**當縮放除數**)。

**轉換 `FUN_c0276288`(臉/眼)/ `FUN_c02763c0`(AAT)**:給框 `{x,y,w,h}` + REF 表頭:
```
xs_pix = x'                  ys_pix = y'
xe_pix = x' + w              ye_pix = y' + h        (角 = 原點 + 尺寸)
param_5[0x808] = (ye−ys)·0x400 / REF_h              // 臉高 = 幀的 Q10 分數(用來按主體大小縮放運動門檻)
```
- **無明確乘法**:框以偵測參考單位攜帶 + REF_w/REF_h,像素縮放在消費端做(= 顯示路徑的 `REF_disp/REF_det` 比例),所以 AF 區實質是「正規化 + 參考尺寸」。
- **長寬比/裁切相依** `FUN_c06873e0`:偵測長寬比 `box_w·100/box_h` vs LV 目標 `REF_w·100/REF_h`,差 **>4%** → letterbox/pillarbox 再置中偏移(`param_3[i] += |Δ|>>1`)。LV 幾何來自 `FUN_c030cea0/c03151c0`(感光模式/長寬比/裁切鉤子)。
- **顯示交叉驗證**:`XC_DisplayFaceFrame*` 讀同一 `R`,`screen = det·(REF_disp/REF_det)` 純均勻縮放無偏移,證實 `R+0x318`=REF_det。

═══════════════════════════════════════════════════════════════
## ⑥ YLevelFaceCalculator — 信心:高
═══════════════════════════════════════════════════════════════
`YLevelFaceCalculatorTH`(evaluator `FUN_c02136f8`,全 disasm 0xC02136F8–7C8)**不新開 AF 區/視窗**,而是**用臉框內 YLevel + 網格聚合 YLevel 依覆蓋比加權混合,再乘亮度增益**。⚠️ **舊版三處錯:是三張表(非兩張)、兩表非互補(獨立)、in-box YLevel 不從網格取。** 正確算式:
```
cov  = round(boxArea·0x1000/frameArea),clamp 0x1000   [FUN_c022a2b8,struct @0xC32025C0:+4 fw/+8 fh/+0xC x0/+0x10 y0/+0x14 x1/+0x18 y1]
        ← 12-bit「面積」分數;表 knee 32/128/256 = 幀面積 0.78%/3.1%/6.25%(臉>6.25% 面積 → 飽和 256)
w(%) = interp(T@0xC0911598, cov)   (32→0,128→25,256→50)   ← in-box 混合權重(臉越大越吃 in-box,最高 50%)
blend = (gridY·(100−w) + inboxY·w)/100                     [FUN_c0229ff8;param_3=gridY, param_4=inboxY]
a(%) = interp(T@0xC0911580, cov)   (32→100,128→75,256→60)  ← 覆蓋衰減
b(%) = interp(T@0xC0911570, AE 亮度 _DAT_c3202c90=FUN_c021a458()[0])  (≤−4096→50, (−4096..0]→50..100 lerp, >0→32)  ← 亮度增益
YLevel_face = b · a · blend / 10000  =  b·a·(gridY·(100−w)+inboxY·w) / 1,000,000
```
- **gridY**(param_3)= 256 區網格聚合 YLevel(YLevelTarget `FUN_c02130f8`,mode 2/3/5/7 選 slot 0x10/14/18/1c/0xc)。
- **inboxY**(param_4)= **臉框內 YLevel,不從 16×16 網格取**:`FUN_c022a240 → FUN_c0311998(0xC3201B14, 4, 0)` = 專用 ISP/AE **ROI 統計累加器**(bank4=current ROI、ch0=Y),ROI 每幀由 `FUN_c022a190` 用**像素精確臉框矩形**設(`FUN_c0219b18` slot 0x20)。→ **Q24:非二值/非面積加權/非整格,是像素精確矩形 ROI 的單一純量**;子量化在不透明 ISP HW。
- 3-pt interp 前端 `FUN_c0213998`/`FUN_c0213a50`(中段才呼叫 `FUN_c04d0a20`);blend 前端 `FUN_c0229ff8`;caller/arg 綁定 `FUN_c0210a70`(evaluator=物件 vtable slot +0x10)。信心 HIGH。

**意義**:臉區 AF **依臉覆蓋多少去加權聚合網格區**,不是把單一 AF 區丟在框上。眼框則是**眼子記錄框直接當視窗**(`param_6=0`,不縮放)。
**⚠️ 更正**:`2.5×W/1.5×H` 重塑**不是眼**,是 **AAT 色彩追蹤路徑** `FUN_c05c3d28`(`w·5/2, h·3/2` 以追蹤框中心重置)。

═══════════════════════════════════════════════════════════════
## ⑦ FaceLowContrast 真相 — 信心:高
═══════════════════════════════════════════════════════════════
`FaceLowConstrast`(sic)= 場景分類 enum **#8**(表 `@0xC2F18680`),但 **此 build 從不指派 #8 = 潛伏值**(分類器 `Face @FUN_c027b4b0` 只吐 {0–7,10};消費端把 8 當 ≡7 防禦處理)。
**真正的低對比機制**:
- 每子區亮度幅 `max−min`:**<0x12(18)→VeryLowContrast(4)**、**<0x23(35)→LowContrast(3)**、else Normal(2)(ROM immediate,mask 表 `@0xC2F18648`)。
- 臉旗標 `DAT_c33d16dc≠0` → Face(7)。
- AF 區**排除**機制:rejection-reason 表 `@0xC2F186BC` reason 4=LowContrast(解碼 `FUN_c028fa80`)→ CDAF 選區時**剔除低對比區**、改用其他區(不是擴張臉框)。
- ⚠️ 未解:`GetCafLowconByYLevelFlg` 背後的 YLevel 數值門檻(getter 內聯,常數未定)。

═══════════════════════════════════════════════════════════════
## ⑧ AF-C 耦合:框 → 驅動狀態機 + 運動預測 — 信心:高
═══════════════════════════════════════════════════════════════
- **Dispatcher `FUN_c0275e60`**(CDAF loop @0xC0242068 呼叫)每幀建 0x2024-byte 目標 AF 區:`ctx+0xe8`=臉AF模式(1 主臉 `FUN_c0276030`,2 可選臉/眼 `FUN_c02760b8`);無臉且 AF-C `param_2+0x20c8∈{4,8}` 且致能 `ctx+0x1cc==3` → AAT(`FUN_c02761c8`,type3)。**優先權 臉 > 眼/追蹤**。
- **無縫交接**:雙緩衝(現 `param_1`、前 `param_1+0x2024`),目標丟失時還原前一區(`FUN_c001510c`),避免臉→眼、追蹤→臉 切換時 AF 跳動。
- **預測連結**:每幀把目標區/峰記錄推進 **10 槽 ring `@0xC33D0384`**(`FUN_c0276588`,index `_DAT_c33d510c` 逢 10 繞回),`JudgeSubjectMoveByPeakData @0xC02766A8` 以此為歷史源 → `CorePeakPosEstimateSubjectMove @0xC0277580`(參數見 AF_AE_INTERNALS ⑤)。
- **耦合本質**:框只決定「**哪塊感光區**」成為評價視窗(區跟著框移動,`height/frame` 按主體大小縮放運動門檻)。**預測數學跑在「每區對焦峰位置歷史」(離焦峰運動),不是框像素速度** —— 框運動只間接透過「搬移被評價的區」進入預測,沒有明確框速度項。

═══════════════════════════════════════════════════════════════
## 關鍵位址速查
═══════════════════════════════════════════════════════════════
| 主題 | 函式 / 位址 |
|---|---|
| 臉偵測(HW) | FaceAndEyeDetection::v2 FUN_c05aa190;ROI 暫存 +0x82C/+0x830;預設區 @0xC2DFC540 |
| 眼偵測(CPU) | thread FUN_c05adb08;exec FUN_c05add48;landmark FUN_c05b9a68/c05b9be8;→框 FUN_c05adfb8;L/R FUN_c05ad9b0 |
| 結果解析 | parser FUN_c05aaff8;count FUN_c05ab360;結果管理器 @0xC37CCA9C;座標轉換 FUN_c05a9af0 |
| **選臉評分** | **FUN_c05aad68**(權重 @0xC2DFCF60=[512,256,128,64]);gate FUN_c05aaa38;排序 FUN_c067c4e0 |
| 追蹤(色彩) | dispatch FUN_c05ab650;init FUN_c05b6ba0;track FUN_c05b6cf8;定位 FUN_c05b1168;橢圓 FUN_c05b1e28;信心 FUN_c05b7d98 |
| 座標→AF區 | FUN_c0276288(臉/眼)/ FUN_c02763c0(AAT);長寬比 FUN_c06873e0;AAT 重塑 FUN_c05c3d28 |
| YLevelFace | evaluator FUN_c02136f8;覆蓋比 FUN_c022a2b8;表 @0xC0911580/0xC0911598 |
| 低對比 | 分類 Face FUN_c027b4b0(門檻18/35);排除 FUN_c028fa80(表 @0xC2F186BC) |
| AF-C 耦合 | dispatcher FUN_c0275e60;ring @0xC33D0384;推入 FUN_c0276588;判定 c02766a8;預測 c0277580 |

**⚠️ 重要陷阱(復刻勿踩)**:CAF 除錯 CSV 欄位 `FaceTopX0…xs_pix/ye_pix` 是**誤導標籤** —— collector `FUN_c024f250` 複製的是**每個 AF 區的 CDAF cell**(stride 0x11c 表,CDAF 峰/爬升碼 `FUN_c0242018` 寫),**不是字面臉框**。真正臉框與轉換看 ①/⑤,別去逆那些 global。

**未解**:①眼↔臉去彈跳計數器在偵測產生器 `FUN_c05aa190` 上游(未追到常數)②低對比 YLevel 門檻數值 ③眼優先權選單 enum 數值 ④偵測器內部(不透明硬體)。
