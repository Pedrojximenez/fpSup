# SIGMA fp / IMX410 ISO、Conversion Gain 與 Analog Readout 研究紀錄

日期：2026-08-18  
韌體：SIGMA fp Ver.5.02  
感光元件：Sony IMX410 系列  
狀態標記：`CONFIRMED`＝由韌體控制流程／常數直接確認；`OTP-RUNTIME`＝流程已確認，但數值來自每顆 sensor 的 OTP；`TO TEST`＝需要實機影像或 register probe 驗證。

## 1. 結論摘要

1. IMX410 在 fp 韌體中只有一條 Bayer RAW 輸出串流；目前沒有發現同一幀同時輸出 LCG 與 HCG 的雙路 RAW。
2. 真正的 conversion gain 有兩種硬體狀態：LCG 與 HCG。選擇由 sensor register `0x05E1` 控制。
3. LCG/HCG 之後另有連續可調的 sensor analog gain；gain code 是 12-bit，寫入 `0x003D–0x0040`。
4. analog gain code 達 `0x0DFD` 時，韌體會啟用另一組 high-analog readout／bias 配置。這是硬體讀出工作點，不是第三種 conversion gain，也不是 gamma／tone curve。
5. Normal／High analog readout 可能影響黑位、線性、讀出雜訊與固定圖樣噪聲，但方向與幅度尚需實測。
6. Sigma 的自動策略大概率是校準後的安全折衷。強制 LCG/HCG 可能改變高光空間與暗部噪聲的取捨；強制 AR 組合未證明能提升畫質。
7. 每台相機的部分 gain 數值來自 IMX410 OTP，因此精確的 ISO→analog code→AR 對照可能有個體差異。發布工具不應硬編碼未經實測的 ISO/AR 對照。

## 2. ISO 並不是 sensor 的輸出格式

Sensor 不直接輸出「ISO 640」或「ISO 3200」。實際路徑是：

```text
光子／像素電荷
  → LCG 或 HCG conversion gain
  → sensor analog gain
  → Normal 或 High analog readout/bias 配置
  → ADC（RAW12／RAW14）
  → 單路 Bayer RAW
  → ISP digital gain（必要時）
```

### 2.1 ADC 位深更正

Sony 官方 IMX410CQK product information 明確標示 sensor 內建 **11-bit／12-bit／14-bit A/D converter**，並指出 14-bit 用於約 19.2 fps 全畫素靜態讀出、12-bit 用於高速 4K 動態讀出。它不是固定 16-bit ADC。

fp 5.02 韌體的通用 bit-type enum 雖包含 RAW16，但 70 個 IMX410 mode 中實際只有 62 個 RAW12 與 8 個 RAW14，沒有 RAW16 mode。機內 ISP／後續影像運算使用 16-bit 容器，不能反推 sensor ADC 是 16-bit。

ISO 是機身把曝光指數映射到上述硬體狀態與增益的控制值。雙原生 ISO 的核心源自 LCG/HCG 硬體，但不表示 sensor 只能輸出兩個固定 ISO。

## 3. 已確認的韌體呼叫鏈

```text
ISO／AE relative gain
  → FUN_c030c878
  → FUN_c0312f18
  → FUN_c03131e0
  → XC_ImageSensorIMX410::v8  @ 0xC0323580  （gain compose）
       → XC_ImageSensorIMX410::v30 @ 0xC03239C8（LCG/HCG 決策）
       → XC_ImageSensorIMX410::v31 @ 0xC0323A78（analog node／digital trim）
  → XC_ImageSensorIMX410::v10 @ 0xC0323818  （寫 sensor registers）
```

`v8` 回傳的 packed gain：

- low 16-bit：sensor analog gain code；
- high 16-bit：超過 sensor analog cap 後的 ISP digital multiplier。

## 4. LCG／HCG：兩種 conversion-gain 硬體狀態

### 4.1 Register 組合（CONFIRMED）

| 狀態 | `0x05E1` | `0x05A6` | `0x05A8` |
|---|---:|---:|---:|
| LCG | `0x00` | `0x29` | `0x27` |
| HCG | `0x01` | `0x2A` | `0x29` |

HCG 會在 gain compose 中扣除 OTP 提供的 HCG conversion-gain dB offset，使 HCG 成為新的低噪硬體工作基準。

### 4.2 模式相關的 HCG 切換門檻（CONFIRMED）

| gain state | 名稱 | HCG 切換點 |
|---:|---|---:|
| 0 | through / Live View | OTP `S+0x84` |
| 1 | still acquisition | ISO 640 |
| 2 | through acquisition | ISO 640 |
| 3 | standard movie | ISO 640 |
| 4 | generic movie RAW | 不自動切 HCG |
| 5 | movie RAW 8-bit | ISO 640 |
| 6 | movie RAW 10-bit | ISO 640 |
| 7 | movie RAW 12-bit | ISO 3200 |
| 8 | digital off | 不切 HCG |

因此可直接確認：

| ISO 範圍 | 靜態／一般影片 | RAW 8/10-bit | RAW12 |
|---:|---|---|---|
| 100–500 | LCG | LCG | LCG |
| 640–2500 | HCG | HCG | LCG |
| 3200 以上 | HCG | HCG | HCG |

ISO 800 在靜態、一般影片與 RAW 8/10-bit 是 HCG；在 CinemaDNG RAW12 則仍是 LCG。

### 4.3 LCG/HCG 的一般取捨

- LCG：通常有較大的滿井容量／高光空間，但讀出雜訊較高。
- HCG：通常降低 input-referred read noise、改善暗部，但可用高光空間可能減少。
- 強制提早 HCG 不會無代價增加動態範圍；它是在暗部噪聲與高光容量間交換。

## 5. Sensor analog gain

### 5.1 寫入 registers（CONFIRMED）

同一個 12-bit analog code 被寫入：

- `0x003D/0x003E`
- `0x003F/0x0040`

Sony gain law：

```text
linear_gain = 4095 / (4095 - analog_code)
```

analog code `0x0DFD`（3581）約為 7.97×、+18.03 dB。

兩份 gain register 在原廠正常路徑寫入相同值。它們可能是 sensor 內的兩個 per-frame context，但目前沒有證據顯示 fp 能用它們同幀輸出兩個不同 gain。

### 5.2 ISP digital gain

analog gain 超過 OTP 定義的 sensor cap 時，`v8` 將 analog 部分限制在 cap，剩餘增益交給 ISP digital gain。這不會增加 sensor 捕捉到的資訊，等價於後續數位乘法。

低擴展 ISO 6/12/25/50 均被 clamp 至 ISO 100 sensor gain；不會增加滿井或 RAW 高光空間。高擴展 ISO 51200/102400 超過 analog cap 的部分由 ISP digital gain 完成，不會改善訊噪比。

## 6. Normal／High Analog Readout（AR）

### 6.1 已確認的切換條件

AR 不直接由 ISO 決定，而由最終 analog gain code 決定：

```text
analog_code < 0x0DFD  → Normal AR
analog_code ≥ 0x0DFD  → High AR
```

### 6.2 已確認的 register 組合

| 組合 | `0x05E1` | `0x05E2` | `0x041F` | `0x05A6` | `0x05A8` |
|---|---:|---:|---:|---:|---:|
| LCG + Normal AR | 0 | 0 | 0 | `0x29` | `0x27` |
| LCG + High AR | 0 | 1 | `0x0E` | `0x29` | `0x27` |
| HCG + Normal AR | 1 | 0 | 0 | `0x2A` | `0x29` |
| HCG + High AR | 1 | 1 | `0x1D` | `0x2A` | `0x29` |

LCG + High AR 是原廠韌體允許的正常組合，不是研究 patch 創造的狀態。

### 6.3 AR 的合理物理解釋與界線

因為沒有公開 IMX410 register datasheet，不能把 `0x05E2/0x041F` 的電路名稱說死。依觸發條件與連動 register，最保守且合理的稱呼是「高類比增益讀出偏壓／工作點配置」。它可能調整：

- readout amplifier 的 bias／工作點；
- 高增益線性；
- 黑位與通道偏差；
- 固定圖樣噪聲；
- 讀出穩定性／頻寬。

它不是 Log、gamma 或軟體 tone curve。它在 ADC 前改變 sensor 內部硬體配置；理想輸出仍應保持線性。

## 7. 為何目前不能給出完整的「每個 ISO 對應 AR」

AR 邏輯與 register 已完全找到；缺的是每個 ISO 最終形成的 analog code。ISO→analog code 還依賴：

- OTP HCG conversion-gain offset `S+0x7C`；
- OTP live-view HCG threshold `S+0x84`；
- OTP max-analog cap `S+0x68`；
- LCG/HCG native reference codes；
- ISO calibration curve；
- analog node 與少量 ISP digital trim。

這些值由 IMX410 生產時寫入 sensor OTP，開機後載入 RAM calibration struct `S`。韌體 ROM 保存公式與規則，但不保存每顆 sensor 的全部數值。

先前保存的 `IMXCFG00.BIN` 與 `IMXOBJ00.BIN` 不是正確的 gain calibration struct，因此尚不足以逐 ISO 算出 analog code。

### 重要更正

「RAW12 約 ISO 800 開始 LCG + High AR」只是依 `+18 dB ≈ 8× ISO 100` 的理論推算，未計入 native reference、OTP、digital trim 與 HCG offset，不能視為實際資料。精確 AR 切換 ISO 必須讀取 runtime calibration 或逐 ISO 記錄最終 register。

## 8. 每台相機是否有差異

有小幅個體校準差異。固定不變的是：

- 模式的 640／3200 HCG 大規則；
- AR 判斷門檻 `analog_code = 0x0DFD`；
- 各組 sensor register 寫法。

可能因 OTP 而不同的是：

- ISO 對應的精確 analog code；
- HCG 對 LCG 的實際 dB offset；
- max analog gain；
- Live View HCG 門檻；
- 某個 ISO 檔是否已跨過 High AR 門檻。

因此發布工具應讀取 runtime 真實狀態，不應假定所有 fp 都在同一 ISO 切 High AR。

## 9. 是否值得開放設定

研究介面可以提供：

- Conversion Gain：Auto / Force LCG / Force HCG；
- Analog Readout：Auto / Force Normal / Force High。

但發布給一般使用者時，較合理的是：

- 保留 `Auto` 為預設；
- 對外只提供偏高光（LCG）／偏暗部（HCG）的策略；
- AR 維持原廠自動控制；
- 四種底層組合只留在研究／校準模式。

理由：LCG/HCG 有清楚的畫質取捨；AR 更像高 analog gain 的配套硬體設定，選錯可能只有黑位、線性或噪聲副作用。

目前已建立純邏輯控制核心：

- `imx410_gain_override.h`
- `imx410_gain_override.c`
- `test_imx410_gain_override.c`

它能產生四種完整、互相一致的 register 組合，但尚未掛入相機，也未寫入 SD 卡。

## 10. 取得實際資料的實驗

### 10.1 Register／runtime probe

逐 ISO 記錄：

- gain state；
- requested relative gain；
- HCG flag；
- final analog code；
- `0x05E1/0x05E2/0x041F/0x05A6/0x05A8`；
- ISP digital gain；
- 正確的 runtime calibration struct `S`；
- sensor mode、bit depth、fps 與溫度。

至少測 ISO：100、200、320、400、500、640、800、1000、1250、1600、2000、2500、3200、4000、6400、12800。

必須分開測：靜態 RAW14、一般影片、RAW 8/10-bit、CinemaDNG RAW12，以及未來候選的超 4K RAW12 mode。

### 10.2 影像品質測量

每個 ISO／組合拍攝：

- 多張 lens-cap dark frames；
- 均勻 flat field；
- 曝光階梯直到飽和；
- 不同曝光時間；
- 冷機與熱機狀態。

分析：

- input-referred read noise；
- 飽和值與可用高光空間；
- 動態範圍；
- row/column FPN 與 banding；
- 黑位漂移；
- CFA channel 線性；
- 暗電流、熱點與溫度穩定性。

「最佳」不能只有單一分數，應形成 Pareto 策略：高光優先與暗部低噪優先。快門／曝光時間也會影響最佳選擇：短曝光、弱訊號時 HCG 的低讀出噪聲更有價值；高光接近飽和時 LCG 更有價值。AR 則主要應依 final analog code 決定，再用實驗確認長曝光與溫度是否改變其噪聲表現。

## 11. 與使用者觀察的關聯

若使用者反映錄影 ISO 320–500 暗部很差，一般影片韌體行為可合理解釋：這是切 HCG 前的 LCG 後段；ISO 640 進 HCG 後可能反而更乾淨。

CinemaDNG RAW12 不同：它直到 ISO 3200 才切 HCG，因此 ISO 640–2500 仍為 LCG。這是最值得測試「提前 HCG」的區間，但是否整體更好仍取決於暗部噪聲改善與高光容量損失的實測結果。

## 12. 當前可信結論

```text
一條 Bayer RAW 輸出
兩種 conversion gain：LCG / HCG
連續 sensor analog gain
兩種 analog readout 工作配置：Normal / High
必要時再加 ISP digital gain
```

LCG/HCG 是雙原生 ISO 的核心硬體；AR 是高類比增益下的 sensor 讀出／bias 硬體配置。不能靠軟體增加第三套真正的 conversion gain，也不能把 digital gain 當成新增感光能力。
