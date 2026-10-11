# RES-CUSTOM 名額與重開提醒：2026-10-11

沿用 v37 的 SupManager 原生五列／分頁／popup，加入使用者要求的標題名額：
`RES-CUSTOM (n/5)`；獨立無 virtual row 的 consumer 為 `RES-CUSTOM (n/6)`。
RC_Title 為 consumer 自己的 resident string descriptor，共 84 個變數；
私有字串仍是 123 個，未超出既有 128 個預算。
只在自己的 builder 暫時加入原生 title 的 text binding，finally 恢復共用 builder；
未修改 SupManager、loader、AutoRun 或 producer 的來源與位元組。

Enable／Disable 成功且實際改變啟用清單後，footer 立即顯示 `Restart to apply`，
原生 FocusOff 不會消除提醒；重新開啟 popup 時回到 `OK: confirm`。
底列仍保留常駐 `Restart to update`。啟用名額立即更新，解析度與 QS 仍在下次開機建立。
滿額、錄影中、寫入失敗與取消維持原有結果。

## 容量範圍

目前 virtual-capable consumer 在建置時保留一個共用動態列，磁碟檔五格。
卸載 RES-Lab 不會自動歸還第六個磁碟名額；本輪沒有加入 producer 存在偵測。
開機時不能以 registry.provider==0 判斷沒有工具：尚未完成編輯／提交時也會是 0。
未來自動歸還需要辨識任意 Virtual RCD 工具，而非只硬編碼 RES-Lab 的名稱。

## 成品與來源

新目錄 `projects/res-lab/cards/20261011-count-v38/{debug,plain}`，consumer header9、producer header17。
建置入口沿用 `build_v3_reslab.py --virtual-rcd --card --out NEW_DIRECTORY`，普通版加 `--no-shell`。
兩份產品 BIN 與 loader 在普通／debug 卡一致；兩個 build.json 的 31 份 source_sha256 均已核對。

| 成品 | bytes | 建置 SHA-256 |
| --- | ---: | --- |
| 32RESCUS.BIN | 182720 | `0751f2e6b6d30f84d38e6b0b7447bd7cfe3f766bb9fd8e97048017ca586031f3` |
| 50RESLAB.BIN | 609720 | `dad8226db751fe10c2cac1f2f21269cc746957c7aacc5b19bec83dd027da155f` |
| LOADER.BIN | 27668 | `07907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f` |

producer、loader、AutoRun 與 v37／v35 相同，無需替換 AutoRun。成品索引 `artifacts.json`。

## 驗證

`native-page.log` 四項原生 allocation／binding／popup／Return 檢查通過。
`saved-rows.log` 六項實際 ARM 啟用管理測試全部通過（302.618s）：
標題 5/5 → 4/5 → 5/5、變更後重開提示、滿額拒絕、持久化與重開後原生列／QS、
故意斷開 Choice callback、失敗寫入／錄影中不變、第二頁隱藏列與 More 不混用、獨立版 0/6。
`restore-settings.log` 用這份 debug 卡的精確 bytes 通過兩項還原／入口測試（63.205s）。
沒有以略過的模擬代替通過。

## 實機

`deploy-v38/deployment.json` phase verified：已保存 RCS1／共用載入器的原檔，
新 BIN 長度與完整讀回一致。configured consumer SHA-256 是
`55a43ca02a34c842b71b6233f93fde86c20fc7f9af4899a5f0e819392cd9d1b6`。
重開後確認 consumer header9／producer header17；macOS PTP 再占用 SIGMA interface0，
查核 IOService 與 exact PID 後釋放，沿用本輪自行啟動的 fpshd 18991。

實際啟用 A9：標題 0/5 → 1/5，名稱白字、Enabled、footer `Restart to apply`。
重新開 popup 回到 `OK: confirm`；再停用 A9，標題恢復 0/5、名稱灰字、Disabled，
`Restart to apply` 經原生 FocusOff 後仍顯示。
相機截圖 `../20261010-sidebar-v13/screenshots/1669-rescustom-count-v38-disabled-restart.jpg`
確認標題名額與重開提醒無截字／遮擋，沿用 SupManager 的可讀字型與格線。

最後全部磁碟檔停用，與本輪部署前 VRC000 sentinel 相同；相機留在列表第一頁，正常待機。
完整 readback `on-camera-restored-32RESCUS.BIN` 與已部署 configured BIN 完全相同。
`on-camera-proof.json` 保存原生 UI responses 與 assertions；boot/final 快照在
`../20261010-sidebar-v13/20261011-v38-file-list-{boot,final}.json`。
活動 rows／consumer／registry 沒有改變。producer 在一般頁面處理時完成預設 UI 初始化
（pages_state 0 → 1），但 applied_valid／applied_geometry 仍為 0，沒有提交配方。

本輪只驗證列表與提示，沒有錄影／SSD 測試；約十次實體 power-off 循環尚未完成，
軟體 reboot 及離線還原測試不代替該實機驗收。
沒有 commit／push／發布；本輪不錄影，不測 SSD。
