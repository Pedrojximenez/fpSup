# fp ISP 色彩硬體地圖 —— 區塊清單、shadow 暫存器 setter、以及怎麼把 CUVAREA 釘出來

2026-09-27；2026-10-09 補正具名診斷路由。離線稽核:韌體映像 + 反編譯。沒有操作相機。
起因是「機內創意 LUT 要用什麼硬體做」。新產品開發見 [LUT sup](../../../projects/lut-sup/README.md)。

## 結論

1. **尚未找到通用 GPU／3D LUT runtime。** 沒有相關名稱不能證明矽晶裡不存在，
   也不能把已確認的「矩陣＋1D」當成整顆 XZ01 的能力上限。
2. **已有多個原生色彩處理區塊。** `RGBLMAT`、`RGBMAT_PL`、gamma、
   `CUVAREA CARE_SEL`、`CUVCONT`、`CSUP/ECSUP`、`C_SAT_C` 都值得追查。
   完整 `.cube` 是否能由這些區塊精確或近似完成，仍須驗證像素方程式、順序及路由。
3. **名稱確實被程式引用。** 診斷 dumper `FUN_c01597b8` 直接引用名稱並列出 MMIO，
   `FUN_c019c810` 的 descriptor 另外對應 shadow。舊結論「只能靠實機找暫存器」已推翻。
4. **CUVAREA 的位址已釘出，但能力未釘死。** `30116600..30116640` ↔
   `30211024..30211064`，17 words。兩個 UV 向量與象限旗標已可靜態追到，
   尚不足以稱作任意 hue LUT，也未證明 FCBlue／Teal&Orange 使用它。

## ISP 色彩鏈(名稱表原始順序,`0xC07D3600`–`0xC07D3D40`)

```
PRE_TOP   GAPSUP · APKNEE · LM · HSEP · CSEP · MEDF · RWAPKNEE · CORRECT_G · GNR · APGEN · SHUSA_EXT
MAT_TOP   PSTAPKNEE · RGBLMAT · PSTIGAM · IGAMMA
GAM_TOP   GAM_GS GAMDEC · GAM_BAS · YCMAT · GAMMA TABLE · RGBMAT_PL · GAMINT · SBUS GAMMA
PST_TOP   Y_GAMMA · APSUP · SHOOT_G · CUVCONT · ECSUP · CKNEE · CUVLPF YLPF
          CUVAREA CARE_SEL · CSUP · YUVHMF · YUVIIR · YSHD_C · DITHER
FIR_TOP   YUVFIR · FOCALZM · ADD_RND · PRIVACY_MASK
YMED_TOP  C_SAT_C · CORING
CEQ       CEQ_YGAM · CEQ_KNEE · CEQ_CLIP · CEQ_CORING · CEQ_OFFSET · CENH SRAM
SIG0/1    DELTA DARK · DARK SHADING · BAYER_NR · FPNR · RWMEDF · SW_DCT · RAWBLT · RAWOUT
          RAW_CORR · DLTEXP · RAWSHAD_LINEAR · RAW ZOOM · SHADING1/2(_R/_GR/_GB/_B) · 3DDNR
          WHITE BALANCE · GRV_C · VLN_C · TBLSD · NLmeans
其他       TMAP · DHAZ · TNCR · MLNR · ZOOM · BEIS · SIES · BLT_YUV · BLT_NLM · HDR_HIST
          CRCT_TOP · CRCT_3A · SRAM_MGR · DOPT_MAIN/ORIGINAL · CONTRAST
```

完整 115 筆在 `isp-map.json` 的 `blocks`。

三個之前沒記載、對創意 look 有用的:

- **`GAM_TOP RGBMAT_PL`** —— 除了線性域的 RGBLMAT,gamma 級之後還有第二個 RGB 矩陣。
  診斷名不證明像素先後。`FUN_c011a8b0` 預設九字更像 YUV→RGB（尺度 128）;
  在確認之前，不直接把它當成可串接的 RGB→RGB 矩陣。
- **`PST_TOP CUVAREA CARE_SEL`** —— 色度平面 + 區域選擇,旁邊有 `CSUP` / `ECSUP`(colour suppression)。
  是選擇性處理的候選，不能由名稱斷言是 per-hue 的唯一入口。
- **`TMAP`** —— 已定位 `30130600..640` ↔ `30212828..868`，17 words。
  原生設定含尺寸、格點倒數與座標，不能只凭縮寫稱為 tone mapping；
  尚無證據把它當作 RGB 外觀 LUT 引擎。

## Shadow bank setter 地圖

ISP 設定寫在 **`0x3021xxxx` 的 shadow bank**；既有量測中直接讀部分 MMIO 為 0，
不將此概括成所有硬體位址不可讀。`blk_c01.c` 有 **323 支含 shadow 引用的函式**，
完整對照在 `isp-map.json` 的 `setters`（保留歷史 key，含引用不等同全是 setter）。

2026-10-09，診斷名稱與 descriptor 的直接交叉核對：

| 區塊 | MMIO 起點 | Shadow 起點 | words |
|---|---|---|---|
| RGBMAT_PL | `30115B80` | `30210EE0` | 9 |
| CUVAREA CARE_SEL | `30116600` | `30211024` | 17 |
| CUVCONT | `30116700` | `30211068` | 8 |
| CSUP | `30116800` | `30211088` | 12 |
| ECSUP | `30116900` | `302110B8` | 2 |
| C_SAT_C | `30117B00` | `3021127C` | 24 |

重現：`python3 -B extract_isp_map.py`，`python3 -B -m unittest test_isp_map`。
輸出附 ROM／decomp SHA-256、120 筆具名診斷路由與 descriptor 來源。
詳見 [本次追查](LUT_BLOCKS_2026-10-09.md)。

色彩鏈那一段:

依據 [`matrix-gamma-audit.md`](../../liveview/matrix-gamma-audit.md) 的 descriptor 稽核
(來源是 `FUN_c019c810` 的建構,不是 MMIO 排序推測):

| 區塊 | Shadow | MMIO | 內容 |
|---|---|---|---|
| **IGAMMA** | `30210C70..CAC` | `30115000..3C` | 三個控制參數 + **27 個分段值** |
| **RGBLMAT** | `30210CB0..CE4` | `30115100..34` | **兩組係數**、兩個共用欄位、尺度旗標 |
| RGBLMAT 其餘 | `30210CEC..D14` | `3011513C..64` | 一個清零/保存 bit + 13 個初始化欄位 |

對應到 setter,並以參數形狀交叉驗證:

| shadow 偏移 | setter | 參數形狀 | 判斷 |
|---|---|---|---|
| `0x30210C70` | `FUN_c0107208` | 2 字 | IGAMMA 控制 |
| `0x30210C78` | `FUN_c0107250` | **27 個值 → 14 字,無遮罩** | **IGAMMA 的 27 個分段值** |
| **`0x30210CB0`** | **`FUN_c0107490`** | **9 個值,各遮罩 `0x7FF`(11-bit)** | **RGBLMAT 第一組 3×3** |
| **`0x30210CC8`** | **`FUN_c0107608`** | 同上,取自結構 `+0x24` 起 | **RGBLMAT 第二組 3×3** |
| `0x30210CE0` | `FUN_c01076c0` | 2 字 | RGBLMAT 共用欄位 / 尺度旗標 |
| `0x30210CEC` | `FUN_c0107460` | 1 字 | RGBLMAT 其餘 |
| `0x30210CF0` | `FUN_c0101478` | 9 個 13-bit + 4 字 | RGBLMAT 其餘(**不是**獨立矩陣) |
| `0x30210D18` | `FUN_c0107708` | 14 | |
| `0x30210D50` | `FUN_c0107b70` | 16 | |
| `0x30210DA8` | `FUN_c01015d0` | 13 | |
| `0x30211024`–`0x30211064` | `FUN_c010b958` / `FUN_c010baf0` | UV 向量、象限與其他欄位 | CUVAREA CARE_SEL，見本次追查 |

> **⚠ 本表 2026-09-27 更正過。** 初版把 `FUN_c0107250 / 0x30210C78` 寫成 RGBLMAT,
> 那是照抄 [`COLOR_SCIENCE.md`](../notes/COLOR_SCIENCE.md) 的「27×16-bit packer」沒有驗證。
> **27 個值是 gamma knot 數,3×3 只需要 9 個** —— 用參數個數與遮罩寬度一驗就清楚。
> 同一個錯誤也讓 `COLOR_SCIENCE.md` 把 RGBLMAT 的 MMIO 寫成 `0x30115000`(那是 IGAMMA),
> 實際是 `0x30115100`。

⚠ **不要用名稱表的順序去對 shadow 偏移。** 現在用診斷程式的直接引用與 descriptor 交叉核對，
不是依表中排列猜暫存器或像素處理順序。

## per-mode 參數結構:`FUN_c010e118`

色彩模式 → ISP 的參數是填進一個結構,不是直接寫 MMIO:

| 欄位 | 內容 |
|---|---|
| `+0x70..+0xac` | 16 個值,**累加後 clamp 到 0..255 的分段曲線**(對比/亮度斜率) |
| `+0xf0..+0x128` | 15 個值,**同樣是累加 clamp 0..255 的曲線** ← 先前未指認 |
| `+0x1a4 / +0x1a8 / +0x1ac` | 色度增益(飽和) |
| `+0x174..+0x1e8` | 常數群(門檻 200/100/0x32、階數 400/600/800、旗標) |

這兩條 0..255 的累加曲線提供 look 參數線索；其像素作用與相對其他區塊的重要性仍需驗證。
結構再由別處推進 ISP，中間隔了數層。

## 驗證 CUVAREA 的使用方式:實機 diff

2026-10-09 已獲授權並執行原廠 enum 0–15 的 CINE 待機掃描，每模式三份 native 讀取、結束復原。
穩定 mode 差異在 RGBLMAT、YCMAT，以及部分模式的 APSUP／CSUP／C_SAT_C；
CUVAREA 有 OFF 同模式內的非穩定讀取，未建立色彩 mode 因果；CUVCONT 沒有穩定 mode 差異。
這不是 pixel 量測，不證明完整 3D LUT、REC 或 MOV／JPG 路由。
詳見 [上機結果](../../../projects/lut-sup/README.md#2026-10-09-上機結果) 與
[原始量測](../../../projects/lut-sup/validation/20261009-native-mode-trial-05/report.json)。

位址已離線定位；以下為原量測設計，active context 與實際像素變化仍需額外驗證：

```
dump 範圍   0x30210A00 .. 0x302114A0   (僅針對核定 context；涵蓋 MAT_TOP 到 CEQ 對比/飽和欄位)
模式序列    OFF → Standard → FCBlue → TealAndOrange → PowderBlue
條件        同場景、同曝光、同白平衡;每次切模式後等畫面穩定再讀
```

既有量測曾在部分 `0x3011xxxx` 讀到零，shadow 可作設定來源；
仍需核對 active descriptor，不能把所有 MMIO 概括為讀不到。

判讀:

| diff 結果 | 意義 |
|---|---|
| 只在 FCBlue / Teal&Orange 變 | 色彩模式相關候選，還需獨立參數／像素驗證 |
| 所有非 OFF 都相同、只有 OFF 不同 | OFF／非 OFF 共用處理候選，不能只據 diff 命名其功能 |
| 與 `FUN_c010e118` 的 `+0x70` / `+0xf0` 曲線對得上 | 對比/飽和那幾條 |

diff 能找出隨 mode 改變的參數，但還要做 UV／灰階／亮度梯度與輸出路由測試，
不能從「某模式有變」直接證明它是創意 look，或直接照抄到 MOV／拍照 context。

## LUT 製作流程

`cube2fp.py` 只評估「3×3 矩陣 + 每通道 1D 曲線」這個模型，
不能作為整顆 ISP 支援 `.cube` 的能力上限。它給出該模型的逼近誤差。
完整 LUT 匯入／取樣與 DNG 保存工具在 [`fpSup/lut`](../../../fpSup/lut/README.md)。

### 模型

```
out = G( M · in )        M：3×3,列和固定為 1
                         G：每通道 1D 曲線
```

列和=1 → 灰色進去還是灰色 → **G 可以直接從 LUT 自己的灰階軸讀出來**(`G_c(t) = LUT(t,t,t)_c`),
不需要迭代,只剩 M 是一次最小平方解。良態,不會發散。

(第一版用交替最佳化,會發散成係數 388、列和 123 的垃圾。改成這個約束後一次解出。)

### 步驟

```
1. 決定落點        監看(顯示端)還是烘進成品(ISP 端)—— 決定寫哪組暫存器
2. 健檢            python3 cube2fp.py look.cube
3. 讀誤差報告      按飽和度分層,判定「適合轉 / 勉強 / 不建議」
4. 取硬體係數      look.fp.json 裡的 matrix_fixed + curves
5. 上機            寫暫存器 → 回讀驗證 → 拍對照
```

### 落點選擇

| | 寫哪 | 影響 |
|---|---|---|
| **監看 LUT 候選** | 顯示端矩陣(`0x30190870` / `0x30190810` / `0x30190C80`,原廠計算尺度 256)<br>+ RGB gamma(`0x30190940` / `0x30190CB0`) | 需驗 active bank、OSD 覆蓋及 LCD/HDMI 路由，不能先宣稱輸出隔離已成立 |
| **烘進成品候選** | ISP 矩陣／tone／CUVAREA 等原生 PQ 路徑 | 可追 MOV/JPEG context，是否影響 RAW 前級仍需測；不能把所有 context 等同 LV |

顯示端 RGB gamma 是 split toning 的候選；ISP tone 的精確運算域與其他區塊組合能力尚未完整確認。
先前「ISP 只有一條亮度曲線所以做不了」的概括，不作為整體能力結論。

### 曲線點數不是瓶頸

實測把曲線量化成 16 / 33 / 64 / 2048 點,飽和<0.35 的 ΔE 是 **2.86 / 2.88 / 2.88 / 2.88** ——
完全沒有差別。膠片曲線夠平滑,顯示端的 16 個節點就夠。

**瓶頸是那個 3×3**:它是線性的,做不到 per-hue,高飽和區的誤差全部來自這裡。

### 實測:兩個真的膠片 LUT

`Rec709 Kodak 2383 D65.cube`(健檢通過):

| 飽和度 | 佔格點 | ΔE76 mean | p95 |
|---|---|---|---|
| < 0.15 | 2.2% | **0.69** | 2.15 |
| 0.15–0.35 | 9.6% | 3.35 | 8.80 |
| 0.35–0.60 | 22.2% | 10.29 | 20.93 |
| > 0.60 | 66.0% | 18.99 | 41.58 |

```
 1.0982  0.0511 -0.1493        定點(尺度 256): 281   13  -38
 0.1735  0.7452  0.0813                         44  191   21
 0.0277  0.1917  0.7806                          7   49  200
```

Fujifilm 3513DI 數字幾乎相同(0.61 / 3.16 / 10.02 / 19.53)。

**低飽和區 ΔE 0.7 看不出來,而那正是畫面的絕大部分** —— 另一輪量過,實拍有 58.6% 的像素
飽和度低於 0.05,四段素材聯集只佔相機色彩立方體的 13.4%。**擬合準的地方就是你會看到的地方。**

### 健檢會擋掉什麼

`SIGMA_fp_Standard_DWGtoSRGB.cube` 會被標成「不建議轉」:

```
⚠ 灰階軸在輸入 0.50 就到頂 → 這個 LUT 預期的輸入不是 0–1 顯示域(domain 不合)
```

它預期 DaVinci Intermediate 編碼的輸入,餵 0–1 進去上半段全白。**這不是擬合失敗,是 domain 不合**
—— 技術型轉換 LUT 本來就不該進相機。健檢在你浪費時間之前先擋下來。

轉不動的另一類是**需要選擇性色相**的 look(只改天空不動膚色)。3×3 一定會連膚色一起轉。
CUVAREA 位址已定位；是否能搭配其他區塊改善這類 look，仍需驗證。

### 上機前必須驗的兩件事

腳本輸出的定點值是**依指定尺度換算**的,以下兩項尚未量到:

- 顯示端 gamma 表的實際數值範圍(16 點對應到什麼刻度)
- 顯示端 3×3 的暫存器編碼(位元寬、符號、是否有 offset 欄位)

**先寫一組已知值回讀驗證**(例如寫 identity 矩陣 + 線性曲線,確認畫面不變),再寫真實係數。

## 界線

- 名稱↔MMIO↔shadow 的對應已由診斷引用與 descriptor 建立，未驗的是像素語意與 active 路由。
- `0x30210CF0` 是「3×3 形狀」的推測,沒有證據說它是 YCMAT 還是 RGBMAT_PL。
- `TMAP` 已找到位址與尺寸／格點類欄位，不能直接命名為 tone mapping；CUVAREA 已有位址與部分欄位打包證據。
- 沒有證明 CUVAREA 就是 FCBlue 的實作 —— 那是基於名稱與缺乏其他 per-hue 手段的推論。
- 沒有操作相機,以上全部來自靜態檔案。

## 檔案

- `extract_isp_map.py` —— 從韌體、具名診斷引用及 descriptor 重建本筆記的資料
- `isp-map.json` —— 115 個區塊名稱 + 323 支 setter 的完整對照
- `cube2fp.py` —— 3D `.cube` → fp 的 3×3 + 1D 曲線,含健檢與誤差報告 → `<name>.fp.json`

## 相關

- [`notes/COLOR_SCIENCE.md`](../notes/COLOR_SCIENCE.md) —— 色彩管線順序、88 條 tone 曲線、CCM
- [`../liveview/upstream-clip-audit.md`](../../liveview/upstream-clip-audit.md) —— tone 之前的截斷追查(未結案)
- [`../liveview/zcam-e2f6-reference.md`](../../../zcam_e2f6/notes/FP_LIVEVIEW_COMPARISON.md) —— 對照:Z CAM 有使用者 3D LUT 模式
