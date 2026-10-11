# SIGMA fp 自動向右曝光（Auto ETTR）與最佳 Gain／AR 選擇研究

日期：2026-08-31  
目標機型：SIGMA fp  
目標韌體：Ver.5.02  
感光元件：Sony IMX410 系列

狀態標記：

- `CONFIRMED`：由 fp 5.02 韌體流程、register 或既有 RAW 實作直接確認。
- `MEASURED`：由工作區內現有 DNG／測試量得。
- `PROPOSED`：本文件提出的控制策略，尚未掛入相機。
- `TO TEST`：必須用實機受控影像或 runtime probe 驗證。

---

## 1. 結論摘要

### 1.1 能不能做

架構上可行，但尚未完成實機閉環驗證。fp 已具備建立閉環所需的大部分積木：

1. live／recording RAW 完成 callback 與 Bayer buffer 候選；
2. per-channel black／white level 與 RAW clipping 分析原型；
3. AE 的 16×16 YLevel 網格、P-line 與 APEX 計算；
4. 曝光時間、ISO、LCG/HCG、analog gain 的 runtime 狀態；
5. LCG/HCG、analog gain、ISP digital gain 與 Analog Readout（AR）的完整韌體鏈。

目前缺的是把它們接成：

```text
線性 RAW 高光尾端統計
        ↓
ETTR headroom／scene-change 判斷
        ↓
快門／光圈的實際曝光控制
        ↓
受限制時才做 CG／analog gain 最佳化
        ↓
AR 由 final analog code 自動派生
```

### 1.2 目前能下的「最佳 gain／AR」結論

在受控量測完成前，production-safe 預設應為：

| 層 | 建議 | 理由 |
|---|---|---|
| 實際曝光 | 優先增加快門時間／開光圈，保留 RAW 高光安全距離 | 只有它們增加收到的光子，才是真正 ETTR |
| Conversion Gain | 先保留韌體 `Auto` | LCG/HCG 的滿井與 read-noise 實測曲線尚未完成 |
| Analog Gain | 不用它假裝「加光」；需要時只用 sensor analog 範圍 | 它不增加 photon SNR；仍可能改善 ADC／後級噪聲利用率 |
| ISP Digital Gain | 不作 ETTR actuator；以 unity 為目標，但先保留原廠 mode-specific trim | 不增加感光資訊或 SNR；任意移除原廠 trim 仍可能影響量化／輸出映射 |
| Analog Readout（AR） | **Production 維持 Firmware Auto**：原廠在 `analog_code < 0x0DFD` 選 Normal，否則 High | 這是原廠依 final analog code 選擇的讀出工作點，不是已證明可獨立最佳化的畫質旋鈕 |

換句話說，現階段最可靠的答案是：

> **用快門／光圈向右曝光；CG 先 Auto；不額外加入 ISP digital gain；AR 由原廠依 final analog code 選擇。**

### 1.3 為何不能指定一組固定值

「最佳」至少同時受以下目標影響：

- 高光容量；
- shadow input-referred read noise；
- motion blur；
- 景深；
- RAW bit depth；
- frame rate／最大曝光時間；
- 溫度、長曝光暗電流與 banding；
- 使用者是否允許犧牲小面積 specular highlight。

LCG 偏向保留高光，HCG 偏向降低暗部讀噪；兩者是 Pareto 取捨，不存在脫離場景與拍攝限制的固定贏家。AR 更不應獨立選；目前沒有證據顯示在低 gain 強制 High AR，或在高 gain 強制 Normal AR，會得到較佳畫質。

---

## 2. 已確認的 fp 曝光與 gain 管線

### 2.1 原廠 AE 不是 ETTR

`CONFIRMED` fp 的 AE 以 16×16 測光網格的加權平均 YLevel 為核心：

```text
Bv = Bv_applied + 1024 × log2(YLevel / 8522.363)
```

- YLevel 是區域平均，不是高光 percentile 或 clipping tail。
- 測光模式可改變各 cell 權重，但仍以平均亮度為核心。
- AE 再經曝光補償、TargetBvShift、臉／AF 區偏移、P-line 限制分配 Tv／Av／Sv。

證據：`../notes/AF_AE_INTERNALS.md` §④、§⑩；`../out/decomp/full/blk_c02.c` 的 `FUN_c020a3c0 @ 0xC020A3C0`、`FUN_c0219f88 @ 0xC0219F88`、`FUN_c0226f58 @ 0xC0226F58`。

因此原廠 AE 能把中間調到「看起來正確」，但無法知道任一 CFA channel 距離 sensor white 還有多少。

### 2.2 顯示 Histogram 也不適合作為唯一 ETTR 感測器

`CONFIRMED` 機內 HistogramDrawer 的 recording provider 取 display／render image descriptor，再從 4-byte pixel buffer 抽樣成 8-bit bins。它不是直接對 Bayer RAW 的 per-channel saturation 做統計。

證據：`../out/decomp/full/blk_c05.c`：

- `HistogramDataProviderRec::v1 @ 0xC05A3128`
- `FUN_c05a3230 @ 0xC05A3230`
- `HistogramDrawerYlevel::v1 @ 0xC05A3410`

顯示 histogram 會受 WB、color transform、gamma／tone 與顯示路徑影響，只能當 UI 輔助，不應當作 RAW clipping ground truth。

### 2.3 Gain 與 AR 的已確認路徑

`CONFIRMED`：

```text
ISO／AE relative gain
  → FUN_c030c878
  → FUN_c0312f18
  → FUN_c03131e0
  → XC_ImageSensorIMX410::v8 @ 0xC0323580
       → v30 @ 0xC03239C8：LCG/HCG
       → v31 @ 0xC0323A78：analog node／digital trim
  → v10 @ 0xC0323818：sensor registers
```

`v8` 的輸出：

- low 16-bit：12-bit sensor analog gain code；
- high 16-bit：analog cap 以上的 ISP digital multiplier。

Sony gain law：

```text
linear_analog_gain = 4095 / (4095 - analog_code)
```

AR 規則：

```text
analog_code < 0x0DFD  → Normal AR
analog_code ≥ 0x0DFD  → High AR
```

`0x0DFD` 約等於 7.97×／+18.03 dB analog gain。完整 register 組合與 mode-specific HCG 門檻見 `SIGMA_FP_IMX410_ISO_GAIN_RESEARCH_2026-08-18.md`。

### 2.4 Mode-specific CG 門檻

`CONFIRMED` 於 fp 5.02 的 gain controller：

| gain state | 既有自動 HCG 決策 |
|---:|---|
| 0 through／Live View | 每台 sensor OTP `S+0x84` |
| 1／2／3 acquisition／through acquisition／standard movie | ISO 640 |
| 4 generic movie RAW | 不自動切 HCG |
| 5／6 movie RAW 8／10-bit | ISO 640 |
| 7 movie RAW 12-bit | ISO 3200 |
| 8 digital off | 不切 HCG |

這張表描述韌體行為，不等於已證明每個門檻都是 ETTR 的最佳畫質點。尤其 shell help、舊筆記與新反編結果對部分 gain-state 名稱曾有不一致；在閉環控制前必須用 runtime bit depth／mode descriptor 對齊，不能只信 shell flag 名稱。

---

## 3. 現有 RAW／測試資料能證明什麼

### 3.1 已通過的純邏輯測試

`MEASURED` 本輪重新編譯並執行成功：

- `test_imx410_gain_override.c`
- `test_raw_false_color_core.c`
- `test_raw_false_color_runtime.c`
- `test_raw_false_color_osd.c`
- `sigma_fp_re_usbshell/host/monitor/test_fpstate.py`（2 tests）

它們能證明：

- Auto／Force LCG／HCG 的純邏輯；
- AR 在 `0x0DFC／0x0DFD` 邊界正確切換；
- 四種 CG×AR register 組合內部一致；
- RAW12／14 packing、zone、near-black 與 per-channel clipping 分類；
- mailbox 採 latest-frame-wins，不會讓舊幀塞住 callback；
- USB shell reply 的既有文字解析案例。

它們不能證明哪種 CG×AR 影像品質最好；`test_fpstate.py` 也沒有測 exposure／gain mapping。現有 mock 對 exposure offset 的讀值仍為零，新版 telemetry V2 又有 worker 掛起紀錄，因此不能把這些測試當成 live telemetry 驗證。

### 3.2 現有 DNG 資料稽核

`MEASURED` 工作區與上一層研究目錄共 1,698 個 DNG，但大多是少數 clip 的連續影格：

| 資料 | 數量／設定 | 限制 |
|---|---|---|
| `captures/fpGFTest_pre_stage4.../A001_001` | 358 幀，RAW12，ISO 100，1/60 s，f/1.4 | 一段一般場景，不是 calibration |
| 同目錄 `A001_002` | 438 幀，RAW12，ISO 800，1/60 s，f/1.4 | 取景不同，未記錄 forced CG／AR |
| `captures/fpGFTest_stage4.../A001_001` | 851 幀，RAW12，ISO 100 | 功能測試 clip，不是 gain sweep |
| `card_backups/.../100SIGMA` | 29 張 RAW14，ISO 100，1/125 s，f/1.4 | 同一 exposure，無 CG×AR sweep |
| 兩份 `_SDI0045.DNG` | 位元完全相同的重複檔，ISO 100 | 單一場景、無 exact-white；少量 near-white pixel 可作 clipping parser 範例，不能選 gain／AR |
| `char_dng` | 12 幀 CinemaDNG | 色彩轉換素材，不是 gain／AR characterization |
| 上一層其他 8 張 | `_SDI0010–0013` 為 ISO 800；`_SDI5625／5626` 為 ISO 2000／1250；另有 `char_chart`、`pre_stillraw` | 稀疏一般場景或流程素材，沒有受控對照狀態 |

現有 tag／decoder 觀察：

- RAW12：BlackLevel 約 255／256，WhiteLevel 4095；
- RAW14：BlackLevel 1024，WhiteLevel 16383。

這些值可作為 host analyzer 的起點，但 live pipeline 仍須逐 mode 驗證。現有資料沒有：

- 同一均勻光源；
- 同一實際曝光；
- LCG／HCG × Normal／High AR 四組；
- 多張 dark／flat pair；
- register、analog code、digital gain、溫度同步記錄。

所以目前不能從現有 DNG 計算出「最佳 gain／AR」。

---

## 4. ETTR 必須控制「真實曝光」，不是只把 ISO 拉高

對固定場景照度，sensor 收到的光量近似：

```text
photon_exposure ∝ exposure_time / f_number²
```

ISO、analog gain 或 digital gain 不會增加入射光子。它們可能改善 ADC code 利用率或降低某些 downstream noise，但不能把 photon shot noise 變少。

因此：

- 快門／光圈可動：可以做真正 Auto ETTR。
- 快門角度與光圈都鎖死的 cinema workflow：**不能做真正 ETTR**；只能做 Gain Optimization，或提示需要加／減燈、ND、光圈或 shutter constraint。
- 用 gain 把 histogram 推右，必須在 UI 中明確標示為「gain fill」，不能稱為增加曝光。

---

## 5. 建議的 RAW 高光統計

### 5.1 每個 CFA channel 分開正規化

`PROPOSED` 對每個 R／G1／G2／B sample：

```text
x_c = clamp((DN_c - Black_c) / (White_c - Black_c), 0, 1)
```

ETTR 不應先套 WB。只要任一 RAW channel 先到 white，就已遺失該 channel 的線性資訊。

### 5.2 同時保留 hard clip 與 robust tail

只看最大值會被 hot pixel／瞬間反光支配；只看 percentile 又可能漏掉小而重要的高光。因此同時使用：

1. **Hard clip guard**：每 channel 接近／到達 white 的 pixel 數與空間分布；
2. **Robust tail**：每 channel `p99.9`、`p99.99`，並取四 channel 最危險者；
3. **Spatial tile maximum**：保留小面積 highlight 的位置，不讓全域 percentile 把它洗掉；
4. **Temporal persistence**：單一固定 sensor 座標的異常點可標為 hot-pixel candidate；跟著場景移動的高光不可忽略。

現有 `raw_false_color_core.c` 每 tile 只抽四個 2×2 cell，適合低成本 overlay，但可能漏掉很小的高光。ETTR 感測器應增加 stratified samples／tile maxima，或使用低成本 histogram 加完整的 near-white scan。

### 5.3 Headroom 公式

令四 channel 的危險 tail 為：

```text
p_tail = max(p_R, p_G1, p_G2, p_B)
headroom_EV = -log2(p_tail)
error_EV = headroom_EV - reserve_EV
```

- `error_EV > 0`：仍可增加真實曝光；
- `error_EV < 0`：已太靠近 white，必須減少曝光；
- 任一 hard clip：直接進入 clip recovery，不等待平均值。

### 5.4 起始安全距離（不是校準完成值）

`PROPOSED／TO TEST`：

| Profile | 初始 reserve | 用途 |
|---|---:|---|
| 靜態、光線穩定、單張 | 0.33 EV | 追求接近 white，但保留量化／校準誤差 |
| 一般影片 | 0.67 EV | 容納 callback→AE→sensor 的控制延遲 |
| 高動態亮度／活動攝影 | 1.0 EV | 防止場景突亮時大量 clipping |

最終 reserve 應由實測 loop latency、曝光生效延遲、光源 flicker 與 white-level variation 決定，不能直接把上表發布成固定規格。

---

## 6. 閉環控制律

### 6.1 狀態機

`PROPOSED`：

```text
INIT
  → MEASURE
  → TRACK ───────────────→ STABLE
      │                      │
      ├─ hard clip ───────→ CLIP_RECOVERY
      ├─ scene jump ──────→ REACQUIRE
      └─ user/record lock ─→ HOLD
```

### 6.2 非對稱反應

高光爆掉不可恢復，輕微 underexposure 可在下一幀或後製補。因此控制速度應非對稱：

- 看到 hard clip：立即減 0.5–1 EV，依 clipped area 加大；
- 高光仍有餘裕：每次最多增加 1/6 EV；
- deadband：初始 ±0.15 EV；
- 增加曝光前要求至少 3 個穩定 sample；
- 減少曝光可在 1 個 sample 觸發；
- scene jump 時清除慢速積分，不沿用上一場景的曝光傾向。

所有數字均為 bring-up 起點，需硬體 loop 測試後調整。

### 6.3 Scene-change 與 flicker

- RAW tail 的快速位移與 AE 16×16 grid 可共同判斷 scene change。
- YLevel grid 適合偵測整體亮度／構圖改變，但不取代 RAW clip guard。
- 50／60 Hz 光源下，快門應量化到防 flicker family；不要為追 0.1 EV headroom 在相鄰 flicker-unsafe shutter 間 pump。
- 錄影期間限制曝光更新頻率，並對 output EV 做 slew-rate limiting，避免可見亮度呼吸。

---

## 7. Actuator 優先序

ETTR controller 必須服從使用者對 motion 與景深的意圖。建議提供 profile，而不是唯一硬編碼順序。

### 7.1 Still Quality

```text
使用者指定／鎖定光圈
  → 延長快門到 motion limit
  → 若允許，自動開光圈到 aperture limit
  → 若仍不足，再進 Gain Optimizer
```

### 7.2 Cinema

```text
固定 shutter angle + 固定光圈
  → 沒有真實曝光 actuator
  → 只做 Gain Optimizer／顯示 ND 或加光提示
```

若允許 auto shutter angle 或 auto aperture，才可在使用者指定的窄範圍內做 Auto ETTR。fp 沒有內建可變 ND，因此明亮場景無法靠軟體維持固定 shutter／aperture 又避免 clipping。

### 7.3 Run-and-gun

```text
先守住最大 shutter time／motion blur
  → 在容許範圍內開光圈
  → HCG／analog gain 補足
  → 不使用品質無益的 ISP digital gain
```

---

## 8. Gain Optimizer：怎麼選 LCG／HCG／analog gain

### 8.1 不把 ISO 當成一個旋鈕

最佳化器應列舉真正的硬體 candidate：

```text
candidate = {
  exposure_time,
  f_number,
  conversion_gain ∈ {LCG, HCG},
  analog_gain_code,
  analog_readout = (analog_gain_code >= 0x0DFD),
  isp_digital_gain = 1.0
}
```

每個 candidate 先預測四 channel peak，超出 reserve 或產生不可接受 clipping 者直接淘汰。

### 8.2 無校準時的安全規則

`PROPOSED`：

1. CG 保留 firmware Auto；
2. AR 嚴格跟隨 `0x0DFD`；
3. 不強制未知 CG×AR 組合；
4. analog gain 不超過每機 OTP cap；
5. ISP digital gain 鎖 1.0×，不足的顯示亮度交給 metadata／後製；
6. Live View 的 HCG 門檻讀本機 OTP，不套固定 ISO；
7. final analog code／AR 以 runtime readback 為準，不由 ISO 猜。

### 8.3 有校準後的選擇準則

`TO TEST` 每個 CG／AR／analog code 建立：

- saturation exposure／saturation electrons；
- input-referred temporal read noise；
- system gain（DN/e−）；
- linearity error；
- row／column FPN、banding；
- black drift；
- hot-pixel rate；
- temperature／exposure-time dependency。

然後：

- 若 HCG 的較低 read noise 對當前 shadow signal 有實質改善，且其 saturation capacity 仍能守住 highlight reserve，選 HCG；
- 若高光容量是約束，或 HCG 會讓預測 peak 過近／clipping，選 LCG；
- analog gain 只增加到足以改善已量得的 ADC／後級噪聲或量化利用率；若增加後 input-referred noise 沒再下降，就停止；
- 任一需要 ISP digital gain 的 candidate，在畫質分數上不優於同 sensor state、後製增亮的版本；品質模式淘汰；
- CG switch 加 hysteresis 與 minimum dwell time，避免畫面在門檻附近來回改變 black／noise texture。

### 8.4 12-bit RAW 的特別候選

韌體讓 RAW12 到 ISO 3200 才自動切 HCG；ISO 640–2500 仍為 LCG。這個區間是「提前 HCG」最值得研究的候選，但目前只能列為 `TO TEST`：

- 可能收益：較低 shadow read noise；
- 可能代價：較低 saturation capacity、black／linearity 變化；
- 必須用同一 photon exposure 的 matched dark／flat／step-wedge 比較；
- 不能只看被 normalize／tone-map 後的成片亮度。

在完成量測前，不應把「RAW12 一律提前 HCG」當成預設。

---

## 9. AR 的最終策略

### 9.1 Production

```text
AR = Auto(final_analog_code)
```

不給一般使用者獨立 Normal／High 選單，只顯示 readback 狀態。

### 9.2 Research mode

Force Normal／Force High 只允許在：

- 單張 still；
- 非 recording；
- 有完整原值可回復；
- 同步記錄 registers、analog code、溫度；
- 每組都有 dark／flat／exposure ramp；
- watchdog／reboot 後回 Auto。

若沒有量到 High AR 在某段 gain 的 read noise、linearity 或 FPN 有穩定優勢，就不建立第二條 production 門檻。現有唯一可信門檻仍是原廠 `0x0DFD`。

---

## 10. fp 5.02 的實作接點

### 10.1 Read-only 第一階段

每筆 telemetry 同步保存：

| 資料 | 現有候選來源 |
|---|---|
| RAW address／format／bit depth | `FUN_c0429f18` completion path；`FrameExpos_s` hook |
| per-channel RAW tail／clip counts | 擴充 `raw_false_color_core` 或另建 ETTR stats worker |
| exposure time | `FUN_c030c7f0` |
| current aperture | lens／menu getter；需 pin runtime source |
| gain state／relative ISO／linear analog gain／HCG | `G @ 0xC343A6A0` |
| final 12-bit analog code | `FrameExpos_s` active slot 候選：`*(0xC3439404 + slot×0x10 + 0x34) & 0xFFFF`，先實機確認 |
| AR／CG registers | sensor I2C readback：`0x05E1/0x05E2/0x041F/0x05A6/0x05A8` |
| ISP digital gain | `G+0x30` cap overflow，另記 v31 inter-node trim |
| scene-change grid／YLevel | AE buffer `0xC3201B14`、`DAT_c3202c6c` 候選，先 live probe |
| temperature | sensor／body temperature source，尚需 pin |

第一階段只記錄，不寫 exposure 或 sensor register。這能先回答 callback 延遲、white-level、slot、mode mapping 與讀值一致性。

### 10.2 Closed-loop 接入點

較安全的 production 架構是：

```text
ETTR worker 算出 ΔEV
  → 注入 existing TargetBvShift／AE request
  → 讓原廠 P-line 分配 Tv／Av／Sv 與 obey limits
```

不建議每幀直接 I2C 改 sensor register：會與原廠 `v10` 競爭，也繞過 exposure timing、P-line、flicker 與 metadata 同步。

候選 seam：

- `FUN_c0226f58 @ 0xC0226F58`：AE 偏移合成；
- `TargetBvShiftBase` vtable 區；
- `FUN_c020a858 @ 0xC020A858`：P-line 前後的 exposure update 路徑。

必須先用 ±1 EV 的 read-only／single-shot probe 確認 sign、單位（EV×1024）、更新延遲與 ACQ／MONIT 差異。

### 10.3 PTP 注意事項

既有 `ConfigApi` PTP 路徑會令 `DAT_c32006F8` 觸發 AE 重新計算並覆蓋原手動值。若 ETTR 走 PTP setter，需先解決 ownership；否則應在相機內部 AE seam 接入，避免 host 與 AE 互相搶值。證據見 `../notes/PTP_READ_USER_EXPOSURE.md`。

---

## 11. 必做的實機校準矩陣

### 11.1 拍攝狀態

至少分開：

- still RAW14；
- standard movie；
- RAW8／10／12；
- 主要 frame rate／sensor mode；
- 冷機、穩態熱機；
- 短曝光與長曝光。

### 11.2 每組資料

對原廠 LCG／HCG + Auto AR，以及只供研究的 CG×forced AR 組合：

1. 32–64 張 lens-cap dark frames；
2. 32–64 張均勻 flat frames；
3. 20+ 段曝光階梯直到 saturation；
4. 每段同步記錄 Tv／Av、relative gain、analog code、CG／AR registers、digital gain、temperature、mode／bit depth；
5. 不變光源與固定構圖；
6. flicker-free DC light 或量測同步光源。

### 11.3 分析輸出

- photon-transfer curve；
- system gain；
- temporal dark noise；
- saturation capacity；
- dynamic range；
- SNR curve；
- linearity；
- DSNU／PRNU；
- row／column FPN；
- black drift 與 hot-pixel rate。

量測方法可依 EMVA 1288 的 linear-sensor 流程，但結果需標示這是特定 fp unit、mode、bit depth、temperature 的 operating point。

---

## 12. 建議開發階段

### Stage 0 — Gain／AR telemetry

- pin final analog code、AR readback、ISP digital gain；
- reconcile gain-state 名稱與 runtime bit depth；
- 讀本機 OTP；
- 不改相機行為。

### Stage 1 — ETTR Meter（只提示）

- per-channel RAW headroom；
- hard clip count／位置；
- 建議 `+／− EV`；
- 驗證 live 與 recorded DNG 的 white／black 一致性。

### Stage 2 — Stock-AE Supervisor

- 只調 AE compensation／TargetBvShift，讓原廠 P-line 保留快門、光圈、ISO、flicker 與使用者限制；
- CG／AR 保持 Firmware Auto；
- 先做 still／非 recording，再測 record start／stop；
- 驗證每步的符號、量化、套用幀與 clipping recovery。

### Stage 3 — Direct Constrained Actuator

- 只有 stock-AE supervisor 無法滿足 profile 時才直接控制；
- 先單獨驗證 shutter-only，再加入可選 aperture；
- 加 actuator profiles、slew limit、hysteresis 與 frame readback；
- 預設 CG／AR 仍 Auto，不直接逐幀寫 sensor I2C。

### Stage 4 — Calibrated Gain Optimizer

- 載入每機、每 mode 的 noise／saturation LUT；
- candidate enumeration；
- HCG 只在量測分數確實勝出時提前；
- AR production 仍依 final code 自動派生。

### Stage 5 — Research-only AR override

- 僅作 characterization，不作一般拍攝預設。

---

## 13. Go／No-Go 條件

閉環寫 exposure 前必須全部通過：

- RAW source 與 recorded plane 對齊；
- Bayer pattern、stride、bit depth、black／white level 逐 mode 驗證；
- tail statistics 不漏小面積高光；
- callback→sensor 生效延遲已量得；
- clipping recovery 在亮度 step test 無 overshoot；
- record start／stop 不死鎖；
- gain／AR readback 與要求一致；
- ISP digital gain 可檢出並在品質模式拒絕；
- 所有 override 在 unload、fault、reboot 後回 Auto；
- 未校準 unit 不啟用 calibrated CG policy。

任一條不滿足時，只發布 ETTR Meter，不發布 Auto ETTR。

---

## 14. 最終建議

### 可以立即採用

```text
RAW per-channel clip/tail 作為曝光尺
快門／光圈作為 ETTR actuator
CG = Firmware Auto
不額外加入 ISP digital gain；保留必要的原廠 mode-specific trim
AR = Firmware Auto，由 final analog code 派生並以 register readback 驗證
```

### 實測後才可採用

```text
LCG/HCG candidate scoring
RAW12 提前 HCG
mode-specific analog-gain optimum
不同溫度／長曝光的 gain policy
任何 forced AR
```

最有價值的下一個實機里程碑不是直接改 exposure，而是做一筆**逐幀同步記錄**：RAW tail、Tv／Av、final analog code、HCG、AR registers、digital gain、mode／bit depth、temperature。只要這筆資料可靠，ETTR Meter 可以先完成；有了受控 dark／flat／step-wedge，才有資格宣稱「最佳 gain」。

---

## 15. 主要依據

### 專案內

- `SIGMA_FP_IMX410_ISO_GAIN_RESEARCH_2026-08-18.md`
- `IMX410_EXPANDED_ISO_FIRMWARE_2026-08-17.md`
- `RAW_FALSE_COLOR_IMPLEMENTATION.md`
- `SIGMA_FP_V502_RAW_FALSE_COLOR_HOOKS.md`
- `raw_false_color_core.c/.h`
- `raw_false_color_runtime.c/.h`
- `imx410_gain_override.c/.h`
- `research/imaging-hw/notes/BAYER_FORMAT_MAP.md`
- `research/imaging-hw/bayer-hooks/frameexpos_capture.S`
- `../notes/AF_AE_INTERNALS.md`
- `../notes/ISO_FIRMWARE_COMPLETE.md`
- `../notes/PTP_READ_USER_EXPOSURE.md`
- `../out/decomp/full/blk_c02.c`
- `../out/decomp/full/blk_c05.c`

### 官方／標準

- Sony Semiconductor Solutions, **IMX410CQK Product Information**：確認 30 dB PGA 與 11／12／14-bit ADC。  
  https://www.sony-semicon.com/files/62/pdf/p-13_IMX410CQK_Flyer.pdf
- EMVA, **EMVA 1288 Release 4.0 Linear**：linear image sensor 的 system gain、temporal dark noise、saturation、SNR 與 dynamic range 量測方法。  
  https://www.emva.org/wp-content/uploads/EMVA1288Linear_4.0Release.pdf
