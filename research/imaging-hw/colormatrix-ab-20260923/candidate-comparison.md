# SIGMA fp ColorMatrix 候選比較

這次比較 A、C、D；B 是前一輪刻意放大色度的探測檔，不是校色候選。

- `A_original.DNG`：原始 fp OFF CinemaDNG，未修改。
- `C_firmware_normal.DNG`：同一張 RAW，僅將 ColorMatrix1/2 換成 fp 韌體的 normal 矩陣，依韌體方式套用該機身校準、截斷至分母 10000。結果亦與同機身的實拍 normal 矩陣逐位元組一致。
- `D_adobe_cm_only.DNG`：同一張 RAW，僅複製 Adobe「SIGMA fp Camera OFF」的 ColorMatrix1/2，不另套用機身校準。

三張的 RAW 像素、AsShotNeutral、黑白位準、曝光、光源標籤和其他資料完全相同。這是矩陣方案比較，不能只憑較飽和或較討喜判定色準。

## 在 Resolve 比較與輸出

沿用前一輪相同專案、RAW 輸出色域／Gamma、曝光及節點設定；三張都選 **As Shot 白平衡**。不要為了顯示相同數字而手動鎖定相同 Kelvin／Tint：矩陣改變可能影響軟體推算出的色溫，這會額外引入變因。

使用原始素材，避免代理檔、Optimized Media 和舊快取；不單獨為其中一張加 LUT、CST、自動校色或色彩調整。三張以完全一致的設定輸出 TIFF 即可進行這輪比較，建議命名 `A.tif`、`C.tif`、`D.tif` 放在此目錄。

## 解讀限制

C 保留 OFF 的其他 profile 資料，所以**不等於完整 normal 色彩模式**。D 沒有複製 Adobe 的 ForwardMatrix、ToneCurve 或其他 profile／look 資料，所以**不等於完整 Adobe 解碼結果**；Adobe 矩陣的機身校準適用方式仍需額外驗證。

產生程序確認差異只存在於兩個既有 72-byte ColorMatrix payload 內，RAW strip 雜湊一致，LibRaw 解壓後的 Bayer 陣列逐值相同，且各檔可成功解碼。詳見 `candidate-verification.json`。這些檢查證明檔案完整及測試範圍受控，不證明候選矩陣已通過 Resolve 實測或實際色彩校準。

後續要判定哪個方案較準確，仍需已知照明下的色卡、灰階和獨立場景，而不是只比較本張室內畫面。
