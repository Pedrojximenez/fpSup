# 多格式 OG 核心:一個核心 + 每格式資料列(設計)

**名稱(使用者 2026-10-07):這個多格式核心叫 res-custom** —— 檔案 `\fpSup\32RESCUS.BIN`、sup_id `RCUS`、程式在 `projects/open-gate/build/res-custom/`。
舊名(本筆記較早的段落與上機紀錄裡可能還看得到):`ogcore`、`32OG.BIN`、sup_id `OGCO`。選單 sup(`31OG3K.BIN`、`31OG2K.BIN`…)名稱不變。

## 2026-10-09：可擴充的 Virtual RCD

已實作一個共用 producer 契約，Res Lab 是第一個使用者。完整 ABI、容量、資料壽命與
套用流程見 [VIRTUAL_RCD.md](../build/res-custom/VIRTUAL_RCD.md)，精確成品與離線證據見
[驗證紀錄](../../res-lab/validation/20261009-virtual-rcd-v1/RESULTS.md)。

producer 提供完整記憶體 RCD，由 res-custom 驗證並編譯成既有虛擬表。註冊 16 個工具
仍只共用一個動態解析度列，mode／profile 預算由當下配方決定；不設 Res Lab／Julien
兩個專用套用接口。一般磁碟 RCD 保留原本路徑；Julien style 尚未實作接入。
Help alias 導向活動工具的私有設定頁，錄影設定頁與列表由 consumer 管理。
loader／AutoRun 不變，服務指標附在 consumer 自己 claim 的 picker veneer。

Apply 先在自有 scratch 編譯、核對 FPS 與容量，停止 live view 後再次核對 busy 才提交。
圖示保持不可變並去重；每次開機最多 32 個不同 pack、合計 4 MiB。
記憶體配方不從上次的列名稱自動恢復，需再次 Apply。
本輪只完成本機來源與離線驗證，未操作相機、寫卡或發布。

**2026-10-23 HDMI RAW 介面研究（尚未接入）：** 可以保留同一解析度列與 producer，
由 consumer 依輸出目標編譯。HDMI 需要自己的 picker／display 身分、format11 與
RAW buffer 路由，現有 CDNG 位深、gain、writer／rate 政策不能直接搬過去。
28 模式的原生離線驗證與相容設計見
[HDMI_RAW.md §7](../../../research/interfaces/notes/HDMI_RAW.md#7-能否與-res-custom-共用介面2026-10-23)。
目前 ABI2 與 RCD 的產品行為未變，任意尺寸外錄仍未驗證。

2026-10-07,**只是設計**,沒有實作、沒上機。使用者決定(向 Jose 要不到原始碼):
保留我們的原始碼核心,做一個類似 Jose registry/slot 的「一個核心 + 每格式一列」。
格式:OG3K、OG2K、S16、OG3.5K、OG4K。前文:`projects/jose-hurtado/notes/JOSE_VS_OURS.md`(他的資料逐欄讀出)、
`VIDEO_CLAMP_V3.md`(階段 A)、`fpSup/uishare/QS_SHARE.md`(§9 API、§12 選擇不進設定區)、`LOADER_V3.md`。

## 0. 結論

**使用者 2026-10-07 定案**:錄影核心一檔 + 選單各一檔;核心照 res-lab 的 v3 形狀(`rl_v3.c` 的 entry:全部 claim → veneer →
任一拒絕 RELEASE → fixup → 靜態字 → 指標對 → 核心 hook、picker 最後 → restore;`OG_V3_PAIR` + `og_pic.py` 建置期改寫 PC 相對、兩原點證明);
保留 OG3K 100p;**不改原廠 profile**,各格式改用 res-lab 的自帶 profile(§3.1)。

- **錄影核心:一個 sup**(暫名 `32RESCUS.BIN`),原始碼裡帶五格式的資料列,建置時用 `--formats` 決定帶哪些列。
  核心擁有全部 hook 與全部執行期字。切換時做 Jose regapply 的語意:**「所有列的字寫回原廠 → 套用選中的那列」**,
  外面包我們現有的交易規則(關中斷、先撤 FLAG、最後發布、MOV 守衛)。
- **選單:每格式一個 UI sup**(`31S16.BIN`、`32OG3K.BIN`…),只有一個 uishare `resolution_qs()` 區塊,不帶錄影程式。
  卡上放哪幾個 UI sup = 選單有哪幾列;核心不需要找它們,只認「被選中的是哪個格式」。
- **不建議**「每格式一個完整核心檔、錄影 hook 套娃」:OG3K/OG2K 今天能這樣,是因為兩者執行期字只共用預覽高。
  加入 Jose 的格式後共用變多(OG3.5K/OG4K 同 mode 3 時序與 clamp、同 p171;S16/OG2K 同 p13),
  離開的層與進入的層誰先跑不固定,共用字會被晚跑的那層蓋掉;要解決得建跨檔的共用帳本,
  而加載器的服務表只在 entry 期間有效(LOADER_V3 §5:`SL_SVC_AT` 跑完歸 0),執行期找不到別人的帳。§2。
- 工作量約 **13–17 天**(含 2–3 天上機)。§8。

## 1. 要守住的(不能因為重構退步)

| 項目 | 現在在哪 | 新核心 |
|---|---|---|
| MOV 守衛 | `og3kfmt`(`C005BE58`)+ FMTLATCH;FLAG = 選了 OG **且** CinemaDNG | 照搬;所有只看 FLAG 的 hook 仍只看 FLAG |
| 引擎組態三欄 `+0x30/+0x90/+0xC0` | `og3kcanvas`(`write_hirate`、`write_engfps`) | 每列的錄影 canvas 清單都帶;`+0x30` 照舊取原廠同一 picker 格的值(`engine_fps(slot)`) |
| 堆疊 8 對齊 | 現有 payload 只有重放原廠序言是奇數 push | **加建置檢查**:payload 的 push/sub sp 必須 8 的倍數,重放序言要標記豁免(比照 uishare `test_stack_alignment.py`) |
| 不改原廠 profile(使用者 2026-10-07) | og3kcanvas 改 canvas 的 RAM 複本,原廠 PARAM 列不動;但 picker 回傳的是原廠 id(p83/p13) | **改用 res-lab 的自帶 profile(§3.1)**:每格式一個私有 id,picker 回它,canvas hook 整列宣告;p13/p83/p171 一律不動 |
| video clamp | 階段 A(GTAB 私有群組) | 每列的 donor 模式都帶 |
| 1:1 PIC / 兩原點證明 / OG_CHAIN 層 | `og_pic.inc`、`build_v3_og.py` | 照搬 |
| 開機重套 | og3krestore(setter + MovSigProcess 重啟) | 照搬;選擇來源換成 §6 |

## 2. 一檔還是多檔

| | A 一個核心 + 五個 UI sup(建議) | B 每格式一個完整核心(OG_CHAIN 套娃) | C 一個 sup 含核心與五個選單列 |
|---|---|---|---|
| 錄影 hook | 核心一層(CHAIN,不是自己的往下) | 每檔一層 | 一層 |
| 共用執行期字 | 核心獨有,「全部還原 → 套用」無順序問題 | 需要跨檔共用帳本(見下) | 同 A |
| UI | 每格式一個 `resolution_qs`(QS_SHARE §5 的形狀) | 同 A | 要 uishare 支援一個 sup 多個 `QS_OPTION`(每個要自己的 k、圖名前綴)——**要問 uishare 那邊** |
| 使用者挑格式 | Merge 頁勾 UI sup | 勾核心檔 | 要重建 |
| 程式碼重複 | 無 | 五份核心(各約 10 KB + veneer) | 無 |

B 的問題具體是:setter 層由外往內跑。進入的層在外、離開的層在內時,離開的層後跑;
若兩者共用某字(mode 3 時序/clamp、p171、p13、預覽高),它會把剛設好的值寫回原廠。
今天 OG3K/OG2K 用 `OGSAVE`(= 新選的 enum)讓離開的層跳過**共用**群組(階段 A 的 `OG_GTAB_SHARED`),
但這要求「共用」對每一對格式都一樣。五格式時「共用」是成對不同的(OG3K 離開給 OG4K 要還原 98,
OG4K 離開給 OG3.5K 不能還原 mode 3),需要每個字的持有者清單 —— 只有加載器的登記簿有,而執行期拿不到。
所以 B 要加一個 sup 間的「OG 匯流排」(第一個 OG 從 cave 建、後來的經 header 鏈找到並登記自己的列),
那等於把 A 的核心邏輯放進每個檔再選一個當主人,複雜度只增不減。

**A 的 UI sup 怎麼辨識**:QS_SHARE §12 定案後,「目前選擇」= `H_SEL`(被選中 UI sup 的檔名)。核心有一張建置期的
「格式名 → 列」表,檔名去掉兩位數前綴與副檔名(`32OG3K.BIN` → `OG3K`)對到列;§12 落地前則用 `ui/enums.py` 的固定值
(OG3K 4、S16 5、OG2K 7、OG4K 8、OG3.5K 9)直接當列鍵,與今天 og3ksel 的 `cmp r1,#OG_ENUM` 同型。
UI sup 不在卡上 → 它那列永遠不會被選中;核心仍 claim 該列的字(EXCL),只是不寫。

## 3. 資料列

### 3.1 自帶 profile(res-lab 的做法;⚠ mapping 寫入那部分已由 3.2 取代)

來源:`IMX410_FULL_DESIGN.md` §13(r71–r72 實機)、`build/imx410_plan.py`(`MAPPING`、`PRIVATE_PROFILE`)、`build/imx410_fmt.S`。

- **機制**:`FUN_c043a158` 用 `mapping[0xC0BD05D4 + id×4]` 找列 → `FUN_c0439d18` 把 65 欄組成 canvas(RAM)→ 我們的 hook
  `C043A19C` 就在組完之後。所以 canvas = 一整列 profile;**給一個私有 id、在 hook 裡把 canvas 整列寫成我們要的值,就是宣告一個 profile**。
  私有 id 用 mapping 的**原廠空槽**(500 槽、194 空,值 `0xFFFFFFFF`),安裝時寫一個字指到「最像的原廠列」當底(res-lab:id 87 → p83 的列;
  r72 另用 p171 當底宣告 6064×4042 讀出,A001_006/007 實錄通過)。picker 表項 `+4` 回私有 id。
- **R1 已查(本次,[驗])**:65 張欄表**只**在 `FUN_c0439d18`(`C0439D2C..C043A12C` 的 65 組 movw/movt)被讀;
  它只有 `FUN_c043a158` 一個呼叫者,也就是我們 hook 的那一處。映像裡沒有其他 movw/movt 或字面值指向欄表(字面值命中 31 處全在 UI 資源資料,值巧合)。
  → **只改 canvas 就涵蓋所有消費者,不需要寫任何欄表**。res-lab 另把 29 欄寫進沒人引用的列 6/7(p13/p14)的欄表(`declare_post`),
  依這個掃描是多餘的;新核心不做(若上機發現不夠再議)。
- **id 的數值仍有語意**:增益分派 `FUN_c043a1c8` 依 id 範圍(131..190 = raw movie)分類,範圍內沒有空 id → `og3kgs` 保留(§13.4)。
- **一個 id 還是每格式一個**:同一時間只有一格式生效,一個 id 就夠;但為了不和 res-lab 的 87 搶同一槽(兩者本來就互斥,仍避免混淆),
  OG 用另一個空槽(候選 88 以上的空 id,建置時對映像確認是 `0xFFFFFFFF`),claim EXCL。
- **每列的底**:OG3K → p83 的列(與今天逐字相同的出發點,res-lab A001_002 證明 id 87 + p83 底 = OG3K)、OG2K/S16 → p13 的列、
  OG3.5K/OG4K → p171 的列;差異全部由該列的 canvas 清單寫(Jose 寫進 p13/p171 PARAM 的那些格,改寫在 canvas)。
- **預覽高(六個 LV profile 的 `+0x28`)**:今天 GTAB 寫原廠欄表 —— 這也是「改原廠 profile」。新核心改成 canvas hook 在 FLAG = 1 時,
  對 id ∈ {5, 210, 227, 257, 258, 259} 的 canvas 寫 `+0x28`(Jose 的 S16/crop 待機框也是這樣做)。前提:選格式後 LV 會重建 canvas
  —— og3krestore 的 MovSigProcess 重啟本來就保證這點;**這是行為改變,要上機驗**(備案:維持 GTAB,但那就不是「原廠 profile 不動」)。

### 3.2 虛擬 profile 與虛擬 mode(使用者 2026-10-07 再修正:取代 3.1 的 mapping 寫入與「搬三張表」)

**原則**:原廠表、描述子、mapping、原廠 profile 一律不寫;在韌體「查詢」那一層攔截我們的虛擬 id,
回傳由核心變數(格式資料列 + 目前選擇)組成、放在 sup 塊裡的列。本節是**只讀調查**的結果([驗] = 讀反編譯/映像)。

#### 3.2.1 虛擬 mode —— 可行,攔截點是七個「找索引」函式

[驗] IMX410 的模式資料全部掛在描述子 `0xC2F1E654`(全映像只有 `C0322E8C`/`C0322EA4` 兩處組出它)與暫存器描述子
`0xC0B5FDA4`(只有 getter `C0326E20`)。映像裡**沒有任何 movw/movt 或字面值直接指向各表**;所有讀取都是
「描述子欄位的基底 + 索引 × 步距」,索引來自下面七個線性掃描函式(都比對 `row[0] == mode_id`):

| 函式 | 表(描述子欄位,步距) | 呼叫者 | 索引會被快取嗎 |
|---|---|---|---|
| `FUN_c0320ba0` | 時序 `+0x00`,0x20 | `C0320FC8`(3 處)、`C0321160`(6 處)、`C0321290` | **會**:`C0321290` 存進 imager 物件 `+0x0C`,`C0320740/0818/08B0` 等直接用 |
| `FUN_c0320b38` | metadata `+0x08`,100 | `C0321028`(約 20 處,含 nominal fps `C032C750`) | 否 |
| `FUN_c0320e90` | `+0x24`,0x28 | `C0320700`、`C0321290` | **會**(`+0x10`) |
| `FUN_c0320ef8` | `+0x48`,0x14 | `C0321088`(3)、`C0321290` | **會**(`+0x14`) |
| `FUN_c0320f60` | `+0x40`,0x38(接收器參數,也就是階段 A 的 clamp 記錄 `0xC0B5C638`) | `C0320AB0 → C032D5E0` | 否 |
| `FUN_c0320c00` | `+0xF4`,0x68 | `C0321100`(14 處) | 否 |
| `FUN_c0326db8` | 暫存器記錄,0x288(mode + 161 字) | 只有寫入器 `FUN_c03258c8` | 否(用完即丟) |

- **關鍵**:這些函式回傳的是**索引**,不是指標;消費端自己算「基底 + 索引 × 步距」,而且 `+0x0C/+0x10/+0x14` 會被快取。
  所以只攔「取列指標」的函式(`C0320FC8`、`C0321028`…)**不夠**。可行的做法是攔上表七個找索引函式(都是函式入口、
  序言是單純的 push,可 replay → CHAIN),對虛擬 id 回傳一個**假索引**:令 `基底 + 假索引 × 步距` 在 32 位元環繞下
  正好等於我們塊內的那一列。條件只有對齊:`(列位址 − 基底)` 要能被 `gcd(步距, 2^32)` 整除(0x20→32、100→4、0x28/0x38/0x68→8、
  0x14→4、0x288→8),假索引 = `(差 / g) × (步距/g)^-1 mod 2^(32−log2 g)`。我們把列放在對齊位址即可。
  其他 id 一律交給下一層(chain_next / 原廠)。
- **生命週期**:列在 sup 塊裡永久存在(塊不釋放);內容只在選擇交易(關中斷)裡改。快取的索引永遠有效。
- **因此 donor 時序與 clamp 都不必再改原廠**:OG3K = 從 mode 98 複製出的虛擬 mode,時序列由選中的格率決定(picker 命中時改我們的列),
  接收器列(0x38)帶 video clamp 位元。原廠只剩 hook 站點與 uishare 的 UI 字。
- **mode id 的數值**:要 < 250(名稱槽 `0xC0B575CC + id×0x20` 在 ROM 裡已排到 250 格)且不在 70 個原廠 id 裡;`0x77` 是「目前模式」的
  哨兵,不能用。

**做不到 / 未確認(要先處理)**

1. **`FUN_c031fb30` 把快取索引截成 16 位元**存進另一個物件(`+0x1CC` = `[3]`(時序索引)、`+0x1D0` = `[4]/[5]`)。假索引一截就錯。
   這是 imager 狀態的快照,消費者還沒查(若只是記錄/除錯 → 無害;若有人拿它回頭索引表 → 虛擬 mode 在那條路上壞掉)。**必查**。
2. **寫死模式號的比較**(例:待機 LV 常駐 mode 8、`0x77`、某些 `switch(mode)`):虛擬 id 會落到 default 分支。全映像列舉還沒做。
3. 原廠消費端若用索引去讀**別的**平行陣列(大小 70 的 RAM 陣列)會越界 —— 目前看到的快取索引都只配自己的表,但沒有窮舉。
4. IMX455(fp L)用另一組描述子(`0xC2F1E7B4`、`FUN_c0326e30`)—— fp 不走,不必處理。

#### 3.2.1a 四項只讀調查的結論(2026-10-07)

**① `FUN_c031fb30` 的 16 位元截斷 —— 不是問題 [驗]。** 它的參數是 `FUN_c031fa00()` 回傳的 `0xC343A99C`
(拍照擷取的統計物件,`FUN_c031fae0` 在 `AcqEndTrans` 之後填它),不是 imager 物件 `0xC343B588`;
`[3]/[4]/[5]` 是統計值,不是快取索引。全反編譯沒有任何地方以絕對位址讀 imager 的 `+0xC/+0x10/+0x14`。

**② 寫死模式號、繞過找索引函式的地方 —— 找到一張表,另有一處常數比較 [驗];未窮舉到底。**
- **描述子 `+0x128` 表(步距 0x5C,筆數 `+0x12C`,依 mode 號找列)沒有找索引函式,是各處內聯掃描**:
  `FUN_c030e2a0`(設定模式路徑,有「找到才做」守衛,且只在 `+0x11C` 旗標時)、`FUN_c032df88`(同樣有守衛)、`FUN_c031acd8`(找不到就跳過)、
  **`FUN_c030fd68`、`FUN_c0310120`、`XC_ImageSensorIMX410::v32`(`C03249A0`)沒有守衛** —— 找不到時索引 = −1,讀表前 0x5C 的資料;
  v32 拿它算放大鏡的讀出窗位置寫進暫存器 `0x22..0x25`。另外 `FUN_c031b3a0`(放大/AF)用 −1 之後的列。
  內容是**放大鏡/裁切的窗位移**(每列 `+0x20/+0x2C/+0x38/+0x44` 各 3 個縮放級)。
  → 虛擬 mode 在**待機與錄影**不經這些路;**放大鏡**會。處理方式見下方「放大鏡」。
- **常數比較**:`blk_c03.c:55152` 的函式把 0x99、0x9A、0xA6..0xAE、0xB7 排除在外 —— 虛擬 id 別落在這些值即可。
- **「目前模式號」的 32 個消費點追過 [驗]**(`FUN_c032c720` 的呼叫者):多數是存起來比較「變了沒」、印 log,或交給
  `FUN_c032c7b8/c860/c898/c8c8`、`FUN_c032dee8`、AE 物件 `0xC3403F70` 的 `+0x58`(`FUN_c029ff28` → `FUN_c032c7b8`)—— 最後都走回
  上表的找索引函式,虛擬 id 會被我們的層接住。**最後 4 處也追完了 [驗]**:
  `FUN_c035fda8`/`FUN_c0360268`(`0xC347FA6C` 的 `+0x9C`)那一處收到的其實是 `FUN_c032c7b8(0x77)` 的**幀週期**,不是模式號;
  imager 子物件 vtable `+0xBC` = `XC_ImageSensor::v45`(`C0322330`)是空函式;`FUN_c0686800` 只把模式號交給 `FUN_c032c860`(→ `C0321028`,已接住);
  `FUN_c020bef8` 把要求的模式號存起來,之後經 `FUN_c030ce00` 走設定模式的正常路徑(已接住)。→ **主路沒有漏網的消費點。**
- **放大鏡(使用者定案:走 (a),各格式下要能用)**[驗]:
  - `FUN_c030fd68`、`FUN_c0310120` 只從 `FUN_c030e2a0` 的「找到才做」分支呼叫,而 `FUN_c030e2a0` 的那段掃描只在 `param_5 != 0` 時跑;
    反編譯裡**所有呼叫者都傳 0**(`C0314xxx` 的三處與 shell 指令 `FUN_c030cd18`)→ 死路,不用處理。`FUN_c032df88` 也有守衛。
  - 真正要處理的:`FUN_c031b3a0`(放大/AF,讀目前模式 4 次:BL `C031B4D4`、`C031B574`、`C031B5E4`、`C031B660` 呼叫 `FUN_c03212f8`)、
    `FUN_c031acd8`(唯一呼叫者 `FUN_c030cc90`,模式在 `param_4`,再傳給 `FUN_c031ac38`)、`XC_ImageSensorIMX410::v32`(`C03249A0`,讀 `imager+4`,寫暫存器 0x22..0x25)。
  - 做法:**4 個呼叫點 BL hook**(那 4 個 `bl c03212f8`:回傳值是虛擬 id 時換成該列的 `zoom_mode`)+ **`FUN_c031acd8` 入口層**(`param_4` 同樣換)
    + **v32 入口層**(虛擬 id 時用我們列裡的放大位移自己算、寫同樣 4 個暫存器;其他 id 往下)。共 6 個 hook,都 CHAIN。
  - `zoom_mode` 預設 = donor(OG3K 98、OG2K 139,幾何相同,放大位移正確)。S16 的放大位移跟 mode 121 不同:v32 用自己的列可以給對,
    但 `FUN_c031b3a0` 內部的計算只能走 donor 的列 —— S16 階段要再確認放大鏡畫面框是否對(上機項)。
  - 未確認:donor 98/117/139 是否在 `+0x128` 表裡(描述子是開機才建,靜態讀不到;上機用 `mem get` 讀描述子 `+0x128/+0x12C` 只讀確認)。
- 純列印用的掃描(`+0x10/+0x14` 列表、`+0xF4` 的 `mode_list` 指令)只是看不到虛擬 mode,無害。

**③ 索引被拿去讀別的平行陣列 —— 沒有 [驗](反編譯範圍內)。** 每個找索引函式的回傳值只配它自己的表:
`[3]`×0x20(時序)、`[4]`×0x28、`[5]`×0x14、`C032D5E0` 用 `+0x40`×0x38、`c0326db8` 只配 0x288。沒有任何呼叫者拿索引當別的陣列的下標,
也沒有比較「索引 < 筆數」(會讓假索引失敗的那種檢查)。限制:只看了反編譯,沒有對組語逐條窮舉。

**④ canvas 建好後用 pid 的地方 [驗]。** `FUN_c0434e08` 把 pid 存在 holder `+0`;唯一的數值消費者是 `FUN_c043a1c8`,
依 pid **範圍**算類別旗標存 `holder+0x168`:<4、5..11、101..129 / 191..198 / 301..312 / 401..416、131..190 / 417..434(raw movie)、29..40、17..28。
→ 虛擬 pid 要挑跟底列同類別的號:p83、p13 都是「0」類,所以 42..100 之間不在任何範圍的號都行(res-lab 的 87 就是這類)。
`og3kgs` 照留(raw movie 那一類沒有空號)。另一個候選 `FUN_c0439380(+0x104 的 4 元素清單, x)` 是成員判斷,傳入值是否為 pid 未確認。

**總結**:虛擬 profile 可行(一個新 BL hook + 選對 pid 類別)。虛擬 mode 在設定模式、時序、metadata、接收器、暫存器、fps 這條主路上可行;
**放大鏡要額外 6 個 hook**(4 個呼叫點 + 2 個入口層);主路其他消費點都已追完。

#### 3.2.2 虛擬 profile —— 可行,不寫 mapping

[驗] mapping `0xC0BD05D4` 全映像只在 `C043A184`(`FUN_c043a158`)被讀;65 張欄表只在 `FUN_c0439d18` 被讀,它只有 `FUN_c043a158` 一個呼叫者。
所以虛擬 profile = 在 `C043A18C`(`ldr r1,[ip,r5,lsl #2]`,下一條之後就是 `bl c0439d18`,lr 在此是死的)換成 BL 到我們:
虛擬 pid → `r1 = 底列號`(原廠某一列,組出基底),否則照原指令讀 mapping;再由現有的 canvas hook(`C043A19C`)覆寫成我們的列。
不需要寫任何表。pid 的**數值**仍有語意(增益分派 `FUN_c043a1c8` 看 131..190),`og3kgs` 照留。
未確認:有沒有消費者在 canvas 建好之後又拿 pid 去查別的表(picker 表、回放名稱表用的是表項指標,不是 pid)—— res-lab 用 id 87 實錄通過是佐證,不是證明。

#### 3.2.3 對格式的影響

| 格式 | 虛擬 mode | 虛擬 profile |
|---|---|---|
| OG3K / OG2K | 複製 98(100p 另一個複製 117)/ 139,時序與 clamp 在我們的列 | 底列 p83 / p13 |
| S16 | **從 mode 121 複製,整列(時序、metadata 2112×1250、接收器、161 個暫存器)在我們的列** —— 不再改原廠 mode 121 | 底列 p13 |
| OG3.5K / OG4K | 複製 mode 3 + clamp | 底列 p171 |

這取代 §5 的 R2(a)(b):S16 走虛擬 mode。

**仍然要改的原廠字**(3.1 版;⚠ 3.2 定案後作廢 —— 虛擬 mode/profile 下只剩 hook 站點與 uishare 的 UI 字):

| 字 | 何時 | 說明 |
|---|---|---|
| `mapping[私有 id]` | 載入時 1 字 | 原廠是空槽 |
| donor 時序記錄 `+4/+8` | picker 命中時,離開寫回 | 感光元件模式表,res-lab 也一樣(70 donor × 2 字) |
| donor 的 clamp 兩字 | OG 生效期間 | 階段 A |
| S16 的模式 121 表 | 見下 | **自帶 profile 解決不了**(§5 R2) |
| hook 站點、uishare 的 CSV/配對表 | — | 照舊 |

每列一個結構(組合語言表,由 Python 計畫產生並逐欄驗證,取代今天 `TARGETS[...]` + 編譯期 `#define`):

| 欄 | 內容 | 例(OG3K) |
|---|---|---|
| `key` / `label` | picker 鍵前綴、解析度名 | `OG3K` |
| `sel` | 選擇鍵(§2:enum 或 H_SEL 名) | 4 |
| `aspect` | 長寬比 enum(2 = 3:2、3 = 16:9；核心 v2 起 9 = 2:1),給 aspect/out/name | 2 |
| `pid` / `base` | 私有 profile id(canvas hook 的守衛)/ 底列 | 私有 id / p83 的列 |
| `rate_max` | 最高格率 enum(反灰,Jose `+0x28`) | 5(59.94)|
| `picker[8]` | 每格率 48 B 一筆(今天 `fmttable` 的格式):鍵、donor 模式、時序記錄、hmax\|tail、vmax\|x、引擎格率;**另加**讀出視窗 `+0xC/+0x10`(Jose registry `+0x30/+0x34`)| 今天的 `FMT_OG3K` |
| `rec_canvas` | 錄影 canvas `{off,val}` 清單:raster、可見、producer/preview、平面碼由位元深度選、三欄、hirate | 今天 `CANVAS_REC` |
| `pb_canvas` | 回放 canvas 清單 | 今天 `CANVAS_PB` |
| `standby_canvas` | 待機/AF/放大鏡框(S16 的 716×424、crop 列) | — |
| `groups` | 私有 GTAB 群組:donor 模式 clamp、S16 的模式表補丁、(若必要)PARAM 格 | 98/117 的 clamp |
| `crop_row` | Crop Mode ON 時改用的列(OG3.5K/OG4K) | — |
| `out_tpl` | og3kout 的輸出描述模板幾何 | 3024×2010 |

五列的值(Jose 的部分從他的位元組讀出,`JOSE_VS_OURS.md` §1.3、§2;**使用前要再徵得他同意並致謝**):

| 列 | donor 模式(時序記錄) | profile | raster → DNG | 格率 | 讀出 / 縮放 |
|---|---|---|---|---|---|
| OG3K | 98(`C0B59540`)、100p 用 117(`C0B59A20`) | 83 | 3024×2010 → 3008×2000 | 23.98–59.94(我們今天還有 100) | 2×2 合併 |
| OG2K | 139(`C0B599A0`) | 13 | 2016×1344 → 2000×1334 | 23.98–100 | 3×3 合併 |
| S16 | 121(`C0B59580`),x_start 1984;另有模式 121 的表補丁 | 13 | 2112×1250 → 2096×1238 | 23.98–59.94、100 | 感光元件 1:1 視窗 |
| OG3.5K | 3(`C0B59560`),視窗 6062×4032 | 171 | 3464×2304 → 3456×2304 | 23.98–29.97 | ISP ÷1.75(RAW RWZM 1792) |
| OG4K | 3,視窗 6030×4020 | 171 | 3840×2560 → 3840×2560 | 23.98–29.97 | ISP ÷1.57(RAW RWZM 1608) |
| OG3.5K/OG4K crop | 同上,crop 列 | 171 | 同 DNG | 同 | 中央 1:1(RAW RWZM 1023) |

## 4. 交易與各 payload 的改法

**setter / 格式 setter(og3ksel、og3kfmt)**:找列(`sel` 比對)→ 算「生效」(列存在 且 CinemaDNG)→ 關中斷 →
- 有生效中的列且(要換列或要離開):撤 FLAG → 該列 donor 時序寫回 → **所有列的私有群組寫回原廠**(聯集,與 Jose 的 slot 0 同義;
  寫幾十個字,代價可忽略,換來沒有順序問題)→ 共用預覽高寫回(新列不是 3:2 時);
- 要進入:寫新列的群組、預覽高(3:2 → 1334)→ 記 `CUR = 列` → 最後 FLAG = 1。
同一份程式,og3kfmt 只換「生效」的算法與回跳,跟今天一樣。

| payload | 今天(編譯期單目標) | 改成 |
|---|---|---|
| fmttable(`C043CCF8`)| 掃一張表 | 掃全部列的 picker(或只掃 `CUR` 列;未生效時也要能回答,因為 picker 可能先於 setter —— 照今天行為:鍵命中就回);記 `PICK_ROW`、格率 index;Crop ON 且列有 `crop_row` → 時序視窗取 crop 列 |
| og3kcanvas(`C043A19C`)| 編譯期 PUT | 走 `CUR` 列的清單(Jose 的 `{off,val}` + `-2` 條件格式),profile 守衛用列的 `profile`;待機清單比照 Jose 依 profile 集合套用 |
| og3kout / aspect×2 / name | 常數 3:2、`OG3K` | 讀 `CUR` 列的 `aspect`、`label`、`out_tpl`;S16 是 16:9 |
| og3kgs、og3kfps×4、og3kpbsel | 只看 FLAG | 不變(nominal fps 已經由 fmttable 依格率鎖存) |
| og3krestore | OGSAVE == 本目標 enum | 依 §6 的選擇來源找列,呼叫原廠 setter;MovSigProcess 重啟照舊 |

**移植 Jose 的 hook(原始碼重寫,行為依他的反組譯)**

| 站點 | 用途 | 我們的寫法 |
|---|---|---|
| `C04A121C` | 格率清單狀態 | 依 `CUR`(或正在看的列)的 `rate_max` 回狀態類別;不是 OG 列 → 往下 |
| `C00A87E4` | 格率正規化上限 | 同上,夾到 `rate_max`,存的值不改 |
| `C04A1788` / `C00A93BC` | Crop Mode 反灰 / 生效值 | 列沒有 `crop_row` → 灰、生效值 OFF(存的值不動);有 → 原廠 |
| `C005BB60` | Crop setter | Crop 變了且 `CUR` 有 `crop_row`:時序視窗與群組換成 crop 列(同一交易) |
| `C043B6A4` | AF/放大鏡 picker(`FUN_c043b638`)| crop 列的框;**先 RE 清楚再寫**(§5 R3) |
| `C005C054`(regseltail) | 換列後補 apply/change、翻 Crop 逼 LV 重建 | **不移植翻 Crop**(會閃一格、暫改 `XC_UserSetting +0x334`);改用 uishare 的 `C05D90F0` 重新解析層 + og3krestore 那套 MovSigProcess 重啟 |

全部 hook 照 OG_CHAIN:claim CHAIN、不是自己的往下、replay 原指令。新增 6–7 個 hook → veneer 從 17 增到約 24,cave 預留要重算。

## 5. 先要解的 RE / 風險

| # | 問題 | 怎麼解 |
|---|---|---|
| R1 | ~~是否有消費者繞過 canvas 讀 PARAM~~ **已解(§3.1)**:沒有;Jose 寫 p13/p171 的格全部改在私有 id 的 canvas | — |
| R2 | S16 要感光元件**真的開窗**:Jose 在載入時永久改模式 121 的 metadata(`C0B59F54..`:6064×4042→2112×1250、25→100 fps)、`C0B5BBEC`(9 字)、`C0B5C71C..`(模式 121 的 0x38 記錄)、`C0B5DCA4`(7 字)、暫存器列 `C0B607D4..F0`(5 字),另時序 `+0xC/+0x10` 視窗 | **自帶 profile 管不到感光元件模式表。** 兩條路:(a) 私有群組,只在 S16 生效時寫、離開寫回(仍是改原廠模式表,但只在生效期間);(b) 宣告新的感光元件模式(§14.1:時序/metadata/暫存器三表搬到 RAM 約 55 KB,新 id 直接被線性掃描找到),**沒有人做過**。要使用者選 |
| R2' | OG3.5K/OG4K | 自帶 profile 可行:p171 底 + canvas(res-lab A001_007 已錄 mode 3 6064×4042 → 3:2);時序視窗 `+0xC/+0x10` 他寫的值 = 模式 3 原廠值,不用改;只剩時序 `+4/+8` 與 clamp(同 OG3K) |
| R3 | `C043B6A4`、`C005BB60` 的完整語意(只讀了他的反組譯) | 對照 `out/decomp/full` 的 `FUN_c043b638`、crop setter;寫成原始碼後與他的二進位做雙胞胎(31FMT 的雙胞胎引擎可重用) |
| R4 | OG3.5K/OG4K 頻寬(290–354 MB/s,只能 SSD)、OG4K DNG 沒有 +16/+10 邊 | 照他的值,上機確認讀檔軟體 |
| R5 | QS N:2 原廠 + 5 = 7 列,uishare f(N) 只實測 N=3、8(4..7 內插) | 上機看 N=7(或先放 6 列) |
| R6 | 第一守則:設定區存什麼 | 依 QS_SHARE §12(只存 2/3 + `H_SEL`);落地前沿用 enums.py 的固定值(5/7/8/9 是原廠未定義值,使用者已知) |
| R7 | mode 3/98 也是 AF/放大鏡模式 | clamp、時序只在 OG 生效時改(階段 A 已這樣) |
| R8 | 與 res-lab、31FMT 互斥 | 照舊:同點 EXCL/CHAIN 規則;31FMT 退役 |

## 6. 選擇從哪來

- §12 落地前:核心 setter 層看 r1 = 列的 `sel`(固定 enum),`OGSAVE` 存選中的 enum(今天 OG_SAVE_ENUM 的做法),og3krestore 依它重套。
- §12 落地後:setter 由 uishare 的 CHAIN 層先處理,核心讀 `H_SEL` 名字 → 列;`OGSAVE` 拿掉;開機重套由 uishare 統一觸發,
  核心提供「把列 X 套上」的回呼(MovSigProcess 重啟留在核心或搬進 uishare,跟 uishare 那邊協調)。

## 7. 測試

1. **OG3K/OG2K 不退步**:重構後的核心只帶 OG3K(或 OG2K)列時,對今天的 `30OG3K/30OG2K` 做雙胞胎:同一串 picker/setter/
   格式 setter/canvas 呼叫,寫入、韌體呼叫、回傳逐事件相同(31FMT 的雙胞胎方法)。
2. **新格式資料**:S16/OG3.5K/OG4K 的 picker 回傳、時序字、canvas 寫入,對 Jose v0.6.1 的二進位做雙胞胎(差異只能是我們刻意的:
   PARAM → canvas、靜態補丁 → 私有群組、clamp 清除、MOV 守衛)。
3. 交易:所有列兩兩切換(含 crop on/off、MOV、UHD/FHD),每一步斷言「只有 CUR 列的字是開的,其餘原廠」;關機全部原廠。
4. 反灰:每列 × 每格率,清單狀態/上限 = `rate_max`;Crop 灰/生效。
5. 堆疊對齊檢查、兩原點 PIC、claim 衝突 RELEASE、mutation(每個新分支至少一個)。
6. 上機:每格式一段錄影 + DNG 尺寸/格率/BlackLevel;MOV 按錄影;crop 4×/8×;反灰;開機重套;clamp 暗場(`VIDEO_CLAMP_V3.md` §3)。

## 8. 工作量與遷移步驟

| 步 | 內容 | 估計 |
|---|---|---|
| 1 | 階段 A clamp 上機(`VIDEO_CLAMP_V3.md` §3) | 0.5 天 |
| 2 | RE:R1、R2、R3 | 2–3 天 |
| 3 | 計畫改成列(`og3k_plan` 的 TARGETS → 列表),payload 改列驅動,堆疊檢查;只帶 OG3K/OG2K 兩列,雙胞胎證明不退步 | 3–4 天 |
| 4 | `32RESCUS.BIN` 建置 + UI sup 建置(每格式一個 `resolution_qs`);OG3K/OG2K 同卡上機 | 1.5 天(依賴 uishare QS 層與 enums) |
| 5 | 加 S16 列(+ R2 群組)、OG3.5K/OG4K 列;對 Jose 雙胞胎 | 2–2.5 天 |
| 6 | Crop 與反灰 hook | 2 天 |
| 7 | 測試補齊、mutation | 1 天 |
| 8 | 上機(每格式、MOV、crop、反灰、開機、clamp) | 2–3 天 |

合計約 13–17 天。退役:`30OG3K/30OG2K` 在步驟 4 上機通過後由 `32RESCUS.BIN` + `3xOG3K/3xOG2K` UI sup 取代;
31FMT 在步驟 5 通過後退役;AutoRun 卡(v0.2.x)不動。

## 9. 要先決定 / 協調

1. A(核心一檔 + UI 各檔)vs C(全部一檔):C 要 uishare 支援一個 sup 多個 `QS_OPTION` —— 問 uishare 那邊。
2. OG3K 要不要保留 100p(Jose 灰掉;我們有,mode 117)。
3. R1 若證明不了「只改 canvas」,接不接受交易內改 p13/p171 PARAM 格。
4. 跟 Jose 確認可以用他的格式資料(時序、視窗、S16 補丁)並在發布時致謝。

## 10. 骨架實作狀態(2026-10-07,離線;未上機、未寫卡、未 commit)

程式在 `projects/open-gate/build/res-custom/`:

| 檔 | 內容 |
|---|---|
| `ogc_layout.py` | 唯一的數字來源:S(核心狀態)、列 / picker 表項 / 虛擬 mode 的版面、hook 清單;產生 `ogc_layout.h` 給 C 與組語 |
| `ogc_rowdata.py` | 從 `og3k_plan` 取一個格式的資料(鍵、時序、引擎格率、canvas 清單…;每格式一個子行程,因為 og3k_plan 在 import 時讀 OG_TARGET) |
| `ogc_shims.S` | 23 個 hook 的 shim(OG_V3_PAIR:movw/movt 由 `og_pic.py` 改寫成 PC 相對;呼叫 C 前把堆疊對齊 8) |
| `ogc.c` | entry(rl_v3 形狀:claim → veneer → 列開關 → 執行期字 → hook,picker 最後 → restore)與全部邏輯(picker、兩個 setter + MOV 守衛、canvas、名稱、輸出描述、7 個找索引層、放大鏡兩個、開機重套) |
| `build_v3_rescustom.py` | 產出 `32RESCUS.BIN`(核心)+ `31OG3K.BIN`、`31OG2K.BIN`(選單 sup:og_v3.c、只有 uishare `resolution_qs`,另外 claim_res 自己的解析度值)+ build.json;兩原點 PIC 證明 |
| `test_v3_rescustom.py` | 20 項 unicorn 測試(真 loader + LOADER.BIN + 三個 sup) |

**架構與現在的 30OG3K/30OG2K 的差異(都是刻意的)**

- picker 表項回傳**虛擬 profile id**(OG3K 88、OG2K 89;mapping 空槽、`FUN_c043a1c8` 類別 0)與**虛擬 mode id**(230 起:OG3K 的 98/117 各一、OG2K 的 139 一個)。
- **不寫任何韌體表**:時序寫進我們的虛擬 mode 時序列(picker 命中時),clamp 在虛擬 mode 的接收器列上恆開,預覽高改在 canvas 裡寫
  (`pid ∈ {5,210,227,257,258,259}` 且 OG 生效時),mapping 不寫(`C043A18C` 的 BL 給底列)。測試 `test_no_firmware_table_changes`
  對時序/metadata/接收器/暫存器/mapping/預覽 profile/尺寸表逐位元組比對原廠。
- 4 個快門角度 hook 拿掉:虛擬 mode 的 metadata `+0x40` 直接是選中格率的整數格率(原廠影片模式本來就這樣),`FUN_c032c750` 的所有使用者都看到正確值。
- og3kpbsel 拿掉(它的 ENT 一直是 0,從不介入)。
- 一個核心多列:選單 sup 在場的列才「開」(entry 用 `holder(UIS_RES_ENUM_BASE + 值)` 判斷;核心檔名排在選單 sup 之後)。一列都沒開 → RELEASE、什麼都沒寫。
- 核心另外 claim 三個 donor 時序記錄(98/117/139 的 `+4..+0xB`,EXCL、**只登記不寫**),用來跟仍會寫它們的舊 OG 核心、31FMT、res-lab 互斥(並修復它們留下的殘值)。

**驗證(離線)**:`test_v3_rescustom` 20 項全過,其中 `test_same_timing_and_canvas_as_todays_opengate` 對 OG3K、OG2K 每個鍵 × 三種位元深度,
比對今天的 30OG3K/30OG2K 與新核心:時序字、引擎格率、canvas hook 輸出的整個 0x108 bytes canvas **逐位元組相同**(profile id 不同是設計)。
既有的 `test_v3_og`、`test_v3_reslab` 不受影響(沒有改共用檔)。

**還沒做**:S16 / OG3.5K / OG4K 列;Crop Mode 與格率反灰 hook;選單 sup 與 uishare QS 層的實機行為;上機。

## 11. 第一次上機:OG3K 錄影花屏(2026-10-07)與修正

**現象**(協調者轉述):32RESCUS + 31OG3K + 31OG2K 全部 LOADED、兩列開;OG3K 錄 A001_017,鏡頭蓋蓋著,第一格 3024×2010 12-bit
卻是滿版條紋,右側約 14% 欄全 0。舊核心同條件乾淨(251..260)。

**分類:(a) 核心邏輯錯,不是 OG3K 那一列的資料。**
虛擬 mode 的攔截漏了**第八張 per-mode 表**:描述子 `+0x10`(實機位址 `0xC0B5B918`,`FRAME_RATE_IS_VMAX.md` 的實機讀值)是
`{值, mode}` 8 bytes 一筆、**mode 在 +4**,由 `FUN_c031ffa0` 掃描並**回傳值**(不是索引)。`FUN_c0320008`(設定模式路徑,算讀出
窗/格式)拿它當第一個參數。我們的 vid 在這張表裡找不到 → 原廠回第 0 筆(mode 0 的值 **2**),而 mode 98 是 **6**
→ 讀出格式錯 → 花屏與右側空白。§3.2.1 的七個找索引函式是以「`row[0] == mode` 的表」搜出來的,這張的 mode 在 +4,所以漏掉。
離線測試也沒抓到:測試用的描述子是自己造的,`+0x10` 是 0,而且只比了時序與 canvas,沒比整串感光元件程式化。

**修正(核心)**
1. 第八個攔截層 `lk_r10`:`FUN_c031ffa0` 入口,vid → 回 donor 那一筆的值(fill 時從描述子 `+0x10` 依 +4 找 donor 抄下)。
2. 核心不再自己加差異:metadata `+0x40` 不再被改(恢復今天核心的做法:四個快門角度 BL hook 回傳選中格率);
   video clamp 改成**列資料**(`clamp: 1`),核心只在列要求時才設。→ 「什麼都不要求的列 = donor 原樣」。
3. 測試用的描述子改成實機的表位址(`+0x10/+0x24/+0x40/+0x48`;`+0xF4` 用映像裡緊接的 `0xC0B5DB00`;只有放大鏡 `+0x128` 仍是合成的)。

**新測試(`ProgrammingTests`)**:在乾淨的相機裡實跑設定模式路徑上所有跑得完的 per-mode 讀取者 —— 八個查表(列/值)、
快取索引的讀取者(`FUN_c0320740/c03208b0/c0320818`)、暫存器寫入器 `FUN_c03258c8`(每一個感光元件暫存器寫入)、
幀週期 —— 外加它們做的每一筆韌體記憶體寫入(硬體頁按需映射)。
- **核心自證**:列不要求任何東西(clamp 0、不 pick)時,vid 98/117/139 的整串結果與原廠直接用 98/117/139 **逐字相同**(165 筆暫存器寫入、151 筆記憶體寫入)。
- **對今天的核心**:OG3K30/OG3K24/OG3K100/OG2K60,新核心與今天的 30OG3K/30OG2K(含 clamp)**逐字相同**。
- 沒納入的(在模擬裡跑不完,需要作業系統環境):`FUN_c0320008`、`FUN_c0320ab0→c032d5e0` 本身 —— 改比它們的輸入
  (`FUN_c031ffa0` 的值、時序列、接收器列),全部逐字相同。`FUN_c032c750` 也跑不完,改比 metadata 列。

## 12. 格式選擇只存在 res-custom 自己的 BIN;相機設定區只存原廠值(設計,2026-10-07,未實作)

使用者決定:選了哪個格式**只記在 `32RESCUS.BIN` 的 +32 設定區**(照 raw-view / lossless 寫回自己檔案的做法);
相機設定區永遠只有原廠值 UHD 3 / FHD 2(每格式的 `stock_value`:OG3K、OG2K、S16 → FHD;OG4K、OG3.5K → UHD);
`OGSAVE`(`XC_CommonSaveData 0xC30754CC`)不再使用。= `fpSup/uishare/QS_SHARE.md` §12.10「240 做法 1」+「變數存 BIN」。

### 12.1 變數在哪

| 變數 | 位置 | 壽命 |
|---|---|---|
| **H_SEL**:目前在選單上選的是哪個格式(選單 sup 的檔名,0 = 原廠列) | uishare(字串層/QS 層標頭,RAM) | 一次開機;**唯一的權威** |
| `SEL`:H_SEL 對到的列 + 1(0 = 無) | res-custom 的 S(由 H_SEL 推出,不另存權威) | 一次開機 |
| `FLAG/CUR`:錄影核心是否生效 | S | 一次開機 |
| 存檔紀錄 `{'RCS1', 格式標籤 8 B, stock_value, 版本, 校驗}` 32 B | **`32RESCUS.BIN` 檔案 +32**(塊裡也有一份,開機時就讀進來了) | 跨電源循環 |
| `DIRTY`:塊裡紀錄 ≠ 目前 SEL | S | 一次開機 |

紀錄存**格式標籤**(`OG3K`),不存列號或 enum —— 卡上組合變了(列順序、少了某個選單 sup)也對得起來。

### 12.2 錄影核心改讀變數(取代 enum 比對)

`生效 = SEL 列存在且開著 && 目前解析度設定值 == 該列的 stock_value && 錄影格式是 CinemaDNG`。

- 解析度 setter hook(`C005C020`)看到的永遠是 2/3,它只記下「目前設定值」,再重算生效;**不再看 enum、不再寫 OGSAVE**。
- 格式 setter(`C005BE58`)同前(MOV 守衛)。
- 重算點:兩個 setter hook、picker hook(錄影/LV 組態一定經過它)、以及 uishare 的 H_SEL 改變通知(§12.5 介面 3)。
  H_SEL 與 setter 誰先跑都可以:條件是「位準」不是「事件」。
- 選原廠 UHD/FHD 列:uishare 把 H_SEL 設 0 → SEL 0 → 不生效、`DIRTY`。注意 **FHD 列和 OG3K 列的設定值同是 2**,
  所以核心**不能**用設定值分辨,只能靠 H_SEL —— 這是 uishare 必須提供 H_SEL 的原因。
- picker、canvas、名稱、輸出、aspect、虛擬 mode/profile:全部照舊,只看 FLAG/CUR。

### 12.3 開機

entry(所有 hook 掛好之後,取代現在的 og3krestore):
1. 讀塊裡的 +32 紀錄(檔案本來就整個在塊裡,不用開檔)。magic/校驗不對 → 當作沒有。
2. 標籤對到一個**開著**的列;**目前解析度設定值 == 該列 stock_value**;錄影格式是 CinemaDNG;不在錄影(沿用 og3krestore 的三個訊號)。
   - 任一不成立 → **不套用**(SEL 0)。設定值不符代表沒插卡時使用者改過,照 raw-view 的規則尊重它;紀錄留著不動(下次選擇時才覆寫)。
3. 成立 → 呼叫 uishare `uis_sel_set(那列的選單 sup 檔名)`(游標/摘要/QS 停到我們那列,**不呼叫原廠 setter**,設定值本來就是 stock_value)
   → 重算生效 → FLAG=1 → MovSigProcess 停/啟(og3krestore 的 `lvreload`,不改)。
- 讀「目前解析度設定值」的原廠 getter:Jose 的位元組用 `C005C058(0xC31CAA80)`(他的 regsel/regfrmax 都這樣讀)—— **待 RE 確認**(0.25 天)。

### 12.4 寫 BIN 的時機

- SEL 改變(選了別的格式、選回原廠列、卡上那列消失)→ `DIRTY = 1`,**當下不寫**(UI 執行緒,可能正要錄影)。
- 寫在**關機存檔的 CHAIN 點 `C0088C60`**(raw-view 已掛在這,res-lab 也是;CHAIN 共用):先呼叫下一層,再看 `DIRTY` 且不在錄影
  → open mode 7(不截斷)→ seek 32 → 寫 32 B → seek 32 → 讀回比對;seek 失敗不寫;沒寫成就留 `DIRTY`(下次 `menu save`/關機再寫)。
  寫成 → `DIRTY = 0`。檔案其餘位元組不變。
- ⚠ 撥電源開關時 SD 是否仍可寫:raw-view 同一點**也還沒上機驗證**。備案 = lossless 的方式(自己的任務閒置時寫);res-custom 目前沒有任務,
  若關機點不行,改用「下一次 LV 重建且不在錄影」時寫(canvas hook 在 LV 重建時一定會跑,但要把寫檔移出 hook 執行緒 —— 需要一個任務,+0.5 天)。
- 拔電池/當機:沒寫成就是上一次的紀錄;設定區本來就只有原廠值,所以最壞是開機回到原廠 FHD/UHD 或上一次的格式。

### 12.5 分工:uishare(另一個代理)要提供的介面

1. **`resolution_qs(..., stock_value=2|3)`**:轉換表裡每個選單 sup 的列用 stock_value(不是 4/7/…);同值的對子依 H_SEL 重排,
   讓游標、收合摘要、QS 圖磚停在使用者選的那列(§12.10)。`ui/enums.py` 改成登記 stock_value(OG3K/OG2K/S16 → 2,OG4K/OG3.5K → 3)。
2. **setter 回呼層**(Settings 與 QS 兩條提交路徑,位址待 uishare RE,240 那邊是 `FUN_c057a6f8`/`FUN_c05821b8`):提交列 k →
   H_SEL = 列 k 的選單 sup 檔名(原廠列 → 0)。
3. **執行期 API**(res-custom 在 entry 時經 `holder(UIS_RES_QSCUR,0)` 找到發號者那層,存下指標;之後任何時候可用):
   - `uis_sel_get(char out[8])` 或直接給 **H_SEL 8 B + 改變計數 4 B 的穩定位址**(res-custom 在重算點讀);
   - `uis_sel_set(const char name[8])`:開機還原用,只動 H_SEL 與游標/摘要,不呼叫原廠 setter;
   - (可選)`uis_sel_watch(fn)`:H_SEL 改變時呼叫 —— 沒有也行,res-custom 在 picker/setter 重算就夠(位準)。
4. **不要**由 uishare 存 H_SEL 到發號者 BIN(§12.3 舊案):格式選擇的持久化歸 res-custom。若其他非 res-custom 的格式 sup 也要持久化,另議。

### 12.6 res-custom 這邊要做的

| 項目 | 估計 |
|---|---|
| RE:目前解析度設定值的 getter(`C005C058(0xC31CAA80)` 確認)、`C0088C60` 的呼叫慣例(照 raw-view) | 0.5 天 |
| S 加 SEL/DIRTY/設定值;列加 stock_value;setter/picker 重算改讀 H_SEL;拿掉 OGSAVE 與 enum 比對 | 0.5 天 |
| +32 紀錄、關機點 CHAIN 寫 BIN(open 7/seek/寫/讀回/重試),開機讀回與套用規則 | 1 天 |
| 測試:選格式→設定值 = stock_value;FHD 列與 OG3K 列同值時以 H_SEL 區分;開機設定值不符不套用;寫 BIN 讀回、seek 失敗不寫、沒變不寫;第一守則斷言(下) | 1 天 |
| 上機(與 uishare 一起) | 0.5–1 天 |
| **合計 res-custom 側** | **約 3.5–4 天**(uishare 側另計,QS_SHARE §12.7 估約 3 天) |

### 12.7 第一守則的證明

1. **設定區只會收到 2/3**:選單與 QS 經轉換表把我們的列換成 stock_value 才交給原廠 setter;res-custom 自己**從不呼叫** `SET_RES`
   (開機還原只設 H_SEL,不設值)—— 程式裡不再有呼叫原廠 setter 的路徑(grep + 測試斷言 SET_RES 呼叫次數 0)。
2. **XC_UserSetting 寬高**:原廠 setter 只拿到 2/3,它重算出的就是原廠 1920×1080 / 3840×2160;res-custom 不碰 `0xC074222C`(現在也沒碰)。
   測試:選 OG3K 前後讀 `0xC3074BE8`/`+4`,等於原廠表的 FHD 值。
3. **CommonSaveData**:不再寫 OGSAVE。測試:所有情境(選格式、換 MOV、選回 FHD/UHD、關機存檔、開機還原)下,
   `0xC307523C..+0x410` 與 `0xC3074BE8..+0x5E4` 只出現原廠 setter 自己的寫入(unicorn 記憶體寫入追蹤,res-custom 的程式範圍內零筆)。
4. **claims**:res-custom 不 claim 任何設定區位址(測試對 claims 清單斷言)。
5. **剩下靠上機的**:拔卡開機後解析度是 FHD/UHD、相機正常;Crop Mode 等其他設定不受影響。

## 13. 解析度 UI 也歸 res-custom(QS 方案 B);uishare 只用通用部分(設計,2026-10-07,未實作)

使用者決定:QS 大圖磚、底列、選擇、游標/摘要,以及 §12 的「選擇存 res-custom BIN、設定區只存原廠值」,**統一由 res-custom 做**,
不再用 uishare 的 QS 共用層(`qs_layer`)。QS 用**方案 B**:每個格式在大圖磚上有自己的狀態(時間 t ≈ 33·k,k = 列號)與**固定圖名**,
不共用 t=66 + 動態圖名,也不靠「每次切換重新解析」—— 後者正是「圖慢一步」與開機疊字雜訊的根因(圖名在版面解析時就定、
放進快取後沒人重載;QS_SHARE.md §4.1 上機訂正)。本節**取代 §12.5**(那份 uishare 介面清單作廢,H_SEL 改成 res-custom 自己的變數)。

### 13.1 誰做什麼

| 部分 | 歸屬 | 說明 |
|---|---|---|
| 字串(格式名、摘要、底列文字) | **uishare 通用**:巢狀字串層(`C05E5B58/61C8/61E0`,SHARED_UI) | 照現在 |
| Settings 清單多一列(CSV_ADD、列文字) | **uishare 通用**:FPUI / `uia_apply` 的 CSV 列 | 照現在;列值改成 stock_value(§13.3) |
| QS 記錄(大圖磚各格式狀態、底列、游標、QS max、Settings popup 位移與每列摘要) | **res-custom**:`C05E6400` 記錄層 | 方案 B 配方由建置期產生(§13.4) |
| 私有圖檔 pack 登記 | **res-custom**:`C05E84D8` | 照 OG 的 `ensure_ui_pack`(每個 resource context 一次) |
| 開機時 QS 版面重新解析一次 | **res-custom**:`C05D90F0` | 只在開機一次(不是每次切換);用 QS_SHARE §4.1 已坐實的 `RCACHE_V3` 語意(r0 = 快取物件、參考數 1、**不在載入 X 的過程中放掉 X**)—— 避開 v5c 的凍結 |
| 列 ↔ 設定值轉換表 | **res-custom**:改指 `C06BDA3C/40/48` 到自己的表(EXCL) | 每列的值 = stock_value;同值的對子依 SEL 重排(§12.10 的做法) |
| 「選了哪列」 | **res-custom**:Settings 與 QS 兩條提交路徑的 setter 回呼(位址待 RE;240 那邊是 `FUN_c057a6f8`/`FUN_c05821b8`) | 寫 S.SEL(取代 H_SEL);§12 的生效條件改讀 SEL |
| 選擇持久化 | **res-custom**:BIN +32(§12.3/12.4 不變) | |

uishare 這邊**不需要再做**:`resolution_qs` 的 QS_OPTION、QS 層、共用轉換表、H_SEL。

### 13.2 方案 B 的記錄改法

- 大圖磚(QS_CINE / QS_STILLlike / QS_Common 的 315 筆 kind 1 + 36 筆 kind 2,與 FP3K/OG 的同一批):
  每個格式 k(k = 2..N−1,N = 原廠 2 列 + 格式數)插一個狀態影格 `t = 33·k`(原廠 0、33 已用),圖名 = 該格式自己的固定圖
  (`<格式>_QS / _SET / _FONT`,放在 res-custom 的私有 pack);狀態曲線終點 `max(end, 33·(N−1))`。
  → 圖名永遠固定,切換只是換狀態,不需要重解析;開機重解析一次(把 hook 掛上前已解析的那份放掉)後就一直正確。
- N 相關欄位(QS max = N−1、游標 clip、底列 x 起點/影格數/終點、Settings popup 位移、每列摘要):沿用 QS_SHARE §3 的表;
  **已實測只有 N = 3(OG)與 N = 8(Jose)**。五格式 = N 7,屬推測值 → 上機逐項看。
- 記錄緩衝:每筆多 (N−2) 個影格;建置時對「原廠最大記錄 + N 最大時的增量」證明複本緩衝夠(OG 512 B、Jose 1 KiB 上機跑過)。
- 配方來源:`fpSup/uishare/gen_qs_recipe.py` 的 FP3K 315/36 筆與 Jose 的底列/N=8 值(uishare 代理會把它查到的時間軸、影格與 N 相關資料
  寫進 QS_SHARE.md 交過來);res-custom 的產生器把 kind 1 的「插 t=66」推廣成「插 t=33·k(每格式一個)」。
- 實作:把 `og3k_ui.S` 的 `ui_record`(二分搜尋 `{記錄位址, meta, FNV}`、五種 kind、複本)移植成 res-custom 的 C(與 ogc.c 同一個 unit),
  配方表放在塊裡;`C05E6400` 掛 CHAIN 層(不是我們的記錄 → 往下)。

### 13.3 選擇、轉換表、設定值

- 轉換表(res-custom 自己的):`{UHD 3 → 列 0, FHD 2 → 列 1, 每個格式 stock_value → 列 k}`;**同值的對子把目前 SEL 的那列排在最前**,
  所以設定值 2 時游標/摘要/QS 狀態停在 SEL 那列(SEL = 0 時停在原廠 FHD)。
- 兩個提交回呼:提交列 k → SEL = k 是格式列 ? k : 0;設定值照原廠流程變成 2/3(轉換表給的)。之後 §12.2 的生效條件照算。
- 開機(§12.3):紀錄的格式 + 設定值 == stock_value → SEL = 那列、對子重排(游標/摘要/QS 直接正確,不呼叫 setter)。

### 13.4 選單 sup 還要分檔嗎 —— 建議併回核心(請使用者決定)

UI 改歸 res-custom 之後,`31OG3K/31OG2K` 只剩「一列 CSV + 幾個字串 + 一個 pack」,而 N 相關欄位、配方、轉換表都要看「這張卡一共幾個格式」:

| | A 併回核心:一個 `32RESCUS.BIN`,建置時選格式(建議) | B 維持分檔 |
|---|---|---|
| N 怎麼知道 | 建置時就知道,配方一次產生、建置期驗證 | 核心 entry 時數 holder,配方要在執行期依 N 套 |
| 使用者加格式 | Merge 頁重建 res-custom(勾格式) | 放一個檔 |
| 測試 | 每個組合都是建置產物,可逐位元組驗 | 組合在執行期才決定,要模擬所有組合 |
| 檔案數 / claim | 1 個檔 | 1 + 格式數 |
| 列開關、檔名排序依賴 | 不需要 | 需要(核心要排在選單 sup 之後) |

→ 建議 A。分檔的唯一好處(丟一個檔就多一格式)在 N 相關欄位沒有通用解之前反而是風險(N=4..7 都是推測值)。

### 13.5 工作量

| 項目 | 估計 |
|---|---|
| RE:`MV_MovRecSize` 兩個提交回呼、Settings 每列摘要的狀態表 | 1 天 |
| 記錄層移植成 C + 方案 B 配方產生器(t=33·k、N 相關欄位、緩衝證明) | 3 天 |
| 轉換表 + 對子重排 + 提交回呼 + SEL(取代 H_SEL / enum) | 1 天 |
| pack 登記 + 開機一次重解析(正確的 RCACHE 語意) | 1.5 天 |
| 選擇存 BIN(§12.4) | 1.5 天 |
| 併回核心(FPUI 只剩 CSV 列與字串,隨建置格式產生)+ 建置 | 1 天 |
| 測試:配方對 FP3K(N=3)/Jose(N=8)參考位元組、每格式狀態與圖名、對子重排、開機套用規則、第一守則(§12.7) | 2 天 |
| 上機(N=7 的推測值逐項確認、開機無疊字、切換即時) | 2 天 |
| **合計** | **約 13 天** |

前提:§11 的錄影核心照現在(虛擬 mode/profile);S16/OG3.5K/OG4K 的列可以和這些並行。

## 14. 格式資料檔:每格式一個檔,只有參數、沒有程式(設計,2026-10-07,未實作)

使用者決定:選單 sup 維持**每格式一個檔**,但檔裡**只有該格式的參數資料**(選單文字、圖、pack、時序/虛擬 mode/profile 參數、
stock_value…),不帶程式、不掛 hook;**所有程式**(QS/選單/選擇/錄影)都在 res-custom 核心。本節取代 §13.4 的「併回核心」建議,
並更新 uishare 移交(QS_SHARE.md §13):時間軸 `t_k = ⌊100k/3⌋`、371 筆的規則、N ≤ 8、開機只需一次 v3+v2 —— 照 §13.2 實作,
資料改從資料檔來。

### 14.1 核心怎麼找到資料 —— 自己讀檔,**不動 sloader**

加載器的服務表沒有「找到別的 sup 的塊」(`holder` 只給路徑),而資料檔沒有程式、不能自己登記。所以**核心在 entry 自己讀**:

- 位置:`\fpSup\RESCUS\` 子資料夾(加載器只看 `\fpSup\*.BIN`、跳過子資料夾,所以資料檔不會被當成 sup、不佔 32 個 sup 名額、
  不在 LOAD.LOG 留 SKIP 行)。檔名 = 格式標籤,8.3:`OG3K.RCD`、`OG2K.RCD`、`S16.RCD`、`OG35K.RCD`、`OG4K.RCD`。
- 讀法:目錄列舉 `C0366918/C0366990/C03669F8/C0366940`(DIR_ENUM_API.md,上機驗過,跳過 `._*`)+ 檔案 API
  `C0365E90/C0365FB0/C0366060/C0366020/C0365ED0`(加載器自己用的同一組),讀進**核心塊尾端預留的資料區**(例如 128 KiB,
  block_size 預留;不用配置器)。依檔名排序(與加載器同規則),所以結果與目錄寫入順序無關。
- 時機:entry 一開始(claim 之前就讀完、驗完;任何失敗都還沒寫東西)。Fast Start 3 的暖開機同樣走 entry,不受影響。
- **載入順序要求:沒有**(資料檔不是 sup)。核心的檔名前綴只影響它與其他 sup 的 hook 疊層順序,照 LOADER_V3 的建議即可。
- 若之後要加載器代勞(例如服務「讀子資料夾的檔」或「依 sup_id 找塊」),那是 sloader 的改動,**目前不需要**;要做會先回報。

### 14.2 資料檔格式 `RCD1`(全部 little-endian)

```
標頭 64 B
  +0x00 'RCD1'      +0x04 版本(欄位佈局)    +0x08 標頭長 64    +0x0C 檔長
  +0x10 FNV-1a(+0x40 到檔尾)                 +0x14 段數 n       +0x18 段表位移
  +0x1C stock_value(2 FHD / 3 UHD)          +0x20 aspect(2 = 3:2,3 = 16:9,9 = 2:1 / MINCORE>=2)
  +0x24 旗標(bit0 clamp、bit1 Crop 可用 …)   +0x28 base profile 號(例 83;核心自己查 mapping 得底列)
  +0x2C 最低核心版本                          +0x30 標籤 8 B('OG3K')   +0x38 保留
段表:n 個 {型別, 位移, 長度}(位移/長度都在檔內)
段型別(未知的「必要」型別 → 整個格式不開;「選用」型別 → 略過)
  1 ENTRIES   picker 表項:{鍵後綴 16 B, vmode 序號, w0, w1, engfps, nominal}…
  2 VMODES    每個虛擬 mode:{donor id, 覆寫筆數, 覆寫 {表種類, 位移, 值}…}
                (表種類 = 時序/metadata/+0x24/接收器/+0x48/+0xF4/暫存器/+0x10 值/放大鏡;S16 的 161 個暫存器與
                 2112×1250 metadata 就是一串覆寫;clamp 也可寫成覆寫 —— 核心只套覆寫,不自己加任何差異,§11 的「自證」照樣成立)
  3 CANVAS    錄影 / 回放 / 待機三張 {位移, 值} 清單、prev_h、DNG 有效尺寸(放大名稱判斷用)
  4 UI        Settings 列文字、收合摘要、底列文字、QS 三張圖名、Settings popup 文字
  5 PACK      私有 NBR pack(該格式的 QS/SET/FONT 圖與缺的 font_S_imageSize_*)
  6 ZOOM      (選用)放大鏡列覆寫
```

### 14.3 核心的處理(取代 §1.3 的建置期 S 與 §10 的列開關)

1. 列舉 `\fpSup\RESCUS\*.RCD`,依名排序,每個檔驗:magic、版本 ∈ 核心支援範圍、`最低核心版本 ≤ 核心`、檔長、FNV、每段界限
   (位移/長度在檔內、清單有結尾、canvas 位移 < 0x108 且 4 對齊、覆寫位移 < 該表步距、暫存器覆寫只在 0x288 內、鍵 ≤ 15 字、
   stock_value ∈ {2,3}、標籤只含英數)。
2. 通過的依名次成為列 0..k(N = 2 + k);**k 上限 6**(N ≤ 8,沒有 Cursor8 —— QS_SHARE §13.3),多出來的不開、記 log。
3. 由資料填 S(列、表項、虛擬 mode、canvas 清單、UI 配方的 N 與每列圖名),**與今天建置期產生的 S 逐位元組相同**(測試的基準)。
4. 一個都沒有 → RELEASE(什麼都沒寫)。

| 情況 | 處理 |
|---|---|
| 資料夾不存在 / 沒有 .RCD | RELEASE,log `RC` + 0 |
| 某檔 magic/FNV/界限錯 | 只略過那個格式,log `RC` + 檔名 + 原因;其他照開 |
| 版本比核心新(核心不認得的必要段/欄位) | 略過那個格式(log `RV`);不嘗試猜 |
| 版本比核心舊 | 核心支援的範圍內照讀;範圍外略過 |
| 兩檔同標籤 | 名次在前的開,後者略過(log) |
| 超過 6 個 | 名次前 6 個開 |
| BIN +32 紀錄的格式這次沒開 | 當作沒有紀錄(§12.3:不套用,設定值本來就是原廠值) |

### 14.4 工作量(在 §13.5 約 13 天之上的增減)

| 項目 | 估計 |
|---|---|
| 資料檔建置器(由 `ogc_rowdata` + UI 資產產生 `.RCD`)與格式規格 | 1.5 天 |
| 核心:讀目錄與檔、驗證、由資料填 S(取代建置期 blob) | 2 天 |
| 測試:由 `.RCD` 填出的 S = 今天建置期的 S(逐位元組);壞檔/新版本/同標籤/超量/缺資料夾;mutation | 1.5 天 |
| 減:§13.5 的「併回核心」 | −1 天 |
| **合計** | **約 17 天**(含上機 2 天) |

不需要 sloader 改動。Merge 頁要能把 `.RCD` 放進 `\fpSup\RESCUS\`(Merge 頁維護者的工作,另計)。

## 15. 實作進度(2026-10-07 起;離線,未上機,未 commit)

### 里程碑 1:RE(完成,[驗] 反編譯 + 映像)

| 要的東西 | 結果 |
|---|---|
| Settings 的解析度提交回呼 | `FUN_c057a6a0`(以 `"MV_Resolution"` 登記,`blk_c05.c:90861/90878`):`[r0+8]` = 提交的列 → `FUN_c06bd9e0`(列→值)→ `vtbl+0x13C(值, 0)` |
| Quick Set 的提交回呼 | `FUN_c05824d0`(`blk_c05.c:95499/95586`;FP3K 掛過的「QS 選擇」點):同上,最後參數 1 |
| 兩者的序言 | `push {r4,r5,r6,r7,lr}`(可 replay,CHAIN) |
| 列 ↔ 值轉換表 | `MenuValueConverterBase::v21`(`C06BDA30`):`movw/movt r2`(`C06BDA3C/40`)= `{值, 列}` 表、`mov r2,#n`(`C06BDA48`)= 筆數;兩個方向都讀它(列→值 `FUN_c06cf5d8`) |
| 目前解析度設定值的 getter | `FUN_c005c058(GET_OBJ())`(與錄影格式 getter `FUN_c005be90` 同形:`+0x1A0` vs `+0x194`;Jose 也用它) |
| 寫回自己檔案的 API | raw-view 的同一組:`F_CTOR/F_OPEN(mode 7)/F_SEEK C03661E0/F_WRITE/F_READ/F_CLOSE/F_DTOR` |

### 里程碑 2:§12 選擇存 BIN + 錄影核心改讀變數(完成,離線)

- S 加 `SEL / RESVAL / DIRTY / PATH / CFG / FOBJ / PAIRS / PAIRN`;列加 `STOCK / MROW`;拿掉 enum 比對、`LAST_ENUM`、OGSAVE。
- 新 hook:兩個提交回呼(`cmt_set`/`cmt_qs`,記 SEL、重排對子、標 DIRTY)、關機存檔呼叫點 `C0088C60`(`save`)。
- 轉換表:entry 把 `C06BDA3C/40/48` 改指到 `S.PAIRS`(EXCL、claim only、關機寫回);對子 `(3,0),(2,1),(stock,列)…`,選中的那列排最前。
- 生效 = SEL 那列開著 && 設定值 == 該列 stock_value && CinemaDNG;設定值被任何路徑改成別的值 → SEL 清 0。
- 開機:讀塊裡 +32 的紀錄(`RCS1`,0x60 B,版本 1、標籤、stock、啟用清單位置已預留、FNV);設定值與 stock 不符/格式不對/錄影中 → 不套用;
  套用時**不呼叫原廠 setter**。
- 寫 BIN:`DIRTY` 且不在錄影時,在關機存檔點寫 +32 的 0x60 B(open 7 → seek → 寫 → seek → 讀回比對),失敗留 DIRTY。
- 檔案佈局:`[FSB1 32][設定區 0x60][程式…]`;塊尾多 0x1000 B 給檔案物件。
- ⚠ 選單 sup(31OG3K/31OG2K)不再 claim QS 位置;但它們的 `resolution_qs` 區塊在**相機上**仍會由 `qs_install` claim 轉換表 → 與核心衝突。
  所以這一版**只能離線**;上機要等 §13/§14 把選單 sup 換成資料檔、UI 進核心。
- 測試 `test_v3_rescustom` 26 項全過:提交回呼與對子順序(含「FHD 列與 OG3K 列同值 2,只靠提交分辨」)、轉換器實際回傳我們的表、
  開機套用規則(6 種情況)、寫 BIN(內容、其餘位元組不變、沒變不寫、seek 失敗不寫、錄影中不寫、下次開機讀回)、
  第一守則(XC_UserSetting/CommonSaveData 範圍零寫入、claims 不含設定區、OGSAVE 金絲雀不變、開機不呼叫 setter)、
  以及原有的程式化序列自證與對今天核心的逐字比對。

### 里程碑 3 + 4:§14 資料檔 + §13 UI/QS 方案 B 進核心(完成,離線;待上機)

**卡上長這樣**(選單 sup `31OG3K/31OG2K.BIN` 不再存在,卡上要刪掉):

```
\fpSup\32RESCUS.BIN          核心:全部程式
\fpSup\RESCUS\OG2K.RCD       每格式一個資料檔,只有參數(4–6 KB,含私有圖 pack)
\fpSup\RESCUS\OG3K.RCD
```

- **資料檔 `RCD1`**(`res-custom/rcd.py` = 規格 + Python 參考檢查器):標頭 64 B(§14.2 原樣,另加 `+0x38` 舊 enum 只作識別)、
  段表 `{型別, 位移, 長度, 旗標 bit0=必要}`;段:ENTRIES(每筆 40 B:鍵 16、donor、w0、w1、engfps、nominal)、
  VMODES(選用;覆寫 `{donor, 表種類, 位移, 值}`,種類 0–6 七張表、7 = +0x10 值、8 = 放大鏡列)、CANVAS(prev_h、DNG 有效寬高、錄影/回放兩串)、
  UI(列文字 32 B、摘要 16 B)、PACK(64 對齊的 NBR)。**檔裡沒有任何程式**:FV handler、uia_apply、QS 層都在核心。
- **核心讀檔**(entry 第一步,claim 之前、只寫自己的塊):路徑 = 自己的路徑把檔名換成 `RESCUS`;目錄 API 列出 `*.RCD`(略過子資料夾、隱藏、`._*`、
  非 .RCD、超過 12 字元的名字),依名排序,最多看 16 個;逐檔讀進塊尾資料區(160 KiB,64 對齊),驗證與 `rcd.decode` 同序同理由;
  同標籤 → 後者略過;啟用清單(BIN +32 的 `NEN/EN`,有效且非空才用)否則前 6 個;再由資料填 S(與 `ogc_layout.state_blob` 逐位元組相同)。
  一個都沒有 → RELEASE(什麼都沒寫)。診斷:`S.RCD_FOUND/OK/BAD/WHY`、`S.RCD_WHYS[16]`(每個名字的結果),LOAD.LOG 一行 `OCD ffookkww`。
- **第六頁介面(只定義)**:`S.NAVAIL` + `S.AVAIL[16]` = 卡上所有有效格式的標籤(依檔名);`S.ENABLE_FN` = `ogc_enable_set(S, n, labels)`
  寫 BIN 紀錄的啟用清單(n ≤ 6,0 = 預設),標 DIRTY → 下次關機存檔寫入 → **重開機生效**。
- **選單(§13.1 的 uishare 通用部分)**:核心連結 uishare 的 `uia_apply`(build_section.unity),用核心內的**模板**(`rcd.ui_template()`:
  `resolution_qs` 的 Settings 部分 —— CSV 一列、B2_5 的 List max / 摘要 / popup 位移 / _excl,**沒有 QS_OPTION**),
  執行期把 `@R`(列文字)`@S`(摘要)`@L`(標籤)換成資料檔的字、三個圖名 `<標籤>_QS/_SET/_FONT` 用 STRBASE 把字串 id 寫進該列 `ROW.QSID`,
  逐列呼叫 `uia_apply`;成功 → 列開、`MROW` = 它拿到的 CSV 列號。某列失敗只關那列;全部失敗 → RELEASE。
- **QS 方案 B(核心自己的三層)**:`C05E6400` 記錄層、`C05D90F0` 版面層、`C05E84D8` pack 層,Thumb B.W → Thumb veneer → ARM shim,
  claim 用 CHAIN(與舊 uishare QS sup 互斥是刻意的)。配方表 = uishare `ui/qs.py encode()`(371 筆)原樣嵌進核心;
  每列 k 的狀態影格在 `⌊100k/3⌋`、依 k 遞增插入(兩個 1 KiB 緩衝交替)、圖 id 是該列自己的;end = max(原值, t(N−1));
  qs_max/cursor/footer_n8 依 N(配方 f(N));footer_label 只寫有那一列的格。N 在第一筆記錄時從 FV 表的 CSV 複本數(uishare `qs_rows_now` 同法)。
  N 不在配方支援範圍(3..8)→ QS 全部不動。只在原廠記錄上改(別人的複本 → 往下)。
  pack:每列的 pack 在每個 resource context 註冊一次(stock NBR 載入後、或第一筆記錄時);註冊失敗的那列不加 QS 狀態。
  開機一次重解析:entry 記下快取當時握著的 QS 版面;之後第一次「別的版面」載入**完成後**、且快取放得掉時,`v3(cache)` 再 `v2(cache)`,
  只做一次、防重入;快取原本是空的就不做。
- **其他改動**:虛擬 profile 起點 88 → **74**(6 列要 6 個連續空的 mapping 槽:74..79);虛擬 mode 上限 8 → 16(`S.VMDONOR` 移到 +0x240);
  donor 的時序紀錄 claim 改在 entry 依資料做(stock 位元組由建置期嵌入的 70 筆表給)。
- **測試**(`test_v3_rescustom`,40 項全過;Unicorn 跑真的加載器 + 核心;uia_apply、v2/v3、各層之下為 stub):
  S 由檔填出 = 參考逐位元組(2 格式、6 格式含覆寫);壞檔/新版本/最低核心版本/未知必要段(選用段照收)/同標籤/超過 6 個/沒有資料夾/
  隱藏與 `._`;**差異測試**:約 190 個逐欄位損壞的檔,核心的每檔判定 = `rcd.decode`;啟用清單;第六頁寫入→存檔→下次開機只開一列;
  每列交給 uia_apply 的區塊 = Python 參考逐位元組、STRBASE id 進 `ROW.QSID`;某列選單失敗;**QS N=3 的 371 筆 = uishare 已上機的配方**(逐位元組);
  N=4、N=8 = `rcd.qs_target` 參考,且狀態時間 = ⌊100k/3⌋;非配方記錄/別人的複本不動;N 從 FV 表數;pack 每 context 一次、失敗的列不加狀態;
  開機重解析的條件與次序(v3 再 v2、在下層之後、只一次)。原有錄影測試(程式化序列自證、對今天 30OG3K/30OG2K 逐字等價等)照過。
- **還沒驗、要上機**:N=4 的 QS 影格與底列(推測值)、開機重解析的 v2 在相機上是否安全、私有 pack 在兩列時都載得到、
  Settings popup 在 N=4 的位移(推測)、資料檔從 `RESCUS\` 讀取(目錄 API 在子資料夾)。

### 里程碑 5:Jose 的 S16 / OG3.5K / OG4K 資料(完成,離線;待上機)

**只有資料,核心一個位元組都沒改**(`32RESCUS.BIN` 與里程碑 3+4 相同,sha256 `03643d32…`)。
- 來源:`res-custom/jose_extract.py` 把 Jose v0.6.1 三包當資料讀(不執行):picker 表項、registry 列、48 格 PARAM、S16 對 mode 121 各表的值補丁。
  結果寫成字面值 `res-custom/jose_formats.py`;測試在 Jose 包存在時逐項比對兩者。
- 換位置不換內容:他寫進原廠 p13/p171 PARAM 的值 → 我們虛擬 profile 的 canvas 對(PARAM 欄位移 = canvas 位移);
  他對 mode 121 的值補丁(META 8、R28 5、R38 8、R68 5、REG 5 個字,**共 31 筆覆寫**,含讀出視窗 TIM +0xC/+0x10;
  不是先前估的 161)→ 虛擬 mode 覆寫;原廠 mode 121 / 3 與原廠 profile 都不動。
- 每格式:S16 = mode 121 + p13 底列,16:9,stock FHD,23.98–59.94(7 筆);OG3.5K / OG4K = mode 3 + p171 底列,3:2,stock UHD,
  23.98–29.97(4 筆),預覽高 1334;三者都開 clamp。檔名排序 → 清單順序 OG2K、OG3.5K、OG3K、OG4K、S16(N = 7)。
- **刻意沒做(要核心新功能,先問)**:S16 100p(他的錄影清單在 100p 才多寫 7 個欄位 → 要「每格率」canvas)、
  待機 canvas 清單(S16、OG4K、crop 列:錄影前的取景框)、Crop Mode(OG3.5K/OG4K 1:1 中央)、格率/Crop 反灰。
  沒有表項的格率(S16 100p、OG3.5K/OG4K 48–100)走既有的「標籤鍵無表項 → 退回原廠」。
- 測試 45 項全過。新增:字面值 = Jose 原檔;5 格式的列、選單、S 與參考一致、轉換表對子(UHD 值的格式落在 UHD);QS N=7 = 方案 B 參考;
  UHD 值格式的選取與生效;**程式化序列等價**:我們的虛擬 mode 寫出的感光元件暫存器與韌體記憶體寫入 =「Jose 補丁寫進原廠表 + 他的時序與 clamp」的原廠 mode,
  而我們這邊原廠表逐位元組不變(S16 兩個格率、OG4K、OG3.5K)。資料變異 3/3 抓到。
- 模擬器附註:Unicorn 在裝了記憶體寫入 hook 時會吃掉覆寫迴圈的一次寫入(只在 hook 存在時;沒有 hook 時列正確),
  所以等價測試先在無 hook 下設一次 mode。相機上沒有這個問題。

### 虛擬表與待機取景框(2026-10-07,使用者決定;完成,離線)

- **虛擬表**:原廠「(解析度, 格率) → (profile, mode)」就是 picker 表(`C0BE5810/59B0/5B50`,26 筆 `{5, profile, mode, 鍵}`;
  原廠每格率各有 profile,例 FHD30 = p175/mode 106、FHD100 = p178/mode 89)。我們的表項本來就取代它;現在每個表項同時帶
  mode(虛擬 mode)與 profile(**變體**):格式預設變體 + 表項自帶 canvas 的變體。虛擬 pid 從 32 個空的、類別 0 的 mapping 槽配
  (`VPID_POOL`:列 74..79 在前,維持已上機的 pid),不寫 mapping。`C043A18C` 依變體表給底列(每個變體可換底 profile),
  canvas hook 先套格式清單再套表項清單。
- **資料檔 v2**(核心讀 v1 與 v2;只有用到新段才寫 v2):段 7 `STANDBY`(群組 {pid 清單, canvas 對})、段 8 `ENTCANVAS`
  (每筆 {表項序號, 底 profile(0 = 格式的), canvas 對})。
- **待機取景框**:不是同一張表,是 canvas hook 依「原廠即時預覽 profile 號」套用(Jose:`0xD2/D4/D6/D8`、`5/7/11/21–24`,
  `0xD1/D5` 只在清單高度 ≤ 640 時 = 只有 S16)。寫死的六個預覽高(p5/210/227/257/258/259 +0x28)併成同一機制:
  3:2 格式的 prev_h 在填 S 時變成第一個群組,其後是檔案的群組。
- **資料**:OG3K100 加 `+0xB0 = 1`(原廠 FHD100 對 FHD30 只差 `+0x30` 與 `+0xB0`);S16 100p 帶 Jose 的 7 個欄位(`+90/+B0/+C0/+DC/+E4/+FC/+100`);
  S16、OG4K 帶待機群組。OG2K100 **沒改**(使用者只指定 OG3K100;同理由是否也要 `+0xB0` 待決定)。
- 測試 47 項全過;新:表項變體(自己的 pid、底列、canvas;同格式其他格率不受影響;不 live 不動)、待機群組(每個 pid 對 Jose 規則)、
  差異測試加 v2 段損壞(約 290 檔,核心判定 = `rcd.decode`);OG3K/OG2K 等價除 OG3K100 `+0xB0` 外。變異 10/10(2 個先因編譯失敗重做成行為變異)。

### Crop Mode、格率反灰、Crop 反灰、LV 重建(2026-10-07,使用者決定;完成,離線)

**RE(反編譯 + 映像 + Jose 原檔)**
- `FUN_c043b828`(CinemaDNG 的 picker 呼叫者)組鍵 = 解析度 token + 格率 + Crop 時加 `"CROP"`(`0xC0BE4720`),最長 15 字。
  所以 **crop 變體就是另一批表項**(`OG4K30CROP` …):picker 依鍵自然選到,不需要在 picker 裡讀 Crop getter。
  我們的 picker 改成比對完整鍵(以前只比前 8 字:`OG35K23_98` 與 `OG35K23_98CROP` 前 8 字相同)。
  沒有 Crop 的格式收到 `…CROP` 鍵時去掉尾巴比對(= Jose 的遮罩比對)。
- 格率:`MenuItemMovieFrameRate::v8` 在 `C00A87E4` 匯合點用 r4 = 允許的最快格率(enum)去夾使用者的值(只影響生效值,存的值不動);
  `FUN_c04a1120`(格率清單狀態類別)在 `C04A121C` 匯合點回 r1 = 類別。類別 ↔ 最快格率:0↔119.88、5↔100、3↔59.94、1↔29.97、4↔25、2↔23.98
  (與 v8 的分支一致)。格率 enum/排序表在 `0xC0735F60`(enum、序、fps×100)。
- Crop:`FUN_c04a1788` = Crop Mode 選單項可不可用(1/0);`MenuItemCropMode::v8` 尾端 `C00A93BC` r3 = 生效值。
- 放大鏡:`FUN_c043b638` 在 `C043B6A4` 選 `MAG4`;Jose 在待機清單寬度 < 1024(= S16)時改 `MAG8`。
- **不用** Jose 的「翻一下 Crop 逼 LV 重建」:改由解析度 setter 變成穿過式(前、原廠、後),
  當「我們的生效列變了但相機的值沒變」(OG3K↔S16 都是 FHD、FHD↔OG3K、UHD↔OG4K)時,在原廠 setter 之後做我們的 `lv_reload`
  (CamSch1 6 → stop → start,開機還原用的同一套)。

**核心(能力)**:5 個新 hook(`cropst/cropeff/frmax/frclass/mag`)經一個 `ogc_gate`:只在我們的格式生效時(S.FLAG)改答案 ——
沒有 Crop 的格式 → Crop 反灰並生效值 0;格率上限/類別 = 原廠與格式「較慢者」(所以 SD 卡的原廠限制照樣有效);
MAG8 依旗標。待機群組多一個條件(npids 高半字:0 永遠、1 Crop 關、2 Crop 開,用 Crop getter `C005BB98`)。
S.NEXT 移到 +0x400(64 格;hook 37 個)、BODY 移到 +0x500。

**資料(內容)**:RCD 標頭 `FLAGS`(bit0 clamp、bit1 MAG8、bit2 Crop 可用)、`+0x3C MAXRATE`(fps×100,0 = 不限;原 RSV)。
OG3.5K/OG4K 各多 4 個 `…CROP` 表項(同 donor/時序,canvas 用 Jose crop 列的 PARAM 值)、Crop 開/關各自的待機群組;
S16 帶 MAG8;各格式 MAXRATE(OG2K/OG3K/S16 = 100p、OG3.5K/OG4K = 29.97);OG2K100 也補 `+0xB0 = 1`(使用者 2026-10-07)。

### 測試分層(使用者 2026-10-07 定)

格式會越來越多,逐格式完整模擬做不完,所以依「改了什麼」分兩層:

1. **核心有改**(ogc.c、ogc_shims.S、佈局、RCD 規格):完整模擬(`test_v3_rescustom`)+ mutation。
   核心自證與既有格式等價**用一組代表資料**即可 —— 目的是證明核心不引入差異,不是逐格式驗資料。
2. **只新增或修改格式資料**(`.RCD` 的內容、`jose_formats.py`、`ogc_rowdata.py` 的資料):不跑整串模擬,改做
   (a) 靜態檢查:`rcd.decode` + 建置檢查(格式、範圍、欄位合理性);
   (b) 對來源逐項比對(例:Jose 原檔 → `jose_extract.py`);
   (c) 上機錄一段,看 DNG 尺寸與畫面。

慢測試(逐格式、逐表項的完整等價模擬與大量損壞檔差異測試)標成 `RC_SLOW`,預設不跑,`RC_SLOW=1` 手動跑;
預設只跑代表性的幾組。

### 修正:Settings 格率清單沒反灰(m7 上機,2026-10-07)

QS 每次即時呼叫 `FUN_c04a1120`(我們的 frclass 有效);Settings 的六個 CSV 變體由 `EXCL_FrameRate` 挑,它來自互斥管理器
(`FUN_c049ec58()`)類別 0x19 的**快取**,只在相機自己的設定值改變時經 `FUN_c049ed70 → FUN_c049ee78` 重算。
我們的格式只存原廠值,所以 UHD↔OG4K、OG3K↔S16、FHD↔OG3K 不會重算。修法:setter 後段在「我們的生效列變了」時呼叫
`FUN_c049ee78(FUN_c049ec58(), {0x19, -1})`(韌體自己的重算:問 provider、比快取、有變才通知寫 `EXCL_FrameRate`)。
測試:同值切換會重算、列沒變不重算、一定在原廠 setter 之後;變異 2/2(第 3 個「不清旗標」是等價變異:前段每次都會重寫它)。

### 修正兩個上機 bug(2026-10-08)

- **A:寫回 BIN 會憑空建檔。** 開機後檔案被改名(All Sups 停用),關機時 mode 7 開舊路徑 → 不存在就**新建** → 128 B 殘檔佔住名字。
  反編譯 `XC_MediaFileSdCard::v1` + `FUN_c063b180`:mode 7(→ 內部碼 2)與 mode 3(→ 8)在檔案不存在時**都會建立**;
  只有 mode 1(讀,內部碼 0)找不到就失敗。修法:寫之前先用 **mode 1** 開、讀 32 B FSB1 標頭,要與這個塊載入時的標頭
  逐字相同才用 mode 7 原地寫;不在 → `SAVE_WHY = 1`、不同/截短 → `2`,什麼都不寫,DIRTY 保留(下次再試)。
  LOAD.LOG 是加載器在開機時寫的,關機時沒有通道,所以記在 `S.SAVE_WHY`(+0x3FC)。
- **B:裝了 res-custom 後 FHD/UHD 的 Settings 格率清單不再反灰。** 原因是核心的選單模板沿用 uishare `resolution_qs`
  的 `RES_EXCL`(第 3 列存在、即 N ≥ 4 時套用):把 B2_5 裡 `B2_5_5` 的六個變體名(`_excl`…`_excl5`)**全部改指 `B2_5_5`(全開)**,
  所以 `EXCL_FrameRate` 怎麼變 Settings 都是全開。拿掉它;格率反灰由核心的類別 0x19 重算負責。
  (uishare 的 `resolution_qs` 也有同一段 —— 屬 uishare,未動,請轉告。)
- 測試 53 項全過;變異:不檢查就寫、檢查用 mode 7、不比標頭、模板放回 RES_EXCL —— 4/4 抓到。

### v0.1.2test 上機結果(2026-10-08)

- LOAD.LOG `OCD05050500` / `OCO0000001F`,32RESCUS 載入(0A)。
- 使用者確認 **Settings 格率反灰正常**:原廠 UHD/FHD 恢復原廠反灰,OG4K/OG3.5K 只到 29.97 → **Bug B 結案**。
- Bug A:加載器 e7 改成「停用清單記在 LOADER.BIN 尾端、不改檔名」,已無法從第 6 頁觸發;核心的「寫前先以讀模式確認是自己」修正保留。
- 先前各版累計已上機:五格式選單/QS(N=7)、OG3K/S16 12-bit、OG4K/OG3.5K 8-bit 錄影(DNG 尺寸對、畫面乾淨)、
  S16 待機取景框、Crop Mode 中央 1:1(OG3.5K A001_039,約 1.77 倍)、Crop 反灰、QS 格率反灰、MOV 守衛、LV 重建無凍結。
- 仍待上機:OG3K/OG2K/S16 100p(需 SSD)、OG4K 待機框、新格式重開機還原。

### 快門角度:調查紀錄(2026-10-08,使用者:不用驗證,調查中止;只記已查到的)

- 角度分支的曝光 = nominal fps × 3600 / 角度;nominal 來自 `FUN_c032c750(mode)` = mode 的 META 列 `+0x40`
  (`FUN_c0321028`,經我們的 META 查表 → 虛擬 mode 拿到 donor 列的複本)。原廠 donor 值:98 → 78、117 → 100、139 → 60、
  121 → 25(Jose 的 S16 覆寫成 100)、3 → 30;原廠電影 mode 用整數(23.98 → 24)。
- 我們的 4 個點(`C02092CC/C0218AEC/C0219260/C03AA568`,= 舊 og3kfps 的四點)在 FLAG == 1 且 id 是我們的時,回傳 picker
  最後命中表項的 nominal;nominal 0(OG3K100,`angle_exclude`)→ 原廠 getter → 虛擬 mode 的 117 複本 = 100,與舊 30OG3K 等價。
  表項 nominal:OG3K/OG2K 照 og3k_plan(OG2K 沒有排除,100p 回 100);S16 24…60、100;OG3.5K/OG4K 與其 CROP 表項 24/24/25/30。
  → 角度曝光這 4 點對五格式(含 100p、Crop)都依表項。Jose 原卡沒有這 4 個 hook(他的 S16 角度會用 100)。
- 未處理、只記錄:`FUN_c032c750` 另有約 45 個呼叫者(AF 驅動、`beforeChangeImagerModeHandler`、CycleComm…)看到的是 donor 的
  nominal(OG3K 78、OG2K 60、S16 100、OG3.5K/OG4K 30),與舊 OG 卡、Jose 卡相同,影響未知。
  若要一致,可在虛擬 mode 的 META 複本 `+0x40` 依 pick 寫入表項 nominal(只動我們的複本)。
- 另一個看到的 metadata 點:DNG FrameRate = canvas `+0x30`。OG3K/OG2K 由 engfps 寫成原廠同格的值;Jose 格式 engfps = 0
  → 沿用底 profile 的值(p13 = 60.0、p171 = 30.0),所以 S16 各格率會標 60、OG3.5K/OG4K 會標 30(未上機確認)。

### 虛擬格率 K=4(2026-10-08,使用者決定;離線完成、待上機;QS 未做)
- 定義在核心(`ogc_layout.VRATES`):239.76、279.72 掛在 119.88(enum 7);17.98、8.99 掛在 23.98(enum 1)。時間碼照原廠格率，不掛 hook。有理數 fps 為 240000/1001、280000/1001、18000/1001、9000/1001。
- .RCD 只宣告表項:每筆 entry 的 +36 = rank(fps×100),key 用 base 的鍵(例如 `OG3K120`)。**該格式的 MAXRATE 必須 ≥ 11988**,否則格率反灰會把 119.88 夾掉。副作用：原廠 119.88 列也會變成可選，但沒有對應的一般表項時會走 fallback(待決定)。
- Settings(B2_5):第 9..12 列由 `vr_ui.b25` 的頁副本(FSPG)、六個 CSV 變體(FV 副本)以及 K 個標籤字串組成;四套 LV 版面在原位改寫(EXCL claim)。15 fps 隱藏列從第 9 列移到第 13 列。
- 列可否選擇跟著目前格式走(`vrate_follow`):格式有該 rank 的表項時恢復原廠的 "a,b",否則填 "0,0"。
- 提交:兩個 MV_FrameRate commit(`rcmt1`/`rcmt2`)把 `[var+8]-9` 轉成 S.VRATE。沒有 VR UI 時第 9 列是原廠的 15 fps,不能當成虛擬格率(測試抓到這個 bug,已修)。
- 轉換表：選中的列放第一;摘要匯出也一樣。
- 存檔:CFG FLAGS = 1 | rank<<8。還原時要同時滿足：該 rank 有提供，而且 FR_GET 等於 base。
- 快門範圍／角度(RE 2026-10-08;hook 與 C 由 `ogc_vtv` 處理，只有在 vr_live 時生效，條件是 VRATE、目前格式有提供、相機格率 == base):
  - `tvmin` C007F5B4:MenuItemFactory vptr+0x4A0,最慢 Tv 的 per-fps 匯合點，寫入 {1,n}。
  - `tvmin2` C0553CDC:GUI 最慢限制清單的副本。
  - `tvdisp` C00A075C:MenuItemShutterSpeed::v3 的顯示夾值 [sp+0x28]。
  - `anglist` C0554768:最大角度清單的 enum;回傳 0(15p,全部角度)。未知 enum 會 throw,所以不能回傳自訂值。
  - `angtv` C052DCFC:角度換 Tv 的 fps×100(r6)。
  - n = 240 / 280 / 18 / 9,採用原廠的整數慣例(119.88 → 1/120)。
- 限制：快門步進表沒有 1/9、1/18、1/240、1/280,正規化器會往下取步進值，實際能選的最慢值是 **1/10、1/20、1/250、1/320**(原廠 119.88 實際也是 1/125)。要剛好落在 1/fps 必須換掉步進表與標籤，成本高，沒有做。
- Cine HDR 的路徑(C007F124、FUN_c05523d0)沒有掛 hook,HDR 開啟時維持原廠行為。
- QS(C7):RE 結論是只改記錄最多只能做到 N=10(9 列加 1 列):底列只有 10 個格子物件，游標只有 Cursor10。N=13 需要新增物件，或改成捲動式底列。待使用者決定。草稿配方在 scratch `fr/`。
- Jose 三個格式的引擎格率(engfps)= 原廠同一 picker slot 的 +0x30 值(S16 取 FHD、OG3.5K/OG4K 取 UHD);第 2 層靜態測試比對映像。此欄不是 DNG FrameRate；標籤另由 C00C9BD0 讀取錄影設定。
- 測試(第 1 層):7 個虛擬格率測試 + Jose engfps 靜態測試;mutation 結果見下。
- mutation(2026-10-08):19/19 被抓到(含 shim 偏移、CSV 位置、標籤、還原/存檔、picker、rcmt 的 VR_UI 檢查)。全套 61 測試通過。

### 格式 = mode 清單 + 最高 fps,核心算時序(.RCD v3,2026-10-08 使用者決定;離線完成，待上機)

**.RCD v3 的內容**
- `MODES`(type 9):每筆 {donor, 最高 fps×100, hmax, PAL hmax, x}。
- `RATECANVAS`(type 10):每筆 {rank(0 = 所有格率), crop, base_profile, pairs}。
- 拿掉每格率的 `ENTRIES`/`ENTCANVAS`。header 的 MAXRATE 必須等於 MODES 裡的最大值。
- 核心只讀 v3:v1/v2 的檔案會被拒(WHY_VERSION),所以核心和 RCD 要一起換。

**表項由核心產生**(ogc.c `gen_entry`,Python 參考 `ogc_layout.gen_entries`;兩邊在 S 裡逐位元組相同)
- 產生順序：原廠 9 個格率，再接虛擬格率(239.76 / 279.72 / 17.98;**8.99 暫不產生**,要等上機確認)。
- 每個格率選第一個「最高 fps ≥ 該格率」的 mode。
- Crop 格式另外產生 CROP 雙胞胎表項。

**時序公式**
- 週期數 cycles = 72 MHz ÷ fps。廣播格率都是有理數，所以 cycles 是整數。
- 實際幀週期取 hmax×vmax(§36 的實測結論),因此 vmax = round(cycles / hmax)。
- tail 取「firmware 自己的計數 hmax×(vmax−1)+tail 恰好等於 cycles」的值。
- tail 下限為 MIN_TAIL = 270,這是上機驗證過的最小值(OG3K100)。低於下限時 vmax 減 1、tail 加 hmax。
- 這個公式是 res-lab `solve_timing`(imx410_full.py)的四捨五入版;res-lab 用的下限是原廠先例 330。

**engfps、nominal 與反灰**
- engfps:原廠格率照原廠對照表(100 → 50、119.88 → 60)。2026-10-11 的 M12 候選修正讓 239.76／279.72 沿用其原生 119.88 入口的 60.0；真實格率保留在感測器時序、VRATE 與 nominal。原本填真實格率會開啟 C01CEC08 的 >99 引擎路徑，離線原始韌體已驗證此分岔；是否解決實機分割仍待上機。
- nominal 一律 round(fps),所以 OG3K100 從 0 變成 100(mode 117 原廠的 +0x40 本來就是 100)。
- 反灰規則：格率 > 格式最高 fps 就反灰。原廠與虛擬格率一視同仁，不會有退回原廠的列。
- 原本的「虛擬 base 例外」已經是死碼，已刪除。

**五個格式的 mode 與最高 fps**
最高 fps = 72 MHz ÷ (hmax × (行數 + 原廠 vblank)),取 floor。

| 格式 | mode | 最高 fps | 備註 |
|---|---|---|---|
| OG3K | M98 | 78.84 | PAL 格率用 hmax 450 |
| OG3K | M117 | 104.79 | |
| OG2K | M139 | 112.04 | |
| S16 | M121 | 100 | Jose 的讀出窗，數值照他的 |
| OG3.5K / OG4K | M3 | 29.97 | 照原本的 Jose 資料 |

- 結果：每個格式多了 17.98;OG3K 新增 119.88 這一列(原本就沒有，現在依規則反灰);各格式可選的原廠格率跟今天一樣。

**跟 v0.1.2 的位元組對照**
- 相同：OG3K23_98 / 25 / 50 / 100、OG2K23_98 / 24 / 60 等。
- 其餘改用四捨五入，誤差都 ≤ 今天:
  - OG2K100 / S16100:−604 → +14 ppm
  - OG3K60:−491 → −121 ppm
  - OG3K24:−233 → −85 ppm
- OG3K24 和 OG3K60 原本抄原廠的偶數 vmax,現在由公式算出，都更準。OG3K100 逐位元組相同。三筆都不需要覆寫。

**測試與 mutation**
- 等價測試改成：hmax 與 x 跟今天相同、cycles 精確、|hmax×vmax − cycles| ≤ hmax/2(觸發 tail 下限時 ≤ hmax),而且誤差不比今天差。
- 其餘的燒錄內容先把今天的時序字注入，再逐位元組比對。
- 全套 65 個測試通過;RC_SLOW 的等價測試也通過。
- mutation:產生器 18/18 全部抓到，其中 3 個是補了測試之後才抓到(rank 0 萬用、Crop 標籤長度、udiv 剛好整除);反灰 6/6 全部抓到。

### 暫停點:QS(c)(2026-10-08,使用者要求暫停)
- **已完成，待上機**
  - .RCD v3:格式 = mode 清單 + 最高 fps,時序由核心計算。tail 下限 270,使用者已確認。
  - 每列反灰、快門／角度 hook、K=4 虛擬格率選單(Settings + LV)。
  - 全套 65 個測試通過，產生器 mutation 18/18 抓到、反灰 6/6 抓到。
- **QS(c) 才剛開始 RE,還沒有設計，也還沒寫程式**
  - 第一輪 RE 的結論見本 §15「虛擬格率 K=4」的 QS 一條，以及 2026-10-08 的交接紀錄。該輪的草稿與腳本放在 scratchpad,已被清掉。
  - 已知的關鍵事實:
    - 大圖磚是 `21_MV_FrameRate` 群組(tag 0x1000B),共 18 筆,9 個狀態，終點 266,文字 clip 的鍵在 t=⌊100k/3⌋。
    - controller max 為 8.0,位址 0xC2372B21 / 0xC25E46D7。
    - 游標用的是 Cursor9(4 筆)。原廠池只有 Cursor2..7、9、10,沒有 Cursor8 和 11 以上。
    - 底列有 10 個格子物件，格率頁在 t=733。格 10 一直是 collapse;沒有第 11 格以後的物件。
    - 解析度 QS 方案 B 的先例:N=8 用 Cursor7,底列位置曲線 C2358981 整體平移(fpSup/uishare/QS_SHARE.md §1、§3、§13)。
  - 第二輪 RE 開了兩個背景代理，已要求它們停止並把成果留在專案目錄:
    - `projects/open-gate/build/res-custom/qs_fr/`:N=13 的大圖磚、終點與 max 配方，以及先例查核、與解析度配方的重疊檢查。
    - `projects/open-gate/build/res-custom/qs_fr/footer/`:底列與游標的兩條路 —— A 新增物件、B 仿 ISO 的捲動底列。
    - 這兩個目錄的內容可能不完整，恢復時先看裡面有什麼。
- **恢復時的下一步**
  1. 看完 qs_fr/ 的成果後，決定走 A 或 B,回報設計：要改／新增哪些記錄、Cursor 的名稱、記錄數、上限、與解析度方案 B 共用核心的 QS 記錄層(qtab)，以及工作量。
  2. 使用者同意後才實作。
- 發布凍結照舊。
- **底列代理的收尾回報(2026-10-08)**,工具:`qs_fr/footer/qsfoot.py`
  - 【反組譯】解析迴圈不數記錄，一直呼叫 FUN_c05e6400,直到結束記錄才停。
    - 推論:hook 交出「原記錄 + 新記錄」的複本，再連呼 next 幾次，就等於插入記錄。這點尚未驗證。
  - 【反組譯】物件陣列用物件 id 插入排序、查找用二分搜尋，所以新物件只要 id 不重複就行。
    - 但陣列容量 = 配置標頭(0x10002)的 objects 數 ×4,而且沒有邊界檢查;arena 大小也由標頭決定。
    - 所以新增物件時，標頭一定要一起改大。
  - 【離線】底列結構：Footer 299 → QSMode 339 → Image 9148 → 9149(寬 1024)→ 格子 9150..9159(共 10 格，由 flexBox 排位置)。
    - 13 格 × 92 = 1196 > 1024,步距要縮到約 78,不然就要改成捲動。
  - 【離線】游標物件 9113 / 9556 的位置 clip 格數：3 / 5 / 6 / 7 / 11 號 clip 是 2 / 3 / 5 / 7 / 4 格;10 號 clip 9 格(98..834);8 號 clip 10 格(52..880)。
  - 未做：Cursor 名字對應到哪個 clip、ISO 捲動底列(B 路)、記錄清單與成本。
- **大圖磚代理收尾(2026-10-08)**:只做了分析，沒寫配方，`qs_fr/` 是空的。
  - 【離線驗證】要改 18 筆文字 clip:
    - CINE / Common 那幾筆 198 B,屬性 vis、text、pos;
    - STILLlike / Common 那幾筆 168 B,屬性 text、vis。
  - 做法：在 text 屬性的尾端追加 t=300/333/366/400 四個影格，值用 marker。每筆 +40 B,最大 238 B(推算，還沒逐欄驗證)。
  - 另外要改：終點 18 筆(266 → 400);controller max 2 筆(0xC2372B21、0xC25E46D7),在 +32 原地把 8.0 改成 12.0。預估總共 38 筆。
  - 先例：原廠的 18_CM_WhiteBalance 和 27_CM_ColorShading 就是終點 400、13 個影格(t=⌊100k/3⌋),所以 k=12 有先例。
  - 未做:gen / verify 腳本、與解析度配方的重疊比對;列 13(15 fps)不補影格(傾向如此，待確認)。

## 2026-10-10：RES-CUSTOM 的獨立 RCD 啟用管理

使用者指定 RES-Lab 只負責編輯／即時虛擬配方與 SAVE，RES-CUSTOM 管理磁碟檔啟用／停用。
最後卡片 `projects/res-lab/cards/20261010-save-v35/{debug,plain}`，producer header17、consumer header7，
已寫入相機。動態人類名稱 `RES-Lab`，內部 VRC000／Virtual RCD ABI2 operations1–4 維持。

consumer 的 More Settings 開自有原生 RC_FILES 頁，私有 RC_Focus／RC_Key，左右選檔、OK 啟用／停用。
啟用記錄沿用 RCS1，完整讀回核對，重開才更新磁碟解析度列；不動本次活動配方。
virtual 保留一格、磁碟五格，獨立 consumer 六格；滿額顯示需要先停用一個。
獨立全部有效檔停用時只保留管理 GUI hook，原廠錄影不改；沒有檔案／全無效仍 RELEASE。
掃描 scratch／頁面變數／焦點皆為 consumer 擁有，未改 loader／AutoRun／錄影公式。

離線驗證：v34 原生流程及頁面8項、claim還原／Settings2項、v35頁面4項通過。
之前的18項 SAVE／sidebar／M12／M9 239.76／279.72p timing／canvas回歸通過；
入口矩陣14組／AutoRun independence3組／catalogue refs8組通過。故意斷開 RC_Key callback 可被測試抓出。

實機：SAVE A9 992×662完整讀回；滿額拒絕、OG2K OFF／A9 ON、重開加入原生列，
原生解析度 popup 可選 A9，QS兩次 draw 與選值一致。NBR A9_FONT／A9_QS 的 filename 是 e2.xci／e0.xci。
最後 A9 OFF、OG2K ON，重開恢復原五檔＋VRC000，相機正常待機。
本輪未錄影／SSD測試，未完成十次實體power-off循環，未發布。
完整命令、成品SHA、通過／失敗／未做及證據索引：
`projects/res-lab/validation/20261010-saved-rows-v29/RESULTS.md`。

## 2026-10-11：RES-CUSTOM 採 SupManager 列表與名額提醒

依使用者要求，v37 以相同 manage_page builder 產生 consumer 私有五列頁面：
數字分頁、檔名與 Enabled／Disabled 同列、原生 Enable／Disable popup；
有效 catalogue 上限16、最多四頁。RC_ descriptor／callbacks／scratch 仍為 consumer 擁有，
不共用 FT_／SL_ 操作變數，不修改 SupManager 或共用載入流程。
v37 已實測第一／第二頁、第二頁 S16 啟用停用、空白列鎖定、取消與返回原 SupManager row4。

最終 v38 卡在 `projects/res-lab/cards/20261011-count-v38/{debug,plain}`，
consumer header9／producer header17。84 個私有變數、123 個私有字串；
標題 `RES-CUSTOM (n/5)`、獨立版 `(n/6)`，實際改變清單且保存成功後顯示 `Restart to apply`。
新建卡來源31份hash核對，普通／debug產品BIN一致；producer、loader、AutoRun 與 v37／v35 完全相同。
四項原生頁面、六項實際 ARM 檔案管理、兩項還原／入口檢查全部通過。
本輪沒有 commit／push／發布。

v38 已部署並重開核對 header9，實際 A9 啟用／停用使標題 0/5 → 1/5 → 0/5，
重開提醒經原生 FocusOff 仍保留，重新開 popup 回到確認提示；截圖無遮擋。
最後完整 configured consumer readback 與部署成品相同，SHA-256
`55a43ca02a34c842b71b6233f93fde86c20fc7f9af4899a5f0e819392cd9d1b6`。
本輪使用者部署前已將磁碟檔全停用，已恢復該 VRC000 sentinel，並非上輪五檔清單。
活動 consumer／rows／registry 未變，producer 只初始化預設 UI，沒有提交配方，相機正常待機。
沒有錄影／SSD測試，約十次實體 power-off 循環仍待驗；軟體 reboot 不代替該驗收。

目前 virtual-capable 版固定預留共用動態列，卸載 RES-Lab 不會自動歸還第六個磁碟名額。
不能以 provider==0 判斷沒有工具，尚未提交配方也會是0；未來需辨識任意虛擬工具。
完整範圍、通過／失敗／未做、成品hash與實機證據索引：
`projects/res-lab/validation/20261010-files-v36/RESULTS.md`、
`projects/res-lab/validation/20261011-count-v38/RESULTS.md`。
