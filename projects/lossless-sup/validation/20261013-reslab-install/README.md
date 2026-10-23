# 2026-10-13 RES-Lab 安裝（v0.2.0test 合併卡）

卡上原為 merge 頁產物：一般版 32RESCUS（755911bf…）、無 RES-Lab。依使用者指示改裝 virtual 版。

| 卡上路徑 | sha256 | 結果 |
|---|---|---|
| `\fpSup\32RESCUS.BIN`（virtual） | 0cb978b7… | 回覆遺失；整檔讀回 `readback-32RESCUS.BIN` 相符 |
| `\fpSup\50RESLAB.BIN` | 19491eb0… | deploy_v3 整檔讀回 OK |
| `\fpSup\RESCUS\README.TXT` | 8f769e25… | 回覆遺失；整檔讀回 `readback-README.TXT` 相符 |

- 來源：`fpSup/tools/merge-v3/inputs/res-tools-20261013/`；以目前原始碼重建三者，逐位元組相同；快照 32 個來源未變。
  一般版與 virtual 版同一次、同一份原始碼建置，差別只有 `--virtual-rcd`。
- RES-Lab 檔名用 8.3 的 `50RESLAB.BIN`（內容同 merge 頁 `50RES-Lab v0.1.0test.BIN`）。
- 未動 AutoRun、LOADER、ALLSUPS（與上次 RES-Lab 實機運作時相同）。未寫 M12240.RCD。
- 備份：`backup/32RESCUS.BIN`（755911bf…）、`backup/ALLSUPS.BIN`、`backup/AutoRun.txt`。
- 待辦（使用者：以後處理）：合併成單一 consumer，RES-Lab 註冊時才建立動態列。
