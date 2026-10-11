SIGMA fp Ver.5.02 / Loader v3：獨立模組候選包

05STOPFX.BIN：原始社群停錄回收補丁，316 bytes。
10LOSS.BIN：拆分後 lossless，保留幀數優化與壓縮紀錄保護，不內嵌 stopfix。
兩個檔案由 Loader v3 各自載入；不需要啟用 lossless 才有 stopfix。
獨立 stopfix 不含 64 MiB 幀數優化。

先前 lossless-bulk-stop-20261012.zip 內的 10LOSS.BIN 含 stopfix，不能與獨立版並用。
本包已使用新拆分版。這個 05STOPFX.BIN 不適用直接加進舊版 v2 卡。

尚未實機驗證或寫卡；離線模擬不代表已證明硬體排程、DMA 與所有忙碌分支安全。
