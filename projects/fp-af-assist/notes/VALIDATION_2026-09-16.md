# fp AF Assist：驗證紀錄

2026-09-16，SIGMA fp w71c1 / 5.02.0.V91 / 13aa621060efff11aaba9b21ad925005302605cf。
使用者明確同意借用 echo `C0BAC2F8` 與 `C072F700..C072F9FF`，非錄影小位移、完成／停止、
讀回驗證及結束還原；不改韌體或 SD 卡。

## 只讀 bridge：通過

證據：[read-probe-a](../captures/2026-09-16-read-probe-a/result.json)。
兩次取得相同 cached position 10707、native min/max 5974/11116、focus event 3、sync event 1，
native-L selector/vtable 正確。真正五個 capture bytes 為 idle，full shutter gate 為 0，AF route 14。
ROI `448 277 128 128`、focus mode 0、area 0、size 3。
scratch 192 words、echo 與四個設定均已讀回還原。

這也確認舊 `C3033A54=1` 不是實際 shutter gate；正確 `C3033A6C=0`。
透過既有 ROM 先 D-cache `C000E91C`、再 I-cache `C000EABC`，才第一次執行已讀回的 ARM。

## Small-step-a：中斷，沒有移動

證據：[原始結果](../captures/2026-09-16-small-step-a/result.json)、
[逐筆交換](../captures/2026-09-16-small-step-a/events.jsonl)。
載入到 `C072F91C` 時連續讀取逾時，後續 cleanup ownership 也無法確認；停止測試。
整份日誌**沒有任何 echo 指標切換、echo 執行或 native bridge call**，所以沒有送出位移命令。
原始結果的 `quarantined=false` 是當時只追蹤「呼叫逾時」的欄位，不代表 cleanup 成功；
後續程式已將 cleanup failure 也標成 quarantine，並分開記錄 `cleanup_complete`。
保留原始結果，不以新解讀覆寫它。

暫停後版本只讀查詢恢復；確認 echo 仍為 `C03D99A0`、鏡頭 10707、capture idle。
以保存的 before-image 比對每個字組，只接受原值／本次載入值後還原 **72 words**。
[recovery result](../captures/2026-09-16-small-step-a-recovery/result.json) 證明 scratch、echo、設定
全部核對一致。沒有重啟相機、改卡、清 flag 或用 AF 解救 transport。
中斷的根本原因尚未證明；後續能通訊不等於已找到或修好根因。

## Small-step-b：20-pulse 控制與 native stop 流程通過

在連線恢復、before-image 已還原、位置與 idle 條件重新確認後建立另一輪，
不是重送不確定的位移命令。
證據：[結果](../captures/2026-09-16-small-step-b/result.json)、
[原始交換](../captures/2026-09-16-small-step-b/events.jsonl)。

| 階段 | 證據 |
|---|---|
| 起點 | 10707，min 5974、max 11116 |
| 第一小步 | 10707 → 10687；native drive return 1 |
| 完成 | focus flag 2 → 3，cached position 10687，重讀穩定 |
| 返回／停止測試 | 10687 → 10707；native drive return 1 |
| stop 前 | host 曾觀察到 focus flag 2 |
| stop call | operation 8，native return 1（abort request accepted） |
| stop 後 | focus flag 3，cached position 10707，重讀穩定 |
| 收尾 | scratch、echo、設定全部核對還原；capture idle、route 14 |

原始結果中的 `stop_test_interrupted_active_move=true` 應限縮解讀為：host 曾看到 native busy，
且後續 abort 被接受。它**沒有光學地證明馬達在移動中被截停**，更不是獨立物理位置量測。
新程式已改用 `native_busy_observed_before_stop`、`native_abort_accepted`，並明確保留
`optical_motion_interruption_verified=false`。

本輪日誌有 13 次記憶體讀／寫交換 ERR，透過有界 idempotent readback 路徑處理；
三次 native move/abort call 都得到可核對 nonce／return 的結果，沒有重送動作。
這仍是一個有已知傳輸不穩定風險的研究版本，不是無人值守相機控制系統。

## Settled-H-a：取樣前中斷，57-word 未啟用載入已還原

證據：[失敗結果](../captures/2026-09-16-settled-h-a/result.json)、
[原始交換](../captures/2026-09-16-settled-h-a/events.jsonl)。
載入最後成功寫入／讀回 `C072F8E0`；下一個 `C072F8E4` 讀取與後續 echo ownership 檢查
共六次 IN timeout。整輪沒有 echo 指標寫入、echo 執行或 bridge call，故沒有進入 H observation
或送出位移命令。結果正確保留 `cleanup_complete=false`、`quarantined=true`，不能算取樣成功。

暫停後，另以保存的 before-image 比對並還原 **57 個 scratch words**。
[recovery result](../captures/2026-09-16-settled-h-a-recovery/result.json) 及
[recovery events](../captures/2026-09-16-settled-h-a-recovery/events.jsonl) 記錄 scratch、echo、
四個設定均已核對一致，`lens_motion_requested=false`。
恢復前 `C30338C8` 四個 busy bytes 全零，`C30338D0` 的 MovieRecording **低 byte** 為零，
`C3033A6C` full shutter gate 為零；不可把 `C30338D0` 整個 word 的 `0x00010000` 當成 recording。
恢復日誌仍有四次 12-byte 短回覆，經 idempotent readback 路徑完成；不是傳輸根因已修復。
原始失敗結果與日誌均保留，不以 recovery 成功覆寫。

源碼／封包與 pacing 待驗假設另見 [傳輸審核](TRANSPORT_AUDIT_2026-09-16.md)。

## Paced reads：10 ms／5 ms 各 500 次完成

兩輪皆為既有 shell 的只讀診斷，各含 500 次 memory read 與一次版本核對，
所以日誌各有 **501 次 exchange、0 ERR、0 timeout**。
[10 ms 結果](../captures/2026-09-16-paced-reads-a/result.json)、
[10 ms 日誌](../captures/2026-09-16-paced-reads-a/events.jsonl)、
[5 ms 結果](../captures/2026-09-16-paced-reads-b/result.json)、
[5 ms 日誌](../captures/2026-09-16-paced-reads-b/events.jsonl)。
間距是 host 設定，不是相機採样率；此有限樣本支持繼續有界測試，**不證明傳輸根因已修復**。

## Settled-H-b-paced：傳輸完成，selector guard 拒絕

[結果](../captures/2026-09-16-settled-h-b-paced/result.json)、
[日誌](../captures/2026-09-16-settled-h-b-paced/events.jsonl)：1211 次 exchange，0 ERR／timeout。
第 725 行讀得 timing selector `C2F14A38=FFFFFFFF`，當時只接受 0／1 的 guard 於第 728 行拒絕；
這是軟體支持範圍不足，不是本輪 USB timeout，也不應將該值擅自改成 0 或 1。
沒有接受任何 H observation、沒有位移；scratch、echo、四項設定均確認還原，
`cleanup_complete=true`、`quarantined=false`。

## Settled-H-c-paced：8 秒截止，跨 scheduler 邊界的 9 筆全數捨棄

[結果](../captures/2026-09-16-settled-h-c-paced/result.json)、
[日誌](../captures/2026-09-16-settled-h-c-paced/events.jsonl)：2054 次 exchange，
**一次 12/64 短回覆、0 USB timeout**；短回覆在第 1247 行的 idempotent scratch 清零寫入，
不是位移或 native call。取樣的 8 秒總截止於約 8.007 秒觸發，應與 USB timeout 分開記錄。
觀察到 28 次 scheduler phase 變化，9 筆候選的前後 phase 均不同，因此全以
`visible_phase_boundary` 捨棄；**接受樣本數為 0**。
即使 H 非零或看似穩定，也沒有提升為有效對焦資料。
全程沒有位移，收尾 scratch、echo、設定核對還原；`cleanup_complete=true`、`quarantined=false`。

## Settled-H-d-bracket：三筆符合規則的靜止 H/L 觀測，已還原

僅在結果檔完成且末筆事件為 `lease_restored` 後納入。
[結果](../captures/2026-09-16-settled-h-d-bracket/result.json)、
[日誌](../captures/2026-09-16-settled-h-d-bracket/events.jsonl)：1834 次 exchange，
一次 12/64 短回覆（第 1046 行的 scratch 讀取）、0 USB timeout。
固定四次只讀 bracket 內不插 pacing，前後一般交換仍維持間距；本輪 bracket 約 2.23–3.95 ms，
接受 3 筆、捨棄 0 筆，整次 observation 約 6.499 秒。

| cached position | H | L | 前／後 scheduler phase |
| ---: | ---: | ---: | --- |
| 10707 | 20798 | 49542 | 1 / 1 |
| 10707 | 20781 | 49576 | 0 / 0 |
| 10707 | 20847 | 49619 | 2 / 2 |

H 中位數 20798、相對全距約 0.317%；L 中位數 49576。
三筆均通過當時的 gain/context guard，gain `[117,985,131,0]`、起終 cached position 均為 10707，
capture idle；scratch、echo、設定全部還原，沒有送出位移。
**phase 前後相等不排除完整繞一圈，亦不是原子 snapshot／曝光對齊證明**；
結果仍保留 `optical_focus_verified=false`、`exposure_alignment_verified=false`、`usable_for_dfd=false`。
這是取樣路徑的一次成功，不是光學合焦、對焦改善或長期穩定性的驗證。

## 整體 AF 流程

整合取消試驗 [assist-cancel-a](../captures/2026-09-16-assist-cancel-a/2026-09-16-072509-850892-assist/result.json)
原定第一筆有效觀察後取消；實際在取得該筆觀察前因 `12/64` USB 短回覆失敗。
**沒有送出位移**，控制器回傳 fault，不自動切換原廠 AF。
無 owned movement，stop 只確認 focus flags=3、cached position=10707，沒有呼叫 native abort。
`cleanup_complete=true`，RAM／echo／設定已核對還原。
這驗證了取樣失敗的安全退出，**不是取消成功或完整 AF loop 通過**。
當時先暫停新增硬體動作並請求本機 daemon 診斷權限。後續使用者明確同意 host-only 替換，
已完成只讀診斷，兩筆短回覆為 PTP SessionNotOpen；沒有修改 worker，見[傳輸審核](TRANSPORT_AUDIT_2026-09-16.md)。

已取得一次 scheduler-progress-checked 靜止 H 觀測；完整 bounded contrast loop 仍待實機測試。
離線控制器測試不當作硬體精度、光學合焦率或速度提升證据。

## Camera-side fixed copy：靜止取樣與動作前取消通過

`focus_snapshot.S` 152 bytes，SHA-256
`d3b3d49d8799c85a796ddb80ab5102e8058feedb41362173f8ac822a0dda37cd`。
入口 `C072F740`、最後 byte `F7D7`，與 504-byte control `F800..F9F7` 不重疊。
仍使用原核准的完整 `F700..F9FF` lease；不是常駐 hook，也沒有改 worker。

[settled-h-e-camera-copy](../captures/2026-09-16-settled-h-e-camera-copy/result.json)：
2,168 次 exchange，0 ERR／uncertain；3 筆 H=7954、7939、7985，L=31496、31454、31416。
H 中位數 7954、相對全距 0.578%，observation 7.662 秒。
copy 前後 phase 為 2/2、2/2、1/1；RPC 約 304–318 ms，**不是 ARM copy 執行耗時**。
起終位置 10707、capture idle、gain/context/settings 一致；scratch、echo、設定核對還原。

[assist-cancel-b-camera-copy](../captures/2026-09-16-assist-cancel-b-camera-copy/2026-09-16-081015-394496-assist/result.json)：
第一筆有效 initial observation 後取消，`status=cancelled`、0 move／abort，位置 10707。
2,240 次 exchange 中有 2 次 12-byte PTP response，均是 idempotent read，經有界重新讀取成功；
沒有重送 echo 或動作。所有 RAM／echo／設定已还原。這是動作前取消通過，不是完整 AF loop。

## Assist-loop-a-camera-copy：部分小步成功，人工取消，未驗收

[結果](../captures/2026-09-16-assist-loop-a-camera-copy/2026-09-16-081053-266293-assist/result.json)、
[逐筆日誌](../captures/2026-09-16-assist-loop-a-camera-copy/2026-09-16-081053-266293-assist/events.jsonl)。
在主線分析到短回覆仍反覆出現後，送一次 SIGINT 給本次驗證程序，走現有 cancel/close 流程；
沒有強制終止 USB daemon 或相機 worker。停止動作不是即時的。

| 順序 | 完成位置 | 已接受 H 中位數 |
|---|---:|---:|
| initial | 10707 | 7952 |
| probe | 10757 | 9975 |
| probe | 10657 | 6126 |
| extend | 10757 | 9895 |
| 取消時最後一小步 | 10807 | 未取樣／未最後確認 |

四次 op7 都收到匹配 nonce/state/native return=1；各次原生完成旗標與 cached target 均核對。
最大離起點 +100、每步不超過100；沒有任何 op8、自動回原位或原廠 AF。
7,412 次 exchange 有 6 次 12-byte 回覆、0 exchange_uncertain，錯誤均保留在原始日誌。
結果為 `fault: cancelled after native stop/completion`，不能重寫為 completed；停止檢查
`native_done=true,position=10807`。`cleanup_complete=true`，scratch／echo／四項設定已還原。
**鏡頭留在 10807，不是起點 10707**；不是獨立光學停止驗證，也沒有最終 contrast confirmation。

慢速 copy 解決了四筆高速 USB bracket 的需求，但沒有消除 PTP 短回覆。
不再進行新的鏡頭試驗或把目前版本標成實機完成。下一方向是離線審核統計發布 hook＋
camera-side buffer；新 hook 的位址、buffer 所有權、執行脈絡與還原需要單獨確認／授權。

## 小步試驗後的離線防護修正

已在主機 transport、bridge 與 service 加入「任何傳輸異常後禁止新動作」的單輪鎖，
包含成功重讀／核對修復後與 cleanup 才出錯的情況。原廠 AF 啟動同受限制；已嘗試半按的
釋放、已擁有動作的停止與完成檢查不因健康鎖單獨被禁用，仍服從 quarantine。
位移 echo 尚未嘗試的錯誤與已嘗試後結果不確定分開，前者不發 abort。
細節見[傳輸防護修正](TRANSPORT_AUDIT_2026-09-16.md#主機防護修正異常恢復不恢復位移權限離線驗證)。

本專案以 `/usr/bin/python3 -B -m unittest discover -s . -p 'test_*.py' -v` 執行
**308 tests，全部通過**；新增 35 項回歸測試，不含 `diagnostics/` 的 4 項獨立測試。
診斷目錄 4 項亦另行通過。新嚴格 memory parser 離線重播現有 18 個 `events.jsonl` 中
18,849 筆成功 memory replies，零格式拒絕；這只確認對既有資料的相容性，不是新 USB 試驗。
這是 mock／loopback／本機組譯檢查，沒有 USB、鏡頭操作或新 hook 部署。
不將新增保護倒推套用於上一節四步實測，也不改寫其 fault、位置或 cleanup 紀錄。
