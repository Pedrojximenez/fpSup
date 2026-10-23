# M12240 上機驗證，2026-10-12

已依使用者「上機測試」授權更新與試錄。**119.88p SD 對照正常停止；239.76p SD 在 94 幀自動 vbuf 停止。使用者 SSD 試錄也秒停，最後一段原生日誌確認 222／222 幀、vbuf／raw1；590 張 SSD 原檔中 401 張檔頭錯位且 LibRaw 拒絕。持續 240p 與 SSD 檔案完整性均未通過，不能只歸因於 SD 速度。**

## 部署與身份

- 以已驗證且沿用的 fpshd 89864 開始，原生 CINE／REC0，三项 writer／XMP／movie busy 皆零；Lossless0、CinemaDNG12-bit、音訊1、SD。
- 17 份現有 AutoRun、loader、全部 Sup 和 RCD 完整備份，見 `backup/manifest.json`。
- 只更新 `32RESCUS.BIN`，加入 `M12240.RCD`。原有 96 B CFG 原封保留，全部其他 Sup／RCD／AutoRun／loader 重新完整讀回相同，見 `deployment/deployment.json`。
- installed consumer（含原 CFG）187,520 B，SHA-256 `7a1ca8757169585952031032e31a1cd4ada7d2e96255f72ff6c718021c0bbb71`；RCD7,136 B，SHA-256 `971fe0f3c78966f2f8ca8c4246260612ff2852a9481eedfcf6d48b35a674490e`。
- 相機保留現有 29,276 B loader／4,666 B AutoRun／producer17，沒有用候選包的較新普通封裝覆蓋這些檔案。exact hybrid fixture 的兩項 ARM 檢查通過；其他實體 optional modules 保留但未在這個聚焦 fixture 模擬。
- hybrid 初次記憶體 canary 失敗，是現有 shell 的兩項 BURST15 描述子未列入現行測試預期；用 exact 00SHELL、LOAD.LOG 和三項固定字實機讀回獨立核對，修正僅此兩字的預期，仍逐字比較整張原生表。證據 `hybrid-offline.log`／`hybrid-offline-corrected.log`／`shell-descriptor-words.json`。
- 兩次單發 reboot：第一次載入 consumer19；第二次套用 RCD 啟用清單。USB IO 回覆视为不確定、未重播；只對已核對的自有 fpshd 發 host QUIT，正常啟動相同程式。現在自有 daemon14207。
- 原生 RES-CUSTOM 清單保留 H2S240，再啟用 M12240（2/5），原生解析度選 M12240。沒有直接改 picker／entry／FPSLATCH 或增加 RAM 實驗。
- 每段之前及之後完整 53,912 B immutable core 比對 consumer19；實機 mode231 donor12、profile p13 base6、RAW1008×672／crop992×662、12-bit；239.76 entry TW0=`014A014A`／TW1=`0006038E`、engine=`436FC29F`、nominal240、VRATE23976。原廠 FPS enum 保持7（119.88），240存在 consumer 私有狀態。

## SD 試錄

HDMI未用於本輪攝影；使用原廠 LCD 截圖與三項 busy 守衛。MOVON／MOVOFF 各成對一次，錄中不輪詢或讀 RAM；到目標時間只有新讀到 REC1 才送停止。資料與截圖全部在 idle 之後取得。

| 試錄 | 新片段 | 目標 | req／fin | 結果 |
|---|---|---:|---:|---|
| M12240 119.88p 對照 | A001_094 |4秒|416／416|目標時 REC1，按鍵停止；原生日誌 Button，LCD綠STBY、三項busy0 |
| M12240 239.76p 短錄 | A001_095 |2秒|94／94|目標時 REC0，自動 vbuf／raw1；未送停止鍵；LCD綠STBY、三項busy0 |

239.76p 真正運行的 CPU header-copy hit +94；後期 p83 canvas／4MiB batch hits 均0。
因此新 p13 guard 有生效，保留原生64MiB；這個組合仍未達持續錄影。SD日誌觀察寫入約222–242MB/s，不能把該延遲換算欄位當成媒體持續能力或唯一根因。

每張 DNG1,095,168 B，239.76p 推算整檔需求約262.58MB/s。這不是實測物理擷取率。

## RAW 樣本

以原生log確認精確檔案大小，只讀已知首／中／末檔名，不列舉相機clip內部。

- A001_094：1／208／416，FrameRate=`120000/1001`。
- A001_095：1／47／94，FrameRate=`240000/1001`。
- 六份 TIFF 起點0、1008×672、12-bit、Compression1、DefaultCrop992×662；六份實際 LibRaw 解碼形狀672×1008。
- 完整檔案及解碼雜湊分別在各段 `raw-frames.json`／`raw-decode.json`；`raw-samples.jpg` 是三幀樣本。

三張抽樣不能代表全部 RAW，也不能證明動態 preview 無拼貼、FOV、實際 exposure cadence、A/V 或時間碼同步；本輪未擷取連續錄影 LCD／HDMI。

## UI 與拒絕紀錄

若干導航檢查在錄影前停止：新 RC_Focus 的 row3 是33634；RC_File 字串只在 rc_post 重新發布，popup當下仍有舊H2字串。實際 LCD截圖確認 M12240 popup 才 Enable。
原生解析度的 committed MV_Resolution 不跟著 popup highlight 更新；先看 LCD，再提交並核對真實活動配方。
這些前置拒絕均沒有送 MOV 鍵。`m12240-120-control/` 是未啟動的空前置目錄，不是錄影片段。
選单返回有非同步延遲；最終對照由独立新 snapshot與LCD守衛確認實際已返回取景。錄影只有上表兩段。

## SSD 手動試錄與全檔核對

相機只有一個USB埠，SSD占用時無法同時用USB shell。已請使用者保持本次開機與M12240／239.76p／12-bit，手動改接SSD試錄10秒，若提前停止不重按停止，再接回相機與SSD。
`ssd-host-before.json` 保留主機SSD現有242個資料夾、最後A001_285，供判斷新片段；在收到使用者完成訊息之前，未再送相機命令。

使用者回報「SSD 測試完成，秒停」。讀取接回主機的 SSD，新增五段 A001_286–290。
原檔未修改；逐張 SHA-256 見 `ssd-host-evidence/manifest.json`。首／中／末原檔、
兩種錯位的代表原檔以及 WAV／XMP 已保存。第二次獨立讀回均與首次雜湊一致。

| SSD 段落 | DNG 數 | WAV 秒數 | TIFF 起點 0 | 起點 19,456 | 起點 65,536 | LibRaw 解碼／拒絕 |
|---|---:|---:|---:|---:|---:|---:|
| A001_286 |94|0.443104|44|18|32|44／50|
| A001_287 |94|0.443104|29|22|43|29／65|
| A001_288 |1|0.037771|1|0|0|1／0|
| A001_289 |179|0.763104|55|44|80|55／124|
| A001_290 |222|0.955104|60|55|107|60／162|
| 合計 |590|—|189|139|262|189／401|

所有五段檔名編號連續。全 590 原檔已交給 LibRaw：189 張起點正常的檔案可解碼，
401 張错位檔全被拒絕，錯位前 bytes 全零。正常原檔逐張解析的影像為1008×672、
12-bit、Compression1、crop992×662、FrameRate=`240000/1001`。
各段兩種錯位代表的相對 TIFF 解析也得到相同主要欄位，但這不是修復或可用 DNG。
完整核對結果見 `ssd-host-verification.json`／`ssd-verify.log`。
首／中／末抽樣多數恰好落在正常檔案，不能據此宣布整段完整。

WAV 是實際音訊長度，不能直接當成 exposure cadence 或錄影键計時。
本輪沒有各段完整原生 log；使用者各次是否改模式或重開機尚待補充。

## SSD 返回相機的原生證據

首次相機 getter 回覆 NO_DEVICE 時停止相機操作，沒有重播，也沒有另起 daemon。
之後主機 USB 列出 SIGMA fp，重新確認 dido 所有的相同 fpshd14207／socket，
在 AF 獨占鎖下讀取 native busy、既有錄影 log 與 immutable core。
返回資料保存為 `ssd-camera-return.json`／`.log`，沒有發出按鍵、清 log、重開機或改設定。

- 最後一段 log：USB volume slot5、exFAT、5000Mbps、1907GB；1095168 B 檔案、
  原生67108864 B batch；時間2026/10/12 07:20:43。
- `req_cnt=222, fin_cnt=222, vbuf/222/534738, raw1`，UI／rec factor皆Nothing。
  count 與 A001_290 對應；此段確認是 vbuf 自動停，不只是使用者「秒停」的觀察。
- 原生日誌顯示多批寫入，request計數增至43、86、128、171、214，
  finish計數依序為1、43、86、129、171、215，最後排空到222。
  故不能把五段都解釋為「完全沒有寫出／回收」。
  日誌首五批的 MB/s 欄為283–299，這些是原生批次延遲欄，仍不是媒體獨立測速。
- 返回時 movie／XMP／writer busy皆0；完整53,912 B core仍精確相符 consumer19。
  選取仍M12240／mode231 donor12、p13 base6、239.76p、12-bit、Lossless0。
- HDR_COPY_CALLS累計1100，等於SD對照416＋SD240的94＋SSD的590。
  HDR_COPY_HITS累計684，與SSD前94相比增加590；p83 legacy／bulk hits仍0。
  CPU檔頭複製路徑命中，未能阻止401張SSD檔頭錯位。
  這是本輪計數與原檔的對應，不能取代每幀來源／目的／writer segment 位址追蹤。

## 判斷與下一項驗證

94 是原廠96槽池扣除保留量後的在途上限，不是等到94張才開始寫檔的門檻。
本輪 SSD 的179／222張也說明至少有部分回收；最後一段在持續寫出的情況下仍 vbuf。
不能把只靠緩衝秒停當成SD速度的充分解釋，更不能把SSD檔頭錯位當成單純頻寬不足。

先前源碼與原生 trace 已核對 event5（準備檔頭）、event8（前進 writer）、event9（完成後歸還）
共享 MRecMgr FIFO，並觀察過通知長時間等待；見
`../20261011-virtual-rate-context-live/recycle-source-audit/REPORT.md`。
這是候選阻塞機制，舊 debug trace 的毫秒值不能搬來當本輪安靜模式的排程證據。
本輪需要直接對照：檔頭來源／目的、writer 取用起點、SSD scatter 消費位址，
以及完成通知至 RAW 回收的順序。不能先擴池或提前歸還仍被 SSD 引用的 RAW。

SSD持續錄影、實際畫面／FOV及十次暖開機仍未通過。本次沒有 commit、push 或發布。
