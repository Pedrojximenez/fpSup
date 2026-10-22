# CRCT 的縮減路徑:Hbin / Hbin2 / Vbin 與 RWZM 不是同一組

> ⚠ **2026-09-21:本文三項結論已被推翻**,見
> [`CRCT_PATH_SELECTOR_SOLVED.md`](CRCT_PATH_SELECTOR_SOLVED.md)。
> §1b「ops 表執行期組出來、靜態解不到」——**錯**,是 ROM 常數 `0xC0B5FCC0`,`+0x9C` = `FUN_c0325228`。
> §1c「感測器描述子不在檔案裡」——**錯**,`out/seg1_c2ef6e00.bin` 一直都在。
> §5.6「hbin 會被清掉」「沒有一個案例兩邊同時開」——**錯**,hbin 被搬到第二級水平 binning(`0x300F08C0`),
> 而錄影分支把 `0x300F0870` 設成 1,兩邊同時作用。


2026-09-14。寫這份是因為讀過這棵樹的人**反覆把 Hbin 系列和 RWZM 當成互斥的選項**。
它們不是。本文從韌體讀出結構,不是從既有筆記轉述。

---

## 0. 一句話

**a0 / a7 兩個校正視窗各自從六個輸出裡挑一個(Hbin、Hbin2、Vbin 是其中三個);
RWZM 掛在另一個緩衝 bufa1 上,只有開跟關。兩組欄位在結構上互相獨立。**

問「這台是 Hbin 還是 RWZM」本身就問錯了 —— 它們不是同一個欄位的兩個值。

⚠ 但「獨立」不等於「可以隨意並用」:**執行期有仲裁**,RWZM 作用時 hbin 會被
條件性清掉(見 §5.6),而 §2 三個實測案例沒有一個兩邊同時開。

---

## 1. 結構,從 `--crct_path--` 的除錯輸出讀出來

`ImagerAcqInThr.cpp`(字串 `0xC0B57100`)有一段把整條 CRCT 路徑印出來的程式碼,
在 **`0xC031DCE0 .. 0xC031E060`**。它的分支就是路徑選擇的忠實鏡子:

```
[r5+0]  bufa0 啟用      → "bufa0_rec_on"  / "bufa0_rec_off"
[r5+4]  bufa0 輸出選擇  → 六選一(下表)
[r5+1]  bufa7 啟用      → "bufa7_rec_on"  / "bufa7_rec_off"
[r5+8]  bufa7 輸出選擇  → 六選一(同一張表)
[r5+2]  bufa1 啟用      → "bufa1_rec_on"  / "bufa1_rec_off"
        ⚠ bufa1 沒有選擇器 —— 只要開著,輸出固定是 CrctRwzmToBufA
[sp+0x30] main hvbin_bypass      [sp+0x31] sub hvbin_bypass
最後     "rec      hbin   :%04d, vbin  :%04d"
```

**選擇器 enum**(`0xC031DD08` 與 `0xC031DE3C` 的兩段 `subs/blo/beq` 階梯,兩邊相同):

| 值 | 輸出 | 字串(a0 / a7) |
|---|---|---|
| 0 | `CrctGainToBufA` | `0xC0B5718C` / `0xC0B5721C` |
| 1 | `CrctCrmfToBufA` | `0xC0B5716C` / `0xC0B571FC` |
| 2 | `CrctVbinToBufA` | `0xC0B571CC` / `0xC0B5725C` |
| 3 | `CrctHbinToBufA` | `0xC0B571AC` / `0xC0B5723C` |
| 4 | `CrctHbin2ToBufA` | `0xC0B57324` / `0xC0B57378` |
| 5 | `CrctSpcToBufA` | `0xC0B57348` / `0xC0B5739C` |

`CrctRwzmToBufA` 的字串是 `0xC0B573CC`,前綴是 **`bufa1 :`** 而不是
`crct1_win_aN :` —— 前綴不同就是在講不同的東西,這是最早能看出區別的線索。

---

## 1b. 那六個名字是一個 3-bit 硬體多工器

選擇器不是軟體概念,它直接進硬體。`0xC031DC44`/`0xC031DC4C` 把剛決定好的值
餵給兩個 Thumb 小函式:

```
0xC0635CA8(a0):  0x300F06B0 &= ~7;  |= selector
0xC0635CD0(a7):  0x300F06D0 &= ~7;  |= selector
```

所以 **Gain / Crmf / Vbin / Hbin / Hbin2 / Spc 是同一個 3-bit 欄位的六個檔位** ——
它選的是「CRCT 鏈上哪一個抽頭餵進輸出緩衝」。決定在 `0xC0320AF0` 裡做,
結果在 `0xC031DC04..0xC031DC40` 抄進描述子,然後立刻下到硬體。

### ⚠ 選了 Hbin ≠ 正在做 binning

H/V binning 的**級本身是另一塊硬體,有自己的 bypass**,位址也在不同區塊:

```
0xC0635D00:  0x30100980 = r0 | (r1 << 4) | (r2 << 8)
             bits[7:4]  = main hvbin_bypass
             bits[11:8] = sub  hvbin_bypass
（另有 0xC06345C0 寫 0x30001 0E0 與 +4 的兩組 2-bit 欄位)
```

mux 檔位(在 `0x300F06Bx`)和 binning 級的 bypass(在 `0x30100980`)是**兩件事**,
可以互相矛盾。這也是為什麼那段除錯輸出會把
`crct1_win_a0 : CrctHbinToBufA` 和 `main hvbin_bypass_on` 分兩行印 —— 它們回答不同問題。

### 決定是誰做的:一張執行期的 ops 表,不是靜態分支

追到底了。呼叫鏈:

```
0xC031DBB0  bl  0xC0322E48(0)        → 取得 imager 物件 sl
0xC031DBBC  ldr r1, [sl, #0xD0]      → ops 表指標
0xC031DBC4  ldr r3, [r1, #0x9C]      → 「算 CRCT 路徑」那一格
0xC031DBD0  blx r3   (r0=sl, r1=輸入幾何 sp+0x5C, r2=輸出結構 sp+0x10)
```

呼叫前先填好預設值,這很說明問題:

```
sp+0x34/38/3C/40 = 1        hbin/vbin 係數預設 1(不 bin)
sp+0x44/48/4C/50 = 0x400    比率預設 unity
```

**所以是 ops 表那一格在覆寫預設值,決定 mux 檔位與係數。**
`0xC0322E48(0)` → `0xC0322E88()` → `0xC03255F8(0xC2F1E654)`,而 `0xC03255F8` 走的是
RAM singleton `0xC343B588` —— **表在執行期組出來,靜態解不到具體實作**。

相關 RTTI 類別名:`PictureQualityCommonCrct`(`0xC2E37AD8`)與
`PictureQualityCommonCrct_xz01`(`0xC2E38A7B`)。

⚠ **這也解釋了為什麼 Hbin/Hbin2 會隨模式變** —— 那格是每個感測器模式各自的實作,
不是一段帶條件的共用程式碼。要定案只能上機讀 `[obj+0xD0]+0x9C` 的實際值再反組譯。

### Hbin 與 Hbin2 的差別:未定

**已知**:整條路徑只有**一組** `hbin` / `vbin` 係數(錄影一組、live view 一組,
結尾以 `rec      hbin   :%04d, vbin  :%04d` 印出,來源 `sp+0x6C`/`sp+0x70` 與
`sp+0x64`/`sp+0x68`)。**所以 Hbin2 不是「第二個倍率」。**

**推論(未證實)**:enum 的順序 Gain(0) → Crmf(1) → Vbin(2) → Hbin(3) → Hbin2(4) →
Spc(5) 若等於管線順序,Hbin2 就是**鏈上更後面的第二個水平抽頭**,而不是另一種演算法。
這只是順序推測,**沒有量過**。

**`CrctSpcToBufA` 的 Spc 是什麼,也還不知道。**

**`0xC0320AF0` 不決定 mux** —— 它在 `0xC031DC00` 被呼叫,比 ops 表那一格
(`0xC031DBD0`)**晚**,而且拿到的是 `sp+0x34/0x3C/0x44/0x4C` 四個指標(抽頭數與
比率),不碰 `sp+0x14`/`sp+0x18` 那兩個 mux 欄位。

它**確實**是另一半的決策點:經 `FUN_c032d9a0` 算出 hbin/vbin 抽頭數與比率夾制,
細節見 §5.2/§5.5。所以這條路徑有**兩個決策點**,分別管 mux 與 binning,
一開始把它們當成同一個是錯的。

---

## 1c. ⚠ `out/MAIN_c0000000.bin` 在 0xC2EF6E00 以上是垃圾

追上面那條鏈時撞到的,**會讓人得到看起來合理但完全錯誤的結論**:

```
檔案實際     49,482,954 bytes  (0x2F30CCA)
DFI 宣告     49,245,696 bytes  (0x2EF6E00)   ← seg0 的 usize
超出         237,258 bytes
```

`FORMAT.md` §3 早就寫了「解壓後需截斷到 DFI 宣告的 usize(最後一個 flag byte 會多吐
幾 byte)」,但 `tools/unpack.py` **從來沒截**。於是 `0xC2EF6E00`(seg1 的載入位址)
以上讀到的是 LZSS 溢出的殘餘,長得像位移過的真資料。

感測器描述子 `0xC2F1E654` 正好落在那之上 —— 它屬於 **seg1,根本不在這個檔案裡**,
而從未截斷的緩衝讀它會安靜地回垃圾。

**2026-09-14 已修** `tools/unpack.py`,加上截斷與提示。已經產生過的
`out/MAIN_c0000000.bin` 要重跑一次才乾淨。

---

## 2. 對照實測

FP3K 的指令級追蹤(`tools/trace_reduction_method.py`,在 Unicorn 裡跑真的選擇
分支並驗證韌體 SHA)列的「Recording enables A0/A7/A1」**正是上面那三個啟用位元組**:

| 情境 | A0/A7/A1 | RAW 比率 | 錄影路由 |
|---|---|---|---|
| 原廠 UHD24 / profile 429 | 0/0/1 | 1600/1600 | `CrctRwzmToBufA` |
| FP3K 3K24 / profile 429 | 0/0/1 | 2048/2048 | `CrctRwzmToBufA` |
| 原廠 UHD24 DC Crop / profile 432 | 1/0/0 | 1023 → 夾到 1024 | `CrctCrmfToBufA` |

完全吻合:前兩者 a0/a7 關、bufa1 開 → Rwzm;第三者 a0 開且選擇器 = 1 → Crmf、bufa1 關。

---

## 3. 比率欄位:1024 基底,以及那個看起來矛盾的 0x3FF

```
PARAM +0x60 / +0xD0     預覽 H / V
PARAM +0x64 / +0xD4     RAW(錄影)H / V
```

**值 ÷ 1024 = 縮減倍率。**

| 值 | 十進位 | 意義 |
|---|---|---|
| `0x3FF` | 1023 | p43 描述子裡的原廠值,**硬體夾到 1024**,效果 = unity |
| `0x400` | 1024 | unity |
| `0x640` | 1600 | 1.5625× |
| `0x800` | 2048 | 2× |

這解掉舊筆記的矛盾:`OPEN_GATE_EXPLORATION_ARCHIVE.md` 寫 unity 是 `0x400`、
`OG3K_IS_THE_STILLS_PATH.md` 與 `OG3K_WHAT_WAS_WRONG.md` 寫 `0x3FF` —— **兩個都對**,
一個是硬體看到的有效值,一個是描述子裡實際躺著的位元組。以前沒有一份筆記說明。

硬體端(`0xC0633E60` 寫入):

```
0x300F0900 = 1              比率區塊啟用
0x300F0908 / 0x300F090C     低半 = 比率;2048 → 0x00000800
                            1600 → 0x00E00640(上半是相位項)
0x300F2900 = 0              次級比率區塊
0x300F0004 bit8             來自感測器 reduction record +0x2D
                            ⚠ 語意未確定 —— 不要叫它「內插啟用」
```

---

## 4. 三個坑

**坑一:拿 zoom 暫存器判斷錄影路徑。** DC Crop 走 `CrctCrmfToBufA` 錄影,
**但仍為了預覽程式化比率硬體**。非零的 zoom 暫存器只證明預覽在縮。

**坑二:以為四個比率格子是全域一組。** 是**每個 profile 各有四格**。OG3K 早期只補了
29.97 的,另外七個格率從沒被補過,測試都用 29.97 所以沒暴露。
見 `projects/open-gate/notes/OG3K_RWZM_AND_BUILD_PIPELINE.md`。

**坑三:只改 RAW 那一對。** 曾經為了省頻寬只讓 `+0x64/+0xD4` unity、留著預覽的
`+0x60/+0xD0` —— **錄影花屏,相機隨後凍結。四格不能拆。**
見 `OG3K_WHAT_WAS_WRONG.md` §6c。

---

---

## 5. 兩條管線,以及 hbin/vbin 到底是什麼(2026-09-14 追加)

本節把原 §5 列為未解的三項解掉兩項半。全部從反編譯讀出。

### 5.1 硬體是兩條對稱的管線

```
main   hbin/vbin   FUN_c0633b30
       rwzm        FUN_c0633e60    0x300F0900 / 0908 / 090C
sub    hbin/vbin   FUN_c0633da0    0x300F2800 / 2810 / 2814 / 2840 / 2850
       rwzm        FUN_c0633f20    0x300F2900 / 2908 / 290C
```

除錯輸出裡的 `main hvbin_bypass` / `sub hvbin_bypass` 就是這兩條。
`0x300F2900` 是「次級比率區塊」—— 它不是備援,是 sub 管線自己的 zoom。

### 5.2 ★ hbin / vbin 的值是抽頭數,不是倍率

決策在 `FUN_c032d9a0`(由 `FUN_c0320af0` 轉呼叫)。它讀
`*(param_1 + 0x114) + index * 0x38` —— `0x38 = 56`,就是 `0xC0B5F770` 那兩筆
reduction record,index 由呼叫端給。

```c
if (*param_4 == 5)       code = 2;      /* main hbin */
else if (*param_4 == 3)  code = 1;
else                     code = 0;

if (param_4[1] == 3)     vcode = 2;     /* main vbin */
else                     vcode = 0;
```

**合法值是 1 / 3 / 5 —— 奇數,對稱 FIR 的抽頭數。** `1` 等於關閉。
`param_5` 是 sub 管線的同一對,邏輯相同。

### 5.3 係數就在那兩筆 record 裡

`+0x08` 起的九個 u16(小端)被讀進 `local_50`..`local_40`,最後進驅動結構。
**把它們叫「係數」是推論** —— 依據是數值本身:三個一組、每組和恰好 4096。

```
record0   1024, 2048, 1024   =  [1 2 1] / 4      真正的平均
record1    256, 3584,  256   =  [1 14 1] / 16    中心權重 87.5%,接近直通
```

`+0x1C` 起是同一組係數的 u8 版本(歸一到 64:`16,32,16` 與 `4,56,4`),
給另一個消費端。

**選擇器用 record1 給 3K 與全寬 UHD、record0 給 DC Crop**(見 §2 的來源)。
也就是說現行 3K 走的是**幾乎不平均**的那一顆核 —— 這和 FP3K 雜訊分析看到的
「3K 同相位鄰域相關性 0.01–0.03 對 UHD 的 0.09」一致,而且把他們當時無法區分的
「平均 vs 挑選」定在挑選那一邊。

**兩筆 record 裡都只有三抽頭係數。`hbin = 5` 要用的五抽頭係數不在這裡,還沒找到。**

### 5.4 hbin 代碼**不是** mux 檔位 —— 一個要撤回的推論

初稿在這裡寫「hbin 代碼 1/2 對應 mux 的 Hbin(3)/Hbin2(4),所以 Hbin = 三抽頭、
Hbin2 = 五抽頭」。**撤回。**

§1b 已經把兩者分開了:mux 檔位是 `0x300F06B0`/`0x300F06D0` 的 3-bit 欄位,
binning 級是另一塊硬體(`0x30100980` 有自己的 bypass)。§5.2 算出來的代碼 0/1/2
是餵給 **binning 驅動**(`FUN_c0633b30` / `FUN_c0633da0`)的,進的是驅動結構的
`+0x1A`,不是 mux。

兩組編號平行純屬巧合。要證實 Hbin 與 Hbin2 的差別,得找出 mux 檔位在什麼條件下
被寫成 3 或 4 —— 那正是 §1b 指的方向。

### 5.5 ★ 比率的夾制比原本寫的更寬

```c
local_5c = 0x400;
if (*param_2 < 0x401) puVar3 = &local_5c;
```

不只 `0x3FF` 被夾 —— **任何 ≤ 1024 的值都當成 unity**。§3 說「1023 夾到 1024」
方向正確,但規則是 `≤ 1024 → unity`。

### 5.6 ★ hbin 與 rwzm 不能自由並用

```c
if (((rwzm 有作用) && hbin_code != 0) && (FUN_c0633d70() == 0)) {
    local_30 = local_3e;
    local_3e = 0;              /* hbin 被關掉 */
}
```

`FUN_c0633d70()` 讀 `_DAT_300f0870 == 1`。**當 RWZM 在作用而那個旗標不是 1 時,
hbin 會被清掉。** 硬體裡有仲裁,不是兩段可以任意疊加。

這修正本文 §0 的「兩邊可以同時作用」—— 結構上兩組欄位確實獨立,
但**執行期有條件**,而且三個實測案例(§2)沒有一個是兩邊同時開的。

### 5.7 感測器側的合併是另一回事

上面全部是 CRCT(感測器之後)。**感測器自己的合併在模式 metadata 表**:

```
0xC0B59DC0,0x64 bytes 一筆,70 筆
  +0x00 模式 id   +0x04/+0x08 幾何   +0x2C/+0x30 輸出裁切
  +0x34/+0x38 裁切原點   +0x3C 位深   +0x40 格率類別
  +0x44 / +0x48 / +0x4C / +0x50   ★ 四個合併倍率(rec/lv × h/v)
```

原廠只用四種組合:

```
(1,1,1,1)  ×23   6064×4042 / 6064×3412 / 5712×3216 / 4176×2174 / 3968×2640 / 6064×2022
(2,2,2,2)  ×36   3032×2012 / 3032×1708 / 2088×1174 / 1984×1320
(3,2,3,3)  × 8   2016×1344 / 2016×1136
(3,3,3,6)  × 3   2016×672
```

**這裡的值是倍率(1/2/3/6),和 §5.2 的抽頭數(1/3/5)是不同的東西,不要混。**

`2016×1344` 正好是 3:2,六個模式涵蓋 60/70/80/90/100/120 fps,捲簾 6.16 ms
(現行 OG3K 的 3032×2012 是 12.44 ms)。

## 7. 還沒定案的

- `hbin = 5` 的五抽頭係數在哪
- 把 hbin 代碼映到輸出選擇器(Hbin / Hbin2)的那行程式
- `0x300F0870` 是什麼、誰設的 —— 它決定 hbin 能不能和 rwzm 並用
- `0x300F0004` bit8 的語意(來自 record `+0x2D`)

## 8. 出處

本文的結構、enum 與位址是 2026-09-14 直接從 `out/MAIN_c0000000.bin` 反組譯讀出的
(`0xC031DCE0..0xC031E060`)。比率與硬體暫存器數字出自
`research/other/external/FP3K-technical-handoff-2026-09-10/analysis/reduction-method/FINDINGS.md`
—— Vitaly Li 的 reduction 調查,這棵樹裡關於本主題最嚴謹的一份。

`research/rtos/notes/SUBSYSTEMS.md` §4.1 的子操作清單是同一批字串,但只是清單,
沒有結構。
