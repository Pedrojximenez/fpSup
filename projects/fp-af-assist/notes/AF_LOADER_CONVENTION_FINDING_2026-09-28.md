# 兩個維護中規範的發現：關機還原的正規做法，與 cache 發布的既有證據

2026-09-28，並行推進 EP83 與 cache 問題時查 [SUP_BUILD_RULES](../../../fpSup/SUP_BUILD_RULES.md) 與 [HOOKS_AT_POWER_OFF](../../../fpSup/HOOKS_AT_POWER_OFF.md) 得到。**本輪只讀檔；沒有相機 I/O、沒有改卡、沒有跑測試**（工具環境暫時無法執行命令，下列未標「已量測」者皆為文件與原始碼陳述）。

## 1. 關機還原：我 9/28 第一輪做的東西不是維護中的做法

`HOOKS_AT_POWER_OFF.md` 第 15–22 行寫得很清楚：

> **Since 2026-09-25 the loader does this, not the sup.** stage2 registers one power-off callback in both lists before it places anything… A sup that arms a hook at run time **declares the site as a four-byte section holding the firmware's own word**, so the journal has it — gyro's `hook_sites()`. **A sup no longer registers a power-off routine of its own.**

也就是說，執行期才裝 hook 的正規做法是**把 hook 位址宣告成一個 4 bytes 的卡片區段、內容是韌體原字**，讓 stage2 在 entry 之前記進 journal，關機由 loader 的單一回呼寫回。我 9/28 第一輪做的 [自帶 power-off 物件](AF_POFF_RESTORE_GUARD_2026-09-28.md) 正是這份規範已經**退役**的模式（gyro v1.13.1 的 `s_poff`／`poff_disarm`，v1.14.0 移除）。

那份實作本身沒有錯、測試也都過，但它：

- 重複了共用 loader 已經提供的機制，違反「不為每個 sup 複製一份」的第一條守則；
- 而且會吃掉**普通清單最後一格**（見下）。

## 2. 兩張清單的實際占用（文件所載的靜態讀取結果）

| | 位址 | 格數 | **韌體自己占用** |
|---|---|---:|---|
| ordinary | `mgr+0x0C` = `C30756D0` | 10 | **8** |
| forced | `mgr+0x34` = `C30756F8` | 10 | **1**（USB gadget） |

stage2 每次載入還會各註冊一個。所以一張已載入的卡上，**普通清單很可能只剩 1 格**。我的 guard 會把它用掉。這是設計上不該做的事，也讓 `require_room()` 的檢查從「保險」變成「幾乎一定會踩到」。

呼叫方式與我實作的一致：`obj->vtbl[+0xC](obj, reason)`，ordinary 由 `C0023C50`、forced 由 `C0023F38`（reason 4）呼叫，回傳值忽略；管理器在呼叫前會把物件位址記到 log（`C001A048`），只存指標不解參考，所以不需要 RTTI。這幾點可用來加強驗證。

## 3. 對 AF 探針的實際結論

| 借用的字 | 能不能走正規的卡片區段路線 |
|---|---|
| AF 接點 `C022C858` | **可以。** 開機時它是原廠值，宣告成 4-byte 區段（內容 `EB00485C`）即可進 journal |
| 借用的 echo `C0BAC2F8` | **不可靠。** 普通冷開機進 stage2 時 echo 可能仍借給 `lboot`，journal 會記下借用中的值，關機就會還原成錯的字。這點 [9/27 筆記](AF_FIRST_HOOK_CHANNEL_2026-09-27.md) 已經指出過 |

echo 的殘留風險本來也比較低：它指向的是 cave 內的 helper，而 **cave 跨暖開機保留且仍是有效程式**；危險的是指向池（heap）的東西，而池會重建。

所以建議的收斂方向是：**AF 接點改走卡片區段（正規路線），echo 另外處理**，而不是為兩個字自帶一個 power-off 物件、吃掉最後一格。這需要重建測試卡並冷開機，是比純 USB 注入大的一步，取捨要由使用者決定。

## 4. cache 發布：既有證據比我先前的描述樂觀，但仍不是證明

`SUP_BUILD_RULES` §4 第 98 行：

> 新寫入的 ARM 程式在首次執行前，沿用**已驗證的** `0xC000E91C()` → `0xC000EABC()`。DSB、記憶體讀回正確、或「新程式進入後自己 flush」都不能取代首次執行前的快取處理。

而 `HOOKS_AT_POWER_OFF` 第 155 行描述 gyro v1.13.1 的做法：把 disarm 常式複製進 cave 後，`C000E91C() → C000EABC()`，**之後由韌體的 power-off manager 在完全不同的 context 呼叫它**——而那是實際出貨過的產品。

這削弱了我上一輪「同一招未經證明」的講法：**這個發布序列在出貨產品裡被依賴過，且被跨 context 呼叫過，沒有歸因到它的失效**。但仍然不是本案的證明，因為：

- 那些發布都發生在**載入期**，AF observer 還沒在跑；我們是在相機運作中改一條 text line。
- 舊 stage1 的顧慮（`ICIALLU` 只對執行它的 context 生效）在文件裡沒有被反駁，只是實務上沒出事。
- 目前沒有讀到 fp 是單核或多核的直接證據；這個問題若確定是單核，顧慮基本消失。**這一項尚未查證**（本輪無法執行反組譯）。

## 5. 因此浮現的第三條路

`HOOKS_AT_POWER_OFF` 第 28–31 行：

> A static patch whose code sits in the firmware image (a VBIN section at a fixed address in the cave) is not covered: that code stays valid, and it survives a warm restart along with the patch that calls it.

**由卡片在開機時安裝 hook**，publication 發生在 stage2、AF observer 尚未執行該位址之前，等於繞開「運作中熱改 text line 的 I-cache 同步」這個問題；而且 hook 本體在 cave（跨暖開機有效），只有資料緩衝需要另外配置。代價是每次改動都要重建卡與冷開機，失去 USB 即時迭代。

## 6. 已採用 B：改走正規路線（同日完成）

使用者選 B。已完成的變更：

| 變更 | 內容 |
|---|---|
| 新增 [hook_site_section.py](../highrate/hook_site_section.py) | 由**已核對雜湊的 ROM 讀出**原字（不手寫），產生 4-byte 區段檔並印出要加進卡片建置的 `--also-bin 0xC022C858:hook-site-C022C858.bin`；另可用 `--check-card` 驗一張已建好的 `fpSup.BIN` 是否真的宣告了該區段 |
| 重寫 [shutdown_restore.py](../highrate/shutdown_restore.py) | 從驗證「自己的物件」改為驗證**共用 loader 的 journal**：由兩張清單找出 journal block（依 stage2 `lh_setup` 的 `X+0=X-8`、`X+4=X+12`、`X+8=journal` 結構辨識，且必須**同時**在兩張清單），走訪 entry，讀出該位址被記下的原字 |
| [af_hook_trial.py](../highrate/af_hook_trial.py) | 移除 guard claim／安裝／註冊。gate 改為：第一個寫入前驗一次 journal，武裝前再驗一次；**不註冊任何東西、不占用任何清單格**。cave claim 由 2,140 降回 1,672 bytes |
| 退役 | `af_poff_guard.S`／`build_poff_guard.py` 加上退役標頭，`test_poff_guard.py` 以明確原因跳過。檔案保留（本目錄無版本控制，刪除不可復原），是否刪除待決 |

echo 仍不走 journal（理由如上節），由主機在每條路徑還原；它指向 cave 內的程式，暖開機後仍是有效程式。

驗證：`shutdown_restore` 23 tests，**6 個突變全部被抓**（丟掉兩張清單規則、不比對原字、不要求已 journal、不檢查 block 佈局、不檢查 entry 範圍、丟掉走訪上限）——其中後兩項第一次沒被抓到，因為測試是「因錯誤的理由通過」，已改成真正可區分的斷言。installer 33 tests（新增：未 journal 就完全不安裝、只在一張清單、journal 記到被 patch 過的字、武裝前重驗、**不註冊也不占格**、卡片交叉核對）。highrate 141 tests、專案根 533 tests 通過，僅餘既有的 guarded-loader 來源身分錯誤。

## 7. 下一步

1. **維持現狀**：繼續用自帶 power-off 物件的 USB 注入路線，但接受它吃掉普通清單最後一格，並在上機前實測兩張清單的實際空位。
2. **改走正規路線**：AF 接點以 4-byte 卡片區段宣告、由 loader journal 還原；echo 另議；探針改由卡片安裝或維持 USB 注入但只借 echo。
3. **先查清單核數**：確認 fp 是否單核，直接決定 cache 顧慮是否存在。這是最便宜也最有決定性的一步。

本輪另已修正 `ep83_libusb_owner.py` 預設 libusb 路徑（原先解析到不存在的 `projects/lib/`，改為維護中的 `projects/usb-shell-sup/lib/`，並在缺檔時明確報「主機打包問題，未嘗試 lease」）。**該修正尚未執行驗證**，工具環境恢復後需重跑相關測試。
