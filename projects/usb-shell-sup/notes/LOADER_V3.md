# Loader v3:一個 sup 一塊、一個 sup 一個檔

2026-10-06,依使用者的原則。**設計,未實作。** 取代 [LOADER_V2.md](LOADER_V2.md) 的「cave 佈局」與「各 sup 要改的」兩節;
V2 的原則 1、2、3(cave 不放變數、cave 只放程式與 hook、關機解除所有補丁)保留。

依據:2026-10-06 的現況盤點與逐 sup 可行性檢查(讀程式碼,未上機),摘要在 §9、§10。

## 0. 使用者定的原則

1. **每個 sup 宣告一整塊記憶體**,裡面是固定長度的變數與方法;塊內彼此用**相對位置**計算。
2. **AutoRun 只載入「載入器」,載入器只載入「加載器」;加載器把 SD 卡根目錄 `fpSup/` 下所有 `.BIN`(不含自己)依序載入。**
3. hook 到同一個韌體位置時,用**套娃**解決能疊的那部分。
4. 衝突時**不載入那個 sup**;**由各 sup 自己管理**這件事,加載器不做仲裁。
5. 加載器固定,不再由 merge 頁面動態生成;合併 = 把檔案放進 `fpSup/`。
6. uishare 不是 sup,是編進各 sup 的函式庫。
7. 修改順序:shell → lossless → gyro → og3k/og2k → raw-view → sensor-lab(改名 **res-lab**)。

## 1. 三層

```
AutoRun / Fast Start 3 / loader hook(0xC03DA420)
  └─ 載入器  cave 0xC072DE64,≤468 B(設定區上限),固定、幾乎不再改
       └─ 開 \fpSup\LOADER.BIN → 配一塊 → 讀進去 → D/I → 呼叫
            加載器(一個普通的塊,永不釋放:關機寫回與登記簿住在這裡)
              └─ 列 \fpSup\*.BIN,跳過 LOADER.BIN,依檔名排序,逐一:
                   讀標頭 → 配 block_size → 整檔讀進塊 → 其餘清零 → D/I
                   → r = entry(r0 = 塊基底, r1 = 服務表)
                   r == RELEASE → 釋放塊、撤銷它的登記、記 log
```

- **載入器**只認一個檔名,所以 Fast Start 的魔術字(由載入器位元組推導)從此不隨 sup 變動;merge 頁面不再改 loader 的立即數或讀取上限。
- **沒有** staging 緩衝、pass 1/pass 2、`0x40000000` 規則、入口表、`fpSup.BIN` 尾段、composer 拼檔。
- `0xC3757A7C` 池指標、`CAVE_ARENA` 以外的 sup 固定 cave 位址全部退場。

## 2. 檔案與標頭

`\fpSup\NNNAME.BIN`,8.3 大寫(韌體是否支援長檔名未測,先限制)。**檔名排序 = 載入順序 = 套娃由內而外的順序**
(後載入的在最外層、最先執行)。建議兩位數前綴:`00SHELL`、`10LOSS`、`20GYRO`、`30OG3K`…

```
+0x00  'FSB1'
+0x04  header_len
+0x08  file_len          整檔長度(含標頭)
+0x0C  block_size        ≥ file_len;超出部分由加載器清零(= BSS)
+0x10  entry_off         相對塊基底;bit0 = Thumb
+0x14  sup_id            4CC,例如 'GYRO'(同 id 只載第一個)
+0x18  version
+0x1C  min_services      需要的服務表版本
```

塊 = 檔案原樣 + 清零的尾端。程式、常數、選單資料(lossless 的 FPLM、res-lab 的 SLMP)都在塊裡,
**不再回頭讀檔**。

## 3. 塊內規則(位置無關)

- 塊內程式與變數一律 PC 相對:組語用 `adr` / `ldr [pc,#]`;C 用 `-fropi -fno-jump-tables`(uishare 已在用)。
- **build 檢查:連結結果沒有任何絕對重定位**;塊內指標表一律存「偏移」。
- 呼叫韌體:`ldr ip,=位址; blx ip`(`bl` 只到 ±32 MB,堆積離韌體約 48 MB)。
- 交給韌體的絕對位址(任務入口、vtable、回呼、hook 目標)在 entry 執行期用 `adr` 算。
- 塊內部需要的對齊(res-lab/raw-view 的 4 KiB 表)由 block_size 預留空間、執行期對齊。

## 4. entry 契約

```
r0 = 塊基底   r1 = 服務表   返回 r0 = KEEP(0) / RELEASE(1)
```

entry 的固定順序 —— **決定之前什麼都不寫**:

```
1. 對每個要改的位置/資源呼叫 claim()       ← 任一失敗 → 直接 return RELEASE
2. 全部成功 → 寫 hook、veneer、值補丁
3. 註冊任務、變數、選單(不可撤銷的動作只能在這之後)
4. return KEEP
```

RELEASE 時加載器丟掉這個 sup 的所有 claim、釋放塊。sup 不能自己釋放自己(程式碼還在塊裡跑)。
提交(步驟 2)之後**不支援卸載**:hook 已生效,保證不了沒人在塊裡執行。

## 5. 服務表(加載器提供,sup 自己決定怎麼用)

| 服務 | 用途 |
|---|---|
| `claim(addr, len, stock_ptr, kind)` | 登記「我要改這段」。同時記 journal(關機寫回 **sup 提供的原廠值**)。回傳成功/衝突 |
| `chain_next(site)` | CHAIN 位置的上一層目標(第一層 = 原廠目標) |
| `claim_res(id, kind)` | 非 hook 資源:LCD 暫存器 `0x30190044`、觸控旗標、無損引擎… |
| `boot_id` | 本次開機識別碼 |
| `log(str)` | 寫 `\fpSup\LOAD.LOG` |
| `reload(name)` | 只重載一個檔(USB shell 熱抽換用) |
| `holder(addr, i)` | **服務版本 3(2026-10-06)**:第 i 個(載入順序,含正在跑的)持有涵蓋 addr 之 claim 的 sup 的路徑;0 = 沒有了 |
| `self()` | 版本 3:正在跑 entry 的 sup 的路徑;entry 之間 0 |
| `done_at_start` | 版本 3(資料欄):加載器開始時的 `LOAD_DONE_US`;跑 entry 期間兩者相等 |

版本 3 的欄位**接在 struct 尾端**(`card.S`、`patch_sup.S`、`test_sup.S` 以 +8..+28 寫死呼叫);只有用到的 sup 設
`min_svc = 3`(31FMT);lossless 等 `min_svc ≤ 2` 照常載入。加載器跑 entry 期間在 `SL_SVC_AT = 0xC072F6FC`
(原 build_autorun 的死常數 `STORE_VER_AT`,沒人讀寫)放 `&svc`,跑完歸 0 —— 給拿不到服務表的函式庫(uishare)用。
⚠ **上機時新 LOADER.BIN 必須和 `min_svc = 3` 的 sup 一起部署**,舊 v2 LOADER 會以 BAD_HEADER 拒絕它。

登記簿住在加載器的塊裡(堆積,**每次開機自然是空的**)。sup 仍是自己決定 claim 什麼、失敗時放棄;
加載器只記帳、不仲裁。

`kind`:

| kind | 誰可以同時持有 | 用在 |
|---|---|---|
| `CHAIN` | 多個 CHAIN | 呼叫點 hook、插入式 hook(被換掉的指令用絕對跳板重建) |
| `EXCL` | 只有一個 | 取代式 hook、值補丁、語意上互斥的位置(og3k/og2k/res-lab、gyro 兩版) |
| `SHARED_UI` | 遵守 uishare 格式的 sup | 字串層 FSDL、檔案轉向 FSHK/FSFV(`0xC05E5BEC`)、換頁 FSPG |

### 這同時解決的三件事

1. **過期的層(V2 的 ⏸ 保留問題)**:位置在登記簿裡沒有人,但記憶體裡不是原廠值 → 一定是上一次開機留下的
   → `claim` 先寫回 sup 提供的原廠值再登記。journal 記的是**宣告的原廠值**(建卡時從
   `out/MAIN_c0000000.bin` 取),不是記憶體裡的值,所以不會把補丁當原字。= V2 討論過的做法 3。
2. **執行期才改的字**(OG 的模式時序、預覽高度):entry 先 claim,之後任何時候寫,關機都會寫回。
3. **大範圍**(res-lab 約 4,800 字):`claim` 收範圍,journal 存範圍而非逐字。

### veneer

跳板仍是 8 B(ARM `E51FF004`+目標 / Thumb `F000F8DF`+目標),從 `CAVE_BUMP` 要。
**不需要在跳板放魔術字或開機識別碼**:誰是哪一層記在登記簿,不靠從記憶體反推。
uishare 的認法(2026-10-06 已做):仍從 veneer 減入口偏移找到標頭,但標頭 +0 是**檔名**(使用者定:loader 帶進來的檔名,
不是 sup_id),要等於 `holder(點, i)` 列出的某個持有者才算一層(uishare `NESTED_HOOKS.md` §4)。

## 6. cave 最後剩下的

```
0xC072DE64  載入器(+0 load、+4 loader hook 入口),最後一字 CAVE_BUMP
0xC072E064  veneer arena ..0xC072EFB4(每次開機由加載器歸零)
0xC072EFB4  park stub
0xC072F000  USB shell 與主機的交接字(主機要從固定位址找到 worker)
0xC072F6F4  LOAD_START / LOAD_DONE(也當主機端的開機識別)
0xC072F700  store_boot(在配置器可用之前執行)
```

**sup 不再擁有任何固定 cave 位址。** 「cave 邊界」統一一個定義(現在有 4 種說法,見 §9)。

## 7. 待解(實作前)

1. ~~列目錄 API~~ **已找到(離線)**:`dir_ctor 0xC0366918(holder, drive=1)` → `dir_open 0xC0366990(holder, "\\fpSup")` → `dir_next 0xC03669F8(holder, entry[0x238])` → `dir_dtor 0xC0366940(holder, 2)`;檔名 UTF-16 支援長檔名、大小在 +0x210、屬性在 +0x218;順序未排序、子目錄不回 `.`/`..`;**2026-10-06 上機驗證**;要跳過 macOS 的 `._*` 檔。見 [DIR_ENUM_API.md](../../../research/firmware/notes/DIR_ENUM_API.md)。
2. 長檔名韌體支援(entry 是 UTF-16);大小寫規則待定。
3. **SD 卡要明確指定**(插著 SSD 時舊 loader 會去 SSD 找,見記憶 loader-opens-vshl-on-the-ssd)。
4. 每多一個檔的開機成本(開檔 + 讀),要實測。
5. 載入器 ≤468 B 能否塞進「開固定檔名 + 配置 + 讀 + D/I + 呼叫」:現行 loader 已做這些,應可。
6. 加載器本身的 journal / 登記簿格式與關機回呼(沿用 stage2 的 `XC_PowerOffMgr` 兩張清單)。
7. 合併頁面的新角色:挑檔、改檔名前綴排序、檢查 sup_id 重複;不再生成 loader。

## 8. 遷移順序與各 sup 要改的

| # | sup | 要改的 | 估計 |
|---|---|---|---|
| 0 | 載入器 + 加載器 | 新寫;unicorn 驗證(`test_loader_hook.py` 的作法) | — |
| 1 | **USB shell** | pass 1 的描述子補丁 7 字與 STATE 歸零搬進 entry 並 claim(值補丁要能認「已是我的值」);熱抽換改 `reload()`;高速通道現況見 §11 | 小–中 |
| 2 | **lossless** | 檢查移到建任務/裝選單**之前**(現在順序相反);hook 尾端改 `chain_next`;card.S 13 個絕對自指標改 PC 相對;FPLM 從塊讀;clip size 位置 `C05BDDAC` 是取代式 → EXCL;無損引擎 `claim_res` | 中–大 |
| 3 | **gyro** | `BLOBBASE` 等巨集改 PC 相對(約 170 處但集中在巨集);job pool / 檔案物件併進塊;刪 `gsup_launch` 複製與 `0xC3757A7C`;4 個 hook 尾端改 `chain_next`;base/gcsv 用 sup_id 互斥;主機部署工具改從 LOAD.LOG 或交接字找塊 | 中 |
| 4 | **og3k / og2k** | 約 51 個 cave 常數、約 100 處改相對塊;格式表存偏移;UI pack(`0xC0793060`)與狀態進塊;刪 35 個「寫原廠值清殘留」的字;執行期改的 8(og2k V3TAP 11)字先 claim;核心位置 EXCL | 中 |
| 5 | **raw-view** | 約 45 個位置;call-site hook 改 `chain_next`(取代 `ldr pc,=原函式`);值補丁 EXCL;launcher 自我複製拿掉;`stub_sv` 會存設定區(第一守則範圍,要先查) | 中 |

| 6 | **sensor-lab → res-lab** | 改名(約 779 個檔提到 sensor-lab,改名本身另做一次);143 個執行期重定位 → 重寫約 12 個 payload 為 PC 相對;core 與 sl_menu 併成一塊;journal gate 換成 claim;SLMP 從塊讀;約 4,500 字原地 UI 補丁 → EXCL,**維持單卡** | 大 |

使用者 2026-10-06 決定:**§5 claim 機制採用**;**lcdflip 退役**;**screenflip 會重做**(屆時直接照 v3 寫,不遷移舊版);
fc-scale(sigma-fp-lab 的 False Color / EL Zone 第三方卡移植)未排 —— 小工作量,但 STATE 寫死在第三方 `fcscale.S` 7 處,
且現行 `0xC072E080` 錨點與 arena 重疊、hook 未申報。

uishare(函式庫)隨第一個用到它的 sup 一起改:STRBASE 改相對塊、層的認法改查登記簿、格式版本號真的被檢查。
**2026-10-06 狀態**:層的認法 ✅(標頭 v2:檔名 + 版本 2,查登記簿;無 v3 加載器時名字 `FSDL`);版本號 ✅(層的版本在認層與
走串時都檢查,FPUI 版本 `uia_apply` 本來就檢查);**STRBASE 改相對塊 ❌ 沒做** —— OG/res-lab 在 entry 執行期改寫
STRBASE 位址並重算 FPUI 的 FNV(sigmafp-re-d9 的範圍),改了就得動 FPUI 格式與 hash,依賴方要求不動。

## 9. 現況盤點摘要(2026-10-06,讀程式碼)

- **沒有任何現行卡用 pass 2。** 每個 sup 都自己 H_GET class 0,再從 `CAVE_BUMP` 要跳板。
  記憶裡的「r10 = pool+0x6000、0x9000..0x1A000 空隙、PGEN @+0x77000」是舊 r 系列 logger。
- 每個 sup 找自己狀態的方法都不同:寫死 cave 字(OG、fc-scale)、池加固定偏移(gyro)、
  魔術字(uishare、lossless "FLPC")、從 hook 跳板反推(sensor-lab)。
- 常數重複:`CAVE_BUMP` 9 份、arena 結尾 `0xC072EFB4` 十幾份、H_GET 位址約 12 份,大多沒有測試核對。
- 「cave 邊界」四種說法:`0xC0730000`(build_autorun)、`0xC0735000`(stage2 不記 journal 的範圍)、
  `0xC072EFB4`(C/組語)、`0xC072D000..0xC0730000`(頁面)。`0xC072D000..0xC0735000` 內的韌體非零資料不進 journal。
- 撞名:`FRAMEBUF` 在 stage2 = `0xC3757A7C`、在 worker = `0xC072F050`;`POOL_BYTES` 在 loader = 64 KB、在 gyro = 1 MiB。
- 合併器只看靜態區段,看不到執行期配置、bump 用量、MMIO。已知衝突:
  **fc-scale 的 `0xC072E080` 在 arena 裡,會被 gyro 的跳板蓋掉**;screenflip 與 lcdflip 同寫 `0x30190044`;
  lossless 現行原始碼與 OG3K 同改 `0xC05E5B58`(出貨版 lossless 沒宣告,暫無影響)。
- 小 bug:`fpSup/fp_usb_shell/inject.py` 用了 `re.search` 但沒 `import re`;多處註解過期
  (`stage2.S:76-78`、`build_catalogue.py:40-45`、`store_boot.S:98-99`、`worker.S:55-62`、`template.html:776-781`)。

## 10. 可行性結論(2026-10-06)

全部 sup 都能改,**沒有 sup 本身的硬障礙**;§5 的 claim/kind 就是為了補三路檢查共同撞到的五個缺口:
過期層修復、合作式值補丁(uishare)、語意互斥、執行期改的字與大範圍 journal、非 hook 資源。

## 11. USB shell 高速通道現況

2026-10-06 讀程式碼與筆記,**沒有新的上機量測**。端點只有 EP01 OUT、EP82 IN、EP83 IN;**EP84 與 EP05 不存在**。
UP01 與 EP83 的程式在 fpSup 裡**尚未 commit**(HEAD 7709b25)。

**相機 → 主機(下行)**

| 路徑 | 狀態 | 速度 | 備註 |
|---|---|---|---|
| EP82 回覆,TRB 直指來源(`read_direct`/`dumpdirect.S`、`getfile.py`) | ✅ 實作、上機驗過(2026-08-27) | **73 MB/s**(1 MB/次最快);31 MB 檔 1.17 s | 2 MB 以上變慢(4 MB 9.5、16 MB 2.1 MB/s),原因未明;疑似單次超過相機 `TIMEOUT_IN=300 ms`(假說)。來源必須是 DMA 可達的堆積,不能是映像 |
| `read_bulk`/`dumpraw.S`(經 16 KiB 暫存) | ✅ 驗證用、讀韌體映像用 | 約 2.7 MB/s | — |
| EP83 bulk 推送 | ⚠ 主機端已在 fpshd 3.1.0;相機端只有離線的 332 B 單次 sender | — | **從未在 EP83 收到過任何資料**;缺:韌體 PTP 事件 sender 會寫同一個 TRB、等待完成不重新 arm EP01、自己的 USER 記憶體、不在 hook 裡送 |
| EP84 hook-push / BATCHPUSH / RAWGRAB | ❌ 舊 gadget 才有,現行不能用 | — | RAWGRAB 會弄當相機 |

**主機 → 相機(上行)**

| 路徑 | 狀態 | 速度 | 備註 |
|---|---|---|---|
| UP01(EP01 二進位上傳,`PUT`/`UCAPS`) | ✅ 上機成功(2026-10-04,441 KB 的 fpSup.BIN),**沒寫進任何筆記** | **約 0.1 MiB/s** | 比下行慢約 600 倍,原因未查;候選:每次 PUT 前多一趟 UCAPS、每塊開新 socket、相機端逐位元 CRC 讀非快取區 |
| 舊 bulkload(echo 240 B/指令) | 退路 | 65–70 KiB/s | 2026-10-04 r80 部署時 `bulkload cursor unavailable` |
| EP05 / 第二個 bulk-OUT | ❌ 不存在 | — | — |

上限:上傳暫存在 worker 池 +0x10000..1 MiB,`MAX_UPLOAD` = 982,016 B。

**跟 v3 有關的固定位址**:worker 本體與池**已經是堆積、位置無關**。固定的只剩 `0xC072F000..F058` 交接字,以及主機寫死的池內佈局:
+0x2000 擷取、+0x6900 上傳 tuple、+0x10000 暫存。`dumpdirect.S` 的 `CAP_PTR/CAP_LEN` 是寫死常數;
所有借 echo 的小程式都靠 `cave.claim`(arena + `LOAD_DONE_US` 當開機識別),所以 **v3 的 arena 與交接字必須保持相容**。

**已知問題**:getfile 與 putfile 共用池 +0x10000(TODO 第 1 項未做);`getfile.S` 用 class 10,和 CinemaDNG 幀緩衝撞 class;
`read_direct` 沒有位址標籤,分不出過期回覆;文件過期(`TRANSFER.md`、fpSup skill 仍寫 UP01 未上機;
fp-camera-control §11 說 daemon 沒有 EP83,但磁碟上的 binary 已經有了)。

## 12. 要改的契約(`fpSup/SUP_BUILD_RULES.md` 中英兩份)

- §1.3「保留兩個 pass 與既有 entry ABI」→ 改為 §4 的 entry 契約(r0 塊基底、r1 服務表、回傳 KEEP/RELEASE)。
- §1.5「不做跨 sup 失敗交易」→ 不是交易:sup 在寫任何東西之前自己放棄,加載器只丟登記、釋放塊。
- §3 載入順序、§3 的 `0x40000000` 表、§5 Fast「只換 BIN」→ 改為「只換 `fpSup/` 裡的檔」。
- §4「卡片改過的每個韌體字由 loader 關機寫回」保留,改成經 `claim`;原廠值由 sup 宣告。

## 13. 實作進度

### 第 0 步:載入器 + 加載器(2026-10-06,離線通過,未上機)

程式在 `fpSup/fp_usb_shell/v3/`:

| 檔案 | 內容 |
|---|---|
| `sloader.h` | sup 標頭 `FSB1`(32 B)、entry 契約、`claim` 種類與回傳碼、服務表 `struct sl_svc` |
| `sloader.c` | 加載器本體(Thumb C,`-fropi`,無重定位、無全域、無字串常數),約 4.7 KB |
| `sloader_entry.S` | ARM 入口 + 關機寫回程式(與 stage2 `lh_unhook` 同一段)+ 兩個字串 |
| `build_v3.py` | 編 LOADER.BIN(0 區段的 VBIN,程式在 +16)、用 `build_autorun.py --loader` 產生 AutoRun(只改路徑)、`make_sup()` 打包 sup |
| `test_v3.py` / `test_sup.S` | unicorn:真的 loader.S + 真的 LOADER.BIN + 真的韌體映像;檔案/目錄/配置器/關機管理用 Python |

**載入器(第 0 層)沒有新寫**:就是現在的 `loader.S`,路徑改成 `\fpSup\LOADER.BIN`(316 → 324 B,仍 ≤ 468)。
它本來就做「開固定檔 → 讀 → 驗 VBIN → 跳 +16」,所以 Fast Start 的設定區副本與 loader hook 入口都不受影響。

**加載器**:先把自己整份複製進一塊 class 0 堆積(staging 會被釋放),在那裡繼續:
重設 `CAVE_BUMP` → 配 journal(32 KiB)→ 兩張關機清單都註冊成功才往下 → 列 `\fpSup`(drive 1)→
濾掉目錄、隱藏檔、`.` 開頭(含 `._*`)、非 `.BIN`、自己 → 依檔名(不分大小寫)排序 →
逐一:讀標頭驗證 → 配 `block_size` → 整檔讀進塊 → 尾端清零 → D/I → `entry(塊, 服務表)` →
RELEASE 就把它第一次 claim 的範圍寫回原廠值、截斷 journal、丟掉 claim、釋放塊 → 最後寫 `LOAD_DONE_US`。

**測試**:13 項通過;15 個 mutation 抓到 14 個,沒抓到的「journal 記記憶體而非原廠值」是等價變異
(修復先把原廠值寫回記憶體,之後兩者相同)。共用鏈 `test_boot_chain test_loader_hook test_splash` 29 項仍通過;
`gyro/test_safety` 沒有新增違規(剩下 3 筆 arena 位址是本次之前就有的:lossless `card_status.py`、
`test_card_emulation.py`、uishare `test_ui_apply.py`)。

### 第 1 步:USB shell 當 sup + 載入動畫搬進 `\fpSup\UI\`(2026-10-06,離線通過,未上機)

- **`patch_sup.S` + `build_v3.patch_sup()`**:通用的「補丁型 sup」—— 表列 {位址, 新位元組, 種類},原廠值 build 時從
  `out/MAIN_c0000000.bin` 取;entry 先全部 claim、任一被拒就 RELEASE 不寫;全過才寫、publish,最後才呼叫內層 entry
  (會做不可撤銷的事,例如建任務)。OG 之後也走這個。
- **`build_v3.shell_sup()` → `00SHELL.BIN`(2,820 B,id `SHEL`)**:列 = worker 的 96 B 交接區(`STATE`,清零,EXCL)
  + `patches.IFACE`(EXCL;`PUSH` 六字可選)→ 內層 = `worker.S` 原樣的 `spawn`。
  過去 pass 1 做的兩件事(清 STATE、改介面)變成 claim;暖開機殘留的 `'VSHL'` 由 claim 的修復清掉。
- **載入動畫**:檔案改放 `\fpSup\UI\0..4.BIN`(子資料夾,加載器的列舉會跳過)。AutoRun 照舊畫第 0~3 格;
  第 4 格 + 停 2 秒 + 恢復重繪由加載器在 `LOAD_DONE_US` 之後呼叫同一份 `splash_finish.S`(原本是 stage2 做)。
  共用程式只加參數:`boot_splash.FourBoxBar(asset_dir)`、`build_autorun.py --splash-dir`、`splash_finish.S` 的
  `SPLASH_PATH`;**預設建置逐位元組不變**(plain / Fast / shell 三種卡 21 個檔 sha256 相同)。
- **測試**:`v3.test_v3` 17 項通過(新增:shell 清掉殘留 `'VSHL'`、改介面、建任務、關機還原;介面字被別人 EXCL 時
  shell 退出不寫不建任務;AutoRun 畫 `\fpSup\UI\`;第 4 格在載入完成之後、重繪恢復)。mutation 19 個抓到 18 個
  (剩下的是同一個等價變異)。共用鏈 29 項仍通過;`test_safety` 無新增違規。
- **卡**:`projects/usb-shell-sup/cards/20261006-v3-step1-shell/`(`MANIFEST.sha256`)。

### 第 1 步上機(2026-10-06)

卡 `cards/20261006-v3-step1-shell/`,經 shell 寫卡並逐檔讀回比對;之後經讀卡機更新 `LOADER.BIN` 兩次(加 `LOAD.LOG`)。

| 開機 | 結果 |
|---|---|
| 1(冷開機,舊 LOADER.BIN 無 log) | 畫面正常;插 USB 後介面 `06/01/01`,我判成 shell 沒起來。**很可能是誤判**:當時只看了 `lsdesc`、用的是失效的舊 daemon,沒有真的跟相機說話;之後一次暖開機 `lsdesc` 也是 `06/01/01` 但 shell 正常回應 —— 介面類別不能當 shell 起沒起來的判準 |
| 2(不插 USB) | `LOAD.LOG`:3.65 s 進加載器、列出 1 個、`00SHELL.BIN` KEEP、完成 1/1;`._LOADER.BIN` 被略過 |
| 3(暖開機,動畫後插 USB) | 介面 `ff/ff/ff`,**shell 正常回應**;worker 任務 `0x79` 在跑;`LOAD_DONE_US` 2.64 s;log 記到 **修復 STATE 96 B**(上一次開機留下的 `'VSHL'`),sup 回傳後 STATE = `'VSHL'`、介面字 = `0xFFFFFF03` |

**UP01 加速(2026-10-06):** 慢的原因是 worker 自己的逐位元 CRC(從堆積執行,9 µs/byte,每塊 150 ms)。
改成呼叫韌體的查表 crc32(`0xC06AE998`,與 zlib 相同,0.6 µs/byte)後每塊 16,320 B 從 151 ms → 13 ms,
上傳本身 1.7 MiB/s。`test_worker_upload` 原本被過時的版本守衛全部跳過,現在映射韌體 crc32 真的跑(4 項通過)。
**下行加速(2026-10-06):** 16 MiB 一次 EP82 讀取 75 → **355.7 MB/s**(8/8 成功、內容與舊路徑相同)。拆解:
USB IN 本身一直很快(daemon 量 16.77 MB / 45 ms ≈ 372 MB/s);慢的是主機端。
1. daemon 把原始資料轉十六進位、Python 用 `+=` 拼接(平方成長)→ 新 `RAW` 指令直接回原始 bytes:75 → 253 MB/s。
2. 寫 16 MB 進 socket 要 ~20 ms,與 USB 傳輸串行 → 新 `RAWSHM <n> /<shm> <指令>`:libusb 直接讀進
   Python 建的 POSIX 共享記憶體,socket 只回 `OKS <n>` → 355.7 MB/s。`putfile.read_direct` 已改用它。
3. EP01/EP82 的 bMaxBurst 3 → 15(`patches.BURST15`,shell sup `burst15=True`):Mac 看到 burst=15、shell 正常,
   但速度只多約 10%,不是主要瓶頸。
`read_direct` 每次呼叫還有 ~85 ms 固定成本(借/還 echo 槽與讀回),大檔才看得到 355 MB/s。
daemon 的 `FPSHD_TIMING=1` 會印每次 IN 的時間。上行仍是 UP01(1.7 MiB/s);要 350 MB/s 需要 worker
讓 OUT 的 TRB 直接指向目的地(不經 CPU 複製與 CRC),檢查改由主機用下行讀回比對。

**剩下的問題**:原廠 PTP 任務偶爾吃掉 EP01 的 OUT(回 12 B `0x2003`),worker 空等 50 s ——
見 `research/interfaces/notes/FP_USB_PTP_SHARED_PATH_2026-09-16.md` 補充。

**高速通道在 v3 shell 上(2026-10-06,開機 3 之後):**

| 路徑 | 結果 |
|---|---|
| EP82 直讀(`read_direct`,worker 池 1 MiB) | 傳輸本身 59 MB/s(0.02 s);第一次呼叫含上傳 `dumpdirect` 小程式,共 0.34 s;再讀 256 KiB 0.01 s |
| `getfile`(卡 → 記憶體 → EP82,`\fpSup\UI\0.BIN` 112 KiB) | 1.37 s / 1.14 s,兩次都與本機檔案逐位元組相同;時間是固定開銷(與 31 MB 1.17 s 一致) |
| UP01 上傳(`put(..., fast=True)` 到池 +0x10000,256 KiB) | 96 KiB/s(0.1 MiB/s,與 10-04 相同),put 的讀回 0 字修補,EP82 讀回逐位元組相同 |
| EP83 | 未測:相機端 sender 仍未實作;這張卡沒帶 `PUSH` 補丁,EP83 仍是 interrupt |

結論:worker 的交接字、`cave.claim`、`LOAD_DONE_US` 開機識別在 v3 下都照舊可用,主機工具不用改。

使用者觀察:三次開機畫面都正常(四格動畫、最後恢復)。log 存在卡片資料夾 `LOAD-boot1.LOG`、`LOAD-boot2.LOG`。

`LOAD.LOG` 格式:每行 `碼 a b 名稱`。碼:01 START(a=開機 µs)、03 略過、0A 載入(a=塊、b=大小)、0B 釋放、
0C 修復(a=位址、b=長度)、0E 完成(a=保留數)、10 衝突、11 列出數、12 claim 寫完後的第一個字(a=位址、b=值)。

**還沒做(依序)**:
1. 開機 1 的失敗原因(若再出現,先讀 `LOAD.LOG`)。
2. Fast Start 3 的部分:loader hook 安裝(`0xC03DA420`)、設定區 provision、AutoRun abort、四格畫面 —— 目前加載器都不做,暖開機會走 AutoRun。
3. `LOAD.LOG` 寫檔(現在 log 只在 RAM;主機要找到它需要一個根指標,位址待定)。
4. `reload(name)`(shell 熱抽換用)。
5. journal 固定 32 KiB,滿了 claim 回 `SL_FULL`;res-lab 若超過再改成串接。

### 第 2 步:lossless 當 sup(2026-10-06,離線通過,未上機)

接手 sigmafp-re-c6 的半成品(`menu_page.c` 的 `fpl_menu_install_data`、`card.c` 的 `FPL_MENU_OFF`、
`patch_sup` 的 `'claim'`/`'res'` 兩種列)。沒有走「patch_sup 外包舊啟動器」的路:那樣啟動器仍會自己 H_GET
一塊 512 KiB 再複製,違反「一個 sup 一塊」。改成 `native/card.S` 的 `V3=1` 入口,**shim 完全共用**。

| §8 的項目 | 做法 |
|---|---|
| 檢查移到建任務/選單之前 | entry 順序:13 個 claim + `claim_res(0x300D0000, EXCL)` → 檢查下層 → `cave_alloc(96)` → 才呼叫 init(建 codec 任務、裝選單列)→ 寫 veneer 與 site。init 之前任何拒絕都回 RELEASE,什麼都沒寫、沒建任務 |
| hook 尾端 `chain_next` | 呼叫點 FLUSH/DISCARD:`flush_real`/`discard_real` = `chain_next`(原廠時就是原函式)。插入點 STOP/END/POOL/EVENT(`b`)與 PLAY(`bl`):site 不是原廠 → 必須是同一種分支(否則 RELEASE),shim 的重放指令改寫成 `ldr pc, <下層>`。**REC 例外**:C 自己呼叫 `C03A2438`,下層不是原廠就 RELEASE。外層 sup 疊在我們上面不受限 |
| card.S 自指標 | V3 不複製:`r11 = 0`、`r5 = adr entry`,`RESIDENT` 巨集照用;`w_*` 在 entry 執行期由 PC 算出(§3 允許) |
| FPLM 從塊讀 | FPUI 區塊(30,844 B,不補零)接在 C text 之後,`FPL_MENU_OFF` 編進 C;迭代到 text 長度穩定 |
| C05BDDAC | EXCL;ARRIVE(`blx r3` 不是分支)也 EXCL;uishare 三個字串層 SHARED_UI;其餘 CHAIN |
| 無損引擎 | `claim_res(0x300D0000, EXCL)` |

- **檔案**:`fpSup/lossless/build_v3_lossless.py` → `10LOSS.BIN`(id `LOSS`,檔 65 KB、塊 236 KiB;舊版 512 KiB
  多出來的是讀 `fpSup.BIN` 用的選單區,`uia_apply` 自己配記憶體,不需要)。claims 表從組好的位元組讀回,
  逐列對 `out/seg0`(hash 固定)與 `out/MAIN` 兩份映像的原廠字、對 `build_card.SITES`、對預定的 kind。
- **舊版逐位元組不變**:`build_card.py` 的 AutoRun / fpSup.BIN / lossless.bin / layout.json sha256 與改前相同。
- **測試** `fpSup/lossless/test_v3_lossless.py`(真 loader.S + 真 LOADER.BIN + 真 10LOSS.BIN):18 項通過 ——
  全部 site 進 journal 且原廠值正確、kind 正確、veneer→shim 在塊內、FLPC 紀錄、任務入口 = 塊內 `task_shim`;
  關機全部寫回;殘留修復後照常 arm;CLIP/ARRIVE/SHARED_UI 被別人持有、FLUSH 被 EXCL、引擎被佔、cave 滿、
  REC 有下層、插入點分支形式不符 → RELEASE 且**沒建任務、沒拿 cave、site 全原廠**;下層存在時呼叫點/插入點接到下層,
  STOP 實跑一次確認暫存器、lr、sp 原樣到下層;外層可 CHAIN 疊上來。mutation 8/8 抓到(另有 2 個 mutation 測試在檔內)。
  既有 `test_card_emulation` 25、`tests/` 76、`v3.test_v3`+共用鏈 48 仍通過;`test_safety` 沒有新增違規。
- **cave 位置變了**:`cave_alloc` 對齊 8,塊在 `0xC072E068`(舊版 `…E064`);`card_status.py` 是掃描 FLPC,不受影響。
- **卡**:`projects/usb-shell-sup/cards/20261006-v3-step2-lossless/`(`MANIFEST.sha256`)。`00SHELL.BIN` 是第 1 步卡上
  那份(sha `480bf2e1…`,相機上現在的);**`--card` 會從目前的 `worker.S` 重建 shell**,f8 正在改它,所以卡裡換回舊的。
  上機只需要多放 `fpSup/10LOSS.BIN`:`deploy_v3.py CARD --only fpSup/10LOSS.BIN`。

**上機(2026-10-06)**:載入、選單列、壓縮都正常;順帶找到並修好既有的「FHD 開錄 94 幀就停」
(檔案層批次大小,`0xC0B9E5D8` 加進 claims,見 `projects/lossless-sup/notes/EARLY_STOP_94.md`)。
卡片目錄的 `10LOSS.BIN` 已換成修正版。

**還沒做**:選單列在 emulation 裡沒裝
(映像 RAM 沒有 GUI 物件,停在第一個檢查);REC 的真 chain(要把 `C03A2438` 改成從 state 讀);
`test_safety` 那 3 筆舊的 arena 位址。

### 第 4 步:OG3K / OG2K 當 sup(2026-10-06,離線通過,未上機)

使用者選 §8 完整版(不是 patch_sup 外包):OpenGate **不再擁有任何固定 cave 位址**。
程式在 `projects/open-gate/build/`:`og_pic.inc`、`og_v3.c`、`build_v3_og.py`、`test_v3_og.py`。

**做法:cave 當座標系,不搬程式碼。** AutoRun 卡寫進 `0xC0730000..0xC0735000` 與私有 NBR pack(`0xC0793060`)的
每一個字,原樣放進塊裡的「layout image」相同相對位置(cave 在 +0、pack 在 +0x5000)。payload 原始碼只改三件事:

| | 改法 |
|---|---|
| cave 位址的 `.equ` | 包成 `OGA(...)`(44 個)、pack 包成 `OGP(...)`(1 個),機械替換 |
| `LDA` / `addr` 巨集 | `OG_V3` 時交給 `OGLDA`:目標在 layout 內 → `movw/movt 差值 + add pc`;其餘照舊絕對 |
| og3k_ui 的 `self` | `OG_V3` 時 `.word label - (. + 8)` + `add pc` |

沒有 `OG_V3` 時一個位元組都不變:`OG_UISHARE=1 build_og3k_gyro.py --no-gyro --release` 的 og3k、og2k
`fpSup.BIN` 與 `AutoRun.txt` 改前改後 `cmp` 相同。靜態檢查讀原始碼的地方改走 `og3k_plan._source()`(把 OGA/OGP 拆掉)。
字數絆線在 v3 下 = 原數 + PC 相對載入數(每個 payload 的成長必須剛好等於它的 `add rd, pc, rd` 數)。

**PIC 證明**:整個 layout 在另一個原點(`OG_V3_OGV=0x10000000`,子行程)再組一次,必須逐位元組相同。
mutation(把 OGLDA 全改絕對)→ 建置拒絕,指出第一個不同的位址。

**檔案**:`30OG3K.BIN`(35,096 B,塊 35,200 B,id `OG3K`)、`30OG2K.BIN`(36,068 B,id `OG2K`)。
`[FSB1][og_v3.c + uishare 的 ui_pool/ui_apply,一個 unit,-fropi][og_tab + 列][layout image][FPUI]`。

| entry 順序(og_v3.c) | 內容 |
|---|---|
| 1 claim | 17 個 hook 點 EXCL;執行期會改的韌體字 EXCL 只登記:GTAB 六個預覽高、donor 時序記錄(OG3K:mode 98 **與 117**,OG3K100 用 117;OG2K:139);uishare 的 4 個站點 SHARED_UI |
| 2 cave | 17 個 veneer 先全部要到 |
| 3 fixup | 格式表 8 個 key 指標 + FPUI 的 4 個 STRBASE 位址(之後重算 FPUI 的 FNV) |
| 4 UI | `uia_apply`(解析度列與標籤);**失敗 → RELEASE**(AutoRun 卡是照樣繼續、只少選單列) |
| 5–7 | 值補丁(UISHARE 下沒有)→ 寫 veneer、publish → 照 AutoRun 卡的順序寫 hook(picker 是 OG 最後一個,之後 UI 的三個 Thumb B.W)→ publish |
| 8 | 呼叫 og3krestore(原本是 VSHL entry) |

**拿掉的**:34 個「把原廠值寫回已不用的 hook 點」的字(RWZM 32、範圍檢查、回放 hook)—— claim 的修復取代它們。
**新增的保護**:mode 117 的時序記錄過去從不還原,現在關機寫回。

**測試** `test_v3_og.py`(真 loader.S + 真 LOADER.BIN + 真 30OG*.BIN):14 項通過 —— 兩個目標都載入、journal = 原廠、
每個 hook 經 cave veneer 到塊內正確位置(Thumb 的實際跑一次確認進 Thumb)、格式表 key 指標指向塊內、FPUI 重算 hash
且 STRBASE 指向塊內 alias 表(最後寫 word 0)、restore 只跑一次且在 hook 之後;**透過 hook 點實跑 picker 與 setter**
(找到 OG3K30、寫 donor 時序、GTAB 切換、FLAG 發布、FMTLATCH 未知時不生效);關機全部寫回;殘留修復;
hook 點 / 執行期字被別人持有、UI 被拒、cave 不夠 → RELEASE 且什麼都沒寫;OG2K+OG3K 同卡只載第一個(OG2K);
lossless + OG3K 同卡兩個都載入。stub 了兩樣並說明:`uia_apply`(映像 RAM 沒有 GUI 物件)與 og3krestore(問韌體設定物件)。
mutation 11/11 抓到。

**卡**:`projects/usb-shell-sup/cards/20261006-v3-step4-og3k/`、`…-og2k/`(`MANIFEST.sha256`);
LOADER/AutoRun/UI/00SHELL/10LOSS 從第 2 步卡逐位元組複製。上機只需要多放一個檔:
`deploy_v3.py CARD --only fpSup/30OG3K.BIN`(OG2K 同理;兩個同時放只會載入 OG2K)。

**還沒做**:上機;Fast Start 3 下 GUI 尚未就緒時 `uia_apply` 會失敗 → OG 整個不載入(待上機確認時機);
hsw / POOLDEPTH / 非 UISHARE 組態 v3 未驗證(builder 只接 og3k/og2k)。

### 第 5 步:raw-view 當 sup(2026-10-06,離線通過,未上機)

`projects/rawview/build/build_v3_rawview.py` → `\fpSup\45RAWV.BIN`(id `RAWV`,min_svc 2,檔 38,412 B、塊 0x8D000)。
**前綴 45**:40 是 screenflip、50 是 res-lab(順序 raw-view 在 res-lab 之前)。同一份 `rv_launch.S` / `rv_resident.S`,以 `V3=1` 組譯;
**舊 AutoRun 卡逐位元組不變**(`build_rawview.py` dev/release 的 AutoRun、fpSup.BIN、rawview.bin sha 與改前相同)。

```
[FSB1 32][設定區 32][rv_launch][rv_resident][表格資料][uishare UI 段落][claims 表]   + 清零尾端 = T0 區(4 KiB 對齊、0x82000)
```

| §8 的項目 | 做法 |
|---|---|
| launcher 自我複製 / H_GET | 拿掉。T0 = 塊內檔案之後第一個 4 KiB 邊界;表、插槽、常駐(仍放 T0+0x3E200,主機工具經 site A 找 `RVW1` 照舊)、矩陣副本都在自己的塊裡 |
| claim 先於一切 | entry 先 claim 40 筆,再跑舊的 GUARD(claim 已把殘留修回原廠);chain_next、`cave_alloc`(19 個 veneer)、`uia_apply`(RAW 列)任一失敗 → RELEASE,**韌體一個字都沒寫** |
| 種類 | CHAIN:三個「只是轉手」的呼叫點 —— 關機存檔 `C0088C60`(res-lab 也掛這裡)、畫質指令 `C02B8E64`、關鍵影格圖名 `C05E2200`(Thumb);常駐的 `sv_next/pq_next/ai_next` = `chain_next`。SHARED_UI:uishare 的 `C05E5BEC`。其餘 EXCL |
| 只有 `--legacy-ui` 才寫的位置 | H1 與 8 個頁面字不 claim(uishare 做);ADV `C1D6ED48` 照舊原地寫、EXCL |
| UI 段落 | 不再是第二個 boot-bin:段落整個放進塊裡,entry 直接呼叫其中的 `uia_apply`,失敗就 RELEASE |

**使用者設定存在自己的 BIN(使用者 2026-10-06 指定)**:
- 設定區 = 檔案 +32 的 32 B `{'RVS1', flag, lat, con, sat, 0, 0, 0}`,建置時全 0。
- 舊版 `stub_sv` 在關機存檔時把原廠色彩改成 `0x10–0x17` 存進相機設定區(拔卡後相機留著一個不認得的色彩值)——**拿掉了**,
  原廠設定區一個字都不改。`stub_sv` 現在:先呼叫下一層(原廠存檔照舊)→ 第 0 組才看 →
  flag = RAW 開著且紀錄的色彩是 OFF → 跟塊裡的設定區比,**有變才寫卡**:open 7 → seek 32 → 寫 32 B → seek → 讀回比對
  (同 lossless 的原地改寫;seek 失敗不寫,免得蓋到檔頭)。沒寫成就把塊裡的 magic 清掉,下次關機重寫。
- 開機:設定區 flag 開**且工作設定的色彩仍是 OFF** → 還原 lat/con/sat(sat 超過 SAT_MAX 當 0),經 setter 設 OFF + pend 17(同舊版)。
  色彩不是 OFF(沒插卡時改過)→ 不還原。
- 遷移:工作設定仍是舊卡留下的 `0x10–0x17` → 照舊版解碼還原一次,setter 寫回 `0xC`,殘留就清掉了。
- 順帶:舊版只存了飽和度的 bit 0;新版存整個值(目前 SAT_MAX = 1,所以沒差)。

**寫卡時機是關機存檔(`FUN_c0088bb0` 內),未上機驗證**:那時 SD 是否仍可寫、會不會拖慢關機,只有實機能回答。
備案是 lossless 的做法(自己的任務在閒置時寫),raw-view 目前沒有任務。

**測試** `projects/rawview/build/test_v3_rawview.py`(真 loader.S + 真 LOADER.BIN + 真 45RAWV.BIN,MAIN + .data 映像):
載入、claims 與 journal、hook→veneer→塊內 stub、三個 *_next;**整個 48 MB 映像比對:改過的韌體字全部在 claims 內**;
關機全部寫回;殘留修復;下層 CHAIN 接上;EXCL/CHAIN/UI 位置被佔、`uia_apply` 失敗 → RELEASE 且沒寫;
`stub_sv`(對齊的 sp,同真正呼叫者 push 4 + sub 16):寫進自己檔案、檔頭與其餘不變、沒變不寫、自訂組不寫、色彩非 OFF 記 0、
seek 失敗不寫且下次重寫、寫入沒生效下次重寫;存下的紀錄下次開機還原;色彩變了不還原;sat 超範圍;舊 0x1x 遷移。
mutation 13/13(先抓到 2 個測試太弱,已加強)。
UI 列本身在 emulation 裡沒裝(映像沒有 GUI 物件,`uia_apply` 由測試回答),同 lossless。

**卡** `projects/usb-shell-sup/cards/20261006-v3-step5-rawview/`(`MANIFEST.sha256`):AutoRun、UI 動畫、00SHELL、10LOSS 取自第 4 步卡,
**LOADER.BIN 是目前建的(svc v3,`f53ece67…`)**;45RAWV `56584fb7…`(uishare 2026-10-06 23:28 定版,連建兩次相同) —— 第 4 步卡的舊 LOADER.BIN 會把 45RAWV 判成 BAD_HEADER(min_svc 2)。
emulation 裡用這張卡的 LOADER + shell + lossless + 45RAWV:三個都 LOADED;加 30OG3K 時 OG3K 不論有沒有 raw-view 都 RELEASE
(它的 UI 在 emulation 裡裝不了),不是衝突。OG3K/OG2K 與 raw-view 唯一重疊的位置是 uishare 的 `C05E5BEC`(兩邊都 SHARED_UI);
lossless、res-lab 沒有重疊。

**第 5 步上機(2026-10-07 01:35–01:41)**:經 `deploy_v3.py --only` 寫 LOADER.BIN(目前的 sloader.c,含 d9 的 holder 修正,
7,260 B,`41f3218a…`)與 45RAWV.BIN(`56584fb7…`),讀回逐位元組相同;舊 LOADER.BIN 與 LOAD.LOG 備份在卡片資料夾 `backup-before/`。

| 步驟 | 結果 |
|---|---|
| 重開(shell,12.3 s) | `LOAD-boot1.LOG`:00SHELL、10LOSS、20GYR2、30OG3K、40FLIP、45RAWV 六個 LOADED,沒有 CONFLICT/REPAIRED |
| 讀記憶體 | site A → cave veneer → 塊內常駐(`RVW1`);`sv/pq/ai_next` = 原廠 `C0088660 / C02B97A8 / C05D6BB9`;路徑 `\fpSup\45RAWV.BIN` |
| COLOR 鍵 → LEFT | 清單最後一項 RAW、預覽變平坦、右框 SA;UP → GA;OK 確定 → flag 1、eff 1、lat 1、相機色彩 0xC |
| `menu save`(與關機存檔同一個 `FUN_c0088bb0`) | 塊內與卡上設定區 = `{RVS1, 1, 1, 0, 0…}`;檔頭與其餘 38,348 B 不變;**相機色彩仍 0xC(不再寫 0x1x)** |
| 重開(11.8 s) | `LOAD-boot2.LOG` 六個 LOADED;flag 1、eff 1、lat 1(GA)還原,預覽是 RAW 平坦畫面 |
| COLOR → RIGHT 到 STD、OK、`menu save` | 第一次 `menu save` USB 逾時(指令沒送到);重送後卡上設定區 flag 0;相機回到 STD |

**未驗**:真的撥電源開關關機時寫卡(會不會拖慢關機、SD 是否仍可寫)—— shell 測不到,要使用者撥一次開關;
錄影的 DNG(ColorMatrix、tone)沒有重錄比對(那部分程式與 AutoRun 卡相同)。

**發布草稿(2026-10-07,未 commit)**:`fpSup/releases/fpsup-raw-view-v0.3.0test/`(sigmafp-re-5e 用 `tools/release_v3.py raw-view 0.3.0test` 建,
README/ABOUT 由 raw-view 補)。45RAWV `701532fe…` = 目前原始碼;與上機版 `56584fb7…` 只差 uishare `qs_layer.c`(10-07 09:20)的兩個
movw 立即數;test_v3_rawview 18 項對這份通過。**這份位元組未上機。**

### 服務表 v2:entry 的 r2 = 自己的檔案路徑(2026-10-06)

`sloader.c`:`struct sup` 多一個常駐的 `path`,呼叫 `entry(block, svc, path)`;`SL_SVC_VERSION` = 2。
其他 sup 不看 r2,`min_svc` 維持 1,行為不變。需要 r2 的 sup 宣告 `min_svc = 2`,舊加載器就不會載入它。
用途:sup 寫回自己的檔案(lossless 保存 ON/OFF),檔名被合併頁改了前綴也找得到自己。
測試 `v3.test_v3.test_each_sup_is_told_its_own_path`(兩個 sup、其中一個改了名,r2 都正確且在常駐區)。
**部署時 `LOADER.BIN` 要跟 lossless 一起換。**

### lossless 保存 ON/OFF(2026-10-06 上機通過)

- 紀錄在 `10LOSS.BIN` 自己的檔案裡:card.S `settings` 16 B {`FLST`, 1, 0/1, 校驗},建置時為 OFF。
- 開機:init 從塊裡讀紀錄,當成選單變數(值與彈出清單的暫存值)的初值。紀錄壞掉就當 OFF,也不存檔。
- 存檔:codec 任務閒置時,如果值跟紀錄不同、連續 1 秒,而且 3 秒內沒有 REC、沒有幀到達、原廠錄影旗標
  (指標 `*(0xC375896C)` 在 status 表建立之前是 0)不是錄影中,就開檔(mode 7)→ seek → 寫 16 B → 讀回比對。
- 上機:ON 存進去,卡上檔案只差 2 個位元組;重開機選單顯示開啟、彈出清單游標在開啟;改 OFF 也存得進去;
  ON 之後的錄影 380 幀全部壓縮。不碰相機設定區。
- 「切換後 1 秒內就按 REC」的邊界沒有精準重現。

**已知、刻意不修(使用者 2026-10-06 決定):** `test_res_lab_cave_audit` 的 debug 卡超過舊 loader 的 `MAXLEN 0xF000`
(62,736 B,多 1,296 B;起因是 worker.S 加了 UP01/MEM1,shell 2,820 → 4,552 B)。那是舊的單檔卡;**不要為 res-lab
調高舊 loader 的讀取上限**,第 6 步改成 v3 之後這個限制就不存在了。在那之前這個測試維持失敗。

**第 4 步上機(2026-10-06 18:03,OG3K)**:卡上 00SHELL + 10LOSS(ON)+ 20GYR2(gyro 探針)+ 30OG3K,`ui_drive.py reboot`
後 11.4 s 回來。`LOAD.LOG`(存在卡片資料夾 `LOAD-boot1.LOG`):四個都 LOADED、沒有 CONFLICT/REPAIRED;OG3K 塊在
`0x451BAFC0`,17 個 hook 都已寫入;預覽高 0x536、donor 時序 `02DF01BD` = og3krestore 依存檔重選了 OG3K。字串層三點是
lossless 之後疊上 OG3K。`menu SetMovRecSize` = 4、格式 0;截圖 3:2 滿版。錄 `A001_035`(OG3K + lossless ON,rec log-on)
約 231 幀 / 7.7 s,收尾請求數 = 完成數,沒停錄。
**未驗**:DNG 尺寸(沒讀檔)、關機寫回(要讀記憶體)、OG2K。

### screenflip 照 v3 重寫(2026-10-06,離線通過,未上機)

`fpSup/screenflip/`(README 有全部細節)→ `\fpSup\40FLIP.BIN`(id `FLIP`,min_svc 2,檔 22.8 KB、塊 28 KiB)。
不改任何韌體字:只 `claim_res` 面板暫存器 `0x30190044` 與觸控旗標 `0xC3760E44`(EXCL,被佔就 RELEASE);
journal 空。行為改成**每個顯示模式各一值、切進該模式才套用**(sup 自己的任務輪詢 `C0061BA8` 等,依據
`research/firmware/notes/DISPLAY_MODE_SWITCH.md`);表存在自己 BIN 的 `settings` 20 B(同 lossless 的原地改寫)。
測試 `screenflip/test_v3_flip.py` 12 項、mutation 14/14;卡 `projects/screenflip/cards/20261006-v3/`(不含 shell)。

### 第 6 步:res-lab(Sensor Lab)當 sup

**2026-10-09 現行版本：純計算／RCD 匯出。** 使用者要求拔除 res-lab 的核心，
`build_v3_reslab.py` 與 `rl_v3.c` 已移除所有 recording hook、外部表指標與感測器補丁。
FSB1 `RLAB` version 2／min_svc 3 常駐自己的計算、選單、匯出及讀回緩衝。
只以 CHAIN claim 共用 GUI-id 與頁面首次註冊兩個位置；計算的 AXIS／canvas 都在自己的塊內。
OUTPUT 的 Save RCD 產生 `\fpSup\RESCUS\LABnnn.RCD` v3，原生寫入後核對完整讀回。
格式標頭由 res-custom 的 `ogc_layout.py` 產生；套用與錄影交給 `32RESCUS.BIN`。
14-bit 可計算，但現行 res-custom 不支援其錄影格式，匯出時明確拒絕。
新成品 `projects/res-lab/cards/20261009-calculator-v3/{plain,debug}`：
檔 444,480 B、常駐配置 712,576 B；詳見
[純計算驗證](../../res-lab/validation/20261009-calculator-v3/RESULTS.md)。未操作相機或寫實體卡。

以下為 **2026-10-06～08 的歷史錄影核心版**，成品保留追溯；現行建置已不再包含該核心。

程式在 `projects/open-gate/build/`:`build_v3_reslab.py`、`rl_v3.c`、`og_pic.py`、`test_v3_reslab.py`;
`sl_menu/sl_menu.c` 多一個 `SL_MENU_IN_BLOCK` 分支;`build_res_lab_card.py` 把 SLMP 區塊的建法抽成
`slmp_block()`/`slmp_limit_of()` 兩邊共用。舊卡(`--b25-menu --test-page lab`)改前改後逐位元組相同。
專案目錄已於 2026-10-07 改名為 `projects/res-lab`(留 `projects/sensor-lab` 符號連結給舊紀錄);同日 `projects/open-gate/build/` 的 `sensor_lab_*` 檔名與識別字也改成 `res_lab_*`(卡片輸出逐位元組不變;`sl_pages.py` 的 `TransSensorLab` 寫進頁面資料，未改)。檔名用 `50RESLAB.BIN`、id `RLAB`。

**做法與 OG 相同的座標系,差在 PIC 的手法**:res-lab 的 payload 在舊 cave 裡排得沒有空隙,OG 那種三指令的
PC 相對 LDA 會撞出 13 處重疊。所以 `OG_V3_PAIR` 下 LDA 照樣出 `movw/movt`(座標),由 `og_pic.py` 在建置時
改寫成同樣兩個字的 `add|sub rd, pc, #hi` + `add|sub rd, rd, #lo`;`ldr pc,[pc,#-4]` + 字面落在 layout 內的
(RETURN_TO 跳到別的 payload)改成 `b` + `nop`。**每個 payload 大小不變、位置不變**,也就沒有 r81 那種
「封裝改了兩個標籤的距離」的問題(舊封裝會拿掉空隙)。
核對:改寫的 140 對 movw/movt 與舊 USER 啟動器執行期重定位的 140 筆 ARM_MOV32 **位置完全相同**;舊的
3 筆 ABS32 = 1 個資料 fixup + 2 個 RETURN_TO 改寫;25 個核心 hook、10 個後期 UI hook、4 組指標對、
4,594 個靜態字、146 個執行期字,與舊封裝逐項相同。兩原點 PIC 證明通過(拿掉 RETURN_TO 改寫就被擋)。

**檔案**:`50RESLAB.BIN` 466,896 B(塊 468,672 B):程式(rl_v3 + sl_menu + sl_modes + ui_pool,一個 unit)、
表、layout image(0x8000)、SLMP(365 KB,`sl_menu_install` 直接從塊裡讀,不再開檔)、尾端 struct sl_menu。
297 個 claim,journal 約 21.5 KB(上限 32 KB)。

| entry(rl_v3.c)| 對應舊卡 |
|---|---|
| claim 全部 → cave 要 35 個 veneer → 任一拒絕 RELEASE | journal gate |
| fixup → 靜態字 → 指標對 → 核心 hook(picker 最後)→ og3krestore | stage2 區段 + 核心啟動器 |
| `sl_menu_install`;成功才寫 MARK、武裝 10 個後期 hook、切 B2_5;NBR 被拒就換回原廠頁 | 後期選單啟動器 |
| 選單沒裝起來 → 核心照常(KEEP) | 舊卡行為 |
`sl_modes.c` 靠 picker 的 veneer 找核心(目標 − FMT_CODE,檢查 CORE_MAGIC):layout 最後一字放 `SLCO`。

**測試** `test_v3_reslab.py`:13 項通過(stub `sl_menu_install` 與 og3krestore,其餘實跑:claim、journal = 原廠、
執行期字獨立核對 70 筆時序 + 預覽高、指標對指到塊內、picker 找核心、og3kgs 經 hook 實跑、選單成功時後期 hook /
MARK / 換頁、NBR 被拒換回原廠頁、關機全部寫回、殘留修復、後期 hook 點 / 靜態字被佔、cave 不夠 → RELEASE)。
mutation 15/15 抓到。既有 OpenGate / Sensor Lab 測試全過,只剩已決定不修的 `test_res_lab_cave_audit`(舊卡 0xF000)。

**卡**:`projects/usb-shell-sup/cards/20261006-v3-step6-reslab/`(LOADER/AutoRun/UI/00SHELL 取自第 2 步卡夾,
LOADER 是 svc v2 那版)。單卡:跟 30OG3K 同卡時 OG3K 先載入、res-lab 會因 picker 等點衝突而 RELEASE。
**還沒做**:上機;改名;`imx410_poff`(自己註冊關機物件)在 v3 下拒絕;Fast Start。

**2026-10-08 res-lab 遷移複核**：改名已完成；現行 `build_v3_reslab.py --card`
直接建目前的 LOADER/AutoRun/UI，`--no-shell` 產普通卡，預設卡片含診斷 shell，
不再預設複製第 2 步的歷史 loader。`50RESLAB.BIN` 最低服務版本為 3。
修正 `SL_MENU_IN_BLOCK` 的 exact-fit 檢查（舊版 `actual >= room` 令真正的選單
安裝器一律回 ROOM），並在讀 SLMP 欄位前檢查宣告長度。新增真正 ARM 安裝器、
recording picker profile 87、shell 組合與整個 48 MiB 韌體映像寫入的驗證。
新成品 `projects/res-lab/cards/20261008-loader-v3/{plain,debug}`：檔 468,048 B、
塊 469,824 B、143 筆 PC 相對改寫、297 claims、21,508 B journal。
精確普通卡 21 項、debug 4 項、兩張卡各 1 項完整映像／關機還原檢查通過；
69 項既有選單／模式回歸及三個新 mutation 均通過，無跳過測試。詳見
[本次紀錄](../../res-lab/validation/20261008-loader-v3/RESULTS.md)。仍未上機，Fast Start 未驗。

**QS 底列缺圖(2026-10-06 晚,已查明,刻意不修)**:v3 OG3K 上機時 QS 底列第三格是韌體的缺圖紅叉(截圖 SS__1365)。
原因在巢狀字串版(OG_UISHARE=1)的 og3k_ui.S,不是 v3:底列兩筆 literal-delta 記錄 C23535A3 / C25B9EF1 的替換位元組
寫死別名 id `0xFFFFFFF3`,巢狀版沒有舊的 ui_string hook,kind 4 照抄位元組,沒人解析。使用者決定**不短期修補**,
等 uishare 的 QS 共用層(fpSup/uishare/QS_SHARE.md)取代 OG 的 QS 程式;已通知 sigmafp-re-70。
另:uishare 字串層還會再改一版(標頭 +3 字),今天用新 uishare 重建的 30OG3K/30OG2K/50RESLAB 都是過渡版。

### OG3K + OG2K 同卡:錄影核心改成層(2026-10-07,離線,第一階段)

使用者:新的 uishare 應該讓兩個同時出現;**enum 跟第幾個堆疊有關**(= k + 2,k 是 CSV_ADD 發的列號;單獨一個 OG 時 k=2 → 4,
與現況一致)。enum 的部分等 uishare 的介面(resolution_qs 的 AUTO enum、entry 交還 enum);風險已記:卡上組成變了,
設定區存的值會指到另一個格式(不是「找不到」),退回 FHD 處理不了 —— uishare 那邊要跟使用者確認。

**第一階段(做完)**:`OG_CHAIN`(只在 v3 建置;AutoRun 卡的 OpenGate 區段逐位元組不變)。
- 14 個 hook 點都 claim CHAIN;每個 payload 往下走的地方改成 `OG_PASS` = 讀自己在 layout 的 NEXT 字(0xC0730100 起,
  `og3k_plan.CHAIN_SLOT`)再跳。entry 寫站點之前用 `svc->chain_next` 填:下面有別人的層 → 那一層;沒有 → 自己的
  `og_replay`(原本的位移指令 + 跳回)。og3kfps 的四個 BL 點共用一個字(呼叫的就是那個字)。
- aspect 兩個:原本一律自己選 2/3,改成「不是我的 → 往下」;payload 因此 100 B,v3 下搬到 0xC0730200 / 0x280。
- og3ksel / og3kfmt:「離開」只在**自己原本是生效的**才寫(donor 時序、六個預覽高),否則什麼都不寫。
- 六個預覽高 claim 改 CHAIN(兩者同一批字);donor 時序仍 EXCL(OG3K 用 98/117、OG2K 用 139,不重疊)。
- 測試:`test_v3_og` 17 項;新增:別人 EXCL 佔 picker → RELEASE;別人的層在 picker 下面 → 不是 OG 的鍵往下、自己的鍵
  在這層回答;**OG3K 與 OG2K 同卡兩個都載入**,OG3K30 / OG2K30 / OG2K60 各由自己的表回答(經 OG3K 外層傳到 OG2K);
  不是生效的層不動共用字;關機全部寫回。mutation 4/4。
**還沒做(第二階段,等 uishare)**:enum = k+2 —— og3ksel 的 `cmp r1,#4`、og3kfmt 的 `cmp r3,#4`、og3krestore 的
OG_ENUM 4 改成「我的 enum」(entry 拿到後存起來);OGSAVE(兩者共用一個字)改成「存的解析度 == 我的 enum 才還原」。
在那之前兩個同卡時都會把 enum 4 當成自己的 —— **還不能上機同卡測**。

## 2026-10-11：Merge 的瞬間／快速啟動

`v3/build_v3.py:boot_card()` 產生成套 AutoRun／LOADER.BIN。共用 builder 的
`--loader-hook` 提供瞬間啟動，`--store-boot` 提供快速啟動；關閉瞬間使用
`--loader-hook-off`，只取消指向共用 loader +4 的已知 RAM callsite。
即使兩者關閉，最終封裝仍帶共用 stage2，以取消暖重啟留下的先前設定。
Merge 預設瞬間開啟、快速未勾；frozen 產品卡不改寫。

v3 core 仍帶自己的 zero-section VBIN 標頭；stage2 的 entry r0 是 resolved entry，
stub 透過 builder 計算的 outer file offset 找回整個外層 VBIN。C 的 code length
來自 core entry 前一字，不再把 outer body length 當成 C code length。FSDS 附在
外層容器尾端，SupManager 保存完整外層檔案並將執行時 strs pointers 恢復為檔案中的零。
不保存內層 payload，不手工改生成的 offset。

共用 stage2、store_boot 與 abort 的韌體呼叫皆對齊 SP 並恢復原呼叫 SP；
stage2 使用 builder 傳入的 UI 目錄，v3 為 fpSup\UI，舊卡為 FPSUPUI。
更新较短檔案不補白，由 putfile 在 staging 已驗證後先刪舊檔並核對不存在，
再寫入與完整讀回。

此新啟動封裝未上機；離線資料、限制和反例見
[本次驗證](../validation/20261011-boot-options/RESULTS.md)。
