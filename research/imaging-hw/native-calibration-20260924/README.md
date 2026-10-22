# fp 原廠輸入校準 → Resolve：目前已確認與下一步

2026-09-24。目標是恢復 **SIGMA fp 自己提供的輸入描述**，不借用其他相機的矩陣，不修改 RAW 像素或烘焙 gamma。

## 已找到的原廠鏈

```text
fp ROM 的 normal ColorMatrix1/2
             ＋
該機身 SensAdj → 私有 CameraCalibration（D）
             ↓
原廠 DNG writer：CM = inverse(D) × ROM CM
             ↓
標準 DNG ColorMatrix1/2 metadata
             ↓
Resolve RAW 解碼 → 選定的輸出色彩空間／Gamma
```

已收到並分析 A/C 的 TIFF：A 與先前 A 整檔完全相同，C 的變化主要可由保留中性方向的固定矩陣解釋，支持 Resolve 實際使用原廠 normal ColorMatrix。詳見 [本輪 A/C 結果](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/native-calibration-20260924/resolve-ac-observation.md)。這仍不足以證明完整計算、所有 DNG profile 標籤支援或絕對色準。

使用者後續確認 TIFF 為內建靜幀，流程是 P3 D60 → DWG → Rec.709，且「無轉換」是指 **Input DRT=None**。不是把 P3 數值錯誤重新指派成 DWG，不需要額外新增 CST。矩陣擬合仍只是最終受管理影像在本場景的近似描述，不能等同於已測得 fp 場景線性 IDT。

normal CM 是韌體明確用於 DNG 輸入 profile 的原廠資料，不是從飽和度猜出來的。機身 SensAdj 與當次白平衡分開；Standard 等模式的私有 RGB 矩陣、Hue/Sat 表及 tone 是另外的渲染資料，不能任意再乘入 ColorMatrix。尚未證明原廠 normal profile 完全不含美學取向。

## 本輪增加的 RAW 層證據

### 後續補足：真正 Standard CinemaDNG 已確認

使用者提供 A001_297 OFF（98 幀）與 A001_298 Standard（122 幀）。兩段各自的色彩 profile 全序列一致；298 的 CM1/2 與既有 C 候選逐 byte 相同，且精確符合原廠 normal ROM＋該機身校準的 writer 計算。**在本次 FHD 12-bit、5.02.0.V91 錄影条件下，直接以 Standard 錄製便會取得 normal CM，已不再只是靜態 DNG 推測。**

Standard 另帶非 identity HueSatMap／ToneCurve，不等於只換矩陣的 C；尚未驗證 Resolve 對新兩段的完整渲染與絕對色準。詳見 [297／298 實拍檢查](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/native-calibration-20260924/cdng-297-298-observation.md)。

> **2026-09-25 更新**：「Resolve 對 297／298 的完整渲染」已實測，見 [`profile-tags-ab-20260925/`](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/profile-tags-ab-20260925/README.md)。結果：Resolve **會**套用 ProfileToneCurve 與 HueSatMap；只換 ColorMatrix 只補到 OFF↔Standard 差異的約 4%，五個 tag 整組移植才等同用 Standard 錄。另外本筆記記載的「預製色調曲線未勾選」與該輪實測不符，待面板確認。絕對色準仍未驗證。

### 較早的 RAW 與 writer 證據

- 同場景、同曝光／白平衡的 `_SDI0010–13`，直接比較未顯影 Bayer：OFF 對 PowderBlue／TealAndOrange／Standard 的各通道區塊中位倍率與 1 相差不超過約 0.11%；R/G、B/G 的中位變化低於 0.05%。這些不是逐像素誤差上限，局部殘差更大。
- 已追到 FHD CinemaDNG 實際使用過的末端封裝路徑；此階段處理 descriptor、標頭／RAW 長度與補零，沒有 ColorMatrix 像素運算。RAW 來源端的全部硬體狀態尚未閉合。
- 兩者共同支持「主要外觀差異來自後续解讀」，使 normal CM 用於 OFF 的候選更有依據；靜態 DNG 的實拍結果不能直接當作全部 CinemaDNG 模式的驗收。

**實務判斷：**目前已有可重現的 fp 原廠輸入描述候選，並證明本次 Resolve 路徑會回應其改動。可用 C 進行受控試用，不必借用 BMD／Sony 色域，也不必改 RAW gamma；尚不能保證它是量測中性、完整原廠 look 或通用批次修復。

## 已有的測試檔，不必重做

[C_firmware_normal.DNG](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/colormatrix-ab-20260923/C_firmware_normal.DNG)

- 依原廠 writer 方法重建，含該機身的補償。
- 兩個矩陣與同機身實拍 `_SDI5625.DNG` 的矩陣 payload 完全相同。
- 相對 A 只有 46 個 byte 改變，全部位於兩個 ColorMatrix payload。
- RAW strip、當次白平衡、黑白位準及其他 metadata 完全不變。
- 保留 OFF 的其他 profile 資料，因此不是完整 Standard 外觀。
- **不要再對 C 加一次機身補償，也不要把私有 CameraCalibration 直接另填進標準 CameraCalibration1/2。**

這些證據確定了原廠來源與計算一致性；A/C 輸出支持 Resolve 會使用這項改動。尚未逐值驗證其完整線性解碼，更不能以比較飽和作為色準判據。

## Resolve 測試設定及後續範圍

本次只讀到目前 Camera Raw 面板為 P3 D60／線性、白平衡「與拍攝時相同」、解碼方式「項目」，高光恢復勾選、預製色調曲線未勾選。沒有修改專案；沒有確認這組設定對時間線全部片段的套用情況或所有節點內容。外部 scripting API 本次未連接成功。

不必為此改選 sRGB。下拉選單與原廠輸入矩陣處在不同層次；它不能代替 camera→色彩基準的描述。

本輪 A/C 已完成輸出反應分析。若後續進行更精確的測試，讓 A/C 使用完全相同的 RAW 輸出色域、Gamma、As Shot 白平衡與曝光，排除 LUT、CST、自動色彩處理、個別調色與舊快取。若變更設定，A/C 都要重新輸出；不要拿新 C 對比不同設定的舊 A。

現有 TIFF 已確認實際解碼差異，不需重複輸出來證明「有差」。若要核對線性矩陣計算及超出 0–1 的值，後續使用可保留浮點數的線性輸出，並記錄完整色彩管理／輸出設定。完整驗證之前，不把 C 宣告為通用修復或批次套用到正式素材。

不需要先有色卡，才能驗證原廠數據來源與 Resolve 的計算行為；若要進一步宣稱絕對色準，才需要獨立的測量依據。

## 證據

- [SensAdj、白平衡與 writer 的完整來源鏈](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/native-calibration-20260924/body-calibration-audit.md)
- [normal CM 用途與 ISP 渲染矩陣的區分](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/native-calibration-20260924/normal-cm-consumers-and-render-base.md)
- [同場景 OFF／正常模式 RAW 實拍比較](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/native-calibration-20260924/existing-raw-capture-comparison.md)
- [CinemaDNG 末端寫入路徑與上游界線](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/native-calibration-20260924/cinemadng-raw-sink-audit.md)
- [現有檔案逐 byte 驗證](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/native-calibration-20260924/body-calibration-verification.json)

本次未操作相機、未修改韌體、未修改現有 DNG 或 Resolve 專案。
