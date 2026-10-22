# SIGMA fp Ver.5.02 — HDMI RAW 外錄格式（模式矩陣 / 連結層 / 酬載）

本文補上 `HDMI_RAW.md`、`../../../projects/hdmi-recorder/notes/RECORDER_SPEC.md` 缺的三塊：
**(1) RAW 可用的完整解析度×幀率矩陣**、**(2) 連結層其實有讀 EDID**、**(3) 線上像素容器是編譯期固定值**。
全部從 Ver.5.02 主映像（`out/seg0_c0000000.bin`, base `0xC0000000`）反編譯 + 直接讀資料表得出，並做了交叉驗證。

> ⚠️ **本文修正 `HDMI_RAW.md` §2 的一項結論**：該文說「相機不讀 EDID / 無 sink capability 讀取」。
> 實際上韌體**有完整的 CEA-861 EDID 解析與能力比對**（見 §3）。原結論「無 vendor handshake、無廠牌辨識」仍然成立，
> 但「不看接了什麼」是錯的——相機會依 sink 宣告的 VIC 清單決定能不能送某個模式。

> ⚠️ **本文也修正 `../../../projects/hdmi-recorder/notes/RECORDER_SPEC.md` §3.4**：該文說「色彩格式完全不在韌體」。
> 實際上在 TX 暫存器 `0x30190004`，只是被設成單一編譯期常數（見 §4）。原結論（4:2:2 直通即可）不受影響。

> ⚠️ **本文也推翻 `../../../projects/hdmi-recorder/notes/HDMI_RAW_RECORDER_BUILD.md` §2 的擷取卡首選**：
> UHD30 4:2:2 需 497 MB/s，超過 USB 3.0 實際可用頻寬（見 §8.4）。

---

## 0. 狀態總表

| 項目 | 狀態 | 出處 |
|---|---|---|
| RAW 可用的解析度 × 幀率矩陣 | ✅ 韌體確定 | §2.3 |
| 14 個 HDMI 模式 ↔ CEA VIC / HDMI_VIC 對照 | ✅ 韌體確定，**兩條獨立證據鏈互證** | §3.1、§9.0(b) |
| 相機會讀 EDID 並依 sink 能力挑模式 | ✅ 韌體確定（**修正舊筆記**） | §3.2 |
| 線上 colour format = 編譯期常數 3，RAW 不改 | ✅ 韌體確定（**修正舊筆記**） | §4 |
| RAW 酬載 = 12-bit 緊密打包，2 px → 3 B | ✅ 韌體確定 | §5 |
| TX 為 HDMI 1.4 級，天花板 297 MHz / 8.91 Gb/s | ✅ 韌體確定（無 SCDC/scrambling/HDCP） | §8.1–8.2 |
| HDMI framebuffer = 2 B/px → 光柵利用率 75% | ✅ 韌體 + **BRAW metadata 獨立印證** | §9.0(a)、§11.3 |
| 線上 Bayer 幀 = **3856 × 2176**（8 px 護欄） | ✅ BRAW `crop_origin`/`crop_size` 推得 | §11.3 |
| 光柵閒置 ≈ 521 行 / 4.0 MB per frame | ✅ 由上兩項推得 | §11.3 |
| TickTimer 實為 64-bit（`FUN_c002B4E0`） | ✅ 韌體確定 | §10.4 |
| 音訊 = 48k / 2ch / **16-bit 位元透明** | ✅ **實測**（OR = `0xFFFF00`） | §11.2 |
| 音訊低 4 bit 可安全夾帶 48 kB/s | ✅ **實測**（熵 + 噪訊底） | §12 |
| BRAW 為 8:1 有損 → 塞像素不可行 | ✅ **實測**（7.94:1） | §11.2 |
| timecode 只有起始值，無法每幀變動 | ✅ **實測**（`stsz` count=1） | §11.2 |
| `0x30193000` 22-word 封包引擎的型別 | ❓ **未確認**。強烈懷疑是相機→錄影機 metadata 通道（機身序號必須頻內傳） | §9.1-B、§11.2 |
| 12-bit 在光柵內的確切位元佈局 / Bayer 相位 | ❓ **仍需實測** | §6 |
| fp 能否改送 24-bit HDMI 音訊 | ❓ **未驗證**，上檔 +12 kB/s 免費 | §12.4(a) |

---

## 1. 一句話結論

RAW over HDMI = **完全標準的 CEA-861 / HDMI 1.4 4K×2K 視訊時序**（依錄影機 EDID 挑選），
**線上像素容器（colour format）是編譯期常數，RAW 與一般影像完全相同**，
差別只在 framebuffer 內容換成 **緊密打包的 12-bit Bayer（2 px → 3 bytes）**。
→ 對錄影機而言就是「一條普通的 UHD/FHD/DCI4K 訊號，但像素值不是影像」。

---

## 2. 使用者可選矩陣（韌體確定）

三個選單項（同時也是 PTP/shell 可設）在設定物件的 vtable 槽位：

| 槽位 | 項目 | 型別 | getter/setter |
|---|---|---|---|
| `0x3b0` | **HdmiIsManual** | bool | `FUN_c005fb50` / `FUN_c005fb88` |
| `0x3b4` | HdmiOutputInfo | bool | `FUN_c005fbe8` / `FUN_c005fc20` |
| `0x3b8` | **HdmiOutputFormat**（0=一般, 1=RAW） | enum | `FUN_c005fc80` / `FUN_c005fcb8` |
| `0x3bc` | **HdmiOutputSize** | enum | `FUN_c005fd18` / `FUN_c005fd50` |
| `0x3c0` | **HdmiOutputFramerate** | enum | `FUN_c005fdb0` / `FUN_c005fde8` |

PTP/shell 端點（名稱表 `0xC0BBBA14`，列格式為 `(name, desc, handler)`）：
`SetHdmiOutputInfo`→`c0400588`、`SetHdmiOutputFormat`→`c0400600`、`SetHdmiIsManual`→`c0400670`、
`SetHdmiOutputSize`→`c04006e8`、`SetHdmiOutputFramerate`→`c0400758`。

### 2.1 Size enum（`MenuItemHdmiOutputSize::v3` @ `0xC00AD950`，常數表 `0xC07440A4`）

| 值 | 光柵 |
|---|---|
| 0 | 1280 × 720 |
| 1 | **1920 × 1080 (FHD)** |
| 2 | **3840 × 2160 (UHD)** |
| 3 | **4096 × 2160 (DCI 4K)** |

`MenuItemHdmiOutputSize::v8` @ `0xC00AD8C8`：**Size=3（DCI 4K）只有在 `HdmiOutputFormat == 1` 時才成立**，
否則被強制降回 2（UHD）。→ **DCI 4K 是 RAW 專屬模式**。
（機身 OSD 只顯示 DCI 4K / UHD / FHD 三格，720p 不在 OSD 清單；見 Lua `0xC2DBB58C`。）

### 2.2 Framerate enum

`MenuItemHdmiOutputFramerate::v8` @ `0xC00ADAA8` + 對照表 `0xC0742250`（9 組 pair）：

| 選單值 | fps | 內部時序 enum `f` |
|---|---|---|
| 1 | 23.98 | 1 |
| 12 | 24 | 2 |
| 2 | 25 | 3 |
| 3 | 29.97 | 4 |
| 13 | 48 | 6 |
| 4 | 50 | 7 |
| 5 | 59.94 | 8 |
| 6 | 100 | 9 |
| 7 | 119.88 | 10 |

（OSD Lua `ssc = {"23.98","24","25","29.97","48","50","59.94","100","119.88"}` 逐項吻合；內部 `f=5` 未使用。）

限制（`MenuItemHdmiOutputFramerate::v8`）：
- **Size = UHD(2)** → 選單值 4/5/6/7/13（50/59.94/100/119.88/48）全部被**夾到 3（29.97）**。
  → **UHD 上限 29.97p**。
- **Size = DCI 4K(3)** → 幀率**強制 0xC = 24 fps**。→ **DCI 4K 只有 24p**。
- FHD / 720p → 9 種全開。

### 2.3 ★ 最終可用矩陣

| 光柵 | 可用 fps |
|---|---|
| **4096 × 2160 (DCI 4K)** | **24 only**（且需 RAW） |
| **3840 × 2160 (UHD)** | 23.98 / 24 / 25 / 29.97 |
| **1920 × 1080 (FHD)** | 23.98 / 24 / 25 / 29.97 / 48 / 50 / 59.94 / 100 / 119.88 |
| 1280 × 720 | 同 FHD（不在 OSD） |

> 解析度/幀率選單本身**不因 RAW 而變**（除了 DCI 4K 解鎖）；RAW 只是 framebuffer 內容換掉。

---

## 3. 連結層：真的有讀 EDID（修正既有筆記）

### 3.1 HDMI 輸出模式表 `0xC0B51044`（14 筆 × 4×u32）

格式 `{width, height, framerate_enum f, mode_id}`，`0xC0B51124` 為表尾哨兵。
查表函式 `FUN_c02F5258`：以 (W,H,f) 找 `mode_id`，再呼叫 `FUN_c002BC80(hdmi_ctx, mode_id)` 檢查**該模式 sink 支不支援**，不支援則回傳 1（fallback）。

| W×H | f | fps | mode_id | → 內部 code | → **CEA VIC / HDMI_VIC** |
|---|---|---|---|---|---|
| 4096×2160 | 2 | 24 | 56 | 0x12B | **HDMI_VIC 4** (4096×2160p24) |
| 3840×2160 | 4 | 29.97 | 49 | 0x11E | **HDMI_VIC 1** (3840×2160p30) |
| 3840×2160 | 3 | 25 | 50 | 0x11F | **HDMI_VIC 2** (3840×2160p25) |
| 3840×2160 | 2 | 24 | 51 | 0x120 | **HDMI_VIC 3** (3840×2160p24) |
| 3840×2160 | 1 | 23.98 | 51 | 0x120 | 同上（23.98 走 24p 時序） |
| 1920×1080 | 10 | 119.88 | 54 | 0x129 | **VIC 63** (1080p120) |
| 1920×1080 | 9 | 100 | 55 | 0x12A | **VIC 64** (1080p100) |
| 1920×1080 | 8 | 59.94 | 44 | 0x119 | **VIC 16** (1080p60) |
| 1920×1080 | 7 | 50 | 45 | 0x11A | **VIC 31** (1080p50) |
| 1920×1080 | 6 | 48 | 58 | 0x12D | **VIC 111** (1080p48, 64:27) |
| 1920×1080 | 4 | 29.97 | 46 | 0x11B | **VIC 34** (1080p30) |
| 1920×1080 | 3 | 25 | 47 | 0x11C | **VIC 33** (1080p25) |
| 1920×1080 | 2 | 24 | 48 | 0x11D | **VIC 32** (1080p24) |
| 1920×1080 | 1 | 23.98 | 48 | 0x11D | 同上 |

推導鏈（三段各自獨立，結果完全自洽）：
`mode_id` --`FUN_c00DEA98`（switch 0..0x3B）--> `code` --取低位元組--> 索引 `DAT_c07C03EC`（bitmask 表）
--> bit --反查 `FUN_c00EBD60` 的 VIC→bit 映射--> **CEA-861 VIC / HDMI 1.4 HDMI_VIC**。

> **4K 走的是 HDMI 1.4 的 4K×2K（HDMI_VIC，帶在 HDMI Vendor Specific InfoFrame）而不是 CTA VIC 93–98**。
> 這對擷取卡有實際影響：卡必須看得懂 HDMI 1.4 4K×2K 宣告，不能只認 HDMI 2.0 的 VIC 95/97。

### 3.2 EDID 解析路徑（原筆記誤判處）

```
HPD 接上 (ctx+0x1F8 == 2)
  → FUN_c002BC40  →  FUN_c00EA9E8(ctx+0x18)          // 建 60 筆「本模式 sink 支援嗎」旗標陣列
                       for id in 0..0x3B:
                         code = FUN_c00DEA98(id)
                         flag = FUN_c00EBFB8(code)     // (DAT_c07C03EC[code] & sink_mask) != 0
                     FUN_c00EBD60()                    // sink_mask 從 EDID 算出
                       ├─ FUN_c00EB470 → … → FUN_c00F0310   // 讀 CEA-861 SVD 清單（最多 128 筆 VIC）@ RAM 0xC3020225
                       ├─ FUN_c00EC580 → … → FUN_c00F03D8   // 讀 HDMI VSDB 的 4K×2K descriptor（HDMI_VIC 1..4）
                       └─ FUN_c00EB488 → FUN_c00F0178       // EDID 有效旗標 DAT_c30202A8
```

`FUN_c00EBD60` 逐一比對 SVD：VIC 2/3→480p、4→720p60、16→1080p60、31→1080p50、32/33/34→1080p24/25/30、
41/47→720p100/120、60/61/62→720p24/25/30、63/64→1080p120/100、96/97→2160p50/60、108/111→720p48/1080p48…；
另讀 HDMI 1.4 4K×2K：HDMI_VIC 1/2/3/4 → 2160p30 / 2160p25 / 2160p24 / **4096×2160p24**。

**fallback 鏈**（sink 不支援時往下退）：
`0xC0B50FE4 = {49,44,39,35}` = UHD30 → 1080p60 → 720p60 → 480p60；
`0xC0B51160 = {49,46,41}`（30p）、`0xC0B5116C = {50,47,42}`（25p）、
`0xC0B51178 = {45,40,36}`（50Hz）、`0xC0B51184 = {51,48,43}`（24p）。

→ **實務結論：錄影機的 EDID 必須宣告 HDMI 1.4 4K×2K（HDMI_VIC 1/3/4）**，
否則 fp 會靜靜地把 UHD RAW 降成 1080p60，RAW 就毀了。
`HdmiEdidFixed`（`0xC04A2760`，shell `display hdmi_edid …`）可**強制固定 EDID** 繞過這點——
對自製錄影機是關鍵除錯／保底手段。

---

## 4. 線上像素容器：編譯期固定，RAW 不改

設模式的入口是 `FUN_c00E9980(ushort *mode)` @ `0xC00E9980`，mode 結構：

| 位移 | 欄位 |
|---|---|
| +0x00 | mode_id（< 0x3C） |
| +0x04 | **colour format（< 5）** |
| +0x08 | aspect / colorimetry（0..3） |
| +0x0C | quantization flag（0/1） |

**所有** `DisplayOutputSelect*::v2` 路徑都把 colour format 寫死成 **3**：

| 函式 | 位址 | colour format |
|---|---|---|
| `DisplayOutputSelectBase::v2` | `0xC02E9560` | `3`（連線時）/ `0`（未連線） |
| `DisplayOutputSelectBaseDual::v2` | `0xC02E9978` | `3` |
| `DisplayOutputSelectBaseHdmiOnly::v2` | `0xC02E9AC8` | `3` |
| `DisplayOutputSelectBaseDualW71c1::v2` | `0xC02F4F58` | 靜態初值 `DAT_c2f1d504 = 3`（seg1，**執行期從未被寫入**） |

→ **RAW 模式不改變 HDMI 的色彩格式/取樣**。錄影機看到的像素容器與一般監看完全一樣。

硬體側：`FUN_c00E5FE0` 把 format 寫進 HDMI TX 暫存器 **`0x30190004` bits[14:12]**
（fmt0→0、fmt1/2→3（再由 `0x200000` 位元分兩種）、fmt3→**2**、fmt4→4），
`FUN_c00E2508` 依 format 切換 TX 通道對（fmt0/4 用 ch 0/3 且 `0x30190364[3:0]=1`＝RGB 族；
fmt1/2 用 ch 5/7；**實際使用的 fmt3 用 ch 8/10**，屬 YCbCr 族但與 fmt1/2 不同）。
XZ01 的 TX 暫存器語意沒有公開手冊，**「3」的確切名稱（4:2:2 / 4:4:4 / 深色位元）無法只靠韌體定死**，
但「**只有一個值、RAW 與非 RAW 相同**」這點是確定的。

> 這修正了 `RECORDER_SPEC.md §3.4` 的「色彩格式完全不在韌體」——
> 它**在**韌體（`0x30190004`），只是被設成單一常數。結論（4:2:2 直通即可）不受影響，
> 但驗證方式變成：**先用一般（非 RAW）輸出確認你的擷取鏈是 bit-exact，再切 RAW**，
> 因為兩者線上容器相同，一般模式驗過就等於 RAW 模式驗過。

---

## 5. 酬載：12-bit 緊密打包 Bayer

`CNRO` @ `0xC015C230`（buffer 描述子 → 位元組數）：

| 描述子位移 | 意義 |
|---|---|
| +0x0C | HSIZE（寬） |
| +0x10 | VSIZE（高） |
| +0x14 | TYPE：0=RAW, 1=YUV, 2=Y, 3=RGB, 4=ARGB |
| +0x18 | RAW 位元深度：0/預設=12, 1=14, 2=16, 3=10 |

```
TYPE=0 (RAW), bit=12 →  W*H*3/2      ← 1.5 B/px，2 px → 3 bytes，緊密打包
TYPE=0, bit=10        →  W*H*10/8
TYPE=0, bit=14        →  W*H*14/8
TYPE=0, bit=16        →  W*H*16/8
TYPE=1 (YUV)          →  W*H*2       ← 一般影像管線 2 B/px
```

位元深度 enum（`FUN_c02DA870` / `imager createraw` 除錯輸出）：`0→12, 1→14, 2→16, 3→10, 4→8` bit。
CinemaDNG 與 HDMI RAW 都走 **mode 0 = 12-bit**。

還有一個**位元組序欄位**（still-raw 描述子 +0x28，除錯字串 `raw_endian :`）：`0=Little, 1=Big, 2=Middle`。
→ 解包時 **endianness 是硬體可設參數，不是固定的**，必須實測確認（見 §6）。

SIG 硬體區塊位址（`FUN_c01597B8` 的暫存器 dump）：
`SIG0_RAWOUT = 0x301128C0`、`SIG1_RAWOUT = 0x30113890`、`SIG0_RAWBLT = 0x30112800`、
`SIG0_RAWSHAD_LINEAR = 0x30112940`、`SIG1_RAW_ZOOM = 0x30113380`；輸出序列器 `SIGSEQ0/1 = 0x30200000 / 0x30200100`。

---

## 6. 仍然只能實測的部分（韌體給不了）

打包發生在 XZ01 ASIC 的 RAWOUT/VOUT 硬體，韌體只設暫存器不搬位元，所以下列必須用真實擷取比對：

1. **Bayer 幀在光柵中的擺放**：3840×2160 的 12-bit Bayer = 12,441,600 B；UHD 光柵在 2 B/px 下有 16,588,800 B。
   → 只用得到 75%。是「填滿 1620 行後留空」、「跨行重排」還是「走深色 3 B/px」，韌體無法區分。
2. **2×12-bit → 3 bytes 的位元順序**（MSB/LSB first）＋ `raw_endian` 實際值。
3. **Bayer 相位**（左上角 RGGB/GRBG/GBRG/BGGR）。
4. **有無 header/metadata 列**。
5. **黑/白位準** ↔ DNG BlackLevel/WhiteLevel。

**建議校準流程（沿用 `RECORDER_SPEC.md §3.3`，但多兩步）**：
- **先跑非 RAW**：一般 UHD 輸出拍平場，確認擷取鏈 bit-exact（因為 §4 證明兩者線上容器相同）。
- 用 `HdmiEdidFixed` 固定 EDID 排除協商變因。
- 再切 RAW，同時 (a) 機內錄 CinemaDNG (b) 存 HDMI 原始幀，逐像素回歸。

---

## 7. 證據位址速查

| 項目 | 位址 |
|---|---|
| HDMI 輸出模式表（14 筆） | `0xC0B51044` – `0xC0B51124` |
| 模式查表 | `FUN_c02F5258` @ `0xC02F5258` |
| mode_id → 內部 code | `FUN_c00DEA98` @ `0xC00DEA98` |
| code → sink 能力 bit | `DAT_c07C03EC`（idx 0x11–0x2E） |
| EDID → sink 能力 mask | `FUN_c00EBD60` @ `0xC00EBD60` |
| EDID SVD 讀取 | `FUN_c00F0310`（RAM `0xC3020225`，count `DAT_c30201A4`） |
| EDID 4K×2K descriptor | `FUN_c00F03D8` |
| 模式支援檢查 | `FUN_c002BC80` @ `0xC002BC80` |
| HDMI 設模式入口 | `FUN_c00E9980` @ `0xC00E9980` |
| colour format → TX 暫存器 | `FUN_c00E5FE0` / `FUN_c00E2508`（reg `0x30190004`） |
| colour format 靜態值 = 3 | `DAT_c2f1d504`（seg1 offset `0x26704`） |
| Size 常數表 | `0xC07440A4` |
| Framerate pair 表（9 組） | `0xC0742250` |
| RAW buffer 尺寸公式 | `CNRO` @ `0xC015C230` |
| HdmiLimit 除錯輸出 | `0xC0437740` |
| HdmiEdidFixed | `0xC04A2760` |
| OSD Lua（HDMI 狀態列） | `0xC2DBB58C` |

> 相關：`HDMI_RAW.md`（transport 性質，§2 需依本文修正）、`../../../projects/hdmi-recorder/notes/RECORDER_SPEC.md`（DNG 結構＋色彩格式，§3.4 需依本文 §4 修正）、`../../../projects/hdmi-recorder/notes/HDMI_RAW_RECORDER_BUILD.md`（建置 SOP）。

---

## 8. HDMI 通道理論上限（新增）

### 8.1 fp 的 TX 是 HDMI 1.4 級

全 ROM 掃描：**無 `SCDC`、無 scrambling、無 HDCP**（三個字串 hit 全是誤中：SCDC 為二進位雜訊、
`Scramble Decoding` 屬韌體更新 LZSS 解擾 `XC_FwupCore.cpp`、`AVI` 來自 `SAVING`）。
SCDC + scrambling 在 TMDS character rate > 340 MHz 時是**強制**的 → 沒有它們就不可能是 HDMI 2.0。

| | char rate 上限 | TMDS line rate | 24 bit/px 有效頻寬 |
|---|---|---|---|
| HDMI 1.4b 規格上限 | 340 MHz | 10.200 Gb/s | 8.160 Gb/s |
| **fp 韌體實際天花板** | **297 MHz** | **8.910 Gb/s** | **7.128 Gb/s** |
| （HDMI 2.0 供對照） | 600 MHz | 18.000 Gb/s | 14.400 Gb/s |

### 8.2 297 MHz 解釋了整個幀率矩陣

`DAT_c0b51044` 的 14 個模式，**沒有一個超過 297 MHz，而且三個解析度各自的最高幀率都剛好落在 297.000 MHz**：

| 模式 | VIC | pixel clock | TMDS line |
|---|---|---|---|
| DCI 4K 24 | HDMI_VIC 4 | **297.000 MHz** | 8.910 Gb/s |
| UHD 29.97 | HDMI_VIC 1 | **296.703 MHz** | 8.901 Gb/s |
| UHD 25 | HDMI_VIC 2 | 297.000 MHz | 8.910 Gb/s |
| UHD 23.98 / 24 | HDMI_VIC 3 | 296.703 / 297.000 MHz | 8.910 Gb/s |
| FHD 119.88 | VIC 63 | **296.703 MHz** | 8.901 Gb/s |
| FHD 100 | VIC 64 | 297.000 MHz | 8.910 Gb/s |
| FHD 59.94 / 50 / 48 | VIC 16 / 31 / 111 | 148.5 MHz | 4.455 Gb/s |
| FHD 29.97 / 25 / 24 | VIC 34 / 33 / 32 | 74.25 MHz | 2.228 Gb/s |

→ **§2.3 的限制不是產品刀法，是 TMDS 時脈天花板**：
- UHD 停在 29.97p，因為 4400×2250×30 = 297.000 MHz 已經滿了。
- DCI 4K 只有 24p，因為 5500×2250×24 = 297.000 MHz 已經滿了（p25 就要 309 MHz）。
- FHD 停在 119.88p，因為 2200×1125×120 = 297.000 MHz 已經滿了。

**旁證**：`FUN_c00EBD60` 會從 EDID 解析 VIC 96/97（3840×2160p50/p60，各需 **594 MHz**，HDMI 2.0 才有），
並存進 bitmask bit 0x80000 / 0x100000——但 `FUN_c00DEA98` 的 mode_id→code 對照表中**沒有任何 id 映到這兩個 bit**。
能力讀得到、卻沒有對應模式可送 → 再次確認 TX 卡在 HDMI 1.4。

### 8.3 RAW 酬載 vs 通道容量：頻寬不是瓶頸

**TMDS 的物理事實：1× 時脈下每個 pixel period 固定 24 bit**（3 channel × 8 bit）。
不論 RGB 4:4:4 8-bit、YCbCr 4:4:4 8-bit、還是 **YCbCr 4:2:2 12-bit**，都是 24 bit/px——
4:2:2 之所以能塞 12-bit/component 而**不需要 deep color**，就是因為它只送 Y + 單一 chroma。
（真正的 36-bit deep color 要 1.5× 時脈 = 445.5 MHz > 340 MHz，在 4K 上**物理不可能**；
韌體也沒有任何色深切換，colorfmt 是單一常數——見 §4。）

所以無論 colorfmt=3 最後證實是哪一種：

| 模式 | active px/s | 24 bit/px 容量 | 12-bit Bayer 需求 | **佔用** |
|---|---|---|---|---|
| UHD 29.97 | 248.6 Mpx/s | 5.967 Gb/s | 2.983 Gb/s | **50.0 %** |
| DCI 4K 24 | 212.3 Mpx/s | 5.096 Gb/s | 2.548 Gb/s | **50.0 %** |
| FHD 119.88 | 248.6 Mpx/s | 5.967 Gb/s | 2.983 Gb/s | **50.0 %** |

→ **每個 wire pixel 可裝 2 個 12-bit Bayer sample，但 RAW 只需要 1 個。全模式一律只用掉一半容量。**
→ **RAW 模式下相機不是被頻寬綁住的，是被「必須送一條合法標準光柵」綁住的。**
這也正面解釋了 §6.1 的 75%/50% 空洞——那是設計上就存在的餘裕，不是我算錯。

> 反推：若 fp 願意用滿密度打包，UHD RAW 理論上可到 59.94p 的資料量；
> 但那需要 594 MHz 的**光柵**，TX 送不出去。所以瓶頸永遠是光柵時序，不是酬載。

### 8.4 ★ 真正的瓶頸在擷取端（推翻 `HDMI_RAW_RECORDER_BUILD.md §2` 首選）

錄影機端要 verbatim 收下這條流，需要的持續頻寬：

| 模式 | 8-bit 4:2:2 (UYVY, 2 B/px) | 12-bit 4:2:2 (3 B/px) |
|---|---|---|
| **UHD 29.97** | **497.2 MB/s** | 745.8 MB/s |
| DCI 4K 24 | 424.7 MB/s | 637.0 MB/s |
| UHD 25 | 414.7 MB/s | 622.1 MB/s |
| UHD 23.98 | 397.7 MB/s | 596.6 MB/s |
| **FHD 119.88** | **497.2 MB/s** | 745.8 MB/s |
| FHD 100 | 414.7 MB/s | 622.1 MB/s |
| FHD 59.94 | 248.6 MB/s | 372.9 MB/s |

對照：**USB 3.0 (5 Gb/s, 8b/10b) = 500 MB/s 理論、實測 bulk 約 380–420 MB/s**。

→ **UHD 29.97 RAW 的 497 MB/s 超過 USB 3.0 的實際可用頻寬。**
USB 3.0 級的 4K 擷取棒在 2160p30 下**必然**退成 4:2:0 / NV12（373 MB/s，剛好塞得下）或掉幀——
而 4:2:0 會砍掉一半色度取樣，**RAW 直接全毀**。
這正是 `HDMI_RAW_RECORDER_BUILD.md §2` 標註「買前確認 2160p30 能出 4:2:2」的那一項——
現在可以定量回答：**在 USB 3.0 上它做不到，不是設定問題**。

可行路線：
1. **LT6911UXC + Jetson Orin Nano**（HDMI→MIPI CSI，不經 USB）—— 原筆記的第二選項，現在升為**首選**。
2. **PCIe 擷取卡**（Magewell Pro Capture / DeckLink）——頻寬充裕，但需要主機。
3. **USB 3.2 Gen2 (10 Gb/s)** 級擷取（~900+ MB/s 實測）——可行，但要確認型號真的是 Gen2。
4. **降規**：UHD **23.98p**（397.7 MB/s）或 **FHD 59.94p**（248.6 MB/s）勉強落在 USB 3.0 內。

---

## 9. 管線上可注入額外資料的縫隙（「偷加料」）

### 9.0 ★ 兩個新的硬證據

**(a) HDMI 掃描輸出的 framebuffer 是 2 bytes/pixel。**
`FUN_c00E23D0` 在啟動輸出前把緩衝區清成 `0x80008000`，長度算式是 **`W * H * 2`**
（`FUN_c00EAD70` 建結構：`[1]=W`、`[2]=H`、`[4]=buffer 位址>>2`）。
→ 線上**資訊**容量是 **16 bit/px**（不是 §8.3 假設的 24 bit/px；24 是 TMDS pixel period，
其中只有 16 bit 是相機真的能填的內容）。修正後的帳：

| 模式 | 16 bit/px 容量 | 12-bit Bayer | **佔用** | **閒置** |
|---|---|---|---|---|
| UHD 29.97 | 497.2 MB/s | 372.9 MB/s | **75 %** | **124.3 MB/s** |
| DCI 4K 24 | 424.7 MB/s | 318.5 MB/s | 75 % | 106.2 MB/s |
| FHD 119.88 | 497.2 MB/s | 372.9 MB/s | 75 % | 124.3 MB/s |

**可測假設**：若 RAW 在光柵中是線性排列，UHD 的 12-bit Bayer（12,441,600 B）
除以每行 `3840×2=7680` B，**剛好填滿 1620 行**，光柵下方 **540 行（4.15 MB/frame）全空**。
→ 這正是 §6 第 4 點「有無 metadata 列」的具體預測，**一次擷取就能證實或推翻**。

**(b) 模式名稱表 `0xC0BB0E28`（`display get_out` 用）完全印證 §3.1 的 VIC 推導**：

```
id 44=1080_60p  45=1080_50p  46=1080_30p  47=1080_25p  48=1080_24p
   49=2160_30p  50=2160_25p  51=2160_24p  54=1080_120p 55=1080_100p
   56=2160_dci_24p          57=720_48p    58=1080_48p
```
逐項與我從 EDID bitmask 反推的 VIC 一致。另外此表揭露 **id_b = id_a + 30**
（對應 `FUN_c00E9A08` 的 `+0x1E`），即同一組時序有兩個 family（模式暫存器 byte1 的旗標決定）。

### 9.1 縫隙清單（依「乾淨度 × 容量 × 風險」排序）

| # | 位置 | 容量 @UHD30 | 證據 | 風險 |
|---|---|---|---|---|
| **A** | **HDMI 內嵌音訊** | ~288 kB/s (48k/24b/2ch) | `HdmiAMute` @`0xC002BCC8`；音訊暫存器 `0x30190360–0x30190380`；韌體有完整音訊堆疊 `XC_Sound.cpp` / `XC_HalAudio` / `MenuItemSound*Volume`（已有軟體合成 PCM 來源） | 低。完全不碰像素，外錄機**一定**會收成 WAV |
| **B** | **`0x30193080–0x301930D4` 封包引擎** | 88 B/frame ≈ 2.6 kB/s | `FUN_c00EAEF8` 把 caller 結構 `[6..0x1B]` **原封 22 words 寫入硬體**，完全不解讀；enable=`0x3019307C[0]`、start/stop=`0x30193078[0]`、狀態=`0x301930E0[13:0]` | 中。**封包型別尚未確認**，需探測；外錄機端要自己解 |
| **C** | **HDMI timecode** | 32 user bits/frame ≈ 120 B/s | `MenuItemTimeCodeOutputSignalOnHdmi : MenuItemCommon<bool>` @`0xC0743CC8` | 低。已是既有功能，錄影機會記錄 |
| **D** | **光柵閒置區（下方 ~540 行）** | **124 MB/s** | 9.0(a) 推導，**待實測** | 中。容量壓倒性，但位置未證實 |
| **E** | **燒進 RAW 像素** | 任意 | 已有繪圖路徑：`display text` / `osdfile` / `image`，以及自家 `codex/raw_false_color_osd.c` | 高。**吃掉像素**，且若經 ProRes RAW（有損）會被改壞 |

### 9.2 決定性限制：你的錄影機是哪一種

| | Atomos 等商用機 | 自製（LT6911UXC + Jetson） |
|---|---|---|
| A 音訊 | ✅ 存成 WAV | ✅ I2S/SPDIF 直取 |
| B 封包 | ❌ 不外露 | ✅ 看得到 |
| C timecode | ✅ 寫進 metadata | ✅ |
| D 閒置行 | ⚠️ ProRes RAW **有損**，可能被改壞 | ✅ verbatim 保住 |
| E 像素 | ⚠️ 同上 | ✅ |

→ **走自製錄影機，A/B/C/D 全開；走 Atomos，只有 A 和 C 可靠。**

### 9.3 但先問：你真的需要多少頻寬？

`HDMI_RAW_RECORDER_BUILD.md §1` 已實測「**HDMI RAW + 內錄可同時進行**」。
既然如此，gyro/lens 這類 telemetry 大可照舊寫 SD 卡（`fpGyroSup` 的 GCSV 路線），
**HDMI 上只需要一個 frame-accurate 的同步標記**（frame counter + timestamp，4–8 B/frame）。
→ 那 **C（timecode user bits, 120 B/s）或 A（音訊上打 LTC）就綽綽有餘**，
根本不必動 D/E 去碰 RAW 像素。

### 9.4 建議的下一步實驗（不需要擷取卡）

1. **`display get_out`** → 確認目前實際輸出的 mode（對照 9.0(b) 名稱表）。
2. **`HdmiLimit`（`0xC0437740`）** → 它會印 `raw: %dx%d`、`recSize: (%dx%d) @ %dbit`、`small raw:`。
   **這一行直接回答「RAW 幀在光柵裡到底多大」**，也就是 9.0(a) 的 1620-vs-2160 假設。
   這是整個管線上最便宜、資訊量最高的一次測量。
3. **`display hdmi_mask_str ON 2160`** → 遮掉所有 2160 模式，強制 fallback，
   用來在沒有 4K 錄影機時測 FHD RAW，或反過來驗證 EDID 協商行為。
4. 有結果後再決定要不要動 D/E。

---

## 10. 把 gyro 整包塞進 HDMI（頻寬驗算與通道選擇）

### 10.1 需求

原始 gyro = **2500 Hz × 8 B = 20,000 B/s**（`GYRO_FOLLOW_THE_FACTORY.md` 的定版 8-byte 記錄）。

| 輸出模式 | 每幀需要 |
|---|---|
| UHD 29.97p | **667 B/frame** |
| UHD 23.98p / DCI 4K 24p | 834 B/frame |
| FHD 119.88p | 167 B/frame |

### 10.2 §9.1 的五條通道重新篩選

| | 通道 | 每幀容量 @UHD30 | 對 667 B 的餘裕 | 判定 |
|---|---|---|---|---|
| **A** | HDMI 內嵌音訊 | 9,600 B/frame (288 kB/s) | **14×** | ✅ |
| B | `0x30193000` 封包引擎 | 88 B/frame | 0.13× | ❌ **不夠，出局** |
| C | timecode user bits | 4 B/frame | 0.006× | ❌ **出局** |
| **D** | 光柵閒置區（若存在） | 4,147,200 B/frame | **6200×** | ✅ |
| E | 燒進 RAW 像素 | 任意 | — | ✅ 但吃畫面 |

B 和 C 只夠放時間戳，**放不下 gyro**。剩下 A 和 D。

**D 的抗損版本**：即使改用大色塊編碼以抵抗 ProRes RAW 的有損壓縮，
3840×540 的閒置區以 **8×8 px 為一格** 仍有 480×67 = 32,160 格 = **4,020 B/frame**，
對 667 B 還有 **6×** 餘裕。不必逐像素，所以有損壓縮也殺不掉。

### 10.3 ★ 真正的好處：塞進去之後，「切片」這個問題就不存在了

gyro 若隨幀走，**每一幀自己就帶著屬於它的那 ~83 筆樣本**（2500/29.97）。
不需要對時基、不需要比對 GCSV、沒有漂移、沒有起訖點模糊。
時間戳從「同步機制」降級成「**冗餘校驗**」。
→ 對 HDMI 外錄這條路，SD 卡上的 gyro log 就不再是必需品（內錄那條路仍然需要）。

**唯一仍要校準一次的**：感光元件曝光 → HDMI 掃出之間的管線延遲 k 幀。
因為它是常數，拍一次閃光/甩動測一次就永久固定。
（若時間戳寫的是 §10.4 的 64-bit tick，連 k 都可以事後純用數值解出。）

### 10.4 共用時基：TickTimer 其實是 64-bit（新發現）

`src/driver/TickTimer/src/TickTimer.cpp`：

```
FUN_c002B4E0(u32 out[2])   → out[0] = 硬體計數器原始值
                             out[1] = 溢位計數（= 秒）
                             內建重讀防競態（溢位值變動就重來）
FUN_c002B6E0()             → µs = (raw*100)/DAT_c2efabd0 + 1000000*overflow
                             ★ 截成 u32 → 約 71.6 分鐘就繞回
```

→ **不要用 `FUN_c002B6E0`**（開機到關機的連續記錄一定會撞到繞回）。
直接用 `FUN_c002B4E0`，自己組 64-bit：

```c
u32 t[2]; FUN_c002B4E0(t);
u64 t_us = (u64)t[1] * 1000000ull + (u64)t[0] * 100ull / DAT_c2efabd0;
//          ^ 秒（u32 → 136 年不繞回）      ^ 次秒 µs
```

`DAT_c2efabd0 = timer_period/10000`（`FUN_c002B5B0` 初始化時算好）。
這個時基 **gyro 記錄器和 HDMI 注入端共用**，就是整套設計的錨。
`FUN_c002B4E0` 在 GyroData task 已被 Stage-5 實證安全（`FUN_c002B6E0` 就是它的外層）。

### 10.5 兩條路的取捨

| | **A 音訊** | **D 閒置光柵行** |
|---|---|---|
| 容量餘裕 | 14× | 6200×（抗損編碼後仍 6×） |
| 相容性 | **任何錄影機**（含 Atomos），自動存成 WAV | 只有 verbatim 自製機 |
| 相依未知數 | **HDMI 音訊取樣來源是否可由韌體注入（未證實）**。有利線索：韌體有 `XC_AudioPlayer.cpp` / `AudioDeviceInterfacePb.cpp` 播放路徑 + `AudF_W`@`0xC01FD380` 8 MB 環 | **閒置行是否存在（未證實）** → `HdmiLimit` 一次量測就知道 |
| 寫入複雜度 | 串流，天然連續 | 要處理 double/triple buffer：必須寫進「下一幀正要掃出的那一塊」 |
| 注入點 | 音訊環 | `XC_DispIntr` / `XC_DispIntrObserver::XC_ThreadEntryMain`（HDMI 輸出幀執行緒） |

### 10.6 建議順序

1. **先跑 `HdmiLimit`** —— 它同時回答「閒置行存不存在」(D) 和 RAW 實際幾何。一次量測解鎖最多資訊。
2. **同時確認音訊路由** —— HDMI 輸出時放一聲快門音，看外錄機的 WAV 有沒有錄到。
   有 → A 可行且與錄影機無關，是最穩的路；沒有 → 專心走 D。
3. 時間戳與 gyro **一律用 §10.4 的 64-bit tick**，不管最後走哪條通道。
4. 記錄格式沿用 `GYRO_FOLLOW_THE_FACTORY.md` 的 8-byte 定版，前面加一個
   `{u64 t_us, u16 n, u16 seq}` 幀頭 —— 12 B 開銷，總計 ~679 B/frame，兩條路都塞得下。

---

## 11. 實測樣本：`yewn_2410221145_0032.braw`（Blackmagic 外錄，2024-10-22）

用真實外錄檔驗證 §9/§10 的推論。檔案是標準 ISO-BMFF 容器（`wide` + `mdat` + `moov`），**三條軌**。

### 11.1 容器摘要

| 軌 | 內容 |
|---|---|
| video | `brst`，**3840×2160**，321 幀，timescale 24000 / delta 1001 → **23.976p**，13.388 s |
| tmcd | **只有 1 個 4-byte sample** = 起始 timecode（1266016 幀 → 14:39:10:16 @24fps nominal） |
| audio | **`in24`，48000 Hz，2ch，little-endian PCM** |

`moov/meta` 的 key-value：
```
camera_type              SIGMA fp L        camera_id      95930419
manufacturer             SIGMA             firmware_version 5000002
crop_origin              (8.0, 8.0)        crop_size      3840 x 2160      [float32]
sensor_area_captured     6000 x 3376       braw_compression_ratio  8:1
encoder_device_manufacturer  Blackmagic Design   encoder_device_version 3.16
```

### 11.2 ★ 哪些資料能被保存 —— 實測結論

| 通道 | 實測結果 | 判定 |
|---|---|---|
| **音訊** | 全軌 1,285,284 個 sample 的 OR = **`0xFFFF00`**：高 16 bit 全被用到，**最低 8 bit 在每一個 sample 上恆為 0**。→ fp 送的是 **16-bit**，錄影機存進 24-bit 容器補零。上 16 bit **位元透明** | ✅ **192,000 B/s** |
| **相機識別 metadata** | `camera_id = 95930419`（機身序號）、`firmware_version`、`crop_*`、`sensor_area_captured` 都在檔裡。**序號不可能是錄影機硬編的 → 相機確實在頻內送出這些欄位** | ✅ 存在，但**每片固定**，非每幀 |
| **timecode** | `stsz` count = **1**。整段只有一個起始值，其餘靠計數推算 | ⚠️ 只有 **32 bit / 每片**，**無法每幀變動** |
| **像素** | 平均 1,567,638 B/幀；未壓縮 12-bit UHD = 12,441,600 B → **7.94 : 1**，吻合宣告的 8:1 | ❌ **有損，塞像素的資料會被毀** |

→ **§9.1 的 D 和 E 在 Blackmagic 這條路上出局**（BRAW 8:1 有損）。
→ **B（`0x30193000` 22-word 封包引擎）獲得強力旁證**：機身序號/型號/韌體版本必須頻內傳送，
   而那段 88 bytes 的不透明酬載正好裝得下（型號 10 B + 序號 4 B + 廠牌 5 B + 韌體 4 B + 三組幾何 24 B ≈ 47 B）。
   **B 很可能就是相機 → 錄影機的 metadata 通道**，且已證實會被錄影機解讀並保存。

### 11.3 ★ 幾何：獨立印證了 §9.0(a) 的 75%

`crop_origin = (8.0, 8.0)` 是 float，配上 `crop_size = 3840×2160`
→ 線上傳的 Bayer 幀帶 **8 px 護欄**，即 **3856 × 2176**。

```
3856 × 2176 × 1.5 B  = 12,585,984 B      ← RAW 酬載
3840 × 2160 × 2   B  = 16,588,800 B      ← UHD 光柵容量（§9.0(a) 的 2 B/px）
                       -----------
利用率 75.9%，閒置 4,002,816 B ≈ 521 行
```

**這是完全獨立的一條證據鏈**（BRAW metadata）落在我從韌體 `FUN_c00E23D0` 推出的 **75%** 上。
§9.0(a) 的「~540 閒置行」假設成立，精確值是 **~521 行**。

另外 `sensor_area_captured = 6000×3376` → fp L 在 UHD 動態下讀的是 6000×3376 視窗（非全幅 9520×6328）。
錄製模式 3840×2160 @23.976p = §3.1 表中的 **mode id 51 / HDMI_VIC 3**，與韌體表吻合。

### 11.4 對 §10 的結論

**gyro 走音訊（§10.5 的 A）—— 已由實測證實可行：**

```
容量  48000 × 2ch × 16 bit = 192,000 B/s   （= 8,008 B/frame @23.976p）
需求  2500 Hz × 8 B        =  20,000 B/s   （=   834 B/frame）
餘裕  9.6×    ——  或只用單聲道 (96 kB/s, 4.8×)，另一聲道留給真音訊
```

- 位元透明度**已實測**：上 16 bit 全程可用，不需要猜。
- 與錄影機無關：BRAW / ProRes RAW / 任何機器都會原封存下 LPCM。
- 不碰像素，因此不受 8:1 有損壓縮影響。

**時間戳**：`tmcd` 只有起始值，所以 timecode **不能**當每幀戳。
改成把 §10.4 的 64-bit tick 直接編進音訊流的幀頭即可（12 B/frame，佔 0.15%）。

---

## 12. 音訊低位元夾帶：容量與代價（用 §11 樣本實測）

不占用整個聲道，只偷每個 sample 的低 N 個 bit，音訊照常可用。

### 12.1 兩個實測數字

**(a) 這份錄音的噪訊底 = −42.7 dBFS**
（1,285,284 個 16-bit sample，10 ms 窗 RMS：最安靜 −42.7、1st percentile −40.2、中位數 −33.2；峰值 −0.7 dBFS）

**(b) 低位元本來就是純噪訊** —— 熵測量（1.000 = 完全隨機）：
```
low 1 bits : 0.999 / 1
low 2 bits : 0.999 / 2
low 3 bits : 0.998 / 3
low 4 bits : 0.996 / 4
```
→ **bit 0–3 不攜帶任何資訊**，是前級噪聲。覆寫它們是「用噪訊換噪訊」，不是破壞訊號。

### 12.2 容量 vs 注入噪訊

每偷 1 bit/sample（雙聲道）= 48000 × 2 = 96,000 bit/s = **12,000 B/s**。
注入噪訊 RMS = `2^N / sqrt(12)` LSB（相對 16-bit 滿刻度 32768）。

| 偷 N bit | 容量 | B/frame @23.976p | 對 gyro(20 kB/s) 餘裕 | 注入噪訊 | 低於實測底 | 總噪訊底變化 |
|---|---|---|---|---|---|---|
| 1 | 12,000 B/s | 501 | 0.6× ❌ | −95.1 dBFS | 52 dB | +0.00 dB |
| 2 | 24,000 B/s | 1,001 | 1.2× | −89.1 dBFS | 46 dB | +0.00 dB |
| **4** | **48,000 B/s** | **2,002** | **2.4×** | **−77.0 dBFS** | **34 dB** | **+0.00 dB** |
| 6 | 72,000 B/s | 3,003 | 3.6× | −65.0 dBFS | 22 dB | +0.03 dB |
| 8 | 96,000 B/s | 4,004 | 4.8× | −52.9 dBFS | 10 dB | +0.39 dB |

（gyro 需求 = 834 B/frame @23.976p）

### 12.3 定案：取 4 bits

2 bits 就夠（1.2×），但沒有餘裕做同步字/幀頭/CRC。
**4 bits 給 2.4× 餘裕**，足夠放 §10.6 的 12-byte 幀頭 + CRC + 2× 冗餘，
注入噪訊 −77 dBFS 仍在本樣本噪訊底下 34 dB。

⚠️ 本樣本的底是 −42.7 dBFS（環境吵或增益高）。**安靜場景 + 低增益時 fp 的底可能降到 −60～−70 dBFS**
—— 4 bits 的 −77 dBFS 仍安全，但 6–8 bits 會開始露出來。
→ **4 bits 是不看場景都成立的選擇。**

### 12.4 兩個附帶事項

**(a) 底下那 8 bit 目前是白白浪費的。**
錄影機存成 24-bit 容器，但 fp 只送 16-bit，低 8 bit 全程為 0（§11.2 實測 OR = `0xFFFF00`）。
HDMI LPCM 規格支援到 24-bit。若能把 fp 的音訊設定（TX 暫存器 `0x30190360`–`0x30190380` 區塊）
改成送 24-bit，就多拿 **8 個完全免費的 bit = 12,000 B/s，對可聽的 16 bit 零影響**。
搭配再偷 1 bit 即達 24 kB/s。**可行性未驗證**，但上檔乾淨，值得探。

**(b) 資料必須在任何音訊處理之前取出。**
24→16 bit 截位沒問題（資料在高位），但**任何增益調整、正規化、重取樣都會毀掉 LSB**。
解碼器要直接讀 BRAW/MOV 的原始 `in24` sample。

---

## 13. HDMI RAW stream 的觸發點（注入器上膛 / 每幀框界）

> ⚠️ **2026-09-14 更正（使用者指出，已核對程式碼）**
> 本節原本把 §13.1 的 `HdmiRecStart` 當成主要錨點，**那是錯的**。
>
> **外錄工作流程裡不會按機身 REC 鍵。** 開啟 HDMI RAW 後 fp 就**持續**對 HDMI 輸出，
> 起錄／停錄完全發生在外錄設備上，**fp 收不到任何通知**
> （韌體無 CEC、HDMI 無回傳通道 —— 見 §8.1 的掃描結果）。
>
> `HdmiRecStart` 由 REC 鍵處理器 `FUN_c04A6720` 驅動（見下），該鍵在此流程中從未被按，
> 所以 §13.1 **在這個用途上永遠不會觸發**。它只適用於「機身 REC 控制 HDMI 輸出」那個內部模式。
>
> **正確的「RAW 串流正在跑」判斷式在 §13.2 末段**：
> `*(u32*)0xC30783A4 == 2`（HDMI 已連線）**且** HdmiOutputFormat == 1（RAW）。
> 兩者都是狀態而非事件 —— **這條串流是自由運行的，沒有相機知道的片段邊界**。
>
> 設計後果（重要）：注入的資料流**必須是自我同步的**。
> 外錄機會從任意時間點切入，所以不能假設「片段開頭 = 資料開頭」：
> 需要同步字 + 每個區塊自帶 64-bit tick 錨點（§10.4），不能整段只放一個錨點。

三個層級都有，但**只有 §13.2 的狀態判斷與 §13.3 的每幀觸發適用於外錄流程**。

### 13.1 邊緣觸發：串流起停（⚠ 外錄流程用不到 —— 見上方更正）

| 函式 | 位址 | 行為 |
|---|---|---|
| `HdmiRecStart` | `0xC0517D20` | log → **`FUN_c0017140(1)`** |
| `HdmiRecStop` | `0xC0517D58` | log → `RECEnd()` → **`FUN_c0017140(0)`** |

兩者都只有 3–4 行，是**理想的 hook 目標**（displace 一條 `bl`，比照 `TELEMETRY_HOOK.md` 的 cave 手法）。

觸發現場：
- `FUN_c04A6720(param_1, param_2)` @ `0xC04A6720` —— **REC 鍵在「HDMI rec image output」模式下的處理器**。
  `if (state==1) → HdmiRecStop()` ／ `else if (FUN_c04A66A8()!=0) → HdmiRecStart()`。
- `FUN_c04A6A20` @ `0xC04A6A20` —— 另一條停止路徑。

### 13.2 輪詢：狀態 cell（絕對位址已解出）

**系統狀態物件** = `FUN_c00178D8()` = `0xC3033834`，`FUN_c0017AC8(p)` = `p+0x18` = **`0xC303384C`**

| 位址 | 欄位 |
|---|---|
| **`0xC3033A50`** (+0x204) | **HDMI rec image output 狀態，1 = 啟用** ✅ 已驗證（`HdmiRecStart`→`FUN_c0017140(1)` 寫入，判斷式讀 `==1`） |
| `0xC3033A44` (+0x1F8) | 可用性判斷用，語意未定 |
| `0xC3033A54` (+0x208) | 子狀態 |

**HDMI 裝置物件** = `FUN_c002B9C8()` = **`0xC30781AC`**（`XC_DisplayHdmi`，0x200 bytes）

| 位址 | 欄位 |
|---|---|
| `0xC30781C4` (+0x18) | EDID 推出的模式支援陣列（60 × u32）— §3.2 |
| `0xC30782B4` (+0x108) | 手動遮罩陣列 — `display hdmi_mask` 寫這裡 |
| **`0xC30783A4`** (+0x1F8) | **HDMI 連線狀態，2 = 已連線** |
| `0xC30783A8` (+0x1FC) | 音訊 mute 旗標（`HdmiAMute` 寫） |
| `0xC30783A9` (+0x1FD) | suspend 旗標 |

> ⚠️ **`HdmiRecStart` ≠「RAW 像素正在流」。** 它是 rec-image-output *連線狀態*。
> 「RAW 串流正在跑」的正確判斷式是：
> `*(u32*)0xC30783A4 == 2`（已連線）**且** HdmiOutputFormat == 1（RAW，menu slot `0x3B8` / `FUN_c005FCB8`）。

### 13.3 每幀觸發：display 中斷（與 HDMI 光柵同相）

```
FUN_c02EDA08(obj, ch)                       建構 + 註冊
   └─ FUN_c00EAB20({handler, ch, 0})        向 HDMI 驅動註冊 per-display-interrupt callback
handler: ch0 = FUN_c02EDB38 @ 0xC02EDB38
         ch1 = FUN_c02EDB80 @ 0xC02EDB80
singleton: ch0 = 0xC34343E4 , ch1 = 0xC34343D0

每次觸發 → FUN_c02EDBC8(obj):
   FUN_c00EA608(plane)  × 3      ch0 用 plane 0/1/2，ch1 用 3/4/5
        ↑ 回傳「當前正在掃出的 framebuffer 實體位址」= val*4 + 0x40000000
   FUN_c001A048(subject, 0x800, 0, 4, ch, p0, p1, p2)   → 派送給觀察者
   XC_INTR__v0(..., 2)                                   → 中斷結束
```

**★ 重點：`XC_DispIntrObserver::XC_ThreadEntryMain` 是 task context，不是 ISR。**
中斷只負責讀 3 個 plane 位址並 post 事件，實際工作在觀察者執行緒跑。
→ 對照 `TELEMETRY_HOOK.md` §1B 的兩難（IRQ 0x79 有相位但不能用 blocking syscall），
**這裡同時拿到「每幀相位」與「task context」**，是比 IRQ 0x79 更好的注入點。

而且 `FUN_c00EA608` 直接給出**當前掃出中的 framebuffer 位址** ——
若走 §9.1-D（寫閒置光柵行），這就是解決 double/triple buffer 的那把鑰匙。

### 13.4 需要一次實機確認的事

1. **ch0 / ch1 哪個是 HDMI**（另一個是 LCD）。看觸發速率是否等於 HDMI 幀率即可判定。
2. display 中斷與 HDMI 掃出同相，而掃出比感光元件曝光晚 **k 幀**（§10.3 的常數）—— 仍要校準一次。
3. **fp 沒有「HDMI REC 觸發」選單項**（HDMI 選單只有 Info / Format / IsManual / Size / Framerate /
   ZoomRatio / TimeCodeOutputSignalOnHdmi）→ **相機不會叫外錄機開始錄**，§11 那段 BRAW 是手動起停的。

---

## 14. 實機量測（2026-09-15，fp + AVerMedia ExtremeCap UVC/UAC）

首次用真機 + HDMI 擷取卡驗證前面的靜態推論。
探針：`projects/gyro-sup/hdmi_audio_probe/`（`hdmiaud` 錄音、`vsnap` 看影像訊號，Swift/AVFoundation，零安裝）。

### 14.1 鏈路確認

```
vsnap:  影格 1920x1080  pixfmt=2vuy  mean 125.7 sd 4.1 min 61 max 138
menu:   SetHdmiOutputSize = 1   SetHdmiOutputFramerate = 5   SetHdmiOutputInfo = 1
```

擷取卡收到 1920×1080 有內容的訊號 → **fp 確實在輸出**。
`SetHdmiOutputSize = 1` ↔ 1920×1080，**§2.1 的 Size enum 解碼在真機上得到驗證**。
`SetHdmiOutputFramerate = 5` ↔ §2.2 對照表的 f8 = 59.94 fps。

### 14.2 ★ HDMI 在 live view 下持續送真實 16-bit 麥克風音訊

錄 3 秒（32-bit float 擷取，287,744 取樣）：

```
L peak −39.5 dBFS   rms −52.4 dBFS
R peak −32.9 dBFS   rms −46.8 dBFS
對 16-bit 網格最大誤差  0.000000 LSB      ← 每一個取樣都精確落在 1/32768 的整數倍
非零 286,617 / 287,744            |值| 範圍 1..744 LSB
```

**「fp 送 16-bit」從 §11.2 的離線 BRAW 推論升級為活訊號實證。**
而且不需要錄影，**live view 狀態下 HDMI 就持續帶著麥克風音訊**。

### 14.3 `SetAudioRecSupport = 0` 不會讓 HDMI 音訊靜音

| | L rms | R rms |
|---|---|---|
| 原狀（=1） | −52.4 dBFS | −46.8 dBFS |
| 設為 0 | −52.4 dBFS | −47.2 dBFS |

無變化。→ `FUN_c01F9BF8` @ `0xC01F9BF8` 的靜音條件靠的是另外三項
（`FUN_c01FB558()`、`+0x18`、`+0x19`），**不是選單的「音訊記錄」旗標**。
§0.1(c) 的描述要照此收斂。

### 14.4 ⚠️ 修正：`HdmiOutputFormat` 不是 0/1 二值

實讀 **`SetHdmiOutputFormat = 3`**（當時 `SetHdmiIsManual = 0`、非 RAW 狀態）。

§2.1 與 §13.2 寫的「0 = 一般、1 = RAW」**過度簡化**。
韌體能確定的只有 `MenuItemHdmiOutputSize::v8` @ `0xC00AD8C8` 要求
**該項 == 1 才允許 DCI 4K**，所以 1 是「某個 RAW 模式」——
但這個 enum **至少有 4 個值**，完整語意未知。
`FUN_c0400600`（PTP setter）取的是 `char`，也支持它不是布林。

→ **不要把「format == 1」當成「RAW 開啟」的唯一判斷式**，
除非先實測列舉出這個 enum 的全部取值。
