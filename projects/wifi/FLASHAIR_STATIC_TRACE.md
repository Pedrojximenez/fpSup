# fp Ver.5.02 韌體中的 FlashAir：靜態追蹤結果

追蹤對象：`out/MAIN_c0000000.bin`（base `0xc0000000`，長度 `0x2f30cca`）
反編譯來源：`out/decomp/full/blk_*.c`（47,156 函式，47,154 成功 — 視為全覆蓋）
日期：2026-09-20

---

## 1. 全部證據（整個韌體只有 4 處 "FlashAir"）

| 位址 | 內容 | 性質 |
|---|---|---|
| `0xc0743e28` | `MenuItemFlashAirSupport` | RTTI type name（vtable @ `0xc0743dac`，14 slots） |
| `0xc0bbe788` | `SetFlashAirSupport` | 服務 shell 指令名 |
| `0xc2da1700` | `CM_FlashAir` | GUI/Lua 字串池中的符號名（池範圍 `0xc2d9e4d8`–`0xc2da43b8`，1005 筆，字典序） |
| `0xc2df1a38` | `CM_FlashAir` | System 選單分組符號表中的一筆 |

`out/lzss_full.bin`（解壓後全鏡像）掃描結果相同，沒有第五處。

## 2. 類別與實體

```
MenuItemFlashAirSupport : MenuItemCommon<bool>     // out/rtti_classes.txt:c0743e18
  vtable @ c0743dac (14 slots)
  slot[0]  c00ad310   deleting dtor -> operator delete(this, 0x18)   // sizeof == 24
  slot[3]  c00ad2c8   空函式（return）
  slot[13] c0743df0   反編譯失敗（bad instruction），其餘 11 slot 與 MenuItemCommon<bool> 共用
```

實體是 `MenuItemFactory_w71c1` 的成員，位於 `this + 0x18cc`，由 vtable slot 243
（`vt + 0x3cc`）取出：

```
MenuItemFactory_w71c1::v243 @ c0085670:
    mov ip, r0 ; movw r1, #0x18cc ; add r1, r1, ip ; mov r0, r1 ; bx lr
```

鄰居（accessor stub 每隔 0x18 一支，成員 offset 連續）：

| slot | vt off | 成員 off | 對應設定 |
|---|---|---|---|
| 242 | `0x3c8` | `0x18b0` | UsbConnectionMode |
| **243** | **`0x3cc`** | **`0x18cc`** | **FlashAirSupport** |
| 244 | `0x3d0` | `0x18e8` | TimeFormat |
| 245 | `0x3d4` | `0x1904` | Language |

（成員 offset 由 `MenuItemFactory_w71c1::v0` 解構子 `c007e5a8` 交叉確認。
基底 `MenuItemFactory::v243` @ `c00b41a0` 直接 `return 0`，只有 `_w71c1` 變體才有實體。）

## 3. 唯一的存取路徑：服務 shell

`Set*` 指令表（entry = {name, 日文標籤, handler}，stride 12）第 `0xc0bbba5c` 筆：

```
name    = 0xc0bbe788  "SetFlashAirSupport"
label   = 0xc0bbe79c  "Flash Air"
handler = 0xc0400838
```

```c
/* FUN_c0400838 @ c0400838 */
if (argc == 1) {                       // set
    v = strtol(argv[0], 0, 10);
    FUN_c005ff78(FUN_c0057ae8(), v != 0, 1);   // -> factory.v243()->set(bool, 0xffff, 1)
    printf("OK\n");                            // DAT_c0bbae4c
} else {                               // get
    printf("%d\n", FUN_c005ffb0(FUN_c0057ae8()));  // DAT_c0bbae50
}
```

```c
/* setter  FUN_c005ff78 */  item = (*(vt + 0x3cc))();  FUN_c0067ad8(item, val, 0xffff, flag);
/* getter  FUN_c005ffb0 */  item = (*(vt + 0x3cc))();  ... FUN_c00913f8(item,0xffff,ctx,0x80000001); FUN_c006b7e8(item, x);
```

`FUN_c0057ae8` @ `c0057ae8` 是設定門面單例，回傳 `0xc31ac530`。

## 4. 誰讀這個旗標 —— 答案是：沒有人

- 全韌體對 `vt + 0x3cc` 的虛擬呼叫只有 **2 處**，就是上面的 getter / setter
  （`blk_c00.c:70856`、`blk_c00.c:70870`）。
  其餘 `+ 0x3cc)` 命中都是別的類別或結構欄位，非 MenuItemFactory。
- `CM_FlashAir` 字串唯一的 code 參照在 `XC_GuiMenuNotifierStill_w71c1::v338` @ `c05990c0`
  （`movw/movt` @ `c05990b0`），路徑是
  `FUN_c06c5560(...) -> FUN_c0593f30(this, "CM_FlashAir", val) -> GUI_QUEUE_FULL(...)`，
  純粹是 GUI 狀態記錄／訊息佇列，不觸碰 SD。
- `CM_FlashAir` 在 690 條 Lua 條件式（`CM_x:v() == n` 形式）中出現 **0 次**，
  沒有任何選單顯示/致能條件依賴它。

## 5. 沒有 UI 字串

韌體內完全沒有 FlashAir 的在地化選單文字。對照鄰居：
`Cable Release` 10 筆、`USB Mode` 3 筆、`Auto Power Off` 1 筆，都有；FlashAir 0 筆。
唯一的人類可讀字串是服務 shell 表裡的日文欄位 `"Flash Air"`。

`0xc2df1a38` 那張分組表的排列是 System 選單順序：

```
CM_AutoPowerOff, CM_EchoMode, ST_MonitoringOutput, CM_USBMode,
CM_FlashAir, ST_CableRelease, CM_DateYear, CM_DateMonth, ...
```

也就是說**位置是留好的（USB Mode 與 Cable Release 之間），但項目沒有被建出來、沒有文字、沒有人讀。**

## 6. 沒有 iSDIO

- 字串掃描：`iSDIO` / `CMD48` / `CMD49` / `ExtensionRegister` / `SDIO` / `ACMD` / `SD_CMD` 全數 0 命中。
- SD 測試 shell 表 `0xc0bc2660`（17 指令）只有檔案／區塊層：
  `slot, test..test6, test_rw, size, fnum, sdmode, format, checkinit, chkop, readOnly, mnt, umnt`，
  沒有任何送任意 CMD 的入口。
- `sdmode` @ `c040ad00` 會回報匯流排模式：`Invalid` / `Normal SDCARD` / `UHS-I` / `UHS-II`
  —— fp 的 SD 控制器支援到 UHS-II。
- 媒體層類別只有 `XC_MediaDriverSdcard` / `XC_MediaDriverHost`（檔案層），
  底層 host controller 驅動無 RTTI，尚未定位。

> **2026-09-20 補正**：§6 的「沒有 iSDIO」只對上層成立。後續追 SD host controller
> 時發現，底層 SDHCI 驅動的 data-command 分派器 `FUN_c0668b70 @ c0668b70`
> **明確列舉並處理 CMD48(0x30) / CMD49(0x31) / CMD56(0x38)**，只是相機上層從未發出。
> 詳見 `SDHCI_MMIO_MAP.md` §5。

## 7. 附帶發現：韌體內建 Lua 5.3

`out/MAIN.strings.txt` 有 `Lua 5.3`、`LUA_PATH_5_3`、`luaopen_%s`、`lua_debug>`、
`LuaFunc_Judgment_`、`LuaFunc_Calculation_`。GUI 用 Lua 運算式決定選單顯示／致能，
相機設定以 `CM_* / ST_* / SYS_* / PB_* / LV_*` 物件的 `:v()` 方法暴露給腳本，例如：

```
CM_FileSelectType:v() == 7 and PB_DisplayType:v() == 0
(function() if SYS_RecordingMedia:v() == 0 or SYS_MediaStatus:v() == 1 ... end end)()
```

共 690 條。這條線跟 FlashAir 無關，但值得另開追蹤。

---

## 結論

fp Ver.5.02 韌體**確實帶有 FlashAir 的資料結構**，但那是 SIGMA 共用程式庫留下的殘骸：
一個 bool 設定項、一個服務 shell 指令、選單裡留好的位置。
**它不驅動任何 SD 行為，沒有 iSDIO，也不可能單靠打開這個旗標讓 FlashAir 動起來。**

對 wifi 專案的意義：
- 相機端不會幫我們做任何事，FlashAir 的 Wi-Fi/Lua 必須完全由卡自己跑（卡上 CONFIG + Lua）。
- 原本規劃的 iSDIO CMD48/49 共享記憶體路徑，相機韌體沒有現成 ABI，
  要走就得自己找到 SD host controller 暫存器，透過 fpShell 的記憶體讀寫注入命令。
  這是獨立且更大的工程，下一步應該是定位 SD host controller 的 MMIO base 與命令暫存器。
