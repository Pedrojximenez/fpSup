# fpSup 載入速度與取消停留：2026-10-11

已取消共用完成動畫的固定 2 秒等待，並更新目前相機的 Loader v3。
目前 Merge v3 沒有 Fast Start；舊 `tools/card-composer` 的 Fast Start 3
不能當作新 `tools/merge-v3` 已支援的證據。

## 實機時間

以下是兩次 USB 連線下的開機；第二次為單次軟體 reboot。
相機的 `LOAD.LOG` 第一筆 START 與 `C072F6F8` DONE 使用同一個原廠微秒計時器。

| 卡片 | START | DONE | Sup 載入與初始化 |
| --- | ---: | ---: | ---: |
| 更新前 | 3.380137 s | 7.658333 s | 4.278196 s |
| 取消停留後 | 3.346261 s | 8.235800 s | 4.889539 s |

DONE 在寫 LOAD.LOG、完成畫面、原本的 2 秒停留與 AutoRun 收尾之前寫入。
取消停留不會直接讓這個時間戳少 2 秒；這兩次也不是固定條件的效能基準。
尚無各 Sup 的分段時間，不能把 4.28–4.89 秒歸咎於某個特定 Sup。
目前卡上有七個候選 Sup，共 936,724 B，另有內建 SupManager 資料。
LOAD.LOG 的 96 筆上限會被 claims 填滿，沒有尾端 DONE log 不代表載入未完成。

## 另外確認的 AutoRun 收尾問題

實際讀回的 AutoRun 是 32,768 B，SHA-256
`0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0`。
開頭已 NOP 逐字延遲，且無前段註解；這項加速已生效。
交棒前仍有 81 個 bootstrap word 寫入與 12 次 osdfile。

逐字延遲在第一次 loader echo **之前**恢復。
目前 `worker.S:spawn` 建立自己的 task 後返回；v3 的 Sup entry、
`sl_run`、`sloader_entry.S` 與 `loader.S` 都會返回 AutoRun。
因此舊筆記「交棒後永不返回，所以補白不計入時間」不適用目前卡。
交棒後還有 29,458 B，包含 28,728 個補白可見字元；原廠 parser 對這些字元
仍會呼叫延遲。不能僅看 32 KB 的檔案大小推斷，必須核對返回路徑。

取消 2 秒停留後的實機原生讀取確認：

- reboot 回覆後約 61.85 秒：DONE 已寫入、DRAW 與 echo 已還原；
  table depth 2，第二筆 callback `C03DA7A8`，AutoRun context `C3756A14` 仍存在。
- 約 112.36 秒：depth 1，只有原生 console callback `C03DA158`，AutoRun 已收尾。

這是執行與完成的採樣界限，**不是精確的完成時間，也不代表畫面一直無法使用**。
本輪沒有修正 AutoRun 結束或補白方式。後續應優先避免在恢復逐字延遲後繼續讀補白，
並保留原廠 script file close、registration pop 與 running flag 的正確收尾。

## 本輪修改與驗證

`boot_splash.py` 的 HOLD_MS 改為 0；共用 `splash_finish.S` 在值為 0 時完全省略
原廠 sleep 呼叫，保留三次完成畫面、DRAW ownership guard、D/I publication 與 full repaint。
普通與 Fast 的 stage2、新 v3 loader 都沿用這一份來源。

共用 boot-chain／loader-hook／splash／v3 測試 51 項通過，SupManager 測試 18 項通過，無略過。
修改舊的 frozen-loader hash assertion 為新的普通 loader 行為驗證，沒有覆寫凍結發布檔。
將 v3 測試的編譯參數刻意改回 2000 ms 時，實際 ARM 執行測試失敗於 `2000 != 0`，
確認取消等待的退化可被檢出；正式來源未被 mutation 改動。

成品 `projects/usb-shell-sup/cards/20261011-no-hold-v3` 是本輪 loader 更新包。
LOADER.BIN：27,652 B，SHA-256
`ecae97aff1c484d878f1ae5c277bc1b9607860f49601c4832c08da97ff0b801a`。
resident C code 與更新前逐位元組一致；移除等待使 stub 短 16 B。
AutoRun 不變，使用者的 FSDS 停用清單保留。

相機部署前完整保存原檔；因 mode 7 不截短，只刪除已備份的 LOADER.BIN，再寫入新檔。
完整讀回與新成品一致；重開後再次完整讀回一致，正常待機、DRAW 與 echo 已還原。
重開時 macOS PTP 再占用 interface 0；經 IOService 與 exact PID 驗證後釋放，
沿用本輪 daemon，最後 PID 22493。未錄影，未測 SSD，未發布。

## Merge v3 的 Fast Start 狀態

檢查 `tools/merge-v3/build_catalogue_v3.py`、`template.html` 與實際 `index.html` 的內嵌資料：
只有 shared、products 等資料；compose 直接複製 shared，沒有 Fast 開關或 Fast 封裝。
內嵌 AutoRun 沒有 store bootstrap，v3 loader 沒有 provision／abort／warm hook 的整合。
因此需要先把 Fast 路徑接入 v3，再加入 Merge 選項，不能宣稱已有支援。

既有 Merge v3 頁面內嵌的是凍結發布的 7,260 B loader，仍含原本的 2 秒停留。
本輪更新的是共用來源與目前相機的 loader；沒有改寫既有發布成品或發布網站。
發布流程下次重建相應 loader 成品時，才會將取消停留帶入下載頁。

原始證據：`analysis.json`、`hardware-proof.json`、`merge-v3-before.json`、
`deployment.json`、完整前後 BIN／AutoRun／LOAD.LOG 與各測試 log。
