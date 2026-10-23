# Unlocked Writer(ULWR,rec-core 寫入層 O2 + O3)

寫卡時不握 FS 鎖，檔案系統工作與寫卡同時進行;SD(CMD20)與 SSD 共用。2026-10-15 由 RECW 改名，下方日期較早的上機紀錄仍沿用舊名 RECW。

設計依據是 [`research/storage/notes/WRITER_LOCK_SCOPE.md`](../../../research/storage/notes/WRITER_LOCK_SCOPE.md) §5–§7。
規劃見 [`../WRITER_PLAN.md`](../WRITER_PLAN.md)。

**做法**:原廠的 C063F380 和 C063F048 一行都不改，仍由原廠決定一批要放什麼(extent、cluster 補齊、門檻、cookie 上限)。
我們只做兩件事：

- 把 vol 的 6 個 arena 指標(+0x4834..+0x4848)換成我們的，讓一批資料收進我們自己的塊。
- hook C063F140,把它從「同步送出」改成「封塊、交給寫入 task、換一個空塊」。

寫入 task 不拿 FS 鎖，自己做 acquire、add、`C01EB790`、release,最後逐一呼叫 C03A55D0 回呼 cookie。

| 檔案 | 內容 | 狀態 |
|---|---|---|
| `bq.h/.c` | 塊佇列純邏輯：開塊、checkpoint、add、rollback、封塊、晚到 cookie、依驅動表上限切段(只在 extent 邊界切)、照順序完成 | `test_bq.py` 9 項(含 3 個 mutant)|
| `wr.h/.c` | 原生轉接層：接上與還原 vol 指標、C063F140 替身、停錄排空(LR = 0xC063F34D)、寫入 task 本體。所有韌體呼叫都經過 `wr_fw` 表 | `test_wr.py` 10 項(含 2 個 mutant)|
| `wr_card.c` + `wr_card.S` | 上機外殼。C 負責韌體函式表、event flag 和寫入 task(優先權 6、堆疊 0x2000、載入時建立)。組語負責切到 cached 別名、兩個 hook(`ldr.w pc,[pc]`)、6 個 veneer;外層沿用 v3 的 `patch_sup`,只宣告兩個位址(SL_EXCL) | `test_card.py` 6 項(含 2 個 mutant)|
| `build.py` | 把 bq.c、wr.c、wr_card.c 合成一個編譯單元,`-fropi` Thumb,用 elf_text 拒絕任何重定位或可寫資料 → `build/20ULWR.BIN` | |
| `wq.h/.c` | 舊版「自己切塊」的佇列 | 已被 bq 取代(切塊交給原廠門檻),只留作參考 |

ARM(Thumb,`-fropi`)編譯結果：bq 1.9 KB + wr 2.2 KB,沒有外部符號;`wr_t` 共 53.7 KB(3 塊 × 2048 段),放在 sup 區塊的 BSS。

## 測試模型(`test_wr.py`)

原廠檔案層由 Python 模擬，**和原廠一樣透過 vol 的指標呼叫**,所以接上、還原都會被走到。模擬的行為包括：

- C063F220 / C063F048 / C063F380 / C063F140 / C063F310
- 不連續、cookie 上限、「4A58==0 立刻回呼」

驅動和裝置也是假的：驅動表忙碌時 acquire 回 0、寫入失敗，並逐 piece 檢查寫到的磁區位置。

每段錄影結束都要成立:

- 每個 cookie 剛好回呼一次，而且照順序。
- 回呼 status 0 時，這一幀的資料已經寫到正確的磁區。
- 停錄的 C063F310 返回時，所有塊都已經完成。
- vol 的 6 個指標換回原廠值,+0x484C 和 +0x4828 都清成 0。
- 驅動表沒有被佔住。

## 比原廠嚴格的地方

- 一幀跨兩批時，原廠只把後一批的 status 交給這一幀。我們在一批失敗時，把錯誤延續給下一批的第一個 cookie。最多多報一幀失敗，不會漏報。
- 晚到的 cookie 在沒有塊還在處理時會直接回呼，這時帶上最後完成那一塊的 status。原廠這裡固定回 0。

## 上機版 `20ULWR.BIN`

| | |
|---|---|
| 檔案 | 5224 B(RECW 時期 5228 B / 初版 4876 B) |
| 區塊 | 59000 B,其中 state 佔 53752 B |
| C 程式碼 | 3882 B |
| sha256 | `db37011bcbb0efdb…`(未上機;內容同 RECW `0107f8d6…`,只改 ID 與 task/flag 名稱) |
| sup ID | `ULWR`(原 `RECW`) |
| 宣告 | C063F140、C063F220、C03A549C 各 8 B,SL_EXCL |
| 塊大小 | 8 MiB |

**`test_card.py`(unicorn)**:用真的 loader v3 載入這個 BIN,然後整段錄影儘量跑**韌體自己的程式碼**:

- 開錄 C063F220(經過 hook220)
- extent 由 C063F048 經過我們的 veneer 加入
- SD 驅動的 acquire、add、checkpoint、rollback、release(C065F020..C065F268)
- 停錄 C063F310(經過 hook140,LR = 0xC063F34D)

只有以下這些由 Python 代替:`C01EB790` 寫入、`C03A55D0`、`C0644B68`、TK-OS 呼叫，以及 C063F380 本身的控制流程。寫入 task 跑的是真的 `wr_service`:原廠在我們的 flag 上等待時，模擬會停下、切去跑寫入 task,再接回原本的流程。

每段錄影都檢查以下幾點:

- 每個 byte 都照 ADMA 描述子實際讀出，寫到檔案該在的磁區位置。
- cookie 照順序、各回呼一次，而且在資料寫入之後才回呼。
- 停錄後 vol 換回原廠指標,+0x484C 和 +0x4828 都是 0,驅動表也已放開。
- 關機後兩個位址還原成原廠 bytes。

測試過程中抓到並修正的問題:

- 晚到的 cookie 直接回呼時，要帶最後完成那一塊的 status(原本固定是 0)。
- 一批寫入失敗時，要把錯誤延續給跨批的那一幀。

## 還沒做

1. 強制 `mgr+0xD=1`(SSD 選「標準」時)。第一版只接 SD 和 SSD「自訂」。
2. 上機:LOSS 壓縮一段已通過(見下)。一般模式未測。
3. 和 LOSS、FCAP 一起載入的組合測試(unicorn)。

## 上機紀錄 2026-10-15(`validation/20261015-live/`)

卡上:LOADER、00SHELL、10LOSS(74720 B,20261015-clear)、**20RECW(dad442fa)**、30FCAP、40GYR2,LOAD.LOG 5/5 載入。
hook 指向 cached 別名 0xC51BC8D0 / 0xC51BC910;wr_t @0xC51BD900:magic OK、flag 0x91、task 125。

`take-fhd60-loss-1`(FHD 59.94p、LOSS ON、SD UHS-II、8 s):

- 448 幀、沒有提早停、req=fin=448;LOSS compressed 447、flush.applied 447、tag_failed 0。
- RECW:install 1、send 59 = sealed 59 = chunk 59;dev_err、acq_retry、wait_free、late、mismatch、drain_timeout 全 0;drain 1,停錄後 vol=0(已還原)。
- rec log:每批約 8 幀(8 MiB),request→finish 約 60 ms(原本 FCAP 單獨時 40 幀一批、寫 400–425 ms)。
- 抽 8 幀(1、2、8、9、10、224、447、448)全部完整解碼，每 tile SOI/EOI 齊全(`frames-A001_070/`)。
  畫面接近全暗(raw_mean ≈319),所以這是「串流結構與解碼完整」的證據，不是對照來源的逐位元比對。
- 這段**有錄音**,使用者確認機內回放正常(音訊 WAV 與 DNG 同走這條寫入路徑)。音畫同步尚未量化(要拍板對齊)。

### 第二段(使用者錄):V60 SD、OG3K 29.97p、LOSS ON —— 38 s 自動停，停後「寫入中」卡住

- rec log:req_cnt=1134、fin_cnt=1133,停止原因 `mem, raw2`。
- LOSS:engine jobs given up 1(122 ms)、engine refused 1、native RAW errors 1(event 5)、壓縮 1094、兩道都忙放行 38。
- RECW:next_seq=done_seq=491,全部塊寫完、cookie 全交回;drain 2、timeout 0;vol 已還原、+0x4850=0;所有 task 閒置。
  ⇒ (更正，依 lossless-sup 讀現場)卡住的是**最後一幀 1134**(slot 78,state 0xC,不在任何佇列)。
  機制(原廠碼):C03A5348 在 C03A5460 先設 0xC,再於 C03A5490 呼叫 C069ADE0(LOSS 的 hook 點);mgr+0xD≠0 時完成只靠 vol cookie。
  C063F380 在 F816 若 vol+0x4828==0 就完全跳過 cookie。停錄 task(C0398D88)看到只剩 0xC 就 C063F310 清 4828。
  ⇒ LOSS 的 C03A5490 hook 不會等待(lossless-sup 確認)。真正的窗在 C069ADE0 內：開檔(C063B180)、寫(C063B898→C063F380)、關檔是**三段各自拿放 FS 鎖**。
  SRecFile 在開檔等 FS 鎖時(例如音訊 C063F898 握鎖、在 C063F140 等裝置/等 RECW 空塊),低優先權停錄 task 得以掃描並排隊;
  開檔放鎖時鎖直接交給停錄 task → C063F310 清 4828 → 接著的寫入在 F816 跳過 cookie。原廠也有此競態;RECW 的等空塊(本段 250 次)把窗放大。
  修法(已做，見下):RECW 在 C03A549C(C069ADE0 返回後)加防護 —— mgr+0xD≠0、node 仍 0xC、vol+0x4828==0 ⇒ 自己呼叫 C03A55D0(node, 寫入成功?0:-1)。
  排空是同步的，已登記的 cookie 早把 node 推到 0xD,所以不會重複完成。
- 計數一致：換卡時已重開機(wr_t 歸零),之後一段短錄(4 send、2 chunk)+ 這段(491 塊)= send 495、chunk 493。
- 證據:`validation/20261015-live/freeze-*`。

## 停錄競態防護(2026-10-15,build `0107f8d6`)

- 第三個宣告 `C03A549C`(ARM,C03A5348 的 `ldrb r3,[fp,#0xd]; cmp r3,#0`,沒有分支跳進來)→ `ldr pc,[pc,#-4]` + shim。
- `wr_late_frame(w, mgr, node)`:我們的停錄已還原 vol(`ended_vol`)、mgr+0xD≠0、node+0x1104==0xC、vol+0x4828==0 ⇒ 回 1,
  shim 把 r3 改 0,讓原廠走自己的「聚合關」分支(C03A54A8:`C03A55D0(node, 寫入>0 ? 0 : -1)` 與後續記帳)。
- `ended_vol` 在 restore 時設、每次 C063F220(hook220 入口，不論是否我們的)清。
- 新計數 `n_late_frame`;wr_t 的 `q` 往後移 8 B(`recw_state.py` 已改成從 build.json 與 `RECW_BLOCK` 算位址)。
- 測試:`test_wr` 加停錄插在最後 1–3 幀開檔與寫入之間(30 種子)、平常不觸發、下一段/原廠自己的段不觸發，
  mutant `WR_MUTANT_NO_LATE` 重現 10-15 症狀(200 幀只回 199)。`test_card` 用 unicorn 跑原廠 C03A549C..C03A55CC:
  停錄後的幀補完成一次(寫入失敗給 -1)、已由排空完成的(0xD)不重複、mgr+0xD=0 時照原廠、錄影中與新一段開始後不觸發;mutant 抓得到。
- 全部測試:bq 9、wq 5、wr 13、card 9 通過。
- **上機回歸(10-15,V60 卡、OG3K 29.97p、LOSS ON)**:錄約 64 s 後自動停(`mem, raw2`),**req=fin=1931,沒有卡住**。
  防護這次沒觸發(n_late_frame 0,競態沒發生)⇒ 證明沒變壞;正確性仍靠離線測試。RECW:825 塊、wait_free 391、錯誤全 0。
  LOSS:take_frames 1936 = 1 + 66 + 1867 + 2;native discard 5(raw)= 1936−1931。證據 `validation/20261015-live/regress-*`。
- **上機多段(10-15,同條件再錄 5 段，都錄到自動停)**:5 段都沒卡住;累計 install 6、drain 6、drain_timeout 0、錯誤全 0,
  **n_late_frame = 1 ⇒ 防護在相機上實際觸發一次，那段照常收尾**。最後一段 req=fin=1788。證據 `validation/20261015-live/multi-reclog.txt`。
- **SSD 自訂(10-15)**:2 TB、5000 Mbps、cluster 512 KiB。RECW 接上 SSD vol(wvol 0xC37DE5A4,不是 SD 的 0xC37D50D4)。
  OG3K、LOSS ON、按鍵停:req=fin=7958;前 7.7 s 在途峰值 4、sdb 最低 87、寫入佔用 21%、每批約 1.4 幀。RECW 錯誤全 0、drain 正常。
  LOSS:3631/7958 幀因兩道都忙放行未壓縮(LOSS 那端跟不上，已告知)。SSD「標準」幾段走原廠逐幀路徑(RECW 不介入，正常)。
  另一張 200 MB/s SD:OG3K 23.98p LOSS ON 8532 幀按鍵停,req=fin;累計 13 段無錯，防護觸發 2 次。證據 `ssd-*`。
