# rawview：相機端 LCD 監看改寫（SIGMA fp 5.02）

目標：LCD 上看到的畫面，**RAW 還有差異的高光與飽和色不要提前剪成一片**；正常範圍依可驗證的顯示轉換呈現。
這是 [`projects/rawlive`](../rawlive/README.md) 規劃的相機端實作；研究依據在 [`research/liveview`](../../research/liveview/README.md)，
對照組包括 [Z CAM E2-F6 的監看 shader](../../zcam_e2f6/notes/FP_LIVEVIEW_COMPARISON.md) 與 [BMCC 6K 的 Rec.709／Gen 5／LUT 資料](../../bmcc6k/notes/FP_LIVEVIEW_COMPARISON.md)。

## 最高原則（使用者，2026-09-24）

**RAW 模式要最大程度還原 RAW 資料，不求好看。** 任何取捨以「螢幕讀數能否正確、完整地反映錄製 RAW」為準：
LV 與錄影的高光範圍一致、顯示是可反推的定義（每檔等寬）、不加創意曲線、不在 LV 路徑多丟任何資訊。

## 最終產品形態

**在 fp 的 Color（色彩模式）選單新增一個「RAW」選項，選到它時 LV 走 rawview 的 raw live 流程。**
要完成的部分：
- **選單**：在色彩模式清單加一列。可參考既有做法：[`lossless-sup/notes/NATIVE_ROW_DONOR.md`](../lossless-sup/notes/NATIVE_ROW_DONOR.md)（借原廠選單列）、open-gate 的新增解析度選項。
- **驅動**：色彩模式本來就會經 PQ 家族切換 tone（`C02D29E0`）與矩陣；選 RAW 時改成：
  LV 感光元件增益跟錄製一致 → 解壓後依 ISO 補數位倍率（`curves/` 的 W(ISO)）→ 平滑肩部顯示曲線 → 色彩矩陣。
- **範圍**：只改監看；錄下來的 RAW 與 metadata 不能變。選 RAW 時 MOV 要怎麼處理待定。

## 產品說明（給使用者）

**RAW 模式：螢幕顯示 12-bit CinemaDNG 實際錄到的 RAW，不求好看。**

- **用法**：COLOR 選單選第 17 列。只在 CinemaDNG 12-bit 時生效（MOV 不支援）。
- **螢幕＝錄到的**：待機增益改成跟錄影一樣，螢幕過曝的地方 DNG 也過曝。
- **頂與底對齊 Rec.709**：依官方各 ISO 的色彩寬容度，感光元件飽和 → 709 白，暗部底線 → 709 黑，中間每檔等寬。
- **中灰位置 ＝ 中灰以下檔數 ÷ 總檔數**（中間不是 709 曲線；709 的 18% 灰約 41%）：

  | ISO | 100 | 200 | 400 | 800 | 1600 | 3200 | 6400 | 12800 | 25600 | 51200 | 102400 |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | 中灰 | 75% | 67% | 59% | 51% | 50% | 56% | 50% | 48% | 45% | 40% | 34% |

- **怎麼看**：純白＝RAW 已飽和；最黑＝只剩雜訊；ISO 100 偏灰白是因為暗部有 9.4 檔。
  M 模式固定曝光時，ISO 100–800 畫面相同（總寬容度都是 12.5 檔）。

## 實作計畫（2026-09-24，三項離線追查整合；未上機）

### 選單（第 3 項追查）

- `menu SetColorMode`（handler `0xC03FE100`，setter `0xC005C958`）。**三套編號** [C]：
  - 選單 enum：0 Standard、1 Vivid、2 Neutral、3 Portrait、4 Landscape、5 Cinema、6 Teal&Orange、7 SunsetRed、8 ForestGreen、9/0xA FOV Blue/Yellow、0xB Mono、**0xC OFF**、0xD PowderBlue、0xE Duotone、0xF WarmGold。
  - GUI 列 0..15（`{enum,gui}` 表 `0xC2E412BC`，列數寫死在 `0xC06C07D8` 的 `mov r2,#0x10`）。
  - PQ enum（`0xC00B8578` 轉換；OFF → **0x24**＝上一節的 36）。不認得的值一律變 Standard。
- 寫入路徑沒有範圍檢查；多處直接比較 0xB/0xC/0xE；Lua 以 `==13/14/15` 判斷；`LV_ColorMode` 16–25 已被單色調色圖示佔用。
- **新增真的 enum 風險最高**（開機變 Standard、各處把它當彩色）。
- **建議編碼：RAW＝原生 OFF（0xC）＋RAM 旗標**。所有 PQ／DNG／MOV／選單判斷都看到真正的 OFF；錄製 metadata 為 OFF。
  旗標在 setter 看到非 0xC 時清除（涵蓋 shell、自訂模式 C1–C3、PTP）。要跨關機保留就存 CommonSave（同 OGSAVE），開機後只在原生仍是 0xC 時套回。
- 選單做法三選一（待決定）：
  - **A 第 17 列「RAW」**：改列數＋在 cave 放 17 項對照表，hook GUI↔enum 兩個轉換；UI 資源要加一個狀態（照 NATIVE_ROW_DONOR／FIXED_POPUP）。最完整、工作量最大。
  - **B 借用一個原廠模式**（如 FOV Classic Yellow）：該列改名／換圖示，選到時內部當 OFF＋旗標。風險最低，但少一個原廠外觀，PTP／EXIF 會記成 FOV Yellow。
  - **C 另開一列私有開關**（lossless-sup 的做法）：色彩清單不動，在別處加「RAW Monitor 開／關」，只在 OFF 時生效。風險低，但不在 Color 選單裡。

### 決定（2026-09-24，使用者）

**RAW 做成 Color 清單的一列（做法 A），並且像其他色彩模式一樣「共用同一套演算法、只換參數」**：
所有模式都走同一個 `FUN_c02d29e0`（tone）／`FUN_c02cfcf0`（矩陣）／YCMAT 路徑，差別只在 root `C2F1A064`（RAM）的 mode→參數表。
RAW＝一組新參數：tone → 我們的每 ISO 表；矩陣、YCMAT → 沿用 OFF；錄製端完全照 OFF，輸出的 CinemaDNG 與選 OFF 時相同。
做法：把 root 的 mode→tone 對照（+0x70）與「不調色」清單（+0x40/+0x44）改指到多了 RAW 的 RAM 副本，並在 PQ 家族的曲線清單（`C097110C` 的 RAM 副本）加上我們的表。
換表、快取、SIGSEQ 排程都交給原廠流程，不 hook `FUN_c011b4c8`。增益（待機用錄影增益、SIG0_RAW_CORR 數位 1×）不在模式參數裡，仍需 hook。

~~**MOV（使用者決定）**：選 RAW 時 MOV 也用 RAW 曲線~~ → **更新（2026-09-24，使用者決定）：RAW 模式只支援 CinemaDNG 12-bit，MOV（以及 8/10-bit）先不支援。**
理由：各錄影格式的增益規則不同（見「MOV 測試」），只有 12-bit 有官方寬容度表且已完整驗證。
錄影格式不是 CinemaDNG 12-bit 時，RAW 模式不作用（hook 旗標視同 0、tone 用原廠 OFF），或選單上 RAW 不可選。

### RAW 模式開啟時要做的事

1. **增益**：hook `0xC0313244`，RAW 旗標開且 gain_state==0（待機）時改用 7（12-bit 錄影規則）→ 類比增益＝錄影值。
2. **數位增益維持 1×**：state 7 會在 **SIG0_RAW_CORR**（LUT 之前）補 800% 數位增益，RAW 模式時要讓這個值為 1×（Q10 `0x400`）。攔截點見下方「增益 hook 設計」。
3. **tone 表**：hook `FUN_c011b4c8`，ctx 0 時換成 `curves/tone2048_iso<N>.u16le`（依目前 ISO 選）；表放自己配置的記憶體、清 D-cache。
4. **色彩**：OFF 的矩陣是 identity；RAW 要的相機矩陣寫 RGBLMAT 第二組（之後做）。

### 增益 hook 設計（離線追查 2026-09-24，未上機）

- **Hook A — gain_state**：`0xC0313244` 原指令 `E595200C`（`ldr r2,[r5,#0xc]`，r5 = helper `0xC343A6A0`）。可用 r0/r1/r3/ip，旗標無用，sp 8-byte 對齊。
  stub：`ldr r2,[r5,#0xc]; cmp r2,#0; bxne lr; ldr r3,=FLAG; ldr r3,[r3]; cmp r3,#0; movne r2,#7; bx lr`。
  只在下一次 `FUN_c03131e0` 執行時生效 → 設旗標後要轉一次 ISO。黑位回呼 `FUN_c0313658` 走另一個 getter，不受影響 [C]。
- **Hook B — RAW_CORR 數位增益 1×**：`0xC032F728` 原指令 `E59C6000`（`ldr r6,[ip]`，最終夾好的增益，Q10）。可用 r0–r3、ip；**sp 未 8-byte 對齊 → stub 必須是 leaf、不能呼叫任何函式**。
  stub：`ldr r6,[ip]; 旗標為 0 → bx lr; r5≠0（bank 1）→ bx lr; mov r6,#0x400; bx lr`。只影響 bank 0（推定 LV）[I]。
- 安裝：`cave.claim` 取 stub 空間（需在 `bl` 範圍內）→ `mem set` 寫入並讀回修正 → callfn `0xC000E91C`（D-cache）＋`0xC000EABC`（I-cache）→ 寫 `bl` 字 → 再 publish。還原＝寫回原字並 publish。
- 預期副作用：state 7 會寫拍照數位欄位 +0x18（下次拍照會以 state 1 重算）[I]；AE 若用 RAW_CORR 之後的統計，自動曝光會以為暗 3 檔（ISO 800）→ **先只在 M 模式、固定 ISO 測**；
  直方圖與 EL Zone 讀顯示影像，會跟著我們的表 [C]。HCG 切換點變成 3200。
- 選表：`0xC343B5A0` 相對增益在拆分之前就寫入，hook 後仍跟隨 ISO [C]；`0xC343B5C0`（+0x38）是被移除的數位倍率 ×100，可交叉核對。

### Color 選單第 17 列「RAW」計畫（離線，2026-09-24，未實作）

**程式 patch**（GUI↔enum 兩個查表都是「第一個符合就返回」[C]）
- 對照表：RAM 複製 `C2E412BC`（16×8）＋`{0xC,16}`；`C06C07CC/07D0`（`E30122BC`/`E34C22E4`）改 movw/movt 指向副本，`C06C07D8` `E3A02010`→`E3A02011`。第 0–15 列不變，全域安全。
- **不 hook 共用函式 `C06C0718`/`C06C0768`**（Cinemagraph、DngDev、LV_ColorMode 等也在用），改 patch 呼叫點：
  - Stub A（GUI→enum）：取代 `bl C06C0718` 於 `C0568950`（`EB055F70`，COLOR 鍵）、`C056D028`（`EB054DBA`，選單）、`C05818B8`（`EB04FB96`，QS）；r1＝GUI 列號，=16 時記下 PEND。
  - Stub B（enum→GUI）：取代 `bl C06C0768` 於 `C0595734`（`EB04AC0B`，`CM_COLFIX_ColorMode` 通知）；結果 15 且旗標開 → 16。`LV_ColorMode` 維持 15（16–25 是單色調色圖示）。
  - Stub C（唯一寫入咽喉）：取代 `C0075CF4` 的 `cmp sl,r6`（`E15A0006`，`FUN_c0075be8`）；色彩模式 item `C31ACDC4`：有 PEND 且新值 0xC → 旗標 1，其他寫入 → 旗標 0；
    OFF↔RAW enum 不變，所以旗標改變時強制「不相等」讓原廠發通知、重新套用。涵蓋選單、COLOR 鍵、QS、shell、色彩包圍、OFF 重設等所有寫入 [C]。
  - 例外：`MenuColorStateProc::v2`（`C0489D48`）在 0..15 間循環會丟掉 RAW；C1–C3 自訂模式可能換 bank 不經 setter → hook 另外以儲存值把關。
- **生效條件**（hook A/B 內判斷）：FLAG && 色彩模式==0xC && 錄影格式==0（CinemaDNG）&& 品質==0（12-bit）。
  設定值：`S=C31AE3B0`，bank＝`C31B32BC`（byte `C31B954C`==0）否則 `C31B8B84`；ColorMode bank+0x12C、RecFormat bank+0x784、CDNG 品質 bank+0x788（0=12、1=14、2=16、3=10、4=8）。
  RecFormat 0=CDNG 需以一次 `mem get` 實機確認（有筆記說法相反）；非 leaf 程式用 getter `C005BE90`／`C005BF28`。
- 變灰：Color 清單的 CSV model 沒有 enable 欄 → 不能變灰；建議「可選但非 12-bit CDNG 時不作用」。

**UI 資源**（RAM 映像 `C1900000..C2D80000`，每頁只解析一次 → 在解析器裡改；沿用 OG3K 的 Thumb hook `C05E6400`／`C05E84D8`／`C05E5B58` 與 FNV 核對）
- 清單是 NBR `C0D22400` 裡的 CSV model：`B1_5_4_Color.cvm`（`C0D502AC`，OFF=`16,set_common_1`）、`ListColorButtonMenu.cvm`（`C0D4DE6C`）、`_EXCL`（`C0D519EC`）、`_EXCL2`（`C0D53C0C`）→ 改成 17 列的副本。
- 最小可行版：三處上限值 15→16（Color 頁 controlValue `C19F54E1`+32、COLOR 鍵頁 `C1D62FEF`+32、QS 三頁 `C234EC96`/`C24844FC`/`C25B57BB`+32）＋17 列 model＋名稱文字 key（Color 頁 Text clip `C19F61F9` 加 t=1066 "RAW"；COLOR 鍵頁 `C1D66BC8` 加 t=533）。
  圖示沿用 OFF 的空白板（`set_common_1`／`qs_common_1`）；沒加 key 的摘要頁會顯示 OFF 的外觀。Color 頁還需新增一個 value 16 的 controlValueEvent（需要插入 record，OG3K 常駐目前不支援）。

### sup 封裝計畫（離線，2026-09-24，未實作）

- **建置路徑**：`build/build_rawview.py` → `build_autorun.py --loader --no-shell --boot-bin rv.bin:0`（開發卡拿掉 `--no-shell`）；不用 `--vshl-entry/--also`；Fast 由 composer 加。
- **記憶體**：照 gyro `gsup_launch.S` 用 USER heap 自己配置 `0x21000`（`0xC001D740` → `0xC001D7F0`）；**不碰 `0xC3757A7C`**。配置失敗就不裝、直接返回。
  佈局：31 × 0x1000 表、插槽 `tabs+0x1F004`（≡4 mod 8）、mode 副本 `tabs+0x1F060`、之後是常駐程式與參數。
- **hook**：開機時從 `CAVE_BUMP`（`0xC072E060`，上限 `0xC072EFB4`）取兩個 8-byte veneer（`ldr pc,[pc,#-4]`＋位址，照 gyro `s_hook`），stub 放在配置的區塊；
  `rv_raw_hooks.S` 改成位置無關（`ldr =P` → `adr`），USB 原型與卡片共用同一份原始碼。加入 `rv_on`／`rv_off` 常駐函式與 magic word（host 工具可經 site A 的 bl→veneer 找到）。
- **表格在相機上產生**：整張合併卡的 BIN 上限 `MAXLEN` 0xF000（61,440 bytes），124 KiB 放不下。
  「每檔等寬」每個 ISO 只差 T = W+L → BIN 只放一張 Q16 `log2(i/1918)`（8 KiB）＋31 組係數＋30 個門檻，開機時算出 31 張表（數毫秒）。
  新增 `rv_tables.py` 為整數公式的唯一定義，建置時比對 `rv_curves` 輸出誤差 ≤1 LSB。rawview BIN 約 10 KiB。
- **開機順序**：檢查兩個 site 與 mode 表第 35 筆為原廠值（否則不裝）→ 配置 → 複製常駐 → 產生表 → 插槽 → mode 副本 → 參數（flag 0）→ veneer → D/I cache → 寫兩個 bl → 再 D/I cache → 返回 0。
  開機時 flag 0、root+0x70 不動，行為與原廠相同；之後由 Color 選單 hook 呼叫 `rv_on/rv_off`。
- **合併卡**：與 og3k／og2k／gyro／usbshell 的位址不衝突；cave 用量 gyro 32＋rawview 16 bytes。release 加 `fpsup-rawview`、`build_catalogue.py` 的 `ORDER` 末尾加 `'rawview'`。
- 待建檔：`build/build_rawview.py`、`build/rv_launch.S`、`build/rv_resident.S`、`build/rv_tables.py`、`build/test_rawview_build.py`。
- 風險：常駐佔用 132 KiB USER heap；4 KiB 對齊與 DMA 一致性沿用原型經驗；開機時若正在 REC／QS 的安全性未證；`rv_off` 後增益要等下次 ISO 變化才回原廠。

### 第一階段：核心 sup 實作（2026-09-24，已建置、離線測試通過、未上機）

- `build/rv_tables.py`：tone 表的整數定義（Q16 log2 表＋每 ISO 係數，上限夾在 B＝螢幕白），與 numpy 版差 ≤1 LSB；卡上資料 8,440 bytes。
- `build/rv_resident.S`：位置無關常駐程式（464 bytes）。參數區 magic `RVW1`、flag、**eff**、last_rel、表、插槽、mode 副本、門檻。
  stub_gs 在待機時計算 eff＝flag && 色彩模式 0xC && 錄影格式 0 && 12-bit（設定 bank 依 `C31B954C` 選 `C31B32BC`／`C31B8B84`，+0x12C/+0x784/+0x788），
  eff 改變時自己切換 root+0x70 並清快取鍵 → 換成 MOV、改色彩模式都會自動回到原廠；stub_dg 只看 eff。
- `build/rv_launch.S`：開機 launcher（676 bytes），照 gyro 模式：原廠值檢查 → USER heap 0x22000 → 4 KiB 對齊 → 算 31 張表 → 插槽／mode 副本 → 常駐＋參數（flag 0）
  → 2 個 CAVE_BUMP veneer → D/I cache → 兩個 bl → D/I cache → 返回 0。
- `build/build_rawview.py`：→ `build_autorun.py --loader --boot-bin`（`--release` 加 `--no-shell`）；檢查 launcher 只呼叫 4 個允許函式。
  產物 `build/out/dev/`：blob 9,580 bytes、fpSup.BIN 32,768 bytes、AutoRun 156 行。
- `build/test_rawview_build.py`（unicorn 模擬）5 項全過：安裝結果逐項核對、原廠值不符時不寫任何東西、預設關閉＝原廠、開啟後選表與增益、非 OFF／MOV／非 12-bit 不作用且中途切 MOV 會還原 root。
- `tools/rv_card.py`：經 site A → veneer 找到卡片版參數區，status／on／off。
- **設定位址已實機確認**：`C31B954C`＝0 → bank A `C31B32BC`；+0x12C／+0x784／+0x788 為 word，改 `menu SetColorMode 0/12`、`SetMovRecFormat 1/0`、`SetMovCinemaDNGQuality 3/0` 都即時跟著變（0xC＝OFF、0＝CinemaDNG、0＝12-bit）。
- **合併卡（shell＋rawview＋fast start）**：`build_rawview.py --fast` → `build_autorun.py --loader --no-ep-patches --store-boot --boot-bin`（與 open-gate `--dev-card --fast` 同一條鏈）。
  以合併器 `build_catalogue.build_fast()` 驗證：AutoRun 與合併器「shell＋fast」範本逐字相同（banner 除外）、store_boot 帶 260-byte loader 的 sha256（0xC4422903）、
  stage2 與 abort 區段與合併器相同、rawview 區段逐位元組相同。banner `fpSup-DEV-RAW-Fast!`。
- **寫卡（2026-09-24 13:49，putfile）**：原卡備份在 `captures/card-backup-2026-09-24/`（AutoRun `ddc2ce33…`、fpSup.BIN 61,440 B `2f2f3b30…`）。
  新 fpSup.BIN 補 0 到 61,440 B（putfile 不截斷）`2cc23de5aa8125f2…`、AutoRun `3818482216f080d8…`，讀回 sha256 相符。
- **第一次開機（慢速，種設定區）後實測**：`rv_card.py status` 經 site A → veneer 找到參數區 `0x4509B200`（RVW1），表格 `0x4507C000`（4 KiB 對齊）、mode 副本 `0x4509B060`；
  flag 0、root 原廠 → 開機即等於原廠。相機自算的表抽查 4 張（k=0/9/15/30）與 `rv_tables` **逐點相同**。
  `on` 後 eff 1、ISO 800 表、類比 985、數位 800→1×，與原型一致。
  **生效條件實測**：切 Standard／MOV／8-bit 時 eff 0、root 回原廠、增益回 3317、tone 回原廠（Standard 為 `0xC0976F34`）；改回即恢復，全部即時。
- **第二次開機（fast start）**：使用者回報比第一次快；`rv_card.py status` 參數區與表格位址與第一次相同、flag 0、原廠行為；LOAD_DONE_US `0xC40F9A`（12.85 s）。
  → **fast start 在合併卡（shell＋rawview）上開機成功**（先前只在 shell-only 卡驗證過）。重開機後 flag 回 0（RAW 預設關閉，尚未持久化）。

### 第二階段：選單程式 patch（2026-09-24，已建置、模擬測試通過、已寫卡、未開機）

- 常駐加入 stub_ma／mb／mc 與參數 pend（+0x94）、guitab（+0x98，17 筆）；常駐 744 bytes、launcher 1,300 bytes、blob 10,484 bytes。
- launcher 另檢查 8 個原廠字（getter `C06C07CC/D0/D8`、三個 GUI→enum 呼叫點、enum→GUI 呼叫點、setter `C0075CF4`），任一不符就整個不裝；
  veneer 5 個（cave 40 bytes，三個 GUI→enum 呼叫點共用一個），getter 的 movw/movt 改指常駐 17 筆表、筆數 17。
- 確認的暫存器慣例：setter `FUN_c0075be8(item, 新值, …)` r4＝item、sl＝舊值、r6＝新值，`beq` 即返回；push 7 個 → sp 未對齊，stub_mc 為 leaf。
  GUI→enum 呼叫點 r1＝GUI 列號（`[r6,#8]`）、結果放 r5；getter 以 r1 為輸出指標、r0 回傳筆數；原廠表 `C2E412BC` 最後一筆 {12,15}＝OFF。
- 模擬測試 9 項全過（新增：選 RAW→強制通知、顯示 16；再選 OFF 清旗標；其他路徑寫入清旗標；pend 但新值非 OFF→不開；其他選單 item 不受影響）。
- `rv_card.py select-raw／select-off`：以 pend＋`menu SetColorMode 12` 模擬選第 17 列（UI 尚未做）。
- 寫卡 13:58：fpSup.BIN（補到 61,440 B）`ee966b82e1c61021…`、AutoRun `3818482216f080d8…`（loader 未變，fast start 的設定區不需重種），讀回相符。
- **上機驗證（fast start 開機）**：getter movw/movt＝`E30B2298`/`E3442509` → `0x4509B298`（參數區＋0x98）、筆數 `E3A02011`；五個呼叫點與 A/B 皆為 bl。
  `select-raw`（ISO 800）：flag 1、eff 1、ISO 800 表、類比 985，**`CM_COLFIX_ColorMode` → 16**；`select-off`：flag 0、原廠（3317、OFF 表），→ 15。
  RAW 狀態下 `menu SetColorMode 0`：flag 立即清 0、Standard 表、→ 0；再 `SetColorMode 12`（無 pend）：一般 OFF、→ 15。**第二階段完成。**
  使用者目視：getter 筆數改 17 後，原本 16 個色彩模式在選單中顯示與切換皆正常。

### 第三階段：UI 資源計畫（離線，2026-09-24）

- **頁面第一次開啟才解析並快取**（`C05E82F1` 經 reader `C18C0460`）[C] → 開機後、開頁前的原地修改有效，不需 hook；頁面開過就要重開機才會生效。
- **NBR 檔案表在載入時被複製到 heap**（`FUN_c05e6400`，ctx+0xAC/+0xB0/+0xB4）[C] → 改大端檔案表無效；檔案內容本身原地使用（`C05E5BB8` 回傳 base+offset），CSV 解析器 `C05F57C8` 容許無 BOM、LF/CR/CRLF。
- 文字不需新字串：字串池 ID `'1634'`（0x359C）在 17 種語言都是 "RAW"。沒有現成寫著 RAW 的 `set_*` 圖示；`set_flash_1/2` 無人參照，可當替換的 donor。
- OG3K 常駐（360 筆 record、7-bit 時間欄位寫死）不能共用；rawview 需自帶 hook，並與 OG3K 串接（讀 hook 點，原廠字就重做、否則解碼 OG3K 的分支再跳過去）。
- **里程碑 1（MENU Color 頁，兩處原地修改）**：`C19F5500` `0x0070410A`→`0x0080410A`（15.0→16.0）；`B1_5_4_Color.cvm`（`C0F8E2EC`，281 B）原地改為無 BOM、前 4 行 CRLF 其餘 LF、加 `17,set_common_1`。
  文字標籤在第 17 列會停在前一個值（沒有 value 16 的 controlValueEvent）；SET 經第二階段 stub A 選到 RAW。測試工具 `tools/rv_ui.py m1`。
- 里程碑 2（COLOR 鍵選單：3 處原地修改＋檔案視圖 hook H1 `C05E5BEC`，換掉 3 個 CSV 與圖示）、里程碑 3（Color 頁 "RAW" 文字：record hook H2 `C05E6400`，含複製事件區塊）、
  里程碑 4（QS：3 處上限＋24 個群組終點 01F4→0215；QS 可能開機就已解析，需要 CINE↔STILL 撥桿才重新解析）——細節見追查報告，未實作。

### 第三階段實測（2026-09-24〜25）

- **畫面辨識（唯讀診斷 `tools/rv_uidiag.py`）**：使用者看到的 Color 選單（COLOR 鍵，MENU 路徑亦同）是 **ColorButtonMenu**，不是 B1_5_4。
  B1_5_4 整個開機週期都沒建立（tree 0），其 model `B1_5_4_Color` 未解析；使用中的是 `ListColorButtonMenu`（16 列、6 欄）。里程碑 1 改錯頁。
  **關閉選單後 ColorButtonMenu 版面與三個 model 都被釋放**（tree 0、child 0）→ 下次開啟會重新解析，不需清快取或重開機。
- **heap 檔案表（唯讀確認）**：原廠 NBR reader `0xC6902940`（+0x24 base `0xC0D22400`、+0xAC 2,259 筆、+0xB0 表 `0xC69922C0`，每筆 {hash, name, offset, size} LE）。
  #75 ListColorButtonMenu（hash `08C7EA7B`，0x342EC，453 B）、#1027 `_EXCL`（`75550E26`，483 B）、#1573 `_EXCL2`（`B0264BF0`，452 B）。
- **里程碑 2（`tools/rv_ui.py m2`，純資料、不掛 hook）**：三個新 CSV（無 BOM、LF；主檔第 1 列 Left→16、第 16 列 Right→16、加 `17,set_common_1,0,15,0,16`；
  `_EXCL`／`_EXCL2` 各加一列停用的 RAW）放 pool 尾端，改 heap 檔案表三筆的 offset（= 新位址 − base）與 size；頁面三值 `C1D63010`／`C1D631AC`（上限 15.0→16.0）、`C1D66CBC`（文字終點 500→533）。
  **結果：COLOR 選單出現第 17 列、可選到，`CM_COLAJ_ColorMode` = 16**（`captures/2026-09-24-ui/SS__0990.JPG`）；文字仍顯示「OFF」（沿用最後一個 key）。
  尚未驗證按 OK 後旗標是否開啟（使用者先重開機，RAM 修改已清除）。

### Fast Start 2 卡與關機寫回（2026-09-25）

- **使用者選 Fast Start 2**。skill fp-merged-card 更新：每張卡都有 stage2 journal＋關機寫回；FS2 = `--store-boot --loader-hook --four-box-bar`，
  電源開關重開走即時路徑、映像保留 → 執行期 patch 若不寫回，下次即時開機會留下指向已不存在記憶體的 hook。
- **H1 取代 heap 檔案表做法**（FS2 在 ~1.4 s 載入，UI 可能尚未建立檔案表）：Thumb `C05E5BEC`（原字 `0x60681840`，adds r0,r0,r1; str r0,[r5,#4]）
  → `B.W` → Thumb veneer（`ldr.w pc,[pc,#0]` `F000F8DF`）→ ARM stub_fv：三個 ListColorButtonMenu CSV 的原廠位址換成常駐區內的新版並改 `[sp]` 大小，回 Thumb `C05E5BF1`。
  頁面三值由 launcher 開機時直接寫（頁面開啟時才解析）。資料唯一定義 `build/rv_uidata.py`。常駐 2,260 B、launcher 1,628 B、blob 12,328 B、veneer 6 個（48 B）。
- **執行期位址宣告成區段**（同 gyro `hook_sites()`）：15 個位址各一個 4-byte「原廠字」區段 → stage2 記 journal、關機寫回；
  也修好上次關機漏跑留下的殘留。**root+0x70（`0xC2F1A0D4`）在 .data（seg1），原廠值要從 `out/seg1_c2ef6e00.bin` 取 `0xC0B3D670`**；
  從 MAIN 映像取會得到 `0x2B78543F`，開機時會寫壞 tone 查表（建置時 assert）。
- **模擬（fp-unicorn-emulation，真實映像）`build/test_rawview_image.py` 18 項**：原廠字即映像指令、所有 patch 點（含 Thumb B.W 解碼）、getter 17 筆、
  韌體自己的 GUI↔enum、選單 stub、增益與 tone 查表、H1 換檔與不影響其他檔、每個原廠字不符時不裝、整張 FS2 卡 loader→journal→rawview→關機寫回、殘留修復。
  突變檢查：14 個突變全部被抓到（含漏宣告 root+0x70、完全不宣告）。另有假記憶體測試 `test_rawview_build.py` 9 項。
- **卡片**：`projects/rawview/cards/rawview-2026-09-25/fs2-1/`（AutoRun `35a3141f…`＝合併器 FS2「shell」範本逐字相同、fpSup.BIN `28a26de2…`、FPSUPUI 0–4）。
  上機前卡上是合併器頁面的 FS2 shell+gyro+og3k（`warm-boot-2026-09-25/page-fs2-shell-gyro-og3k`，備份於 `rawview-2026-09-25/backup-before-rawview/`）。
  AutoRun 相同 → 只換 fpSup.BIN（補到 61,440 B）與 FPSUPUI 0–4（banner 不同），2026-09-25 10:34 寫入，全部讀回 sha256 相符。尚未開機。

### 選 RAW 後變回 OFF 的修正（2026-09-25）

- **上機（fs2-1）**：即時路徑開機、rawview 載入、COLOR 選單第 17 列出現；但按 OK 後顯示回到 OFF，旗標 0、pend 0。
- **原因（推定）**：COLOR 鍵選單 `FUN_c0568930` 是游標移動即時套用的回呼（GUI→enum → setter vt+0x1E0）；選到第 17 列時旗標已開，
  按 OK／離開時韌體再寫一次 OFF（不經 GUI 轉換、無 pend），舊規則「無 pend 一律清」把旗標清掉。
- **修正（fs2-2，fpSup.BIN `a9fac138…`，AutoRun／FPSUPUI 與 fs2-1 相同）**：pend 改三態（16→1、15→2、其他→0）；
  setter：新值 ≠ OFF → 清；pend 1 → 開；pend 2 → 關；其餘（值仍 OFF 的重複寫入）→ 不變。加 8 筆事件紀錄環（常駐 +0x120 計數、+0x124 {tag,a,b,flag}），`rv_card.py dbg` 讀。
  模擬新增「重複寫 OFF 保留 RAW」與紀錄環測試（真實映像 20 項全過），突變「無 pend 一律清」被抓到。10:52 寫卡，讀回相符。

### 第二次修正：enum→GUI 重新同步（2026-09-25）

- **fs2-2 上機仍變回 OFF。事件紀錄**：`GUI→enum 16`（pend 1）→ setter 旗標 0→1 → **`GUI→enum 15`**（pend 2）→ setter 1→0。
  RAW 開啟後強制通知，韌體經某條未 patch 的 enum→GUI 路徑，以 enum 12 查 17 筆表，第一個符合是 {12,15} → 游標拉回第 16 列 → 觸發選 OFF。
  試接 `CM_CHGMOD`（`C0597E3C`）到 stub_mb：無效（`CM_CHGMOD_ColorMode` 讀到 0，不是這個選單的變數），已還原。
  C06C0768 的五個呼叫點：ST_COLBKT `C0594FB0`、CM_COLFIX `C0595734`、CM_DNGDEV `C0597504`、CM_CHGMOD `C0597E3C`、LV_ColorMode `C059DA1C`。
- **修正（fs2-3，fpSup.BIN `a72f05c9…`，11:03 寫卡、讀回相符）**：旗標改變時 stub_mc 對調 guitab 第 16、17 筆的 GUI 值
  → RAW 時為 {12,16},{12,15}：任何 enum→GUI 路徑都得 16；GUI 15／16 → OFF 不變。新增 stub_ml 接 LV_ColorMode 呼叫點（原字 `EB048B51`），16 → 15。
  veneer 7 個（56 B），該位址加入宣告區段。常駐改用 PC 相對巨集 PADR 取參數區（adr 距離不夠）。
  模擬 21 項全過（新增：RAW 時韌體原函式直接回 16、LV 回 15、重新同步後再寫 OFF 保留 RAW）；突變「不對調」「LV 不改回 15」皆抓到。
  已知副作用：RAW 時 ST_COLBKT／CM_DNGDEV 也會拿到 16。

### 第三次修正：其餘 15.0 上限（2026-09-25，成功）

- fs2-3 上機仍出現 `GUI→enum 15`；捲動時的 setter 前面沒有 GUI→enum 事件 → 15 不是查表來的。
  ColorButtonMenu 頁面裡與列表上限同結構的控制值記錄還有 4 個上限 15.0（`C1D5F1FF`、`C1D62A7C`、`C1D63F8B`、`C1D65B26`，+0x20 大端 float）。
- `rv_ui.py caps` 以 shell 在 RAM 改成 16.0 → **選第 17 列按 OK 後旗標 1、eff 1、RAW tone 生效，`CM_COLAJ`／`CM_COLFIX` = 16，不再出現 GUI→enum 15**。
- 做進卡片（fs2-4，fpSup.BIN `b641a5e1…`，11:12 寫卡、讀回相符）：`rv_uidata.PAGE` 加 4 筆 word 修改；launcher 頁面檢查與寫入改成表格驅動（`rv_page.inc` 由 build 產生），
  宣告區段也由 PAGE 產生（共 20 個）。模擬 21 項全過，突變「跳過頁面檢查」「跳過頁面寫入」皆抓到。
- **待處理**：`LV_ColorMode` 也變成 16（應為 15，16–25 是單色調色圖示）。程式碼只有 `C059DA28` 一處引用（已接 stub_ml），
  另兩處在 UI 資源（`C18D5CA4`、`C2DA4104`），推定 Lua 由 `CM_COLFIX_ColorMode` 直接算出。

### 上機確認紀錄

- **2026-09-24 唯讀（`captures/2026-09-24-modetables`，選單 ColorMode 12＝OFF）**：
  - root `C2F1A064` 在 RAM，`{指標, 筆數}` 成對；+0x70 → `C0B3D670`（0x24 筆，mode→tone）、+0x78 → `C0B3D790`（對比）、+0x28/+0x30 已是 RAM 副本（`C2F1AAE8`/`C2F1ADA4`），與追查一致。
  - 待機（ISO 100）與 **12-bit CinemaDNG 錄影中**：tone 都只用 context 0、同一張表（singleton+A0 = hw `30200094` = `C09C3F34`＝OFF 表；+198 = FFFFFFFF；`30200194` = 0）。
    → 錄影中 LCD 與待機共用同一張表，RAW 外觀錄影時不會跳回；CinemaDNG 不經過此表。
  - **MOV**（依原廠色彩模式行為推論，使用者指出）：每個色彩模式在 LCD 上的外觀就是 MOV 的外觀，錄影開始時畫面不跳 → LCD 與 MOV 共用同一張 tone 表，不切換。
    → **選 RAW 時錄 MOV，MOV 會帶 RAW 的曲線**，和選 Standard 時 MOV 帶 Standard 外觀一樣。context 1 推定用於拍照等其他路徑 [I]。
  - 88 張原廠 tone 表：76 張在 index 1873–1919 到頂、之後最多再升 2 碼 → 原廠所有色彩模式都把「白」放在 index 約 1918，RAW 表沿用同一個尺度。

- **2026-09-24 tone 原型 `tools/rv_tone_proto.py on`（使用者執行，OFF、ISO 100）**：
  root+0x70 → `0x45078100`（RAM 副本），singleton+A0 = `0x45077000`（本工具表），hw `30200094` = `0x0141DC00`（＝表位址換算的 word address），
  快取鍵被韌體改回 0x24 → **原廠換表流程完整跑完，硬體正在讀 RAW 表**。「RAW＝一組新參數」確認可行。
  工具在最後確認時讀 +A0 遇到 USB 回覆遺失而中止（已改成重試）；狀態本身正確。

- **燈泡對照（ISO 100、1/60、F2、+2.3；`captures/2026-09-24-screens` SS__0975/0976 = RAW 表、SS__0977 = 原廠 OFF）**：
  原廠 OFF 畫面 28% ≥250、燈泡核心 255；RAW 表 0% ≥250、燈泡核心平在 213（＝當時 ISO 100 白點 0.822）；光暈過渡較緩；中間調幾乎不變（牆面 134 → 138）。
  燈泡核心在 RAW 表也是平的是正確的：ISO 100 時 LV 與錄影類比增益相同，那一片錄下的 RAW 同樣飽和。
  `rv_tone_proto.py off` 還原成功（+A0 回 `C09C3F34`、hw 回 `00270FCD`），不需重開機。
- **使用者決定：每個 ISO 以自己的寬容度頂峰對到顯示的白**。`tone2048_iso<N>` 已改：中灰以下照 BMCC；中灰以上把 0..W(ISO) 檔按比例對到 BMCC 的 0..6.09 檔肩部並正規化，
  感光元件飽和（index 1918）＝ 1.0。中灰各 ISO 0.404–0.407；ISO 100 +1/+2/+3 檔 → 0.68/0.92/0.998，ISO 800 → 0.54/0.68/0.82。

- **新曲線上機（每 ISO 頂峰＝白，ISO 100，SS__0980，構圖與前幾張不同）**：純白（≥250，27.5%）只在燈泡核心（感光元件飽和處）；
  光暈區 0 個像素 ≥250，第 300 行 246 → 245 → 241 → 236 → … → 160 連續下降。ISO 100 只有 3.09 檔，肩部較陡、光暈偏亮，屬正常。

- **使用者決定（取代上一條外觀版）：RAW 模式要正確反映 RAW 資料，不求好看 → 每檔等寬（對數）**。
  `rv_curves.py --map stops`（預設）：顯示值 = (log2(x) + T) / T，x = i/1918（相對感光元件滿位），T = W(ISO) + L(ISO)（官方中灰以上＋以下）。
  白＝感光元件滿位、黑＝官方暗部底線，每檔約 8% 螢幕高度，中灰位置隨 ISO：100 → 75%、400 → 59%、800 → 51%、3200 → 57%。
  L(ISO) 的 1/3 檔內插：100–800 每檔 −1；1600–3200 之間沿 800→1600 斜率外推（不跨 3200 的 HCG 切換）；其他對數內插。舊外觀版保留為 `--map bmcc`。
  **限制**：LUT 線性輸入 2048 點，index 1 已是滿位下約 10.9 檔；LV 8-bit 折線暗部每 16 個 12-bit 值一碼 → LV 實際只分得出滿位下約 8–9 檔，
  最底 3–4 檔在螢幕上是量化雜訊（位置正確、層次不足）。錄製的 12-bit RAW 不受影響。

- **每檔等寬表上機驗證（ISO 100，`captures/2026-09-24-logcheck`：同時讀 LV RAW 與截圖 SS__0984）**：
  由 LV RAW（綠通道，折線還原，黑 253、滿位 4060）算出每塊的預期顯示值，和截圖逐塊（16×16）比較：
  **相關 0.996、殘差 rms 2.8 碼；螢幕 = 0.936 × 預期 + 16.9** → 螢幕亮度確實等於 RAW 的「距飽和檔數」。
  偏差只有黑位墊高約 17 碼（最底約 0.8 檔壓在一起），來自 tone 表之後（YCMAT／CSC 或截圖本身），待查；可在表內預補償。
  **使用者目視：燈罩實物是黑的，LCD 與截圖看起來一樣（都偏灰）** → 截圖＝LCD，黑位墊高約 17 碼也在 LCD 上。
  燈罩在 RAW 裡約在中灰下 3.3 檔（滿位下 6.4 檔），每檔等寬時顯示在約 49%：黑色物體顯示成灰，是 ISO 100 暗部還有 9.41 檔空間的正確結果，
  墊高另外再亮一點。使用者覺得整體偏亮。
  **使用者決定：維持每檔等寬，只修黑位墊高**。`rv_curves.py` 加入顯示端補償 `out = (D − lift/255) / gain`（預設 lift 16.9、gain 0.936），
  預測螢幕值與目標一致（中灰 0.753/0.753、滿位下 6.4 檔 0.489/0.488；8–9 檔處受 LUT index 解析度限制差約 0.01）。
  **上機驗證（`captures/2026-09-24-logcheck2`，SS__0985）：螢幕 = 0.999 × 預期 + 0.0，平均誤差 2.2 碼（約 0.1 檔），相關 0.991**
  → 螢幕值 ÷ 255 × 總寬容度 ＝ 距暗部底線的檔數，可直接讀。
  注意：按截圖鍵後相機會回顯那張截圖幾秒，這段時間讀到的 LV RAW 與截圖都不是即時畫面（SS__0983 即是），要等回顯結束再擷取。

- **增益 hook 上機（`tools/rv_gain_proto.py`，使用者執行 install + on；M 模式、ISO 800）**：stub 在 cave `0xC072E66C`，
  site A `0xC0313244` = `EB106D09`、site B `0xC032F728` = `EB0FFBD8`（bl 目標核對正確）。
  旗標開後 **類比碼 3317 → 985、倍率 5.26 → 1.31**（＝12-bit 錄影），不用轉 ISO 就生效；韌體算出數位 800%，
  但 bank 0 RAW_CORR shadow `0x302104FC..518` 全為 `0x400`（1×）→ hook B 生效（MMIO `301128E8` 讀回 0，不可讀）。
  **LV RAW（`captures/2026-09-24-gain800`）與 ISO 100 原廠 LV RAW 幾乎相同**（G 中位數 174/174、=255 像素 112,686/112,664）
  → ISO 800 的 LV 現在就是 12-bit 錄影實際記錄的資料；255 的那片是燈泡核心，感光元件本身飽和。

- **ISO 800 端到端驗證（增益 hook ＋ ISO 800 RAW 表，`captures/2026-09-24-raw800`，SS__0988）**：
  螢幕 = 0.999 × 預期 + 0.0，平均誤差 2.2 碼，相關 0.991 → **ISO 800 的 LCD 讀數＝12-bit 錄影 RAW 的實際檔數**。
  ISO 800 畫面與 ISO 100 幾乎相同：兩者錄下的 RAW 相同、官方飽和點與底線相同（T＝12.5），只差中灰位置（75% vs 51%）——這正是「反映 RAW」的正確結果；
  原廠畫面則會亮 3 檔、燈泡周圍大片切白。畫面下方曝光補償顯示由 +2.0 變 +3.0，疑為 AE 測光受 hook 影響（M 模式下只影響顯示值），待查。

- **整合原型 `tools/rv_raw.py`（stub `rv_raw_hooks.S`）上機（使用者授權由 agent 執行）**：舊原型先完全拆除（兩個 site 回原字、增益回 3317）。
  stub 在 cave `0xC072E6BC`（site A `EB106D3E`、B `EB0FFC29`）；31 張表在 pool `0x45058000`（上傳 68 s，6,364 字補寫），插槽 `0x45078004`、N `0xF08E0DE3`。
  hook A 在每次增益計算時以 r6（這次的相對增益，`FUN_c03131e0` 第二參數，至 hook 點未被改寫 [C]）查門檻選表、改插槽並清快取鍵。
  用 `menu SetIso` 切換驗證（不寫 flash，最後設回 800）：

  | ISO | 相對增益 | 類比碼／倍率 | 數位×100（被 hook B 壓成 1×） | tone 表 |
  |---|---|---|---|---|
  | 100 | 117 | 985／1.31 | 100 | ISO 100 |
  | 3200 | 3744 | 1546／1.60 | 500 | ISO 3200 |
  | 6400 | 7488 | 2055／2.00 | 800 | ISO 6400 |
  | 800 | 936 | 985／1.31 | 800 | ISO 800 |

  → **ISO 改變時自動換表完成**（第 1 項）。

- **HCG 與 ISO 1600（`menu SetIso`，1000 未切成功、停在 800）**：ISO 1600 RAW 開 類比 2540／2.63×、原廠 3706／10.53× → 原廠 LV 同樣早 2 檔；
  兩者 HCG 皆 0，未見 640–3199 的 HCG 問題。開關切換正常。
- **錄影（`key MOVON/MOVOFF` 觸發，RAW 開、ISO 800）**：錄影中 gain_state 7（韌體自設）、類比 985、模式 MONIT1_60_LOWP5（enum 0x139）；
  tone 表維持 ISO 800 表 → 錄影中 LCD 保持 RAW 畫面；停止後回 state 0，增益不變。
  ⚠ **待驗證**：hook B 在錄影中也把 bank 0 RAW_CORR 壓成 1×（原廠 800%）。若 CinemaDNG 在 RAW_CORR 之後取樣，錄製 RAW 會被改到。
  **已驗證（`captures/2026-09-24-dngcheck`）**：同場景 ISO 800，A001_031（RAW 開）與 A001_032（RAW 關）各取第 1、30 幀（2016×1344、黑 256、白 4095，每幀 4,143,104 bytes，
  以已知檔名 `A001_nnn_20260924_0000NN.DNG` 直接 getfile，未列片段資料夾）：扣黑位逐塊比值 **0.998**（p10–p90 0.997–0.999）、相關 1.0000、飽和像素數相同
  → **錄製 RAW 未被改到**，RAW_CORR 在 CinemaDNG 取樣點之後，hook B 只影響監看，維持現狀。

- **AE／曝光表（離線追查）**：AE 16×16 統計在 `0x30058000`，取樣點在 RAW_CORR 之前，引擎自己套數位增益（`0xC343B5C0` 數位×100 → `0x30058290/294`，黑位 `0x30058200`）[C]；
  Bv 的 Sv 用的是要求的 ISO。hook B 只改送往硬體的 r6，AE 用的環形緩衝值不變 → **AE 的增益帳是對的**。
  曝光表 +2.0 → +3.0 是真的：類比降低後統計多了 2 檔高光空間，原本在原廠 LV 會切平的燈泡周圍被算進平均（估計 +0.7～0.9 EV，以 1/3 檔顯示為 +3.0）。
  自動曝光在有高光的場景會比原廠暗最多約 1–2 EV，和原廠 12-bit 錄影時的 AE 行為相同，對 RAW 而言更正確 → **不修**。
  其他：AF 前端增益被夾在 511%（`0xC0B56534`），ISO 800 時 CDAF 訊號約為原廠 0.64×，低光 AF 可能較早判定低對比 [I]；AWB 統計多了高光空間，可能小幅偏移 [I]；
  直方圖、EL Zone、臉部偵測讀 tone 之後的影像，跟隨 RAW 表。

- **⚠ 錄影凍結（2026-09-24 12:4x；原以為是 MOV，使用者插卡確認其實是 CinemaDNG）**：RAW 開（`rv_raw.py on`，ISO 800），`key MOVON/MOVOFF` 錄約 0.5 秒後 USB shell 回 `LIBUSB_ERROR_TIMEOUT moved=0/64`，
  相機凍結、需關機重開；MOV 沒有存成（`\CINEMA` 最後仍是 A001_032）。原因未定：(1) 已知的 USB worker 與寫卡 I/O 互鎖（fp-camera-control 注意事項），或 (2) hook 在 MOV 路徑出錯。
  區分方法：先在**未安裝 hook**、shell 連線中錄一段 MOV；不凍結才是 hook 的問題，再裝 hook 單獨測（先只開 hook A，再加 B，再加 tone）。
  **分段測試（重開機後，`tools/rv_movtest.py`，每段錄約 0.5 秒；⚠ 實際格式仍是 CinemaDNG，不是 MOV）**：原廠＋shell → A001_033 ✅；只 hook A → A001_034 ✅；A＋B → A001_035 ✅；
  A＋B＋tone（完整 RAW，ISO 800 表生效）→ A001_036 ✅。**CinemaDNG 下凍結無法重現**，推定為已知的 USB worker 與寫卡 I/O 偶發互鎖，或與「切換 RAW／ISO 後立即錄影」的時序有關，待觀察。
  **MOV 尚未測試**；「MOV 也用 RAW 曲線」未驗證。
  當時錄影設定 `SetMovRecFormat` 0（CinemaDNG）、`SetMovRecSize` **4（OG3K）**：凍結也可能與 OG3K 有關。
  ⚠ open-gate 筆記已確認「OG3K + MOV + 錄影 → 硬凍結」：**MOV 測試前必須先把解析度改成 FHD／UHD**，否則無法區分原因。
  （重開機後 pool 位址改變：表區 `0x45114000`、插槽 `0x45134004`；stub `0xC072E66C`。）

- **MOV 測試（格式 MOV＝`SetMovRecFormat` 1、FHD＝`SetMovRecSize` 2；`captures/2026-09-24-movcheck`）**：0／A／AB／ABT 四段皆正常存檔
  （`\CINEMA\A001_037..040_20260924.MOV`，MOV 直接是檔案、可 getfile；RAW 段 1.48 MB，原廠 1.79 MB），無凍結。
  但兩段畫面都約 90% ≥250：**錄 MOV 時韌體用 MOV 的增益規則** —— ISO 800 錄 MOV：gain_state 3、類比 1546／1.60×、**HCG 1**、數位 125%；
  錄 12-bit CinemaDNG：state 7、985／1.31×、LCG、800%。MOV（Base 100/640）在 ISO 800 已切 HCG，感光元件約早 2.7 檔到頂。
  → **RAW 模式待機時的增益必須跟隨「目前設定的錄影格式」**，否則 LCD 顯示的是 CinemaDNG 的 RAW、不是實際要錄的東西。
  錄影開始時的 state 對照（追查已知，內部編號）：MOV 3；CinemaDNG 位深 12→7、10→6、8→5。
  MOV／8／10-bit 沒有官方寬容度表：白點可由增益模型推（W = 3.09 + log2(ISO/100) − log2(有效類比增益 / ISO100 類比增益)，HCG 的轉換增益以 12-bit ISO 3200 反推），暗部底線需實測。

### 上機順序（每一步都先請同意）

1. 唯讀確認：錄影中 tone context（`30200000..1FF`、`C3414470+A0/+198`）；tone 表輸入尺度（用只把某段 index 設黑的測試表）。
2. 先用 shell 注入的原型逐項驗證 1→2→3，每項都有已驗證的還原步驟；不再用 `imager fixed_gain`。
3. 做選單（A／B／C），照 SUP_BUILD_RULES 封裝成 sup；旗標持久化最後做。

## 設計取捨與跨機型對照

| 項目 | 取自 | rawview 的做法 |
|---|---|---|
| 分層 | Z CAM：解碼 → 單一增益 → 單一矩陣 → 可換的 1D 顯示表 → 面板校正 | 同樣分層；每一級單獨可驗證、可還原 |
| 中灰 | Z CAM 把 18% 灰放在 25% 顯示值（壓暗約 1.1 檔換高光） | 可調曝光偏移，預設參考此值 |
| 高光 | Z CAM 在 +3.65 檔硬切；BMCC Film→Video LUT 是平滑肩部（中性合成輸入 +2/+4/+6 EV → 0.677／0.914／0.986） | **不照抄 Z CAM**：肩部形狀以 BMCC 為參考方向，在第一個不可逆限幅前保留餘量 |
| 色域 | Z CAM 逐通道 clamp，會轉色；BMCC 用 33³ LUT，已證有跨通道處理 | 單靠已確認的 1／3 條 1D tone 表不足以重現任意跨通道 3D LUT；先量出限制，再確認 C_SAT_C／矩陣等其他區塊可完成的範圍 |
| 曲線取樣 | BMCC 硬體曲線 6144 點、輸入軸分段步距 `[1,1,2,4,8,16]`（模型擬合，非 bit-exact），高光段用少點數涵蓋大範圍 | fp tone LUT 2048 點的**輸入軸對應還沒證**（matrix-gamma-audit §7）；要先確定它是線性或分段索引，才能算出高光肩部實際能放多少檔 |
| 依 ISO 選表 | BMCC 每族 13 條，25 組 ISO→曲線索引 | 快照要記 ISO；fp 的 `C02D29E0` 是否也依 ISO 換表要用兩個 ISO 的快照比對 |
| 面板 | Z CAM 每台一份 `cali_display.gamma` | fp 已有獨立的 LCD CSC＋16 點 RGB gamma，最後一級才碰 |

研究明確指出：**第一個 pixel clip 的位置還沒量到**。所以不先改 tone，先量。

### 每個 ISO 一組曲線

fp 各 ISO 的寬容度不同（[ISO_DR_UNDERSTANDING](../../research/imx410/notes/ISO_DR_UNDERSTANDING.md)）：類比增益最高 30 dB（ISO 100→3200），超過改用 ISP 數位增益，高光空間一路減少；
LCG→HCG 切換點依 gain_state 而定：LV `through` 由每台相機的 OTP 決定，12-bit CinemaDNG 是 3200，拍照與 8/10-bit 是 640。
所以監看曲線不能只有一條，要像 BMCC（13 條曲線、25 組 ISO→曲線索引）一樣建一張表：

```
(ISO, 錄影位深) → 這組設定下錄製 RAW 的白點，換算成比中灰高幾檔
               → LV 寫入 8-bit 前的增益／編碼：讓這個白點剛好落在 255 以下
               → 顯示肩部：從肩部起點平滑壓到這個白點
```

**錄製端的白點已有官方數字**：SIGMA Cine Gear 的 EL Zone 資料（[`reference/fp_el_zone_cinegear.png`](reference/fp_el_zone_cinegear.png)）直接標了檔數；
官方 Base ISO 100/3200 柱狀圖（[`reference/fp_iso_latitude_official.jpg`](reference/fp_iso_latitude_official.jpg)）形狀相同，逐像素量出的上緣約偏高 0.2 檔，以下表為準：

| ISO | 100 | 200 | 400 | 800 | 1600 | 3200 | 6400 | 12800 | 25600 | 51200 | 102400 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 中灰以上（白點） | +3.09 | +4.09 | +5.09 | +6.09 | +6.09 | +5.42 | +6.09 | +6.09 | +6.09 | +6.09 | +6.09 |
| 中灰以下 | −9.41 | −8.41 | −7.41 | −6.41 | −6.07 | −7.04 | −6.21 | −5.63 | −4.89 | −4.04 | −3.15 |
| 總寬容度 | 12.50 | 12.50 | 12.50 | 12.50 | 12.16 | 12.46 | 12.30 | 11.72 | 10.98 | 10.13 | 9.24 |
| 飽和點（圖上絕對檔） | 17 | 17 | 17 | 17 | 16 | ≈14.4 | 14 | 13 | 12 | 11 | 10 |

**資料核對（2026-09-24，逐像素量兩張圖）**
- Cine Gear 圖內部一致：每根柱子畫的長度和印出的數字相差 ≤0.13 檔（1 px ≈ 0.036 檔）。
  中灰的絕對位置每升一檔 ISO 正好降 1.0 檔（13.94、12.93、11.93、10.96、9.95、8.98、7.98…），和韌體 rel-gain 表「ISO 100→117、每檔加倍」一致。
- 飽和點 100–800 都在 17.07，1600 降到 16.06，3200 降到 14.37，之後每檔降 1；暗部底線 100–800 固定 4.60，1600 是 3.95，3200 跳到 1.98。
  → 100–800 只改亮度標籤（和 ISO_DR_UNDERSTANDING §4 一致）；1600 起才真的加類比增益；3200 換 HCG，底線大降、飽和點多降 0.7 檔（HCG 轉換增益）。
- 官方柱狀圖上緣整體比 Cine Gear 低 0.17 檔（畫法偏差），**只有 ISO 100 例外，高了 0.21**：扣掉偏差後，ISO 100 約 +3.47，Cine Gear 是 +3.09，差約 0.4 檔。
  官方文件 [`reference/fp_dual_base_iso_2020.pdf`](reference/fp_dual_base_iso_2020.pdf)（SIGMA《Dual Base ISO Technology》，2020-10）內文明寫 ISO 100 headroom **3.09 檔**，
  所以柱狀圖 ISO 100 那根是畫圖誤差，以 Cine Gear／PDF 的數字為準。
- 官方圖下緣是漸層淡出：400 以上和 Cine Gear 相差 ≤0.06 檔；100、200 少了 0.33 檔，推測是長柱淡出太多，不當作差異。
- 本專案 LV 量測時 gain 936 = 117×8 → **ISO 800**，對應錄製白點 +6.09。

EL Zone 色階本身是以 18% 灰為 0、−6…+6 檔上色。**fp 的 EL Zone 在監看時已經依 ISO 把 RAW 換算成「距中灰幾檔」**，
韌體裡應該有一張和上表對應的每 ISO 表（中灰位置或白點）。這是找 LV 編碼與每 ISO 設定的直接線索：
先從 EL Zone 的實作追（候選：[`research/display/sigma_fp_v502_raw_false_color.h`](../../research/display/sigma_fp_v502_raw_false_color.h) 與其 caller）。

讀法（推論）：100→800 高光每檔 ISO 多約 1 檔、暗部少約 1 檔，總寬容度不變，符合「低段 ISO 只是改亮度標籤」；
800 以上白點停在 +6.09；3200 換到第二個原生基準，白點掉到 +5.42、暗部多約一檔。
**適用格式（PDF 第 3 頁證實）：CinemaDNG 12-bit 與 HDMI RAW**，Base ISO 100/3200。PDF 對「standard exposure」的定義是 18% 灰被呈現為 18% 灰的曝光；
灰條＝headroom（到白點），橙條＝leg room（到暗部）。
**MOV 與 CinemaDNG 10/8-bit 的 Base ISO 是 100/640**（PDF 第 2 頁），官方沒給它們的表；640 起切 HCG，所以這些格式的曲線表要另外實測，不能沿用上表。
拍照（JPEG/DNG）也是 100/640。

所以曲線表的第一欄可以直接用這個白點：**監看肩部在每個 ISO 要剛好收在上表的「中灰以上」**。ISO 100 只有 +3.09 檔，肩部很短；800 以上有 +6.09 檔。
剩下要實測的是 LV 這一側：LV 8-bit 在各 ISO 的編碼斜率、上限，以及中灰落在哪個碼值。
兩者之差就是那個 ISO 下 LV 提早丟掉的高光。量測順序：100、400、800、3200、6400。對燈泡量（失焦、畫面留一塊正常亮度的牆面當中灰參考、腳架固定），每次讀兩個槽比對閃爍。

## 階段

1. **來源與基線快照（進行中）** — `tools/rv_snapshot.py` 唯讀讀取監看路徑各級設定；`tools/rv_decode.py` 解讀／比對。
2. **找 LV RAW 來源** — 待機 LV 的 small_raw 緩衝位址與格式；ImgCtrl 幀描述 `0xC3439404` 在待機是空的，不能用。
   離線追查（2026-09-24，未上機）：待機 LV RAW 在 **SIG 環形緩衝**，由 A1 寫入 DMA（`0x301822xx`）每幀填入。
   槽數 `0xC31E0DDC`、槽 handle `0xC31E0DE4+4i`、寬高 `0xC31E0DD4/D8`、槽大小 `0xC31DF6AC`；
   位址 = `(handle & 0x3FFFFFFF)*4 + 0x40000000`；最新交給 ISP 的幀 `0xC31D96D4`（僅 `0xC31DF690`==1 時更新）；
   交叉核對 `0xC375D928/2C`。格式推定 packed RAW12、影像後接 0x18／0x28 附加資料，bit 順序與 endian 未定。
   **實機核對（同日，CINE 待機 MONIT1_60）**：寬高 2016×1344、槽數 2、handle `02A400E0`／`02AE56E6`；
   換算得 `0x4A900380` = `*(0xC375D928)` ✓（換算公式成立），第二槽 `0x4AB95B98` = 第一槽 + 槽大小 ✓。
   槽大小 `0x295818` = 2016×1344×**1 byte** + 0x18 → **待機 LV RAW 是每像素 8-bit，不是 12-bit**
   （對上記憶體配置公式的 enum 8/10→8）。8-bit 是線性截位還是壓縮曲線，要讀像素才知道；這對「tone 前是否已截斷」是關鍵。
   `0xC31D96D4`=0、`0xC31DF690`=0：待機不走交接路徑，最新槽要另判（`0x301822E8 & 7` 或逐槽比對）。
   **第一幀像素（`captures/2026-09-24-standby-01/sigring_slot0_4A900380.bin`，單幀、場景未控制）**：
   - 2016×1344 8-bit，直接排列、無 padding，是可辨場景的 Bayer；綠在 (0,0)/(1,1)，R/B 在 (0,1)/(1,0)（哪個是 R 待定）。
   - 值域 9…152，**152…255 完全沒用到**。
   - 四個通道頂端都是「堆積後陡降」：G 約 144–151 各數百到上千點、152 只剩 40；(0,1) 在 145 截止；(1,0) 在 138 截止。
   - ~~反光處已在 8-bit 來源裡平掉~~ **訂正**：同場景調亮後（`captures/2026-09-24-bright-01`，快門 1/60、F2、gain 936 不變）頂端跟著上移到 255，
     所以 152 只是當時場景最亮處，不是截斷。CRCT bin 在此模式是 1/1 直通，本來就不是候選。
   **調亮後（兩槽結果一致）**：
   - 兩個 G 格位各約 4,400 點**正好等於 255**、(0,1) 約 100 點、(1,0) 最高只到 247 → **8-bit 容器上限 255 是一個硬切**，而且是逐通道：
     反光處 G 先切、另一色還有階調，監看會在這裡開始轉色。
   - 還不知道 255 之上的感光元件訊號是否還有餘量（即 12-bit → 8-bit 轉換是否把可用高光丟掉）。
   - 兩幀逐塊對照的對應關係是凹的（暗 35→78、105→197、145→252），三個格位幾乎同一條；但**補光不是均勻倍率**，
     這個對照不能判定 8-bit 是線性還是壓縮。要用快門階梯（均勻的曝光倍率）再判。
   **快門階梯（`captures/2026-09-24-ladder-*`，同場景；`imager fixed_gain 1 936` + `imager fixed_shutter 1 <µs>`，做完兩者都 `0 0` 關閉，mode_now 回到 1/60、936）**：
   1/480、1/240、1/60 有像素；1/120 那次只存到幀描述，沒有影像。`menu SetShutterSpeed` 從主機寫不進去，要改用 `imager fixed_shutter`，而且 AE 會同時改 gain，所以 gain 也要固定。
   - **8-bit 是「線性＋肩部」，不是全段對數**（訂正同日較早的說法）：把 +1 檔對應串起來（+1 檔兩次＝實測 +2 檔，60→128.1 對 128.2，曝光是純倍率），
     每檔碼值 30 → 32.9 → 38.1 → 48.5 → 69.3 → 105.1 → 140.8 → 182 → 226。扣黑位約 27 後每檔比值 2.07／1.93／1.96／1.98 → **碼值約 100 以下是線性**；
     之上比值掉到 1.85、1.46，變成每檔約 +42 碼的壓縮肩部，最後在 255 硬切。三個格位是同一條曲線。
   - **255 切掉的是還有階調的訊號**：1/480 時 G 值 125–134 的像素（約 10 碼的階調）到 1/60 **全部變成 255**。
     110–125 的像素照每檔約 42 碼的規律延伸（239、249、253），沒有提早變平的跡象，所以不是感光元件先飽和，而是 **LV 8-bit 編碼的上限 255 先到**。
   - 所以在 ISO800（gain 936）時，**第一個截斷就在 LV RAW 寫進 8-bit 的這一步**，比 tone、矩陣、LCD 都早。
     要讓 LCD 保留這段高光，必須改寫入 8-bit 之前的增益或編碼（或整條曲線往下移）；只改 tone 沒有用。
   - 待查：1) 8-bit 編碼曲線與 gain 在哪一級、由哪些暫存器設定（候選：SIG0 前端、RAWBLT、A1 寫入 DMA 的位深轉換）；
     2) 12-bit 錄製 RAW 在同曝光下還有多少餘量；3) ISO100（gain 117）是否也一樣先撞到 255。
   RAW_PUSH.md §1.2 的 `0x50000000` ring 只供 `rawPlay` 回灌，不是 LV 來源。`imager createraw／zero_cut_raw／testpattern`、`rawPlay` 有副作用，不跑。
3. **定位第一個截斷** — 固定場景 A/B：原廠 / 活動 context 換 identity tone / 已確認在 clip 前的共同衰減；灰階與紅藍洋紅漸層分開量。
4. **實作監看轉換** — 只在已證實的監看 context 改；處理 SIGSEQ 排程與 cache 發布；不借用 `C3414DA8`（原廠 context 1 在用）。
5. **封裝 sup** — 照 [`SUP_BUILD_RULES.md`](../SUP_BUILD_RULES.md)：新功能放 BIN、沿用共用 loader，entry 安裝完返回。
6. **驗證** — MOV／DNG／metadata 不變、切模式後仍生效且可還原、面板實測。

## BMCC 6K 研究的接入方式

完整對照見 [BMCC 6K Live View／Rec.709](../../bmcc6k/notes/FP_LIVEVIEW_COMPARISON.md)，原始研究、資料與工具集中於 [BMCC 歸檔](../../bmcc6k/README.md)。

- **可重算的顯示參考**：Film→Video／Extended Video LUT 明訂 Gen 5 Film／Blackmagic Wide Gamut 輸入及 Rec709／BT1886 輸出；33³ LUT 含跨通道處理與不同高光肩部，可補充原本的 Z CAM 對照。
- **先建立正確輸入**：未來若做 fp 的離線 LUT 比較，先用 fp 自身校準把已確認來源轉入正確工作色域與 Film 編碼。Blackmagic 的感測器校準、ISO 選表和硬體曲線封裝不是 fp 參數。
- **分別驗證外觀與硬體能力**：合成 18% 灰經兩份 LUT 的輸出約為 0.405541／0.410959；它們不是 fp LCD 亮度目標，也不能直接替代上表 Z CAM 的中灰參考。先統一曝光尺度、transfer 與 range，再比較灰階和紅／藍／洋紅漸層。
- **保持原來的實作優先序**：確認 LV RAW 來源、定位第一個截斷、證明監看 context 隔離，再選擇機內映射。此次整合沒有新增 fp 3D LUT runtime、顯示 patch 或 SUP。

### 12→8-bit 的實際位置（2026-09-24，離線追查＋實測核對）

- **是 A1 寫入 DMA 內建的 6 段折線**，不是 TBLSD／RAWBLT／RAWOUT，也沒有 ROM 表 [C]。
  `FUN_c0630e90` 在 8-bit（fmt 4）時設 `0x3018220C` bits0–2=3 與 **bit8＝折線啟用**；節點由 `FUN_c0117DF8` 用程式內常數寫入
  A1 `0x30182244..6C`（A2 `0x30182344..6C` 相同），反向（解壓）節點在 SIGSEQ 影子 `0x301A0110..16C`。
  A1 另有每通道增益 `0x30182270/74`（預設 `02000100/01000200`），位在折線之前 [I]。
- 折線（12-bit L → 8-bit）：0–192 ÷16；→544 ÷4；→832 ÷8；→1664 ÷16；→3584 ÷32；之後斜率 15/1024，約 L=4060 到 255。
  8-bit CinemaDNG writer `FUN_c02c4908` 的 LinearizationTable 用的是同一組節點（12/100/136/188/248 ↔ 192/544/832/1664/3584）[C]。
- **實測核對**：快門階梯的碼值用這條折線還原成 12-bit 後，扣黑位 253 每檔剛好翻倍（log2 比值 0.94–1.04，rms 0.029）→ 折線正確，LV 8-bit 可以精確還原成線性。
  前面說的「碼值 100 以下線性、之上 42 碼/檔肩部」就是這條折線。
- **所以 255 不是折線丟掉的，是 12-bit 感光元件讀值到頂**（L≈4060）。折線本身沒有浪費餘量。
- **根本原因（推論，待實測）**：LV 在 ISO 800 用 gain 936（= 117×8，真的 3 檔類比增益）；
  官方表的飽和點在 100–800 不變，表示 12-bit 錄製在 100–800 用的是和 ISO 100 相同的增益、只改亮度標籤。
  若屬實，**ISO 800 時 LV 比錄製 RAW 早 3 檔爆掉**，這就是「RAW 還有、LCD 已經白掉」的來源；ISO 400 早 2 檔、200 早 1 檔、100 相同。
  **實測證實（2026-09-24，ISO 800，同一場景；讀 IMX410 驅動物件 `0xC343B5A0..BF`）**：

  | 狀態 | gain_state | 相對增益 | 類比增益碼 `0xC343B5A8` | 類比倍率 `0xC343B5B4` | HCG |
  |---|---|---|---|---|---|
  | 待機 LV（MONIT1_60） | through | 936 | **3317** | **5.26×** | 0 |
  | 錄 12-bit CDNG（MONIT1_30_HD_LOWP3） | movie_raw_12bit | 936 | **985** | **1.31×** | 0 |

  錄影的類比增益＝ISO 100 待機時的值（AF 研究紀錄 985／1.31×），ISO 800 只是標籤；待機 LV 真的多加 4 倍（2 檔）類比增益。
  → **ISO 800 時 LV 至少比錄製 RAW 早 2 檔爆**；另外 1 檔亮度若也在 A1 折線之前補（候選 `0x30182270/74`），就是早 3 檔，待查。
  `imager mode_now` 印的 gain 兩者都是 936（那是相對增益），不能拿它判斷。
  **修正實驗（同日，`captures/2026-09-24-gain-base` vs `gain-117`）**：待機時 `imager fixed_gain 1 117` → 類比碼 985／1.31×，和錄影相同。
  - 基準（5.26×）有 10,952 個像素在 254–255；改 117 後同一批像素落在 158–166、有層次，全畫面沒有 255，最亮處距上限還有 1.8 檔。
  - 中間調線性比 3.97×＝1.99 檔，等於類比倍率比 4.02×；A1 通道增益 `0x30182270/74` 為 unity（`02000100 01000200`）。
    → 另外 1 檔亮度在 8-bit 之後才補，**ISO 800 時 LV 比錄製早 2 檔爆（不是 3 檔）**。
  - **核心改法已實機驗證**：LV 用錄影的類比增益即可保住高光；亮度差在解壓後補。
  - **注意（2026-09-24 實際發生）**：`imager fixed_gain 0 0` 關閉後，增益停在最後寫入的值，**之後轉 ISO 也不會再改變亮度**。
    寫回原值（`fixed_gain 1 936` 再 `0 0`）只能讓數值對上，仍不會恢復跟隨 ISO；開關快門覆寫也沒用。**只有關機重開才完全恢復。**
    在找出正確的還原方式之前，不再用 `imager fixed_gain` 做實驗。
  - 另見 `imager fixed_gain_state <flag>`：6 = movie raw 12bit。可能可以讓待機 LV 直接套用 12-bit 錄影的增益規則，是 RAW 模式的候選做法；未測，上機前先離線確認還原方式。
- **對實作的意義**：不必改 A1 折線。LV 感光元件增益改用錄製時的增益（100–800 都用 117），剩下的 ISO 倍率移到解壓之後當數位增益 ——
  這正是 BMCC「固定編碼、每 ISO 只換輸入比例」的做法；`rv_curves.py` 的 W(ISO) 就是這個比例。
  只改 A1 折線或 `0x30182270/74` 也行，但 `0x301A0140..16C` 解壓端、EL Zone 都要一致，而且 `FUN_c0117DF8`／`FUN_c0630e90` 會在 LV 啟動或換模式時覆寫。

### RAW 模式・增益部分（離線追查 2026-09-24，未上機）

- **ISO → 類比／數位拆分在 `FUN_c03131E0`**，依 helper `0xC343A6A0`+0x0C 的 gain_state 選規則（v8 → v30 HCG、v31 數位梯）[C]。
  內部編號和 shell 旗標不同：內部 0 through、7 = movie_raw_12bit（shell 的 6）。
  - state 7、rel 936：數位 800%、類比 rel 117 → 碼 985 [C]，和錄影實測一致。
  - state 0：兩點梯度，實測推算約數位 200%、類比碼 3317 [I]。
  - 數位增益寫到 **SIG0_RAW_CORR** shadow `0x302104FC..518`（MMIO `0x301128E8..904`；原誤記為 SIG1），在 A1 8-bit 折線**之後** [C/I]，和「剩下 1 檔在 8-bit 之後補」的實測一致。
- 誰設 gain_state：待機 → 0；錄影開始依位深 5/6/7、MOV 3；錄影結束 → 0；拍照暫時 1 [C]。轉 ISO 不會改 gain_state [C]。
  韌體本身已有「待機用 raw 增益」的 HOLD 路徑（cam-state +0x328），觸發條件不明，且會重設監看模式，不採用。
- **`fixed_gain` 卡住的原因**：`imager fixed_gain 0` 只印字、沒有清掉 helper+0x10；AE 每次都用這個固定值 [C]。
  理論上的還原：`imager fixed_gain 1 -1`（寫回建構時的 −1），再轉一次 ISO [C，未實測]。
- **最小改法**：在 `0xC0313244`（讀 gain_state 的那條指令）放 hook：RAW 旗標開且 state==0 時改用 7。
  只影響待機的增益拆分；拍照、錄影、`mode_now` 不受影響；還原＝寫回原指令並清 I-cache。
  - 預期：類比增益降到錄影值，800% 數位補在 SIG0_RAW_CORR，LCD 亮度大致不變 [I]。
  - 風險：HCG 切換點變成 3200（ISO 640–3199 待機可能從 HCG 變 LCG）；AE 統計若取自 RAW_CORR 之前會暗 3 檔 [I]；
    state 7 另寫拍照數位欄位 +0x18；黑位回呼 `FUN_c0313658` 仍走 through 行為，要和錄影比對；HDMI 與 MOV 待機也會受影響，要另外限制。

### RAW 模式・tone 與色彩部分（離線追查 2026-09-24，未上機）

- **更正**：`captures/2026-09-24-standby-01` 當時色彩模式是 **OFF（36）**（tone 快取 index 82）；RGBLMAT 是 identity 是因為 OFF 的兩組矩陣都是 identity，不是「待機不用矩陣」。
- **tone LUT 在 RGB、輸入是線性** [C]：OFF 的表（index 82，`C09C3F34`）＝ sRGB(i/1918)×8190（RMS 0.70 碼）→ index 1918 是白，1918–2047 只剩 0.094 檔。
  輸入推定 index ≈ (L12 − 256)/2 [I，待實機確認]。2048 × u16、輸出 0..8190。
- **所以 LUT 之前不能補 >1× 的增益**：錄影類比增益下，感光元件滿位已經約在 index 1918，任何 ×2^N 都會把剛救回的最上 N 檔推出表外。
  **ISO 亮度要做進 LUT**：T[i] = 8190·D(比例·i/1918)。
  ⚠ 和增益部分衝突：hook 改成 state 7 後，會在 SIG0_RAW_CORR（LUT 之前）補 800% 數位增益。**RAW 模式必須同時讓待機 RAW_CORR 數位增益維持 1×**，亮度只由 LUT 補。
- 待機只有 context 0 生效（hw `30200094` = `C09C3F34`，context 1 位址為 0）；錄影時哪個 context 未知，要在錄影中讀一次 `30200000..1FF` 與 `C3414470+A0/+198`。
  錄製 RAW 不經過這張 LUT（在 demosaic 之後）；MOV 可能共用 context 0 [I]。
- **安裝方式**：表放自己配置的記憶體（32-byte 對齊，避開 `C3414DA8..C3421DA8` 原廠 scratch）；
  word address 換算照 `FUN_c011b4c8`；descriptor `[0]=ctx,[1]=1,[2..10]=0,[0xB..]=位址`；呼叫 `FUN_c011b4c8` 再 `FUN_c019c190(ctx)`；填表後 `FUN_c000e91c` 清 D-cache。
  **hook `FUN_c011b4c8`**：所有換表路徑都經過它；RAW 開且 ctx==0 時換成我們的表。另有純資料做法：把 root `C2F1A064`（RAM）的 mode→index 表改指 RAM 副本。
- **色彩**：相機 3×3 是 RGBLMAT **第二組**，依色彩模式設定（`FUN_c02cfcf0`）；OFF 是 identity。YCMAT 也依模式，C_SAT_C 像 16 點飽和曲線 [I]。
- **色彩模式編號**：0 Standard、3 Vivid、5 Neutral、6 Portrait、7 Landscape、8 Cinema、9 WarmGold、10 Teal&Orange、11 SunsetRed、12 ForestGreen、13 PowderBlue、14/15 FOV Classic Blue/Yellow、1/2/16–23 Mono、24–33 DuoTone、36 OFF。
  **建議**：「RAW」是 UI 上的一列，實際把模式設成 36（OFF）並另存自己的旗標；新增 37 會流到 DNG／metadata 的查表，可能越界。錄下來的 metadata 會是 OFF。
- `curves/tone2048_iso<N>.u16le`：已產生（31 個 ISO）。中灰在各 ISO 都是 0.404–0.406（BMCC 0.4055）；白點 ISO 100 → 0.822、800 → 0.987、3200 → 0.977。

### 每 ISO 曲線表（照 BMCC 做法，`tools/rv_curves.py` → `curves/`）

- **編碼（所有 ISO 共用一條）**：8-bit = k·Gen5Film(x) + c；黑位 27（現行 LV 實測），+6.09 檔 → 250（留 5 碼餘量）。
  中灰 → 126，中高段約 20 碼/檔（現行 LV 肩部約 42 碼/檔、下半段線性）。
- **每 ISO 只換輸入比例**：12-bit 感光元件滿位 = 中灰以上 W(ISO) 檔。W 用官方 12-bit CDNG／HDMI RAW 表；1/3 檔 ISO 內插並標 `interp`
  （100–800 每檔 +1；800 到 3200 前固定 6.09；3200→6400 對數內插 5.42→6.09；6400 以上 6.09）。
  所以中灰在每個 ISO 都落在 126，白點碼值隨 ISO 移動：ISO 100 → 189、400 → 230、800–2500 → 250、3200 → 236。這和 BMCC 曲線輸出上限隨 ISO 上升是同一件事。
- **顯示（所有 ISO 共用）**：LV 碼 → 反算 Film code → BMCC Film→Video 中性軸 → 8-bit。中灰顯示 103（0.404，BMCC 0.4055），+4 檔 233、+6 檔 251，平滑肩部、不硬切。
- 輸出：`enc_iso<N>.u8`（4096 → 8-bit，31 個 ISO）、`display.u8`（256）、`curves.json`、`curves.csv`。
- 未證參數：12-bit 黑位預設 256；MOV 與 8/10-bit（Base 100/640）沒有官方表，未產生。
  顯示只定了中性軸；色彩（矩陣、跨通道、色域壓縮）另做。表長、節點與暫存器要等 12→8-bit 的實際設定位置確定後再換算。

### BMCC 曲線核對（2026-09-24，從原始資料獨立重算）

- mode 2 Film 的 13 條曲線：全部單調；用 Gen 5 Film 公式、分段輸入軸 `[1,1,2,4,8,16]`、每條只擬一個 input scale，
  **RMSE 0.285–0.290 code、最大誤差 ≤0.586 code**；相鄰曲線 scale 比值全部 1.260 = 2^(1/3)；改用均勻輸入軸最佳 RMSE 166 code。與報告完全一致。
- 新看到的：每條曲線的輸出上限不同（2420 → 3264，每 1/3 EV 約 +70 code）。
  若輸入軸盡頭代表感光元件滿位，則各曲線白點在 18% 灰以上 +3.93 → +7.93 檔、每條多 1/3 檔 [I]。
  → BMCC 的「每 ISO 一條曲線」其實是**同一條 Film 編碼、只把曝光尺度每 1/3 EV 平移一次**，白點隨之移動；rawview 的每 ISO 表可以用同樣做法：
  一條固定的顯示曲線，依 ISO 改輸入尺度與白點。
- 和 fp LV 對照：Gen 5 Film 在中高段約 15 碼/檔（換成 8-bit）、涵蓋十幾檔；fp LV 8-bit 在碼值 100 以下是線性、之上約 42 碼/檔，
  所以 fp LV 8-bit 本身能放的高光檔數遠少於 Film 編碼。這也是改寫入 8-bit 前的曲線有效的原因：換成對數型，能在 255 內放進更多檔。

BMCC 資料只放研究歸檔；下列 `captures` 繼續保存 SIGMA fp 實測。`rv_snapshot.py`／`rv_decode.py` 的位址、讀取和解讀流程未因這次整合而改動。

## 實機紀錄

### 2026-09-24 待機快照 `captures/2026-09-24-standby-01`

狀態：CINE 待機、MONIT1_60（enum 8）、12-bit、2016×1344、small_raw hvbin 1/1、gain_state through。

| 級 | 活動值 | 意義 |
|---|---|---|
| TBLSD gain | 256/512/512/256 | = ROM 預設（R/B 256、G 512 的不同編碼） |
| SIG1 WB gain | 499 / 512 / 511 / 439 | 待機 WB 生效中 |
| RWAPKNEE | ctl bit7 = 0 | 關閉，與 raw-front-audit 靜態推論一致 |
| IGAMMA ctl | `00010FFF 00000FFF` | = ROM 預設 |
| RGBLMAT 兩組 | **identity**（係數 0x200，除 2 旗標 0） | 待機時色彩矩陣**不在 RGBLMAT**；色彩轉換在別處（C_SAT_C／YCMAT 等，待查） |
| LCD CSC（三個 bank 相同） | `[0.973 −0.184 −0.457 / 1 1.855 0 / 0.992 0 1.562]` | 709 型 YUV→RGB（1.856/1.575 那組）乘上面板白點微調（G 0.973、R 0.992） |
| LCD gamma | 16…255 identity | 顯示端 gamma 未使用 |
| tone sw descriptor | count 1/1 | 待機兩個 context 各用一條表 |

注意：這些區段是**依序讀**的，不是同一幀的一致快照；在沒有模式切換的待機可接受，換模式量測前要改成相機端一次取樣。

## 附帶訂正

`fpshell_tool/monitor/rawstream.py` 預設讀的 `0x49C00000` 落在顯示 scanout ring（`0x49BFD000..0x49FF9000`，見 IMAGE_CHANNELS.md），
**那不是 Bayer**；當時「16-bit BE、寬 1620 解得乾淨」不能當 LV RAW 的格式證據。

## 2026-09-25 「顏色怪怪的」A/B(fs2-4,ISO 100,CDNG 12-bit 待機)

`rv_card.py off/on` + 新增的 `rv_card.py shot NAME`(CAPTURE 鍵截圖並取回)。檔案 `captures/2026-09-25/ab_stock_off.JPG`、`ab_raw.JPG`(SS__0995/0996)。

| 區塊 | 原廠 OFF 色相 / 彩度(max−min) | RAW 色相 / 彩度 |
|---|---|---|
| 牆(中性) | — / 2 | — / 1 |
| 鼻子(褐) | 35° / 26 | 37° / 20 |
| 愛心(粉) | 327° / 29 | 322° / 15 |
| 帶子(紅) | 351° / 40 | 350° / 33 |
| 藍臉頰 | 192° / 16 | 199° / 13 |

- **色相對、中性無偏色**(差 ≤ 7°)。「怪」來自亮度與反差:ISO 100 的 T = 12.5 檔,中灰在畫面 75%,整個場景擠在 0.66–0.78。
- 逐通道 log:通道差 r 檔只佔畫面 r/T,所以彩度被壓(愛心 29 → 15)。ISO 越高 T 越小、越不灰(ISO 800 中灰約 51%)。
- 原廠 OFF 本身就很淡(OFF 的矩陣看來接近單位矩陣,顯示的是相機原生 RGB),所以 RAW 也繼承。
- LV HUD 下方列沒有畫色彩模式圖示,LV_ColorMode=16 目前看不到影響。

### 使用者指正後的追查(同日)

- **選單選 RAW(GUI 16)vs 只開旗標(GUI 15,之前的測試方式)**:截圖 `ab_raw` / `flag15_raw` 統計相同(亮度中位數 178/177、彩度 5.5/5.5)→ 選單本身沒有改變畫面。
  暫存器差 20 個字:`0x30210330..350`、`0x30210848/84C`(區塊未知)、`0x302000F4/1F4`(LUT 描述),其餘是 AWB 即時值。畫面沒看到影響,待查來源。
- **ISO 100 → 800(`iso100_menu` / `iso800_menu`)**:畫面快門角度由 120° 變 14°(灰字＝自動曝光)→ AE 照 ISO 數字縮短 3 檔快門,RAW 本身暗 3 檔,
  所以畫面變暗(中位數 179 → 108)。M 模式固定曝光時 ISO 100–800 畫面相同(9/24 `raw800` 已驗證,T 都是 12.5)。
- 第 17 列出現 OFF 沒有的調整項(使用者回報)：`CM_COLAJ_ColorMode` = 16,調整面板把 16 當成別的模式。待追。
- **第 17 列的「±0」框(`captures/2026-09-25/row17_option.JPG`,SS__1000)**：是「效果強度」調整。顯示與否由 UI 資源條件式
  `not(CM_COLFIX_MonoFlag:v() == 1 or CM_COLAJ_ColorMode :v() == 15)` 等決定,寫死 15(OFF)。
  修法：`CM_COLFIX/CM_COLAJ/CM_DNGDEV_ColorMode ... == 15` 共 9 處的 `==` 改 `>=`(長度不變,原廠值最大 15 不受影響)，
  資料 `build/rv_uidata.EXPR`、shell 測試 `tools/rv_ui.py expr / expr-undo`。待上機確認:條件式是開頁時才編譯(RAM 改即生效)還是開機時就編好。

### 兩段對數(2026-09-25,使用者決定,待群組在兩版間選)

- 使用者要求:中灰對到 709 中灰(G = OETF709(0.18) = 0.409),頂底仍依官方寬容度對齊 709 → **兩段對數**:中灰以下 L 檔均分 0..G、以上 W 檔均分 G..1。
- 實作:`rv_curves.py --map twolog`(預設;`stops` 保留)、`rv_tables.py` 每 ISO 一筆 {AH, AL, BL, K=−W},launcher 迴圈以 LOG ≥ K 選段。
  整數與 numpy 最大差 1 LSB,blob 8,812 B;模擬 30 項全過。**尚未建卡、未上機。**
- BMCC 對照(反編譯資料重算):Video 中灰 0.404、Extended 0.409、Film 0.384,各 ISO 相同、只有白端隨 ISO 移動 → 支持中灰固定。
  差異:BMCC 中灰上下斜率相近(平滑 S 曲線,無轉折);低 ISO 白端只到 0.909(不把飽和拉到白)。我們保留轉折與飽和＝白(忠實反映 RAW)。
- 示意頁(給群組選):https://claude.ai/artifact/1UbCAtwYLMLSRtT4QAgPiE

### A + B 兩種曲線(2026-09-25,使用者決定「A + B,B 要是曲線」)

- **A = 每檔等寬**(`stops`,不變)。**B = 709 中灰平滑曲線**(`smooth`):過 (底線, 0)、(中灰, 0.409)、(飽和, 1),
  以 PCHIP(單調三次 Hermite,Fritsch–Carlson 權重)連接;中灰處斜率連續、無過衝。
  各 ISO:中灰每檔約 0.077–0.083(102400 為 0.113);ISO 100 底線斜率 0(趾部)、飽和處 0.228;中灰 ±2 檔 ≈ 0.26 / 0.58–0.65(200–12800 幾乎相同)。
  折角版 `twolog` 保留在 `rv_curves.py` 供比對,不上卡。
- **產表引擎改為兩段三次式**(`rv_tables.py`):每 ISO 一筆 64 B {XL, XG, K0, 上段 K1–K3, 下段 K1–K3},
  x 夾到 [底線, 飽和],Horner 三次 smull;A 是 K2 = K3 = 0 的特例。62 張表(A 31 + B 31),整數與浮點最大差 1 LSB。
  配置 0x42000;插槽／mode 副本／常駐移到 T0 + 0x3E004／0x3E060／0x3E200。
- **常駐 +0x1A4 curve**(0 = A、1 = B),stub_gs 選表時 B 加 31。`rv_card.py curve A|B`(寫 curve、清 last_rel)。
  選單切換方式未定(先用 host 指令)。
- **±0 框修正做進卡片**:9 處條件式 `==` → `>=` 併入 `rv_uidata.PAGE`(開機核對原廠字、寫入、宣告區段關機寫回)。
- 模擬 31 項全過(新增 B 組選表)。突變:不選 B、上下段對調、不夾底線 → 皆抓到;不夾上限(x > 0)未抓到——
  index 2047 只超出飽和 0.09 檔,結果本來就夾到白,屬無效果冗餘,保留。
  整卡測試:Camera 的 H_ADDR 固定回 HEAP 會與 stage2 journal 重疊(0x42000),`CardCamera` 讓 H_ADDR 回 HEAP + 0x200000(實機配置器不會重疊)。
- **卡片 fs2-5**(`cards/rawview-2026-09-25/fs2-5`):fpSup.BIN `15c42efb…`(32,768 B),AutoRun 與 FPSUPUI 0–4 與 fs2-4 相同。**未寫卡、未上機。**

### RAW 模式色彩矩陣(2026-09-25,研究,未實作)

- OFF 在相機內沒有校色:模式矩陣表(root+0x08 → ROM `0xC0B39CC8`,35 筆 × 0x18 {mode, 9 × s16},512 = 1.0,
  每列順序 R:(R,G,B)、G:(G,R,B)、B:(B,R,G))的 OFF(0x24,`0xC0B39FF8`)＝單位矩陣;live RGBLMAT 兩組皆 0x200 對角;
  YCMAT／RGBMAT_PL 只是 601 的 RGB↔YCbCr。OFF 的 CDNG ColorMatrix 換算成 cam→709 也是單位矩陣 → 現行 LCD＝Resolve 預設顯影。
- 真校色矩陣只在非 OFF 的 DNG(`_SDI5625` CM2,D65):cam→709 = [[1.378,−0.582,0.204],[−0.097,1.224,−0.127],[0.061,−0.439,1.378]]。
- BMCC 對照(子代理,腳本在 scratchpad/bmcc_color):機型共用雙錨點矩陣(2856K/6500K),無逐台校色;Film to Video 在中低飽和 ＝ 3×3 + 每通道 tone
  (飽和增益 ≈1.02),709 邊界附近軟壓縮(R 在邊界輸出 0.84)。fp 硬體可做到前者 → 建議直接套上面矩陣
  (×512 = [[706,−298,104],[−50,627,−65],[31,−225,706]],表內順序 R(706,−298,104) G(627,−50,−65) B(706,31,−225))。
- 待辦:上機驗證換 root+0x08 指標(RAM 副本、OFF 筆換矩陣)後 LCD 是否重新載入;之後可依白平衡在 CM1/CM2 間內插。

### 四個 RAW 選項 R1 R2 RC1 RC2(2026-09-25,使用者要求)

| 列(NO) | GUI | 名稱 | variant | 曲線 | 色彩矩陣 |
|---|---|---|---|---|---|
| 17 | 16 | R1 | 0 | A 每檔等寬 | 無(OFF 原生) |
| 18 | 17 | R2 | 1 | B 709 中灰平滑 | 無 |
| 19 | 18 | RC1 | 2 | A | fp 校色(cam→709) |
| 20 | 19 | RC2 | 3 | B | fp 校色 |

- **矩陣上機驗證(`tools/rv_matrix.py`,fs2-4)**:root+0x08 指到 RAM 副本(OFF 筆換校色矩陣)+ `SetColorMode 12` → RGBLMAT 組 2 = 新係數;
  `mat_before`/`mat_on`(SS__1001/1002):彩度 愛心 32→53、帶子 41→64、黃 24→46,牆 0.3→2.7(灰維持中性 → 方向正確)。
  指標換回後**不觸發**也在 1 s 內回到單位矩陣 → 韌體每次 PQ 更新都重查 root+0x08,stub_gs 換指標即可。
- 矩陣定義 `build/rv_color.py`(DNG CM2 → cam→709,列和 512,表內順序、不觸發縮半 assert)。
- 常駐:pend = GUI + 1(15..19 → 16..20);stub_mc 設 flag/variant,生效列改變時 guitab index 15..19 改成「生效列在前、其餘遞增」;
  stub_mb 回 16 + variant;stub_ml 16..19 → 15;stub_gs 在 eff 或 variant 改變時換 root+0x70、root+0x08(RC 且生效 → 副本)、重選表(bit 0 → B 組)。
  參數區:guitab 20 筆(+0x98)、dbg +0x138/+0x13C、variant +0x1BC、mat_copy +0x1C0、var_app +0x1C4。
- launcher:guard root+0x08 = {0xC0B39CC8, 35}、OFF 筆 = 原廠單位矩陣;T0 + 0x3F000 放矩陣副本;guitab + {0xC,16..19};getter 筆數 20。
  root+0x08(seg1 原廠 0xC0B39CC8)宣告為執行期區段(journal、關機寫回)。
- UI:CSV 第 17–20 列(主檔 Left/Right 串接、第 1 列 Left → 19;_EXCL/_EXCL2 各四列停用);頁面上限 15.0 → 19.0(0x98)、文字終點 500 → 632(每列 33,推定)。
  **列的圖示／文字仍是 OFF**(set_common_1;名稱 R1…RC2 需要自製圖示與文字 key,里程碑 3)。
- `rv_card.py variant R1|R2|RC1|RC2`、`status` 顯示 variant 與矩陣指標。
- 模擬 36 項全過;突變 14 個全部抓到(補:StandDown 原本沒設 root+0x08 初值 → 每個子測試都因 root+0x08 不符而「通過」、等於沒測;
  已補初值、加入矩陣表／OFF 筆的 guard 位置與「全原廠會安裝」的正向對照)。
- **卡片 fs2-6**(`cards/rawview-2026-09-25/fs2-6`):fpSup.BIN `55b92f93325e00db…`(32,768 B),AutoRun/FPSUPUI 與 fs2-4/5 相同。未寫卡、未上機。
  2026-09-25 14:55 寫卡(補到 61,440 B),讀回 sha256 f6acd843… 相符。
- **fs2-6 上機(2026-09-25)**:兩次重開後載入(params 0x45175200)。使用者用 COLOR 選單在 R1↔R2 間切換,dbg:生效列 16↔17、按 OK 後不跳回 OFF。
  `rv_card.py variant` 依序切四種並截圖(`v_R1..v_RC2.JPG`、`v_montage.jpg`,SS__1003–1006,ISO 320、曝光指示 −1.7):
  亮度中位數 R1 97 / R2 45 / RC1 99 / RC2 46;平均彩度 8.4 / 6.2 / 13.4 / 10.2。RC 時 root+0x08 = 0x45176000(副本),R 時為原廠。
  注意:`menu SetMovCinemaDNGQuality` 回 4,但設定區 +0x788 = 0(stub 判定 12-bit)→ 兩者編號不同,待使用者確認實際位深。

### 構想:一列 RAW + AEL 細部頁切換(2026-09-25,離線研究,未實作)

- 細部頁 = **ColorModeAdvancedSettings**(NBU `C1D66D7D–C1D8671E`,無 CSV;`UicGuiMenuColoModeAdvanced` blk_c05.c:81279)。
  `MenuMode` 依 CM_COLFIX_ColorMode:≤12 → Contrast/Sharpness/Saturation;13(DUO)→ Contrast/Sharpness;14(MONO)→ + Toning;刻度 −1.0..+1.0。
- **OFF 沒有細部頁**:ColorButtonMenu 物件 `NotOFF or OFF`(`C1D62A10`)≤14.0(`C1D62AA8`)→ AEL 可用、==15(`C1D62B0B`)→ 隱藏。
- 值:`FUN_c00b46f8` 依模式 enum 取 8-byte 記錄 {Effect, Contrast, Sharpness, Saturation, Toning}(s8);**OFF(0xC)→ RAM 暫存 `0xC31CC020`**(不存檔);
  寫入在模式 0xC 時不寫;UI −5..+5。GUI 16 不越界(呼叫點都傳 0xffff = 目前模式 enum 0xC)。
- 建議 (a):借 Contrast → 曲線 A/B、Saturation → 矩陣;`C1D62AA8` 門檻改高讓 RAW 列有 AEL;
  stub 攔 UI 回呼 `c056d528`/`c056d5d8`(AJ 預覽)、`c056d3c8`/`c056d478`(FIX 確認)讀 `[r0+8]`,通知 `c0595808`/`c0595878`/`c0595960`/`c05959d0` 回我們的值;
  設定要保留需另存 CommonSave。項目名稱仍是 Contrast/Saturation。(b) 新增項目:NBU 插入不可行,不建議。腳本:scratchpad/colaj/。
- 上機(fs2-6):使用者回報 RAW 列**原本就能按 AEL 進細部頁**(不需改 `C1D62AA8` 門檻;GUI 16 不觸發 ≤14 / ==15 任一事件,沿用前一狀態)。測試時已把 `C1D62AA8` 在 RAM 改成 19.0,重開即還原。

### 仿 DUO:上下框 = A/B、AEL 飽和度 = 矩陣程度(2026-09-25,離線研究,未實作)

- 上下框物件 `Effect or Scheme`(`C1D63F1F`,依 CM_COLAJ_ColorMode):0–12 → Effect、13 → Scheme(DUO)、14–15 → Effect(`C1D640A4`/`C1D640A8`);
  16 無事件(沿用前一列)。Effect −5..+5 數字;`ToggleVisible` 依 `CBM_BKTMonochrome`(0 → 可操作、1 → 灰字)。
- DUO 的 Scheme 框不能借(字形與 DUO 10 色共用、回呼 `c0568a90` 只在模式 0xE 動作);`font_menu_LB_id_A/B` 只在 Scheme 動畫可用。
- Effect 上下 → 回呼 `FUN_c0568a00`(blk_c05.c:77565,[r0+8] = UI −5..+5)→ vt+0x204;OFF/RAW(0xC)在 `c009a790` 被擋。
- 飽和度:AJ `c056d5d8`(捲動每步)、FIX `c056d478`(OK);值 UI −5..+5;通知 v85 `c0595878`/v90 `c05959d0`(r1 = 存值 −10..+10)。
- **OFF 暫存 0xC31CC020 不能當儲存處**:PQ v3 會把 +3 → PQ+0x290 飽和、+0 → PQ+0x2A8(OFF 也吃)。改存常駐 RAM,要保留再寫 CommonSave。
- 最小 patch:三處 EXPR(CBM_BKTMonochrome:`C2D9FD47`/`C2DAF097`/`C2DAF0DA`)改回 `==`;`C1D640A8` 15.0 → 16.0;
  hook `c0568a00`(存 A/B、直接返回)、`c05958e8` v87(發布我們的 Effect)、`c056d5d8`/`c056d478`(存矩陣程度)、`c0595878`/`c05959d0`(換 r1)。
- **命名(使用者,2026-09-25)**:上下框兩個值 = **Latitude — Stop Aligned(SA,曲線 A 每檔等寬)**、**Latitude — Gray Aligned(GA,曲線 B 中灰對 709)**。
  Effect 框只有數字字形 → 先以數字代表(待定對應),顯示「SA/GA」文字需另做字形／文字(里程碑 3)。

### 改成直接做在 OFF 列(2026-09-25,使用者決定)

- 不新增色彩列。OFF 列右側上下框:**−1 = SA(Latitude — Stop Aligned,曲線 A)、0 = OFF(原廠)、+1 = GA(Latitude — Gray Aligned,曲線 B)**。
- 可移除:CSV 第 17–20 列、上限 15→19、guitab 重排、stub_ma/mb/mc/ml、H1、頁面上限。
- 需要:OFF 的上下框可操作(`CBM_BKTMonochrome` 三處 `== 15` → `== 99`,等長)、攔 Effect 回呼 `c0568a00` 與發布 v87 `c05958e8`(存/顯示我們的狀態,夾到 ±1)。
  矩陣程度(AEL 飽和度)需另開 OFF 的細部頁(`C1D62B0B` ==15 隱藏),之後再做。

### 單列 RAW + 上下框 SA/GA + AEL 飽和度 = 矩陣程度(2026-09-25,使用者決定;fs2-7 候選)

- 放棄「直接做在 OFF 列」:OFF 框灰字由 NBV 規則 `CBM_BKTMonochrome` 決定,規則在 FS2 載入前已編譯,執行期與開機改字串都無效
  (上機:游標在 OFF 時仍為 1;`gui seti` 立即被規則改回)。同理先前 9 處 EXPR 條件式修改從未生效,已從卡片移除。
- 第 17 列 RAW(GUI 16):CBM_BKTMonochrome 只對 ==15 成立 → RAW 列的右側框本來就可操作;AEL 細部頁本來就能進。
- **右側上下框**:`c0568a3c`(回呼 FUN_c0568a00 的 `bl C06C0D20`)→ stub_ef:UI 值 > 目前顯示(SA −1 / GA +1)→ GA、< → SA;
  `c0595908`(v87 的 `bl C06C0D70`,r7 = 模式)→ stub_en:模式 0xC 且 RAW → 回 −1/+1。頁面 `C1D640A8` 15.0 → 16.0(框固定是 Effect)。
- **AEL 飽和度**:`c056d5f8`(AJ 捲動)/`c056d498`(FIX 按 OK)的 `bl C06C1060` → stub_sa(存 sat/sat_fix,夾 ±5);
  `c059588c`(v85 COLFIX)/`c05959e4`(v90 COLAJ)的 `bl C06C10B0` → stub_sn(回 sat_fix / sat)。取消 = 頁面以 FIX 值重設 AJ。
  原廠對 OFF(0xC)的寫入本來就擋,stub 只換換算、原廠流程照走 → 不動 OFF 暫存 0xC31CC020(PQ 會讀它)。
- 矩陣程度 `rv_color.sat_table`:−5..0 → 0..100 %(每格 20 %)、+1..+5 → 110..150 %;11 筆 × 24 B 在參數區 +0x1B8,
  stub_gs 在 lat/sat/eff 改變時抄進矩陣副本 OFF 筆、root+0x08 → 副本(生效時)。預設 SA、飽和度 0(100 %)。
- 參數區:guitab 17、dbg +0x120/+0x124、lat +0x1A4、mat +0x1A8、key +0x1AC、sat +0x1B0、sat_fix +0x1B4、sat_tab +0x1B8;veneer 11(88 B)。
- 模擬:合成 15 + 真實映像 24 全過(含從真實呼叫點經 veneer 進 stub 的 SA/GA、飽和度 AJ/FIX/v85/v90、各飽和度矩陣進韌體查表)。
- 工具:`rv_card.py lat SA|GA`、`rv_card.py sat N`;`status` 顯示 SA/GA、飽和度、矩陣指標。
- 突變 10 個全部抓到,還原後全過。**卡片 fs2-7**(`cards/rawview-2026-09-25/fs2-7`):fpSup.BIN `4e64ac551d187e35…`,AutoRun/FPSUPUI 同前。未寫卡。
  2026-09-25 16:37 寫卡(補到 61,440 B),讀回 sha256 c981b218… 相符。

### fs2-7 上機回報與修正(2026-09-25)

- 使用者回報:① 第 17 列只有按 OK 才選定、退出不會(其他色彩退出也選定);② 選中第 17 列沒有即時預覽;
  ③ 右側框仍可調 ±5;④ 每次進 COLOR 選單第 17 列 SA/GA 就切換。
- ①②:dbg 顯示游標移動的 setter 前沒有 GUI→enum 事件 → 游標移動(預覽/退出即選定)走 `CM_COLAJ_ColorMode` 回呼
  FUN_c0568988 的 `bl C06C07E8`(`C05689A8`),未接。新增 stub_mj(同 stub_ma 的 pend 邏輯,尾跳 C06C07E8)。
  C06C0718 其餘未接的呼叫者是 CM_CHGMOD(C056C5B0)與 CM_DNGDEV(C0572CF0),與此選單無關。
- ③④:開選單時頁面把 CM_COLFIX_Effect(v82 發布,未接 → 存值 0)複製到 AJ → 回呼收到 0 ≠ ±1 → 被當成上/下。
  新增 v82 `bl C06C0D70`(`C05957B0`)也接 stub_en;stub_ef 切換後以 FUN_c0593f30(發布 UI 變數;原廠「回呼 → setter → 通知」同一路)
  把 CM_COLAJ_Effect 與 CM_COLFIX_Effect 設回 −1/+1(框停在 ±1),等於顯示值時不動(自己發布引起的回呼不會再切)。
- 模擬 41 項全過。
- 突變 5 個(預覽尾跳、預覽未接、相等也切換、不發布 FIX、v82 未接)全部抓到。使用者:框只要 0 / 1 → **SA = 0、GA = 1**。
- **卡片 fs2-8**:fpSup.BIN `489a365f26b5278c…`,AutoRun/FPSUPUI 同前;2026-09-25 17:02 寫卡,讀回 sha256 5f94a319… 相符。
- **fs2-8 上機**:SA/GA 0/1 與預覽正常。AEL 頁在 RAW 列卡住(上下、MENU 無效):`MenuMode` 依 CM_COLFIX_ColorMode,16 不符任何事件 → 無選單組。
  RAM 測試 `C1D6ED48` 12.0 → 16.0(Normal ≤ 16)→ 上下、退出正常(DUO/MONO 待確認)。
  飽和度「無效果」查證:頁面開著調到 −1.0(UI −5)時 sat = −5、OFF 筆 = 單位矩陣、RGBLMAT 組 2 = 單位;工具切回 0 → 組 2 = 校色矩陣。
  截圖 `sat_m5`/`sat_0`(SS__1007/1008,`sat_pair.jpg`):平均彩度 7.2 → 10.1、p95 34 → 55 → **有作用但在 SA 曲線下不明顯**。
  頁首顯示「MONO. 黑白」(沿用前一狀態),待處理。
- 使用者:飽和度限制 0..5 → **0 = 不套、5 = 100 %(每格 20 %),預設 0**;stub_sa 夾 0..5,捲動被夾時發布 CM_COLAJ_Saturation 拉回(不發布 FIX)。
  AEL 頁 `C1D6ED48` 12.0 → 16.0 併入 PAGE。模擬 41 項全過。**卡片 fs2-9** 建好,未寫卡。
- 使用者問能否關掉對比/清晰度:RAW 下本來就無作用(OFF 寫入被擋);隱藏需改頁面結構(不可行);可選「鎖在 0」。使用者:先不管。
- **使用者新方向:飽和度 > 0 時把校色矩陣寫入 CDNG**(RAW 像素不動,只改 ColorMatrix;原則「metadata 不動」因此調整)。研究中。
  2026-09-25 寫卡 fs2-9,讀回 sha256 ea95f2f2… 相符。

### CDNG 寫入校色矩陣(2026-09-25,離線研究,未實作)

- `FUN_c02c4a50`(blk_c02.c:123708):讀 Sigma makernote 0x11f(逐台 CameraCalibration P,本機 diag(1.0433,1,1.0193)),CM = inv(P)·C,
  ×10000 寫 0xC621/0xC622;OFF 判斷 `info[+0x118]*4+0x30 == 0x24`(0xC02C4BD8/4C8C,`E3500024`)與 HueSatMap/ToneCurve/私有模式 ID 共用 → 不改。
  C 為 ROM double[9]:OFF CM1 0xC096FD74、CM2 0xC096FCE4;非 OFF CM1 0xC096FD2C、CM2 0xC096FC9C(驗算:FC9C/P = _SDI5625 CM2;cam→709 = LCD 矩陣)。
- cDNG writer `FUN_c02c7448`(IFD0;呼叫者 FUN_c02b97a8 type 5),推定每片段一次;靜態 DNG `FUN_c02c6870` 也呼叫 4a50。
- **方案 A**:OFF 分支載入常數位址的 movw/movt 改指常駐緩衝 X1/X2(各 72 B):
  0xC02C4BE4 `E30F2D74`、0xC02C4BE8 `E34C2096`、0xC02C4C98 `E30F2CE4`、0xC02C4C9C `E34C2096`。緩衝平時 = 原廠 OFF 常數;
  RAW 生效且 sat > 0 → C_k。inv(P) 照常乘上。影響僅 CM1/CM2(靜態 DNG 也走此處,但緩衝只在 RAW 生效時改)。
- 部分程度:C_k,i = D_i·inv(I + k(M_i − I))·A(A = XYZ→709、D_i = OFF 常數/A 的逐列縮放、M_i = A·inv(N_i)·D_i),k = 0/1 端點精確。
- 風險:Resolve Temp/Tint 讀數會變(白仍中性);私有 0x124 已反映 LCD 矩陣;錄影中不改(stub_gs 只在待機跑)。腳本:scratchpad/dngcm/。

### 第 17 列 RAW 圖示(2026-09-25,fs2-10)

- 圖示字樣是圖檔。試過 `cmn_play_raw`(播放箭頭)、`font_G_HDMIfmt_raw`(HDMI 窄高字形,使用者:太醜)。
- 自製:原廠「OFF」= set_common_1.xci(0xC14E4F98,86×74,墨水框 x 17..68、y 25..47);Arial Narrow(比對 OFF 誤差 3.1 %)
  字高 23、底線 47、置中、邊緣 lo 0.05/hi 0.6 → `tools/rv_icon.py` → `build/rv_raw_icon.xci`(1,086 B,XCI 用 OG3K `xci.py`)。
- 借用名稱 `set_flash_1`(原廠閃電;位址由相機 heap 檔案表讀出:0xC14EBAAC,533 B;離線從 ROM 大端表推名稱會錯一格):
  CSV 第 17 列 → set_flash_1,H1(stub_fv)換檔表加第 4 格 → RAW 圖示。RAM 實測(`icon_rawtile_crop.png`,SS__1018)與 OFF/MONO./DUO. 同風格。
- 矩陣副本移到 T0 + 0x3F800(常駐變大)。模擬 42 項全過;突變「只掃 3 格」抓到。
- **卡片 fs2-10**:2026-09-25 17:54 寫卡,讀回 sha256 f3124a60… 相符。
- 待辦:下方大字(第 17 列沿用前一列文字)→「RAW」(字串池 ID 0x359C);上下框 0/1 → SA/GA 字形;CDNG 寫入校色矩陣(方案 A,待決定);
  對比/清晰度鎖 0(暫緩)。

### SA/GA 字樣、CDNG 校色矩陣、對比/清晰鎖 0(2026-09-25,fs2-11 候選)

- **CDNG ColorMatrix**(`build/rv_dngcm.py`):DNG writer OFF 分支的 movw/movt(0xC02C4BE4/BE8、4C98/4C9C)改指常駐 `cm_buf`
  (初值 = 原廠 OFF 常數;stills 與未生效時不變);stub_gs 在 eff/lat/sat 改變時抄 `cm_tab[生效 ? sat : 0]`(6 級 × CM1/CM2 × 9 double)。
  C_k = D·inv(I + k(M − I))·A(D = OFF ÷ A 逐列、M = A·inv(N)·D);k = 0/1 等於原廠 OFF/非 OFF 常數(assert)。
  Resolve 式換算與 LCD M_k:k = 0、1 一致,1–4 最多差 0.039(DNG 另乘逐台 P;LCD 矩陣已含 P)。錄影中不變(stub_gs 只在待機)。
- **SA/GA 字樣**:`gui image log` 上機:右側框 = 符號格 `font_menu_LB_kigou_08`(±)/`_07`(+)(41×51)+ 數字格 `font_menu_LB_0`/`_1`
  (34×51),每次重畫重新載入;AEL 頁用 font_G_*。font_menu_LB 是通用選單字型 → 條件式替換:stub_fv 的 `gltab`
  (RAW 生效 && COLOR 選單開著 && 游標在 GUI 16)把 ±/0/+/1 換成 S/A/G/A(DIN Alternate Bold,對原廠 0/1 誤差 6.6 %;
  `tools/rv_icon.py` → `build/rv_glyph_*.xci`;位址由相機 heap 檔案表讀出)。選單開/關:ColorButtonMenu vtable v25/v26
  (0xC0D119FC/0xC0D11A00)→ stub_mo/stub_mx;游標:stub_ma/mj 記 P_CUR。參數區 +0x1B8 menu、+0x1BC cur,sat_tab 移到 +0x1C0。
- **對比/清晰鎖 0**:AEL 頁回呼 bl(對比 AJ C056D548/FIX C056D3E8 → C06C0EC0;清晰 AJ C056D5A0/FIX C056D440 → C06C0F90)
  → stub_zc/zs(RAW 時回 0,AJ 非 0 發布 CM_COLAJ_Contrast/Sharpness = 0);通知 v83/v88(C059581C/C0595974)、v84/v89
  (C0595854/C05959AC)→ stub_znc/zns(回 0)。veneer 16。
- 常駐 ~8.9 KB,矩陣副本移到 T0 + 0x40800。模擬 45 項全過。
- **卡片 fs2-11**:突變 8 個全部抓到。2026-09-25 18:40 寫卡(第一次 putfile 在剛開機時失敗:LOAD_DONE_US 尚為 0),讀回 sha256 8ad83c9a… 相符。
- **fs2-11 上機**:SA/GA 操作後變成「G1」「±0」。條件(flag 1、menu 1、cur 16)皆成立;`gui image log`:按上下時只載入
  kigou_06/07、LB_2(框短暫 ±2 再被拉回),±/0/1 不再載入 → **字形有快取**,依條件換檔不可靠,且換過的字母可能留在快取出現在別列。
  研究中:圖片快取清除,或在「字元 → 字形名」處依條件改用專屬借用名(快取分開)。

### 依 SIGMA fp Rec709 LUT & Operations Guide v3 修正曲線(2026-09-25,使用者指定為權威)

- 文件:Ole Berek(2023-06-28,依若松白皮書;文件自述 SIGMA 無官方 LUT)。`~/Downloads/SIGMA fp Rec709 LUT & Operations Guide v3.pdf`。
- **寬容度表**(p.2):第一迴路 ISO 100–800、第二迴路 3200–5000,皆 12.5 檔(第二迴路 12.46)。改用文件逐 1/3 檔:
  125 3.42/9.08 … 640 5.76/6.74;**4000 5.75/6.71、5000 6.09/6.37**(舊內插 5.64/6.77、5.85/6.50)。5000 以上沿用 SIGMA 官方表
  (W 皆 6.09,L 6.21 → 3.15);1000–2500 W 6.09(類比增益)。
- **GA 曲線 = 文件 v2/v3「LA - SIGMA Rec709 ISO N」**(p.4):以 PDFKit 5× 渲染、0% 線/s = 0 線/格線定軸、由右往左追黃線,
  V-Log 線在 s = 0 讀值 41.9–42.3(理論 42.1)→ 校正可信。`reference/lut709/lut709_digitized.json`(含裁切圖)。
  特徵:暗部各 ISO 幾乎相同(−2 ≈ 24 %、−4 ≈ 11 %、−6 ≈ 4 %,無加對比)、中灰 43–46 %(46/44/44/43/44/43 與文件表格一致)、
  高光平滑到 100 %(約在飽和點前 0.3 檔)。曲線只取決於 W → `rv_curves.lut709(s, W)`:中灰以下數值內插、中灰以上以 u = s/W 對齊內插。
  5000 以上:W = 6.09 同 5000(推測,使用者詢問後採用)。
- **產表引擎改為取樣表**(任意曲線):每張 146 點(−8..+6.5 檔,每 0.1)u16 含顯示補償,launcher 線性內插;SA 也用同一引擎。
  整數 vs 浮點最大 18 LSB(0.2 %)。blob 38.8 KB。突變(t = x·10、內插項、S0 偏移)皆抓到。模擬 45 項全過。
- SA/GA 字形:H1 條件換檔停用(快取問題);研究代理建議改在 drawImage(0xC061F0A0,原廠 `d4f80880`)換 LB 字表,
  用原廠 font_menu_LB_id_S/A/G(40×51)— 待實作。
- **卡片 fs2-12**(fpSup.BIN 40,780 B 內容、補齊 61,440 B):2026-09-26 01:58 寫卡,讀回 sha256 525692e7… 相符。
- **fs2-13**(fs2-12 + 選單事件記呼叫點 lr):2026-09-26 寫卡,讀回 sha256 f402fdeb… 相符。待辦:切解析度 RAW → OFF(紀錄最後為 GUI 15 → 選 OFF);錄影開始畫面亮一檔(ISO 3200 時待機 hcg 0)。
- **切解析度 RAW → OFF**:fs2-13 dbg:`GUI→enum 15 ← QS` → 選 OFF。QS 列表沒有 RAW 列,切解析度時以 15 重新同步。
  修正:stub_ma 在 QS 路徑(lr = C05818BC)一律 pend 0、不記游標;QS 選其他模式仍由 setter 關 RAW;QS 選 OFF 不再關 RAW(需在 COLOR 選單選 OFF)。
  模擬 46 項全過,突變抓到。**fs2-14** 建好(fpSup.BIN 2cb67c20…),未寫卡。
  2026-09-26 寫卡 fs2-14,讀回 sha256 2cb67c20… 相符。
- **fs2-14 上機**:切解析度不再跳回 OFF。錄影開始畫面亮一檔:只在 UHD。UHD 錄影中 `imager mode_now` = MONIT1_24_HD_LOWP2 6064×3412、
  **gain_state movie_raw_8bit(5)**;待機我們固定回 7(12-bit)。UHD CinemaDNG 實際 8-bit,但設定區 +0x788 仍為 0(stub 判定 12-bit)
  → 待機增益規則與錄影不同。gain_state:0 through、1 acq、2 through_acq、3 movie、4 movie_raw、5 8bit、6 10bit、7 12bit、8 digital_off。
  待決:UHD(8-bit)時停用 RAW,或待機改用錄影將採用的 gain_state(需找出韌體依解析度決定位深之處;8-bit 的寬容度為 Base 100/640,資料未知)。

### SA/GA 字樣改用 drawImage 換字表(2026-09-26,fs2-15)

- 研究(代理,只讀):圖片依名稱快取(FUN_c05dfe88 二分搜、entry+0x18 實例、引用計數 FUN_c05d8910/FUN_c05d8b88),強制卸載會 use-after-free。
  Effect 框用 drawImage(Thumb 0xC061F008)的原生字表:依 [sp,#0x10] 字型 idx 選 sl(idx 2 = font_menu_LB 表 0xC2F2DE38,.data),
  0xC061F124 起逐字比對 {u32 字元, 圖名*, w, h}。LB 表:'P' = ±(kigou_08)、'+'、'-'、0–9 …。
- 做法:Thumb B.W 0xC061F0A0(原廠 `ldr.w r8,[r4,#8]` = 0x8008F8D4)→ veneer 16 → stub_dt:RAW && 選單開 && 游標 16 && idx 2 &&
  字串 "-5"/"+5" → sl = dttab {'-' → font_menu_LB_id_S、'+' → id_G、'5' → id_A,40×51}(原廠字母字形,名稱不同 → 快取不衝突)。
  框只在文字變時重畫 → RAW 列框值改為 SA = −5、GA = +5(其他列通常 ±0,游標移入必重畫);stub_ef/en 相應修改。
  H1 字形換檔移除。launcher 的 Thumb B.W 編碼抽成巨集 THUMB_BW(H1 與 drawImage 共用)。veneer 17。
- 模擬 47 項全過(含從真實 Thumb 指令執行 drawImage 攔截點、B.W 解碼、各不換條件);突變 4 個皆抓到。
- **卡片 fs2-15** 建好(fpSup.BIN 2bce2086…),未寫卡。
  2026-09-26 寫卡 fs2-15,讀回 sha256 2bce2086… 相符。
- **fs2-16**(fs2-15 + stub_dt 診斷紀錄 +0x1C0,sat_tab 移到 +0x1D0):2026-09-26 寫卡,讀回 sha256 dddef00d… 相符。fs2-15 上機:第 17 列仍顯示 −5/+5(條件 flag 1、menu 1、cur 16 皆成立)。
- **fs2-17**(stub_dt 16 筆環診斷):寫卡,讀回 sha256 2e5fcace… 相符。fs2-16 紀錄:drawImage 只在少數時候被呼叫,最後一筆 idx 4 字串 "250";RAM 改條件 idx 4 仍無效。

### 設定關機存檔路徑(2026-09-26,研究代理,只讀)

- 關機:`XC_PowerOffMgr__v1` 0xC0023C50 跑完所有關機回呼後 `FUN_c0022820(0xC3074ABC)` flush(dirty 才寫)。選單設定回呼
  `SaveOnPowerOffObserver__v1` 0xC00789B0 → v9 0xC0088E98(快照 2 覆回)、v2 0xC0088BB0(`FUN_c0088660` 整塊 0x4F00 B 複製,type 0xE,
  word 加總校驗 `FUN_c0022918`,+0x2A40 magic 0x4D444C00 + 版本,開機 v1 0xC0088A88 讀回/校驗失敗用預設、v29 0xC008D7B8 版本遷移)。
- 位置 [I]:NAND 分區 4 offset 0xFFFE0000 大小 0x20000(seg1 0xC2EF72D0/72CC);CommonSave(type 9)+0x800、MenuSetting(0xE)+0x3800。
- 選單設定物件 0xC31AE3B0;bank A = obj+0x4F0C(現行工作副本 0x9C0 B),bank B = obj+0xA7D4(快照 1);選擇 byte 只被寫 0 → 實際只用 A。
  7 組設定(組號 obj+0x58CC);色彩模式在存檔紀錄第 0 組 +0x130(= 4 + 0x12C)。`menu save` 不寫 NAND。拔電池:最後一次正常關機後的變更遺失。
- CommonSave RAM 0xC307523C(0x410 B,存取結構 0xC3074954,`FUN_c00222d0` 推入並重算校驗)。已用:+0x00..27、+0x200..22F、
  +0x280..2BF(鏡頭記憶,`DoMemory` 0xC0358768 會把 +0x290 寫 0 → OGSAVE +0x290 有風險)、+0x380..38B、+0x400..40F。
- RAW 旗標持久化建議:CommonSave +0x230..+0x27F 存 magic + 值(例 'RAWV' + ~flag),改變時寫 RAM 並呼叫 `FUN_c00222d0(0xC3074954)`,
  開機時原生色彩仍為 0xC 才套回。未實作。
- **fs2-18**(+ stub_il 圖檔載入診斷):寫卡,讀回 sha256 125a850f… 相符。fs2-17 環紀錄:drawImage 0xC061F008 只畫 LV 資訊(0.00、1/80、360d、F8.0、+0.7、2500;呼叫者 C05D631D),COLOR 框不經過它;字串池 +5/−5 改 GA/SA 無效;CSV 字型 0xC0F8EEBC 起含 A–Z(font_menu_LB_id_*)、p = ±。
- **fs2-18 診斷結果**:框字形的載入鏈 `FUN_c0601f98`(C060239F,xcimage 解碼)← **`FUN_c05e6400`(C05E7485,解析一筆 NBU 記錄 = OG 的 ui_record)**
  ← FUN_c05db6a0 ← 0xC0605DD8 附近 ← FUN_c0611520 ← FUN_c05d5e30 ← FUN_c05d6990。→ 框的 ±/數字字形是**版面記錄裡的圖片**
  (關鍵影格依數值切換),在頁面解析時就載入,名字經字串池偏移引用(池 0xC18C0474;font_menu_LB_0 0xC18E6760、kigou_07 0xC18E6BB8、
  kigou_08 0xC18E6BD0)。不是文字繪製 → drawImage 字表與字串「+5」都無關。依條件換圖檔只能在頁面開啟時決定一次,無法依游標列切換。

### SA/GA:改效果框關鍵影格的圖名(2026-09-26,fs2-19)

- 效果框 = 兩個圖片元件(版面記錄):符號(drawImage 預設 kigou_08;animationClip 關鍵影格 − 0xC1D64AF7、± 0xC1D64B01、+ 0xC1D64B0B)
  與數字(預設 LB_0;關鍵影格依 −5..+5:0xC1D64BCD(−5)… 0xC1D64BFF(0)… 0xC1D64C31(+5)),另有 NumberMono/SignMono 灰色版。
  值是字串池大端偏移(0x0002xxxx)。
- stub_mc 在生效列改變時切 4 格低 2 byte:RAW → − = id_S(0x2660C)、+ = id_G(0x2651C)、±5 = id_A(0x264A4);否則原廠。
  選單每次開啟重新解析 → 依開啟當時狀態;原廠字母字形名稱只有此處使用 → 無快取衝突。框值 SA = −5、GA = +5。
  限制:RAW 開著時開啟的選單中,其他列的非零負/正值會顯示 S/G 符號(0 不受影響);剛選 RAW 的那一次選單仍為 ±5,重開才換。
- 移除 stub_dt(drawImage 字表,證實無關)。launcher 以 kf_guard 核對 6 個 word(不寫),並宣告為執行期區段(關機寫回)。
- 模擬 49 項全過;突變(RAW 時仍寫原廠偏移、不核對關鍵影格)皆抓到。**fs2-19** 建好(fpSup.BIN 0e220ea7…),未寫卡。
  2026-09-26 寫卡 fs2-19,讀回 sha256 0e220ea7… 相符。

### SA/GA:關鍵影格套用點即時換圖名(2026-09-26,fs2-20)

- 研究(代理,只讀):animationClip 關鍵影格只存圖名(kf+0x18,字串池指標;`FUN_c05edbe8`);數值改變 → seek →
  `FUN_c05e1fa8` 逐 track,Thumb 0xC05E2200 `bl FUN_c05d6bb8(node, prop, name)`(原廠字 0xFCDAF7F4)把名字設到節點;
  `FUN_c05d6990` 名字不同才更新並經類別回呼依名稱載圖/快取。fp = 容器(+0x18 記錄 id:效果框符號 0x177、數字 0x178;
  同 id 也在 DNGDEV/CHGMOD 版 ColorButtonMenu)。
- 做法:該 bl 改 Thumb BL → veneer 16(Thumb)→ stub_ai:RAW && 游標 16 && 容器 id 0x177/0x178 → kigou_06 → id_S、
  kigou_07 → id_G、LB_5 → id_A,尾跳原函式。每次數值改變都經過 → 即時、他列不受影響、不需重開選單。
  撤銷 fs2-19 的版面關鍵影格修改(版面恢復原廠)。launcher THUMB_BW 巨集加 BL 旗標(hw2 0xD000)。
- 模擬 48 項全過(含真實 Thumb 指令執行、BL 解碼、各不換條件);突變 4 個皆抓到。
- **fs2-20** 建好(fpSup.BIN c56013e9…),未寫卡。
  2026-09-26 寫卡 fs2-20,讀回 sha256 c56013e9… 相符。

### v0.2.3test：COLOR 第 17 列改用 fpSup/uishare 的「添加」（2026-10-03，離線）

- `rv_launch.S` 加 `UISHARE`（預設 1）：啟動器不再守衛／寫 H1（C05E5BEC）與 9 個 ColorButtonMenu／
  ColorModeAdvancedSettings 頁面字；改由卡上的 UI 段落（`fpSup/uishare`：`ui/options.py color_raw()` +
  `ui_apply.c`）在 CSV 複本追加 RAW 列、在兩頁的複本加上上限，H1 由共用處理器 `fv_handler.S` 掛（別的 sup 共用）。
  `build_rawview.py --legacy-ui` 仍逐位元重現 v0.2.2test 的 49 段。
- **stub_ai 修正**：原本用原廠字串池的絕對位址（`NAME_K06` 等）比對字形名稱；同卡有 Lossless（附加字串 → UI 改用
  共用池副本）時永遠比不中，框顯示 −5/+5（相機 10/03）。改成比「目前池（reader+0x14）裡的位移」，讀不到 GUI 時退回原廠池。
  新測試 `test_effect_glyphs_when_the_pool_is_a_shared_copy` 在舊碼上失敗、新碼通過。
- 測試：test_rawview_build 23、test_rawview_image 29 全過。未上機。
- 第一守則待決：stub_sv 關機時把色彩存成 0x10–0x17（原廠未定義）—— 既有行為，沒改。

### DNG ColorMatrix：飽和度 +1 不再改變解出的白（2026-10-04，離線）

- 社群 Luka（fp-view-pack v0.2、rv-chartfit.patch）指出：舊式 +1 寫原廠非 OFF 常數 N，同一個 AsShotNeutral 用 OFF 標籤解成
  6503 K、用 N 解成 **7614 K**（本機 ROM 重算確認）→ 切 +1 在 Resolve 白點偏約 1100 K。每列正規化的驗算看不到。
- `rv_dngcm.py` 改為 C_k = diag(O·W)·inv(M_k)·A·Bradford(W→D65)（第 0 級仍是原廠 OFF 位元組）；M 仍是 Sigma 的
  （rv_color 不變，色卡擬合矩陣等鎢絲燈色卡再決定）。tables() assert 每級解出的白 = W、解碼 = LCD 的 M_k；__main__ 以舊式為必須失敗的對照。
  突變（換回舊式）：解碼檢查與白檢查各自都抓到。只有 rv_dngcm.inc 第 1 級變。測試 23 + 28 全過。fpSup.BIN（out/dev）8b126d0d…。
- **上機（2026-10-04，SD fpSup2，ISO 100）**：A001_042 OFF、043 RAW-SA、044 RAW-GA 皆為第 0 級（= 原廠 OFF）；
  045 RAW-SA＋飽和度 +1 = 新第 1 級（CM1/CM2 與 inv(P)·C_1 只差 ×10000 截位）；046（GA，使用者忘了切飽和度）第 0 級。
  每段逐格 CM 不變；五段 AsShotNeutral 相同。
