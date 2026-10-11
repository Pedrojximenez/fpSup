# 2026-10-11：Merge v3 瞬間／快速啟動

本機 Merge v3 頁面已重建。瞬間啟動預設勾選；快速啟動是未勾選的獨立 checkbox。
切換選項會選用成套 AutoRun／LOADER.BIN，保留產品及格式資料的選取；zip 名稱與
README 記錄兩個選項。frozen release 的產品與資料不改寫。

## 實作與修正

- `boot_card()` 透過維護中的共用 builder，以共用 stage2 包裝 v3 C returning entry。
  沒有另外維護一份 Fast provision／abort／warm loader。
- 瞬間開啟用 RAM hook；关闭時只撤除同一共用 loader 的已知 callsite，保留其他程式的修改。
- 快速啟動用設定區 bootstrap；首次未命中走正常載入並 provision，命中仍重讀 LOADER，
  完成後下一個 echo 才關閉 AutoRun 的 file、registration 和 running byte。
- 共用 stage2、store_boot、abort 對齊 native caller 的 SP，並恢復原 SP。
  新測試曾實際抓到未對齊呼叫，修正後 final suite 通過。
- 共用 stage2 使用指定的啟動畫面目錄。v3 讀 `\fpSup\UI\0.BIN`／`4.BIN`，
  避免沿用舊卡 `\FPSUPUI` 路徑。
- v3 stub 的外層檔案 offset 由 builder 重算。C code length 讀內層標頭；
  FSDS 附在外層容器尾端，SupManager 保存完整外層檔案。
- 沒有固定兩秒完成停留、AutoRun 尾端補白或 BIN 檔案長度補白。
  短檔熱更新沿用先驗證 staging、刪舊檔、確認不存在、寫入與完整讀回的共用流程。

## 最終成品

完整大小、hash、頁面 hash、來源 hash 和 frozen 產品 hash 在 `boot-manifest.json`。
頁面內嵌的來源 hash 已與當前實際來源逐一核對。

| 瞬間 | 快速 | AutoRun | LOADER.BIN |
|---|---|---:|---:|
| 關 | 關 | 3,561 B | 8,248 B |
| 關 | 開 | 4,666 B | 8,568 B |
| 開（預設） | 關（預設） | 3,561 B | 8,528 B |
| 開 | 開 | 4,666 B | 8,848 B |

以上是 Merge 的普通 loader；帶 SupManager 的开发組合另在 ARM 測試中核對，
不以表中的普通 loader 替換相機目前的管理版。

## 驗證

- `final-arm-tests.log`：60 項通過，沒有 skip。包括共用 loader／stage2／store／splash、
  v3 實際入口、四種組合、暖重啟、缺檔回退參數、hook guard、關閉瞬間、foreign callsite、
  Fast 命中／未命中、AutoRun teardown、快取呼叫對齊、關機還原及保存後重新開機。
  測試實際頁面內嵌配對等於當前 builder 的輸出。
- `merge-compose.log`：所有 frozen 產品與資料、四種選項的 zip、實際檔尾、hash、
  啟動選項 README、OFF 衝突處理及可重現下載全部通過。
- `merge-ui.log`：頁面的實際 render/change handlers 通過預設值、checkbox、
  四種組合、選取保留及下載檢查。使用最小 DOM 單元模型，沒有瀏覽器畫面截圖。
- `merge-data.log`：合成 RCD 資料及混合歷史有補白／無補白 release 的合併檢查通過。
- `legacy-compose.log`：71 種合法選取／214 種 normal-Fast-push 組合、7 個 frozen 產品，
  7 個檔案長度／read-cap 邊界與 12 次共用 builder 重現核對全部通過。
- `legacy-ui.log`：舊頁的實際 UI handlers 回歸通過。
- `mutations.log`：刪掉 bootstrap 對齊會觸發 D/I 呼叫 ABI 檢查；把 v3 的外層 offset
  改錯會被實際 manager 執行拒絕，兩個暫時產物反例均被抓到。沒有改寫原始碼或 frozen release。
  各 boot variant 的翻轉位元反例亦會阻擋 zip 下載。

新啟動封裝尚未上機，也尚未發布。離線韌體 I/O／配置／UI 由模型替代，
不據此宣稱實機載入秒數或設定 flash 的持續保存。之前相機的無補白 AutoRun 部署另見
[無補白驗證](../../../res-lab/validation/20261011-no-padding/RESULTS.md)。
