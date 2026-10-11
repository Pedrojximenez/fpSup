# SIGMA fp — 自製 HDMI RAW → CinemaDNG 錄影機 建置 SOP

> ⚠️ **2026-09-13 選型推翻 → 見 `../../../research/interfaces/../../../research/interfaces/notes/HDMI_RAW_FORMAT.md` §8.4**
> **§2 的首選（Magewell USB Capture HDMI 4K Plus）在 UHD RAW 下不可行。**
> UHD 29.97p 的 8-bit 4:2:2 需 **497 MB/s**，超過 USB 3.0 的實際可用頻寬（~380–420 MB/s）；
> 卡必然退成 4:2:0 / NV12（373 MB/s）或掉幀 → RAW 全毀。**這是頻寬問題，不是設定問題。**
> → 首選改為 **LT6911UXC + Jetson Orin Nano**（走 CSI 不經 USB）；
>   其次 PCIe 擷取卡、確認為 USB 3.2 Gen2 的型號；或降規到 UHD 23.98p（398 MB/s）/ FHD 59.94p（249 MB/s）。
> §7 驗證清單的「擷取為 verbatim 4:2:2」一項，可改用非 RAW 輸出先驗（兩者線上容器相同）。

目標:接 fp 的 HDMI RAW 輸出,還原成 CinemaDNG(12-bit UHD)序列 + 同步音訊。
背景/規格見 `RECORDER_SPEC.md`(DNG 結構 §2、HDMI transport §3、**色彩格式與卡結論 §3.4**)與 `HDMI_RAW.md`。
使用情境:相機 USB-C 被 GIMBAL 控焦佔用 → 影像只能走 HDMI。

═══════════════════════════════════════════════════════════════
## 1. 架構
═══════════════════════════════════════════════════════════════
```
fp HDMI (RAW raster, 12-bit Bayer 打包進標準光柵)
  ├─ 影像 → 擷取卡(verbatim 4:2:2)→ 解包 Bayer → DNG 序列 ──┐
  └─ 嵌入音訊 → I2S/SPDIF → WAV ─────────────────────────────┤→ 共用 timecode/幀計數 → 後製同步
```
- **相機端**:HDMI 輸出設 `SetHdmiOutputFormat = RAW`(`font_G_HDMIfmt_raw`)、Size = UHD。
- **前提驗證**:① RAW HDMI + GIMBAL USB session 並存 —— ✅ **實測 OK,且可同時內錄**(2026 確認);② HDMI RAW 是不是 4:2:2 可保住(§4,待卡實測)。
  → ①「可同時內錄」很關鍵:§4 校準能**同時**取「fp 內錄 CinemaDNG」+「HDMI 擷取幀」逐像素比對。

═══════════════════════════════════════════════════════════════
## 2. 擷取硬體選型
═══════════════════════════════════════════════════════════════
韌體實證(`RECORDER_SPEC §3.4`):RAW = 8-bit 容器裝緊密打包 12-bit Bayer(`2px→3bytes` LE)、CSC 已 bypass、原生 4:2:2、**無 RGB 4:4:4 路徑**。→ **verbatim 4:2:2 就夠,不用 $1400 DeckLink;但 4:2:0 會毀 RAW**。

| 方案 | 形態 | ~價 | 備註 |
|---|---|---|---|
| **Magewell USB Capture HDMI 4K Plus** | HDMI→USB→現有 PC | ~$300 | MWCapture SDK 抓 UYVY;**買前確認 2160p30 能出 4:2:2 不被迫 NV12/4:2:0** |
| **LT6911UXC + Jetson Orin Nano** | HDMI→MIPI CSI→獨立 Linux 機 | ~$50+$250 | 開源驅動(InES-HPMM);V4L2;可無 PC。CSI 不是 PC 介面故需 Jetson |
| (更省 CSI 主機)Raspberry Pi 5 | HDMI→CSI | ~$70 | 有 CSI 但 4K bit-exact 較難、風險高 |
| ❌ Inogeni 4K2USB3 | — | — | 4K 只給 4:2:0 → 毀 RAW |
| ❌ AJA U-TAP HDMI | — | — | 只到 1080p |
| ❌ Elgato 等消費級 | — | — | 壓縮 + 4:2:0 + 加料 |

**音訊**:HDMI 帶嵌入 LPCM(通常 48kHz)。LT6911UXC 有 **I2S/SPDIF** 輸出;Magewell 也擷取嵌入音訊。→ 收成 WAV。

═══════════════════════════════════════════════════════════════
## 3. Verbatim 配置(命根:不能加料)
═══════════════════════════════════════════════════════════════
任一層做「4:2:2→4:4:4 重建 / CSC / range scaling / LUT / 銳化 / 降噪 / scaling」都會改 code 值 → RAW 全毀。
- **Magewell**:SDK 指定輸出格式 = **UYVY / YUY2(4:2:2 8-bit)**,關 color conversion,設 **full-range bypass**,不 scale。
- **LT6911UXC**:設成 **verbatim 直通**(關 chroma 濾波/CSC/scaling);對應 Jetson 端。
- **Jetson VI/CSI**:走 **bypass 模式**,**不進 ISP**(V4L2 raw capture,pixel format 對上 LT6911 輸出)。
- 驗:抓一塊已知平坦區,確認 code 值原值進原值出(尤其查 **16 / 235** 附近有沒有被 range 縮放)。

═══════════════════════════════════════════════════════════════
## 4. 一次性校準(唯一必須實測的環節,見 RECORDER_SPEC §3.3)
═══════════════════════════════════════════════════════════════
raster 寬 / 打包位元順序 / Bayer 相位 / metadata 列 韌體給不了(runtime + ASIC),必須實測:
1. 拍固定**灰階/色卡**場景,**同時**:(a) fp 內錄一張 **CinemaDNG**(SD 卡);(b) 你的錄影機存 **HDMI 原始幀**。
2. 逐像素回歸:
   - **實際光柵尺寸**(擷取幀寬×高,可能 ≠ Bayer 尺寸,因 12-bit 打包改每列 byte 數)。
   - **打包佈局**:`2×12-bit → 3-byte` 的位元順序(LE 已知,MSB/LSB first 實測)、跨像素通道攤放。
   - **Bayer 相位**:左上角 CFA(RGGB/GRBG/GBRG/BGGR)—— 用色卡定。
   - **header/metadata 列**:頂/底有無中繼列 → 辨識剔除。
   - **黑/白位準**:擷取值域 ↔ DNG BlackLevel/WhiteLevel(對齊參考 DNG)。
3. 直到你解出的 Bayer 值與 fp 卡上 DNG **逐像素吻合**。

═══════════════════════════════════════════════════════════════
## 5. 每幀寫 DNG(結構全在 RECORDER_SPEC §2)
═══════════════════════════════════════════════════════════════
1. 切掉 metadata 列 → 依 §4 公式解包成 16-bit 容器裡的 12-bit Bayer 平面。
2. 組 raw SubIFD:`BitsPerSample=12, Compression=1, PhotoInterp=32803(CFA), CFAPattern/CFALayout=校準值`(tag 集合 §2.2)。
3. **機種常數 tag 整包從一張真實 fp CinemaDNG 複製**(ColorMatrix1/2、CalibrationIlluminant、WhiteLevel/BlackLevel、Profile*…;§2.3 —— 最可靠,別自己算)。
4. 每幀變動 tag:`ImageWidth/Length, AsShotNeutral, ExposureTime, FNumber, ISO, DateTime, TimeCodes(0xC763), FrameRate(0xC764), StripOffsets/ByteCounts, 像素`。
5. 寫序列(檔名比照 fp `%s%04d.DNG`);工具可用 libtiff / tinydng / 自寫 IFD(參考 `tools/cinedng_to_dcp.py` 的 TIFF 寫法)。

═══════════════════════════════════════════════════════════════
## 6. 音訊 + 同步
═══════════════════════════════════════════════════════════════
- 擷取 HDMI 嵌入音訊(I2S/SPDIF 或 Magewell audio)→ 寫 **WAV**(48kHz stereo,實測確認)。
- **同步**:DNG 幀的 `TimeCodes(0xC763) + FrameRate(0xC764)` 當對齊依據;或錄影機給 {DNG 序列 + WAV} 共用開始時戳/幀計數,等間隔對齊。後製(Resolve 匯入 CinemaDNG 序列)依 timecode 貼 WAV。
- CinemaDNG 本體無音軌 —— fp 內錄也是「DNG 資料夾 + 獨立 WAV」,照抄此模型。

═══════════════════════════════════════════════════════════════
## 7. 驗證清單
═══════════════════════════════════════════════════════════════
- [x] RAW HDMI + GIMBAL USB 並存 OK ✅(實測,且可同時內錄)
- [ ] 擷取為 verbatim 4:2:2、無 CSC/range/scaling(16/235 附近 code 值不變)
- [ ] 一幀解包後 Bayer 值 = fp 內錄 CinemaDNG(§4)
- [ ] Resolve / RawTherapee / rawpy 能開你的 DNG,色彩與 fp 卡上 CinemaDNG 目視+數值吻合
- [ ] 音訊 WAV 與影像 timecode 對齊

> 相關:`RECORDER_SPEC.md`(規格全本)、`HDMI_RAW.md`(transport 性質)、`tools/cinedng_to_dcp.py`(DNG/TIFF 寫法參考)。
