# SIGMA fp 5.02 — CinemaDNG 幀表頭：每個標籤的「產生者」清單

2026-10-14，純離線（反編譯 `out/decomp/full/blk_c0*.c`、映像 `out/MAIN_c0000000.bin`）。只寫**產生者**，不涵蓋讀者。
**[V]** = 反編譯或反組譯看過（含映像中的常數表／vtable）；**[I]** = 推論。
count／大小以程式中的 `FUN_c00ba378` 參數為準。可變長度的項目（使用者字串、OpcodeList3）另外拿一個 stock 12-bit 幀
`projects/open-gate/captures/imx410-reverse-A001_150/A001_150_20260928_000001.DNG` 對過，表內數字取自這一幀（202 個標籤，都對得到產生者）。
這一幀只用來核對，結論都來自程式碼。

---

## 0. 結論

1. **表頭共 0x13400 = 78,848 B**：TIFF 頭 8 B，IFD0 16,664 B，0xC634 6,734 B，Exif 1,004 B，**MakerNote 54,338 B（69%）**，對齊補白 100 B。
2. **≥256 B 的 12 項（不算兩個容器）加起來 67,156 B（佔表頭 85%）**。其中 **DNG 解碼需要的只有 OpcodeList3（12,564 B）**，算上 Profile 渲染表（C6FA/FB/FC，2,752 B）也只有 15,316 B。
   其餘 51,840 B 都是 SIGMA 私有：
   - MN 0x12D 16 KB、0x12B 9 KB、0x124/0x129 各 576 B、0x12A 192 B：**相機內 16 種「色彩模式」的整組色彩表一次全部寫進去**（每支片相同，跟目前選哪個模式無關）。
   - MN 0x200 16 KB：**ISP／AE／AF／WB 內部狀態快照**（DataPool side info），尾段常常是零。
   - MN 0x117 8 KB：2×32×32 的色彩 shading 增益（OpcodeList3 GainMap 用的也是同一張來源表），**每幀重寫**。
   - MN 0x43／0x45 各 256 B：AE 分區表；0x45 沒開閃燈時全零。
3. **每幀真的會重寫的大項目只有三個**：MN 0x117（8 KB）、IFD0 0xC74E（12.5 KB，只在 `local_34[0xcc]` 成立時）、MN 0x11A（200 B）。其他都是幾個 byte 的值。
4. 寫入規則：`FUN_c00ba378` → IFD vt+0x1C = `TiffIfd::v5 @C00BEC58`。**同一個 tag 再加一次會覆蓋前一次的 type/count/值**（blk_c00.c，v5 的 `iVar3 != 0` 分支）[V]。
   所以「最後加的人」決定內容。順序是：builder 預設值 → mode-0 observer（lens、AE＋strobe、AF）→ AWB 錄影資訊 → 色彩 `FUN_c02c7448` → tagMgr flag 4 → v9 序列化。
5. 寫入的不只 `FUN_c00ba378`，還有兩條路：
   - `FUN_c00ba208(b,ifd,tag,type,count)`：**零填的 placeholder**，上限 0x100 B（blk_c00.c:144195）；
   - AE 子系統用自己的表格（每筆 16 B：`{u16 tag, u16 type, u32 count, fn, flag}`），每筆經 `FUN_c00bfc38` 直接加到 IFD 物件（`FUN_c0217340`，blk_c02.c:18399）[V]。

---

## 1. 產生路徑（開錄一次）與每幀更新者

| 階段 | 函式 | 加入的標籤 | 證據 |
|---|---|---|---|
| a. builder type 2 | `FUN_c00c1ca0` blk_c00.c:148699 | TIFF 'II'、0x8769、0x8825（只在 `FUN_c00d2830()` 時）、0xC634 容器、0x927C 容器 | [V] |
| | `FUN_c00c2b20(b,2)` blk_c00.c:149356-149431 | IFD0 預設：0xFE、0x106、0x115、0x11C×2、0x828D/E、0xC617、0xC619、0xC612/3、0xC614、0xC62A、0xC62B、0xC62C、0xC62F、0xC635、0xC6FD、**0xC764**，以及共用的 0x10E、0x10F、0x110、0x112、0x11A/B、0x128、0x131、0x13B、0x8298 | [V] |
| | `FUN_c00c33f8(b,2)` blk_c00.c:149434 | Exif：0x9286、0x8830、0x9000、0xA000、0xA001、0xA217、0xA300/1、0xA401/4/6、0xA210、0xA431、0xA500（mode 2 不加 0x9101/0x9102/0xA002/0xA003） | [V] |
| | `MULTI(b,2)` blk_c00.c:149535 | MN 0x02、0x03、0x04、0x0B、0x0E/0x0F（零填）、0x16、0x17、0x6F、0x72、0x84、0x85、0x8E、0x8F、0x102、0x10C、0x118、0x119、0x11D、0x11E、0x125、0x134 | [V] |
| | `FUN_c00c4f90(b,2)` blk_c00.c:150086 | 0xC634 內 215 筆（常數 SRATIONAL／BYTE 等，見 §4） | [V] |
| b. mode-0 通知 `FUN_c00559f0(S,0,3,dp)` | lens `FUN_c0364020`（vt C0B96650+0x10）blk_c03.c:67707 | Exif 0x9206、0x920A、0xA405、0xA432-4；MN 0x0A、0x27-0x2E、0x48、0x104-0x108、0x128；IFD0 0xC630 | [V] |
| | AE observer `@C0228A48`（反組譯）→ AE tag 管理器 vt+0xC(ifd,dp,flagOnly=0) | IFD0 表 C091319C：0xC772；Exif 表 C09131BC：0x829A、0x829D、0x8822、0x8827、0x8832、0x9201-0x9205、0x9207、0x9209、0xA402；MN 表 C09134AC：0x08、0x09、0x43、0x47、0x56、0x63、0x110、0x111、0x112、0x114、0x11C、0x127（movie 用 `FUN_c02173e8` 的 0xC3202870 這一組） | [V] 表格，[I] 選哪一組（只有這組同時含 Exif 0x9209 與 MN 0x11C，跟實檔吻合） |
| | 同一 handler `C0228BF4: bl FUN_c02b4b18` → strobe `FUN_c02b8638` blk_c02.c:115224 | MN 0x20、0x45、0x110、0x111（覆蓋 AE 的），閃燈時再加 0x43 | [V] |
| | AF `PictagAfObserverForAfterExpos::v1 @C022BE20` → `FUN_c0291910` blk_c02.c:89134 | 不加標籤；寫 side info，並以 DataPool vt+0x10（v2）把 **0x2140 B AF 資料（0xC33D5214）**複製到 dp+0x14C0（= MN 0x200 的尾段）；再呼叫 AfMgrTagsModel vt+0x10 = `FUN_c02a8e20` → MN 0x10F | [V] |
| | AWB `AwbCameraTagObserver::v1 @C02B1D10` blk_c02.c:110392 | mode 0 不加（只處理 mode 5 與 mode 3） | [V] |
| | 色彩 observer `FUN_c02b9010` | mode 0 不加（只處理 mode 2/3/5） | [V] |
| | GPS `FUN_c05cc870` blk_c05.c:155793 | GPS IFD 0x00-0x1F，**只在有 GPS 裝置時**（實檔沒有 0x8825） | [V] 呼叫，[I] 條件 |
| c. AWB 錄影資訊 | `FUN_c02b18d0` blk_c02.c:110283（經 vtable C096BB74 呼叫） | MN 0x07、0x11F、0x33、0x131、0x74、0x75、0x120/0x121、0xC634 子項（`FUN_c02b1790`、`FUN_c02b0890`→`FUN_c02b0510`）；IFD0 0xC628；Exif 0x9208、0xA403 | [V] 內容，[I] 呼叫者是 `FUN_c02aaea0` 那條路 |
| d. 色彩 `FUN_c02b8e38(6,4,dp,set)` → `FUN_c02b97a8` case 6 → 色彩 tag 管理器 0xC3414C98（vt C096FBE8）vt+0x24 = **`FUN_c02c7448`** blk_c02.c:125217（event mode==0 才進來；builder 用 DataPool vt+0x2C） | 見下一列 | | [V] |
| | `FUN_c02c7448` 依序呼叫 | Exif 0xA408/9/A、0xA20E/F；IFD0 **0xC618**（條件）、0xC621/2、0xC62A、0xC6F9-0xC6FC、0xC61A、0xC620、0xC68D、0xC761、**0xC74E**；MN 0x0D、0x10-0x12、0x2F、0x34、0x3D、0x7C-0x7E、0x82、0x10A、0x113、0x115/6、**0x117**、**0x11A**、0x11B、**0x124、0x129、0x12A、0x12B、0x12D**、0x126、0x132、0x137；0xC634 子項（`FUN_c02ca050/c02ca560/c02cad28/c02cb0c0/c02c4678/c02c4708/c02c47f8` 等） | [V] |
| | vt+0x14 `FUN_c02c6870`、vt+0x1C `FUN_c02c7110` | 改用 DataPool vt+0x24/+0x30 的 builder（拍照用）；movie DataPool 這兩個回 0 → 不加 | [V] 程式，[I] 回 0 |
| e. tagMgr `XC_RecMgrTagCinema::v2 @C03A85F8` blk_c03.c | `FUN_c03a7c28` blk_c03.c:115488 | 表 C0B9ED9C 中 flag&4 的 19 筆（#19 IFD1 0x132 不加）：0x132、0xC65D、0xC763、0x9003/4、0x9010-2、0xA420、MN 0x05、0x06、0x19、0x3E、0x66、0x100、0x101、0x10C、0x10D、0x10E | [V] |
| f. v9 `@C06A4C48` → `FUN_c06a4bd0` blk_c06.c:133721 | `FUN_c06a5290` | 0x100、0x101、0x102、0x103、0x111、0x116、0x117、0xC61D、0xC61F、0xC65A、0xC65B（壓縮路徑改加 0x142-0x145） | [V] |
| | `FUN_c06a5ac8` blk_c06.c:134118 | 0xC634 的 0x101F/0x201F/0x301F（只在 `[0xC3074910]==1` 時） | [V] |
| | `FUN_c06a5630` blk_c06.c:134022 | **MN 0x200 UNDEFINED×0x4000** | [V] |
| | v9 本體 blk_c06.c:133811 | 0x111 重加一次（值 = 對齊後表頭長） | [V] |

**每幀**（`C038C700` 的 observer 通知 mode 3，加上 tagMgr v1）：全部經 `FUN_c05a4bc0` 原地覆寫，type 與 count 都不能變。

| 寫入者 | 標籤 |
|---|---|
| tagMgr v1 | 0x132、0xC65D、0xC763、0x9003/4、0x9010-2、0xA420、MN 0x19 每幀；MN 0x05、0x06、0x3E、0x66、0x100、0x101 每 10 幀 |
| lens `FUN_c03644a8` | 0x9206、0x920A、0xA405、MN 0x2C-0x2E |
| AE `FUN_c0218c38` blk_c02.c:19080 | 0x829A、0x829D、0x8827、0x8832、0x9201-0x9205、MN 0x112、0x11C、0x127、IFD0 0xC772 |
| AF `FUN_c02aa5d0` | MN 0x10F |
| AWB mode 3（blk_c02.c:110560 起） | MN 0x07、0x33、0x131、0x74、0x75、0x120；Exif 0x9208、0xA403；IFD0 0xC628；0xC634 子項 |
| 色彩 vt+0x28 `FUN_c02c79d0` blk_c02.c:125361 | 一定寫：0xC61A、0xC761、0xC62A、**MN 0x117（8 KB）**、**MN 0x11A**、MN 0x113、0x137、0x126、0x132；條件式：**0xC74E（`local_34[0xcc]`）**；「與上次不同才寫」：0xA408-A、MN 0x0D、0x10、0x11、0x2F、0x34、0x3D、0x7C-0x7E、0x82、0xC634 子項 |

---

## 2. 大項目（≥256 B）逐一追到來源

### 2.1 MN 0x12D FLOAT×0x1000 = 16,384 B（SIGMA 私有，色彩表，常數）[V]
`FUN_c02c5ed0` blk_c02.c:124521：16 次 `FUN_c02c5df0(mgr, buf+0x400*i, b, mode_id, buf+0x4000)`，mode_id 依序是
0x23,1,0,3,5,6,7,0xE,0xB,0xC,0xF,8,10,0x24,0xD,0x24（0x24 出現兩次）。`FUN_c02c5df0` blk_c02.c:124472：
`FUN_c02d2f40(mode_id)` 在曲線表 `FUN_c02cf300()` 找到該模式，複製 0x1000 B（1024 個 u32，每個 = 兩個 16-bit 值）到暫存，
取其中 127 點，x = i·16·(1/2048)，y = 曲線值×(1/2048) 經 `FUN_c02c4e38`，最後一點固定 (1.0, 1.0) → 每模式 128 個 (x,y) = 256 floats。
**內容是韌體內建、與拍攝無關的色調曲線；同一張錄影、甚至不同錄影都相同** [I：同韌體同色彩表]。開錄時算一次，每幀不寫。
暫存區 `mgr+0x24` 是色彩 tag 管理器共用的 scratch 緩衝；builder 加入時會把資料複製一份（`TiffIfd::v5` 的 `FUN_c00bd460`）[V]。

### 2.2 MN 0x200 UNDEFINED×0x4000 = 16,384 B（SIGMA 私有，內部狀態快照）[V／I]
`FUN_c06a5630` blk_c06.c:134022：配 16 KB → `DataPool::v1 @C00565F8`（DataPool vt+0xC）`memcpy(dst, dp+4, min(n,0x4000))` → add。
來源是 `DataPoolOfCameraTagConcrete<2770,XC_CameraTagsSideInfoOem>` 的 side info：
- DataPool 建立時從全域原型 `0xC308BA8C`（`FUN_c0055ab8`）複製。原型有約 90 處經 `FUN_c0055ab8()` 取用並寫入，
  例如 ISP 控制器 `FUN_c0043e08`（`FUN_c0044c18()->vt+0x34`）、AE `FUN_c0227ce0`、AF `afmgrif`、色彩 `FUN_c02ba640`／`FUN_c02bb928` [V 呼叫點；I 各自寫哪段]。
- 尾段：AF observer `FUN_c0291910` blk_c02.c:89155 用 DataPool vt+0x10（`v2 @C0056B50`，上限 0x2B44）把
  **0xC33D5214 起 0x2140 B 的 AF 資料**複製到 dp+0x14C0，也就是 0x200 blob 的 offset 0x14BC [V]。
  這段緩衝在 `FUN_c02913f8`（blk_c02.c:89016）會被 memset 0。AF 不寫時大部分是零 → 實檔的「零尾」[I]。
- 開錄時複製一次，每幀不寫 [V]。**內容是 ISP／AE／AF／WB 的內部狀態與 AF 記錄，等同除錯／診斷資料**，DNG 解碼用不到 [I]。

### 2.3 IFD0 0xC74E OpcodeList3 UNDEFINED×0x3114 = 12,564 B（DNG 校正）[V]
`FUN_c02cdf30(mgr,b,ifd=0,isp,ctx,0)` blk_c02.c:129784：
- 大小只有兩種：`ifd==0` 且 event mode 為 0 或 3 時 **0x3114**（2 個 opcode），否則 **0xB8**（只有第 1 個）。超出時 assert（blk_c02.c:130270）。
- opcode 1：**WarpRectilinear**，3 planes × 6 DOUBLE＋中心點。係數取自鏡頭資料 `ctx+0x34..0x8C`（`ctx+0x180` 有鏡頭校正資料時），否則用常數模板 DAT_C0970DAC（恆等）。
- opcode 2：**GainMap**（模板 DAT_C0970C2C）。Top=5、Left=8、Bottom=`ctx->f0[1]+5`、Right=`ctx->f0[0]+8`，
  網格 32×32×3 planes = 0xC00 floats = 12,288 B。值來自 **ctx+0x190 的色彩 shading u16 表**（兩個 plane，與 MN 0x117 同源）×鏡頭週邊光量曲線
  （`FUN_c02d3a90(ctx+0xF8)`，以 9 點二次內插成 1024 點；沒有鏡頭資料時全 1.0）。
- 每幀由 `FUN_c02ce918`（blk_c02.c:130757）在 `local_34[0xcc]` 成立時重寫。

### 2.4 MN 0x12B FLOAT×0x900 = 9,216 B（SIGMA 私有，色彩表，常數）[V]
`FUN_c02c5b38` blk_c02.c:124399：對同樣 16 個 mode_id 呼叫 `FUN_c02c5ad8`：`FUN_c02c6540(mode)` 找索引，
從色彩模式表 `**(mgr+8) + idx*0x244 + 4` 複製 0x240 B（找不到就用第 0 筆）。
每模式 144 floats = HueSatMap 24 hue × 2 sat × 1 val × 3（維度由 MN 0x12A 宣告）。韌體常數，開錄一次。

### 2.5 MN 0x117 FLOAT×0x800 = 8,192 B（SIGMA 私有，ISP 校正，每幀）[V]
`FUN_c02cce38` blk_c02.c:128999（add）、`FUN_c02ccf48` blk_c02.c:129044（每幀，`FUN_c05a4bc0`）：
讀 `*(ctx+0x190)`：兩個 plane，各 32×32 個 u16（plane 2 在 +0x800），×`DAT_c02ccf40` = 1/512 → float（512 = 1.0）。
若全部都在 |g−1| ≤ 1.19e-7 之內，`mgr+6=0`（代表沒有校正）[V]。內容是 **ISP 目前使用的色彩 shading／週邊光量增益網格**。

### 2.6 IFD0 0xC634 DNGPrivateData（6,734 B 容器）— 見 §4

### 2.7 IFD0 0xC6FC ProfileToneCurve FLOAT×256 = 1,024 B（DNG 選用，渲染）[V]
`FUN_c02c4e80` blk_c02.c:123884：從色彩表 `*(*(mgr+8)+0x20)+4` 複製 0x400 B；目前色彩模式是 0x24 時改用 +0x404 那組。
128 個 (x,y)。開錄一次，每幀不寫。

### 2.8 IFD0 0xC6FA／0xC6FB ProfileHueSatMapData1/2 FLOAT×216 = 864 B ×2（DNG 選用，渲染）[V]
`FUN_c02c4d40` blk_c02.c:123833：Dims 0xC6F9 = 常數 DAT_c096fdf0 {36,2,1}；Data1 = `*(*(mgr+8)+0x18)+4`，Data2 = +0x364，各 0x360 B；
色彩模式 0x24 時整組改用 +0x6C4。開錄一次。

### 2.9 MN 0x124／0x129 FLOAT×144 = 576 B ×2（SIGMA 私有，16 色彩模式矩陣）[V]
- 0x124 `FUN_c02c57c0` blk_c02.c:124312：對 16 個 mode_id 呼叫 `FUN_c02c5440`，從 `FUN_c02d5df0()+8` 的表（每筆 0x18 B，9 個 s16）
  取 3×3，每個元素除以第一列的和，存成 float。
- 0x129 `FUN_c02c5948` blk_c02.c:124341：用 `FUN_c02c55a0`，從色相／飽和參數（`piVar2[10]` 表每筆 0x14 B ＋ 偏移表）經 `FUN_c02c9860` 乘矩陣，得 3×3。
- 兩者都是韌體常數，開錄一次。

### 2.10 MN 0x43／0x45 BYTE×256 ×2（SIGMA 私有）[V]
- 0x43：AE 表的 handler `FUN_c0218528` → `FUN_c0218438` 計算 `clip(offset + FUN_c02195f0(zone_i), ≤255)`，存到 0xC32028D0，
  共 W×H 區（`*(ae+0x808)`×`*(ae+0x809)`，≤256）。`DAT_c3202c39 != 0` 時跳過（AE 回呼會清掉它，blk_c02.c:30207）。
  閃燈拍攝時 strobe 改加 0xC3413890 的版本。開錄一次，每幀不寫 → **整支片固定是開錄當下的 AE 分區值** [V]。
- 0x45：`FUN_c02b8638`，閃燈參數為 0（錄影）時先 `memset(0xC3413790,0,0x100)` 再加入 → **固定 256 B 全零** [V]。

### 2.11 IFD0 0xC618 LinearizationTable SHORT×256 = 512 B（DNG 必要，條件式）[V]
`FUN_c02c4908` blk_c02.c:123642：只在 `*(*(ctx+0xF0)+8)==4` 時加。值是程式算出的 6 段分段線性表（0..0xC 步 16，之後斜率 4、8、16、32、0x49）。
大部分 stock 幀沒有這個標籤；有的時候表頭跨到 0x13800。

---

## 3. 全部標籤（stock 12-bit 幀，依大小排序）

「bytes」= type 大小 × count。兩個容器（0x927C、0xC634）的大小已經把裡面的子標籤算進去，**不要和子標籤重複加總**。
| # | IFD | tag | type | count | bytes | 產生者 (file:line) | 內容 | 每幀更新 | 分類 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | EXIF | 0x927C | UNDEFINED | 54338 | 54338 (容器) | `FUN_c00c1ca0` blk_c00.c:148839 | MakerNote 容器（"SIGMA\0\0\0"+IFD），大小 = MN 全部 | 部分 | SIGMA 私有 |
| 2 | MN | 0x012D | FLOAT | 4096 | 16384 | 色彩 `FUN_c02c7448` → `FUN_c02c5ed0` blk_c02.c:124547 | 16 色彩模式 × 色調曲線 128 點 (x,y) FLOAT（`FUN_c02c5df0`，曲線表 `FUN_c02cf300`） | 否 | SIGMA 私有 |
| 3 | MN | 0x0200 | UNDEFINED | 16384 | 16384 | v9 `FUN_c06a5630` blk_c06.c:134037 | 16 KB side info（DataPool+4..+0x4004） | 否 | SIGMA 私有 |
| 4 | IFD0 | 0xC74E | UNDEFINED | 12564 | 12564 | `FUN_c02cdf30` blk_c02.c:130262 | OpcodeList3：WarpRectilinear＋GainMap 32×32×3 | 是：`FUN_c02ce918` blk_c02.c:130757 | DNG 必要（校正） |
| 5 | MN | 0x012B | FLOAT | 2304 | 9216 | 色彩 `FUN_c02c7448` → `FUN_c02c5b38` blk_c02.c:124467 | 16 色彩模式 × HueSatMap 24×2×1×3 FLOAT（`FUN_c02c5ad8` 從色彩模式表 **(mgr+8) 每筆 0x244 B 複製 0x240） | 否 | SIGMA 私有 |
| 6 | MN | 0x0117 | FLOAT | 2048 | 8192 | 色彩 `FUN_c02c7448` → `FUN_c02cce38` blk_c02.c:129033 | 色彩 shading 增益表 2×32×32 FLOAT（ctx+0x190 的 u16 ×1/512） | 是：`FUN_c02ccf48` blk_c02.c:129078 | SIGMA 私有 |
| 7 | IFD0 | 0xC634 | BYTE | 6734 | 6734 (容器) | `FUN_c00c1ca0` blk_c00.c:148820 | DNGPrivateData 容器 "SIGMA_EXTH_SPPA"（內容見 §C634） | 部分 | SIGMA 私有 |
| 8 | IFD0 | 0xC6FC | FLOAT | 256 | 1024 | `FUN_c02c4e80` blk_c02.c:123898 | ProfileToneCurve 128 點 (x,y)，色彩表 *(mgr+8)+0x20 | 否 | DNG 選用(渲染) |
| 9 | IFD0 | 0xC6FA | FLOAT | 216 | 864 | `FUN_c02c4d40` blk_c02.c:123859 | ProfileHueSatMapData1 216 FLOAT，色彩表 *(mgr+8)+0x18（+4） | 否 | DNG 選用(渲染) |
| 10 | IFD0 | 0xC6FB | FLOAT | 216 | 864 | `FUN_c02c4d40` blk_c02.c:123860 | ProfileHueSatMapData2 216 FLOAT（同表 +0x364） | 否 | DNG 選用(渲染) |
| 11 | MN | 0x0124 | FLOAT | 144 | 576 | 色彩 `FUN_c02c7448` → `FUN_c02c57c0` blk_c02.c:124336 | 16 色彩模式 × 3×3 矩陣（`FUN_c02c5440`，列和正規化） | 否 | SIGMA 私有 |
| 12 | MN | 0x0129 | FLOAT | 144 | 576 | 色彩 `FUN_c02c7448` → `FUN_c02c5948` blk_c02.c:124365 | 16 色彩模式 × 3×3 矩陣（`FUN_c02c55a0` 由色相/飽和參數合成） | 否 | SIGMA 私有 |
| 13 | MN | 0x0043 | BYTE | 256 | 256 | AE 表 C09134AC（mode 0） handler `FUN_c0218528` blk_c02.c:18891（`FUN_c0218438`） | AE 分區亮度表，src 0xC32028D0，W×H≤256 區塊；閃燈時改由 `FUN_c02b8638` 0xC3413890 | 否 | SIGMA 私有 |
| 14 | MN | 0x0045 | BYTE | 256 | 256 | strobe `FUN_c02b8638` blk_c02.c:115242 | 閃燈分區表 src 0xC3413790；無閃燈時先 memset 0（blk_c02.c:115237）→ 256 B 全零 | 否 | SIGMA 私有 |
| 15 | MN | 0x011A | DOUBLE | 25 | 200 | 色彩 `FUN_c02c7448` → `FUN_c02cd218` blk_c02.c:129201 | 25×DOUBLE ISP 係數（u16/10000；無鏡頭資料時全 1.0） | 是：`FUN_c02cd058` blk_c02.c:129138 | SIGMA 私有 |
| 16 | MN | 0x012A | LONG | 48 | 192 | 色彩 `FUN_c02c7448` → `FUN_c02c5b38` blk_c02.c:124449 | 16 × {24,2,1} 常數（`FUN_c02c5ac0`）= 0x12B 的維度 | 否 | SIGMA 私有 |
| 17 | MN | 0x0120 | FLOAT | 30 | 120 | AWB `FUN_c02b10a8` blk_c02.c:109906 | 30 FLOAT AWB 狀態 | 是：`FUN_c02b1ca0` blk_c02.c:110381 | SIGMA 私有 |
| 18 | MN | 0x0121 | FLOAT | 30 | 120 | AWB `FUN_c02b10a8` blk_c02.c:109907 | 30 FLOAT AWB 狀態（param_3+0x78） | 否 | SIGMA 私有 |
| 19 | EXIF | 0xA434 | ASCII | 96 | 96 | lens `FUN_c03631e0` blk_c03.c:67186 | LensModel | 否 | 標準中繼資料 |
| 20 | IFD0 | 0xC621 | SRATIONAL | 9 | 72 | `FUN_c02c4a50` blk_c02.c:123805 | ColorMatrix1 = inv(MN 0x11F)×常數表 C096FD2C/FD74 | 否 | DNG 必要 |
| 21 | IFD0 | 0xC622 | SRATIONAL | 9 | 72 | `FUN_c02c4a50` blk_c02.c:123827 | ColorMatrix2 = inv(MN 0x11F)×常數表 C096FC9C/FCE4 | 否 | DNG 必要 |
| 22 | EXIF | 0x9286 | UNDEFINED | 72 | 72 | `FUN_c00c33f8` mode2 blk_c00.c:149472 | UserComment "ASCII\0\0\0"+64 B 使用者字串（表 0xC31CC054） | 否 | 標準中繼資料 |
| 23 | MN | 0x010F | SHORT | 36 | 72 | AF `FUN_c02aa6c8` blk_c02.c:105792（AfMgrTagsModel vt C096B3D0 → `FUN_c02a8e20`） | AF 點資訊 36×SHORT | 是：`FUN_c02aa5d0` blk_c02.c:105744 | SIGMA 私有 |
| 24 | IFD0 | 0x010E | ASCII | 64 | 64 | `FUN_c00c2b20` mode2 blk_c00.c:149408 | ImageDescription，使用者字串表 0xC31CC054（`FUN_c00bd1c0`），count = 表內長度 | 否 | 標準中繼資料 |
| 25 | IFD0 | 0x013B | ASCII | 64 | 64 | `FUN_c00c2b20` mode2 blk_c00.c:149426 | Artist，使用者字串（count 由設定長度決定） | 否 | 標準中繼資料 |
| 26 | IFD0 | 0x8298 | ASCII | 64 | 64 | `FUN_c00c2b20` mode2 blk_c00.c:149429 | Copyright，使用者字串 | 否 | 標準中繼資料 |
| 27 | MN | 0x0082 | SRATIONAL | 6 | 48 | 色彩 `FUN_c02c7448` → `FUN_c02cccd0` :128958 | 6×SRATIONAL | 變更時：`FUN_c02ccbf8` | SIGMA 私有 |
| 28 | MN | 0x0034 | FLOAT | 9 | 36 | 色彩 `FUN_c02c7448` → `FUN_c02cc130` :128624 | 3×3 FLOAT 色彩矩陣 | 色彩模式變更時：`FUN_c02cbe50` | SIGMA 私有 |
| 29 | MN | 0x011F | FLOAT | 9 | 36 | AWB `FUN_c02b0118` blk_c02.c:109353 | 3×3 FLOAT WB/色彩矩陣（ColorMatrix 的來源） | 否 | SIGMA 私有 |
| 30 | EXIF | 0xA420 | ASCII | 33 | 33 | tagMgr #8 | ImageUniqueID（64-bit 幀計數器） | 是：tagMgr | 標準中繼資料 |
| 31 | IFD0 | 0xC61A | RATIONAL | 4 | 32 | `FUN_c02ca2b0` blk_c02.c:127212 | BlackLevel 4×RATIONAL（感測器 OB） | 是：`FUN_c02ca190` blk_c02.c:127150 | DNG 必要 |
| 32 | IFD0 | 0xC630 | RATIONAL | 4 | 32 | lens `FUN_c0363a30` blk_c03.c:67603 | LensInfo | 否 | 標準中繼資料 |
| 33 | EXIF | 0xA432 | RATIONAL | 4 | 32 | lens `FUN_c0363020` blk_c03.c:67150 | LensSpecification | 否 | 標準中繼資料 |
| 34 | MN | 0x0084 | ASCII | 32 | 32 | `FUN_c00ca2c8` blk_c00.c:151776 | "SIGMA fp"（32 B 固定，尾零） | 否 | SIGMA 私有 |
| 35 | IFD0 | 0x0131 | ASCII | 25 | 25 | `FUN_c00ca260` blk_c00.c:151766 | "SIGMA fp Ver.%s"（25 B 固定） | 否 | 標準中繼資料 |
| 36 | MN | 0x0017 | ASCII | 25 | 25 | `FUN_c00ca348` blk_c00.c:151802 | 韌體版本字串 | 否 | SIGMA 私有 |
| 37 | IFD0 | 0xC628 | RATIONAL | 3 | 24 | AWB `FUN_c02b1330` blk_c02.c:110020 | AsShotNeutral | 是：`FUN_c02b1398` blk_c02.c:110043 | DNG 必要 |
| 38 | EXIF | 0xA433 | ASCII | 24 | 24 | lens `FUN_c0363178` blk_c03.c:67168 | LensMake | 否 | 標準中繼資料 |
| 39 | MN | 0x011D | RATIONAL | 3 | 24 | MULTI mode2 blk_c00.c:149923 | 3×RATIONAL（設定 +0x3B0 物件） | 否 | SIGMA 私有 |
| 40 | IFD0 | 0x0132 | ASCII | 20 | 20 | tagMgr #0 `FUN_c03a7c28` blk_c03.c:115488 | DateTime（時鐘） | 是：tagMgr v1 | 標準中繼資料 |
| 41 | EXIF | 0x9003 | ASCII | 20 | 20 | tagMgr #3 | DateTimeOriginal | 是：tagMgr | 標準中繼資料 |
| 42 | EXIF | 0x9004 | ASCII | 20 | 20 | tagMgr #4 | DateTimeDigitized | 是：tagMgr | 標準中繼資料 |
| 43 | MN | 0x0112 | LONG | 5 | 20 | AE 表 C09134AC（mode 0） | 5×LONG AE 狀態 | 是：`FUN_c0218c38` :19264 | SIGMA 私有 |
| 44 | MN | 0x000B | ASCII | 18 | 18 | MULTI mode2 blk_c00.c:149886 | "sRGB"/"AdobeRGB (1998)" | 否 | SIGMA 私有 |
| 45 | IFD0 | 0xC65D | BYTE | 16 | 16 | tagMgr #1 | RawDataUniqueID（由 0xA420 轉 16 B） | 是：tagMgr v1 | DNG 選用(渲染) |
| 46 | IFD0 | 0xC68D | LONG | 4 | 16 | `FUN_c02c4418` blk_c02.c:123473 | ActiveArea | 否 | DNG 必要 |
| 47 | IFD0 | 0xC761 | DOUBLE | 2 | 16 | `FUN_c02cd838` blk_c02.c:129477 | NoiseProfile 2×DOUBLE | 是：`FUN_c02cd678` blk_c02.c:129412 | DNG 選用(渲染) |
| 48 | MN | 0x0007 | ASCII | 16 | 16 | AWB `FUN_c02b03a0` blk_c02.c:109481 | WB 模式字串 | 是：`FUN_c02b0458` blk_c02.c:109513 | SIGMA 私有 |
| 49 | MN | 0x002A | RATIONAL | 2 | 16 | lens `FUN_c0363438` blk_c03.c:67305 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 50 | MN | 0x002B | RATIONAL | 2 | 16 | lens `FUN_c03634e0` blk_c03.c:67336 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 51 | MN | 0x0116 | SRATIONAL | 2 | 16 | 色彩 `FUN_c02c7448` → `FUN_c02c5090` :124020 | 2×SRATIONAL | 否 | SIGMA 私有 |
| 52 | MN | 0x0128 | RATIONAL | 2 | 16 | lens `FUN_c0363900` blk_c03.c:67536 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 53 | MN | 0x0131 | SRATIONAL | 2 | 16 | AWB `FUN_c02b1220` blk_c02.c:109975 | 2×SRATIONAL | 是：`FUN_c02b12a8` | SIGMA 私有 |
| 54 | MN | 0x0134 | RATIONAL | 2 | 16 | `FUN_c00ca3f0` blk_c00.c:151826 | 2×RATIONAL 常數 | 否 | SIGMA 私有 |
| 55 | MN | 0x0137 | RATIONAL | 2 | 16 | 色彩 `FUN_c02c7448` → `FUN_c02cd5d8` :129347 | 2×RATIONAL | 是：`FUN_c02cd538` | SIGMA 私有 |
| 56 | MN | 0x003D | ASCII | 14 | 14 | 色彩 `FUN_c02c7448` → `FUN_c02cc408` :128655 | 色彩模式名稱（14 B 字串） | 變更時：`FUN_c02cc620` | SIGMA 私有 |
| 57 | IFD0 | 0xC6F9 | LONG | 3 | 12 | `FUN_c02c4d40` blk_c02.c:123858 | ProfileHueSatMapDims {36,2,1} 常數 DAT_c096fdf0 | 否 | DNG 選用(渲染) |
| 58 | EXIF | 0xA431 | ASCII | 12 | 12 | `FUN_c00c33f8` mode2 blk_c00.c:149529 | BodySerialNumber | 否 | 標準中繼資料 |
| 59 | MN | 0x000A | ASCII | 12 | 12 | lens `FUN_c0363248` blk_c03.c:67221 | 鏡頭字串 | 否 | SIGMA 私有 |
| 60 | MN | 0x0016 | ASCII | 12 | 12 | MULTI mode2 blk_c00.c:149658 | "Qual:12bit"/10/8 | 否 | SIGMA 私有 |
| 61 | MN | 0x0033 | FLOAT | 3 | 12 | AWB `FUN_c02b11a0` blk_c02.c:109953 | WB 3×FLOAT | 是：`FUN_c02b1120` | SIGMA 私有 |
| 62 | MN | 0x0048 | ASCII | 12 | 12 | lens `FUN_c0363598` blk_c03.c:67380 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 63 | IFD0 | 0x0110 | ASCII | 11 | 11 | `FUN_c00ca220` blk_c00.c:151750 | "SIGMA fp" | 否 | 標準中繼資料 |
| 64 | IFD0 | 0xC614 | ASCII | 11 | 11 | `FUN_c00ca1a0` blk_c00.c:151730 | UniqueCameraModel "SIGMA fp" | 否 | DNG 必要 |
| 65 | MN | 0x0002 | ASCII | 10 | 10 | MULTI mode2 blk_c00.c:149877 | 序號 ASCII（`FUN_c00cc290`） | 否 | SIGMA 私有 |
| 66 | IFD0 | 0xC62F | ASCII | 9 | 9 | `FUN_c00c2b20` mode2 blk_c00.c:149376 | CameraSerialNumber（`FUN_c00cc290` vt+0xC） | 否 | 標準中繼資料 |
| 67 | IFD0 | 0x011A | RATIONAL | 1 | 8 | `FUN_c00c2b20` mode2 blk_c00.c:149419 | 72/1 | 否 | 標準中繼資料 |
| 68 | IFD0 | 0x011B | RATIONAL | 1 | 8 | `FUN_c00c2b20` mode2 blk_c00.c:149420 | 72/1 | 否 | 標準中繼資料 |
| 69 | IFD0 | 0xC61F | LONG | 2 | 8 | `FUN_c06a5290` blk_c06.c:134012 (`FUN_c00ba310`) | DefaultCropOrigin desc[6..7] | 否 | DNG 必要 |
| 70 | IFD0 | 0xC620 | LONG | 2 | 8 | `FUN_c02c43c0` blk_c02.c:123454 | DefaultCropSize | 否 | DNG 必要 |
| 71 | IFD0 | 0xC62A | SRATIONAL | 1 | 8 | `FUN_c00c2b20` mode2 blk_c00.c:149370；色彩 `FUN_c02cbb70` blk_c02.c:128312 覆寫 | BaselineExposure | 是：`FUN_c02cbb20` blk_c02.c:128296 | DNG 選用(渲染) |
| 72 | IFD0 | 0xC62B | RATIONAL | 1 | 8 | `FUN_c00c2b20` mode2 blk_c00.c:149371 | BaselineNoise 10/10 | 否 | DNG 選用(渲染) |
| 73 | IFD0 | 0xC62C | RATIONAL | 1 | 8 | `FUN_c00ca1e0` blk_c00.c:151740 | BaselineSharpness | 否 | DNG 選用(渲染) |
| 74 | IFD0 | 0xC763 | BYTE | 8 | 8 | tagMgr #2 | TimeCodes（SMPTE，`FUN_c00d0248`） | 是：tagMgr v1 | CinemaDNG |
| 75 | IFD0 | 0xC764 | SRATIONAL | 1 | 8 | `FUN_c00c2b20` mode2 blk_c00.c:149380 | FrameRate `FUN_c00c9bd0`（設定 +0x14 → 30000/1001…） | 否 | CinemaDNG |
| 76 | IFD0 | 0xC772 | RATIONAL | 1 | 8 | AE 表 C091319C（handler C0218BD0，`FUN_c0217340`） | TStop | 是：`FUN_c0218c38` blk_c02.c:19298 | CinemaDNG |
| 77 | EXIF | 0x829A | RATIONAL | 1 | 8 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | ExposureTime | 是：`FUN_c0218c38` blk_c02.c:19233 | 標準中繼資料 |
| 78 | EXIF | 0x829D | RATIONAL | 1 | 8 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | FNumber | 是：`FUN_c0218c38` :19235 | 標準中繼資料 |
| 79 | EXIF | 0x9201 | SRATIONAL | 1 | 8 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | ShutterSpeedValue | 是：`FUN_c0218c38` :19249 | 標準中繼資料 |
| 80 | EXIF | 0x9202 | RATIONAL | 1 | 8 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | ApertureValue | 是：`FUN_c0218c38` :19251 | 標準中繼資料 |
| 81 | EXIF | 0x9203 | SRATIONAL | 1 | 8 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | BrightnessValue | 是：`FUN_c0218c38` :19255（mode 3） | 標準中繼資料 |
| 82 | EXIF | 0x9204 | SRATIONAL | 1 | 8 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | ExposureBiasValue | 是：`FUN_c0218c38` :19257 | 標準中繼資料 |
| 83 | EXIF | 0x9205 | RATIONAL | 1 | 8 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | MaxApertureValue | 是：`FUN_c0218c38` :19260 | 標準中繼資料 |
| 84 | EXIF | 0x9206 | RATIONAL | 1 | 8 | lens `FUN_c0364810` blk_c03.c:67959 | SubjectDistance（對焦距離） | 是：`FUN_c0364798` blk_c03.c:67936 | 標準中繼資料 |
| 85 | EXIF | 0x920A | RATIONAL | 1 | 8 | lens `FUN_c0364888` blk_c03.c:67982 | FocalLength | 是：`FUN_c0364900` | 標準中繼資料 |
| 86 | EXIF | 0xA20E | RATIONAL | 1 | 8 | 色彩 `FUN_c02c51f8` blk_c02.c:124058 | FocalPlaneXResolution | 否 | 標準中繼資料 |
| 87 | EXIF | 0xA20F | RATIONAL | 1 | 8 | 色彩 `FUN_c02c51f8` blk_c02.c:124059 | FocalPlaneYResolution | 否 | 標準中繼資料 |
| 88 | EXIF | 0xA404 | RATIONAL | 1 | 8 | `FUN_c00c33f8` mode2 blk_c00.c:149522 | DigitalZoomRatio | 否 | 標準中繼資料 |
| 89 | EXIF | 0xA500 | RATIONAL | 1 | 8 | `FUN_c00c33f8` mode2 blk_c00.c:149530 | Gamma 2.2 | 否 | 標準中繼資料 |
| 90 | MN | 0x0003 | ASCII | 8 | 8 | MULTI mode2 blk_c00.c:149645 | "SINGLE"/"MULTI"… | 否 | SIGMA 私有 |
| 91 | MN | 0x0005 | ASCII | 8 | 8 | tagMgr #9 | 設定 +0x1BC 字串 | 每 10 幀 | SIGMA 私有 |
| 92 | MN | 0x000D | SRATIONAL | 1 | 8 | 色彩 `FUN_c02c7448` → `FUN_c02cbc18` blk_c02.c:128344 | 色彩參數 | 變更時：`FUN_c02cbbc0` | SIGMA 私有 |
| 93 | MN | 0x000E | SRATIONAL | 1 | 8 | MULTI mode2 `FUN_c00ba208` blk_c00.c:149887 | 零填 placeholder | 否 | SIGMA 私有 |
| 94 | MN | 0x000F | SRATIONAL | 1 | 8 | MULTI mode2 `FUN_c00ba208` blk_c00.c:149888 | 零填 placeholder | 否 | SIGMA 私有 |
| 95 | MN | 0x0010 | SRATIONAL | 1 | 8 | 色彩 `FUN_c02c7448` → `FUN_c02cbcc8` :128376 | 色彩參數 | 變更時：`FUN_c02cbc70` | SIGMA 私有 |
| 96 | MN | 0x0011 | SRATIONAL | 1 | 8 | 色彩 `FUN_c02c7448` → `FUN_c02cbd78` :128408 | 色彩參數 | 變更時：`FUN_c02cbd20` | SIGMA 私有 |
| 97 | MN | 0x0012 | SRATIONAL | 1 | 8 | 色彩 `FUN_c02c7448` → `FUN_c02c4f08` :123913 | 色彩參數 | 否 | SIGMA 私有 |
| 98 | MN | 0x0019 | ASCII | 8 | 8 | tagMgr #11 | "%03uof%03u" | 是（值不變） | SIGMA 私有 |
| 99 | MN | 0x002C | RATIONAL | 1 | 8 | lens `FUN_c0364b78` blk_c03.c:68121 | 鏡頭 RATIONAL | 是：`FUN_c0364ae8` | SIGMA 私有 |
| 100 | MN | 0x0047 | SRATIONAL | 1 | 8 | AE 表 C09134AC（mode 0） | AE SRATIONAL | 否 | SIGMA 私有 |
| 101 | MN | 0x0056 | SRATIONAL | 1 | 8 | AE 表 C09134AC（mode 0） | AE SRATIONAL | 否 | SIGMA 私有 |
| 102 | MN | 0x0063 | SRATIONAL | 1 | 8 | AE 表 C09134AC（mode 0） | AE SRATIONAL | 否 | SIGMA 私有 |
| 103 | MN | 0x0066 | SHORT | 4 | 8 | tagMgr #13 | crop 幾何 | 每 10 幀 | SIGMA 私有 |
| 104 | MN | 0x0085 | SRATIONAL | 1 | 8 | MULTI mode2 blk_c00.c:149663 | SRATIONAL 常數 | 否 | SIGMA 私有 |
| 105 | MN | 0x0100 | SSHORT | 4 | 8 | tagMgr #14 | 4×SSHORT（`FUN_c05a66a8`/10，溫度?） | 每 10 幀 | SIGMA 私有 |
| 106 | MN | 0x0114 | SRATIONAL | 1 | 8 | AE 表 C09134AC（mode 0） | SRATIONAL | 否 | SIGMA 私有 |
| 107 | MN | 0x0119 | SHORT | 4 | 8 | `FUN_c00ca3b0` blk_c00.c:151812 | 4×SHORT 常數 DAT_c0748f08 | 否 | SIGMA 私有 |
| 108 | MN | 0x011B | DOUBLE | 1 | 8 | 色彩 `FUN_c02c7448` → `FUN_c02c5178` :124035 | DOUBLE | 否 | SIGMA 私有 |
| 109 | MN | 0x011C | RATIONAL | 1 | 8 | AE 表 C09134AC（mode 0） | RATIONAL | 是：`FUN_c0218c38` :19295 | SIGMA 私有 |
| 110 | MN | 0x0127 | RATIONAL | 1 | 8 | AE 表 C09134AC（mode 0） | RATIONAL | 是：`FUN_c0218c38` :19297 | SIGMA 私有 |
| 111 | EXIF | 0x9010 | ASCII | 7 | 7 | tagMgr #5 | OffsetTime | 是（值不變） | 標準中繼資料 |
| 112 | EXIF | 0x9011 | ASCII | 7 | 7 | tagMgr #6 | OffsetTimeOriginal | 是（值不變） | 標準中繼資料 |
| 113 | EXIF | 0x9012 | ASCII | 7 | 7 | tagMgr #7 | OffsetTimeDigitized | 是（值不變） | 標準中繼資料 |
| 114 | IFD0 | 0x010F | ASCII | 6 | 6 | `FUN_c00c2b20` mode2 blk_c00.c:149409 | "SIGMA" | 否 | 標準中繼資料 |
| 115 | MN | 0x007C | SHORT | 3 | 6 | 色彩 `FUN_c02c7448` → `FUN_c02cc838` :128749 | 3×SHORT | 變更時：`FUN_c02cc870` | SIGMA 私有 |
| 116 | IFD0 | 0x00FE | LONG | 1 | 4 | `FUN_c00c2b20` mode2 blk_c00.c:149357 | NewSubfileType=0 常數 DAT_c07480a8 | 否 | DNG 必要 |
| 117 | IFD0 | 0x0100 | LONG | 1 | 4 | `FUN_c06a5290` blk_c06.c:133973 | 寬，format descriptor puVar3[0] | 否 | DNG 必要 |
| 118 | IFD0 | 0x0101 | LONG | 1 | 4 | `FUN_c06a5290` blk_c06.c:133975 | 高 puVar3[1] | 否 | DNG 必要 |
| 119 | IFD0 | 0x0111 | LONG | 1 | 4 | `FUN_c06a5290` blk_c06.c:133988 (src=0) + v9 `@C06A4C48` blk_c06.c:133811 | StripOffsets = 對齊後表頭長 | 否 | DNG 必要 |
| 120 | IFD0 | 0x0116 | LONG | 1 | 4 | `FUN_c06a5290` blk_c06.c:133990 | RowsPerStrip=高 | 否 | DNG 必要 |
| 121 | IFD0 | 0x0117 | LONG | 1 | 4 | `FUN_c06a5290` blk_c06.c:133992 | StripByteCounts `FUN_c02da770(desc)` | 否 | DNG 必要 |
| 122 | IFD0 | 0x828D | SHORT | 2 | 4 | `FUN_c00c2b20` mode2 blk_c00.c:149361 | CFARepeatPatternDim 2,2（RAM DAT_c2efb4e4，執行期初始化） | 否 | DNG 必要 |
| 123 | IFD0 | 0x828E | BYTE | 4 | 4 | `FUN_c00c2b20` mode2 blk_c00.c:149362 | CFAPattern（RAM DAT_c2efb4e0） | 否 | DNG 必要 |
| 124 | IFD0 | 0x8769 | LONG | 1 | 4 | `FUN_c00c1ca0` blk_c00.c:148753 | Exif IFD 指標 | 否 | DNG 必要 |
| 125 | IFD0 | 0xC612 | BYTE | 4 | 4 | `FUN_c00c2b20` mode2 blk_c00.c:149366 | DNGVersion 1.4.0.0 | 否 | DNG 必要 |
| 126 | IFD0 | 0xC613 | BYTE | 4 | 4 | `FUN_c00c2b20` mode2 blk_c00.c:149367 | DNGBackwardVersion 1.4.0.0 | 否 | DNG 必要 |
| 127 | IFD0 | 0xC619 | SHORT | 2 | 4 | `FUN_c00c2b20` mode2 blk_c00.c:149364 | BlackLevelRepeatDim 2,2 | 否 | DNG 必要 |
| 128 | IFD0 | 0xC61D | LONG | 1 | 4 | `FUN_c06a5290` blk_c06.c:134009 | WhiteLevel=(1<<bits)-1；8-bit 時 0xFFF | 否 | DNG 必要 |
| 129 | IFD0 | 0xC6FD | LONG | 1 | 4 | `FUN_c00c2b20` mode2 blk_c00.c:149378 | ProfileEmbedPolicy=1 | 否 | DNG 選用(渲染) |
| 130 | EXIF | 0x8832 | LONG | 1 | 4 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | RecommendedExposureIndex | 是：`FUN_c0218c38` :19245 | 標準中繼資料 |
| 131 | EXIF | 0x9000 | UNDEFINED | 4 | 4 | `FUN_c00c33f8` mode2 blk_c00.c:149508 | "0231" | 否 | 標準中繼資料 |
| 132 | EXIF | 0xA000 | UNDEFINED | 4 | 4 | `FUN_c00c33f8` mode2 blk_c00.c:149509 | "0100" | 否 | 標準中繼資料 |
| 133 | MN | 0x0004 | ASCII | 4 | 4 | MULTI mode2 blk_c00.c:149698 | 畫質字串 | 否 | SIGMA 私有 |
| 134 | MN | 0x002F | LONG | 1 | 4 | 色彩 `FUN_c02c7448` → `FUN_c02cbe10` :128436 | 色彩 LONG | 變更時：`FUN_c02cbdd0` | SIGMA 私有 |
| 135 | MN | 0x003E | LONG | 1 | 4 | tagMgr #12 | 設定 +0x338/+0x33C | 每 10 幀 | SIGMA 私有 |
| 136 | MN | 0x006F | LONG | 1 | 4 | MULTI mode2 blk_c00.c:149660 | 常數 | 否 | SIGMA 私有 |
| 137 | MN | 0x010D | BYTE | 4 | 4 | tagMgr #17 | 4×BYTE | 否 | SIGMA 私有 |
| 138 | MN | 0x0113 | SLONG | 1 | 4 | 色彩 `FUN_c02c7448` → `FUN_c02ccda8` :128981 | SLONG | 是：`FUN_c02ccdf0` | SIGMA 私有 |
| 139 | MN | 0x0006 | ASCII | 3 | 3 | tagMgr #10 | 同上 | 每 10 幀 | SIGMA 私有 |
| 140 | MN | 0x008F | UNDEFINED | 3 | 3 | MULTI mode2 blk_c00.c:149703 | 3 B 常數＋旗標 | 否 | SIGMA 私有 |
| 141 | MN | 0x0111 | BYTE | 3 | 3 | AE 表 C09134AC（mode 0）；strobe :115250 覆寫 | 3×BYTE | 否 | SIGMA 私有 |
| 142 | IFD0 | 0x0102 | SHORT | 1 | 2 | `FUN_c06a5290` blk_c06.c:133978 | 位元深 `FUN_c02da870(desc[9])` | 否 | DNG 必要 |
| 143 | IFD0 | 0x0103 | SHORT | 1 | 2 | `FUN_c06a5290` blk_c06.c:133986 | 1（未壓縮）；+4 旗標非 0 時 7 | 否 | DNG 必要 |
| 144 | IFD0 | 0x0106 | SHORT | 1 | 2 | `FUN_c00c2b20` mode2 blk_c00.c:149358 | 0x8023 CFA 常數 | 否 | DNG 必要 |
| 145 | IFD0 | 0x0112 | SHORT | 1 | 2 | `FUN_c00c2b20` mode2 blk_c00.c:149418 | Orientation `FUN_c00c9b48()`（重力感測） | 否 | 標準中繼資料 |
| 146 | IFD0 | 0x0115 | SHORT | 1 | 2 | `FUN_c00c2b20` mode2 blk_c00.c:149359 | SamplesPerPixel=1 | 否 | DNG 必要 |
| 147 | IFD0 | 0x011C | SHORT | 1 | 2 | `FUN_c00c2b20` mode2 blk_c00.c:149360/149365 | PlanarConfig（同一 tag 加兩次，後者覆寫） | 否 | DNG 必要 |
| 148 | IFD0 | 0x0128 | SHORT | 1 | 2 | `FUN_c00c2b20` mode2 blk_c00.c:149421 | ResolutionUnit=2 | 否 | 標準中繼資料 |
| 149 | IFD0 | 0xC617 | SHORT | 1 | 2 | `FUN_c00c2b20` mode2 blk_c00.c:149363 | CFALayout=1 | 否 | DNG 必要 |
| 150 | IFD0 | 0xC635 | SHORT | 1 | 2 | `FUN_c00c2b20` mode2 blk_c00.c:149377 | MakerNoteSafety=0 | 否 | 標準中繼資料 |
| 151 | IFD0 | 0xC65A | SHORT | 1 | 2 | `FUN_c06a5290` blk_c06.c:134015 | CalibrationIlluminant1=17 | 否 | DNG 必要 |
| 152 | IFD0 | 0xC65B | SHORT | 1 | 2 | `FUN_c06a5290` blk_c06.c:134017 | CalibrationIlluminant2=21 | 否 | DNG 必要 |
| 153 | EXIF | 0x8822 | SHORT | 1 | 2 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | ExposureProgram | 否 | 標準中繼資料 |
| 154 | EXIF | 0x8827 | SHORT | 1 | 2 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | ISO | 是：`FUN_c0218c38` :19273 | 標準中繼資料 |
| 155 | EXIF | 0x8830 | SHORT | 1 | 2 | `FUN_c00c33f8` mode2 blk_c00.c:149506 | SensitivityType=2 | 否 | 標準中繼資料 |
| 156 | EXIF | 0x9207 | SHORT | 1 | 2 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | MeteringMode | 否 | 標準中繼資料 |
| 157 | EXIF | 0x9208 | SHORT | 1 | 2 | AWB `FUN_c02b1488` blk_c02.c:110086 | LightSource | 是：`FUN_c02b1400` blk_c02.c:110061 | 標準中繼資料 |
| 158 | EXIF | 0x9209 | SHORT | 1 | 2 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | Flash | 否 | 標準中繼資料 |
| 159 | EXIF | 0xA001 | SHORT | 1 | 2 | `FUN_c00c33f8` mode2 blk_c00.c:149516 | ColorSpace 1/0xFFFF | 否 | 標準中繼資料 |
| 160 | EXIF | 0xA210 | SHORT | 1 | 2 | `FUN_c00c33f8` mode2 blk_c00.c:149525 | FocalPlaneResolutionUnit=2 | 否 | 標準中繼資料 |
| 161 | EXIF | 0xA217 | SHORT | 1 | 2 | `FUN_c00c33f8` mode2 blk_c00.c:149518 | SensingMethod | 否 | 標準中繼資料 |
| 162 | EXIF | 0xA401 | SHORT | 1 | 2 | `FUN_c00c33f8` mode2 blk_c00.c:149521 | CustomRendered | 否 | 標準中繼資料 |
| 163 | EXIF | 0xA402 | SHORT | 1 | 2 | AE 表 C09131BC（`FUN_c0217340`，mode 0） | ExposureMode | 否 | 標準中繼資料 |
| 164 | EXIF | 0xA403 | SHORT | 1 | 2 | AWB `FUN_c02b1728` blk_c02.c:110222 | WhiteBalance | 是：`FUN_c02b16c0` blk_c02.c:110207 | 標準中繼資料 |
| 165 | EXIF | 0xA405 | SHORT | 1 | 2 | lens `FUN_c0364a30` blk_c03.c:68069 | FocalLengthIn35mm | 是：`FUN_c0364978` | 標準中繼資料 |
| 166 | EXIF | 0xA406 | SHORT | 1 | 2 | `FUN_c00c33f8` mode2 blk_c00.c:149523 | SceneCaptureType | 否 | 標準中繼資料 |
| 167 | EXIF | 0xA408 | SHORT | 1 | 2 | 色彩 `FUN_c02cb800` blk_c02.c:128170 | Contrast | 變更時：`FUN_c02cb880` | 標準中繼資料 |
| 168 | EXIF | 0xA409 | SHORT | 1 | 2 | 色彩 `FUN_c02cb900` blk_c02.c:128212 | Saturation | 變更時：`FUN_c02cb988` | 標準中繼資料 |
| 169 | EXIF | 0xA40A | SHORT | 1 | 2 | 色彩 `FUN_c02cba10` blk_c02.c:128254 | Sharpness | 變更時：`FUN_c02cba98` | 標準中繼資料 |
| 170 | MN | 0x0008 | ASCII | 2 | 2 | AE 表 C09134AC（mode 0） | AE 字串（handler C02182F8） | 否 | SIGMA 私有 |
| 171 | MN | 0x0009 | ASCII | 2 | 2 | AE 表 C09134AC（mode 0） | AE 字串（handler C02183B0） | 否 | SIGMA 私有 |
| 172 | MN | 0x0020 | SHORT | 1 | 2 | strobe `FUN_c02b8638` blk_c02.c:115235（AE observer C0228BF4 呼叫） | 閃燈狀態位元 | 否 | SIGMA 私有 |
| 173 | MN | 0x0027 | SHORT | 1 | 2 | lens `FUN_c0363328` blk_c03.c:67241 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 174 | MN | 0x0104 | BYTE | 2 | 2 | lens `FUN_c0363698` blk_c03.c:67398 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 175 | MN | 0x0105 | BYTE | 2 | 2 | lens `FUN_c0363708` blk_c03.c:67418 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 176 | MN | 0x0107 | BYTE | 2 | 2 | lens `FUN_c03637e0` blk_c03.c:67457 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 177 | MN | 0x0108 | SHORT | 1 | 2 | lens `FUN_c0363850` blk_c03.c:67491 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 178 | MN | 0x0118 | SHORT | 1 | 2 | `FUN_c00ca308` blk_c00.c:151786 | 常數 | 否 | SIGMA 私有 |
| 179 | EXIF | 0xA300 | UNDEFINED | 1 | 1 | `FUN_c00c33f8` mode2 blk_c00.c:149519 | FileSource | 否 | 標準中繼資料 |
| 180 | EXIF | 0xA301 | UNDEFINED | 1 | 1 | `FUN_c00c33f8` mode2 blk_c00.c:149520 | SceneType | 否 | 標準中繼資料 |
| 181 | MN | 0x0028 | BYTE | 1 | 1 | lens `FUN_c0363390` blk_c03.c:67259 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 182 | MN | 0x0029 | BYTE | 1 | 1 | lens `FUN_c03633f0` blk_c03.c:67272 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 183 | MN | 0x002D | BYTE | 1 | 1 | lens `FUN_c0364c08` blk_c03.c:68134 | 鏡頭 BYTE | 是：`FUN_c0364c50` | SIGMA 私有 |
| 184 | MN | 0x002E | BYTE | 1 | 1 | lens `FUN_c0364ce0` blk_c03.c:68173 | 鏡頭 BYTE | 是：`FUN_c0364c98` | SIGMA 私有 |
| 185 | MN | 0x0072 | BYTE | 1 | 1 | MULTI mode2 blk_c00.c:149659 | 常數 | 否 | SIGMA 私有 |
| 186 | MN | 0x0074 | BYTE | 1 | 1 | AWB `FUN_c02b02c0` blk_c02.c:109430 | WB | 是：`FUN_c02b0278` | SIGMA 私有 |
| 187 | MN | 0x0075 | BYTE | 1 | 1 | AWB `FUN_c02b0350` blk_c02.c:109456 | WB | 是：`FUN_c02b0308` | SIGMA 私有 |
| 188 | MN | 0x007D | BYTE | 1 | 1 | 色彩 `FUN_c02c7448` → `armGold` :128811 | BYTE | 變更時：`rBlue` | SIGMA 私有 |
| 189 | MN | 0x007E | BYTE | 1 | 1 | 色彩 `FUN_c02c7448` → `FUN_c02ccb30` :128867 | BYTE | 變更時：`FUN_c02cca68` | SIGMA 私有 |
| 190 | MN | 0x008E | BYTE | 1 | 1 | MULTI mode2 blk_c00.c:149664 | 常數 | 否 | SIGMA 私有 |
| 191 | MN | 0x0101 | BYTE | 1 | 1 | tagMgr #15 | 設定 +0x24 | 每 10 幀 | SIGMA 私有 |
| 192 | MN | 0x0102 | BYTE | 1 | 1 | MULTI mode2 blk_c00.c:149894 | 設定 +0x1B | 否 | SIGMA 私有 |
| 193 | MN | 0x0106 | BYTE | 1 | 1 | lens `FUN_c0363778` blk_c03.c:67437 | 鏡頭資訊 | 否 | SIGMA 私有 |
| 194 | MN | 0x010A | BYTE | 1 | 1 | 色彩 `FUN_c02c7448` → `FUN_c02c4f70` :123975 | BYTE | 否 | SIGMA 私有 |
| 195 | MN | 0x010C | BYTE | 1 | 1 | MULTI mode2 blk_c00.c:149665＋tagMgr #16 | BYTE | 否 | SIGMA 私有 |
| 196 | MN | 0x010E | BYTE | 1 | 1 | tagMgr #18 | BYTE | 否 | SIGMA 私有 |
| 197 | MN | 0x0110 | BYTE | 1 | 1 | AE 表 C09134AC（mode 0）；strobe `FUN_c02b8638` :115245 覆寫 | BYTE | 否 | SIGMA 私有 |
| 198 | MN | 0x0115 | BYTE | 1 | 1 | 色彩 `FUN_c02c7448` → `FUN_c02c5090` :124016 | BYTE | 否 | SIGMA 私有 |
| 199 | MN | 0x011E | BYTE | 1 | 1 | MULTI mode2 blk_c00.c:149933 | BYTE | 否 | SIGMA 私有 |
| 200 | MN | 0x0125 | BYTE | 1 | 1 | MULTI mode2 blk_c00.c:149949 | 旗標 | 否 | SIGMA 私有 |
| 201 | MN | 0x0126 | BYTE | 1 | 1 | 色彩 `FUN_c02c7448` → `FUN_c02cd3d8` :129235 | BYTE | 是：`FUN_c02cd448` | SIGMA 私有 |
| 202 | MN | 0x0132 | BYTE | 1 | 1 | 色彩 `FUN_c02c7448` → `FUN_c02cd4f8` :129286 | BYTE | 是：`FUN_c02cd4b8` | SIGMA 私有 |

---

## 4. 0xC634 DNGPrivateData 的內容（6,734 B）[V]

格式：16 B 魔術字 `"SIGMA_EXTH_SPPA\0"`，接著一個小端 IFD（**378 筆**，offset 從容器開頭算），next=0。

| 類型×count | 筆數 | 值區 bytes |
|---|---|---|
| SRATIONAL×1 | 204 | 1,632 |
| BYTE×1 | 72 | inline |
| SSHORT×1 | 48 | inline |
| SHORT×1 | 42 | inline |
| SSHORT×32 | 8 | 512 |
| SHORT×4 | 4 | 32 |
| 合計 | 378 | 2,428（inline 的也算進去）；佔用 = 16＋2＋378×12＋4＋2,176 out-of-line = 6,734 |

產生者：
- `FUN_c00c4f90` blk_c00.c:150086-150360：215 筆，幾乎全部是常數表 DAT_c07483F5..C074869C 的值。tag 0x0003-0x0069、0x1003-0x3025 三組（0x1xxx／0x2xxx／0x3xxx 同值）、0xFFFD-0xFFFF；0x56/0x1052/0x2052/0x3052 依 `FUN_c02db528` 選表 DAT_c074869C [V]。
- 色彩 `FUN_c02c7448`：`FUN_c02ca050`（0x09/0x16 族）、`FUN_c02ca560`（0x19-0x1B 族）、`FUN_c02cad28`（0x5A-0x5F 族，24 筆）、`FUN_c02cb0c0`（0x60/0x63 族）、
  `FUN_c02c4678`（0x2C/0x1020…）、`FUN_c02c4708`、`FUN_c02c47f8`、`FUN_c02cb4c0`（SSHORT×32 鏡頭表，來源 `FUN_c02d3a90`）以及 `FUN_c02c9928/9a58/9ad8/9cf0/9e38/ca3d0/ca740/ca800/ca938/cab90` [V]。
- AWB：`FUN_c02b1790`（DAT_c096bfbc 表）、`FUN_c02b0510`（DAT_c096bf8c 表）[V]。
- v9 `FUN_c06a5ac8`：0x101F/0x201F/0x301F SHORT×4 [V]。
- 每幀：色彩 `FUN_c02c9980/c02c9a00/c02c9bc8/c02c9d80/c02c9f28/c02ca478/c02ca6c0/c02ca888/c02caa48/c02cac48/c02cb1d0`、AWB `FUN_c02b06c0/c02b1830`，大多是「跟上次不同才寫」[V]。
- 判讀：這是 SIGMA Photo Pro 顯影參數（每個色彩／色調設定的數值，分成 3 組）；單筆都很小，佔用的大頭是 IFD 項目本身（378×12 = 4.5 KB）[I]。

---

## 5. 總量

### 5.1 依 IFD（stock 12-bit 幀；「值 bytes」不含容器本身）

| 區段 | 標籤數 | 值 bytes（type×count） | 實際佔用（項目表＋out-of-line 值） |
|---|---|---|---|
| TIFF 頭 | — | — | 8 |
| IFD0 | 58（含 0x8769、0xC634） | 16,040 | 16,664 |
| └ 0xC634 私有 IFD | 378 | 2,428 | 6,734（含 16 B 魔術字） |
| Exif | 47（含 0x927C） | 482 | 1,004 |
| └ MakerNote（0x927C） | 97 | 53,230 | 54,338（含 10 B "SIGMA\0\0\0\x01\x04" 頭） |
| GPS | 0（沒有 GPS 時不建立） | 0 | 0 |
| 對齊補白（`FUN_c0699390(…,0x400)`） | | | 100 |
| **合計** | **580** | | **78,848 = 0x13400** |

### 5.2 依分類（值 bytes）

| 分類 | bytes | 主要項目 |
|---|---|---|
| SIGMA 私有（MakerNote） | 53,230 | 0x12D 16,384、0x200 16,384、0x12B 9,216、0x117 8,192、0x124/0x129 1,152、0x43/0x45 512 |
| SIGMA 私有（0xC634） | 2,428（佔用 6,734） | 378 個顯影參數 |
| DNG 必要（校正）0xC74E | 12,564 | WarpRectilinear＋GainMap |
| DNG 選用（渲染）0xC6F9-C6FD、0xC62A-C62C、0xC65D、0xC761 | 2,824 | Profile HueSatMap×2、ToneCurve |
| 標準中繼資料（TIFF／Exif） | 799 | 0x10E/0x13B/0x8298（各 64 B 使用者字串）、0x9286 72、0xA434 96 |
| DNG 必要（解碼） | 311 | 0x100-0x117、CFA、0xC612-C61F、ColorMatrix、AsShotNeutral、ActiveArea… |
| CinemaDNG | 24 | 0xC763 TimeCodes、0xC764 FrameRate、0xC772 TStop |

真正「解碼影像」需要的（DNG 必要＋OpcodeList3）只有約 12.9 KB；**去掉 MakerNote 與 0xC634 之後，表頭約 18 KB**。

---

## 6. 程式會加、但這一幀沒有的（條件式）

| 標籤 | 產生者 | 條件 | 大小 |
|---|---|---|---|
| IFD0 0xC618 | `FUN_c02c4908` blk_c02.c:123700 | `*(*(ctx+0xF0)+8)==4` | 512 B |
| IFD0 0x142-0x145 | `FUN_c06a5290` blk_c06.c:133996-134000、v9 blk_c06.c:133816 | format 的 `+4` 旗標（壓縮／tile） | 8＋4×N×2 |
| GPS IFD 0x00-0x1F | `FUN_c05cc870`；每幀 `FUN_c05ccee8` blk_c05.c:155932 | `FUN_c00d2830()`（有 GPS） | 約 200 B（0x1B/0x1C 可變長度） |
| 0xC634 0x101F/0x201F/0x301F | `FUN_c06a5ac8` | `[[0xC3074910]]==1` | 3×8（這一幀**有**） |
| MN 0x43 閃燈版 | `FUN_c02b8638` | `[0xC3202D08]!=0` | 256（覆蓋 AE 版） |
| IFD1 0x132 | tagMgr #19 | flag 只有 1/2，不含 4 → 不加；每幀寫入的查詢會失敗 | 0 |

---

## 7. 尚未確定的部分

- `FUN_c02b18d0`（AWB 錄影資訊加入者）是經 vtable 呼叫的；判定它在開錄時被叫到，是靠「標籤有出現在實檔」[I]。
- 色彩 vt+0x14／+0x1C 對 movie 不做事，是因為 DataPool vt+0x24／+0x30 對 type-2 DataPool 回 0；這個回傳值沒有逐一核對 [I]。
- AE 用的是表組 0xC3202870：依據是 `FUN_c02173e8` 的參數分支＋實檔，沒追 movie 實際傳入的參數 [I]。
- MN 0x200 的 side info 由約 90 個呼叫點寫入原型，沒有逐一標出各自的 offset [I]。
- MN 0x11A 的 25 個值是 ISP 物件 `ctx+0x19C → vt+0x3C → vt+0x18` 給的 u16 陣列 /10000，語意沒查清楚 [I]。
