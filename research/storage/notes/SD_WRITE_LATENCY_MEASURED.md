# 錄影中 SD 寫入延遲 —— 實測 692 ms (2026-08-25)

> **根因已找到 (2026-09-13):見 `notes/research/storage/STORAGE_SPEED.md` §4。**
> 那張卡寫入只有 **94 MB/s**,而 FHD 12bit 錄影需要 **97.2 MB/s** ——
> 錄影期間卡是**滿載**的。692 ms 不是排程或優先權問題,是卡本身。
> 本文的結論(寫入移到背景 writer)仍然正確,只是原因不同。

## 一句話
陀螺執行緒直接寫卡,在 CinemaDNG 錄影中最壞要 **692 ms**,是陀螺 ring 容量
(240 ms)的 **2.9 倍**。**必須把寫入移到背景執行緒。**

## 數字
```
典型 write        4.1 ms
★ 最大 write      692 ms        ← ring 餘裕 240 ms 的 288%
閒置基準          典型 4 ms / 最大 8.7 ms
區塊              5120 bytes(640 樣本 = 0.256 s)
30 秒錄影         276 個區塊 = 1.38 MB
```
量測方式:`projects/gyro-sup/fpshell-era/gyro_block_hook.S`,hook 在 `0xC00D0794`,區塊填滿就寫,
`FN_TICK`(`0xC002B6E0`,微秒)夾住 write 呼叫。

## ⚠️ OVERFLOW=0 不代表沒掉資料
那個計數器只抓「單一 span 大於整個區塊」。ring 繞圈時 head 指標的差值看起來
仍然正常,遺失對計數器是**隱形的**。692 ms 期間 ring 繞了約 3 圈,
約 1700 個樣本被硬體覆寫 —— 這是推論不是量測,但很確定。

**要真的偵測遺失,drain 必須比對「head 移動量」與「經過時間 × 取樣率」。**

## 結論:走 stage6 的雙緩衝
緩衝需求其實很小:
```
要蓋過 692 ms × 20 KB/s ≈ 14 KB
32 KB 雙緩衝綽綽有餘
```
陀螺執行緒只複製(微秒級),writer task 承受那 692 ms。
這也解釋了 stage5 為什麼把全部資料留在 RAM、只在停止時寫檔。

stage6 的兩個致命錯已修並實機驗證(見 `notes/projects/open-gate/../../../projects/open-gate/notes/RECORDING_GEOMETRY_AND_LENS_PROGRAM.md`):
錯的 syscall 對(Cyc 而非主線)、ASCII 寫進 `stksz`。

## ★★ 前置條件:錄影時 daemon 必須斷開

> ⚠️ **訂正 (2026-09-10):這一節的變因寫錯了,而且比它早兩天就已經有正確答案。**
> 真兇是 **host 在 record-start 那一瞬間下的 shell 交易**,不是連線本身 ——
> 見 `RECORD_SHELL_COEXIST_RESOLVED.md`(2026-08-23 定案):那筆交易的 DWC3
> DEPCMD 撞上 record-start 的 link/power flutter → IRQ-0x34 livelock。
>
> 2026-09-10 實測:**daemon 全程連著、但按錄影前後主機完全不發指令 → 兩次錄影都正常。**
>
> 規則是「**按錄影時主機要靜默**」,不是「daemon 要斷開」。daemon 可以一直掛著。
> 下面那張表是在「daemon 連著**且正在 poll**」的條件下量的,別讀成連線本身的效應。
> 見 `FRAME_RATE_IS_VMAX.md` §7。

**這一輪之前所有錄影期測試的結果全部作廢** —— 每次錄影時 daemon 都連著。

```
沒接 daemon        → 錄影正常
daemon 連過再斷開  → 錄影正常
daemon 連著        → 凍結 / 影像空白
```
損壞只在連線期間,斷開就恢復。可行的工作流程:
```
連上 daemon → 注入、裝 hook、設定狀態
斷開 daemon → 錄影(hook 在相機端持續運作,不需要 daemon 在場)
再連上      → 讀結果
```

這推翻了舊結論「錄影凍結是主機輪詢造成的」—— 這次**完全沒有輪詢**也凍結,
真正的變因是**連線本身**(claim interface / arm wait / EP84 armed),不是輪詢。

## 走過的彎路(值得記,因為每一項都花了一輪)
| 誤判 | 真相 |
|---|---|
| `0xC0366020` 是 flush | 是 **close**(vtable 呼叫後 `str #0,[r4]` 清 handle)。每區塊呼叫 → 第二次寫入打到空 handle → 卡死 |
| ring `head` 是偏移量 | 是**絕對指標**(0x2E0075E4) |
| 「放不下就丟棄」 | 會卡在剛好不夠的位置(2252/2560),寫出條件永遠達不到 |
| 狀態放 `0x44F6ADC0` | 那是 **shell 自己的指令緩衝**(讀出來是 ASCII `"FPSH"`),每個指令覆寫一次 |
| 只計時 `write` | `write` 只進緩衝;**讀卡才發現檔案根本不存在** |

## stage6 已依此調整(2026-08-25,尚未實機跑過核心邏輯)
稽核 `codex/stage6_gyro_double_buffer_hook.S`,三項要改、兩項本來就對:
```
BUF_A = 0x44F6ADC0        ❌ 那是 USB shell 自己的指令緩衝 → 搬到池尾 0x44F6C000
STATE/FILE_* = 0x456Dxxxx ❌ 遠離已配置區 → 搬到池尾 0x44F6BE00
open 模式 0x0402          ❌ 檔案已存在就失敗 → 改成 7
0xC0366020 用法           ✅ 在 writer_close 裡只呼叫一次,正確
ring head 當指標          ✅ 本來就對
```
緩衝 32 KB → **16 KB**(0.82 s,蓋過 692 ms 有餘),少偷佔一半池空間。

**核心邏輯(雙緩衝交接、writer task 的 READY 輪詢、GFB6 block、CRC-32)從未實機跑過。**
下一輪的順序:注入但不啟動 → 確認 CALLS 在動 → 啟動 writer,閒置驗交接 →
**斷開 daemon** → 錄影 → 連回來讀 S_DROPPED / S_ERROR。
