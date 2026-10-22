---
name: fp-native-ui
description: SIGMA fp (Ver.5.02) 原生 UI 的操作知識(要和別的 sup 合併、用「添加」改選單時另見 fp-ui-add) —— 選單列 CSV (.cvm) 怎麼改才會畫出來、選得到;反灰與「因以下的狀態無法選擇」對話框從哪來;選到之後值會不會被設定層截掉;row / internal / export 三種列舉與配對表;NBU 記錄什麼時候被讀;QS 為什麼貴;上機怎麼量才不會被舊畫面騙;以及**在設定頁加一整列新設定項**(執行期換掉整頁 NBU、私有 app 變數、只存在記憶體的開關、donor 列怎麼挑、popup 的箭頭/「更多選項」從哪來、選單資料併進 fpSup.BIN、私有字串走共用 FSPL 字串池、跟 OG 合併在同一張卡;外部卡反推的:畫字時依模式換文字的 hook 點、讓原廠藏起來的列現身、搬列時 popup 要一起移)。凡是要加選單列或新設定項、加私有字串、讓兩個會改 UI 的 sup 合併、開反灰、改格率/位元深度/解析度清單、追「看得到選不到 / 選得到看不到 / 選了被改回去 / 切到那頁空白、游標卡住 / 合併後別人的選單壞掉」時先讀這份。
---

> **設定區風險（2026-10-04 更新）**：原廠在 loader 前讀取持久設定；
> 不支援的值可能使開機或選單失效，拔卡本身不會清除該值。使用者已指出現在有還原手段，
> 因此不再把這類故障描述成不可恢復。上機前確認會保存的值、可能症狀及適用的還原流程；
> 未確認還原條件時，優先把自訂狀態留在 RAM。240 fps 與 14-bit 的處理不同，
> 詳見 `research/SETTINGS_AREA_FIRST_RULE.md`。
> *(Stock firmware reads persistent settings before the loader. A recovery
> method now exists; check its applicability before a live trial.)*

# fp 原生 UI —— 改之前先讀

位址只對 **Ver.5.02**(`out/MAIN_c0000000.bin`)。每一條都標了證據等級:
**[實機]** 在相機上量到、**[離線]** 反組譯或模擬執行、**[推論]** 沒驗過。
推論不要當結論用。

詳細文件在 `research/ui/`(入口 `UI_NAVIGATOR.md`)與
`projects/open-gate/notes/IMX410_FULL_DESIGN.md` §8。這份是濃縮的操作面。

上機範圍以本次對話已授權的操作為準；讀記憶體先核對位址與目的，
`mem set`、寫卡、deploy 要有該次操作的授權，已授權的步驟不重複請示。
截圖/寫卡/Fast 卡的程序看 `fp-camera-control`、`fp-merged-card`、`fpSup/.claude/skills/fp-*`。

---

## 1. 核心:位置不重要,**讀取時機**才重要

| 你改的東西 | 什麼時候被讀 | 執行期打 RAM 有效嗎 | 證據 |
|---|---|---|---|
| enum↔state / row↔enum 配對表 | 每次求值 | ✅ 立刻 | [實機] |
| `.cvm` CSV **內容**(原地、不超過原槽) | **開那一頁時** | ✅ 退出選單再進去就生效,不用重開機 | [實機] |
| NBR 目錄項(repoint 資料位移/長度) | 只在第一次查找 | ❌ 無效 | [實機] |
| NBU 集合索引 `+0x0C`(集合改指向) | 開機 | ❌ 無效,連切語言重建 UI 都撐過去 | [實機] |
| NBU 記錄內容(如 controller max) | 該資源集被解析時;`B2_5` 是開設定頁才解析 | ✅(`B2_5` 這組) | [實機] |
| 解析後的 heap 物件 | —— | ❌ 螢幕物件一釋放就沒了 | [實機] |
| XCI 圖示 | 按**名字**快取 | ⚠ 要新名字才會重新解碼 | [實機] |
| **整頁 NBU**(MainB2 這種設定頁)的來源位移、字串池指標 | **每次顯示那頁時重新解析**(UI 資源快取一次只留一頁,打開選單就丟掉) | ✅ 改 reader / 執行期項目,整頁換成自己的(§8) | [實機] |

- AutoRun / Fast loader 都在開機約 8 秒後才跑,**UI 已經載入**。從卡片沒辦法更早
  (`0xC03DA420` 就是啟動 AutoRun 的那條 `bl`)。[實機]
- 所以「原地改」是執行期唯一有效的形式。塞不下就**騰空間**(拿掉欄位),不要搬家。

## 2. 選單列 = CSV,規則全部是實機付過學費的

`.cvm` 在 NBR 容器 `0xC0D22400` 裡;目錄是 BE `{fnv1a(path), 名稱位移, 資料位移, 長度}`,
描述子長度欄在 **+12,big-endian**。工具:`research/ui/tools/nbr_stock.py`
(`list --ext cvm`、`show <path>`、`menu <path>`)。

1. **原地寫**在該資源自己的資料位址上。
2. **結尾 CRLF 不能省** —— 少了,最後一列不被 parse、整列消失。[實機]
3. **要騰空間就整欄拿掉(連表頭)**,不要留空格(`,,`)。留空的列畫不出來。
   `IMAGE` 欄最安全;欄位由表頭決定,**任何解析 .cvm 的程式都要依表頭找欄,不能寫死索引**。[實機]
4. `TEXT` 可以直接寫字面文字(`240 fps`),不用動 `.nloc`。[實機]
5. 列數變了要改 **controller max = 列數 − 1**,BE float,在 tag `0x1000E` 記錄的 **record+0x20**。
   不用猜:`python3 research/ui/tools/nbu_probe/nbu_format.py maxima B2_5 --rows N`。
   位址可能沒對齊(`B2_5_2` 的在 `0xC1A690D7`),`mem_set` 只寫字 → 讀改寫。
   同一列數常有好幾筆(excl 變體、CINE/STILL),只改一筆可能只在某些情境生效。[實機]
6. 比原廠短就 **NUL 補到原槽長**,並把描述子長度改成新長度。[實機可用]
7. **popup 的列是模板複製的,不是固定子物件。** `List → ListItem` 一個 ListItem 依 CSV 列數複製,
   但 **ListItem 的 tag `0x1000E` prop 3 第二個 float = 列實例數**,原廠全機一律 = max(8, 列數)
   (9 列→9.0、11 列→11.0、12 列→12.0)。列數超過它,多的列沒有實例:畫不出來、游標也到不了。
   位元深度 4 列 < 8 所以沒事;格率 10 列要把 9.0 改 10.0。[離線:全機 93 個清單掃描]
   ⚠ 舊說法「格率 popup 只有 9 個文字子物件」是錯的 —— 那 9 個 IconText 是**收合摘要**。
8. **kind 16 的 popup List(B2_5 那種)每一列要有一組游標事件**:`controlValueEvent`(值 == v,事件名 "0v")
   + 同 key 的 `controlFocus`(焦點移到名叫 "v" 的列實例)。沒有那一組,游標「到得了」但畫面完全不動、
   看不到那一列。List 物件記錄的 w0 = 元件數,加一組要 +1;配置標頭的 controlValueEvent / controlFocus 容量各 +1。
   多出的位元組可放在任一記錄尾端當零填充(原廠共用收尾 `C05E7B06..C05E7B1A` 會跳過)。[實機 r5]
   ⚠ 原廠 11/12 列的 popup(kind 9/12)用 app 變數 `ListFocus` 驅動,不是每列一組,不能照抄。
9. **一個清單的「上限」不只一個,全部都要跟著列數改。** 格率選單有三個:List `0xC1A74B44`(游標範圍)、
   MenuItem_Select `0xC1A73D63`(摘要)、**IconChange `0xC1A744F5`**。漏改 IconChange 的症狀很隱蔽:選單看起來正常,
   但原廠通知把列寫回 GUI 變數時被夾回 8,再觸發一次 setter 回呼(2026-10-01 實機,RAM 改 9.0 即解)。
   用 `nbu_format.py maxima` 列出同列數的所有上限,逐一確認。[實機]
10. **GUI 變數的 setter 回呼可能不只一個,而且名字相近的變數會讓你掛錯。** `MV_FrameRate` 有兩個回呼
    `FUN_c057a6f8`、`FUN_c05821b8`;旁邊的 `FUN_c057a750` 是 `MV_Binning`(轉換表槽 +0x64,格率是 +0x60)。
    以反編譯源碼的 `FUN_c0560fb0/c0561080(obj, s_MV_xxx, FUN_yyy)` 列出**全部**註冊,並有測試釘住。[實機:掛錯兩次]
11. **執行期找路徑用 RAM 紀錄器,不要猜**:`projects/open-gate/build/diag/getter_log.{S,py}` 掛在表取得函式,
    記錄呼叫者、列/值、當下記號與表順序、29 個堆疊字;`--go/--reload/--read/--off`。sp 比較深 = 巢狀在前一筆裡。[實機]

症狀對照:
- 列沒出現 → CSV 形式 / 寫入沒進去(先逐字讀回)/ 沒退出重進。
- 列出現、游標到不了 → List 的 controller max。
- 列沒出現、游標也到不了,但 CSV 形式正確 → ListItem 列實例數(規則 7)。
- 選了之後收合摘要空白 → enum→state 轉換器沒有那個值(§4)。

**最小實驗**:先把既有一列的 TEXT 換成等長的 `ZZZZ`,證明 CSV 真的被讀,再談加列。一次只動一個變因。

## 3. 反灰、「無法選擇」對話框、值被改回去 —— 三件不同的事

2026-09-30 用 A/B 卡 + RAM CSV 兩點對照實機定案
(`projects/res-lab/validation/20260930-rate-reject-ab/PLAN.md`)。

### 3a. 介面層:反灰 + 對話框 = CSV 變體的 `Enabled,Enabled2`

- 格率清單有六個變體:`B2_5_5`(全開)、`_excl`(到 29.97)、`_excl2`(24)、`_excl3`(25)、
  `_excl4`(59.94)、`_excl5`(100)。位元深度有 `B2_5_2` / `B2_5_2_excl`。
- 一列 `1,2` = 正常可選;`0,0` = 反灰,按下去跳原廠「因以下的狀態無法選擇:位元深度 / 記憶媒體」。
- **挑哪個變體 = app 變數 `EXCL_FrameRate`(0..5)**,頁面用它當 `ExclList` 群組的 apply-frame,
  在 List 的 `model` clip 裡挑 `B2_5_5` / `_excl` … `_excl5`。位元深度同理:`EXCL_CinemaDNGQuality` → `B2_5_2` / `_excl`。
  **[實機 2026-10-02,SD]** 變體**跟著解析度走**:

  | | CUSTOM | FHD | UHD |
  |---|---|---|---|
  | `EXCL_FrameRate` | 0(全開) | 4 | 3 |
  | `EXCL_CinemaDNGQuality` | 0 | 0 | 1 |
  | 互斥類別 0x19 快取(`0xC3768B88`) | 0 | 3 | 4 |

  所以 **CUSTOM 原廠就挑全開**,不必改 CSV;把六個變體都改全開(`WITH_RATE_ALL_OPEN`)會讓 FHD/UHD 也全亮。
  ⚠ 舊說法「變體由 NBU 腳本依媒體決定、`C04A1120` hook 無效」是錯的;9/30 那次 hook 無效較可能是
  互斥管理器只在依賴的設定變了才重算(見下)。
- 互斥管理器(單例 `0xC3766AEC`):每類別一個 provider(`+(類別+0x7BD)*4`)與快取狀態(`+0x2038+類別*4`);
  設定變了只重算依賴表(`+4` 起,每筆 0x90 B:{鍵, 類別…, -1})列出的類別,**狀態有變才**呼叫通知
  (`FUN_c049ef18` 依類別呼叫通知物件 vtable,`0x17` → `+0x6C4` 寫 `EXCL_FrameRate`…,decomp 的 vN 名稱有錯位,以實機為準)。
- 讀 app 變數不用呼叫函式:`tools` 見下方「讀 app 變數」。
- **打開反灰 = 把變體裡的 `0,0` 原地改成 `1,2`**(等長,開頁重讀)。[實機:SD + 12-bit 下 100/119.88 變成可選]

### 3b. 設定層:選得進去不代表值留得住

- 值送進去後,原廠正規化器會依 SD / 12-bit 等條件把格率壓到上限。
  格率 menu item 類 `MenuItemMovieFrameRate` 的 vtable 在 `0xC07422A0`:
  slot 1 `C00A8958` = 依賴的六個設定(對話框列出的來源)、
  slot 3 `C00A83B8` = internal → export(給收合摘要)、
  **slot 8 `C00A84E0` = 正規化器**(上限 r4 在 `C00A87E4` 被比較,rank 表 `C0063548` 以 internal 為鍵)。
- 實機兩點:只開 CSV、沒有正規化器 hook → 選 119.88 變 **59.94**;
  r2(`C00A87E4` hook,CUSTOM 下放行)→ **保持 119.88**。[實機]
- **所以「全開」要兩層一起做:CSV 變體開介面 + 正規化器 hook 開設定。** 只做一層會看起來像另一層壞了。

### 3c. 其他格率清單來源(不管反灰)

- `C049A788`:依 class id `0x19` 回傳允許清單(`C0CDAC78..ACD8`,2/3/4/7/8/9 筆)。
  class 由 `C049ED20` **每次即時呼叫** provider `C04A1120`(沒有快取)。消費者只有這支和 `C04C7678`(位元遮罩)。
- QS 值清單 `C05332A8`。

## 4. 值鏈:三種列舉,不要混

一個選單值會經過三個**不同的**編號空間:

```
row(第幾列)  --C06BDB00 表 C2E40224-->  internal(設定值)  --C00A8818/C0063520-->  export(picker/摘要)
```

- 轉換器是 326 支同形狀的葉函式:`movw r2,#lo / movt r2,#hi / str / mov r2,#count / bx lr`。
  **搬表 = 改那三個立即值**,不用 hook。工具 `research/ui/tools/enum_converters.py`。[實機]
- 格率:stock rank 表 `(internal, export, rank)` 在 `0xC0735F60`;
  合法表 `(internal, export)` 在 `0xC0742250`;選列表 `(internal, row)` 在 `0xC2E40224`;
  摘要表 `C06CB6D0 → C2E44EE4` 是 **export → summary state**。
- 240:**row 9 → internal 8 → export 11 → 字串 `240` → 鍵 `CUST240` → summary state 9**。
  ⚠ export 5 會進原生 assert(`C043CAF0`);internal 5 是 59.94。兩個都不能拿來當 240。[離線]
- internal 0 = 隱藏的 15 fps,保留在 row 10。

## 5. QS 是另一個世界

QS 沒有 CSV,全在 NBU 記錄裡,而且同一群組在 `QS_CINE` 裡重複 8 次。
「解析度多一個狀態」掃出 218 筆記錄,**152 筆在 QS**,Settings 只有 6 筆。
一個新狀態要同時補影像陣列 `0x1000B`、每個伴隨屬性(visibility / rectangle / position /
collapse / cursor / timeline)、配置標頭 `0x10002`,少一個圖磚就疊在一起。
**只要不需要 QS 圖磚,成本就從 ~360 筆掉到幾個寫入。** 位元深度沒有 QS 項。

## 6. 上機量測:怎麼不被騙

- **CSV / NBU 改完要退出選單再進去**;idle 畫布要半按 S1 才刷新(否則拍到舊畫面)。
- **讀設定值要等配方重算**:選完立刻讀可能還是舊值,約 3 秒後連讀兩次一致才算。[實機 2026-09-30]
- `gui image log` 跨幀,第一次重繪帶著舊狀態的圖示:關 → 改 → 等 3 秒 → 開(丟掉)→ 關 → 清 log → 開。
- 截圖:`key CAPTUREON/CAPTUREOFF` → `\DCIM\100SIGMA\SS__nnnn.JPG`。
  QS overlay 要用 `display capture <path> 3 2`(`retries=0`),主層是 ARGB4444。
- **差分優先**:一個觀察點不算證據。要回答「是哪一層」就做只差一層的兩張卡
  (`imx410_plan` 的 `WITH_RATE_NATIVE` / `WITH_RATE_UI` / `WITH_RATE_LV` 可在建卡時關掉;
  AXIS 要沿用對照卡的,否則多一個變因)。
- **先跟使用者確認症狀本身。** 2026-09-30 我把「反灰列被拒」誤記成「連 23.98 都被拒」,
  追了一整輪不存在的問題。追之前把「哪一列、做了什麼、看到什麼」重述一次給使用者確認。

## 7. 240 目前狀態(2026-09-30)

| 項目 | 狀態 |
|---|---|
| 值鏈 row 9 → internal 8 → export 11 → `CUST240` | [離線] 以原廠函式實跑通過 |
| 設定層放行(正規化器 hook) | [實機] 119.88 保持,240 未單獨驗 |
| popup 第 10 列 | ✅ **r5 實機顯示 `240 fps`**。缺的是 List 4439 對值 9 的「controlValueEvent + controlFocus」(見 §2 規則 8);ListItem 10.0 也一併改了,單獨改它沒有可見差異 |
| **選下第 10 項** | ✅ **做法 1 實機成功（r9 + RAM 的 IconChange 9.0，2026-10-01）**：第 10 列交給原廠 119.88，記憶體記號 `RATE240`（ROLE 6/7 掛兩個 `MV_FrameRate` 回呼）+ `imx410_fmt` 120+記號→240；關選單後 FPSLATCH 239.76，選回 119.88 也正確。原廠設定只存 119.88。r10（IconChange 寫進 build）實機再驗通過：兩向切換正確；**240 已實際錄影，使用者確認結果良好** |
| 收合摘要 state 9 | r2 借用 Icon 4458 當第 10 個 IconText,但 MenuItem_Select `0xC1A73D43` prop 0x12 仍 8.0(規律 max(7, 子物件−1))。r4 改 9.0 [離線] |
| LV 待機格率文字(四套 LARGE/MEDIUM) | [離線] |
| QS 240 圖示 | ❌ 未做 |

**摘要的另一條規律**:MenuItem_Select 的 prop 0x12 = max(7, IconText 子物件數 − 1)(全機 30+ 項吻合)。
加摘要子物件就要跟著加它,否則新狀態被夾掉;r2 的離線測試直接把 9.0 餵給 setter,繞過了這個上限。

## 8. 加一整列新設定項:執行期換掉整頁(fpLossless,2026-09-30～10-01)

在 SHOOT 第 2 頁(CINE)「音訊記錄」下面加 `Lossless RAW 關閉/開啟`,**不用 hook**。
值是私有 app 變數,只在記憶體、每次開機 0,不寫設定區。程式:`fpSup/lossless/native/menu_page.c`,
頁面產生:`fpSup/lossless/menu/build_menu_candidate.py --profile audio-toggle`,
打包:`menu/pack_menu_file.py`。完整紀錄:**`research/ui/NATIVE_ROW_AND_SHARED_POOL.md`**
(另見 `projects/lossless-sup/notes/PROGRESS_20260930.md` §19、`PROGRESS_20261001.md`)。

### 8a. 執行期結構(開機後才有,位址每次開機不同;Ver.5.02 從相機讀的)[實機]

```
[C37B7048]            = UI app(C055F0F0 的 GUI 物件 +0)
app+7C 畫面 vector     : +4 數量(221)、+10 陣列;screen +04 app、+08 名字、+0C 快取 root、+24 共用 reader
reader(所有頁共用一個): +04 游標、+10 字串池長度 176152、+14 字串池 C18C0474、+20 NBU 總長、
                        +24 NBU 基底 C18C0460、+A8/+AC 44-byte 執行期項目(+04 名字、+08 頁面位移、+18 arena)
app+888 → +60          = app 變數 registry
```

- **MainB2 開機時就被快取**,但一打開選單就被釋放,顯示時由 `C05E82F1` 重新解析:
  找名字相符的執行期項目 → `reader+04 = entry+08` → 從 `reader+24 + 位移` 讀記錄,字串以 `reader+14` 為基底。[實機]
- 所以:**把 `entry+08` 改成 `(自己的頁 − C18C0460) mod 2^32`**,下一次顯示就讀你的頁。
  私有字串**不要自己換 `reader+14/+10`**:走共用字串池(§8e),別的 sup 才能一起用。
  位移繞一圈(0x8389…)沒問題;頁面放在自己配的 USER 記憶體、永不釋放即可(UI 會借用字串)。[實機]
- 動手前逐項比對原廠值(pool、長度、NBU 基底、項目位移 0x76FF04),不符就全部不寫。
- **子頁也適用(B2_5,2026-10-02 實機)**:B2_5 執行期項目位移 `0x19C130`(頁 `0xC1A5C590`),
  RAM 改成 B2_6 的 `0x1B8E9B` 後退出重進「錄影設定」→ 顯示音訊頁內容;改回即恢復。
  所以「依狀態切換整頁」只要改這一個字(例如 CUSTOM 時指向私有頁)。[實機]

### 8b. donor 列怎麼挑 —— **要用同一頁的列**[實機二分]

用四張只換 FPLMENU.BIN 的卡二分(頁面補零到等長,parser 遇到 `FFFFFFFF/8` 就停):

| 變體 | 結果 |
|---|---|
| 原廠 MainB2 從自己的 RAM 載入 | 正常 → 換頁機制沒問題 |
| 原廠頁 + 擴充後的配置標頭 `0x10002` | 正常 → 附加 budget 沒問題 |
| MainY4 的兩選項列(就算 CINE 也設成隱藏) | **第一次切過去空白、再切一次看得到但游標卡死**;每次進選單 GUI log `0xC055F8D4 ERR 10000009,4` |
| 同上但綁回原廠變數 | 一樣壞 → 跟私有變數無關 |
| **同頁「音訊記錄」列(B2_6)的複製** | 正常 |

- **別頁的列搬過來,連隱藏都會讓整頁壞掉**,原因未追(離線結構檢查全過)。先用同頁的列。
- **別頁的「邏輯物件」也不行,而且是安靜地不行**(2026-10-03,B2_5 解析度 CUSTOM 跳頁)。
  MainB2 的 `JumpEvent`(32736,不畫東西)整個搬到 B2_5:頁面正常、不凍結,但它的事件**從不觸發**——
  動畫 on-visible、值事件、固定值寫入(d3)全都沒反應。改用本頁 `ControlModeChange`(3114)的副本、
  動作也從本頁記錄複製(Right_Help 的 controlAppState、popup Up 的 changePropertyByControl),一次就成功。
  **新物件、新動作一律從同頁的記錄複製**;要跨頁時把它當未驗證的假設,先做一張只測它的對照卡。
  可用做法(r23):popup ListItem 的 Right 加 `changePropertyByControl(隱藏物件.controlValue.value, "value")`
  ——ListItem 實例自己的值 = 列號 + 1——隱藏物件 `controlValueEvent` type 0x12(value-change + value-equal)
  == CUSTOM+1 → `controlAppState` sync-request "<私有頁>"。程式:`projects/open-gate/build/sl_b25_page.py` `lab_jump`。
- 動作記錄 +28 的數字不是記錄順序(B2_5 popup Up:focus 3 排在 change 2 前面),可能是執行順序;
  插新動作時放在前後兩個原廠數字之間。
- `controlValueEvent` type 是旗標:0x01 on-visible、0x02 value-change、0x04 increase、0x08 decrease、
  0x10 value-equal、0x20 greater、0x40 lower、0x80 range(字串表 `0xC2E029EC`)。
- 上機自測(部署、重開、送鍵、截圖、導航地圖):skill `fp-ui-selftest`。
- **繪製順序:記錄越前面越晚畫(在上面)**。B5_4_2 的 BG 5039 在資訊區 35533 之後才不會蓋住它;
  把背景放到前面,整塊就被蓋掉(r30)。插新物件要想清楚它在誰的前面。
- **即時顯示一個數字(r31 實機)**:原廠 `drawImageLayout` 數字欄(B5_4_2 Width 39544 這種,rules=2
  QS_Digits:只有 0-9 . 等,沒有 × : %,符號要獨立的圖片物件)+ `appVariableEvent` 綁 `text` 到
  **整數** app 變數(以 %d 顯示);原生程式用 `C0593F30(0, 名字, 值)`(ARM,GUI 佇列,原廠 668 處)
  寫值,畫面當下更新。值改變的時機:`C0560FB0(0xC37B7048, 名字, Thumb 回呼)` 訂閱私有變數的寫入
  (綁定上下文 {app,0,1};回呼 `cb(描述子, x)`,新值在 +8,回傳 0)。同一行的 flexBox 會自動排位置,
  複製出的欄位不用自己算 x。程式:`sl_lab_page.panel_line`、`sl_menu/sl_modes.c` `panel()`。
  `drawImageLayout` 的細節(查表規則、字元表、寬度綁定):背景調查報告摘要在 `sl_lab_page.py` 的 PANEL_* 註解。
- **小數(或任何字元表內的字)用字串變數(r38 實機)**:登記型別 2(`C05DB308` 經 `C05D9B40` 複製初始字串,
  初始值不能是 0),同一個數字欄的 `appVariableEvent text` 綁定不用改;寫入 `C0593FE0(0, 名字, 字串)`(ARM)
  只把**指標**排進 GUI 佇列 → 字串放常駐緩衝區(struct 裡)。"0.32" 這樣顯示正確,欄寬照字數 ×34。
  原生 blob 的 static 函式會被加前綴,**不要和 struct 欄位同名**(`rwzm_text` 撞名編不過)。
- **字串變數 → `drawText`(r43 實機,Data rate 列)**:綁定要帶 **component-id = drawText 的區域編號**
  (原廠 `CM_WBText` 的形式:欄位 mask `0x2f`、58 B)。數字欄用的 `0x2b` 形式(沒有 component-id)只找得到
  drawImageLayout,綁在 drawText 上畫面空白(r41/r42)。drawText 欄位:`text` = 4 B 位移 + **1 B 旗標**
  (32..36),`horz-align` u32(37..40),`rect` 16 B;拿掉 horz-align 就是原廠摘要的預設靠右(53 B)。
  切記錄要照 schema 的實際寬度,切錯一個 byte 就整筆無聲失效 —— 測試要釘長度與 rect。程式:`sl_lab_page.rate_line`。
- **動態框線(r47 實機,MODE 示意圖)**:`drawRect` 照同頁游標外框(mask 0x20b:color、do-fill 0、border-width、rect),
  **rect 的 x/y/w/h 各綁一個整數變數**:62-byte appVariableEvent(mask 0x3f,component-id = drawRect 區域編號,
  property `rect`,`property-subindex` 0..3)。原生端 post 整數即時改框。文字顏色:drawText 加 `color` 欄位
  (mask bit 13,horz-align 之後 4 B RGBA)。**按住重複**:keyEvent 的 type/args 怎麼改都不會重複(d8 實機四種),
  USB 注入的鍵也從不重複;原廠日期頁的遞增 handler 也只 +1 —— 按住要另找機制。
- **圖片標題換成文字(r56 實機,分頁 FILTER/MODES/OUTPUT)**:把 `drawImage` 換成同 local id、同 `color` 的
  `drawText`(mask 0x40002011),原本只動 `color` 的 clip 照樣讓選中變白。`horz-align` 列舉:0 inherit、1 left、
  2 center、3 right(schema 預設字串)。**換了元件類型或多加綁定,header 的元件配額要跟著算**(舊記錄進 removed、
  新記錄進 plus),否則 check_page 的配額會錯。
- **原生 blob 的 static 函式名不能和 `struct sl_menu` 欄位同名**:撞了四次(rwzm_text、ro_w、area_w、filter_key),
  `test_sl_modes.test_no_static_name_is_a_field_name` 現在在主機上就擋下。
- **`appVariableEvent` 綁 `is-visible` 沒有作用**(d7 實機:物件一直顯示/隱藏不跟變數);綁 `opacity`
  (整數 0/1 轉浮點)就會即時顯示/隱藏。位置在父物件範圍外的子物件不會被裁(箭頭在欄位上方 -30 照樣畫)。
- **原地編輯一列數值(日期/時間頁的做法,r34)**:列(MenuItem_Jump)按 Right/OK → 寫請求碼 + `controlFocus`
  到一個看不見的編輯物件 E;E 的每個鍵只做 `controlAppVariable(SL_O_Key ← 碼)`,OK/MENU 再把焦點還給列。
  原生回呼依碼改值、吸附合法值、`C0593F30` 回寫各欄位,並把 `SL_O_Key` 送回 0(我們自己送的值不會觸發回呼,
  所以同一個鍵再按一次還是「變化」)。按住加速用 `C002B920()`(ARM,開機毫秒數)量連按間隔。
  原廠日期頁(Y5_1)的上下鍵也是 sync-request 給原生處理,所以頁面裡的加減一定要自己做。
- **很多私有字串時用 `uis_intern_many(字串陣列, 數量, UIS_NOT_STOCK, 位移陣列)`**(fpSup/uishare,2026-10-03):
  一批只清一對 D-cache、不掃原廠池(建卡程式放進字串區的本來就都是原廠池沒有的)。Sensor Lab 私有字串
  從 ~40 增到 ~70,開機 `LOAD_DONE_US` 反而從 17.2 s 降到 11.4 s。逐一 `uis_intern` 的成本是每個字串
  兩次全 D-cache 清除 + 整池線性掃描(r13:59 個字串 +20 s)。
- **列內左右切換值(r35)**:清單列 MenuItem_Select 的 Right 改成 `changePropertyByControl(自己 controlValue,
  'dst + 1')` + `controlAppVariable(變數 ← 自己 controlValue)`,新增 Left(`dst - 1`);controlValue 上限設成
  剛好「選項數 − 1」就會停在最後一項;OK 照舊開清單。範本是同頁 STYLE 的 MenuItem_Step 彈出框(SubMenu 42315)。
  原廠 `MenuItem_Step` 本身不是列內左右切換,是在右邊開一個上下調整的小框。
- **Cortex-A9 沒有除法指令**:原生區塊裡寫 `/`、`%` 會要 `__aeabi_uidiv`(沒有 libgcc,建置失敗);
  用常數、位元遮罩代替。
- 原生區塊(build_sl_menu)沒有連結器:`.rodata` 常數表、檔內呼叫公開函式都會產生 .text 重定位而建置失敗
  (`-fropi` 不管 .rodata);用算式代替表、檔內呼叫走 static 函式、公開名稱只做薄包裝。
- **複製別頁 donor 的列,三個 2026-10-03 在 Sensor Lab 分頁(B5_4_2 STYLE 列)踩到的坑**:
  1. 清單樣板 `0x10008`(269 B)的物件 id 在固定位移 20,65,77,97,117,137,157,177,197,217,237;
     **不要用「> 64 的值才換」掃描**——B5_4_2 的 List/ListItem/Text 是 14/15/16,沒換到,
     popup 指向已刪的原廠 ListItem:按 Right 後看不見清單、焦點消失(S1 可退)。
  2. donor 的 `submenu_width_01/_02` 依 app 變數把 List 改成 1024 − w 寬(原廠給圖示清單的 ~240 px);
     文字清單要拿掉這兩個物件,List 用自己的 x 77 / 寬 947。
  3. **一個物件裡,事件(+28)與動畫片段(+24)共用同一套本地編號**,新增事件的編號要取兩者最大值 + 1。
     B5_4_2 STYLE 列的 List 片段是 17、事件到 16;只看事件給新游標事件 17 → 選到那列時 SetList
     播片段 17 卻找到事件,**整台相機掛掉(UI 與 USB shell 都沒回應,要拔電池)**。
     d5/d6 對照卡定位(3 項正常、5 項只改上限正常、5 項只加事件就掛)。B2_5 的事件到 19 所以從沒撞到。
     建置現在用 `sl_lab_page.duplicate_local_ids` 擋;原廠 B5_4_2/B2_5/MainB2 都沒有任何重複。
     (曾懷疑清單文字的 `>` 是原因並改成 "23.98p+",實機證明不是;`rows_csv` 仍拒絕 `<` `>` 以防萬一。)
  另:原廠頁裡蓋在列上的背景(B5_4_2 BG 5039,y 81 h 162 不透明)要一起拿掉;
  `.nloc` 字串 ID 換頁就畫不出來(0315 在 B2_5 可、在 SL_LAB 空白),標題用字面文字。
- 游標卡住可以按 MENU 退出,但選單記得上次的列,再進去又卡 → 讓使用者自己按,不要一直用 USB 送鍵
  (`key MENUON/RIGHTON` 連送曾讓 USB shell 卡住,要拔插)。

### 8c. 同頁複製列要改掉的東西(B2_6 → Lossless RAW)[實機]

| 原本 | 作用 | 改成 |
|---|---|---|
| `MV_AudioRecord`(5 欄) | 值 | `MV_fpLossless` |
| `SUB_MV_AudioRecord` | popup 暫存值 | `SUB_MV_fpLossless` |
| `EXCL_AudioRecord`(5 欄) | 錄音被停用時鎖住、反灰 | `EXCL_fpLossless`(永遠 0) |
| JumpEvent sync-request `B2_6` | 選 ON 跳音訊子選單 | `xxx`(原廠另一分支就用它當 no-op) |
| 標題 drawText `0326_C` + 文字動畫 `0326_C`/`0326_CI` | 標題 | 字面 `Lossless RAW`(resolver flag 0) |
| List 值==1 → `Footer` 區段 `Footer02` | 底部「› 更多選項」 | `Footer05`(值 0 用的那個) |
| Cursor02 drawImage 的 is-visible 動畫 key@66 = 1 | 「開啟 ›」的箭頭 | 0 |

- 三個私有變數都要**先註冊**(`C05DB309`,Thumb,`{type 0, 名字指標, 0}`;registry **借用**名字指標,
  要放在永不釋放的記憶體)。從 loader 的 task 註冊,實機沒問題。值讀 descriptor +08。[實機]
- **popup 的「關閉/開啟」文字不是 CSV 來的**,是 ListItem 子物件的 drawText(`0080`/`0081`)。
  `B2_6.cvm`(`1,0080,xxx` / `2,0081,B2_6`)跟原廠錄音列共用,不要動它。
- 值:0 = 關閉、1 = 開啟;收合摘要也用 `0080/0081`,會顯示中文。

### 8d. 上卡:選單資料併進 fpSup.BIN[實機]

- loader 讀 fpSup.BIN 最多 `MAXLEN 0xF000`。選單資料("FPLM" v2)接在 **0xF000 之後**,loader 看不到。
  loader 的部分補零到剛好 0xF000,選單區塊補零到 0x30000。
- 開機時用 loader 同一組檔案 API(`C0365E90/FB0/6060/6020/5ED0`,volume 1 = SD)**同一個 handle 讀兩次**:
  先讀 0xF000 跳過,再讀選單區塊;magic/FNV 不對就什麼都不裝。
- FPLM v2:`+00 "FPLM" +04 2 +08 頁面長 +0C 私有字串長 +10 引用數 +14 0x76FF04 +18 FNV +1C 0`,
  `+20` 頁面 → 私有字串 → `{頁面位移, 字串位移}` 引用。引用由 builder manifest 產生、打包時逐一比對頁面。
- 安裝結果碼 `menu.result`:1 已安裝 … 7 讀不到檔、8 格式不符、9 註冊失敗、11 共用字串池拒絕。
  任何失敗都不動 UI,錄影一律原廠。
- **putfile 不能截短檔案** → 固定補零到同樣大小。**AutoRun 不要改**,只用 putfile 寫 fpSup.BIN、讀回比 SHA-256。
- 最快回原廠:換回不帶選單的 fpSup.BIN。

### 8e. 私有字串:共用 FSPL 字串池(`fpSup/uishare`)[實機]

- 不要每個 sup 自己複製一份字串池再換 `reader+14`:OG 的字串 hook(`C05E5B58`)只認原廠池,
  兩個一起裝 OG 的選單就壞(實機發生過)。
- 約定:在自己的入口呼叫 `uis_intern(s, n, &offset)`。池裡已有就回傳那個位移(原廠或別的 sup 加的),
  沒有就附加。第一次附加時把原廠池整份複製一次(多 16 KiB、永不釋放),前面 16 bytes 標頭
  `"FSPL" | 版本 1 | 容量 | 0`,並把 reader 換過去;`reader+0x10` 永遠是使用中的長度。
- **誰都不事先佔位移**:頁面在載入時才把拿到的位移寫進去(lossless 18 個欄位)。
- 自己的程式會檢查字串池的 sup(像 OG 的 alias hook),要接受「原廠池 **或** `uis_pool_known()`」。
- 實機:容量 0x2F02D、長度 176,241(原廠 +89 B);`xxx`、`Footer05` 直接沿用原廠位移。
- **每個私有字串都有開機成本**:`uis_intern` 整池(17 萬 B)線性搜尋一次,附加時再清兩次 D-cache。
  Sensor Lab r13 有 ~80 個私有字串(複製物件各取新名),開機卡在第 3 格多 ~20 s;改成沿用原廠名後
  降到 23 個。物件名不必唯一(原廠 220 頁中 165 頁有同名兄弟物件)—— 能用原廠池既有字串就用。[實機/離線量測]

### 8f. 與別的 sup 合併 [實機/離線]

- OG3K/OG2K 的 ui_string(`og3k_ui.S`)已改成接受原廠池或 FSPL v1 池;**已發行的 OG(OG3K ≤ 0.2.7a、
  OG2K ≤ 0.1.4a)只認原廠池,不能和會附加字串的 sup 合併**。
- 合併卡:`fpSup/lossless/build_card.py --og og3k|og2k`(OG 自己的發行建置取全部固定段落與入口;
  入口由 build_autorun 的跳板依序呼叫,有沒有 USB shell 都一樣)。`--plain` 不帶 FS2、`--no-shell` 不帶 shell。
- 實機:OG3K + lossless,兩邊選單、QS 正常。OG2K + lossless 只在模擬器開過機。
- Sensor Lab 原地重建 B2_5,跟 OG 的原地修改相衝;跟 lossless 不重疊。
- 每個 sup 改了 UI 的哪裡:`research/ui/UI_SERVICE_INVENTORY.md`;後續的 add_row/hide_row/add_option:
  `fpSup/uishare/PLAN.md`。
- 觀察(與 lossless 無關):裝 OG3K 時,解析度設 FHD 播 OG3K 影片會被壓扁、設 OG3K 播 FHD 會被拉長;
  切到 OG3K 再切回 FHD 又正常。沒有回放 hook 的卡一樣,是 OG3K 自己的顯示行為,待查。

## 8g. 新增一整個私有頁(子頁)—— Sensor Lab r13–r16,2026-10-02/03 [實機]

不借原廠頁、不搬表、只加兩個小 hook。程式:`projects/open-gate/build/sl_pages.py`、
`sl_menu/sl_modes.c`(註冊)、`sl_excl.S` ROLE 15(GUI id)。設計:`IMX410_FULL_DESIGN.md` §8.12。

1. **頁 + 畫面物件 + 執行期項目**:私有包 `"NBR\0"` + 版本 **0x01090000**(註冊函式只認 NBR 魔術字;
   頁面記錄是 NBU 1.9 格式,解析版本從容器繼承)+ pool + tag `0x10001` 頁索引
   (每筆 `{fnv1a, 名字, 1, 位移, 0, 0, 1024, 682}`,依雜湊排序)。用 `C05E84D8(app, 包, 長, &新 reader)`
   在 UI 執行緒註冊,原廠會建 screen(app+7C)與項目;之後把新 reader +0x10/+0x14 換成共用池。
   註冊前查 app+0x80 < app+0x84(畫面清單)與 app+0xF8 < app+0xFC(狀態機清單),滿了會重新配置。[實機]
2. **切頁要轉換**:UI 只在 app+0xF4 的某台狀態機命中「(目前畫面, 請求)」才換頁。原廠的在 NBM
   (`0xC2DE3D20`,17 台);同一個包裡加 `0x50001`/`0x50002 {狀態數,0×6,轉換數,名}`/`0x50003 {名,0,0}`/
   `0x50004 {來源,目標,事件,""}`。原廠**沒有通用 Return**,每頁明寫「子 —Return→ 父」。[實機]
3. **GUI 頁表要有它**:沒登記 → `NullGuiInterface`,它的 v1 不轉送任何按鍵。掛 `0xC056461C`
   (`bl FUN_c0564638`)讓 `SL_` 頁回傳父頁的 GUI id(B2_5 = 36)。app 頁表不用登記(沿用父頁)。[實機]
4. **頁面內容要是完整的原廠頁結構**:只有根物件 + 一個抄來的 MENU keyEvent(0xB)的頁,
   切過去後**所有按鍵(含半按)都無效**;換成原廠 B2_6_2 完整複本就能操作、MENU 返回。[實機差分]
5. 每個私有字串都有開機成本(見 §8e);頁面可借原廠名。

## 8h. 外部卡(Julien sigma-fp-supmod R120)反推出來的規則 —— **[離線]**,來自他能用的卡,我們沒上機

拆解全文:`research/other/external/sigma-fp-supmod-R120/ANALYSIS.md` §10。他的字串 hook(`0xC05E5B58`)、
記錄解譯器 hook(`0xC05E6400`)、CSV 改法跟我們 OG3K/本 skill 同一套;以下是我們**沒有**的:

1. **畫字時的文字解析可以 hook:`0xC05EC4B4`**(`FUN_c05ec490` 內 `bl FUN_c05ebf80`;後者取介面 0x1003 再呼叫 +4)。
   每次畫 drawText 都經過 → 不改記錄就能依狀態改任何元件(含 QS)的字。他依 CINE/STILL
   (`[0xC31AE3A8]==1` + `C0057AE8`/`C0058340`)換標籤,STILL 回原廠;CSV TEXT 放合成鍵 `LJ0/LJ1/LJN`,在這裡解成文字。
   和 §2 規則 4(TEXT 寫字面文字)比:字面是靜態的,這個可以隨模式變。
2. **互斥的兩列共用同一個 y,由 is-visible clip 互換。** 錄影設定頁 `B2_5_2`(位元深度)與 `B2_5_3`(ALL-I/GOP)
   都在 y=81:B2_5_2 clip `[(0,1),(66,0)]`、B2_5_3 `[(0,0),(66,1)]`(依格式)。列距 81 px(B2_5_4 162、B2_5_5 243)。
   → 加列的另一條路:讓原廠藏起來的列現身(他把 `B2_5_3` 拿來當 Lossless 開關)。
   怎麼讓它在 cDNG 也顯示並移到 y=162,靜態補丁裡看不到,應是解譯器 hook 解析時改的,**未追完**。
3. **搬列要一起改它的 `List`(與 `Scrolbar_onoff`)位置**,那是相對於列的。原廠 B2_5_5 的 List/Scrollbar y = −243(=−列 y),
   B2_5_4 的 List y = 0。他把 B2_5_4 162→243、List 0→−243;B2_5_5 243→324、List/Scrollbar −243→−324。
4. **收合摘要的文字跟 CSV 分開**:MenuItem_Select 下 `IconText0N` 的 drawText。位元深度 CSV 改 12/14 後,
   他另把 IconText01/02 的 `0305/0306` 改成 `0307/0244`。只改 CSV,摘要會是舊字。(B2_5_2 的 List max 2.0→1.0 照 §2 規則 5)
5. **XCI 同名原地換像素**他做了約 70 個。和 §1「要新名字才重解」不矛盾的推論:他在那些圖示第一次解碼前就寫好。未驗證。
6. **掏空用不到的大 XCI 當程式碼空間**:`L_focusScale_scaleBar.xci` 21 KB → 842 B(改目錄長度欄),空出 21,116 B。
   前提:確認那個圖示開機後從沒被解碼/顯示。

## 8i. 用「添加」合併選單 —— fpSup/uishare（2026-10-03）[離線；未上機]

不再各自改原廠資源；每個 sup 在 Python 宣告它**加什麼**，開機時由共用套用器組合：

- **頁（任何有執行期項目的資源組）**：從「目前的樣子」複製一份（`FSPG` 標頭），插入記錄、加計數，最後才換 `entry+08`。
  兩個 sup 疊在同一頁 = 再做一次；物件 ID、列的 Y、選項 index 都在開機時發。
- **清單 CSV**：經共用取檔處理器（`fv_handler.S`，掛在 `C05E5BEC`，raw-view H1 的共用版）改指到複本；每個 sup 往複本追加列。
- **字串**：`uis_intern_hinted`（帶建置時算好的原廠位移，不掃 17 萬 bytes）。
- 怎麼用、規則、驗證：**skill `fp-ui-add`**；技術筆記 `research/ui/UI_AND_STRINGS_BY_ADDITION.md`；
  計畫與狀態 `fpSup/uishare/MENU_MERGE_PLAN.md`。
- **陷阱（實機症狀，10/03）**：用**絕對位址**比對原廠字串（例：raw-view `stub_ai` 比 `0xC18E6BA0`）在別的 sup
  附加字串後會失效（UI 改用池副本）→ 一律比「目前池（`reader+0x14`）裡的位移」。

## 9. 工具

**讀 app 變數(只讀,mem get)**:`[C37B7048]` = app → `[app+0x888]+0x60` = registry → registry+0x14 是排序雜湊表
(`+8` 筆數、`+0xC` 12 B 項目 `{FNV-1a(名字), ?, descriptor}`);descriptor `+0` 型別、`+4` 名字、`+8` 值。
腳本:`projects/open-gate/build/sl_menu/appvars.py NAME…`(第一次讀整張表約 2,200 筆並快取)。

```
research/ui/tools/uinav.py            at / pages / sets / pool / icons / routes / traps / who
research/ui/tools/nbr_stock.py        .cvm 與 NBR 目錄
research/ui/tools/nbu_probe/nbu_format.py   split / join / group <名> / maxima <集合> --rows N
research/ui/tools/enum_converters.py  326 支轉換器:at <addr> / list --count N
research/ui/tools/nbu_components.py   一個物件子樹的每個元件+型別化屬性(事件、controlFocus 目標、動畫區段、
                                      app 變數、sync-request、drawText),--clips 連動畫 key;原廠頁或私有頁檔都可
fpSup/lossless/menu/build_menu_candidate.py --profile audio-toggle   私有 MainB2(+`word_writes` 指定字改寫)
fpSup/lossless/menu/pack_menu_file.py       → FPLM v2 區塊,build_card.py 接在 fpSup.BIN 的 0xF000 之後;
                                              native/menu_page.c 在相機上安裝
fpSup/uishare/ui_pool.{c,h}                 uis_intern / uis_pool_known;test_ui_pool.py(含突變)
projects/open-gate/build/test_og3k_ui_string.py   OG 的字串 hook 接受 FSPL 池(unicorn,含突變)
research/ui/tools/xci.py, render_xci.py     圖示與畫面擷取
projects/open-gate/build/imx410_rate_native.py / imx410_rate_ui.py / imx410_rate_lv.py
```

反組譯小工具:capstone ARM 模式直接讀 `out/MAIN_c0000000.bin`(base `0xC0000000`);
**腳本別叫 `dis.py`**(會蓋掉標準庫、capstone import 失敗)。
找呼叫者要掃**整個映像**(BL 範圍 ±32 MB),也要搜 movw/movt 成對載入的函式位址
(provider 表常這樣註冊,例如 `C049FCB8` 註冊 `C04A1120`)。
