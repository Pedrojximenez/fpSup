# fpSup-Merge v3

`build_catalogue_v3.py` 核對 frozen release 的 manifest、共同檔案、產品及資料，
再透過 `fp_usb_shell/v3/build_v3.py:boot_card()` 生成八種完整配對
（fpSup 管理頁、瞬間啟動、快速啟動各自開／關）。
產品、資料與啟動畫面維持發行檔內容；不改寫 frozen release。

Merge 頁面預設開啟瞬間啟動，快速啟動為未勾選的獨立選項。
fpSup 管理頁也是獨立勾選項，預設不勾；可單獨下載。勾選時封裝帶管理頁的
完整 loader、尾端 FSDS 清單與 `fpSup/UI/ALLSUPS.BIN`，取消時不包含此頁資料。
管理頁開啟各 Sup 的 More Settings，Sup 啟用／停用在重開機後生效。
瞬間啟動透過 RAM hook 在電源開關重啟後直接讀取 LOADER；快速啟動透過相機設定區的
bootstrap 加速冷開機，首次使用會保存 loader。關閉瞬間啟動會取消先前留下的已知 RAM hook，
保留其他程式的 callsite。兩者仍使用同一套 v3 sup 初始化流程。

設定會選用成套的 AutoRun／LOADER.BIN；zip README 記錄選項，下載前核對所有檔案 hash。
AutoRun 和 BIN 都只保留實際資料及必要對齊，沒有檔案長度補白。熱更新較短檔案必須使用
共用 putfile 的先刪再寫流程；一般主機複製更新仍依頁面說明移除舊卡片資料。

RES-Lab 在公開 Merge 頁先標記「開發中」，不可勾選，也不內嵌其 BIN。
RES-Lab 的開發快照留在本地。公開快照只收錄 RES-CUSTOM 與固定 RCD；
完成開發後加入 RES-Lab 快照並移除 catalogue 的 `stage=dev` 才開放選項。

RES-Lab 與 RES-CUSTOM 仍是兩個 Sup。RES-Lab 選項自動加入 RES-CUSTOM 及 fpSup 管理頁，
並選用 virtual-capable consumer；兩個 Sup 同時啟用，不再列為衝突。
RES-Lab 完成編輯即套用，不需要已存 RCD；SAVE 可以另外儲存具名檔案。
只選 RES-Lab 時固定格式預設不勾，避免填滿解析度列表；可在 RES-CUSTOM 格式列另外勾選。
RES-CUSTOM 獨立選取時使用非虛擬 consumer，不預留動態列。

RES-CUSTOM 現在採有版號的測試版 `fpsup-res-custom-v0.1.3test`，不再以開發快照覆蓋 release。
OG3.5K、OG4K 可選 12-bit，同時保留 8-bit、10-bit；可用位深由各 RCD 宣告。
產品 BIN 與五份 RCD 保留先前線上 `inputs/res-custom-20261013/` 的原始 bytes，
來源與 exact-artifact 離線驗證記錄放在新 release；不宣稱已實錄驗證。
RES-Lab 維持「開發中」，新 release 不包含 RES-Lab。既有 frozen release 維持原檔。
INPUTS 預設只包含 STOPFX；RES-CUSTOM 從有版號的 release 選取。要離線查驗其他快照可明確傳入 `--inputs`；
`build_res_tools.py --out NEW_DIRECTORY` 仍拒絕覆蓋舊快照。
RES-Lab builder 直接輸出 `50RES-Lab v0.1.0test.BIN`；SupManager 沿用檔名顯示，
不新增產品登記或 BIN 資料格式。
`--releases` 測試預設只讀指定 release，另傳 `--inputs` 才加入快照。

預設重建同步產生 `tools/merge-v3/index.html` 與正式入口
`tools/card-composer/index.html`；指定 `--out` 的測試只寫該輸出。

重建及離線驗證：

```text
python3 -B tools/merge-v3/build_catalogue_v3.py
node tools/merge-v3/test_merge_v3.js
node tools/merge-v3/test_ui_v3.js
sh tools/merge-v3/test_data_files.sh
cd fp_usb_shell
python3 -B -m unittest -v v3.test_boot_options
```

`test_boot_options` 核對頁面內嵌八種配對與實際 builder 完全相同；實跑共用 ARM loader／stage2 與 v3 C 入口，核對啟動組合、
暖啟動、Fast 命中／未命中、AutoRun 關閉、回退、關機還原、啟動畫面路徑及 SupManager 保存。
離線模型替代韌體 I/O／配置／UI，不能證明實機時間或 flash 寫回。

JOSE 的兩項監看工具已加入「監看與螢幕」：Desqueeze v0.1.4test
(`41DSQZ.BIN`) 與 Tap to Zoom v0.1.0test (`42TAPZ.BIN`)。作者顯示
Jose Hurtado，下載 README 同樣保留作者。原始 releases 完整保留，
輸出使用本頁現行共用啟動配對，不改動產品 BIN。
兩項 picture hook 使用 CHAIN 並依檔名順序載入；作者的實機驗證
與我們對本次封裝的離線檢查分別記錄，不把作者的測試當成本機實測。

每個 Sup 方塊提供可展開的「版本改動」，列出保留的 release 與目前提供的版本。
`version_notes.json` 保存從原始版本紀錄整理的英／繁中摘要，簡中沿用既有轉換表。
摘要只寫使用者能理解的改動，不把 consumer、RCD policy、開發編號或封裝來源放進頁面。
主頁顯示所選功能與格式；下載仍在內部核對完整雜湊，頁面不列內部檔案或檢查數量。
新 release 自動列入歷史；未補摘要時讀取 README 的 WHAT CHANGED 區段，
沒有區段則標示尚無摘要，並連到原始版本說明。查閱不改變下載選擇，展開狀態在
勾選與切換語言後保留。驗證：

```text
python3 -B -m unittest discover -s tools/merge-v3 -p test_version_history.py
```

STOPFX 恢復為獨立選項，作者 Ruari。`inputs/stopfx-20261012/manifest.json` 核對原始
316-byte `05STOPFX.BIN`，SHA-256 `f9f26a092c5676ead5771ba8be4aac9c3734e9ed0cd144002a73b3f6b657c9d9`。
只加入 STOPFX 快照；Lossless 維持 `fpsup-lossless-v0.2.0test`，不帶本機較新的開發 BIN。
