# layercopy：只複製改過的範圍，不再每輪整層 memcpy（2026-10-19，離線，**停在設計**）

**沒有實作、沒有 patch.json、沒有上機、沒有 commit。** 原因：前提只對一部分 slot 成立，
而在成立的那些 slot 裡，要能逐位元證明「只複製某個範圍」，需要知道該 drawer 實際寫了哪裡；
這件事離線證明不了（理由見 §3）。

`python3 -B evidence.py`：重新核對下面每一條靜態/模擬事實（8/8 成立）。

## 1. `C0528BA0` 什麼時候跑 [靜 + 模]

- `C0528700` 第二階段：slot 這輪畫了、也 commit 了（`C0528178` 為真 → layer vt+0x14），
  之後逐一問該 slot 的三個 drawer 的 **vt+0x1C**；任一回真 → `C0528BA0(ctrl, layer)`。
- `C0528BA0`：`memcpy(back = vt+0x10 desc+4, front = vt+0xC desc+4, stride(vt+0x28) × height(desc+8 → +4))`，整層。
- **UIC drawer 從不要求複製**：兩個 UIC vtable（`C0D17780`、`C2E45DF8`）的 +0x1C 都是 `C05757F8`，固定回 0。
- **非 UIC drawer 預設要求複製**：預設 +0x1C `C03E05A0` 固定回 1（`C05A26C8` 註冊的 drawer vt `C2DF7F68` 就是它；shell `display osd` 的 drawer 也共用 `C03E0588..05A0` 這組預設）。
- 模擬（真的 `C0528700` + 真的 commit/ring，dirtyclean 的 rig）：只有 UIC 的 slot，5 輪 commit **0 次複製**；
  slot 裡有一個 +0x1C=1 的非 UIC drawer，5 輪 **5 次複製**。

所以「每輪整層 memcpy」**只發生在含非 UIC drawer 的 slot**。
這跟上機資料一致：DrawMgr 裡的 memcpy 只在**波形開著**時出現（idle-1 6.1%、全 UI 12.8%），波形關掉就消失（idle-nowave）。
推論（未上機確認）：波形 drawer（HistogramDrawerWaveForm，非 UIC）所在的 slot 每輪 commit 後整層複製。

**順帶查出：上機時 dirtyclean 的 whole-buffer 不是複製造成的。** fast 路徑只在「畫過的 slot 全是 UIC drawer」才會走，
那種 slot 根本不會被複製。whole-buffer 的另一個來源是 `dirtyclean.S` 在 uicMgr 記錄（`0xC37B7034+0x18`）裡
**找不到 base 相符的記錄、或 rect 是空的** → 清整個 buffer。上機 whole-buffer = fast 次數(118/118)
⇒ 真機上這個記錄查找一直失敗（記錄位址/格式和靜態推論不符，或 rect 是空的）。dirtyclean 仍然正確（清整個 buffer 是保守做法），
但它「只清畫過的列」的效益在真機上從來沒發生過。**要修 dirtyclean 先上機讀這 10 筆記錄。**

## 2. 設計（給有複製的 slot）

三重緩衝每次 commit 前進一格：commit n 之後，back = commit n−2 時的 front。
若 n−2、n−1、n 三輪都「commit 後有複製、而且我們看到了」，那麼

```
back 現在 = F(n−2)      front 現在 = F(n)
F(n) 與 F(n−2) 只在 W(n−1) ∪ W(n) 內不同      W(j) = 第 j 輪寫進當時 back buffer 的範圍
```

→ 只複製 `W(n−1) ∪ W(n)` 的外接矩形（逐列，列寬 ≥ 半個 stride 就整段），結果與整層複製逐位元相同。

每個 slot 記最近兩次複製事件 `{front base, back base, W}`，複製前檢查：
1. `front(n) == back(n−1)`（上次同步的 buffer 正是這次畫完 commit 的那個 = 中間只有一次 commit）；
2. `front(n−1) == back(n−2)`；
3. `back(n) == front(n−2)`，三個 base 互不相同；
4. 兩輪的 W 都已知（不是 full），且 front/back 的 stride、高度與上次相同。

任何一條不成立 → 照原廠整層複製，並把該 slot 歷史重設成「這次是 full」。
W(j) 的來源：該輪有整層清除（`C05287F4` → `C0528B40`，hook 記）→ full；
slot 內每個 drawer 都要有已知的寫入範圍，否則 full。

**與 dirtyclean 的介面**：layercopy 每次複製後在 `lc_copied[slot] = {base, x0, y0, x1, y1}`（或 full）留下範圍；
dirtyclean 看到該 slot 有 copy 記號時清這個範圍，不再整個 buffer。整合時 dirtyclean 的 `C0528AE0`、`C05287F4` 兩個 hook
尾跳改成 layercopy 的 hook（同一個 sup，鏈在一起，不各自 claim）。

## 3. 卡在哪裡

複製發生的 slot 一定有非 UIC drawer，而那些 drawer（波形、直方圖、shell OSD）**不回報寫了哪裡**。
要逐位元證明，得知道波形 drawer 每輪的寫入範圍：
- 靜態看 `C05A35A0`，畫點的範圍來自波形物件 `+0x1C/+0x20/+0x24/+0x28`（x、y、寬、高），
  畫點走 `C0529D10 → C052B098`；但物件位址、是否還有別的 drawer 跟它同 slot、背景/格線是否超出框，
  都要相機上的物件狀態才知道。
- 離線跑真的波形繪製需要它的物件與影像資料，模擬器裡沒有。

範圍若取錯（漏掉一塊），後果是殘影；所以沒有上機事實前不實作。

## 4. 上機要先回答的（相機回來，不錄影）

1. 用 `callfn C05278F8`（drawer 註冊前取 DrawController 的 getter）拿到 ctrl，讀：
   `ctrl + 12*s` 每個 slot 的三個 drawer 與其 vptr、`ctrl+0x58+8*s` 的 layer、layer 格式/尺寸。波形開/關各讀一次。
2. 在 `C0528BA0` 掛一個計數（或 profiler 加讀被中斷的 SP 取 memcpy 的呼叫者：`C001510C` 進入時 push `{r0,r6,r8,lr}`），
   確認 DrawMgr 的 memcpy 就是它、每秒幾次、哪個 slot。
3. 讀波形物件的 `+0x1C..+0x28`，和截圖上的波形框比對。
4. 讀 uicMgr `0xC37B7034+0x18` 的 10 筆記錄（dirtyclean 為什麼一直 whole-buffer）。

有了 1–3，波形 slot 的 W 就是「波形框（＋框線）」：每輪複製 ≈ 334×188 像素，而不是 1024×682，約少 11 倍。
實作時另加一個**自檢模式**：partial 複製後立刻整層比對 front/back，不同就計數並永久退回整層複製——上機驗證期間開著，確認 0 之後再關。

## 5. DrawController 實際位址(2026-10-20 更正 §4 第 1 步)

- `C05278F8()` 回的是**外層持有者** H(上機 `0xC3782FC8` = `0xC3782FB8+0x10`),不是 DrawController。
  DrawController = `[H+4]` = `0xC3782FB8+0x68` = `0xC3783020`(上機 dump 第 2 字):`C0527D88` 註冊前 `ldr r0,[r4,#4]`;
  `C05278F8` 用 `C05281B0(r4+0x68)` 建構它。
- `C05281B0` 清零的欄位 = 結構：`+0x00..0x2F` drawers[4][3]、`+0x30`、`+0x34` 事件旗標、`+0x38` clear[4]、
  `+0x48` drawer 數[4]、`+0x58` layer[4](各 8 B;`C0528700` 讀 +5 的旗標位元組)、`+0x78` 鎖。
- layer:back desc = `[L+0x24+0x28]` = `L+0x4C`(`C0721CC8`);ring 的 desc 在 `L+0x3C`(`ring+0x18`),index `L+0x50`。
- 唯讀探針 `live_probe.py`:只用 `callfn C05278F8` 與 `mem_get`(None 重讀，位址不合理就跳過)。

## 6. 上機探針 1 結果與波形層(2026-10-20)

探針 1(`validation/20261019-live/layer_probe_wave_on.txt`,波形+音訊表開):drawer 數 [0,0,1,1];
slot 2 = UIC2 drawer,16bpp 層 `0xC3824FA8`(與 slot 0 共用);**slot 3 = 波形 drawer(vptr `C2DF80C4`,draw `C05A2EE8`,+0x1C `C03E05A0`=1)
在獨立 8bpp 層 `0xC3825014`** → 每輪整層複製 1024×682×1 ≈ 700 KB。

uicMgr 記錄：UIC 物件是 `C055F0F0()` = `0xC37B7048`(不是 `0xC37B7034`);記錄在 `0xC37B7060`,每筆 0x20、+4 base、+8 x,y,w,h、+0x18 mode。
上機樣本對齊後是音訊表格子(11,566,14,16)等。dirtyclean 已修(見其 README 更正)。

波形層的寫入範圍(靜態):
- drawer `C05A2EE8`:`[+5]` 或 `[arg+1]` 為真 → **memset 整層**(desc 物件 +0x10 × +0x14)再畫 → 該輪 W = full。
- 否則交給 painter `[+0x24]` 的 `C05A3728`:先填 `painter+8..+0x14`(x,y,w,h)背景，再在 `+0x1C/+0x20` 起、`+0x24 × +0x28` 內畫點
  (`C05A34B8` 抽樣 330 欄、`C05A35A0` 每欄直方圖 → `C0529D10` 畫點)。painter vptr 應為 `C2DF8F40`/`C2DF8FD8`/`C2DF9214`(+0xC = `C05A3728`)。
- 物件 +0x1C..+0x28 不是框:那是 drawer 快取的 layout(1620×1080 來源尺寸)。框在 painter 上。
→ 探針 2 `live_probe2.py` 讀 painter 的兩個 rect,和截圖(約 x 683..1017、y 430..617)比對。
若相符:slot 3 的 W = fill rect ∪ plot rect(memset 輪除外 = full),layercopy 每輪只複製約 334×188 B(≈63 KB,原 700 KB)。
memset 輪要在 draw 前看 `[drawer+5]`/`[arg+1]`(drawer 自己會清 `+5`),所以實作要多 hook 一點：或在 copy hook 前保守地把「該輪 `+5` 曾為真」當 full。
