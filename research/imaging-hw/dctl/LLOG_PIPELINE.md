# fp CinemaDNG → L-Log（DaVinci Resolve）

2026-10-23。目標：fp 的 cDNG 選用原廠矩陣、BF 矩陣或自訂矩陣，在 Resolve 裡轉成 L-Log，之後就能直接套 L-Log 的 LUT。

## L-Log 是什麼（Leica《L-Log Reference Manual》V1.9）

- 色域：**ITU-R BT.2020**，D65（SL Typ 601 例外，用 BT.709）。沒有另外的「L-Gamut」。
- 曲線（LSR = 線性場景反射率，0.18 = 18% 灰）：
  - LSR ≤ 0.006：`8·LSR + 0.09`
  - 其他：`0.27·log10(1.3·LSR + 0.0115) + 0.6`
- 18% 灰 = 0.4353（10-bit 445，約 44 IRE）；黑 = 92；L-Log 白限 LSR 23.3 = 1023。H.264/H.265 用全範圍，ProRes 用視訊範圍。
- 驗算：`SIGMA_fp_to_LLog.dctl` 的公式和手冊表 1 的 8 個點，10-bit 全部相同；12-bit 有兩點差 1（手冊自己的捨入）。把 c 改成 0.28 的突變會被抓到。

**和 BF 對照（2026-10-23 解開，10-24 補完）**：BF 在 L-Log 模式下關掉 Tcd 色調表，改用一條 49 點的 gamma 折線，前段的 Knee／Deknee 互逆，所以進曲線的是線性資料。
這條折線等於 `1023·L-Log(LSR) − 92`，輸入 16383 對應 LSR 23.3，49 點都在 ±2 碼以內，所以這份 DCTL 的曲線和 BF 機內是同一條。
色域這一段 BF 用自己的 CC1 矩陣加上 Multi-Axis 的固定色度增益，和 DNG 矩陣算出的 2020 對不上；細節在 `sigma_bf/COLOR_ANALYSIS.md`「BF 的 L-Log 實作」。

## 流程

```
fp cDNG ──cdng_profile.py──► 換矩陣、拿掉 HueSatMap/ToneCurve（RAW 位元組不動）
        ──Resolve Camera RAW 解碼──► Rec.2020 Linear（或 RCM 的 DWG/Intermediate）
        ──SIGMA_fp_to_LLog.dctl──► L-Log / BT.2020
        ──任何 L-Log LUT──► Rec.709 等
```

### 1. 選矩陣

```
python3 tools/cdng_profile.py <cDNG 資料夾> <輸出資料夾> --matrix fp     # 原廠矩陣
python3 tools/cdng_profile.py <cDNG 資料夾> <輸出資料夾> --matrix bf     # BF 矩陣
python3 tools/cdng_profile.py <cDNG 資料夾> <輸出資料夾> --matrix my.json
```

- 做法：原檔照抄，在檔尾附一個新的 IFD0，再把檔頭指過去；每個檔案都會檢查影像 strip 的 SHA-256 前後相同，不同就不寫。
- 預設拿掉 `ProfileHueSatMap` 與 `ProfileToneCurve`：fp 在 cDNG 裡把色彩模式的 look 存在這兩個欄位，留著就不是場景線性，套 log 會錯。真的要保留就加 `--keep-look`。
- `my.json`：`{"cm1": [9 個], "cm2": [9 個], "illum1": 17, "illum2": 21}`，DNG 慣例（XYZ → 相機），已經把機身校正乘進去。
- 已測：fp 單幀，exiftool 讀回矩陣與 ProfileName 正確；validate 只有原檔本來就有的 4 個小警告；改掉 strip 裡 1 個位元，檢查會擋下來。

### 2. Resolve 設定（不用色彩管理）

- Project Settings → Color Management：**DaVinci YRGB**。
- Camera RAW → CinemaDNG：Decode using = Project（或在 clip 上設）；**Color Space = Rec.2020**、**Gamma = Linear**；White Balance = As Shot。
- 節點：OpenFX **DCTL** → `SIGMA_fp_to_LLog`，Input = **Rec.2020 Linear**。
- 曝光：拍一張灰卡，調 **Exposure (stops)**，讓灰卡在波形上落在 **44%**（445/1023）。這一步決定 L-Log 的 LUT 會不會偏亮或偏暗。
- 後面接 L-Log 的 LUT（例如 Leica 或 SIGMA 發的 L-Log → Rec.709）。

### 2'. 用色彩管理（DaVinci Wide Gamut / Intermediate 時間軸）

- DCTL 的 Input 改成 **DaVinci WG / Intermediate**：先轉回線性，再轉 BT.2020（DWG → 2020 矩陣由兩組原色計算，D65），最後套 L-Log。
- 輸出要當 L-Log 看的話，節點後面不要再讓 RCM 做輸出轉換（Output Color Space 設成跟 Timeline 一樣，或用 Color Space Transform 繞過）。

## BF 模擬版：`SIGMA_fp_BF_LLog.dctl`（2026-10-24）

fp 和 BF 是同一顆 IMX410，所以不經過 DNG 矩陣，直接照 BF 機內的順序算：

```
fp cDNG ──cdng_profile.py --matrix native──► 每幀 ColorMatrix = diag(AsShotNeutral)·(XYZ→2020)
        ──Resolve Camera RAW：Rec.2020 / Linear──► 白平衡後的相機 RGB（「Rec.2020」只是載體）
        ──SIGMA_fp_BF_LLog.dctl──► CC1 → 裁切 0..23.3 → L-Log 曲線 → BT.2020 YCbCr 色度 ×增益
```

- CC1 = `[[249,6,1],[16,285,-45],[31,-65,290]]/256`、曲線、YC 係數都是 BF 韌體原值。
- **BF chroma gain** 預設 1.25：韌體的 Multi-Axis 色度增益是 320，假設 256 = 1.0 才得到 1.25，**這個單位沒有驗證**。
  套用位置（L-Log 曲線之後、在 YCbCr 上）也是依 Milbeaut R2Y 的慣例推的。
- **Clip like the ISP**：照硬體把 CC1 輸出裁到 0..23.3（14 bit），最後裁到 0..1。關掉就保留超出範圍的值。
- 曝光一樣用灰卡定在 44%（445）。
- 已驗：依 DNG 規範模擬解碼，`--matrix native` 的檔案解出來正好是 `相機 RGB ÷ AsShotNeutral`（白點 D65、對角矩陣、誤差 0）；
  exiftool validate 和原檔一樣只有 4 個小警告；Python 參考算出灰 445.3、黑 92.1、白限 1023.0。
- 沒驗：Resolve 解 cDNG 是否完全照 DNG 規範（尤其白點換算）、fp 與 BF 的濾光片是否相同。沒有 BF 實拍，所以只能說「照 BF 的算法」，不能說「和 BF 拍出來一樣」。

## 還沒驗證的地方

- Resolve 解碼 cDNG 成 Linear 時，HueSatMap/ToneCurve 到底有沒有被套用，沒有實測；拿掉它們就不用管這件事。
- Resolve 的 Linear 解碼有沒有固定增益（舊筆記：DWG 流程裡「感光元件歸一化 × 2.124」）。這只影響曝光，用灰卡定 44% 就會抵消。
- 動態範圍：fp 的白點在 L-Log 曲線上落在哪裡（例如 ISO 100 時約 +3~4 EV），要拿實拍確認。超過感光元件白點的部分是 Resolve 的高光重建，不是真資料。
- 這是 L-Log 規格，不是「BF 機內 L-Log」的逐位元複製。要對 BF 實拍，得先解開 BF 的色調表輸入編碼，或拿 BF 的 L-Log 樣片對照。
