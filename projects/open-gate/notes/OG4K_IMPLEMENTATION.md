# OG4K-4000 實作進度 — 2026-09-15

目標維持 M151 full-height、RWZM1536、4016×2676 RAW12、有效4000×2666、精確24p。
本輪完全離線；尚未安裝相機、產生發行卡或修改現有 OG3K 發行檔。

## 已完成的核心

實作在 `fpSup/opengate/og4k/`；耦合的原廠函式驗證在
`projects/open-gate/build/og4k_offline/`。

- 可組譯、可在 ARM 模擬器執行的 M151 切入／退出／boot recovery。
- 全10字原值比對、讀回驗證、失敗rollback、最後發布enabled。
- 暖重開1024種已知新舊word混合狀態，全部可恢復原廠；未知值拒絕。
- p429 私有畫布只補8個RAW欄位；預覽與共用profile原值保留。
- 回放私有畫布從實際檔案光柵/裁切判斷；先限p71 UHD12 donor。

獨立審查發現並修正了拒絕請求仍清busy/enabled，以及退出失敗rollback後enabled未恢復
的問題。這些行為已有原生ARM回歸測試。對state的boot recovery只處理本核心的資料生命週期，
不能等同整個UI resident/hook與DMA都已具備暖重開保證。

## 原廠韌體的獨立核對

1. `C0320AB0 → C0320F60 → C032D5E0`：M151 full-height 的兩組68-byte receiver參數
   都逐byte等同native M3。每次省略一個receiver word都會被測試抓出。
2. `C0439D18`：完整profile gather與既有模型在312個有效profile一致。
3. `C03D9630 → C01AAA30 → C0135D40/C0135DB8`：OG4K普通列6024bytes、末列6032bytes，
   所以預期StripByteCounts是 **16,120,232**，不是只乘像素所得的16,120,224。
4. `C0435428 / C0435588`：OG4K p71回放FieldAngle為18,842,272bytes。
   p429的`+3C=0`使FieldAngle不配置錄影RAW平面，其總量沒增加不能證明錄影緩衝足夠。
5. `C037A990 → C02DA770 → C001CFD8`：CinemaDNG kind1 的primary配置請求會隨
   OG4K尺寸增加為 **16,207,360bytes / 1024對齊**。實體allocator與pool可用量仍被模擬，
   但請求大小、primary失敗返回、secondary失敗釋放與handle重置可執行驗證。
6. 整合管線實際執行原廠p429 factory/gather → 本次ARM `record_canvas` →
   原廠 `C0438B60/C0438018` descriptor → `C02E5B78` recording copy → 原廠尺寸callback
   與配置請求。不是手填寬高的descriptor：結果確為4016×2676 RAW12、origin8,5、
   RWZM1536/1536，preview descriptor整段不變。上游settings/profile selector未模擬，
   p429仍為明確輸入；錄影物件kind1與prefix仍是原廠推導的fixture，不是完整constructor執行。

## 預覽輸入與RAW輸入

p429 `+F4/+F8=6064×3412` 保留，與先前F1的18字方案一致。這組欄位經
`C0434EF8 → C01D1630` 進入處理／預覽配置；沒有證据說它會被自動改成4042。

RAW擷取 `ContSet_Adr1 C031BE60` 另經 `C032C860(...,0x77)` 取得目前sensor mode的
geometry。`0x77` 是「目前mode」的sentinel，之後再套RAW descriptor的RWZM與even crop。
因此M151的geometry高度4042會影響RAW擷取來源，並不要求同時改預覽輸入高度。

原始證據：`out/decomp/full/blk_c03.c` 的 C031BE60、C0321028、C032C860；
`blk_c04.c` 的 C0434EF8；`blk_c01.c` 的 C01D1630、C01D4340、C01D4360。

## 尚未接上的部分

- 選單／QS的OG4K選項、只開放24p/RAW12/crop-off的限制、錄影前錯誤提示。
- 從真實韌體狀態構造request，確認pipeline停止重組，再執行transaction。
- 實際canvas hook與DNG metadata回放adapter、p71路由、cache publication和hook撤除。
- 錄影ring/pool可用容量、實際DNG header與writer/回放metadata傳遞、併發與長時間寫入。

## 重跑離線驗證

2026-09-15：合併執行 **53 tests PASS、0 skipped**（Unicorn2.1.4）；
ARM核心1332bytes，SHA-256：
`6ddc70f907ca25dfad5c405cf37fa5de049c1aff6cd8cb39f2c3e723ce2b34b3`。

Python、clang與Unicorn備妥後，執行
`projects/open-gate/build/og4k_offline/run_offline.py`；加`--verbose`可列出各測試。
此入口包含候選參數、ARM核心、receiver、尺寸、descriptor、allocator與整合管線；
缺少Unicorn或任何測試被skip都不算整套通過。它不部署韌體、不開USB、不產生發行卡。

目前交付的是離線核心與驗證程式，沒有可安裝的OG4K版本。後續相機測試仍須先告知使用者。
F1先例與離線幾何只能支持這個候選，還不能宣稱4K畫質、所有photosite參與或完整光學視野
已經驗證。第一支影像需核對Bayer phase、每列邊界、裁切與固定機位full-resolution參考。
