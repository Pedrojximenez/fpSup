# 預先產生可切換的 RAW／壓縮檔頭：離線可行性驗證

使用者提出：hook 原廠檔頭生產，預備壓縮需要的欄位，讓同一份檔頭容易切換 RAW／lossless。
本輪完成原廠建表分支的 ARM 追蹤及一份可解碼的檔案原型。
**尚未安裝新 hook、修改 LOSS 的執行期程式或建置／部署新 BIN；沒有 120p 效能結果。**
使用者禁止再嘗試 240p；本輪沒有 USB、相機查詢、錄影、改卡或重開。

## 已找到的原廠接點

韌體：`out/seg0_c0000000.bin`，SHA-256
`aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`。
來源為實際 ARM 字組及 `out/decomp/full/blk_c00.c`、`blk_c03.c`、`blk_c05.c`、`blk_c06.c`。

- REC 初始：`FUN_c0378a50` 建立 CinemaDNG 的本次錄影物件。`C0378EB0: blx r2`
  呼叫 DNG format 的 header serializer；原廠隨後將返回的長度存到 frame `+0x14C`
  與單例 `C358DB98 +0xC`。單例 `+0x10` 是模板、`+0x8` 是格式物件。
  這是準備本次檔頭、記下有界欄位位置的候選接點；不是已安裝的 hook。
- 原廠建表值填入：`FUN_c06a5290` 原本已有 RAW／JPEG lossless tile 分支。
  主影像分支的 Compression 是 1 或 7；分別要求 273/278/279，或 322–325。
  原廠 tile 尺寸寫死 256×256，與目前 LOSS 的可選 grid 不同。
  **不能只開啟 DngTile 的旗標就當作整合完成。**
- `FUN_c00ba378` 是圖形中 tag 的查找／設定介面，找不到 tag 會返回 0。
  ARM 追蹤只證明原廠提出相應的 tag/type/count/value 設定要求；並沒有執行
  TIFF graph 配置與 serializer，也沒有證明新增 tag 已實際加入原廠圖形。
  `FUN_c00c1ca0` 及其 tag 初始化下游仍須接上預留版型。
- 每幀：`C038BFD0` 呼叫 `FUN_c038c5f8`，`XC_RecMgrTagCinema::v1 @C03A8490`
  及 observers 更新模板的時間碼／曝光等資訊。`FUN_c05a4bc0` 的設定位置可快取；
  不能擴充 IFD 後仍讓它沿用已失效的位移。
- `C038C77C` 將已更新模板 DMA 到該幀。Gyro2 已使用這個接點，RES-CUSTOM
  可能在內層 `C00FBB90` 使用 CPU copy；未覆蓋或修改任一既有 hook。

`native_builder_trace.py` 在 Unicorn 執行原廠 `C06A5290` 與原廠 descriptor／DngTile
accessors 的指令；只替代 tag setter、位深與 raster-size 查詢。使用 1936×1090／12-bit
fixture，原廠 256×256 grid 的 tile 數為 40（8×5）。確認兩條分支的參數、返回、stack
及 callee-saved registers。這不模擬配置器、DMA、serializer 或排程。

## 一塊檔頭、兩種主表

原型保留每幀原始 metadata 的位置，在同一塊 prefix 中預備兩個小型 IFD：

```text
TIFF 主表指標 ── 預設指向 RAW IFD（offset 8）
原有 metadata  ── Exif、MakerNote、曝光、時間碼等，兩種 IFD 共用
預備壓縮 IFD  ── Compression=7、tile 寬高與兩張長度／位置表
對齊 padding
像素／壓縮資料
```

RAW 與壓縮各有自己的 layout 欄位；輸出的 TIFF 根指標只選其中一種。
inactive IFD 不放進 top-level next-IFD chain。這保留現有回放路徑所需的 RAW 描述，
也避免同一個有效 IFD 夾帶相互衝突的 strips／tiles。

每次錄影先按 geometry、grid 與 metadata schema 計算版型／有界位置。
每幀更新所有 inline 非 layout 值；外部值與 opaque blobs 共用當幀原始資料。
壓縮完成時只寫 tile offsets、counts，**最後**才切換根指標。
無法壓縮的幀保留 RAW 根，不用重建整張 IFD。
geometry、tag/type/count 或引用位置改變時，不使用舊版型。

原型的 `prepare_frame()` 仍會解析／複製來源 metadata；這是離線參考，
**不是省 CPU 的原生 hook 實作**。實作 adapter 必須對接原廠每幀更新的已有位置，
或用一次建好的有界鏡像位置表同步所有 inline 值；不能把第一幀的值凍結到後續幀。
提前建表只是移除壓縮完成階段的重建，不能把準備成本當成消失。

## 驗證結果

13 項測試通過，完整紀錄為 `prototype-tests.log`：

- 同一份 prepared prefix 的 RAW 與壓縮輸出，LibRaw 解碼均與原始 RAW 逐像素相同。
- 使用相機 `A001_165` 的第 2 幀 JPEG tiles，壓縮 payload 完全不變；新檔與原相機
  壓縮檔的 LibRaw samples 相同。sample `real-camera-prepared.DNG` 可供檔案檢查。
- 所有非 layout root 值、Exif、MakerNote／其他 opaque ranges 保留；測試刻意更改
  當幀 inline WhiteLevel 及 Exif ExposureTime，確認壓縮主表與共用資料會更新。
  不靠固定場景的相鄰幀相同來判定 metadata 可凍結。
- 12 tiles 完成階段為 **25 個邏輯 32-bit 寫入**：12 個 offsets、12 個 counts、1 個根指標。
  tables 為 word-aligned；其他 prefix bytes 不變。這是 host 原型操作數，並非 ARM
  指令數、非快取匯流排交易數或相機 CPU 百分比。
- malformed size/count/sum 零寫入拒絕，保留 RAW。覆蓋 1 tile 的 inline TIFF 值、
  合法 160 tiles 的上界及超限拒絕；這些合成 payload 不宣稱可 JPEG 解碼。
- 隔離 mutation 故意提前發布根指標、凍結 inline metadata，相關驗證均能偵測。
- 原廠 ARM RAW／tile 建表參數追蹤分別通過。

FHD 範例原 prefix 為 78,848 B，新 prefix 為 79,872 B，增加 **1 KiB**；
160 tiles 範例增加 2 KiB。位置由 IFD 尺寸與 tile 數推導，不固定套用 1 KiB。
相機 sample 的 hash、長度與明確限制見 `prototype-results.json`。

首次執行的離線模擬因主機 sandbox 的 JIT 權限以 exit 132 結束；首次 host 測試
亦遇到原型匯入路徑錯誤。修正匯入路徑並以已允許的本機 JIT 執行權限重跑，才取得
成功紀錄。host encoder 的既有 reader 發出未關檔 ResourceWarning，未改其來源。
未把首次失敗列為通過。

## 實機接入仍需完成

1. REC header generation adapter：有界預留空間、原廠圖形／模板配置的容量、長度發布，
   非 CinemaDNG／LOSS OFF／初始化失敗皆原樣通過。不能只依記憶體範圍猜配置容量。
2. 每幀 metadata adapter：驗證 schema 與當幀所有權；同步 inline 值並保留原廠既有
   更新順序。沿用 loader 的 hook claim／journal，核對 Gyro2、RES-CUSTOM 的鏈。
3. frame hold／writer：目前 `frame_hold.c` 固定 `0x13400` prefix、`0x2000` file offset。
   新長度必須從實際 descriptor／已驗證版型導出，容量、stock/compressed 長度與
   DMA 範圍一致。記憶體 charge 與 positions 的估計亦要計入新檔頭。
4. 機內回放：現有 decode 保留 RAW IFD 的設計可以沿用，但 native RAW 回放也要
   驗證新的 pixel offset／header length；外部 LibRaw 能讀不能代替相機回放證明。
5. 正式 BIN 的 hook ABI、初始化／關機還原、RAW fallback、動態 metadata、
   allocation/registry ownership 離線驗收；相機待機確認後才做 119.88p 有界量測。

64 MiB 的原廠批次門檻、兩通道／單壓縮引擎及獨立 Ruari STOPFX 均未修改。
原先 4 KiB 工作區候選仍未部署；本輪也沒有將新原型當作目前相機版本。

## 方向整理（2026-10-13 補記）

本段只整理既有證據與優先順序，未新增量測。估算均標明來源，不是相機結果。

### 預備檔頭能省多少

`20261012-pipeline-cost` 正式版（`fe35400b…`，FHD 59.94p）實測五段每幀 CPU：
表頭 DMA 0.022、尾表 0.427、入列 0.021、引擎設定 0.304 ms；等待＋完成修補每次 0.105 ms、
約每幀 1.9 次。合計約 **0.98 ms／幀**，其中尾表約 44%。

若按幀數線性外推到 119.88p（**未量測**；尾表成本取決於 IFD 大小，不隨 geometry 縮小）：
五段約 11.7% CPU，尾表約 5.1%。預備檔頭把尾表換成 25 個字組寫入，可去掉的大致就是這一項，
加上逐幀把 IFD 讀出未快取區的讀取。它不減少引擎設定、DMA、批次回呼或 MRecMgr 的其他增量。
在 FHD 59.94p，同一算法只有約 2.6%；本方案主要對小 geometry／高幀率有意義。

### 與 120p 工作區候選的關係

`20261012-120p-packing` 的 `890210a9…` 是同一目標（尾表成本）的低風險版：只換 LOSS BIN，
非快取交易 600 → 387，但 ARM 指令 9,479 → 20,615。預備檔頭是終點方案，但要新增 REC 初始化與
每幀 metadata 兩個 hook。兩者不必同時做；先用候選量出「尾表在 120p 實際佔多少」，
再決定是否值得投入原生接入。

### 建議順序

0. **先查擴充位置池是否放在非快取記憶體而拖慢高幀率**：240p 在未載 LOSS 時曾穩定；擴充版 LOSS 載入即換掉原廠描述子池，
   且放在 NonCache 常駐區，HSW 有同類實機失敗紀錄。詳見 `notes/PROGRESS_20261013.md`「240p 為什麼以前穩、現在卡」。
   這一項可能比尾表大得多，應先於下面各項。
   靜態追查另見同頁「補記 2」：原廠 registry 的 11 個全表迴圈被固定擴到 1016 格，且在 NonCache 上掃描；
   優化順序已改為先修迴圈終點、池位置與「能用 96 格就不擴充」，尾表退到其後。
1. **先取得 119.88p 基線**（需使用者授權相機操作；不碰 240p）。從 rec facts 讀實際 geometry 與
   sensor／engine 有效幀率，以 10/12 的保護優先序方法量 LOSS OFF、`fe35400b` ON、`890210a9` ON。
   M12240 119.88p 先前控制無反應，尚未證明是 CPU 飽和；先確認原因，再談封裝優化。
2. 不做執行期 CPU 預算閘門（使用者決定，2026-10-13）：大家的機身相同，引擎時間幾乎不隨畫面內容變化
   （TILE_GRID 鏡頭蓋對照只差 1–3%），所以每個模式的負載可以事先在一台相機上量定。
   若某個 geometry／幀率量出來 CPU 不夠，直接在該模式固定政策（例如限定壓縮比例或不提供 ON），
   不在每幀動態判斷。
3. 若 120p 量測顯示尾表仍是主要可省項，再依「實機接入仍需完成」1–5 項接入預備檔頭，
   順序為：REC 初始化 adapter 的容量證明 → 模板層（`C038C77C` DMA 前、快取記憶體）同步 inline 值，
   與 Gyro2 共用接點 → `frame_hold` 由固定 `0x13400` 改為 descriptor 導出（FHD 為 `0x13800`）→
   完成階段 25 寫 → 機內回放。每步都先 Unicorn／host 驗收。
4. 次一個可省項是引擎設定 0.30 ms／幀；`FUN_c05a4bc0` 設定位置可按 take 快取，
   但須先證明哪些欄位逐幀不變，不得凍結動態值。

### 介入時機：在檔頭之前（使用者提議，2026-10-13）

現行 LOSS 在 `C038BFF0`（幀交給 creator）介入，此時原廠已在 `C038C77C` 把模板 DMA 進幀；
完成後再把原廠 IFD 讀出、在 spare 的非快取區重建尾表，這就是「回寫檔頭」的成本來源。

改在檔頭產生之前介入，也就是讓原廠模板本身帶著預備好的壓縮 IFD，就由每幀原有的表頭 DMA 一起搬過去，
CPU 不必再讀寫整張 IFD。唯一做不到事先寫好的是 tile offsets／byte counts：它們在壓縮完成後才存在。
因此完成階段仍剩 25 個字組（12 offsets、12 counts、根指標），這是下限，不是本方案的缺陷。

再往後推、把該幀的表頭 DMA 延到壓縮完成後才發，雖然可以連這 25 字組都在 cached 模板裡填好，
但模板是全片共用的單例，下一幀的 observers 會在這期間改寫它，必須另存每幀的模板或動態值，
複雜度與風險都大於省下的幾微秒；不採用。

結論：使用者的方向就是本原型的接法——REC 初始化時把壓縮 IFD 放進模板（`C0378EB0` serializer 之後），
每幀在 `C038C77C` DMA 前同步 inline 值，完成時只寫 25 字組。優先序仍在 registry 全表掃描修正之後。
