# 合併機制研究：從「改原廠」改成「添加」

2026-10-03。研究與評估，尚未實作任何一項。前作：`fpSup/uishare/PLAN.md`（操作清單）、
`research/ui/UI_SERVICE_INVENTORY.md`（各 sup 改了 UI 的哪裡）。本頁回答使用者的三個問題：
每個 sup 能不能都用「添加」、添加機制要不要做成獨立 sup、值不值得；並記下 Lossless 開機變慢的原因。

證據等級沿用 fp-native-ui：**[實機] [離線] [推論]**。

---

## 1. 現在每個 sup 是怎麼改選單的

| sup | 使用者看到的 | 實際做法 | 性質 |
|---|---|---|---|
| raw-view | COLOR 清單第 17 列 RAW | 3 個 CSV（`ListColorButtonMenu`、`_EXCL`、`_EXCL2`）以 H1 hook（`C05E5BEC` 取檔位置）**整檔換成自己的版本**；9 個 NBU 版面字原地改（清單上限 15→16 等）；getter 表 movw/movt；多個 GUI→enum stub | **改原廠**：Color 清單只有一份，誰再改它就撞 |
| OG3K / OG2K | 解析度第 3 格 | CSV `B2_5_4` 第 3 列原地改；controller max；~360 筆 NBU 記錄經 `C05E6400` 解析 hook 逐筆換；私有 NBR 包（`C05E84D8`）；字串別名 hook（`C05E5B58`） | **改原廠**：兩個 OG 都要「第 3 格」→ 互斥 |
| Lossless | SHOOT 第 2 頁多一列 | MainB2 **整頁換成自己的複本**（runtime 項目 `entry+08`）；私有字串走 FSPL 共用池 | 字串已是添加；**頁面是取代**：第二個想在 MainB2 加列的 sup 只能二選一 |
| Sensor Lab | 240 fps、14-bit、反灰、私有頁 | B2_5 整組原地重建；CSV 變體原地改；私有頁用私有 NBR 註冊 | **改原廠**：與 OG 都動 B2_5 |

唯一已經是「添加」的是字串（`uis_intern`，FSPL 標頭，誰都可以接著加）。[實機]

## 2. 衝突從哪裡來

全部衝突都落在「原廠只有一個位置」的東西上：

| 單一位置 | 誰在搶 |
|---|---|
| 一頁的執行期項目 `entry+08`（指向哪份頁面） | Lossless（MainB2）；未來任何加列的 sup |
| 一個清單的 CSV（以及它的上限、ListItem 數、每值事件） | raw-view（Color）、OG3K vs OG2K（解析度第 3 格）、Sensor Lab（格率／位元深度） |
| 解析 hook `C05E6400`、字串 hook `C05E5B58`、取檔 hook `C05E5BEC` | OG 擁有前兩個；raw-view 擁有第三個；Sensor Lab 也想要記錄 hook |
| QS 版面（開機解析後常駐） | OG（~360 筆）；raw-view 計畫中 |
| 字串池 `reader+0x14` | 已解決（FSPL） |

**程式碼段落本身不衝突**（hook inventory，2026-10-01 [離線]）——衝突全在 UI 資源與它的執行期結構。

### 一個例外：OG3K + OG2K 不是 UI 能解決的

兩者的 88 個段落放在**完全相同的位址**（2026-10-03 比對 v0.2.8a / v0.1.5a [離線]）：錄影核心是同一份程式、
不同的表。選單改成添加，也只能讓兩個選項「同時出現在清單裡」；要真的合併，得把 OG 核心做成一份
同時帶兩套幾何的產品（或把核心拆成「共用核心 + 每個解析度一份表」）。這是 OG 的產品工作，不在本頁的機制裡。

## 3. 「添加」模型

原則（已寫在 uishare PLAN，這裡收斂成一句）：**每個共享資源變成「原廠 + 附加清單」**。
第一個要附加的 sup 把原廠那份複製成可擴充、帶自我描述標頭的版本並切換過去；之後的 sup 找到標頭就接著加；
編號（列號、選項 index、字串位移、物件 ID、Y 座標）一律在載入時發放，不事先佔用。

需要的操作（PLAN 已列，這裡標上誰會用）：

| 操作 | 用的 sup | 取代現在的 |
|---|---|---|
| `uis_intern` 字串 | 全部 | 已完成 |
| `add_row(頁, 片段)` | Lossless、lcdflip、未來的開關類 sup | Lossless 整頁替換 |
| `add_option(清單, 標籤) → index` | raw-view（Color RAW）、OG（解析度）、Sensor Lab（240、14-bit） | 原地改 CSV / H1 換檔 / 佔第 3 格 |
| `set_option_enabled` | Sensor Lab | CSV 變體原地改 |
| 私有圖示包 | OG、raw-view | 各自註冊 NBR |
| 記錄 hook / 取檔 hook 的**串接** | OG、raw-view、Sensor Lab | 各自獨佔 |
| QS 狀態 | OG | 360 筆逐筆換 |

`add_option` 是核心也是最貴的：一個新選項要同時補 CSV 列、controller max（可能不只一個，fp-native-ui §2 規則 9）、
ListItem 實例數、每值 `controlValueEvent`+`controlFocus`、收合摘要子物件與其上限、row↔enum 與 enum↔state 表。
QS 再加一層（影像陣列、伴隨屬性、配置標頭），單一選項就是數百筆記錄。

### 還沒在相機上證明的前提（PLAN「Mechanisms to prove」）

1. **CSV 改指 RAM 複本**：NBR 目錄在映像裡開機後就失效 [實機]，但 heap 上的檔案表（raw-view `rv_uidiag nbr`
   讀到 reader `+0xAC` 數量、`+0xB0` 表、`+0xB4` 基底）可能是活的 [推論]。raw-view 的 H1 證明了「在取檔位置換掉」可行 [實機]；
   把 H1 做成共用的「取檔改指表」（多個 sup 往同一張表加 `{原廠位址 → 新資料}`），就是 CSV 添加的最小實作。
2. **子頁改指**：B2_5 已在相機上證明 [實機 2026-10-02]，MainB2 也是 [實機]。
3. **QS**：開機解析後常駐，需要強制重解析（OG 的 `C05D90F0`）[實機]。

## 4. 添加機制放哪裡：三個做法

### A. 函式庫（現行 uishare 的做法）

每個 sup 把同一份 C 碼編進自己的 BIN，按約定操作共享資料。

- 好：沒有相依；單獨發布不用多帶東西；合併器不用懂 UI；已在 FSPL 上證明可行。
- 壞：程式重複——每個 sup 帶一份（`ui_pool` 很小；`add_option` 估計數 KB）；
  兩個 sup 帶不同版本的函式庫時，只能靠資料標頭的版本號相容。
- **致命處：hook 只能有一個主人。** `C05E6400`、`C05E5BEC` 這類點，函式庫做法下仍然是「誰先裝誰贏」，
  後來的 sup 看到不是原廠字就退讓（raw-view、OG 現在都這樣），那個 sup 的 UI 就少一塊。

### B. 獨立的 UI 服務 sup（先安裝，匯出 API 表）

- 好：一份程式、一處修；所有 hook 只裝一次，內部維護 handler 清單；QS 重解析統一處理。
- 壞：
  - 每個改 UI 的 sup 都依賴它，單獨發布的卡也得帶它——實際上變成「每張卡都要有」，等於共用 loader 的第二層；
  - 新的 ABI（API 表格式、版本、找到服務的方法）要凍結，改一次所有 sup 重發；
  - 「先安裝」違反 SUP_BUILD_RULES §1/§2「不讓 sup 互相接力、沿用 entries.S 的順序」，要改契約；
  - 服務有 bug 時所有 sup 的 UI 一起不見。

### C. 混合：資料約定 + 小函式庫 + 可串接的 hook 標頭（建議）

- 字串、頁面複本、CSV 複本、清單上限這些「資料」照 A：自我描述標頭 + 函式庫，各 sup 自帶。
- 只有「單一主人」的 hook 點另立一條約定：**第一個需要的 sup 安裝一個帶標頭的跳板**
  （`magic | 版本 | handler 數 | handler[]`，放在自己配的永久記憶體），之後的 sup 找到標頭就把自己的 handler 加進表，
  不再「看到不是原廠字就退讓」。和 FSPL 同一套思路，沒有獨立產品、沒有安裝順序要求。
- 好：保留「每個 sup 單獨可用」；重複的只有小函式庫；解決了 A 的致命處。
- 壞：跳板本身要極小心（在 UI 執行緒、每筆記錄都經過，要快、不能配置記憶體）；每個 hook 點都要一份跳板規格；
  已發布的 OG / raw-view 不認得這個標頭，舊版和新版不能混用（和 FSPL 當時一樣，要合併器標示不相容）。

### 值不值得

| | 不做（維持現狀） | C |
|---|---|---|
| 已發生的合併事故 | 字串池 vs OG 別名（10/01）、OG3K/OG2K 互斥、raw-view 在 lossless+og3k+gyro 卡上選單壞掉（10/03，原因未定） | — |
| 每新增一個 UI sup | 每一對組合都可能要個別修，成本隨組合數增加 | 只要遵守約定 |
| 一次性成本 | 0 | 函式庫 `add_row` / `add_option`（不含 QS）+ 兩個 hook 跳板（記錄、取檔）+ 每個 sup 改寫並重發 |
| QS | — | 最貴；先只給 OG，其他 sup 暫不做 QS |

判斷：目前有 4 個改 UI 的 sup、2 個在路上（Sensor Lab、lcdflip），已經出現 3 次合併事故，**做 C 值得**；
但 **QS 的通用化不值得先做**——只有 OG 需要，成本是其餘全部的好幾倍。

## 5. 各 sup 改成添加後的樣子

| sup | 改成 | 先決條件 |
|---|---|---|
| raw-view | `add_option(Color, "RAW")` 拿到 index（不再寫死 17）；H1 換檔改成往共用取檔表加項 | 取檔跳板；CSV 複本機制（§3 前提 1） |
| Lossless | `add_row(MainB2, 片段)`；MainB2 由共用「頁面複本」提供，別的 sup 也能在同頁加列 | 頁面片段重定位（ID、字串、Y、配置標頭容量） |
| OG3K / OG2K | `add_option(解析度, "OG3K")`；QS 記錄用參數化片段；字串別名 hook 換成 `uis_intern` | 記錄跳板；**兩者同卡還需要 OG 核心合一（§2 例外）** |
| Sensor Lab | `add_option` ×2 + `set_option_enabled`；不再整組重建 B2_5 | 與 OG 共用 B2_5 的添加 |

## 6. Lossless 開機變慢：原因與修法（字串池提示已實作，2026-10-03；完整方案見 `fpSup/uishare/MENU_MERGE_PLAN.md`）

- 量到：lossless + shell + gyro + og3k + raw-view + FS2 卡，`LOAD_DONE_US` = **20.05 s**
  （fp-merged-card 參考：快速路徑 11–12 s、慢速 15–16 s）。[實機 2026-10-03，一次]
- 原因（高度可能）：`ui_pool.c` 的 `find()` 對每個字串把整個 17 萬 bytes 的池逐字比對一遍；
  Sensor Lab 實機量到每個字串約 0.25 s（80 個字串 → 多 ~20 s，fp-native-ui §8e）。Lossless 的頁面有 18 個引用、
  快取只有 8 格，十幾次完整掃描 ≈ 數秒。[推論，待量]
- 修法（不改約定、不改資料格式）：
  1. **原廠位移提示**：builder 離線就知道原廠池內容（ROM），把「原廠已有的字串」的位移一起打包；
     執行期只比對那個位移上的 n 個 bytes（O(n)）就回傳，不用掃描。
  2. **只掃附加區**：原廠池沒有的字串，只需在 `len > 原廠長度` 的附加區找（別的 sup 加的，通常幾百 bytes）。
  3. 兩者合起來，`uis_intern` 從「每個字串掃 17 萬 bytes」變成「幾十 bytes」，預期 Lossless 多出的幾秒歸零。
- 驗證：同一張卡改前改後各開機 3 次比 `LOAD_DONE_US`；Sensor Lab 也同時受惠。

## 7. GitHub 上的合併網頁（2026-10-03 檢查）

- 線上頁 = commit `199ced0`（SHA-256 相同）。
- 用它自己的測試、配上有 `--read-cap` 的載入器跑：35 個組合 / 106 種情況**全過**；目前任何產品組合都不會觸發「拉高讀取量」。
- 但跟上一版（`332404d`）比，**每一張卡的 stage2 都不同**：線上頁內嵌的 stage2 是用本機未提交的 `stage2.S`
  建的（呼叫入口前把堆疊對齊 8 bytes，864 → 876 B）。AutoRun 完全相同。
  - Fast Start 2 版的這個 stage2 已隨 Lossless 測試卡多次上機 [實機]；一般卡（非 FS2）版沒有單獨上機過。
  - GitHub 上的原始碼重建不出這一頁（`build_autorun --read-cap` 與 `loader.S READ_CAP` 都沒提交）。
- 結論：**功能上沒壞**，但它發的卡帶著一個 GitHub 原始碼裡沒有的 stage2。兩條路：
  補提交載入器那一半（讓原始碼與網頁一致），或退回 `332404d`（stage2 回到舊版）。

## 8. 建議的順序

1. `uis_intern` 加原廠位移提示 + 只掃附加區（§6）。小、獨立、立刻有感。
2. 二分 raw-view 在合併卡上壞掉的原因（需要寫卡、重開機；見對話紀錄 2026-10-03）。
3. 在相機上證明 §3 前提 1（CSV 改指／取檔表）——它決定 `add_option` 能不能不靠逐檔 hook。
4. 取檔跳板 + raw-view 改用它（raw-view 是取檔 hook 的唯一使用者，改動面最小）。
5. `add_row`，Lossless 改用。
6. `add_option`（不含 QS），Sensor Lab 240 先用；再 OG（含 QS）。
7. OG 核心合一（OG3K + OG2K 同卡）另案評估。
