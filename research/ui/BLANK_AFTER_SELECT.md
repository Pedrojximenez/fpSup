# 選完之後一片空白 —— 不用 hook 的解法

2026-09-29。工具 [`tools/enum_converters.py`](tools/enum_converters.py)。

## 原因

選單存的是 **enum**,畫面畫的是 **display state**。中間隔著一支很小的 ARM 葉函式,
全機有 **326 支**,一個控制項一支,形狀都一樣:

```
movw r2, #<low>      ┐ 配對表的位址,兩個立即值
movt r2, #<high>     ┘
str  r2, [ip]          交給呼叫端
mov  r2, #<count>      幾組配對
bx   lr
```

配對表是 `{enum, state}`,**每次求值都會重讀**(`FUN_c06ccd10`)——
所以改表立刻生效,不用重開機(`README.md` §4 實機驗過)。

解析度那一支在 `0xC06BDA3C`,表 `0xC2E4020C`,三組:

```
3 -> 0     2 -> 1     4 -> 2
```

**你加的新列,它的 enum 在表裡沒有對應**,所以控制項拿不到 state ——
畫出來就是空白。**這不是 CSV 的問題,CSV 那半已經成功了。**

## 解法:改三個立即值,不是 hook

1. 在任何地方擺一張自己的配對表(`{enum, state}`,little-endian,每組 8 bytes);
2. 把那支轉換器的 **`movw` / `movt`** 改成指向它;
3. 把 **`mov r2,#N`** 改成新的組數。

**沒有分支、沒有 trampoline、沒有被搬走的指令** —— 只是三個常數。

```
$ python3 research/ui/tools/enum_converters.py at 0xC06BDA3C
0xC06BDA3C  table 0xC2E4020C  3 pairs   patch 0xC06BDA3C/0xC06BDA40/0xC06BDA48
        3->0, 2->1, 4->2
```

### 這條路是實機驗證過的

fpSup-Formats 就是這樣做的:它把解析度那支指到自己的六組表 `0xC0731C40`。
**我們的工具從格式算出來的三個字,與那張卡實際寫的逐位元組相同:**

```
0xC06BDA3C = 40 2c 01 e3      movw r2,#0x1C40
0xC06BDA40 = 73 20 4c e3      movt r2,#0xC073     → 表 0xC0731C40
0xC06BDA48 = 06 20 a0 e3      mov  r2,#6          → 六組
```

## 怎麼找到「你那個控制項」的那一支

326 支都在 `0xC06BD000`..`0xC06D0000`,可以按組數篩:

```
python3 research/ui/tools/enum_converters.py list --count 3
```

篩出來還是會有好幾支,再用**配對內容**認:每支的 `{enum, state}` 會長得像那個控制項
(例如位元深度三態會是 `0->0, 1->1, 2->2`,解析度是 `3->0, 2->1, 4->2` 這種不連續的)。

⚠ **注意 `mov r2,#N` 是 8-bit 立即值**,所以組數上限 63(工具會擋)。

## 還沒解的

- **哪一支對應哪一個控制項,目前只能用組數 + 配對內容猜。** 精確的對應要走
  widget 的 vtable `+0x5C`(`FUN_c06bd988` 就是從那裡取的),還沒追。
- 原廠留的那個 `4 -> 2`(解析度的第三態)是 SIGMA 自己定義的、沒接完的狀態
  —— 見 `projects/open-gate/notes/UI_STATE2_HAS_NO_ICON.md` §0。
- **新的 state 還要有美術**:圖示家族 `qs_resolution` / `set_resolution` /
  `font_menu_MB_resolution` 原廠各只有兩個成員,第三態沒有圖。見下一節。
