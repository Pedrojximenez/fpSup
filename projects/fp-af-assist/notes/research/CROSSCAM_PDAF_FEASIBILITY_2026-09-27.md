# 跨機身重審：fp 能否靠韌體取得可用 PDAF

> **2026-10-11 補充：** 新增 [PDAF shell 指令與 PD 行幾何的兩道閘](PDAF_SHELL_AND_PDLINE_GATES_2026-10-11.md)：感光元件資訊 `+0xFC`（0xC2F1E750）是「支援 PDAF」旗標，IMX410=0、IMX455=1；`af msr pddef` 被 `+0x184` 擋且預設靜默。

日期：2026-09-27。目標是 SIGMA fp Ver.5.02；不是 fp L。方法為本地韌體位元組、既有反組譯、模式表及既有 RAW capture 的離線重查。本輪沒有連接相機、部署、寫寄存器或新增拍攝；只新增本文件。

## 判決

**目前不能把「fp 可經韌體解鎖 PDAF」列為可交付功能或主要研發假設。感測器是否另有可開啟的相位輸出仍未知；正常已測 RAW 路徑沒有取得可用相位樣本，現有原廠 fp PDAF 演算路徑也被關閉。主投入應轉到機內 DFD 輔助 CDAF、AAT 及其他經確認無 PDAF 機型的可移用方法。**

這不是「已證明 fp 晶圓絕無相位結構」。Sony 相同 driver family 的正面證據，足以保留底層研究問題；不足以跨過 fp 的資料可得性、像素／封包定位、校準及可達演算四個門檻。本文不替未知問題填入成功率百分比。

本輪比舊摘要多做了三類實質核對：

1. 從 fp 原始映像與 runtime dump 核對 vtable dispatch，**修正舊報告將 header 起點與函式起點混用的 slot 說法**。
2. 重新解碼 `PRESHOT000.BIN`，對照同曝光 DNG，重做指定週期的殘差掃描；**全幅相關係數未精確重現舊值，差異如下公開保留**。
3. 核對 Sony formatter RTTI／MMIO、A7C 全部匯出表的來源位元組，並找到 A7C 與 A7III 相對應的動態 companion-register 程式；Nikon 則直接重讀原始尺寸值。

## 1. 先分開感測器家族、實際 variant 與 PDAF 能力

| 機型／資料 | 本地可證到哪一層 | 不能由此推論 |
|---|---|---|
| fp 5.02 | IMX410 driver、constructor、runtime object 及模式表可互相對照 | 相同 family 就有 Sony 的遮罩、OTP、輸出通道或校準 |
| Sony A7III 4.04 | `av-cam.bin` 有 IMX410 RTTI，已追到該類別的 control／transfer methods | Sony phase pipeline 等於 fp 可用 pipeline |
| Sony A7C 2.03 | 同樣有 IMX410 RTTI；349 個 register records × 19 欄可回對 binary | A7C 新讀出表等於新找到 fp PDAF enable |
| Nikon Z6／Z6II | 解開的韌體有相近 sensor／AF 幾何；**IMX410 型號仍是推論**，未找出相同 register map | 3032×4040 尺寸就是相位左右 pair，或尺寸表足以重建 PDAF |
| Nikon Zf | 本地更新檔未解開；型號同源說法仍是推論 | 不能從產品像素數補上韌體證據 |
| Panasonic S1／S1H／S5、S5II／IIX、Leica SL2-S | 本地記錄停在加密容器；感測器精確型號未由可讀 driver 證实 | 不能把有／無 PDAF 的產品規格直接當同一 sensor variant 的 A/B |
| Blackmagic Cinema Camera 6K | 本次總盤點另支線提供官方 Camera 10.2.2 更新新增 phase AF 的確認；本地主要演算法 payload 仍未解開 | **不能再列為「無 PDAF」反例**；也不能因可後加功能，就推論 fp 已具備同樣資料源 |

本輪直接在 Sony 映像找到完整 RTTI `N6Camera6Imager6IMX41019C_ImagerCtrl_IMX410E`：A7III VA `0x63F02CA4`，A7C VA `0x63F84843`，共同 image base `0x635C6000`。這證明韌體 driver family，沒有證明相同光學遮罩／silicon option。

Nikon 型號界線見 [本地記錄](/Users/dido/Developer.localized/SIGMAfp_re/nikon_imx410/notes/NIKON_IMX410.md:46)；Panasonic 加密與型號限制見 [本地記錄](/Users/dido/Developer.localized/SIGMAfp_re/panasonic_imx410/notes/PANASONIC_IMX410.md:6)。Blackmagic 官方來源由總盤點另一支線核對：[Camera SDK and software updates](https://www.blackmagicdesign.com/mx/developer/partial/camera/sdk-and-software)。本離線子任務沒有重新連網查該頁，不把官方功能宣告當成已解出的本機 producer／consumer。

## 2. fp：重新核對 gate、dispatch 與 RAW

### 2.1 可修改的 capability gate，不能代替資料源

原始 `out/seg0_c0000000.bin` 中，`u32[0xC092B8D0 + 0x184] = 0xC029BA08`。重新以 ARM 解碼：

```text
C029BA14  mov r2, #0
C029BA18  mov r0, r2
C029BA20  bx lr
```

所以這是無條件回 0，而非尚未理解的條件分支。`CalcCafDriveSpeed` 的 caller 在呼叫前測試同一 offset，非零才進入。來源：[return 0 實作](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:97514)、[實際 caller](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:48943)。

這個 gate 可以用韌體修改改掉；**但改它只會使後續程式可達，不會生成缺失的 phase pairs、可靠度、校準或 defocus**。它是原廠配置未使用 PDAF 的強證據，不是不可改變的硬體熔絲證據。

### 2.2 本輪更正：`PdafCorrect` 的 `+0xA8` 實際指向 v40

舊 8/18 報告稱「slot 42／+0xA8，IMX410 no-op `0xC0322280`」。重新核對 runtime object 與實際指令後，正確鏈為：

```text
sensor object = 0xC343B588
object + 0xD0 = 0xC343B658
IMXOBJ00.BIN[0x158] = 0xC0B5FCC0
PdafCorrect → FUN_C030F710:
  C030F784 ldr ip, [r2, #0xD0]
  C030F78C ldr r8, [ip, #0xA8]
  C030F7B8 blx r8
u32[0xC0B5FCC0 + 0xA8] = 0xC0322228 = XC_ImageSensor::v40 → return 0
u32[0xC0B5FCC0 + 0xB0] = 0xC0322280 = XC_ImageSensor::v42 → no-op
```

`0xC0B5FCC0` 前兩個 word 是 `0` 與 typeinfo pointer；首函式位於 `0xC0B5FCC8`。舊說法用首函式的編號解釋以 header 為基準的 offset，差了 8 bytes。constructor 確實把 header 位址寫入 `object+0xD0`，與 snapshot 一致，不可自行換成 `FCC8`。

來源：[constructor／singleton](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:25629)、[間接呼叫](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:12153)、[v40 與 v42](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:23542)。對應 IMX455 的 **v40 `0xC03295B8`** 才會取 geometry、計算行間距並呼叫 backend `FUN_c032e118`：[實作](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:27542)。

**結論不變，但理由更精確：fp 這條 sensor-specific correction dispatch 回 0；不能把共用 `PdafCorrect` 字串或 IMX455 的幾何表當成 fp phase 座標證據。** 本輪只更正本文件，不覆寫歷史報告。

### 2.3 原始 capture 與 bypass 確認

重查 `research/imx410/captures/NIKON_D80_preformat_2026-08-17/`：

- `PDPRE.BIN` 首 word `0xE92D4DF0`；`PDPST.BIN` 與 `PDPST000.BIN` 均為 `0xE12FFF1E`（`BX LR`）。
- `DEFORIG.BIN`／`DEFPOST.BIN` 中保存的 acquisition argument 指令由 `mov r2,#1` 改為 `mov r2,#0`；與既有 WDD／BDD bypass 實驗記錄相符。
- `HOLDMETA000.BIN` 前六個 u32 為 `{5F900C00,1,0,0,1,1}`；`HOLDEND000.BIN` 為 `{5F900C00,1,1,0,1,1}`。依既有 wrapper layout：RAW pointer 正確、hold entered、dump 時 release=0、之後 release=1、mode 0／RAW14／單幀。

這些是既有 capture 的時序／patch 證據；不是本輪新增實機試驗。wrapper 與有效／無效輪的區別見 [歷史記錄](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/SIGMA_FP_PDAF_INVESTIGATION_REPORT_2026-08-18.md:171)。

### 2.4 本輪 RAW 重算結果與限制

`PRESHOT000.BIN` 為 50,331,648 bytes。取開頭 `6064×4042×14/8` bytes，按每 7 bytes 四個 MSB-first RAW14 解碼；前四點重現 `{1195,1411,1212,1413}`。使用 rawpy 0.27.0 讀同曝光 `_SDI0042.DNG` 的未裁切 `raw_image`，形狀亦為 4042×6064。

| 檢查 | 本輪結果 |
|---|---|
| 兩個 green CFA plane | 與 DNG pixel-for-pixel 完全一致，差值非零數皆 0 |
| red／blue | 非零差值分別 5,130,672／5,018,016 點，差值中位數 −5／+4 DN；為廣泛色平面差異 |
| 全幅 Pearson correlation | **0.9999658557369344**；舊筆記為 0.99998646，本輪未重現其精確值 |

兩個備份目錄的 RAW、DNG、HOLD metadata 雜湊完全相同，故這次數值差異不是選到不同檔案。舊 correlation 的像素選取／解碼工具細節未完整保存，差異原因仍未知；不以舊精確值作新的證據。兩個 green 完全相同、首點與幾何重現，仍支持 frame／packing 對齊。

另做獨立殘差掃描：四 CFA plane 分開，中心減去 sensor-grid 軸向 offsets `±2、±4` 的八個同色鄰點平均，邊緣各去除 4 sensor pixels。以 sensor-coordinate period `4,8,16,32,64,92,128` 分組取 median。四 plane 的 residual MAD 為 `8、11.875、11.875、8.625 DN`；period≤64 最大 group-median 偏移分別 `0.625、0.8125、0.875、0.625 DN`；period128 最大為 `1.5、2.0、2.25、1.625 DN`。

這次掃描沒有給出可定位的強週期遮罩訊號，與舊分析方向一致。**但「分組 median 遠小於單點 MAD」不是正式檢出力／顯著性分析；本輪沒有跨場景重現固定座標，也沒有受控 pupil-mask／左右瞳孔照明測試。** 一個 normal still frame 不能排除非週期 mask、特殊 LV mode、sensor-side 已處理資料或不同封包輸出；也不能把未發現 lattice 寫成所有模式的硬體不存在證明。

可支持的範圍是：在這條已觀測 RAW acquisition 與 bypass 條件下，沒有取得可供演算的 phase pair，也不支持「只關 CPU PdafCorrect 就能拿回相位資料」。

原始檔案 SHA-256：

```text
PRESHOT000.BIN  7db9ea428018bdf294d7b3e1be0e3ed64d539b0de89d95bb3959ac3764969338
_SDI0042.DNG   e6f302ba4ae8a1d45bff89d966a60af51adfbffe7b47815dac95776548b2ee4a
HOLDMETA000    8fca610d05b23848d914c9ee9b35efe4dee6121d95a479b54605886c6491e152
HOLDEND000     412bba3b884eb72ad91b51df4a71a905e159b037a878c9639ddae59d184ec1d9
```

## 3. Sony：控制寄存器是正面線索，VC1 不是 sensor-phase 證明

### 3.1 A7III 的 ingress 與 egress 分離可由 binary 確認

本轮直接讀 A7III 4.04 `av-cam.bin`（SHA-256 `e1b0f84e8323005a34b43de6dd0083fca712d2c654f0d9716512e0a54631bbe7`）：

- `0x63EFEA32` 為 `N6Camera7DFECore10Ofmt_MwrapE`；typeinfo `0x646EEACC` 的 name pointer 指向此字串；vtable header `0x646BACD0` 的 typeinfo pointer 指回該物件。
- constructor `0x637A9D3C` 從 literals `0x637A9D70/74` 載入 **`0xFC0A7000/0xFC0A7400`**，依 core 選取，將 VC1 capability 存在 object+9。
- `setVc1PacketInterval` 的結尾跳至 `0x63CE7634`；該原始 Thumb 指令為 `str r1,[r0,#0x3c]; bx lr`。這是上述 **DFE output formatter** 的寫入，並不是 sensor receiver 的 VC1 enable。
- `0x63E22FA0` 的六筆 descriptor 原值重讀為 `{1,1,0x2C,0,0}`、`{1,1,0x2D,0,0}`、`{1,1,0x31,0,0}`，重複兩組。證明 CAM transfer 設定有 VC1，仍未證其 payload 就是 phase pixels。
- `GCS2RXLINK_DFE` 錯誤處理確實另有兩條 leg；已讀到其第二 bank literal `0x637AFDA8 = 0xFC0F0100`，與 formatter 不同。不可將 receiver bank、formatter、CAM MIF 的三個硬體域因都提到 transfer 就合成同一條 sensor VC1。

原始反組譯與 caller：[formatter constructor](/Users/dido/Developer.localized/SIGMAfp_re/sony_a7m3/a7m3-re-20260904/work/phase_route/vc_receiver_ctor_decomp.log:65)、[interval 寫入](/Users/dido/Developer.localized/SIGMAfp_re/sony_a7m3/a7m3-re-20260904/work/phase_route/vc_interval_exact_child.txt:49)、[RX error path](/Users/dido/Developer.localized/SIGMAfp_re/sony_a7m3/a7m3-re-20260904/work/phase_route/root_gcs2_error_disasm.txt:304)、[RX setup](/Users/dido/Developer.localized/SIGMAfp_re/sony_a7m3/a7m3-re-20260904/work/phase_route/gcs2rx_setup_decomp.log:193)。

已存的後續 trace 將 AfterCap/type-4 接到 `CompDecomp → IIB line → FOPD R0 → AFMAP`；normal real-time 用 internal selector 0，ZpdPre 又有另一個 AXI output。這些是 Sony 下游資料面的正面證據，**還缺 `sensor ingress → phase extractor／packing` 的那一段**；也没有證據可把 ZpdPre 的 DDR buffer 強接為 FOPD 輸入。[各假說及缺口](/Users/dido/Developer.localized/SIGMAfp_re/sony_a7m3/a7m3-re-20260904/outputs/sony_a7iii_phase_data_route_followup.md:570)

### 3.2 A7C 新的 binary 交叉核對

本輪未只信匯出 CSV：以 A7C `av-cam.bin`（SHA-256 `0c77df5708ce672306a431ec26f4bce41765598b487402fe32eb887f3169c3b9`）重讀 GOT→patch pointer、238 筆 24-byte patch records，逐筆比較 CSV 的原始 register address、default byte 與 19 欄值。**349 筆全部匹配，0 mismatch。** 結構入口可參照 [匯出器](/Users/dido/Developer.localized/SIGMAfp_re/other_imx410/scripts/export_a7c_tables.py:16)，本輪沒有執行其寫檔部分。

此外直接確認：A7C 首函式 vtable `0x645B0C08` 的 slot16 指向 `0x637B1201`（Thumb entry `0x637B1200`）。此函式對應 A7III 的 slot14／`SetRead_ZAF @0x637B2FB0`，保留同一組 companion 操作：

| A7C 原始 binary 證據 | register record |
|---|---|
| GOT `0x646529C4 + 0xB1C0 / +0x46C8` | `0x64643682 / 0x646437AA` → `0x0048 / 0x0047` |
| GOT `+0x22F0 / +0x0F6C` | `0x64643462 / 0x646434B6` → `0x004A / 0x0049` |
| calls `0x637B12A2 / 0x637B12B2` | 兩次呼叫 builder `0x63D3F5D4`，組兩組 high/low 值 |
| GOT `+0x873C`；指令 `0x637B12DC / 0x637B12FE` | record `0x646437F2` → `0x05E2`；OR `#2` |
| GOT `+0x691C`；`0x637B12EC..0x637B1314` | record `0x646437DA` → `0x0424`；選 `0x1D/0x0E/0x23/0x1B` |

A7III 同型操作的可讀反組譯見 [SetRead_ZAF](/Users/dido/Developer.localized/SIGMAfp_re/sony_a7m3/a7m3-re-20260904/work/analysis_avcam/zaf_methods_disasm.txt:183)。A7C 的這次核對增加「Sony 兩款 IMX410 driver 有同源專用控制」的可信度，**不增加「fp 同一 sensor variant 能輸出相位樣本」的直接證據**。目前不能將 `05E2 bit1` 自行命名為 PDAF enable；它是條件式的 ZAF read-path 行為。

## 4. Nikon：幾何是真的，phase packing 與型號還沒有證明

本輪直接讀 Z6 `eg1620_038000.bi` 的 `0x1EF653C`，24 筆 u16LE 尺寸與 CSV 相符，包含 `6064×3412`、`6064×1138`、`2020×1342`。另重找到唯一連續 u32LE `3032,4040` 在 `0x1EF8A48`，`1976,2636` 在 `0x1EF8ABC`。`IMX410` ASCII 在該主映像為 0 次。

原始資料索引：[幾何 CSV](/Users/dido/Developer.localized/SIGMAfp_re/nikon_imx410/Z6/z6_geometry_lists.csv:2)、[AF 記錄說明](/Users/dido/Developer.localized/SIGMAfp_re/nikon_imx410/notes/NIKON_IMX410.md:96)。**沒有字串不是型號否證，尺寸相同也不是型號確證。**

3032×4040 可以是全高、水平縮減的 AF 讀出，也可能處在某一處理階段；目前沒有 decode 出 pupil A/B 排列、masked-coordinate map 或對應寄存器 sequence。既有多種 table 搜尋沒有找到相同 map；要從此繼續，具體缺口是 SIF SPI writer 與 RAM relocation，不是再多列幾個相同尺寸。[搜尋範圍與缺口](/Users/dido/Developer.localized/SIGMAfp_re/nikon_imx410/notes/NIKON_IMX410.md:57)

因此 Nikon 目前給的是「AF 可以有特殊讀出幾何」的旁證，沒有跨過 fp 的第一個資料門檻。本輪不把早期搜尋負結果升格為 Nikon 全 binary 不可能有 sensor table。

## 5. 四個可行性門檻

| 門檻 | fp 現況 | 跨機身已帶來什麼 | 能改變判決的最小新證據 |
|---|---|---|---|
| **G1 相位樣本／payload 真正存在且可取得** | 正常已測 RAW 無可用 pair；特殊 mode／封包與物理 mask **未知** | Sony 有專用 control 與下游 phase hardware；A7C companion code 重現，Nikon 有 AF 幾何 | **fp 本機來源**、可重複的左右瞳孔差異樣本，或同 variant 的可靠文件明確指出 phase output 與可達配置；僅 register ACK／值不同不足 |
| **G2 定位、配對與時序** | 尚無 fp phase-coordinate map、payload layout、pair polarity 或相位資料與曝光的配對 | Sony 已有下游 buffer／AFMAP；最初 extractor edge 未封閉 | 解出固定座標或 packet schema，能把兩側樣本配成同一曝光／同一區域；對可控 defocus 正負產生可預期變化 |
| **G3 校準與可辨識的 defocus** | 尚無該 fp 資料源的 shading、缺陷、lens／aperture／field 校準；鏡頭 DPP／距離表不能取代它 | Sony 校準物件名與 service 命令提供方向，schema／輸入關係仍有缺口 | 留出場景與位置的有號離焦預測，比普通 CDAF／單幅亮度變化有額外資訊；覆蓋至少一鏡頭、一光圈及 field 區間並標限制 |
| **G4 機內演算／AF 整合可達且有效** | 原廠 fp PDAF gate=0；共用框架存在，但沒有合格的 phase input | Sony 展示多段硬體／韌體協同，不能直接搬到 fp SoC | 機內觀測模式下 estimator 能吃有效樣本且符合幀預算，再做受限 AF 整合與原廠 A/B；不以強開 gate 或出現非 sentinel 當合焦成功 |

**瓶頸在 G1，不在先改 G4 的 return 0。** 改寫韌體讓演算法可達是一項工程能力；是否有互補瞳孔訊號則是另一項條件。共同的 `PdafCorrect`、Sony register 名稱、Nikon AF 尺寸、Blackmagic 後加功能，均不能替代 fp 本機的 G1 證據。

## 6. 停止／續查規則與資源方向

**現在就把主要開發資源投到無 PDAF 方法，不等待把所有未知查完。** fp 的機內 CDAF／DFD／AAT 有可用統計與已定位流程；跨機身應優先研究可讀且型號／功能已確認的 CDAF、DFD、多頻帶評價、主體置信度與控制節奏。對照機型的「無 PDAF」分類須按明確 firmware 版本核對；Blackmagic Cinema Camera 6K 不再當作當前的無 PDAF 樣本。Panasonic 目前加密的主程式也不應因標示 DFD 就假定已有可移植碼。

PDAF 支線只保留有具體入口的有限查核：

1. **一輪只回答一個明確缺口。** 例如 Sony/A7C 指定 phase-extractor mux 的一條 caller／writer chain，或 fp 指定 candidate 的 dynamic write／variant check。沿已知函式或表追到返回、資料來源或硬體 writer即記錄結果；没有下一條具名 edge，就標未知並停止該輪。
2. **續查門檻是新證據，不是更多同類字串。** 只有 fp payload、同 variant 技術文件、可重現 source→phase extractor 連線，或可識別的 calibration schema，才足以重新安排下一輪。新增一款相同像素數相機、再次找到 ZAF 字串或重複 generic service API，不自動續開研究。
3. **G1 未過，不推進 G3/G4 的移植或盲試。** 不直接移植 Sony mode table、不重試已 hang 的 raster window 修改、不靠 gate=1 測試「看看會不會有 PDAF」。這些操作既未提供明確候選資料源，也不在本輪離線範圍內。
4. **任何正面候選先離線辨識。** 先證明是 phase-specific 的 pupil 訊號，而非普通 Bayer、亮度統計、DFE 中間格式或 metadata；再另訂有邊界的採集與驗證方案。G1 有正面結果只代表值得繼續，不代表四關全過。

機內 hook／EP83 可以服務 AF／AAT 觀測、資料傳回與離線研究，無須把它限定為 PDAF 探針；它也不使產品依賴電腦即時控制。現階段最有價值的使用是原廠 CDAF／AAT 及 DFD 輔助的研究驗證。整體工作入口見 [AF 開發整理](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/FP_AF_DEVELOPMENT_STATUS_2026-09-27.md)。
