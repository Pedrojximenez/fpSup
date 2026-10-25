# SIGMA fp H.264 10bit 硬體能力分析

> **2026-10-24 續查：** 已用原廠 ARM 指令完成 314 個離線情境。profile 選擇值 3 會由原廠低 QP 邏輯自動選到；264 組 SDK 描述子的兩個候選輸入格式欄位仍固定為 2／0。模式 8–11 的 ARM 初始化路徑也會複製正常的 192 KiB 控制映像，但尚未執行控制 ISA 或取得 HEVC 碼流。另盤點 8 個 ISP packer 呼叫點。**仍未找到已驗證的 10-bit 路徑，也未證明硬體只能 8-bit。** 詳見 [本輪證據與重跑工具](../h264-10bit-audit-20261024/README.md)。

fp Ver.5.02 的 MOV 編碼鏈確實控制 `0x300Cxxxx` 的硬體 codec，並載入控制程式。**CinemaDNG 管線已有 12-bit Bayer 來源，上游高位深來源不是缺口。** 現有兩份 fp MOV 都是 H.264 High、4:2:0、8-bit；尚待確認的是 RAW 經色彩處理後能否以高位深格式交給 codec，以及 codec 能否編碼 H.264 10-bit。現有證據不足以判定晶片在物理上只能處理 8-bit。

底層另有高度符合 HEVC 的分支，值得繼續解析；這項發現不等於支援 HEVC Main10，更不能推導 H.264 High 10 可用。

## 分析範圍與證據

2026-10-15。離線讀取原廠映像、既有反編譯與已保存的 MOV，並以 ROM 指令核對關鍵暫存器操作。沒有相機 I/O、RAM 注入或寫卡。

| 項目 | 身分 |
|---|---|
| 主映像 | `out/seg0_c0000000.bin`，49,245,696 bytes |
| SHA-256 | `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622` |
| 可重跑分析 | [audit.py](../h264-10bit-audit-20261015/audit.py) |
| 函式位址、行號、MOV SPS、雜湊 | [report.json](../h264-10bit-audit-20261015/report.json) |
| 相關反編譯節錄 | [evidence.c](../h264-10bit-audit-20261015/evidence.c) |
| 關鍵 ROM 指令 | [disassembly.txt](../h264-10bit-audit-20261015/disassembly.txt) |

重跑：`python3 -B research/imaging-hw/h264-10bit-audit-20261015/audit.py`。工具要求映像雜湊吻合，並將自行解析的 SPS 位深與 ffprobe 比對。

## 編碼器位置與初始化

韌體平台代號是 **XZ01 / w71c1**。已定位的是由主 CPU 控制的 codec 暫存器介面；沒有從這份映像取得可唯一對應商用料號的硬體 ID，也沒有證據需要把編碼器視為另一顆外接晶片。既有筆記的「Socionext Milbeaut 系」標示，不足以替代特定 codec IP 的規格書。

MOV 啟動從 `movRec @ C038A3E8` 進入 `C06B07A0 → C06B0AE0`，後者建立 SDK 的錄影參數與 callback，經 `C070E208 → C070F6D0` 配置錄影狀態。錄影工作路徑的 `C07101C0` 再呼叫 `C07254E0`，建立 0x104-byte 底層描述子，最後經 `C0708978 → C0709E50` 寫 codec 暫存器。

`C070A870` 把 `C2EB4390` 起的 **0x30000 bytes（192 KiB）**複製到 codec 工作區；`C070A8B0` 將該區位址寫入 `300C0100 / 300C0104`。另有 `C070A890` 複製 `C2EE4390` 起的 0x10000 bytes。這是 codec 控制程式的入口，指令集與各 bank 語意仍未解出。

| 控制程式 | 長度 | SHA-256 |
|---|---:|---|
| `C2EB4390` | 196,608 | `1ba39bfb19a952f982e9ff82f5f67377705611f538aba015621c68c3c7695c98` |

控制程式可由韌體搬入，代表有可研究的程式層；不表示像素運算單元、記憶體介面或熵編碼單元可由軟體擴充位寬。

## 原廠 MOV 已確認的輸出

兩份既有檔案為 `projects/rawview/captures/2026-09-24-movcheck/A001_037.MOV` 與 `A001_040.MOV`。兩者的 SPS 完全相同，自行解析與 FFmpeg `trace_headers`／ffprobe 結果一致。

| SPS 欄位 | 值 | 意義 |
|---|---:|---|
| `profile_idc` | 100 | High |
| `level_idc` | 51 | Level 5.1 |
| `chroma_format_idc` | 1 | 4:2:0 |
| `bit_depth_luma_minus8` | 0 | Y 為 8-bit |
| `bit_depth_chroma_minus8` | 0 | Cb/Cr 為 8-bit |

影片為 1920×1080、30000/1001 fps。這證明這兩次錄影使用的模式，不代表已列舉晶片全部能力。

## H.264 10bit 候選欄位

| 入口 | 已確認行為 | 尚未成立的解讀 |
|---|---|---|
| `C070C578` → `300C020C[1:0]` | 接受 0、1、2、3；原廠轉換 `C0725B30` 只產生 0、1、2 | 選擇值 3 尚未對應到 SPS profile，不能直接命名 High 10 |
| `C070CAF0` | 在來源欄位為 2、量化上下限變數小於 6，且相關格率條件成立時，可自行改用選擇值 3 | 值 3 不是單憑存在就能當成未開放的 10-bit 選項 |
| `C070AB40` → `300C02C0[4:3]` | 格式列舉 0、1、2 分別清空、設 0x8、設 0x10；`C07254E0` 的對應欄位固定為 2 | 未建立列舉與每像素位深／packing 的對應 |
| `C070D638` → `300C0238[2:0]` | 輸入 0、1、2 對應低位 0、5、3 | 語意未解，不可據此寫入「10-bit」 |
| `C07254E0` | 建立描述子並固定多個欄位；已追的上層 MOV 參數沒有已確認的 8/10-bit 切換 | 尚無可傳遞到 codec 的 10-bit YUV buffer 契約 |

`300C020C` 的低兩位是**內部列舉**，不是直接寫 H.264 `profile_idc`；把 110 寫入這個兩位欄位不會變成 High 10。即使解出 High 10 profile，仍須同時證明輸入 packing、重建／參考幀精度、變換／量化範圍與熵編碼能處理 10-bit。

## CinemaDNG 的 12bit 來源

CinemaDNG 管線的全幀 Bayer buffer 已具備 12-bit 資料，應直接把它作為候選來源，不必先寫成 DNG 檔再讀回。既有 FHD 12-bit 實機紀錄已定位 RAW buffer 與 writer 交接，見 [CinemaDNG RAW 寫入路徑](../native-calibration-20260924/cinemadng-raw-sink-audit.md)。`FrameExpos_s @ C0315C10` 所使用的 RAW descriptor 與位深列舉另見 [Bayer 格式圖](BAYER_FORMAT_MAP.md)；實際接線仍需沿用當前幀的尺寸、packing 與緩衝區所有權。

一般彩色 10-bit H.264 的候選資料流是：

`CinemaDNG 12-bit Bayer buffer → ISP 去馬賽克與色彩處理 → 10-bit YUV → 硬體 codec`

12-bit Bayer 來源已成立；中間高位深輸出與 codec 位深能力仍待確認。優先追 ISP 在哪個輸出階段量化／打包成 8-bit，以及是否可在該處保留高精度、轉成 codec 能讀取的 10-bit YUV。這不必預設整套去馬賽克與色彩處理由 CPU 重做。

目前已驗證的彩色預覽是 8-bit YUYV，見 [影像通道紀錄](IMAGE_CHANNELS.md)。這只描述該預覽輸出，不能用來否定 CinemaDNG 的 12-bit 來源或其他 ISP 輸出能力。

### 2026-10-15：ISP 打包與 MOV buffer 交接續查

已定位具名 `YUV_PACK`（MMIO `3011E004`、shadow `3021236C`、setter `C01570D0`）與 `PST_TOP DITHER`（MMIO `30116580`、shadow `3021100C`、setter `C010C9D0`）。位置由診斷名稱與傳輸描述子交叉核對，尚未證明 DITHER 是唯一的 8-bit 量化點。

沿 profile → engine config → frame descriptor 追到的 `+0x101` 列舉會連帶改變半高計算與打包，較符合色度取樣／儲存方式；不能命名為 8／10／12-bit。控制該特殊分支的 canvas `+0x94`，在重新核對的 **306 列原廠 profile 全部為 0**，沒有找到可直接借用的高位深 YUV profile。這不排除其他路徑或執行期設定。

另已追到 `C0429910 → C0428690 → C01D69D0` 的輸出 ring 設定，以及 `C0429470 → C01D7638` 的完成端描述子；其中部分格式 flags 實為路由旗標。尚未建立 10-bit buffer 契約。詳見 [本輪資料流與證據](../h264-10bit-audit-20261015/RAW_TO_CODEC.md)，可用 [trace_raw_to_codec.py](../h264-10bit-audit-20261015/trace_raw_to_codec.py) 重跑 35 支函式與 19,890 個 ROM words 的核對。

## HEVC 候選路徑

`C0709A80` 在底層模式 **8–11** 設定 `300C03F8.bit0`。之後 `C070B7A0` 會切到不同的 level／幾何設定，包含 `C070C930` 與 `C070CAB0`。

`C070C930` 的像素上限依序為 **36,864、122,880、245,760、552,960、983,040、2,228,224、8,912,896**；還有 66,846,720、267,386,880、534,773,760 等每秒樣本上限。這些數字與 [FFmpeg 的 HEVC level 表](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/h265_profile_level.c)逐項吻合；幾何配置亦切換到以 32 行對齊的路徑。因此可把它列為**強靜態證據支持的 HEVC 驅動分支**。

現有正常 MOV 的模式選擇器 `C070D858` 只回傳 **0 或 5**，沒有選擇 8–11。封裝端 `C071F3E8 / C071FCD8` 寫入的是 `avc1 / avcC`；映像中未找到 `hvc1 / hev1 / hvcC`。即使 HEVC 硬體分支可用，也需要另行處理碼流辨識與封裝。

這個分支尚未驗證實際晶片的完成訊號、輸出 NAL 或 SPS/VPS；也可能是共用 SDK 留下的能力。**有 HEVC 程式分支不表示 Main10 可用，HEVC Main10 可用也不表示 H.264 High 10 可用。**

## 可行性判定與後續驗證

| 問題 | 本輪判定 |
|---|---|
| fp 是否真的有硬體影片 codec | 是，已追到 MOV 初始化、MMIO 與碼流標頭取出 |
| 是否已有高位深影像來源 | 是，CinemaDNG 管線已有 12-bit Bayer buffer |
| 是否已有高位深 RAW 到 codec 的完整交接 | 否，ISP 高精度 YUV 輸出、格式與 codec 能力仍待確認 |
| 是否只是把 8-bit 硬編碼的選單鎖住 | 尚無證據 |
| 是否已找到 H.264 10-bit 開關 | 否 |
| 是否能斷言晶片永遠不能 H.264 10-bit | 否，codec 控制程式與部分格式欄位尚未解出 |
| 是否值得繼續解析 | 是，具體入口為 profile 列舉、輸入格式欄位與 codec 控制程式 |

沿 CinemaDNG 的 12-bit Bayer 來源追 ISP 輸出，定位降為 8-bit 的階段及高位深格式選項。同時解出 `C070C578` 選擇值 3 對應的 SPS 語法，以及 `300C02C0 / 300C0238` 是否包含高位深格式。接著追 codec 控制程式如何產生 `profile_idc`、`chroma_format_idc`、`bit_depth_luma_minus8` 與 `bit_depth_chroma_minus8`，並核對參考幀儲存配置。這比先修改 MOV 選單或檔案標頭更能判斷硬體能力。

實機驗證若進入下一階段，應使用已知 packing 的合成 10-bit 影像與獨立輸出緩衝，先做單幀。合格證據需要原生 SPS 宣告 10-bit、標準解碼器能完整解碼，並用受控的成對輸入確認超過 8-bit 的來源差異確實通過管線。只改 SPS、只看到解碼後低兩位非零，或只收到成功回傳，都不足以證明真 10-bit。

## 舊研究結論的修正

[RAW_COMPRESSION_RESEARCH.md](RAW_COMPRESSION_RESEARCH.md) 與 [HW_LOSSLESS_JPEG_CODEC.md](HW_LOSSLESS_JPEG_CODEC.md) 曾把 `0x300C` 整塊視為不壓縮的 RAW 讀出前端，並寫下全韌體沒有 H.264／HEVC 的結論。MOV 呼叫鏈、碼流標頭取出及 codec level 設定已推翻這個全域否定。這項更正不代表影片 codec 可直接處理 Bayer，也不改變 `0x300D` 無損 JPEG 的獨立研究結果。
