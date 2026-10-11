# Liveview 的 bin／vbin 分支與上游截斷

2026-09-24；SIGMA fp 5.02；離線核對 ROM、反編譯與既有紀錄，未連線相機。

## 結論

**使用者提出的 bin／vbin 方向有直接韌體依據：預覽有獨立的 hbin／vbin 參數，原廠部分錄影配置確實指定預覽 3×3、錄製 1×1。** 但這不是所有模式的共同狀態，也不等於 LCD 直接讀 `CrctVbinToBufA` 的錄影 DMA buffer。

目前找到的兩組 CRCT reduction record，按現有 u16／u8 欄位的無符號解讀，係數皆非負、垂直每組和 4096、水平每組和 64；若 ASIC 採相同解讀、按該和歸一化且累加器位寬足夠，bin 不會自行產生超出輸入最大值的 overshoot。這個結果排除了「看到 3×3 就必定亮度相加成九倍」的推論，**沒有排除 ASIC 中間溢位、錯誤 shift／range、bin 前已剪平，或 bin 後 gain／matrix 限幅。**

## 1. 不是靠名稱猜的：preview 與 record 的設定鏈

以下箭頭是**設定資料的流向**，不是已確認的所有像素運算先後。

```text
profile PARAM
  preview +58/+C4 hbin/vbin；+60/+D0 zoom
  record  +5C/+C8 hbin/vbin；+64/+D4 zoom
   ↓ C0438018：XC_LiveViewDispParamWithRaw
  descriptor preview +A8/+AC bins、+A0/+A4 zoom
             record  +50/+54 bins、+48/+4C zoom
   ↓ C031D988 → imager0 ops+9C → C0325228
  main/sub reduction 與 record DMA 路由選擇
   ↓ C0320AF0 → C032D9A0
  C0633B30 main／C0633DA0 sub → CRCT MMIO
```

可核對的原始位置：

- [descriptor constructor](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c04.c:38102)：逐欄位複製上述 preview／record 參數。
- [C031D988](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:20721)：組成兩組尺寸、zoom、bin、bit-depth 描述並呼叫路徑選擇器；診斷字串明確分別寫 `rec hbin/vbin` 與 `liveview hbin/vbin`。
- [bin enum 轉換](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:35196)：H 的 0/1/2 → 1/3/5；V 的 0/1 → 1/3。
- [reduction builder](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:29681)：讀取 sensor descriptor `+114` 的 record 指標、每筆 `0x38` bytes，送入主／副管線 driver。

ROM 獨立核對：`[C2F1E654+114] = C0B5F770`、`[C0B5FCC0+9C] = C0325228`。必須分別使用 seg0、seg1 正確映射；不可把舊 MAIN 的尾端當成 seg1。

### 不能混淆 DMA 抽頭與預覽內部處理

`C031D988` 的 `CrctVbinToBufA`／`CrctHbinToBufA`／`CrctHbin2ToBufA` 字串位於 `bufa0_rec_on`、`bufa7_rec_on` 的診斷分支。它們回答的是**錄製 writeout 選哪個抽頭**；另一組 `liveview hbin/vbin`、main/sub bins 回答預覽與管線如何縮減。

所以舊 [CRCT selector 研究](../imaging-hw/notes/CRCT_PATH_SELECTOR_SOLVED.md) 的「Vbin mux 未被原生選到」不能擴張成「liveview 沒有走 Vbin」。同樣，錄製視窗關閉也不能解讀為 preview 停止。

## 2. 模式證據：有 3×3，也有 through

本輪把外部 handoff 的 306 列、每列 65 欄 **19,890 個值**逐一與 seg0 重讀比對；500 個 profile mapping entry 也全部吻合。以下是 ROM 靜態 template，不能冒充當前 RAM 狀態。

| template／歷史觀測 | preview H/V bin | record H/V bin | 能證明的事 |
|---|---|---|---|
| 原廠全部 306 列中的 17 列 | 3／3 | 1／1 | 存在明確的預覽 bin 分支 |
| 其餘 289 列 | 1／1 | 1／1 | CRCT bin 不是所有 template 都開啟 |
| profile429（UHD24，row286） | 3／3 | 1／1 | preview zoom=1024／1024；record zoom=1600／1600；base dimensions 分別 2016×1135 與 3856×2170 |
| profile5（monitor template，row2） | 1／1 | 1／1 | preview base=2016×1344；record dimensions=0／0；不能把 profile5 當成所有錄影時唯一 RAW 採集來源 |
| 2026-09-16 實機既有待機紀錄 | `small_raw hvbin 1／1` | 未在此筆獨立確認 | MONIT1_60、sensor enum8、12bit、2016×1344、zoom1024／1024、gain_state through |

最後一筆來源：[當時 mode_now 原文](../../projects/fp-af-assist/notes/evidence/capture-af-fusion-2026-09-16-iso100-v5.md#independent-mode-query)。**sensor mode enum8 與 profile ID5／429 是不同編號空間。** sensor 自身 readout 可能已縮減；CRCT through 不代表全解析 sensor readout。

`C0436180/C0436218 → C0436360` 另把 profile `+80/+84` 的格式編號轉成 raw-bit enum；`C031D988` 會分別印出 preview／record raw bit。這表示位深也需按當前 descriptor 查證，不能沿用 sensor ADC 位深或 tone LUT 輸出 13bit 代替。位深量化本身也不等同亮部硬截斷：需核對 full scale 的映射及是否有平台。

## 3. bin 核是否自己產生溢出？

| ROM record | 垂直係數（每三個一組，共三組） | 水平係數（每三個一組，共四組） | 第二水平級 |
|---|---|---|---|
| 0，`C0B5F770` | `[1024,2048,1024]` ×3；每組和4096 | `[16,32,16]` ×4；每組和64 | `[16,32,16]` |
| 1，`C0B5F7A8` | `[256,3584,256]` ×3；每組和4096 | `[4,56,4]` ×4；每組和64 | `[4,56,4]` |

若 `y = Σ(wᵢxᵢ)/Σwᵢ`、所有 `wᵢ≥0`，則 `min(xᵢ)≤y≤max(xᵢ)`。這是係數的數學界限；歸一除數由係數和推得，係數無符號解讀依 ROM 欄位；尚無 ASIC 規格或階段像素測試確認實際 arithmetic／係數 signedness。

累加前不可先捨掉高位。以 unsigned、未預先縮放的完整加權和為例：

| 輸入位深 | 垂直 weighted-sum 最少位數 | 水平 weighted-sum 最少位數 |
|---|---|---|
| 12bit | 24bit | 18bit |
| 13bit | 25bit | 19bit |
| 14bit | 26bit | 20bit |

這是**所需精度**，不是已知的 ASIC 位寬。硬體也可能使用等效的分段／預縮放運算；不能由表格直接指控硬體 overflow。

### driver 中已知的控制，不替未知 bit 命名

[main driver C0633B30](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c06.c:45821) 寫：

- V：`300F0800`，係數 `0810/0814/0818/081C/0820`。
- H：`300F0840`，係數 `0850/0854/0858/085C`。
- H2：`300F08C0`，係數 `08C4`。

V code=2（builder 由 vbin=3 產生）時，record0 的主控制值是 `00000001`，record1 是 `00010001`。同樣輸入到 [sub driver C0633DA0](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c06.c:45928) 則兩者都是 `00000041`。主／副 driver 對 variant 的處理不同；**不能把 bit4.. 當成已解碼的「亮度右移位數」，更不能共用一套 shift 假設。** 這些值是條件式 driver 重算值，並非本輪讀到的活動 MMIO。

`C032D9A0` 還會在指定 RWZM／bin 條件把 H code 從 driver `+1A` 搬到 `+28`，也就是第二水平級；清掉第一級不等於停止水平縮減。副管線只寫精簡的 V/H 係數與控制，沒有主管線完整 H2 結構。

## 4. 對 rawlive 的具體意義

優先定位 **liveview／small_raw 分支上仍保留 Bayer 或其他可證明線性資料的實際 buffer**，並確認它在 bin、gain、WB、matrix 的哪一側。不要因名稱有 Raw、尺寸約 2K 或畫面看起來平，就認定它可還原。

最小資料配對應包含：同一模式與時刻的 sensor enum、profile／descriptor、preview/record H/V bin、main/sub reduction record 與控制、preview bit-depth／packing、黑白位、gain state、來源 buffer 的當幀有效區與序號。之後才比較 bin 前後或 preview RAW 與 ISP 輸出是否出現平台。

若 bin 後仍保留梯度、後級 RGB 已平台，重點移到 gain／WB／matrix／IGAMMA；若 bin 輸出已平台，需再分 sensor 輸入已飽和與 CRCT 運算／range。不能靠替換末端 tone 完成這個區分。

## 可重算資料

- [audit_preview_reduction.py](audit_preview_reduction.py)：只讀兩段 ROM 與已歸檔 JSON；不執行歷史脚本、不連相機。
- [preview-reduction-audit.json](preview-reduction-audit.json)：來源 SHA256、逐欄位核對數、所有 17 個 binned profile ID、record bytes、係數及條件式 accumulator 界限。
- 可指定 `--repo` 與 `--output /private/tmp/preview-reduction-audit.json` 重算。
