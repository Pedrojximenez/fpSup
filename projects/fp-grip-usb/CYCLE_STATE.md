# Grip USB 研究交接

2026-10-24，Asia/Taipei。使用者最新指示：「咱們改研究grid連usb吧 我的grid會接上lidar」。grid 暫按 Grip 理解。

## 已完成

- 本對話主線改為 LiDAR → Grip → USB → Mac／fp，獨立目錄 projects/fp-grip-usb。
- 已讀 dji_focus_pro/USB_PROTOCOL.md 第17節及 df101fh/0505 數值→PTP 原始反編譯與封存驗證結果。只是引用既有離線成果，沒有重跑成功測試或新增硬體能力。
- 官方已核對 Grip 四種 USB-C 孔的用途，以及 Grip 使用 Ronin App 更新；不要把充電孔稱作已驗證更新孔。
- 既有循環 focus-pro-lidar 已原地更新為「Focus Pro Grip USB 循環研發」，保留30分鐘間隔與本對話；不建立第二個排程。
- 上一輪 LiDAR 無 Grip 測試的接線問題／移除Grip待辦已被新方向取代；不要再催促使用者拔Grip。

## 唯一待回覆

已詢問一次：使用 Grip 螢幕右側相機控制孔連 fp、充電孔先連 Mac，或先研究兩孔。尚未回覆；不要假定已接好。沒有新的 USB／fp／Grip／LiDAR 操作。

收到選孔後先確認當下設備、版本與基準。相機孔以 host→PTP device 方法觀測；充電孔先確認有無資料列舉，不送任意命令。當前沒有實機結果。

## 最新完成：原始相機身分分流會擋掉數值對焦

參閱 [相機身分與數值對焦分流](research/camera-identity-numeric-gate-20261024.md)，證據 `evidence/20261024-driver-gate02/`，工具 `tools/verify_camera_driver_gate.py`。全輪離線，無USB／網路／寫卡／fp操作。

- 原始600943A4分類、600942DC複製ops：1003 wildcardPID→kind8/SIGMA ioctl600D7242；04DA→kind4/LUMIX ioctl60096204。合成PID不是實機descriptor。
- 相同queue action12(hex)、value1000在SIGMA回3、不組PTP；LUMIX組9416/03010031。SIGMA dispatcher範圍檢查排除selector20(hex)，相機任務忽略回傳再取下一筆。
- 任務60093890在取走action後檢查ops指標202109A4及共用byte2022D278；任一未準備則不分派，無本地重試。ops ownership／ready／PTP狀態是fixture，尚未跑完整init。
- 每條執行指令bytes對回SHA 4e2dec7e7bcbc4bcbf91d63c7f45a04b7c72098e31bcc56b3181a3e0b1c3676e。首個實際驗證通過，沒有重跑舊成功builder或註冊掃描。
- 這代表只加fp接收handler可能不足，不代表SIGMA所有控制不支援，不代表單改VID足夠，尚無實體Grip配對／距離單位／影格結果。

## 下一個離線未知

追原始LUMIX初始化60096038、共用ops安裝及gate writer：哪些握手／能力回覆使數值任務允許分派，失敗時是否保留或清掉gate？已有原始C與映像，可在等待選孔期間離線驗證。不要先動fp VID，不重跑舊組包正例。

實機仍等待原先一次選孔問題；不重問、不要求拔Grip。若使用者選充電孔，改先唯讀確認有無資料列舉。現有fp0.1.1仍有拉焦回歸，不能直接當成完成相容層上機。舊LiDAR直連主線暫不推進，封存保持不變。
