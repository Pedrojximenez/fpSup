# SIGMA fp — 自製 HDMI RAW → CinemaDNG 錄影機 規格書

> ⚠️ **2026-09-13 部分修正 → 見 `../../../research/interfaces/../../../research/interfaces/notes/HDMI_RAW_FORMAT.md`**
> - **§3.4 的「色彩格式完全不在韌體」不正確。** 它在 TX 暫存器 `0x30190004` bits[14:12]
>   （`FUN_c00E5FE0` 寫入），只是被設成**單一編譯期常數 3**，所有輸出路徑（含 RAW）共用。
>   → 原結論「4:2:2 verbatim 直通即可」**不受影響**，但驗證方式可簡化：
>   先用一般（非 RAW）輸出確認擷取鏈 bit-exact，等於也驗證了 RAW。
> - **§5 的「HDMI 光柵確切幾何 ❌ 需實測」已部分解決**：
>   HDMI framebuffer = **2 B/px**（`FUN_c00E23D0` 清 `W*H*2`），線上 Bayer 幀 = **3856×2176**
>   （由實拍 BRAW 的 `crop_origin (8,8)` / `crop_size 3840×2160` 推得），
>   光柵利用率 **75.9%**，閒置約 **521 行**。仍待實測的只剩位元佈局與 Bayer 相位。

目標：接 fp 的 HDMI RAW 輸出，還原成 CinemaDNG 序列。
本文件從 Ver.5.02 韌體反推出「你要複製的兩份規格」：**(A) DNG 檔案結構** 與 **(B) HDMI RAW 傳輸**。

> 誠實界線：DNG 結構（tag 集合）已由韌體**確認**；色彩科學數值（ColorMatrix 等）是機種常數，
> 建議直接從一張真實 fp CinemaDNG 複製（見 §2.3）。HDMI 上**確切的像素位元排列**（打包順序、
> Bayer 相位）韌體指出其參數存在於模式表，但**最終位元佈局需用真實擷取比對確認**（見 §3.3）。

---

## 1. 整體資料流（回顧，詳見 `notes/research/interfaces/../../../research/interfaces/notes/HDMI_RAW.md`）

```
感光元件 Bayer → SIG0/SIG1 RAWOUT（12-bit 打包進 DRAM framebuffer）
   → DisplayOutputSelect → XZ01 HDMI TX（標準視訊光柵，無 vendor handshake）
   → HDMI 纜線 → 【你的錄影機】
```

你的錄影機要做的：
```
HDMI 擷取（標準視訊幀）→ 解包成 Bayer 平面 → 包成 DNG（每幀一檔）→ 寫 .DNG 序列
```

---

## 2. (A) CinemaDNG 檔案結構 —— 已由韌體確認

fp 的 DNG builder 用 **tag-list 模板表**（韌體 `0xC0746E00` 起）逐一產生 IFD。
以下是解析出來的**確切 tag 集合**。

### 2.1 主影像 IFD（縮圖/預覽用）
`NewSubfileType, ImageWidth, ImageLength, BitsPerSample, Compression, PhotoInterp,
ImageDescription, Make, Model, StripOffsets, Orientation, SamplesPerPixel, RowsPerStrip,
StripByteCounts, XResolution, YResolution, PlanarConfig, ResolutionUnit, Software, DateTime,
Artist, SubIFDs, Copyright, ExifIFD, GPSInfo(0x8825), DNGVersion, DNGBackwardVersion,
UniqueCameraModel, ColorMatrix1, ColorMatrix2, AsShotNeutral, BaselineExposure, BaselineNoise,
BaselineSharpness, 0xC62F(CameraSerial), LensInfo, DNGPrivateData, MakerNoteSafety,
CalibrationIlluminant1, CalibrationIlluminant2, RawDataUniqueID, ProfileHueSatMapDims,
ProfileHueSatMapData1, ProfileHueSatMapData2, ProfileToneCurve, ProfileEmbedPolicy,
PreviewColorSpace, 0xC7A3`

### 2.2 RAW SubIFD（★ 真正的 RAW 幀，這是錄影機主要要寫的）
`NewSubfileType(=0), ImageWidth, ImageLength, BitsPerSample(=12), Compression(=1 未壓縮),
PhotoInterp(=32803 CFA), ImageDescription, Make, Model, StripOffsets, Orientation,
SamplesPerPixel(=1), RowsPerStrip, StripByteCounts, XResolution, YResolution, PlanarConfig,
ResolutionUnit, Software, DateTime, Artist, TileWidth(0x142), TileLength(0x143),
TileOffsets(0x144), TileByteCounts(0x145), CFARepeatPatternDim(=2,2), CFAPattern,
Copyright, ExifIFD, DNGVersion, DNGBackwardVersion, UniqueCameraModel, CFALayout,
LinearizationTable, BlackLevelRepeatDim, BlackLevel, WhiteLevel, DefaultCropOrigin,
DefaultCropSize, ColorMatrix1, ColorMatrix2, AsShotNeutral, BaselineExposure, BaselineNoise,
BaselineSharpness, 0xC62F, LensInfo, DNGPrivateData, MakerNoteSafety,
CalibrationIlluminant1, CalibrationIlluminant2, RawDataUniqueID, ActiveArea,
ProfileHueSatMapDims, ProfileHueSatMapData1/2, ProfileToneCurve, ProfileEmbedPolicy,
OpcodeList2, OpcodeList3, TimeCodes, FrameRate, 0xC772(ProfileGainTableMap), 0xC7A3`

重點：
- **BitsPerSample = 12**、**Compression = 1（未壓縮）**、**PhotoInterpretation = 32803（CFA/Bayer）**
- 用 **Tile**（0x142–0x145）而非 Strip 存像素——但錄影機自己寫時可用 Strip（StripOffsets/StripByteCounts），DNG 讀取器兩者都吃
- **OpcodeList2/3** = 鏡頭校正（暗角/畸變/色差），fp 把它當「後製 opcode」寫進 DNG 讓解 RAW 時套用
- **TimeCodes(0xC763) + FrameRate(0xC764)** = CinemaDNG 影格中繼資料（做序列時要填）
- **DNGPrivateData** 內含 SIGMA 專屬區塊 `SIGMA_EXTH_SPPA`（韌體 `0xC0747A98`）

### 2.3 數值怎麼填（策略）
DNG builder 的 **tag 集合**已確認；**數值**分兩類：

| 類型 | tag | 來源 |
|---|---|---|
| **機種常數**（每台 fp 都一樣） | ColorMatrix1/2, ForwardMatrix, CalibrationIlluminant1/2, UniqueCameraModel="SIGMA fp", CFAPattern, CFALayout, WhiteLevel, BlackLevel, LinearizationTable, Profile* | **直接從一張真實 fp CinemaDNG 複製**（最可靠；這些值是燒在韌體的常數，抄現成的不會錯） |
| **每幀變動** | ImageWidth/Length, AsShotNeutral（白平衡）, ExposureTime, FNumber, ISO, DateTime, TimeCodes, StripOffsets/ByteCounts, RAW 像素 | 錄影機依當下擷取填 |

→ **建議**：先用 fp 自己錄一段 CinemaDNG 到卡上當「黃金參考」，用 exiftool 匯出完整 tag，
把「機種常數」那類整包搬進你的 DNG 產生器。位元深度/CFA/矩陣都以那份為準。

位元深度 enum（韌體 `FUN_c02DA870`）：`0→12, 1→14, 2→16, 3→10, 4→8`bit。CinemaDNG RAW 走 **mode 0 = 12-bit**。

---

## 3. (B) HDMI RAW 傳輸

### 3.1 光柵與時序（幾何來自 `HdmiLimit` @ 0xC0437740）
輸出幾何存在一個 record struct（`*(ctx+4)`）：

| struct 位移 | 欄位 |
|---|---|
| +0x08 / +0x0C | recSize 寬 / 高 |
| +0x18 / +0x1C | stillSize 寬 / 高 |
| +0x20 | 位元深度 enum（→ FUN_c02DA870） |
| +0x28 | zoom 模式 |
| +0x44 | full_angle_mode 旗標 |
| +0x26 / +0x47 | HdmiRaw / HdmiRec 旗標 |
| +0x2c…+0x40 | zoom 座標 (x,y,w,h,...) |

HDMI 輸出尺寸選單值：**1920×1080 / 3840×2160 / (4224×…)**、可選 fps（`SetHdmiOutputSize/Framerate`）。
公開已知：fp 的 HDMI RAW 為 **12-bit Bayer，UHD(3840×2160) 或 FHD(1920×1080)**。

### 3.2 12-bit 打包（原理）
RAW 模式時 SIG0/SIG1 的 **RAWOUT** 硬體區塊把每個 12-bit Bayer sample 打包，
以「一張 RGB/YCbCr 視訊幀」的形式塞進 HDMI 光柵。12-bit 塞進 8-bit-per-channel 的 HDMI 像素，
常見做法是「2 個 12-bit sample 打包成 3 bytes」，再攤平到視訊幀的像素通道。
`RAWMODE ON`（`FUN_c04EB9E8`）會寫 SIG 硬體暫存器（mode 值 0x123..0x678 對應不同打包/尺寸模式）。

### 3.3 ★ 需要用真實擷取確認的部分
韌體確認了「12-bit、Bayer、走標準光柵、參數在模式表」，但**確切位元佈局無法只靠韌體百分百定死**
（打包發生在 XZ01 ASIC 硬體暫存器層，不是純軟體）。做錄影機時必須用真實 HDMI 擷取比對：

1. **實際光柵尺寸**：擷取到的視訊幀寬×高（可能與 Bayer 尺寸不同，因為 12-bit 打包會改變每列 byte 數）
2. **打包佈局**：2×12-bit→3-byte 的位元順序（MSB/LSB first）、跨像素通道的攤放方式
3. **Bayer 相位**：擷取幀左上角對應的 CFA pattern（RGGB/GRBG/GBRG/BGGR 哪一種）——用一張已知色卡/灰卡校準
4. **有無 header/metadata 列**：某些相機在光柵頂/底塞幾列中繼資料，要辨識並剔除
5. **黑/白位準**：擷取值域對應 DNG 的 BlackLevel/WhiteLevel（可與參考 DNG 對齊）

> 這 5 點是「把擷取 buffer 正確變成 DNG raw plane」的核心，也是唯一必須實測的環節。
> 建議流程：拍固定灰階/色卡場景，**同時**（a）fp 錄卡上 CinemaDNG（b）你的錄影機存 HDMI 原始幀，
> 逐像素回歸出打包公式，直到你的 DNG 與 fp 卡上 DNG 在解出的 Bayer 值上吻合。

### 3.4 ★ 色彩格式 & 擷取卡結論（韌體實證，2026 更新）

**線上色彩標籤(RGB/YCbCr、4:2:2/4:4:4)不在韌體 —— 由 XZ01 ASIC HDMI-TX 硬體產生**（全 ROM 掃描：無任何 colorspace/subsampling 選擇暫存器、無 AVI-InfoFrame builder、無 `InfoFrame/YCbCr/colorimetry` 字串；輸出區塊 `0x30200000` 只有 DMA/中斷/DRAM base）。所以「4:2:2 vs 4:4:4」**無法只靠韌體 100% 定死**——但韌體證據**強烈指向 4:2:2 足夠**：

| 韌體證據 | 位址 |
|---|---|
| **RAW 酬載 = 緊密打包 12-bit Bayer,`2 px → 3 bytes`（1.5 B/px）,little-endian**（10-bit ×10/8、14-bit ×14/8) | `CNRO` `FUN_c015c230`(TYPE=0 RAW→ `W·H·3/2`) |
| **RAW 路徑繞過 RGB→YUV(CSC bypass)**,Bayer 原封通過 | `SIGPRO_RawToRawVmix`(ROM c07d3f4c);對比 `SIGPRO_RawToYuv` c07d3ef4 走 R2Y |
| **fp HDMI 管線原生 8-bit YCbCr 4:2:2**(video buffer 2 B/px);**韌體無任何 RGB 4:4:4 輸出路徑** | TYPE=1 YUV→`W·H·2`;TYPE 字串 `RAW/RGB/YUV/Y/ARGB` @c07d3e84 |
| 解析度 = **DCI4K 4096×2160 / UHD 3840×2160 / FHD 1920×1080**;**無「UHD 強制 4:2:2」色彩分支**(色彩根本不在韌體) | 幾何表 `DAT_c0b51044` |
| RAW raster **寬度是 runtime 算的**(`FORMAT_A/LINESPACE_A` `0x30200040/44`,`FUN_c019f4b0`),**韌體給不了靜態值** | → 仍需 §3.3 實測 raster 寬 |

**擷取卡結論**:
- ✅ **一張「原封轉發 8-bit YCbCr 4:2:2(UYVY)」的擷取即可 bit-exact 保住 RAW**;**RGB 4:4:4 非必要**(韌體無此路徑)。
- ❌ **4:2:0 會毀 RAW**(比 4:2:2 再砍一半色度)——**多數 4K USB 卡在 4K 會掉 4:2:0,要小心**。
- ❌ 任何 **CSC(YUV↔RGB)、range scaling(limited↔full)、LUT/銳化/降噪、4:2:2→4:4:4 重建、scaling** 都會改 code 值 → 必須全關(verbatim / data passthrough)。
- **卡選型**(UHD):**Magewell USB Capture HDMI 4K Plus**(~$300,SDK 抓 UYVY,需確認 2160p30 不被迫 4:2:0)或 **LT6911UXC + Jetson Orin Nano**(~$300,獨立機,VI bypass)。Inogeni 4K2USB3=4:2:0 出局;AJA U-TAP=1080p only。DeckLink 4K Extreme($1400 RGB 4:4:4)**不需要**。
- **一次性驗證**:抓一幀 vs 內錄 CinemaDNG,確認 (a) bit-exact、(b) §3.3 的 raster 寬/打包/相位。

---

## 4. 建議的錄影機管線

```
1. HDMI 擷取卡：以「標準視訊模式」抓 fp 輸出（把它當普通 1080p/UHD 訊號，不需 RAW 專屬支援）
2. 每幀：切掉可能的 metadata 列 → 依 §3.3 公式解包成 16-bit 容器裡的 12-bit Bayer 平面
3. 組 DNG：
   - 用 §2.2 的 tag 集合建 raw SubIFD（BitsPerSample=12, PhotoInterp=32803, CFAPattern=參考值）
   - 機種常數 tag 整包從參考 fp DNG 複製（§2.3）
   - 每幀填 AsShotNeutral / Exposure / DateTime / TimeCodes / FrameRate / 像素
4. 寫檔：CLIP/序列，檔名比照 fp（%s%04d.DNG）
5. 驗證：用 Resolve / RawTherapee / dcraw 開你的 DNG，與 fp 卡上 CinemaDNG 目視 + 數值比對
```

省事路線：可直接輸出成 **Adobe DNG（單幀序列）**，用現成 libtiff / tinydng / rawpy 寫 IFD；
色彩科學交給 DNG 內嵌的 ColorMatrix/Profile（從參考 DNG 抄），你只負責把像素放對位置。

---

## 5. 韌體確認 vs 待實測 一覽

| 項目 | 狀態 |
|---|---|
| DNG 主 IFD / raw SubIFD 的 tag 集合 | ✅ 韌體確認（§2.1/2.2） |
| BitsPerSample=12 / Compression=1 / PhotoInterp=CFA | ✅ 韌體確認 |
| 有 OpcodeList（鏡頭校正）、TimeCodes、FrameRate、SIGMA_EXTH_SPPA 私有資料 | ✅ 韌體確認 |
| ColorMatrix/ForwardMatrix/WhiteLevel/CFAPattern 的**數值** | ⚠️ 機種常數，抄參考 DNG（最可靠） |
| HDMI 輸出尺寸選項 1080/2160、12-bit RAW | ✅ 韌體確認 |
| HDMI 光柵**確切像素打包位元佈局 / Bayer 相位 / metadata 列** | ❌ 需真實擷取比對（§3.3） |
| RAW 傳輸無 vendor handshake（相機端） | ✅ 韌體確認（`notes/research/interfaces/../../../research/interfaces/notes/HDMI_RAW.md`） |

---

## 6. 產出檔案
- `notes/research/interfaces/../../../research/interfaces/notes/HDMI_RAW.md` — RAW→HDMI 路徑與 transport 性質
- `out/decomp/dng_named/dng_named.c` — 110 個 CinemaDNG 相關函式
- `out/decomp/dngwrite.c` — 檔案容器寫檔器（SPP/XMP/MediaFile）
- `out/decomp/bitdepth.c` — 位元深度 enum 轉換
- DNG IFD 模板表：seg0 `0xC0746E00`–`0xC0747B00`（tag-list + descriptor + SIGMA_EXTH_SPPA）
