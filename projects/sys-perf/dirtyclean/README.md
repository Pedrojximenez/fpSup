# dirtyclean:重繪後只清本輪畫過的範圍

> **⚠ 更正(2026-10-20,上機探針)**:舊版把 UIC 物件寫成 `0xC37B7034`,實際是 `C055F0F0()` 回傳的 `0xC37B7034+0x14 = 0xC37B7048`;
> 記錄查找因此永遠失敗 → v2.1 上機 whole-buffer 118/118。已修，測試加上「常數必須等於映像裡 `C055F0F0` 的回傳值」檢查。
> 同理，原廠計時旗標「uicMgr+0x198」實際位址是 `0xC37B71E0`,不是 `0xC37B71CC`。

> 上機記錄樣本(波形+音訊表開):base c6355180 rect (11,566,14,16)、c64aa180 (11,566,22,16)、c6200180 (11,598,62,16),mode 0 —— 音訊表的格子。(2026-10-19，離線完成，**未上機**)

原廠 `C0528700`(DrawController 一輪重繪)只要任一 slot 畫了東西，就呼叫 `C000E91C`：
**整個 L1+L2 set/way clean+invalidate，全程關 IRQ+FIQ**。時間碼影格欄位開著時約每秒 21 次(`TIMECODE_DISPLAY_COST.md`)。
這裡改成：**本輪畫過的 slot 全都只有 UIC drawer 時**，只對 UIC 畫過的列做 DCCMVAC(不關中斷)；其他情況一律照原廠呼叫 `C000E91C`。

## 1. CPU 寫、裝置讀的東西 [靜]

| 寫入者 | 寫到哪 | 範圍怎麼知道 |
|---|---|---|
| 各 drawer 的 draw(`C0528848` 起，vt+0xC) | 該 slot 圖層的 **back buffer** = getBuffer(`C0721328`) = `[layer+0x4C]` desc：`+4` base、`+8`→{w,h}；格式 `[layer+0x1C]`；stride = vt+0x28(`C0721638`) | UIC：UIC 物件 `0xC37B7048`(= `C055F0F0()` = `0xC37B7034+0x14`)`+0x18` 的 10 筆記錄(每筆 0x20：`+4` buffer base、`+8` x,y,w,h)，`C05614E0` 每輪寫入、`C05615E0` 只畫這塊。**其他 drawer 不回報範圍** |
| 整層清除 `C0528B40` → fill `C0721480` → `C0722490`/`C0722530`/`C07224E0` | 同一個 back buffer，**整層**，CPU 逐像素(不是 DMA) | 看 `[ctrl+0x38+s*4]`，執行後歸零 → 用 hook 記 |
| 整層 memcpy `C0528BA0`(commit **之後**，drawer +0x1C 為真時) | **下一輪**的 back buffer，整層 | 用 hook 記，下一輪消耗 |
| commit `C0721370` → ring `C0721CD8` | 只改 RAM 指標；顯示控制器由 present 訊息/暫存器取位址 | — |

三重緩衝：`layer+0x3C/40/44` 三個 desc，commit 時 idx+1，front=`[+0x48]`，back=`[+0x4C]`。
slot 的 drawer 只有四個註冊點(`C0527D88` 的呼叫者)：UIC(`C06D1634`)、`C05A26C8`/`C05A29D8`(vtable 在直方圖類旁，推定直方圖/波形)、`C03E01C4`(shell `display osd`，slot 2)。

**有沒有東西依賴「invalidate」**：UI 路徑上 CPU 讀的都是 CPU 自己寫的(memcpy 讀 front buffer、glyph、查表)，沒找到依賴 [靜]。
**不確定**：直方圖 drawer 可能讀 ISP DMA 寫的統計資料，且可能順便靠這次全清看到新值。所以**有非 UIC drawer 的 slot 一律走原廠全清**，那條路徑行為完全不變。
另一個不能排除的：別的任務碰巧靠 UI 的全清把自己的 DMA 緩衝清出去。那原本就是競態(UI 不畫就不清)，但若存在，開啟後可能讓它更常出錯 → 上機步驟 5。

## 2. 改法

| 位址 | 原指令 | 改成 | 進入時依賴 |
|---|---|---|---|
| `C0528954` | `bl C000E91C` | `bl` veneer → `dc_clean` | r4 = DrawController(callee-saved)；`[sp+0x18..0x1B]` = 各 slot drew；lr = `C0528958`(會檢查) |
| `C05287F4` | `bl C0528B40` | `bl` veneer → `dc_clear_hook` | r5 = slot；記 `C_CLEAR` 後尾跳原函式 |
| `C0528AE0` | `bl C0528BA0` | `bl` veneer → `dc_copy_hook` | r6 = slot；記 `C_COPY` 後尾跳原函式 |

`dc_clean`：
1. 檢查：開關、回傳位址、每個畫過的 slot 的 drawer vptr ∈ {`C0D17780`,`C2E45DF8`}(UIC)、圖層 vptr ∈ {`C2EF6280`,`C2E38E5C`}、base ≥ `0xC0000000`、大小 ≤ 8 MiB。任一不符 → 尾跳 `C000E91C`(原廠行為)。
2. slot 被清除或 memcpy 過 → 清整個 back buffer；否則找 base 相符的 UIC 記錄，裁到圖層範圍內，逐列清 `[bytes(x), bytes(x+w)+1)`；列寬 ≥ 半個 stride 就整段清。找不到記錄或 rect 空 → 整個 buffer。
3. `dsb sy`；消耗本輪的 clear 標記與畫過 slot 的 copy 標記。**全程不關中斷，也不 invalidate。**

veneer(各 8 B：`ldr pc,[pc,#-4]` + 目標)要在 `C0528954` ±32 MiB 內 → 用 `cave.claim`(arena `C072E064..C072EFB4`)。本體 1120 B，與位置無關，放自己的配置區。細節與順序在 `patch.json`(`make_patch.py` 產生)。

## 3. 離線驗證(unicorn，真韌體映像)

```sh
python3 -B test_dirtyclean.py            # 17 個情境
python3 -B test_dirtyclean.py --mutate   # 13 個突變
python3 -B cost.py                       # 指令數
```
- **真的在跑的**：`C0528700` 本身、getBuffer/commit/ring/fill/memcpy/pixelsToBytes、UIC 的 +0x1C、我們的程式碼。
  stub：鎖、事件旗標(給 dirty 位元)、log、`C0528E18/178/650/C28/6D0`、`C000E91C`(模型：所有髒 line 變乾淨)、drawer 的 draw(UIC stub 寫滿自己的 rect 並寫 uicMgr 記錄，如同 `C0561198`;「其他」drawer 寫一塊不回報的範圍)。
- **判準**：每次 commit(`C0721370`)時，被 commit 的 buffer 沒有任何髒 cache line(模擬寫入或 drawer 寫入、之後沒被我們的 DCCMVAC 或全清清掉)。另檢查 sp 與 r4–r11 還原。
- 結果：17/17 通過(含 sp≡4 進入、左上/右下超界、兩個 slot、清除、其他 drawer、memcpy 後 drawer 離開、另一 slot 的 fast 輪不吃掉 copy 標記、4/16/32 bpp、停用、原廠對照)。**13 個突變全被抓到**(少一列、結尾 +1、忽略 clear/copy 標記、不檢查 drawer 種類、只處理 slot 0、hook 不記、fast 路徑清光 copy 標記、x/w/h 不裁切、stride 錯)。
- **測不到的**：真的 UIC/直方圖 drawer 寫了哪些位址(用 stub 代替)；uicMgr 記錄就是本輪實際渲染範圍(靜態讀 `C0561198` 得出)；硬體快取行為。

## 4. 成本 [模，unicorn]

| 情況 | 我們 | 原廠 `C000E91C` |
|---|---|---|
| 時間碼 FF 兩位數 | 1,908 指令，141 line | 186,980 指令，37,376 次 set/way，**全程關 IRQ+FIQ** |
| 秒＋影格四位數 | 2,237 指令，188 line | 同上 |
| 一列選單 1024×80 | 18,200 指令，2,561 line | 同上 |
| 整層(換頁) | 153,048 指令，21,825 line | 同上 |

原廠的 set/way 次數取決於 L2 大小，模擬器報的 CCSIDR 不一定是相機的；相機上讀 CCSIDR 才算數。
整層時兩邊指令數接近，但我們不關中斷、不把其他任務的快取資料趕出去。

## 5. 上機驗證(相機回來後；先廣播取得使用權，不在錄影中)

1. **唯讀**：三個位址的字等於 `patch.json` 的 orig_word；讀 `0xC37B7048+0x18` 的記錄，`+4` 應等於某個圖層 desc 的 base、rect 合理；各 slot 的 drawer vptr 實際值。不符就停。
2. **只掛不啟用**：`C_EN=0` 安裝 → `C_CALLS` 隨重繪增加、`C_FALL == C_CALLS`(全走原廠)。畫面不應有任何差異。
3. **啟用**：`C_EN=1`，時間碼開著、停在 CINE 待機 → `C_FAST` 應增加、`C_WHY` 看 fallback 原因。
4. **殘影/撕裂的客觀檢查**：每次 commit 後，用 MEM1 分別讀 front buffer(`[layer+0x48]` desc 的 base)的**可快取位址**與**不可快取別名**(`-0x80000000`，見 CPU_GLOBAL_CONFIG 頁表)。兩者不同 = 有髒 line 沒寫回 DRAM = bug。front buffer 至少兩輪內不會被改寫(三重緩衝)。針對 rect 區與整層各比一次；開選單、換頁、開直方圖(應走 fallback)各做一次。
   目視：時間碼跑 1 分鐘、選單來回切、QS 開關，看有沒有殘留舊數字或區塊閃爍。
5. **副作用**：開關 `C_EN` 各錄同設定一段，比較停錄時間、`analyzer tskmon` 與 profiler；確認直方圖/波形值仍在更新(它們走原廠全清，應不受影響)。
6. **拆除**：先還原 `C0528954`，再還原另兩處，D/I 快取處理；本體留到重開機。關機寫回靠 loader journal(三個位址宣告成 4 B 區段)。

## 6. 與其他兩條線的介面

- **Fill DMA**(`projects/sys-perf/filldma/`)：若圖層 fill 改走 DMA，(1)**開始 DMA 前**必須 clean+invalidate 目標範圍；(2)經由 `C0528B40` 進入(`dc_clear_hook` 會記)或自己設 `C_CLEAR` 的 slot 位元。dirtyclean 隨後清整個 back buffer，而且從不 invalidate。
- **NEON 繪圖**(`projects/sys-perf/neonblit/`)：只要仍寫在 UIC 回報的 rect 內就不用改；若加了寫 rect 以外區域的快速路徑，必須把範圍併進 uicMgr 記錄，或讓該 slot 走 fallback。
