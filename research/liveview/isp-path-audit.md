# fp LCD 色彩截斷：ISP 路徑離線稽核

2026-09-24。只讀本地 Ver.5.02 反編譯與既有筆記；未連相機、未部署或修改韌體。下文 `[C]` 是可直接核對的程式事實；`[I]` 是推論；`[?]` 是尚未證明的語意／實機行為。

原始碼根目錄：`/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/`。行號針對此目錄的 `blk_c01.c`、`blk_c02.c` 等現存版本。這份文件不把舊筆記的總管線圖當成硬體規格。

## 1. 先修正地址與既有結論

`research/imaging-hw/notes/COLOR_SCIENCE.md` 把幾個印表標籤對到了前一個區塊。診斷程式先列名稱、再列該區塊地址，必須以相同規則讀取。

| 硬體區塊 | MMIO | Shadow 起點 | 直接證據 |
|---|---:|---:|---|
| MAT_TOP_IGAMMA | `0x30115000` | `0x30210C70` | `blk_c01.c:50117`、`84657` |
| MAT_TOP_RGBLMAT | `0x30115100` | `0x30210CB0` | `blk_c01.c:50120`、`84658` |
| MAT_TOP_PSTIGAM | `0x30115200` | `0x30210D18` | `blk_c01.c:50124`、`84659` |
| GAM_TOP_GAM_GS_GAMDEC | `0x30115804`、`0x30115820` | `0x30210D50`、`0x30210D58` | `blk_c01.c:50127`、`84660` |
| GAM_TOP_GAM_BAS | `0x30115900` | `0x30210DDC` | `blk_c01.c:50133`、`84662` |
| GAM_TOP_YCMAT | `0x30115A00` | `0x30210E64` | `blk_c01.c:50136`、`84663` |
| GAM_TOP_GAMMA_TABLE | `0x30115B00` | `0x30210EB4` | `blk_c01.c:50140`、`84664` |
| GAM_TOP_SBUS_GAMMA | `0x30115B14`、`0x30115B2C` | `0x30210EC4`、`0x30210EDC` | `blk_c01.c:50143`、`84665` |
| GAM_TOP_RGBMAT_PL | `0x30115B80` | `0x30210EE0` | `blk_c01.c:50147`、`84667` |
| PST_TOP_Y_GAMMA | `0x30115E00` | `0x30210F08` | `blk_c01.c:50153`、`84669` |
| YMED_TOP_C_SAT_C | `0x30117B00` | `0x3021127C` | `blk_c01.c:50214`、`84689` |
| CEQ_CLIP | `0x3011D700` | `0x30212228` | `blk_c01.c:50333`、`84727` |
| CEQ_Y_GAMMA | `0x3011D800` | `0x30212324` | `blk_c01.c:50338`、`84728` |

`FUN_c019c810` (`blk_c01.c:84591` 起) 的 descriptor 建構把 shadow 與 MMIO 成對列出，可交叉驗證。[C]

因此：

- **`0x30115A00` 是 YCMAT，不是「2048 點主 tone 表」的直接寫入位址。** [C]
- `FUN_c0107250` 寫 `0x30210C78..0x30210CAC`，屬於 **IGAMMA 分段參數**，不是 3×3 CCM packer。[C]
- `0x30117280` 的名字是 BLT_NLM，C_SAT_C 在 `0x30117B00`。[C]
- 「有 88 條 tone ROM 資源」與「tone 一定在 YUV 域／CCM 後、只有一條對所有通道相同的函數」是不同強度的主張。前者可以驗證，後者不能僅由這個 MMIO 排序證明。[?]
- 舊筆記的「沒有 hue LUT」「所有創作矩陣都是 per-unit 校準」「RGBLMAT 不隨 mode 改」也不能直接沿用。現存 `research/imaging-hw/color-firmware-20260924/fp-private-color-findings.md` 已記錄相關修正。

## 2. 真正 RGBLMAT：兩組 3×3、原生可縮小增益

`FUN_c01073a0` (`blk_c01.c:3567`) 與 `FUN_c0107548` (`3635`) 各接收九個 signed 16-bit 係數，再編碼為 11-bit (`& 0x7FF`)；identity 係數為 `0x200`。這證明是可以表達負係數的固定精度矩陣，不代表負的**像素**一定能往後傳。[C／?]

`FUN_c0107490` (`3617`) 將第一組寫到 shadow `0x30210CB0..C4`；`FUN_c0107608` (`3675`) 將第二組寫到 `0x30210CC8..DC`。對應 MMIO `0x30115100..14`、`0x30115118..2C`。[C]

`FUN_c01076c0` (`3693`) 寫最後幾個參數到 shadow `0x30210CE0/CE4`，即 MMIO `0x30115130/34`。`FUN_c011a6d0` (`13054`) 將來源 `+0x48/+0x4C/+0x50` 預設為零。後續已追到 `+0x50 → MMIO 30115134` 與原生兩組矩陣超界時全18係數除2的 flag 相連，支持係數尺度補償的解讀；硬體精確語意仍未知。不能直接命名為 black clamp 或 negative-clip disable。見 [新稽核](matrix-gamma-audit.md)。[C/I/?]

`FUN_c02cfcf0` (`blk_c02.c:131315`) 根據 mode／調整／狀態取得兩組矩陣，呼叫上述 packers (`131445` 附近)。不能只量 tone 表而忽略這些模式處理。[C]

另有重要的原生增益拆分：

- `FUN_c032ec70` (`blk_c03.c:30558`) 將一個 Q10 類型增益拆為至少 `0x400` 與至多 `0x400` 兩部分。
- 大於 unity 的部分經 `FUN_c011da30` 寫 SIG0 TBLSD gain shadow `0x302103C8/CC`，即 MMIO `0x30112740/44`。預設 R/兩個 G/B 的數值比例是 `0x100/0x200/0x200/0x100`，不可把四個欄位當同樣的 unity 編码。[C]
- 小於 unity 的部分由 `FUN_c032ef78` 存於 `0xC34143B8 + 0xB0/+0xB4` 兩個 context；`FUN_c032efa8` (`30719`) 上限夾到 `0x400`，以 Q10 方式縮放**第一組矩陣的 indices 0/3/6，以及第二組的全部九項**，包含負係數的 11-bit 編碼處理，再呼叫四個 RGBLMAT setters (`30830`)。第一組其餘六項保留，因此不是兩組矩陣全部等比縮小。[C]

這是比「把最終畫面整體變暗」更有研究价值的前段 headroom 候選。但要確認它在 live/MOV 的使用範圍、會不會改 RAW、是否早於實際 clip。這個原生分支尚不能當成逐通道等比衰減；矩陣縮小也無法解決已經變成零的負值色域裁切。[I／?]

## 3. 真正 tone dispatch 與 cache

ROM 資源 getter `FUN_c02cf300` (`blk_c02.c:130774`) 回傳 `0xC097110C`。三個 PQ 家族建構子使用它：

| 建構子 | 位址／行號 | Tone wrapper |
|---|---|---|
| `FUN_c02bf6d8` | `blk_c02.c:120180` | `FUN_c02c0160` (`120630`) |
| `FUN_c02c1d68` | `121762` | `FUN_c02c2648` (`122119`) |
| `FUN_c02c2e08` | `122451` | `FUN_c02c38b0` (`122897`) |

三者最後均取得 `FUN_c02c1cf0()` 的 singleton `0xC3414470`，再呼叫 **`FUN_c02d29e0`** (`133347`)。[C]

`FUN_c02d29e0` 的實際行為：

1. 以 `param_3 + 0xF8` 的 boolean 為兩個處理 context；另外比較模式、對比、toning、特殊處理等狀態決定是否換表 (`133385..133444`)。
2. `FUN_c02d2f40` (`133563`) 找 profile 基底 index，加入對比調整 index；某些 profile 的對比 index 乘 3。
3. 普通分支使用一條 LUT。另一分支使用三條相鄰 LUT，descriptor selector 為 `0x1B/0x2D/0x36`，不能預先假定所有色彩模式都走同一共用曲線 (`133499..133523`)。
4. 有 toning 時 `FUN_c02d2fd0` (`133594`) 生成 RAM LUT；長度 `0x400` 個 word = 2048 個 uint16。正向外推分支明確對**產生的 LUT 數值**夾 `0..0x1FFF` (`133640..133678`)。
5. context 0 使用兩套 RAM scratch 輪替；context 1 使用 `0xC3414DA8/5DA8/6DA8` 三個固定區域。這些是**韌體已用區域，不能當新 scratch**。
6. `FUN_c011b4c8` (`blk_c01.c:13868`) 註冊 LUT descriptor，轉換來源地址為硬體 word address，存入兩套狀態。
7. `FUN_c019c190` (`84186`) 讀 descriptor，呼叫 `FUN_c01a0560` 排入 SIGSEQ。

**patch 必須處理 firmware cache／重排程。** 只把一個 ROM pointer 改到另一張表，若 `FUN_c02d29e0` 判定 key 未變，可能只沿用之前的 descriptor。就算畫面當時看起來改變，也應驗證切模式、開始／停止錄影、重進 live view 後仍使用同一目標表。[I]

**尚未證明 display-only。** 這個 tone 路徑被多個 PQ 家族共用；兩個 context 不等於「LCD 與 MOV 各自獨立」。需要追到 native pipeline state／調用端，或在受控試驗用 MOV 與 LCD 同時比對。不能把全域曲線資源替換直接包裝為只改 LCD 的功能。[C／?]

舊筆記將 `FUN_c047af40` (`blk_c04.c:91604`) 當 tone curve selector，但它只直接顯示某物件的 vtable `+0x214` 呼叫；沒有直接接到 LUT descriptor。真正可觀察 tone table 消費的入口應以上述 `c02d29e0` 鏈為準。

## 4. 實證的 clamp，與尚未證明的 pixel clip

| 位置 | 程式可證明的事 | 不能據此聲稱 |
|---|---|---|
| `FUN_c0117248`, `blk_c01.c:10635` | 四個 Bayer/WB gain **參數**上限 `0xFFF`；寫 shadow `0x30210768/6C` → SIG1 `0x30113494/98`，亦寫 `0x30210468/6C` → RAWBLT `0x30112820/24` | 不能把 gain 參數上限說成像素 clipping threshold |
| `FUN_c01073a0/c0107548` | signed 矩陣係數編成 11-bit | 不能證明負像素保留／裁切的位置 |
| `FUN_c02d2fd0` | 生成 tone LUT 的外推值被夾 `0..8191` | 不能證明目前 live 正在走該分支 |
| `FUN_c02d3190`, `blk_c02.c:133677` | 從 CEQ 曲線生成 4096 點表時夾 `0..4095` | 不能把此軟體重建函式當作 pixel processing 硬體實測 |
| CEQ_CLIP `0x3011D700` | 48 個表項及額外參數可配置；`FUN_c0112b00` (`blk_c01.c:8862`) 寫表；`FUN_c0110800` (`8319`) 寫後段參數 | 名字帶 CLIP 不表示它就是飽和 LED 突變的根因 |

`FUN_c011b0a0` (`blk_c01.c:13620`) 提供 CEQ_CLIP 周邊預設：來源 `+0x46C=0xFFF`、`+0x470/+0x474=0`，以及 `+0x4AC/+0x4B0=0x80`。由 setter 可精確映射到 MMIO `0x3011D7C0/C4`、`0x3011D7F4/F8`。目前不知道這些欄位的完整硬體語意，**不能把它們全設最大當作「解除 clip」**。

## 5. YUV／LCD range：有足夠理由測，但沒有已證 root cause

`FUN_c0108140` (`blk_c01.c:3943`) 的 YCMAT luma 預設係數為 `1224/2403/469`，總和 4096，接近 Rec.601 權重。[C]

`FUN_c011a8b0` (`13175`) 給 GAM_TOP_RGBMAT_PL 一個 3×3 預設：

```text
[0x80, 0,    0xB3]
[0x80, 0x1D4,0x1A5]
[0x80, 0xE3, 0]
```

若用 signed 9-bit 且 unity=128 解讀，得到近似標準 YCbCr→RGB 的 `[1,0,1.3984; 1,-0.34375,-0.71094; 1,1.77344,0]`。[I] 這有助於確認內部色差矩陣，不是 LCD full/legal-range 的證明；也不能從該矩陣猜負像素是否在此裁切。

目前沒有確認 LCD 的 `16..235`／`0..255` 接受范围、硬體矩陣生效點、或 LCD panel gamma。應以灰階階梯與飽和色階同時查看原生畫面資料、相機截圖、HDMI 擷取和 LCD 拍攝區分：

- 若原生 YUV／截圖裡顏色已經平頂，LCD 校準與背光無法恢復。
- 若檔案／截圖連續、只有面板顯示丟層次，才優先追 panel range／gamma／色域。
- 擷取卡自身的 range 解讀要校對，不能把 HDMI 擷取與 LCD 的差異直接視為相機硬體差異。

本地 `IMAGE_CHANNELS.md` 記載的 develop descriptor `0xC375C05C`／base cell `0xC375C078` 是可追查的影像樣本來源，但它在部分 live idle 狀態為零；不能把此候選當成任何狀態均可用的線性 RGB tap。

## 6. 推薦下一輪證據順序

1. 重現問題時先固定曝光與 WB，用同場景 RAW 確認感光元件各通道未飽和；只有上游資訊尚在，display 改法才有可恢復的內容。
2. 記錄實際 mode、context、tone descriptor 地址／表內容、RGBLMAT 兩組係數、WB／gain、CEQ 和顯示模式。不能以選單文字推定實際 active LUT。
3. 對純灰階和飽和 LED 梯度分開做原廠／identity／平滑 shoulder LUT 比較。identity 只是一個定位工具；恢復 gamma 與色域映射才是正常觀看的交付物。
4. 若換表仍有同樣色相斷崖，測原生 pre-tone gain／矩陣縮放分支。若負通道 clip 出現在矩陣輸出，僅縮小 gain 沒有作用，應優先調整色域映射或尋找可保留負值的上游路徑。
5. 最後才設計限制在監看的 LUT／matrix 控制，並驗證 MOV、JPEG、DNG 的受影響範圍。全域資源修改不能預設為 display-only。

可行結論是「不該再把 linear tone 當完整修復」；現階段尚沒有足夠證據宣告某個硬體 clip bit 已被找到，亦沒有已驗證只改 LCD、不影響 MOV 的 patch。

## 7. 找回的歷史 patch 不能直接重用

已讀 `/Users/dido/Documents/Codex/2026-08-16/4/work/generate_stretched_curve_autorun.py`，它選 ROM **ID 83**，生成：

```text
T_stretched(x) = interpolate(T83, x × 1918 / 2047)
```

這是把 ID 83 的有效輸入區間拉滿，不是 `T(x)=x` 的 identity。輸出 `/Users/dido/Documents/Codex/2026-08-16/4/outputs/AutoRun_Stretched_ID83_Test.txt` 將 4096 bytes 寫到 `0xC3414DA8`，然後把 CH0 descriptor pointer `0xC31D7580` 改成 `0x00D0536A`。[C]

**原腳本的「known non-cache RAM」說法没有程式證據，且這塊 RAM 已證明是原生 context 1 tone scratch。** `FUN_c02d29e0` 明確重用 `0xC3414DA8`。CH0 指向它後，另一個 context 的 curve 生成可能覆蓋內容；保存 before/after 不會消除這個所有權問題。原生生成曲線路徑會呼叫 `FUN_c000e91c`，舊 Autorun 只有 `mem set` 和 `mem save`，没有等效 cache publish。[C]

因此下一輪不能照抄舊 Autorun；應由已審核的 snapshot／安裝機制建立穩定證據，再決定獨立 LUT 儲存與復原範圍。

## 8. 下一輪最小 snapshot 清單（設計，未執行）

單獨讀 RAM 指標、稍後再讀 LUT 可能跨過換表；應讓已審核的相機端 snapshot 同時保存 descriptor／context／generation，再跟隨經檢查的 LUT 地址。以下是研究所需最小集合，不是直接執行的 shell 指令。

| 集合 | 位置／內容 | 用途 |
|---|---|---|
| Scene／mode | 曝光、ISO、WB、色彩模式／各調整、錄影格式、live／record／playback 狀態；PQ 呼叫時 `param+0xF8/+0x11C/+0x118/+0x120/+0xE0` | 釘住 context 及處理狀態，不能只記選單文字 |
| Software LUT descriptors | `0xC31D7554..0xC31D75EB` | 含兩個 count、selector 與 word-address 陣列；`FUN_c011b4c8` 直接證據 |
| Active hardware LUT descriptors | `0x30200034`、`0x30200050`、`0x30200070..0x302000A8`；另一組全部 `+0x100` | 核對 RAM 登記與實際 SIGSEQ descriptor，`FUN_c01a0560` (`blk_c01.c:86135`) |
| LUT payload | 上述 active descriptor 指向的每張 LUT，各 `0x1000` bytes；一或三張，以 count／selector 為準 | 驗證真正表內容與是否在原生 scratch 被覆寫 |
| Cache／native gain | `0xC3414D28..0xC3414DA7`、`0xC2F19D40..0xC2F19D4B`；singleton `0xC3414470+0xA0/+0x198`；gain `0xC34143B8+0xB0/+0xB4` | 記錄 mode/contrast/toning cache key 與曲線指標、native headroom 分流 |
| Upstream／matrix | `0x30112740/44`、`0x30112820/24`、`0x30113494/98`；`0x30115000..3F`、`0x30115100..67`、`0x30115200..37` | gain、IGAMMA、兩組 RGBLMAT 及後續線性化候選 |
| Gamma/color stages | `0x30115804/08`、`0x30115820..A3`、`0x30115900..87`、`0x30115A00..4F`、`0x30115B00..3B`、`0x30115B80..A3` | 記錄 GAM／YCMAT／gamma 載入與 RGBMAT_PL 的實際配置 |
| Output clip/range 候選 | `0x30117B00..5F`、`0x3011D700..FB`、`0x3011D800..47`；當前 panel／HDMI mode 與輸出格式 | 區分 saturation/CEQ 與顯示端解碼；目前無已證 LCD full/legal range register |
| Image evidence | 同一穩定場景 RAW + active develop descriptor／影像 + 相機截圖；若測 LCD panel 再拍 LCD，必要時 HDMI | 只有寄存器與 LUT 無法證明哪一層像素先丟失 |

讀取 MMIO、指標追蹤、快照程式均須遵守目前 USB-shell 的已審核操作與資源所有權；這份離線設計沒有建立 live 操作授權。
