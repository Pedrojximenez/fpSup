# fp 的 PDAF shell 指令與 PD 行幾何:兩道閘都關著(附 A7III 對照)

日期:2026-10-11。起因:網友問「`pdaf caf`/`pd_*.csv` 能不能在 UHD CDNG 錄影時觀察 DiffPh?PD 行讀出有沒有寫進錄影模式?」
方法:韌體映像 capstone 反組譯 + `research/imx410/captures/NIKON_D80_preformat_2026-08-17/` 的 IMXOBJ00/IMXCFG00 傾印;經獨立子代理對抗式複驗。全程離線，未碰相機。
英文版:[PDAF_SHELL_AND_PDLINE_GATES_2026-10-11.en.md](PDAF_SHELL_AND_PDLINE_GATES_2026-10-11.en.md)

## 結論

- **(a)** `pdaf caf/sequence/image/invalid` 不是指令，是 `af dbg` 的除錯位元;真正量 DiffPh 的 `af msr pddef` 被 AF model `+0x184`(無條件回 0)擋掉，**預設靜默不做事**。
- **(b)** PD 行幾何在 fp 上**任何模式**(錄影、靜態)都不存在:感光元件資訊 `+0xFC`(=「支援 PDAF」旗標)在 IMX410 是 0,幾何 getter 根本不會被呼叫;就算呼叫，IMX410 的 `+0xBC` 也是空函式。
- 與 8/18 RAW 掃描([調查報告](SIGMA_FP_PDAF_INVESTIGATION_REPORT_2026-08-18.md))、9/27 重審([跨機身](CROSSCAM_PDAF_FEASIBILITY_2026-09-27.md))結論一致;本文新增的是 `+0xFC` 旗標與 pddef 閘。

## 1. `af msr pddef` 與 pdaf 除錯位元

- `setParam @ 0xC0233A98` 閘(0xC0233AAC 起):`bl c02a4398; ldr r3,[r7,#0x20]; add r3,#0x184; ldr r3,[r3]; blx r3; cmp r0,#0`。與 `CalcCafDriveSpeed` 的閘逐字相同。
- 物件 = 靜態單例 `0xC3404678`(FUN_c02a4528 建構，先 `0xC096B150` 基底 `AfMgrModelSingleOem_Sig`,再 `0xC092B8D0` 子類)。`+0x20` 存的是 vtable **表頭**(字 0 = 0、字 1 = typeinfo),`+0x184` 相對表頭。
- `0xC092BA54 = 0xC029BA08`(基底同值、子類未覆寫);本體 `mov r2,#0; mov r0,r2; bx lr`,無分支、不讀全域。
- 錯誤訊息 `###ERROR### cannot be executed the function is disabled.` 走 `FUN_c022cbf0(0x40,…)`:需已註冊輸出回呼(0xC33D30E4)**且**除錯位元 0x40(`af dbg 1 7`,"measure")打開才會印。⚠ 先前回覆說「會印錯誤」是錯的。
- 四個 pdaf 字串在說明表 0xC0BAD2BC 第 17~20 項;`af dbg`(FUN_c03dca18,命令表 0xC0BAE014)參數 1:0=reset、1=printData、2=setData;n → 遮罩 1<<(n-1),寫 0xC3207030。
  - 0x10000 sequence:DoOneShotRanging、DoContShooting、isExecOnPdafData
  - 0x20000 image:calcJudgeImageParamaeter、calcJudgeImageYuvCheck、FUN_c0283df8
  - 0x40000 invalid:**靜態找不到讀取者**(死旗標)
  - 0x80000 caf:CafPdDriveMain、CalcPdCafDriveDir、CafMode5_*
  - 都只是 PDAF 路徑上的除錯輸出，路徑不跑就沒作用。
- 另:`af msr` 不是唯讀，可能進 S2 拍攝流程。

## 2. PD 行幾何(`PDAF size=… line=…`)

- 印出者 `calcJudgeImageParamaeter @ 0xC0283830`;欄位 `param_4[0x27..0x2B]` 來自 `FUN_c0312ac8` 從 0xC343A68C 複製的 0x14 bytes(0xC343A68C 唯一寫入者就是它)。
- `FUN_c0312ac8` 閘 @0xC0312AE4:`ldrb r0,[r0,#0xFC]`,r0 = `FUN_c0322020()` = 感光元件資訊結構 0xC2F1E654 → 讀 **0xC2F1E750**。
  - 開機由 ROM 0xC0B5F89C 初始化(0xC0322F88)為 **0**;傾印也是 0;無其他寫入者。
  - IMX455 同欄位來自 0xC0B728A4,值 **1**。→ `+0xFC` 實質是「感光元件支援 PDAF」旗標。
  - `PdafCorrect`(FUN_c030fb20)同樣被 `+0xFC` 擋住。
- `0xC3201B14+0x18` = IMX410 物件:FUN_c0311448 寫 `[+0x18] = FUN_c0322e48(0)` → 固定 0xC343B588;`+0xD0` = 0xC0B5FCC0(typeinfo "XC_ImageSensorIMX410")。傾印吻合(+0 = 0xC2F1E654)。
- 閘就算開:IMX410/基底 `+0xBC` = 0xC0322330(`XC_ImageSensor::v45`)`push{r4,r5}; mov…; nop; nop; pop; bx lr`,不寫輸出;`+0xC4`(0xC0322370)也空。呼叫端 Face(0xC027B4B0)先從全 0 的 ROM 0xC0921A1C 複製 0x800 bytes 進緩衝 → 幾何欄位是 0。
- IMX455 `+0xBC` = 0xC0329BC0 是真實作:FUN_c032c4a8 按模式查 0x5C bytes/筆的 PD 記錄表。
- 沒有其他來源:IMX410 `+0xD8` 持有物件(0xC343B67C)只指向模式表 0xC0B5FDAC(0x46 筆),沒有 IMX455 那張 PD 表(FUN_c032c710);傾印裡 +4 = 1 是 guard 字。fp 韌體裡也有 IMX455 第二單例(FUN_c0322e48(1) → 0xC343B6AC),這條路徑不用。
- `calcJudgeImageParamaeter` 回傳值只看 FUN_c02aa7c0 vtable +0x20("sensor modes that cannot use phase detection"),不看幾何。

## 3. Sony A7III 4.04 對照(摘要)

詳見 `sony_a7m3/a7m3-re-20260904/outputs/sony_a7iii_v404_imx410_pdaf_reverse_comparison.md` 與 `…/sony_a7iii_phase_data_route_followup.md`。

| | A7III | fp |
|---|---|---|
| IMX410 驅動 | RTTI `C_ImagerCtrl_IMX410` | `XC_ImageSensorIMX410` |
| 暫存器重疊 | fp 161 個模式暫存器中 155 個出現在 Sony 寫入表(96.3%);最佳配對 144/155 值相同 | — |
| 一般讀出 | `0x003D–0040`、`0x041F`、`0x05E2` bit0 | 相同 |
| ZAF 曝光 | `SetExposure_ZAF`:`0x000B–0010`、`0x0036` | 靜態表與已定位動態寫入未見 |
| ZAF 讀出 | `SetRead_ZAF`:`0x0047–004A`、`0x0424`、`0x05E2` bit1(A7C 2.03 相同) | 未見 |
| 下游 | DFE ZpdPre/FOPD → AFMAP、ZPD 缺陷/擬合緩衝、`A_CAP_RAW_PHASE_DIFF_INFO` 有處理程式 | 無對應;`+0xFC`=0、`+0x184`=0 |
| VC1 | DFE 輸出封包器 `Ofmt_Mwrap`,**不是**感光元件原生 PDAF 通道 | — |

意義:A7III 的相位 AF = 感光元件 ZAF 讀出設定 + DFE 相位抽取 + 校正資料，三者齊全;fp 三樣都沒有。
仍未證實：fp 晶圓有沒有遮罩(A7III 有 693 點不代表 fp 的版本也有)。唯一有鑑別力的實驗是在 fp 上對 `0x0047–004A` 做最小化讀回/ACK 測試;改讀出視窗曾卡機，未做。「fp 未見」只限已查範圍，不是整份 binary 的窮舉。

## 4. 對網友方案的判讀

- 有號離焦直接餵 0x9413:資料源不存在。強改 `+0x184`/`+0xFC` 只會讓程式讀到 sentinel `-0x80000000` 或全 0 幾何。
- 主體鎖定 + 保持再修正，用 CDAF/DFD 統計([DFD_VIA_AF_STATS](DFD_VIA_AF_STATS.md))驅動 0x9413:可行方向。
- ⚠ 0x9413 錄影中可用，我方仍只是閘程式的強推論([PTP_FOCUS_RECORDING](PTP_FOCUS_RECORDING.md)),未實機驗證。
