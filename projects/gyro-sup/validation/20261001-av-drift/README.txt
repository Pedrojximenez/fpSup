fpSup-GYRO 音訊漂移對照候選 — 2026-10-01

狀態：僅完成離線調查／建置，尚未實拍；不是已確認的修復版本。
使用者症狀：原始素材聲音約早三格，錄越久越偏；最嚴重片尾約十五秒畫面正常、聲音提早結束。沒有保留素材可量測。

調查方向
原廠收音事件使用單一事件字及最大計數 1 的 semaphore。音訊處理工作優先級低於 GCSV，且每次 callback 只累加固定 4096 bytes；若多次通知在等候期间合併，可能使音訊長度縮短。這是程式層面的可能機制，尚未量到實機事件遺失或 GCSV 的最長連續執行時間。
原廠真正錄音有 8 MiB 緩衝；兩個 16 KiB 是收音表路徑，不能混用。

本候選只隔離一個變因
candidate：GCSV 每至多 128 筆轉換後呼叫 1 ms delay，讓其他工作獲得處理時間。
control：同一份本機來源，保留原本一次轉換完整區塊的方式。
兩者都保留 writer 優先級 6、完整樣本、每區塊一次寫入與同一條載入流程。
未啟用 --format-yield 的 GCSV 與 Base payload，已逐位元組確認與本輪修改前相同。

產物
candidate/ 和 control/ 是一般、不含 USB shell 的對照卡片內容。
candidate-debug/ 和 control-debug/ 包含診斷 shell。
candidate-fast/ 和 control-fast/ 為 Fast Start 2 封裝。
同一組 candidate/control 的 AutoRun.txt 完全相同，差異在 fpSup.BIN。
這些是目前本機來源建置，含工作區既有修改，不是凍結 v1.14.0 發行檔的逐位元組重建。
本輪沒有寫卡、操作相機、commit、push 或發布；也沒有替換既有正式版下載。

建置（專案根目錄）
python3 -B fpSup/gyro/build_base_card.py --edition gcsv --format-yield --version avtest-20261001 --out projects/gyro-sup/validation/20261001-av-drift/candidate --banner fpSup-Gyro-avtest!
control 去掉 --format-yield，改用 control 輸出目錄。
debug 加 --debug；Fast 加 --store-boot --loader-hook --four-box-bar。
本選項只接受 GCSV 且要求明確 --out；不要覆蓋凍結發行品。

驗證範圍
真實 ARM formatter／writer 的模擬：6 項通過，零跳過；資料逐位元組一致、單次寫入、暫存器與堆疊及停用讓出動作的變異檢查皆通過，見 yield-tests.log。
原有 test_gcsv_format、test_imu_stream、test_safety：110 項中 109 項通過，1 項失敗。
失敗是修改範圍外的 lossless/card_status.py:22、lossless/test_card_emulation.py:41 使用 arena 固定位址，被既有全專案掃描攔下；未更動或放寬該檢查。詳見 existing-tests.log。
這些檢查不證明相機排程、實際媒體延遲或聲畫同步。

後續實拍驗收
原廠／Base／control／candidate 使用同一張卡或 SSD、同幀率、同錄音格式，記錄確切載入版本。
開頭與結尾各拍一次可見及可聽的同步動作，保留完整 DNG、WAV、GCSV；長度至少涵蓋先前出現問題的範圍。
比對開頭與結尾 offset、WAV sample 數及尾段是否有資料、DNG FrameRate／TimeCodes，並確認無錄影自停與陀螺資料缺失。
只比檔案長度不能當成實測聲畫同步。若候選仍漂移，應量 raw audio IRQ 與已處理 callback 數、音訊寫入結果及 formatter 執行時間，不能继续猜優先級或拆更多小寫入。

來源與追溯
調查記錄：../../notes/STREAM_DROP_INVESTIGATION.md 最前方 2026-10-01 節。
source-manifest.json：本機 git HEAD 與實際參與建置來源雜湊。
build-hashes.json：每個卡片產物 SHA-256。
candidate.patch：本輪來源更改（新測試另存在 fpSup/gyro/test_gcsv_yield.py）。
