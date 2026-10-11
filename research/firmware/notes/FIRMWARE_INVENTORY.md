# SIGMA fp Ver.5.02 — 韌體完整清單 / 全量反編譯存底

這份是「完整反編譯整個韌體」那輪的成果與新發現彙整。

## 1. 全量反編譯產出

- **`out/decomp/full/blk_000.c` … `blk_XXX.c`(18 檔,依位址 1MB 分塊)**
  = seg0 主映像**全部 47,156 個函式**的反編譯(47,154 成功,2 失敗)。
- 命名狀態:15,475 個具名(14,843 來自 vtable RTTI + 632 來自 `__func__` 字串),其餘 `FUN_xxxx`。
- 要查任何函式:算出位址落在哪個 1MB bucket(位址 >>20 & 0xFFF)→ 開對應 `blk_XXX.c`。

## 2. ★ 重要發現:fp 與 fp L 共用同一份韌體

這份「fp Ver.5.02」韌體**同時內含兩顆感光元件的完整驅動與設定**:
- **IMX410**(SIGMA fp,24MP,6000×4000)
- **IMX455**(SIGMA fp L,61MP,9520×6328)

字串證據:`SIGMA fp L`、`XC_ImageSensorIMX410/455`、`font_menu_LB_fileName_model__fpl`、
影像尺寸 `9520x6328(60M)` / `6000x4000(24M)`。
→ 這解釋了為什麼 **fp Ver.5.02 與 fp L Ver.3.02 同日發布**(2023-08-03):同一 codebase(w71c1 平台),
開機時依機身 EEPROM/感光元件辨識切換 IMX410/IMX455 路徑。

## 3. ★ 硬體晶片清單(BOM)

| 類別 | 晶片 | 韌體符號 |
|---|---|---|
| **SoC / 影像 ASIC** | **XZ01**(Socionext Milbeaut 系,w71c1 板級) | `XZ01ES1.0`, `W71C1` |
| **感光元件** | **Sony IMX410**(fp)/ **IMX455**(fp L) | `XC_ImageSensorIMX410/455` |
| **電源 IC(兼 RTC)** | **Richtek RT5035C** | `XC_PowerIcRT5035C`, `XC_RtcIcRT5035C` |
| **電量計** | **Mitsumi MM3556** | `BatteryIcMM3556` |
| **LCD(含觸控)** | **JDI LPM032M366C**(3.2") | `XC_DisplayLcdJDI_LPM032M366C`, `TouchPanelIcLPM032M366` |
| **陀螺儀** | **InvenSense ICM20321** | `IMUDevInterface_ICM20321` |
| **加速度計** | **NXP MMA8452Q** | `IMUDevSens_ACCEL_MMA8452Q` |
| **快門** | **純電子**(無機械快門) | `XC_FpShutterNoDevice` |
| **儲存** | NAND(內部)+ SD UHS-II + USB host SSD | `XC_PromDriverNand`, `MscHost` |
| **副處理器** | ARM926 ×2(NAND 分割區 `ARM926_1/2`) | IPL 分割表 |

- **IMU(ICM20321 陀螺 + MMA8452Q 加速度)** 用於電子防抖 + 水平儀 + 動態預測 AF。
- **RT5035C 兼 RTC**(時鐘也在電源 IC 上)。

## 4. 影像編解碼 / 壓縮

- **CinemaDNG(影片)= 未壓縮**(Compression=1)→ 需 ~300MB/s,故綁外接 SSD。`RECORDER_SPEC.md` 的假設正確。
- **靜態 DNG = 可選 LJPEG 壓縮**(`cam_still_raw_compress` + `src/hal/RawCD/src/XC_HalLjpeg.cpp`,RawCD=Raw CoDec)。
- SIG0/SIG1 硬體管線(XZ01):`BAYER_NR`, `3DDNR`, `GAMMA`, `CRCT`(校正), `RAWOUT`(RAW 打包)。

## 5. 安全 posture(全四段掃描,補充 SECURITY.md)

- **無任何密碼 / API key / 私鑰 / ssh key / 憑證。**
- **無密碼學簽章 / 雜湊驗證**(SHA/MD5/AES 常數表全無);完整性只有 byte-sum / CRC32 / BCH-ECC。
- **無 backdoor / god-mode / master-key 字串。**
- URL 全良性:W3C(RDF/XMP)、Adobe XMP、**Pix4D**(空拍/攝影測量 metadata namespace)、SIGMA Photo Pro、IPA 字型授權。
- 殘留:開發者信箱 `sugar-keiki@infoseek.jp`(某第三方/字型庫留下,非機密)。

## 6. 子系統覆蓋狀態

| 已深入 | 概覽 / 待深入 |
|---|---|
| 容器格式、LZSS、DFI | seg1(data 段:PTP dispatch 表在此) |
| L-mount 協定、AF、影像管線、Fwup | DAT1(1MB)內容 |
| HDMI RAW、PTP、GIMBAL、shell、mem 指令 | IPL 完整流程(base=0 已知) |
| USB 各 class、控制/資料出口(EGRESS_MAP) | 感光元件暫存器級序列(IMX410/455 mode 表) |
| 安全/簽章、硬體 BOM | Lua UI 系統、Menu 系統細節 |

## 7. 平台身份小結
- 機身平台代號:**w71c1**;影像 ASIC:**XZ01**;bootloader:**PureNAND IPL xz01-v0.7 (Misato)**。
- 一份韌體 = fp + fp L;編譯器 IAR;RTOS 跡象 eSOL 系(itron 類原語:semaphore/eventflag/messagebuffer/cyclichandler)。
