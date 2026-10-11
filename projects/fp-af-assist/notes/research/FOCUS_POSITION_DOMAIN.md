# SIGMA fp — 對焦位置域:PTP vs GIMBAL 單位關係(反組譯確認)

## 結論
- 存在單一「對焦位置控制物件」(singleton @ `0xc347fa6c`,vtable 式),定義一個**絕對位置域**。
- **PTP** 給的兩個整數 = **min / max**(行程端點)= `FUN_c02dffb0()` / `FUN_c02dffd0()`。
- **GIMBAL** 只能**設定相對**(0x9411 ExecRelativeFocusDriving),**沒有絕對設定**。
- 但 **GIMBAL 讀得到目前的絕對位置**:`GIMBAL_GetFocusPosition`(0x9405)回 `(1, current_abs)`,
  其中 `current_abs = FUN_c035fd48()`,**與 min/max 同一絕對域**。

## 鐵證:相對驅動器內部把 current/min/max 綁同域

`0x9411` handler `FUN_c04ef000`(反組譯,decompile 缺此函式):
```
c04ef108  FUN_c035fec8(3)             → 取鏡頭縮放係數 scale
c04ef11c  s1 = user_delta (float, r6+0xc)
c04ef128  s0 = user_delta * scale
c04ef12c  s0 = s0 / 20.0
c04ef130  r4 = (int)s0                 → 位置位移量 pos_delta
c04ef158  bl FUN_c035fd48             → sl = current_abs  (★ = 0x9405 回傳值)
c04ef164  r1 = r4 + sl                → target = current + pos_delta
c04ef16c  bl FUN_c02dffb0             → min
c04ef174  bl FUN_c02dffd0             → max
c04ef17c… clamp target ∈ [min,max]
c04ef1d0  bl FUN_c035ffc0(target)     → 驅動到絕對 target
```
→ `current + delta` 要夾進 `[min,max]` ⇒ **current 與 min/max 同刻度 = 絕對位置**。

## 位置域函式對照

| 量 | 函式 | 說明 |
|---|---|---|
| current(絕對) | `FUN_c035fd48` (vtable+0xb4) | GIMBAL 0x9405 回的第二個整數 |
| min | `FUN_c02dffb0` = base − off_lo | PTP 兩整數之一 |
| max | `FUN_c02dffd0` = base + off_hi | PTP 兩整數之一 |
| set 絕對(內部) | `FUN_c035ffc0` / shell `setfpos`(vtable+0xa8) | 驅動器目標 |
| 相對縮放係數 | `FUN_c035fec8(3)` = `FUN_c0360760(obj,3)` | **鏡頭相關**,執行期取 |

## GIMBAL 相對「單位」= 被鏡頭係數縮放
```
實際位置位移 pos_delta = round( 送的值 × lens_scale(3) / 20 )
```
所以 GIMBAL 相對值**不是 1:1 位置單位**(× 鏡頭係數 / 20)。這就是「GIMBAL 單位不同」的來源。

## 閘控
- `GIMBAL_GetFocusPosition`(0x9405)與相對驅動都需 **mode==2 (LiveView)**(`FUN_c035f560`),否則 `0x200f`。
- 0x9405 回 `(1, current)`:第一個是有效旗標(常數 1),**不是 min**。

## 用「只能相對」的 GIMBAL 做絕對定位(閉迴路)
1. 開機讀一次 (min,max)(PTP)。
2. 讀 current_abs(0x9405 第二整數)。
3. 標定 scale:送已知相對值 V、量 Δcurrent → `scale = Δ×20/V`。
4. 之後要到 target_abs:送 `V = (target_abs − current_abs) × 20 / scale`;因 round+clamp,重讀 0x9405 收斂。
- ✅ 位置域可完全閉迴路。
- ❌ 仍拿不到「絕對位置 ↔ 公尺距離」(需鏡頭距離表,PTP/GIMBAL 不給;見 `LENS_DATA_ACCESS.md`)。

## 信心
- current/min/max 同絕對域、相對=current+scaled_delta 後夾限、0x9405 回 current —— **反組譯確認**。
- `lens_scale(3)` 實際數值隨鏡頭(執行期物件)—— 需實測標定。
