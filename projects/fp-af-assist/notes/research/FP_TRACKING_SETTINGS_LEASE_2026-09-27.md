# 原廠 Tracking baseline：設定、模式與還原邊界

2026-09-27；離線核對本地 Ver.5.02 反編譯與 ROM，未開 socket、未操作相機。供一次受控原廠半按試驗使用，沒有解除舊 collector 的 live 安裝阻擋。

ROM：`out/seg0_c0000000.bin`，base `C0000000`，SHA-256 `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`。

## 指令與模式

| 原生 shell 指令 | handler | 無參數 | 一個十進位參數 |
|---|---|---|---|
| `menu SetRecMode` | `C03FAA90` | `C0058340` 讀 CinemaMode | 走 `C0058308`；本次只需要 getter，並未完整稽核切換整機模式副作用 |
| `menu SetFocusMode` | `C03FC0E0` | `C0059D18` | `C0059CE0(value, notify=1)` |
| `menu SetFocusArea` | `C03FC150` | `C0059DE8` | `C0059DB0(value, notify=1)` |
| `menu SetFocusAreaSize` | `C03FC1C0` | `C0059EB8` | `C0059E80(value, notify=1)` |
| `menu SetFocusPosition` | `C03FBFE0` | 回 `x y width height` | **四個**十進位參數，走原廠 clamp/snap 與通知 |

以上 no-arg 分支是不要求變更使用者設定的 getter；仍可能 lazy-init 或更新 menu cache，不能稱為沒有任何內部 RAM 寫入。

原廠 STILL Tracking 所需 menu enum 是 **FocusMode=1（AF-C）、FocusArea=3（Tracking）**。不能把 applied AF area enum 與 menu enum 混用：`MenuItemFocusArea::v3 C00A31E0` 把 menu 0/1→applied 1、menu 2→applied 4、menu 3→applied 3（特殊 +58C gate 非零則 applied 1）。後者 applied 3 才由 `C05A8850` 的 tracking gate 使用。

`MenuItemFocusMode_w71c1::v8 C008B310` 判斷鏡頭 AF/MF 能力、MF 優先與 CinemaMode。ROM `C008B3DC..3EC` 確認 CinemaMode=1 且要求 FocusMode=1 時，effective mode 變成 0。`C008B400` 將 FocusMode=2 對應 MF storage flag。AF 控制 `C028EAB8` 的 continuous request case 4 也只接受 applied FocusMode=1；`C00A3118` 將有效 menu 值原樣寫到 applied +1BC。

`MenuItemFocusArea_w71c1::v8 C008B520` 在 effective FocusMode=0 時不允許 Tracking：ROM `C008B6A0..6F4` 明確將要求 area 3 轉成 2；MF mode=2 時 area>1 則變成 0。因此準備順序必須是 **先確認 STILL，再 FocusMode=1，讀回 1，再 FocusArea=3，讀回 3**。無法讀回所需值就停止，不改 raw applied 欄位繞過限制。

## 不呼叫 getter 的固定 CinemaMode 讀取

- Menu storage base **B=C31AE3B0**，initialization guard **C31AE3A8**；ROM `C008ACF0..AD38`。
- factory vtable `[C07397D8+10]=C00842F8`，返回 factory+24；對應 menu item id 2（CinemaMode）。
- item accessor table `[C07461DC+2*4]=C00B4C38`。ROM `C00B4C44..54` 取得 B 後相加 **11E00**。
- 故 stored CinemaMode 為 **C31C01B0，u32**。0=STILL、1=CINE。未知值不作有效模式；guard 未初始化時不推論。
- `MenuItemCinemaMode::v3 C0092FF0` 把非零 CinemaMode 轉為 applied +44=1；特殊 +5B4 gate 非零會強制 applied +44=0。因此 stored 值與有效 applied 值不可無條件等同。可用已稽核 no-arg `menu SetRecMode` 交叉檢查；它也不能取代所有 runtime capture guards。
- 不要使用銀行選擇 byte `C31B954C` 來判 STILL/CINE；它的角色是 menu storage bank 選擇，非 CinemaMode enum。

上述固定值的 ROM 稽核只支持讀取；不是 raw setter 或整機模式切換授權。

## 原廠 setter 的副作用

模式 setter 路徑：`C0059CE0 → C0067F28 → C0076CF8`。
區域 setter 路徑：`C0059DB0 → C0067C48 → C0076BA8`。

兩者先呼叫 native vtable+2C 寫 storage，再因 shell notify=1 呼叫 +34；mode 的 +34=`C008BD18`，area 的 +34=`C008BCF0`，都進入 `C0091288 → C00912F8 → C0091050` 的設定套用，再以 `C0021C50 → C0021E78` 通知 UserSetting observers。來源中沒有直接 `S1ON` 或 TouchAF dispatch，但既有 AF-C／PreAF observer 可能反應，所以設定切換也應在授權鏡頭操作範圍內。

已讀的 setter/套用路徑沒有直接卡檔案寫入呼叫；未窮盡所有 observers 或延遲保存路徑，不能保證不產生任何持久化。不要用「只改 RAM」描述這些原廠選單操作。無參數 mode getter 有 native cache 副作用。

## 一次試驗與使用者可見設定還原

1. 先保存**當下** getter 的 mode、area、size、position，以及 CinemaMode、capture guards、echo owner；不能用前一輪值作 baseline。
2. 保持 exclusive AF lock，設定並讀回 AF-C，再設定並讀回 Tracking。不要額外修改 size/position；原廠會隨 area 改變 effective ROI，記錄其結果。
3. 準備都通過後，只有一次 `key S1ON`。保持有界，`finally` 先 `key S1OFF`；不重送結果不明的 S1ON，不送 S2，不改用另一套 AF trigger 補救。
4. 釋放後還原：**baseline mode → baseline area → baseline size → baseline position**；各 setter 只在值需恢復時使用，最後四项 getter 全部比對 baseline。由於 mode 會影響 area、area/size 會影響 effective rectangle，position 最後恢復。設定不明、模式被使用者切走或傳輸失敗時保留診斷，不盲目追加試驗。
5. getter tuple 完全相同只表示使用者可見這四項恢复；不是 lens position、光學合焦或整個 native storage 逐位恢復。

特別是 `C008B400`／`C008B768` 會改 native 儲存銀行的 area-history `+4EC/+4F0` 與 flags `+4F4/+4F5`。AF-S 和 AF-C 共用／覆寫部分歷史：只保存四項 getter 無法證明所有隱藏歷史逐位恢復。不要為追求逐位相同而直接 poke storage；這不是已驗證的原廠還原方式。

來源：`out/decomp/full/blk_c00.c`（C005、C006、C007、C008、C009、C00A、C00B 函式）、`blk_c02.c`（C028EAB8）、`blk_c03.c`（C03F shell handlers）。本文關鍵常數與 branch 已用本地 ROM ARM disassembly 交叉核對；沒有以實機變更來猜 enum。
