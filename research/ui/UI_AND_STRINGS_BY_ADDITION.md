# UI 與文字：用「添加」合併 —— 技術筆記

2026-10-03。Ver.5.02（`out/MAIN_c0000000.bin`，與 `out/seg0_c0000000.bin` 前綴相同）。
程式在 `fpSup/uishare/`；計畫與進度 `fpSup/uishare/MENU_MERGE_PLAN.md`；為什麼這樣設計 `research/ui/MERGE_BY_ADDITION.md`。
操作手冊是 skill `fp-ui-add`；原生 UI 本身的規則是 skill `fp-native-ui`。

證據等級：**[實機]** 相機上量到、**[模擬]** unicorn 跑真映像、**[離線]** 主機測試／反組譯、**[推論]** 沒驗過。
**本筆記描述的機制本身全部是 [離線]/[模擬]，尚未上機**（上機清單見 §11）。

---

## 1. 問題：大家都在改「原廠只有一份」的東西

| 單一位置 | 以前誰在搶 | 後果 |
|---|---|---|
| 字串池 `reader+0x14` | Lossless 換成自己的複本；OG 別名 hook 只認原廠池 | OG 選單壞 [實機 09/30] |
| 一頁的執行期項目 `entry+08` | Lossless 換整頁 MainB2 | 第二個想在 MainB2 加列的 sup 只能二選一 |
| 清單 CSV（槽長固定）與它的上限 | raw-view 整檔換 COLOR 三個 CSV；OG3K/OG2K 都寫第 3 格 | 互斥 |
| 取檔位置 `C05E5BEC`（H1） | raw-view 獨佔 | 別人無法改 CSV |
| 用**絕對位址**認原廠字串 | raw-view `stub_ai` | 同卡有附加字串的 sup → SA/GA 框顯示 −5/+5 [實機 10/03] |

解法：每一種共享資源都變成「原廠 + 附加清單」，帶自我描述標頭，第一個需要的 sup 建立可擴充複本，之後的 sup 找到標頭接著加。
**編號（物件 ID、列號、選項 index、字串位移、列的 Y）一律在開機時發，不事先佔。**

---

## 2. 文字：共用字串池（FSPL）

### 2.1 原廠怎麼解字串 [實機]

NBU 記錄裡的字串欄位是**相對字串池的位移**（大端）。所有畫面共用一個 reader：
`reader+0x14` = 池位址（原廠 `0xC18C0474`）、`reader+0x10` = 長度（原廠 176,152）。
`C05E5B58` 檢查 `offset < reader+0x10`，位址 = `reader+0x14 + offset`；`C05E61C8`/`C05E9008` 對落在池內的指標借用、池外的複製。

### 2.2 約定（`fpSup/uishare/ui_pool.{h,c}`）

- `uis_intern(s, n, &off)`：池裡已有 `s\0`（任何位置，包括是別的字串的結尾）就回傳該位移；否則附加。
- 第一次附加時把原廠池**整份複製一次**（多 16 KiB 空間、永不釋放），切換 reader（先指標、後長度）。
- 標頭在池前 16 bytes：`"FSPL" | 版本 1 | 容量 | 0`；`reader+0x10` 永遠是使用中長度。
- 原廠位移在副本裡**不變**；附加的字串 4-byte 對齊開始；只附加、不移動、不刪。
- 空間不夠就配一份更大的副本、舊的留著（UI 可能還借著舊池的字串）。
- 池既不是原廠也不是 FSPL → 拒絕，只缺這個 sup 的字串，其他不動。
- 自己的程式會檢查池的 sup（OG 的 `ui_string`）要接受「原廠池 **或** `uis_pool_known()`」。OG3K ≥ 0.2.8a、OG2K ≥ 0.1.5a 已接受 [離線，FSPL 路徑隨 Lossless 卡實機]。

### 2.3 開機成本與提示（`uis_intern_hinted`）

- 不帶提示時，每個字串都把 17 萬 bytes 原廠池逐字比一遍；實機量到約 **0.25 s／字串**（Sensor Lab 80 個字串多 ~20 s）[實機]。
- 建置時就知道原廠池（釘死映像），所以每個字串帶 `stock_at`：
  - `stock_at` = `uis_intern` 會在原廠池第一個找到的位置（`s` 後接 NUL）→ 執行期只核對 n+1 bytes，錯了退回完整掃描；
  - `UIS_NOT_STOCK`（0xFFFFFFFF）→ 只在附加區（原廠長度之後）找。
- 計算：`fpSup/lossless/menu/pack_menu_file.py stock_at()`（Python `bytes.find(s + b'\0')`）。
- 驗證：Lossless 的 `xxx` → 0x2A5C4、`Footer05` → 0x12BC4，和 10/01 相機上沿用的原廠位移相同 [離線 ↔ 實機]。
- 提示與不提示的呼叫者得到相同位移（測試釘住）。

### 2.4 陷阱

- **不要用絕對位址認原廠字串**。別的 sup 一附加字串，UI 解出來的名稱指標就在副本裡。比「目前池（`reader+0x14`）裡的位移」：
  raw-view v0.2.3test 的 `stub_ai` 就是這樣修的（讀 `[C37B7048]→app+0x8C→[0]→+0x24→+0x14`，讀不到退回原廠池）。
- 字串欄位寫進頁面要在**頁面被解析之前**；頁面被解析後才附加的字串不影響已解析的物件。
- 名字不必唯一（原廠 220 頁中 165 頁有同名兄弟物件）；能沿用原廠池裡已有的字就沿用。

---

## 3. 頁面：共用頁面複本（FSPG）

### 3.1 依據 [實機]

整頁 NBU（MainB2、B2_5 等有執行期項目的資源組）每次顯示時由 `reader+24 + entry+08` 重新解析；
把 `entry+08` 改成 `(自己的頁 − 0xC18C0460) mod 2^32`，下一次顯示就讀你的頁（MainB2 09/30、B2_5 10/02）。
資源組清單與原廠位移：`research/ui/nbu_sets.json`（221 組；長度 = 下一組起點 − 本組起點）。

**不是每一組都能這樣改指** [實機 10/03]：`ColorModeAdvancedSettings`（COLOR 的 AEL 細部頁）用複本改 MenuMode 範圍沒生效
（raw-view v0.2.3test 首版「更多選項」不見），同一個字在韌體映像裡原地改（v0.2.2test、bCOLOR）有效。
已證明可改指：MainB2、B2_5 [實機]；ColorButtonMenu [待上機確認]。
**沒證明過的組，只改數值時就原地寫**（把那個字以原廠字宣告成段落 → stage2 journal、關機寫回），不要做複本。

### 3.2 複本與座標

- 每個 sup 套用時都**另做一份新複本**（從「目前的頁」複製：原廠頁或別人的複本），全部改完才切換 `entry+08`。
  失敗時現用的頁完全不動。舊複本不釋放。
- 頁前 128 bytes 標頭：`"FSPG" | 版本 1 | 容量 | 長度 | 原廠長度 | 下一個物件 ID | 插入數 | 插入容量 | 插入表位址 | 8 組計數器 {名稱雜湊, 值}`。
- 所有指令都用**原廠座標**。插入表 `{原廠位置 q, 長度 n}` 把原廠位置換算成目前位置：
  `current(p) = p + Σ n（q ≤ p 的每筆插入）`；在 q 的新插入落在之前所有 q 插入的後面 → 同一點的修改依載入順序疊起來。
- 物件 ID：`PAGE` 帶「原廠下一個 ID」（原廠最大 ID + 1）與這個 sup 要的本地 ID 數；複本記住下一個 ID。
- 計數器（`ALLOC`）：例如 `MainB2.rows`，第 k 個加列的 sup 拿 `base + step·k`（Lossless：Y = 243 + 81·k）。

### 3.2b 複製的成本 [模擬 10/03]

新規則要「改在複本上、最後才切換」（全有或全無、可疊加、每次開機從原廠開始），代價是每頁複製一次。
原廠頁的起點常常沒對齊（ColorButtonMenu 從 …AA6 開始），只在「來源和目的都對齊」時才整字搬，結果整頁逐 byte：
raw-view 的 UI 段落 71 萬條指令。改成**複本起點與來源同一個對齊**（FSPG 標頭放在 `(頁 & ~3) − 128`）、插入搬移也整字（插入長度都是 4 的倍數）
→ 9.5 萬條；Lossless 套 MainB2 的 byte 讀取 21.7 萬 → 6.3 萬（剩下的是 30 KB 區塊的校驗與片段）。
只改數值、不插入記錄的話，還可以不複製（見上：原地寫 + 宣告段落），代價是兩個 sup 改同一個字時要有累加約定（未做）。

### 3.3 加一列（add_row）要改的東西 [離線，與實機頁面逐位元相同]

以 Lossless（複製同頁「音訊記錄」列，`build_menu_candidate.py --profile audio-toggle`）為例：

| 改什麼 | 怎麼表達 |
|---|---|
| 複製的 23 個物件、27,456 bytes 記錄，插在 donor 列之後 | `INSERT`；欄位重定位：物件 ID（LOCAL_ID）、私有字串（STRING）、列的 Y（SLOT_F32） |
| 頁首 `0x10002`：物件數、各元件種類計數、群組／clip 屬性／key 三個預算陣列各在尾端追加 | `ADD32` 計數 + 在各陣列尾端 `INSERT`；頁首記錄長度 `ADD32` |
| 父物件（B2）子數量 | `ADD32 +1` |
| ModeChange 根清單追加 `{新根, 1}` | `INSERT`（LOCAL_ID）+ 數量 `ADD32` + 記錄長度 `ADD32` |

順序無關（座標換算處理位移）；兩列疊加後子數量、物件數、ModeChange 都一致 [離線]。
頁首預算陣列原廠只拿總和配置 arena（`C05E6400` 靜態追蹤），所以追加在尾端即可 [離線；配置是否成功只有實機知道]。

---

## 4. 清單與檔案：共用取檔改指表（FSFV）

### 4.1 依據

CSV（`.cvm`）在 NBR 容器 `0xC0D22400`；NBR 目錄開機後就失效（改指沒用）[實機]，但「取檔位置」可以在執行期換：
`FUN_c05e5bb8` 結尾 `C05E5BEC adds r0,r0,r1; str r0,[r5,#4]`，大小在 `[sp]`。raw-view 的 H1 在這裡換掉檔案 [實機 09/25–27]。

### 4.2 共用處理器（`fpSup/uishare/fv_handler.S`）

- 第一個需要的 sup：從 cave bump 配置器拿 8 bytes 當 Thumb veneer（`ldr.w pc,[pc,#0]` + 處理器位址），把 `C05E5BEC` 改成 Thumb B.W 到 veneer。
  處理器區塊前 16 bytes `"FSHK" | 1 | 表位址 | 0`，表 `"FSFV" | 1 | 數量 | 容量 | {原廠位址, 複本位址, 大小}…`（容量 32）。
- 之後的 sup：解 B.W → veneer → 處理器 → 驗 `FSHK` → 取表，只加表項。站點是別人的程式（例：舊 raw-view 的 H1）→ `UIA_HOOK`，不動。
- 處理器：先做原本的 adds，查表；命中就換位址並把大小寫進 `[sp]`；然後原本的 str，回 Thumb `C05E5BF0`。可用 r1–r3、ip [模擬]。
- 站點 `0xC05E5BEC`（原廠字 `0x60681840`）必須在卡上以 4-byte 段落宣告原廠字 → stage2 journal、關機寫回。

### 4.3 CSV 追加（add_option）

- `FILE 原廠位址, 大小, 預留` → 取「目前的檔」（表裡的複本或原廠檔）做新複本。
- `CSV_ADD 模板` → 附加一列；`{N}` = 加完後的列數（新列的編號）、`{P}` = N−1、`{Q}` = N−2；沿用檔案的行尾（CRLF 或 LF），最後一列沒行尾就先補。
  **新列的 0-based index（加之前的資料列數）存成 slot**：這就是開機時發給這個 sup 的選項 index。
- `CSV_CELL 列, 欄, 模板` → 改一格（列：0 = 第一列、1 = 這個 sup 加列之前的最後一列；欄依表頭 0-based）。
- `FILE_SET` → 整檔替換（圖示借名）；別人已換過同一檔 → `UIA_CONFLICT`。
- `EXPECT slot, 值` → 這個 sup 的語意綁死某個 index 時（raw-view = 16、OG = 2），不符就整個區塊不裝。

### 4.4 選項的其他部分

- 清單的上限（controller max，**所有**同列數的上限都要 +1，含動畫 key）、COLOR 的文字群組終點（+33/列）→ 在資源組的頁面複本 `ADDF`／`ADD32`。
  只限已證明可改指的組（§3.1）；sup 自己語意的字（raw-view 的 AEL 範圍）留在 sup 啟動器原地寫。
- 收合摘要文字 → `SETSTR_SLOT`：依發到的 index 選原廠欄位位置，寫入 intern 的字串位移。
- 浮點都是「整數值的大端 float」；相機端不用浮點運算（自寫轉換）。

---

## 5. FPUI 格式（`fpSup/uishare/ui/fpui.py` 是規格與參考實作）

容器小端：`"FPUI" | 1 | 總長 | FNV-1a(0x20..) | 字串數 | 指令字數 | 片段長 | 0`，接字串表 `{stock_at, n, 字串\0, 補 4}`、指令、片段。
字串的 `stock_at`：原廠位移 / `0xFFFFFFFF`（不在原廠池）/ `0xFFFFFFFE`（名稱，不 intern：頁名、模板、計數器名）。

| 指令 | 參數 |
|---|---|
| `PAGE` | 名稱#、原廠項目位移、原廠長度、原廠下一個 ID、本地 ID 數、插入總長、插入數 |
| `GUARD` | 原廠位置、預期大端字 |
| `INSERT` | 原廠位置、片段位移、長度、重定位 `{kind<<24\|arg, 位移}`（LOCAL_ID / STRING / SLOT_F32 / SLOT_U32） |
| `ADD32` / `ADDF` | 原廠位置、增量 |
| `ALLOC` | 計數器名#、base、step |
| `DONE` | （頁完成；最後統一切換） |
| `HOOK_FV` | 站點、原廠字、表容量、處理器片段位移／長度、入口位移、cave bump、arena 終點、veneer 字、表字位移 |
| `FILE` / `CSV_ADD` / `CSV_CELL` / `FILE_SET` / `FILE_DONE` | 見 §4.3 |
| `EXPECT` | slot、值 |
| `SETSTR_SLOT` | slot、base、n、字串#、n 個原廠位置 |

**全有或全無**：整個區塊成功才提交 —— 先寫出快取，再把檔案表項加上（新項：位址、大小、發布、數量+1；舊項：先換指標再換大小），
再發布，最後切所有頁的 `entry+08`、發布。任何失敗：UI 原樣（已裝的 hook 例外：空表的處理器是透明的）。

---

## 6. 相機端（`fpSup/uishare/ui_apply.c`）

- `uia_apply(block, bytes, &outcome)`：outcome 有結果碼、失敗的指令、第一個物件 ID、發到的 slots。
- 結果碼：OK、BLOCK（不是 FPUI v1／損壞）、NO_UI、PAGE（頁既非原廠也非 FSPG）、GUARD、NO_MEMORY、STRING、OP、FULL、HOOK、CONFLICT。
- 編進相機程式的限制：只有 `.text`、沒有重定位；**結構指定會變成 memcpy、除法會變成 `__aeabi_uidiv`**（Cortex-A9 沒有硬體除法）→ 逐字複製、用減法轉十進位。
- 搬記憶體：來源與目的同對齊就整字（`move()`），頁面複本保持來源的對齊；FSPG 標頭在 `(頁 & ~3) − 128`。
- 從 entry 呼叫（loader 的 task），不要從 hook。

## 7. 一個 sup 怎麼用

| 情況 | 做法 |
|---|---|
| 自己有 C 程式（Lossless） | 把 `uishare/ui_pool.c` + `ui_apply.c` 編進自己的單元，讀自己的 FPUI，呼叫 `uia_apply` |
| 組語或不想動程式（raw-view、OG） | `build_section.py section(block)` → 一個 destination-0 段落（`section.S` 入口 + 套用器 ~7 KB + 區塊），`--boot-bin FILE:0`；`info['sites']` 每個都以原廠字 `--also-bin` 宣告 |
| 區塊放哪裡 | 小的放段落裡；大的（Lossless 30 KB）放 fpSup.BIN 尾段，位置 = 這張卡的讀取上限（`max(0xF000, VBIN 結尾對齊 4 KiB)`），從 VBIN 標頭算 |

Python 端：
- `ui/rows.py row_block()`：從頁面建置器的整頁 + manifest 反推「加了什麼」（v1）。
- `ui/options.py`：`color_raw(icon)`（COLOR 第 17 列 RAW）、`resolution(標籤, 摘要)`（解析度 state 2）、`csv_file()`、`page_ops()`、`hook_fv()`、`run()`（參考套用器跑整張映像）。

## 8. 合併網頁

- 尾段：放在合併後的讀取上限（Lossless 單卡 0xF000；五合一 0x1A000）。
- 一張發布卡有兩個以上入口（自己的 payload + UI 段落）時帶 build_autorun 的入口跳板：網頁認出跳板（程式碼與 `entries.S` 相同）、
  讀表、把每個入口併進合併卡的入口表、丟掉那張卡自己的跳板。Python 重現檢查（`own_trampoline`）同步。
- OG 的 UI 段落在 restore 之前跑（UI → restore）。

## 9. 驗證方式（每一層都要能失敗）

1. **單獨 = 今天**：每個改寫，單獨套用的結果要和今天上機過的位元組相同（Lossless 頁逐位元；raw-view 三個 CSV 逐格、圖示、9 個頁面字逐位元；OG 解析度三列逐格、List 上限、摘要文字）。
2. **C = 參考**：同一批區塊，C（主機，真 NBU）與 Python 參考逐位元相同，含三個 sup 任一順序（`test_ui_apply`、`test_options`）。
3. **ARM 實跑**：卡上真正的位元組在 unicorn 跑真映像（Lossless `MenuEmulationTests`；raw-view `test_rawview_image` 從真的 H1 站點經共用處理器拿到組好的 CSV）。
4. **mutation**：每個保證都有一個會被抓到的破壞（uishare 50 項測試含 ~25 個 mutation；Lossless 選單 17 個）。
   兩個防線刻意不列 mutation：B.W 符號位（cave 永遠在站點之後）、veneer 字檢查（FSHK 檢查已涵蓋）。
5. **速度也要有測試**：結果正確的退化（整字退回逐 byte）比對測試抓不到 → 夾具數 byte 讀取次數，套 Lossless 區塊必須 < 12 萬
   （`test_the_page_is_moved_a_word_at_a_time`；「複本對齊錯」mutation 會讓它變 21.7 萬）。

## 10. 已知限制

- **QS 沒通用化**：OG 的 360 筆 QS 記錄仍走自己的 `C05E6400`（目前只有 OG 用）。
- **OG 的字串別名 hook `C05E5B58`** 仍在（接受 FSPL）；要拿掉得把 ui_record 表改成 32 位元位移。
- **OG3K + OG2K 同卡**：UI 可並存，但錄影核心 88 段同位址、都用 enum 4。
- **選項值**：解析度只有一個原廠備用值（enum 4 ↔ state 2）。超過就要「原廠合法值 + 記憶體記號」與轉換表擴充（未做）。
- **第一守則待決**：OG 存解析度 4（CUSTOM）+ OGSAVE；raw-view 關機存色彩 0x10–0x17。都是既有行為。
- **未上機**：ColorButtonMenu 的頁面複本、CSV 經共用處理器（raw-view 自己的 H1 已實機）、兩個 sup 疊同一頁。
- **已知失敗**：ColorModeAdvancedSettings 的頁面複本不生效 [實機 10/03] → 改回 raw-view 原地寫（v0.2.3test 重建）。
  合併卡（舊 raw-view v0.2.2test + Lossless + OG3K + gyro）上「更多選項」也不見，原因未確認。
- **開機時間**：raw-view 的大頭是啟動器產生 124 張表（970 萬條指令，GitHub 版相同）；UI 段落現在 9.5 萬條。

## 11. 上機清單

`projects/uishare/cards/uishare-2026-10-03/`（合併網頁離線組，帶 shell + FS2）：
01 Lossless、02 raw-view、03 OG3K、04 五合一。看什麼見 `MENU_MERGE_PLAN.md` §10。
