# SIGMA fp 長時間 USB Shell 交接文件

日期：2026-08-18  
目前階段：EP05 Bulk OUT → 64-byte framed echo → EP84 Bulk IN 已可連續四輪；多 Agent host 工具已完成 mock 與實機驗證。四輪版本只是 transport baseline，不是專案完成品。最終目標是相機端長時間常駐 worker，持續執行 `接收 → 驗證 → dispatch → 回覆 → 再次 arm`，直到明確 CLOSE、斷線或 bounded fault。

## 最終目標與完成條件（2026-08-18 重新確認）

使用者要求的是「長時間 USB Shell」，不是四次命令測試器。不得再把 bounded 四輪版稱為完成工具。

完成條件：

1. 相機冷開機後建立獨立 firmware worker，不依賴 AutoRun 手動重複 `log`。
2. EP05／EP84 在每輪完成後由 camera-side state machine 重新 arm。
3. 單次連線至少通過 16 輪、64 輪，最終進行長時間壓力測試。
4. FPSH frame 的 magic、version、command、sequence、length、status、CRC32 在相機端驗證。
5. 支援明確 `CLOSE`；拔線／timeout 不得讓 worker 忙迴圈或無限等待。
6. host 仍由單一 `fpshelld` 持有 interface 1，多 Agent 透過 Unix socket 共用。
7. 產物必須能從 source 重建，包含 AutoRun、ARM worker、host daemon、CLI、測試與 SHA-256 manifest。

不再列為完成阻擋項目：成功 Bulk traffic 後偶發無法正常關機。此 teardown 研究已依使用者要求停止；已知恢復方式為拔電池 20–30 秒。長時間 Shell 仍需避免新增已知 hard-lock 呼叫，但不再為追求正常關機反覆修改 endpoint teardown。

## 目前進度摘要

### 已實機證實

- vendor interface 1，EP05 Bulk OUT、EP84 Bulk IN，SuperSpeed max packet 1024。
- v29 時序：host claim interface 1 後靜默 32 秒，可可靠進入第一輪。
- 四輪 1024-byte OUT／64-byte IN 完整成功；FPSH v1 的英文、中文、PING payload 均已實機回傳。
- host daemon 單一 USB owner、多 client 排程、sequence、CRC32、0600 socket、JSON CLI。
- compact AutoRun 已移除 SD 診斷寫檔；第一次 compact 實測發現 round gap 競態，host 已新增預設 2500 ms inter-request guard。這只是過渡修正，長駐 worker 應自行處理 completion 後再 arm。

### 四輪 baseline 的限制

- v27/v29 AutoRun 以 29 次 `log` 手動推進四輪 staged handler。
- 第四輪後 stage 7 EndTransfer 並三閃，因此通道必然結束。
- 電腦端無法延長 session；必須由相機 firmware worker 持續重新 arm endpoint。

### 已定位的 firmware task ABI

工作區既有 `stage6_gyro_double_buffer_hook.S` 提供可沿用的 direct-entry task 建立方式：

- descriptor：32 bytes；`[0]=0`、`[4]=1`、`[8]=entry`、`[12]=priority 0x3C`、`[16..23]=name`、`[24]=0`。
- create：ARM `0xC01F885C`，傳入 descriptor pointer，回傳 task handle。
- start：ARM `0xC01F8D90`，傳入 create 回傳的 handle。
- cooperative sleep：ARM `0xC03705D8`，`r0` 為 sleep interval；既有 worker 使用 5。

上述 ABI 來自已逆向的 gyro worker，但尚未在 USB Shell 路徑完成獨立實機驗證。因此先做最小 task probe，不直接把 USB 狀態機與未知 task ABI 一次混合。

### 正在進行：persistent task probe

新檔案：

- `fpshell_tool/camera/persistent_task_probe.S`
- `fpshell_tool/build_task_probe.py`
- 預定產物：`fpshell_tool/dist/AutoRun_TaskProbe.txt`

probe 行為：AutoRun 呼叫 starter；starter 建立低優先權背景 task；worker 每 10 單位累加 heartbeat。1.5 秒後保存 `THRPROBE.BIN`，用 handle、`STRT/STAR/WORK` marker 與遞增 counter 證明 task 持續運作。probe 不碰 USB endpoint，斷電即還原。

目前 builder 第一次執行發現系統沒有 `llvm-objcopy`；下一步改用工作區既有 `build_stage5_autorun.py` 的 ELF section／relocation reader，不新增外部依賴。

## 後續實作順序

1. 完成並實機驗證 task probe。
2. 建立 bounded 16-round USB worker：poll TRB completion、EP05 收包、FPSH 驗證、EP84 回覆、重新 arm。
3. host 取消四輪上限，加入 `CLOSE` command 與長 session sequence。
4. 實機依序驗證 16、64、數百輪；記錄 timeout、CRC mismatch 與 CPU/UI responsiveness。
5. 加入 disconnect/backoff；只有在 worker 不會忙迴圈後才測拔插。
6. 收斂 persistent AutoRun、release archive、操作文件與最終 SD 卡產物。

## 當前工作計畫

- [x] 找到可參考的 firmware task create/start/sleep ABI。
- [ ] task heartbeat probe 可重建並通過實機。
- [ ] 16-round persistent worker。
- [ ] 64-round壓力測試。
- [ ] FPSH camera-side parser／dispatcher／CLOSE。
- [ ] 長時間 session 與 reconnect/backoff。
- [ ] 最終 release 與 SD 卡部署。

## 交接時的精確狀態

### 相機／SD 卡

- 16GB ExFAT 卡名：`fpShellTest`，裝置通常為 `/dev/disk6`；128GB `fpFCtest` 不可誤寫。
- 卡上目前是 compact 四輪 AutoRun，SHA-256：
  `ab699491cf5d824c4d0d1135787c7c49406c69ac1db6fc82edddda5019d1f59e`。
- compact AutoRun 已做過一次實機：sequence 0 成功；sequence 1 的 OUT 太早落入上一輪 resource，之後 EP84 IN timeout。原因是移除 SD `mem save` 後，host client 可在相機 1.5 秒 round gap 內立刻提交下一包。
- host 已新增預設 `2500 ms` inter-request guard；所有 mock／結構測試通過，但此修正尚未以 compact AutoRun 重新實機驗證。
- 使用者已確認最終目標是長時間 Shell，因此不必再花一輪驗證四輪 compact + host guard；它只保留作為已知競態與 transport 參考。
- 上一次相機仍在 compact AutoRun 測試週期；在寫 task probe 前必須拔電池 20–30 秒，再把 16GB 卡插回 Mac。

### Host tool 產物

工作目錄：`/Users/dido/Developer.localized/SIGMAfp_re/codex/fpshell_tool/`

- `fpshelld.c`：單一 libusb owner、FPSH framing、CRC32、sequence、多 client serialization、daemon lock、ready 後才公開 socket、預設 2500 ms inter-request guard。
- `fpshell`：CLI、UTF-8 44-byte 限制、timeout、JSON。
- `fpshellctl`：背景 start/status/stop，預設 32 秒 camera arm wait。
- `make test`：6 組 daemon/CLI tests + 5 組 compact AutoRun tests 全數通過。
- package：`fpshell_tool/release/FPShell-1.0.0-macOS-arm64.tar.gz`。
- compact release archive 最新 SHA-256（加入 inter-request guard 後）：
  `3d6065559d2dfe94d108be743f79758cfda053242bd101030bbb6cd27cbe2c3d`。
- 注意：`FPShell 1.0` 命名只是 bounded host/tool 封裝，不能視為長時間 Shell final release；長駐版完成時應改版號與 README 定位。

### Persistent task probe 產物

- source：`fpshell_tool/camera/persistent_task_probe.S`
- builder：`fpshell_tool/build_task_probe.py`
- AutoRun：`fpshell_tool/dist/AutoRun_TaskProbe.txt`
- ARM code size：`0xE4` bytes，load `0xC072E800`，state `0xC072E900`。
- source SHA-256：
  `8ebf295f68651c93a865144fec6bf2f7f86aeb9c3d38f359645ee0b4480d9842`。
- AutoRun SHA-256：
  `3fbc4fbe1e75bd11f066054ad49d2a0a5dcbdf331c355b7807dd922269e78f33`。
- builder 原先使用 `llvm-objcopy` 失敗，已改用 `build_stage5_autorun.py` 的 ELF extraction/relocation helper，因此不需額外工具。

Probe state layout (`THRPROBE.BIN`, 64 bytes)：

| Offset | 意義 | 成功預期 |
|---:|---|---|
| `0x00` | starter marker | ASCII `STRT` little-endian word |
| `0x04` | create 回傳 handle | `>= 1` |
| `0x08` | start 回傳值 | 保存原值，先不假設語意 |
| `0x0C` | starter result | `STAR`；失敗為 `FAIL` |
| `0x10` | worker marker | `WORK` |
| `0x14` | heartbeat counter | 1.5 秒後明顯大於 0 |

Probe worker 每 10 單位 sleep 後累加 heartbeat，不碰 USB／檔案系統；AutoRun 主流程在 1.5 秒後才保存 snapshot。背景 task 不主動退出，必須以拔電池冷重置清除，符合 RAM-only probe 邊界。

## 下一個 Agent／下一輪實驗的精確操作

1. 等使用者將 16GB `fpShellTest` 插回 Mac並說「讀卡」。
2. 用 `diskutil info /Volumes/fpShellTest` 核對 15.9 GB、ExFAT、Secure Digital；不可只憑 `/dev/diskN` 猜測。
3. 備份卡上的 compact `AutoRun.txt` 到新的 timestamped capture 目錄。
4. 寫入 `fpshell_tool/dist/AutoRun_TaskProbe.txt` 為卡根目錄 `AutoRun.txt`。
5. `sync`、`cmp -s`、`shasum -a 256`，必須得到
   `3fbc4fbe1e75bd11f066054ad49d2a0a5dcbdf331c355b7807dd922269e78f33`。
6. `diskutil eject` 退出整顆 16GB 卡。
7. 使用者插卡、拔電池 20–30 秒、冷開機；一閃後等待兩閃完成。此 probe 不需接 USB。
8. 拔電池清除常駐 task，把卡插回 Mac，讀 `THRPROBE.BIN`。
9. 只有 marker、handle、heartbeat 全部符合上表，才開始 16-round USB worker；task ABI 失敗時只修 probe，不加入 endpoint code。

## 16-round worker 初版設計約束

- starter 只建立 task並立即返回 AutoRun，USB worker 在低優先權 task 中運行。
- worker 不再依賴 AutoRun `log` 推進 stage。
- 每輪狀態：`ARM_OUT → POLL_OUT_COMPLETE → VALIDATE → ARM_IN → POLL_IN_COMPLETE → ARM_OUT`。
- OUT completion 以 TRB control HWO bit 清除／remaining length 變化判斷；poll loop 必須呼叫 `0xC03705D8` sleep，不可 busy-spin。
- 只使用已實機成功的 DMA alias；不可呼叫 `FUN_c000ea54` cache invalidate。
- 每個 poll 有 bounded timeout 和 fault counter；首版到 16 輪後進入 idle，不嘗試關機 teardown。
- 首版先 echo 完整 64-byte FPSH frame；camera-side CRC/parser 可在 loop 穩定後加入，避免 task、USB loop、parser 三個變數同時改動。
- host 初版以 `--limit 16`，每輪仍序列化；長駐 worker穩定後才改為 unlimited／explicit CLOSE。
- 16 輪驗收必須檢查每個 sequence/payload；不能只看 host exit code。

## 明確停止事項

- 不再研究「正常關機偶發卡住」的完整 teardown。
- 不再製作 v34 類 bitmap/context restore 猜測版。
- 不再把等待更久視為關機修正；60 秒等待實驗仍可卡住。
- 不再以多次手寫 AutoRun `log` 當長駐方案。
- 不在 task ABI 未實機成立前加入 USB endpoint loop。

## 歷史參考：v27–v33 四輪研究

以下內容保留既有實驗證據與位址，若與文件前半部「最終目標／精確狀態／操作順序」衝突，應以前半部為準。

### 使用者操作約定

- 測試卡為 16GB ExFAT `fpShellTest`；128GB `fpGfTest` 不可誤寫。
- 寫完 SD 卡並準備插相機時，退出整顆磁碟；只讀診斷時保持掛載。
- 冷開機須拔電池 20–30 秒，不能只關機。
- 彩條提示：第一次表示 AutoRun 已執行；第二次表示 hook 已就緒、可以接 USB；三次表示測試及 endpoint 清理已完成，可以拔線或關機。
- v27 在看到三次彩條以前，不應嘗試關機。

### 已證實成果

- 保留原 PTP interface，新增 vendor interface 1。
- EP05 為 Bulk OUT，EP84 為 Bulk IN；SuperSpeed max packet 均為 1024。
- v24 修正關鍵模式問題：USB registration 會把 context 4 mode 改回 3，必須在 registration 後、`FUN_c01e62a9(4)` 初始化前再次寫入 mode 2。
- v24 首次完成 EP05 1024 bytes OUT 與 EP84 64 bytes IN，Mac 收到正確 `SHELLECHO...`。
- v25 在同一 USB 連線完成四輪不同資料的雙向 echo；四次 OUT、四次 IN 均成功，沒有 ZLP、timeout 或資料錯誤。
- v26 compact AutoRun 將第二次彩條時間由約 50 秒降至約 18 秒。
- DMA buffer 的 `0x44...` 與 `0xC4...` CPU alias 都能直接讀到新 DMA 內容。

### 絕對禁區

- 不可呼叫 cache invalidate `FUN_c000ea54`：已證實會讓相機硬鎖。
- 不可對 DMA 收到的資料做會覆蓋內容的 stale-cache clean。
- EP84 host 尚在等待資料時不可提前 EndTransfer；舊版曾導致 `LIBUSB_ERROR_IO`。
- 不可在 active EP05／EP84 transfer 尚未退休時宣告測試完成，否則相機正常關機可能卡住。

### v27 的修正

v26 最後一次測試留下：

- EP84 TRB：length `0x40`、control `0x813`（仍 active）。
- EP05 TRB：length `0x400`、control `0x813`（仍 active）。

這會讓相機關機流程等待未釋放的 USB resource。v27 在 staged handler 新增 stage 7：

1. 最後一次 stage 6 啟動 EP84 後等待 3 秒，讓 Mac 完成 IN。
2. 呼叫 `FUN_c01e6d48(5)`，終止 EP05/context 5。
3. 呼叫 `FUN_c01e6d48(4)`，終止 EP84/context 4。
4. 將兩個回傳值與 marker `0x27270707` 留在診斷區。
5. 儲存 `R2737.BIN`、`CLEAN27.BIN` 及控制器診斷後，才顯示三次彩條。

v27 AutoRun：

- `/Users/dido/Documents/Codex/2026-08-16/4/outputs/AutoRun_USB_Shell_v27_SafeCleanup.txt`
- SHA-256：`40ee119a1ce0c5ac307a31045771d34033de88fcacf566b4105d9b0171b21d62`
- 已於 2026-08-18 寫入 16GB `fpShellTest` 並逐位元比對，之後已退出 `/dev/disk6`。

Host：

- `/Users/dido/Documents/Codex/2026-08-16/4/ep05_ep84_echo_host`
- SHA-256：`470fb802593918c9858f67fa62a61eff24a189f43a78cf964541abd80978b549`
- 已移除固定等待 50 秒；claim interface 後立即排入 EP05 OUT，OUT/IN timeout 均為 60 秒。

### v27 實機測試流程

1. 將 16GB 卡插入相機，冷開機。
2. 看到第二次彩條後接 USB；Mac 啟動 host。
3. 確認 host 顯示四輪 `EP05 -> EP84 echo success`。
4. 等相機顯示三次彩條。
5. 拔 USB，測試相機能否正常操作與正常關機。
6. 把卡插回 Mac，讀取 `R2737.BIN`、`CLEAN27.BIN`、`DONE27.BIN` 及最後 TRB 診斷。

成功條件：stage 7 marker 為 `0x27270707`、兩次 EndTransfer 有合理回傳、三次彩條後相機可正常關機。若 host 最後一輪收到 IO error，表示 3 秒仍不足或清理時序過早；先延長最後等待，不要移除 camera-side cleanup。

#### 2026-08-18 首次 v27 實機結果

- interface 1、EP84、EP05 枚舉正常。
- Host 的 round 0 EP05 OUT 立即回傳 `LIBUSB_ERROR_IO`；重新執行一次仍相同，推測 queued OUT 被 stage 0 的 EndTransfer 取消後 endpoint 保持 error/halt 狀態。
- 相機仍完成 stage 7，並顯示三次彩條。
- 三次彩條後拔 USB，相機可正常操作及正常關機。
- 結論：v27 的關機安全修正成功；transport 本輪未成功，下一版 host 應處理第一次取消、clear halt 或調整 queue 時序。

### 重要位址與函式

- handler：`0xC072E480`，v27 code range `0xC072E480–0xC072E6AB`。
- handler state：`0xC072E07C`；diagnostic base：`0xC072E080`。
- shared DMA pointer：`[0xC3757A7C]`。
- context 4 TRB pointer table：`[0xC31E3274]`。
- context 5 TRB pointer table：`[0xC31E3278]`。
- context 4 mode：`0xC31E38C8`。
- EndTransfer：ARM symbol `FUN_c01e6d48`，Thumb entry `0xC01E6D49`。
- StartTransfer wrapper：ARM symbol `FUN_c01e6b80`，Thumb entry `0xC01E6B81`；EP05 使用參數 10，EP84 使用參數 9。
- callback pointer：`0xC30257B0`；noop `0xC072DF4C`；DMA callback `0xC072DF54`。
- builder hook patch：`0xC04DC618 = 0xEB092B07`。

### 當時規劃的下一步（已被本文件前半部取代）

1. 先完成 v27 關機安全性驗證，不要同時加入 shell parser。
2. 若 v27 成功，再把四輪固定 echo 改成長駐命令迴圈。
3. 定義 host 的 `CLOSE` control packet；正常退出主動 CLOSE，camera side 仍保留 bounded timeout cleanup，避免 Mac 直接斷線時再次卡機。
4. Host 加入 SIGINT/SIGTERM handler，盡量 release interface；但 camera-side cleanup 不可依賴 host。
5. 最後再加入命令 framing、長度、sequence、status/error response，形成真正 Shell 基礎通道。

### 多 Agent 工具原型

已建立 `/Users/dido/Developer.localized/SIGMAfp_re/codex/fpshell_tool/`：

- `fpshelld`：唯一持有 libusb interface 1，透過 Unix socket 序列化所有請求。
- `fpshell`：Agent／使用者端 CLI，不直接接觸 USB。
- 支援 `STATUS`、`ECHO`、`QUIT`；socket 預設 `/tmp/fpshell.sock`。
- 目前仍受 v29/v30 相機 AutoRun 四輪上限約束；這是 host-side concurrency 架構原型，不是長駐 camera shell。
- Daemon SHA-256：`ce9f8a66185eff00cb43847e6c25f396f10c880d1355ebeaf14455b081a90b58`。
- 2026-08-18 實機：四個並行 client 分別送 `agent-A`～`agent-D`，daemon 正確序列化為 sequence 0～3；四個 echo 全部正確、無錯配，daemon 可正常 `QUIT`。
- 重要更正：上述成功傳輸後，即使 daemon 已 `QUIT` 且實體 USB 已拔除，相機仍可能無法關機。stage 7 的兩次 EndTransfer 雖回 0，仍不是完整 endpoint/service teardown。正式長駐版之前，需逆向 init 的對稱 deinit/unregister；目前安全恢復方式仍是拔電池 20–30 秒。

#### 2026-08-18 host 工具更新

- `fpshelld` 已加入 64-byte `FPSH` v1 binary frame、CRC32、sequence、status 與 44-byte payload；1024-byte EP05 packet 其餘部分補零。
- 支援 `STATUS`、`INFO`、`PING`、`ECHO`、`QUIT`，並提供 `--mock`、`--arm-wait`、`--limit`、`--socket`。
- `fpshell` 支援 `--json`、`--timeout`、`--socket`，並在本機先檢查 UTF-8 payload 上限，避免浪費 camera request。
- Unix socket mode 固定 `0600`。多 client 可同時連入，但 USB 操作由 daemon 單線序列化。
- `make test` 的五組 mock 測試全數通過；不需相機或 SD 卡。
- 詳細用法：`fpshell_tool/README.md`；wire format：`fpshell_tool/PROTOCOL.md`；相機長駐 worker 設計：`fpshell_tool/CAMERA_LOOP_DESIGN.md`。
- 工具階段以 v29 claim 後靜默 32 秒為基準，仍只有四個 camera request。v31–v33 關機 teardown 實驗不併入穩定工具。

### 相關檔案

- Assembly：`/Users/dido/Documents/Codex/2026-08-16/4/ep05_ep84_echo.S`
- v27 object：`/Users/dido/Documents/Codex/2026-08-16/4/ep05_ep84_echo_v27.o`
- Init：`/Users/dido/Documents/Codex/2026-08-16/4/ep84_bulk_init.S`
- Builder：`/Users/dido/Documents/Codex/2026-08-16/4/ep05_ep84_builder_hook.S`
- Host source：`/Users/dido/Documents/Codex/2026-08-16/4/ep05_ep84_echo_host.c`
- 研究日誌：`/Users/dido/Developer.localized/SIGMAfp_re/codex/PROJECT_LOG_2026-08-17_EP05_EP84.md`
- v27 寫卡前備份：`/Users/dido/Documents/Codex/2026-08-16/4/captures/v27_before_write_20260818/AutoRun.txt`
