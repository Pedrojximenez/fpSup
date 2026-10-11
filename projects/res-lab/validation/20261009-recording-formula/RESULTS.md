# 2026-10-09：錄影預覽抽頭／畫布公式排查

使用者要求先解決錄影中的錯位、分裂畫面，再測 SSD／240p；本輪先以 USB 連線、SD 卡、低格率隔離畫面問題。
Res Lab 與 res-custom 仍是兩個 Sup，沿用同一個 Virtual RCD 服務。沒有新增供應工具專用的錄影接口。

## 問題與證據

- 使用者 SSD 截圖 `SS__1598-ssd-user-recording.JPG` 顯示 279.72p REC、A001-242，畫面中央分裂且兩側場景的尺度不同。
- 原 unity 預覽／縮放 RAW 的組合實際走原廠 E 路徑。先前將選擇器結果解讀成「2000 寬預覽必定讀到 1008 寬 RAW」的推論不充分，2026-10-10 撤回：選擇器只證明路由設定，不能單獨證明 LCD 消費的緩衝 pitch。保存的 r78 已有同一組參數且使用者確認正常。
- v10 嘗試等向 1536 預覽，走 F 的獨立抽頭；使用者仍回報錄影預覽有問題，因此 v10 未驗收。`v10-m12-2997-preview-baseline-record.json` 的低格率基準持續約六秒、由按鍵停止，160 幀完成；只有錄影初期的截圖被寫出，不能據此排除稍後才發生的異常。三次截圖要求僅產出一個檔案，已保存實際交付數，沒有重播錄影。

## v11 候選修正

當記錄使用 binning 或兩軸縮放不同，且記錄抽頭寬度在預覽上限內，預覽沿用逐軸**完全相同的 bin 與 RWZM**，選擇原廠 C 路徑。相同總乘積不代表相同硬體抽頭；不再將 no-bin 大縮放改拆成 bin3 與小縮放。
其他模式保留原廠的有界預覽規則。預覽可見範圍、16 像素對齊與來源邊界仍獨立檢查。

M12 AUTO：RAW／預覽光柵 1008×672，可見 992×662，RWZM 2048／1023；待機可見 1984×1324。
實際 ROM 選擇器的 C 結果為 mux `[1,4]`、主縮放 `[2048,1024]`、secondary `[0,0]`。
Apply 的資料檢查同時拒絕合法大小但錯誤抽頭組合；不只檢查寬高是否非零。

## 離線驗證與部署

- Python profile 16／16 通過，包含逐項突變檢查。
- Host 選單 48／48 通過，包含公式及 UI 突變檢查：`v11-host-menu-verified.log`。
- 精確 producer BIN 的 1,750 組 ARM 幾何通過：70 模式、62 個可 Apply 模式、8 個 RAW14 拒絕。142,800 組物理幾何檢查通過。
- 20 種毒化配方拒絕且保留活動配方；真實 ARM UI 高格率 installer 8 組通過。
- 原廠 ROM 預覽選擇器實際執行通過；它證明配置路徑，不能代替實機圖像／DMA／排程驗收。
- 普通與 debug 的產品 BIN 相同。consumer、AutoRun、Loader 與 v10 完全相同，僅更新 producer。
- 新 `50RESLAB.BIN`：version 8、452768 bytes、SHA-256 `579c224cdca865e03630998bf0ec097d1cbd4bd4b5af5857fd28d67d4bf12e5e`。
- `v11-deployment.json` 記錄完整 v10 備份、新檔完整讀回與一致性。未發布、未改原有其他 Sup。
- 修正公式旁的過期註解後，在 `cards/20261009-virtual-rcd-v11-final/{debug,plain}` 重新建置；23 個程式／UI 檔案與實際部署的 v11 完全一致，產品 hash 不變。`v11-final-artifacts.json` 保留比較，原候選未覆蓋。

## 實機驗收狀態

重開後已確認 producer version 8／consumer version 4。PTP 匯入程序占用 USB 介面；只釋放已確認的 SIGMA claimant，保留自有 daemon，恢復連線後才繼續。沒有因 ACCESS 回覆重播錄影或 Apply。

M12 AUTO／CinemaDNG 12-bit 的實機結果：

| 格率／階段 | 片段 | 完成幀數 | 停止與畫面 |
|---|---|---:|---|
| 29.97p，失焦前置核對 | A001-015 | 155 | 約六秒，正常按鍵停止；預覽與 RAW 都失焦，此片不作細節驗收 |
| 29.97p，清晰景物、持續錄影 | A001-016 | 169 | 約六秒，正常按鍵停止；待機、第三秒後 REC、停止後的清晰畫面一致，沒有分裂／幾何錯位 |
| 29.97p，REC 起始核對 | A001-017 | 90 | 約三至四秒，正常按鍵停止；起始 REC 截圖沒有分裂／幾何錯位 |
| 59.94p，清晰景物、持續錄影 | A001-018 | 342 | 約六秒，正常按鍵停止；第三秒後 REC 截圖沒有分裂／幾何錯位 |

三個清晰片段各抽查首、中、末幀，共九幀；均有有效 TIFF header、可由 rawpy／LibRaw 解碼，1008×672、DefaultCrop 992×662。29.97／59.94 的 DNG 標記與實際感測器配置時序相符。這是抽查，不代表逐幀／所有模式完整畫質驗收。另讀取當前 producer 自有畫布的 29 個欄位，全部與 C 路徑公式相符，見 `v11-live-canvas-proof.json`；未注入 probe 或修改欄位。

主要證據：`v11-m12-focused-2997-record.json`、`v11-m12-focused-2997-start-record.json`、`v11-m12-focused-5994-record.json`、對應 REC 截圖／DNG／decoded-samples.json。原待機與停止後截圖為 `../20261009-oncamera/screenshots/1611-v11-m12-focused-before.jpg`、`1613-v11-m12-focused-after.jpg`。

該階段曾留在 M12／29.97p 待機；`../20261009-oncamera/fps-v11-final-2997.json` 保存實際 owner、活動配方及格率。

**後續使用者確認仍有一下下的異常，並拍到 SS__1616.JPG／A001-020。** 已取回 `v11-user-transient-SS__1616.JPG`：畫面約 y=526 有水平接縫，上下圖像的焦點／位置不一致，底部也有窄條殘留。故 v11 **仍未修好錄影切換異常**；前述穩定階段與一次起始截圖沒有涵蓋這個瞬間，不能將未拍到視為修復。繼續排查配置切換與舊成功版本的差異，SSD 測試仍未開始。

240／280 的持續錄影、SSD、DNG 格率標記及完整畫質均尚未驗收。
既有 SSD A001-242 的 94 幀中，29 幀有正常 TIFF header、65 幀 header 為零；有效首尾 RAW 能解碼，不能說整段乾淨。
其錄影紀錄包含 `vbuf/94/546446, raw1`，提前停止不是已證明的 SD 帶寬問題。
這些問題保留在 `ssd-clip-audit.json` 與 `user-record-log.txt`，待預覽正常後再單獨排查。

## 2026-10-10：首秒切屏與 r77 / r78 回歸

使用者再次限定：29.97p 也發生，僅在開始錄影約第一秒。第二張已取回的
`v11-user-transient-SS__1618.JPG` 是 119.88p／A001-022，同樣在 y≈526 有水平
接縫及底部殘條。其 native log 保存為 `v11-user-transient-second-rec-log.txt`，
94 幀、`vbuf/94/102075, raw1`；不能把這個 SD 停錄結果當作 SSD／240p 驗收。

歷史筆記 `IMX410_FULL_DESIGN.md` 的 r77 明確記錄：M12 AUTO、preview 1008×672、
2048/1023 不等軸預覽，在 REC 起始底部四分之一錯位約一秒。r78 改成等向預覽後，
使用者確認不錯位、不放大。v11 擴大「binning 使用 C 路徑」的條件，把**沒有
binning、只有不等向 RAW 縮放**也導入 C，重新引入已知的 r77 參數。

`extract_frozen_r78.py` 實際執行保存的 r78 成品中的 Thumb 選單與 ARM recipe，
不以今日原始碼重建舊版。SHA-256：
`4c39061502bfe82f3e43347488464fb942b588aeb366925399b519b97e239543`。
輸出為 `frozen-r78.json`。所得 M12 AUTO：

| 欄位 | r78 | v11 |
|---|---:|---:|
| RAW 光柵／有效範圍 | 1008×672 / 992×662 | 相同 |
| RAW RWZM | 2048 / unity | 相同 |
| 預覽光柵 | 2000×672 | 1008×672 |
| 預覽可見範圍 | 1984×662 | 992×662 |
| 預覽 RWZM | unity / unity | 2048 / unity |
| 待機可見範圍 | 1984×1324 | 相同 |

v12 候選恢復無 binning 的 r78 預覽規則，保留 binning 原有的精確配對路徑；
producer 拒絕無 binning 卻不等軸的預覽。另修正不等軸 binned preview 觸及
尺寸上限時漏掉 preview H/V 倍數的比例計算；預設 M12 未觸及這個分支，兩個
問題分開判定。相同預覽倍數沿用既有整數取整，以保留 M98 等已知邊界。

回歸測試直接使用凍結參數，並通過實際 Virtual RCD Apply／consumer canvas。
ROM 路徑測試也訂正兩處 fixture：kind 是 RAW 位深列舉，不是 PARAM +0x1C；
輸出初值遵循 C031D988，不再全設零。它仍不能代替實機過渡期驗收。

v12 的預設 M12 幾何與 v9 相同。因此這是針對 **v11 首秒回歸**的修正候選，
不是已經解決舊 SSD 高格率分裂、壞 TIFF header 或提前停止；那些證據仍然有效。
目前先驗收 29.97p 的錄影開始，不以高格率測試混淆問題。

### v12 離線證據與產物

- `v12-profile.log`：17／17（含逐項突變）；78 個原廠影片 profile 逐字重現。
- `v12-native-preview.log`：凍結 r78 的 29 個欄位、待機範圍、64 個 profile 欄位
  與兩個感測器 timing words 均相符。唯一另外處理的 +0x30：res-custom 遵循
  原廠名義 30.0，r78 寫 30000/1001；本輪沒有變更此欄，真實時序相同。
  unity 的 1023／1024 依原廠夾制比較。
- `v12-arm-formula.json`：1,750 組 ARM 計算、62 模式可編碼、8 RAW14 拒絕。
- `v12-geometry-audit.json`：70 模式、142,800 組、0 超界。
- `v12-guards.json`：20 種毒化資料拒絕，活動配方保持不變。
- `v12-transition-mutation.json`：隔離成品移除等向預覽防護後，測試抓到舊 v11
  參數被誤接受（48000 bytes RCD，預期拒絕）。
- 普通／debug producer 相同；與 v11 比較只變 `50RESLAB.BIN`。consumer、Loader、
  AutoRun 保持一致。producer version 9、452896 bytes、SHA-256
  `992712475e517c6d170475c8829ca1c176937b28aa10c838ca3d4235646c812c`。
  新目錄：`cards/20261010-virtual-rcd-v12/{plain,debug}`，原成品未覆蓋。

- `v12-host-menu-final.log`：48／48，包含新增的首秒回歸與不等軸上限比例突變。先前兩輪失敗為測試的過期 mutation seam／不正確固定 zoom 預期，原始失敗 log 保留；修正後完整重跑通過。

### v12 上機（M12／29.97p 首秒切屏：使用者確認正常）

`v12-deployment.json`：保存完整 v11 producer 備份，再更新單一 BIN，完整讀回一致。
重開一次，macOS PTP 再占用介面；只釋放已確認 SIGMA claimant，沿用本任務 daemon，
恢復後 getter 成功。`runtime-v12-boot.json` 確認 producer 9／consumer 4。
原生選單選 M12 AUTO 992×662，Apply 只按一次，generation=1。
`fps-v12-before-start.json` 確認 29.97002997p 實際時序與 native FPS enum 3。

一次起始短片：`v12-m12-2997-start-record.json`／A001-024，90 幀，
`ui factor: Button`、`rec factor: Nothing`，正常按鍵停止。MOV 之後立即送出
一次 CAPTURE；第一個狀態觀測為 0.289 s，REC=1。截圖顯示 REC，未見先前
底部約 y526 的水平接縫；這是單次樣本，不能排除未捕捉到的瞬間。
首／中／末（1、45、90）三幀完整解碼，1008×672、DefaultCrop 992×662、
FrameRate 30000/1001，見 `v12-decoded-samples.json`。首末影像已目視核對。

隨後參數核對的待機檢查讀到 REC=1，因此在任何記憶體讀取前中止；沒有對這次
新的錄影發送停止鍵。使用者首秒目視回覆待確認；SSD／240p 尚未測試。

**使用者最終確認（2026-10-10）：「正常了」。** 本輪 M12 AUTO／29.97p 的
錄影開始切屏已通過使用者實機確認。`v12-live-canvas-proof.json` 另證明待機時
相機 producer 的 29 個實際欄位全部與凍結 r78 相同；沒有額外送出錄影或停止鍵。
根因定位為 v11 將無 binning 的不等向 RAW 縮放也套進「預覽跟隨錄影」分支，
重現 r77 已知首秒 LCD 錯位；修正恢復獨立、等向預覽。相機現已載入 v12。

此確認範圍是目前 M12 AUTO／29.97p 的起始預覽，不擴大成所有模式／格率、
SSD、240／280p、壞 TIFF header、提前停錄或高格率 DNG 標記已解決。未發布。
