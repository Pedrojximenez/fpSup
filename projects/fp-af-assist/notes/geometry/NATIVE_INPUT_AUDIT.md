# 幾何方向器的 native 輸入稽核

日期：2026-09-27。對象：fp Ver.5.02、目前 `af_fusion_snapshot.S`／`af_fusion_collector.py` 與離線歷史檔。**只有檔案、反編譯與 ROM 的離線唯讀檢查；未操作相機、USB、鏡頭，未新增 probe 或修改 transport。**

同日後續實作：collector JSON v7 已依本稽核修正解碼，把舊 subject 誤標欄位隔離為 raw evidence，幾何 cue 均為未知；binary v1/v2/v3 的擷取範圍未改。新增完整 native subject bytes decoder，並修正 FACE_EYE_AF 筆記。下文「現行 snapshot／decoder」描述的是本次修正前的問題及未補齊的 wire data，不能再引用舊 valid=true 當現有 v7 行為。見 [新版使用方式](../research/AF_FUSION_TOOL_USAGE.md#61-幾何用主體資料契約)。

## 判決

現有 AFF1 snapshot **不能直接轉成有可信尺度與合焦錨點的 `FgSample`**。除了缺乏來源時間、身份／尺度 generation、鏡頭 stationary 與光學確認事件，本次核對原始程式還找到三個 subject 欄位歸屬／offset 問題：

1. JSON 的 `subject.face` 讀到的是 **AAT GetResult 矩形**，不是原始 face record。
2. `face0_tracking_id` 讀錯位置；真實 parser 把 ID 寫在 group `+0x24`，目前 snapshot 讀 group `+0x34`。
3. `subject.aat` 把 AAT 發布結構開頭的兩個 u32 解成四個 i16；這並非 `{x,y,w,h}`。

因此「欄位存在、valid=true、w_norm 非空」也不足以採用。此輪 core 與 JSONL replay 仍是 **shadow-only 離線模組**，不是已接入 native face／AAT 的實機幾何對焦。舊 capture 維持原樣，本文揭露語意問題，不重新命名舊值為真值。

契約見 [geometry.h](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/focus/geometry/geometry.h:6)：尺度必須是相對有效影像寬度的**線性尺寸**；三個 generation 是 adapter 自己維護的非零身份 token；`fg_confirm()` 要有明確光學確認、有效位置與新事件，不能由尺寸或 lens settled 推斷。

## 1. 三項來源核對

以下 `M=0xC37CCA9C` 是 DetectionResultMgr；`S=0xC303384C` 是 status 資料區。

### 1.1 `face` 實際讀 AAT 結果

現行 snapshot 將 `M+0x3D0` 命名 `FACE_MODE`、`M+0x3E0` 命名 `FACE_RECT`，存到 record `+0x80` 與 `+0x84..0x90`。bit 3 只檢查 w/h 正值，decoder 再做矩形相交判定並除以 320；沒有確認此來源是 face、沒有 producer valid、沒有 mode gate。

- [snapshot 位址定義](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/af_fusion_snapshot.S:57)、[複製及 bit 3](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/af_fusion_snapshot.S:178)。
- [decoder 命名與 w_norm](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/af_fusion_collector.py:146)。

原始呼叫鏈是 `C05ABEC8`（AAT 每輪工作）呼叫 tracker 的 GetResult vtable，再把結果傳給 `C05AC690(M, result)`。後者把 `{xs,xe,ys,ye}` 寫為 `M+0x3E0 {xs,ys,xe-xs,ye-ys}`；另一 backend 分支更會直接用固定 `0x40×0x40` 框。這不能當 face 尺度。

- [AAT GetResult → C05AC690](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:132354)。
- [矩形寫入／固定框分支](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:132704)。
- 已離線核對 ROM ARM：`C05AC6A8` 令 r4=M+3DC；`C05AC764/76C/77C/78C` 依序寫 r4+4/+8/+C/+10；即 M+3E0/+3E4/+3E8/+3EC。來源 [seg0](/Users/dido/Developer.localized/SIGMAfp_re/out/seg0_c0000000.bin)。

`M+3D0` 也由 AAT state setter `C05AC5C0` 寫入，不能因 JSON 名稱為 face.mode 就解成臉偵測狀態。[setter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:132644)

### 1.2 原始 face size 可定位，但目前未捕捉；ID offset 不可沿用

face parser `C05AAFF8` 使用 raw record `P=M+0x47C+raw_index×0x20`，排序後寫入 `G=M+0x10+selected_index×0x9C`：

| 來源 | 欄位 | 語意／限制 |
|---|---|---|
| `P+08/+0C` u32 | center x/y | 原始偵測座標；要記錄當時 reference 與 crop |
| `P+10` u32 | size | 原始方形線性尺寸，寫到 G+08/+0C/+18/+1C/+2C |
| `P+14` u32 → `G+28` | score | 另有排序／有效性 gate，並非尺度可信概率 |
| `P+18` u16 → `G+20` | angle | 原生 angle；不能未經驗證命名為 yaw 或照抄外部 yaw 補償 |
| `P+1C` u32 → `G+24` | native tracking ID | raw ID，不是 adapter target_generation |
| `G+30` byte | parsed valid | snapshot 的 `M+40=C37CCADC` 確實讀到 group 0 此 byte；但沒有 group 0 尺度 tuple |

依據 [parser 寫入](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:131621)。目前 snapshot 的 `FACE0_TRACK=C37CCAE0=M+44=G+34`，正確 group-0 ID 位置是 `M+34=C37CCAD0=G+24`。ARM `C05AB27C..288` 也直接確認：先加 M+10，再把 raw +1C 寫至 group+24。這是靜態 offset 結論，尚未做新的實機讀值驗證。

`C05A9AF0` 依 mode 選 reference，並且有略過轉換分支；在這個 parser 呼叫中只轉換 G+0/+4，不能把所有 raw size 無條件宣稱為已驗證的 `size/320`。[座標轉換](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:130735)

原筆記 [FACE_EYE_AF](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FACE_EYE_AF.md:39) 曾把 ID 寫成 group+34，與本次原始碼及 ARM 核對不符；同日後續實作已修正該筆記及 collector 解碼。Native adapter 應依上述重新審核。

### 1.3 現行 `aat` 不是原始 tracker 半軸，也不是正確的四元矩形

snapshot 讀 `C3033E00` 的 8 bytes，decoder 解為 `<hhhh>`；品質 byte 讀 `C3033E26`。[擷取](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/af_fusion_snapshot.S:166)、[解碼](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/af_fusion_collector.py:135)

但 `C05A9900` 把 `M+4` 起 0x470 bytes 發布到 `S+278`。因此 `C3033E00=S+5B4` 對應的是 **M+340**，不是 i16 矩形。

- M 基底：[singleton](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:130900)。
- S 基底：`C00178D8` 回 C3033834，[C0017AC8](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:21558) 加 18；[singleton](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:21475)。
- [M+4 發布](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:130628)、[目的 singleton+290=S+278](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:21886)、[0x470 bytes copy](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:23623)。

`C05AC690` 自增 M+3DC，條件成立才把 M+3DC 起 0x28 bytes 複製到 M+340。其結構如下：

| 已發佈 status 位置 | 對應 M 位置 | 內容 |
|---|---|---|
| `C3033E00 = S+5B4` | +340 | AAT 路徑計數（複製自 +3DC） |
| `C3033E04..10 = S+5B8..5C4` | +344..350 | 四個 i32 的結果矩形 x/y/w/h |
| `C3033E14..20 = S+5C8..5D4` | +354..360 | 另一座標版本四個 i32 矩形；AF 實際讀這組 |
| `C3033E24/25/26/27` | +364..367 | valid/ever-found/quality/附加結果 byte；其中 +26 是現行 confidence_raw |

依據 [計數、結果與條件複製](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:132704)。ARM `C05AC838..85C` 確認複製起點 M+3DC、目的 M+340、總長 0x28。AF `C02761C8` 檢查 `S+5D8 != 0` **且** `S+5DA > 19`，`C02763C0` 讀參數 `S+5B4` 的 +14/+18/+1C/+20，再做輸出 reshape。[AF gate](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:72610)、[AF 讀值](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:72700)

所以現行 `aat.locked` 只是錯誤矩形判定再加 `quality>19`，連原廠 valid gate 也未完整涵蓋；不能設 `FG_AAT_SCALE_VALIDATED`。

真正 color-tracker model 是 `C37CDFA8` 的 0x2C bytes，半軸在 +4/+6（u16），角度 +8、hits 映射信心 +0C、半軸面積比例 +0D。目前 AFF1 完全沒收這份資料。GetResult 可以使用另外處理過的狀態，還會半軸右移、轉換座標；搜尋窗、擬合後 model、輸出矩形、AF ROI 要各自標記。[GetResult](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:139568)

原廠 **已存在** C05B2DC0 的大小相依 normalizer／floor／aspect gate，會自行改變搜尋窗，不能把它當物體深度訊號，也不能把復刻漏 normalizer 的發散當原廠缺陷。[normalizer](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:136650) `model+0D` 由兩半軸與 maxAxis² 算出，**不是前景命中密度**；+0C 的 hits 信心也不是幾何可靠性。[欄位計算](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c05.c:139893)

## 2. 與 FgSample 契約逐項比較

| core 所需 | AFF1 可讀 | 尚缺／不可誤用 |
|---|---|---|
| `scale_q16` | 上述命名有誤的矩形欄位與固定 320×213 宣告 | 無已驗證 native face 尺度；無 AAT raw axes。不能把 AF ROI 或面積直接當線性尺寸 |
| `source_kind` | decoder 優先 `face.valid`，其次 `aat.locked` | 兩組不是已核對的 face/AAT 雙來源。不能照 cue_source 設 FG_FACE |
| `source_seq` | record +08，執行 handler 即加一 | 是觀測次數，非 detection publication 或曝光 generation；同一舊資料可重讀 |
| `sample_ms/now_ms` | +10/+14 的 camera 32-bit μs tick；host before/after wall-clock ns | 只量取讀記憶體的區間，沒有來源產生時間／age；host midpoint 不是曝光時點。μs wrap 必須先正確延展，再統一 ms epoch，不能直接 /1000 假裝 32-bit ms wrap |
| `target_generation` | 一個讀錯位置的 face0 ID；`subject.track_id` 刻意保持 null | 無所選目標身份、reset/reacquire、原始 ID 重用事件 |
| `context_generation` | AF drive/area/route、gain、shutter、fno 等片段 | 無完整 lens identity、readout/reference/crop/zoom/e-stabilization/尺度定義變更事件 |
| `scale_generation` | 無 | 需 adapter 對 face/AAT handover、reseed、raw/model/result 定義變更增代 |
| `FG_PROJECTION_STABLE` | 無 native pose／reference tuple | 不能由框平滑、score 高或 body_motion=0 推定；原始 angle 亦不等於外部 yaw |
| `FG_LENS_STATIONARY` | +50 g_afpos、+58 mposm、route、step_state、speed_lpf 等 | 無獨立當前 motor completion/settle 及位置配對；命令域/歷史域不等於 lens stationary |
| `FG_CDAF_CONFIRMED`、`FG_POSITION_VALID`、focus_event_seq | H/L、peak_now/max/min、peak_argmax | 無當前同目標的成功合焦事件、失敗 reason、確認時位置與尺度；峰值與 route 返回不能自行設 confirmation bits |

來源：[AFF1 sequence 產生](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/af_fusion_snapshot.S:93)、[time/AF/subject 輸出](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/af_fusion_collector.py:249)。

`snapshot_coherent` 只代表 area/sample index 在讀取前後相同且未越界。它沒有同步鎖 face、AAT、AF、曝光／鏡頭；沒有 detection counter 前後夾讀。decoder 本身也明示 idle 時 mposm 可留舊值，而 H/L 仍更新。[coherent 判定](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/af_fusion_collector.py:177)、[限制](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/af_fusion_collector.py:268)

同理，session nonce／sequence／magic／trailer 可驗 transport record 來歷與封裝，不能驗來源 fresh；capture guard 也不是 motor idle。AFF1 binary v1/v2/v3 與 JSON schema 名稱分別演進，不能把舊 capture guard／gain 欄位直接套最新語意。[版本分支](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/af_fusion_collector.py:183)

既有 H/L freshness 稽核指出 scheduler phase 是循環值、debug counter 有 gate，均不是曝光 ID；即使前後 phase 相同也不是完整 seqlock。[freshness 界線](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AF_STATS_FRESHNESS_2026-09-16.md:181)

## 3. 舊資料可合法重播的範圍

### 現存 af-fusion captures

唯讀盤點 `research/autofocus/captures/af-fusion/*/samples.jsonl` 的 15 檔，共 **3538 records**，歷史 JSON schema 為 v1–v5；所有檔依當時保存的欄位均為 `face.valid=false`、`aat.locked=false`、`subject.track_id=null`。這是**舊 decoder 的欄位值盤點**，不證明當時沒有真實人臉／AAT，也不驗證錯誤 offset。

這批檔可驗解碼、時序拒絕、缺欄位／no-anchor 流程；不能重播出已驗證尺度或首次合焦後幾何趨勢。例：[repeat-a 第 1 筆](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/captures/af-fusion/2026-09-16-repeat-a/samples.jsonl:1)。

三輪 Near 完成歷史重現峰值，證明的是所支持分支的曲線／候選位置一致性；其最後位置屬命令域，並非馬達／光學真值。完成 byte 或 offline reconstructed peak 不能自動產生幾何錨點。[重複性證據邊界](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_AF_REPEATABILITY_2026-09-16.md:33)

### `turn_and_walk.jsonl`

唯讀核對 [舊 fixture](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/fixtures/turn_and_walk.jsonl:1)：1040 rows，t=0..59.975 秒且嚴格遞增；841 rows 有 face 與 yaw_deg，906 rows 有 human。框只有 `w,h,cx,cy,x,y,confidence`。檔案中沒有 native AAT、track ID、有效影像 reference、crop／lens metadata、motor position、合焦事件、曝光／來源 timestamp 或已知接近／遠離標註。

可用於舊外部 detection 的尺度／遺失模式研究，或新 core 的**明確標示為假設情境**的輸入穩健性測試；**不能無標記補造 generation、projection_stable、lens_stationary、CDAF_CONFIRMED，把結果稱為 native 已驗證重播**。直接依現有證據轉入完整 core，缺有效錨點就應 UNKNOWN。若另加 synthetic anchor／測試 metadata，必須存為獨立衍生測試，不改原 fixture，並不得拿合成條件算實機方向準確率。

舊 subject 模組也明確區分直接量測與推算尺寸，且 fixture 包含轉身／出框；檔名不等於每幀的深度方向真值。[舊模組說明](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/focus/subject.py:13)

## 4. 最小下一步 native adapter 工作

1. **先建立正確、具來源版本的資料契約。** 修正上述 subject 位址／型別歸屬，新增原始 face 選中項完整 tuple（size、ID、valid、score、angle、reference）與 AAT model 原始半軸／結果矩形／AF 採用 ROI 的分離欄位。新契約版本拒絕把舊名稱默認升級；首版只採 face 尺度，AAT 先供連續性／旁路研究。
2. **在適合的 native publication 邊界觀測並自建 generation。** hook 完成後發佈 immutable observation，含 native source、來源 completion 時點／可驗 age、adapter source_seq、目標選擇／reacquire、model reseed、模式／crop／鏡頭變更。現有 M+3DC 是 AAT 函式呼叫計數，還有 stale GetResult／條件複製分支，僅可作診斷，不能直接冒充曝光 counter 或 target_generation。要先驗 producer、snapshot 與 AF 事件能否配對。
3. **獨立建立光學確認 adapter。** 追出原廠成功／失敗 AF 完成分支及獨立 lens-completion／位置來源；記錄事件序列、事件時間、所採目標／ROI generation、確認結果、有效位置。只在與新鮮同來源尺度配對時呼叫 fg_confirm；CDAF 提交候選、鏡頭停止或 H 最大都不足以單獨設成功 bit。
4. **把 flags 當測量 gate。** `FG_SCALE_VALID` 需正確線性尺度／reference；`FG_IDENTITY_VALID` 需同一目標；`FG_TIME_VALID` 需有可驗來源 age；`FG_PROJECTION_STABLE` 需 pose／crop／breathing 控制；`FG_LENS_STATIONARY` 需獨立移動證據。未知就不設 bit。AAT 另需固定距離、自動調框、轉頭／遮擋及已知前後移動對照才可設 `FG_AAT_SCALE_VALIDATED`。
5. **仍先 shadow-only。** 有真實 tuple 才把紀錄與人工／獨立運動真值離線對照，分開量方向誤判、UNKNOWN 覆蓋率、翻轉延遲、anchor 錯配與失效。EP83 或 USB 可作開發回傳方式，但不替代 tuple 語意驗證，也不讓產品運算依賴電腦。這份工作未部署 hook，未完成 native adapter 或實機測量。

本輪可完成的是獨立 C core／明示來源的離線 JSONL 接口。**目前真正缺口在可信 native observation 與合焦事件的配對，不是替已有 snapshot 補上全真的 flags。**
