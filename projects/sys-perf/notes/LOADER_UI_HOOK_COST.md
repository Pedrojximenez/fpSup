# Loader 的 UI 字串 hook 為什麼吃掉 37% 的 Gui:Update(2026-10-20，離線分析)

這份筆記只做離線分析，沒有碰相機，也沒有改 fpSup 原始碼。標記方式：**[靜]** 是看反組譯或原始碼得到的，**[測]** 是上機量測，**[推]** 是推論。

## 0. 上機數據 [測]

- 測試條件：只載入 00SHELL，其餘 sup 全部停用。LOADER.BIN 的 sha256 是 965c8175…。
- 原廠 GUI log 量到的時間：

  | 動作 | Gui:Update | Gui:Render |
  |---|---|---|
  | 開選單 | 346 ms | 66 ms |
  | 關選單 | 482 ms | 16 ms |
  | 切分頁 | 131–210 ms | 66 ms |

- PC 取樣：開關選單 6 次，DrawMgr 有 **37.3%** 的樣本落在 RAM 程式碼 `0x451AB000..0x451AC100`（LOADER 載入基底 `0x45153E00` + `0x57200..0x58200`）。
- 呼叫者（LR）分布：
  - `C05D9B5D` 306 次：在 `bl C05E9008` 之後。`C05E9008` 用 `bne.w C05E61C8` 尾跳。
  - `C05E8E13` 178 次：在 `bl C05E61C8` 之後。
  - `C05E7B4D`、`C05E7F3B`、`C05E6F25`：都在 `bl C05E5B58` 之後。

## 1. 那段 RAM 程式碼是什麼 [靜]

是 uishare 的**套娃字串 hook**（`uishare/ui_strings.S`、`NESTED_HOOKS.md`）。它掛在三個葉函式上：

| 掛鉤點 | 名稱 | 原廠函式長度 |
|---|---|---|
| `C05E5B58` | 解析 resolve | 5 道指令 |
| `C05E61C8` | 擁有 owns | 約 8 道 |
| `C05E61E0` | 剩餘 remain | 約 5 道 |

- 只停用 sup 並不會拿掉這些 hook：LOADER.BIN 內建的 All Sups 頁（`allsups.c` 的 `allsups_entry`，把 `ft6_site(1..3)` 宣告為 `SL_SHARED_UI`，再呼叫 `uia_apply`）自己也掛了一層。
- 層的程式碼由 `ui_pool.c:uis_layer_add` 從 `alloc()`（`C001D740` class 0）配置，再用 `uis_layer_code` 複製進去。
- `LOAD.LOG` 的 `0A 45153E00 00054CF2 LOADER.BIN` 是 ALLSUPS.BIN 資料區塊，它的長度是 0x54CF2。層的區塊和 loader 本身都在同一個 heap，所以位址落在這一帶。

## 2. 為什麼這麼貴

**(a) 指令數 [靜]**：每次呼叫走 cave veneer（`ldr pc`）→ ENTER（8 道）→ QS 檢查（3 道）→ 範圍檢查（5 道）→ 沒命中就走 NEXT（3 道）→ 原廠規則重寫（6 道）→ LEAVE（3 道）+ `bx`。合計約 30 道，原廠只要 5–8 道。這些函式是記錄解析器的核心路徑，一次 Update 會被呼叫上萬次。不過只看指令數，解釋不了 37%。

**(b) 主因：程式碼在不可快取的位址上執行 [靜＋推]**

- 開機 MMU 表（`C000E7B0`，預設表 `C0725F38`）有兩個別名指向同一段物理記憶體：
  - **VA `0x40000000` 起 2 GB → PA `0x40000000`**，屬性 TEX=100 C=0 B=0，也就是 **Normal、inner/outer 都不可快取**。
  - **VA `0xC0000000` 起 1 GB → 同一段 PA**，屬性 inner/outer WBWA，可快取。
- 韌體配置器（loader 的 `mem_get`、uishare 的 `C001D740/C001D7F0`）回傳的都是 **`0x45xxxxxx`，也就是不可快取的那個別名**。00SHELL 在 `0x45051D80`，ALLSUPS 在 `0x45153E00`，70PERF 在 `0x45403420`。
- 在不可快取記憶體上執行時，I-cache 不會快取那些指令，每次取指令都直接讀 DRAM。層的標頭資料用 `adr hdr` 讀取，也是不可快取的讀取。所以這 30 道指令每一道都是 DRAM 延遲。
- 同一個原因也能解釋另一件事：**70PERF 的 NEON 模組在模擬器裡快 5–6 倍，上機反而變慢**，而且取樣幾乎都落在我們自己的碼上。模組本身沒錯，是在不可快取的位址上跑。
- **所有 sup 的常駐 hook 程式碼都有同樣的問題**，例如 gyro 在 MRecMgr 裡佔約 1.9%，LOSS 的 hook 也是。

## 3. 拿掉這個成本可以省多少 [推]

- 如果 hook 碼在可快取別名上執行，每次呼叫約 30 道指令、全部 I-cache 命中，比現在快數十倍，成本可以忽略。
- 依 37% 估算：
  - 開選單 Gui:Update 346 → 約 220 ms，整體約 430 → 300 ms。
  - 關選單 Update 482 → 約 300 ms。
  - 切分頁 Update 約少三分之一。
- 這是用整段 DrawMgr 時間的比例套到 Update 上，要上機量才算數。

## 4. 修法(都不改字串結果)

**A. 讓常駐程式碼從可快取別名執行（系統層，效益最大）[推]**
- 做法：配置後把位址換成 `block + 0x80000000`（`0x4xxxxxxx` → `0xCxxxxxxx`，同一段 PA），veneer 和尾呼叫目標都填這個位址。先對這段做 D-cache clean+invalidate，再 I-cache invalidate。
- 風險：同一段 PA 同時用可快取和不可快取兩個別名存取。區塊頭尾所在的 cache line 可能跟 heap 的 metadata 共用，被寫回時會蓋掉配置器用不可快取別名寫入的資料。
  - 對策：多要 64 B 的 padding，只把 64 對齊的內部範圍當成可快取區使用。
  - 另外要保證之後只透過可快取別名寫入這段資料。
- 範圍：
  - loader 的 sup 區塊（sloader.c `load_one`/`load_builtin`，給 entry 的 block）。
  - uishare `ui_pool.c` 的層區塊。
  - 70PERF 等所有在 heap 執行程式碼的 sup。
- 動到共用 loader 的預設位元組（記憶 shared-loader-default-bytes），**所有產品都要重新出**。uishare 部分也會改所有使用它的 sup。必須先上機證實屬性（見 §5），再跟使用者確認架構方向（flag-architecture-drift-early）。

**B. 只修層的程式碼（範圍小）**
- uishare 的層區塊改用可快取別名（作法和風險同 A），或把層碼放進 cave（`0xC072xxxx` 已可快取，但空間只有 3.9 KB）。
- 層碼加一個快速路徑：ENTER 之前就判斷「沒有 QS 也不在範圍內」，直接跳原廠規則，省掉 ENTER/LEAVE。不過在不可快取的情況下，指令數減半也只省一半。

**C. 沒人用私有字串時不掛這三個點**
- 只停用其他 sup 時，All Sups 頁本身仍需要私有字串，所以實際上一定會掛。治標用。

## 5. 上機驗證(建議順序)

1. **唯讀**確認屬性：TTBR0 頁表位於 `0x44300000`（開機寫入的位址，用不可快取別名讀）。讀 `[0x44300000 + 0x451*4]` 與 `[0x44300000 + 0xC51*4]` 兩個 supersection 描述子，預期前者 TEX=100、C=B=0，後者 TEX=101、B=1。
2. 對照實驗（不改 loader）：
   - 用 `callfn` 把同一小段計時迴圈分別放在 `0x45xxxxxx` 和 `+0x80000000` 執行，量 1 MHz 計數器的差，就能直接看出不可快取執行慢多少。
   - 或用 `perfctl` 把 70PERF 的某一個 veneer 改指向可快取別名，比較 nb 在兩個別名下的 DrawMgr。
3. 證實之後才改 loader/uishare，重出產品，再用 `ui_latency.py` 量開選單、關選單、切分頁的 Update 時間。
