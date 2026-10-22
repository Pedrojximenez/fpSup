# 相機壓縮輸出讀回 — 已執行 2026-09-23，通過

寫於 2026-09-23 離線，同日執行完畢。

**結果:相機自己的位元流被證明無損**——2,110,240 個樣本的 SHA-256 與來源完全相同。
細節與證據見 [`IMPLEMENTATION.md`](IMPLEMENTATION.md) 與
[`../build/ledger-camera-bitstream-20260923.json`](../build/ledger-camera-bitstream-20260923.json)。

執行時發現的兩件事，已回寫到下面：tile 在 arena 裡確實連續（12 個 SOI delta 全為 0），
但**最後一塊被補到讓總長 512 對齊**，所以框界檢查改成允許 EOI 之後的零填充。

## 1. 要回答什麼

到今天為止已經證明的是:相機**能**編碼、**多快**(13,652 µs)、**多小**(1,386,496 bytes)。
沒有證明的是**編出來的東西對不對**。所有被解碼驗證過的位元流都是主機編的。

探針把相機的輸出丟棄了,所以我們有相機的 tile **尺寸**,沒有相機的 tile **內容**。

## 2. 關鍵機會

**相機把同一幀的未壓縮 DNG 寫到卡上了。** 所以只要把 scratch 裡的壓縮輸出讀回主機,
就能和卡上那一幀逐樣本比對:

```
相機 scratch 的 payload  +  canonical segment 0  →  解碼  →  與該幀的 stock DNG 比對
```

這會是第一次驗證相機自己的無損位元流。

## 3. 阻擋的四件事

| # | 問題 | 解法 |
|---|---|---|
| 1 | 成功時探針會**釋放**區塊,payload 隨之消失 | ✅ `--keep` 已實作 |
| 2 | 工具**沒有釋放動作**,保留後只能拔電池 | ✅ `release` 已實作 |
| 3 | 1.4 MB 要離開相機 | `mem save` 寫到卡,再用讀卡機取(**優先**)或 `getfile` |
| 4 | 不知道編的是哪一幀 | 用探針記錄的首/末像素字比對,不靠檔名或順序 |

`getfile` 會用到 template 區並 claim cave 空間,**只能在 hook 已還原之後**跑。
讀卡機完全避開這個風險,是建議做法。

## 4. 程序(每段各一次錄影)

```sh
preflight            # PPWR
scratch              # ALOC,保留 4 MiB
encode-live --keep   # 編碼後不釋放
status               # 取 tile sizes、handle、first/last pixel word
```

然後把 payload 倒出來:

```sh
fpsh mem save \PAYLOAD.BIN <handle>,<handle+sum(tile_sizes)>,
```

取回檔案後,主機端:

```sh
python3 tools/verify_camera_payload.py \
    --payload PAYLOAD.BIN \
    --tile-sizes 71288,123173,... \
    --clip-folder /Volumes/<card>/CINEMA/A001_nnn \
    --first-pixel-word 0x... --last-pixel-word 0x... \
    --out /tmp/camera_assembled.DNG
```

最後明確釋放區塊,或拔電池。

## 5. 兩個被明確標示而非假設的前提

**哪一幀。** 探針記錄它讀到的來源首字與末字;`find_frame()` 用這兩個字在 clip 資料夾裡
找,找不到或找到多個都拒絕,不猜。

**tile 在 arena 裡是否連續。** 目前按尺寸依序切,並在報告裡標明
`tiles_assumed_contiguous_from_arena_base: true`。若實際有間隔或對齊,
**SOI/EOI 框界檢查會立刻抓到**(見下),不會默默產出錯誤影像。

## 6. 2026-09-23 量到的一件事,改變了驗證設計

**解碼不能驗證 tile 表。** 把第 0 塊宣告長度 +16、最後一塊 −16(總長不變),
每一個樣本仍然完全正確。原因:每個 tile 都是完整的 JPEG 流
(`ffd8 ffc3` … `ffd9`),LibRaw 靠掃描 SOI 重新同步。

所以「解得開」**不代表**表是對的。`verify_camera_payload.check_tile_framing()`
因此要求每個宣告區間都必須是完整的 SOI…EOI,這才是抓得到表錯的檢查。
相機 writer 的尺寸表正確性必須靠結構檢查建立,不能靠解碼結果。

## 7. 風險

- 保留區塊後若未釋放,4 MiB 會留到下次開機。
- `mem save` 會在錄影後寫 1.4 MB 到卡。
- 若 codec 的 arena 版面不是連續的,切片會產生無法框界的資料——會被抓到,不危險。
- **不得**在 armed 期間跑 `getfile`／`putfile`／任何 template helper。

## 8. `--keep` 與 `release` 的實作要點

**`--keep` 不是「跳過釋放」,是「釋放碼不存在」。** 它是組譯期 define,
整段 release 區塊不被組譯,所以**沒有任何路徑能到達 `F_FREE`**。
映像因此小 96 bytes(1,428 → 1,332),有測試逐指令確認 keep 版不含該呼叫、
一般版含有。

**`release` 只允許兩種有據可循的情況:**

| 狀態 | 動作 |
|---|---|
| codec 從未進入 | 釋放 |
| 已進入且回報成功(`--keep` 的正常結果) | 釋放 |
| 已進入但未成功 | **拒絕。** 引擎可能仍持有 DMA;拔電池(ROADMAP §5.4) |

釋放**回傳之後**才把 `FREE_MAGIC` 記進狀態區——否則 retained-scratch 閘門會對一塊
已不存在的區塊永遠拒絕,正是 2026-09-23 那次繞過釋放造成的情況。
重複呼叫是無操作;handle 形狀不對則拒絕;`F_FREE` 沒回來則不記錄、不重試。

## 9. 同一次 session 順便解決的事:快取視窗

`--keep` 之後 codec 已經用 DMA 把輸出寫進 arena。此時從兩個視窗讀同一處,
就能判定哪個視窗與 DMA 同調 —— **只讀,零額外風險**:

```sh
python3 tools/window_coherency.py --fpsh <path> --handle 0x452B9000
```

| 結果 | 意義 |
|---|---|
| `0x4` 看到 SOI、`0xC` 是舊資料 | `0x4` 是與 DMA 同調的視窗 |
| 兩邊都看到 SOI | 單獨無法定論(快取可能根本沒持有那些行) |
| `0x4` 看不到 SOI | 連 `0x4` 視窗也是快取的,交出去前必須清 |

**為什麼需要量:** 韌體自己的慣用法(`FUN_c062f510`)是「CPU 在 `0xC` 視窗操作 →
`FUN_c000e91c` 清 D-cache → 把 `0x4` 位址交給硬體」,這說明 `0xC` 是快取的,
但**沒有**說 CPU 從 `0x4` 看到什麼。而我們要掛的 flush 路徑,在反編譯追得到的範圍內
(往下 4 層、22 個函式後撞上間接分派)**完全沒有快取維護**。離線問不出答案。

這個答案決定寫卡階段的形狀:若 `0x4` 同調,標頭就從那裡寫,不需要每幀清快取;
若不同調,就得付 set/way 全清的代價,或改用定點維護。

## 10. 現在已經可以用的部分

`tools/verify_camera_payload.py` 與其 10 項測試**已完成並通過**,用主機編碼的位元組
代替相機 dump 跑完整條路徑:找幀、框界檢查、切片、組裝、解碼、逐樣本比對。
唯一需要相機的是第 4 節那個 dump。
