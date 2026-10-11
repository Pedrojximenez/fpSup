# fp 5.02 native observation hook：離線接點與 ABI 契約

2026-09-27。核對本機 ROM、反編譯與現有 recorder；沒有相機 I/O、daemon、載入器／卡片／transport 修改。本文件及 [native_hook_sites.json](../../../../fpSup/focus/geometry/native_hook_sites.json) 是 **record-only 接點設計**。同日後续已完成 [native_observer.S](../../../../fpSup/focus/geometry/native_observer.S) 的純 ARM 有界記錄候選與模擬器位址建置，沒有 installer，`deployment_ready=false`。實作與驗證狀態以 [OFFLINE_INTEGRATION](OFFLINE_INTEGRATION.md)／[VALIDATION](VALIDATION.md)為準；不能把 native unknown 欄位轉成有效旗標。

## 結論與固定來源

四個主要接點都是 ARM `BL`，可以替換單一 callsite 的目的地，保持原函式恰好執行一次。**AF payload 必須在原 callback 前記錄，其餘三點在原 callee 返回後記錄。** 原函式執行時必須保留精確原 SP。完整保存 register/APSR、建立 recorder 自己的對齊 frame、呼叫 bounded C recorder、再完全還原，是本輪待編譯／模擬的候選；下表另列不呼叫 C 的 post-only leaf 可行子集，不能混為同一份實作保證。

**目前實作選擇：**保存 64-byte frame 後呼叫同一組語檔的 stackless recorder，不呼叫 C；因此不新增 public ABI 的 stack alignment 前提。下文 C-recorder 及 no-SP leaf 是設計比較，不能當作實際採用形狀。AF pre recorder 完成後直接 tail-forward 原 callee，保留原 LR；其餘三點採 before/after trampoline，完整保留返回資料與 APSR，再跳固定 continuation。四來源各用獨立有限陣列與單次 exclusive lock，timer 讀取關閉。

- ROM `out/seg0_c0000000.bin`，base `0xC0000000`，49,245,696 bytes，SHA-256 `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`。JSON 包含每點原 little-endian bytes、32-bit word、context bytes、原函式 entry／return 地址及精確來源行號。
- 已完整閱讀 [fp-usb-shell skill](/Users/dido/.codex/skills/fp-usb-shell/SKILL.md) 及其 [upstream reference](/Users/dido/.codex/skills/fp-usb-shell/references/upstream-fp-usb-shell.md)，並以維護版更正取代歷史「空閒 cave」「只清 D-cache」等說法。
- 現有 [af_publication.S:9](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/highrate/af_publication.S:9) 提供 no-SP、原 producer 一次、有限 append、DMB 後 commit 的設計先例；它只適用 `C022C858`，**不能直接把地址換成下表便使用**。該 recorder 的 H/L schema、128-byte record、r0/r1 scratch 與單 scheduler writer 都不是新接點的共同契約。

| 來源邊界 | 原 callsite → callee → continuation | 原字組／LE bytes | after-native leaf scratch |
|---|---|---|---|
| 指定 AF 結果轉發前 | `C028E310 → C022B720 → C028E314` | `EBFE7502`／`0275feeb` | pre phase 全保存；post-only 替代才可 `r0, lr` |
| native-L final 分支設 event 返回 | `C0340458 → C036D758 → C034045C` | `EB00B4BE`／`beb400eb` | `r1, lr`；保留並記錄 `r0` |
| face parser 的條件 publication 返回 | `C05AB348 → C05A9900 → C05AB34C` | `EBFFF96C`／`6cf9ffeb` | `r0, lr` |
| AAT ColorTracking::v2 的 Run 返回 | `C05AB8C8 → C05B6CF8 → C05AB8CC` | `EB002D0A`／`0a2d00eb` | `r1, lr`；必須保留 `r0` |

`lr` 可以在 after-native 當 scratch，是因為這四個固定 continuation 在使用 LR 前會再 BL 或從自己的已保存 frame POP PC；**不是 AAPCS 一般性允許丟掉 LR**。返回必須用固定 continuation 的 `LDR pc`／已驗 branch，不能 `BX lr`。

## 1. 共同 wrapper 契約

入口保持所有原始參數、SP、callee-saved 暫存器與 flags；pre recorder 若執行，須先完整還原，再用 `ADR lr, after_native; LDR pc, original_target_literal` 或等價 literal 載入把原函式交還執行，不能借用 r12 破壞入參。四個 callee 本體的 entry LR 都只保存後正常返回，未見把它當 caller ID／資料指標；間接 observer、除錯 unwinder 對返回地址的特殊依賴仍未全域審核。

完整保存 C-recorder 候選的必要約束：保存 r0–r12、LR、APSR（NZCV、Q、GE），保留 exact saved-SP；在新增 public ABI 呼叫前把 recorder stack 對齊至 8 bytes，返回後先回到 saved frame 再還原，原 native callee 得到原 SP。`push` 偶數個 register 本身不建立 alignment。C binary 必須確認不使用 VFP/SIMD、不改 FPSCR，否則另保存該現場。這增加 stack 需求，仍缺 recorder 最大 stack／native task high-water 驗證；離線模擬成功不能取代。

post recorder 應先保存原 r0（特別是 AAT return 與 event-set 結果），不能讓 recorder 回傳值流入 continuation。恢復時可把 LR 設為 callsite+4 再固定跳 continuation，因為本四點已證不使用 current LR 而先 BL／POP-PC；這不是宣稱與原函式返回後 LR 的 bit pattern 完全相同。所有其他寄存器／APSR 應保持。

若另外選 no-SP post-only leaf，原 callee 返回後才可使用上表兩個 scratch，其他 `r0..r12`、SP、VFP/FPSCR、APSR Q/GE 必須原樣保持；r4/r6 等來源寄存器只讀。普通 CMP/TST 可改 NZCV，因為四點的 continuation 在依賴條件前會重新比較（下節有確切位置）。此子集不使用 DSP/SIMD、push/pop、BL/BLX；**不適用所需的 AF pre-forward phase**。所有形狀都禁止動態配置、列印、mutex、wait 或 USB；複製長度固定或編譯期上限固定，不採無界重試。

此形狀保留原 native SP 的 alignment phase；不假定 firmware private ABI 一定為 8-byte aligned。核對的 caller frame delta：

| 接點 | 相對直接 enclosing function entry SP | 原 callee 自身 frame（不含子呼叫） |
|---|---:|---:|
| AF result | `−0x88C`：C028D968 PUSH 0x20，SUB 0x86C | C022B720 PUSH `0x14` |
| native-L final | `−0x34`：C0340210 PUSH 0x0C，SUB 0x28 | C036D758 PUSH `0x0C` |
| face publication | `−0x158`：C05AAFF8 PUSH 0x20，SUB 0x138 | C05A9900 frame `0x480` |
| AAT Run | `−0x08`：C05AB8A0 PUSH r4,lr | C05B6CF8 frame `0xA8` |

表中都是原碼 delta；不包含 C recorder 額外保存 frame／call stack。no-SP leaf 不建立額外 stack 需求，但不能拿來認證完整保存 C-recorder 候選。現有 [confirm_join.h:6](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/focus/geometry/confirm_join.h:6) 是序列化 consumer 契約，不能在四個 producer hook 中直接共同呼叫同一狀態。

## 2. AF result：C028E310

原參數為 `r0=C32044D8`（C022AD58 getter 返回）、`r1=SP+0x6F4`、`r2=0`。payload 為 `0xAC` bytes，這個 SP 是 C028D968 的既有 local frame，**必須複製內容，不能只把 stack pointer 延後交給 consumer**。原 `C028E298 BL C028E7F8` 在此之前發出最終定位，沒有一般性的等待完成保證。[terminal 路徑](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:87198)

`C022B720` 若找到 observer，會先把 AF model+0x2254 寫到 payload+0xA8，再呼叫 observer vtable+0x0C。callback 是否改寫 payload 尚未完整審核，所以首選事件 `af_terminal_pre_forward` 在 native call 前複製 payload。此時 +0xA8 尚未由轉發器填入，不能把該 raw word 命名為 observer 提供的識別。原 callee 仍照常執行，沒有 observer 也不能由 pre event 宣稱 callback 已送達。[轉發器](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32813)

可有界保存：完整 payload、`C329160B` error byte、`C32914E0` AF target raw、`C33D51FC` 原生診斷 counter、r4/r5/r7 原 caller context pointer、本 hook 的 source_seq。error／counter／target 都標記為 pre-forward CPU read；不據此填 episode、drive 或 exposure generation。pre recorder 之後須完全還原 r0/r1/r2、其他寄存器、APSR、SP，再執行原 callee，不能讓 recorder 傳參破壞原 payload pointer。

Continuation：`C028E314/C028E318` 立即重建 r0；`C028E31C BL C0013090` 重寫 LR。callee 在 `C00130B0 CMP r0,#0` 前沒有 NZCV 條件依賴。故 **post-only 替代** 的最窄 scratch 為 r0/lr；不能以此倒推 pre-forward 也能丟掉這兩者。r4/r5/r7 不是可自由使用的 scratch。

**不形成 acceptance：** terminal 可含取消 cleanup，success byte 與 error 也不能證明 motor end、同一 subject、有效光學 anchor。沒有 episode-begin／cancel／drive-begin 觀測時，僅輸出 raw event。[confirmation gate](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/geometry/NATIVE_CONFIRMATION_AUDIT.md:111)

## 3. Native-L final end：C0340458

限定 `r4=F=C3476414`、`[F]=C0B8EEEC`、native-L selector `C3476408==1` 的已支持 layout。原參數 `r0=r4+0x44`、`r1=1`。此前 `C034044C BL C0340668` 已呼叫原 callback；本點是 message 3 的 **final 分支**，backlash 中途分支走 `C0340400` 後跳走，不經此點。[分支來源](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:42179)

`C036D758` 返回 `r0=1` 才代表 `tk_set_flg` 成功，0 是失敗；應記 `event_set_return_raw`，不能只因 hook 觸發就設 done。[event-set wrapper](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:74825)

after-native 可用 r1/lr，保留 r0：`C034045C` 立刻重寫 r1，`C0340460 CMP` 重新定義 NZCV；兩條後續路徑都在讀 LR 前再 BL（`C0340474` 或迴圈 `C034023C`）。record 保存 r0、F+4 cached position、F+0x14 mode、F+0x28 abort byte（此處通常已被清除）、F+0x30 backlash state、F+0x58 sync pointer raw。沒有已驗 mapping／範圍 guard 時不追讀 sync pointer。

**兩個不可補成 true 的缺口：** 此時 F+0x28 清零不能倒推之前沒有 abort；設 event 可能喚醒另一 task，after-native leaf 執行前已有排程／新 drive 的可能。故後讀位置不是與 set-event 原子綁定，亦沒有 packet receive time。必須另外捕捉 drive begin／abort／generation 並完成排序與位置來源驗證，才有 native end 的配對資格。這個 hook 絕不自行設 `POSITION_VALID` 或 `SETTLE_VALIDATED`。

## 4. Face parser publication：C05AB348

`C05AAFF8` 完成最多五個 `0x9C` parsed groups、valid／id 等欄位後，只有 `M+4==0` 才呼叫 `C05A9900`；此時 `r4=M`，原 `r0=r4`。[parser](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:131618)、[publication gate](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:131651)

after-native 在 parser 外層 lock guard 的 release `C05AB354` 之前，可從白名單 `M=C37CCA9C` 複製指定 slot（首版 group0，M+0x10，固定 `0x9C` bytes）及 M+4、M+0x0C、M+0x0D flags。source_kind 是 `parsed_face_group`，不是 status 中的 face 已被 AF 採用；slot 也不是 persistent identity。若未證明所有其他 writer 都服從同一 lock，不能把此 CPU copy 宣稱全系統原子快照。

`C05A9900` 本身受 cfg+0x0C/+0x0F 分支影響：可能只推進既有 status，或把 validity 清掉。因此 event 名稱為 `face_parser_publication_return`；沒有新的 frame／exposure 保證，也不把每次 publication 直接變成 target/scale generation。[publication 分支](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:130628)

Continuation `C05AB34C ADD r0,sp,#0xC`、`C05AB350 MOV r1,#2`、`C05AB354 BL C00102D0`；callee 在 `C00102DC CMP r4,#0` 前無條件依賴。最窄使用 r0/lr，r4 與原 stack 保留。由於條件不成立時 parser 不呼叫本點，**source_seq 只計本 publication call 返回，不計所有 parser 執行／偵測幀**。

## 5. AAT model：C05AB8C8

選擇 `AatInterfaceColorTracking::v2` 內 Run 呼叫，限定 color backend。`C05B6CF8` 不讀 incoming 參數；先檢查 `C37CDFD4` 是否 1／2，無效時直接回 −1，沒有更新模型。正常路徑先複製 `C37CDFA8` 的 `0x2C` model 到 local，再串行處理、copy back、可選 `C05B8620` 修正、GetResult cache 等步驟，最後回 0；處理失敗也可能已 copy back 模型後才回 −1。[演算與模型寫回](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:139307)、[後置修正與失敗](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:139381)

因此回傳事件 `aat_color_run_return` 應保存 signed r0、model 全 `0x2C` bytes、`C37CDFD4/D5` state bytes 與 `C2F2D860` cache-dirty raw；**return 0 是此 Run 成功返回，不是 validated object scale；return −1 的 model 既可能未更新，也可能是失敗後中間模型。** v2 呼叫前的 state（若未獨立捕捉）維持 unknown。

`C05AB8CC CMP r0,#0` 直接使用 return value，故 r0 不可 scratch；r1 於兩條條件 MOV 完整覆寫，LR 最後由 `C05AB8DC POP {r4,pc}` 的 caller frame 返回，不讀当前 LR。r1/lr 可供 no-SP leaf，NZCV 由 `C05AB8CC` 重設。其餘全部保留。

這裡不涵蓋另一個 `C05B6C60 BL C05B6CF8` 的 reseed／初始化呼叫；不安裝全域 entry hook 假装兩者同源。也不把 `C05B7080 STM r2,{r0,r1}` 當最終完成：後面 `C05B709C BL C05B8620` 還可改 model。`C05B70B0 BL C05B7440` 只是 cache-dirty marker（callee 設 C2F2D860=1），不是完整 Run 成功。

## 6. Direct BL、range veneer、instruction relocation 分清楚

四個推薦点只替換原有 **一個 BL word**；原 callee 用絕對 ARM target 呼叫，無需搬移／重定位原 prologue 或 continuation 指令。`BL` 必須保留 link，不能換成 B 後期待通用 return。

目標在 `(site+8)` 的有符號 26-bit byte displacement 範圍、4-byte aligned 時，可直接 BL 到 wrapper。範圍為 `−0x02000000 <= target−site−8 < 0x02000000`。若 payload 位於 `0x4...` pool，原 callsite 不能直達：需另外有已證 ownership 的近端 8-byte veneer，`E51FF004`（LE `04f01fe5`，`LDR pc,[pc,#−4]`）後接 ARM 絕對 target。veneer 不改 LR／其他 register，且自己也要完成 cache publication 與生命週期驗證。[現有 range／veneer 實作](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/highrate/build_publication.py:46)

沒有選擇任何 veneer/cave/buffer 地址；shared scratch、loader pool 與歷史空洞均不視為可用區域。JSON 的 replacement／veneer address 維持 null，不能被當部署 manifest。

不採用的中間接點：

- `C034045C LDR r1,[r4,#0x14]` 是普通指令，若覆寫必須另做 displaced-instruction relocation／return 契約；原 BL wrapper 已能取得較準確的 event-set result。
- `C05AB358 ADD sp,sp,#0x138` 是 epilogue，不能套 BL wrapper；改寫須重建原 stack unwind。選擇較早的 publication BL 可避開。
- `C05B7080 STM r2,{r0,r1}` 為尚會後置修正的 copy-back，既非 final 又需處理 displaced store。
- `C05AC878 BL C05A9900` 可作 AAT status publication 的額外候選，但 `M+340` 可能沿用舊資料；本輪未審完其返回 caller 對 flags/live-state 的契約，列為 supplemental，不加入四點可用 scratch 白名單。[條件 copy](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:132738)

## 7. Record-only adapter 與上機前的有界完成條件

可沿用 highrate 的「有限、不覆寫、完整 body 後 DMB、commit marker 最後發布」設計，**每一 producer 先用獨立 append buffer／source_seq**。此四點不是同一 writer；禁止共用一個未同步遞增 write index。reader 不清除／重用正在被 hook 寫的記憶體；滿載走原 continuation，不阻塞、不重試、不再呼叫原 producer。DMB 是 CPU ordering，不是 DMA cache clean。

建議 observation envelope 至少含格式版本、capture nonce、site_id、source_seq、raw source bytes、capture phase、call return raw（適用時）、source pointer／layout 身分、commit/inverse marker、loss／overflow狀態。未建立 timestamp source 前 `event_ms=null`；每來源序號不等於跨 task stream_seq、exposure_seq 或 episode/drive/target/context/scale generation。raw byte decoder 可消費內容；confirmation join 必須拒絕缺少原生證據的欄位。

本輪已完成：ROM身份和原call word／鄰近instructions核對、callee正常return與LR用法、原stackdelta、四點 post leaf scratch/NZCV界線、AF pre 必須保留的參數、copyback與publication的語意限制。尚需完成以下離線可檢查項目，才到「可安排上機驗證」：

1. 為四點實作各自 bounded wrapper／recorder binary（AF pre、其他 post）；以實際組譯 bytes 做 instruction-level 測試：原函式恰一次、phase順序、每條 disabled/full/mismatch 路徑、registers/SP/APSR保持、r0 AAT return 保持、固定 continuation 正確，以及最大複製範圍。C 方案另驗 VFP/SIMD 禁用、動態 stack alignment、保存 frame 與 stack budget；模擬不能證明 native task 剩餘 stack。
2. 做獨立 producer buffer 的 ownership／commit／overflow／consumer loss 契約；明確新增觀測所需 memory 由誰配置及何時釋放，不能沿用舊 AF guarded loader 的 pool 假設。此文件不修改載入鏈。
3. 审核安裝／卸載的 task quiescence、expected-word 比對、先寫驗證 payload/veneer 再發布 caches 再arm、原始word還原及readback；需保留正在執行的code至所有producer確實退出。USB same-worker barrier 不是 AF／Lens task barrier。
4. 若目標超出 record-only，另補 begin/drive/abort/context 來源與共同時間排序，解析 callback 是否改 payload、motor位置來源時刻；不能用四點近似時間配對補出缺少事件。

真正需實機的剩餘 gate：四點在白名單 mode/鏡頭下可達性與所有writer、重入／task preemption、最壞執行時間、snapshot coherence、掛接／卸載與cache、跨來源實際事件順序與遺失率。光學清晰度／settle／scale校準屬後續独立驗收；raw recorder 可上機測量不代表 `fg_confirm` 或鏡頭控制已可啟用。

## 8. TICK_US 的原始 timer 來源與 bounded-read 界線

`C002B6E0` 並非直接讀單一 32-bit free-running 微秒 register。它呼叫 `C002B4E0` 建立 `(raw_count, software_epoch)`，再呼叫 `C002B440(epoch,raw,1000000)` 轉換。[getter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:36203)

| 來源 | 原廠讀法／來源 | 靜態已知 |
|---|---|---|
| timer5 raw counter | `C00165E8` 讀 `[*C30337F0 + 5*0x10 + 4]` | 32-bit LDR；初始化 base `2D810000`，所以實際位址 `2D810054` |
| timer pending | `C00164C0` 讀 `[*C30337FC+4]` 的 bit5 | 初始化 base `2D810080`，所以實際位址 `2D810084`、mask `0x20` |
| software epoch | `C30781A4` | `C002B820` 每次 timer callback 加一，32-bit word |
| period／換算值 | `C2EFABC8`／`C2EFABCC`／`C2EFABD0` | Tick init 取 `12000000`，保存 period、period/1000、period/10000 |

MMIO 地址來自 ROM `C0011568` 的 MOVW/MOVT 寫 pointer，不是猜 uncached alias。[映射](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:13671)、[counter getter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:20040)、[pending getter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:19974)

`C0016190` 報告 `12000000` 及最大 period `0xFFFFFF`，設定器也拒絕 period 超過 `0xFFFFFF`，並將 period 放在控制字 bits31:8。因此已證的是 **24-bit period 設定範圍、32-bit counter 讀取寬度**；沒有硬體手冊證據便不擴寫成所有 timer mode 的 counter width。[能力／period 設定](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:19831)、[Tick 初始化](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:36149)

原廠把一個 software epoch 換成 1,000,000 微秒；當 period=12,000,000 時，公式等價於 `epoch*1000000 + floor(raw/12)`，結果在 ARM 32-bit 算术回傳，微秒值每 `2^32 µs = 4294.967296 s` 回繞。raw 則按 timer period 回繞，不能將 raw 的自然差直接當微秒；實際初始化、running period 與跨電源 continuity 仍需驗證。[轉換公式](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:36095)

`C002B4E0` 的原順序為 raw_before → epoch → pending → raw_after；pending 為真時使用 epoch+1，否則檢查 raw wrap 及 epoch 是否變動。`C002B564`、`C002B588`、`C002B5A0` 都會遞迴呼叫自己，未設次數上限。底層 getters 還呼叫 `C000EC14/C000EC24` 暫時屏蔽／恢復 IRQ/FIQ。[重讀邏輯](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:36113) 這不是 wait，但不是本 recorder 可認證的有界成本；不因現有 snapshot 曾呼叫便在新 hook 無條件加入。

**可離線設計的最窄 inline 候選：** 在獨立預檢確認 `*C30337F0==2D810000`、`*C30337FC==2D810080`、Tick 已初始化且 period/config 符合白名單後，只作固定次數 volatile LDR，保存 raw_before/after、epoch_before/after、pending_before/after 與 period raw；不寫 timer、不清 pending、不改 IRQ/FIQ、不呼叫 getter、不重試。這是診斷 tuple，若跨 wrap／epoch 競爭便由 consumer 拒絕或保留未知，而非無界讀到一致為止。

尚未認證直接 MMIO 讀取在四個新 task/hook 的 timing、ordering／副作用與 rollover tuple 接受規則；原 getter 保護序列也不能被刪掉後假定等價。首版完全不讀 MMIO、`event_ms=null` 亦是有效 record-only 方案。**單讀 `2D810054` 不能標 `tick_us`、不能填 `TIME_VALID`，更不能當曝光時間。** timer 資料不足不妨礙保存 AF／face／AAT raw record；確認配對繼續保持未授權。
