# UI 繪製管線的 CPU 成本(2026-10-16，離線)

問題：使用者覺得 fp「做什麼都卡卡的」。這份筆記拆解選單/OSD 從「要重繪」到「上螢幕」每一段花在哪裡。
只讀 `out/seg0_c0000000.bin` 與 `out/decomp/full/`，沒有相機 I/O。
**[靜]** = 反組譯直接看到；**[模]** = unicorn 實際執行量到；**[推]** = 推論。

## 1. 管線總覽

```
CYC_DRAW 循環處理器(16 ms)  C05276F0
  每 3 次(48 ms ≈ 20.8 Hz):
    ├ FUN_c0527e28 → DrawThread 旗標 0x2 → 各 drawer 的 tick(+0x18)
    └ 4 個 slot 全部標 dirty(C05277A0..C0527814,沒條件)→ 旗標 0x4
DrawThread(DrawMgr,pri 17) DrawThread__v1 C0528F28
  └ 繪製一輪 C0528700:
      每個 dirty slot:可選的整層清除 C0528B40 → 每個 drawer 的 draw(+0xC)
      有任何 drawer 回報「畫了」→ C000E91C 整個 L1+L2 clean+inv(關中斷)
      slot 2/3:commit(+0x14)+(drawer +0x1C 為真時)整層 memcpy C0528BA0
UIC drawer = UicDrawHandler::v1 C06D1948 → FUN_c0561198(uicMgr=0xC37B7034)
  ├ Update:收集 dirty rect,和前幾個緩衝的 rect 取聯集(三重緩衝)  C05614E0
  ├ Render:只畫聯集 rect(rect 空就不畫)  C05615E0 → 渲染器 +0x1C
  └ 後處理：rect 內逐像素 ARGB4444 查表(預乘 alpha,表 0xC0D0D684)  C0563BA8
```

- **節奏是 48 ms 一輪 [靜]。** 除數在 RAM：`[0xC3782FA4]`(重繪請求)、`[0xC3782FA0]`(dirty 輪詢)，開機各設 3，只設一次。
  所以按鍵到畫面最快也要等下一個 48 ms 邊界，再加渲染時間，再加三重緩衝。
- **UIC 有做 dirty rect [靜]**：沒變的畫面不會整頁重畫。整頁重畫只發生在 mode 2(`param_5+8` 整層 rect)，例如換頁。
- **UIC 的 drawer 不做整層 memcpy [靜]**：它的 +0x1C 是 `C05757F8`，回傳 0。整層 memcpy 只發生在其他 drawer。

## 2. 沒有 2D 硬體引擎在幫 UI [靜/推]

- 圖層合成(LCD/HDMI 4 層 + alpha)是顯示控制器做的 [靜，見 DISPLAY_OSD_MAP]。
- **但「把圖畫進圖層」全是 CPU**：一套通用的軟體 2D 引擎(Thumb，`C06D….C0700000`)，包含掃描線多邊形光柵化(`C06D5B00`)，
  以及每種像素格式一份 span 函式(`C06E4xxx`、`C06E9xxx`、`C06EExxx`、`C06F4xxx`、`C06F99xx`、`C06FFxxx`)。
- **所有 span 都走仿射取樣**：每個像素算 16.16 座標、clamp、`mla` 算位址。等倍、不旋轉的貼圖也走同一條路，沒有 memcpy 快速路徑。
- 沒有找到任何 blitter 或 DMA 暫存器出現在 UI 路徑上。這是「沒找到」，不是「證明不存在」。

### 每像素指令數 [靜，從迴圈本體數的]

| span | 用途 | 指令/像素 | 記憶體操作/像素 |
|---|---|---|---|
| `C06E9D42` | 32bpp 不透明貼圖(仿射) | 12 | 4 |
| `C06E4FFA` | 16bpp 不透明貼圖(仿射) | 12 | 3 |
| `C06E9AA4` | 32bpp source-over 混色 | 40 | 11 |
| `C06E4A4C` | 8bpp 調色盤 → RGB565 混色 | 46 | 12 |
| `C06E9BEA` | 32bpp 混色 + 全域顏色調變 | 58 | 17 |
| `C0722490` | 圖層 fill(16bpp，一次一個 `strh`) | 4 | 1 |
| 對照:`C001510C` memcpy | — | ≈0.1–0.25 | — |

**[推] 量級**：主圖層是 1024×682(698k 像素)。換頁整層重畫時，如果都走混色 span(40–58 指令/像素)，
**一層就是 28–40 M 指令**。A7 的 IPC 與時脈都沒量過，所以無法換成毫秒，但這已經和 48 ms 一輪是同一個量級。
dirty rect 小的時候(例如秒數跳動)成本小很多。

## 3. 圖資：每次換頁都重新解壓，而且解壓器很慢

- `.xci` 共 2005 張，全部是 16bpp YUV + LZ4。壓縮後 2.93 MB，**解開 24.99 MB** [靜，掃 `0xC1240000` 起的檔頭]。
- **LZ4 解壓器是逐位元組函式呼叫的寫法 [靜]**：
  - 區塊解壓在 `C05A7630`。
  - literal 與 match 都交給 `C04D11E8` 複製，它一次一個位元組，每個位元組都要讀寫串流指標。
  - 讀 token 是 `C04D12D8`，每個 token 一次函式呼叫。
- **[模] 抽樣 60 張 icon 直接跑原廠 `C05A7630`**：解出 614,084 bytes，花 9,779,832 指令，**15.9 指令/輸出位元組**。
  輸出與獨立的 Python LZ4 解碼逐位元組相同(腳本 `scratchpad/perf/emu_lz4.py`，見文末)。
  - 一張 380×380(289 KB)要 2.9–3.5 M 指令。
  - 正常的 LZ4 解碼器(8/16 B wildcopy)約 0.5–1.5 指令/byte，**差 10–30 倍**。
- **快取策略 [靜]**：
  - 開機時 `UicResourceCache::v1`(`C0565288`)預載約 272 項(字型、數字、常用符號)。
  - ⚠ 2026-10-19 更正：`C05663E8` 的那一格只裝三個 QS 版面之一(`QS_CINE`/`QS_STILL`/`QS_STILLlike`，依模式)，**不是換頁快取**;真正的換畫面是 `C05DD5CA` 載入新的、`C05DD670` 卸載舊的，見 `projects/sys-perf/pagelru/README.md` §1。原文：
  - 頁面資源集由 `UicResourceCache::v2`(`C05663E8`)管理，**只有一格**：名字不同就先卸載舊的(`C05D93A0`)，再載入新的(`C05D9390` → 佈局載入器 `C05D90F0`)。
  - 所以 A → B → A 會把 A 整組重新解析並解壓一次。
  - 既有筆記也確認：NBU 每組資源集解析一次、CSV 不快取(開頁才讀)，見 `research/ui/HOW_CHANGES_TAKE_EFFECT.md` §5。

## 4. 每輪繪製後的整快取清除 [靜]

- `C0528700` 只要任一 slot 畫了東西，就呼叫一次 `C000E91C`：L1+L2 set/way clean+invalidate，**全程關 IRQ+FIQ**。
- 上限約每秒 20.8 次。待機時有沒有東西在變(秒數、音量表、直方圖)決定實際次數 [推：CINE 待機幾乎每輪都有]。
- 代價有兩部分：走過 L1+L2 每一條 line，加上其他任務的熱資料被趕出去。L2 大小沒量過(要在機上讀 CCSIDR)。

## 5. 可優化候選

| # | 改法 | 預估收益 | 風險 | 離線能做到哪 |
|---|---|---|---|---|
| A | **換掉 LZ4 解壓器**：`C05A7630` 改成同介面(讀寫同一組串流指標)的快速版，或只把 `C04D11E8` 改成字組複製 | 解壓 10–30×;換頁時間的解壓部分 | 低：純函式、無共享狀態 | **全部**：2005 張逐位元組對拍 + 指令數(harness 已有) |
| B | **圖層 fill 改用 memset 式寫法**:`C0722490`/`C0722530`/`C07224E0` 改成 STM 寫法(16bpp 先把值複製成 32 位元) | 整層清除 2.8 M → 約 0.1 M 指令 | 低 | 全部(unicorn 對拍輸出緩衝) |
| C | **span 加等倍快速路徑**：仿射參數是 identity 時，不透明 → 逐列 memcpy，混色 → NEON 一次 8 像素 | 換頁、QS 動畫的主成本;12→≈0.3、40–58→≈5 指令/像素 [推] | 中高：要先找出 span 分派與參數結構;要覆蓋所有格式組合 | span 可在 unicorn 單獨對拍;分派點還要再追 |
| D | **繪製後改成只清 dirty rect 範圍**:`C000E91C` 換成對 UIC 回報 rect 做 `C000EB90` | 省掉 L1+L2 全走一次與關中斷;rect 小時最有效 | 中：非 UIC drawer(直方圖、OSD 文字)也會寫圖層，要全部算進 rect，漏一個就閃爍或殘影 | 邏輯可模擬;正確性要上機看 |
| E | **重繪節奏**:`[0xC3782FA4]`/`[0xC3782FA0]` 從 3 改 2(32 ms) | 按鍵到畫面的延遲少 16 ms;CPU 增加約 50% 的 UI 份額 | 低(RAM 值，可還原);但錄影時 CPU 已滿，**錄影中不能用** | 無;只能上機 |
| F | **資源集兩格 LRU**:`C05663E8` 保留上一組不卸載 | A↔B 來回不再重解 | 中：記憶體上限不明;OG/uishare 的 RCACHE hook 依賴目前的單格語意(見記憶 rcache-v3-takes-the-cache) | 少 |

建議順序：**A、B 先做**(收益明確、離線可完全驗證)，**C 是最大的那塊**，但要先把分派追清楚。D、E、F 要上機量。

## 6. 上機驗證步驟(等相機)

1. **原廠自帶計時**:`uicMgr+0x198`(`0xC37B71CC`)bit0 = 1 會用 log 類別 0x2000 印「Gui Update / Gui Render」每輪的 µs(`C05613C8`);
   bit1 印每輪 rect。資源集載入有「Load_Start / Load_End」。shell 有原生 `log` 指令(`log on`、`log act …`)，用法未驗證。
2. 翻選單、換頁、開 QS，各錄 10 秒 log：分成 Update、Render 與 Load 時間。
3. 掛計數器在 `C05A7630`、`C0722490`、`C000E91C`、`C06E9AA4` 等 span 入口，取每秒次數 × 每次像素數。
4. 有 profiler 之後(見 `research/firmware/notes/PC_SAMPLER_HOOKPOINTS.md`)直接看 DrawMgr 的 PC 分佈。
   **注意**:`C000E91C` 關中斷，它的時間會集中記在 `C000E9B4` 附近。

## 重現

```sh
# LZ4 解壓器指令數(unicorn,與參考解碼器逐位元組比對)
python3 scratchpad/perf/xci_scan.py     # 列出 2005 張 xci → xci_ents.json
python3 scratchpad/perf/emu_lz4.py      # 抽 60 張 + 3 張 380x380
# 迴圈掃描
python3 scratchpad/perf/tloops.py c0000000 c0c00000
```
(scratchpad = `/private/tmp/claude-501/-Users-dido-Developer-localized-SIGMAfp-re/d8b52e05-f45d-4908-9eb1-c2708f2ac578/scratchpad/perf/`;要保留就搬進 `research/display/`。)
