# SIGMA fp Ver.5.02 — HDMI RAW 輸出路徑分析

> **2026-10-23 ISP 路徑重查（§6）：** 已用原韌體離線執行 HDMI RAW 表的 28 個
> profile，確認有 CRCT RAW 路由與模式相依的縮放。舊 §1 直接指定
>「SIG0/SIG1 RAWOUT + RAWSHAD_LINEAR」超出當時證據，已收斂；黑位、壞點、
>陰影校正、白平衡及降噪是否烘入 HDMI RAW，尚未逐項證實。

> **2026-10-23 res-custom 共用介面重查（§7）：** 可共用選單、producer 與配方管理，
> 需要獨立的 HDMI RAW 套用器；28 模式離線驗證確認虛擬 entry 的顯示分類、格式與
> gain 判斷都有差異。§1–5 是早期筆記；其中「無廠商辨識」已被
> `TSBMDAJA @ C00EC948` 的 ATS/BMD/AJA 比對推翻；精確 Bayer packing、guard 與
> 接收器 metadata 尚未閉合，不能依舊文的容量比例推導任意解析度可外錄。

> ⚠️ **2026-09-13 部分修正 → 見 `HDMI_RAW_FORMAT.md`**
> - **§2 的「相機不讀 EDID / 不看接了什麼」是錯的。** 韌體有完整 CEA-861 EDID 解析
>   （`FUN_c00EBD60` 讀 SVD 清單 + HDMI VSDB 4K×2K），HPD 接上後由 `FUN_c00EA9E8` 建 60 筆
>   模式支援表，送模式前逐一比對，不支援就走 fallback 鏈。
>   → EDID 能力解析與廠商辨識均存在；是否另有 RAW 私有交握，不能靠字串缺席判定。
> - 新增內容：完整解析度×幀率矩陣、14 個模式 ↔ CEA VIC 對照、297 MHz 頻寬天花板、
>   線上 colour format 為編譯期常數、光柵利用率 75%、線上 Bayer 幀 = 3856×2176。

## 一句話結論

原廠 HDMI RAW 使用 Bayer 輸出鏈與標準 HDMI 視訊時序；相機會讀 EDID，
也有 ATS/BMD/AJA 廠商辨識。精確 RAW packing、metadata 與接收端解碼契約仍需驗證。
目前可確認原生縮放與輸出設定（§6），以及接入 res-custom 所需的軟體邊界（§7）；
不能由此保證任意自訂尺寸能被外錄機辨識。

---

## 1. RAW buffer → HDMI 資料流

```
感光元件 (Bayer)
   │
   ▼
XZ01 的 RAW 處理／輸出路徑
   │   已驗證：CRCT profile → 原生路由選擇 → RAW 縮放／輸出設定（§6）
   │   ├─ 全幅 UHD / DCI：CrctRwzmToBufA
   │   ├─ 全幅 FHD：CrctHbin2ToBufA 抽頭
   │   └─ Crop：CrctCrmfToBufA 抽頭
   │   尚未閉合：逐模式的 SIG RAWOUT／校正級與 HDMI Bayer payload 對應
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

**歷史段落：以下「不讀 EDID／無廠商辨識」結論已撤回，見頁首及 §7.5。**
保留早期排查紀錄，不應再作為新功能的前提。

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
- **`AtomosFr` / `TSBMDAJA`**：不能一律視為無功能的 debug 標籤。
  `TSBMDAJA @ C00EC948` 實際比對 EDID 廠商碼 ATS/BMD/AJA；見 §7.5。

---

## 4. 對兩個問題的直接回答

**Q1「RAW buffer → HDMI 怎麼走」** → 見 §1。
簡述：XZ01 的 RAW 處理／輸出路徑產生 Bayer buffer →
DisplayOutputSelect 選路由 → 以選單指定的**標準視訊時序**由 XZ01 HDMI TX 掃描輸出。
不能僅憑診斷區塊名稱斷言所有模式都經 SIG0/SIG1 RAWOUT 或特定校正級；見 §6。
RAW 幀被當成一張「有位元深度的影像」直接放進普通視訊光柵。

**Q2「標準/半標準 transport，還是 Atomos/BMD 專屬 handshake 才開啟」** →
**標準 HDMI 承載相機專用 RAW 資料；RAW 私有交握的全貌尚未確認。**
- 連結/實體層：**完全標準 HDMI**（TMDS/InfoFrame 由 ASIC 處理，就是一般視訊訊號）。
- 酬載：原廠 RAW buffer 進入專用 display 路徑；精確線上 packing 與標記尚未完整還原。
- 開啟與選模式：有選單狀態、HPD、EDID 能力表和廠商辨識，不能簡化成單一布林。
- 外錄機必須能解讀 fp 的 RAW 格式；只讓接收器看到一條標準 4K 訊號，
  不能證明它能辨識修改過的 Bayer 幾何。見 §7.5。

---

## 5. 產出檔案

| 檔案 | 內容 |
|---|---|
| `out/decomp/hdmi_named/hdmi_named.c` | 47 個 HDMI/Display/DispIntr/OutputSelect/MediaDriver 具名函式 |
| `out/decomp/hdmirec.c` | AtomosFr / HdmiRecStart / HdmiEdidFixed / HdmiLimit |
| `out/decomp/rawout.c` | SIG RAWOUT / RAWMODE 相關 |
| `out/decomp/hdmiraw.c` | HdmiRaw / imager createraw 等 |

## 6. HDMI RAW 是否經 ISP：2026-10-23 離線驗證

**能確認它經過 XZ01 的 RAW 處理／輸出設定鏈，不能稱完全繞過影像處理。
能確認原生 RAW 縮放；不能把「RAW」解讀成 sensor 每個數值原封不動。
目前仍不能逐項確認黑位、壞點、陰影校正、WB、NR 是否作用於 HDMI payload。**

### 6.1 模式與原生執行證據

`HdmiLimit @ C0437740` 把設定 `+26 != 0`、`+47 == 0` 標成 `HdmiRaw`。
`C043B988` 的同條件分支選 `C0BE5450`，28 筆、每筆 16 bytes，結束於
`C0BE5610`。其 profile ID 是第二個 word，不能拿第三個 sensor enum 當 profile。

本輪由 `C0439D18` 的 65 個原生 column 位址重讀 ROM，再執行：

```text
HDMI RAW profile → C0438018 建 RAW descriptor
 → C031D988 → imager0 ops+9C = C0325228
 → C0320AF0 / C032D9A0 → CRCT driver 暫存器寫入
```

| 模式組 | 筆數 | 原生 record 抽頭 | Record RAW zoom 參數 |
| --- | ---: | --- | --- |
| 全幅 DCI4K24 | 1 | `CrctRwzmToBufA`，a1 | `1500/1024` |
| 全幅 UHD30/25/24/23.98 | 4 | `CrctRwzmToBufA`，a1 | `1600/1024` |
| 全幅 FHD，各幀率 | 9 | `CrctHbin2ToBufA`，a7、mux=4 | `1600/1024` |
| DCI/UHD/FHD Crop | 14 | `CrctCrmfToBufA`，a0、mux=1 | ROM 1023，原生夾至 unity 1024 |

例如 UHD30 profile366、UHD24 profile443：原生 driver 寫
`300F0900=1`、`300F0908=300F090C=00E00640`，低 16 bits 是 1600。
DCI4K24 profile365 則是 `00EE05DC`，低 16 bits 是 1500。
這是原韌體執行產生的配置，不只是從表格名稱猜測。

**不要把預覽寄存器當錄製效果。** DCI/UHD Crop 的 record zoom 是 unity，
卻仍可能看到 `300F0900=1`、`0908/090C=800`，那是主管線為 preview 配的 2×。
錄製選的是 CRMF 抽頭。`Hbin2` 也只是抽頭名，不單憑名字斷言正在 bin。

全部 28 筆的格式欄位 `+80/+84 = 7/11`；這是處理格式 enum，**不是 7-bit/11-bit**。
RAW source mask `+3C` 也依模式變（`101`、`4`、`1`），不能用一張 SIG 方塊圖概括。

### 6.2 舊證據的界限與位址訂正

- `C01597B8` 是標籤／暫存器診斷 dumper；`C019C810` 建 descriptor 對照。
  它們證明硬體區塊及對照存在，**不證明 HDMI RAW 時啟用**，也不證明像素先後。
- dumper 先印標籤再列地址：`SIG0_NLmeans = 30112940`，
  **`SIG0_RAWSHAD_LINEAR = 301129A0`**。舊格式筆記把它錯配到前一塊，已修正。
- `RAWMODE ON` 的 `C04EB9E8` 寫的是經 `C00554E8` 取得的設定物件 `+4`，
  值為 `123..678`；不能說這幾個值本身是 SIG MMIO 寫入或校正開關。
- 已存在的 WB／offset setter、PQ dirty 更新、非線性表，都只能各自證明配置能力。
  未把 HDMI RAW 的 source tap、active context、校正 enable 與當幀 Bayer 像素閉合前，
  黑位／壞點／shading／WB／NR 應標「未確認」，不能標「已開」或「已關」。
- [官方手冊](https://www.sigma-global.com/en/support/download/fp_Manual_FW_Ver.5.0_EN.pdf#page=100)
  第100頁只明確說 CinemaDNG 不支援選單的 Color Shading Correction；
  不能外推為 HDMI RAW 的所有感光元件校正都關閉，也不能把鏡頭色偏校正等同 sensor dark shading。

### 6.3 重現與限制

- 工具：[audit_hdmi_raw_isp.py](../audit_hdmi_raw_isp.py)。
- 結果：[hdmi-raw-isp-audit.json](../hdmi-raw-isp-audit.json)，28/28 通過，
  保存每模式的 ROM row、descriptor 欄位、實際走過的指令位址與 CRCT 寄存器結果。
- 重算：`python3 -B research/interfaces/audit_hdmi_raw_isp.py`。
- seg0 SHA256：`aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`。
  seg1 SHA256：`0dcaca8f5441fe4ddc6ed801cb888e325df4e76006e4f53a1c3219809b22ce7b`。
- 只驗證 W71c1 原廠 HDMI RAW 表及原生配置程式；descriptor/manager、sensor singleton
  查找有明示 stub，MMIO 是零初值 RAM。沒有模擬 ASIC 像素運算、沒有實機 active-state
  讀回、沒有操作相機。不能用本結果聲稱插值核、各校正的逐像素效果或精確線上 packing 已驗證。

## 7. 能否與 res-custom 共用介面：2026-10-23

**可以共用使用者介面、producer 與配方管理；現有 CinemaDNG 套用端不能直接套到
HDMI RAW。建議同一個 res-custom consumer 管理兩個輸出套用器，保留一個共用動態列。
這是離線可行性研究，尚未實作 HDMI 產品補丁，也未驗證外錄機接收自訂幾何。**

### 7.1 共用流程與必要的分流

```text
res-custom 解析度列 / Res Lab 設定頁
                  ↓
             producer → RCD
                  ↓
       共用驗證、資源預算、選擇與提交交易
                  ↓
          共同的 sensor 讀出需求
                  ↓
        ┌─────────┴───────────┐
        ↓                     ↓
 CinemaDNG 套用器       HDMI RAW 套用器（待實作）
 現有三張 CDNG picker   HDMI picker + RAW display 身分
 DNG 位深 / writer      RAW format11 / buffer 與顯示路由
 DNG active area        Bayer 幾何與 HDMI carrier 契約
```

感測器與前段管線是共用資源，不能讓兩個套用器各自切成互相衝突的 sensor mode。
若要同時使用兩個輸出，核心須先編譯出共同讀出，再檢查各輸出所需的抽頭與幾何；
目前沒有證明任意 CDNG／HDMI 自訂組合可同時使用。

| 元件 | 可共用程度 | 本輪判斷 |
| --- | --- | --- |
| 原生解析度列表、QS、共用動態列、producer 私有設定頁 | 可沿用架構 | 不需要再造一套 HDMI 解析度 UI |
| RCD 讀取、校驗、staging、圖示與容量管理 | 可沿用框架 | target 與 HDMI 語意須納入驗證 |
| 虛擬 sensor mode、讀出視窗、縮放／bin 配方 | 可共用描述及底層查詢機制 | 每個 target 重新核對抽頭、時序與 buffer；不代表所有配方均有效 |
| profile／canvas 虛擬化 | 同一機制、不同 target 編譯 | HDMI donor、格式、entry kind、gain 判斷須分流 |
| CDNG 位深與 writer policy | 不可直接套用 | 不把 DNG 8/10/12-bit 當 HDMI transport 格式 |
| HDMI display、EDID、實際輸出格率、接收器解碼 | HDMI 專屬 | 保留原廠協商並驗證真正輸出狀態 |

現有程式的精確定義見
[virtual_rcd.h](../../../projects/open-gate/build/res-custom/virtual_rcd.h)、
[ogc_virtual.c](../../../projects/open-gate/build/res-custom/ogc_virtual.c)、
[ogc.c](../../../projects/open-gate/build/res-custom/ogc.c)。
`res-custom-v4` 也有相同的 HDMI picker 缺口；兩個來源目錄的功能並不完全相同，
不能因名稱含 v4 就假定已包含另一目錄所有能力。

### 7.2 原生流程的三個確定障礙

**A. 查表入口與顯示分類都要處理。**

現有 `ogc_pick @ C043CCF8` 只接受 `C0BE5810/59B0/5B50` 三張 CDNG 表。
HDMI RAW 在 `C043B988` 的 `cfg[25]==0 && cfg[26]!=0 && cfg[47]==0` 分支，
走 `C043CE18` 搜尋 `C0BE5450..C0BE5610` 的 28 筆 entry。
本輪原生執行這個查表函式，28 筆均找到原表 entry，沒有經過 CDNG picker hook。
現有 `fill_s` 還固定產生 entry 第一個 word=5；HDMI 原表全部是3。
相同 16-byte 外形不等於 entry 語意相同。

原生 `XC_LiveViewConfiguratorW71c1::v5 @ C043C090` 再用表項**指標範圍**分類：
`C043D158` 只把 `[C0BE5450,C0BE5610)` 視為 HDMI RAW。

| 回傳 entry | 原生選到的 display param，相對 configurator | 28 筆結果 |
| --- | --- | --- |
| 原廠 HDMI entry | DCI4K `+560`；其他 `+538` | 全部符合 |
| 完整複製到 RAM，無身分適配 | `+268`，並進診斷 fallback | 全部失去 RAW display 分類 |
| RAM entry，測試替身只辨識本 consumer 的 HDMI entry | DCI4K `+560`；其他 `+538` | 全部恢復 |

最後一列只是**介面契約的離線實驗**：測試在 `C043D158` 攔認一個自有 RAM entry。
尚未決定產品 hook 位置、鏈結或 relocation，也不是建議對所有呼叫強制回1。
正式套用器應以 target、entry owner 與 generation 辨識自有 entry，其他呼叫照原廠。
改 key 或調整查表長度，本身不能解決指標範圍分類。

**B. HDMI 格式不能讓 CDNG 位深覆蓋。**

28 個 HDMI RAW profile 的 canvas `+80/+84=7/11`。
原生 `C0434EF8` 把它們搬到 Sig config `+08/+104`。
把現有 `ogc_canvas` 的兩個位深指定式套在同一份 HDMI canvas，再執行原生轉換：

| 使用的指定式 | Sig config `+08/+104` | 保留 HDMI format11 |
| --- | --- | --- |
| 原廠 HDMI | `7/11` | 是 |
| CDNG 8-bit | `10/10` | 否 |
| CDNG 10-bit | `10/9` | 否 |
| CDNG 12-bit | `7/7` | 否 |

這是設定資料的原生搬運驗證，**不是模擬格式11的 ASIC 像素運算**。
格式 enum 也不是位元數。HDMI adapter 必須使用 HDMI donor／格式政策，
保留或明確編譯 `+3C` RAW source mask、record tap、preview 與各 buffer 幾何；
不能只在 CDNG 配方後面補一個「外錄」旗標。

**C. RAW display 與 gain 判斷有額外語意。**

`+538/+560` 使用 `XC_LiveViewDispParamWithRaw`：

- `v5 @ C04380E0` 的 index3，與 `v6 @ C0438150` 的 mask2，直接回傳 RAW placeholder，
  本輪 56 次原生呼叫都得到 descriptor type5，且不經現有 `OUT @ C0437E98`。
  `ogc_out` 本身也只處理 index0/2 的預覽 aspect；它不能負責宣告外錄 Bayer 尺寸。
- 依反編譯，`C042B8C8` 對 type5 改從 LiveViewModeMgr 取 RAW descriptor，
  透過 `C01D5F40/C01D5F58` 取 RAW ring 地址／數量，轉交 `C02E50F8`。
  buffer 配置與 stride 必須和這條路一致，不能接成一般 YUV descriptor。
- `C043A1C8` 的 object `+E0` 即內嵌 canvas `+84`；值11時加 class bit `100`。
  28 個 stock HDMI PID，以及同 canvas 改成測試 virtual PID85，都回 `100`；
  原生 `C0436080` 查 raw-movie bit 時回0。
  現有 `ogc_gs @ C03A6DD8` 會替活動的 CDNG virtual profile 回1，不能無條件沿用到 HDMI。

### 7.3 共用 RCD 服務要增加的契約（設計，未實作）

現有 Virtual RCD **ABI2** 的 `vrc_input` 只有 `fps_rank/format`，
`format` 來自內錄 `GET_FMT`；`vrc_apply` 要求它為0（CinemaDNG）。
HDMI RAW 是另外的狀態，不能拿這個欄位判斷，也不能把 `format` 偷換含義。
`capabilities/reserved` 目前必須0，現版會拒絕非零值。

下一版需明確宣告並協商：

1. **輸出目標**：配方支援哪些 target、當前要求哪個 target、實際啟用哪個 target。
   保留內錄 format；同時帶入有效的 HDMI 狀態與原廠 mode／rate。
   不能單靠 `HdmiOutputFormat==1`，該 enum 的完整映射尚未還原，見格式筆記 §14.4。
2. **分開的幾何**：sensor 讀出視窗、每個 RAW 抽頭／buffer 尺寸、有效 Bayer 區域、
   stride／padding／CFA 原點，以及標準 HDMI carrier／精確有理數幀率。
   現有 CANVAS pair list 雖裝得下不少數值，卻沒有表示這些契約的欄位；
   DNG `active_w/h` 不能直接當 HDMI 介面尺寸。
3. **target 限定的編譯與作用域**：虛擬表 entry、canvas、gain、bin kernel、格率 UI、
   preview/playback、writer 各按 target 選用。共有一個 sensor mode 時先解衝突。
   現有 `FLAG/PICKOK` 不是 HDMI target 身分，尤其 `ogc_binfilt.c` 只依目前 row 與旗標取配置。
4. **可觀察的狀態**：回報 requested/effective target、carrier、幀率、generation 與不支援原因。
   保留目前一列的 UI 身分與 consumer 自有設定，原廠設定繼續只存合法 backing value。
5. **明確相容性**：擴充 ABI／discovery 與 producer 的協商；ABI2 舊 producer 保持原有語意。
   HDMI 配方用新的 required section 與提高 `MINCORE`，讓舊 consumer 明確拒絕。
   不得用 optional section 讓舊版忽略 HDMI 意圖後誤當 CDNG 套用。

這些都可在既有 consumer／producer 服務架構內設計；目前沒有證據需要另外分叉 loader。
仍須完成服務版本相容設計，不能直接把 ABI2 header 的保留欄位當新功能啟用。

### 7.4 套用交易與連線切換

現版 `busy()` 只檢查本機 MOV REC、XMP file 與 MOV writer，
不能知道外錄機是否正在錄。HDMI RAW 待機時已有連續輸出；
相機沒按 REC，不等於改配方不影響外錄。

建議第一版先在 HDMI 輸出停用／未連線時套用，連線後由原廠流程重建。
若要連線中 Apply，須另外實作 HDMI owner 的停止、buffer reader 退場、提交、
重新協商／重啟與失敗回復；成功會改變輸出串流，不能保證外錄無中斷。
HPD、RAW↔非RAW、內錄格式、crop、frame rate 任一改變都要讓舊 target 狀態失效，
再以新 generation 建立，不讓 CDNG latch 或 kernel 配置沿用到其他輸出。

### 7.5 兩階段驗證邊界

**第一階段：保留原廠 RAW 幾何與 HDMI carrier，研究視窗／縮放控制。**
先用一個原廠 UHD 或 FHD donor，以同一解析度列切到 HDMI adapter；
保持原生 RAW buffer、格式、輸出尺寸與時序，再逐項測感測器視窗或縮放。
這樣可先驗證選單共用與套用交易，仍需實機／錄影機量測畫面、CFA、裁切、幀率與解碼。
本輪僅證明軟體介面障礙和原生設定鏈，未證明改讀出視窗後已可正常外錄。

**第二階段：改變有效 Bayer 尺寸／比例，例如真正的3:2外錄。**
必須閉合線上 packing、guard、Bayer origin、RAW buffer pitch 與 receiver metadata／解碼幾何。
`C02F5258` 對原廠14種標準模式查表，再透過 `C002BC80` 檢查接收端支援；
不支援有 fallback，未知表格組合則進 assertion。
同樣送 UHD timing，並不代表外錄機會接受不同 payload 寬高；
通道 bit 數有空間也不構成可用性證據。

`TSBMDAJA @ C00EC948` 比對 ATS/BMD/AJA，與 HDMI RAW configurator 的選擇旗標是不同狀態；
先前 [HDMI_RAW_PATH.md](../../../projects/open-gate/notes/HDMI_RAW_PATH.md) 的低階實驗
也出現設定顯示 UHD，但接收端實際仍收到 FHD。驗證時應讀實際輸出／接收結果，
不能只看選單 getter，更不應為套配方而強制 EDID 或偽造廠商碼。

**所以：共用介面可行；現有 OG3K／OG4K 配方自動變成相同尺寸的 HDMI RAW 外錄，
目前不成立。任意 Bayer 尺寸能否被商用外錄機接受仍是另一項未解問題。**

### 7.6 離線證據與重現

- 工具：[audit_hdmi_rescustom_interface.py](../audit_hdmi_rescustom_interface.py)。
- 結果：[hdmi-rescustom-interface-audit.json](../hdmi-rescustom-interface-audit.json)。
  28 個 HDMI profile，原生查表28次、display 選擇84次、RAW dispatch56次、
  canvas→Sig112次、class／raw-movie query112次，全部通過。
- 重算：`python3 -B research/interfaces/audit_hdmi_rescustom_interface.py`。
  使用 §6.3 的同一份 seg0／seg1 SHA256，結果另保存本輪所讀 consumer 來源 hash。
- 原韌體 ROM 為唯讀；模擬寫入只准 stack 與測試 Sig config。
  回傳 entry 的 configurator v3、logger、少量 settings／sensor lookup 有明示替身。
  RAM entry 身分辨識是測試替身；CDNG 位深兩個指定式依來源核對後在資料上模擬，
  **沒有執行 res-custom ARM payload，也沒有建置或安裝產品補丁**。
- 未驗證：ASIC 像素運算、其他 configurator families、商用錄影機、metadata、
  packing、自訂幾何、實機切換與 HPD／EDID fallback。這些結果不可作為上機安全或外錄成功的證明。
