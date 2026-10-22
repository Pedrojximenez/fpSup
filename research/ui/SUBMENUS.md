# 按右鍵進子選單 —— 是怎麼做到的

2026-09-29,全部離線。`python3 research/ui/tools/nbr_stock.py submenus`

## 短答

**在 CSV 的 `Popup` 欄寫目的地的頁面名字。** 那一欄只有三種內容:

| 內容 | 意思 |
|---|---|
| `Popup` | 普通的值彈出清單,就地展開 |
| `zzz` / `xx` / `xxx` / `xxxxx` | 沒有東西(佔位) |
| **一個頁面名**(`B3_1`、`B2_6_1`、`SetupHelpMenu`…) | **按右鍵跳到那一頁** |

全機有 **123 列**會跳,通往 **33 個目的地**。

但光寫 CSV 不夠 —— 還有兩個條件,下面講。

## 目的地必須真的存在,而且要存在兩張表裡

33 個目的地中有 31 個**同時**是:

- **GUI 頁**:`0xC0D0DB68` 那張 196 筆的 `{名字, page id}` 表(`B2_6` = 37、`B2_6_1` = 38、`SetupHelpMenu` = 162)
- **NBU 資源集**:221 筆索引裡的一筆(`uinav.py sets <名字>`)

兩個例外,都值得知道:

- **`B5_7`** 本身兩張表都沒有。真正的頁是 **`B5_7S` 與 `B5_7C`**(STILL / CINE 各一份,
  page id 都是 160)。CSV 寫的是**基底名,韌體自己接模式後綴** ——
  資源那邊也對得上:`ListMenu/B5_7_STILL.cvm` 與 `B5_7_CINE.cvm` 兩個檔。
- **`B2_2_1`** 只存在於字串池,不是頁也不是資源集。那大概是頁內的錨點而不是一頁,
  或者根本是條死路。**沒驗證過,別拿它當範例。**

所以:**你只能跳到已經存在的頁。** 要做一頁新的,是另一個量級的工作
(新的資源集 + page id + 處理器),不是改 CSV 能解決的。

## 列本身也要是「會跳的那一種」

字串池裡的 widget 類別名說得很清楚:

| 類別 | 行為 |
|---|---|
| `MenuItem_Select` | 只選值,**不跳** |
| `MenuItem_Jump`(`_R`、`_Y`) | **只跳**,不顯示值 |
| `MenuItem_SelectJump`(`_R`、`_Y`、`_4`、`_10`、`_4_and_Under`、`_10_and_Over`) | 顯示值**而且**會跳 |

`_R` / `_Y` 對應 MainR\* / MainY\* 那兩個頁籤家族;`_4` / `_10` 是清單長度的版面變體。
每一個都是自己的一個 **NBU 資源集**(共用模板,`MenuItem_SelectJump` 就是 221 筆索引的第 0 筆)。

跳的動作本身叫 **`JumpEvent`**(另有 `JumpEventCINE` / `JumpEventSTILL` 給分模式用)。
記錄裡的分布:`JumpEvent` 出現 99 次,`MenuItem_Jump` 116 次、`MenuItem_SelectJump` 28 次,
**絕大多數在 tag `0x10003`(物件記錄)** —— 也就是說「這一列是哪種 widget」寫在物件記錄裡,
不在 CSV 裡。

這正好對上 fpLossless 的 donor 筆記:那個 donor
「是 `MenuItem_Select`(19459),**不是** `MenuItem_SelectJump`,而且沒有 JumpEvent」——
所以那個 donor 做出來的列**不會跳**,要跳就得換 donor。

## 所以要做一列會跳的,要三件事

1. **CSV**:`Popup` 欄填目的地頁面名(改 8 bytes 就能換整個 CSV,見
   [`RESOURCE_REPLACEMENT.md`](RESOURCE_REPLACEMENT.md))。
2. **物件記錄**:那一列的物件要是 `MenuItem_Jump` / `MenuItem_SelectJump` 類,並帶 `JumpEvent`。
   這在 NBU 那一側(tag `0x10003` + 伴隨屬性),要挑一個**本來就會跳的 donor** 來改嫁。
3. **目的地頁要已經存在**(兩張表都要有)。

第 1 項是資料、很便宜;第 2 項是目前整條路最貴的部分;第 3 項基本上是個限制條件。

## 還沒解的

- `JumpEvent` 記錄裡目的地到底存在哪個欄位(`0x10009` 的六個 u32 + 動畫鍵已經知道排列,
  但鍵的內容還沒逐欄解)。
- `B2_2_1` 那條路到底是什麼。
- **全部離線,一項都沒有在相機上驗證過。**
