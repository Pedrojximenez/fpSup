# fpsup-ui —— v4 sup 自己的選單頁

給 loader v4 的 sup 用的頁面函式庫。它做的事和 v3 的 uishare 相同：載入頁面包、讓頁面能用私有字串、
登記變數、註冊頁面。差別是**不處理共用**：沒有套娃層、不搜尋字串、不複製字串，也沒有字串數或檔案數的上限。
（使用者 2026-10-21 定案）

## 分工

| 誰 | 負責 |
|---|---|
| LOADER.BIN | fpSup 頁（SYSTEM 第 6 頁）的主人；開機一開始就掛好兩個固定規則的 hook（見下）；提供 `file_read`、`borrow` |
| 你的 sup | 用這個函式庫裝自己的頁；要放設定列到 fpSup 頁就用 `svc->page_add` |
| 容器 sup | 多個 sup 要改**同一個原廠位置**時，由它們上面的容器 sup 協調（例如 res-custom）；loader 不管 |

自己的頁不礙到別人，就不需要任何協調。

## 用法

```c
#include "sloader4.h"
#include "fpsup_ui.c"            /* build_v4 已把 fpSup/fpsup-ui 加進 include 路徑 */

int sup_entry(void *block, const struct sl_svc *svc, const char *path)
{
    const void *ui = fpui_read(svc, "\\fpSup\\UI\\MINE.BIN");   /* 路徑要常駐 */
    if (ui && !fpui_install(svc, ui)) {
        fpui_watch(ui, MY_KEY, &my_key_changed);     /* UI 執行緒呼叫 */
        fpui_set(ui, MY_VALUE, 3);
    }
    return SL_KEEP;
}

static uint32_t my_key_changed(uintptr_t desc)
{
    uint32_t v = fpui_value(desc);
    ...
    fpui_show("FT_MINE");                            /* 只能在 UI 執行緒；fpSup 頁的列請用 fpui_open */
    return 0;
}
```

在 entry 裡就能直接裝，不用等其他 sup：loader 的 hook 在任何 sup 載入前就已經掛好。

| 函式 | 作用 |
|---|---|
| `fpui_read(svc, path)` | 讀頁面檔到自己的記憶體（快取別名、64 bytes 對齊）；失敗回 0 |
| `fpui_install(svc, ui)` | 填字串編號、`borrow`、登記變數、註冊頁面與狀態機；0 = 成功 |
| `fpui_text(ui, i)` | 第 i 段固定文字 |
| `fpui_first(ui, i)` | 第 i 個變數的初值 |
| `fpui_set(ui, i, v)` / `fpui_set_text(ui, i, s)` | 推數值／文字（文字指標要常駐） |
| `fpui_watch(ui, i, fn)` + `fpui_value(desc)` | 頁面改了第 i 個變數時在 UI 執行緒呼叫 `fn(desc)` |
| `fpui_open(svc, name)` | fpSup 頁 JUMP 列的 `open()` 裡用：走原廠狀態機換到這一頁（loader 服務表 v7 `ui_go`）；沒有 v7 時退回 `fpui_show` |
| `fpui_show(name)` | 直接設畫面（UI 執行緒）。**之後選單會吃掉快速連按的鍵，直到退出選單**（2026-10-25 實機），只在沒有別的路時用 |

變數和文字都用**編號**，順序就是 `uishare/tab/build_fp4.py` `ft4_file()` 拿到的順序；sup 不需要知道檔案格式，
也不需要任何韌體位址。錯的 `ui` 或越界編號什麼都不做（文字回 0、`fpui_watch` 回 `SL_BADARG`）。
`fpui_install` 的錯誤碼：1 不是頁面檔、2 不在快取別名、3–7 GUI 還沒好、8 字串索引超出、9 borrow 失敗、10 變數登記失敗。

## 規則

- 頁名用 `FT_` 開頭，才會借到 MainY5 的 GUI 編號（loader 的頁面 hook 認 `FT_` 前綴）。
- 變數名不要和別人撞（用自己的前綴，例如 SupManager 用 `SM_`）。
- 從 fpSup 頁打開的頁面（JUMP 列）：
  - `open()` 先推好頁面變數，最後 `return fpui_open(svc, "FT_MINE")`。
  - 頁面包要有轉換 `build_fp4.open_transitions("FT_MINE")`（FT_Y6 → FT_MINE，request = 頁名）。
  - 頁面進入時要寫 `FT_Go = 0`（`manage_page.enter_write(pg, GO_VAR, 0)`；`build_manage(v4=True)` 已內建）。
  - 原理：loader 在 `open()` 之後才推 `FT_Go`，fpSup 頁的「變數改變」事件再送原廠 request，
    所以頁面建立時 `open()` 推的焦點與可見度都已生效；直接設畫面或按鍵當下送 request 都太早或會掉鍵。
- **不要自己掛** `0xC05E5B58` / `0xC05E61C8` / `0xC05E61E0`（loader 獨佔）；要顯示文字就放進自己的頁面檔。

## 字串怎麼運作

頁面裡引用字串的地方，安裝時被填成「那段文字的位址 − 0x80000000」（同一塊記憶體的非快取別名 0x4…）。
loader 的解析 hook 只認一條規則：編號在 `[0x40000000, 0x80000000)` 就回傳「編號 + 0x80000000」，
其餘照原廠規則（原廠字串池位移都遠小於 0x40000000）。所以 loader 不需要知道任何 sup 有哪些字串。
唯一要告訴 loader 的是「哪段記憶體放著這種字串」（`svc->borrow`），讓韌體釋放字串時不會去 free 它。

開選單 Gui:Update 實測從 uishare 套娃的約 480 ms 降到約 192 ms（projects/sys-perf/README.md，字串 hook A/B）。

## 檔案

- `fpsup_ui.c`：函式庫本體（`#include` 進 sup，-fropi 單一單元）。
- 頁面資料由 `fpSup/uishare/tab/build_fp4.py` 產生（magic `FT4S`，17 字檔頭）。
- 測試：`fpSup/loader-v4/test_ui_v4.py`（`FpuiLibraryTests` 用 `test_fpui_probe.c` 像第三方 sup 一樣呼叫它）。
