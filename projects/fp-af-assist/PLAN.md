# fp CINE 連續自動對焦：完整開發計畫

更新：2026-09-27。目標：SIGMA fp Ver.5.02 的**影片連續 AF**。本頁是後續工作及驗收入口；歷史研究、實作與失敗紀錄保留，不以舊計畫的未錄影／STILL 限制改變目前產品範圍。

**產品主線：原廠 CDAF 首次合焦 → 同主體光學錨點 → 機內 face／AAT 幾何判斷接近／遠離 → 輔助原廠 CDAF 持續追焦 → 失效後重新取得。** AAT 改善可以獨立交付；DFD 通過獨立驗收後才加入離焦量／位移資訊。估計、判斷與控制在機內，正常使用不依賴電腦或 USB。

**開發第一優先 P0：先完成多接點 hook＋USB 連續資料平台，降低設定、擷取、回傳與分析成本。** 平台目標是將原廠 AF 資料持續以受限小批次送到電腦；這是研究基礎設施，正常產品仍不依賴 USB。平台與算法驗收分開：[平台階段計畫](notes/AF_TELEMETRY_PLATFORM_PLAN_2026-09-27.md)、[事件／接點清單](notes/AF_STREAM_HOOK_CATALOG_2026-09-27.md)、[目前 transport 整合缺口](notes/AF_STREAM_TRANSPORT_GAP_2026-09-27.md)。

`[x]` 只表示該項列明的證據已完成；`[ ]` 表示仍待實作或驗收。離線通過、CINE 待機觀測、實際錄影成效分開記錄。不使用完成百分比或無依據的日期預估。

## 現況與證據邊界

- [x] 第一個 H/L hook 試驗流程、ARM allocation/export helper 與同 daemon EP83 consumer 已完成離線增量。首批可先用既有 EP82 raw bulk；目前 USB preflight 回 NO_DEVICE，沒有真實 hook 實收。[本輪實作／驗證與接續](notes/AF_FIRST_HOOK_CHANNEL_2026-09-27.md)
- [x] 關機還原改走維護中的正規機制：AF 接點以**內容為韌體原字的 4-byte 卡片區段**宣告，由 stage2 記進 journal、共用 loader 的單一回呼寫回；探針只**驗證**（第一個寫入前一次、武裝前一次），不註冊、不占用 power-off 清單格。自帶物件已退役——韌體自己就占了普通清單 10 格中的 8 格。抽電池／當機仍無 callback。[規範發現與實作](notes/AF_LOADER_CONVENTION_FINDING_2026-09-28.md)
- [x] recorder 已加入分級（off/count/record）與重入偵測（`in_body`＋latched `overlaps`），資料路徑不再輪詢：一次觀測視窗、一次 bulk 匯出已提交前綴。capture schema 升為 2；7 個突變對照全部被抓。[實作與邊界](notes/AF_HOOK_STAGED_NOPOLL_2026-09-28.md)
- [x] 已核對舊「全能控制台」時期同接點的 stage1 子系統，取其分級與重入設計，不取其 mailbox 輪詢路徑與固定 cave 位址。[核對紀錄](notes/AF_PRIOR_HOOK_REVIEW_2026-09-28.md)
- [x] **cache 同步已由單核證據排除。** `C000EABC` 確實是本地版 `ICIALLU`，但全映像**沒有任何 MPIDR 讀取、沒有 SCU/PERIPHBASE 存取、沒有廣播 ICIALLUIS**，而且原廠自己的 D-cache 維護用 **set/way**——那在架構上不會廣播，只有單核才成立。執行這份映像的 ARM 核心只有一顆，所以從 shell task 發布的程式，AF observer 取指時看得到。發布順序（先 D 後 I）仍必要。[證據](notes/AF_CACHE_COHERENCY_2026-09-28.md)
- [x] 已分清兩條 USB 通道：shell 的 EP01/EP82 回覆路徑已完善並上機量過（相機→主機 73 MB/s、回覆上限 16 MB），EP83 串流相機端未接通、執行中 daemon 也沒有 host consumer。[核對紀錄](notes/AF_CHANNEL_STATE_VERIFY_2026-09-28.md)
- [x] 已完成原廠 CDAF、face／eye／AAT、鏡頭位置域及跨機型研究盤點；目前優先序以本頁為準，算法方向參照 [機內階段規劃](notes/FP_AF_FIRMWARE_ROADMAP_2026-09-27.md)。[歷史進度](notes/FP_AF_DEVELOPMENT_STATUS_2026-09-27.md)
- [x] 已有共用 FACE／AAT 幾何 C 核心、光學確認事件的 shadow join、JSONL 重播、原始 subject decoder；固定 AAT 框不自動取得尺度權限，換主體／尺度／來源會使錨點失效。[幾何輸入稽核](notes/research/FP_CINE_GEOMETRY_INPUTS_2026-09-27.md)
- [x] 四個 native 接點的 ROM／ABI metadata、有限 raw observer 與 ARM 模擬已完成離線驗證。native callee 在模擬中是 stub；沒有因此完成 installer 或實機觀測驗收。[離線交接](notes/geometry/OFFLINE_INTEGRATION.md)、[驗證紀錄](notes/geometry/VALIDATION.md)
- [x] 已取得當次原生唯讀 preflight、接點字組與 task stack 基線；發現目前 worker 獨立 pool 與舊 collector 不相容，舊 live 安裝已被阻擋。這不等於新 observer 的記憶體所有權、最壞 stack 餘量或安裝生命週期已解。[preflight 實測說明](notes/evidence/capture-native-preflight-20260927-121028.md)
- [x] **13:36 CINE 原廠半按基線完成：**一次 S1ON／S1OFF，host 派發間隔 2.010014 s，6 筆完整 held 觀測；另 1 筆 partial 因釋放期限結束，非傳輸失敗。釋放後 shutter=0、設定前後一致、transport anomaly=0。[分析](../../research/autofocus/captures/cine-af/20260927-cine-baseline/analysis.json)、[原始按／放紀錄](../../research/autofocus/captures/cine-af/20260927-cine-baseline/acquisition.jsonl)
- [x] 同輪辨識出的限制：full-time/preAF byte=1，但不證明馬達持續動作；face 已啟用但 group 0 parsed-invalid、完整 held 觀測的 raw face count=0；runtime tracking=0，AAT backend／model／publication=0。AAT 的零資料對應未啟動狀態，**不能當作已啟動 AAT 的失敗樣本**。menu area=2 與 AF copy area=4 屬不同域，不互相替代。[CINE 實測結論](notes/FP_CINE_BASELINE_2026-09-27.md)
- [ ] 尚未證明新機內幾何或 AAT 改動改善影片追焦；上述資料明列 `geometry_eligible=false`、`optical_focus_confirmed=false`、`recorded_video_caf_validated=false`。S1OFF 回到原廠生命週期，不保證所有 full-time AF 馬達活動停止。

## 立即下一步：先交付可持續觀測的開發平台

**關機還原已閉合到普通／強制關機的程度，下一步是暖開機殘留與第一批 H/L 實收。** `af_hook_trial.py` 不再無條件封閉：它在第一個寫入前唯讀核對兩張 power-off 表有空格，註冊自己的還原物件，並在武裝前重驗；任一條件不成立就不武裝，也沒有略過選項。抽電池／當機沒有 callback，因此 veneer 的 boot-stamp 守衛仍待補。EP82 單 source 試驗可與下列 EP83 P0-A 並行，不能據此勾選 EP83 實收或持續 session 完成。

1. **P0-A：有限合成資料實收。** 相機端與主機端已完成離線實作：[EP83 T0](notes/EP83_T0_2026-09-29.md) 確認 daemon 要的 terminal 就是 worker 的一般回覆 frame，因此 worker 保有 EP01／EP82、sender 只碰 EP83（physical 7、logical 3、TRB `C31E3270`），**不啟用 CMD4 adapter**。332-byte `ep83_send.S` 與主機 runner 各有 16／11 tests、6 個突變全被抓。尚缺：換上有 EP83 的 daemon、接上配置器、證明原廠 PTP event sender 不爭用同一 TRB。 閉合現行 loader／常駐記憶體 lease、相機與 host 單一 owner，先驗一批 bytes、nonce／CRC、EP83 completion 與 EP82 terminal。現在 camera binding 仍產生 synthetic，尚無 EP83 實收證據。
2. **P0-B：真實單 source。** 接一個已核對 producer，以有限 batch 驗 payload、原函式效果、hook 成本與清理；來源／context 標籤和時間未知仍保留。以此分離來源問題與 transport 問題。
3. **P0-C：多 source。** 接 AF／lens／face／AAT／H/L，分 schema、source sequence 與缺失；補 request／decision／實際 ROI／target lifecycle 等因果事件。共同時鐘未通過前只提供分來源有序資料。
4. **P0-D：一次開始的受限 session。** 重設五層 single-use 為有界逐批 ownership 協定，持續送小批次；驗上一批 EP83 及 EP82 terminal 都完成才回收、有限 credits、stop／fault／主機慢讀／退出。不能以 host while-loop 重呼叫 one-shot 取代。
5. **P0-E：錄影負載及自動分析。** 分 CINE 待機／實際錄影，驗原廠 AF 與畫面不退步；自動保存 binary／manifest、來源覆蓋／丟樣／關聯及可重播報告，再用同一平台支持 AAT、幾何與 DFD。

這是上線驗收順序；時鐘、bank／owner 協定、CINE lifecycle 逆向及離線反例可提前並行。既有六筆 CINE held 觀測作基線，避免以反覆半按或逐筆 RAM 輪詢維持日常資料工作流。各階段具體交付及退出條件見 [平台計畫](notes/AF_TELEMETRY_PLATFORM_PLAN_2026-09-27.md)。

## P0／M0：多接點 hook＋USB 持續資料平台

定位：**目前開發第一優先**，建立可反覆使用的資料擷取、離線研究、校準及 A/B 平台；正常 AF 閉環仍在機內。M1 的動態來源／時序與後續算法實驗使用這條資料鏈，有限記錄及 completed-history 保留作比對。

當前 camera binding／host 仍是 synthetic-only；sender result、camera private、camera control、host session、host owner 五層 single-use 尚未改成連續批次。舊 `C3757A7C` pool、guarded-loader hash 與現行 worker 配置不相容；專用 libusb owner 又拒絕已有 fpshd socket，不能雙方同時 claim。詳見 [transport gap](notes/AF_STREAM_TRANSPORT_GAP_2026-09-27.md)。

- [x] 已有 recorder、封包／CRC／nonce、sender／receiver 及 camera／control／memory／host owner 候選與離線測試；尚未完成相機實收及全流程 ownership 驗收。
- [ ] 明確選擇 AF／AAT 原始資料格式、來源種類、generation、時間及分批策略；舊 128-byte record 不代表新資料需求全部具備。
- [ ] 修正／核對維護中 loader 與 libusb 路徑整合；來源 hash 拒絕必須查明差異，不能只換 hash 繞過。
- [ ] 閉合原廠 PTP／event producer、mode 切換、EP83／TRB、DMA lease、completion、取消及 teardown 的**單一 owner**；host 單 client 或一次 preflight 讀值不能消除相機內競爭。
- [ ] 證明 hook 不送 USB；由合適 task 傳有限批次，端點失敗不阻塞 AF，資源只在 producer／DMA 確定退出後釋放。
- [ ] 先驗有限合成批次筆數、順序、CRC、重複／遺失及收尾，再驗真資料與原廠事件共存；量實際吞吐、延遲與觀測開／關干擾。

- [ ] P0-A 交付有限合成 batch 的真實 EP83／EP82 收尾證據；`camera_make_synthetic` 與 `SYNT` 限制尚未解除。
- [ ] P0-B／C 接真實單來源再多來源，保持 128-byte H/L 與 256-byte observer 的 schema／decoder 區別，補齊 T0 因果事件及共同時鐘；缺失來源不可靜默跳過。
- [ ] P0-D 完成五層逐批狀態與 bank 交接、部分已提交前綴封批、session/batch/source 身分、有限 credits、backpressure、stop/fault 及 producer／DMA owner 回收。
- [ ] P0-E 驗 CINE 錄影負載、控制通道公平性、host 退出／拔線下原廠進展；自動產出原始檔、session manifest、來源／丟樣／成本與可重播分析。

**目前 blocker：**ownership、現行 loader／memory lifecycle、真實實收與連續回收契約尚未閉合，不能宣稱已有串流或已達高速。不能用短回覆重試／ACK 恢復來推定未知命令沒有執行。

參考：[高頻資料方案](highrate/README.md)、[EP83 sender ABI](notes/EP83_SENDER_ABI_2026-09-16.md)、[記憶體契約](notes/EP83_MEMORY_MAPPING_2026-09-16.md)、[USB ownership 稽核](notes/USB_ROUTING_REPAIR_AUDIT_2026-09-16.md)、[hook owner](notes/HOOK_OWNER_AUDIT_2026-09-16.md)。

## P1／M1：CINE 資料來源、時間與觀測生命週期

依賴：P0/M0 的真資料來源與 ownership 增量、當次機身／韌體身份及原生 CINE 路徑。來源契約／時鐘逆向與 P0 並行；跨來源動態結論要等相應 common-clock／generation 驗收。

- [ ] 定義完整 trial context：鏡頭身份、光圈、焦段、影像模式／readout／crop、曝光／gain、錄影狀態、ROI 與 detector 設定；保存原始值及解釋版本。
- [ ] 對齊 CINE 的 FullTimeAfSupport、HalfReleaseAFSupport、原廠 AF 排程與錄影啟停；CINE FocusMode=0 不當作「影片無連續 AF」，不強設 STILL AF-C=1。
- [ ] 對每個來源保存 raw bytes、producer／完成接點、序號、時間來源、有效／失效原因；區分新發布、重讀快取、未初始化及完整／partial 記錄。
- [ ] 建立曝光／統計 generation、採用 ROI generation、subject generation、AF episode、lens drive generation 的關聯；來源獨立 counter 不能冒充跨來源總順序。
- [ ] 實作共同時鐘與 wrap／race／age 契約。現 observer 不讀 timer；原生 getter 有遞迴重讀可能，不能直接塞進要求固定成本的 hook；未解時保持來源時間未知。
- [ ] 對齊 H/L、gain／readout、AF strategy、lens 位置與實際影像。completed-history 可做離線曲線，但不自動證明即時曝光同步；H/L 是頻帶統計，不是 PDAF 左右半像素。
- [ ] 依現 worker 配置建立合法常駐記憶體、單一 owner、producer quiescence、cache publication、安裝／解除與故障保留流程；禁止借用舊 pool 或未知 cave。
- [ ] 量四個 hook 的耗時分佈、最壞耗時、stack 使用、nested／busy loss、滿載行為及對原廠排程的影響；有限 buffer 滿後不覆寫，不在 hook 等待或送 USB。
- [ ] 驗證觀測開／關、來源未初始化、資料遺失、使用者改模式／設定、開始／停止錄影時的退出與還原。

**驗收：**每筆用於估計的資料可追溯來源、context、新鮮度及相互對齊；不足者明確拒絕。觀測成本有上限，原廠行為沒有可辨識退步。CINE 待機只能關閉部分資料缺口，錄影負載另驗。

參考：[CINE 啟動邊界](notes/research/FP_CINE_AAT_ACTIVATION_2026-09-27.md)、[統計新鮮度](notes/research/FP_AF_STATS_FRESHNESS_2026-09-16.md)、[native hook](notes/geometry/NATIVE_HOOK_PLAN.md)、[worker pool guard](notes/research/FP_AF_COLLECTOR_WORKER_POOL_GUARD_2026-09-27.md)、[stack 診斷](notes/research/FP_NATIVE_TASK_STACK_DIAGNOSTIC_2026-09-27.md)。

## P1／M1-S：face／AAT 啟動、身份、reseed 與尺度

依賴：M1 來源／context 契約及 P0 真資料通道；CINE 啟動／停止逆向與平台並行，動態結論須待原廠已啟動且能記錄的樣本。

- [ ] 查明 CINE face／eye enable、detector 發布、顯示框及 AF 採用框的關係；畫面框不直接當作 AF 正在使用該主體的證據。
- [ ] 從原廠 CINE 生命週期安排 AAT target 初始化、參照影像／ROI、通知、Run／GetResult、停止與重新啟動；確認 RecMgr、detector worker 與 callback 的所有權。
- [ ] 定義選主體及 face → AAT 的受控交接。Touch AF 的指定 ROI 取得不等於 AAT Tracking；debug handler 存在也不代表適合裸呼叫。
- [ ] 建立 target／context／scale generation；換人、失去後重抓、reseed、face／AAT 切換、readout／crop 或尺度定義改變時使舊錨點失效。
- [ ] 分開 face primary／detector tuple、AAT 原始 model、GetResult／publication、AF-input 及 AF 最終採用 ROI；座標轉換須使用已證實的有效影像寬度，不能猜 320 或沿用 host 1620。
- [ ] 逐來源驗證 normalized linear size。固定 64×64 publication、搜尋窗、半軸面積及 AF ROI 不直接作尺度；model 半軸含 normalizer／自適應效應，需獨立證明與主體投影的關係。
- [ ] 以固定主體、已知接近／遠離、橫移、轉頭、遮擋、同色背景、雙主體及失去後重抓區分真實尺度變化與算法調框；分 source 保存效度、拒絕原因與適用條件。

**驗收：**先證明 CINE 下來源確實初始化並持續更新，再證明身份與尺度可用。正尺寸、valid、quality 或「找到」旗標都不足以設定幾何權限；AAT 尺度未通過時，AAT 可先服務身份／ROI，不阻擋有可信 face 尺度的方向研究。

參考：[face／AAT 研究](notes/research/FACE_EYE_AF.md)、[AAT lifecycle](notes/research/FP_AAT_ACTIVATION_2026-09-27.md)、[CINE 啟動限制](notes/research/FP_CINE_AAT_ACTIVATION_2026-09-27.md)、[face display](notes/research/FP_FACE_DISPLAY_SOURCE_2026-09-27.md)、[face enable](notes/research/FP_FACE_ENABLE_STATE_2026-09-27.md)、[native 輸入](notes/geometry/NATIVE_INPUT_AUDIT.md)。

## P1／M1-F：原廠首次光學合焦與錨點

依賴：M1 時序／drive 關聯、M1-S 同主體新鮮尺度。

- [ ] 實作 native begin／cancel／AF-result／drive-begin／final-end adapter，確認成功／失敗、retry、backlash 中間停止及 no-op 的可達條件。
- [ ] 分開 native AF 接受結果、命令完成、真實 lens-settled、位置新鮮度及獨立光學品質；函式 return、event-set 成功、Hpeak 或 cached position 不能互相替代。
- [ ] 用同一 episode／drive 的成功與 final end，配對之後的新鮮同主體樣本；缺來源、亂序、丟失、過期、取消／故障一律阻擋，不能借上一輪事件。
- [ ] 將 shadow candidate 到 `fg_confirm` 的授權建立在實測條件上；不得把 join 的 candidate-ready 自動當作光學確認。
- [ ] 確認錨點儲存的尺度、時間、身份、context 與位置域，定義老化、使用者介入、主體／來源切換及失效後重新取得。
- [ ] 區分首次取得、已有錨點後追焦及失效重取得的資料集與成績；不以合焦後收益宣稱冷啟動問題已解。

**驗收：**原生事件與獨立影像品質一致；失敗／取消／不完整配對不建立或刷新錨點。其後仍由原廠 AF 保持鏡頭控制權。

參考：[native confirmation audit](notes/geometry/NATIVE_CONFIRMATION_AUDIT.md)、[離線 join 整合](notes/geometry/OFFLINE_INTEGRATION.md)、[位置域](notes/research/FOCUS_POSITION_DOMAIN.md)。

## P1／M2-G：共享幾何方向與移動中鏡頭問題

依賴：M1-S 可用尺度、M1-F 光學錨點；與 AAT 單項改善並行，不等待 DFD。

- [x] face／AAT 共用 `FgSample` 與倒數尺度趨勢；AAT 另需明示尺度驗證，motion authority 固定為 0；離線測試包含換代丟錨點、舊樣本拒絕及 lens moving 清趨勢。
- [ ] 把可信 native adapter 接到旁路 core，仍只記錄 direction／rate／reason／coverage；依機內時間與資料率重訂窗口及 age 門檻，舊 host 延遲不能沿用。
- [ ] 量方向錯誤、UNKNOWN 比例、靜止假動作、慢速啟動及反向延遲；以已知主體運動作真值，與光學前／後焦及鏡頭位置 sign 分開。
- [ ] 改善合成重播已顯示的反向遲滯；比較短窗、變點／反向確認與不確定時拒絕等有界方案，避免靠增加 UNKNOWN 隱藏錯判。
- [ ] **路徑 A：短暫穩定窗口。** 量原廠 CINE 連續 AF 中真實 settled 區段、更新率、方向覆蓋率及輸出延遲。現 core 在 moving 時清趨勢；若窗口不足，不以重讀快取或假設 stationary 湊樣本。
- [ ] **路徑 B：經校準的呼吸補償。** 固定主體量 scale 對實際 lens position 的關係，按鏡頭／焦段／readout／crop／移動方向／曝光時序分組；用留出動態序列驗證。若成立，新增明確的移動中尺度契約及測試，不能偽設 `FG_LENS_STATIONARY` 或繞過 `FJ_SETTLE_VALIDATED`。
- [ ] 量姿態、遮擋、防震／裁切、變焦及曝光改變的干擾；低效度時拒絕並由原廠流程重新確認。
- [ ] 幾何絕對估距／粗位置模型只作後續可選比較：須有當前主體與鏡頭校準、足夠跨度及跨場次留出驗證；模型只以光學確認更新，不能用自己的指令目標自訓練。

**驗收：**face 與已驗證的 AAT 分別交付錯向率、覆蓋率、靜止假動作及轉向延遲；moving-lens 路徑需有真實 CINE 可用率。主體接近不等於目前應將 native position 加或減；幾何方向不得直接變成馬達命令。

參考：[CINE 幾何契約與兩條路徑](notes/research/FP_CINE_GEOMETRY_INPUTS_2026-09-27.md)、[融合分工](notes/research/FP_GEOMETRY_DFD_FUSION_2026-09-27.md)、[核心驗證及已知錯向](notes/geometry/VALIDATION.md)、[核心程式](../../fpSup/focus/geometry/geometry.c)。

## P1／M2-A：AAT 追蹤與 AF 耦合改善

依賴：M1-S 已啟動且可重播的原廠 tracking baseline；不能從全零 inactive 快照推論原廠追蹤缺陷。

- [ ] 建立原廠 CINE 失敗案例集，先分類：錯誤接受目標／失去身份、背景污染、遮擋後恢復、框抖動造成不必要重驅、真實深度變化反應慢。
- [ ] 核對原廠已有的大小 normalizer、lost recovery、色彩模型 gate、低命中處理與 AF 採用品質條件。復刻缺少模組造成的問題不直接移植為原廠修補項。
- [ ] 每輪只選一個有實例的改動：可追蹤性／接受條件、模型更新／凍結與到期、失去後 reseed，或 AF 採用的持續性／重驅遲滯；保留原廠對照及拒絕原因。
- [ ] 同時驗反例：灰色但有紋理主體、短暫遮擋返回、真實沿光軸移動、face／eye 切入切出、多主體競爭及相似背景。
- [ ] 所有 hold／平滑／凍結有明確期限、重新取得條件與 generation；不以更久錯跟換取較穩定的框。
- [ ] 保存實際 AF 採用分支與 ROI，分開 tracker 改善與 AF 控制改善；AAT-only 可先交付，無需等待其尺度能支援幾何。

**驗收：**指定失敗可重現減少，錯跟時間、失鎖／重取時間、誤重驅／分鐘及真實深度變化反應不退步。「框更不動」不是成功標準。

參考：[AAT 原廠模型](notes/research/FACE_EYE_AF.md)、[機內修改接點](notes/research/FP_AF_FIRMWARE_INTERVENTION_MAP_2026-09-27.md)、[AAT 改善取捨](notes/FP_AF_FIRMWARE_ROADMAP_2026-09-27.md)。

## P2／M2-D：可選 DFD／離焦量支線

依賴：M1 統計／曝光／位置／ROI 對齊及獨立光學真值。可離線並行，結果未成立前不阻擋幾何＋CDAF／AAT。

- [ ] 先固定一個已具鏡頭資料的組合、光圈及 readout／曝光條件，優先比較既有 SIGMA 28mm Art 資料；其他鏡頭的距離表不當作可共用 DFD 校準。
- [ ] 比較原廠搜尋、已知位移下簡單 H 梯度、H/L 多頻帶、局部峰區間／曲線模型；優先利用原廠已有探測動作，不先新增大量可見 wobble。
- [ ] 驗證離焦量／峰區間、前後焦符號、信心、拒絕及適用條件；光學 defocus 和主體移動方向分開輸出，不直接相乘。
- [ ] 用獨立影像清晰度及局部 focus bracket 定義最佳點／可接受區間；分場次、主體與 trial 留出，不能以相鄰幀分割製造虛假泛化。
- [ ] 量相同覆蓋率下，相對簡單梯度是否提供額外資訊；區間同報涵蓋率與寬度，防止只擴大區間或大量拒絕過關。
- [ ] 若控制混淆因子後仍不能跨場景穩定勝過簡單基準，停止擴大該模型；保留結論並回到幾何＋CDAF／AAT。只有校準與留出光學驗證通過才稱已驗證 DFD。
- [ ] 通過後先機內旁路提案，再以獨立 A/B 加入位移／峰區間建議；保留低信心回原廠搜尋、CDAF 最終確認。

參考：[DFD 統計研究](notes/research/DFD_VIA_AF_STATS.md)、[方向診斷](notes/research/FP_AF_DIRECTION_DIAGNOSTICS_2026-09-16.md)、[距離／位置原理](notes/research/FOCUS_DISTANCE_PRINCIPLE.md)、[融合契約](notes/research/FP_GEOMETRY_DFD_FUSION_2026-09-27.md)。

## P1／M3：機內整合與原廠控制權

依賴：M1 完成；幾何版需要 M2-G，AAT-only 需要 M2-A，DFD 增量另外需要 M2-D。

- [ ] 選定最小原廠接點，先只讀／shadow，再由單一原廠 owner 接受有期限的建議；不讓多個模組同時直接下鏡頭命令。
- [ ] 明確分開未合焦、建立錨點、追蹤、短暫失效、失去目標及重新取得；每次決策記錄來源、信心、age、採用／拒絕理由。
- [ ] 優先改善方向、搜尋區間、重驅或近峰判斷中已量到的瓶頸；核對原廠已有 Fast／Slow／Near、峰內插、回驅與歷史預測，不把死碼當現成能力。
- [ ] 量 CINE 觀測、估計、決策的耗時與最壞 deadline、常駐記憶體、stack、丟樣及排程餘裕；超時或資料失效撤回建議，原廠流程可繼續。
- [ ] 依維護中的共用 loader／stage2／entry 與 journal 整合；ROM expected bytes、版本、配置、cache 發布與回滾均可核對。離線 object／模擬器地址不是可安裝產物。
- [ ] 實作啟用／停用、未知鏡頭／模式退回原廠、手動介入、設定改變、錄影啟停、錯誤與重開機處理；保留每項實驗可單獨關閉的比較方式。
- [ ] 驗證拔除 USB、關閉 host 工具時 AF 仍在機內正常工作；電腦即時估計／決策／控制路線維持擱置。

**驗收：**有限受控場景中能完成原廠首焦 → 錨點 → 機內輔助 → 原廠確認／重新取得，且符合已量測的錄影負載預算；沒有第二套互相競爭的鏡頭控制權。

參考：[介入接點](notes/research/FP_AF_FIRMWARE_INTERVENTION_MAP_2026-09-27.md)、[native focus control](notes/research/FP_NATIVE_FOCUS_CONTROL_2026-09-16.md)、[載入規範](../../fpSup/SUP_BUILD_RULES.md)。

## P1／M4：實際錄影 A/B 與畫面品質

依賴：有可關閉的機內候選、可信時間／影像／ROI 記錄及受控恢復。CINE 待機或一次半按成功不能代替本階段。

- [ ] 在看修改版成績前，凍結場景、trial 分組、光學成功標準、允許退步範圍、延遲／品質指標與樣本不足的判定；以完整 trial／場次留出。
- [ ] 分別比較原廠、AAT-only、幾何＋CDAF；DFD 通過後再比較 DFD＋CDAF 及完整融合。保持其餘 tracker／ROI／曝光條件一致，逐項歸因。
- [ ] **實際錄影中**測靜止、前後移動、慢速、快速、反向、橫移、轉頭、遮擋、多主體、低光／低紋理／高亮點及相似背景；保存原始影片與同步決策資料。
- [ ] 分開首次合焦、已有錨點追焦及失去後重取；報清晰度、失焦時間、對焦延遲、pumping／可見反轉、總行程、錯跟及非預期跳焦。
- [ ] 同報 UNKNOWN／拒絕、失敗案例、樣本量、不確定性與跨場次差異；不以提前停止、更多拒絕或挑成功素材宣稱加速。
- [ ] 驗錄影開始／停止、影像／裁切切換、手動介入、光圈／鏡頭變動及 USB 斷線；檢查畫面是否掉幀、卡頓、控制抖動或錄影流程受干擾。
- [ ] 先完成單一已宣告鏡頭／光圈／模式，再依證據擴展；距離表可作起點，不代表所有鏡頭光學校準與馬達 sign 相同。

**驗收：**最終影像品質與成功率不退步，且至少一項預先選定的追焦延遲、可見 pumping、錯跟、失焦時間或行程有跨場次可重現收益；同時符合錄影穩定性及主體反應要求。門檻需來自本機基線與使用目的，沒有既有證據便不捏造數字。

## P1／M5：可使用版本、恢復與交付

- [ ] 列明支援的 fp 韌體、鏡頭、光圈、焦段、CINE 模式／readout 與限制；未知組合採原廠流程。
- [ ] 發布包包含來源／ROM／產物 hash、配置版本、重播資料、測試報告、安裝與停用步驟，以及可核對的 loader journal／還原結果。
- [ ] 驗證安裝中斷、啟用失敗、未知 owner、滿載／丟資料、native fault、手動取消、USB 中斷與重開機；無法證明執行已退出時保留診斷資源，不假稱全部復原。
- [ ] 長時間實際錄影與反覆錄影啟停下量資源使用、熱／負載條件、畫面及 AF 穩定性；以支持條件記錄結果，不外推未測組合。
- [ ] 產品入口用使用者能理解的啟用／停用與適用條件；研究位址、raw flags、USB owner 等留在診斷資料。
- [ ] 完成不接電腦的實際使用驗收，再將實驗版升格為可使用版本；未通過項留在明確限制及後續清單。

## P3：跨機型參考與 PDAF 有界支線

- [x] fp、Sony A7III／A7C、Nikon 及其他 IMX410 類機型已重新分級證據；同系列 sensor 不等於同 variant、phase payload 或相同可達路徑。[PDAF 可行性重審](notes/research/CROSSCAM_PDAF_FEASIBILITY_2026-09-27.md)
- [ ] PDAF 只有出現能改變判決的具體新證據才續查：**fp phase pixels／payload → 可定位 → 鏡頭／機身校準 → 可達演算法與輸入路徑**。逐 gate 保存已證／未知／否定；無 fp 資料來源時不反覆搜尋假設的 enable bit，也不阻塞 CINE 幾何／CDAF。
- [ ] Sony phase ingress 與 DFE egress、Nikon 相關結構僅作證據對照；不能從他機 PDAF 成功推得 fp 可開啟。
- [ ] Blackmagic 全片幅 Cinema Camera 6K 新版新增 phase AF 是分類線索；不能將其當作無 PDAF 反例，也不能反推 fp 使用同一 sensor variant 或已有 payload。
- [ ] Panasonic／Leica 只在取得可讀核心或可驗證演算法證據時深化；加密 payload、符號或 API 名稱不等於已取得 DFD 實作。
- [ ] Z CAM 僅針對統計對齊、反轉後樣本丟棄、重搜／失敗／ROI 耦合等具體問題做程式對照；**不作連續 AF 性能標竿，不列照搬控制器目標**。

**停止規則：**每次外部研究先指定一個問題、最小新證據與輸出；若只能重述同 sensor／符號／通用 API，記錄未知並停止該輪，將重心放回 fp 的可量測主線。[非 PDAF 參考分類](notes/research/NON_PDAF_CAMERA_REFERENCE_2026-09-27.md)、[Z CAM 程式參考](../../zcam_e2f6/notes/ZCAM_AF_REFERENCE_2026-09-27.fp-af-assist.md)

## 目前會阻擋哪一步

| 未解條件 | 直接阻擋 | 不必等它的工作 |
|---|---|---|
| CINE face 無效、AAT 未啟動 | 真實 subject 尺度／追蹤成效及其幾何錨點 | lifecycle 逆向、有限觀測設計、離線測試 |
| source 時間、曝光／ROI／drive 對齊未閉合 | 動態估計與光學事件自動授權 | 原始解碼、已完成歷史曲線、合成契約測試 |
| 新 observer memory／owner／stack／安裝生命週期未驗 | 部署機內 recorder | ABI／ROM／模擬驗證、既有原生觀測 |
| 抽電池／當機沒有 power-off callback，暖開機重建 heap | 宣稱 armed 接點在任何斷電下都安全 | 普通／強制關機還原已驗；veneer boot-stamp 守衛可離線設計 |
| 測試卡尚未宣告 hook 接點的 4-byte 區段 | 武裝 AF 接點（gate 會如實拒絕） | 卡片區段工具已完成；其餘離線工作不受影響 |
| lens moving 使幾何清窗 | 持續移動中的連續幾何輸出 | 真實 settled 窗口量測、呼吸校準設計、AAT-only |
| EP83／DMA／native USB owner、五層逐批回收未閉合 | P0 持續資料平台部署／實收與連續 session | 同 owner／lease 設計、schema／decoder、CINE lifecycle 逆向及離線分析 |
| DFD 尚無跨場景額外價值證據 | DFD 位移增量 | 幾何＋CDAF、AAT 改善 |
| 缺實際錄影光學 A/B | 連續 AF 改善與產品發布聲明 | 有界候選、資料契約與恢復準備 |

程式與原始資料維持原位置：[幾何實作](../../fpSup/focus/geometry/)、[AF 研究工具](../../research/autofocus/)、[raw captures](../../research/autofocus/captures/)。本專案集中計畫及筆記；資料搬遷不改變任何實驗的 provenance 或驗證狀態。
