# SIGMA fp Ver.5.02 — 韌體隱藏 / 未公開功能調查

從 Ver.5.02 主韌體反推。以下功能在**量產韌體中確實存在**(字串、指令表、處理函式都在),
但多數需要特定進入管道(串列埠 / SD 卡腳本 / 工廠碼)才能觸發。

> 誠實界線:「存在於韌體」= 確認;「實際能不能在你手上的機器觸發」取決於進入管道是否被
> 硬體閘控(見 §1),部分需拆機接測試點或特定金鑰,我無法從韌體 100% 斷定量產機的閘控狀態。

---

## 1. 進入管道(怎麼觸發這些隱藏功能)

### 1.1 UART 串列除錯主控台 ★
- 開機時有 baud 協商:`Hit enter key within %d seconds (After timeout, baudrate will be %d)`
  → 開機數秒內從串列送 Enter 就進入 shell(經典除錯主控台入口)
- 指令:`uart <baudrate>` / `uart def` / `uart force <baudrate>` / `uart info`
- 相關:`InitSerial` / `ReInitSerial` / `4W serial`(4 線式串列)/ `Change to the shellmode`
- 實體位置:應在機身內部測試點(TX/RX/GND),需拆機;確切腳位需硬體確認

### 1.2 AutoRun.txt(SD 卡腳本自動執行)★★ —— 訂閱鏈追蹤結果
機制(已由反編譯確認):
- `XC_ShellScriptAutoRun` 是 **`XC_Observer<const XC_MediaUpdateInfo &>`**——訂閱媒體(SD 卡)
  事件的觀察者,與 `XC_MediaDeviceCheckerObserver`(核心系統觀察者)是**同一個 subject
  `XC_Subject<const XC_MediaUpdateInfo &, 6U>` 的 peer**。
- 觸發回呼 `update()` (v1 @ `0xC03DA3F8`):
  ```c
  if ((info[3] & info[0]) != 0) FUN_c03DA758("\AutoRun.txt", 1);  // 執行腳本
  ```
  `info[]` = `XC_MediaUpdateInfo`;由 DeviceChecker::update 對照可知 `info[4]`=裝置在位旗標、
  `info[0/1/3]`=狀態/類型位元遮罩。**執行回呼內無 factory/debug/shellmode 閘控**——確定。
- `ctrl keyIn 3 10 1 0 ctrl mediaIn \autorun.txt` 是**注入媒體事件**的測試指令(ctrl 指令表),
  證明此執行路徑可用。

★ **未解(靜態分析的邊界,誠實記錄)**:AutoRun 觀察者「是否在量產開機被建構並訂閱到 subject」
無法用 headless 靜態分析定論。三種方法(raw-dword 掃描 / movw-movt 追蹤 / Ghidra 參照庫)
對 AutoRun 都回 0,**但對已知活躍的觀察者(StorageMgr / DeviceChecker / DeviceExt)也全回 0**
——因為 IAR 的 vptr 設定走 ADR/共用建構子傳參,這批方法一致失效。故「找不到建構點」不是
「未訂閱」的證據,只是工具限制。要定論只剩兩條路:
  1. **互動式 Ghidra GUI**:對 `XC_Subject<XC_MediaUpdateInfo,6U>` 的 addObserver 下中斷/追
     XREF,或用 decompiler 手動跟 shell init(xc_shell.cpp)的建構鏈與 ADR。
  2. **實機測試**(最快):放**無害**的 `\AutoRun.txt`(只跑 `log`/顯示類,絕不碰
     `writecam`/`format`/`ts nand`)到卡根目錄,插卡觀察是否有反應。

### 1.3 工廠 / 廠商測試模式
- `VendorTestMode`、`CAM_FACTORY_CODE_ADDR`、`CAM_INSPECT_STATUS_ADDR`、`FACTORY CODE = %d`
- `MenuItemFactory` / `MenuSelectorFactory` / `XC_MenuSelectorFactoryInterface`
  → 選單系統內有一整套**工廠選單**(正常 UI 不顯示,由 factory code / inspect status 閘控)
- `factory reset (for debug)`、`FactorySettingResetReq`

---

## 2. Debug shell 指令全集(25+ 指令表,依模組)

完整清單見 `out/shell_cmdtables.txt`。重點模組:

### 2.1 imager(感光元件)—— 40 指令 @ `0xC0BB7694` ★
工廠**感光元件校正套件**:
`createraw, testpattern, mode_check, adj_init, adj_data_dump, view_adj,`
`exe_agc, exe_awb, exe_wdd, exe_bdd, exe_shading, exe_acquired_shading, exe_shadingcheck,`
`exe_sort, defect_collect_off/check, exe_lvds, fixed_shutter, fixed_gain, zero_cut_raw`
→ 可重跑 AGC/白平衡/白點/黑點/遮光校正、缺陷像素偵測、產生測試圖樣。**能改寫感光元件校正**。

### 2.2 lens(鏡頭)—— 25 指令 @ `0xC0BB9734` ★
`sh, init, fc(對焦), ir(光圈), setav/getav, setfpos/getfpos, cnvav, dof(景深),`
`fwup(鏡頭韌體更新), emulate(鏡頭模擬), read, tr, mc(卡口轉接), ver`
→ **`emulate`= 鏡頭模擬**(無鏡頭時模擬鏡頭行為);可直接驅動對焦/光圈、讀寫鏡頭。

### 2.3 display / monitor —— 24 指令 @ `0xC0BB1410` ★
`monitor, hdmi, hdmi_onoff, hdmi_mask, hdmi_mask_str, hdmi_edid, colorbar, lcd, lcdTune,`
`zoom, osd, osdPalette, osdfile, image, text, faceframe, focusarea, peaking, capture, get_out`
→ **`hdmi_edid`= 覆寫/偽造 EDID**、`hdmi_mask`= HDMI 遮罩、`colorbar`= 輸出色條測試訊號、
`get_out`/`capture`= 抓輸出畫面。對你的 HDMI RAW 錄影機專案很有用(可強制輸出模式)。

### 2.4 capture / AF / play —— 29 指令 @ `0xC0BC3F34`
`startAF, stopAF, AFON/AFOFF, capture, captureLv, startUVC/stopUVC, rawPlay, play*,`
`ptpget/ptpClr, setPWB, dbinfo, lvinfo, view_capa`
→ 腳本化拍攝、**UVC 測試模式**、RAW 播放、PTP 控制。

### 2.5 AF measure —— 19 指令 @ `0xC0918864`
`offset, moffset, peak, pline, safarea, disparea, safoffset, cafdmp, cafwob, pddef, adjoffset`
→ AF 微調、PDAF 失焦資料傾印、AF 校正偏移。

### 2.6 校正資料讀寫 —— 11 指令 @ `0xC0BC9938` ⚠️
`read, get, set, write, load, save, readcom, readcam, writecam`
→ **`readcam`/`writecam`= 讀寫相機校正資料**(NAND `CAMADJ`)。誤用會破壞出廠校正。

### 2.7 其他模組
| 表位址 | 模組 | 重點指令 |
|---|---|---|
| `0xC0BC3570` | ctrl / 測試框架 | `mediaOut, keyIn, save_log, timmem, t_assert`(自動化測試腳本原語) |
| `0xC0BC2660` | SD 卡 | `slot, test_rw, format, mnt, umnt, sdmode`(低階卡片存取/格式化) |
| `0xC0918F5C` | I2C/SPI 時脈 | `f_60KHZ … f_15MHZ`(匯流排頻率測試) |
| `0xC0CEEE5C` | 白平衡 | `set_wb_01 … set_wb_12`(12 組 WB 預設) |
| `0xC0BB0104` | 偵測 | 臉/眼偵測、追蹤除錯 |
| `0xC0BAFE48` | 人臉辨識 | `face_r_enable, face_r_a…d`(**註冊人臉辨識**,fp UI 未公開) |
| `0xC0BB2270` | 閃燈 | `manual_flash, flash, test`(手動觸發閃燈) |
| `0xC0BAE598` | 音訊 | `mic, rec, codec, dngpb` |
| `0xC0BBA5CC` | 記憶體除錯 | `heapmem, memmap, memtbl, poolchk`(堆積/記憶池傾印) |
| `0xC0BC51F8` | RTC | `utc_offset, summer_time, tickm`(時鐘調整) |
| `0xC0BB046C` | 按鍵模擬 | `s1, s2, push, press`(模擬快門/按鍵) |
| `0xC0BB24CC` | 檔案 | `del, delall, delCinemaDng, rename`(直接刪檔) |

---

## 3. 值得注意的隱藏「相機功能」(非純除錯)

- **人臉辨識 (face recognition)**：`face_r_enable / face_r_a…d`、`FaceAndEyeDetectionFunc.cpp`、
  `AAT_MID`。fp 的公開規格只有臉/眼「偵測」對焦;韌體裡有「註冊特定人臉辨識」的殘留機制。
- **鏡頭模擬 `emulate`**：可在無鏡頭下模擬鏡頭,方便台架測試。
- **NAND 直接載入 `ts nand`**：`ts nand SUBCPU1 0x90000000 0x98000000 … `——把 NAND 分割區直接
  載入 RAM 執行(副處理器韌體注入的管道)。
- **HDMI EDID 偽造 / 色條輸出**：`hdmi_edid`、`colorbar`——可強制 HDMI 輸出時序與內容。
- **任務/記憶體剖析器**：`analyzer tskmon_start …`、`heapmem`、`acc_log`——完整的執行期剖析。
- **多語系/區域**：無明顯區域鎖字串(未見 region lock),但有語系資源。

---

## 4. 安全 / 風險備註

- 這些多為**原廠工廠/維修/研發用**的除錯介面,不是消費者功能。
- **高風險指令**:`writecam`(改校正)、`exe_*`(重跑校正)、`format`/`del*`(毀資料)、
  `ts nand`/`writecam`(改 NAND)——誤用可導致校正跑掉或變磚。
- **對你有用的低風險項**:`hdmi_edid`/`colorbar`/`get_out`(HDMI 錄影機開發)、
  `rawPlay`/`createraw`(RAW 管線研究)、AutoRun.txt(自動化)。
- 進入管道(串列腳位、AutoRun 閘控)需**實機確認**;韌體證明功能存在,但不保證量產機未加鎖。

---

## 5. 產出檔案
- `out/shell_cmdtables.txt` — 25 個指令表完整列舉
- `out/decomp/autorun.c` / `autorun2.c` — AutoRun.txt 執行路徑
- `out/decomp/shell/shell.c` — shell 核心函式(KeyCheck / MediaHolder / ScriptAutoRun)
