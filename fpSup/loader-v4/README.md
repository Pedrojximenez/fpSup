# Loader v4 — 最小組合(核心 + SUPMGR + SHELL)

設計：`projects/loader-v4/DESIGN.md`(2026-10-20 定稿)。**離線完成，沒上機、沒寫卡、沒 commit。**
`v3/` 一個位元組都沒動(v3 工作區裡的未提交修改是 10/11 其他 session 留下的)。

## 檔案

| 檔 | 內容 |
|---|---|
| `sloader4.h` | 合約:48 B 標頭 `FSB4`(flags、一段 DMA 範圍、顯示名稱)、服務表 v5、fpSup 頁的 `struct sl_row` |
| `sloader4.c` | 核心(由 v3 `sloader.c` 衍生):載入、claim/journal/關機寫回、cave、publish、快取執行、fpSup 頁註冊表、停用清單、服務查找 |
| `sloader4_entry.S` | 入口 stub(v3 的，拿掉 allsups;`strs` 4 個字) |
| `supmgr.c` | SupManager sup(`SUPMGR.BIN`,sup_id `SMGR`):在 fpSup 頁註冊一列、`provide(SMGR)` 提供 toggle |
| `build_v4.py` | 建置:`python3 -B v4/build_v4.py --out DIR` → `DIR/fpSup/{LOADER,SUPMGR,SHELL}.BIN` + `DIR/AutoRun.txt`(沿用 v3 的共用開機外殼) |
| `test_sup4.c` | 測試用 sup(前面放設定表，回寫它看到的東西) |
| `test_v4.py` | unicorn 測試 + `--mutate` |

產物(2026-10-20 這版):`LOADER.BIN` 11448 B `a2b44321…`、`SHELL.BIN` 4524 B `d711f05c…`、`SUPMGR.BIN` 268 B `6a323c53…`。

## v4 合約重點(給要遷移的 sup)

- **標頭** 48 B:`magic "FSB4"`、`header_len 48`、`file_len`、`block_size`、`entry_off`、`sup_id`、`version`、`min_svc`(5)、
  `flags`(`SL_F_CACHED_OK`=1)、`dma_off/dma_len`、`name_off`(顯示名稱)。v3 檔(`FSB1`)**不載入**,LOAD.LOG 記 `14`(OLD_FORMAT)。
- **載入順序 = 檔名字母序**(不分大小寫),不再用數字前綴。
- **快取執行**:區塊 64 B 對齊、補滿整條快取列;經非快取別名讀檔、`publish()` 後，有 `SL_F_CACHED_OK` 的 sup 在 `+0x80000000`
  執行,`entry` 拿到的 `block` 也是快取別名。DMA 共用的區段用 `svc->uncached(p)` 取 0x4… 別名(只換算 sup 自己區塊內的位址)。
  核心自己(含 journal、關機程式、狀態)也在快取別名執行。
- **服務表 v5**:v3 的欄位位置全部不變(`patch_sup.S` 的 +8..+28 照用),後面加
  `uncached`、`self_path`、`file_is`、`provide`、`find`、`page_add`、`page_refresh`、`page_count`、`page_row`、`sups_list`、`disabled_get`、`disabled_set`。
- **res-custom 維護者的兩個需求**:
  1. `cave_alloc` **與 v3 完全相同**(同一 bump、8 對齊),RESCUS 的 24 B veneer 形狀不變，`vrc_find()` 照舊可用;
     另提供 `svc->provide(id, ptr)` / `svc->find(id)` 明確查找(先 provide 者勝，第二個回 `SL_CONFLICT`;sup 被 RELEASE 時一併撤銷)。
  2. 自己的檔案路徑：`entry` 的 r2(同 v3)、`svc->self()`(entry 期間)、**`svc->self_path(svc, 區塊內任一位址)`**(開機後任何時候，兩種別名都可)。
     寫回前用 **`svc->file_is(path, expect, n)`** 確認檔案存在且前 n bytes 相同——它只讀不建檔(sup-writeback-must-not-create)。
- **fpSup 頁**:`page_add(row)` 回列號，`SL_BADARG`(類型不對、JUMP/ACTION 沒 open、TOGGLE/LIST 缺 get/set、不在 entry 中)、
  `SL_FULL`(總數 64)。依標題排序(不分大小寫),**SupManager(sup_id `SMGR`)的列固定在最前**。不限單一 sup 列數。
  每頁 5 列:第 p 頁第 k 格 = `page_row(p*5+k)`。結構與字串由 sup 常駐保管。
- **停用清單**:在 LOADER.BIN 檔尾(`FSDS`,沿用 v3 格式)。**卡上有 SupManager 才套用**;SupManager 不會被停用;
  `disabled_set(SMGR)` 回 `SL_BADARG`;寫回 LOADER.BIN 前先 `file_is` 比前 64 B,不符就不寫(`SL_NOT_SELF`)。
- **LOAD.LOG**:每個檔一行(LOADED 行的第二欄 = claim 數),不再逐一列 claim(v3 會被塞滿而漏掉後面的 sup)。

## 測試結果(2026-10-20)

`cd fpSup/fp_usb_shell && python3 -B -m unittest v4.test_v4` → **25/25 OK**(約 30 s)。涵蓋：
字母序與舊格式拒載、LOAD.LOG 只計數、DMA 範圍不合法 = BAD_HEADER、核心在快取別名、CACHED_OK sup 在快取別名且 64 對齊
(沒旗標的在非快取別名)、BSS 清零到整條快取列、self/self_path/file_is(含「不建檔」)、provide/find(先到者勝、跨 sup)、
cave_alloc 與 v3 相同、列排序與 SupManager 置頂、5 列分頁對應、總數 64 與錯誤列、RELEASE 的 sup 不留列與服務、列的回呼常駐可呼叫、
停用清單三規則(有 SupManager 套用/沒有就忽略/不能停用自己)、`disabled_set` 寫回與「檔案被換掉就不寫」、`sups_list` 內容、
關機寫回與殘留修復(含「只 claim 不寫」時殘留也被還原)、衝突 RELEASE、真的 SUPMGR(註冊、provide、經它 toggle)、真的 SHELL(v4 載入並 spawn worker)。

`python3 -B v4/test_v4.py --mutate`:**20/20 突變全被抓到**(約 12 分鐘)。

## 與設計的差異(這一輪沒做到的)

1. **fpSup 頁與 SupManager 頁的畫面沒有移植。** v3 的畫面是 `allsups.c` + `\fpSup\UI\ALLSUPS.BIN`(FT6:FT_ page-id hook、
   NBR 讀取器、固定格變數、POST_STR、彈窗)。v4 這輪只有**資料層**:註冊表、排序、分頁對應(`page_row(p*5+k)`)、
   `sups_list` / `disabled_*`。要把 FT6 畫面改成「通用列表頁讀註冊表」+「SupManager 自己的頁」,是下一步(會用到 uishare,
   要與 RESCUS 等的 UI hook 一起驗)。在那之前，相機上看不到 fpSup 頁的新列。
2. **SHELL 沒開 `SL_F_CACHED_OK`。** 它的區塊只放 `spawn`;worker 會把自己搬到 `WCODE_PTR` 的另一塊配置執行，
   TRB/EP82/EP83/MEM1 緩衝在 worker 自己的池(CPU 位址 − 0x40000000 = DMA 位址，依賴非快取別名)。
   讓 worker 本體走快取要改 worker.S(搬到快取別名、DMA 緩衝明確維護)——不在這輪範圍。
3. **SUPMGR 的 `open()` 只記錄被選中**(沒有畫面可跳)。

## 上機步驟(主 session 做;每步先廣播相機使用權)

第一步只放 `LOADER.BIN` + `SHELL.BIN`(+ `AutoRun.txt`),其餘 sup 先移出卡:
1. 開機，讀 LOAD.LOG:`0A … SHELL.BIN`、`0E` DONE;沒有 `14`。
2. **頁表確認快取別名**:用 sys-perf 的方法讀 `[0x44300000 + (va>>20)*4]`,核心區塊(fill/poff 物件位址)在 0xC5… 時描述子應為 TEX=5 B=1。
3. **迴圈計時**:同 `projects/sys-perf` 的 4M 指令迴圈，核心不影響，但要確認 `cave` 仍可用(`cave.claim`)。
4. **USB 傳輸 sha**:putfile / getfile 一個 1 MB 檔，讀回比 sha256(SHELL 仍是非快取，行為應與 v3 相同)。
5. **`ui_latency.py`**(projects/sys-perf/validation/20261019-live/):開/關選單 Gui:Update,與基準(開 346 ms、關 482 ms)比較。
   注意：這一步看不到 uishare hook 的改善——那要等 UI 層(差異 1)移植、hook 走快取別名之後。
6. 再加 `SUPMGR.BIN`:LOAD.LOG 有它;`sups_list`/`disabled_set` 可用 callfn 經服務表驗(畫面待差異 1)。

## 突變

`test_v4.py` 檔尾 `MUTANTS`(20 個):快取執行(sup/核心)、64 對齊、舊格式拒載、停用清單三規則、排序(反向、SupManager 不置頂)、
總數上限、RELEASE 留列/留服務、file_is 說謊、disabled_set 不驗檔、provide 覆蓋、self_path 認不得非快取別名、claim 逐行記錄、
DMA 不驗、殘留不修、BSS 不清。第一輪有 2 個存活(provide 回傳未檢查、殘留修復被 sup 自己的寫入蓋掉)、4 個不能編譯，
補了測試與修正突變後 20/20。

## 開機外殼：圖片開機畫面 + 兩種快速啟動(2026-10-20)

`build_v4.py` 原本只產出舊的預設外殼(文字進度條、沒有快速啟動)。現在跟 v3 的 `boot_card` 用同一組開關，同一個產生器(`build_autorun.py`):

```
python3 -B v4/build_v4.py --card --out v4/out-card     # = --splash --instant --fast(合併頁出貨的組合)
python3 -B v4/build_v4.py --out v4/out                 # 不加選項：與先前逐位元組相同
```

- `--splash`:四格圖片開機畫面，同時寫出 `fpSup/UI/0..4.BIN`(與目前共用的開機圖逐位元組相同)。
- `--instant`:Fast Start 2,電源開關重開走 RAM 裡的 loader hook(`0xC03DA420`),不跑 AutoRun。
- `--fast`:Fast Start 3,第一次開機把 loader 存進設定區(`XC_CommonSaveData+0x28`),之後冷開機由短 AutoRun 從設定區載入。
- **`out-card/AutoRun.txt` 與卡上原本由合併頁產生的 AutoRun 逐位元組相同**(`card-backup-20261020/AutoRun.txt`,sha256 2e77dfe3…),
  沒有任何差異行;開機外殼不含 loader 位元組,loader 在 LOADER.BIN 的區段裡。
- 產物:`out-card/` = `AutoRun.txt` 4666 B `2e77dfe3…`、`fpSup/LOADER.BIN` 12360 B `88ee9749…`、`SHELL.BIN`、`SUPMGR.BIN`、`UI/0..4.BIN`。
- 測試:`python3 -B -m unittest v4.test_boot_card_v4`(8 項，unicorn,真的 v4 核心與 SHELL):
  四種 instant×fast 組合都載入 v4 SHELL+測試 sup 並在關機寫回;Fast Start 2 暖開機不跑 AutoRun 也載入;
  Fast Start 3 第一次 miss → 存入設定區 → 冷開機從設定區載入。突變：拿掉 splash / instant / fast 任一都會失敗。
- 設定區：寫入的是 v3 合併卡已上機使用中的同一個 store bootstrap 格式(magic = loader 位元組的 sha256 前 4 B),
  不寫任何設定值(遵守 research/SETTINGS_AREA_FIRST_RULE.md)。**不需要在選單開啟**:第一次冷開機自己存，之後自動走快速路徑。
  換成不同 loader 位元組的卡(例如加 `--boot-markers`,它開了 `--profile`)時，第一次冷開機 magic 不符 → 走慢速路徑並重存，第二次起才快。

## 開機打點 `--boot-markers`(預設關)

```
python3 -B v4/build_v4.py --card --boot-markers --out v4/out-card-markers    # 隱含 build_autorun --profile
python3 -B ../../projects/loader-v4/boot_timeline.py                         # 開機後在主機讀時間軸
```

- **位址**:向 cave 要——arena 起點 `0xC072E064`(= `CAVE_ARENA`)。打點常式 `asm/boot_marker.S`(68 B)在 `0xC072E064..0xC072E0A7`,
  陣列在 **`0xC072E0B4`**:`magic, count, stamp[14]`(共 `0x98` B 到 `0xC072E0FC`)。讀:`mem get 0xC072E0B4,,64`。
  AutoRun 在 loader 跑之前寫入;每次開機 bump 會重設到 arena 起點，v4 核心(`BOOT_MARKERS`)在 `sl_load` 一開始就用第一個
  `cave_alloc` 把這塊拿走(arena 起點是 4 mod 8,cave_alloc 回 `0xC072E068`;bump 從 `0xC072E064` 開始，整塊都是自己的),
  之後任何 sup/host 的 `cave_alloc` / `cave.claim` 都在它後面。
- **magic**:AutoRun 寫 `'MRK1'`;核心看到 `MRK1` 改成 `'MRKD'`(這次開機的 AutoRun 寫的);不是 `MRK1`(暖開機沒有 AutoRun,
  陣列是上一次開機留下的)就清成 `'NONE'`、count 0。
- **時鐘**:`F_TICK_US`(`0xC002B6E0`),與 `LOAD_START_US`(`0xC072F6F4`,`--profile`)、`LOAD_DONE_US`(`0xC072F6F8`)、韌體 log 同一個鐘。
- **打點位置**(AutoRun 去延遲處理之後才插入，所以不影響「交給 cave 前恢復逐字延遲」那段):

  | 標記 | 位置 | 慢速路徑 | Fast Start 3 命中 | Fast Start 2 |
  |---|---|---|---|---|
  | S0、S1 | AutoRun 第一行(去延遲 NOP)之後、常式寫入並 publish 之後，連打兩次 | ✓ | ✓ | — |
  | S2 | 第一個 `display osdfile` 之前 | ✓ | ✓ | — |
  | S3 | 最後一個 `display osdfile` 之後(在第一次交給 loader/store 之前) | ✓ | ✓ | — |
  | S4 | 呼叫 store bootstrap 之前 | ✓ | ✓ | — |
  | (loader) | `LOAD_START_US` / `LOAD_DONE_US` | ✓ | ✓ | ✓ |
  | S5 | 呼叫逐字寫出的 loader 之前 | ✓ | — | — |
  | S6 | 逐字 loader 返回之後 | ✓ | — | — |

  **store bootstrap 之後不插標記**:Fast Start 3 命中時 loader 會把下一個 `echo` 設成中止腳本，標記會蓋掉它，腳本就會往下再載一次
  (突變測試「標記插在 store slot 與它的 echo 之間」會失敗)。所以 Fast Start 3 的「loader 返回」用 `LOAD_DONE_US`。
- **S0 不是 AutoRun 的真正第一行**:前面有去延遲 NOP 1 行、常式寫入 17 行 `mem set`、陣列初始化 2 行、publish 4 行(共 24 行)。
- **標記開銷**:每個標記 = 2 行(`mem set` + `echo`);**S1 − S0 每次開機都量**(boot_timeline.py 會印)。尚未上機，數字待量;
  整體多出：常式安裝 23 行 + 7 個標記 14 行(慢速路徑)/ 5 個 10 行(Fast Start 3),以及 `--profile` 的 loader 多 6 個字。
- **關閉時逐位元組相同**:`--card` 與不加選項的產物與加選項前相同(diff 驗證;測試 `test_off_is_byte_identical`);
  v3 的 `test_boot_options` 8/8、v4 `test_v4` 25/25 照過，v3 合併卡 AutoRun 仍與卡上備份相同。
- 測試(`v4.test_boot_card_v4`,真的逐行執行 AutoRun):慢速路徑 7 個遞增標記且 S5 < LOAD_START < LOAD_DONE < S6、
  常式在載入後仍完整、bump 在區塊之後;Fast Start 3 命中 5 個標記且 S4 < LOAD_START、腳本停止;Fast Start 2 暖開機陣列被清成 NONE。
  突變 7/7 抓到(不 Fast Start 3、核心不標 seen、暖開機不清、不保留區塊、計數不前進、少 S6、標記插進 store slot 與 echo 之間)。

## 上機部署(out-card 或 out-card-markers)

1. 刪舊再寫(mode 7 不截斷):`fl del \AutoRun.txt`、`fl del \fpSup\LOADER.BIN`,再 putfile 寫入，全長讀回比 sha256。
   `SHELL.BIN` / `SUPMGR.BIN` 已在卡上且未變就不用動。
2. `fpSup\UI\0..4.BIN`:卡上原本那份與 out-card 的逐位元組相同，**不用重寫**(只有空卡才需要寫)。
3. v3 的 `fpSup\UI\ALLSUPS.BIN` v4 不用，可留可刪。
4. 冷開機一次(插著 USB 關機會變冷開機;或撥開關關機後拔線再開)。Fast Start 3 第一次冷開機走慢速路徑並存設定區，之後才快。
5. 有打點的卡：開機後跑 `boot_timeline.py`;要比三種開機，各做一次冷開機(慢速/Fast Start 3)與一次電源開關重開(Fast Start 2)。

## 縮小引導程式(`--slim`,2026-10-20,離線完成，未上機)

`python3 -B v4/build_v4.py --out DIR --card --slim`(可加 `--boot-markers`)。**預設不變**:不加 `--slim` 時產物與之前逐位元組相同
(`--card` AutoRun 仍 = 卡上備份 `2e77dfe3`;`out-card-markers` `7f58e009`、`out-card-nofs3` `84792781` 也不變)。

### 現在 AutoRun 逐行 `mem set` 寫進 cave 的東西

| 段 | 內容 | 字數(原 → slim) |
|---|---|---|
| loader 入口 | `b load` + `b lhook`(Fast Start 2 入口在 +4) | 2 → 0 |
| 配置 | push、`H_GET`/`H_ADDR` 要 64 KiB staging(class 0) | 約 13 → 13 |
| 開檔 | F_MGR、F_VOL、ctor、open;**SSD 時先試 F_VOL 的卷、失敗再改卡**(重試迴圈) | 約 21 → 14(`--slim-open`:直接開卡;F_MGR/F_VOL 照呼叫) |
| 讀檔 | read、close | 7 → 7 |
| 驗證+執行 | dtor、"VBIN" 魔數、D/I-cache、跳 stage2(檔案第一段) | 16 → 16 |
| 歸還+返回 | `H_FREE`、pop | 5 → 5 |
| Fast Start 2 入口 `lhook` | 暖開機 hook 進來：load,失敗才啟動 AutoRun | 10 → 0(`--lhook-in-file`:改放在 BIN,stage2 放到 loader 後面) |
| 路徑字串 | `\fpSup\LOADER.BIN` | 5 → 5 |
| **loader 合計** | | **81 → 62**(帶 `--profile` 88 → 69) |
| Fast Start 3 引導 | 驗魔數、從設定區複製 loader 到 cave、publish、跳 | **30 → 26**(`--store-slim`:cache 改直接 `bl`、常數一次 ldmia) |
| 標記(只在 `--boot-markers`) | stamp 常式 | 不變 |

### 估算(以上機實測每行 `mem set` ≈ 7.3 ms:(3.66−3.24 s)/(88−30 行))

| 開機路徑 | 少的行數 | 預估 |
|---|---|---|
| 一般(無 FS3,每次冷開機) | 19 | **約 −140 ms**(loader 完成 3.66 → ~3.52 s) |
| Fast Start 3 命中 | 4 | 約 −30 ms(3.24 → ~3.21 s) |
| FS3 換 loader 後第一次 | 23 | 約 −170 ms |
| 設定區用量 | loader 324 → 248 B | 少 76 B(上限 468 B) |

### 試過但不可行:Fast Start 3 直接在設定區執行(不複製)

設定區在 0xC307xxxx,韌體函式在 0xC000–0xC044xxxx,距離 46–48 MB,**超過 ARM `bl` 的 ±32 MB**;
loader 的每個韌體呼叫都是一個 `bl`,改成暫存器呼叫每個多 2 字，反而更大。已撤回(unicorn 實際跑到 FETCH_UNMAPPED 才發現)。

### 行為差異(都只在 `--slim`)
- `--slim-open`:loader 一律開**卡**上的檔(原本先試 F_VOL 指的卷，接 SSD 時是 SSD,再退回卡)。F_MGR/F_VOL 仍呼叫(跳過曾導致凍結)。
  開檔失敗時把 staging 第一字清零，保證不會執行到上次殘留的 "VBIN"。
- `--lhook-in-file`:暖開機 hook 指向 `asm/lhook_stub.S`(10 字，stage2 每次載入都放到 loader 後面、對齊 8);
  stage2 武裝前照舊檢查該位址的第一字。只在 `--instant`(`--loader-hook`)時啟用。
- `--store-slim`:`asm/store_boot_slim.S`,契約同 store_boot(魔數來自卡、不讀設定區的長度、miss 什麼都不碰)。

### 測試
`python3 -B -m unittest v4.test_boot_slim_v4`:7/7(逐行解譯 AutoRun:一般冷開機+暖 hook、接 SSD 時 slim 直接開卡、
找不到檔且 staging 全是舊 "VBIN" 時不執行、FS3 慢路徑→命中(cave 由設定區複製、stub 重新放置並武裝)、FS2 經 stub 重載、
外來設定區不動)。`python3 -B v4/test_boot_slim_v4.py --mutate`:**9/9 突變被抓到**。
既有測試重跑：`v4.test_boot_card_v4` 8/8、`v4.test_v4` 25/25、`v3.test_boot_options` 8/8。

### 上機步驟
1. `build_v4.py --out out-card-slim --card --slim --boot-markers`(比較時再出一份 `--splash --instant --boot-markers --slim` = 無 FS3)。
2. 照「上機部署」:刪舊再寫 `AutoRun.txt`、`fpSup\LOADER.BIN`,全長讀回比 sha256。
3. 冷開機(shell `reboot` 會重載映像 = 冷開機)×3,每次 `boot_timeline.py`;FS3 卡第一次是慢路徑、之後命中。
4. 對照組用同一方式量非 slim 版(上次:一般 3.63–3.68 s、FS3 3.19–3.29 s)。
5. 撥電源開關重開，確認 Fast Start 2 經 stub 仍能載入(hook 位址 = loader 後面，不再是 CAVE_LOW+4)。

### 預設改為 slim(2026-10-20,使用者決定)
`build_v4.py` 的 `--slim` 現在**預設開啟**;`--no-slim` 產出舊引導程式(`--card --no-slim` 的 AutoRun 仍逐位元組 = 合併頁版 `2e77dfe3`)。
上機實測:一般冷開機 loader 完成 3.63–3.68 → **3.47–3.54 s**;瞬間啟動經 BIN 內 lhook stub 正常(1.44 s)。
行為差異:slim 的 loader 只讀 SD 卡，不再去 SSD 找檔(使用者接受)。測試:test_boot_card_v4 8/8、test_boot_slim_v4 7/7、test_v4 25/25。

## 關機紀錄器(`--pwroff-log`,除錯用，預設關;2026-10-20)

目的：查「插著 USB 撥開關時，關機為什麼送 0x40(完整重置)而不是 0x10(自我刷新)」。
背景與位址:`projects/loader-v4/notes/IMAGE_RETENTION.md`。**關閉時 LOADER 逐位元組不變**(4 種組態對改動前原始碼比對過)。

| 紀錄 | 誰寫、何時 | 放哪 | 活得過 |
|---|---|---|---|
| 早期(28 字) | 核心自己的關機程序(`unhook` 先呼叫 `pl_early`,再寫回 journal);XC_PowerOffMgr 兩個清單都會叫，第二次只計數 | XC_CommonSaveData `+0x210`(0xC307544C,112 B 空區;FS3 用 `+0x28` 起，不重疊) | **冷開機**(清單回呼在設定存 flash 之前) |
| 晚期(13 字) | 包住原廠否決回呼 `[0xC31D848C]=C0023B60` 的 `pl_wrap`;C0122F90 呼叫它後立刻寫 0x2D000400 | 開機時 `cave_alloc(64)` 的區塊(不清零) | 只有**暖開機**(自我刷新) |

- 回呼指標在**關機當下**才換(`pl_early`,只在它仍等於原廠 C0023B60 時);它在 BSS、每次開機由 C0023A20 重新註冊，不需 journal。包裝函式呼叫原廠函式並**原樣回傳**;前後各寫一次(原廠那條重置路徑可能不返回)並清 D-cache。
- 早期紀錄抓：關機原因、`[0xC30756C4+0x08/0x60/0x68/0x6C/0x70]`、`0x2D000300..30C`、`0x2D000280`、回呼指標與 `+0x230/+0x234`、序號、開機 id。
- 限制:(1)晚期紀錄在冷開機時一定沒有(cave 隨映像重載)——冷開機只能靠早期紀錄;(2)喚醒因子是 C0122F90 讀的那一刻才決定，早期紀錄是清單回呼時的值(稍早);晚期紀錄若 0x308/30C 都是 -1,表示 C0122F90 已因 r5=0 清掉;(3)寫入的是設定區裡研究過的空區，仍屬實驗——若出現任何設定異常，拿掉這版即可(下次關機不再寫)。
- 讀取:`python3 -B projects/loader-v4/pwroff_log.py <標籤>`(唯讀;附加到 `projects/loader-v4/validation/pwroff_log.jsonl`),會推算當次寫了哪個命令與原因(喚醒因子 / 回呼否決 / 原因 3/4/6)。
- 測試:`python3 -B -m unittest v4.test_pwroff_log_v4`(8/8)、`--mutate` 8/8 被抓到;v4 既有測試不變。

### 上機步驟
1. 建卡:`python3 -B v4/build_v4.py --out <dir> --splash --instant --boot-markers --pwroff-log`;部署 LOADER.BIN 與 AutoRun(先 fl del 再寫、讀回比 sha)。重開一次讓它生效(第一次關機才開始有紀錄)。
2. **插著 USB** 撥開關 ×N:每次開好(shell 通)就跑 `pwroff_log.py usb-<i>`。冷開機時只會有早期紀錄。
3. **拔掉 USB** 撥開關 ×N(開好後插回)→ `pwroff_log.py nousb-<i>`。暖開機時兩份紀錄都有，可直接看命令與原因。
4. 比較兩組的 `mgr_08`、`pmu_308/30C`、`cb_230/234`、`armed`、`command/why`。

## 插 USB 也瞬間啟動 —— 已移除(2026-10-20)

`--fast-usb-reboot`(FUSB)已從 v4 **完全拿掉**(使用者決定，保持 loader 精簡)。它在關機時改寫原廠否決回呼 C0023B60,
但上機實測(`projects/loader-v4/validation/README.md`、`notes/IMAGE_RETENTION.md` §7)證明那條路與插 USB 無關：
插著 USB 撥電源開關，韌體把關機改成 **reason 3**(與 shell `reboot` 相同)→ mode 2 寫 0x20 → 必定重新載入映像，
根本不經否決回呼，所以 FUSB 開著也還是冷開機。

**替代(已實測可用)**:`python3 -B fpSup/fp_usb_shell/fastreboot.py now [--wake 2]` —— 送原生 shell `poff N`
(reason 1 + N 秒後鬧鐘喚醒),插著 USB 也瞬間啟動、不用碰相機;主機端約 7.4 s(含 2 s 鬧鐘),loader 約 1.8 s 完成。
瞬間重開保留 RAM,要乾淨狀態用 shell `reboot`(冷)。不帶數字的 `poff` 會關機且不會自己開回來。

移除時驗收：六種組態(`--card`、`--card --no-slim`、`--splash --instant --boot-markers --pwroff-log`、同前加 `--pwroff-file`、
只 `--pwroff-log`、只 `--pwroff-file`)的 LOADER 與 AutoRun 和移除前 `--no-fast-usb-reboot` 產物**逐位元組相同**
(`--card` LOADER `4fb3e23e`、`--card --no-slim` AutoRun `2e77dfe3`、上機版 `--pwroff-log` LOADER `8948d108`)。

## 關機紀錄寫卡(`--pwroff-file`,除錯用，預設關;2026-10-20)

為什麼：插 USB 撥開關是冷開機，RAM(cave、晚期紀錄)全清;設定區在 XC_PowerOffMgr 清單回呼**之前**就存 flash、開機讀回，
所以 `--pwroff-log` 的早期紀錄寫了也留不住(上機 2026-10-20 實測)。卡上的檔案活得過冷開機。

- 核心關機程序(`poff_hook`,排在 `pl_early` **之後**)把一筆固定 128 B 寫到
  `\fpSup\PWROFF.LOG`(open mode 7、固定長度覆寫，只寫這個檔名)。兩個清單都會叫：第一次寫、第二次只計數。
- 檔案物件與路徑在**開機時**配好(關機時不配置);開機時讀舊檔接續序號(magic 與尾端 ~magic 都對才採信)。
  建檔失敗就跳過，關機照常(journal 寫回不受影響，有測試)。
- 內容(32 字):magic `PWF1`、序號、第幾次呼叫、關機原因(傳入的 reason)、tick µs、current_time ms、
  `[0xC30756C4+0x08/0x60/0x68/0x6C/0x70]`、`0x2D000300..30C`(喚醒因子)、`0x2D000314`(原始輸入,VBUS = id2)、`0x2D000280`、
  外部供電位元組 `[[0xC30783D8+4]+0xB8]`、busy `[0xC3075748]`、否決回呼 `[0xC31D848C]` 與 `+0x230/+0x234`、
  保留欄位 22–24(原 FUSB;現固定 0xFFFFFFFE,舊記錄仍可讀)、boot id、LOAD_DONE_US、~magic。
- **限制**:這筆是在 C0122F90 決定 0x10/0x40 **之前**取的，是決定的輸入不是結果;結果看下次開機的 `0x2D000280` bit0。
  寫卡發生在關機途中，若卡驅動在關機時不能用，這一筆就沒有(序號不前進，讀取工具會說「回呼沒跑或沒寫成」)。
- 關閉時 LOADER 逐位元組不變:`--splash --instant --boot-markers --pwroff-log` 仍是上機版 `99ab85ee`;`--card --no-slim` AutoRun 仍 `2e77dfe3`。
- 測試:`python3 -B -m unittest v4.test_pwroff_file_v4`(9/9)、`--mutate` 8/8 抓到;test_v4 25/25、test_boot_card_v4 8/8、
  test_boot_slim_v4 7/7、test_pwroff_log_v4 8/8全過。

### 上機步驟
1. `python3 -B v4/build_v4.py --out <dir> --splash --instant --boot-markers --pwroff-file`;
   部署 LOADER.BIN(先 fl del 再寫，讀回比 sha;AutoRun 不變)。重開一次生效(之後每次關機才寫)。
2. **插著 USB** 撥開關 ×2:每次開好(shell 通)跑 `python3 -B projects/loader-v4/pwroff_file.py usb-<i>`。
3. **拔掉 USB** 撥開關 ×2(開好後插回)→ `pwroff_file.py nousb-<i>`。
4. 比較兩組的 reason、`mgr_60/68`、`pmu_300..30C`、`pmu_314`、`ext_power`、`busy`、`cb`;
   **檔案不存在或序號沒前進 = 關機程序沒跑或沒寫成**——那本身就是答案(插 USB 時走的是另一條關機路徑)。

## fpSup 頁與 SupManager 頁(2026-10-21,離線完成，未上機)

設計:`projects/loader-v4/DESIGN.md` §14(使用者定案：首頁同 SupManager 版型、設定列在列上用 popup 改值、SupManager 頁維持 v3 r3o2 拿掉 More options)。

| 檔 | 內容 |
|---|---|
| `fpsup_ui.c` | 核心的 UI 引擎(v3 allsups.c 一般化：FT4P 資料檔 → 字串層、變數、NBR 頁、狀態機、`FT_` page-id 層)+ 首頁 FT_Y6 邏輯。`FPSUP_UI` 時由 sloader4.c include,uishare 一起編成一個單元 |
| `supmgr.c` | SupManager:首頁第一列 JUMP → `svc->ui_show("FT_LIST")`;清單/Enable/Disable 用核心的 `sups_list`/`disabled_set` |
| `uishare/tab/home4_page.py` | 首頁畫面(MainY5 物件;5 列 = 名稱 + 右側值 + 原生 popup 三項 + JUMP 箭頭) |
| `uishare/tab/build_fp4.py` | FT4P 寫檔器;`\fpSup\UI\FPSUP.BIN`(首頁)、`\fpSup\UI\SUPMGR.BIN`(v3 FT_LIST,變數改 `SM_`) |

- 服務表 **v6**:`ui_pack(path, ready, arg)`(entry 中登記，所有 sup 載完後核心安裝，再呼叫 ready)、`ui_show(page)`(韌體 `gui scr set`:`C054DD38()->vt[0x48]`)。
- 列的種類：TOGGLE = Off/On(可給兩個標籤)、LIST ≤ 3 項(`SL_LIST_MAX`,原廠 popup 三格)、JUMP 顯示箭頭、ACTION;JUMP/ACTION 鎖住 popup,Right/OK 寫 `FT_Key = 40 + k` → 核心呼叫 `open()`。
- 核心以偽 sup「LOADER.BIN」(sup_id `FUI4`)在所有 sup 之後 claim GUI/字串站點，關機照常還原;SupManager 清單不列它。LOAD.LOG 碼 `32`:`1` 無資料檔、`100+r` 首頁安裝結果、`200+r` 各 sup 的頁。
- 建卡:`build_v4.py --ui`(預設開)多寫 `UI\FPSUP.BIN`(125 KB)、`UI\SUPMGR.BIN`(107 KB);`--no-ui` = 不含頁面的核心。
- 測試:`python3 -B -m unittest v4.test_ui_v4`(16 項，真核心 + 真資料檔 + v3 的假 UI app)、`uishare/tab` 的 `test_fp4`(5 項：原生解譯、變數全有註冊、原廠轉場);突變 fpsup_ui.c 11 個、supmgr.c 7 個全被抓到。原有 55 項 v4 回歸全過。

**上機待驗(風險)**:`ui_show` 從 UI 執行緒切頁、FT_LIST 的 MENU 回 FT_Y6;鎖住的列 Right/OK 是否仍寫 FT_Key;popup 第三格(v3 刪掉的 33499)位置與 `max-value`/高度綁定;開機時 POST 變數值(v3 是註冊時給值);瞬間啟動時 GUI 是否已就緒;SupManager 頁沿用首頁註冊的 logo 圖。

### 第一次上機(2026-10-21)

卡:`LOADER.BIN` 30320 B(`card-ui`,AutoRun 與卡上相同未動)+ `SUPMGR.BIN` + `UI\FPSUP.BIN` + `UI\SUPMGR.BIN`;`fastreboot.py now`。

- **通過**:LOAD.LOG `32 00000100`(首頁裝好)、`32 00000200 SUPMGR.BIN`(SupManager 頁包裝好、ready 跑過);FT_Y6 在
  SHOOT 1 左邊(MainB1 按 LEFT 進入);標題、logo、SupManager 列、`...` 箭頭、`Loader v4`、頁尾隨焦點換(Page/Back ↔ OK/Back)。
  畫面數 223(221+2)、狀態機 19(17+2)。`SM_PageText` = "1 / 3"(清單 15 筆)。
- **壞 1 分頁條是彩色條紋**:v3 SupManager 頁也有(使用者確認),是 `manage_page.page_tabs` 的舊 bug,不是 v4 新增。
- **壞 2 JUMP 列按 RIGHT 不跳頁**:`svc_ui_show` 用 `gui scr set` 的路(C054DD38 vt+0x48),**選單裡完全無效**
  (`gui scr set MainY5` 在選單裡也不動)。選單內換頁只能走頁面的 `controlAppState` request → 狀態機轉換。
  執行函式 0xC05F1399 要的是動作物件(延後佇列 ctx+0x198+0x30),無法用字串直接呼叫。
  另外 `smgr->opened`(0xC50C0CC4)實機按 RIGHT 後仍為 0,鎖住(Lock=1)的列 Right 有沒有寫 FT_Key 未確認。
- **壞 3 焦點掉進看不見的物件**:從 MainY5 按 RIGHT 進入時 FT_Focus = 55(原廠分頁列的焦點編號),畫面無反白;
  另一次是 33617(看不見的第 2 列)。照 skill 用 S1 退出,沒有卡死。
- `gui seti` 不可靠(`seti FT_TabX5 77` 讀回 4096),不能拿來模擬頁面寫入。

### 第二輪診斷與修正(2026-10-21,離線完成，待上機)

診斷(實機，卡片未動;`callfn` 呼叫 POST_INT 推變數、`mem_get` 讀 `smgr->opened`):

- **彩條 = 寬 1024 的分頁標籤**。`FT_TabVisible1=0` 彩條消失;`FT_TabWidth1` 改 1000、1022 都正常顯示 "1"。
  SupManager 頁 3 頁(寬 341)時數字正常 —— 不是數字圖的問題，是單頁時那一格剛好 1024。
- **JUMP 列不跳頁 = 被鎖住**。`Lock=1` 的列 Right/OK 完全不送 FT_Key(`opened` 停在 0);推 `FT_Lock1=0`
  後列變白、出現 `>`,按 RIGHT 直接進 SupManager 頁(`opened`=1),回來沒有殘留 popup。
  `ui_show`(vt+0x48)**從 UI 執行緒回呼呼叫有效**;從 shell 下 `gui scr set` 才無效。
- **焦點掉進看不見的列 = 上下鍵循環經過空 slot**。標題列按 UP → 33704(第 5 個空 slot);綁在 tab-index 的 0 擋不住。
  原廠用 objectBase `is-visible`(popup 平常 is-visible=0,上下鍵不會進去)。
  在頁面上推 `FT_Focus` 只改變數，不會移動焦點(只在進頁時採用)。
- `gui seti` 不可靠，模擬頁面寫入要用 POST_INT(callfn)。

修正:

- `fpsup_ui.c` / `supmgr.c`:單頁時分頁寬 1022(首頁改版後單頁不顯示分頁，只剩 SupManager 用得到)。
- 只有空 slot 上鎖(`Lock = !r`);JUMP / ACTION 列不鎖，Right/OK 同時開原廠 popup(換頁後看不到)。
- `home4_page.setting_row`、`manage_page.sup_row`:`Visible` 另外綁列根物件的 `is-visible`。
- **使用者 2026-10-21:6 項(含)以下不分頁**。首頁 slot 0..5(slot 0 在標題列的位置):≤6 列時標題列隱藏
  (`FT_Title`=0)、焦點落在 slot 0(`FT_Row0` 的初值 = slot 0 SELECT 編號 33588);>6 列才出現標題列、每頁 5 列在 slot 1..5。
  頁面寫回的鍵碼改用 j = slot + 1(popup 20+j、JUMP/ACTION 40+j)。
- 測試:test_ui_v4 20 項(新增 6 列不分頁、7 列分頁、後頁跳頁、page_refresh 重畫、slot 0 重畫)、
  test_fp4 5、test_manage_page 7、v4 核心/開機/關機 + v3 allsups 74 項通過;fpsup_ui.c 這次的 11 個突變全抓到。
- 卡:`card-ui2`(AutoRun 與卡上 a1a97df3 相同);LOADER.BIN 30728 B、SUPMGR.BIN 2716 B、UI\FPSUP.BIN 134348 B、UI\SUPMGR.BIN 107380 B。
- 未做:SupManager 頁的「6 項以內不分頁」(它沿用 v3 版型與變數)。ACTION 列按 Right 會開一個空白 popup(目前沒有 sup 用 ACTION)。
- **第二輪上機通過**(card-ui2):LOAD.LOG 兩包都裝好;只有 SupManager 一列 → 沒有標題列、第 1 列白字帶 `>`、
  進頁焦點 33588;UP/DOWN 不再進空列(is-visible 有效);RIGHT 進 SupManager 頁(分頁 1 2 3 正常)、MENU 回來焦點仍在原列。
  剩一個觀察：從第 1 列按 UP 會到原廠分頁層 55(左右切 MainY5/MainB1,與原廠相同),但畫面沒有任何反白。

### 第三輪(2026-10-21,離線完成，待上機)

- **MENU 退不出去(使用者實機回報)**:複製列時刪掉了原廠 MENU 的 48 bytes `controlAppState`(原廠的退出選單),
  換成 `Return` request,但 TransFtTab 沒有 FT_Y6 的 Return 轉換。首頁的列與標題列改回原廠退出動作
  (`home4_page.stock_exit`);SupManager 頁照舊 Return 回 FT_Y6。test_fp4 檢查 FT_Y6 沒有 41 bytes 的具名 request。
- **頁首反白**:焦點在原廠分頁層 55(左右切 MainY5 / MainB1)時沒有任何標示 → `manager_header(head_var=)` 加灰底,
  opacity 綁 `FT_HeadOn` / `SM_HeadOn`,核心在焦點回呼裡推 `v == 55`。頁首是 render group,灰底會不會即時重畫待上機確認。
- **SupManager 也 6 項以內不分頁**:`build_manage(v4=True)` 加 slot 0 與 `FT_Title`;變數接在 v3 的後面
  (`build_fp4.supmgr_extra`:slot 0 的 12 個、Title、Row0、HeadOn);`supmgr.c` 用 `vpart` / `vslot` 換算;
  `smgr_open` 換頁前推 `SM_Focus`(不分頁 = slot 0,分頁 = 標題列 —— 進頁前推的焦點值會被採用，第一輪實測過)。
  v4 的 `sup_row` popup 鍵碼 20 + k + 1(slot 0 不與「關閉」的 20 撞)。v3 預設參數下輸出不變。
- 使用者決定翻頁維持標題列 + 數字分頁(不改原廠那種細橫杠)。
- 測試:test_ui_v4 23、test_fp4 6、test_manage_page 7、v4 核心/開機/關機 + v3 allsups 74 通過;
  supmgr.c 12 個與 fpsup_ui.c 1 個突變全抓到。卡 `card-ui3`(AutoRun a1a97df3 不變):
  LOADER.BIN 30740、SUPMGR.BIN 3028、UI\FPSUP.BIN 134651、UI\SUPMGR.BIN 116901。
- **第三輪上機通過**(card-ui3,再換 card-ui4 的兩個 UI 檔):首頁列上 MENU 直接退回 LV;SupManager 15 項 → 分頁 1/2/3、
  進頁焦點在標題列、第 3 頁 5 列(已載入白字、舊格式與 SupManager 灰字);MENU 回首頁、再 MENU 退出。
  頁首反白:灰底放在頁首群組裡會蓋掉 logo 和標題 → 改成群組前面的同層物件(card-ui4,只換 UI\FPSUP.BIN、UI\SUPMGR.BIN,
  LOADER / SUPMGR 位元組不變);焦點到 55 時頁首變灰、logo 與標題在上，回到列上即消失，首頁與 SupManager 頁都正常。

## 私有字串與 sup 的頁面(2026-10-21 重做：不用 uishare、不設上限、loader 只當 fpSup 頁的主人)

使用者定案：
- loader v4 是 **fpSup 頁的主人**，統籌這一頁的 UI;其他 sup 做自己的 UI 不礙到人就隨它。
- 需要協調(改同一個原廠位置)的 sup,由上面的**容器 sup** 協調(例如 res-custom),不是 loader。
- 推薦的載入方式做成函式庫 **`fpSup/fpsup-ui/`**(= uishare 去掉「共用」):每個 sup 自己 `#include`。
  說明與 API 見 `fpSup/fpsup-ui/README.md`。fpSup 首頁也用它裝。

loader 這邊只剩兩個**固定規則**的 hook(開機一開始、任何 sup 之前就掛好，不需要任何 sup 的資料):
- 頁面 hook:頁名 `FT_` 開頭 → MainY5 的 GUI id。
- 字串 hook:編號在 [0x40000000, 0x80000000) = 字串自己的位址(非快取別名)→ 回傳 +0x80000000;其餘原廠規則。
  擁有／剩餘走 `borrow()` 登記的範圍鏈結串列(C,經 `str_callc` 對齊堆疊、還原 r1/r3/r12/lr/sp)。
- 服務表 v6 後段只有兩個通用服務:`file_read(path, buf, n)`、`borrow(lo, hi)`。
- 原廠字(四個掛鉤點)由 build_v4.py 從韌體映像讀出、以 -D 傳入;頁面檔不再帶。頁面檔 magic `FT4S`,檔頭 17 字。
- LOAD.LOG `32`:a=0 hook 已掛 / 1 沒有首頁檔 / 2 宣告失敗 / 3 cave 不夠 / 0x100+r 首頁 / 0x300+n 第 n 個字串點不是原廠字。
- SupManager 在自己的 entry 用 fpsup-ui 裝 `UI\SUPMGR.BIN`(那時後面的 sup 還沒載，所以清單在打開頁面時重列)。
- A/B 實測(單層 hook 對 uishare 套娃):開選單 Update 480 → 192 ms,切頁 −50~55%(projects/sys-perf/README.md)。

## 已上線 sup 升到 v4(2026-10-22,離線完成，未上機、未寫卡、未 commit)

使用者 10-22 指派：合併頁上已上線的 sup 由這個 session 升到 v4。決定:Lossless 開關搬到 fpSup 頁的開關列;
ScreenFlip 留在原廠 TOOLS 頁;Res-Custom 從線上版 v0.1.4test 的原始碼(`projects/open-gate/archive/res-custom-before-generalize-20261019/`)升;
Jose 的兩個由我們改。

**核心修正**:三個字串 hook 點改成 `SL_EXCL`(`fpsup_home.c` ui_early)。原本是 SHARED_UI,帶著 v3 uishare 的 sup 能一起 claim、
載入後選單卻靜靜裝不上;現在會被拒載,LOAD.LOG 記衝突(`test_ui_v4` test_a_v3_uishare_sup_is_refused_on_the_string_sites)。

| sup | v4 檔 | 怎麼做 | 測試 |
|---|---|---|---|
| FCAP / ULWR / STOPFX / GYR2(build 6)/ SHELL | `ports.py` | 各自 builder 建 v3,`build_v4.from_v3` 換檔頭(本體不動、+16 B;GYR2 經人工確認位置無關);SHELL 帶 release 的 BURST15 | `test_ports_v4`;ULWR 全段錄影 `projects/rec-core/writer`: `ULWR_V4=1 python3 -B -m unittest test_card`(9 項) |
| Lossless | `fpSup/lossless/build_v4_lossless.py` → LOSS.BIN 31,040 B | `native/menu_row4.c`:fpSup 頁 TOGGLE 列取代 CINE 頁列(拿掉 uishare);存檔位移 48、寫前 `file_is` | `fpSup/lossless/test_v4_lossless.py`(9 項，含 fpSup 頁顯示) |
| ScreenFlip | `fpSup/screenflip/build_v4_flip.py` → FLIP.BIN 21,008 B | TOOLS 列改走 `fpsup-ui/fpui_stock.c`;存檔 48 + `file_is` | `test_v4_flip.py`(14 項：v3 全部行為測試重跑 + 頁面對參考實作、字串經核心 resolve) |
| RAW-View | `projects/rawview/build/build_v4_rawview.py` → RAWV.BIN 33,996 B | COLOR 列走 `fpsup-ui/build_stock_section.py`;`stub_sv` 寫前 `file_is`、先清 D-cache、檔案物件用非快取別名 | `test_v4_rawview.py`(v3 的 18 項重跑 + 4 項) |
| Res-Custom | `projects/open-gate/build/res-custom-v4/build_v4_rescustom.py` → RESCUS.BIN 310,272 B + 同樣 5 個 .RCD | 線上 v0.1.4test 原始碼複本 + `#ifdef OGC_V4`:檔頭 48、選單走 fpui_stock(`ogc_uia` 取 SL_SVC_AT 的 svc)、不 claim 字串點(C05E5BEC 仍 SHARED_UI);檔案物件放非快取別名、讀 .RCD／寫設定前後整個 D-cache clean+invalidate;RCD 檔頁改 FT4S `FT_RCFILES`(fpsup_ui.c)+ fpSup 頁 JUMP 列「Res-Custom」,MENU 回 FT_Y6;顯示名放在 layout 之前(S 本體要全零) | `test_v4_rescustom.py`:v3 的 66 項在 v4 核心重跑 + 4 項 v4(檔頭、無字串點、快取別名、檔案 I/O 非快取＋清快取，兩個突變都抓到)+ `UiV4Tests` 7 項(真的 fpui_stock/fpsup_ui:B2_5 列、虛擬幀率頁、QS 圖名 id 經核心 resolve 且 borrow、解析度清單、JUMP 列開頁、停用寫回 48、全停用仍留列、8 個檔翻頁)+ v3 位元組等於發布檔 |
| Desqueeze / Tap to Zoom(Jose) | `ports_jose.py` → DSQZ.BIN / TAPZ.BIN | 他的原檔只改兩個字:claim 數(去掉字串點)、`bl uia_apply` 改呼叫附加在 BSS 之後的 fpui_stock(svc 取自 SL_SVC_AT) | `test_ports_jose_v4.py`(4 項：列在 SHOOT 2/4、字串經核心 resolve、關機還原) |

- **`fpsup-ui/fpui_stock.c`**:uishare `ui_apply.c` 的 fork(原廠頁加列、頁面副本照 FSPG 慣例讓多個 sup 疊加)。原廠字串沿用原廠位移;
  其餘字串的編號 = 字串位址 − 0x80000000,有私有字串時要求快取別名並 `borrow`。頁面副本放快取別名。不支援 QS_OPTION(QS 由容器 sup 自己做)。
- v3 位元組都沒變：各 builder 的新參數預設關;Lossless、ScreenFlip 以 HEAD 版原始碼重建比對相同,RAW-View 去掉 `#if V4` 後等於發布時的原始碼雜湊。
  (三者的 v3 重建和發布檔本來就不同：uishare `ui_apply.c` 有別人未提交的修改。)
- **上機要驗**:每個 sup 的 LOAD.LOG 載入/claim 數;Lossless 開關切換後壓縮與存檔跨關機;ScreenFlip TOOLS 列與存檔;RAW-View COLOR 列、存檔、
  與 Res-Custom 共用 C0088C60/C05E5BEC(v4 字母序 RAWV 先於 RESCUS);Jose 兩列與功能;ULWR SD/SSD;Gyro2 每幀區塊。
- **Res-Custom 的 v3 位元組不變**:`res-custom-v4/` 是 archive 的複本(archive 本身沒動);把發布檔裡的 RCD 檔頁塞回去重建 = 線上 d9a8e100 逐位元組相同
  (不塞回時差 320 B,只因共用的 `uishare/tab/manage_page.py` 之後改過);v4 的改動全部在 `#ifdef OGC_V4` / `build_core(v4=True)`。
  RCD 檔頁 = v4 SupManager 的同一頁(`build_manage(v4=True)`,變數 SM_→RC_,標題綁 `RC_Header`「RES-CUSTOM (啟用數/上限)」):
  6 個(含)以下不翻頁、標題列藏起來從第 0 格開始;7 個以上第 1–5 格翻頁;分頁列有焦點時標題亮。邏輯照 `supmgr.c` 移植(`ogc_files.c` RV_*)。
- **Res-Custom 上機要驗**:B2_5 解析度列與 QS 圖示(字串 id 經核心)、虛擬幀率頁、RCD 檔頁進出(FT_RCFILES ↔ FT_Y6)、選擇存檔跨關機、
  讀 .RCD 在快取執行下內容正確(LOAD.LOG `OCD` 行的 found/ok 數)。
- 合併頁的 v4 打包:`tools/merge-v4/`(2026-10-24,本機、未發布)。

### 已上線 sup 的 v4 第一次上機(2026-10-24)

卡：`build_v4.py --splash --instant --boot-markers`(AutoRun 591e93f9 與卡上相同未動)+ 10 個 v4 sup(SHELL 沿用卡上 d711f05c);
測完照備份還原(卡上 IMXB/LUT 等原樣)。
- 冷開機與 `poff` 瞬間重開:12 個全部 LOADED,claim 數與離線相同(DSQZ 24、TAPZ 3、RAWV 40、RESCUS 117、LOSS 10、GYR2 2…),RESCUS `OCD` 5/5;皆在快取別名。
- 選單：fpSup 頁(SupManager / Lossless RAW / Res-Custom)、RCD 頁(5 檔不分頁、popup、MENU 回 FT_Y6)、SupManager 24 檔分 5 頁且顯示名正確、
  SHOOT 2 Desqueeze、SHOOT 4 Tap to Zoom、B2_5 解析度清單(OG2K…S16)、COLOR 的 RAW、Y2_5_1 TOOLS 第 5 列 Screen Flip:全部正常。
- 存檔:Lossless ON 跨 poff 保留;選 S16 → poff → 冷開機仍是 S16。
- **發現(RAW-View,應該 v3 也有)**:COLOR 清單游標移到 RAW 再按 MENU 取消，值仍是 0xC 但實際停在 RAW(列摘要顯示 STD.,再開清單游標在 RAW);要明確選 OFF 才回去。
- 快門角度(測試者回報 S16 關機後變 180°):v4 未重現 —— FHD 與 S16 下設 90°/ISO 640,poff + 冷開機後都保留 900。
- 未測：錄影(ULWR、Gyro2 每幀、Lossless 壓縮)、Jose 兩個功能本身、ScreenFlip 實際翻轉。

### 2026-10-24 第二批(離線完成，未上機)

- **游標延遲(使用者回報 fpSup 頁、SupManager 頁游標移動很 lag)**:焦點回呼每次移動都無條件 POST 頁首反白(`*_HeadOn`)
  與頁尾提示(`*_OK`)兩個變數，每個 POST 都讓 GUI 多跑一輪更新。改成值變了才 POST(`fpsup_home.c` home_focus/home_hint、
  `supmgr.c` smgr_focus/hint、Res-Custom `ogc_files.c` rv_focus/rv_hint)。測試 `test_moving_the_cursor_posts_nothing_unchanged`
  (test_ui_v4、test_v4_rescustom),三處各自還原舊碼都抓到。**是否就是 lag 的主因未量**:上機用 `projects/sys-perf/validation/20261019-live/ui_latency.py` 量 DOWN 的 Gui:Update(原廠頁 / fpSup 頁 / SupManager 頁，改前改後)。
- **Gyro2 開關**:不再只換檔頭。`projects/gyro2-sup/build.py --v4` = `gyr2.S -DGYR2_V4` + `src/gyr2_row4.c`:fpSup 頁 TOGGLE「Gyro2」,
  OFF = 開錄(mode 0)不加 MakerNote tag、整段不寫每幀區塊(開錄時鎖定);存在 GYR2.BIN 自己的記錄(`g2_rec`,寫前 `file_is`,錄影中不改);
  新裝為 ON。v3 位元組不變(2cbfe477)。測試 `test_gyr2_v4.py` 7 項，4 個突變都抓到。
- **Lossless 新裝預設 ON**(使用者):v4 的出廠記錄改 on=1;存過 OFF 的照樣 OFF。v3 位元組不變(e6e7b6a4)。

### 2026-10-24 第二批上機

卡：merge-v4 `b` 快照的 sup + 卡上原有 `QSTOUCH.BIN`(別人的 sup,與 TAPZ 搶 C0CFCCDC → TAPZ RELEASED,兩組相同)。
- **游標 A/B**(`ui_latency.py`,每組 10 鍵，單位 ms:按鍵→開始 / Gui:Update / Render):
  原廠 MainB1 約 50–75 / 1–2 / 19–20;fpSup 頁 A 約 50/75、B 約 65/40(DOWN/UP)/ 1–2 / 18;SupManager 頁 A 約 90/65、B 約 63/87 / 1–2 / 27;
  原廠曝光設定子頁 B1_1 約 75–100 / 13 / 52。三種頁都偶爾一次 6–10 輪、0.6–1.5 s 的長延遲(原廠頁也有)。
  **結論：POST 去重量不出差別;以 shell 送鍵量，我們的頁與原廠同級**。使用者感覺的 lag 要再確認是哪種操作(實體鍵/轉盤、進頁第一下 Render 76–114)。
- Gyro2 開關：頁面 OFF→寫回 GYR2.BIN(`G2ST,1,1`,其餘位元組不變);OFF 錄 A001_018:MakerNote 無 0x4653、無 FSG2;
  ON 錄 A001_019:81 幀全有 v2 區塊、樣本首尾相接、frame_seq 連續、無 lost、writer 6。
- Lossless 新裝 ON:列顯示 ON;兩段第 2 幀起約 1.0 MB/幀(未壓縮 3.2 MB)。
- 發現：在 fpSup 頁離開選單後，再按 MENU 回到的是原廠 SYSTEM 第 5 頁(MainY5),不是 fpSup 頁(FT_* 借 MainY5 的 GUI id)。
- 結束時卡 = merge-v4 `b` 全選 + 瞬間啟動 + 快速啟動(AutoRun 7190b462、LOADER 5ee215ec)+ QSTOUCH(使用者：不用還原)。

### 2026-10-24 第三批(使用者 UI 意見，離線完成，未上機)

- 從分頁列切到 fpSup 頁時焦點留在分頁列(FT_Focus 初值 55、FT_HeadOn 1),左右可繼續切頁;DOWN 才進列(原本落在 SupManager 列)。
- 標題「fpSUP」→「fpSup」;v4 三頁(fpSup、SupManager、Res-Custom 檔案頁)標題往下 5 px(`manage_page.V4_TITLE_Y` = 18,v3 頁仍 13,`build_ft6` 輸出不變)。
- fpSup 頁的「...」(1536 `font_G_3dot`)只在 JUMP 列顯示(跟 > 箭頭同綁 `FT_Jump<k>`):Gyro2、Lossless 這類開關列只顯示值。
- SupManager 頁與 Res-Custom 檔案頁的列(彈出 Enable/Disable,不是進頁)不畫「...」:`manage_page.sup_row(dots=False)`,只在 v4。
- 快照 `tools/merge-v4/inputs/v4-20261024d`。

### 2026-10-24 第四批：開關照原生(上機確認)

- **Off/On 自動翻譯**:變數送來的字串 GUI 照字面畫(上機實測顯示「0081」)。原廠的翻譯在 drawText 的文字欄位:
  文字 id 後一個 byte = 1 表示 .nloc key、畫的時候依語言查表(0 = 字面;`pg.literal` 會清成 0)。
  所以每個 slot 加原廠記錄複製來的靜態文字物件(`home4_page.stock_text`):值欄複製列名 30021 的 drawText、
  清單項目複製 30013/30027,只換 key `0080`/`0081`(B2_6.cvm 的 Off/On),保留原廠字體設定/大小/顏色。
  核心以 `FT_Tog`/`FT_TOff`/`FT_TOn` 控制顯示，開關列的文字變數送空白。上機：中文介面顯示「開啟／關閉」。
- **位置/寬度照原廠**(量 SHOOT 2「音訊記錄」):值欄右緣 965(30021 的 850×54 矩形、對齊欄位設靠右);
  開關的清單 x 797、寬 227,文字靠右到 965。清單的 x/寬綁 `FT_PopX`/`FT_PopW`,開關列 797/227,其他清單列維持 604/420。
- 踩到的坑：矩形高度改小(46)時字整個不畫;清單項目內的文字物件比項目寬(694 > 420)時也不畫。
- **清單 x/寬綁變數會拖慢每個按鍵**:`bind_sub` 綁 popup 的 position/size 後，連原廠 SYSTEM 第 5 頁按鍵→開始都從 ~60 變 125–210 ms、Render 18→33(上機 A/B;拿掉綁定即恢復，翻譯物件本身影響小)。所以清單一律固定原廠開關清單大小(x 797、寬 227、文字靠右到 965);目前沒有 sup 用 LIST 列。修正後 fpSup 頁 44 ms / Render 22、SYSTEM 5 59 ms / 17。
- **進場焦點**:FT_Focus 會記住上次的列，從原廠頁切回來時焦點落在列上(RIGHT 會打開那列)。改在頁面自己的進場 screenEvent(原廠 MainY5 的：先從焦點變數聚焦)最前面加一個動作把 FT_Focus 寫成 55(`home4_page.enter_on_tabs`);從子頁返回也一樣回到分頁列。上機：退出選單再切回，焦點在分頁列、RIGHT 切到 SHOOT 1。
- 未做：SupManager / Res-Custom 頁的 Enable/Disable 仍是英文字面;列名字體(`label_text` 強制英文字體設定)使用者說可能看錯，先不動。
- **SupManager 頁 / Res-Custom 檔案頁的 Enable/Disable**(使用者選：用原生 On/Off,其他說明文字維持英文):原廠 .nloc 沒有 Enable/Disable,
  `manage_page.sup_row(native=True)`(只在 v4)把兩個清單項目換成原廠 30013/30027 的 drawText,key 0081(開啟,choice 0)/ 0080(關閉,choice 1),
  清單同原廠開關清單 227 寬、文字靠右到 965;v3 頁 `build_ft6` 輸出不變(071a5d67)。上機兩頁都顯示「開啟／關閉」。
  狀態欄 Enabled/Disabled、Unload on restart、Restart to update 仍英文。快照 `tools/merge-v4/inputs/v4-20261024e`。
- **SupManager / Res-Custom 頁右欄改成原生 On/Off**(使用者 2026-10-24):`sup_row(native=True)` 在右欄放原廠 30021 的開啟/關閉
  (`stock_text`,已搬進 manage_page 共用,綁 `FT_TOff<k>`/`FT_TOn<k>`→SM_/RC_);不畫綠色 E;
  紅色 R(Unload on restart / Load on restart 等)放大到列名大小(NAME_SIZE、46 高)、右緣 855。
  變數接在 `supmgr_extra()` 最後(TOff0..5、TOn0..5);supmgr.c `V_TOFF`/`V_TON`:下次開機載入 = 開啟;
  Res-Custom `RV_TOFF`/`RV_TON`(RC_Header 往後移 12),RCD 啟用 = 開啟,不再送 Enabled/Disabled。
  快照 `tools/merge-v4/inputs/v4-20261024f`。離線完成，未上機(使用者在用相機)。
- **SupManager / RES-Custom 頁變慢**:每列的版本文字 V 的 x 綁在 `VersionX`('position' bind_sub,v3 留下來的)。
  v4 不顯示版本 → native 列不畫 V、不綁(核心照送 49,無害)。上機:SupManager 按鍵→開始 100–125 → 57–88 ms、
  RES-Custom 53–81 ms;Render 兩頁 33 ms(fpSup 頁 22、原廠 17–20,多的是右欄開啟/關閉與放大紅字);進頁後頭一兩鍵 Render 100+。
- 名稱(使用者):fpSup 頁列名與 SupManager 顯示名「Res-Custom」→「RES-Custom」;「Lossless RAW」→「Lossless-CDNG」。
  快照 `tools/merge-v4/inputs/v4-20261024g`。
- **RES-Custom 的重開提醒照 SupManager**(使用者):列上紅字(放大的 R)= 這次開機已載入(`row_by_label`)而下次不載入 →「Unload on restart」,
  反之「Load on restart」;頁尾不再顯示「Restart to apply」,右下「Restart to update」改空白(錯誤訊息 List full / Write failed / Recording busy 照舊)。
  文字表加 RT_UNLOAD/RT_LOAD(取 SupManager 的字)。快照 `tools/merge-v4/inputs/v4-20261024h`。離線完成。
- **RES-Custom 頁**(使用者):右下角的數量(5/6)拿掉(標題已有);列名改成該 RCD 在解析度清單裡的名字(RCD 的 SEC_UI 列文字，
  例「OG3.5K 3456x2304」),讀不到時才退回「檔名.RCD」。上機確認。快照 `tools/merge-v4/inputs/v4-20261024i`。
- **頁尾固定、logo 6 色**(使用者 2026-10-25):分頁的清單頁(SupManager / RES-Custom)頁尾固定「● OK ◀▶ Page MENU Back」不再切換
  (帶圖示的頁尾每重畫一次約 55 ms;標題↔清單 85 → 32 ms);logo 改原圖自身 6 色(黑線/白/膚/黃髮/紅/青),
  31 層 → 6 層,fpSup 頁標題↔清單 37 → 23 ms(原廠 20)。上機確認。
- **快速連按掉鍵 = 直接設畫面**(2026-10-25 實機):從 fpSup 頁打開 SupManager / RES-Custom 用的是 `gui scr set`(fpui_show),
  之後選單在快速連按時會吃鍵(0.15 s 間隔 4 下只動 1–2 下;0.3 s 以上不掉),直到退出選單。剛開機對 FT_Y6 自己
  `gui scr set FT_Y6` 一次就能重現;原廠子頁進出不會。`gui send <名字>` 走的是 AppSync,不會換頁。
  **修正:走原廠狀態機換頁。**
  - 服務表 **v7** `ui_go(page)`(sup 的最低需求仍是 v6;fpsup-ui `fpui_open(svc, page)` 執行時才看有沒有 v7,沒有就退回 fpui_show)。
  - JUMP 列按下:核心清空共用請求字串 T_GO(`build_fp4.GO_TEXT`,私有字串、執行時才讀)→ 呼叫 `open()`
    (sup 推好自己頁面的變數,最後 `fpui_open` 把頁名寫進 T_GO)→ 核心推 `FT_Go` 的下一個值。
  - fpSup 頁根物件上的 `appVariableChangeEvent`(MainY5 submenu_width 那筆的格式)在 `FT_Go` 變化時送 controlAppState request T_GO;
    各 sup 頁面包有 `FT_Y6 → 頁名`(request = 頁名,`build_fp4.open_transitions`)。
  - 為什麼不在按鍵事件直接送 request:request 比 open() 推的變數更早生效,RES-Custom(不分頁、焦點在第 0 列)進頁時第 0 列還沒顯示,
    焦點落空、按鍵全無反應。變數改變事件排在同一批變數之後,頁面建立時都已生效。
  - 回彈:fpSup 頁重建時會再觸發一次變化事件 → MENU 回來又被送回子頁。子頁進場時寫 `FT_Go = 0`(`manage_page.enter_write`,
    `build_manage(v4=True)` 與 Color 頁內建),核心看到 0 就清空 T_GO(`home_go`),重建時送的是空請求。
    (試過「等於 1 才觸發」的事件,type 5 / 0 都不會觸發,原因未明。)
  - 上機(LOADER 20864 B):SupManager 進出兩次後再進,焦點在分頁列;RES-Custom 進頁焦點在第 1 列、連按 3 下全到;
    回 fpSup 頁連按 4 下全到。Color(LUT.BIN)原始碼已改、離線測試,相機上的 LUT.BIN 是 10-22 舊版未換。
- **版本號放在檔名上**(使用者 2026-10-25):`Gyro2_v0.1.0.BIN`。SupManager 列名 = 標頭顯示名 + 檔名 `_v` 之後到 `.BIN` 的那段,
  顯示成「Gyro2 (0.1.0)」(沒有 `_v` 只顯示名稱;沒有標頭名稱時顯示檔名、不加括號)。
  同名不同版本(去掉 `_v…` 後相同)時 loader 讓新版先載入,舊版成為重複 sup_id 不載入、SupManager 灰字「Load failed」(使用者選 A)。
  比較:數字逐段比,`0.1.0` 新於 `0.1.0test`,再比後綴字母。檔名上限 39 字元(NAME_MAX);LOAD.LOG 每筆改記整個檔名(text 20 → 40,檔案 4096 → 8192 B)。
  SupManager bss 0x800 → 0x1000(每列 40 bytes 的列名)。測試:test_v4 `test_a_newer_version_of_one_name_wins`、
  test_ui_v4 `test_the_file_names_version_in_brackets`。各產品的輸出檔名還沒改。
- **各產品改名**(使用者 2026-10-25):名稱、檔名、版本集中在 `names_v4.py`,各建置與合併頁都從這裡取。
  RES-Custom_v0.1.4、Lossless_v0.3.0(fpSup 頁列名「Lossless-CDNG」→「Lossless」)、UnlockWriter_v0.1.0test「Unlock Writer」、
  Stop-FX_v0.1.0、Gyro2_v0.1.0、RAW-View_v0.3.0、ScreenFlip_v0.1.0「Screen Flip」、Desqueeze_v0.1.4、
  TapToZoom_v0.1.0「Tap To Zoom」(Jose 的 FPUI 區塊裡同長度改字、重算 FNV)、USB-Shell_v3.4.0、EarlyFlush_v0.1.0「Early Flush」(原 FCAP)。
  合併頁:`build_inputs_v4.py` 產生新名稱的快照(manifest 帶 name/version),`build_catalogue_v4.py` 用它;舊快照不動。
  卡上已有舊檔名(SHELL.BIN、GYR2.BIN…)時,新舊檔名不同,不會被當成同名新舊版:要先刪舊檔。
