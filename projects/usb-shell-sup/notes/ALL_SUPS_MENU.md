# All Sups 選單(規劃,2026-10-06)

使用者定的:

- SYSTEM 分類有一列 **All Sups ›**,點開才列出相機裡所有 sup(`\fpSup\*.BIN` 與停用的 `*.OFF`)。
- 每個 sup 一列:**啟用 / 停用**,以及 sup 自己提供的 **更多選項 ›**。
- **停用要重開機才生效**。停用 = 把檔案改名成 `.OFF`,啟用 = 改回 `.BIN`。加載器本來就只載 `.BIN`;
  在電腦上一眼看得出狀態,也能手動改回。
- **清單頁由加載器提供**:uishare 編進 `LOADER.BIN`。

## 架構

```
SYSTEM 某頁
 └ All Sups ›                       加載器開機時 add_row(入口列,MenuItem_Jump)
     ├ 10LOSS  [啟用]  ›           每列:名稱 + 啟用/停用 + 有選項頁才有 ›
     ├ 30OG3K  [啟用]  ›
     └ 40FLIP  [停用]
```

- **時機**:加載器在所有 sup 都載入之後才建清單頁(要知道誰有選項頁、誰載入失敗)。
  lossless 在 init 裝選單列已經證明載入時 GUI 物件就存在。
- **列的來源**:列目錄(`dir_ctor/open/next`,已上機)。`.BIN` 與 `.OFF` 都列,LOADER.BIN、隱藏檔、`._*` 除外。
- **名稱**:先用檔名主檔名(`10LOSS`)。之後可以在 FSB1 標頭或 sup 的 UI 區塊加顯示名稱。
- **啟用/停用**:每列一個記憶體變數。值改變後,由加載器的閒置程式改檔名(韌體的 rename,shell `fl rename` 用的那支)。
  不碰相機設定區。**加載器目前沒有任務**,需要決定由誰在閒置時執行改名(見待決 2)。
- **更多選項**:sup 在自己的 FPUI 區塊宣告「我的選項頁 = 頁名」。加載器建清單時查到,就把那一列做成跳轉列。
  頁面本身由 sup 自己用 uishare 加(現有的 add_row / 換頁機制)。
- **加載器自己**不出現在清單、不能停用。

## 要先查清楚的(上機前,依序)

1. **私有頁面怎麼建、怎麼從一列跳過去**:Sensor Lab 的 SL_LAB 私有頁做過(projects/res-lab);
   跳轉的規則見記憶 submenu-jump-mechanism(列要是 MenuItem_Jump 帶 JumpEvent,目的頁要先存在)。
2. **列數在開機時才知道**:uishare 的 add_row 是建置時從頁面建置器產生的。要確認能否在執行期用同一個 donor 列重複
   產生 N 列、每列換文字與變數名;不行的話,改成建置時預先做 K 列的模板,開機時只填用到的列。
3. **超過 6 列要捲動**:自訂頁還沒有超過 6 列的先例(記憶 menu-slots-and-scrolling)。
4. ~~改名 API~~ **已找到(離線)**:shell `fl rename` 的 handler `FUN_c03E67C8`:
   `f_ctor(obj, 卷)` → `f_open(obj, 舊路徑, 7)` → **`FUN_c0366508(obj, 新路徑)`**(0 = 失敗)→ `f_dtor`。
   上機前要驗證:改的是自己以外的 sup 檔,而且那個檔在加載器讀完時已經關閉。
5. **加載器變大**:loader.S 讀 LOADER.BIN 的上限預設 0xF000(60 KB),`build_autorun --read-cap` 最多 0x1F000,
   但改上限要重建 AutoRun。LOADER.BIN 目前 7 KB;uishare 的 ui_pool + ui_apply 預估一二十 KB,應在 60 KB 內(待實測)。

## 調查結果(2026-10-06,讀筆記與原始碼,未上機)

| 項目 | 現況 | 證據 |
|---|---|---|
| 私有頁 | Sensor Lab 的 SL_LAB 做過:離線打包 NBR 頁 + 私有狀態機,`C05E84D8(app, 包, 長, &reader)` 註冊,GUI 頁表 hook `0xC056461C` 回傳父頁 id(寫死 B2_5)。**沒有通用 API**,程式在 sensor-lab | [實機] r16b/r18 |
| 跳進私有頁 | 用 `controlAppState sync-request "<頁名>"`(CUSTOM → RIGHT → SL_LAB);從別頁複製的 JumpEvent 不會觸發 | [實機] |
| 開機時才決定列數 | uishare/FPUI **不支援**(操作清單建置時固定)。可行方向:離線先做 K 列,多的用 `opacity` 綁私有變數隱藏;每列文字用字串變數(drawText 綁定,`C0593FE0` 寫入) | opacity、字串變數各自 [實機];組合起來未做過 |
| 超過 6 列 | 自訂頁會不會捲動 [未知];SIGMA 自己的做法是多開分頁 | — |
| **SYSTEM 頁加列** | **沒有成功前例**。lossless 曾把 MainY4 的列搬進 MainB2,整頁壞掉(`ERR 10000009,4`);MainY 頁能不能改指 [未知];MainY 頁不是 flexbox 版面 | [實機](失敗的那次) |
| 更多選項(popup 底部) | `Footer02` 區段、箭頭是 Cursor02 的 is-visible 動畫 | [實機] |

**最大的風險是第一步:在 SYSTEM 頁加一列。** 要先做一個最小實驗:SYSTEM 某頁加一列不做事的 All Sups,
上機看頁面有沒有壞、能不能選到。不行的話,入口改放已證明可改指的頁(MainB2 / B2_5),再跟使用者確認。

## 使用者定的 UI(2026-10-06)

- 入口:**SYSTEM 新增第 6 頁**(現在的第 5 頁已排滿 6 列),這一頁放 All Sups ›。
  要做的:私有頁(以 SYSTEM 第 5 頁為底)、接進左右翻頁的環(第 5 頁 → 第 6 頁 → SHOOT 第 1 頁,反向亦同)、
  頁碼條從 5 格變 6 格。三件都沒有前例。
- 停用:選了之後**顯示漏斗**,改名完成後那一列標示「**重開機後停用**」(啟用同理)。改名在選擇當下執行。

## 待決

1. ~~入口~~:SYSTEM 第 6 頁。
2. 改名在哪個脈絡執行:要能顯示漏斗、又能做檔案操作(加載器的小任務,或 UI 事件裡同步做)。
3. 跟 sigmafp-re-70(正在改 uishare 與 sloader)分工。

## 最小可行版

入口列 + 清單頁 + 每列只有名稱與啟用/停用(改名),先不做「更多選項」。
上機驗證跳進、返回、改值、重開後生效,再加「更多選項」。

## SYSTEM 第 6 頁的調查(2026-10-06,解析 out/MAIN_c0000000.bin,全部離線)

- **翻頁環**:原廠 NBM 容器 `0xC2DE3D20` 裡的 `TransMainMenu` 狀態機(13 狀態、26 轉換),
  例如 `MainY5 —Menu01→ MainB1`、`MainB1 —Menu13→ MainY5`。請求由頁面自己的 keyEvent 送出:
  MainY5 的 Left → `Menu12`、Right → `Menu01`,撥盤也一樣;MainB1 有 `Menu13` / `Menu02`。
- **進選單回到哪頁**:`TransSystem` 的 `Choice0001` 依 `CM_MenuTabNo` 0..12 決定(Y5 = 12)。新頁要第 13 號。
- **頁碼條**:每一頁自己畫(`HeaderActiveTab_Y` 的 Tab01..05,各一個 drawRect),亮哪格由 `MenuTab` 動畫集的
  13 個 key(依 `CM_MenuTabNo`)決定。要 6 格:**全部 13 頁**的 `_Y` 都要加 Tab06,MenuTab 也要加第 14 個 key。
- **GUI 頁表**:`0xC0D0DB68`,MainY1..Y5 = 17..21;私有頁要靠 hook `0xC056461C` 借 GUI id(Sensor Lab 實機)。
- **漏斗**:沒有筆記。候選:圖示 `cmn_clock_1/2/3.xci`(LV 頁,`LV_ImageProcessing` 驅動)、
  選單 NBU 頁 `Processing`、字串 `UicGuiMenuMediaFormatInProgress`。怎麼從程式顯示:未知。
- **未知**:MainY5(115 KB)/ MainB1(141 KB)能不能用頁面複本改指;私有狀態機與原廠 `TransMainMenu`
  對同一組轉換時誰優先;`CM_MenuTabNo` = 13 會不會被截掉。
- ⚠ **第一守則**:`CM_MenuTabNo` 很可能會被存進設定區(選單記得上次的分頁)。存成原廠不支援的 13,
  開機時可能出問題。上機前必須先查清楚它存不存、存在哪、原廠怎麼讀。

## 第 6 頁的機制(2026-10-06 第二輪,unicorn 實跑原廠函式;腳本在 research/ui/tools/nbm_probe/)

- **翻頁怎麼決定**:頁面送出的請求(如 `Menu01`)由 `FUN_c05DD448` 從 app+0x108 隊列取出,交給
  `FUN_c05ED028(app, 目前畫面名, 0, 請求名, &out, 0)`,依序掃 app+0xF4 上的狀態機,**第一個比中的採用**。
  原廠 17 台排在前面(TransMainMenu 是第 8 台),`C05E84D8` 註冊的私有包 append 在後 → 同一組轉換原廠贏。
- **不用 hook 的插入法**:私有包註冊後,用 `FUN_c05D7538(vec, m)` 從 app+0xF4 移除,再 `FUN_c05D74D8(vec, m, 0)`
  插到第 0 格。代價:這台的所有轉換都優先於原廠 → 只放第 6 頁需要的四筆:
  `MainY5 —Menu01→ MainY6`、`MainB1 —Menu13→ MainY6`、`MainY6 —Menu01→ MainB1`、`MainY6 —Menu13→ MainY5`
  (加上第 6 頁的子頁轉換),**不放 WildCard 狀態**。emu_two_machines.py 用原廠函式驗證了兩種順序的結果不同。
- **CM_MenuTabNo**:NBV 變數(第 378 個,int,初值 0,沒有持久欄位);C++ 端只訂閱、存到 0xC37B735C,
  沒有 cam_* 參數或 CommonSaveData 路徑 → **離線判斷不會進設定區**(待上機:切到 Y5 → 關機再開 → 選單應回 B1)。
  但 `TransSystem` 的 Choice0001 只列 0..12:值 13 時 MENU 會打不開選單(推論)。
  → **第 6 頁沿用 "12"**:按 MENU 重開選單時回到 SYSTEM 第 5 頁,不會出現 13,也不碰原廠的 Choice。
- **頁碼條**:每頁(含子頁)各自畫。最小做法:第 6 頁自己畫 6 格;Y1..Y5 仍是 5 格,要 6 格得改 Y1..Y5 的 _Y(待決)。
- **還需要**:第 6 頁的 GUI id(Sensor Lab 用 hook `0xC056461C` 回傳父頁 id;要通用化),頁面要是完整的原廠結構(以 MainY5 為底)。

## uishare 新功能(設計草案,實作前給 sigmafp-re-70 確認)

`uis_tab_add(...)`(暫名):把一個私有頁接進某個頁籤環的最後:
1. 以建置時從 MainY5 複製的完整頁(NBR 包)註冊(C05E84D8),包裡帶一台只有上述轉換的私有狀態機;
2. 把這台機器移到 app+0xF4 第 0 格;
3. GUI id(通用版的 0xC056461C 處理);
4. 頁碼條:第 6 頁自己 6 格。
多個 sup 都要加頁時的排序與「誰是最後一頁」:用加載器登記簿協調(之後再設計)。

### 共用站點 0xC056461C(私有頁的 GUI id)—— 套娃規則(2026-10-06 與 d9 定案)

- 原廠字 `0xEB000005` = `bl FUN_c0564638`;呼叫時 r0 = CustomScreenLoader、r1 = 頁名(char*)、lr = 原呼叫者。
- 每個要私有頁的 sup 一層:claim **CHAIN**(不准 EXCL);entry 寫站點之前用 `svc->chain_next(0xC056461C, ARM)`
  取得內層目標存進自己的塊(第一層就是 `0xC0564638`),站點改成 BL 到自己的 veneer。
- 每層**只認自己的頁名前綴**:res-lab = `SL_`;uishare 的分頁 = `FT_`(fpSup Tab)。其他 sup 不准用這兩個前綴。
  認得 → r0 = 該頁的 GUI id(父頁或借用的 id)、`bx lr`;不認得 → r0/r1/lr 原樣跳內層目標。
  只動 r0(回傳)與 ip,其他暫存器不碰。不需要層標頭:誰在內層由 BL 目標決定。
- res-lab 改法由 d9 做(rl_v3 / sl_excl:claim 改 CHAIN、fallthrough 改跳 chain_next 的結果)。

## 第 6 頁 r1 上機(2026-10-07,e7 接手 58 的設計)

程式:`fpSup/uishare/tab/`(`ft6.S` 實驗 sup、`build_ft6.py`、`test_ft6.py`:unicorn 跑真 loader v3 + 真映像，
C05E84D8 換 Python;頁面包經原廠狀態機比對;mutation 三項皆抓到)。卡:`cards/20261007-ft6-r1/fpSup/90FTAB6.BIN`
(sha1 9ecdeb8b…),與 00SHELL/10LOSS/20GYR2/32RESCUS/40FLIP/45RAWV 同卡。

- 頁名 `FT_Y6` = MainY5 原封複本;私有狀態機 `TransFtTab` 只有五筆轉換(Y5 -Menu01-> FT_Y6、B1 -Menu13-> FT_Y6、
  FT_Y6 -Menu01-> B1、FT_Y6 -Menu12/13-> Y5)。**Menu01/12/13 是「目標分頁號」**:Y5 的 Left 送 Menu12(到 Y4),
  所以複本的 Left 要配 Menu12,不是草案寫的 Menu13。
- **註冊在 loader 的任務裡做(entry 時)**,不是 UI 執行緒:原廠 C05E84D8(app, 包, 長, &reader) → 新 reader +0x10/+0x14
  指向原廠 reader 的字串池 → app+0xF4 最後一台(名稱比對 `TransFtTab`)旋轉到第 0 格(未呼叫 FUN_c05D7538/74D8,
  容量內直接搬指標)。32RESCUS 的 QS 層掛在 C05E84D8 上，非原廠包直接往下傳，不衝突。
- 0xC056461C CHAIN 一層:`FT_` → 21(MainY5 的 GUI id),其餘交 chain_next / FUN_c0564638。
- **實機結果(冷開機經 USB reboot)**:B1 ←LEFT→ FT_Y6 ←LEFT→ Y5、Y5 →RIGHT→ FT_Y6 →RIGHT→ B1,一圈全對;
  FT_Y6 上 DOWN 進列、焦點反白正常;列上 RIGHT 無反應(子頁轉換只認 MainY5,預期);MENU 從 FT_Y6 直接回 LV,
  再按 MENU 回到 **MainY5**(CM_MenuTabNo 沿用 12,如設計)。無凍結。頁碼條仍是 5 格亮第 5 格(未改)。
- LOAD.LOG 只有 4096 bytes,被暖開機的 REPAIRED(12)行塞滿，看不到 `FT6 s=N` 那一行 —— 要看狀態得讀記憶體。
- 未測：暖開機(撥開關)路徑下 UI app 是否已存在(不存在會 s=3/4 RELEASE);撥盤翻頁。

下一步：清空頁面(留標題列與頁碼條、放 All Sups 一列)、第 6 頁畫 6 格頁碼條、做成 uishare 通用功能(先給 70 看設計)。

## 停用的表示法(使用者 2026-10-07 定案)

**改副檔名**:`\fpSup\NAME.BIN` ↔ `\fpSup\NAME.OFF`,同一層。不用 `fpSup/OFF/` 子資料夾。
理由(省資源):一次掃 `\fpSup` 就同時列出啟用與停用;切換 = 同目錄改名一次;不需跨目錄搬移或建資料夾。
merge-v3 的衝突輸家也改寫成 `NAME.OFF`(已通知 sigmafp-re-45)。改名 API `FUN_c0366508` 仍只有離線證據，上機待驗。

## 第 6 頁 r2 上機(2026-10-07)

程式:`fpSup/uishare/tab/ft6.c`(C 版 sup,與 uishare 的 ui_pool.c/ui_apply.c 同一 unity 編譯)、`ft6_page.py`(頁面)、
`build_ft6.py`(`sup2()`)、`test_ft6.py`(11 項 unicorn + 原廠解析器；mutation 皆抓到)。
卡 `cards/20261007-ft6-r2c/fpSup/90FTAB6.BIN`(sha256 b8c13d10…)。

- 頁面 = MainY5 去掉 Y5_2..Y5_6,只留 Y5_1 一列;列名 drawText 改字面文字(+4 旗標 0),位移開機時由 uishare 字串層
  (FPUI 區塊一個字串 + STRBASE)發給;entry 先把 STRBASE 的位址改成自己 tab 的欄位、重算區塊 fnv,再 uia_apply。
- 33510(CameraControl_ExclChk)兩個事件的動作全指向被刪的列 → 事件連動作一起刪、物件記錄數 -1。
- **兩個踩過的雷(r2/r2b 實機)**:① 動作 +28 是順序號但**不是**依記錄順序 1..n(HeaderActiveTab Up 是 2、1),
  重編會壞;② 原本就沒有動作的事件(n=0)不能當「全刪光」移除(HeaderActiveTab 的 CM_MenuTabNo 事件)——
  兩者都讓頁首變成 SHOOT/B1、列全不見。回歸測試 `test_only_the_planned_records_change` 守著。
- **頁碼條**:每格的 color 動畫只有 Root 的 MenuTab 動畫集登記過的物件才會播(r2b:新物件複製動畫仍全暗)。
  做法：原廠 Tab01..04 搬到 SHOOT 頁碼條的 1..4 格位置、**原廠 Tab05 連自己的動畫搬到第 6 格**(Y5 時間點本來就亮)、
  第 5 格補一個無動畫的暗色方塊。
- 實機(r2c):SYSTEM 分頁、6 格第 6 格亮、「All Sups」列、焦點反白與 › 正常;B1↔FT_Y6↔Y5 一圈、MENU 離開正常;
  第 5 頁不變(仍 5 格)。列上 RIGHT 仍無作用(r3:清單頁)。
- 未做：守則 §6 的「開機、不錄影、關機」約十次(成品時做);暖開機路徑。

## r3a:第 6 頁搬進 Loader v3(2026-10-07,上機通過)

使用者定：第 6 頁綁在加載器(獨立 sup 拿不到別人的載入結果)。做法(與 sigmafp-re-70 協調):
- `fp_usb_shell/v3/allsups.c`(由 ft6.c 來)與 uishare ui_pool.c/ui_apply.c 跟 sloader.c 編成一個 unity
  (`build_v3.loader_bin(allsups=True)`,`-DSL_ALLSUPS`、stub 多一個 `ALLSUPS_PATH` 字串)。LOADER.BIN 7260 → 20900 B。
- 資料(表 + FPUI 區塊 + 頁面包,39.7 KB)放 `\fpSup\UI\ALLSUPS.BIN`(`build_ft6.py --data`),不進 LOADER.BIN,
  讀取上限與 AutoRun 不動。
- sloader.c 在所有檔案載入完、SL_SVC_AT 清零前 `load_builtin()`:以 `sups[]` 一項「LOADER.BIN」(id `FT6T`)進入，
  claim / holder / self / uishare 層名稱 / LOAD.LOG / 失敗復原都跟一般 sup 一樣。缺檔 OPEN_FAIL、壞檔 BAD_HEADER,什麼都不改。
- **預設建置(不含第 6 頁)維持逐位元組 41f3218a…**,v3 發行版共用的 loader。第一次重構(抽出 enter())改到預設位元組，
  害 45 作廢一個 gyro2 發行版 —— 改共用 loader 時先比對預設 sha256。第 6 頁要進發行版時，所有 v3 產品一起換 loader。
- 測試:`v3/test_allsups.py` 9 項(真 loader.S + LOADER.BIN 讀卡、字串層屬於 LOADER、關機寫回、缺檔/壞檔/衝突);test_v3 22 項不變。
- 卡 `cards/20261007-allsups-r3a/`(LOADER.BIN sha256 ce2765a4…、UI\ALLSUPS.BIN 377fc5da…,舊 LOADER 備份在 backup-before/);
  90FTAB6.BIN 已刪。實機:與 r2c 相同畫面、翻頁一圈、MENU 離開;其他 sup 照常載入(shell 正常)。

下一步 r3b:清單(含 .OFF)、切換改名、狀態顯示。

## r3b / r3c:清單與切換(2026-10-07,上機通過)

- **r3b**(MainY5 的 6 列複本)上機打通了切換，踩到的雷:① IconText01 的 objectBase 多一個欄位(遮罩 0x43)預設隱藏，
  綁變數也不顯示 → 改 Name 的格式;② 清單頁的物件 id 跟第 6 頁不同，而兩頁共用 `MENU_Level1` 記焦點 → 進來或回去都失焦、
  MENU 失效(半按快門可脫困)→ 第 1 格沿用原廠 id(3451)、清單自己的焦點改記私有 `FT_Focus`。
- **r3c**(使用者:「嘗試語言列的呈現」):清單頁改以 `Y5_2`(語言頁)為底，3×6 格、17 格、標題「All Sups」。
  拿掉:首次開機語言流程(KeyMaskCheck/LangCheck,寫 SYS_LangSetting、跳 LV)、目前語言標記 CursorFix、標題的綁定;
  `CM_Language`/`CM_LanguageAj` 全換成私有 `FT_Focus`;每格 OK 原本寫 CM_Language → 改寫 `FT_Key = k`(46 B 帶值格式，
  +32 遮罩 0x81、+41 值字串),並刪掉其後的 controlAppState(按完留在本頁);MENU 沿用語言頁的取消(Return → FT_Y6)。
  測試 `test_the_grid_writes_no_setting` 守「整頁不再提到語言設定變數」。
- 每格一個文字變數 `FT_N<k>` = 名稱(去掉載入順序的數字前綴)+ 狀態:``/` (OFF)`/` (ON*)`/` (OFF*)`/` (!)`/` (ERR)`,
  `*` = 下次開機才生效。字在 ALLSUPS.BIN 的 TEXTS,改字只要重建資料檔。
- loader 以 `C05DB309` 註冊變數、`C0560FB0` 訂閱 FT_Key(在 loader 的任務裡做，實機可用)、回呼在 UI 執行緒改名
  (檔案物件 + 開檔模式 7 + `C0366508`,同 shell 的 `fl rename`)後 `C0593FE0` 推字、`C0593F30` 把 FT_Key 歸零。
- 實機(卡 `cards/20261007-allsups-r3c/`,LOADER 698257c9…、ALLSUPS c913eeaa…):格子顯示 SHELL/LOSS/GYR2/RESCUS/FLIP/RAWV;
  RAWV 按 OK → 卡上變 45RAWV.OFF、格子即時顯示 `RAWV (OFF*)`;再按 → .BIN、`RAWV`;MENU 回第 6 頁、再 MENU 離開;
  CM_Language 仍是 7(繁中)。
- 一次 USB worker 卡死(看原廠語言頁時、按了一長串鍵之後),拔插 USB 恢復;沒有證據跟第 6 頁有關。
- 待做：超過 17 個 sup(分頁);sup 自己帶顯示名稱(使用者覺得檔名難看);第 6 頁其他列;進發行版(全部 v3 產品一起換 loader)。

## r3d:產品名稱、版本、紅綠狀態(2026-10-08,離線通過，待上機)

使用者要求：完整產品名(USB-Shell / Gyro2 / Lossless / RES-Custom / RAW-View / Flip)、
小字版本號、選卸載 → 小紅字「重開後卸載」、已卸載的反灰、選開啟 → 小綠字「重開後載入」。
- 每格 5 個物件/文字變數:`FT_N`(白名，本次有載入)、`FT_G`(灰名，沒載入)、`FT_V`(小字版本)、`FT_R`(小紅字)、`FT_E`(小綠字);
  不顯示的放 " "。字型大小/顏色照 sl_lab_page.diagram 的作法(遮罩加 bit 2 font-size、bit 13 color,欄位依位元序);
  紅綠中文字借繁中格的 `TraChin_fontsetting`(bit 1 font)。版面：第一行名稱 font 40,第二行 font 24 左版本、右狀態，全部靠左
  (對齊欄位的值還沒摸清)。
- 名稱/版本：開機讀每個檔的 FSB1 檔頭 sup_id,查 ALLSUPS.BIN 的 {id, 名稱, 版本} 表;版本取 `fpSup/releases/` 每個 id 最新的 v3 發行版
  (build_catalogue_v3 的規則)—— **建置時就固定**,換 sup 不重建 ALLSUPS.BIN 會顯示舊版本。長期應由 sup 自帶名稱與版本。
  表裡沒有的 sup 顯示去掉數字前綴的檔名。檔頭的 `version` 欄位幾乎都是 1,不能用。
- **ui_apply 一個 FPUI 區塊最多 64 個字串**(MAX_STRINGS)、8 個 STRBASE:現在約 110 個私有字串 → 每 60 個一個區塊(各自一層字串層),
  每塊只要一個 STRBASE(層內位移依區塊順序連號)。
- 測試:test_allsups 12 項(名稱查表、反灰、紅綠切換、改名失敗)、test_ft6 4 項、test_v3 22 項;mutation 4/4。
- 卡 `cards/20261008-allsups-r3d/`(LOADER 7d08e27a…、ALLSUPS 5d107dbb…)。

## r3e:不改檔名，停用清單記在 LOADER.BIN(使用者 2026-10-08 定案，取代 .BIN↔.OFF)

起因(70 查到):停用時立刻改名 → 那次開機 sup 還在跑，關機時以 mode 7 寫回自己原本的路徑 → 新建 128 B 假 .BIN,
下次拒載、名字也被佔住。使用者:「別改名了，紀錄在 loader_v3 的 bin 裡面」。
- LOADER.BIN 程式碼之後多 128 B:`FSDS`、數量、最多 30 個 sup_id(VBIN +12 的程式長度不含它，loader.S / AutoRun 不受影響)。
  `loader_bin(allsups=True)` 附上空清單;預設建置不變(41f3218a)。
- 開機:sl_boot 先把 LOADER.BIN 原檔留一份(stub 先把字串指標寫進自己的 `strs`,副本要把那 5 個字補回 0)並讀清單;
  load_one 讀到檔頭 id 在清單上就不載入，LOAD.LOG 記 code 19 (DISABLED)。
- 第 6 頁按 OK:清單加/減該 id,用原檔副本整份寫回 LOADER.BIN(同長度，不怕不截斷);寫失敗清單還原、紅字「寫入失敗」。
  不再呼叫改名。沒有檔頭 id 的、舊的 .OFF 檔只顯示(灰)不能切換。
- 測試 test_allsups 13 項(清單上的不載入、寫回後只有清單不同、失敗還原、不改名);mutation 3/3。
- 卡 `cards/20261008-allsups-r3e/`。merge-v3 的衝突輸家改用這份清單(待 45),不再寫 .OFF。

### FSDS 確切格式(給 merge-v3 / 發行檢查，2026-10-08)

- 位置：`16 + code_len`,`code_len` = VBIN 標頭 +12 的 u32(little-endian)。build_v3 把程式碼補到 4 的倍數，所以 FSDS 一定 4 位元組對齊。
  LOADER.BIN 總長 = `16 + code_len + 128`,FSDS 是檔案的最後 128 B。
- 內容(全部 little-endian u32):`+0` magic `0x53445346`("FSDS")、`+4` 數量 n(0..30)、`+8..+127` 30 格 sup_id
  (FSB1 標頭 +20 的 u32,同一個值)。前 n 格有效，**其餘必須是 0**;順序沒有意義(第 6 頁移除時把最後一格搬進空位、最後一格清 0)。
- magic 不符或 n > 30 → loader 當作沒有清單(全部照常載入)。
- 程式碼部分(前 `16 + code_len` bytes)= 發行版 loader 原樣;第 6 頁寫回時只改 FSDS(test_allsups 驗「只有清單不同」)。

- 2026-10-08 使用者:相機上的字不要中文 → 狀態改英文：紅 `Unload on restart` / `Load failed` / `Write failed`,綠 `Load on restart`;
  小字 font 20、不再借繁中字型。

### r3e 上機(2026-10-08,卡 `cards/20261008-allsups-r3e5/`,LOADER ea4b5a80…、ALLSUPS 9627c58d…)

完整一輪通過:RAW-View 按 OK → 小紅字 `Unload on restart`、卡上 LOADER.BIN 清單 = [RAWV] → 重開後 RAW-View 灰、沒載入 →
按 OK → 小綠字 `Load on restart`、清單清空 → 重開後恢復白字。名稱/版本/反灰/紅綠都照設計顯示。
踩過的:
- **r3d 的 bug**:格子迴圈裡把 drawText 範本也叫 `tmpl`,蓋掉了 OK 動作用的 46 B controlAppVariable 範本 → 每格 OK 變成一筆
  drawText,按 OK 什麼都沒發生。測試只數字串引用沒驗記錄種類，所以沒抓到 → 加 `test_each_cell_ok_writes_ft_key`(mutation 驗過)。
- `gui seti` 對這些私有變數不生效(寫了讀回仍是舊值),不能拿來觸發回呼;`gui geti/gets` 讀值可以。
- 相機時鐘與主機不同步：用檔案時間判斷「有沒有寫入」要先對齊，r3e 第一次誤判成「寫了但清單是空的」。
- 除錯管道：FT_Key 開機 = 3000 + 清單找到 ×100 + 訂閱回傳;按完 = 1000 + ft6_disable 碼 ×10 + 清單找到
  (碼:1 寫入、2 無清單、3 無 id、4 滿、5 開檔、6 寫入失敗)。兩者都大於格數，不會誤觸。
- 變數註冊順序改成 FT_Key、紅、綠、名稱、灰名、版本、FT_Focus(要推送的放前面);後面變數推送是否真的有問題沒有定論
  (當時其實是 OK 根本沒寫 FT_Key)。

### r3f:底部列 Uninstall / Install / Cancel(2026-10-08 上機通過，卡 `cards/20261008-allsups-r3f/`)

- 語言頁的底部是 Footer(71) 下的 Text01(40),一整串在地化字串含按鍵圖示標記:
  `<!font_G_bt_ok_K153,CENTER>OK<!28sp,CENTER><!font_G_bt_menu_K153,CENTER>Cancel`(English Footer05),由動畫切換文字。
- 做法:Text01 移出畫面(x=3000;縮成 0×0 文字仍會畫出來)、同位置放一個無動畫的複本綁 `FT_OK`;
  allsups.c 用同樣的圖示標記組字：開著的 → `[OK] Uninstall [MENU] Cancel`、關著的 → `[OK] Install ...`、沒得切的 → 只有 `[MENU] Cancel`。
  另訂閱 `FT_Focus`(游標移動時換字)、切換後也更新。變數順序:FT_Key、FT_OK、紅、綠、名、灰名、版本、FT_Focus。
- 實機：游標在 USB-Shell 顯示 Uninstall;RAW-View 按 OK → 紅字 + 底部變 Install;再按 → 復原(清單空)。

## r3g:把按鈕交給 sup(使用者 2026-10-08:「loader 只負責把按鈕交給 sup,做什麼由 sup 決定」)

- 服務表 v4(只在含第 6 頁的 loader;sloader.h 用 `SL_ALLSUPS` / sup 端 `SL_SVC_BUTTON` 條件編譯，預設建置不變):
  `int button(svc, int (*fn)(void *), void *arg, const char *label)`,登記給「正在執行 entry 的那個 sup」。
- 第 6 頁每格加 `AEL` keyEvent → `FT_Key = 100 + k`;loader 回呼把它轉給那格 sup 登記的 fn(arg)(UI 執行緒),
  FT_Key 診斷 = 2000 + 格號 + 回傳值 ×100。底部列只有登記過的 sup 才多 `[AEL] <label>`(圖示 `font_G_bt_AEL_K153`)。
  沒登記的 sup 完全不受影響(使用者:「不是所有 sup 都會有更多功能」)。
- 測試 sup `v3/button_sup.S`(60BTN.BIN,id BTNS,label "Settings",handler 計數)。unicorn 15 項、mutation 2/2 過。
- **上機(r3g)**:格子與底部 `[OK] Uninstall [AEL] Settings [MENU] Cancel` 顯示正確;**但在格子上按 AEL 沒有觸發**
  (FT_Key 不變)。shell 的 `key AELON` 本身有效：在 LV 按會切換偽色(這台相機 AEL 被指派成偽色)。
  把 FT_LIST 的 GUI id 改成 B3_5_5 的 47(原廠用到 AEL 的頁)也沒用，已改回 21。
  原廠頁面的 AEL 事件名有三種:`AEL`(24 頁，多為設定子頁)、`AEL Down`/`AEL Up`(只在 LV 頁)。
  推測：選單裡實體 AEL 送不送 `AEL` 事件跟「AEL 鍵的自訂指派」有關 —— 未驗證。
- **AEL 沒送進格子(2026-10-08 追查)**:keyEvent 記錄的**最後一個字才是按鍵碼**(OK 0x0D、AEL 0x13、DISP 0x1A、QS 0x14、
  MODE 0x16、PLAY 0x17、TONE 0x18、COLOR 0x19、上下左右 0x26/0x28/0x25/0x27、前轉盤 0x30/0x31、後轉盤 0x40/0x41),名稱只是標籤;
  第一版從 OK 複製來的 AEL 事件按鍵碼還是 0x0D(已修，有測試)。修好後 AEL 仍不觸發;DISP 探針也不觸發;GUI id 改 47 也無效。
  按鍵路徑是 按鍵 → app 目前選單處理器 → GUI v1 → 頁面(IMX410_FULL_DESIGN.md §3647)。主選單頁(MainY5 等)不在 app 頁表
  (0xC0CDF4AC,60 筆只有子頁);原廠用 AEL 的子頁(B3_5_5、B3_1_10…)在 app 表的處理器是 0,沿用父頁的(B3_5 = 0xC04B5EF8)。
  推論：主選單那層的 app 處理器不把 AEL/DISP 往下送 —— 要 AEL,FT_LIST 得拿到會送 AEL 的 app 處理器(hook 查表 FUN_c04b66a8)。未驗證。


## r3h：管理首頁、標題翻頁與 Enable／Disable popup（2026-10-08 初版離線；後續上機見下節）

使用者定案：page 與 Manage Sups 合成同一列；Sup 右鍵直接選 Enable／Disable；只有已啟用且已載入、並由 Sup 提供的更多設定才出現。桃紅色依 fpSup logo 採 `#E03858`（assets/site.css 的 artwork 色碼），取代預覽的 `#ff4fa3`。

- 新的 `uishare/tab/manage_page.py` 全頁與 donor 都來自 MainY5。同頁 Y5_1 的 jump 列供首頁與翻頁列；Y5_4 的三項 popup 供 Sup 列。原廠更新／QR 設定寫入與 JumpEvent 拿掉，不碰那些持久設定。
- `FT_Y6` 四個入口：Manage Sups、Updates、SD Card Tools、About fpSup。後三者是資訊／Coming soon 頁，版本標示 Loader v3 / r3h preview；未實作網路、QR 更新或格式化回寫。
- `FT_LIST` 五列：Manage Sups＋頁碼、四個可替換內容的 Sup 列。標題 Left／Right 寫 FT_Key=10／11；只在這兩個值翻頁，邊界停住，焦點不動。Sup Right／OK 保留原生 popup；選項寫 FT_Choice1..4=0（Enable）、1（Disable）、2（More Settings），然後回原列。
- 51 個私有變數：FT_Key、FT_OK、四槽的 R/E/N/G/V、FT_PageText、FT_Version、Visible/Lock/Max/More/Default/Choice 四槽、FT_Focus／FT_HomeFocus／FT_InfoFocus0。空列 opacity=0、tab-index=0，且鎖住選擇；focus 均用私有物件 ID，沒有將私有 ID 留在 MENU_Level1。
- 每個選擇經「目前頁 ×4＋槽號」找 Sup；Enable／Disable 是指定狀態，重複選擇不反轉。沿用 FSDS 同長度回寫與失敗復原，不改 BIN 檔名。剛 Enable 但本次未載入的 Sup 顯示 Load on restart，仍沒有 More Settings。
- service v4 的 `button` ABI 不變，r3h 改為 More Settings provider。只有 bin=on、boot=ON、有成功載入的 sup index、有 handler 才提供／呼叫；Disable 即撤下。Sup 的頁面與持久化由 Sup 自己處理。本次測試 handler 只計數，未新增產品設定頁。
- UI 資料 magic 改 FT6U（0x55365446），避免用 FT6T 舊變數配置讀新資料。不是每次建置的 runtime 配對雜湊。預設不帶第六頁的 loader 完整 SHA-256 仍為 41f3218ac1405962eee7182528e969531de4e11adf0c7a0b4868dda79f8cf67c。
- 目前列表存 32 個 Sup／八頁；loader 保留一個 sup slot 給管理頁，最多載入 31 個產品。FSDS 停用表仍為 30。畫面物件數與列表容量分開，增加 Sup 數不用新增頁面版型。
- 相機曾量到 screen vector 221/224，新包五頁必須擴充。原廠 NBR registrar 會擴充 screen／machine vector（fp-native-ui §8g）；r3h 只拒絕 count>capacity 的異常紀錄，正常滿載交給原廠處理。模擬器明確替身測試两個 vector 搬移後的 reader／machine 先後順序；這不是本次實機擴充證據。

建置：`python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261008-allsups-r3h`。新增 --allsups 同時產生 loader 與 UI 資料；相同配置的 AutoRun 不變。產物見該目錄 README.md、manifest.json、verification.txt。

驗證：66 項既有 loader／boot／restore 回歸、最終 16 項管理測試、9 項原生／舊頁面測試通過。四個暫存故障變體全被抓到：錯分頁索引、寫失敗未還原、停用仍顯示 provider、拒絕正常 vector 增長。另執行磁碟上保存的精確 loader／UI／AutoRun 指令，FT6 s=00、51 變數、呼叫堆疊對齊、關機後 GUI 與三個字串站點全部回原廠。

最終 SHA-256：LOADER.BIN（25,964 B）46dc1c7a936ddb4e0c638fd8daf2b8344f9dbe8be1e33224e68761159a43cdbb；ALLSUPS.BIN（388,277 B）19e8b2dfb6987958a42e8154c09e9d7d81bd00b5cc459b946055a95db4008bf5。

**初版離線驗證時尚未上機**：真實繪製、標題／空列／popup 焦點、原廠容量增長、Sup 自有設定頁往返、SD 寫入與開關機。Sup 版本文字仍是建置產品表，不是每個 Sup 的自述 metadata。後續換 loader 時先移轉原卡 FSDS；此測試包的停用表是空的。該階段未寫卡、未操作相機、未 commit／push／發布。

### r3h 上機與 UI 修正（2026-10-08 至 2026-10-09，最終 r3h7）

使用者授權「上機測試」。相機原卡是發行版 loader（41f3218a…），六個產品 Sup 全部保留；只更新 LOADER.BIN 與 ALLSUPS.BIN，AutoRun 原檔與建置相同。前置備份、逐次截圖、原生回覆、六次 shell reboot 紀錄在 `cards/20261008-allsups-r3h-live1/`；本次未測實體電源開關的 warm power cycle。

最終候選 `cards/20261009-allsups-r3h7/`：LOADER.BIN 25,964 B，SHA-256 `46dc1c7a936ddb4e0c638fd8daf2b8344f9dbe8be1e33224e68761159a43cdbb`；ALLSUPS.BIN 281,157 B，SHA-256 `edecd5ba3eeea91a7053d712fd31954bb616be3cf6e52b31ee9ed4ebf82e3a12`。最後完整讀回 loader、ALLSUPS 與 AutoRun，全部逐位元相同；FSDS count=0、其餘 30 格皆 0。臨時 60BTN.BIN 已刪除，最後卡上仍是原六個產品 Sup。

實機通過：

- 第六分頁首頁、四列 Sup＋標題翻頁、第二頁兩個空列隱藏、名稱／版本／灰字與紅綠狀態、原生 footer、桃紅 `#E03858`。
- 標題 Left／Right：1/2→2/2→1/2，首末邊界停住，FT_Focus 維持 3451。Sup 列與標題的 MENU 都回 FT_Y6；Updates／SD Card Tools／About 三個入口及 MENU 返回通過。
- Flip Disable：寫回 LOADER 的唯一差異在 FSDS，清單為 FLIP；重開後未載入、灰字。Enable：清單清空，當次顯示 Load on restart；再重開後恢復白字。最後 Flip 與 RAW-View 均為啟用狀態。
- 臨時 BTNS provider：載入後出現 More Settings；游標移到第三項並按 OK，FT_Key=2107（第一次回呼），再次呼叫=2207。Disable 後第三項撤下；本次仍已載入的 BTNS 再 Enable 後第三項恢復。r3h6 去掉文字位置動畫後再次實測第三項及回呼=2107。
- 原廠 screen vector 真正由 221/224 增長為 226/232（最後 +0x80=0xE2、+0x84=0xE8），machine vector 18/24。五個新頁面均能進入；不再只依賴模擬替身的容量增長證據。
- 最後 is_recording=0，停在 FT_Y6 首頁 Manage Sups 列；MENU 能退到 LV_CINE_MEDIUM。重新按 MENU 會依原廠 MENU_Level1=55 回 MainY5，再按 Right 才回 FT_Y6；目前未持久化自訂第六分頁的原廠選單位置。

本輪真實繪製抓到並修正的問題（`uishare/tab/manage_page.py`）：

- 私有文字需有效的初始字串與明確左對齊；灰字／版本／狀態物件需放在 donor BG 前，避免被遮住。
- popup 的三個原廠文字框帶 8,938 B 的 position/rect 動畫，換選項時會移走新標籤；移除這三段文字動畫並修正 component quota，保留原廠 list／游標動畫。UI 包從約 388 KB 降為 281 KB。
- popup 展寬，固定文字框，selected BG 透明，避免反白遮住文字；覆寫 literal 同時移除原欄位的舊字串引用。
- 使用 MainY5 原生 Footer 的父物件與字型標記，移走原生 Text01／FooterSelect；版本文字置於 footer 右側。
- donor 清理時刪除了 Sup Select 列的 Menu 動作；補上指向本頁 Return 的 controlAppState，r3h7 實機返回通過。

驗證範圍：初版 66 項 loader／boot／restore、16 項管理、9 項原生／舊頁、4 項故障變體通過；本輪第一次 UI 改版後重跑 16 項管理與 9 項原生／舊頁，後續 UI 修正逐版跑 4 項管理頁測試，最終 r3h7 四項通過。loader 程式碼本輪沒有再改，未重複執行全部 66 項。產品 Sup 自有設定頁的實際開啟／返回尚未驗證，只有 provider 回呼；網路更新、QR、SD 格式化回寫仍為 Coming soon。本次沒有錄影、AF／鏡頭試驗、SD 格式化、commit／push／發布。

關鍵截圖：1459 最終管理第一頁、1464 最終第二頁、1465 最終首頁；1451 Enable／Disable popup、1452 待載入狀態、1457 三項 popup；1460–1462 資訊頁。完整結果與限制見試驗目錄 RESULTS.md。

### r3i／r3i2：標題去除省略號、Audio 式更多選項（2026-10-09，上機通過）

使用者要求 Manage Sups 頁碼後不要「…」，並參考已截圖的音訊紀錄 More options。找到原始 SS__1458.JPG，保留於 `cards/20261009-allsups-r3i-reference/`。

- 查過原廠 `MenuItem_Tab_Item2/3` 固定二／三頁 tab 及 B5_7C 固定四頁 Page 控制；不能直接套到 Sup 數量決定的頁數。本版沿用 MainY5 的可聚焦同頁列，以原廠 `font_G_bt_rightleft_K153` footer 提示左右鍵翻頁。標題 drawImage 10062（省略號）及 3457（子頁箭頭）改為 blank；保留焦點 3451 的左右鍵與動態頁碼。
- popup 改為 Enable／Disable 兩項；OK 確認狀態。只在已啟用、本次成功載入、有 provider 且 popup 選 Enable 時顯示右側箭頭與底部 `More options`；Right 呼叫 provider。選 Disable 即隱藏，Right 不呼叫也不改停用表。移除原第三項、舊 JumpEvent 與會覆寫兩項 max-value 的動畫。
- List 的 controlValueEvent 寫 FT_Selected1..4；FocusOn／Off 傳 popup 狀態。新增 FT_RightFooter，共 52 變數。資料 ABI 改 FT6V（0x56365446），含 popup／selected[4]／header 六個 runtime words；service v4 button ABI 不變。
- 上機抓到 popup List 沒有綁 FT_Default，停用後再開仍選 Enable。r3i2 對 List 自身補綁，實測 Disable／Enable 重開皆正確（1470／1471）；不是只綁外層 Select。
- 最終候選 `cards/20261009-allsups-r3i2/`：LOADER 26,752 B／`eea6ce21450f97aacc0b719dc4726965346273c8d115c4052f952b10ff5bf80f`；ALLSUPS 280,464 B／`8eaeff23cba5bfc43057cb34d55dbf01130f33fe95a83468525873233eade182`。AutoRun 未改，預設發行 loader 仍 41f3218a…。
- 離線 17 項管理測試＋五個隔離故障變體通過，最終六項原生 UI 測試通過。實機三次 shell reboot；計數 Sup 在 Enable Right 時 0→1，Disable Right 時保持 1，兩者不改 Enable 偏好。FT_Key 被 FocusOff 歸零，改由核對當次 boot stamp／FSB1／service／row 後讀測試 Sup 自有 counter 作證。
- 最後刪除 60BTN.BIN，重開後只有原六個產品；loader／ALLSUPS／AutoRun 全檔讀回與候選相同，FSDS 空、未用格全 0；1472 是最後六個產品的第二頁，相機停 FT_Y6，is_recording=0。完整證據在 `cards/20261009-allsups-r3i-live1/RESULTS.md`。

限制：未測真實產品 Sup 自有設定頁，只有回呼；MENU 原廠記憶仍回 SYSTEM 5，再 Right 到 6。空列隱藏／鎖住但原生焦點仍可能走到，未聲稱跳過。Updates／QR／SD 格式化回寫仍 Coming soon，Enable／Disable 仍重開生效。本輪未重跑已通過的 66 項基線，未測實體電源開關、未錄影／AF／鏡頭／格式化，未 commit／push／發布。

### r3j／r3j2：原廠英文文字、每頁五個 Sup 與版本／狀態對齊（2026-10-09，上機通過）

使用者追加：看看可沿用的原廠文字；第一頁下面空一格；重開提示位置奇怪、字體比例不一致。本輪將管理清單改為標題＋五個 Sup，剛好使用原廠六列；32 個資料列最多七頁，產品載入 31／FSDS 30 的限制不變。首頁仍為四個功能入口。

- `build_ft6.py` 從原始 seg0 的 English.nloc 讀原廠字串：Footer01（OK／Back）、Footer05（OK／Cancel）、Footer02（Further Options）。保留先前指定的英文 UI，CM_Language 仍為 7；這是建置時重用原廠英文，不是 runtime 隨語言切換。更多設定右鍵圖示／文字、popup 取消提示均實測（1474／1476）。
- 原廠英文表沒有單獨 Enable／Disable、Page、Manage Sups 或 Sup 重開狀態的完全相同文字，保留自訂。Version 1339／Current Version 1348、Memory Media Format 1033／<Media> Format 1036、Load from QR Code 2100／Save QR Code 2098 等資源已列入 native-text-audit.json；未將原廠韌體／設定更新誤當 Sup 網路更新。
- 明確沿用 `Other_fontsetting`，名称／標題／popup 字級 44，版本／狀態／preview 字級 24；原廠 Latin scaleHorz 本來就是 0.80，未另外拉伸個別物件。標題沿原廠 Name 的 54 px 文字框垂直置中，r3j2 修正第一版誤設 79 px 而偏低的問題。
- 版本與紅／綠狀態連成單一靠左次行（x=49、y=48），版本只出現一次；有狀態時整行用紅／綠，否則顯示灰色版本。持久文字借 row 原有 196 B detail，總 stride 272 B 不變。第五列 Flip Enable 的綠字及 USB-Shell Disable 的紅字均實測（1475／1478）。
- 五槽共 63 變數，新增第五 choice／selected 回呼；索引依五槽計算。資料 ABI FT6W（0x57365446），runtime selected[5]，service v4 button ABI 不變。18 項管理行為測試＋六個隔離故障變體通過（unittest 19 tests）；最終六項原生 UI 測試通過。新增第五列回呼錯指第四列的變體被抓到。
- 本輪備份發現使用者已將 FLIP／SHEL 設為下次停用；code 與 r3i2 相同，只有 FSDS 不同。保存原 loader，再暫時透過 popup 啟用 USB-Shell 以維持兩次 reboot 後連線，移轉 FLIP 偏好；最後再透過 popup 還原 SHEL。最終 128 B FSDS 與原備份逐位元相同，未在還原 SHEL 後再重開。
- 最終實機包 `cards/20261009-allsups-r3j2-camera/`：LOADER 27,428 B／`eede52236c08cf03dee596395434ee8847709facca2e3c49e70490f206c03828`；ALLSUPS 289,895 B／`f7a640c92614906a32918d35c610fb0bd72152f20bc738d2a2e5b022ffce6ab0`；AutoRun 同 0c5107ff…未寫。generic `r3j2` loader 只有 FSDS 空表差別。預設發行 loader 全 SHA 仍 41f3218a…。
- 計數 Sup 再測 Right：0→1，選 Disable 時保持 1，無偏好變更；之後刪除 60BTN.BIN，重開只剩原六個產品檔。最終三檔完整讀回一致、FSDS=[FLIP,SHEL]、is_recording=0、FT_Y6。1478 最終第一頁五個 Sup、1479 第二頁 RAW-View、1477 首頁。完整證據見 `cards/20261009-allsups-r3j-live1/RESULTS.md`。

仍未新增產品自有設定頁／網路與 QR 更新／SD 格式化回寫；保留前述原廠 MENU 記憶與空列焦點限制。未測實體電源開關，未錄影／AF／鏡頭／格式化，未 commit／push／發布。

### r3k／r3l／r3m：Sup Manager、相鄰版本與右側狀態欄（2026-10-09，上機通過）

使用者將名稱定為 Sup Manager，拿掉標題頁碼的尖括號；逐步要求 Sup 名稱上下置中、版本緊接名稱並對齊基線、重開提示做成右側欄位，以及頁碼／Loader v3／省略號共用左線，Loader 與 Page／Back 對齊。最終 r3m：名稱 y=16／字級44，灰色版本 y=30／字級26，依相同原廠字型的實機名稱 ink end 留12 px間距；狀態 x=460、width=404，字級24、靠右。頁碼與 Loader 的 frame x=901；移除過時的 r3h preview 開發註記。

私有資料 ABI FT6X（0x58365446）：68變數，新增五個 VersionX 整數，沿用原廠 property-subindex 對 position.X 綁定；產品表從12 B改16 B，包含版本位置。位置是既有六個產品表的建置 metadata，量測來源1484／1485；若名稱或字級改變需更新。row272 B、五槽、32資料列／七頁、產品31／FSDS30與service v4 button ABI不變。18項管理測試、六項原生解譯／matcher測試通過；最終源碼重建與保存檔完全一致，預設loader完整SHA仍41f3218a…。AutoRun未變。

本輪共三次shell reboot，僅更新loader/UI。使用者在看外觀時變更過偏好，每次先捕捉當下FSDS；r3m前是SHEL單獨停用。透過popup暫時Enable維持重開連線，再用新版popup恢復Disable；最後全128 B與before-r3m.BIN相同，恢復後未再重開。六個原產品與AutoRun未改、未加入fixture。最終camera loader27,136 B／24e2ba09094245f225f72f1d2bf4be020980ec05db1187e3f418dffa53adc5d3，UI290,638 B／54841edc7e7b66e4fd1be687536fe4deef08ea42593163d2a60297642cd2fd7c；三檔完整讀回一致。

1488為最終第一頁（SHEL的灰版本與紅色右欄提示），1489第二頁（RAW-View）；實機確認動態版本位置、上下置中、基線、左對齊、首末翻頁邊界与回首頁。is_recording=0、CM_Language=7、FT_Y6。證據在cards/20261009-allsups-r3k-live1/RESULTS.md，最終卡為r3m與r3m-camera。既有catalogue版本、原廠菜單記憶／隱藏列焦點限制及未實作網路／QR／格式化／live unload保留；未錄影／AF／鏡頭／實體電源測試，未commit／push／發布。


### r3n20：獨立 fpSUP 頁、logo2、原廠分頁焦點與窄 popup（2026-10-09，上機通過）

使用者要求首頁／資訊頁顯示 fpSUP、管理頁左上 SupManager＋logo，不再畫成 SYSTEM 第六頁，取消分類列與游標紅框；底部 Loader v3 加大至字級32。最終 logo 採根目錄 logo2.png，31個 native tinted XCI 色層、64×64，x28/y12（比初版下移4），中心y44與標題字框對齊。Sup名稱44／版本26與右側狀態欄延續r3m。

原廠參考1520／1521／1522確認：目前頁碼始終白、其餘灰，只有焦點在分頁列才有目前頁的灰底。保留 MainY5 Cursor01 的 Focus_On／Focus_Off，將灰底置於其下；頁碼與深色背景分開安排原生繪製順序，無新runtime變數／loader code。原廠數字是ARGB4444：inline圖示不吃文字顏色，因此新增保留字形／alpha的私有灰色副本。r3n17誤依L/A工具縮低byte成桃紅，r3n19修正原生四個nibble；logo透明色層也沿用premultiplied ARGB4444。

Enable／Disable popup改x604／width420／height162，跟著Sup槽位，絕對y180／261／342／421／421，底部止於583。同步縮item與背景，移除原廠韌體版本捲動／背景寬度clips；保留cursor位置與焦點，文字置於選取灰底前。1528／1530／1532實測首／中／底列，1536／1538實測Enable與Disable游標上下切換；只Cancel，未確認啟用偏好。

私有FT6Z改為獨立NBR1.5圖片reader保留filename pool、NBR1.9頁reader才採共用stock pool；圖片放在最後page pack之前，確保load_builtin讀取範圍含圖。r3n9曾實際首入凍結、使用者重開；r3n11資料超讀取界線被離線拒絕。r3n12／13的缺字截圖不可等同實際顯示失敗，使用者已確認「相機螢幕正常」；連拍原始檔顯示USB截圖會漏靜態chrome，1542為完整最終畫面，未合成。96變數／五槽／32資料列與七頁、row272、servicev4與產品／FSDS上限不變。

r3n19原生11測試、管理18測試通過；r3n20只改logoY，五頁原生解譯及重複local-ID檢查通過（1測試）。最終源碼重建UI逐位元一致。最終LOADER 27,668 B／07907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f；UI 347,740 B／d2fcbe9d90ac326a1d1be39f649631e7bd89f89407eeeb702bdd01ff9a899ffc；AutoRun仍0c5107ff…，後半輪只更新UI。三檔完整讀回一致、128 B FSDS與before-r3n19全相同且空表、六產品仍在。相機停FT_LIST page1／focus3451、is_recording0、CM_Language7。未錄影／AF／格式化／實體電源循環／commit／push／發布；QR／網路／SD回寫及live unload未新增。詳cards/20261009-allsups-r3n-live1/RESULTS.md及r3n20/PROVENANCE.json。


r3n21微調：使用者要求logo與標題靠近，logo再往下。僅logo y12→16、標題x117→104，間距25→12；五頁header共用。五頁原生解譯／local-ID檢查通過（1測試14.062s），其他來源hash／Loader／AutoRun與r3n20相同，UI源碼重建逐位元一致。只寫UI並完整讀回，單次shell reboot；使用者已進FT_LIST開Lossless popup，LV guard在送任何menu key前停止，直接截目前畫面1546，不變更焦點／選擇。最終三檔全讀回一致、128 B FSDS與before-r3n21相同空表；UI347,740 B／e7cb5478b60ee63b0d00841aa8c1628b47bceb02e7ce7f106e81a5f265c40ca4，Loader與AutoRun同前。詳r3n-live1 RESULTS.md、final-readback-r3n21.json及r3n21 PROVENANCE.json。


### r3o1／r3o2：未完成功能反灰與直接格式化入口（2026-10-09）

使用者要求未完成功能反灰，SD Card Format (Keep fpSup) 直接放首頁，不再藏在 SD Card Tools。r3o1 將 Updates／SD format 入口及資訊頁中 update／scan／QR／keep fpSup 灰化、原生 SelectLock，移除 Right／OK activation 與 dots／arrow；保留 Up／Down／Menu。格式化／回寫仍未實作，沒有送格式化命令。12項原生檢查19.033s、故障變體拒絕及精確源碼重建通過。上機 Right／OK 不進反灰項目，SupManager／About 正常；1548首頁、1553格式化焦點、1555QR反灰。只寫UI並全檔讀回；UI347504B／92e9b9b8220fed7878fae23bc5fb8ca416704636241244f6b847cac89eef894e，Loader／AutoRun與r3n21相同，128 B FSDS不變空表、六產品保留，使用者language0保持、is_recording0。

使用者再要求 About 也反灰，因內容不重要且有項目卡住。r3o2 將 About 入口鎖住；首頁只有 SupManager 可進入。12項原生檢查18.500s、精確源碼重建通過，UI347378B／acd15bdad956f36bb44818b089bd6aa3745ecbe08f93dc4f1cd8430a8db57204。未改Loader／AutoRun／runtime／ABI。上機預檢時SIGMA USB已不在enumeration，host camera=closed；尚未開始r3o2寫入，等待相機連回。詳r3n-live1 RESULTS.md與r3o2 PROVENANCE.json。


r3o2 上機完成：使用者開機後恢復連線、備份預檢，僅寫UI347378B，完整讀回／目錄尺寸核對與單次shell reboot。三個反灰入口Right與OK均留FT_Y6；SupManager的Right／OK均可進FT_LIST，Menu返回。1558完整首頁三列反灰、1561 About焦點仍灰且無可開啟圖示；其他漏chrome原始USB圖保留，未合成。最後三檔全讀回匹配r3o2，Loader與全128B FSDS符合更新前，六原產品／AutoRun未寫，FSDS空表；FT_Y6 focus3451、language0保留、is_recording0。About資訊頁未修復或進入，而是按要求鎖住首頁入口。詳r3n-live1 RESULTS.md、final-readback-r3o2.json與r3o2 PROVENANCE.json。
