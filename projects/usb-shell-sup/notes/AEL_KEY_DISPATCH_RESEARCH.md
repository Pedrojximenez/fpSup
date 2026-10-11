# AEL 按鍵派送鏈 —— 為什麼 FT_LIST 收不到 AEL(離線調查 2026-10-08)

範圍:SIGMA fp Ver.5.02,`out/MAIN_c0000000.bin`(base 0xC0000000)、`out/decomp/full/blk_c0*.c`。
**全部離線,未上機。** 標「未驗證」的是推論。

## 0. 結論先講

1. 派送鏈分三層,每層都查過,**對 AEL 都沒有「主選單衍生頁才擋」的邏輯**:
   app 選單處理器 `v16` → 處理器自己的 GUI 物件 `v1` → GUI 佇列 → UIC 的 keyEvent 比對。
2. app 頁表的 12-byte「handler」**跟按鍵無關**:它是「回傳 `{"submenu_NN", x 位置}` 表」的取值函式(依語言索引),只管彈出子選單的版面。
3. 唯一找到的 AEL 與 OK 差異:**訊息類別**。OK 在 Y5 類別送成「characters-keys」(0x40/0x80),
   AEL 和 DISP 在**所有**選單類別都送成「system-keys」(0x100/0x200)。我們的 AEL 記錄
   與原廠 B3_5_5 的 AEL 記錄形式完全相同(`keys` 用預設 3 = 兩類都收),所以記錄本身應該不是原因。
4. 因此 AEL 在 app 層被吃掉,或是 UIC 對 system-keys 走不同的路由 —— **兩者離線都無法定案**,
   要用下面的 `gui key` 注入測試分辨(繞過 app 層,直接進 GUI 佇列)。
5. `gui key` 的參數順序跟說明文字**不一樣**:實際上是 `gui key <GuiKeyType> <class> [<on>]`。
   `gui key 0 19 1` = 按下 ShutterHalf(system-key)**卻從沒放開** —— 很可能就是先前 shell 卡死的原因(未驗證)。

## 1. 按鍵怎麼變成 GUI 訊息

### 1.1 硬體/app 層:按鍵碼 → 處理器 vtable 槽位

- 硬體按鍵碼表 `0xC0BB7CD8`(`{code, name*, flags}` 12 B/筆):PLAY 8、DISP 0x35、TONE 0x2F、COLOR 0x2B、MODE 0x28、
  MENU 0x0A、QS 0x22、**AEL 0x24**、UP 0x14、DOWN 0x18、LEFT 0x10、RIGHT 0x0C、OK 0x1C、DIAL2 0x60、DIAL1 0x5F、
  S1 4、S2 6、LENS_DET 0x3D、POWER 3(按下 = code,放開 = code+1)。
- 對照 `CommonEventHandler_w71c1__v71` @ `0xC0451C08`(blk_c04.c:57872):事件型別 0x10 時,依按鍵碼呼叫
  `[handler+8]` vtable(MainMenuHandler 的 vptr = `0xC0CD18E4`,建構子 blk_c04.c:85463;Ghidra 的 vN = vptr+8+4N):

  | 按鍵 | 碼 | vptr 偏移 | 槽位 | MenuHandlerSubBase 實作 | 送給 GUI 的 GuiKeyType |
  |---|---|---|---|---|---|
  | S1 | 4/5 | +0x14 | v3 | `0xC046B568` | 0 |
  | S2 | 6/7 | +0x18 | v4 | `0xC046B5B8` | 1 |
  | PLAY | 8/9 | +0x24 | v7 | `0xC046B848` | 7 |
  | MENU | 0xA | +0x28 | v8 | MainMenuHandler 自己的 `0xC04742E0` | — |
  | UP/DOWN/LEFT/RIGHT | | +0x34/+0x38/+0x30/+0x2C | v11/v12/v10/v9 | | 0xC/0xD/0xE/0xF |
  | OK | 0x1C | +0x3C | v13 | `0xC046B9A8` | 0xB |
  | QS | 0x22 | +0x44 | v15 | `0xC046B768` | 4 |
  | **AEL** | 0x24/0x25 | **+0x48** | **v16** | **`0xC046B720`** | **3**(只在按下時) |
  | MODE/COLOR/TONE | | +0x4C/+0x50/+0x58 | v17/v18/v20 | 走 app 功能 `FUN_c04a29b8(0x11/0x12/0x13)`,**不進 GUI** | — |
  | **DISP** | 0x35/0x36 | +0x60 | **v22** | `0xC046B960` | 10(**只在放開時**) |

  (v71 是遠端/廠商按鍵事件的入口;硬體走同一組槽位是由這張對照表推得,未驗證。)
- `MenuHandlerSubBase__v16` @ `0xC046B720`(blk_c04.c:78571):`if (byte[this+0x15]==0 && 按下) FUN_c04509f8(**(this+0x10), 3)`。
  `FUN_c04509f8` @ `0xC04509F8` 對處理器自己的 GUI 物件呼叫 `v1(3,1)` 再 `v1(3,0)`。
  OK(v13)走的是完全相同的模式,只差 GuiKeyType。
- MainMenuHandler 的 13+ 份 vtable(`0xC0CD18E4` 起,步距 0x19C;typeinfo 名 MenuSys1..5Handler、MenuPlay1/2Handler…)
  **全部**沿用 `MenuHandlerSubBase__v16` / `__v22`,沒有覆寫(逐份讀過 `0xC0CD1960..0xC0CD2FE8`)。
  有覆寫 v16 的只有特定處理器(Qs、FocusArea、ToneButton、ColorModeBkt、Cinemagraph…,blk_c04.c grep `Handler__v16`)。

### 1.2 GUI 層:`UicContentsIfBase::v1` @ `0xC06D13A0`

```
if (this->v17(key,on) == 0) return 0;          // vptr+0x4C
list = this->v23();                            // vptr+0x64:這個類別的「characters-keys」清單
FUN_c055db10(key, on, msg, list) → GUI 佇列
```
- 物件 vptr 指向 vtable 起點(建構子 `0xC06D1318` 直接存 `0xC2E45D0C`),所以 +0x4C = Ghidra 的 v17、+0x64 = v23。
- **v17 不是過濾器**:191 個 GUI 類別中 183 個用 `UicContentsIfBase__v17` @ `0xC06D14B8` = 永遠回 1。
  GUI 21(`UicGuiMenuY5`,建構子 `0xC0584BE8`,vptr `0xC0D1E5FC`)與 GUI 47(建構子 `0xC057C620`,vptr `0xC0D1AC88`)都是這個。
- 按鍵碼對照 `FUN_c055dfd0` 表 `0xC0D0CCA0`(GuiKeyType → UIC 碼,37 筆):
  0→0x10、1→0x11、2→0x12、**3→0x13(AEL)**、4→0x14、5→0x1B、6→0x16、7→0x17、8→0x18、9→0x19、**10→0x1A(DISP)**、
  11→0x0D、12→0x26、13→0x28、14→0x25、15→0x27、19→0x31、20→0x30、21→0x30、22→0x31、23→0x40、24→0x41、16/17/18→0x50/0x52/0x51、25..34→0x60..0x69、35/36→0x70/0x71。
- 訊息類別 `FUN_c055db98` @ `0xC055DB98`:key 在 v23 清單內 → 按下 0x40 / 放開 0x80;不在 → 0x100 / 0x200。
  - Y5 類別(GUI 21)清單 `0xC0D1DE60` = {5,11,14,15,12,13}(MENU/OK/方向鍵)
  - GUI 47 清單 `0xC0D1A760` = {5}
  - 基底清單 `0xC0D0CDE8` = {12,13,14,15,11,5}
  - 沒有任何一份清單含 3(AEL)或 10(DISP)。所以改 GUI id 到 47 不會改變 AEL 的訊息類別。

### 1.3 UIC 層:keyEvent 的比對 `FUN_c05fbfb8`(Thumb,經 `0xC05FC128`/`0xC05FC130`)

keyEvent 類別的屬性表 `0xC2E02D14`(與 fpSup/lossless/menu/build_menu_candidate.py:53 一致),初始值 `FUN_c05fc148`(Thumb):

| # | 名稱 | 種類 | 列舉 | 預設 |
|---|---|---|---|---|
| 0 | type | flags | onkeypress=1 / onkeydown=2 / onkeyup=4 | 0 |
| 1 | keys | flags | **system-keys=1(0x100/0x200)/ characters-keys=2(0x40/0x80)** | 3 |
| 2 | keycode | bool(要不要比對按鍵碼) | | 1 |
| 3 | args | HEX4 = UIC 按鍵碼 | | 0 |
| 4 | do-propagate | bool | | 1 |

- 記錄格式:`keyEvent` 記錄在 local id 之後的那個字是**屬性存在遮罩**(bit i = 屬性 i),後面依序放有出現的值。
  所以「最後一個字是按鍵碼」= `args`。例:`a 2 d` = keys=2、args=0x0D;`8 13` = 只有 args=0x13。
- 比對:`(keys&1 && msg==0x100) || (keys&2 && msg==0x40)` → 按下動作;`0x200/0x80` → 放開動作;keycode≠0 時還要 `args==key`。
- `type` 預設 0 在比對程式裡看起來「什麼都不觸發」,但原廠 Y5_2 的 OK(`8 d`,沒有 type)實機能用,
  所以記錄解析一定還有我沒追到的預設/轉換(未驗證)。**這不影響本題**:我們的 AEL 與原廠的 AEL 是同一種寫法。

### 1.4 FT_LIST 的記錄 vs 原廠

離線重建 `ft6_page.build_grid()`:17 格每格的 AEL 記錄都是 `… 1 8ad4 <owner> <local> 8 13`,
與原廠 B3_5_5 記錄 320、ColorButtonMenu 記錄 309 的 `8 13` **逐欄同形**(只有 owner/local 不同)。
全原廠統計(所有頁的 keyEvent):AEL 記錄 `keys` 大多是預設或 1(system),沒有一筆只收 characters-keys;
OK 記錄在 Y5_2/MainY5 是預設(`8 d`),在 B3_5_5/ColorButtonMenu 是 `keys=2`。

差別在**擁有者**:原廠的 AEL 幾乎都放在專用物件(ColorButtonMenu / FocusAreaButtonMenu_2_1 的 `AELKeyEvent`、
`DisplayKeyEvent`)或頁層級的 `Menu` 物件上(B3_5_5);我們放在會取得焦點的格子上。
UIC 是否把 system-keys 送到焦點鏈以外的地方(或只送到某些物件),我沒有追到(UIC 派送給事件物件的入口沒找到)—— 未驗證。

## 2. app 頁表的「handler」是什麼

- `ScrNotFound` @ `0xC04B6520` → `FUN_c04b66a8`(blk_c04.c:137411)**依頁名首字選表**:
  `Ma*` → `0xC0CDEE1C`(13 筆,**MainB1..MainY5 都在**)、`B` → `0xC0CDF4AC`(60)、`R` → `0xC0CDEEC4`(35)、
  `Y` → `0xC0CDF254`(49)、其他首字 → `0xC0CDF074`(39,LV_*、ColorButtonMenu、QS_* …)。
  先前「主選單頁不在表裡」是只看了 B 表的誤會。`FT_*` 會查「其他」表,查不到 → 只記 log,沿用前一頁的畫面編號與 handler。
- handler 是**取值函式**,回傳 `{char* "submenu_NN", int}` 表,索引是 `[0xC376922C]`(語言):
  MainY5 `0xC04B8F98` → `0xC0CE9930 + idx*24`(`submenu_01=289, submenu_02=520` …);
  ColorButtonMenu `0xC04B8D68` → `0xC0CE78C8 + idx*32`。
  使用者 `FUN_c04b6308`(依名查值)→ `FUN_c04b6238` 呼叫 `obj->+0x7B8(值)`,上限 0x3B3(947)→ 彈出子選單的 x 位置。
- B3_5 的 `0xC04B5EF8` 同類:複製一張表到 `0xC3768F30` 後依量測字寬調整(`FUN_c04b5de8` 同型)。
  **與按鍵無關**,給 FT_LIST 加 app 表項目不會讓 AEL 通。
- 畫面編號(`FUN_c0513830`)才可能影響 app 選了哪個處理器;FT 頁沿用前一頁的,所以在 FT_LIST 上 app 處理器
  應該仍是 MainY5 的 MainMenuHandler(OK 可用即佐證),而它的 v16 會轉送 AEL —— 未驗證。

## 3. shell `gui key` 的真正參數

處理函式 `FUN_c03e88c8`(blk_c03.c 約 162460;字串 `invalid params`、`Send %d(%d) OK`、`Send %d(%d) %sOK` 在 `0xC0BB31DC..31FC`,
說明文字 `0xC0BB35D8`)。目標物件是 `FUN_c054dd38()` = `UicGuiFunction` 單例 `0xC3786188`,vtable `0xC0D0DAD4`,+0x64 = `UicGuiFunction__v23` @ `0xC055D780`
→ `FUN_c055db58(key, on, msg, cls)` → `FUN_c055db98(key, on, msg, cls==0)` → 直接進 GUI 佇列。**繞過 app 處理器與頁的 GUI 類別。**

- 2 個參數:`gui key <GuiKeyType> <cls>` → `FUN_c03e9258` 送「按下」再「放開」(一對)。
- 3 個參數:`gui key <GuiKeyType> <cls> <on>` → 只送一次(按下或放開)。
- `cls`:0 = characters-keys(0x40/0x80),非 0 = system-keys(0x100/0x200)。說明文字寫的
  `<eXC_GuiControlType> <eXC_GuiKeyType> <on_off>` 順序與程式不符,以程式為準。
- AEL = GuiKeyType **3**;DISP = **10**;OK = 11;MENU = 5。
- `gui key 0 19 1` = GuiKeyType 0(UIC 0x10 ShutterHalf)、system-key、**只按下不放開** → 半按卡住,與當時 shell 卡死吻合(未驗證)。

`eXC_GuiControlType`(`FUN_c054a3e0` @ `0xC054A3E0` 的參數,給 `FUN_c054dc80` 選 GUI 物件):
0 → `0xC3783194`、1 → GUI 1、2 → GUI 8、3 → GUI 2、4 → GUI 3、6 → `0xC37831A0`、其他 → `0xC3783190`。
`gui key` 不用它。

## 4. 最小、安全的做法

### 4.1 先上機分辨是哪一層吃掉(只送成對的按下+放開,只用 2 個參數)

在 FT_LIST 上,游標停在一格,每一步後 `mem get` 看 FT_Key:

| 步 | 指令 | 意義 | 預期 |
|---|---|---|---|
| 0 | `gui key 11 0` | OK,characters-key(與實體 OK 同類) | FT_Key = 格號 → 證明注入路徑可用 |
| 1 | `gui key 3 1` | AEL,system-key(實體 AEL 會用的類別) | |
| 2 | `gui key 3 0` | AEL,characters-key | |
| 3 | `gui key 10 1` | DISP,system-key | |

判讀:
- 1 觸發 → UIC 與記錄都沒問題,**是 app 層沒送**(實體 AEL 沒到 `MenuHandlerSubBase__v16`,或當下處理器不是它)。
- 1 不觸發、2 觸發 → UIC 對 system-keys 的路由不經過焦點格子 → 把 AEL 記錄搬到頁層級物件
  (照 B3_5_5 放在 `Menu`,或照 ColorButtonMenu 加一個 `AELKeyEvent` 物件),用 FT_Focus 判斷是哪一格。
- 1、2 都不觸發 → 記錄本身(或格子物件)不吃 AEL;拿原廠 B3_5_5 的 AEL 記錄整筆(含 owner 結構)做對照卡。

另一個便宜的對照:**在原廠 ColorButtonMenu / B3_1_9 上按實體 AEL**,確認這台機(AEL 已自訂成偽色)在原廠 AEL 頁上 AEL 會動。
不會動 → 問題是自訂指派,不是我們的頁。

唯讀探針(mem get,不寫):CustomScreenLoader 單例 `0xC37B722C`:`+4` 目前頁名指標、`+8` GUI id(u16)、`+0xC` 目前 GUI 物件。
在 FT_LIST 上應為 `FT_LIST` / 21 / `0xC37849A0`。

不要做:3 參數形式(會留下半按/按下狀態)、cls 以外的值、在錄影或回放中送。

### 4.2 修法候選(依測試結果選一個,都只改頁面資料,不加 hook)

- (UIC 路由問題)把 AEL keyEvent 從格子移到頁層級的 `Menu` 物件(原廠 B3_5_5 的位置),動作改成
  「`FT_Key = AEL_BASE + FT_Focus`」;或加一個不可見的 `AELKeyEvent` 物件(ColorButtonMenu 物件 0x10B2 的寫法)。
- (app 層問題)app 端加 hook 不划算;可改用不經 app 的鍵:Y5 類別清單裡的鍵(MENU/OK/方向鍵)都已經送得到,
  或改用 COLOR/TONE 以外的實體鍵 —— 需要再查。
- 給 FT_LIST 加 app 頁表項目**沒用**(表是版面寬度,且在 ROM)。

## 5. 未解

- UIC 把 key 訊息分給哪些事件物件(焦點鏈?所有物件?依 `keys`?)—— 沒找到 UIC 呼叫事件回呼 `0xC05FC131` 的入口。
- keyEvent `type` 預設 0 為什麼仍會觸發(屬性預設可能由記錄解析另外補)。
- B3_5_5 的 OK 記錄 `keys=2`(只收 0x40)但 GUI 47 會把 OK 送成 0x100 —— 那頁的 OK 實際怎麼生效沒查。
- 硬體按鍵是否和 v71 的遠端按鍵走同一組槽位(由按鍵碼對照推得,高度吻合但沒追到硬體入口)。
