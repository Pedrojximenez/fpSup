---
name: fp-ui-add
description: SIGMA fp (Ver.5.02) 的 sup 怎麼用「添加」而不是「改原廠」來動選單與文字，才能和別的 sup 合併在同一張卡 —— fpSup/uishare：私有字串走套娃 hook（每個 sup 一層，掛在 C05E5B58/C05E61C8/C05E61E0，不複製、不掃字串池；STRBASE 把位移交給 sup 自己的資料）；整頁加一列（add_row，頁面複本 FSPG + 原廠座標插入）；清單加一個選項（add_option：CSV 經共用取檔處理器 C05E5BEC 追加列、上限 +1、摘要文字、開機時發 index）；FPUI 區塊格式與 ui_apply.c；UI 段落（build_section.py，任何 sup 用 --boot-bin 帶）；合併網頁怎麼放尾段與展開卡自帶的入口跳板；怎麼證明「單獨 = 今天、C = 參考、ARM 實跑、mutation」。凡是要給 sup 加選單列、加選項（解析度、COLOR、格率…）、加私有字串或圖示、讓兩個改 UI 的 sup 同卡、追「合併後別人的選單壞了／字形變回原廠／開機變慢」時用這份；原生 UI 本身的規則（CSV 怎麼寫、上限、donor 列）看 fp-native-ui。
---

> **設定區風險（2026-10-04 更新）**：加選項可能經由選單、QS、轉盤、hook 或 `mem set`
> 把原廠不支援的值存入設定區。原廠會在 loader 前讀取該值；使用者已指出現在有還原手段，
> 因此依實際值、故障症狀及還原流程評估風險，不再一律視為不可恢復。
> 上機前明確說明會保存什麼值，以及還原手段是否適用；條件未確認時，優先使用每次開機歸零的記憶體記號。
> 解析度 CUSTOM、14-bit 與 240 fps 的處理不同，詳見 `research/SETTINGS_AREA_FIRST_RULE.md`。

# 用「添加」動選單與文字

詳細技術筆記：`research/ui/UI_AND_STRINGS_BY_ADDITION.md`（格式、座標規則、證據等級）。
計畫與進度：`fpSup/uishare/MENU_MERGE_PLAN.md`（§10 狀態、上機清單）。原生 UI 規則：skill `fp-native-ui`。
**機制本身尚未上機（2026-10-03）**；依據的原生行為（整頁改指、CSV 執行期換、FSPL 池）都已實機。

> **Loader v4（2026-10-21 起）**：v4 的 sup 不用 uishare 套娃，改用 `fpSup/fpsup-ui`（每個 sup 自帶頁面包，loader 只擁有 fpSup 頁）；
> 從 fpSup 頁開自己的頁要用 `fpui_open(svc, 頁名)`＋`build_fp4.open_transitions`＋進場寫 `FT_Go = 0`，不要 `fpui_show`
> （會讓選單掉鍵，`research/ui/MENU_PAGE_SWITCH.md`）。sup 檔名 `<名>_v<版本>.BIN`（`loader-v4/names_v4.py`）。以下內容是 v3 的。

## 1. 先選對做法

| 你要加的 | 用 | 不要 |
|---|---|---|
| 私有字串（列名、變數名、標籤） | FPUI 區塊的字串（原廠有的帶 `stock_at`，其餘自動進本 sup 的**套娃層**，`uishare/NESTED_HOOKS.md`）；自己程式要用位移就 `options.hand_out` → `STRBASE` | 複製字串池、換 `reader+0x14`、`uis_intern`（舊做法）；寫死位移（如 `FFFFFFF2`） |
| 一整列設定（Lossless RAW 那種） | `add_row`：頁面複本 + 插入 donor 列的複製 | 換掉整頁；從別頁搬列（fp-native-ui §8b） |
| 清單多一個選項（解析度、COLOR…） | `add_option`：CSV 追加列 + 上限 +1 + 摘要 | 原地改 CSV 槽、佔死第 N 格、自己掛 H1 |
| 換一個圖示 | `FILE` + `FILE_SET`（借一個沒人用的原廠名） | 同名原地改（快取） |
| 選了之後要做什麼（錄影、增益…） | 留在 sup 自己的 hook | 放進 UI 區塊 |

## 2. 怎麼做

**Python（建置時）** —— `fpSup/uishare/ui/`：

```python
import sys; sys.path.insert(0, 'fpSup/uishare')
from ui import fpui, options as O, rows
blk = O.resolution('OG3K 3008x2000', 'OG3K')          # 或 O.color_raw(icon)
block = blk.encode()                                   # FPUI 區塊
pages, files, pool, res = O.run([block])               # 參考套用器跑整張映像：先看結果
```

新的選項清單照 `options.py` 寫一個 recipe：`hook_fv(blk)` → 每個 CSV（含 `_EXCL` 變體）`csv_file(...)`
→ 語意綁死 index 就 `EXPECT` → `page_ops()` 把**所有**同列數的上限 `ADDF +1`（`be_float_at` 找大端 float 的真正位置，常常沒對齊）
→ 摘要文字 `SETSTR_SLOT`。加列照 `rows.row_block()`（v1 從頁面建置器的整頁反推）。

**帶上卡**：
- 有自己的 C：把 `ui_pool.c` + `ui_apply.c` 編進去，讀區塊、呼叫 `uia_apply()`（Lossless `native/menu_page.c`）。
- 組語或不想動程式：`build_section.section(block)` → `--boot-bin FILE:0`；`info['sites']` 每個以**原廠字**做 4-byte `--also-bin`
  （stage2 journal、關機寫回）。raw-view：`build_rawview.py`；OG：`OG_UISHARE=1 build_og3k_gyro.py`。
- 區塊太大放 fpSup.BIN 尾段：位置 = 讀取上限 `max(0xF000, VBIN 結尾對齊 4 KiB)`，執行期從 VBIN 標頭算（合併網頁照同一規則放）。

## 3. 必守規則

1. **編號不事先佔**：物件 ID、選項 index、列的 Y、字串位移都開機時發。語意必須綁某個 index 就用 `EXPECT`，不符整個區塊不裝。
2. **原廠座標**：`INSERT`/`ADD` 一律用原廠頁位置；換算由插入表做。不要算「別人插入之後」的位置。
3. **改複本、最後才切換**：不寫韌體映像裡的 NBU／CSV（暖開機會留著、無法疊加）。
   **例外：沒證明過可改指的資源組**（`ColorModeAdvancedSettings` 已證明**不行**，複本不生效）——
   只改數值時原地寫，那個字以原廠字宣告成段落（stage2 journal、關機寫回）。已證明可改指：MainB2、B2_5。
4. **比字串用位移，不用絕對位址**：舊 sup 一附加字串，UI 就改用池副本。（raw-view `stub_ai` 曾因此在合併卡顯示 −5/+5。）
   私有字串的位移 ≥ `0x40000000`，只有經過 `C05E5B58` 才找得到，不要自己拿 `reader+0x14` 加位移去讀。
5. **共用站點只裝一次**：`C05E5BEC` 已是別人的程式（不是 FSHK）就退讓（`UIA_HOOK`），不要搶。
6. **相機端 C**：只有 `.text`、無重定位；不要結構指定（→ memcpy）、不要除法（→ `__aeabi_uidiv`，A9 沒有硬體除法）、不要浮點。
   **不要逐 byte 搬大塊記憶體**：原廠頁起點常沒對齊；複本保持來源的對齊、整字搬（`move()`）。逐 byte 搬 160 KB 在開機看得出來。
7. **檢查持久設定**：確認新選項會存入的值、原廠讀取時機、可能症狀與適用的還原流程；
   條件未確認時，優先把自訂狀態放在記憶體記號。已驗證的 CUSTOM 與 14-bit 依各自的紀錄處理。
8. **新的共用掛鉤點用套娃，不用複本**（`uishare/NESTED_HOOKS.md`）：只套 leaf、每層只答自己的、
   r0–r1 原樣往內傳、只動原廠函式會動的暫存器、最內層自己重寫原廠行為、不認得的 hook 就退讓、
   掛鉤點以原廠字宣告成 4-byte 段落。頁面（記錄解析器）還沒有套娃版本，見該筆記 §6。

## 4. 證明它對（照這個順序）

```sh
cd fpSup/uishare && python3 -B -m unittest test_ui_pool test_ui_apply test_options test_ui_strings   # ~20 s，含 mutation
cd fpSup/lossless && python3 -B native/test_menu_page.py && python3 -B test_card_emulation.py
cd projects/rawview/build && python3 -B -m unittest test_rawview_image test_rawview_build
OG_UISHARE=1 python3 -B projects/open-gate/build/test_boot_entry_chain.py
OG_TARGET=og3k python3 -B projects/open-gate/build/test_og_nested_strings.py   # og2k likewise
python3 -B fpSup/tools/card-composer/build_catalogue.py && (cd fpSup/tools/card-composer && node test_compose.js)
```

- **單獨 = 今天**：新做法單獨套用的結果要和今天上機過的位元組相同（頁逐位元、CSV 逐格）。這是改架構不增加相機風險的關鍵。
- **C = 參考**：C 與 `fpui.apply` 逐位元相同，含多個 sup 任一順序。
- **ARM 實跑**：卡上真正的位元組在 unicorn 跑真映像（skill `fp-unicorn-emulation`）。第一次就過要做一次 mutation 證明測試會失敗。
- 測試讀相機表格時，大小超過 1 MB 就當壞表，不要照著讀（mutation 會把位址當大小，讀 2.6 億 bytes 卡 40 分鐘）。
- **速度要另外測**：結果正確的退化（整字退回逐 byte）比對測試抓不到 → 數 byte 讀取次數（`test_the_page_is_moved_a_word_at_a_time`）；
  量指令數：unicorn 計數（raw-view 啟動器 970 萬、UI 段落 9.5 萬，2026-10-03）。

## 5. 症狀對照

| 症狀 | 先查 |
|---|---|
| 合併後某個 sup 的選單文字／字形變回原廠 | 它是不是用絕對位址比對原廠字串（§3 規則 4） |
| 加了 sup 後開機慢了好幾秒 | 有沒有不帶提示的 `uis_intern`（每個字串 ~0.25 s）；有沒有逐 byte 複製大頁（看 byte 讀取數／指令數） |
| 選項列在、但它的進階頁（「更多選項」）不見 | 那個字是不是改在沒證明過的資源組複本裡（ColorModeAdvancedSettings 不行）→ 原地寫 |
| 一個 sup 的 UI 完全沒裝 | `uia_outcome.result/op`：GUARD（頁不是預期的）、HOOK（站點被別人佔）、EXPECT 不符、PAGE |
| 選項列出現、選不到 | 有一個上限沒 +1（fp-native-ui §2 規則 9） |
| 合併卡某個 sup 的入口沒被呼叫 | 那張卡自帶入口跳板，合併網頁有沒有展開（`ownTrampoline`） |
| 舊版 raw-view 與新版 OG 同卡 RAW 全不見 | 舊 raw-view 守衛 H1，被共用處理器佔了 → 用 v0.2.3test 以上 |
