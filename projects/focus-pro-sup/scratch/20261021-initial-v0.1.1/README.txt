# Focus Pro／Panasonic PTP 相容 SUP 原型 0.1

適用 SIGMA fp 5.02，**實驗原型；使用者回報原廠可控制對焦，套用 SUP 後反而失效**。2026-10-16 已讀回卡片，SUP 與交付版一致、未被停用、USB shell 已停用；載入日誌已滿，尚無此模組的載入結果或 USB 交易紀錄。不能宣稱 SUP 對焦已成功，也不能依 LiDAR 本體燈號判定相機 USB 握手成功。目標是讓 DJI 的 Panasonic 相機控制路徑能向 fp 送相對拉焦，協議參照來自 DJI RS 4 GB83；Grip 實際使用的協議分支仍未確認。

成品 `fpSup/60FPPTP.BIN` 由現行 Loader v3 載入。完整卡片另含 `AutoRun.txt`、`fpSup/LOADER.BIN`；不帶 USB shell、Fast 或其他 SUP，不改 flash 或相機持久設定。

這版會在相機控制 USB 類別提供 Panasonic S1H 參照身分（VID 04DA、PID 2382、USB product `DC-S1H`），PTP DeviceInfo 則明確標示 `SIGMA fp Focus PTP prototype`。保留原廠 PTP 收送與標準 session，處理 `9102/9103/9104` 及 `9416(03010011)` 的四個相對模式。擴展識別資料是 libgphoto2 公開樣本的參照 fixture，並非此機實測回覆。

相對控制使用鏡頭原生的近／無限遠換算確定方向，small=20、large=80 原生位置單位，夾在當前原生界限內。僅原生 L 接環鏡頭、待機、沒有拍攝／保存／對焦進行中，且 ready/event、位置及鏡頭身分檢查通過時提交。相同或更舊 transaction 不重做鏡頭動作；回覆 OK 表示原生提交接受，不表示合焦。

32 位 `03010031`、LiDAR AF、錄影中拉焦，以及 Panasonic FOV／完整狀態／錄影／屬性設定在此版不支援，會回覆錯誤，不會轉入語意重號的 SIGMA handler。這版也會攔截並拒絕 fp 原廠的 `9411/9412` 雲台對焦命令；因此不能假定原廠拉焦功能在相容身分下保留。使用者最新回報是套用 SUP 後無法電控對焦，尚未取得實際命令來定位原因；原生 API 的等待及與機內 AF 的競爭也不能由離線模擬排除。

2026-10-16 協議研究已補上 Grip 模式切換／校正內部訊息、RS 4 GB83 數值型對焦的完整原始 ARM 路徑，以及 25 種 Panasonic PTP 對話，見 [研究第 15 節](../../dji_focus_pro/USB_PROTOCOL.md#15-lidar-af-啟用校正與完整對話盤點2026-10-16)。新增 28 項離線檢查及 3 項反例通過；`03010031` 單位與 Grip→相機的 LiDAR AF 啟用接點仍未確認。這些結果未改動本 0.1 SUP，不表示 LiDAR AF 已可用。

安裝測試時，先使用相機的「相機控制／PTP」USB 模式，將對焦切至 MF；卡片載入完成後再接 Grip。若原本已有 Loader v3，可只加入 `60FPPTP.BIN`，重新開機後載入。**同卡的 `00SHELL.BIN` 會與本 SUP 的 PTP 所有權互斥**：依載入順序只有先載入者生效。不要為了載入本原型覆蓋原本的其他成品；完整測試卡適合放另一張卡。

2026-10-15 建置階段僅製作本機產物，沒有由代理寫實體卡、操作或重啟相機；2026-10-16 收到使用者電控對焦成功及似乎不需要 SUP 的回報。應先以不含 AutoRun／SUP 的卡、正常關機後取下電池再開機，建立原廠控制基準，再評估本原型是否有用途。四種轉輪方向／幅度、斷線，以及不錄影的關機／暖開機還原，仍需各自記錄測試結果。短資料或錯誤的 data header 會停用此實例的動作，需重新載入；不自動重播或中止鏡頭。

建置（在研究專案根目錄）：

```sh
python3 -B fpSup/focuspro/build.py --out <新的空目錄> --card
```

USB 接收 callsite、身分設定 callsite、PTP 介面／接收器所有權和身分設定的初始化資料共六筆 EXCL claim，交由共用 loader journal 在關機寫回。常駐 code、state、診斷環均在自己的 FSB1 block，僅兩個小 veneer 向共用 arena 配置。沒有新增 loader、共享變數或常駐 task。

自訂唯讀 PTP `95F0()` 回傳 `FPCP` v1 診斷資料：64-byte 標頭，接 48 筆 24-byte record。標頭含 requests、submitted、rejected、replayed、io_failed、poisoned、identity_calls、last_tid／target／response 及 extended_session；record 為六個 little-endian u32：sequence、transaction、opcode、parameter、response、detail。這個查詢不需要擴展 session，但需要標準 PTP session。所有紀錄僅存 RAM。

來源及雜湊、限制在成品 `build.json`；本機檢查結果隨開發卡交付。使用者已觀察到 fp 電控對焦，但尚不能將此結果歸因於 SUP，也不包含 LiDAR AF。

2026-10-15：交付檔 4,032 bytes，SHA-256 `63022ae62afabb8286657fca084346755eddcde711c3563fa8f7dc8eb5eed03c`。對交付的 AutoRun、LOADER 和 SUP 執行 32 項 Cortex-A9／Unicorn 測試，全數通過、無跳過；其中 6 項反例涵蓋 transaction 比對、去重、錄影閘門、首次 publication、claim 拒絕和 initialized-data journal。USB 與鏡頭效果仍由明確 stub 代替，沒有實機或光學驗證。SUP 內容改變前後的 AutoRun 與 LOADER 逐位元組相同。

```sh
python3 -B fpSup/focuspro/test_focuspro.py --card-root <開發卡輸出目錄> --report <結果.json>
```

## 實機回報與歸因修正（2026-10-16）

使用者於交付原型後回報：「測試完成，很不錯，確實控制了fp的電控對焦」，隨後補充：「我發現好像不需要這個sup本來就可以控制欸」。因此撤回「SUP 已實機成功」及「成功基準」的歸因，0.1 僅保留為已交付的實驗產物。

fp 原廠 5.02 已有 `GIMBAL_ExecRelativeFocusDriving`（`9411`）及 `GIMBAL_ExecAbsoluteFocusDriving`（`9412`）接收命令；DJI RS 4 參照韌體也有 SIGMA VID `1003` 的獨立分類。這支持原生控制的可能性，尚不能證明 Grip 實際發送這些命令。本對話沒有記錄無 SUP 冷開機的完整條件、SUP 載入／提交診斷或 USB 封包，故不判定先前測試走的是原生或相容路徑。

此紀錄依據使用者回報，沒有另行讀回相機上的檔案或擷取 USB 封包。鏡頭型號、各模式方向／幅度及其他操作的結果未在回報中列出。

本次僅更新研究紀錄，不重建或修改已交付的 SUP、AutoRun、LOADER、ZIP 與建置／離線驗證報告。交付檔雜湊維持上述值。

### 後續對照與讀卡結果（同日）

使用者進一步指出：套用 SUP 後手柄反而無法控制電控對焦，但 LiDAR 指示燈顯示其理解的連接成功；並確認是 **LiDAR 本體燈號**。本體燈號的具體顏色／閃爍方式未提供。[DJI 手冊第 7 頁](https://dl.djicdn.com/downloads/DJI_Focus_Pro/DJI_Focus_Pro_User_Manual_enI.pdf) 將常亮綠／紅／黃定義為 AF／MF／AMF 模式，不能單獨當作 fp USB 握手完成的證據。

依使用者「讀卡吧」讀取 `/Volumes/fpSup`，證據保存在 [card_read.json](../../projects/focus-pro-sup/evidence/20261016-card-read/card_read.json) 及同目錄的原檔副本：

- `60FPPTP.BIN` 為交付的 4,032 bytes，SHA-256 與上列一致；FSDS 停用清單未包含 FPCP。
- 卡上共有 12 個產品 SUP，停用的是 `00SHELL.BIN`、`41DSQZ.BIN`、`42TAPZ.BIN`；9 個處於啟用設定。日誌亦明記 USB shell 被停用。
- `LOAD.LOG` 正好 96 筆，與 loader 的 `MAX_LOG=96` 相符；最後一筆是 `32RESCUS.BIN` 後的 claim，沒有 FPCP 結果或 `DONE`。此為日誌飽和，不能解讀為 FPCP 載入失敗。
- 現版 `95F0` 診斷環僅存在相機 RAM，卡上沒有 Grip USB 命令、拒絕原因或 submitted 計數。讀卡無法補回此輪的交易紀錄。

已確認程式中可能造成回歸的行為：USB 會改成 Panasonic 參照身分，原廠 SIGMA vendor 操作被拒絕；數值對焦 `9416(03010031)`、Panasonic 狀態／FOV 操作也被拒絕。實際是哪條路徑造成此輪失效，仍需交易紀錄。本次未修改記憶卡或重建 SUP。

## 現有原型的診斷讀取

[diagnostics.py](diagnostics.py) 可解碼現版 `95F0` 的 FPCP v1 RAM 診斷環，也可透過 PyUSB／libusb 讀取連接電腦的原型。只允許 DeviceInfo、標準 session 開關及唯讀 `95F0`；先核對原型 DeviceInfo，沒有鏡頭動作、USB reset、切換 configuration、強制卸載驅動或逾時重試。既有 session 不會被強制關閉；只關閉由本工具成功開啟的 session，傳輸結果不明時不再送命令。

下一輪測試後保持 fp 供電及開機狀態，拔下 Grip 相機控制線、改接電腦，才能嘗試取回同一實例的 RAM 紀錄；拔電池或重新開機後無法讀回前次紀錄。重新接線能否保留該機的實例仍需實測。此輪讀卡時未取得 RAM 紀錄。

以下在研究專案根目錄執行；`--usb` 才會接觸 USB，無參數僅顯示說明。`--out` 要用新的本機空目錄。USB 模式需要 PyUSB 及 libusb backend；目前 Python 未安裝 PyUSB，本輪未安裝依賴或進行實機讀取。若介面已被另一程式占用，工具會報錯，不會停止該程式。

```sh
python3 -B fpSup/focuspro/diagnostics.py --usb --out projects/focus-pro-sup/diagnostics/<新的測試目錄>
python3 -B fpSup/focuspro/diagnostics.py --decode <snapshot.bin或PTP資料檔>
```

輸出為 `snapshot.bin` 及 `report.json`，包含 submitted 計數、最近 48 筆命令／第一參數／回覆，以及可直接辨識的拒絕類型。這不是完整 USB 抓包；原廠 pass-through 沒有列入環中，舊初始化紀錄可能已被輪詢覆蓋，現版也沒有 data payload 全文或每一個守衛的個別原因。

離線驗證：13 項主機協議／介面測試與 3 項執行交付版 SUP 原始 ARM 的整合測試通過、無跳過；另刻意移除命令白名單，確認測試會失敗。整合測試使用原 SUP，USB／session／鏡頭外部效果仍為 stub；輸出的 `emulated-*` 檔案是模擬證據。[驗證結果](../../projects/focus-pro-sup/diagnostics/20261016-offline/host_validation.json)。
