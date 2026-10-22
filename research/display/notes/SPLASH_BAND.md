# 開機橫幅:黑底色塊 + logo + 進度條 — 怎麼畫(2026-09-19,四支探針已上機)

目標:在畫面**上方**蓋一條不透明黑色橫幅,把相機自己的 UI 蓋掉,在上面放 logo
與載入進度條,取代現在的 `fpSup[###.....]040` 純文字列。

旗標:**[C]** 反編譯讀得到,**[M]** 2026-09-19 實機量到,**[P]** 還沒驗。
底下每一條結論都標了是哪一種。

---

## 0. 一句話

**主層是 1024×682 的 ARGB4444,三重緩衝,沒有調色盤;
`display osdfile` 是「把原始 ARGB4444 memcpy 到左上角」;
`offset` 參數讓同一個檔變成翻頁動畫。** 三件事都實機驗過。

---

## 1. `display osdfile` 不是 TIF 載入器,是「貼原始點陣到左上角」 [C]+[M]

handler `FUN_c03E4270` @ `0xC03E4270`:

```
display osdfile <path> (layer0-1) (MonitorNum0-1) (h) (v) (offset)
```

| 步驟 | 程式碼 |
|---|---|
| 整個檔讀進配置器緩衝 | `FUN_c001d740/7f0` + `FUN_c0366060`,**drive 固定 1**(卡;不是 SSD) |
| 取 layer | `getLayer(mgr, 0)` —— **寫死主層**;`layer0-1` 這個參數只餵給 present 的 flag |
| 取 buffer | `getBuffer` → `base = *(desc+4)`、`W = dims[0]`、`H = dims[1]`,印出 `addr 0x%08x (%04d,%04d)` |
| dst | `base` —— **永遠是左上角 (0,0),沒有 x/y 參數** |
| src | `filebuf + offset` |
| 每列 | `memcpy(dst, src, pixelsToBytes(h))`;`dst += pixelsToBytes(W)`;`src += pixelsToBytes(h)` |
| 列數 | `min(v, H)` |
| 收尾 | cache clean `FUN_c000e91c` → `commit`(+0x14)→ `FUN_c02e8a08(monTarget, desc, flag)` |

- **沒有解碼器**。help 舉例 `\SAMPLE\TEST.TIF` 只是因為 `offset` 可以跳過 TIF 檔頭。
  檔案內容必須**已經是 layer 的原生像素格式**(見 §2),一列 `h` 個像素、連續排列。
- **`h`/`v` 是來源影像的寬高(像素)**,不是位置。預設都是 300(`0xC0BB119C/11A0`)。
- **貼圖位置固定左上角** —— 蓋上方 UI 剛好,畫中間做不到(要嘛前面補整片透明列,要嘛自己寫記憶體)。
- **[M] `offset` 只動來源 → 同一個檔就是翻頁動畫**。實測:1024×64 三格接成一個檔,
  `offset = 2*1024*64*2 = 262144` 貼出第 3 格,進度條那一列剛好 800 px 填滿(= 設計值)。

---

## 2. 像素格式:**主層 ARGB4444,副層 8bpp 調色盤** [M]

| | 主層 (MainLayer, `getLayer(mgr,0)`) | 副層 (SubLayer, `getLayer(mgr,1)`) |
|---|---|---|
| 尺寸 | 1024×682 | 1024×682 |
| 每像素 | **2 bytes = ARGB4444**(`0xARGB`,高 nibble 是 alpha) | **1 byte = 調色盤索引** |
| 調色盤 | **沒有**(`display palette 1 0` 印 0 筆) | 30 筆 YUVA(`display palette 2 0`) |
| `display capture` 檔頭 | `fmtflag=0 depth=4` | `fmtflag=1 depth=8`,檔名多 `0000` |
| 誰寫進去 | `display osd` / `osdfile` / 相機自己的 OSD | `display text`、相機的彩色指示 |

證據不是推論:把一張 `display capture` 的主層當 ARGB4444 展開,渲染出來就是
CINE 待機畫面本人 —— 綠色 STBY、橘色 F2.0、白字、音量表的黃紅刻度全部正確。
直方圖也對得起來:`0xF000` 不透明黑、`0xB000` 是 OSD 底下那層半透明黑幕、
`0xFFFF` 白字、`0xF6D6` 就是那顆綠點。

> ⚠️ `research/ui/tools/render_xci.py` 把全螢幕 capture 當 L8A8 解 —— 對**圖示**沒錯
> (圖示是另一種 16bpp),對**主層 capture 是錯的**,顏色會變灰階。

**常用值**:不透明黑 `0xF000`、白 `0xFFFF`、半透明黑幕 `0xB000`、全透明 `0x0000`、
琥珀 `0xFF94`、綠 `0xF0F0`。

副層調色盤(索引 → A,Y,U,V):
`0` 全透明 · `1` 白 · **`2` 不透明黑** · `3` 紅 · `4` 綠 · `5` 藍 · `6` A=187 的黑 ·
`7` 深灰 · `8–15` 全 0 · `16–29` alpha+亮度漸層(文字反鋸齒用)。

### fill 只取低 16 bits [C]+[M]
`fill`(vtable +0x20 = `0xC0721480`)依 `layer+0x1c` 分派;fmt 1 走 `FUN_c0722490`,
`uxth` 之後 `strh`。實機:

- `display osd 1 0xff000000` → **整層變全透明**(低 16 bits 是 0)。什麼都沒發生。
- `display osd 1 0x0000f000` → **整層不透明黑**(691,936 px = `0xF000`)。

> **順帶修掉一個現成的 bug**:`build_autorun.py` 的 `FPSUP_BAR_BG` 註解寫
> 「`0xAARRGGBB` 填不透明」—— **錯的**,`0xFF000000` 什麼都不會發生。
> 要不透明得寫 `0x0000f000`。

---

## 3. 三重緩衝 [M]

連續三次 `getBuffer` 拿到三個不同的 base,而且會輪:

```
0xC6355180 → 0xC6200180 → 0xC64AA180 → (回到第一個)
```

所以:

- 任何 `display osd` / `display osdfile` **要連下三次**,三個 buffer 才都有東西,否則會閃。
  (現行 AutoRun 的三次 `display osd 1` 就是這個原因,只是當時的註解說是「開層」。)
- **自己寫像素的話,base 每次都要重新問,而且要寫三份** —— 寫死一個位址會間歇性消失。

---

## 4. 三個元素各自怎麼畫

上方 UI 實測佔 **y = 11..44**(其餘內容在 y 561..618 與 638..671),所以 `v = 56~64` 就蓋得乾淨。

### 黑底橫幅
- 只蓋上面一條:`display osdfile \FPSUP\BAND.BIN 0 0 1024 64 0`(連三次)
- 整片:`display osd 1 0x0000f000`(連三次)

### 留一塊不蓋(例:電池)—— 三個做法,只有一個成立 [M]

貼圖每一列都是從 x=0 連續複製 `h` 個像素,**中間不能跳欄**。所以「只留電池」有三條路:

| 做法 | 結果 |
|---|---|
| 那塊做成全透明(`0x0000`) | ❌ **不是保留,是擦掉**。原本相機畫在那裡的電池被寫成透明就沒了 |
| 貼完等相機自己重畫 | ❌ 三個 buffer 的重畫不同步,畫面上電池時有時無 |
| **把相機畫的電池像素烤進 band** | ✅ 每次貼圖連電池一起畫回去,三個 buffer 都有,不閃 |

第一次量的時候我以為透明洞成功了 —— 因為那張 capture 剛好抓到「相機已經重畫回來」的那個
buffer(洞內 991 個白像素),另外兩個是空的。**單張 capture 不能代表畫面**,三個 buffer 要各抓一張。

烤進去的做法:從一張乾淨的 `display capture` 取出那塊區域(電池實測 x 4..71、y 12..44,
取 x 0..79 / y 0..63),非透明的像素疊進 band。連反鋸齒都是相機自己的,所以看起來就是原生的。

兩個代價:

- **是快照**。電量刻度不會跟著變。
- **底色會交替**。相機自己重畫的那個 buffer 電池背後是透明的(看得到 live view),
  我們貼的那個是黑的 —— 除非 band 裡電池那塊的底也留透明,只放字形。

真正乾淨的解法還是 DrawingObserver:每幀在相機畫完之後補畫 band,並且避開電池那塊 ——
那樣電池是相機自己即時畫的,我們只負責蓋掉不要的部分。

### logo
和黑底**做在同一張圖裡**,主機端先算好 —— 相機這邊只有 memcpy,沒有縮放、沒有合成、沒有解碼。
**主層是 ARGB4444,所以 logo 可以全彩**(4096 色 × 16 級 alpha),不需要碰調色盤。
`display osdPalette` 只對副層有意義。

### 進度條

| 做法 | 每步成本 | 適用 |
|---|---|---|
| 同一個檔 + `offset` 翻頁 [M] | 三條 `display osdfile`(每條整檔重讀) | AutoRun 階段(那時我們的程式還沒起來) |
| 每步一個檔 | 三條指令 + 小讀 | 同上,想壓低每次的讀取量時 |
| 自己寫像素 [P] | 一次 worker 呼叫 | worker 起來之後;唯一能做平滑動畫的 |

開機時**每條 display 指令約 283 ms**(`build_autorun.py`,2026-09-18 實測),
三次一步 → 一步約 0.85 秒。步數就是開機時間的預算。

**進度條要放在最上面幾列。** 貼圖永遠從第 0 列開始,所以「只更新進度條」的成本等於
「從第 0 列到進度條底部」的列數。條放在 y44 → 每步要重貼 57 列;條放在 y0..12 → 每步 13 列,
26 KB 對 117 KB,差快五倍。logo 放在條下面,一次貼完就不用再動。

**檔案要小。** `putfile.py` 用 `mem set` 逐字搬（現行 `fpSup/fp_usb_shell/asm/putfile.S` 負責最後的寫檔），
實測 131 KB 約 40 秒、393 KB 約一分半、786 KB 超過六分鐘還沒完。
一格 1024×64 = 131 KB,所以翻頁格數乘上去很快就不能用了 —— 這也是「條放頂端」的第二個理由。

---

## 5. 層與 z-order [C]

| 指令 | 打到哪一層 |
|---|---|
| `display osdfile` | **寫死主層** |
| `display text` | **寫死副層**,矩形固定 `(0,0,0x180,0x20)`、起筆 `(0x10,0x18)`、白色、16px/字 |
| `display osd` / `osdPalette` | 跟著 `display monitor <mon> <layer>`(`FUN_c03E56D8`:idx = mon*2 + layer) |

現行 AutoRun 第 25 行 `display monitor 0 1` → 之後的 `display osd 1 <bg>` 填的是**副層**。
「黑底橫幅走主層 + 進度數字沿用 `display text`(副層)」這個分工能不能疊對,[P] 還沒驗。

---

## 6. 會被洗掉 [C]+[M]

draw thread 每個 redraw cycle 開頭 `fill()` 整層(`FUN_c0528700`→`FUN_c0528b40`),
out-of-band 畫的東西撐不過一次 GUI 重繪。實機看得到:整層填黑之後,capture 裡
已經有相機自己重畫回來的 `0xB000` 半透明黑幕與白字。

開機階段 GUI 還沒接手,所以現在的文字進度條看得到。要撐過重繪 →
註冊自己的 DrawingObserver(`FUN_c0528300`,細節在 `OSD_PERSISTENT_MARKER.md`)。

---

## 7. `display capture` 的用法(自我驗證的工具) [M]

```
display capture \FPT.XCI 1 2      # 1=主層 2=副層 3=both;0/1/2 = none/RLE/LZ4
```

- **USB 一定會回 `LIBUSB_ERROR_TIMEOUT`**,但檔案有寫成功。不要重送,`dir \` 確認就好。
- both 會多產生一個 `<名字>0000.XCI`(副層)。
- 解:`XC\0\0` 檔頭 0x20 bytes,`+0x08` w/h,`+0x2F` LZ4 block 長度,payload 從 `0x20` 起;
  主層 raw 大小 = w*h*2,副層 = w*h。
- **主層要用 ARGB4444 展開**,不是 L8A8。

---

## 8. 這次做到哪裡(2026-09-19 收工)

**成立的**:主層 ARGB4444、三重緩衝、`display osdfile` 的三個參數語意、`offset` 翻頁、
`fill` 只吃低 16 bits、整條上排 UI 蓋得掉、電池可以用「烤進 band」的方式留下。
畫面最後已清回透明(`display osd 1 0x00000000` ×3),相機沒有留下任何東西。

**沒做的**:DrawingObserver(唯一能同時做到「常駐不閃」和「電池是即時的」的解法)、
主機端的 band 產生器、把 `build_autorun.py` 的文字進度條換成貼圖版。

**踩到的坑**(已寫進 `fpSup/.claude/skills/fp-camera/SKILL.md`):
`putfile.py` 寫到一半被 `pkill` → 主機取消進行中的傳輸 → vendor 端點僵掉,
裝置還在列舉、node id 沒變,但每條指令都回 `frame0 ... moved=0/64`,重開 daemon 無效,
**要拔插 USB**(不用冷開機,worker 活著、計數器接著跑)。

**方法上的教訓**:三重緩衝之下,**單張 `display capture` 不能拿來判斷畫面**。
我就是這樣把「透明洞」誤判成成功的 —— 抓到的剛好是相機已經重畫回來的那個 buffer。
要下結論就連抓三張。

**卡上留的測試檔**(沒清):`FPBAND.BIN` `FPHOLE.BIN` `FPBAT.BIN` `FPBAND2.BIN`(不完整)、
`FPCAP0*.XCI` `FPT*.XCI` `FPU*.XCI`。

## Quick-ref
- 子指令表 `0xC0BB1410`,24 筆,stride 12:`{name, help, handler}`
- `osdfile` `0xC03E4270`、`osd` `0xC03E3D00`、`osdPalette` `0xC03E3E90`、`text` `0xC03E4620`、
  `capture` `0xC03E4AD0`、`palette` `0xC03E4D78`、`image` `0xC03E4150`(**是 live view 圖層開關,不是貼圖**)
- layer vtable:`+0x0c` surface/palette info、`+0x10` getBuffer、`+0x14` commit、`+0x18` setPalette、
  `+0x1c` clearPalette、`+0x20` fill、`+0x28` pixelsToBytes、`+0x2c` capture
- `fill` fmt 分派 `0xC0721480`;fmt1 `0xC0722490`(`uxth`+`strh`)、fmt3 `0xC07224E0`(`uxtb`)
- present `FUN_c02e8a08`、disable `FUN_c02e8e58`、monTarget `FUN_c02e44b0/d0`
