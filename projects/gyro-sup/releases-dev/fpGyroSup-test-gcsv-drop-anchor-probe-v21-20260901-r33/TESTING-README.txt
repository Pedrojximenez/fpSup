fpGyroSup r33：分辨真實 drop_batch 與 timestamp anchor 假跳

本版沿用 r32 的錄影、GCSV、JSON、鎖定與寫卡流程，只在 GCSV 最後增加一行
不含逗號的診斷資料：

  #FPD1;drop_samples=N;max_block_head_tick_us=N

Gyroflow 現行 parser 會忽略單欄列，不會把它當成 gyro 或 accel 資料。

測試流程：
1. 拔電池冷開機，等待 fpSup!。
2. 先錄 20～30 秒，正常停止並等待鎖解除。
3. 確認可再次錄影後，錄約 5～10 分鐘，正常停止。
4. 正常關機後讀卡。

驗收與判讀：
- 每段必須都有 DNG、GCSV 與 JSON；GCSV 最後一行必須是 #FPD1 trailer。
- drop_samples=0 且 GCSV 有大接縫：可排除 producer 的 drop_batch；若
  max_block_head_tick_us 也異常大，便強烈支持 head→TickTimer 被延遲。
  這仍不能排除更上游的 sensor pause 或 hardware-ring overwrite。
- drop_samples>0：已直接證明 drop_batch；再依數值判斷缺多少筆。
- 短片先驗證 JSON 與鎖定均正常，才做長測。

停止條件：
- 缺 JSON、缺診斷 trailer、錄影自行停止、凍結或停止後鎖不解除。
- r33 是診斷版，不以其 trailer 作正式發布格式。
