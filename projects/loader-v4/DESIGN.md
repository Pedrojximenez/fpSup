# Loader v4 設計(草案，2026-10-20)

狀態:**已定稿(2026-10-20,§10 使用者拍板)**,尚無程式碼、沒上機、沒 commit。使用者已決定:**全部一起改、全產品一起重出**。
依據：使用者 2026-10-20 的五點要求 + sys-perf 上機發現(`projects/sys-perf/README.md`「系統性發現」、
`projects/sys-perf/notes/LOADER_UI_HOOK_COST.md`)。v3 現況只當經驗參考(記憶 rebuild-first-principles)。

---

## 1. 目標與非目標

**目標**
1. **loader 核心最小化**:只做「載入、記帳、還原、配置、註冊表」,不帶任何畫面功能。
2. **SupManager 獨立成 sup**(`\fpSup\SUPMGR.BIN`),負責列出 sup、啟用/停用。
3. **各 sup 的設定直接掛在 fpSup 頁**,不再藏在 SupManager 的「更多設定」裡。
4. **移除** Updates、SD Card Format、About fpSup。以後要就做成獨立 sup,自己註冊一列。
5. **fpSup 頁支援翻頁**:每頁 5 列，超過就分頁;焦點在標題列時 ◀▶ 翻頁。
6. **快取執行**:sup 的程式碼與私有資料改走快取別名(+0x80000000),實測非快取慢約 50 倍。

**非目標**
- 不做執行期卸載 sup(維持 v3:停用 = 下次開機不載)。
- 不改 sup 檔案格式的基本形(一檔一塊、entry 一次、claim 記帳),只擴充。
- 不在 v4 做 sup 之間的資料共享框架(uishare 共用變數照舊)。

## 2. 現況(v3)與要改的地方

| 項目 | v3 現況 | v4 |
|---|---|---|
| fpSup 頁 | LOADER.BIN 內建(allsups.c + `\fpSup\UI\ALLSUPS.BIN`,FT6Z):SupManager / Updates / SD Card Format / About 四列 | loader 只提供「fpSup 頁 + 註冊 API」;列全部來自 sup |
| SupManager | allsups.c,編進 LOADER.BIN(`SL_ALLSUPS`),每頁 5 列 × 5 頁 | 獨立 sup,透過註冊 API 在 fpSup 頁放一列，跳到自己的頁 |
| sup 的設定入口 | `svc->button()`(v4 服務表):在 SupManager 彈窗裡的「More Settings」 | `svc->page_add()`:直接成為 fpSup 頁的一列 |
| 停用清單 | LOADER.BIN 檔尾 `FSDS`(DS_MAX 30) | 不變，仍由 loader 核心保管(見 §6) |
| sup 記憶體 | `mem_get(class 0)` 回傳 **0x4… 非快取別名** | 程式碼/私有資料走 +0x80000000 快取別名(見 §5) |
| UI 字串 hook | uishare 套娃 hook(C05E5B58/C05E61C8/C05E61E0),hook 本體在非快取記憶體 | 同機制，但 hook 本體在快取別名;沒有私有字串的 sup 不掛層 |

## 3. loader 核心職責(最小化)

只保留這些，其他一律外移到 sup:
1. 列 `\fpSup\*.BIN`、**依檔名字母排序**(不再用數字前綴)、讀停用清單(沒有 SupManager 時忽略)、逐一載入(一檔一塊)、呼叫 entry。**只認 v4 格式**;舊格式不載入，LOAD.LOG 記一行「格式不符」。
2. claim 記帳(CHAIN / EXCL / SHARED_UI)、journal、關機寫回(PowerOffMgr,沿用 HOOKS_AT_POWER_OFF.md)。
3. cave 配置(veneer)、`publish()`(D-clean + I-inval)。
4. **新**:快取執行的載入流程(§5)。
5. **新**:fpSup 頁註冊表 + 一個通用的 fpSup 頁(§4)。
6. 停用清單的讀寫 API(給 SupManager 用)與救援(§6)。
7. LOAD.LOG(順便修：v3 的 4096 B 會被 hook 行塞滿，後面的 sup 就沒有記錄——v4 改成每個 sup 一行摘要、hook 細節另檔或計數)。

不再在核心裡的：SupManager 畫面、Updates、SD Card Format、About、任何文字/圖片資源以外的 UI 邏輯。

## 4. fpSup 頁註冊 API

### 4.1 服務表(v4 起，只往後加)

```c
/* 一列。loader 只記指標，結構與字串由 sup 常駐保管。 */
struct sl_row {
    uint16_t kind;       /* SL_ROW_JUMP / SL_ROW_TOGGLE / SL_ROW_LIST / SL_ROW_ACTION */
    const char *title;   /* 列標題(UTF-8,常駐) */
    const char *value;   /* 右側摘要文字(可 0;TOGGLE/LIST 由 loader 依 get 產生) */
    int  (*get)(void *arg);                 /* TOGGLE/LIST:目前值 */
    int  (*set)(void *arg, int v);          /* TOGGLE/LIST:使用者選的值;回 0 成功 */
    const char *const *choices; uint16_t n_choices;   /* LIST 的選項 */
    int  (*open)(void *arg);                /* JUMP:跳到 sup 自己的頁;ACTION:按 OK 執行 */
    void *arg;
};
int (*page_add)(const struct sl_svc *, const struct sl_row *row);   /* 回列號或 <0 */
void (*page_refresh)(const struct sl_svc *, int row);               /* 值變了，重畫該列 */
```

- **列類型**:JUMP(›,跳 sup 自己的頁)、TOGGLE(開/關)、LIST(彈出清單)、ACTION(按 OK 執行一次，例如格式化)。
- **回呼都在 UI 執行緒**,要快速返回;重工作自己丟到別處(沿用 v3 button 的規則)。
- **字串**:標題與選項用 sup 自己常駐的字串，loader 透過 uishare 的私有字串層顯示;語言由 sup 決定(可給多語系表)。
- **排序**:不用數字。fpSup 頁的列**依顯示名稱排序**;唯一例外：SupManager(若有)固定第一列。
- **上限**:只限總列數 64(約 13 頁，可調);**不限單一 sup 的列數**。超過回 SL_FULL,不影響其他 sup。
- **載入失敗或被停用的 sup 不會出現在 fpSup 頁**(它的 entry 沒跑，自然沒註冊)。

### 4.2 翻頁

- **每頁 5 列**(保留底部提示;記憶 menu-slots-and-scrolling:超過 6 沒有先例，不嘗試捲動)。
- 列數 > 每頁格數時分頁;分頁狀態顯示在標題列(例「fpSup 1/3」)或底部提示(沿用 v3 SupManager 的 T_PAGE_HINT 做法)。
- 按鍵:**焦點在標題列時 ◀▶ 翻頁**(v3 SupManager 已上機驗證的作法);焦點在列上時照原廠語意(RIGHT = 進入/開清單)。
- 翻頁只換「列 → 變數」的對應(v3 FT6 已驗證的作法：固定可見格數的變數，換頁時重新 POST_STR),不需要新的 .cvm 頁。

### 4.3 實作重點(沿用已上機驗證的機制)
- fpSup 頁本身沿用 v3 的頁面掛載(FT_ page-id hook、`\fpSup\UI\` 資源、NBR 讀取器);v3 的 FT6 結構改成「通用列表頁」,內容由註冊表填。
- SupManager 原本用的「五格 × 名稱/版本/狀態」版面成為 SupManager sup 自己的頁。

## 5. 快取執行

### 5.1 事實(上機證實 2026-10-20)
- VA 0x45… 描述子 `0x45044C02`:supersection TEX=4 C=0 B=0 = non-cacheable;VA 0xC5… 描述子 `0x45045C06`:同一實體，TEX=5 B=1 = WBWA。
- 兩別名內容相同;4M 指令迴圈：快取 ~0.04 s、非快取 2.26 s。
- 韌體配置器回傳 0x4… 別名，所以 v3 所有 sup 都在非快取記憶體上執行。

### 5.2 規則
- **sup 區塊預設以快取別名執行**:loader 讀檔到 0x4… 區塊後，對整塊 D-clean(實際上非快取寫入已在 DRAM,但保險起見)、**I-cache 全失效**,然後以 `block + 0x80000000` 計算 entry 並呼叫;傳給 sup 的 `block` 也是快取別名。
- **區塊 64 B 對齊、尾端補到 64 B**,避免和配置器管理資料共用快取列(配置時多要 128 B 自己對齊)。
- **DMA 共用的緩衝必須宣告**:sup 標頭新增 `dma_off/dma_len`(一段)或 sup 自行用 `svc->uncached(ptr)` 取 0x4… 別名存取;交給 DMA 前後自己做 range clean / invalidate(`C000EB90` / `C000EB28`)。
- **sup 標頭新增 `flags`**:`SL_F_CACHED_OK`(v4 sup 預設設);沒設的在非快取別名執行(給確實需要的特殊 sup)。舊 v3 格式不載入。
- **寫回自己程式碼的 sup**(自修改、狀態字在程式碼裡，記憶 state-words-inside-code):寫完要 `publish()`;這類寫入點要逐一列出。
- **loader 自己**(常駐的 hook:關機寫回、UI 頁)也改走快取別名。

### 5.3 驗證法
- 離線：模擬器不反映快取 → 只驗位址換算、標頭欄位、DMA 段宣告與 publish 順序。
- 上機:(a)讀頁表描述子確認 block 落在 WBWA;(b)同一段迴圈在兩別名計時(sys-perf 的方法);
  (c)`ui_latency.py` 量開/關選單的 Gui:Update(基準：開 346 ms、關 482 ms,只載 shell);
  (d)每個有 DMA 的 sup 跑它自己的上機驗收(USB 傳輸 sha、LOSS 壓縮逐檔比對、gyro 一筆不漏)。

## 6. 停用清單與救援

- 停用清單仍在 LOADER.BIN 檔尾(`FSDS`),由**核心**讀寫;SupManager 只透過 `svc->disabled_get/set(id)` 修改。
- **SupManager 不能停用自己**(核心拒絕把 SupManager 的 sup_id 寫進清單)。
- **不做救援鍵**(使用者:不是每個人都需要 SupManager)。
- **卡上沒有 SupManager(或它沒載入)時，核心忽略停用清單、全部載入**——放了什麼就載入什麼，也不會因為拿掉 SupManager 而被舊清單卡住。
- 停用改名的 128 B 假檔問題(記憶 sup-writeback-must-not-create):v4 不改檔名，只用清單。

## 7. SupManager sup

- 檔名不帶數字(例 `SUPMGR.BIN`;載入順序依檔名字母，SupManager 只需在 UI 第一次打開時讀結果，它要列出別人的載入結果，所以**畫面資料在 UI 第一次打開時才填**,不是 entry 時)。
- 需要的服務：`page_add`(在 fpSup 頁放一列 JUMP「SupManager」,固定第一列)、`sups_list()`(名稱、版本、這次是否載入、下次是否啟用、失敗原因——由核心提供只讀表)、`disabled_get/set`。
- 自己的頁 = v3 allsups 的版面(名稱/版本/狀態 × 5 格 × 分頁),程式與 UI 資料從 LOADER.BIN 搬出。
- 不再有「More Settings」彈窗;各 sup 的設定在 fpSup 頁自己那一列。

## 8. 各 sup 遷移清單

下表「UI」= 現在怎麼掛畫面;「DMA」= 推測要留非快取的緩衝,**每個都要該 sup 的維護者確認**。

| sup | UI 現況 | v4 要改 | DMA(推測) | 風險 |
|---|---|---|---|---|
| 00SHELL | 無 | 標頭 flags;USB TRB/MEM1 緩衝走非快取 | **有**:TRB、EP82/83 傳輸緩衝、MEM1 窗口 | 高:USB 最敏感;先單獨驗 |
| 05STOPFX | 無 | flags | 無(推) | 低 |
| 10LOSS | SupManager More Settings + 拍攝選單列(uishare add_row) | 設定改 `page_add`;flags;LJ 引擎/表頭 DMA 緩衝宣告 | **有**:壓縮輸入輸出、表頭 DMA、寫卡批次 | 高 |
| 20GYR2 | More Settings? | `page_add`;flags | **有**:零拷貝寫卡(.GYR v7) | 中 |
| 20ULWR | 無/More Settings | flags;寫卡緩衝 | **有**:SD 寫入批次 | 高 |
| 30FCAP | 無 | flags | 待查 | 低 |
| 32RESCUS(res-custom/OGC) | `svc->button`(ogc.c、rl_v3.c)+ 解析度清單 add_option + 私有字串 | `page_add`;flags;RCACHE hook(記憶 rcache-v3-takes-the-cache) | ISP/感光元件設定(多為暫存器，推無 DMA 緩衝) | 高:UI 最複雜 |
| 40FLIP | 自己的 TOOLS 列 / BIN 存設定 | 改 `page_add`(TOGGLE/LIST) | 無(暫存器) | 低 |
| 41DSQZ / 42TAPZ | 待查 | `page_add`;flags | 待查 | 中 |
| 45RAWV | 設定存自己 BIN | `page_add`;flags | **有**:RAW 幀緩衝 | 中 |
| 60FPPTP | 待查 | flags | **有**(推):PTP/USB | 中 |
| 70PERF(sys-perf) | 無 UI(perfctl) | 可選 `page_add` 開關;flags | Fill DMA 目標(層緩衝本來就在快取別名) | 低 |
| uishare(編進各 sup) | 私有字串套娃 hook | hook 本體在快取別名;沒有私有字串的 sup 不掛層 | 無 | 中:所有 UI sup 共用 |

## 9. 合併頁(merge-v3)要改的

- 產出 v4 LOADER.BIN(新核心)+ `SUPMGR.BIN`;移除 Updates/Format/About 的資源。
- 衝突檢查加：每個 sup 的 v4 標頭(flags、DMA 段)、`page_add` 列數總和 ≤ 上限、顯示名稱重複提示。
- 舊 v3 sup 不支援(v4 loader 不載入);合併頁直接拒收並提示更新。
- 停用清單沿用(sup_id),合併頁可預設勾選。

## 10. 已拍板(2026-10-20)

1. 翻頁鍵:**(b)焦點在標題列時 ◀▶ 翻頁**。
2. **不做救援鍵**;沒有 SupManager 時忽略停用清單、全部載入。
3. fpSup 頁**維持**現在位置(SYSTEM 第 6 頁)。
4. **每頁 5 列**。
5. **不做舊版相容**:v4 只認 v4 格式，舊 sup 不載入(LOAD.LOG 記錄)。
6. **拿掉數字順序**:檔名不帶數字前綴，載入順序依檔名字母;fpSup 頁依顯示名稱排序，SupManager 固定第一列。
7. **不限單一 sup 的列數**,只限總數 64。

## 11. 測試計畫

**離線**(每項都要 mutation 證明測試會失敗):
- loader 核心：沿用 `v3/test_v3.py` 的 Camera(真 LOADER + 真 loader.S),加:快取別名換算、64 B 對齊、DMA 段、publish 順序、停用清單、SupManager 不能停用自己、沒有 SupManager 時忽略清單、舊格式拒載。
- 註冊表/翻頁:unicorn 跑 page_add 上限、排序、翻頁變數對應(沿用 test_allsups.py 的 FT6 驗證)。
- SupManager sup:列表內容與 v3 allsups 一致(同樣的載入結果 → 同樣的顯示)。
- 各 sup:原有測試 + 標頭/列註冊。

**上機**(每步先廣播相機使用權、錄影/回放中不碰 USB):
1. 只放 v4 LOADER + 00SHELL:頁表確認快取別名、迴圈計時、USB 傳輸 sha、`ui_latency.py` 開關選單。
2. 加 SupManager:fpSup 頁一列、進出、啟用/停用、拿掉 SupManager 後全部載入。
3. 逐一加 sup(先無 DMA 的：STOPFX、FLIP、FCAP;再 RESCUS;最後 SHELL 以外的 DMA 類 LOSS/ULWR/GYR2/RAWV/FPPTP),每個跑它自己的驗收。
4. 全部一起：開機時間、選單延遲、錄影(LOSS/ULWR/GYR2 同時)、關機還原 ×10、暖開機殘留。

## 12. 發布順序

1. 定稿本文件(§10 拍板)。
2. 核心 + SupManager + shell(v4 最小卡)→ 上機 §11-1/2。
3. 各 sup 維護者依 §8 遷移(可平行，各自上機驗收)。
4. 合併頁 v4 → 全產品一起重出;v3 保留下載作為回退。
5. 公開頁面(fpSup/)更新說明:fpSup 頁變化、快取執行帶來的效能改善(附實測數字)。

## 13. 待辦：瞬間啟動(Fast Start 2)的觸發穩定性(2026-10-20 使用者提出)
- 現況：瞬間啟動「機率性」觸發;使用者認為 hook 位置(目前 0xC03DA420 → cave loader hook)可能要改。
- 兩種可能來源：(a)撥開關後韌體映像時保留時不保留(換位置無用，要找保留條件);(b)映像都保留，但 hook 所在路徑不是每次開機必經(換到必經點即可穩定)。
- 量法：開機標記(--boot-markers)+ 每次撥開關後檢查「hook 字是否仍在」與「實際走的路徑」;hook 在卻沒走 → 換位置;hook 不在 → 映像沒保留。
- 時程：開機外殼(新版動畫 + Fast Start 2/3 + 標記)完成後，與 Fast Start 3 的時間量測一起上機收樣本。
- **結果(2026-10-20,validation/README.md)**:觸發 ⇔ 映像保留;失敗全是映像被重新載入 → **hook 位置不是問題，不改**。USB 連接是主要因素。下一步若要提高觸發率，要查關機路徑的映像保留條件。

## 14. fpSup 頁與 SupManager 頁的畫面(2026-10-21 使用者定案，實作中)

使用者決定：
1. fpSup 首頁用 **SupManager 頁的版型**:fpSUP logo + 標題列(焦點在標題時 ◀▶ 翻頁、頁碼分頁條)+ 5 列;SupManager 固定第一列。
2. sup 的設定列**直接在列上改值**:TOGGLE/LIST 按 Right/OK 開原生 popup 選值，列右側顯示目前值;JUMP 跳到 sup 自己的頁;ACTION 按 OK 執行。
3. SupManager 頁**維持 v3 r3o2 的樣子**(logo、每頁 5 個、Enable/Disable popup、右側重開提示),**拿掉 More options**。
4. Updates / SD Card Format / About 移除(§10 已定)。

### 14.1 分工

- **核心**(LOADER.BIN + `\fpSup\UI\FPSUP.BIN`):共用的 UI 引擎(私有字串層、NBR 頁註冊、`FT_` page-id 層)只放一份在核心;
  首頁 `FT_Y6` 的資料與邏輯(讀註冊表、5 列 × 分頁、popup 選值、JUMP)。
- **sup**:要自己頁面的 sup(第一個是 SupManager)透過服務把自己的 UI 資料檔交給核心註冊，畫面邏輯在 sup 自己。
- 服務表加(版本 6,只往後加;v5 的 sup 照常載入):
  - `ui_pack(svc, path)`:載入並註冊 sup 的 FT 資料檔(字串層 + 頁 + 變數定義),回傳句柄。
  - `ui_show(svc, page)`:切到指定頁。韌體 `gui scr set` 的作法:`o = C054DD38(); o->vt[0x48](o, name)`(離線讀到，未上機)。
- JUMP 列的 `open()` 由 sup 呼叫 `ui_show` 跳到自己的頁。

### 14.2 分階段

1. **首頁**(核心):資料產生器從 v3 `manage_page.build_manage` 衍生 —— 標題列 + 頁碼條沿用;5 列改成「名稱 + 右側值 + popup」。
   列的 popup 項目數固定(LIST 最多 4 個選項,TOGGLE = 2),不用的項目隱藏。離線：原生頁解譯測試 + unicorn 跑核心回呼。
2. **SupManager 頁**搬進 SUPMGR.BIN(資料檔 `\fpSup\UI\SUPMGR.BIN`),拿掉 More options;經 `ui_pack` 註冊、首頁第一列 JUMP 到它。
3. 上機：首頁畫面、翻頁、popup 改值、JUMP 進出、MENU 返回、SupManager 啟用/停用。

風險(要上機才知道):`ui_show` 從 UI 執行緒回呼切頁後 MENU 返回是否回到首頁;popup 項目數動態隱藏。
