fpGyroSup r13 GCSV fast-path 實機測試

這版只最佳化 GCSV 十進位格式化，不改錄影生命週期與寫卡節奏：
- AutoRun.txt、VSHL.BIN 與正式 v1.1 完全相同。
- GCSV 仍每次寫 16 KiB，寫完讓步 5 ms。
- GYR -> GCSV -> JSON -> 解鎖的 native MovieSaving 交易不變。

測試方式：
1. 把 AutoRun.txt、VSHL.BIN、PGEN.BIN 當成同一組寫入卡片。
2. 開機等 fpSup!。
3. 錄製一段 45～60 秒 CinemaDNG，停止後立刻嘗試開始下一段。
4. 記下大約幾秒後相機接受第二段；第二段錄 10 秒左右即可停止。
5. 使用正常關機，等相機自行關閉，再把卡放回讀卡器說「讀卡」。

驗收：
- 第一段與第二段 GYR 都必須 dropped=0、error=0。
- 兩份 GCSV 資料列須與主機由 GYR 重建的六軸資料逐列一致。
- JSON 必須完整有效。
- 第一段 JSON 完成前不得建立第二段。
- 關機不得截斷第二段 sidecar。

這輪先驗證 45～60 秒的實際加速幅度；超過 35 分 47 秒的無號時間戳修正，等短測
通過後再安排長片驗證。
