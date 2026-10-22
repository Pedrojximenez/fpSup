# 格式註冊架構 —— 讓 OG3K 成為真正的第三個選項

> 2026-09-11。目標:在選單裡新增解析度選項,而且**未來要加第四、第五個時只是資料表多一列**。
> 前提是「加寬模式」那條路不能用 —— 它把原廠 FHD 吃掉了,就沒有第三個選項可言。
>
> 接續 `SENSOR_READOUT_NOISE_2026-09-11.md`。

---

## 1. ★ picker 是字串鍵表,不是索引表

```c
/* FUN_c043ccf8 —— 只有六條指令 */
int lookup(obj, table, key) {
    end = table + 0x1a0;                     /* 26 筆 × 16 bytes */
    while (table != end) {
        if (strncmp(key, *(table + 0xC), 15) == 0) return table;
        table += 0x10;
    }
    return 0;
}
```

呼叫端 **`FUN_c043b828`** 組鍵:

```c
key = "";
(*(obj+8) + 0x0C)(obj, key, p);              /* 附加解析度名  "UHD" / "FHD" */
(*(obj+8) + 0x10)(obj, key, p);              /* 附加幀率      "30" "25" "23_98" ... */
if (*(char*)(p + 0x17)) strcat(key, "CROP"); /* 樣板在 0xC0BE4720 */
table = (*(int*)(p+0x20)==4) ? 0xC0BE5810
      : (*(int*)(p+0x20)==3) ? 0xC0BE59B0
      :                        0xC0BE5B50;
entry = lookup(obj, table, key);
if (!entry) { log_error(); entry = 0xC0BE5B50; }   /* 退回表3 第 0 筆 */
```

**每一筆 16 bytes 就是一個完整的格式定義:**

```
+0x00  5            常數
+0x04  profile      處理 profile
+0x08  sensor mode  感光元件模式
+0x0C  key ptr      查詢鍵字串
```

## 2. 三張表 = **三種位元深度**,表3 是 12-bit

> **2026-09-15 訂正:** 本節原標題寫「三張表 = 三種錄影格式,表3 是 CinemaDNG」
> —— 不準確,收回。三張**都是** CinemaDNG,選表的
> `*(int*)(p+0x20)` 就是 `eRawBitType`:**4 = 8-bit(表1)、3 = 10-bit(表2)、
> 其餘 = 12-bit(表3)**。這個誤解直接造成 v0.2.1a 的缺陷 ——
> OG3K 只註冊在表3,選 8/10-bit 時查不到就走原廠的錯誤退回
> `entry = 0xC0BE5B50` = 表3 第 0 筆 = **UHD30**。
> 見 `OG3K_8BIT_10BIT_FALLS_BACK_TO_UHD.md`。

感光元件模式三張表幾乎完全相同,**差的是 profile,系統性差 20**:

```
key        mode   表1    表2    表3
UHD30        7    131    151    171
FHD30      106    135    155    175      ← 175
FHD60       27    133    153    173
```

`FHD30` 在表3 是 **profile 175** —— 正是筆記裡「`r5 = 175` → SoA row 122」那個。
**所以 12-bit CinemaDNG 走表3。** 表1/表2 是同樣的格式,只差位元深度
(profile 系統性差 20,實際欄位只差 `+0x080`/`+0x084` 兩個平面格式碼)。

例外:只有 idx24/25(`FHD120CROP`/`FHD100CROP`)的感光元件模式在表3 不同。

## 3. 解析度名是指標表,長度不受限

```
0xC0BE4510  { 222, ptr("UHD"),     6,  53 }     第 1 組(對應表1)
0xC0BE4520  { 222, ptr("FHD"),     6, 371 }
0xC0BE4530  { 222, ptr("UHDCROP"), 6, 373 }
0xC0BE4540  { 222, ptr("FHDCROP"), 6,  61 }
0xC0BE4550  ...                                  第 2 組,+0x40
0xC0BE4590  ...                                  第 3 組,+0x80
```

字串本體在 `0xC0BE45E4`(`"UHD\0FHD\0UHDCROP\0FHDCROP\0"`)。
**因為是指標,新名字可以放在 cave、任意長度** —— `OG3K` 沒有長度問題。

### 3.1 解開了:表基底是 0xC0BE4508,每筆 `{6, id, 222, name_ptr}`

先前把邊界抓錯了一個字。正確的是:

```
0xC0BE4508  { 6,  71, 222, ptr("UHD")     }   表3(CinemaDNG)第 0 筆 ... 見下
0xC0BE4518  { 6,  73, 222, ptr("FHD")     }
0xC0BE4528  { 6, 391, 222, ptr("UHDCROP") }
0xC0BE4538  { 6, 393, 222, ptr("FHDCROP") }
```

三張表的基底是 **`0xC0BE4508` / `0xC0BE4548` / `0xC0BE4588`**,各 4 筆 × 16 bytes = `0x40`,
對應 picker 的三張表。CinemaDNG 是第三張 `0xC0BE4588`:

```
表1 0xC0BE4508   UHD=51  FHD=53  UHDCROP=371  FHDCROP=373
表2 0xC0BE4548   UHD=61  FHD=63  UHDCROP=381  FHDCROP=383
表3 0xC0BE4588   UHD=71  FHD=73  UHDCROP=391  FHDCROP=393   ← CinemaDNG
```

**`+0x04` 就是解析度 enum。** 由 `FUN_c043d7b8` 證實:

```c
int by_id(table, id, key) {
    end = table + 0x40;
    while (table != end) {
        if (*(int*)(table + 4) == id) break;      /* 比對 +0x04 */
        table += 0x10;
    }
    if (table == end) return 0;
    if (key == 0) return table;
    return strncmp(*(char**)(table+0xC), key, len(key)) ? 0 : table;
}
```

### 3.2 三個查表函式,形狀完全一樣

```
FUN_c043ccf8(obj, table, key)   picker:  <名><幀率>[CROP] → entry    表尾 +0x1a0 (26 筆)
FUN_c043cf38(obj, table, key)   解析度:  <名>[CROP]      → entry    表尾 +0x40  ( 4 筆)
FUN_c043d7b8(table, id, key)    反查:    enum            → entry    表尾 +0x40  ( 4 筆)
```

呼叫端 `FUN_c043b828`(picker) 與 `FUN_c043bc68`(解析度) 都用**同一個虛擬呼叫
`(*(obj+8)+0x0C)`** 組出解析度名。

**表尾都是寫死的常數,所以不能原地 append —— 三個都要 hook。**

## 4. 可用的 donor:四個現成的 3032×2012 模式

電影 picker 只引用 70 個模式裡的 28 個。沒被引用、且幾何已經是 3032×2012 的:

```
mode  98   hmax 445   77.3 fps    安靜類比組  R = 0.55
mode 143   hmax 445   18.0 fps    安靜類比組
mode  11   hmax 330  105.4 fps    快速類比組  R = 0.97
mode 117   hmax 330   99.9 fps    快速類比組
```

**它們本來就是 2012 行,連加寬都不用做。**

## 5. 幀率可行性(3032×2012)

讀出時間 = hmax × 2012 / 72 MHz。hmax 445 → 12.435 ms;hmax 330 → 9.222 ms。

```
key          一格 ms   hmax445  hmax330
OG3K23_98    41.708      ✓        ✓
OG3K24       41.667      ✓        ✓
OG3K25       40.000      ✓        ✓
OG3K30       33.367      ✓        ✓
OG3K48       20.833      ✓        ✓
OG3K50       20.000      ✓        ✓
OG3K60       16.683      ✓        ✓
OG3K100      10.000      ✗        ✓
OG3K120       8.342      ✗        ✗
```

**OG3K120 不可能。** 全機最小 hmax 是 330,3032×2012 的上限是
`72e6 / (330 × 2012)` = **108.4 fps**。那一格只能留原廠 FHD120。

## 6. 一個模式一組時序 → hook 順手改時序

七個 ≤60 的幀率不能同時掛在 mode 98 上。解法是讓 hook 在查表時寫入時序 ——
查表正好發生在格式套用、感光元件被程式化之前。時序**全部抄原廠對應模式的**,
所以每個幀率都是精確值:

```
key          donor  hmax/tail/vmax   抄自      fps       捲簾
OG3K23_98     98    445/585/6748    mode 109  23.976   12.435 ms
OG3K24        98    445/1145/6740   mode 218  24.000   12.435
OG3K25        98    450/450/6400    mode 125  25.000   12.575
OG3K30        98    445/735/5398    mode 106  29.970   12.435
OG3K48        98    445/795/3370    mode 220  48.000   12.435
OG3K50        98    450/450/3200    mode 115  50.000   12.575
OG3K60        98    445/1035/2698   mode  27  59.940   12.435
OG3K100      117    330/270/2182    計算      100.000   9.222
```

profile 沿用同幀率 FHD 在表3 的值(175/173/…)。

## 7. 選單三件,機制都確定了

**① 字串記錄放得下 14 字元。** 記錄是 28 bytes:

```
08 00 00 00 | 0d 00 00 00 | "0314"\0 | "FHD 1920x1080" | \0 \0
  表頭          宣告長度       id          13 字元         填充
```

14 字元:`4+4+5+14+1 = 28`,大小不變,**只要把長度欄 13 改成 14**。
`OG3K 3008x2000` 剛好。17 種語言各一份。

**② 「看得見但選不動」** —— 社群交接文件:

> `Adding a CSV row alone made the option visible but unselectable.`
> `Settings controller max at C1A709BC had to become float 2 instead of 1.`

`0xC1A709BC` 的位元組是 `3f 80 00 00`。**這個結構是大端序**(旁邊 `00 00 00 03`、
`00 00 00 0a`、`00 00 00 01`),所以那是 **BE float 1.0**。改成 BE float 2.0:

```
mem set 0xC1A709BC 0x00000040      stock 0x0000803F
```

**③ CSV 三列塞得下。** 原廠 89 bytes,拿掉 `Popup` 欄、資料列用裸 `\n`:

```
<BOM>NO,TEXT,IMAGE,Enabled,Enabled2\r\n
1,0313,blank,1,2\n
2,0314,blank,1,2\n
3,XXXX,blank,1,2\n          ← 86 bytes,還剩 3
```

## 8. QS 是另一回事

`UHD`/`FHD` 在 QS 的標籤住在**固定 4 bytes 的槽**(`0xC07481E4`、`0xC0748A1C`):

```
'HI\0\0'  'MED\0'  'LOW\0'  'UHD\0'  'FHD\0'
```

`OG3K` 加 NUL 要 5 bytes,塞不進去。三條路:

- 縮成 3 字元(`3K` / `OG3`),直接放得進
- 照社群做法用圖片資源(`FP3K_QS.xci`),但他們警告
  `Changing only resolution-image keys broke QS. Every companion layout/visibility/
  animation property needs the new state.` —— 47 個群組、380 個資源變更
- 先不做 QS

## 9. 完整架構

```
cave 裡的格式表(純資料):
   { key:"OG3K30", profile:175, donor:98,  hmax:445, tail:735,  vmax:5398 }
   { key:"OG3K60", profile:173, donor:98,  hmax:445, tail:1035, vmax:2698 }
   { key:"OG3K100",profile:178, donor:117, hmax:330, tail:270,  vmax:2182 }
   ...

hook A   FUN_c043ccf8       格式鍵 "OG3K<rate>" → 寫 donor 時序 → 回傳我們的 entry
hook B   FUN_c043cf38       解析度名 "OG3K" → 回傳我們的第 5 筆
hook C   FUN_c043d7b8       enum 75 → 回傳我們的第 5 筆
hook D   C043A19C           依 entry 分派畫布,不再無條件 3032×2012
資料     選單               CSV 第三列 + 字串記錄 + C1A709BC

三個查表 hook 的實作一樣:進入時先掃我們自己的表,命中就直接 return,
否則跳回原廠迴圈。每個約 15 條指令。

新 enum 取 **75**(表3 的 UHD=71 / FHD=73 之後),表1/表2 對應 55 / 65。
```

**加第四、第五個格式 = 格式表多幾列,程式一個字都不用改。**

## 10. 下一步

```
1  解開 0xC0BE4510 的 +0x0C(53/371/373/61…)    決定 hook B 的做法
2  把加寬那七個模式的 patch 退掉                 恢復原廠 FHD
3  量掉 mode 106 加寬版的素材                    確認安靜組真的給 R=0.55
```

第 3 項是前提:格式表把 donor 98 放在所有 ≤60 的幀率上,是建立在「安靜類比組
真的給 0.55」這個假設上。064/065 證明的是「picker 指向 98」,這次是「加寬 106」,
機制不同,還沒實測確認。

---

# 第二部分:全鏈打通(2026-09-11 晚)

三個 hook 的設計不必全做 —— 實機追下去發現**解析度名不是來自 enum,
而是來自「請求的寬高」**,整條鏈因此短了一大截。

## 11. 解析度名發射器:比對寬高,不是查 enum

函式指標表在 **`0xC0BE44D0`**(靜態,在映像裡),從執行中的相機讀出來:

```
物件       0xC375E8DC
函式表     0xC0BE44D0
  +0x00  0x00000000
  +0x04  0xC0BE639C
  +0x08  0xC043AE48
  +0x0C  0xC0437B48   ← 解析度名發射器
  +0x10  0xC043CAF0   ← 幀率發射器
  +0x14  0xC043BE68
```

**因為是靜態函式指標表,換發射器只要改 `0xC0BE44DC` 一個字**,不必掛程式碼 hook。

`FUN_c0437b48` 的邏輯就是一條比對鏈:

```
name = "FHD"                      預設        r4 = 0xC0BCFE88
(w,h) == (4096,2160)  →  "DCI4K"              r4 = 0xC0BCFE90
(w,h) == (3840,2160)  →  "UHD"                r4 = 0xC0BCFE8C
(w,h) == (1280,720)   →  "HD"                 r4 = 0xC0BCFE98
```

配對表:

```
0xC0BCFE70  { 4096, 2160 }        字串  0xC0BCFE88 'FHD'
0xC0BCFE78  { 3840, 2160 }              0xC0BCFE8C 'UHD'
0xC0BCFE80  { 1280,  720 }              0xC0BCFE90 'DCI4K'
                                        0xC0BCFE98 'HD'
```

`w`/`h` 來自 `request+8` / `request+0xC`。

## 12. ★ 這解開了一個舊死路

`CANVAS_IS_NOT_THE_SETTINGS_BLOCK.md` 的結論是「改 `MenuItemMovieRecSize`
(`0xC0742204`)和設定區,對 DNG 沒有作用」。**那個結論本身沒錯,但我們看錯輸出了。**

它不控制畫布,但它控制**設定裡的寬高**,而寬高一路決定到感光元件模式:

```
選單 → MenuItemMovieRecSize → 設定寬高 → 發射器比對 → 名字 → 鍵 → picker → 模式
```

當年量的是「DNG 有沒有變」,而畫布另有來源(`C043A19C`),所以看起來毫無反應。
那條路其實是主幹道,只是出口不在當時看的地方。

## 13. 實機驗證的三步

用 `ogdev.py` 在 USB shell 上做,每一步秒級迭代。

**第一步:證實 picker 查表點是活的。** `keylog.S` 掛在 `FUN_c043ccf8` 進入點,
記下 `(table, key)`。立刻命中:

```
 #       table  key
 0  0xC0BE5B50  'FHD30'
```

`0xC0BE5B50` 是第三張表 —— 證實了「CinemaDNG 走表3」(原本只是從 profile 175 推的)。
順帶:`FUN_c043cf38`(只查解析度名那個)全程 **0 次命中**,這條流程不走它。

**第二步:證實 hook 能回傳自製 entry。** `fmthook.S` 在鍵 == `"FHD30"` 時回傳
cave 裡的 `{ 5, 175, 117, ptr }`,其餘跳回原廠迴圈。錄一段後
`0xC343B590` 讀回 **117**(原廠會給 106)。命中 24,398 次,相機正常。

**第三步:全鏈。** 四個字:

```
0xC0BCFE80  1280 -> 3032     徵用 {1280,720}→"HD" 那一支
0xC0BCFE84   720 -> 2012
0xC074222C  1920 -> 3032     MenuItemMovieRecSize enum2
0xC0742230  1080 -> 2012
```

選單切一次之後,keylog 記到新的鍵:

```
 1  0xC0BE5B50  'HD30'       ★
```

再把 entry 的 donor 改成 mode 98、時序寫成 `445/735/5398`(= 29.97003,0 ppm),
錄一段:**`0xC343B590` = 98**。

**整條鏈走的是韌體自己的機制,跟原廠選 UHD 同一條路,只是查表點多了一筆我們的 entry。**

## 14. 一個差點出事的地方

第三步之前檢查時發現 **mode 98 的時序沒有被套用** —— 卡上是 `og3k_autorun`
(加寬七個模式那版),它不含 `mode98_autorun` 的時序補丁,mode 98 還是出貨的
77.267 fps。拿它當 29.97 的 donor 會錄出錯的東西。

**donor 的時序必須由格式表自己寫入,不能假設開機時已經套好。**
這正是 §6 設計裡「hook 順手改時序」存在的理由。

## 15. 現在缺的只剩填資料

```
✓ 名字     徵用 "HD" 那一支,兩個字
✓ 鍵       "HD30" 自動組出
✓ entry    hook 回傳自製 entry,實機驗證兩次
✓ donor    mode 98/117/11/143 現成,時序照抄原廠
✓ 畫布     C043A19C 已在跑
```

收尾三件:

1. **字串指標** —— `0xC0437C34/38` 的 movw/movt 改指向 cave 的 `"OG3K"`,
   內部鍵就變成 `"OG3K30"`,跟選單標籤一致。兩個字。
2. **選單標籤** —— 字串記錄長度欄 13→14,顯示 `OG3K 3008x2000`。17 種語言。
3. **第三列** —— CSV 三列 + `0xC1A709BC` = BE float 2.0,讓 OG3K 與原廠 FHD 並存。
   在此之前是「FHD 那一格就是 OG3K」。

加第二、第三個幀率只是格式表多幾列:
`"HD60"` → donor 98 + `445/1035/2698`、`"HD100"` → donor 117 + `330/270/2182`。

## 16. 開發環境

`codex/opengate/ogdev.py` —— 組譯、上傳、掛鉤、回讀,全部走 `mem set/get`,
**不碰 host 工具的暫存區**(`0xC072F800`–`FE00`),所以 open gate 的 hook 可以
同時活著。原值記在 `.ogdev_state.json`,`off` 一行還原。

```
./ogdev.py up  keylog.S 0xC0730200      組譯上傳並逐字驗證
./ogdev.py arm 0xC043CCF8 0xC0730200    用 B 指令掛上(自動記原值)
./ogdev.py off 0xC043CCF8               還原
./ogdev.py log                          讀紀錄
```

開發用 cave:**`0xC0730000`–`0xC0732A00`**(10 KB,映像裡為空,避開 USB shell
worker 與 host 工具暫存區)。

payload 骨架(掛在函式進入點,原指令位移後補回):

```asm
entry:
    push    {r3, r4, ip, lr}
    ... 判斷 ...
    LDA     r0, ENTRY            @ 命中:直接設回傳值
    pop     {r3, r4, ip, lr}
    bx      lr
pass:
    pop     {r3, r4, ip, lr}
    push    {r4, r5, r6, r7, r10, r11, lr}   @ 位移的原指令
    LDA     ip, BACK
    bx      ip
```

---

# 第三部分:三格式並存(2026-09-12)

**OG3K 成為選單裡真正的第三個選項,與原廠 UHD / FHD 並存,任何切換順序都正確。**
實機驗證:

```
A001_077   3032×2012   OG3K
A001_078   3856×2170   UHD
A001_079   3032×2012   OG3K      ← UHD → OG3K
A001_080   1936×1090   FHD
A001_081   3032×2012   OG3K      ← FHD → OG3K
```

## 17. 第三列一直都有身分:enum 4

先前以為「第三列在下游分不出來」,是因為只看了發射器收到的請求結構
(兩列逐位元組相同)。**往上一層看就有了。**

解析度 setter `C005C020`(`push {r4,r5,r6,lr}`,r0=obj r1=enum r2=flag)掛上
logger 之後:

```
第一列 UHD   →  enum 3
第二列 FHD   →  enum 2
第三列 OG3K  →  enum 4      ★
```

下游看起來一樣,是因為 `MenuItemMovieRecSize`(`0xC0742204`)只有
`{2→1920×1080, 3→3840×2160}` 兩筆,**enum 4 查不到尺寸**。

五個設定 setter 的進入點完全相同,都是 `E92D4070`:

```
C005C020 解析度   C005BE58 格式   C005BEF0 品質   C005C0B8 幀率   C005BB60 裁切
```

## 18. ★ 走錯的那一步:以為 fallback 會落到 enum 2

第一版讓 setter hook 依 enum 改寫 `MenuItemMovieRecSize` 的 enum-2 尺寸對
(enum 4 → 3032×2012、其餘 → 1920×1080),想法是「enum 4 查不到就會用 enum 2 那一筆」。

**從 FHD 切過來成立,從 UHD 切過來不成立。** 實測:

```
setter 命中 4 次  最後 enum = 4  旗標 = 1
MenuItemMovieRecSize enum2 = 3032 × 2012     ← 我們寫進去了
主設定 = 3840 × 2160                          ← 但設定沒跟著走
```

**enum 4 查不到尺寸時的行為是「保持原值」,不是落回 enum 2。** 所以結果取決於
前一個選的是什麼 —— 這種相依於歷史狀態的設計不可靠,整條路要換掉。

## 19. 最終架構:一個旗標,四個各自獨立的零件

```
og3ksel     72B   掛 C005C020    enum 4 → 旗標 0xC0731C08 = 1,其餘 = 0
og3kname    88B   換 0xC0BE44DC  旗標 1 → 暫時把 request+8/+0xC 換成 3032×2012
                  (函式指標一個字) 呼叫原函式,再還原;旗標 0 → 尾呼叫原函式
rowpatch   252B   掛 C043A19C    旗標 0 就原樣放行,不再無條件覆寫 1936×1090
fmttable   132B   掛 C043CCF8    格式表 8 個幀率,寫 donor 時序後回傳 entry
```

**完全不碰 `MenuItemMovieRecSize`**,尺寸對永遠是原廠 1920×1080,FHD 不受影響。
解析度名不再依賴尺寸,而是直接由旗標決定 —— 所以跟切換順序無關。

發射器是**靜態函式指標表**(`0xC0BE44D0` slot `+0x0C`),所以「換掉發射器」是
改一個字,不是掛程式碼 hook,原函式完好無損,還能被我們尾呼叫。

## 20. 選單資料三件

```
CSV  0xC0F8E7EC   三列 86 bytes:  1,0313 / 2,0314 / 3,OG3K
                  拿掉 Popup 欄、資料列用裸 \n 才塞得下
上限 0xC1A709BC   BE float 1.0 → 2.0 (寫 0x00000040)。不改的話第三列
                  看得見但游標移不下去。
名字 0xC0BCFE80   發射器配對表第三支 {1280,720} → {3032,2012}
     0xC0437C34/38  該支的字串指標 → cave 的 "OG3K"
```

`{1280,720}→"HD"` 那一支 CinemaDNG 用不到,徵用它。

## 21. 坑:活的 payload 不能原地改

把 `rowpatch` 從 232B 換成帶旗標守衛的 252B 時,直接逐字覆寫 `0xC072F800`
—— **相機當場當掉**。那段程式碼被 `C043A19C` 指著,取景時每秒執行幾十次,
逐字覆寫會執行到半新半舊的混合。

先前換 `fmttable` 沒事,是因為那些 payload 都放在**新位址**、最後才 arm,
順序天然正確。

**規則:換一段已經被 hook 指著的 payload,必須先解除 hook。**
`og3k_load.py` 現在會自動處理:偵測到 payload 需要更新就先寫回原廠指令。

## 22. 已知邊界

- **冷開機後第一次選 OG3K 之前,旗標是 0。** setter 沒被呼叫過,所以
  開機若停在 OG3K,那一次會錄成 FHD。重新選一次即可。
  之後可在 loader 裡補上開機讀一次目前 enum。
- **外層設定摘要、HUD、QS 仍顯示 FHD/UHD。** 那三處是圖片資源
  (`Y4_1_3_2_FHD` / `set_resolution_1` / `qs_resolution_1_S` 那一族),
  不是文字。社群為此做了私有 NBR 資源包並改了 380 個資源項。
- 子選單清單的文字**可以**熱改:CSV 的 `TEXT` 欄有字面 fallback
  (`C05EBE58`),鍵查不到就直接顯示字面值,所以不必碰本地化字典。

## 23. og3k_load.py

一行把整套裝回執行中的相機,冪等,`--check` 只檢查不寫。

```
發射器配對 / cave 字串 / 原函式字串指標 / og3kname + 函式指標
MenuItemMovieRecSize 保持原廠 / 控制器上限 / 選單 CSV
格式表 8 筆 / fmttable payload / 畫布 payload + hook
og3ksel payload + setter hook / picker hook(最後 arm)
```

兩個 hook 有「既非原廠也非我們的就停手」的保護;畫布 payload 需要更新時
會先解除 hook。前提是卡上有任何提供 `C043A19C` 掛點的 build。

---

# 第四部分:外層摘要(2026-09-12)

**結論:摘要的文字路徑只能顯示數字,做不到 "OG3K"。** 要顯示文字得走圖片資源,
那是另一個工程段落。以下是把這件事釘死的過程。

## 24. enum → 顯示狀態的映射本來就是對的

`MV_Resolution` 的顯示映射:

```
FUN_c06bd988(obj, enum)
   → 虛擬呼叫 vtable+0x5C 取得 (table, count)
   → FUN_c06ccd10(enum, table, count, 0)

/* FUN_c06ccd10 —— 通用的 {key,value} 配對查表,預設值 param_4 */
for (i = 0; i < count; i++)
    if (table[i*2] == key) return table[i*2+1];
return default;
```

掛 logger 記下 `(key, table, count)`,實機讀到:

```
表 0xC2E4020C,3 筆
  { 3, 0 }   UHD   → 顯示狀態 0
  { 2, 1 }   FHD   → 顯示狀態 1
  { 4, 2 }   OG3K  → 顯示狀態 2
```

**這張表是跟著 CSV 的列數建出來的** —— 我們加了第三列,它自己就多了第三筆。
所以 enum → 狀態這一段完全不需要動。

缺的是「狀態 2 沒有對應的視覺資源」,所以退回顯示 FHD。

## 25. 綁定機制正常,只是狀態 2 沒綁

一個字的實驗:把表裡 `{4, 2}` 改成 `{4, 0}`,摘要立刻變成 **UHD**。

所以狀態 → 資源的機制是好的,單純是狀態 2 沒有東西可指。

## 26. 資源家族(閒置的材料)

```
Y4_1_3_2_UHD / _FHD / _DCI4K            摘要,三個 —— DCI4K 在 fp 上永不顯示
set_resolution_1 / 2                     兩個
M_resolution_1 / 2 / 480 / 576 / 720     五個(480/576/720 是舊制,閒置)
L_resolution_1 / 2 / 480 / 576 / 720     五個
qs_resolution_1_S / 2_S                  兩個
font_menu_MB_resolution_1 / 2            兩個
```

`Y4_1_3_2_DCI4K` 的 NBU 記錄與 `Y4_1_3_2_UHD` 的**結構完全相同**,差別只在資源名
偏移與一個數值鍵(`0x12D1` vs `0x1128`,不是池偏移,語意未解)。
**第三個狀態的資料是現成的,缺的是「狀態索引 → 記錄」那條連線。**

引用位置(大端序池偏移,在 NBU 記錄區):

```
Y4_1_3_2_UHD    偏移 0x2455C   引用於 0xC2C22886 / 0xC2C23B76
Y4_1_3_2_FHD    偏移 0x2454C   引用於 0xC2C1FD06 / 0xC2C266CA / 0xC2C279B0
Y4_1_3_2_DCI4K  偏移 0x2453C   引用於 0xC2C1EA20
```

## 27. ★ CSV 的 IMAGE 欄留空 = 切換成文字渲染

第三列從 `3,OG3K,blank,1,2` 改成 `3,OG3K,,1,2`(IMAGE 欄空),摘要立刻從 FHD
變成一個字面的 **`3`**。

這跟社群照片上的結果完全一致(`settings summary literal 3`)。

## 28. ★ 但那個文字是「NO 欄被當數字解析」

社群當時的第三列是 `3,3K 3000x2000,,1,2` —— `NO` 是 `3`、`TEXT` 首字也是 `3`,
所以他們分不出來顯示的是哪一欄。我們的 `TEXT` 是 `OG3K`(首字 `O`)卻仍顯示 `3`,
**所以不是 TEXT**。

再把 `NO` 改成 `3K` 測多字元:**還是顯示 `3`**。第三列仍在、仍可選。

`atoi("3K") = 3`。**摘要把 NO 欄當整數解析後顯示,所以只可能是數字。**

這條路到此為止。要在摘要顯示 "OG3K" 必須把狀態 2 綁到一個圖片資源
(徵用閒置的 `Y4_1_3_2_DCI4K` 是最短路徑,再替換那張點陣圖),
也就是社群做私有 NBR 資源包那條路。

## 29. 最終採用的 CSV

```
<BOM>NO,TEXT,IMAGE,Enabled,Enabled2\n
1,0313,blank,1,2\n
2,0314,blank,1,2\n
3,OG3K 3008x2000,,1,2              ← 最後一列不收尾換行
```

**剛好 89 bytes。** 標頭與資料列全部用裸 `\n`、最後一列省掉換行,才塞得下完整標籤。
(社群的紀錄:`uses LF separators without final newline to fit`。)

結果:

```
子選單清單   OG3K 3008x2000      完整標籤
外層摘要     3                    數字,但至少不是誤導的 FHD
HUD / QS     仍是 UHD/FHD 的圖    未處理
```

錄影功能完全不受這些影響 —— 拍攝走的是 `og3ksel` 維護的旗標,跟 CSV 與資源綁定無關。
