# SIGMA fp — 用 PTP 傳輸 CinemaDNG 影片？調查結果

## 短答

**fp 的 PTP 是 SIGMA 自家的 vendor tethering 協定(SIGMA Capture Pro 用),不是通用 MTP 檔案瀏覽器。**
它有「靜態檔」與「影片檔」傳輸操作,但 **CinemaDNG(一資料夾的 .DNG 幀 + WAV)不符合它的「單一 movie file」傳輸模型**,找不到 CinemaDNG 專屬的 PTP 傳輸路徑。
→ **要把 CinemaDNG 透過 USB 拿出來,正解是 Mass Storage (MSC) 模式**(把 SD 卡當隨身碟,直接複製整個 CinemaDNG 資料夾)。

---

## 1. fp 的 USB 模式(韌體確認)

`XC_UsbSpec_TH.cpp`,選單 `SetUsbConnectionMode`:
| 模式 | 用途 |
|---|---|
| **MassStorage (MSC)** | SD 卡掛載成 USB 磁碟 → 直接複製檔案(**CinemaDNG 走這條**) |
| **PTP / Camera Control** | SIGMA vendor tethering 協定(遠端控制 + 拍攝傳輸) |
| UVC | 網路攝影機(YUV 視訊) |
| CDC (DEBUG) | 串列除錯 |

---

## 2. PTP 是 vendor 協定,不是標準 MTP

從命令名稱表(seg0 `0xC0CF4AB8`–`0xC0CF5050`)抽出的**完整 SIGMA vendor PTP 操作集**:

**相機控制**:`GetCamConfig / GetCamStatus / GetCamDataGrp1..6 / GetCamCaptStatus /
GetCamCanSetInfo1..5 / GetCamViewFrame / GetCamDataGroupFocus / GetCamDataGroupMovie /
SetCamDataGrp1..6 / SetCamDataGroupFocus / SetCamDataGroupMovie / SnapCommand / ResetCommand`

**Tethered 拍攝傳輸(靜態)**:`CaptureRAWImage → TransferRAWImage`(拍一張 RAW,USB 拉回)

**已錄檔案傳輸**:
- 靜態:`GetPictFileInfo / GetPartialPictFile / GetBigPartialPictFile / GetCamPictFileInfo2`
- 影片:`GetMovieFileInfo / GetPartialMovieFile`

**調校 / 工廠**:`ConfigAdjustment / LoadAdjustmentData / SaveAdjustmentData / GetCamAdjustmentStatus`
**影像庫**:`ClearImageDBSingle / ClearImageDBAll`
**GIMBAL_***:一整套雲台/外部控制(對焦驅動、拍攝、錄影起停)
**低階**:`XCGetLong / XCGetVar / XCSetLong / XCSetVar / XCExecute / ConfigAPI`
(注意:**沒有標準 MTP 的 GetObjectHandles / GetObject / SendObject / GetStorageInfo**——它不是通用檔案協定)

---

## 3. 為什麼 CinemaDNG 走不了「影片檔傳輸」

- **CinemaDNG 的實體結構**:一個資料夾裡放一序列編號 `.DNG` 幀(格式字串 `%s%04d.DNG`)+ WAV 音訊。
  **不是單一檔案。**
- **影片傳輸操作是單檔模型**:`GetMovieFileInfo` / `GetPartialMovieFile` 針對「一個 movie file」
  (fp 的 MOV / H.264 短片)。
- **有檔案格式閘控**:PTP 檔案資訊建構器 `FUN_c04f2f70` 會檢查格式碼:
  ```c
  if (fmt == 3)      ok (type A)
  else if (fmt == 5) ok (type B)
  else               s_format_error   // 其他格式一律拒絕
  ```
  只有特定格式碼能過。找不到把 CinemaDNG 資料夾當成可傳「movie file」的分支。
- **檔案清單建構**(`PlayFileListMgr` 的 profiling:Dir Open → Dir Read → MakeFileList →
  canPlayMovieFile → setFileType)是給機內播放用的;CinemaDNG 在機內被當「一個可播 clip」,
  但沒有證據顯示它被登錄成 PTP 可傳輸的 movie object。

---

## 4. 結論與可行做法

| 需求 | 可行性 | 做法 |
|---|---|---|
| **把已錄的 CinemaDNG 從卡上拉到電腦** | ✅ 正解 | **MSC 模式**:卡掛載成磁碟,複製整個 CinemaDNG 資料夾(.DNG 序列 + WAV) |
| 用 vendor PTP 傳 CinemaDNG「影片」 | ❌ 未見支援 | 影片傳輸是單檔(MOV)模型 + 格式碼閘控;CinemaDNG 是資料夾序列,不符 |
| Tethered 即時拉 RAW | ⚠️ 僅靜態 | `CaptureRAWImage/TransferRAWImage` 是**靜態 RAW** tethered 拍攝,非影片 CinemaDNG |
| 即時串流 RAW 影片 | (另條路) | 走 **HDMI RAW 輸出**(見 `notes/research/interfaces/HDMI_RAW.md` / `RECORDER_SPEC.md`),非 PTP |

**一句話**:CinemaDNG 影片的設計取檔方式就是 MSC 複製(或抽卡讀卡機);PTP 那套是拍攝控制 +
單檔(靜態/MOV)傳輸,沒有為 CinemaDNG 資料夾序列開傳輸路徑。即時 RAW 影片則走 HDMI,不走 PTP。

---

## 5. 信心與界線

- 「PTP 是 vendor 協定、操作集內容、無標準 MTP GetObject、影片傳輸有格式碼閘控」——**已由反編譯確認**。
- 「CinemaDNG 資料夾不被登錄成 PTP movie object」——**強推論**(基於單檔模型 + 格式閘控 +
  找不到 CinemaDNG 專屬分支),但 `GetMovieFileInfo` 完整處理器因 movw/movt 參照,headless 未能
  逐行反編譯到底;若要 100% 排除,需互動式 Ghidra 追 `GetMovieFileInfo` 的格式碼 3/5 對應表,
  確認裡面沒有 CinemaDNG 類型。

## 產出
- 命令名表:seg0 `0xC0CF4AB8`–`0xC0CF5050`
- `out/decomp/ptpmod.c`(302 個 PTP 模組函式)、`out/decomp/ptpxfer.c`
