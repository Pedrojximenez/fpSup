# 2026-10-13 寫入器防護（C037DF50.. 15 word）上機

建置：`build_v3_lossless.py --expand-slots --slot-force 1016 --bulk-stock`（含防護），build `e7039c00…`，部署（ON）`4ee2ee1d…`。
和前一個候選版 `a1a09ada…` 的差別只有寫入器防護。
模擬（真韌體）：`test_writer_completion_redispatches_only_for_its_active_frame`、`test_mutation_stock_writer_completion_dispatches_twice` 通過。

`rec_tickets.py`：錄影中每 0.2 s 讀寫入器訊息票剩餘張數（`0xC35202B4+0x18`，只讀）。

## UHS-II（寫入比錄影快，沒有積壓）

| 片段 | 結果 |
|---|---|
| HS280 119.88p 5 s（`rec-fhd60-a.json`，標籤誤記為 fhd60，實際是 HS280） | 516/516 收尾；513 壓縮；票最少 126，結束後 128 |
| HS280 119.88p 10 s（`rec-hs120-10s.json`） | 1146/1146 收尾；1143 壓縮；票最少 126，結束後 128 |

防護沒有造成退化。真正的積壓（在途超過 128 幀）要用慢卡才能測。
