# fp 原生 UI 導航

目標是**完全控制 fp 的原生 UI**。這份是進入點:先看這裡決定要走哪條路,再去讀那條路的筆記。

隨附兩個檔案:

- [`NBU_RECORD_FORMAT.md`](NBU_RECORD_FORMAT.md) —— **格式本身的完整參考**:兩個容器、記錄框架、解析 context、四個讀取方法、逐 tag 的 token 文法,每一條都標了是「跑出來的 🟢 / 讀反編譯 🔵 / 還沒讀 ⚪」。
- [`ui_map.json`](ui_map.json) —— 人工整理的地圖:區域、函式、hook 點、誰改過什麼、六條路線、九個陷阱。每一筆都帶出處。
- [`tools/uinav.py`](tools/uinav.py) —— 查詢工具。字串池、頁表、圖示清單**不存檔**,直接從釘住的韌體映像讀,所以不會跟映像脫節。

```
python3 research/ui/tools/uinav.py verify            # 映像 hash、四個索引的規模
python3 research/ui/tools/uinav.py at 0xC05E6400     # 這個位址是什麼、誰 hook 了它
python3 research/ui/tools/uinav.py pages ^Main       # 196 個原生 GUI 頁 → page id
python3 research/ui/tools/uinav.py sets Main         # 221 個 NBU 資源集(模擬解出來的)
python3 research/ui/tools/uinav.py pool Resolution   # 14,470 條字串池(含 pool offset)
python3 research/ui/tools/uinav.py screens           # gui scr set 能用的畫面名
python3 research/ui/tools/uinav.py vars --count      # 變數命名空間統計(CM_ 589、PB_ 328…)
python3 research/ui/tools/uinav.py icons qs_resolution
python3 research/ui/tools/uinav.py who fpsup-formats # 某個產品動到的每一個位址
python3 research/ui/tools/uinav.py routes            # 六條介入路線與代價
python3 research/ui/tools/uinav.py traps             # 已經踩過的坑
python3 research/ui/tools/uinav.py emu               # 哪些原生入口已經能離線執行
python3 research/ui/tools/uinav.py find resolution   # 橫跨所有索引一次找
```

測試:`cd research/ui/tools && python3 -B -m unittest test_uinav`(19 項,全離線)。
其中一項用 `MAINB2_ROW_EXTENSION.md` 獨立算出的 pool offset `0x1A3B8 → MainB2`
反過來釘住池基底 —— 因為只用 uinav 自己的算式寫測試會**自我一致地錯**。

---

## 1. 五層,重點是「什麼時候被讀」

| 層 | 位置 | 何時讀 | 執行期改得動嗎 |
|---|---|---|---|
| enum→state 配對表 | `0xC2E4020C` (RAM) | **每次求值** by `0xC06CCD10` | ✅ 立刻,下一次重繪就生效 |
| 字串池 | `0xC18C0474` (14,470 條) | 隨需,經 `0xC05E5B58` | ✅ 用 resolver hook 供應合成 offset |
| 序列化 UI 記錄 (NBU) | `0xC1900000`–`0xC2D80000` | **每組資源集只解譯一次** | ⚠️ 只能在解譯當下換掉(見 R2) |
| 解析後的元素物件 | GUI heap | 隨螢幕物件生死 | ❌ 固定位址的修改留不住 |
| XCI 圖示 | `0xC1240014`–`0xC151C348` | image open 路徑,**按名字快取** | ⚠️ 要用新名字才會重新解碼 |

這張表就是整件事的核心:**位置不重要,讀取時機才重要。**
八份解析後的元素副本被改對過、讀回過,之後掃 144 MB 一個都找不到 ——
不是被重建,是擁有它們的螢幕物件被釋放了。

補充索引(都可用 `uinav.py` 直接查):

- **GUI 頁表** `0xC0D0DB68`..`0xC0D0E1B0`:196 筆 `{name_ptr, page_id}`。`MainB2` = 10、`MainY4` = 20。
- **XCI 建置清單** `0xC0D24968`:2006 條 `../ResXCI/...` 路徑;圖檔庫實際有 **2004 個 blob**
  (README §2 寫 2005,以走訪結果訂正;有 2 個缺口,所以 index 對位要靠尺寸確認)。
- **資源目錄** `0xC0D4DDC0` 起的 16-byte **big-endian** 記錄 `{length, offset, count, hash}`。
- **自由空檔** `0xC0793060`:韌體裡的零區,已被用來放私有 UI pack。

**改完什麼時候生效** → [`HOW_CHANGES_TAKE_EFFECT.md`](HOW_CHANGES_TAKE_EFFECT.md)。

## 2. 六條路線

`uinav.py routes` 會印出完整版。摘要:

| 路線 | 代價 | 拿到什麼 | 驗證狀態 |
|---|---|---|---|
| **R1** enum→state 配對表 | 一個 word | 多一個顯示狀態 | ✅ 實機 |
| **R2** 私有 NBR + 指紋守衛的記錄副本 | 3 個 Thumb hook + 一包 pack + ~2.5k words | **真正的原生列、QS 圖磚、底列、收合摘要** | ✅ 實機(FP3K、og3k、formats) |
| **R3** 目錄改指向 | 8 bytes / 個資源 | **換掉任何資源:圖示、字型、195 個選單 CSV** | ✅ 機制已解,且能重現實機補丁 |
| **R4** 解析後的圖磚退路 | 3 個 hook,只蓋 20/21 圖磚 | 已經解析過的畫面上補一個圖磚 | ❌ 只追過,沒裝 |
| **R5** donor 列改嫁 | 龐大的離線配方 | **全新的設定項**(不是既有項的新值) | ❌ 只有離線 |
| **R6** 畫在 UI 上面 | 小 | 文字、方框、點陣圖、false color、開機橫幅 | ✅ 實機(本專案 + 兩個第三方) |

**目前唯一能做出原生外觀的路是 R2**,R3 是它的載入手段。
R1 只換狀態、不生美術。R6 不是原生 UI,但便宜又可靠。

### R2 的三個 hook(照這個順序上)

```
0xC05E5B58  NBU string resolver   先武裝(被動依賴)
0xC05E84D8  NBR memory loader     註冊一次私有 pack
0xC05E6400  NBU record 解譯器     最後武裝 —— 它一活就會把合成 offset 丟給原廠 parser
0xC05D90F0  layout loader         og3k 再多掛一個:把 hook 之前建好的 Quick Set 佈局丟掉,
                                  下次載入才會重新解析
```

每一筆目標記錄:比對**位址 + 原始位元組的 FNV-1a**,複製到 512 bytes 以內的暫存區,
在副本上加新狀態與**所有伴隨屬性**,再讓原廠解譯器去解那份副本。

## 3. 六個一定會撞到的事

`uinav.py traps` 有全部九條。最貴的六條:

1. **只加圖片屬性沒有用。** 新狀態要同時出現在 controller 最大值、group endpoint,
   以及 visibility / rectangle / position / collapse / cursor / timeline 每一個伴隨屬性,
   少一個圖磚就疊在一起、看起來壞掉。
2. **CSV 加一列會「看得到但選不到」**,直到 `0xC1A709BC` 的 controller 最大值變大
   (三列要 2.0、六列要 5.0)。
3. **解析度陣列開機後不再重建。** 掛著 append hook 試過 QS 重繪、`gui scr set 1_03_CINE`、
   換走再換回、MENU 開關、`SetRecMode`、`STILL`/`CINESW` —— 命中 **0**。
   所以 target bitmap 全 0 是**時機沒對上**,不是畫不出來。
4. **合成的圖示名字必須是新的**,沿用原廠 `_2` 的名字,快取後端沒有理由再解碼一次。
5. **GUI 區全是 Thumb-2。** 進 hook 用 `B.W`(T4)不要用 `BL`,`lr` 才留著原本的返回位址;
   local label 之間不要 `bl`(`R_ARM_THM_CALL` 沒實作);回去用 `bx` 到 Thumb 位址。
6. **量測會被上一格污染。** `gui image log` 跨幀,狀態改完的第一次重繪還帶著舊狀態的圖示。
   正確做法:關畫面 → 改設定 → 等 3 秒 → 開(丟掉)→ 關 → 清 log → 開(這次才算)。
   而且截 Quick Set 要用 `display capture <path> 3 2`(`retries=0`),不要用 `key CAPTUREON`,
   它會把 overlay 關掉;主層是 **ARGB4444**,不是 L8A8。

## 4. 模擬器是這條路的主力工具

`skill: fp-unicorn-emulation`。UI 這邊用的是同一招:**釘住的原廠指令**在 unicorn 裡跑,
只把外部服務換成 Python 替身,而且**沒登記的呼叫會炸**。`uinav.py emu` 列出現況:

| 探針 | 已執行的原生入口 | 測試 |
|---|---|---|
| **`tools/nbu_probe`** | **`0xC05E6400` 記錄解譯器本體** + context 建構子 + 四個讀取方法 + 字串解析 + 物件工廠 | **32** |
| `tools/native_variable_probe` | `0xC05DB309` 註冊、`0xC05DB419` 查找、`0xC05DCA89`、`0xC05ED249` | 15 |
| 同上(binding) | 為什麼 callback 錯誤否決不了原生賦值、為什麼單靠 unsubscribe 不能回收 callback 記憶體 | 18 |
| `tools/native_page_probe` | 延遲載入頁面 | 16 |
| `tools/native_control_probe` | 選擇控制項的權限(也就是「灰掉」這件事) | 14 |
| `tools/native_component_schema.py` | 產出 `component-schemas-v502.json` | — |

### 最小產物:三個寫入做出第三列(2026-09-29)

`tools/menu_row_patch.py --append "3K 3008x2000"` → 新 CSV(121 B,寫在
`L_resolution_480p.xci` 上)+ 8 bytes 改指標 + `0xC1A709BC` 的 BE float(列數−1)。
**133 bytes,零 hook。** 只到 Settings —— QS 圖磚要另外 152 筆記錄。
配方在 [`RESOURCE_REPLACEMENT.md`](RESOURCE_REPLACEMENT.md)。

### 換任何資源只要 8 個位元組,不用 hook(2026-09-29)

完整說明在 [`RESOURCE_REPLACEMENT.md`](RESOURCE_REPLACEMENT.md),工具 `tools/nbr_stock.py`。

`0xC0D22400` 的 **NBR 容器**跟 NBU 同一個記錄格式。它的 tag 2 裡是一張
**2259 筆、16 bytes、big-endian、按 key 排序**的目錄:
`{FNV-1a(路徑), 名稱池位移, 資料位移(從 0xC0D22400 起), 長度}`。

**往一筆的 +0x08 寫 8 個位元組,就把那個資源換掉了** —— 圖示、字型,以及
**每一個選單列表 CSV**(共 195 個 `.cvm`)。新內容可以比原廠長。

原廠解析度選單就是 89 bytes 的 `../MenuB12/data/ListB12/B2_5_4.cvm`:
兩列 `1,0313` 與 `2,0314`。**「選單有幾列」的來源就在這裡。**

驗證:2259/2259 的 key 等於路徑的 FNV-1a;2005/2005 的 `.xci` 資料位址是 `XC  `;
而且我們算出來的補丁與 fpSup-Formats 實際寫進 `0xC0D4DE04` 的 8 個位元組**逐位元組相同**。

### 記錄格式已經解開 —— 可以直接改資料,不用 hook(2026-09-29)

**每一筆記錄都是 `{BE tag, BE size, body}`,`size` 含表頭。** 因為自帶長度,
拆開／換掉／插入／重新輸出一整個資源集**完全不需要逐 tag 的文法**。
純 Python 的 [`nbu_format.py`](tools/nbu_probe/nbu_format.py)(不依賴 unicorn)
0.4 秒拆完**全部 221 個資源集、303,597 筆記錄**,而且
**220 個集合首尾相接一個位元組不差**;MainB2 的 1392 筆邊界與韌體解譯器完全相同、
`join()` 回去逐位元組相同。

關鍵的兩個 tag:**`0x10003` = 物件**(數量 = 配置標頭的 `objectBase`)、
**`0x1000B` = 影像陣列**(全 UI 11,383 筆;實測它是唯一會呼叫 `FUN_c05e2988` 的 tag,
就是 README §5c 講的 case 10)。「加一個 UI 狀態」要同時動影像陣列、每個伴隨屬性、
配置標頭 `0x10002`,以及 `0xC1A709BC` 的 controller 最大值。

**還缺兩件事**:記錄 body 的逐欄位文法(只解了一部分),
以及把改好的 set 交給韌體載入的路(R3 資源目錄改指向,欄位語意未追)。

### `0xC05E6400` 已經在跑了(2026-09-29)

完整說明在 [`tools/nbu_probe/README.md`](tools/nbu_probe/README.md)。第一段做完的結果:

- **token 是 big-endian u32** —— 由建構子安裝的四個讀取方法直接證實。
  所以 `0xC1A709BC` 寫 `40 A0 00 00` 就是 5.0。
- **20 MB 記錄區不是一個線性容器。** 最上層只有兩筆:字串池(tag 1,執行後
  `ctx+0x14` = `0xC18C0474`)與 **221 筆資源集索引**(tag `0x10001`,每筆
  `{FNV hash, 名字, 從 0xC18C0460 起的位移}`)。每個螢幕各自一段記錄流 ——
  這解釋了「某些 set 延遲解析」與「開機後解析度陣列不再重建」為何能並存。
  索引存成 [`nbu_sets.json`](nbu_sets.json),`uinav.py sets` / `uinav.py at` 都吃它。
- **資源集的開法**:沒有 magic、cursor 從 0、版本從上層繼承、`ctx+0x0C` 要給 owner 物件。
- **tag `0x10002` = 配置標頭,已完全解出。** MainB2 是 3,028 bytes = 757 個 BE word,
  宣告 23 個類別(`objectBase` 193 = `objects` 欄位、`drawText` 27、`controlValue` 20…)。
  **加一列就要動這張表。**
- 三個手算值被執行結果一字不差地證實:MainB2 的 hash/pool offset/位移、
  MainB2 與 MainY4 的頁面邊界。

**下一段:走到元素建構。** 目前停在 MainB2 的第二筆記錄(`0xC05E7770`),
差的是真的 app 物件 —— 六個函式在等:`0xC05D9080`、`0xC05D9378`、`0xC05D9B00`、
`0xC05D9E88`、`0xC05E04E8`、`0xC05E0CC8`。`native_variable_probe` 已經示範過
怎麼給一個合成 registry,接上去就能離線驗證「六列選單的記錄副本會被怎麼解析」。

模擬告訴不了你的事:GUI 會不會畫出來、螢幕什麼時候被解析、替身取代掉的原廠函式原本會做什麼。

## 5. 誰改過什麼

完整清單在 [`UI_MODS_INVENTORY.md`](UI_MODS_INVENTORY.md),`uinav.py who` 可查單一產品。

---

版本:2026-09-29。位址只對 Ver.5.02。
