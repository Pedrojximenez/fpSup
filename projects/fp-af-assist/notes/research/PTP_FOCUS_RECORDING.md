# PTP/GIMBAL 錄影中控焦 — session 閘研究 (待續)

目標:錄影中控制對焦,又不失去 LiveView / 不進 GIMBAL 獨佔鎖死模式。
狀態:靜態逆向到極限,**關鍵未解點需實機測**(見 §5 實驗)。

---

## 1. 兩個對焦閘(反編譯確認)

### 1a. 一般 PTP 對焦 `SetCamDataGroupFocus (0x9032)` — 錄影中被擋
handler `FUN_c04f5ae8` @ 0xC04F5AE8,181137–181143:
```c
iVar1 = captureState + 0x18;          // FUN_c0017ac8
if (*(u32*)(iVar1+0x220)==0 && *(u8*)(iVar1+0x7c)==0)   // 兩個都要 0
    FUN_c04ef7d0(target);              // 驅動對焦
```
- `state[0x220]`:0=閒置、**1/2=拍攝/錄影**。錄影時=2 → 擋。
- 事件驅動(狀態轉換設一次,非每幀重寫)。

**閘欄位絕對位址**(captureState base `0xC3033834` + 0x18 = `0xC303384C`):
- 主閘 `[0x220]` → **`0xC3033A6C`**(u32)
- 副閘 `[0x7c]` → **`0xC30338C8`**(byte)
- ⚠️ base 0xC3033834 是分析推得,實機先 `mem get 0xC3033A6C`(待機應 0、錄影應非 0)確認。

### 1b. GIMBAL 相對對焦 `ExecRelativeFocusDriving (0x9411)` — 閘較寬
handler `FUN_c04ef000` @ 0xC04EF000:
- 閘 `state[0x220] != 1`(錄影時=2 → **過**)。
- 內部 `target = current + round(送值 × lens_scale/20)`,夾限 `[min,max]`,驅動。
- **handler 自己不檢查 GIMBAL session**(不呼叫 FUN_c04ef528)。

---

## 2. GIMBAL session 閘的真實結構

派發器 `FUN_c04ea5e8` @ 0xC04EA5E8:
```c
entry = lookup(opcode)              // {opcode, handler, name, aux}
if (entry.aux != 0 && FUN_c04ea3c0() != 0) {   // 條件式 pre-check
    if (entry.aux(&err) == 0) return err;       // 失敗 abort (aux=session檢查→0x2003)
}
entry.handler(...)
```
- **session 檢查 = `FUN_c04ef528`**:`mgr[0x728]==3` 才過,否則回 **`0x2003` (Session Not Open)**。
- **pre-check 只在 `FUN_c04ea3c0()!=0` 時跑**,而 `FUN_c04ea3c0() = (DAT_c37749e0==0)`。
  → **`DAT_c37749e0 != 0` 時 session 檢查被跳過**。
- `DAT_c37749e0` @ `0xC37749E0`:被 `FUN_c04ea6d0` 設 1、某 0x2005 錯誤路徑設 0。
  **語意混濁**(像 batch/遞迴狀態,非乾淨開關),會被韌體改寫。

## 3. GIMBAL session 由 `mgr[0x728]` 表示
- `OpenApplication (0x9401)` 進 session → `mgr[0x728]=3`。
- **鎖死副作用**(LiveView 失效、一般 API 停)推測來自別的碼讀 `mgr[0x728]==3`。
- mgr 取得:`FUN_c04f4a80()`。728 檢查散見 blk_c04:177089/177290 等。

## 4. 「假裝 gimbal 模式」的兩個候選(都需實機驗證)

| poke | 效果 | 風險 |
|---|---|---|
| `mem set mgr[0x728]=3` | session 檢查過 | ⚠️ 八成觸發鎖死(= 想避免的東西) |
| `mem set DAT_c37749e0=1` (0xC37749E0) | 跳過 session 檢查,不碰 0x728 | 可能不鎖死,但語意混濁+會被重寫,未必壓得住 |
| `mem set 0xC3033A6C=0`(錄影閘歸零) | 讓 **0x9032** 錄影中可對焦 | ⚠️ 狀態污染:GetCamStatus 說謊、錄影穩定性未知;建議「寫0→對焦→寫回2」最小窗 |

## 5. ★ 待續:實機實驗(回傳碼直接見真章,不用拆機/hack)

**核心未解問題:0x9411 到底需不需要 session?** 靜態看 handler 不查、pre-check 條件式——只有實測知道。

1. 正常 PTP 連線(**不送 OpenApplication**),待機送 **0x9411**:
   - 回 `0x2003` → session 是硬需求。
   - 回 `0x2001` 且對焦動 → **0x9411 不需 session** → 錄影中直接送即可,不用進獨佔模式!(最佳結果)
2. 若步驟1 回 0x2003:先送 **0x9404 SetCamFocusAllowance** 再送 0x9411,看沒 OpenApplication 能不能過。
3. 錄影中重複,觀察 LiveView 掉不掉。
4. 若真要 mem 路:先 `mem get 0xC37749E0` 讀常態值,再測 `=1` 能否跳過 session 且不鎖 LiveView。

**先要釐清的前提**(使用者觀察):「PTP 下整台相機不能用」是**普通 PTP 連線**就這樣,還是**進 GIMBAL session** 才這樣?→ 決定 0x9032 待機對焦到底通不通、以及有沒有救。

## 相關檔案/位址速查
| 項目 | 值 |
|---|---|
| 0x9032 handler | FUN_c04f5ae8 @ 0xC04F5AE8 |
| 0x9411 handler | FUN_c04ef000 @ 0xC04EF000 |
| GIMBAL 派發器 | FUN_c04ea5e8 @ 0xC04EA5E8 |
| session 檢查(aux) | FUN_c04ef528 @ 0xC04EF528(回 0x2003) |
| session pre-check 開關 | DAT_c37749e0 @ 0xC37749E0(==0 才檢查) |
| session 旗標 | mgr[0x728]==3(mgr = FUN_c04f4a80) |
| 錄影閘欄位 | 0xC3033A6C([0x220]) / 0xC30338C8([0x7c]) |
| 對焦驅動器 | FUN_c04ef7d0 @ 0xC04EF7D0 |
| 焦點位置域 | 見 FOCUS_POSITION_DOMAIN.md |

> 相關:`GIMBAL_MANUAL.md`、`PTP_FOCUS.md`、`FOCUS_POSITION_DOMAIN.md`。
