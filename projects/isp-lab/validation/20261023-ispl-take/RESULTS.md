# ISPL 第一次上機：錄影停不下來（2026-10-23）——結論：isp-lab 改成不錄影

條件：v4 卡（IMXB、LUT、SHELL、SUPMGR），CINE FHD 1920×1080 29.97p 12-bit，SD。sigmafp-re-40 讓出相機，使用者同意。

## 過程
1. ISPL.BIN（sha256 a9ce957f…）寫卡、讀回相符；instant restart 後 LOAD.LOG `0A … ISPL.BIN 3 claims`。
2. 主機工具三個問題，當場修：MEM1 讀也要窗口；窗口只收 0x40000000..0x80000000（sink 要走非快取別名＋整快取 clean+invalidate C000E91C）；
   寫入以 1 KiB 進位長度檢查窗口。配置器 class 0 只給 4 MiB 一塊、總共約 8–11.5 MiB（16 MiB 拒絕）→ 塊改 4 MiB 並遞減、WR_BLOCK 8→2 MiB。
3. **第一次 take**（sha256 c2cade09…，冷開機）：sup 第 3 秒 `key MOVON`+`MOVOFF` 開錄成功；第 6 秒同樣的按法沒停下。
   靜默 16 s 後主機送出一個 is_recording 查詢（違反錄影中不碰 USB），回 1。使用者重開，計數器隨重載清空，原因未知。
4. 照原廠錄影腳本 FUN_c0405ba0 改 ctl（`recstate ena/init` → `key MOVON` → `recstate movrecstwai` → … → `key MOVON` → `recstate movsavewai`，
   只送 MOVON；開始未確認不按第二次；停止最多 3 次；逐步記錄）。sha256 622fa24c…，unicorn 27 項過。
5. **第二次 take**：同樣停不下來，**連實體 REC 都停不了**；讀狀態時 USB 已斷（`shl open failed`）。使用者重開。沒有任何狀態資料。
6. 收尾：刪除 ISPL.BIN，冷開機，LOAD.LOG 回到 IMXB／LUT／SHELL／SUPMGR，CINE 待機。卡上 CINEMA 留下兩段空片段（工具不刪 CINEMA）。

## 判斷
- 實體 REC 也停不了 → 不是按鍵注入的問題，是**停止流程本身被卡住**。最可疑：寫入層 sink（IMXL 從沒上過機；停止時原廠要等所有幀完成），
  或控制 task 在錄影中從非 UI task 呼叫 shell 執行器。兩次都沒有證據，**不能確定**。
- 「錄影中」是最不可控的狀態：USB 不能碰、出事拿不到證據、卡住要重開。

## 決定（使用者 2026-10-23）
isp-lab 改成**不錄影為主**，跟 imx410-lab 一樣：
- ISP 每一級在待機時抓（BUFA0 已可；BUFA1＝RWZM 輸出待查能否待機手動開）。
- 預覽／待機畫面用 lcd.py。
- DNG 層（rec/act/留邊/檔頭）離線算，最後少量配方由使用者手動錄一小段寫卡核對。
- 「錄影中畫面」「回放」移到最後、少量、手動。
- ISPL sup 擱置：程式與測試保留，不再上機。

## 事後離線分析：最可能的原因是我們把 class 0 借光了 [I，強]
- `ispl.py take` 的 lend() 是「借到被拒為止」：第一次 4 MiB×2 後被拒、第二次借到 11.5 MiB 被拒 → **class 0 被我們掏空**。
- memory `allocator-not-across-recording`（2026-08-27 對照實驗＋09-06 讀韌體）：錄影路徑本身從 class 0（USER）、2、4、10 要記憶體；
  握著它要的量跨過錄影開始 → 原廠配置失敗 → 相機卡死（當時 64 KiB 就足以凍結 class 10）。
- 吻合現象：開錄成功（起始配置也許夠），之後的配置失敗讓錄影狀態機卡住 → sup 的停止與實體 REC 都無效，第二次連 USB 都死。
- sigmafp-re-40 事前就提醒過「借出的大塊記憶體跨錄影是否安全：未知」；我沒有把它當成要先擋的風險。
- 若日後恢復自動錄影測試：跨錄影的緩衝只能用池（`memmgr bufmem get`，224/224 撐過錄影），或錄影期間不持有任何配置器記憶體。
  這也表示「錄影停不下來」多半是 ISPL 的借法造成，不是錄影本身不可測。
