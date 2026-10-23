# SIGMA FP2 vs fp —— 硬體差異

來源:FP2 = 官方英文型錄 `official-downloads/261009_Sigma_FP2 Catalogue_Camera_EN.pdf`(resource 12417,官網未列出);
fp = sigma-global.com fp 規格頁(2026-10-23 擷取)。韌體尚未公開(見文末)。

## 對 RE 有影響的差異

| 項目 | fp | FP2 | RE 意義 |
|---|---|---|---|
| 感光元件 | 背照式 CMOS,24.6 / 25.3 MP,6000×4000 | **部分堆疊式** CMOS,24.5 / 26.8 MP,6016×4012 | 不是 IMX410;總像素多 1.5 MP,模式表/暫存器全要重做 |
| AF | 純對比(IMX410 無 PDAF) | **像面相位 + 對比**,主體追蹤(人/狗貓鳥、眼) | 有 PDAF 像素 → 感光元件確定換了 |
| 機內儲存 | 無 | **約 70 GB 內建記憶體** | 新的儲存層;卡滿後續錄 |
| 錄影 RAW | CinemaDNG 8/10/12 bit | **ProRes RAW / RAW HQ 12 bit**(只能錄到 USB SSD,最高 6K 29.97) | 沒有 CinemaDNG;現有 cDNG 工具鏈(lossless、gyro sidecar、IFD)全不適用 |
| 錄影壓縮 | H.264 ALL-I/GOP | H.264、**H.265**、**L-Log** | 新編碼器 |
| 解析度/格率 | UHD ≤29.97、FHD ≤119.88 | **6K Open Gate** ≤59.94、4K ≤59.94(裁切 100/119.88)、2K ≤119.88 | 原廠就有 open gate;比例 3:2/16:9/17:9/4:3 |
| 音訊 | LPCM 2ch 48 kHz/16 bit | LPCM 4ch 96k / 2ch 192k 24 bit,**32-bit float** | |
| ISO | 基礎 100/640(靜態)、100–25600 | 雙基礎 320/2500(MOV)、**Log/RAW 1250/10000**,100–102400 | |
| 快門 | 1/8000–30 s | **1/25600**–30 s,電子快門 | 讀出明顯更快(堆疊式) |
| 連拍 | 18 fps | 20 fps(DNG 180 張) | |
| 閃燈同步 | 1/30(14-bit 1/15) | 1/50(裁切 1/60) | 全域讀出時間大約 20 ms 以下 |
| 螢幕 | 固定 3.15" 2.1M | **可翻** +90/–45° | |
| USB | 1× USB 3.1 Gen1 Type-C | **兩個 Type-C**:Port 1 USB 2.0(UAC、快門線、**EVF**、PD);Port 2 USB 3.2(大量儲存、UVC、UAC、快門線、PD) | EVF 走 USB;USB shell 的端點/描述元規劃要重查 |
| HDMI | Type D 1.4 | **Type A 2.1** | |
| 耳機 | 3.5 mm(需 EVF-11) | 只走 USB | |
| 時間碼 | 與麥克風/遙控共用 | 與麥克風共用 | |
| 熱靴 | HU-11 | HU-21(OM System / Lumix 規格),含閃燈同步端子 | |
| 電池 | BP-51,約 280 張,充電時不能用 | **BP-91**,約 370 張 / 130 分鐘錄影,USB PD、DC 接頭 CN-91 | |
| 尺寸/重量 | 112.6×69.9×45.3 mm,370 g | 112.8×69.9×41.8 mm,376 g | |
| 防塵防滴 | 有 | 有 | |
| 防手震 | 電子 | 電子 EIS,只限錄影,6K 不能用 | |

## 其他新功能

- Director's Viewfinder(ARRI / SONY / RED 機型框線,變形鏡頭 1.25–2.0× 還原)
- QR code 存/讀設定、截圖、Webcam、機內 DNG 顯影(含補光)、從影片擷取靜態
- **原廠支援 Gyroflow**(我們的 gyro sup 在 fp 上做的事變成原廠功能)
- 13 種色彩模式,與 fp 相同的那一組

## 官網其他未列出的檔案

`official-downloads/`:FP2 機身 STEP(標準、螢幕 90° 無蓋)、HU21、EVF21(+EC51 / 45°+EC61)、LVF21(含/僅支架)、BPL21 —— resource 12409–12416。

## 韌體

2026-10-23:韌體總表沒有 FP2;`/support/firmware/fp2/` 是 404;英文/日文 resource 12200–12800 沒有 `.bin`。
`check_fw.py` 每天往新的 resource id 掃,出現就下載到 `firmware/`。

## BF 韌體作為 FP2 的前例

完整分析在 `sigma_bf/README.md`(2026-10-14):「SIGMA bf SOF」容器已解、全區加密;每區從 offset 0 重用同一金鑰流(two-time pad),
XOR 值集中在 0/1/3/7/0x40/0x80/0xC0 → 明文是低熵、有結構的資料;假設相同處為 0 的投票只覆蓋 28%,需要真正的明文模型。**2026-10-23 已免金鑰解密**(`sigma_bf/bf_decrypt.py`),主程式有 `__C46AUTORUN.txt`。
fp 的 `FP__V502.bin` 是明文 `@DFI` 容器。推論:FP2 若沿用 BF 容器,官方檔一出就能用同一支工具解。
