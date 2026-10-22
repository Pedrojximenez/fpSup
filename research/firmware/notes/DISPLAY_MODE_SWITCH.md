# 顯示模式（Display Mode / DISP 循環）—— 值在哪、怎麼知道它換了、Y2_5_1 編的是哪一個

2026-10-06，Ver.5.02，**全部離線**（`out/seg0_c0000000.bin` + `out/decomp/full` + capstone），沒有碰相機。
目的：fpScreenFlip 要「每個自訂顯示模式各自一個翻轉值，**切進那個模式時**才套用」。

信心標記：**[高]** 反編譯 + 反組譯都對得上；**[中]** 推論鏈完整但有一環沒直接看到；**[低]** 猜測，要上機。

---

## 0. 先更正一個前提

`0xC0BBBC90` 那張遠端設定表的格式是 **{名字, 說明, 函式}** 三個字一筆，函式在名字**後面第二個字**：

```
C0BBBC84 → "SetFunction"     說明 "QSカスタム(機能割当て)"   函式 C0401C80
C0BBBC90 → "SetDisplayMode"  說明 "DispMode:カスタム設定番号" 函式 C0401D00   ← 真的
C0BBBC9C → "SetDisplayCustomSupport" "カスタム設定の有効状態"   函式 C0401D70
C0BBBCE4 → "SetDisplayTimeCode"                              函式 C0402078
```

所以 `FUN_c0401c80`（`c0061b08`/`c0061ac8`/`c0065830`、屬性 `+0x400`）是 **SetFunction（QS 功能分配，MenuItemFunction，8 格）**，
不是顯示模式。SetDisplayTimeCode 用的是 `c0062048/c0062088`（`+0x424`），不是 `c0061f00/f40`（那是 `+0x41C` = DistanceUnit）。[高]

---

## 1. 目前顯示模式的值

### 1a. 屬性物件 [高]

設定管理器 `FUN_c0057ae8()` = `0xC31AC530`（靜態）：

| 欄位 | 值 |
|---|---|
| `+0` | storage `0xC31AC59C`（vtable `0xC07397D8`） |
| `+8` | 屬性觀察者 context `0xC31AC540`（10 格，`+0x2C` 啟用 byte，開機 `DAT_c31ac56c = 1`） |
| `+0xC` | 「整批重載」觀察者 `0xC31AC524`（2 格） |

storage vtable 的存取 thunk 全是 `return r0 + 固定偏移`，建構子 `FUN_c007ba18` 裡逐一建好，id 與 RTTI 對得上：

| storage vtable 偏移 | storage 偏移 | 絕對位址 | id | 類別 |
|---|---|---|---|---|
| `+0x010` | `+0x0024` | `0xC31AC5C0` | 0x02 | MenuItemCinemaMode（STILL/CINE 開關） |
| `+0x3FC` | `+0x19E4` | `0xC31ADF80` | 0xD2 | MenuItemShootingStyle |
| `+0x400` | `+0x1A00` | | 0xD3 | MenuItemFunction（**不是**顯示模式） |
| **`+0x404`** | **`+0x1A1C`** | **`0xC31ADFB8`** | **0xD4** | **MenuItemDisplayMode** |
| `+0x408` | `+0x1A50` | `0xC31ADFEC` | — | MenuItemDisplayCustomLcdEnabled |
| `+0x40C` | `+0x1A38` | `0xC31ADFD4` | 0xD6 | MenuItemDisplayCustomSupport（每格是否啟用，5 格） |
| `+0x410`…`+0x440` | `+0x1A68`…`+0x1BC0` | | 0xD7…0xE4 | DisplayCustom FontSize / Info / LensInfo / DistanceUnit / DateTime / **TimeCode (0xDC, +0x424)** / GridLines / GridLineColor / FrameGuide / CenterMark / ElectronicLevel / BrightnessLevel / ZebraPattern / AudioMeter |

反組譯（建構子內）：

```
C007DEC4 mov r1,#0xd4 ; movw r0,#0x1a1c ; add r0,r0,r4 ; bl C0087FF8
         ... str 0xC0744820,[r4,#0x1a28]          ; vtable = MenuItemDisplayMode
```

DisplayMode 屬性**不快取**（vtable `+0x24` = `MenuItemDisplayMode::v7` 回 0），每次讀都走 `+0x18`
（`FUN_c00b81e8(0xD4, …)` → `FUN_c00b7168`）拿到設定區裡的那個字。

### 1b. 值實際存在哪 [高]

`FUN_c00b7168`（id 0xD4 的位址函式）：

```c
iVar1 = FUN_c008acf0();                         // 0xC31AE3B0 MenuSettingStorage
iVar5 = *(int *)(iVar1 + 0x11e00);
style = ShootingStyle(0xffff);                  // storage+0x3FC
if (iVar5 != 0 && style != 1)  return FUN_c008b258(iVar1) + 0x2770;   // CINE 組
else                           return FUN_c008b258(iVar1) + 0x2458;   // STILL 組
```

`FUN_c008b258` 依 `0xC31B954C` 那個 byte 回 `0xC31AE3BC` 或 `0xC31B3C84`（雙緩衝），還拿鎖。
**所以沒有固定絕對位址**，要用 getter 讀。

同一個 `+0x2458/+0x2770` 也是「`0xffff` = 目前自訂」的解析來源：

```c
// FUN_c00b4a28(base+0x22f8, isStill, idx)
if (idx == 0xffff) idx = isStill ? *(base+0x22f8+0x160) /*=+0x2458*/ : *(base+0x22f8+0x478) /*=+0x2770*/;
```

每個自訂的區塊（`FUN_c00b4a78`）：idx 0..3 在 `base + 0x245C / 0x2774 + idx*0x78`，idx 4 在 `base + 0x4BF8 / 0x4CE8`（後來加的）。
`isStill = (CinemaMode == 0) || (ShootingStyle == 1)`。→ **STILL 與 CINE 各有一份「目前模式」與一份 5 格自訂**（ShootingStyle==1 時共用 STILL 那份）。[高]

### 1c. 編碼 [高，第 5 格的標籤 中]

- 值 = **0 起算的格號**：0..3 = 自訂 1..4，**4 = 第 5 格 = LCD 關閉**。
  證據：`MenuItemDisplayCustomLcdEnabled::v8 @C00AF218` 就是 `return DisplayMode(0xffff) != 4;`，
  DISP 處理器切完後依它呼叫 `LcdOffStart` / `LcdOffStop`。
- 格數 = `FUN_c00b4490(0xD6)` = **5**。沒有「標準」模式；值 0 就是自訂 1。
- 寫入（`MenuItemDisplayMode::v9 @C00AEF18`）：要寫 v，從 `(v+i) mod 5` 起找第一個 CustomSupport 啟用的格存進去 → **永遠落在啟用的格**，寫 `cur+1` 就是 DISP 的循環。
- 原廠重置（`FUN_c04b4688`）：兩組都是格 0/1/2 啟用、3/4 停用，DisplayMode = 0。

### 1d. 卡片端最便宜的讀法 [高]

```c
uintptr_t s = ((uintptr_t(*)(void))0xC0057AE8)();          // ARM
uint32_t  m = ((uint32_t(*)(uintptr_t))0xC0061BA8)(s);       // ARM，回 0..4
```

`FUN_c0061ba8` = `storage->+0x404` → `FUN_c00913f8(prop,0xffff,…)` → `FUN_c006b4e8`，就是遠端 GetDisplayMode 用的那支（`C0401D00` else 分支）。
它會拿 `FUN_c008b258` 的鎖，別在中斷裡呼叫。

輔助 getter（全 ARM、引數都是 `s`）：`C0061A68` ShootingStyle、`C0058340` CinemaMode、`C0061C08` LcdEnabled、
`C0061CA8(s, idx)` 第 idx 格是否啟用。

### 1e. `SYS_DisplayMode` 不是這個 [高]

`SYS_DisplayMode` 是 **LCD / EVF 哪個在顯示**（0/1，`FUN_c06cb4d0` 只接受 0/1）：

- 寫入者：通知器 `XC_GuiMenuNotifierStill_w71c1::v401 @C059A110`（vtable 偏移 `+0x64C`）；被呼叫於
  `BootEventHandler_w71c1::v73 @C044FC18`（開機，值 = `FUN_c0517e78()`）和
  `CommonEventHandler_w71c1::v44 @C04513A0`（log 字串 `EvfDispChanged`）。旁邊 v400 是 `SYS_EvfStatus`。
- 讀取者：`UicGuiMenuEvfBrightness/LcdBrightness/LcdColorTemp::v23`，只用來挑 LCD 或 EVF 的字串。

`CM_DisplayMode` 是播放（PB）的顯示模式（`FUN_c05897c8`，與 CM_Rotate/CM_Delete 一起訂閱）。
**live view 的自訂顯示模式沒有任何 UI 變數**（通知器 v292…v305 只發 `ST_DSPSEL_*` 與各項目的值）。

---

## 2. 怎麼知道它換了

### 2a. 切換路徑（呼叫 `FUN_c0061b68` = DisplayMode setter 的全部）[高]

| 來源 | 位置 | 說明 |
|---|---|---|
| **DISP 鍵** | `StandbyEventHandler_w71c1::v22 @C0482D10` | `m = C0061BA8(s); C04A8A18(1); C0061B68(s, m+1, 1); C04A87F0(0); … if (!C0061C08(s)) LcdOffStart else LcdOffStop` |
| 遠端 | `FUN_c0401d00`（SetDisplayMode） | `C0061B68(s, v, 1)` |
| 原廠重置 | `FUN_c04b4688` | `C0061B68(s, 0)` |
| 停用目前那格 | `MenuItemDisplayCustomSupport::v10 @C00AF2A8` | 直接 `C0068098(prop, 同值, 0xffff, 0)` → v9 跳到下一個啟用格 |

v22 是 DISP：同一格在 PlayEventHandler 系列也是切播放顯示（比對推得）[中高]。

DISP 呼叫點反組譯：

```
C0482DA4  EBEF7B7F  bl  C0061BA8          ; 讀目前
C0482DB4            bl  C04A8A18          ; (r0=1)
C0482DB8            add r1, r7, #1
C0482DC0            mov r2, #1
C0482DC4  EBEF7B67  bl  C0061B68          ; ← 寫 m+1
C0482DCC            bl  C04A87F0          ; (r0=0)
```

### 2b. 建議：settings 屬性觀察者（不改韌體字）[高，執行緒 中]

setter 尾端 `FUN_c0077eb0`：

```
C0077FB0 bl  C006B4E8          ; 讀新值
C0077FBC cmp sl, r6            ; 跟舊值比
C0077FC0 beq C0077FF8          ; 沒變 → 不通知
...
C0077FF0 EB00646A bl C00911A0  ; (prop, idx, 1, 1)
```

`FUN_c00911a0` → 依賴圖 → 每個屬性 `vtable+0x10` → `FUN_c0090e38(ctx=prop+8=0xC31AC540, &ev)`
→ 若 `ctx+0x2C` → `FUN_c0090e68` 逐一呼叫 10 格：`obj->vptr[+0xC](obj, ev)`，**回 0 就被移出**。
`ev = {u32 屬性 id, u32 idx}`，DISP 時是 `{0xD4, 0xFFFF}`。原廠 `MenuDisplayModeHandler`（`+0x144` → `@C0460B70`）就是看 `ev[0]==0xD4`。

註冊／註銷（ARM）：

```c
((void(*)(uintptr_t,void*))0xC0057BF8)(s, &obs);   // → FUN_c0063850(ctx, obj)：關中斷、同物件不重複、找空格
((void(*)(uintptr_t,void*))0xC0057C18)(s, &obs);   // 註銷
```

物件只要 `{vptr, …}`，`vptr+0xC` 放回呼（`blx r2`，Thumb 位元有效）。原廠樣板：`MenuItemIdObserver`
（建構 `C0452EB8`，vtable `0xC0CBEE94`，回呼 `C0452F30` 回 1）。

會觸發 0xD4 事件的：DISP、遠端、原廠重置、停用目前那格（值改變時）；
另外 **CustomSupport (0xD6) 的依賴清單就是 `{DisplayMode}`**（`MenuItemDisplayCustomSupport::v1 @C00AF348`），
所以在 Y2_5 勾選／取消任何格都可能帶出一次 `{0xD4,…}` 但值沒變 → 回呼要自己比上一次的值。

建議回呼：`ev[0] ∈ {0xD4, 0xD6, 0x02, 0xD2}` 時重讀 `C0061BA8` 與組別（STILL/CINE），跟上次不同才做事。

⚠ **執行緒**：回呼跑在**呼叫 setter 的那個任務**（DISP = 事件處理器任務，遠端 = PTP 任務），**不是 UI app 執行緒**。
不要在回呼裡查 UI 變數表；要動 UI 就用 `C0593F30(0, name, value)` 丟進 GUI 佇列（任何任務都可呼叫），
或寫私有變數 `MV_fpFlipMode`，讓它在 UI 執行緒的 C0560FB0 回呼裡做事。直接寫圖層暫存器 + `C02E4420` 能否在非 UI 任務做：[低]，要上機。

⚠ **格數**：10 格；滿了 `FUN_c0063850` 會 `FUN_c0011100(...XC_Observer...,0x43)`（assert）然後寫 `ctx[-1]`。
註冊前先數 `0xC31AC540[0..9]` 有沒有空格。FP3K 實機看過「選單開著時 2 格」，每個開著的選單頁
（`MenuHandlerSubBase::v72` → `C0057BF8(handler+0x18)`）佔 1 格、離開時（v73 → `C0057C18`）釋放。

### 2c. 備案：呼叫點 hook [高]

- 只抓 DISP：`0xC0482DC4`，原字 `0xEBEF7B67`（`bl C0061B68`；r0=s、r1=m+1、r2=1）。
  hook 呼叫原函式後再 `C0061BA8` 讀結果（v9 會跳過停用格，r1 不一定是最後的值）。遠端／停用格／重置都抓不到。
- 抓所有改值：`0xC0077FF0` `bl C00911A0`（`0xEB00646A`）——這是 **所有 `MenuItem<unsigned int>` 共用的 setter**，hook 要過濾 `[r0]==0xD4`，太寬，不建議。

### 2d. 開機與 STILL/CINE 切換**不走** setter [高]

- 開機：值是從設定區直接載入的，沒有 setter、沒有 0xD4 事件。卡片初始化（AutoRun 後，約開機 8 s）要**自己讀一次並套用**。
- STILL↔CINE（CinemaMode id 2）或 ShootingStyle 改變：`+0x2458` ↔ `+0x2770` 換一份，**有效顯示模式直接變了，但沒有 0xD4 事件**
  （CinemaMode 的依賴清單 `C0093190`、ShootingStyle 的 `C00ACFE8` 都不含 0xD4）。
  不過 CinemaMode／ShootingStyle 自己改值時會有 `{0x02,…}`／`{0xD2,…}` 事件經同一個 ctx（兩者 vtable+0x10 都是 `C0090E38`）→ 一起聽就好。[中高]
- CinemaMode 的 v11（`C0093178`）還會跑 `FUN_c0058128`：整批失效 + 叫 `0xC31AC524` 那 2 格「重載觀察者」（無事件內容）。不要佔那 2 格。

---

## 3. Y2_5 → 自訂 N → Y2_5_1：怎麼知道在編哪一格

### 3a. 開頁的路徑 [高]

`MenuDisplayModeHandler::v86 @C0460A88`（Y2_5 列表頁的處理器，vtable `0xC0CC5E6C` +0x160）：
`submenu_01..05` → `Y2_5(…, 0..4)`（`@C049E428`）→ 把 N 放進選單參數單例（`FUN_c054a2e0` → `0xC3786A04`）再換頁。

進頁時 `MenuHandlerSubBase::v72 @C046B3D8` 依序：清旗標 → **`vptr+0x184`** → 註冊屬性觀察者。
`MenuDisplayCustomHandler`（**靜態實例 `0xC376287C`**，vptr 在 +8 = `0xC0CC6008`，建構 `C0460BF0` 把 +0x28 設 0xFFFF）
的 `+0x184` = `MenuDisplayCustomHandler::v95 @C0460C60`：

```c
*(handler+0x28) = (*(param_obj+8)->+0x20)();      // ← 編輯中的格號 N
notifier->+0x49C(C0061D50(s, N));  // FontSize
...
notifier->+0x4A8(C0062088(s, N));  // TimeCode
... 共 12 項，全部用 N 讀、丟給通知器 → ST_/MV_DSPMODFIX_* UI 變數
```

**卡片端拿 N**：

- `*(volatile uint32_t *)0xC37628A4`（= `0xC376287C + 0x28`）。第一次進頁前是 0xFFFF；離開頁後保留最後的值。[高；BSS 位址靜態，但要上機確認不是被重建]
- 或頁面活著時（`*(uint32_t*)0xC37B7468 != 0`，`UicGuiMenuDisplayCustom` 實例）呼叫 `FUN_c0571d10`（ARM，回 N）。
  `UicGuiMenuDisplayCustom::v18 @C056FE58` 用同一個值挑標題。

組別要另外算：`still = (C0058340(s)==0) || (C0061A68(s)==1)`（頁標題也是這樣加 `<font G mode still/cine>`）。
建議私有表用 `[2][5]` 或至少 `[2][4]`。

### 3b. FIX / AJ、ST_ / MV_ [中]

- **ST_ = STILL 組，MV_ = CINE 組**：同一槽 v296，Still 通知器（`@C05988F8`）發 `ST_DSPMODFIX_TimeCode`，
  Cine/StillLike 通知器（`@C0593A58`）發 `MV_DSPMODFIX_TimeCode`。
- **FIX / AJ**：頁面的回呼都呼叫接收器 `+0x38C` = `MenuAction_w71c1::v225 @C04ACA48` = `C0062048(s, 值, N, 旗標)`，
  FIX 系列旗標 0、AJ 系列旗標 1（`FUN_c0571460` vs `FUN_c0571988`）。旗標就是 setter 的「強制通知」。
  和原廠 `MV_MFDisplayFix/Aj` 同一套：**Fix = 收合列上確定的值，Aj = popup 開著、游標移動時的調整值（即時預覽）**。
  兩者都寫進格 N 的設定。

### 3c. 進頁事件：能不能訂閱？ [高]

**不能用 C0560FB0 去訂原廠的 DSPMOD 變數。** UI 變數描述元的訂閱只有**一格**（`desc+0x18`）：
`FUN_c05dcb18` 在 `*(desc+0x18) != 0` 時回錯誤 2（C0560FB0 只記 log）。
`UicGuiMenuDisplayCustom::v25 @C0570050` 開頁時訂閱全部 `ST/MV_DSPMODFIX_*`、`ST/MV_DSPMODAJ_*`（v26 離開時取消）；
`UicGuiMenuDisplayMode::v25 @C056FAE8` 訂 `ST_DSPSEL_Custom1..5`。
**我們先佔了 → 原廠那頁的回呼掛不上 → 改了值也不會存進設定。**

進頁時也沒有任何屬性事件（v95 只讀）。所以「進頁就把格 N 的值載進 `MV_fpScreenFlip`」只剩 hook：

**建議：換一個 vtable 字（資料，不是程式碼）**

```
0xC0CC618C  = 0xC0460C60   (MenuDisplayCustomHandler vptr 0xC0CC6008 + 0x184 → v95)
```

改成我們的 ARM thunk：`orig(handler)`（先讓它把 N 寫到 +0x28）→ `N = *(handler+0x28)` →
`C0593F30(0, "MV_fpScreenFlip", table[set][N])`。跑在選單事件任務，post 是佇列，安全。
要照 SUP 規則記 journal。只有 `MenuHandlerSubBase::v72`（進頁）會呼叫這格；別的 handler 的 v95 也在 +0x184，但各自的 vtable，不受影響。[高]

備案：`0xC0CC5FCC`（列表頁 v86，原字 `0xC0460A88`）可以拿到 `submenu_0N` 字串，但那時還沒換頁。

使用者改我們那列時（`MV_fpScreenFlip` 的 UI 執行緒回呼）：讀 `0xC37628A4` 拿 N、算組別、存表；
若 (組別, N) 正好是目前有效的模式，就立刻套用。

### 3d. 哪些格不能編 [中]

`submenu_01..05` 五格都能進 Y2_5_1（`Y2_5(…, 4)` 存在，格 4 也有自己的設定區塊）。
`ST_DSPSEL_CustomN` 只是「這格是否在 DISP 循環裡」（`C0061CA8`），不擋編輯。
UI 資源字串只有 `MV_DSPSEL_Custom1..4`（沒有 `MV_DSPSEL_Custom5`），CINE 組可能只顯示 4 格 [低]。
格 4 = LCD 關閉，它的子設定大概只影響 EVF/HDMI 的 OSD [低]。翻轉建議對格 4 不動作（LCD 本來就關）。

---

## 4. 陷阱

1. **一個變數只能一個訂閱者**（3c）。只訂自己的私有變數。
2. **觀察者回呼不在 UI 執行緒**（2b）。
3. **觀察者只有 10 格，滿了就 assert**；註冊前檢查。
4. **開機、STILL/CINE、ShootingStyle 都不會發 0xD4**；初始化時套用一次，並聽 0x02 / 0xD2。
5. **0xD4 事件可能值沒變**（CustomSupport 的依賴）；自己比較。
6. **DISP 只落在啟用的格**；停用目前那格會把模式推到下一格（會發事件）。
7. **格 4 = LCD 關**：DISP 處理器在那之後 `LcdOffStart`。
8. **EVF**：`SYS_DisplayMode` / `SYS_EvfStatus` 表示 EVF 在顯示時，LCD 翻轉沒有意義；`EvfDispChanged` 會改它。
9. **HDMI 插拔會把圖層暫存器清 0**（fpScreenFlip README），沒有事件；下一次切模式才會重寫。
10. 設定區是雙緩衝、有鎖（`FUN_c008b258`），**不要直接讀 `+0x2458` 這種位址**，用 `C0061BA8`。
11. 原廠重置把每組設成 0、格 0..2 啟用；我們的表也要跟著重置或至少不能越界。

---

## 5. 要上機確認的

- DISP 按一次是否只看到一次 `{0xD4,0xFFFF}`、回呼跑在哪個任務；在那裡寫圖層暫存器 + `C02E4420` 安不安全。
- `0xC31AC540` 開機後實際用了幾格。
- `0xC37628A4` 在進頁後是否等於 N（也確認實例沒被重建到別處）。
- vtable 字 `0xC0CC618C` 換掉後，進頁有沒有正常載入 `MV_fpScreenFlip`。
- 第 5 格的選單標籤是不是 LCD 關閉；CINE 組有沒有第 5 格。
- STILL↔CINE 切換時是否真的有 `{0x02,…}` 事件（還是只有整批重載那條路）。
- 開機後的第一次套用：卡片初始化時 LCD/EVF 狀態是否已穩定。
