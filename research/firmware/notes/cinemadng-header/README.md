# CinemaDNG 每幀檔頭（fp 5.02）

2026-10-14 Gyro2 工作階段（`aef4d18e`）的離線研究報告，原樣從該階段 scratchpad 存入，未再改寫。全部未上機；[V]／[I] 標記見各檔。

| 檔 | 內容 |
|---|---|
| [HDR_CDNG.md](HDR_CDNG.md) | 模板怎麼建、每幀怎麼改（20 筆表 `C0B9ED9C`＋observer `0xC31AC4EC`）、對焦距離的寫法、sup 能否註冊 observer（§0.6） |
| [HDR_PRODUCERS.md](HDR_PRODUCERS.md) | 模板裡 580 個標籤各自的產生者、大小、是否每幀改寫 |
| [HDR_READERS.md](HDR_READERS.md) | 相機自己會讀回哪些標籤（錄影中、回放、機內顯影）；**MN 0x33 不可刪，否則錄影中 assert 當機** |

用到的地方：
- Gyro2：改用 observer＋自己的 tag 寫陀螺資料（`projects/gyro-sup/notes/GYRO2_CAMERA_DESIGN.md` §11 待更正）。
- Lossless：開錄時用 observer 加私有 tag **0xFD4C**（UNDEFINED×0xA00）預放壓縮 IFD，完成時只寫 tile 欄位、表與根指標（`projects/lossless-sup/validation/20261014-observer-tag/`）。Gyro2 的 tag 要用別的號碼。
