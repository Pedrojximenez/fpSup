# 舊「全能控制台」時期的 AF hook：核對與取用

2026-09-28，依使用者提示核對先前做控制台時掛過的 AF 資料。本輪只讀檔、跑既有離線測試；沒有相機 I/O、沒有搬移程式、沒有安裝。

## 三處來源與價值

| 來源 | 是什麼 | 價值 |
|---|---|---|
| [console/](../../open-gate/test-build/console/) | `fpstate.py` 約 40 個即時欄位的位址表，走已退役 worker 的 `mem read`。README 自述不能直接跑 | **輪詢**，不是 hook。AF 欄位多數已在現行 `LIVE_SOURCE_WORDS`；只有 body-motion `C3404678(+4)` 未列入 |
| [af_fusion_snapshot.S](../../../research/autofocus/af_fusion_snapshot.S) | echo handler 替換式 snapshot，record 0xD4 bytes，含 `saf_jdat_h/l`（51 格）與 `mposm[]`（最多 1000 筆）掃焦歷史索引與 index-stability 檢查 | 現行專案已知；live 已被 worker pool guard 擋下 |
| **`worktrees/fpsup_repo/focus/dfd/` stage1** | **掛同一個接點的完整子系統**：`stage1_af_stats_hook.S` 832 bytes、`stage1_manager.py`、`stage1_reader.py`、`STAGE1.md`、兩份測試 | **主 checkout 沒有，現行筆記一份都沒引用。** 本輪重跑：`build` 正常、**92 個離線測試全過** |

stage1 的接點與現行 `af_publication.S` 完全相同：`C022C858`，原字 `EB00485C`，`BL C023E9D0`，返回 `C022C85C`。payload `0xC072E400..0xC072E740`，mailbox `0xC072E700`，armed 字 `0xEB1406E8`。

## 取用了什麼

依使用者定調（重心在 hook 與快速導出，不主動讀記憶體），只取與 **hook 自身安全**有關的三件事，實作見 [分級與不輪詢](AF_HOOK_STAGED_NOPOLL_2026-09-28.md)：

1. **分級 bring-up**（off/count/record）。stage1 是 0/1/3/7，第四級呼叫 TickTimer；本專案不取 timer 級，因為不需要且會進入韌體 timer helper。
2. **重入偵測**與「一旦偵測到就永久停止發布」。stage1 用 LDREX/STREX 的 `in_flight` 加 sticky `overlaps`；本專案改用普通 load/store 的標記，原因是 ABI 稽核未審 r2/r3/r12（strex 需要第三個暫存器）。
3. **讀取時前後確認 hook 仍在**的觀念。stage1 是 `hook before → mailbox → overlaps postcheck → hook after`；本專案對應為守衛在 arm 前與還原後各讀一次，並把 `in_body`／`overlaps` 一起匯出。

## 沒有取用什麼，為什麼

- **64-byte mailbox 與 5–10 Hz 輪詢 reader**：這正是要避開的資料路徑。本專案維持「hook 寫進有限緩衝、一次 bulk 導出」。
- **seq_begin/seq_end 撕裂讀保護**：那是單一可變 cell 的配套。本專案每筆 record 在 commit 前完整寫入，並有 commit/complement 與 in-order 檢查，等價保護已經更強。
- **固定載入位址**：`0xC072E400`／mailbox `0xC072E700` 落在現行 cave arena（`C072E064..C072EFB4`）之內，會與 `cave.claim()` 撞車——9/28 的 power-off 物件測試位址 `C072E708` 就壓在舊 mailbox 上。`cave.py` 的 ArenaTests 本來就會擋任何寫死 arena 內位址的原始碼。要沿用必須先改成 claim。
- 那個 worktree 的 `fp_usb_shell` 與維護版不同（`worker.S`、`VSHL.BIN`、`callfn.py` 均 modified），其 preflight 期望值不能直接當成現行 worker 的。

## 最要緊的收穫：它為什麼把自己停住

stage1 的 live install 是**硬停**，理由不是關機還原，是 **cache 同步**：

> `C000E91C` 以 set/way clean+invalidate 全部 D/unified cache 並 DSB/ISB；`C000EABC` 是 `ICIALLU` 後 DSB/ISB，**但只對執行它的 local context 生效**。沒有證據顯示它能讓真正跑 `AfContinuousObserver` 的 context 同步失效，也沒有該 observer 的 affinity/rendezvous 證據。從 USB shell task 依序呼叫兩者，不能當作已證明的修正。

現行 `af_hook_trial.py` 的 `probe.publish()` 做的就是這一對呼叫。**同日稍後已查明這個顧慮在本機不成立**：它需要第二顆核心才會發生，而全映像沒有 MPIDR 讀取、沒有 SCU 存取、沒有廣播 ICIALLUIS，原廠 D-cache 維護還用 set/way（架構上不廣播）。見 [單核證據](AF_CACHE_COHERENCY_2026-09-28.md)。舊 stage1 的判讀本身沒錯，只是缺了核數這一項。

stage1 也評估並拒絕了改 `C09185B0` 的 `AfContinuousObserver::v1` vtable 指標（可避免熱改 text line）：完整 v1 callback 有**不執行 `C023E9D0`** 的初始化／gate-false 路徑，無條件在返回後發布會把舊 H/L 誤算成新 evaluation。這個理由對[幾何的四個接點](geometry/NATIVE_HOOK_PLAN.md)同樣適用，應一併核對。

## 尚未納入的現成資料

以下在 stage1／console 有、現行專案沒有，可低成本補上：

- `PEAK_NOW 0xC32915C4`、`PEAK_MAX 0xC32915C8`、body-motion `0xC3404678(+4)`：均不在 `LIVE_SOURCE_WORDS`。
- AF ctx 的 mode 欄位在 `+0x20C8`。
- 六個 AF vtable slot 的 preflight 期望值（stage1 install 前逐一核對）：

  | slot | 期望值 | 名稱 |
  |---|---|---|
  | `C09185B0` | `C022C7E8` | AfContinuousObserver::v1 |
  | `C091DF58` | `C025CD30` | AfMgrProcessFast::v5 |
  | `C091DF60` | `C025E170` | AfMgrProcessFast::v7 |
  | `C091F158` | `C026B6D0` | AfMgrProcessNear::v7 |
  | `C091F17C` | `C026DBB0` | AfMgrProcessNear::v16 |
  | `C091F6C0` | `C026F128` | AfMgrProcessRocking::v6 |

  現行專案只在 [HOOK_LIFECYCLE_AUDIT](HOOK_LIFECYCLE_AUDIT_2026-09-16.md) 提過第一個，其餘五個從未出現。stage1 另外還核對 echo handler 與 mem handler slot。

這些都尚未加入現行 `ROM_GUARDS`／來源清單，屬下一輪工作，不是本輪已完成項目。
