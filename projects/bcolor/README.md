# bCOLOR：在 fp 上套 BMCC 6K 的色彩（SIGMA fp 5.02）

2026-10-02 建立。由 [`projects/rawview`](../rawview/README.md) fork，**離線建置、模擬通過，尚未上機、未寫卡**。

COLOR 選單第 17 列「bCOLOR」：LCD 監看改成 Blackmagic Cinema Camera 6K 的色彩流程，錄下的 CinemaDNG 同時寫入對應的 ColorMatrix。
錄影增益、12-bit CinemaDNG 限定、關機記憶、回放還原，全部沿用 Raw View。

## 與 Raw View 的關係（使用者 2026-10-02）

- **兩個產品目前不相容，不能同卡。** 使用同一批 hook 位址與第 17 列；關機存檔也都用色彩值 0x10–0x17，
  換卡時上次的狀態會被另一個產品照自己的意思解讀（lat、con 兩個位元）。UI 相容規則以後再做。
- 程式碼盡量沿用 rawview：檔名（`rv_*`、include）不改，差別集中在資料與 `rv_resident.S` 的幾行。
  對照用 `diff -r ../rawview/build build`。

## 色彩流程

BMCC 的來源與驗算見 [BMCC 6K 研究入口](../../bmcc6k/README.md)。

```
fp 白平衡後的相機 RGB ─①校準→ XYZ D65 ─②→ BMWG 線性 ─③LUT 矩陣→ 709 線性 ─④BMCC tone→ LCD
                       └──────────── fp 硬體的 3×3(RGBLMAT) ────────────┘      └ tone 表 ┘
```

| 步驟 | 內容 | 來源 |
|---|---|---|
| ① FC | fp 自己的校準（非 OFF 模式 DNG 的 CM2，同 Raw View 飽和度 +0.2） | `rv_color.cam_to_709` |
| ① BC | **BMCC 6K 的 ForwardMatrix2**（D65）：把 fp 的 RGB 當成 BMCC 的感光元件 | datapack field 7 |
| ② | XYZ → Blackmagic Wide Gamut Gen5（原色與官方一致） | `bc_bmcc.bmwg_to_xyz` |
| ③ | 原廠 33³ LUT 在中低飽和區拆成 3×3 + 1D，擬合出的 3×3 | `bc_bmcc.lut_matrix` |
| ④ | LUT 中性軸：18% 灰以上 s 檔 → Gen5 Film → LUT 對角線 | `bc_bmcc.tone` |

datapack 校準欄位已由數值驗算確認身分：field 4/5 = ColorMatrix1/2（StdA 2856K / D65，XYZ→相機），
field 6/7 = 白平衡後相機 → XYZ D65（以轉置存），field 10/11 = 同一組經 CAT02 轉到 D50。
`CM2 · FM2` 是對角矩陣 diag(0.419, 1, 0.777)，也就是 BMCC 在 D65 下的相機中性值。

③ 的擬合：Video 的 3×3 與色度上的 BMWG→709 只差 0.02 以內，中低飽和區 3×3 + 1D 重現原廠 LUT 平均誤差 0.0012、95% 0.0033（顯示值）；
Extended Video 平均 0.0030、95% 0.012。**高飽和色的軟壓縮與 Video LUT 的不對稱，fp 硬體的 3×3 + 1D 做不到。**

## 操作

| 控制 | 作用 |
|---|---|
| COLOR 第 17 列 bCOLOR | 開啟（CinemaDNG 12-bit 才生效，同 Raw View） |
| 右側框 FC / BC | 校準：FC = fp 自己的，BC = BMCC 6K 的。框顯示 −5 / +5，字形換成 F/B + C |
| AEL 對比 0 / +0.2 | BMCC 顯示轉換：0 = Film → Video，+0.2 = Film → Extended Video |
| AEL 飽和度 | 鎖 0（拉動會被拉回） |
| AEL 清晰度 | 鎖 0（同 Raw View） |

錄下的 CinemaDNG：

| 狀態 | ColorMatrix1 / 2 |
|---|---|
| bCOLOR 不生效 | 原廠 OFF 常數，與一般錄影相同 |
| FC | 原廠非 OFF 常數（fp 自己的校準） |
| BC | BMCC 6K 的 CM1（StdA）/ CM2（D65） |

韌體照常再乘逐台的 makernote P。DNG 只能帶色度校準，BMWG／Film／LUT 的外觀要在 Resolve 自己套（或用 Resolve 的 Blackmagic Design 色彩空間）。
RAW 像素不變。

### 削波時的顯示值

和 BMCC 一樣，每個 ISO 只移動曝光尺度，曲線固定，所以**感光元件削波不一定是白**：

| ISO | 中灰以上 W 檔 | Video | Extended |
|---|---:|---:|---:|
| 100 | 3.09 | 0.822 | 0.816 |
| 200 | 4.09 | 0.921 | 0.888 |
| 400 | 5.09 | 0.969 | 0.934 |
| 800–1600、6400 以上 | 6.09 | 0.987 | 0.963 |
| 3200 | 5.42 | 0.977 | 0.945 |

中灰：Video 0.406、Extended 0.411（與 BMCC 相同）。

## 檔案

| 檔案 | 內容 |
|---|---|
| `build/bc_bmcc.py` | **新增**。BMCC 資料的唯一定義：LUT 讀取與四面體內插、tone、LUT 矩陣擬合、datapack 校準 |
| `build/rv_color.py` | LCD 矩陣四組 `bc_table(lat \| con << 1)` |
| `build/rv_dngcm.py` | DNG 三級 `bc_blob()`：原廠 OFF / FC / BC |
| `build/rv_tables.py` | tone 表：四組（lat 不影響曲線，組 0 = 1、2 = 3，沿用 rawview 的選表） |
| `build/rv_resident.S` | magic `BCL1`；LCD 矩陣以 lat \| con << 1 選、DNG 以 eff ? lat + 1 : 0 選；飽和度鎖 0；框字形 F/B/C |
| `build/build_bcolor.py` | 建置（banner `fpSup-…-bCOLOR…`） |
| `tools/rv_icon.py` | 第 17 列圖示「bCOLOR」（寬度限 64 px） |
| `tools/rv_card.py` | host 工具：`lat FC\|BC`、`con 0\|1`；找 `BCL1` |

launcher（`rv_launch.S`）、增益、選單、存檔、回放的程式與 rawview 相同。

## 建置與測試（2026-10-02）

```sh
cd build
python3 -B build_bcolor.py --out out/dev            # 開發卡(含 USB shell)
python3 -B build_bcolor.py --fs2 --out out/dev-fs2  # 開發卡 + Fast Start 3(FPSUPUI/ 要一起放)
python3 -B build_bcolor.py --release --out out/release
python3 -B -m unittest test_bcolor_build test_bcolor_image
python3 rv_tables.py                                 # 整數表 vs 浮點:最大 8 LSB
```

- 測試：build 27 項（含新增 `BMCC`：tone 與歸檔四面體取樣逐點相同、LUT 跨通道格點、校準恆等式、DNG 三級）、整卡模擬 28 項。
  修改過的語意（矩陣選擇、DNG 選擇、飽和度鎖 0、框字形）都把對應測試改成 bCOLOR 的預期；
  常駐的四處修改各故意改壞一次，測試都抓到。
- blob 23,932 B（launch 4,436、常駐 6,020、表格 13,476）。
- 產物 SHA-256（僅供追溯）：

  | 卡 | fpSup.BIN | AutoRun.txt |
  |---|---|---|
  | out/dev | `83de8cdb…` | `7e4cc438…` |
  | out/dev-fs2 | `07c1efc1…` | `35a3141f…` |
  | out/release | `143b5e43…` | `46d08f71…` |

## 未做／待驗

- **未上機。** 上機時照 SUP_BUILD_RULES §6：開機、不錄影、關機、插卡再開，重複約十次；疊在上一張卡（尤其 Raw View）之上開機。
- 圖示與框字母未在實機看過（字母用原廠 `font_menu_LB_id_*`，同 Raw View 的 S/G/A 做法）。
- BC 是「把 fp 當成 BMCC 感光元件」：兩台的濾鏡組不同，白平衡後 fp→BMCC 相機 RGB 的轉換非對角項達 0.29，所以 BC 的色相不是 BMCC 實拍的色相，而是 BMCC 校準套在 fp 資料上的結果。要讓 fp「像 BMCC」，色度上準的是 FC。
- AEL 選單頁的「飽和度」數字仍會顯示（鎖 0）；沒有改名。
- 未加入 fpSup-Merge（catalogue）、未發布。
