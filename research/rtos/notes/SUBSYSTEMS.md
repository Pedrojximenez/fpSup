# SIGMA fp Ver.5.02 — 子系統分析

分析基礎：Ghidra 12.1.2 專案 `ghidra_proj/SIGMAfp`，主映像載入於 0xC0000000。
共 **47,156 個函式**，其中 **15,475 個已具名**（14,843 來自 vtable、632 來自 `__func__` 字串）。
反編譯輸出在 `out/decomp/`。

---

## 0. 平台

| 項目 | 值 |
|---|---|
| ASIC | **XZ01**（`XZ01ES1.0`，`@VRIXZ01`；原始碼路徑亦見 `SIG_GHS_XZ01`） |
| 板級代號 | **w71c1**（大量 `*_w71c1.cpp` 機種分支） |
| 主 CPU | ARMv7‑A + VFP/NEON，映像基址 0xC0000000 |
| 副處理器 | ARM926 ×2（NAND 分割區 `ARM926_1` / `ARM926_2` / `ARM9`） |
| 開機 | **PureNAND IPL xz01-v0.7.r255715 (Misato) [DEBUG BUILD] (Jun 19 2019)** |
| 儲存 | NAND（`src/hal/PromDriver/src/nand/XC_PromDriverNand.cpp`），媒體 FAT16/FAT32/exFAT |
| 腳本 | 內嵌 **Lua 5.3** |
| 編譯器 | IAR |

NAND 分割區名稱（IPL 內字串表 @IPL+0x11690）：
`*UNKNOWN ID*`, `IPL`, `PART_TBL`, `BOOT`, `FIRM`, `CAMDEF`, `CAMADJ`, `USER`,
`DEBUG`, `ARM926_1`, `ARM926_2`, `ARM9`, `FIRM2`, `FIRM_SLAVE`,
`DATA0`, `DATA1`, `DATA2`, `DATA3`, `STORAGE`

---

## 1. 韌體更新（Fwup）

### 1.1 標頭解析器 — `analyze_firmware_bin_head_main` @ `0xC04CED60`

解析每段前面的 ASCII 標頭，以空白 / `\n\r`（`" \n\r"` @ `0xC0CF173C`）分隔 token，
比對一張 7 筆的 key 表 @ `0xC0CF1704`，格式 `{u32 type, char* key}`：

| type | key | 我們的 5.02 檔案是否使用 |
|---|---|---|
| 0 | `LENGTH=` | ✔ |
| 2 | `LOADADDRESS=` | ✘（解析器支援，此版未用） |
| 3 | `OFFSET=` | ✘ |
| 4 | `VER=` | ✔ |
| 5 | `DVR=` | ✔ |
| 6 | `SUM=` | ✔ |
| 7 | `PID=` | ✘ |

解析結果寫入 context：`+0x240` = LENGTH，`+0x248` = OFFSET，`+0x200` = 名稱字串區。
回傳值 = `param_2 + 0x100`（跳過 0x100 標頭），亦即「下一段的位移」——與我們拆出的
容器佈局完全一致。

### 1.2 驗證強度

目前所見的完整性檢查只有 **`SUM=` 的 byte 累加和**（見 `notes/research/firmware/../../firmware/notes/FORMAT.md` §1，四段全部
以此驗證通過）。在主韌體反編譯範圍內**沒有發現 RSA / ECDSA / HMAC 或任何雜湊簽章驗證**。

⚠️ 這是「目前為止未發現」，不是「確定不存在」——真正的授權/簽章檢查若存在，最可能位於
**IPL**（131 KB bootloader），而 IPL 尚未完成分析（見 §5）。要下定論必須先把 IPL 做完。

其他相關：
- `CAM_DOWNLOAD_FIRMWARE_ADDR`、`CAM_FLASH_MODE_ADDR` — 更新用的暫存位址常數
- `src/library/Fwup/src/XC_Fwup.cpp` / `XC_FwupCore.cpp` / `XC_FwupMedia.cpp`
- `XC_FwupMediaCore` → `XC_FwupMediaCorePureNand`（寫入端）
- `FirmwareImplBase` → `FirmwareImplCamera` / `FirmwareImplExtEvf` / `FirmwareImplLens`
  （三種更新目標：機身、外接 EVF、鏡頭）
- 錯誤字串：`Flash Write Error!!(%-17s:%3d)[ code = %d ]`、`check sum error : %d->%d`、
  `Fwup Error %d`、`Fwup Finish`

---

## 2. L-mount 鏡頭協定

`src/hal/Lens/src/LensLmount/`（25 個原始檔）。傳輸層為 SPI（`LmountSpi.cpp`）。

### 2.1 指令集（全部已具名並反編譯，見 `out/decomp/lmount/lmount.c`）

| 指令 | 位址 | 說明 |
|---|---|---|
| `CmdInit` / `cmdInitMain` | `0xC0357010` | 初始化握手，最多 16 次重試，每次間隔 50 ms |
| `CmdStatus` | `0xC03559C0` | 讀狀態，回傳兩個 16-bit 值 |
| `CmdRead` / `cmdReadMain` | `0xC0355BE0` / `0xC0357188` | 讀鏡頭記憶體 |
| `CmdWrite` / `cmdWriteMain` | — / `0xC03573D0` | 寫鏡頭記憶體 |
| `CmdWriteVerify` | — | 寫後回讀比對 |
| `CmdFocus` | — | 對焦驅動（`CmdFocus(%d %ld %d %s)`） |
| `CmdAperture` / `CmdMcAperture` | — | 光圈（`Mc` = 卡口轉接器 Mount Converter） |
| `CmdMcBundle` / `cmdMcBundleMain` | — | 轉接器批次指令 |
| `CmdStandby` / `CmdMcStandby` | — | 待機 |
| `CmdAdvLcEnable` / `CmdAdvLcExit` | — | Advanced Lens Communication 模式 |
| `CmdEnd` | — | 結束 |
| `CmdUpdateFw` | — | 鏡頭韌體更新 |

輔助：`PreCommunicationSequence()`、`recoverySequence()`、`judge_cmd_init_status()`。

### 2.2 傳輸細節（自 `CmdRead` / `cmdReadMain` 反編譯讀出）

- 單次交易上限 **0xFF bytes**；`CmdRead` 自動把長度切成 0xFF 的區塊迭代
- 總長度上限 **0xA000 (40 KB)**，超過會觸發 assert（`LmountSpi.cpp:0x140`）
- 接收緩衝：payload 在 `+0x10`；`CmdStatus` 的兩個回傳值在 `+0x0B/+0x0C` 與 `+0x0D/+0x0E`，
  **高位元組在低位址 → 線上是 big-endian**
- 狀態暫存器位元：`0x001` = init 完成、`0x400` = write busy、`0x800` = read data ready
- 重試策略：init 16 次、write 16 次、**read 2500 次**；read 超時會判定
  「detect old lens-fw try cmd_init」並重跑 `CmdInit`（舊鏡頭韌體相容路徑）
- 逾時常數 `LENS_FWUP_TIMEOUT`；讀等待 1000 ms、寫等待 4000 ms

### 2.3 鏡頭資料

log 格式字串揭露的欄位：
```
lmount spec ver: %d.%d.%d
Lmount SpecVer Body %d.%02d Lens %d.%02d
lens id: 0x%04x          lens serial: %d
lens fw ver: %d-%d-%d-%d lens fw ver(hex): 0x%08X
lens sys ver: %d.%02d
```

### 2.4 鏡頭韌體更新（`LmountFwUp.cpp`）

`bool LmountFwUp::readFile(unsigned char*, unsigned int, unsigned int)`
檔名 `lensfirm.bin`，索引表每筆記錄：
```
index %2d file_type %d lens_type 0x%04X ver %d.%d offset %d length %d crc32 0x%08X
```
以 **CRC32** 驗證（`%s() invalid crc32 0x%08X(calc) 0x%08X(hdr)`），
建表函式 `MakeLensFwUpInfo`。寫入用 `CmdWriteVerify`（`%s() verify err addr=0x%08X size=%3d`）。

### 2.5 光學校正

`src/library/CameraController/OpticalCorrection/src/LmountTH/`：
`OpticalCorrection_LmountCommon` / `_LmountL` / `_LmountMc`，
含 `LmountL_THShading_w71c1.cpp`、`LmountL_THDistortion.cpp`（周邊失光 / 畸變），
以及 `LmountMcDataMtf.cpp`（MTF 資料）。

---

## 3. 自動對焦

`src/library/CameraController/AfMgr/`，反編譯 498 個函式於 `out/decomp/af/af.c`。

### 3.1 類別架構

```
AfMgrProcessBase
├── AfMgrProcessFast          快速
├── AfMgrProcessSlow          慢速
├── AfMgrProcessNear          近距
│   └── AfMgrProcessHybrid    混合（PDAF + 對比）
├── AfMgrProcessRocking       擺動搜尋
└── AfMgrProcessContShooting  連拍

AfMgrModelBase ├ AfMgrModelSingleBase ├ AfMgrModelSingleOem_Sig
               └ AfMgrModelContinuousBase ├ AfMgrModelContinuousOem_Sig
AfMgrDriveBase ├ AfMgrDriveScan  └ AfMgrDriveIntermittent
AfMgrOffsetBase ├ AfMgrOffsetSaf_w71c1  └ AfMgrOffsetCaf_w71c1
AfMgrLensBase → AfMgrLensOem_Sig
AfMgrAreaBase → AfMgrAreaOem_TH
```

### 3.2 相位差偵測（PDAF）

`AfMgrPhaseDetection.cpp`、`AfMgrMeasurePdafDefocus.cpp`、`LmountPdaf.cpp`（@`0xC0353ACC`）。

- 已具名函式：`isExecOnPdafData`、`CafMode5_CheckPdaf`、`defocusImpl`、`LmountPdaf_update`
- PDAF 幾何參數 log：
  `PDAF size=%u, %u, line=(%u, %u), (%u, %u), interval=%u, sensor=%u`
- 有「無法使用相位差的感光元件模式」判斷（`sensor modes that cannot use phase detection.`）
- 失焦量換算表：`[Defocus Per Pls]`、`[Scale Defocus Per Pls]`、`[Pdaf Cor]`，
  每支鏡頭有 `DefocusPerPulse` 與 `PDAF Cor` 係數（thin/max/min/ave/now 五組統計）
- 失敗時回退：`###### not drive pdaf . do near af!!!!!`（改走 `AfMgrProcessNear`）

### 3.3 偵測

`DetectionMgr`（含 `AAT_MID` 子模組）、`AatInterfaceBase` →
`AatInterfaceColorTracking` / `AatInterfaceHistTracking`（色彩追蹤 / 直方圖追蹤）。

---

## 4. 影像管線 / 畫質

反編譯 336 個函式於 `out/decomp/imaging/imaging.c`。

### 4.1 SIGPRO（訊號處理）操作

`XC_SigproRawMix`、`XC_SigproRawMakePreview`、`XC_SigproJpegComp`、`XC_SigproJpegDecomp`、
`XC_SigproMBlender`、`XC_SigproFillLight` / `XC_SigproFillLightMgr`

硬體區塊名稱（暫存器/路徑字串）：
`SIG0 BAYER_NR`、`SIG1 3DDNR`、`GAM_TOP SBUS GAMMA`、`MAT_TOP IGAMMA`、
`CRCT_TOP`、`CRCT_3A`、`crct1_win_a0/a7`（校正視窗），
子操作 `CrctGainToBufA`、`CrctCrmfToBufA`、`CrctHbinToBufA`、`CrctVbinToBufA`、
`CrctHbin2ToBufA`、`CrctSpcToBufA`、`CrctRwzmToBufA`

⚠ 這是清單不是結構。前六個是 **a0/a7 校正視窗的六選一**,`CrctRwzmToBufA` 掛在
**另一個緩衝 bufa1**,只有開關 —— 兩邊可以同時作用。結構與 enum 見
`../../imaging-hw/notes/CRCT_REDUCTION_PATHS.md`。

### 4.2 影像請求（輸出樣式）

```
XC_ImageRequestOutputStyle
├── XC_ImageRequestOutputStyleMulti      → _w71c1
├── XC_ImageRequestOutputStyleMultiEdge
├── XC_ImageRequestOutputStyleDetail     → _w71c1
├── XC_ImageRequestOutputStyleDngDevelop → _w71c1
└── XC_ImageRequestOutputStyleCinemagraph→ _w71c1
XC_ImageRequestSrcMakerFile → _w71c1
XC_ImageRequestDrawerCore   → _W71c1
XC_ImageRequestPlayHistogram→ _w71c1
```

模式常數：`MOVIE_REC_DNG`、`PLAY_DNG_DEV`、`PLAY_CINEMA_DNG`、`PLAY_CINEMA_DNG_ONE`。
DNG 私有資料：`XC_DngPrivateData`。

### 4.3 感光元件校正

`src/library/CameraController/SensorAdjustment/`：
`SensorAdjustment.cpp`、`...Agc.cpp`、`...Awb.cpp`、`...Bdd.cpp`、
`...Defectsort.cpp`、`...Shading.cpp`、`...ShadingCsCheck.cpp`、`...Wdd.cpp`
（AGC / 白平衡 / 黑點缺陷 / 缺陷排序 / 遮光 / 白點缺陷）。

校正資料存於 NAND `CAMADJ` 分割區，經 `XC_AdjustDataMgrCore<T>` 存取，
型別包含 `XC_AdjustDataSensor`、`XC_AdjustDataLens`、`XC_AdjustDataBodyIMU`。
`CAM_CCD_DEFECT_DETECT` / `CAM_CCD_DEFECT_BLACK` 為缺陷像素表。

顯示端 gamma 表：`PARAM_LCD{R,G,B}GAMMA_1..4`、`PARAM_EVF{R,G,B}GAMMA_1..4`。

---

## 5. IPL（bootloader）

`out/IPL.raw`，131,072 bytes，**未壓縮**，位於容器 0x175E600。

- 版本：`PureNAND IPL xz01-v0.7.r255715 (Misato) [DEBUG BUILD] (Jun 19 2019 15:29:49)`
- **載入基址 = 0x00000000**（已確認）：向量表在 0x0，例外處理器在絕對位址 0xB8–0xE8；
  8 個常數池值落在 [0, 0x20000) 內、其他候選基址皆 0。ARMv7（用 movw/movt 建位址）。
- 開機流程（`Reset`@0x0 → handler@0xB8）：`bl 0x120`（初始化）→ 設 SYS 模式 →
  `bl 0x1C0`、`bl 0x260`、`bl 0x264` → `bl 0x40`。MMIO 在 **0x30080000**（`hardimp_reg_set`
  的 `movw r8,#0; movt r8,#0x3008; str …`）。
- 呼叫 SoC **mask ROM**：透過 thunk 呼叫固定位址 **0x2E000428**（XZ01 boot ROM 的低階 API，
  不在本韌體檔內）。
- DRAM 初始化 log：`# of DRAMs: %d`、`# of CS: %d`、`DRAM Size: %d MiB`、`DRAM Clock: %d KHz`。
- 載入器：`firmware_load_firminfo`、`flash_read`、`loading [%08lx:%10s] ......`、
  `0x%08lx bytes in%8d usec.%7d KB/s`，讀 NAND 分割區並搬到 DRAM。
- 完整性檢查字串僅：`invalid partition table. (error code: %d)`、`Invalid Firmware?`、
  `Instead, I'll load BOOT for you.`（FIRM 無效時回退載入 BOOT）、`load error`、
  `Warning: IPL can not identify this ASIC.`。NAND ECC = `BCH2K124`（BCH，2K page，124-bit）。
- 搬移目標：FIRM 最終被載到高位址區（DFI/PTBL 列出 0xFFF10000 / 0xFFF20000 / 0xFFFE0000）後跳入執行。

Ghidra headless 對此 bootloader 的函式/xref 還原不足（movw/movt 參照未自動解析，
函式辨識 247–663 不等），要逐指令跟完「載入→搬移→跳轉」需要**互動式** Ghidra。
但這不影響安全結論——見 `notes/research/firmware/../../firmware/notes/SECURITY.md`。

### ★ 安全結論（詳見 `notes/research/firmware/../../firmware/notes/SECURITY.md`）

**整個韌體找不到任何密碼學簽章或雜湊（SHA/MD5/AES 常數表全數 NOT FOUND）。**
完整性保護只有容器的 byte-sum（`SUM=`）、鏡頭韌體的 CRC32、NAND 的 BCH ECC——
全部可重算，無一為密碼學簽章。信心程度高。

---

## 6. Debug shell

`src/shell/src/cmd/` — 韌體內建互動式命令列，指令包含：

- `Fwup \firmname.bin` — 直接觸發韌體更新
- `dir` / `mkdir` — 檔案系統瀏覽
- `ts nand SUBCPU1 0x90000000 0x98000000 0x4000 0x6000 0x0` — NAND→RAM 載入
  （參數：`(part id (str)) (dst) (work) (comp size) (original size) (offset)`）
- `setting load` / `setting save` — 參數存取 FlashValue
- `CameraSetting read` / `write`
- `ae fix shutter …`、`af msr peak …`、`af_eval`、`single_af`、`predict` 等 AF/AE 調校
- `analyzer tskmon_start 100000 1000 1000000 100 2000 \DBG_TASK.txt` — 任務監控
- `dbg_out crct_path` — 影像校正路徑傾印

尚未確認此 shell 在量產韌體中的啟用條件與存取管道（UART？USB？），值得追。

---

## 7. 產出檔案

| 檔案 | 內容 |
|---|---|
| `out/seg0_c0000000.bin` | 主映像 49,245,696 bytes @ 0xC0000000 |
| `out/seg1_c2ef6e00.bin` | 第二段 236,032 bytes @ 0xC2EF6E00 |
| `out/IPL.raw` / `PTBL.raw` / `DAT1.raw` | 其餘三段原始資料 |
| `out/rtti_classes.txt` / `.json` | 2,462 個類別 + 繼承關係 |
| `out/vtables.txt` | 2,416 張 vtable、49,606 slot |
| `out/symbols_vfunc.tsv` | 14,843 個虛擬函式位址→名稱 |
| `out/source_files.txt` | 394 個原始碼路徑 |
| `out/pretty_functions.txt` | 12 個完整 C++ 簽章 |
| `out/decomp/{lmount,fwup,af,imaging}/*.c` | 1,333 個反編譯函式 |
| `out/decomp/fwup_verify.c` | 韌體標頭解析器 |
| `ghidra_proj/` | Ghidra 專案（含 seg0 與 IPL 兩個 program） |

### 開啟 Ghidra GUI

```sh
cd /Users/dido/Developer/SIGMAfp_re
JAVA_HOME=$PWD/tools/jdk/Contents/Home \
  tools/ghidra/ghidra_12.1.2_PUBLIC/ghidraRun
# 開啟專案 ghidra_proj/SIGMAfp
```
