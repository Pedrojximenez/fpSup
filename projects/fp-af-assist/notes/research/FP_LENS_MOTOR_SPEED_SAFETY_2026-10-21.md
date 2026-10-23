# fp 5.02 鏡頭馬達提速：離線可行性與安全邊界

2026-10-21。使用者正在使用相機，本次全程離線：只讀既有韌體與歷史 dump，沒有開啟 USB／socket、呼叫相機指令、部署程式或移動鏡頭。使用者確認研究 fp 上的鏡頭，未指定目前鏡頭型號。

## 結論

**有控速接點，也存在一般最高速度與影片速度不同的鏡頭；尚無證據能保證突破影片額度後的持續運作安全，或給出通用安全加速百分比。**

較保守的研究方向是先找出實際驅動速度是否低於該鏡頭、該模式的原廠額度，再改善範圍內的速度規劃與搜尋距離。若已達該額度，就不能僅憑另一模式較大的數值宣稱仍有安全空間。超過鏡頭宣告的一般最高值，現階段沒有支持證據。

## 1. 從兩份原始 dump 重讀的速度額度

| 歷史鏡頭 | 最低 pps | 一般最高 pps | 影片 pps | 一般／影片比值 | 使用延伸速度欄位 |
|---|---:|---:|---:|---:|---|
| SIGMA 28mm F1.4 DG HSM Art 019 | 200 | 37,000 | 12,000 | 3.0833 | 否 |
| Panasonic LUMIX S 40/F2 | 480 | 25,920 | 20,160 | 1.2857 | 是 |

pps 是韌體診斷中的 pulses per second。這些是**鏡頭資料中的速度額度**，不是本次量得的運動速度、磨耗／溫度額定，也不代表目前裝著其中一顆鏡頭。比值僅比較資料欄位，不能當作 AF 速度提升倍數。

來源是兩個 `research/lens/captures/*/HEAP34.bin`。本次從已初始化的 native-L 物件 `F=0xC3476414` 驗證 vtable `0xC0B8EEEC`，再讀 `F+0x54`，兩份歷史資料都指向 `0xC3464980`，檔內 offset `0x64980`。用鏡頭名稱、type code、serial 與既存 identity JSON 交叉核對，沒有把 `_LENS_DATA_:` 字串所在位置當作 struct base。

`FUN_c03344b0` 從鏡頭通訊資料解析以下欄位，`dumpLensData` 的診斷字串確認其名稱：

| 用途 | 一般欄位 | extended 欄位 |
|---|---|---|
| 最低 | `+0x78` | `+0x13C` |
| 一般最高 | `+0x7C` | `+0x140` |
| 影片 | `+0x80` | `+0x144` |

選擇依 `lens_data+0x64` 的 bit 23：`FUN_c033a848(data,0x17)`。28mm 不支援時，extended 三欄都是 `0xFFFFFF`，**不是可用的 16,777,215 pps 上限**。40mm 支援且三個 extended 值與一般值相同。getter `C033DE20/DE58/DE90` 與位元選擇已對照 ROM 指令。

## 2. 原廠如何把速度送給鏡頭

絕對位置驅動鏈：

```text
C035FFC0(target, direction_mode, speed_request)
  → C0360430 → C03324D8 → native-L C033EC80
  → driveImpl C033F050 → focusDriveTask C0340210
  → selCmdFocus C033FDA0 → CmdFocus 或 Advanced LC
```

`C033EC80` 有兩條不同分支：

- `speed_request==0`：依 lens-sync singleton `+0x157`，選一般最高 getter `C033DE20` 或影片 getter `C033DE90`。此旗標的 setter `ChangeMovieRecording` 同時向鏡頭送設定；它不是可單獨當作正在寫錄影檔的可靠旗標。
- 非零：呼叫 `C033ED98`，換算後夾在 **最低值與一般最高值**之間。這段沒有再呼叫影片 getter。

非零參數**不能直接當作最終 pps**。令 `S=speed_request`、`D=*(F->sync_data+0x24)`、`T=C032C7B8(0x77)`，ROM 對照支持：

```text
P = floor(S × D × 1,000,000 / (T × 1,000))
final_pps = min(general_max, max(minimum, P))
```

這是普通、合法輸入且中間乘法不溢位時的數學簡寫；實際為 ARM 64-bit 乘除，不能用任意大參數驗證「會被 clamp 保護」。`D` 在兩份歷史 capture 分別為 304／170，顯示相同 request 也不能跨鏡頭視為相同最終速度。本次沒有重新量 `T`，不把舊筆記的單一時序值當作目前狀態。

`AfMgrDriveScan` 的 vtable `0xC091C50C+0x18` 指向 `C0238B58`，再走：

```text
C035FE88 → C03604D0 → controller slot +0xBC C0332520
  → native-L slot +0x1C C033EF90 → C033ED98
```

此掃描路徑也使用同一換算／一般最大值 clamp。vtable words 與關鍵分支均已對照 `out/seg0_c0000000.bin`，不是只依反編譯函式命名推測。

`C0357E58` 的一般 command serializer 將最終速度低 16 bits 寫入兩個 byte；bit 23 支援時另寫高 8 bits。Advanced LC 的 `cmd_adv_lc` 同樣依能力填第 3 byte。這是原廠協定的速度請求，**這條鏈沒有直接設定馬達電壓、電流或 PWM**。鏡頭內的加減速、限流、溫度保護和是否另外夾限，機身韌體本身不足以證明。

## 3. 更正舊的「movie cap 12000」說法

`AF_AE_INTERNALS.md` 原本將 28mm 的掃描 request 算式，直接解釋為約 13,000 pps、被 movie 12,000 封頂。這個結論不能由本次核對的控制鏈支持：

1. Scan 算出的值還要經過 `C033ED98` 換算，不能直接等同線上 pps。
2. Scan 接的是 `C033EF90`，其 clamp 使用一般最高值，不是 movie getter。
3. Movie 模式設定還會傳到鏡頭；鏡頭是否自行限速，本次沒有鏡頭內部韌體或線上運動量測。

因此保留原始算式作研究線索，撤回「該掃描一定被 12,000 封頂」及其衍生的目前速度／可提升倍數。也不能反過來宣稱原廠影片 AF 已經跑到 37,000 pps。

## 4. 可以與不能稱作安全的範圍

| 方案 | 現有證據與判斷 |
|---|---|
| 實際低於該模式額度時，提高 request、保持原廠能力／額度與完成流程 | 可研究；仍需量實際速度、合焦與反向誤差，沒有現成通用百分比 |
| 縮短不必要搜尋、已知目標的移位與量測掃描分開規劃 | 可改善總時間；須維持 CDAF 收斂與原廠所有權，收益尚未實測 |
| 影片改用較大的一般最高額度 | 原廠有不同額度且非零分支可送更大值；不等於已驗證長時間追焦、噪音、供電、溫升或磨耗安全 |
| 修改鏡頭資料、能力 bit，或超過一般最高額度 | 無支持證據；可能失去正確 clamp／位寬，現階段不建議 |

**光學效果與機械安全需分開。** 對比掃描若採樣率不變，速度提高會增加每筆樣本跨過的位置，可能漏峰／多次重掃。理想等速時每樣本間距約為 `v / f_sample`；加倍 `v` 就加倍間距。這是關係式，不是本機目前採樣頻率的量測。方向翻轉、背隙與停下後影像穩定亦需另外驗。

完成 ACK、cached position、abort 被接受均不能單獨證明物理停妥。沿用 [native focus audit](FP_NATIVE_FOCUS_CONTROL_2026-09-16.md) 的完成事件與未知結果處理：原廠 AF／使用者控焦的所有權未取得、錄影狀態有競爭、傳輸結果不明時，不把下一次 move 當作補救。

## 5. 相機可供測試後，最小驗證順序

目前沒有執行以下步驟，也沒有新增可上機的提速控制器：

1. 確認實際鏡頭身份、鏡頭韌體、active speed fields 與原廠協定能力；歷史固定 RAM 位址不是新 session 的保證。
2. 用原廠動作取得 request、換算後 pps、開始／結束與影像焦點基線，先區分時間花在等待、來回搜尋、行程或停穩。
3. 只有基線低於該模式額度，才考慮在額度內逐級比較；先用行程中段、少次數、遠離端點的有界移位。測試幅度依該鏡頭和基線定，不預先稱某個百分比安全。
4. 比較同一行程雙方向的完成時間、實際影像停穩、最終誤差／回差、失敗與異音；沒有故障不等於長期壽命已驗證。CINE 長時間工作量另外評估。
5. 才考慮有限的 AF 搜尋流程比較。保留原廠限位與完成機制，不竄改能力／額度、同步模式旗標或持久設定來取得加速。

## 可重現證據

- [離線 audit.py](../../../../research/autofocus/analysis/lens-motor-speed-20261021/audit.py)：只讀既存 ROM／dump，驗證名稱／identity、native-L 指標、能力 bit、額度、協定位寬與 ROM vtable。
- [audit.json](../../../../research/autofocus/analysis/lens-motor-speed-20261021/audit.json)：兩份 dump 與 ROM 的 SHA-256、原始欄位與選中欄位；明記安全、實際速度與目前鏡頭均未驗證。
- [ROM 指令摘錄](../../../../research/autofocus/analysis/lens-motor-speed-20261021/rom-speed.asm)：Scan、三個額度 getter、預設／非零分支、換算 clamp 與 command serializer。

重播：在 repository root 執行 `python3 research/autofocus/analysis/lens-motor-speed-20261021/audit.py`，需要既有 Python capstone；只更新同目錄的衍生 JSON／ASM。兩份原始 capture 未改動。

原廠 [fp FW5.0 使用說明書 p.62–63](https://www.sigma-global.com/en/support/download/fp_Manual_FW_Ver.5.0_EN_2.pdf) 的 Focus Ring Control 是手動環轉角／轉速與位移的關係，不能用這個選單功能當作已提供 AF 馬達安全提速設定。
