# OFF 以外模式與可交付的色彩流程

2026-09-23。這份補充區分：相機渲染外觀、DNG 標準 profile 標籤、Sigma 私有設定，以及實際 RAW 像素。它不是已完成的色度校準。

## 新確認：非 OFF 共用基礎 DNG profile

在 Ver.5.02 的已檢查 writer 中，ColorMatrix1/2、ProfileHueSatMapData1/2、ProfileToneCurve 只分 OFF 與非 OFF 兩組，不是每種創作模式各一套。

實拍靜態 DNG 交叉檢查：

- `_SDI0010.DNG` = OFF。
- `_SDI0011.DNG` = PowderBlue。
- `_SDI0012.DNG` = TealAndOrange。
- `_SDI0013.DNG` = Standard。

後三者的上述五個標準 DNG tag payload 全部逐位元組相同，並非只是數值近似。兩張額外樣本 `_SDI5625.DNG`（PowderBlue）、`_SDI5626.DNG`（OFF）亦符合相應分組。這些樣本是 still DNG；與 CinemaDNG 的關聯來自已檢查的共同標籤 writer 及原始 cDNG 樣本，不應表述成已拍攝全部模式的 cDNG 對照。

非 OFF 基礎 profile 包含：

- normal 雙光源 ColorMatrix，仍包含該機身的 CameraCalibration 正規化。
- 每光源 72 組 HSV 控制點，71 組不是 identity；所以不只是增加一個全局飽和度。CM1 對應表的 hue shift 範圍 -20 至 +10 度，CM2 表為 -20 至 +4 度；飽和度與明度亦有比例調整。這些是表內控制點範圍，不代表每個實拍像素都改動這麼多。
- 共用的非線性 ProfileToneCurve，128 組座標。例如 x≈0.303 對應 y≈0.521，與 OFF 的 x=y 不同。這是顯影指示，不是把曲線直接寫進 RAW 像素。

OFF 則使用專用矩陣、identity HueSatMap 與 identity tone curve。

## 來源定位

檔案：`/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c`。

- ColorMatrix 選擇：`FUN_c02c4a50`，123706 行起。
- HueSatMap 寫入：`FUN_c02c4d40`，123833 行起。
- ToneCurve 寫入：`FUN_c02c4e80`，123884 行起。
- writer 物件的 profile 表指標來自 `FUN_c02d73e8`，136461 行起，回傳常數表 `0xC0B40074`。
- ROM HueSatMap base `0xC0B42760`、ToneCurve base `0xC0B434E8`；實拍 tag payload 與 writer 選取的 ROM payload 一致。
- 模式→profile ID：`FUN_c02c4228`，123340 行起；使用者模式的 ID 透過 `FUN_c02c9928`／`FUN_c02c9980` 寫入私有 group 8 的 tag，不能把這個 ID 表誤認為標準 DNG HueSatMap／ToneCurve 的逐模式選擇表。

已渲染外觀的 Vivid、Neutral、Cinema、Teal & Orange 等差異，屬於機內渲染／認得 Sigma 私有設定的顯影流程；只讀取上述共用標準 profile 並不等於重現完整機內 look。本次沒有證明 Resolve 逐項使用所有私有或標準 profile tag；目前直接 A/B 實驗只證明 ColorMatrix 變更有作用。

## 官方手冊的範圍

[SIGMA fp FW5.0 手冊](https://www.sigma-global.com/en/support/download/fp_Manual_FW_Ver.5.0_EN.pdf)，印刷頁 94–96：說明不同色彩模式、DNG 可在 Sigma Photo Pro 改模式，且 CinemaDNG 的色彩模式效果只用於機內觀看。

「不把創作 look 烘焙進 CinemaDNG」不可直接擴張成「OFF 與非 OFF 的 metadata 完全相同」：實際 writer 與檔案已顯示兩者的基礎 profile 不同。跨模式 RAW 像素處理是否完全一致仍須進一步驗證，不能只由 metadata writer 推定。

## 建議方案

1. 先驗證 C：保留 OFF 的 identity 色彩表／曲線，只換回 normal ColorMatrix。它是合理的低風格干預候選，不是已證實的中性校準。與 A、D 在固定解碼設定、As Shot 白平衡下比較；本輪 TIFF 足夠判讀反應。
2. 用已知照明下色卡、灰階、膚色／獨立樣本驗證候選的色準、白平衡行為與曝光穩定性。至少涵蓋日光與鎢絲光；不能保證雙光源矩陣能完美處理所有窄頻 LED。
3. 若驗證通過，製作只處理副本的 metadata 預處理器：辨識機型、韌體／標籤條件、機身校準與光源，記錄修改與 RAW hash；不得將本機身的一組數值無條件套到所有素材或其他機身。
4. 固定 Resolve 解碼與色彩管理模板，確認中途沒有不可逆裁切或重複轉換；將已校準的線性輸出轉入 DWG／Intermediate 或 ACES 工作流程。這個標準空間轉換不能取代前面的相機校準。
5. 把 SIGMA 創作 look 做成獨立、可關閉且標明輸入空間的層。調色師不再猜 native gamut，只需使用已驗證模板。若要跨軟體穩定交接，可額外輸出明確記錄色彩空間的中間素材，並保留原始 RAW。

若完全不想處理 DNG 副本，也可在固定解碼路徑之後製作等效 DCTL 修正；但需考慮白平衡／雙光源插值，而且無法挽回 RAW 解碼階段已裁切的數值。因此現階段優先驗證 metadata 路徑，不先交付萬用 LUT。

本次未更改任何原始素材、相機、Resolve 專案或既有專案外的研究筆記。
