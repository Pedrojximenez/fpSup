# 寫入 task 的鎖範圍:批次送出哪些步驟需要 FS 鎖(fp 5.02)

2026-10-14。純靜態(`out/MAIN_c0000000.bin`、`out/decomp/full/blk_c01/c03/c06.c`、capstone)。沒有上機。
[C]=程式碼證實(附位址),[I]=推論。承接 [`WRITE_PATH_AFTER_BULK.md`](WRITE_PATH_AFTER_BULK.md)(WP)、
[`EXFAT_PER_FILE_METADATA.md`](EXFAT_PER_FILE_METADATA.md)(EM)、`projects/rec-core/WRITER_SPEC.md`(§5.1/5.2/5.8)。

模式:FS 層、驅動層幾乎全是 Thumb(呼叫位址 +1):`C063F048/F140/F220/F310/F380`、`C0646580/6C60`、`C01EB790`、
`C01EFBE0`、`C065DB70`、`C065F020/F060/F268/EFE0/F000`、`C06702B8/0338/0248/0280/03C0`、`C06710D8`。
**ARM**:`C03A55D0`、`C03A5190`、`C0398D88`、`C0376300`、所有 TK-OS stub(`C01F8xxx`、`C0016xxx`)。

## 0. 結論先講

1. **送出本身不需要 FS 鎖。** `C0646C60(vol,3,vol+0x3D0,3,…,arena)` 在批次長度是 sector 倍數時,實際動作 =
   「把 kind3 那唯一一格 cache 的欄位重設」+「一次 `C01EB790`」。它讀的 vol 欄位(+0x1458/+0x1460/+0x146C)
   都是掛載時定好的常數;kind3 只有 `C063F140` 在用;不碰 FAT、bitmap、kind1/kind2、合併緩衝。[C]
   ⇒ 寫入 task 可以不拿 FS 鎖,直接呼叫 `C01EB790(*vol, LBA, 0, sectors, arena)`(更乾淨)或 `C0646C60`。
2. **驅動層自己會互斥,不會壞表。** 所有媒體 I/O(讀寫、SD/SSD/其他)都經 `C01EFBE0`/`C01EFAC8`,
   先拿**全域裝置號誌 `[0xC31F79E4]`**(tk_wai_sem、FIFO、無限等、無優先權繼承),整個 DMA 期間持有。
   提交端在寫入 task DMA 時發的任何 I/O(目錄擴充、LRU 換出、音訊)= **阻塞到 DMA 完**,不回錯、不碰 ADMA 表。[C]
3. **驅動的 arena 全機只有一個**(SD:ADMA2 表 0x43818EC8;SSD:0xC42F77D8),而且原廠讓 vol **整段錄影都握著它**
   (送出後立刻放、立刻取回)。取不到時 acquire 回 0、不等待 ⇒ 原廠的聚合會**永久降級**成逐段同步直寫。[C]
   ⇒「兩塊輪替」必須用我們自己的清單,在寫入 task 送出前一刻才把 {ptr,len} 填進驅動 arena。可行:arena 的
   add 只是位址轉換 + 填描述子(SD 另把 ≤3 B 的不對齊頭複製進 bounce)。[C]
4. **vol+0x4834..0x4848 是 RAM 裡的函式指標**(掛載時由驅動填、`C063F220` 填 +0x4834)。把這六個換成我們的,
   `C063F048` 與 `C063F380` 的攢塊邏輯**一行都不用改**,只剩 `C063F140` 要 hook。[C]
5. 一定要一起改的語意只有一個:`C063F380` 尾端「`+0x4A58==0` ⇒ 立刻回呼 cookie(status 0)」——非同步後那一幀的
   資料可能還在剛交出去的塊裡。這個回呼走 `vol+0x4834`,所以換指標就能接住。[C]
6. 停錄:`C0398D88` 每收到一個幀事件就重查一次(`cDevt_stop` 被 `C038C058` 反覆呼叫),第 2 態呼叫
   `C03A5190(mgr,0)` → `C063B950`(FS 鎖)→ `C063F310(vol,0)`。原廠語意 =「這個呼叫返回時,所有在途幀都已寫完並回呼」。
   **建議在 `C063F310` 路徑同步排空寫入 task**(其他路徑非同步)。[C 流程 / I 建議]

## 1. `C063F140(vol)` 逐行 [C](Thumb,0xC063F140–0xC063F21A)

```
C063F14C  if (vol+0x484C == 0) return;                       // 沒有 arena:什麼都不做(不回呼、不再取)
C063F154  status = 0;
C063F15A  if (vol+0x4A54 != 0 && vol+0x4A58 != 0)
C063F196      status = C0646C60(vol, 3, vol+0x3D0, 3,          // kind3、mode 3(直寫)
                                vol+0x4A54 /*起始 cluster*/, 0 /*byte 偏移*/,
                                vol+0x4A58 /*長度 bytes*/, vol+0x484C /*arena 當 buffer*/);
C063F19E      (status<0 只有一個 nop,沒有任何錯誤處理)
C063F1A8  cb = vol+0x4834;                                      // = C03A55D0(C063F220 從 0xC0B9E5D8 表填)
C063F1AC  if (cb) for (i=0; i < vol+0x4850; i++) cb(vol+0x4854[i], status);   // 同一個 status 給每幀
C063F1D6  (vol+0x4848)();                                       // 放 arena
C063F1E0  vol+0x484C = (vol+0x4838)();                          // 立刻再取(可能回 0 ⇒ 之後永久降級)
C063F1F6  vol+0x4850 = 0; vol+0x4A54 = 0; vol+0x4A58 = 0;
```

| 欄位 | C063F140 | 意義 |
|---|---|---|
| +0x4828 | 不讀 | 門檻(C063F220 依 cluster 對齊;非 0 = 聚合開) |
| +0x482C / +0x4830 | 不讀 | 補齊用零緩衝 / 每次補齊上限 0x40000(C063F048 用) |
| +0x4834 | 讀(回呼) | cookie 回呼 |
| +0x4838 / +0x4848 | 呼叫 | arena acquire / release |
| +0x483C / +0x4840 / +0x4844 | 不碰 | arena add / checkpoint / rollback(只有 C063F048 用) |
| +0x484C | 讀、寫 | arena 指標 |
| +0x4850、+0x4854[0x80] | 讀、清 | cookie 數與陣列(0x4854+0x80×4 = 0x4A54) |
| +0x4A54 / +0x4A58 | 讀、清 | 起始 cluster / 累積 bytes(含 cluster 補齊) |
| +0x3D0 | 傳入 | kind3 cache 物件 |

- 回傳 void。`C0646C60` 回 0 = 成功、負值 = 失敗(lossless-sup IMPLEMENTATION 已驗)。
- `4A54==0 或 4A58==0` ⇒ 不寫,cookie 一律 status 0。`C063F310(vol, 非0)` 就是先清 4A54 讓批次被丟棄。
- 錯誤路徑:不呼叫 `C0646F00`、不停聚合;錯誤只經 status 傳給該批每一幀。
- 呼叫點(全部):`C063F348`(C063F310)、`C063F682`(不連續)、`C063F6A8`(add 失敗)、`C063F6F2`(到門檻)、
  `C063F82C`(cookie 滿 0x80)、`C063F9B2`(C063F898 一般寫入)。[C,decomp 全域 grep]

### 1.1 回呼表(掛載 `C0644E30` 從 `C01EB8E0` → `C01F03E0`(拿裝置號誌)取得)[C]

| vol 欄位 | 角色 | SD(`C065F280` 填) | SSD(`C06703D8` 填) |
|---|---|---|---|
| +0x4838 | acquire | `C065F021` | `C06702B9` |
| +0x483C | add(addr,len) | `C065F061` | `C0670339` |
| +0x4840 | checkpoint | `C065EFE1` | `C0670249` |
| +0x4844 | rollback | `C065F001` | `C0670281` |
| +0x4848 | release | `C065F269` | `C06703C1` |

驅動不支援時用 `C0644E00/08/19/21/29` 的空殼。

## 2. `C0646C60` / `C0646580`(kind3、mode 3/5)[C]

`C0646C60(vol,kind,cache,mode,cl,off,len,buf)`:cl≥2 ⇒ `LBA = (cl-2)×[vol+0x146C] + [vol+0x1458]`,
再 `+ off/[vol+0x1460]`,呼叫 `C0646580(vol,kind,cache,mode,LBA64,off%ss,len,buf)`。cl<2(FAT12/16 根目錄)用 +0x1470/+0x1448。

`C0646580` 依序:
1. **cache 維護**:`buf ≥ 0xC0000000`(cached)才做;寫:len≤0x1000 `C000EB90` 否則全清 `C000E9B8`。
   SD arena = 0x43818EC8、SSD arena = **0x442F77D8**(uncached 別名)⇒ 不做。[C]
2. mode 2..5:`C0646050(vol,kind,cache,1)` 寫出並作廢同 kind 的 dirty。mode 4/5 要求 off==0 且 len 為 sector 倍數,否則 -3。
3. mode≥2 ⇒ 視為單 sector 窗(local_64=2)。整 sector 的部分**一次** `C01EB790(*vol, LBA, hi, sectors, buf)`;
   回傳 ≠1 就原樣傳回(失敗)。
4. 不對齊的頭/尾(只有 len 不是 sector 倍數時)走 `C0646248` 經該 kind 的 cache 讀改寫。

### 2.1 觸碰清單

| 步驟 | 動到什麼 | 共享? | 鎖 |
|---|---|---|---|
| C0646C60 算 LBA | 讀 vol+0x1458/+0x1460/+0x146C | 掛載常數 | **可鎖外** |
| cache 維護 | 只對 cached buf;arena 都是 uncached | 無 | 可鎖外 |
| `C0646050(kind3,1)` | kind3 唯一一格的 {LBA,年齡=1000,state=0} 重設;尾端 `C0645BD0(vol,3)` 因 kind≠2 直接回 1 | kind3 只有 C063F140 用;`C0646F00`(錯誤丟棄)也只是寫同樣的重設值 | 實務上可鎖外 [C];改直接呼叫 `C01EB790` 就完全不碰 |
| `C01EB790` 以下 | 裝置 I/O | 由裝置號誌保護(§3) | **可鎖外** |
| `C0646248` 頭尾 | kind3 cache 緩衝 | 批次長度恆為 cluster 倍數 ⇒ 不會走到 | — |
| **mode 5(kind4,cVar5==1 路徑)** | `C0646050(kind4=file+0x5C8,1)`:寫出並作廢**該檔**的 dirty cache,可能經 `C0645D80` 發 I/O | 檔案 handle | **必須鎖內** |
| mode 1(kind4 直寫退路,cVar5==2) | kind4 cache LRU、讀改寫 | 檔案 handle | **必須鎖內** |

**必須在 FS 鎖內**(都在提交端,`C063F380` 內):`C064B730` 預留、`C063D870`/`C064A040` 配 cluster
(free-extent 表、kind1 bitmap/FAT)、file+0x250/0x264/0x268、vol+0x4A54/0x4A58/0x4850/0x4854[] 的更新、
`C063F048`(呼叫 add 回呼)、kind4 路徑、`C0646050` 對 kind1/kind2、合併緩衝(全域 `0xC2F2E648..65C`,無自己的鎖)。
**可在鎖外**:把一塊的 {ptr,len} 填進驅動 arena(C065F060/C0670338)、`C01EB790`、`C03A55D0` 回呼(§6.3)。

## 3. 裝置層互斥 [C]

### 3.1 鎖的層次(由外到內,所有路徑順序一致)

| 鎖 | 物件 | 取得 / 釋放 | 種類 | 誰拿 |
|---|---|---|---|---|
| FS 全域 | `[0xC37D0644]` | `C01F8E8C`(svc 0x19 tk_wai_sem, TMO_FEVR)/ `C01F8CDC`(0x18 tk_sig_sem) | 號誌 {TA_TFIFO, 1, 1}(`C063AF98` 建立)| C063B898/B908/B950/B180/B3D0… |
| **裝置全域** | `[0xC31F79E4]` | `C01F0B98` / `C01F0BC0`(同上兩個 stub) | 號誌 {0, 1, 1}(`C01F0B50` 建立) | `C01EFBE0`(寫)、`C01EFAC8`(讀)、`C01EFD48`、`C01F0460/04B0`、`C01F03E0` 等 12 處 |
| SD 驅動 | `[0xC2F2E790]` "SDePower" | `C0016B54`(0x1D tk_loc_mtx)/ `C0016BE4`(0x1E tk_unl_mtx),在 `C0663A40/C0663A90` | **互斥鎖 TA_INHERIT**(atr 0x42) | `C065DB70` |
| SSD 驅動 | `[0xC3821468]` | `C01F8E8C`/`C01F8CDC` | 號誌(建立參數 0xC2F2EA30 在 BSS,靜態看不到)| `C06710D8`、`C0671170` 等 |

寫入鏈:`C01EB790` → `C01EB5B0`(0xE→SD、0x11→SSD)→ `C01EA2B8`(分割區換算、遞迴)→ **`C01EFBE0`:拿裝置號誌** →
SD `C065DB70`(拿 SDePower)→ `C065DC40` → UHS-II `C0663268`(…`C065FCE8` tk_wai_flg 等中斷)/ UHS-I `C065E300`;
SSD `C01F0FD0` → `C01F47E0` → `C06710D8`(拿 0xC3821468)→ `C0671BF0`。**整個傳輸是同步的,裝置號誌持有到 DMA 完成。**

### 3.2 寫入 task DMA 期間,提交端對同一裝置再發 I/O

- 結果:**在 `C01EFBE0`/`C01EFAC8` 的 tk_wai_sem 上阻塞**,FIFO 排隊,DMA 結束後接著做。不回錯。[C]
- 不會破壞 ADMA 表:一般 I/O 用另一張表 `0x43816EC0`(+bounce `0x4381AEC8`,`C065F388`),arena 用 `0x43818EC8`
  (+bounce `0x4381AECC`)。共用的只有 DMA 狀態 `[0xC3816EA4]`(1 閒置、2/3 一般寫/讀、4 arena),
  由 `C065F658`(準備)/`C065F750`(結束)切換,狀態 ≠1 時回 -66(0xFFFFFFBE)—— 但它只在裝置號誌 + SDePower 內被呼叫,
  所以兩筆不會重疊。[C]
- 跨裝置也會互等:裝置號誌是全域的,寫 SSD 時連 SD 的讀都要等。[C]
- **優先權反轉風險**:裝置號誌與 FS 號誌都**沒有優先權繼承**。提交端(SRecFile pri 6,握 FS 鎖)等寫入 task 放裝置號誌;
  若寫入 task 優先權低(例如 28),DMA 完成後它要等 9..25 的 task 讓出 CPU 才能放號誌 —— 就是 2026-08 那次凍結的形狀。
  ⇒ **寫入 task 優先權數字必須 ≤ 6**。[C 鎖種類 / I 後果]
- 鎖順序:FS → 裝置 → 驅動。寫入 task 只拿裝置(經 C01EB790),**絕不在持有裝置號誌時拿 FS 鎖** ⇒ 無循環。[C]

### 3.3 SD `C065F020`(acquire)拿不到表

```
C065F02A  關中斷(C000EC14)
C065F030  if ([0xC3816E80] != 0) { 開中斷; return 0; }       // 不等待、不回錯碼,只回 NULL
C065F03E  [E80]=1; 開中斷; [E88]=[E94]=[E9C]=0; checkpoint; return [0xC3816E84] (=0x43818EC8)
```
SSD `C06702B8` 同型:busy `[0xC42F77D4]`,成功回 `0x442F77D8`,失敗回 0。release(`C065F268`/`C06703C0`)只清 busy,不檢查。

FS 的反應:`C063F140`/`C063F220` 把 0 存進 +0x484C ⇒ `C063F380` 走 cVar5=2(逐段經 kind4 同步直寫),
cookie 走「4A58==0 立刻回呼」;**聚合路徑永遠不會再呼叫 acquire**(只有 C063F140 在 484C≠0 時才再取),
所以整段錄影都降級。`C063F380` cVar5==1 路徑與 `C0646D38`(`C06429A0` 填 0x00/0xFF,格式化類)拿不到就退回一般 I/O。[C]

## 4. arena 生命週期與格式

### 4.1 生命週期 [C]
- 錄影開始 `C063F220`(經 `XC_MediaFileSdCard::v17` → `C063B908` FS 鎖):設 +0x4828..+0x4834,**acquire 一次**。
- 每次 `C063F140`:送出 → release → 立刻 acquire。⇒ 整段錄影 vol 一直握著驅動 arena,別人(同裝置其他檔案、`C0646D38`)拿不到。
- 停 `C063F310`:`C063F140` 後若 484C≠0 再 release 一次,清 +0x4828/+0x484C。

### 4.2 `C063F048`(把一個 extent 加進 arena)[C]
參數是 `C063F380` 堆疊上的結構(`&local_50`):`[0]=vol, [1..3]=段落迭代器{清單指標, 目前位址, 目前剩餘}, [4]=補齊緩衝(+0x482C),
[5]=每次補齊上限(+0x4830), [6]=cluster bytes, [7]=起始 cluster, [9]=本 extent bytes, [0xB]=補齊後 bytes(輸出)`。
```
save 迭代器; (vol+0x4840)()                         // checkpoint
do { C063F000 取下一片 = min(extent 剩餘, 該段剩餘); if ((vol+0x483C)(addr,len) < 0) goto fail; } while (剩餘)
[0xB] = 向上取整到 cluster;補齊部分以 (vol+0x483C)(pad_buf, min(剩, 0x40000)) 重複加入,失敗 goto fail
return 0
fail: 還原迭代器; (vol+0x4844)(); return -1         // rollback 整個 extent
```
`C063F048` 本身不定義格式,只呼叫 add(addr,len)。格式在驅動:

### 4.3 SD add `C065F060(addr,len)` —— ADMA2 描述子,每筆 8 B [C]
- 前提 busy=1;len=0 直接回 0。位址轉實體:`≥0xC0000000 → −0xC0000000`、`0x40000000..0xBFFFFFFF → −0x40000000`。
- `[0xC3816E9C] += len`(總 bytes)。
- 不對齊頭(`-addr & 3`):最多 3 B **在 add 當下複製**到 `0x4381AECC + [E94]×4`(上限 0x100 格),加一筆描述子指向它。
- 其餘每筆最多 `[0xC2F2E750]`(host 版本 ≥4 為 0x4000000,否則 0x10000;`C065F360`)。
- word0:bit0 Valid=1、bit1 End=0、bit2 Int=0、bit5..3 Act=0b100(Tran,0x20)、bit15..6 = len[25:16]、bit31..16 = len[15:0]
  (切滿上限時長度欄寫 0 = 最大值);word1 = 實體位址。表 `0x43818EC8`,上限 0x400 筆(`[E88]`)。
- checkpoint `C065EFE0`:E88→E8C、E94→E98、E9C→EA0;rollback `C065F000` 反向還原。
- 送出時 `C065F658`:buf 必須 == `[0xC3816E84]`、len 必須 == `[E9C]` 且是 512 倍數、E88≠0;
  把最後一筆 `|= End`,狀態 EA4=4,回傳表的實體位址。

### 4.4 SSD add `C0670338(addr,len)` —— 每筆 8 B {實體位址, 長度},不切 [C]
- 表 `0xC42F77D8`(acquire 回 uncached 別名 0x442F77D8),上限 0x400 筆;筆數 `[0xC42F97D8]`、總 bytes `[0xC42F97E0]`;
  checkpoint `C0670248` → `[97DC]/[97E4]`,rollback `C0670280` 還原。
- 傳輸時 `C0670690` 以游標 `[97E8 索引, 97F0 位址, 97F4 剩餘, 9800 已用]` 每次取 ≤0x10000(xHCI TRB);`C0670450/C06704A8` 存/還原游標。
- 驅動以 `C0670420(buf == 0x442F77D8)` 認出 arena。

### 4.5 「兩塊輪替」可行性
- 可以在寫入 task 送出前一刻才 acquire → 逐筆 add → 送 → release:add 不讀資料(SD 例外:≤3 B 頭在 add 時複製,
  那時幀已完整、直到 cookie 回呼才會釋放,所以安全)。[C]
- 限制:每次送出 ≤0x400 筆(SD 還要 ≤0x100 個頭)。SD 每片筆數 = (addr&3?1:0) + ceil(剩餘/[0xC2F2E750])。
  64 KiB 描述子時一個 64 MiB 塊就要 ≥1024 筆 —— 原廠在這裡就會「arena 用盡」提早送出。
  ⇒ 寫入 task 把一塊切成數次送出,**切點只能在一次 `C063F048` 的結尾**(那裡一定是 cluster 邊界,LBA 連續、長度是 512 倍數)。
  我們的 checkpoint 回呼(+0x4840)剛好標出每個 `C063F048` 的開頭。[C]
- 幀段位址必須是 uncached 別名:`C063F380` 對 `≥0xC0000000` 的段直接回 -3;補齊緩衝 `C063F220` 也檢查。⇒ 寫入 task 不需做 D-cache 維護。[C]

## 5. `C063F380` 攢塊對 arena 的依賴,與要一起改的分支

| # | 位置 | 原廠行為 | 換成我們的清單後 |
|---|---|---|---|
| a | `C063F048` 全部 | 只經 vol+0x483C/0x4840/0x4844 | **不改碼**;換指標。我們的 add **永不失敗**(清單開大,驅動上限在送出時切) |
| b | `C063F686–F692` | `484C==0` ⇒ cVar5=2 直寫 | 我們的 acquire **永不回 0**(沒空塊就等寫入 task 放),否則整段降級 |
| c | `C063F650–F682` | 不連續 ⇒ C063F140 | 不改(C063F140 已 hook) |
| d | `C063F6A0–F6AC` | add 失敗 ⇒ cVar5=2 + C063F140 + 本 extent 同步直寫 | 依 (a) 不會發生;若發生仍正確(直寫是同步的,cookie 走 g) |
| e | `C063F6E4–F6F2` | `4A58 ≥ 4828` ⇒ C063F140 | 不改;塊大小 = 改寫 vol+0x4828(需 cluster 對齊) |
| f | `C063F81E–F82C` | cookie 數 == 0x80 ⇒ C063F140(在加入本幀前檢查) | 不改;我們的塊至少存 0x80 個 cookie |
| **g** | **`C063F830–F886`** | **`4A58==0` ⇒ `(vol+0x4834)(frame,0)` 立刻回呼** | **語意必改**:本幀最後一片可能在剛交出去的塊裡。把 +0x4834 換成「掛到最後一個尚未完成的塊;沒有就直接呼叫 C03A55D0」。寫入 task FIFO 完成 ⇒ 掛最後一塊就涵蓋該幀所有較早的片 |
| h | `C063F6F8–F768`(cVar5==1,聚合關) | 直接 +0x4838 → C063F048 → `C0646C60(kind4,mode5,arena)` → +0x4848 | 會把 arena 指標當 buffer 傳給驅動 ⇒ **只要 +0x4828==0 就必須是原廠指標**:在 C063F220 之後才裝、在 C063F310 排空時還原 |
| i | `C063F9AE–F9B2`(C063F898) | 一般寫入前先送出未滿批次 | 非同步交出即可;之後它的同步寫會在裝置號誌上等 DMA(原廠也是同步等) |
| j | `C063F34C–F35E`(C063F310) | C063F140 後 `484C≠0` 就 release | 我們排空後先還原指標並把 484C 清 0,讓它跳過 release |
| k | `C063F220` | 設門檻、+0x4834、acquire 一次 | 原函式跑完後:用原廠 +0x4848 放掉驅動 arena、存原指標、裝我們的六個、484C=我們的塊、必要時改 +0x4828 |

另外兩個要知道的:
- `C063F380` 在聚合開時要求檔案位置 cluster 對齊(`C01F84A4(pos, cluster)`,否則 -3);每個 extent 都補到 cluster ⇒ 下一幀自然對齊。[C]
- 一幀跨兩塊時 cookie 只在後一塊,status 也只反映後一塊(原廠如此)。要更嚴可以在寫入 task 把較早塊的失敗 OR 進去。[C/I]

## 6. 停錄

### 6.1 流程 [C]
```
C038C058(幀事件處理)/ 其他 → cDevt_stop(C038C3C0) → C0398D88(1, take)
  C0376300(mgr, take) 掃 96 格描述子(+0x1100==take 或 take==-1):
     有 state ∉ {0,0xB,0xC,0xD}  → 0    (上游還在處理)
     有 0xB                       → 1    (等 SRecFile 寫)
     有 0xC 或 0xD、沒有 0xB      → 2    (已交給 FS、等完成/回收)
     全空                         → 3
  0/1 → log 0x10110331/2,return 0
  2   → log 0x10110333,C03A5190(mgr,0),return 0
  3   → C03A5190(mgr,1)(失敗 → 錯誤收尾),之後 ImageSave、C0444698(…,0)、媒體 v6 把 vol+0x481C 設回 1(flush kind1/2)…
  return 0 ⇒ cDevt_stop 設 +0x20=1,等下一個事件再查
C03A5190(mgr, p): if mgr+0xC { if mgr+0xD { XC_MediaFile(mgr+0x10) → vtable+0x50 (XC_MediaFileSdCard::v18)
                                → C063B950:拿 FS 鎖 → C063F310(vol, 0) → 放鎖 }
                               if p { mgr+0xC=0; mgr+0x10=0; C03A5998 } }
C063F310(vol, 0): 4828==0 → -3;否則 C063F140(送出最後一批,同步、回呼)→ 484C≠0 則 release → 清 4828、484C
```
- 狀態:0xC 在 `C03A5348` 交給 FS 前設(聚合開時,`C03A52D0(…,3,0)`);0xD 在 `C03A55D0` 設(`C03A52D0(…,4,err)`)。
  0xB 是「等 SRecFile 寫」[I,依 C0398D88 的處理推定]。
- 第一次走 2 之後 4828 已清,後續事件再走 2 時 `C063F310` 回 -3、v18 只記 log(原廠本來就會,0xD 也算 2)。

### 6.2 非同步後怎麼維持語意
- 原廠語意:**`C03A5190(mgr,0)` 返回時,這段所有在途幀都已寫完並呼叫過 `C03A55D0`。** 之後的 3 態才把中繼資料 flush(481C=1)。
- 建議:在 hook 的 `C063F140` 裡以返回位址辨認 `C063F310` 呼叫(LR == 0xC063F34D),那一次:交出最後一塊 →
  **等寫入 task 排空(佇列空、全部 cookie 已回呼),有逾時** → 還原 vol+0x4834..0x4848 原廠指標 → 484C=0。
  其他五個呼叫點都非同步。[I]
- 為什麼可以在 FS 鎖內等:寫入 task 的送出不拿 FS 鎖;`C03A55D0` 不拿 FS 鎖(原廠在 FS 鎖內呼叫它,號誌不可重入,若它要 FS 鎖原廠早就死結)。[C 推得]
- 只靠事件驅動(不等)理論上也會收斂,但 `C038C058` 是在呼叫 cDevt_stop **之後**才回收目前那一幀(0xD 仍算 2),
  最後一幀之後是否還有事件把它推到 3,靜態看不清楚 [I];同步排空沒有這個疑慮。
- `C063F310(vol, 非0)`:4A54 被清 ⇒ 目前這塊不寫、cookie 給 0;仍要先等較早的塊(FIFO)。

### 6.3 `C03A55D0` 能不能在寫入 task、鎖外呼叫
- 原廠就在**鎖外**呼叫它:`C03A5348` 聚合關時(`C069ADE0` 返回後、`C063B898` 已放鎖)。[C]
- 原廠就在**兩個 task** 呼叫它:SRecFile(C063F380 內)與停錄處理 task(C0398D88 → C063F310)。[C]
- 它做的事:log、`frame+0x1104=0xD`、`C03A52D0(mgr, id, 4, err)` 通知兩個 listener(`C03A5248` 註冊)。listener 內容沒追 [I]。
- 結論:可在寫入 task 鎖外呼叫。保守做法是**先把塊標成空閒、再逐一回呼**(提交端等空塊時不必等回呼)。

## 7. 結論:寫入 task 送出一塊的最小安全序列

### 7.1 提交端(原廠 task,已在 FS 鎖內;hook `C063F140` 入口)
```
1. if vol+0x484C == 0: return                                  // 原廠語意
2. 封塊:起始 cl = +0x4A54、bytes = +0x4A58、cookies = +0x4854[0..+0x4850)、我們的片清單與「C063F048 邊界」
   (4A54==0 或 4A58==0 ⇒ 標「不寫,status 0」)
3. 塊放進 FIFO,通知寫入 task
4. 取下一個空塊(沒有就等 —— 寫入 task 不需要 FS 鎖,不會死結);+0x484C = 塊;清 +0x4850/+0x4A54/+0x4A58
5. 若 LR == 0xC063F34D(來自 C063F310):等排空(逾時)→ 還原六個原廠指標 → +0x484C = 0
```
### 7.2 寫入 task(不拿 FS 鎖;優先權 ≤ 6)
```
1. 取一塊
2. 依 C063F048 邊界切成若干段,每段 ≤0x400 筆(SD 另 ≤0x100 頭;筆數依 [0xC2F2E750])
   每段:
   a. arena = 原廠 acquire(C065F021 / C06702B9);回 0 ⇒ tk_dly_tsk 後重試(只有 C0646D38/他檔在用時)
   b. 逐片 原廠 add(addr,len)(C065F061 / C0670339);<0 ⇒ 塊失敗
   c. r = C01EB790(*vol, LBA, 0, bytes/[vol+0x1460], arena)          // 1 = 成功
        LBA = (cl−2)×[vol+0x146C] + [vol+0x1458] + 已送 sectors
      (或 C0646C60(vol,3,vol+0x3D0,3,cl',0,bytes,arena),0 = 成功)
   d. 原廠 release(C065F269 / C06703C1)
3. status = 全部成功 ? 0 : 負值
4. 塊標成空閒(喚醒等塊的提交端)
5. for cookie: C03A55D0(cookie, status)        // ARM,鎖外
6. 完成計數 +1(給 §7.1 第 5 步)
```
哪些步驟拿什麼鎖:提交端 1–5 都在原廠的 FS 鎖內(本來就握著);寫入 task **不拿 FS 鎖**,只在 2c 經 `C01EFBE0` 自動拿裝置號誌
(與驅動鎖)。arena 的 acquire/add/release 不需要任何鎖(關中斷 TAS)。

### 7.3 Hook 點

| 點 | 位址 / 原廠字 | 作法 |
|---|---|---|
| **`C063F140` 入口**(必要) | 0xC063F140:`2D E9 F0 45`(push.w {r4-r8,sl,lr})、`84 B0`(sub sp,#0x10)、`04 46`(mov r4,r0) | 8 B 換成 `DF F8 00 F0` + 位址(ldr.w pc,[pc];0xC063F144 已 4 對齊)。前 8 B 無 PC 相對指令。整個函式由我們實作 |
| `C063F220` 之後(必要) | 入口 0xC063F220:`2D E9 F0 41`(push.w {r4-r8,lr})、`07 46`、`0D 46`;或在 WRITER_SPEC §5.8 已計畫的 C03A50F8 之後 | 原函式成功後:原 +0x4848 放掉驅動 arena、存並換 vol+0x4834..0x4848、484C=我們的塊、門檻寫 +0x4828 |
| vol 欄位(資料,不是碼) | SD vol = 0xC37D50D4:+0x4834/+0x4838/+0x483C/+0x4840/+0x4844/+0x4848/+0x484C/+0x4828 | 只在 4828≠0 期間換;停錄還原 |
| `C063F310` | 不另 hook;用 C063F140 的 LR(0xC063F34D)辨認 | 同步排空 |

- 所有碼 hook 走 loader v3 claim + journal,寫完做 I-cache 維護;不和 LOSS(`C03A5490`、`C038BFF0`)、STOPFX(`C0377118`)、
  gyro2(`C038C77C`)重疊。
- 不要 hook `C063F048`/`C063F380`:它們全靠 vol 指標,換指標就夠。

## 8. 未解 / 要驗

- SSD 號誌 0xC3821468 的建立參數(0xC2F2EA30 在 BSS)。
- `C03A52D0` 兩個 listener 的內容(是否只送訊息、能否被兩個 task 同時呼叫)。
- 停錄只靠事件會不會收斂(§6.2),上機前先用 unicorn 跑 C0398D88/C0376300 的狀態序列。
- `[0xC2F2E750]` 在 HD312 上的實值(決定 64 MiB 塊要切幾段)。
- 寫入 task 優先權 ≤6 時對 SRecFile(6)/音訊的影響(I7):寫入 task 大部分時間在 tk_wai_flg 裡,CPU 只花在填表與回呼。
