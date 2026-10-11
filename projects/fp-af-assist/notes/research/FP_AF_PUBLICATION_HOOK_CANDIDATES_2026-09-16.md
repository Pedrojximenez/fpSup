# SIGMA fp 5.02：AF publication hook 候選的 bounded offline audit

日期：2026-09-16。正式歸檔目的地：`research/autofocus/notes/`。

本文件只保存已完成的離線審核，不是 hook 設計、實作或部署指示。沒有操作相機／USB、寫入相機 RAM、修改韌體或新增授權。以下連結按正式歸檔位置撰寫。

## 結論與證據界線

兩個最可信的候選是：

1. 背景 `AfContinuousObserver` 呼叫 H/L producer **返回之後**：適合觀察每次 CPU publication，不能據此宣稱每筆都是新 sensor exposure。
2. 原廠 `Near::v5` 完成 history／位置 commit **之後、v6 之前**：適合觀察原廠 H/L—位置配對，但位置是原廠補償估計，不是獨立量得的曝光瞬間真值。

「確證」指 fp 5.02 decomp 與指定位置的 ROM ARM 指令吻合；「候選」指語意適合觀察，**不表示該處可安全直接改寫**。沒有完成 DMA generation、跨 task 排他、cache coherence 或曝光 ID 的端到端證明。

ROM 核對來源：`out/seg0_c0000000.bin`，映射基址 `0xC0000000`；以下 ARM 字組是解碼後的 32-bit 值，不是檔案中 little-endian byte 顯示順序。

## 候選 A：背景 H/L producer 返回

入口：`AfContinuousObserver__v1 @ C022C7E8`。

| 地址 | ARM 字組 | 指令／意義 |
|---|---|---|
| `C022C7E8` | `E92D4030` | `PUSH {r4,r5,lr}`，observer 的 stack frame |
| `C022C84C` | `E3A02000` | `MOV r2,#0` |
| `C022C850` | `E1A00004` | `MOV r0,r4`，model |
| `C022C854` | `E1A01002` | `MOV r1,r2`，mode 0 |
| `C022C858` | `EB00485C` | `BL C023E9D0`，本 callsite 確定是 `(model,0,0)` |
| `C022C85C` | `E1A00004` | 返回 continuation；此時 producer 已完成 |
| `C022C860` | `E3A01000` | `MOV r1,#0` |
| `C022C864` | `EB003C19` | `BL C023B8D0`，後續 AF decision |

觀察邊界是 `C022C858` 的 native call 完成後、`C022C85C` 原 continuation 前。這是 call-boundary 候選，不是要求直接覆寫 `C022C85C`。

### 為何這裡比全域 producer entry 精確

`C023E9D0` 依序呼叫 `C027B678`、`C023E6F8`，再發布 51 區的處理後 CDAF bands：

| 資料 | 位址 |
|---|---|
| H per-area | `C32985E8 + 4*area` |
| L per-area | `C32986B4 + 4*area` |
| auxiliary arrays | `C3298780`、`C329884C` |
| aggregate fields | `C32915C4/C8/CC/D0`、`C32915A8` |
| mode-0 additional arrays | `C3297928`、`C32979F4` |

producer 還執行 `C023EC28` 的 model/correction 更新後才返回。其 `param3==1` 分支會跳過 per-area publication；所以只盯全域 `C023E9D0` entry，或把所有呼叫當成相同類型，都不成立。本背景 callsite 固定 `param3=0`，避開該歧義。

`C328E768` 只在 `C0275E10()` debug callback 非零時增加，不是無條件 publication counter。H/L 數值重複也不能判定沒有新 publication。

來源：[blk_c02.c](../../../../out/decomp/full/blk_c02.c)，`AfContinuousObserver__v1` 行 33522 起、`C023E9D0` 行 44325 起；精確 callsite 另由上述 ROM 核對。

### ABI 與可取欄位

- native call arguments 是 `r0=model,r1=0,r2=0`；`r4` 在 observer continuation 仍承載 model。
- native return 的完整語意不能由 decompiler 的 `void` 宣告推定；任何未來 wrapper 必須保留原呼叫效果、原 continuation 所需 live state、callee-saved registers 與既有 stack/interworking 約束。這份 audit 沒有認證一個可任意套用的 trampoline ABI。
- 可觀察選定 ROI 的 H/L、aggregate、area index、AF route/model context，並連同 gain/HCG/context 記錄以供離線排除條件變化。不能把這些零散讀值直接宣称為原子、同曝光資料。
- `C035FD48()` 所屬 lens getter 路線與 drive object 中的拷貝是 cached position 來源，不因在 producer 後讀取就變成曝光位置。`C32914E0` 是 AF 管理狀態使用的 position 欄位，也不能直接當成即時曝光位置。

## 候選 B：Near history 與補償位置 commit

入口：`AfMgrProcessNear__v5 @ C026AE50`。Near object 的 strategy vtable 為 `C091F134`，其 `+1C=C026AE50`。

### 精確 commit 與較清楚的呼叫邊界

| 地址 | ARM 字組 | 指令／意義 |
|---|---|---|
| `C026B0C0` | `E301E958` | `MOVW lr,#0x1958` |
| `C026B0C4` | `E1A03106` | `LSL r3,r6,#2`，`r6=k` |
| `C026B0C8` | `E34CE329` | `MOVT lr,#0xC329` |
| `C026B0CC` | `E78EC003` | `STR ip,[lr,r3]`，實際寫入 `mposm[k]` |
| `C026B0D0` | `E301C5BC` | 第一個 post-store continuation 指令 |
| `C025A660` | `E12FFF33` | 共用 dispatcher 的 `BLX r3`，strategy vtable+1C |
| `C025A664` | `E1A03000` | v5 return continuation，`MOV r3,r0` |
| `C025A698` | `E12FFF33` | 後續 strategy v6 call，vtable+20 |

`C026B0CC` 確定是位置 commit，但它是函式內部的 store 邊界，並非天然 ABI 邊界。若未來研究觀察點，較清楚的語意是共用 `C025A660` **確認目標為 Near v5** 後，等 native call 返回，在 `C025A664` continuation 前記錄。此時 v5 內後續操作也已完成，v6 尚未推進索引。

共用 callsite 不能無條件把其他 AF strategy 都解讀成 Near；若選擇它，未來必須保留原 virtual target、返回值與 interworking 行為。這不是本次已完成的設計。

已核對的 ABI 線索：

- 共用 dispatcher `C025A618` 使用 `r4=process,r6=model,r7=descriptor`；v5 返回值在 `r0`，緊接著複製到 `r3/r5`。
- 在 Near 的內部 store 邊界：`r6=k`、`r3=4*k`、`lr=C3291958`、`ip=剛算出的 native position`。`r4` 是 Near object、`r7` 是 model、`sb` 是 drive object。
- 不能將 call-boundary ABI 套用於中途 store：任何改動都還需完整 live-register/APSR/stack 分析，原 store 也不可遺失或重做。本文未認證這種中途 patch。

來源：[blk_c02.c](../../../../out/decomp/full/blk_c02.c)，`C025A618` 行 59268 起、Near ctor 行 66885 起、Near v5 行 67140 起；字組由 ROM 核對。

### 索引配對：必須保留 n、delay、k

Near v5 的語意：

- `n = *(Near+3C)`，當前 history 寫入索引。
- `delay = *(Near+08)`，signed 延遲欄位。
- 通常 `k=n-delay`；原程式在 `delay>=0 && n<delay` 時將 k clamp 為 0，負 delay 則走減法分支。
- v5 先把當前 H/L 寫入 **history[n]**，再把本次計算的位置寫到 **mposm[k]**。

| history | 基址／定址 |
|---|---|
| H | `C329B128 + 4*(area*1000+index)` |
| L | `C32CCE08 + 4*(area*1000+index)` |
| native mposm | `C3291958 + 4*index` |

因此要研究原廠既有配對，應明確讀 `Hhistory[area*1000+k]`、`Lhistory[area*1000+k]`、`mposm[k]`；**不能在 delay>0 時把當前 H[n]/L[n] 與 mposm[k] 配成同一筆**。可另外記錄 current n 的 H/L，但欄名必須區分。

採用資料仍需檢查 n、k、area、實際有效 history 範圍、startup clamp 與負 delay 情況，不能將 clamp 出來的 index 0 當成每次都有新完整配對。Near v6 `C026B268` 之後才寫 `C329153C=k+1`，再推進 `Near+3C`；`C329153C` 不是跨策略通用的「最後完成樣本」。

來源：[blk_c02.c](../../../../out/decomp/full/blk_c02.c)，行 67140–67329；既有分析：[FP_ORIGINAL_AF_TRIAL_2026-09-16.md](FP_ORIGINAL_AF_TRIAL_2026-09-16.md)。

### Near drive 分支：不能一概稱 Scan 三點內插

base ctor `C0259CA8→C025B8F8` 預設給 `Near+4=C3206AEC`；其 `+40=C091C4E0`，vtable+20 是 `C0238028`（`AfMgrDriveIntermittent::v6`），不是直接 `C0238B78`。

`C0238028` 按 `C0360038()` 分支：

- 返回 0：轉入 `C32069CC`／vtable `C091C50C` 的 slot+20=`C0238B78`（Scan v6），由位置歷史經 `C0238D18→C0239118` 等作曝光時序相關內插。
- 非 0：走 Intermittent 的 slot+24=`C0238138→C0238560`，按位置差與曝光時序作補償。

Scan 的三點歷史、曝光中心相關運算及 `exposure_timing_just_center` 字串是補償意圖的強證據，但不是獨立驗證的物理精度。Near 記錄應保留實際 drive object/vtable 與能判明分支的 context，把 mposm 標為 **native compensated position estimate**。

drive 的 cached position 更新可見 `C025B298` 從 `C035FD48()` 取得值後，寫進 Scan／Intermittent object。`C035FF88()` 也經 lens virtual getter 路線提供 model+20F8 使用的參數；它不是一個通用曝光 position getter。

來源：[blk_c02.c](../../../../out/decomp/full/blk_c02.c)，base ctor 行 59016、drive getter 行 60050、cached 更新行 59724 起、Intermittent v6 行 40071、補償行 40222、Scan v6 行 40431、Scan 時序／內插行 40642；[blk_c03.c](../../../../out/decomp/full/blk_c03.c)，`C035FD48` 行 63425、`C035FF88` 行 63743、`C0360160` 行 63946、`C03606A8` 行 64286。

## Task／interrupt context

### 背景 producer：CameraMgrScheduler task，不是直接 ISR

- thread wrapper `C0207AD0` 建立／啟動 thread；ROM vtable `C090EF54` 的 entry thunk `C02070D0` 呼叫 `C0207620`。
- `C0207620` 有 `C036D818(...,FFFFFFFF)` event wait，之後經 observer vtable+0C 呼叫背景 observer。
- scheduler phase 是循環狀態，不是無限遞增的 frame ID；dispatch 另受 mode、divisor、readout/subcycle 影響。

### Near：AfMgrSingle task，不是直接 ISR

- `safmgr C028B610` 建 event flags 與 thread，vtable `C09252C4` 的 thunk `C028EAA0→C028C620`。
- `C028C620` 等待 singleton `C33D51C0+08=C33D51C8` bit0，再由 `C0259D50→C025A618` 派發 Near 等 strategy。
- `AfSingleObserver C022C768→C028B7B0` 負責相關 AF wake；背景與 Near 是不同 task 路徑，不能由同一 USB worker 的序列化推出兩者互斥。

VD 來源的已查鏈：IRQ `0x79` 登記 `C0125478`；callback registration 經 `C01269F8/C0125400` 與 `C0321640`，scheduler callback `C02074B0→C02074C0` 發 event，再由 thread 執行 AF observer。這證明 VD 相關排程來源，不代表 AF task 執行時刻就是 VD／曝光時刻，也不證明沒有 event 合併或漏過 producer publication。

來源：[blk_c01.c](../../../../out/decomp/full/blk_c01.c)，IRQ setup/handler 行 21647 起、`C01269F8` 行 23424；[blk_c02.c](../../../../out/decomp/full/blk_c02.c)，scheduler 行 6731 起、AfSingleObserver 行 33484、safmgr 行 85785、wake 行 85873、AF thread 行 86372；[blk_c03.c](../../../../out/decomp/full/blk_c03.c)，`C0321498` 行 22691 起、callback registry 行 22717、dispatch 行 22772。

## 時間欄位不是曝光 ID

| 欄位／getter | 本次允許的解讀 | 不成立的解讀 |
|---|---|---|
| `C002B6E0` | CPU 記錄時的微秒時間；getter 經 `C002B4E0/C002B440(...,1000000)` | 此 H/L 所屬曝光的 frame ID／曝光 timestamp |
| scheduler phase `C31F8CB4` | 循環的 scheduler phase | 單調 VD sequence |
| `C0125870()` | raw subcycle 值 | 通用 frame ID |
| `C32915C0` | `C028B7B0` 喚醒時有條件增加的 AF wake/debug index | 無條件 VD counter |
| `C328E768` | 受 debug callback 條件控制的 producer counter | 一直有效的 publication generation |
| `C02083B0()` | 實際經 `C021F790→C0216658` 讀 AE singleton `C32027DC+0C` | 本次尚未證實為 VD_tick，不能沿用舊筆記標籤當曝光 ID |

若未來增加本地 hook sequence，它最多先證明「完成了一次該 hook」，不能單憑序號升級成「取得了一次新 DMA／新曝光」。兩候選都還缺少到 AF-statistics DMA producer 與曝光 generation 的完整對照。

來源：[blk_c00.c](../../../../out/decomp/full/blk_c00.c)，`C002B6E0` 行 36203；[blk_c02.c](../../../../out/decomp/full/blk_c02.c)，`C02083B0` 行 7412、AE singleton 行 17743、`C021F790` 行 24088、AF wake 行 85873。背景 freshness 限制見 [FP_AF_STATS_FRESHNESS_2026-09-16.md](FP_AF_STATS_FRESHNESS_2026-09-16.md)。

## 尚未獲得的部署前提

本文件沒有提出或執行部署。原先只涉及 echo 插槽與指定 scratch 範圍的小範圍驗證授權，不自動涵蓋新的 AF callsite、strategy vtable 或 interrupt 路徑。

- **新 hook 地址的明確 scope／授權**：上表是候選，不是可寫白名單。
- **buffer ownership**：必須另行證明記錄區、code、scratch、既有 snapshot 與 USB/DMA 工作區互不衝突；不能因當前看似空白就佔用。
- **AF task quiescence**：啟用、拆除、還原前須有 AF task 不在 hook/trampoline/record writer 裡的證據。必要的生命週期與排他機制尚未設計。
- **USB same-worker barrier 不是 AF task barrier**：新的合法同 worker 回覆，只能證明該 USB worker 的前一個 shell call 已返回；不能證明 scheduler／AfMgrSingle task 已退出 hook、沒有持有舊 code address，或不會再寫記錄區。
- **尚缺的安全審核**：完整 ABI/live state、stack、code publication/cache、record coherence、bounded execution cost、重入／多 producer、可靠卸載與原 owner 還原。task context 不等於可以在 hook 裡阻塞、列印、分配記憶體或執行 USB。

因此目前只建議把候選 A 作為「CPU H/L publication 完成點」的下一步研究標的，把候選 B 作為「原廠延遲補償配對」的離線對照。這不是新設計或硬體測試的批准。
