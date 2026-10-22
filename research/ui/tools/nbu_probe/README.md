# NBU 記錄解譯器的離線模擬

兩個檔案,分工明確:

- **`nbu_format.py`** —— 純 Python 的格式編解碼,**不 import unicorn**。這是「真正改 UI」要用的那一半。
- **`nbu_probe.py`** —— 跑相機**自己的** `FUN_c05e6400`(Thumb),對著釘住的 `out/seg0_c0000000.bin`。
  它的用途是**證明上面那個解碼是對的**。

```
python3 nbu_format.py sweep             # 純 Python 拆開整個 UI(0.4 秒)
python3 nbu_format.py records MainB2 --tag 0x1000B
python3 nbu_probe.py index              # 解析容器,列出 221 個資源集
python3 nbu_probe.py map MainB2         # 用韌體自己的解譯器走完一整頁
python3 nbu_probe.py index Main         # 只看名字含 Main 的
python3 nbu_probe.py index --json ../../nbu_sets.json
python3 nbu_probe.py set MainB2         # 解析一個資源集並逐筆追蹤
python3 -B -m unittest                  # 37 項測試;格式與 harness 共十二次變異檢查都會失敗
```

`uinav.py sets` / `uinav.py at <addr>` 吃的就是這裡產生的 `research/ui/nbu_sets.json`。

---

## 用真的原廠指令跑的部分

| 位址 | 是什麼 |
|---|---|
| `0xC05E6400`..`0xC05E7B28` | 記錄解譯器本體(5.4 KB Thumb) |
| `0xC05E5F20` / `0xC05E5FE0` | context 建構子 —— **context 是韌體自己建的,不是我們拼的** |
| `0xC05E63E8` | 版本/前言讀取 |
| `0xC05E5D78` / `0xC05E5DB8` / `0xC05E5E38` / `0xC05E5EA8` | 建構子安裝在 `ctx+0x34..0x40` 的四個記憶體讀取方法:signed byte、**big-endian u32**、區塊複製、跳過 n |
| `0xC05E5E20` | 同一個字重新解讀成 float |
| `0xC05E5B58` | pool offset → 字串:用 `ctx+0x10` 的池大小做邊界檢查,加上 `ctx+0x14` 的池基底 |
| `0xC0013E2C` | strcmp |

其他一律是 Python 替身,而且**沒登記的呼叫會炸,並且把位址印出來**(`UnstubbedCall`)——
所以「這筆記錄需要哪些韌體服務」是個**答案**,不是一個安靜的 0。

`survey=True` 會把未知呼叫自動補成回傳 0 的替身並記錄下來,用來一次看完需求清單;
那些 0 **不是**原廠會回的值,只能當探路用。

### 唯一非得有的替身

`FUN_c05e8ef8(ctx, size)` 不是回傳原始記憶體:呼叫端馬上 `ldr r2,[r0]` / `ldr r1,[r0,#0x34]` / `blx r2`,
所以回來的是一個**在那塊記憶體裡做出來的配置器物件**(+0x00 配置函式、+0x34 tag)。
回傳乾淨的零記憶體會讓解譯器跳到位址 0。這個替身照樣式補上表頭;原廠 arena 的擺放與記帳沒有重現。

---

## 已經量出來的東西

### 1. token 就是 big-endian u32

讀取方法直接證實:cursor 在 `ctx+0x04`、基底在 `ctx+0x24`,每次 +4。
float 走同一個字。所以 `0xC1A709BC` 寫 `40 A0 00 00` 就是 5.0 —— 跟 fpSup-Formats 那張卡對得上。

### 2. 最上層容器只有兩筆記錄

`0xC18C0460` = `"NBU\0"` + 版本 `0x01090000`(1.9):

| 記錄 | tag | 大小 | 作用 |
|---|---|---|---|
| 0 | `0x1` | 176,160 B | 字串池。**執行後 `ctx+0x14` = `0xC18C0474`、大小 `0x2B018`** |
| 1 | `0x10001` | 7,088 B | **資源集索引:221 筆**,每筆 0x2C bytes `{FNV hash, 名字, 從 0xC18C0460 起的位移}`,按 hash 排序 |
| 2 | `0xFFFFFFFF` | 8 B | 結束,回傳 1 |

字串池基底原本是「拿三個名字比對出來的」;現在是**執行原廠程式碼得到的**。

**20 MB 的記錄區不是一個線性容器。** 每個螢幕是索引裡的一筆、各自一段記錄流 ——
這正好解釋了為什麼「某些 screen-specific set 是延遲解析的」,以及為什麼
「開機後解析度陣列不再重建」跟「parser 還在跑」兩件事可以同時成立。

### 3. 資源集怎麼開

不是嵌套的 NBU:**沒有 magic、第一個 token 在位移 0、版本是從上層繼承的(harness 直接寫進去,不是讀到的)**。
另外要給一個 owner 物件放在 `ctx+0x0C`,解譯器會把它做出來的 arena 寫回 `owner+0x0C`(`0xC05E68EA`);
給 0 就會寫穿空指標。

### 4. tag `0x10002` = 配置標頭,已完全解出

MainB2 的第一筆記錄,**3,028 bytes = 757 個 big-endian word,解譯器一個不漏地讀完**:

```
+0x00  tag      0x00010002
+0x04  size     0xBD4  (3028)
+0x08  objects  0xC1   (193)
+0x0C  0
+0x10  classes  0x17   (23)
       然後 23 組 {名字的 pool offset, 實例數}
```

MainB2 宣告的 23 個類別與數量:

```
animationClip 180   appStateEvent 3   appVariableChangeEvent 24
appVariableEvent 9  changePropertyByControl 50   controlAnimation 154
controlAppState 75  controlAppVariable 103   controlFocus 38
controlTimer 10     controlValue 20   controlValueEvent 45
drawImage 28        drawRect 64       drawText 27   fill 1
flexBoxItem 6       focusEvent 24     keyEvent 91   layoutFlexBox 1
objectBase 193      screenEvent 9     timerEvent 4
```

`objectBase` 的數量 = `objects` 欄位 = 193。**加一列就要動這張表**,
`allocation_header()` 是純 Python 解碼,測試用它跟韌體的解析結果互相對帳。

### 5. 三個獨立交叉驗證

手算出來的值 vs 執行出來的值,完全相同:

| 出處 | 手算 | 模擬 |
|---|---|---|
| `MAINB2_ROW_EXTENSION.md` | MainB2 hash `BDD26684`、pool offset `0x1A3B8`、位移 `0x76FF04` | 相同 |
| 同上 | MainB2 範圍 `C2030364..C2055DB0`、配置標頭 3028 bytes | 相同(MainB3 就從 `C2055DB0` 開始) |
| `NATIVE_ROW_DONOR.md` | MainY4 `[C214A0C0, C217CDEE)` | 相同(MainY5 從 `C217CDEE` 開始) |

---

---

## 記錄格式 —— 這才是「真正改 UI」的那把鑰匙

**每一筆記錄都是 `{BE u32 tag, BE u32 size, body…}`,`size` 含 tag 與 size 兩個字。**
MainB2 的 1391 筆全部相符,結尾是 `FFFFFFFF 00000008`。
記錄大小是**位元組粒度**(reader 可以讀單一位元組),所以 body 不知道 tag 就不能當 word 走。

因為記錄自帶長度,**拆開、換掉、插入、重新輸出一整個資源集完全不需要逐 tag 的文法**。
`nbu_format.split()` / `join()` 做的就是這件事,改 body 之後 `size` 自己算出來。

### 全樹驗證(0.41 秒,純 Python)

```
221 sets, 303597 records
220 of 220 sets end exactly where the next begins
```

**220 個資源集首尾相接、一個位元組不差** —— 這是格式正確性的 220 次獨立閉合檢查。
MainB2 另外做過逐筆對帳:Python 拆出來的 1392 筆邊界與韌體解譯器**完全相同**,
`join()` 回去**逐位元組相同**。

### tag 目錄(case N 是 `0xC05E6460` 那個 switch 的第 N 支,N = tag − 0x10001)

| tag | case | 是什麼 | 全 UI 數量 | MainB2 |
|---|---|---|---|---|
| `0x10001` | 0 | 資源集索引(只在最上層) | 1 | — |
| `0x10002` | 1 | 配置標頭 | 221 | 1 |
| `0x10003` | 2 | **物件** —— 數量 = 配置標頭的 `objectBase` | 36,379 | 193 |
| `0x10004` | 3 | value/binding(轉 `FUN_c05e8070`) | 37,513 | 199 |
| `0x10005` | 4 | 屬性 + 動畫鍵 | 26,326 | 120 |
| `0x10006` | 5 | 屬性(多一個值) | 47,314 | 209 |
| `0x10007` | 6 | 屬性(layout) | 211 | 1 |
| `0x10008` | 7 | 屬性 + 巢狀 key list | 164 | 0 |
| `0x10009` | 8 | 屬性(短) | 89,068 | 430 |
| `0x1000A` | 9 | 資源引用 | 46,528 | 159 |
| **`0x1000B`** | **10** | **影像陣列** —— README §5c 講的那個 case 10 | **11,383** | **52** |
| `0x1000C` | 0xb | value/binding | 0 | 0 |
| `0x1000E` | 0xd | value/binding | 6,863 | 20 |
| `0x110xx` | — | 整塊複製的表 | 1,406 | 7 |
| `0xFFFFFFFF` | — | 結束 | 221 | 1 |

`0x1000B` 是**實測**釘出來的:它是唯一一個 trace 裡會呼叫 `FUN_c05e2988`
(image_container_new)的 tag。要加一個 UI 狀態就是要動它 —— 以及每一個伴隨屬性。

### 所以「加一列」到底要動什麼

1. 目標 set 裡的 `0x1000B` 影像陣列(加一個元素);
2. 每一個伴隨屬性記錄(`0x10005`/`0x10006`/`0x10009`…)都要有對應的新狀態;
3. **`0x10002` 配置標頭**:它宣告了每個類別的實例數與 `objects`,加物件就要一起加;
4. `0xC1A709BC` 的 controller 最大值(三列 2.0、六列 5.0);
5. 然後整個 set 重新輸出 —— `join()` 會把 `size` 算好。

這條路不需要在解譯器裡攔截任何東西,改的是資料本身。
**還缺的是把改好的 set 交給韌體載入的路**(見下)。

## 還沒做到的(下一段)

繼續往 MainB2 的第二筆記錄走會停在 `0xC05E7770`:那條路要真的 app 物件
(vector、registry、class 表),六個函式在等 ——
`0xC05D9080`、`0xC05D9378`、`0xC05D9B00`、`0xC05D9E88`、`0xC05E04E8`、`0xC05E0CC8`。
其中 `0xC05E04E8` 是「用名字線性搜一個 vector」,`0xC05D9E88` 是「查到就回 `+0x2C`」。

`native_variable_probe` 已經示範過怎麼給一個合成 registry(15 項測試)。
把那套接上來,就能走到元素建構(`0xC05EDC40` / `0xC05E2CA8`),
也就是**離線驗證「六列選單的記錄副本會被怎麼解析」**。那是下一個里程碑,這裡還沒做。

### 兩個缺口,擋在「真正改 UI」前面

1. **body 的逐欄位文法。** 現在能拆能拼能改長度,但要**有意義地**改一筆
   `0x1000B` 或 `0x10006`,還要把 body 的欄位解出來。`0xC05E6460` 的 switch 已經讀過
   case 0/1/2/4/5/6/7,把它們寫成解碼器並用「解碼→重編碼逐位元組相同」當驗收,是直路。
2. **載入路徑。** 改好的 set 要讓韌體載進去。fpSup-Formats 的做法(改
   `0xC0D4DE04` 那筆 16-byte big-endian 資源目錄記錄,指向放在韌體零區的私有 pack)
   是目前唯一不靠解譯器 hook 的路,但**欄位語意還沒追過**。追出來,
   「換掉整個資源集」就成立了,三個 Thumb hook 可以整組拿掉。

模擬告訴不了你的事:GUI 會不會把結果畫出來、某個螢幕什麼時候被解析、
以及被替身取代的原廠函式原本會做什麼。
