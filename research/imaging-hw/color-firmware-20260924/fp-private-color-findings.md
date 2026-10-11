# fp 私有色彩矩陣：離線韌體與實拍檔交叉核對

2026-09-24。全部工作在既有檔案上完成，未連線、讀取或修改相機。

## 本次新增結論

1. **不用色卡也能還原相機的設計行為。** 現有 cDNG 與靜態 DNG 已帶有多模式私有矩陣表，不必先做 live RAM dump。
2. **OFF 的特定 RGB 矩陣階段確實是 identity**，不只是標準 ColorMatrix 的數學猜測：利用 A 的私有 tag 0x33、0x34 反算，與 identity 最大差約 4e-8。
3. **一般模式的私有矩陣是另外一層 look／渲染資料**，不能把它直接當成 DNG ColorMatrix，也不能因為有兩組 3×3 就全部相乘。其座標基底、前後白平衡與 tone 階段必須對上。
4. 找到明確的標準基底常數：linear sRGB→XYZ D50，以及 Adobe RGB→linear sRGB。所以韌體並非只有無法辨認的「native gamut」數值。
5. 這些發現仍不是感光元件光譜響應或絕對色準證明；但足以推進有根據的輸入校準／原廠 look 分離，不需等待色卡才開始。

## 16 組矩陣全部隨檔寫出，不是只写當前模式

來源 `/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c`：

- `FUN_c02c5440`，124134 行：選取 mode 對應的 9 個有符號 short，按第一列總和正規化，重排成 3×3 float。
- `FUN_c02c57c0`，124315 行附近：依序建立 16 組上述矩陣，寫入私有 tag `0x124`。
- `FUN_c02c55a0`，124206 行：建立另一組亮度／色差結構的矩陣，含模式參數與兩個色差增益。
- `FUN_c02c5948`，124340 行附近：同樣寫出 16 組至私有 tag `0x129`。

兩組表的模式順序均為：

`0x23, 1, 0, 3, 5, 6, 7, 0xe, 0xb, 0xc, 0xf, 8, 10, 0x24, 0xd, 0x24`。

Standard 對應模式 0、表內第 3 組；OFF 對應 0x24、第 14 與 16 組。

比較 `A_original.DNG` 和現有 `_SDI0010`～`_SDI0013.DNG`，兩個私有表分別全部相同。**原因是每個檔案都攜帶完整 16 模式表，不能解讀成切換模式完全無效。**

tag 0x124：

```text
Standard = [1.234375 -0.1796875 -0.0546875;
            0         1.26171875 -0.26171875;
            0        -0.10546875  1.10546875]
OFF = identity
```

tag 0x129 的第一列固定為 `[0.298828125, 0.586669921875, 0.114501953125]`，後兩列為零和色差係數；它明顯不是 XYZ↔sensor calibration 類型的矩陣。OFF 在此並非 identity，因為 RGB↔亮度／色差的必要座標轉換不等於創作 look。

## 更強的獨立證據：當前矩陣 tag 0x34

`FUN_c02cc130`（128537 行）及另一 writer `FUN_c02cbe50` 讀取當前 render 物件中 RGB 係數，乘上已知基底轉換與私有白平衡 tag 0x33，最後存成 tag 0x34。

**反編譯 C 漏掉了最後的 3×3 反矩陣與 float 轉換。** 直接檢查 `seg0_c0000000.bin` 的 ARM 指令 `0xC02CC2D8..0xC02CC3CC` 可見 cofactor、determinant、除法及 float stores；不能只照反編譯 C 的有缺陷 stack 變數解讀。

一般分支的公式為：

```text
T_private_0x34 = inverse(S_XYZD50 × M_selected × diag(WB_private_0x33))
```

在 Adobe RGB 分支，`M_selected` 前另乘 AdobeRGB→sRGB 的矩陣。另有一個模式值為 5 的固定常數分支，本次未賦予其外部語意。

從初始化 data segment `/Users/dido/Developer.localized/SIGMAfp_re/out/seg1_c2ef6e00.bin`，按基址 0xC2EF6E00 解析 double：

```text
0xC2F19CEC = linear sRGB → XYZ D50
[0.4360747 0.3850649 0.1430804;
 0.2225045 0.7168786 0.0606169;
 0.0139322 0.0971045 0.7141733]

0xC2F19CA4 ≈ Adobe RGB → linear sRGB
[1.398354843 -0.398353701 -0.0000018439;
 0.000000340005 0.999998705 0.000000925335;
 -0.000000240954 -0.042929252 1.042929092]
```

注意 MAIN 容器不能在這段直接用 VA−0xC0000000 當平坦映射；須使用 seg1。初始化值不是任意時刻的 live RAM 證據，但 A 實際 metadata 的精確重建提供獨立佐證。

對 A（sRGB、OFF）反算 `inverse(S) × inverse(T) × inverse(diag(WB))`，得到 identity，最大絕對誤差約 4e-8。這是**該次渲染矩陣設定**的證據，不表示 cDNG RAW 像素已經通過此渲染矩陣。

其餘四張 still 是 AdobeRGB(1998)。反算結果落在 1/512 格點上；非 OFF 包含大於 2 的係數。源碼 `FUN_c0107548`／`FUN_c01073a0` 有 `&0x7ff` 的硬體係數包裝，writer 則以 32-bit signed 讀取。故需要還原 11-bit signed 語意；**tag 0x34 不能直接作 IDT 使用**。此差異不證明真正的像素渲染錯誤：ISP 能按自身位元格式解讀。Standard 還原符號後再轉回 sRGB，與 tag 0x124 的 Standard 表近似（含兩套 basis 的量化差異）。

## 對後續校準方案的意義

- DNG normal CM 是 XYZ→reference-camera 描述；私有 0x124 是選定渲染階段的 RGB matrix；0x129 是亮度／色差處理。不能把三者視為同座標空間的可替換矩陣。
- **尚未證明 `inverse(normal CM)` 的輸出在相機裡接到 0x124 的前端。** 因此 normal CM × Standard 私有矩陣可能重複計入顯色／look，不宜現在合成「更準」的校準。
- 正確用途是兩條分開：以 normal CM 作線性輸入候選；以私有矩陣、profile、tone 及成對 JPEG 還原可關閉的原廠 look。可以用現有素材驗證是否重現原廠處理，不能把重現 JPEG 當作客觀色準。
- 下一個有價值的純離線步驟是追查 `FUN_c02cfcf0` 與其上游 vtable 的 render 基底來源，並把 CameraCalibration、每拍 WB、創作 RGB matrix、tone 順序分開。比較 Sony 韌體應優先比結構／輸入輸出定義，不直接搬矩陣。

## 舊筆記更正提示

本次未修改父專案研究筆記。`COLOR_SCIENCE.md` 中 RGBLMAT MMIO 的舊地址不準確：診斷列印程式將 `0x30115000` 標為 IGAMMA，RGBLMAT 為 `0x30115100..0x3011513c`（`blk_c01.c` 約 50117–50123 行）。亦不應沿用「私有 matrices 均為 per-unit calibration」或「沒有 hue LUT」的舊概括。

所有數據、來源 hash、逐檔矩陣及反算結果見 [fp-private-matrix-audit.json](./fp-private-matrix-audit.json)；可用同目錄 `fp_private_matrix_audit.py` 重現。
