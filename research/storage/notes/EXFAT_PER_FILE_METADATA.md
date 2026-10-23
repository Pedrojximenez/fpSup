# exFAT 每檔中繼資料:原廠對卡寫了什麼、何時寫(fp 5.02)

2026-10-14。純靜態(`out/MAIN_c0000000.bin`、`out/decomp/full/blk_c03.c`、`blk_c06.c`、capstone)。沒有上機。
[C]=程式碼證實(附位址),[I]=推論。承接 [`WRITE_PATH_AFTER_BULK.md`](WRITE_PATH_AFTER_BULK.md)(WP)。
FS 層函式幾乎全是 **Thumb-2**(首字 `e92d 4xxx` = push.w),呼叫位址要 +1;`C036B678` 是 ARM。

## 0. 結論先講

1. **錄 CinemaDNG 期間,原廠把 FS 切到「不同步」模式,每個檔的目錄項、bitmap、FAT 都只寫進 RAM cache,關檔不寫卡。** [C]
   - 錄影開始 `XC_StillCreateRaw::v4`(C0377A30,模式 1)先呼叫媒體驅動 v6(`C036B678`,vtable `0xC0B97A24`)
     參數 0 → `C063B098` → `C06415C0(vol, 4, &0)` → `vol+0x481C = 0`,再呼叫 `C0378A50` → `C03A5050`(CinemaDngFile 初始化)。
   - 停錄 `C0398D88` 在 `C03A5190(…,1)`(停止聚合)之後把它設回 1 → 這時才把全部中繼資料一次寫出。
2. **每個 DNG 從開到關,穩態下對卡的非影像寫入次數 ≈ 0。** 只有攤提的:每 ~16 檔讀一次 2 KiB 目錄窗、
   每 ~512 檔寫一次 ≤64 KiB 的目錄、bitmap 扇區很少被換出、每 ~1024 檔目錄長一個 cluster(數筆小寫入 + 兩種 cache 強制 flush)。[C 機制 / I 頻率]
3. **WP §4「SD 每檔多 ~3.2 ms」很可能不是中繼資料,也不是積壓**:三個 SD 情境的批次週期都正好等於攢滿一批所需的幀時間
   (57 檔 ÷ 119.88 fps = 475 ms ≈ 254+211 = 465 ms;57 ÷ 59.94 = 951 ≈ 939;8 ÷ 23.976 = 334 ≈ 320),
   持續 MB/s 也等於需求(135 vs 131、212 vs 203)⇒ **空檔是在等幀**,拿它擬合出的 m_f = 3.19 ms 是假象。[I,算術]
   SSD 240p 週期 186 ms vs 攢滿 179 ms,才是真的略為積壓。WRITER_THEORY 的 m_f 與「W3 中繼資料合併優先」需要重新評估。
4. FS 層的逐檔路徑 SD 與 SSD **完全相同**(同一個 FS、同一個 sync 開關),所以就算有逐檔成本,也不會因媒體不同而差 8 倍。[C]
5. 既有的延後機制就是第 1 點的 sync-off + 寫回 cache + 64 KiB 目錄合併緩衝。要「一塊只寫一次」只需在批次邊界加一次 flush(§7),不必重寫 exFAT。

## 1. 物件與 cache

volume = `0xC37D066C + idx*0x4A68`(SD idx 1 = `0xC37D50D4`)。檔案 handle 0x614 B(pool,`C0650C00`)。

| 欄位 | 意義 | 證據 |
|---|---|---|
| vol+0x2EC/0x338/0x384/0x3D0 | kind0/1/2/3 cache 物件(各 0x4C) | `C0644A30` 初始化 [C] |
| file+0x5C8 | kind4 cache 物件(每檔) | `C0650DA0` → `C0646B00(vol,4,…)` [C] |
| vol+0x481C | **關檔同步**:1=每次關檔 flush kind1/kind2;0=不 flush,啟用目錄合併緩衝 | 掛載 `C0644E30` 設 1;唯一寫入者 `C06415C0` 碼 4 [C] |
| vol+0x4820 | cache 策略:0=寫回(dirty),1=直寫,2=不 cache | 掛載設 0;碼 7 的 setter 沒有呼叫者 [C] |
| vol+0x4814/0x4818 | 目錄空槽提示 {dir cluster, entry index} | `C06452C0/F0/D8` [C] |
| vol+0x45B0/0x47BC | 絕對路徑 → 目錄資訊 MRU cache | `C063D738/C063D7B0` [C] |
| vol+0x147C… | RAM 的 free-extent 表(next-fit) | `C064A040`、`C064B260`、`C0649F48` [C] |
| file+0x248 | {FirstCluster, **NoFatChain**} | `C064F338`、`C063D870` [C] |
| file+0x250/0x254 | DataLength(= 寫到的最大位置) | `C063F380` 尾、`C064F338` [C] |
| file+0x220 | 1 = 新檔、目錄項尚未建立 | `C063E820` [C] |
| file+0x228..0x247 | 32 B「類 FAT 目錄項」暫存:屬性 +0xB、時間戳 | `C064F2B8`、`C063EB90` [C] |

### 1.1 cache 種類(表 `0xC2E34818` 筆數 {16,16,4,1,1}、`0xC2E3482C` sectors {1,1,4,1,16})

| kind | 物件 | 筆 × 大小 | 內容 | 證據 |
|---|---|---|---|---|
| 0 | vol+0x2EC | 16 × 1 sector | 開機區:exFAT VBR 主/備份(sector 0、12,只寫 PercentInUse 0x70=0xFF);FAT32 FSInfo | `C0644560`、`C0644698`;只在掛載 `C0644A30` 寫並 flush [C] |
| 1 | vol+0x338 | 16 × 1 sector | **FAT 與 allocation bitmap 共用** | FAT:`C06473C0`;bitmap:`C0648EB0`(讀改寫 1 byte)、`C0649050` [C] |
| 2 | vol+0x384 | 4 × 4 sector(2 KiB = 64 個目錄項) | **目錄** | `C0647AC8/BB0/C20/CC8/D80`、`C064E5D0` [C] |
| 3 | vol+0x3D0 | 1 × 1 sector | 批次聚合寫入的佔位;只有 `C063F140` 用,模式 3(直寫),永遠不會 dirty | 唯一呼叫點 [C] |
| 4 | file+0x5C8 | 1 × 16 sector(8 KiB) | 每檔資料 cache,處理非聚合路徑的不對齊頭尾 | `C063EE10`、`C063F380`(cVar5==2)、`C063F898` [C] |

窗對齊:`C0646B00` 以資料區起點 mod 窗大小為基準;kind2..4 的窗不超過一個 cluster。[C]

### 1.2 cache 存取 `C0646580(vol, kind, cache, mode, sector64, off, len, buf)` [C]
- mode 0=讀、1=寫(走 cache);2..5 = 直接 I/O(3、5 寫),**之前先 `C0646050(…,1)` 把同 kind 的 dirty 寫出並作廢**。
- 走 cache 的寫:`C0646248` 找窗;沒命中就以 LRU(+0xC 年齡)換出,**換出的若 dirty 先寫卡**(`C0645D80`);
  寫的長度不滿一窗時**先讀整窗**(`C0645C28`)。策略 0 → 標 dirty(state 2),策略 1 → 立刻寫並 `C0645BD0`。
- flush `C0646050(vol,kind,cache,p)`:p=0 寫出 dirty(依 sector 排序,**每筆整窗一條寫入**)、保留;p=1 寫出並作廢;p=2 直接丟掉。
  包裝:`C0646BD0`。錯誤路徑 `C0646F00` 對 kind0..3 用 p=2 —— **寫卡出錯時,RAM 裡延後的中繼資料整批丟棄**。
- **目錄合併緩衝**:`DAT_c2f2e648`(= [0xC37E3014],64 KiB)、裝置 `DAT_c2f2e64c`、範圍 `c2f2e650..65c`。
  只對 kind2、只在 sync off(`C0645B10(vol, 481C==0)` 啟用)。`C0645D80` 把相鄰的窗併進去,不相鄰或滿 64 KiB 才發一條 `C01EB790`;
  `C0645BD0` 在每次 flush 尾端把它寫出;讀到重疊範圍時 `C0645C28` 也會先寫出。[C]

## 2. 開檔(建立新檔)[C]

```
C069ADE0  flags: 0x806(有不對齊段)/ 0x1806(全部 512 對齊,C069AD80)/ 0x406(只有靜態 DNG,C03813D0 第 4 參數 0)
 └ C0365FB0 → XC_MediaFileSdCard::v1 (C0368178)
     0x806 → 模式 4;0x1806 → 模式 10;0x406 → 模式 2(+0x400 = C0367708 先 mkdir -p)
     0x10806 → 模式 4×10=0x28(06CMD20 用,WP §9.1)
 └ C063B180(取 FS 鎖)
     模式 4/10/0x28:**不查同名**,直接 -4 → C063E820(create)
     模式 2:C063E580 查,不存在才 create
 └ C063E820
     C063D5B0 路徑→volume;C06417F0 → C01EB3A0(SD 只看寫保護旗標 C0662DF0,無指令)
     C0650DA0 取 handle(檢查同路徑已開 → -8);C0646B00 初始化 kind4
     file+0x24C = (vol 是 exFAT && 非模式 7) ? 1 : 0      ← NoFatChain 預設開
     模式 10:C0646BF8(vol,4,file+0x5C8, 2) —— 資料 cache 關閉
     C0649650 / C064B610(配置狀態 1;模式 0x28 且 vol+0x1FF0==0 → 狀態 2 = VSC AU 模式)
```
- **開檔不建立目錄項、不寫卡、不讀卡**(路徑走 MRU cache)。目錄項延到關檔才建(file+0x220=1)。
- 例外:VSC AU 模式(只有 0x10806 且卡支援 VSC)在開檔就 `C0649DB8`(CMD20)、`C064A040` 配一整個 AU、`C0649E70`(CMD20)。

## 3. 寫資料:cluster、bitmap、FAT [C]

```
C063B898(FS 鎖)→ C063F380
  C064B730 預留(只查 RAM:C0647DC0、C0649900 讀 vol+0x1FDC 等計數)
  C063D870(每次要一段):長度向上取整成 cluster
   └ C064B858 → C064A040(vol, flags, n, &start, &got, &last)
       C0649F48(vol,1):free-extent 表空了才掃整張 bitmap(C064ABF8,經 kind1 讀)
       exFAT:C0648F98 → 每個 cluster 一次 C0648EB0 = kind1 讀 1 B + 寫 1 B(只動 RAM,dirty)
       flags bit1(非連續):C0647908 → C06473C0 寫 FAT 鏈到 kind1(dirty)
   ├ 新段與既有段相鄰 → 只延長,保持 NoFatChain
   └ 不相鄰且 file+0x24C=1 → 補寫整條 FAT(C0647908 mode 2 + 新段 mode 1)、清 NoFatChain、C064BBC0 設 bit1
  聚合(SD 恆開):C063F048 → 驅動回呼 vol+0x483C(SD = C065F061,直接填 ADMA2 描述子,不碰 cache)
```
- 一個 DNG 在乾淨卡上是一段連續 cluster ⇒ **NoFatChain、不寫 FAT;bitmap 每個 cluster 一個 bit,全在 kind1 RAM。** [C]
- 用的是 next-fit 的 free-extent 表;一檔被批次邊界切成兩次配置時仍相鄰(同一條 extent)。[I]
- 聚合路徑不使用 kind4;只有 arena 失敗退回 cVar5==2 時,不對齊頭尾才進 kind4(0x806)。[C]

## 4. 關檔 [C]

```
XC_MediaFile::~ (vtable+8) → C0369430(取秒數 C0370210/1000)→ C063B3D0(FS 鎖)
 → C063CDE0(設時間)→ C06416E0(…,6)→ C063EB10
    C063EA08 → C063EB90:
       C0646BD0(vol,4,file+0x5C8,0)            kind4 flush(0x1806 策略 2 = 無事;聚合路徑也無 dirty)
       C064BA50                                  狀態 1:只有 bit1(非連續)才寫 FAT;連續檔什麼都不做
       時間戳:modify(+0x240/+0x23E)、access=modify(+0x23A/+0x23C)、UTC offset = vol+0x1430;
               新檔另設 create(+0x238/+0x236)、create 10ms(+0x235)
       新檔 → C063E3F8 → C063DE58(父目錄,MRU cache)→ C064D2E0 → exFAT C064E808
              → param 1:**跳過同名檢查**(C064E1D0)→ C064E980
                 從提示 vol+0x4818 往前一格開始掃(kind2 讀,通常命中),找 2+ceil(名長/15) 個空項;
                 不夠 → 擴目錄(§5.4)
                 C064FB80:File 0x85 / Stream 0xC0 / Name 0xC1×k,算 SetChecksum(C064F1C0,略過 File 的 byte 2–3),
                           每項 C0647D80 = kind2 寫(dirty,不寫卡)
       舊檔 → C063DE58 + C064D238 → C064E458 重寫整組
    C064BB48:狀態 1 什麼都不做;狀態 2(VSC)= C064BC08 退還 AU 剩餘 + C0649F18(CMD20)
    C0650E90 放 handle
    C063D510:vol+0x481C ? flush kind1 : 不做
    C063D490:vol+0x481C ? flush kind2 : 不做
```
Stream extension(`C064F338`):GeneralSecondaryFlags = **1,或 3(NoFatChain)**;NameLength、NameHash;
**ValidDataLength = DataLength = file+0x250(實際位元組,不含 cluster 補齊)**;FirstCluster = file+0x248。
File entry(`C064F2B8`):SecondaryCount、SetChecksum、屬性、三組時間戳、10ms、UTC offset。

⇒ 錄影中(481C=0):**關檔 0 筆寫卡**。不錄影時(481C=1,例如一般檔案操作):每次關檔 = 每個 dirty bitmap/FAT 扇區各一條 512 B +
每個 dirty 目錄窗一條 2 KiB(合併緩衝關閉,逐窗寫)。

## 5. 什麼時候真的寫卡(錄影中)

| # | 觸發 | 寫什麼 | 頻率(FHD/120p 類,128 KiB cluster,每檔 4 個目錄項) |
|---|---|---|---|
| 5.1 | kind2 換出 dirty 窗 | 2 KiB 進合併緩衝;不相鄰或滿 64 KiB 才發一條寫入 | 寫:每 ~512 檔一條 ≤64 KiB [I] |
| 5.2 | kind2 新窗未命中(寫不滿一窗要先讀) | **讀** 2 KiB | 每 ~16 檔一次 [I] |
| 5.3 | kind1 換出 dirty bitmap 扇區 | 512 B | 一個 bitmap 扇區管 4096 cluster(~455 檔);16 筆 LRU,很少換出 [I] |
| 5.4 | 目錄 cluster 用完(C064E980 → C064F550) | 配 1 cluster(bitmap)、直寫補零 128 KiB(C064E5D0 模式 3,先 flush+作廢 kind2)、目錄若是 NoFatChain 且新 cluster 不相鄰則補整條 FAT(C064E100,flush kind1)、改父目錄的 DataLength(C064D238)、**最後無條件 flush kind2 與 kind1** | 每 ~1024 檔一次 [I] |
| 5.5 | free-extent 表用完(C0649F48) | 經 kind1 讀整張 bitmap,可能把 dirty bitmap 擠出去 | 罕見 [I] |
| 5.6 | 停錄 C0398D88 → C06415C0(碼 4, 1) | `C0645B10` 寫出合併緩衝並關閉 → flush kind1(每個 dirty 扇區一條 512 B)→ flush kind2(每個 dirty 窗一條 2 KiB) | 每段一次 [C] |

- 批次送出 `C063F140` 只 flush kind3(永遠空),**不會**帶出 kind1/kind2。[C]
- 一般寫入 `C063F898`(音訊)先送出影像批,但不 flush 中繼資料。[C]
- ⚠ `C0398D88` 的 `iVar2==2` 分支呼叫 `C03A5190(…,0)` 後直接 return,不把 481C 設回 1(sync 留在 off 到下次停錄)。[C]

## 6. 每個 DNG 的帳(問題 5)

| 分支 | 開檔 | 寫入期間 | 關檔 | 攤提 |
|---|---|---|---|---|
| **錄影中,0x806 或 0x1806,連續**(常態) | 0 | 0(bitmap 只在 RAM) | 0(目錄項只在 RAM) | 5.1–5.4:≈ 1/16 次 2 KiB 讀 + 1/512 次 ≤64 KiB 寫 + 極少的 512 B |
| 錄影中,cluster 不連續 | 0 | FAT 鏈進 kind1 RAM | 0 | 多碰幾個 FAT 扇區;kind1 只有 16 筆,碎片化時換出變多 [I] |
| 0x806 vs 0x1806 | 相同 | 聚合路徑相同;非聚合退路時 0x806 頭尾進 kind4 | 0x806 可能 flush kind4(≤8 KiB) | — |
| 聚合關(SSD Standard) | 0 | 每幀直寫 | 0 | 同上(sync 開關跟聚合無關) |
| VSC AU 模式(0x10806 + V 卡) | CMD20 ×2 + 配一個 AU | 同上 | 退還 AU 剩餘(bitmap)+ CMD20 | WP §12.4 |
| sync on(非錄影的一般寫檔) | 0 | 0 | 512 B × dirty bitmap/FAT 扇區 + 2 KiB × dirty 目錄窗(多半 1+1) | — |

⇒ **原廠在錄影中沒有「每檔一筆中繼資料 I/O」。** [C 機制、I 頻率]

## 7. 可借的延後機制與 hook 點(問題 6、7)

**既有機制**:sync-off(vol+0x481C=0)+ 寫回 cache(策略 0)+ 64 KiB 目錄合併緩衝。它已經把中繼資料延到換出或停錄。
**強迫 flush 的呼叫點**:`C0398D88`(停錄,經 `C036B678` → `C063B098` → `C06415C0`)、`C064F550`(擴目錄)、
`C064E100`、`C064E5D0` 模式 3 前的 `C0646050(…,1)`、LRU 換出(`C0646248`)、合併緩衝重疊讀(`C0645C28`)、
`C06407A8`(rmdir)、錯誤 `C0646F00`(丟棄)。

**若要「同一塊的目錄項與 bitmap 只寫一次,且跟資料一起落地」**:
- **hook 點:`C063F140`(Thumb,0xC063F141)在 `C0646C60` 成功之後、cookie 回呼之前**(仍在 FS 鎖內):
  依序 `C0646BD0(vol,1,vol+0x338,0)`、`C0646BD0(vol,2,vol+0x384,0)`(後者尾端 `C0645BD0` 寫出合併緩衝)。
  效果:每批 = 資料 1 條 + bitmap 通常 1 條 512 B + 目錄 1 條(相鄰窗由合併緩衝串成 ≤64 KiB)。
  寫入順序變成「資料先、中繼資料後」,斷電時卡上目錄只會指向已寫完的資料。
- 代價:比原廠多寫(原廠幾乎不寫);每批多 2 條小寫入。這是**一致性**的改進,不是速度改進。
- 若目標是速度,依 §0.3 原廠的逐檔中繼資料 I/O 本來就近乎 0,W3 預期收益要先用 M1(`C01EB790`/`C01EB730` 計數)確認。

**風險**:
1. 斷電一致性(原廠就有):錄影中目錄項幾乎都只在 RAM;斷電 = 整段只剩換出過的部分。合併緩衝可能在對應資料批寫入**之前**
   就把目錄項寫出(換出時機與批次無關)⇒ 斷電後目錄可能指向還沒寫的 cluster。[I]
2. 錯誤路徑 `C0646F00` 丟棄所有 dirty cache:寫卡錯誤時,這段錄影的目錄項全部消失。[C]
3. 檔案大小:目錄項在關檔才建、DataLength 取 file+0x250 ⇒ 不存在「建檔時大小未知」的問題;
   若改成在開檔或批次前預寫目錄項,就必須之後重寫 Stream(DataLength/ValidDataLength)與 SetChecksum。
4. 同名:模式 4/10 不查同名、關檔也跳過檢查 ⇒ 名稱重複會產生重複目錄項。[C]
5. 錄影中的目錄掃描/回放:經 kind2 cache 讀,RAM 內一致;但合併緩衝裡的窗只有 `C0645C28` 重疊時才寫出再讀,
   其他裝置(另一張媒體)拿不到合併緩衝(全域一個裝置)。[C]
6. 擴目錄(§5.4)會在批次中途插入 128 KiB 補零直寫與兩種 cache flush,是錄影中唯一成串的中繼資料 I/O;
   預先把目錄做大(或錄影前預配置目錄 cluster)可避開。[I]
7. hook 在 FS 鎖內呼叫 flush,錯誤要走原廠 `C0646F00`;不要在鎖外呼叫 cache 函式(cache 與合併緩衝都是全域、無自己的鎖)。[C]

## 8. 未解 / 要上機確認

- 錄影中讀 `0xC37D50D4+0x481C`(SD)應為 0、`+0x4820` 應為 0;`DAT_c2f2e64c` 應為 SD 的裝置碼 0xE。
- M1:hook `C01EB790`/`C01EB730`(Thumb +1)記 {tick, LBA, 長度},驗證「每檔 0 筆、每 ~16 檔一次 2 KiB 讀」。
- CinemaDNG 實際檔名長度(決定每檔 3 或 4 個目錄項)。
- §0.3 的「SD 不是積壓」用一段 SD UHS-II 240p(真積壓)的 rec log 確認;若那時空檔仍 ∝ 檔數,再找 CPU 端原因。
