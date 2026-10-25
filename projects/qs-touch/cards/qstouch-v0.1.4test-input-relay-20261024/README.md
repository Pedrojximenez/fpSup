# QS Touch SUP — native touch test

This is a real `FSB4` SUP for SIGMA fp Ver.5.02 and Loader v4 services v6,
with the shared fpSup page renderer enabled. It creates its own native page
and touch callback. It is not the browser preview or an ARM object file.

**This first build tests interaction only. FORMAT / DC / RES / FPS values are
private test values. They do not change recording settings.** The page says
`QS TOUCH TEST`, and every tile says `UI values only`.

## 開啟與操作

已使用相容 Loader v4 的卡只需新增 `fpSup/QSTOUCH.BIN`。UI 已包在同一顆 SUP，
不需要額外的 QS 頁面檔；相容的現有 AutoRun 與 LOADER 不需要為這顆 SUP 更新。
本機另附的完整測試卡內容供獨立測試使用；上機只加入自己的 SUP。

從 `MENU → SYSTEM → fpSup → QS Touch test` 開啟。

- 點磁磚選取；底列 `− / +` 或橫拖可調整本 SUP 的測試值。
- 雙點磁磚或點 `MORE`，在同一個原生 QS 頁面顯示該項的預設選項；點選項切換。
- 更多選項中上滑返回；主畫面上滑或點右上 `BACK` 返回 fpSup 選單。
- 長按約 480 ms 後拖到另一格，放手才換位。排序只留在本次開機的記憶體中。
- 多指取消本次操作；關閉頁面後，已由本 SUP 接手的接觸會等放手才交還原廠。

自製磁磚沒有吸附或淡入淡出。v0.1.4 保留已驗證選單頁的完整焦點／按鍵骨架，
移除其動畫播放請求；骨架的被動動畫資料和預留空間仍保留，本版不宣稱已優化記憶體占用。
移動取樣若沒有造成可見變化，不會重送整頁變數更新。

## 本版邊界

這是原生 SUP 接入的第一個測試階段，尚未取代原廠 QS 按鍵或實況頂端下拉入口。
目前只有一頁、四種自製磁磚與八個可放置位置；未加入添加／垃圾桶、背景透明度選項、
DC／RES 自訂寬高、設定保存或相機錄影服務。測試選項不宣稱相機支援那些錄影組合。
瀏覽器原型已有的完整編輯功能，不等於本 SUP 已具備。

觸控 observer slot 與 Tap to Zoom 使用同一位置，採獨佔宣告。
若它已被其他 SUP 接手，本模組會拒絕載入，不覆寫對方，也不自動停用其他 SUP。

v0.1.0/0.1.1 已上機：能載入，但精簡頁面開啟未通過；直接切頁診斷也未通過並出現 USB 逾時，均已撤下。
v0.1.2 改用原生焦點骨架、私有 QTG_ 變數與有效初始焦點，保留 13 個自己的繪圖物件。
上機能停留在頁面、收到觸控封包，但背景蓋住文字，而且原先的直接變數訂閱未觸發操作。
v0.1.3 僅離線調整繪圖順序；v0.1.4 合併順序修正與下述原生事件轉接，尚未上機。
LCD 最終繪圖、實體觸控接觸序列、頁面生命周期與主觀手感仍須驗證。
離線服務替代不驗證快取硬體、實際 GUI 排程或效能。

## Build and verify

Run from the research repository root, always into a new directory:

```sh
python3 -B projects/qs-touch/sup/build.py --out projects/qs-touch/build/qstouch-sup-only
python3 -B projects/qs-touch/sup/verify.py --out projects/qs-touch/cards/qstouch-recheck
```

The verifier builds a normal shared Loader v4 card, executes its exact
AutoRun / loader / SUP bytes in Unicorn, parses the private page with the
original NBU interpreter, and checks isolated broken source variants.
Missing Unicorn or firmware is an error, never a skipped success.

No custom loader, Fast provisioning, worker task, USB operation, card write,
recording command or publication is performed. Existing v4 loader and
`fpsup-ui` sources are imported without modification.

## Native integration

`touch_sup.c` includes the existing portable `qs_tiles` / `qs_tiles_touch`
core in a single position independent unit. All resident code, state, UI
strings and page resources belong to the SUP block, not loader staging.
The entry returns after installation. Failed partial UI registration keeps
the block alive because the native registry may already borrow pointers.

The pinned native `TouchOperationObserver::v1` slot `C0CFCCDC` originally
points to `C05131A0`. Its six-word input is first x/y, second x/y, timestamp
and the mapped gesture. Contact presence is derived from coordinate validity;
mapped gesture flags are not reinterpreted as DOWN/UP. The input task only
posts `QST_Touch` to the GUI queue. The firmware queue uses the **silent**
setter (`C055F8F0 → C05DC778`): bound components update, but a C subscriber is
deliberately skipped. The page's change-only `appVariableChangeEvent` copies
that integer to `QST_Input` through native `controlAppVariable`
(`C05F15E0 → C05DC7C8`, notifying setter). Only `QST_Input` has the operation
subscriber. Model/page work stays on the GUI thread. A page-opening tag
rejects old queued inputs. The alternating serial bit keeps repeated samples
distinct; integer-to-integer copying preserves all 32 packet bits.

The revised tests no longer deliver a silent raw post directly to its C
subscriber. They require the relay in the exact SUP page, execute original
silent/notifying setters and the copy action in a guarded native probe, and
check signed/high-bit packet values. Page scheduling and final drawing remain
explicit substitutes; this is not physical-touch verification.

The shared loader journals the slot before the SUP arms it. Resident data
and code are published before the pointer is installed, then published again.
Both idle and interaction power-off paths must restore the original pointer.
An unknown pointer is rejected before claim, so the loader's general stale
repair policy cannot silently overwrite an unrelated touch owner here.
