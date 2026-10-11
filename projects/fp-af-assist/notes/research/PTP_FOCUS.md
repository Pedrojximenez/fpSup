# SIGMA fp — PTP 對焦控制在錄影時失效：原因與可能解法

## 症狀
PTP 對焦指令在**待機/LiveView 可用**,但**錄影中送同樣指令沒反應**(指令被接受、對焦馬達不動)。

## 根因(反編譯確認)

你用的很可能是 **`SetCamDataGroupFocus`(PTP opcode `0x9032`)**,處理器 `FUN_c04f5ae8`。
它解析對焦欄位後,**對焦驅動被閘控**:

```c
// FUN_c04f5ae8  (0x9032 SetCamDataGroupFocus)
... 解析對焦目標到 obj+0x178 ...
lock();  state = getCaptureState();      // 全域單例 @0xC3033834
if (state[0x220] == 0 && state[0x7c] == 0) {
    FUN_c04ef7d0(target);                // ← 只有「閒置狀態」才真的驅動對焦
}
// 否則:指令被 ACK,但對焦不動  ← 你的症狀
```

- `state[0x220]` = **拍攝狀態(capture state)**。確認依據:它在 `GetCamStatus` 類回應裡被
  原樣回報給電腦(`*resp = *(u16*)(state+0x220)`)——就是 fp 告訴 tethering app「我現在在幹嘛」。
  待機時為 0(允許對焦);進入錄影/拍攝時變非 0 → 對焦驅動被跳過。
- 底層執行器 `FUN_c04ef7d0` 還會要求**相機模式 == 2(LiveView)**,並檢查對焦位置範圍/AF busy,
  不符就回 PTP 錯誤 **`0x200f`**(Operation Not Possible)。錄影時 LiveView 仍在(模式維持 2),
  所以擋點是上面 handler 層的 `state[0x220]` 閘,不是模式。

**結論**:這是**刻意的設計閘控**——標準 tether 對焦指令只在相機閒置時允許外部拉焦。
錄影中,fp 預期對焦交給機內連續 AF 或鏡頭環,不接受外部絕對/相對定位。

## 可能解法:改用 GIMBAL_* 對焦指令(需實測)

韌體裡對焦有**多個進入點,閘控寬鬆度不同**(都呼叫同一個驅動器 `FUN_c04ef7d0`):

| 進入點 | 對應指令(推定) | 驅動條件 |
|---|---|---|
| `FUN_c04f5ae8` | **SetCamDataGroupFocus (0x9032)** | `state[0x220]==0 && state[0x7c]==0`(**最嚴,錄影必擋**) |
| `FUN_c04ef1f8` | **GIMBAL_Exec*FocusDriving** | `state[0x220] != 1`(**較寬鬆**) |
| `FUN_c04f1848` | (AF 類) | `state[0x204]==1` |

`FUN_c04ef1f8` 的閘是 `state[0x220] != 1` 而非 `== 0`。若錄影時 `state[0x220]` 是「非 0 且非 1」
的值(例如 2),則:
- `SetCamDataGroupFocus` → `state[0x220]!=0` → **擋**
- `GIMBAL_Exec*FocusDriving` → `state[0x220]!=1` → **仍會驅動** ✓

SIGMA 的 **GIMBAL_*** 系列(`GIMBAL_OpenApplication / GIMBAL_GetFocusPosition /
GIMBAL_SetCamFocusAllowance / GIMBAL_ExecRelativeFocusDriving / GIMBAL_ExecAbsoluteFocusDriving /
GIMBAL_StartAutoFocus …`)正是為**外接雲台/穩定器**設計的——雲台本來就要在**錄影中拉焦**,
所以這條路徑的狀態閘刻意放寬。

### 建議測試流程
1. 送 **`GIMBAL_OpenApplication`** 開 session(進入雲台控制模式)。
2. 送 **`GIMBAL_SetCamFocusAllowance`**(啟用對焦驅動許可)。
3. 錄影中送 **`GIMBAL_ExecRelativeFocusDriving`** / **`GIMBAL_ExecAbsoluteFocusDriving`**。
4. 對照:同場景用 `SetCamDataGroupFocus (0x9032)` 應無效,GIMBAL 版應有效。

> 完整 GIMBAL 操作集見 `notes/research/interfaces/../../interfaces/notes/PTP_CINEMADNG.md` §2(命令名表 seg0 0xC0CF4F14–0xC0CF5050)。

## 信心與界線
- 「`SetCamDataGroupFocus (0x9032)` 的對焦驅動被 `state[0x220]/[0x7c]` 閘控、錄影時擋掉」
  —— **反編譯確認**(handler `FUN_c04f5ae8`)。
- 「`state[0x220]` = 拍攝狀態、會回報給 PC」—— **確認**(GetCamStatus 回應複製此欄位)。
- 「GIMBAL 對焦路徑在錄影中可用」—— **強推論**(不同、較寬鬆的閘 + 雲台用途),
  但 `state[0x220]` 錄影時的**確切數值**無法純靜態確認(寫入者用 base+offset,不可靜態解析),
  故此解法**需實測**驗證。若 GIMBAL 路徑也擋,代表錄影時 `state[0x220]` 正好 ==1,那就無軟解。

## 產出
- `out/decomp/setfocus.c`(0x9032 handler)、`out/decomp/gimbalfocus.c`(對焦模組 22 函式)、
  `out/decomp/focusgate.c` / `focusdrv_callers.c`(驅動器與所有進入點)
