# M12 240p：格率切換缺口候選修正，2026-10-11

使用者回報目前 120p 正常、240p 提前終止且錄影中有拼貼，要求先保存目前版本，再從來源嘗試修復。此輪只做來源檢查、離線修改、建置與 ARM 模擬；沒有操作相機、寫卡或錄影。

## 修正前保存

- 獨立 Git 快照：`13890262b461a637195cbd211959b3c0947aa5bf`，分支 `snapshots/reslab-m12-before-240p-20261011`。沒有提交既有 fpSup checkout 的使用者變更。
- 可還原備份：`before-fix.bundle`（77,598,362 bytes，`git bundle verify` 通過）；詳細範圍及雜湊見 `baseline.json`、快照中的 `SNAPSHOT.json`。
- **git:3000 已保存並核對遠端 commit。** 使用者確認這是記錄整份專案歷史的私人完整倉庫後，將 5,540 個來源／韌體／基準檔案推送到 `git@git:bei/sigma_fp_re_usbshell.git` 的上述新分支；遠端指向 `13890262b461a637195cbd211959b3c0947aa5bf`。先前自動審核的傳送範圍疑慮已由使用者澄清，既有分支未改動。
- 快照排除了衍生輸出及 captures。重建另借用未修改的 MAIN、seg0、logo2.png 及 og3k_86x49.xci；四個輸入雜湊記於 `payload-comparison.json`。

## 確認的程式缺口

120p、虛擬 240p、虛擬 280p 都使用原廠格率 enum 7。Settings 的 `FUN_c057a6f8` 與 Quick Set 的 `FUN_c05821b8` 先轉換選單列，再經 MenuAction 呼叫原廠格率 setter。

`FUN_c0074d78` 在 setter 前後讀有效 enum，只有 enum 改變才呼叫 vtable +0x30 與 `FUN_c00911a0` 通知影像管線。此判斷已用韌體映像中的原始 ARM 指令執行，getter／setter／通知僅在邊界建模；同 enum 無通知、不同 enum 有通知均符合來源。

原本 `ogc_rcmt` 只在原廠回呼前更新 `S_VRATE` 與轉換表。120→240、240→280、280→120 的 enum 沒有變，因此這條選單路徑沒有通知重新套用新感測器時序。

## 候選修改

- `ogc_rcmt` 與兩條 rate commit shim 改成原廠回呼前／後兩階段：先發布虛擬格率，再讓原廠回呼完整返回，最後補做必要的 Live View 重建。
- 只有虛擬格率改變、仍使用同一原廠 enum、活動配方仍有效，才補做重建。重复選擇或不同 enum 的切換沿用原廠通知。
- 回呼後重新檢查錄影／寫檔狀態、Virtual RCD 套用鎖及實際 enum；沒有運行中的 Live View 時不啟動它。待處理標記在執行重建前清除。
- 保留原廠參數、r0 回傳值、callee-saved registers、SP 及外部呼叫的 8-byte 對齊。新增兩個消費端診斷字 `RATE_LVOWED`、`RATE_LV_RELOADS`，未搬移既有狀態。
- 消費端版本 9→10；沒有調整 VR_TIME、M12 幾何、CRCT tap、RAW pool、共用 loader 或 RES-Lab 主程式。

## 離線驗證

分批對候選成品執行的 **12 個不同檢查均通過**：

1. 六個 `test_reslab_rate_commit` 檢查：兩條選單路徑 120→240→280→120；重複／不同 carrier 不額外重建；五種回呼後拒絕條件；關機還原 rate hooks；原廠 enum 通知判斷；故意略過後半階段的 mutation 能被偵測。
2. 兩個 `test_reslab_preview_route` 檢查：M12 r78 幾何／感測器 timing／原生 CRCT 選擇器；binning 的 matching native tap。
3. 三個 `VirtualTests` 整合檢查：ABI/status、所有宣告掛鉤的關機還原、Live View stop/commit/start 與 UHD setter。
4. 一個 `NativeUI` 檢查：原廠格率選單變體與參考一致。

同一個往返切換測試對修正前快照執行，Settings／Quick Set 兩個 subtest 都在缺少 Live View 重建處失敗（`baseline-regression.log`，1 test、2 failures、64.398 s）。候選兩條路徑通過；mutation 只改模擬器內的 FN_RCMT 跳板，保留前半更新但略過後半，測試抓到沒有重建與未清除的 pending enum。

開發過程另有兩個測試呼叫問題，已釐清並單獨重驗通過：初版測試把原廠 30p enum 3 寫成 12；UI 檢查誤指定成 `VirtualTests`，其實位於 `NativeUI`。`debug-regression.log` 保留誤指定的錯誤；正確 UI 檢查見 `native-ui-regression.log`。這些不計為候選功能通過或失敗。詳細逐項結果見 `test-results.json`。

這不是完整測試集全綠：先前 engine60 實驗留下的 `test_m12_high_rates_keep_the_native_120_engine_path` 在修正前 v38 已因 240／280 engine field 仍為實際高速而失敗。此輪未改其斷言、未重新引入已撤回的 engine60 修改。

## 成品與來源

候選在 `projects/res-lab/cards/20261011-m12-rate-reload/{plain,debug}`，两份消費端 bytes 相同：

- `32RESCUS.BIN`：183,104 bytes，SHA-256 `57d3587cb6df182a2a8de613ba5458e6e902182d5ca242a1ee63fd6e6c1428ca`。
- 修正前消費端：182,720 bytes，SHA-256 `0751f2e6b6d30f84d38e6b0b7447bd7cfe3f766bb9fd8e97048017ca586031f3`；快照重建精確吻合已回退 v38。
- 以修正前來源重建作比較，候選 AutoRun、LOADER.BIN、`50RES-Lab v0.1.0test.BIN` 全部逐位元相同（`payload-comparison.json`）。舊 frozen v38 的產品檔名／封裝較早，不能用它的 AutoRun 判定本輪是否改 loader。
- shim 4,548 bytes，在既有 4,608-byte 上限內；兩個起點的 PIC 建置與既有 bounds 檢查通過。
- `candidate.patch` 保存五個來源檔的差異；`candidate.json` 保存候選來源及成品雜湊。

## 仍未證實修復的部分

此修正處理一個可重現的格率切換通知缺口，**不能宣稱已修好 240p 提前停止或錄影拼貼**。先前完整 Live View 重建後仍曾重現高速拼貼；既有 RAW descriptor 深度／未完成寫入與 engine 高速分支也仍是錄影問題的調查線索。此輪没有擴容或套用已失敗的 engine60／native30／matching-tap 實驗。

硬體驗收仍需連續有動態景物的 120p／240p 往返、完整錄影畫面與 RAW／停止狀態；單一 DNG、STBY 或 req==fin 不足以證明成功。未部署候選，沒有新增實機驗收結果。
