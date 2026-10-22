# SIGMA fp USB：PTP SessionNotOpen 回覆與 FPSH 共享傳輸路徑

日期：2026-09-16。正式分類：`research/interfaces/notes/`。
目標版本：SIGMA fp `w71c1 / 5.02.0.V91 / 13aa621060efff11aaba9b21ad925005302605cf`。
本筆記是既存日誌與原始碼的離線審核；撰寫時沒有操作 USB、相機、worker 或 SD 卡。
事故與原始素材仍留在發生它的 AF-assist 工作區；本篇保存可跨專案使用的協定與所有權限制。

## 結論及證據等級

| 等級 | 可支持的結論 |
| --- | --- |
| 確證：封包 | 兩次 12-byte 回覆均可精確解碼為 PTP response `0x2003`；transaction ID 分別等於當次 FPSH sequence 193、25。它們不是有效 FPSH ACK。 |
| 確證：靜態源碼 | 原廠 PTP 與 shell worker 使用相同 bulk endpoint/TRB table；改 USB interface class 不等於移除原廠 USB task。 |
| 強候選：產生路徑 | `C04DC780` 的「session 未開」分支會產生完全相同格式，且 FPSH sequence 與 PTP transaction ID 位於相同 offset。 |
| 尚未證實 | 實際命中的 producer、哪個 task／哪次完成事件造成交錯、誰先後看見哪些 buffer，以及同筆 shell 是否執行。 |
| 尚未證實 | 短回覆解釋了所有歷史 timeout、cache corruption、固定 50 秒恢復，或 pacing 已消除根因。 |

**PTP 拒絕不是 shell 未執行的證明；USB OUT 成功也不是 shell 執行 ACK。**
沒有有效、可對應且內容核對完成的 FPSH 回覆時，命令結果仍不確定；不能因此重送非冪等動作。

## 1. 兩次保存的 12-byte 封包

兩輪失敗的請求都是只讀 `mem get 0xC32985E8,,0x4`。未送鏡頭位移。

| 日誌 | 當次 tx sequence | 接收 bytes | 解碼 |
| --- | ---: | --- | --- |
| [host-diag-a stderr](../../../projects/fp-af-assist/captures/2026-09-16-host-diag-a/daemon-stderr.log)，第 2 行 | 193 | `0c00000003000320c1000000` | length 12、type 3、response `2003`、transaction 193 |
| [host-diag-b stderr](../../../projects/fp-af-assist/captures/2026-09-16-host-diag-b/daemon-stderr.log)，第 2 行 | 25 | `0c0000000300032019000000` | length 12、type 3、response `2003`、transaction 25 |

這兩次 frame receive 都是 `rc=0`、`moved=12`、`expected=64`：USB transfer 成功收到短封包，
不是該次 IN transfer timeout，也不是已通過 FPSH framing／CRC 的回覆。

- diag-a：完成 23／100 個只讀 brackets，193 次 exchange；最後一筆短回覆後停止。
  [結果](../../../projects/fp-af-assist/captures/2026-09-16-host-diag-a/readonly-brackets/result.json)、
  [events](../../../projects/fp-af-assist/captures/2026-09-16-host-diag-a/readonly-brackets/events.jsonl) 第 216 行。
- diag-b：完成 2／100 個只讀 brackets，25 次 exchange；最後一筆短回覆後停止。
  [結果](../../../projects/fp-af-assist/captures/2026-09-16-host-diag-b/readonly-brackets/result.json)、
  [events](../../../projects/fp-af-assist/captures/2026-09-16-host-diag-b/readonly-brackets/events.jsonl) 第 27 行。
- diag-a 另有 500 次、5 ms pacing 的 memory reads 完成（加版本查詢為 501 次 exchange，0 ERR）。
  [paced-read 結果](../../../projects/fp-af-assist/captures/2026-09-16-host-diag-a/paced-reads/result.json)、
  [events](../../../projects/fp-af-assist/captures/2026-09-16-host-diag-a/paced-reads/events.jsonl)。
  不同負載的有限樣本不能證明短回覆已修好。

## 2. diag-b 的 drain：20 ms 窗口沒有收到後續資料

diag-b stderr 第 3 行記錄原有 `drain_in()` 的第一次 transfer：

```text
seq=25 drain_iteration=0 rc=-7 moved=0 expected=16384 captured=0 hex=
```

`rc=-7` 是 libusb timeout；`expected=16384` 是接收 buffer 容量，不是預期必須到達的回覆長度。
該 drain 的原始 timeout 設為 **20 ms**；frame 與 drain 兩行 `MONOTONIC_RAW` 時戳相差約
**21.023 ms**，不可將這個含記錄／呼叫開銷的差值當成相機處理時間。
本次零 byte timeout 後，原有 loop 立即結束，沒有觀察到可匹配 sequence 25 的 FPSH frame。

因此本次**不支持「drain 丟掉了同筆正常 FPSH 回覆」**；也不能由這個短窗口推論更晚不會到達、
worker 沒有執行、或 native PTP 是唯一消費者。diag-a 沒有 drain payload 記錄，不能補推其內容。

v2 只在原有 drain transfer 後加 stderr 記錄，20 ms、最多 8 次及停止條件未改，沒有新增 USB
transfer、重試或封包接受規則。見
[v2 patch](../../../projects/fp-af-assist/diagnostics/fpshd-drain-log-v2.patch) 與
[v2 原始碼](../../../projects/fp-af-assist/diagnostics/fpshd-diagnostic-v2.c)，L217–229。
stderr 本身可能擾動時序；這不是零干擾量測。
[離線測試說明](../../../projects/fp-af-assist/diagnostics/README-v2.md) 的「PTP 後接有效 FPSH」是 mock fixture，
**不是相機實測**，不得拿來填補本次未收到 FPSH 的證據。

## 3. 原廠 SessionNotOpen producer：精確匹配，但尚無動態 call trace

[blk_c04.c](../../../out/decomp/full/blk_c04.c) 中：

1. `C04DC780`，L166066–166069：解出 container length、`+4` type、`+6` opcode、`+8` transaction ID。
2. L166096–166112：session slot `C377390C` 未開，且 opcode 不是 `1001`／`1002` 時，直接呼叫
   `C04E8F70(0xC, 0x2003, transaction_id, 0)`，返回 6。
   `1002` 成功分支在 L166166–166175 保存 session ID，支持 `2003` 的 session-not-open 語義。
3. `C04E8F70`，L174184–174219，經 `C04DBE28`／`C04DC248` 走 response 路徑。
4. `C04DC308`，L165866–165878：寫入 little-endian length、type 3、response code、transaction ID；
   L165909 再交 `C04DC0F8` 發送。長度 12 時不附加參數。

FPSH 的布局見 [fpshd.c](../../../fpSup/fp_usb_shell/host/fpshd.c)，L44–55、180–189：

| Offset | FPSH framed SHL | PTP parser 解讀 |
| --- | --- | --- |
| `+0` | `FPSH` magic | container length（不是合法的該筆 PTP 長度） |
| `+4` | version 1、command 3 | type `0301`（不是 PTP command type 1） |
| `+6` | flags，這些 framed requests 為 0 | opcode 0，不是 `1001`／`1002` |
| `+8` | request sequence | transaction ID |

上列 native session guard 之前，該函式沒有先拒絕 type／length 不合法的檢查。
**如果 FPSH header 到達這個 parser**，未開 session 分支可以產生觀察到的 `2003 + 相同 ID`。
但進入該 parser 的上游接收／拷貝狀態仍需動態證據，不能把欄位匹配升格為完整競態重建。

## 4. 共享的是端點、TRB 與 driver 狀態，不是已證實的獨佔消費

- 現行 EP01 OUT／EP82 IN 分別使用 logical 1／2、physical 2／5；worker 使用
  TRB pointer slots `C31E3268`／`C31E326C`。
  [worker.S](../../../fpSup/fp_usb_shell/camera/worker.S)，L85–101、546–565、685–703。
- Native `C01E7080` 以 `C01E60E0` 選 bulk OUT，寫入
  `C31E3264 + logical_endpoint*4` 指向的 TRB，再 StartTransfer／Wait。
  [blk_c01.c](../../../out/decomp/full/blk_c01.c)，L137827–137850。
- Native `C01E5320` 以 `C01E6110` 選 bulk IN，寫同一個 TRB table，再 StartTransfer／Wait。
  同檔 L136235–136281；endpoint selectors 在 L137073–137101。
- Native `C01E7780` 的 completion handling 更新共享 `C31E3974`／`C31E3A08`，
  並可將 OUT TRB 再指向 native buffer `[*C3025744]`。
  同檔 L138236–138251。worker 則從 `[*C3757A7C]` 取得自己的 frame pool。
  **這不表示兩個 payload buffers 已被證實相同**；被證實共用的是 TRB／endpoint／driver state。
- 原廠 `usbTask` 在 `C0033B80` 等候 USB 事件，mode 5 經
  `C0033AD0 → C04DB778 → C04DC780` 進入 PTP receive/parser。
  [blk_c00.c](../../../out/decomp/full/blk_c00.c)，L42687–42703、42720–42768；
  [blk_c04.c](../../../out/decomp/full/blk_c04.c)，L165419–165444。
  靜態路徑存在不等於已量到事故當刻是哪個 PTP／PTS task 在運行；也不能與 native lens-control
  worker 僅因名字近似而視為同一 task。
- [patches.py](../../../fpSup/fp_usb_shell/patches.py)，L18–24，將 interface class 改為 vendor-specific，
  目的在阻止 host PTP stack 搶 interface；它沒有停用相機端 PTP task。
  `fpshd.c` 開頭「class handler removed／bulk pipes belong to us」的歷史註解，
  不能覆蓋目前 patch 與 native source 的反證。

以上足以否定「換成 vendor class 就取得相機端獨佔通道」的假設；尚不足以判斷該筆 OUT
只被 native PTP 看見、只被 worker 看見、被拷貝後兩邊皆看見，或 IN reply 被後續重設取代。

## 5. 不重播、不推定 ACK：可保留的 host 診斷方向

現在的 daemon 在短 frame 後 drain 並返回 ERR；見
[fpshd.c](../../../fpSup/fp_usb_shell/host/fpshd.c)，L230–242，drain 在 L141–161。
若另行核准做 host-only「讀過 stray PTP、等待 FPSH」實驗，應限於固定只讀命令：

1. **只發一次 OUT；不重播同筆命令。** 不送 OpenSession、改 session flag 或以 native PTP 回覆推定 shell 成敗。
2. 只針對明確格式的 framed read path；設定小的 IN skip 次數上限和單一絕對截止，
   不因每收到一個封包就重置期限，不套用到 raw-block／寫入／對焦控制。
3. 保存每個 stray packet。只有完整 FPSH magic/version/CRC/sequence、command/status、
   預期 payload 與讀取位址全部匹配，才可接受該次讀取；PTP response 本身永不作為 FPSH ACK。
4. 未知封包、錯誤或期限到達即停止，結果為 uncertain；保留 ownership/quarantine 規則。
5. 若日後**同一 OUT、沒有重送**之後真的看到 PTP 再接 matching FPSH，才支持該個案可以讀過
   stray response；diag-b 目前沒有這項證據，不能預先當作有效修復。

即使得到 matching FPSH，仍非 exactly-once 保證：[worker.S](../../../fpSup/fp_usb_shell/camera/worker.S)
L336–373 在讀 frame 後主要檢查 payload 的 `shl ` 前綴，沒有先驗證 incoming FPSH
magic/version/CRC/sequence，也沒有 request 去重機制；L467–479 以原 frame header 重建回覆 CRC。
它可支持符合該 header 的回覆已產生，不能單獨排除重複執行，更不能證明鏡頭實際完成或光學合焦。

## 6. 可重查的源碼身分

下面是此次離線核對的 SHA-256；不是從相機讀回的 live worker 身分證明。
所有行號以這些檔案版本為準。診斷二進位與 mock provenance 另見
[v1](../../../projects/fp-af-assist/diagnostics/README.md)、
[v2](../../../projects/fp-af-assist/diagnostics/README-v2.md)。

| 檔案 | SHA-256 |
| --- | --- |
| `fpSup/fp_usb_shell/host/fpshd.c` | `0ef089fcc296a84016622e0bbf3e8a45a8f3852ef2c782a4b6fab58c29c8ed4f` |
| `fpSup/fp_usb_shell/camera/worker.S` | `8f53430545be444d63cf985515d39097134d54329e50e26d2767c206fab8bc45` |
| `out/decomp/full/blk_c00.c` | `9bb8b762d86f951617792b912d1bd2f2d2581f587e159c54e68d974bdd015180` |
| `out/decomp/full/blk_c01.c` | `4b8d1d419598eb6e67b9cda963de99e724091959213b863bca787d99a529c2b9` |
| `out/decomp/full/blk_c04.c` | `f68b2ac76f71eea5250adf61ab996cbee63b392629d3bfe98dd59e543f795756` |
| `projects/fp-af-assist/diagnostics/fpshd-diagnostic.c` | `36041ca0ebb685790e519ac1dbc2a1a43b043e8da75ba6075242766524449c34` |
| `projects/fp-af-assist/diagnostics/fpshd-diagnostic-v2.c` | `ec28e7c740c44b4186333e9da6e17b00be16914bf12b502f4330e65005bea729` |

維護提示：交接位置與正式目的地同為 repo 根以下三層，本文 `../../../` 相對連結可直接搬移。
原始 captures 與 diagnostics 由主線歸檔至 `projects/fp-af-assist/`，本篇連結亦同步更新。
不要為配合敘述而改寫原始 logs。後續新證據可修正「未知／候選」，但不可追溯宣稱本次已證明。

## 補充 2026-10-06:UP01 上重現

v3 載入的 shell(`projects/usb-shell-sup/notes/LOADER_V3.md`)、worker 改用韌體 crc32 之後,每次 16,320 B PUT
約 9-13 ms;連續 PUT 在第 59 次、第 20 次各撞到一次:

```text
upload ack uncertain rc=0 moved=12 head=0c000000.03000320.2c000000
```

同樣是 PTP response `0x2003`(Session Not Open),transaction ID `0x2C` = 當次 FPSH sequence 44。
之後 worker 卡在 OUT 等待,約 50 s(`TIMEOUT`)後自己恢復;worker 計數器 `faults` 累積到 135。
→ 原廠 PTP 任務吃掉 shell 的 OUT 這件事,在大量、密集的上傳時一樣發生,頻率約 1/20~1/60 PUT。
daemon(`host/fpshd.c` upload ack)現在會把短回覆的前 12 B 印進錯誤訊息。仍未查明觸發點(第 3 節的 `C01E7080`)。
