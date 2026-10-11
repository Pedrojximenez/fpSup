# USB routing repair audit — single native owner, not ACK recovery

日期：2026-09-16。範圍：fp 5.02 的離線 source/binary 審核與修復提案。
本輪只新增本檔；沒有 USB、daemon、worker、記憶體、端點、SD 卡或相機操作。

## 決策

**沒有找到能由 host-only 真正修復目前 ownership 競爭的方案。** 主機可以更完整地保存、
分類或繼續接收異常封包，但不能從 EP01 OUT 的主機成功回傳，判定哪個 camera-side
consumer 使用了資料，也不能強制原廠與自訂 worker 對同一 TRB／完成事件互斥。

建議的最小「結構上能消除這組雙 consumer」修復，是 **mode-5 native-task single-owner
adapter**：讓原廠 `usbTask` 保有 bulk 收發與完成事件生命週期，在其 PTP 接收服務入口
改由一個有界 FPSH 服務處理；**不再啟動目前獨立 worker 的 arm/wait/reply loop**。
保留原廠 EP0、enumeration、描述元與底層 driver。這不是只加 sampling hook，亦不是
在 PTP parser 前忽略 FPSH；獨立端點 loop 的退出是此提案不可分割的部分。

這是可供下一輪離線實作與審核的具體修復方向，**不是已完成、可立即部署的 patch**。
它不聲稱解釋每次 timeout，也未證明所有 camera-side bulk writer 已排除。需要下述
ABI／封包邊界／生命週期驗證與新授權，不能直接啟用 AF motion。

既有 `0x2003` 封包、sequence 與 drain 證據不在此重述，見
[共享路徑研究筆記](../../../research/interfaces/notes/FP_USB_PTP_SHARED_PATH_2026-09-16.md)。
本篇補充的是 ownership 路徑及修復選擇。

## 1. 足以約束修復設計的新增源碼事實

以下 C00/C01/C04 分別指 `out/decomp/full/blk_c00.c`、`blk_c01.c`、`blk_c04.c`；
行號以文末雜湊版本為準。

### 1.1 worker 的 Wait 並非獨立等待器

目前 [worker.S](../../../fpSup/fp_usb_shell/camera/worker.S:323) 的路徑為：

```text
worker: arm_out → C01E4E80(logical 1) → read worker frame → SHRUN
        → arm_in → C01E4E80(logical 2) → next_round

C01E4E80 → C01E4B30 → C01E71E0 → C01E7780
                                      └→ C01E76B8 on not-ready events
```

- `C01E4E80` 是實際實作；worker 以 Thumb entry `C01E4E81` 呼叫。
  C01:135922–135942 會呼叫 `C01E4B30`，不只是回傳一個私有 semaphore。
- `C01E4B30` 將 logical endpoint 組成 `0x10000000 | logical<<1 | direction`，
  交 `C01E71E0`（C01:135654–135697）。
- `C01E71E0` 使用同一 RTOS flag ID `C31E3210`，等待後直接呼叫
  `C01E7780`／`C01E76B8`（C01:137923–137978）。
- `C01E7780` 在 bulk OUT 完成時可設 `C31E3A08=1`、`C31E3974=0`；
  當 `C31E3974!=1 && C31E3A08==0` 時，另可將 bulk OUT TRB 指回
  `*(u32*)C3025744` 所指的原廠接收 buffer，再 `StartTransfer`。
  這個後段不只存在於 OUT 專屬分支，因此 **IN 完成處理也可能重新 arm OUT**
  （C01:138233–138251）。条件是否在事故當刻成立仍未量到。
- `C01E76B8` 對 bulk OUT 的 not-ready 事件也能 arm 同一原廠 buffer
  （C01:138156–138165）。

因此只讓 parser 提前 return、只暫停高階 PTP command dispatch，或只增加 host pacing，
都不能宣稱 worker 的 wait 已不會碰原廠接收狀態。

### 1.2 原廠 usbTask 也會處理同一 bulk completion

完整可達路徑是：

```text
USB IRQ C01E3660 → signal C31E3A88 semaphore
usbTask C0033B80 → C01E9380 → C01E92E8
  → C01E3D68 → C01E71E0(endpoint, 0) → C01E7780
  → event 2 → C0033AD0(mode 5) → C04DB778 → C04DC780
```

- IRQ completion 清共享 active-state 並設 completion flag；not-ready 事件另設 endpoint
  bit；結尾 signal `C31E3A88`（C01:134611–134691）。
- `C01E9380` 等該 semaphore（C01:140039–140063），`usbTask` 醒後呼叫
  `C01E92E8` 並在 event 2 執行 `C0033AD0`（C00:42753–42768）。
- `C01E92E8` 在 queue 沒現成事件時呼叫 `C01E3D68`
  （C01:139975–139991；queue getter 見 139059–139069）。
- `C01E3D68` 在 `C31E3974==1` 時，對選到的 bulk OUT 呼叫同一
  `C01E71E0(...,0,...)`（C01:134886–134889）。

這是兩個 task 可達相同 driver completion routine 的靜態證據，不是事故動態排程 trace。
它比「可能同時讀一個 payload buffer」更精確：兩者的 buffer 可以不同，但 endpoint、TRB
pointer slot、active-state、完成 flag 與再 arm 邏輯確實共用。

### 1.3 存在性檢查不是端點租約

worker 只檢查 DALEPENA bits `0x24` 與 USB_STATE 不為 4
（worker.S:302–321），隨後直接寫 `*C31E3268`／`*C31E326C` 的 TRB，再呼叫
`C01E6B80`（worker.S:549–566、685–702）。

`C01E6B80` 會修改 driver active-state，送 DEPCMD，bulk OUT 成功後設 `C31E3974=1`
（C01:137542–137587）。這不是「先取得 consumer 身分、再准許改 TRB」的 API；worker
甚至在呼叫它前就已改 TRB。端點 enabled 只能證明管道存在，不能證明原廠接收／回覆已退出。

`C0033AD0` 在 handler 前後呼叫的 ioctl `0xE,0/1` 也 **不是可借用的 ownership lock**：
`C01E88A0` case `0xE` 只在非零參數時呼叫 `C01E4138`，後者在此映像中是空函式
（C00:42723,42736；C01:139303–139307、135119–135124）。

### 1.4 native 接收 API 與 parser 入口必須一起處理

`C04DB778` 先設定 ioctl `0x14=1`，讀四個 bytes，再把所得 length 截成 16 bits，
切回 `0x14=0` 並讀其餘 bytes，最後才呼叫 `C04DC780`
（C04:165419–165443）。ARM 原始碼核對：`C04DB834..C04DB84C` 組合四 bytes 後執行
`uxth r6,r1`；不是可以把任意四-byte FPSH magic 當成安全長度的通用 packet router。

`0x14` 對應 `C01E4C30`，管理 `C31E39FC` 與 `C31E3A00` 的 partial-read offset
（C01:139322–139323、135723–135729）。實際資料路徑為：

```text
read:  C00337C8 → C01E87B8 → C01E7FA8 → C01E8000 → C01E4ED0
write: C0033838 → C01E8820 → C01E8070 → C01E8110/C01E5320
```

read 的副作用包括 native-buffer copy、offset／pending-data 狀態更新與必要的重新 arm
（C01:135964–136062）。`C01E8000` 只測非負 timeout 參數後即呼叫 `C01E4ED0`，
並未把該參數下傳（C01:138618–138628）；不能將傳入的 200／225 宣稱為完整有界 host deadline。
write 的 exact return-value convention 也必須保留：PTP 發送端將 `C0033838` 的 **0**
當成功（C04:165780–165791），不可拿 worker 的 `StartTransfer`／Wait 結果混用。

## 2. 為何幾種 host-only 小改動不是修復

| 手段 | 本輪判定 |
| --- | --- |
| 遇 12-byte PTP 後繼續 IN、等待同 seq FPSH | 可另做只讀診斷；若真的得到有效 FPSH，僅改善該次收取。不能保證 worker 收到 OUT、不能阻止 native 另 arm，也不能把期限延長或 drain 當 ACK。 |
| 延遲／單 client／host interface claim | host seriality 不約束相機兩個 task。claim interface 在 fpshd.c:104–109，camera TRB ownership 不在 libusb 管理。 |
| 發 PTP OpenSession | 改變 native session，沒有轉移 bulk owner；opcode 0 仍不是 shell，可能只把 2003 換成另一錯誤。C04DC780 的 default 仍送 2005（C04:166740–166741）。 |
| 清 native session flag、清 halt、reset／re-enumerate | 不是只讀；可能消除一次症狀，但既有兩條 owner 路徑仍在。不得將 reset 作為 uncertain shell 未執行的證據。 |
| 將 interface class 換 vendor-specific | 已有 patches.py:18–24 明說只防 host PTP claimant；不關閉原廠 task。 |
| 只關 parser／殺 usbTask／改共享 flag | 不能清除 worker Wait 內的 native re-arm；還可能移除 mode/configuration handling 或留下 armed transfer。没有完整可逆 ownership 協定，不建議。 |

`fpshd.c:196–203` 的一次 OUT 與 `234–242` 的 IN 失敗仍必須分開理解：OUT 成功不證明
shell 已執行，IN 的 PTP 錯誤亦不證明 shell 未執行。此提案不修改「uncertain → 停止新增
動作／保留證據」政策，**沒有 ACK recovery 或 command replay 授權**。

## 3. 一個具體修復提案：native-task single-owner FPSH adapter

### 控制流入口與檔案

已對 `out/seg0_c0000000.bin` 離線反組譯確認：

- `C0033B38`: `mov r0,r4`，此分支的 mode 為 5。
- **`C0033B3C`: `BL C04DB778`，原始 ARM word `0xEB129F0D`。**
- 返回後經 `C0033B64..C0033B70` 執行原有 post-handler 邏輯。

下一輪若獲授權，可在 shell-only 專用 build 中將此 **mode-5 單次服務呼叫** 接到新 adapter，
而不是讓 adapter 變成第二個常駐 endpoint loop。概念上的實作檔案範圍：

- `fpSup/fp_usb_shell/camera/worker.S`：把 shell capture／dispatch／framed-reply 部分整理為
  有正常 return 的單次服務；新 build 不再啟動既有 `serve/arm_out/arm_in` 常駐路徑。
- 新 camera-side adapter：由 native `usbTask` 服務一次已到達的 packet，使用原廠 buffered
  read/write 與 state transitions；**不直接寫 TRB、不另呼叫 StartTransfer/EndTransfer**。
- 對應 build／loader 設定：在 USB 尚未開始服務時安裝 adapter 與已核對的 callsite，
  保存 before-image／版本雜湊，明確禁止同時啟動舊 worker。
- `host/fpshd.c`：初版限定固定 64-byte framed request、固定小回覆；拒絕 long-spill、
  raw/BULK 變體。不是在舊 daemon 的 failed-exchange path 加 resend。

既有 native read/write prototype 可由上述函式推導，但不是已驗證的公開 SDK。新的 RAM
配置、entry address、stack 契約與 cache publication 尚未設計，**本篇沒有建議寫入地址
或產生可直接執行的 patch bytes**；`C0033B3C` 是已核對的候選控制流位置，不是本次操作清單。

### 初版協定與 ownership 不變量

1. 同一 dedicated shell build 只有 native task adapter 是 EP01/EP82 的高階 FPSH consumer；
   原廠低階 USB driver／EP0 task 保留。旧 worker 一開始就不啟動，不能在本輪不可靠 shell
   上一邊執行它、一邊把它熱換掉並宣稱已交接。
2. native task 先完整接收、驗證固定 frame 長度、magic、version、command、flags、payload
   上限、NUL 邊界、CRC，再 dispatch。**先判 FPSH，再進 PTP length/parser**，FPSH 不可到達
   `C04DC780`。專用 shell-only 初版不允許同時開 native PTP session；非 FPSH input 拒絕，
   不以「先消費四 bytes 再 call 原 handler」假裝無損 fallback。
3. request sequence 在執行前 consume，重複／過期 sequence 不再執行命令；回覆明確區分
   accepted/completed 與 transport failure。daemon 重啟造成 sequence 重設的 session policy
   必須明文設計，不能把舊 frame 誤認成新命令；初版可限制為同一次冷啟動、同一 daemon。
4. shell command 在 task context 執行一次，完成後由**同一 adapter、同一 native write route**
   送完回覆再 return。host failure 不觸發第二次 dispatch；若回覆遺失仍保持 unknown outcome。
5. 原廠 consumer 的 pending-buffer、short-packet、partial-read offset、USB reset／disconnect
   清理，由一個明確生命週期負責。不是靠改 `C31E3A08` 或 `C31E3974` 常數壓住另一 consumer。

如此才從來源消除「兩個高階 consumer 改同一 TRB 並各自生 reply」的設計。
callsite replacement 只是接入方式；**如果舊 worker 繼續 arm/wait，這個修復就沒有成立。**

## 4. 必須補足的證據及授權

下一步是離線設計／mock／instruction review，不是 live RAM 試寫：

- 驗證 native API 的實際 packet-length／short-transfer 行為；只知道 `read(64)` 回傳 64
  不足以排除後面還有一段同 transfer payload。明確處理 USB speed/MPS、split reads、ZLP、
  extra bytes、截斷 frame。buffer 大小及回覆 cap 不可沿用 PTP length 欄位任意擴張。
- 驗證 `C0033B3C` 的 caller stack、callee-save、正常返回及輸出 sink 生命週期；確認 shell
  dispatcher 在 usbTask context 呼叫的鎖與重入行為。先只開固定 version／已核准 read-only
  memory commands，不把任意 shell／echo／lens command 當成 transport smoke test。
- 枚舉 mode-5 active 時所有其他 EP82 bulk writers，包括 native queued-transfer task
  `C01E7BD0`（C01:138398–138468）是否仍有 producer；single owner 的斷言須包括這些來源。
  本轮沒有把「PTP response writer 不再由此 parser 觸發」升格為「所有 IN writes 皆被排除」。
- 對 replay、malformed frame、超時、reply send failure、disconnect、mode reconfiguration 做
  故障注入測試；不僅觀察沒有 `2003`，還要證明一次 accepted frame 至多一次 shell dispatch，
  且每個結果屬於唯一 seq。零 PTP 錯誤是必要但不充分的驗收條件。
- 確認專用 build 的 code/data 區與現有 loader、gyro、AF scratch 沒重疊；安裝前 data readback、
  ROM D/I-cache publication、舊 word 驗證、失敗／rollback 方案須另審。

**所需新授權**：先允許上述 transport 實作與離線測試；另行批准專用測試 build 的明確 code
range/callsite、boot／SD 部署與回復方式，以及非錄影、非移動的有界硬體測試。這些不包含
殺原廠 task、host reset、即時 endpoint MMIO、任意記憶體修改或任何 AF movement 的默示許可。
現有只讀／AF scratch 授權不自動涵蓋更換整個傳輸所有權模型。

## 5. 本次來源身分

| 路徑 | SHA-256 |
| --- | --- |
| `fpSup/fp_usb_shell/host/fpshd.c` | `0ef089fcc296a84016622e0bbf3e8a45a8f3852ef2c782a4b6fab58c29c8ed4f` |
| `fpSup/fp_usb_shell/camera/worker.S` | `8f53430545be444d63cf985515d39097134d54329e50e26d2767c206fab8bc45` |
| `fpSup/fp_usb_shell/patches.py` | `6c80ee504ebce5e4122d847249fd25051c14dca5d1b9344ce6cc0371087a4f9e` |
| `out/decomp/full/blk_c00.c` | `9bb8b762d86f951617792b912d1bd2f2d2581f587e159c54e68d974bdd015180` |
| `out/decomp/full/blk_c01.c` | `4b8d1d419598eb6e67b9cda963de99e724091959213b863bca787d99a529c2b9` |
| `out/decomp/full/blk_c04.c` | `f68b2ac76f71eea5250adf61ab996cbee63b392629d3bfe98dd59e543f795756` |
| `out/seg0_c0000000.bin` | `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622` |

以上是磁碟 source／binary 身分，不是從相機讀回的 live worker 身分。
