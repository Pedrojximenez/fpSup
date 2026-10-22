# AutoRun.txt — 用 mem save 把鏡頭資料 dump 到 SD 卡

原程式／證據目錄：[research/lens/notes](../../../../research/lens/notes/)。筆記已集中至 fp-af-assist；下文歷史結果與限制保留。

不需要 UART、不需要 debug 模式。原理見 `EGRESS_MAP.md` / 對話:AutoRun observer 開機無條件註冊、
命令派發器零權限檢查、`mem save` 直寫 SD 卡。

## 檔案內容(放 SD 卡根目錄,檔名 `AutoRun.txt`)

```
mem save \CANARY.bin 0xC0000600,,0x100
mem save \LENSDAT.bin 0xC2F1C000,,0x5000
mem save \LENSOPT.bin 0xC2F2C000,,0x8000
```

### 語法(反編譯確認)
```
mem save [path] start_address,end_address,      ← 存區間(注意:[ ] 是說明佔位,不要真的打!)
mem save [path] start_address,,size             ← start 起 size bytes  ← 本檔用這個
```
- ⚠️ usage 印的 `[ ]` 是佔位符,**不要真的打中括號**——`strtoul("[0x..")` 遇 `[` 回 0,位址變 0、指令失敗建不出檔。
- 三欄用逗號分隔:`start,end,size`;用 start+size 就把 end 留空 → `start,,size`。shell 用空白切 token,位址那串中間不能有空白。
- path 用反斜線根目錄:`\NAME.bin`。位址/大小用 0x 十六進位。

### 三行在做什麼
| 檔案 | 範圍 | 內容 |
|---|---|---|
| `CANARY.bin` | 0xC0000600 起 0x100 | **驗證用**:dump 韌體進入點。卡上有這檔 = AutoRun+mem save 確實執行了 |
| `LENSDAT.bin` | 0xC2F1C000–0xC2F21000(20KB) | 鏡頭資料結構(見下,含 DefocusPerPulse / pps / 端點 / 能力旗標) |
| `LENSOPT.bin` | 0xC2F2C000–0xC2F34000(32KB) | 光學校正表(distortion 支撐點表在 0xC2F2D87A) |

## 位址依據(這份韌體 fp Ver.5.02)
- **鏡頭資料結構全域**:靜態引用範圍 `0xC2F1DFD8–0xC2F205C0`(331 個引用),結構大小 ~0x2228(8.7KB,
  `DownloadLensData` 存取到 `param[0x88a]`)。→ dump `0xC2F1C000` 起 20KB 完整涵蓋(前後留邊)。
- **光學表**:distortion 支撐點表確認在 `0xC2F2D87A`(執行期由鏡頭 ROM 下載);dump `0xC2F2C000` 起
  32KB 涵蓋 distortion/shading/MTF/T-value 區。
- ⚠️ 位址是**此版本**的;不同韌體版本 bss 佈局會變,換版要重新定位。

## 前提條件(重要)
1. **開機時要裝著鏡頭**——鏡頭資料是 `DownloadLensData` 在鏡頭初始化時才填進 RAM。沒鏡頭 → 那塊是空的/舊的。
2. AutoRun 在**插卡事件**觸發 → 開機後插卡,或帶卡開機。此時鏡頭早已初始化,資料就緒。
3. SD 卡要可寫(非鎖定),FAT 格式。

## 怎麼確認成功
- 拔卡,看根目錄:
  - 有 `CANARY.bin`(0x100 bytes)→ **AutoRun 執行成功**(機制確認)。
  - 有 `LENSDAT.bin` / `LENSOPT.bin` → 鏡頭資料已 dump。
- 若**連 CANARY.bin 都沒有** → AutoRun 沒觸發(可能媒體事件位元遮罩 `(param_2[3] & *param_2)`
  需要特定卡狀態,見對話結論的保留點)。這時改試:帶卡開機 vs 開機後插卡、換卡、確認檔名大小寫 `AutoRun.txt`。

## 離線解析 LENSDAT.bin(對照 dumpLensData 欄位)
結構 base = 0xC2F1E000 附近(dump 從 0xC2F1C000 起,故 base 約在檔案 offset 0x2000)。已知欄位(相對結構 base):
```
+0x64   lens_equipment (0x08X)
+0xC4   Tr1  +0xC8 Tr2  +0xCC Tr3  +0xD0 Tr4  (通訊延遲 ms)
+0xD4   zoom_encoder_division_number
+0xD8   lens_equipment
+0x2EC  lens_equipment_add
+0x2F4  MC_Equipment
+0x33C  lens_function_info
```
DefocusPerPulse / focus pps min/max/movie / backlash / 端點 等在結構更後段(dump 已涵蓋);
用 `dumpLensData` 的字串順序在 `blk_c03.c:39531` 逐欄對照 offset 即可。
LENSOPT.bin 裡找 distortion 支撐點:17×uint16 的 Q15 表(見 `DISTCONVERTER_MATH.md`)。

## 進階:同法可 dump 任何 RAM
`mem save` 是任意記憶體 → 卡。同一張 AutoRun 也能:
- dump 感光元件校正 / AF 遙測 / captureState 等。
- dump **Bayer live-view raw buffer**(`0x50000000 + idx*0x100000`,11 幀環,每幀 1MB)→
  `mem save \RAW.bin [0x50000000,,0x100000]`(這就把單張 raw 存出來,無韌體改機)。
- 讀/改設定:`mem get`(印到 console,需 UART 才看得到)、`mem set [addr] [data]`(寫記憶體)。

## 風險
- `mem save` 只讀不改,安全。`mem set` 會**寫任意記憶體**,亂寫會當機/損壞,務必小心。
- 這條路等於「單張 SD 卡 = 任意記憶體讀寫」,對機器是完全信任的。只在自己的機器、清楚位址時用。
