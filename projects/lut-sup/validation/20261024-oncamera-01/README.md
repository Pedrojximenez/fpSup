# 2026-10-24 第一次上機：20261022-color-comments-01

使用者授權（「上機測試」→ 選 B → 「開始」）。用的是使用者自己的多 sup 卡（loader v4、13 個 sup）。
**用加入的方式部署**：只寫 `\fpSup\LUT.BIN`、`\fpSup\LUT\`（settings/menu/SOURCES/DATA）和 `\fpSup\UI\COLOR.BIN`，
沿用卡上的 LOADER/SUPMGR/UI/AutoRun，**沒有換成開發包自帶的那一份**。部署前的備份放在 `backup-before/`。
寫入用 `fp_usb_shell/v3/deploy_v3.py --only …`，每個檔案都全長讀回比對過。

## 通過
- LOAD.LOG：LUT.BIN 狀態 0，14 個 sup 全部載入（`readback/load_after.log`）。
- fpSup 頁出現 `Color`；私有頁 Active LUT / LUT manager / LUT monitoring 都畫得出來。
- Select LUT 只列出啟用的 LUT；選 Demo_P3 後 LUT.BIN 改了 5 個 byte，**重開機後仍是 Demo_P3**。
- 逐份設定：Unmarked_709 把色域設成 Rec.709、Gamma 設成 2.4 → 卡上 cube 的 `FPSUP_INPUT_COLOR_SPACE rec709`、
  `FPSUP_INPUT_GAMMA gamma24`，檔案長度維持 641 B（只改那一行與補白），**重開機後讀回仍正確**。
- 狀態 Setup required → Disabled → Enable 後變 Enabled，並出現在 Select LUT。
- LUT monitoring 選 On → 被拒絕、重繪成 Off（後端還沒接上，符合預期）。
- MENU 逐層返回：清單 → Color → fpSup 頁 → live view。

## 問題（待修）
1. **設定頁第 1 頁最後一列（LUT gamma family）再按 DOWN**：沒有翻到第 2 頁，焦點掉進看不見的物件（沒有任何列反白），要用 S1 退出。
2. **設定頁分頁列再按 UP，接著按 LEFT**：變成整頁空白、標題列反白，要用 S1 退出。
3. Select LUT 打開時游標在 Off，不在目前選中的那份（Active 標示是對的）。
4. 從子頁按 MENU 返回時，焦點沒有回到進入時的那一列（回 Color 時焦點落在 monitoring；回 fpSup 頁時沒有任何列反白）。

1、2 都沒有讓 shell 掛掉，S1 就能退出。
