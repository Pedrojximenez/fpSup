# CRCT 路徑選擇器解開了:Hbin2 是唯一活著的 binning 抽頭

2026-09-21。承 `CRCT_REDUCTION_PATHS.md` 與 `REDUCTION_INVENTORY.md`。
本文**推翻那兩份的三項結論**,並解掉它們列為未定案的四項中的三項。

全部從 `out/seg0_c0000000.bin` + `out/seg1_c2ef6e00.bin` 反組譯讀出,
關鍵處逐指令驗證,並與 Vitaly Li 的 Unicorn native trace 三個實測案例交叉比對。

---

## 0. 三句話

1. **決策函式不是執行期組出來的。** ops 表是 ROM 常數 `0xC0B5FCC0`,
   `+0x9C` = **`FUN_c0325228`**,八個分支全部靜態可讀。
2. **RWZM 作用時 hbin 不是被關掉,是被搬到第二級水平 binning**
   (`0x300F08C0` + 核 `0x300F08C4`)。
3. **`CrctHbin2ToBufA`(4)是唯一真的被開啟過的 binning 抽頭。**
   `CrctHbinToBufA`(3)只寫在一個**停用**的視窗上;
   `Gain`(0)/`Vbin`(2)/`Spc`(5)**兩個實作都從來不寫**。

---

## 1. 先修工具:seg1 一直都在

`CRCT_REDUCTION_PATHS.md` §1c 寫「感測器描述子 `0xC2F1E654` 屬於 seg1,
**根本不在這個檔案裡**」。那句話只對 `out/MAIN_c0000000.bin` 成立。

```
out/seg0_c0000000.bin   49,245,696   0xC0000000..0xC2EF6E00
out/seg1_c2ef6e00.bin      236,032   0xC2EF6E00..0xC2F30800   ← 一直在 out/ 裡
```

`0xC2F1E654` 落在 seg1 偏移 `0x27854`。自我檢查:`desc+0x114` 讀出
`0xC0B5F770`,正是筆記說的 reduction record 位址。**兩個檔案一起 map 就能讀。**

⚠ `out/MAIN_c0000000.bin`(49,482,954 bytes)仍是未截斷的舊檔,
`tools/unpack.py` 已修但沒重跑。**不要用它;用 seg0 + seg1。**

---

## 2. ops 表是 ROM 常數,不是執行期的

`CRCT_REDUCTION_PATHS.md` §1b 的結論是「表在執行期組出來,靜態解不到具體實作,
要定案只能上機讀 `[obj+0xD0]+0x9C`」。**不必上機。**

```
FUN_c03255b0(0xC343B588, &DAT_c2f1e654)     imager0 的 ctor
    *(obj + 0xD0) = &DAT_c0b5fcc0            ← ROM 常數位址
0xC0B5FCC0 + 0x9C = 0xC0325228               ← CRCT 路徑選擇器
```

`0xC0325228` 正是 FP3K handoff 裡 `trace_reduction_method.py` 點名的
"native path selector C0325228" —— 兩邊獨立得到同一個位址。

### ★ 有第二個 imager,別只看一個

```
imager0   FUN_c0322e48(0) → 0xC343B588   ops 0xC0B5FCC0   +0x9C = 0xC0325228   records 0xC0B5F770
imager1   FUN_c0322e48(1) → 0xC343B6AC   ops 0xC0B72AB0   +0x9C = 0xC0329198   records 0xC0B72664
```

`FUN_c031d988`(錄影路徑)走 `FUN_c0322e48(0)`,所以是 imager0。
**imager1 有自己的一套選擇器與 reduction record,本文沒有追它的呼叫者。**

---

## 3. 選擇器的八個分支(`FUN_c0325228`,完整)

輸入 `r4` = 幾何結構(`FUN_c031d988` 的 `local_58`,0x38 bytes),
輸出 `ip` = 路徑結構(`local_a4`,0x4C bytes)。

```
輸入  +0x00/+0x04  錄影尺寸(兩者皆 0 = 沒在錄)
      +0x08/+0x0C  錄影 RWZM H/V      ← PARAM +0x64/+0xD4,先夾 max(v,1024)
      +0x10/+0x14  錄影 hbin/vbin 抽頭數   ← 經 FUN_c022ee10/ee90 轉成 1/3/5
      +0x18        kind
      +0x24/+0x28  預覽 RWZM H/V      ← PARAM +0x60/+0xD0
      +0x2C/+0x30  預覽 hbin/vbin 抽頭數

輸出  +0x00/01/02  a0 / a7 / a1 啟用
      +0x04/+0x08  a0 / a7 六選一 mux   → FUN_c0635ca8 / c0635cd0
      +0x20        → FUN_c0633d30 → 0x300F0870   ★ 韌體自己叫它 main hvbin_bypass
      +0x21        → FUN_c0633d90(空殼,return 1)
      +0x24/+0x28  主管線 hbin/vbin      +0x2C/+0x30 副管線
      +0x34/+0x38  主管線 RWZM           +0x3C/+0x40 副管線
      +0x44        → 0x30100980 bit4(真正的 hvbin bypass 硬體位元)
      +0x48        ★ reduction record 索引(0 或 1)
```

夾制常數 `DAT_c0b57144 = 1024`,`unity` 以下一律當 unity。

| 分支 | 條件 | a0/a7/a1 | a0 mux | a7 mux | 0x300F0870 | 主管線吃 | record |
|---|---|---|---|---|---|---|---|
| A | 沒在錄影 | 0/0/0 | 1 | 1 | 0 | 預覽 | 0 |
| B | 錄=預覽,且 unity | kind==4 ? 0/1/0 : 1/0/0 | 1 | 1 | 0 | 預覽 | 0 |
| **C** | 錄=預覽,非 unity | **0/1/0** | 1 | **4 Hbin2** | 0 | 錄影 | 0 |
| D | 錄≠預覽,錄是 unity | kind==4 ? 0/1/0 : 1/0/0 | 1 | 1 | 0 | 預覽 | 0 |
| **E** | 錄≠預覽,預覽是 unity | **0/0/1** | 1 | 3 Hbin | **1** | RWZM=錄影,bin=**預覽** | **1** |
| **F** | 兩邊都縮且不同 | **0/1/0** | 4 | **4 Hbin2** | 0 | 錄影;副管線=預覽 | 0 |

分支 B 與 D 各自因 `kind==4` 再分岔,所以 `str [ip,#4]` / `str [ip,#8]` 共 8 對
—— 我逐一列舉過所有寫入點,沒有遺漏。

### 對照三個實測案例(FP3K Unicorn native trace,有驗韌體 SHA)

| 案例 | trace 量到 | 本文模型 | record |
|---|---|---|---|
| 原廠 UHD24 p429,ratio 1600 | 0/0/1 `CrctRwzmToBufA` | **分支 E** ✔ | 1 ✔ |
| FP3K 3K24 p429,ratio 2048 | 0/0/1 `CrctRwzmToBufA` | **分支 E** ✔ | 1 ✔ |
| 原廠 UHD24 DC Crop p432,1023→1024 | 1/0/0 `CrctCrmfToBufA` | **分支 B** ✔ | 0 ✔ |

三個案例的啟用位元、路由**與 record 索引**全中。
FP3K FINDINGS 說「selector 選 record1 給 3K 與全寬 UHD、record0 給 DC Crop」
—— 那就是輸出 `+0x48`,分支 E 寫 1、其餘寫 0。

---

## 4. ★ Hbin 與 Hbin2 的差別(舊筆記列為未定案)

### 4a. 硬體有兩級水平 binning,只有一級垂直

主管線 `FUN_c0633b30` 寫的暫存器,按功能分:

```
垂直      0x300F0800  控制      0x300F0810/0814/0818/0820  9 個 u16 係數(/4096)
水平一    0x300F0840  控制      0x300F0850/0854/0858/085C  4×3 個 u8 係數(/64)
水平二    0x300F08C0  控制      0x300F08C4                 1×3 個 u8 係數  ★
```

副管線 `FUN_c0633da0` 是精簡版:`0x300F2800`(垂直)+ `0x300F2810/2814`、
`0x300F2840`(水平)+ `0x300F2850`,**沒有第二級水平**。

mux 列舉有 `Vbin` 一個、`Hbin` / `Hbin2` 兩個 —— **和硬體的一垂直、兩水平完全對上。**

### 4b. hbin 是「搬走」,不是「清掉」

`FUN_c032d9a0` 的仲裁,逐指令:

```
c032dda4  ldrb ip, [sp, #0x22]    ; 驅動結構 +0x1A = 水平代碼
c032dda8  strb ip, [sp, #0x30]    ; → 驅動結構 +0x28
c032ddac  mov  ip, #0
c032ddb0  strb ip, [sp, #0x22]    ; 第一級關掉
```

(驅動結構在 `sp+8`,memset 0x2C bytes;`+0x1A`=`sp+0x22`、`+0x28`=`sp+0x30`。)

而 `FUN_c0633b30` 把 `+0x28` 寫進 **`0x300F08C0`**,
`+0x29..0x2B` 寫進 `0x300F08C4`。**水平 binning 被移到第二級繼續做。**

同樣的三指令序列出現兩次,第二個觸發條件不同:

```
c032ddd8  ; 當 [FUN_c0322020()+0xFC] != 0 且 hbin 開著而 vbin 關著
```

也就是**只做水平不做垂直時,也走第二級**。

`CRCT_REDUCTION_PATHS.md` §5.6 的「hbin 會被清掉」與
`REDUCTION_INVENTORY.md` §4 的「hbin 必定被關掉」**兩處都要改成「被搬到第二級」**。

### 4c. ★ 只有 Hbin2 真的被開啟過

把兩個實作裡每一個寫進 mux 欄位的指令全部列舉(imager0 有 16 個、imager1 有 10 個):

```
imager0  a0 mux ∈ {1 Crmf, 4 Hbin2}     a7 mux ∈ {1 Crmf, 3 Hbin, 4 Hbin2}
imager1  a0 mux ∈ {1 Crmf, 4 Hbin2}     a7 mux ∈ {1 Crmf, 4 Hbin2}
```

**`Gain`(0)、`Vbin`(2)、`Spc`(5) 兩個實作都從來不寫。**
呼叫前的預設值是 1(Crmf),而選擇器每條分支都會覆寫 `+0x04` 與 `+0x08`,
所以那三個檔位在 Ver.5.02 **完全無法達到**。

再把「視窗有沒有啟用」疊上去:

| 分支 | 真正活著的組合 |
|---|---|
| B / D | a0 或 a7 啟用,mux = **1 Crmf** |
| C / F | a7 啟用,mux = **4 Hbin2** |
| E | a1 啟用 → **RWZM**;a7 mux 寫 3 Hbin **但 a7 沒啟用** |

**`CrctHbinToBufA` 在整個韌體裡只出現在一個停用的視窗上。**
它不是「另一種 binning」,它是**沒有被接出去的那一級**。

---

## 5. ★ hbin 與 RWZM 並不互斥

`REDUCTION_INVENTORY.md` §4 寫:

> `FUN_c0633d70()` 讀 `0x300F0870 == 1`,寫它的只有 `FUN_c0633d30`,
> 而**全韌體三個呼叫點傳的都是 `0`**。
> 所以在原廠韌體裡,RWZM 一開,hbin 必定被關掉。

**這是錯的。** `FUN_c031d988` 的呼叫點傳的是 `local_84`,也就是選擇器輸出 `+0x20`
—— 一個**每條分支各自決定**的值。而**分支 E 寫的是 1**:

```
c03254e4  mov  r3, #1
c03254e8  strb r3, [ip, #0x20]
```

分支 E 就是原廠 UHD / FP3K 3K 的錄影分支(FP3K trace 三取二)。
所以錄影時 `FUN_c0633d70()` 回 true,§4b 的仲裁**不會觸發**,
hbin 留在第一級,**和 RWZM 同時作用**。

連帶要撤回 `CRCT_REDUCTION_PATHS.md` §5.6 的
「三個實測案例沒有一個兩邊同時開」—— 分支 E 的主管線同時吃
**錄影的 RWZM 比率**與**預覽的 hbin/vbin 抽頭數**(見 §3 表最後兩欄)。

### 順帶:`0x300F0870` 是什麼,韌體自己說了

除錯輸出印 `main hvbin_bypass_on/off` 用的是 `local_84`,
`FUN_c0633d30(local_84)` 用的也是 `local_84` —— **同一個欄位**。

所以 `0x300F0870` 的名字就是 **main hvbin_bypass**。
⚠ 但**真正的 bypass 硬體位元是另一個**:輸出 `+0x44` → `FUN_c0635d00(1, +0x44, 0)`
→ `0x30100980 = 1 | bypass<<4`,只有分支 F 會設。
**除錯字串印的不是那個位元。** 兩者同名不同物,這是 `CRCT_REDUCTION_PATHS.md` §1b
把「mux 檔位」和「binning bypass」分開講時沒看到的第三樣東西。

---

## 6. reduction record 的完整欄位表

`0xC0B5F770`,兩筆 `0x38` bytes。`FUN_c032d9a0` 幾乎原封不動複製成驅動結構,
只換掉三個欄位。

| record | 驅動結構 | → 暫存器 | 內容 | record0 | record1 |
|---|---|---|---|---|---|
| — | +0x00 | 0x300F0800 bits[3:0] | **垂直代碼**(算出來的) | 0 或 2 | 同 |
| +0x06 | +0x01 | 0x300F0800 bit16 等 | 垂直變體 | 3 | 2 |
| +0x07 | +0x04 | 0x300F0800 bit29 | | 0 | 0 |
| +0x08..+0x19 | +0x08..+0x19 | 0x300F0810/14/18/1C/20 | **垂直係數** 9×u16 /4096 | `1024,2048,1024` ×3 | `256,3584,256` ×3 |
| — | +0x1A | 0x300F0840 bits[7:0] | **水平代碼**(算出來的) | 0/1/2 | 同 |
| +0x1B | +0x1B | 0x300F0840 bit16 | | 1 | 0 |
| +0x1C..+0x27 | 同 | 0x300F0850/54/58/5C | **水平一係數** 4×3×u8 /64 | `16,32,16` ×4 | `4,56,4` ×4 |
| +0x28 = 0 | **+0x28** | **0x300F08C0** | **被搬過來的水平代碼** | (被覆寫) | (被覆寫) |
| +0x29..+0x2B | 同 | 0x300F08C4 | **水平二係數** 1×3×u8 | `16,32,16` | `4,56,4` |
| +0x2C | — | | | 1 | 1 |
| +0x2D | → rwzm 驅動 | 0x300F0004 bit8 | | **1** | **1** |
| +0x2E..+0x35 | — | | 四個 u16 | `6016,4014,3856,2174` | 同 |

三件事:

- **核就是 `[1 2 1]/4` 與 `[1 14 1]/16`,兩個方向都一樣**,舊筆記只講了水平那組 u8 版。
- **`0x300F0004` bit8 = `record[0x2D] & 1`,兩筆 record 都是 1 → 恆為 1。**
  它不是逐模式的開關,`REDUCTION_INVENTORY.md` §7 可以把這條劃掉
  （語意仍不明,但它不會變,所以不能用來區分任何東西）。
- **`hbin = 5`(÷5)要用的五抽頭係數,record 裡沒有。** 兩筆都只有三抽頭。
  要嘛在矽片裡,要嘛在別處 —— 仍未找到。

---

## 7. RWZM 驅動(`FUN_c0633e60`)逐行

```c
0x300F0004 = (0x300F0004 & ~0x100) | (record[0x2D] & 1) << 8;   // 無條件,恆 1
if (enable) {
    r = ratio & 0x3FF;  if (r < 0x201) r = abs(0x400 - r);
    phase = 0x200 - (r >> 1);
    0x300F0900 = 1;
    0x300F0908 = ratio_h | phase_h << 16;     // ratio 是完整 u16,不遮罩
    0x300F090C = ratio_v | phase_v << 16;
} else 0x300F0900 = 0;
```

對上 FP3K 實測的暫存器值:`1600 → 0x00E00640`、`2048 → 0x00000800`。✔

---

## 8. PARAM profile 表(2026-09-21 稍晚補上,解開了)

初稿這一節寫「表的排列我沒解出來,預覽欄與錄影欄逐筆相同,和實測矛盾」。
**原因找到了,是我自己讀錯:column 在記憶體裡不是按 struct offset 順序排的。**

權威定義在 `research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json`
(`columns[].offset → table`,306 rows,`元素 = table + row*4`),`og3k_plan.py` 的
`profile_col()` 就是讀它。四個 column 的實際位址:

```
+0x58 預覽 hbin  0xC0BD8EBC      +0x5C 錄影 hbin  0xC0BE1E2C
+0xC4 預覽 vbin  0xC0BD9384      +0xC8 錄影 vbin  0xC0BE22F4
+0x60 預覽 zoomH 0xC0BD984C      +0x64 錄影 zoomH 0xC0BE149C
+0xD0 預覽 zoomV 0xC0BD9D14      +0xD4 錄影 zoomV 0xC0BE1964
```

**位址順序與 offset 順序不一致**(`+0x60` 的下一個 column 是 `+0xD0` 不是 `+0x64`)。
把相鄰 column 當成相鄰 offset,就會把「預覽 H vs 錄影 H」誤讀成「H vs V」。
anchor 檢查:四個 column 在 row 122 算出
`0xC0BD9A34 / 0xC0BE1684 / 0xC0BD9EFC / 0xC0BE1B4C`,**與 OG3K 筆記的四個位址逐一相同**。

### 8a. 原廠分支分布(306 個 profile 全部算過)

| 分支 | 筆數 | 真正活著的路由 |
|---|---|---|
| B | 172 | `CrctCrmfToBufA` |
| **C** | **36** | **`CrctHbin2ToBufA`(a7 啟用)** |
| D | 81 | `CrctCrmfToBufA` |
| **E** | **17** | **`CrctRwzmToBufA`(a1 啟用)** |
| F | **0** | 雙管線 —— **原廠一筆都不走** |

- 交叉驗證:profile **429 落在分支 E**、**432 落在 B/D** —— 與 FP3K native trace
  量到的 `0/0/1 Rwzm` 與 `1/0/0 Crmf` 一致。這是第四重獨立確認。
- **`CrctHbin2ToBufA` 真的活著,36 筆。** §4c 的結論成立且有量。
- **分支 F 是死路**(雙管線同時服務兩種縮放),程式在、從沒被走到。

### 8b. ★ hbin 與 RWZM 確實同時作用,而且就是那 17 筆

分支 E 的 17 個 row 與「預覽 hbin = 1」的 17 個 row **逐一相同**:

```
row 78,79,86,98,99,106,118,119,126,230,231,237,239,274,280,286,300
profile 131,132,139,151,152,159,171,172,179,365,366,372,374,417,423,429,443
幾何 3856x2170 / 3840x2160 / 4096x2160   錄影 zoom 1600(365 是 1500)  預覽 zoom 1023
```

分支 E 的主管線吃**錄影的 RWZM 比率**與**預覽的 hbin/vbin 抽頭數**(§3),
而它同時把 `0x300F0870` 設成 1(§5),仲裁不觸發。

**所以那 17 個 UHD 錄影 profile,主管線是 RWZM 1.5625× 與 hbin÷3 / vbin÷3 疊在一起跑的。**
`REDUCTION_INVENTORY.md` §2 的統計(錄影 hbin 全 0、17 筆預覽 hbin=1)**是對的**,
初稿叫人不要引用是我的誤判,撤回。

### 8c. RWZM 能不能非等比 / 放大

- **程式碼不限制非等比**:H 與 V 是兩個獨立暫存器(`0x300F0908` / `0x300F090C`),
  在 `FUN_c032d9a0` 裡**各自獨立夾制**,enable 條件是 OR
  (`任一軸 != 1024 就開`,`c032dc6c..dc84`)。單軸縮放是韌體預期內的狀態。
- **但原廠沒有先例**:306 筆的預覽組與錄影組**各自 H==V,逐筆等比**。
- **不能放大**:只有下限夾制 `if (1024 >= ratio) ratio = 1024`(`c032dc24` / `c032dc44`,
  `bhs`),**沒有上限檢查**。ratio 是除數語意,放大需要 < 1024,會被夾掉。

## 9. 還沒定案的

- `hbin = 5` 的五抽頭係數(兩筆 record 都只有三抽頭)。
- 輸入 `+0x18` 的 `kind`,以及 `kind == 4` 為什麼改用 a7 視窗。
- `[FUN_c0322020()+0xFC]` 那個旗標是誰設的(§4b 第二條搬移路徑的閘)。
- imager1(`FUN_c0329198`)在什麼情況下被選到。
- `Crmf` 與 `Spc` 各是什麼修正(`Spc` 永遠不被選,優先度最低)。
- RWZM ratio 的硬體上限(韌體沒有上限檢查;原廠最大 3072 = 3×,在預覽側)。

## 10. 出處與重現

```python
# seg0 + seg1 一起 map,否則 0xC2EF6E00 以上讀不到
SEGS = [(0xC0000000, 'out/seg0_c0000000.bin'), (0xC2EF6E00, 'out/seg1_c2ef6e00.bin')]
```

逐指令看過的:`0xC0325228..0xC03255AC`(選擇器八分支)、
`0xC032DD50..0xC032DDF0`(仲裁)、`0xC0635CA8/CD0`(mux 寫入)、
`0xC0635D00`(bypass 暫存器)、`0xC0635DB0/DC8/DE0/DF8`(四個驅動 shim)、
`0xC022EE10/EE90`(抽頭數轉換)。
反編譯對照:`out/decomp/full/blk_c03.c`、`blk_c04.c`、`blk_c06.c`。
交叉比對:`research/other/external/FP3K-technical-handoff-2026-09-10/analysis/reduction-method/FINDINGS.md`。
