# fp 錄影中的機身無損壓縮 —— 編碼器規格與尺寸帳 (2026-09-15)

> 這份講**編碼器**:0x300D 到底編出什麼、一幀會變多大、要花多少時間。
> 講**接線**(怎麼從錄影路徑摸到引擎、hook 在哪)的是
> `../../imaging-hw/notes/HW_LOSSLESS_JPEG_CODEC.md`,那份仍然有效,這份不重複。
> 信心標記:**[C]** 反編/規格確認 · **[M]** 本次實測或由實檔量出 · **[I]** 推論 · **[P]** 待上機。
> 本文保存通用 codec/格式研究；目前產品判定、實機證據訂正、async 與動態降載 gates 請讀
> [`projects/lossless-sup/notes/ROADMAP.md`](../../../projects/lossless-sup/notes/ROADMAP.md)。

## 一句話

引擎吐出來的東西**跟 slimRAW 的產物是同一種格式**(DNG `Compression=7`、lossless JPEG、
predictor 1),所以「錄影時機身壓縮」不是發明新東西,是把拍照路徑已經在做的事接到影片幀上。

如果目標包含**機內回放**與未來的**動態抽幀**,目前最合理的順序已調整為:

1. **P0 回放格式閘門**:先決定是延伸 CinemaDngPlay、另做代理預覽,或明確把壓縮片標成
   「只能匯出」。原廠影片路徑目前不解析 tiled `Compression=7` 所需的 tile tags(§14.10)。
2. **P1 安全量測**:保留 exact flush/writer probe,完成整段 preflight/fail-open、表頭引用區驗證、
   codec stage-aware unwind、熱重開清 state;探針不等於可錄影功能。
3. **P2 固定格率 FHD**:只有回放策略成立後,才在 SD flush 外包 wrapper,每幀只 encode 一次、
   512×368、header+scratch 兩段零拷貝;先 23.976p,再驗 29.97p sustained。
4. **P3 管線與降載**:另建 codec/storage worker、queue、順序與 backpressure。若要動態抽幀,
   還必須另定時間軸語意;不能只少寫幾個連號 DNG 就稱為可回放片段。
5. **P4 實驗項**:predictor P1/P5 selector、非 16 倍數 TileLength;都不能進預設。

**引擎的四點成本模型已經量完,候選幾何仍待外部驗證。** 三參數 least-squares 校準殘差
在 ±2 µs 內(尚不是獨立驗證集):

```
t(µs) = 2,179  +  4,954.40 × 對齊Mpix  +  40.926 × tile數
        └ 每次呼叫    └ 201.8 Mpix/s        └ 每個 tile
```

主機端打包路徑已經驗證:真的把一幀 fp CinemaDNG 壓成了 `Compression=7`,LibRaw 解開後
**與原檔逐樣本完全相同**,表頭手術全部發生在既有 78,848 byte 表頭的零區裡。

| engine-only | @24p | @30p |
|---|---|---|
| **FHD** | 33% duty ✅ | **42% ✅** |
| **OG3K** | **82% ⚠️** | 103% ❌ |
| UHD | 108% ❌ | 135% ❌ |

壓縮比從**引擎自己的 size table** 量出來是 **2.525:1**(ISO 100、正確曝光、12-bit 全幅)。
⚠️ 不要用完整 DNG 大小推:例如 `_SDI0012.DNG` 整檔 36.33 MB,其中 14-bit raw tiles
25.68 MB,其餘約 10.65 MB 是其他 IFD/預覽;另一次 12-bit probe 的引擎輸出才是 14.56 MB。
兩者不是同一 bit depth/tile 條件,不能直接相減(§10)。滿載的消除能力約 **65–145 MB/s**。

另一個會改變實作的發現:相對原廠 256×256 / 最大 512×512,FHD 的正確 tile 幾何可少
**17.4% / 24.0% 編碼時間**(§8)。

## 0. 引擎吃的是打包資料 —— 所以 hook 手上那塊就能直接餵 [C]

先解掉一個會讓整個方案作廢的疑慮:hook 點 `FUN_c069ac88` 手上的 buffer 是**打包 12-bit**
的 CinemaDNG strip,而拍照路徑餵給引擎的是感測器 buffer。兩者格式若不同,來源就不能直接用。

`FUN_c062fff8` 的 stride 計算回答了:

```c
iVar8 = 12 / 14 / 16 / 10;                          // bitdepth code -> 每樣本位元數
_DAT_300d006c = (iVar8 * width & 0x7ffff) >> 4;     // 每列 bit 數 / 16 -> 16-bit 字
_DAT_300d0070 = (iVar8 * tileW & 0x3fff ) >> 6;
```

列距 = **位元深度 × 寬度 / 16**。12-bit、寬 1936 → 23232 bits = 1452 字,正好是 CinemaDNG
strip 的列距。**引擎讀的是原生位元深度的打包資料**,不是未打包 16-bit。

⇒ `buf + 78848` 直接就是合法的 src,不必解包、不必多一塊中繼緩衝、不必多一次 DRAM 來回。
跨 10/12/14-bit 共用時,這也解釋了「寬度必須是 8 的倍數」約束;單看 12-bit 的
`12×width/16` 其實只要求寬度為 4 的倍數。

同一個函式還把邊緣 tile 的處理攤開:`0x4C` 放 `(W-1)/tileW` 與 `(H-1)/tileH`(格數減一),
`0x50`/`0x54` 放 `W mod tileW` 與 `H mod tileH`(餘數)。所以引擎**知道**邊緣只有部分資料 ——
它只讀真的那部分,但仍然編出滿格的 tile(見 §4)。

## 1. 跟 slimRAW 的關係

slimRAW 能對 fp 素材省很多,是因為**相機錄影根本沒壓**(CinemaDNG 全部 `Compression=1`),
熵編碼的空間整個留著。它做的事 —— 把每幀重新包成 lossless JPEG 的 DNG —— 和 0x300D
拍照時做的事是同一件。差別只有**誰做、什麼時候做**:

| | 壓縮器 | 時機 | 產物 |
|---|---|---|---|
| slimRAW | 主機 CPU | 拍完之後 | DNG `Compression=7` |
| fp 拍照 | 0x300D 硬體 | 快門當下 | DNG `Compression=7`,256×256 tile |
| **想要的** | 0x300D 硬體 | **錄影當下** | 同上 |

所以這題的風險不在「壓縮會不會有效」,那已經被 slimRAW 證明過了;風險在時間與接線。

## 2. 引擎的編碼規格 —— 從它自己的輸出讀出來 [M]

拿一張相機自己拍的 `Compression=7` 照片(`_SDI0011.DNG`,6064×4042 14-bit),
把 tile 的 JPEG 標頭直接解出來:

```
FFC3 SOF3 (lossless)   precision=14  lines=256  samples/line=128  components=2
       comp0 id=0 H=1 V=1      comp1 id=1 H=1 V=1
FFC4 DHT  class=0 id=0         FFC4 DHT class=0 id=1
FFDA SOS  Ns=2  predictor(Ss)=1  Se=0  Ah=0  Al=0
```

讀出來的事實:

- **一個 256 寬的 tile 被拆成 2 個 component**(偶欄 / 奇欄),所以每個 component 的
  「左鄰」天生就是**同色**的 CFA 樣本。這正是 Bayer 無損壓縮的標準做法。
- **predictor = 1(Ra,左)**。純水平預測,不用上一列。
- **Al = 0**,沒有 point transform ⇒ 真無損,和「硬體沒有品質旋鈕」一致。
- **每個 tile 自己帶 Huffman 表,而且每個都不一樣**(抽 9 個 tile,9 個相異 DHT)⇒
  引擎有**逐 tile 自適應統計** [M]。通常需先統計再編碼(或暫存殘差後編碼) [I],
  但僅由輸出不能斷言感測器資料被實體讀了兩遍。
- 每 tile 標頭 **94–98 bytes** + EOI 2 bytes。tile 數再多也可忽略。

## 3. 成本模型,用晶片自己的輸出校準 [M]

寫了一個 lossless-JPEG 解碼器把 tile 解回像素,再用上面那組參數重算「這個 tile 應該多大」
(逐 component 最佳 Huffman + category 附加位元 + 96 B 標頭),對照引擎的實際輸出:

| tile | 引擎實際 | 模型 | 誤差 |
|---|---|---|---|
| 0 | 63,016 | 62,881 | −0.21% |
| 1 | 66,213 | 65,921 | −0.44% |
| 23 | 53,312 | 53,121 | −0.36% |
| 100 | 69,731 | 69,556 | −0.25% |
| 200 | 66,509 | 66,348 | −0.24% |
| 383(角落,兩邊都是邊緣) | 43,590 | 42,464 | −2.58% |

一般 tile 的模型與硬體差 **0.2–0.5%**,角落 tile 是 **2.58%**;整幀仍應視為近似值,
不是「熵的理論下限」。工具在 `../tileplan.py`。

## 4. 邊緣 tile 補滿的方式 —— 時間全價、位元組幾乎免費 [M]

> ⚠️ 這一節推翻了本文上一版的說法(「padding 在時間和位元組上都是全價」)。位元組那半是錯的。

6064 不是 256 的整數倍(23.7 個),但**最後一欄 tile 的 SOF 仍然是 128×256 滿格** [M],
而 §0 又顯示引擎其實**知道**餘數是 176。所以它只讀真資料、內部補滿後編出滿格 tile。
把邊緣 tile 解開看它補什麼:

```
右邊緣 tile(真實資料只有 176/256 欄)
   第 100 列 …172..183:  2011 3059 1971 3264 1971 3264 1971 3264 …
   補滿區每列只有 2 個相異值,等同複製最後一組 CFA 欄對

下邊緣 tile(真實資料只有 202/256 列)
   第 202 列起:  2470 1798 2470 1798 …   整塊補滿區只有 2 個相異值
   而且不是最後兩列的複製 —— 那組常數正是「上一列的第一組 CFA 對」
```

兩種現象是同一個機制:**引擎對補滿的樣本一律送出 diff = 0**。解碼端第一個補滿樣本用正上方
(Rb)、之後沿列用左鄰(Ra),於是水平補滿塌成最後一組欄對、垂直補滿整列塌成上一列的首組值。
兩者都是 SSSS=0 的長串,**約 1 bit/樣本**。

把這個規則寫進模型,再對引擎自己的邊緣 tile 驗一次:

| 邊緣 tile | 引擎實際 | 模型 | 誤差 |
|---|---|---|---|
| 右邊緣(176/256 欄) | 54,933 | 54,725 | −0.38% |
| 下邊緣(202/256 列) | 58,174 | 57,981 | −0.33% |
| 角落(176×202,兩邊都補) | 43,590 | 42,464 | −2.58% |

(角落那格引擎比最佳 Huffman 差 2.6% —— 補滿樣本最多、統計最偏斜的一格,硬體建表的近似在
這裡露出來。對整幀的影響 <1%。)

> ⇒ **補滿的像素在「時間」上是全價**(引擎照跑,韌體的 timeout 也是按 tile 對齊後的像素算),
> **在「位元組」上幾乎免費**。所以 tile 幾何主要是**速度**問題,不是檔案大小問題。

## 5. tile 幾何:第一次估算(已被 §8 的實測取代)

合法解是兩組約束的交集:

```
引擎 FUN_c062fff8   tileW 32..512 且 32 的倍數     tileH 2..512 且為偶數
TIFF 6.0            TileWidth / TileLength 都必須是 16 的倍數
⇒ 交集              tileW ∈ {32,64,...,512}        tileH ∈ {16,32,...,512}
```

以下舊估算當時對影片候選另加了 **tile 數 ≤64** 的人為上限(表內 6K 參考列自己又用了96,
正是舊版不一致處);那不是表頭的真容量。目前最小已知 gap 3,326 B 扣掉 59-tag IFD 後
可放 326 tiles,§8 起已用真容量重算:

| 格式 | 最佳 tile | 個數 | 補滿後 | 浪費 | 引擎 ms | fps 上限 |
|---|---|---|---|---|---|---|
| **FHD 1936×1090** | **288×368** | 21 | 2.226 Mpix | **+5.5%** | 13.1 | 76 |
| | *[256×256]* | 40 | 2.621 | *+24.2%* | 15.4 | 65 |
| | *[512×512]* | 12 | 3.146 | *+49.1%* | 18.5 | 54 |
| **OG3K 3024×2010** | **512×336** | 36 | 6.193 | +1.9% | 36.5 | 27 |
| | *[256×256 / 512×512]* | 96 / 24 | 6.291 | +3.5% | 37.1 | 27 |
| **UHD 3840×2160** | **480×432** | 40 | 8.294 | **+0.00%** | 48.9 | 20.5 |
| | *[512×512]* | 40 | 10.486 | *+26.4%* | 61.8 | 16.2 |
| 6K 6064×4042 | 512×512 | 96 | 25.166 | +2.7% | 148.3 | 6.7 |

(引擎 ms 用實測下限 169.7 Mpix/s。)

**FHD 是重災區**:1090 除不進 256 也除不進 512。照抄拍照的 256×256 白跑 24% 的像素,
用最大的 512×512 白跑 49%。**288×368 把它降到 5.5%,比 512×512 快 29%。**
**UHD 更漂亮:480×432 剛好整除,一格都不浪費**(512×512 會白跑 26%)。

位元組那邊的差距小得多(因為 §4):真的把檔案做出來量,

```
FHD   256x256  40 tiles   1,291,014 B   2.513:1
FHD   512x512  12 tiles   1,378,342 B   2.354:1
FHD   288x368  21 tiles   1,250,148 B   2.595:1   <- 比 512x512 小 10%
OG3K  512x336  36 tiles   3,356,188 B   2.740:1
```

## 6. 端到端做出來了 —— 主機端,像素 bit-exact(表頭見本節訂正)[M]

不只是估算。把一幀真實的未壓縮 fp CinemaDNG **實際壓成 `Compression=7`**,而且刻意照
機身端 hook 能做的方式做:

```
保留原本 78,848 byte 的表頭原封不動
在表頭的零區裡「重建」一份 IFD:Compression 1 -> 7、
  丟掉 273/278/279(StripOffsets/RowsPerStrip/StripByteCounts)、
  加上 322/323/324/325(TileWidth/TileLength/TileOffsets/TileByteCounts)
  58 個標籤 -> 59 個
既有標籤的 out-of-line 值全部原地不動(表頭沒動,指標自然還有效)
改寫檔頭 offset 4 指向新 IFD
壓縮資料照舊從 78,848 開始寫
```

結果:

```
A001_083_FHD_f07   3,244,544 -> 1,250,148 B  (288x368, 21 tiles)  2.595:1
A001_083_FHD_f07   3,244,544 -> 1,291,014 B  (256x256, 40 tiles)  2.513:1
A001_084_OG3K_f07  9,196,544 -> 3,356,188 B  (512x336, 36 tiles)  2.740:1

exiftool  無新增警告(來源原有 3 個 minor MakerNotes 警告),Compression/TileWidth/TileLength 正確
LibRaw    三個檔全部解得開,raw_image 與原檔【逐樣本完全相同】
新 IFD 用掉 882 / 1,034 bytes,零區有 3,410 bytes
```

**主機端打包路徑已經 bit-exact 驗證。** 連 288×368 這種非原廠、自訂 tile 尺寸 LibRaw 都吃。
而且成本模型預測 1.290 MB、實際做出來 1,291,014 B —— 差 0.08%。

### ⚠️ 訂正(2026-09-16):那塊「零區」不是空的,是 SIGMA 的 MakerNote

上面那段手術**寫壞了中繼資料**,而我的驗證抓不到。`projects/lossless-sup` 的
host trial 用獨立的 TIFF 守衛檢查了同樣四張幀,四張全部在編碼前就被拒絕。自己驗過:

```
Exif IFD @16676,47 個標籤
MakerNote (0x927C) type=7 count=54338   宣告範圍 17684 .. 72022
  開頭 bytes: 53 49 47 4d 41 ...  = "SIGMA"
我寫新 IFD 的 68612                      在裡面
```

**尾端那 3,410 bytes 的零是 MakerNote 宣告酬載的一部分,不是無主的 TIFF padding。**
LibRaw 逐樣本相等之所以通過,是因為 LibRaw 根本不解 MakerNote —— 像素確實無損,
但我覆蓋掉了 882–1,034 bytes 的原廠中繼資料。

所以前一節「**掃出夠大的零區**」那個處方是**錯的方法**:零不等於可用。正確的判準是
**這個位址有沒有被任何標籤(含 Exif / GPS / Interop / SubIFD 等巢狀 IFD)宣告**,
要算的是完整的受保護集合,不是找零。

替代做法(`projects/lossless-sup/tools/mkcompressed_safe.py`):原本 78,848 bytes 的表頭
**一個位元組都不動**,只改檔頭 offset 4 的根 IFD 指標,新的 IFD/表格**接在 78848 之後**,
壓縮資料改從 79872 開始 —— 也就是**表頭長大 1,024 bytes**。四張真實幀全部通過(原始
根 IFD 位元組、非佈局標籤、巢狀中繼資料、LibRaw 2,110,240 個樣本逐一相等):

```
A001_083 FHD f07          3,244,544 → 1,261,568   2.572:1
pre-stage4 A001_001 f001  3,244,544 → 1,329,152   2.441:1
pre-stage4 A001_002 f001  3,244,544 → 1,398,272   2.320:1
stage4 A001_001 f249      3,244,544 → 1,389,056   2.336:1
```

(用的正是 §8 的 512×368、predictor 1。比值 2.32–2.57,與 §10 實測的 2.525 一致。)

**但這個做法機身端用不了** —— 相機的寫檔器是**固定大小表頭**,不能長大 1 KB。
所以「表頭放得下嗎」這一題**重新打開**,而且比原本難:既不能長大,又不能佔用 MakerNote。
可能的出路(都未驗證):壓縮幀改寫一份較短的 MakerNote、或讓寫檔器對壓縮幀改用不同的表頭長度。

## 7. 上機實測 —— 引擎的完整成本函數 (2026-09-15)

在相機上量的,hook 包住拍照路徑自己的 `bl FUN_c05a6920`(不 cold-call)。
四個測點,三參數 least-squares 模型,**校準殘差在 ±2 µs 內**;仍需其他幾何做外部驗證:

```
t(µs) = 2,179  +  4,954.40 × 對齊Mpix  +  40.926 × tile數
        └ 每次呼叫    └ 201.8 Mpix/s        └ 每個 tile
```

| 對齊像素 | tiles | 實測 µs | 模型 µs |
|---|---|---|---|
| 25.166 Mpix | 384 | 142,576 | 142,576 |
| 25.166 | 96 | 130,790 | 130,790 |
| 6.291 | 96 | 37,280 | 37,278 |
| 6.291 | 24 | 34,330 | 34,332 |

### 怎麼把三項分開的

單看不同畫幅是分不開的:同樣用 256×256 的話 **tile 數 = 對齊像素 / 65536**,兩個變數完全共線。
關鍵是這個控制組 —— 對這兩個幾何,256 和 512 的格線**補滿到完全相同的光柵**:

```
6064x4042   256 → 24x16 = 384      512 → 12x8 = 96      都是 6144x4096
3032x2012   256 → 12x 8 =  96      512 →  6x4 = 24      都是 3072x2048
```

像素數不變、tile 數變 1/4、而且都還是單一 stripe(`FUN_c062f478` 的 64 MB band),
所以電源開關次數也一樣。做法是在 hook 裡把 encStruct 的 tileW/tileH 換掉再還原
(`raw/ljtile.S`)。兩個尺寸各自獨立算出的每-tile 成本是 **41.0 / 40.9 µs**,一致到 0.2%。

### 三個數字各自的意義

- **201.8 Mpix/s** 才是引擎真正的像素速率。先前量到的 169–176 是「256×256 下的等效速率」,
  被每-tile 那一項吃掉 9%。
- **40.93 µs / tile**。256² 與 512² 這組同光柵控制點支持固定 tile 項約 41 µs;
  512×368 / 512×336 / 480×432 是由模型外推,仍待獨立幾何驗證。可能來源是 Huffman 統計、
  位元對齊或 DMA 周轉,不能只憑時間拆得更細。
- **2,179 µs / 呼叫**。⚠️ 我在拿到每-tile 這一項之前曾經把它收回,說它是量測假象 —— **那次收回是錯的**,
  它是真的,只是在共線的兩點擬合裡分不出來。

### 2.18 ms 尚未定位;「持有 reference」會弄壞 bring-up

bring-up / teardown 整條路都讀過了 —— `FUN_c062fee8` → `FUN_c0708c60`(電源域 3)、
`FUN_c06304f0`、`FUN_c07095a8`(時脈域 5)、`FUN_c0630480`,底層 `FUN_c070e060` / `FUN_c070e0b8` ——
反編中**只看到暫存器寫入,沒有顯式延遲迴圈或 settle 等待**。這排除韌體主動 sleep,
但不能排除 MMIO/clock-domain transition 或 IRQ→task 喚醒的硬體等待。每條 stripe 的 memset 也只有
`tile數 × 4` bytes(`_DAT_c302cde8`,由 `FUN_c062f5a8` 設)。

而顯而易見的優化「先持有一個 reference 讓電源域不要關」**會讓 bring-up 直接失敗**:

```c
FUN_c070dc18:  if (0 < refcount[domain]) return 0;   // 已經開著
FUN_c07095a8:  else if (iVar1 == 0) uVar2 = 1;       // → 回 1
FUN_c062fee8:  if (FUN_c07095a8(5,1) == 0) {...}     // 只認 0,其餘視為失敗
```

時脈這條不容忍 refcount(電源域的 `FUN_c0708c60` 是 `r==0 || r==1` 兩者皆可,它容忍)。
這正好解釋了 2026-08-30 那次「先手動給 domain 5 也沒用」。
2.18 ms 到底花在哪仍未定 —— 要拆成「踢之前 / 踢之後」得在 `FUN_c062f6f8` 裡的
Thumb BL 上再插一個時戳。

### 時脈沒有現成的旋鈕

`300000000` 這個常數只出現在 RFC 讀出的分頻計算(寫 `0x300C0208`),**codec 沒有自己的頻率常數**。
若實際時脈是 200 MHz,201.8 Mpix/s 約為 1.01 pixel/clock,只表示數量級相符;
目前沒有獨立量到 codec clock。已知時脈控制與感測器讀出共用、沒有明確獨立分頻器,不值得動。

## 8. tile 幾何的最佳解(用實測成本函數重算)

最小化 `4,954.40 × 對齊Mpix + 40.926 × tile數`,限制為引擎/TIFF 的幾何約束與
最小已知 3,326 B header gap 可容納的 326 tiles:

| 格式 | 最佳 tile | tiles | 時間 | vs 256×256 | vs 512×512 |
|---|---|---|---|---|---|
| **FHD 1936×1090** | **512×368** | 12 | **13.87 ms** | −17.4% | −24.0% |
| **OG3K 3024×2010** | **512×512** | 24 | **34.33 ms** | −7.9% | — |
| UHD 3840×2160 | 480×432 | 40 | 44.91 ms | −12.9% | −19.5% |
| 6K 6064×4042 | 512×512 | 96 | 130.8 ms | −8.3% | — |

§5 那個「只把 padding 壓到最小」的選法(FHD 288×368,21 tiles)現在是次佳 —— 14.07 ms,
輸給 512×368 的 13.87,因為**少 9 個 tile 比少 0.035 Mpix 值錢**。

這張表只排**時間**。若把寫卡量也放進目標函數,OG3K 應選 **512×336**:34.3357 ms,
只比 512×512 的 34.3316 ms 多 **4.1 µs**,但既有實幀由約 3.402 MB 降到
3.354 MB(−1.4%;另一個畫面約 −4.0%)。這是卡速受限時幾乎免費的收益。FHD 的容量版
則是 288×368:比 512×368 慢 0.193 ms、檔案只再小約 0.9–1.0%,收益小得多。

## 9. 錄影預算判定(codec 實測 + 儲存 benchmark,未做端到端)

引擎側(§7 的成本函數,最佳 tile):

| 格式 | @24p | @30p |
|---|---|---|
| **FHD** | 33% duty ✅ | **42% ✅**(爭用 +17% → 49%) |
| **OG3K** | **82% ⚠️**(爭用 → 96%) | 103% ❌ |
| UHD | 108% ❌ | 135% ❌ |
| 6K | 314% ❌ | 392% ❌ |

碼率側(含 78,848 B 表頭,對照實測 SD 94 MB/s、SSD 390 MB/s):

| | 未壓縮 | 2.525:1 | 2.0:1 | 1.5:1 |
|---|---|---|---|---|
| FHD 30p | 97.2 | **39.9** | 49.8 | 65.6 |
| OG3K 24p | 220.5 | **88.5** | 111.2 | 147.6 |
| UHD 24p | 300.2 | 120.0 | 151.0 | 200.8 |

表中的 30p / 24p 實際按 29.97 / 23.976 計算。引擎 duty 與獨立卡速都不是整合後的總 service time。

靜態 call chain 已確認目前 hook 架構在**同一 worker 先 blocking encode,再同步 V5.02 SD flush,
返回後才取下一幀** [C]。
所以必須相加,不能把兩欄當成可重疊資源。用既有 f07 實際輸出大小估算(尚未含 open/close、
filesystem 與其他固定成本):

| 模式 | frame budget | encode | write @94 / @66 MB/s | 串行合計 @94 / @66 | 現架構 |
|---|---:|---:|---:|---:|---|
| FHD 23.976 | 41.71 ms | 13.87 | 13.4 / 19.1 | **27.3 / 33.0 ms** | 最安全首測 |
| FHD 29.97 | 33.37 ms | 13.87 | 13.4 / 19.1 | **27.3 / 33.0 ms** | 94 MB/s 可試;66 MB/s 邊緣 |
| FHD 50 | 20.00 ms | 13.87 | 13.4 / 19.1 | 27.3 / 33.0 ms | ❌ |
| OG3K 18.002 | 55.55 ms | 34.34 | 35.7 / 50.9 | **70.0 / 85.2 ms** | ❌ |
| OG3K 23.976 | 41.71 ms | 34.34 | 35.7 / 50.9 | **70.0 / 85.2 ms** | ❌ |

- **FHD 先 23.976p、再 29.97p,但仍需 sustained writer 驗證。** f07 實幀在 94 MB/s
  模型約 27.3 ms;落到 66 MB/s 已是 33.0 ms,還沒算固定開銷。它仍能解掉一個真實的痛 ——
  未壓縮的 97.2 MB/s
  本來就壓著 94 MB/s 的卡在跑,`SD_WRITE_LATENCY_MEASURED.md` 那個 692 ms 最壞寫入延遲、
  writer 搶不到鎖與陀螺儀掉樣本都**符合 storage pressure 的症狀**,但尚不能斷言只有這個根因。
- **OG3K 18/24p 在現架構都不可持續。** 實際 f07 樣本也要約 70 ms/幀,同步上限約
  14.3 fps@94 MB/s / 11.7 fps@66 MB/s;28-frame ring 只會延後填滿。
- **UHD:卡在引擎**,跟壓縮比無關。24p 差 8%(44.91 vs 41.71 ms)。

### OG3K 30p 單獨拆開看

引擎那邊只差一點點,碼率那邊差得比較多:

```
最佳 tile 512x512(24 個)  34.33 ms / 幀      30p 預算 33.37 ms  → 103%,差 0.96 ms
                                              爭用 +17%          → 120%
```

差的 0.96 ms **比每次呼叫的固定成本 2.18 ms 還小** —— 若那筆能消掉或重疊掉,乾淨狀態
會變成 32.15 ms / 96% duty 剛好過;但爭用一進來又不行。而且 tile 幾何已經榨到底
(512×512 的 24 個是 tile 數下限,換任何幾何只會更慢:512×336 是 34.34、384×512 是 34.66)。

碼率:30p 壓完 **110.6 MB/s**(2.525:1),對 94 MB/s 的卡超 18%。
機會式壓縮(壓得完的幀壓、壓不完的原樣寫)也救不了:

```
乾淨  f=0.97  →  115.2 MB/s        爭用  f=0.83  →  138.5 MB/s
```

**結論**

| 去處 | 判定 |
|---|---|
| OG3K 30p → 機身 SD | ❌ 引擎差 3%(爭用後 20%)、卡差 18%,兩個都要解,而引擎沒有時脈旋鈕 |
| OG3K 30p → SSD | ⚠️ **壓縮不是必需品** —— 未壓縮 275.6 MB/s 已經在實測 390 MB/s 的 SSD 之下。壓縮的價值是**同一顆碟錄兩倍長**(→ 115–140 MB/s),不是可行性 |
| OG3K 18/24p → 機身 SD | ❌ 現行 worker 的 encode+write 串行約 70–85 ms/幀;需重新管線化,不是調 tile 可解 |

⇒ **現行同步架構先做 FHD;OG3K 18/24 也必須先重做 pipeline。30p 是 SSD 的事,而 SSD
本來就不需要壓縮來解決吞吐。**

## 10. 既有 probes 中時間只弱受內容影響;壓縮比要量引擎 [M/P]

用 ISO 當熵的旋鈕,同一場景、同一幾何(6064×4042 12-bit、512×512、96 tiles):

| ISO | µs | Mpix/s |
|---|---|---|
| 100 | 130,259 | 193.2 |
| 800 | 132,739 | 189.6 |
| 6400 | 133,059 | 189.1 |
| 25600 | 132,469 | 190.0 |

在這四個 ISO probe 的輸出範圍內,編碼時間只差 **2.1%**,表示 VLC 對這批內容不敏感。
但 ISO 與曝光沒有受控,正確曝光高 ISO / 更高熵場景尚未封閉;因此不能外推成「任何畫面都不掉速」。
§7 的成本函數目前是合理的工程模型,不是已證明的最壞情況上限。

### ⚠️ 陷阱:靜態 DNG 的檔案大小不能拿來算壓縮比

我第一次用卡上的檔案大小推壓縮比,得到 ISO 100 只有 1.43:1、ISO 6400 就膨脹 ——
**那是錯的**。把 hook 改成直接加總引擎自己的 size table(`_DAT_c302cde4`,
`_DAT_c302cdec` 筆,**大端序**存放,`FUN_c062f4c0` 就是那個位元組交換)之後:

```
ISO 100、正確曝光、12-bit、6064x4042、512x512 tiles
  96 tiles   每 tile 113,292 – 202,469 bytes,平均 151,669
  壓縮總量   14,560,256 bytes
  未壓縮     36,766,032 bytes
  壓縮比     2.525 : 1
```

不要把這個 12-bit probe 和 native 14-bit 檔案混成同一條件。以 `_SDI0012.DNG` 為例:

```
完整檔案                          36,326,688 bytes
14-bit / 256×256 raw TileByteCounts 約 25.68 MB
其餘 IFD、內嵌預覽等              約 10.65 MB
```

上面的 **14,560,256 bytes** 則是另一次 12-bit / 512×512 probe。它可以證明 12-bit
引擎輸出與壓縮比,但不能直接與 14-bit native payload 相減來算預覽。共同教訓仍是:
**要量 raw 壓縮比就讀 size table / `TileByteCounts`,不要用完整 DNG 大小。**

§11 的 14-bit 數字則是直接加總 `TileByteCounts`,**沒有**被預覽污染;它和這個陷阱不同。
但它的分母是補滿後光柵,用來估「相對未壓縮寫卡量」時會因 2.7% padding 略高估壓縮比。

### 消除能力(回答「滿載能降多少 MB/s」)

```
滿載吞入   228–281 MB/s(12-bit;畫幅越大,每次呼叫與每-tile 成本攤得越薄)
爭用後     195–240 MB/s
消除 = 吞入 × (1 − 1/壓縮比)
```

| 壓縮比 | 消除 MB/s |
|---|---|
| 2.525:1(實測,ISO 100 正確曝光) | **118–145** |
| 2.0:1 | 98–120 |
| 1.5:1 | 65–80 |

⇒ **大致 65–145 MB/s,典型抓 100**。純像素上限 302.7 MB/s 吞入,2.525:1 下消除 183。

⚠️ 仍未量:**正確曝光下的高 ISO**。相機的快門與光圈**從主機寫不進去**
(`menu SetShutterSpeed` / `SetFnum` 只讀不寫),所以沒辦法用固定曝光掃 ISO ——
固定 1/60 掃 ISO 等於在掃曝光,高 ISO 會過曝削波。要補這條曲線,得在相機上
把每個 ISO 的曝光調對,每點約十秒。實務上使用者多半就開 100/800/3200 並把曝光控好。

## 11. 壓縮比的真實變異(靜態檔案)[M]

引擎的實際輸出,從相機自己拍的 7 張 14-bit 照片直接加總 `TileByteCounts`(不是模型)。
第一欄以引擎真的處理的 6144×4096 補滿光柵為分子;第二欄以 6064×4042 有效樣本為分子,
後者才適合估未壓縮寫卡量:

```
素材               對齊光柵比          有效樣本比
_SDI0010..0013   1.711 – 1.718 : 1   1.667 – 1.673 : 1
_SDI5625/5626    1.862 / 1.909 : 1   1.813 / 1.859 : 1
_SDI0042         2.138 : 1           2.083 : 1
```

**14-bit 有效樣本比 1.67–2.08:1。** 12-bit 影片幀通常會更好(少兩個 bit 多半是雜訊) [I],
本次實際壓出來的 FHD/OG3K 幀是 2.51–2.74:1。但那幾幀是**同一個暗場景**
(平均值 404/4095,取自 open-gate EV bug 的證據集),所以:

> 規劃暫用 **1.65:1 作壓力下限、2.0:1 作 12-bit 設計值、2.6:1 作這批暗場素材實測值**。
> 舊筆記的 2.3:1 與 slimRAW 的 2.18:1 落在中間,彼此一致。
> 目前複雜度/雜訊較高的 14-bit 素材最低有效比約 1.67;12-bit、正確曝光的高 ISO 曲線仍未量。
> 現行同步路徑的 OG3K 18/24 已被 §9 的總 service time 排除;即使未來管線化,
> SD 那一側也吃不起 1.65–2.0 的低壓縮比。

## 12. 順帶訂正兩個小數字

- 舊的 169.7 Mpix/s 有兩個問題:分母用了**真實**像素而非補滿後的,而且它是 **256×256 下的
  等效速率**,把每-tile 成本算進了每像素裡。實測拆開後是 **201.8 Mpix/s + 40.93 µs/tile +
  2.18 ms/呼叫**(§7),同一個 14-bit 全幅幀對應 169.5 Mpix/s 的等效值 —— 兩者並不矛盾。
- 每幀 78,848 B 的表頭在未壓縮時只佔 2.4%,壓縮後佔 6.3%(FHD)。30p 是 2.4 MB/s。
  不值得動,但排 SD 預算時別忘了它。

## 13. 未決

| # | 問題 | 狀態 |
|---|---|---|
| 1 | ~~引擎真實持續速率~~ | **已答**(§7):201.8 Mpix/s + 40.93 µs/tile + 2.179 ms/呼叫;四點校準殘差 ±2 µs,待外部幾何驗證 |
| 2 | ~~引擎補滿時讀到什麼~~ | **已答**(§4):一律送 diff=0,時間全價、位元組幾乎免費 |
| 3 | 高熵 tile 上 VLC 會不會掉速 | **部分回答**(§10):既有四個 ISO probe 只差 2.1%;正確曝光高 ISO / 最壞熵仍待量 [P] |
| 4 | **壓縮幀的表頭要放哪** | **重新打開**(§6 訂正):原以為可用的零區落在 SIGMA MakerNote 宣告的 17684..72022 內,`projects/lossless-sup` 的 TIFF 守衛四張幀全部在編碼前拒絕。唯一通過的做法把表頭撐大 1 KB,而機身寫檔器是固定長度。出路未定:壓縮幀改寫較短的 MakerNote?讓寫檔器對壓縮幀用不同表頭長度? [P] |
| 5 | **那 2.18 ms 花在哪** | 反編未見顯式 sleep,但 MMIO/clock transition/IRQ 喚醒都未排除。要拆成「踢之前/踢之後」得在 `FUN_c062f6f8` 的 **Thumb** BL 上插時戳。若是可重疊的踢後等待,非阻塞收尾才可能藏掉 [P];即使如此也救不了 OG3K 30p 進 SD |
| 6 | hook 裡阻塞 14 ms(FHD)/ 34 ms(OG3K)會不會擠爆 writer | **靜態已答**:目前同一 worker 依序 encode→同步 SD flush→下一幀,必須把時間相加。`cine_log.txt` 只再量固定開銷/backlog,不是驗證現架構能否重疊 |
| 7 | 爭用的真實幅度 | 目前的 +17% 來自 L 尺寸連拍(每幀寫 25 MB)。錄影時寫入是持續滿載,數字可能不同 [P] |
| 8 | 回放/NLE 吃不吃壓縮或混合序列 | **機內影片回放靜態分析已否定原樣支援 tiled Compression=7**(§14.10);NLE 與混合序列仍要實測 [P]。未通過前只能 REC 前整段 fail-open,不能依賴逐幀 raw fallback |
| 9 | **正確曝光下的高 ISO 壓縮比** | 快門與光圈**從主機寫不進去**(`SetShutterSpeed`/`SetFnum` 只讀不寫),固定快門掃 ISO 等於在掃曝光。要補這條曲線得在相機上逐點調曝光 [P] |
| 10 | 輸出大於未壓縮或 runtime encode 失敗怎麼辦 | REC 前 preflight 失敗→整段維持 `Compression=1`;開始寫壓縮序列後先停止/報錯並 sticky-disable。只有混合序列通過 NLE 矩陣後才允許逐幀 raw fallback,且連錯/backlog 要有 circuit breaker |

**標準 predictor 1 的四點成本模型已完成。** 但在產品順序上,回放格式閘門現在先於錄影
wrapper。REC 前失敗整段保持原樣;runtime 失敗在混合序列驗證前不能擅自插入 raw 幀。
OG3K 18/24 必須排在非同步 pipeline 之後;動態抽幀另受 §14.10 的時間軸限制。

## 14. 優化審查(2026-09-15,純離線)

### 14.1 先把「最快」與「最省卡」拆成兩個 profile [M/I]

最新成本函數的每個額外 tile 等價於 **8,261 個補滿像素**;多一次 codec 呼叫則等價於
0.440 Mpix 或 53.24 個 tile。因此一幀應維持**一次呼叫、uniform tiles**,不要為了修邊緣
拆成多次呼叫。

| 格式 | latency profile | storage profile | 取捨 |
|---|---|---|---|
| FHD | **512×368**,12 tiles,13.872 ms | 288×368,21 tiles,14.065 ms | storage 版約小 1%,但多 0.193 ms;首版仍用 latency 版 |
| OG3K | 512×512,24 tiles,34.332 ms | **512×336**,36 tiles,34.336 ms | 只多 4.1 µs,實幀小 1.4–4.0%;未來 pipeline/低 fps 才用 storage 版 |
| UHD | **480×432**,40 tiles,44.910 ms | 同左 | 3840×2160 正好整除,沒有取捨 |
| 6K | 512×512,96 tiles,130.790 ms | 512×368,132 tiles,130.802 ms | 幾乎同速;但不是即時錄影候選 |

`tileplan.py` 先前仍用舊的 169.7 Mpix/s 且只按 padding 排序,會把已被 §8 推翻的解再報一次。
現在已改成 `2,179 + 4,954.40×Mpix + 40.926×tiles` 排序,`cost` 的時間欄也走同一公式。

### 14.2 優化邊界在 worker 架構,不是再榨 0.5 ms [C/I]

`0xC0722AFC` 的 blocking encode 與 `FUN_c069ade0` SD flush 在同一 queue worker、同一
call stack;handler 返回後才 dequeue 下一幀。V5.02 SD backend 也會等 completion bit 才返回。
因此現架構的吞吐是 **Tencode + Twrite + overhead**,§9 的實幀預算已排除 FHD50 與
OG3K 18/24。28-frame ring 只延後爆滿。

只有另建非阻塞 codec + 獨立 storage worker/queue,才可把穩態下限改成
`max(Tencode,Twrite)`。到那時,以下才是候選篩選表;SD 欄是像素 payload 所需最低壓縮比,
94 MB/s 來自 50 MB benchmark、66 MB/s 來自同卡 10 MB benchmark:

| 模式 | fps | engine duty | +17% | SD 最低比 @94 / @66 MB/s |
|---|---:|---:|---:|---:|
| FHD | 29.97 | 41.6% | 48.6% | 1.04 / 1.49 |
| FHD | 50 | 69.4% | 81.2% | 1.76 / 2.55 |
| FHD | 59.94 | 83.2% | 97.3% | 2.13 / 3.10 |
| OG3K | 18.002 | 61.8% | 72.3% | 1.77 / 2.54 |
| OG3K | 23.976 | 82.3% | 96.3% | 2.37 / 3.41 |
| OG3K | 25 | 85.8% | 100.4% | 2.48 / 3.56 |
| OG3K | 29.97 | 102.9% | 120.4% | 2.98 / 4.29 |

⇒ pipeline 重寫後才把 **FHD50** 與 **OG3K 18.002p / 512×336** 列為下一批候選;
而且必須先證明 `cam_is_bulk_write` / Custom 能跨幀聚合,或該卡的小檔曲線也夠快。
FHD59.94 / OG3K23.976 的 contention 餘裕太薄。`cine_log.txt` 的 request/finish 可量 backlog
與固定開銷,但短片被 ring 撐住仍不代表可持續。

### 14.3 `0x1806` 不要求最後一段 512-byte 對齊 [C/M]

再讀一次 `FUN_c069ad80` 後發現先前的「逐 segment 全檢查」判讀過嚴。當 writer 的
aligned-mode flag 已啟用時,它的迴圈條件是
`while (node->next != NULL)`:只檢查**非末段**的 `length & 0x1ff`,最後一段刻意不檢查。
因此現行每幀只有一個完整 DNG segment 時,不論壓縮後總長是否為 512 倍數都會選 `0x1806`。

零拷貝拆成兩段時也剛好符合這個規則:

1. 第一段 header 長 78,848 bytes = 154×512,通過檢查。
2. 最後一段 lossless JPEG payload 保留**真實長度**,不必補 512。
3. `TileByteCounts` 同樣保留各 tile 真實長度;只需確保 segment 的排序鍵讓 payload 在最後。

主機端仍保留 `mkcompressed.py --file-align 512` 作讀取器相容性/尾端容忍度測試;實測補尾的
FHD 檔可 bit-exact 解開。但照目前反編,**機身 writer 不需要這個 padding**,也不應為它多寫資料。

### 14.4 Writer wrapper 與 scratch 壽命（2026-09-23 訂正）[L/C/P]

比全域 hook `0xC0722AFC` 更窄也更安全的位置是 `0xC03A5490: BL FUN_c069ade0`。
到這裡 movie-DNG 的 writer list 已完整建立;wrapper 可以先驗證、encode、commit 表頭/list,
呼叫原 flush。**原先「返回即可重用 scratch」推論撤回**：G3 的 call 僅 372 µs，G5 共用
單 arena 的多幀輸出產生重複內容；尚未找到最後讀者 fence。`FileSplitWriter` 的多 segment
支援不等於兩段 layout 已 live 驗證。早期 proposal 為:

```
segment 0   自有 expanded header 79,872 bytes（不可覆寫 MakerNote 零區）
segment 1   codec scratch 的 compressed bitstream(真實長度、排在最後)
```

這能少掉約 **75 MB/s(FHD30)** / **161 MB/s(OG3K24)** 的 memcpy DRAM 讀+寫流量。
目前 G4 實際成功的是一個 contiguous node：79,872-byte header + payload。每個 output 必須
保留到可關聯的最後讀者 release，不能按 flush return 或固定 sleep 回收。需要幾個 slots 由
hold time 與 allocator 決定，不能先宣稱一個／兩個足夠。SD 契約也不能外推到 SSD。
完整規格見 [`BUFFER_DESIGN.md`](../../../projects/lossless-sup/notes/BUFFER_DESIGN.md)。

wrapper 仍必須只接受精確形狀:`count==1`、node 位於 writer 內建 arena 且 16-byte 對齊、
`next==NULL`、`kind==2`、ptr/len/模式/尺寸/`StripOffsets` 全吻合。把原 node 改成 header,
再以同 `kind=2` stable-append scratch 是兩段替代方案；首版優先沿用已驗證的 single-node layout。

### 14.5 表頭空間要找「未引用區」,不是只找零 [C/M]

原本 `largest_zero_run()` 只看 byte 是否為 0。某個合法 metadata value 若剛好整段為零,
也可能被誤認成 padding。既有 `mkcompressed.py` 排除 IFD0 與直接 out-of-line values,
但**尚未遞迴保護 Exif/MakerNote**;它找到的 3,326–3,410 B gap 不代表安全可寫。

**2026-09-15,四個 FHD 實檔補驗 [M]:** Exif MakerNote 的宣告範圍為
`[17684,72022)`;舊工具選用的零區落在其中,四檔全部被新增預檢拒絕,沒有呼叫 encoder。
完整保護 root/nested IFD 及其 out-of-line values 後,最大合法零區只有
`[78756,78848)` 的 **92 B**;512×368 / 12 tiles 所需新 IFD 與兩個陣列為 **810 B**。
所以不能再把原 gap 當作固定 78,848 B 表頭內可用空間的證據。

獨立的主機試驗改為保留原表頭(只更新 offset 4 的 root pointer),將新 IFD/table
追加於 `78848`,compressed stream 從 `79872` 開始,表頭增加 **1024 B**。
四檔經 LibRaw 解碼各 **2,110,240** 個樣本完全相同,原 root IFD、非 layout tags、
nested metadata 與其餘舊表頭 bytes 不變。這是像素無損,不是原始整檔 byte roundtrip;
stock strip 的 12 B 非像素尾端不作為影像編碼。
這個主機格式驗證**不表示原機內固定表頭 writer 已支援擴充**,也不是機內回放或速度證明。
試驗工具與逐檔證據放在 `projects/lossless-sup`;舊研究 builder 保持原樣供比較。

機身版要再嚴一層:只接受已知的 58-tag / `StripOffsets=78848` 形狀,遞迴保護所有 IFD、
SubIFD、Exif/GPS IFD 與被引用區間;任何長度、重疊、零區或 scratch guard 不合就在
第一次 commit 前停用該 clip 的壓縮,整段維持 `Compression=1`。新 IFD 與兩個陣列全部寫好後,
做 memory barrier 與必要的 data-cache clean,
確保 codec/SD DMA 可見;**最後一筆**才改檔頭 offset 4,再於 writer enqueue 前同步一次。
copy-back 與零拷貝兩路都必須遵守同一套 cache coherency 順序。

### 14.6 predictor 5 有收益,但不能當成 0x300D 已支援 [M/P]

`FUN_c062fff8` 目前固定把 `0x300D0058` 寫成 `...|0x101`,實檔 SOS 是 predictor 1;
公開的 init/enc struct 沒有 predictor 欄。低位是否真是 selector 仍未證實。

主機端已把 SOF3 encoder/decoder 擴成 predictor 1..7,並實際做出 predictor 5 DNG:

| 素材 | tile | predictor 1 DNG bytes | predictor 5 DNG bytes | 差 |
|---|---|---:|---:|---:|
| FHD f07 | 512×368 | 1,260,513 B | 1,170,946 B | −7.1%(純 bitstream 約 −7.5%) |
| OG3K f07 | 512×336 | 3,356,188 B | 3,258,565 B | −2.9% |

兩份都經 LibRaw 逐樣本 bit-exact、ExifTool 無新增警告。但 14-bit 實拍照片上 predictor 5
反而比 predictor 1 大 0.2–1.3%,所以它是**內容相依**的,不能硬切。若日後證明 MMIO 可選,
先用稀疏殘差估計器在 P1/P5 間選擇;不要每幀編兩次。第一次上機只改一張靜態照片的 selector,
讀回 SOS 與 size table,不直接進錄影。

### 14.7 非 16 倍數 TileLength:相容性實驗,不是預設 [M/P]

靜態反編只看到韌體參數檢查要求 tileH 為偶數;**0x300D 是否真的接受非 16 倍數仍待上機**。
主機 encoder 做出的 512×364(FHD)與 512×504(OG3K)可被 LibRaw 逐樣本相同解開,
時間模型分別再省 0.122 / 0.487 ms。但
[TIFF 6.0 §15 p.67](https://www.itu.int/itudoc/itu-t/com16/tiff-fx/docs/tiff6.pdf)明文要求
`TileLength` 為 16 的倍數。OG3K 512×504 仍是 33.845 ms,離 29.97p 的 33.367 ms
還差 0.478 ms。

⇒ 這只能放在「需 Resolve/Adobe/其他 NLE 完整矩陣」的 compatibility 實驗開關;
標準相容預設維持 512×368 / 512×336 / 480×432。0.5 ms 不值得換一個非標準 DNG。

### 14.8 熱重開時所有 runtime state 都要失效 [C/I]

先前 gyro 的暖重開故障不是演算法問題,而是 cave RAM 留著上一輪 allocator pointer,
開機碼只看「非零」就誤判 buffer 仍有效。機身壓縮不能重演同一種生命週期錯誤:

- 每次 loader 啟動先清 scratch/output-pool pointer、busy/completion 狀態與 header-gap 快取;
- 每次重新配置並驗證容量與 512-byte 對齊,不能把 cave 裡的非零地址當成有效 allocation;
- hook 最後才掛;配置或檢查失敗就維持原 writer,不要留下半安裝狀態;
- clip 結束或錯誤時只在 writer completion 後釋放 output slot,暖重開則把舊 queue 全部視為失效。

固定地址的程式碼/row patch 與 allocator-owned buffer 是兩回事;需要重置的是跨開機會失真的
runtime ownership。這項可先做成純記憶體單元測試,實機則要另外驗證冷開、選單 reboot 與連續兩段 REC。

### 14.9 codec 失敗必須 stage-aware unwind,不能下一幀盲重試 [C/P]

`FUN_c062f6f8` 的參數、busy/wait、跨 stripe 等多條失敗路徑會直接 return,未必走正常 teardown;
bring-up 本身也可能只拿到部分 power/clock/IRQ 後失敗。首版 wrapper 不能把原函式的 error
return 當成「引擎已恢復 idle」。

安全順序應是:

1. encode 前做 atomic try-lock、engine-idle、單 stripe、全部幾何/容量/guard 與 writer/header preflight。
2. 每拿到一個 resource 就記 stage;失敗時依相反順序做對應 unwind,並把壓縮設為 sticky-disabled。
3. header/list commit 前失敗且本 clip **尚未寫入任何壓縮幀**,writer 保持原樣、把整段鎖定為
   raw 後呼叫原 flush;若先前已有壓縮幀,則停止/報錯,不能在中途插入 raw 幀。
4. commit 後、flush 前失敗也只在「壓縮幀計數為 0」時可 rollback/cache clean 後把整段轉 raw;
   一旦已有壓縮幀或 SD flush 已開始並回錯,不可補寫 raw(前一筆也可能已部分落卡),
   只能保留原錯誤、清 RAM state 並停止/報錯。
5. 在混合 Compression 序列通過 NLE 測試前,runtime codec 失敗不做逐幀 fallback;
   連續錯誤或 backlog 超閾值也應觸發 circuit breaker,避免每幀先浪費 14 ms 再失敗。

### 14.10 機內回放與動態抽幀是兩個獨立的格式問題 [C/I/P]

V5.02 的靜態 DNG 顯影路徑在 `0xC03C8350` 有 `Compression=7` 的硬體 LJPEG 解碼分支,
但 **CinemaDngPlay 不是走這條路**。影片回放解析器 `FUN_c05c1880` 讀
`StripOffsets(0x111)`,沒有讀 `TileOffsets(0x144)`;`FUN_c05c1a58` 也沒有讀
`Compression(0x103)`、`TileWidth/TileLength(0x142/0x143)`、
`TileOffsets/TileByteCounts(0x144/0x145)`。因此主機端已驗證合法的 tiled
`Compression=7` DNG,**不能假設放回相機就會由影片播放器解碼**。[C]

影片回放也不是要求每幀檔案等大。`0xC05C0E90..0xC05C0EA0` 先以 descriptor `+0x18`
作讀取容量,`0xC05C0EA4..0xC05C0EB0` 在實際長度 `+0x1C == capacity` 時 assert;
`actual < capacity` 可接受。這個共用 capacity 由第一個被選取影格的檔案大小向上對齊導出,
所以壓縮後大小可變,但後續影格都必須小於第一幀建立的容量。這不是可靠的最壞情況保證;
若要沿用原播放器,REC 前需保守配置上界,不能拿第一幀的壓縮大小當上界。[C/I]

動態抽幀則是另一層問題:

- 仍把寫出的檔案連續編號:播放器會按固定 fps 播放,被抽掉的時間消失,動作加速且節奏跳變。
- 保留原 frame number 造成檔號缺口:播放器是否停止、跳過或報錯尚未驗證,不能當協定。
- 重複上一幀維持 cadence:能保時間,但若仍要寫完整 DNG,就失去主要的 I/O 降載收益。
- 真正保留拍攝時間需要每幀 timestamp/duration、VFR index 或 sidecar,也需要播放器理解;
  現有「一串固定 fps DNG」沒有這個語意。[I/P]

因此動態抽幀不能藏成透明的壓縮細節。較安全的產品分法只有三種:整段固定低一級 fps、
壓縮片標記為只能匯出並附 sidecar 時間軸,或另做能理解 VFR/代理影像的回放層。
在其中一條完成前,本支線維持研究 probe,不升為預設錄影功能。

## 15. 旁邊那條實作線(2026-09-16)

編碼器這一側(本文)之外,`fpLossless` 正在把「無損壓縮 OFF/ON」做成 CINE 選單第四列:

```
fpSup/lossless/            實作原始碼:control / ui_control / binding / loader / menu / native
projects/lossless-sup/     整合筆記、測試證據、host trial 工具
    notes/ROADMAP.md                當前產品狀態、架構、證據訂正與研究閘門
    notes/IMPLEMENTATION.md         逐日歷史實作紀錄
    notes/NATIVE_ROW_DONOR.md        選單列的 donor 結構
    notes/FIXED_POPUP.md             固定寬度 popup 的取捨
    tools/mkcompressed_safe.py       §6 訂正裡那個安全版建置器
    tools/tiff_guard.py              算出完整受保護範圍的 TIFF 守衛
```

分工是它自己宣告的:**通用 codec 研究留在 `research/slimRAW` 與 `research/imaging-hw`
(也就是本文),整合證據與產品決策在 `projects/lossless-sup`。**

它已經採用本文 §8 的結果當第一個目標 —— FHD 1936×1090 RAW12 / 24000/1001 / SD、
predictor 1、**512×368 tiles**。四張真實幀的 host trial 得到 **2.32–2.57:1**,
與 §10 由引擎 size table 量到的 2.525 一致(§6 訂正有表)。

那條線仍沒有 AutoRun、VSHL 或可安裝產物，`ON` 在真機上不可用；但 2026-09-21 已新增
movie-path 單幀 encode-to-RAM 與 8-frame short-burst 實機證據。compressed writer／寫卡、
正式 512×368、最壞容量、長跑與回放仍未成立，現況以 project roadmap 為準。
`fpSup/raw/lossless_codec/` 比 `research/imaging-hw/fhd_compression/` 新
—— 後者是舊鏡像,預設路徑在重整後已經失效。

## 工具

同層的檔案,都不需要相機:

```
tiff.py         最小 TIFF/DNG IFD 解析
ljpeg.py        lossless JPEG (SOF3) 解碼器 —— predictor 1..7,把輸出解回像素
ljenc.py        lossless JPEG 編碼器 —— 預設照引擎 P1;P2..P7 只供主機研究
ljcost.py       12-bit 打包解讀 + 逐 tile / predictor 成本模型(一般 tile 0.2–0.5%,角落可到 2.6%)
tilegeom.py     引擎的邊緣補滿規則 + 補滿後成本
tileplan.py     驅動:最新實測時間模型的 geom / cost <DNG> / engine <DNG>
mkcompressed.py 端到端:未壓縮 CinemaDNG -> Compression=7;可測 predictor/512B 尾端對齊
                ⚠️ 它的原地手術會寫進 SIGMA MakerNote(§6 訂正)。要保留中繼資料
                請用 projects/lossless-sup/tools/mkcompressed_safe.py;本檔保留未改作對照
```

上機的部分在 `fpSup/raw/`(需要 USB shell):

```
ljtime.S / ljtime_deploy.py   單張計時(本輪加了 tileW/tileH/位元深度欄位)
ljburst.S / ljburst_deploy.py 連拍計時 —— 每幀 t0/t1,看幀間間隔與 duty
ljtile.S / ljtile_run.py      覆寫 tileW/tileH,把每-tile 成本從每像素成本分離
```

`ljtile.S` 的 `cbytes` 加總已補上大端序 `rev`;更正前的舊 `cbytes` log 不可用,但 t0/t1
計時完全不受影響。新的 probe 必須先離線 assemble 通過,再依下述相機流程驗證。

⚠️ 三者都 hook `0xC037E7AC` 的 `bl FUN_c05a6920`,**不 cold-call 引擎**。
探針碼放 `0xC072FB00`、結果放 `0xC072FC00` —— 避開陀螺儀 logger(`0xC072E064..EFAC`)
與 open gate rowpatch(`0xC072F800..F8E8`),裝之前先 `--survey` 確認是零。
armed 期間不要跑 `getfile`/`putfile` 的大量傳輸(共用 template 區)。

```sh
./tileplan.py geom                              # 各格式最佳 tile 幾何
./tileplan.py cost <未壓縮.DNG> 288 368         # 估這幀壓完多大、花多久
./tileplan.py cost <未壓縮.DNG> --predictor 5 512 368  # 主機端 P5 估算
./tileplan.py engine <Compression=7.DNG>        # 讀引擎的實際壓縮比
./mkcompressed.py in.DNG out.DNG 288 368        # 真的把它壓出來
./mkcompressed.py in.DNG out.DNG 512 368 --predictor 5 --file-align 512
```

最後一條是**主機相容性實驗**,不是「0x300D 已能用 P5」的證據。

素材用的是既有的 `projects/open-gate/captures/opengate_ev_bug_20260914/dng/`(未壓縮影片幀)與
`research/imaging-hw/color-characterisation/captures/`、`research/imx410/captures/`(引擎壓過的照片),
沒有另外複製。
