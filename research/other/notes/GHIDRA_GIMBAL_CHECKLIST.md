# 互動式 Ghidra 追 GIMBAL opcode / 對焦 dispatch — 操作 Checklist

目標:在 Ghidra GUI 把 **GIMBAL 各指令的 PTP opcode + 參數格式 + 對焦 session 流程**逐一挖出來。
本 checklist 針對本韌體的兩個障礙客製:(a) IAR 用 **movw/movt** 建位址(headless 沒建 xref);
(b) 指令派發是 **switch**(不是指標表)。GUI 的分析器能解掉這兩個,headless 不行。

專案:`ghidra_proj/SIGMAfp`,program `seg0_c0000000.bin`(base 0xC0000000)。
```sh
JAVA_HOME=$PWD/tools/jdk/Contents/Home tools/ghidra/ghidra_12.1.2_PUBLIC/ghidraRun
```

---

## STEP 0 — 讓 movw/movt 產生 XREF(最關鍵的前置）

headless 之所以追不到,就是這步沒做。GUI 裡:

1. 開 `seg0_c0000000.bin`。
2. **Analysis → Auto Analyze**,勾選確認這幾個有跑:
   - `ARM Aggressive Instruction Finder`
   - `ARM Symbol` / `Constant Reference Analyzer`（把 movw+movt 對解成位址參照）
   - `Decompiler Parameter ID`
   - `Reference`
3. 跑完後驗證:跳到 `0xC04F5AE8`（已知的 0x9032 handler),Decompiler 應該直接顯示
   `"(0x9032)SetCamDataGroupFocus"` 字面字串（不再是 `DAT_c0cf5a60`）。若顯示出來 → xref 已建立,可繼續。
   若沒有 → 對該 `movt` 指令右鍵 `References → Create Reference`,或補跑 `ARM Constant Reference Analyzer`。

---

## STEP 1 — 用「log 字串」直接撈 opcode↔handler（最快的一招）

本韌體每個 Set 指令 handler 都會 log `"(0x90XX)指令名"`。善用這點:

1. **Search → For Strings…**,filter regex：`\(0x9[0-9A-F]{3}\)`
2. 每個命中字串 → 右鍵 `References → Show References to`（STEP 0 後才有 xref）→ 跳到 handler。
3. 這樣一次得到所有 **Set\* 指令的 opcode↔handler**（已知:0x9016–0x902A,0x9032 focus,0x9034 movie,0x9038 gps,0x9109,0x9433）。
4. 若 GIMBAL handler 也 log 自己的名字：Search Strings filter `GIMBAL_` → 各名字 → `References to` → 找到各 GIMBAL handler 函式。**先把這些 handler 都命名/標好。**

> 已知錨點:`"(0x9032)SetCamDataGroupFocus"` @ `0xC0CF5A60`；GIMBAL 名字表 @ `0xC0CF4D30`–`0xC0CF5050`；
> `GIMBAL_ExecRelativeFocusDriving` 字串 @ `0xC0CF4F74`。

---

## STEP 2 — 找 opcode 派發器（switch）

從已知 handler 反推 dispatcher：

1. 到 `FUN_c04f5ae8`（0x9032 handler）。它是某 **命令類**的方法。在 Listing 左側看它的 **Namespace/vtable**：
   右鍵函式名 → `References → Show References to`。命中的多半是**該類的 vtable slot**。
2. 對 vtable 位址再 `Show References to` → 找到**建構該命令物件**的函式（命令註冊處）。
   IAR 模式下建構子會 `movw/movt` 載入 vtable + 寫入 **opcode 欄位**（一個 `str #imm` 到物件 +offset）。
   在建構子的 Decompiler 裡找 `obj->field = 0x9032;` 這種賦值 → 確認 opcode 存在物件哪個 offset。
3. 找**主 dispatcher**：它拿收到的 PTP opcode,對照命令物件的 opcode 欄位或一個 switch。
   在 PTP 模組（`0xC04E0000`–`0xC0510000`,`ptpcmd` 原始檔）用 **Search → For Scalars** 找值 `0x9032`
   或 `0x9433`；命中的函式若是大 switch → 就是 dispatcher。
4. dispatcher 找到後,Decompiler 會把整個 `switch(opcode)` 展開,**每個 case 標籤就是一個 opcode**,
   case body 呼叫對應 handler → **GIMBAL 各子指令的 opcode 一次全出**。
   若 Ghidra 沒把 switch 認出來（跳表沒 fixup）：在 indirect `BX/BLX` 指令上右鍵
   `→ Fix up Jump Table` / 手動 `Create Jump Table`,指定 index 範圍,Ghidra 會補回 case。

---

## STEP 3 — 若 GIMBAL 是「單 opcode + 子命令」模型

GIMBAL 系列很可能共用一個 0x94xx opcode,再用**第一個 PTP Parameter 或 data 首欄位當子命令碼** switch。判斷法：

1. 到某個 GIMBAL handler（STEP 1 找到的),看它是否讀「參數1」再 switch。
2. 若是：那唯一的 PTP opcode = GIMBAL 群共用 opcode（用 STEP 2.3 的 Scalar 搜尋 0x94xx 確認,
   `SetGpsParam=0x9433` 是錨點,GIMBAL 群應相鄰）;**子命令碼**就是各 `GIMBAL_*` 的實際值,
   在該 switch 的 case 標籤上。
3. 把每個 case 對應到 STEP 1 命名的 handler（`ExecRelativeFocusDriving` / `SetCamFocusAllowance` /
   `OpenApplication`…），即得「opcode + 子碼」完整映射。

---

## STEP 4 — 解參數格式(TLV / data phase)

focus/資料類指令的 data phase 是 **CamDataGroup TLV**：`[u32 ?][u32 count][entries×12B: {u16 tag,…,value}]`。
解析器已定位：

- `FUN_c0501350(parser, dataPtr, dataLen)` — 初始化（entry 數在 dataPtr+4,entries 在 +8,每筆 0xC）
- `FUN_c0501508(parser, tag, dest, maxlen)` — 依 **tag** 取值

做法：
1. 到目標 handler,把 `FUN_c0501508` 的呼叫逐行看,**第 2 引數就是 tag、第 4 引數是大小** →
   直接列出該指令吃哪些 tag/型別。（SetCamDataGroupFocus 已解:tags 1,2,3,4,0xa..0xe,0x33,0x34,0x50,0x51 —
   見 `notes/research/interfaces/../../interfaces/notes/PTP_OPCODES.md §3`。）
2. GIMBAL 對焦指令（`ExecRelativeFocusDriving` 等）多半直接吃 PTP **Parameter 1..5**（非 TLV）：
   在 handler 開頭看它從命令容器（通常 `param+0x0C`/`+0x10`…）讀哪幾個 32-bit 參數 →
   即 relative/absolute 驅動量、方向、速度等。

---

## STEP 5 — 驗證對焦閘控差異（回應你的實際問題）

1. 到 `FUN_c04f5ae8`（0x9032）與 `FUN_c04ef1f8`（較寬鬆路徑）,兩者都呼叫 `FUN_c04ef7d0`（對焦驅動器 @`0xC04EF7D0`）。
2. 比對兩者對 `captureState`（全域 `0xC3033834`,getter `FUN_c0017ac8` = base+0x18）的檢查：
   - 0x9032：`state[0x220]==0 && state[0x7c]==0` 才驅動 → 錄影擋
   - `FUN_c04ef1f8`：`state[0x220]!=1` → 較寬鬆
3. **關鍵待解**:`state[0x220]` 錄影時的值。在 GUI 追它的**寫入者**：
   - 到 `0xC3033834`,`Show References to` → 篩出**寫入**（STR）的函式。
   - 找錄影起停相關者（`MovRecFuncStateREC*` / SnapCommand）→ 看它把 `state[0x220]` 設成幾。
   - 若錄影時 `state[0x220]==2`（非 0 非 1）→ GIMBAL 路徑可繞過;若 `==1` → 無軟解。
   （headless 追不到寫入者,因為都用 base+offset;GUI 的 `References to` 對全域變數能完整列出讀寫。）

---

## STEP 6 — 交叉驗證（強烈建議）

把 STEP 2–4 得到的 opcode/參數,跟**真實 USB 側錄**對照（Wireshark + usbmon/USBPcap,側錄 SIGMA 官方
app 或會控焦的雲台）。兩邊一致才算定案。詳見 `notes/research/interfaces/../../interfaces/notes/PTP_OPCODES.md §5`。

---

## 快速錨點表(直接跳這些位址）

| 位址 | 是什麼 |
|---|---|
| `0xC04F5AE8` | SetCamDataGroupFocus (0x9032) handler — dispatch 反推起點 |
| `0xC04EF1F8` | 較寬鬆對焦路徑（疑似 GIMBAL Exec\*FocusDriving） |
| `0xC04EF7D0` | 共用對焦驅動器（兩條路徑都呼叫它;內含 mode==2 檢查） |
| `0xC0501350` / `0xC0501508` | CamDataGroup TLV parser（讀參數格式用） |
| `0xC3033834` | captureState 全域（+0x18+0x220 = 錄影閘欄位;追寫入者） |
| `0xC0CF4D30`–`0xC0CF5050` | GIMBAL_\* 命令名字串表 |
| `0xC0CF5A60` | `"(0x9032)SetCamDataGroupFocus"` log 字串（STEP 1 範例） |
| `0xC04E0000`–`0xC0510000` | PTP 模組（dispatcher / handlers 都在此區） |

## 一句話策略
**STEP 0（建 xref）→ STEP 1（log 字串撈 handler）→ STEP 2/3（反推 dispatcher 讀 switch 得 opcode）
→ STEP 4（TLV/參數）→ STEP 5（對焦閘）→ STEP 6（USB 側錄對帳）。**
其中 STEP 0 是 headless 做不到、GUI 才有的關鍵;做完後 STEP 1 的「log 字串→xref」會讓大部分 opcode 直接浮現。
