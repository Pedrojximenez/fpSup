# AF publication hook：owner／重新註冊路徑的有界離線稽核

2026-09-16，SIGMA fp Ver.5.02。接續
[HOOK_LIFECYCLE_AUDIT](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/HOOK_LIFECYCLE_AUDIT_2026-09-16.md)。
只新增本筆記；沒有 USB、相機操作、實作修改或新 hook 核准。

## 結論先說

**沒有找到 AF-specific、可以持有並涵蓋所有 slot-0 start/stop 的既有 mutex。**
AFMgr 的 event worker 只處理 stop/init/update；start 直接在呼叫者 context 註冊 observer。
所以借 AFMgr completion bit 當 lock、等其 idle，或僅把 AF model 改成 stopped，都不能排除重新註冊。

但是可以把必要保護範圍縮小：不必要求 owner 從 host 等待開始一直被鎖住。
本次有來源依據的最小替代候選是 **非等待式 try-commit**：在同 CPU 的既有短 interrupt critical section 裡，
重新核對 scheduler ready 與 callsite 身分，只有 ready 才完成指令切換及 cache publication；不 ready 就原樣返回。
等待／再次嘗試在 critical section 外，有界且不持鎖。

若 USB helper、scheduler 及此 callsite 的 native caller 確實屬於同一 CPU，這可關閉最後檢查到指令切換之間的
re-register／重新進入競態，甚至不必暫時修改 slot enable。
**此處仍是設計候選，不是已驗證 installer。** 最小尚缺檢查列在第 5 節；不需為尋找不存在的 AF mutex
繼續無限擴大 UI／整個 firmware 的 owner call graph。

## 1. slot 0 實際 writer 已縮成有限集合

搜尋 `out/decomp/full/*.c` 的三個 setter 全部呼叫，另對 ROM 掃描 ARM direct BL 並核對 critical 參數：
`C02072B8` 14 處、`C0207358` 11 處、`C02073D8` 9 處，共 34 處。
固定非 0 的槽位為 1–8；與 slot 0 有關的只有下表。這是已解出的 native source／ARM direct-call 範圍，
不宣稱涵蓋所有可能的 computed call、Thumb 或 RAM 注入程式。

| 實際 BL 地址 → setter | caller／確定參數 | owner 意義 |
|---|---|---|
| `C022B414 → C02072B8` | `C022B378` 的 descriptor type=2；`r1=model+0x2228, r2=0` | 唯一已見的 native slot-0 registration；setter 會設 enable=1 |
| `C022AEA0 → C0207358` | `C022ADF0`；`r1=0` | AFMgr worker 的 stop-all 路徑清除 observer／enable |
| `C023BE70 → C02073D8` | `C023BE58`；`r1=0, r2=0` | 停用 slot 0，隨即等 scheduler ready；外層還有 AF abort／狀態改變 |
| `C029BF64 / C029C07C → C02073D8` | `C029BEA8`；先 `(slot=0,enable=0)`，最後 `(0,1)` | `check_eval_area` measurement 路徑，直接停用／重新啟用，不經 AFMgr event worker |
| `C03DB62C / C03DB6B4 → C02073D8` | shell `start`／`stop` handlers；`r1=parsed_slot, r2=1/0` | 可以指定 slot 0；這些是 scheduler 工具，不是 AF-owner lock |

setter 實作：[register/unregister/enable](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6572)。
重要來源：[register](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32709)、
[unregister](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32533)、
[disable/wait](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:42231)、
[measurement](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:97789)、
[shell handlers](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:154301)。

`C029BEA8` 的來源為 `C022CEC8 → C029BC40 → C029BEA8`，解析字串明確是 `check_eval_area`，
且會改 sensor mode／讀取量測；不能拿來當 lifecycle helper。
見 [measurement entry](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:33955) 與
[parser](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:97669)。
shell table `C0BAC9CC` 的 name 指向 `C0BACA28="start"`，handler `C03DB5C0`；下一筆 name
`C0BACA60="stop"`、handler `C03DB648`。这里只記錄入口，不建議操作這些命令。

`C023BE58` 有兩個已解出的上層 caller：`C022ADF0` 與 `C028BA90`（single-AF processing）。
因此其停用／等待用途也不等於擁有整個 AF model 的互斥鎖。
見 [single processing caller](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:86015)。

## 2. AFMgr worker 是命令執行者，不是所有 start 的唯一 owner

model singleton 是 `C32044D8`。`C022AD58` 使用 once guard 初始化，然後直接回傳；
該 guard 不包住後續 start/stop 操作，不可挪作 ownership mutex。
見 [singleton](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32486)。

建構 `C022AAF8` 建立兩個 event wrappers：`C32044B8` wake，`C32044B4` request/completion；
thread holder `C32044C4`，entry vtable `C0918438+0x0C = C022AAE0`，再進 `C022C5F0`。
見 [construction](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32436)。

`C022C5F0` 的完整 dispatch 集合已核對 source 與 ROM：

| `C32044B4` bit | 執行函式 | slot 0 關係 |
|---|---|---|
| `2` | `C022AF98` | single-AF stop，取消 slot 1 |
| `4` | `C022ADF0` | stop-all，取消 slot 0／1 |
| `8` | `C022B118` | 初始化／更新 model，未直接註冊 slot 0 |
| `0x10` | `C022BB78` | AF update 路徑，未直接註冊 slot 0 |
| `1` | 每輪末尾設置 completion | 沒有 acquisition／owner 身分，也沒有阻止直接 start |

見 [worker loop](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:33412)。
提交端寫 shared model 參數、set request bit、set wake；`C022C6D0` 在 callback 參數=0 時
等 completion bit 1，mode=`0x10`（成功後清 event），timeout=`0xFFFFFFFF`。
它是該 request 的同步等待，不是保護後續任意作業的 token。
見 [stop request](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32503)、
[init request](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32601)、
[completion wait](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:33446)。

不能挾持 bit 1、吞掉 completion、持續清 event 或停住 AFMgr worker 來擋 start；
那不會涵蓋下面的 direct path，反而會阻塞原廠等待者。

## 3. 直接 start 繞過上述 worker：三個已解出的入口

`C022A938` 的 ROM `C022A944..C022A950` 是 `get singleton → C022B378` 的直接呼叫。
`C022B378` type=2 分支沒有 lock、event wait 或 stopped gate；`C022B400` 先將 observer state 設 2，
`C022B414` 註冊 slot 0。不能把 model state=0 或 observer state=0 當作 owner lock。

三個 direct caller：

1. `C0399E88`（Camera3A 流程），在 `C0399F08` 呼叫 `C022A938`。
   descriptor type 來自 `param_2`，`param_4!=0` 時才改成 8；正常 type=2 會註冊 slot 0。
   外層 `C039A238` 等流程可到這裡；被呼叫函式沒有取得共用 AF mutex。
   見 [Camera3A start](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:105558) 與
   [background start caller](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:105716)。
2. `C0487EE0`（UI handler 路徑），ROM `C0487F54` 明確寫 descriptor type=2，
   `C0487F64` 直接呼叫 `C022A938`；停止分支才呼叫 `C022A980(0)` 走 AFMgr worker。
   因此只保護 Camera3A 狀態物件或 AFMgr event 都沒有涵蓋這條 start。
   見 [UI start/stop](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c04.c:101975)。
3. `C022E360` 測試輔助路徑，在 `C022E3A8` 呼叫 `C022A938`，但 ROM `C022E380..384`
   固定 descriptor=1，故這個 callsite 本身不是 slot-0 start；它還會 stop／wait／初始化，不能借作無副作用屏障。
   見 [test helper](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:34796)。

host AF lease 可排除守約的本研究工具，不能替代這些 native caller 的執行排除。
不過也不需要把它們全部停住到 host 完成漫長讀寫：只需要讓最後的安全檢查與指令 commit 沒有競態。

## 4. 已存在、值得採用的最小原語：短 XC_INTR，而非持鎖等待

### 4.1 已證實的 native 行為

`C001CCE0`（XC_INTR 建構）把 `C000EC14()` 返回的原 CPSR 存到 guard object；
`C001CD18` 用 `C000EC24(saved)` 還原。ROM `C000EC14..EC38` 明確只保存／遮蔽／還原 IRQ+FIQ bits `0xC0`。
既有 registry mutation 也使用此 guard，例如 `C0321508/C03215C0`。
見 [XC_INTR wrapper](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:26251) 與
[registry precedent](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:22719)。

ready reference `C036D888 → C01F8BE0 → C00040A0` 不會等待 event：

- `C00040C8` 保存／遮蔽 IRQ+FIQ；讀合法 event 的 pattern，成功才填 result。
- `C0004108..4110` 檢查進入時 CPSR 的 `0xC0`；若已遮蔽就跳過 `C0004154` 的 task-dispatch 呼叫。
- `C000415C` 還原所保存的 mask，故外層 mask 保持有效。
- 唯一額外 getter `C000E040` 只回傳 first waiter ID 或 0，無等待／mutation。

見 [event reference](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:2661) 與
[waiter getter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:10864)。

**ready reference 的確切 ABI（另核對 `C036D888..C036D8DC` ROM）：**

```c
uint32_t C036D888(const uint32_t *event_wrapper, uint32_t result[3]);
// r0 = wrapper address；r1 = caller-owned、預先清零的 12-byte result
// return r0 = 1：成功，三字均寫入；return r0 = 0：失敗，不寫 result
```

此處 `event_wrapper` 必須是已初始化 scheduler `*(S+0x0C)`，預期固定身分 `C31F8C9C`；
**不是**把 `*(C31F8C9C)` 的 kernel ID 直接當 pointer 傳入。
輸出依序是 `[event exinf, first waiter task ID（無 waiter 為 0）, current pattern]`。
只有 `return==1 && (result[2]&1)!=0` 才是 ready；ready=0 與 API 失敗要區分記錄。
它沒有 timeout／mode 參數，不消耗 completion，也不清 event bits。
ROM 在 `C036D898` 先 load wrapper 的 ID，`C036D8A0` 呼叫 kernel-reference stub，
只在 kernel return=0 的分支複製三字。
見 [wrapper](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:74897)。

cache helper `C000E91C` 本來就用 `C000E91C..E928` 保存／遮蔽 IRQ+FIQ，執行有限 cache set/way 迴圈，
最後 `C000E9A4..E9B0` 只還原進入時的 `0xC0`。
因此外層若已遮蔽，它**不會**在 flush 結束後偷偷開中斷。
`C000EABC` 為 I-cache invalidation + DSB + ISB，沒有解除中斷遮蔽。
兩者仍只是本次已核對的 CPU cache primitive，不能冒稱跨 core shootdown。
見 [D-cache helper](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:11420) 與
[I-cache helper](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:11540)；CPSR 部分以 ROM 為準，decompiler 未完整呈現。

### 4.2 最小 try-commit 語意（尚未實作）

預先完成 code/data lease、before-image、ABI 與 code readback。最終的一次短 task-context helper 只做：

1. 進入 XC_INTR 等效的局部 critical section；不在這裡呼叫 lazy singleton constructor。
2. 核對 scheduler／observer／event wrapper 與 callsite 原值，初始化三字結果，成功 reference ready bit 1。
3. 不 ready、reference 失敗或身分不符：不改 callsite／slot enable／AF model／event bits，
   完整還原 mask，返回明確 not-ready／refused。僅 helper 自己的 stack/result/diagnostic output 有寫入，
   沒有持續性的 camera-control mutation；不得順便做 stop、disable、clear-ready 或 cache publish。
4. ready 且同 CPU 排除條件成立：完成單一固定 callsite 的 expected-word replacement、readback、D/I-cache publication，
   再完整還原 mask。途中不得有 USB、printf、配置、sleep、等待或無界重試。

等 ready 的時間留在 critical section 外；不把 host 先前觀察到的 ready 當作步驟 2 的替代品。
critical section 內若 ready=0，絕不能等到它變 1：被遮蔽的 scheduler 必須先得到執行機會才會返回並設 ready。

在同 CPU、native callback 僅由已辨識 scheduler 路徑執行的前提下，ready=1 保證目前沒有 in-flight callback，
而 critical section 使其他 native task 無法在 commit 前重新註冊／進入；解除 critical section 後
重新啟用可以發生，但它只能看到已完成 publication 的指令。
所以此方向**不需要長期暫借 enable byte，也不需要覆寫原廠 start/stop 意圖**。
這是對上篇「先 disable 再等 ready」概念的縮減，不是宣稱原廠已有 hook installer。

安裝與 detach 都應走同一 try-commit。detach 成功後，才可在後续已證明沒有其他引用的時點回收 hook code/data；
執行 try-commit 的 helper 自己則仍須遵守 USB-worker 返回／echo lease 規則，不能自我覆寫。
uncertain commit reply 不能重試當作沒發生，需保留其 nonce／原值／結果證據。

## 5. 最小剩餘檢查與停止界線

1. **確認同 CPU 執行域。** 本次已找到的 owner 路徑屬 native task／scheduler；XC_INTR 僅本 CPU 有效。
   尚未有足夠證據證明 USB worker、CameraMgrScheduler 及其他 callsite caller 不會在另一個 CPU 執行。
   應針對此具體執行域查 boot/task-affinity 與 existing worker entry，而非把「整台相機有幾核」當成答案。
2. **量化 critical-section 上限。** reference／fixed stores／cache helper 均無本次已見的 blocking wait，
   但 cache flush 成本取決於 CPU cache 幾何；需給出本 target 的 instruction／cache-operation 上限與允許的 interrupt 延遲。
   native helper 自己也遮蔽 IRQ 不等於任何頻率、任意新增工作量都安全。
3. **把具體 commit helper 的失敗路徑審完。** expected callsite word、未知 owner 拒絕、mask restore、
   readback/cache publication、nonce、在 uncertain reply 下不回收；並確保 helper 與被回收 hook 的 lease 不相互覆蓋。

只要第 1 項不成立，局部 critical section 就不夠，必須改用真正跨 CPU 的 native 同步；
本次未發現可代用的 AF event mutex。不能用一次 active=0、AFMgr ACK、phase 推進或前後 slot 值相同補洞。
在這些檢查完成與新增範圍獲核准之前，不部署、不用 unbounded `C0207450`，也不為取得 quiet state 自動觸發 AF stop／模式切換。

## 來源識別

ROM 與 `blk_c00/02/03.c` SHA-256 同上篇 lifecycle note；critical args 與 CPSR/cache 行為都另以 ARM disassembly 核對。
本次新增檢查 `blk_c04.c` 的 `C0487EE0`，關鍵 ROM 點為 `C0487F54=mov r2,#2`、
`C0487F58=str r2,[sp]`、`C0487F64=bl C022A938`。
所有結論限定已辨識的 Ver.5.02 native 路徑；沒有把 source fact、條件式推論與硬體實測混為一談。

## 6. 後續有界縮減（未部署）

同 kernel 的具體鏈已補齊：CamSch `C0207AD0 → C036DD40(index=13) → C036ECA8 → C0016A58`，
start 經 `C036DDF8 → C036EE08 → C0016BC0`；既有 `camera/worker.S` 也使用
`C0016A58/C0016BC0`。main-task kernel `C000A9C0` 與 ready-reference `C00040A0`
使用固定全域 current/next `C3000098/C30000A0`，在 IRQ mask 已設時不 dispatch。
這支持「相同 uniprocessor-style kernel 執行域」的推論，但不單獨證明其他處理器永不執行此 image，
也不把歷史 Cyc task descriptor 誤套到 main task。

critical section 的 cache 工作也可縮小：所有新 code/data 預先在區外完成 publication；
commit 只改 `C022C858` 一個字時，候選為 `C000EB90(C022C858,C022C85B)`
清理涵蓋該字的 cache line，接 `C000EABC()`，不在遮蔽區做整個 D-cache set/way sweep。
`C000EB90` 的 inclusive-end 與 MVA-clean/DSB 已於 EP83 ABI 審核過；這是待測 helper 的設計，
沒有繞過第一個 RAM helper 執行前必須以 ROM 完成 D/I publication 的 bootstrap 規則。
