# 原生設定列、共用字串池、與 OG 共存（fpLossless，2026-09-30～10-01）

Ver.5.02（w71c1）。證據等級：**[實機]** 相機上量到、**[離線]** 反組譯／模擬、**[推論]** 沒驗過。
操作面的濃縮版在 skill `fp-native-ui` §8；這份是完整紀錄與理由。

程式：`fpSup/lossless/native/menu_page.c`（安裝）、`fpSup/lossless/menu/build_menu_candidate.py`
（產生頁面）、`menu/pack_menu_file.py`（打包）、`fpSup/uishare/ui_pool.c`（共用字串池）、
`projects/open-gate/build/og3k_ui.S`（OG 的字串 hook）。進度紀錄：
`projects/lossless-sup/notes/PROGRESS_20260930.md` §18–§19c、`PROGRESS_20261001.md`。

---

## 0. 結果一覽

| 項目 | 狀態 |
|---|---|
| SHOOT 第 2 頁（CINE）「音訊記錄」下面多一列 `Lossless RAW 關閉/開啟` | [實機] 正常，游標、切頁、popup 都對 |
| 值只在記憶體，每次開機為關閉，不寫設定區 | [實機] |
| popup 沒有「› 更多選項」、「開啟 ›」沒有箭頭 | [實機] |
| 選單資料併進 fpSup.BIN（不再有 FPLMENU.BIN） | [實機] |
| 私有字串走共用字串池（FSPL） | [實機] 18 個引用全部解析正確 |
| 與 OG3K 合併，兩邊選單／QS 都正常 | [實機]（卡 s／t／ac） |
| 與 OG2K 合併 | [離線] 建出來、模擬開機正常；**未上機** |
| 與 Sensor Lab 合併 | [離線] 有衝突（§7） |

---

## 1. 為什麼要整頁換掉，而且不用 hook

設定頁（MainB2 這類）的 NBU **每次顯示時重新解析**：UI 資源快取一次只留一頁，打開選單就丟掉，
顯示時由 `C05E82F1` 找名字相符的執行期項目，`reader+04 = entry+08`，再從 `reader+24 + 位移`
讀記錄，字串以 `reader+14` 為基底。[實機]

所以只要在開機時：
1. 把自己的頁面放在永不釋放的記憶體；
2. 把 MainB2 執行期項目的 `+08` 改成 `(自己的頁 − C18C0460) mod 2^32`；

下一次顯示就讀自己的頁。不用 hook，也不用重開 UI。動手前逐項比對原廠值（字串池、長度、NBU 基底、
項目位移 `0x76FF04`），任何一項不符就整個不寫。[實機]

執行期結構（位址每次開機不同）：

```
[C37B7048]            = UI app（C055F0F0 的 GUI 物件 +0）
app+7C 畫面 vector     : +4 數量（221）、+10 陣列；screen +04 app、+08 名字、+0C 快取 root、+24 共用 reader
reader（所有頁共用一個）: +04 游標、+10 字串池長度 176152、+14 字串池 C18C0474、+20 NBU 總長、
                        +24 NBU 基底 C18C0460、+A8/+AC 44-byte 執行期項目（+04 名字、+08 頁面位移、+18 arena）
app+888 → +60          = app 變數 registry
```

## 2. donor 列：只能用同一頁的列 [實機二分]

四張只換頁面的卡（頁面補零到等長；parser 遇到 `FFFFFFFF/8` 就停）：

| 變體 | 結果 |
|---|---|
| 原廠 MainB2 從自己的 RAM 載入 | 正常 → 換頁機制本身沒問題 |
| 原廠頁 + 擴充的配置標頭 `0x10002` | 正常 → 附加 budget 沒問題 |
| MainY4 的兩選項列（CINE 也設成隱藏） | 第一次切過去空白，再切一次看得到但游標卡死；GUI log 每次 `0xC055F8D4 ERR 10000009,4` |
| 同上但綁回原廠變數 | 一樣壞 → 跟私有變數無關 |
| **同頁「音訊記錄」列（B2_6）的複製** | **正常** |

別頁的列搬過來，就算隱藏也會讓整頁壞掉。離線結構檢查全過，原因未追。[實機]

## 3. 複製來的列要改的東西 [實機]

| 原本 | 作用 | 改成 |
|---|---|---|
| `MV_AudioRecord` | 值 | `MV_fpLossless` |
| `SUB_MV_AudioRecord` | popup 暫存值 | `SUB_MV_fpLossless` |
| `EXCL_AudioRecord` | 錄音停用時鎖住、反灰 | `EXCL_fpLossless`（永遠 0） |
| JumpEvent sync-request `B2_6` | 選開啟時跳到音訊子選單 | `xxx`（原廠另一個分支就拿它當 no-op） |
| 標題 drawText `0326_C`＋文字動畫 `0326_C`/`0326_CI` | 標題 | 字面 `Lossless RAW`（resolver flag 0） |
| List 值==1 → `Footer` 區段 `Footer02` | 底部「› 更多選項」 | `Footer05`（值 0 用的那個），記錄 `0x204ED01+45` |
| Cursor02 drawImage 的可見性動畫 key@66 = 1 | 「開啟 ›」的箭頭 | 0，記錄 `0x204F4CC+64` |

- 後兩項是 `build_menu_candidate.py` 的 `word_writes`：指定記錄、指定字，改寫後重新驗證。
- **popup 的「關閉／開啟」文字不是 CSV 來的**，是 ListItem 子物件的 drawText（`0080`/`0081`）。
  `B2_6.cvm`（`1,0080,xxx` / `2,0081,B2_6`）跟原廠錄音列共用，不要動。
- 值：0 = 關閉、1 = 開啟。收合摘要也用 `0080/0081`，會跟著語言顯示。

## 4. 私有 app 變數 [實機]

- 三個變數都要**先註冊**：`C05DB309`（Thumb），參數 `app, 數量, {type 0, 名字指標, 0}*`。
- registry **借用**名字指標，所以名字要放在永不釋放的記憶體。卡上程式沒有 `.rodata`，名字是用字
  一個一個拼出來的（`menu_page.c` 的 `NAME_WORDS`）。
- 從 loader 的 task 註冊，實機沒問題。值讀 descriptor `+08`；錄影入口用 `fpl_menu_on()`，值為 1 才走 lossless。

## 5. 上卡：選單資料併進 fpSup.BIN [實機]

loader 讀 fpSup.BIN 最多 `MAXLEN 0xF000`，所以選單資料接在 0xF000 之後，loader 看不到、不影響它：

```
fpSup.BIN:  [0, 0xF000)   loader 的部分（VBIN），補零到剛好 0xF000
            [0xF000, …)   "FPLM" v2 區塊，補零到 0x30000
FPLM v2（little-endian 字）:
  +00 "FPLM"  +04 版本 2  +08 頁面長度  +0C 私有字串長度
  +10 引用數  +14 原廠 MainB2 頁位移 0x76FF04  +18 FNV-1a(頁面+字串+引用)  +1C 0
  +20 頁面，接著私有字串（NUL 結尾），接著每個引用一組 {頁面位移, 字串位移}
```

- 開機時用 loader 同一組檔案 API（`C0365E90/FB0/6060/6020/5ED0`，volume 1 = SD）**同一個 handle 讀兩次**：
  第一次讀 0xF000 bytes 跳過 loader 的部分，第二次讀選單區塊。第二次如果沒有接著讀，magic 就對不上，什麼都不裝。
- 引用由 builder 的 manifest 產生，打包時逐一和頁面比對，多一個字或少一個字都拒絕。
- `putfile` 不會截短檔案，所以固定補零到同樣大小，讀的一方只看標頭宣告的長度。
- 安裝結果碼（`menu.result`）：1 已安裝、2 沒有 GUI、3 沒有 MainB2 畫面、4 reader 不是原廠、
  5 沒有 MainB2 項目、6 空間不夠、7 讀不到檔、8 格式／校驗不符、9 註冊失敗、10 變數不能用、11 共用字串池拒絕。
- 任何一步失敗都不改 UI，錄影一律原廠（`fpl_menu_on()` 為 0）。

## 6. 共用字串池（FSPL）[實機]

**問題**：lossless 原本把 `reader+14/+10` 換成自己的字串池副本，但 OG3K 的字串 hook（`C05E5B58`）
只在字串池是原廠那一份時才生效，兩者一起裝 OG 的選單就壞掉。

**做法是一個約定，不是整合器**（`fpSup/uishare`，見其 README）：

- 每個 sup 在自己的入口用 `uis_intern(s, n, &offset)` 取得字串位移。字串已經在池裡（原廠的或別的 sup 加的），
  就回傳那個位移；沒有就附加。
- 第一次附加時把原廠字串池整份複製一次（多 16 KiB 空間、永不釋放），前面 16 bytes 是標頭，並把 reader 換過去：

  | 位置 | 內容 |
  |---|---|
  | −16 | `"FSPL"` |
  | −12 | 版本 1 |
  | −8 | 容量 |
  | −4 | 0 |

  `reader+0x10` 永遠是目前使用的長度。之後的 sup 直接往後附加，原廠位移的意義不變。
- 誰也不事先佔位移：lossless 的頁面在載入時才把拿到的位移寫進 18 個欄位。
- 相機上量到：容量 0x2F02D、長度 176,241（原廠 + 89 B）；`xxx` 和 `Footer05` 直接沿用原廠位移（0x2A5C4、0x12BC4）。
- 測試：`fpSup/uishare/test_ui_pool.py` 15 個、8 個突變；`menu_page` 26 個、15 個突變。

## 7. 與 OG 共存

- **OG3K / OG2K 的字串 hook 改成接受兩種池**（`og3k_ui.S` 的 ui_string）：原廠池，或前 16 bytes 是
  FSPL 版本 1 標頭的池（檢查對齊、ip>16、`ip-16` 是 magic、`ip-12` 是 1）。其他一律交給原廠的
  `C05E5B58`。測試：`projects/open-gate/build/test_og3k_ui_string.py` 7 個、5 個突變。
- 合併卡用 `fpSup/lossless/build_card.py --og og3k|og2k`，從 OG 自己的發行建置取出全部固定段落與入口，
  入口由 build_autorun 的跳板依序呼叫（lossless 先、OG 後），與 USB shell 有無無關。
  兩者的段落互不重疊（已逐段檢查）。
- [實機] OG3K + lossless：OG3K 的選單、QS、lossless 的列都正常。
- **已發行的 OG（OG3K ≤ 0.2.7a、OG2K ≤ 0.1.4a）只接受原廠池**，不能和會附加字串的 sup 合併。
  要合併就得用目前原始碼建的 OG，或等 OG 出新版。
- **Sensor Lab**：原地重建 B2_5，和 OG 的原地修改相衝；跟 lossless 沒有段落或 UI hook 重疊。
  計畫中的 `add_option` 會取代這種原地修改。

## 8. 觀察：OG3K 卡的回放比例（未解，不是 lossless 造成）

- 解析度設在 FHD 時，播 OG3K 影片看起來被壓扁；設在 OG3K 時，播 FHD 影片看起來被拉長。[實機]
- 切到 OG3K 之後 OG3K 影片正常，**再切回 FHD 仍然正常**，所以不只是單純跟著目前的選項。[實機]
- 換成完全沒有回放 hook 的卡（z）一樣，所以是 OG3K 本身的顯示行為。[實機]
- 待查：OG3K 版本說明提到「顯示跟著選項走」，比較可能是某個狀態只在切換時更新。[推論]

## 9. UI 共用的後續

- 計畫：`fpSup/uishare/PLAN.md`（`add_row`、`hide_row`、`add_option`、`set_option_enabled`、私有圖示）。
- 每個 sup 目前改了什麼：`research/ui/UI_SERVICE_INVENTORY.md`。
- 要先在相機上證明的三個機制：CSV 轉向（NBR 目錄在 heap 上的副本是否有效）、子頁轉向（B2_5 等走執行期項目）、
  QS（共用、可串接的記錄 hook 加上重新解析觸發）。

## 10. 未解問題

- 為什麼別頁的列（MainY4）搬進 MainB2 會讓整頁壞掉（GUI `ERR 10000009,4`）。
- OG3K 回放比例的觸發條件（§8）。
- OG2K + lossless 未上機。
