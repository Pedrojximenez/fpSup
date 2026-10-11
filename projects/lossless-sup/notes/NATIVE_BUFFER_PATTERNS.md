# 原廠緩存機制：借用現有完成通知，不另造框架

> **9/30 入口更新：** 當前狀態見 [PROGRESS §10](PROGRESS_20260930.md)。
> 9/29 已有原生寫回、縮短 node 與聚合批次量測；下方仍保留 9/24–27 的靜態研究及當時順序。
> 現行不另建完整批次 pool；原廠 ownership／完成通知可作來源持有與回收研究依據，
> 但「批次通常累積多幀」不是跨 batch／停錄時 codec 來源的保留保證。

日期：2026-09-24。範圍：SIGMA fp Ver.5.02，離線反編與映像核對；沒有操作相機或實作 hook。
本篇補充 [`BUFFER_DESIGN.md`](BUFFER_DESIGN.md)，並訂正當日早先 writer-chain 的錯誤。
`[C]` 是靜態程式事實，`[I]` 是推論，`[P]` 是待驗證設計；不是新增 live pass。

**9/27 狀態更新：** 本文保留 9/24 原生機制調查；當前開發入口改看
[`CURRENT_DEVELOPMENT.md`](CURRENT_DEVELOPMENT.md)。C1 已在同模式兩次量到 clone counters=0、
owner=`0xFFFFFFFF`、DNG 起點為 allocation+`0x2000`；C2 單幀 copy-back 已成功。
因此「先驗 callback 比 copy-back 直接」不再作共同工作順序，callback/slots 留作備案。
9/24 選單切換未關掉 SD aggregation，是該測試路徑的結果，不是證明韌體絕無其他關閉方式；
也不需要為此重試同一選單。原生 buffer 與 batch 的連續進度仍未驗證。

## 0. 9/30 新實作所需的原生證據

單工作槽 [`frame_pipeline.c`](../../../fpSup/lossless/frame_pipeline.c) 已在 host 與 ARM 執行，
但尚無 native adapter。要借原廠機制的是**來源 hold、完成通知和恰好一次回收**，不是複製整個 pool。
忙時 RAW 通過是 policy；讓原廠 writer 在另一幀被延後時繼續前進，仍需原生證據。

本輪核對 [`blk_c03.c`](../../../out/decomp/full/blk_c03.c) 與部分原始指令後，新增以下限制：

| 位置 | 事實及影響 |
|---|---|
| `C03A5490` / `C03813D0` | 148 B writer 在 caller stack；內部 list/node 指向自己，不可保存或淺拷貝作延後提交 |
| `frame+0x1030` | pathname，不是 writer descriptor |
| `C03A54F4/F8` | flush 的 r0/r1 同為 0 是失敗，不是「沒有立即寫卡所以成功返回 0」 |
| `C03A5248/52D0` | observer 確實登錄／通知；不可忽略 completion |
| `C037DD50` | creator `+0x1C` 單一 active ID，忙時只把後來 frame 放入 `+0x10` FIFO |
| `C0377150` | worker 從 registry 解析 message 的 ID；v4 返回不清 active ID |
| `C0376F20` | 清 active ID，dispatch FIFO 下一幀；不是來源 hold API |
| `C037DF40 → C037E008` | 通常先回收 frame `+0xFE8/+0x138` 再推進；提前呼叫會破壞延後幀資源 |
| `C0377008 → C03805D8` | mailbox 只複製 8 B message，不是整幀 lease |
| `C0376488` | `frame+0x10FC` 是可重用登錄索引（kind 1 至多 `0x60`），不能作永久 sequence |
| `Dup2/C0374BF0` | 分配新 frame／format、註冊 clone，再維護 owner refs；不是可直接套用的 AddRef |

前四項由 [`test_native_writer_contract.py`](../../../fpSup/raw/lossless_codec/test_native_writer_contract.py)
執行真實映像的有限路徑驗證；FIFO／registry／Dup2 是靜態研究，沒有把它們算進 live 或全鏈 pass。
舊 [`ledger-static-late-submit-20260929.json`](../build/ledger-static-late-submit-20260929.json)
保留，但其中零回傳成功、無 observer、pathname=writer 的前提失效。舊 skip 實驗不能否定所有合法 defer。

後續先追 `C038BD98 → enqueue`、`C038C058 → C037DF40`、`C0398D88 → stop/drain`：
找出獨立保留整幀與 metadata 的途徑，並證明 creator 推進／來源補交各自恰好一次。
不能只提前推進再讓晚到 completion 再推一次，也不能以 64 MiB 批次推估保留期。
通過前不安裝新的 native hook，舊 inline driver arm 已停用。

## 1. 結論：有，而且最值得借的是 CinemaDNG 自己的完成回呼

| 原廠機制 | 可以借的部分 | 現階段不搬的部分 |
|---|---|---|
| CinemaDNG → SD scatter aggregation | 原生 frame cookie、批次完成後逐幀通知 | 不另建大型 RAM cache；不能把 submit return 當 release |
| RAW frame owner／clone | handle 與容量分開、最後引用才回收 | 不偽造原生 frame、不把未知 RAW ring 當自有空間 |
| AudioFileWriter + 固定訊息池 | 固定數量、滿了明確失敗、短臨界區 | 暫不新增 thread／mailbox／通用 pool；descriptor 回收不等於 payload 回收 |

**若恢復自有 output slots，優先驗證原廠 `C03A55D0` 能否承接完成通知**，並查清小 pool
與 batch 的相容性。目前 copy-back 沿用原生 buffer ownership，不先複製整套 queue。

## 2. 必須先訂正的呼叫鏈 [C]

早先 [`ledger-writer-chain-static-20260924.json`](../build/ledger-writer-chain-static-20260924.json)
將 vtable 開頭兩個 words 當成方法而偏移了 8 bytes，錯追到 `C03689C8`。
保留原檔供追溯，但其下游鏈與「不經 C063F380」結論不再採用。

映像 `out/seg0_c0000000.bin`，以 `0xC0000000` 為 base，`C0B972C4` 的實際內容：

| 相對 vtable 位移 | word | 用途 |
|---|---|---|
| `+00 / +04` | `00000000 / C0B9731C` | 表頭，非兩個方法 |
| `+14` | `C03685B0` | v3，plain write |
| `+18` | `C03686C0` | v4，scatter write，`C0366168` 實際 dispatch |
| `+20` | `C03689C8` | v6，另一個 pathname 操作，不是這次 scatter write |

正確主鏈：

```text
C03A5348 CinemaDNG 當幀 writer
  -> C069ADE0  nodes -> {scatter_pairs, count, frame_cookie}
  -> C0366168  vtable +0x18
  -> C03686C0 -> C063B898 -> C063F380
  -> 保留 range descriptors／必要時送出批次
  -> C063F140 -> C0646C60 -> 逐 cookie 呼叫 C03A55D0
```

movie 的 cookie **不是 0，而是當前 frame 物件指標**：`C03A5348` 呼叫
`C069ADE0(local_writer, frame)`。映像 `C03A5488..C03A5490` 是
`E1A01004 E28D0020 EB0BD652`，即 `mov r1,r4; add r0,sp,#0x20; bl C069ADE0`。
其他路徑以 0 呼叫不能套用到 movie。原生 callback 會解參考這個 frame，絕不可換成 slot index。

## 3. SD cache 實際保留什麼 [C]

`C03A5050` 初始化 CinemaDNG 時，配置 class 0 的 `0x40000`（256 KiB）輔助區。
當 manager `+0xD` 的設定旗標啟用時，送入四個 words：

```text
{ 0x04000000, helper_pointer, 0x00040000, C03A55D0 }
```

常數表 `C0B9E5D8` 實際是 `04000000 00000000 00040000 C03A55D0`；pointer 執行時補入。
經 `C0366790 -> C0369058 -> C063B908 -> C063F220` 設定 volume aggregation。
**64 MiB 是批次累積門檻，不是額外配置了 64 MiB 影像副本。** 門檻還會依 volume 幾何對齊。
這個模式存在於靜態路徑；G3/G5 當次旗標值仍須直接驗證。

`C063F048` 遍歷 scatter ranges，透過 volume `+0x483C` 交給底層 descriptor builder。
其中 `C065F060` 把實體 pointer 與編碼後 length/flags 存入每筆 8 bytes、最多 1024 筆的表。
只有未對齊開頭至多 3 bytes 會複製到小輔助區，**不是整幀 memcpy**。
另一個裝置 backend `C0670338` 也保存 pointer/length descriptors，不能從「cache」一詞
推論 payload 已經被備份。裝置 callback 選擇見 `C0644E30 -> C01EB8E0 -> C01F03E0`。

`C063F380` 在尚有批次資料時，將 scatter 的第三個 word（frame cookie）放入
volume `+0x4854` 陣列；計數在 `+0x4850`，最多 `0x80` 筆。沒有 pending bytes 時，
可以當場呼叫完成 callback。因此 callback 既可能延後，也可能 inline。

`C063F140` 的順序是：呼叫 `C0646C60` 處理累積傳輸 → 對每個 cookie 通知結果 →
歸還／重新取得 descriptor arena → 清批次計數。這使「快速提交、晚些才讀 payload」
成為 G5 重複內容的具體候選解釋；但仍不能省略 G5 的逐幀長度／檔名關聯驗證。

### 原生完成回呼

`C03A55D0(frame, status)` 更新完成統計，設 `frame+0x1104 = 0xD`，再以
`frame+0x10FC` 的 frame id，呼叫 `C03A52D0(manager, frame_id, 4, status != 0)`
通知原生生命週期觀察者。aggregation 關閉時，`C03A5348` 在 submit 後自行呼叫它。

這比從零設計通知協定更直接，但 **靜態看見 callback ≠ 已證明自有 arena 的最後 DMA
讀取已結束**。仍要核對下層返回語意、錯誤路徑、重複／缺漏通知與原生 callback 是否退出。
它也不代表耐斷電保存；資料生命週期與檔案成功是不同判定。

### 小 pool 與大 batch 可能互相等待 [I]

N=2 只能作兩格不混用的有界實驗，不能假設第二幀後自然收到 release。若原廠一直等批次
門檻而 producer 又等空 slot，就可能停滯，即使卡很快也一樣。實際還有 cluster 不連續、
descriptor 用盡、cookie 數量、plain write 等提早送出條件，不能直接拿 64 MiB 除檔案大小
宣稱正式所需格數；聚合計數包含按檔案系統幾何補齊的 bytes。

**壓縮檔變小，也可能延後原生批次完成。** 所以連 copy-back 借原生 frame pool 的方案，
都要重驗批次進度；原 RAW 能持續錄影，不等於縮小檔案後仍有相同回收節奏。

`C03A5190 -> C03667E0 -> C0369100 -> C063B950 -> C063F310` 會送出後
**停用 aggregation**（清 `+0x4828` 與 `+0x484C`），不是一般 per-frame flush。
內部 `C063F140` 雖保留 aggregation，尚未證明能從自有 context 安全呼叫；不可繞過
原本鎖與狀態管理。接下來先找原生進度保障／可用送出邊界，不直接改門檻、不配置大池硬撐。

已確認的 stop/drain 上游是 `cDevt_stop(C038C3C0) -> C0398D88`：它用 `C0376300`
掃描原生 frame 狀態，仍有 `0xB` 時等待；已無 `0xB` 等較早階段、表中仍見 `0xC/0xD` 時呼叫
`C03A5190(manager,0)` 排空並停用底層聚合；已無待處理項再以參數 1 完整收尾。
此處不是 free-slot 數量判斷，不能據此宣稱正常錄影時有低水位自動 flush。
這是待驗證的進度風險，並非已觀測到 deadlock。

## 4. RAW frame 管理可借的生命週期 [C/P]

- `C001CFD8` 建立 `{handle, actual_capacity, allocator_class}` descriptor；
  `C001D038` 回報實際容量。可借這種分離方式，不把 file length 或相鄰地址間距當容量。
- `C037A990` 的 RAW descriptor 在 frame `+0x68`，使用 class 10、`0x400` alignment。
- `C0374BF0`（Dup2）讓 clone `+0x1118` 保存 owner frame id，owner `+0x1114` 引用數加一。
  `C03777B8` 在最後引用歸還後才經 `C0374180 -> C001D3D0` 釋放原始配置。
- `C0381090 / C0381008` 的原生 FIFO 使用 lock/head/tail，frame `+0x110C` 是鏈結。
  知道這個規律即可；不把自有 slot 偽裝成原生 frame 插入原廠 queue。

因此「原生幀 buffer 一定是獨占」尚不成立。這組程式證明有 owner/clone 機制，不是證明
當前 movie 每次都有 clone；copy-back 前必須確認該 seam 沒有其他 RAW 讀者。

### 把壓縮檔複製回原生 buf：保留候選，不當成已成立捷徑

[`IMPLEMENTATION.md`](IMPLEMENTATION.md) 早先提出 copy-back 值得比較，但需收緊：

1. tapseg 的地址範圍／spacing 只能推測 pool 分布，不能定案「固定 28 格」；不能把
   `0x31A400` spacing 當作該 `buf` 全部可寫容量。
2. 74 幀 mark-only 是在 padding 寫一個 word，不是完整 RAW 被覆寫後仍無其他讀者的證明。
3. 在 descriptor base/capacity 確認前，最多以原 `seg[1]` 作候選 copy 長度上限；還須確認
   整段可寫與排他性。模型的 `4,037,760 B` 檔案大於原 `3,244,544 B`，先因容量淘汰，
   不是只討論複製時間。
4. 必須等 codec 不再讀來源、當幀 metadata 保存完成、完整 copy 與必要 cache 維護完成，
   才改長度提交。scratch 到此才能重用；下游生命週期只是轉由原生 frame 承擔，並未消失。
5. G4a 測的是反方向 mirror；用其速率估 copy-back 僅是成本假說，不是 24p 通過證據。
   class 0／10 不同也不代表沒有 DRAM、頻寬或 allocator 壓力競爭。

以上為 9/24 的安全疑問；9/26 C1/C2 已提供部分實證，copy-back 現作單幀基線。
尚未消除的限制與下一步見 CURRENT_DEVELOPMENT，不把當時的優先序沿用到現在。

## 5. AudioFileWriter：可抄規律，不抄整套 [C/P]

`C01FBC80` 將 offset、payload pointer、length 放入 24-byte 訊息，送入 mailbox；
`C01FBD40` 的 writer thread 收訊息、seek／plain write，最後 `C01FC138` 歸還訊息。
`C01FBB18` 解構路徑送停止訊息、join，再清理 writer。這是未來 async 的參考，不是首版前置。

其 `MPoolFixed<24,32>`（`C01FCA80 / C01FCDF8 / C01FD0F8`）有 32 格，每格
24 bytes 使用區加 12 bytes 管理區；短臨界區中 acquire/release，滿了回 0，歸還時核對
範圍與 busy magic。少量 output slots 用陣列 busy/state 就夠，不必抄 free-list 或借 audio pool。

尤其 **歸還 message 只釋放 descriptor，不自動釋放它指向的影像資料**。thread join 也
不是另一條 SD 路徑的 payload fence。plain write 經 `C03685B0 -> C063B818 -> C063F898`，
與 scatter 不同，並可先觸發 `C063F140`；不能用 G3 的 scatter 延遲斷言 gyro 只靠時間差安全。

## 6. 自有 output slots 備案的證據鏈 [P，非本輪主線]

1. 離線補齊 `C0646C60` 返回／失敗語意與原生低水位送出路徑，確認 small pool 不會因批次
   政策失去進度。未確認前不接自有 flush，不改 cache 設定。
2. 未來另獲上機授權後，先觀察原生路徑：當幀 `frame pointer/id → node pointer/length →
   submit → C03A55D0(status)`；同步記錄 aggregation flag 與批次 bytes。這輪不改資料所有權。
3. 通過後，自有 slot 以小陣列關聯 `(native_frame, native_frame_id, slot, generation)`。
   在真正 submit seam 依 output pointer 找 slot，保留原 frame cookie 及原 callback 行為。
   callback 前快照 identity，原 callback 可能促成 frame 回收，返回後不再解參考 frame。
4. 只有已證明最後讀者結束、原 callback 返回、submit caller hold 清除，才允許該 slot 重用。
   inline、延後、錯誤、stop 與 pool-full 先驗證；不靠 frame pointer 單獨猜 generation。
5. 確認 release 與 batch policy 配合後才決定正式 N。source_seq／PTS 與 encode 前決策位置
   保留給未來抽幀；frame id 不是曝光時間，也不在這次引入動態 scheduler。

## 7. 重查入口

反編行號可能隨重新匯出改變，以上述函式地址搜尋；相對本檔的原始檔：

- [`blk_c03.c`](../../../out/decomp/full/blk_c03.c)：media vtable wrapper、RAW owner/clone、CinemaDNG init/write/completion。
- [`blk_c06.c`](../../../out/decomp/full/blk_c06.c)：scatter、aggregation、裝置 range descriptors、writer nodes。
- [`blk_c00.c`](../../../out/decomp/full/blk_c00.c)：allocator handle/capacity descriptor。
- [`blk_c01.c`](../../../out/decomp/full/blk_c01.c)：AudioFileWriter、MPoolFixed。
- [`seg0_c0000000.bin`](../../../out/seg0_c0000000.bin)：vtable、常數表與 movie cookie 指令核對。

以上 §1–7 為當時的文件更新紀錄；當輪沒有改 runtime source、重跑 codec 測試、操作相機、改卡或部署。

## 8. 9月30日原生 pending 與 teardown 指令驗證

最新主線改為無選單直接啟用、USB shell、Fast Start 2；詳見
[PROGRESS §12](PROGRESS_20260930.md#12-直接啟用壓縮與-usb-shell-測試版)。
新增 `test_native_defer_contract.py` 真實指令測試，不再只靠反編推測。

`C038BFF0` 在 metadata 更新後、creator enqueue 前，可候選為選幀接點。
`C037DD50` 前綴到 `C037DE08` 會把真 kind1 幀設為 B，但未占 active/FIFO；
暫留 10、先正常處理 RAW 11、再正常 enqueue/complete 10 的指令序列成立。
普通 `C0398D88(1,take)` 等待 B、`C03752A0` 不清 B；因此不能把單一 creator active
直接解讀為「根本無法先讓後來 RAW 通過」。

但 B **不是完整引用租約**：`C0375030` 可直接交給 destructor，另一 stop 分類
`C0375BE0` 不等待 B，THR 狀態離開的 `C0398D18` 會全表回收。真正接線必須在這些路徑
使用來源前後建立排他／drain；只攔 free 或手改 refcount 不成立。真 IRQ callback 不依赖
MovRec task 收訊息，因此 pre-drain 可考慮等自有 codec worker 退出；不可在同 task 等原生
檔案完成。這還不是已證 scheduler 或 DMA fence，詳細證據／替身界線以 §12 為準。
