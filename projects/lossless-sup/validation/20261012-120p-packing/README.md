# 120p：DNG 封裝工作區候選

使用者回報 240p 嚴重卡頓後，明確要求不要再嘗試 240p／USB 診斷，改以 120p 優化。
本輪後續只做離線工作；**尚未部署這個候選，也沒有取得新的 120p 相機計時**。
本輪開始時、該限制提出之前的一次狀態讀取回報 NO_DEVICE，之後沒有再操作相機。

## 為何會有逐幀的新尾表

原始 RAW DNG 沒有這個壓縮尾表。LOSS 讀取的是該幀原廠表頭的 IFD，
保留原廠欄位，將 RAW strip 的描述替換成 JPEG 壓縮與 tile 的寬高、offset、byte count。
目前把新 IFD 放在壓縮資料後面，是保留原廠表頭內容、減少版面重排的實作選擇，
並不是 lossless 必須有尾表。

壓縮大小與 tile 長度逐幀不同，相關位置／長度必須更新；曝光、時間碼等資料也要對應同一幀。
固定 tag／type 等資訊理論上可以做模板，但不能把整份第一幀的資料直接套到後續幀。
本輪三個固定場景樣本的 58 個原始 IFD entries 相同；這不足以證明在曝光、ISO、模式、
鏡頭或 metadata 狀態改變時仍相同。見 `metadata-sample-comparison.json`。

## 這個候選做了什麼

每條 codec 通道增加 4 KiB CPU 專用工作區，合計 8 KiB，沒有多加 RAW 幀。
先一次讀入該幀的原始 IFD，在工作區完成驗證與尾表，再將完整尾表連續寫回。
全部資料寫回後，最後才發布根 IFD 指標。工作區不交給 DMA、不跨函式保留借用。
超出工作區容量的合法 IFD，使用相同的有界直接寫入流程。

不改 64 MiB 批次門檻、位置公式、RAW 記憶體保護、兩通道／單引擎，
也不改 Ruari 的獨立 STOPFX。重建沿用原有 builder 與 loader ABI，只換 LOSS BIN。

## 已取得的證據

以同一個相機 DNG 表頭與相機 JPEG tiles 執行編譯的 ARM 指令，檔案內容逐 byte 相同，
精確 EOF 外的位元組不變，根指標是唯一且最後的根指標寫入，stack／callee-saved registers 保持。
只有記憶體 read/write callback 是替代；不模擬相機的 DMA、排程或 SDRAM 等待。

| 封裝 | 檔案區域讀取 | 檔案區域寫入 | 執行指令 |
|---|---:|---:|---:|
| 前一輪已部署版本的封裝來源 | 363 | 237 | 9,479 |
| 工作區候選 | 183 | 204 | 20,615 |
| 工作區不足，直接寫入 | 366 | 237 | 13,358 |

候選的非快取檔案交易從 600 降到 387，約減少 35.5%；讀取減少約一半。
**指令數反而增加**，不能只根據交易數宣稱相機 CPU 已下降。
內嵌函式實驗只略減至 20,414 指令，會增加程式尺寸，沒有採入產品來源。
完整資料見 `arm-trailer-results.json`、`arm-inline-results.json`。

離線檢查：

- 基本尾表 25 項測試通過，包含直接／工作區兩路的逐 byte 比對、LibRaw 解碼、
  邊界保留、零寫入拒絕、工作區恰好容量及 mutation 檢查。
- 額外覆蓋 1–160 個 tiles 的合成表格封裝、最大合法 IFD 的容量不足回退，以及接近表頭尾端的 IFD。
  原有 host reference 固定 12 個 FHD tiles；第一次額外測試因此被 reference 拒絕。
  改用獨立 reference 模組設定合成 tile 數後重跑，不修改共用 reference，不宣稱這些是合法 FHD 編碼幾何。
- Frame hold 164 項先通過；另一項因 mutation 的舊函式名稱錨點報錯，
  錨點更新後該 mutation 套件重跑通過。沒有將初次 165 項呼叫的失敗標為成功。
- 實際保存的正式候選 BIN 16 項 ARM 測試通過；診斷 BIN 16 項亦通過，
  原生 pool／registry／completion callback 與 ABI 使用現有 harness。
- 初次獨立 ARM probe 被 ELF extractor 拒絕 relocation，改用正式 builder 相同的內部連結規則；
  下一次 probe 的模擬 stack 與 RAM 映射重疊，修正後才取得上表。失敗日誌保留。

## 候選與下一步

正式候選 `candidate/10LOSS.BIN`：80,800 bytes，
SHA-256 `890210a9ae4ef086e2141ce535b461f6ee73b376322b81eefed227fa38891f66`。
診斷候選 `profile/10LOSS.BIN`：81,248 bytes，
SHA-256 `aa1885e29b9cc71e1db4b2f52b1fe81393dc28a67082da5626a0a2c4cf3cfff0`。
正式候選不含分段計時陣列；兩者都尚未寫入相機卡。

相機回到待機、USB 可用後，先核對實際 119.88p 模式，包含 sensor／engine 的有效幀率，
避開 nominal carrier 看似 120p、實際仍跑 240p 的情況。
比較同一個 120p 條件下 LOSS OFF、前一輪版本 ON 與候選 ON 的任務負載、
封裝 CPU 時間、RAW fallback、媒體等待、位置與配置回收。
不以加大緩存或降低 64 MiB 門檻代替這項比較；本輪不能宣稱 120p／240p 已修復。

機器可讀狀態見 `status.json`。相機最後已驗證載入的仍為前一輪
`fe35400b3354ff2218c4f3d83ada0f7bc5fe3bd8c8ed9abc12a26a9e45049e4d` 版本；
使用者之後的手動設定／試錄狀態未知。未 commit、push、更新發佈品或公開部署。
