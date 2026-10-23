# 70PERF.BIN —— sys-perf 整合 sup(Loader v3,控制區 layout 2)

v1(四模組)2026-10-19 已上機：安裝、dirtyclean、neonblit 逐像素、filldma 驅動通過，lz4fast 未觸發(見 `../README.md` 上機實測 2/3)。
v2(本版，同日離線):加 inputredraw、iconcache、pagelru。**v2 沒有上機、沒有寫卡、沒有 commit。**

| 模組 | 做什麼 | 修補點 | 開關 |
|---|---|---|---|
| dirtyclean | 重繪後只清畫過的範圍，不整快取清除 | 3 個 ARM `bl`:`C0528AE0` copy、`C05287F4` clear、`C0528954` clean | dirtyclean 自己的 `C_EN` |
| neonblit | ARGB4444 圖層 span 表 1 的 NEON 版 | 9 個 span 指標(資料)`0xC2EB3F5C..F94` | `pf_nb` |
| filldma | 整層清除改走 Fill DMA | 不改任何字;由分派函式呼叫 | filldma 自己的 `fd_enable` |
| lz4fast | LZ4 解壓器(**上機:UI 不走它**,真正的 UI 解碼器是 `C0601F98` 內嵌) | 1 個 ARM `bl` `C05A7EE0` | `pf_lz` |
| inputredraw | 按鍵入列後立即請求重畫(改原廠行為，使用者已同意) | 1 個 ARM `bl` `C06D1418` | 它的 enable(+8);錄影中另有 `rec_ok` |
| iconcache | UI 圖示解壓結果快取(LRU,128 格) | 2 個 Thumb `b.w`(對齊字)`C060219C`(H1)、`C060234C`(H2) | 它的 EN(+4);arena = 本塊 BSS 1 MiB |
| pagelru | 換頁時保留舊畫面(預設 2 頁) | 2 個 Thumb `bl`→`blx`:`C05DD5CA` load(2 對齊,claim `C05DD5C8..CF` 8 B)、`C05DD670` unload | 它的 enable(+4) |
| 分派 | 兩個 vtable 的 fill 槽 `0xC2E38E7C`、`0xC2EF62A0` → `pf_layer_fill` | 2 個指標(資料) | — |

總開關 `pf_master`:0 = 所有 hook 走原廠路徑(新模組經閘門 stub;iconcache 的兩點在函式中間，
閘門**重播被換掉的兩條 Thumb 指令**後接回 `C06021A1`/`C0602351`,旗標與原廠相同)。

## 檔案

| 檔 | 內容 |
|---|---|
| `perf_core.S` | 控制區、`pf_layer_fill`、`pf_dc_gate`、entry(claim → veneer → 分兩階段寫)、`thumb_branch`(blx/b.w 編碼) |
| `build_perf.py` | 從 7 個模組**原始碼重建**,sha256 必須等於它們 patch.json 記的;產生閘門 stub、claim 表、寫入表;`make_sup` 封成 `70PERF.BIN` |
| `test_perf_loader.py` | 經**真的 LOADER.BIN + loader.S** 載入：四種寫入(data/bl/Thumb blx/Thumb b.w)與 veneer、2 對齊點旁的半字不動、模組初值(全 0、arena)、journal(含 8 B claim)、關機寫回、暖開機殘留修復、EXCL/CHAIN 衝突 RELEASE |
| `test_perf_gates.py` | 新模組閘門單元測試：master 0 → 原廠路徑(參數、LR、Thumb 狀態;iconcache 重播的暫存器/記憶體/NZCV),master 1 → 模組 |
| `test_perf_render.py` | 整體：真 `C0528700` 重繪輪 + 真 layer 方法 + 真 Fill DMA 驅動 + 真 span,12 組開關 × 4 情境(含「連續強制重畫」=inputredraw 的效果、ir+dc 共存、全開、全開但 master 關);`--mutate` |
| `test_perf_lz.py` | 真 .xci 經 `C05A7E50`,`pf_lz` 開/關/master 關，與原廠比對 |
| `conflicts.py` | 掃樹裡所有 sup:靜態找位址 + 跑每個 v3 entry 記錄 claim;位址表 = 每個 claim 的每個字 + 每個修補點 |
| `perfctl.py` | 上機:`find`、`status`、`set k=v`(寫後讀回);layout 2 多 `ir`/`ir_rec_ok`/`ir_min_ms`/`ic`/`pl`/`pl_capacity` 與三模組計數 |

產物(13,628 B,含 neonblit 10-19 23:55 加的 span idx 7 `0xC2EB3F78`):`out/70PERF.BIN`(預設，全部功能開關 0)
sha256 `855a7200cda42a17715a15a27382d8fee1530f1396ae092c76de15dd1a50189d`;21 筆 claim(23 個位址)、9 個 veneer。
block = 檔案 + 1 MiB iconcache arena(class 0 loader heap;loader 上限 16 MiB)。`out-all/` 是舊的(idx 7 之前),要用時重建。

建置:`python3 -B build_perf.py --out DIR [--enable dc,nb,fd,lz,ir,ic,pl|all] [--master 0|1]`。

## 控制區(body = 檔案 +32)

| +偏移 | 欄位 |
|---|---|
| 00 | `'PERF'` |
| 04 | layout 版本 = 2 |
| 08 / 0C / 10 | `pf_master` / `pf_nb` / `pf_lz` |
| 14 | 安裝結果:1 = 完成;0x101 claim 失敗、0x102 沒 cave、0x103 cave 超出 BL 範圍 |
| 18 | veneer 位址(cave,9 × 8 B) |
| 1C–28 | fill 分派次數：總、DMA、NEON、原廠 |
| 2C–38 | dirtyclean / filldma / neonblit / lz4fast 在 body 內的偏移 |
| 3C | build id |
| 40 | log 緩衝 |
| **54 / 58 / 5C** | **inputredraw / iconcache / pagelru 在 body 內的偏移**(本版 0x1920 / 0x1A90 / 0x2F90) |

模組內開關：inputredraw +08 enable、+0C rec_ok、+10 min_ms;iconcache +04 EN、+08 arena、+0C arena 大小;pagelru +04 enable、+08 容量。
v1 上機時 LOAD.LOG(4096 B)滿了沒寫到 `PERF ctl`:可用 `[0xC2E38E7C] - 0x60`(=`pf_layer_fill` 偏移 96)反推控制區。

## 安裝 / 拆除 / 關機

- entry:先 claim 全部 21 筆(23 個位址，EXCL),任一失敗 → RELEASE、什麼都沒寫;再 `cave_alloc` 9 個 veneer(ARM `ldr pc,[pc,#-4]`;
  Thumb `b.w` 用 Thumb veneer `ldr.w pc,[pc,#0]`);初始化模組控制字(全部開關 0、iconcache arena = `align8(pf_end)`、EN 最後寫);
  publish;階段 1:資料指標、dc copy/clear、lz、ir、pl unload、ic H2 → publish;階段 2:dc clean、pl load、ic H1 → publish。
- 關機還原 = loader 的 journal。沒有執行期拆除:`perfctl set master=0` 全部回原廠。
- 暖開機殘留由 loader 的 claim 修復(含 Thumb 點)。

## 測試結果(2026-10-19 v2)

- (以下於含 idx 7 的現行樹重跑;mutation 在 idx 7 之前跑，perf_core.S 未變)
- `test_perf_loader`:5/5。`test_perf_gates`:4/4(含 Thumb 分支正負偏移)。`test_perf_render`:48/48(4 情境 × 12 組合)。`test_perf_lz`:3/3。
- 各模組原測試重跑全過:neonblit 2403+600 例 0 失敗、dirtyclean 全情境、filldma 20/20、inputredraw 全過(按鍵→喚醒 48→0 ms)、
  pagelru 10/10、iconcache PASS(2005 張兩輪)、lz4fast 2005 張 0 差異。
- `--mutate`:**21/21 突變被抓到**(原 11 個 + 新 10 個：ir/pl 閘門無視 master、ic1 重播漏 `mov r0,r11`、ic2 重播丟旗標、ic1 接回位址錯、
  Thumb 分支 J2 錯、blx 只寫一個半字、Thumb veneer 寫成 ARM、iconcache arena 沒設、inputredraw 出貨即開)。
  第一輪 J2 突變存活：真機配置的偏移恆為正(cave 在修補點之上，S=0)而與正確碼等價;補了 `ThumbBranch` 正負偏移單元測試後抓到。
- `conflicts.py`:922 個檔**沒有任何一個碰到我們 23 個位址**;陽性對照(本檔):動態 23/23、靜態 22/23
  (`C05DD5CC` 本來就不是本檔的字面值;別的 sup 若改它會帶這個字面值而被抓到)。

## 上機(v2):逐步啟用

前提:v1 步驟已過。每步前廣播相機使用權;錄影/回放中不碰 USB。

1. 寫入 v2(比 v1 長，可直接覆寫;讀回比 sha256),重開;`perfctl status`:state=1、layout 2、全部開關 0。
2. 重驗 v1 四項(dc/nb/fd)不退化(`ui_cost.py`、截圖)。
3. **ir**:`set ir=1`,用 `key` 送方向鍵，看 `ir_kicks`;選單捲動截圖;`uicMgr+0x198` bit0 看 Gui Update 時間戳。
4. **ic**:`set ic=1`,換頁幾次看 `ic_hits/misses`;截圖與 ic=0 逐像素比;換頁 Load_Start/End。
5. **pl**:`set pl=1`,每頁(選單、子選單、QS、回放、popup、各 sup 加的列)截圖與 pl=0 比;捲動位置/動畫狀態;開始錄影確認 `pl_flushed`。
6. 任何一步異常:`master=0`,記下 `perfctl status`,冷開機。

## 上機前未證實的假設

- 各模組 README 所列(iconcache 未在相機上跑過;pagelru 保留畫面的內部狀態不重設、記憶體用量未知;inputredraw 不涵蓋 MENU/MODE 等非 GUI 物件鍵)。
- iconcache 的 1 MiB arena 跟 class 0 heap 要：開機時其他 sup 也在要，總量未在真機量過。
- iconcache 在 sup 層只測了閘門與模組自身測試，沒有「整個 sup 安裝後跑真 `C0601F98`」的測試。

## v3(2026-10-20,離線):併入 alphalut
- 模組 `projects/sys-perf/alphalut`:1 個 ARM bl(`C0561734` → `pf_g_al` master 閘門 → `al_unpremul`;master 關 = 原廠 `C0563BA8`)。
  開關 `al`(alphalut 控制 +08,**預設 0**;模組本身出貨是 1,entry 改寫成 AL_EN_INIT)。計數:calls/neon-blocks/zero-skips/fallbacks。
- 控制區 layout **3**:`+40` = alphalut 偏移(原本 +40..+53 是 log 緩衝，log 行改在堆疊上組，svc->log 會複製)。
  其餘偏移不變(`pf_layer_fill` 仍在 +0x60,`ctl = [0xC2E38E7C] - 0x60` 照舊)。
- 產物 `out/70PERF.BIN` 14164 B,sha256 `1b4ae2777c6b0d66…`,claims 22、veneers 10,neonblit 仍是 18eb444f(idx 7 版)。
- build_perf.py:neonblit.S 與 patch.json 不符時(另一條線正在改)改用 patch.json 記錄的 neonblit.bin(同 sha256)。
- 測試(此 BIN):test_perf_gates 4/4(含 pf_g_al)、test_perf_loader 5/5(layout 3、+40、al=0、ALUT magic)、alphalut 原測試過。
  新 mutants(al 閘門忽略 master、stock 目標錯、出貨即開、+40 未填)已加進 MUTANTS。
  **未完成**:render 48 組、test_perf_lz、conflicts.py 重掃、新 mutants 的有效判定——00:05 dirtyclean.S 被別的線改動
  (patch.json 未跟著更新),目前任何重建都在 module_dirtyclean 失敗;等 dirtyclean 定版後重跑。


## v4:`--without` 與 waveform(2026-10-20,離線)

上機:v2 起(iconcache 1 MiB arena + pagelru)USB shell 頻繁卡死，刪掉 70PERF 後同樣負載 6 輪穩定 → 推論 arena 擠壓 shell/USB 記憶體(未證實)。
- `build_perf.py --without ir,ic,pl,al,wf`:被排除的模組不組進 BIN、不 claim、不配 arena(無 ic 時 block_size 不含 1 MiB),
  控制區偏移字 = 0;perfctl 對它顯示 `n/a`、拒絕 set。
- 新模組 **waveform**(`projects/sys-perf/waveform`):三個 vtable 槽 `0xC2DF8F4C/8FE4/9220`(原廠 `C05A3728`)claim EXCL,
  指向 master 閘門 `pf_g_wf` → `wf_method`;開關 `wf`= wf_ctl+4(**預設 0**),計數 +8 fast、+C fallback。
- 控制區 layout **4**:`+44` = waveform 偏移(其餘不變)。
- **lean 卡** = `out-lean/70PERF.BIN`(`--without ic,pl`):dc、nb(5797fab2)、fd、lz、ir、al、wf,開關全 0。
- 測試(full 與 lean 都跑):test_perf_loader 5/5、test_perf_gates 5/5、test_perf_render 48/48、test_perf_lz 3/3、
  test_perf_without 8 組合;waveform 原測試 166/0;conflicts 922 檔 0 碰觸。
  mutation:test_perf_without 4/4(arena、仍載入、偏移非 0、wf 未 claim),render 新增 wf 4 個(閘門無視 master、stock 位址、出貨即開、+44)。
- 環境變數 `PERF_WITHOUT=ic,pl` 讓四支 sup 測試改測 lean。
