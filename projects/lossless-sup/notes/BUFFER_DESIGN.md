# fpLossless 緩衝區設計：原生 frame、獨立 codec 輸出與生命週期

## 當前入口 — 2026-09-30

最新實作與阻擋項見 [PROGRESS §14](PROGRESS_20260930.md)，優先於下方歷史快照。
新增 [`frame_pipeline.c`](../../../fpSup/lossless/frame_pipeline.c)：只保留一個待壓來源的
lease（session／take／frame、buffer、metadata、writer identity、容量與完整 stock 檔案長度），
不配置影像、不建待壓 queue 或完整批次 pool。原生 hold／defer／handoff adapter 尚未提供。

OFF：全部 RAW。ON：空閒時接當前幀；忙時後來的幀全部原樣 RAW 通過；codec 靜止且完整
輸出驗證後，只交回保存的同一來源幀。原生 writer 接手來源、且不再借用 codec 輸出，才釋放
這個工作槽並接下一個到來的幀，不必等 SD 整批寫完。完整壓縮 DNG 不比 stock 小時，原幀
RAW 交回而非停錄；真正錯誤／不明 ownership 則保留至清理證明完成。停止須主動收完末幀，
不能依賴下一幀觸發。這是已做離線測試的 policy，不是已完成的韌體 pipeline。

舊非同步探針用 block A 放 template／state／size table、block B 放輸出，A、B 各 4 MiB；
它把前幀寫到後幀，driver 的 arm 已停用，不再作新流程的建置入口。

**不能把「SD 持有原生 frame」當成「codec 跨幀必定能讀」。** 來源可能在 batch flush／停錄時
被釋放，須有完成前持有的證據；allocation 持有紀錄也不等於 DMA／IRQ 已停。
新版以保存的同幀 identity 避免前幀內容寫入後幀；native adapter 還缺持有與同幀提交證據。
零輸入拷貝不是 codec 原地覆寫；仍須獨立驗證輸出容量、來源尾端、停止與 release。

使用者本輪的「動態抽幀壓縮」是抽選幀去壓縮，不是丟棄未選幀或改 VFR；時間戳由同幀
metadata 保留，不自行重建。沒有加入多池、額外 worker 或通用 scheduler。
分帶與 A/B 合併留到 FHD 閉環之後。

## REC 前預留工作區

使用者定案：**在原廠錄影開始占用 RAW 池之前，先正式配置壓縮工作區，再讓原生錄影使用剩餘空間。**
這個順序已實作在 `native/rec_workspace.c`，配合 `raw_workspace.c` 與 `workspace_layout.c`，
完成主機整合測試及 ARM 編譯；RAW descriptor 呼叫另有 ARM 執行測試。尚未安裝 REC hook、
提供真實 producer facts 或上機驗證；不新增通用 pool／排程器。

程式順序是：確認前一 take 已排空 → 完成原廠 REC prepare／`MOVIE_REC_DNG` 配置切換 →
讀取實際格式 →
以自己的 descriptor 從 RAW/class 10 預留一塊有界工作區 → 確認原生來源仍有足夠餘裕 →
通過既有 REC readiness gate → 放行原生錄影啟動。不能等第一幀到 writer 才搶配置。

這個入口須在**每次 REC** 執行，包括已經停留在 mode 3 的第二次錄影；只掛在 memory-map
切換函式會漏掉暖啟動。亦不可在開機的 STILL map 先拿 RAW 區再跨模式保留，因為換 map
會重建該池。確切 hook 與跨 task 先後關係仍需指令／生命週期測試，見 PROGRESS §13。

錄影期間只重用這塊工作區，不逐幀申請或釋放；空閒可接下一個到來的幀，忙時後來的幀 RAW
通過。工作槽空閒不等於把 arena 歸還 allocator。停錄／啟動取消後，要等 worker、codec DMA
及所有輸出使用者退出，再正式歸還；模式切換前不得留下自有 RAW allocation。

容量依本次 geometry、位深、對齊及表格計算，不固定拿全池的一個百分比。
當前 output 是 packed raster 大小的 benefit-only 預算，不是已證明的 codec 最壞輸出界限；
硬體寫界未證明前不得提交。14-bit 僅支援容量計算，control 尚未開放該格式錄影。
6K14 原生來源約 43 MB 只證明來源所需容量，**不是無損壓縮最壞輸出的安全上限**。
來源尾端若必須複製補齊，該額外 input 也須在同一 REC 前置階段配置及納入預算。
預留失敗、原生餘裕不足或容量界限未證明時，撤銷已確認無使用者的新配置並回報未就緒，
不得偽造 Lossless ready 或繞過 `fpl_begin_direct`。不在 REC 中途重新搶一塊大緩衝。

先前 16 MiB 只量到 USER/class 0；CDNG map 的 RAW 名義容量約 708 MiB，RAW_SUB 82 MiB
是其 fallback，不是無主空間；YUV／JPEG 在此模式也回到 RAW，不能重複計算。
本方向使用正式配置及釋放 API，不硬寫固定地址、不改原廠分區表、不借 still 的全局 descriptor。

## 9/27 設計快照（以下保留歷史，不作現行執行順序）

更新：2026-09-27。狀態：C2 單幀 copy-back 已寫卡；連續重用／批次進度與硬體上界尚未成立。  
範圍：FHD RAW12、512×368 tiles、固定 lossless；保持現有同步 encode 與單節點 writer。

## 1. 決定

**當前採原生 frame + 一塊 encode scratch 的 copy-back 基線，不先實作自有 output pool。**
依 [C1](../build/ledger-c1-frame-survey-20260926.json)、[C2](../build/ledger-c2-copyback-20260926.json)：

1. 在當幀 context 同步 encode 到 scratch；保留來源直到 codec 與當幀 header snapshot 完成。
2. 以實際 tile sizes 組完整 DNG，驗證 `file_bytes = 0x13800 + sum(tile_sizes)`。
3. 只有完整檔案及實際 copy 範圍都不超過原 `seg[1]`，才複製回原生 DNG 起點。
   **`seg[0]` 不改，只改 `seg[1]`。** 不借 allocation 前 8 KiB、尾端間隙或其他 frame。
4. 下游持有原生 buffer，scratch 沒交給 SD；codec/header/copy 完成後才可重用。
   這避免 G5 的單 arena 跨幀被 SD 持有，不代表原生 batch policy 已對連續壓縮驗證。

C2 只證明一幀、encode 13,753 µs；沒有量到 copy 成本，也不是 C3／sustained。
PHASE 7 的放不下留 RAW 是研究探針行為；fixed-lossless 產品不默認採 mixed fallback。
最新工作順序與 zero-copy 限制見 [`CURRENT_DEVELOPMENT.md`](CURRENT_DEVELOPMENT.md)。

**以下 §2–6 保留 9/24 自有 output slots 備案，僅在恢復 pointer redirect 時適用；
不是本輪實作清單。** 不新增 worker、通用 pool、journal 或動態 scheduler。

當前問題不只是「記憶體不夠」：G5 的八次 encode 後，檢查的 frame 1、2、4、8 內容相同，
且第四次 encode 長度與讀回檔案不符。payload 與 writer descriptor 的逐幀關係都要查。
G3 的 372 µs submit return 不能當成可重用通知。
證據：[G3](../build/ledger-g3-20260923.json)、[G5](../build/ledger-g5-sustained-20260923.json)。

9/24 找到 CinemaDNG 現成的逐幀完成回呼 `C03A55D0`。自有 slots 備案優先借用它，不新增通知框架；
SD cache 保存 range descriptors 而非整幀副本，小 pool 還要與批次送出政策配合。
靜態證據與舊筆記訂正見 [`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md)。

## 2. 自有 slots 備案的最小資料結構

錄影前配置 `slots[N]` 與 N 個獨立 arena；錄影中不 alloc/free。小型 slot descriptors 放在
獨立 CPU 控制區，不貼在可能被 codec 越界的 payload 後。

```c
struct output_slot {             // 設計草圖，不是已實作 ABI
    uint32_t handle;             // 原 allocator handle，交给 writer
    uint32_t cpu_view;           // 已驗證的 CPU 存取 alias
    uint32_t payload_capacity;
    uint32_t file_bytes;
    uint32_t generation;         // 每次租用遞增，避免舊事件釋放新幀
    uint32_t state;              // FREE / BUILDING / HELD / ERROR
    uint32_t submit_active;      // 原 submit 尚未返回
    uint32_t release_seen;       // 已證明最後讀者放手
    uint32_t native_frame;       // 原生 cookie；關聯值，不取代原 cookie
    uint32_t native_frame_id;    // 提交時快照，用於核對，不是 PTS
    uint64_t source_seq;
    uint64_t source_pts;         // 預留未來抽幀，不代表已取得曝光時間
    uint32_t seg[2];            // 穩定的 {handle, file_bytes}
};
```

全域僅需 `accepting`、下一來源幀號、fault 與使用中數量。現有順序呼叫者管理 slots；
completion 若從另一 context 抵達，只發布事件，不做配置或 I/O。共享欄位使用短 critical
section／已驗證的事件機制，不靠 `volatile`，也不假設 ARM32 的 64-bit 欄位能原子更新。

generation 只有在事件可攜回原 request identity 時才有效。若 backend 只有可重用的 pointer，
不能自行猜是哪一代；輪轉重用仍不啟用。暫不增加獨立 request pool；slot 保守持有到
該 request 終態與 callback 已退休。若兩者晚於 buffer release，延後回收即可。

## 3. 選取與寫入

```text
取得當幀 source / source_seq / PTS
  -> 找一格 FREE，設 BUILDING
  -> 在現有來源 call context 同步 encode 到該格 payload
  -> 用當幀 metadata 建 header，檢查 tile sizes / guard / file length
  -> 固定該格 seg = {handle, file_bytes}，設 HELD，submit_active = 1
  -> 經原 writer 註冊／提交，保持原呼叫回傳語意
  -> submit 返回只清 submit_active，不直接設 FREE
  -> 最後讀者 release + request/callback 結束，才回 FREE
```

每次線性掃描少量 slots 即可；不需要 queue framework，也不以 `source_seq % N` 強制覆蓋。
從 HELD 開始，header、payload、tile arrays、seg 都不可改。

`FUN_c069ac88` 會將 `seg` 的 pointer/length 複製到 writer node，**不會複製 payload**；
`FUN_c069ade0` 再從 nodes 建 scatter list。保留自有 seg 不能自動解決原廠 node 的壽命，
仍需確認 register→真正 submit 之間的 pointer/length 沒被別幀替換。

來源在 encode 與當幀 header snapshot 完成前保持有效；不要把原 source pointer 留給延後工作。
每幀 header 使用 live entries，不能只重用 reference frame 的非 layout 欄位。

## 4. Output slot 的具體版面

沿用已成功寫卡的 contiguous header+payload。令 arena 大小為 `S`，尾區固定 64 KiB：

| 區域 | 相對位置／大小 |
|---|---|
| 原始當幀 header copy | `0 .. 0x133FF`，78,848 B |
| 新 root IFD、tile arrays、padding | `0x13400 .. 0x137FF`，1,024 B |
| codec payload | `0x13800 .. S-0x10000-1` |
| output guard | `S-0x10000` |
| codec final / temporary tables | `S-0xF000` / `S-0xEC00` |
| 現行 template / metadata 工作區 | `S-0xE000` / `S-0xDC00` |
| allocation-end guard | `S-4` |

```text
payload_capacity = S - 0x10000 - 0x13800
file_bytes       = 0x13800 + encoded_bytes
```

只把 `file_bytes` 交給 writer，尾區不進檔。保留 codec 已回報的合法 EOI 後零 padding。
每格用原 allocator 的獨立 handle／已驗證 alignment；CPU alias 沿用 G4 的契約，不猜地址。

現行 `S=4 MiB` 的 payload capacity 是 **4,048,896 B**，不是 4 MiB。
**這是現行實驗版面，不是任意輸入都安全的容量證明。** 現行模型已改為整數 14 bits/sample，
FHD 512×368 為 3,957,888 B，但未含 byte stuffing，不能用平均壓縮率或簡單抽樣縮減緩衝。
16 MiB 也只是條件式保守候選，尚未
證明 allocator／完整硬體契約；推導留在 [BUFFER_RESEARCH §4](BUFFER_RESEARCH.md#4-output-slot-的具體版面)。

9/24 source 已修正兩個入口：`compress*` 共用容量預檢；ARM sum 比較
`WORK_CAP - OUT_OFF`，不是整個 `WORK_CAP`。本次只核對 source，未重跑先前測試。
但事後 sum／guard 仍不能阻止已發生的 DMA 越界；新增 live run 前仍要確認所選配置的
安全邊界。暫不做通用 layout generator。

## 5. 何時釋放

一格只有在以下條件全成立才回 FREE：

- token 對應本次 slot/generation，所有資料與 guard 檢查通過。
- 原註冊／submit 呼叫已返回，沒有 caller 還在使用 descriptor。
- 已證明下游不再讀該格 bytes；request 已終態，且 backend 保證不再 callback。

completion 可以在 submit 返回前發生：只設 `release_seen`，等 `submit_active` 清除再回收。
写入失敗即設 ERROR；不以 RAW 重試，不釋放所有權不明的 arena。release 不代表資料已耐斷電，
clip 成功仍要看原 writer 的錯誤／close 結果。

**已定位候選：原生逐幀完成回呼 `C03A55D0(frame, status)`，尚未證明自有 arena 可在此重用。**
正確路徑是 `C069ADE0 -> C0366168(+0x18) -> C03686C0 -> C063B898 -> C063F380`；
批次經 `C063F140 -> C0646C60` 後對各 cookie 通知。movie cookie 是原生 frame pointer，
不是 0；舊筆記混用了其他路徑。原生 callback 會解參考 frame，不能改塞 slot index。

以小型 slot 陣列保存 frame pointer/id 與 slot/generation 關聯，保留原 callback 的行為。
原 callback 前先快照 identity，返回後不再讀可能已回收的 frame；只有最後讀者、原 callback
與 submit caller 都已結束才回收。下層傳輸返回、錯誤及批次進度仍須驗證。
查清前只作每格用一次的有界實驗，不用 sleep 或 REC stop 猜測安全時間。

## 6. 格數、滿載與停止

第一個離線／有界生命週期測試採 **N=2**；只驗證两格不混用，不宣稱能持續錄影。
相機配置需先確認容量與 allocator；以現行 4 MiB 實驗版面估算，兩格為 8 MiB，未含小型控制區。

正式 N 在量到 acquisition→safe-recycle 的持有時間後決定。固定約 24 fps 可先以
`ceil(24 * hold_seconds) + 1` 規劃，再用壅塞測試修正；這不是用時間取代 release。

**另須先驗證原生 batch policy。** 初始化可設定約 64 MiB aggregation 門檻；少量 slots
可能先用滿而沒有 completion，不能把這直接診斷成卡慢。壓縮變小也會改變批次回收節奏。
原生 `C03A5190/C063F310` 是送出並停用 aggregation，不是隨意可用的 flush-only；內部
`C063F140` 的呼叫 context／鎖尚未確認，不直接呼叫，也不以配置 64 MiB 自有池作預設解法。

- 沒有 FREE：停止接受新的壓縮工作，透過已驗證 recorder error/stop 路徑結束 fixed clip；
  不覆寫、不假成功、不提交零長 node、不偷偷改 RAW。
- stop 先關閉新 admission，處理已接受幀；所有下游讀者／callbacks 確定退出才 free 或卸載。
- 等待有上限；逾時保留 ERROR slots 與 callback code，回報未完成，不能無限卡住或強制 free。

若安全的 recorder stop 路徑尚未接好，就不做會碰到 pool-full 的 fixed 長跑。初期限次診斷可
明示只重導向兩幀、其餘保持原廠路徑；它不是 fixed-lossless 成品，且兩格仍須等確定安全才回收。

## 7. 未來抽幀只預留三件事

保留 `source_seq`、`source_pts`，並讓「是否保留此幀」的判斷位於取得 slot／encode **之前**。
未來 DROP 就不取大 buffer；現在不實作 DROP、sidecar 或壓縮預測器，不讓這些阻擋 buffer 修復。

## 8. 下一步與驗收

1. 先補 `bound-probe-two` 兩區 ownership／回收與失敗判定；它是來源／目的分離的研究版面，
   **不是兩格 output ring**。現有手填第二 handle 及「scratch 跑兩次」流程不構成完整方案。
2. 確認資料確實觸界、size 有效與 guard 結果；encoder 拒絕或小輸出不能判硬體 bound 通過。
3. 在 copy-back 基線補實機 post-encode/copy 與完整 call 成本，之後才做有界 C3 八幀與 batch 進度。
4. 若重新選擇自有 slots，才執行下列備案驗收與正式 N sizing；不以加大 N 掩蓋不釋放。

自有 slots 備案的驗收保留：

- 每格使用前／提交後 bytes 與當幀一致；manifest 記 `source_seq, slot, generation, pointer,
  length, pre-submit hash, filename, readback hash`。不能只看可解碼，亦不能要求靜態場景必有不同 hash。
- 故意延後 release，下一幀不覆寫舊格；第三次需求在兩格皆忙時正確拒絕。
- inline／晚到／重複 completion 不誤釋放；未知 request identity 不允許重用。
- stop／錯誤後沒有提前 free；容量邊界與每幀 metadata 正確。

本次只更新設計筆記，沒有新增 runtime 程式、執行相機測試或宣稱上述驗收已通過。
現行 source：[host probe](../../../fpSup/raw/lossless_codec/single_frame_codec_probe.py)、
[ARM probe](../../../fpSup/raw/lossless_codec/single_frame_encode_discard_probe.S)。
先前較完整的多池／動態框架討論保留於 [BUFFER_RESEARCH.md](BUFFER_RESEARCH.md)，非目前實作清單。
