# Gyro2：把陀螺資料嵌進 CinemaDNG，讓 Gyroflow 外掛直接讀 (2026-10-06)

目標：Gyro2 把壓縮過的 IMU 資料寫進每張 CinemaDNG 的自訂 metadata，
由我們改過的 Gyroflow（telemetry-parser + OFX 外掛）讀出並轉成 Gyroflow Protobuf schema。

機身端設計（緩存、hook、零拷貝、與 lossless 解耦）見 [GYRO2_CAMERA_DESIGN.md](GYRO2_CAMERA_DESIGN.md)。

研究基準（上游 HEAD）：
- gyroflow/gyroflow-plugins `32ae998` (2026-09-07)，依賴 gyroflow-core `d918ab3`
- gyroflow/gyroflow `77b4940` (2026-09-28)，依賴 telemetry-parser `d45ebf2`
- AdrianEddy/telemetry-parser `d45ebf2` (2026-09-04)

---

## 1. 結論：Protobuf 或 JSON？兩種都支援，但我們都不需要

`telemetry-parser/src/gyroflow/gyroflow.proto` 是官方給相機廠的 schema
（`Main{magic_string="GyroflowProtobuf", protocol_version, Header, FrameMetadata}`，
第一則帶 Header，之後每幀一則 FrameMetadata）。它有兩種「線上格式」，最後都解成同一組
prost 產生的 Rust struct `gyroflow_proto::Main`，再走同一條
`process_header()` / `process_frame()` / `emit_lens_profile()`：

| 編碼 | 放在哪 | 偵測 | 程式 |
|---|---|---|---|
| 二進位 protobuf (proto3 wire) | MP4/MOV 的 metadata track，每個 sample 一則 Main | 前後 5 MB 內 memmem `GyroflowProtobuf` | `gyroflow/binary.rs::parse` → `util::get_metadata_track_samples` |
| JSONL (proto3 canonical JSON，一行一則 Main) | `.jsonl` 檔（直接開，或 mp4/mov/mkv 同名 sidecar） | 副檔名 jsonl + 欄位名 marker | `gyroflow/proto_json.rs` + `binary.rs::parse_jsonl` |

**對我們的意義：** 既然要改 parser，就在 Rust 裡把我們的壓縮格式直接解成
`gyroflow_proto::Main` struct，交給既有的 process_* —— 不必先序列化成 protobuf bytes，
也不必轉 JSON。`parse_jsonl()` 就是現成範本：它示範了「沒有 MP4 容器時如何自己造
`SampleInfo`（timestamp = frame_index / file_frame_rate）」。

**相機端不要寫真正的 protobuf：** 每個 IMUData 要 double timestamp + 3–6 個 float，
約 26–40 B/樣本；我們的 int16×3 是 6 B/樣本，再做差分壓縮會更小。2500 Hz、23.976 fps
下每幀約 104 筆 → protobuf ≈ 2.9 KB/幀，自訂格式 ≈ 0.3–0.6 KB/幀。ARM hook 也不適合做
varint/float 編碼。

## 2. 現況：今天的 Gyroflow 對 DNG 能做什麼

1. **telemetry-parser 不看 DNG 內容。** 各 parser 的 `possible_extensions()` 都不含 dng；
   `GyroflowProtobuf` 只吃 mp4/mov/jsonl。DNG 只有一條路：
   `util::find_gcsv_sidecar_for_image_sequence()` 找 `同名.gcsv` 或去掉幀號後的 `clip.gcsv`。
   ⚠ `.jsonl` sidecar 自動搜尋**只**對 mp4/mov/mkv，DNG 序列不會去找 jsonl。
2. **OFX 外掛直接吃 DNG 會失敗。** 外掛用 fuscript 問 Resolve 取得目前片段
   （fps、frame_count、duration、解析度、路徑；`[000000-000357]` 會換成第一幀路徑），然後：
   - 若旁邊有 `.gyroflow` 專案 → 讀專案（今天 DNG 唯一可行的外掛流程）；
   - 否則 `stab.load_video_file(..., metadata=None)` → `gyroflow_core::util::get_video_metadata()`
     只接受 `mp4/mov/braw/insv/360/mxf`，**DNG 直接 `UnsupportedFormat`** → 外掛顯示
     「Failed to load file info」並嘗試開 Gyroflow App。
   - 外掛手上其實已經有 Resolve 給的 fps/尺寸/幀數，只是沒傳進 `load_video_file`。
3. 外掛有 `has_accurate_timestamps` 判斷：資料源回 false 會自動開 Gyroflow App 做同步。
   `GyroflowProtobuf` 回 true（非 GPMD passthrough），所以走 protobuf 路線可以免手動同步。

## 3. fp CinemaDNG 檔頭：有沒有地方放資料

掃描本機 2,696 張 fp DNG（FHD / OG2K / OG3K / 3:2 / OG3K120，Ver.5.02）：

- 影像資料起點 `StripOffsets` 幾乎固定 **78,848 (0x13400)**；OG3K120 sup 改過的檔為 79,872，
  且 IFD0 變成 59 筆（多了 LinearizationTable）→ **我們已有在韌體端加 IFD 標籤、
  以 1 KB 為單位撐大檔頭的先例**（open-gate）。
- IFD0 有 `DNGPrivateData (0xC634)`：SIGMA 自己的 `SIGMA_EXTH_SPP…` 6,734 B，固定在 0x11956。
  之後只剩 92 B 到影像資料。
- 0xC634 前面有一段**沒被任何標籤引用的全零區**，長度隨 MakerNoteSigma（97 筆，長度可變）浮動：
  觀察到最小 **3,270 B**、最大 11,076 B。
- 不同模式間 IFD0 標籤順序/數量一致（58 筆），TimeCodes(0xC763)、FrameRate(0xC764) 都在。

兩種放法：

| 方案 | 相機端 | 讀取端 | 風險 |
|---|---|---|---|
| A. 寫進 0xC634 前的零區（不改 TIFF 結構），讀取端掃 magic | 最小：固定位址 memcpy | 讀檔頭 ~80 KB memmem magic | 未被引用的 bytes 會在 DNG 被重寫（Adobe DNG Converter、exiftool 改寫）時遺失；可用空間取決於 MakerNote 長度（最差約 3.2 KB） |
| B. 新增私有 IFD0 標籤（照 OG sup 的做法，撐大檔頭 1 KB） | 要改檔頭產生器（已有先例） | 正規 TIFF 解析取標籤 | 標籤號要避開已登記值；工具改寫時較可能保留 |

建議：**原型用 A，正式版用 B**；兩者的 payload 格式相同，parser 先找標籤、找不到再掃 magic。

> **2026-10-06 更正（來自 lossless-sup `tools/canonical_header.py`）：** 上面的「零區」落在
> **MakerNote 宣告的範圍內**，不是自由空間；保護好所有 IFD 與 out-of-line 值後，原檔頭合法空位只有
> DNGPrivateData 之後的 **92 B**。因此方案 A 不可用，Gyro2 必須擴充檔頭（方案 B）。
> 另外 lossless 目前把檔頭長度寫死為 78,848，root IFD 由主機預建樣板產生 —— gyro 在 stock IFD0
> 加的標籤在 lossless 路徑下會遺失，需要兩者間的檔頭契約（見對話紀錄 / 後續設計）。
>
> **2026-10-06 決定：** 那段零區正是 **MakerNote 的尾端**（宣告範圍結束於 DNGPrivateData 起點）。
> Gyro2 把資料當作 MakerNote 內容寫進尾端零區（同 sigma-fp-supmod 的做法），不改 IFD、
> lossless 不用改。擴充表頭 + 標籤 65000 降為容量不足時的備案。詳見 GYRO2_CAMERA_DESIGN.md §7。

## 4. 建議的 payload（每幀自我描述）

每張 DNG 放「涵蓋該幀曝光區間」的樣本，**每幀都重複一份很小的 clip header**
（序列被剪、改名、只拷一段也能解）：

```
magic 'FSG2' | ver | kind
clip:  imu_rate, gscale, ascale, orientation, readout_us, rec_start_us
frame: frame_no, start_ts_us(讀出第一列的時間), exposure_us
imu:   n, 首筆 int16×3, 之後 zigzag-varint 差分（時間由樣本位置推得，見機身設計 §3）
event: 水平儀/焦點 tag 插在其發生位置（或另列 {位置, type, value}），不存時間戳
crc32
```

翻譯成 proto 時：`Header.camera` = SIGMA/fp/lens（lens 由 EXIF/DNGLensInfo 補），
`clip.imu_sample_rate`、`frame_readout_time_us`（用 make_gyroflow_lens_profile.py 的模式表）、
`camera.imu_orientation`（已解出的軸向，見 GYROFLOW_ORIENTATION_SOLVED.md），
`FrameMetadata.imu[]` 每筆換成 deg/s、m/s²、`sample_timestamp_us`。
可順便填 `lens_profile`（直接 inline 我們生成的 profile JSON）→ 外掛不必另選鏡頭。

## 5. 我們的 fork 已有原型：ijigen/gyroflow-plugins `feature/cdng-protobuf`

commit `53aa262` (2026-10-04)，base = 上游 main `32ae998`（main 與上游 0/0 同步）。
鎖定 gyroflow-core `d918ab3` + telemetry-parser `d45ebf2`（與上面研究的版本相同，
`proto_json::to_jsonl_line` 存在）。本機沒有 cargo，**尚未編譯/跑測試**。

做法（只改外掛，不 fork core / telemetry-parser）：
- `common/src/cdng.rs`：讀 IFD0 **私有標籤 65000**（BYTE/UNDEFINED），內容 = 一則二進位
  `gyroflow_proto::Main`；把同目錄「同前綴 + 尾端數字」的整個序列逐檔讀出，
  驗證 magic/version、第一幀必有 Header、`frame_number` 必須 1..N 連續，
  再用 `proto_json::to_jsonl_line` 轉成 **JSONL 記憶體串流**。
- `common/src/lib.rs`：`.dng` 路徑走 cdng；用 Header 的寬高/fps/幀數組 `VideoMetadata`，
  以虛擬路徑 `xxx.cdng-<hash>.jsonl` 呼叫 `load_video_file(..., Some(md), true)`
  —— 繞過 core 的 `get_video_metadata()` 副檔名限制，並讓 telemetry-parser 走 JSONL 分支；
  載入後檢查 `per_frame_time_offsets.len() == frame_count`，再把 url 改回真正 DNG 路徑。
- `openfx`：Resolve 給的 `[0001-0100]` 只在檔名部分替換；Browse 加入 dng。

→ 這正好回答「必須是 JSON 嗎」：**DNG 裡放的是二進位 protobuf，JSONL 只是外掛內部
餵給 pinned telemetry-parser 的橋**（因為它的 protobuf 入口只有 MP4 track 和 JSONL 兩種）。

### 原型對真實 fp 素材的落差
1. **fp 的 DNG 沒有標籤 65000**，IFD0 58 筆後緊接資料區（0x2C6），無法原地加一筆
   → 相機端要照 OG sup 的方式重組檔頭（59 筆、strip offset +1024）。
2. **Gyro2 的壓縮格式要多一層解碼**：在 `read_private_tag()` 之後判斷 payload 開頭——
   是我們的 magic `FSG2` 且 kind = 壓縮格式就解壓並組出 `gyroflow_proto::Main`，否則照舊 `prost` decode。
   其餘流程（JSONL 橋、驗證、Resolve 整合）全部沿用。
3. **檢查太嚴**：任一 DNG 缺號、或只拷了序列中段（`frame_number` 不從 1 開始）就整段失敗。
   fp 掉幀或使用者剪片時會遇到；建議改成以第一幀 frame_number 為基準、允許缺號時插空幀。
4. 檔名：fp 為 `A001_001_20260817_000244.DNG`，尾端數字規則可正確切出前綴
   `A001_001_20260817_`；但若同目錄有跨日期的同片段（理論上不會）會被當成不同序列。
5. 「每幀都要有自己的標籤」：可以接受（per-frame 設計本來就這樣）。

## 6. 若不用 fork 原型、改 parser 的替代路線（參考）

**telemetry-parser**（核心）
1. 新增 `src/sigma/`（或擴充 gyroflow 模組）parser：`possible_extensions = ["dng"]`，
   `detect()` 在 MakerNote 尾端找我們的 magic。
2. `parse()`：由第一幀路徑推出序列（`trim_sequence_suffix` 已存在於 util.rs），逐檔只讀前
   ~80 KB，解 payload → 組 `gyroflow_proto::Main` → 照 `parse_jsonl` 的方式造 `SampleInfo`
   並呼叫 `process_header/process_frame/emit_lens_profile`（目前是 private，要改成 `pub(crate)`）。
3. 序列有上千檔：只讀檔頭、可平行；外掛已開 `cache-gyro-metadata` feature。

**gyroflow-core**：`util::get_video_metadata()` 加 DNG：寬高取 DefaultCropSize、fps 取
FrameRate(0xC764)、幀數 = 序列檔數。

**gyroflow-plugins**：DNG 時把 fuscript 得到的 `CurrentFileInfo`（Resolve 的 fps/幀數/尺寸）
組成 `VideoMetadata` 傳進 `load_video_file(..., Some(md), true)`，作為 core 失敗時的後援。

**相容退路（不改 Gyroflow）**：主機端小工具從 DNG 抽 payload → 產生 `.gcsv`（今天就會自動被找到，
但 OFX 仍需 `.gyroflow` 專案）或 `.jsonl`（只能在 Gyroflow App 手動載入）。

## 7. 待確認

- 每幀 payload 要在**該幀 DNG 寫出前**備妥：Gyro hook 每 VD drain 一次，需確認 DNG 檔頭組裝時點
  與 VD 的先後，以及「幀 N 的檔頭」對應的樣本區間（可多帶前後 guard 樣本，proto 規範也建議）。
- `start_timestamp_us` 用 TickTimer 定義的「第一列讀出時刻」需和 VD 對齊實測一次。
- 上游接受度：若想合併進官方，較可能被接受的是「DNG 私有標籤內放標準 GyroflowProtobuf bytes」；
  我們的壓縮格式較適合留在 fork 或以獨立 vendor parser 形式提交。
