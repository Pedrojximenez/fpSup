fpGyroSup r7 相位探針測試

這版只用來確認目前約 20 秒自動停止是否來自 CDNG／GYR 固定相位碰撞。

不變的部分：
- GYR 仍以 16 KiB A/B 緩衝串流，不把整段錄影留在記憶體。
- native lifecycle 仍負責片名、SD/SSD volume 與錄影結束。
- 錄影中不新增診斷檔案寫入。
- 機內 GCSV 仍會在錄影與原生建檔都完成後產生。

新增的量測：
- 每次完整 GYR block 相對於前一個 CDNG 寫入返回點的相位。
- GYR 進場時，外層 CDNG 寫入呼叫是否尚未返回。
- GYR 寫入呼叫的總等待＋寫入時間。
- .GYR 只在結束時多帶原本就存在的 72-byte 診斷區，magic 為 GFT6。

測試方式：
1. 使用與 A001_045～047 相同的 CinemaDNG 設定。
2. 開機等畫面顯示 fpSup!。
3. 錄一段至少 25 秒；若相機約 20 秒自行停止，不要立刻關機，等卡燈與後處理完成。
4. 最好再錄一段同設定作重複驗證。
5. 把卡放回讀卡器並說「讀卡」，我會解碼 GFT6 並比較最初四次與停止前四次寫入。

僅供 SIGMA fp Ver.5.02 測試。這是無 USB shell 的 release AutoRun。
探針只在有效的 SAG6 logger、ACTIVE 錄影及 CDNG adapter 下記錄；無效軟重啟
會還原共用寫入入口，不會把殘留跳轉留給下一個映像。
