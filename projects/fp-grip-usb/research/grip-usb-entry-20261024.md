# Grip USB 入口與來源界線

日期：2026-10-24，Asia/Taipei。本輪工作是研究轉向、核對既有來源與安排下一個可判讀的入口；沒有新增實機能力。

使用者決定讓 LiDAR 接 Grip，再研究 Grip USB。官方列 Grip 的 USB-C 孔為 LiDAR、Motor、相機控制與電池充電；螢幕右側是相機控制孔。Grip／Hand Unit 的更新經 Ronin 手機 App，LiDAR 才是電腦版 Assistant 更新。這不能證明 Grip 充電孔一定沒有資料功能，但也不能把 LiDAR 更新孔的 DUML 協議套過來。[DJI 官方支援頁](https://www.dji.com/support/product/focus-pro)

既有 [控制器第17節](../../../dji_focus_pro/USB_PROTOCOL.md#17-focus-pro-相機-usb-直接參照與-sup-011-觀測版2026-10-21)已完成 df101fh/0505 的原始指令驗證：內部16＋float32經整數轉換，入action12佇列，再由相機任務／LUMIX driver組成 PTP9416(03010031)，data內容為屬性、長度4、u32數值；在USB scheduler之前停止。這提供真實程式入口，但不是實體Grip側錄，也沒有確認物理單位或測距來源。

來源 package 為 V01.02.0200_df101fh，模組0505/PJ18/v00.01.13.33，SHA-256 `4e2dec7e7bcbc4bcbf91d63c7f45a04b7c72098e31bcc56b3181a3e0b1c3676e`。公開索引產品名稱與程式內handle/wheel名稱曾不一致，現階段仍以package/module/hash識別，不因目錄叫grip就宣稱與使用者本體版本相符。

相機控制的參考程式由控制器作USB host、相機作PTP device；Mac的一般USB host連線不能代替相機，也不能僅接在旁邊取得Grip↔fp的對話。下一個測試取決於使用者選擇相機控制孔或充電孔，已詢問一次，尚未開始硬體操作。

本輪核對來源：[source-index.json](../evidence/20261024-scope01/source-index.json)。沿用既有原始bytes／離線結果，不重跑既有通過案例。舊 LiDAR 更新孔支線暫停接續，但封存資料保留；它的距離成功、DF/D6失敗或主韌體加密狀態均不算Grip USB結果。

官方手冊PDF的web讀取因檔案超過工具上限失敗，未以無法讀到的頁面作新依據；本輪官方用途核對來自可讀的支援頁。沒有下載新韌體、開啟USB、送命令、寫卡、修改相機或覆寫封存檔。
