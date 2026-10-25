# LUT UI 第二版（2026-10-24 使用者定版）

使用者看完第一次上機（`validation/20261024-oncamera-01`）後的要求：

- fpSup 頁只有 **LUT manager**：列出所有 LUT，右側原廠 開／關；右下角「AEL 更多選項」。
- 更多選項只有 **色域**、**Gamma** 兩列，選項照達芬奇 cDNG，Gamma 依色域連動。
  **不可**因彈出選單只有 3 格而拆「分組」——原廠清單會捲動；**不可**退回「開啟／關閉／更多選項」彈出選單——AEL 要真的能用。
- 輸出固定 Rec.709，不給選。
- 開啟的 LUT 出現在**原生 COLOR 清單**；強度用原生 ±（Effect）。QS 第一版不做。
- Color 私有頁、Active LUT、監看開關、強度列全部拿掉。

## 已完成（離線，未上機）

- 原生：manager 列 = TOGGLE（原廠 0080/0081 開／關，`build_fp4.GROUPS` 的 Tog/TOff/TOn）；未設定的列顯示 Setup required、不鎖（AEL 要能進）。
- AEL：每格 SELECT 加 `AEL` keyEvent（鍵碼 0x13）→ `LC_Key = 80+k+1` → 開該 LUT 的設定頁。右下角 `LC_RightFooter` 顯示 `AEL Further Options`（只在 manager）。
- 設定頁兩列 `Color space`（8）、`Gamma`（6／Blackmagic 2），選項是絕對索引，寫回 cube 註解。
- fpSup 頁那一列直接開 manager；MENU：設定頁 → manager → fpSup。
- API v2 加 `pick(index)`：給之後的 COLOR 清單選要監看哪一份。
- 測試：test_library_native 18、test_sup_ui 13、test_sup_native 13 全過。

## 待做

### A. AEL 實機確認
私有頁 AEL 以前（v3 FT_LIST）沒觸發，原因未定（`projects/usb-shell-sup/notes/AEL_KEY_DISPATCH_RESEARCH.md`）。
上機：在 manager 列按實體 AEL；沒反應就照該筆記 §4.1 用 `gui key 3 1`／`gui key 3 0` 分層。
備案（不退回彈出選單）：AEL 記錄搬到頁層級物件（原廠 B3_5_5 的 `Menu`）或加 `AELKeyEvent` 物件（ColorButtonMenu 寫法）。

### B. 會捲動的長清單（色域 8、Gamma 6/2）
- home4 的彈出選單（MainY5 第 207 列）是固定 3 格＋游標動畫，不會捲；共用預設不能改（d8b52e05 維護，與 loader 核心綁定）。
- 原廠會捲的是帶 `list` 元件（`scrollEvent`、`drawScrollbar`）的列，資料來自 CSV 模型。主選單族裡 **MainB1 的 `B1_4`（連拍／自拍，7 列）** 與 MainR2 的 `R2_5` 有。
- 做法：把 MainB1 的 B1_4 列複製進 LUT 設定頁（LUT 自己的 builder）；CSV 用**私有 NBR**（plugin `modelCSV`、屬性 `{0x20002,20,1,1,檔名}`、依資源名查找，格式見 `projects/open-gate/build/sl_lists.py`），經原廠 NBR 載入器 `C05E84D8` 註冊（Sensor Lab 實機做過）。不借、不改原廠 CSV。
- Gamma 依色域換清單：照原廠 `_excl` 變體（列模型依 EXCL 變數選變體），LC_GAMMA（6）／變體（Blackmagic 2）。
- a9 的實機規則：不要 bind_sub 綁 position/size（每鍵慢 ~100 ms）；要翻譯的字用原廠 drawText＋.nloc key；項目內文字物件比項目寬就整個不畫。

### C. 原生 COLOR 清單
見 `NATIVE_COLOR_LIST_RESEARCH.md`。LUT.BIN 成為 COLOR 清單唯一主人，RAW View 改向它登記；
名字是 86×74 XCI 圖（主機準備 LUT 時畫）；強度 = Effect ±：±0=100%、每 −1 減 20%、正值夾 100%（使用者未指定，我定，可改）。
