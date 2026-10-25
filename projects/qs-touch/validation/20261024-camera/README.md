# QS Touch 上機測試（2026-10-24，進行中）

實體卡已加入 `\fpSup\QSTOUCH.BIN`。AutoRun、Loader、其他 SUP 未更換；每次寫入後完整讀回比對。

- 原始版：19132 B，SHA-256 `ad987e33f283a24bd3c0f41381d91580895bdb7fa6ff9b806fb7a3c812e139c0`。
- r1：19252 B，SHA-256 `38196f1579936b6f5ec07fd80ae2ceab5e70d43c75914a057a6445ee02d651b2`。
- 原卡 Loader SHA-256 `bc8a7410d5aebd71139c51467330688bcb63ae93627e5fcb841a429fa5bea3d6`。
- 原卡 AutoRun SHA-256 `591e93f911d9c5f8abc33ad52eb9a1a3d2af50c33c2995e888ddf1c3bbedc28d`。

原版與 r1 都在真機 LOAD.LOG 顯示已載入，一個獨佔 claim；初始化 result=0、installed=1。
原版由正常選單開啟後 QST_Active=0，沒有保持在 FT_QSTOUCH。既有 SupManager 由正常選單開啟成功。
使用者回報觸控無效時，實際頁面是原廠 QS_CINE；本 SUP 目前尚未替換原廠 QS 入口。

r1 在自己的 UI 回呼以 native app 的 find/set-page 函式直接切頁，並保存回傳結果。
原卡組合的 13 項 ARM 模擬通過（`exact-loader-r1-offline.txt`）。原生畫面與輸入仍須真機驗證。
開啟 r1 後 USB 開始逾時；未重送開頁或按鍵，未釋放任何不確定的記憶體。等待使用者回報機身畫面。

第一輪 USB 失聯由使用者確認是關機或拔線，不計為當機。
沒有發送錄影指令，也沒有驗證真實錄影設定；FORMAT/DC/RES/FPS 都仍是 SUP 自己的示範值。
未完成實體觸控、主觀流暢度或約十次機身電源/換卡生命週期驗收。

`backup/` 為原卡備份，`deploy-*.log`、`readback-*.BIN` 為寫入及完整讀回證據；
`trial.jsonl` 記錄逐次 UI 操作。`exact-card*` 為使用原卡檔案進行的離線組合，不代表所有原卡 SUP 都被模擬。


## 後續狀態（2026-10-24）

以上 r1 等待狀態已過期。其後已移除 r1 並重開機核對還原；使用者換了另一張卡，
該卡本來啟用 Tap to Zoom。依使用者「暫停 Tap to Zoom，測完還原」進行測試，
最後確認為 Tap to Zoom 暫停、v0.1.2 focus-final 已完整寫入並讀回，
SHA-256 `7c2ab548493110302c2e895a996e1a3cfa5aad1a4c127d6587e72d5117baf728`。
不得把前面原卡的 AutoRun／Loader 當作這張替換卡的內容。

v0.1.2 的完整原生焦點骨架能保持 `FT_QSTOUCH`；診斷收到原始觸控封包，
但沒有帶動操作回呼。實拍背景開／關比較也顯示圖層順序錯誤。
`focus-normal-open.json`、`focus-screen-SS2080.jpg`、`bg-off-SS2081.jpg`、
`native-gui-input-check.json` 保存這一階段的證據；合成 GUI 輸入不算實體手指驗證。

使用者其後改為「不用你開始寫吧」，因此本輪僅離線修正與驗證，沒有再連相機、
寫卡、還原 Tap to Zoom 或重開機，也沒有製作任何額外備份。
v0.1.4 修正 POST_INT 靜默更新與 C 回呼之間的事件轉接，合併尚未上機的畫面順序修正；
候選版位於 `../../cards/qstouch-v0.1.4test-input-relay-20261024/`。
新的 SUP 尚未部署，硬體觸控仍未通過，測完仍需還原 Tap to Zoom。
