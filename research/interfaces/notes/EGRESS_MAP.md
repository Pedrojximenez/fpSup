# SIGMA fp Ver.5.02 — 控制與資料出口總表（EGRESS MAP）

這份彙整整串逆向的結論：**在單一 USB-C 埠的限制下,如何把「控制」送進去、把「RAW/CinemaDNG 資料」拿出來**,
每條路的能力、缺口、代價、以及未定論的實測前提。

---

## 0. 核心結論(TL;DR)

> **fp 韌體把「影像資料」和「即時控制」設計成分走不同實體通道。單一 USB-C 給不了「完整控制 + 高頻寬資料」兩者兼得。**
> - 免改韌體的**控制**:PTP(GIMBAL,但排他)或 UART shell(繞閘,但要拆機/預錄)。
> - 免改韌體的**資料**:PTP 拉單張 DNG,或 HDMI RAW。
> - **連續 RAW 出機外**:不管走哪個 USB class,都要改韌體(沒有「RAW→USB 端點」的 pump)。

**那面反覆撞到的牆**:USB 每個 class(PTP/UVC/CDC)頻寬都夠,但**沒有任何一條有把連續 RAW framebuffer 寫進 USB 端點的韌體碼**。管子夠粗 ≠ 有東西流進管子。

---

## 1. USB-C 單埠的模式(互斥)

`XC_UsbClass` 狀態機,一次只能一個角色:

| 模式 | class | 用途 | 選單可達? |
|---|---|---|---|
| MassStorage (MSC) | `XC_MassStorage` | SD 卡當隨身碟複製檔案 | ✅ MENU |
| PTP / Camera Control | `XC_UsbPTP` | SIGMA vendor tethering(控制 + 傳輸) | ✅ MENU |
| UVC | `XC_UsbUvc` | 網路攝影機(YUY2 8-bit,~1080p) | ✅ MENU |
| CDC | `XC_UsbCom` | vendor 命令伺服器 | ❌ **DEBUG-only** |
| Host / 外接 SSD | `XC_UsbClassExtDevice` | fp 當 USB host 供電+寫 SSD(UHD 12-bit CinemaDNG 用) | — |

**UHD 12-bit CinemaDNG 綁外接 SSD 是頻寬因素**(`buffer over cnt`、`MB/s` 量測、UHS-II 偵測):~300 MB/s,SD 卡撐不住 → 物理限制,改韌體也沒用。

---

## 2. 資料出口(把 RAW/CinemaDNG 拿出來)

| 路 | 拿到什麼 | 連續? | 免改韌體? | 備註 |
|---|---|---|---|---|
| **外接 SSD(USB-C host)** | UHD 12-bit CinemaDNG | ✅ | ✅ | 但佔滿 USB-C,控制無法並存 |
| **HDMI RAW** | 12-bit Bayer(8/10/12,跟畫質設定) | ✅ | ✅ | 影像走 HDMI → USB-C 空出來給控制。**唯一能「連續 RAW + 控制」的組合** |
| **PTP `CaptureRAWImage`/`TransferRAWImage`** | **全解析度靜態 DNG**(24MP,格式碼 3=DNG) | ❌ 單張 | ✅ | 靜態拍攝管線(SnapCap_CameraOnly),連拍/縮時可,非 24fps 影片。速率未實測 |
| **MSC 複製** | 已錄的 CinemaDNG 資料夾 | 事後 | ✅ | 抽卡/掛載複製 |
| UVC | 處理過的 YUY2 8-bit ~1080p | ✅ | ✅(但非 RAW) | 要改成傳 RAW = 大改韌體 |
| **連續 UHD 12-bit RAW over USB** | — | — | ❌ **要改韌體** | 把 Bayer buffer `0x50000000` 路由到 USB 端點(UVC/bulk/CDC 皆同此需求) |

**內部 Bayer 定址**:`XC_LiveViewRawMemInterface` → `0x50000000 + index*0x100000`(11 格 ring,每格 1MB),格式 `raw_bit/raw_endian`(Little/Middle)。這是 DIY「RAW→USB」改韌體的資料源起點。
（`XC_LiveViewRawMemInterfaceSample` 是**未使用的範例死碼**;`ext_SdkDrv` 是編進韌體的原始碼,非主機可呼叫的 SDK。）

---

## 3. 控制通道(對焦/拍攝/錄影)

### 3.1 對焦指令與「錄影閘」

| 指令 | opcode | 傳輸 | 錄影中可用? | 閘門 |
|---|---|---|---|---|
| `SetCamDataGroupFocus` | **0x9032** | PTP / CDdC(MenuSet) | ❌ **被擋** | `state[0x220]==0 && state[0x7c]==0`(僅閒置) |
| `GIMBAL_ExecRelativeFocusDriving` | **0x9411** | 只在 PTP | ⭕ 閘較寬 | `state[0x220]!=1` + mode==2 + capture-state,**但需 GIMBAL session** |
| `GIMBAL_ExecAbsoluteFocusDriving` | **0x9412** | 只在 PTP | ⭕ 閘較寬(同 Relative) | 同上 |
| **shell `setfpos <pulse>`** | — | **只在 UART / AutoRun** | ✅ **繞過所有 PTP 閘** | 直接 `FUN_c0360128()->drive(pos)`,無 state/mode 檢查 |

- `state[0x220]` = 拍攝狀態,會回報給 host(GetCamStatus)。錄影時的值(是否 !=1)**未實測定論**。
- shell 對焦驅動 `setfpos → FUN_c035fe08 → FUN_c03602f8 → lens->vtable[0xa8](pos)`,**PTP 閘全在 handler 層,shell 跳過**。

### 3.2 GIMBAL 完整指令集(seg1 表 `{opcode,handler,name,aux}`,aux 共用 `0xC04EF528`=session 檢查)

| opcode | 指令 | handler |
|---|---|---|
| 0x9401 | OpenApplication | 0xC04EECC8 |
| 0x9402 | CloseApplication | 0xC04EEE50 |
| 0x9403 | GetCamState | 0xC04EEEF8 |
| 0x9404 | SetCamFocusAllowance | 0xC04EEFB0 |
| 0x9405 | GetFocusPosition | 0xC04EEF50 |
| 0x9411 | ExecRelativeFocusDriving | 0xC04EF000 |
| 0x9412 | ExecAbsoluteFocusDriving | 0xC04EF1F8 |
| 0x9413 | StartAutoFocus | 0xC04EF298 |
| 0x9414 | StopAutoFocus | 0xC04EF2C0 |
| 0x9421 | StartStillCapture | 0xC04EF2E8 |
| 0x9422 | StopStillCapture | 0xC04EF340 |
| 0x9423 | StartMovieRecording | 0xC04EF390 |
| 0x9424 | StopMovieRecording | 0xC04EF3B8 |
| 0x9431 | ShiftParameter | 0xC04EF478 |
| 0x9432 | GetParameter | 0xC04EF560 |
| 0x9433 | SetGpsParam | 0xC04EF6D8 |

- **Session 流程**:`0x9401 Open` → `0x9404 Allowance` → `0x9411/0x9412 Focus` → `0x9402 Close`。
- **Relative(0x9411)參數**:Param1 = float32 相對量(`pulses = Param1 × config[3] / 20`),Param2 必須 0。
- **回應碼**:0x2001=OK、0x2003=session 未開、0x200f=操作不可能(閘擋)、0x2019=一般失敗。

### 3.3 ★ GIMBAL session 是排他模式(實測+反編譯確認)

`OpenApplication` 設 `mgr[0x728]=3` + 一排權限旗標 + `FUN_c04ee6d8(true)`(切互斥模式)。
→ **~18 個 PTP 命令 handler 檢查 `[0x728]`,session 一開就走「被擋」分支;normal API + USB LiveView 都關**。
→ 設計給「**實體雲台 + HDMI 監看**」:影像走 HDMI(LV 管線還活著,mode==2 成立),USB 專做 GIMBAL 控制。
→ **未定論**:HDMI 接著時 GIMBAL focus 的 mode==2 閘會不會過(實測:進 session 看 HDMI 有無畫面 + 送 0x9411)。

---

## 4. Shell(繞閘的關鍵)

### 4.1 能餵進 shell 的來源

| 來源 | 免 UART? | 說明 |
|---|---|---|
| **UART 序列** | ❌ | 主互動入口(開機「Hit enter」,baud 預設 115200,可到 2Mbps) |
| **AutoRun.txt** | ✅ | SD 卡腳本,插卡自動跑。**唯一免拆機路**,但**預錄非即時** + 需 AutoRun 啟用 |
| `ctrl mediaIn \file` | — | 要先有 shell |

**排除的假橋**:`XCExecute`(PTP 0x9205,= 通用變數/callback RPC,非 shell)、CDC(vendor 命令,非文字 shell)、`ShellAppSyncRequestListener`(只 log)。
→ **文字 shell 沒有任何互動式 USB 路徑。**

### 4.2 Shell 能力(繞閘後能控什麼,25+ 指令表,見 `HIDDEN_FEATURES.md` / `out/shell_cmdtables.txt`)

- **鏡頭**:`setfpos`(對焦絕對脈衝)、`setav`(光圈)、`fc/getfpos`(讀)、`emulate`(鏡頭模擬)
- **拍攝/錄影**:錄影鍵一次完整按壓是 `key MOVON` → `key MOVOFF`；第一次
  完整按壓開始、第二次完整按壓停止。`MOVOFF` 只是 key-up，不能單獨當成
  stop。另有 `key s1/s2`(快門)、`startAF/capture`。
- **時序**:`ctrl sleep <ms>`(→ 可做預錄 rack focus)
- **HDMI**:`hdmi_edid`(偽造)、`colorbar`、`get_out`、`capture`
- **感光元件**:`createraw`、`still_raw_dump`、`exe_agc/awb/shading`(重跑校正)
- **校正資料**:`readcam/writecam`(⚠️ 改校正,誤用變磚)
- **NAND**:`ts nand`(載入)
- **讀 ADC/轉盤**:`XC_ShellCmdAdcReader`(但只印值,shell 無變數/條件)

### 4.3 AutoRun 互動性的天花板

- **預錄序列(rack focus/縮時)**:✅ 完整 MOV 按壓開始 → `setfpos` / `ctrl sleep`
  → 第二次完整 MOV 按壓停止，可用遞迴 `ctrl mediaIn` 做迴圈。兩次完整按壓都
  是 `key MOVON` → `key MOVOFF`，不能把第一次 ON 與最後一次 OFF 誤當成
  start/stop 配對。
- **即時閉迴路(讀轉盤→驅焦)**:❌ shell CLI **無 if/無變數**;`adc` 讀值只印出。
- **AutoRun 跑 Lua 做閉迴路**:❌ 無 shell→Lua 執行橋;且 Lua 綁定**只有 `:v()` 讀取,無驅動對焦的 action 綁定**;Lua 被沙盒化。
- → 真互動只剩 **UART** 或 **改韌體**。

---

## 5. 決策表(依需求選路)

| 你要 | 免改韌體的路 | 代價 |
|---|---|---|
| UHD 12-bit CinemaDNG **機內錄** + 預錄 rack focus | 外接 SSD(USB-C)+ **AutoRun.txt** 焦點序列 | 需 AutoRun 啟用;預錄非即時 |
| UHD 12-bit RAW **影片** + **即時控制** | **HDMI RAW(資料)+ USB-C PTP(控制)** | 需 HDMI 錄影機;非機內錄 |
| 錄影中**即時互動控焦** | **UART** shell `setfpos` | 拆機接 UART(電壓/焊接風險) |
| 錄影中控焦(排他 OK) | **GIMBAL**(PTP)+ HDMI 監看 | USB LV/normal API 關 |
| 拉**靜態/連拍 RAW** 到 PC | PTP `CaptureRAWImage`/`TransferRAWImage` | 寫 host 端程式;非影片 |
| 連續 **Bayer/CinemaDNG 串流**出機外 | ❌ 無 | **改韌體**(RAW→USB pump)或 HDMI |

---

## 6. 未定論的實測前提(make-or-break)

1. **AutoRun.txt 在量產機是否啟用**（`XC_ShellScriptAutoRun` 觀察者是否註冊）—— 靜態無法定論。
   **第一步實測**:放無害 `AutoRun.txt`，以兩次完整 MOV 按壓錄一小段
   （每次都是 `key MOVON` 後接 `key MOVOFF`）再看是否執行。
2. **`state[0x220]` 錄影時是否 !=1** —— 決定 GIMBAL focus 錄影中通不通。實測:`GetCamStatus` 待機/錄影各讀一次比對。
3. **HDMI 監看時 GIMBAL focus 是否過 mode==2 閘** —— 進 session + HDMI + 送 0x9411 看焦動不動。
4. **PTP 拉單張 DNG 的實際連拉速率** —— 送 CaptureRAW→GetCaptStatus→TransferRAW 計時。
5. **UART 焊點位置 + 電壓(1.8V/3.3V)** —— 需拆機/社群參考;電壓接錯會燒。
6. **CDC 是否需先有 shell 才能進** —— `usb cdc` 是 shell 指令,AutoRun 可跑但 CDC 對目標無加分(=PTP 子集,無 GIMBAL、無 raw)。

---

## 7. 相關文件
- `notes/research/firmware/../../firmware/notes/FORMAT.md` — 韌體容器格式/解壓/校驗
- `notes/research/rtos/../../rtos/notes/SUBSYSTEMS.md` — 子系統(L-mount/AF/影像/Fwup)
- `notes/research/interfaces/HDMI_RAW.md` / `notes/projects/hdmi-recorder/../../../projects/hdmi-recorder/notes/RECORDER_SPEC.md` — HDMI RAW transport + 自製錄影機規格
- `notes/research/interfaces/PTP_CINEMADNG.md` / `notes/research/autofocus/../../autofocus/notes/PTP_FOCUS.md` / `notes/research/interfaces/PTP_OPCODES.md` — PTP 傳輸/對焦/opcode
- `notes/research/firmware/../../firmware/notes/HIDDEN_FEATURES.md` — debug shell / 隱藏功能 / 進入管道
- `notes/research/other/../../other/notes/GHIDRA_GIMBAL_CHECKLIST.md` — 互動式 Ghidra 追 opcode 步驟
- `notes/research/firmware/../../firmware/notes/SECURITY.md` — 韌體完整性/簽章分析(無密碼學簽章)
