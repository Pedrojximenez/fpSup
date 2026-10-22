# 2026-10-10：RES-CUSTOM 獨立管理 RCD

## 完成範圍

依使用者最後指示，**RES-CUSTOM 負責啟用／停用，RES-Lab 不管理清單**。
兩個 Sup 仍分開；最後成品是 `cards/20261010-save-v35/{debug,plain}`，
`50RESLAB.BIN` header v17、`32RESCUS.BIN` header v7。v35 已寫入並在實機開機驗證。

- 動態解析度／QS 顯示 `RES-Lab`；穩定內部身分仍為 `VRC000`。
- RES-Lab 編輯完成自動套用；SAVE 只選名稱、存 RCD，保留 Mode 與活動配方。
- RES-Custom → More Settings 是 consumer 自己的原生 `RC_FILES` 頁。
  RCD 列左右選檔、OK 啟用／停用；Enabled 列 OK／右鍵也可切換。
  顯示檔名、狀態、已用名額及重開提醒。開頁重新掃描有效檔案。
- 啟用記錄寫入 consumer 的既有 RCS1 96 bytes，完整讀回核對。
  操作只改下次開機清單，不改本次錄影表或 producer 的活動配方；錄影中拒絕修改。
- 搭配虛擬 provider 時五個檔案名額，加一個虛擬列；滿額拒絕並顯示
  `List full: disable one`。獨立 consumer 六格；全部有效檔案停用仍可進管理頁重新啟用。
  全部檔案缺失／無效的舊 RELEASE 路徑維持原樣。
- 獨立模式全部停用時只保留管理頁 GUI hook；不安裝錄影表／錄影 hook。
  明確全部停用沿用 RCS1 的保留身分 sentinel，避免 `NEN=0` 被解讀為預設全開。
- 私有焦點、頁面變數、掃描 scratch 都在 consumer 所有的區塊中；Return 回 SupManager。
  共用 Virtual RCD ABI 2 的原有 operations 1–4、loader、AutoRun 與錄影公式不變。

## 原因與實際卡片證據

舊 consumer 固定六個 custom resolution／八個總 UI 列；虛擬列已保留一格，
預設磁碟 RCD 因此只載入五份。新 SAVE 檔案可以寫出，但沒有獨立的 consumer 清單管理 UI，
也不應由 producer 任意啟用檔案或塞滿原生清單。

本次開始時卡片只查到 OG2K、OG35K、OG3K、OG4K、S16 五個原檔，
未查到新的使用者 SAVE 檔案；因此不能把先前未出現的新解析度，全都歸因為某個既存檔案被容量擋住。
本次另以 SAVE 實際產生 A9，再驗證完整使用流程。

## 建置與追溯

建置入口：`python3 -B projects/open-gate/build/build_v3_reslab.py --virtual-rcd --card --out NEW_DIRECTORY`。
使用新輸出目錄；plain 卡的 shell 差異由既有 `--no-shell` 選項控制。
兩卡的 producer、consumer、loader 成品位元組相同，卡片組合由各自 manifest 列出。
實際命令／來源與配置以卡片 `build.json` 和 `artifacts-v35.json` 為準。

| 成品 | bytes | SHA-256（空白 RCS1 的建置成品） |
| --- | ---: | --- |
| 50RESLAB.BIN | 609720 | `dad8226db751fe10c2cac1f2f21269cc746957c7aacc5b19bec83dd027da155f` |
| 32RESCUS.BIN | 139136 | `16d74adcac3f32b9fd9ff384e221874b44b3718b7a399d7fc55528a85558d503` |
| LOADER.BIN | 27668 | `07907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f` |

AutoRun 沿用 v25，SHA-256 `0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0`。
不需更新 AutoRun 或 loader。部署先備份兩個 Sup、AutoRun、loader，保留既有有效設定，
寫完全部讀回核對；證據在 `deploy-v33/`、`deploy-v34/`、`deploy-v35/`。
v33 未開機；v34、v35 有實際開機。最後卡片 consumer 因 RCS1 內容不同，完整 SHA-256 為
`18f1535b17e92452dbac5c170698e3487669480c801bb4bf78f508b9c0cd5a6d`；
`32RESCUS-final-readback.BIN` 已核對除了 `[32,128)` 設定區，所有位元組與 v35 完全一致。

v35 相較 v34 只修正 consumer 原生頁面的 RCD 列 OK 動作，讓它與頁面提示一致。
`artifacts-v35.json` 證明 file-page blob 之外全部相同，ARM 程式／布局／producer 沒有變更。

## 離線驗證

以下紀錄保留通過／失敗實況；不把重複或前版測試加總為同一套最終測試。

| 證據 | 結果與涵蓋範圍 |
| --- | --- |
| `tests-v31.log` | 完整 SAVE → consumer 選擇 → 真正 UI 安裝重開 → QS／record recipe 案例，1 項通過 |
| `tests-v31-regression.log` | 18 項通過；命名 SAVE、sidebar、M12／M9 239.76／279.72p 原生 commit、timing、canvas |
| `tests-v34-final.log` | 8 項通過；完整流程、明確全部停用、失敗寫入／錄影保護、斷開 RC_Key 的故意 mutation、獨立全停用保持原廠 recording、原生頁面配置／綁定／Return |
| `tests-v34-restore.log` | 2 項通過；shutdown claim 還原、兩種原生 Settings request 並保持 recording 狀態 |
| `page-tests-v35.log` | 4 項通過；最後原生頁面、consumer 私有變數、Return、RCD 列 L/R/OK 與提示一致 |
| `entry-chain/report.json` | 14 個入口組合、3 個 AutoRun independence、8 個 catalogue refs 通過；共用鏈未修改 |

原生頁面測試曾抓到 donor 的 `FT_Focus` 仍寫 SupManager 焦點，已在 v34 改為 `RC_Focus`。
保留早期編譯／測試失敗記錄：unused parameter、非 static helper 的 ELF relocation、重複 probe 定義；
以及測試本身錯用 Pool 方法、binding 長度、比較前已預補丁的 ROM snapshot 等問題。
最後通過紀錄如上，不以早期失敗代表最終版本。測試故意斷開 consumer callback 後，預期啟用斷言確實失敗。

## 實機驗證

所有原生回覆都保存於 `../20261010-sidebar-v13/commands.jsonl`；
runtime JSON、截圖沿用同一既有測試目錄，避免覆蓋歷史證據。

1. 讀回舊版 v25：header 16／6，卡片原先五個檔案，啟用記錄 `NEN=0`。
2. 安裝 v34，實際從 SupManager 打開 consumer 的 RC_FILES。
   `1659-rescustom-manager-v34.jpg` 顯示 OG2K、ON、5/5；返回焦點正常。
3. 開 RES-Lab，M12 自動套用 992×662；SAVE A9 成功。
   完整讀回 [A9.RCD](A9.RCD)，48068 bytes，SHA-256
   `76a296e2a567a673f74693b8e33409fe83fce2fc6c08acfd53af92abce490096`。
   解碼標籤 A9、尺寸 992×662、mode donor 12；`save-camera.json` 證明 SAVE 前後活動配方和啟用清單一致。
4. 管理頁重新掃描查到 A9；滿額啟用遭拒。停用 OG2K 再啟用 A9 成功。
   本次活動 M12 幾何、registry 與錄影表保持一致。
5. 安裝最終 v35 並重開：A9 為 native resolution row 2，OG2K 移出。
   `1665-native-rcd-list-v35.jpg` 實際顯示 A9 992×662。
6. 切 CinemaDNG，在原生解析度清單 DOWN／OK 選用 A9；
   `20261010-v35-a9-native-selected.json` 的 selected/current/flag 均為 1，尺寸 992×662。
   再開 QS，`MV_Resolution=2`；兩個獨立顯示窗口載入 A9_FONT／A9_QS。
   NBR 的實際 filename 是 `e2.xci`／`e0.xci`，尺寸 150×38／86×49，
   並非檔案名含 A9。對照解碼 resource 與兩次 GUI draw 的證據在 `live-final-proof.json`、
   `qs-a9-actual-v35.log`、`qs-a9-stable-actual-v35.log`。
7. 最終管理頁以 RCD 列 OK 停用 A9：ON → OFF、5/5 → 4/5；
   RIGHT 選 OG2K，再 OK 啟用：OFF → ON、回到 5/5。
8. 再重開：原先 OG2K／OG35K／OG3K／OG4K／S16＋VRC000 都正確載入，
   A9 不在載入列、仍在 catalogue。RCS1 checksum 正確，selected 回到 stock 0。
   最終 runtime：`20261010-v35-final-original-list-boot.json`。完整 consumer 檔案再次讀回核對。
   相機正常 CINE 待機、`is_recording=0`；格式讀回 CinemaDNG。

QS 操作有以下限制，保留實際結果：`CMDDIAL2 1` 沒改變選值，沒有將它當作成功 QS 選取；
本次實際選取使用原生解析度 popup，QS 測的是該選值的顯示與圖示載入。
較早的 `qs-a9-stable.log`、`qs-resolution-open.log`、`20261010-manager-a9-qs.json`
名稱容易誤導，但當時仍為 stock FHD，不作 A9 選取證據。CAPTURE 會關閉 QS，所以不拿截圖替代 QS draw 日誌。
本次 GUI image log 已關閉。重開的預期 USB IO、macOS SIGMA ptpcamerad 搶介面皆保留；
每次 reboot 只送一次，核對既有 daemon／實際 PTP PID 後恢復，不重送 toggle。

## 未做與保留限制

- 本輪是存檔／管理／原生 UI 驗證，沒有錄影、SSD 測速或畫質驗收。
- 本輪有軟體重開機；未完成約十次實體電源關機、插卡再開的 power-off 循環，不能以軟 reboot 取代。
- 未擴充 native resolution／QS 的列數；磁碟清單掃描仍有 16 個有效檔案上限。
- 失敗持久化測試證明 RAM 設定及 dirty 狀態不被改動，不宣稱卡片短寫具有交易式復原。
- 沒有 commit、push、發布或覆寫凍結 release。A9 是本次建立的樣本，最後保留為停用。
