# DaVinci 解碼特徵化 — 操作說明(回讀 16-bit TIFF)

目標:量出「DaVinci 把 CinemaDNG 解碼進 DWG」的完整變換,並和相機 JPG 對齊。
需要**兩張 16-bit TIFF**,兩者的 Camera Raw 設定必須**完全一致**。

## 步驟
1. **匯入**:把資料夾 `char_dng/`(12 幀 CinemaDNG 序列)拖進媒體池 → 會變成一個影片 clip。
   同時確保 `_SDI0013.DNG` 也在媒體池。
2. **Camera Raw 設定(兩個 clip 都設成一樣,就是你平常的流程)**:
   - Decode Using: Clip / Camera Metadata(兩者相同即可)
   - Color Space = **ACES**,Gamma = **Linear**(你現在的設定)
   - White Balance = As Shot,其餘不動。
3. **時間線**:各放一段。專案 = DaVinci YRGB Color Managed,working = DaVinci Wide Gamut / Intermediate。
4. **輸出(Deliver)兩張 TIFF**:
   - Format = **TIFF**,Codec = **RGB 16-bit**
   - **Output / Data Color Space = DaVinci Wide Gamut / DaVinci Intermediate**(不要 709/sRGB,不要 tone-mapping)
   - 各匯出**單幀**即可:
     - `char_out.tif`  ← 特徵圖那段
     - `SDI0013_dwg.tif` ← `_SDI0013.DNG` 那段(原生解析度,不要裁切/縮放)
5. 把 `char_out.tif` 和 `SDI0013_dwg.tif` 兩個檔給我。

## 我這邊會做
- `char_out.tif`:按 6×4 相對中心讀 24 格 DWG/DI 值 → 對照 `char_key.csv` 的已知輸入
  → 反解 DaVinci 的**傳遞函數 + 原色矩陣**(解析度無關,讀中心)。
- `SDI0013_dwg.tif` vs `_SDI0013.JPG`:逐像素對應「DaVinci 節點值 ↔ 相機 SIGMA 渲染」
  → 直接擬出 DCTL 該做的變換(把 DaVinci 解碼 + SIGMA look 一次吸收)。

## 注意
- 輸出色域**務必**是 DWG/DI,這樣我拿到的就是節點原始值,不含輸出 DRT。
- 兩張 TIFF 的 Camera Raw 設定要一致,否則對不起來。
- 解析度不拘(我讀相對中心);但 `_SDI0013` 那張盡量原生 6000×4000 以便和 JPG 對齊。
