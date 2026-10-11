# SIGMA fp EP05 → EP84 Shell 通道開發日誌

日期：2026-08-17  
韌體：SIGMA fp Ver.5.02  
目前版本：v15（已完成實測）

## 目標

在保留原生 PTP interface 0 的前提下，新增 vendor interface 1：

- EP05 Bulk OUT：Mac → 相機
- EP84 Bulk IN：相機 → Mac
- 第一階段：EP05 收到資料後原樣 echo 到 EP84
- 後續：以此建立雙向 Shell 基礎通道

所有修改都只寫入 executable RAM；完整冷開機可恢復。

## 已確認里程碑

1. PTP 與 vendor interface 1 可以同時列舉。
2. EP84 descriptor 正常：Bulk IN、SuperSpeed maxPacket 1024。
3. EP05 descriptor 正常：Bulk OUT、SuperSpeed maxPacket 1024。
4. EP84 固定 64-byte `EP84TEST` 已成功傳送。
5. EP84/EP05 endpoint 啟用需要 `DALEPENA |= 0x600`。
6. v12、v14 已讓主機 EP05 OUT 成功完成 1024 bytes。
7. macOS 右上角相機圖示消失不是 USB detach：IORegistry 中 SIGMA fp 仍為 registered、active、USB 5 Gbps、configuration 1。

## 重要操作規則

- 必須拔電池 20–30 秒冷開機；只關機可能保留舊 RAM hook。
- AutoRun 約需 75–90 秒完成大量 RAM 寫入。
- 彩條提示自 v14 起：
  - 1 次：AutoRun 已觸發。
  - 2 次：hook 安裝完成，可以接 USB。
  - 3 次：診斷全部寫完，可以關機讀卡。
- 只有寫卡且下一步要插相機時才退出 SD；讀卡後保持掛載。

## 版本與結果

### v9：EP10 endpoint-state / event 診斷

- EP10 EndTransfer 成功。
- EP10 StartTransfer 成功，resource index 6。
- Firmware wait 回 `-5`。
- 新 OUT TRB 保持 length `0x400`、control `0x813`（HWO 未被消耗）。
- GetEndpointState command 成功，state value 為 4。
- `GEVNTCOUNT0 = 0`，事件已被韌體消費。

### v10–v11：縮短 timeout 與提示實驗

- 部分輪次在 AutoRun 尚未完成前關機，只留下 PRE/TXINIT，不能視為有效 endpoint 實驗。
- `display text` 不會顯示在目前 LiveView layer。
- 相機端 wait 從 60 秒縮短到 15 秒；主機送出延遲從 40 秒縮短到 5 秒。

### v12：第一次可靠的 EP05 OUT 成功

- 彩條提示有效；第一次彩條後接 USB。
- 主機結果：EP05 OUT success，transferred 1024。
- EP84 只收到 0-byte ZLP。
- 相機 firmware wait 仍回 `-5`。
- 我們新配置的 context-5 TRB 完全未被消耗。
- 結論：主機封包沒有進入我們重新配置的 DMA buffer。

Capture：`/Users/dido/Documents/Codex/2026-08-16/4/captures/ep05_ep84_v12_out_success_zlp_20260817_1547`

### v13：直接呼叫底層 D-cache API（失敗方向）

- 在 TRB StartTransfer 前呼叫 `FUN_c000eb90(start,end)` clean。
- OUT buffer 後呼叫 `FUN_c000ea54(start,end)` invalidate。
- 呼叫沒有卡死，但 EP10 StartTransfer 回 `-1`，EP05 回到 I/O error。
- `RX13.BIN` 誤選到既有 helper code 區 `0xC072E180`，不是有效 DMA 快照。
- 結論：不能直接以此方式／時機呼叫底層 cache API；已回退。

Capture：`/Users/dido/Documents/Codex/2026-08-16/4/captures/ep05_ep84_v13_cache_clean_20260817_1558`

### v14：回復 v12 路徑、正確 RX 快照區

- EP05 OUT 再次成功 1024 bytes。
- EP84 仍收到 0-byte ZLP。
- firmware wait 仍為 `-5`；新 TRB HWO 未消耗。
- `RX14.BIN` 位於已驗證 zero cave `0xC072E700`，內容沒有 `SHELLECHO`，主要為 `0xFF`／舊資料。
- 確認 host packet 並未進入我們替換後的 DMA buffer。
- macOS USB event log 未出現整個裝置 detach。

Capture：`/Users/dido/Documents/Codex/2026-08-16/4/captures/ep05_ep84_v14_out_success_rx_snapshot_20260817_1606`

### v15：沿用初始化時的原始 OUT resource（已否定）

核心策略：

- 不再對 context 5 執行 EndTransfer。
- 不替換 context-5 TRB。
- 不重新 StartTransfer EP10。
- 直接等待 context 5 初始化時已啟動的原始 EP05 OUT resource。
- 記錄原始 TRB 的 DMA address、length、control。
- 從該原始 DMA buffer 複製前 64 bytes 到 `RX15.BIN`。
- OUT wait 成功後，結束原本 EP84/ZLP resource，使用同一 DMA buffer re-arm EP84 64-byte IN。
- Mac host 端忽略最多 8 個舊 ZLP，再等待真正 echo。

驗證：

- Handler 65 words，與 AutoRun authoritative block 逐 word 比對，0 mismatch。
- 已移除 v13 的 cache clean/invalidate 呼叫。
- AutoRun SHA-256：`48caa2cb5798721218bdaa4b367dd90bf220d6349be83a9ea0ec9b59983bffe8`
- v15 已完成完整冷開機實測並產生全部診斷。

實測結果：

- 主機 EP05 OUT 回 `LIBUSB_ERROR_IO`，transferred 0。
- Firmware wait 回 `-5`。
- 原始 context-5 TRB pointer：`0xC31E3310`。
- 原始 TRB：DMA `0x04F271C0`、length `0x400`、control `0x813`。
- Wait 後 length/control 完全不變，HWO 未被消耗。
- CPU alias `0x44F271C0` 的 `RX15.BIN` 沒有 `SHELLECHO`，只有原有資料。
- 結論：初始化時的原始 OUT resource 也沒有實際接收 host packet，不能直接沿用。

Capture：`/Users/dido/Documents/Codex/2026-08-16/4/captures/ep05_ep84_v15_reuse_initial_resource_20260817_1614`

## 目前最重要的技術判斷

v12/v14 的 EndTransfer＋StartTransfer 是讓 host EP05 OUT 回 success 的必要條件，但自建 TRB 沒有被消耗；v15 證明初始化時的原始 TRB 也不會直接接收。下一個問題已縮小為：`FUN_c01e6b80` StartTransfer wrapper 實際使用哪個 TRB pointer／參數，以及它是否從另一個 resource table 取 descriptor。

## 下一步

1. 反編譯 `FUN_c01e6b80` 與直接 caller，確認 StartTransfer wrapper 的完整 ABI。
2. 找出 wrapper 實際讀取的 TRB pointer／resource table。
3. 比較原生可工作的 OUT endpoint caller 如何準備 TRB、cache 與 event semaphore。
4. 下一版回到 v12/v14 的 End＋Start 路徑，但將診斷對準 wrapper 真正使用的 descriptor。

### v16–v18：EP05 DMA 成功與同步 sender 卡死定位

- v16 正確的 `0x431E...` TRB alias 證明 EP05 OUT 已完整 DMA：context 5
  length 由 `0x400` 歸零，HWO 由 `0x813` 清成 `0x812`。
- v17 在 OUT 後 invalidate `0xC4...` cached alias，並呼叫原生
  `FUN_c01e5880` 發送 EP84；實測穩定在約 60 秒後卡死。
- 重測的 `TXINIT013` 與有效 v16 `TXINIT012` 完全一致，證明卡死發生在
  v17 handler 的原生同步 sender，而非 endpoint 初始化。
- v18 移除 `FUN_c01e5880` 的 60 秒 wait/timeout cleanup，只沿用其 cache
  clean 與正常 TRB 格式，直接對 EP9 StartTransfer 後立即返回保存診斷。
- v18 handler 90 words，AutoRun 逐 word 比對 0 mismatch；SHA-256：
  `606fa25853233dd63356b5abac748cbd637192efc37c7d17c7d2b301c7554b38`。

### v19：逐階段阻塞定位

- v18 仍在 handler 內卡住，且沒有任何 post-handler 檔案，無法區分 cache
  maintenance 與 EP9 command 阻塞。
- v19 將流程拆成 7 次獨立 `log` 呼叫；每次只執行一階段並立即返回：
  EP05 Start、OUT snapshot、invalidate、cached snapshot/mode 2、clean、EP84 End、
  EP84 Start。
- 每階段保存 `STG190.BIN` 至 `STG196.BIN`；另保存 invalidate 前後 alias
  快照 `RX19U.BIN`／`RX19C.BIN`。
- Handler 138 words、無 relocation、AutoRun 逐 word 比對 0 mismatch；SHA-256：
  `856f91d5a2fba12320bce599662fa9c2c4ef16df1250d206b861a82617b5c9c2`。

### v20：移除會硬鎖的 cache API

- v19 只完成 `STG190`、`STG191`；`STG192` 不存在，精確證明
  `FUN_c000ea54` invalidate 在此 buffer/alias 上會硬鎖。
- v20 將 invalidate 與 clean 階段改成純 marker，不再呼叫底層 cache API，
  並讓 EP84 直接重用 EP05 的 physical DMA buffer。
- EP05 等待窗延長為 20 秒；Mac EP84 read timeout 延長為 60 秒。
- Handler 124 words、無 relocation、逐 word 比對 0 mismatch；SHA-256：
  `9dd58e57f89cdf5ef29e1a4ecfde9fb7424b66451b79af585b172c88335b2022`。

### v24：EP05 → EP84 雙向 echo 成功

- USB registration 會把 context 4 覆寫為 mode 3；在 registration 後、
  `FUN_c01e62a9(4)` 初始化前恢復 mode 2，EP84 resource 才會建立在正確路徑。
- Host 成功送出 EP05 1024 bytes，並從 EP84 收回完全相同的前 64 bytes。
- EP05 與 EP84 TRB 最終皆為 length `0`、control `0x812`，雙向均被 DWC3
  完整消耗。USB Shell 基礎雙向 transport 正式成立。

### v25：四輪 persistent transport 驗證

- 同一 USB 連線連續執行 4 輪不同 payload 的 EP05 → EP84 echo。
- 每輪重新 re-arm 兩個 endpoint，保留 7 個 stage checkpoints，共 28 個。
- Host 逐輪比對 64-byte response；EP84 timeout 保持 60 秒。
- AutoRun SHA-256：
  `f3997129bd6aff4f712b33f28009c55685d76ef0a04801470c98b5344f0718db`。

### v26：compact startup

- 第二次彩條前的 RAM 寫入由 904 次降為 301 次，移除所有歷史版本覆寫。
- 移除第二次彩條前 9 個診斷存檔；固定 sleep 僅保留第一次彩條的 700 ms。
- Builder hook、callback（含跨界 literal pool）、初始 EP84 packet、EP84 init、
  persistent handler 與 v25 最終 RAM 值逐址比對 0 mismatch。
- Compact AutoRun SHA-256：
  `33d4e0445ab40ca4a05af6d5b38538c3f973edb296b5192c963ba37c05caa721`。

### v27：endpoint safe cleanup

- v26 在失敗／錯位測試後可能留下 EP05 與 EP84 TRB control `0x813`，使相機關機等待 USB resource 而卡住。
- Handler 新增 stage 7：依序 EndTransfer context 5 與 context 4，保存回傳值及 marker `0x27270707`。
- 最後一次 EP84 StartTransfer 後等待 3 秒才清理；`R2737.BIN`、`CLEAN27.BIN` 保存完成後才允許三次彩條。
- AutoRun SHA-256：
  `40ee119a1ce0c5ac307a31045771d34033de88fcacf566b4105d9b0171b21d62`。
- 已寫入 16GB `fpShellTest`、逐位元驗證並退出；下一步為實機確認四輪 echo 與三次彩條後能正常關機。
- 2026-08-18 實機結果：interface 1、EP84／EP05 均正確枚舉；Mac 端本輪 EP05 OUT 立即回 `LIBUSB_ERROR_IO`，但相機仍完成 stage 7 並顯示三次彩條。拔除 USB 後相機可正常操作及正常關機，證實 v27 camera-side cleanup 已修正「注入後無法關機」。下一步需讀回 `R2737.BIN`／`CLEAN27.BIN`，並修正 host 在 stage 0 EndTransfer 期間第一次 OUT 被取消的重試時序。
- 讀卡確認：`R2737.BIN` state=`8`、cleanup marker=`0x27270707`；context 5 與 context 4 EndTransfer 回傳值均為 `0`。四輪 EP05 snapshot 皆維持 length=`0x400`、control=`0x813`，RX buffer 未改變，證實本輪 transport 沒有收包。EndTransfer 後 TRB 記憶體仍保留 `0x813`，但 firmware resource 已成功退休，因此不可只用保存的 HWO bit 判斷 shutdown cleanup。

### v28：host EP05 cancelled-transfer recovery

- 相機端沿用已證實可正常關機的 v27 AutoRun 與 stage 7 cleanup。
- Host 若 EP05 OUT 回 `LIBUSB_ERROR_IO` 且 transferred=`0`，會 clear halt、等待 250 ms，重送同一 payload；最多八次。
- 其他錯誤及 partial transfer 不重試，避免重複執行不確定的命令。
- Host SHA-256：`23e969c6399b3a70da5189ccf48c656f1b43ec8064b71f850feaa837b332626e`。
- 16GB 卡內容不需重寫，已退出供下一輪實機測試。
- 實機：前五次 EP05 IO，第六次回 success/1024；EP84 success/64，但 host 比對失敗。
- 讀卡證實四輪 EP05 TRB 均維持 length=`0x400`、control=`0x813`，`RX270U000.BIN`／其餘 RX 全為 `0xFF`。因此 host 的 success 落在尚未綁定新 TRB 的舊 endpoint/FIFO，沒有進入 shared DMA；EP84 回傳的是原本的 FF buffer。
- v29 應以相機 AutoRun 時序為準：interface claim 後涵蓋 30 秒 reconnect window，等 stage 0 真正 arm 再送第一包；不再用短時間 clear-halt success 當作 ready 訊號。

### v29：non-invasive arm wait

- Host claim interface 後等待 32 秒，期間不 submit EP05、也不 clear halt。
- 目標是讓相機先完成 30 秒 reconnect window、stage 0 EndTransfer 與新 TRB StartTransfer，再送第一包。
- Host SHA-256：`a5022aef05bf643b5d65688363ed9ee6181b5a566dc8ecf6ba62d9cf75a61dd8`。
- 相機端沿用 v27 cleanup；16GB 卡未改內容，已安全退出。
- 2026-08-18 實機成功：四輪 EP05 OUT 均為 success/1024 bytes，四輪 EP84 IN 均為 success/64 bytes；逐輪 payload 完全一致，ZLP=0，host exit code=0。證實 claim 後 32 秒靜默等待可可靠避開 pre-stage-0 resource，恢復 v25 的四輪雙向 transport，同時保留 v27 安全 cleanup。
- 讀卡交叉驗證：四輪 RX 分別為 `SHELL000`～`SHELL003`，各 64 bytes 與 host payload 零差異；四次 OUT TRB 均為 length=`0`、control=`0x812`。最後 state=`8`、EndTransfer(5)=`0`、EndTransfer(4)=`0`、marker=`0x27270707`。完整基準 capture：`captures/v29_four_round_success_20260818_0249/`。

### v30：USB logical deconfigure shutdown test

- v29 的「關機失敗」發生於實體 USB 線仍連接；兩個 vendor endpoint cleanup 實際均已成功。
- v30 成功完成四輪後靜默等待 12 秒，讓相機 stage 7、診斷保存與三次彩條完成。
- Host 接著 release interface 1，送標準 `SET_CONFIGURATION(0)`，測試實體線不拔時邏輯 deconfigure 是否足以允許相機關機。
- 僅成功路徑 deconfigure；transport 失敗時不擴大 USB 狀態變更。
- Host SHA-256：`7f0372ae51c430a1a6f862f5d1bea5f7a617351fb8ca1f5fa552d6717216174e`。
- 實機：四輪 echo 全成功；release interface 1 與 `SET_CONFIGURATION(0)` 均回 success，host exit code=0。但實體 USB 線仍接著時，相機依然不能關機。
- 結論：關機阻擋點不在 EP05／EP84 active transfer、interface claim 或 USB configuration，而在更上層的實體 attach/VBUS／相機 USB session 狀態。現階段操作規則維持「三次彩條後拔 USB，再關機」。除非找到相機端 gadget soft-disconnect 函式，host 標準 USB API 無法取代實體拔線。

### FPShell daemon：多 client 實機成功

- `fpshelld` 作為唯一 libusb/interface 1 owner，四個 `fpshell` client 同時連 Unix socket。
- Daemon 依序完成四輪，回應為：sequence 0=`agent-A`、1=`agent-B`、2=`agent-C`、3=`agent-D`。
- 四個 client 均 exit code 0；payload／sequence 沒有交叉或錯配。
- `STATUS` 回 `state=ready used=4 limit=4`；等待 12 秒後 `QUIT` 正常停止，daemon exit code 0。
- 證實多 Agent host-side 架構可行；剩餘四輪限制來自目前 camera AutoRun，下一步是相機端長駐 request loop 與正式 framing。
- 後續關機回報：完成四輪、daemon `QUIT`、拔除實體 USB 後，相機仍可能卡在關機。讀卡仍顯示 state=8、EndTransfer(5/4)=0、marker 正確；四輪 TRB 均完成。
- 修正結論：v27 cleanup 只足以處理「沒有成功收包／早期 IO」的案例；一旦 vendor Bulk 完成過，EndTransfer 不會撤銷 endpoint registration、完成 callback/semaphore 或 USB service 的全部軟體狀態。必須找到 `FUN_c01e62a9` init 的對稱 deinit/unregister 路徑，不能只增加等待或重複 EndTransfer。

### FPShell host 工具完善（2026-08-18）

- 將 v29 的 32 秒 arm wait 與四輪上限固定為穩定 transport baseline；v31–v33 teardown 留在研究分支，不阻塞工具開發。
- `fpshelld` 成為唯一 interface 1 owner；Unix socket 權限為 `0600`，並可用 `--socket`、`--arm-wait`、`--limit`、`--mock` 設定。
- 正式定義 64-byte `FPSH` v1 frame：magic、version、command、flags、sequence、payload length、status、CRC32 與 44-byte payload。frame 放入 1024-byte EP05 transfer 前段，EP84 回收 64 bytes。
- daemon 驗證 header、command、sequence、length、status 與 CRC；支援 local `STATUS`／`INFO` 及 USB `PING`／`ECHO`。
- `fpshell` 新增 socket/response timeout、UTF-8 byte 長度預檢、明確 exit code 與 Agent 友善的 `--json` 單行輸出。
- mock backend 測試涵蓋四個並行 client、sequence/payload 不錯配、四輪 session limit、single-daemon ownership、0600 權限、JSON、Unicode 超長拒絕、socket 連線錯誤及 clean quit。`make clean all && make test`：5 tests 全數通過，C 編譯無 warning。
- 文件新增 `fpshell_tool/PROTOCOL.md` 與 `CAMERA_LOOP_DESIGN.md`。長駐相機端應採 callback-driven state machine，先做 16/64 次 bounded echo，再測 CLOSE、拔插與正常關機；不得猜測 task ABI 或重新引入已知會 hard-lock 的 cache invalidate。

### v31：native USB disconnect teardown

- Ghidra xref 找到 `FUN_c01e6ef8`：原生 USB disconnect event 路徑會依 `_DAT_c31e398c` active bitmap EndTransfer context 1–6，接著呼叫 `FUN_c01e3418()`、`FUN_c01e3318(1)`，並在對應模式清除 `_DAT_c31e3968`。
- Handler 新增 stage 8，在 v27 stage 7 的 EP05／EP84 EndTransfer 後呼叫 Thumb entry `0xC01E6EF9`；保存 return 與 marker `0x31310808`。
- AutoRun 保存 `R3138.BIN`、`USBTD31.BIN`；只有 native teardown 返回後才顯示三次彩條。
- Handler 596 bytes，range `0xC072E480–0xC072E6D3`，逐 word 比對成功，未碰 RX region `0xC072E700`。
- AutoRun SHA-256：`b44ae2635c3d59c186c57b0a3e813f7bd28c03c58305a2b29cc8bac7a4ab7704`；已寫入 16GB `fpShellTest` 並退出。
- 實機讀卡：stage 8 state=9、return=0、marker=`0x31310808`，DWC/event registers 確實被 teardown，但成功傳輸後關機仍卡住。`_DAT_c31e398c` 仍保留 EP9/EP10 active bits `0x600`，builder hook、callback 與 context enabled flags 亦未還原。

### v32：full RAM hook/state restoration

- stage 9 清除 `_DAT_c31e398c & 0x600`，停用 context 4/5 enabled flags，清零 callback `0xC30257B0`，並把 builder patch `0xC04DC618` 還原為 firmware 原始指令 `0xEB0032CA`。
- Restore routine 獨立放在 `0xC072E800–0xC072E86B`；主 handler 為 636 bytes、`0xC072E480–0xC072E6FB`，不覆蓋 `0xC072E700` RX region。
- 保存 stage 9 `R3239.BIN` 與 `REST32.BIN`；marker=`0x32320909`。
- AutoRun SHA-256：`9f009a2eb98fe1c87dc36912f3772164bf0b50553b2d5e803191b4c42d8e0d85`；已寫入 16GB `fpShellTest` 並退出。
- 首次實機：interface/EP 枚舉正常，但 round 0 EP05 OUT 60 秒後回 `LIBUSB_ERROR_IO`、0 bytes；AutoRun 仍完成三次彩條。拔線等待後相機可正常關機，證明 stage 8/9 在「未成功傳輸」案例沒有破壞 shutdown。尚未驗證成功傳輸後是否修正卡關機，需讀卡定位本輪未 arm 原因。
- 讀卡：stage 0 的 context5 StartTransfer return=`-1`，OUT TRB 始終 `0x400/0x813`；RX 的 `SHELL003` 是前次殘留，並非本輪資料。stage 9 完整執行：state=10、teardown/restore return 均 0、bitmap `0xAA7→0x8A7`、marker=`0x32320909`。程式碼與 restore 本身正常；下一輪以拔電池 20–30 秒的嚴格冷開機重測同一 v32。
- 嚴格冷開機重測四輪全部成功、payload 零差異；stage 9 state=10、所有 return=0、bitmap `0x6A7→0x0A7`，但拔線後關機仍卡住。
- 成功 vs 未傳輸 run 的明確差異：context5 `0xC31E3924` software state 為 2（未傳輸為 0），且 context5 仍為自訂 mode=1/direction=OUT（未傳輸可關機 run 為原生 mode=3/direction=IN）。`FUN_c01e6d48(5)` 反編譯證實會在成功 resource 上把 context state 設成 2。下一版精準還原 context5 mode/direction/state，而非擴大 controller teardown。

### v33：context 5 native-state restore

- 在 v32 restore routine 中保存成功傳輸後的 context5 mode/direction/state，並精準還原為 mode=3、direction=1、software state=0。
- 保留 v32 的 bitmap、enabled、callback 與 builder hook 還原；stage 9 marker 改為 `0x33330909`。
- 主 handler 636 bytes、結束 `0xC072E6FB`；restore routine 180 bytes、`0xC072E800–0xC072E8B3`；兩段逐 byte 驗證成功。
- AutoRun SHA-256：`092c1a2c74613d47839b794016f029bbfa29fc560b0159da0e65861e29fa43f7`；已寫入 16GB `fpShellTest` 並退出。
- 實機四輪成功，但拔線後關機仍卡住。讀卡確認 stage 9 完整執行，保存的 pre-values 為 mode=1、direction=0、state=2，且 post context5 已與可關機基準一致為 mode=3、direction=1、state=0。
- 新差異：可關機基準 bitmap=`0x8A7`，v33 post=`0x0A7`。context5 恢復為 native IN 後應把 active mapping 從 custom EP10 bit `0x400` 移回 native EP11 bit `0x800`；v33 只清 `0x600` 而未設 `0x800`。另 native bookkeeping 基準為 ring index `C31E3A18=2`、EP10 resource `C31E3A58=0`、EP11 resource `C31E3A5C=0x80`。下一版應同步恢復這組一致狀態。

## 平行研究：Gyroflow／外接 IMU

已新增 [`SIGMA_FP_GYROFLOW_NIYIEN_A1_RESEARCH_2026-08-17.md`](../gyro-sup/SIGMA_FP_GYROFLOW_NIYIEN_A1_RESEARCH_2026-08-17.md)。目前判斷：

- Gyroflow 沒有把 SIGMA fp 列為可直接讀取內建 gyro metadata 的相機。
- NiYien Senseflow A1 是 Gyroflow 官方文件列出的外接 gyro source；NiYien 官方相機清單明列 fp／fp L。
- A1 可先作為實際穩定方案，也可在後續搜尋 fp 內部 IMU／姿態 ring buffer 時充當三軸 ground truth。
- 下一個實驗入口是取得 fp + A1 的原始 DNG、gyro log 與 `.gyroflow` 專案，確認同步、檔案格式及各模式的 rolling-shutter readout time。
