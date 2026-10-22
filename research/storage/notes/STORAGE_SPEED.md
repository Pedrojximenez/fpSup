# 儲存速度:韌體自帶的跑分,與實測數字 (2026-09-13)

## 一句話

**韌體自己就有完整的儲存跑分套件(`sdcard test2..test6`、`test_rw`),會直接印
`MB/sec`,不用我們寫任何東西。** 用它量出來:**SSD 寫 390(卡在 USB 匯流排,
不是硬碟)、SD 寫 94、而 FHD 12bit 錄影要 97.2** —— 這解釋了我們追了一個月的
好幾個症狀。

---

## 1. ★ 韌體自帶的跑分 —— 不要自己寫

`sdcard`,handler `0xC040B4D0`,子指令表 `0xC0BC2660`:

```
slot        無參數 = 印目前 slot;sd0 = 記憶卡(值 1);ext = 外接儲存(值 5)
test2 [slot] [bufsize]                  (Write,Read,Diff)*offset
test3 [slot] [bufsize] [loop num]       (Write,Read)*loop          <- 用這個
test4 [slot] [bufsize]                  (Write,Read)*offset
test5 [slot] [au] [bufsize] [filename]  (Write loop, Read loop)
test_rw [slot] [bufsize]                (Write,Read,Seek,Discard,Delete)
size [slot] / fnum [slot] / checkinit [slot] / mnt [slot] / umnt [slot]
sdmode / chkop / readOnly
⚠️ format [slot]         絕對不要打
⚠️ test6 [slot] [filecount]   "Disk full",會把卡寫滿
```

**`ext` = 5 = 外接 SSD。**(slot 名稱表在 `0xC0BC1C70`,`{"sd0",1}` `{"ext",5}`)

### `test3` 拆開來看(`FUN_c0408A20`)

```
預設 bufsize = 10,000,000
緩衝來自配置器 class 10                 <- 錄影通道,不能在錄影時跑
開 \test.txt,open mode 7(可覆寫,不截斷其他檔)
FUN_c002b940() 夾住單次 write           <- 1 MHz 計數器
印 "ok %9u[us] %8.4f[MB/sec]"           <- 它自己算好
然後同樣量一次 read,再跑下一個 loop
配不到緩衝會印 "bufferSize Err" 然後繼續,不會掛
```

**印出來的 MB/sec 是 bytes/µs = 十進位 MB/s**,跟 CinemaDNG 的碼率同一把尺,
可以直接比。

### 輸出怎麼收:`ctrl mediaOut`

```
ctrl mediaOut \FPSPEED.TXT     開始把 shell 輸出導進檔案(FUN_c040BFE0)
ctrl mediaOut off              結束
```
寫到**預設 slot**,所以要先 `sdcard slot sd0`,結果檔才會落在記憶卡上。
(`test3` 的 slot 是顯式參數,不吃預設值。)

`ctrl save_log` **不是**這個 —— 它是 NAND 裡的 assert log,4 個槽位,跟 shell
輸出無關。

### 為什麼要走 AutoRun 而不是 USB shell

**USB-C 只有一個孔。SSD 插上 = host 模式 = USB shell 不能用。**
而且在指令執行到一半拔 USB,worker 正要把輸出送回 EP 0x83,那會卡住端點。

所以:`ctrl sleep <ms>`(`FUN_c040C4D8`)當插拔視窗,開機只插記憶卡,倒數期間
熱插 SSD,再 `sdcard mnt ext`。實機驗證可行(2026-09-13)。

⚠️ **`ctrl sleep` 擋住 AutoRun 執行緒 30 秒是可行的(n=1),但沒有更多樣本。**

現成的卡:`fpSup/tools/storage-benchmark/`(**沒有任何 `mem set`,不綁韌體版本**)。

---

## 2. 實測

```
                          寫         讀
SSD 2 TB,外接盒 A        390        400      50 MB 起就平
SSD 2 TB,外接盒 B        363        370      同一顆硬碟
SD 128 GB UHS-II           94        218      兩次開機重現,誤差 <1%
```

**SSD 卡在匯流排,不是硬碟。** 讀寫落差 3% 以內。USB 3.0 Gen1 = 5 Gbps
**8b/10b 編碼 = 500 MB/s 載荷**(不是 625 —— 那個數字漏掉編碼開銷),
bulk 大量儲存實務值 400~450。**換更快的硬碟不會有用;換外接盒差 7%。**

### ★ 寫入區塊大小有影響,而且不小

```
              10 MB      50 MB     100 MB
SSD            328        390        393     50 MB 起平
SD              66         94          ?     +48%,還沒看到平台
```

**一格 6K 8bit 是 24.5 MB,一格 open gate 12bit 是 9.2 MB。**
「一格一個檔」—— CinemaDNG 就是這樣 —— 讓卡永遠在這條曲線的慢端運作。
會攢大塊再寫的 writer 可能白撿一截。**SD 卡 50 MB 以上沒量過。**

---

## 3. ★ 相機實際的錄影碼率(從卡上真實檔案的 header 量的)

```
FHD  1936x1090  12bit    3,244,544 B/frame     97.2 MB/s
UHD  3856x2170   8bit    8,447,488 B/frame    253.2 MB/s
UHD  3856x2170  12bit   12,630,528 B/frame    378.5 MB/s
open gate 3032x2012 12b  9,229,824 B/frame    276.6 MB/s

DNG header 開銷 = 79,240 B(open gate)/ 79,960 B(UHD 8bit)= 約 0.9%
```

---

## 4. ★★ 這解釋了什麼

### FHD 錄影時那張卡是滿載的

```
FHD 12bit 需要   97.2 MB/s
那張卡能寫        94   MB/s
```

**差 3%,靠 RAM 緩衝墊著。** 這才是下面這些症狀的**共同根因**:

- `SD_WRITE_LATENCY_MEASURED.md` 的**錄影中最壞 692 ms 寫入延遲**
- `STREAM_DROP_INVESTIGATION.md` 的 **writer(優先權 28)搶不到卡鎖**
- 陀螺樣本被擠掉

不是排程問題,不是優先權問題 —— **是卡在錄 FHD 時根本沒有閒的時候。**
換一張快的卡,這幾個問題會一起變輕。

### open gate 片段停在 3~4 秒不是 bug

卡上 31 段 open gate(3032×2012 12bit = **276.6 MB/s**)全部 ≤ 4.1 秒。
對上 94 MB/s 的卡,緩衝以 **182 MB/s** 的赤字被吃掉;由片長反推
**錄影緩衝約 600~750 MB**。

**這也順便量到了錄影 RAM 緩衝的大小**,那是以前沒有數字的東西。

---

## 5. ★ 訂正:8bit CinemaDNG **有** LinearizationTable

以前記過「fp 的 DNG 有 58 個 tag,不含 `LinearizationTable`(50712)」。
**那只對 12bit 成立。**

```
12bit 檔案   58 個 tag,沒有 50712
 8bit 檔案   59 個 tag,多的就是 50712
```

`3856×2170`、`BitsPerSample=8`、`Compression=1` 的實際內容:

```
tag 50712  type SHORT  count 256   8bit code -> 12bit level
  code   0- 32   每個 code  8.5 階
  code  32- 64             4.0        <- 暗部細
  code  64-128             5.75
  code 128-192            16.0
  code 192-255            36.6        <- 亮部粗
  單調遞增,0 -> 4095,WhiteLevel 仍是 4095
```

**分段線性的 log 曲線,走 DNG 標準自己的機制。** 也就是說:
**8bit RAW 的 companding 是出廠韌體就解決好的問題,不需要我們發明。**

---

## 6. 兩個媒體是獨立的

```
SD     XC_MediaDriverSdcard,鎖在 0xC351EE18 (+0x3C)
SSD    USB host 大量儲存(MscHost;shell 有 usb hmsc / usb mc)
```

不同驅動、不同鎖、不同控制器,**沒有共用寫入隊列**
(這點在追漏幀時就確認過了,見 `STREAM_DROP_INVESTIGATION.md`)。
所以頻寬**可以預期相加**。

⚠️ **假設,未驗證:它們真的會相加。** 兩者是**分開量**的;同時寫要共用 DRAM
頻寬與 CPU。

---

## 7. 還沒量的

1. **SD 卡 50 MB 以上的區塊。** 曲線還在往上,而且這是免費的。
2. **好一點的卡能到多少。** 讀 218 證明控制器是 UHS-II,慢的是卡本身。
   UHS-II HD312 的理論值是 312。
3. **相加性。**(第 6 節)
4. **`test5` 的 `[au]` 參數是什麼。** 看起來是配置單元,沒追。

---

## 相關

- `fpSup/projects/6k-to-ssd.md` —— 這些數字撐起來的設計
- `fpSup/tools/storage-benchmark/` —— 可以發給網友的測速卡
- `notes/research/storage/SD_WRITE_LATENCY_MEASURED.md` —— 692 ms 的症狀,根因在本文 §4
- `notes/projects/gyro-sup/../../../projects/gyro-sup/notes/STREAM_DROP_INVESTIGATION.md` —— 卡鎖爭用,根因同上
- `notes/projects/usb-shell-sup/../../../projects/usb-shell-sup/notes/SHELL_COMMANDS.md` —— 韌體 shell 的 77 條指令表
