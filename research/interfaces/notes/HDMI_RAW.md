# SIGMA fp Ver.5.02 — HDMI RAW 輸出路徑分析

> ⚠️ **2026-09-13 部分修正 → 見 `HDMI_RAW_FORMAT.md`**
> - **§2 的「相機不讀 EDID / 不看接了什麼」是錯的。** 韌體有完整 CEA-861 EDID 解析
>   （`FUN_c00EBD60` 讀 SVD 清單 + HDMI VSDB 4K×2K），HPD 接上後由 `FUN_c00EA9E8` 建 60 筆
>   模式支援表，送模式前逐一比對，不支援就走 fallback 鏈。
>   → **「無 vendor handshake、無廠牌辨識」仍然成立**；錯的只是「不讀 sink 能力」這句。
> - 新增內容：完整解析度×幀率矩陣、14 個模式 ↔ CEA VIC 對照、297 MHz 頻寬天花板、
>   線上 colour format 為編譯期常數、光柵利用率 75%、線上 Bayer 幀 = 3856×2176。

## 一句話結論

RAW-over-HDMI 是**標準 HDMI 視訊光柵（raster）承載打包後的 12-bit Bayer**；
連結層 100% 標準 HDMI，**相機端沒有任何 vendor handshake、也不讀取錄影機 EDID/身分**。
「這是 RAW」的解讀完全在錄影機端（Atomos/BMD 需預先內建 fp 的解包 profile）。
→ 屬「**慣例式（by convention）的半標準 transport**」，不是協商式協定，也不是被 vendor handshake 解鎖。

---

## 1. RAW buffer → HDMI 資料流

```
感光元件 (Bayer)
   │
   ▼
SIG0 / SIG1  影像處理硬體管線 (XZ01 ASIC)
   │   RAW 輸出模式時，走 "RAWOUT" 區塊而非完整 YUV 開發：
   │   ├─ SIG0 RAWOUT / SIG1 RAWOUT   ← 把 12-bit Bayer 打包寫入 DRAM framebuffer
   │   └─ SIG0_RAWSHAD_LINEAR 等前處理
   │   （RAWMODE ON → 寫 SIG 硬體暫存器；debug 路徑 FUN_c04eb9e8 寫 mode 值 0x123..0x678）
   ▼
DRAM framebuffer（打包後的 RAW 幀）
   │
   ▼
DisplayOutputSelect*  輸出路由選擇
   ├─ DisplayOutputSelectBaseLcdOnly
   ├─ DisplayOutputSelectBaseHdmiOnly
   └─ DisplayOutputSelectBaseDual / DualW71c1   （LCD + HDMI 同時）
   │   依物件狀態 +0x1f8（輸出模式 1/2/4）選不同 raster 設定表
   │   （mode==4 → &DAT_c0b50fe4；否則 → &DAT_c0b50ff4）
   ▼
HDMI 掃描輸出：以「選單設定的標準視訊時序」把 framebuffer 掃出去
   ├─ SetHdmiOutputSize       1080 / 2160 / (4224)
   ├─ SetHdmiOutputFramerate  eXC_MenuFrameRate
   ├─ SetHdmiOutputFormat     eXC_MenuHdmiOutputFormat（含 RAW 這一格式：font_G_HDMIfmt_raw）
   └─ SetHdmiOutputZoomRatio / Info
   ▼
XZ01 ASIC 的 HDMI TX（TMDS/AVI-InfoFrame 等協定層在硬體，不在本韌體碼內）
   ▼
HDMI 纜線 → 外接錄影機
```

驅動與時序：
- `XC_DispIntr`（display interrupt / vsync）產生幀時序；
  `XC_DispIntrObserver::XC_ThreadEntryMain` 是輸出執行緒。
- `XC_Observer<const XC_MovSigYuvOutParam&>` / `XC_Subject<...,4U>`：SIG 輸出參數觀察者，
  協調每幀輸出（RAW 與 YUV 兩條輸出路徑共用這套幀同步）。
- `XC_MediaDriverHost` / `XC_MediaDriver`：媒體輸出驅動。

幀幾何（由 `HdmiLimit` @ `0xC0437740` 除錯輸出可讀出欄位）：
`table %d imgr %d sig %d`、`small raw %dx%d`、`raw %dx%d`、
`recSize %dx%d %dbit`、`stillSize %dx%d %dbit`、`lvType %d lvCam %d`、`full_angle_mode`。
→ RAW 幀被當成「有寬高與位元深度的一張影像」直接塞進視訊時序。

相關 acquisition 模式（12-bit 系列）：
`ACQ_12BIT`, `_MIX`, `_CROP`, `_CONTINUOUS`, `_MIX_CROP`, `_CONTINUOUS_MIX`,
`_CONTINUOUS_CROP`, `_MIX2`, `_CONTINUOUS_MIX2` …；`gain_state: movie_raw_12bit`。

---

## 2. 連線 / 觸發（無協商）

| 元件 | 位址 | 行為 |
|---|---|---|
| `XC_DisplayHdmiObserverDevOp` | v1 @ `0xC02DC200` | 反應 HDMI **熱插拔 (HPD)**：狀態 `+0x1f8==2` 視為已連線，設定 in/out notify（`in notify`/`in notified`/`out notify`/`out notified`/`in suspend`）。**只看有沒有接、不看接了什麼。** |
| `DelayableHdmiMonitoringConnection` / `DelayableHdmiRecImageOutputConnection` | — | 兩種連線意圖：即時監看 vs 錄製影像輸出（對應上面的 raster 設定差異） |
| `HdmiRecStart` | `0xC0517D20` | 送內部事件 (msg id 2, param 1) 開始錄製影像輸出——**純內部事件，無對外交握** |
| `HdmiEdidFixed` | `0xC04A2760` | 可**強制固定 EDID**（配合 debug 指令 `display hdmi_edid [2160_30/...]` / `off`）。代表 RAW 輸出**不依賴讀取 sink 的 EDID** |

**關鍵反證（找不到的東西）**：全主韌體字串掃描中——
- ❌ 無 `EDID read` / `DDC` / `sink capability` / `read sink` 之類的**能力讀取**字串
- ❌ 無 `manufacturer id` / `vendor id` / 針對特定廠牌分支
- ❌ 無 CEC / VSIF（vendor-specific InfoFrame）協商碼
- ❌ 無 Atomos/Blackmagic/Ninja/Shogun/Video Assist 的**裝置偵測資料庫**
  （`AtomosFr` 只出現 **1 次**，且是個 debug 記錄/指令函式 `0xC00ECD30`，非裝置交握）

---

## 3. 那些品牌字串是什麼？

- **`ProRes …`（ProRes HD / 2K / 3.2K / 4K UHD / S16 / Ana.(x2) / 4:3 2.8K …）**：
  這些是**錄影機端**的錄製解析度預設名（Atomos 收到 fp 的 RAW 後錄成 ProRes RAW）。
  在韌體中作為 UI/資源字串（各出現 17/34 次於資源表），**不是相機自己編 ProRes**，
  也不是透過 HDMI 對錄影機下的指令。fp 自身只錄 CinemaDNG / MOV。
- **`AtomosFr` / `TSBMDAJA`**：debug 函式內的記錄標籤，非裝置協定。

---

## 4. 對兩個問題的直接回答

**Q1「RAW buffer → HDMI 怎麼走」** → 見 §1。
簡述：SIG0/SIG1 的 RAWOUT 硬體區塊把 Bayer 打包進 DRAM framebuffer →
DisplayOutputSelect 選路由 → 以選單指定的**標準視訊時序**由 XZ01 HDMI TX 掃描輸出。
RAW 幀被當成一張「有位元深度的影像」直接放進普通視訊光柵。

**Q2「標準/半標準 transport，還是 Atomos/BMD 專屬 handshake 才開啟」** →
**半標準、慣例式；相機端無 vendor handshake。**
- 連結/實體層：**完全標準 HDMI**（TMDS/InfoFrame 由 ASIC 處理，就是一般視訊訊號）。
- 酬載：把打包 Bayer 塞進視訊幀，**沒有 in-band 標記說「這是 RAW」**（無 vendor InfoFrame 宣告）。
- 開啟條件：**只看選單設定（HDMI 輸出格式選 RAW）+ HPD 有接**，不做任何裝置識別或能力交換。
- 因此「需要特定錄影機」的部分**全在錄影機端**：Atomos/BMD 必須預先內建 fp 的
  解包 profile（知道這張 1080p/4K 光柵其實是某位元深度/排列的 Bayer）才錄得出 RAW。
  相機不會、也不需要對錄影機做任何專屬交握。

> 佐證強度：**高**。基於全韌體字串掃描（無 EDID 能力讀取 / 無 vendor 分支 / 無裝置庫）
> 加上輸出狀態機反編譯（純內部 mode + HPD 驅動）。唯一未逐位元確認的是 XZ01 ASIC
> HDMI TX 送出的 AVI-InfoFrame 具體欄位（那在硬體暫存器層，不在本韌體碼內）——
> 但那不改變「相機端無交握、無裝置識別」的結論。

---

## 5. 產出檔案

| 檔案 | 內容 |
|---|---|
| `out/decomp/hdmi_named/hdmi_named.c` | 47 個 HDMI/Display/DispIntr/OutputSelect/MediaDriver 具名函式 |
| `out/decomp/hdmirec.c` | AtomosFr / HdmiRecStart / HdmiEdidFixed / HdmiLimit |
| `out/decomp/rawout.c` | SIG RAWOUT / RAWMODE 相關 |
| `out/decomp/hdmiraw.c` | HdmiRaw / imager createraw 等 |
