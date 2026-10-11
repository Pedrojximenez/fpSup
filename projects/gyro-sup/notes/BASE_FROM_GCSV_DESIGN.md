# base 由 gcsv 參數化產生 —— 設計(定案)

2026-09-20。尚未實作。**本文件取代同名的第一版**,那一版把 `decode.py` 的
GFS6 當成現行格式,推導出來的東西大半是錯的 —— 見 §6。

## 0. 為什麼

base 是獨立的 `ring_task.S`,所以**沒有人改它**。2026-09-19 修好 gcsv 的
profile 尺寸之後,base 仍把選單尺寸寫進檔頭,open gate 下是錯的。
**一份修正,只修好一半的產品。**

一份原始碼、一個參數,下一個修正才會自動到齊。

## 1. 現狀:base 已經是零拷貝

```
ring_task.inc.S:224   0x00 "GFS7"  0x04 version  0x08 period_ps  0x0C gscale
                      0x10 orient  0x14 clip(8)  0x1C volume
                      0x20 payload 0x24 dropped  0x28 mode  0x2C exposure_us
                      0x30 width   0x34 height
                      HDR_BYTES = 64,之後是 8 B 記錄
```

記錄形狀(`imu_stream.inc.S`):

```
 0 i16 x   2 i16 y   4 i16 tag(0=陀螺 1=加速度)   6 i16 z
```

> One ordered stream, one record shape. 「The payload here goes to the card
> exactly as the producers left it.」

**所以零拷貝、無區塊檔頭、無 CRC、無 footer、無 96 B 鏡頭區 —— 全部已經成立。**
時間靠位置:tag 0 前進 400.0854 us,tag 1 不前進。

## 2. 差異只剩三項

| | base 現況 | 要變成 |
|---|---|---|
| 位置 | `\GYRO\A001_037.GYR`,**要使用者自己建資料夾** | 根目錄 |
| 鏡頭 | 無,靠下游自己算(缺焦距與畸變) | `\A001_037.json`,與 gcsv 同一個產生器 |
| 檔頭 | 64 B,寬高是選單尺寸(OG3K 下錯) | 20 B,只留解讀所需 |

資料本身**一個位元組都不用動**。

## 3. 定案

### (a) 根目錄

使用者:「一堆人忘記放資料夾跟我說沒看到,生資料夾又可能有更多風險」。
現行 base README 要求使用者自建 `\GYRO\` 且明說不代建;而**錄影開始時建目錄,
每一次 SSD take 都凍結相機**(`gcsv_task.S:clip_path`)。

不是新功能:gcsv 的階梯 Rung 1 就是根目錄(`G_FALLBACK != 0` 時只寫一個 `\`)。
**base = 從 Rung 1 起跳。**

### (b) 鏡頭走 json,而且只有一種 json

使用者:「不要有不同版本的 JSON」。所以 `.json` 就是 Gyroflow 的 lens profile,
**兩個 edition 逐欄相同,不加任何自訂欄位**。

自訂欄位一度被提議(把三個比例塞進去),**否決**:那是別人的格式,
Gyroflow 的解析器是不是嚴格模式我們沒查證過,而賭贏也只省二十個位元組。
解讀 `.GYR` 所需的東西放回 `.GYR` 自己的檔頭。

### (c) 20 B 檔頭,magic 用雜湊

```
0x00  magic        0x9F5BEB0D
0x04  period_ps    400085400
0x08  gscale       0.000137923f
0x0C  ascale       0.0009765625f
0x10  orient       0x007A7978   "xyz",三軸全負
                   之後全是 8 B 記錄
```

magic 是格式規格字串的 SHA-256 前四位元組(小端):

```
fpSup gyro stream: le; hdr magic,period_ps,gscale,ascale,orient; rec i16 x,y,tag,z
```

可重現、有來源,而且與 `GFS7`/`GFS6`/`GFB6`/`GFM6`/`GFE6`/`VBIN`/`LDAT` 都不撞。

**為什麼用雜湊而不是遞增版本號**(使用者):「不然要一直更新網頁很麻煩」。
檔頭已自我描述,校正值改了就改檔頭裡的值,magic 不動,轉檔器不必維護版本表。
**只有佈局改變才換 magic** —— 換時重算規格字串的雜湊。

`orient` 一度差點被漏掉。它和那三個比例是同一類:**解讀資料所必需**,
不是中繼資料。丟掉它,轉檔器就得把軸向寫死,跟把 `0.0004000854` 寫死一樣脆 ——
而後者正是已經修過一次的 bug(舊檔頭用整數 400 us,四十秒漂 3.4 ms)。

被丟掉的欄位,以及它們去哪:

| 欄位 | 去處 |
|---|---|
| clip id | 檔名 |
| volume / payload | 診斷用;檔案大小即 payload |
| dropped | 完整性追蹤歸 hdmi-raw(使用者決定) |
| mode / width / height | `.json` |
| exposure_us | **無處可去,待決** |

### (d) 下游

`decode.py`(停在 GFS6)與現行網頁轉換器**一起退役**,新的線上轉檔器是唯一消費者。
所以 `.GYR` 的格式現在沒有任何東西釘住,是改檔頭的時機。

## 4. 參數化的形狀

一份 task 原始碼,`FPGYRO_EDITION_BASE` 決定:

```
路徑     G_FALLBACK 起始值 0 → 1
檔頭     20 B 二進位  vs  gcsv 的文字頭
資料     記錄直寫     vs  gcsv_rows 轉文字
json     兩邊都做,同一份產生器,同一種格式
```

`build_base_card.py` 的 `EDITIONS` 由「兩個檔名」變成「同一個檔名 + 一組 defines」。

## 5. 必須重驗

base 的 payload 會整個換掉。這是重做,不是修補:

- 根目錄產出 `\A001_037.GYR` 與 `\A001_037.json`,不需要任何資料夾
- OG3K take 的 `.json` 是 3024x2010(這件事的起點)
- 新轉檔器讀得動 20 B 檔頭 + 8 B 記錄流
- 重驗時會撞見啟動器那條線:`logger.S` 4032 B 對上 3920 B 額度,
  `test_safety.py` 三條紅著。與本設計無關但擋路。
- README 改寫:不再需要建 `\GYRO\`

## 6. 第一版錯在哪(留著當教訓)

第一版拿 `decode.py` 當現行格式的權威,於是推導出「要不要保留區塊檔頭 / CRC /
footer / 96 B 鏡頭區」這一整串問題 —— **而那些在 v7 早就都沒有了**。
`decode.py` 的 docstring 第一行就寫著「Validate GFS6/GFB6」,我沒讀。

同一種錯這個 session 犯了四次(`0xC38250E4`、`FUN_c0021c40` 傳 null、
`kind=2`、這次),共通點都是**把一個看起來合理的來源當成已經證實的來源**。
每一次都是使用者反問才停下來。
