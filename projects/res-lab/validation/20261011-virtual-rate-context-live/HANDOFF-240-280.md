# RES-Lab M12 240／280：未修復，供重新審查的交接

更新：2026-10-12，Asia/Taipei。這是工作狀態與證據索引，不是成功修復報告。

## 2026-10-12 最新狀態：SSD 仍短錄；接回時 RAM 設定已重置，待核對試錄順序

使用者要求先用 RAM 測試原廠29.97p、只讓sensor240，再考慮 RCD 泛用性。
已停止新增緩存管線修正；未部署 v18。v18 草稿與512×368方案保存於
`sd-small-m12/withdrawn-v18`，正式來源恢復到已部署 v17。

本輪四字RAM改動：H2S240/native30 的entry ENGFPS及 FPSLATCH 改為原廠30.0，
entry NOMINAL及VM.NOM改為30。W0/W1維持330/330/910×6（239.76023976fps）。
原廠29.97p的引擎宣告是30.0，不能用29.970浮點替代；韌體fps<30有不同分支。
沒有改 native timing、allocator、FIFO、writer或RCD／BIN。Lossless正常選單OFF。

SD A001_089：錄中C31DF574實讀30.0，native REC1；64MiB；req94/fin94，
vbuf/94/81226/raw1，自行停止，未送STOP。HDMI紅REC約85/30=2.83秒，
之後綠STBY。首張DNG TIFF在0，1008×672、12bit、Compression1、FrameRate30000/1001，
可用LibRaw解碼。其餘樣本讀取前USB被拔，尚未補齊。
跨午夜：folder日期20261012，實際DNG檔名日期仍20261011；勿列舉clip子目錄猜檔名。

使用者SSD報告仍秒停。接回相機後確認同一個resident allocation與四字修改仍在；
SSD原廠日誌req94/fin94，64MiB，vbuf/94/215785/raw1，寫入段約273–278MB/s。
這否定「只把引擎／虛擬nominal改回30就能修復」；尚不能證明所有副作用或根因。

新明確差異：舊imx410_fmt回傳原廠donor mode12；現行H2 entry.MODE=230，VM donor12。
原廠TIM row42 at C0B59A40，在ROM與實機均已是330/330/910×6，也就是239.76。
已執行只改entry.MODE230→12的RAM對照（其餘四字30.0／30保持）。
錄中C31DF574實讀30.0，nativeREC1；到20秒時REC0，自行停止，未送STOP。
HDMI顯示A001-091、紅REC／0:00:03，到900張HDMI及後續新24張觀察仍未回綠STBY。
新原生log顯示req94/fin65、64MiB、vbuf/94/81021/raw1；該log時間欄仍是上一段SSD
的00:09:44，不能用作這段開始時間，也不能把fin65當成完成後最終檔案數。
停止狀態不一致，未使用檔案工具，未送第二次錄影鍵，未寫還原MODE230。
當時entry.MODE仍12，前述四字修改仍在RAM，因此要求使用者重開恢復。
**使用者已重開並拔除HDMI；已重新確認nativeREC0與原廠LCD綠STBY。**
USB舊handle回報NO_DEVICE後已關閉；既有daemon重新連接，不另起競爭daemon。
重開的core/state基址碰巧相同，但VM由0x45202600變為0x45202400；未沿舊地址還原。
重選正常選單H2前，SEL/FLAG與FPSLATCH都重置；重選後MODE230、ENGFPS239.76、
NOMINAL240讀回證明舊五字修改已消失，證據在`hdmi-off-h2-selected.json`。
本次改法不需要寫native timing，且原廠TIM與固定descriptor已在寫入前核對：
C343B588→C2F1E654→{C0B59500,70}；這是固定BSS descriptor，不是ROM或旋轉指標。
先前descriptor範圍錯誤及HDMI第一張初始化未完整的兩次預檢拒絕均零寫入，證據已另存。
原廠mode12單字RAM對照也未修復；不能把虛擬mode230單獨認定為根因。

### 拔除 HDMI 後的新 SD 對照

重新由正常選單選H2S240，再以相同四字RAM修改設為processing30.0、nominal30，
MODE230、sensor TW239.76、29.97p選單、LosslessOFF、audio1、原廠64MiB維持。
A001_092：目標20秒時REC0，未送STOP；req94/fin94、vbuf/94/81009/raw1、64MiB。
錄中C31DF574實讀30.0／nativeREC1。停止後原廠LCD綠STBY，且released consumer
的三個busy條件全部0（MovieRecording、XMP file object、MovieWriting）；不靠REC0單一讀值
就借檔案工具。這個guard也以REC0但寫入/XMP仍忙的受控測試確認拒絕截圖。

**使用者回報「差不多 接回ssd 與usb」，已保存四段新 SSD 的檔案證據。**
前兩段 A001_282／283 各94張，音訊0.421771／0.443104秒；前者TIFF位置
{0:41,19456:21,65536:32}，後者{0:30,19456:22,65536:42}。
A001_284有104張、音訊0.677771秒，TIFF全部在0；A001_285只有32個DNG，
張號15–46、缺1–14且無WAV，不能把它叫做「完整46張」。四段檔案皆1095168 bytes，
首／中／末標籤1008×672、12-bit、Compression1、crop992×662、FrameRate30000/1001。
SSD原檔未改；全檔SHA與選定原檔、WAV／XMP在`sensor-only-no-hdmi-ssd-return/ssd-files/manifest.json`。

接回相機時nativeREC0，三項busy0、LCD綠STBY；native rec log-out為(no data)。
resident core仍逐字核對v17，但allocation由0x451d4780改為0x45118ec0，
consumer FLAG/CUR/FPSLATCH與header hit counters全部0，四字RAM組態已不再生效。
選單MV_FrameRate3、MV_Resolution0、MV_fpLossless1（試錄前Lossless0）。
已詢問使用者重開／改設定的試錄順序；尚未收到答覆，不能把四段都歸入同一RAM組態，
也不能以空停止日誌宣稱本次SSD的native vbuf已取得。尚無成功修復。

此對照也有重開造成的其他差異：前一次producer已Apply但未選取，nentries17／nvm2；
新開機producer尚未Apply，nentries14／nvm3。**更正：H2 VM.CLAMP前後均0。**
CLAMP在VM+0x3C／word15；保存的兩份raw array均0。先前1→0是索引判讀錯誤，
不能當作本輪額外變因。
因此不是嚴格單一變因；兩種組態的SD均94張自行停止，不能將任何一項宣稱為修復。
詳見`no-hdmi-comparison.json`；preserved entry與VM raw words可逐字比較。

每張DNG1095168 bytes，按sensor設定239.76推算總檔案需求262.58 MB/s，
不是只算RAW strip，也不是實測sensor cadence。這超過使用者估計SD200 MB/s；
SD結果不足以單獨排除SSD上的HDMI影響。先前縮小解析度及Lossless試驗亦保存，未追加緩存修補。

其他工作正在修改shared res-custom來源（位深選單相關），本輪沒有覆寫、部署或提交那些改動。
live host helpers已固定使用`reference-source-v17/ogc_layout.py`，hash/provenance有保存；
resident core仍逐字核對v17 reference。保存本輪用checkpoint.py --evidence-only，避免納入其他來源。

RCD方向：現有required section12已包含{rank,crop,TW0,TW1,ENGFPS,NOMINAL}，
可表達sensor239.76／processing30.0／nominal30；H2檔目前選的是239.76／240。
本輪未修改或部署RCD。entry.MODE仍由consumer一律產生虛擬ID，是另一個獨立限制，
但native12對照失敗，尚無理由把增加native-ID選項宣稱為修復。

下一個尚未實機測過的組合是native MODE12＋舊H2推導的ENGFPS239.76／NOMINAL240，
選單／container維持29.97；先前MODE12試驗使用ENGFPS30／NOMINAL30，並不是此組合。
已完成`test_native_m12_historical_pair.py`的固定v17 ARM離線驗證：只改entry.MODE一字，
picker重入保持12；由獨立原廠p13 defaults生成完整65字canvas與H2重建值相同；
八種virtual lookup（含R10）均拒絕native12；TIM未改；原廠DMA header和64MiB維持，
RECRATE不改30000/1001，ABI及native tables核對通過。
這是參數／機器碼驗證，沒有模擬排程、DMA或媒體吞吐，也不是成功錄製證明。
已保存`prepare_native_m12_historical_pair.py`，要求正常選單已選H2與LosslessOFF，
驗證native三項busy0／LCD綠STBY、resident完整v17、entry和VM owner bounds，
只寫MODE一字並讀回，不啟動錄影、不寫卡、不覆寫舊manifest。**此腳本尚未執行。**
不要把目前LosslessON／H2未選的返回狀態直接拿來試錄這個組合。

證據：`sensor-only-ram/patch.json`、`sensor-only-native30-quiet20/trial.json`、
`first-frame-evidence.json`（在trial目錄內）、`sensor-only-ssd-return.json`、
`sensor-only-after-ssd.json`、`native-m12-identity-offline.txt`、
`native-m12-identity-patch.json`、`native-m12-identity-quiet20/trial.json`、
`native-m12-identity-stalled-return.json`、`native-m12-identity-return.json`、
`sensor-only-no-hdmi-ram/patch.json`、`sensor-only-no-hdmi-quiet20/trial.json`、
`no-hdmi-comparison.json`、`native-lcd-idle-offline.txt`。

目前相機USB與SSD均已接回電腦，既有owned fpshd PID89864，v17 code bytes已核對。
所有本輪RAM修改已不再生效；H2尚未選，29.97p／LosslessON。最後已確認nativeREC0、
原廠LCD綠STBY、native三項busy0。沒有啟動新錄影，沒有部署新的RCD／BIN。
正在等待使用者說明四段SSD試錄之間或回接前的重開／設定改動順序。

以下保留2026-10-11早期交接作歷史背景；版本與連線敘述以本節為準。

## 使用者的目標與目前結果

120p 能錄製；M12 虛擬 240／280 錄製會提前停止，錄影畫面有拼貼或縮小。
使用者要求從代碼修復、確認虛擬格率在整個系統生效，並上機測試。
使用者已授權相機／卡片測試及私人 git:3000 全專案歷史保存，不必重新詢問這些授權。
相機只有一個 USB 埠；接 SSD 時不能同時透過電腦的 USB shell 操作。
使用者已反覆換接及重開，對大量未能收斂的候選測試很疲倦。

**持續 240／280、畫面拼貼及 FOV 問題均未通過實機驗收。**
最後一輪源碼審查沒有改動或安裝新的相機程式。
不能把離線測試通過、成功讀出參數、94 個完整檔案或停止後池歸還，稱為錄製修復。

## 環境與保存

- 工作目錄：`/Users/dido/Developer.localized/SIGMAfp_re`。
- 證據目錄：`projects/res-lab/validation/20261011-virtual-rate-context-live`（本文所在目錄）。
- 根目錄不是 Git 倉庫。`fpSup` 是有未提交內容的巢狀倉庫；不要 reset、stage 或提交它。
- 獨立全專案歷史倉庫：`/private/tmp/reslab-m12-baseline-20261011-1329`。
- 分支：`fix/reslab-m12-rate-reload-20261011`。
- 遠端：`git@git:bei/sigma_fp_re_usbshell.git`，網頁 `http://git:3000/bei/sigma_fp_re_usbshell`。
- 本文之前已推送並核對遠端的版本：`58974151b0b4da5d1a0cbdcba4280bf11d004508`。
- 保存工具：`../20261011-virtual-rate-context/checkpoint.py`。
  小型證據、候選卡與修改會複製進歷史倉庫；大型 HDMI／RGB／逐命令資料保留本機並記錄 SHA。
  因此不是每個大型擷取檔都已上傳 git，原始檔不要刪除。

## 成功樣本確實存在，但成功的精確 RAM 程式未找回

原始成功片段：`/Users/dido/Movies/fpsup/hightspeed/A001_193`。
4809 張連續 DNG、音訊 20.069771 秒，支持使用者過去的 240p 成功紀錄。
全部 4809 張已掃描 TIFF 前綴，均從 offset 0 開始；原檔未修改。
RAW1008×672，12-bit，Compression=1，crop992×662@(8,5)，檔案 FrameRate30000/1001。
因此必須分清 sensor／capture engine 的 239.76 與當時 application／container 的 29.97。

DNG／WAV 時間為 2026-09-29 09:14:25+08。附近歷史截圖支持相機時鐘快約 56–60 秒；
推算 host 開始約 09:13:25–30。這需要時鐘／時區未改的假設。
歷史 08:55 已驗證 H2 RAM 安裝；09:16 新 rate hook 的安裝在 preflight 失敗、零寫入。
最強線索是 9/29 H2／p13 家族，**不是已找到精確 BIN 或 commit**。
October1 r10／p83 是另一份較晚的成功參考，不要混稱為 A001_193 的確切版本。
MakerNote 尚未完整解碼；Software 標籤只有原廠 5.02.0.V91，不含自訂版本識別。

資料：`success-version-audit/REPORT.md`、`tiff-prefix-all-frames.json` 及同目錄歷史摘錄。

## 最後安裝的比較版本：H2 v16，已失敗

程式：`projects/open-gate/build/res-custom/build_v3_rescustom.py` VERSION16。
主要消費端：`projects/open-gate/build/res-custom/ogc.c`。
卡片：`projects/res-lab/cards/20261011-virtual-header-inner/plain-h2-recording-v16`；
相應 DEBUG 卡在 `debug-h2-recording-v16`。
離線參考：本文目錄 `reference-h2-v16`。

`h2-success-rcd/H2S240.RCD`：7060 bytes，SHA256
`835d214cf4c0b17d26f075e6ce3f749fe346ac88fb7c9ab4b9fe3642f15cbc99`。
它重建歷史 H2 家族的參數，並非復原成功那次實際 RAM 全貌。
M12、native30、S.VRATE=0、sensor／engine239.76、nominal240；
timing330/330/910×6，p13 class2、PARAM+88=0、zoom2048/1024。
25 個歷史 canvas 欄位已重建；沒有 A001_193 的完整 FPSLATCH／65-word 快照。
當次 engine 設定仍有依歷史 recipe 推導的部分，不能當原始實機讀回。

v16 新增 RCD required section12 的每 carrier timing 支援；producer／loader／AutoRun 沒改。
v15 會拒絕這個 required section；v16 的原始 ARM parser／timing／canvas／ABI 離線測試通過。
H2 使用原廠 DMA header 和 64MiB 批次；現有 CPU-header／4MiB guard 的計數是 0。

SD：`h2-native30-v16-quiet`，A001_086，req94/fin94，native vbuf/94/raw1，自行停止。
沒有送 STOP 鍵。停止後 nativeREC0 與 HDMI 綠色 STBY 已確認。
首／中／末 DNG TIFF 在0，LibRaw 可解碼；短且模糊的畫面不足以完成拼貼／FOV 驗收。

SSD 手動後續：A001_277 一張；A001_278／279 各94張，使用者報告秒停。
後兩段各29張 TIFF在0、22張在19456、43張在65536；前綴全零。
兩段數量分布相同，逐張位置相差3張，不是完全相同的錯位序列。
原始檔雜湊與選定原檔在 `h2-ssd-host-evidence/manifest.json`。
這三段沒有完整 HDMI／native stop trace；94檔本身不能單獨證明 native vbuf。

## 已由源碼和原始 ARM 核對的機制

主報告：`recycle-source-audit/REPORT.md`。
韌體：`out/MAIN_c0000000.bin`；反編譯：`out/decomp/full/blk_c00.c` 至相關 blk。

1. 96 槽 RAW／描述子池正常可有94張在途；94不是寫入觸發門檻。
2. event5準備逐張 header；event8前進 writer；event9歸還 RAW／描述子。
   三者共用 MRecMgr FIFO。下一張 writer 還會被 creator+1C 的 event8 確認卡住。
3. 保存的1MiB試驗：event8等124.206ms；event9等238.774ms，其間處理36張 header。
   在 event9 被處理前先 vbuf。這證明該試驗有回收／推進延遲，
   **不能單獨證明相對成功舊版的唯一退化來源**。
4. GyroOFF 試驗有7次 vbuf前 RAW歸還，仍然失敗。不是所有試驗都完全不釋放。
5. native queue priority 比較 msg+4 kind，而5／8／9的 kind同為2B，event在+C。
   單改 queue attribute 不能優先8／9。
6. SSD volume+483C 的 C0670338 保留來源地址／長度，沒有複製影像。
   C0670690 分段消費，每段至多65536 bytes。媒體完成之前不能強制 free RAW。
7. 原始 ARM 的 FIFO、writer推進、scatter連續性三項受控測試通過；
   沒有模擬實際排程、cache、DMA、USB TRB 或 SSD timing。

更正舊欄位：99990005／C03A55C0 是 writer返回，並非 writer進入或持久化完成。
DEBUG 會改變排程；vbuf之後的延遲包含同步 stop/drain。
free branch／release入口的紀錄早於 allocator返回；停止後96/96另有讀回。
目前沒有跨測試累積池洩漏的直接證據，也不能排除其他種類的記憶體洩漏。

工具：`audit_recycle_path.py`、`test_native_recycle_contract.py`；結果與原檔 SHA在主報告旁。
原始 ARM fixture 初始失敗及修正紀錄都有保存，不是修改原廠韌體後才通過。

## 尚未驗證的線索，不能當作根因

- 19456 = native header reserve0x18000 − actual header0x13400；65536 = SSD segment上限。
  這是對齊線索。尚未找出在哪一層形成錯位，也未證明整個 RAW 一起移動。
- earlier SSD A001_274／275／276 與舊成功A193全數 TIFF在0；
  276 的 v15 CPU-header／4MiB guard 有生效，但 carrier／profile／batch也不同，不能宣稱 DMA單一因果。
- `m12_high_entry` 要求 S.VRATE23976／27972，所以 H2 的 VRATE0 即使capture240也不命中。
  這是具體 coverage 缺口，但此 helper還被 legacy canvas使用；
  直接放寬可能把 H2 p13+88=0 改成後來 r10 p83+88=4，破壞對照。
- 現行 producer 統一公式與舊 profile 有 class／preview reduction差異；
  離線 counterexample 證明當前 guard 不接受舊 profile，未完成通用公式修復。
- 沒有實作或安裝 queue重排、額外回收工作、池擴大或強制free。

## 已失敗或不應盲目重做的方向

v15 r10完整profile：SD240到101張／280到94張，SSD276到134張後vbuf。
v14 CPU-header＋local4MiB、global1MiB、GyroOFF均未達持續錄製。
Lossless不是所有失敗的必要條件：失敗樣本有12-bit Compression=1。
舊 SSD fast-path disable C069AD80 強制返回0曾使實機卡住，不要重播。
使用者提到 Downloads/fp-stop-leak-fix、fp-phase-detect；
STOPFX清理忽略忙碌／引用所有權，不曾安裝，不能當作安全修法。
不要將相同失敗試驗改名後重新要求使用者操作。

## 接手時建議先獨立反證，再選下一個改動

先讀成功版本與回收源碼兩份主報告，重新檢查推論，勿把本交接當既定答案。
優先比較 9/29 成功當時完整執行環境：實際 RAM hook／Gyro配置／載體／
application-rate與capture-rate分工，而不只重播部分sensor數值。
缺失的原始安裝 BIN／full-latch 必須繼續標示未知，不能宣稱已還原。

若追 SSD 錯位，需要同一build／同一profile的 header來源與目的、writer segment起點、
SSD scatter來源地址，定位第一個失真邊界。
若改回收排程，需要先證明控制／錯誤訊息順序及完整媒體引用所有權；
不能靠直接free或全域queue priority猜測修復。
CPU-header-only H2對照可以隔離一個變數，但只是一項尚未實作的試驗，
不能預先承諾它解決提前停止；不可同時改bulk／geometry以致失去歸因。

驗收至少需要：使用者指定的240／280持續時長、無自行停止、連續完整DNG、
sensor實際cadence的獨立證據、STBY／REC畫面無拼貼且FOV符合預期、停止後池回歸。
舊A193約20秒可作240復現參考；280沒有同等成功原始樣本，不要假定已曾達成。

## 最後已知連線狀態與操作注意

最近一次 host USB inventory只有RTL9210CN SSD，沒有SIGMA相機。
使用者先前說仍接電腦，但目前不能據此假定USB shell已恢復。
曾詢問保持開機、USB接電腦並確認「相機操控」模式，尚未收到該題回覆。
本文製作期間沒有發送任何相機操作；接手時先刷新enumeration及實際狀態。

按現有 skills 的流程操作：fp-camera-control、fp-usb-shell、fp-merged-card、
fp-unicorn-emulation，及 fpSup/AGENTS.md、fpSup/SUP_BUILD_RULES.md。
live操作持有 `/tmp/fp-af-fusion.lock`；寫入前新讀nativeREC0且HDMI綠色STBY。
無USB裝置時不要送命令；不要盲目重播未知結果的key／reboot；只處理確認的owned PID。
不要 live memmgr bufchk／bufmemget，也不要對相機clip子目錄dir。
新ARM hook保持LR／callee-saved與新call的8-byte stack alignment；
發布code按照C000E91C→C000EABC，不猜測空閒scratch RAM。
