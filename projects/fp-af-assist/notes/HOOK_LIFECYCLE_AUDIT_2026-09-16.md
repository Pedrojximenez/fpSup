# AF publication hook：離線 lifecycle / quiescence 稽核

日期：2026-09-16。對象：SIGMA fp Ver.5.02，`C022C858` 的 background observer publication callsite。

本次只有 ROM／反編譯與既有筆記的靜態檢查；沒有 USB、相機 RAM 變更、程序操作或 hook 實作。
既有 echo／`C072F700..C072F9FF` 核准範圍**不包含**此 AF callsite 或新記錄區域。

## 結論

找到原廠確實使用的 **停用 scheduler slot → 等待 scheduler ready acknowledgement** 配對，
比 `active=0`、USB echo 返回或 phase 變化更直接：

- `C023BE58` 的開頭以 `C02073D8(S, 0, 0)` 停用 slot 0，接著 `C0207450(S)` 等待 ready event bit 1。
- `C0207620` 在整輪同步 observer callbacks 返回後、下一輪等待前設 ready bit 1；開始 dispatch 前已清掉該 bit。
- 在「同一已初始化 scheduler、停用對它可見、期間無任何 re-register/re-enable、event 操作成功、此 callsite 沒有其他執行來源」的前提下，成功取得 ready bit 1 可作 **舊 callback 已返回且 slot 0 不再進入** 的條件式 quiescence 證據。

但這尚非完整可用的 hook lifecycle：**未找到將上述條件一併鎖住的既有排他所有權原語**；
所有 caller／其他 core 的排除，以及 code-cache publication 範圍也未完成證明。
原版 `C0207450` 又是無限等待，不能直接當作有界 USB helper；整個 `C023BE58` 更會 abort／改 AF 狀態。
因此本次結論是「已有可依據的 native barrier 語意，但 install/uninstall 仍缺少必要條件」，不是批准上機。

## 1. 固定身分與執行路徑

以 `S = C31F8CB4` 表示 singleton scheduler；以下 ready/wake 是本筆記的功能標籤，不是推定的新 ABI。

| 位置 | 已核對內容 |
|---|---|
| `S+0x00 = C31F8CB4` | 循環 phase；並非單調 generation |
| `S+0x04 = C31F8CB8` | mode |
| `S+0x08 = C31F8CBC` | wake event wrapper 指標，建構值 `C31F8CA0` |
| `S+0x0C = C31F8CC0` | ready event wrapper 指標，建構值 `C31F8C9C` |
| `S+0x14 = C31F8CC8` | scheduler thread holder，建構值 `C31F8CA4` |
| `S+0x18 = C31F8CCC` | slot 0 observer 指標 |
| `S+0x24 = C31F8CD8` | slot 0 enable **byte** |

初始化與 once 路徑：[`CamSch1 / C0207188`](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6504)。
`C0207AD0` 建立 thread entry；ROM vtable `C090EF54+0x0C = C02070D0`，該 thunk 在 `C02070E0` 分支到 `C0207620`。
見 [thread construction](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6904)。

`C022B378` 的 mode-2 路徑設定 observer state `context+0x222C=2`，將 `context+0x2228` 註冊為 slot 0，
見 [background registration](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32709)。
observer vtable `C09185A4+0x0C = C022C7E8`；其 publication 呼叫是 `C022C858: EB00485C`，
即 `BL C023E9D0`，返回 `C022C85C`，然後才呼叫 AF decision。
見 [observer](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:33522) 與
[先前 callsite 稽核](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AF_PUBLICATION_HOOK_CANDIDATES_2026-09-16.md)。

範圍受限的 ROM xref 檢查：aligned literal `C022C7E8` 只見 `C09185B0`；ARM B/BL 直接指向
`C022C7E8`／`C022C858` 未見；`C0207620` 的 ARM B/BL 命中 `C02070E0`。
**這不是全系統唯一 caller 證明**：沒有涵蓋所有 Thumb／computed pointer／RAM 動態註冊來源。

## 2. 原廠 disable + ready 配對：已用 ROM 修正反編譯缺參數

[`C023BE58`](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:42231)
的 decompiler 把第一次 `C02073D8` 顯示成兩個參數，不能直接據此判斷 enable 值。
實際 ARM 是：

```text
C023BE64  BL  C0207188       ; CamSch1()
C023BE68  MOV R2, #0
C023BE6C  MOV R1, R2         ; slot 0, enable 0
C023BE70  BL  C02073D8
C023BE74  BL  C0207188
C023BE78  BL  C0207450
```

`C02073D8` 只在 observer 非 NULL 時，以 `STRB` 寫 `S+slot*0x14+0x24`；不取消已被 scheduler 複製到區域變數的 callback。
見 [enable setter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6612)。

`C0207450` 等 `C036D818(*(S+0x0C), 1, 0, &result, 0xFFFFFFFF)`；非成功則 assert。
ROM `C020745C..C0207474` 亦核對到 timeout=-1、bits=1、mode=0。
見 [wait helper](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6642)。

另一個獨立 native precedent：`C029C248` 先停用 slot 2，再呼叫 `C0207450`，最後重新啟用 slot 2；
其用途包含 AE／program-line 測試，不是可以直接借用的純同步 wrapper。
見 [slot 2 disable/wait](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:97919)。

## 3. ready bit 的語意不是猜名字

`C0207620` 的 ROM／source 順序：

1. `C02076B0` 設 ready bit 1，然後等 wake bit 1。
2. wake 成功後清 wake；再等 ready bit 2，成功後 `C020775C` 清 ready 全部 bit。
3. mode 6 則不 dispatch；其他 mode 逐 slot 複製 observer／tables／enable 到區域變數。
4. `observer->vfunc(+0x0C)` 是同步呼叫，返回後才處理下一槽。
5. 所有槽完成／mode 中斷之後才更新 phase，迴圈回到步驟 1。

見 [ready/wait/clear](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6780)、
[local slot copy](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6838)、
[synchronous call / phase update](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6866)。

VD callback `C02074C0` 先 reference ready：如果 bit 1 為 0，只記錄 overrun；若為 1，
依序 set wake 1、clear ready 0、set ready 2。即使 scheduler 在 wake set 後被喚醒，仍須等 bit 2，
並在 dispatch 前清 ready；不能因為 wake 提早出現而將舊 bit 1 留到 callback 內。
見 [VD-side handshake](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6655)。

### event kernel 對照

不能把 wrapper 的第一字當作旗標，它是 kernel event ID。
本次由 ROM syscall dispatcher `C0001240..C0001248` 及其 literal `C0001568 = C0021040` 追到下表，
不是僅依 wrapper 名稱推論。

| wrapper → syscall stub | syscall literal / dispatch entry | kernel 實作與效果 |
|---|---|---|
| `C036D758 → C0016B9C` | `80220200` / `C00010C8` | `C0003C58`：pattern OR bits，喚醒符合條件 waiter |
| `C036D7E0 → C00169C8` | `80230200` / `C00010CC` | `C0003DB0`：pattern AND mask；mask 0 清全部 |
| `C036D818 → C0016C08` | `80240500` / `C00010D0` | `C0003E78`：mode 0 等全部指定 bits，**不**自動清除 |
| `C036D888 → C01F8BE0` | `80250200` / `C00010D4` | `C00040A0`：成功時回傳三字，第三字是 pattern |

kernel 依據：[set](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:2483)、
[clear](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:2555)、
[wait/mode](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:2611)、
[reference](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:2676)。
wrapper 依據：[wait return mapping / reference copy](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:74875)。

ROM event templates `C090EFE8` / `C090F000` 分別是 `CamSch1` / `CamSch2`，attr=`0x48`、initial pattern=0；
constructor 把 template+4/+8 傳進 kernel create。見 [event construction](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:74781)。
wait kernel 的 `attr & 8` 分支容許多 waiter；仍不得隨意改 event bits／attr 來製造 acknowledgement。

以上 kernel 操作在本 CPU 用 `C000EC14/C000EC24` 保存／遮蔽／還原 IRQ/FIQ；ROM 指令已確認。
**這不等於跨 core lock 或全系統 instruction-cache shootdown。**

### 條件式證明與限制

在正常成功 event 路徑下，ready bit 1 為 1 時，此 scheduler 尚未進入下一輪 slot dispatch，
或上一輪已全部返回。若 disable 已可見且禁止重新啟用：

- 若 ready 原本為 1，沒有正在執行的 slot 0；下一輪讀到 enable=0，因此不需強迫一次 0→1 才有效。
- 若 slot 0 正在執行、甚至已複製 enable=1 但尚未 call，ready 必為 0；只能等本輪返回後的 ready=1。
- ACK 之後 ready 可以再清掉、其他槽可以繼續執行；只要 slot 0 持續停用，它不能再次進入。

此證明不包含事件失效後 assert 仍繼續、任意 alias 修改同一 flag、另一 scheduler 複用該 event、
其他 caller 進入同一程式碼、未同步的跨 core 可見性，以及在檢查前後偷偷 re-enable 的情況。
一次 enable readback 或兩次相同狀態快照不能排除最後一種競態。

## 4. 最小可支持的 lifecycle 方向（設計條件，不是部署步驟）

可考慮的最小概念是：**取得可證明的 slot 所有權／禁止新進入 → 停用 slot 0 → 有界、成功的 ready reference →
在保持禁止新進入時處理 callsite/cache → 最後才恢復原 scheduler enable 狀態。**

安裝與解除都需要這個保護區間；不應先在運行中的 task 下任意還原指令，再靠猜测等待時間回收記憶體。
解除時 hook code／data 的回收必須在原指令完整還原、cache publication 完成、沒有 task 尚在 hook 中之後。
「回收」包含把 before-image 寫回 scratch，並不只有 free。

可能的有界觀測是 `C036D888` reference：初始化 3-word 輸出，核對 return=1，再檢查第三字 bit 1；
host 有 deadline，逾時／transport error／身分改變就不能宣稱 quiescent，不能藉 timeout 推定可以回收。
reference 本身不清旗標；不要使用 clear-ready 或 set-ready 來加速。
這只是候選 adapter：本次**沒有**新增任何呼叫能力，也沒有證明在現有 USB worker 中的完整執行預算。

`C0207450` 本身會阻塞到無限 timeout，故不作第一版有界 helper 候選；
有限 timeout 的 `C036D818` 仍須單獨確認時間單位、等待 context 與失敗處理。
不可從 AF scheduler 自己的 callback 內等 ready：它必須先返回才可能設 ready，存在自等死鎖。

slot 停用會暫停原 background AF callback 的原生工作；即使不改選單設定，也不是純 read-only 操作。
`C023BE58` 在等待後還可能呼叫 `C035FEE8` abort，並呼叫 `C024D418`／`C02404A0` 改 AF 狀態，
所以不可整段重用。已有 thread 不需重啟，也不应為此建立第二個 scheduler。

### 尚缺的必要條件

1. 原廠 AF state owner 的排他方式：`C02072B8` 註冊會重寫 slot 並把 enable 設成 1；
   `C0207358` unregister 及 `C02073D8` enable setter 內沒有 mutex／ack。
   目前未證明可阻止模式變更、原 AF 请求等路徑並行重新註冊。見 [registration setters](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6572)。
2. 此 callsite 的完整執行來源與 task/core 排除。已有 vtable／scheduler 路徑是正向證據，不是排他性證明。
3. slot disable、ready reference 及指令 publication 在相關 CPU 間的 memory/cache 可見性；
   既有 D-cache clean／I-cache invalidate ROM helper 不可未經核對就當作所有 core 同步。
4. hook ABI、worst-case execution、獨立 code/data 所有權、before-image、失敗時保留狀態與恢复策略；
   不可用已核准 echo lease 替代新增區域的核准。

## 5. phase-after-restore witness：本次不接受為獨立回收條件

確實，`C0207620` 的本輪 phase 更新在同步 callback 返回之後。
如果另已證明「只有該 task 寫 phase／進入 callsite、完整 code-cache 同步、最後 hook instance 對應關係、
無模式重設、無後續進入」，那麼嚴格有序的後續 phase 更新可以佐證 task 已越過返回。
但它沒有免除這些前提，也沒有比 ready barrier 更少的證明義務。

目前直接反例／缺口：

- `C02073B8` 在 `C02073C4` 寫 mode，`C02073CC` **直接把 phase 清成 0**；因此 1→0、2→0 不必來自 callback 完成。
  前後讀到相同 mode 也排除不了中間變更後改回。見 [mode setter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6601)。
- scheduler 自己也會因 modulus 或 mode-abort 重設 phase；它不是有 nonce 的單調退出 generation。
- hook 的 `returned`／`active=0` 標记是在最後的返回指令**之前**写入；可能仍有 PC/LR／暫存器指向將回收的區域。
- 還原 callsite 後的 pending fetched branch、另一 core 的 I-cache、其他 task／computed caller 尚未被排除。
- 只有 USB handler 的成功回覆，最多證明该 handler 完成，不是 AF scheduler 的執行位置。

因此不把「原指令 readback 正確 + active=0 + 看見 phase 變化」升格為安全卸載。
若無法建立第 4 節的禁止新進入／ready 條件，應保留「quiescence 未證明」結論。

## 6. 其他現有原語的排除

- mode 6 + ready wait 確有原廠先例：`C022D448` 的 measurement dispatcher；但 mode 6 停掉整個 scheduler dispatch，
  mode setter 又重設 phase，後面還有 sensor/measurement 動作，比 slot 0 disable 更廣，不當作無副作用替代。
  見 [mode 6 / wait](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:34209)。
- `C0207358` unregister 只清 shared observer/enable，不等已複製到 local 的 callback，因此不單獨构成 barrier。
- `C0207600 → C036DE30 → C01F8814 → C000B0E0` 改 task priority（syscall literal `80090200`、entry `C0001064`）；
  並沒有等待 callback 返回。見 [thread wrapper](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:75229) 與
  [priority kernel](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:8558)。
- `C0207B20` 是 thread-holder destructor，不是可逆的 callback join；不當作同步方案。
  見 [destructor](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6919)。
- `C0321508/C03215C0` 對 VD callback registry 使用局部 interrupt guard；刪除 VD callback 不會證明已喚醒的 scheduler 完成。
  見 [VD registry/remove](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:22719)。
- `C036E028/C036E1F8` 的 thread-pool completion 不是這個 standalone scheduler 的 join；不能混用物件或 ready flag。

## 可重現來源

既有設計前提：[HOOK_SAMPLING_PLAN](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/HOOK_SAMPLING_PLAN_2026-09-16.md)。
本次核對使用 ROM `out/seg0_c0000000.bin`，base `C0000000`，及 `out/decomp/full`；反編譯缺少參數處以 ARM bytes 為準。

```text
SHA256 seg0_c0000000.bin
aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622
SHA256 blk_c00.c
9bb8b762d86f951617792b912d1bd2f2d2581f587e159c54e68d974bdd015180
SHA256 blk_c02.c
c2c5b6aabb2fbd01497d0b9acda511ab51a60d651724a363197c8d8bad51d491
SHA256 blk_c03.c
12a216e184e0eb183588f707644224adc95f602b9185deb4c5415d7d52627a8d
```
