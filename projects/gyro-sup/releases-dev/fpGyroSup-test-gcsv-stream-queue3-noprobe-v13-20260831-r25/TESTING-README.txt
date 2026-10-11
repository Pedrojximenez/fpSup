fpGyroSup r25：三槽 logger／r23 PGEN 隔離測試

這一版保留 r24 的三槽 queue，但完全移除 back-pressure probe；PGEN.BIN 與
已成功產生 A001_017 GCSV/JSON 的 r23 逐位元一致。

只需錄一段約 10 秒：
1. 完整關機後放入卡片並開機，等到 fpSup!。
2. 再等約 3 秒，錄 10 秒後正常停止。
3. 等錄影鎖解除，正常關機，再把卡放回讀卡器並說「讀卡」。

這輪先不測激烈晃動；唯一驗收是同一資料夾內是否同時出現 GCSV 與 JSON。

- 若兩者出現：三槽 logger 可用，r24 問題在 probe/PGEN。
- 若兩者仍都沒有：問題在三槽常駐 logger 或其記憶體配置。

本版不會新增 GYR。三個啟動檔必須全部來自這個資料夾。
