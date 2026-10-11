# 出貨卡的建置流程 —— 現況盤點

2026-09-22。把「新版 AutoRun + 整套建置」攤開成一條線,並在最後列出**還沒收乾淨**的東西。
每一條都是從樹裡查到或當場跑出來的,不是回憶。

## 2026-09-24 介面續改：sup 格子與分類

**後續發布：**使用者明確要求「推上git」後，已提交並推送至 GitHub `origin/main`：
`84ebcff60bd2598e1bdbda224fd0bbd9e1fd55dc`（Update fpSup-Merge catalogue grid and boot packaging）。
共 15 檔：本任務 composer／boot 包裝／測試／守則，加上由既有產生器同步的首頁與 README 版本表；
發行表、render、兩份頁面的 34 組合併與 UI 事件測試、4 項 boot-chain unittest 均通過。
未納入其他 AI 的 raw／lossless／OG 研究修改或 .DS_Store，未更動 frozen releases，未寫卡／上機。
下方「未 commit／push」保留為開發完成、尚未取得發布授權當時的狀態；本段記錄其後的授權發布。

依使用者要求，fpSup-Merge 的 sup 清單改為 responsive 格子，開始以 catalogue 的
`category` metadata 產生分類按鈕，不把四個現有產品寫成另一份固定 UI 清單。

- 預設停在 **Shooting**，顯示 gyro／OG3K／OG2K；**Development 預設不展開**，
  切到 Development 或 All 才顯示 Shell。預設勾選仍只有 gyro＋OG3K。
- 切分類只改顯示，不取消已選 sup，也不重組下載檔案。上方常駐已選清單可跨分類移除選項，
  並提示其他分類中還有幾項已選。OG3K／OG2K 的互斥規則保留。
- **Fast Start 改為獨立啟動設定開關**，預設 off，不是 sup 卡片、不參與分類。
  EP83 仍放在已選 Shell 的進階選項內。上傳檔案另歸 Uploaded，移除最後一個後回到有效分類。
- 新 sup 只需設定 `PRODUCTS.category`；未知分類自動出現，缺省為 Other／`uncategorized`。
  不新增搜尋、分頁或通用外掛框架；本輪不動 payload、合併演算法、AutoRun 或 boot chain。

正式來源重新生成的 `index.html`／`artifact.html` 都通過 `render.py --check`、
原本 `test_compose.js` 的 34 組回歸，以及新增 `test_catalog_ui.js`：實際執行頁面 script
與事件處理器，核對分類、跨類別選取、OG 互斥、上傳／移除、EP83 和 Fast on→off。
Fast 開啟時切換分類不改 Fast 狀態或產物；關閉後完全回到原本 normal BIN／AutoRun。
此 UI 測試使用離線 DOM stub，**不是瀏覽器目視或相機驗證**；本輪未重試先前被政策阻擋的本機瀏覽器預覽。

另比對修改前後：移除新增 `category` 欄位後，整份 catalogue 逐 byte 一致；
內嵌 `compose` script 也逐 byte 一致。Frozen releases 未修改，未寫卡／上機／commit／push。
本輪只是介面顯示變更，使用者不需要因此換 AutoRun 或 BIN。

本次介面產物 SHA-256（下節前一輪 loader 更新的頁面 hash 保留為當時快照）：

- `tools/card-composer/index.html`：`d285aed5c8e13f775f5d530716c619b108bc2d3d8ddcc18c42d0441b80767152`
- `tools/card-composer/artifact.html`：`ff27e03480b289dc5fe9355849ce70061e0d27f92ab9af08424e80127550c4b1`

## 2026-09-24 整合更新：fpSup-Merge 採用現行載入鏈

本輪延續下方 09-23 的載入鏈收尾，**更新的是本機合併器，不是重新發行四個產品**。
已與 OG 共用穩定性紀錄的維護 AI 確認分工：本節記錄 composer／封裝與離線驗證，
OG 筆記的既有上機證據不改寫，也不把相同 OG payload 視為新合併卡的上機證明。

### 本次範圍與意義

- 從 frozen releases 載入 **Shell 3.2.0、gyro 1.13、OG3K 0.2.5a、OG2K 0.1.2a**，
  重建 `fpSup/tools/card-composer/index.html` 與 `artifact.html`。凍結檔案沒有覆寫。
- 現行 normal／Fast 模板帶入 loader 的 D → I → stage2 與 Fast 六暫存器對齊修正。
  兩個 pass 保留；多入口維持 **worker → gyro → OG restore**，缺少的項目直接省略。
  normal loader 260 B、stage2 304 B；Fast stage2 388 B、abort 152 B。
  normal 104 條，Fast 全腳本 169 條；不再把 bootstrap 的 26 個 words 說成完整開機命令數。
- **EP83 選项真正作用於 BIN。** 舊頁面只切 AutoRun 模板，但三種模板的命令已相同，
  所以關閉時仍帶六筆補丁。現在從共用 `patches.PUSH` 取得六筆確切 `(address, word)`，
  僅對明確的 built-in Shell 卡保留／移除。介面 class patch 不變；上傳卡不猜測、不代刪。
  `destination=0` 也不再自動被認作 Shell，gyro 的 launcher 不會冒出 Shell 選項。
- **32 KiB 是填充大小，不是 loader 的讀取上限。** 新 shell+gyro+OG2K reference 使用
  32,792 B，舊共用 builder 因固定 32,768 B 而拒絕；browser 原本已支援較大封包。
  共用 builder 與 Python composer 現在對齊既有政策：用量 ≤32,768 B 時維持原填充，
  更大時填至從 `loader.S` 讀出的 `MAXLEN=0xF000`（61,440 B），超過上限仍拒絕。
  不改 loader buffer、runtime 檢查或載入 ABI。
- 移除過期 `STALE`。兩個 gyro+OG plain reference 恢復逐 byte 一致檢查；
  shell reference 與合併器以相同 EP-off 配置比較完整區段及解析後的入口順序。
  兩者 worker 放置位置不同，只允許區段排列與入口表 offset 重定位；其餘 blob、數量、
  trampoline 程式碼、self-offset、結束值與入口順序都必須一致，並確認目的區段不重疊。
- 更新合併器 README 與 Fast 說明：**同 loader／封裝配置的相容 payload 更新仍只换 BIN**。
  不加入 BIN hash、版本配對、pair ID 或每次換 BIN 就換 AutoRun 的規則。
  採用這次真的變更過的 loader／Fast 封裝時，才一次更新對應的 AutoRun＋BIN。
  單卡 ordinary 且維持出貨選項時，BIN 仍逐 byte 保留；Shell EP-off 與 Fast 是明確重包裝。

### 正式來源驗證

在 `fpSup/` 執行以下項目，均通過：

```sh
python3 -B tools/card-composer/build_catalogue.py
python3 -B tools/card-composer/render.py --check
node tools/card-composer/test_compose.js
node tools/card-composer/test_compose.js tools/card-composer/artifact.html
python3 -B fp_usb_shell/test_boot_chain.py
git diff --check
```

- Generator：4 frozen BIN round-trip、2 plain 合併逐 byte、2 shell 同配置區段／有序入口、
  AutoRun references 與 3 個 JavaScript 區塊語法檢查通過；臨時 reference 不留作出貨成品。
- 每份 HTML 直接執行其內嵌 compose 程式：**11 個合法非空選擇、34 組 normal／Fast／EP83 模式**，
  4 個 frozen 單卡、入口重定位／順序、payload 不綁 AutoRun、內嵌 D/I／Fast SP 均通過。
  EP-off 的六筆確實不存在，EP-on 的六筆值與 `patches.PUSH` 相同。
- 共用 boot-chain **4 項 unittest** 通過（原 3 項加容量邊界）。主機建置與頁面均測
  32,768、32,772、61,440、61,444 B：前三者採預期填充，最後一項被既有容量檢查拒絕。
  主機測試同時確認跨填充級距不改 AutoRun。
- 額外跑完整研究樹 `test_boot_entry_chain.py --jobs 3` **未通過**：14 組均先被
  `build_og3k_gyro.py` 的 UI 預期字數 guard 擋下，OG3K 實際 3498 vs 預期 3486，
  OG2K 實際 3774 vs 預期 3762，皆差 12 words。本輪未修改該 OG 路徑，已交接 OG 維護 AI，
  未放寬 guard，新增 12 words 的來源尚未在本輪獨立核對；不能沿用 09-23 的 14 組通過作為當前源碼通過證據。
  失敗報告：`/var/folders/20/mb8w7p_x7nlfpctnt7qd77b00000gn/T/boot-entry-chain-g24o7sk5/report.json`。
- 本機 HTML 的瀏覽器預覽被 URL 安全政策阻擋，**沒有完成目視／點擊／下載 smoke test**；
  以上 JavaScript 測試是離線執行，不冒充瀏覽器操作。未寫卡、未操作相機、未 commit／push／發布。

### 本次識別值（僅追溯，不作 runtime 配對）

以下均為 SHA-256：

fpSup 基底 commit：`e8567bf41a47966e5c2dedeab312f2da19ef5a0b`，另加本輪工作樹修改。
額外 OG 回歸使用的研究樹來源：`build_og3k_gyro.py`
`b2bf9bb9da267aae2a1b916012886e5ff2761f456e21284e81b5cc37cecb2c71`；
`build_og3k_ui_candidate.py`
`1cbf068655e393bdb2c937fe009245ed77e39170466b4c76a42244dc9bc3e904`。

| 檔案（相對 fpSup） | SHA-256 |
|---|---|
| `tools/card-composer/index.html` | `25d4c291293b647d90ce0ef34fa9f6cffb030c824a7ece397e1338b736e2899b` |
| `tools/card-composer/artifact.html` | `8cdf121c861fe335016f736e8180c792eba7e7dbc17e0982b4c427899971a1c5` |
| `releases/fpsup-usbshell-v3.2.0/fpSup.BIN` | `d05ee7f4fb6354cc6de7447e27c54dc1bcabd836d2ed36cf26a9ae607527540a` |
| `releases/fpsup-gyro-v1.13/fpSup.BIN` | `149210ddac0a6648e464596a582215fb55135ac4e5b825711dc7bf07613bd0b8` |
| `releases/fpsup-og3k-v0.2.5a/fpSup.BIN` | `83d5cb0fd9bad8c28199f6163096daa5e650e8842313afa8bb9368d989df1785` |
| `releases/fpsup-og2k-v0.1.2a/fpSup.BIN` | `e6ae63384eebc0fbed34b84d7e77fc10afb3aaa9d6a93a1854f2dc5c8377eaed` |

本節取代下方歷史盤點中的「composer README／STALE 尚未收尾」狀態；其餘歷史事項不因此宣稱完成。

## 2026-09-23 整合更新：boot chain 最小收尾

未來 agent 製作 sup 的單一規範：[SUP_BUILD_RULES.md](../../../fpSup/SUP_BUILD_RULES.md)。
本檔繼續保存實作／驗證結果，不複製另一份守則。

本段與 [OG 共用穩定性紀錄](../../open-gate/notes/OG_BOOT_RESTORE_STABILITY_REVIEW_2026-09-23.md)
協同維護：這份記錄載入鏈的程式與離線驗證，OG 筆記記錄還原／錄影／QS 的上機證據。
下方 2026-09-22 的出貨 bytes、條數與時間量測保留為歷史基準；**不等於這次修改後的新建置已上機**。

### 已實作的三項修正

1. **保留 OG 還原入口。** 直接 UI builder 原本已將 `0xC0731600` 放進 BIN header；
   中間的 `build_og3k_gyro.py` 卻仍只接受 entry 0。現在重包裝時保留 canonical entry，
   經 `build_base_card.py --vshl-entry` 交給既有的多入口程式；catalogue 的 `refs()` 也傳遞入口。
   有 shell 與 gyro 時維持 **worker → gyro → restore**，沒有的項目直接省略。
   舊 frozen release 的 entry 0、`OG_FMT_GUARD=0` 都繼續支援。
2. **loader 首次執行 stage2 前，補齊快取處理。** `loader.S` 的
   `0xC000E91C`（D-cache）後加入 `0xC000EABC`（I-cache），然後才 `blx` stage2。
   白話說：檔案已讀進 RAM，不代表 CPU 執行時不會拿到那個地址先前的舊指令；
   stage2 自己後面的快取處理無法補救「還沒成功進入 stage2」這個窗口。
3. **Fast start 的呼叫堆疊對齊。** `store_boot.S` 的保存／恢復集合改為
   `r4-r8,lr`（返回分支用 pc），由 20 bytes 變為 24 bytes；保持進入韌體函式時 SP 對齊 8 bytes。
   命中後仍是還原 LR 再尾呼叫 loader；未命中仍返回，讓 AutoRun 走慢路徑。
   多保存一個暫存器不增加 ARM 指令數，也不增加 bootstrap 的 104 bytes。

### 保持不變的界線

- 不新增相機端 BIN 雜湊、版本配對或結構檢查；builder 原有的產物自檢不是新的 runtime 驗證。
- 不合併兩個 pass、不改 entry 參數／回傳慣例、不引入失敗交易或新的啟動狀態機。
- 現行順序仍為 `loader D/I → stage2 pass 1 → D/I → entry → pass 2 → D/I`；
  Fast start 才有後續 store provision 與 abort，普通卡沒有。
- Fast magic 是 **loader bytes 的 build-time 識別值**，不是 BIN 的識別值，也不是開機時重算 stored body 的完整性檢查。
  相同 loader／Fast 配置下，換相容 BIN 不用換 AutoRun。**這次真的修改了 loader，採用這次修正時需一次更新對應 AutoRun 與 BIN**；
  不可把新 Fast BIN 的 provisioning 與舊 loader 混搭，再把它當作一般 payload 更新。
- 沒有部署相機、寫卡或發布。先前 OG2K restore-entry 封包的上機結果保留在 OG 共用筆記，不能當成這次新 loader 的上機驗證。

### 離線驗證

從專案根目錄執行（`--out` 使用新的測試目錄）：

```sh
python3 -B fpSup/fp_usb_shell/test_boot_chain.py
python3 -B projects/open-gate/build/test_boot_entry_chain.py --out /private/tmp/bootfinish-entry-matrix-official --jobs 3
```

- `test_boot_chain.py`：3 項 unittest 通過。解碼 normal／profile 的實際組譯指令，
  確认 D → I → stage2；檢查 Fast hit／miss 的堆疊與返回指令；normal／Fast／Fast+profile
  下改 BIN 內容及長度，AutoRun 逐 byte 不變。移除 I-cache 呼叫、改回舊五暫存器的負對照會失敗。
- `test_boot_entry_chain.py`：14 組 OG3K／OG2K 建置通過（各 target 的純版 release/debug、
  合併版 release/debug、Fast 合併 debug、guard-off 純版及合併版），純 release 由既有 builder
  自檢確認 BIN 與 canonical UI release 逐 byte 一致。測試用實際 worker／gyro blob 定位、
  解碼多入口表，確認 restore 恰好一次、位置最後，而不是只搜尋位址字串。
- 另有 3 組「僅改 entry，AutoRun 不變」、8 組 catalogue refs fixture（OG3K／OG2K ×
  frozen entry 0／新 restore entry × plain/shell），以及 4 組新 source refs BIN 與直接合併建置
  的逐 byte 一致檢查，全部通過。Catalogue 只測 `refs()`，未執行寫網站的 `main()`；
  測試用 UI-record manifest fixture，不改凍結發行品或宣稱已重新發布合併網頁。
- 新 normal loader **260 B**、profile **288 B**，都在 468 B store 容量內；bootstrap **104 B**。
  一般 **104** 條命令、Fast 完整腳本 **169**、Fast+profile **176**；Fast hit 前段仍為 **69**。
  舊版 103／168 條與 256 B 的數字不直接覆蓋；本次沒有重測開機時間。
- 系統 Python 與 Homebrew Python 的機器碼 unittest 都通過。Unicorn 最小 ARM 試跑在
  `emu_start` 以 exit 132 中止，**未取得模擬執行通過的證據**；以上是建置與機器碼靜態檢查。

測試報告及每張卡的 SHA-256：`/private/tmp/bootfinish-entry-matrix/report.json`（staging）與
`/private/tmp/bootfinish-entry-matrix-official/report.json`（正式來源回歸）。每張卡的 `build.log`
放在相同輸出目錄。報告是可重跑的測試產物，開發結論只併在本節與 OG 共用筆記。

---

## 0. 一句話

**一張卡只有兩個檔:`AutoRun.txt` 和 `fpSup.BIN`,放 SD 卡根目錄。**
`AutoRun.txt` 現在跟產品無關 —— 三個出貨產品的 `AutoRun.txt` 只差橫幅那三行。
所有內容都在 `fpSup.BIN`。

實測(2026-09-22,`releases/` 底下三張現行卡):

```
fpsup-gyro-v1.12.1   AutoRun 103 條(71 mem set)  fpSup.BIN 14 區段  entry 0x00000844
fpsup-usbshell-v3.1.1 同上 103 條                fpSup.BIN 10 區段  entry 0x0000018C
fpsup-og3k-v0.2.4a   同上 103 條                fpSup.BIN 80 區段  entry 0  (純靜態寫入)
```

`diff` 三個 `AutoRun.txt`:只有 `display text fpSup-XXX!` 那三行不同。

---

## 1. 相機開機時發生什麼(出貨版)

`AutoRun.txt` 是韌體 shell 的腳本,開機時由直譯器逐行執行。103 條分成四段:

**① 畫面(4 條 + 進度條)**
`display monitor 0 1`、文字顏色 `0xC0BB1208`、x/y 兩個立即數
(`0xC03E46A0`/`0xC03E4698`,程式碼立即數,所以用覆寫而不是參數)。
之後每個階段三次 `display text` + `display osd 1` —— 重複是因為 OSD 要撐過重繪。

**② 把 loader 寫進空洞(71 條 `mem set`)**
`0xC072DE64..` 264 bytes。這是整份腳本唯一還在「拼字」的東西,
而且**長度不再隨內容成長** —— 加功能是加 `fpSup.BIN` 的區段,不是加指令。

**③ 借 echo 的 handler 跑一次(4 條)**

```
mem set 0xC0BAC2F8 0xC072DE64     ← 把 echo 的 handler 指到 loader
echo                               ← 在 shell dispatcher 的任務裡執行,讀檔是正常的事
mem set 0xC0BAC2F8 0xC03D99A0     ← 還原(寫三次,因為 mem set 會掉寫入)
```

loader 在這一次呼叫裡做完全部的事:

```
向配置器要 64 KiB staging(class 0 USER,H_GET 0xC001D740)
  +0x0000 file object   +0x1000 檔案本體(最多 0xF000)
開 \fpSup.BIN(VOL_SD=1)→ 讀 → 關 → 檢查 magic "VBIN" → 清快取(0xC000E91C)
分支到 stage2(檔案第一個區段,destination 0,就地執行)
  pass 1  放所有 firmware 位址的區段(≥0x40000000)
  s2_publish  D-cache + I-cache,在任何放進去的東西被執行之前
  呼叫 header 的 entry —— 是「呼叫」不是「跳」,它必須回來
                          (payload 在這裡自己跟配置器要記憶體並發佈 0xC3757A7C)
  pass 2  放 destination < 0x40000000 的區段 = pool 的位移
回到 loader → 釋放 staging → 回到 echo handler
```

檔案缺了或截斷 → magic 不合 → 什麼都不做,相機就是一台普通相機。

**④ 橫幅**
清畫面、`display text fpSup-Gyro-v1.12.1!` ×3。橫幅**是辨識這張卡的唯一方法**。

之後是填充註解,補到 32768 bytes(`PAD_TO`)—— 因為 `putfile` 的 mode 7 覆寫但不截斷。

### 快載入(fast start)—— 完整順序

不在出貨卡上(`release_card.py` 會擋)。`--store-boot` 建出來的 AutoRun 是 **168 條**,
但那是一份**有兩條路**的腳本:第二次之後開機只走前面 69 條就停了。

**AutoRun(第一段,兩條路共用)**

```
display monitor / 顏色 / x / y      3 條 mem set
26 條 mem set → 0xC072F700          store_boot,26 個字
mem set 0xC0BAC2F8 0xC072F700       echo handler 指向 store_boot
畫橫幅                               ← 在 echo 之前畫,因為快路徑會停在這個畫面
echo                                 ① 執行 store_boot
echo                                 ② 見下,一行兩個意思
```

**① store_boot(`0xC072F700`,借 echo 的 handler 跑)**

```
讀 [0xC3075264] 與 build 時算出的 magic = sha256(loader 的 bytes)[0:4]
  不同 → mov r0,#0; return      ← 什麼都沒碰,AutoRun 繼續往下(慢路徑)
  相同 → 把設定區 +4 起的 STORE_LEN bytes 複製到 0xC072DE64
          D-cache(0xC000E91C)+ I-cache(0xC000EABC)
          bx r0 → **直接尾呼叫進 loader**
```

補一個修正:**這裡沒有第二次 hook echo**。store_boot 是 `bx`,loader 是在
**同一次 echo 呼叫**裡跑完的。magic 是雜湊不是字串,所以「設定區裡是另一版 loader」
這個狀態不可能發生 —— loader 改一個指令,magic 就變,卡片自動退回慢路徑。

**② loader(`0xC072DE64`,256 bytes;設定區裝得下 468)**

```
H_GET(desc, class 0 USER, 64 KiB) → H_ADDR    失敗就什麼都不放(load_fail)
  +0x0000 file object   +0x1000 檔案(最多 0xF000)
F_MGR → F_VOL(#0)= 相機現在指的那個卷
  開 \fpSup.BIN 失敗 → F_DTOR → 退回 VOL_SD=1 再開一次
  (⚠ 開機前插 SSD 就是從這裡壞掉的:F_VOL 回 SSD,SSD 上沒有這個檔)
F_READ → F_CLOSE → F_DTOR
檢查 [buf] == "VBIN",不合 → load_stop
F_CACHE → blx 到「表尾 = 第一個區段的資料」= stage2(destination 0,就地執行)
```

**③ stage2(在 staging buffer 裡就地跑)**

```
pass 1   放所有 ≥0x40000000 的區段
s2_publish
呼叫 header 的 entry(<0x40000000 就是檔內位移;**呼叫不是跳,它必須回來**)
         payload 在這裡自己跟配置器要記憶體,並發佈到 0xC3757A7C
pass 2   放 <0x40000000 的區段 = 上面那塊記憶體的位移(沒發佈就整個跳過)
s2_publish

#ifdef STORE_PROVISION      ← 只有有快載入的卡才編進來
   store 的 magic == 這次 build 的 magic ?
     相同 → 什麼都不做(已經是這一版)
     不同 → 把 0xC072DE64 的 STORE_LEN bytes 寫進設定區 +4,**magic 最後寫**
            (寫到一半斷電,下次開機 magic 不合,自動走慢路徑)
   ← 這就是「第一次開機種下去」的那一步,而且是在 loader **證明自己能用之後**
     才寫 flash:檔開了、區段放完、entry 回來了
#ifdef ARM_ABORT
   mem: [0xC0BAC2F8] = 0xC072F080   ← 把 echo handler 指到 abort
```

**④ 回程與停止**

```
stage2 return → loader 釋放 staging(H_FREE)→ 回到 echo handler → AutoRun 讀下一行
下一行就是 ②那個 echo:此刻 slot 指著 abort
abort(0xC072F080):
   先把 handler 還原成 0xC03D99A0(等一下那三條還原命令不會被執行到)
   走註冊表 0xC2F20FC0 找到 per-line callback == 0xC03DA7A8 的那一筆
   F_CLOSE 腳本自己的檔(少了這個,之後任何人都開不了 \AutoRun.txt,直到重開機)
   CALL 0xC0420D90 彈出註冊項、depth -= 1
   清 [ctx+0x90] running byte  → 直譯器下一次讀就是 EOF
腳本停止,畫面停在稍早畫的橫幅
```

**慢路徑(第一次開機,或 magic 不合)**:兩個 `echo` 都是 store_boot 的
「什麼都沒碰」→ 進度跳到 **050**(整個開機唯一一處大聲說「這不是快路徑」)→
還原 handler → 64 條 `mem set` 拼出 loader → `echo` → 走一模一樣的 ②③,
差別只在 stage2 這次會把 loader 種進設定區。

**實測條數(2026-09-22 現地重建)**

| | 執行的命令 | mem set | display | echo |
|---|---|---|---|---|
| 快路徑(第二次之後) | **69** | 30 | 36 | 2 |
| 慢路徑(第一次) | 168 | 71+26 | 42 | 3 |
| 一般出貨卡 | 103 | 71 | 30 | 1 |

⚠ 「快載入 = 26 條」這個講法要修正:**26 是 store_boot 的 26 個 `mem set`**,
不是執行的命令數。快路徑實際跑 69 條,而且它的 `display` 比一般卡**多 6 條**。
按 `boot-time-levers` 的實測(display ≈283 ms、`mem set` 便宜得多),
省下的 41 條 `mem set` 有一部分被那 6 條 display 吃掉 —— **快載入到底快多少沒有直接量過**,
兩張卡各測一次就知道。

## 1.45 開機時間:載入其實是免費的(2026-09-22 實機)

相機自己的 `TICK_US` 開機歸零,所以在 loader 進來和 stage2 結束各寫一個戳記
(`0xC072F6F4` / `0xC072F6F8`,`mem get 0xC072F6F4,,8`),就能把開機切開:

```
通電 → loader 拿到控制權   11,689 ms    相機自己開機 ≈8,876 + AutoRun 42 條 ≈2,813
loader + stage2 + entry         3.5 ms  ← 讀檔、放區段、跑 worker,全部
```

**`fpSup.BIN` 裡放什麼、放多少,對開機時間幾乎沒有影響。** 這就是為什麼
「把東西從 AutoRun 搬進檔案」從頭到尾都是對的方向 —— 72 ms/字換成 0。

指令單價:`display osd` 76 ms、`display text` 38 ms、`mem set` 72 ms、
`display monitor` 83 ms。快載入的真實價值是**每次省 2.18 s、第一次多付 4.35 s**。

完整的量法、數字、兩次凍結的解剖與兩道新守衛:[`BOOT_TIMING.md`](BOOT_TIMING.md)。

## 1.5 空洞區 = cave = 注入區 —— 它主要放的是指標

三個名字同一件事:韌體 RAM 裡那段原本全零、沒人用的縫。樹裡多半寫「注入區」
(28 處)或「零區」(11 處),英文一律 `cave`;這份跟著使用者的講法寫「空洞區」。


`0xC072D000..0xC0730000`。**不是住處,是錨點區**:真正的程式碼在配置器給的記憶體裡,
cave 只留「固定位址才有意義」的東西 —— hook stub、狀態字、指向別處的指標。
(記憶 `cave-zero-map-is-full`:stock 只有兩段零區,扣掉現有主人根本沒有 3 KB 連續空間,
所以別挑固定位址,跟分配器要。)

```
0xC072DE64  stage1 / loader        256 B   AutoRun 拼出來,或 store_boot 從設定區複製過來
0xC072E064  LOADER_END = CAVE_LOW+0x200    payload 只能從這裡以上開始

            —— 以下是 gyro payload 的 hook stub(必須在固定位址,因為韌體要跳進來)——
0xC072E200  accel_hook      0xC072E300  gyro_drain
0xC072E4E0  rec start       0xC072E620  rec stop      0xC072E6A0  mode hook
0xC072EC60  stream_space

0xC072EC38  -> stream_claim   ┐ 四個**指標字**。producer 是各自獨立的 blob,
0xC072EC3C  -> stream_commit  │ 分支解析不過去,所以 build 把位址算好寫成字,
0xC072EC40  -> gyro_drain     │ 互相呼叫都走這四個字。
0xC072EC44  -> stream_flush   ┘

0xC072EFB4  park stub              payload 不可越過(build_base_card.check() 擋)
0xC072F000  worker state 16 words  0xC072F040 caplen
0xC072F050  WPOOL_PTR   ┐ worker 的「目錄」:worker 的程式碼**不在 cave**,
0xC072F054  WPOOL_SIZE  │ 它自己跟分配器要池、把自己複製進去,
0xC072F058  WCODE_PTR   ┘ cave 留下的只有主機工具找得到它的三個字
0xC072F080  abort                  停止 AutoRun 的那段,由 fpSup.BIN 放進來
0xC072F6D8  POOL_DESC              loader 的配置器描述元,只在開機那幾秒用
0xC072F6F8  STORE_FROM             舊的 store_boot→loader 握手字,現已不用
0xC072F700  store_boot             26 個字;**不能放 CAVE_LOW**,它會蓋掉自己
0xC0730000  CAVE_END
```

不在 cave 但同一組概念的一個字:

```
0xC3757A7C  FRAMEBUF   payload 的 entry 把它要到的池位址發佈在這裡,
                       stage2 的 pass 2 讀它來把「池位移」換算成真位址。
                       loader **不寫**它 —— loader 的 staging 是要還回去的,
                       指向已釋放的記憶體比指向 0 更糟。
```

## 1.6 stage1 / stage2 —— 分界線是「檔案進記憶體了沒」

樹裡沒有 `stage1` 這個名字(只有 `loader.S` 和「first half」),但分法就是這個:

| | stage1 = `loader.S` | stage2 = `stage2.S` |
|---|---|---|
| 住哪 | cave `0xC072DE64`,256 bytes | fpSup.BIN 的**第一個區段**,destination 0 |
| 怎麼到位 | 64 條 `mem set` 拼出來,或從設定區複製 | 跟著檔案一起被讀進 staging buffer |
| 怎麼執行 | 借 echo 的 handler 呼叫 | 就地執行,**不複製**(所以「免費」) |
| 成本 | 每個字一條 `mem set` | 0 |
| 做什麼 | 要記憶體、開檔、讀、關、驗 "VBIN" | 放區段、快取、呼叫 entry、種 flash、arm abort |
| 限制 | **必須塞進設定區的 468 bytes** | 只受 32 KB 檔案大小限制 |

規則就一句:**檔案還沒進記憶體之前非做不可的,才留在 stage1。**
`abort` 當初在 stage1 裡佔了 464 中的 128 bytes,搬成 stage2 放的一個 cave 區段,
設定區就多出四分之一 —— 這是同一條規則的一次應用,不是省程式碼而已。

## 1.7 誰還在濫用空洞區(2026-09-22 逐張卡清點)

把 `releases/` 每張卡的 VBIN 解開,按目的位址分類:

| 卡 | cave | firmware 補丁 | dest 0(就地執行) |
|---|---|---|---|
| og3k v0.2.4a / og2k v0.1.1a | **0 段** | 79 段 12.7 KB | 1 段 |
| usbshell v3.1.1 | 1 段 **96 B**(狀態字) | 7 段 28 B | 2 段 2088 B |
| usbshell v3.1.0(上一版) | 1 段 **1608 B**(worker 本體) | 0 | 1 段 |
| **gyro v1.12.1** | **11 段 1736 B** | 1 段 4 B | 2 段 11212 B |

**og3k/og2k 是乾淨的**(純韌體補丁),**usbshell 已經改好了** ——
v3.1.0 把 1608 B 的 worker 塞在 `0xC072F050`(而那正好壓在 `ABORT_AT 0xC072F080` 上,
是快載入卡建不出來的那次事故);v3.1.1 之後 worker 自己要池、把自己複製進去,
cave 只剩 96 B 狀態字。

**還在濫用的是 gyro。** 11 段拆開來看:

```
必須固定位址(韌體 BL 跳進來)
  0xC072E200  152  accel   ← 0xC050D4C8
  0xC072E4E0  196  start   ← 0xC03790B8
  0xC072E620  124  stop    ← 0xC038C484
  0xC072E6A0   64  mode    ← 0xC0058310            小計 536 B
必須固定位址(別人讀它)
  0xC072EC38..EC44  16     四個指標字
  0xC072EFB4   76         park stub(是界線本身)
沒有任何東西直接跳進來 —— imu_stream_deploy.py 自己的註解就寫「Not hooks. Called.」
  0xC072E300  324  drain
  0xC072EC60  784  space                            小計 1108 B  ← 64%
```

`drain` 和 `space` 是**被那四個指標字呼叫的**,不是 hook。按這棵樹自己的規則
(`cave-zero-map-is-full`:「cave 只留錨點 —— 狀態/trampoline/descriptor」),
**這 1108 B 本來就該在池裡**,cave 只留那四個字。11 KB 的 writer 早就搬走了
(`gsup_launch` 要池、複製進去),這兩段是沒跟上的。

**而且空間真的不夠了。** payload 視窗 `0xC072E064..0xC072EFB4` 共 3920 B:

```
用掉 1660 B,剩 2260 B,但碎成 8 個空隙,最大的一個只有 1368 B
最後一段結束於 0xC072EF70,離 park stub 只剩 68 B
```

「沒有 3 KB 連續空間」這句話現在有數字了。

### 已經搬了(2026-09-22)

`drain` 和 `space` 現在是 writer blob 的一部分(`writer_core.inc.S` 的 `#include`),
四個指標字由 `gsup_boot` 從 routine table 填,和 `take_open`/`writer_post` 同一個形狀。

```
gcsv 卡   區段 14 → 8    cave 1736 B → 612 B(只剩四個 hook stub + park stub)
blob      11,212 B → 12,420 B(1,108 B 換到池裡,池是一 MB)
AutoRun   103 條,沒變(它本來就不隨內容成長)
```

payload 視窗(`0xC072E064..0xC072EFB4`,3920 B)連狀態字一起算:

```
           用掉      空隙   最大連續
v1.12.1    1964 B    11 個   684 B
搬完        840 B     9 個   856 B
```

**空間總量多了 1124 B,但最大連續只從 684 變 856** —— 因為切碎視窗的是散落的狀態字
(`STATE_AT` 0xC072E1B0、`ACC_STATE` 0xC072E8C0、writer counters 0xC072E8E0、
block state 0xC072EBA0、writer words 0xC072EC00),不是這兩段程式碼。
要一大塊連續空間的話,下一根槓桿是那些字,不是再搬程式碼。

改了什麼:

| 檔 | 改動 |
|---|---|
| `imu_stream.inc.S` | 加 include guard(兩處 include 同一個標頭會重複定義巨集) |
| `writer_core.inc.S` | `#include` 那兩個檔;`gsup_offsets` 加四個字(+0x30..0x3C);`gsup_boot` 在 arm hook 之前寫那四個 cave 字 |
| `ring_task_deploy.py` | `GSUP_ROUTINES` 追加四個名字(**只能往後加**,gsup_boot 用固定偏移讀) |
| `imu_stream_deploy.py` | `PRODUCERS` 移除 drain/space;`arm()`/`stage()` 從 `R.place()` 解出位址;刪掉沒人用的 `_symbols()` |
| `build_base_card.py` | 不再產生那四個指標字的區段 |
| `release_card.py` | 區段清單只剩三個 hook;改成查 blob 的 routine table(11 個 routine,零就是掉了) |
| `test_imu_stream.py` | 三個新測試:兩檔在 blob 裡、table 順序是 ABI、**四個字必須在任何 hook 被 arm 之前寫入** |
| `tools/card-composer/build_catalogue.py` | 兩筆 STALE(見下) |

**離線驗到什麼**:兩個 edition 都建得起來、og3k `--dev-card` 合併卡建得起來、
149 個測試通過(4 個 fail 是改動前就在的,全在已作廢的 `logger.S` 那條線);
新的 routine-table 檢查與「先寫字再 arm」檢查都做過 mutation —— 把表格字清零、
把四個寫入搬到 arm 之後,兩個檢查都抓得到。

**上機驗過了(2026-09-22)**,卡是 `fpSup-DEV-POOL!`:

```
AutoRun.txt  a7860ae852bed102b4a52e8db99ac3517667290d868f1b28e50da137353c3fc0
fpSup.BIN    24c7f0477c1bcc98bc95e93c8b92823b581516795a9dbaeb400438e974d7625a
```

開機:介面 class 變 ff/ff/ff、shell `pong`。pool = `0x4507B400`,四個字讀回來

```
STREAM_CLAIMFN  0x450C0180 = pool+0x44000+0xD80    STREAM_COMMITFN 0x450C02B0 (+0xEB0)
STREAM_FLUSHFN  0x450C03AC = pool+0x44000+0xFAC    STREAM_DRAINFN  0x450C0490 (+0x1090)
```

四個都推得出同一個 blob base,不是巧合對上一個;`0x450C0490` 前四個字
`E92D53FF E3030FCC E34C031E E5900000` 與本機 blob 的 `gyro_drain` 逐字相同。
舊位址 `0xC072E300`/`0xC072EC60` 全零。四個 hook 的 branch word 與本機算出的相同
(arm 是 `gsup_boot` 最後一步,所以它整條走完),八個 block 也拿到了。

一次 3.6 秒的 CinemaDNG:

```
GCOUNT 8965 = .gcsv 的 8965 列(逐筆相符)   t 0..8964,步長全為 1,沒有非遞增
其中 155 列帶加速度計讀數                    dropped_blocks=000000  B_DROPS 0  T_LOST 0
A001_092.gcsv  155,448 B(T_BYTES 0x25E30,5 次寫入)
A001_092.json  1,030 B — mode 106、10.556 ms、LUMIX S 40/F2、四個畸變係數都在
```

drain 平均每 58 個樣本跑一次(約 23 ms),韌體的 ring 是 600 筆(240 ms),餘裕很大。
(順帶:accel 這次算起來約 43 Hz,比筆記裡的 100 Hz 低 —— 跟這次搬家無關,改天再看。)

**合併器**:`gyro+og3k` 與 `gyro+og2k` 兩個重現檢查現在是 STALE ——
目錄合併的是**凍結的 v1.12.1**(舊佈局),參考卡是**從源碼重建**(新佈局),
兩邊都對、在切出新版之前不可能相同。`index.html` 沒有變,網頁仍然發 v1.12.1。
切版之後要把那兩筆 STALE 刪掉(檔案裡的守衛會把「開始通過的 STALE」變成失敗)。

## 1.8 契約:每張卡自己配

**規則一句話:載入器只保證「你的位元組在你說的位址上,而且被呼叫一次」。
記憶體、指標、hook,全部是那張卡自己的事。**

這不是慣例,是目前每一層實際在做的事:

| 誰 | 自己配什麼 | 誰還掉 |
|---|---|---|
| loader | 64 KiB staging(class 0),放檔案和 file object | 自己,`H_FREE`,stage2 回來之後 |
| gyro | 1 MB(`gsup_launch`),自己把 writer 複製進去 | 不還,整個開機期間持有 |
| shell worker | 自己一塊,自己把程式碼複製進去 | 不還 |
| og3k / og2k | **不配** —— entry = 0,純靜態韌體寫入 | — |

「不配」也是合法的答案。契約不要求你配,只要求**你要的東西你自己去要**。

### 完整順序

```
① store_boot        只有快卡。驗 magic = sha256(loader) → 複製 loader 進空洞區
                    → publish 兩級快取 → bx 尾呼叫進 loader(同一次 echo 裡)

② loader            自己配 64 KiB staging(失敗就什麼都不做)
                    F_VOL 當前卷 → 開 \fpSup.BIN → 失敗退回 SD → 讀 → 關
                    驗 "VBIN" → publish → blx 到區段表尾 = stage2(就地執行)

③ stage2   pass 1   放所有 ≥0x40000000 的區段(韌體位址)
           publish  在任何放進去的東西被執行之前
           ⟨無名⟩    呼叫 entry —— 合併卡是 trampoline 逐張呼叫
                    ├── 每張卡:配自己的記憶體
                    ├──         發佈池位址(0xC3757A7C,給自己人讀)
                    ├──         寫自己的 call-through 指標字進空洞區
                    ├──         最後才 arm 韌體 hook(配置失敗就一個都不 arm)
                    └──         **返回**
           pass 2   放 <0x40000000 的區段 = 上面那塊記憶體的位移
           publish
           STORE_PROVISION  store magic 不同才寫 flash,magic 最後寫
           ARM_ABORT        echo slot → abort

④ loader            H_FREE 還掉 staging          ← 唯一的「清除」
⑤ AutoRun           下一行 echo → abort:還原 handler、關腳本檔、
                    彈註冊項、清 running byte → 腳本停止,畫面停在橫幅
```

### 一張卡的 entry:必須 / 不可以

**必須**
- **返回。** 不返回的話:自己的韌體區段有了,pass 2 沒了,設定區沒種,腳本沒停,
  而且沒有任何診斷 —— 沒人活著能講話。
- **配置失敗就什麼都不 arm。** 半個能用的卡比不能用的更糟:take 兩邊都沒了,
  只有一邊是明顯的。
- **arm hook 放最後。** 一個 armed 的 hook 讀到還沒寫的字,不會當機 ——
  每個呼叫端都 guard 零 —— 它會安安靜靜什麼都不記錄。

**不可以**
- 假設別人已經配好池。`0xC3757A7C` 在你之前可能是 0。
- 假設自己是第一個或最後一個。合併卡照目錄順序走,你不知道自己第幾個。
- 呼叫下一張卡。鏈結是 trampoline 的事 —— payload 是從凍結的發行版合併來的,
  裡面沒有「下一個」可以 patch。

### 這條規則現在的兩個後果

**一、pass 2 已經沒有任何一張卡在用。** 逐張清點(2026-09-22):

```
fpsup-gyro-v1.11b   1 個(PGEN,pool+0x44000,10,552 B)   ← 最後一個用戶
其餘 13 張發行版 + 現在建的兩張                 0 個
```

pool-offset 區段是**唯一**需要「別人先發佈一塊記憶體給我用」的機制,
也就是唯一違反「自己配」的東西。v1.12.0 把 writer 改成跟在 `gsup_launch`
後面自己複製進去之後,它就沒有用戶了。真要收的話,stage2 可以塌成
「放區段 → 呼叫 entry → 完成」一趟,但那會動到每張卡的位元組。

**二、`0xC3757A7C` 只剩下「發佈給自己人讀」一個用途。** loader 刻意不寫它
(staging 是要還的,指向已釋放的記憶體比指向 0 更糟);寫它的是 gyro 的
`gsup_launch`,讀它的是 gyro 自己的 `gsup_boot`。它現在是 gyro 內部的一個字,
不是系統級的池指標。

### 還沒遵守契約的地方

- **沒有人清 `store_boot`**(`0xC072F700`,104 B)。它留到重開機。而那個位址
  正好是主機一次性模板區(`TEMPLATE_BLOCK`),所以第一次用 putfile/getfile
  會順手蓋掉 —— 意外,不是設計。
- **沒有人清 `POOL_DESC`**(`0xC072F6D8`,16 B)。loader 還掉 staging 之後,
  那個描述元留在空洞區,實機 dump 裡看得到。
- **呼叫 entry 那一段沒有名字**,連 label 都沒有(`stage2.S:58-73` 內聯)。
  建議 `s2_entries`,跟 `s2_pass`/`s2_publish` 同一個家族;會動位元組,
  所以跟下次切版一起做。

## 2. 誰把這兩個檔建出來

**唯一會寫出 `AutoRun.txt` 和 `fpSup.BIN` 的程式是
`fpSup/fp_usb_shell/build_autorun.py`。** 其他都是它的前端。

```
gyro        release_card.py <edition> <version>
              └─ build_base_card.py --edition {base,gcsv} --version …
                   ├─ 組每個 producer 區段(位址讀自 imu_stream_deploy.PRODUCERS)
                   ├─ launch()  = gsup_launch.S + writer(destination 0)
                   ├─ check()   重疊 / 不可碰 park stub / 不可落在 loader
                   └─ build_autorun.py --loader --no-shell --also-bin …×N --boot-bin
              └─ check_sections()  必備區段清單 + 恰好兩個 destination-0 + 沒有 abort
              └─ zip + SHA256SUMS

og3k/og2k   OG_TARGET=og2k build_og3k_gyro.py --no-gyro --release
              └─ build_og3k_ui_candidate.py --release  (原生 UI 的 360 records)
              └─ build_autorun.py --loader --no-shell --also-bin …×N
            (帶 gyro 的合併版只有 --reference / --dev-card,不是出貨路徑)

usbshell    build_autorun.py --loader   (worker 自己就是 payload,entry 在檔內)

合併版      fpSup/tools/card-composer/index.html —— 瀏覽器裡把 releases/ 的
            VBIN 串接起來;build_catalogue.py 重建目錄並用腳本重算五種組合驗證
```

開關的意思:`--no-shell` = 不放 worker、不打端點補丁(但**介面 class 補丁一直在**,
沒有它主機的 PTP stack 會搶走 interface 0);`--debug` = 留著 shell 以便事後問相機。

## 3. 發行

```
releases/fpsup-<product>-v<num>[<qual>]/   AutoRun.txt  fpSup.BIN  ABOUT.txt  README.txt
tools/build_releases.py                    從上面那個目錄產生首頁表格(--check 給 CI)
tools/card-composer/build_catalogue.py     從上面那個目錄重建合併器頁面並自我驗證
git push origin <branch>:main              main 一動才算發行(Pages 與下載連結)
git push local HEAD:main                   每一張進相機的測試卡都要先進這裡
```

版本挑最新的規則在 `releases/README.md`:數字逐段比整數,再比 qualifier
(無 > 字母 > `test`)。

---

## 4. 還沒收乾淨的(這就是「很亂」的具體形狀)

**① 舊的 gyro 建置線還在樹裡,而且文件指向它。**
`gyro/release_zip.py` → `build_card.py` + `build_pgen.py`,出三個檔
(`AutoRun.txt`/`fpSup.BIN`/`PGEN.BIN`)。出貨版早就不是這條:
v1.12.1 的 zip 裡只有 `AutoRun.txt`/`fpSup.BIN`/`README.txt`。
- `gyro/README.md` 的表格還在介紹 `build_card.py` / `build_pgen.py` / `makecard.py`
- 記憶 `release-build-must-be-scripted` 寫的是「走 `release_zip.py`」 —— **已過期**,現在是 `release_card.py`
- `.claude/skills/fp-release` 只講 gyro,沒提 `releases/`、`build_releases.py`、`build_catalogue.py`

**② 兩個發行位置,沒有腳本把它們接起來。**
`gyro/release/fp-gyro-sup-v1.12.1.zip` 與 `releases/fpsup-gyro-v1.12.1/`
實測是同樣的 bytes(三個檔 sha256 全同),但那是**手工複製**的 ——
`release_card.py` 不知道 `releases/` 存在,`build_releases.py` 不知道 zip 存在。
og3k / usbshell 根本沒有 zip 那一半。

**③ 建置目錄留著上一代的產物。**
`gyro/release/base/VSHL.BIN`(舊檔名)、`gyro/release/card/PGEN.BIN`+`GYRO/`。
這些是 build 目錄不是產品,但看起來像產品。

**④ 合併器 README 描述的 AutoRun 三配置已經不存在。**
README 說 `plain 135 / shell 189 / shellpush 195` 條、loader 236 vs 356 bytes、
`NOTASK=1`。2026-09-22 實跑三種:**103 條、71 `mem set`、三份指令完全相同**
(`shell` 與 `shellpush` 連註解都一樣,`plain` 只差註解與填充)。
`NOTASK` 在 `loader.S` 裡已經不存在,只剩 `build_autorun.py:729` 一句過期註解。
頁面本身沒事(它每次都重新產生),但 README 會把人帶偏,
而且「三個模板」這件事現在可以直接收成一個。

**⑤ 檔名兩個都要讀。** 寫一律 `fpSup.BIN`;2026-09-19 之前發行的卡是 `VSHL.BIN`,
讀的地方兩個都認。`gyro/autorun/AutoRun.txt`(開發用那份)的註解還寫著 `\VSHL.BIN`。

**⑥ 跨樹依賴。** 只有 `fpSup/` 上 GitHub,但 og3k/og2k 的建置在
`projects/open-gate/build/`(研究樹),`build_catalogue.py` 也從
`HERE.parent.parent.parent` 往上跨出 `fpSup/` 去找。
拿到 fpSup repo 的人建不出 open gate 卡。

**⑦ `build_catalogue.py` 有兩條 STALE 例外**,原因寫在檔案裡:
參考卡是從源碼重建、合併用的是凍結的發行版,兩者本來就會分開。

---

## 相關

- `fpSup/tools/card-composer/README.md` —— 合併器的設計與檢查(數字已過期,見 ④)
- `DEV_MERGED_CARDS.md` —— 開發用合併卡與使用者拿到的差在哪
- `AUTORUN_STORE_BOOT.md` —— 快載入
- `research/firmware/notes/AUTORUN_INTERPRETER_AND_ABORT.md` —— 直譯器與中止要自己彈出註冊項
- `research/firmware/notes/PERSISTENT_STORE_COMMONSAVE.md` —— 設定區那 824 bytes


## 2026-09-24：透明四框載入畫面（offline、opt-in）

共用 `build_autorun.py --loader --four-box-bar` 新增黃色 fp／coral Sup／透明四框。
沒有改 loader bytes、兩 pass 或 entry ABI；共用 stage2 在載入時間戳後，同步畫第四格、
停留 2 秒、還原原廠 UI 並要求 native redraw，然後才返回並釋放 staging。
普通／debug／Fast 使用同一條載入鏈，Fast miss 不倒退，abort 邏輯不變。

首次採用須帶 `AutoRun.txt`、`fpSup.BIN`、新 `FPSUPUI/` 五張小圖；相容 payload-only 更新
保持 AutoRun 和圖檔相同。現行產品／composer 預設未啟用，不更新網站或 frozen releases。
AutoRun display 條數 31→20（普通）、64→20（Fast 全稿）；普通總命令 104→106，
Fast 命中前綴 69→58。圖檔讀量約 1.05 MiB，另有刻意的 2 秒完成停留，實際速度未測。

細節、native addresses、失敗兜底及未驗證邊界見
[BOOT_BANNER §11](../../../research/display/notes/BOOT_BANNER.md)。
離線驗證：`test_boot_chain.py`、`test_splash.py`（ARM 模擬用 firmware mocks）。
依使用者要求沒有上機／寫卡／發布。
