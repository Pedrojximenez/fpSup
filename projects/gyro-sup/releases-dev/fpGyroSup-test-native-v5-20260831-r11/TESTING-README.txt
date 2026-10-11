fpGyroSup r11 原生 WaitEncoding 重複整段鎖測試

一次任務的完成順序固定為：

CinemaDNG 結束 -> GYR 關檔 -> 進入 WaitEncoding -> GCSV -> JSON -> 解鎖

r10 已證實錄影與 GYR 健康，但 DoWaitEnc 從 writer 呼叫時只登記延後切換；若
事件執行緒剛好在睡，下一個錄影鍵會先由 Standby 處理。r11 使用原廠的純喚醒
訊息，讓每一次錄影結束都立即完成 WaitEncoding 交接。

這版只修錄影／關機鎖，不改 GCSV 效能：
- GCSV 二進位與 r10 逐位元相同。
- 仍是 16 KiB 寫入與每段 5 ms 讓步。
- 不啟用開機掃描或復原補寫。

測試：
1. 開機等 fpSup!。
2. 錄製第一段 30～45 秒並停止；停止後立刻連按錄影鍵。預期在同片的 GCSV、
   JSON 完成前不會建立第二段。
3. 解鎖後錄製第二段 30～45 秒並停止，再立刻連按錄影鍵。預期第二次也會鎖住，
   直到第二段 GCSV、JSON 完成後才允許第三段。
4. 錄製第三段 30～45 秒，停止後立刻正常關機。預期相機等待第三段 GCSV、JSON
   完成才關機；請勿強制斷電。
5. 把卡放回讀卡器並說「讀卡」。

僅供 SIGMA fp Ver.5.02 測試。這是無 USB shell 的 release AutoRun。
