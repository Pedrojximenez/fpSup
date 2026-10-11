# RAW 前端、白平衡與 knee：上游截斷稽核

2026-09-24。離線限定；未連相機、未改韌體。`[C]` 是程式／ROM 直接事實，`[I]` 是推論，`[?]` 尚未證明。反編譯來源均在 `/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/`。

## 結果與訂正

**前端有多組增益、偏移與非線性處理控制，但本次沒有找到能單憑軟體確認「現在 live 的某級正在把像素剪平」的證據。** 主要進展是排除容易誤認的 clipping、找出應加入下次同步快照的範圍，及修正 TBLSD / RAWBLT 名稱。

1. **`0x30112740/44` 是 SIG0 TBLSD 區塊的 gain，不能再稱 RAWBLT gain。** 原報告的增益分流計算仍成立，區塊名稱需要訂正。
2. **SIG0 / SIG1 RAWOUT 的 `0x1FFF0000` 是空間輸出範圍線索，不能當作 8191 像素上限。** 追到實際 caller 使用寬度及 offset，已排除僅由常數推定 intensity clamp 的做法。
3. RWAPKNEE 的預設表確實非等差，但初始化與 common PQ builder 都傳控制值 `0`，setter 會清選擇 bit；有表不代表當前正在啟用此表。
4. 白平衡的 `0xFFF` 明確是四個 **gain 參數**的上限。SIG1 另一個 `0xFFF` 常數則只有單欄位配置證據，沒有完整欄位名稱，不能將兩者混為 pixel saturation。
5. 靜態資訊不能排除 bin/vbin ASIC 中間累加位寬不足、早期飽和或輸出縮位；這要用 binned Bayer 與另一抽頭的同場景值配對。按現有無符號欄位與歸一化解讀，ROM 核沒有必然導致高光 overshoot 的證據；ASIC 的係數 signedness 仍未獨立確認。

## 1. 正確區塊映射

診斷函式 `FUN_c01597B8` 先列標籤，再列位址。ROM 字串 `0xC07D3870` 是 `SIG0＿TBLSD`（全形底線）。以 `FUN_c019C810` descriptor 建構交叉驗證：

| 區塊 | MMIO | Shadow | 來源 |
| --- | --- | --- | --- |
| SIG0 TBLSD | `30112700..BF` | `30210388..447` | `blk_c01.c:49994`、`:84618` |
| SIG0 RAWBLT | `30112800..64` 等 | `30210448..4D0` | `:49997`、`:84619` |
| SIG0 RAWOUT | `301128C0..CC` | `302104D4..4E0` | `:50003`、`:84622` |
| SIG1 WHITE BALANCE | `30113480`、`30113494..A8`、`301134C0..F4` | `30210764`、`30210768..7C`、`30210780..B4` | `:50031`、`:84632` |
| SIG1 RAWOUT | `30113890..98` | `30210998..9A0` | `:50067`、`:84642` |
| PRE_TOP RWAPKNEE | `30114200..44` | `302109E0..A24` | `:50077`、`:84645` |
| PRE_TOP APKNEE | `30114800..3C` | `30210B30..6C` | `:50104`、`:84653` |
| MAT_TOP PSTAPKNEE | `30114C00..1C` | `30210C50..6C` | `:50113`、`:84656` |

這只是 descriptor 對照，不是硬體精確處理順序證明。

## 2. Gain 與 offset：是配置，不是逐像素運算

### TBLSD gain

`FUN_c011DA30` (`blk_c01.c:15393`) 將輸入結構 `+7C/+80/+84/+88` 各自 `&0xFFF`，寫 `302103C8/CC`，即 `30112740/44`。`FUN_c011DA00` (`:15380`) 預設為 `0x100,0x200,0x200,0x100`，初始化 `FUN_c0118570` (`:11404`) 也直接寫相同 packed 值 `02000100,01000200`。[C]

執行期 `FUN_c032EC70` (`blk_c03.c:30558`) 把 Q10 類型增益拆成兩段：較大的部分至少 `0x400`，經右移 2 bits 及綠通道 ×2 後交給 TBLSD setter；小於 unity 的部分交給 RGBLMAT 係數縮放。這個右移是 **gain fixed-point 換算**，不是 Bayer 像素右移。[C]

`PictureQualityCommonSig0Sig1__v3 @ C068F320` (`blk_c06.c:119037`) 在 PQ dirty/force 條件成立時也將 gain 寫回預設。因此 patch 只寫一次可能被原生更新覆蓋。沒有證據把 context `0/1` 直接命名為 LCD / record。[C/?]

### WB gain

`FUN_c0117248` (`blk_c01.c:10635`) 對四個 gain **參數**做上限 `4095`，同時寫 SIG1 `30113494/98` 與 RAWBLT `30112820/24` 的 shadows。`FUN_c032F988` (`blk_c03.c:31189`) 先將每通道 gain × percentage、四捨五入 `/100`，再限制到 `0xFFF`，呼叫前述 setter。[C]

這證明白平衡有倍率並在兩個區塊保存，不證明像素累加結果何時飽和、SIG1 是否所有 live mode 都經過，或 Bayer 檔案是否與此路徑共用。[?]

### Offset 編碼

`FUN_c0104910` (`blk_c01.c:2652`) 將 signed short × `-4`，編成 `&0x7FFF` 的四個 offset；`FUN_c01049B0` (`:2681`) 寫 `30210798/9C`，即 `301134D8/DC`。這是 signed offset 的寄存器表示，**`0x7FFF` 不可當成 pixel ceiling**。[C]

`FUN_c011DAA8` (`:15411`) 另外把四個 15-bit 參數写入 `301134C0/C4`。`FUN_c0118948` (`:11554`) 初始化使用 runtime RAM `C31D7454`；`FUN_c0118A78` (`:11589`) / `FUN_c011A4A8` (`:12913`) 使用 `C31D737C` 供 offset setter。這些 RAM 值不能從 ROM default 推定為實機當前黑位。[C]

RAWBLT ROM 結構 `C2F12A3C` 的 `+38..44` 是四個 `0x7C00`，`+48..54` 是四個 `0x400`。`FUN_c0102DF8` (`:1991`) 將來源 `&0x1FFF <<2`，`FUN_c0102E38` (`:2006`) 寫前一組到 `30112810/14`；`FUN_c0102E80` / `FUN_c0102EE8` (`:2020` / `:2041`) 寫後一組到 `30112818/1C`。同樣是參數與表示法；不能宣稱 13→15-bit pixel pipeline。[C/?]

## 3. RAWOUT：排除 8191 亮度上限的誤判

`FUN_c01187B0` (`blk_c01.c:11464`) 將 SIG0 RAWOUT `301128C0/C4` 初始化為 `0x1FFF0000`；`FUN_c0118D88` (`:11696`) 把 SIG1 `30113894` 寫相同值。只看數字，很容易誤認為 `[0,8191]` intensity clip。

但執行期的 `FUN_c0156AE0` (`:48401`) / `FUN_c0156B90` (`:48428`) 是兩個 packed window setters：

- `FUN_c013CAE8` (`:38340`，關鍵 `:38440..38453`) 依 `param_1[5]/2` 及 `param_1[6]` 設邊界，並在相鄰碼把同些數值放入輸出 descriptor 的寬與 stride。
- `FUN_c0161840` (`:53608`，關鍵 `:54296..54322`) 直接用 `local_3CC` 和輸出 descriptor 寬 `_DAT_C3021CD0` 組成欄位；後續 field 則調整 offset / height。
- `FUN_c01CEF08` (`:119633`，`:119735..119742`) 與 `FUN_c01CFD30` (`:120294`) 還會恢復全範圍預設。

所以至少這些 `0x1FFF0000` 與 `14-bit` 欄位是**空間座標／window 的證據**，不能當作 tone 之前有 13-bit 亮度截斷的證據。[C/I]

## 4. RWAPKNEE：曲線存在與啟用需分開

`FUN_c011A4C8` (`blk_c01.c:12924`) 和 ROM `C2F12E74` 是相同的 33-word 結構：

```text
control = 0
15 values = 03AD 0709 0937 0A17 0AB7 0B37 0BB7 0C37
            0CB7 0D37 0DB7 0E37 0EB7 0F37 0FB7
17 values = 01FF 01AE 01AE 0080 0060 0040 0040 0040
            0040 0040 0040 0040 0040 0040 0040 0040 0020
```

`FUN_c0106628` (`:3228`) 將前 15 值寫入 `30114204..20`，後 17 值寫入 `30114224..44`；根據 control bit0 設定或清除 shadow `30210014` bit7，另外記錄 `C31D7274+context`。[C]

初始化 `FUN_c0118EF8` (`:11756`) 載入 ROM；common PQ `PictureQualityCommonPrePst__v11 @ C068FE28` (`blk_c06.c:119444`) 在 force/dirty 條件成立時呼叫 builder + setter，故這兩條已知路徑的 control 都是 0，setter 走清 bit 分支。[C]

目前沒有從 C 函式找到完整的硬體分段計算公式；兩組值不宜擅自命名成 x / slope，也不能推算 tone-domain 有幾檔 headroom。`30114200` 另有 Bayer phase 類型的 mirror / XOR 調整（例如 `blk_c01.c:35781`、`:66956`），與上述 enable bit 不是同一個欄位。[?]

## 5. APKNEE、PSTAPKNEE 與 SIG1 單欄位

`FUN_c010B490` (`blk_c01.c:5443`) 產生 APKNEE 兩組相同參數；無啟用輸入時每組是 `0,8,0,8,0,8,0,8,4095,4095`；啟用時解包 12-bit 與 4-bit 參數。`FUN_c010B6E8` (`:5523`) 寫 `30114810..34`。[C]

初始化 `FUN_c0119178` (`:11904`) 從 ROM `C2F0BF90` 載入 120 bytes，再呼叫 APKNEE 及 PSTAPKNEE setters。ROM 內兩組 APKNEE 值如上；PSTAPKNEE 的 `+50..6C` 是 `4095,8` 重複四次。`FUN_c010B650` (`:5505`) 寫 `30114C00..10`，並清 `30114C1C`。這些 `4095` 可能是 knee 節點／域端點，但**沒有直接 pixel min/max 運算，不能據此斷言為硬 clip**。[C/?]

SIG1 `FUN_c01065C8` (`:3208`) 將一個 word 寫 `301134A0`；初始化 `FUN_c01188E8` (`:11524`) 從 ROM `C2F0BDE8` 讀得 `0xFFF`。鄰近 `FUN_c01065F8` 寫 `301134A4`，來源 runtime RAM `C31D743C`。在目前全反編譯交叉引用中，兩 setter 都只見初始化 caller。`301134A0=0xFFF` 是下一輪應保存的未知欄位，尚不是已命名的 clip threshold。[C/?]

## 6. bin/vbin 與剩餘驗證

已直接重讀 ROM `C0B5F770/C0B5F7A8`：九個 u16 值為三組 `[1024,2048,1024]` 或 `[256,3584,256]`；每組和 `4096`。對應 u8 三點值 `[16,32,16]` 或 `[4,56,4]` 每組和 `64`。見 `FUN_c032D9A0` (`blk_c03.c:29681`) 消費、`FUN_c0633B30` / `C0633DA0` (`blk_c06.c:45821` / `45928`) 配置。

在係數是線性歸一加權的解讀下，它們是非負凸組合，輸出不應超過輸入最大值。**這是數學條件推論，不是 ASIC 的實測保證**；未查明累加器精度、先 clip 再 scale、黑位處理與輸出 bit packing。詳細 preview route 由同輪獨立報告稽核。

本輪建議新增的同步快照資料為：TBLSD `30112734..44`；RAWBLT `30112800..2C`；SIG1 `30113494..F4`；RWAPKNEE `30114200..44` 加 shadow `30210014` / `C31D7274+context`；APKNEE `30114800..3C`、PSTAPKNEE `30114C00..1C`。**快照必須同時確認 frame/context 與 binned Bayer descriptor，僅寄存器值無法證明像素截斷。**

RAW 檔案與預覽是否共用各級不能由區塊名得知。已讀的 CinemaDNG writer 稽核只證明末端封裝沒有創作矩陣，不證明 CRCT / SIG 分叉之前完全沒有變動。本輪沒有追加任何相機操作。

## 重算材料

同目錄 `extract_raw_front_constants.py` 僅讀取 `out/seg0_c0000000.bin` 與 `out/seg1_c2ef6e00.bin`；已執行並輸出 `raw-front-constants.json`。JSON 保存兩個 segment 的 SHA256、上述 ROM 原值及 bin 係數和，沒有包含或模擬實機 active register。工具可自動尋找 repository root，亦接受 `--root`。
