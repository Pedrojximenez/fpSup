# SIGMA fp OFF：設計意圖的證據與界線

日期：2026-09-23。對象：現有 Ver.5.02 反編譯結果、ROM 常數，以及 A_original.DNG；不是 SIGMA 內部設計文件。

## 判斷

較符合現有證據的解釋是：OFF 是刻意實作的「盡量不作顯色／風格處理」模式，不像單純忘了填 ColorMatrix。它是否同時提供適合中性色彩管理的相機特性描述，仍須色卡／光源量測驗證。不能據此認定 SIGMA 曾有未完成的電影色彩計畫，或已證明 Resolve 存在解析錯誤。

## 官方定位

- [SIGMA Color Mode Library 的 Off](https://www.sigma-global.com/en/shooting-with-sigma/sigma_color_mode_library/) 明確把它定位為供後製調色者使用、幾乎未調色且接近感光元件直接輸出的模式。
- [官方 fp 韌體紀錄](https://www.sigma-global.com/en/support/firmware/fp/) 把 OFF 列為 2020-06-25 Ver.2.00 新增選項。新增日期證明它是有意加入的功能，但不證明色度學準確性或整個後製整合已完備。

## 本機可重現的實作證據

反編譯檔：`/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c`。

- `FUN_c02c4a50`（123706 行起）：讀取 Sigma 私有 CameraCalibration，求逆，再乘 normal 或 OFF ROM 矩陣，量化成 denominator=10000 的 ColorMatrix1/2。
- 123784、123806 行：模式值 0x24 的專用分支。同一檔的模式名稱寫入邏輯將 0x24 對應 OFF。
- `FUN_c02c4d40`（123833 行起）：OFF 另選 ProfileHueSatMap 資料。
- `FUN_c02c4e80`（123884 行起）：OFF 另選 ProfileToneCurve 資料。
- A_original.DNG 的兩組 HueSatMap 全部為 [0,1,1]，意即不改色相、不縮放飽和度與明度；128 組 tone curve 座標均 x=y。
- 按 writer 的計算方法，從 ROM 和 A 的機身校準值可完整重建 A 的兩組 ColorMatrix 整數分子。不是僅靠畫面觀感推測它用了哪組常數。

## OFF 矩陣的特殊結構

ROM：`/Users/dido/Developer.localized/SIGMAfp_re/out/MAIN_c0000000.bin`，基址 0xC0000000。

- OFF CM1：0xC096FD74，9 個 little-endian double。
- OFF CM2：0xC096FCE4，9 個 little-endian double。

將其與常用 linear-sRGB→XYZ 矩陣 S 的反矩陣比較：

```text
S = [0.4124564  0.3575761  0.1804375]
    [0.2126729  0.7151522  0.0721750]
    [0.0193339  0.1191920  0.9503041]

OFF_CM ≈ diag(g) × inverse(S)
CM1 g ≈ [0.47982293, 1.21056899, 1.56916373]
CM2 g ≈ [0.49225160, 0.99999989, 0.64890809]
```

此關係的最大元素絕對殘差分別約 3.03e-7、2.51e-7；S 本身是有限位數的標準近似。反矩陣三個欄向量正規化所得 xy 接近 (0.64,0.33)、(0.30,0.60)、(0.15,0.06)，即 sRGB／Rec.709 的三原色色度。

在只考慮 CM2 反矩陣和 D65 linear-sRGB 輸出矩陣的簡化模型中：

```text
inverse(S) × inverse(OFF_CM2) ≈ diag(1/g)
```

亦即主要剩下逐通道增益，而非一般相機校色會有的跨通道混合。這是「刻意近似繞過顯色校正」的有力線索，與官方定位和 identity look/tone 相互吻合。

注意：這不是對所有白平衡、色適應、雙光源插值、Resolve 處理或 RAW 像素來源的完整模型；也不表示 fp 感光元件的真實可記錄色域只有 Rec.709。從矩陣推得的是標籤所描述的基底，不是光譜量測。

## 為何仍可能不適合直接作為中性輸入描述

[Adobe DNG 1.7.1 規格](https://helpx.adobe.com/content/dam/help/en/camera-raw/digital-negative/jcr_content/root/content/flex/items/position/position-par/download_section_733958301/download-1/DNG_Spec_1_7_1_0.pdf) 的 ColorMatrix 定義是校準光源下 XYZ 到 reference camera native space 的關係；look 與 tone 有另外的 profile 標籤。

「不套風格」與「不作相機顯色校準」不是同一件事。如果 OFF 的 RAW 仍是未經相應跨通道轉換的感光元件訊號，而 CM 卻以近似 Rec.709 基底描述，則一般解碼器即使忠實讀取標籤，也可能得到不是中性校準結果的畫面。這是一個需要驗證的條件推論，不是已查明的韌體缺陷。

既有 A/B 和 TIFF 實驗已支持目前 Resolve 路徑對 ColorMatrix 的變動有反應；它們不能證明原矩陣色準、全部 DNG profile 標籤支援程度，或 SIGMA 與 Blackmagic／Atomos 的內部設計約定。

## 下一步與不應下的結論

- C normal-matrix-only、D Adobe-CM-only 是候選比較，不是已驗證的修復。
- 要用已知光源、色卡及獨立驗證樣本評估中性輸入映射，並另行確認不同色彩模式的 RAW 路徑。
- 若想保留目前 OFF 的觀感，可把輸入校準與創作 look 分開，而不是把「長得像 fp」當作 ColorMatrix 準確的證據。
- 只換 metadata／使用線性矩陣並不必改變 RAW 像素或把線性訊號改成 log。
- 尚無本次證據支持「OFF 本來就是 BMD Gen1／V-Gamut、只是標籤漏寫」；也沒有足夠證據認定這是一個開發到一半而被放棄的功能。
