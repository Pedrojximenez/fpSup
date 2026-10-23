# SIGMA fp Ver 5.02 — 相機端 RAW 壓縮開發研究

> **2026-10-15 更正：** 本文「全韌體沒有 H.264／HEVC」及把整個 `0x300C` 視為無壓縮 RAW 前端的判讀已撤回。已由 MOV 初始化鏈追到 `0x300Cxxxx` 硬體 codec，另有 HEVC 候選分支；10-bit 能力仍未證實。見 [H.264 10bit 分析](FP_H264_10BIT_FEASIBILITY_2026-10-15.md)。這不表示影片 codec 可直接壓縮 Bayer。

> 目標:讓 fp 在相機端把 raw(Bayer)幀無損壓縮,用於 (A) USB 即時串流降頻寬 / (B) 未來 SD 卡錄製 UHD 壓縮 RAW,PC 端還原。
> 本文彙整 2026-08-20 的完整逆向與可行性研究。EA 為 ARM 位址(base 0xC0000000),file-offset = EA − 0xC0000000。
> 信心標記:**[C]** 反編確認 · **[I]** 推論 · **[P]** 需上機實測。
> 姊妹文件:壓縮引擎 ABI 細節見 `HW_LOSSLESS_JPEG_CODEC.md`;傳輸 recipe 見 `RAW_PUSH.md`;DNG 結構見 `RECORDER_SPEC.md`。

---

## 0. 一句話結論
硬體無損壓縮**確定可行、可被注入碼獨立呼叫、idle 時安全、且沒有更好的引擎躲著**。壓縮比實測 **~2:1**(足以降頻寬 / 錄兩倍長)。**唯一未定的變數是壓縮引擎的真實吞吐(32–300 Mpix/s),只有上機 IRQ-0x29 計時探針能定。** USB 即時 raw 串流**不需要壓縮器**就能到 ~24–30fps;壓縮是「衝更高 fps / 塞 SD / 錄更久」的加成。

---

## 1. fp 的原生壓縮現況(實測真實檔案)
| 內容 | 位元 | 壓縮 | 說明 |
|---|---|---|---|
| **CinemaDNG 影片**(FHD & UHD) | 12-bit | **未壓縮**(Compression=1) | 每幀單一 IFD、無內嵌預覽;相機錄影**從不壓** |
| **靜態拍照 DNG** | 14-bit | **無損 JPEG**(Compression=7,256×256 tiled) | 相機**只有拍照**才叫無損引擎 |

- 驗證檔:`/Users/dido/Movies/A001_001/*.DNG`(FHD 1936×1090 12-bit Comp=1,裁 1920×1080);`_SDI0011.DNG`(SubIFD 6064×4042 14-bit tiled,WhiteLevel 16383)。
- **fp 錄 UHD RAW 強制外接 SSD** 的原因:UHD 12-bit 未壓縮 = 12.44 MB/幀 → 29.97fps = **373 MB/s**,超過 SD 持續寫入。
- slimRAW 這類軟體能對 fp CinemaDNG 省很多,正是因為**相機錄影根本沒壓**,~2:1 的熵編碼空間全在。

---

## 2. 全機壓縮硬體盤點(對抗式全掃 0x30xxxxxx,35 個 MMIO 區塊)[C]
**只有兩顆壓縮引擎,沒有漏掉任何 raw packer/compander:**

| 引擎 | MMIO | 類型 | 輸入 | 用途 |
|---|---|---|---|---|
| **XC_HalLjpeg** | **0x300D0000**, IRQ 0x29 | **無損 JPEG**(predictor+Huffman) | **Bayer/CFA raw**,10/12/14/16-bit | 拍照 DNG(Compression=7)。**這是唯一能壓 raw 的** |
| XC_SigproJpegComp | 0x301B0000 | 有損 baseline DCT(SOF0,Q85/90/95) | YCbCr 彩色,非 CFA | 拍照/預覽 JPEG,焊死在 ISP |

- **2026-10-15 撤回：** 不能把 `0x300C` 整塊判作無資料縮減的 RAW 前端；`C070B7A0` 位於 MOV codec 設定鏈，包含影片編碼的碼率、GOP、level 等設定。
- 舊掃描未找到可直接套用於 Bayer 的其他壓縮路徑；它不能支持「全域沒有 H.264／HEVC」。H.264 硬體路徑與 HEVC 候選分支見上方更正。
- 有一個 **CPU-only 軟體 codec 庫**(`XcImageEncoderInterface`:NoCompress / Lz4 / SRLE,blk_c05 ~c05a71a8+),但**零 MMIO、不在 Bayer 路徑、非 video-rate**,僅通用 buffer/QR 用。

---

## 3. 無損引擎 0x300D — ABI 與獨立呼叫 [C]
### 呼叫序列(注入碼可 replay)
```
RAWCD()               @c062f440  -- 懶建 event flag DAT_c2f2e60c(encode 內自動)
FUN_c05a6890(&init)   @c05a6890  -- init:鎖 src/dst/幾何(→FUN_c062f5a8)
FUN_c05a6920(&enc)    @c05a6920  -- encode,阻塞到完成(→FUN_c062f6f8)
FUN_c05a6990(out,1)   @c05a6990  -- 讀回壓縮大小(→FUN_c062fa48)
```
- 解碼對應:`FUN_c05a69e0`(round-trip 驗證用)。真實 call site:blk_c03.c:85629。
- **initStruct**(9 words + 1 byte):[0]寬 [1]高 [2]bitdepth code(0→12,1→14,2→16,3→10)[3]tileW(0x100)[4]tileH(0x100)[5]**SRC DRAM ptr** [6]work base [7]**DST+size-table base** [8]mode byte(0=全幀)。
- **encStruct**(5 words):[0]寬 [1]高 [2]bitdepthCode [3]tileW [4]tileH(buffer 來自 init 鎖的全域)。
- 壓縮位元組數:暫存器 `0x300D00F8` 讀回;bitstream DMA 到 dst;EOI 修補 FUN_c062f6c0。
- **無損硬寫死,無品質旋鈕** → 這就是 Compression=7 引擎,bit-exact。

### 冷啟動獨立可叫 — 無隱藏 blocker [C]
- encode 內自帶所有前置:event flag 懶建、電源域 5 + 時脈 + IRQ 0x29 在 `FUN_c062fee8` 拉起、mode byte `_DAT_c37cf87c` 由 programmer 設。
- **不依賴 live capture / RFC active / 事先校正** → 餵合成 buffer 就能跑。
- **電源域 5 是 refcounted**(FUN_c070dc18)→ 壓完關電**不會誤關感測器**(比原本擔心的安全)。
- guard 全是呼叫端可控:寬 8..0x4000 且 ×8、高 2..0x4000 偶數、tileW 0x20..0x200 ×32、buffer **1KB 對齊**。

### 硬體約束
- **1KB 對齊**(位址以 (virt+0xC0000000)>>10 寫入)。
- 幾何上下限如上;src/dst 需在 DMA 可見 DRAM,cache 一致性自理(FUN_c062f510 map + cache-clean FUN_c000e91c)。

### ⚠️ 唯一風險:單引擎、無 mutex → **只在 idle(沒在拍照)時叫**,否則踩到拍照壓縮會卡死 IRQ 0x29,需重開。

---

## 4. 吞吐量 — 唯一未定的變數 [C floor / I ceiling / P true]
- **32 Mpix/s 是 watchdog timeout,不是吞吐。** `FUN_c062f6f8`:`timeout = tile對齊像素 / 32000`(min 100 ticks),只證明真實吞吐 **≥ 32**。(早期把它當定值是踩了「self-consistent wrong values」陷阱,已修正。)
- **時脈 ≈ 300 MHz 的舊推論依據已失效（2026-10-15）**：`C070BE68` 的 300000000 是影片 codec 的處理預算常數，不能當成 `0x300D` 時脈的量測；本段以 300 MHz 推算的上限仍是假設。
- **~1 sample/clock,與位元深度無關**(10-bit 不比 14-bit 快;bitdepth 只改 stride 暫存器)[I]。
- **DMA 不是瓶頸**:+0x78/+0x7c/+0x84 是 src/2nd/3rd DRAM 位址(非 burst 設定);無 burst-length 暫存器;輸入讀取 450–600 MB/s < DDR。**瓶頸是 VLC(變長碼)samples/clock,不是 DMA、不是電源切換。**
- **每幀只 1 次 power cycle**(UHD/FHD/全幅都是單 stripe,64MiB band budget)→ 對連續使用友善。
- **韌體無任何 perf counter / 計時器** → 真實 sustained Mpix/s **只能上機實測**。

| 若引擎真實是… | 無損最高 UHD fps | 壓縮 UHD RAW 上 SD? |
|---|---|---|
| 300(天花板,1px/clk) | ~36 | ✅ 30fps 有餘裕 |
| ~250 | ~30 | ✅ 剛好 |
| ~150 | ~18 | ⚠️ 24/30 不到 |
| 32(舊誤解) | ~4 | ❌ |

- 能把它拉到 UHD30 以下的唯一因素:**高熵 tile 上 VLC sub-1-px/clk**(靜態看不到)。
- **不能安全超頻**:時脈與 sensor readout 綁一起,無獨立分頻器。**單引擎,不能並行。**

---

## 5. 壓縮比 — 實測 [C]
拿真實 CinemaDNG 幀算「同色左鄰預測殘差熵」(即引擎 predictor+Huffman 能達到的):
- 殘差熵 **5.19 bits/px** → **無損比 2.31:1**(vs 12-bit 打包),與 slimRAW 量到的 ~2.18:1 一致。
- **隨畫面浮動**:暗/乾淨 ~2.3:1、一般曝光 ~2:1、亮/高 ISO/細節多/高雜訊 ~1.5–1.9:1。
- 換算 UHD30 位元率:未壓 373 → 壓後 **161–233 MB/s**(視畫面)。

---

## 6. 傳輸 — 不是瓶頸(慢的是舊做法)[C]
- **鏈路 = USB3 SuperSpeed**(bcdUSB 0x0320);vendor bulk IN 是真 SS pipe(burst 3)。
- **你日常 UHD 12-bit 29.97 錄 SSD = 373 MB/s,量產級穩定** → USB 路徑實測 **≥373 MB/s**。
- 49p LiveView 是 **UVC isochronous**(EP 0x84,YUY2 1080p,6 格環形,203 MB/s);PTP LiveView 是 pull-only 有損 JPEG,**不是** 49p 載體、別模仿。
- **舊 RAWGRAB 慢的根因(方法錯,非頻寬)**:單 TRB / host-pull 每幀一命令 / 每次 clear_halt+drain+usleep120ms / 未 gate re-arm → device-side DEPCMD stall + DALEPENA desync + DWC3 IRQ-0x34 livelock。
- **正確 recipe**(取代 RAWGRAB):源頭 hook 快照 → N 層環形(滿就丟幀,絕不擋擷取)→ 專屬消費者任務**持續 armed**,從 0x50000000 **零拷貝** DMA 進 ctx4 TRB(≤16MB,UHD 一幀 12.4MB 進得去一個 TRB)→ StartXfer `FUN_c01e6b80(9)` → IRQ 喚醒 re-arm(flag `0xC31E3210`)→ **不 clear_halt、不 drain、frame-to-frame 保持 armed**。
- **結果**:未壓縮 UHD ~24fps、壓 2:1 ~50fps;逼近 PHY ~400 天花板可到 UHD30 未壓縮。

---

## 7. 錄製時間(UHD 12-bit 29.97,~93% 可用率)
| 容量 | 未壓縮 | 壓縮 ~2:1 | 範圍(1.6:1~2.3:1) |
|---|---|---|---|
| 128GB | 5 分 | 11 分 | 9–12 分 |
| 256GB | 11 分 | 21 分 | 17–25 分 |
| 512GB | 21 分 | 43 分 | 34–49 分 |
| 1TB | 43 分 | 85 分 | 68–98 分 |
| 2TB | 85 分 | 170 分 | 136–197 分 |
- **無損 ~2:1 = 同卡錄兩倍長 / 同長度半空間**。CinemaDNG 每幀一檔,無單檔 4GB 限制。

---

## 8. SD 卡錄製那道 gate(若走 SD 壓縮 RAW)[C]
- gate = **`FUN_c04a19b0` @0xC04A19B0**,純軟體三 enum 比較:`格式==DNG && 尺寸==UHD && (無 USB-SSD || 目的地≠外接) → 擋`。**無速度/碼率/DMA 判斷。**
- **無韌體 SD 上限數字**:只讀 UHS 等級 → 布林「是不是 UHS-II」→ 調寫入分塊節奏。上限 = 卡實體能撐多少。
- **可放寬**:patch `FUN_c04a19b0`→1 + 繞過 clamp `@0xC00A7EE0` + `FUN_c04a1120`。錄影路徑不再檢查目的地。
- 寫不贏 = **乾淨 StopOverflow 停錄**(96 格 FIFO,不損檔不掉幀,反應式)。
- **沒有 latent 壓縮影片路徑** —— movie 壓縮**得我們自己造**(DNG 寫檔器現成:compress flag byte at (image-desc)+4,由 `FUN_c06a3730` 設,唯一 caller `XC_StillCreateFile__v4 @c037e0f8`,拍照專用;只要把 movie 幀接上這條 + 設 flag)。

---

## 9. 三種產品形態的可行性總表
| 形態 | 需壓縮器? | 現況 |
|---|---|---|
| **USB 即時 raw 串流 ~24fps** | ❌ 不需要 | ✅ **最穩**,只要把傳輸做對(recipe 有了) |
| **USB 即時壓縮 raw ~50fps** | ✅ | 取決於引擎吞吐(探針) |
| **SD 錄 UHD 壓縮 RAW @30fps** | ✅ 必須 | 取決於引擎吞吐;gate 可 patch、寫檔器現成、壓縮比夠 |
| SD 錄 UHD 無損 RAW 低 fps(~10-12) | ❌ | ✅ 只需 patch gate + 快卡(未壓縮匹配 SD 頻寬) |

---

## 10. 唯一的下一步:上機探針(idle,低風險)
量 0x300D 真實吞吐,settle 整個「壓縮 fps」問題:
1. idle 時,poke 一個已知大小、1KB 對齊 buffer 當 src。
2. 呼叫 `FUN_c05a6890`(init)→ `FUN_c05a6920`(encode)。
3. **計時 IRQ-0x29 完成 / 輪詢 `0x300D0000`/`0x3FC` done-bit**,對照像素數;換 2–3 個尺寸分離固定開銷與每像素速率 → sustained Mpix/s。
4. 用 `FUN_c05a69e0` 解回比對 bit-exact。
- 安全性:引擎非拍照時 idle、電源域 refcounted、buffer 小、單發。最壞情況 = 卡死→拔電池重開,**不燒不磚**(不碰 NAND/flash)。

## 附:信心帳
- **[C]**:只有兩顆引擎;0x300D 冷啟動可叫 + refcount 安全;32Mpix/s 是 timeout;DMA 非瓶頸;每幀單 stripe;無 latent 壓縮影片路徑;壓縮比 ~2.3:1;傳輸 ≥373MB/s;RAWGRAB 卡機根因;SD gate 軟可 patch。
- **[I]**:300MHz、~1px/clk、~300Mpix/s 天花板。
- **[P]**:真實 sustained Mpix/s(32–300);0x50000000 零拷貝 bus alias;連續 push 的實際 MB/s 與 re-arm 延遲。
