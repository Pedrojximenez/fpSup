# ISP／錄影路徑的尺寸規則（給 readout_plan.py 用）— 2026-10-22

從 res-lab、open-gate、imx410-lab 整理出來，只做離線閱讀，沒有碰相機。
證據等級：**[M]** 上機量過、**[C]** 程式碼或韌體反組譯、**[I]** 推論。
路徑縮寫：`OG/` = `projects/open-gate/`，`RL/` = `projects/res-lab/`，`IL/` = `projects/imx410-lab/`。

## 0. 先釐清名詞（res-lab 裡混用最嚴重的地方）

| 名稱 | 意思 | 寫在哪 |
|---|---|---|
| window（視窗） | 感光元件的讀出光柵，也就是模式的 ro_w × ro_h | PARAM +0xF4/+0xF8，畫布 c[25]/c[26] |
| rec（記錄矩陣／畫布） | 實際寫進 DNG 的 ImageWidth × ImageLength | PARAM +0x00/+0x04（+0xDC/+0xE4） |
| act（有效輸出） | DNG 的 DefaultCropSize，也就是使用者看到的「解析度」 | PARAM +0x24/+0x2C |
| 錄影 RWZM | Z 值，單位是 x1024，輸出 = 輸入 × 1024 / Z | H 在 +0x64，V 在 +0xD4 |
| 預覽 RWZM | 另一組欄位，跟錄影那組互不相通 | H 在 +0x60，V 在 +0xD0 |

例子：OG3K 的 rec 是 3024×2010，act 是 3008×2000。OG2K 的 rec 是 2016×1344，act 是 2000×1334。
原廠 UHD 的 rec 是 3856×2170，act 是 3840×2160；FHD 的 rec 是 1936×1090，act 是 1920×1080。
**注意：readout_plan 的 `RES` 預設值（2016、3024）是 rec 寬，3840 卻是 act 寬，兩種混在一起用。**

## 1. 輸出（DNG）寬高

| # | 規則 | 證據 | 來源 |
|---|---|---|---|
| 1.1 | `rec_w = ((window_w // bin_h) * 1024 // Zh) & ~15`，`rec_h = ((window_h // bin_v) * 1024 // Zv) & ~1` | [C]，同時跟原廠 78 個影片 profile 逐欄吻合 | `OG/build/rl_v3.c:121`、`OG/build/sl_menu/sl_modes.c:1400`、`OG/build/imx410_profile.py` |
| 1.2 | act_w 必須是 16 的倍數，act_h 必須是偶數 | [C]（producer 會拒絕不合規的值）＋[M]（res-lab 錄過 992×360、1504×1006） | `rl_v3.c:302-303`、`sl_modes.c` 的 W_STEP=16、H_STEP=2；`RL/validation/20261009-formula-audit/RESULTS.md` |
| 1.3 | 留邊：`act_w + 16 ≤ rec_w`，`act_h + 10 ≤ rec_h` | [C] producer 強制；原廠是慣例（78 列有留，28 列沒留，例如 p365 的 4096×2160） | `rl_v3.c:114,123`；`OG/notes/IMX410_FULL_DESIGN.md §3.2` |
| 1.4 | DefaultCropOrigin = ((rec−act)/2, (rec−act)/2)，原點可以是奇數 | [M] OG3K 是 (8,5)，3872×2182→3840×2160 是 (16,11) | `IMX410_FULL_DESIGN.md §3.1` 及約 2976 行 |
| 1.5 | 有裁切時：Z 由「裁切後的讀出」算出，rec 仍保留整個視窗，act 是置中的一塊 | [C] | `sl_modes.c:1294 zoom()` 及 1400 行；`formula-audit/RESULTS.md` |
| 1.6 | 寫入器每列 byte 數以整數截斷計算，寬度沒對齊會**默默錯位**（沒有任何遮罩攔下來）。各位深的寬度粒度：8-bit 是 4，10-bit 是 16，12-bit 是 8，14-bit 是 16，16-bit 是 2。統一取 16 | [C] FUN_c0630e90 → 0x3018220C/2214；原廠 act 寬 118/118 都是 16 的倍數 | `IMX410_FULL_DESIGN.md §3` |
| 1.7 | 高度：韌體在 vbin≠1 的路徑上會主動把 y 遮成偶數（共 12 處 `&0xfffe`），給奇數會被改成偶數，結果是位移而不是損毀 | [C] | `IMX410_FULL_DESIGN.md §3.1b` |
| 1.8 | act 高「8 的倍數」**不是**規則（OG2K 的 1334 就錄得出來） | [M] | 同上 |
| 1.9 | 上下限：producer 要求 act ≤ 6064×4040，rec ≤ window/bin；下限沒有證據（producer 只要求至少 16×2 加邊）；矩形座標是 ushort | [C] | `rl_v3.c:301-303`、`sl_modes.c snap()` |
| 1.10 | 錄影位深：res-custom 只收 8／10／12；14-bit 可以算，但匯出會被拒絕 | [C] | `RL/README.md:284`、`RL/validation/20261012-rcd-bitdepth/RESULTS.md` |
| 1.11 | 每格檔案大小 ≈ rec_w × rec_h × bits / 8 + 約 79 KB 檔頭 | [M] M12 1008×672 12-bit 每檔 1,095,168 B；UHD 10-bit 為 +79,248 | `RL/validation/20261013-m12-240-native-dma/RESULTS.md`、`OG/notes/OG3K_8BIT_10BIT_FALLS_BACK_TO_UHD.md` |

## 2. RWZM

| # | 規則 | 證據 | 來源 |
|---|---|---|---|
| 2.1 | Z 是整數 x1024，所以比例的步進是 1/1024。1023 代表 unity，韌體會夾成 1024 | [C] | `imx410_profile.py RWZM_UNITY_STOCK`；`IMX410_FULL_DESIGN.md §6.2` |
| 2.2 | 只能縮小：zoom() 不會回傳小於 1024 的值，producer 也拒絕 Z<1023。硬體能不能放大沒查過 | [C]（是政策，不是量出來的） | `sl_modes.c:1294`、`rl_v3.c:116` |
| 2.3 | 上限 Z ≤ 16384（16 倍）。這是**規劃器自己訂的範圍，不是硬體極限** | [C] | `formula-audit/RESULTS.md`；`sl_modes.c:1299` |
| 2.4 | 錄影實際用過的 Z：原廠只有 1024、1500、1600；自製的 1536（OG4K）、1792（OG3.5K，外部專案實錄）、2048（M12 AUTO，[M]） | [C]/[M] | `IMX410_FULL_DESIGN.md §12.26`、`imx410_profile.py` 開頭說明、`20261009-recording-formula/RESULTS.md` |
| 2.5 | 兩軸各自獨立（非等向）：錄影可以，M12 AUTO 以 2048/1023 錄過，DNG 正常 | [M] | `20261009-recording-formula/RESULTS.md`（A001-016/018） |
| 2.6 | 不用 binning 時，**預覽**的兩軸縮放必須相同；不同的話，開錄第一秒 LCD 會出現接縫（r77、v11 兩次重現） | [M] | 同上 §v12；`rl_v3.c:128` |
| 2.7 | 有 binning，且 `window × 1024 / (bin_h × Zh) ≤ 2100` 時，預覽的 bin 和 RWZM 必須逐軸等於錄影的（分支 C，Hbin2 抽頭） | [C]＋[M]（M98 hbin3 實錄） | `rl_v3.c:129`；`IMX410_FULL_DESIGN.md §6.2` |
| 2.8 | 繞過：unity（1023/1024）走 Crmf 抽頭，不經過重取樣。OG3K、OG2K 就是這條，量起來沒有條帶 | [C]＋[M]（畫質量測） | `IMX410_FULL_DESIGN.md §6.2`；`fpSup/explainers/rwzm-resampler.html` |
| 2.9 | 畫質（軟規則）：比例 Z/1024 化成最簡分數後，分母 ≤5 就不會出現條帶；分母 16（25/16）會有 16 列週期的橫帶 | 25/16 是 [M]；其他比例是 [I] | `rwzm-resampler.html`（裡面註明「Still open」） |
| 2.10 | 預覽限制：預覽來源寬 ≤ 2100；預覽可見寬 ≤ 2000 且是 16 的倍數；預覽光柵 = 可見 + 16/10，而且不能超出來源（r71 超出會花屏、凍結）；待機可見 ≤ 2000×1334 | [C]＋[M] | `rl_v3.c:132-136`、`imx410_profile.py` |
| 2.11 | CRCT bin：H 可選 1、3、5（純計算版只有 1、3），V 可選 1、3 | [C] | `rl_v3.c:111`、`sl_modes.c snap()` |

## 3. 接收端／BUFA／感光元件視窗

| # | 規則 | 證據 | 來源 |
|---|---|---|---|
| 3.1 | 接收端水平視窗：`0x3010000C` 低半是 END、高半是 START，單位都是 12 px。位置可以任意（0/1200/2400/3060 都量過，相關係數 1.000） | [M] | `IL/notes/IMX410_RULES.md §33` |
| 3.2 | x0 不是 12 的倍數時，原廠程式另寫 `0x300F10C0[19:16] = x0 % 12` 和 `0x300F021C = 12 − 餘數`（mode 10 的 8 → 6072−8 = 6064） | mode 10 是 [M]；任意值是 [C]，未測 | §7、§8、§33；`IL/notes/L7_14BIT.md` |
| 3.3 | BUFA0 會把寬度截到 16 的倍數：12-bit 時 3000 px 變 2992（1122 字）。14-bit 是每 16 px 7 個字，寬度不是 16 的倍數就會截掉最後半個字 | 12-bit 是 [M]；14-bit 是 [C] | §33；`L7_14BIT.md §4` |
| 3.4 | 垂直：感光元件的 `0024/25` 是輸出列數 ÷ 2，所以高度以 2 列為單位；`0022/23` 是起始列，可以任意（誤差 1–3 列）。`0003=1` 開啟視窗 | [M] | §7、§15 |
| 3.5 | 感光元件的高度和接收端的 y 視窗（`0x30100024`）必須一致，否則不出幀 | [M] | §15 |
| 3.6 | 水平裁切不會縮短捲簾，也不會提高幀率；唯一的例外是 11-bit 快速 AD 要做到 HMAX ≤ 360，接收端寬必須 ≤ 4176 | [M] | §33、§31 L2b |
| 3.7 | 感光元件格式寬（`0001`）：6064、5073（18）、4160（2B/2C，接收端用 4176）、4016（03）、3032（h2）、2016/2020（h3） | [M] | §31、§43、§45 |
| 3.8 | ★ **錄影路徑目前不用接收端裁切。** 畫布的視窗 = 模式光柵（c[25]/c[26] = ro_w/ro_h）。res-lab 的「Crop」只是 Z 加上置中的 DefaultCrop。要自訂感光元件視窗就得改模式表（虛擬模式）；S16 有先例，但 OG_MULTIFORMAT R2 還沒解 | [C] | `rl_v3.c:135`；`OG/notes/OG_MULTIFORMAT_CORE_DESIGN.md §5 R2` |

## 4. 幀率與資料率

| # | 規則 | 證據 | 來源 |
|---|---|---|---|
| 4.1 | 錄影格率只能是這幾個：23.98／24／25／29.97／48／50／59.94／100／119.88／239.76／279.72 | [C] | `sl_modes.c rate_fps100` |
| 4.2 | 模式上限 = 72 MHz ÷ (HMAX × (光柵列 + 消隱))，必須 ≥ 17.98 | [C] | `rl_v3.c rl_encode` |
| 4.3 | 超過 60 fps：PARAM +0xB0 = 1。239.76 和 279.72 時預覽改走錄影路徑（預覽縮放 = 錄影縮放、預覽光柵 = act+16/10、0x88=4、0xFC=2.0） | [C]＋[M]（M12） | `rl_v3.c:266`；`RL/validation/20261014-unified-hirate/RESULTS.md` |
| 4.4 | 資料率 = rec × bits × fps（含邊），不是 act | [C] | `sl_modes.c rate_format`；`formula-audit` |
| 4.5 | SD 寫入約 94 MB/s，而 FHD 12-bit 就要 97.2，已經頂到 | [M] | memory `storage-speed-and-fw-benchmark` |
| 4.6 | SSD 卡在 USB 匯流排，約 390 MB/s。實際持續錄過：10-bit M12 239.76p 約 222 MB/s 撐 90.9 s；12-bit 約 262.6 MB/s 只撐 36–40 s 就自動停 | [M] | `RL/RESCUSTOM_STATUS.md §1,§3` |
| 4.7 | 高格率測試要關掉 shell 和 HDMI，開著時請求速率會掉到約 188 fps | [M] | `20261014-unified-hirate` |
| 4.8 | RAW 池有 94 個描述子；原廠檔案層每 64 MiB 或 128 檔才結算一次。所以每格太小（小於約 64 MiB ÷ 94 ≈ 714 KB）時，在結算前就會用完 94 格 | lossless 是 [M]；未壓縮小格是 [I] | memory `lossless-early-stop-94` |
| 4.9 | 279.72 用 4 MiB 批次加 CPU 複製檔頭；239.76 用原廠 DMA 檔頭加 64 MiB 批次（每格 CPU 複製會拖垮 240） | [C]＋[M] | `20261013-m12-240-native-dma` |

## 5. 矛盾與未解（不猜）

1. **12-bit 的寬度粒度兩邊對不起來。** 寫入器 FUN_c0630e90（0x3018220C/2214）算出來是 8，但 BUFA0（0x3018210C/2114）實測截到 16。可能是兩個不同的 BUFA 通道，沒查證。
2. **OG4K 有兩種定義。** OG4K_IMPLEMENTATION 寫的是 RAW 4016×2676、有效 4000×2666、Z=1536；任務說明和 explainer 寫 3840×2560；OG_MULTIFORMAT R4 又說「OG4K DNG 沒有 +16/+10 邊」。
3. **非等向 RWZM 的說法前後矛盾。** IMX410_FULL_DESIGN §12.26 寫「原廠零先例、未驗」，但後來 M12 AUTO 已經用 2048/1023 錄過了，那一段筆記過時。
4. **RWZM 範圍 1024..16384 和「只能縮小」都是政策，** 硬體真正的極限沒量過。
5. **「分母 ≤5 無條帶」只在 25/16 解過，** 3/2 是推論（explainer 自己標了「Still open」）。
6. **SD 速度數字不一致：** 94 MB/s（sdcard test3）和「SD 約 241 MB/s」（`20261013-m12-240-native-dma`）。同一張卡可能協商成 UHS-I 或 UHS-II。
7. **239.76／279.72 的預覽走錄影路徑時，** producer 沒檢查 rec 寬會不會超過預覽來源 2100 或可見 2000。目前只有 M12 這種大小測過，大幅面配 240 沒有證據。
8. **小幅面未壓縮（例如 992×360，每格約 638 KB）可能撞上 94 描述子的限制，** 但只錄過短片。
9. **留邊 16/10 是慣例還是必要？** 原廠有 28 列是 (0,0)；producer 強制留邊，是保守的選擇。
10. **垂直起始列是奇數時，Bayer 相位會不會跟著變？** 沒有文件。DNG 原點本身可以是奇數（OG3K y=5）。
11. **readout_plan 的 4016、4176 寬度**來自 imx410-lab 的 RAM 連拍，錄影路徑還不能自訂視窗（見 3.8）。
12. 已知未修的問題：`test_reslab_preview_route` 有 2 項在修改前就失敗；240 的選擇重開後不會保存；計時器除的是錯的格率。

## 6. 建議給規劃器的檢查

```python
def legal_record(win_w, win_h, bin_h, bin_v, zh, zv, act_w, act_h, bits, fps, medium):
    assert bin_h in (1, 3, 5) and bin_v in (1, 3)
    assert 1024 <= zh <= 16384 and 1024 <= zv <= 16384          # 1023 也接受，視為 1024
    rec_w = (win_w // bin_h) * 1024 // zh & ~15
    rec_h = (win_h // bin_v) * 1024 // zv & ~1
    assert act_w % 16 == 0 and act_h % 2 == 0
    assert act_w + 16 <= rec_w and act_h + 10 <= rec_h
    origin = ((rec_w - act_w) // 2, (rec_h - act_h) // 2)
    assert bits in (8, 10, 12)
    assert fps in (23.976, 24, 25, 29.97, 48, 50, 59.94, 100, 119.88, 239.76, 279.72)
    frame = rec_w * rec_h * bits // 8 + 79_000
    mbps = frame * fps / 1e6                  # SD 不超過約 90，SSD 實證可持續約 220
    # 警告：frame < 714 KB 有 94 描述子風險；zh != zv 且沒 bin 時，預覽要另走等向
    # 軟規則：Fraction(zh, 1024).limit_denominator(64).denominator <= 5
    return rec_w, rec_h, origin, mbps
```

要讓 rec 剛好等於 act 加邊，Z 這樣取：`Z = (win // bin) * 1024 // (act + 16)`（V 軸用 +10），算完要用 1.1 回推檢查一次。
接收端裁切寬取 48 的倍數（12 和 16 的公倍數），BUFA 就不會暗中再截。

## 補充（2026-10-22，主對話，ROM 表實查）：錄影光柵可以水平裁切
- [C] 原廠窄寬模式就是用時序表 TIM 的 **+0xA（x 起點）/ +0xC（x 終點）** 在接收端裁一個比感光元件格式窄的光柵：
  mode 102（12-bit 4176×2174）格式 0x2A（6064）+ x 952..5128；mode 6（14-bit 4176）同樣 952..5128；mode 132（2×2 2088）476..2564；mode 95（14-bit 5712）184..5896。
  公式：x 起點 = 原 x0 + (格式寬 − 光柵寬)/2（1×1 x0 = 8、2×2 = 4、3×3 = 6）。META +4/+0x14/+0x24 = 光柵寬。
- 所以「錄影窗 = 模式光柵」仍成立，但**光柵本身可以在虛擬 mode 裡用 TIM x 窗裁窄**（res-custom 的 TIM 覆寫即可），不必靠 RWZM + DefaultCrop 才能裁寬；資料率也跟著光柵變小。
- 實作：`readout_cfg.plan()` 的 raster_w（16 的倍數）、`readout_export.py` 寫 TIM +0xA/+0xC 與 META 寬；驗算重現 mode 102 的 952..5128。
