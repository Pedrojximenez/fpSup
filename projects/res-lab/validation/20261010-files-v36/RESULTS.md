# RES-CUSTOM 列表改版：2026-10-10

使用者要求介面像 SupManager。本輪改用同一 `manage_page.build_manage()` 的原生元件，
以 consumer 自己的 RC_ 變數、83 個 resident descriptors、五個 file-choice callbacks 驅動。
沒有修改共用 SupManager、loader、AutoRun、RES-Lab UI 或錄影公式。

## 成品

`projects/res-lab/cards/20261010-files-v37/{debug,plain}`；consumer header v8、producer header v17。
普通與 debug 的兩個產品 BIN 及 loader 相同。producer、loader、AutoRun 與 v35 完全一致。
本輪使用新的建置目錄，沒有覆寫凍結 release；沒有 commit／push／發布。

建置入口：`python3 -B projects/open-gate/build/build_v3_reslab.py --virtual-rcd --card --out NEW_DIRECTORY`，
普通卡另加 `--no-shell`。來源與成品 manifest 全部核對，見 `artifacts-v37.json`。

| 成品 | bytes | SHA-256（建置成品） |
| --- | ---: | --- |
| 32RESCUS.BIN | 182336 | `b816bbf959fa6771cc22536e7a60431901bcd7ffdc4f3b097b4844982a2781a3` |
| 50RESLAB.BIN | 609720 | `dad8226db751fe10c2cac1f2f21269cc746957c7aacc5b19bec83dd027da155f` |
| LOADER.BIN | 27668 | `07907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f` |

## 操作

- 上方數字分頁，焦點在分頁列時左右切換；最多四頁對應既有 16 個有效檔案 catalogue 上限。
- 每頁五檔，檔名與 Enabled／Disabled 在同一列；停用名稱為灰色，狀態沿用 SupManager 的綠／紅字。
- 檔案列 OK／右鍵開啟 Enable／Disable；上下選項，OK 確認，MENU 取消或返回。
- 底列顯示已用名額與 `Restart to update`；重新開機才更新磁碟解析度及 QS。
- 仍是五個磁碟名額加一個 Virtual RCD；獨立 consumer 六個磁碟名額。
  滿額拒絕、錄影保護、RCS1 持久化與寫入失敗保持 RAM 原狀沿用 v35。
- 隱藏列被鎖定。callback 再確認 page × 5 + row 不超出 catalogue；
  inherited More Settings choice 2 沒有檔案操作，不會當作 Enable。
- 空 catalogue 顯示 `No RCD files` 並鎖定列；私有頁面的 Return 仍回 FT_LIST。

## 離線驗證

`focused-tests.log`：六項 ARM saved-file 測試全部通過，包含實際 UI／QS 安裝重開、
明確全部停用、失敗寫入與錄影保護、故意斷開 Choice callback、
第二頁實際檔案與隱藏列／More choice 不混用、獨立無 producer 的全停用模式。

同次執行的兩個頁面測試失敗來自測試解析方式：將整數位置綁定當成文字、
錯用 drawText 的文字 offset。修正測試後，`native-page-fixed.log` 四項全部通過；
原生 allocation graph、文字 component 綁定、consumer 私有寫入、Return、五個 popup／四個頁籤都已核對。
不宣稱最初 `focused-tests.log` 整套通過。

v36 首次建置因 C 字串 literal／callback array 產生 helper 不支援的 ELF relocation，未上機。
v37 改用同一程式內的 immediate 字串字與明確 callback 註冊，建置通過，PIC origin 比對保持。
`build-debug-v36-failed.log`、`build-debug-v37.log` 保留實際輸出。
第一次未升權的原生頁面檢查遭本機 JIT 執行限制結束，沒有當作通過的模擬結果。

## 實機與還原驗證

v37 已寫入相機並完整讀回，`deploy-v37/deployment.json` 的 phase 為 verified。
實際載入 consumer header8／producer header17，見
`../20261010-sidebar-v13/20261010-v37-file-list-boot.json`。
重開後 macOS ptpcamerad 占用 SIGMA interface0；核對 IOService 與 exact PID 後釋放，
沿用本輪自行啟動的 fpshd（17859），原生待機 getter 恢復。

相機有效 catalogue 是 A9／OG2K／OG35K／OG3K／OG4K／S16，共六份。
部署前使用者的 RCS1 已是 VRC000 sentinel（磁碟全部停用），並非上輪的原五檔。
第一頁五檔與 0/5、第二頁只有 S16、空白列鎖定、兩個數字頁籤，以及兩項 popup 均已實測。
三張相機截圖在 `../20261010-sidebar-v13/screenshots/`：
`1666-rescustom-list-v37-page1.jpg`、`1667-rescustom-list-v37-page2.jpg`、
`1668-rescustom-list-v37-popup.jpg`。檔名、標題、狀態與 footer 無遮擋／截字。

實際以第二頁 row1 啟用 S16，名稱白字、Enabled、1/5 與磁碟 RCS1 `S16` 一致；
再停用後名稱灰字、Disabled、0/5 與原先 VRC000 sentinel 一致。
兩次完整 consumer BIN 讀回見 `on-camera-{s16-enabled,restored}-32RESCUS.BIN`，
CRC 與設定區以外的全部 bytes 核對通過，索引見 `on-camera-config-proof.json`。
保存沿用 ogc_save：選擇欄位寫目前 sel_row；本輪為原生選取，會清除部署前已停用的 A9 舊標籤。
因此只宣稱啟用清單已恢復，不宣稱整個 96 bytes 設定與部署前相同。

MENU 在 popup 取消後仍為 RC_FILES，再按 MENU 返回 FT_LIST，
FT_Focus 保留 RES-Custom row4（33684），RC_Focus 獨立。
結束時回第一頁，焦點分頁列，全部磁碟檔停用，相機 is_recording=0；SetMovRecSize=2。
`../20261010-sidebar-v13/20261011-v37-file-list-final.json` 的 registry／活動 rows／consumer／producer
與開機快照相同，管理列表沒有套用配方。原生命令保存在同目錄 `commands.jsonl`。

本輪不錄影、不做 SSD 測速；尚未完成約十次實體 power-off 循環，軟體 reboot 不代替該驗收。
v37 上機後，使用者追加標題名額與修改後重開提醒；後續成品見
`../20261011-count-v38/RESULTS.md`。
