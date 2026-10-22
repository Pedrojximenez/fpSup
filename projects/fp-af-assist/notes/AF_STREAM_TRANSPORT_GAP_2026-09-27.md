# AF 開發資料持續回傳：EP83 整合缺口

2026-09-27，離線來源稽核。使用者要求把機內 hook 資料持續回傳 USB，以降低逐次操作／讀 RAM 的成本。本文沒有相機 I/O、部署、loader／worker 修改或效能實測。

**同日後續增量：** [第一個 AF hook／高速通道紀錄](AF_FIRST_HOOK_CHANNEL_2026-09-27.md) 已加入同 daemon EP83 host consumer、獨立 USER 配置／export helper 與有限 H/L probe。下文「fpshd 不收 EP83」是修改前狀態；現在 source 有已測候選，但未替換 daemon，未接合 camera sender。現行 probe 的 shutdown journal 尚未驗證，live 預設封閉；相機唯讀 preflight 另回 NO_DEVICE。這些增量沒有解除本頁的相機端 endpoint／持續批次 ownership 缺口。

**建議下一個交付目標是「一次開啟、持續接收有界小批次」的觀測 session。** 每批有大小上限、序號、完整性檢查與明確記憶體交接；相機原廠 AF 不等待電腦。一次完整合成批次是傳輸最初的驗收項目，不應成為每次取樣都得重新安裝、開機或等滿大緩衝的工作流程。

## 現有程式可沿用到哪裡

| 部分 | 已有來源能力 | 還不是持續串流的原因 |
|---|---|---|
| 舊 H/L recorder | [af_publication.S](../highrate/af_publication.S)：`C022C858` 原 producer 執行一次，128-byte record、commit/complement、DMB、有限 append，hook 不做 USB | `count==capacity` 後 enabled=0、full=1；明文禁止 armed 時清除／重用。不是可循環的 ring。 |
| 四路 observer | [native_observer.S](../../../fpSup/focus/geometry/native_observer.S:10)：AF／lens／face／AAT 各自 40-byte state、256-byte record；單次 LDREX/STREX、不等待、滿載不覆寫 | 與舊 64-byte state／128-byte record 不相容，尚無批次交接或 live installer。現有 finite decoder 不能直接收四路格式。 |
| 封包／sender | [af_sender.c](../highrate/af_sender.c:55)：CPU-copy、CRC、publish、一次 Start／Wait、exact completion、故障 quarantine；[af_batch.py](../highrate/af_batch.py:58) 完整性解碼 | 硬要求舊 source identity、full=1、count=capacity、128-byte stride；只接受 fresh result。不是任意 raw payload 或 partial-batch sender。 |
| EP83 接收 | [ep83_receiver.py](../highrate/ep83_receiver.py)：正確 USB MPS buffer、絕對 deadline、nonce／長度／CRC，拒絕非末尾 short transfer | 只收一批，不 drain／重試／重同步；成功後還要由同 owner 驗 EP82 terminal。這些驗證值得保留。 |
| camera binding | [af_ep83_camera.c](../highrate/af_ep83_camera.c:591)：固定 build／mapping／TRB guards、persistent nonce consume、receipt | 第 638 行仍呼叫 `af_ep83_camera_make_synthetic`，並不是從真實 AF hook 取資料。private phase 與 nonce 是 single-use。 |
| camera control | [af_ep83_control.c](../highrate/af_ep83_control.c)：native usbTask mode-5 的 CMD4 候選，64-byte control／terminal，避開原 PTP parser | 第一次進入即令 persistent phase 非零；後續 invocation 拒絕。terminal 只 Start EP82，buffer 持續保留；沒有下一批前的 EP82 完成／重新武裝協定。 |
| host session／owner | [ep83_host_session.py](../highrate/ep83_host_session.py:274)、[ep83_libusb_owner.py](../highrate/ep83_libusb_owner.py)：一個 claim、一個 trigger、一批、一個 terminal，錯誤鎖定 | owner、sequence reservation、descriptor、trigger、terminal、session 都是 single-use，host 還硬要求 `camera_state=SYNT`。建立新 Python 物件不會解除相機端 quarantine 或證明 DMA 可重用。 |

舊最大批次為 `64 + 64 + 256×128 = 32,896 bytes`。目前 camera builder 仍明列 `deployment_ready=false`、`loader_integration_complete=false`、`single_usb_owner_verified=false`；這是正確狀態。[build_ep83_camera.py](../highrate/build_ep83_camera.py:301)

## 必須先修的三個實際整合缺口

1. **由現行共用載入流程取得自己的記憶體。** `build_guarded_loader.py:17` 仍鎖定舊 loader hash `e43b274…`；本次讀到維護版 hash 是 `53991350965bbdc8749ec779969ab46ee5fe20dca8fe1e664952256e89596471`。現在 loader 配置的是返回前釋放的 64 KiB staging，各 payload 自行保留常駐配置。highrate 的 `af_ep83_memory.c:80` 與 camera binding 仍把 `C3757A7C` 當作自己的 1 MiB pool descriptor；現行 shell worker 改用 `C072F050/F054/F058` 發布自己獨立的 pool／code。**更新來源 hash 或只換 pointer 常數，都沒有取得 AF buffer lease。** 新 launcher 應依 [SUP_BUILD_RULES](../../../fpSup/SUP_BUILD_RULES.md) 配置自己的 code/state/records/DMA，entry 返回，沿用 journal、D/I publication 與關機還原，不新增另一份 loader。

2. **收發雙方各只有一個 USB owner。** [fpshd.c](../../../fpSup/fp_usb_shell/host/fpshd.c:31) 只定義 EP01／EP82 與 CMD1／CMD3；其同步 socket loop 不消費 EP83，也沒有 AF83 CMD4 路由。現行 [worker.S](../../../fpSup/fp_usb_shell/camera/worker.S:49) 是文字 shell dispatcher，不是 highrate native mode-5 CMD4 adapter。`LibusbOwner` 又明確拒絕存在 `/tmp/fpshd.sock`，屬於另一個專用測試 owner，不能與 fpshd 各自 claim interface 0。為減少日常測試操作，建議把串流服務接進維護中的同一 host owner，以及對應的相機單一控制路徑；不要同時啟用 native CMD4 adapter 與原 worker 競爭 EP01/EP82。採哪個相機 owner 必須先作明確整合選擇。

3. **EP83 admission／mode／TRB 必須由相機 owner 一起管理。** 原廠 PTP event sender 會寫同一 EP83 TRB；只改 descriptor 不等於 controller 已是 bulk，也不排除原 sender。現有 [boot plan](../highrate/ep83_boot_plan.py:14) 的 `C01E5880` success-noop 與 `C07E2800` mode 2→1 只是候選，會影響原 event delivery；必須驗證與目前 shell、native USB task、enumeration／reset／關機的共存。[af_ep83_wait.c](../highrate/af_ep83_wait.c) 已有直接 RTOS event wait，避開舊 `C01E56F1 → C01E7780` 可能重武裝 EP01 的副作用，但這沒有自行建立 endpoint ownership。詳見 [sender ABI](EP83_SENDER_ABI_2026-09-16.md)。

獨立 libusb 路線另有小型路徑缺陷：`ep83_libusb_owner.py:21` 預設解析到不存在的 `projects/lib/libusb-1.0.dylib`；本地檔案在 `projects/usb-shell-sup/lib/libusb-1.0.dylib`。修路徑不會解決前述 owner 問題。

## 最小工程拆分與驗收順序

| 交付 | 最少新增／調整 | 驗收證據 |
|---|---|---|
| T0：真實單批 transport | 新的 owned-memory launcher 與目前 build 契約；單一相機 owner；同 host owner 接 EP83；沿用 exact completion／CRC／terminal 檢查 | 合成來源完整實收，保存 descriptor、送收長度、TRB receipt、nonce、原 bytes 與 terminal。Start 成功、mock 或只讀 context 不是實收。 |
| T1：同 session 連續小批次 | 將 fresh/complete/rejected/quarantined 擴成可逐批前進的 owner 狀態；只有確認上一批 DMA **及 EP82 terminal** 完成後才交還其 buffer；session nonce／batch sequence／來源 sequence 分開；stop／status 與有限 credits | 一次開始後連續多批，每批不需重啟／重安裝；測 stop、主機慢讀／退出／拔線、CRC／長度錯誤、terminal 遺失，故障後沒有盲目下一批。 |
| S0：真實單來源接入 | producer 有界提交、task 封裝／發送；至少雙 bank 或明確 single-producer queue；支援時間或數量門檻封批，低頻來源不必等滿 256 筆 | 主機接收時下一 bank 可繼續填寫；無撕裂／重用 in-flight buffer；量每批延遲、隊列峰值、source loss 與 hook 開销。 |
| S1：多來源 AF 觀測 | 各 producer 獨立 queue／序號，task 合併；為 FNR1／新 source schema 定義明確 version、stride、source ID、有效 payload 長度與 loss，不把它偽裝為舊 H/L AFB1 | AF／lens／face／AAT bytes 各走正確 decoder，來源不足仍保留 raw／unknown；先證交付完整性和原廠路徑仍運作。 |

T0、T1 用合成資料隔離 transport 問題；S0、S1 才接真實 hook。T1 的預定終點是有界小批次的長 session，不是把整段研究資料累積完才一次傳出。也不需要一开始增加 chained TRB／無限 DMA queue；單一 in-flight batch 加可繼續填寫的另一 bank，已可先建立連續觀測流程。

**不能只用 host while-loop 重新呼叫現有 one-shot。** 每批需要新的合法 consume 身分與重用交接；不能清零已 quarantine 的 private/result/control state。現有 framing 的 full=capacity 假設也要版本化處理，才能封送少於 bank capacity 的已提交前綴。consumer 不能在 producer 正寫入時改 capacity／nonce／count。

同 host owner 的 EP83 service 應用有限 receive buffer／磁碟輸出队列與明確 backpressure；shell/control 有獨立排程機會。不要把現行 `fpshd.exchange()` 的 EP82 stale-frame skip／drain／clear-halt 行為原封不動套到串流故障，亦不能讓它吞掉新協定的 terminal。二進位資料宜走 bounded binary channel 或直接落檔，逐筆 hex／JSON 不宜位於 hook 或 transport 關鍵路徑。

## 故障時只停觀測，原廠 AF 繼續

- hook 永遠先／後依原 ABI 完成原生呼叫，附加工作限於有界 copy＋commit；不執行 USB、wait、配置、檔案、重試或反向鏡頭控制。各 task 不共用未同步寫入索引。
- 沒有空 bank／queue 滿時記 loss 並略過附加紀錄，保持原 continuation；不覆寫 consumer 或 DMA 正持有的內容。新資料缺口可見，比延遲 AF 好；這是觀測器的預期退化方式。
- USB／主機／記錄故障只讓 telemetry session fault，停止接受新批次；不回收狀態不確定的 DMA buffer。保留原始故障證據；不自動 S1、REC、EndTransfer、USB global recovery 或重啟相機。
- 停止收資料不等於可以卸載 hook。code／state 要保留到 producer quiescence 與所有 consumer/DMA lifetime 都已證明結束；`full`、host 關 handle、Start return 都不是這個證明。
- 「AF 不受影響」是必須量測的驗收條件，還不是實機結論。除了 hook 開銷，也要驗發送 task 優先序、短 critical section、IRQ mask 恢復、記憶體／總線競爭與 USB 斷線時原廠 AF 進展。

本次僅完成來源對照；未重新執行全部 highrate suite，也未新增一筆 EP83 實收證據。既有 README 的歷史離線測試成績不等於現行 loader／worker 整合已通過。
