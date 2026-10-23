# SIGMA fp 5.02：相機自己會從 CinemaDNG 檔／模板讀回哪些標籤

2026-10-14，純離線研究（未上機）。來源：`out/decomp/full/blk_c0*.c`（Ghidra）、`out/MAIN_c0000000.bin`（capstone 全映像 BL 掃描）、
實檔 `projects/rawview/captures/2026-09-24-dngcheck/A001_031_f000001.DNG`（自寫 TIFF 解析器）。
背景：`hdr_cdng.md`（模板建構與每幀寫入）。

證據等級：**[V]** = 反編譯／反組譯／映像表格直接看到；**[I]** = 推論。`blk_c05.c:146583` = 反編譯檔：行號。

---

## 0. 方法與完整性

1. 標籤讀取 API（MetaData 函式庫，`blk_c00.c:144099..144620`）[V]：
   - `FUN_c00b9f58(obj, ifd, idx)` 選 IFD：0=IFD0、1=IFD1、2=Exif(0x8769)、3=GPS(0x8825)、4=Interop(0xA005)、5=MakerNote(Exif→0x927C)、6=SubIFD(0x14A)、7=0xC6F5、8=0xC634（`blk_c00.c:144099`）。
   - 取值：`FUN_c00ba3e0(obj,ifd,tag,out,&size)`、`FUN_c00ba458(obj,ifd,idx,tag,out,&size)`、`FUN_c00ba4d8`（size=n*8）；
     取項目：`FUN_c00ba1b0`/`FUN_c00ba528`/`FUN_c00ba558`；MakerNote 容器屬性 `FUN_c00ba5a8`；串流（不整檔載入）`FUN_c00ba610`。
     回傳 0=成功、100=找不到。
   - 解析檔頭：`FUN_c00c1508(obj, buf, len, type, flag)`，**type 2 = CinemaDNG**（同 `FUN_c00c1ca0` 的 type 2）；轉換 `FUN_c00c16c8(dst, src, srcType, dstType)`。
   - 模板（已序列化）唯讀查詢：`FUN_c05a4ca8`（→ fmt vt+0x3C `C06A5188` → `FUN_c05a5228` → `FUN_c00bb830` → `FUN_c00bf360`）。
2. **對整個映像做 BL 掃描**（不靠 Ghidra 是否切出函式）：所有 `bl` 到上述 getter 的呼叫點共 190 個，再對 getter 包裝函式（`FUN_c03d56e8..FUN_c03d84d8`、`FUN_c05c1db8/1e40/1ed0/1f58`、`FUN_c06a8ec0/9738/98d8`、`FUN_c05a5000/5d88`）再掃一次（111 個），從呼叫前的 `mov/movw r1,r2,r3` 取出 ifd／tag 常數。
   Ghidra 漏切的只有 1 個：`0xC02B093C`（AWB vt+0x1C `C02B08F0`，讀 MN 0x11F）。
   getter 在映像中沒有任何資料指標（不經函式指標呼叫）；`FUN_c00be268`（IFD 內找 tag）在函式庫外沒有呼叫者 [V]。
3. 例外：MetaData 轉換器（`FUN_c00c2608/2728/2800`）用迴圈走過整個 IFD，按白名單或整個 IFD **複製**（不解讀值）。這類列為「複製」，不算「解讀」。
4. 沒做：縮圖（index）畫面的 CinemaDNG 繪製路徑沒有逐條追；推測它也走下面的播放／顯影管線 [I]。

---

## 1. 機內播放真的支援 CinemaDNG（問題 3）[V]

- 原始碼路徑字串：`src/library/CinemaDngPlay/src/XC_CinemaDngPlay.cpp`、`CinemaDngFileReader.cpp`、`CinemaDngYuvCopier.cpp`、`DngBufferInfo.cpp`、`DposPreReader.cpp`（映像 `0x2DFD2F0..0x2DFE800`）；
  log 字串 `"tag [%8d:%08X] TC = %02d:%02d:%02d:%02d"`、`"tiff get miss"`、`"pic setting cnt"`、`"tag miss cnt"`。
- 類別：`XC_CinemaDngPlay`(v0..v17，`blk_c05.c:143133..145255`)、`XC_CinemaDngPlayThread`、`XC_CinemaDngPlayAudio`、`CinemaDngFileReader`、`CinemaDngTagReader`、`CinemaDngYuvCopier`、`DposPreReader`、
  `PlayFileSearchCinema`、`PlayFilePathMgrCinema`、`PlayFileEraseCinema`、`PlayFileLockCinema`、`PlayFileMarkCinema`、`PlayFileTurnCinema`（`blk_c06.c:135652..139977`）。
- UI 字串：`Playback_Movie_CinemaDNG_WarningON/OFF`（`blk_c04.c:91583`）、`Playback_Movie_Save_DNG`、`Playback_Movie_Save_JPEG`。
- 路徑格式：`\CINEMA\` + `%c%03d_%03d`（clip 資料夾）／`%c%03d_%03d_%08d.`（幀檔），`FUN_c069b568`。檔案種類碼（file+0x1C）：**5 = CinemaDNG clip**，3 = MOV，3/6 也出現在 CINEMA 幀檔路徑 [V 程式；碼的語意部分 I]。
- `XC_PlayFuncSeqDngDeveloping::v32 @C03C8350`：`*(seq+0x30)==5` 時用 **type 2** 解析、讀 IFD0（`blk_c03.c:140956-140970`）→ 機內 RAW 顯影支援 CinemaDNG 幀。

---

## 2. 讀取者總覽（CinemaDNG 相關）

| 代號 | 函式 | 情境 | 每幀？ |
|---|---|---|---|
| P1 | `XC_CinemaDngPlay::v11 @C05BDB08` → `FUN_c05c1a58`、`FUN_c05c1bd8`（`blk_c05.c:143757,146661,146713`） | 開始播放：讀第一個檔的整個檔頭（type 2） | 一次 |
| P2 | `CinemaDngTagReader::v1` → `FUN_c05c1880`（`blk_c05.c:146583`） | 播放中每一幀：解析該幀檔頭（type 2） | **每幀** |
| P3 | `FUN_c05bc908` → `FUN_c05bb4a0`（`blk_c05.c:142888,141963`） | 播放中每一幀把該幀的 tag 物件送進顯影參數設定 | **每幀**（shading 只在第一幀／跳轉後 `param_2==0`） |
| D | `XC_PlayFuncSeqDngDeveloping::v32 @C03C8350`（`blk_c03.c:140864`） | 機內 RAW 顯影（含 CinemaDNG 幀，以及播放暫停畫面） | — |
| C | `FUN_c0386960` → `FUN_c0386eb0`/`FUN_c0386fc8`（`blk_c03.c:90774,91074`） | **錄影中擷取靜態影像**：停錄後把已寫入卡的 CinemaDNG 幀檔整檔讀回、type 2 解析、顯影成靜態影像 | 每張擷取 |
| I | `getPlayFileTagData @C03C1B18` → `FUN_c03bae30` → `setPlayInfo`／`FUN_c03bb0a8`（播放器是 CinemaDNG 時用 type 2，`blk_c03.c:130710`）→ 回呼 `FUN_c03c1fa8`（`blk_c03.c:135991`） | 播放資訊顯示（檔案資訊／拍攝資訊） | 一次 |
| M | `PlayFileMarkCinema` → `FUN_c06abce0` → `FUN_c06a9118` → `FUN_c06a9190`（`blk_c06.c:138749,136847`） | 標記（file type 3/5/6；type 5 自動找 clip 裡的第一個 `.DNG`），**在檔案上原地改寫** | — |
| T | `PlayFileTurnCinema` → `FUN_c06ad940` → `FUN_c06a9498` → `FUN_c06a9400`（`blk_c06.c:139991,136974,136948`） | 旋轉（type 3/5/6），原地改寫 0x112 | — |
| X | DngDeveloping::v35 `FUN_c00c16c8(src=2, dst=0/1)`（`blk_c03.c:141692`）；`FUN_c03cc380`/`FUN_c03cc420`（`blk_c03.c:143300,143327`，`+0xB0==5` 時 2→3） | 從 CinemaDNG 存成 DNG／JPEG：轉換器複製標籤 | — |
| R1 | 色彩 observer `FUN_c02b9010`（mode 2/3）→ 色彩物件 vt+0x28 `FUN_c02c79d0`（`blk_c02.c:115821,125361`） | **錄影中每幀**，讀**已序列化的模板** | **每幀** |
| R0 | 色彩 vt+0x10/0x14/0x24 `FUN_c02c6610/6870/7448`、`FUN_c02c4a50`；AWB | 建構模板時讀 **builder**（序列化前） | 開錄一次 |

P3／D／C 共用同一組「顯影參數讀取者」（下稱 **DEV**）[V]：
- `FUN_c02b8e88(tag)` → 色彩物件（`0xC3414C98`，vtable `C096FBE8`）vt+0x2C `C02C97F0` → vt+0x3C **`FUN_c02c89b8`**（`blk_c02.c:125975`）→ `FUN_c02d4898`、`FUN_c02d4ba8`（`FUN_c02d4f28` 也呼叫後者）。
- `FUN_c0044c18()`（`0xC307B7FC`，+0xC vtable `C0734D08`）vt+0x30 = **`FUN_c00448b8`**（`blk_c00.c:53647`）→ `FUN_c0045fc8()` vt+0x5C = **`FUN_c0045d90`**（vtable `C0734DF0`+0x5C=`C0734E4C`）、再依 MN 0x10A bit7 選 **`FUN_c004dd20`** 或 **`FUN_c0051510`**（鏡頭校正）。
- `FUN_c02da658()`（`0xC3425510`，+0x40 vtable `C0B46744`）vt+0x28 = **`FUN_c02d9d38`**（shading，`blk_c02.c:137628`）。
- `FUN_c02ab2a0(…, tag, 0, param_4, …)`（`blk_c02.c:106355`）→ AWB 物件 `0xC340B638`（vtable `C096BB68`）：param_4≠0（播放）走 vt+0x18 **`FUN_c02b0a28`**；param_4==0（從檔案顯影）走 vt+0x1C `C02B08F0` 與 vt+0x14 **`FUN_c02b0af8`**。
- **`FUN_c05bb7d8`**（Ghidra 誤名為 `Daylight`，`blk_c05.c:142052`）：畫面設定（WB、色彩模式…）。

---

## 3. 標籤 × 讀取者表

「必要」= 讀不到時該函式提早 return／放棄後續（行為後果 [I]，除非另註）。「選用」= 讀不到用預設值。

### 3.1 IFD0（ifd 0）

| tag (ifd, id) | 讀取者（函式位址） | 用途 | 證據 |
|---|---|---|---|
| (0, 0x111) StripOffsets | P2 `FUN_c05c1880`（`blk_c05.c:146606` 後，`C05C1964`）；D v32（`C03C90B8`）；C `FUN_c0386fc8`（`C0387190`） | 每幀 RAW 資料位置；播放、顯影、擷取都靠它 | [V] |
| (0, 0x117) StripByteCounts | D v32（`C03C9148`） | 顯影時 RAW 長度 | [V] |
| (0, 0x100/0x101) 寬高 | P1 `FUN_c05c1a58`；D v32；C；DEV `FUN_c02d4898`（必要）；I `FUN_c03d7d60` | 影像尺寸 | [V] |
| (0, 0x102) BitsPerSample | P1（10→3、12→0、其他→4）；D；C；DEV `FUN_c02d4898`（必要） | 位元深度 | [V] |
| (0, 0x103) Compression | D v32 | 是否壓縮 | [V] |
| (0, 0x142–0x145) Tile* | D v32 | tiled DNG（CinemaDNG 不用，讀不到走 strip）| [V] |
| (0, 0xFE) NewSubfileType | DEV `FUN_c02d4898`（必要；=0 → 主影像在 IFD0 並要求 0xC764）、`FUN_c004dd20/51510`、`FUN_c02d9d38`（必要） | 主影像在 IFD0 還是 SubIFD | [V] |
| (0, 0xC61F) DefaultCropOrigin | D；C；DEV `FUN_c02d4898`（必要） | 裁切起點 | [V] |
| (0, 0xC620) DefaultCropSize | P1（選用） | 裁切尺寸 | [V] |
| (0, 0xC764) FrameRate | P1（選用，預設 4）；DEV `FUN_c02d4898`（NewSubfileType=0 時必要）；I `FUN_c03d7d60`；轉換 2→1 讀來寫 MN 0x138（`FUN_c00c8d60`） | 播放格率／顯示 | [V] |
| (0, 0xC763) TimeCodes | P1 `FUN_c05c1bd8`、P2（每幀，選用，有預設值） | 播放時間碼顯示（`FUN_c00cfed8`，`blk_c05.c:142903`） | [V] |
| (0, 0xC62A) BaselineExposure | DEV `FUN_c02d4898`（在 `*(cfg+0x1E0)` 旗標為 0 時讀，失敗則整體回 0） | 曝光基準 | [V] |
| (0, 0xC74E) OpcodeList3 | DEV `FUN_c004dd20`/`FUN_c0051510`（必要） | 鏡頭畸變校正 | [V] |
| (0, 0xC772) | I `FUN_c03d7d60` | 資訊顯示 | [V] |
| (0, 0x112) Orientation | I `FUN_c03d5ca8`；T `FUN_c06a9400`→`FUN_c06a9738` 讀、`FUN_c06a9a78` 原地寫 | 旋轉 | [V] 呼叫；CinemaDNG 實際能否旋轉 [I] |
| (0, 0x10E/0x10F/0x110/0x13B/0x8298) | I `FUN_c03d5da0`、`FUN_c03d7948` | 資訊顯示（機型、作者、版權） | [V] |
| (0, 0x14A) + SubIFD 0x100/0x101 | I `FUN_c03d7948` | 資訊顯示（CinemaDNG 沒有，讀不到即略過） | [V] |
| 其他 IFD0（0xC612–0xC635、0xC65A/B/D、0xC6F9–0xC6FD、0xC61A、0xC61D、0xC618/9、0x828D/E、0xC68D、0xC761…） | 只有轉換器 2→1（`FUN_c00c8908` 白名單、`FUN_c00c8f00` 複製到 SubIFD）／2→3／2→0 白名單複製 | 存成 DNG／JPEG 時帶過去 | [V]（白名單從映像 `C0748D10`、`C0748DB0`、`C0748784` 讀出） |

### 3.2 Exif（ifd 2）

| tag | 讀取者 | 用途 | 證據 |
|---|---|---|---|
| (2, 0xA001) ColorSpace | DEV `FUN_c05bb7d8`；I `FUN_c03d5da0` | sRGB／AdobeRGB 設定 | [V] |
| (2, 0x9202) ApertureValue | DEV `FUN_c02d4ba8`（失敗則略過 0x200/0x82 區塊） | 顯影參數 | [V] |
| (2, 0x829A/0x829D/0x8832/0x9201/0x9204/0x9207/0x920A/0xA432/0xA433) | I `FUN_c03d5da0` | 拍攝資訊顯示 | [V] |
| (2, 其他) | 轉換器：2→1 複製整個 Exif（刪 0xA20E/F/0xA210）、2→3 白名單（`C0748DC8`）、2→0 白名單（`C07487B0`+2×0x56） | 帶到匯出的 DNG／JPEG | [V] |

### 3.3 MakerNote（ifd 5）

| tag | 讀取者（函式位址） | 用途 | 證據 |
|---|---|---|---|
| **(5, 0x200)** side info 16 KB | DEV `FUN_c02d4ba8`（`FUN_c00ba528` 取 entry，讀 blob 內 **+0xD0C**（u16×2）與 **+0xD14**（位元欄）；CinemaDNG（NewSubfileType=0）只用 +0xD0C） | 顯影參數（`+0x22C/+0x230/+0x238`）；缺 0x200 時連 MN 0x82 一起略過 | [V] 讀取；用途 [I]。實檔 A001_031 +0xD0C..+0xD17 全 0 |
| **(5, 0x117)** FLOAT×2048 shading | DEV `FUN_c02d9d38`（`C02D9F60`） | 播放第一幀／顯影／擷取時算 shading 表 | [V] |
| (5, 0x116) | `FUN_c05bb7d8`（必要，最後一項）；`FUN_c02d9d38`（0xFE≠0 分支）；I | 畫面設定、shading 插值 | [V] |
| (5, 0x137) | `FUN_c02d9d38`（0xFE≠0 分支） | shading 插值 | [V] |
| (5, 0x118) | DEV `FUN_c02d4898`（必要；實檔值 0x2B） | 決定走 0x10A 或 0x12E 分支 | [V] |
| (5, 0x10A) 位元旗標 | P1（bit6）；`FUN_c05bb7d8`；`FUN_c0045d90`（bit7 選校正版本）；`FUN_c02d4898`（0x118==0x2B 時必要）；I | 校正開關、畫面設定 | [V] |
| (5, 0x12E) | `FUN_c02d4898`（0x118≠0x2B 時必要，實檔沒有）；I | — | [V] |
| (5, 0x112) | `FUN_c02d4898`（必要，20 B）；I | 顯影參數 | [V] |
| (5, 0x108) | `FUN_c0045d90`（失敗則不設定校正） | 鏡頭 ID → 校正版本 | [V] |
| (5, 0x11A/0x11B) | `FUN_c004dd20`（0x11B→0x11A 依序，必要）、`FUN_c0051510`（0x11A） | 鏡頭校正係數 | [V] |
| (5, 0x135/0x136) | `FUN_c004dd20`（選用；實檔沒有） | 校正 | [V] |
| (5, 0x33) WB gain | **R1 `FUN_c02c79d0` 每幀從模板讀**（見 §4）；R0 `FUN_c02c6610/6870/7448` 從 builder 讀；DEV AWB `FUN_c02b0a28`（播放）；X 白名單 2→0 | 錄影：算 MN 0x34；播放：WB | [V] |
| (5, 0x11F) | R0 `FUN_c02c4a50`（builder，算色彩矩陣）；AWB `C02B08F0`（從檔顯影） | 色彩 | [V] |
| (5, 0x120) | AWB `FUN_c02b0af8`（從檔顯影，param_4==0） | AWB | [V] |
| (5, 0x07/0x74/0x75/0x3D/0x7D/0x132/0x113/0x0D/0x11/0x10/0x7E/0x82) | `FUN_c05bb7d8`（依序、多數必要：任一缺失就 return 0，後面不設）；I `FUN_c03d5da0` | 播放／顯影的 WB 名稱、色彩模式、對比等畫面設定 | [V] |
| (5, 0x82) | 另外 `FUN_c02d4ba8` | 顯影 | [V] |
| (5, 0x2F) bit0 | M `FUN_c06a9190`→`FUN_c06a98d8` 讀、`FUN_c06a9bd8` 原地寫；I `FUN_c03d5ca8`；X `FUN_c03cc420`（讀後清 bit0 再寫回轉換物件）；`FUN_c06a8fa0` | 標記狀態 | [V]；讀不到 → 標記失敗（回 0） |
| (5, 0x04/0x05/0x08/0x12/0x3E/0x66/0x10F/0x114/0x115/0x125/0x126/0x130/0x134/0x11D/0x11E/0x16/0x11C) | 只有 I：`FUN_c03d5da0`、`FUN_c03d7948`（0x11D）、`FUN_c03d7f20`（0x16、0x11C） | 資訊顯示 | [V] |
| 其他 MN | 轉換器：2→1 **複製整個 MakerNote**（只刪 0x11C，`FUN_c00c8d60`）；2→3 白名單 64 項（`C0748E24`，含 0x117）；2→0 白名單 83 項（`C0748A70`，含 0x117、0x11F、0x33、0x34） | 帶到匯出檔，不解讀 | [V] |

### 3.4 0xC634 DNGPrivateData（ifd 8）

| tag | 讀取者 | 用途 | 證據 |
|---|---|---|---|
| (8, 0x24) | `FUN_c05bb7d8`（必要，在 WB 字串／0x74／0x75 之後；缺了就不設色彩模式及之後所有項） | 畫面設定 | [V] |
| (8, 0x5A)、(8, 0x24) | `FUN_c03d55e8`（只在 DCIM 靜態 DNG 資訊路徑 `FUN_c03d5488`） | 靜態檔資訊 | [V] |
| 整個 0xC634 | 轉換 2→1 `FUN_c00c9550` 整塊複製 | 匯出 DNG | [V] |

實檔 0xC634 = 6734 B，開頭 `SIGMA_EXTH_SPPA`。

---

## 4. 錄影中會不會讀回模板（問題 2）

1. **會，而且有一個會當機的：MN 0x33。** 色彩 observer `FUN_c02b9010` 在 event mode 2／3 呼叫色彩物件 vt+0x28 `FUN_c02c79d0`（`blk_c02.c:115821`）。
   開錄（flag≠0）時它把約 20 組 cache 設成 `{-1, fmt}`（`blk_c02.c:125621-125700`）；mode 3（每幀）時
   `FUN_c05a4ca8(&DAT_c3414820, 5, 0x33, buf, 12)` **從已序列化的模板讀 MN 0x33**，
   **讀不到就 `FUN_c0011100(…, 0xF67)`**（`blk_c02.c:125798-125801`）= `FUN_c0011130` 印 "Assertion failed" 後**無窮迴圈**（`blk_c00.c:13415`）[V]。
   讀到的值餵給 `FUN_c02cbe50`，寫 **MN 0x34**（`C02CC114: FUN_c05a4bc0(…,5,0x34,DOUBLE,…)`）[V]。
   這個函式在 CinemaDNG 錄影時確實會跑：同一函式每幀寫的 0xC61A（`FUN_c02ca190`）、0xC74E（`FUN_c02ce918`）在實檔各幀間有變動（hdr_cdng §2.2）[I，強]。
   → **MN 0x33 不能從模板刪；type／count（FLOAT×3）也不能改**（查詢要求 tag/type/count 相同）。
2. 整個映像中 `FUN_c05a4ca8`（唯讀模板查詢）**只有這一個呼叫者**（`C02C8464`）[V]；fmt vt+0x3C 沒有其他直接呼叫者 [V，搜尋 `+0x14)+0x3c))`]。
   斷言只出現在這一處：檢查所有 `FUN_c05a4bc0`／`FUN_c05a4ca8`／`FUN_c03a7c70` 呼叫後 4 行內有 `FUN_c0011100` 的，只有這一個 [V]。
3. 每幀寫入（`FUN_c05a4bc0`）本身也是「先找再寫」：標籤被刪 → 找不到 → 不寫、不當機，但 cache 留在 -1，**下一幀再走一次 IFD 鏈並配 0x14 B 暫存物件**（hdr_cdng §0.3）→ 每刪一個每幀寫的標籤，每幀就多一次完整查找 [V 機制／I 成本]。
   受影響：IFD0 0x132、0xC65D、0xC763、0xC61A、0xC74E、0xC628、0xC62A、0xC761；Exif 0x9003/4、0x9010-12、0xA420、0x829A…；MN 0x05、0x06、0x19、0x3E、0x66、0x100、0x101、0x117、0x11A、0x120、0x2C-0x2E、0x34 等（完整清單見 hdr_cdng §2）。
4. 建構期讀 builder（序列化前）[V]：`FUN_c02c6610/6870/7448` 讀 MN 0x33，`FUN_c02c4a50` 讀 MN 0x11F 來算色彩標籤。只有「在 builder 裡刪」才有影響；序列化後在模板裡刪則不影響這幾個。
5. 存檔與 StripOffsets [V]：在 `C037xxxx`（`XC_StillCreateFile::v4 @C037E0F8` 一帶）與 MovRec `C038xxxx` 中，getter 的 BL 只有 `FUN_c0386fc8`（停錄後擷取靜態影像）。
   錄影中沒有任何程式讀 0x111／0x117；表頭長度來自 `req+0x14C`。韌體本身沒有 CinemaDNG 壓縮路徑（lossless 是第三方 sup，掛在 `C03A5490`）。
6. 停錄後（C）`FUN_c0386960` 會把錄影中擷取的幀檔從卡整檔讀回（`FUN_c0386eb0`），type 2 解析並跑完整 DEV。

---

## 5. 刪除影響摘要

- **錄影本身**：只有 **MN 0x33** 是硬性要求（缺了就斷言當機）。其他標籤刪掉只會讓對應的每幀寫入靜默失敗，並多出每幀查找成本。
- **機內播放／顯影／擷取**（DEV + P1/P2）需要：IFD0 0xFE、0x100、0x101、0x102、0x103、0x111、0x117、0xC61F、0xC764、0xC62A、0xC74E；
  MN 0x07、0x0D、0x10、0x11、0x33、0x3D、0x74、0x75、0x7D、0x7E、0x82、0x108、0x10A、0x112、0x113、0x116、0x117、0x118、0x11A、0x11B、0x137、0x132、0x200（+0xD0C）；
  Exif 0xA001、0x9202；0xC634 子項 0x24。
  選用：0xC620、0xC763、0x135、0x136、0x11F、0x120、0x12E（0x118≠0x2B 時才必要）。
  缺了的後果是該函式提早 return、參數沒設好（畫面顏色／校正錯誤或播放失敗）[I：沒有上機驗證]。
- **標記**：MN 0x2F（LONG×1）。**資訊顯示**：§3 標 I 的項目，缺了只是不顯示 [I]。
- **匯出 DNG（2→1）**：Exif、MakerNote、0xC634 整塊照搬；刪掉就是匯出檔也沒有，之後機內再顯影那個靜態 DNG 時，同樣受上面 DEV 需求影響 [I]。

---

## 6. 相機自己從不讀回的 MakerNote／私有資料

範圍：實檔 A001_031 的 MakerNote 共 97 個標籤；對照 §0 的全映像 BL 掃描（190 + 111 個呼叫點，涵蓋所有 MetaData getter 與包裝函式），以及 Ghidra 中所有 `FUN_c00b9f58` 外部呼叫者
（`FUN_c0217340`、`FUN_c02192f8` 是 AE 的寫入者，用 `FUN_c00bfc38` 加項目）。
「從不讀」指沒有任何程式**解讀**它的值；轉換器整 IFD／白名單**複製**不算（見 §3.3）。

**任何路徑都不解讀（CinemaDNG 檔中存在）**[V，以上述掃描為準]：
MN 0x02、0x06、0x09、0x0A、0x0B、0x0E、0x0F、0x17、0x19、0x27、0x28、0x29、0x2A、0x2B、0x2C、0x2D、0x2E、0x34、0x43、0x45、0x47、0x48、0x63、0x72、0x7C、0x84、0x85、0x8F、
0x100、0x101、0x102、0x104、0x105、0x106、0x107、0x10E、0x110、0x111、0x119、0x121、**0x124**、0x127、0x128、0x129、0x12A、**0x12B**、**0x12D**、0x131。

**只在靜態檔（DCIM）資訊路徑讀，CinemaDNG 不會走到**（`FUN_c03d8028`、`FUN_c03d8290` 只由 `FUN_c03d54f0/5530/5978/59a0/5c28/5c68` 呼叫，它們只用於 type 1/2/4，`blk_c03.c:135593-135604, 135935`）[V]：
MN 0x03、0x20、0x56、0x6F、0x8E、0x10C、0x10D（以及 0x1C-0x1E，實檔沒有）。

**0xC634**：除了子項 **0x24**（`FUN_c05bb7d8`）與 0x5A（只在靜態路徑），其餘子項沒有讀取者 [V]。

注意：
- 上面這些雖然「不讀」，但其中有每幀寫入者（例如 MN 0x2C-0x2E、0x34、0x100、0x101、0x10C-0x10E、0x05/0x06/0x19/0x3E/0x66、0x11A、0x120、0x117）。
  它們被刪時寫入會失敗，並造成 §4.3 的每幀重複查找。要刪就一併停掉寫入者（或接受成本）。
- MN **0x34** 由 MN 0x33 算出、每幀寫入，本身沒人讀；但 **0x33 不能刪**（§4.1）。
- MN **0x200**：在播放／顯影時只讀 +0xD0C（CinemaDNG）。0x200 整塊刪掉 → `FUN_c02d4ba8` 略過 0x200 與 0x82 的設定（不會當機）[V 程式結構／I 畫面後果]。
- MN **0x117**：錄影中沒人讀，但播放第一幀、顯影、擷取的 shading 都要用它（`FUN_c02d9d38`）。刪了這些功能就沒有 shading 校正 [I]。
- MakerNote 檔頭（`SIGMA\0\0\0\x01\x04a\0`，IFD 在 +10）與 0x927C 容器必須保留，解析才能找到上面的必要項。`FUN_c03d7948` 也透過 `FUN_c00ba5a8` 讀 MakerNote 容器 +0x28 [V]。

---

## 7. 主要引用

- getter：`blk_c00.c:144099`（`FUN_c00b9f58`）、`144207-144420`
- P1/P2：`blk_c05.c:143757-143840`、`146583-146730`；P3：`blk_c05.c:141963-142050`、`142846-142910`
- `FUN_c05bb7d8`：`blk_c05.c:142052-142470`（反組譯 `C05BB810..C05BC278`）
- DEV：`blk_c02.c:125975`（`FUN_c02c89b8`）、`134783-134935`（`FUN_c02d4898`）、`134940-135000`（`FUN_c02d4ba8`）、`137628-137750`（`FUN_c02d9d38`）、`106355-106450`（`FUN_c02ab2a0`）、`109680-109770`；`blk_c00.c:53647, 54366, 58390-58480, 60280-60310`
- D：`blk_c03.c:140864-141302`、`141649-141700`；C：`blk_c03.c:90774-90860`、`91074-91140`
- I：`blk_c03.c:135847-136035`、`130475-130600`、`130710-130745`、`150461-151880`
- M／T：`blk_c06.c:136847-136945`、`136948-137030`、`138749`、`139991`
- 轉換器：`blk_c00.c:148488`（`FUN_c00c16c8`）、`149057-149160`、`150362-151500`
- 模板讀回＋斷言：`blk_c02.c:115746-115830`、`125361-125801`；`blk_c00.c:13415`；`blk_c05.c:126766-126790`（`FUN_c05a4ca8`）
