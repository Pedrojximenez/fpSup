LUT4 現有 v4 卡的增量測試包

只加入 fpSup/LUT/ACTIVE.LUT 與 fpSup/LUT.BIN。
不覆蓋現有 AutoRun、Loader、UI 或其他 sup。
素材為 identity 診斷 LUT；Live View 後端尚未接通，監看維持 Off。
已以相機讀回的 Loader／UI 離線核對色域、Gamma、監看拒用與關機。
安裝順序、檔案尺寸及 SHA-256 見 deployment.json；寫入後必須完整讀回再重啟。
目前尚未安裝或進行相機 UI 測試。
