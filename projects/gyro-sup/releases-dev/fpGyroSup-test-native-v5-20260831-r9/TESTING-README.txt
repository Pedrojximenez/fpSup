fpGyroSup r9 原生整段處理鎖測試

一次任務的完成順序固定為：

CinemaDNG 結束 -> GYR 完整關檔 -> GCSV 完成 -> JSON 完成 -> 解鎖

與 r8 相比：
- 保留已確認可長錄、GYR 0 drop 的 MovieRecording 啟動閘門。
- GCSV 與 JSON 開始前，透過相機正式的系統狀態更新入口宣告
  StillImageProcessing。
- GCSV 每 5 ms 主動讓步時仍保持原生鎖；不再因讓步而允許下一段錄影或
  太早關機。
- GCSV、JSON、重試與佇列中的後續片段都完成後，才透過同一正式入口解除。
- 不啟用開機掃描或復原補寫。

測試：
1. 開機等 fpSup!。
2. 以相同 CinemaDNG 設定錄製 45～60 秒並停止。
3. 停止後立刻按錄影鍵，再嘗試正常關機：預期新錄影不會開始，關機會等候；
   若畫面顯示影像處理中也屬預期。
4. 等鎖解除後，確認可正常開始第二段錄影，再錄 30～45 秒並停止。
5. 不要強制斷電。完成後把卡放回讀卡器並說「讀卡」，我會核對每段 DNG、
   GYR、GCSV、JSON 的筆數、完整性與完成時間順序。

僅供 SIGMA fp Ver.5.02 測試。這是無 USB shell 的 release AutoRun。
