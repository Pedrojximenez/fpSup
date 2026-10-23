# filldma：整層填色交給硬體 Fill DMA（2026-10-19，離線）

狀態：離線完成，unicorn 對拍 20/20、mutation 22/22。**沒有上機、沒有寫卡、沒有 commit。**
**[靜]** = 反組譯看到；**[模]** = unicorn 跑出來；**[推]** = 推論。

## 1. 介面（給 dispatcher）

`fd_layer_fill(r0 = layer, r1 = value)`，ARM，位於 `filldma.bin` +0x40，參數與圖層 vtable 的 fill `C0721480` 相同。

| 回傳 | 意思 |
|---|---|
| `0` | 已填完（DMA；或 DMA 開始後出錯時由本函式用 CPU 補完） |
| `1`–`7` | **不接手**：沒寫任何像素、沒做任何快取操作、沒碰 driver。1 停用、2 不是 16bpp、3 圖層無效、4 小於門檻、5 driver 沒初始化、6 對齊/不是 DRAM/太大、7 錄影中 |

- 只能在 task 內呼叫（會在 driver 的號誌上睡）；不碰 VFP/NEON；clobber r0–r3、ip。進入時 sp 不必 8 對齊。
- **vtable 槽 `0xC2E38E7C`、`0xC2EF62A0`（原值 `C0721480`）由 dispatcher 佔用，本檔不寫它們**（`patch.json` 的 `patches` 是空的）。
- RAM 可調（`patch.json` 的 `header`）：`fd_enable`(+08)、`fd_thresh`(+0C，預設 0x4000 B)、`fd_rec_ok`(+10，預設 0＝錄影中不接手)。
  統計：calls、dma_ok、dma_bytes、declined、cpu_done、last_code、last_base/size。
- 給 dirtyclean：回傳 0 時 `[base, base+size)` 已經 invalidate，CPU 看到的就是新值，該範圍沒有髒 line，不需要再 clean。

## 2. Fill DMA driver（`0x30041000`）[靜]

- `C00DB188(desc)`（Thumb）：wai_sem 互斥 `[0xC301FEC4]` → 開 IRQ 0x24（`C000FCA0`）→ 時脈閘 `0x300022A4 |= 0x100` → `C00DAFF8` → 關時脈閘 → 關 IRQ → sig_sem。
  **同步**：`C00DAFF8` 每段寫 start bit 後 wai_sem `[0xC301FEC0]`，由 IRQ 0x24 的 `C00DB7E0` 給號誌。成功回 0，取不到互斥回 -1。
- 暫存器：+00 bit0 start、+04 |=1、+08 =0xFF（清狀態）、**+10 目的 = DRAM 偏移/4**、+14 stride（word）、+18 寬（word）、+1C 列數、+20/+24 樣式（32-bit）、+28 bits1:0 模式（0＝填）。
  寬、列、stride 都要 < 0x4000；否則只接受 stride==寬，再自己拆段。本檔一律拆成「0x2000 word × N 列」＋餘數一列，不會走到那條拆段路徑。
- 位址：DRAM 偏移 = cached VA − 0xC0000000 = 非快取別名 − 0x40000000（`C00DB2F8`、`C00218C8`、CPU 退路 `C00DB278` 三處一致）。
  **陷阱**：desc+0x0C 若傳 VA>>2（×4 > 0x80000000），driver 會自己呼叫 `C000E91C` 清整個快取。本檔只傳偏移。
- 初始化 `C00DBC80` 會**建一個 task**，並註冊 IRQ 0x24。開機時 LCD 初始化 `C0308078 → C00E9970 → C00DB998` 已經跑過 [靜]，旗標是 `[0xC31D25B4]==1`。
  本檔不是 1 就不接手，絕不自己 init。原廠 `C0021798`（SDK fillRect）不做 init 就呼叫 driver，所以不借用它。
- 使用者：Display 函式庫的 YUV/tiled 清除（`C071E960 → C00E1EC8`）、`C00DB2F8` 一族、driver 自己的非同步 task。
  沒找到錄影路徑呼叫它 [推]；併用由原廠互斥保證。

## 3. 為什麼這樣做快取 [靜/推]

- 只接手 base 與 size 都對齊 64 B（整條 line）的情況，所以 DMA 會覆寫範圍內每條 line 的全部位元組。
- DMA 前先 **invalidate**（`C000EB28`，每次 64 KB，限制關中斷時間）：髒 line 直接丟掉，不寫回；否則 DMA 期間被逐出的髒 line 會蓋掉 DMA 的結果。
- DMA 後再 invalidate 一次：丟掉 DMA 期間被預取、內容還是舊值的 line。
- driver 在已經 invalidate 之後才失敗時，本函式自己用 STM 把整塊寫完並回傳 0，不會把「快取已被動過」的狀態交回去。
- 非快取別名（0x40000000–0x7FFFFFFF）不做快取操作。

## 4. 結果 [模]

整層 1024×682 16bpp：原廠 `C0721480` 執行 2,793,588 道指令；本函式 1,179 道，另加兩次 invalidate（實機約 13 萬道指令 [推]），其餘時間 DMA 跑、DrawThread 睡。
DMA 實際要多少 µs、和 CPU 寫的 DRAM 頻寬差多少，**沒量過**。

## 5. 測試

`python3 -B -m unittest test_filldma`（約 14 秒）：真映像，layer 物件用真 vtable `0xC2E38E5C`，參考答案是原廠 `C0721480 → C0722490` 實跑。

- 接手：整層（兩段：滿列＋餘數）、高位元忽略、剛好整列、非快取別名、sp≡4、門檻可調、`fd_rec_ok`。
  比對整塊緩衝區（含前後 64 B 護欄）和原廠逐位元相同；檢查 desc 欄位、樣式；檢查事件順序：
  invalidate 全範圍、無縫、每次 ≤ 64 KB → lock → IRQ 開 → start → done → IRQ 關 → unlock（×2）→ invalidate；錄影檢查在任何快取操作之前；
  r4–r11、sp 復原；我們自己發出的呼叫 sp 都是 8 對齊；互斥有釋放。
- 出錯：每段都失敗、只有第一段失敗 → CPU 補完、結果相同、補完前再 invalidate 一次。
- 不接手（1–7 每種都測）：回傳碼正確、**緩衝區不變、沒有 invalidate、沒呼叫 driver**；接著跑原廠 fill，結果和原廠相同。
- 模型：0x30041000 寫 start 時，依暫存器填記憶體並給 done 號誌；檢查時脈閘已開、模式 0、兩個樣式字相同、寬/列/stride < 0x4000。
  快取別名用 `mem_map_ptr` 兩個位址共用同一塊記憶體。

`python3 -B mutate.py`：22 個改壞的版本（每一道檢查、兩次 invalidate、樣式、偏移、拆段、錯誤處理、sp 對齊、回傳碼……）全部被抓到；原始檔不改，突變版寫在暫存目錄。

**沒驗到的**：driver 被 stub 掉的部分（OS 號誌、`C000FCA0`、`C00178D8`）、真的 DMA 硬體行為（32-bit 樣式的位元組序、2D 模式是否照模型、完成中斷）、invalidate 真的有效。

## 6. 上機最小驗證（非錄影，先別接 dispatcher）

照 skill `fp-firmware-call`，用 `callfn` 一個一個呼叫，每步讀回：

1. 讀 `patch.json` 的 `fw_checks`、`runtime_checks`：`[0xC31D25B4]==1`、`[0xC301FEC4]`、`[0xC301FEC0]` 非 0。不符就停。
2. `B = cave.claim('filldma.test', 0x20000)`（要 64 對齊；不夠就多要一點再自己對齊），`put` 填 0x5A。
3. 直接測 driver：在 `B+0x10000` 放 0x28 B desc：`+0C=(B−0xC0000000)>>2`、`+10=0`、`+14=0x100`、`+18=1`、`+1C=0x100`、`+20=+24=0x11223344`。
   呼叫前對 `[B, B+0x400)` 呼叫 `C000EB28(B, B+0x3FF)`。接著 `callfn.call(0xC00DB189, r0=desc)`，回傳應為 0。
   之後再 `C000EB28` 一次，讀回 `B..B+0x400`：每字 0x11223344（同時確認位元組序），`B+0x400` 起仍是 0x5A5A5A5A。
   **卡住（不回來）= 完成中斷沒來**：照 skill 的冷開機恢復，記錄下來，這條線就停。
4. 載入 `filldma.bin`（`C000E91C` → `C000EABC`），在 claim 的記憶體建一個假 layer（vt=`0xC2E38E5C`、w=512、h=64、[+0x1C]=1、[+0x4C]=bufobj、[bufobj+4]=B），
   `callfn.call(blk+0x40, r0=layer, r1=0xF00F)` → 回 0，讀回整塊 = 0xF00FF00F；`fd_dma_ok`=1。
5. 量時間：同一塊用原廠 `C0721480` 和 `fd_layer_fill` 各呼叫一次，前後讀 `C002B6E0`（1 MHz）。
6. 之後才交給 dispatcher 接 vtable 槽，用 `uicMgr+0x198` bit0 看 Gui Render µs，並截圖比對。

## 檔案

| 檔 | 內容 |
|---|---|
| `filldma.S` | `fd_layer_fill`（780 B，位置無關） |
| `build.py` | 組譯、核對 11 個韌體字與 2 個 vtable 槽，輸出 `filldma.bin`、`patch.json` |
| `test_filldma.py` | unicorn 測試（20 項） |
| `mutate.py` | mutation 檢查（22 個） |
