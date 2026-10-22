# 換掉任何一個 UI 資源

> ## ✅ 2026-09-29 實機定案:**加一列完全不用 hook**
>
> | | 結果 |
> |---|---|
> | **原地改內容、長度不變** | ✅ **有效**,連重開機都不用(退出選單再進去就好) |
> | **原地加一列**(位元深度 3→4、格率 9→10) | ✅ **有效** —— **列會畫出來,配上 controller max 也選得到** |
> | **改目錄項指到別處**(repoint) | ❌ **無效**,韌體照樣讀原本那份 |
> | **改目錄項的長度欄** | ❌ 同上,一樣是死的 |
>
> **所以「資料就能畫列」是成立的。** 本文原標題「8 個位元組,不用 hook」是錯的 ——
> 不用 hook 是對的,**但不是靠那 8 個位元組**,是靠**原地改內容**。
>
> 之前兩次失敗的真因是 **CSV 的形式**,不是機制:見下面〈替換 CSV 的規則〉。

2026-09-29。位址只對 Ver.5.02。工具:[`tools/nbr_stock.py`](tools/nbr_stock.py)、
測試 [`tools/test_nbr_stock.py`](tools/test_nbr_stock.py)(34 項,八次變異檢查都會失敗)。

```
python3 research/ui/tools/nbr_stock.py verify
python3 research/ui/tools/nbr_stock.py list --ext cvm      # 195 個選單 CSV
python3 research/ui/tools/nbr_stock.py show ../MenuB12/data/ListB12/B2_5_4.cvm
python3 research/ui/tools/nbr_stock.py repoint <path> <新位址> <新長度>
python3 research/ui/tools/nbr_stock.py menu ../MenuB12/data/ListB12/B2_5_5.cvm
python3 research/ui/tools/nbr_stock.py strings fps --lang "Traditional Chinese"
```

## 結論先講

**相機畫的每一個圖示、字型、本地化檔,以及每一個選單列表 CSV,都是同一張排序目錄裡的一筆。
換掉任何一個資源 = 把新位元組放到有空間的地方,然後往那筆寫 8 個位元組。**
解譯器不用攔、字串不用騙、NBR 不用另外註冊。

原廠的解析度選單列表就是一個 89 bytes 的 CSV:

```
../MenuB12/data/ListB12/B2_5_4.cvm      0xC0F8E7EC  89 B   目錄項 0xC0D4DDFC
    NO,TEXT,Popup,IMAGE,Enabled,Enabled2
    1,0313,Popup,blank,1,2
    2,0314,Popup,blank,1,2
```

兩列,UHD 與 FHD。**這就是「選單裡有幾列」的來源。**

## 替換 CSV 的規則(實機定案)

1. **原地改。** 寫在該資源自己的 `data_address` 上。repoint 是死的。
2. **最後一列的結尾 CRLF 不能省。** 位元深度那次為了塞進槽裡把它拿掉,
   第四列就整列消失 —— 這是那次失敗的真因。
3. **要騰空間就整欄拿掉,不要把格子留空。** `IMAGE` 是最安全的那一欄
   (欄位由表頭決定,全機本來就有 13 種表頭)。留空格子反而會變長。
4. **`TEXT` 可以直接寫字面文字**,所以新列不用動 `.nloc`。
5. **列數變了就要配 controller 最大值**(`= 列數 − 1`,**big-endian float**),
   否則列畫得出來但選不到。它是一筆 tag `0x1000E` NBU 記錄裡 **record+32** 的那個字。
   **不用再用猜的**:

   ```
   python3 research/ui/tools/nbu_probe/nbu_format.py maxima B2_5 --rows 3
     #821   record 0xC1A68D5B  max 2.0 -> 3 rows   write the float at 0xC1A68D7B
     #834   record 0xC1A690B7  max 2.0 -> 3 rows   write the float at 0xC1A690D7  ← 位元深度
     #1650  record 0xC1A747C8  max 2.0 -> 3 rows   write the float at 0xC1A747E8
   ```

   整個 `B2_5` 有 **28 筆**。已知對照:`0xC1A709BC` = 1.0(解析度 2 列)、
   `0xC1A690D7` = 2.0(位元深度 3 列),兩個都是實機用過的。

   ⚠ **同一個列數會重複出現好幾次**(`_excl` 變體、CINE/STILL 各一份)——
   格率 9 列就有三筆(`0xC1A73D63` / `0xC1A744F5` / `0xC1A74B44`)。
   只改一筆可能只有某些情境生效。
6. **建議補到與原廠等長。** 長度欄是死的,所以寫得比原廠短時,
   後面會留著舊內容的殘尾。實測寫 219 bytes 進 257 bytes 的槽仍然成功
   (推測解析器碰到殘尾那半列就停了),但**補滿最乾淨,而且少一個變因**。

> ⚠ 第 6 點裡「殘尾會被忽略」是**推測**,不是量到的。要釘死它:
> 寫一份比原廠短、而且**殘尾剛好是一列完整的舊列**的 CSV,看那列會不會變成鬼影。

## 圖片空間:能不能擴大

**不能加新的,但可以換掉不用的,而且空間比想像中多。**

- 目錄是**開機固化**的(見下一節),所以**沒辦法新增一筆**指向新的圖 ——
  repoint 是死的。
- 但每一張圖都是一個獨立的槽,**原地換掉就會生效**,而且
  **新圖的尺寸可以不同**(w/h 在 XCI 標頭裡,handle 只帶位址與長度)——
  唯一的限制是**編碼後的位元組要塞得進那個槽**。

規模:**2,005 張 xci,合計 2,925 KB**。容器本身只剩 3,486 bytes 的碎片,
所以要空間就得挑犧牲品。現成的:

| 候選 | 大小 | 說明 |
|---|---:|---|
| `L_/M_resolution_{480p,576p,720p,dci4K}` | **23,228 B** | fp 選單沒有這些解析度;Formats 已經用掉 `L_resolution_480p`(3,314 B) |
| `menu_info_japan_set` + `menu_info_canada_set` | 24,968 B | 法規資訊畫面 |
| `cmn_suijunki_1/2` | 22,099 B | 水準儀 |
| `L_focusScale_scaleBar` | 21,384 B | 對焦尺 |

最大的幾個家族:`font_S_imageSize` 182 KB、`L_iso` 123 KB、`qs_iso` 115 KB、
`M_iso` 99 KB、`set_iso` 86 KB —— **光 ISO 四個家族就 423 KB**,
如果不需要完整的 ISO 圖示集,那是很大一塊。

`nbr_stock.py list --ext xci <pattern>` 可以列出任何一組的位址與長度。

⚠ 兩件事沒驗證:**(1)** 換成不同尺寸的圖,widget 的版面會不會跟著調整;
**(2)** 一張圖被畫過之後改它會不會被快取住(圖示那邊**確定**按名字快取 ——
所以 FP3K 才說合成的名字必須是新的)。

## 查找是怎麼做的(源碼,2026-09-29)

```
FUN_c05e8d50(dir, name, &size) -> 資料位移 或 -1
    key = fnv1a(name)                    ; 0xC05E9DE8
    dir[0] = 筆數、dir[4] = 表位址
    對 16-byte 記錄做二分搜尋:
        比 entry[0](hash)
        相同再 strcmp(entry[4], name)    ← 執行期 entry+4 是**字串指標**,
                                            不是映像裡那個名稱池位移
        命中: *size = entry[0xC];  return entry[8]

FUN_c05e5bb8(out, name, res)             ; 兩個呼叫點都是 vtable 方法
    r0 = res + 0xAC                      ; ← 目錄描述子 {筆數, 表位址}
    bl FUN_c05e8d50
    miss → blx res[0x114](out, name)     ; ← 查不到時的**回呼**,res[0x110] 是它的 ctx
    hit  → out[4] = 位移 + res[0xB4]     ; ← res+0xB4 是**資料基底**
           out[0] = 長度
           out[0xC] = 0xC2E0033C         ; vtable
           return 1
```

三件事從這段直接讀得出來:

1. **`entry+4` 在執行期是指標**,映像裡卻是名稱池位移 —— 所以**開機時做過一次 fix-up**。
2. 查找產出的是 `out` 這個 **handle(絕對位址 + 長度)**,消費端拿走。
   **改目錄不會讓已經發出去的 handle 改變。**
3. **miss 時有一個回呼 `res[0x114]`** —— 那是個 RAM 裡的函式指標,不是程式碼 hook。
   要「新增」一個原廠沒有的資源名,這裡是入口。(未驗證。)

`res` 是資源集物件;`res+0xAC` / `res+0xB4` / `res+0x110..0x114` 是它的三個欄位。
**目前還不知道 `res` 在執行期的位址** —— 找到它,repoint 才有機會活過來。

## 容器

```
0xC0D22400  "NBR\0"、版本 1.5、一個空字、然後是長度自帶的記錄
            —— 跟 NBU 容器同一個格式 {u32 tag, u32 size, body},
               tools/nbu_probe/nbu_format.py 兩邊都能拆

  tag 1          177,572 B  at 0xC0D2240C   名稱池:2,260 條以 NUL 分隔的建置路徑
  tag 2       11,817,672 B  at 0xC0D4D9B0   目錄 + 它指向的資料
  tag 0x20001     81,844 B  at 0xC1892C78   (本文未解)
  結束                  8 B  at 0xC18A6C2C
```

tag 2 的 body:`u32 count = 2259`,接著 2259 筆 16 bytes 的 **big-endian** 記錄,
**按 key 升冪排序**:

```
+0x00  u32  FNV-1a(路徑)        查表的 key
+0x04  u32  路徑在名稱池裡的位移
+0x08  u32  資料位移 —— 從 0xC0D22400 起算
+0x0C  u32  資料長度(bytes)
```

**位移是相對容器基底的**,所以不能直接寫絕對位址 —— 這是最容易弄錯的一點。

## 為什麼這不是猜的

三個獨立驗證,全部對著 `out/seg0_c0000000.bin`:

| 檢查 | 結果 |
|---|---|
| 每一筆的 key 是不是它指向的那條路徑的 FNV-1a | **2259 / 2259** |
| 2005 筆 `.xci` 的「基底 + 資料位移」處是不是 `XC\0\0` 圖塊開頭 | **2005 / 2005** |
| 我們算出來的補丁 = fpSup-Formats 實際寫的位元組 | **逐位元組相同** |

第三個最有力。fpSup-Formats v0.3.0a(實機驗證過的第三方卡)在 `0xC0D4DE04` 寫了 8 bytes。
那個位址就是**目錄第 68 筆 + 0x08**,也就是 `B2_5_4.cvm` 的 {資料位移, 長度}。
它把自己的六列 CSV(156 bytes)放在 `0xC12C7CF8`,然後把那筆指過去:

```
$ nbr_stock.py repoint ../MenuB12/data/ListB12/B2_5_4.cvm 0xC12C7CF8 156
  stock: 0xC0F8E7EC  89 B
  write 8 bytes at 0xC0D4DE04: 00 5a 58 f8 00 00 00 9c
  (offset 0x5A58F8 from 0xC0D22400)

$ 那張卡實際寫的     0xC0D4DE04: 00 5a 58 f8 00 00 00 9c
```

**我們從格式本身推出一張別人已經在相機上驗證過的補丁,一個位元組不差。**
測試 `test_we_reproduce_the_bytes_that_card_really_writes` 就是這件事,
而且它讀的是樹裡那張卡的 payload,不是抄來的常數。

## 換一個資源的配方

1. 新位元組放到有空間的地方(Formats 用的是 `0xC12C7CF8`,原本是一塊 XCI 圖塊 —— 它照樣
   進 loader 的 journal,關機寫回,所以原廠圖示會回來)。
2. `nbr_stock.py repoint <path> <新位址> <新長度>` 印出要寫哪 8 個位元組、寫在哪。
3. 兩段都用 loader 的 journal section 寫進去。**沒有任何 hook。**

新的長度可以比原廠大 —— 這正是重點:原地改不下的東西,搬走再改指標就行。

## 整個選單就是 195 個 CSV

`nbr_stock.py list --ext cvm` 全部列得出來,每一個都可以這樣換。幾個入口:

| 路徑 | 是什麼 | 長度 |
|---|---|---|
| `MenuB12/data/ListB12/B2_5_4.cvm` | **解析度列表**(UHD / FHD) | 89 B |
| `MenuB12/data/ListB12/B2_5_1.cvm` … `B2_5_5.cvm` | 同一頁的其他列表(含 `_excl*` 變體) | — |
| `MainMenu/data/ListMenu/B2_2.cvm` | MENU 第二頁的項目 | 221 B |
| `ButtonMenu/data/ListShootingMode.cvm` | 拍攝模式按鈕選單 | 157 B |
| `ButtonMenu/data/ListColorButtonMenu.cvm` | 色彩模式按鈕選單(含兩個 `_EXCL` 變體) | 453 B |

容器裡還有兩個值得記一筆的非 CSV 資源:

- **`CommonObj/data/submenu_width.csv`,274,313 bytes** —— 彈出視窗寬度表。
  `projects/lossless-sup/notes/FIXED_POPUP.md` 當初在跟「共用寬度/同步路徑」纏鬥,
  那條路徑的資料就是這個檔,**而它是可以整個換掉的資源**。沒追過內容。
- 17 個 `.nloc` 字串表、`ipagp.otf`(3.6 MB)、`SimChin_dat_RT.otf`(1.7 MB)等字型,
  同樣都是目錄裡的一筆。`nbr_stock.py list` 全部列得出來。

`_excl` 變體是「某些組合下要排除哪幾列」的版本 —— 灰掉/隱藏在這一層就有表可以改。

## 一列選單的完整資料鏈

```
B2_5_4.cvm   "1,0313,Popup,blank,1,2"
                  │      │     │    └─ Enabled / Enabled2
                  │      │     └────── IMAGE:  XCI 圖示名(blank = 無)
                  │      └──────────── Popup:  彈出頁(或 zzz = 沒有)
                  └─────────────────── TEXT:   字串 id
                                          ↓
English.nloc  "0313" → "UHD 3840x2160"
```

**三層全部是資料,全部可以用同一個 8 bytes 的手法換掉。**

### 欄位

`.cvm` **沒有固定欄位** —— 欄名由第一行決定,195 個檔案裡有 13 種不同的表頭。
拿固定欄位去解會讀錯格(測試裡有守這條)。常見的是
`NO,TEXT,Popup,IMAGE,Enabled,Enabled2`(137 個)。

| 欄 | 意思 |
|---|---|
| `NO` | 第幾列(1 起) |
| `TEXT` | 字串 id,**或直接寫死的字面文字**(見下) |
| `Popup` | 按下去開哪一頁;`Popup` = 一般彈出、`zzz` = 沒有 |
| `IMAGE` | XCI 圖示基底名(`set_imageQuality_1`、`blank`) |
| `Enabled` / `Enabled2` | **`1,2` = 可選,`0,0` = 灰掉** |

**灰掉是資料。** `B2_5_5.cvm`(9 個幀率)與 `B2_5_5_excl.cvm` 內容一模一樣,
只有第 5–9 列(48 fps 以上)是 `0,0`。`_excl*` 就是預先烤好的「這個情境下哪幾列不能選」。

### 字串表 `.nloc`

17 種語言各一個檔,`Common/Strings/<語言>.nloc`:

```
"NDB\0" u32 版本 u32 筆數,然後每筆 8 bytes:
    u32 LE  FNV-1a(ASCII id)
    u8      0
    u24 LE  記錄位移        ← 三個 byte,不是四個:+4 的 LE word 會大 256 倍、超出檔案
記錄: u32 LE id 位移、u32 LE 文字位移,兩者都是 NUL 結尾
```

**17 種語言、46,376 筆,每一筆的 key 都等於 `fnv1a(id)`** —— 解不出來就丟例外,所以
能跑完本身就是驗證。`0313 = UHD 3840x2160`、`0316 = 23.98 fps`、`0004 = Manual Exposure`。

### TEXT 可以直接寫字面文字 —— 不用動 .nloc

fpSup-Formats 的六列 CSV 就是這樣做的(我們從那張卡的 payload 直接讀出來的):

```
NO,TEXT,IMAGE,Enabled,Enabled2          ← 它自己的表頭,連 Popup 欄都沒有
1,0313,blank,1,2                        ← 原廠 id,保留多語系
2,0314,blank,1,2
3,S16 2096x1238,,1,2                    ← 字面文字,.nloc 一個字都沒改
4,OG2K 2000x1334,,1,2
5,OG3K 3008x2000,,1,2
6,OG3.5K 3456x2308,,1,2
```

**所以「加一列」不需要重建 112 KB 的字串表。**

## 最小產物:資料做出第三列

[`tools/menu_row_patch.py`](tools/menu_row_patch.py),測試
[`tools/test_menu_row_patch.py`](tools/test_menu_row_patch.py)(16 項,四次變異都會失敗)。

```
$ python3 research/ui/tools/menu_row_patch.py --append "3K 3008x2000"

../MenuB12/data/ListB12/B2_5_4.cvm
  2 rows -> 3

NO,TEXT,Popup,IMAGE,Enabled,Enabled2
1,0313,Popup,blank,1,2
2,0314,Popup,blank,1,2
3,3K 3008x2000,Popup,blank,1,2

  0xC12C7CF8   121 B  the 3-row CSV, over L_resolution_480p.xci
  0xC0D4DE04     8 B  repoint B2_5_4.cvm at 0xC12C7CF8
  0xC1A709BC     4 B  Settings controller max 1.0 -> 2.0
  -- 3 writes, 133 bytes, no hook
```

**三個寫入、133 bytes、零 hook。** `--autorun` 會印出 34 行 `mem set`,
`--json` 產出給卡片建置用的 section 清單。

### 三個寫入分別在做什麼

1. **新 CSV**:保留原廠表頭,新列的 `TEXT` 直接寫字面文字(所以 `.nloc` 一個字都不用動),
   `Enabled/Enabled2 = 1,2`。
2. **改指標**:`nbr_stock.repoint` 算出來的 8 bytes。
3. **controller 最大值**:`0xC1A709BC`,**big-endian float,值 = 列數 − 1**
   (原廠 1.0 → 三列要 2.0;fpSup-Formats 六列寫 5.0,對得上)。
   **少了這個就是 FP3K 說的「看得到但選不到」。**

### 落腳點的取捨

容器是滿的(`nbr_stock.py room`:1,718 個 3-byte 空隙、共 3,486 bytes),
**新 CSV 一定是寫在某個既有資源上面**。預設犧牲
`L_resolution_480p.xci`(3,314 B)—— 一個 5.02 的 fp 沒有對應選單列的 480p 圖示,
而且 fpSup-Formats 在實機驗證過的卡上犧牲的就是它。
loader 會把每一個動過的字 journal 起來、關機寫回,所以圖示會回來。
`--victim` 可以換別的。

### ⚠ 這個產物只做到 Settings

**列會出現、會被選中,但 Quick Set 的圖磚不會動。** QS 要另外 152 筆 NBU 記錄
(見 [`QUICK_SET.md`](QUICK_SET.md))。回報結果時請把兩件事分開講。

另外:選了這一列之後相機會怎麼錄影,**這個補丁完全沒有處理** ——
它只動 UI,沒有格式註冊、沒有畫布、沒有感測器模式。這是一個 UI 機制的驗證品,不是一個功能。

`mem set` 走 USB shell 會**靜默掉寫入**,必須逐字回讀;做成卡片請走 loader 的 VBIN section。

## 這條路還缺什麼

**只換 CSV 不夠,原廠自己就會卡在這裡:** FP3K 的紀錄說,加一列會「看得到但選不到」,
直到 `0xC1A709BC` 的 Settings controller 最大值變大(三列 2.0、六列 5.0)。
而「畫得出新圖磚」還要 NBU 那一側:影像陣列 `0x1000B` 加狀態、每個伴隨屬性都要跟上、
配置標頭 `0x10002` 的類別計數要改。那半邊在
[`tools/nbu_probe/README.md`](tools/nbu_probe/README.md)。

沒解的:tag `0x20001`(81,844 B)是什麼;`Enabled2` 為什麼是 2 而不是 1;
`_excl` 變體是由哪段程式碼挑的(挑選在程式裡,內容在資料裡)。
還有 —— **本文全部是離線的**。這些補丁在相機上的行為,只有 Formats 那張卡的
`B2_5_4` 那一筆被別人驗證過。
