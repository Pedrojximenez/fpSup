# fp 影像通道地圖 — 哪塊 buffer 能解、哪塊不能

> **2026-10-09 更正：ring 不能一律判成 tiled。** 在 CINE MONIT1、native OFF、
> 1620×911 下，授權讀取 ring 首筆 `49801000` 的 0x3FC000 bytes，按 descriptor 寬度
> 1620、每列 3240 bytes 可線性解出完整彩色場景，Y-first 4:2:2 byte 排列與 YUYV 一致。
> 用 1920 等錯誤 stride 會產生條紋；舊 probe 的 raw bytes／完整模式未在本次重驗，
> 保留為歷史觀測，不推廣到所有模式。`C375C078` 仍為 0，`C375C0B0` 則指向會輪替的 ring。
> [實檔、狀態／視窗復原](../../../projects/lut-sup/validation/20261009-native-preview-bytes-01/report.json)、
> [解碼及 stride 比較](../../../projects/lut-sup/validation/20261009-native-preview-bytes-01/analysis.json)。
> RGB 矩陣／range／transfer、Cb/Cr 的標靶校驗與 frame lease 尚未完成；不可直接寫回或報 LUT 還原率。

> 2026-08-24 從上個 session transcript 補記（8/23 那天做的，當時只到一半就被 API 中斷）。

## 一句話
目前已可讀取一份原生 CINE **全彩預覽**；依當前 descriptor 解碼，不能套用固定 1920 寬或 tiled 假設。
偵測影像 `0xC375D8C0` 是另一個灰階通道，不等於全彩 LUT 的像素來源。

---

## 通道 1：偵測影像（Detection Image）★ 已實機驗證
韌體人臉/物體偵測**真正吃的那張圖**。使用者的洞見帶出來的：「韌體做 AF/人臉一定要有一張可用的影像」——對。

| 項目 | 值 |
|---|---|
| descriptor | **`0xC375D8C0`**（singleton `0xC375D840` + 0x18 起、stride 0x34、找 `+0x30 & 0x20`） |
| buffer addr | `*(0xC375D8C0)` = 例 `0x4483C340`（每幀活的） |
| 格式 | **8-bit 線性灰階**，W=320（desc+0x14）、H=180（desc+0x18） |
| buffer size | `desc+0x24` = **76800** = 320×240（active 只到 **180 行**，180 之後是 padding/雜訊） |
| 推送 | `push_detect.S`（= push_green 改讀 `*(0xC375D8C0)`）注入 @`0xC072F600`，`BATCHPUSH 76800 1` |
| 實測 | 76800 bytes / **0.97ms**、75.7 MB/s、err=SUCCESS。解成 320×240 灰階 → **看得出實景**（已 Read PNG 確認） |

**RE 鏈**：`FUN_c03e06a0` @`0xC03E06A0`（debug 字串 `"face > w %u h %u x %u y %u addr %"`，`blk_c03.c:157572`）
→ `FUN_c0436590()` 取 singleton `0xC375D840` → `FUN_c0436f28(sing, 0x20)` @`0xC0436F28`（`blk_c04.c:37276`，掃 +0x18..+0xE8 stride 0x34 找 `+0x30 & mask`）。

**為什麼是這張**：小、線性、灰階 = 偵測演算法要的（省算力、對比結構清楚），所以韌體不吃 tiled 顯示圖也不吃全解析 Bayer。

---

## 通道 2：顯示 scanout ring — **TILED，別解** ❌

> **2026-10-15 更正：** 下列 `C070B330 / C070B3E8` 已追到 MOV codec 設定鏈，不能把它們的幾何／stride 暫存器當作顯示 scanout 一定 tiled 的證據。此節保留歷史調查；實際可線性解碼的 ring 仍以頁首 2026-10-09 實檔證據為準。[codec 分析](FP_H264_10BIT_FEASIBILITY_2026-10-15.md)

- latch `0xC375BF88` → ring `0x49801000 / 0x49BFD000 / 0x49FF9000 / 0x4A3F5000`（4 × `0x3FC000` = 1920×**1088**×2）
- 被顯示 DMA（MMIO **`0x300C0000`**，`FUN_c070b330`/`FUN_c070b3e8`，`blk_c07.c:9419-9495`）以 **16px tile** 定址：
  - width reg `_DAT_300c026c = ((W+0xf)>>4 & 0x1ff)<<2`；height reg `_DAT_300c0250 = (H-1)&0xff`
  - ⇒ **120×68 個 16px tile** = 1920×1088 → **這就是 1080 被墊成 1088 的原因**（68×16）
  - mode selector `DAT_c2f30040`(0..0xb) 切 linear/tiled stride
- 寫入端 `FUN_c0148988` @`0xC0148988`（MMIO `0x3011A8xx`）是雙平面 per-plane stride 引擎，符合 block/tiled writer。
- **實測**：YUYV / UYVY / planar / RGB565 / 16-bit / 自相關掃 stride(1000–4200) —— 全部給出**一模一樣的橫條結構**。tiling 會平等地打爛所有線性 stride，所以「分數都一樣」本身就是 tiled 的證據。
- 若真要用（fallback）：`(68,120,16,16,2)` reshape，對著已知亮邊 brute-force 軸序做 detile 標定。**沒必要，用通道 3。**

## 通道 3：線性 develop YUV — **候選最佳全解析源**（機制 [C]，實機值 [P]）
韌體自己每幀重建的**線性 packed 4:2:2 副本**（跟 scanout 同一幀，但沒 tile）。

| what | EA |
|---|---|
| descriptor | `0xC375C05C`（`FUN_c0429470` @`0xC0429470`，`blk_c04.c:27353` 每幀重建） |
| **linear YUV base** | **`*(0xC375C078)`**（desc+0x1c），`blk_c04.c:27384`，值 = `handle*4+0x40000000`（`FUN_c0022fb8`）→ 可直接 DMA 的 `0x4xxxxxxx` |
| W / H | `*(0xC375C06C)` / `*(0xC375C070)` → 期望 **1920 / 1080**（是 1080 不是 1088） |
| fmt | `*(0xC375C080)` |

- 格式 **packed YUYV 4:2:2、Y-first**（`[Y0,U,Y1,V]`，U/V≈0x80），由 `CNRO` @`0xC015C230`（`blk_c01.c:50656`）TYPE=1(YUV) ⇒ size = W·H·2 確認。
- **證明是線性**：韌體自己的 debug dumper `FUN_c05b3728`（`blk_c05.c:136972`）做 `memcpy(dst, *(desc+0x1c), W*H*2)` 存成 `"%08d.yuv"`，scratch 配 `0x3F4800 = 1920·1080·2`。W·H·2 直 memcpy 存 .yuv 只有線性 raster 才說得通。
- ⚠️ **實機第一次 peek 是 0**（`base=0 W=0 H=0`）—— 該 descriptor **只在特定顯示/錄影態才 per-frame 重建**，LiveView 閒置時是空的。要用得先確認它活著。

## 訂正舊筆記
- `BAYER_FORMAT_MAP.md` 說 `0xC375BF88`→`0x49xxxxxx` 是「YUV develop output」：**內容對，但那是 tiled scanout 表示**；線性版在另一個 descriptor `0xC375C05C`。
- `RAW_PUSH.md` 說 UVC ring（`UvcImgBf` @`0xC04D8538`）是 YUY2：**錯，是 MJPEG 壓縮的**（`XC_StillCreateUVC` JPEG-encode 同一張 develop 幀，`blk_c03.c:84891`）。不能當線性替代源。
- 沒有獨立的線性 HDMI/LCD scanout DRAM buffer；scanout 由 SIGSEQ/BUFEF/ROTATE 引擎（`0x30200000`/`0x301Bxxxx`）即時生成。

---

## 通用推送常式 push_ptr.S（已建、已注入，未跑完就被中斷）
一個 routine 推任何通道，切通道只改 STATE 欄位：
```
STATE+0x70 = N（幀數）
STATE+0x74 = fallback addr
STATE+0x78 = framesize
STATE+0x7C = 指標 cell 位址   ← 切通道只改這個
```
每幀讀 `buf = *(*(STATE+0x7C))` → 驗證 `0x40000000..0x60000000` → 零拷貝 arm ctx4 指向它 → StartTransfer(9) + wait(4)。
- detect 通道：`+0x7C = 0xC375D8C0`, `+0x78 = 76800`
- develop 通道：`+0x7C = 0xC375C078`, `+0x78 = W*H*2`
- green 通道：`+0x7C = 0xC3404768`
38 words，注入 @`0xC072F600` 已驗證（首字 `0xe92d43f0`）。

## ⚠️ 操作教訓
**連續 BATCHPUSH（dfd_image.py 的 poller）會把 EP84 弄 stall** —— 跟 RAWGRAB hammering 同病，需拔插 USB 線。
真 live 串流必須**worker 自驅動 push loop**（一次 call 推 N 幀），不能每幀下一個命令。

## AF 綠通道 ≠ 影像（回答使用者的問題）
AF 綠 band 是 SIG AF 統計引擎（`0x30050000`）輸出的 **256 個 int32 = 逐掃描線高頻能量**：抽 Bayer 綠 CFA → 高通 → 每線加總。
是**對比式對焦的 1D 銳度曲線**，不是像素，畫不成場景圖。跟偵測影像（320×180 實景灰階）是完全不同層次的東西。
