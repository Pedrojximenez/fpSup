# 2026-10-11 最新狀態：依使用者要求撤回高速實驗

使用者回報 120p 錄影畫面會停住、240／280p 仍約一秒中斷，要求先還原
實驗前版本，之後僅修 RES-CUSTOM 高幀率設定。v39／v40、engine30、
matching tap 與 half-preview 均不是已接受的修復，不再沿此方向上機。

- `user-rollback-v38/deployment.json`：只將 32RESCUS.BIN 還原為實驗前 v38，
  完整長度 182720，SHA-256 `0751f2e6b6d30f84d38e6b0b7447bd7cfe3f766bb9fd8e97048017ca586031f3`。
  原 CFG 保留；AutoRun、LOADER、RES-Lab 分別完整读回未變。没有補白。
- 一次軟體重開後，`user-rollback-v38-boot.json` 及五個 v38 code slices
  (`user-rollback-v38-code.json`) 確認回退實際執行。PTP 介面占用已按 exact PID
  釋放，現有 replacement daemon 62470；正常 STBY。沒有重播 reboot。
- 本機 `ogc_layout.py` 撤回 v39 的兩個 ENGFPS60 修改，維持 v38 虛擬率資料；
  `rollback-v38-source-proof.json` 重新編譯逐位元等於凍結 v38，不會由下次建置
  再帶入已撤回的實驗。RES-Lab 公式、預覽路由、RAW pool 未改。
- 重新檢查完整已存 HDMI：`withdrawn-preview-freeze-audit.json` 證明
  v39-120-visible 的 scene ROI 在 frames62..218 连續157 frames 完全相同
  （按30Hz約5.23秒）。先前僅以 RAW582/582及停止成功就報120p正常是錯誤驗收。
  v39-280-chronology 同樣55..80連續26 frames停住。此結果不是新的錄影。

240／280p 設定及提前中斷尚未修復。感測器時序與 DNG FrameRate 標籤是不同
欄位，舊版仍把虛擬240／280標為120000/1001；改標籤本身不能聲稱修好錄影。
以回退版本為後續唯一基準，普通率回歸／高率驗收要檢查整段畫面動態，
不能把短窗一格 DNG 或單一 STBY 截圖當成完成。

---

以下保存舊實驗紀錄，不代表當前版本或已接受的修復。

# M12 分割再現：2026-10-11 初步診斷

最新實機反證（v39 重開後）：280p 原尺寸兩次短試錄分別出現半幅紫色與左右不同尺度；中間加寬的對照短窗正常，還原原尺寸並重啟 Live View 後仍重現，所以重建預覽並不足以解決。engine60 已進原生管線，但候選仍未通過分割驗收。120p 582/582 正常完成；高速短試錄都只有 1 格，不能冒充高幀率長錄成功。詳細補充見文末。

使用者回報 M12 只有 240／280p 分割，120p 正常。引擎格率錯配候選已通過
離線驗證，僅 consumer 已寫卡／完整讀回；目前載入的 v38 另以兩個 owned
data words 做同參數對照，沒有換 live code 或重新啟動。120p 已實錄及讀回
首／中／末 RAW，但第一段景物全黑，無法驗收畫面。之後有景物的 240p
試錄未見中央分割，但提前停止 94/92、REC 顯示卡住，取回第 92 格底部
有異常；280p 尚未錄製，不能宣稱整體已修復。以下保留診斷進程。

## 已讀到的實機事實

- `../20261010-sidebar-v13/20261011-m12-recurrence-before.json`：producer 17、
  consumer 9；即時配方 generation 7、活動列 VRC000，並非已儲存的 RCD。
  M12、992×662、1×1、沒有額外裁切、沒有鏡頭 desqueeze。
- `native-reads.json` 保存這次既有 runner 的原生回覆。
  `SetMovFramerate` 為 7，這是 119.88p 與虛擬 239.76／279.72p 共用的原生入口；
  尚未讀到 VRATE／實際感測器時序，不能據此指定確切格率。
- 最後一次 `rec log-out`：94/94、`vbuf/94/92001, raw1`、file-size 1,095,168，
  沒有取得這段的 DNG，因此沒有判定 RAW 是否分割或 header 是否有效。
- 卡上新增 `SS__1670.JPG`（308,106 bytes，04:11:18）。初讀尚未取回；
  後續已完整讀回並目視，見文末：239.76 REC 中央垂直分割／兩側比例不同。
- 詳細讀取第一次因 REC=1 守衛中止。稍後再次讀取時 USB 回覆 NO_DEVICE，
  新的 `inspect_current.py` 在第一個狀態 getter 即中止，沒有讀取配方或改 RAM。

## 離線核對與限制

當前來源仍保留 r78 等向預覽規則與 no-bin unequal-preview 拒絕守衛。
`test_reslab_preview_route.PreviewRouteTests.test_m12_r78_geometry_survives_virtual_rcd_and_native_selection`
於本輪實際執行通過（1 test，41.378 s）：29 個 producer 欄位、待機可見範圍、
64 個 profile 幾何字及 29.97p 感測器 timing 與凍結 r78 相符。
它不證明目前相機高幀率過渡期的 LCD／DMA 行為，也沒有取代實機驗收。

歷史 `../20261009-recording-formula/RESULTS.md` 的使用者「正常了」確認限於
M12 AUTO／29.97p 首秒預覽；舊 SSD 高幀率分割、壞 TIFF header 與提前停止
當時就未解決。此次症狀持續時間、精確幀率及 RAW 是否受影響仍待確認。

## 後續讀取

`inspect_current.py` 使用已驗證 header 的 v38 facts，僅讀既有 owners 的狀態、
producer canvas、當前 consumer base／variant canvas 和時序；不呼叫 picker。
需在待機／USB 連線時執行，保留獨立檔名。相機記憶體的完整比對尚未完成，
不能聲稱已定位根因或已修復。

## 使用者後續確認

使用者確認：120p 錄製正常，只有 240／280p 出現分割，與之前已修好的
29.97p 首秒切屏是不同問題。

緩衝擴容的歷史核對：`HSW_240FPS_MODE12.md` §71 記錄描述子池擴容曾因
NonCacheBuffer 配置及 shell 脈絡呼叫 heap 配置而失敗／凍結。
舊 `og3k_plan.py` 有 `OG_POOLDEPTH=300` 的 opt-in 實作，但現行 RCUS v9
來源與 v38 build facts 沒有該初始化或四個 pool-bound patch sites。
另一個 `OG_BUFCLASS=29` 額外影像緩衝嘗試在 §66 被確認為 SSD 異常的原因；
不能把它當作已驗證的 240p 修復。這次沒有重新啟用或移植上述實驗。

## 引擎格率錯配與候選（2026-10-11）

`ogc_layout.VR_TIME` 原本把 239.76／279.72 的真實感測器格率放入
`ENT_ENGFPS`。picker 鎖存後，`ogc_canvas` 把它寫入 canvas +0x30。
正常的原生 119.88 在此欄位是 60.0。

原始韌體鏈已以指令執行確認：

- `C0434EF8` 把 canvas +0x30 翻譯成 cfg +0x10。
- `C01D1630` 的 publication prefix 把 cfg +0x10 寫到 `C31DF574`。
- `C01D34F0` 讀該引擎欄位，`C01CEC08` 用 ROM 中的 99.0 做 >99 閘門。
- 這個閘門會改變 ISP callback／plane 配置路徑；實機分割是否由此造成尚待 A/B。

候選僅把 240／280 的引擎格率改為其原生 119.88 入口的 60.0。
感測器週期、VRATE、nominal、快門與預覽／RAW 幾何都保留。
這是待上機候選，不是「已修復分割」的結論。

`test_reslab_preview_route.native_engine_gate` 執行真實 translator、publication
prefix 和 HFR gate；模型／capability 查詢為明列 stub，在硬體設定前停止
publication prefix。它不模擬 DMA、畫面正確性或寫入吞吐。

| 配置 | sensor hmax/tail/vmax | 引擎 FPS | 原始韌體 >99 閘門 |
|---|---|---|---|
| v38 120 | 330/330/1820 | 60.0 | 0 |
| v38 240 | 330/330/910 | 239.76024 | 1 |
| v38 280 | 330/330/780 | 279.72028 | 1 |
| 候選 240 | 330/330/910 | 60.0 | 0 |
| 候選 280 | 330/330/780 | 60.0 | 0 |

新測試先對凍結 v38 執行，240／280 各有一個明確失敗（1 test / 32.218 s）。
候選 `test_reslab_preview_route` 3 tests / 94.346 s 通過：
高格率 canvas 全 65 字與正常 120 完全相同；29.97 的 r78 幾何、standby
區域與原始 CRCT route 保留；binning route 保留。
另外在模擬記憶體注入舊真實格率值，原始韌體閘門重新變成 1，證明斷言
能辨識這個回歸，沒有在共享來源中來回修改 mutation。

Res-Custom 的 picker、時序公式誤差、快門範圍／angle 與 Jose 原廠引擎
格率對照共 4 tests / 16.213 s 通過。沒有把 emulation 當成實機畫面驗收。

另更正來源／設計筆記把 engfps 稱作 DNG FrameRate 的錯誤。
`IMX410_FULL_DESIGN.md` §12.35 與原廠 writer 顯示 DNG tag 0xC764 經
`C00C9BD0` 讀取錄影設定有理數；engine 欄位不是該標籤的來源。
本候選不增加 DNG hook；現有虛擬率標籤問題須另行處理。

## 舊成品恢復到的參數

`extract_legacy_engine.py` 對保存的 `hsw-win-20260926/ctrl240/fpSup.BIN`
執行其原始 canvas hook，沒有從目前來源重建舊版本。
結果在 `legacy-ctrl240.json`：M12、330/330/910/x6、239.76024 fps，
RAW 2016×672、crop 2000×662、donor p13、engine 60.0。
此成品不能宣稱就是 A001_160 的確切成品；它是保存的舊 240 參考。

歷史已確認的素材：HSW §68 的 A001_160 為 10-bit、139/139、零位移，
實拍 0.58 s；IMX410 §12.33／§12.35 的 A001_170／171 為 12-bit，
RAW 1008×672、crop 992×662、RWZM 2048/1024、94 格乾淨停。
這些證明 240 曾產出乾淨素材，不能冒充長時間錄影或 LCD 正確的證據。
相鄰 9/30 舊 calculator 成品的 rate table 仍填真實格率，因此不可聲稱
所有舊成功配置都使用 engine 60.0。

## 候選產物與上機狀態

輸出：`../../cards/20261011-m12-engine60-v39/debug/`。

- `32RESCUS.BIN`：182,720 B，SHA-256
  `650c6fa0f27d216adba551cbec777741d42b39f4374e8b76db0f71dfbfe1cb85`。
  32-byte SUP header 與 v38 相同；core ABI 9 / RCD v3 不變。
- producer：609,720 B，與 v38 完全相同，SHA-256
  `dad8226db751fe10c2cac1f2f21269cc746957c7aacc5b19bec83dd027da155f`。
  候選目錄採用前一項已完成的檔名 `50RES-Lab v0.1.0test.BIN`；本次不需更新 producer。
- builder 生成的 AutoRun／LOADER 與 v38 不同（目前共用 loader 來源與選項），
  它們不是本次要部署的候選。若實機確認 owner／舊 consumer bytes 相符，
  只更新 consumer 並保留其 CFG 記錄，不動卡上的 AutoRun、LOADER、RCD、producer。
- 使用者回覆 USB 已接回後，host IOUSB 清單仍只有 hubs 與 AVerMedia，沒有 SIGMA。
  已請使用者核對相機端插接／USB 螢幕；沒有冒用 ACCESS recovery 或重啟 daemon。

待辦：待機時執行 `inspect_current.py NEW_TAG`，讀目前 VRATE／entry／canvas；
取回 SS__1670.JPG；核對原始 consumer、精確 CFG／檔長後才寫入候選並完整
讀回；再分別驗證 120→240→280 的錄影畫面與 RAW。SD 的提前停止不拿來
評估 SSD 240p 長時間吞吐，先驗證畫面分割。

使用者再次確認線已接好後，重新讀取 IOUSB 與 IOService：仍只有 hubs 和
AVerMedia，SIGMA VID 0x1003 沒有裝置／介面占用者。已存在的 fpshd PID 26613
仍是本專案 executable，host STATUS 回覆 camera=closed、quarantine=0、fault=none。
一次原生 `status get is_recording` 回覆 `ERR shl open 1003:c432 failed`，
未進入相機讀取。另查 system_profiler SPUSBDataType 沒有可用裝置項，
不把這個空輸出當作獨立的 USB 排除證據。已詢問相機螢幕狀態；没有重啟
服務、停止程序、送相機按鍵或寫入候選。

## 重新插接後的實機結果與待驗收狀態

- SIGMA fp 已重新列舉，沿用既有 fpshd PID 26613；原生 REC=0。
  `usb-restored-before-v39.json`：M12 992×662、12bit、VRATE=0、sensor
  119.88011988、engine 60；producer／consumer 均與 r78 幾何相同。
- `deployment-v39/SS__1670.JPG` 已取回：A001-018 / REC / 239.76，中央
  垂直分界、左右畫面比例不一致。不是先前 29.97p 首秒底部 seam。
- 第一次更新前檢查拒絕 exact pristine all-zero CFG，停止在讀檔階段，
  沒有寫卡。已把 guard 限定為 exact frozen default 或合法 magic/version/
  checksum record；不接受未知 CFG。首次執行寫入的自動權限審核逾時，
  尚未開啟程序；重試一次成功。備份與未知版本守衛均保留。
- `deployment-v39-defaultcfg/deployment.json`：只更新 32RESCUS.BIN，完整
  卡片檔案讀回 hash 等於上述候選；AutoRun 4666 B、LOADER 29276 B、
  producer 609720 B 前後完整 bytes 相同。96-byte pristine CFG 保留。
  沒有補白、改名、修改其他 SUP 或重開機。
- 卡片候選尚未經 reboot 載入。為保留現行 recipe，在 REC=0／AF lease 下
  核對 boot owners、frozen v38 code slices、generation=7、row=5、S_END／
  ENT table 範圍與精確原值，僅改兩個 data words：`0x4514694c`、
  `0x4514698c` 的 ENT_ENGFPS → 0x42700000（60.0）。
  `live-engine-plan.json`／`live-engine-applied.json` 保存完整 before/after；
  沒有修改任何 live instruction、FPSLATCH、時序、geometry 或 registry。
  下一次在舊 consumer runtime 重新 apply 配方可能重建 entries；本暫時
  A/B 必須重新檢查，不能宣稱此 RAM 修改會跨 reboot 或重建持續有效。
- 導覽中曾切到 stock UHD／8bit／25p，未錄製；已經正常解析度選單與
  原生 setter 恢復 RES-Lab／12bit／119.88，guard 確認同一 M12 recipe、
  同一 generation 和相同時序後才開始唯一新錄影。
- `corrected-120/trial.json`：新片 A001_022，觀察到 REC=1，fresh REC=1
  守衛後才發停止鍵，最後 REC=0；559/559、Button stop、UHS-II 119GB。
  已讀完整 1／280／559 格（各 1095168 B），TIFF 主 IFD 與 rawpy 都能
  解碼：1008×672、12bit、crop 992×662、FrameRate 120000/1001。
  只證明流程／資料可讀；三格感光資料幾乎都在 black level，不能判斷
  預覽／RAW 是否分割。此 SD 測試不代表 SSD 長時間高幀率吞吐驗收。
- 用完整裝置名稱 AVerMedia ExtremeCap UVC 擷取 240 個 HDMI frames，
  FFmpeg input 1920×1080，檔案 1024×576 RGB，按實際 frame count 限制，
  passthrough 不補格。OBS 沒有停止或改動。數字 device index 曾變動，
  一張誤取的非 HDMI 本機圖已刪除、不作證據；後續固定完整裝置名稱。
  HDMI 顯示 REC 變化但景物全黑，沒有拿 UI 動態當成 live scene 正常。
  已增加 record runner 的可见 scene detail guard，黑場會在任何 MOV key
  前中止。8 秒 HDMI 另以 FFV1 無損壓縮，完整解碼 bytes/hash 相同才
  移除暫存 RGB，見 trial.json 的 hdmi_archive。
- 正常幀率選單選中 239.76；`corrected-240-ready.json` 確認 VRATE=23976、
  native enum=7、sensor 239.76023976、engine 60、r78 geometry 零差異。
  `C31DF574` 讀回 0x42700000（60.0），目前為待機讀取，不冒充錄影中
  高幀率 gate 的實測。尚未在可見景物下實錄 240／280。
- 舊 A001_018 首格已完整讀回／正常解碼，EXIF 04:11:16，對應截圖
  modify 04:11:18 與畫面片號；有相同玩偶與粉紅物件，首格未見截圖
  中央分割。FrameRate tag 仍是 120000/1001。只能代表這一格，不推論
  全片 RAW 正常。指定第 240 格一次 read 的 open 返回 0，保留結果，
  不遍歷檔案或推論確切片長。

已請使用者取下鏡頭蓋／提供有光且可見細節的景物。目前停在 239.76p
M12 待機；未再錄製黑場。下一步是可見景物 120→240→280 前後與開始
過渡期畫面、各片首／中／末 RAW，之後再安排 SSD。修正版正式載入後
還需新 facts／owner 核對，不能沿用舊 v38 函式 offset 或原 heap address。


## 有景物的 240p：中央分割未再現，停止未完成

- `corrected-240-visible/trial.json` / A001_023：同一 generation 7、M12
  992×662／12-bit、sensor 239.76023976、engine 60.0。HDMI input 為完整
  名稱 AVerMedia、1920×1080；240 個實收 RGB frames，沒有補格。
  scene p99=73、std=16.22，有可比較的玩偶與粉紅物件。
- HDMI 20 格為 STBY、36 格開始有 REC；開始前後及實際原生 REC=1 時窗
  的樣本未見 SS__1670 的中央分割。這是單次短片的取樣，非完整高格率
  預覽驗收。RAW 1、46 格也未見中央分割。
- 原生 REC=1 最早 0.4125 秒、最後 1.004 秒；1.8212 秒變為 0。
  runner 沒有送停止鍵（stop_sent=false）。最後 8 秒 HDMI 的 REC／0:01
  顯示停住，不能把後面的紅 REC 當成持續錄影；一次正常 MENU 沒有效果，
  screen 仍 LV_CINE_MEDIUM。`stop-verification.json` 修正原 runner 將
  REC=0 誤稱 standby_after=true 的語意，真正畫面沒有回 STBY。
- native log 94 requested / 92 finished、vbuf/94/91328, raw1；header time /
  Button factor 仍是上一段 120 的值，不能說這次是 Button 正常停止。
  固定原廠 pool pointer 0xC2F1F3D8 讀到 0xC3520CD0、vtable 0xC0B99474，
  free_count=93。只讀 verified 原廠物件，沒有 allocator call／換池。
- 直接已知檔名取得 DNG 1、46、92 各 1095168 B；TIFF 主 IFD 均有效，
  1008×672、12-bit、crop 992×662、FrameRate 120000/1001。rawpy 均可
  解碼，但這不表示影像全部有效。第 92 格 raw row 641–671 尾部有異常，
  首／中格沒有同種異常。`raw-decode.json`、`raw-tail-audit.json` 與
  `raw-contact-sheet.jpg` 保存證據。
- 異常第一個像素在 row 641 / x358，對應約 file offset 0x100001；檔案
  0x100000 處竟是另一個 TIFF header（2000×1344）。這恰為 legacy
  read_direct 的 1 MiB round-trip 邊界。尚未獨立讀卡／換帶位址標記的
  read_bulk 重取，不能確定尾部是錄影寫檔損壞或讀取傳輸問題；兩者要
  分開驗證。前述停止卡住有独立 HDMI／native counts 證據。
- record_preview.py 已加入正面的 green STBY preflight／stop 核對。
  保存的 20 / 42 / 239 frames 分別判為 STBY / REC / REC，會抓到本次
  stop_incomplete。未見 STBY 時不送新的 MOV，也不自動做後續 file tools。
- 保存故障證據後送一次原生 reboot；回覆 LIBUSB_ERROR_IO，未重播。
  精確 PID 26613 host QUIT 收到 OK bye，25 秒後替代 PID 58079。
  fresh standby getter open failed；HDMI 為 No Signal、IOUSB 沒有 SIGMA。
  不宣稱候選已載入。已請使用者手動關閉再開啟、保持 USB。
- `v39-live-facts/` 是 host-only facts 相容目錄：新 consumer、同 bytes
  producer 以卡上實際檔名 50RESLAB.BIN 提供給 inspector；沒有改卡檔名。

待續：實機恢復後先證明候選 owner／code、正常 STBY，再核對 M12 recipe。
先對 A001_023 第 92 格做有位址標記的獨立讀回，辨識 1 MiB 異常來源；
停止卡住排查完成後才錄 280。沒有重加舊 pooldepth／BUFCLASS29，也沒有
將 SD 的提前停止推論成 SSD 吞吐問題。


追加離線核對：8 秒有景物 HDMI 已以 FFV1 無損保存為
`corrected-240-visible/hdmi.mkv`（52,242,421 B）。完整解碼得
424,673,280 B，SHA-256
`f9a7ae14936b991d4c85c5ca0178e7a5dc3b44b51d6e384e25e39def7a9e5e76`，
與暫存 RGB 完全相同才移除暫存。接近實際 REC=1 時窗的 20 / 34 / 42 /
50 / 64 frame PNG 另存；先前 record-frame-138 / 239 為卡住的 REC 畫面，
不再稱它們為實際錄影中／末期。

`read_frame_checked.py` 已準備好，以 maintained getfile 配置／讀檔／釋放，
只將主機讀回改用 source-address-tagged read_bulk，每塊檢查來源位址。
只接受該 trial 已讀過的已知 DNG index、精確長度、fresh (<30s) green STBY
證據、native REC=0／LV_CINE_MEDIUM／sd0；不送錄影鍵、不列 clip 內容。
已做語法與 exact path 檢查，尚未執行相機讀回。最後 IOUSB 摘要仍無 SIGMA，
PID 58079 是本專案 fpshd；等待手動開機恢復，沒有重播 reboot。

## 2026-10-11 使用者重開後的 v39 核對

- USB 恢復後，辨識 SIGMA interface 0 的 ptpcamerad claimant，使用已維護的精確 reclaim 路徑；daemon 58079 保留。
- `v39-running-code.json` 在 0x800、19008、22448、32400 核對新版 code bytes；後三段可區分 v38，確認真正開機執行的是 v39。
- 初次啟動 producer 未套用、consumer flag/current=0；inspect_current 改為不遍歷 inactive row，未把未套用 canvas 當成有效 recipe。
- 透過正常 Res-Lab UI 恢復 M12 992×662／12bit，generation=2；normal native fps setter 選回 119.88p。`v39-m12-ready120.json` 的 producer／consumer r78 canvas 差異皆為空，engine=60。
- 上次 A001_023 的第一格與第 92 格以帶地址 read_bulk 路徑嘗試重新讀取，但兩個已知完整路徑均 open returned 0；未執行資料回傳，沒有盲重試或列舉 clip 子目錄。保留 checked-read JSON；不能歸因為只有尾格消失，也不能排除先前 1MiB 無地址傳輸混入資料。
- 新版可見場景 120p：`v39-120-visible/trial.json` req=fin=582，Nothing／Button，最後 3 格與 `standby-fresh.png` 均為綠色 STBY；`v39-after120.json` 為 LV_CINE_MEDIUM、REC=0、sensor119.88、engine60、r78 零差異。所查看 HDMI frames 未見中央分割。
- 原 runner 要求最後 5 格全為 STBY，前 2 格轉場造成 phase=stop_incomplete；原紀錄保留，`stop-verification.json` 補記正常停止證據。更新為末尾 3 格連續正面 STBY；拒絕紅 REC 或未知畫面。
- 高速 SD 預覽 runner 改為第一個新鮮 REC=1 後再確認一次並送唯一 stop pair，不拿這種短試錄宣稱長錄／媒體通量穩定。

- 240p 新版兩次短測 `v39-240-short`／`v39-240-startup`（stop target:firstREC／0.85s），均正常 STBY、Nothing/Button、req=fin=1，A001_025／026 新 clip。REC flag 先於 RAW 連續寫入；這些短試錄只有一格，不能宣稱連續高幀率寫入已通過。畫面轉場樣本未見原本中央分割。
- 首格均以有來源地址的 read_bulk 讀回，1008×672／12bit／crop992×662，精確 1,095,168B；先前匿名 1MiB 回傳帶來的尾部風險不適用此新傳輸驗證。
- A001_024（120p）取回首／291／582格，精確相同長度与正確 raster/crop/bit depth；RAW 預覽能辨識實際場景。以微弱 RAW 訊號約 black256～283 做 auto-level 會顯著放大雜訊，不能把其低值直接誤稱黑畫面。原始 TIFF 與 PNG 保留。

## 280p 實機反證：v39 尚未修好分割

- v39-ready280-short.json：sensor279.72027972、VRATE27972、entry/variant18、engine60，與 r78 幾何零差異。
- v39-280-startup／A001_027：正常 Button/Nothing 停止、req=fin=1、末尾回 STBY；RAW 帶來源地址取回，1,095,168B／1008×672／12bit／crop992×662。只有一格，不代表持續寫入驗收。
- frame-058.png／audit-frame-058.png 抓到左半邊紫色、幾何錯位；全 240 格離線檢查，frames58–67 共 10 個 HDMI frames 同樣異常（約0.33s，包含停止過渡，不能說全是持續錄影）。逐格方法、分數、contact 保留在 all-frame-transition-audit.json。
- 同方法檢查 120、240-firstREC、240-0.85s 的全部 frames，沒有該 magenta 異常；這是有限短窗，不排除連續240p分割。
- v39-native-isp-after280.json 在正常 UI 回240、REC=0 後讀 C31DF574=60.0，證明 native publication 生效；不是錄影瞬間快照，不能反推全過渡每一幀的配置。
- 工程結論：候選v39尚未通過画面分割驗收；先不切SSD／不增加RAW pool，繼續核對過渡配置。

- 新增可逆寬度對照：正常 UI 一次選 Desq2.0x，得到 OUTPUT1984×662、RAW2000×672、preview2016×672、recordRWZM1032/unity；感測器M12、bin1×1、crop0、height不變，generation3。v39-wide-output-configured.json 保存 producer/consumer完整差異。這是診斷設定，不是最終解法；尚待280p短測，之後恢復DesqOFF/992×662。

## 寬度 A/B 與原尺寸重新套用的反證

- `v39-280-wide-startup`／A001_028：generation3、原生槽7、VRATE27972、engine60；限時0.85s，Nothing/Button、req=fin=1、正面 STBY。240 個 HDMI frames 的轉場樣本未見半幅錯位，contact 已目視。這是短窗，不能說連續 RAW 錄影通過。
- 唯一 RAW 首格以 source-address-tagged read_bulk 精確讀回2,095,104B；2000×672／12bit／crop1984×662。StripByteCounts 為2,016,008B，比 raster packed12 多8B；原嚴格 decoder 拒絕此長度，不把它誤判成壞影像。獨立 decoder 限制只允許末尾0–15B，記錄尾8B，不移動 row stride；預覽能辨識場景。
- 正常 UI 一次還原 DesqOFF，`v39-narrow-restored.json` 證明 generation4、原尺寸992×662、RAW1008×672、r78幾何零差異、VRATE仍27972。此操作走完整 Virtual RCD Apply／Live View stop-start，沒有改原生槽或幀率。
- `v39-280-narrow-reapply`／A001_029：同0.85s、req=fin=1、Nothing/Button、回STBY。HDMI frames59–66目視可見中央垂直接縫，左半幅放大／尺度與右半幅不同。沒有原先大片紫色；magenta fraction最高0.1626，低於0.2門檻，因此「沒有紫色高分」不能當成畫面通過。`audit_hdmi.py` 只作場景特定候選挑選，仍需要看圖。
- 結論：原尺寸重新套用也重現，排除「完整 LV reload 本身就清好問題」的充分性；縮放／來源尺寸與高速錄影切換的配合是線索，尚未證明某個欄位為根因。預覽跟隨 RAW 的舊 C 路徑會重新引入已知29.97p水平接縫，不直接回退到它。
- 歷史成功窄幅240（IMX410_FULL_DESIGN §12.33／12.35）原生槽為29.97；當前虛擬240／280借119.88槽。以維護中的 builder 做 process-local overrides 的 native30 對照版，production source 未改；只改兩個高速虛擬率的原生槽與 key suffix，sensor timing、engine60、完整幾何、producer與loader均保留。這是診斷候選，不是已驗收修復。

## 原生30槽診斷對照版 v40：離線與寫卡

- `build_native30.py` 的 overrides 僅存在建置程序中；不改 production source，不手工修 BIN。VRATES前兩項原生enum7→3、VR_TIME base row8→3，engine60與cycles300300／257400保留；vr_ui一致。builder兩座標PIC／大小／重疊守衛通過。
- Consumer182720B、SHA-256 `4358fce4127aedebbff0b93ea9db91f0a2805ae4cc013552dabc2f43e31c99dc`；entry由編譯器重算而差4B，header其他欄與96B CFG不變。沒有補白。producer、loader、AutoRun與其他資產逐檔相同；完整建置provenance保存於新卡目錄。
- 實際BIN的ARM integration：menu row9／10→原生enum3、實際picker選VRC00030、各自VRATE／nominal／timing330/330/910或780、engine60、完整r78幾何、native>99 gate=0、快門最低240／280、回普通29.97列清VRATE、callback計數與stack/table守衛通過。以v39反證同檢查在两個virtual rank均捕捉(7,row)≠(3,row)。
- 初次完整離線run的3個既有ABI／Apply／無效幾何守衛均通過；新案例的快門呼叫把第5個positional argument誤當r3（fixture實際是LR），造成2個UC_ERR_FETCH_UNMAPPED。改為顯式寫r3，僅重跑受影響新案例，30.412s通過；production BIN未改。保留初始失敗、修復後與反證logs，`v40-offline-proof.json`整合4案例。沙箱最初拒絕Unicorn執行記憶體造成SIGILL；已授權環境的run沒有該問題，全部都是離線。
- `v40-before-deploy.png`為正面greenSTBY；`deployment-v40-native30/deployment.json` phase=verified，實際原檔完整備份、CFG保留、僅寫32RESCUS.BIN、長度182720與完整source-address-tagged讀回一致。AutoRun、LOADER、50RESLAB再次完整讀回證明未變。
- 新候選在卡上，執行中仍是v39。已請使用者正常關機再開、USB保持連線；沒有重播前次uncertain native reboot。`v40-live-facts`僅host檔名適配，沒有改卡上producer名稱。下一步要證明新boot owner／code slices，再恢復M12原尺寸並做280→240短窗。未宣稱根因或畫面已修復。
- 六段新版 HDMI RGB 暫存均已保存為 FFV1；每段完整解碼回424,673,280B並與原檔SHA-256逐字節相同後才移除暫存RGB。各自`hdmi-archive.json`保留證明，PNG／trial／all-frame audit保留。相機RAW／clip未刪除。三段280畫面另有`manual-picture-review.json`，明確記錄兩個分割反證與中間寬幅短窗的限制。

## v40 authorized reboot and hardware counterexamples

- Single native reboot returned IO; no replay. Owned daemon58079 QUIT, replacement60279. HDMI and IOUSB proved boot; exact SIGMA iface0 PTP claimant58457 was reclaimed with the maintained adapter. Fresh REC0 and host faultnone.
- New consumer base0x45118ec0/state0x45144e00, producer0x45543340/state0x455d80f8. Exact eight-word headers and five code slices verified. Normal UI restored M12/992x662/RAW1008x672/12bit/bin1x1/crop0/DesqOFF, generation3; full producer/consumer r78 geometry unchanged.
- Menu remembered MainY5 rather than the expected page. Navigation entered reset confirmation Y5_5_1, without OK/commit; MENU exited and HDMI verified the main page before further navigation. No reset was performed.
- Native carrier3 verified: virtual27972, timing330/330/780, engine60. A001_030 (`v40-280-startup`) stopped normally, req=fin=1, positive greenSTBY. HDMI65-74 shows central vertical scale mismatch. Carrier30 does not resolve the fault.
- A001_031 (`v40-240-startup`) also stopped normally, req=fin=1. HDMI58/60/62/64/66 shows a displaced rectangular patch at upper left. No full-height central seam is not a picture pass.
- Both complete240-frame HDMI captures saved as FFV1 with full424,673,280-byte decode/hash equality before removing task-owned RGB temporaries. All PNG/JSON evidence remains; no camera files deleted. Magenta scores below0.2 missed both visible faults. Short one-DNG windows do not establish sustained high-rate recording.
- Diagnostic v40 is not accepted as a production fix. No pool enlargement or SSD trial. Production source does not include its carrier override.
- Next bounded clue: real native C01CEF08 has a class1/flag/near60 predicate that writes C2F16594. Standby independent reads were FPS60/flag0/class0/switch0, so activation during recording remains unproved. Proposed reversible data-only change is the two existing high entries' ENGFPS60->30, with timing/geometry/code unchanged and normal UI repick required.
- Offline fixture attempts preserved: initial missing explicit memset boundary; second correctly detected that entry data alone does not update FPSLATCH. Fixed fixture repicks after each data change, matching the intended live workflow. No live data change has yet been made.

## Engine30 and matching-tap hardware results

- Actual v40 ARM engine30 test passed in32.691s after the two explicit fixture repairs above. Both high entry words were changed F60->F30 with owner/code/generation/bounds guards and exact readback, addresses0x45146a0c/0x45146a4c. Normal UI repicked280. This is data-only diagnostic, not a card/source fix.
- A001_032 (`v40-engine30-280-startup`) still shows an upper-left rectangle at64/66/68/70; req=fin=1, normal STBY. A001_033 (`v40-engine30-280-firstwrite`, target1.05s) still shows central vertical mismatch65-72, req=fin=1, normal STBY. Between fresh REC1 checks at1.0598-1.0608s, native channel0 C31DF574 was30.0 and channel1 C31DF724 was0.0. Scalar reads are independent, not an atomic DMA snapshot, but30 did apply during this observed REC window. Engine30 alone is not a picture fix.
- Post-stop channel0 returned60.0 and channel1 remained0; earlier standby FPS60 reads establish standby publication only, not recording engine state. Do not infer that engine30 failed to apply from a post-stop60 value.
- Matching-tap offline exact consumer test passed33.005s. Four existing ROW_REC values changed only:0x0c2000->1008,0x201984->992,0x601023->2048,0xd82000->1008. Native selector changed E->[0,1,0]/mux[1,4]/record0 (C). Timing/RAW/other geometry unchanged. Data-only live plan/readback addresses0x4514706c/0x45147084/0x451470bc/0x45147104; producer remained unchanged, consumer differed in exactly these4fields. Normal native7->virtual280/native3 transition used to rebuild configuration.
- `v40-matching-280-firstwrite`: HDMI counterA001-034, continuous240frame capture. Fresh REC1 at0.4813s; next getter requested after target1.05s returned REC0 at1.7863s, so no stop toggle was replayed. req94/fin91, vbuf94, first write954->1531ms, positive STBY never returned. rec-log wall time remained previous11:52:19 and is not claimed as a fresh trial timestamp. No post-fault directory/file tools.
- Matching C reintroduced a horizontal lower-region seam visible42/48/54/60, consistent with the known r77/v11 failure. Later REC timer0:03 stalled. This is a negative result for both picture integrity and completion, not an accepted remedy; no SSD/pool experiment.
- Saved full HDMI and native transcript before sending exactly one authorized recovery reboot. All six RAM diagnostic words disappear on a verified new boot; card still holds diagnostic v40 until scoped rollback. Do not reuse old boot pointers or reapply these changes after recovery.

## Manual recovery and verified rollback to v39

- User physically powered off/on with USB connected after the failed matching-tap stop/recovery. Fresh HDMI `v40-manual-recovery.png` and `v40-before-rollback.png` show green STBY / A001-035. Existing owned fpshd61102 was retained; the maintained exact-interface reclaim released only verified SIGMA PTP claimant60309. Fresh REC0.
- New boot consumer0x451d4780; `v40-manual-recovered.json` and five immutable code slices prove v40, fresh inactive Lab/VRATE0. No pre-fault pointer or six diagnostic data words reused.
- `update_native30.py` rollback guard now reads the separate accepted 120p stop-verification evidence (last three positive STBY frames, fresh REC0/LV, Nothing/Button,582/582), preserving the original stricter five-frame false result. Rollback source bytes equal the pre-v40 backup outside the96-byte CFG.
- `rollback-v40-to-v39/deployment.json`: verified exact182720-byte installed SHA650c6fa0f27d216adba551cbec777741d42b39f4374e8b76db0f71dfbfe1cb85; CFG preserved, full backups and source-address-tagged readback; AutoRun/LOADER/producer independently read back unchanged. No padding or camera clip deletion.
- One authorized reboot, IO reply not replayed; owned61102 QUIT, replacement61334. SIGMA interface reappeared with exact PTP claimant61202, reclaimed. `rollback-v39-boot.json`, five v39 code slices (`rollback-v39-code.json`), fresh REC0 and green STBY HDMI `rollback-v39-boot.png` prove rollback is running. Lab starts inactive; no M12 recipe yet reapplied. HDMI scene is now defocused but standby status is unambiguous.
- Camera recovered; original 240/280p picture defect remains unresolved. v40/carrier30, engine30 and matching-tap changes are not accepted fixes.
