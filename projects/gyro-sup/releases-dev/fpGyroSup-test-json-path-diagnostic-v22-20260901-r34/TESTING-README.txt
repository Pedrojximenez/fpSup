fpGyroSup r34：JSON 路徑診斷

1. 拔電池冷開機，等待 fpSup!。
2. 錄影 20～60 秒，正常停止，等待 SD 鎖解除。
3. 再錄第二段，正常停止並等鎖解除。
4. 正常關機後讀卡。

每段請檢查 DNG、GCSV、JSON，以及同檔名的 JDG：
- 有 JSON、無 JDG：正常。
- 無 JSON、有 JDG：把 JDG 內完整一行交回分析。
- 無 JSON、無 JDG：仍是有效結果，可能是診斷檔也無法開啟。

GCSV 仍應保留 r33 的 #FPD1 診斷尾行。本版只定位 JSON 消失路徑，
不把 GCSV 完整率視為已修復。
