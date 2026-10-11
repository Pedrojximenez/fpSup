fpGyroSup r35：JSON builder 返回點診斷

1. 拔電池冷開機，等待 fpSup!。
2. 先錄 20～30 秒，正常停止並等待鎖解除。
3. 再錄 1～3 分鐘，正常停止並等待鎖解除。
4. 若停止後超過 30 秒仍鎖住，記下大約等待時間；不要連續開新錄影。
5. 正常關機後讀卡。

判讀：
- JSON 存在、JDG reason=8：builder 在一秒內成功。
- JSON 存在、JDG reason=7：builder 最後成功，但本身耗時至少一秒。
- JDG reason=0：builder 沒有返回，或後續 JDG 覆寫也失敗。
- JSON 與 JDG reason=8/7 且 attempts>1：前面曾失敗，後續重試成功。
- JSON 不存在、JDG 存在：依 FPJ2 reason/phase/elapsed/lifecycle/stream 定位。
- 兩者皆不存在：builder 未返回，或連 JDG 的 F_OPEN 也不可用。

GCSV 仍會輸出 r33/r34 的 #FPD1；r35 沒有修 writer back-pressure。
