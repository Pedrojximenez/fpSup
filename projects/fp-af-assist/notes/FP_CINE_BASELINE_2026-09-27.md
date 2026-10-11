# CINE 原廠半按基線：2026-09-27

目標限定為錄影時的機內連續 AF。這輪先完成 CINE 待機的原廠取得／釋放觀測；使用者授權由代理半按快門。沒有切換 STILL、改對焦設定、啟動錄影、注入 hook 或直接控制鏡頭。

## 實測結果

| 項目 | 結果 | 解讀界線 |
|---|---|---|
| CINE 身分 | stored／AF copy CinemaMode 都為 1，初始化及來源 owner 核對通過 | AF copy 與 menu、active UserSetting 是不同資料來源 |
| 影片 full-time AF | AF copy 的有效 byte 為 1 | 開啟旗標不等於已證明連續馬達運作 |
| 原廠半按／放開 | 13:36:41 開始，兩次 host intent 間隔 2.010014 秒，各一次 S1ON／S1OFF | 主機時間不是硬即時保證或光學時間 |
| 持有期間資料 | 六筆完整原始觀測；第七筆因釋放期限停止 | 序列讀取不是曝光同步快照；部分觀測不當完整樣本 |
| AF／鏡頭快取 | scheduler 改變；cached position：事前 6792、持有時觀察到 7160／6848、事後 6798 | 不是實際鏡頭位置連續量測，也未證明合焦正確 |
| face | face／eye runtime=1；六筆 raw count=0、group0 parsed-valid=0 | 當下沒有可採用的臉部尺度；不能據此推論畫面沒有人 |
| AAT | runtime tracking=0；backend、model、publication 為零 | 屬未啟動，不能列為已啟動後的跟丟或效能失敗 |
| 清理與設定 | S1OFF 回覆完成、shutter state=0、前後四個 focus getter 相同、transport anomaly=0 | 放開後由原廠 AF 生命週期接手，不保證 full-time AF 不再移鏡 |

前後設定皆為 rectangle `215 158 595 365`、mode `0`、area `2`、size `3`。AF copy area raw=4，不能把它直接當 menu area enum，也不能代替 active UserSetting 的 AAT gate。

## 對下一步的影響

- 已證明在目前 USB shell 下能完成一次原廠 CINE 半按及釋放，並保留原始來源資料；仍未驗證實際錄影 CAF、辨識率、幾何方向或 DFD。
- 不再反覆半按試圖啟動 AAT。優先補齊 CINE detector 的啟動、初始化主體、更新與停止／恢復接點。
- face 與 AAT 共用幾何核心；先確立可靠尺度與首次光學合焦錨點，並處理鏡頭移動時的呼吸干擾。
- AAT 的固定 64×64 publication 框和自適應模型半軸都不能直接當距離。機內正常追焦不依賴電腦；EP83 僅作開發觀測。

## 證據與工具

原始資料位於 [CINE capture 目錄](../../../research/autofocus/captures/cine-af/20260927-cine-baseline/)：

- [原廠半按完整紀錄](../../../research/autofocus/captures/cine-af/20260927-cine-baseline/acquisition.jsonl)
- [離線解碼與限制](../../../research/autofocus/captures/cine-af/20260927-cine-baseline/analysis.json)
- [四次待機基線](../../../research/autofocus/captures/cine-af/20260927-cine-baseline/baseline-summary.json)
- [原始檔案校驗清單](../../../research/autofocus/captures/cine-af/20260927-cine-baseline/SHA256SUMS.json)

工具為 [CINE baseline](../../../research/autofocus/af_cine_baseline.py) 與 [一次原廠取得觀測](../../../research/autofocus/af_cine_acquisition_trial.py)。它們沒有解除舊 collector 的 memory lease 阻擋。依據見 [CINE AAT／S1 稽核](research/FP_CINE_AAT_ACTIVATION_2026-09-27.md)、[幾何輸入限制](research/FP_CINE_GEOMETRY_INPUTS_2026-09-27.md)。下一步以 [完整開發清單](../PLAN.md) 為準。
