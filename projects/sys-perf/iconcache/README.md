# iconcache:圖示解壓一次就留著重複用(2026-10-19,離線)

狀態：離線完成，unicorn 對拍通過。**沒有上機、沒有寫卡、沒有 commit。**
**[靜]** = 反組譯;**[模]** = unicorn 跑出來;**[推]** = 推論。

## 1. 先更正:UI 圖示不是走 C05A7E50 [靜]

上機看到 lz4fast 的 `C05A7E50` 在選單各頁 0 次呼叫，原因找到了：
- **UI 圖示的載入函式是 `C0601F98`(Thumb,UIC 的 Image 節點)**,由節點的屬性設定/載入方法
  `C0602450`、`C0602478` 呼叫(兩者是 vtable 方法)。它：
  1. 用 UIC 平台介面 `r6`(`+0 alloc(size, ud)`、`+4 free`、`+0xC 找資源`、`+0x10 釋放資源`、`+0x34 ud`)按名字拿到 .xci;
  2. 檢查 `XC\0\0` 檔頭，依壓縮型態分三路：0 = 直接指 ROM、1 = 以 `C0602601/2651`(16bpp)或 `C06026A9/2719`(32bpp)逐列解、
     **2 = LZ4 frame,解碼器直接寫在函式裡**(`C06021A0..C060235A`,逐位元組 `ldrb/strb` 迴圈 + `C06027A0` 讀長度);
  3. 解出的 buffer 交給繪圖 driver 建圖(`[r7+0x3c]`),圖擁有 buffer,節點卸載時用 `r6+4` 釋放;
  4. 若 `uicMgr+0x198` bit2,呼叫 `[0xC37CECF8]`(= `C055FDC8`)記一行 gui image log —— 就是 `gui image log 1` 那行。
- 2005 張 .xci **全部是壓縮型態 2**。所以 `C05A7630/C05A7E50`(lz4fast 換的那個)不是 UI 圖示的路徑。
  **lz4fast 換錯解碼器**:真正的 UI 解碼是 `C06021A0..C060235A`,約 5 指令/輸出位元組 [模](比 C05A7630 的 13–16 好)。
- **沒有任何快取**:每次節點載入都重新解。重複解壓的情況:頁面重新載入(資源集只快取一組，見 `C05663E8`)、
  同一張圖被多個節點使用(例如時間碼的數字字形)。[靜]

## 2. 做法

兩個 hook,各是一個**對齊的 Thumb32 字**(單一 32-bit 寫入，換的瞬間是原子的),`b.w` 到 8 B veneer
(`ldr.w pc,[pc,#0]` + 本體位址，偶數 = 進 ARM):

| | 位址 | 原字 | 原指令 | 我們 |
|---|---|---|---|---|
| H1 | `C060219C` | `46586B71` | `ldr r1,[r6,#0x34] ; mov r0,fp` | 查快取。命中：照原廠呼叫 `alloc(size, ud)` → memcpy → `[sp+0x48]=buf` → 跳 `C060235A`(原廠的 `ldr.w fp,[sp,#0x48]`)。未命中：記下 key,重做兩條原指令，回 `C06021A0` 讓原廠解碼 |
| H2 | `C060234C` | `92243204` | `adds r2,#4 ; str r2,[sp,#0x90]` | LZ4 路徑的結尾。若這個 frame(以 sp 認)就是剛才未命中的那一張，且解碼器**剛好寫滿 size**(`[sp+0x98]==size`、`[sp+0x9c]==buf`、壓縮型態 2),複製進快取;重做兩條原指令，回 `C0602350` |

- key = (LZ4 frame 位址、壓縮大小、**FNV-1a 對整段壓縮資料**、解出大小)。資源在 RAM 被改寫(同位址不同內容)也會 miss。
  壓縮大小其實已被雜湊涵蓋(雜湊只算那麼長)，在 key 裡是多一道防呆，所以沒有對應的 mutation。
- **擁有權與原廠相同**:命中時 buffer 一樣由 UIC 的 `alloc` 給，交給圖、由圖釋放;快取自己的拷貝在 arena 裡，從不交出去。
- arena 由安裝者給(`ARENA`/`ARENA_SZ`,8 對齊)。建議放在 sup 塊的 BSS(v3 塊來自 class 0 USER 堆，跟 10LOSS/32RESCUS
  一樣整次開機握著、跨錄影已有先例);**不要用 class 10**(記憶 allocator-not-across-recording)。
- 表 128 格、first-fit、滿了淘汰最久沒用的(未被 pin 的)。搜尋不關中斷;每次改表時關 IRQ/FIQ、先 O(N) 重新驗證再寫。
  memcpy 期間不關中斷，命中的項目被 pin 住不會被淘汰。
- 大於 `MAXENT`(預設 512 KiB)的不快取。
- **唯一的行為差異**:命中時 UIC `alloc` 回 0 —— 原廠會解碼到位址 0(壞掉);我們讓 `[sp+0x48]=0`,走原廠的錯誤路徑。

控制區(本體 +0):`+00 'ICCH'`、`+04 enable`、`+08 arena`、`+0C arena_size`、`+10 max_entry`、
`+14 hits`、`+18 misses`、`+1C inserts`、`+20 evicts`、`+24 skips`、`+28 alloc_fail`、`+2C pending_sp`、`+40 clock`、
`+48 rejects`、`+50` 表(128 × 32 B:state、src、csz、hash、size、off、stamp、pins)。
enable=0 時兩個 hook 只重做原指令(等同原廠)。

## 3. 成本 [模]

`python3 -B cost.py`(C0602184 → C060235E 的指令數，不含 alloc 本身):

| | 指令/輸出位元組 |
|---|---|
| 原廠解碼 | 4.96 |
| 命中(雜湊壓縮資料 + memcpy) | 0.29(**約 17 倍**) |
| 未命中的額外成本(雜湊 + 拷進快取) | +6.8% |

## 4. 測試 [模]

`python3 -B test_iconcache.py`(約 4 分鐘;`--quick` 300 張約 40 秒;`--mutate`)
- 真實映像跑 `C0602184 → C060235E`,原廠與修補版**分兩個 unicorn 實例**(unicorn 不會作廢已翻譯的區塊)。
  比對：fp、整個解出的 buffer、r4–r7、sl、sp、alloc 的參數、整個堆疊 frame(命中時 LZ4 暫存字 0x44、0x70–0x9F 不寫，排除)。
- 全部 2005 張：第一輪(全未命中，逐張與原廠相同)+ 反序第二輪(命中 128 張 = 表格上限，全部相同且解碼迴圈 0 指令)。
- LRU:A B C 插入、A 命中、D 插入淘汰 B;以及全部命中過再插入，最久沒用的必須可被淘汰。
- enable=0(計數器不動、輸出相同)、命中時 alloc 失敗、同位址內容改變(必須 miss)、超過 MAXENT、解碼不滿(拒收)。
- `--mutate`:10/10 被抓到(命中不 memcpy、查找不比雜湊、H2 不檢查長度、fits 不檢查重疊、淘汰最新的、
  命中不寫 [sp+0x48]、未命中漏 `mov r0,fp`、H2 漏 `str [sp,#0x90]`、pin 不釋放、H1 無視 enable)。

## 5. 上機驗證(未做)

1. 安裝順序(`patch.json` arm_order):寫本體與 veneer 讀回 → 寫 arena/arena_size(enable 仍 0)→ `C000E91C`+`C000EABC`
   → 先改 H2 再改 H1(各一個對齊字，改完各做一次快取維護)→ enable=1。兩個字要宣告成 4-byte 區段(關機寫回)。
2. 換頁時間：開 `uicMgr+0x198` bit0(`0xC37B71CC`)看 Gui Update/Render µs 與換頁的 Load_Start/End;
   同一組換頁(例如選單 A→B→A 來回 10 次)enable 0/1 各量一次。
3. `gui image log 1`:確認換頁時載入的圖示名單與 enable 0 相同(只是不再解碼);截圖逐像素比對。
4. 計數器：`hits`、`misses`、`inserts`、`evicts`、`skips`、`rejects`(應為 0)、`alloc_fail`(應為 0)。
5. 錄影中不碰 USB;錄一段確認 arena 握著不影響錄影(arena 在 sup 塊 BSS 時與其他 sup 同一種記憶體)。

## 6. 範圍外的觀察

- lz4fast 應改成換 `C0601F98` 裡的內嵌解碼(`C06021A0..C060235A`);目前它換的 `C05A7630` 在 UI 上不會被呼叫。
  有了 iconcache 之後，只剩第一次載入要解碼。
