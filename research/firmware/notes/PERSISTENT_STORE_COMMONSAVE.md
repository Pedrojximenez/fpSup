# 824 bytes 可以跨電源循環存活的地方 —— XC_CommonSaveData

2026-09-17,USB shell 實機量測。

**結論**:RAM 什麼都留不住;`XC_CommonSaveData` 這塊設定區留得住,
而且**不需要下任何存檔命令**,相機自己會存進 flash、開機自己載回來。

---

## 1. 位置與容量

```
基底   0xC307523C      大小 0x410 bytes (260 words)
來源   src/library/UserSetting/src/XC_CommonSave.cpp
```

`0xC307523C` 落在開機會清零的 BSS 範圍內(`0xC3000000..0xC38D6FB0`)——
所以它**不是靠 RAM 殘留**,是開機時從 flash 重新載入的。

整塊 260 words 裡只有 42 個非零。`setting readcom` 只吐得出 `levelGauge` 一項。

### 實測:207 個 word 寫入、電源循環、逐字驗證

每個 word 寫由偏移推導的值(`0xA5______`),所以「被搬位置」和「被覆寫」分得出來。

| 區段 | 存活 | 可用 |
|---|---|---|
| `+0x024 .. +0x200` | **118/119** | **472 bytes** ← 最長連續 |
| `+0x210 .. +0x280` | 28/28 | 112 bytes |
| `+0x290 .. +0x380` | 60/60 | 240 bytes |
| | **206/207** | **合計 824 bytes** |

**被清零 0 個、被搬位置 0 個。** 唯一動到的是 `+0x024`:寫 `A5002409`,
回來 `A5000000` —— **低 16 bits 被清**,那是韌體自己的一個 u16 欄位,避開即可。

→ **安全的連續區段是 `+0x028 .. +0x200`,472 bytes。**

## 2. 存檔是自動的

寫進 RAM 鏡像之後**沒有下任何命令**,電源開關重開,值就回來了。
整塊與備份比對只有 6 個 word 不同:我們寫的 4 個,加 `+0x18`/`+0x1c`(日期時間戳)。

存檔路徑 `0xC0022548` 只檢查兩件事,**沒有校驗碼**:

```
[obj+0x08] == 9        型別 id,不符就 assert
[obj+0x10] == 0x410    大小,不符就強制改回 0x410
```

所以內容怎麼變都不會被判定損壞。

## 3. 為什麼這件事重要

> **2026-09-18:這一節是設計草稿,已經做出來了,細節與草稿不同。**
> 實作、實機結果與現行數字在
> `projects/usb-shell-sup/notes/AUTORUN_STORE_BOOT.md`。三處差別:
> 表頭只剩 **1 個字的 magic**(版本與 CRC 都拿掉了,magic 改成 loader 位元組的
> sha256,改一條指令就自動失配);引導碼是 **29 條**不是估的 15-18;
> 而 loader 現在 **464 bytes**,468 bytes 的空間只剩 4 bytes。
> §4 的四個風險全部照這裡寫的處理了,只有「別人第一次開機」那條仍然是慢的。

AutoRun 最貴的是**把 304 bytes 的 loader 用 76 條 `mem set` 一個字一個字寫進 cave**
(每條約 65 ms,約 4 秒)。

472 bytes 放得下那 304 bytes。於是:

```
AutoRun 只留 bootstrap(估 15-18 條)
  → 驗 magic / 版本 / CRC
  → 從 0xC307523C+off 複製 loader 進 cave
  → 清快取、跳進去
每次開機省 ~40 條 ≈ 2.7 秒,冷開機一樣有效
```

**它不依賴任何 RAM 殘留** —— 那正是它比「暖開機跳過載入」高明的地方,後者已被
`DRAM_SELF_REFRESH_AND_WARM_BOOT.md` 的量測證明不可能。

## 4. 風險,四個都要寫進設計

1. **那片零區可能是保留欄位。** 原廠現在不用,不代表某個沒觸發過的功能不用
   (GPS、間隔拍攝、自訂模式…)。**一次電源循環存活 ≠ 永遠安全。**
   → 緩解:存 **magic + 版本 + CRC**,bootstrap 驗不過就什麼都不做,
     讓完整 AutoRun 接手。最壞情況是退回現在的開機速度,不會執行壞掉的程式碼。
2. **選單的「設定重置」會清掉它** → 要能自我重新配置。
3. **需要一次性寫入。** 對自己用是純賺,對發布是障礙 —— 別人第一次開機仍要跑完整流程。
   → 緩解:完整 AutoRun 跑完後順手把 loader 寫進設定區,下次開機 bootstrap 接手。
     搭配 `AUTORUN_INTERPRETER_AND_ABORT.md` 的 `[ctx+0x90] = 0` 就能在驗證通過時
     直接停掉解譯器,**自我配置且對發布透明**。
4. **flash 寫入次數有限** —— 只在換版本時寫,無所謂。

## 5. 量測方法

`scratchpad/commonsave_probe.py`(`arm` / `check` / `restore`)。
`arm` 會先把整塊 0x410 備份成 JSON,`restore` 逐字寫回並驗證 —— 本次還原後
與備份 **0 個 word 不同**。

相關:[[DRAM_SELF_REFRESH_AND_WARM_BOOT.md]](RAM 不留的完整量測)、
[[AUTORUN_INTERPRETER_AND_ABORT.md]](怎麼停掉 AutoRun 解譯器,含一條實機更正)、
[[AUTORUN_STORE_BOOT.md]](`projects/usb-shell-sup/notes/` —— 照這份做出來的東西)。
