# PC 取樣 profiler 的插入點(2026-10-16，離線靜態)

只讀 `out/seg0_c0000000.bin`。沒有相機 I/O。標示：**[靜]** = 反組譯直接看到；**[推]** = 推論，要上機驗證。
工具在 `research/firmware/pc_sampler_scan/`(`fwdis.py ADDR LEN`、`callers.py ADDR`、`movwt.py VALUE…`)。

## 1. 中斷註冊與系統 tick

**兩層表** [靜]
- `tk_def_int` 實作 `C0001660`(syscall 表 `C0001040` 第 0x37 格；stub `C0016A7C`，service `0x80370200`)。
- TA_HLNG(attr bit0)且 IRQ<0x80：低階表 `0xC30000AC+n*4` = `C0000E64`(高階包裝，存 VFP)，C 處理函式放在 `0xC30004AC+n*4`。
  不是 HLNG 的話，處理函式直接放低階表。
- 驅動常用的包裝是 `C000FBB8(irq, handler)`：以 HLNG 註冊，舊值記在 `[0xC2EF6F88]` 表；`C000FCA0(irq, 1)` 開啟該 IRQ。
- 中斷控制器：`[0xC3033460]` 是暫存器基底指標。`C0010130` 讀 `[[base]] & 0x7F` = 目前 IRQ 號；
  `C000FFF0(irq)` 把 `~(1<<irq%32)` 寫到 `base+4+(irq/32)*4`，推測是 ack/清除 [推]。IRQ 31 會被跳過(當作 spurious)。

**計時器驅動**(8 個通道，共用 **IRQ 4**)[靜]
- 初始化 `C0016080`：用 `C000FBB8(4, C0016000)` 註冊共用 ISR，接著開啟 IRQ 4。
- ISR `C0016000`：讀 `[[0xC30337FC]+4] & [0xC3033808]`，寫入 `~bits` 清除，再依序呼叫 `[0xC303380C + ch*4]`。
- 通道暫存器在 `[0xC30337F0] + ch*16`：`+0` ctrl(`count<<8 | 0x40 | 0x10(有 handler)`)、`+4` 目前計數、`+8` 啟用。
- API：`C0016190(ch, &info)` 取得資訊(時脈 **12 MHz** = 0x00B71B00、計數上限 0xFFFFFF)；
  `C0016210(ch, {count, handler, lvl(1..0x6E), 0, 0})` 啟動週期中斷(通道已被佔用時回 3)；
  `C00163F8(ch)` 停止；`C00165E8(ch, &cnt)` 讀目前計數。

**系統 tick = 計時器通道 0，週期 1 ms** [靜]
- `timer_startup` `C000D808`：`C0016210(0, {12e6/1000 = 12000, C0016978, 0x37})`。
- `C0016978`：taskindp(`0xC303326C`)加 1，呼叫 `knl_timer_handler` `C000D9A8`，再減 1。
- `C000D9A8`：`current_time`(`0xC301EAE4`，64 位元，單位 ms)加 1，處理 timeout 佇列 `0xC301FE90`。
- 順帶發現：每個 tick 都會給 ctxtsk 記帳。`TCB+0x1E`(int16)>0 時 `TCB+0x6C`(stime)加 1，否則 `TCB+0x70`(utime)加 1。
  這是原廠內建、以 tick 為單位的每任務 CPU 計數 [靜；欄位語意是推論]。

**各通道佔用情況**(以靜態呼叫 `C0016210` 的位置為準)

| 通道 | 使用者 |
|---|---|
| 0 | OS tick(`C000D884`) |
| 2 | `C00008C8` 裡的暫時性延遲，用完就停 |
| 5 | 原廠 tskmon 時鐘(`C002B63C`；`C002B718` 讀通道 5 計數加秒數 `0xC30781A4`) |
| 7 | `C06808A8`(在 analyzer 的程式區附近) |
| 1、3、4、6 | 找不到任何呼叫者 → **可能閒置** [推：可能有程式直接寫暫存器] |

## 2. IRQ 進入點與堆疊佈局

- 向量 `+0x18` → `C00014A0`(IRQ 模式)。依序推入 `lr-4`、`ip`、`spsr`、`r3`、`r0-r2`，取 IRQ 號，
  再彈回 `r0-r2`，以 `bx` 呼叫低階表裡的位址 [靜]。
- **呼叫低階處理函式時(IRQ 模式)**：`[sp+0]=r3`、`[sp+4]=被中斷的 CPSR(spsr)`、`[sp+8]=ip`、**`[sp+12]=被中斷的 PC`**。
  `r0-r2` 是被中斷者的值，`ip` 等於表格項目位址。`C0000E64` 依靠 `ip` 算出 IRQ 號，所以包在它外面的程式必須保留 `ip`、`r0-r2` [靜]。
- 高階路徑 `C0000E64`：再推入 `r0-r2`、`d0-d15`、`fpscr`，切到 `0xD2`(IRQ 模式、I/F 關閉)，再推入 `{cpsr, lr}`、`ip`，
  然後呼叫 `[0xC30004AC+irq*4](r0=irq)` [靜]。所以 **C 處理函式在 IRQ 模式下執行、中斷關閉、可以用 VFP**。
- IRQ 堆疊頂端是 `0xC42F1FC0`(重置碼 `C000060C`)[靜]。處理函式執行期間中斷是關的，不會巢狀，
  所以被中斷的 PC 固定在 **`0xC42F1FBC`**，spsr 在 **`0xC42F1FB4`** [推，上機時檢查 spsr 的模式位元與 PC 範圍]。
- 處理函式返回後 → `C0000F88`(ret_int)：切到 SVC，把 frame 搬過去，視 `0xC303326C`(taskindp)、`0xC3000094`(dispatch disabled)、
  中斷遮罩、`ctxtsk != schedtsk` 決定是否跳到 dispatcher `C0000D10` [靜]。
- 原廠有中斷進出 hook：`[0xC2EF6E30]/[0xC2EF6E34]` 平時指向 `C0000EC4/C0000EDC`；`C0000F50` 把它們切到 `C0000F14/C0000F38`，
  改呼叫 `[0xC2EF6E38]`/`[0xC2EF6E3C]`(參數 r0=irq)。`C0000F6C` 切回 [靜]。

## 3. 目前任務

- **ctxtsk = `[0xC3000098]`**，schedtsk = `[0xC30000A0]` [靜：dispatcher `C0000D48`/`C0000D90`]。
- 閒置時 ctxtsk = 0：dispatcher 迴圈 `C0000D64` 會先把 ctxtsk 清成 0 [靜]。
- **task id = `[TCB+8]`**：原廠 dispatch hook `C0000DE4/C0000E0C` 以 `r0=[r8+8]` 呼叫使用者 hook，跟 T-Kernel 的 TCB 佈局一致 [靜+推]。
  `TCB+0x78` = 存起來的 sp。
- 原廠 tskmon 走 dispatch hook(`[0xC2EF6E28]/[0xC2EF6E2C]`，由 `C0000E24` 設定，呼叫者 `C00077E0`/`C0007840`)，
  時間戳記來自通道 5 [靜]。

## 4. 建議的插入方式

**A(最簡單)**：把通道 0 的 handler 指標 `0xC303380C` 從 `C0016978` 換成包裝函式。
包裝函式讀 `[0xC42F1FBC]`(PC)、`[0xC42F1FB4]`(spsr)、`[0xC3000098]`→`[+8]`(tid)，寫進環形緩衝區，再 `b C0016978`。
它是一般 C 呼叫慣例、IRQ 模式、中斷關閉。只改 RAM 的 4 bytes，可以還原。
缺點是取樣和 1 ms tick 對齊：在 tick 剛過就被喚醒、又在下個 tick 前睡回去的任務會系統性地取樣不足。

**B(去偏差)**：用閒置通道(1/3/4/6 擇一)，透過 `C0016210(ch, {≈12036(非 1 ms 整數倍), wrapper, 0x37, 0, 0})` 註冊，
包裝函式內容同 A，結束時用 `C00163F8(ch)` 停止。前提是該通道真的沒人用：上機先讀 `[0xC30337F0]+ch*16+8` 確認為 0 [推]。

**限制(兩種都有)**：關中斷的區段取樣不到。例如 `C000E91C` 等快取維護函式全程關 IRQ，
它們花的時間會記到開中斷後的第一條指令(在呼叫者附近)，不會落在函式本體。
FIQ 路徑(`C0000874`)也看不到。

## 重現

```sh
cd research/firmware/pc_sampler_scan
python3 fwdis.py c00014a0 60     # IRQ 進入點
python3 fwdis.py c0001660 140    # tk_def_int
python3 fwdis.py c000d808 b0     # timer_startup(ch0, 12000, C0016978)
python3 fwdis.py c0016000 80     # 計時器共用 ISR
python3 callers.py c0016210      # 誰註冊計時器通道
python3 movwt.py c0016978 c3000098
```
