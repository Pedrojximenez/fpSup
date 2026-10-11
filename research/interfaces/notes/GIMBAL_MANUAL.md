# SIGMA fp — GIMBAL 外控指令說明書

PTP vendor 指令集,SIGMA 為外接雲台/穩定器設計的相機外控協定。所有 opcode + handler 位址
經韌體(fp Ver.5.02)確認;對焦域行為經反組譯 + 實機驗證。

## 0. 總覽:16 個 opcode

| opcode | 指令 | handler | 說明 |
|---|---|---|---|
| `0x9401` | GIMBAL_OpenApplication | C04EECC8 | 進入雲台 session(獨佔模式) |
| `0x9402` | GIMBAL_CloseApplication | C04EEE50 | 結束 session |
| `0x9403` | GIMBAL_GetCamState | C04EEEF8 | 讀相機狀態 |
| `0x9404` | GIMBAL_SetCamFocusAllowance | C04EEFB0 | 啟用對焦驅動許可 |
| `0x9405` | GIMBAL_GetFocusPosition | C04EEF50 | 讀目前對焦**絕對位置** |
| `0x9411` | GIMBAL_ExecRelativeFocusDriving | C04EF000 | **相對**驅動對焦 |
| `0x9412` | GIMBAL_ExecAbsoluteFocusDriving | C04EF1F8 | (絕對驅動;實機上外部只開放相對,見 §5) |
| `0x9413` | GIMBAL_StartAutoFocus | C04EF298 | 啟動 AF |
| `0x9414` | GIMBAL_StopAutoFocus | C04EF2C0 | 停止 AF |
| `0x9421` | GIMBAL_StartStillCapture | C04EF2E8 | 開始拍照 |
| `0x9422` | GIMBAL_StopStillCapture | C04EF340 | 結束拍照 |
| `0x9423` | GIMBAL_StartMovieRecording | C04EF390 | 開始錄影 |
| `0x9424` | GIMBAL_StopMovieRecording | C04EF3B8 | 停止錄影 |
| `0x9431` | GIMBAL_ShiftParameter | C04EF478 | 位移某參數(相對調整) |
| `0x9432` | GIMBAL_GetParameter | C04EF560 | 讀某參數 |
| `0x9433` | GIMBAL_SetGpsParam | C04EF6D8 | 設 GPS 參數 |

共用 aux/回應處理 @ C04EF528。

---

## 1. Session 生命週期

```
0x9401 OpenApplication        → 進入雲台外控 session
  (mgr[0x728] = 3, 獨佔模式)   ⚠️ 進入後: 一般 PTP API 失效、USB LiveView 失效
0x9404 SetCamFocusAllowance   → 啟用對焦驅動許可 (要先開才能驅動對焦)
  ... 控制指令 ...
0x9402 CloseApplication       → 結束, 還原一般模式
```
- **OpenApplication 會把相機切到獨佔的雲台模式**(`mgr[0x728]=3`)。此模式下正常 PTP 控制與
  USB LiveView 都被停用——雲台獨佔對焦/快門/錄影控制。這是刻意設計(雲台要在錄影中連續控焦)。
- 要先 `SetCamFocusAllowance` 開對焦許可,`ExecRelativeFocusDriving` 才會真的驅動。

## 2. 對焦控制(核心)

### 2.1 讀目前位置 — 0x9405 GetFocusPosition
- 需 **mode==2 (LiveView)**,否則回 PTP 錯誤 `0x200F`(Operation Not Possible)。
- 回傳 2 個整數:`[0]=1`(有效旗標,常數)、`[1]=目前絕對位置`。
- 這個絕對位置與相機的對焦行程 `[min,max]` 同一刻度(見 §3)。

### 2.2 相對驅動 — 0x9411 ExecRelativeFocusDriving
- 參數:一個帶符號的相對量(float / 定點,見下)。
- 韌體內部:`target = 目前位置 + round(送的值 × lens_scale / 20)`,再夾限在 `[min,max]`,然後驅動。
- **單位不是 1:1 位置**:你送的值會 `× 鏡頭相關係數 / 20` 才變成實際位置位移。
  `lens_scale` 隨鏡頭不同(執行期取自對焦物件),**首次使用建議實測標定**(見 §5)。
- 閘控較寬(`captureState[0x220] != 1`),**錄影中可用**——這是雲台系列存在的主因。

### 2.3 絕對驅動 — 0x9412 ExecAbsoluteFocusDriving
- handler 存在(C04EF1F8),吃絕對位置參數,同樣夾限 `[min,max]`。
- ⚠️ 實機驗證:**外部 GIMBAL 介面只開放相對(0x9411),不開放絕對設定**。
  若你的裝置送 0x9412 無效,請改用「讀 0x9405 目前位置 + 送 0x9411 相對」自行合成絕對定位(見 §4)。

### 2.4 AF 起停 — 0x9413 / 0x9414
- `StartAutoFocus` / `StopAutoFocus`:交給機內 AF(對比爬山)自動對焦,不需自算位移。

## 3. 對焦位置域

- 位置控制物件(singleton),定義一個**絕對位置域**:
  - `min = FUN_c02dffb0()`、`max = FUN_c02dffd0()`(基準 ± 偏移)
  - `current = FUN_c035fd48()`（= 0x9405 回傳值）
  - 三者**同一刻度**。驅動 target 超出 `[min,max]` → 回 `0x201D`。
- min/max = 對焦行程兩端點(對應 PTP 側可讀到的兩個整數)。
- ⚠️ 位置是**抽象正規化值**,不是公尺、不是原始馬達脈衝。要換算公尺需鏡頭距離表(見 `AF_COMPLETE.md`)。

## 4. 用「只能相對」做出「絕對定位」(閉迴路)

因為 0x9405 能讀絕對 current:
1. 開機讀一次 `[min,max]`(PTP GetFocusPosition/CamData)。
2. 讀 `current`(0x9405 第二個整數)。
3. 標定 scale:送已知相對值 V、量 Δcurrent → `scale = Δcurrent × 20 / V`。
4. 要到 `target`:送 `V = (target − current) × 20 / scale`;因 round+clamp,**重讀 0x9405 收斂**。
✅ 位置域可完全閉迴路。

## 5. 參數控制

- `0x9432 GetParameter` / `0x9431 ShiftParameter`:讀 / 相對位移某相機參數(光圈、ISO 等,子命令碼選參數)。
- `0x9433 SetGpsParam`:寫 GPS 資訊(給地理標記)。
- 拍照/錄影:`0x9421/0x9422`(靜態)、`0x9423/0x9424`(動態)。

## 6. 錯誤碼(PTP Response)
| 碼 | 意義 |
|---|---|
| `0x2001` | OK |
| `0x200F` | Operation Not Possible(如非 LiveView 時讀 focus) |
| `0x201D` | 位置超出 `[min,max]` |
| `0x2019` | Device Busy / 無法驅動 |

## 7. 建議工作流程(錄影中連續控焦)
```
0x9401 Open → 0x9404 SetCamFocusAllowance → 0x9423 StartMovieRecording
  loop:  0x9405 GetFocusPosition (讀 current)
         0x9411 ExecRelativeFocusDriving (送 delta)
0x9424 StopMovieRecording → 0x9402 Close
```

## 信心
- opcode↔handler 對照、focus 位置域、相對驅動公式(current+scaled_delta 後夾限)、
  0x9405 回 current、Open 進獨佔模式 —— **反編譯/反組譯確認**。
- 「外部只開放相對、不開放絕對」—— **實機驗證**。
- 各參數子命令碼的確切 byte 佈局 —— 建議 USB 側錄官方雲台流量對帳(見 `PTP_OPCODES.md §5`)。
- `lens_scale` 實際值隨鏡頭 —— 需實測標定。
