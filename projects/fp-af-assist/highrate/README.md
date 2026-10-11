# fp AF 開發資料平台：由有限批次走向持續觀測

**2026-09-28：** 新增 `af_poff_guard.S`／`build_poff_guard.py`／`shutdown_restore.py` 與兩份測試；`af_hook_trial.py` 的 live gate 改為註冊並驗證自己的 power-off 還原物件（普通＋強制兩表），不再無條件封閉。細節與邊界見 [關機還原筆記](../notes/AF_POFF_RESTORE_GUARD_2026-09-28.md)。

**2026-09-27 最新優先序：本平台是 P0 第一優先。** 目標是一次啟動受限 session，將機內多接點原始資料以有界小批次持續傳回 USB，自動保存／重播，降低每輪研究成本。正常 AF 的估計、決策與控制仍在機內；電腦即時 AF 控制路線維持擱置。

- [平台階段與驗收](../notes/AF_TELEMETRY_PLATFORM_PLAN_2026-09-27.md)
- [事件／接點 catalog](../notes/AF_STREAM_HOOK_CATALOG_2026-09-27.md)
- [現行 transport／loader／owner 缺口](../notes/AF_STREAM_TRANSPORT_GAP_2026-09-27.md)
- [完整 AF 開發計畫](../PLAN.md)
- [第一個 AF hook／通道增量](../notes/AF_FIRST_HOOK_CHANNEL_2026-09-27.md)

**本輪新增：** `fpshd.c` 已有同 owner EP83 接收候選；`af_probe_helper.S`＋`af_hook_trial.py` 完成有限 H/L probe 的離線流程，第一批規劃以現行 EP82 raw bulk 取回。沒有替換 daemon，沒有上機 hook。相機 preflight 回 NO_DEVICE；probe 另因 shutdown journal 尚未驗證而預設禁止 live 派發，`--inspect` 明列 `live_ready=false`。詳細驗證、恢復缺口及下一步見上方增量紀錄。

**現在還不是可用的連續串流。** recorder、封包、sender/receiver 與 camera/control/memory/host binding 有離線候選；camera binding 仍製作 synthetic，host 要求 `SYNT`。五層 single-use（sender result、camera private、camera control、host session、LibusbOwner）尚未有跨批回收協定；AF／lens／face／AAT 的 256-byte observer 也未接到只接受舊 128-byte H/L finite capture 的 sender。沒有新增 EP83 真資料實收／吞吐／錄影影響證據。

現行整合另受三件事阻擋：guarded loader 來源契約／staging 生命周期改變，legacy `C3757A7C` pool 不能當 AF 已租用資源；新的 fpshd EP83 consumer 尚未接合相機 sender，而舊專用 LibusbOwner 與既有 daemon 互斥；相機 native PTP event producer、controller mode 和 EP83/TRB 仍需同 owner 管理。現有直接 RTOS wait 候選避開舊 WaitIn 的 EP01 rearm 副作用，不能因此略過 endpoint ownership。具體來源以 transport gap 及本輪增量為準。

交付順序：**有限合成實收 → 真資料單 source → 多 source → 受限 session 連續批次／owner 回收 → 錄影負載與自動分析**。有限合成只用來隔離 transport 問題；持續 session 是主要開發交付，不以逐批重裝、重啟或 host while-loop 重呼叫 one-shot 取代。bank/queue、common clock 與同 owner service 的离線設計可以並行。

資料路徑為 producer 有界 copy/commit → 有限 bank/queue → 獨立 task 封包／DMA → 單一 USB owner／EP83 → 同 host owner 接收落檔。控制通道只做 start/status/stop 與 terminal；hook 不做 USB，原廠 AF 不等待主機。所有 rate、成本與 loss 先量測，沒有資料就維持未知。

## 9/16 有限批次原型及歷史驗證

以下保留舊版資料契約、產物與當時實測。提及 pool 值、hash、候選位址、測試數量或「目前／第一輪」時均限該歷史版本，不構成現行 worker 的 lease 或持續串流能力；新整合以本頁上方三份文件為準。

2026-09-16：依使用者「心力放在高速通道，PTP 輪詢快不了」的指示，當時先建立有限 H/L 批次。
**已有離線可組譯／可測的 recorder、發送核心與接收元件；尚未部署，不是已可用的高速 AF。**

資料路徑：原生 H/L producer 返回 → 相機 RAM 有限取樣 → task-context 封包／DMA → EP83 → 主機驗證。
PTP／命令通道只留給啟停及前後狀態核對，不逐筆取得 H/L；hook 本身不執行 USB。

**本輪查明的實機整合卡點：EP83 不是空閒的專用通道。** 原廠 PTP event sender 也會改它的 TRB，
而現有 descriptor bulk patch 並未改 controller 的預設 mode-2/interrupt 設定。
正確 IN Wait 是 `C01E56F1`，不是舊 probe 的 `C01E4E81`。後續獲准的唯讀檢查已確認
live ctx3=`{mode=2,direction=1,endpoint=3,0}`，pool pointer=`0x44F6FE00`；
這不是 controller MMIO／排他 owner／pool lease 的驗收。
見 [實機原始紀錄](runtime-read-20260916-a.jsonl) 與 [EP83 sender ABI／ownership](../notes/EP83_SENDER_ABI_2026-09-16.md)。
在 native event admission、controller mode 與 TRB 排他使用未解決前，不產生固定地址 adapter、不上機。

## 既有有限批次實作

- `af_publication.S`：固定 `C022C858` 的 ARM wrapper，原 producer 恰好執行一次，
  精確保留原 SP／參數。recorder 不使用 stack、不呼叫函式、沒有迴圈；
  每筆 128 bytes，1..256 筆即停止，不覆寫。magic／schema／容量／model／nonce／full guards。
- `build_publication.py`：沿用專案維護中的 ARM assembler。明確要求 code/state/records 位址，
  檢查 alignment、overlap、wrap、branch range；CLI 另核對本機 ROM hash 和原 callsite。
  已拒絕覆蓋原 producer 與已知取樣來源；這份排除表不完整，不能取代 RAM ownership 證明。
  支援明確指定的 8-byte 近端 veneer，以跳到直接 BL 範圍外的 pool code；不自動選擇借用位址。
  沒有預設可用 RAM、installer、USB 或 camera I/O；manifest 明確標記 ownership/lifecycle 未驗證。
- `af_batch.py`：完整 finite-capture 解碼與 AFB1 reference encoder／incremental decoder。
  序號、nonce、commit/complement、固定長度及 header/body CRC32 全部驗證；錯誤鎖定，不重同步。
- `af_sender.c/.h`：無 heap／libc／全域狀態的 task-context 發送核心。
  完整 capture 檢查、CPU-copy、AFB1 CRC、DMA publish、單次 Start／Wait／completion check。
  firmware 操作使用注入 callbacks；**實際韌體 adapter 尚未完成，不能把 callbacks 全設成功部署**。
  Start／Wait／completion 不明時保留 DMA，不自動 End／free／重試；完成也不代表 hook 可拆。
  純 C completion checker 另拒絕 synthetic-End wake、HWO 未清、residue、TRB 身分及未知控制位。
  checker 不能自行建立 ownership；必須在同一排他 owner 下取得一致的 camera-side snapshot。
- `build_sender.py`：將同一份經 host 測試的 C 編譯為 ARM，再沿用維護中的 assembler 處理內部呼叫。
  拒絕外部 runtime symbols 或額外 data-section 依賴。只產生 core，不安裝、不啟動 task。
  `test_af_sender.py` 在上層，涵蓋 C/Python byte-for-byte、C→EP83 接收、各階段故障與重入。
- `build_test_bundle.py`：只用明確傳入的 lab-model 位址、nonce、capacity 與本機 ROM，整合 recorder、
  sender、選配 veneer、初始 state/records、manifest 與 SHA256SUMS；只建立不存在的新目錄，checksum 最後寫入。
  不含 installer／USB，所有 ownership、DMA mapping、lifecycle 與 hardware-validation 旗標皆為 false，**不是 AF beta**。
  `test_build_test_bundle.py` 的 7 項離線測試另驗證 CLI、精確 layout、hash、拒絕覆寫、direct/veneer 與錯誤 ROM。
- `ep83_receiver.py`：注入既有 USB owner 的 read 函式，不自行開裝置或發 trigger。
  單批、絕對 deadline、packet-size 對齊；只有恰好完成宣告長度的 terminal short read 可接受。
  沒有 drain／重試／重連，也尚未接入 `fpshd.c`。
  接收測試位於上層 `test_ep83_receiver.py`。
- `runtime_probe.py`：明確啟動才連既有 daemon，鎖定 AF lease，核對完整韌體 build，
  只讀 endpoint contexts `C31E3888..C31E38F7` 與 pool pointer `C3757A7C`。
  不重試、不跟隨 pool 指標、不借 echo、不寫相機；逐筆保存新 JSONL，拒絕覆寫。
  這是本次已授權的診斷範圍，不能當作任意 RAM 讀寫工具。
- `replay_batch.py`：離線驗證已存 AFB1，要求從獨立 run record 提供 expected nonce；
  輸入受 32,896-byte 上限約束，只接受 regular file，輸出新 JSON 且不覆寫。
  不把 file CRC 通過當成 USB 完成、曝光同步或可控制 AF。
- `ep83_boot_plan.py`：只讀本機完整 seg0 ROM、核對 SHA-256 與兩個 before-image，輸出
  **review-only JSON**。候選順序是先把 `C01E5880` 變成成功 no-op，再把 `C07E2800`
  的 ctx3 預設 mode 由 2 改為 1；它不產生 AutoRun、不寫卡、不連 USB，且固定標示
  `deployment_ready=false`、`adapter_complete=false`。這兩個候選字本身仍不構成 single owner。
- `test_highrate.py`：以實際組譯後 bytes 作窄 ARM instruction-model 測試，
  包含 guard、ABI、來源位址／byte width、每個未完成寫入前綴、滿載後三次回呼、
  256 筆的任意 chunk 解碼、逐 byte 毀損、stale nonce、截斷、extra bytes 和 bounded fuzz。

這是 CPU 指令子集合與封包測試，不是 IRQ／cache／USB 模擬，也不是實機延遲證據。

## 固定資料契約

Capture = 64-byte state + N × 128-byte record。
AFB1 = 64-byte transport header + capture；N=256 時總共 **32,896 bytes**。
相機 state 與 records 可以不相鄰；task-context sender 必須依此順序組合。

記錄包括 area-0 H/L、原生 cached lens position、獨立 AF-manager position、gain、曝光、
ROI 與 scheduler 前後狀態。cached lens position 只在 drive-end 更新，不是曝光對齊位置。
完整表格與 ABI 證據見 [recorder 契約](../notes/AF_HIGHRATE_RECORDER_CONTRACT_2026-09-16.md)。

解碼永遠回報 `usable_for_af_control=false`、`usable_for_dfd=false`、
`native_l_identity_verified=false`、`detach_verified=false`、`source_rate_hz=null`。
本地序號是 producer 返回次數，不是 sensor frame ID；CRC 只能驗證傳輸完整性。
每次 arm 必須使用新 nonce；同 nonce 的舊完整批次無法靠 CRC 或這個 decoder 辨別為重播。

## 歷史單批接線條件與新版延伸

當時 `fpshd.c` 沒有 EP83 consumer（9/27 已新增 host 候選，尚未上機）；既有 100/100 probe 只驗證 StartTransfer 被接受，
不是已收到 bytes。端點為 logical 3／physical 7，與 EP82 的 reply／drain 分開。

P0-A 第一個實收證據仍是 **一批一次送完**；以下為舊 H/L 接入流程的參考。完成單／多來源驗證後，P0-D 必須另實作受限 session 的連續交接，不能停留在這個 one-shot：

1. 明確取得 code、state、records、DMA staging 的排他 lease；不碰 shell 自有 scratch。
2. 完成 scheduler quiescence 下的 install/detach 與 D/I-cache publication。
3. camera task 在 full 後組合 AFB1；copy 到已取得 lease 的 DMA buffer，依已驗證映射處理 cache 可見性。
4. 同一 USB owner 預備 EP83 接收、一次 trigger、一次 Start/Wait、有界超時；核對 EP82 最終狀態。
5. 驗證 bytes／nonce／CRC／還原，再測連續批次；不自動重送結果不明的 trigger。

不得直接 DMA 讀 code cave；不得在錄影期間長期佔用 type-10 heap allocation。
既有 boot DMA pool 是可審查候選，不是這份程式已取得的 lease。
歷史候選為 [pool +0x50000..+0x65000](../notes/AF_HIGHRATE_MEMORY_PLAN_2026-09-16.md)，
另需近端 veneer；此 legacy pool 方案不適用現行 worker，須依共用 loader 取得新的常駐 lease，不能只改 pointer／hash。before-image 或零值不能取代排他 owner 證據。
`full=1` 只代表 record body 不再更新：hook 仍會執行並讀 state，**不能因此覆寫／回收任何區域**。

native-L selector/vtable、timing、observer、processing-state 與 UI/ROI 前後 guards 尚未整合。
前後相同亦不能排除中間改變後復原；因此本版本只產生診斷資料，未接入鏡頭控制。

## 離線測試

在本目錄執行：

```sh
/usr/bin/python3 -B -m unittest discover -s . -p 'test_*.py' -v
```

需要本機既有 clang 與 Capstone。測試中的 `C0800000`／`D0000000`／`D0001000`
只是模型地址，**不得當作實機可用位置**。這裡沒有任何部署或相機操作指令。

2026-09-16 已核對本機 fp 5.02 ROM SHA256，CLI 組譯成功。候選 recorder 現為 724 bytes，
最長模型路徑為 179 條 wrapper／recorder 指令（不含原生 producer）；不是執行時間上限。
task sender core 為 2,024 bytes，ARM 呼叫者須提供 8-byte 對齊 stack；firmware adapter 的空間另計。
取樣／格式／veneer 19 項、EP83 接收 25 項、C sender 13 項、唯讀 probe 5 項、既有 snapshot／bridge 回歸 30 項，合計 **92/92 通過**，
全程無相機 I/O。整組測試在上層 `fp-af-assist` 目錄執行：

```sh
/usr/bin/python3 -B -m unittest -v highrate.test_highrate highrate.test_runtime_probe test_ep83_receiver test_af_sender test_focus_snapshot test_focus_bridge
```

先前 `../transport_native/` 的 native-owner 草稿依最新優先序暫停，不是本高速路徑的先決條件；
現行 USB 異常鎖仍保留，不能因改用 EP83 就忽略控制通道的不確定狀態。

## 歷史 cold-boot candidate 的副作用與更正

ROM／decomp 核對支持候選 before-image：`C01E5880` 為 `4DF0E92D`，`C07E2800` 為
`00000002`；`C01E5880` 的 source xrefs 包括 `C01E8158` 與 `C01E91D0`，而
`C01E67F8` 會把 `C07E2800` 的 ctx3 預設 tuple 複製到 runtime context。

但 `C01E7780` 的 mode-1 completion 路徑還有一個具體 blocker：在
`C31E3974 != 1 && C31E3A08 == 0` 時，它會經 `C01E60E0` 選 bulk OUT、重寫其 TRB 並
Start OUT。也就是 WaitIn(3) 可能順手重武裝 EP01，與現有 worker/native PTP shared routing
衝突。尚未關閉這個副作用與 lifecycle 前，JSON plan 的 preflight 必須維持失敗；不得把
兩個 candidate words 當成已完成 adapter 或 live installer。候選只適合另行授權後的冷啟動、
未接 USB、single-worker owner 與明確 DMA lease 設計審查；回復路徑是不用候選 patch 重新啟動。

本輪後續已執行一次限定 live probe：host STATUS、native version、上述兩項 RAM reads 均成功；
韌體符合 w71c1 / 5.02.0.V91 / 完整 build hash，三筆相機命令未重送。
沒有寫卡、部署、模式修改或鏡頭動作；沒有量到 EP83 傳輸速度，不能稱為高速 AF 已完成。

## 9/16 具體產物

- [offline-test-a0-20260916/manifest.json](artifacts/offline-test-a0-20260916/manifest.json)：
  已實際編譯 recorder 724 bytes、sender 2,024 bytes、8-byte veneer 與容量 256 的初始影像；
  9 個文件 SHA256SUMS 全部核對通過，builder hash 也吻合目前 source。
  地址全為明確的未租用 lab-model，`deployment_ready=false`，**不是 AF beta，不能裝相機**。
- [ep83-boot-review-20260916.json](artifacts/ep83-boot-review-20260916.json)：核對完整 ROM 與兩個
  before-images 後產生的審查方案，不是開機檔；保留三項未解 blocker 和 preflight=false。
- [runtime-read-20260916-a.jsonl](runtime-read-20260916-a.jsonl)：本輪唯一 live 操作的完整紀錄。

離線重播（`NEW.json` 不可存在；nonce 必須來自獨立的本輪記錄）：

```sh
/usr/bin/python3 -B highrate/replay_batch.py CAPTURE.afb --expected-nonce 0xYOUR_NONCE --output NEW.json
```

本輪增加重播 5 項、bundle 7 項、boot plan 4 項測試。根目錄完整回歸 **386/386 通過**，含 UI localhost tests；
這些是離線測試，與上述 live read 分開計算，不包含一次實際 EP83 bulk delivery。
