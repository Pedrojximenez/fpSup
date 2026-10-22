# Sup 的「更多設定」頁 —— 調查(2026-10-08,全部離線,未上機)

問題:sup 怎麼在 All Sups 清單(FT_LIST)自己那一格之下,開一頁**由 sup 自己提供**的設定頁(自己的列/選項),
值怎麼回到 sup、怎麼存。前提文件:`ALL_SUPS_MENU.md`(r1–r3e)、`LOADER_V3.md`。
標記:**[實機]** = 筆記記載已上機;**[離線]** = 讀碼/模擬;**未驗證** = 推論。

---

## 1. 現有先例

### 1a. res-lab 的私有頁 SL_LAB(最完整的先例)

| 環節 | 做法 | 出處 |
|---|---|---|
| 頁面內容 | 以原廠 `B5_4_2`(取景框線頁,三個內分頁)為底,整頁複本;每列複製**同頁** STYLE 第一列(MenuItem_Select + popup);所有變數改成私有(`SL_F_*`、`SL_LabFocus`…),建置時拒絕還留著 `MV_FRMGUIDE_*` 的頁 | `projects/open-gate/build/sl_lab_page.py` 檔頭 |
| 打包 | `"NBR\0"` + 版本 `0x01090000` + tag 1 池 + tag `0x10001` 頁索引 `{fnv1a,名,1,位移,0,0,1024,682}` + 狀態機 `0x50001..0x50004` + 頁 | `sl_pages.build_pack` |
| 狀態機 | `TransSensorLab`:每頁 `父 —<頁名>→ 頁`、`頁 —Return→ 父`(原廠沒有通用 Return) | `sl_pages.transitions` |
| 註冊 | `C05E84D8(app, 包, 長, &reader)`;新 reader 的 +0x10/+0x14 換成共用池 | `sl_pages.py` 檔頭、`sl_modes.c` `nbr_register` |
| GUI id | hook `0xC056461C`:`SL_` 前綴回傳父頁 GUI id(B2_5 = 36);沒登記 → NullGuiInterface,按鍵全死 [實機 r15] | `sl_pages.gui_parent_id`、skill fp-native-ui §8g |
| 從 B2_5 跳進去 | 解析度 = CUSTOM 時 footer 換 `Footer02`(「› 更多選項」);popup Right 寫列號到隱藏 `SL_JumpEvent` 的 controlValue;值事件 type 0x12 == CUSTOM+1 → `controlAppState` sync-request `"SL_LAB"`。**物件與動作必須從同頁複製**(MainB2 的 JumpEvent 搬過來從不觸發)[實機 r20–r23] | `sl_b25_page.lab_jump`、`size_jump` |
| 值回 sup | 私有變數 `C05DB309` 註冊(名字指標要常駐);`C0560FB0(0xC37B7048, 名, cb)` 訂閱,cb 在 UI 執行緒、新值在描述子 +8;寫回畫面 `C0593F30`(int)/`C0593FE0`(字串,GUI 只留指標);自己的 post 不觸發 cb | `sl_menu/sl_modes.c` L117–127、`panel_changed`、`sl_menu_ui` |
| 持久 | res-lab 的選擇存自己的 BIN(LOADER_V3.md 第 6 步、記憶 custom-format-selection-is-a-variable) | — |

可直接沿用的頁面技巧(fp-native-ui §8b):列內左右切值(r35)、字串變數 → drawText(r43,需 component-id)、
`opacity` 綁 int 做顯示/隱藏(`is-visible` 無效)、事件與動畫共用本地編號(撞號整機掛)。

### 1b. uishare(add_row / add_option / 字串層)

- FPUI 操作碼 1..18(`fpSup/uishare/ui/fpui.py` L84–89):PAGE/GUARD/INSERT/ADD32/ADDF/ALLOC/DONE、HOOK_FV、
  CSV_ADD/CELL、FILE_*、EXPECT、SETSTR_SLOT、STRBASE、QS_OPTION、IF_SLOT。
  **全部是「改既有頁/清單」,沒有「登記一整頁 + 狀態機」的操作**。私有頁目前只有兩份手寫實作:
  res-lab(`sl_menu.c`/`sl_modes.c`)與 All Sups(`allsups.c` `ft6_register`)。
- 字串層:每個 sup 一層,STRBASE 把私有字串的池位移交給 sup 自己的資料;一個 FPUI 區塊最多 64 字串
  (`ui_apply.c MAX_STRINGS`,ALL_SUPS_MENU r3d)。
- add_row 只能在建置時決定列;「開機才知道列數」不支援(ALL_SUPS_MENU 調查表)。

### 1c. 各 sup 現在的設定列

| sup | 入口 | 值 | 持久 | 能當「更多設定頁」嗎 |
|---|---|---|---|---|
| lossless | MainB2(CINE 第 2 頁)加一列「Lossless RAW」,同頁 B2_6 列複本;`Footer02` 改 `Footer05`、JumpEvent 改 `xxx`(**刻意拿掉了「更多選項」**) | 私有 `MV_fpLossless` | `10LOSS.BIN` 的 `settings` 16 B `FLST`;codec 任務閒置、非錄影、穩定 1 s 才寫(mode 7、seek、寫、讀回) | 列本身不是頁;但它的持久做法就是範本 |
| screenflip | `Y2_5_1` 第 3 頁 TOOLS 第 5 列 | `MV_fpScreenFlip`,依正在編的自訂 N 用 `C0593F30` 回填 | `40FLIP.BIN` `settings` 20 B `FFST` | 同上;已是「依情境回填變數」的例子 |
| raw-view | COLOR 清單第 17 列(add_option / HOOK_FV),原廠的「更多選項」進階頁 | — | 自己 BIN | 用原廠進階頁,不是私有頁 |
| res-lab | B2_5 → SL_LAB(1a) | 49 個私有變數 | 自己 BIN | **唯一完整私有設定頁先例**,但寫死父頁 B2_5 |
| All Sups | FT_Y6 → FT_LIST | `FT_Key`/`FT_Focus`,`allsups_key` 回呼 | LOADER.BIN 尾 128 B FSDS | 本身就是「loader 提供的設定頁」 |

結論:**沒有任何一份是可重用的「sup 自己的頁」產生器**;最接近的組合 = res-lab 的頁面建法 + All Sups 的註冊/層 + lossless 的持久。

## 2. 記憶裡要遵守的事實

- submenu-jump-mechanism:原廠跳頁要 MenuItem_Jump + JumpEvent;**但私有頁不靠它**,我們一律用 `controlAppState`
  sync-request + 狀態機轉換(FT_Y6→FT_LIST、B2_5→SL_LAB 都是)[實機]。目的頁必須已存在(已註冊)。
- menu-slots-and-scrolling:清單捲動現成;分頁超過 6 列的 flexbox 捲不捲**未知** → 設定頁先 ≤ 6 列。
- csv-row-is-data-only:popup 清單用 CSV、`TEXT` 可寫字面文字、改列數要配 controller max。
- native-ui-routes:原生外觀只有 R2(私有 NBR)一條路。
- system-page6-works:私有包可以在 **loader 任務(entry)** 註冊 [實機];Menu01/12/13 是目標分頁號。
- custom-format-selection-is-a-variable:使用者不要集中存設定 → **每個 sup 存自己的檔**。
- ALL_SUPS_MENU r3b:兩頁共用 `MENU_Level1` 記焦點 → 進出失焦、MENU 失效 → **每頁焦點用自己的私有變數**。
- ALL_SUPS_MENU r3e:停用不改檔名(改名後 sup 關機寫回原路徑產生 128 B 假 .BIN)→ sup 寫回自己的檔路徑穩定。

## 3. 提案:任何 sup 都能宣告「我的設定頁」

### 3a. 關鍵限制:格子上沒有空的鍵

離線列出 `Y5_2` 每格的 keyEvent(`ft6_page` 的 stock_pool + `nbu_format`,本次跑):
**Up/Down/Left/Right(格子導航)、OK(3 個動作,FT_LIST 改成寫 FT_Key 切換載入)、Menu(Return)** —— 六個全用掉。
其他頁上出現過的鍵名:`QS`、`FDial_R/L`、`BDial_R/L`、`Tab_Left/Right`、`OK_Help`、`Right_Help`…
它們在 FT_LIST 會不會送到格子 **未驗證**。所以入口有三種選擇(**要使用者定,會動到既定的 OK 行為**,見記憶 ask-before-design-change):

| 方案 | 操作 | 代價 |
|---|---|---|
| **A. 每格一頁「sup 詳情」** | OK → loader 的共用詳情頁 `FT_SUP`:列1「Load at boot  On/Off」(原本的切換)、列2「Settings ›」(有宣告才可選)、版本 | OK 不再直接切換;詳情頁要開機時填內容(變數) |
| B. 另一顆鍵 | 例:格子加 `QS` 或 `FDial` keyEvent → 跳該 sup 的頁;OK 維持切換 | 那顆鍵在選單頁能不能用要先上機量 |
| C. 從 sup 自己的入口 | 像 res-lab 從 B2_5 用 Footer02 跳 | 每個 sup 各做一次,頁父不同、GUI id 不同,不通用 |

建議 **A**(原始規劃「每列:啟用/停用 + 更多選項 ›」就是這個形狀),B 當實驗備案。以下機制 A/B 共用。

### 3b. 宣告:service v4 `declare_page`(建議)

```c
/* sloader.h, version 4, appended (前面欄位不動) */
int (*declare_page)(const struct sl_svc *, const char *page_name, uint32_t pool_off);
```
- sup 在 entry 裡:先 uia_apply 自己的字串層(頁名是它 FPUI 區塊裡的一個私有字串,STRBASE 給出池位移
  `pool_off`)→ 註冊自己的頁包 → 呼叫 `declare_page`。loader 記在 `sups[cur]`。
- sup **不設 min_svc = 4**:`svc->version < 4` 時就不宣告,自己的頁仍註冊(無入口而已),舊 loader 照樣載入。
- 替代方案(不建議):FSB1 標頭沒有空欄位(`version` 幾乎都是 1,r3d 已說不能用);在 sup 區塊裡放 magic 讓 loader 掃 —— 脆弱。
- ⚠ 改 sloader 會動到預設 loader 位元組(`41f3218a…`,LOADER_V3 r3a)→ 所有 v3 產品一起換 loader。

### 3c. 頁名、GUI id、狀態機

- **頁名 = `FT_<sup_id>`**(例 `FT_RAWV`):`allsups.c` 的 `ft6_layer`(0xC056461C CHAIN 一層)認 `FT_` → GUI id 21(MainY5),
  FT_LIST 用同一個 id 已上機可操作。→ sup **不必自己掛 0xC056461C**。要修改的規則:「`FT_` 保留給 All Sups 底下的頁,
  sup 只能用 `FT_<自己的 id>`」(現行 ALL_SUPS_MENU §共用站點寫「其他 sup 不准用 FT_」)。
  無 loader 第 6 頁時這頁沒有 GUI id,但也沒有入口,無害。
- **轉換放在 sup 自己的包**(sup 建置時就知道兩個名字):
  `FT_SUP —FT_<id>→ FT_<id>`(方案 A)或 `FT_LIST —FT_<id>→ FT_<id>`(方案 B),以及 `FT_<id> —Return→ 來源頁`。
  兩個都是私有畫面名,跟原廠不會撞 → sup 的機器**不用搬到第 0 格**(`FUN_c05ED028` 第一個比中的採用,ALL_SUPS_MENU §第 6 頁機制)。
- **loader 側只寫一個字**:格子(或 FT_SUP 的 Settings 列)的 `controlAppState` +36 請求欄位 = 該 sup 的 `pool_off`(big-endian),
  在 `ft6_register` 註冊 ALLSUPS 包**之前**寫(同 step 3 寫 refs 的方式,`allsups.c` L476–479)。沒宣告/沒載入 → 寫原廠池裡的 `xxx`
  (lossless 的 no-op 請求),轉換不中,畫面不動。時序沒問題:sup 的 entry 都在 `load_builtin()` 之前跑完。
- 方案 A 的 FT_SUP 只有一頁,由 loader 在 OK 回呼裡依格子 k 用 `C0593FE0` 推名稱/狀態字,並把 Settings 列的請求…… **但請求欄位是記錄裡的池位移,註冊後不能再改**(頁面記錄解析時才讀,FT_SUP 每次開都重解?**未驗證**)。
  穩妥做法:FT_SUP 內放 17 個隱藏 jump 物件(每格一個,`opacity` 綁 `FT_Sel==k`),或 Settings 列寫 `FT_Go = k`、
  每個 k 一個 `controlValueEvent value-equal k → sync-request` 動作(res-lab `lab_jump` 的 type 0x12 形式,同頁複製)
  —— 17 個動作的 `+36` 各自在開機時填 `pool_off`。這是 A 比 B 貴的地方。
- **MENU 回格子**:sup 頁的 MENU 動作送 `Return` → sup 機器 `FT_<id> —Return→ FT_LIST`(或 FT_SUP)。FT_LIST 焦點記在
  私有 `FT_Focus`,回來應停在原格(r3b 修法;**未驗證**跨 sup 頁往返)。sup 頁自己的焦點**不能**用 `FT_Focus` 或 `MENU_Level*`。

### 3d. 頁面內容怎麼做

- 不要從零寫:sup 頁 = **整頁原廠結構** + 同頁列複製(§8g 規則 4:只有根物件的頁按鍵全死)。
  建議把 res-lab 的建法抽成 uishare 的 `settings_page(name, rows)`:底頁先用 SL_LAB 已上機的 `B5_4_2` STYLE 列
  (MenuItem_Select + popup 清單、列內左右切值),每列 `(標題字面文字, 私有變數名, 選項字串…)`,≤ 6 列。
  ⚠ SL_LAB 的 GUI id 是 B2_5(36),改用 21(MainY5)時同一頁會不會照常收鍵 **未驗證**(FT_LIST 是 Y5_2 底、id 21,可以)。
- 打包:`build_ft6.build_pack`(轉換可指定)已是通用版 `sl_pages.build_pack`;sup 的包 = 一頁 + 一台小機器。

### 3e. 值怎麼回 sup、怎麼存

1. entry 裡 `C05DB309` 註冊私有變數(名字放常駐區;初值 = 自己 BIN 裡存的值)、`C0560FB0` 訂閱 —— 兩者在 loader 任務呼叫已上機(FT_Key)。
2. 回呼(UI 執行緒):改 sup 內部狀態;需要連動的字用 `C0593F30/C0593FE0` 推;觸發型的鍵變數處理完 post 回 0。
3. 存:**sup 自己的 BIN** 裡固定位置的 `settings` 記錄(lossless `FLST` 16 B、screenflip `FFST` 20 B 的格式:magic、版本、值、校驗),
   路徑用 entry 的 r2(svc v2,`min_svc` 2)。mode 7 原地同長度改寫 + 讀回(mode 7 不截斷,file-api-open-modes)。
   **時機照 lossless**:回呼只設欠帳旗標,由自己的閒置輪詢在「非錄影、3 s 內沒 REC、值穩定 1 s」時寫(stop-path-keep-it-thin、
   no-usb-during-rec)。allsups 在 UI 回呼裡直接寫 LOADER.BIN 已上機,但那是選單裡的單次動作;sup 沒有任務的(只有回呼)才照它直接寫。
4. 不集中存、不碰相機設定區(第一守則);也不再改檔名,路徑在整次開機有效。被停用的 sup 不跑、不寫回,不衝突。

## 4. 未決 / 風險

1. **入口 A/B/C 要使用者定**(A 會改 OK 的既定行為)。
2. B 的候選鍵(QS、轉盤)在 FT_LIST 格子上會不會觸發 —— 未驗證。
3. 畫面清單容量:`ft6_register` 在 `app+0x80 + 1 >= app+0x84` 時拒絕(回 5)。sup 各註冊一頁會吃容量;原廠滿了會重新配置(fp-native-ui §8g),
   但 allsups 自己選擇拒絕 → 要量開機後實際的 count/cap。
4. 機器數:每個 sup 一台,app+0xF8/0xFC 同理;`ft6_register` 要求「多一台且最後一台是 TransFtTab」—— sup 先註冊不影響,但順序別顛倒。
5. 一個包能不能**沒有**狀態機(頁的轉換都放 loader)—— 未驗證;提案讓 sup 自帶機器,避開這題。
6. 字串:頁名、列標題、選項都是私有字串,每 sup 的 FPUI 區塊 ≤ 64;每個私有字串有開機成本(§8e)。
7. 格子上要不要顯示「›」:可加一個 `FT_M<k>` 文字變數(又 17 個字串,ALLSUPS.BIN 區塊數 +1)。
8. 讀 FT_SUP 請求欄位在每次開頁是否重解(決定 A 能不能只用一個動作)—— 未驗證。
9. sup 頁用 MainY5 的 GUI handler(21):原廠 Y5 handler 對未知物件的 OK/Right 有沒有副作用 —— FT_LIST 沒看到,但列型頁未試。

## 5. 最小的第一個上機實驗(一次只改一件事)

**E1:sup 自帶的頁能從第 6 頁跳進去、按鍵有效、MENU 回來。** 不動 sloader、不加 svc。
- 測試 sup `95MSET.BIN`(id `MSET`):自己的字串層 + 一個包:頁 `FT_MSET` = `ft6_page.build_grid()` 的輸出把
  `FT_Key`/`FT_Focus` 改名為 `MS_Key`/`MS_Focus`(已上機的頁,OK 只寫私有變數,不寫設定),
  機器 `FT_Y6 —FT_MSET→ FT_MSET`、`FT_MSET —Return→ FT_Y6`;訂閱 `MS_Key`,回呼把值寫到自己的 BIN 的 16 B 紀錄。
- ALLSUPS.BIN 改一處:FT_Y6 那一列的 **OK** 請求改成 `FT_MSET`(Right 仍是 `FT_LIST`),請求字串建置時就是私有字串(不需 loader 開機填)。
- 看:OK 進 FT_MSET(畫面、焦點)、方向鍵移動、OK 讓 `gui geti MS_Key` 變、MENU 回 FT_Y6、Right 仍進 FT_LIST;
  關機前卡上 95MSET.BIN 只差那 16 B。LOAD.LOG 讀記憶體(4096 B 會被擠掉)。
- 過了再做 E2:loader 依 `declare_page` 在開機時填請求欄位;E3:入口(A 或 B)。

上機前:unicorn 跑真 loader v3 + 真映像(`test_ft6.py` 形式)、原廠狀態機比對 `(FT_Y6, FT_MSET)`、`(FT_MSET, Return)`
(`sl_pages.native_switch`)、mutation;先問同機 session 相機是否在用(agents-means-peer-sessions)。
