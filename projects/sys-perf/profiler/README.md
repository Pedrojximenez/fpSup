# PC 取樣 profiler(2026-10-16，離線完成，**未上機**)

用途：知道 CPU 時間花在哪個**函式**。原廠 `analyzer tskmon` 只能分到任務。
依據：[`research/firmware/notes/PC_SAMPLER_HOOKPOINTS.md`](../../../research/firmware/notes/PC_SAMPLER_HOOKPOINTS.md)。

## 檔案

| 檔案 | 內容 |
|---|---|
| `pcsample.S` | 相機端：計時器通道處理函式，328 B(控制區 64 B + 程式)，與位置無關 |
| `pcsample.py` | 主機端：`check / install / start / stop / status / read / names / uninstall` |
| `analyze.py` | 離線報告：依任務、依函式 top N、`--callers` 依 LR 展開、`--task` 篩選 |
| `names.tsv` | 我們自己定的函式名稱(優先於 `out/symbols_vfunc.tsv`) |
| `test_pcsample.py` | unicorn：真映像的 IRQ 完整路徑，9 個情境 + 15 個突變 |
| `test_host.py` | unicorn：`pcsample.py` 對著模擬相機跑完整流程，5 個情境 + 11 個突變 |

## 怎麼運作

每次計時器中斷寫一筆 16 B 記錄到環形緩衝：

| 偏移 | 內容 |
|---|---|
| +0 | 被中斷的 PC(`[0xC42F1FBC]`) |
| +4 | 被中斷模式的 LR(只讀 SVC/SYS/USR 的 bank) |
| +8 | `tid<<8 \| SPSR&0xFF`(tid 0 = ctxtsk 為 0) |
| +12 | `current_time`(ms) |

先寫記錄，再 `dmb`，最後更新索引。

兩種掛法，都只改指標：
- **B(預設)**：用原廠 `C0016210` 註冊閒置通道(預設 ch 3)，週期 12037 counts ≈ 1.003 ms，不跟 1 ms tick 對齊；`C00163F8` 停止。
- **A**：把 `0xC303380C`(ch 0 的 handler)換成我們的函式，記完尾跳回 `C0016978`。取樣會跟 tick 對齊。

`install` 會自我檢查：0.5 s 內呼叫次數要合理，**OS 時鐘還要在走**，不對就自動移除。
環形緩衝從配置器 class 0 要(預設 16384 筆 = 256 KiB，約 16 s)。程式碼放 `cave.claim`，重開前不釋放。

`uninstall` 的順序：先關 `C_EN`，再還原指標或停通道，接著確認呼叫已停止，最後才釋放環。
安裝途中斷線也能用 `uninstall` 收拾(狀態 `arming`)。

## 測試(離線)

```sh
cd projects/sys-perf/profiler
python3 -B test_pcsample.py && python3 -B test_pcsample.py --mutate
python3 -B test_host.py     && python3 -B test_host.py --mutate
```

**`test_pcsample.py`** 從 `C00014A0` 進入，走 `C0000E64`、hook `C0000EC4`、計時器 ISR `C0016000`、我們的函式、(A 才有)`C0016978`、`ret_int` `C0000F88`，最後 `ldm ...pc}^` 回到被中斷點。
- 斷言：r0–r12、sp、lr、CPSR(含 Thumb)、d0–d15 都還原，IRQ sp 回到頂端，記錄內容正確，OS tick 恰好一次(B 為零)。
- 也涵蓋：idle、停用、skip/limit、繞圈，以及亂的 SPSR 不會切到非法模式。
- 只有 `knl_timer_handler` 被換掉：它在模擬裡數 tick，並推進 `current_time`。

**`test_host.py`** 讓 `C0016210`/`C00163F8` 在模擬裡真的執行。時間流逝用逐毫秒的完整 IRQ 模擬，通道週期取韌體寫進暫存器的值。
- `mem set` 模擬兩成掉寫入。
- 突變全部被抓到：漏寫指標、漏還原、漏停通道、漏釋放環、B 沒給 handler、A 沒設 orig(OS 時鐘停 → 安裝自檢退回)、漏 I-cache 失效、安裝中斷沒記錄、沒開 EN、沒擋錄影、沒查通道佔用。

結果(2026-10-16)：兩組全部通過，26 個突變 0 個存活。

## 第一次上機

先問其他 session 有沒有人在用相機，相機停在 CINE 待機、**不在錄影**。

| 步驟 | 指令 | 要看到的 | 不對時 |
|---|---|---|---|
| 1 | `pcsample.py check`(唯讀) | `tick_handler=C0016978`、IRQ4 = (`C0000E64`,`C0016000`)、`ms_per_s≈1000`、ch 1/3/4/6 的 running/handler/hash 全 0、`irq_frame` 的 spsr 模式是 0x13/0x1F/0x10、PC 像程式位址 | 停下來，回去讀反組譯。**frame 不像就不要安裝** |
| 2 | `install --via B --ch 3` | 約 498 calls / 500 ms | 自動移除；shell 卡住就照 fp-firmware-call §5 冷開機(重開會重設計時器表) |
| 3 | `start`，等 2 s，`stop`，`read idle-1` | `analyze.py captures/idle-1`：模式只有 svc/sys/usr，PC 落在已知函式 | `C_FRAME` 錯，先 uninstall |
| 4 | 交叉驗證：同一個窗口跑 `analyzer tskmon_start`(ch 5，與我們無關) | 每任務佔比和 tskmon_top 差幾個百分點以內 | 我們的 tid 或取樣有偏差 |
| 5 | `names`，再 `uninstall` | `tasks.tsv` 有名字；ch 3 的 handler 與 running 歸零 | — |
| 6 | 之後要量選單或播放：install → start → 操作 → stop → read | | |
| 7 | 錄影：`start --skip 3000`，3 s 內按 REC，錄完停錄、等 10 s 再 `read` | 錄影中**不碰 USB** | — |

## 上機前尚未證實的假設

1. 被中斷的 PC 在 `0xC42F1FBC`：IRQ 堆疊頂 `0xC42F1FC0` 而且不會巢狀(靜態)。**模擬用的是同一個假設，所以證明不了它。** 步驟 1 會檢查。
2. ch 1/3/4/6 沒人用：只看到沒有靜態呼叫 `C0016210`，可能有程式直接寫暫存器。`check` 和 `install` 都會檢查，`C0016210` 遇到被佔用的通道也會回 3。
3. tid = `[ctxtsk+8]`；閒置時 ctxtsk=0。tskmon 把閒置算給 `inittsk`(tid 1)，所以兩邊的 idle 可能分在不同 tid，比對時要合併看。
4. 計時器 pending 是「寫 0 清除」：從 ISR 的 `str ~bits` 推論，模擬就是照這個做的。
5. class 0 的環能不能跨錄影握著：沒有測過(見 memory「配置器不能跨錄影」)。
6. **插著 profiler 關機沒有測過**：關機前一定要 `uninstall`。
7. `C0016210` 的 lvl 參數(0x37)照抄 `timer_startup`，意義未知。
8. 用切 CPSR.M 讀 banked LR：qemu 上正確，真機未驗。
9. 關中斷的區段看不到：時間會落在開中斷後的第一條指令。快取全清這類函式仍落在函式本體(`bx lr` 前)，但超過 1 ms 的那段會少算。
10. 真正的 `Camera` 類別(對 `putfile`/`cave`/`callfn` 的薄包裝)只有在真機上才會被執行到。
