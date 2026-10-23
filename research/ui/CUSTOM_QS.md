# 自訂 QS 編輯器與 QS 畫面 —— 靜態逆向（Ver.5.02）

2026-10-20，**全部離線**：只讀 `out/MAIN_c0000000.bin`、`out/decomp/full/blk_c*.c`、
Julien R120/R168 的 `FPOG.BIN`。沒有碰相機，沒有改任何既有檔案。
標記：**[驗]** = 看過反編譯/位元組/離線模擬；**[推]** = 推論，未驗證。

後半（§6 起）是 2026-10-20 方向調整後的重點：**做我們自己的 QS 頁取代原廠 QS**。
自訂 QS 編輯器（§1–§5）照原本查到的寫下來，已不是主線。

重現用的暫存腳本（不屬於專案）：FRM1 解包 `build.py`、反組譯 `dis.py`、
NBM 傾印 `research/ui/tools/nbm_probe/dump_nbm.py`、元件傾印 `research/ui/tools/nbu_components.py --page A:B --root N`。

---

## 0. 一頁摘要

| 問題 | 答案 |
|---|---|
| 自訂 QS 編輯器是什麼 | NBU 頁 `Y2_3C` / `Y2_3C_ShutterAngle` / `Y2_3S` / `Y2_3SLike`（GUI id 123），原生類別 `UicGuiMenuQsCustom` + `MenuQsCustomHandler` [驗] |
| 可選功能清單 | CSV `../MenuY12/data/Y2_3_{CINE,CINE_W91C1,CINE_angle,CINE_angle_W91C1,SLIKE(_W91C1),SSLIKE(_W91C1),STILL(_W91C1)}.cvm`，欄位 `NO,ID,IMAGE,KEY,memo`；CINE 32 列 [驗] |
| 存在哪 | 8 格 × 每個拍攝風格（STILL/CINE）各一組；app 變數 `MV_QSMENU_QS1..8`（CINE）、`CM_/ST_QSMENU_QS1..8`；設定 getter `FUN_c0061b08(settings, slot)`、setter `FUN_c0061ac8(settings, value, slot, 0)` [驗] |
| 兩套編號 | app 變數/CSV ID 是 **UI 編號 0..48**；設定區存 **internal 編號 0..53**，經轉換表 `C2E4300C`/`C2E431A4`（51 對）互轉 [驗表；哪張是 CINE 為 推] |
| 未知 id | UI→internal 查不到時 `FUN_c06d0fa0` 回傳 **0**（不會把垃圾寫進設定區，會變成 0 = 拍攝模式那一格）[驗] |
| Julien 的 DT | **沒有新增 id**：把 CSV 的耳機音量列（ID 48）圖示換成 `menu_flash`（並原地換掉 `menu_flash.xci` 像素），KEY `1929` 由他的文字 hook 在 CINE 解成 "Data Rate"；設定區存的就是耳機音量（UI 48 → internal 53）[驗 CSV/字串；internal 值 推] |
| QS 怎麼打開 | LV 頁 `CommonSystemKeyEvent` 的 keyEvent QS（0x14）→ `controlAppState sync-request "QS"` → 狀態機 `TransSystem`：`WildCard —QS→ Choice0002`，依 `LV_ShootingStyle` 0/1/2 → `QS_STILL`/`QS_STILLlike`/`QS_CINE` [驗] |
| QS 是不是疊加層 | 是一張**全螢幕 1024×682、根物件 fill = 0x00000000（透明）**的 OSD 頁，和 LV 頁一樣；選單頁（MainB2/B2_5）是 0xFFFFFFFF [驗位元組；欄位語意 推]。影像是另一個平面 |
| 圖磚怎麼改值 | 每個功能一個「值holder」物件（controlValue + `appVariableEvent` 綁 `MV_Resolution`/`MV_FrameRate`/`CM_WhiteBalance`…）；轉盤 `DialKeyEvent` 依 `QS_QSMode` 只開一組 keyEvent，做 `changePropertyByControl(dst ± 1)`；少數走 `sync-request Fdial_R/L、Bdial_R/L` 給原生 `MenuQsHandler__v86` [驗] |
| 寫值之後 | `UicGuiMenuQs__v25 @C05806B8` 訂閱 ~70 個 app 變數，每個回呼經 MenuValueConverter 再呼叫 MenuAction setter（例：`MV_Resolution → FUN_c05824d0 → conv FUN_c06bd9e0 → handler+0x13C`）[驗] |
| drawText 能不能用 | 能。原廠 `QS_CINE` 本身就有 6 筆 drawText（`fontsetting`、size 0x36）[驗] |
| 建議 | **設計 Q1：把 `QS_CINE` 的執行期項目 `entry+08` 換成我們的頁**（§8a 已實機的機制），狀態機、GUI id 159、原生訂閱全部沿用原廠，0 個程式 hook 就能打開/關閉 [推，需差分上機] |

---

## 1. 自訂 QS 編輯器：頁面與原生類別

| 項目 | 位置 | 標記 |
|---|---|---|
| NBU 資源集 | `Y2_3C` 0xC27F9903、`Y2_3C_ShutterAngle` 0xC28BC223、`Y2_3S` 0xC2984B05、`Y2_3SLike` 0xC2A4C402（`uinav.py sets`） | [驗] |
| GUI 頁表 | `Y2_3S`/`Y2_3C`/`Y2_3C_ShutterAngle`/`Y2_3SLike` 都是 id 123（0xC0D0DE88..DEA0） | [驗] |
| 根下物件 | `Footer`, `Header`, `Menu`, `LV`, `DialKeyEvent`, `MenuBG`, `AppVars`, `CommonSystemKeyEvent` | [驗] |
| 變數鏡像 | `AppVars`(obj 6590)：`appVariableChangeEvent MV_QSMENU_QS1` → `controlAppVariable Y2n3_MV_QS1 ← MV_QSMENU_QS1`（×8） | [驗] |
| 預覽圖示 | `Icon01_CINE`(obj 103)：`controlAnimation apply-frame = MV_QSMENU_QS1`、`range-upperlimit 48` | [驗] |
| 原生 GUI | `UicGuiMenuQsCustom`（vtable `DAT_c0d1c500`，單例 `0xC37B75C4`），`v25 @C057E7E0` 訂閱、`v26 @C057EA28` 退訂 | [驗] |
| 原生 handler | `MenuQsCustomHandler`：v72 `C0470FE8`、v73 `C0471038`、v95 `C0471100`（開頁時讀 8 格）、v78 `C04711A8`（事件） | [驗] |

清單 CSV（`nbr_stock.py show ../MenuY12/data/Y2_3_CINE.cvm`）[驗]：

```
NO,ID,IMAGE,KEY,memo
1,0,menu_mode,1093,撮影モード
2,1,menu_cine_shutter,1094,…
…
9,20,menu_cine_format,1114,フォーマット
10,21,menu_cine_resolution,1116,解像度
11,22,menu_cine_fps,1118,フレームレート
…
14,25,menu_wb,1121,ホワイトバランス
…
32,48,menu_headPhone,1929,ヘッドホン音量
```

- `ID` = 功能的 UI 編號（= 寫進 `MV_QSMENU_QSn` 的值），`IMAGE` = 清單圖示，`KEY` = `.nloc` 字串 id，`memo` 不用。[驗 CSV；欄位語意 推，Julien 的改法支持]
- CINE 列出的 ID：0,1,2,3,4,8,15,17,20–29,31–39,44–48（32 項）。
- CSV 由誰讀：反編譯裡找不到 `Y2_3_` 字串參照，應是 Y2_3* 頁的 List 元件以名字指定 [推]。

## 2. 設定區裡的表示

### 2.1 app 變數 → 原生 → 設定

```
MV_QSMENU_QSk 被寫（編輯器選定）
  └ UicGuiMenuQsCustom__v25 訂閱 → 回呼 FUN_c057ec70..FUN_c057eed8（k = 0..7）
       v = FUN_c06c7bc0(conv, 新值)          ← UI 編號 → internal（下表）
       handler(+0x44 取得)->vfunc+0x374(v, k)
  └ （MenuAction）FUN_c0061ac8(settings, v, k, 0)   e.g. MenuAction_w71c1__v219 @C04AC840
       → settings 物件（vtable +0x400 取得）FUN_c0065830 → FUN_c0070a38
          發通知 FUN_c001a048(…, 0x20000, …)、vfunc+0x2C 寫入、前後值不同時 vfunc+0x30 + FUN_c00911a0
讀：FUN_c0061b08(settings, k) → FUN_c00913f8 索引 → FUN_c006ea30（含快取 +0x14）
```

[驗] 以上呼叫鏈都在反編譯裡（blk_c05.c:94088–94290、blk_c00.c:72183–72210、blk_c00.c FUN_c0065830/FUN_c0070a38）。
寫入真正落在哪個 FlashValue 欄位（vfunc +0x2C 的實作）**沒追到**。

- **兩組各 8 格**：重設預設 `FUN_c04b4688`（blk_c04.c:136414 起）用 `FUN_c04b5748(tmp, style, …)` 暫時切拍攝風格
  （`FUN_c0058308`），先寫 STILL 8 格 `9,10,11,19,20,22,24,30`，再寫 CINE 8 格 `21,25,40,2,3,9,27,19`（internal 編號）[驗]。
- 原生其它寫入點：`FUN_c053dae0`（blk_c05.c:43660，查 8-byte 表再 `FUN_c0061ac8`）、`FUN_c0401c80`（blk_c04.c:1600）[驗]。

### 2.2 UI 編號 ↔ internal 編號

`FUN_c06c7bc0`：`C0058340()==1`（CINE）用 converter vtable +0x344，否則 +0x340 取表；
`FUN_c06d0fa0(ui, 表, n)` 在 `{internal, ui}` 對中找 `ui`，**找不到回傳 0** [驗]。

兩張 51 對的表（`MenuValueConverterBase__v206 → C2E4300C`、`v207 → C2E431A4`）[驗]，差別只在
UI 1/20/21/22/34：

| UI | 表 C2E4300C | 表 C2E431A4 |
|---|---|---|
| 1 | internal 1、2 | 2、1 |
| 20 | 20 | **21** |
| 21 | 22 | **23** |
| 22 | 24 | **25** |
| 34 | 34 | 35 |
| 25 | 19 | 19 |
| 48 | 53 | 53 |

C2E431A4 對 CINE CSV 合理（UI 20/21/22 = 格式/解析度/格率 → internal 21/23/25，CINE 預設含 21、25），
所以 **C2E431A4 = CINE、+0x344 = v207** [推，vtable 偏移差 8 未核對]。

### 2.3 合法值、驗證、未知 id

- NBU 端：圖示動畫 `range-upperlimit-value 48` → UI 0..48 [驗]。
- 原生端：UI 值查不到 → internal 0。**所以把 UI 值 49+ 寫進 `MV_QSMENU_QSn` 不會把未知值存進設定區**，
  會存成 internal 0（拍攝模式那格）[驗 FUN_c06d0fa0；setter 內 vfunc+0x2C 是否另有範圍檢查 未查]。
- 反過來，若設定區已經有 internal 54+（例如別的 mod 寫的），顯示端怎麼處理沒追 [不確定]。
- **守則角度**：只要寫進設定區的是轉換表左欄裡的值，就是原廠支援的值。

## 3. QS 畫面怎麼依版面畫格子（原廠）

`QS_CINE`（0xC2278C02..0xC239C5FB，1.2 MB，955 個物件）根下 [驗]：

```
Root(1) 1024×682，fill 0x00000000，controlValue -1..7（目前焦點格）→ controlFocus QS_CINE1..8
CommonSystemKeyEvent(245)  QS/半按/全按/REC/MODE/PLAY/TONE… 的 keyEvent
DialKeyEvent(254)          前/後轉盤，見 §8
Footer(299)                每個功能一個「值 holder」+ 底部清單
QS_CINE1(7856) … QS_CINE8(9839)   8 格，每格約 94 KB —— 每格自帶所有功能的圖示
Cursor(10060)、BG(10069)、Button(8553)（AEL 鍵）、OK Btn(9112)…
```

每一格（以 `QS_CINE1` 為例）[驗]：

- focusEvent → `controlAppVariable QS_QSMode ← MV_QSMENU_QS1`（目前焦點格的功能 id 交給全頁共用）。
- `Icon01`/`Icon02`：`appVariableChangeEvent MV_QSMENU_QS1 (≤48)` → `controlAnimation apply-frame MV_QSMENU_QS1`
  ——**用功能 id 當動畫影格**，挑出這格要畫的標籤底板與值圖示。值圖示再由各功能變數（`MV_Resolution` 等）
  自己的動畫挑影格。這就是 QUICK_SET.md 說的「同一群組在 QS_CINE 重複 8 次」的原因。
- 上下左右只做 `controlFocus`；OK → `controlAppState`（app-sync-request 0）；MENU → `sync-request "Menu"`。

**最小介入點（若還要沿用原廠 QS）** [推]：某格功能 id = X（借用的原廠 id）且 BIN 說這格是我們的 →
(1) 圖示：Julien 的做法是換 XCI 像素/換 CSV 圖示名；(2) 文字：drawText 解析 hook `0xC05EC4B4`（fp-native-ui §8h-1）；
(3) 值：Julien hook `0xC05FCE58/D360/D4D0/D4E8/D8E0` 這組 QS 圖磚值/文字繪製。
方向調整後這條路不建議（見 §6–§9）。

## 4. Julien 的先例

### 4.1 R120：DT / Data Rate（解 `FPOG.BIN`，862 筆，舊值全部與 5.02 相符）[驗]

| 補丁 | 內容 |
|---|---|
| `C0F936A4` `C0F93CA8` `C0F94298` `C0F94880` | `Y2_3_CINE` / `_W91C1` / `_angle` / `_angle_W91C1`：`32,48,menu_headPhone,1929,ヘッドホン音量` → `32,48,menu_flash,1929,xxxxxxxx…` |
| `C0F950A8` `C0F958D4` | `Y2_3_SLIKE` / `_W91C1`：`41,48,menu_headPhone,1929,（…）` → `41,48,menu_flash,1929,xxx…` |
| `C145D120` 384 B | `menu_flash.xci`（86×74）像素原地換掉（同尺寸）→ 編輯器裡那列的圖示 |
| `C0731270` 新程式（cave） | 文字解析：鍵 `"1929"` → `"Data Rate"`、`"1793"` → `"DC Crop"`，只在 `[0xC31AE3A8]==1` 且 `C0057AE8()`≠0 且 `C0058340()==1`（CINE）時；否則回原廠 |
| `C2820EF8` 起 132 筆（`Y2_3C`、`Y2_3C_ShutterAngle`、`Y2_3SLike` 範圍） | 編輯器預覽裡的圖示名字指標改指（例：`set_resolution_1` → 池中另一字串的尾段）；README「R117 編輯器圖示正確」 |

- **ID 欄沒動（還是 48）**，所以使用者選「DT」時 `MV_QSMENU_QSn = 48`，設定區存的是耳機音量
  （UI 48 → internal 53）[CSV 驗；internal 值 推]。STILL/SSLIKE 的 CSV 沒改（STILL 回原廠）。
- QS 畫面上那格本來就是 `DISP_HeadphoneVolume` 那格，DATA 內容由他的圖磚繪製 hook 畫（ANALYSIS §4）。

### 4.2 R168：多個新圖磚（`projects/julien-acquaviva/upstream/release/R168/FPOG.BIN`，1013 筆）[驗]

同一招擴大：CINE/SLIKE CSV 裡**保留 ID、只換 IMAGE 與 memo**：

| ID（原廠功能） | 新 IMAGE |
|---|---|
| 15 HDR | `qs_flash_2` |
| 17 DC Crop | `set_cropZoom_1_00` |
| 20 格式 | `qs_formatQuality_6_S` |
| 21 解析度 | `set_cropZoom_1_83` |
| 39 電子防震 | `set_cropZoom_1_91` |
| 48 耳機音量 | `set_cropZoom_2_5` |

→ README 的 SENSOR/RATIO/FPS/CROP/OUTPUT/DATA/RS 都是**借原廠功能 id**，設定區永遠只存原廠 id。[驗 CSV；對應名稱 推]

## 5. 若要在編輯器加我們的項目（舊主線，保留）

只讀原廠資料 + 1 個 hook 就夠的做法 [推]：借一個 CINE 用不到的原廠 id（例：48 耳機音量或 15 HDR），
CSV 用 fp-ui-add 的 add_option/取檔處理器換 IMAGE/KEY，文字走 `C05EC4B4` 或私有字串；
設定區存的是那個原廠 id；BIN 記「借了哪個 id」。不要寫 UI 49+（會被轉成 0，使用者那格變成拍攝模式）。

---

## 6. A. QS 是怎麼被打開、怎麼關閉的

### 6.1 打開 [驗]

```
LV_CINE_LARGE/MEDIUM 頁  CommonSystemKeyEvent(obj 5222)
   keyEvent QS (args 0x14)                         @0xC1E0DD9A
   controlAppVariable SYS_SubmenuOpen
   controlAppState {} 
   controlAppState "to QS Menu screen" sync-request "QS", view-state-event 1   @0xC1E0DE22（mask 0x21）
另一入口：ChangeScreen(obj 131) appVariableChangeEvent CM_TransitionFlag==2 → sync-request "QS" @0xC1E10610
          （從 QS 進子選單、返回時回到 QS 用）
另有 KeyEvent(obj 9111) keyEvent QS @0xC1E11149
```

NBM `0xC2DE3D20`，17 台狀態機（`dump_nbm.py`）[驗]：

```
TransSystem（第 2 台；68 狀態、113 轉換）
  WildCard   —"QS"→  Choice0002
  Choice0002 —(LV_ShootingStyle:v()==0)→ QS_STILL
  Choice0002 —(LV_ShootingStyle:v()==1)→ QS_STILLlike
  Choice0002 —(LV_ShootingStyle:v()==2)→ QS_CINE
  QS_CINE —"B1_1"/"B1_2"/…/"B2_5"/"B2_6"/"B2_1"/"B3_1"/"Y4_1_3"…→ 子選單（22 條）
TransLevel2: Y2_6_3_3 —Return→ Choice0002
```

- **`QS_Common`**：不是頁（GUI 頁表沒有它、狀態機沒有它），是共用資源集；根 fill 0x000000FF [推：共用片段/背景]。
- `QS_STILL`/`QS_STILLlike`/`QS_CINE` 在 GUI 頁表都是 **id 159**（0xC0D0DDB0..C0）[驗]，
  對應原生 `UicGuiMenuQs`（單例 `0xC37B75C8`）+ `MenuQsHandler`（`C0471570..C0473E80`）[推：由訂閱回呼用的單例推得]。

### 6.2 關閉 [驗]

- QS 頁 `CommonSystemKeyEvent`(245) keyEvent QS @0xC2289444 → `controlAppState` @0xC22894CA
  「to LV screen」：mask **0x22** = `app-sync-request 0` + `view-state-event 1`，**沒有 sync-request 字串**。
  OK Btn(9112) @0xC22890A5 同一形式。每格的 OK（@0xC228B331）也是 app-sync-request 0。
- 也就是說回 LV 是「原生 app 狀態請求 0」，不經 NBM 字串事件 [推：語意]；
  NBM 那邊 `TransLV: WildCard —"LV"→ Choice0001 → FontSize0/1/2 → LV_*` 是用 `LV` 事件的路徑。
- 半按/全按/REC 先 `sync-request "ClearFlg"(to-uic)` 再 app-sync-request 0。

### 6.3 讓 QS 鍵改去我們的頁：可行做法

**轉換比對順序（離線模擬，[驗]）**：`emu_two_machines.py` 用真的解譯器與比對器 `FUN_c05ed028`
跑出「**app+0xF4 上越前面的狀態機先命中**」。原廠 NBM 開機就註冊；我們的私有包（§8g）之後才 push_back，
所以**在私有包裡加 `(LV_*/WildCard, "QS") → 我們的頁` 會輸給原廠 `TransSystem`，不會生效。**

| 做法 | 內容 | 要改的 | 風險 |
|---|---|---|---|
| **Q1 換 `QS_CINE` 項目位移（建議）** | 和 fp-native-ui §8a 一樣：把名字 `QS_CINE` 的執行期項目 `entry+08` 改成 `(我們的頁 − C18C0460)`；狀態機照舊轉到 `QS_CINE`，畫的是我們的記錄 | 1 個字（RAM）；還原就是寫回原值 | ①QS_CINE 什麼時候被解析/快取（MainB2 是開機快取、開選單時釋放、顯示時 `C05E82F1` 重解）未查；若是常駐快取，要在第一次打開前換或要讓它被釋放。②原生 `MenuQsHandler`/`UicGuiMenuQs` 會呼叫 view 物件方法（`+0x48C/+0x490/+0x5D8/+0xCC`、`FUN_c0472b48`、`FUN_c04720f0`），若依賴原廠物件存在，缺了可能出錯 → 頁面先從**完整 QS_CINE 複本**開始刪（§8g-4 教訓）。③STILL/STILLlike 不受影響（沒換） |
| Q2 改 LV 端請求字串 | LV_CINE_LARGE/MEDIUM 的 `sync-request "QS"`（@C1E0DE22、ChangeScreen @C1E10610、obj 9111 那筆）改成 `"FPQS"`，私有包加 `WildCard —FPQS→ 我們的頁`、我們的頁 —子選單…→ | LV 兩頁 × 3 筆記錄（要在 LV 頁解析前改，或換整頁）＋私有狀態機＋ GUI 頁表 hook `C056461C` 回 159 | LV 頁是常駐的、多份；改字串影響 CM_TransitionFlag 回 QS 的路徑；別的畫面（WildCard）按 QS 仍去原廠 |
| Q3 hook 比對器 | 在 `FUN_c05ed028` / matcher（`FUN_c05dd448` 呼叫它）入口：`cur ∈ LV_CINE_*`、`req=="QS"`、我們開著 → 把 req 換成 `"FPQS"` | 1 個程式 hook（ROM 程式區）＋私有狀態機＋頁表 hook | 每次轉換都經過，寫錯整個 UI 不能換頁；但最集中、STILL 判斷容易 |
| Q4 改原廠 NBM 記錄 | `Choice0002 → QS_CINE` 的目標字串偏移指到我們的頁名 | NBM 記錄在開機註冊時就被讀進 heap，要在註冊前改或改 heap 物件 | 時機與 heap 位址每次開機不同；不建議 |

- 不論哪個，**GUI id 要是 159**（`UicGuiMenuQs`），原生訂閱（§8）才會在我們的頁上生效。Q1 天生如此（名字不變）；
  Q2/Q3 要用 §8g-3 的 `C056461C` hook 讓我們的頁名回傳 159 [推]。
- 回 LV：沿用 QS_CINE 的 `CommonSystemKeyEvent`/`OK Btn` 那幾筆（app-sync-request 0）即可 [推]。
  子選單（AEL → `B2_5` 等）回來靠 `CM_TransitionFlag=2` + LV 的 ChangeScreen 再送 `"QS"`；Q1 下會回到我們的頁 [推]。

## 7. B. 是不是疊在 live view 上的圖層

- 根物件 `fill`（tag 0x10005）位元組 [驗]：

  | 頁 | Root fill 第 7 個 word |
  |---|---|
  | `QS_CINE`、`QS_STILLlike`、`LV_CINE_LARGE` | `00000000` |
  | `QS_Common` | `000000FF` |
  | `MainB2`、`B2_5` | `FFFFFFFF`（B2_5 另有 mask 2 與尺寸 1024×682） |

  → QS 和 LV 頁一樣是「透明底的全螢幕 OSD 頁」，選單頁是不透明底 [推：該 word 是 RGBA 填色]。
  不是另一種「疊加層物件」：一次只有一張 GUI 頁，影像在另一個平面，所以截圖要 `display capture <path> 3 2`
  拿 OSD 主層（ARGB4444，fp-native-ui §6）。
- QS 的半透明格子是各自的 `BG`/`drawRect`/圖片畫出來的，不是整頁 alpha [推]。
- **我們的私有頁要做到一樣**：根物件 `objectBase size 1024×682` + `fill` 用 QS_CINE 的那筆（填色 0）[推]；
  其餘照 §8g（私有 NBR 包、0x10001 索引、0x50001-4、`C05E84D8` 註冊）。用 Q1 的話連註冊都可以省掉，
  只要把頁面放在常駐記憶體，換 `entry+08`。

## 8. C. 原廠一格圖磚怎麼改設定

### 8.1 NBU 這一側 [驗]

`DialKeyEvent`(254)：controlValue −1..48、`appVariableEvent component-id 5`；四個子物件 `FR/FL/BR/BL` 各一組
`controlAnimation apply-frame QS_QSMode`——**依目前格的功能 id 只開那一格的 keyEvent**。每個 keyEvent 做：

```
FR keyEvent N:  changePropertyByControl(holder_N.controlValue.value, "dst + 1")   ← 大多數功能
FR keyEvent 8/16:  controlAppState sync-request "Fdial_R"                      ← 交給原生
```

Footer 下的值 holder（例）：

| holder | 綁的變數 | controlValue |
|---|---|---|
| obj 301 `0` | `CM_ShootingMode` | max 9、loop |
| obj 341 `19` | `MV_RecordingFormat` | |
| obj 343 `20` | `MV_Resolution` | loop；`appVariableChangeEvent QS_QSMode==21` 時顯示游標/箭頭 |
| obj 345 `21` | `MV_FrameRate` | max 8、loop；`QS_EXCL21 ← EXCL_FrameRate`（反灰） |
| obj 319 `18` | `CM_WhiteBalance` | |
| obj 323 `22` | `MV_AudioRecord` | |
| obj 324 `23` | `CM_COLAJ_ColorMode`（`CM_COLFIX_ColorMode` 複製過來） | max 15 |

快門/ISO 的 holder 用索引變數（`CM_ShutterSpeedIndex`、`CM_ShutterSpeedItem`；ISO 在 obj 10584 `CM_ISOSensitivity component-id 3`）[驗]。

⚠ 編號差一：holder 名字 `20`（Resolution）對應 `QS_QSMode==21`；CSV 裡 Resolution 的 ID 是 21。
轉盤 keyEvent 的編號 20 → holder 343。所以「物件名/keyEvent 影格號 = 功能 id − 1」或 DialKeyEvent 的 −1 起點造成位移 [推，要上機核對]。

holder 上沒有看到 `controlAppVariable(變數 ← controlValue)`，只有 `appVariableEvent 變數`；
所以**原廠 QS 靠 appVariableEvent 的雙向綁定把 controlValue 寫回 app 變數** [推]。
（fp-native-ui §8b r35 我們自己的列是另外加 controlAppVariable 才寫得回去 —— 兩者矛盾，第一個對照卡就測這個。）

AEL 鍵（`Button`/obj 8514，key 0x13）[驗]：依 `QS_QSMode` 影格，`CM_TransitionFlag=2`、`MENU_Level1/2`、
`CM_MenuTabNo` 設好後 `sync-request "B2_5"`（格式/解析度…）、`"ModeButtonMenuSetC"` 等 → 打開完整設定頁，返回時回 QS。

### 8.2 原生這一側 [驗]

`UicGuiMenuQs__v25 @C05806B8` 一次訂閱約 70 個變數（`FUN_c0560fb0(reg, 名字, 回呼)`），v26 @C0580D48 退訂。回呼形狀都一樣：

```
v = Converter(conv=[0xC37B75C8][0xD], 新值)
handler = ([0xC37B75C8]->vfunc+0x44)()
handler->vfunc+OFF(v, 1)
```

| 變數 | 回呼 | 轉換器 | handler 偏移 |
|---|---|---|---|
| `MV_Resolution` | `FUN_c05824d0` | `FUN_c06bd9e0` | +0x13C |
| `MV_FrameRate` | `FUN_c05821b8` | `FUN_c06bdab0` | +0x140 |
| `MV_RecordingFormat` | `FUN_c0582528` | `FUN_c06bd6a0` | +0x12C |
| `CM_ISOSensitivity` | `FUN_c0581690` | `FUN_c06bc2c8` | +0x44 |
| `CM_WhiteBalance` | `FUN_c0582210` | `FUN_c06bedf0` | +0x160 |
| `CM_HeadphoneVolume` | `FUN_c0582ab0` | | （Julien hook 了這支與 `FUN_c0582420` ST_DNGQuality） |
| `QS_QSMode` | `FUN_c0582d28` | | |

`handler` 的偏移是 MenuAction 系的 setter（同形狀的 `MenuAction_w71c1__v219` 就是 QS 格子的 setter）[推]，
之後才是設定層的正規化（fp-native-ui §3b「選得進去不代表值留得住」）。B2_5 頁的 GUI（blk_c05.c:90861）也訂閱
`MV_Resolution`/`MV_FrameRate`，所以同一個變數在選單頁、QS 頁都走原廠 setter。

`MenuQsHandler__v86 @C0471E40`：處理 `QsShutterPushedDisp`、`QsAperturePushedDisp`、`Fdial_L/R`、`Bdial_L/R`
（→ `FUN_c0471fd0(±1)`），依的是畫面類別號（+0x70：1..3、0x2F）而不是 QS_QSMode [驗程式；語意 推]。

### 8.3 我們的頁最少需要什麼 [推]

- 頁的 GUI 是 159（Q1 天生；Q2/Q3 用頁表 hook）→ `UicGuiMenuQs` 的訂閱在 → **只要綁同一個原廠 app 變數**
  （`MV_Resolution`、`MV_FrameRate`、`MV_RecordingFormat`、`CM_ISOSensitivity`…），寫入就走原廠轉換器、setter、正規化。
- 寫入方法照原廠 holder：controlValue（loop、max）+ `appVariableEvent` 綁變數 + 轉盤/上下鍵
  `changePropertyByControl dst±1`；若雙向綁定實測不成立，就加 `controlAppVariable(變數 ← controlValue)`（r35 做法）。
- **res-custom 的格式/格率/位深不是原廠值**：不要直接綁 `MV_Resolution`。綁私有變數（`SL_…`），原生回呼
  （`C0560FB0` 訂閱）把選擇記進 BIN，必要時再用 `C0593F30` 把**原廠合法值**寫進 `MV_Resolution`/`MV_FrameRate`
  （例如 donor 解析度與它的格率）。這樣設定區永遠只會收到原廠值（第一守則）。
- 反灰：原廠用 `EXCL_FrameRate` → `QS_EXCL21`，我們的頁可直接讀同一個 EXCL 變數。

## 9. D. QS 畫面能不能用 drawText

- **能** [驗]：`QS_CINE` 有 6 筆 drawText（`Text` @0xC237BB59/0xC237D671/0xC237EB01、`LockMessage` @0xC23951F2、
  `String` @0xC2397E2E、`Option` @0xC2397FBB），`font-setting "fontsetting"`、`font-size 0x36`。
- 字型/元件限制：原廠 QS 文字都用 `.nloc` 鍵（`1910`、`1422`）。fp-native-ui §8b：`.nloc` 鍵換頁可能畫不出來
  （`0315` 在 SL_LAB 空白）→ 我們的值文字用**字面字串或字串 app 變數**（r43 形式：`appVariableEvent` 帶
  component-id = drawText 區域編號、mask 0x2F、58 B）。Q1 下頁名還是 `QS_CINE`，.nloc 鍵可能可用 [推]。
- 數字欄 `drawImageLayout`（QS_Digits 字元表）也在 QS 裡（98 筆），r31/r38 的方法同樣適用 [驗存在；行為 推]。

## 10. 建議設計

### 設計 Q1（建議）：整頁替換 `QS_CINE`

1. 建卡時從原廠 `QS_CINE`（0xC2278C02..0xC239C5FB）產生我們的頁：保留 `Root`(fill 0)、`CommonSystemKeyEvent`、
   `OK Btn`、`Cursor`/`BG`、`DialKeyEvent` 的骨架；把 8 個 `QS_CINEn` 換成我們自己的格子（一格一個功能，
   drawText + 私有/原廠 app 變數），一次做一項（解析度/格式 → 格率 → 位深 → ISO/快門…）。
   新物件與動作**從 QS_CINE 自己的記錄複製**（§8b：跨頁 donor 會安靜失效）。
2. 開機在 UI 執行緒把 `QS_CINE` 項目 `entry+08` 改成我們頁的位移（動手前比對原廠位移）。STILL 不換。
3. 原廠設定（ISO、快門、WB）綁原廠變數 → 原廠 setter；res-custom 項目綁私有變數 → BIN。
4. 要 hook 的：**0 個程式 hook**（若 QS_CINE 是常駐快取，可能要多一個「讓它重解」的處理）。
   原廠資料全部只讀。
5. 關掉 = 寫回原位移。

### 設計 Q3（備案）：比對器 hook + 私有頁

`FUN_c05ed028` 入口 1 個 hook 把 `(LV_CINE_*, "QS")` 改成 `"FPQS"`，私有包加狀態機與頁、`C056461C` 讓頁名回 159。
好處是原廠 QS 頁完全不動、可隨時切回；壞處是 2 個程式 hook，且子選單返回路徑要自己補。

### 風險與設定區

- 設定區只會經原廠 setter 收到原廠變數的值；**不要把 res-custom 的 index 寫進 `MV_Resolution` 等原廠變數**。
- 自訂 QS 版面（`MV_QSMENU_QSn`）在 Q1/Q3 都不用動；我們的版面存 BIN。
- 若仍想讓「自訂 QS 編輯器」能放我們的項目：只借原廠 id（§5），絕不寫 UI 49+（會變成 internal 0）。

## 11. 待上機確認（全部要先問使用者）

1. QS_CINE 的解析/快取時機（換 `entry+08` 後第一次按 QS 是否就讀新頁）。
2. 原廠 holder 的 `appVariableEvent` 是否雙向（只改 controlValue，`MV_*` 會不會變）。
3. 「功能 id 與物件名差一」的實際對應。
4. 我們的頁缺少原廠物件時，`MenuQsHandler`/`UicGuiMenuQs` 的 view 方法會不會出錯（差分：完整複本 vs 刪掉一格）。
5. 自訂 QS 那兩張轉換表哪張是 CINE（讀 `MV_QSMENU_QS1` 與設定值各一次即可，`mem get` 已授權）。

---

## 12. RES/FPS/FMT 圖磚替換（2026-10-20 定案方向）

定案：使用者用原廠「自訂 QS」把 RES/FPS/FMT 放在任一格（設定區只存原廠 id），我們用 Q1
（換 `QS_CINE` 的 `entry+08`）把頁換成「QS_CINE 複本 + 這三種圖磚改寫」，其他功能維持原廠。
本節仍全部離線。資料來源：`nbu_components.walk()` 走過整個 QS_CINE（955 物件、8518 元件、4224 clip）、
自己解的 `0x1000B` 動畫群組、keyEvent/clip 原始位元組。

### 12.1 三個功能的編號 [驗，internal 一欄 推]

| 功能 | CSV `Y2_3_CINE.cvm` 列 | UI 編號（= `MV_QSMENU_QSn` = `QS_QSMode`） | internal（設定區；C2E431A4 表） | IMAGE / KEY（CINE） | SLIKE 的 KEY |
|---|---|---|---|---|---|
| FMT | 9 | **20** | 21 | `menu_cine_format` / 1114「フォーマット」 | 1115「画質/フォーマット」 |
| RES | 10 | **21** | 23 | `menu_cine_resolution` / 1116「解像度」 | 1117「画像サイズ/解像度」 |
| FPS | 11 | **22** | 25 | `menu_cine_fps` / 1118「フレームレート」 | |

- 圖磚影格時間 = UI 編號 × 33.3：`Icon01` 標籤 clip（@0xC228B9C4）666 = `menu_cine_format_qs`、
  700 = `menu_cine_resolution`、733 = `menu_cine_fps`，一路到 1600 = `menu_headPhone`（48）[驗]。
- **FMT = 錄影格式 + 畫質**：值的顯示用 `MV_RecordingFormat` 選 DNG/MOV 兩段，DNG 段的影格是 `MV_DNGQuality`
  （位深 12/10/8）、MOV 段是 `MV_MOVQuality`（§12.3）。QS 裡轉盤只改 `MV_RecordingFormat`；
  位深在 QS 裡**沒有**可調的 holder，要經 AEL → `B2_5`（§12.4）[驗]。
  所以「位深」沒有自己的 QS 功能 id，只能當 FMT 圖磚的一部分顯示（與 IMX410_FULL_DESIGN 的結論一致）。
- **物件/群組名字和 keyEvent 名字 = UI 編號 − 1**（`19_MV_RecordingFormat`、`20_MV_Resolution`、holder 名 `19/20/21`、
  轉盤 keyEvent `19/20/21`）。§8.1 的「差一」已查清：keyEvent `20` 的 local id 0x2C，在 FR 的 keys clip
  （@0xC2344994，以 local id 對應）只在 700 = UI 21 開啟；`19`(0x2B)→666、`21`(0x2D)→733 [驗]。
  比對用的 `QS_QSMode equal-value` 就是 UI 編號（holder 341==20、343==21、345==22）[驗]。

### 12.2 8 格的結構與同構性

格子根物件：`QS_CINE1` 7856、`QS_CINE2` 9599、`QS_CINE3` 9639、`QS_CINE4` 9679、`QS_CINE5` 9719、
`QS_CINE6` 9759、`QS_CINE7` 9799、`QS_CINE8` 9839 [驗]。記錄區段：

| 格 | 記錄範圍 |
|---|---|
| 1 | 0xC228B0B5..0xC22A1D6F |
| 2 | 0xC22A219D..0xC22B8E5C |
| 3 | 0xC22B928A..0xC22CFF49 |
| 4 | 0xC22D0377..0xC22E7036 |
| 5 | 0xC22E7464..0xC22FE123 |
| 6 | 0xC22FE551..0xC2315210 |
| 7 | 0xC231563E..0xC232C2FD |
| 8 | 0xC232C72B..0xC23433EA |

**同構** [驗]：每格 44 個物件、464 個元件、462 個 clip；clip 內容 8 格**完全相同**；
元件只有 25 處不同，全是「格子位置、`MV_QSMENU_QSn` 的 n、`QS_FocusPos` 值、controlFocus 目標、物件 id」。
→ 同一個轉換規則套 8 次即可，只要每格換一張物件 id 對照表（id 不是等距，例如 Icon02 = 7859/9601/9641/9681/9721/9761/9801/9841）。

一格（格 1）的樹（只列和三個功能有關的）：

```
QS_CINE1 7856           focus → QS_QSMode ← MV_QSMENU_QS1；OK → app-sync-request 0；MENU → "Menu"
├ Icon01 7858           drawImage；clip 50 依 MV_QSMENU_QS1 影格挑標籤圖（menu_cine_format_qs / _resolution / _fps）
└ Icon02 7859           animation 群組 "Icon02"（@0xC228BEA9）依 MV_QSMENU_QS1 影格，開關 QSMENU 的事件（clip 68 type）
   ├ QSMENU 7860        值變化事件（§12.3）→ 播放值群組
   ├ Icon 7914          大值：drawImage；RES 用 clip 12（位置 53,108、150×38） = font_menu_MB_resolution_1/_2
   ├ Icon3 7969 ─┬ Icon 7922   小值 drawImage 86×49：clip 57 qs_formatQuality_*_S、62/66 qs_fps_*_S、65 qs_resolution_*_S
   │             └ s 7970      "p" 字尾 qs_fps_tex_S
   ├ Digits 10753 / Digits3 10754 / aperture 10897 / TC 10896 / font_menu_LB 10991 …（別的功能用；值群組會把它們關掉）
```

「調整中」狀態 [驗]：**同頁**，不開別的頁或 popup。按上下左右只換焦點格；轉盤直接改值；
選中時 Footer 下 `QSMode`(339) 裡該功能的 holder 播 `Cursor`/`Arrow` 動畫（FPS 的 holder 345 還會 is-visible=1、`Dial ON`、
`FooterColor White`）。只有 AEL 鍵（key 0x13，`Button`/`AEL` 8514）會開別的頁：FMT（keyEvent 19 @0xC23989C4）
→ `CM_TransitionFlag=2`、`CM_MenuTabNo=1`、`MENU_Level1=650`、`MENU_Level2=4247` → `sync-request "B2_5"`；
RES/FPS（keyEvent 20/21 @0xC2398B0B/@0xC2398C1F）設好同樣的變數後啟動 controlTimer 10679/10680（之後應該也開 B2_5）[推]。

### 12.3 值現在怎麼顯示 [驗]

每格的 `QSMENU`(7860) 有值變化事件，但只在格子影格對的時候啟用
（`Icon02` 群組 → 7860 clip 68 的 `type`：在 666/700/733 為 3，其餘為 0）：

| 事件（格 1 位址） | 監聽 | 播放的群組（擁有者 Icon02 7859） |
|---|---|---|
| `19_1` @0xC229027B | `MV_RecordingFormat` | `19_MV_RecordingFormat` interval DNG，影格 = `MV_DNGQuality` |
| `19_2` @0xC229034C | `MV_RecordingFormat == 1` | 同上 interval MOV，影格 = `MV_MOVQuality` |
| `19_3` @0xC22919D8 / `19_4` @0xC2291A3C | `MV_DNGQuality` / `MV_MOVQuality` | 同上 |
| `20` @0xC2290421 | `MV_Resolution` | `20_MV_Resolution`（影格 MV_Resolution）＋ `35_MV_TimeCodeRate`（影格 MV_FrameRate） |
| `20_2` @0xC2290529 | `MV_FrameRate` | `20_MV_Resolution` ＋ `20_MV_TimeCodeRate` |
| `21_1` @0xC2290631 | `MV_FrameRate` | `21_MV_FrameRate` ＋ `21_MV_Resolution` |
| `21_2` @0xC2290735 | `MV_Resolution` | 同上 |

群組（`0x1000B`，格 1；其他 7 格同形，位址見下）的 C 欄 = 要播的 `(物件, clip)`；
每個群組都會列出**所有兄弟物件的「隱藏」clip**，再把自己要的物件打開：

```
19_MV_RecordingFormat @0xC228C298: (7914,11 隱藏) (7969,10 顯示 Icon3) (7922,57 qs_formatQuality_*_S) (7970,6) …
20_MV_Resolution      @0xC228C346: (7914,12 顯示＋font_menu_MB_resolution_1/2) (7969,2 顯示 Icon3) …
20_MV_TimeCodeRate    @0xC228CF2C: (7922,66 qs_fps_*_S) (7970,7 "p") …            ← RES 圖磚下方的小格率
21_MV_FrameRate       @0xC228C3CF: (7914,13 隱藏) (7969,9) …
21_MV_Resolution      @0xC228CD3E: (7969,24) (7922,65 qs_resolution_*_S) (7970,5) …   ← FPS 圖磚上的小解析度
```

8 格的 `20_MV_Resolution`：0xC228C346、0xC22A3433、0xC22BA520、0xC22D160D、0xC22E86FA、0xC22FF7E7、0xC23168D4、0xC232D9C1；
`19_MV_RecordingFormat`、`21_MV_FrameRate`、`21_MV_Resolution`、`20_MV_TimeCodeRate` 都在同一格的相鄰位址（`grp.py` 列表）。

→ **值 = 依變數值挑 .xci 的動畫影格**（每 33 ms 一個值）。RES 只有 2 張大圖（FHD/UHD 等級），
FPS 9 張 `qs_fps_*_S`，FMT 5 張 `qs_formatQuality_*_S`。沒有任何 drawText。

**可當樣板的 drawText**（全部在 Footer，不在格子裡）[驗]：

| 物件 | 路徑 | 用途 |
|---|---|---|
| 11484 `Text` | Footer › QSMode 339 › `24_W91C1`(音訊增益) › EXCL=0 › Auto › EXCL=1 | 文字 `.nloc 1910`，灰色 888888，「無法調整」說明 |
| 11481 / 4607 `Text` | 同上 Manual › Ch1/Ch2 | 同上 |
| 11473 `String` | Footer › QSMode › `48` › EXCL=1 | 同上（耳機音量） |
| 809 `LockMessage` | Footer › QSMode › `36`(鎖定) | `.nloc 1422` |
| 8512 `Option` | Footer | 文字由動畫 `Option`（影格 QS_FooterGuid1）換；另有 `appVariableEvent submenu_width component-id 4` |

全部 `font-setting "fontsetting"`、`font-size 0x36`。**沒有一個是「text 綁字串變數」**；8512 有 appVariableEvent
帶 component-id 的同頁樣板，可改 `property-name text` 用（r43 形式）[推]。

### 12.4 值改變的路 [驗]

```
轉盤（FR args 未記、FL 0x31、BR 0x41、BL 0x40；DialKeyEvent 254 的 FR/FL/BR/BL 子物件，
     keys clip 依 QS_QSMode 只開一個 keyEvent）
  FMT  keyEvent 19 → changePropertyByControl(obj 341.controlValue, dst±1)   FR @0xC2344192 / FL @0xC23464B2 / BR @0xC2348842 / BL @0xC234ABD2
  RES  keyEvent 20 → obj 343                                               FR @0xC23441F1 / FL @0xC2346515 / BR @0xC23488A5 / BL @0xC234AC35
  FPS  keyEvent 21 → obj 345                                               FR @0xC2344250 / FL @0xC2346578 / BR @0xC2348908 / BL @0xC234AC98
holder（Footer › QSMode 339，全頁一份，8 格共用）
  341 '19' controlValue loop            appVariableEvent @0xC2371AD1  MV_RecordingFormat
  343 '20' controlValue loop            appVariableEvent @0xC23724C7  MV_Resolution
  345 '21' controlValue max 8, loop     appVariableEvent @0xC2372B4D  MV_FrameRate；EXCL_FrameRate → QS_EXCL21
     appVariableEvent 的 type = 1。type 的列舉字串（@0xC2E000FC）是 "A2P" / "A2P+P2A"
     → 1 = 雙向：controlValue 被改 → 寫回 app 變數
  → app 變數改變 → UicGuiMenuQs__v25 的訂閱回呼（§8.2：MV_Resolution → FUN_c05824d0 → +0x13C；
     MV_FrameRate → FUN_c05821b8 → +0x140；MV_RecordingFormat → FUN_c0582528 → +0x12C）→ 原廠 setter
  → 同一個變數的變化觸發各格 QSMENU 事件 → 換圖（§12.3）
```

- 這三個功能**不經過** `Fdial_*`/`Bdial_*` sync-request，也不經過 `MenuQsHandler__v86`
  （只有 keyEvent 8、16 送 Fdial_R）[驗]。
- §8.1 的疑點已解：原廠 holder 是雙向綁定（type 1），我們 r35 的列沒寫回，大概是因為 type 是 0（A2P）[推]。

**改成「改私有變數、觸發我們的回呼」最少要動**：

1. holder 343（RES）：appVariableEvent @0xC23724C7 的 `variable-name` `MV_Resolution` → `SL_QsRes`
   （type 維持 1）；controlValue @0xC237249F 加上 `max-value = 選項數 − 1`（mask 變、記錄變長）；
   它自己的 `appVariableChangeEvent MV_Resolution`（@0xC2372546）和兩個 `Cursor2 apply-frame MV_Resolution`
   （@0xC237256F/@0xC23725CE）也換成 `SL_QsRes`（只影響 Footer 游標動畫，可以後做）。
2. 轉盤 keyEvent 不用改，它們本來就是改 holder 343 的 controlValue。
3. 原生：`C05DB309` 註冊 `SL_QsRes`（整數）與 `SL_QsResText`（字串，型別 2）、`C0560FB0` 訂閱 `SL_QsRes`
   → 回呼呼叫 res-custom 核心 API → `C0593FE0(0, "SL_QsResText", 字串)`。
   需要原廠側也跟著變時，用 `C0593F30(0, "MV_Resolution", 原廠合法值)` → 經 v25 → 原廠 setter（只寫原廠值）。

**原生會不會多做事** [推]：`MV_Resolution` 沒變時，v25 的 `FUN_c05824d0` 不會被呼叫，各格的 QSMENU `20`/`21_2`
事件也不會觸發；`MenuQsHandler` 不看這三個變數。我們主動寫 `MV_Resolution`（donor）時才會走原廠 setter，
還會觸發原廠圖示更新（被我們藏起來的那張也會跟著更新，沒有壞處）。
FPS 圖磚上的小解析度（`21_MV_Resolution` → qs_resolution_*_S）會顯示 donor 的原廠解析度，等換 FPS 時一起處理。

### 12.5 一次替換一種（先 RES）的工作量估算 [推]

| 範圍 | 記錄 | 說明 |
|---|---|---|
| Footer holder 343 | 1–4 筆修改 | §12.4-1（最少只改 variable-name 1 筆；加 max-value 1 筆） |
| 每格：藏原廠大值 | 8 筆修改 | `20_MV_Resolution` 群組的 `(7914,12)` 換成 `(7914,13)`（7914 的隱藏 clip；同長，只改 4 B）。小格率（`7969,2` 與 `20_MV_TimeCodeRate`）要不要藏另外決定 |
| 每格：新的值文字物件 | 8 × 約 8 筆新增 | `0x10003` 物件（掛在 Icon02 下）+ objectBase（在 clip 12 給 7914 的位置 53,108，150×38）+ drawText（照 Footer 11484 的欄位，字面空字串）+ appVariableEvent（text ← `SL_QsResText`，component-id = 這個 drawText 的區域編號，r43 形式）+ 顯示/隱藏：`appVariableChangeEvent MV_QSMENU_QSn equal 21` → `changePropertyByControl is-visible 1`，greater/lower 21 → 0（照 holder 345 的模式，同頁樣板） |
| 頁標頭 | 1 筆 | `0x10002` 元件配額（removed/plus）要重算（§8b r56） |
| 程式 hook | **0** | 只用既有機制：`entry+08` 換頁、變數註冊、`C0560FB0` 訂閱、`C0593FE0`/`C0593F30` 寫值 |

合計約 **80 筆新增 + 10 筆修改**。FPS 規模相同（holder 345；群組 `21_MV_FrameRate`、`21_MV_Resolution`；
多一個 `QS_EXCL21 ← EXCL_FrameRate` 的反灰要決定保留或換成私有 EXCL）。
FMT 也一樣（holder 341；群組 `19_MV_RecordingFormat` 的兩個 interval；位深只顯示、由我們的字串一起表示）。

**風險**：

- **id 衝突**：原廠物件 id 最大到 11686（955 個）→ 新物件從 11687 往上發；每個物件的事件（+28）與 clip（+24）
  共用本地編號，新的要取兩者最大值 + 1（§8b 2026-10-03 的當機坑）。
- **同頁 donor 規則**（§8b）：所有新元件從 QS_CINE 自己的記錄複製（drawText ← 11484；顯示/隱藏事件 ← holder 345；
  text 綁定 ← 8512 的 appVariableEvent 改 property-name）。r43 的 drawText 綁定是在 SL 頁驗證過的，
  在 QS 頁還沒驗證過。
- **原廠群組會蓋過新物件**：原廠群組只會列出原廠的兄弟物件，不知道我們的新物件，所以切到別的功能時不會被它們藏起來。
  這就是要用「自己監聽 MV_QSMENU_QSn」控制顯示的原因。要小心 `Icon02` 群組播放的時機和我們事件的先後
  （若有閃爍，就把新物件也加進 `Icon02` 群組的 C 欄，再加一個依影格開關的 clip）。
- **原生期望的物件**：`MenuQsHandler`/`UicGuiMenuQs` 的 view 方法（§6.3 Q1 風險②）——這個做法沒有刪掉任何原廠物件，
  只有新增與改變數名，風險比整頁重寫小。
- **holder 343 是 8 格共用**：改了以後，RES 不論放在哪一格都走私有變數（這正是我們要的），
  但同時也**沒有任何一格**能直接用轉盤改原廠解析度（原廠解析度只能從 B2_5 改，或由我們的回呼寫 donor）。
- **`entry+08` 換頁的快取時機**（§11-1）仍是第一個要上機確認的。
- **STILL / STILLlike** 不受影響（只換 QS_CINE）。
