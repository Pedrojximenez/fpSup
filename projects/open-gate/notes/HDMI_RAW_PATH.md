# HDMI RAW —— 它是真的,而且有自己的格式表

2026-09-17。起因:社群問「能不能做 2.39:1 / 6K」,以及使用者提議
「先做一個純 HDMI 版的 OG6K」。

信心:**[C]** 反編/實機交叉驗證 · **[I]** 推論 · **[?]** 未解。

> **2026-10-23 更新：** 共用 res-custom 介面可行，但「加一筆表就能 OG6K 外錄」
> 並不成立。28 模式原生離線測試找到 RAM entry 的顯示身分分類、HDMI format11、
> RAW display／gain 路由等必要適配；精確結果與分階段設計見
> [HDMI_RAW.md §7](../../../research/interfaces/notes/HDMI_RAW.md#7-能否與-res-custom-共用介面2026-10-23)。
> 下文保留2026-09-17的調查；任意尺寸的 packing／metadata／接收器支援仍未驗證。

---

## 0. 一句話

**HDMI RAW 有專屬的28筆格式表 `0xC0BE5450`，entry外形與感測器mode空間可和
CinemaDNG 的虛擬化機制對照。** 但新增虛擬 entry 還須處理下游身分、格式、
RAW buffer 與 HDMI／接收器契約；同樣16-byte外形不能證明任意 OG 尺寸可外錄。

---

## 1. 分派器 `FUN_c043b988` [C]

它和我們的格式選擇器 `FUN_c043b828` 同構,就在隔壁。依旗標決定查哪張表:

```c
if (cfg[0x25] == 0) {
    if (cfg[0x26] == 0)                            // 不是 HDMI raw
        lookup(cfg[0x45] ? 0xC0BE5050 : 0xC0BE4D50);
    else if (cfg[0x47] == 0)
        lookup(0xC0BE5450);                        // HdmiRaw
    else
        lookup(0xC0BE5150);                        // HdmiRec
} else
    lookup(0xC0BE5610);
```

旗標名稱由 `HdmiLimit @ 0xC0437740` 的狀態傾印確認 —— 它從同一個結構印出
`recSize`、`stillSize`、`eRawBitType`,以及 `HdmiRaw` / `HdmiRec` / `HdmiLimit`
三選一的標籤。字串全部來自 `src/library/LiveViewState/src/LiveViewModeMgr.cpp`。

`LiveViewState` 模組佔 **0xC04367C0 .. 0xC043FEB8**,裡面有
`XC_LiveViewConfiguratorW71c1__v2 @ 0xC043CAF0`。
**我們的 hook 本來就在這個模組裡**:格式表 hook `0xC043CCF8`、canvas hook
`0xC043A19C`、格式選擇器 `FUN_c043b828`。HDMI RAW 不是隔壁的子系統。

## 2. 四張表並排 [C]

表型:`{const, profile, mode, key_ptr}`,每筆 16 bytes。

**每張表的長度不同**,由各自的搜尋器寫死(`iVar2 = param_2 + span`),而且
**五張表完全相接、沒有空隙** —— 每張的 `起點 + span` 正好是下一張的起點:

| 表 | const | span | 筆數 | 搜尋器 | 內容 |
|---|---|---|---|---|---|
| `0xC0BE4D50` 一般 | 3 | 0x300 | 48 | `FUN_c043cdb8` | UHD/FHD + EIS |
| `0xC0BE5050` ? | 3 | 0x100 | 16 | `FUN_c043ce78` | `cfg[0x45]` 分支 |
| `0xC0BE5150` HdmiRec | 3 | 0x300 | 48 | `FUN_c043cdb8` | 幾乎同「一般」 |
| **`0xC0BE5450` HdmiRaw** | **3** | **0x1C0** | **28** | **`FUN_c043ce18`** | UHD/FHD + **DCI4K24** + CROP,無 EIS |
| `0xC0BE5610` `cfg[0x25]` | 4 | 0x200 | 32 | `FUN_c043cd58` | |
| `0xC0BE5810` CDNG 8-bit | 5 | | | | |
| `0xC0BE59B0` CDNG 10-bit | 5 | | | | |
| `0xC0BE5B50` CDNG 12-bit | 5 | | | UHD/FHD + CROP |

四個搜尋器是**各自獨立但形狀相同**的線性掃描,只差那個 span 常數。

> **更正(2026-09-17 第二輪):** 先前寫「26/26 全滿」是錯的 —— 我只印了 26 列。
> HdmiRaw 實際是 **28 筆全滿**,最後兩筆是 `FHD120CROP` / `FHD100CROP`。
> 結論不變(仍然沒有空位),但數字要對。

HdmiRaw 的 profile 落在 **`0x16D`–`0x184`** 與 **`0x1BB`–`0x1C0`**,
和 CinemaDNG 的 `0xAB`–`0xBD` 是**不同的區塊**。

`mode` 欄位是同一個感測器模式編號空間(`0x97`=151、`0x07`=7、`0x7B`=123…)。

**HdmiRaw 有 `DCI4K24`,內建 CinemaDNG 沒有。**

## 3. 廠商偵測和 raw 模式是兩回事 [C]

`TSBMDAJA @ 0xC00EC948` 比對 HDMI 接收端的三字元廠商識別碼,表在
`0xC07C04E0` = `"ATS"`(Atomos)/`"BMD"`(Blackmagic)/`"AJA"`:

```c
FUN_c00ef2b8(&id);
for (i = 0; i < 3; i++)
    if (table[i*3..+2] == id[0..2] && (1<<i & 允許遮罩))
        DAT_c31d5e72 = 1;
```

`FUN_c00eca10 @ 0xC00ECA10` 是那個旗標的 getter(Thumb,四道指令)。

**它和 `cfg[0x26]`(HDMI raw 模式)是不同的旗標。** 這解釋了 §4 的實機結果。

## 4. 實機實驗(2026-09-17)[C]

擷取卡:AVerMedia ExtremeCap UVC,**最高 1920×1080**,無 4K 格式。

### 4a. 偽造廠商偵測 —— 生效,但不夠

把 getter 改成永遠回傳真,**一個字**:

```
0xC00ECA10   0x8D04F84D -> 0x47702001     movs r0,#1 ; bx lr  (Thumb)
```

改 getter 而不是改變數,是因為 `TSBMDAJA()` 在熱插拔時會重算變數。
工具:`../build/hdmi_recorder_force.py`(有 `--check` / `--restore`)。

相機**自己就改了設定**:

| | 補丁前 | 補丁後 |
|---|---|---|
| `SetHdmiOutputSize` | 1(1920×1080) | **2(3840×2160)** |
| `SetHdmiOutputFramerate` | 5 | 3 |

`SetHdmiIsManual = 0`,所以是相機自動選的。活的輸出狀態
(context 指標在 `0xC30751D4 + 0x5C`):

```
ctx+0x39C 模式碼     = 0
ctx+0x3A0 輸出寬     = 3840
ctx+0x3A4 輸出高     = 2160
ctx+0x3AC HDMI 連接  = 1
```

**但擷取卡實際收到的仍是 1920×1080** —— 相機有依 EDID 協商降下來,
`ctx+0x3A0/+0x3A4` 是**設定值不是實際輸出**。

### 4b. 加上 CinemaDNG + 乾淨輸出 —— 仍然不是 raw

```
SetMovRecFormat    0 -> 1     (CinemaDNG)
SetHdmiOutputInfo  1 -> 0     (關掉資訊疊加)
```

HUD 確實消失了,但抓下來仍是**一般監看視訊**:有效畫面 1622×917
(比例 1.769 ≈ 16:9),整體縮到約 85% 置中,四周黑邊。

**原因現在清楚了**:我們騙的是廠商偵測,`cfg[0x26]` 沒動,所以 §1 的分派器
查的還是一般表 `0xC0BE4D50`。

### 4c. 順手做出來的量測工具

`scratchpad/grab.swift` → `grab`,用 AVFoundation 抓 UVC 擷取卡一張畫面,
同時列出它支援與當前鎖定的格式:

```sh
./grab AVerMedia /tmp/cap.png
```

**以後不用買錄影機就能看相機的 HDMI 輸出。** OG6K 出不出得去、出去是什麼
畫幅,直接抓來看。

## 5. OG6K over HDMI RAW 要做什麼

OG6K 的錄影側 target 已經寫進 `../build/og3k_plan.py` 並通過靜態檢查
(698 筆寫入;OG3K 749 與 OG2K 782 逐字未變)。

```
donor 感測器模式 = M3 MONIT1_30(6064x4042 RAW12,MONIT class)
rec 6064x4042   act 6048x4032   (= OG2K 2016x1344 的三倍)
四個格率,零誤差:23.976 / 24.000 / 25.000 / 29.97003
格率上限是感測器給的:445 x 4042 / 72 MHz = 24.982 ms -> 40.03 fps,
    所以這個畫幅沒有 48/50/60
```

要走 HDMI RAW 還缺:

1. **在 `0xC0BE5450` 註冊一筆。** 表滿了,所以要私有表 + 改導查表,
   就是 OG3K/OG2K 現在的做法
2. **`const` 欄是 3 不是 5**
3. **捐贈者要重挑** —— HdmiRaw 的 profile 在 `0x16D`–`0x184`/`0x1BB`–`0x1C0`,
   p14 那份稽核是對 CinemaDNG 空間做的,不適用。**已完成,見 §5c。**
4. 誰在什麼條件下設 `cfg[0x26]` [?] —— 見 §5d。

§5b 解出 RWZM 編碼,§5c 給出完整欄位清單。剩下的未解項目集中在 §5d。

## 5b. RWZM 的編碼 —— 解出來了 [C]

profile 的四個 RWZM 欄位 `+0x60 / +0x64 / +0xD0 / +0xD4`(後兩個是前兩個的複本):

```
+0x60 = 預覽平面的縮減比      +0x64 = RAW 平面的縮減比
單位 1024。1023(0x3FF)= unity,原廠慣用;我們的 plan 寫 0x400,同義。
```

原廠只用四種值:`1023 / 1500 / 1536 / 1600 / 2048` = `1.0 / 1.465 / 1.5 / 1.5625 / 2.0`。

證據(`+0x64` 每一列都對上 rec 的縮減比):

| profile | `+0x64`/1024 | 感測器/rec | `+0x60`/1024 | 感測器/預覽 |
|---|---|---|---|---|
| **p83 OG3K** | **0.999** | **1.0000** ✓ | **1.500** | **1.4980** ✓ |
| p173 FHD CDNG | 1.5625 | 1.5661 ✓ | 1.5625 | 1.5661 ✓ |
| FHD25 raw | 1.5625 | 1.5792 ✓ | 1.5625 | 1.5661 ✓ |
| DCI4K24 raw | 1.4648 | 1.4805 ✓ | 0.999 | 3.008 ✗ |
| UHD30 raw | 1.5625 | 1.5792 ✓ | 0.999 | 3.008 ✗ |

`+0x60` 只在**預覽由縮放器產生**時對得上。UHD30/DCI4K24 那兩列對不上,是因為
它們的預覽走**感測器側 ÷3 的路**(2016×1135),縮放器就擺 unity。
縮放器實測最大只到 2.0,做不出 3.0。

這和 plan 的 `RW_ON = 0x400` / `RW_OFF = 0x640` 是同一套編碼。

## 5c. OG6K over HDMI RAW 的完整欄位清單

捐贈者 **p0x180 `UHD23_98CROP`**(2026-09-17 使用者選定)。全 65 欄稽核過,
對 p16E(UHD30 raw)只差 17 欄,而且**兩件已經是對的**:

```
+0x080/+0x084   7 / 11        平面格式已是 HDMI raw 的 12-bit 預覽 / 16-bit RAW
+0x0FC/+0x100   1.0 / 1.0     感測器縮減倍率已是 ÷1
```

比 p13/p14 那種 0x0 空白模板(對 p16E 差 28 欄)好得多。

要改的:

```
+0x000/+0x004   3840x2160 -> 6064x4042      rec
+0x024/+0x02C   3840x2160 -> 6064x4042      active(HdmiRaw 的 act == rec)
+0x0DC/+0x0E4   3840x2160 -> 6064x4042      生產者
+0x0F4/+0x0F8   4176x2174 -> 6064x4042      感測器輸入(現在是 crop 柵格)
+0x00C/+0x010   1936x1087 -> 2016x1344      預覽柵格(÷3 的全 3:2)
+0x020/+0x028   1920x1077 -> 2000x1334      預覽可見
+0x0D8/+0x0E0   1936x1087 -> 2016x1344      生產者預覽
+0x060/+0x0D0   2048      -> 1023           預覽 RWZM -> unity
+0x064/+0x0D4   1023         不變           RAW 平面本來就 unity(CROP profile)
+0x030          24.0      -> 跟著格率
```

**RAW 那一半不用動** —— p0x180 是 CROP profile,RAW 平面原本就沒在縮放。
預覽照 UHD30raw 的做法:縮放器 unity,預覽由感測器側 ÷3 供應,
而 OG6K 的全 3:2 對應的 ÷3 預覽正好是 **2016×1344**(= OG2K 的畫幅,
也是相機閒置時跑的 MONIT1_60)。

## 5d. 分派樹 —— 完整解出 [C]

`XC_LiveViewConfiguratorW71c1__v3 @ 0xC043BE68` 依 LV type 與三個並列旗標分派:

```c
iVar3 = *param_2;                              // LV type
...
else if (iVar3 == 2) {                         // CINE
    cVar1 = cfg[0x25];
    bVar5 = (cVar1 == 0);
    if (bVar5) cVar1 = cfg[0x26];
    if (bVar5 && cVar1 == 0) {
        if ((char)param_2[9] == 0)   FUN_c043b988(...);   // param_2[9] = cfg[0x24]
        else                         FUN_c043b828(...);   // <- 我們 hook 的 CDNG 選擇器
    } else                           FUN_c043b988(...);   // 0x25 或 0x26 有設
}
```

**所以要進到 HdmiRaw 表,條件是 `cfg[0x26] != 0` 且 `cfg[0x47] == 0`。**

`cfg[0x24]` = 「是 CinemaDNG」。這也順帶解釋了我們的 `FUN_c043b828` hook
為什麼只在 CDNG 時被呼叫。

## 5d-2. 註冊的介入點 —— 兩道指令 [C]

`FUN_c043b988` 是 **ARM 模式**(`0xC043B988 = E92D4070` = `push {r4,r5,r6,lr}`)。
HdmiRaw 的查表呼叫在 `0xC043BAB0`,表位址就在它前面兩道指令:

```
0xC043BAA0  E3051450   movw r1, #0x5450
0xC043BAA4  E1A0200D   mov  r2, sp
0xC043BAA8  E34C10BE   movt r1, #0xC0BE      -> r1 = 0xC0BE5450
0xC043BAAC  E1A00005   mov  r0, r5
0xC043BAB0  EB0004D8   bl   0xC043CE18
```

**不需要 trampoline,不需要 hook 程式碼。** 改那兩道立即數就好:

```
私有表 0xC0733000(舉例):
  0xC043BAA0   E3051450 -> E3031000    movw r1, #0x3000
  0xC043BAA8   E34C10BE -> E34C1073    movt r1, #0xC073
```

(編碼器已用原廠那兩道指令做過往返驗證。)

比 CDNG 那邊乾淨得多 —— `FUN_c043ce18` **只被這一處呼叫**,而 CDNG 那邊要同時
處理三張表。

### 私有表的形狀

搜尋器的 span 是**寫死**的 `param_2 + 0x1C0`,所以私有表必須正好 **448 bytes
= 28 筆**,不能多也不能少(多的掃不到,少的會掃出界)。

```
27 筆照抄原廠 + 1 筆 OG6K
犧牲掉 UHD23_98CROP —— 正好就是我們借 profile p0x180 的那一筆,
沒有多犧牲任何別的模式。
```

OG6K 的條目:`{const=3, profile=0x180, mode=3, key_ptr=<我們的字串>}`
(`mode 3` = M3 `MONIT1_30`;`const` 是 **3** 不是 CDNG 的 5)。

## 5e. 還沒做的

1. ~~私有表 + 改導~~ —— **實作完成:`../build/og6k_hdmi/`**(2026-09-17)。

   ```
   build.py        離線計畫產生器,187 筆寫入(其中只有 2 筆是程式碼)
   test_build.py   22 個測試,全部通過
   ```

   刻意**不**接進 `og3k_plan.py` —— 那支檔案整個圍繞 CDNG 流程(fmttable hook、
   canvas hook、fps hook、UI、CSV),HDMI 這條是另一種機制,硬接進去只會讓
   已經驗證的三個 target 冒風險。

   換掉的四筆:

   ```
   [15] UHD30CROP    -> OG6K30
   [16] UHD25CROP    -> OG6K25
   [17] UHD24CROP    -> OG6K24
   [18] UHD23_98CROP -> OG6K23_98
   ```

   四個捐贈 profile **只差 `+0x030` 標稱 fps,而且那個欄位本來就對**,
   所以四個共用同一組幾何修改,fps 連寫都不用寫。
   `+0x064 / +0x0D4`(RAW 平面 RWZM)原本就 unity,也不寫 —— 有測試守著這兩條,
   免得後人「順手補齊」反而增加風險。

   測試裡最重要的三個:
   - 編碼器必須能重現原廠那兩道指令(否則它就是錯的)
   - 沒有任何一筆寫入落在原廠表 `0xC0BE5450..0xC0BE5610` 內
   - 未替換的 24 筆必須逐字與原廠相同

2. **誰設 `cfg[0x26]` [?]** —— **不是阻礙**(2026-09-17 使用者指出):
   真正測試的人會有 Atomos/BMD 錄影機,相機自己會設這個旗標。
   這一項只影響「我們能不能在沒有錄影機的桌上自行驗證」,不影響能不能做。

   以下是追過但沒追到底的紀錄: —— **用 grep 找不到**,2026-09-17 試過四種過濾:
   `+0x26` 的寫入(33 個)、`+0x24/+0x25/+0x26` 至少兩個(21 個)、
   `+0x26`&`+0x47`(4 個)、`+0x45`&`+0x47`(9 個)。逐一看過的候選:

   | 候選 | 實際是什麼 |
   |---|---|
   | `FUN_c02e6f48` | Display 模組的邊緣偵測 `cfg[0x24] = (~new) & old` |
   | `FUN_c0152a38` | MMIO(`0x3021xxxx`)暫存器程式化 |
   | `FUN_c04c6ac0` | 色彩範圍設定(0x10/0xF0/2),另一個結構 |

   這些 offset 太常見,靜態搜尋一直撈到假陽性。

   **改用原始檔結構去追,比 grep 有效得多**(2026-09-17 第二輪):

   韌體的 assert 字串帶著原始檔路徑。LiveViewState 只有四個檔:

   ```
   inc/LiveViewModeMgr.h
   src/LiveViewModeMgr.cpp                  <- HdmiLimit 等 7 個函式在這
   src/config/w71c1/LiveViewConfig_w71c1.cpp <- XC_LiveViewConfiguratorW71c1__v2/v3
   src/config/w91c1/LiveViewConfig_w91c1.cpp
   ```

   由此確認 config 的類別是 **`XC_LiveViewDispParam`**(vtable slot 在同一檔),
   建構者是 **`FUN_c0436b80 @ 0xC0436B80`** —— 它從全域 context 填一個
   **92 bytes(0x5C)** 的結構,正好涵蓋 0x24..0x47。

   在 `param_4 == 0` 分支裡:

   ```c
   if ((param_1 < 2) && (param_2[8] != 0)) {
       param_2[9] = param_3[0x167];      // cfg[0x24..0x27] <- ctx + 0x59C
       ...
   }
   ```

   **`cfg[0x24]`(CinemaDNG)、`[0x25]`、`[0x26]`(HdmiRaw)是同一個字的三個
   位元組。** 但那段被 `param_1 < 2` 擋住,而 CINE 的 LV type 是 2。

   實機驗證(2026-09-17,ctx = `0xC3074BE8`,讀 `0xC3075184`):

   ```
   MOV        ctx+0x59C = 0x00000000
   CinemaDNG  ctx+0x59C = 0x00000000     <- 不跟著變
   切回 MOV   ctx+0x59C = 0x00000000
   ```

   **和反編譯一致 —— CINE 不走那條路。** 所以 ctx+0x59C 是非 CINE 的來源,
   CINE 的來源仍未確定 [?]。

   `FUN_c0436b80` 有四個呼叫點,三個 `param_4 = 0`,一個(`blk_c04.c:37020`,
   在 `FUN_c04369d8` 內)傳 `puVar3[0x18]`。那條 `*param_4 == 5` 分支會先把
   整個結構清零再只填五個欄位,也沒寫 0x24。

   **下一步從 `blk_c04.c:37020` 的 `puVar3[0x18]` 往回追**,或確認
   configurator 的 `param_2` 是否根本是另一個(包含 DispParam 的)物件 ——
   目前兩者的欄位偏移相容,但沒有證據它們是同一個。

## 6. 相機目前的狀態

**已全部還原(2026-09-17)。** `0xC00ECA10` 回到 `0x8D04F84D`,
`SetMovRecFormat` / `SetHdmiOutputInfo` / `SetHdmiOutputSize` /
`SetHdmiOutputFramerate` 都回到基準值 0 / 1 / 1 / 5。相機是乾淨的。

(`SetHdmiOutputSize` 與 `Framerate` 是相機在「以為有錄影機」時**自己**改的,
補丁還原後不會自動退回,要手動設。)

## 7. 還要更正的一件事

我先前說「改 `0xC07440A4/A8` 那兩個字就能讓 HDMI 輸出 6064×4042」——
**那是錯的**。`MenuItemHdmiOutputSize__v3` 的四組尺寸
(1280×720 / 1920×1080 / 3840×2160 / 4096×2160)是**選單顯示與自動選擇**用的,
而且 §4a 證明實際輸出還要和 sink 的 EDID 協商。畫幅不是從那張表來的。

真正的入口是 §1 的格式表。
