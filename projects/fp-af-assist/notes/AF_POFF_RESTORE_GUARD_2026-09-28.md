# 關機還原：AF 探針自己的 power-off 物件

> **已退役（2026-09-28 同日稍後）。** 關機還原是共用 loader 的職責：執行期才裝的 hook 接點，改為在卡片宣告成一個內容為韌體原字的 4 bytes 區段，由 stage2 記進 journal、loader 的單一回呼寫回；sup 不再自己註冊關機回呼。本頁做的自帶物件另外會吃掉普通清單十格中的最後一格（韌體自己已占 8 格）。程式保留為管理器 ABI 的紀錄，已不在任何安裝路徑上；測試以明確原因跳過。決策與現行做法見 [規範發現](AF_LOADER_CONVENTION_FINDING_2026-09-28.md)。

2026-09-28。先前 `af_hook_trial.py` 的 live gate 是**無條件封閉**，理由是「目前 loader 的關機還原未驗證」。本輪把它換成**實際可驗證的機制**：探針註冊自己的 power-off 還原物件，並在武裝 AF 接點前後各核對一次管理器的兩張表。純離線實作與模擬；沒有相機 I/O、沒有安裝、沒有註冊到任何相機、沒有改卡片或韌體。

## 1. 先確定 loader 的 journal 能與不能做什麼

核對 [stage2.S](../../../fpSup/fp_usb_shell/asm/stage2.S) 的 `LH_RESTORE`：

- journal 由**卡片 section table** 建立。`lh_want` 只收 `>= 0x40000000` 且在 cave（`C072D000..C0735000`）之外的目的位址；cave 存的是 hook 本體不是 hook 接點，故明文不 journal。
- 大小在 `lh_setup` 用同一個判斷從 section table 數出來，所以 journal 不會長出配置外；**沒有 runtime append API，也沒有公開剩餘容量**。
- 塊配置為 `X+0` vtable(`X-8`)、`X+4` routine、`X+8` journal、`X+12` 起 `lh_unhook`，entry 為 `{address, bytes, 原字...}` 以 0 結尾。
- 註冊順序是普通表（`r2=0`）再強制表（`r2=1`）；普通表失敗就 `r10=0`，什麼都不 journal、不武裝。`LH_MARK+8` 在註冊前就發布塊地址，**marker 不是已註冊證據**。

這些行為已由維護中的 [test_loader_hook.py](../../../fpSup/fp_usb_shell/test_loader_hook.py) 模擬驗證（journal 只含 cave 外韌體 section 的原字；關機後每個字都回復，唯獨 AutoRun 那一個 patch 保留）。

**結論：AF 接點 `C022C858` 與借用的 echo `C0BAC2F8` 是執行期經 USB 寫入的，不是卡片 section，因此永遠不在 journal 裡，也不能塞進去。** 這不是 loader 的缺陷，是它的設計邊界。

## 2. 韌體 power-off 管理器的實際結構

由反編譯確認（本輪新增的依據）：

| 事實 | 來源 |
|---|---|
| 管理器是固定單例 `0xC30756C4`，getter `C0023A98` 首次呼叫才建構 | `blk_c00.c` FUN_c0023a98 |
| `POFF_ADD = C0024118 (mgr, obj, forced)`：`forced==0` 用 `mgr+0x0C`，否則 `mgr+0x34` | `blk_c00.c` FUN_c0024118 |
| 每張表 **10 格** u32；填第一個為 0 的格；十格全滿回 0（拒絕），成功回 1 | 同上，`if (9 < uVar1) return 0` |
| 關機時以 `[[obj]+0xC](obj, reason)` 呼叫，兩張表都可能跑到，所以可能跑兩次 | stage2 `lh_unhook` 註解與同結構的原廠用例 |

所以普通表位於 `C30756D0`、強制表位於 `C30756F8`，可直接唯讀解碼。

## 3. 本輪新增的程式

| 檔案 | 內容 |
|---|---|
| [af_poff_guard.S](../highrate/af_poff_guard.S) | **468 bytes**，在 cave 的最終位址上組譯（絕對 header 字，不可搬移）。`+0x00` vtable=`X-8`、`+0x04` routine、`+0x08` 表指標、`+0x0C` status、`+0x10` runs、`+0x14` masks，之後是程式與 `{address, original, allowed[4]}` 表 |
| [build_poff_guard.py](../highrate/build_poff_guard.py) | 組譯、核對 header 六字與表內容確實等於要求的字、拒絕未對齊／等於原字的 armed word／重複 allowed，輸出 manifest 與雜湊 |
| [shutdown_restore.py](../highrate/shutdown_restore.py) | 唯讀裁決：解碼兩張表的有效前綴、重讀物件與 reviewed bytes 逐字比對（只允許 status/runs/masks 變動）、由卡片 VBIN 陳述 journal 覆蓋範圍 |
| [test_poff_guard.py](../highrate/test_poff_guard.py) | **33 tests**，Unicorn 跑真實機器碼，`POFF_ADD` 依反編譯建模且表在模擬記憶體中，因此斷言的是效果不是自述 |
| [test_shutdown_restore.py](../highrate/test_shutdown_restore.py) | **16 tests**，純解碼邊界，不需 Unicorn |

還原規則：逐筆比對現值；**已是原字就不寫**；現值在 allowed 集合內才寫回原字；否則記為 foreign owner 並**留給對方不覆寫**。allowed 集合在組譯時固定——AF 接點只有 armed branch 一個；echo 有 D-cache、I-cache、capture helper 與**本物件自己的 register entry**（安裝過程同樣經該 echo 借用抵達）。寫回後才做一次 D-cache clean 與 I-cache invalidate，因為還原的字是指令。表走訪上限 8 筆，allowed 掃描上限 4 格。

註冊路徑：每個 boot 只嘗試一次（第二次直接拒絕，不會重複進表）；普通表被拒就**不碰**強制表；`status` 明確區分「已嘗試」「管理器為空」「普通表滿」「強制表滿」。

## 4. gate 改成什麼

`af_hook_trial.py` 現在：

1. **第一個寫入之前**（唯讀）讀兩張表，任一張滿或終止符後有非零字就直接拒絕，`installation_performed=false`，一個字都不寫。
2. claim 四塊 cave（helper 1536＋param 128＋veneer 8＋guard 468 = **2,140 bytes**，arena 共 3,920），放入物件、發布、經 echo 呼叫 register entry 一次、還原 echo。
3. 重讀物件與兩張表：必須在**兩張表都在**、bytes 與表內容等於 reviewed、且物件自述與表內容一致才通過。
4. **武裝 AF 接點前再驗一次**，`shutdown_restore_verified` 只由第二次裁決設定。
5. 收尾把 guard 的 `runs`／`restored`／`foreign` 一併存進 `cleanup.guard`。

`--inspect` 現在回 `live_ready=true`，並列出四項執行期條件；`--run-live-hook` **沒有任何略過選項**（測試會掃描原始碼確認不存在 `--force`／`--skip`／`--no-verify`）。

## 5. 驗證

| 檢查 | 結果 |
|---|---|
| guard ARM 真實機器碼（Unicorn） | 33 tests 通過；含註冊、雙表、拒絕、重入、還原、冪等、foreign、零字不算自己人、走訪上限、快取順序、SP 4-off、r4–r11 保留 |
| 突變對照（guard） | **6 個**全部被抓：不註冊強制表、還原不寫入、不發布 I-cache、不落 attempted、丟掉已是原字的判斷、丟掉走訪上限、把零當成 allowed |
| 裁決解碼器 | 16 tests 通過；另外 3 個突變（跳過逐字比對、忽略自述一致、忽略終止符後非零）全部被抓 |
| installer 狀態機 | 27 tests 通過，其中 8 個是新 gate：任一表滿不安裝、precheck 後才滿、管理器為空、物件被改、武裝前重驗、完整裁決內容、無 CLI 略過 |
| highrate 全套 | **152 tests 通過** |
| 專案根回歸 | 543 tests，**1 個既有錯誤**：`test_guarded_loader` 的 `build_guarded_loader.py` 仍鎖舊 loader 來源身分（`maintained loader source identity changed`）。與本輪無關，屬 [transport gap](AF_STREAM_TRANSPORT_GAP_2026-09-27.md) 已列的待辦，不能只換 hash 繞過 |

本輪還修掉一個自己造成的回歸：把 guard 大小算在 module import 會讓 `import af_hook_trial` 跑 clang，違反既有「import 不起 subprocess」契約；已改為延遲且快取。

## 6. 邊界（不要擴張）

- **只覆蓋普通與強制關機。** 抽電池、當機或 IPL 重置沒有任何 callback 會跑；那種情況接點仍是 armed，暖啟動保留 firmware/cave 但**重建 heap**，recorder 程式在 USER 配置裡，指標即懸空。這是仍未關閉的風險，不能用本物件宣稱已解。
- 註冊是經原廠 `POFF_ADD` 寫進一個**空格**，不是寫未知位址；但它仍然是對韌體 RAM 的一次寫入，且本輪**沒有在相機上做過**。
- 全部為模擬：`POFF_ADD`、cache 常式與關機時序都是模型。真實管理器如何走表、何時走、與 USB／錄影的交互都未驗。
- 還原物件不是 quiescence 證明：它把字放回去，不代表被暫停的程式已離開。`quiescence_proven`、`warm_boot_verified` 固定為 false。
- 仍然**沒有** EP83 實收、沒有 hook 實裝、沒有 AF／幾何／DFD 有效性。

## 7. 接續

1. USB 恢復後（9/27 20:30 仍為 `LIBUSB_ERROR_NO_DEVICE`）先做當輪唯讀 preflight，讀兩張表的實際占用，確認有兩個空格。
2. 用真實 loader／stage2 在 Unicorn 走一次「已註冊本物件 → 關機 → 暖開機」，核對兩表有效前綴交集與 boot 前後一致；本輪只驗了本物件自己，沒有與 loader 物件同時在表上的情形。
3. 補「抽電池／當機」的殘留處理：候選是讓 veneer 先比對 boot stamp，不符就直接執行原呼叫。這是暖開機安全的關鍵缺口，與本物件分開驗收。
4. 之後才是 64 筆 H/L 經已完善的 EP82 通道實收（見[高速通道現況核對](AF_CHANNEL_STATE_VERIFY_2026-09-28.md)）。

接法與可重用的 ABI 已寫入 skill [`fp-camera-control` §12](../../../.claude/skills/fp-camera-control/SKILL.md)。

重跑：

```sh
cd projects/fp-af-assist
python3 -B -m unittest discover -s highrate -t . -p 'test_*.py'
python3 -B highrate/af_hook_trial.py --inspect --output NEW_DIRECTORY
```
