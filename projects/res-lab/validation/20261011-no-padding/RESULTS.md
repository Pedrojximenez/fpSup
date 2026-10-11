# 2026-10-11：移除檔案補白

相機的 `\AutoRun.txt` 已從 32,768 B 更新成 3,561 B。新檔逐位元組等於舊檔
補白開始前的完整前綴。更新先完成資料與寫入程式的 staging 驗證，再刪舊檔、
確認不存在、寫入實際資料；目錄長度及完整讀回都相符。

- 新 AutoRun SHA-256：`889800fa363c75bfe0d9da43da82312276388a8929748ce05221ce0da931bb4c`
- LOADER 保持 27,652 B，SHA-256：`ecae97aff1c484d878f1ae5c277bc1b9607860f49601c4832c08da97ff0b801a`
- 設定區 FSDS 及其他 sup 檔案未更換。
- `deployment.json` 為 verified；`deployment-commands.jsonl` 留存先刪再寫的順序。
- 單次重啟後 `postboot-state.txt`：登記深度 1、一般 console callback、echo／字元延遲／DRAW 均恢復原值。
  AutoRun 已正常結束；沒有精確捕捉結束時刻，因此不推算此輪總開機時間。

共用 builder、v3 builder 和兩個 Merge 的輸出不再為維持舊檔長度補白。
既有 frozen release 不改寫；Merge 只在 manifest 核對後移除辨識到的歷史 AutoRun 補白，
二進位產品、資料與必要區段對齊保留。短檔替換由共用 putfile 負責，根目錄及子目錄都適用；
不確定長度、刪除失敗或刪後仍存在即停止，不再寫入。

離線驗證：41 項檔案更新測試、51 項載入／啟動畫面測試與更新後 22 項 v3 測試通過。
故意略過刪舊檔後，根目錄和子目錄的獨立 mode-7 模型都留下舊尾巴，兩項反例均被測試抓到
（`mutation-tests.log`）。Merge 的下載包、實際 EOF、manifest、固定資料偏移及舊產品內容也已核對。

後續新增的 v3 瞬間／快速啟動封裝另見
[啟動選項驗證](../../../usb-shell-sup/validation/20261011-boot-options/RESULTS.md)。本次上機只部署上述無補白 AutoRun，
不能視作後續啟動封裝已上機。
