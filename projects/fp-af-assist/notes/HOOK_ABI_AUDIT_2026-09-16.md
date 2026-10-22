# C022C858 背景 H/L publication hook：ABI 與 stack 離線審核

2026-09-16。範圍限 fp 5.02 的 `C022C858 → C023E9D0 → C022C85C`，不重做掛點比較。
只有 ROM、decomp 與現有 assembler/template 的唯讀檢查；沒有 USB、payload 實作、部署工具或相機寫入。

## 結論

**固定單 callsite、完全不改 SP 的 wrapper 形狀，在已查原碼上有較強的 ABI 可行性。**
在入口不 push、不動 `r4..r11`，以不改 flags 的方式令 LR 指向 wrapper 的 after-native continuation，
再轉入原 `C023E9D0`。等原函式正常返回，只使用已證明於原 continuation 被覆寫的 `r0/r1`
作 bounded leaf 記錄，最後轉到固定 `C022C85C`。這裡是可行性判斷，**不是實作、binary 或部署批准**。

不能直接套用「push 偶數個暫存器便一定 8-byte aligned」的範本註解：
本 observer 本來就 push 三個暫存器。已證明掛點 SP 與 OS thread-entry SP 相差 `0x9C`，
因此兩者的 `SP mod 8` 相差 4。OS entry 的實際 SP 值／完整 restore-to-entry alignment
本次沒有完成端到端證明，也沒有 live 量測。若 OS entry 是 0 mod 8，原 producer entry 就是 4 mod 8。
不得把 AAPCS 的一般預設，或相機目前能運作，當成此掛點對齊的實測證據。

上述 no-SP 形狀保留原 producer 的**精確 SP 與局部布局**，不需要先猜其 alignment phase。
它仍不解決 buffer ownership、publication ordering、重入、最壞執行時間、cache 或 AF task quiescence。

## 來源與重現識別

- ROM：`out/seg0_c0000000.bin`，映射 `C0000000`；SHA-256
  `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`。
- decomp：[blk_c02.c](../../../out/decomp/full/blk_c02.c)、[blk_c03.c](../../../out/decomp/full/blk_c03.c)、
  [blk_c00.c](../../../out/decomp/full/blk_c00.c)。ABI 與字組以 ROM disassembly 為準，不從 `void` 宣告推定。
- [armasm.py](../../../fpSup/fp_usb_shell/armasm.py)，SHA-256
  `fb3206b1492f0729e88571c1990969acaa78db45401bd4d06e3d95ece4bb7cb6`。
- 背景：[掛點候選](research/FP_AF_PUBLICATION_HOOK_CANDIDATES_2026-09-16.md)、
  [本專案 hook plan](HOOK_SAMPLING_PLAN_2026-09-16.md)。

下表 ARM 字組是 32-bit instruction value，不是 ROM 的 little-endian byte 字串。

## 1. Scheduler 至 observer 的實際 stack delta

此路徑是 native `XC_Thread`，不是依模板新建的 ThreadPool worker。
`C0207AD0` 以 descriptor index `0xD` 呼叫 `C036DD40`，再 `C036DDF8→C036EE08` 啟動。
`C036ECA8` 用 `C036EE50` 作 OS task entry。ROM descriptor `C0B98130`
（`C0B97F90 + 0xD*0x20`）含 task name `CamSch`、priority `0xF`、stack size `0x4000`。
**0xD 是 descriptor index，不是直接 priority。**

令 **K = OS 開始執行 `C036EE50` 時的 SP**：

| 位置 | 已核對指令 | 該處／後續 SP |
|---|---|---|
| `C036EE50` | `E92D4070 PUSH {r4,r5,r6,lr}` | `K−0x10` |
| `C036EE7C` | `E12FFF31 BLX r1`，body vtable+0C | 不再改 SP |
| `C02070D0` | `E92D4010 PUSH {r4,lr}` | `K−0x18` |
| `C02070E0` | `EB00014E BL C0207620` | scheduler entry `K−0x18` |
| `C0207620` | `E92D4BF0 PUSH {r4,r5,r6,r7,r8,r9,r11,lr}` | 再扣 `0x20` |
| `C0207624` | `E24DD058 SUB sp,sp,#0x58` | scheduler loop `K−0x90` |
| `C02079D0` | `E12FFF31 BLX r1`，observer vtable+0C | observer entry `K−0x90` |
| `C022C7E8` | `E92D4030 PUSH {r4,r5,lr}` | `K−0x9C` |
| `C022C858` | `EB00485C BL C023E9D0` | producer entry `K−0x9C` |
| `C023E9D0` | `E92D44F0 PUSH {r4,r5,r6,r7,r10,lr}` | 再扣 `0x18` |
| `C023E9D4/D8` | `MOVW r3,#0x518; SUB sp,sp,r3` | producer local frame `K−0x5CC` |

已檢查 `C0207620..C0207A94`：observer dispatch 前沒有另一個改變 SP 的局部分支，
迴圈使用固定 frame；函式出口以 `ADD sp,#0x58` 與對應 POP 還原。
producer 自己的 frame 共 `0x530` bytes；**`K−0x5CC` 不包括任何被呼叫子函式的 stack，不能當作最高用量**。

stack 初始化的有限補充證據：

- `C036ECA8` 建立 task attribute `0x41`、stack size `0x4000`，經 `C0016A58`（service `80010100`）。
- ROM syscall table 對應：`[C0001568]=C0021040`，signed service index `−32767` 指向
  table entry `C0001044`，內容 `C000A9C0`。
- `C000A9C0` 將 size round 到 8 的倍數；本 attribute 走 allocator `C0004D90`，並保存 top=`base+size`。
- `C000A4C8` 建初始 context：保存 `top−0xD0`，entry PC 放在 `top−4`，status 放在 `top−0xC`。

這些證明 stack size 與初始 context 的布局，**尚未完整證明 allocator 回傳 base 的 alignment，
以及 dispatcher 還原後 K 的最終值**。故本文只將 delta 視為確證；0/4 mod 8 的絕對選擇保留未知。
即使日後證明 K=0 mod 8，也不應擅自「修正」原 native private call 的 4-mod-8 布局。

來源：blk_c02 行 6731、6909 起；blk_c03 行 75170、75206、75956、75995、76012 起；
blk_c00 行 3338、7843、8181 起；上述精確地址另由 ROM 核對。

## 2. 原 producer 的輸入、返回與 LR

呼叫前：

| 地址 | 字組 | 指令 |
|---|---|---|
| `C022C84C` | `E3A02000` | `MOV r2,#0` |
| `C022C850` | `E1A00004` | `MOV r0,r4` |
| `C022C854` | `E1A01002` | `MOV r1,r2` |
| `C022C858` | `EB00485C` | `BL C023E9D0` |

本 native call 的已證輸入為 `r0=model,r1=0,r2=0`。
producer 立即把這三者保存為 `r4/r5/r6`，`r3` 先被 `MOVW #0x518` 覆寫。
函式沒有從 caller stack 取第四／更多輸入；它自己的 stack argument slots 是給後續子呼叫使用。

LR 審核：整段 `C023E9D0..C023EC20` 對 entry LR 的用途是 prologue 保存、正常 epilogue 載入 PC。
中間 BL/BLX 使用 LR 作各自的呼叫返回位址；沒有把 entry LR 讀作 caller identity、資料索引或調整 stack 的輸入。
所以將 entry LR 改成 after-native 的 ARM continuation，與此函式本體的正常返回機制相容。
這不等於已審核所有 debug callback／異常 unwinder 的可觀察行為。

正常出口：

| 地址 | 字組 | 指令 |
|---|---|---|
| `C023EC18` | `E3000518` | `MOVW r0,#0x518` |
| `C023EC1C` | `E08DD000` | `ADD sp,sp,r0` |
| `C023EC20` | `E8BD84F0` | `POP {r4,r5,r6,r7,r10,pc}` |

因此 **r0 的正常返回值確定是 `0x518`**，不是憑 decompiler `void` 假定任意。
`r1/r2/r3/r12` 與 flags 隨實際 producer/debug 分支及子呼叫改變；本函式没有定義穩定的額外回傳 tuple。
`r4/r5/r6/r7/r10` 明確恢復；本體不改 `r8/r9/r11`，仍依賴其子呼叫遵守 native convention。
wrapper 不應擴展為可破壞 `r4..r11` 的自由空間。

來源：blk_c02 行 33522、44325 起；ROM 全段入口至正常出口已檢查。

## 3. C022C85C 以後的 live-register／flags

| 狀態 | 已核對的下一次處理 | 有限結論 |
|---|---|---|
| `r0` | `C022C85C E1A00004 MOV r0,r4` | producer r0 在 continuation 被覆寫，不被使用 |
| `r1` | `C022C860 E3A01000 MOV r1,#0` | producer r1 在 continuation 被覆寫，不被使用 |
| `lr` | `C022C864 EB003C19 BL C023B8D0` | normal continuation 不先讀 producer 留下的 LR |
| `r4` | `C022C85C` 立即讀作 model，之後再用 | 必須保留 |
| `r2` | `C023B8E0 LDR r2,[r5,#0x30]` | 下一個直接 callee 在讀 incoming r2 前覆寫它 |
| `r3/r12` | 在已查 `C023B8D0..C023B920` 沒有直接讀 incoming 值 | 不足以泛化為所有下游／特殊 native convention 都不依賴；最窄 stub 不動它們 |
| `NZCV` | `C023B8E4 CMP r2,#0`，此前沒有條件依賴 | 原 producer NZCV 對已查 continuation 的直接控制流是 dead |
| APSR 其他 bits | CMP 不等於清除 Q／GE 等 | **不能說整个 APSR 都 dead**；最窄 stub 保持 flags，不用 DSP/SIMD |

`C023B8D0` 的前兩個動作是把 `r0/r1` 放到 `r5/r6`，其後只讀 model 欄位並測試，
再呼叫 `C035F560`。此 getter 包裝經 `C035F550` 呼叫 lens singleton/state 路線；
本次沒有為了證明 r3/r12 可丟棄而擴展審計整個 transitive call graph。
只使用 r0/r1 的 leaf recorder 可避開這項未知，而不需要以 ABI 常識補洞。

observer 最後 `C022C8A8 E8BD8030 POP {r4,r5,pc}` 回 scheduler。
因此 wrapper 的正常返回必須保持原 SP、observer frame、caller 保存區以及 callee-saved state。

## 4. 無 SP 變動形狀的可行性與限制

只對此固定單 callsite，可作如下**控制流判斷**（不是可部署程式）：

`原 BL 到 wrapper → 無 stack 變動地令 LR=after_native → branch 原 producer → native POP 返回 after_native → leaf 記錄 → branch C022C85C`

成立所需的 code 約束：

1. 原 producer 恰好執行一次；不得跳過原呼叫、把返回當成 retry，或令 recording failure 再呼叫 producer。
2. 入口不改 SP、不改原 `r0/r1/r2`、不改 `r4..r11`；設置 LR／轉移不得意外改 flags 或 ISA state。
3. 最窄 after-native recorder 不額外 BL/BLX，只使用 r0/r1 作暫存；不使用 stack、VFP、DSP/SIMD 或 flag-setting 指令。
   這是刻意窄的可行子集，不是斷言只有這種實作才可能正確。若只加入 `CMP/TST` 等影響 NZCV、
   不改 Q/GE 的普通比較，第 3 節的直接 continuation 分析也已支持其 NZCV clobber；不能把此結論
   擴充到整個 APSR、其他掛點或任何修改後的 native continuation。
4. 最後使用固定 `C022C85C` 的正常 continuation；不能 `BX lr`，因為 LR 已為 wrapper/native 內部呼叫使用，
   也不能假設 entry LR 在 producer 返回後仍保存。
5. 只能適用 ARM `C022C858` 這一處；若移到另一 callsite、共用 producer entry、Thumb target 或其他 firmware，須重做審核。
6. 記錄只能從核准且已驗證的地址讀／寫；滿、disabled、錯誤分支與 publish marker 的完整控制流仍需逐路徑審核。
   普通 NZCV 比較可利用上述已證 deadness；若使用其他 flags／狀態，必須另行證明保留或更寬的安全契約。

「leaf」在此僅指 **after-native recorder 不呼叫其他函式**。整個 wrapper 仍把控制權交給原 native producer，
不能把它當成一般可供任意 caller 呼叫、任意 LR 返回的 leaf function。
新 code 仍有未驗證的指令 fetch/cache、資料 ownership、競爭及執行時間成本；ABI 相容不等於 camera-safe。

### 若加入 clock 或其他 getter

呼叫 `C002B6E0` 就不再是上述 leaf 子集。需另段保存所需現場與精確原 SP，
在新增呼叫的 public ABI 邊界動態確認／建立 8-byte alignment，返回後精確還原。
不能只看 push register count；也不能動態對齊後忘記原 SP，或把下對齊得到的空間當作已擁有的 stack。
新保存 frame、callee 最大 stack、flags／LR／callee-saved 還原及可否在此 task 呼叫都需追加審核。
本次沒有認證任何 clock wrapper；CPU timestamp 也仍不是曝光 ID。

## 5. 現有 assembler/template 的界線

`armasm.py` 只抽取 `.text`，修復其明確支援的 relocation；目前程式實際處理
`R_ARM_CALL (28)` 與 `R_ARM_LDR_PC_G0 (4)`，其他 relocation 或 target 在 `.text` 外會拒絕。
R_ARM_CALL 的 displacement 寫入採 24-bit masking，沒有完整的 signed branch-range 驗證；
成功 assemble 本身不證明 runtime target 正確。未來須逐項核對 load base、ARM/Thumb bit、branch encoding、
±32 MiB branch 範圍與精確 continuation；不得讓未處理的 external branch relocation 蒙混過關。

當時的 `templates/hookprobe.S`／`oneshot.S` 是 gyro／echo 歷史模板；目前來源位於
`fpSup/fp_usb_shell/asm/hookprobe.S`／`asm/oneshot.S`。
其「偶數個 push 保持對齊」只保留**入口已對齊**的 phase，不建立 alignment。
它們的 scratch、原函式、callsite、返回值保存策略都不等於這個 AF 掛點的契約，不能直接照搬。
本文只讀這些檔案，沒有建立或組譯新 payload。

## 未解決／不可由本審核推定

- 實際 OS-entry K 的值與完整 8-byte alignment 證明、目前 task stack high-water／剩餘量。
- 任意更寬 recorder 使用 r2/r3/r12、APSR Q/GE、stack 或額外 native call 的安全性。
- 指令／buffer 位址授權、before-image 與 ownership、record atomicity、跨 task／DMA coherence、最壞執行時間。
- 新 hook 安裝與卸載的 AF-task quiescence；**USB same-worker barrier 不能替代 scheduler/AF task barrier**。
- 原 producer 每次 publication 對應新 DMA／新曝光，以及 cached lens position 的曝光對齊。

本筆記支持繼續離線檢查最窄 no-SP／leaf 記錄形狀；不授權修改 `C022C858`、新增 buffer 或進行硬體試驗。
