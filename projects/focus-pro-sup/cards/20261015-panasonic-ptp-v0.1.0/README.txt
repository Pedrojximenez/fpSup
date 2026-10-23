# Focus Pro／Panasonic PTP 相容 SUP 原型 0.1

適用 SIGMA fp 5.02，**離線原型，未上機驗證**。目標是讓 DJI 的 Panasonic 相機控制路徑能向 fp 送相對拉焦。協議參照來自 DJI RS 4 GB83；Focus Pro Grip 是否使用同一路徑仍待實機確認。

成品 `fpSup/60FPPTP.BIN` 由現行 Loader v3 載入。完整卡片另含 `AutoRun.txt`、`fpSup/LOADER.BIN`；不帶 USB shell、Fast 或其他 SUP，不改 flash 或相機持久設定。

這版會在相機控制 USB 類別提供 Panasonic S1H 參照身分（VID 04DA、PID 2382、USB product `DC-S1H`），PTP DeviceInfo 則明確標示 `SIGMA fp Focus PTP prototype`。保留原廠 PTP 收送與標準 session，處理 `9102/9103/9104` 及 `9416(03010011)` 的四個相對模式。擴展識別資料是 libgphoto2 公開樣本的參照 fixture，並非此機實測回覆。

相對控制使用鏡頭原生的近／無限遠換算確定方向，small=20、large=80 原生位置單位，夾在當前原生界限內。僅原生 L 接環鏡頭、待機、沒有拍攝／保存／對焦進行中，且 ready/event、位置及鏡頭身分檢查通過時提交。相同或更舊 transaction 不重做鏡頭動作；回覆 OK 表示原生提交接受，不表示合焦。

32 位 `03010031`、LiDAR AF、錄影中拉焦，以及 Panasonic FOV／完整狀態／錄影／屬性設定在此版不支援，會回覆錯誤，不會轉入語意重號的 SIGMA handler。相對拉焦與光學方向尚未上機核對；原生 API 的等待及與機內 AF 的競爭也不能由離線模擬排除。

安裝測試時，先使用相機的「相機控制／PTP」USB 模式，將對焦切至 MF；卡片載入完成後再接 Grip。若原本已有 Loader v3，可只加入 `60FPPTP.BIN`，重新開機後載入。**同卡的 `00SHELL.BIN` 會與本 SUP 的 PTP 所有權互斥**：依載入順序只有先載入者生效。不要為了載入本原型覆蓋原本的其他成品；完整測試卡適合放另一張卡。

本輪僅製作本機產物，沒有寫實體卡、操作或重啟相機。正式硬體驗收尚需握手、四種轉輪方向／幅度、斷線，以及不錄影的關機／暖開機還原測試。短資料或錯誤的 data header 會停用此實例的動作，需重新載入；不自動重播或中止鏡頭。

建置（在研究專案根目錄）：

```sh
python3 -B fpSup/focuspro/build.py --out <新的空目錄> --card
```

USB 接收 callsite、身分設定 callsite、PTP 介面／接收器所有權和身分設定的初始化資料共六筆 EXCL claim，交由共用 loader journal 在關機寫回。常駐 code、state、診斷環均在自己的 FSB1 block，僅兩個小 veneer 向共用 arena 配置。沒有新增 loader、共享變數或常駐 task。

自訂唯讀 PTP `95F0()` 回傳 `FPCP` v1 診斷資料：64-byte 標頭，接 48 筆 24-byte record。標頭含 requests、submitted、rejected、replayed、io_failed、poisoned、identity_calls、last_tid／target／response 及 extended_session；record 為六個 little-endian u32：sequence、transaction、opcode、parameter、response、detail。這個查詢不需要擴展 session，但需要標準 PTP session。所有紀錄僅存 RAM。

來源及雜湊、限制在成品 `build.json`；本機檢查結果隨開發卡交付。這不是 Focus Pro／fp 互通或 LiDAR AF 已成功的宣告。

2026-10-15：交付檔 4,032 bytes，SHA-256 `63022ae62afabb8286657fca084346755eddcde711c3563fa8f7dc8eb5eed03c`。對交付的 AutoRun、LOADER 和 SUP 執行 32 項 Cortex-A9／Unicorn 測試，全數通過、無跳過；其中 6 項反例涵蓋 transaction 比對、去重、錄影閘門、首次 publication、claim 拒絕和 initialized-data journal。USB 與鏡頭效果仍由明確 stub 代替，沒有實機或光學驗證。SUP 內容改變前後的 AutoRun 與 LOADER 逐位元組相同。

```sh
python3 -B fpSup/focuspro/test_focuspro.py --card-root <開發卡輸出目錄> --report <結果.json>
```
