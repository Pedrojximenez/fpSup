# SIGMA fp：PTP + EP84 Bulk IN / RAW Stream 研究紀錄

更新日期：2026-08-17  
範圍：自有 SIGMA fp 硬體的韌體研究、RAM-only patch、USB driver 除錯。本文不涉及永久寫入韌體；目前修改正常情況下可由重新開機還原。

## 目標

最終希望同時保留：

1. PTP / gimbal 控制。
2. 獨立 USB Bulk 通道。
3. 先以 Bulk 通道建立雙向 Shell，再逐步替換為 RAW frame stream。

目前的最小里程碑是：Mac 從新增的 EP84 Bulk IN 收到一個固定 64-byte `EP84TEST` 封包。

## 已證實成立

### Composite USB descriptor

已能讓相機同時枚舉：

- Interface 0：PTP，class `0x06`，原始 endpoints `EP01 / EP82 / EP83`。
- Interface 1：vendor-specific，class `0xFF`，Bulk IN `EP84`。
- USB SuperSpeed 5 Gbps。

PTP 在 composite descriptor 下仍可運作。這證明「PTP + 第二介面」在 descriptor 與 host enumeration 層可行。

重要位置：

- Descriptor builder hook callsite：`0xC04DC618`
- Code cave：`0xC072723C`
- Active descriptor root pointer：`0xC30792C4`

### Shell command table

- Command table 起點：`0xC0BAC14C`
- Entry stride：`0x18`
- `echo` handler pointer：`0xC0BAC2F8`
- `log` handler pointer：`0xC0BAC478`
- `0xC0BAC2F4` 是 command name 尾端 padding，不是 handler。

曾經把 `0xC0BAC2F4` 認成 handler，這是已修正的重要錯誤。

### ARM / Thumb 呼叫模式

- `FUN_c01e62a8`：Thumb，呼叫指標需為 `0xC01E62A9`
- `FUN_c01e5998`：Thumb，呼叫指標需為 `0xC01E5999`
- `FUN_c001510c`（memcpy）：ARM，呼叫指標為 `0xC001510C`

ARM cave handler 使用 `BLX register` 呼叫上述函式。

### EP84 原生 mode-3 初始化

以 `FUN_c01e62a8(4)` 初始化 context 4 後，EP84 可避免 STALL，Mac 能收到 ZLP。

觀察到的 endpoint config：

- `0xC31E39E0 = 0x00082002`
- `0xC31E39E4 = 0x12FF2700`

Mode-3 ring：

- Descriptor slots 位於 context dump offset `0x80 / 0x90 / 0xA0`
- 一般 slot flags：`0xC69`
- Terminal/link descriptor flags：`0xC89`
- `_DAT_c31e3a18` 是三格 ring index。

### 原生 sender

`FUN_c01e5998(buffer, length)` 是目前使用的 mode-3 sender。

核心行為：

- 驗證 buffer address `>= 0x40000000`。
- 寫入目前 ring descriptor 的 DMA address、length、flags `0xC69`。
- 若 `_DAT_c31e3964 & 4 == 0`，走 start-transfer / doorbell `FUN_c01e6b80`。
- 若 active bit 已存在，走 ring update `FUN_c01e6cd8`。
- 成功後推進 `_DAT_c31e3a18`。

`_DAT_c31e3964`：`0xC31E3964`。

### Completion callback

Mode-3 completion 會經過 `FUN_c01e61a0()`，使用 callback pointer：

- callback global：`0xC30257B0`

callback 為 NULL 時，韌體會再次呼叫 `FUN_c01e5998(..., 0)`，形成持續 ZLP。因此測試 callback 必須先把自己替換成 no-op，避免無限重送。

目前已證實：

- 一次性 callback 會被呼叫。
- callback 能把 `0xC30257B0` 改成 no-op。
- callback 中呼叫 sender 的結果可寫回 cave 供 dump。

## macOS receiver

檔案：

- `/Users/dido/Documents/Codex/2026-08-16/4/ep84_read.m`
- `/Users/dido/Documents/Codex/2026-08-16/4/ep84_read`

Receiver 使用 IOUSBHost：

- VID `0x1003`
- PID `0xC432`
- Interface number `1`
- Interface class `0xFF`
- Pipe address `0x84`
- DMA request length 已確認為 64 bytes。

已發現並修正：成功收到 ZLP 後不應呼叫 `clearStall`。ZLP 不是 stall；在這時清 endpoint 可能打斷下一筆 transfer。

IOUSBHost 行為：

- 同步 `sendIORequestWithData` 能穩定收到 ZLP。
- 非同步 `enqueueIORequestWithData` 在此實驗中回 `kIOReturnNotResponding (0xE00002ED)`。
- 多筆與單筆非同步 request 都失敗，因此目前回到同步讀取。
- ZLP 後已移除 20 ms sleep，立即提交下一個 64-byte read。
- 2026-08-17 10:35 再移除開啟 pipe 後及 `NotResponding` 後的
  `clearStallWithError:`；`NotResponding` 不等於 STALL，清除 EP84 可能取消
  相機剛排入的下一筆 mode-3 transfer。Receiver 已重新編譯並 ad-hoc sign。
- 一輪可收到約 36–40 個 ZLP，但仍未收到非零 payload。

常見 IOReturn：

- `0xE00002D6`：`kIOReturnTimeout`
- `0xE00002EB`：`kIOReturnAborted`
- `0xE00002ED`：`kIOReturnNotResponding`

## 已測試的 payload buffer 路線

### 1. Code cave RAM：`0xC072E000`

固定 64-byte packet 放在 `0xC072E000`，內容開頭：

```text
45 50 38 34 54 45 53 54
E  P  8  4  T  E  S  T
```

Sender 曾回傳 `0`，descriptor 也曾顯示：

- DMA address：`0x0072E000`
- length：`0x40`
- flags：`0xC69`

但 Mac 只收到 ZLP。推測 code cave 雖可由 CPU 存取，未必是適合 USB controller 的 DMA buffer。

### 2. 韌體共用 USB buffer：`0x442F71C0`

Global `_DAT_c3025744` 指向：

- CPU alias：`0x442F71C0`
- Descriptor/DMA address：`0x042F71C0`

callback 改傳這個 buffer 後仍只收到 ZLP。此 buffer 被多個 PTP/USB 路徑共用，可能在 init 或其他 transaction 中被覆寫，不適合長期作為 EP84 私有 buffer。

### 3. `memmgr bufmem get` 私有 buffer

Shell 可使用：

```text
memmgr bufmem get <type> [size] [align]
```

已知：

- `type = 0..14` 對應 `XC_MEMTYPE`
- pool/type 0 是 USER，mode 無關且較穩定
- 結果結構：`0xC3757A7C = [address, size, tag]`
- address 為 0 表示配置失敗
- `memmgr bufmem rel` 可釋放，或重新開機自動釋放

本輪命令：

```text
memmgr bufmem get 0 0x1000 0x40
```

實際 `BUF.BIN` 與 `BUFPOST.BIN` 都是：

```text
address = 0x44F6ADC0
size    = 0x00000040
tag     = 0x00000000
```

結論：配置成功、callback 前後 metadata 一致，但 size 回報為 `0x40`，不是預期 `0x1000`。需要重新確認 Shell handler 的參數順序／解析規則；64 bytes 對本次 packet 仍剛好足夠。

最新 callback：

1. 從 `0xC3757A7C` 讀取配置位址。
2. 把實際位址記錄到 `0xC072DFE4`。
3. 若位址為 0，記錄 sender result `-1` 並退出。
4. 用 `FUN_c001510c` 將 64 bytes 從 `0xC072E000` 複製到配置 buffer。
5. 呼叫 `FUN_c01e5998(allocated_buffer, 64)`。
6. 把 sender result 記錄到 `0xC072DFE0`。

最新 dump `TX9013.BIN` 顯示：

- callback 已執行。
- callback 看到配置位址 `0x44F6ADC0`。
- sender result 是 `0xFFFFFFFF`（−1）。

所以 allocator 本身成功；這輪失敗發生在 sender/start-transfer 狀態，不是 allocation failure。

## 重要 dump 與偏移

AutoRun 目前輸出：

- `EC9*.BIN`：`0xC31E3800`, size `0x400`
- `EDC9*.BIN`：`0xC31E3200`, size `0x300`
- `REG9*.BIN`：`0xC3025700`, size `0x100`
- `TX9*.BIN`：`0xC072DE64`, size `0x220`
- `BUF*.BIN`：allocator result，callback 前
- `BUFPOST*.BIN`：allocator result，callback 後

相機 `mem save` 不覆蓋既有檔案，會自動產生 `000 / 001 / ...` 流水號。分析時必須按修改時間選最新檔，不能一直讀無尾碼檔。

下一輪 callback diagnostics 已移到 `0xC072E040`，避免擴充後的 callback
code 與結果區互相覆蓋：

- `0xC072E040`：sender return value
- `0xC072E044`：callback 實際讀到的 allocated address
- `0xC072E048`：AutoRun 完成 marker `0xE84E84EE`
- `0xC072E04C`：callback 入口時 `0xC31E3964` flags
- `0xC072E050`：sender 前 ring index `0xC31E3A18`
- `0xC072E054`：memcpy 後、sender 前的 flags
- `0xC072E058`：sender 後 ring index
- `0xC072E05C`：私有 buffer 第一個 word，預期 `0x34385045` (`EP84`)

固定 64-byte source packet 同步移到 `0xC072E100`。更新後的 AutoRun 與
`ep84_dma_callback.S` 已就緒，下一輪硬體測試可直接使用。

## AutoRun 執行時序

相機似乎每次開機只會執行一次 AutoRun。可靠流程：

1. USB 與 SD 都拔除。
2. 相機完全關機，等約 5 秒。
3. 開機，等 Live View 完整出現。
4. Mac 先啟動 `ep84_read`。
5. SD 作為本次開機第一次插入。
6. 等至少 15 秒再接 USB。
7. AutoRun 自身含 30 秒 sleep；接 USB 後仍需保持連線約 45–70 秒。

若 Mac 只看到 interface 0 / class 6，表示 hook 沒生效；正常 composite 應另有 interface 1 / class `0xFF`。

## 目前判斷

已經排除：

- Composite descriptor 不可行。
- PTP 與 vendor interface 無法共存。
- EP84 必然 STALL。
- Mac request buffer 長度為 0。
- callback 完全無法執行。
- allocator 配置失敗。

尚未解決：

- 為何某些 callback sender 測試回 `0`，allocator callback 最新測試卻回 `−1`。
- 為何 host 持續收到 ZLP，而非 descriptor 中要求的 64 bytes。
- active bit `0x4`、completion callback 與 ring update 的精確時序。
- transfer event 是否帶有 short-packet/error completion，而目前 dump 在 cleanup 後看不到瞬間狀態。

### 2026-08-17 10:39：callback 未觸發案例

完整 `TX9014.BIN` 顯示 AutoRun 已正常走到最終 dump，但 callback diagnostics
除了完成 marker 外仍全是 `0xDEADBEEF`，因此 callback 完全未執行。Allocator
前後皆為 `[0x44F6ADC0, 0x40, 0]`。最終 `0xC31E3964 = 0`、ring index
`0xC31E3A18 = 2`，三個 descriptor 仍是 length 0 / flags `0xC69`。

同時發現 AutoRun 雖已安裝 temporary `log` handler 作為 delayed native sender，
卻只呼叫了 `echo` 初始化，從未實際呼叫 `log`。下一版已補上 `log`，將其
sender return value 記錄在 `0xC072E060`；原本的 `0xC072DF84` 已落入擴充後
的 callback code 範圍，亦已修正以免 handler 回寫破壞指令。

### 下一版：mode-1 normal Bulk context 4

`FUN_c01e62a8()` 會依 endpoint context table 的 mode 選擇初始化方式。Context 4
位於 `0xC31E38C8` 的 mode 目前為 `3`，因而走 UVC/isoc ring。新測試會在
USB 枚舉完成後把它暫時改為 `1`，再執行 `FUN_c01e62a8(4)`。

由於 generic normal sender `FUN_c01e5740()` 會以 `FUN_c01e6110()` 選到第一個
mode-1 IN context（很可能是 PTP EP82），新 handler 不使用它，而是直接：

1. 將 `EP84TEST` 複製到 allocator buffer。
2. 填入 `DAT_c31e3264[4]` 指向的普通 descriptor，flags `0x813`。
3. 呼叫 `FUN_c01e6b80(9)`，其中 `9 = (context 4 << 1) | IN`。
4. 將 StartTransfer 結果記錄至 `0xC072E060`。

Handler 位於 `0xC072E180`，source 為 `ep84_bulk_context_sender.S`。

第一次 mode-1 測試在枚舉完成後才把 `0xC31E38C8` 由 3 改成 1，接著
`FUN_c01e62a8(4)` 阻塞，沒有最終 dump。這表示已啟用 endpoint 不宜熱切換
mode。下一個 probe 改在 USB reconnect 前設定 mode 1，並在任何 init 呼叫前
先輸出 `MODE.BIN` (`0xC31E38C0`, 0x20 bytes)，因此即使 init 再次阻塞，仍可
判斷 endpoint registration 是否把 mode 覆寫回 3。

Probe 結果成功：`MODE.BIN` 與最終 context dump 都顯示 context 4 mode = 1；
普通 descriptor 為 DMA `0x05026680`、length `0x40`、flags `0x813`，而
`FUN_c01e6b80(9)` 回傳 `0`。相機端 normal Bulk transfer 已成功 enqueue。

Host 仍未收到 payload 的主要嫌疑已轉為初始化競態：IOUSBHost 在 AutoRun 的
延遲 init/sender 前立即提交 read，先收到 `NotResponding`，pipe 隨後永久失效。
Receiver 現在會在 interface/pipe 出現後先等 20 秒，讓相機先 queue transfer，
再提交第一個同步 64-byte read。

拔電池 15–30 秒的完整 cold boot 與一般關機結果幾乎逐 byte 相同；差異只有
時間戳與新 allocator 位址，因此目前問題不是殘留 RAM patch。Context table
最終為 `{mode=1, direction=IN, endpoint_number=4, enabled=1}`，確認 context 4
確實映射到 EP84。StartTransfer 配發的 endpoint resource index 位於
`0xC31E3A54`，值為 `5`，不是未配置的 `0x80`。所以 controller command 不只
回傳 0，也成功取得 transfer resource；尚缺的是 host transaction 與這筆
resource/TRB 的完成事件。

下一輪新增兩項交叉診斷：

- `ep84_libusb_read`：使用 libusb 1.0.29 的 Darwin backend，不經 IOUSBHost
  Objective-C pipe API；interface 1 出現後等待 20 秒，再提交 EP84 Bulk IN。
  專案目錄附帶自編譯的 `libusb-1.0.dylib`，binary 使用 `@loader_path` rpath。
- Camera sender 在 `FUN_c01e6b80(9)` 返回的瞬間，把 return value、resource
  index、TRB DMA、length 與 control 分別保存至 `0xC072E060..0xC072E070`，
  避免只看三秒後的最終 dump 而漏掉瞬間狀態。

即時 snapshot 證實 StartTransfer return `0`、resource `5`、TRB DMA/length
正確，但 control `0x813` 的 HWO bit 在 libusb transaction 後仍為 1，controller
從未消耗 TRB。追查 `FUN_c01e62a8()` 發現 late-added context 只更新 firmware
shadow `0xC31E398C`；真正的 DWC3 `DALEPENA` 是 `0x2100C720`，未在這條晚期
初始化路徑同步。下一版 init 會在 context 4 config 後執行
`DALEPENA |= 0x200`（physical endpoint index 9 / EP84 IN），並新增
`DWCPRE.BIN`、`DWC9.BIN` 前後 register dump。

### 里程碑完成：EP84TEST 收到（2026-08-17）

加入 `DALEPENA |= 0x200` 後，libusb receiver 成功從 interface 1 / EP84
收到完整 64 bytes：

```text
45 50 38 34 54 45 53 54 00 01 02 03 04 05 06 07
08 09 0a 0b 0c 0d 0e 0f 10 11 12 13 14 15 16 17
18 19 1a 1b 1c 1d 1e 1f 20 21 22 23 24 25 26 27
28 29 2a 2b 2c 2d 2e 2f 30 31 32 33 34 35 36 37
```

前 8 bytes 為 ASCII `EP84TEST`，其餘 pattern 全部正確。已證實：

- PTP + vendor interface composite 可同時枚舉。
- Context 4 normal Bulk mode 1 可驅動 EP84。
- Allocator buffer 的 DMA alias 與 `0x813` TRB 正確。
- `FUN_c01e6b80(9)` StartTransfer 路徑可用。
- Late-added endpoint 必須同步 firmware shadow 到實體 DWC3 `DALEPENA`。
- Mac libusb Bulk IN 可正常接收 payload。

下一階段可由固定 packet 前進到 EP05 Bulk OUT + EP84 Bulk IN echo，之後接入
shell dispatcher，再考慮 RAW producer/ring。

## EP05 → EP84 echo 準備

下一版把 vendor interface 1 擴充為兩個 endpoints：EP05 Bulk OUT 與 EP84
Bulk IN。Configuration total length 更新為 FS/HS `0x3E`、SS `0x5C`，endpoint
descriptor arrays 與 SS companion arrays 分開配置。

Context 5 被設定為 `{mode=1, direction=OUT, endpoint=5, enabled=1}`，並與
context 4 一起初始化；DWC3 `DALEPENA` 同時開啟 bit 9 與 bit 10 (`0x600`)。
一次性 echo handler：

1. 對 context 5 / EP05 OUT 排入 64-byte `0x813` TRB。
2. 等待 `FUN_c01e4e80(5, 60000)` 完成。
3. 對同一 DMA buffer 排入 context 4 / EP84 IN TRB。
4. Host 比較回傳 64 bytes 是否與送出內容完全相同。

相關檔案：`ep05_ep84_builder_hook.S`、`ep05_ep84_echo.S`、
`ep05_ep84_echo_host.c` / `ep05_ep84_echo_host`。診斷區 `0xC072E080..E090`
依序記錄 OUT StartTransfer、OUT wait、OUT TRB length/control、IN StartTransfer。

第一輪 echo 結果：雙 endpoint interface 可被 libusb claim，context 5 最終為
`{mode=1, OUT, endpoint=5, enabled=1}`，`DALEPENA` 也由 `0xA7` 變成
`0x6A7`，確認 physical indices 9/10 都 enable。EP05 descriptor 為 DMA
buffer、length `0x40`、control `0x813`，但 `FUN_c01e6b80(10)` 立即回 `-1`；
OUT wait 與 EP84 echo 尚未執行。下一步需在 return 當下記錄 physical endpoint
10 的 DWC3 `DEPCMD` (`0x2100C8AC`) status/error bits，區分 endpoint config
failure、resource/state error或 StartTransfer parameter error。

## 建議下一步

### A. 先精確定位 sender 的 −1 來源

在 callback 中分段記錄：

1. 進入 callback 時的 `0xC31E3964`。
2. memcpy 後的 flags。
3. sender 前後的 ring index `0xC31E3A18`。
4. allocated buffer 前 16 bytes的副本或 checksum。

這能區分：

- buffer address gate；
- controller busy check；
- `FUN_c01e6b80()` start-transfer 失敗；
- active bit 在 callback 前已被清除。

### B. 直接呼叫 allocator API

已知候選：

- `FUN_c001cf78(type)`
- `FUN_c001cfd8(pool, out, size, align, flags)`

長期可讓 hook 第一次觸發時自行配置 buffer，將 pointer 存在 cave，避免依賴 Shell global `0xC3757A7C`。在確認參數與回傳規則前，Shell `memmgr` 路線較容易觀察。

### C. 先完成 Shell 通道，再做 RAW

預定介面：

- EP84 Bulk IN：Shell response / dump，之後承載 RAW。
- 新增 Bulk OUT（候選 EP05）：Mac 傳入命令。
- PTP endpoints 保持不變。

順序：固定 packet → Bulk OUT echo → shell dispatcher → RAM dump/read/write → frame buffer → ring/double-buffer RAW stream。

## 工作檔案

- AutoRun：`/Users/dido/Documents/Codex/2026-08-16/4/outputs/AutoRun_PTP_EP84_BuilderHook_Test.txt`
- Receiver source：`/Users/dido/Documents/Codex/2026-08-16/4/ep84_read.m`
- Receiver binary：`/Users/dido/Documents/Codex/2026-08-16/4/ep84_read`
- Callback assembly：`/Users/dido/Documents/Codex/2026-08-16/4/ep84_dma_callback.S`
- 舊 handler assembly：`/Users/dido/Documents/Codex/2026-08-16/4/ep84_sender.S`
- 工作筆記：`/Users/dido/Documents/Codex/2026-08-16/4/notes/PTP_RAW_BULK_IN_RESEARCH.md`
