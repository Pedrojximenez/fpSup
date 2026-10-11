fpGyroSup r12 原生 MovieSaving 整段交易測試

一次任務的完成順序固定為：

CinemaDNG 結束 -> GYR 關檔 -> 接管 MovieSaving -> GCSV -> JSON -> 解鎖

r10/r11 使用的 WaitEncoding 屬於 UI 事件狀態，實測無法可靠攔住 CinemaDNG。
r12 改用韌體核心錄影管理器本身檢查的 MovieSaving；正常關機也會等待同一欄位
清除，因此不需要復原補寫流程。

這版只更換原生生命週期鎖，不改 GCSV 效能：
- GCSV 二進位與 r11 逐位元相同。
- 仍是 16 KiB 寫入與每段 5 ms 讓步。
- 不啟用開機掃描或復原補寫。

測試：
1. 開機等 fpSup!。
2. 錄製第一段 30～45 秒並停止；停止後立刻連按錄影鍵。預期相機保持保存中、
   不建立第二段，直到第一段 GCSV、JSON 完成。
3. 解鎖後錄製第二段 30～45 秒，停止後立刻正常關機。預期相機等待第二段的
   GCSV、JSON 完成才關機；請勿強制斷電。
4. 把卡放回讀卡器並說「讀卡」。

若測試錄影鎖時意外建立了第二段，請停止錄影後直接讀卡，不必追加更多片段。

僅供 SIGMA fp Ver.5.02 測試。這是無 USB shell 的 release AutoRun。
