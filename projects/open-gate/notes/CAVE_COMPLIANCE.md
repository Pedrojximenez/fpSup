# 空洞區(cave)合規:Sensor Lab r80 覆寫證據與 USER 搬遷

2026-10-04。觸發:裝 Sensor Lab 卡時拔卡,原廠「無記憶媒體」變成文字代碼 `1478`,重開也一樣。

## 本輪狀態：離線搬遷完成，r81 錄影實機凍結，r83 待上機

- 歷史 r80 的五個區段覆寫原廠非零 cave 資料，是已證實的舊卡問題；
  `1478` 的原因仍未證實，不能把兩者畫上等號。舊卡與舊固定位址計畫
  仍不適合作為驗收或發布依據。
- 新建卡路徑把核心程式／資料打包成 B2_5 配置的 **9,040 B 核心封裝**，
  連同 **652 B journal guard** 共 **9,692 B** 複製到 USER 常駐區，
  並處理 **125 筆重定位**；
  19 個核心與 10 個後期 UI hook 的 veneer 由 `CAVE_BUMP` 執行期配置；
  連同 6 個外部指標字，共有 35 個受保護的原廠字位置。
  最終 VBIN **沒有 Sensor Lab 固定位址 cave 區段**。普通／debug／Fast 普通／
  Fast debug VBIN 分別為 **54,712／57,240／55,344／57,920 B**，均低於
  `0xF000` 的選單區塊起點；四種模式與替代 AXIS 配方共八組均通過離線建置。
- 共用 stage2 現在於 journal 配置或普通／強制關機 callback 註冊失敗時，
  在 pass 1 與任何產品入口之前停止。USER 常駐 launcher 在武裝 hook 前
  再核對兩張 callback 清單、journal 對原廠字的覆蓋和待裝位址現值。
- [搬遷後整卡模擬](../build/test_res_lab_migrated_boot.py)執行真實 loader、
  stage2、USER relocation、核心與後期 UI 安裝及兩次關機回呼；
  普通版 **290 筆**、debug 版 **297 筆**非 cave journal 記錄還原，原廠
  `0xC0730000..0xC0735000` 的 **20,480 B** 維持原樣。已保存
  [r81 debug 非 Fast 成品](../../res-lab/cards/20261004-b25-menu-r81-user-relocated/debug/)
  通過最終成品檢查與 15 種損壞成品測試；
  B2_5 parser 在這項模擬中以成功回傳替身處理；
  這些離線通過沒有涵蓋真實錄影流程。使用者回報已寫入 fpSup2 的 r81
  在按下 REC 後立即凍結，而較早 r80 固定位址版沒有這種立即凍結。
  r81 成品已定位出搬遷後 profile ID 讀錯，只保留供問題追溯，不再作錄影
  驗收。修正後的 [r83 debug 非 Fast 候選卡](../../res-lab/cards/20261004-b25-menu-r83-picker-reloc/debug/)
  已通過八組建置、最終成品與 15 種損壞成品檢查及整卡離線模擬；
  fpSup2 仍是 r81 最後一次寫入紀錄，目前未掛載。r83 尚未寫卡或實機複驗。

以下第 1–5 節保留 r80 問題的來源與搬遷前規劃，不能讀成新卡的目前配置。

## 0. 規則(使用者)

> 空洞區有一個索引,紀錄下一個沒有使用的空洞區位置,我們必須遵照這個規則,而且空洞區只可以放
> hook 韌體指標,不能隨意使用。 —— 全產品都要遵守。

- 索引:`CAVE_BUMP` = `0xC072E060`,arena `0xC072E064..0xC072EFB4`(3,920 B)。stage2 每次開機把 bump 重設到
  arena 底(`fpSup/fp_usb_shell/asm/stage2.S:100-104`);沒有 free list,誰要就往上推。
- arena 裡只放 hook 的跳板(veneer):`0xE51FF004`(`ldr pc,[pc,#-4]`)+ 本體位址,8 B。
- 程式與資料向分配器要:`H_GET 0xC001D740(desc, class 0 USER, size, 0)` + `H_ADDR 0xC001D7F0`,永不釋放。

## 1. ★ 歷史 Sensor Lab 卡覆寫原廠韌體資料(有證據)

- 原廠映像的零區是 `0xC072DE64..0xC0732A40` 與 `0xC0732C84..0xC0734C84`;中間 **`0xC0732A40..0xC0732C84`
  (580 B)有 120 B 原廠資料**,從一個 `0xFFFFFFFF` 開始(調查推測像 IMU 設定,`IMU_w71c1` 結構從
  0xC0732C40 起;擁有者未查)。來源:`projects/fc-scale/notes/FC_SCALE_CARD_AS_VBIN.md:32`,用映像重掃確認。
- `imx410_plan.py:47` 的 `CAVE_HI = 0xC0732C84` 把這段當成可用;240 fps 的 5 段 payload
  (`imx410_rate_native.py:37-43`)正好蓋在上面:

  | 段 | 範圍 |
  |---|---|
  | native_rate_1 | 0xC0732A20..0xC0732A6C |
  | native_rate_2 | 0xC0732AA0..0xC0732AEC |
  | native_rate_6 | 0xC0732B20..0xC0732B90 |
  | native_rate_7 | 0xC0732BA0..0xC0732C10 |
  | native_rate_5 | 0xC0732C10..0xC0732C20 |

- `layout_errors()` 用的就是錯的上界,所以從加入 240 fps(約 2026-09-30)起**每一張 Sensor Lab 卡都有**
  (已解析 r3、r5 plain、r80 fast-debug 確認)。
- 2026-10-04 對 r80 **最終** `fpSup.BIN` 再做逐位元組核對:5 個區段有 352 B 落在這個
  580 B 範圍,其中 67 B 原廠非零且全被改動。上面的 120 B 是整個範圍的原廠非零總數,
  **不是** r80 實際改動的非零位元組數。
- stage2 不把 cave 記進 journal(`stage2.S:28,40-41`),撥電源開關是暖開機、映像不重載 ——
  **被蓋掉的原廠資料拔卡、撥開關都不會恢復,要拔電池冷開機。**
- 韌體裡找不到指向這段的字面值或 movw/movt(可能是基底 + 偏移),所以還不知道誰在用、壞掉會怎樣。

## 2. 「1478」= `No memory media.`

- 原廠字串池 `0xC18C0474` 偏移 `0x331C` = ASCII `1478`;`English.nloc` 裡 `1478 = "No memory media."`
  (`research/ui/tools/nbr_stock.py`)。.nloc 用 FNV-1a(id) 索引。
- 畫面出現 `1478` = 池偏移解析正常、**查 .nloc 失敗**,於是畫出 id 本身(CSV 寫字面文字也是靠這個行為)。
- FSPL 共用字串池(`fpSup/uishare/ui_pool.c:30-37`)從 USER heap 配、保留原廠前綴,不太像兇手(推測)。
- 推測 A:sl_excl ROLE 6/7 掛 page parser `C05E82F0`、用 `C05E84D8` 註冊私有 NBR,可能改變 .nloc 查表的情境
  (fp-native-ui 記過「.nloc ID 換頁就畫不出來」)。推測 B:第 1 節的原廠資料被蓋。兩者都沒證據。
- 分辨:修好第 1 節後拔電池冷開機看;不插卡冷開機;換 Lossless 卡(同樣用 FSPL);Sensor Lab 不帶
  `--b25-menu` 或 `WITH_RATE_NATIVE=False`。
- 同一時期另一個未解:UHD 下把位元深度 8 -> 12 bit 時凍結(設定區讀回仍是原廠合法值)。

## 3. 誰合規、誰不合規(依使用者的規則)

| 產品 | cave 用法 |
|---|---|
| lossless 0.1.2test、raw-view 0.2.3test | 0 段 —— 合規 |
| gyro-base 1.14.0 | 只有 park stub 76 B |
| usbshell | `0xC072F000` 的 96 B(worker ABI) |
| **og3k 0.2.8a / og2k** | **32 段、10,196 B 固定位址在 0xC0730000..0xC0734C84** —— 不合規 |
| **Sensor Lab 舊卡至 r80** | 全部程式與資料在 0xC0730000..0xC0732C84 手挑位址,外加第 1 節的覆寫 —— 不合規 |
| **Sensor Lab USER 配置** | 無固定位址 Sensor Lab cave 區段；19 + 10 個執行期 veneer 使用 `CAVE_BUMP`。r81 成品與離線模擬通過，但實機按 REC 立即凍結；修正候選仍待實機複驗 |

`fpSup/tools/cave_audit.py:40` 把 `CAVE_HI` 設在 0xC0730000,所以把 OG 判成 clean;依使用者的規則它也要改。

## 4. 合規的做法(Lossless / Gyro 現行)

- launcher 是 destination-0 區段(`--boot-bin FILE:0`),在 staging 原地執行:向 USER 要一塊、整個 blob 複製
  過去、清零狀態區,`0xC000E91C`(D-cache)-> `0xC000EABC`(I-cache)再執行。
  Lossless:`fpSup/lossless/native/card.S:82-180`;Gyro:`fpSup/gyro/gsup_launch.S:58-118`。
- 裝 hook:要掛時才讀 `CAVE_BUMP`、加大小、檢查不超過 `0xC072EFB4`、寫回 bump;寫 veneer、清快取,
  **最後**才在 hook 點寫 `BL/B`。Lossless 先確認每個點還是原廠字才 arm,全有或全無(`card.S:244-330`);
  Gyro `writer_core.inc.S:1336-1390`;uishare Thumb veneer `ui_apply.c:237-271`。
- payload 找自己的資料:Lossless 用 pc 相對 + r11(常駐 - staging),C 以 `-fropi` 編;Gyro 讀池指標加固定偏移。
- 關機寫回:每個 hook 點宣告成 4 B、內容是原廠字的區段(`gyro/build_base_card.py:221 hook_sites()`),
  stage2 在 entry 前記進 journal,關機由 loader 共用回呼寫回。

## 5. Sensor Lab 搬遷前的工作清單(歷史)

- 寫死的 cave 位址:og3krecipe 7、imx410_fmt 9、imx410_canvas 3、imx410_aspect 3、imx410_fps 2、imx410_rate 4、
  og3kgs 3、og3ksel 7、og3kname 3、og3kfmt 4、og3krestore 3、og3kout 10;另有 imx410_rate_native、sl_excl 經 builder
  拿 FLAG/MARK/RATE240,sl_modes.c 13 個 `-DSL_*`(`build_sl_menu.py:44-53`),`sl_menu_launch.S` 寫 MARK 0xC0730380,
  `--vshl-entry` 是 RESTORE_CODE 絕對位址。
- hook:19 個 ARM `B/BL` 由 pass 1 直接跳進 cave;`--b25-menu` 再加約 10 個(vtable 字、page parser 的 Thumb B.W)。
  改成 veneer 約 30 x 8 = 240 B arena。
- 可沿用:`sl_menu_launch.S` 已是 lossless launcher 的形狀(USER 區塊、複製、清零),缺 hook;照 `card.S` 補 RESIDENT、
  veneer 與「全是原廠字才 arm」,hook 點用 `hook_sites()` 宣告。
- 主機工具(og3k_load、ogstate、測試)讀固定的 FLAG/MARK:改成掃 arena 的 veneer、跟指標找到區塊開頭的 magic。
- 工作量約 3–5 天;風險在 hook 從 pass 1 改成 entry 時才 arm 的時序(QS 從開機就快取、picker 初始化),要對照組上機。

## 6. 處置與待驗項目

`build/res_lab_cave_audit.py` 仍使舊的固定 cave 計畫、USB 直裝路徑與 AXIS
實機推送在寫入前失敗；建卡器則先把歷史計畫轉成 USER 區段與原廠字 hook 宣告，
再對真正交付的 VBIN 做 cave 與引用檢查。只把五段挪到另一個固定零區的做法
仍會被拒絕。建卡器先在暫存目錄完成所有檢查，通過後才移入指定輸出目錄。

搬遷後入口會在 USER 配置區複製並重定位常駐程式／資料，完成 D/I 快取發佈，
再核對 journal 與兩張 PowerOffMgr 清單；核心與後期 UI 分別在自身 hook
仍是原廠字時配置 veneer、最後武裝。執行期會改的外部 MOVW/MOVT 指標字
也先以原廠字區段交給 stage2 journal。共用 stage2 的 `lh_setup` 失敗路徑
已改為在 pass 1 前停止，強制清單的註冊回值也會檢查。

舊 r80 原卡的再現仍保留於 [`test_res_lab_warm_cave.py`](../build/test_res_lab_warm_cave.py)：
297 筆非 cave journal 會還原，但 67 個被覆寫的原廠非零位元組在兩次
關機回呼後仍改變。新整卡模擬的普通版 290 筆、debug 版 297 筆還原與原廠
cave 保持原樣，是對
新產物的另一項離線觀測，不能倒推 r80 安全。兩項測試都不是實機證據。

仍須在相機上確認開機、不錄影關機／再開、上一張卡留下映像時的暖啟動、
B2_5 私有選單、修正後基準錄影與 `1478` 是否重現。整卡模擬以 stub 代替原廠
B2_5 parser 和其他韌體服務，無法證明感測器時序或 UI 生命週期。若先前
關機回呼漏跑，暖映像可能在本次載入前就留有舊 hook；新 gate 可拒絕再次
武裝，不能消除載入前已存在的殘留風險。

## 7. r81 錄影立即凍結的定位與修正

2026-10-04 使用者回報：搬遷後的 r81 卡按下 REC 立即凍結；比較用的較早
r80 固定位址版沒有立即凍結。這是實機症狀回報，尚缺相同模式、位深與格率
的逐項 A/B 紀錄；r80 的已確認原廠資料覆寫依然存在。

檢查實際寫入的 r81 `fpSup.BIN`，錄影 picker `imx410_fmt` 在建立 `ENTRY`
時，用舊的 `PROFILE_ID - RECIPE = 0x1AC` 作為相對位移。USER 封裝把兩者
壓到相距 `0x1A4`；舊指令於是讀到 `COLTAB+4` 的第二個欄表位址
`0xC0BE3FA4`，將它寫成 profile ID，而預期值為 **87**。讀錯 profile ID
是成品位元組可重現的事實；它能解釋錄影進入時錯誤選表，是否為此次凍結的
唯一原因仍需相機重測。

來源已將 picker 改成載入可重定位的 `PROFILE_ID` 絕對位址再讀值，並把
`sl_excl_9` 程式槽位移開 8 B。[新的離線回歸測試](../build/test_res_lab_record_picker.py)直接執行 USER 封裝後的
picker，核對 `ENTRY` 寫入 87，且故意還原 r81 舊指令時重現錯讀。
整卡模擬與這項測試不能替代實際按 REC；修正候選成品的相機結果待補。
同一 r83 候選也修正 MODE 清單只按 FILTER 的 Frame rate 篩選、不得被使用者
錄影 FPS 設定縮減的規則；已寫卡的 r81 不含這項更正，選單實機結果也待補。
封裝後 picker 的離線對照結果是 r81 把 `0xC0BE3FA4` 寫入 `ENTRY+4`，
r83 寫入 **87**。這仍未證明實機錄影不會凍結。
