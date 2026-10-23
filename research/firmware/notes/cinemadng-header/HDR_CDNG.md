# SIGMA fp 5.02 — CinemaDNG 每幀表頭的所有產生路徑

2026-10-14，純離線研究：反編譯 `out/decomp/full/blk_c0*.c`、映像 `out/MAIN_c0000000.bin`（capstone 反組譯），
以及 repo 內 115 個目錄的實拍 DNG（每目錄第一幀，自寫 TIFF 解析器）。未上機。

證據等級：**[V]** = 反編譯或反組譯看過（含映像讀出的 vtable／表格）；**[I]** = 推論。
`blk_c03.c:94924` 這種寫法表示反編譯檔與行號。

修正既有筆記（GYRO2_CAMERA_DESIGN.md §11）的三處：
1. `C038BFE4..BFF0` 呼叫的 vt+0x10 是 `XC_StillCreateFile::v2 @C037DD50`，**它只把 handle 排進佇列**（`FUN_c0377008`）。
   真正寫檔的是 vt+0x18 `XC_StillCreateFile::v4 @C037E0F8`，在存檔任務中執行（vtable `C0B9AEEC`：+0x10=C037DD50、+0x18=C037E0F8）[V]。
2. 每幀改寫的不只 tagMgr 表裡的 20 筆，**還有 observer**：`FUN_c00559f0` 會通知全域 Subject `0xC31AC4EC` 上的 observer
   （最多 9 個），它們用同一個 `FUN_c05a4bc0` 機制寫標籤（0x9206、0x829A、0x9203、0xC61A、0xC74E、MN 0x117 等）[V]。
3. 表頭長度**不是固定 0x13400**：有 LinearizationTable（0xC618）時是 0x13800，整個 MakerNote 往後移 0x20C [V，實檔＋builder]。

---

## 0. 對焦距離的寫入路徑（gyro2 參考）

### 0.1 呼叫鏈（每幀，MovRec 任務內，在 DMA 之前）[V]

```
MovRecFuncStateCinemaDng::v38 @C038BC50  (event+0xC == 5, RAW 完成)
 └ FUN_c038bd98                                   blk_c03.c:94926
    ├ C038BFC4  str [req+0x14C] = [0xC358DBA4]    ; 表頭長度
    └ C038BFD0  bl FUN_c038c5f8                   blk_c03.c:95199
        ├ C038C66C blx tagMgr->vt(+0x170)+0xC  = XC_RecMgrTagCinema::v1 @C03A8490（20 筆表，見 §2）
        ├ C038C6CC bl FUN_c030cbc0(ctx,[req+0x4C]) → 存到 DataPool+0x4004（本幀 RAW 的 capture handle）
        ├ C038C700 bl FUN_c00559f0(Subject 0xC31AC4EC, mode=3, type=3, DataPool)
        │     ├ DataPool->vt+0x44 設 event {mode=3,type=3,flag=0}（DataPool+0x45E0）
        │     ├ FUN_c0055fe0: 依序呼叫 9 個 observer slot 的 vt+0xC(obs, DataPool)
        │     │   └ PictagLensObserverForAfterExpos::v1 @C0360C88   blk_c03.c:64622
        │     │       └ lens 物件 0xC3498DF0（vptr C0B9664C）vt+0x1C = FUN_c03644a8   blk_c03.c:67803
        │     │           mode==3 且 cache 有效 →
        │     │           FUN_c0364798 → FUN_c05a4bc0(&cache@C3498DB8, ifd=2, 0x9206, type=5, count=1, &{num,den})
        │     │           FUN_c0364900 → 0x920A FocalLength   (cache C3498DB0)
        │     │           FUN_c0364978 → 0xA405 FocalLengthIn35mm (C3498DA8)
        │     │           FUN_c0364ae8 → MakerNote 0x2C RATIONAL (C3498DA0)
        │     │           FUN_c0364c50 → MakerNote 0x2D BYTE     (C3498D98)
        │     │           FUN_c0364c98 → MakerNote 0x2E BYTE     (C3498D90)
        │     └ *(DataPool+0x45D4) = 0                    ; 「目前的 format」指標被清掉
        └ C038C77C blx FUN_c00fbb90({模板, [req+0x4C]-[req+0x14C], [req+0x14C], flags=0})
```

`FUN_c00559f0` 呼叫點的參數：`r0 = FUN_c00577f0()`（Subject 單例 `0xC31AC4EC`），`r1 = 3`（因為 `XC_RecMgrTagCinema::v1` 回傳 1；
非 cinema 的 `XC_RecMgrTag::v1 @C03A89D0` 回 0 → mode 2），`r2 = 3`，`r3 = DataPool`（`[0xC358DB98]`）[V，blk_c03.c:95229-95235]。

### 0.2 值從哪裡來 [V]
- `FUN_c0364798`（反組譯 C0364798..C036480C）：
  - 鏡頭在位（`FUN_c035f560` = `FUN_c035f550()==2`）：分子 = `FUN_c035fe48()`，分母 = `[C0B964C0]` = **1000** → 單位 mm，寫出公尺。
  - 無鏡頭：`{[C0B964C4]=0, [C0B964C8]=10}` = 0/10。
- `FUN_c035fe48` → `FUN_c0360380([0xC347FA6C])` → 鏡頭管理器 `0xC3464850`（vptr `C0B8DA14`）vt+0xB0 = `FUN_c03322d8`
  → 依 `[0xC3476408]`（0/1/2）選 focus provider，呼叫其 vt+0x60：
  | `[0xC3476408]` | 物件 | vt+0x60 | 回傳 |
  |---|---|---|---|
  | 0 | `LmountFocusNone`（0xC3476614，vptr C0B8FB34） | `@C0342428` | 常數 2000 |
  | 1 | `LmountFocusL`（FocsPred，0xC3476414，vptr C0B8EEEC） | `@C033EB28` | `*(*(obj+0x58)+0x1C)` |
  | 2 | `LmountFocusMc`（0xC34765CC，vptr C0B8F670） | `@C0341090` | `u16[ FUN_c034df70(obj+0x34)+0x30 ] * 10` |
- L 接環鏡頭的值是鏡頭通訊層快取在 `*(obj+0x58)+0x1C` 的最新值；**讀的時間是 event 5（RAW 完成）當下**，不是該幀曝光中點 [I]。
- 同一機制的鄰居：0x920A／0xA405 用 `FUN_c03629d8`（焦距），MN 0x2C 用 `FUN_c0362188(FUN_c0362da8(),1)/10`，
  MN 0x2D `FUN_c0362978`、MN 0x2E `FUN_c0362ab8`。

### 0.3 模板裡的位置怎麼找 [V]
`FUN_c05a4bc0(int cache[2], ifd, tag, type, count, src)`（blk_c05.c:126746）。`cache = {offset, fmt}`：
- `fmt == 0` → 直接回 0（什麼都不做）。
- `offset < 0`（第一次）→ `fmt->vt(+0x14)+0x30` = `XC_StillFileFormatDngTh::v10 @C06A5020` → `FUN_c05a51a8` → `FUN_c00bb288`
  **在已序列化的模板裡走 IFD 鏈找標籤**：ifd 0=IFD0、1=IFD0 的 next IFD、2=Exif（經 0x8769）、3=GPS（0x8825）、
  5=MakerNote（0x8769→0x927C，`FUN_c00c1110`）、8=DNGPrivateData（0xC634，`FUN_c00c0510`）。
  `FUN_c00bf180` 要求 **tag、type、count 三者都與模板中的項目相同**，然後把值寫進去（≤4 B 寫在 entry 內，否則寫到值區），
  回傳值在模板中的絕對位移，存入 `cache[0]`。找不到就回 -1，下一幀會再找一次。
- `offset ≥ 0`（之後每幀）→ `fmt->vt+0x34` = `v11 @C06A50B0`：`if (len+off <= 模板大小) memcpy(模板+off, src, len)`，
  `len = typesize[type] * count`（`DAT_c0746CDC` 表：1,1,2,4,8,1,1,2,4,8,4,8 對應 type 1..12）。
- 所以位置是**第一次寫入時以 tag 查詢、之後用快取的 offset**。

快取何時建立：開錄最後一次通知 `C0378F70: bl FUN_c00559f0(Subject, 2, 3, DataPool)`。此時
- `C0378F08` 已把 `NOTFOUND(format容器,1)`（DNG format 物件，+0x14 vtable `C2E3A938`）存進 `DataPool+0x45D4`；
- `FUN_c00559f0` 算出的 event flag = 1（上一次通知是 DataPool 建立時的 mode 0）。
`FUN_c03644a8` 看到 flag≠0 就把 6 個 cache 設成 `{-1, *(DataPool->vt+0x28)}`（blk_c03.c:67803-67870）。
每幀通知時 flag=0、`+0x45D4` 已是 0，所以每幀用的是開錄時抓到的 fmt；若 flag=1 而 `+0x45D4==0`，函式會提早 return，不會把 cache 弄壞。

### 0.4 寫法、大小、時序、成本
- 原地覆寫、長度固定；**模板長度永遠不變**（v11 有上界檢查，不會長大，也沒有 realloc）[V]。
- 時序：在 `C038C700`（通知）之內同步完成，早於 `C038C77C` 的 DMA；DMA 帶 flags=0、同步等完成（`FUN_c00fbb90` 在 `(char)p[3]==0` 時呼叫 `FUN_c00fbc10` 等待）[V]。
- 成本：快取命中時每個標籤 = 兩層虛擬呼叫 + 邊界檢查 + 8 B memcpy，約數十到一百多條指令 [I]。第一次（查表）要走 IFD 鏈，
  而且 `FUN_c00bf180` 會 `FUN_c03d8bd0(0x14)` 配一個暫存物件 [V]。

### 0.5 能不能寫任意長度的資料塊
- **可以，只要長度與模板裡該標籤的 count×typesize 一樣。** 原廠每幀就這樣寫 MakerNote 0x117：`FUN_c02ccf48`
  → `FUN_c05a4bc0(p,5,0x117,FLOAT,0x800,buf)` = **每幀 8 KB**（blk_c02.c:129078）[V]。MN 0x200 是 UNDEFINED×0x4000，
  用 `FUN_c05a4bc0(cache,5,0x200,7,0x4000,buf)` 就是每幀覆寫整個 16 KB（含 SIGMA 自己的 side info，要先備份）[I]。
- 更精準的做法：把 `fmt->vt+0x34`（v11）當成「模板內任意 offset、任意長度、有上界檢查的 memcpy」直接呼叫，
  只寫 0x200 的零尾。0x200 值區的 offset 可用唯讀查詢 `FUN_c05a4ca8`（vt+0x3C `v13 @C06A5188` → `FUN_c00bb830`
  → `FUN_c00bf360`，只複製出來、不寫入）取得 [V 函式語意；組合用法為 I]。
- 不能用這個機制**加**新標籤或改 count：查詢要求 tag/type/count 完全一致，模板序列化後就不再動。

### 0.6 sup 能不能加表項或 observer
- **表 `C0B9ED9C`：不能直接加。** 迴圈上限寫死 `0x14`（`XC_RecMgrTagCinema::v1` 的 `uVar2 < 0x14`），物件是固定 0x218 B，
  entry 指標放在 obj+0..+0x9C、cache 在 obj+0x178..+0x218，建構子 `FUN_c03a72f8` 逐一填入 20 個 [V]。要加只能改程式碼（迴圈上限、物件大小、配置器 `MPoolFixed<536,96>`）[I]，不建議。
  改既有 entry 的值指標（obj+8*i+4）技術上可行，但會影響原廠標籤。
- **observer 清單：可以。** Subject `0xC31AC4EC` 有 9 個 slot，註冊函式 `FUN_c00d2958(subject, obs)`（找空位、關中斷），
  移除 `FUN_c00d2a08` [V]。原廠註冊者只有 6 處（其中 GPS 有條件）[V]：
  | 註冊點 | observer 物件 | vt+0xC handler |
  |---|---|---|
  | `FUN_c00d26c8`（GPS，條件式） | GPS 物件 vt+0x14 | — |
  | `FUN_c0360fb8` | 0xC3498D5C | `PictagLensObserverForAfterExpos::v1 @C0360C88` |
  | `FUN_c0228c18` | 0xC320447C | AeTag observer `@C0228A48`（Ghidra 沒切成函式） |
  | `FUN_c022be40` | 0xC3206868 | `PictagAfObserverForAfterExpos::v1 @C022BE20` |
  | `FUN_c02ab798` | 0xC3409C7C | `AwbCameraTagObserver::v1 @C02B1D10` |
  | `FUN_c02bb928`（blk_c02.c:117371） | 0xC34142C0 | `FUN_c02b9010`（色彩／DNG 標籤） |
  → 至少 3 個空位 [I：沒有找到其他寫入 slot 的程式]。sup 的 observer 只要是一個 vptr 指向「+0xC = handler(this, DataPool)」的物件，
  handler 回非 0（回 0 會被自動移除）。handler 要：(a) 用 `DataPool->vt+0x40` 讀 event，只在 mode==3 時寫；
  (b) 在 flag≠0 且 `*(DataPool->vt+0x28)()` 非 0 時抓 fmt；(c) 注意它也會被拍照等其他 DataPool 通知呼叫。
  執行點在 lens observer 之後、DMA 之前，與 lossless（下游 writer）、supmod（C038BFE4）都不同點。

---

## 1. 開錄時的模板建構（一次）

主流程：`FUN_c0378a50`（blk_c03.c:82818）[V]
1. `FUN_c038a0f8()` = MovRec 單例 `0xC358DB98`：+0 DataPool、+4 tagMgr、+8 format 容器、+0xC 表頭長、+0x10 模板緩衝 [V]。
2. `FUN_c038a138` → `FUN_c00558f8(Subject, &dp, 3, 1)`（C038A154）：
   - 配 0x45EC 的 `DataPoolOfCameraTagConcrete<2770,XC_CameraTagsSideInfoOem>`，`FUN_c0056540` **從全域原型 `0xC308BA8C` 複製 16 KB side info**；
   - vt+0x58 `v20 @C00567A8`(3) → `FUN_c00c15e0(&b,2)` → `FUN_c00c1618` type 2 → **`FUN_c00c1ca0`** 建 builder，存 `DataPool+0x45D0`；
   - `FUN_c0057a40(0xC308BA8C)` 清原型 side info 的 +0x57C..+0x640；
   - `FUN_c00559f0(Subject, 0, 3, dp)`：**mode 0 通知，6 個 observer 把自己的標籤加進 builder**（`FUN_c00ba378` = builder add）。
   - `FUN_c03a87f0(&C3588D00,&tm,3)` 建 `XC_RecMgrTagCinema`（0x218 B，vt C0B9EF2C）。
3. `FUN_c02aaea0`（AWB／錄影資訊）、`FUN_c02b8e38(6,4,dp,set)`、`(3,4,…)`（色彩：ColorMatrix 等，含 `FUN_c02c4a50`、`FUN_c02c4908`）[V 呼叫；內容 I]。
4. `FUN_c038a220` → `FUN_c06a4990`：format 容器（`XC_StillMultiFileFormatTh`，vt C2E3A9E4），DNG 子物件 `FUN_c06a4808`
   → `FUN_c06a6340`（+0x88=1，無縮圖）或 `FUN_c06a6418`（+0x88=0，帶縮圖）；+0x14 vtable `C2E3A938`。`FUN_c06a4bb0` 設段 0 容量 0x18000 [V]。
5. 模板緩衝：`FUN_c038a288(容器->vt+0x10())` 用 `FUN_c001d038(…,0x40)` 配置，存單例 +0x10 [V]。
6. tagMgr 初值：`FUN_c03a7be0/7a08/77d8/7828/7840`；`C0378E90` tagMgr->vt+0x10 = `XC_RecMgrTagCinema::v2 @C03A85F8`：
   flag 含 4 的表項以 `FUN_c03a7c28 → FUN_c00ba378` 加進 builder（此時 `+0x45D4==0`，cache 是 `{-1,0}`）[V]。
7. **序列化** `C0378EB0`: `fmt->vt+0x2C` = `XC_StillFileFormatDngTh::v9 @C06A4C48`：
   取 builder（+0x88≠0 → `DataPool->vt+0x2C` = +0x45D0），`FUN_c06a4bd0` 加影像結構與 MN 0x200，加 0x111，
   長度 `FUN_c0699390(…, 0x400)` 對齊 0x400，builder vt+0x10 寫進模板，回傳長度 → `req+0x14C` 與單例 +0xC [V]。
8. `C0378F08`：`*(DataPool+0x45D4) = fmt`；`C0378F38` 設 event {2,3,0}；`C0378F54` 再呼叫 v2（建 cache `{-1,fmt}`）；
   `C0378F70` `FUN_c00559f0(Subject,2,3,dp)`（flag=1，observer 建 cache）[V]。

### 1.1 各 IFD／標籤群組的產生者

| 項目 | 產生時機 | 函式位址 | 資料來源 | 證據 |
|---|---|---|---|---|
| TIFF 頭 'II'、IFD0、Exif IFD（0x8769）、GPS IFD（0x8825，有 GPS 時）、MakerNote（0x927C，`FUN_c00c0908`）、0xC634 容器 | 開錄一次 | `FUN_c00c1ca0`（blk_c00.c:148699） | type 2；GPS 由 `FUN_c00d2830` 決定 | [V] |
| IFD0 預設標籤（0xFE、0x100-0x103、0x106、0x10E、0x10F、0x112、0x115、0x116、0x11A-0x11C、0x128、0x13B、0x828D/E、0x8298、0xC612/3、0xC617、0xC619、0xC62A/B/F、0xC635、0xC6FD、0xC764 …） | 開錄一次 | `FUN_c00c2b20`（blk_c00.c:149305） | 常數／設定 | [V] |
| Exif 預設（0x9000、0x9101/2、0x9286、0xA000-0xA003、0xA210、0xA217、0xA300/1、0xA401/4/6、0xA431、0xA500、0x8830） | 開錄一次 | `FUN_c00c33f8` | 常數／設定 | [V] |
| MakerNote 預設標籤（0xB、0xE、0xF、0x16、0x1E/1F、0x26、0x6F、0x72、0x85、0x8E/8F、0x102、0x10C、0x11D/E、0x125、0x138） | 開錄一次 | `MULTI`（blk_c00.c:149535） | 設定 | [V] |
| 0xC634 DNG private（SIGMA 私有 IFD，ifd 8：0x0E..0x69、0x1003..0x3025 …） | 開錄一次（部分每幀，見 §2.2） | `FUN_c00c4f90`（blk_c00.c:150086） | 設定／校正 | [V] |
| 影像結構：0x100-0x103、0x111、0x116、0x117、0x142-0x145、0xC61D、0xC61F、0xC65A、0xC65B | 開錄一次 | `FUN_c06a5290`（`FUN_c06a4bd0` 內） | format descriptor（format+0x18） | [V] |
| 0xC634 子項 0x101F/0x201F/0x301F | 開錄一次 | `FUN_c06a5ac8` | format | [V] |
| **MakerNote 0x200**（UNDEFINED×0x4000） | 開錄一次 | `FUN_c06a5630`（blk_c06.c:134024） | `DataPool::v1 @C00565F8` 複製 DataPool+4..+0x4004 | [V] |
| 0x111 StripOffsets（或 0x144/0x145） | 開錄一次 | `XC_StillFileFormatDngTh::v9 @C06A4C48` | format | [V] |
| 0xC618 LinearizationTable（256×SHORT） | 開錄一次，條件式 | `FUN_c02c4908`（blk_c02.c:123644） | `*(*(ctx+0xF0)+8)==4` 時才加 | [V] |
| ColorMatrix／色彩標籤 | 開錄一次 | `FUN_c02b8e38`→`FUN_c02b97a8`、`FUN_c02c4a50` | 色彩設定 | [I] |
| 鏡頭：0x9206、0x920A、0xA405、0xA432-0xA434、MN 0x0A、0x27-0x2E、0x48、0x104-0x108、0x128 | 開錄一次（mode 0） | lens observer `FUN_c0364020`（vt+0x14，blk_c03.c:67707） | 鏡頭管理器 | [V] |
| DateTime 0x132、0xC65D、0xC763 TimeCodes、0x9003/4、0x9010-12、0xA420、MN 數項 | 開錄一次（flag 4）＋每幀 | `XC_RecMgrTagCinema::v2 @C03A85F8` / v1 | 見 §2 | [V] |
| AE、AF、AWB、GPS、色彩 observer 的其他標籤 | 開錄一次（mode 0） | 各 observer vt+0xC | 各子系統 | [I：未逐一展開] |

---

## 2. 每幀更新

### 2.1 `XC_RecMgrTagCinema::v1 @C03A8490`（表 `C0B9ED9C`，20×0x14 B）[V]

entry 格式：`+0 index, +4 ifd, +8 tag(u16), +0xA count(u16), +0xC type(u16), +0x10 flags`。
flags：1/2/8 = 拍照用 builder（`XC_RecMgrTag::v2` 的 +0x20/+0x24/+0x30），**4 = 開錄時加進 movie builder**，
**0x10 = 每幀不寫**，**0x20 = 只有 `frame%10==0` 才寫**（frame = obj+0x174，每次 +1）。
寫入一律 `FUN_c03a7c70(obj+0x178+8i, obj+8i)` → `FUN_c05a4bc0`；值指標在 obj+8i+4，由下列 getter 設定。

| # | ifd | tag | type×count | flags | 產生時機 | getter（設值指標） | 資料來源 |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 0x132 DateTime | ASCII×20 | 0xF | 每幀 | `FUN_c03a7f30` (+0xC1) | `FUN_c03a7eb8` 時鐘（`FUN_c03a8a18`，變了才更新） |
| 1 | 0 | 0xC65D RawDataUniqueID | BYTE×16 | 0x6 | 每幀 | `FUN_c03a82d8` (+0xDC) | 由 0xA420 字串轉 16 byte |
| 2 | 0 | 0xC763 TimeCodes | BYTE×8 | 0x4 | 每幀 | `FUN_c03a7be0` (+0xEC) | `FUN_c00d0248(tc源=FUN_c037ff70, …)` |
| 3 | 2 | 0x9003 DateTimeOriginal | ASCII×20 | 0xF | 每幀 | `FUN_c03a7fb0` (+0xF4) | 時鐘 |
| 4 | 2 | 0x9004 DateTimeDigitized | ASCII×20 | 0xF | 每幀 | `FUN_c03a80e0` (+0x108) | 時鐘 |
| 5-7 | 2 | 0x9010/11/12 OffsetTime* | ASCII×7 | 0xF | 每幀（值只在開錄算） | `FUN_c03a8028` (+0xD5) | 時區 +0xB4/+0xB8 |
| 8 | 2 | 0xA420 ImageUniqueID | ASCII×33 | 0xF | 每幀 | `FUN_c03a82d8` (+0x11C) | `"%8s%04X…%08llX…"`，64-bit 計數器 `C3588D00`（`FUN_c03a7de8`→`FUN_c03a88a8` 每幀 +1，存 `[C307495C]+0x10`） |
| 9 | 5 | MN 0x05 | ASCII×8 | 0x2F | 每 10 幀 | `FUN_c03a78e0` (+0x13D) | 設定 +0x1BC |
| 10 | 5 | MN 0x06 | ASCII×3 | 0x2F | 每 10 幀 | `FUN_c03a78e0` (+0x145) | 同上 |
| 11 | 5 | MN 0x19 | ASCII×8 | 0xF | 每幀（值開錄算） | `FUN_c03a7658` (+0x148) | `"%03uof%03u"` |
| 12 | 5 | MN 0x3E | LONG×1 | 0x2F | 每 10 幀 | `FUN_c03a8158` (+0x154) | 設定 +0x338/+0x33C |
| 13 | 5 | MN 0x66 | SHORT×4 | 0x2F | 每 10 幀 | `FUN_c03a7a08` (+0x158) | crop 幾何 |
| 14 | 5 | MN 0x100 | SSHORT×4 | 0x2F | 每 10 幀 | `FUN_c03a81e0` (+0x160) | `FUN_c05a66a8(0..3)/10`（溫度）[I 語意] |
| 15 | 5 | MN 0x101 | BYTE×1 | 0x2F | 每 10 幀 | `FUN_c03a81e0` (+0x168) | 設定 +0x24 |
| 16 | 5 | MN 0x10C | BYTE×1 | 0x17 | 不每幀 | `FUN_c03a7658` (+0x169) | — |
| 17 | 5 | MN 0x10D | BYTE×4 | 0x17 | 不每幀 | `FUN_c03a7658` (+0x16A) | — |
| 18 | 5 | MN 0x10E | BYTE×1 | 0x1F | 不每幀 | `FUN_c03a7e30` (+0x16E) | — |
| 19 | 1 | 0x132 | ASCII×20 | 0x3 | 每幀嘗試 | `FUN_c03a7f30` (+0xC1) | CinemaDNG 沒有 IFD1（實檔 next IFD=0）→ 查詢每幀失敗、不寫 [V 實檔，I 影響] |

`v1` 也會用 `DataPool->vt+0x44` 設 event {2 或 3（每 10 幀）, 3, 0}，但隨即被 `FUN_c00559f0` 覆寫為 {3,3,flag} [V]。

### 2.2 observer 的每幀寫入（`C038C700` 通知內）

全部經 `FUN_c05a4bc0`，cache 在開錄通知時建立。[V] 為 `FUN_c05a4bc0` 呼叫本身；「哪個 observer、mode 3 是否會走到」標 [I] 的是沒有逐條追完分派。

| 標籤 | 產生時機 | 函式位址 | 資料來源 | 證據 |
|---|---|---|---|---|
| 0x9206、0x920A、0xA405、MN 0x2C/0x2D/0x2E | 每幀 | lens `FUN_c03644a8` → `FUN_c0364798/4900/4978/4AE8/4C50/4C98` | 鏡頭管理器（§0.2） | [V] |
| 0x829A ExposureTime、0x829D、0x8832、0x9201、0x9202、0x9205、0x8827、MN 0x112、0x11C、0x127、0xC772 | 每幀 | `FUN_c0218c38`（blk_c02.c:19084），cache `C32029D0..C3202A30` | **本幀**：`DataPool->vt+0x18` 取 `DataPool+0x4004` 的 handle → `FUN_c030cad0` | [V] 寫入／[I] 由 AeTag observer `@C0228A48` 呼叫 |
| 0x9203 BrightnessValue、0x9204 | 每幀，只在 mode==3 | 同上（`if (*event==3)`） | 同上 | [V] |
| 0xC61A BlackLevel | 每幀 | `FUN_c02ca190`（blk_c02.c:127150） | 色彩／感測器 | [V] 寫入／[I] observer |
| 0xC74E OpcodeList3 | 每幀 | `FUN_c02ce918`（blk_c02.c:130757） | 光學校正 | [V]／[I] |
| MN 0x117（FLOAT×0x800 = 8 KB） | 每幀 | `FUN_c02ccf48`（blk_c02.c:129078） | 32×32×2 gain 表 | [V]／[I] |
| MN 0x11A（DOUBLE×25） | 每幀 | `FUN_c02cd058` | — | [V]／[I] |
| MN 0x120（FLOAT×30） | 每幀 | `FUN_c02b1ca0`（AWB） | AWB | [V]／[I] |
| 其他 `FUN_c05a4bc0` 寫入者（MN 0x07、0x0D、0x10、0x11、0x2F、0x33、0x34、0x3D、0x74/75、0x7C-0x7E、0x82、0x10F、0x113、0x126、0x131、0x132、0x137；Exif 0x9208、0xA403、0xA408-0xA40A；IFD0 0xC628、0xC62A、0xC761；0xC634 子項；GPS 0x0-0x1F `FUN_c05ccee8`） | 視 observer 而定 | blk_c02.c:105744-130762、blk_c05.c:155932 | 各子系統 | [V] 呼叫存在／[I] 是否每幀 |

實檔佐證（GYRO2 §11）：A001_001 的 851 幀間有變動的 = 0xC61A、0xC65D、0xC763、0xA420、0x9203、0x9206、0xC74E、MN 0x100/0x117/0x11A/0x120，與上表一致；其他被重寫但值不變。

### 2.3 DMA 與存檔 [V]
- `C038C77C blx FUN_c00fbb90`：參數 `{src=[0xC358DBA8]（模板）, dst=[req+0x4C]-[req+0x14C], len=[req+0x14C], +0xC flags=0}`（`DAT_C0B9C218..24` 初值全 0）。flags=0 → 同步等完成。
- `C038BFF0 blx` → `XC_StillCreateFile::v2 @C037DD50(this,[req+0x10FC],1)`：設 req+0x1104，`FUN_c0377008` 排入佇列。
- 存檔任務：`XC_StillCreateFile::v4 @C037E0F8`，req+4==1（CinemaDNG）→ `req+0x4C -= req+0x14C`、format->vt+0x4C 設 descriptor、`FUN_c03a5348`（C03A5490 → `FUN_c069ADE0` 寫媒體）。SD 與外接 SSD 走同一條（SSD 實檔表頭同為 0x13400）[V 檔案／I 媒體層]。

---

## 3. MakerNote 0x200 的內容與零尾

- 內容：`DataPool+4 .. +0x4004` 的 16 KB `XC_CameraTagsSideInfoOem`，開錄時由 `FUN_c06a5630` 經 `DataPool::v1 @C00565F8`（`memcpy(dst, dp+4, min(n,0x4000))`）複製一次 [V]。之後每幀不再寫 → 整段錄影各幀相同 [V 實檔]。
- 來源：DataPool 建立時 `FUN_c0056540` 從全域原型 `0xC308BA8C` 複製（`FUN_c00561d0(dp+4, proto+4)`）；mode-0 通知期間 observer 可再改 [V／I]。
- 可變長的尾段：`DataPool::v2 @C0056B50` 把最多 **0x2B44** B 複製到 `dp+0x14C0`，也就是 0x200 blob 內 **offset 0x14BC 起**（`v3 @C0056BA8` 回傳 0x2B44）[V]。
  實檔最小「已用長度」正好是 0x14BC（尾段空）；其他錄影已用 0x14C5..0x3BFD → **零尾 = 0x4000 − 0x14BC − (v2 寫入長度)**，隨 v2 的內容長度變 [V 數字吻合，I 呼叫者未確認]。
- 實測零尾（115 個目錄的第一幀，全為 12-bit）：stock FHD 11,076 B；res-lab／OG 等 sup 下 8,8xx、3,2xx-3,7xx，
  **外接 SSD 的 1008×672 錄影只剩 1,027～1,186 B**（例如 `projects/res-lab/validation/20261012-m12-240-live/ssd-host-evidence/A001_289` = 1,027 B）。
  → 不能假設 ≥3 KB；gyro2 必須在開錄時量零尾長度，資料塊要能縮小或放棄。

---

## 4. 表頭長度隨模式改變嗎

| 情況 | strip offset（表頭長） | MakerNote 位置 | 0x200 值區 | 來源 |
|---|---|---|---|---|
| FHD／UHD／crop／OG2K（sup）／120-280p（res-lab）／SD／SSD，12-bit | 0x13400 | 0x4514（count 0xD442） | 0xD956 | 約 100 個目錄 [V] |
| 有 0xC618 LinearizationTable（A001_182，OG3K+119.88 退回 UHD30） | **0x13800** | 0x4720 | 0xDB62 | [V] |
| 拍照 DNG（_SDI，160×120 IFD0） | 0x11C00 | 0x2D44 | 0xC198 | 不同流程 [V] |

- 長度 = builder 序列化後對齊 0x400（`FUN_c0699390(...,0x400)`）[V]；加 512 B 的 LinearizationTable 就跨到下一個 0x400。
- `FUN_c02c4908` 只在 `*(*(ctx+0xF0)+8)==4` 時加 0xC618 [V]；這個值 4 應對應非 12-bit 的 RAW 格式（8/10-bit）[I，沒有 8/10-bit 實檔可驗證]。
- 段容量 `FUN_c06a4bb0` → 0x18000 [V]；模板緩衝大小 = 容器 vt+0x10（`XC_StillMultiFileFormat::v2 @C0699060`，兩個子 format 段長相加）[V]。
- 結論：**位置不能寫死**，要從 IFD0 → 0x8769 → 0x927C → 0x200 解析，或用 `FUN_c05a4ca8` 查詢。

---

## 5. 其他／替代路徑

搜尋範圍：`MovRecFuncStateCinemaDng::v0..v43`（blk_c03.c:94373-94922）、`XC_RecMgrRawCapture::v0..v3`（blk_c03.c:90072-90130）、
`FUN_c038a288/a138/a220` 的所有呼叫者、所有 `FUN_c05a4bc0` 呼叫者、`XC_StillCreateFile::v4` 的所有分支、`cineCapture`。

1. **模板建構只有一處**：`FUN_c038a138`、`FUN_c038a220`、`FUN_c038a288` 都只被 `FUN_c0378a50` 呼叫（`FUN_c038a2f0` 釋放另見 blk_c03.c:103503）[V]。
   沒有找到不使用模板、為每幀重新序列化的 CinemaDNG 路徑。
2. **每幀表頭只有一處**：`FUN_c038c5f8` 只被 `FUN_c038bd98` 呼叫，後者只由 `v38` 在 event 5 呼叫 [V]。
   v38 之外的 v1-v37、v43 是按鍵、鏡頭、設定變更、停止處理，沒有任何一個會產生表頭 [V]。
3. **除錯：只有 RAW、沒有表頭** [V]：`XC_StillCreateFile::v4` 當 `*(設定+0x358) != 0` 時走 else 分支
   （log 0x99990001），用 `FUN_c03660e8(file, [req+0x4C], FUN_c02da770(req+0x10))` 寫出副檔名 "RAW"（`C0B9ACBC`）的純像素檔，不寫 DNG 表頭（blk_c03.c:85809-85830）。
4. **錄影中擷取靜態影像** [V／I]：v3／v35 設 `param_1[6]` → event 5 時 `cineCapture(0xC358DD88, req+0x1030)`（@C03866F8）
   只把該幀的路徑排進 8 格佇列；停止後 `FUN_c0386960` 經 `FUN_c0382710`（拍照 RecMgr）產生**靜態影像**，
   用的是拍照的 DataPool／format，不是 CinemaDNG 幀表頭 [I]。
5. `XC_RecMgrRawCapture::v0..v3`：只是 RAW 請求介面（解構、取 buffer、`FUN_c001d6e0` 等待、設狀態），與表頭無關 [V]。
6. 縮時／間隔拍攝在 CinemaDNG 下：沒有找到專屬的表頭路徑 [I]。
7. `FUN_c00c2728` / `FUN_c00c2800`、`XC_PlayFuncSeqDngDeveloping`：播放／機內顯影讀 DNG，不在錄影路徑上（GYRO2 §11 與 raw-sink 稽核）。
8. 第三方：lossless-sup 掛在 `C03A5490`，supmod 換掉 `C038BFE4` 的 vt 讀取（GYRO2 §11.3）；兩者都在 DMA 之後，用的是同一個表頭。
9. **不同模式下表頭內容的差異**來自 builder 內容（例如 §4 的 0xC618），不是另一條程式路徑 [V]。
