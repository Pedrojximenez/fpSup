# screenflip —— 開發卡

原始碼與說明在 `fpSup/screenflip/`。這裡只放上機用的卡。

- `cards/20261007-v3e/` —— **目前版**(2026-10-07 03:35):uishare 定版(字串層 v5 / QS 層 v2,標頭自帶入口偏移)。13 項測試過，未上機。同卡用字串層的 sup 都要換成這版才互認。
- `cards/20261007-v3d/` —— 上一版、已上機(2026-10-07):uishare 字串層 v3(含 svc_holder 修正)、字串點 SHARED_UI claim、帶 00SHELL。六個 sup 同卡全部載入,字串層 40FLIP→30OG3K→10LOSS。
- `cards/20261007-v3c/` —— 同上但早一版 ui_pool,未上機。
- `cards/20261006-v3/` —— **Loader v3 版**(2026-10-06,離線通過、未上機):每個顯示模式各一個翻轉值,切進該模式才套用;
  設定存在 `40FLIP.BIN` 自己裡面。卡上已有 v3 LOADER/shell 時只要多放 `fpSup/40FLIP.BIN`。`MANIFEST.sha256` 為準。
- `cards/screenflip-2026-10-04/` —— 舊 v2 版(設了就翻),2026-10-06 從 `projects/usb-shell-sup/cards/` 搬來,已退役。
