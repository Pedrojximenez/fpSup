# Quick Set(QS)選單

2026-09-29,全部離線,對著釘住的 `out/seg0_c0000000.bin`。
工具:[`tools/nbu_probe/nbu_format.py`](tools/nbu_probe/nbu_format.py)、
[`tools/nbr_stock.py`](tools/nbr_stock.py)。

```
python3 research/ui/tools/nbu_probe/nbu_format.py group 20_MV_Resolution
python3 research/ui/tools/nbr_stock.py list --ext xci qs_
```

## 一句話

**QS 跟 MENU 不是同一種東西。** 選單列是 CSV(`.cvm`,換一個 8 bytes 就好);
**QS 完全沒有 CSV** —— 它整個活在 NBU 記錄裡,而且同一個東西被複製了很多份。

## 四個 QS 資源集

| 資源集 | 位址 | 記錄數 |
|---|---|---|
| `QS_CINE` | `0xC2278C02` | 14,285 |
| `QS_Common` | `0xC239C5FB` | — |
| `QS_STILL` | `0xC23E1F9C` | — |
| `QS_STILLlike` | `0xC24D1DC8` | — |

⚠️ **訂正一個既有說法。** FP3K 的交接筆記寫「QS footer 記錄 `C2278C02`/`C24D1DC8` 需要
第三格 700 與加寬的游標範圍;長得很像的 `C23E1F9C` 屬於靜態照片控制,不要動」。
那三個位址**不是單一記錄,是整個資源集的起點** —— `QS_CINE`、`QS_STILLlike`、`QS_STILL`。
他的結論(動前兩個、別動第三個)方向仍然成立,但尺度差了四個數量級:
`QS_CINE` 一個人就有 14,285 筆記錄。

## 圖磚長什麼樣

QS 沒有 `.cvm`,但有 **172 個 `qs_*.xci` 圖示**(`nbr_stock.py list --ext xci qs_`)。
一格圖磚是「標籤底板 + 值圖示」:

```
menu_cine_format_qs.xci      150x74   FORMAT 底板
font_menu_MB_format_1.xci    150x38     文字行
qs_formatQuality_3_S.xci      86x49     值圖示
```

值圖示的編號跟著 widget 的狀態走,但序列化的形式是**動畫曲線**,不是索引陣列
(見 [`README.md`](README.md) §3)。

## 狀態就在 tag `0x1000B` 裡,而且已經解出來了

`0x1000B` 是 case 10,全 UI 有 **11,383 筆,全部逐欄解得開、一個位元組不剩**:

```
u32 nA, u32 nB, u32 nC, u32 群組名, u32 owner
nA x { u32 資源名, u32 a, u32 b, u32 c, u32 d, u8 e }   ← 一個 UI 狀態一筆
nB x { u32 名字, u32 值, u8 旗標, u32 額外(旗標為真時) }
nC x { u32, u32 }
u32 名字2、u32 尾碼
```

解析度那兩個群組(`20_MV_Resolution`、`21_MV_Resolution`)每一筆都是
`nA = 1`、`b = 33`。**33 就是 README §3 說的「兩狀態曲線的終點」——
第三個狀態要 66。** 現在那個數字有名字、有位址、可以直接改。

## 這是為什麼 QS 的工作量大

「解析度多一個狀態」要碰的記錄,全樹掃出來是 **218 筆**:

| 資源集 | 筆數 | 是什麼 |
|---|---|---|
| `QS_CINE` | **68** | QS 錄影頁 |
| `QS_STILLlike` | **68** | QS 靜態-like 頁 |
| `Y2_3SLike` | 24 | live view 資訊列 |
| `QS_Common` | 16 | QS 共用 |
| `Y2_3C` | 16 | live view 資訊列 |
| `Y2_3C_ShutterAngle` | 16 | 同上(快門角度版) |
| `B2_5` | 6 | **Settings 那一頁** |
| `CropZoomButtonMenu` | 4 | 裁切/放大按鈕選單 |

按 tag 分:`0x10009` 短屬性 104、`0x10006` 屬性 69、`0x1000B` 群組 37、`0x10003` 物件 8。

**218 筆裡有 152 筆在 QS 的三個集合裡 —— Settings 那邊只有 6 筆。**
換句話說:選單那一列很便宜(一個 CSV),**QS 才是九成的工作**。
而且 `QS_CINE` 裡同一個群組出現 **8 次** —— 那就是 og3k 筆記講的
「非當前 screen/style variants 尚未回歸」:每個版面變體各有一份,改一份只修好一個畫面。

## 和選單那條路的分工

| | MENU 列 | QS 圖磚 |
|---|---|---|
| 資料在哪 | `.cvm` CSV,NBR 目錄裡的一筆 | NBU 記錄,散在 4 個資源集 |
| 換法 | 寫新 CSV + **8 bytes 改指標** | 改記錄本體(見 `nbu_probe/README.md`) |
| 文字 | `TEXT` 欄,可以直接寫字面文字 | 圖示 `.xci`,要畫 |
| 灰掉 | `Enabled/Enabled2 = 0,0`(資料) | 未解 |
| 要碰幾筆 | 1 | **152** |

## 沒解的

- `nB`(額外項)與 `nC`(成對的 id)各自的語意;`a`/`c`/`d`/`e` 只知道 `b` 是終點時間。
- QS 的灰掉機制(選單那邊是 `Enabled` 欄;QS 沒有對應的資料欄)。
- `QS_STILL` 與 `QS_STILLlike` 的分工。
- **全部離線。** 這裡沒有任何一項在相機上驗證過。
