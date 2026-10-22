# SIGMA fp CinemaDNG ColorMatrix A/B 測試

目的：確認 Resolve 的目前解碼路徑是否受到嵌入的 ColorMatrix1/2 影響。

- `A_original.DNG`：真實 fp 12-bit CinemaDNG 單幀的逐位元組副本。
- `B_matrix_probe.DNG`：同一檔案，只修改既有 ColorMatrix1/2 的矩陣數值。

B 是刻意放大色度差異的偵測檔，不是正式校色檔。A/B 的 RAW 像素、黑白位準、AsShotNeutral、曝光、相機型號、光源標籤及所有其他資料完全相同。來源為 FHD CinemaDNG，儲存尺寸 1936×1090，有效裁切為 1920×1080。

## 在 Resolve 比較

1. 將 A、B 以兩個獨立素材匯入。不要只看檔案管理員或媒體縮圖；在時間軸／Color 頁查看實際 RAW 解碼結果。
2. 兩張使用同樣的專案色彩管理、Camera RAW 解碼色域與 Gamma。先用相同的 As Shot 白平衡與相同曝光，不對 B 另外校正。
3. 比較時使用原始素材，避免代理檔、Optimized Media 或舊 render cache；兩張使用相同且無調整的節點，不使用自動色彩、個別 LUT 或個別調色。
4. 若解碼輸出明顯不同，代表此版本／設定的解碼路徑受到 ColorMatrix 標籤影響。B 預期會有更強的色度差異，可能產生超色域／裁切；中間色溫亦可能有色偏。
5. 若肉眼相同，請用完全一致的輸出設定各輸出一張浮點 EXR 比較 RGB 數值，再排除快取和解碼設定覆蓋。這時仍不可直接推論 Resolve 完全忽略所有 metadata。

這個測試同時改 CM1、CM2，避免只改到目前未使用的端點；它不能單獨證明兩個端點都被讀取，也不能證明插值、白平衡或整體色彩校準正確。若要判別個別標籤，需另做單標籤測試。

## 測試矩陣

對每個光源端點，在原矩陣右側乘上 Q：`CM_B = CM_A × Q`。

```text
Q = [ 0.5  0.5×Xw  0   ]
    [ 0    1       0   ]
    [ 0    0.5×Zw  0.5 ]
```

W = (Xw, 1, Zw) 為對應的光源白點：Standard A 用 (1.09850, 1, 0.35585)，D65 用 (0.95047, 1, 1.08883)。Q 保留該端點白色，行列式為 0.25，保持可逆；理想線性反向解碼中，Q 的反矩陣維持 Y 並把相對白點的色度偏離放大兩倍。這不是保證螢幕上的飽和度恰好兩倍，且雙光源插值時白色不保證完全不變。

## 檔案驗證

`verification.json` 記錄檔案與 RAW payload 的 SHA-256、修改位址和 A/B 矩陣。產生時確認 B 的任何差異均位於原有兩個 72-byte 矩陣 payload 之內，檔案長度與其他 bytes 均相同；原始素材未修改。

另外以 LibRaw 實際開啟兩張檔案，確認解壓後的 Bayer 陣列逐值相同，且相同設定下的 RGB 解碼輸出不同。這是檔案可讀與測試擾動有效的交叉檢查，不代表 Resolve 已通過測試。

使用者已回報 Resolve 的 A/B 顯示不同，並提供兩張 JPEG；已核對可見色度差異。浮點 EXR 的精確數值驗證尚未完成。詳見 `resolve-jpeg-observation.md`。`verification.json` 的 `Resolve_test_performed: false` 記錄的是最初產生檔案時的狀態。

後續收到兩張 16-bit TIFF，數值分析支持矩陣的色度放大方向及量級，詳見 `resolve-tiff-observation.md` 與 `resolve-tiff-analysis.json`。本輪 metadata 反應測試已有正面结果；正式色彩校準和浮點範圍驗證是後續工作。

## OFF 的設計意圖

官方定位、韌體分支及 ROM 矩陣的交叉分析見 [off-design-assessment.md](off-design-assessment.md)。目前證據偏向刻意設計的低處理模式；尚不足以認定它是未完成功能，也不能把顯示差異直接等同色彩校準錯誤。

## 下一輪候選檔

已新增 `C_firmware_normal.DNG`、`D_adobe_cm_only.DNG`，與 A 使用完全相同的 RAW 像素，僅更換 ColorMatrix1/2。比較 A／C／D 的方式與限制見 [candidate-comparison.md](candidate-comparison.md)，逐項驗證見 `candidate-verification.json`。TIFF 可供這一輪比較；請維持相同設定及 As Shot 白平衡。

後續確認非 OFF 模式共用標準 DNG 基礎 profile，而非各模式一套專屬矩陣／色彩表；來源、實拍樣本範圍與建議工作流見 [non-off-modes-and-workflow.md](non-off-modes-and-workflow.md)。

> **2026-09-25**：C 的配方（只換 ColorMatrix1/2）在真正的 OFF cDNG 上實測，只補到 OFF↔Standard 全部差異的約 4%；Resolve 同時會套用 ProfileToneCurve 與 HueSatMap，要五個 tag 一起移植才等同 Standard。見 [`profile-tags-ab-20260925/`](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/profile-tags-ab-20260925/README.md)。
