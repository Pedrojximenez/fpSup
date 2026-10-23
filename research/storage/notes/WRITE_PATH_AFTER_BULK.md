# CinemaDNG 寫入路徑:64 MiB 批次送出之後(SD / SSD)

2026-10-14。靜態分析(`out/MAIN_c0000000.bin`、`out/decomp/full/blk_c03.c`、`blk_c06.c`)
加上現有 rec log 的時間分析。沒有上機。[C]=程式碼證實(附位址),[I]=推論,[L]=現有實機紀錄。

## 0. 一句話

**一個 volume 同時只有一批在寫;寫入是同步的,在提交幀的 task 裡做完,全程握著 FS 全域鎖。**
寫入期間不累積下一批,寫完才逐檔做開檔、配置 cluster、FAT、關檔。
所以積壓時批與批之間的空檔是「逐檔 CPU 成本沒有和 DMA 重疊」,不是在等資料。

## 1. 共同路徑(SD 與 SSD)[C]

```
C037E0B8(每幀處理,task 推論為 SRecFile)
 └ C03A5348 → C069ADE0:開檔 → 收 ≤8 段 {ptr,len} → C0366168 → … → C063B898
     C063B898:取 FS 全域鎖 [0xC37D0644](無限等)→ C063F380 → 放鎖 → C0366020 關檔
 C063F380:C064B730 預留 → C063D870 配一段連續 cluster(FAT 鏈此時就寫進 FAT cache)
   ├ 聚合開(settings+0x9C≠0):C063F048 把本段與 cluster 補齊加進 arena(vol+0x483C)
   │    累積 +0x4A58 ≥ 門檻 +0x4828 → C063F140 送出
   └ 聚合關:C063F048 建本幀描述子 → C0646C60(mode 5)同步寫完 → C03A5348 自己回呼 C03A55D0
 C063F140:C0646C60(vol,3,vol+0x3D0,3,起始 cluster +0x4A54,0,長度 +0x4A58,arena)
   → C0646580(先 writeback kind3 cache)→ C01EB790 → 裝置驅動(§2、§3)
   → 同步返回後,對每個 cookie(+0x4854[i], i<+0x4850)呼叫 C03A55D0(frame, 同一個 status)
   → 放 arena、立刻再取回(聚合保持開啟)
```

- **門檻**:常數表 `0xC0B9E5D8` = {0x04000000, pad_buf, 0x40000, C03A55D0};C063F220 向上對齊到
  `vol+0x146C × vol+0x1460`(推論為 cluster)存進 `+0x4828`;比較點在 C063F380。[C]
- **啟用**:`mgr+0xD = settings+0x9C`,只在 C03A50F8(C03A5050 錄影初始化)讀一次。[C]
  `settings+0x9C = (MediaSelect==0) ? 1 : (WriteMode==1)`(C00AB8E8,唯一寫入者)。
  ⇒ **SD 永遠聚合;SSD 只有 Custom 聚合,Standard 逐幀同步寫。** [C;0/1 對應的標籤為 I]
- **停用**:只在 C063F310(清 +0x4828/+0x484C),唯一路徑 C03A5190 ← cDevt_stop。[C]
- **提早送出**:cluster 不連續;arena 用盡(1024 筆或 256 個 head 小區,該段改直寫);
  cookie 滿 0x80(128 幀);**任何一般寫入 C063F898(音訊 WAV)會先送出未滿的批**;停止。[C]
  (gyro 已改為 FSG2 隨 CinemaDNG 一起寫入,不再有獨立的一般寫入。)
  開檔、關檔、配置 cluster 不會觸發送出。
- **一幀可跨兩批**,cookie 只記在後一批。[C]
- **cluster 補齊的零會真的寫進卡**,而且計入門檻。[C]
- 兩種模式都**不繞過 FS**、**不複製影像**(arena 只記 {實體位址, 長度})。[C]

## 2. SD [C]

- 整批是**一條** ADMA2 描述子表(全機一張 `0x43818EC8`,8 B/筆,最多 0x400 筆;忙碌旗標
  `0xC3816E80` 關中斷 test-and-set)。
- UHS-II:C0663268 → **一個 DCMD**(TLEN = 整批 sector 數),C0660D60 寫暫存器,
  C065FCE8 `tk_wai_flg` 等中斷(逾時 30000)。錯誤重試 3 次後改走 UHS-I。
- UHS-I:C065E300 → … → **一個 CMD25**(Auto-CMD23 C0669200)。
- 每筆描述子上限 `[0xC2F2E750]`(C065F360):host 版本 ≥4 時 64 MiB(26-bit 長度),否則 64 KiB。
  **HD312 走哪一種未驗。**
- **queue depth = 1**:一張表 + FS 鎖 + 同步呼叫。

## 3. SSD(USB MSC)[C]

- C0646C60 → C01EB790 → C01EFBE0(裝置 0x11)→ C01F0FD0 → C01F47E0 → C06710D8(SSD 鎖 0xC3821468)
  → **C0671BF0 依 `0xC382144C` 切成多條 SCSI WRITE**:
  - BOT、512 B sector:上限 0xFFFF sector,所以 64 MiB = 65535 + 65535 + **2 sector**(每批多一條 1 KiB 尾巴)。
  - UAS、4 streams:8 條 × 8 MiB;只有指令長度「鎖定」(`0xC382145C`)後才走管線 C0672398(≤4 條在途),
    **每批結尾 C0672650 把在途指令全部等完**。
- **65536** = xHCI Normal TRB 長度上限:C0670690 從 arena 游標(0xC42F97E8/97F0/97F4)每次取
  `min(該筆剩餘, TD 剩餘, 0x10000)`;C066FCA0 排 TRB(CH、最後一個 IOC),C0670228 doorbell。
  環空位不足時截斷,等 C066D890 完成事件再續排。
- **Standard 永遠不會進 UAS 管線**:每幀指令都小於當時的上限,C0670D00 只在「整條照上限送成功」時加倍,
  所以永遠不鎖定。[C 依邏輯推出]
- SSD 只有一個 arena(0xC42F77D8,使用中旗標 0xC42F77D4)⇒ 同時一批。

## 4. 實測時間(現有 rec log,205 份、4,066 筆)[L]

rec log 就是 CinemaDngFile.cpp 的 CSV(`request,finish,diff,gap,reqcnt,fincnt,diff,sdb,MB/s`),
**一列 = 一次批次送出**;gap = 本批 request − 上批 finish;sdb = 描述子池剩餘。
**205 份裡沒有任何兩批重疊。**

| 情境 | 每批 | 寫入 | 寫入中 MB/s | 空檔 | duty | 持續 MB/s |
|---|---|---|---|---|---|---|
| SD UHS-II,1008×672,119.88p,sdb 5 | 57 檔 59.5 MiB | 254 ms | 246 | 211 ms | 0.55 | ~135 |
| SD,同上 59.94p | 57 檔 | 255 ms | 245 | 684 ms(等資料) | 0.27 | 66 = 需求 |
| SSD 5 Gbps,240p,sdb 2–10 | 43 檔 44.9 MiB | 164 ms | 284 | 22 ms | 0.86 | ~250(需求 263) |
| SD UHS-II,UHD 8.4 MB | 8 檔 | 263 ms | 257 | 57 ms | 0.82 | ~212 |

- 每批檔數 = 依 cluster 取整後湊到 ≥64 MiB(SD 128 KiB cluster → 57 檔;SSD 512 KiB → 43 檔)。
- ⚠ **更正(2026-10-14 晚)**:下面這條對 SD 不成立 —— SD 情境的週期 = 57 幀 ÷ fps,沒有積壓,空檔是在等幀;錄影中 FS 不寫回中繼資料(EXFAT_PER_FILE_METADATA.md)。只有 SSD 240p 有輕微積壓。原文保留:
- **積壓時空檔仍在,且與批內檔數成正比**:SD gap ≈ 5.9 ms × 檔數 − 4.7(約 3.7–5.9 ms/檔),
  SSD 約 0.53 ms/檔。⇒ 逐檔固定成本(開檔/配置/FAT/關檔),寫入期間被同步寫入擋住,寫完才補做。[L+I]
- 低格率的 0.7–1.6 s 空檔只是在等攢滿,不是浪費。
- 來源:`projects/res-lab/validation/20261009-recording-formula/*-record.json`、
  `20261011-*/…/trial.json`、`20261012-m12-240-live/ssd-camera-return.json`、
  `projects/lossless-sup/validation/20261012-camera-lossless-stopfx/uhd30-autostop-01.json` 等。
- ⚠ 小批次(1–6 檔)的紀錄多半是改過 bulk 的實驗,log 標頭仍印 67108864,不能當原廠行為。
  lossless 的紀錄 file-size 是未壓縮大小,MB/s 偏高。

## 5. 更正

- `projects/lossless-sup/build/ledger-mediawritemode-gate-20260924.json` 的 vtable 偏移錯 4 bytes
  (正確 vptr `0xC07397D8`,不是 `…DC`)。「shell 寫的值 v3 讀不到」應撤回;
  當時「設 2 沒效果」是因為媒體是 SD,公式恆為 1。
- 「SD 最壞 692 ms = 64 MiB ÷ 97 MB/s」只是 UHS-I 下的推算;UHS-II 實測每批 254 ms。

## 6. 19456 / 65536 錯位(SSD)

- 19456 = 0x18000 − 0x13400,只有 DNG writer 這層知道這兩個數(C03A5348 → C03813D0,
  表頭 node 長度 = frame+0x14C)。實測位移是**逐檔固定**、不沿批累加 ⇒ 比較像在逐檔建 node 那層形成
  (含 res-lab 自己的 hook),不是 SSD 層。[I]
- SSD 層唯一的 64 KiB 單位候選:arena 游標全域、以 TRB 前進;BOT 重試有存還游標
  (C066CFC0/C066CFD0),UAS 管線 C0672398 沒有。[C 機制,是否觸發未證]

## 7. 未解

1. HD312 host 版本 ≥4?(每筆描述子 64 MiB 或 64 KiB;UHS-I 下 >0xFFFF block 能否通過)
2. 空檔裡媒體是在寫中繼資料還是閒著;SD 每檔成本為何是 SSD 的 ~8 倍。
3. FAT/目錄 cache 何時 writeback;kind0–3 cache 的語意。
4. C03A5348 的呼叫者 task 與優先權(推論 SRecFile)。
5. Write Mode Standard、BOT/UAS、UHS-I 都**沒有任何實測紀錄**。
6. 錄影中音訊一般寫入切短批次的實際頻率。
7. SSD exFAT cluster 大小、輔助區(補齊)內容是否為零。

## 8. 對重建的意義

- 硬體/驅動每個 volume 一次一個指令(SD)或一批(SSD),**要持續寫卡,只能把寫入移到專屬的
  寫入 task,並讓逐檔的 FS 工作與 DMA 重疊**:寫入 task 寫第 N 塊時,提交端照常為第 N+1 塊
  開檔、配置 cluster、填描述子。需要兩張描述子表(SD 的 ADMA 表、SSD 的 arena 各一張)與
  更短的 FS 鎖持有範圍。
- 逐塊歸還(每塊完成就回呼該塊的幀),不必等整批。
- 一般寫入(音訊 WAV)不應強迫送出影像批;應排進同一個寫入 task。gyro 已隨 CDNG 寫入,不必考慮。

## 9. 外部研究與最佳作法(2026-10-14 文獻查詢)

### 9.1 SD 的錄影專用模式(Video Speed Class)
- 速度等級的保證只適用於**寫進完全未使用的 AU(Free AU)、從 AU 開頭依序寫**;寫過一半的 AU 不能拿來錄影。
  VSC 把 AU 上限加大到 512 MB,AU 再切成 RU(recording unit),**從 RU 邊界開始、以 RU 倍數寫入**才有保證。
  主機用 CMD20(Speed Class Control)進入錄影模式,並以 CMD20 通知目錄更新等;另有 Suspend/Resume。
  (來源:SDA 速度等級頁、KIOXIA 專利 US 11,573,701;精確指令編碼在會員版 Part 1 規格,未取得。)
- **fp 韌體有完整的 VSC 配置器,只是原廠不開** [C](2026-10-14 更正:先前寫「找不到呼叫者」是錯的)。
  SD ioctl 0x198(C065DEA0 → C065E948 → C065E8E0,指令字 0x141B0000 = CMD20、R1b;
  卡的 SCR CMD_SUPPORT bit0 不支援就不送)。FS 層四個發 CMD20 的函式都有呼叫者:
  C064B610(開檔配置,mode 1)→ C0649DB8(0x18000000 包住目錄 sector 重寫)、
  C064A040 → C0649EA0(0x78000000 | AU 位址>>10)、C0649E70(0x08000000);
  C064BB48(關檔)→ C0649F18(0x88000000)。
  mode 1 來自建檔旗標 bit0 ← open mode > 0x13 ← `XC_MediaFileSdCard::open` flags `0x10000`(C0368344 mode×10)。
  **全韌體沒有人帶 0x10000**;DNG flush C069ADE0 用 0x806/0x1806。
  另需 `vol+0x1FF0 == 0`(C064AD18:AU 由 ioctl 0x109 讀 SD Status,與 cluster 對齊)。
  ⇒ 試驗模組 `fpSup/cmd20/`(06CMD20.BIN)把 DNG 開檔改成 0x10806,未上機。
- 速度等級的寫入 busy 不得超過 250 ms(Part 1 v3.01)。

### 9.2 快閃卡的 FTL 行為
- 卡同時能「開著」的 AU / 抹除區塊數很少(flashbench:`--open-au-nr` 往上加到效能掉下來為止;抹除區塊常見 4–8 MB)。
  資料流和 FAT/目錄/bitmap 寫在不同區域,每次切換都可能讓卡做搬移。
  ⇒ **[I] 這是 SD 每檔 4–6 ms、SSD 每檔 0.5 ms 的合理解釋**:SSD 的 FTL 有 DRAM 快取與大量開放區塊,
  小筆中繼資料寫入便宜得多。
- SD 6.0 的 Command Queue / Cache(A2)針對隨機讀寫,對連續錄影幫助有限;SD Express(NVMe)fp 硬體不支援。
- SSD 的 GC 會造成延遲尖峰,緩衝要能吸收(ACM CSUR 的 GC 綜述)。

### 9.3 exFAT
- 目錄項有「連續檔」位元(NoFatChain):整個檔連續時**完全不寫 FAT**,只動 cluster bitmap。
- 分開記錄「配置長度」與「有效資料長度」,可以先預配置再寫入,不會洩漏舊資料。
- 預配置可避免碎片;cluster 配置要走 bitmap,在快閃上成本不低(Linux exfat fallocate 修補討論)。

### 9.4 Magic Lantern 的實務經驗
- 專屬 writer、緩衝池、每次寫**接近 32 MiB 的連續區塊**;排程器挑最大的連續區塊送出;
  5D3 上兩個 writer 執行緒分別寫 CF 與 SD(雙卡分流)。

### 9.5 對重建寫入層的建議(依投報率)
1. **寫入與逐檔 FS 工作重疊**(§8):專屬寫入 task、兩張描述子表、FS 鎖只包發指令。
2. **中繼資料批次化**:一批幀一次在 bitmap 預配置一段**對齊 AU 的連續 cluster**,
   每個檔標成連續檔(不寫 FAT),目錄項整批寫一次,而不是每檔散寫 FAT/目錄/bitmap。
3. **SD 走 VSC 協定**:錄影開始 CMD20、寫入從 AU 開頭並以 RU 倍數對齊、目錄更新用 CMD20 包住
   (韌體已有現成配置器,但它是**每檔**一個 AU,對小 DNG 不合用,§9.1)。AU/RU 大小由卡的 SD Status 讀出,不寫死。
4. 塊大小以 AU(SD)或指令上限(SSD:BOT 32 MiB、UAS 8 MiB×4)決定,不是固定 64 MiB;每塊完成即歸還。
5. 音訊 WAV 併進同一個寫入 task,不再強迫送出影像批。

### 9.6 要上機補的量測
- 錄影時 C065E8E0(CMD20)有沒有被呼叫(原廠預期不會;裝 06CMD20 後應該會)。
- 卡的 AU 大小與是否支援 VSC(SD Status)。
- SD 每檔 4–6 ms 的拆解:FAT、目錄、bitmap 各寫幾次、寫在哪裡。

來源:sdcard.org 速度等級頁;KIOXIA 專利 US 11,573,701(Justia);Arnd Bergmann flashbench README;
bahjeez microSD 調查;ACM CSUR《Garbage Collection Techniques in SSDs》(doi 10.1145/3816041);
Wikipedia exFAT;Linux exfat FALLOC_FL_ZERO_RANGE 修補討論(2026-03);Magic Lantern 論壇 mlv_rec 討論串;
SDA SD Express 白皮書。

## 10. 其他 SIGMA 機種(2026-10-14)

- **fp L Ver.3.02**:寫入路徑逐函式比對,只差重定位常數;64 MiB 門檻、同步送出、VSC 配置器同樣沒被打開,全部與 fp 5.02 相同。見 `sigma_fpl/README.md`。
- **BF Ver.1.04**:容器已解,內容是串流加密(各區段金鑰流相同),未解密;且沒有記憶卡槽。見 `sigma_bf/README.md`。
- ⇒ SIGMA 沒有在後續機種中改寫這一層,重建只能靠自己設計(§9.5)。

## 11. 依最新研究的優化方案(2026-10-14)

### 11.1 文獻的共同結論(可移植到 fp)
- **對齊抹除單位的純連續寫入,讓裝置不必做 GC**:Zoned UFS(FAST '26,SK hynix/Google)把 zone 對齊 NAND
  抹除區塊,碎片化下寫入吞吐仍 >2×,延遲更可預測。SD 的對應物就是 Video Speed Class 的 Free AU/RU 規則(§9.1)。
- **裝置能同時開著的寫入流很少**:同一篇的 UFS 只給 Zoned LU 兩個 768 KB 寫入緩衝(最多兩個 zone 同時寫);
  F2FS 把「需要隨機更新的中繼資料」放進獨立的小區域,資料走連續流。⇒ 中繼資料要少、要集中、要批次。
- **小筆寫入要合併**(SpanDB FAST '21、MedFS FAST '25 的共同主題)。
- **從頭到尾保持寫入順序**(Zoned UFS:電源管理、requeue 都可能偷偷打亂)。
- 緩衝:雙緩衝會讓兩端互等,三緩衝/池才能吸收抖動;整條管線保持在 DMA 緩衝內、避免 CPU 複製。

### 11.2 套到 fp 的方案與預期收益(依投報率)

| # | 改法 | 依據 | 預期 |
|---|---|---|---|
| 1 | 專屬寫入 task,寫入與逐檔 FS 工作重疊(兩張描述子表) | §4 實測:積壓時空檔 = 逐檔成本 | SD UHS-II 120p:每批 FS 工作 211 ms < 寫入 254 ms,可完全藏住,duty 0.55 → 接近 1,持續約 135 → ~240 MB/s [I];SSD 240p:0.86 → ~1,250 → ~284 MB/s,超過需求 263 [I] |
| 2 | 中繼資料批次化:一批預配置對齊 AU 的連續 cluster、檔案標 NoFatChain(不寫 FAT)、bitmap 與目錄項每批寫一次 | Zoned UFS / F2FS 的中繼資料分流;exFAT 連續檔位元 | 降低 SD 每檔 4–6 ms(量測後才知道降多少);減少卡內 GC 尖峰 |
| 3 | SD 走 VSC:CMD20 開始錄影、批次從 AU 開頭、以 RU 倍數寫;塊大小 = AU | SD VSC;韌體已有 C0649xxx | 取得卡的保證最低速度,壓低 692 ms 級尖峰 [I] |
| 4 | 每塊完成即歸還、塊大小依媒體(SD=AU、SSD=指令上限) | 幀被扣住的時間從一整批縮成一塊 | 小幀/高格率不再撞 96 格與 RAM 上限 |
| 5 | 音訊 WAV 進同一個寫入 task | §1:一般寫入會強迫送出未滿的批 | 批次不再被切碎 |
| 6 | **檢查 cluster 補齊的實際成本** | SD 128 KiB cluster:1,095,168 B → 1,179,648 B(+7.7%);SSD 512 KiB:→ 1,572,864 B(**+43.6%**) | 若補齊真的寫進媒體,SSD 小幀模式大量浪費頻寬;可改為多檔共用連續 cluster 流(#2)或改格式化參數。待驗:補齊是否實際傳輸(rec log 的 MB/s 以檔案大小計) |

### 11.3 要先量的(都是唯讀/計數)
- 錄影中 C065E8E0(CMD20)是否被呼叫;卡的 AU 大小與 VSC 支援(SD Status)。
- SD 每檔 4–6 ms 的拆解(FAT / bitmap / 目錄各寫幾次、寫在哪)。
- cluster 補齊是否實際寫入媒體(SSD 每批送出的位元組數 vs 檔案總和)。

來源補充:USENIX FAST '26《Unleashing Zoned UFS》(Kim et al.);USENIX ATC '25 Z-LFS;FAST '25 MedFS;
FAST '21 SpanDB;FAST '15 F2FS;arXiv 2307.11866(NAND 與主機儲存堆疊整合綜述)。

## 12. 上機:這張卡能不能走 VSC(2026-10-14,只讀)

卡:使用者目前插的 SD(128 GB 級,UHS-II 協商)。只讀 `mem get`,未錄影、未載入 06CMD20。
探針:`research/storage/sd_au_probe.py`。

| 讀什麼 | 位址 | 值 | 意義 |
|---|---|---|---|
| UHS-II 使用中 | 0xC2F2E7BC | 1 | 走 UHS-II,CMD20 由 C0662B28 送,不看 UHS-I 的 SCR 位元組 |
| UHS-II CMD20 支援 | 0xC2F2E874 | 0x02458403 | bit0=1 ⇒ 驅動允許 CMD20 [I:欄位語意依 C0662B28] |
| UHS-I SCR 位元組 | 0xC381B52B+slot×8 | 0(整段 0) | UHS-I 路徑才用,這裡無效 |
| SD Status 快取 | 0xC2F2E8A8 | 0xF0000000 | AU_SIZE=0xF(64 MB);**VIDEO_SPEED_CLASS=0、VSC_AU_SIZE=0** |
| | 0xC2F2E8AC / 8B0 | 0x00200AA3 / 0x0000400C | UHS grade=3、speed class 欄位 |
| SD vol(0xC37D50D4)+0x1FF0 | | 1 | **AU 配置關閉,退回一般配置** |
| +0x1FEC / +0x1FE8 / +0x1FE4 | | 1 / 2 / 0xEEF80 | 與 C064AD18 的退回分支完全吻合 |
| +0x146C / +0x1460 / +0x145C | | 0x100 / 0x200 / 0xEEF80 | 每 cluster 256 sector(128 KiB)、512 B/sector、978,816 cluster |
| +0x1434 / +0x1458 | | 0x8000 / 0x8000 | 分割區起點與資料區各 16 MiB ⇒ 資料區在 32 MiB |

結論:
- ioctl 0x109(C0663CE0)回報 VSC=0、VSC AU=0,所以 C0649D70 取不到 VSC AU,C064AD18 關掉 AU 配置。
  **這張卡上載入 06CMD20 不會走 VSC 配置**(FS 第一道關就退回)。
- 待確認:卡上標示是否有 V30/V60/V90。若有標示卻讀到 0,則是韌體解析 UHS-II 的 SD Status 有問題,不是卡不支援。
- 即使沒有 VSC,一般 AU_SIZE 仍是 64 MB;資料區起點 32 MiB(符合 SDXC 的 32 MiB 邊界單位,但不是 64 MB 的倍數)[I]。

### 12.1 同一張卡在 Mac 上(內建 UHS-II 讀卡機,IORegistry,只讀)
- CID:MID 0x03(SanDisk [I])、OID 0x5054「PT」、PNM「SP2BP」、Rev 3.0、2020-04、SDXC 128 GB、UHS-II 模式。
- macOS 回報 Specification Version 3.0、Speed Class 碼 4(Class 10)。VSC 是 SD 5.0 才有;規格版本 3.0 ⇒ 卡設計早於 VSC [I],
  與相機讀到 VIDEO_SPEED_CLASS=0 一致。可能是第一代 SanDisk Extreme PRO UHS-II(U3、無 V 標)[I,未查證型號]。
- exFAT:分割區起點 16 MiB、cluster 128 KiB(與相機 vol 欄位一致)。
- ⇒ 要測 VSC 需要一張規格版本 ≥ 5.0、標有 V60/V90 的卡。

### 12.2 CMD20 單發測試 —— 卡死(2026-10-14)
- 前置:is_recording 0;callfn getter C0407E20 → 1(工具正常);SD vol[0] 裝置碼 = 0xE。
- 送出:`callfn(0xC01EB940, 0xE, 0x198, B)`,B = cave.claim('cmd20test.arg') = 0xC072E6C0,內容 0x00000000
  (推定為 SD 3.0 舊式 Start Recording;bit27=0)。路徑:ioctl 0x198 → C065E948 → UHS-II → C0662B28。
- 結果:**呼叫沒有返回**,shell 任務卡在驅動裡;callfn 還原 echo 時 `echo handler did not become 0xC03D99A0`,
  之後 `version` → LIBUSB_ERROR_TIMEOUT。echo 槽(0xC0BAC2F8)可能仍指向 callfn ⇒ 需要冷開機。
- 未知:卡是否真的收到 CMD20、是在等卡的 busy 還是等驅動的鎖/事件(從 shell 任務呼叫,不在 FS 鎖內)。
- **真因(事後反組譯):C01EB940 是 Thumb 函式(首字 0x4604B570),呼叫位址應為 0xC01EB941。**
  callfn 以偶數位址 blx,CPU 用 ARM 模式執行 Thumb 碼 ⇒ 跳進亂碼。卡死與 CMD20、卡片、驅動無關;CMD20 根本沒送出。
- 下一次:位址 +1;並照原廠 C0649DB8 的環境先拿 FS 全域鎖([0xC37D0644],C01F8E8C/C01F8CDC,兩者為 ARM)。stub:`research/storage/cmd20_fslock.S`。

### 12.3 CMD20 單發測試 —— 成功送達,但卡片不回報對錯(2026-10-14,冷開機後)
- stub `research/storage/cmd20_fslock.S`(FS 鎖內呼叫 ioctl 0x198,ioctl 位址 0xC01EB941;r1 給緩衝區就在鎖內複製
  UHS-II 命令/回應區 0xC381B480..+0x2C)。unicorn 驗過參數、Thumb 切換、堆疊。
- 三發結果完全相同:

| 參數 | callfn | ioctl 回傳 | 回應區(鎖內複製) |
|---|---|---|---|
| 0x00000000 舊式 Start Recording | 返回 | 1 | `0d000001 00000100 … 0d001020 00090000` |
| 0x08000000 VSC Start Recording | 返回 | 1 | 同上 |
| 0xF0000000 保留碼(負面對照) | 返回 | 1 | 同上 |

- 解讀:驅動走 UHS-II 路徑(C0662B28 送 CMD20 → C0660B88 沒有錯誤位元 0x8000 → C0662168 送 CMD13)。
  回應區是 CMD13(header 0x0D、RCA 0x0001),卡片狀態 0x00000900 = tran 狀態、READY_FOR_DATA,錯誤位元全 0
  (含 ILLEGAL_COMMAND)。CMD20 自己的回應被 CMD13 蓋掉。
- **保留碼也沒有錯誤 ⇒ 從回應無法判斷卡片是否真的進入錄影模式**;只能確認指令送達、卡片沒有拒絕、送完仍正常。
- 每發後 `dir \fpSup` 正常,未錄影,未寫卡,未動設定區。
- 下一步:功能性驗證只能看效果 —— 錄影時在 Start Recording 之後量寫入速度/延遲尖峰,與不送的對照比較。

### 12.4 V60 卡:原廠 VSC 配置器會啟動(2026-10-14,只讀)
卡:SanDisk「SP2BP」產品修訂 5.0、2024-12、128 GB,UHS-II;與舊卡同產品名(舊卡修訂 3.0、2020)。
macOS 兩張都報「Specification Version 3.0」⇒ macOS 這欄不能判斷 VSC(§12.1 的推論作廢,舊卡的證據只剩相機讀到的 VSC=0)。
卡上只放 Loader v3 + 00SHELL(build_v3.py --shell,無 fast-start),未重新格式化(本來就是 16 MiB / 128 KiB)。

| 讀什麼 | 舊卡 | **V60 卡** |
|---|---|---|
| SD Status 快取 0xC2F2E8A8 | 0xF0000000 | **0x93C00240** |
| AU_SIZE 碼 | 0xF(64 MB) | 0x9(4 MB) |
| VIDEO_SPEED_CLASS | 0 | **60** |
| VSC_AU_SIZE | 0 | **36 MB** |
| 0xC2F2E874 | 0x02458403 | 0x02458443 |
| vol+0x1FF0 AU 模式 | 1(退回) | **0(VSC 配置啟用)** |
| vol+0x1FEC 每 AU cluster | 1 | **0x120 = 288 = 36 MiB** |
| vol+0x1FE8 | 2 | 0x22 = 34(推定:第一個 AU 邊界在 cluster 34 ⇒ 資料區 32 MiB + 4 MiB = 36 MiB) |
| vol+0x1FE4 / +0x1FE0 | — | 0xD3C = 3,388 個 free AU / 0xD3B |
| vol+0x145C cluster 數 | 0xEEF80 | 0xEE3C0 |

- 3,388 × 36 MiB ≈ 119 GiB ≈ 整張空卡 ⇒ +0x1FE4 是 free AU 數 [I]。
- **對「每檔一個 AU」的預測**(06CMD20 的原廠流程):FHD 29.97p 每秒 30 檔 ⇒ 約 113 秒用光 free AU;
  23.976p 約 141 秒;M12 239.76p 約 14 秒。用光之後 C0649F48 重掃不到 ⇒ 寫入錯誤、提早停錄 [I,待上機]。
