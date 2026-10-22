# SIGMA fp — PTP vendor 指令 opcode / 參數格式 / GIMBAL 流程

## 1. 已確認的 opcode(韌體帶 opcode 的字串,直接證據)

| opcode | 指令 | 備註 |
|---|---|---|
| `0x9016` | SetCamDataGrp1 | |
| `0x9017` | SetCamDataGrp2 | |
| `0x9018` | SetCamDataGrp3 | |
| `0x9024` | SetCamDataGrp4 | |
| `0x9028` | SetCamDataGrp5 | |
| `0x902A` | SetCamDataGrp6 | |
| **`0x9032`** | **SetCamDataGroupFocus** | ★ 你目前用的對焦指令,錄影中被擋 |
| `0x9034` | SetCamDataGroupMovie | |
| `0x9038` | SetCamDataGroupGps | |
| `0x9109` | SetCamAdjustmentStatus | |
| `0x9433` | SetGpsParam (= GIMBAL_SetGpsParam) | ★ 錨點:GIMBAL 群在 **0x94xx** |

（Get 系列依 SIGMA 慣例在較低 opcode;`ptp log` 內部有完整 opcode↔name 對照,但那張表用 switch
派發、名稱只作 log,靜態無法直接列出對應——見 §4。）

## 2. CamDataGroup 酬載格式(TLV,反編譯 parser 確認)

`SetCamDataGrp*` / `SetCamDataGroupFocus` 的 data phase 酬載是 **TLV 結構**
（parser `FUN_c0501350` / `FUN_c0501508`）:

```
offset 0x00  u32  ?        (parser 檢查非 0、4-byte 對齊)
offset 0x04  u32  count    entry 數
offset 0x08  entries[count]  每筆 12 (0xc) bytes: { u16 tag, ... , value }
```
讀取:`FUN_c0501508(buf, tag, dest, maxlen)` → 依 tag 找 entry、複製 value。

## 3. ★ SetCamDataGroupFocus (0x9032) 欄位(從 handler `FUN_c04f5ae8` 逐 tag 解出)

| tag | 大小 | 用途(推定) |
|---|---|---|
| 1 | 1 | FocusMode / 對焦模式旗標 |
| 2 | 1 | (焦點相關旗標;handler 比對此值變化 → 觸發旗標 0x196) |
| 3 | 1 | |
| 4 | 1 | |
| 10 (0xa) | 1 | |
| 11 (0xb) | 1 | |
| 12 (0xc) | 1 | |
| 13 (0xd) | 4 | 32-bit 值(對焦位置?) |
| 14 (0xe) | 8 | 64-bit 值 |
| 0x33 | 1 | |
| 0x34 | 1 | |
| 0x50 | 1 | |
| 0x51 | 2 | 16-bit(對焦驅動量?→ 傳給 `FUN_c04ef7d0`) |

驅動對焦時 handler 呼叫 `FUN_c04ef7d0(*(u16*)(obj+0x178))`,且**僅在 `captureState[0x220]==0
&& [0x7c]==0`（閒置）才驅動**——這就是錄影中失效的閘（見 `notes/research/autofocus/../../autofocus/notes/PTP_FOCUS.md`）。

## 4. GIMBAL 指令群(名稱已抽,opcode/參數 需外部佐證)

命令名表(seg0 `0xC0CF4D30`–`0xC0CF5050`)完整列出:
```
GIMBAL_OpenApplication      GIMBAL_CloseApplication
GIMBAL_GetParameter         GIMBAL_ShiftParameter
GIMBAL_GetCamState          GIMBAL_SetGpsParam (=0x9433)
GIMBAL_GetFocusPosition     GIMBAL_SetCamFocusAllowance
GIMBAL_ExecRelativeFocusDriving   GIMBAL_ExecAbsoluteFocusDriving
GIMBAL_StartAutoFocus       GIMBAL_StopAutoFocus
GIMBAL_StartStillCapture    GIMBAL_StopStillCapture
GIMBAL_StartMovieRecording  GIMBAL_StopMovieRecording
```

**推定的 session 流程**(依指令語意):
1. `GIMBAL_OpenApplication` — 進入雲台/外控 session
2. `GIMBAL_SetCamFocusAllowance` — 啟用對焦驅動許可
3. `GIMBAL_ExecRelativeFocusDriving` / `GIMBAL_ExecAbsoluteFocusDriving` — 驅動對焦（錄影中）
4. `GIMBAL_GetFocusPosition` — 讀回位置
5. `GIMBAL_CloseApplication` — 結束

**為什麼 opcode/參數無法純靜態給出**:命令名只作 log,實際派發是 switch(opcode 用 movw/movt 載入
比對),且各 GIMBAL 子指令的參數解析散在 switch case;handler 位址不以指標表存在(`FUN_c04ef1f8`
在整個映像零 dword 出現 → 經 computed jump 派發)。要逐一定死需**互動式 Ghidra** 追那個 switch。

## 5. ★ 最可靠的取得方式:USB 封包側錄(建議)

比逆向 switch 更快更準——**側錄一個已知能用的來源**的 USB PTP 流量:
- SIGMA 官方 tethering / Capture app,或
- 能在錄影中控焦的雲台/外控裝置(它就是用這套 GIMBAL 指令)

用 Wireshark + usbmon(Linux)或 USBPcap(Windows)抓,就能看到:
- 每個 GIMBAL 指令的**確切 PTP OperationCode(0x94xx)**
- **參數(Parameter 1..5)與 data phase 的 byte 佈局**
- **session 開關與 allowance 的實際順序**

對照本文件 §1/§3 的韌體事實驗證即可。

## 6. 立即可做的驗證(用你已會送 PTP 的工具)

1. 用 `SetCamDataGroupFocus (0x9032)` + §3 的 TLV,**待機時**送 → 應能對焦(驗證格式對)。
2. 同樣指令**錄影中**送 → 應無效(驗證 §3 的閘）。
3. 若能側錄到 GIMBAL 流量,取得真 opcode 後,錄影中送 `GIMBAL_Exec*FocusDriving` → 驗證是否繞過。

## 信心
- §1 opcode、§2 TLV 格式、§3 focus 欄位、§4 GIMBAL 名稱 + 0x94xx 群 —— **韌體確認**。
- GIMBAL 各子指令的**確切 opcode 與參數 byte 佈局** —— **未從韌體取得**(switch 派發),
  建議用 §5 側錄取得,或互動式 Ghidra 追 switch。
