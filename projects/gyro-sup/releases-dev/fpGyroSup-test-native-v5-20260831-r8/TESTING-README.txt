fpGyroSup r8 單一錄影交易測試

一次任務的完成順序固定為：

CinemaDNG 結束 -> GYR 完整關檔 -> 同片 GCSV 完成 -> 同片 JSON 完成

與 r7 相比：
- 保留已成功錄製 46 秒、GYR 0 drop 的 MovieRecording 啟動閘門。
- 移除全域寫入相位探針。
- 不啟用開機掃描或復原補寫。
- GYR 關檔後不再回外層睡 5 ms，直接在同一 writer task 產生 GCSV。
- 不再先做完所有片段的 GCSV；每片的 GCSV、JSON 完成才前進。
- 正常失敗重試留在同一個 busy run，不插入外層空檔。

測試：
1. 開機等 fpSup!。
2. 以相同 CinemaDNG 設定錄製 45～60 秒並停止。
3. 停止後立刻嘗試再次錄影及關機，確認相機在 GCSV/JSON 完成前保持原生
   寫入保護；完成後才恢復操作。
4. 再錄第二段，確認同樣順利結束。
5. 放回讀卡器並說「讀卡」，我會核對 DNG、GYR、GCSV、JSON 的完整性與
   完成時間順序。

僅供 SIGMA fp Ver.5.02 測試。這是無 USB shell 的 release AutoRun。
