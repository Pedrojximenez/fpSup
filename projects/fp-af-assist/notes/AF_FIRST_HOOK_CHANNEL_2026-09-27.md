# 第一個 AF hook 與高速通道增量

2026-09-27。使用者要求先完善高速通道，試著取得一個 AF 函式的資料。本輪完成主機 EP83 接收增量、ARM 配置／匯出 helper 與有限 H/L hook 安裝流程的離線實作。**尚未安裝 hook、沒有相機 AF 批次實收。**

**2026-09-28 核對：** 本頁四列的驗證界線已逐列覆核，全部相符；執行中的 daemon 仍是 9/25 的 binary（無 `EP83`，STATUS 自報 `transport=EP01-EP82`）。已完善並上機量過的高速通道是 shell 的 EP01/EP82 回覆路徑（相機→主機 73 MB/s），EP83 仍無一筆實收。見 [高速通道現況核對](AF_CHANNEL_STATE_VERIFY_2026-09-28.md)。

## 已完成的程式

| 部分 | 內容 | 驗證界線 |
|---|---|---|
| 同 daemon EP83 接收 | [fpshd.c](../../../fpSup/fp_usb_shell/host/fpshd.c)：`EP83 <bytes> <shellline>`；沿用既有 libusb handle/interface，不另開 owner。先 trigger，再收 EP83，再驗 EP82 terminal | 主機候選已編譯及測試，未替換執行中的 daemon；不代表相機 sender／PTP exclusion 已完成 |
| ARM helper | [af_probe_helper.S](../highrate/af_probe_helper.S)：1100 bytes；一次配置自己的 64 KiB USER 記憶體、驗 CP15／MMU noncache mapping、完整 capture 匯出前 D-cache publication | 真實機器碼由 Unicorn 執行，allocator／韌體呼叫由測試模型提供；未在相機呼叫 |
| 有限 hook 試驗流程 | [af_hook_trial.py](../highrate/af_hook_trial.py)：完整 CINE 基線、ROM 與現行 worker bytes 核對、boot-scoped cave claims、code/state publication、有限填滿、還原入口、EP82 raw bulk 匯出及 nonce 解碼 | 安裝／故障路徑用 mock 驗證；**預設 live guard 關閉，沒有強制略過選項** |
| recorder | 沿用 [af_publication.S](../highrate/af_publication.S)，724 bytes；`C022C858` 原字 `EB00485C` 呼叫 `C023E9D0`，返回 `C022C85C` | 保留原 SP、原廠呼叫恰一次；hook 只做有限 copy/commit，沒有 USB、配置、wait 或鏡頭命令 |

首批計畫容量 64，每筆 128 bytes，含 64-byte header 合計 **8,256 bytes**。資料含 area-0 H/L、cached lens position、scheduler／ROI／曝光等原始 context。原廠 producer 次數不是 sensor frame ID；首次 AF／DFD／幾何有效性仍為 false。

本次分開兩個增量：EP83 接收向長期專用串流通道前進；第一個真實來源試驗可以先用現行 shell 已支援的 **EP82 raw bulk**，一次取回有限批次，避免逐筆讀 H/L。後者不是 EP83 驗收，也沒有重新啟用電腦控制對焦的產品路線。

EP83 socket 成功回覆為 `OK83 <bytes> <sequence>\n` 加指定長度的 binary。上限 65,536 bytes、單次 trigger、2 秒整體期限、MPS 對齊、精確末尾 short read、同 sequence／CRC／status 的 EP82 terminal。OUT 派發後結果不明會鎖住 daemon 的後續相機交換，不 drain／clear-halt／自動重送；重啟 daemon 不代表相機 DMA 已結束。AF payload 的 nonce／schema／CRC 仍由上層驗證，daemon 本身不賦予 AF 有效性。

## 本輪相機結果

[20:30 唯讀 preflight 原始紀錄](../highrate/artifacts/hook-preflight-20260927.jsonl)：host STATUS 成功，但第一個相機 `version` 立即回 `LIBUSB_ERROR_NO_DEVICE moved=0/64`。當輪已鎖定 fault，未重送、未配置／寫 RAM、未 hook、未送按鍵／設定或鏡頭命令。

既有 daemon、PTP guards 與卡片均未替換。`STATUS camera=open` 是舊 handle 狀態，不能當作目前已能使用相機。先前 13:36 的 CINE 基線仍保留為歷史證據。

## 實測前尚須閉合的恢復條件

除了 USB 重新可用，還有一項實際程式缺口：**目前 probe 未驗證 AF callsite 與借用 echo 的 loader 關機還原。** 正常完成會還原並讀回；USB 中斷時不盲目再寫，所有 helper／code／state／records／veneer 保留。但這只能避免當次 boot 的資源重用，不能把暖重啟當成恢復。

[SUP_BUILD_RULES](../../../fpSup/SUP_BUILD_RULES.md) 說明：撥電源開關會保留 firmware/cave，但重建 heap。若 AF 入口還指向舊 heap，暖開機有懸空指標風險。因此 `verify_shutdown_restore()` 尚未完成前，`--run-live-hook` 會在任何相機 I/O 前落檔 `status=blocked`；`--inspect` 明列 `live_ready=false`。沒有把這件事留成可忽略的提示。

核對 [stage2.S](../../../fpSup/fp_usb_shell/asm/stage2.S) 得到：

- journal 依 section table 配置精確容量，沒有 runtime append API 或公開剩餘容量；不在 RAM 裡自行延長它。
- 可選 `LH_MARK+8` 在 callback 註冊前便發布物件地址，因此 marker 不是已註冊證據。
- 還原記錄保存的是 section 寫入前的 live 字。普通冷啟動進入 stage2 時 echo 可能仍借給 `lboot`；只加 `--also ECHO:原字` 不能證明 journal 最終還原到原廠 echo。
- ROM 的 PowerOff manager 為 `C30756C4`，普通／強制表各 10 格。後續 verifier 可核對兩表有效前綴交集、完整 callback bytes、boot 前後一致；journal 沒有 count／capacity／allocation-end，還必須搭配**實際卡的 VBIN manifest**推導有界讀取及兩個目標的最終還原值。

這裡沒有修改共用 loader、卡片或韌體映像。需沿用維護中的 builder 完成具體還原安排，不能單純改 hash、宣告已持有舊 pool，或重新啟動來略過此條件。

## 離線驗證與重現

- EP83 host：11 tests 通過，使用實際 `fpshd.c`＋fake libusb；包含長度／MPS 組合、舊 handle 重用、超時、OUT／資料／terminal 異常、sequence／CRC、錯誤鎖定。
- Recorder／格式：19 tests 通過，涵蓋原廠 ABI、commit、滿載不覆寫、錯誤資料及 nonce。
- ARM helper：18 個 Unicorn tests 通過；覆蓋 allocation、CP15／32 個 supersection descriptor、export 前重驗、header、D-cache 順序；移除三項保護的 mutation 都被抓到。
- Installer：成功／失敗流程及 production live gate 的測試結果另見 [本輪驗證摘要](../highrate/artifacts/hook-offline-20260927-v2/validation.json)。這些測試不取代實際 shutdown／DMA／AF 光學驗證。
- [目前來源與 inspect 結果](../highrate/artifacts/hook-offline-20260927-v2/inspect.json)／[來源雜湊](../highrate/artifacts/hook-offline-20260927-v2/sources.json)。早一輪 `hook-offline-20260927` 是加入 shutdown gate 前的歷史輸出，以 v2 為準。

專案根的離線檢查：

```sh
python3 -B projects/fp-af-assist/highrate/af_hook_trial.py --inspect --output NEW_DIRECTORY
python3 -B fpSup/fp_usb_shell/host/tests/test_ep83_host.py
```

在 `projects/fp-af-assist` 執行相關 Python tests；ARM helper 需要已安裝 Unicorn／Capstone 的 Python，且 macOS 需允許離線 JIT：

```sh
python3 -B -m unittest -v highrate.test_highrate highrate.test_af_probe_helper highrate.test_af_hook_trial
```

## 接續順序

1. 核對實際卡片來源／manifest 與 loader 的正常、強制關機還原；修完後用真實 loader ARM 模擬故障／暖開機路徑，再解除 production live gate。
2. USB 可用時重新做當輪 CINE／ROM／worker／boot 基線，有限 hook 64 筆並以 EP82 bulk 實收，保存原 bytes、nonce、還原及設定核對。第一輪不自動錄影或送 S1。
3. 整合相機 EP83 sender 的 native PTP admission、mode／TRB、獨立 DMA lease 與完成回報，再使用新的同 daemon consumer；不能用普通 `SHL` 派發一個等待 EP83 讀取的 sender。
4. 實收驗證後才擴充為雙 bank／有限連續 session、多來源及 CINE 錄影負載。host while-loop 重跑單批不能取代 camera-side ownership 交接。
