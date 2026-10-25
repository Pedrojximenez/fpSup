# 相機 USB 身分決定數值對焦是否會送出

日期：2026-10-24（台北），heartbeat 11:42 UTC。離線研究 df101fh/0505/PJ18/v00.01.13.33；尚未與使用者實體 Grip 版本配對。USB 孔選擇仍待回覆，本輪沒有開啟裝置、網路、寫卡或操作 fp。

## 新結論與開發含意

**在這份控制器參考韌體中，SIGMA 身分會選到不處理數值對焦 selector 0x20 的 driver；同一個相機任務收到相同數值時，Panasonic 分支才會組出 PTP 9416／03010031。** SIGMA 分支回傳3，未呼叫 PTP transport；相機任務沒有檢查該回傳值，而是直接去取下一筆佇列資料。

這是對 fp 端實作的重要限制：只增加 `9416(03010031)` 接收 handler，不保證控制器會送來它。若採 fp-only 相容方案，還必須處理相機辨識與完整握手，或找到原生 SIGMA driver 另一個可用路徑。**此結果不代表 SIGMA 所有控制都不支援，也不表示只改 VID 就足夠**；目前沒有建置或部署新的 fp 相容層。

結果：[validation.json](../evidence/20261024-driver-gate02/validation.json)；工具：[verify_camera_driver_gate.py](../tools/verify_camera_driver_gate.py)。本輪沒有重做先前的完整命令註冊掃描或單獨 builder 正例；新增的驗證問題是實際的 VID 分類、ops 選擇與任務 gate 如何影響同一個數值 action。

## 原始身分分類及 ops 選擇

執行 `600943A4` 分類器，接著執行 `600942DC` 的實際 ops 複製。輸入 PID 是明列的合成值，不是假稱讀到 fp descriptor。

| VID／PID fixture | 分類回傳 | kind | 選到的 ioctl（Thumb 指標） |
| --- | --- | --- | --- |
| 1003／1234 | 1 | 8 | 600D7243（SIGMA） |
| 1003／5678 | 1 | 8 | 同上 |
| 04DA／1234 | 1 | 4 | 60096205（LUMIX） |
| FFFF／1234 | 0 | 0 | 未執行 ops 切換；保留初始通用表 |

原始 runtime 表 `20201620` 裡 SIGMA、Panasonic 的 PID 都是 FFFF wildcard；原始比較碼既接受相等 PID，也接受 FFFF。kind8 的 ops 原表為 `20201C4C`，kind4 為 `20201980`；複製至共用 `20201670`，+4 另改為共用回呼。SIGMA init 的原始日誌字串明列 Sigma；LUMIX 的名稱沿用已封存原始 init／driver 證據，非只憑 VID 猜標籤。

初始化 `.data` 與低位址執行區依先前已核對的 boot copy 表還原，不把 flash 字節直接當未初始化 RAM。裝置分類及 ops 複製執行真實指令；logger 是模型邊界。

## 相機任務的兩個 gate 與 driver 差異

原始任務 `60093890` 先從 `202114FC` 取走 action，然後檢查：

1. `202109A4` 的 ops 指標是否非零；為零會記錄 No camera line insert，再取下一筆。
2. `600E5CDC` 指向的 `2022D278` 首 byte 是否非零；為零直接取下一筆。

只有兩者通過才分派。action `0x12` 在 `60093A0C` 轉成 selector `0x20`，從 ops+20(hex) 呼叫 ioctl。此 byte 是這段程式的 gate，本輪**未驗證完整初始化如何寫入它**，不將設為1的 fixture 當成握手成功。

本輪以實際選出的共用 ops 表連接相機任務，但 `202109A4 → 20201670` 的安裝與 ready byte 是明列 fixture，尚未執行整個 device manager／初始化流程。佇列只提供一筆 `{action=0x12,value=1000}`；1000 是合成控制值，沒有指定毫米單位。

| 情境 | 原始任務結果 |
| --- | --- |
| SIGMA kind8、ops 有值、gate=1 | 呼叫600D7242，selector32，回傳3；沒有 PTP／lock／clock 呼叫，回到下一次 queue receive |
| Panasonic kind4、ops 有值、gate=1 | 呼叫60096204，組成9416／03010031，data含u32值1000；停在USB scheduler之前 |
| Panasonic、gate=0 | action已取出，未呼叫 ioctl，回到下一次 queue receive |
| ops 指標為零 | action已取出，記錄錯誤，未呼叫 ioctl |
| queue 回傳失敗 | 不分派，不產生封包 |

SIGMA dispatcher `600D7242` 對 selector 減3後比較0x12；0x20超出這個範圍，直接走 `600D7278` 的回傳3。只執行、驗證了這個拒絕分支，不推論其他 selector。任務在 `60093A16` 直接跳回接收迴圈，沒有重試或保存這筆數值的原始指令證據；這不排除其他上游 publisher 日後重送新值。

Panasonic 正例保留完整 command/data container，但這是離線 buffer，未真正發送。相機 session、ready、TID、transport state 都有 fixture；因此不能說完成了原廠相機握手。

## 來源與執行限制

- 原始映像：`dji_focus_pro/analysis/df101fh/df101fh_0505_v00.01.13.33_20240702_verified.bin`。
- SHA-256：`4e2dec7e7bcbc4bcbf91d63c7f45a04b7c72098e31bcc56b3181a3e0b1c3676e`。
- 每條實際執行指令記錄 runtime address、原檔 offset 與 bytes，逐一對回原始映像；不使用翻譯的 Python 分支取代分類器或 dispatcher。
- 原有 helper `verify_focus_handle_ptp.machine()` 只建立記憶體映射／boot copies，未執行它的 main，也未改寫舊結果。新測試在獨立 evidence 目錄。
- 模型邊界：queue、logger、clock、mutex／OS semaphore、camera ready／ops owner／PTP狀態；停止於真正 USB scheduler 前。未跑 USB enumerate、PTP session 初始化、真正 LiDAR producer、鏡頭移動或 Android App。
- 初次嘗試使用 dji_focus_pro/.venv 查離線套件時缺 capstone；系統 Python 原有 capstone5.0.7／unicorn2.1.4 可用，沒有安裝套件。實際新驗證 attempt1 通過；Unicorn 依先前環境限制在允許本地記憶體映射的執行環境離線運行，沒有裝置存取。
- `600309A4` 的既有 command record 為 local module0407、04:2F、handler60092EE1。只是原始表格／前輪註冊證據的引用，不是新可發往 Grip USB 的命令；本輪沒把內部 CAN 訊息當 USB setter。
- 這沒有新增 liveview／深度點雲、距離單位／有效性、實體 Grip 版本對應或 fp 實機能力。

## 下一輪具體未知

沿原始 LUMIX 初始化 `60096038` 追到：**什麼成功／失敗條件會寫入共用 gate；何時安裝實際 ops；哪些握手／能力回覆才會允許後續數值分派？** 先離線核對，不因 host identity 分流就直接改 fp VID，也不復用尚有原廠拉焦回歸的0.1.1成品上機。

USB孔問題仍只保留原先一次詢問，未再要求改線或拔Grip。若使用者選充電孔，實機優先改做資料列舉確認；本筆記依然只作相機控制孔的離線參考。
