# Loader v2 與 cave 規則

> ⚠ 2026-10-06:佈局與各 sup 改法由 [LOADER_V3.md](LOADER_V3.md) 取代(一個 sup 一塊、`fpSup/*.BIN`);下方 ⏸ 保留問題的解法在 V3 §5。

2026-09-25,依使用者的原則。**未實作。** 依據:`WARM_BOOT_GATE.md` 最小測試(loader hook 1.402 s 載入)。

## 原則(使用者定)

1. **cave 不放變數。** 每個 sup 的狀態放自己的工作記憶體(池)。
2. **cave 只放程式與 hook:** loader、loader hook、各 sup hook 的 veneer。
3. **關機時解除所有 sup 寫過的韌體位址**(loader hook 除外)。og 也不例外 ——
   暖開機只保留 hook,sup 的其他資源(池、BSS 註冊、配置)都沒了,留下的 hook 等於懸空。
4. **暖開機由loader hook全部重載。**

## 關鍵:原字記在池裡

解除要知道原字。og3k 一張卡就改了 55 段、4 KB 韌體,放不進 cave,也不該放(原則 1)。
但**解除發生在關機回呼裡,那時池還活著** —— 所以原字記在池裡就夠了,不需要跨開機。

```
載入時   stage2 放每個絕對位址的區段前,先把那段原字複製進 journal(池)
         entry 執行期裝的 hook 也走同一個函式 patch(site, word) → 先記再寫
關機時   PowerOffMgr → unhook:journal 逆序寫回、發布快取
暖開機   映像 = 原廠 + loader + loader hook(+ 無人會跳進的舊 veneer/og 程式位元組)
```

- journal 由 loader 向配置器要(class 0,不釋放);大小 = 所有區段總長 + 8 B/段。
  og3k 約 14 KB(含它映像零區的程式,原字是 0,寫回也無害 —— 規則簡單勝過省記憶體)。
- unhook 本身放 loader 區塊(程式,約 60 B,只用立即數);它讀的 journal 位址寫死在自己的
  `movw/movt` 裡 —— stage2 在載入時把位址 patch 進 unhook 的兩個指令字,cave 不放變數。
- `0xC03DA420`(loader hook)**不進 journal**,是唯一刻意跨開機的補丁。

## cave 佈局

```
0xC072DE64  loader 區塊 512 B:loader ~260 B、gate ~80 B、unhook ~60 B、poff 物件 8 B
0xC072E064  veneer 槽:每槽 8 B { ldr pc,[pc,#-4] ; 目標 },固定槽位,依序給
            (韌體 bl 只到 ±32 MB,跳不到池,所以 veneer 非在 cave 不可)
```

沒有 `CAVE_BUMP`、沒有 arena、沒有 worker 狀態區、沒有 `LOAD_DONE_US`。
veneer 槽的分配交給 stage2(載入時知道每個 sup 要幾個),不用執行期配置器。

## 開機流程

```
冷開機:映像重載 → 0xC03DA420 原廠 → AutoRun → loader ─┐
暖開機:0xC03DA420 → gate → loader ─────────────────────┤
                                                      ▼
   配 journal → 讀 fpSup.BIN、驗 VBIN(失敗回傳 0 → gate 放行 AutoRun)
   stage2:逐段「記原字 → 寫」→ entry 配自己的池、用 patch() 裝 hook
   註冊關機回呼(一般 + 強制)→ 把 unhook 的 journal 位址填好
   裝 0xC03DA420 = bl gate → loader 回傳 1
```

順序上的硬規則:**關機回呼註冊失敗 → 不裝任何 hook、不裝loader hook**(沿用 HOOKS_AT_POWER_OFF)。

## 各 sup 要改的

| 產品 | 改動 |
|---|---|
| og3k / og2k | 不用改 —— 它只有 BIN 區段,stage2 自動記帳、關機自動還原 |
| gyro | `s_hook` 改呼叫共用 `patch()`;veneer 用 stage2 給的槽;刪 `poff_disarm` |
| usbshell | worker 狀態 96 B(`0xC072F000`)搬進 worker 的池;主機從 `0xC3757A7C` 找(BSS,開機清零) |
| 主機工具 | `cave.claim` 改向 worker 的池要 |
| AutoRun | 3 個畫面補丁搬進 BIN(否則不進 journal,也不會在暖開機重載) |

## 剩下的風險

- **關機回呼沒跑到**(當機、凍結後拔電):journal 在池裡,開機時已經沒了,補丁會留下來。
  下次開機可能在 1.4 s 前觸發懸空 hook。**使用者 2026-09-25 判定為可接受風險,不另設機制。**
  (拔電池是否重載映像仍未量,量到再記。)
- **熱插卡**會不會再觸發loader hook(`0xC03DA3F8` 是 `XC_ShellScriptAutoRun` 的虛擬函式)。

## 實作進度

**第 1 步(2026-09-25,離線通過,未上機):** `--loader-hook`(`build_autorun.py`)。
- `loader.S`:+4 是 loader hook 入口;`load` 回傳 1/0。
- `stage2.S`(`#ifdef LOADER_HOOK`):配 journal 區塊 → 複製 unhook → 註冊一般 + 強制清單 →
  pass 1 逐段記原字(cave `0xC072D000..0xC0735000` 不記)→ 確認 loader+4 是這版的入口才裝 `0xC03DA420`。
- `test_loader_hook.py`:unicorn 跑真的 loader + stage2 + 韌體映像,6 項;7 個 mutation 全部抓到。
- 上機卡 `~/Desktop/fpsup-loader-hook-1/`,檢查 `loader_hook_check.py`。

**第 1 步上機通過(2026-09-25):** 連續兩次暖開機都沒有進度條,1.391 s 載入完成;關機還原跑了 2 次;
下一次開機記下的 7 個原字全等於原廠值 → 關機時確實還原了。

## 待討論:loader hook 路徑沒有畫面回饋

暖開機跳過 AutoRun,也就沒有進度條和 banner,使用者不知道載入完成了。已查到的:
- 可以不經 shell 分派器,直接呼叫 `display` 子命令的處理函式(`splash_finish.S` 用 osdfile `0xC03E4270` 這樣做,上機畫得出來)。
  分派器 `0xC03E5510` 用 argv[0] 查子命令,處理函式收 (ctx, 參數個數, 參數陣列),ctx[0] 是 printf。
  `text` = `0xC03E4620`(argc>0 時讀 argv[0] 為字串),`osd` = `0xC03E3D00`。
- 未知:1.39 s 時 OSD 圖層是否已可用、開機動畫是否播完、畫上去會不會被之後的 UI 重繪蓋掉。
- 使用者提的方向:(a) 在 1.39 s 載入後緊接著畫;(b) 把 loader hook 改掛在開機動畫上(動畫結束時觸發)。

## loader hook 路徑的畫面(2026-09-25)

- 1.35 s 直接畫文字 banner:畫得出來,但 0.2 s 後被 UI 蓋掉(`NORMAL OSD DISP` 在 1.561 s,
  而且它記在顯示切換函式 `0xC02E6B90` 的開頭,真正切換在後面)。
- 等到 3 s 才畫:留得住,但先清整層會把 UI 圖示一起清掉 → 快路徑不清。
- **定案方向:四格畫面(`--four-box-bar`)。** stage2 在快路徑自己補上 AutoRun 的前段
  (等到 3 s → 記下 `0xC0528700` 原字 → 暫停重繪 → `0.BIN` ×3),再走原本的 `splash_finish`
  (`4.BIN`、停 2 s、恢復重繪、強制完整重畫)。重繪已被 AutoRun 暫停就代表是慢路徑,不重複。
  LH6 上機:第一次暖開機四格出現、UI 完整回來。
- 另:插著 USB 線關機一律冷開機;SSD 開機前接著不影響快路徑。

## 三段式開機(2026-09-25,使用者要求把 store-boot 加回來)

慢(AutoRun 拼出 loader、存進設定區)→ 快(AutoRun 引導碼從設定區複製 loader、中止)→ 瞬間(loader hook)。
三條路都進同一個 loader + stage2。stage2 的 ARM_ABORT 改成「註冊表裡真的有 AutoRun(每行回呼 0xC03DA7A8)
才把 echo 指向中止程式」,深度 > 15 視為非活表(映像檔在那個位址是垃圾值 0x38357C54)。
上機(og3k v0.2.5a 原樣 + shell + 四格,`cards/warm-boot-2026-09-25/og3k-3way-1`):
冷開機慢 → 冷開機快 → 暖開機瞬間;之後讀:hook 裝著、LOAD_DONE 1.356 s、echo 槽是原廠值、
設定區 = 這版 loader、journal 63/63 = 原廠(上一次快開機的關機回呼有還原)。
使用者觀察:沒插線的暖開機偶爾仍會掉到 AutoRun,原因未明;有快路徑後代價很小。

## ⏸ 保留問題:關機回呼漏跑一次之後,記到的「原字」是錯的(2026-09-25,使用者要求先記下)

**現象(模擬器):** stage2 的規則是「寫入前,記下當下記憶體裡的值」。如果上一次關機回呼沒跑到
(當機、拔電),記憶體裡留著上次的補丁,這次就會把**補丁值**當成原字記下 → 關機還原把補丁寫回去 →
每次暖開機都留著,直到冷開機。
- og3k:留下的是指向映像內 og 程式的補丁,不會當機,只是一直留著。
- gyro:留下的是指向**上一次的池**的 `bl` 跳板,開機 1.4 s 內觸發就可能當機 —— 最危險。
  模擬:STOP 位址預先放一個舊 `bl` → 載入時宣告區段把它修回原廠,但記錄記到舊 `bl` → 關機又寫回舊 `bl`。

**根本原因:** 主載入在相機上無法得知原廠值(暖開機時映像就是上次留下的;原廠值只在 NAND 的壓縮韌體裡)。
原廠值只有「建卡時」知道(手上有 `out/MAIN_c0000000.bin`),或產品自己知道(gyro 的 `*_ORIG` 常數)。

**討論過的做法(都未實作):**
1. gyro 宣告每個 hook 位址兩次:第一次清掉殘留,第二次記到原廠值;依賴「關機還原照記錄順序重放、後蓋前」。只改 gyro 建置。
2. 宣告區段帶旗標(長度最高位元)=「這是原廠值」:stage2 寫入並直接把區段資料當原字記,不讀記憶體。改 stage2 + gyro 建置。
3. 通用版:建卡時替**每個**韌體區段自動附上原廠值區段(從參考映像取),stage2 一律用卡片提供的原廠值記錄
   → 所有產品都不會記錯,暖開機也會先把殘留清掉。代價:BIN 多出補丁位元組數(og3k 約 4 KB,在讀取上限內);
   合併器要跟著帶。
使用者表示還沒看懂,**先保留,之後再討論**。

**第 3 步目前的狀態(未上機):** gyro 已拿掉 `s_poff`/`poff_disarm`(`writer_core.inc.S`、`ring_task.inc.S` 的 POFF 常數),
`build_base_card.py` 一律 `--loader-hook` 並加 4 個 hook 位址宣告區段(`hook_sites()`,來源 `imu_stream_deploy.PRODUCERS`)。
`test_imu_stream.PowerOff` 的三個 disarm 測試還沒改(會失敗)。

## 收尾(2026-09-25):一起更新

- **拆成兩層:** `LH_RESTORE`(關機寫回)每張 `--loader` 卡預設都有;`LOADER_HOOK`(裝 `0xC03DA420` + 四格)只有 `--loader-hook`。
- **發布(本機 releases/,未 commit):** usbshell v3.3.0、gyro v1.14.0、og3k v0.2.6a、og2k v0.1.3a。
  og 的 85 區段原樣自前一版重包;gyro 用 release_card.py;單一卡只走慢開,README 寫了注意事項。
- **合併頁面:** Fast Start 2 = `--store-boot --loader-hook --four-box-bar`,zip 帶 `FPSUPUI/`;build_catalogue 5 組重現全過。
  頁面合出的 shell+gyro+og3k+FS2 卡上機:瞬開/快開都有出現。
- **修好** `projects/open-gate/build/build_og3k_gyro.py` 的字數檢查(漏算 og3k v0.2.5a 的 ui_layout 狀態 12 字);`test_boot_entry_chain.py` 14 案全過。
- **文件:** SUP_BUILD_RULES(中英)、BUILDING(中英)、HOOKS_AT_POWER_OFF.md、card-composer README、發布表。
- **仍開放:** ⏸ 殘留當原字的保留問題;暖開機變冷開機的比例(下午明顯變高,原因未明,IPL 決定)。
