# 說明書 — 透過 USB/PTP 讀取使用者原本的 Av/Tv/ISO(路線 A:ePtpSaveMode)

目標:連 USB 後,拿到**使用者在機身上撥的原始曝光值**,而不是進 PC 控制後被覆蓋的預設值。
fp Ver.5.02。所有 opcode/位址由韌體反編譯確認(信心標於各處)。

═══════════════════════════════════════════════════════════════
## 0. 為什麼會被覆蓋(原理)
═══════════════════════════════════════════════════════════════
- 你送的「open config」= **ConfigApi(opcode `0x9035`,data-in,回 79-byte 身分 IFD)**。(舊筆記寫 0x9101 OpenApplication 是錯的,見 §1 更正。)
- 開啟後 AE 進入 PC 控制、設全域旗標 **`DAT_c32006F8 = 1`** → 覆蓋曝光。
  ⚠️ 註:旗標的確切觸發鏈(`FUN_c0502dd8`→`FUN_c0208550(1)`)是 agent 循「0x9101」追出來的,既然 0x9101 是 dead,實際觸發應在 **0x9035 ConfigApi** 的 handler 裡 —— 覆蓋行為(實機可見)為真,但內部鏈結需以 0x9035 重新確認。
- AE 迴圈(`FUN_c0208d18`)一看到旗標亮,就走「重新測光」分支(`FUN_c021a7e8`)→ **即時算一個 program/預設曝光蓋掉手動值**。
- **重點:你機身撥的值沒被刪**,只是「旗標亮著時 AE 用算出來的值」。所以要嘛讓旗標別觸發覆蓋(路線 A),要嘛在覆蓋前把原值撈出來(路線 B,另一份文件)。

═══════════════════════════════════════════════════════════════
## 1. PTP 命令參考(已確認)
═══════════════════════════════════════════════════════════════
SIGMA vendor opcode(dispatch 表 @ROM `0xC2F22F2C`):

> ⚠️ **更正(實機驗證):** agent 早前給的 `0x9101 OpenApplication` **錯了** —— router 有 code 但 GetDeviceInfo **不宣告**(宣告的 64 個 op 裡沒有任何 0x91xx)= dead/legacy。真正的「開啟」是 **`0x9035 ConfigApi`**。`0x9011 GetCamStatus` 也不在宣告清單。以下為修正版。

| Opcode | 名稱 | 方向 | 用途 |
|---|---|---|---|
| `0x1002` | OpenSession(標準 PTP) | — | 開 PTP session |
| **`0x9035`** | **ConfigApi** | data-**in** | **開 SIGMA 控制**;回 **79-byte 身分 IFD**(★ 這才是「開啟」,取代舊的 0x9101) |
| **`0x9012`** | **GetCamDataGrp1** | data-in | 讀 Av/Tv/ISO(★ 要用的) |
| `0x901a` | GetCamCanSetInfo | data-in | 可設定範圍 |
| `0x9016` | SetCamDataGrp1 | data-out | 寫 Av/Tv/ISO(PC→相機) |
| **`0x902F`** | **CloseApplication** | data-**out** | 關閉控制;handler @`0xC04F10B0` |

- **標準 PTP 曝光屬性(0x5007 FNumber / 0x500D ExposureTime / 0x500F ExposureIndex / GetDevicePropValue 0x1015)fp 全都不支援** → 所有曝光值只能走上面的 vendor 命令。
- Dispatch 是 switch `FUN_c04e4a60`(非表);data-in 群 → `FUN_c04e4868`,data-out 群 → `FUN_c04e49a0`→`FUN_c04ea4f0`(handler 表 @`DAT_c2f2315c`,16-byte 記錄 `{opcode,handler,name_str,post}`)。
- `GetCamDataGrp1(0x9012)` 內部會先做一次同步 MenuGet(刷新 live 值)再序列化回傳。

### ★ CloseApplication(0x902F)乾淨退出 —— 10-byte 酬載內容「不重要」
handler `0xC04F10B0`(併於 `FUN_c04f0f70` 尾段)反組譯確認:**完全不讀酬載**(r6=payload 存了但無 LDR),收端 `FUN_c04e8a30` 也只讀宣告 size、**無 parity 驗證**。它只做:
```
FUN_c04f4af0(PtpCmd_obj, 0)   // = 退出 PC 控制模式(ConfigApi 的反向)
obj[0x6F5] = 1                // 設旗標
return 0x2001                 // PTP OK
```
→ **送 0x902F 時附任意 10 bytes(例如 10 個 0)當 data-out 酬載即可**(要有 data phase,內容忽略)。這樣就能乾淨退出 API 模式,不用拔線。

### CamDataGroup1 結構(回傳 data phase,結構在 RAM `0xC377683C`)
SIGMA CamDataGroup 格式:`[FieldPresent 2 bytes bitmask][各欄位…][parity]`。欄位偏移(相對結構起點):

| Off | 欄位 | 型別 |
|---|---|---|
| +0x00 | FieldPresent_1(bitmask) | u8 |
| +0x01 | FieldPresent_2(bitmask) | u8 |
| **+0x02** | **ShutterSpeed (Tv)** | u8 APEX |
| **+0x03** | **Aperture (Av)** | u8 APEX |
| +0x04 | ProgramShift | s8 |
| +0x05 | ISOAuto | u8(0/1) |
| **+0x06** | **ISOSpeed (Sv)** | u8 APEX |
| +0x07 | ExpCompensation | s8 |
| +0x08 | ABValue | u8 |
| +0x09 | ABSetting | u8 |
| +0x0A | FrameBufferState | u8 |
| +0x0C | MediaFreeSpace | u16 |
| +0x10 | CurrentLensFocalLength | u16 |
| +0x12 | BatteryState | u8 |

> ⚠️ `FieldPresent` 的位元決定該欄位是否有效/存在於封包。解析時先讀 2 bytes bitmask,再依序取被標記存在的欄位。實作時建議用 SIGMA 官方 Camera SDK 的 CamDataGroup1 定義交叉核對(欄位順序一致)。

═══════════════════════════════════════════════════════════════
## 2. 位元組 → 實際值 解碼(需校準)
═══════════════════════════════════════════════════════════════
內部 AE 用 EV×1024;wire byte ≈ **EV×8**(`ctx+0x37 = Av×8`)。**零點 offset 韌體未 dump 出,務必校準**。RE 推導的公式(offset 假設為 0,先當起點):
```
Fno      = 2^(AvByte / 16)                 # f/1.4→8, f/2→16, f/2.8→24, f/8→48
ISO      = 3.125 × 2^(SvByte / 8)          # ISO100→40, ISO3200→80, ISO6400→88
Shutter  = 2^(−TvByte / 8)  秒             # 1s→0, 1/60→≈47, 1/1000→≈80
ExpComp  = ExpCompByte / 8  EV
```
**★ 校準步驟(必做一次)**:機身撥三個已知值(例:ISO 100 / f/2.8 / 1/100s),讀出三個 byte,解出線性映射 `EV = (byte − b0)/8`(b0=各欄位零點)。之後就能精確反算。SIGMA 官方 SDK 也有對照表可核對。

═══════════════════════════════════════════════════════════════
## 3. ePtpSaveMode(路線 A 的核心變數)
═══════════════════════════════════════════════════════════════
- 使用者設定 `cam_ptp_savemode`,**值 {0,1,2},預設 0**,storage RAM `0xC3758C48`(1 byte);伴隨 `cam_is_ptp_mode` @`0xC3758C45`。
- 由名稱與 3 值範圍研判:**它選「PTP 進入時如何對待設定」** —— 很可能 0=重設成預設(現況)、1 或 2=保留使用者設定。
- ⚠️ **未在韌體證實 value→行為的分支點**,所以**這是要你實機驗證的假設**。

**怎麼設定(依可行性由易到難,逐一試)**:
1. **相機選單**(最穩):找 USB/連線相關設定裡有沒有「PTP 儲存模式 / PTP Save」之類選項,把它從預設改成 1(或 2)。若選單有,這是首選。
2. **Shell / AutoRun**(選單沒有時):此設定走 shell user-setting 系統(`ShellUserSettingAccessor<ePtpSaveMode>`)。可嘗試用 `setting` 相關 shell 指令設定,或最後手段 AutoRun `mem set 0xC3758C48 1`(注意:此位址是 shell 鏡像,live 值走 user-settings 物件,mem set 未必被邏輯讀到 —— 未驗證)。
3. **PTP**:檢查是否可經 SetCamDataGrp2~6 之一寫入(本輪未定位到對應欄位)。

═══════════════════════════════════════════════════════════════
## 4. 完整操作流程
═══════════════════════════════════════════════════════════════
```
前置:機身撥好你要保留的 Av/Tv/ISO(手動模式)

實驗迴圈(ePtpSaveMode = 0 → 1 → 2 各跑一次):
  1. 設定 ePtpSaveMode = N(用 §3 的方法)
  2. USB 連線
  3. PTP OpenSession (0x1002)
  4. SIGMA ConfigApi (0x9035, data-in)     ← 開啟控制;覆蓋旗標在此觸發
  5. GetCamDataGrp1 (0x9012)               ← 讀回結構
  6. 解析 +0x02 Tv / +0x03 Av / +0x06 Sv,用 §2 公式反算
  7. 比對:讀回的值 == 你機身撥的原值?
      - 相等 → 這個 ePtpSaveMode 值就是答案(路線 A 成立)
      - 不等(是預設值)→ 換下一個 N
  8. CloseApplication (0x902f) / CloseSession
```

**判讀**:
- 若某個 N(1 或 2)讓步驟 6 讀到**你撥的原值** → 完成。之後正式流程就是「開機前設好 ePtpSaveMode=N」→ 每次連線 GetCamDataGrp1 直接拿原值。
- 若 0/1/2 全都回預設值 → **路線 A 不成立**,改走路線 B(在 OpenApplication 前用 AutoRun `mem save` 撈 menu 設定模型,或讀最後一張照片 EXIF)。

═══════════════════════════════════════════════════════════════
## 5. 實作骨架(接你現有的 PTP transport)
═══════════════════════════════════════════════════════════════
```python
# 假設你已有 PTP transport(libusb/gphoto2/自寫),能送 operation + 收 data phase
SESSION=1
ptp.open_session(SESSION)                      # 0x1002
ptp.command_with_data_in(0x9035)               # ConfigApi (開啟, 回 79-byte 身分 IFD)
data = ptp.command_with_data_in(0x9012)        # GetCamDataGrp1 -> 回傳 CamDataGroup1 bytes

# data[0..1] = FieldPresent bitmask;之後才是欄位
fp1, fp2 = data[0], data[1]
tv, av, progshift, isoauto, sv, expcomp = data[2:8]

def fno(av):  return 2**((av - AV0)/16)        # AV0/SV0/TV0 = 校準得的零點
def iso(sv):  return 3.125 * 2**((sv - SV0)/8)
def shutter(tv): return 2**(-(tv - TV0)/8)     # 秒
print("Av byte=%d -> f/%.1f" % (av, fno(av)))
print("Sv byte=%d -> ISO %d" % (sv, round(iso(sv))))
print("Tv byte=%d -> 1/%.0fs" % (tv, 1/shutter(tv)))
ptp.command_with_data_out(0x902f, bytes(10))   # CloseApplication (酬載10 bytes,內容忽略)→ 乾淨退出
```
> `command_with_data_in` = 送 operation container(code 0x9012,無參數)後,收 data container,取其 payload。CamDataGroup1 payload 即上表。

═══════════════════════════════════════════════════════════════
## 6. 信心 / 未解
═══════════════════════════════════════════════════════════════
- **已確認**:opcode **0x9035 ConfigApi(開啟)/ 0x9012 GetCamDataGrp1 / 0x902F CloseApplication** 與 handler(0x902F@`0xC04F10B0`);CloseApplication 忽略酬載、只做 mode-exit;fp 無標準 PTP 屬性;CamDataGroup1 欄位偏移(Tv+2/Av+3/Sv+6);結構 RAM `0xC377683C`;覆蓋機制(旗標 `DAT_c32006F8` gate AE 重算);ePtpSaveMode 註冊(3 值,storage `0xC3758C48`)。
- **未證實(要實機測)**:①ePtpSaveMode value→行為對照(路線 A 成敗關鍵)②各 APEX byte 零點 offset(§2 校準補上)③如何從 PTP/選單設定 ePtpSaveMode 的最穩路徑。
- 若路線 A 失敗:見「路線 B」(OpenApplication 前 `mem save` menu 設定模型 / EXIF)。要我把路線 B 也寫成說明書就說一聲。
