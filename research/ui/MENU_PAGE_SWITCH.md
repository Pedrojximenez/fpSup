# 選單裡換頁：直接設畫面會掉鍵，要走原廠狀態機（2026-10-25）

標記：**[實機]** 上機驗過；**[離線]** 只讀反組譯。

## 症狀 [實機]

從 fpSup 頁進過 SupManager／RES-Custom 後，快速連按（0.15 s 間隔）會吃鍵：4 下只動 1–2 下；
0.3 s 以上不掉。退出選單回待機再進才恢復。原廠子頁進出不會。

**最小重現**：剛開機進 fpSup 頁（FT_Y6），shell 下一次 `gui scr set FT_Y6`（同一頁），連按 4 下 → 只動 1 下。
三次 `scr set` 比例差不多，不累積。

量法：`fpSup/fp_usb_shell/ui_burst.py`（GUI 時間日誌，按鍵間隔可調）＋截圖數游標位置（`ui_shot.sh`）。**render 次數 ≠ 游標移動數**，一定要看截圖。

## 換頁的兩條路 [離線]

螢幕管理器 `FUN_c054dd38()` → 物件 0xC3786188，vtable 0xC0D0DAD4：

| vt | 做什麼 | 事件型別 |
|---|---|---|
| +0x48 | `gui scr set`：記下畫面名，GUI 迴圈結束時 `c0560730` 逐 app `c05e0758/c05e07c8` 直接設畫面 | 9 |
| +0x0C | `gui send <名字>`：建事件 3（`c055dcd8`，兩個旗標由 +0x8C/+0x90 查名單），`c05640f8` 批次 → `c05606a0` 逐 app `c05dc690(app,0,1,{0,name})` 送 SyncRequest | 3 |

`gui send Return／Menu01／Menu13` 都**不會換頁**：頁面之間的轉換不是 AppSync 請求。 [實機]

原廠頁面換頁是頁面動作 `controlAppState`（41 bytes，+36 是請求字串，例：MainY5 列的 Right 送 `Y5_1`）。
執行函式 0xC05F1399（Thumb）把（請求, 動作物件）排進延後佇列（app+0x198+0x30），之後才轉換。

GUI 主迴圈 0xC055E4B8 的事件 switch（0xC055E5C4）：型別 2 = 變數整數（批次存在 gui+0x444，`c0563ff0` 在迴圈尾端
經 `c055f8f0` → 逐 app `c05dc778(app,0,n,entries)` 套用）。**變數是批次的，比延後的 controlAppState 晚生效** [實機推論]。

## v4 的做法 [實機]

1. fpSup 頁根物件上一個 `appVariableChangeEvent`（MainY5 submenu_width 那筆的 45 bytes 格式，只有變數名＋type），
   監看 `FT_Go`，動作 = controlAppState 請求，請求字串是私有字串 T_GO（執行時才讀，可在 RAM 改）。
2. 按 JUMP 列：核心清空 T_GO → 呼叫 sup 的 `open()`（推好頁面變數，最後 `fpui_open` → `svc->ui_go` 把頁名寫進 T_GO）
   → 核心推 `FT_Go` 下一個值。同一批變數裡 FT_Go 在最後，事件觸發時 open() 推的值都已生效。
3. 各 sup 頁面包有轉換 FT_Y6 → 頁名（request = 頁名，`build_fp4.open_transitions`）。
4. 子頁進場寫 `FT_Go = 0`（`manage_page.enter_write`）；核心看到 0 清空 T_GO。否則回到 fpSup 頁時頁面重建會**再觸發一次**事件，MENU 一回來又被送回子頁。

試過不行的：
- 按鍵事件直接送 request：比 open() 推的變數早生效，RES-Custom（不分頁、焦點在第 0 列）進頁時第 0 列還沒顯示 → 焦點落空、全部按鍵無效。
- 「等於 1」的變化事件（49 bytes，mask 7，+44 byte 5 或 0，+45 float 1.0，照 B1_1 的 CM_TransitionFlag）：完全不觸發，原因未明。

## appVariableChangeEvent 欄位（從原廠樣本歸納）[離線]

`+16` 動作數、`+20` 描述名（pool 位移或 0xFFFFFFFF）、`+24` 擁有物件、`+28` 事件編號、`+32` 欄位 mask
（bit0 variable-name、bit1 type、bit2 equal-value、bit3 greater、bit4 lower…）、`+36` 變數名，之後依 mask 排；
mask 3 = 45 bytes（`+40` u32 0、`+44` 1 byte），mask 7 = 49 bytes（再加 float）。
原廠 13235 筆，其中 426 筆的動作含 controlAppState。
