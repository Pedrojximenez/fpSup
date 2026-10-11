# fp 上游追查：IGAMMA／RGBLMAT／PSTIGAM／GAM 控制

2026-09-24，Ver.5.02 離線研究。只讀既有反編譯與韌體分段，沒有操作相機。`[C]` 是程式／靜態二進位直接證據；`[I]` 是推論；`[?]` 是尚未確認的硬體行為。以下 `blk_cXX.c` 均在 `/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/`。

## 結論

這一段**尚未找到可證明「像素先被夾成 0…2047，才進 2048 點 tone LUT」的控制或運算**。2048 個表項證明的是表長度；沒有證明輸入像素位深、索引縮放、插值與超範圍規則。[C／?]

但本輪釐清兩個直接影響下一版修復設計的地方：

1. **RGBLMAT `+0x34` 跟矩陣係數超範圍後的縮半旗標相連。** 這是係數範圍／尺度 fallback；不能把它當作已找到的 pixel clip 開關。[C]
2. **原生 Q10 衰減只縮第一組矩陣的 3 個欄位，以及第二組的全部 9 個欄位。** 第一組另 6 個交叉項保持原值，因此目前不能保證此控制等價於全部 RGB 像素等比縮小。[C／?]

IGAMMA 與 PSTIGAM 的預設分段數列皆嚴格遞增，且尾端值不同。沒有靜態 plateau 證據；先前把所有這些預設概括為「identity／關閉」也不夠精確。[C]

## 1. 地址及觀察範圍

映射依據是 `FUN_c019c810` 的 descriptor 建構，而非單靠 MMIO 排序猜像素順序。直接見 [blk_c01.c:84657](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:84657)。

| 區塊 | Shadow | MMIO | 涵蓋內容 |
|---|---|---|---|
| IGAMMA | `30210C70..CAC` | `30115000..3C` | 三個控制參數與 27 個分段值 |
| RGBLMAT | `30210CB0..CE4` | `30115100..34` | 兩組係數、兩個共用欄位、尺度旗標 |
| RGBLMAT 其餘 | `30210CEC..D14` | `3011513C..64` | 一個被清零／保存的 bit，及另 13 個初始化欄位 |
| PSTIGAM | `30210D18..D4C` | `30115200..34` | 27 個分段值 |
| GAM_GS/GAMDEC | `30210D50/D54`、`30210D58..DD8` | `30115804/08`、`30115820..A0` | 兩個編碼控制與周邊參數 |
| GAM_BAS | `30210DDC..E60` | `30115900..84` | 共 64 個資料欄位；另有一個上層模式欄位 |

目前不能只因 IGAMMA 名稱或地址在前，就宣稱它的 27 個值是特定已知單位的像素輸入／輸出。也不能以 RGBLMAT signed 係數推論負像素可往後保留。

## 2. RGBLMAT `+0x34` 的尺度 fallback 已追通

`FUN_c02cf938` 接收兩組 9 個 signed 16-bit 係數；重排進 18 個 signed integer 後，以每組三項為一列检查：

```text
若任一列的第 1 項 >= 1024，
或第 2／3 項 < -511：
    flag = 1
    全部 18 項各除以 2，向 0 截整
否則維持係數與呼叫者提供的 flag
```

來源：[blk_c02.c:131147](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:131147)。ARM 指令已獨立核對：`c02cf9bc cmp #0x400; bge`，負閾值實際建為 `-511`，`c02cfa00 add ... lsr #31; asr #1` 確認除 2 是向零截整。[C]

完整传遞鏈：

1. `FUN_c02cfcf0` 在換矩陣分支令 `local_48=0`，呼叫 `FUN_c02cf938(...,&local_48)`，將結果寫 `param_2[0x14]`，即矩陣結構 `+0x50`。[blk_c02.c:131445](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:131445)
2. `FUN_c032eea8` 將整個 `0x58` bytes 結構複製到 matrix singleton 的指定 context。[blk_c03.c:30654](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:30654)
3. `FUN_c032efa8` 複製結構並處理額外增益，最後呼叫 `FUN_c01076c0`。[blk_c03.c:30719](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:30719)
4. `FUN_c01076c0` 將結構 `+0x50` 寫入 shadow `30210CE4`，descriptor 映射至 MMIO **`30115134`**。[blk_c01.c:3695](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:3695)

因此最有根據的命名是 **matrix coefficient scale fallback flag**。[C] 它很可能通知硬體補償被除以 2 的係數，例如更改固定小數尺度或結果倍增。[I] 目前沒有硬體規格／像素觀測來區分這些做法，**不能把 `flag=1` 等同於已證實增加一檔 pixel headroom**。[?]

同一 setter 的 `30115130` 低／高 16 bits 來自結構 `+0x48/+0x4C`；初始化 `FUN_c011a6d0` 都設 0，runtime common PQ matrix builder 也呼叫此初始化。[blk_c01.c:13056](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:13056)、[blk_c06.c:121190](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c06.c:121190)。未找到足夠依據把這兩項命名為 black clamp、negative clip 或 pixel maximum。

## 3. 原生 Q10 衰減：確定是選擇性縮放，不是 18 項全縮

`FUN_c032efa8` 將 `singleton+0xB0/+0xB4` 的 gain 上限夾到 `0x400`。小於 `0x400` 時，用 `(gain × magnitude + 0x200) >> 10` 縮小指定係數；若其 11-bit 編碼大於 `0x400`，以 `0x800-code` 處理負係數的量值，再轉回編碼。這些都是**參數運算**。[C]

係數 index 以 `FUN_c0107490`／`FUN_c0107608` 的輸入結構為準，從 0 起算：

| 群組 | 被 Q10 縮放的 index | 對應係數 MMIO | 未縮放的 index |
|---|---|---|---|
| 第 1 組 | **0、3、6** | `30115100`、`30115108`、`30115110` | **1、2、4、5、7、8**，在 `30115104/0C/14` 的成對欄位 |
| 第 2 組 | **9…17 全部** | `30115118..2C` | 無 |
| 控制 | `+0x48/+0x4C/+0x50` 不被這段 Q10 運算更改 | `30115130/34` | 維持已選矩陣結構內容 |

直接來源：[blk_c03.c:30719](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:30719)；packed address 來源：[blk_c01.c:3617](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:3617)、[blk_c01.c:3675](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:3675)。

第一組 identity 的三個 `0x200` 正好在 0、3、6，其餘欄位 0。這也表示它不是一般 row-major 對角線位置的係數序列；對硬體完整方程式尚未確認之前，不能把 18 個欄位直接套成兩次一般 3×3 矩陣相乘。[C／?]

所以原生衰減仍是值得測的前段控制，但需要用灰階與 R/G/B/C/M/Y 梯度驗證其實際作用；只看灰階變暗不夠。無法由這段程式推論它會保留所有色相或救回已被夾成 0 的負值通道。

三個 PQ 家族矩陣 wrapper 都經由此 singleton：`FUN_c02bfb28`、`FUN_c02c20b8`、`FUN_c02c3120`；可直接查已辨認的寫入呼叫點 [blk_c02.c:120391](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:120391)、[blk_c02.c:121925](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:121925)、[blk_c02.c:122611](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:122611)。這仍不等於已證實 display-only。

## 4. IGAMMA／PSTIGAM 預設：無 plateau，但不是已證 identity

`FUN_c0107208` 原樣打包三個控制參數：

```text
30115000 = control[0] | control[1] << 16
30115004 = control[2]
```

`DAT_c2f0c008` 靜態值與 `FUN_c011a5e0` runtime 回填一致，均為 `[0xFFF, 1, 0xFFF]`，所以已知預設 packed value 為 `00010FFF`、`00000FFF`。[C]

**這是上游 range 調查應優先記錄的控制對，但不能僅憑 `0xFFF` 就宣稱它們是像素高限。** Setter 沒有做 per-pixel 運算，也未揭露欄位語意。[?]

IGAMMA 27 值由 `FUN_c0107250` 寫 `30115008..3C`，PSTIGAM 27 值由 `FUN_c0107708` 寫 `30115200..34`。

| index | IGAMMA `C2F0C014` | PSTIGAM `C2F0C0D8` |
|---|---:|---:|
| 0…19 | 128,256,384,512,640,768,896,1024,1280,1536,1792,2048,2304,2560,2816,3072,3328,3584,3840,3968 | 同左 |
| 20 | 4096 | 4096 |
| 21 | 4226 (`1082`) | 4608 (`1200`) |
| 22 | 4436 (`1154`) | 5120 (`1400`) |
| 23 | 4608 (`1200`) | 5632 (`1600`) |
| 24 | 4778 (`12AA`) | 6144 (`1800`) |
| 25 | 4948 (`1354`) | 7168 (`1C00`) |
| 26 | 5120 (`1400`) | 8192 (`2000`) |

來源：[blk_c01.c:13010](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:13010)、[blk_c01.c:13046](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:13046)，並直接解碼 `out/seg1_c2ef6e00.bin`。完整數列／來源 SHA256 在 `matrix-gamma-static-data.json`。

兩列數值均嚴格增加，没有平頂。[C] 但未知每點橫座標和硬體如何處理超端點，不能據此保證全輸入域不截斷，也不能把尾端的差異直接換算曝光檔數。[?]

啟動初始化 `FUN_c01191B8`、`FUN_c01191F8`、`FUN_c0119280` 複製這些資料至 shadow。Runtime `PictureQualityCommonPrePst__v44/__v45/__v46` 也可覆寫同一內容；它們受 `param_2+0x11C` 或資源列的 `+5` byte 控制。三個 PQ 資源根的 id `0x2B/0x2C/0x2D` 兩個 byte 都是 0，因此一般非強制更新不應假定會逐次重寫；強制分支仍會回填。[C]

來源：[blk_c01.c:11920](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:11920)、[blk_c06.c:120109](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c06.c:120109)。

## 5. GAM_GS/GAMDEC 有兩組編碼控制；未證明它們是 input clip

`FUN_c0107b28` 取 4 個 bytes；第 1／3 個只保留 7 bits。`FUN_c0107d18` 將每組 `(a,b)` 打包到 `30115804`／`30115808` 的低 28 bits，同時保留原 top nibble：[C]

```text
if b == 0: e = 0; m = 0
else:      e = (b >> 6) + 1; m = 63 - (b & 63)
reg = (reg & 0xF0000000) | a | ((m & 0x7F) << 14) | (e << 24)
```

這是一個含縮放／指數狀態的編碼候選；**不能把它當作把 pixel 右移幾 bits 的已證公式**，也不能由 7-bit 的 `a` 範圍推論像素位深。[I／?]

來源：[blk_c01.c:3799](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:3799)、[blk_c01.c:3859](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:3859)。其完整初始化資料 `C2F13094` 有 36 個 uint32：index 0 和 3 是 `0x40`，其他全為 0。預設 `30115804=30115808=0x40`，周圍資料為 0。[C]

在 PQ 資源根 `C0B38ACC`，`+0x108` 指向 `C0B39134`，唯一一列的選擇門檻為 100，資料 bytes 恰為 `[64,0,64,0]`。`FUN_c0695848` 依 `param_2+0xFC` 選該列；`PictureQualityCommonPrePst__v53` → `FUN_c0100DD0` → `FUN_c0107B28` → `FUN_c0107D18` 將其下發。[C]

另外兩個資源根 `C0B3EFDC`、`C0B3F83C` 的對應欄位指向 RAM `C3424EE4`、`C342528C`；initializer 從同一基底資源複製兩個 words，所以初始化來源相同，不能據此說 runtime RAM 永遠相同。直接來源：[blk_c02.c:136210](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:136210)，另一根在 `FUN_c02d7000` 同型複製。[C]

GAMDEC 其餘欄位由 `FUN_c0107B70` 打包；`FUN_c0101578/FUN_c01015D0` 負責 `30115864..A0` 一帶的附加初始化。其中沒有找到可定名為高／低像素限幅的運算。後兩者的預設來源是 runtime/BSS `C31D7444`、`C31D74F4`，不能拿檔案外不存在的 bytes 假造 live 值。

## 6. GAM_BAS：已知資料預設為零，不能只憑零解讀 bypass

`FUN_c011a6e8` 產生 65 個 words，word 0 是 1，word 1…64 全為 0；與靜態 `C2F13124` 一致。[C]

`FUN_c0107df0` 將 word 0 寫入另一個全域控制 shadow `30210014` 的 bits 12…13；將其他 64 個欄位打包到 `30115900..84`。因此「整個 GAM_BAS 全零」不完整：有一個另外位置的 mode=1。[C]

Runtime `PictureQualityCommonPrePst__v55` 可重新寫入，但三個 PQ 資源的 id `0x34` 為 enable byte 1、update byte 0，需要實際狀態才能判定何時生效。資料全零可能代表基底／殘差為 0，不能直接當作已證 identity 或 bypass。[?]

來源：[blk_c01.c:3896](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:3896)、[blk_c01.c:13068](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:13068)、[blk_c06.c:120348](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c06.c:120348)。

## 7. 要如何從這裡繼續判定 clip

本區目前可證明的限制是**係數／控制參數範圍及曲線採樣值**，還不是第一次 per-pixel 資訊損失的位置。需要的最小補證是：

- 記錄問題重現時的 active IGAMMA 三控制值／27 knots、兩組矩陣／尺度旗標、PSTIGAM 27 knots、GAM 兩組編碼值及 GAM_BAS mode。不能拿 ROM defaults 當 active 寄存器。
- 若進行原生 headroom 對照，必須保存全部 18 係數 before/after，連同 `30115134`；不只記一個 gain number。
- 至少用純灰與 6 種飽和色的漸層，同時看 RAW 未飽和範圍與預覽差異。矩陣縮放後僅灰階恢復，不能證明負值色域裁切已解決。
- 若要主張輸入被夾至 11 bits，需要找到硬體索引方程式或直接的輸入／輸出對照。單用 2048 entries 與 13-bit LUT 值，無法決定輸入域寬度。

以上是待實作的觀察設計，並非本輪已做的實機量測。

## 可重核附件

- `matrix-gamma-static-data.json`：六组 defaults、三個 PQ 根的指定 flags／參數列、兩個韌體分段的 SHA256。
- `extract_matrix_gamma.py`：僅用 Python 標準庫，讀 `--project-root` 內的 seg0／seg1，以 `--output` 指定 JSON 輸出目錄。
- `matrix-scale-fallback.disasm.txt`：`FUN_c02cf938` ARM 指令，核對有號門檻與除 2 截整方式。

本報告沒有把 `&0x7FF`／`&0x1FFF` 當像素裁切證據，也沒有提出可直接部署的 MMIO patch。
