# Hook 分級、重入偵測與不輪詢的一次匯出

2026-09-28。使用者定調：**研發重心放在 hook，把 hook 到的資料快速由 USB 導出，而不是主動去讀記憶體。** 本輪照這個方向改了兩件事：recorder 自己的安全（分級＋重入偵測），以及資料路徑不再輪詢。純離線實作與模型驗證；沒有相機 I/O、沒有安裝、沒有卡片或韌體變更。

參考來源是舊 [`focus/dfd` stage1](AF_PRIOR_HOOK_REVIEW_2026-09-28.md) 掛在**同一個接點**的探針。只取它與 hook 安全有關的三件事；它的 64-byte mailbox＋主機每 0.1 秒輪詢的資料路徑**不採用**，因為那正是要避免的模式。

## 1. 分級（capture 格式 schema 2，header word 12）

| level | 值 | hook 做的事 |
|---|---|---|
| off | 0 | 只重放原廠呼叫。**連計數都不動**，header 完全不變 |
| count | 1 | 只累加「原廠 producer 回來幾次」。不讀任何欄位、不寫 record |
| record | 3 | 完整 128-byte record，與先前相同 |

任何其他值一律視為 off，所以 header 被弄壞時是 fail-closed。`level` 是**主機專用字**，hook 只讀不寫（指令模型的寫入白名單不含該位址，另有測試確認整輪 258 次呼叫都沒寫過它）。

意義：第一次上機不必冒險等 64 筆填滿，`--level count` 只要看一個數字有沒有在跳，就知道接點真的在跑。`af_hook_trial.py` 的**預設已改為 count**；record 要明確指定。階梯沒有跨 run 機器強制，筆記與 CLI 說明都寫明 record 應該接在一次成功的 count 之後。

## 2. 重入偵測（header word 14 `in_body`、word 15 `overlaps`）

body 進入時標記 `in_body`，每條離開路徑都清除；若進來時發現已被標記，就**不發布任何東西**、把 `overlaps` 鎖定為非零、也不清除別人的標記。`overlaps` 一旦非零，此後**永遠不再發布 record**（直到冷開機重建 header），但原廠呼叫仍每次完整重放。

**這是普通 load/store，不是互斥證明。** LDREX/STREX 需要第三個暫存器，而 [HOOK_ABI_AUDIT](HOOK_ABI_AUDIT_2026-09-16.md) 明確把 r2/r3/r12 列為**未審、最窄 stub 不動**，所以不能為了原子操作擴張暫存器使用範圍。剩下的空窗是「兩個 body 在同一瞬間通過標記」；那種情況由 reader 的 in-order commit/complement 檢查接住（record 會判為未提交或亂序）。這個限制寫在 `af_publication.S` 檔頭，不是靠筆記記住。

`af_sender.c` 的 header 檢查同步升級：`overlaps` 非零、`in_body` 非零或 `hits < count` 的 capture **一律不送**。

## 3. 資料路徑不再輪詢

舊流程：arm 之後每 0.1 秒讀一次 header 等 `full=1`，順便輪詢 CINE／shutter 守衛，滿了才匯出。

新流程：

```
arm → 一次 sleep（觀測視窗內完全不上 USB）→ 還原接點 → 守衛各讀一次
    → 一次 bulk 把整塊 buffer 讀回來 → 解碼「已提交前綴」
```

- `decode_capture` 現在接受未滿的 capture，只解已提交的前 `count` 筆；要求完整的呼叫端（`pack_batch`）改用 `require_full=True`。
- 沒有「填不滿就失敗」的期限了：短視窗是合法的部分結果。record 級別下一筆都沒有才算失敗。
- 觀測視窗內主機**一次交換都沒有**（有測試量 `operations` 數量前後相等），所以 hook 執行期間沒有 USB 流量與它競爭。
- 匯出仍走已完善的 EP82 大量回覆路徑，64 筆連 header 共 8,256 bytes 一次讀回。

另外修掉一個因此浮現的邊界：`enabled` 清除與 `full` 設定之間相隔幾個指令，讀到那個空窗的 header 以前會被判為損壞；現在視為合法的收尾狀態，`full` 回報 false，需要完整性的呼叫端才會拒絕。

## 4. 驗證

| 檢查 | 結果 |
|---|---|
| recorder 指令模型 | **27 tests**（原 19）。新增：off／未知等級完全惰性、count 級只計數不寫 record、重入者不計數不清標記只鎖 overlaps、鎖定後永不再發布、標記在整個 body 期間為 1 且結束清除、hook 從不寫 level 字、已提交前綴不等 full 即可解碼、滿載後 records/count/enabled/full 全凍結 |
| 突變對照（recorder） | **7 個**全部被抓，且皆以模型支援的無害指令替換，失敗來自行為而非未知指令：不設標記、不鎖 overlaps、丟掉 sticky 檢查、丟掉 level gate、不清標記、off 級掉進 body、不計數 |
| installer 狀態機 | **32 tests**（原 27）。新增：視窗中守衛變動在匯出前擋下、資料路徑零輪詢、count 級成功、producer 沒跑就失敗、重入保留 bytes 但判定無效、還原後仍有標記不算成功 |
| C sender | 14 tests，含新增「重入／未收尾／hits 不足的 capture 絕不送出」 |
| highrate 全套 | **165 tests 通過** |
| 專案根回歸 | 556 tests，**1 個既有錯誤**：`test_guarded_loader` 的 loader 來源身分鎖，與本輪無關（見 [transport gap](AF_STREAM_TRANSPORT_GAP_2026-09-27.md)） |

recorder 由 724 成長為 840 bytes（210 words）；指令上限從 200 提高到 216，仍是緊的直線 leaf。schema 由 1 升為 2，`af_ep83_camera.c` 的 synthetic 產生器與 `af_sender.c` 的 header 檢查一併更新。

## 5. 邊界

- 全部是離線與模型：指令模型不是 CPU／IRQ／cache／USB 模擬器，不證明任何時序。
- 重入偵測是普通 load/store，不是互斥證明（見上）。`in_body` 在還原後為 0 只是**提示**，不是 quiescence 證明；`serialization_verified` 只代表「本次沒偵測到」。
- **仍沒有上機**：USB 自 9/27 20:30 起回 `LIBUSB_ERROR_NO_DEVICE`。
- ~~更要緊的是另一道還沒關的閘：**cache 同步**。~~ **2026-09-28 稍後已排除**：全映像沒有 MPIDR 讀取／SCU 存取／廣播 ICIALLUIS，且原廠 D-cache 維護用 set/way（架構上不廣播），代表只有一顆 ARM 核心執行這份映像，ICIALLU 從哪個 task 呼叫都作用在同一份 I-cache。詳見 [單核證據](AF_CACHE_COHERENCY_2026-09-28.md)。以下為當時的描述：
  把 hook 程式寫進 cave 後，沒有證據顯示真正執行 `AfContinuousObserver` 的 context 會看到新程式。`C000E91C` 是 D/unified cache set/way clean+invalidate 加 DSB/ISB；`C000EABC` 是 `ICIALLU` 加 DSB/ISB，但**只對執行它的 context 生效**，而我們是從 USB shell task 呼叫的。舊 stage1 正是為此把 live install 硬停。目前 `probe.publish()` 做的就是這一對呼叫，等於沿用同一個未證明的步驟。**這是 arming 的前置條件，不是本輪能宣告解決的。**

## 6. 接續

1. ~~解決或界定 cache 同步~~ **已排除**（見上）。原本列出的替代接點評估仍有價值：找出能對目標 context 生效的路徑，或改用不需熱改 text line 的接點（舊 stage1 評估過 `C09185B0` 的 v1 vtable 指標並拒絕，理由是 v1 有不呼叫 `C023E9D0` 的 gate-false 路徑，無條件發布會把舊 H/L 誤算成新 evaluation——這個理由對幾何四接點同樣適用）。
2. USB 恢復後：`--level count` 做第一次上機，只看 `hits` 是否隨半按／CAF evaluation 遞增，`overlaps` 必須為 0。
3. 通過後才 `--level record`，一次視窗、一次匯出，收 64 筆 H/L。
4. 之後才是 EP83：由相機主動推，主機不必來要。

重跑：

```sh
cd projects/fp-af-assist
python3 -B -m unittest discover -s highrate -t . -p 'test_*.py'
python3 -B highrate/af_hook_trial.py --inspect --output NEW_DIRECTORY
```
