# Merge：可選 fpSup 管理頁與 RES-Lab，2026-10-11

本機 `fpSup/tools/merge-v3/index.html` 已重建。沒有寫入相機、建立 release/tag、
commit、push 或發布網站。

- fpSup 管理頁獨立勾選，預設不勾，可只下載此頁。勾選使用帶 SupManager 的完整
  `boot_card(allsups=True)` 配對及 `fpSup/UI/ALLSUPS.BIN`；取消時省略此頁資料。
- 瞬間啟動仍預設開啟，快速啟動仍預設不勾；共八種完整 AutoRun／LOADER 配對。
- RES-Lab 可勾選，與 RES-CUSTOM 是兩個 Sup，沒有互斥。勾 RES-Lab 自動帶入
  virtual-capable consumer 及管理頁，標示相依關係；設定即套用，SAVE 另存具名 RCD。
- 只選 RES-Lab 不預填固定解析度；可另外勾選 RCD。`RESCUS/README.TXT` 建立 SAVE
  所需目錄。獨立 RES-CUSTOM 使用 non-virtual consumer，不保留動態列。
- Res 工具顯示開發版。新輸入快照在 `tools/merge-v3/inputs/res-tools-20261011`，
  完整 manifest 與來源雜湊；不改 frozen release、不冒充正式版。producer 609,720 B、
  virtual consumer 182,720 B 與先前 v38 上機保存的成品逐位元組相同。
- AutoRun 沒有補白；manager 的 128 B FSDS 是有效清單資料，位於整個外層容器尾端。

## 驗證

- `compose.log`：實際頁面 compose／zip、八種配對、RES-Lab 四種啟動、獨立管理頁、
  相依加入、standard／virtual core 選取、無 RCD 套用、資料勾選、hash、EOF、
  frozen 產品與 UI 精確比對均通過。翻轉 boot、manager UI、virtual consumer 位元均拒絕下載。
- `ui.log`：實際 render／change handlers 的最小 DOM 測試通過。相依勾選、取消、
  必需 checkbox、固定格式初始不勾及可另選、下載狀態通過；不是瀏覽器截圖。
- `data-files.log`：alternate release、合成資料及混合歷史補白／無補白輸入通過。
- `arm.log`：8 個 boot-options 與 18 個管理頁測試，26 項通過，無 skip。
  實際執行 ARM／C，頁面內嵌八種配對等於 builder 輸出；管理頁啟用／停用、保存、
  再開機與關機寫回皆驗證。
- `manager-four-options.log`：另核對全部四個管理頁啟動組合保存完整外層檔案並於
  重開後停用選定 Sup，1 項通過（四個子案例）。
- `res-lab-arm.log`：以頁面組成的 exact loader／producer／consumer 執行四個產品
  測試：無檔案套用、靜態格式共存、原生設定請求、關機還原均通過。此次 runner
  還曾誤引用 `VirtualTests` 中不存在的一個 UI 測試，造成一項 load error；該項實際
  位於 `NativeUI`，已修正引用，在 `res-lab-ui.log` 單獨重跑並通過。沒有產品執行失敗。
  此 fixture 替代原廠 OS／UI，未在同一模型執行 builtin 管理頁的實際 NBR 載入，
  管理頁執行另由上述 26 項測試覆盖。
- 隔離快照的位元翻轉被 catalogue 的 manifest 檢查拒絕；原輸入未修改。
- `git diff --check` 通過。

最終 page／配對／產品 hash 見 `manifest.json`。
`review-card-final-filenames` 與 `RES-Lab-Merge.zip` 是最後頁面的預設 RES-Lab 實際輸出，沒有固定 RCD；
較早 `review-card` 只保留作產品 ARM runner 的 exact 位元組來源（當時還包含固定 RCD）。
未實測新 Merge 卡片的 LCD、感測器、錄影、冷／暖啟動秒數或 flash 持續保存。

## RES-Lab 名稱與版本

依使用者最後指示，builder 直接輸出 `50RES-Lab v0.1.0test.BIN`。
SupManager 沿用原本「去掉排序數字與副檔名」的顯示，因此呈現 `RES-Lab v0.1.0test`。
沒有新增 RLAB 登記、BIN metadata 或載入規則；共用 builder、header、loader、管理頁
來源與原快照雜湊完全一致。609,720 B 的產品內容也與原 `50RESLAB.BIN` 完全一致。
Merge 從檔名取得完整顯示標示，輸入快照改用 `inputs/res-tools-20261011-names`。
`compose-filenames.log`、`ui-filenames.log` 均通過；八種 boot pair 精確位元組未變。
`projects/res-lab/validation/20261011-reslab-label` 保存檔案、manifest 及
現有管理頁／此前相機讀回 Loader 的實際 ARM 驗證，名稱、版本與 Disable 行為通過。
此時 USB 未偵測到相機，未寫入相機。

## 此前啟動檢查的實機發現

相機讀回另在 `projects/res-lab/validation/20261011-start-trigger`。
AutoRun 是 Fast 版，但 LOADER 是原本 plain manager core，沒有共享啟動封裝；
expected store magic `93528A87` 與實際 `5C502AA9` 不吻合，Fast 未命中。
`C03DA420` 仍為 stock `EB0000CC`，瞬間啟動沒有掛鉤。
此檢查沒有修正或重啟相機；只完成讀回、證據保存與判讀。
