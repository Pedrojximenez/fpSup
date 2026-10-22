# fp AF Assist — 接手入口

**目前先做 P0：多接點 hook＋USB 持續資料平台。** 使用者要降低逐次操作／讀 RAM／整理資料的實驗成本；一次開始受限觀測 session，連續收小批次、自動保存與重播。AF 產品仍是純機內 CINE 錄影連續對焦，正常使用不依賴電腦。

先讀 [完整開發清單](PLAN.md)、[資料平台計畫](notes/AF_TELEMETRY_PLATFORM_PLAN_2026-09-27.md)、[hook catalog](notes/AF_STREAM_HOOK_CATALOG_2026-09-27.md)、[transport gap](notes/AF_STREAM_TRANSPORT_GAP_2026-09-27.md)。57 份散落 AF 正文已集中，後續新筆記直接放 [本專案 notes](notes/README.md)；程式、原始量測、tool-sources 與封存資料維持原位。

**最新實作（9/28 第二輪）：[hook 分級、重入偵測與不輪詢匯出](notes/AF_HOOK_STAGED_NOPOLL_2026-09-28.md)。** 使用者定調重心在 hook 與快速導出、不主動讀記憶體。recorder 加入 off/count/record 三級（預設 count，第一次上機只看計數器遞增）與重入偵測（`in_body` 標記＋latched `overlaps`，偵測到就永久停止發布但仍完整重放原廠呼叫）；資料路徑改為「arm → 一次 sleep，視窗內零 USB 交換 → 還原 → 一次 bulk 匯出已提交前綴」，不再輪詢 header 等 full。capture schema 升為 2，`af_sender.c` 拒送重入／未收尾的 capture。recorder 27 tests＋7 個突變全被抓、installer 32 tests、highrate 165 tests 全過。**重入偵測是普通 load/store 不是互斥證明**（ABI 稽核未審 r2/r3/r12，strex 需第三個暫存器）。同輪核對了舊「全能控制台」時期[同接點的 stage1 子系統](notes/AF_PRIOR_HOOK_REVIEW_2026-09-28.md)，取其分級與重入設計，不取其 mailbox 輪詢路徑。該核對曾指出一道 cache 同步的閘，**同日稍後已排除**：那個機制需要第二顆核心，而全映像**沒有任何 MPIDR 讀取、沒有 SCU/PERIPHBASE 存取、沒有廣播 ICIALLUIS**，且原廠自己的 D-cache 維護用 **set/way**（架構上不廣播，只有單核才成立）。執行這份映像的 ARM 核心只有一顆，所以從 shell task 發布的程式，AF observer 取指時看得到；發布順序（先 D 後 I）仍必要。[單核證據](notes/AF_CACHE_COHERENCY_2026-09-28.md)

**9/29：[EP83 T0 離線完成](notes/EP83_T0_2026-09-29.md)。** 核對 fpshd 後確認它要的 terminal 就是 worker 的一般 `shl` 回覆 frame，所以 T0 **不需要第二個 owner**：worker 全程保有 EP01／EP82，sender 經借用的 echo 在一個普通 shl 命令內只碰 EP83（physical 7、logical 3、TRB 指標 `C31E3270`、control `0x813`，序列與 worker 的 `arm_in_block` 相同）。`af_ep83_control.c` 的 CMD4 adapter 明確不使用。新增 332-byte [ep83_send.S](highrate/ep83_send.S)（16 tests，6 個突變全被抓；`dsb` 改以真實位元組的指令順序檢查，因為 Unicorn 不模擬 barrier）與主機 runner [ep83_t0.py](highrate/ep83_t0.py)（11 tests，`--run-live` 目前直接拒絕）。配置器已接上：抽出 [user_alloc.py](highrate/user_alloc.py) 讓 AF 探針與 T0 共用同一份 claim／allocate（bump 寫入守衛、一次配置、DMA 視窗與 worker 重疊檢查，5 個突變全被抓），`boot_allocator()` 取四個 cave 區塊與一塊 64 KiB USER 配置。抽出時修掉一個自己造成的回歸：被拒配置的 raw receipt 曾經消失。**尚未上機**：要換上有 EP83 的 daemon（現行 binary 自 9/25 起沒有）、並證明原廠 PTP event sender 不爭用同一 TRB；USB 仍 NO_DEVICE。

**9/28 第三輪（關機還原現行做法）：[關機還原改走 loader journal](notes/AF_LOADER_CONVENTION_FINDING_2026-09-28.md)。** 查到維護中的 `HOOKS_AT_POWER_OFF.md` 明訂：2026-09-25 起關機還原由共用 loader 負責，**sup 不再自己註冊關機回呼**；執行期才裝的 hook 接點改為在卡片宣告成內容為韌體原字的 4-byte 區段。文件另載明韌體自己已占普通清單 10 格中的 8 格、強制清單 1 格，所以自帶物件會吃掉最後一格。因此第一輪的自帶 power-off 物件**已退役**（檔案保留、測試明確跳過、不在任何安裝路徑上）。現行：`hook_site_section.py` 由已核對 ROM 產生區段檔與 `--also-bin` 參數；`shutdown_restore.py` 改為由兩張清單找出 loader journal block 並讀出記下的原字；`af_hook_trial.py` 只驗證、不註冊、不占格。23＋33 tests、6 個突變全被抓、highrate 141、專案根 533 通過。**尚未做卡：** 要真的受保護，測試卡必須加上該區段並冷開機。echo 不走 journal（stage2 執行時可能仍借給 lboot），由主機還原。

**9/28 第一輪（已退役）：[power-off 物件](notes/AF_POFF_RESTORE_GUARD_2026-09-28.md)。** live gate 從無條件封閉換成可驗證機制：探針自帶 468-byte 還原物件，寫入前唯讀核對普通／強制兩表有空格，註冊後重讀物件與兩表，武裝 AF 接點前再驗一次，`shutdown_restore_verified` 只由第二次裁決設定；沒有任何略過選項。guard ARM 真實機器碼 33 tests＋6 個突變、裁決解碼器 16 tests＋3 個突變、installer 27 tests、highrate 全套 152 tests 通過。**只覆蓋普通與強制關機**：抽電池／當機沒有 callback，暖開機保留 cave 卻重建 heap，veneer 的 boot-stamp 守衛仍待補，仍無實機註冊。另已分清兩條 USB 通道：[EP82 已完善上機、EP83 未接通](notes/AF_CHANNEL_STATE_VERIFY_2026-09-28.md)。

**9/27 實作：[第一個 AF hook／高速通道增量](notes/AF_FIRST_HOOK_CHANNEL_2026-09-27.md)。** fpshd 原始碼已加入同 handle 的 EP83 consumer 並通過離線測試；執行中的 daemon 未替換。另有 1100-byte ARM allocation/export helper 與 `af_hook_trial.py`，準備先由現行 EP82 raw bulk 取得 64 筆 H/L。20:30 第一個唯讀相機命令回 NO_DEVICE，沒有安裝 hook。恢復稽核發現 loader journal 依設計只覆蓋卡片 section，不會覆蓋執行期寫入的 AF 接點與 echo；已於 9/28 改為探針自帶 power-off 還原物件（見上）。暖開機保留 cave 卻重建 heap 的風險仍未關閉。

接續交付依序是：有限合成實收 → 真資料單 source → 多 source → 同 session 持續小批次／owner 回收 → CINE 錄影負載與自動分析。共同時鐘、bank／owner 設計與 CINE lifecycle 逆向可以並行；有限合成只是第一道驗收，不能停在逐批重裝／重開機的工作流。

**精確現況：** camera binding 仍呼叫 `af_ep83_camera_make_synthetic`，舊獨立 host session 要求 `SYNT`；sender result、camera private、camera control、host session、LibusbOwner 五層都是 single-use。尚無 EP83 真實資料實收／持續串流證據。現行 shell worker 自有 pool，不可沿用 highrate 的 `C3757A7C` legacy pool 假設；guarded loader hash／staging 生命周期亦需更新整合。新的 fpshd EP83 consumer 只是已測 host 候選，相機 sender／native PTP 排他使用未接合；不能另開 LibusbOwner 雙方 claim。保持原廠 AF 不等待 USB。

**既有相機證據：** [13:36 CINE 半按基線](notes/FP_CINE_BASELINE_2026-09-27.md) 完成一次 S1ON／S1OFF、六筆完整觀測與一次期限 partial；釋放後 shutter=0、設定一致、通訊異常=0。full-time byte=1，face 無有效結果、AAT tracking=0 且 backend/model/publication=0。這是 shell 原生取得／釋放基線，不是 EP83、錄影 CAF、光學合焦或幾何／DFD 驗收。CINE 主體來源與 AAT lifecycle 清單保留；不切 STILL、不靠重複半按啟用 AAT。

## 以下為較早時間點的交接紀錄

下文保留當時指示、產物與實測來源。出現「最新／當前／接續」皆指原段落日期，不能覆蓋上方 P0 順序；舊授權不擴張為未知位址／資源的 ownership 證明，舊 pool 值也不是目前配置。現在狀態與下一步以四份最新入口為準。

2026-09-27 使用者最新限定：**只做 CINE 錄影時的連續對焦；相機保留 CINE，不切 STILL。幾何方向運算共用於 face 與 AAT。** 已授權由代理操作半按／放開；沒有要求啟動錄影。13:11 基線固定 storage guard=1、CinemaMode=1，尚未送設定 setter 或 S1。已做的 STILL Tracking runner 僅留離線測試，不執行、不放寬 guard。CINE 有獨立 FullTimeAfSupport／MV_AlwaysAFSetting 路徑，FocusMode=0 不能當成影片持續 AF 關閉；下一步核對 CINE applied continuous-AF、AAT 入口與主體來源。**CINE 待機觀測與實際錄影驗收分開記錄；錄影是交付目標，不再延到最後才考慮。** 現有幾何核心的「鏡頭移動時清除趨勢」仍是錄影 CAF 的實際限制，須驗證採樣排程或呼吸補償，不能宣稱已能持續估方向。

2026-09-27 AAT 啟動條件已另行核對：[觸發／選定目標／幾何錨點](notes/research/FP_AAT_ACTIVATION_2026-09-27.md)。官方原廠 Tracking 流程是 STILL AF-C、選定目標後半按，點螢幕不是唯一條件。Backend 初始化讀 applied AF ROI，不直接讀 tap；尚未證明自動 face→AAT 交接。下一個 AAT baseline 先走真實模式／START／SetTarget／Run／停止流程，不能把下方 tracking=0 的觀測當 AAT 失敗案例。此項為離線＋官方文件核對，未操作相機。

2026-09-27 12:53 後續已完成 [辨識來源與顯示路徑診斷](notes/evidence/capture-native-preflight-20260927-124113.md)：同一 daemon 的舊 USB handle 經確認後重新連線，沒有啟停 daemon。固定資料證明 runtime face/eye=1、tracking=0；約 2.388 秒 8 次觀測的 raw face count／parsed face valid 全為 0。SysStatus／observer／renderer 三副本吻合；殘留 eye 6×6 不可當有效主體，AAT 尚未啟用。使用者已更正螢幕是否有框難以判斷，不將 UI 框當真值。新增 `af_native_preflight.py --subject-path --subject-samples 8` 固定唯讀診斷，40 項相關離線測試通過；沒有直接 RAM 寫入、設定變更、hook 或鏡頭命令。原廠 no-arg handler 可能更新內部 cache，輸出已明示寫入統計範圍。下方全零／相機使用中的說明是較早快照。

2026-09-27 USB shell 已接上並完成 [原生唯讀 preflight](notes/evidence/capture-native-preflight-20260927-121028.md)：四接點／12 guards、版本、echo、capture 與設定核對完成，取得 stack sentinel 基線；沒有 RAM 注入、hook 安裝或鏡頭動作。實測 worker pool=`45037980`、舊 `C3757A7C=0`，host cave register 屬前一 boot。舊 AF collector 因 DMA／fixed scratch lease 不相容已設為 live 拒絕，仍可離線 inspect/decode/mock；[修正說明](notes/research/FP_AF_COLLECTOR_WORKER_POOL_GUARD_2026-09-27.md)。當前 face/AAT 主體資料為零，需啟用來源與主體入鏡後再讀。完整 autofocus 離線回歸 173 tests 全過；不要把下方 9/16 或早一輪的 live 操作 recipe 當作可直接安裝的現行流程。

2026-09-27 後續離線整合：[合焦配對與 raw observer 交接](notes/geometry/OFFLINE_INTEGRATION.md)。已實作同輪 AF result／final drive end／新鮮 subject 的 shadow 配對、配對→幾何回放、四個原廠接點的純 ARM finite recorder 及 raw 解碼；ROM 接點已核對。完整測試与 ARM 模擬結果見 [VALIDATION](notes/geometry/VALIDATION.md)。配對候選不自動代表光學合焦；四來源尚無可信共用時間／身份，不能直接餵進幾何。**相機仍在使用；只做離線工作，下一個實機環境核對前停下，沒有 installer／寫卡／USB 操作。** 下文早一階段的「尚無 hook」指當時實作狀態，目前有離線組語候選，仍沒有已裝機 hook。

2026-09-27 **已開始離線實作**：[機內幾何 C 核心](notes/geometry/README.md)完成首次合焦基準、接近／遠離／靜止方向器、失效管理、JSONL 重播及 ARM object 建置。驗證結果見 [VALIDATION](notes/geometry/VALIDATION.md)；實機來源 adapter、hook 與光學效果尚未驗證。最新限制：**相機正在使用，不連線或操作相機**。
[輸入稽核](notes/geometry/NATIVE_INPUT_AUDIT.md)發現 AFF1 face 實為 AAT 結果、face ID offset 錯位、aat 矩形解碼型別／起點錯誤。**同日後續已修正 JSON v7 解碼**，保留來源 raw bytes，舊 binary／captures 不改；新增完整 native subject bytes decoder。不要把舊 snapshot 補全 flags 當可信幾何輸入。[合焦事件稽核](notes/geometry/NATIVE_CONFIRMATION_AUDIT.md)進一步區分 AF 成功結果、最後鏡頭移動完成與光學穩定。

2026-09-27 最新規劃：先看 [跨機型重審後的機內開發階段](notes/FP_AF_FIRMWARE_ROADMAP_2026-09-27.md)，歷史成果見 [跨專案進度盤點](notes/FP_AF_DEVELOPMENT_STATUS_2026-09-27.md)。
本輪重查 fp／Sony／Nikon 原始資料後，PDAF 仍未取得 fp 可用資料源，不列為主線前提。
Z CAM 僅作可讀 CDAF 與失敗機制對照，不作連續 AF 性能範本；Panasonic DFD 是方法參考，但本地 AF 核心仍未解。
新版 BMCC 全片幅 Cinema Camera 6K 已有 PDAF，移出無 PDAF 對照組。
使用者已確認現在可以修改韌體；最新主線是 **先由原廠 CDAF 合焦一次建立錨點，機內 face／AAT 幾何判接近／遠離，DFD 若成立再估離焦與位移，原廠 CDAF 確認**。
幾何沿用其他專案經驗，列 M2-G 主線，不再放到 M4 之後；首版改善合焦後追焦，首次合焦與失效重取得另驗。[最新融合分工](notes/research/FP_GEOMETRY_DFD_FUSION_2026-09-27.md)
**電腦參與即時 AF 運算與控制的 host AF Assist 暫時擱置**。
**機內 hook 擷取 AF／AAT 資料 → 緩衝 → EP83 快速傳回電腦**保留為開發研究與驗證路線；
電腦可做離線分析、校準及 A/B，正常 AF 控制與幾何運算留在韌體內。
這項分工與新規劃 M0–M5 取代下文以外部 AF 閉環為交付目標的歷史優先序。
本檔下文保留 9/16 的交接快照；較晚原始碼已有 camera／control／guarded-loader 候選，
但現行維護 loader 更新已令 guarded-loader 建置拒絕，目錄搬移也留下 libusb 預設路徑問題。
下文 386/386 為歷史成績，不能代替目前建置檢查；尚未完成 AF／EP83 實機驗收。
上述 guarded-loader／libusb 問題是 EP83 觀測工具的待辦，與機內 DFD／AAT 模型及決策接點分開驗收。

更新：2026-09-16。新任務「接手 fp 自動對焦優化」接手舊任務
「逆向 Sony α7 III 韌體」（`01a068f6-1496-74c0-ae81-707b9dcac8a3`）。
這份是進度導航；原始實測資料、失敗結果與完整研究筆記仍是證據。

## 9/16 歷史目標與指示（優先序已由上方 9/27 決定取代）

完成 SIGMA fp Ver.5.02 第一個可試用的 AF 輔助版本：非錄影 Live View、單一 ROI、
受限對焦搜尋、完成／停止與還原流程、可明確選用原廠 AF、操作說明及實機驗收。
目前版本 **0.1.0-pre1，完整 AF 流程未驗收，尚無快於原廠 AF 的測量**。

從舊任務最後一份紀錄核對的使用者指示（台北時間）：

- 06:12：「繼續做直到第一個版本出來為止」。
- 06:18：同意借 echo `C0BAC2F8`、RAM `C072F700..C072F9FF`，非錄影小位移、
  完成／停止、讀回驗證和結束還原；當次範圍不改韌體或 SD 卡。
- 07:37：同意暫換電腦端 USB 診斷程式，先做唯讀驗證。
- 08:11：「高速取樣你可能需要hook」。
- 08:44：「有些問題為什麼不看fp的源代碼就好？」——優先查現有反編譯及 ARM。
- 08:53：「有需要你可以優化usb shell」。USB shell 的必要實作與離線測試已在續作範圍內；
  舊筆記中再次要求先批准離線實作的文字不能蓋過這項指示。
- 本次接手後最新指示：「我覺得心力應該放在高速通道那邊，ptp就是輪詢得快不了」。
  **最新優先序：producer hook → 有限緩衝 → EP83 批次傳送。** 不再先做 native-owner routing 改造。

新的具體相機安裝／記憶體範圍仍應依實際方案核對；上述 USB 優化指示不等於批准任何
未知位址覆寫、刷機或刪改卡片。接手初期保持離線；後續經同意完成兩項限定 RAM 唯讀檢查，
沒有相機 RAM 寫入、改 daemon 或鏡頭動作。

## 工作位置

- 現有工作副本：本目錄 `/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/`。
- 專案歸檔：`/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/`。
- USB shell 維護程式：`/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/`。
- 通用相機證據：`research/autofocus/`、`research/interfaces/`；原始反編譯：`out/decomp/full/`。

接手時 `diff -qr` 核對：兩份 AF 目錄的共通檔案皆相同；工作副本另外有
`CONTROL_AUDIT.md`、`AF_FRESHNESS_AUDIT.md`、`handoff/` 與以下兩份最新筆記。
`codex/` 和研究總根目錄沒有 Git；`fpSup/` 有 Git，當時有其他 lossless／OpenGate 的未提交工作。
避免覆寫或提交那些無關變動，也不要盲目整棵同步 `handoff/`。

## 已證實到哪裡

- 有可運行的離線 UI、受限 H 搜尋控制器、native getter／move／abort bridge、記錄與還原邏輯。
- 既有實測完成 20-pulse 位移及 native 完成／停止流程；固定相機端 H/L copy 與動作前取消通過。
- 最後一次整合只完成四次受限小步，因重複 USB 短回覆而人工取消。結果為 fault；
  RAM／echo／設定已核對還原，最後 cached position 10807，起點 10707。
  這是當時紀錄，**不是現在的相機位置或狀態**。
- 之後補上傳輸異常鎖：即使重讀成功，也禁止該 Transport 的新位移及新 S1ON；
  process 重啟不構成恢復證据。`HARDWARE_MOTION_VERIFIED` 仍為 `False`。
- 本次接手重跑主測試 **308/308**、diagnostics **4/4**。主測試初次在 sandbox 被擋的
  17 個錯誤全是 localhost socket bind；允許本機 loopback 後全數通過。沒有 USB I/O。
- `research/autofocus/` 的離線研究工具測試也由平行稽核重跑，**129/129** 通過。

主測試：`/usr/bin/python3 -B -m unittest discover -s . -p 'test_*.py' -v`
（在本目錄）。診斷測試：在 `diagnostics/` 執行
`/usr/bin/python3 -B -m unittest -v test_diagnostic_v2.py test_diagnostic_build.py`。

## 9/16 歷史卡點與當時下一步

### 當時結論：未達可上機 AF 測試版

使用者要求「繼續，直到第一個測試版產出」。本輪已完成限定 live read，並實際產生
`highrate/artifacts/offline-test-a0-20260916/`（9 files SHA256SUMS 全通過），**只可離線測試**。
另有 `highrate/replay_batch.py` 與 `highrate/artifacts/ep83-boot-review-20260916.json`。
不要將這些產物改稱 AF beta 或宣稱已量到傳輸速度。
最終 root unittest discover **386/386 通過**（5.662 s，已允许本機 loopback）；
其中預期的 CLI 缺參數拒絕訊息來自單元測試，不是回歸失敗。全部測試都沒有相機／USB I/O。

最小下一路徑已收斂到 **冷啟動／未接 USB 的 EP83 isolation 候選**：
native sender `C01E5880: 4DF0E92D→47702000`，再 default tuple `C07E2800: 2→1`；
不在當前 session 熱改 ctx3。仍需完成 single-worker adapter 與 hook lifecycle。
新發現的固定卡點：mode-1 `C01E7780` completion 可能重寫／重新 Start bulk OUT EP01，
所以兩個 patch 本身不足以修好 ownership。下一代理應針對這個路徑解決，勿再無界尋找 mutex。

最新使用者回覆「繼續」緊接在明確詢問「備份並更新測試卡 AutoRun/VSHL、加入新的 RAM
修補、先完成離線驗證、由使用者冷啟動、不刷韌體、第一輪不移動鏡頭」之後，因此已同意
**這條具體測試卡／冷啟動路線**。不得再次把這份同意記為未回答；也不等於未知寫入範圍、
任意 firmware flash、拍攝或 AF motion 的批准。實際目標和技術可部署性仍須核對。
第一輪改為 synthetic finite EP83 batch，**不安裝 AF producer hook**；先驗證高速收發。
候選 pool 仍以已讀 `44F6FE00` 為基準，範圍／配置改變就停止。
本輪仍沒有相機寫入、daemon 切換、卡片操作、鏡頭動作或拍攝；`/Volumes` 沒有測試卡掛載。

### 當時接續實作紀錄

- `highrate/af_ep83_wait.c/.h`：真正的單次 RTOS flag 等待與 ARM fixed callbacks，8/8 mock
  tests。避開 `C01E7780`／End／reset／EP01 rearm；仍需 ownership 與 exact receipt。
- `highrate/ep83_host_session.py`：一次 trigger、EP83 batch、EP82 AFT1 terminal，12/12 tests。
- `highrate/ep83_libusb_owner.py`：實際 ctypes/libusb binding，9/9 tests；只在明確 lease
  才開裝置，唯一 VID/PID target、合作 lock、拒絕既有 daemon socket、不 detach/reset/drain/retry。
  EP82 的實際 USB buffer 至少 MPS，即使 protocol terminal 只有 64 bytes。尚未 live 使用。
- `highrate/af_ep83_memory.c/.h`：唯讀 CP15／實際 MMU table／pool allocation guard，6/6
  tests；CPU `0x4...` 由原廠 NonCacheBuf 配置，檢查實際 noncached mapping 才允許使用；
  不再假設要加 `0x40000000` 讀另一個 alias。完整 git label 位於 `C0725F94`。
- agents 正在整合 `af_ep83_camera.c/.h` 與 `build_ep83_camera.py`；config 的 runtime
  owner/mapping/nonce fields 預設零，不能把填 cookie 當成 owner 或部署證據。
- root 正處理 control entry 和冷啟動裝載。舊 worker 不能與 native usbTask 宣稱 single-owner；
  第一個 synthetic trial 可用極小 native mode-5 CMD4 adapter（不復活整套 SHL/native draft），
  但此入口／loader 仍未完成、不可安裝。

**先完成高速批次路徑，入口為 [highrate/README.md](highrate/README.md)。**
已新增固定 producer-return recorder、離線 builder、AFB1 batch 格式／decoder 與實際 ARM bytes
的 instruction-model 測試。取樣上限 256 筆，每筆 128 bytes；含 framing 總計 32,896 bytes。
滿載後不覆寫，但不代表 hook 已拆除。尚無 installer／實機 EP83 byte delivery／速度測量。
本次新增取樣／格式／veneer 19 項、EP83 接收 25 項、C sender 13 項、唯讀 probe 5 項，
加上既有 snapshot／bridge 回歸 30 項，合計 92/92。`highrate/README.md` 列有重跑命令；
單元測試沒有相機或 USB I/O，live probe 原始紀錄另存。
recorder 已補 full==0 guard，現為 724 bytes；sender core 為 2,024 bytes，只有 ARM core，
還沒有真實 firmware callbacks／task entry／installer。Start／Wait 失敗保留 DMA，不自動 End／重送。
builder 現支援顯式 near veneer；候選 pool layout 見
[AF_HIGHRATE_MEMORY_PLAN](notes/AF_HIGHRATE_MEMORY_PLAN_2026-09-16.md)，未取得 lease。

**優先讀 [EP83_SENDER_ABI](notes/EP83_SENDER_ABI_2026-09-16.md) 的新更正：**
IN Wait 應為 `C01E56F1`；ctx3 預設 mode-2/interrupt 不會被 descriptor patch 改掉；
native PTP event sender `C01E91D0→C01E5880` 也會改同一 TRB。
`C31E3AC4` 只是無鎖 flag，不能拿來完成 ownership。後續獲准的 live read 已確認
ctx3=`{2,1,3,0}`，pool=`0x44F6FE00`；沒有讀 controller MMIO，也沒有取得新 pool lease。
不要直接改 mode=1（原 event selector 會找不到 mode-2 IN）。
這兩項是固定 adapter 的真實前置工程，不是再加 pacing 或重試可以解決。
原始逐筆紀錄為 `highrate/runtime-read-20260916-a.jsonl`：STATUS 的 seq=11845，
隨後 native version 與固定兩項 mem get 成功，零相機寫入／零鏡頭命令／零重送。
型號／版本／完整 build hash 均符合預期；pool 指標穩定性、owner、映射與可部署性仍未驗收。

已抓到兩筆與 FPSH sequence 對應的 PTP `SessionNotOpen`；原廠 usbTask 和自訂 worker
可達同一 TRB／完成處理／重新 arm 路徑。這支持結構性競爭問題，尚未證明每次 timeout 的動態成因。
控制通道的異常鎖不能解除；改用 EP83 不自動修復啟停控制的競爭問題。

1. 高速取樣契約：[AF_HIGHRATE_RECORDER_CONTRACT](notes/AF_HIGHRATE_RECORDER_CONTRACT_2026-09-16.md)。
   producer 完成後有界記錄；record 包含 H/L、native-L cached position、AF-manager position
   與 gain/context。cached position 不是曝光同步值；輸出硬標為不可直接控制／不可 DFD。
   `C022C858` 原字 `EB00485C` 已從本機 ROM 核對；掛點／buffer 尚未部署。
2. 目前 daemon 無 EP83 reader。沿用 logical 3 / physical 7 的端點契約做一次完整 batch：
   先處理 DMA lease、host packet-size／deadline／CRC，再接 task-context sender。
   舊 probe 的 100/100 只是 Start 接受，不是資料已傳到主機。不可直接使用舊 EP84 範本。
3. 生命周期查到 [HOOK_OWNER_AUDIT](notes/HOOK_OWNER_AUDIT_2026-09-16.md)：
   未找到涵蓋所有重新註冊的 AF mutex；候選是同 CPU 短 critical section 內 ready-check +
   try-commit。仍缺同 CPU 執行域、critical-section 上限及 helper 失敗分支驗證。
   不要重開整個 firmware 的無界 owner 搜尋，也不要把一次 ready 當作安全卸載證明。
4. 通訊及取樣達成可驗收條件後，再完成整輪 AF 實測、取消／還原及與原廠 AF 的實測比較。

`transport_native/` 是本次轉向前留下的未整合、未測試草稿，已標明暫停；不要把它當成修復完成。
[USB_ROUTING_REPAIR_AUDIT](notes/USB_ROUTING_REPAIR_AUDIT_2026-09-16.md) 保留供控制通道後續使用。

## 按需讀取

先讀本檔與 [README](README.md)。實測看 [VALIDATION](notes/VALIDATION_2026-09-16.md)；
傳輸看 [TRANSPORT_AUDIT](notes/TRANSPORT_AUDIT_2026-09-16.md) 及上述 repair note；
hook 才讀 ABI／lifecycle／owner 三份專題。避免把完整舊對話、所有 captures 或整棵反編譯
一次載入。沿用 `sigma-fp-af-research`、`fp-usb-shell` 的工具路徑與已核對的限制。
