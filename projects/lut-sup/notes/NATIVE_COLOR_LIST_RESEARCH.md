# 原生 COLOR 清單加 N 列 + ±框當強度 —— 離線研究（2026-10-24）

範圍：讓 LUT sup（color 容器）成為 COLOR 清單（ColorButtonMenu）所有附加列的唯一主人，RAW View 改向它登記。
只讀研究，未碰相機、未改任何既有檔案。韌體 5.02。

標記：**[code]** = 反編譯/原始碼/映像直接可見；**[cam]** = 既有筆記記載的實機結果；**[inf]** = 推論，未驗。
縮寫：`RV:n` = `projects/rawview/README.md` 第 n 行；`rvR`/`rvL` = `projects/rawview/build/rv_resident.S` / `rv_launch.S`；
`opt` = `fpSup/uishare/ui/options.py`；`L4` = `fpSup/loader-v4/README.md`；decomp = `out/decomp/full/blk_c0*.c`。

## 0. 基本事實

- 使用者看到的 COLOR 條（COLOR 鍵與 MENU 路徑都是）= **ColorButtonMenu**，model = `ListColorButtonMenu.cvm`（原廠 16 列）＋`_EXCL`＋`_EXCL2`；
  `B1_5_4_Color` 整個開機週期都沒建立 [cam] RV:174-178。關閉選單後版面與三個 model 都釋放，下次開啟重新解析 [cam] RV:176。
- CSV 欄位 `NO,IMAGE,enable,Left,Right,FocusOn`（Left/Right 是 0-based 鄰列，首尾相接）[code] `rv_csv.inc` csv0 表頭、opt:120-125。
- 每列的「名字」**就是圖示**：條上每格是 86×74 的 `set_color_XX.xci`，字畫在圖裡（T&O、SunR.、OFF…）
  [cam] `projects/rawview/captures/2026-09-25/icon_raw.JPG`；RAW 列是自製 `rv_raw_icon.xci` 冒用無人用的 `set_flash_1` [cam] RV:759-766。
- 色彩模式設定字：bank A `0xC31B32BC`+0x12C（`C31B954C`==0 時用 A）[cam] RV:133。
  GUI↔enum 表 `C2E412BC`（16×{enum,gui}，getter `MenuValueConverterBase__v69` `C06C07C0` 回傳表與筆數 0x10）[code] blk_c06.c:159921。
  映像值：GUI0-5→enum0-5、6→15、7→6、8→7、9→8、10→13、11→9、12→10、13→14(DUO)、14→11(MONO)、**15→12(0xC=OFF)** [code]（seg1 讀出）。
  UI 條件式裡的 `CM_*_ColorMode` 都是 **GUI 值**（≤12 一般、13 DUO、14 MONO、15 OFF）[code+cam] RV:676-677。

## 1. RAW View v4 現在怎麼加第 17 列

建置：`build_v4_rawview.py` → `build_v3_rawview.build(v4=True)`；UI 列由 `opt.color_raw()` 產 FPUI 區塊，經
`fpSup/fpsup-ui/build_stock_section.py`（`fpui_stock.c`，無字串層）當段落帶進 RAWV.BIN（build_v3_rawview.py:83-92）。
claim 共 40 個（RAWV 40 已在 v4 實機 LOAD.LOG 看到 [cam] L4:414）：

**(a) UI 資料（fpui_stock 區塊，開機套用，頁面/CSV 都是複本）**
- 取檔重導 `C05E5BEC`（Thumb `adds r0,r0,r1; str r0,[r5,#4]`，原字 `0x60681840`）→ 共用 `fv_handler.S`，表容量 32；SHARED_UI claim [code] opt:41,93-96。
- 三個 CSV 複本 `OP_CSV_ADD`：主檔加 `{N},set_flash_1,0,{Q},0,{P}`，第 1 列 Left→P、最後原廠列 Right→P；
  `_EXCL` 加 `{N},set_common_1,1,15,15,15`、`_EXCL2` 加 `{N},set_common_1,1,14,0,15`（停用列）[code] opt:120-125。
  `OP_EXPECT index 16`：拿到的不是 GUI 16 就整個不加 [code] opt:141。
- 圖示：`set_flash_1.xci`（`C14EBAAC`,533 B）整檔換成 RAW 圖 [code] opt:142-145；[cam] RV:766。
- ColorButtonMenu 頁面複本 `OP_ADDF +1`：列表/動畫上限 `C1D63010 C1D631AC C1D5F200 C1D62A7C C1D63F8C C1D65B24`（BE float 15.0→16.0）、
  文字群組終點 `C1D66CBC` +33（500→533）、Effect 框種類 `C1D640A8` 15→16 [code] opt:126-128,146-149。
  其中後 4 個上限「少了就按 OK 後 16 被夾回 15 → 選回 OFF」[cam] RV:222-226。
- AEL 頁 `ColorModeAdvancedSettings` MenuMode Normal 範圍 `C1D6ED48` 12.0→16.0：**頁面複本無效**，改由 launcher 在映像原地寫（EXCL claim）
  [cam] RV:736-737；`UI_AND_STRINGS_BY_ADDITION.md:72-73`；rvL:719-726。

**(b) 程式 patch（launcher 寫，veneer→rv_resident stub）**
- getter：`C06C07CC/07D0` movw/movt 改指常駐 guitab（17 筆 = 原廠 16 + `{0xC,16}`），`C06C07D8` `E3A02010`→`E3A02011` [code] rvL:672-695；[cam] RV:156-159。
- **Stub A（GUI→enum，stub_ma/stub_mj）**：取代 `bl C06C0718` 於 `C0568950`（COLOR 鍵 OK）、`C056D028`（選單）、`C05818B8`（QS），
  及 `bl C06C07E8` 於 `C05689A8`（游標移動即時預覽/離開即選定）；記 pend（GUI15→16、16→17）與游標；QS（lr=`C05818BC`）一律 pend 0
  [code] rvR:427-458,52-57；[cam] stub_mj 必要 RV:723-729、QS 例外 RV:808-810。
- **Stub B（enum→GUI，stub_mb）**：`bl C06C0768` 於 `C0595734`（CM_COLFIX 通知）結果 15 且 flag → 16 [code] rvR:460-469。
  stub_ml：`C059DA1C`（LV_ColorMode）16→15，因 LV_ColorMode 16–25 是單色調色圖示 [code] rvR:523-529；RV:45。
- **Stub C（唯一寫入咽喉）**：`C0075CF4` `cmp sl,r6`（`E15A0006`，`FUN_c0075be8`：r4=item、sl=舊值、r6=新值；push 7 個 → sp 未對齊 → leaf）。
  item==`C31ACDC4`（色彩模式）時：新值≠0xC → flag 0；pend16 → 0；pend17 → 1；**生效列改變就把 guitab 裡 enum 0xC 的那幾筆 GUI 值重排成「生效列在前」並強制 Z=0 讓原廠發通知**
  [code] rvR:471-521；[cam] 不重排會被未知 enum→GUI 路徑以 15 拉回 OFF RV:210-217。
- ±框（Effect）：stub_ef `C0568A3C`、stub_en `C0595908`（v87 CM_COLAJ_Effect）＋`C05957B0`（v82 CM_COLFIX_Effect）[code] rvR:531-576；[cam] RV:723-737。
- AEL：飽和度 stub_sa `C056D5F8`/`C056D498`、stub_sn `C059588C`/`C05959E4`；對比/清晰鎖 0 共 8 個 bl（`C056D548 C056D3E8 C056D5A0 C056D440 C059581C C0595974 C0595854 C05959AC`）
  [code] rvR:578-640、build_rawview.py:59-75。
- 框字形 SA/GA：Thumb `C05E2200` `bl FUN_c05d6bb8`（關鍵影格設圖名）→ stub_ai，容器 id 0x177/0x178（CHAIN）[code] RV:862-871。
- 選單開關：ColorButtonMenu vtable v25/v26 `C0D119FC/C0D11A00` → stub_mo/mx [code] rvL:675-683。
- 其他（非清單）：增益/tone `C0313244`、`C032F728`、root+0x70 `C2F1A0D4`、root+0x08 `C2F1A06C`、DNG CM 4 字、關機 `C0088C60`（CHAIN）、PQ `C02B8E64`（CHAIN）。
- 存檔：v3/v4 存在 RAWV.BIN 自己的 32 B 記錄（v4 在 +48，寫前 `file_is`）；不再把 0x10–0x17 寫進韌體設定 [code] build_v3_rawview.py:16-22、test_v4_rawview.py。

**已實機的**：17 列出現/可選/OK 不跳回 [cam] RV:226、L4:417；4 列版（R1 R2 RC1 RC2，GUI 16–19、上限 19.0、文字 632、guitab 20 筆、pend=GUI+1、stub_ml 16..19→15）
R1↔R2 切換不跳回 OFF [cam] RV:656-668；SA/GA、AEL [cam] RV:736-740；v4 RAWV 在 12 sup 卡上 COLOR 的 RAW 正常 [cam] L4:417。
**已知 bug**：游標移到 RAW 再按 MENU 取消，值 0xC 但仍停在 RAW（摘要顯示 STD.）[cam] L4:418；AEL 頁首沿用前一狀態（「MONO. 黑白」）[cam] RV:741。

## 2. 從 1 列到 N 列

**已有先例**：4 列版已實機（上 §1），所以「全部掛在 enum 0xC、guitab 排生效列在前」的機制可延伸到 N 列 [cam→inf]。逐項：

| 項目 | N 列要做的 | 狀態 |
|---|---|---|
| guitab | 16+N 筆，額外列全是 `{0xC, 16..15+N}`；getter 筆數 `E3A020xx`（imm8，N≤32 → ≤48 OK） | [code] |
| 頁面上限 6 個＋Effect 框 `C1D640A8` | 15.0 → 15+N | 4 列已 [cam] |
| 文字群組終點 `C1D66CBC` | 500 + 33·N | 4 列 632 [cam]；它是什麼仍不明（條上沒有可見大字）[inf] |
| AEL MenuMode `C1D6ED48` | 12.0 → 15+N，**只能映像原地寫** | [cam] |
| AEL 可進與否 `C1D62AA8`（≤14 顯示 AEL）/`C1D62B0B`（==15 隱藏） | GUI≥16 無事件 → 沿用前一列狀態；從 OFF 往右移進第一個附加列時可能被藏 | **待驗** RV:677,683 |
| stub_ma pend | pend = GUI+1（GUI≥15）；QS 仍 0 | 4 列已 [cam] RV:656 |
| stub_ml | ≥16 → 15（不是 ==16） | [code] |
| CSV 三份 | 主檔首尾串接；`_EXCL/_EXCL2` 各加 N 個停用列（`_EXCL` 何時被用不明） | [code]/[inf] |
| 每列標籤＝圖示 | 每列要一個**不同的 donor 圖名**＋自己的 86×74 XCI | 見下 |

**GUI 16+ 撞號**：只在 LV_ColorMode（16–25 單色調色圖示）有意義，stub_ml 收掉 [code]；
副作用：ST_COLBKT（`C0594FB0`）、CM_DNGDEV（`C0597504`）的 enum→GUI 也會拿到 16+ [code] RV:215,220（目前未見問題 [cam]）。

**最難的阻礙（依難度）**
1. **自訂名稱 = 執行期產生圖示**。LUT 名稱只有相機上才知道（啟用清單在機內改）。需要：
   (a) N 個無人用的 donor 圖名：映像 2004 個 .xci 中，名稱不在 NBU 字串池也不在任何 .cvm 的約 496 個，`set_*` 有 17 個、86×74 的 19 個
   （`set_flash_1/2`、`set_cropZoom_*`、`menu_isoAuto_*`…）[code]；但 `cropZoom_1_24` 這類可能由程式拼名使用 → 每個 donor 要逐一確認 [inf]。
   (b) 機上組字：XCI = 頭 0x33 B + LZ4 frame，16bpp（低位元組亮度、高位元組 alpha）[code] `projects/open-gate/build/xci.py:1-23`；
   用 LZ4「未壓縮 block」（長度最高位）就不必在機上壓縮——**韌體解碼器吃不吃未壓縮 block 未驗** [inf]。字型建議主機端預先點陣化 ASCII（約 25 KB）放 LUT.BIN。
   (c) 圖片依名稱快取＋引用計數（`FUN_c05dfe88`/`FUN_c05d8910`）；同名換內容會看到舊圖 [cam] RV:787-789、[code] RV:819；
   因此啟用清單改變時要在選單關閉後才換內容，且 donor 名不能出現在當下開著的其他畫面 [inf]。
2. **FPUI 上限**：`fpui_stock.c` 每區塊 `UIA_MAX_SLOTS 8`（CSV_ADD 次數）、`MAX_FILES 8`、`fv_handler` 表容量 32 [code] fpui_stock.c:27,89；opt:41。
   N 列 × 3 CSV 超過 8 → registry 不能用 FPUI 區塊加列，要自己組三個 CSV 並自己管重導（見 §4）。
3. **單一 enum 多工的同步漏洞**（全部列都是 0xC + 我們的狀態）：MENU 取消 bug [cam]；`MenuColorStateProc::v2`（`C0489D48`）依序以 enum 0..15 呼叫 setter `FUN_c005c958` 再還原，
   第一次寫入就清掉 flag、最後寫 0xC 時 pend=0 不恢復 [code] blk_c04.c:104745-104771（觸發條件未知）；QS 以 GUI 15 重新同步 [cam] RV:808；
   C1–C3 自訂模式可能整組換 bank、不經 setter [inf] RV:48,94（存檔有 7 組設定、組號 obj+0x58CC，色彩在第 0 組 +0x130 [code] RV:838-839）；PTP/shell 的 `SetColorMode` 會經 setter 清 flag [code]。
4. **N 可變**：清單長度要在開啟前定好。ColorButtonMenu 每次開啟重新解析 [cam]，所以在 v25（開啟）前改頁面複本上限與 CSV 複本就能動態 N [inf，待驗]；
   但 `C1D6ED48` 是映像原地字，固定寫成最大值即可（Normal 範圍放寬不影響原廠 ≤12）[inf]。
5. **QS**：QS 色彩 holder obj 324 `CM_COLAJ_ColorMode` max 15、loop [code] `research/ui/CUSTOM_QS.md:281`；QS 很貴（OG3K 315 筆 QS 記錄）。第一版不做，QS 顯示 OFF。

## 3. ±框（Effect）與 AEL

**寫入路徑** [code]：框上下 → 回呼 `FUN_c0568a00`（blk_c05.c:77580；目前模式 enum==0xE DUO 時改走 `FUN_c0568a90` 的 Scheme）
→ `C06C0D20`（UI→存值，表 `C2E414FC`：存值 −5..+5 以 s8 存，UI −5..+5，11 格）→ vt+0x204
→ `MenuItemColorModeEffect__v9`（`C009A790`，blk_c00.c:114140）：**目前模式是 0xC（OFF）就不寫**，否則寫一個 byte
→ `__v3`（`C009A7F8`）套到畫質結構 PQ+0x2A8（DUO 則 PQ+0x278）。
通知：v87 `C0595908`（CM_COLAJ_Effect）、v82 `C05957B0`（CM_COLFIX_Effect）經 `C06C0D70`（存值→UI）[code] RV:690；rvR:564-576。

**存放處（逐模式）** [code] `FUN_c00b46f8`（blk_c00.c:138937-139018）、bank=`FUN_c00897e8`=`0xC31AE3B0`+0x4F0C（或 +0xA7D4）：
每模式一筆 8 B `{Effect s8, Contrast, Sharpness, Saturation, Toning u32}`；
enum 0..0xB → bank+0x130+enum·8（bank A 絕對位址 `0xC31B33EC`…）；enum 0xD/0xE/0xF → bank+0x844+(enum−0xD)·8；
**OFF(0xC) → RAM `0xC31CC020`（不存檔，第一次存取清零）**。存取器族 `FUN_c00b58e8/5938/5988/59d0/5a20`（Effect/對比/清晰/飽和/Toning），
參數≠0 時讀 bank+0x654+n 等另一組槽（推定色彩包圍）[code/inf]。bank 關機整塊寫 NAND [code] RV:832-840。
飽和度存值 −10..+10（表 `C2E415A4`，UI×2）[code]。

**OFF 灰掉**：框是否可操作由 NBV 規則 `CBM_BKTMonochrome`，只對 GUI==15 成立；規則開機前已編譯，改字串無效 [cam] RV:707-709。
→ GUI≥16 的附加列框本來就可操作 [cam] RV:709-710。框種類 `Effect or Scheme`（`C1D63F1F`）0–12/14–15 Effect、13 Scheme，16+ 無事件 → 需 `C1D640A8` 上限一起抬 [cam]。
框的 ±/數字是版面記錄裡的圖片（關鍵影格依數值換圖名），不是文字 → 顯示只能是 −5..+5 或像 SA/GA 一樣經 stub_ai 換成其他現成字形 [cam] RV:850-871。

**LUT 列重用為強度（不污染原廠值）**：附加列的 enum 是 0xC，原廠寫入本來就擋 → 只要照 RAW View 的 stub_ef/stub_en 模式：
stub_ef 攔 `C0568A3C` 的換算，把 UI 值存進 **registry 的「目前生效列」槽**（LUT 則寫回 LUT.BIN 該份的強度）、夾範圍後以 `PUBLISH C0593F30` 把 AJ/FIX 拉回；
stub_en 在模式 0xC 且附加列生效時回傳該列的值。原廠 16 模式的記錄與 `0xC31CC020` 都不會被寫 [code]（RAW View 已證）[cam]。
建議映射（待使用者定）：沿用 LUT 現行五段 0/25/50/75/100%（fpSup/lut/README.md:50）→ **±0 = 100%、−1..−4 = 75/50/25/0%**，+1..+5、−5 夾回。
新列預設 ±0 = 100% 自然。若要 10% 一格可用 −5..+5 全段，但數字不直觀。

**AEL「更多選項」= ColorModeAdvancedSettings**（NBU `C1D66D7D–C1D8671E`，無 CSV；`UicGuiMenuColoModeAdvanced` blk_c05.c:81279）[code] RV:675。
`MenuMode` 依 CM_COLFIX_ColorMode：≤12 → Contrast/Sharpness/Saturation、13 DUO → Contrast/Sharpness、14 MONO → +Toning；刻度 −1.0..+1.0 [code]。
GUI 16+ 不符任何事件會卡死（上下、MENU 無效）→ 要 `C1D6ED48` 放寬 [cam] RV:736-737。OFF 沒有 AEL 頁 [code] RV:677。
LUT 列建議：對比/清晰/飽和全部鎖 0（RAW View 的 stub_zc/zs/znc/zns + stub_sa 模式）或由 registry 依列交給登記者處理（RAW 用對比=曲線、飽和=矩陣程度）。

## 4. 建議設計：LUT sup 擁有的 color list registry

**原則**：所有 COLOR 清單位置只由 LUT.BIN claim（RAW View/bCOLOR 不再 claim 任何清單站點）；登記者只提供「列」與回呼。
LUT.BIN 先於 RAWV.BIN 載入（v4 依檔名字母序）[code] L4:24；用 `svc->provide(CLST_ID, &api)`，RAWV 以 `svc->find` 取得（先 provide 者勝）[code] sloader4.h:108-110。

```c
struct clst_row {            /* 常駐在登記者區塊內 */
  uint32_t owner;            /* sup_id */
  const char *label;         /* 圖示上的字（≤8 字元） */
  const void *icon;          /* 可選：現成 XCI；0 = registry 用內建點陣字組 */
  int  (*on_select)(void *arg, int active);   /* 生效/失效（setter 咽喉內呼叫，只能設旗標） */
  int  (*box_get)(void *arg), (*box_set)(void *arg, int ui);   /* ±框；0 = registry 鎖 ±0 */
  int  (*ael)(void *arg, int item, int ui);   /* 可選：AEL 三項；0 = 鎖 0 */
  void *arg;
};
int clst_add(const struct clst_row *r);      /* 回 row handle；GUI 編號由 registry 決定，不給登記者寫死 */
int clst_active(void);                        /* 目前生效 handle 或 -1 */
```

**hook 最小集合（全在 LUT.BIN，一次 claim）**：getter 3 字、GUI→enum 4 處（含 C05689A8）、enum→GUI 2 處（C0595734、C059DA1C）、setter `C0075CF4`、
±框 3 處、AEL 12 處（或只鎖）、ColorButtonMenu v25/v26、`C05E2200`（只在需要字形替換時）、`C1D6ED48`（原地）、取檔重導 `C05E5BEC`（SHARED_UI，與 Res-Custom 共用）。
RAW 專屬的增益/tone/矩陣/DNG/PQ/關機站點留在 RAWV.BIN（不屬清單）。

**清單組裝**：registry 自己在常駐區產生三個 CSV 與 N 個圖示，在 v25（開啟）時依當下 N 改頁面複本上限、更新重導表；
不用 FPUI `CSV_ADD`（上限 8）。donor 圖名表固定 32 個、build 時逐一確認無人用。生效狀態只存 LUT.BIN（列以 owner+key 記，不以 GUI 號記）。

**修已知漏洞**：v26（關閉）時以 CM_COLFIX 的 GUI 值重新對齊生效列（修 MENU 取消）；閒置輪詢檢查設定字==0xC，否則清生效列（涵蓋 C1–C3、PTP、`MenuColorStateProc::v2`）。

## 5. 步驟與每步上機要驗的

| # | 做什麼 | 上機看什麼 |
|---|---|---|
| 0 | 讀現有卡：LOAD.LOG 確認 RAWV 40 claims；列出 donor 候選 | 用 `gui image log` 確認候選圖名在主要畫面/選單從不載入 |
| 1 | LUT.BIN 以「RAW View 現行 1 列」邏輯接管（RAWV 改成不 claim 清單站點，經 find 登記）；行為應與今天逐項相同 | 第 17 列出現、選/OK/離開即選定、SA/GA、AEL、QS 切解析度不掉；LOAD.LOG 無衝突 |
| 2 | 修 MENU 取消（v26 對齊） | 游標移到附加列按 MENU → 回原模式；摘要與實際一致 |
| 3 | N=4 固定列、固定內建圖示（LUT1..LUT4） | 4 列可捲、可選、生效列切換不跳回 OFF；從 OFF 往右進第 1 列時 AEL 提示是否出現（`C1D62AA8` 問題） |
| 4 | 機上組字 XCI（未壓縮 LZ4 block）＋donor 重導 | 圖示正確、與原廠同風格；改名後重開選單看到新字（快取問題） |
| 5 | ±框 = 強度（stub_ef/en 一般化），寫回 LUT.BIN | 框只停在 −4..0；切列顯示各自的值；原廠模式的 Effect 值不變（讀 bank+0x130.. 前後比對）；跨關機保留 |
| 6 | 動態 N（啟用清單改變後下次開選單生效） | 增刪列不需重開機；N=最大值時捲動/首尾相接正常 |
| 7 | AEL 鎖 0 / 交給登記者 | LUT 列 AEL 頁可進可退、數字被拉回；RAW 列維持對比=曲線、飽和=矩陣 |
| 8 | （之後）QS | 暫不做；確認 QS 顯示 OFF 且操作 QS 選原廠模式會正確清掉附加列 |

每步都先比對 claim 數與 LOAD.LOG，並在 `_EXCL` 狀態（觸發條件待查）下各看一次清單。
