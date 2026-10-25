LCD Backlight v0.1.0test — SIGMA fp Ver.5.02 / Loader v4

檔案：Backlight_v0.1.0test.BIN
加入既有 Loader v4 配置的位置：\fpSup\Backlight_v0.1.0test.BIN
不需要為本 sup 更新 AutoRun.txt 或 LOADER.BIN；Loader v3 不支援 FSB4。

載入時：原廠背光電流設定 18 → 20，名義電流約 +10.53%。
這不是量測的尼特數增幅；本版只有離線驗證，未在相機上測試。

fpSup 頁 → LCD Backlight：
  Lower   降一格，最低 Stock（原廠 18）
  中間列  Stock / Boost 1…13，顯示最近一次確認的等級
  Higher  升一格，最高 Boost 13（晶片設定 31）

設定不儲存：下一次載入回到本檔預設值 20。
若 SupManager 停用或移除此 sup，下次開機由原生初始化回到 18。
遇到 Unknown 表示無法確認硬體狀態，本次開機不再由本 sup 寫入。

已保留同一暫存器的其他電源欄位；每次更改均讀回確認。
沒有韌體 hook、常駐 task、初始化表補丁或相機設定區寫入。

來源：fpSup/backlight/
研究：projects/lcd-brightness/BACKLIGHT_CURRENT_2026-10-25.md
建置與來源雜湊：build.json
實際交付檔案的離線驗證：validation.json、test-results.txt
結果：14 項通過，0 跳過。Instant/Fast 使用目前標準的含開機圖組態。
實測亮度、功耗、溫升與長時間使用能力仍待相機驗證。
