# GCSV-stream 掉針調查日誌 (2026-09-02)

## 2026-10-04：恢復優化至目前工作區並重新驗證

使用者要求續作。核對時工作區的 `gcsv_rows.S` 已回到優化前版本，先前新增測試也
已不在工作區；保存的 patch／測試產物仍在。只重新套入數字直接輸出與 held-pointer
兩項優化，未恢復 yield 診斷。GCSV raw blob SHA-256 仍精確等於前輪優化版
`c6e9f98bffaf057768bd099c587d903f031f378bc656692fdc17fb0bb07472bb`。

新增獨立 `gyro/test_gcsv_direct.py`，不依賴先前 yield 測試：10 項真正 ARM 測試
通過、零跳過，包含數字全域／ABI、跨區塊覆寫、刪除保存動作的 mutation、單次寫入
與 Base/GCSV JSON helper。兩組指令數、文字輸出及暫存寫入結果與下節相同。
共用開機三套重驗 29 項通過；舊 gyro suite 117 項中 116 通過，仍有同一項既存
lossless arena 固定位址檢查失敗，未放寬檢查。

本輪使用當前 builder／Fast Start 3 重新建置 12 組 before/after，六組對應 AutoRun
及 UI assets 一致，來源在建置前後穩定。比對僅針對本輪相同 loader 配置，不將
10/01 舊 AutoRun 當成目前封裝。紀錄與來源快照位於
`../validation/20261004-gcsv-direct-output/`。未上機，仍不能宣稱音訊問題已修復。

## 2026-10-02：直接輸出／減少暫存複製（僅離線驗證）

依使用者指示先檢查零拷貝空間、再實作兩項優化：`gcsv_rows.S::put_u32`
改成直接填入最終文字區；`gcsv_format` 在區塊持有期間保留樣本指標，返回前才
複製跨呼叫的最後一筆到 `G_HELD`。感測器環形資料快照仍保留，沒有把會覆寫的
硬體環形區直接排入背景佇列。writer 優先級、採樣、每區塊一次寫入與預設排程均未改。

真實 ARM 模擬兩組各 2,048 records，輸出與修改前逐 byte 相同：
小數值／起始 timestamp 指令數 400,398 → 282,908（-29.343%）；
極值／較大 timestamp 777,126 → 669,756（-13.816%）。
兩組每區塊的 held 樣本寫入皆為 16,064 → 8 bytes。
這些是合成輸入的指令／記憶體操作計數，不能換算成實機速度或聲畫同步改善。

15 項 direct／yield ARM 測試通過，零跳過，涵蓋數值全域、界限／ABI、立即覆寫原始
區塊、小輸出空間、最後一筆、單次寫入與移除跨呼叫 copy 的 mutation。
共用 JSON 數字 helper 三種版本 1,278 個案例亦通過。
GCSV／Base × plain／debug／Fast 的 before／after 共 12 個建置通過，對應 AutoRun
均相同；Base 因共用 JSON formatter 而改變 BIN，原始 GYR writer 路徑不變。
117 項既有測試中 116 通過，1 項仍是下節已記錄的 lossless arena 固定位址衝突。

結果、來源 patch、hash 與測試產物在 `../validation/20261001-gcsv-direct-output/`。
本輪未操作相機、寫卡或發布，音訊提早結束仍待實拍驗證。

## 2026-10-01：原始素材音訊超前、累積漂移（尚未修復驗證）

使用者回報目前最新 GCSV 版、多數幀率：原始素材的音訊約早畫面三格，
錄得越久偏差越大，最嚴重片尾約十五秒無聲。使用者進一步確認：畫面正常，
只有聲音提早結束。沒有保留可分析的素材，尚未能從檔案驗證 WAV sample 數、
是否內含靜音；儲存媒體、實際版本組合及片長也未知。
這是原始影音完整性問題，不能用 Gyroflow offset 或 GCSV tscale 修復。
單純漏影格會縮短影像時間軸、通常令聲音落後，不能拿來直接解釋此處的聲音超前。

此次離線追查的事實（以現行程式與 Ver.5.02 反組譯為準）：

- `gyro/gcsv_task.S::writer_put` 在優先級 6 的 task 內一次轉換整塊 16 KiB records，
  隨後一次寫出通常約 45 KB 文字；GCSV 自己零 drop 不代表原廠影音沒有受影響。
- 原廠 `AUD_INT` 的 ISR `C00D4178` 把單一事件字 `C31CC828` 設成 3，
  signal 的 semaphore `C31CC824` 最大計數為 1。消費工作 `C00D41A0` 清事件後呼叫一次
  `C31CC810` 指向的 callback，再累加 `C31CC830`。後者計的是已處理 callback，不是原始 IRQ。
- 正常初始化 `C01F9F50` 要求 AUD_INT 優先級 7；錄音初始化要求 16，但已有 task 不重建。
  兩者都低於 GCSV 的 6；本輪沒有讀取實機 task 優先級。
- 錄音 callback `C01FF278 → C01FEB20 → C01FEB60` 每次將累積位置增加固定 `0x1000` bytes
  （`DspAudioDevice::v8 @ C01FFEC0`），沒有從 DSP 寫入指標差補回略過的事件。
  因此若高優先級工作讓通知合併，可能壓縮音訊時間軸。**尚未量到 GCSV 連續執行時間，
  也沒有證明本次真的遺失通知。**
- 真正錄音 `DspAudioDevice::v1 @ C01FEF68` 配置 8 MiB + 16 KiB，並約每 4 MiB 或
  ring 邊界提交資料。`v5 @ C01FF3B8` 的兩個 16 KiB 是 AlevStart 收音表路徑；
  現行 `imu_stream.inc.S` 的「錄音只容許 85 ms」註解不可拿來作為根因證據。
- 音訊與 GCSV 共用儲存鎖，但 mutex 持有不等於關中斷或禁止全部 task 排程。
  原廠 audio writer 不檢查寫入回傳值，亦有依 offset seek 的路徑；寫入失敗／空洞
  與 callback 計數縮短是不同假說，仍需素材或診斷數據區分。

主要來源：`out/decomp/full/blk_c00.c` 的 `C00D41A0`、`AUD_INT`，
`blk_c01.c` 的 `C01F9F50`、`C01FEB60`、`C01FEBA8`、`C01FEF68`、`C01FBD40`；
ISR 事件覆寫另外以 `out/MAIN_c0000000.bin` 的 Thumb 指令核對。

本輪只製作 opt-in 排程對照候選：GCSV 每至多 128 筆轉換後讓出 1 ms，
維持優先級、完整樣本及每原始區塊一次寫入。預設建置保持原行為。
不能把它稱為已修復；離線模擬只能驗資料與 ABI，不能模擬真實排程或儲存延遲。
不可為此直接改成多次小寫入，本文既有實測已記錄這條路的退步。

驗收需要同設定的原廠、Base、GCSV control 與候選對照，保留完整 DNG/WAV/GCSV，
拍攝開頭及結尾可視／可聽同步事件。檢查 WAV 真實 sample 數與尾段內容、DNG FrameRate
及 TimeCodes；舊素材實際有 `0xC763` TimeCodes，不能沿用「DNG 沒有時間碼」的舊說法。
檔案長度差不能單獨當成聲畫 offset。若可做原廠事件診斷，需分別計 raw IRQ、
已處理 callback、DSP byte count，並量 formatter 最長連續執行時間。

本輪建置／測試紀錄存於 `../validation/20261001-av-drift/`。未操作相機、寫卡或發布。

## 目標
解 GCSV-only stream 模式(錄影期直接寫文字 GCSV,不產 GYR)的掉針。主線 = stream(取代 v1.1 的
GYR 後處理);GYR 模式錄影期只寫 raw,零掉針。

## 硬數據(初期)
- 純 r23(雙槽32KB+64K寫,全採2500Hz,PGEN 3e729c0b):A001_002 21s = 99.32%,掉的 360 列幾乎全在
  1 個 142ms 大缺口 → 偶發尖峰,不是持續落後。
- 同段 142ms 音訊 WAV 完整沒掉 → 不是全系統卡死,是陀螺這條線特有。
- 用數字排除:CPU 算力(轉一列~70指令,2500列/s=17.5萬指令/s,用不到萬分之三)、寫入速度
  (卡 97MB/s vs 文字 0.1MB/s)、緩衝空間(pool 1MB 尾巴空 ~570KB)。

## 試過並撤回的(全靠推理、沒先量)
1. 降採樣 1250Hz(r36):99.99% 但拿溫和片比高動態片,未控變數(用戶:「1%是浮動」)。
2. callback 端降採樣:注入區溢位 64B,擱置。
3. poll 5ms→1ms:**GCSV 整段消失**——poll 間隔是多個 loop-based 計時基準(Q_OPEN_DELAY、
   open_ticks、pg_boundary),縮它把延遲全縮 5 倍,打亂時序。
4. 優先級 28→8:更糟(96.92%),多了大缺口。定時看模式提高優先級搶 CPU 害到陀螺擷取(20)。
5. 加大雙槽 128KB:撤回,緩衝深度非瓶頸(142ms 只積壓 <3KB)。
6. 「CPU-bound=根源、GYR才對」:自相矛盾撤回(CPU 快即不佔 CPU)。

## 音訊架構(agent RE)
- 無共用寫入隊列;影片、音訊各寫各檔,只共用單一 SD 卡鎖(XC_MediaDriverSdcard+0x3c,0xc351ee18,
  FUN_c036b1e0),mutex 不可搶佔。
- 音訊不掉靠:8MB DMA ring(~40s)+ 32 深指標隊列(零拷貝)+ 專屬 writer(AudF_W@c01fd380,
  優先級 6,阻塞式 recv)。音訊 writer 是 IO-bound(寫 raw,等鎖時讓 CPU)。
- 優先權(小=高):SRecFile 6、ImgCtrl 7、SRecMgr 9、GyroData 20、我們 writer 28、RECMGRMV 50。

## 備用位址
~~tk_slp_tsk@0xC01F8CC4、tk_wup_tsk@0xC01F8A84、tk_dly_tsk@0xC01F89CC~~ **⚠️ 這三個都錯,是 stub+0xC(那條 `ldr ip,[pc,#0xc]`),不是函式入口。**
正確:**tk_slp_tsk@0xC01F8CB8**(service 0x80110100)、**tk_wup_tsk@0xC01F8A78**(0x80120100)、**tk_dly_tsk@0xC01F89C4**(0x80460100)。
掃法:每個 stub 的 service ID 存在 stub+0x20,四個已知正確的 stub 都符合這條規則
(`tk_cre_tsk@0xC0016A58`→0x80010100、`tk_sta_tsk@0xC0016BC0`→0x80030200)。
四個 stub 的位元組完全相同:`push{r4}/add r4,sp,#4/push{lr}/ldr ip,[pc,#0xc]/bl/pop/pop/bx lr`。
照舊位址呼叫會跳過 prologue —— 在優先級 6 的任務裡就是凍結。2026-09-06 掃描修正。
pool ptr 0xC3757A7C(本次 0x44F6ADC0);logger state r10=pool+0x6000;S_DROPPED=+0x14;
pool 碼窗 0x44FE1DD0(=S_JSON_FN−0x38C);fpshd vid 1003/pid c432,EP01/82,/tmp/fpshd.sock。

## 結局(2026-09-02 晚)— 掉針線已解,機制與槓桿皆實證

### 診斷:USB shell 直讀 S_DROPPED
乾淨 shell 卡 + load.py 熱注入純 r23 stream logger(PGEN 先 putfile 上卡),錄影期 kill -9 fpshd,
錄後重接讀 pool+0x6014。**S_DROPPED=3402(1.36s)**,與 GCSV 缺口逐筆吻合(3405)→ 掉針 = 桌子滿,
擷取停排除。缺口 5 次 180–342ms 全在用力晃的後半,0 次 >1.6s。

### 機制
雙槽:一槽 1.6s 填滿;writer 服務另一槽若 >1.6s 即溢出。用力晃 → 五位數 → 一槽文字 ~148KB → 3 次
64KB F_WRITE;每次等影片放卡鎖 ~0.5s(我們 28 墊底,影片/音訊 6 先搶)→ ~1.9s > 1.6s。
轉文字快;時間 = 等鎖 × 次數。位元組頻寬綽綽有餘(0.1MB/s < 音訊 0.19MB/s),缺的是「輪次」。
解釋全部歷史:poll/優先級無效(writer 卡在 F_WRITE 內等鎖)、32K 更慘(次數翻倍)、256K 曾害影片
自停(握鎖太久,mutex 不可搶佔)、64K 是兩面夾殺的平衡點。

### 受控 A/B(同機、同晃法、只換 PGEN,熱重載)
| take | PGEN | S_DROPPED | 完整率 | 缺口 |
|---|---|---|---|---|
| A001_001 | r23 全採七欄 | 3402 | 97.757% | 5 次 180–342ms |
| A001_003 | r36 1250Hz+sparse | **0** | **99.994%** | 0 |
晃動強度相當(五位數占比 10.3% vs ~11%)。**r36 把每槽 F_WRITE 從 3 次壓到 1 次,掉針 3402→0。**
「文字變小」= sparse(accel 只在新值那列寫;r23 每列重寫 53×,實測 96% 列變四欄)+ 1250Hz(兩筆平均)。

### 狀態
- 源碼樹 fpSup/gyro/gcsvgen.S 已含 r36 邏輯,PGEN 雜湊 9fe5ce1c6b31 逐位元等於實測版;測試綠;未 commit。
- 相機:乾淨 shell 卡 + 熱注入 r23 logger + r36 PGEN;daemon 已重接(錄影前需 kill -9)。
- **未解(獨立線)**:JSON width=0 —— A001_003(第三段)S_GEOM 仍 0×0、無 JSON,非僅冷開機第一段;
  0xC37CE210 在 stream 模式下可能整段為 0。下一題。
- Shell 配方:PGEN 熱重載(putfile + S_POOL_TRIED 歸零 + 指紋驗證)、大檔 getfile --size 直讀
  (韌體回 actual,本機截)、絕不對大資料夾 dir(端點失步,重啟 fpshd 復原)。

## 收尾(2026-09-03)— 三條線全部實證收乾淨

### 接縫時間戳(r37 gcsvgen 接縫延續)
每列輸出時記 ST_NEXT_EXPECT(兩筆平均 +800、單筆尾 +600);新區塊開頭:**S_DROPPED 自上一區塊未變 → 接上網格**
(硬體 2500 Hz 嚴格等距,重定錨只會把 callback 延遲帶進時間軸);變了 → 重定錨留洞;另有 10240 µs 保險上限
(< 最小真洞 14.5 ms)。狀態字 ST_NEXT_EXPECT=0x3C、ST_PREV_DROPPED=0x40(雙槽下休眠的 S_C 記錄空位)。
迭代:猜容差 600→1536→4096 µs,殘留 7→2→1(延遲尾巴 0.65/1.2/1.8/4 ms 一路冒出來);改成計數閘後
A001_007:38874 列、只剩 800/600 兩種間隔、殘留 0、S_DROPPED 0、單調。**教訓:別猜延遲分布,用硬計數器當閘。**

### JSON(profilegen pg_dng_dims)
尺寸改讀該段自己的 DNG:路徑 = O_GCSV_PATH 資料夾 + TopFile(0xC358E148 裸檔名);open mode 1、讀 1 KiB
到 O_READ、解 IFD0 找 0x100/0x101(內嵌,無 SubIFD)。S_GEOM 在 stream 模式整段 0×0(004–007 皆是),
不再依賴 0xC37CE210。A001_004/005/006/007 四段 JSON 全部正確(1936×1090, mode 106, readout 10.556)。

### 最終基準 r37 = r36(1250 Hz + sparse)+ 接縫延續 + DNG 尺寸
- 源碼 fpSup/gyro(logger.S 雙槽、gcsvgen.S、profilegen.S),測試全綠(safety 28、format 12+seam 6),未 commit。
- 打包 codex/fpgyrosup_releases/fpGyroSup-stream-baseline-r37-20260903[.zip];PGEN ae19da252532 = 相機實測版。
- 相機:乾淨 shell 卡 + 熱注入 logger + r37 PGEN;daemon 接著(再錄前 kill -9)。
- 掉幀線:3402→0(受控 A/B);JSON 線:width=0 已解;接縫線:殘留 0。stream 可正式取代 GYR。

### 長片驗證 A001_008(2026-09-03,手動停,15.4 min,r37)
DNG 27,706 張連續、全 3,244,544 B、零 0-byte;WAV 對齊;GCSV 1,156,985 列、S_DROPPED=0(資料 100%)、單調。
接縫殘留 18 個(10.9–11.5 ms,609 接縫的 3%)= callback 延遲尾巴 > 10 ms 保險。因與最小真掉樣 14.5 ms 只差 3 ms,
不再調上限;下一步改「封緘時快照 S_DROPPED 進區塊」的精確比對(見 memory)。JSON 正確(1936×1090)。
教訓(shell):getfile over-ask 40 MiB 卡死相機配置器(需重開機);上限 32 MiB,大檔走讀卡機。

## r38 — exact seal-time drop snapshot (2026-09-03, built, not yet verified live)
- The 15.4-min r37 take left 18 seams of ~11 ms, all at blocks where the callback
  latency tail delayed the first sample after a seal. Tolerance guessing (600→10240 µs)
  kept leaving residuals, so the tolerance is gone.
- Callback now stores S_DROPPED into the slot record's spare +4 word at BOTH seal sites
  (select_buffer and recording_stopped). Writer copies it into the block header CRC word
  (stream builds never persisted a CRC). gcsvgen compares this block's seal count with the
  previous block's; equal ⇒ no drop between the two seals ⇒ continue the grid, regardless
  of anchor latency. Guard is now a 65 ms sanity bound only.
- logger 3728 B (headroom 192), PGEN 235d5933 written to card root. Tests: 28 + format all OK.

## r38e / r39c (2026-09-03) — attach gate, JSON without DNG, idle lens cache, early JSON
- r38 seal snapshot verified: A001_003/004/008/009/010 all S_DROPPED 0, intervals only 800/600 us, no gaps.
- A001_005..007 were never logged: the firmware publishes MovieRecording to 0xC347DF38+0x157 OR, when the
  movie-engine selector 0xC347D1C0+0x14 (synced from the "LDAFR" serial status packet) reads 0x21, to
  0xC34765CC+0x3D (publisher FUN_c0332480 / test FUN_c0352e18).  Observer: 219/219 unattached polls had
  +0x157 == 0.  r38e mirrors the publisher's selection in the callback (+4 B; two cmpne folds paid for it).
  The 0x21 path has not been exercised since (008/009/010 attached on the 0x11 path).
- JSON dims: CameraMgrSetting registers cam_movie_imagesize.h/.v at 0xC3758B98/9C (FUN_c0419db8, base
  0xC375953C).  pg_setting_dims = setting + 16/10 replaces pg_dng_dims; regenerated A001_008.json byte-identical.
  (Mode-table geometry is the sensor readout, 3032x1708 for mode 106 -- correct for rolling shutter, not for dims.)
- Lens: the two ~700 ms bus reads (B_FOCAL, B_NAME) now run in the writer's idle poll (pg_lens_cache_poll)
  guarded by a 68-byte LENS_REGION fingerprint; cache fills within 1 s of idle.  Known window: REC pressed
  during a cache read (right after boot or a lens swap) delays the adapter's publication by up to ~1.4 s.
- Early JSON: pg_json_early writes the profile once O_LC_STATE==4, S_FILE==2 and S_MODE_RUN is sampled
  (block 1-2, ~2-3 s into the take).  A001_010: EARLY_RES=1 at SEQ=2, stop-time job skipped (SKIP=1),
  JSON identical to the stop-time build.  The stop-time path remains as fallback (cache miss / early failure).
- Trap found on the way: pg_write's return-value gate also required S_POST_BUSY==1 (three gates, not two).

## r39d (2026-09-03) — release-card regression found and fixed
- First release card (r39c): first take after boot not logged; no JSON on any take.  Debug card reproduced both.
- Cause 1 (JSON): 0xC3758B98/9C is the USB shell's `setting readcam` mirror of CameraMgrSetting, not the live
  setting; it reads 0 unless the shell command ran.  Live block = FUN_c0206e98() + 0x40 (1920/1080 verified).
- Cause 2 (first take): the idle lens-cache bus reads at boot blocked the writer task while the user pressed REC.
  Replaced by the firmware's lens-info singleton (FUN_c03341c8 -> 0xC3464980, name +0x24, focal +0x68); with the
  boot-time bus reads gone the immediate-after-boot take is logged (A001_007 on the debug card).
- Cold-boot debug-card verification: 007/008/009 all logged, all JSONs early (SKIP=3), identical to reference.
- Lesson: the shell-card verification passed by accident (the readcam mirror had been filled by my own RE).
  Anything read from RAM must be traced to the firmware's own writer of that word before it counts.

## Portrait takes and Gyroflow (2026-09-03, r39d kept)
- Gyroflow 1.6.3 decodes the DNG sequence through MDK/FFmpeg's tiff decoder as stored: 1936x1090, no rotation
  (GUI log: "tiff 1936x1090 bayer_rggb16le", transform orientation 0).  FFmpeg's tiff.c never reads TIFF_ORIENTATION.
  So for Gyroflow the correct gcsv for a portrait take is the body-frame "xyz" and the landscape JSON, exactly as
  for landscape; the stabilised output is sideways and is rotated in the NLE.  Verified headless on A001_014
  (EXIF 8): stored frame + xyz + offset -250 ms -> residual motion 2.52 -> 0.07 px (1/4 scale).
- If the frames ARE rotated to the display orientation (a real portrait video), the mapping is EXIF 8 -> Yxz,
  EXIF 6 -> yXz (measured; the geometric derivation had the pair swapped), JSON needs no change (Gyroflow swaps
  the profile dims itself), readout direction makes no measurable difference.  A per-take header patch using
  FUN_c00c9b48 (1/3/6/8 -> xyz/XYz/yXz/Yxz) was built (PGEN a5744455) and reverted; not shipped while Gyroflow
  leaves DNG sequences unrotated (open issue gyroflow#1117).
- The user's portrait failures were autosync failures, not axis errors: GUI log "Setting offset at 2936: 2283
  (cost 936)" and "Sync point out of acceptable range" on a 5.8 s take.  Manual offset works.

## Portrait, settled end to end (2026-09-04, r40 = r39d + per-take orientation)
- The user's real pipeline is Gyroflow (project) -> DaVinci Resolve + Gyroflow OFX.  Resolve hands the plugin the
  frame rotated per the DNG Orientation tag (exports were 1080x1920).  Measured on Resolve's own exports of
  A001_014 (EXIF 8, sync offset -250 ms): rotation 0 + Yxz -> residual 0.37 px (input 2.52); rotation 0 + xyz
  -> 2.35; project rotation 270 + Yxz -> 1.39.  So the camera writes the orientation per take from
  FUN_c00c9b48: 1 xyz, 3 XYz, 6 yXz, 8 Yxz (PGEN a5744455, shipped as r40).
- The earlier "nothing works" was autosync producing +2283 / +3997 ms on short portrait clips; with a manual
  offset the same data stabilises.  Next: anchor the gcsv time origin to the first DNG so offsets sit near 0.

## Portrait: scope decision (2026-09-04)
Landscape is the supported case and needs nothing.  Portrait is handed to a host-side tool, by the user's
decision, after these were tried and rejected:
  - per-take gcsv orientation (r40/r41, PGEN a5744455): correct only if the project's dimensions are rotated
    too, which no sidecar can set.  Reverted.
  - gcsv time origin at the flag rise (r42) and at the first-DNG open (r43): the flag led the first frame by
    3.81 s on a cold-boot take; the open tick is card-dependent.  Neither is a frame-exposure anchor.  Kept as
    codex/fpgyrosup_releases/r41_orientation_and_origin.patch.
  - suppressing the DNG Orientation tag while recording (orient_stub.S + one word over the bl at 0xC00C32C8,
    stills untouched via the MovieRecording flag): built and verified in the section table, not shipped -- the
    user chose not to alter the CinemaDNG.
Measured matrix, Resolve exports of A001_014 (EXIF 8, offset -250 ms), residual frame-to-frame motion in px at
quarter scale, input 2.49-2.52:
    video 1090x1936 + rotated profile + Yxz   0.26   correct                (project E, what the tool writes)
    video 1090x1936 + landscape profile + Yxz 2.03   barely stabilised      (dimensions alone are not enough)
    video 1936x1090 + rotated profile + Yxz   4.33   worse than the input
    video 1936x1090 + landscape profile + Yxz 0.37   3x magnified, stretched
    video 1936x1090 + landscape profile + xyz 2.35   barely stabilised
Upstream is unlikely to move: gyroflow#1117 (DNG), #1115 (Insta360 FreeFrame, rotation applied twice),
gyroflow-plugins#38 (Resolve, vertical, settings do not persist), gyroflow-ofx#48 (GoPro vertical, 2023).
The three open ones have no maintainer reply.

## Boot time (2026-09-04/05) — 10.8 s -> 9.0 s on the release card
Timed on the camera, power-on to `fpSup!`: the debug card (166 commands) takes 11 s and the release card
(113 commands) 9 s.  Those two solve to about 38 ms per AutoRun command and 4.7 s of fixed cost -- the
camera's own start-up, the 1 MiB pool and the file read together.  The older note in this repo (60 ms per
`mem set`, 6 s camera, 4 s pool, 18 s total) does not describe this configuration and should not be used.
Everything except the loader already travels in VSHL.BIN, so the only lever is the loader's word count and
the progress bar.
  A  progress sent twice instead of three times (FPSUP_THIN_BAR=1 still sends once)      -15 commands
  B  firmware calls as one-word `bl` instead of movw+movt+blx.  The assembler lays the
     loader out at zero, so the offset is computed from LOADER_BASE (passed in by
     build_autorun) and a label difference; `.` is not a relocatable expression.        -16 commands
  C  the loader's second half (place the sections, cache maintenance, branch to the
     entry) moved into VSHL.BIN as its first section, destination 0 meaning "run where
     it lands".  Stage one keeps: restore the callback, open/read/close, check the
     magic, clean the cache, hand over the buffer.                                      -16 commands
Loader 100 -> 68 words (release), 131 -> 91 (debug).  Release 160 -> 113 commands, debug 224 -> 166.
Verified offline against the built binary (header, section table, stage2 bytes, every destination, the
AutoRun's own words, the hook armed last) and then on hardware: the debug card boots and the USB shell
answers, which exercises both stage-2 paths -- placing the worker and branching to the file's entry.
Not taken: shrinking the 1 MiB pool.  The whole fixed cost is 4.7 s including the camera's own start-up,
so the allocation cannot be the 4 s the old note claimed, and a pool relayout would buy nothing.
