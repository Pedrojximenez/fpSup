# QS／FPS 上機記錄 — 2026-10-15

**最新（run7）：** 目前卡上為 `combined-fix12`，實際卡檔 SHA-256
`faa27b8f655f7a3c6b23be8c80cc288553c7993cf0f68a7a2bf95b0814c33cf7`。
黑框往外加厚約 3 px，保留白字、字級與 fix10 的間距；對比色實拍確認四側外擴，最後已完整還原黑色。
開關 QS 後 1944 顯示完整 `29.97 FPS`；字形仍有差異。
舊圖 1910 是更新前原廠畫面，先前據此作出的「59.94 與原廠一致」判定已撤回。
首次 QS **延遲未解決**；最後正式量測是 fix4 的 **6.1161 s**，fix12 未重新計時。十一個模組均載入，已回待機。
重新接回的是另一張 loader／AutoRun 不同的卡，不能拿先前 4.02 秒與後來 3.16 秒算同卡改善。
最新成品與驗證見 [run7 外描邊](run7/RESULTS.md)；間距調整見 [run5](run5/RESULTS.md)，原廠對照見 [run4](run4/RESULTS.md)，接手歷史見 [run3](run3/RESULTS.md)。

## 下列為 run1／run2 歷史階段狀態

其中「尚未寫卡／尚未開始」只描述當時，已由上面的 run7 最新狀態取代。

結果：一次組裝的 QS 改動沒有明顯縮短首次等待。這是相機上的量測，不是離線模擬。

**後續上機（run2）：** 已寫入 FPS＋QS 合併版，首次 QSON 回覆 4.022509 s，QS_HITS=168、QS_RELOADS=0、QS_PACKFAIL=0。
原廠 GUI 計時 Update=3924 ms、Render=96 ms；第一張圖片前有 3.671385 s 間隔。
這只能定位到圖片載入之前，不能單獨確認是原廠解析或 consumer 的哪個路徑。
完整紀錄見 `run2/native-profile/`，GUI ring 136/256、overwrite=0，原有日誌未清除，兩個診斷旗標已還原。

合併版實際卡檔為 228,928 B，SHA-256 `df07d4cf334e5cfa193dde1b9d5539330ccf1c1919ba6051c0530653749a316b`，
整檔讀回相符、保留使用者 CFG；執行中固定 code 另逐位元組核對。原有 loader、AutoRun 和其他模組未改。
FPS 狀態為 VR_WHY=23（0x10+UIA_OP）、VR_UI=0、LV_RECORDS=0；擷取 `run2/1904-20261015-combined-before-fix.jpg`
顯示仍為原廠 59.94 FPS。使用者表示看不出差異，不能把此回饋當作新排版驗收。

已查到 `vr_template` 要返回 4 個選單＋29 個 LV 標籤，但 `uia_apply` 的 MAX_STRBASE=8。
修正獨立於 CSV slot 上限的文字返回容量，改為同一 block 可有的 64 個 strings；沒有改檔案格式、loader 或 AutoRun。
實際 C applier 的 33 個標籤及舊限制 mutation 2/2 通過；共用 applier 28/28；四個 LV 原廠 parser／資源測試 4/4；
保存 BIN 的 371 個 QS 記錄、12 個 LV 替換與 journal 還原通過。ARM uia_apply 靜態 stack frame 為 3208 B。
新候選 `combined-fix1/32RESCUS.BIN` SHA-256 `28e83a3db30462b4e0c52d6ab5fe6a5996162a82cdac927078db4cba5533d71a`。
這些仍是離線結果，不能取代實際 FPS 截圖或 QS 耗時驗收。

USB 隨後回報 NO_DEVICE，停用 RES-Custom 比較的 runner 在待機檢查即退出，未備份刪檔、未寫任何候選。
目前卡上仍為上面的合併版；`combined-fix1` 尚未寫入。同卡暫停 RES-Custom 的 QS 比較也尚未開始。
以下為先前兩版比較的歷史記錄，其中「卡上目前為 QS 版」已由本段後續狀態取代。

| 版本 | 重開後第一次 | 關閉再開第二次 |
|---|---:|---:|
| 舊 QS clone 邏輯 | 4.3424 s | 0.5300 s |
| 一次組裝 | 4.3268 s | 0.5274 s |

每版各量一次首次與第二次開啟。首次差約 0.016 s，不能據此確認效能改善。原先減少自訂記錄複製量的數字，不代表總開啟時間會等比例縮短；本輪不支持該段是主要瓶頸。下一步仍需分段量測原廠版面解析及圖片載入，不能把它們直接寫成已確認根因。

## 授權與測試條件

使用者要求上機測試，並確認將 RES-Custom 加入目前這張卡。實際卡原本沒有 RES-Custom／RESCUS 目錄；保有 00SHELL、10LOSS、20RECW、30FCAP、40GYR2 與 LOADER。CINE 待機、sd0、is_recording=0，沒有錄影或截圖，也沒有操作原有片段。

使用五個靜態格式 OG2K、OG3K、OG35K、OG4K、S16，未加入 RES-Lab producer 或虛擬 bootstrap row。兩版都使用 FPS 樣式修改前的版面與完全相同的 RCD。這是為適應目前沒有 RES-Lab 的卡所建的 plain consumer，與先前交付的 `../qs-only/32RESCUS.BIN`（Virtual RCD 版）不同。

- 比較基準 `baseline/32RESCUS.BIN`：184,128 B，SHA-256 `42d9869185808b2577fa421e490b25a09fbd5fe46294cdbef579e149dea1dd71`。
- 實際留在卡上的 QS 版 `optimized/32RESCUS.BIN`：184,064 B，SHA-256 `7e8bc253408c05fc71bd49358ebbde2a99884c4a4af269cd1d6fc130c059ae69`。
- 相機內載入程式的固定 code 區也逐位元組比對，並非只核對卡檔。五個 row 皆存在。
- 更新保留設定區 bytes 32..128；其 SHA-256 `2ea9ab9198d1638007400cd2c3bef1cc745b864b76011a0e1bc52180ac6452d4`。
- 基準版改成較短 QS 版時，先完整驗證 staging，刪除單一舊 BIN、確認消失，再寫入新檔；整檔讀回與實際目錄長度皆相符。

載入器及 AutoRun 沿用卡上原件，沒有重建或更換。事前備份在 `backup/manifest.json`；事後原有七個檔（AutoRun、LOADER、五個原有 Sup）整檔讀回與原備份相同。`LOAD.LOG` 的 4096 B 輸出已填滿，沒有結尾 DONE，不能只憑它證明所有後續模組的完整初始化。RES-Custom 的實際 code 與執行狀態另有直接核對。

## 計時方法與邊界

計時從送出單次 native `key QSON` 起，到 camera-side snapshot 讀到 `QS_CINE` 為止。QSON 本身回覆所需時間分別為 4.3413／0.5286 s 與 4.3233／0.5262 s，與活動畫面確認相近。這驗證 shell 輸入到活動畫面切換的時間，未量 LCD 掃描或真人按鍵的機械時間。

畫面快照在相機內一次讀 app → current screen → name，複製最多 32 bytes，並重查 app／screen 指標；不從主機拼接正在切換的多段指標。使用命名的 320 B cave claim 與已擁有的參數區，程式讀回驗證後先經原廠 D-cache／I-cache ROM helpers 發布才使用。葉函式沒有 firmware 呼叫，離線 8 個案例涵蓋原廠 C6 GUI heap、無效指標、未對齊指標及暫存器／堆疊保存。

首個快照嘗試的 C-region 界限過窄，當時 GUI app 在 C68FF318；未送 QS 按鍵就拒絕，handler 已還原。修正並離線核對後才首次開啟 QS，因此保留了同次開機的首次條件。

這張卡實測 QSOFF 回覆成功但只放開按鍵，沒有關閉 QS。第一次基準測試因此停止在有確認回覆的 QS 畫面，沒有重送不明命令；後來從已確認的 QS 狀態用下一個 QSON 按下關閉，完成第二次量測。之後每次 QSON 按下都以 QSOFF 放開，並再次核對畫面。原始回覆、恢復流程與全部時間保留在 `commands.jsonl`、`timing-baseline.json`、`timing-optimized.json`。

兩版測試結束時均 QS_BOOT=1、QS_RELOADS=0、QS_HITS=168、QS_N=7、QS_READY=1。本輪沒有觸發 consumer 的開機 cache 強制重建分支，因此先前由來源提出的「重建一次造成等待」只是一個條件路徑分析，不能當成本輪實測根因。

## 測試後狀態

兩版最後都回到 `LV_CINE_MEDIUM`、非錄影待機，echo handler 完整還原。原有服務只重新連線當前 socket 的已識別擁有者，沒有停止其他舊 daemon。每次 reboot 指令僅送一次；它的 USB IO 斷線回覆未重送，之後新 boot 的 worker 與已載入 code 皆確認。

最後七個原檔比對完成後，額外 row／pack 狀態核對遇到 `LIBUSB_ERROR_NO_DEVICE`。使用者隨後表示要自行實測 QS，因此停止所有相機命令，不重新連線或重送。`final-state.json` 的 phase 仍是 checking，不能把這項未完成的 pack 狀態核對寫成通過；前面的原檔比對及計時結果保持有效。

使用者回報「FPS 跑回去」，已詢問指文字樣式或格率設定值，尚未收到區分。另已離線建置包含 FPS 三段文字與 QS 改動的 `combined/`，但未寫卡、未重開，也未把這版當作本輪 QS 比較成品。物理開關／換卡十輪、錄影與 FPS 畫面驗收尚未做；240p 工作維持暫停。
