# fp Ver.5.02 人臉顯示資料路徑離線稽核（2026-09-27）

本次僅讀本地反編譯與 ROM；沒有 USB、socket 或相機 I/O。使用者已更正「不容易判斷螢幕是否有人臉框」，因此螢幕框可見狀態為 **未確認**；不能以此宣稱 UI 與 DetectionResultMgr 互相矛盾。

## 結論與固定讀取候選

DisplayFaceFrame 使用 SysStatus 的 detection publication 與兩份固定顯示副本，無須追查 heap。它們可用來確認 publication／UI 消費路徑是否有資料，但不能單憑非零資料判定畫面確實有框、主體 identity 連續、資料新鮮或可供幾何對焦。

| 名稱 | 固定基底 F | 建議首段 | 座標／state 尾段 |
| --- | --- | --- | --- |
| SysStatus focus publication | `C3033AC4` | F + `0x00..0xA7`，42 words | `C3033DDC`，8 words |
| DisplaySysStatusFocusObserver 共用副本 | `C3433C58` | F + `0x00..0xA7`，42 words | `C3433F70`，8 words |
| DisplayFaceFrame render 副本 | `C3434474` | F + `0x00..0xA7`，42 words | `C343478C`，8 words |

三個 F 的首段包含 12-byte header 與第一張臉的三個 52-byte 子槽；尾段為 F + `0x318..0x337`。這是檢查第一主體與當前選中子槽的有限讀取，不包含其餘四組人臉。

補充固定範圍：

| 地址 | words | 意義 |
| --- | --- | --- |
| `C34348E4` | 1 | renderer F + `0x470` 的顯示型別；只有顯示副本有此附加欄位，勿把 SysStatus F + `0x470` 當同類欄位 |
| `C3435A54` | 9 | renderer object 32 bytes 與其初始化 guard；object + `0x18` 應指向 `C3434474`，+ `0x1C` 建構後 vtable 為 `C0B53BC8` |
| `C30338E8` | 1 | word byte 2，即 `C30338EA`，為 renderer 檢查的 SysStatus 抑制旗標 |
| `C3426318` | 3 | 顯示 observer 的抑制／更新控制；`C3426318`、`C3426320`、`C3426321` 分別在下述消費路徑使用 |

全部候選合計 656 bytes，均為固定 RAM 位址；每次依既有工具以有限 word chunk 讀取、不重試、不呼叫 getter，不變更設定。更小的初查可先只讀各 F 的 3-word header，再依結果讀取已列明的固定槽位。

## Producer → publication → display

1. `FUN_c05aaff8` 把 face detector 結果排成至多 5 組，每組 `0x9C = 3 × 0x34`；每組首槽是 face，後兩槽是 eyes。其寫入基底為 manager M + `0x10 + group × 0x9C`。
2. `FUN_c05a9900` 在 manager lock 內取 M + `4` 的 `0x470` bytes，經 `FUN_c0017fb0` / `FUN_c0019878` 發佈。SysStatus singleton 位於 `C3033834`；publication 在 singleton + `0x290 = C3033AC4`。SysStatus data getter 回傳 singleton + `0x18`，故消費者也以 data + `0x278` 指向同一位置。
3. `XC_DisplaySysStatusFocusObserver__v1` (`C02EB8A8`) 處理事件 `0x01000000` 時，把事件資料 + `0x278` 的 `0x470` bytes 複製至 observer 共用副本 `C3433C58`。Observer event `0x100` 另更新其 + `0x470`。
4. `FUN_c02eb9b8` 取得 `FUN_c02fa0d0()` 回傳的 renderer object `C3435A54`，再呼叫 `FUN_c02ef540` / `FUN_c02ef958`，以 `0x470` bytes 更新 renderer 副本 `C3434474`，並另寫其 + `0x470` 顯示型別。
5. `FUN_c02ef5c8` 另有從 SysStatus publication 直接複製到 renderer 副本的路徑，因此 observer 與 renderer 不能被視為必定同時更新。
6. `FUN_c02ef7d0` 實際決定是否提交 face frame；`XC_DisplayFaceFrame__v1` (`C02EF4A8`) 只是回傳型別相關常數，不是座標來源。

`FUN_c05a9900` 還受 `FUN_c03a0410()` 回傳之 debug/config flags 影響：+ `0xC` 非零走 `FUN_c05a9c10`；+ `0xF` 非零則清除發佈副本的兩個 flag。這不等於目前相機已設定該旗標，需另外固定讀取才能判定。

## 結構與顯示條件

以三個 publication 副本的 F 為基準：

| 偏移 | 離線確認之用途 |
| --- | --- |
| `+0x04`，u32 | 第一組內選中子槽；selector setter `C05AAD00` 只寫 `0`、`1`、`2` |
| `+0x08`，u8 | renderer 必須非零；face producer 在沒有可用 face 時清零，有 face 時置 1 |
| `+0x09`，u8 | renderer 也必須非零；是獨立 publication／ready 類旗標，不應直接命名為 face count |
| `+0x0C + i × 0x34` | 第一組的三個 face／eye 子槽，`i=0..2` |
| 子槽 `+0x00..0x0F` | renderer 使用的 x、y、w、h，四個 word |
| 子槽 `+0x10..0x1F` | detector/debug 座標 x、y、w、h；不要與前四 word 自動視為同一座標系 |
| 子槽 `+0x20`、`+0x24`、`+0x28`、`+0x2C` | producer 寫入的附加 raw 欄位；`+0x28` 被 debug 文本輸出為 sc，沒有經本稽核建立穩定 subject identity 語意 |
| 子槽 `+0x30`，u8 | 該子槽有效旗標；不能替代全局發佈旗標與 freshness |
| `+0x318`、`+0x31C` | 尺度／座標 dimensions；renderer 的縮放函式以 `+0x318` 第一個 word 作分母 |
| `+0x320..0x32F` | producer 複製的 ROI 四個 word |
| `+0x330` | face detector state（manager M + `0x334`）；原始 enum，不在本稽核推定 UI 設定值 |
| `+0x334` | 尾段额外 raw word；不作時間戳或序號使用 |

`FUN_c05ab360` 迴圈 5 次，只查看 `F + 0x0C + group × 0x9C + 0x30`，因此 `0x34` 是子槽 stride、`0x9C` 是 face group stride。`l_eye` (`C05AA6A8`) 的 selector 字串表 `C2DFBA18` 指向 `face` (`C2DFBEA8`)、`r_eye` (`C2DFBEB0`)、`l_eye` (`C2DFBEB8`)，因此三個子槽 index 分別為 0=face、1=r_eye、2=l_eye；本次不依眼睛標籤猜測使用者畫面方位。

Renderer `FUN_c02ef7d0` 的具體分支：

- F + `0x09` 與 F + `0x08` 均非零，且 `C30338EA == 0` 才會走提交分支。
- 讀 F + `0x04` 作子槽 index；若 F + `0x470 == 1` 且 index 非零，將 index 強制改為 0。
- 取 `F + 0x0C + index × 0x34` 的前四個 word，搭配 F + `0x318` 尺度，呼叫 `FUN_c02ef6c8`。
- 成功走此分支後 object + `0x0C` 寫 1；未滿足條件則清除既有 frame 並將其寫 0。
- object 前兩個 word 是 display implementation pointers；缺少有效 implementation 時，提交函式可不做繪製。即使 + `0x0C == 1`，仍不能單憑它宣稱實體螢幕有可見框。
- `C3426318` 非零會讓 observer 不呼叫更新函式；`C3426320` 非零走清框後更新資料但不立即繪製的路徑。非零／舊副本可能只是停留資料。

所有 shell raw reads 都非原子、不取得 native lock，也沒有保證跨副本共同 epoch；只可診斷來源，不能把這些資料直接標記 `geometry_usable=true` 或作為啟動鏡頭控制的依据。

## ROM ARM 交叉證據

對照檔案：`out/seg0_c0000000.bin`，base `C0000000`，SHA-256 `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`。以下由該檔案使用 Capstone ARM mode 解碼，沒有依赖相機回應。

| ROM 指令位置 | bytes（little endian）／指令 | 證據 |
| --- | --- | --- |
| `C00178DC`、`C00178E0` | `344803e3` / `movw r4,#0x3834`；`03434ce3` / `movt r4,#0xc303` | SysStatus singleton |
| `C0017ACC` | `18108ce2` / `add r1,ip,#0x18` | data getter offset |
| `C0017FC0` | `291e84e2` / `add r1,r4,#0x290` | publication offset |
| `C0017FC8` | `0134a0e3` / `mov r3,#0x1000000` | publication event |
| `C02EBA5C`、`C02EBA60` | `584c03e3` / `movw r4,#0x3c58`；`43434ce3` / `movt r4,#0xc343` | observer static buffer |
| `C02EB8D4`、`C02EB8D8`、`C02EB8DC` | `9e1f86e2` / `add r1,r6,#0x278`；`472ea0e3` / `mov r2,#0x470`；`32a5f4eb` / `bl C0014DAC` | observer memcpy |
| `C02EF3D0`、`C02EF3D4` | `740404e3` / `movw r0,#0x4474`；`43034ce3` / `movt r0,#0xc343` | renderer static buffer |
| `C02EF42C`、`C02EF434` | `e7ffffeb` / `bl C02EF3D0`；`181084e5` / `str r1,[r4,#0x18]` | renderer object contains static buffer pointer |
| `C02FA0D4`、`C02FA0D8` | `544a05e3` / `movw r4,#0x5a54`；`43434ce3` / `movt r4,#0xc343` | renderer object |
| `C02FA0F8`、`C02FA0FC`、`C02FA100` | `c80b03e3` / `movw r0,#0x3bc8`；`b5004ce3` / `movt r0,#0xc0b5`；`1c0084e5` / `str r0,[r4,#0x1c]` | concrete object vtable |
| `C02EF7E0`、`C02EF7EC` | `0910d1e5` / `ldrb r1,[r1,#9]`；`0810d115` / `ldrbne r1,[r1,#8]` | two display gates |
| `C02EF800` | `9e10d0e5` / `ldrb r1,[r0,#0x9e]` | SysStatus suppression at `C3033834+18+9E` |
| `C02EF810` | `047091e5` / `ldr r7,[r1,#4]` | selected subslot |
| `C02EF818` | `701491e5` / `ldr r1,[r1,#0x470]` | attached display type |
| `C02EF840`、`C02EF844`、`C02EF848` | `3420a0e3` / `mov r2,#0x34`；`0c1081e2` / `add r1,r1,#0xc`；`971221e0` / `mla r1,r7,r2,r1` | selected rectangle address |
| `C02EF864` | `c63f81e2` / `add r3,r1,#0x318` | scale coordinate argument |
| `C02EF8A4`、`C02EF8D8` | `0c5084e5` / `str r5,[r4,#0xc]`；`0c1084e5` / `str r1,[r4,#0xc]` | submitted count 1 / cleared count 0 |
| `C05AB378..C05AB38C` | `add r3,r1,r1,lsl #1`；`mov r4,#0x34`；`mul r3,r4,r3`；`add r4,ip,#0xc`；`add r3,r3,r4`；`ldrb r3,[r3,#0x30]` | group stride 3 × 0x34 |
| `C05AB3A0` | `050051e3` / `cmp r1,#5` | 5 face groups |

## 可復查的反編譯位置

- `out/decomp/full/blk_c00.c:21475`：singleton `FUN_c00178d8`。
- `out/decomp/full/blk_c00.c:21558`：`FUN_c0017ac8`。
- `out/decomp/full/blk_c00.c:21886`：publication `FUN_c0017fb0`；`23621`：locked compare/copy `FUN_c0019878`。
- `out/decomp/full/blk_c02.c:152345`：`XC_DisplaySysStatusFocusObserver__v1`；`152384`：`FUN_c02eb9b8`；`152413`：`FUN_c02eba58`。
- `out/decomp/full/blk_c02.c:155547`：renderer buffer getter；`155645`：direct SysStatus copy；`155718`：`FUN_c02ef7d0`。
- `out/decomp/full/blk_c02.c:164281`：renderer object singleton。
- `out/decomp/full/blk_c05.c:130616`：`FUN_c05a9900`；`131593`：`FUN_c05aaff8`；`131687`：`FUN_c05ab360`。

以上行號僅方便搜尋；應以函式標籤和 ROM 地址作穩定證據索引。
