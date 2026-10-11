# RES-Lab 檔名修正

依使用者指示，builder 直接輸出 `50RES-Lab v0.1.0test.BIN`。
SupManager 使用原有檔名顯示路徑，呈現 `RES-Lab v0.1.0test`。
沒有新增 RLAB 登記或 BIN metadata；共用來源逐檔比對原快照雜湊完全一致。
產品 609,720 B 與原 `50RESLAB.BIN` 逐位元組相同。

- `manager-arm.log`：既有管理頁的名稱、版本與 Disable 顯示通過。
- `installed-loader-arm.log`：用此前相機讀回的 exact Loader 驗證同一行為，通過。
- `apply-arm.log`：最終 Merge 卡片新檔名的 ARM entry／虛擬解析度套用通過。
  OS、UI 與儲存仍是模型；沒有實測長檔名在相機 SD 上的實際讀取。
- Merge compose、UI 與八種配對精確比對通過；配對位元組未變。
- 第一個 apply runner 在錯誤目錄執行而找不到模組，沒有執行產品；
  已在正確目錄重跑，證據另保留。

USB 未偵測到相機，未寫入相機或重啟。未 commit、push、發布或覆寫 frozen release。
