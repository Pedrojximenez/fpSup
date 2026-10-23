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

RES-Lab 與 RES-CUSTOM 仍是兩個 Sup。RES-Lab 選項自動加入 RES-CUSTOM 及 fpSup 管理頁，
並選用 virtual-capable consumer；兩個 Sup 同時啟用，不再列為衝突。
RES-Lab 完成編輯即套用，不需要已存 RCD；SAVE 可以另外儲存具名檔案。
只選 RES-Lab 時固定格式預設不勾，避免填滿解析度列表；可在 RES-CUSTOM 格式列另外勾選。
RES-CUSTOM 獨立選取時使用非虛擬 consumer，不預留動態列。

當前 Res 工具採 manifest 核對的開發快照，顯示「開發版」，不是新的正式發行版本。
`inputs/res-tools-20261011-names/manifest.json` 保存產品、standard／virtual consumer、RCD、
SAVE 目錄說明與來源雜湊；讀取快照不需要完整研究樹。既有 frozen release 維持原檔。
要更新快照，在完整研究樹以 `build_res_tools.py --out NEW_DIRECTORY` 建立新目錄，
核對產品測試後再更新 catalogue 的 INPUTS；腳本拒絕覆蓋舊快照。
RES-Lab builder 直接輸出 `50RES-Lab v0.1.0test.BIN`；SupManager 沿用檔名顯示，
不新增產品登記或 BIN 資料格式。
`--releases` 測試預設只讀指定 release，另傳 `--inputs` 才加入快照。

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
