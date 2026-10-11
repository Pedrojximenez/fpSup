fpSup-GYRO GCSV 直接輸出優化 — 2026-10-01 開始，10-02 完成

狀態
已修改來源並完成離線 ARM 驗證與建置。尚未上機，不能宣稱已修復音訊漂移。
本輪不啟用先前的 --format-yield 排程診斷，不改 writer 優先級、原始擷取、採樣、
每個原始區塊一次寫入或寫卡方式。既有 opt-in 診斷仍保留且通過回歸。

修改
fpSup/gyro/gcsv_rows.S：
1. put_u32 先決定位數，直接由最終輸出位置往前填數字；移除數字 stack scratch
   與逐 byte 重抄。完整支援 uint32；文字使用 byte store，允許任意位址對齊。
   共用十進位 pair table，新增 72 bytes 位數與十次方小表，沒有 40 KB 大查表。
2. gcsv_format 在持有原始區塊期間僅保留待輸出樣本的指標；每次返回前，才把仍未
   輸出的最後一筆複製到 G_HELD。區塊釋放後沒有殘留指向它的指標。
Base 的 JSON 也使用 put_u32，所以 Base BIN 會改變；其原始 GYR writer 路徑未改。

量測
真實 ARM gcsv_format + gcsv_last，各處理 2,048 records（2,008 gyro + 40 accel）：
案例                      修改前指令   修改後指令   減少       文字 bytes
小數值／起始時間戳         400,398      282,908      29.343%    23,266
極值／較大時間戳           777,126      669,756      13.816%    56,984
兩組輸出皆與修改前及獨立 Python 格式規則逐 byte 相同。
上述兩組 G_HELD 樣本暫存寫入皆由 16,064 bytes 降至 8 bytes。
這是合成輸入的 ARM 指令與記憶體操作計數，不是 CPU cycles、實機速度或音訊修復證據。
完整數據與 blob/output hashes：instruction-counts.json。

驗證
- test_gcsv_direct + test_gcsv_yield：15 項通過、零跳過，見 direct-tests.log。
  實際執行全部 unsigned 16-bit、signed 16-bit 與 +32768、uint32 邊界和隨機值；
  驗證四種輸出對齊、前後界限、ABI/SP、空輸入、連續 accel、小輸出空間、uint32
  計數回繞、原始區塊立即覆寫、結尾最後一筆與每區塊一次寫入。
  故意移除 G_HELD 返回前的 copy 會被測試抓到；yield 停用的變異亦被抓到。
- JSON ji/jm/jhalf：GCSV／Base／yield 版本共 1,278 個案例與 baseline／Python
  oracle 相同；奇數輸出位址、guards、暫存器及 SP 驗證通過。
- 原有 test_gcsv_format、test_imu_stream、test_lifecycle、test_safety：117 項中
  116 項通過，1 項既存失敗。test_nothing_claims_an_address_in_the_arena 指出
  lossless/card_status.py:22 與 lossless/test_card_emulation.py:41 使用 C072E064。
  與前一輪相同，未修改這些檔案或放寬檢查。見 regression-tests.log。
- 12 個建置通過：GCSV／Base × plain／debug／Fast × before／after。每組 AutoRun
  逐 byte 相同；loader 配置不變時，這次 payload 改動不要求更新 AutoRun。
  驗证每個成品含有實際組譯、修補後的 launcher/writer、routine table 與 entry；
  before 原始 blob 與保存基準一致。見 build-report.json、build.log。
  未重跑未更動的共用 loader 硬體或完整開機模擬；建置檢查不等於上機驗收。

產物
builds/after-gcsv-plain/ 是一般 GCSV 離線測試版；同層另有 Base、debug 與 Fast 對照。
均來自本機工作區（含既有修改），不是凍結發行版的逐 byte 重建，也未覆寫正式版。
一般 GCSV fpSup.BIN SHA-256：
247b1cb3095c25865785bd2ff42b28fdc3a548a00e54fd96e5092a5aba913b89
一般 GCSV AutoRun.txt SHA-256：
15d1c118a7c62da739b0523f06891cf7eab754aada06a667e6e1dbfb04c00459
其他 hashes 及命令在 build-report.json。hash 僅供追溯，不構成 runtime 配對限制。

重現（專案根目錄）
python3 -B fpSup/gyro/build_base_card.py --edition gcsv --version direct-test-20261001 --banner fpSup-Gyro-direct! --out projects/gyro-sup/validation/20261001-gcsv-direct-output/builds/after-gcsv-plain
python3 -B projects/gyro-sup/validation/20261001-gcsv-direct-output/verify_builds.py
在 fpSup/gyro 執行：python3 -B -m unittest test_gcsv_direct test_gcsv_yield
在 fpSup/gyro 執行：python3 -B -m unittest test_gcsv_format test_imu_stream test_lifecycle test_safety
本機 sandbox 限制 Unicorn JIT；本輪 ARM 測試在獲准的離線執行環境成功完成。
若只出現 skipped，不能視為 ARM 驗證通過。純 fpSup checkout 缺研究基準檔時，
核心目前版本測試仍可執行，只有 before/after 計數測試需研究樹中的 baseline。

追溯
before/：優化前來源、raw blobs 與 symbols；direct-output.patch：本輪格式化修改。
source-manifest.json：工作區 HEAD 與來源 hashes。
fpSup/gyro/test_gcsv_direct.py：新增 ARM 測試。
本輪未寫卡、操作相機、commit、push 或發布。
