# Grip USB 研究交接

2026-10-24，Asia/Taipei。使用者最新指示：「咱們改研究grid連usb吧 我的grid會接上lidar」。grid 暫按 Grip 理解。

## 已完成

- 本對話主線改為 LiDAR → Grip → USB → Mac／fp，獨立目錄 projects/fp-grip-usb。
- 已讀 dji_focus_pro/USB_PROTOCOL.md 第17節及 df101fh/0505 數值→PTP 原始反編譯與封存驗證結果。只是引用既有離線成果，沒有重跑成功測試或新增硬體能力。
- 官方已核對 Grip 四種 USB-C 孔的用途，以及 Grip 使用 Ronin App 更新；不要把充電孔稱作已驗證更新孔。
- 既有循環 focus-pro-lidar 已原地更新為「Focus Pro Grip USB 循環研發」，保留30分鐘間隔與本對話；不建立第二個排程。
- 上一輪 LiDAR 無 Grip 測試的接線問題／移除Grip待辦已被新方向取代；不要再催促使用者拔Grip。

## 唯一待回覆

已詢問一次：使用 Grip 螢幕右側相機控制孔連 fp、充電孔先連 Mac，或先研究兩孔。尚未回覆；不要假定已接好。沒有新的 USB／fp／Grip／LiDAR 操作。

收到選孔後先確認當下設備、版本與基準。相機孔以 host→PTP device 方法觀測；充電孔先確認有無資料列舉，不送任意命令。當前沒有實機結果。

## 離線接續點

- 原始參考 df101fh/0505 SHA 4e2dec7e7bcbc4bcbf91d63c7f45a04b7c72098e31bcc56b3181a3e0b1c3676e：60092EE0 的16＋float → action12 → 60093890 → LUMIX selector20(hex) → PTP9416/03010031。
- 未證明實體Grip版本、啟用條件、單位、無效值或LiDAR真正producer。相機控制孔被選定後，優先追該接收回呼的註冊／產品選擇與實機握手觀測，不重跑已封存的完整組包正例。
- 現有 fp 0.1.1 只觀測原始數值，仍有原廠拉焦回歸與未實作握手／FOV；使用前需依相機技能和相關 AGENTS 檢查現況。此轉向不等於授權盲刷或以猜值驅動鏡頭。
- 舊 LiDAR 本體 02:99 schema、無Grip冷開機、74組失敗解密假設保持原狀，暫不推進；只引用封存資料。
