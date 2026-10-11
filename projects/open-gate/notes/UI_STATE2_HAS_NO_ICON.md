# OG3K UI:原廠狀態 2 缺少完整資源狀態

日期 2026-09-14。用全量反編譯 + 資源池偏移交叉引用查出來的,尚未上機驗證的部分會標明。

> **最新校正（第十輪，實機）:**本筆記保留了調查過程，所以早期 §3、§5、H.5 的
> 「直接索引陣列 / last terminator / 狀態 2 越界」是已撤回的心智模型。
> 原生格式其實是時間曲線；可執行結論以 §AA–§AE 為準。真正缺的是 controller
> 上限、group endpoint、time-66 的全套 companion keys、footer/cursor 與三種
> 尺寸的私有圖資，不是只在 image array 後面補一格。目前 CINE 的 Settings、
> QS 大小圖與三格 footer 已冷開實機通過；其他 style/回歸仍未驗。

## 0. 先撤回 FORMAT_REGISTRY_DESIGN.md §24 的一句話

§24 寫:

> 這張表是跟著 CSV 的列數建出來的 —— 我們加了第三列,它自己就多了第三筆。

**錯。** 那張表是原廠 ROM 常數,筆數寫死在程式碼裡:

```c
/* MenuValueConverterBase__v21 @ 0xC06BDA30 */
undefined4 MenuValueConverterBase__v21(undefined4 param_1, undefined4 *param_2) {
    *param_2 = &DAT_c2e4020c;
    return 3;                      /* ← 筆數 3,寫死 */
}
```

ROM 內容(0xC2E4020C 起,{key,value} 配對):

```
{3, 0}   enum 3 → 狀態 0
{2, 1}   enum 2 → 狀態 1
{4, 2}   enum 4 → 狀態 2      ← 原廠就有,不是我們加的
```

**原廠 SIGMA 本來就定義了第三個影片解析度 enum 4 → 顯示狀態 2。**
(推測是共用碼庫裡的 DCI 4K,fp 機身用不到。)

我們加 CSV 第三列時,只是讓 enum 4 變得可以被選到,並沒有創造狀態 2。

這條修正很重要:它把問題從「我們做了越界的事」變成「原廠留了一個沒接完的狀態」。

## 1. 呼叫鏈

```
XC_GuiStandbyCineMenuNotifier_w71c1__v59 @ 0xC059C640
    uVar1 = FUN_c06bd988(obj[1], enum);         /* enum → 顯示狀態 */
    FUN_c0593f30(obj, "LV_Resolution", uVar1);  /* 以字串鍵發佈狀態 */

FUN_c06bd988 @ 0xC06BD988
    (*vtable+0x5C)(obj, &table)  →  MenuValueConverterBase__v21  → (0xC2E4020C, 3)
    FUN_c06ccd10(enum, table, 3, 0)             /* 線性配對查表,預設 0 */
```

`LV_Resolution` 只有兩個發佈者(Cine 與 StillLike 的 v59),沒有任何程式碼消費它 ——
消費端是資源層,用字串鍵在執行期查,所以 xref 查不到。

## 2. UI 綁定層是 Lua

韌體裡內嵌 Lua 腳本,例如 HDMI 輸出格式那一段:

```lua
string.format("%s",(function(prefix,suffix,a,b,c,d)
  local ssa = {"<!font_G_HDMIfmt_raw,CENTER>", ""}
  local ssb = {"DCI 4K ", "UHD ", "FHD "}
  local ssc = {"23.98 fps", ... , "119.88 fps"}
  return ssa[a+1] .. ssb[b+1] .. ssc[c+1]
end)("<!font_M_",",CENTER>", MV_OutputSignal:v(), MV_OutputResolution:v(), ...))
```

要點:

- `<!資源名,CENTER>` 是**把圖示嵌進文字**的指令,全韌體有 305 種
- 狀態值是用 `KEY:v()` 取的,條件式語言支援 `and` / `or` / `==`
- **文字串接可以組出資源名** —— 這是比原本以為的更靈活的槓桿

但:全韌體 305 個 `<!...>` 指令裡,**沒有任何一個含 `resolution`**。
所以 QS 的 RES. 格不走 Lua 圖示名那條路。

## 3. QS 的 RES. 格怎麼選圖（早期判讀，已校正）

資源池基底 **0xC18C0474**(用三個名字驗證:`Y4_1_3_2_UHD` 偏移 0x2455C、
`_FHD` 0x2454C、`_DCI4K` 0x2453C,與舊筆記記錄的偏移完全吻合)。

以大端序 32-bit 池偏移搜尋引用:

```
qs_resolution_1_S   偏移 0x028E68   18 處引用,首處 0xC22A179F
qs_resolution_2_S   偏移 0x028E7C   18 處引用,首處 0xC22A17A9
```

兩者相距 10 bytes。當時把附近的位元組判讀成直接索引陣列:

```
0xC22A1791  00 02 71 dc   →  "image"
0xC22A179F  00 02 8e 68   →  qs_resolution_1_S   後接 00 00 00 00  (狀態 0)
0xC22A17A9  00 02 8e 7c   →  qs_resolution_2_S   後接 00 00 00 01  (狀態 1)
0xC22A17B9  00 02 4f 08   →  "color"
```

**這段「狀態 2 落在陣列外」的結論已撤回。** 十個 byte 是動畫 key:

```
flag_a:u8, flag_b:u8, time:u32 BE, value:u32 BE
```

`value` 才是圖資字串 offset；原廠兩個 key 的 `time` 是 0 / 33。
`FUN_c05e2280` 依 evaluator `+0x1C` 的浮點時間找相鄰 key，超過末 key 會夾到
末 key，不會越界。第三狀態需要把 group endpoint 延到 66，並為**每一個**
companion property 補 time-66 key；只補 image 不構成完整狀態。

(18 處引用應是 18 個語言/變體版本,間距 0x170ED。)

## 4. 資源家族的成員數:狀態 2 真的沒有圖

```
qs_resolution_1_S / 2_S                    2 個   ← QS 格
set_resolution_1 / 2                       2 個   ← 設定摘要
font_menu_MB_resolution_1 / 2              2 個   ← 選單字體
Y4_1_3_2_FHD / _UHD                        2 個(C0D4 名表)
Y4_1_3_2_DCI4K / _FHD / _UHD               3 個(C18E 名表)  ← 唯一有第三個的
M_resolution_1 / 2 / 480p / 576p / 720p / dci4K    6 個
L_resolution_1 / 2 / 480p / 576p / 720p / dci4K    6 個
```

對照:其他需要多狀態的 QS 家族都備齊了 ——
`qs_aspect` 7 個、`qs_mode` 7 個、`qs_imageSize` 3 個、`qs_iso` 43 個。
而且編號**可以不連續**(`qs_drive` 沒有 `_2`,`qs_formatQuality` 沒有 `_4`),
所以格式本身不要求連號。

**仍成立的部分:**這三個 resolution 圖資家族確實只出貨兩張，沒有第三張
OG3K 圖；但 consumer 不是依 state 直接索引。

## 5. 三個症狀都來自「第三狀態未完成」，但路徑不同

| 症狀 | 機制 |
|---|---|
| 選單收合列顯示 `3` | 獨立的 `drawText` 記錄 `0xC1A7246B` 仍是字面摘要 `3` |
| QS RES. 格亂碼 | 兩個 controller 最大值仍是 1；20/21 兩族 endpoint 只到 33，且 layout/image 等 property 都沒有 time-66 key |
| QS strip 沒有 OG3K | 共用 footer 沒有 time-700 的第三格，cursor 範圍也仍只涵蓋 UHD/FHD |

共同根因仍是:**原廠留下 enum 4 → 狀態 2 的資料路徑，卻沒有把第三狀態的
動畫、版面與圖資做完。** 修補單一 image property 不足以解決任何一族。

## 6. 可走的路(依代價排序)

1. **把 enum 4 改指到狀態 0 或 1。** §25 已實測:把 ROM 影像裡的 `{4,2}` 改成 `{4,0}`,
   摘要立刻顯示 UHD。代價:標籤是錯的(顯示 UHD 或 FHD),但畫面乾淨、不再有亂碼。
   這是唯一「今天就能做完」的選項。
2. **走 Lua 文字路徑。** `<!icon,CENTER>` 證明文字裡可以嵌圖示,且文字可由狀態組出來。
   若 RES. 格能改綁到文字屬性而非 `image` 屬性,就能用字型字符拼出 "OG3K"。
   **未驗證** —— 下一步要查的就是這個。
3. **加資源。** 就是社群做私有 NBR 資源包那條路(他們改了 380 個資源項)。
   沒有任何 hook 能變出韌體裡不存在的點陣圖。

## 7. 同時撤回我自己這一輪提出的一個想法

我先前提議「CSV 的 TEXT 欄放短數字字串 id,再 hook id→文字的解析函式,
一次解掉收合列與 QS」。**對收合列無效** —— §28 已經證明那個 `3` 來自 `NO` 欄的
`atoi`,那條路徑根本不讀 TEXT 欄。提出前沒有先讀完既有筆記。

---

# 附錄:資源系統的結構(2026-09-14 第二輪)

為了估路 3 的代價而查的。**確定的**與**只是假說的**分開寫。

## A. 確定的

**資源系統由三層組成:**

1. **排序過的字串池**,基底 `0xC18C0474`。名字、鍵、條件式全在裡面,
   NUL 結尾、4-byte 對齊、按字母排序。開頭是
   `" Default Focus Object"` / `"! SelfTimer"` / `"!= -1"` / `"!QS_QSMode"` 這類。
2. **UI 記錄大區塊**,約 `0xC1900000`–`0xC2D80000`(20 MB,熵 3.1–3.6、六成是零)。
   位元組打包,用**大端序池偏移**引用字串。
3. **內嵌 Lua**,在 `0xC2D80000` 之後的高可列印區。

**池偏移的算法驗證過**(三個名字都對):

```
名字位址 - 0xC18C0474 = 池偏移
Y4_1_3_2_UHD   0xC18E49D0 → 0x2455C   ✓ 與舊筆記吻合
Y4_1_3_2_FHD   0xC18E49C0 → 0x2454C   ✓
Y4_1_3_2_DCI4K 0xC18E49B0 → 0x2453C   ✓
```

**QS 的 RES. 格記錄**(18 份語言/變體副本,間距 0x170ED,內容相同):

```
0xC22A1791  00 02 71 dc  →  "image"
0xC22A179F  00 02 8e 68  →  qs_resolution_1_S   後接 00000000
0xC22A17A9  00 02 8e 7c  →  qs_resolution_2_S   後接 00000001
0xC22A17B9  00 02 4f 08  →  "color"
```

## B. 沒找到的:圖示的點陣資料

- 不在 UI 記錄區 —— 18 處引用 `qs_resolution_1_S` 全部是同一個 widget 的
  `image` 屬性,沒有第二種上下文
- `.xci` 路徑字串(`0xC0D40C0A` 一帶)只是**建置清單**,不是索引
- 名字表沒有任何指標或小端序偏移指向它(搜 `0x28E68` LE 與絕對位址皆 0 命中)

→ **靜態映像裡沒有可直接定位的圖示索引。**

## C. 假說(未驗證,不要拿來當前提)

`0xC0FBACE0` 有一張 **11,644 筆的遞增 u32 表**(至 `0xC0FC62D0`),
值域 `0x02D72D00` – `0x04C22800`。若加上 `0xC0000000`,範圍是
`0xC2D72D00` – `0xC4C22800` —— **起點在映像內,終點在映像結束
(`0xC2F30CCA`)之後**,也就是開機時才配置的 DRAM。

差值:開頭一段固定 256,中位數 3328,最大 27904。筆數與資源數量級相符。

**但抽查 `0xC2D72E00` 看到的是更多 UI 記錄(`00 02 4f 08` = "color"),不是點陣。**
所以這張表可能根本不是圖示索引,也可能是它但我抽錯了位置。**未證實。**

## D. 方向結論

靜態分析到此為止。要再往下必須**從執行中的相機 dump 資源記憶體**
(至少 `0xC2D72D00` 之後那一段),才能確認:

1. 圖示點陣在不在那裡、格式是什麼
2. 解析後的 `image` 陣列在 RAM 的哪裡、能不能重指到自建的三筆陣列

這需要 USB shell → 需要一張帶 shell 的開發卡。
出貨版沒有 shell(2026-09-14 實測:worker 完全不回應,不是故障)。

---

# 第三輪(2026-09-14 下午):上機量測

相機上有完整的 GUI 內省介面,這一輪全部是量測,不是推論。

## E. 工具:shell 可以完全代替手動操作

```
menu Set*            改任何設定。已用:SetMovRecSize 2→4 切到 OG3K
key <NAME>           送任何按鍵。QSON/QSOFF 是開關式(兩個事件都會切換)
key CAPTUREON/OFF    ★ 就是截圖鍵,相機寫 SS__xxxx.JPG 到卡上
getfile.py           把截圖拉回主機 —— 完整的「自己截圖」管線
gui scr set <name>   直接指定畫面。名字在資源池:1_01_CINE / 1_03_CINE / 1_04_SLike …
gui geti/sets        用名字讀寫 UI 變數
gui image log 1      ★ 記錄每一張載入的 .xci 檔名與尺寸
log act/out <FLAG>   37 個頻道。GUI 頻道會被 0xc055fa14 的 ERR 洗版,要濾掉
mem save [path] [start,end]   把記憶體存成檔案到卡上
display osdfile      把任意 TIF 畫到 OSD 圖層(不需資源包的退路)
```

## F. ★ 直接證據:RES. 格根本沒載入圖示

`gui image log 1` + 開 QS,一幀載入 38 張圖。每個格子都是「底板 + 值的圖示」:

```
menu_cine_format_qs.xci      150x74    FORMAT 底板
font_menu_MB_format_1.xci    150x38      值
qs_formatQuality_3_S.xci      86x49      圖示   ✔

menu_cine_resolution.xci      86x74    RES.  底板
                                         ← 沒有任何 qs_resolution_*_S.xci

qs_fps_3_S.xci                91x49    FPS   圖示   ✔
menu_cine_fps.xci             86x74          底板
```

**畫面上的亂碼不是「載入了錯的圖」,是「根本沒載入」** —— 那塊區域的殘留內容被畫出來。
第二部分從位元組推出的「陣列只有兩筆、狀態 2 越界」得到直接證據。

副產品:檔名編號跟著狀態走(FPS 29.97 載 `qs_fps_3_S`、品質載 `qs_formatQuality_3_S`)。
解析度狀態 2 要的是 **`qs_resolution_3_S.xci`,那個檔不存在**。

## G. ★ 順帶解掉一個疑點:gui geti 是誤導的訊號

`gui geti LV_Resolution` 從頭到尾讀回 `0`,一度讓我懷疑 enum→狀態的映射。
但 log 顯示 **狀態 0 的 `qs_resolution_1_S` 也沒載入** —— 如果狀態真的是 0,
它應該要載。既然兩筆都沒中,狀態只可能是 2。

**所以靜態追出來的映射是對的,`gui geti` 讀的是另一個變數。**
(`LV_Resolution` 有 Cine 與 StillLike 兩個發佈者,各有獨立鍵表
`0xC2DF3448` / `0xC2DF3D0C`。)

## H. 序列化區塊在執行期**不是**槓桿(結論反覆過兩次,最終如此)

這一節記錄一段來回,因為過程本身比結論更值得記住。

### H.1 第一次:判定無效

把 18 份副本裡 `qs_resolution_2_S` 的 `val` 欄 1 → 2。重開 QS、`gui gc`、
`gui scr set` 都沒變化 → 判定「區塊不是執行期槓桿」。

### H.2 撤回:以為是漏了觸發刷新

使用者問「你有切換一下設定讓他刷新嗎」。補上 `menu SetMovRecSize` 切換之後,
log 裡出現了 `qs_resolution_2_S.xci`,於是撤回 H.1,改稱「區塊有效,只是要刷新」。

**這個撤回是錯的。**

### H.3 ★ 真正的問題:跨幀污染

`gui image log` 的視窗會跨兩幀,**換狀態後的第一次繪製帶著舊狀態的內容**。
所以「切到 OG3K 後看到 `qs_resolution_2_S`」其實是前一個 FHD 幀的殘影。

我在紀錄裡兩次註記了這個歧義,又兩次照著判定成功。同一個錯誤犯兩次。

**修正後的探針紀律**(`build/qsprobe.py`):

```
關 QS → 換 enum → 等 3 秒
→ 開 QS(第一次繪製,丟掉) → 關 QS → 清 log
→ 開 QS(第二次繪製) → 這一幀才算數
```

### H.4 用乾淨探針重測:三種修改全部零效果

```
原廠            enum 3 → qs_resolution_1_S ✔      enum 4 → 什麼都沒有
val 1→2         enum 4 → 什麼都沒有                enum 2 → 照樣正常
條目數 2→3      enum 4 → 什麼都沒有
清 last + 第三筆 + 條目數 3
                enum 3 → qs_resolution_1_S ✔      enum 4 → 什麼都沒有
```

**三種獨立修改,全部零效果。H.1 的結論成立:資源記錄開機時解析一次進活的結構,
之後不再回頭讀序列化資料。**

### H.5 格式校正:是動畫曲線，不是直接索引

```
property header 20B:
  key_count:u32, type:u32, component:u32, property_name:u32, dimension:u32
key 10B × key_count:
  flag_a:u8, flag_b:u8, time:u32 BE, value:u32 BE
```

原生 `0xC05E6400` case 9 對每個 key 依序讀兩個 u8、time u32、value u32；
archived native-parser verifier 也逐筆核對 `raw[0]` / `raw[1]`、`>I@+2`、
`>I@+6`。`FUN_c05e2280` 依時間找 bracketing keys：區間內 lower 是最後一筆
`time <= t`（同時間重複取最後一筆）、upper 是第一筆 `time > t`；首尾外都
夾到第一/最後一筆，`t == last` 也兩者皆 last。
`FUN_c05e2970` 回傳 lower selected key `+0x18` 的 value。

H.4 的零效果仍證明「已建好的畫面不重讀原序列化 bytes」；但當時用
`last` / 直接 index 描述那些試寫欄位是錯的，不能再當成格式證據。

## I. 下一步

1. **開機時改。** AutoRun 跑在開機時。如果它早於資源解析,同樣的 patch
   從卡上套用就會生效。這是唯一還沒試、而且直接沿用現成機械的方向。
2. **攻解析後的結構。** 找 parser 的輸出物件,直接改活的結構。
3. **`display osdfile`。** 把自己的圖疊上去,完全繞開資源系統。

## J. 新的可重現故障:密集開關 QS 會弄死 USB worker

兩次都一樣:連續多次 `key QSON` 之後,shell 變成 `LIBUSB_ERROR_TIMEOUT moved=0/64`,
相機仍在 USB 上列舉(node id 不變 = 沒重開),但 worker 完全不回應。
恢復方式:拔 USB、重插。

**探針每跑一次會開關 QS 五次,所以一次不要連測太多個 enum。**

---

# 第四輪:活的資料 vs 烘焙好的資料

## K. ★ enum→狀態配對表是活的

`0xC2E4020C` 的三筆配對由 `FUN_c06ccd10` 在**每次求值**時線性查表,
和 widget 的序列化 blob 不同 —— 它是活的。

實驗:把 `{4,2}` 改成 `{4,1}`(一個字,`0xC2E40220`)。用乾淨探針測,
而且刻意讓前一個狀態是 UHD,排除污染:

```
enum 3 (UHD)   →  qs_resolution_1_S ✔
enum 4 (OG3K)  →  qs_resolution_2_S ×3 + font_menu_MB_resolution_2   ← 真的載入
```

**立刻生效,不用重開機,不用特殊刷新。** 工具:`build/statemap_try.py`。

這條界線現在很清楚,也解釋了為什麼前三個 patch 全部無效而這個立刻有效 ——
不是隨機,是資料性質不同:

| 資料 | 何時讀 | 執行期可改 |
|---|---|---|
| enum→狀態配對表 `0xC2E4020C` | 每次求值 | ✅ |
| widget 的 `image` 序列化陣列 | 開機解析一次 | ❌ |

## L. 這是退路,不是解法

`{4,1}` 等於告訴整個 UI「OG3K 就是 FHD」:

- QS 格子乾淨了,但標籤是 FHD
- 選單收合列從 `3` 變成 FHD —— 使用者早就說過那是誤導
- 錄影完全不受影響(走 `og3ksel` 的旗標)

**而且真正的瓶頸不是槽位,是點陣。** 就算找到解析後的陣列、加了第三個槽位,
`qs_resolution_3_S.xci` 這個檔仍然不存在,指過去也沒有圖。
所以要做「原生感」的解法,**應該先攻點陣格式,不是先攻槽位** ——
點陣做不出來的話,槽位做了也沒用。

## M. ★ 硬規則:shell 卡死之後必須完整重套 og3k_load

第二次 shell 卡死時,寫入是寫到一半被中斷的,OG3K 的安裝被打壞了 12 個字,
其中含「選單第三列 → enum」的對應。症狀:從選單選 OG3K,enum 被寫成 `0`,
而 `0` 不在配對表裡 → `FUN_c06ccd10` 回預設值 0 → 顯示 UHD。

**`--check` 只會說「改了 N 字」,不會分辨那 N 個字是無害的 log 槽還是關鍵對應表。**
當時看到「改了 9 字」就當成 log 槽放過去了,是錯的。

規則:**只要 shell 卡死過,先跑一次完整的 `og3k_load.py`,再相信任何行為。**

---

# 第五輪:★ 兩個阻礙都破了

## N. XCI 格式(完整)

用 `xcitrace.S` 攔 `gui image log` 的回呼(只換 `0xC37CECF8` 那個函式指標,
不改任何指令),抄呼叫端的堆疊。堆疊裡有兩個落在 `0xC14xxxxx` 的指標 ——
**封存檔一直都在靜態韌體映像裡**,之前搜不到是因為資料是 LZ4 壓縮的。

```
+0x00  "XC\0\0"
+0x04  u32  大小
+0x08  u16  寬            ← 與 image log 報的尺寸逐一吻合
+0x0A  u16  高
+0x0C  u32  0x00000400
+0x10  u16  0x0202
+0x20  標準 LZ4 frame(magic 04 22 4D 18,FLG/BD + 8-byte content size + HC,
                      block size u32 在 +0x2F,資料在 +0x33)
內容    16bpp:byte0 = 亮度,byte1 = alpha (L8A8)
```

三張測試圖解出來都是**精確的 16 bit/px**(22200 = 150×74×2),
渲染就是 `FORMAT` / `12bit` / `RES.`,和畫面完全一致。

**整個封存檔:2005 個 blob,0xC1240014 .. 0xC151C348**,全在靜態映像內,
開機後就在可寫的 RAM。blob 順序與 2006 條 `.xci` 路徑清單對應(中間一個缺口)。

要的兩張:

```
0xC14D4184  86x49  "UHD"  = qs_resolution_1_S
0xC14D44B0  86x49  "FHD"  = qs_resolution_2_S   (blob 644 bytes)
```

閒置可覆寫的目標(fp 永不顯示 DCI4K):

```
M_resolution_dci4K  @0xC1359724  可用 2896 bytes
L_resolution_dci4K  @0xC12CA138  可用 3472 bytes
```

## O. ★ 解析後的陣列(活的,可寫)

在 GUI 堆 `0xC71xxxxx`–`0xC74xxxxx` 搜「指向名字字串的指標」(`0xC18E92DC`)
就找到了 —— 之前搜字串 `qs_resolution` 搜不到,因為堆裡存的是**指標**不是字串。

```
+0x00  筆數 = 2                     ← 活的
+0x04  2
+0x08  8
+0x0C  → 元素指標陣列               ← 活的
元素   ~0x34 bytes,+0x18 = 名字指標,之後是四個浮點與 0x21(序列化版的 tail)
```

重開機後版面不變,只有位址變。18 份語言副本。

## P. 完整可行的計畫(所有未知數都消除了)

1. 主機端畫一張 86×49 的 OG3K → L8A8 → LZ4 → 加 0x20 標頭
2. 覆寫 `M_resolution_dci4K` 的 blob(2896 bytes 夠,fp 永不顯示它)
3. 在空白 RAM(`0xC0733000` 一帶)蓋一個三元素指標陣列 + 一個新元素物件,
   名字指標指向 `M_resolution_dci4K`
4. 18 份副本的 `+0x0C` 指到新陣列、筆數寫 3

全部是執行期寫入,不需要重開機,拔電池即還原。

## Q. 撤回第四輪 §L 的判斷

§L 說「瓶頸是點陣,槽位是容易的一半,應該先攻點陣」。**順序判斷是對的
(先攻點陣確實正確),但難度評估反了** —— 點陣一個 hook 就破了,
槽位反而多花了幾輪。不過先攻點陣仍然是對的選擇:點陣做不出來,槽位做了也沒用。

---

# 第六輪:圖做出來了,槽位卡在「物件是暫時的」

## R. ★ OG3K 圖塊完成

`build/xci.py` —— 解碼器與編碼器。**往返測試像素完全相同**
(把原廠 FHD 解開再編回去,L 與 A 兩張圖逐像素一致),所以格式沒有猜測成分。

新圖:86×49、Arial Narrow Bold、大寫高 24px(原廠 26,四個字母得矮一點)、
L == A 純白。實心 16.9% / 半透明邊 6.6%(原廠 14.5% / 6.8%)。
blob 1564 bytes,`M_resolution_dci4K` 的槽位有 2896。

一個細節:LANCZOS 直接降取樣會留下很長的淡尾巴(半透明像素 16.9%,
原廠只有 6.8%),看起來灰灰的。`text_tile` 的 `lo/hi` 把過渡帶收緊之後就對了。

## S. ★ 槽位:解析後的物件是**暫時的**

實際寫進去測了:

```
覆寫 M_resolution_dci4K 的 blob            ✔ 寫入正確
8 份陣列表頭 筆數 2→3、+0x0C 指向新陣列    ✔ 讀回全部正確
新元素 +0x18 指向 M_resolution_dci4K       ✔
→ 開 QS  仍然什麼都沒載入
```

回頭再掃,**那 8 份副本消失了** —— 同一個位址範圍裡一份都找不到。
再掃一次(QS 開著、關著各一次)也是 0 份。

**元素物件每次都重建,而且會在堆裡換位置。** 所以:

| 目標 | 為什麼不行 |
|---|---|
| 序列化資料 `0xC22A17xx` | 開機解析一次,之後不再讀 |
| 解析後的堆物件 | 每次重建、位址會變,固定位址的 patch 撐不住 |

這解釋了到目前為止**每一個**結果:三次序列化 patch 無效、這次堆 patch 也無效,
而 `0xC2E4020C`(每次求值都查的表)一改就生效。**界線是「何時讀」,不是「在哪」。**

## T. 下一步只剩一條像樣的路:hook 建構函式

既然物件是每次重建的,唯一持久的介入點就是**建構它的那段程式**。
元素的 `+0x0C` 是 `0xC05EDC38`(Thumb),那是找建構函式的起點。

hook 在那裡把第三個元素接上去,就是這個專案一直在用的做法
(「依原有設計增加功能,不動原本的東西」),而且天生持久 —— 每次重建都會再跑一次。

注意:那一帶是 Thumb 程式碼,和我們現有的 ARM payload 機制不同,要先處理交互呼叫。

---

# 第七輪:Thumb hook 可用了,建構流程完整還原

## U. ★ Thumb hook —— 這個專案第一次

GUI 那一整區全是 Thumb-2,原本的 ARM hook 機制不適用。可行的做法:

- `armasm.py` 底層是 clang,`.thumb` 直接可用。**但 payload 內部不能用 `bl`**
  —— 那會產生 `R_ARM_THM_CALL`,現有的重定位處理只認 ARM 的 `R_ARM_CALL`。
  分支和 pc 相對的文字池都沒問題。
- 入口用 **`B.W`(T4)而不是 `BL`**,`lr` 就不會被動到,位移的指令可以原樣執行。
- 回程用一個「原本的程式碼馬上就會覆寫」的暫存器 `bx` 回去,目標要帶 Thumb 位元。

編碼公式(**前向與反向都跟 clang 對過才敢寫**):

```python
off = target - (site + 4)
s, i1, i2 = (off>>24)&1, (off>>23)&1, (off>>22)&1
j1, j2 = (~i1 ^ s)&1, (~i2 ^ s)&1
hw1 = 0xF000 | (s<<10) | ((off>>12)&0x3FF)
hw2 = 0x9000 | (j1<<13) | (j2<<11) | ((off>>1)&0x7FF)
word = hw1 | (hw2<<16)          # hw1 放在低位址
```

```
前向 +0x1BAC38   我 hw1=F1BA hw2=BE1C   clang f1ba be1c  ✔
反向 −0x1BAC46   我 hw1=F645 hw2=B9DD   clang f645 b9dd  ✔
```

工具:`build/elemobs.S`(第一個範本)、`build/appendobs.S`(帶名字過濾)。
兩個都上機武裝、拆除過,相機全程穩定。

## V. ★ 圖示陣列的建構流程(完整)

`FUN_c05e6400` 的 `case 10` 就是建圖示陣列的地方:

```c
case 10:
    count     = read();
    container = FUN_c05e2988(alloc, name, count, ...);
    for (i = 0; i < count; i++) {
        name = FUN_c05e5b58(param_1, read());   /* 池偏移 → 字串位址 */
        elem = FUN_c05edc40(alloc);             /* 配置 0x34         */
        FUN_c05edb68(elem, name);               /* 名字寫進 +0x18    */
        FUN_c05edd20(elem, read(), 0, read(), 0);
        elem[0x24] = read();
        FUN_c05e2ca8(container, elem);          /* 接進容器          */
        FUN_c05edb10(elem);                     /* 放掉我們的參考    */
    }
```

**加第三筆所需要的材料全部齊了:**

- `FUN_c05e2ca8(容器, 元素)` 是理想介入點 —— 元素已填好(`+0x18` 可辨識 widget)、
  容器在手。掛上去讀出來的名字完全正確(`OFF`、`Blk1`…`Blk15`)。
- `FUN_c05edd40` 複製元素,而且**配置器是從元素自己的 `+0x10` 取的**,
  所以不需要直譯器的配置器物件。
- `FUN_c05edb68(複製品, 0xC18DA6C4)` 就能把名字換成 `M_resolution_dci4K`
  —— 那張圖的 blob 我們已經可以覆寫成 OG3K。

## W. ★ 但是:陣列開機後就不再重建

帶名字過濾的 hook 武裝著,把每一種畫面層級的切換都試過:

```
一次 QS 繪製(共 314 次 append)     0 筆
gui scr set 1_03_CINE               0 筆
切 UHD 再切回 OG3K                  0 筆
進選單 / 離開選單                    0 筆
SetRecMode 靜止畫 ↔ 錄影             0 筆
STILL 鍵 / CINESW 鍵                0 筆
(回放鍵測到一半 USB worker 卡死 —— 進回放會做卡片 I/O,是已知的互鎖)
```

**全部是 0。**

### 順帶修正第六輪 §S 的說法

§S 說「元素物件每次重建」。更精確的說法是:**那八份陣列消失,是因為擁有它們的
畫面物件被釋放了,不是元素被重建。** 陣列本身是**開機時資源集被整批直譯那一次**
建好的,之後不再重建。

## X. 下一步:把觀察 hook 做進 AutoRun

如果 §W 成立,hook 就必須**在資源解析之前**武裝 —— 也就是 AutoRun 的時序問題。

差別在於:當初「AutoRun 太晚」是**推論**,現在可以**驗證**。

```
把 build/appendobs.S(只記錄,不改行為)做進 AutoRun → 開機 → 讀紀錄

有命中 → AutoRun 早於資源解析,整條路通;把觀察版換成
         「複製元素 + 改名字 + 再 append 一次」就完成
沒命中 → AutoRun 確實太晚,這條路排除,要找更早的掛載點
```

**兩種結果都有用**,而且成本只有一次建卡加一次開機。

---

# 第八輪:開機時序探針已建好,等實機冷開機

## Y. 依新目錄邊界分開「共用 UI 機械」與「OpenGate 測試資料」

UI / XCI / Thumb hook 的通用原始碼現在以
`research/ui/tools/` 為準;OpenGate 只保留自己的整合測試包:

```
research/ui/tools/build_appendobs_boot_probe.py   通用建置器
research/ui/tools/appendobs.S                     通用觀察 hook
research/ui/tools/appendobs_ctl.py                通用完整性檢查 / reader
projects/open-gate/build/ui_boot_probe/           這次 OpenGate 整合測試包
```

沒有把觀察碼加進 `og3k_plan.py`:Plan 同時餔開發載入器與出貨卡,
診斷碼不該進產品。

## Z. 測試包的離線驗證

```
appendobs payload      76 bytes
payload SHA-256        c7878141b861ee5364f7114ba419844766f25a945ea924519eef32146e426dd7
hook site              0xC05E2CA8,stock 0x4605B530
Thumb B.W              0xB9AAF150 -> 0xC0733000
AutoRun                 32768 bytes,210 commands(實測上限 648)
AutoRun SHA-256          3638e3ae5559fef61e0cf57d2defdab04bbc4bd23bb144b3001c331e0fd054c6
VSHL.BIN                32768 bytes,2 sections
VSHL.BIN SHA-256         230b080b44643f05bf11a83f49406a2ead55bce0de7aebdfc217c91cc823d126
cave                    0xC0733000..0xC0734000,參考映像全零
```

AutoRun 的第一批可執行指令固定是
**payload → `SLOTP=LOGBEG` → hook**,hook 之後才開始載入 USB shell。
這樣零命中才能回答 AutoRun 時序,不會只是測試包自己裝得太慢。

Reader 的舊版會把 12-byte `{container, element, name}` 用 8-byte stride 解讀,
已在 `research/ui/tools/appendobs_ctl.py` 修正;現在會先逐字核對 payload
與 hook,再驗證 `SLOTP` 是 12-byte 邊界。

下一步是**完整拔電冷開機**,banner 顯示 `UIBOOT!` 後先不進 QS、
不切畫面,立即執行:

```
python3 research/ui/tools/appendobs_ctl.py read
```

- payload / hook 完整且 `SLOTP > 0xC0733100`:開機解析期有命中,
  可進入「clone 第二元素 → 改名 OG3K tile → append」。
- payload / hook 完整且 `SLOTP == 0xC0733100`:AutoRun 太晚,改找更早的掛載點。
- 任一完整性檢查失敗:這是載入失敗,不是時序結論。

這支探針目前只過濾 `qs_resolution_1_S / 2_S`,所以成功也只先證明
QS 解析度格這一族可加第三槽;設定摘要與其他大小的圖示族仍要逐族量測,
不在這次零命中就宣稱三個 UI 症狀全部解決。

---

# 第九輪:AutoRun 確實較晚;沿用 parser-copy precedent,但逐筆驗 timing

## AA. 修正第七、八輪的「唯一下一步」

使用者確認:**AutoRun 肯定晚於原廠資源載入。** 因此 §X / §Z 的冷開機
`appendobs` 觀察器不再是主線;它保留為通用時序探針,但不值得為這個已知答案
再浪費一次相機開機。

這不代表原生 UI 路徑必然關閉。重新依新目錄邏輯檢查
`research/other/external/FP3K-technical-handoff-2026-09-10/` 後發現:
同一份 Ver.5.02 韌體、同一段 NBR/NBU 程式碼，早先 FP3K v0.3.2 已在相機上
成功使用過這套機制:

```
0xC05E84D8  NBR 記憶體載入器
0xC05E6400  NBU 單筆記錄直譯器
0xC05E5B58  NBU 字串解析器
```

若原廠 NBR 已先載入，**後續真的發生的** NBU 解析仍帶著活的 resource context。
`0xC05E6400` hook 會用這個 context 懶載入一次私有 NBR，再把**位址與完整
原始 FNV 都吻合**的記錄複製到 512-byte 暫存區、加上第三狀態，交回原廠
直譯器解析，最後還原 reader base 並依原記錄長度前進。原廠 NBU 與原廠圖資
都不覆寫。FP3K v0.3.2 的硬體結果也已證明，只加 image key 會破版；
visibility / rect / position / collapse / timeline 等 companion keys 必須一起複製。

但晚註冊 private NBR **不會重播已解析的 NBU 記錄**。v0.3.2 的畫面成功只
證明它自己的 AutoRun 在目標 screen-specific parse 前完成（或畫面之後 lazy
parse），不能證明目前較慢、195-command 的 OpenGate loader 還有同樣餘裕。
因此本輪把 timing gate 降到逐筆：resident 為排序後的 360 筆記錄各保留一個
unique-hit bit。private pack ready 只證明資源註冊；目標 bit 命中才證明該筆
UI 修補實際交給原廠 parser。

## AB. OpenGate 真正需要的範圍

OpenGate 現有 `og3kname` 已處理 HUD 名稱，所以不搬 FP3K 的整套 47 組 UI。
這次只取與三個未解外觀直接耦合的精確記錄:

| 類型 | 筆數 | 用途 |
|---|---:|---|
| `layout-keys` | 315 | 18 組大 QS `20_MV_Resolution` + 18 組小 QS `21_MV_Resolution` 的完整 companion properties |
| `state-end` | 36 | 各組 timeline 終點 33 → 66 |
| `literal-delta` | 6 | 共用底部 UHD/FHD/OG3K footer、第三格與 cursor 範圍 |
| `summary-label` | 1 | `0xC1A7246B` 收合摘要 `3` → `OG3K` |
| `QS-limit` | 2 | `0xC237249F` / `0xC25E405A` 最大索引 1 → 2 |
| **合計** | **360** | HUD `Resolution` 家族不動 |

私有 NBR 只帶三個資源，避免覆寫任何原廠 UHD/FHD 圖:

```
OG3K_QS     86x49   QS 值圖
OG3K_SET    86x74   底部選項圖
OG3K_FONT  150x38   大 QS 值圖
```

## AC. 新目錄下的實作

共用知識 / 工具:

```
research/ui/tools/nbr.py
    NBR 1.5 builder + 結構、FNV、邊界驗證
research/ui/tools/xci.py
research/ui/captures/og3k_86x49.xci
```

OpenGate 耦合整合與測試資料:

```
projects/open-gate/build/og3k_ui.S
projects/open-gate/build/build_og3k_ui_candidate.py
projects/open-gate/build/verify_og3k_ui_candidate.py
projects/open-gate/build/decode_og3k_ui_state.py
projects/open-gate/build/check_og3k_ui_cave.py
projects/open-gate/build/ui_runtime_candidate/
```

`og3k_ui.S` 只處理 UI，沒有任何 capture geometry；建置器把它和目前
`og3k_plan.py` 的 590 筆 OpenGate 計畫合併，但把所有 payload / private NBR /
state 放在前面，最後才武裝原有與新增 hooks。候選輸出刻意留在 `projects/`，
沒有更新 `fpSup/` 的公開產品包。

## AD. 2026-09-14 離線結果

```
UI code       0xC0732C84..0xC07343B8   5940 bytes
UI state      0xC0732700..0xC0732748     72 bytes
private NBR   0xC0793060..0xC0793EF4   3732 bytes
VSHL used                                  14492 / 32768 bytes
VSHL sections                                 75
```

state 前 24 bytes 記 context / pack status / native result / 所有 post-install
stock record 次數 / exact-copy-path 呼叫次數 / 最後地址；`+0x18` 起 45 bytes
是 360-bit unique-hit bitmap。`decode_og3k_ui_state.py` 只解本機 dump，不會
自行碰相機，並按 kind 與 36 個 20/21 groups 報告完整度。

完整韌體 SHA-256 是
`92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4`；
其中含 UI 的前 49,245,696 bytes SHA-256 是
`aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`，
與硬體驗證過的 FP3K 計畫完全相同。360 筆 source bytes 全部逐筆吻合。

兩次獨立重建結果位元一致:

```
AutoRun.txt  3a2a58c9b7f20db8a2f47d0a62774fd1aabb8c396e734fe4780fac0e6b5f7c53
VSHL.BIN     583190c93bc56aa5b1429d9a61a22d72d5dd6715314c5d26005c7fd32f22ab06
OG3KUI.BIN   c8b7bb738e39ebb6d4908452567b4565001f1c45fd7ce29bfa17a0f20ff263eb
OG3KUI.NBR   c199170c0701d2f26520f89cd90b0731e552452f1f8bedd9e772b157ca50fe05
```

獨立 verifier 從 `VSHL.BIN` 回讀 code/state/pack，重新解析 NBR 與三個 XCI，
並反向解碼三個 Thumb B.W；Capstone 的第二次獨立反組譯也得到:

```
0xC05E84D8  B.W 0xC0732C84
0xC05E6400  B.W 0xC0732DD0
0xC05E5B58  B.W 0xC0732D64
```

五個回到原廠 Thumb stub 的內部跳轉已額外檢查為 `orr ip, ip, #1`，不能用
`add ip, ip, #1`：`.thumb_func` symbol 可能已帶 bit 0，`add` 會把它變偶數並
錯誤切到 ARM。verifier 同時核對三個 stub 的首四 bytes 確實重播原廠指令。

這是冷開前的離線 gate；目前 CINE 實機結果見 §AE。

## AE. 實機 gate:冷開與目前 CINE UI 已通過

最新 `fp-camera-control` 規則已納入流程。2026-09-14 USB shell 已連上並確認
相機是 `5.02.0.V91`。取得明確讀取同意後，用新增的
`check_og3k_ui_cave.py` 把 `0xC0793060..0xC0793EF4` 分成四段讀；單次整段
`mem get` 會撞 shell 16 KiB 文字回覆上限而截斷，不能當證據。分段讀有完整
地址覆蓋檢查，待機、QS 開啟、主選單開啟三種狀態的 933 words 全部為零。

卡片原有兩檔已完整備份到
`build/camera_backups/pre-ui-runtime-20260914/`。原 `VSHL.BIN` 是會占
`0xC0733000..0xC0734000` 的舊 `ui_boot_probe`，因此沒有熱載新 resident。
新候選兩檔已寫到 SD 根目錄並完整抓回；readback SHA 與本機 source 逐位元
相同，記錄在 `ui_runtime_candidate/camera_preboot_readback/MANIFEST.md`。
上述 preboot gate 通過後，已照規則完成真正的完整冷開：拔 USB 與外接供電、
取出電池超過 30 秒、保持 USB 未接開機，最後才接回 USB。沒有用 worker 轉送
`reboot` / `poff`，也沒有熱載任何會碰 resident caves 的舊探針。

冷開後、尚未打開目標畫面時，明確讀取同意下取得的
`0xC0732700..0xC0732747` state 是:

```
pack status                  1 (ready)
post-install stock records  6596
exact copies                   0
unique target bits           0 / 360
```

這是乾淨的 timing baseline：private NBR 晚註冊成功，但不會重播已消費記錄。
接著以 enum 4、等待 3 秒、丟棄第一次 QS draw、只量第二次 draw。內建 image
log 實際配對到 `OG3K_FONT.xci 150x38` 與 `OG3K_QS.xci 86x49`。再讀同一份
state 時，數字變成 41,133 筆 stock records、164 次 exact copies、164/360
unique bits；其中 8 組 `20_MV_Resolution` 與配對的 8 組
`21_MV_Resolution` 全部完整，並命中目前 active footer/cursor/limit。

進入 SHOOT → 記錄設定 CINE 後，收合摘要畫面乾淨第二幀顯示
CinemaDNG / 12 bit / OG3K / 29.97 fps；原生解析度選擇畫面完整顯示
UHD 3840x2160、FHD 1920x1080、OG3K 3008x2000。第三次 state 讀回新增唯一
的 summary record `0xC1A7246B`，合計 165/360。

普通截圖鍵不適合 QS，因此本輪另外驗出韌體內建的
`display capture \\FILE.XCI 3 2`。它不送相機按鍵，可在 QS 未關閉時直接存下
1024x682 L8A8 UI 層。選中 RES. 的實際畫面清楚顯示 UHD / FHD / OG3K 三格，
游標落在 OG3K；同時 image log 逐一載入 `set_resolution_1.xci`、
`set_resolution_2.xci`、`OG3K_SET.xci`。共用解碼工具放在
`research/ui/tools/render_xci.py`；OpenGate 的 XCI/JPEG、hash、逐步 state 結果
與限制記在 `build/ui_runtime_candidate/camera_postboot/MANIFEST.md`。

因此本輪被點名的四項 UI 繪製，在目前 CINE 配置全部通過。剩餘 195 個未命中
bits 是這次沒有啟用的其他 screen/style variants，不能說成已驗證，也不能反過來
把它們當成本畫面失敗。這是錄影重測前的狀態；後續短 FHD/UHD/OG3K transition
結果見 §AH。尚未做的是持續寫入、素材內容、回放、Still-like 與其他 UI variant
的回歸；候選仍是 `projects/` 內的 debug build，沒有更新 `fpSup/`。

## AF. resident 與舊探針互斥

候選 resident 擁有 `0xC0732700..0xC0732748` 與
`0xC0732C84..0xC07343B8`。舊的 `size_ctl`、`cfgring`、`cfgsnap`、
`appendobs`、`elemobs`、`xcitrace`、`0xC0733400` log family、`zoomlog`、
`og3ktile`、`livepatch` 都與它重疊，候選在場時不得執行。這些檔案保留作
獨立診斷，不搬進共用產品路徑。韌體內建的 `gui image log` 不占這些 caves，
是目前允許的 UI draw 量測方法。

## AG. 若 exact-hit 為 0 的後解析備援

不要只在 `0xC0602098` 換 XCI。那裡是 image open/decode，不是每次 draw；
若 FHD → OG3K 仍回同一個 `_2` 名稱，backend cache 可能完全不重開資源。
目前靜態 trace 收斂出的最小三層實驗是:

1. 先做 observation-only `0xC05E37F8`，確認 FLAG=1 時 20/21 container
   確實收到 time 66，而 stock end=33 導致選擇失敗；命中後才只對這兩個
   exact group 把 66 映成 33，沿用 FHD companion geometry。
2. 在 `0xC05E2970` 跑完原函式後，以 `[r1-0x50]` exact group name 與
   `[r1+0x1c]` time 作 guard，把兩個 `_2` image 結果換成 unique
   `OG3K_FONT` / `OG3K_QS` 名稱，強迫 backend 判定 name change。
3. `0xC0602098` 只替這兩個 synthetic names 回傳 bounded XCI descriptor。

這條備援仍只涵蓋 20/21 active tile。footer 第三格必須同時保留 FHD 與新增
OG3K，不能直接把 `set_resolution_2` blob 換掉；cursor/max 與 Settings summary
也仍是獨立問題。因此先用 bitmap 裁決 parser-copy timing，再決定是否建立這個
分離的 observation candidate，不把兩條未驗路徑混在同一張測試卡。

## AH. 2026-09-14 錄影凍結重測：立即切換沒有重現

使用者第一次在 full-UI candidate 上嘗試 OG3K 錄影時，相機建立
`CINEMA/A001_082` 後凍結，靠拔電池恢復。恢復後從卡上完整讀回
`AutoRun.txt` / `VSHL.BIN`，SHA-256 與本機 candidate 逐位元相同；再冷開後
三個 UI hook 與 payload 起始碼也全部吻合，排除安裝損壞或半載入。

同一個 candidate 隨後由 USB 驅動七次錄影切換：FHD 一次、OG3K 三次、UHD
三次。OG3K / UHD 都依 SD 卡速度限制在約一秒，建立連續的
`A001_083..A001_089`，每次最後 `is_recording -> 0`，沒有再次凍結。錄影後
第二次乾淨 QS draw 仍載入 `OG3K_FONT 150x38` / `OG3K_QS 86x49`；state 的
resource context 未換、pack status 仍是 ready，stock records 由 24,411 增至
34,537，exact copies 與 bitmap 維持 164。正常的短 REC transition 沒有清掉
`0xC0793060..0xC0793EF4` private NBR，也沒有觀察到 context reload storm。

這只通過「立即開始／停止」而不是持續寫入：目前 SD 卡不足以長錄 UHD/OG3K，
沒有解開素材資料夾驗證影格內容。第一次 freeze 因此降為未重現事件，不能歸因
給 UI，也不能宣告已解決。若用更快媒體重現，使用
`build/ui_recording_ab/core_only/` 做嚴格 A/B；其 AutoRun 與 A 位元相同，590
筆 OpenGate core 與 USB worker 也完全相同，唯一移除 2,439 個 UI-only words。

本輪另修正 USB 控制語意：`MOVON` / `MOVOFF` 是同一按鍵的 down/up，不是
start/stop。開始與停止各需要一次完整 `MOVON -> MOVOFF`；只送第二個
`MOVOFF` 會讓相機繼續錄影。這是共用相機控制知識，已同步到
`.claude/skills/fp-camera-control/SKILL.md` 與
`research/interfaces/notes/EGRESS_MAP.md`，而本節只保留 OpenGate 耦合結果。
