# sys-perf —— fp 系統優化(2026-10-16 起)

目標：使用者覺得 fp「做什麼都卡卡的」。目前只有離線靜態結果，所有數字都要上機才算數。

## 已排除(不要再追)
- 全域設定：Cortex-A7 級單核，快取/MMU/預取/memcpy 都合理(`research/firmware/notes/CPU_GLOBAL_CONFIG.md`)。
- 待機降頻：找不到執行期改 CPU 時脈的程式碼(`CLOCK_IDLE_IRQOFF.md`)。
- idle 任務：只做 WFI,不空轉。
- `C0500A68` ≥10KB 整快取清除：只在 PTP vendor 路徑。

## 候選，依「對卡頓的直接程度 × 離線可驗證度」排序
| # | 候選 | 證據 | 離線可驗？ | 改行為？ |
|---|---|---|---|---|
| 1 | 換 LZ4 圖示解壓器 `C05A7630`/`C04D11E8`(逐位元組，15.9 指令/位元組) | unicorn 實測 | 可，2005 張逐位元組對拍 | 否 |
| 2 | fill `C0722490` 改多像素寫入 | 靜態 | 可 | 否 |
| 3 | 等倍貼圖快速路徑(span 仿射 12–58 指令/像素) | 靜態 | 部分(要先追分派點) | 否 |
| 4 | 每輪重繪後 `C0528700`→`C000E91C` 整快取清除，改清 dirty rect 範圍 | 靜態 | 否 | 否 |
| 5 | 頁面資源單格→兩格 LRU(`C05663E8`) | 靜態 | 否 | 否(碰 RCACHE hook) |
| 6 | 重繪節奏 48→32 ms(`[0xC3782FA4]` 3→2) | 靜態 | 否 | 是，需同意 |
| 7 | CamSch ≥60p AE 槽隔幀(週期表 `C090F0AC`) | 靜態+舊量測 | 否 | 是，需同意 |
| 8 | MONITCYC 2 ms、`C01DA808` 自旋 | 靜態 | 否 | 視改法 |

## 上機第一輪(相機回來後)
1. 廣播取得相機使用權。
2. `profiler/pcsample.py check`(唯讀)→ 驗 PC 位址、通道空閒(見 `profiler/README.md`)。
3. 原廠計時：uicMgr+0x198 bit0(Gui Update/Render µs)、`cam ls/le`(CamSch 每槽)。
4. PC 取樣：待機、開選單、翻頁、回放、錄影 FHD 29.97/59.94,同一次開機。
5. 依結果重排上表。

## 筆記
`research/firmware/notes/`:CPU_GLOBAL_CONFIG、PC_SAMPLER_HOOKPOINTS、CPU_POLLING_HOTSPOTS、CLOCK_IDLE_IRQOFF、PER_FRAME_CPU_PATH;
`research/display/notes/UI_DRAW_CPU_COST.md`;profiler 在 `profiler/`。

## 使用者觀察(2026-10-16)
「開啟一堆 UI 會影響錄影效率，更容易卡停。」錄影任務優先權高於 DrawMgr,所以可能途徑(未量):
1. 每輪重繪後 `C000E91C` 整快取清除+關中斷 → 延遲 SD/影格中斷、趕掉錄影任務快取(不受優先權保護)。
2. CPU 繪圖 + 多圖層掃描與 RAW/SD DMA 搶 DRAM 頻寬。
3. CYC_DRAW 等循環處理器在中斷內跑。
4. 低於 17 的錄影相關工作(CamMain 20、自家 writer 28 類)被 DrawMgr 搶。
5. 直方圖/波形若是 CPU 逐幀算。
上機 A/B:同設定 UI 全開 vs 最少，各量 PC 取樣、Gui Render µs、`C000E91C` 次數、停錄時間。待確認使用者開的是哪些 UI 元素。

## 進度與順序(2026-10-19 使用者定)
- 離線完成：neonblit、dirtyclean、filldma、lz4fast,整合成 sup/out/70PERF.BIN(預設四開關全關;上機逐步開，見 sup/README.md)。
- **上機測試通過後**才做剩下的:(1)同變數 UI 訊息合併/值沒變不重畫 (2)圖示解壓結果快取 (3)頁面資源多格 LRU(碰 RCACHE hook,要上機)
  (4)有輸入立即重畫(改原廠行為——做之前再跟使用者確認一次)。

## 上機實測 1(2026-10-19,待機 CINE,FHD 29.97,PC 取樣 2.4 s)
| | 波形開 | 波形關 |
|---|---|---|
| 閒置 | 47.6% | 72.1% |
| DrawMgr | 28.8% | 4.9% |
| CamSch | 11.2% | 10.8% |
**波形監視器(SetDisplayBrightnessLevel=1,HistogramDrawerWaveForm)單獨吃約 24% CPU**:
`C05A35A0`(每欄 256 格直方圖+畫)7.9%、`C05A34B8`(330 欄抽樣)6.0%、DrawMgr 內 memcpy 6.1%。
→ 新優化目標第一名：波形繪製(逐位元相同的 NEON/演算法改寫)。captures:profiler/captures/idle-1、idle-nowave。

## 上機實測 2(2026-10-19,70PERF.BIN 已載入，控制區 0x45403420,build 76bb98cc)
- 安裝:state=1,15 字全換(LOAD.LOG 4096 B 滿在 32RESCUS,70PERF 那行沒寫進去 → 用 pf_layer_fill 位址反推控制區)。
- 全關：所有路徑走原廠(dirtyclean fallback why=1)。
- **dirtyclean ✅**:波形開時 why=3(非 UIC drawer)全 fallback,符合設計;波形關時 fast 路徑接手(~13 輪/s)、全程開中斷;
  但每輪都是 whole-buffer(原廠每次 commit 後整層 memcpy 到下一個 back buffer),截圖無殘影。
- **neonblit ✅**:選單畫面 nb=1 與 nb=0 截圖**逐像素相同**(diff=0)。
- **filldma ✅(驅動)**:直接呼叫 C00DB188 填 1 KiB:回 0、256 字全 0x11223344(位元組序對)、護欄 0x5A 未動、完成中斷正常。
  但 dispatcher 的 fill 槽開機後只被呼叫 2 次(開機時),選單/換頁都不走 → 實際收益小。
- **lz4fast ⚠ 未觸發**:選單各頁 lz_calls=0,沒驗到。要找會走 C05A7E50 的畫面(開機動畫/回放?)。
- 導航注意：直接送 RIGHT/LEFT 會進曝光模式選單(M/S/A/P),差點改到模式;之後用 fp-ui-selftest 的導航。
- cave 區被 filldma.test(0x500)用光，第二輪 profiler 裝不上，要重開機。

## 上機實測 3(2026-10-19,重開後，自訂顯示模式，逐項開 UI,CINE 待機 PC 取樣 2 s;腳本 validation/20261019-live/ui_cost.py)
| 元素 | DrawMgr 增量 |
|---|---|
| 亮度波形 BrightnessLevel | **+24.9%** |
| 時間碼 TimeCode | **+6.6%** |
| 音訊表 AudioMeter | +3.4% |
| 水平儀 | +0.9% |
| 格線/構圖框/中心點/斑馬/鏡頭資訊/日期 | ≈0 |
- 全開:DrawMgr 49.5%、閒置 26.9%(大於各項相加)。**70PERF 全開 vs 全關：無差別(50.1 vs 49.5)**——熱點不在 70PERF 換掉的路徑。
- 全開時 DrawMgr 內：波形 `C05A35A0`+`C05A34B8` 27.5%、**`C0563BA8` 14.4%**(ARGB4444 逐像素依 alpha 查 16×16 表 0xC0D0D684 縮放 RGB)、
  memcpy 12.8%(推:每輪整層複製到下個 back buffer)、`C0706960` 5.0%。
- 時間碼熱點 `C06FBD28`/`C06FBCAA`(Thumb,driver 6 區)不在 neonblit 換掉的 9 個 span 內。
- 下一版(v2)目標：波形、C0563BA8(NEON vtbl)、整層 memcpy 只複製 dirty 範圍、時間碼的 span。
- 顯示設定已還原成使用者原值(模式 1、波形 1、音訊表 1、時間碼 0、斑馬 0)。

## 剩下四項(2026-10-19 離線完成)
| 項目 | 結果 |
|---|---|
| uicoalesce | **不做**:原廠已合併同變數更新(C0563F40,每輪一次);值沒變不重畫上限 <1%。時間碼熱點=span idx 7 `C06FBCD8` |
| inputredraw | 完成：`C06D1418` bl→ReqForceDraw,按鍵到喚醒 48→0 ms(模擬);錄影中預設原廠節奏 |
| pagelru | 完成，預設關：換頁 `C05DD5CA`/`C05DD670` 保留舊畫面 2 頁;`C05663E8` 不是頁快取(QS 版面)已更正;上機要逐頁截圖 |
| iconcache | 完成:UI 圖示真正解碼器是 `C0601F98` 內嵌 LZ4(`C06021A0..C060235A`);**lz4fast 換錯解碼器**(C05A7630 不在 UI 路徑);命中 17× |
v2 待整合:inputredraw、iconcache、pagelru(關)+ CPU 熱點(波形、C0563BA8、span idx 7、整層 memcpy)。

## 上機實測 4(2026-10-19 23:40,70PERF v2,sha256 7eec82b3…,控制區 0x45403420 layout 2)
- 安裝 state=1,七開關全關 = 原廠路徑。
- ir/ic/pl 全開：選單 SHOOT 1→2→3→2→1 換頁 **截圖與全關逐像素相同**,首次 vs 快取回來也相同。
  pagelru:hits 2、kept 5、evict 1;iconcache:misses 38、hits 2(回頭的頁被 pagelru 保留，不再解碼)。
- inputredraw:calls 18、kicks 1、skip-pending 9——換頁鍵原廠已在 key-down 強制重畫，收益小;延遲未量(需 Gui Render 時間戳)。
- ui_cost(v2 全開 vs 全關，全 UI):DrawMgr 49.8% vs 47.9%,無差別(符合預期：v2 新功能針對延遲，不是 CPU 熱點)。
  每元素增量與實測 3 一致(波形 +26.6、時間碼 +8.9、音訊表 +4.0)。全 UI 全開截圖正確。
- 注意：這次相機的格率/ISO/片段號(25p、ISO 1000、A001-001)與先前(29.97p、ISO 800、A001-102)不同，非本次操作所致，已告知使用者。

## 上機實測 5(2026-10-20 00:0x,70PERF v2.1 sha 855a7200,含 neonblit idx 7)
- 只開時間碼，交替 3 輪:**nb=0 DrawMgr 8.6%、nb=1 21.5%(neonblit 讓它變慢 2.5 倍)**。
- PC 取樣：時間在 nb_a4_blend 的逐像素尾段(nb_mod+0x4E4..0x598),NEON 主迴圈只約 1/6。
- 根因(推):離線測速用隨機 alpha;實機字形窄(29 px)、大半透明，原廠可能有 alpha 0/F 捷徑，我們每像素完整混色+每呼叫 vpush。
  v1 全 UI 時 nb=1 也略慢(49.8 vs 47.9),同一問題。**教訓：測速必須用實機的資料分布(真實字形、真實 run 切法)。**
- neonblit 修正交回該線(全 alpha 0 跳過、全 F 複製、短寬度走原廠/精簡路徑，每種實際情況必須 ≤ 原廠)。
- layercopy:DrawController 實際佈局與假設不符(ctrl=0xC3782FC8),交回該線寫唯讀探針。
- alphalut(C0563BA8 取消預乘)離線完成(含全 0 與 UI 樣內容皆不慢於原廠),整合中。

## 上機實測 6(2026-10-20)
- alphalut(70PERF 1b4ae277):選單 SYSTEM 頁 al=0/1 **截圖逐像素相同**;al=1 時真的執行(2 calls、174592 NEON 塊 ≈ 整層)。CPU A/B 未量成(USB 卡死)。
- **v2 起 USB shell 頻繁卡死**(需關機-拔線-開機-插線)。刪掉 70PERF.BIN 重開後：40 指令 39 成功(首條逾時屬正常)、
  profiler 取樣+改顯示設定 6 輪全穩。推論:iconcache 1 MiB class-0 arena(+pagelru 保留畫面)擠壓 shell/USB 記憶體(未證實)。
  → 下一版 lean:`--without ic,pl`,只放 dc/nb/fd/lz/ir/al/wf。
- 卡上目前**沒有** 70PERF.BIN(已 fl del,重開確認 fill 槽回原廠 C0721480)。
- 拍攝設定在某次相機自行重開後一度變成 25p/ISO 1000/A001-001,之後又見 29.97p/ISO 800(片段號仍 001);非本 session 操作。
- **⚠ 更正(同日稍晚)**:open-gate-ce 告知約 1 小時前相機換插 fpSup2 卡並重開，之後它那邊的 shell 也一直 TIMEOUT。
  拍攝設定變化(25p/ISO 1000/A001-001)與 USB 卡死的時間點都與換卡重疊 →「iconcache 1 MiB arena 擠壓 USB」的推論**證據不足**,
  可能只是換卡後的狀況。lean build 仍保留作為對照，但 v2 不應被判定為卡死原因，要用同一張卡做有/無 70PERF 的對照才算數。
  fpSup2 卡的 32RESCUS.BIN 開機會自動套回 OG3K(res-custom 存檔)→ 錄影實際模式要錄完讀 0xC343B590 確認。

## 錄影中全系統 CPU(2026-10-20,fpSup2 卡，實際模式 230、29.97p、LOSS 開 232/233 幀壓縮;無 70PERF)
| 每秒 | DrawMgr | 閒置 | CamSch | MRecMgr |
|---|---|---|---|---|
| 錄影中，波形開 | 31–34% | 28–30% | 15% | 9% |
| 錄影中，波形關 | 4–5% | 56–59% | 14% | 9% |
| 停錄後待機，波形開 / 關 | 33% / 4% | 40% / 70% | 11% | — |
- **錄影中最大的 CPU 消耗是 UI(波形),大於所有錄影任務總和**;波形單獨約 28%。錄影任務本身(CamSch+MRecMgr ≈ 24%)不隨波形改變。
- 20GYR2 的 hook 程式在 MRecMgr 內約 1.9%(outside:451C99xx)。
- 波形框實測：背景 x=684 y=431 332×186,畫點 x=685 y=432 330×184(wave_probe2.txt)。
- → 重做波形(方案 A 逐位元相同：直接寫像素+只複製框)開發中:projects/sys-perf/waveform2/。
- 腳本:validation/20261019-live/rec_profile.py;captures:profiler/captures/take1、take2-nowave。

## UI 延遲實測(2026-10-20,只載入 00SHELL,其餘 sup 全停用;原廠 GUI log:uicMgr+0x198 = 0xC37B71E0 bit0、log act GUI)
| 操作 | 按鍵→開始 | Gui:Update | Gui:Render | 按鍵→完成 |
|---|---|---|---|---|
| 開選單 | 85 ms | **346 ms** | 66 ms | ≈430 ms |
| 切分頁 | 85 ms | 131–210 ms | 66 ms | ≈220–300 ms |
| 關選單 | 35 ms | **482 ms** | 16 ms | ≈520 ms |
- **卡頓主體是 Gui:Update(UI 樹更新/排版)**,Render(實際畫圖)只 16–66 ms → 先前的繪圖加速打在小頭上。
- 開關選單 PC 取樣:**DrawMgr 37% 落在 LOADER 基底+0x57200..0x58200 的 RAM 程式碼**(呼叫者 C05D9B5D、C05E8E13、C05E7B4D…),
  推為 fpSup loader 的 UI hook(私有字串/資源),即使所有 sup 停用仍在跑。分析中:notes/LOADER_UI_HOOK_COST.md。
- 腳本:validation/20261019-live/ui_latency.py;資料:validation/20261020-uilatency/。

## ★ 系統性發現：所有 sup 的程式碼都跑在不經快取的別名上(2026-10-20 上機證實)
- 頁表：VA 0x45xxxxxx 描述子 0x45044C02 = supersection,TEX=4 C=0 B=0(**non-cacheable**);
  VA 0xC5xxxxxx 描述子 0x45045C06 = 同一實體位址,TEX=5 B=1(WBWA)。兩別名讀到同樣資料。
- 韌體配置器(C001D740 等)回傳的是 0x4… 非快取別名 → loader、uishare hook、gyro、LOSS、ULWR、70PERF 全部在非快取記憶體上執行。
- 實測:400 萬指令小迴圈，快取別名 0.04–0.06 s(多為 USB 開銷)、**非快取別名 2.26 s(慢約 50 倍以上)**。
- 解釋了：開關選單 Update 37% 在 uishare 字串 hook(notes/LOADER_UI_HOOK_COST.md)、neonblit 模擬快實機慢、錄影中 gyro hook 約 2%。
- 修法(待使用者決定，共用 loader):sup 程式碼與私有資料改用 +0x80000000 快取別名執行(載入後 D-cache clean + I-cache invalidate);
  交給 DMA 的緩衝(USB TRB、LOSS 幀)必須留在非快取別名。建議逐 sup opt-in,先做 uishare UI hook。

## 字串 hook A/B(2026-10-21,loader v4,同一張卡、同一次開機流程，只換 4 個檔)
A = uishare 套娃層(card-ui4,LOADER 30740 B);B = 核心單層查表 hook(card-ui5,LOADER 19980 B)。
工具 validation/20261019-live/ui_latency.py,資料 ui_latency_1952*.json(A)、1954*/1955*/1956*(B)。單位：Gui:Update ms。

| 動作 | A | B | 差 |
|---|---|---|---|
| 開選單(×3) | 480 / 477(第一次 1,暖機) | 191 / 194 / 192 | **−60%** |
| 關選單 | 量不到(log 空) | 265–283 | — |
| SHOOT 1→2→3 | 197, 174 / 197, 177 | 82, 82 / 83, 83 | −55% |
| 3→2→1 | 184, 272 / 178, 273 | 88, 136 / 77, 136 | −50% |
| SHOOT 1→fpSup | 252 / 252 | 111 / 117 | −55% |
| fpSup→SupManager | 252 | 131 | −48% |
| SupManager→fpSup | 232 | 104 | −55% |
| 按鍵→開始更新 | 約 315 ms | 約 80 ms | −235 ms |

- 兩輪各自重複性好(差 <5 ms)。Render 不變(60–80 ms):省下的全在 Update(記錄解析時的字串查詢)。
- B 的 fpSup / SupManager / SHOOT 1 截圖文字全對;重開機 A 10.3 s、B 7.3 s。
