# fp AF Assist：USB 傳輸停頓審核

2026-09-16。前半為既存日誌、host／worker 原始碼及離線組譯審核；後續依使用者明確同意，
只更換本機 daemon 為記錄封包的診斷版並進行只讀 USB 試驗。未修改相機 worker、韌體、卡片或設定。
依 `fp-usb-shell` skill 保留未知 ownership、逾時不等於未執行、不得自行換 worker 的邊界。

## 已確認：兩次停頓發生在 bridge 啟用前

下表只計 `event=exchange`；12-byte 欄是 USB 回覆成功但長度為 `12/64`，不是 USB timeout。
成功往返中位數來自日誌 `elapsed_s`，不代表相機內部執行耗時。

| 原始日誌 | 交換數 | 12-byte 短回覆 | IN timeout | 成功中位數 |
| --- | ---: | ---: | ---: | ---: |
| [read-probe-a](../captures/2026-09-16-read-probe-a/events.jsonl) | 1460 | 17 | 0 | 0.292 ms |
| [small-step-a](../captures/2026-09-16-small-step-a/events.jsonl) | 238 | 2 | 6 | 0.302 ms |
| [small-step-b](../captures/2026-09-16-small-step-b/events.jsonl) | 2586 | 13 | 0 | 0.274 ms |
| [settled-h-a](../captures/2026-09-16-settled-h-a/events.jsonl) | 193 | 2 | 6 | 0.303 ms |

`small-step-a` 日誌第 234–239 行、`settled-h-a` 第 189–194 行是連續 timeout。
前者最後成功寫入 `C072F91C`，後者最後成功寫入／讀回 `C072F8E0`，下一個 `C072F8E4` 讀取開始逾時。
**這兩輪皆沒有 echo 指標寫入、echo 執行或 bridge call**：本輪尚未執行新 ARM，也未做 ROM cache
publication，不能將停頓直接歸因於本輪對焦函式或 cache helper。其他歷史因素仍未排除。

`frame0 TIMEOUT moved=0/64` 發生前，daemon 已成功完成命令 OUT transfer；它不證明 worker 已執行命令。
依據：[fpshd.c:196](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/host/fpshd.c:196)，
OUT 失敗在 198–203 行直接返回；IN frame0 等待與錯誤則在 230–242 行。

## 後續 pacing 證據：未再見 timeout，短回覆仍存在

以下只納入已有完成結果與完整收尾日誌的輪次；計數方式與前表相同。
`paced-reads` 各為 500 次 memory read 加一次版本查詢。

| 原始日誌 | 交換數 | 12-byte 短回覆 | IN timeout | 成功中位數 |
| --- | ---: | ---: | ---: | ---: |
| [paced-reads-a：10 ms](../captures/2026-09-16-paced-reads-a/events.jsonl) | 501 | 0 | 0 | 0.583 ms |
| [paced-reads-b：5 ms](../captures/2026-09-16-paced-reads-b/events.jsonl) | 501 | 0 | 0 | 0.548 ms |
| [settled-h-b-paced](../captures/2026-09-16-settled-h-b-paced/events.jsonl) | 1211 | 0 | 0 | 0.563 ms |
| [settled-h-c-paced](../captures/2026-09-16-settled-h-c-paced/events.jsonl) | 2054 | 1 | 0 | 0.578 ms |
| [settled-h-d-bracket](../captures/2026-09-16-settled-h-d-bracket/events.jsonl) | 1834 | 1 | 0 | 0.558 ms |

`b` 的失敗是 selector `FFFFFFFF` 超出當時 guard 的 0／1 支持範圍；`c` 是 observation 的
8 秒總截止、0 accepted／9 boundary-discarded samples，**兩者不是 USB timeout**。
`c` 第 1247 行短回覆發生於 `mem set C072F720 0`；`d` 第 1046 行為 `mem get C072F718`。
二者都屬 idempotent 記憶體路徑，不是 move／abort 重送；最後均有 scratch、echo、設定核對還原。
`d` 接受 3 筆靜止 H/L observation，但不證明曝光對齊或光學合焦。

現行 [Transport](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/focus_bridge.py:48)
預設一般交換完成至下次開始至少 5 ms；
[固定 H bracket](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/focus_bridge.py:113)
只省略四次指定 read 之間的三個間距，不開放任意高速命令。
`c` 的候選 bracket 約 18.22–21.93 ms，`d` 約 2.23–3.95 ms；這是不同取樣實作下的觀測，
不能把 `d` 當作所有交換一律 5 ms 的同條件重複。
較疏的流量下尚未重現先前停頓，是有用的有限樣本；**短回覆仍然出現，沒有證明 pacing 消除根因**，
亦不是隨機化或同負載的因果比較。完整結果與資料接受條件见 [驗證紀錄](VALIDATION_2026-09-16.md)。

## 封包與等待路徑

- 正常 framed SHL 回覆的 TRB 長度固定 **64 bytes**，見
  [worker.S:684](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/camera/worker.S:684)。
  12-byte 回覆不是此正常路徑預期的封包。原始 daemon 未保留內容；後續診斷版已確認兩筆為
  PTP SessionNotOpen response，見下節。此結論不倒推每筆歷史短回覆必定相同。
- 短回覆會立即結束本次交換，並以最多 8 次、每次 20 ms 的 IN 讀取清除殘留，見
  [fpshd.c:141](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/host/fpshd.c:141)、236–242。
  這條路徑可能連稍後到達的正確回覆一起清掉，因此 ERR 不證明 `mem set` 沒生效。
  正常完整 FPSH frame 另有 CRC 與 sequence 檢查（248–279）。
- worker 的 OUT wait literal 是 `50000`，IN 是 `300`；回覆處理後才回到下一輪重新 arm OUT。
  見 [worker.S:103](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/camera/worker.S:103)、
  114、323–334、482–525。**尚未證明這兩次停頓就是一輪「50 秒 OUT 等待」**，也未量測確切恢復時刻。
- `C01E4E80` 的 native wait 在 -4 路徑會呼叫 `C01E6EF8`；後者結束已配置的 endpoint transfers
  並呼叫 USB recovery。見 [blk_c01.c:135922](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:135922)、
  137705–137733。不是所有 timeout 都走此分支；沒有本輪 worker state，不能指定實際走了哪一條。
- daemon 的 `TMO` 分別套在每個 USB transfer，並非整次交換總截止；多 frame／stale frame 可能讓整次
  交換比 bridge 的 host deadline 更長。這是源碼限制，不是本次停頓已證實的原因。

## 離線排除範圍與未證實因素

使用現行 `armasm.assemble(camera/worker.S)` 離線組譯：**1608 bytes**，放在
`C072F050..C072F697`，到 `F700` 尚有 **104 bytes**。
SHA-256：`18f982ca9973496b0c7ab4afeb924134dff280c10342642cca61854806a72c5d`。
建置原本也有 [F700 邊界檢查](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/build_autorun.py:172)。
所以目前源碼不與 bridge scratch 重疊；**未比對正在執行的 worker bytes，不能由此證明 live build 相同**。

ROM `C000E91C` 是全 D-cache set/way maintenance，`C000EABC` 是 I-cache invalidation，見
[native control audit](research/FP_NATIVE_FOCUS_CONTROL_2026-09-16.md#instruction-cache-publication)。本審核沒有證實 DMA pool 的
MMU/cache 屬性或 dirty alias 狀態，故沒有證據把 pool corruption 指定為根因。

另有獨立 ABI 風險：`arm_out`、`arm_in_block`、`arm_in` 在呼叫 firmware 前各 push 5 registers
（worker.S:529、666、685）；由對齊的 `serve` 路徑進入時，這不維持 8-byte call-stack alignment。
值得另案審核，但**不是本輪停頓的已證實根因**；本次不改 worker。

## 可在原範圍內驗證的下一步

1. 持續 timeout 後停止新增動作並保持 quarantine；只在安靜等待後做有界、可核對位址的只讀檢查。
2. 恢復前確認 echo ownership、版本、capture idle，以及本輪保存的 scratch before-image；只還原已知自身改動。
3. 已完成上述 **5–10 ms 間距**只讀比較；後續保留 pacing 與逐筆錯誤證據，不能把零 timeout 推廣為無故障保證。
4. Idempotent write 失敗先讀回；不得重送不確定的 move／abort／echo execution。
5. 若仍失敗，下一個有價值的證據是原始 12-byte payload 與故障期間 worker state。
   更換 daemon、改 endpoint／worker 或重新部署需另外界定及取得權限，不屬於本次自動恢復。

實際 72-word／57-word 還原、被拒絕的取樣與後續一次成功觀測，見 [驗證紀錄](VALIDATION_2026-09-16.md)。

## 授權 host-only 診斷：兩筆 PTP SessionNotOpen

使用者同意停止本次由我們啟動的 daemon，換成只增加異常封包記錄的本機診斷版。
每次先核對原 echo、版本、capture idle、native-L identity、位置及四項設定，再送 host socket
`QUIT` 並確認 `OK bye`／process exit。未使用 native shell `quit`，未重新部署 worker。
原始 binary 保留；診斷版只記已收到的 bytes，不改封包接受規則或重送行為。

| 試驗 | 結果 | 原始封包 |
|---|---|---|
| [diag-a](../captures/2026-09-16-host-diag-a/readonly-brackets/result.json) | 23 個四讀 bracket 完成，首個錯誤即停 | `0c00000003000320c1000000` |
| [diag-b](../captures/2026-09-16-host-diag-b/readonly-brackets/result.json) | 2 個 bracket 完成，首個錯誤即停 | `0c0000000300032019000000` |

兩筆均是 little-endian length=12、type=3、response=0x2003，transaction 分別為 193／25，
吻合當時 FPSH sequence。0x2003 為 [PTP SessionNotOpen](https://raw.githubusercontent.com/gphoto/libgphoto2/master/camlibs/ptp2/ptp.h)。
[diag-a stderr](../captures/2026-09-16-host-diag-a/daemon-stderr.log)、
[diag-b stderr](../captures/2026-09-16-host-diag-b/daemon-stderr.log) 保留原 bytes。
diag-a 後續另有 500 次 paced read 完成；這不消除並行路徑的風險。

v2 額外記錄的是既有 drain read：首輪 20 ms 內 `rc=-7,moved=0`，沒有觀察到 FPSH 回覆。
**這不證明更晚沒有回覆，也不證明 shell 沒執行**。沒有加入 read-past、忽略 PTP 或重新傳送動作。
診斷輸出本身會影響 host 時序；不是零擾動的量測。

原生 `C04DC780` 有相符的 SessionNotOpen 產生分支；native USB 與 worker 使用相同 OUT／IN
TRB globals，vendor-class patch 不會關閉 native PTP task。這些是源碼事實；確切 live race 時序、
每筆歷史 timeout 成因及 exactly-once execution **尚未證實**。完整共通證據將保存在
[USB/PTP 路徑筆記](../../../research/interfaces/notes/FP_USB_PTP_SHARED_PATH_2026-09-16.md)。

## 後續取樣方案：固定 camera-side copy

`focus_snapshot.S` 為 152 bytes，放在既有授權範圍 `C072F740..F7D7`，不改 worker。
單次 nonce/op=9 copy phase/mode、H、L、phase/mode 至 `F724..F738`；不做鏡頭／USB／MMIO／等待操作。
host 全程保留 >=5 ms 間距，原四讀 burst 僅留作只讀診斷。
既有 gain/context、phase、settle、完成與精確還原規則仍保留，沒有將 helper 當成原子快照或曝光同步。
這降低取樣對密集傳輸的需求，**不是修復共享 endpoint 的證明**；實測狀態見驗證紀錄。

## 主機防護修正：異常恢復不恢復位移權限（離線驗證）

前述舊版允許 idempotent read/write 的有界修復；部分小步試驗因此在短回覆後仍繼續，
最後才由人為取消。新版本在 `Transport` 內新增單一實例生命期的 sticky health latch：

- socket／daemon ERR、超長／格式錯誤回覆、記錄失敗與最終 RAM 核對失敗均記為異常。
  後續成功讀取、核對修復或 cleanup 不清除它；異常數單獨累計。
- op7 在 preflight 前、準備請求前與真正 echo 前檢查。準備中即使有界修復成功，仍不得啟動位移。
- echo 尚未嘗試時的準備失敗記為 `MotionNotDispatched`（`NOT_DISPATCHED`），不虛構已擁有馬達動作，
  也不自動 abort。若已嘗試 echo 後失敗，仍是 uncertain execution，保留 quarantine，不能重送。
- 只讀／完成檢查、已擁有動作的一次 stop、精確核對還原仍可使用；所有原有 ownership 與 quarantine
  限制不變。恢復通訊不是允許再對焦，stop ACK 也不是物理停止證明。
- 原廠 S1ON 在 preflight 前後均檢查 latch；未嘗試 S1ON 不發出多餘 S1OFF；一旦嘗試 ON，原有
  finally release 仍執行。原廠 AF 仍只能明確另選，不作自動 fallback。
- `CameraService` 將 `transport_faulted`、`transport_anomaly_count` 存入結果，任何收尾異常也會
  將該 job 與 service 鎖為 fault；若演算法原先已返回，保留 `status_before_transport_fault`。

新 ERR 在 host 事件中為 `exchange_uncertain`（error 包含原始 daemon reply），不再是舊版的
`exchange` + ERR reply。比較新舊日誌須同時計兩種事件，**不重写舊實測檔**。
`exchange_uncertain` 是 host 無法確認此次交換，不代表每種命令都曾執行。

新增 31 項 transport/dispatch 測試與 4 項 service/native-AF 測試；本專案 308 項離線測試通過。
測試以替代 socket、模擬鏡頭與 loopback HTTP 覆蓋；**沒有在相機重跑，也沒有修復共用 USB 路徑**。
鎖只存在於該 transport／service，重開程式不是硬體復原方式。新 hook 亦不解除此控制通道問題。
