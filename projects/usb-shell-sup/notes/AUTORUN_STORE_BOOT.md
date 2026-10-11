# 開機加速:loader 住在設定區(store-boot)

> **2026-09-25 更新(LOADER_V2):** 每張 `--loader` 卡的 stage2 現在都會先註冊關機回呼、記下被覆寫的韌體字,關機時寫回;`--loader-hook` 讓暖開機由 `0xC03DA420` 直接叫 loader、不跑 AutoRun;合併頁面的選項改為 Fast Start 2(`--store-boot --loader-hook --four-box-bar`)。本筆記以下內容是之前的狀態,新的設計、上機結果與未解問題見 `LOADER_V2.md`。

2026-09-18 實作並實機驗證。**程式碼全在 `fpSup` 工作區,尚未提交。**

一句話:AutoRun 只寫 29 個字的引導碼,loader 本體住在 `XC_CommonSaveData`
(開機自己從 flash 回來)。引導碼驗過 magic 就把它複製進注入區、跳進去;
loader 載完把 AutoRun 解譯器中止 —— **穩態一張卡只執行 66 條命令**
(同樣的卡不走設定區是 117 條,第一次開機 211 條)。

前情:`research/firmware/notes/PERSISTENT_STORE_COMMONSAVE.md`(設定區能存 824 bytes,
量測)、`research/firmware/notes/AUTORUN_INTERPRETER_AND_ABORT.md`(解譯器怎麼停,靜態 RE)、
`research/firmware/notes/DRAM_SELF_REFRESH_AND_WARM_BOOT.md`(為什麼不走熱記憶體)。

---

## 1. 三個零件

| 檔案 | 大小 | 住哪 | 做什麼 |
|---|---|---|---|
| `fpSup/fp_usb_shell/asm/store_boot.S` | 116 bytes / **29 字** | `0xC072F700` | 驗 magic、複製、清快取、跳進 loader |
| `fpSup/fp_usb_shell/asm/loader.S` | 464 bytes / 116 字(含 store+abort) | `0xC072DE64` | 原本的載入工作 + 發佈自己進設定區 + 武裝中止 |
| `fpSup/fp_usb_shell/build_autorun.py` | — | — | `--store-boot` 開關,量 loader、算 magic、拒絕放不下的組合 |

`store_boot.S` 是 untracked 的新檔;另外兩個是改動。組建:

```
./build_autorun.py --loader --store-boot --out <dir>/AutoRun.txt --banner fpSup-SHS4!
```

診斷用:`--abort-now`(loader 當場中止,不武裝 —— banner 不會畫)、
`--abort-always`(沒有設定區也中止,用來把「中止」跟「設定區」拆開量)。
畫面成本用環境變數:`FPSUP_NO_BAR=1` / `FPSUP_MIN_BAR=1` / `FPSUP_THIN_BAR=1`。

## 2. 記憶體地圖

```
0xC072DE64  CAVE_LOW      loader 本體(CALL 巨集烤死在這個位址,不能搬)
0xC072F050  LOAD          worker,到 0xC072F6A8
0xC072F6D8  POOL_DESC     配置器描述子 16 bytes(要活過 H_GET → H_ADDR)
0xC072F6F8  STORE_FROM    ★ 握手字:1 = 這次是從設定區進來的
0xC072F6FC  (STORE_VER_AT) 死常數,沒有任何人讀 —— 見 §8
0xC072F700  STORE_BOOT_AT 引導碼。★ 絕對不能放 CAVE_LOW,它會複製到自己頭上
0xC3075264  STORE         設定區裡的本體 = magic 1 字 + loader 原文
```

`build_autorun` 會擋兩件事:worker 長到碰 `POOL_DESC`、引導碼長到超出注入區頂
(`CAVE_END = 0xC0730000`)。

## 3. 開機流程

**第一次(或驗不過)**

```
第 1..55 條:33 條 mem set(3 畫面補丁 + 29 引導碼 + 1 改 echo 指標)+ 22 條畫面
echo          → store_boot:magic 不符 → 什麼都不碰,回傳 0
banner        → ⚠ 這時候畫出來的 banner 是假的,載入還沒開始
echo          → store_boot 再失敗一次 → 回傳
…            → 慢路徑:116 條寫 loader、改指標
echo          → loader 跑完整流程
                STORE_FROM == 0 → 把自己寫進設定區(magic 最後才寫)
                            → 不武裝中止
              → 腳本正常跑完
```

**穩態**

```
第 1..55 條:同上,一模一樣
echo          → store_boot:magic 符 → 複製 464 bytes 進 CAVE_LOW
                → 清 D/I cache → STORE_FROM = 1 → 跳進 loader
                loader 載完整個 VSHL.BIN、起 worker
                STORE_FROM == 1 → 不重寫 flash → 把 echo 指標改成 abort_entry → 返回
banner        → 這時候是真的
echo          → abort_entry:彈出註冊項、[ctx+0x90] = 0 → 解譯器停在這裡
                (後面 145 條永遠讀不到)
```

**一行兩用**:第 66 條那個 `echo`,快路徑是中止點,慢路徑是「再失敗一次然後往下走」。
AutoRun 沒有條件式,這是唯一能表達分支的寫法。

**自愈**:magic 不符就完全不動作,最壞情況只是退回今天的開機速度。
會不符的情況 —— 設定區沒播種過、換了另一張卡、loader 改過一個位元、
使用者做了設定重置、韌體把那塊欄位收回去用。全部同一個結果:走慢路徑、順手重新播種。
半寫的 store 也安全,因為 **magic 是最後一個寫的字**。

## 4. ⚠ 設定區只剩 4 bytes

```
可用(連續、實測存活)   468 bytes   0xC3075268 .. 0xC307543C
loader(store 組態)      464 bytes
剩                          4 bytes  ← 一條指令
```

下一個往 loader 加東西的人會直接撞牆。**不會靜默** —— `build_autorun` 會
`sys.exit('loader is N bytes; the store holds 468')`,而且引導碼與 loader 的長度
量兩次、對不起來也 exit(同一個常數放兩個地方曾經讓每次開機都靜默失敗)。

要空間有三條路:把 provision/abort 以外的東西推進 `VSHL.BIN` 的 stage2;
用設定區的第二、三段(`+0x210..+0x280` 112 bytes、`+0x290..+0x380` 240 bytes,
不連續,引導碼要多一個迴圈);或砍掉 `abort_entry` 的表掃描改用直接取堆疊頂
(會在巢狀腳本時拿錯,不建議)。

## 5. 表頭為什麼從 16 bytes 縮到 1 個字

原設計(`PERSISTENT_STORE_COMMONSAVE.md` §3)是 magic + 版本 + 長度 + CRC。
現在只剩 magic,三個欄位各有各的死法:

- **長度** 改成編譯期常數。從「正在被檢查的東西」讀長度,而複製迴圈會照著跑 ——
  一個垃圾長度會從注入區一路寫穿 payload 跟 worker。值不可能錯,就不需要守衛。
- **magic 改成 `sha256(loader bytes)[:8]`**,目前這一版是 `0xD78EABD2`。
  手寫字串要**人**去記得改:`'fpLD'` → `'fpL2'` 那一輪,一個晚上 loader 改了四次
  而字串沒動,那四版任何一版都會「magic 對、長度不對、跳進去」。
  derive 之後這個狀態不可達,**magic 就是版本**,而且是在跳進去**之前**驗的。
- **CRC / 版本** 的工作移到 loader:比對「卡片宣告的版本」而不是自己烤進去的常數
  (設定區活得比卡片久,舊 loader 拿自己的常數驗自己一定過,參考值必須來自外面)。
  ⚠ 但內容雜湊上線之後這條就多餘了,**版本字沒有實作,常數還留在 `build_autorun.py:109`**。

## 6. ⚠ 中止解譯器欠一個彈出 —— 花掉一天的 bug

`AUTORUN_INTERPRETER_AND_ABORT.md` §4 寫「寫旗標讓韌體自己收尾,少一個我們要負責的步驟」。
**那是錯的,而且錯得很貴。** 收尾回呼 `0xC03DA700` 是這樣:

```
ldrb r1, [r4, #0x90]
cmp  r1, #0
beq  跳過
bl   0xC0420D90        ← 把註冊項彈出、depth −1
```

清零 → 彈出被跳過 → depth 降不回 0 → 相機一直以為有腳本在跑。

| | 結果 |
|---|---|
| 不中止 | shell 通 |
| 中止,正常時機 | **shell 不通** |
| 中止,提早五秒 | shell 不通 |
| 中止 + 補上 `CALL 0xC0420D90` | shell 通 |

**只有 shell 卡會死**,worker 是活的但回覆送不出去(`ERR shl frame0 moved=0/64`);
og3k 那類 payload 完全沒事。而 shell 卡壞了就沒工具查。
規則:**誰清那個位元組,誰就欠那個彈出。** 現在 `abort_entry` 在清零前先彈出,
收尾看到 0 會跳過它自己那次,淨結果剛好一次。

**判讀規則:看進度條,不要看 banner。** banner 畫在中止點之前,兩條路長得一模一樣;
首開甚至會看到兩次 banner。要看的是進度條有沒有繼續走到 090。

## 7. 同一晚順手搬掉的三件事

都跟設定區無關,但都在減 `mem set`:

- `memmgr bufmem get` 從腳本搬進 loader(`H_GET 0xC001D740` / `H_ADDR 0xC001D7F0`,
  class 0 = USER,1 MiB;位址照樣留在 `0xC3757A7C` 給下游)。少一條腳本命令,
  也少一個「腳本必須按順序做對」的東西。
- loader 裡建任務的 24 個字砍掉 —— `worker.S` 的 bootstrap 本來就自己 `tk_cre_tsk`,
  loader 是在幫一個會自己建任務的 payload 建任務。VSHL 的 entry 也從 `serve` 改成 `spawn`。
- 7 個韌體補丁字 + 17 個 worker 狀態零 = **24 條 `mem set` 改成 VSHL.BIN 的區段**。
  它們都是「固定值寫固定位址」,那就是區段的定義。

## 8. 命令帳(數出來的)

| 卡 | 執行命令 | mem set | display |
|---|---|---|---|
| `--loader`(不走設定區) | 117 | 73 | 43 |
| `--loader --store-boot` 第一次 | 211 | 156 | 52 |
| `--loader --store-boot` 穩態 | **66** | 33 | 31 |

穩態那 33 條 mem set 拆得剛好:3(畫面補丁)+ 29(引導碼)+ 1(echo 指標)。

## 9. ⚠ 但開機時間的大頭是畫面,不是這些命令

同一晚量到的(`boot-time-levers`):兩張卡 `mem set` **完全相同(33 條)**、VSHL 同一份,
只差 display 條數:

| 卡 | 快路徑 | display | 實測 |
|---|---|---|---|
| og3k-pool | 66 | 31 | 8.9 s |
| og3k-minbar | 54 | 19 | **5.5 s** |
| og3k-nobar | 45 | 10 | 卡在桌面上,**還沒量** |

→ 12 條 display = 3.4 s,**約 283 ms 一條**。

**三件要說清楚的事:**

1. **`mem set` 的單價至今沒有直接量到。** 上面那組實驗兩張卡的 `mem set` 條數相同,
   所以它對 `mem set` 一個字都沒說 —— 而 store-boot 省的正是 `mem set`。
   舊資料能給的最好估計是 ~38 ms(2026-09-05 那兩張卡的差幾乎都是 `mem set`)。
   照這個估:穩態比 `--loader` 少 40 條 `mem set`(≈1.5 s)加 12 條 display(≈3.4 s)。
   **⚠ 兩個都是估算,沒有一個是直接量 store 卡得到的。**
   `store_boot.S` 跟 `build_autorun.py` 的註解裡還寫著「每條 `mem set` 約 65 ms」,
   那是舊數字,沒有實驗支持。
2. **那兩個數字的量測起點沒記下來。** 兩式相減除了 283 ms,還得到
   「固定開銷 + 33 條 `mem set` = 0.13 s」。如果起點是通電,這個值不可能
   (相機自己開機就要好幾秒)。所以起點應該是「第一格進度條出現」,但沒寫,
   下次量之前必須先把它定義清楚,否則所有秒數都不能互相比較。
3. **`display osd` 的用法可能整個是白付的。** 用法字串是 `(on:1,off:0) (color)` ——
   它是「打開圖層」不是「呈現」,而 AutoRun 每條 `display text` 後面都跟一條,
   那時圖層早就開著。如果貴的是那個 enable,進度條的成本可以直接歸零。
   未驗:`scratchpad/display_cost.py` 逐條計時 + 測「只有 text 不加 osd」會不會顯示。

**預測(可以否證)**:若 283 ms 線性,og3k-nobar 應落在 8.9 − 21×0.283 ≈ **3.0 s**。
桌面上那張卡量一次就知道。

## 10. 還沒做

1. **全部未提交** —— `fpSup` 工作區 13 個檔案 dirty,`store_boot.S` 還是 untracked。
2. **發布路徑不知道有這件事** —— 全樹只有 `build_autorun.py` 提到 store-boot。
   card-composer、合併卡、og3k 卡都還是舊路徑。
3. `STORE_VER_AT`(`build_autorun.py:109`)是死常數,該刪或該實作(§5)。
4. `display` 的真實成本(§9 第 3 點),以及量測起點的定義(§9 第 2 點)。
5. 源碼註解裡的「65 ms/`mem set`」要改掉。
6. `--retain-ram`(熱記憶體)**已經決定不走**,理由在 `DRAM_SELF_REFRESH_AND_WARM_BOOT.md`
   的結尾:位址每次開機不同、冷開機讀到 `FFFFFFFF`、引導碼只會變大。開關留著但不是這條路。

## 11. 桌面上那些卡是什麼

banner 就是卡的身分證。2026-09-18 這一輪:

| banner | 目錄 | 測什麼 |
|---|---|---|
| `fpSup-AR-O/T/S!` | `fpsup-autorun-compare/` | 三方比較包(原版 / 精簡 / 設定區),payload 固定只換 AutoRun |
| `fpSup-SHL1!` | `fpsup-shell-unified/` | 一份 loader 吃所有組態 |
| `fpSup-WIPE!` | `fpsup-store-wipe/` | 把設定區清掉,回到未播種狀態 |
| `fpSup-OG-P1/M1/N1!` | `fpsup-og3k-pool/minbar/nobar/` | ★ 畫面成本三階(§9) |
| `fpSup-SHN1!` | `fpsup-shell-nostore/` | 對照組:同一份 VSHL,不走設定區 |
| `fpSup-SHA1!` | `fpsup-shell-abortnow/` | 中止改成當場拿,拆開「武裝」這個變因 |
| `fpSup-SHB3!` | `fpsup-shell-abortalways/` | ★ 沒有設定區也中止 —— 把「中止」跟「設定區」拆開 |
| `fpSup-SHS4!` | `fpsup-shell-store/` | ★ **現行成品**,與工作區逐字元相同(只差 banner) |

`fpsup-shell-store` 跟 `fpsup-shell-abortalways` 是 18:57 的那一對,§6 的表就是它們量出來的。

相關記憶:`autorun-abort-owes-a-pop`、`boot-time-levers`、`persistent-store-commonsave`、
`autorun-loads-from-bin`、`release-build-must-be-scripted`。
