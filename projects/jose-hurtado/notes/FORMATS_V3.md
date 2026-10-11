# Jose 的 fpSup-Formats v0.6.1 → Loader v3(`31FMT.BIN`)

2026-10-06,**離線完成,未上機**。原始包:`../formats-v0.6.1/original/`(現行)、`../formats-v0.6.0/original/`(保留);
S16、OG3.5K、OG4K,未改動。⚠ v0.6.1 其實有**五包**:OG2K(slot 2)與 OG3K(slot 3)兩包沒收進 `original/`,
只在 `~/Downloads/fpSup-Formats-v0.6.1/releases/`(核心 115 段五包逐位元組相同;見 `JOSE_VS_OURS.md`),31FMT 因此只含三格。工具:`../formats/tools/`、`../formats/v3/`,`FMT_VERSION=0.6.0|0.6.1` 選包(預設 0.6.1)。

**現況一句話**:v0.6.1 的三格式搬成 `31FMT.BIN`(sup 版本 3、`min_svc` 3);他的字串 hook 不再裝,
改成一層標準 uishare 字串層(以檔名 `31FMT` 命名),所以和 `10LOSS` 同卡兩種順序都載入、兩邊字串都解得到;
v0.6.1 新增的 video clamp 寫的 8 個字全部 claim(EXCL)、關機寫回原廠值。
規格:[LOADER_V3.md](../../usb-shell-sup/notes/LOADER_V3.md)。前例:OG3K/OG2K 第 4 步(`build_v3_og.py`)。

## 0. 沒有原始碼

PR [ijigen/fpSup#7](https://github.com/ijigen/fpSup/pull/7) 和他的 fork 都只有 release 二進位;
v0.3.0a MANIFEST 提到的 `projects/open-gate/build/registry/` 不在這台機器。
所以不能照 OG 的做法「在兩個原點各組譯一次、比對結果」,改成**對 Jose 的位元組直接搬家**,
再用「雙胞胎」模擬證明行為沒變(§4)。

我們樹裡的 `fpSup/opengate/og4k/core.S` **跟他不同源**:我們的 donor 是 `0xC0B59D04`
(`T0=0x047901BD`),他的 OG4K/OG3.5K 用 `0xC0B59560`(`0x02DF01BD/0x00081516`),只有 magic `'OG4K'` 一樣。

## 1. 他的 VBIN 長什麼樣

三包的 stage2(876 B)完全相同;**核心 109 段(v0.6.1:115 段)在三包裡逐位元組相同**,每包另加自己的 slot 段:

| 包 | slot | 解析度 enum | slot 段 |
|---|---|---|---|
| S16 | 1 | 5 | picker `C072FB00`、token `C0730440`、欄表 `C0730DC0`、registry `C0731280`、記錄 `C07944DC`、圖示 pack `C079465C`、`C0794D5C`,以及感光元件模式表 `C0B59F54..C0B607F0` 的值補丁 |
| OG3.5K | 4 | 9 | `C072FF80`、`C0730458`、`C0731000`、`C0731340`、crop 列 `C0731440`、`C0731640`、`C079459C`、`C07A4BF0`、`C07A6670`、`C07A6730` |
| OG4K | 5 | 8 | `C0730100`、`C0730460`、`C07310C0`、`C0731380`、crop 列 `C0731400`、`C07945DC`、`C07A5430`、`C07A5B70`、`C07A64B0`、`C07A6570` |

佈局座標分三段(piece):cave `C072FB00..C0735000`、私有 pack 與 compositor `C0793060..C0794EA0`、
圖示 pack `C07A4BF0..C07A67F4`。入口 `C0793C30`(compositor)。

**cave 重疊檢查**:Jose 最低用到 `C072FB00`,沒碰 shell 交接字 `C072F000..F058`、`LOAD_START/DONE`(`F6F4/F6F8`)、
`store_boot`(`F700` 起,到 `FB00` 還有 1 KiB)。但舊 putfile 曾用 `C072FA00` 當 bulk loader —— 舊卡上是否衝突沒查;v3 下他的段已經不放 cave,問題自動消失。

⚠ `C0732A40` 以後與 `C0734C84..C0735000` 在原廠映像裡**不是零**(韌體 .data:字串、指標)。他的段沒有蓋到那裡,
他的程式也沒讀那裡(雙胞胎測試有檢查:只讀到映像與塊都是零的空 slot)。

## 2. 反組譯得到的事實(`tools/fmt_layout.py`)

- 從 23 個 hook 目標、compositor、開機刷新 task(`C0794034`)與暫存器呼叫做遞迴下降:**1,835 條指令(v0.6.1:1,872)、33 個入口**。
  沒走到的程式只有兩段死碼(`C0730578..C07305B0` 在無條件 `b` 之後、`C07330DC` 沒人引用),兩段都沒有位址參考。
- **他從不用 B/BL 跳出自己的 piece**:呼叫韌體一律 `movw/movt ip; blx ip`,跨 piece 也是。
  所以塊離韌體約 48 MB(超出 B/BL 的 ±32 MB)也不用改任何分支。builder 對此做斷言。
- 要修正的只有:**120 組 MOVW/MOVT**,以及 **143 個 32 位元字**(指標表、字面值、Thumb 函式指標 `|1`)。
  它們是唯一指向佈局的東西 —— 「接近但在 piece 外」的值:0 個。
- 韌體端有三個字存放佈局位址:`C06BDA3C/40`(韌體程式裡的 `movw/movt r2` = enum pair 表 `C0731C40`)、
  `C07426F8`(函式指標 → `C07304E0`)。entry 依塊位置重新編碼。

## 3. v3 的形狀

`../formats/v3/build_v3_fmt.py` → `\fpSup\31FMT.BIN`(sup_id `FMT6`;v0.6.1:54,836 B,塊 54,976 B,版本 3,`min_svc` 3)。
版本:1 = v0.6.0 字串點 EXCL(已作廢)、2 = v0.6.0 + uishare 字串層、3 = v0.6.1。
檔案比 v0.6.0 第一版大約 10 KB:多了編進同一 unit 的 uishare `ui_pool.c`(`uis_layer_fixed`)。

```
[FSB1] [fmt_tab+各表] [fmt_v3.c,Thumb -fropi] [piece0][piece1][piece2](各自保持 mod 64 對齊)[0:veneer 位址]
```

entry 順序(§4):全部 claim → 要 veneer → 塊內 fixup → **字串層(`uis_layer_fixed`,最後一個會拒絕的步驟)**
→ 值補丁 → 韌體裡的座標字 → veneer → hook(照他的 VBIN 順序)→ 呼叫 compositor 一次(r0 = 自己的位址,同 stage2)。
任一步失敗都在寫塊外任何東西之前 RELEASE。

**claim 共 136 筆(v0.6.1):133 筆 EXCL + 3 筆 SHARED_UI:**

| 種類 | 筆數 | 說明 |
|---|---|---|
| hook | 22 | 20 個 ARM B/BL + 2 個 Thumb B.W(`C05E6400/C05E84D8`)。他的第三個 `C05E5B58` 不裝(§6) |
| 值補丁 | 15 | CSV `C12C7CF8`(512 B)、`C0F8E7EC`、`C0D4DE04`、`C1A709BC`、`C06BDA48`、`C0CDC058`、S16 的模式表 |
| cleaner 的原廠字 | 40 | 舊版留下的清理字 → 只 claim(claim 本身就會把殘留寫回原廠)。v0.6.1 多 6 個 = video clamp 的字(§9) |
| 韌體裡的座標字 | 3 | 上面 §2 |
| 執行期才寫的字 | 53 | regapply 的 48 格(表 `C0730C10`)+ 5 筆 donor 時序記錄的 +4..+0x13(表 `C0730470`;picker 指的 donor 都在其中,builder 檢查)。video clamp 的 8 字在全格式建置裡都已被上兩列涵蓋;單格式建置(沒有 S16 段)時 `C0B5C71C/C730` 在這裡補 claim |
| 字串層的三個點 | 3 | `C05E5B58/61C8/61E0`,SHARED_UI(uishare `ui/chain.SITES`),只 claim、由 `uis_layer_fixed` 寫 |

**為什麼是一個 sup 而不是核心 + 三個格式檔**:核心用**寫死在自己佈局裡的 slot 位置**找格式
(registry `C0731240 + 0x40×slot`、picker `C072FB00 + 0x180×(slot-1)`),而 v3 的服務表沒有「找到別的 sup 的塊」的服務。
拆開就要改加載器。現在用 `--formats s16,og35k,og4k` 在建置時挑格式;沒挑的 slot 是零,等同那張卡上沒放那包。

PR#7 提到的「每次載入標記 slot、擋暖重開殘留」:v3 的塊每次開機都是新讀的,殘留不存在;韌體字的殘留由 claim 修復。

## 4. 驗證(`../formats/v3/test_v3_fmt.py`,v0.6.1 14 項全過約 120 秒;`FMT_VERSION=0.6.0` 也 14 項全過)

真的 loader.S + LOADER.BIN + 參考映像(`test_v3.Camera`):

- 載入、journal 記的是映像的原廠值、23 個 veneer、韌體 movw/movt 指向塊內的 enum 表、函式指標、建了 1 個 task、
  run-once 旗標清掉、Settings 上限依格式數;**開機全程沒碰到任何 Jose 的固定座標**。
- 關機後 128 筆全部寫回原廠;上次留下的 hook/值會被 REPAIRED 再裝上。
- 5 個代表位置(hook、regapply 格、donor 記錄、韌體 movw、CSV)被別人持有 → RELEASED、什麼都沒寫、沒拿 cave。
- 跟 `30OG3K.BIN`(v3)同卡:只載入 OG3K。
- **跟 lossless 同卡,兩種順序**(`10LOSS`+`31FMT`、`31FMT`+`40LOSS`;模擬裡掛上 lossless 的 MenuCamera 那套 GUI 物件,
  讓 lossless 的列與字串層真的裝上):兩個都載入;層名由內到外 `['10LOSS','31FMT']` / `['31FMT','40LOSS']`;
  經**韌體自己的** `C05E5B58` 解析:他的 39 個 id = 他的表、lossless 的每個私有位移 = 它的字、原廠位移 = 原廠規則;
  lossless 在外層時仍從 `0x40000000` 發號(跳過他的固定範圍)。
- 字串層:他的 id 經韌體解析器 = 他的表(他原 hook 的答案);`FFFFFFCF`/`FFFFFFF7`/`FFFFFFFF`/池長 → 0;
  擁有/剩餘對他的字串 = 1 / 到塊尾。字串點被別人以非 uishare 方式持有 → RELEASED、什麼都沒寫。
- 三種格式各自單獨建置、載入都通過;v0.6.1 時每次都檢查 clamp 8 字都在 journal、關機後 = 映像值。

**雙胞胎**(行為等價的證明;v0.6.1:528 次執行、991,486 個事件完全相同):同一套引擎跑兩份記憶體 —— Jose 的段放在他的固定位址(stage2 的樣子)vs loader 建好的塊。
先跑 compositor,比對他擁有的每個位元組(塊位址換回座標);再對 33 個入口 × 8 組輸入 × 2 種韌體回傳值,
記下每次寫入、每次呼叫韌體(含參數)、每次回傳:**528 次執行、991,346 個事件完全相同**;
v3 那份從沒讀寫過固定座標,也沒有任何值是「還沒修正的座標」。

**變異測試**:從檔案拿掉最後一個 MOVW/MOVT fixup、或最後一個字 fixup,雙胞胎測試都會失敗。
2026-10-06 加的:entry 不裝字串層(3 項失敗)、字串點改回 EXCL(3 項失敗)、層的 hi 改成 file_len(3 項失敗)、
builder 不 claim clamp 的執行期字(og35k/og4k 單格式 2 項失敗)—— 都抓到。
(第一版的字變異沒被抓到 —— 正規化把沒修正的座標當成正確,已改成直接判錯。)一律 `python3 -B`。

## 5. 卡

`../formats-v0.6.1/cards/20261006-v3-fmt061/`(LOADER + `31FMT`)與 `…-fmt061-loss/`(再加 `10LOSS`,用新版 uishare 建):
`build_v3_fmt.py --card [--lossless]`,**LOADER.BIN 是當場用 `build_v3.py` 建的服務版本 3**(31FMT 的 `min_svc` 3,
舊的 v2 LOADER 會以 BAD_HEADER 拒絕它)。`31FMT.BIN` sha256 `c4db6faa…7d12`,兩次建置相同。
**沒有放 00SHELL**。**沒寫進任何相機或卡。** 上機時 LOADER.BIN 必須和 31FMT 一起換。

`../formats-v0.6.0/cards/20261006-v3-fmt/` 是第一版(字串點 EXCL、v2 LOADER),已過時,只留作紀錄。

## 6. 字串 hook `C05E5B58`:他顯示什麼、現在怎麼裝

**2026-10-06 已改(使用者:用套娃)**:他的 `C05E5B58` hook 不裝;entry 呼叫 uishare 的
`uis_layer_fixed(他的表, 39, 0xFFFFFFD0, 塊頭, 塊尾)` 掛一層**標準字串層**:標頭名 = `31FMT`(loader 給的檔名)、
三個入口(解析/擁有/剩餘)都掛、沒命中交給下一層。他的表原地使用(不複製,compositor 照樣填);
擁有/剩餘的範圍是整個塊,因為他的字串分散在三個 piece(原廠 realloc 只拷貝 min(新長度, 剩餘),見 NESTED_HOOKS §3)。
builder 從他的位元組斷言 hook 的形狀(`cmn r1,#0x30` / `cmn r1,#0xa` / `add r1,#0x30` / 表字面值 `C0732DA0`),不符就停。
**行為差異只有一條**:他原本還要求 reader 的池是原廠或 `FSPL` 複本才命中;uishare v1 起池永遠是原廠,所以實際上相同。
下面是改之前的分析,保留作為依據。

**他用這個點做什麼**:解析度清單與 QS 上的新列需要「原廠字串池裡沒有的字」。
他的記錄 hook(`C05E6400`)把 379 筆原廠 NBU 記錄(表 `C073321C`,以記錄在映像裡的位址二分搜尋)換成複本,
複本的文字/影像名稱欄填入**固定的負數字串 id `0xFFFFFFD0..0xFFFFFFF6`**;韌體解析這些 id 時走到 `C05E5B58`,
他回傳自己表 `C0734AC8` 裡的字串。命中條件:id 在範圍內,且 reader 的池是原廠 `0xC18C0474`
(或池前 0x10 是 `'FSPL'`,也就是舊 uishare 的池複本)。其餘一律重放原廠指令(`cmp.w r1,#-1`)後跳回 `C05E5B5C`。

表在載入時由 compositor 依卡上的格式填好。三格式時(模擬 compositor 得到的實際內容):

| id | 字串 | 用途 |
|---|---|---|
| `FFFFFFF6` / `FFFFFFD0` / `FFFFFFD1` | `S16 2096x1238` / `OG3.5K 3456x2304` / `OG4K 3840x2560` | 第 3/4/5 列的標籤 |
| `FFFFFFF2..F4` | `S16_QS` `S16_SET` `S16_FONT` | 第 3 列的影像名稱(從他的私有 NBR pack 載入的圖) |
| `FFFFFFE0..E2`、`E3..E5` | `OG35K_*`、`OG4K_*` | 第 4、5 列的影像名稱 |
| `D2..D4`、`E6..EE` | `SLOT4..6`、`S5..S7_*` | 空 slot 的占位,不會顯示 |

CSV(`C12C7CF8`)同時改成 `3,S16 2096x1238 / 4,OG3.5K… / 5,OG4K…`:Settings 清單的文字直接寫在 CSV,
不經字串 id。字串 id 用在記錄 hook 換掉的那些記錄上;依 v0.3.0a 的說明是 QS 圖磚、底列標籤與收合摘要(**推論**,沒有逐筆對照 379 筆記錄)。

**跟 lossless 是同一個掛點,不是同一批 id。** lossless 的字串在 uishare 的 FSDL 層裡,id 是開機時從
`0x40000000` 往上發(NESTED_HOOKS §3);他的是 `0xFFFFFFD0..F6` 固定值。兩個範圍不重疊。
衝突只有一件事:他沒命中就**重放原廠**,不交給下一層,所以裝在 lossless 上面時 lossless 的字串會消失。
這就是 `31FMT` 跟 `10LOSS` 不能同卡的唯一原因;其餘點 lossless 沒宣告(OG3K 才宣告 `C05E6400/84D8`)。

**改成標準 uishare 層的評估(未動手)**

| 版本 | 要改的 | 量 |
|---|---|---|
| 最小:沒命中交給下一層 | 沒命中的跳轉字面值(`C0732DB4`,現在 = 原廠重放 `C0732DC1`)改指到塊內一個 8 B 跳板;entry 先 `chain_next(C05E5B58, thumb)`,0 就用原廠重放;`C05E5B58` 改宣告 SHARED_UI | 改 1 個字、加 8 B、C 約 10 行,雙胞胎測試的「沒命中」事件要改預期 |
| 完整:別人也能疊在他上面 | 再加 FSDL v1 標頭(base/count/data_lo/hi/三個 next)與「擁有」「剩餘」兩個入口(各約 10 條指令),並掛 `C05E61C8/61E0`(SHARED_UI) | 約 40–60 條新指令 + 標頭 + 3 個 claim + 測試 |

lossless 是在**自己的 entry 裡同步**裝層(`card.c:350` → `fpl_menu_install_data` → `uia_apply`),
而 `10LOSS` 依檔名先於 `31FMT` 載入,所以**最小版就足以和 lossless 同卡**。
完整版只在之後還有 uishare sup 要疊上來時才需要(檔名排在 `31` 之後的)。

風險:
1. **id 寫死**。他的 id 不是開機發的(違反 NESTED_HOOKS 規則 4)。跟 uishare 的 `0x40000000+` 不會撞,
   但跟任何同樣寫死負數 id 的舊卡會撞;舊 OG3K 的 `FFFFFFF2` 正好在他的範圍內,不過 OG3K 本來就和他互斥。
2. **只掛解析、沒掛擁有/剩餘**(他原版就是這樣)。韌體的 free/realloc 會把他的字串指標當成池外指標,
   有一天可能交給原廠 free(NESTED_HOOKS §3)。最小版保留這個既有風險,完整版才會修掉。
3. **命中條件依賴池**。uishare v1 不再複製池,所以 reader 的池仍是原廠 `0xC18C0474`,條件成立;
   若有 sup 還在用舊的池複本,`'FSPL'` 那條也會接住。
4. **順序依賴**。最小版只保證「他在別人上面」。若有 uishare sup 排在他後面,
   對方會在掛點看到不認得的 B.W 而不裝(UIA_HOOK),行為取決於那個 sup。
5. 改的是他的二進位(沒有原始碼),要用雙胞胎測試證明「只有沒命中那條路變了」,並加 lossless 同卡的模擬
   (原廠 id = 原廠值、他的 id = 他的字串、lossless 的 id = lossless 的字串)。

## 7. 開機刷新改的 `[[0xC3075230]+0x334]`,以及其他執行期寫入

**`0xC30751D4` 是 `XC_UserSetting` 的單例**(`FUN_c0021c00` = 取實例,保護字 `0xC3075234`,大小 0x60,
建構式 `FUN_c0021b40`,vtable `0xC07286EC`)。`+0x5C`(= `0xC3075230`)是它的資料指標
(`FUN_c0021c40` 就是 `return [this+0x5C]`),指向另一個單例 `0xC3074BE8`:大小 0x5E4 的使用者設定資料
(`FUN_c0021b00`/`FUN_c0022138` 建構,`FUN_c0022a00` 填預設)。

**`+0x334` 是 Crop Mode。** 原廠唯一的寫入者是 `MenuItemCropMode::v3`(`0xC00A93C8`),
它把選單項的值(`FUN_c00a9268()`)寫進 `data+0x334`;讀取者:`FUN_c0364978/0364A30`(值 = 1 時 EXIF 35mm 等效焦距 ×1.5)、
`blk_c02.c:32940`(建 LV/錄影設定時 `+0x20DC = (+0x334 == 1)`)。預設 2(`FUN_c0022a00` 的 `param_1[0xCD]`)。

**它在不在會存的區域?不在。** 資料物件在 `0xC3074BE8..0xC30751CC`,實例在 `..0xC3075234`,
`XC_CommonSaveData` 從 `0xC307523C` 開始;唯一的存檔管理員是 `XC_SettingSaveDataMgrCore<XC_CommonSaveData>`。
`XC_UserSetting` 的資料是**從選單設定推導出來的執行期副本**(由 `MenuItemCropMode::v3` 這類 apply 寫入),
持久的值存在選單設定那一邊。

**他怎麼用**:`regseltail`(hook `C005C054`)只在「待機外觀會變」時:
`C0091288(0xC31ACB3C, 0xFFFF, 1, 0)` → `data+0x334 ^= 1` → 再一次 `C0091288(…, 1, 0)` → `C00911A0(…, 1, 1)`。
翻轉夾在兩次 apply 之間,第二次 apply 會呼叫 `MenuItemCropMode::v3` 把它寫回選單的真值。
所以觀察者看到的是「Crop 變了又變回」,藉此觸發 LV 重建;**翻轉後的值(2 → 3、1 → 0)不會留下,也不會被存**。
⚠ 推論的前提是 `C0091288` 的 0xFFFF 會 apply 到 Crop Mode 項。這點只讀了反編譯,沒有在模擬或相機上確認。

**其他 claim 不了的執行期寫入**(都不在韌體映像裡,沒有原廠值可記;原版行為相同):

| 位置 | 誰寫 | 是什麼 | 會不會存 |
|---|---|---|---|
| `[[0xC3075230]+0x334]` | regseltail | Crop Mode 的執行期副本,翻轉後被 apply 寫回(上段) | 不會 |
| `0xC3767490/94` | regcanvas(hook `C043A19C`) | BSS 物件 `0xC3767480`:第一字 = `0x69` 且 `+0x10 = -1` 時,寫 `+0x10 = 0x2D`、`+0x14 = -1`。物件身分沒找到(反編譯裡沒有這個常數,疑為以基底+位移存取的模式記錄) | BSS,不在 CommonSaveData;未證實 |
| RAM 裡的資源目錄 | UI runtime(NBR 載入 hook `C05E84D8` 之後) | `[0xC69029F0]` 指向的目錄落在 `0xC6800000..0xC7C00000` 且 `+0x440 = 0x0780AE3B` 時,把 `+0x448/+0x44C` 改成 `{0x5A58F8, CSV 長度}`。這是 `C0D4DE04` 同一個改指標,改在已載入的副本上 | 堆積,不會 |
| 韌體解析物件 `[r4+0x24]`、`[r4+4]` | 記錄 hook(`C05E6400`) | 解析時暫時指向他堆疊上的複本,呼叫原廠解析後還原 | 暫時 |
| 呼叫參數裡的韌體物件(`str [r1, r0]`、`[ip+0x10]` 等) | regcanvas、picker | 原廠傳進來的畫布/請求物件欄位(就是他改格式的方式) | 隨物件生命週期 |

## 8. 未解 / 要決定

1. ~~跟 lossless 同卡~~ 已解(§6,完整版:標準層)。但**同一張卡上所有用字串層的 sup 必須用同一版 uishare 建**
   (層標頭 v2 與 v1 互不承認,見 NESTED_HOOKS §4)。
6. LOAD.LOG 的記錄只有 96 筆,31FMT 一個就寫 130 多筆 CLAIM,之後載入的 sup 的 LOADED 行會被擠掉
   (測試改讀 loader 的登記簿)。上機看 LOAD.LOG 時要知道這點。
2. 一個 sup 裝三種格式(§3)。要做到「一格式一檔」,得在加載器加一個服務,例如依 sup_id 找到塊。
3. §7 的兩個推論沒確認:`C0091288(0xFFFF)` 會 apply Crop Mode;`0xC3767480` 的身分。
4. 雙胞胎的韌體呼叫一律用 stub(兩邊相同):真正的回傳值走到的路徑,只有上機才看得到。
5. Jose 的 `C0D4DE04` 改指標與 CSV 仍放在韌體映像原地(`C12C7CF8`,已 claim);沒搬進塊。

## 9. v0.6.1 的變更:video clamp

Jose 的說明:3:2 用到的感光元件模式(3/98/121/139)是靜態/LV 模式,黑位校正走 stills clamp,高 ISO 時黑位逐幀跳一階
→ 暗部閃爍。v0.6.1 套用格式時打開該模式的 video clamp(原廠錄影模式都有的兩欄),回 UHD/FHD 時關掉。

**位元組上的差異**(`fpSup.BIN` 約 2 萬 bytes 不同是 VBIN 內的位移造成):核心只有兩段改變 ——
`C0730800`(440→492 B)、`C0731800`(regapply,384→496 B);加 6 個 4 B 的韌體段 `C0B5C6AC/6C0/6E4/6F8/CE54/CE68`,
內容 = 映像原值(cleaner 型,宣告「我會改這些字」讓 stage2 journal)。其餘位址不變。

**clamp 程式**(`C07318E8..C07319A4`,builder 逐字斷言):每次 apply 先對字面值表 `C07319E0` 的 4 筆記錄
`C0B5C6E0/C6A8/CE50/C718` 清 `[rec+4]` 的 bit 3 與 `[rec+0x18]` 的 bit 14–15;選了 Formats 模式時再對
`rec = C0B5C638 + ((donor − C0B59500) × 7 >> 2)` 設回。被 picker 用到的 donor(S16 `C0B59580`→`C718`、OG3.5K/OG4K
`C0B59560`→`C6E0`)都落在這 4 筆裡(builder 檢查)。✎ 2026-10-07 更正:他的 OG3K/OG2K slot 用的是 `C0B59540`(mode 98 → `C6A8`)與
`C0B599A0`(mode 139 → `CE50`),**都在清單裡**;`C0B59620` 是 mode 7(原廠 UHD)的時序記錄,只出現在 regsel 的寫回原廠表
`C0730470`。清單外的是 OG3K100 的 mode 117(`C0B59A20` → `CF30`):picker/regsel 會設、從不清(`JOSE_VS_OURS.md` §5.1)。

**claim**:8 個字(4 筆 × `+4/+0x18`)全部 EXCL。全格式建置時 6 個由 cleaner 段、`C71C/C730` 由 S16 的模式表值補丁涵蓋;
沒有 S16 時 builder 以「執行期才寫」補 claim。**「關掉 = 原廠值」已確認**:這 8 個字在映像裡,bit 3 與 bit 14–15 都是 0
(`+4` 全為 0,`+0x18` 為 `0x00040003/0x00040002`),所以 bic 回到的就是原廠值;builder 若發現映像裡這些位元是 1 會停。
關機時 journal 寫回映像值(測試確認)。**未確認**:S16 的值補丁本身在 `C71C..C750`,clamp 的 bic 會清掉它設的位元 ——
看他的值,`+4` 與 `+0x18` 這兩格他沒設 bit 3/14–15,所以不衝突;上機效果(閃爍是否消失)只有 Jose 的相機測過。
