# LOSS 提前封裝與幀索引交接 — 2026-10-12

已部署並完成兩段 29.97p 短錄；59.94p 的嚴重操作延遲已定位到 LOSS 開啟時的 CPU 負載與低優先序任務延遲。高幀率問題尚未修復。手動停錄後已恢復連線、確認資源歸還，並完成同條件 LOSS 開／關任務耗時比對，詳見文末。

## 改了什麼

1. 壓縮完成後，先把該幀的原始表頭複製到 spare，完成壓縮 DNG 的 IFD 與 tile 長度表，再交換原廠幀的配置紀錄與像素指標，最後入列。
2. 寫入端只修正實際檔案長度，不再重建 DNG，也不再逐項搜尋紀錄。
3. 每個 native id 對應一筆 20 bytes 的交接資料：檔案緩衝區、最終長度、原始長度、幀描述位址、generation。兩條通道各保留自己的短表；每幀最多查看兩個指定位置。
4. 每條通道只需一份 640 bytes 的 tile 長度工作表，封裝後即可重用。檔案內已有自己的 tile 長度表，不必再為所有待寫幀各保存一份。
5. 表頭、tile 長度或容量不合規時，在交換配置或複製壓縮像素前退回原始 RAW。幀編號重用時檢查 generation；身分、緩衝區與原始長度不符時不套用舊資料。

copy-back 備援路徑先檢查並完成 trailer，再複製壓縮像素。正式雙 spare 路徑則在 spare 裡完成封裝後才交換配置。

原生 64 MiB 批次目標、位置數公式、RAW 記憶體 admission 機制與 buffer 釋放責任維持原狀。STOPFX 保持獨立，作者為 Ruari，未修改其實作。

## 記憶體比較

以下為 ARM 編譯器對 1016 個位置版本的實際結構尺寸；不是影像壓縮率或上機耗時預測。

| 項目 | 修改前 | 修改後 |
|---|---:|---:|
| 每位置交接紀錄 | 676 bytes | 20 bytes |
| 兩條通道的 hold 結構合計 | 1,374,624 bytes | 42,920 bytes |
| LOSS 整體常駐配置 | 5,976,064 bytes | 4,644,864 bytes |

新常駐配置約 4.43 MiB，主要仍是擴充的原生幀描述池。這次並未縮小每張 RAW allocation，亦未把 64 MiB 當成全部 RAM 用量上限。

## 產物

- [擴充位置候選 10LOSS.BIN](expanded/10LOSS.BIN)：79,456 bytes；SHA-256 `1df6ac89a36b6260000c793fcf9c2856236f1df629d839c3949ebae42136ddad`。
- [原有預設建置 10LOSS.BIN](default/10LOSS.BIN)：73,056 bytes；SHA-256 `7b623dae63b11706403fad434cadf368efadebd3f52b82e29e6309dacaad5b32`。這是預設 96 位置／既有提前批次策略，並未改為新的擴充策略。

與目前擴充位置試驗銜接時使用 `expanded`。載入格式、檔名與共用 loader ABI 未改，沿用現有 AutoRun／LOADER。expanded 已寫卡並完整讀回核對，正常重開一次後載入。未發布，亦未更新 merge 頁面。

從專案根目錄建置（輸出目錄必須為新目錄）：

```sh
python3 -B fpSup/lossless/build_v3_lossless.py --expand-slots --out projects/lossless-sup/validation/20261012-early-dng-handoff/expanded
python3 -B fpSup/lossless/build_v3_lossless.py --out projects/lossless-sup/validation/20261012-early-dng-handoff/default
```

## 驗證與限制

- 177 項主機測試通過：同幀內容、入列時已完成 DNG、兩通道交錯、RAW fallback、generation／buffer／id 檢查、停錄回收、trailer 與記憶體初始化，以及對應錯誤注入。
- 16 項針對儲存的 expanded BIN 的 ARM 測試通過：高編號 1015、兩通道指定紀錄讀取、writer 不改寫檔案內容、原生池／registry／完成回呼、64 MiB 門檻。
- 52 項 loader／hook 測試與 6 項 LOSS／STOPFX 整合測試通過，包括兩種載入順序及關機還原。
- 隔離 BIN 刻意移除索引乘法，確實被新測試的讀取位址斷言攔下。`mutation-index-stride` 僅為錯誤注入證據，不得部署。
- Unicorn 2.1.4 的全域 MEM_READ hook 會使這段 Thumb IT 執行改變；同一個 helper 在沒有該 hook 時正確、有 hook 時錯誤。最終測試將追蹤限於實際紀錄區，保留錯誤注入驗證。未修改產品機器碼來遷就模擬器。

測試日誌與機器可讀結果見本目錄各 `*-tests.log`、`mutation-index-stride.log`、`layout-sizes.json` 與 `status.json`。`before` 保存本輪修改前的主要來源。

離線結果未證明先前 119.88p 卡住的問題已全部排除；本輪亦未繼續測試 119.88p。

## 本輪上機結果

只替換 `10LOSS.BIN`，原檔與 Ruari 的 `05STOPFX.BIN` 均已備份。寫入回覆逾時後沒有重送，依原生完成狀態、精確目錄長度及完整讀回確認 SHA-256 與候選檔相同。新 boot 為 12117900。STOPFX 的載入 hook 正常。

| 測試 | 完成寫入 | 壓縮幀 | 停錄後空位／容量 | LOSS 初始化 | 第一幀到達 |
|---|---:|---:|---:|---:|---:|
| FHD 29.97p 第一段 | 108/108 | 107 | 404/404 | 18.482 ms | 591.604 ms |
| FHD 29.97p 第二段 | 112/112 | 111 | 408/408 | 11.288 ms | 561.458 ms |

兩段各保留一幀原始 RAW。registry、完成 cookie 及 writer 均回到閒置，每段釋放兩個 codec spare；封裝失敗、codec fault、長度不符均為 0。原生日誌均記錄 `bulk-size=67108864`。這裡的初始化與第一幀時間來自 LOSS 內部計時，不等於按鍵到 LCD 指示的實測時間。上一版兩段初始化分別為 159.268／149.337 ms，並非嚴格控制的效能基準。

A001_151 的第 1、2、108 幀讀回可解碼；第 2 與 108 幀為壓縮 DNG，12 個 tile 均有有效 JPEG 起迄標記，IFD、長度與尾端補零正常。這是抽樣驗證，不代表逐幀核驗全部片段。

59.94p 原生設定 enum 5／UI row 6 確認一致後，送出一次 REC 開始按鍵。六秒等待結束的狀態查詢逾時；停止按鍵尚未自動送出，沒有重複切換 REC。使用者確認相機持續錄影、非常卡頓，長按 REC 才勉強停止。手動停止後的一次只讀查詢仍逾時，已停止向相機發指令，等待確認寫入燈、選單及重新接入 USB。

以上逾時是第一次上機的當時狀態。後續在同一次開機成功恢復連線，取得該段 2,231/2,231 幀完成、428/428 位置歸還的證據；並非一直無法回收。這次優化確實縮短了起錄初始化，但尚未解決高幀率錄影時的嚴重延遲。

詳細記錄：`fhd-30p-take1.json`、`fhd-30p-take2.json`、`fhd-60p-take1.json`、`manual-stop-state.json`、`fhd-30p-take1-frames/validation.json`。

## 59.94p 卡頓診斷：CPU 與排程（2026-10-12）

**確認到任務層級：同一份 BIN、同一 boot、同樣 428 個位置及原廠 64 MiB 批次，LOSS OFF 可正常查詢與停錄；LOSS ON 使錄影時 CPU 接近滿載，較低優先序的畫面更新及 USB 通訊延遲。尚未把錄影管理任務的增加耗時細分到某一個函式。** 本輪只做診斷，未替換產品 BIN，未修改 STOPFX。

### 控制條件及量測方法

- FHD RAW 1936×1090、12-bit、60000/1001 fps、音訊 ON；同一張 UHS-II 卡、同一次開機 12117900。
- 首次 LOSS OFF 六秒比較 A001_154 完成 338/338 幀，USB 與配對 REC 停錄正常；428 個位置全部歸還。只切換 LOSS。
- 原廠 `analyzer` 任務切換紀錄採 32,768 筆固定環形緩衝，約 0.88 MiB，沒有每幀 USB 取樣。原先 LOSS ON 測量仍逾時，手動停錄後才取回的 CPU 摘要已被待機資料覆蓋，**不能用該 26.0% 數字表示錄影負載**。
- 最終兩秒比較在 ON、OFF 兩邊都暫時把已核對身分的 `_VSHL` 通訊任務由優先序 28 調至 10；其他任務優先序不變。如此能在錄影中準時保存摘要、停止 profiler 並送出一次配對停錄鍵。這是取得證據的診斷措施，不是產品修正。
- A001_157（ON）完成 111/111 幀，其中 104 幀壓縮、7 幀 RAW；A001_158（OFF）完成 85/85 幀。兩段各自確認 428/428 位置歸還。OFF 的 hold 統計保留上一段值，不能把它誤算成 OFF 也壓縮 104 幀。
- 第一次幀到達分別在 REC 準備後 547.520／757.276 ms；比較使用兩段 monitor 起點後 **1.1–2.1 秒**的相同長度區段，避開兩邊的起錄等待。完整摘要含起錄，所以其 86.0%／71.7% 不是下表的值。
- `read_task_ring.py` 只讀取已停止、且位址與大小符合原廠擁有配置的紀錄。`analyze_task_rings.py` 依 C002B718/C002B440 的實際時鐘換算及 C0682298 的歸屬規則離線統計；兩段完整摘要的總時間及 CPU 百分比均與相機輸出吻合。

### 實測結果

以下百分比是觀察窗內 CPU 時間，不是壓縮引擎的硬體忙碌比例，也不把 15 ms 的編碼等待時間當成 15 ms CPU 執行時間。原廠切換追蹤的開銷與可能包含的中斷時間在兩段都存在。

| 任務／指標 | LOSS OFF | LOSS ON |
|---|---:|---:|
| CPU 忙碌 | 83.18% | 97.29% |
| CPU 閒置 | 16.82% | 2.71% |
| CamSch 原廠相機排程 | 47.60% | 43.64% |
| MRecMgr 錄影管理 | 13.37% | 26.20% |
| FPLCODE LOSS 工作任務 | 0.80% | 7.89% |
| SRecFile 檔案寫入任務 | 3.28% | 4.03% |
| DrawMgr 畫面更新 | 2.64% | 1.44% |
| _VSHL 診斷通訊 | 0.15% | 0.16% |
| DrawMgr 相鄰執行起點最長間隔 | 56.919 ms | 249.030 ms |

ON 的最後三個 100 ms 區段均沒有閒置時間。DrawMgr 的間隔是任務切換紀錄，不是 LCD 端到端延遲量測；它與使用者看到秒數／按鍵延遲、影像仍正常的現象一致。

主要增加落在 MRecMgr 與 FPLCODE。原廠優先序數字越小越優先：FPLCODE 12、MRecMgr/CamSch 15、DrawMgr 17、CamMain 20、原本的 _VSHL 28。新增工作接近吃完原本剩餘的 CPU 時間，低優先序任務難以即時處理。提高通訊任務優先序後能準時取樣及停錄，支持通訊被排程延遲的判斷；並不證明選單延遲已修好。

### 記憶體與媒體證據

- ON 兩秒比較時 `pressure_raw=0`，RAW 可用量最低仍為 439,914,560 bytes（約 419.5 MiB），高於保留量 250,500,096 bytes（約 238.9 MiB）。CPU 卡頓已在未觸發記憶體保護時出現，因此不能歸因為必須等 RAM 用完。
- 較長的兩段手動停錄資料分別完成 2,231/2,231 與 2,786/2,786 幀；停錄後位置、registry、完成 cookie 與 writer 均歸還／閒置。第一段 RAW 使用峰值 601,861,312 bytes（約 574 MiB），停錄後使用量為 0；這些測試未觀察到持續洩漏，不代表所有錯誤情境都已驗證。
- 長錄影確實出現 RAW 記憶體壓力，第一段 900 幀壓縮、1,117 幀因保留量政策轉 RAW，另有 213 幀雙通道忙碌及第一幀 RAW。它是額外壓力，不能倒過來當成短測 CPU 卡頓的必要條件。
- 原生日誌均保留 `bulk-size=67108864`。長錄影的正常批次寫入多約 260–280 MB/s；沒有 codec stall/fault、表頭 DMA 失敗或 DNG 封裝失敗。第一段 `lookup_missing=59` 仍未定位，不能把這個診斷計數直接當成丟檔或 CPU 根因。
- 64 MiB 是寫入批次門檻，並非全部影格配置的 RAM 上限，也不限制每秒的壓縮／封裝／回收 CPU 工作量。428 個位置及 STOPFX 在 OFF 比較中同樣存在，因此它們單獨不足以重現本次卡頓。

### 修正方向與界線

目前到達 hook 在 C038BFF0 的 CinemaDNG 事件處理內呼叫 `fpl_card_arrive`，會收取已完成通道、複製表頭、建立 DNG trailer、交換配置並入列；並非只有獨立 FPLCODE 工作任務承擔新增成本。下一步應分別量測這條交接路徑與完成回收路徑，尤其表頭 DMA、封裝及批次完成回呼，才能確認 MRecMgr 增加的約 13 個百分點各自花在哪裡。現有 task profiler 不能把該增量全部判給其中一個函式，也沒有證明硬體壓縮的 CPU 成本就是全部原因。

保留 64 MiB 策略時，還需要 CPU 時間或壓縮幀率的預算：當即時處理餘裕不足，限制送入壓縮的頻率，其餘幀走 RAW，且仍受原本媒體吞吐量與記憶體保護約束。單純增加位置、取消紀錄搜尋，或只提高某一任務優先序，都不足以消除這次量到的負載。

這是每種條件一段的短時間 CPU 比較，不是長錄影穩定性驗收；59.94p／119.88p 仍不能標為已修復。沒有修改使用者要求保留的 64 MiB，也沒有將 STOPFX 併回 LOSS。

### 收尾與證據

兩段診斷後 `_VSHL` 均已還原 28；原廠 profiler 已停止並以原廠命令釋放配置，配置指標／大小回到 0。相機最後確認 CINE 待機、writer 閒置、29.97p（enum 3／UI row 3）、LOSS ON 且設定保存成功，428/428 位置歸還。未重開、未替換 BIN、未發布。

- `lag-cpu-comparison.json`：可重算的區段統計。
- `lag-protected-{on,off}-take.json`：完整操作、原廠 CPU 摘要、rec log、還原後任務優先序。
- `lag-protected-{on,off}-take-ring.{bin,json}`：停止後的原始任務切換紀錄與時鐘／配置資料。
- `lag-post-stop.json`、`lag-native.json`、`lag-profile-on-recovery.json`、`lag-profile-on-post-stop.json`：兩段手動停錄後的完成／記憶體證據。
- `lag-profiler-cleanup.json`、`lag-final-standby.json`：診斷工具釋放及相機最終狀態。

另一次診斷啟動因回覆文字格式檢查過嚴，在送出 REC 前停止；當時的通訊優先序已核對並還原，證據為 `lag-protected-on.json` 與 `lag-protected-no-rec-restoration.json`。修正檢查後才執行上述兩段比較，沒有對不確定的 REC 按鍵重送。
