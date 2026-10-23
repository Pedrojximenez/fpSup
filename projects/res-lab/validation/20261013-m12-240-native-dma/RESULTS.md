# M12240 v20：239.76p 改回原廠 DMA 表頭 — 2026-10-13（離線，未上機）

依據：成功的 A001_193（9/29，SSD 4809 幀）沒有 Gyro2 FSG2，且當時用原廠 DMA 表頭；
所有失敗片段都有 FSG2。使用者關閉 Gyro2 後由秒停改善為約 17 秒才停。
v19 在 239.76p 由 consumer 以 CPU 複製每幀 78,848 B 表頭（實機 hits 每幀一次，
DEBUG 下中位 2.85 ms，在 MovRec 管理工作內）。這是 9/29 之後新增、仍在每幀執行的工作。

改動（`changes.patch`）：`ogc_hdrcopy` 只在引擎 280p（0x438BDC32）使用 CPU 複製；
239.76p 回到原廠 C00FBB90 DMA。consumer VERSION 19→20。RCD、producer、loader、AutoRun 不變。

驗證：`test-header-copy.log` 8/8、`test-m12.log`（exact debug 卡）6/6 通過。
240 的測試期望改為走原廠路徑（v19 會失敗於此項）。只驗證軟體路徑，不模擬排程／SSD。

成品：`../../cards/20261013-m12-240-native-dma/{plain,debug,standalone}`；
32RESCUS.BIN SHA-256 `abf70106a7ca703d5491bd4af8e6d28e2521aedf81b669b9226307fc2983f16c`。
上機：只換 32RESCUS.BIN（保留卡上 CFG），Gyro2 維持停用，SSD 239.76p 驗收。

## 2026-10-14 上機（使用者手動 SSD）

v20（240：原廠 DMA 表頭＋原廠 64MiB）已部署、重開核對常駐碼；HS280／239.76p。
SD 3 秒對照：hits 0／0，94 幀 vbuf（SD 約 241 MB/s < 需求 262.6 MB/s，預期）。
使用者停用全部其他 Sup（含 shell），只留 RES-Custom，SSD 寫入模式改「標準」：
A001_314 2792 幀／WAV 11.69 s；A001_315 3394 幀／WAV 14.17 s；仍自動停止。
兩段全部 DNG TIFF 起點 0（先前 19456／65536 錯位消失）。每 0.5 s 檔案時間戳約 241–250 張直到結束，
長度不固定 → 符合突發寫入停頓超過約 0.39 s（94 張緩衝）而非每幀固定 CPU 缺口。
同 SSD 10/13 有 Sup 時 A001_304/305/307 約 2000–2100 幀。SSD 已用 61%（1.1 TB／1.9 TB）。
本段無原生 rec log（shell 停用）。

## 2026-10-14 01:50 使用者 SSD 兩段（＋一段短片）

A001_316：10-bit（925,696 B/檔）131 幀、WAV 0.59 s。
A001_317：10-bit 5094 幀、WAV 21.31 s，每秒 238–244 張穩定到結尾，TIFF 全在 0（需求約 221.9 MB/s）。
A001_318：12-bit（1,095,168 B）917 幀、WAV 3.86 s，TIFF 全在 0。
A001_317 已超過 A001_193（4809 幀／20.07 s）；停止方式（手動或自動）待使用者確認。
