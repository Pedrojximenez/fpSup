# Focus Pro PTP SUP 0.1 — 離線驗證

適用 SIGMA fp 5.02。此產物為實驗原型，尚未確認 Grip 實機互通。

- 32 項 Cortex-A9／Unicorn 測試通過，0 失敗、0 錯誤、0 跳過。
- 6 項反例均被獨立斷言攔下：transaction、去重、錄影、publication、claim、data journal。
- 執行實際共用 loader／stage2、v3 加載器、SUP entry／veneer／C 程式。
- USB、原生 PTP session、鏡頭 getter／event／drive acceptance、檔案／RTOS／快取效果由明確 stub 代替。
- 四種相對模式、鏡頭範圍與方向、資料長度／type／TID、重複請求、傳輸回覆失敗、
  不支援的數值命令、PTP 身分、ABI 與兩種堆疊對齊、claim 衝突／cave 耗盡、
  不同載入位置、殘留修復、關機還原及 bounded 診斷環均有測試。
- native flags／鏡頭身分與位置檢查不代表已證明與機內 AF 原子互斥。
- SUP 內容改變前後的 AutoRun／LOADER 逐位元組不變。
- 沒有相機／卡片操作、光學驗證、commit、push 或發布。

測試命令：

```sh
python3 -B fpSup/focuspro/test_focuspro.py --card-root projects/focus-pro-sup/cards/20261015-panasonic-ptp-v0.1.0 --report projects/focus-pro-sup/cards/20261015-panasonic-ptp-v0.1.0/validation.json
```

確切來源與產物雜湊見 build.json；原始測試輸出見 validation.log，機器可讀結果見 validation.json。
標準 PTP session 的實際執行效果仍屬原廠行為，測試只驗證會正確交回 parser 與保留 ABI。
獨立既有基準亦通過：LoaderV3Tests.test_loads_in_name_order_skipping_what_is_not_a_sup，以及 BootOptionsTests.test_four_options_load_real_v3_and_restore_products。
