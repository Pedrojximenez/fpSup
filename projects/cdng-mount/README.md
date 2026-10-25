# cdng-mount — 把 JPEG XL 存檔掛成一般磁碟，讀取時才在 GPU 解壓

目標：達芬奇直接匯入 / 播放一個看起來是普通 CinemaDNG 序列的磁碟；實體只存壓縮過的存檔。
解碼器是獨立專案 [`projects/jxl-metal`](../jxl-metal/README.md)（標準 JPEG XL 無損，Metal，逐像素一致）。

## 掛載方式（2026-10-24 驗證）

macOS 能把**本機 HTTP 伺服器上的映像檔**掛成區塊裝置：`diskutil image attach http://127.0.0.1:PORT/x.iso`
（舊的 `hdiutil attach http://…` 也可，但已標示 deprecated）。系統只發 Range 請求讀需要的部分。

驗證：3 MB 的 ISO9660/Joliet 映像由 `validation/http-attach-20261024/range_server.py`（Python，支援 Range）提供，
掛成 `/dev/disk13`，檔案內容與原檔 `cmp` 一致，伺服器收到 14 個 206 Range 請求。
不需要 kext、macFUSE、FSKit 或付費開發者帳號。

## 合成 HFS+（2026-10-24 驗證）

`src/hfs.rs`：唯讀 HFS+（TN1150）即時合成。卷宗標頭、空間配置表（全滿）、extents B-tree（只有標頭）、
catalog B-tree 在啟動時建好；檔案內容在被讀到時才由回呼產生。`src/main.rs` 是支援 Range 的 HTTP 伺服器。

| 規模 | 結果 |
|---|---|
| 2 資料夾 × 3 檔 | 掛載成功，6/6 檔逐位元一致 |
| **1000 片段 × 1000 幀 = 100 萬檔，虛擬 12.6 TB** | 建構 2.5 s、掛載 0.66 s、列根目錄 6 ms、列一個片段 23 ms、找一個檔 11 ms、`find` 全部 100 萬檔 3.6 s；隨機 30 檔（各 12.6 MB）逐位元一致 |

重現：`cargo build --release && ./target/release/cdng-mount test PORT DIRS FILES SIZE manifest.txt`，
`diskutil image attach --readOnly --nobrowse --mountPoint MNT http://127.0.0.1:PORT/volume.img`，
`python3 validation/hfs-1m-20261024/verify.py MNT manifest.txt`。

限制（目前）：catalog 整個建在記憶體裡；header node 的 map 記錄最多涵蓋約 6.3 萬個 8 KB 節點（約 100 多萬檔），
再大要加 map node 或改成即時計算節點；名稱只接受 ASCII；檔案各一個連續 extent。

## 架構（草案）

```
.cdngj 存檔（JXL 幀 + 索引；格式見 projects/cdng-image）
  → 本機 HTTP 伺服器（Rust）：Range → 哪幀 DNG 的哪段
  → jxl-metal 解碼（批次、快取、順向預讀）→ 排回 Bayer、12-bit 打包、DNG 檔頭
  → diskutil image attach → 達芬奇
```

既有可沿用的部分：projects/cdng-image 的 `archive.rs`（存檔與索引）、`iso.rs` / `virtual_disk.rs`
（ISO9660 + Joliet 磁區即時合成，`read_sectors`）。缺的只有「HTTP Range → read_sectors」與 GPU 解碼接上。

建議存檔編碼：`cjxl -q 100 -e 7 --faster_decoding=1 --buffering=0 -g 0`（見 jxl-metal README）。

## 待確認

- 存檔格式沿用 cdng-image 的 .cdngj，還是另訂？
- 讀取模式：達芬奇讀 DNG 時的 Range 大小與順序、需要多少預讀。
- 回放時 GPU 與達芬奇共用的實際佔用。
