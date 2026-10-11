# Gyro2 機身端設計：每幀陀螺資料寫進 CinemaDNG (2026-10-06 討論稿)

狀態（2026-10-07）：**已實作並上機。** 現況以 §14 為準（Vd 計時、無鎖單一寫入者）；§4、§13 的鎖與 hook 計時已被取代。
讀取端（Gyroflow fork）與 DNG 檔頭空間的研究見
[GYRO2_CDNG_GYROFLOW_PLUGIN_RESEARCH.md](GYRO2_CDNG_GYROFLOW_PLUGIN_RESEARCH.md)。

標記：**[定]** = 使用者已定的框架；**[議]** = 討論中提出、尚待決定的建議；**[?]** = 待查證。

---

## 0. 實作方針 [定 2026-10-06]

- **Gyro2 是新的 sup，從零照 loader v3 寫**（`projects/usb-shell-sup/notes/LOADER_V3.md`），不在 Gyro1 上改，
  也不遷移 Gyro1。詳見 §12。
- **Gyro1 先不處理**（維持現狀，去留之後再定）。

## 1. 目標與約束

- 每張 CinemaDNG 帶「屬於自己這一幀」的原始陀螺資料，加上水平儀（加速度計）與焦點距離事件，
  壓縮後放在 **DNG 的 MakerNote 尾端**（見 §7），由 fork 的 Gyroflow 外掛轉成 Gyroflow Protobuf。
- **[定] 支援 lossless 架構**：lossless 會讓幀以非順序出現、並可能扣住幀一段時間。
  → 2026-10-06 研究（§11）後：gyro 寫入點在 lossless **之前**、且按幀順序執行，**lossless 的扣幀與亂序不影響 Gyro2**（見 §4.0）。
- **[定] gyro 與 lossless 不耦合**：兩個 sup 不知道彼此存在。
- 盡量零拷貝。

## 2. 記憶體：一塊 arena，固定位移 [定]

- gyro 透過分配器一次宣告一整片記憶體，放**所有變數、緩存與方法**。
- 方法存取變數/緩存只需 `base + 固定位移`（ARM 上可固定一個 base 暫存器）。
- [議] 位移表只維護一份來源（產生組語 `.equ` 與主機端解碼器共用），避免兩邊不同步。

## 3. 時間不靠時間戳：用「在陀螺資料流中的位置」 [定]

**核心想法（使用者）：** 以水平儀觸發、焦點移動觸發作為「搬移陀螺資料」的時機。
事件發生時**先把陀螺 ring 搬到最新，再記錄事件**，於是事件在陀螺資料流中的位置
本身就是時間 —— 不需要記錄時間戳。

- 解碼端換算：`t = 起始時間 + 位置 × 400 µs`（ODR 2500 Hz），填入 Gyroflow protobuf 的
  `sample_timestamp_us`。
- 幀邊界同理（[議]）：幀開始/結束 hook 也先搬再記位置，幀的範圍同樣不需時間戳。

### 焦點距離也不需要時間戳
- 與水平儀同一套機制，位置即時間。
- 位置代表的是 **hook 觸發的時刻**，不是鏡頭實際到位/加速度計實際取樣的時刻。
  若鏡頭回報有**固定延遲**，量一次、在解碼端當常數修正即可，不必逐筆存時間戳。
  只有延遲不固定且需要精確時才需韌體的量測時間 [?]。
- 精度需求低：Gyroflow 的焦點/焦距（呼吸、變焦）用**每幀一個值**即可（`LensData` 本就逐幀）；
  陀螺才需要次毫秒。
- 焦點不動就不觸發 → 解碼端在無事件的幀**沿用上一個值**。陀螺搬移節奏靠水平儀（約 100 Hz）
  與其他 hook 維持，不受影響。

## 4. 資料結構

> **2026-10-06 晚間更正，以 §13 為準。** 下面 §4.0 的「簡化」把使用者設計中「陀螺搬進自己的緩衝」拿掉了（筆記裡寫了保留小 log 當保險，
> 實作卻沒做），P1–P3 因此只靠每幀 hook 直接讀副處理器 ring。`A001_041`（lossless ON）MovRec 多次卡住 200 ms 以上，
> 超過 ring 的 240 ms，資料真的遺失。§13 依使用者設計重做：兩個緩衝、水平儀 hook 搬陀螺、每幀用指標切出精確對準的區間。


### 4.0 因寫入點而簡化 [定 2026-10-06]

§11 查明：每幀表頭在 **MovRec 任務處理「RAW 完成」事件時**產生（`C038C77C` DMA 複製模板），
早於 `XC_StillCreateFile__v2`，也早於 lossless 的任何介入。gyro 在這裡把資料寫進表頭後，
lossless 再怎麼延後、重排，資料都已經在那一幀自己的表頭裡，並隨 lossless 整份複製原表頭一起帶走。

因此 4.1／4.2 中**為了對付 lossless 而設計的部分不再需要**：
- 不需要 N 個每幀緩存、不需要以 `frame_seq % N` 取格、不需要「被下一輪覆蓋」的檢查。
- 每幀在寫表頭時，直接寫「上一幀寫到的位置 → 現在」這段樣本（加前後 guard）即可。

**剩下的記憶體需求**只有兩個，都與 lossless 無關：
1. **陀螺 log（可小）**：讓兩次寫表頭之間的樣本不被副處理器 ring（600 筆 ≈ 240 ms）覆蓋。
   9 fps 的幀間隔約 111 ms < 240 ms，理論上可在寫表頭時**直接讀副處理器 ring**（一次拷貝，supmod 就是這樣）；
   但 MovRec 任務若偶爾延遲過久會漏樣本，所以保留水平儀觸發的 `drain()` 搬到小 log 當保險
   （容量數百 ms～1 s 即可）。
2. **事件 log**：記錄上一幀以來的水平儀／焦點事件與位置。

4.1 的「位置即時間」與 4.2 的「事件另存、記 `write_idx`」原則都保留；
`frame slots[N]` 簡化成單一的「上一幀寫到哪」游標。

仍需上機確認（§9）：「RAW 完成」事件是否嚴格照幀序處理；lossless 掉幀時是否整幀不產生（而非只缺表頭）。

### 4.1 使用者原始方案 [定 → 部分被 4.0 取代]
- N 個每幀緩存（N = 4～6 或更多，需測試），每個要能容納**最極端 9 fps** 一幀的長度。
- 內容：原始陀螺資料，中間插入帶 tag 的水平儀資料/焦點距離資料。
- 每幀開始或結束時，依序輪替「目前使用的緩存」。

### 4.2 建議的等價改良 [議 → `frame slots[N]` 被 4.0 取代]
把「每幀緩存」拆成三塊，**資訊與 4.1 相同**（事件位置仍是隱含時間），只是擺放方式不同：

```
gyro log ring   連續追加的陀螺樣本；寫入位置 write_idx 為 32-bit 單調遞增（不歸零）
event ring      {write_idx, type(水平儀/焦點), value}  ← write_idx 就是 4.1 裡 tag 前面的樣本數
frame slots[N]  {frame_seq, first_idx, last_idx, first_evt, last_evt}   以 frame_seq % N 取格
```

| | 4.1 tag 插在陀螺資料中 | 4.2 事件另存，記 write_idx |
|---|---|---|
| 位置資訊 / 需不需要時間戳 | tag 前的樣本數 / 不需要 | write_idx / 不需要 |
| 陀螺資料是否連續 | 被 tag 打斷 | 連續 |
| 用 `[first,last)` 直接取一幀 | 否，要逐筆跳 tag | 是 |
| 容量 | 每格都要 9 fps 最壞長度 | 長短幀共用；容量 = ring 涵蓋秒數，與 N 無關 |
| 覆蓋檢查 | 難（tag 長度不定） | `write_idx - first_idx > capacity` 一個減法 |
| guard 樣本（前後多帶） | 要另外存 | 範圍往外擴即可 |

9 fps 量級參考：1/9 s × 2500 Hz ≈ 278 筆 × 6 B ≈ 1.7 KB/幀（未含事件與 guard）。

**DNG 內的格式仍可以是插入式 tag**：寫入 DNG 時邊讀邊編碼，編碼器同時走 gyro ring 與
event ring，編到某事件的 write_idx 就在輸出插入該 tag。記憶體分開存不影響外掛端格式。

## 5. Hook 與流程

| Hook | 動作 |
|---|---|
| 水平儀更新 [定] | 若錄影中：`drain()` → 記錄水平儀事件（位置 + 值） |
| 焦點位置變化 [定] | 若錄影中：`drain()` → 記錄焦點事件（位置 + 值） |
| ~~每幀開始或結束~~ | 不再需要獨立的幀 hook：「RAW 完成」寫表頭那一刻就是幀標記（`frame_mark`），見下列 |
| 產生 CDNG metadata（`C038C77C`，§11.4）[定 2026-10-06] | `drain()` → 記下 `frame_mark` → 把「上一幀游標 → 現在」的樣本、事件寫成 FSG2 資料塊進**模板**零尾 → 更新游標 → 呼叫原 DMA |
| 停止錄影 [定] | 補齊剩餘的陀螺資料（最後一幀尾段） |

- **[議] `drain()` 是唯一、可重入的搬移函式**：讀副處理器 ring head，把上次讀到之後的新樣本搬進
  gyro log ring。任何 hook 都可先呼叫它；多呼叫只會把位置往前推，不破壞「先搬再記」的語意。
  副處理器 ring 600 筆 ≈ 240 ms（2500 Hz）一圈，任一 ≥ 5 Hz 的觸發都足以不漏樣本。
- **[議] 產生表頭的 hook 也先 `drain()`**，讓該幀尾段盡量已經進來。
- 搬移漏了樣本（MovRec 延遲過久、ring 已繞過）時：不寫錯的資料，設「此幀資料遺失」旗標，外掛端插空幀。
  （原本為 lossless 設計的「被下一輪覆蓋」檢查已不需要，見 §4.0。）

## 6. 零拷貝盤點

陀螺來源是副處理器共享 RAM 的 600 筆 ring（`0x2E00644C`，見 GYRO_IMU_GYROFLOW.md），
約 240 ms 就被覆蓋，所以最少兩次拷貝：

| 拷貝 | 可省？ | 說明 |
|---|---|---|
| 副處理器 ring → gyro log ring | 不可 | 來源很快被覆蓋 |
| gyro log ring → DNG 表頭 | 不可 | 目的地（該幀表頭）在產生時才存在；[議] 壓縮直接做在這次拷貝裡，不留中間暫存 |
| DNG 表頭 → lossless arena | **零額外** | lossless 本來就每幀 `memcpy` 整份原表頭（含 MakerNote）；gyro 資料就被順便帶走 |

4.1 與 4.2 的拷貝次數相同（都是兩次）；4.2 的好處在容量與檢查，不在次數。

## 7. 資料放在哪：MakerNote 尾端 [定 2026-10-06]

### 7.1 位置
MakerNote（EXIF 標籤 `0x927C`）是 EXIF 留給廠商的私有區塊，其他軟體視為不透明資料、原樣保留。
fp CinemaDNG 的 MakerNote（SIGMA，97 筆）**宣告長度比實際用到的多，尾端是一段全零空間**。
以 FHD 樣本 `A001_001_20260817_000244.DNG` 實測：

```
0x00008  IFD0（58 筆）
0x04514  ┌ MakerNote 開始（宣告 54,338 B）
         │   SIGMA 的 97 筆參數
0x0EE12  │   尾端全零 11,076 B        ← Gyro2 的資料寫在這裡
0x11956  └ MakerNote 結束 = DNGPrivateData 開始（SIGMA_EXTH…，6,734 B）
0x13400  影像資料 (78,848)
```

- MakerNote 宣告範圍**剛好結束在 DNGPrivateData 起點**，尾端零區完全屬於 MakerNote。
- 零區長度隨 MakerNote 實際內容浮動：本機 2,696 張中觀察到 **3,270～11,076 B**。

### 7.2 為什麼選它（相對於「擴充表頭 + IFD0 標籤 65000」）

| | IFD0 新增標籤 65000（原方案，改為備案） | MakerNote 尾端（採用） |
|---|---|---|
| 改檔案結構 | 要：IFD0 58→59 筆、表頭變長、影像起點後移 | 不用：寫進既有零區 |
| 機身端 | 要改寫表頭產生程式 | 在固定範圍內寫資料 |
| 與 lossless | lossless 寫死表頭長度、用預建 IFD 樣板 → **資料遺失**，lossless 必須改 | lossless 整份複製原表頭 → **自動帶走，lossless 不用改** |
| 外掛找資料 | 讀 TIFF 標籤 | 讀 EXIF → MakerNote 範圍，在尾端掃 magic |
| 容量 | 自訂 | 受零區限制，最差約 3.2 KB |
| 其他工具改寫 DNG | 較可能保留 | 可能丟失（MakerNoteSafety = 0）；Resolve 不改寫 DNG，主流程不受影響 |

→ **gyro 與 lossless 的解耦由位置本身達成，不需要表頭契約。**
原 §7「表頭契約」（lossless 改讀 `StripOffsets`、執行期通用複製 IFD）降為備案，
只在 MakerNote 尾端容量不足時才需要。

### 7.3 寫入規則
- 每幀寫入前**從當幀 MakerNote 實際內容判斷零區起點**（不寫死位址），並確認資料長度 ≤ 零區長度；
  放不下時寫「截斷」旗標，不越界、不碰 DNGPrivateData。
- 資料從零區**尾端往前對齊**或從零區起點加安全間隔寫入 [議]，避免貼著 SIGMA 的最後一筆資料。
- 資料塊自帶 magic、版本、長度、CRC，外掛靠 magic 定位並驗證。
- **magic = `FSG2`**（定 2026-10-06）。刻意避開 sigma-fp-supmod 已在同位置使用的 `FPG2`（格式不同，見 §10）。
- 資料塊格式（外掛 `feature/cdng-makernote` @ `a235e88` 已實作）：
  `magic "FSG2" | version u8 = 1 | kind u8 (1 = protobuf Main；2 保留給壓縮格式) | reserved u16 = 0 |
  length u32 | payload | CRC-32 u32`，整數一律 little-endian。

### 7.4 kind 2 payload 格式 v1 [定 2026-10-06]

決定：樣本**不壓縮**（原始 i16×3）；感光模式**直接帶數值**（外掛不需模式表）；
曝光時間**不放**，外掛讀 DNG EXIF ExposureTime（需驗證它反映實際曝光 [?]）。
整數一律 little-endian。外層 FSG2 資料塊已含長度與 CRC，這裡不重複。

| 位移 | 型別 | 欄位 | 說明 |
|---|---|---|---|
| 0 | u8 | `fmt_version` | = 1 |
| 1 | u8 | `orientation` | 0 = `xyz`（已驗證） |
| 2 | u16 | `flags` | bit0 資料被覆蓋遺失；bit1 放不下被截斷；bit2 片段第一幀；bit3 片段最後一幀；bit4 OIS 開；bit5 電子防震開；bit6 帶鏡頭校正表 |
| 4 | u32 | `clip_id` | 開始錄影時的 TickTimer 值，辨認同一段 |
| 8 | u32 | `frame_seq` | 原生幀號，從 0 起；外掛用來偵測掉幀 |
| 12 | u32 | `sample_period_ps` | 陀螺取樣週期，**皮秒**（Gyro1 實測 400,085,400 = 2499.466 Hz；ns 會累積漂移） |
| 16 | f32 | `gscale` | rad/s / count（Gyro1 實測 0.000137923，不是理論 1/131） |
| 20 | f32 | `ascale` | g / count（0.0009765625） |
| 24 | u32 | `readout_ns` | 實際模式的讀出時間（u32：14-bit 模式可達 27.5 ms） |
| 28 | u16 | `mode_id` | `S_MODE_RUN`，僅供除錯/追查 |
| 30 | u16×4 | `crop_x/y/w/h` | 讀出視窗在感光元件上的位置（感光元件像素） |
| 38 | u16 | `frame_mark` | 幀 hook 觸發時的位置，相對 `base_idx` |
| 40 | u32 | `base_idx` | 本塊第一筆樣本的全域序號（自錄影開始累計，不歸零） |
| 44 | u16 | `n_samples` | |
| 46 | u16 | `n_events` | |
| 48 | i16×3 × n | samples | 原始 X, Y, Z（副處理器 ring 的 `X,Y,pad,Z` 去掉 pad） |
| … | 事件 × n | events | 每筆 `pos u16`（相對 `base_idx`）、`type u8`、`len u8`、`value[len]` |
| … | 504 B（僅 bit6） | lens table | 見下方「鏡頭畸變」 |

事件類型：1 = 水平儀（`len 6`，i16×3 原始值）；2 = 焦點（`len 4`，u32 原始值）。
帶 `len` 讓外掛能跳過不認識的類型，之後加類型（例如變焦焦距）不必改版本。

**鏡頭畸變：原始校正表，只放在片段第一幀** [定 2026-10-06，選項 A']

Gyro1 (v1.14) 在錄影結束時把韌體的鏡頭校正表內插、擬合成 `.json`，整段只有一組值。
Gyro2 改成把**原始表**原樣帶出，數學移到外掛：

| 欄位 | 大小 | 來源 | 說明 |
|---|---|---|---|
| `calib_focal` | u32 | `0xC307CDF0` | 校正時的實際焦距，0.1 mm（例：Art 40mm 標 40.0、實測 39.4） |
| `axis[5]` | u32×5 | `0xC307CE2C` | 對焦支撐點，2^24 / 物距 mm（0=∞、…、55924=300 mm） |
| `nodes[5][3][4]` | f64×60 | `0xC307D270` | 5 對焦點 × RGB 三平面 × 4 徑向係數，記憶體原樣（一次 memcpy 480 B） |

- 只在 `flags` bit6 的那一塊出現，正常就是片段第一幀（bit2）。鏡頭在一段內固定，不必每幀重複。
- 外掛：取序列中帶表的那一幀，依**每幀**對焦距離（EXIF SubjectDistance，或焦點事件）線性內插
  綠平面 → 取出 `kr0`（呼吸）當焦距縮放 → 擬合 OpenCV fisheye 4 係數 → 逐幀 `LensData`。
  移植 `fpSup/gyro/lens_dist_table.py` 的 `interpolate()` / `coefficients()`，
  並以 Gyro1 同素材輸出的 `.json` 對照驗證。
- 容量：只多在第一幀。9 fps 第一幀約 2.0 + 0.5 = 2.5 KB，仍低於最小零區 3,270 B。

**沒有表時的退路**（只拷中間一段、或第一幀遺失）：每張 fp DNG 的 **OpcodeList3 本來就有
WarpRectilinear**，內容是已依對焦內插好的係數（實測 FHD 樣本綠平面
`kr0..kr3 = 1.000334, −0.01484, 0.00518, −0.009761`，含呼吸），Gyro1 也驗證過它等於內插表的結果。
外掛可逐幀讀它，再配 EXIF FocalLength（標稱焦距，少了校正焦距的約 1.5% 修正）。
[?] 待驗證：錄影中改對焦時 WarpRectilinear 是否逐幀更新；相機關閉鏡頭校正時 opcode 是否仍存在。

**外掛已實作（`e6a8fcc`，`common/src/lensfit.rs`）**：照 Gyro1 機身算法移植——
焦距用校正焦距（不合理時退回鏡頭回報值）、`focal_px = 輸出寬 × 焦距 / (35.9 × 讀出寬/6000)`、
以每幀 EXIF SubjectDistance 內插綠平面、`kr0` 乘到焦距、在 ρ = 0.55/0.85/1.0 collocation 擬合 fisheye k1–k3（k4 = 0）。
- 對 fpSup `test_distfit.py`（LUMIX S 40/F2 機身讀出的表）黃金值：係數與焦距誤差 < 1e-8。
- **真實交叉驗證**：`A001_150`（LUMIX S 40/F2）DNG 記錄 SubjectDistance 0.3 m，其 WarpRectilinear 綠平面
  與機身表 300 mm 節點完全相同（< 1e-9）→ **EXIF SubjectDistance 就是相機內插用的對焦距離**，外掛的對焦來源正確。
- 逐幀給 `LensData` 後，telemetry-parser 自行合成 lens profile，gyroflow-core 不再去查鏡頭資料庫
  （先前 `CameraIdentifier.lens_model` 為空的問題因此不影響）。

**鏡頭資訊不放進資料塊**：錄影中不能換鏡頭，鏡頭在一段內固定；且每張 DNG 的 EXIF 已帶
`LensModel`、`FocalLength`、`LensInfo`（例：`28mm F1.4 DG HSM | Art 019`、`LUMIX S 40/F2`），
外掛直接讀。例外：
- 變焦鏡錄影中轉焦：EXIF `FocalLength` 是否逐幀更新 [?] —— 若否，加事件類型 3（焦距）。
- 手動/轉接鏡：EXIF 沒有或不正確 → 外掛讓使用者手選 lens profile。
- 畸變 profile 不在 DNG：外掛以 `LensModel` 對應 Gyroflow 鏡頭資料庫，或用我們的產生器（`make_gyroflow_lens_profile.py`）。

外掛換算：`t(i) = (base_idx + i) × sample_period_ns`，加上一個校正過的常數偏移；
相鄰幀的 guard 樣本可重疊，外掛以全域序號去重，掉幀也不會錯位。
單位換算在外掛做：陀螺 `raw × gscale` rad/s → deg/s；水平儀 `raw × ascale × 9.80665` m/s²。
水平儀先照 Gyro1 `gcsv_rows.S` 規則轉成陀螺軸（X = 原生 Y、Y = −原生 X、Z = Z），再與陀螺共用 `xyz`；
外掛以「保持上一次讀值」填每筆樣本（protobuf 路徑每筆都會推 accel，空的就是 0）。
規格以外掛 `common/src/fsg2.rs`（解碼器＋參考編碼器）為準。

### 7.5 容量估算（kind 2 v1，原始 i16×3）
每塊 = FSG2 外框 16 B + payload 標頭 48 B + 樣本 6 B×n + 事件（水平儀約 100 Hz，每筆 10 B）。
guard 以前後各 16 筆估。

| 幀率 | 樣本/幀 | 樣本 + guard | 事件 | 合計 | 最小零區 3,270 B |
|---|---|---|---|---|---|
| 23.976 | ≈104 | ≈816 B | ≈5 筆 ≈50 B | ≈0.9 KB | 充裕 |
| 9（最極端） | ≈278 | ≈1,860 B | ≈12 筆 ≈120 B | ≈2.0 KB | 放得下，餘約 1.2 KB |

## 8. Gyroflow protobuf 欄位盤點：還缺什麼

對照 `gyroflow.proto`。原則：**DNG 每幀本來就有的值由外掛讀 DNG 標籤，不重複放進 payload**；
payload 只放 DNG 沒有、只有機身知道的東西。

### 8.1 缺、必須補（依優先順序）

1. **幀時間錨點** —— `FrameMetadata.start_timestamp_us`（第一列讀出瞬間）/ `end_timestamp_us`。
   我們只有「幀 hook 觸發時的陀螺位置」，hook 時刻與實際讀出的**常數偏移未量測** [?]。
   protobuf 路線 `has_accurate_timestamps = true`，Gyroflow **不會再用 optical flow 自動對齊**，
   偏移錯就直接穩定錯。`end = start + 讀出時間`，讀出時間取自模式表
   （`make_gyroflow_lens_profile.py`，例 OG3K30 = 12.435 ms）。
2. **感光元件幾何**（每段固定）—— `crop_x/y/w/h`、`pixel_pitch_x/y_nm`、`sensor_pixel_width/height`、
   `frame_readout_time_us`、`frame_readout_direction`。機身 `profilegen.S` 已在算；
   必須用**實際執行中的模式**（`S_MODE_RUN`），避免 `LENS_PROFILE_WRONG_SIZE_WITH_OG3K.md` 的尺寸退回問題。
3. **外掛讀 DNG EXIF 與 MakerNote 尾端**（見 8.2、§7）—— 原型目前只讀 IFD0 標籤 65000，
   要改成：解析 ExifIFD → MakerNote 範圍 → 在尾端找 magic。
4. **鏡頭 profile** —— 機身產生的 profile JSON 直接放 `Header.camera.lens_profile`。
   **變焦焦距**目前沒有 hook，影響視角、比焦點重要 → 決定：加焦距變化 hook，或用每幀 EXIF FocalLength。
5. **防手震狀態** —— 鏡頭 OIS（L 卡口 OS 鏡）無位移資料、Gyroflow 無法補償 → 建議拍攝時關閉，
   並把 OIS 開關寫進 payload，外掛發現開著時警告。fp 電子防震在 CinemaDNG 下是否作用 [?]，
   若會則必須關閉並記錄狀態。fp 無 IBIS。
6. **加速度計** —— MMA8452Q 軸向**未驗證**（未驗證的 accel 會經 VQF 融合污染結果，
   見 `GYROFLOW_ORIENTATION_SOLVED.md`）；單位要 m/s²（`raw/1024 × 9.80665`）。
   第一版照樣記錄水平儀事件，但**不填進 `IMUData.accelerometer`**，驗證軸向後再開。
7. **陀螺校正** —— 單位 deg/s（`raw/131`），`imu_orientation = "xyz"`（已驗證）。
   ring 原始值是否已扣零點 offset [?]（校正區塊 `0xC307B548 +0x11C`）。

### 8.2 DNG 每幀已有，外掛直接讀

| protobuf 欄位 | DNG 來源 |
|---|---|
| `exposure_time_us`（也用於曝光中點 = start − exposure/2） | EXIF ExposureTime |
| `iso` | EXIF ISO |
| `LensData.f_number` / `focal_length_mm` | EXIF FNumber / FocalLength、DNGLensInfo |
| `LensData.focus_distance_mm` | **EXIF SubjectDistance（每幀都有，例 0.403 m）** |
| 白平衡 | AsShotNeutral |
| `file_frame_rate` 等 | FrameRate (0xC764) |
| `camera_model` / `camera_serial_number` / `firmware_version` | Model / CameraSerialNumber / Software |
| `frame_width/height` | DefaultCropSize |

→ 既然每幀有 SubjectDistance，**焦點 hook 可能多餘**（Gyroflow 只需每幀一個焦點值）。
它唯一的額外價值是多一個陀螺搬移觸發來源，而水平儀約 100 Hz 已足夠。

### 8.3 可以不管
GPS、`quaternions`（送原始 IMU 由 Gyroflow 融合）、EIS mesh、IBIS、磁力計、`color_profile`。

## 9. 待確認

1. ~~「CDNG custom metadata 生產的位置」~~ → **已查明（§11）**：每幀表頭在 MovRec 任務處理 RAW 完成事件時，
   由 `FUN_c038c5f8` 改寫模板後 DMA 到幀緩衝區，早於 `XC_StillCreateFile__v2` 與 lossless。
2. ~~表頭產生時點~~ → 在 **RAW 完成（event 5）之後**，該幀曝光與讀出都已結束，尾段樣本已在 ring 裡，
   不需回填。
3. ~~N 由 lossless 扣幀長度決定~~ → 不再需要（§4.0）。改為確認：「RAW 完成」事件是否嚴格照幀序處理；
   lossless 掉幀時是否整幀不產生。由 `C038C77C` 探針（寫固定圖樣＋幀號）在開著 lossless 時一併驗證。
4. [?] 鏡頭焦點回報的延遲（一次性量測，做解碼端常數修正）。
5. [?] 水平儀觸發的實際頻率與抖動（是否穩定約 100 Hz）。
6. ~~4.1 或 4.2 的選擇~~ → 以 §4.0 的簡化版為準（單一游標＋小陀螺 log＋事件 log）。
7. [?] 幀 hook 時刻與第一列讀出時刻的常數偏移（見 §8.1-1，最影響結果）。
8. [?] ring 陀螺原始值是否已扣零點 offset。
9. [?] fp 電子防震在 CinemaDNG 模式是否作用；OIS 開關狀態從哪裡讀。
10. 焦點 hook 是否保留（每幀 EXIF SubjectDistance 已足夠）；變焦焦距是否加 hook。
11. [?] 所有模式（UHD、OG2K/3K、120 fps、14-bit 等）MakerNote 尾端零區的最小值；
    以及韌體是否每幀都把該區清零（避免殘留上一幀資料）。
12. ~~magic 名稱~~ → 已定 `FSG2`。是否與 sigma-fp-supmod 協調共用格式仍可討論。

## 10. 對照：sigma-fp-supmod (julienacquaviva, R120, 2026-10-02)

公開內容只有 README 與執行檔（`AutoRun.txt`、`BOOT.BIN`、`FPOG.BIN`），無原始碼。
README 致謝 Bei (ijigen) / fpSup，聲明為獨立實作，R46 起以 Claude 開發。

| 項目 | supmod | 我們 |
|---|---|---|
| 架構 | 單一整合 mod（OG、14-bit、lossless、陀螺、UI） | 模組化 sup，以 fpSup-Merge 合卡 |
| 陀螺位置 | 每幀 `FPG2` 塊，MakerNote 尾端 | 同位置（本節決定） |
| 每幀時間資訊 | 讀出時間 + 曝光時間（R116 以曝光時間對齊） | 規劃中（§8.1-1） |
| 軸向 | pan / tilt 確認，roll 正負未確認 | `xyz` 三軸皆驗證 |
| Lossless | 內建；相機自行中止時結尾可能缺幀 | 獨立 lossless-sup |
| 讀取端 | 自製 Resolve OFX（顯影＋穩定），未公開 | fork 官方 Gyroflow OFX，Resolve 顯影 |
| 驗證 | 每 build 跑模擬器驗證鏈，120 builds | unicorn 模擬 + 上機自測 |

## 11. 韌體：每幀表頭在哪裡產生（2026-10-06 離線研究，未上機）

來源：完整反編譯 `out/decomp/full/` 與 `out/MAIN_c0000000.bin`；兩個子代理分別追原廠路徑與拆 supmod R120 的 FPOG.BIN，
關鍵指令已逐條對過映像。[V] = 反編譯/反組譯看過；[I] = 推論。

### 11.1 原廠流程
- **開錄時建一次** [V]：`FUN_c0378a50` → `FUN_c038a138` → DataPool `v20` → `FUN_c00c1ca0`（type 2）建出 IFD0、Exif、
  MakerNote（`XC_MakerNoteIfd`，"SIGMA\0\0\0"+0x0104）、0xC634；在 `C0378EB0` 經 format vtable +0x2C
  （`XC_StillFileFormatDngTh::v9 @C06A4C48`，`TiffSegment__v2 @C00B9DF8`）序列化成**模板**，
  長度對齊到 0x400（= 0x13400）存 request+0x14C。錄影單例 `0xC358DB98`：+0 DataPool、+4 tagMgr、+8 format、
  +0xC 表頭長、**+0x10 模板位址**。（`FUN_c00c2728`/`c00c2800` 是播放/轉檔路徑，不在錄影上。）
- **每幀** [V]：`MovRecFuncStateCinemaDng__v38` 收到 event 5（RAW 完成）→ `FUN_c038bd98`：
  1. `C038BFD0: bl FUN_c038c5f8` —— 改寫模板中會變的值：`XC_RecMgrTagCinema::v1 @C03A8490`（表 `C0B9ED9C`，20 筆：
     0x132、0xC65D、0xC763、0x9003/4、0x9010-12、0xA420、MakerNote 數項；flag 0x20 的每 10 幀才更新），
     再同步通知 observer（例：0x829A/0x9203、0x9206、0xC74E）；寫法都是 `FUN_c05a4bc0` 找位置後原地 memcpy。
  2. **`C038C77C: blx 0xC00FBB90`** —— DMA 把整份模板（`{src 模板, dst=[req+0x4C]−[req+0x14C], len}`）複製到
     該幀 RAW 前方；flags=0 時同步等完成。
  3. `C038BFE4..BFF0` 取 vtable+0x10、`blx r3` → `XC_StillCreateFile__v2 @C037DD50(this, [req+0x10FC], 1)` 存檔。
- 實檔佐證 [V]：A001_001 的 851 幀間只有 0xC61A、0xC65D、0xC763、0xA420、0x9203、0x9206、0xC74E 與 MakerNote
  0x100/0x117/0x11A/0x120 會變。
- 執行情境：MovRec 任務（不是中斷、不是 writer 任務）。lossless-sup 掛在更下游的 writer（`C03A5490` wrapper），
  supmod 的 lossless 掛在 `C038BFE4`；兩者都在表頭複製之後。

### 11.2 MakerNote 尾端零區的真面目 [V]
MakerNote 最後一個標籤是 **0x0200（UNDEFINED，固定 0x4000 B）**，由 `FUN_c06a5630` 建立，內容是 DataPool 的 16 KB
側資訊（`DataPool::v1 @C00565F8`）。檔案 0xD956..0x11956，結束點正好接 0xC634。尾端零是這 16 KB 沒用到的部分，
**不是正式保留區**，大小隨內容變（實測 3,270～11,076 B）。整段 0x200 資料在一段錄影內各幀都不變。

### 11.3 supmod R120 的做法（對照）[V]
- 把 `C038BFE4` 的 vtable 讀取改成 `movw/movt r3,#0xC0734171`（原本 `blx r3` 不動）→ 替換函式先呼叫 FPG2 寫入器
  （`0xC1468540`，放在掏空的 XCI 區），再分流到 LJ 壓縮或原廠 `C037DD50`。也就是**表頭已 DMA 進幀緩衝區後**才寫。
- 寫入器：驗 `II*\0`、IFD0@8 → 0x8769 → 0x927C（count ≥ 0x1000）→ **寫在 MakerNote 結尾 − 0xC00，且這 3,072 B
  必須全零才寫**（不覆寫、不重複）；**magic 最後寫**當提交標記。曝光從**該幀表頭自己的 EXIF 0x829A** 讀；
  readout 查自帶的模式表。陀螺直接讀 `[0xC31E3FCC]+0x60` 的 ring（同我們），每幀拉「上次索引+1..目前」最多 500 筆，
  時間用 `FUN_c002b6e0`。沒有 hook 2.5 kHz 陀螺執行緒。

### 11.4 Gyro2 的 hook 點建議
**首選：`C038C77C: blx 0xC00FBB90`（DMA 呼叫點）**，在呼叫前把 FSG2 資料塊寫進**模板**的 0x200 零尾，再呼叫原 DMA。
- 該處 [V]：r0 = sp+0x1C 指向 `{src 模板, dst 幀表頭, len}`，r5 = request，r6 = tagMgr，r4 = DataPool；
  幀號可用 `[r6+0x174]`（每幀 +1，此時 = 序號+1）或 `[req+0x10FC]`。
- 好處：資料隨原廠同一次 DMA 進幀，不用自己處理幀緩衝區的 cache；跟 lossless（下游 writer）與 supmod（`C038BFE4`）
  都是不同的點，**解耦成立**。
- 注意：
  - **模板會帶著上一幀的內容** → 每幀都要寫；寫不出來時要把區塊清零或寫「遺失」旗標，否則讀者會讀到上一幀的資料
    （FSG2 有 `frame_seq` 與 CRC，外掛可再加「frame_seq 必須遞增」檢查）。
  - CPU 寫模板後 DMA 讀模板：原廠 `FUN_c05a4bc0` 也是 CPU 寫，推測 DMA 函式內有 cache 維護（`FUN_c00fb5c0`/`fb618`）[I]，
    **需上機驗證**；保險做法是寫完自己 clean 該範圍的 D-cache。
  - 位置不寫死：開錄第一幀從 IFD0 → 0x8769 → 0x927C → 0x200 解析模板內的零尾，確認全零後才使用；
    寫入長度上限取零尾長度（最小約 3.2 KB，符合 §7.5 的 2.5 KB 估算）。
  - MovRec 任務內不可阻塞。
- 備選：包住 `C038BFD0` 的 `bl FUN_c038c5f8`，在它返回後直接寫幀緩衝區（`[req+0x4C]−[req+0x14C]`），但要自己 clean D-cache。

### 11.5 對設計的影響
- 表頭在 **event 5（RAW 完成）** 時產生 → 該幀曝光與讀出已結束，尾段陀螺樣本已在 ring 裡：§9 第 2 項解決，不需回填。
- 「幀 hook」可以直接用這個點：`frame_mark` = 此刻的陀螺位置，對應「RAW 完成」時刻；它與第一列讀出的常數偏移
  （`HOOK_TO_READOUT_US`）仍需上機量測。
- 曝光時間可比照 supmod 從**該幀模板的 EXIF 0x829A** 讀（外掛端已經從 EXIF 讀，不需放進資料塊）。

## 12. 實作：照 loader v3 從零寫 Gyro2 [定 2026-10-06]

### 12.1 為什麼重寫而不改 Gyro1
- Gyro1 v1.14 約 6,100 行組語，最大的幾塊都是寫檔：`writer_core.inc.S` 1,470、`gcsv_task.S`+`gcsv_rows.S` 1,194、
  `gcsv_json.S`+`gcsv_dist.S`+`distfit.inc.S` 1,317、`ring_task`/`stream_space`/`mpool*` 約 800 ——
  Gyro2 沒有自己的檔案（資料隨原廠 DMA 進表頭，§11）、擬合移到外掛，這些都用不到。
- 執行情境、hook 點、輸出方式都不同（Gyro1：寫檔任務＋sidecar；Gyro2：MovRec 任務內寫模板）。
- loader v3 的原則 1（每個 sup 一整塊記憶體、固定長度變數與方法、相對位置）就是 §2 的 arena 設計；
  v3 筆記把 Gyro1 遷移估為「中」（約 170 處 `BLOBBASE` 巨集、job pool 併塊、刪 `gsup_launch` 複製與 `0xC3757A7C`、
  4 個 hook 改 `chain_next`、主機工具），且多半花在 Gyro2 用不到的寫檔部分 → 直接照 v3 寫新的。

### 12.2 沿用的已驗證模組（拿邏輯／位址，改寫成 v3 的 PC 相對）
| 來源（`fpSup/gyro/`） | 用途 |
|---|---|
| `gyro_drain.S` | 事件觸發的 ring 搬移 = §5 的 `drain()` |
| `accel_hook.S`（`0xC050D47C` 一帶） | 水平儀 hook：觸發 `drain()`、記事件 |
| `imu_stream.inc.S` 的 ring 讀取 | 副處理器 ring 指標鏈、樣本格式 |
| `rec_trigger.S` | 錄影開始／停止 |
| `profilegen.S` `pg_readout_us` 與幾何 | `readout_ns`、crop 視窗 |
| 校正表位址與 `pg_dist_focal` 規則 | 鏡頭表只 memcpy |

### 12.3 Gyro2 在 v3 的樣子
- 一個檔 `\fpSup\20GYR2.BIN`（名稱與前綴待最後定），`sup_id = 'GYR2'`，標頭 `FSB1`。
- entry：claim `C038C77C`（呼叫點 hook，`CHAIN`）、claim 水平儀 hook（`CHAIN`）→ 任一失敗 RELEASE；
  全成功才寫 hook → 回 KEEP。
- 與 lossless：不同位置，可並存（lossless 在下游 writer）。與 Gyro1／Base：`EXCL` 或 sup_id 互斥（v3 已列「gyro 兩版」）。
- 塊內：上一幀游標、小陀螺 log、事件 log、開錄時解析的模板零尾位置與長度、模式幾何；全部 PC 相對，build 檢查無絕對重定位。

### 12.4 依賴與順序
- v3 加載器與 claim 服務尚未完成（遷移順序 shell → lossless → gyro；第 1 步 shell 已離線完成、未上機）。
  Gyro2 上機要等加載器可用。
- 在那之前先在 **fp-unicorn-emulation** 裡開發與驗證核心：
  1. `C038C77C` 探針：只寫固定圖樣＋幀號進模板零尾（先驗 hook、零尾解析、DMA 帶進幀）；
  2. ring 讀取＋FSG2 kind 2 編碼（以外掛 `fsg2::encode` 為逐位元組規格）；
  3. 水平儀事件、模式幾何、鏡頭校正表；
  4. 加載器可用後上機：開著 lossless 驗幀號連續（§9），再量 `HOOK_TO_READOUT_US`。

### 12.5 進度
- **P0 探針（2026-10-06，模擬通過，未上機）**：`projects/gyro2-sup/`。v3 sup `20GYR2.BIN`（1,260 B）在 `C038C77C`
  寫 64 B 探針塊進模板零尾。13 個模擬測試（真的 sloader、真實 fp 表頭三種、與 v3 lossless 同卡）、突變 10/10。
  模擬中確認：v3 lossless 掛 `C038BFF0`（存檔呼叫），在 Gyro2 的表頭 DMA 之後，兩者不共用位置。
  上機步驟見 `projects/gyro2-sup/README.md`（**上機前先問使用者**）。
- **P0 上機（2026-10-06 17:15–17:30，FHD CinemaDNG，v3 卡：LOADER + 00SHELL + 10LOSS + 20GYR2）**：
  - `LOAD.LOG`：`20GYR2.BIN` LOADED、`C038C77C` 寫入 `BL` 跳板、3/3 sup 載入。
  - `A001_027`（59.94p，138 幀）、`A001_028`（29.97p，23 幀）、`A001_029`（同一開機的第二段，30 幀）：
    **每一幀都有探針塊**、位置 `0xEE54` 一致（零尾 `0xEE14` 起 11,074 B）→ hook 每幀執行、**CPU 寫模板後 DMA 有帶進幀**
    （DCCMVAC 的做法在機身成立）、`verify_probe.py` PASS。
  - 時間：hook 間隔中位數 = 幀間隔（59.94p 16,681 µs、29.97p 約 33,380 µs）；每段第一個間隔較短（5.2 ms）。
  - **更正子代理推論**：`[r6+0x174]` tag 計數器逐幀 +1、每段**從 3 開始**（不是 1）；`[r5+0x10FC]` 是 **0–95 循環的 request 槽位**，
    不是幀號。→ 新一段改以「計數器不連續或停頓 > 0.5 s」判斷（機身第二段驗證有效：計數器回到 3、重新解析）。
    Gyro2 的 `frame_seq` 用自己每段的計數。
  - **lossless 實際壓縮（使用者開啟後，17:32）**：`A001_030`（FHD 29.97p，55 幀；第 1 幀未壓縮、其餘 54 幀被 10LOSS 壓縮）
    **55 幀全部有塊**、計數器與本段幀數逐幀連續、`verify_probe.py` PASS。抓兩個完整壓縮幀（704,512 B）：根 IFD 在
    payload 之後（`0xABC00`，Compression=7、tile），從它走 Exif → MakerNote（`0x4514`）→ 0x0200 → 塊（`0xEE5C`），
    **塊被正式的標籤鏈引用**。→ §4.0「lossless 不影響 Gyro2」在機身成立。
  - 這段的塊位置是 `0xEE5C`（零尾 11,066 B），前幾段是 `0xEE54`：SIGMA 0x200 資料每段長度不同，每段重新解析是必要的。
- **P1 陀螺資料（2026-10-06 18:00，模擬 14 測試＋突變 17/17；上機通過）**：`20GYR2.BIN` 2,004 B。每幀在同一 hook
  讀副處理器 ring（同 Gyro1 `gyro_drain.S` 的指標鏈），寫 FSG2 kind 2（外框 + 48 B 標頭 + i16×3 樣本 + CRC-32）。
  新一段往回補 250 筆；`base_idx` 自本段起累計；`frame_mark` = 本塊樣本數；放不下保留最新（截斷旗標）；
  間隔 > 220 ms 標遺失；重新解析前先清掉自己的舊塊。讀出時間、crop、事件、鏡頭表留到 P2/P3（欄位為 0）。
  - 上機 `A001_033`（64 幀，63 lossless）、`A001_034`（73 幀，72 lossless）：**每幀都有有效塊**（CRC 過）、
    frame_seq 連續、`base_idx` 逐塊接續、旗標只有第一幀的 FIRST；每幀 83–84 筆（= 2499.5/29.97），第二幀 61 筆
    （第一個間隔較短，同 P0）。
  - **外掛端到端**：`real_fp_clip_dir`（fork `cd854bd`）讀這兩段 → gyroflow-core：5,481 / 6,232 筆、**2,499.5 Hz**、
    姿態有限值。相機靜止，最大 1 °/s（原始值偏移與 Gyro1 記錄的零點相符）。
  - 限制：表頭只抓前 80 KB，lossless 幀的根 IFD 在檔尾 → 外掛測試用「根指標改回 8」的複本；完整檔案的端到端待下次上機。
  - **下一步**：讓使用者拿相機做水平搖／俯仰／傾斜，確認方向與量級（軸向 `xyz` 在 Gyroflow 中的實際效果）；P2 水平儀事件；P3 讀出時間、crop、鏡頭表。
- **動作測試 `A001_036`（2026-10-06 18:06，OG3K 3008×2000 29.97p，lossless ON，與 30OG3K.BIN 同卡）**：使用者依語音提示
  手持做水平搖／俯仰／傾斜（各晚約 3–4 s 開始）。474 幀全部有塊、frame_seq 與 `base_idx` 完全接續、OG3K 表頭中位置 `0x10C94`。
  逐 0.5 s 主導軸：**水平搖 4.4–5.4 s → X（約 60%）、俯仰 10.9–12.4 s → Y（約 76%）、傾斜 13.4–15.4 s → Z（約 80%）**，
  與 Gyro1 實拍驗證的軸對應一致（orientation `xyz`）。外掛端到端：39,686 筆、15.88 s、2,499.5 Hz、最大 258.6 °/s。
  - **發現並修正一個 bug**：第 404 幀 n=0 且標遺失、第 405 幀 168 筆（兩幀份）——副處理器的寫入位置會短暫停在 ring 結尾
    （偏移 = `0x12C0`）才繞回 0，P1 把它當越界（`bhs`）。樣本沒有真的遺失（讀取位置沒前進，下一幀補上，序號連續）。
    改為結尾視同 0（`bhi`），加測試與突變（18/18），`20GYR2.BIN` 2,008 B，**尚未部署**。
  - 插曲：抓檔途中 `cave.py` 報「LOAD_DONE_US reads zero」，OG3K session 查明是 shell 的 `mem get` 沒回應時
    `boot_id()` 把 None 也報成 0（訊息誤導），字本身沒變；`fetch_heads.py` 已加重試。建議 cave.py 把 None 與 0 分開報（fpSup，未改）。
  - 尚未驗證：轉動的**正負號**（需要對照畫面，例如用讀卡機拷完整檔在 Gyroflow／Resolve 看）。
- **P2 水平儀事件＋P3 模式／鏡頭（2026-10-06，模擬 22 測試、突變 30/30；未上機）**：`20GYR2.BIN` 3,780 B（含 640 B 事件佇列）。
  - P2：第二個 CHAIN hook `0xC050D4C8`（Gyro1 `accel_hook.S` 同點，驅動釋放鎖後、r4 指向 x,y,z；原指令 `mov r2,#0`，
    沒有下一層時由我們補做）。水平儀 hook 只把 {序號, tick, ring 偏移, x,y,z} 放進 32 格無鎖佇列（序號驗證，寫方先作廢再寫回）；
    寫表頭時把「本塊 ring 範圍內」的事件換成樣本位置寫入（每塊最多 16 筆）。在本塊 ring 讀取之後才記錄的留給下一塊；
    更早的（超過上限留下的）丟掉，不會卡住佇列；過期（> 220 ms）丟掉；新一段先清空佇列。
  - P3：每段第一幀呼叫 `0xC032C720()`（目前模式）、`F_TIMING/F_GEOM(0xC343B588, mode)`（同 Gyro1 gcsv_json.S），
    算讀出 ns = hmax×行數×125/9、crop（讀出寬×binH、行數×binV，置中，上限 6000×4000）；附 504 B 鏡頭校正表（旗標 0x40）。
    最大樣本數保留事件空間（160 B），第一幀再讓出鏡頭表的空間（84 筆）。
  - 外掛交叉驗證（模擬片段）：gyroflow-core 收到讀出 10.5556 ms、逐幀鏡頭參數、水平儀經四分之一圈換成 m/s²（`(12,−8,1020)` → `(−0.077,−0.115,9.77)`）。
  - 突變測試工具的教訓：改 `mutate.py` 加過濾參數時縮排壞掉、迴圈沒跑卻印出「3/3 caught」；已修正，並補了
    「水平儀 hook 點被獨佔時也要放棄」的測試。
  - 待上機：機身上 `0xC032C720`／`F_TIMING`／`F_GEOM` 在 MovRec 任務裡呼叫是否安全、讀出值是否與 Gyro1 一致；
    事件數與 100 Hz 是否吻合；外掛讀完整檔（含 lossless 根 IFD）。
- **完整檔案驗證（2026-10-06 19:46，讀卡機）**：從 SD 卡拷出 `A001_033/034/036` 完整 DNG（lossless 根 IFD 在檔尾），
  外掛直接讀（不改根指標）：5,481／6,232／39,686 筆，與只抓表頭的結果完全一致 → 「完整檔案待驗證」結案。
  同時以讀卡機把卡上 `20GYR2.BIN` 換成 P2/P3 版（3,780 B）；macOS 會在 exFAT 上產生 `._20GYR2.BIN`，已刪（v3 loader 也會跳過 `._*`）。
- **P2/P3 上機（2026-10-06 19:50，`A001_040`，FHD 29.97p，lossless ON，LUMIX S 40/F2）**：`LOAD.LOG`：`20GYR2.BIN` LOADED，
  `C038C77C` 與 `C050D4C8` 都寫入跳板（同卡 30OG3K 這次被 RELEASE，與 Gyro2 無關）。145 幀：
  - P3：第一幀讀出 **10,556,389 ns、模式 106**（Gyro1 實機值「106 → 10.556 ms」一致）、crop (0, 292, 6000, 3416)；
    鏡頭表只在第一幀，焦距 40.0 mm、綠平面與 fpSup `test_distfit.py` 從機身讀出的 LUMIX S 40/F2 表逐值相同。
    在 MovRec 任務裡呼叫 `0xC032C720`／`F_TIMING`／`F_GEOM` 沒有問題。
  - P2：216 筆水平儀事件，每幀 1–2 筆、約 45 次／秒（Gyro1 實測驅動發布 47.2 Hz，相符；不是 100 Hz）；位置都在本塊範圍且遞增。
  - 外掛端到端：讀出 10.556 ms；逐幀鏡頭 40 mm、fx 2,139 px、依對焦 0.341 m 內插的畸變係數；水平儀換成陀螺軸
    (−9.43, −0.25, −1.91) m/s²（|a| ≈ g，換到 Gyroflow 機身座標後重力落在偏航軸，符合手持水平）。
  - 剩下：用畫面驗證轉動正負號與穩定效果（需在 Resolve 裝新版外掛）；量 `HOOK_TO_READOUT_US`。

## 13. 緩衝重設計：兩個緩衝，水平儀搬、每幀用指標切（選項 B）[定 2026-10-06]

使用者的原設計是對的：陀螺樣本要由頻繁觸發的搬移存進**我們自己的**緩衝，不能只靠每幀 hook 讀 240 ms 的副處理器 ring。
副處理器 ring：600 格原地覆蓋、寫到結尾回第一格（不搬移、不清空），`[ring]` 指向下一格；只知道最新在哪，不知道繞了幾圈。

| 緩衝 | 大小 | 寫入者 | 內容 |
|---|---|---|---|
| 陀螺緩衝 | 8,192 筆 × 6 B = 48 KB（約 3.3 s），區塊 BSS | 水平儀 hook 的 `drain()`（47 Hz）；水平儀 > 100 ms 沒搬時每幀 hook 代搬 | x, y, z；全域序號 `W` 單調遞增 |
| 水平儀緩衝 | 256 筆 × 12 B | 水平儀 hook（先 drain 再記） | `{pos = W, x, y, z}` |

- `drain()`：`LDREX/STREX` 搶「搬移中」旗標，搶不到就跳過；搬「上次 ring 位置 → 現在」，間隔超過一圈時以時間推算圈數，
  被覆蓋的記遺失；更新 `{W, ring 位置}` 用序號鎖，讀方拿到的是同一時刻的一組。
- 每幀 hook（只讀，不寫緩衝）：`mark = W + ring 中尚未搬的筆數`；資料塊 = `[上一個 mark, mark)`，已搬的部分讀陀螺緩衝、
  最後一小段（< 21 ms）讀 ring → **每塊剛好是這一幀的區間，無重疊、無缺口**；水平儀事件取 pos 在區間內者。
- 新一段（tag 計數器不連續，或停頓 > 3 s）：起點 = `mark − 250`（往回補 250 筆，從陀螺緩衝取）。
- 遺失：區間開頭已被陀螺緩衝覆蓋（MovRec 卡 > 3.3 s），或 ring 尚未搬的部分 > 584 筆（水平儀停太久且代搬也來不及）。
- 9 fps（111 ms）、18 fps（55 ms）都在範圍內；MovRec 卡頓的容忍度由 240 ms 變為約 3.3 s。

## 14. 現況（2026-10-07）：無鎖、Vd 計時 [定]

**相機端（`projects/gyro2-sup/build/20GYR2_VD.BIN`，4,208 B，sha1 `87dd82ac`，已在卡上、開機確認；下面的錄影實測來自同設計、多掛 0x7f 的探針版）**

- 陀螺緩衝**只有水平儀 hook 一個寫入者**，不用鎖。2026-10-06 有 `LDREX/STREX` 鎖的版本開機卡在第三格，拿掉後正常。
  每幀 hook 只讀：已搬的讀緩衝，尚未搬的尾段直接讀 ring（ring 保留 240 ms）。
  水平儀停太久時，snapshot 以時間推算 ring 繞了幾圈，被覆蓋的部分記遺失，但位置不偏。
- **Vd（IRQ 0x79，`FUN_c0125478`）**：把 Thumb 位置 `0xC0125480`（`movt r4,#0xC31D`）換成 BLX，經 ARM veneer
  記「陀螺流位置 + TickTimer」，再重做那條 `movt`。EXCL claim，**必要**：claim 不到就整個不載入。
  每幀寫成 FSG2 事件類型 3（4 B TickTimer，只供診斷）。IRQ 0x7f 試過，在 Vd 後 0.125 ms，同一時刻，不用。
- 模擬 32 測試、突變 43/43。

**實測（A001_012 1/250、A001_016 1/50，OG3K 29.97p）**

| 項目 | 結果 |
|---|---|
| Vd 週期 | ±5 µs（p5–p95），無重複觸發 |
| Vd 位置 vs 陀螺時鐘 | 殘差 0.29 筆 rms；陀螺時鐘比 TickTimer 快 5 ppm |
| hook 在 Vd 之後 | 中位 14.0 ms，四分位 13.6–14.0，偶爾延遲到 65 ms；延遲時後面幾幀的 Vd 落進前一個區塊，那幾幀區塊沒有 Vd（Vd 總數 = 幀數 + 回溯，一個都沒少） |
| hook 偏移逐段漂移 | 051 −8.8 ms、012 −5.2 ms（畫面中心相對 hook）：所以不能用 hook 計時 |
| Vd 綁在讀出還是曝光 | 快門 1/250 → 1/50，畫面中心約每 ms 曝光前移 0.9 ms：綁讀出（曝光開始已排除） |

**外掛端（fork `feature/cdng-makernote`，本機 commit，未推）**

- 每幀時間：整段所有 Vd 位置擬合一條直線（斜率也擬合，吸收時鐘漂移）；每幀取 `frame_seq + 偏移` 對應的 Vd，
  偏移取前後 9 幀的中位數（偶發的 hook 延遲被多數決排除，錄影跳過感光幀的位移會保留）。
  第一列讀出 = Vd + **0.9 ms**（±1 ms）：光流比對得 1.8 ms（±3），再用 Gyroflow 自己的 autosync 修正
  （016 +1.25、012 +0.93 ms；畫面錯一幀時讀 +34.5，確定正負號；修正後 016 剩 +0.35）。沒有 Vd 的片段直接拒絕。
- 果凍效應：讀出時間（FHD 10.556 ms、OG3K 12.435 ms）與方向 TopToBottom 已用畫面驗證（051 殘差 0.68 px，不修 1.02，反向 1.74）。
- 比例：OG3K 讀全感光元件（6000×4000，2×2 合併），外掛焦距正確；殘餘的放大率差隨拍攝距離變（0.38 m 1.15 倍、1.18 m 0.89 倍），
  判斷是手持轉動的視差，陀螺量不到。
- 外掛已改名 **Gyroflow (fpSup)**，ID `io.github.ijigen.fpsup.gyroflow`，與官方 Gyroflow 並存。

**格式（FSG2 kind 2，版本 1，維持不動）**：frame_mark 恆等於 n_samples；事件類型 1 水平儀、3 Vd，
類型 2（對焦）預留未寫；相機只設 LOST、TRUNC、FIRST、LENS 旗標。

- 檔名中斷的片段（相機沒寫出的幀）：外掛只讀選定那張所在的連續段，每段各自載入。

**鏡頭（2026-10-07）**
- 手動鏡頭（EXIF 無焦距）：不用鏡頭表（可能是上一顆的殘值），外掛「Manual lens focal (mm)」+ 通用畸變：理想直線投影
  （tanθ 級數 1/3, 2/15, 17/315, 62/2835）再加焦段典型角落桶狀（Gyroflow 資料庫 111 個 fp 鏡頭檔中位數）。
  資料庫搜尋與 111 筆下拉選單做過又移除（Resolve Fusion 頁不送文字欄位的變更事件）；鏡頭檔改用上游「Load preset/lens profile」載入。已實機確認（A001_023–025，`~/Movies/Gyro2/manual_lens/`）：EXIF 焦距、光圈、對焦距離都是 0/10，鏡頭名稱空白；FSG2 鏡頭表的焦距欄是 65535（無效）。
- 呼吸（A001_018，桌上靜止，0.3 m → ∞）：畫面縮 2.2 %；鏡頭表給 1.2 %。不是少修的原因。
- 手持近物的 5–15 % 比例偏差：主要是視差（陀螺量不到平移）；∞ 對焦遠景（A001_019）自動校正 −4.5 %。
- 自動校正原型 `projects/gyro2-sup/autocal.py`（陀螺 + 光流擬合 f、k1、k2）：019 前後半 −8.7 / +3.9 %，畸變不可靠；
  1/50 動態模糊是主因。待 1/250 遠景片再評估。

**外掛更新**：tag `fpsup-vN`、外掛 RELEASE=1；每日檢查、指定版本安裝、SHA-256 驗證、備份、Roll back。CI 只編 OpenFX、無憑證時 ad-hoc。

**未做**：上下/滾轉定量、120p、長錄影、對焦事件（暫不做）。

