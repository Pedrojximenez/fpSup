# USB shell — 代辦

USB shell 目前只有作者在用，所以改規格不必顧慮外部相容性 —— 這是排程上的
自由度，不是重要性的判斷。這裡的項目是「晚點做」，不是「不重要」。

---

## 1. 開機時的配置從三次降回一到兩次 ★ 已定案，等排程

**問題。** 2026-09-19 把共用池拆開之後，開機的配置次數變多了：

```
之前   腳本 memmgr bufmem get 1 MiB                       1 次
之後   loader    64 KiB   暫存，stage2 回來就還掉
       worker     1 MiB   spawn 裡
       worker    1408 B   程式碼那塊
                                                          3 次，共 1.06 MiB
```

總量沒變，**次數變三倍**。gyro 搬進池之後還會再加第四次。

而配置很可能就是開機最貴的一段：2026-09-17 的開機影片裡，進度條卡在
`020` 三秒半才跳 `030`，而那一段在當時的腳本裡正是
`memmgr bufmem get 0 1048576`；舊程式碼自己的註解也寫著
「the allocation is seconds; say so rather than look stalled」。

⚠ 未證實：借 echo 呼叫 heapalloc 要 333 KB 是瞬間回來的（暖機狀態）。
所以「配置很慢」只有影片這一個證據，而且是舊卡。

**做法。**

1. `putfile` 改成每次自己跟分配器要暫存區 —— `getfile` 已經是這樣做的
   （輸出裡的 `buffer 0x5F900980 (333388 bytes asked for)` 就是）。
   putfile 目前借 worker 的池、放在 `+0x10000`，而那正是 worker 要 1 MiB
   的唯一理由。
2. worker 的池從 1 MiB 降到 32 KiB。它自己只用到 `0x6828`：
   幀 `+0`（4 KiB）、擷取 `+0x2000`（16 KiB）、fault 計數 `+0x6800`（40 B）。
3. 程式碼那塊併進同一次配置（`+0x7000`，1404 B），總共要 32 KiB。

   ⚠ 這是「在一塊裡面用固定偏移」，也就是今天才剛拿掉的那個模式 ——
   差別在於**這塊只有 worker 一個使用者，所有偏移都在同一個檔案裡**。
   當初出事的是「一塊池、五個互不相識的使用者、靠註解協調」。
   併之前要確認 putfile 那一步真的做完了，否則又變成兩個人共用一塊。

結果：開機配置 `64 KiB + 32 KiB` 兩次，而且大的那次還是用完就還。

---

## 2. 退路卡的 worker 位址跟退役的 copyprobe 撞

`WORKER_AT = 0xC072E800`（非 --loader 的退路卡把 worker 放這裡）跟
`_retired_2026-09-19/copyprobe.S` 的 `SCRATCH` 同一個位址。

實務上踩不到（退路卡是純 shell，不會跑 copyprobe），但這正是「靠約定
避開」的老毛病。挪開，或在 build 時檢查。

---

## 3. 進度條 —— 先不要動，等數字

今天兩個看起來合理的模型都被推翻了：

- ❌「display 一條 283 ms」：暖機逐條實測全是毫秒等級
  （`display text` 1.4 ms、`display osd` 0.9 ms、`mem set` 0.8 ms）。
- ❌「開機時顯示子系統還沒起來所以慢」：開機影片顯示 **AutoRun 是在
  live view 完全跑起來之後大約 3 秒才開始執行的**（logo 2.5 s、
  live view 3.0 s、進度條 5.8 s）。相機那時候是暖的。

所以那 8.9 秒花在哪裡，目前沒有可信的解釋。**要量，不要推論。**

量法：loader 在自己頭尾記 TK-OS 的 tick，開機後把那幾個字讀出來。
要量的那一段現在就在 loader 裡，是程式碼，不佔 AutoRun 命令。
前置工作只有一項：找出 tick 計數器的位址。

### OSD 繪圖模型 —— 2026-09-19 實機定版

**三緩衝，而且每一個操作只碰一個 buffer。**

    畫一次 → 閃（三格裡有一格有）
    畫三次 → 穩

`display text`、`display osd 1 <color>`（整片填色）、`display osd 0`（關圖層）、
`display osdfile` **全部都是**。沒有「一次作用在全部 buffer」的指令。
build_autorun 進度條每格送 3 遍就是這個原因，那個註解一直都是對的。

### ★ 真正的規則（2026-09-19 早上，階梯式實測定版）

**啟用圖層要三遍；啟用之後每次繪圖一遍就夠，而且穩定。**

    一次性   display osd 1 0x00000000   ×3    啟用圖層。透明就行，不遮畫面。
    之後     display text <任何字>       ×1    立刻生效、不閃、不必重送

逐階測出來的：

| 做法 | 結果 |
|---|---|
| 進選單再出來（整個重畫）之後，直接送一條 `display text` | **什麼都沒有** —— 圖層被關掉了 |
| `display osd 1 0x00000000` ×3，再送一條 `display text` | **出現，穩定** |
| 送一次之後十秒完全不下命令 | **還在** —— 不是靠連續重送撐的 |

**不透明底是不需要的。** 昨晚以為「整片不透明才會穩」，錯了：那片底幾個
小時後被 UI 重畫洗掉了，文字卻一直留著。真正起作用的是「圖層在三個 buffer
裡都被啟用過」。

⚠ 還有一個對不起來的觀察：更早一次「透明啟用 ×3 之後送 osdfile」是會閃的。
目前沒有解釋，重做這條之前不要把它當成已知。

**清掉的方法**不是任何關閉指令，是讓 GUI 整個重畫一輪 —— `key MENUON`
進選單再出來。實測無效的：透明填滿 ×6、`display osd 0` ×3、`display reset`
（都回 ok，畫面不動）。順帶這也把圖層關掉，所以清完要重新啟用。

**`(h) (v) (offset)` 三個參數都不能決定位置**，圖一律貼左上角
（試過 `256 64 0`、`0 0 0`、`384 309 0`、`offset=341×1024`）。要排版就做
整片 1024×682 的圖，位置畫在圖裡面。

**HDMI 看不到 OSD** —— 填色在 LCD 上有、HDMI 輸出沒有。驗畫面只能看 LCD
或截圖，HDMI 擷取只能看影像本身。

⚠ `display osd 1 <color>` 的顏色通道順序不是筆記寫的 ARGB：送 `0xC00000FF`
（照 ARGB 該是半透明藍）實際出來是半透明綠。要重新定。

### 開機畫面的成本

    display monitor 0 1                1
    display osd 1 0x00000000     ×3    3     啟用圖層，一次性
    display osdfile \BOOT.TIF …   ×1    1     logo，可選
    display text <每一格>         ×1    1 條/格
    display text <結束畫面>       ×1    1

| 版本 | 命令數 |
|---|---|
| 現在，完整 5 格 | 31 |
| 現在，精簡 2 格（FAST2） | 19 |
| **新做法，9 格** | **14** |
| **新做法，2 格** | **7** |

格數想加多少都行，一格一條。而且進度條疊在 live view 上，不遮畫面。


已經確認可用的素材：
- `display osdfile <path> (layer) (monitor) (h) (v) (offset)` 吃**標準
  32-bit RGBA 未壓縮 TIF**（PIL 直接存的就能用），一條命令完成讀檔、
  解碼、貼上，alpha 遮罩有效（實測半透明綠透出底下的畫面）。
- OSD 表面：1024×682 **ARGB4444**，2 bytes/px，高 4 bits 是 alpha。
  `.xci` 表頭 32 bytes：`'XC'` + payload 大小 + u16 寬 + u16 高 + stride + 格式 id。
  位址由 `display osd`（不帶參數）回報，雙緩衝輪流。
- ⚠ 畫上去的東西會被相機 UI 的重繪洗掉 —— 跟 `display text` 一樣。
  進度條每格送 3 遍就是在跟重繪搶。
- HDMI 擷取卡（`AVerMedia ExtremeCap UVC`，avfoundation 裝置 2）可以
  直接抓相機畫面，1920×1080，不用繞截圖檔。

---

## 4. `copyprobe.S` 已退役

`projects/usb-shell-sup/_retired_2026-09-19/copyprobe.S`，理由寫在它的檔頭。
