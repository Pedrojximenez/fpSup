# fp 溫度感測:ADC→°C 換算與過熱門檻(Ver.5.02,離線 RE)

2026-10-23,純離線(MAIN_c0000000.bin + seg1_c2ef6e00.bin + decomp),未上機。

## 1. 換算:查表,單位 0.1 °C

`src/library/TempAdcConversion`(FUN_c05a66a8 / c05a66d0 / c05a6750 / c05a6820 / c05a67a8):

- 感測器 id → ADC 通道(FUN_c05a66d0):0→11 `temp_lcd`、1→7 `temp_cmos`、2→5 `temp_body`、
  3→10 `temp_battery`、4→8 `temp_vtemp_b`、5→9 `temp_vtemp_t`。
  通道名表 0xC2E35A6C(`{名字, 編號}`),與 shell `adc` 的名字同一套。
- 讀值 `raw = min(adc, 0xFF)`,`°C×10 = table[raw]`(FUN_c05a6820)。
- 表(FUN_c05a6750,各 256 個 int32):
  - **body**(id 2)用表 A **0xC2DF9818**
  - **其餘**(lcd/cmos/battery/vtemp)用表 B **0xC2DF9C18**
- shell 的 `tsd temp`(FUN_c0410030)就是走這條印出「Temperature (example 10.5 degrees = 105)」,
  名字表 0xC0BC4938 證實 id↔名字:2=body、0=lcd、1=cmos、3=battery、4=vtemp_b、5=vtemp_t。

表 A(body)節錄:raw 0–34 = 118.5、64=92.0、96=74.5、117=65.0、128=60.5、172=42.5、
200=29.0、224=16.0、240=2.0、≥251 = −20.0。
表 B 節錄:raw 0–15 = 118.3、32=85.5、53=64.3、64=56.3、69=53.0、88=42.5、98=37.5、
127=25.5、160=12.0、189=0.0、≥226 = −20.0。

**方向:raw 越大越冷**(兩張表都單調遞減;NTC 接上拉的典型行為)。

先前實測換算:temp_cmos 88 → 42.5 °C、temp_body 172 → 42.5 °C、temp_battery 127 → 25.5 °C、
temp_lcd 98 → 37.5 °C(合理)。

## 2. 檢查執行緒 TempChk / TemperatureCheck

- 物件 0xC3425874(FUN_c02debc8 建構,TempChk @c02deaa8),任務名 "TempChk"、堆疊 0x2000。
- 開機時 DeviceOperation 初始化 FUN_c02dbc70 → FUN_c02dece8 啟動;
  主迴圈 TemperatureCheck::v1 @c02ded00:**每 1000 ms**、無限迴圈、**不看 app 狀態**
  (待機/錄影/選單/播放都在跑)。
- 每輪 FUN_c02ded48 讀 4 個值(0.1 °C)存到物件:
  +0x58 body、+0x5C cmos、+0x60 lcd、+0x64 battery
  → **可直接 peek 0xC34258CC / D0 / D4 / D8** 拿到韌體自己算好的溫度。
- 門檻三組(FUN_c02dec48 寫,FUN_c02dec08 取):
  +0x04 shutdown[body,cmos,lcd,battery]、+0x14 warning[…]、+0x24 recovery[…]。

### 判定

- **Shutdown**(FUN_c02ded98):`temp > shutdown` 且旗標原本為 0 → 旗標=1,並送 DeviceOperation
  事件 **0x74**;`temp < shutdown` 才清除。旗標寫進系統狀態(物件 0xC3033834,
  status+0x2C → **0xC3033878..7B**,順序 body,cmos,lcd,battery;通知遮罩 2)。
- **Warning**(FUN_c02def00):`warning == recovery` 時旗標強制 0(=停用);
  否則 `temp > warning` 設旗標,`temp <= recovery` 清除(遲滯)。旗標在 status+0x30 → **0xC303387C..7F**。

## 3. 預設門檻(資料段 0xC2F1D2DC..F0,初始化 FUN_c02e2510 / FUN_c02e2840)

| 感測器 | shutdown | warning | recovery | 備註 |
|---|---|---|---|---|
| body (表 A) | **65.0 °C**(raw ≤116 觸發,≥118 清) | 64.9 | 64.9 | warning=recovery → 停用 |
| cmos (表 B) | **64.0 °C**(raw ≤53 觸發,≥54 清) | **56.0 °C**(raw ≤64) | **53.0 °C**(raw ≥69 解除) | 唯一有效的警告級 |
| lcd (表 B) | **60.0 °C**(raw ≤58,≥59 清) | 59.9 | 59.9 | 停用 |
| battery (表 B) | **60.0 °C**(raw ≤58,≥59 清) | 59.9 | 59.9 | 停用 |

資料值:0xC2F1D2DC=560(cmos warn)、D2E0=600(lcd sd)、D2E4=530(cmos recov)、D2E8=600(bat sd)、
D2EC=640(cmos sd)、D2F0=650(body sd)。其餘 warning/recovery 由 FUN_c02e2840 設成 `shutdown−1`。
初始化時有 assert:`recovery ≤ warning < shutdown`。

執行期可用 shell `tsd threshold [body|lcd|cmos|battery] [shutdown|warning|recovery] [value]` 改
(處理函式 @c04100d0,decomp 誤命名為 "battery";會檢查大小順序),無參數時印出三組門檻。

## 4. 觸發後做什麼

- **警告圖示**:StandbySysStatusObserver::v1 @c0493990,遮罩 2 時若任何 shutdown 或 warning
  旗標為 1 → 呼叫顯示介面 slot 0x70(推斷 = 過熱圖示)。只在 Standby(拍攝/錄影待機畫面)
  的觀察者裡看到;Menu/Play 觀察者不看這組旗標。實際上平常只有 **cmos > 56 °C** 會亮圖示。
- **關機**:shutdown 旗標新設 → 事件 0x74。事件分派 FUN_c04cc008 把 0x74 交給目前事件處理器
  vtable +0x120(v72);各狀態的 v72 收尾後進 WaitPowerOff,其 v72 @c0489180 在 shutdown 旗標
  有設時顯示訊息 0xE 4000 ms 再關機(+0x19 的另一個關機原因顯示 0xC)。
  另一個來源(c02e14xx 的 case 5)也發 0x74,所以 0x74 推斷是通用「關機要求」。
- PowerOffMgr(FUN_c0024730)在關機路徑查同一組 shutdown 旗標,改硬體位元 7(用途未查)。
- **錄影中**:沒找到錄影模組直接讀 warning 旗標的程式;錄影不會因 56 °C 警告而停,
  只會在任一 shutdown 門檻時隨關機一起結束(推斷)。

## 5. 可信度

- 讀自程式碼(高):查表位址與內容、通道對應、方向、門檻數值、比較方向與遲滯、1 s 週期、
  warning 對 body/lcd/battery 停用、圖示由 Standby 觀察者依旗標顯示。
- 推斷(中):事件 0x74 = 關機、訊息 0xE = 高溫關機訊息、slot 0x70 = 溫度圖示、錄影不另外停止。
- 未驗:上機用 `tsd temp`、peek 0xC34258CC.. 或 0xC3033878.. 對照即可確認(不需要過熱)。
