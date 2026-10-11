# CINE AF 多接點 USB 串流：事件清單與證據缺口

2026-09-27。依目前方向，優先建立「機內多個 hook → 有界緩衝 → 獨立 sender → USB 主機記錄」的研究通道；主機不參與正式 AF 控制。本文件只盤點既有程式與來源，沒有相機 I/O、ARM 程式修改、部署或新增固定 patch。

**五個現有 recorder 來源可以作第一個串流增量，但不足以重建完整 CINE 對焦因果。** 缺少 request／decision、實際採用 ROI、lens begin／abort、AAT 初始化／失效，以及共同時間。新優先順序是先讓這些來源可關聯並可靠送出，再用 trace 決定 AAT、幾何與 DFD 的改動。下列頻率皆為設計策略，沒有宣稱已量到 Hz、USB 吞吐或 hook 成本。

## 1. 五個既有來源：已驗證的是哪一層

「已核對」表示指定 ROM 的 callsite／ABI 或既有離線 recorder 已核對；不表示目前 CINE 路徑必達、可直接安裝、已取得 RAM／DMA ownership，或已完成硬體驗收。四來源的 ROM 身分與精確原字組在 [native_hook_sites.json](../../../fpSup/focus/geometry/native_hook_sites.json)，語意見 [native hook 稽核](geometry/NATIVE_HOOK_PLAN.md)。

| 事件／既有接點 | 已有實作與可保存內容 | 仍不能聲稱 |
|---|---|---|
| `af_terminal_pre_forward`；`C028E310 → C022B720 → C028E314`，原 callback **前** | `native_observer.S` source 1；172-byte payload、error byte `C329160B`、AF manager position `C32914E0`、native counter `C33D51FC` | 此特定 single-AF terminal 已涵蓋 CINE full-time CAF；terminal 一定成功；成功等於 final lens end；counter 等於 episode 或曝光序號 |
| `native_l_final_event_set_return`；`C0340458 → C036D758 → C034045C`，返回後 | source 2；F=`C3476414` 的 92 bytes、原 event-set return；含 cached position、mode、abort-pending、backlash 與未解參照 sync pointer | 位置是連續馬達／光學真值；已清掉的 abort byte=0 代表沒有取消；event-set 可能排程其他 task，返回後讀值並非完成瞬間的原子快照 |
| `face_parser_publication_return`；`C05AB348 → C05A9900 → C05AB34C`，返回後 | source 3；group0=`C37CCAAC` 的 156 bytes，加 publication gate／found／parser state | 每次 call 都是新影格、group0 是 AF 所選臉、native ID 永久不重用、此框已被 AF 採用；部分分支會延用／清除狀態 |
| `aat_color_run_return`；`C05AB8C8 → C05B6CF8 → C05AB8CC`，返回後 | source 4；signed return、`C37CDFA8` 的 44-byte model、Run／GetResult state、cache-dirty raw | 包含 SetTarget／reseed；return 0 是可信尺度；return −1 一定未更新模型；此接點不含 `C05B6C60` 的初始化／reseed Run 呼叫 |
| `af_hl_publication_return`；`C022C858 → C023E9D0 → C022C85C`，返回後 | `highrate/af_publication.S`；128-byte record，area-0 H/L、scheduler phase／mode、chosen/reference area、route、gain／exposure／ROI context、cached lens 與獨立 AF-manager position | H/L 一筆等於新曝光；area0 一定是被採用區；兩種 position 等於曝光位置；此既有受控 decoder 可直接用於錄影 CAF |

四來源使用每來源 **40-byte state + N×256-byte record**，各自有限陣列；已保存完整 register／APSR，額外 wrapper frame 64 bytes，單次 exclusive 嘗試、忙碌即放棄，只有 **sticky loss flag**。既有 decoder 只讀已停用、無 busy 的 finite snapshot；沒有 streaming consume／reuse 協定。見 [recorder](../../../fpSup/focus/geometry/native_observer.S)、[decoder](../../../fpSup/focus/geometry/observer_decode.py)。

H/L 使用 **64-byte state + N×128-byte record**，single-scheduler writer、滿後停用；它沒有記錄滿載後略過了幾次 publication，也沒有 common clock。既有驗證只接受 area0、route14、特定 scheduler modes 及非錄影／非持有 S1 條件；CINE 串流需要獨立 raw schema 與狀態解讀，不能刪掉舊 guard 就宣稱通過。見 [H/L recorder 契約](AF_HIGHRATE_RECORDER_CONTRACT_2026-09-16.md)。

## 2. 最小事件集合與優先層級

層級表示上線次序與壅塞保留優先級。T0 是關聯事件，不應固定每 N 次才記；T1 是判讀所需的連續訊號；T2 才是較大量的診斷明細。既有五點先接成可解碼的 transport smoke test 時，缺少的 T0 必須在 session header 列出，不能稱作完整 CINE causal trace。

| 層級／事件 | 最小內容與記錄方式 | 現有來源／尚需稽核 |
|---|---|---|
| T0 `stream_begin/end`、`source_status` | firmware／build／hook-set hash、boot/session nonce、各 source 是否啟用／通過 identity、結束與缺失原因；開始／結束／錯誤必存 | 新串流 metadata；不可把零事件混成 hook 未裝、來源未啟動或主體不存在 |
| T0 `mode_context_changed` | stored CINE、active UserSetting identity、AF copy identity、FullTimeAF／HalfReleaseAF、有效 focus/area、recording、readout/crop/reference、lens identity/domain、gain／曝光 context；開始與已提交變更時保存 | 已有唯讀 baseline 能定位資料；**沒有已核對的共同 context-commit hook**。追 menu → active setting → AF applied copy 的實際生效邊界，分開三層 raw enum；低頻 control-plane 快照只能作補充 |
| T0 `af_request`／`af_request_accepted`／`af_release_cancel` | request kind、origin、queue/receive 關聯、參數／ROI、原回覆；新要求、接受／拒絕、釋放、取消各保留 | S1：`C0371770`／`C0371838` command 1／2；Touch AF：`C03725C8` command 0F。語意已定位，**精確 enqueue/dequeue hooks、參數壽命、CAF 自主入口仍需 audit**；不得只保存 host key intent |
| T0 `af_decision/state_transition` | 原 state／新 state、strategy／route、觸發／不觸發、reason raw、採用 ROI 與統計版本、實際驅動要求；所有轉移保留，重複 no-change 判定可計數彙總 | 背景 `C022C864 → C023B8D0` 位於 H/L 之後；`C0259D50`／`C025A4C0` 為策略／route 入口，`C028A360` 為重驅研究入口。**只有路徑定位；decision payload、精確 hook ABI 與 CINE 覆蓋未完成** |
| T0 `af_roi_adopted`／`stats_roi_applied` | face／eye／AAT／manual 採用分支、來源觀測 ID、xs/xe/ys/ye、座標 reference、chosen/reference area、有效區集合、實際 statistics 配置版本；切換必存，相同配置只引用 generation | `C0275E60 → C02761C8/C02763C0` 定位結果採用；需再追到 **真正送往 AF statistics 的區域配置提交點**。目前沒有這個已核對 hook；menu rectangle、AAT 顯示框與 area0 都不能代替它 |
| T0 `af_episode_begin/end` | 支持的 manager/mode、begin 原因、request 關聯、episode ID、cancel/fault；新一輪必存 | `C028CDB8` 初始化與現有 terminal 可作 single-AF 候選；**CINE CAF 是否採另一 cycle／state 語意須另證**。不能強迫所有 full-time CAF 等待 single-AF terminal |
| T0 `lens_drive_request/accepted/begin`、`lens_abort`、`lens_final_end` | origin／request、target、direction mode、speed、接受／拒絕／no-op、drive ID、實際 task 發命令、取消原因、backlash 階段、final end／fault；逐事件 | final end 已有 source 2。已知 drive 鏈 `C035FFC0 → C0360430 → C03324D8 → C033EC80 → C033F050`，task `C0340210` 的 message0／1／3，abort `C033F638`；**request、queue、send、abort 的精確觀測邊界仍待 ABI audit**。同 target 的新請求也可能是新 drive；不能靠 cache 變動編號 |
| T0 `subject_select/init/reseed/lost/stop` | 主體來源、選定 ROI、reference、target／model generation、原成功／失敗／lost raw 與 gate；切換與失效全部保存 | AAT：`C05AC248` 初始 ROI、`C05AC388` 新模型／延續、`C05ABB70` command2 queue、`C05ABEC8` pending SetTarget、`C05AB9B0 → C05B6BA0` color init。**語意定位，尚無這些 lifecycle hooks**；face 選定／ID 重用亦須補。lost 原因與恢復分支需 audit，Run −1 不能一律叫 lost |
| T0 `native_af_result` | 原 payload／error、episode／request、最終 target、當前 drive/context 關聯；成功、失敗、取消一律保留 | source 1 可重用；取消 cleanup、final-drive/no-op 分支及 CINE coverage 待補；原廠結果接受與獨立光學確認分欄 |
| T1 `af_statistics` | producer ID/phase、H/L 與 actual ROI generation、gain／exposure/HPF context、source sequence、lens request/end 關聯；先以每次符合來源契約的 publication 記 compact tuple | source 5 的 area0 版本可作增量；**選定區／多區、raw band、DMA/exposure identity 尚需擴充 audit**。H/L 不改也保留 publication identity，不能只寫數值差分 |
| T1 `face_observation`／`aat_model_update` | raw result/model、validity／return、來源序號、native ID／group、reference、model generation；先保存每次 publication／Run 的 compact payload | sources 3／4 可重用，但 source3 只有 group0；全組選定與 AAT GetResult/adopted publication 是另外來源。AAT fixed64×64／自適應半軸不可當自然物體尺度 |
| T2 `af_history/detail`、`aat_candidate/detail` | 完整 H/L 區陣列、Near n/delay/k、補償位置、搜尋窗／hits／模型更新條件、較大 raw bytes；有限 burst 或可宣告的 decimation | Near `C025A660` 在辨識 virtual target 為 `C026AE50` 後返回是候選，尚無 hook；AAT `C05B2910`／`C05B2DC0` 是診斷入口，未有 ABI/生命週期 audit。第一版不以「全部函式進出」取代有界事件 |

原始來源與語意依據：[介入接點圖](research/FP_AF_FIRMWARE_INTERVENTION_MAP_2026-09-27.md)、[publication 候選](research/FP_AF_PUBLICATION_HOOK_CANDIDATES_2026-09-16.md)、[lens 控制](research/FP_NATIVE_FOCUS_CONTROL_2026-09-16.md)、[AAT lifecycle](research/FP_AAT_ACTIVATION_2026-09-27.md)、[CINE gate](research/FP_CINE_AAT_ACTIVATION_2026-09-27.md)。表中待 audit 的函式地址是搜尋入口，不是新增可寫 patch 清單。

## 3. CINE 的關聯鏈與不可代填的欄位

理想 trace 能回答：**模式／來源 → 主體結果 → 實際採用 ROI → 新統計 → 原廠判定 → drive 要求／接受／執行 → final end → 後續統計與主體結果**。S1、Touch AF 只是一部分 request origin；FullTimeAF 自發重對焦也必須有 trace。來源可並行、結果可能早於 final end、事件可能不發生；不要求每輪都硬湊出一條完整鏈。

每個 record 最低共有欄位：`schema_version, session_nonce, source_id, event_kind, record_seq, observed_seq, time_domain, time_validity, payload_length, context_generation, related_event_ids, loss_epoch`。native raw 欄位與經驗證的解讀分開；尚未取得的時間、影格、generation／關聯寫 null／unknown，不填 0 冒充第一輪。

| 識別欄位 | 建立規則 |
|---|---|
| `record_seq` | 某來源已 commit 的記錄序列；不等於看到的所有呼叫 |
| `observed_seq` | 在已證 single-writer／有界 ownership 契約下，計 eligible 邊界到訪；decimation／drop 也須可辨別。現有兩套 recorder 尚未提供此語意 |
| `request_id`、`episode_generation` | 從 native request／接受與實際 episode/cycle begin 串接；不能用 host intent、`C33D51FC` 或任意下一個 terminal 代填 |
| `drive_generation` | native drive 接受／發送鏈給身分；拒絕與 no-op 另記，abort 與 backlash 段維持父關聯；final end 須配到同一 drive |
| `target_generation`／`model_generation` | 新選定、SetTarget／reseed、lost→reacquire、來源切換；native tracking ID 是 raw evidence，不能單獨作世代 |
| `roi_generation`／`context_generation`／`scale_generation` | 採用區與 stats 配置、模式/readout/crop/lens、尺度來源/模型分別版本化；版本來源提交點未證時不偽造 cross-task 一致性 |
| `exposure_generation` | 只有完成 DMA／sensor 來源映射才可設；scheduler phase、Run 次數、影像 pointer 變化、USB batch 序號都不代替它 |

不要讓不同 task 的 hook 直接共改一個沒有 ownership 的全域 generation。先保存各 owner 的 native 邊界／request token，sender 只編封包序號，host 以明確的關聯證據還原；無法配對的事件獨立保留並說明原因。之後如在機內傳遞 generation，也需獨立驗證其 producer／consumer 發布契約。

目前 [CINE baseline](FP_CINE_BASELINE_2026-09-27.md) 的 copied area raw4 與 menu area2 是不同資料來源；tracking runtime=0、backend/model=0 代表未啟動。trace 必須能呈現這種狀態，不能把沒有 AAT update 叫作追蹤掉幀。CINE FocusMode0 也不能直接解讀為 FullTimeAF 關閉。

## 4. 共同時鐘是因果 trace 的必要增量

現有五個 recorder 都沒有可用共同時間。每來源順序可先驗證；跨 task 僅按 USB 到達／sender 掃 bank 次序排序不成立。即使有共同 CPU timestamp，同時或重疊事件也只能給部分順序；因果仍要 request／generation 關聯。

既有 [timer 稽核](geometry/NATIVE_HOOK_PLAN.md#8-tick_us-的原始-timer-來源與-bounded-read-界線) 已定位 `C002B6E0` 的 timer5 raw counter、software epoch 與 pending/wrap 處理。原 getter 含未設重讀上限的遞迴和 IRQ/FIQ 保護，不能直接塞進 hot hook。固定次數 raw/epoch/pending tuple 只是待驗候選，尚未證明各 hook 的 MMIO ordering、rollover 判定與成本。

第一個可稱為跨來源 timeline 的版本必須驗收一種共同機內時鐘：已知 timebase／period／boot epoch、固定成本、wrap／reset 處理、可識別無效 tuple，並實測時間讀取開銷。不要單讀 counter 就標微秒。若此時仍未完成，只能交付分來源 ordered raw stream，明確 `cross_source_timeline_verified=false`，不輸出 AF latency 或前因後果判決。USB host receive time 另欄保留，用於傳送延遲／停頓分析，不能回填 capture time。

CPU hook 時間與 sensor exposure 時間分成兩個 time domain；common clock 通過也不自動代表 H/L、face、AAT 與 lens position 同曝光。

## 5. 頻率、背壓與成本：先保留事件，再削減大資料

- **T0 事件驅動。** 所有 mode／target／ROI／state 轉移、request／result、drive begin/end／abort、loss notice 保留，不按固定 Hz 輪詢。重複 no-change 的 decision 可以彙總，但需報原 evaluation 次數、區間與最後狀態；涉及不同 request／統計版本時不得合併。
- **T1 先以 1:1 compact publication 建立基準。** 頻率由原廠 producer 決定；未量前不填 30/60/100 Hz。若容量／成本不足，再宣告每 N 個 eligible publication 取一筆，例如 N=2/4/8 是待驗配置，不是已測得的工作點。保持 observed sequence 和略過數，狀態／validity／generation 轉移強制記錄；不得在過載後只留下成功樣本。
- **T2 小窗口／decimation。** 全區 H/L、完整 tracker 候選／圖像資料只在指定有限窗口取樣；不能因 USB 可傳就放進每個高頻 hook。T0/T1 本身必須足以解釋該窗口的來源與失效。
- hook 僅做固定、有上界的欄位複製／commit；USB、CRC／封包、大量解碼與 cache/DMA 工作在獨立 sender。使用有上界的多 bank／queue 與明確 FREE→WRITING→READY→SENDING→FREE ownership，sender 消費時 producer 不能覆寫。現有 finite arrays 的 enabled/full 不能當成可循環重用協定。
- 壅塞時先停 T2、再依事先宣告配置降低 T1；T0 保留獨立容量。任何等級都不可等待 USB 或阻塞原廠 AF。T0 若也滿，標記該段因果鏈不完整，原廠 AF 繼續；不能靜默覆蓋或無限等待。

新 stream status 至少分開 `eligible_seen, committed, intentionally_decimated, buffer_full_dropped, contention_loss, source_guard_rejected, sender_failed, host_gap`；每來源、每 bank/session 可核對。計數本身也需證明有界且競態正確；無法精確計的 contention 先保留 sticky flag 和「數量未知」，不要把它當 1 次或 0 次。counter wrap／飽和須明示。host gap 不必等於 hook drop，sender failure 亦不證明相機端資料未產生。

既有 FNO1 只有 sticky loss，H/L schema 沒有 full 後 loss 計數；兩者都不能直接報「0% 丟樣」。新版本應保留原始格式解碼相容性，不追寫歷史 capture。

測量分離三項：hook 額外延遲、CPU→sender 排隊延遲、USB→host 延遲。比較原廠／僅 metadata／各 source mask／完整 stream，同樣 CINE context 下觀察 AF task 執行、stack high-water、missed publication、UI/recording 行為與完整退出。可用 `bytes_per_second = Σ(record_bytes × observed_source_rate / N) + metadata` 作容量預算；目前只有既有 128/256-byte record 大小已知，source rate／peak burst／stall 時長都待量，不能宣稱頻寬足夠。

## 6. 下一個有界交付

1. 定義多來源 stream envelope、bank ownership、loss accounting／source mask 與 host decoder；沿用既有五點 payload，先用離線合成事件驗證並行、亂序、缺失、重送、bank 飽和與中止。這是 transport／格式增量，不冒充 native 因果驗證。
2. 並行稽核共同時鐘及 T0 的 request／decision／ROI commit／lens begin/abort／AAT lifecycle。逐點取得精確 callsite、before-image、ABI、task／core／reentrancy、資料壽命、成本與生命週期證據；未過者在 hook-set manifest 標為 absent。
3. 既有五點到多 bank stream 的第一輪只讀觀測先證來源可達、計數／丟樣、原函式效果與 USB 實收；CINE 錄影模式與 standby 分別驗收。不要以已成功的單次 S1 取代 continuous/recording 覆蓋。
4. T0/T1 足夠且 common clock 通過後，才交付可重播的 CINE 因果 trace；對每條採用 ROI→decision→drive→result/end 提供可配對或明確 unknown 的結果。再由同一 trace 決定 AAT、幾何方向與 DFD 的實際介入順序。

本輪只新增本清單；未調整既有 recorder／transport、來源 manifest、歷史校驗或相機狀態。
