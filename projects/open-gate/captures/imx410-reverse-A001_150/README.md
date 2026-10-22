# A001_150 —— 逆向幾何鏈的實體證物

2026-09-29 01:59,相機卡上錄的。原始 clip 共 **37 格**,這裡只留第一格。
機制見 `notes/IMX410_FULL_DESIGN.md` §12.23(方向)、§12.25(欄位訂正)、
§12.27(接上)、§12.29(上機)。

## 這一格證明了什麼

**使用者只給「視野」與「想要的輸出」,旋鈕是解出來的。**

```
輸入   原始解析度 6064x3412(全開閘的窗口)
       最終裁切   3840x2160        <- 這是**輸入**,不是衍生值
解出   hbin ÷1  vbin ÷1  RWZM 1600/1600
相機   自己挑 mode 7(= 原廠 UHD30 用的那顆;A_MODE 留 0 沒有釘選)
```

## 解出來的標籤

```
NewSubfileType       0
ImageWidth           3872          = 記錄矩陣 rec
ImageLength          2182
BitsPerSample        12
Compression          1
StripOffsets         78848
StripByteCounts      12673064      ~ 3872 x 2182 x 1.5 = 12673056(+8)
BlackLevel           262160/1024
WhiteLevel           4095
DefaultCropOrigin    (16, 11)      = ((3872-3840)/2, (2182-2160)/2) 逐格置中
DefaultCropSize      (3840, 2160)  ★ 與目標一個字不差
BaselineExposure     0/1024
FrameRate            30000/1001
ExposureTime         1/60          = 29.97 的 180°
ISO                  100
```

`StripByteCounts` 比 `寬x高x1.5` 多 8 bytes。原廠也有同類餘量
(`og3k120-defect-A001_182` 是多 12),所以不是我們的問題。

## 它的另一半:B 組

逆向成立的證明是**一對**,不是一格。同一個 `3840x2160`:

```
B  視野 4176x2174  RWZM unity  rec 4176x2174  相機挑 mode 102  = 原廠 UHD30CROP
C  視野 6064x3412  RWZM 1600   rec 3872x2182  相機挑 mode 7    = 原廠 UHD30   ← 這一段
```

兩個視野、兩組旋鈕、同一個輸出 —— 正是原廠 UHD30CROP / UHD30 那一對。
B 組沒有留 DNG(它的重點是 mode 選擇,在 RECIPE 逐字比對時就驗掉了)。

## 為什麼只有 37 格

資料率:`3872 x 2182 x 12bit x 29.97 ≈ 380 MB/s`,SD 約 100 MB/s。
所以預期就是**錄一下下然後 `vbuf` 乾淨停止**(§10),不是失敗。
按一次 `MOVON/MOVOFF` 就走,`is_recording` 在 +6s 已回 0,錄完相機完全健康。

⚠ 但 §10 的模型下界是 `POOL_INFLIGHT = 94` 格,**實際只有 37**。
每格 12.75 MB 遠大於模型假設的每格約 1.02 MB 在途成本,所以這裡卡住的
大概是 RAW 區的容量而不是描述子數量。**模型對大格子高估了,這條還沒解。**

## 取檔方式

走 USB shell,不是掛卡:

```
dir \CINEMA                                    找到 A001_150
dir \CINEMA\A001_150                           拿到確切檔名(日期是 20260928,不是 0929)
getfile.py '\CINEMA\A001_150\A001_150_20260928_000001.DNG' out.DNG --size 12752384
```

12.75 MB / 1.3 s。`dir` **不支援萬用字元**(用法只吃目錄路徑),所以沒有
「部分 dir」這個選項;這段只有 37 格、listing 約 6 KB,跑完 shell 健康。
上千格的片段仍然不要 `dir`。
