# Loader v3 第六頁 r3h：離線測試版

第六頁固定顯示 Manage Sups、Updates、SD Card Tools、About fpSup。品牌色取 fpSup logo 的 `#E03858`。

Manage Sups 與頁碼合成一列；停在這列時左右翻頁，翻頁後焦點留在原列。每頁四個 Sup，名稱、版本與待重開機的變更分開顯示。Sup 的右鍵／OK 開啟 Enable、Disable 選單；兩個動作設定下一次開機狀態，不改名、不卸載正在執行的 Sup。

More Settings 只出現在已載入、下一次開機仍啟用，而且有註冊 `svc->button` 回呼的 Sup。loader 轉交回呼，設定頁與儲存由 Sup 自己提供。本次沒有替現有產品新增設定頁。

Updates、掃碼更新、fpSup QR Code、格式化並回寫 fpSup 目前是標示 Coming soon 的預留入口，沒有連網或格式化操作。

## 建置

在研究專案根目錄執行：

```sh
python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261008-allsups-r3h
```

`fpSup/LOADER.BIN` 與 `fpSup/UI/ALLSUPS.BIN` 是本次更新。目錄另附普通 Loader v3 的 AutoRun 與五個既有開機畫面；沒有附產品 Sup。相同建置配置的 AutoRun 位元組不變。未寫入 SD 卡、未操作相機、未發布。

UI 資料改用 FT6U magic，舊 FT6T 資料會被新 loader 拒絕；這是資料結構辨識，不是每次建置的雜湊綁定。後續替換舊卡的 loader 前，需保留舊 FSDS 停用清單，不能把本目錄的空清單直接當作使用者原設定。

## 已驗證與限制

- 66 項 loader、開機鏈與關機還原回歸通過；最終管理來源另跑 16 項測試通過。
- 9 項原生頁面／舊頁面測試通過，包含真正的韌體 NBU 解析器與狀態機匹配器。
- 四個暫存副本故障變體均被測試抓到：錯誤分頁索引、失敗寫入未回復、停用後仍露出設定入口、拒絕正常頁面容量增長。
- 實跑本目錄保存的 LOADER、ALLSUPS 與 AutoRun 開機指令，確認初始化與關機還原。SHA-256 與來源摘要見 `manifest.json`。
- 預設未啟用第六頁的 loader 保持既有完整 SHA-256：`41f3218ac1405962eee7182528e969531de4e11adf0c7a0b4868dda79f8cf67c`。

目前清單存 32 個 Sup（八頁），loader 留一個位置給管理功能，最多載入 31 個產品；停用表容量仍是 30。畫面物件數與 Sup 總數分離，後續增加容量不用新增畫面頁。

Sup 版本文字沿用建置時產品表，還不是每個 Sup 自行提供的版本資料。相機實際畫面、按鍵／焦點、原廠容量增長、Sup 設定頁往返及真實 SD 寫入仍待上機；模擬器的註冊器與檔案操作是明確的替身。
