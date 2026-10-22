fpSup-GYRO GCSV 直接輸出優化 — 2026-10-04

已完成來源修改、實際 ARM 離線測試及本機建置；尚未上機，音訊問題未經修復驗證。

修改範圍
1. put_u32 直接填入最終文字緩衝，省掉數字暫存與重抄，完整支援 uint32。
2. gcsv_format 處理區塊期間以指標保留樣本；返回前只保存最後一筆未輸出的樣本，
   不留下指向已釋放區塊的指標。
感測器擷取、採樣、writer 優先級 6、排程與每個原始區塊一次寫入均維持原狀。
本次沒有加入先前的 yield 診斷。Base 的 JSON 共用數字函式，因此 Base BIN 也會變。

量測（各 2,048 records，2,008 gyro + 40 accel）
小數值／起始時間戳：400,398 → 282,908 ARM 指令，減少 29.343%。
極值／較大時間戳：777,126 → 669,756 ARM 指令，減少 13.816%。
兩組輸出與修改前及独立格式規則逐 byte 相同；每組 G_HELD 樣本暫存寫入從
16,064 bytes 降至 8 bytes。這是合成輸入的指令／記憶體操作計數，不是實機耗時。
詳見 instruction-counts.json。

本輪驗證
- 獨立 test_gcsv_direct：10 項通過，零失敗、零跳過，16.465 秒。
  實際執行完整 unsigned/signed 16-bit、+32768、uint32 邊界與隨機值；涵蓋
  所有輸出對齊、前後界限、ABI/SP、跨呼叫原始區塊覆寫、空資料、連續 accel、
  小緩衝、計數回繞、最後一筆與單次寫入，以及 Base/GCSV JSON 數字 helper。
  故意移除返回前保存樣本的機器碼會被測試抓到。見 direct-tests.log。
- 共用 boot_chain、loader_hook、splash：29 項通過，零跳過；測試前後來源穩定。
  見 shared-chain-recheck.log/.json。首次舊測試未明確指定 legacy 啟動畫面選項
  所造成的失敗另存 shared-chain-tests.log/.json；外部工作補上明確選項後重驗，
  原有斷言未放寬。本輪未修改共用載入程式或這些測試。
- 舊 gyro 格式、串流、生命週期與安全檢查：117 項中 116 通過，1 項既存失敗。
  test_nothing_claims_an_address_in_the_arena 指出 lossless/card_status.py:22、
  lossless/test_card_emulation.py:41 使用 C072E064；與前輪相同，未放寬檢查。
  見 regression-tests.log。
- GCSV／Base × plain／debug／Fast × before／after：12 組建置全部通過。
  本輪六組對應 AutoRun、UI assets 及其他元件皆相同，僅 payload 相關內容改變。
  launcher、writer、routine table、entry、區段順序與邊界均核對成功；目前 builder
  的 AutoRun 起首 NOP／交接前三次 restore 也已檢查。建置前後來源 hashes 穩定。
  見 build-report.json、build.log；使用目前 Fast Start 3 流程。

產物與追溯
builds/after-gcsv-plain/：一般 GCSV 離線測試版（不含 USB shell）；同層為其他對照。
測試包保留完整 AutoRun.txt、fpSup.BIN 與 FPSUPUI 資料夾；本 README 取代 builder
產生的通用產品說明，避免將歷史產品敘述誤認為本輪實拍結果。
同一 loader／封裝配置下，本次優化不要求更新 AutoRun；這不宣稱可與其他日期或
其他封裝配置的 AutoRun 混用。10/04 的建置流程與 10/01 不同，請依本輪產物識別。

一般 GCSV fpSup.BIN SHA-256：
d2e440c936bd4a48e67f018b342f4d1c233bf2cd7a5e551682ed4cb5da08f2d2
一般 GCSV AutoRun.txt SHA-256：
5dc89b8506e8ce408276a9eab61fbb9fda94d4a194b65f2fd17c9e410b8fe642
hash 僅供追溯，不構成 runtime 配對限制。所有產物來自目前工作區，含既有建置流程
修改，不是凍結發行版的逐 byte 重建；未覆寫正式下載、寫卡、操作相機或 commit/push。

重現
在 fpSup/gyro 執行：python3 -B -m unittest -v test_gcsv_direct
在 fpSup/gyro 執行：python3 -B -m unittest test_gcsv_format test_imu_stream test_lifecycle test_safety
在 fpSup/fp_usb_shell 執行：python3 -B -m unittest test_boot_chain test_loader_hook test_splash
在專案根目錄執行：python3 -B projects/gyro-sup/validation/20261004-gcsv-direct-output/verify_builds.py
實際建置命令亦存於 build-report.json。
此機 sandbox 阻擋 Unicorn JIT；本輪在獲准的離線環境完成真正 ARM 執行。
若只得到 skipped，不能當成模擬成功。純 fpSup checkout 缺 before 快照時，核心
測試仍執行，只有 before/after 指令計數測試需要研究樹基準。

before/ 保存本輪修改前來源、blobs 與 symbols；source/ 保存修改後來源與測試。
direct-output.patch 是兩項優化的 diff；source-manifest.json 記錄建置來源。
10/04 續作時工作區已回到原 formatter；本輪從保存 patch 恢復這兩項優化，
未恢复排程診斷。現在 formatter 機器碼仍精確吻合 10/01 已驗證的優化版本。
