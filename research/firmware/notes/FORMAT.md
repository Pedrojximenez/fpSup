# SIGMA fp — FP__V502.BIN 韌體格式 (Ver.5.02, 2023-08-03)

檔案: `FP__V502.bin`  25,692,160 bytes (0x1880800)
SHA-256: `c9fa76f32f523bb2dc9a3fbda39418c31573cab6a1aa5c56d28c371862066ed8`

## 1. 容器佈局

四個區段串接，每段前面都有 0x100 bytes 的 ASCII 標頭（空白填充，以 `\n\r` 結尾）。

| 檔案位移 | 標頭 | Body 位移 | Body 長度 | 內容 |
|---|---|---|---|---|
| 0x0000000 | `LENGTH=24503296 w71c1 VER=V91 DVR=5.02 SUM=2768501654 IPL PTBL DAT1` | 0x0000100 | 24,503,040 | MAIN（含 DFI 表 + 壓縮酬載） |
| 0x175E500 | `IPL LENGTH=131072 xxxxx VER=v8bb-00000 DVR=00 SUM=7571023` | 0x175E600 | 131,072 | IPL，**未壓縮** ARM 碼 |
| 0x177E600 | `PTBL LENGTH=4096 xxxxx VER=v8bb-00000 DVR=00 SUM=2394` | 0x177E700 | 4,096 | 分割表 (`@PEI`) |
| 0x177F700 | `DAT1 LENGTH=1052672 xxxxx VER=v8bb-00000 DVR=00 SUM=166779754` | 0x177F800 | 1,052,672 | 資料區 |

**校驗**：`SUM` = body 所有 byte 的算術和（mod 2^32）。四段全部驗證通過。
`LENGTH` = 標頭(0x100) + body 長度。

## 2. DFI 段表（MAIN body 開頭，檔案 0x100）

```
0x100  "@DFI"        magic
0x104  u32  1        version
0x108  u32  0x40000000
0x10C  u32  1
0x120  段記錄 [0..]  每筆 0x18 bytes
```

段記錄 24 bytes：

| off | 欄位 |
|---|---|
| +0x00 | u32 解壓後大小 |
| +0x04 | u32 壓縮資料相對位移（相對檔案 0x300） |
| +0x08 | u32 載入位址 |
| +0x0C | u32 checksum（**壓縮資料**的 byte sum） |
| +0x10 | u32 壓縮方式（1 = LZSS） |
| +0x14 | u32 壓縮後大小 |

實際兩段：

| # | 解壓大小 | 壓縮位移 | 載入位址 | checksum | 方式 | 壓縮大小 |
|---|---|---|---|---|---|---|
| 0 | 0x02EF6E00 (49,245,696) | 0x0 | **0xC0000000** | 0xA434830A | 1 | 0x1740E00 |
| 1 | 0x00039A00 (236,032) | 0x1740E00 | **0xC2EF6E00** | 0x00CF6567 | 0x11 | 0x1D400 |

兩段在記憶體中連續：0xC0000000 – 0xC2F30800。
DFI 尾端另有 (id, size, addr) 表：`1: 0x1000 @0xC2F30800`、`2: 0x10000 @0xFFF10000`、`3: 0x400 @0xC2F31800`。
其他常數：`0xC3000000`（RAM 上緣，48 MB）、`0x008D6FB4`。

## 3. 壓縮：經典 LZSS（Okumura）

- ring buffer N = 4096，初值 0x00
- F = 18，THRESHOLD = 2，起始寫入位置 r = N − F = 0xFEE
- 控制 byte，LSB 優先；bit=1 → 字面 byte；bit=0 → 2-byte match token
- match: `offset = b0 | ((b1 & 0xF0) << 4)`，`length = (b1 & 0x0F) + 3`

解壓後需截斷到 DFI 宣告的 usize（最後一個 flag byte 會多吐幾 byte）。

實作見 `tools/lzss.py`。

## 4. 目標平台

- **ARMv7-A**（Cortex-A 級）+ VFP/NEON，little-endian
- 韌體同時含 ARM 與 Thumb 碼
- 重置向量在 0xC0000000（8 筆 `ldr pc,[pc,#0x18]`），入口 `0xC0000600`
- startup：設定 FIQ/IRQ/SVC/ABT/UND/SYS 六組堆疊 → 寫 VBAR (`mcr p15,0,r0,c12,c0,0`) → NSACR/CPACR 開放 CP10/CP11 → `vmsr fpexc, #0x40000000` 開 VFP → BSS 清零 (`0xC00006C0`) → 跳 `0xC0001C80`
- SoC 平台代號 **w71c1**（原始碼中大量 `*_w71c1.cpp` 型號分支）
- 編譯器：IAR（RTTI/vtable 佈局與字串特徵）

## 5. PTBL（`@PEI`）

```
0x00  "@PEI"
0x04  u32 version = 1
0x08  u32 entry count = 11
0x0C  entries[11]，每筆 24 bytes
```
entry：`(u32 id, u32 f1, u32 f2, u32 addr, u32 offset, u32 size)`；11 筆 offset/size 完全連續，總長 0x2BF00。
id 值：0x10000013, 0x10000011, 0x10000203, 0x10000022, 0x10000010, 0x10000012,
0x10000202, 0x10000101, 0x10000102, 0x10000200, 0x10000201。
（單位尚未確定，見待辦）

## 6. 已還原的符號資訊

- **原始碼路徑字串 394 個**（`out/source_files.txt`）— 完整 C++ 專案目錄樹
- **C++ RTTI 類別 2,462 個**含繼承關係（`out/rtti_classes.txt` / `.json`）
- **vtable 2,416 張、49,184 個 slot、14,422 個唯一虛擬函式位址**（`out/vtables.txt`, `out/vfunc_map.json`）

RTTI 記錄格式（vptr = 0xC0726FB8）：
```
+0x00 u32 vptr      = 0xC0726FB8
+0x04 char* name    （未 mangle 的類別名，含模板如 XC_Observer<...>）
+0x08 u32 type id   （指向 0xC3032xxx 的遞增值）
+0x0C 基底描述表*   （{typeinfo*, offset, flags} 陣列，flags bit4 = 結尾）
```

## 7. 其他識別

- 嵌入 **Lua 5.3** 直譯器（`LUA_PATH_5_3`, `init.lua`, `luaopen_*`）
- 檔案系統：FAT16 / FAT32 / exFAT
- 介面：USB(PTP/UVC/CDC/MSC)、HDMI。先前列出的 Bluetooth 經 fp 5.02
  韌體全域複核後無驅動／協定棧／裝置字串支持，應撤回。`WiFiMgr` 與
  `Grp5 Eye_Fi` 屬 Eye-Fi SD 卡支援；`wireless` 圖示屬無線閃燈狀態，均不能
  證明機身內建 Wi-Fi／Bluetooth。
- 多語系 UI 字串（英/日/荷/丹/芬…）

## 8. 進度

已完成：
- [x] 容器格式 + LZSS 解壓 + 四段 checksum 驗證
- [x] RTTI / vtable / 原始碼路徑符號還原
- [x] 匯入 Ghidra（JDK 21 + Ghidra 12.1.2 裝在 `tools/`），47,156 函式、15,475 具名
- [x] 四個子系統反編譯（見 `notes/research/rtos/../../rtos/notes/SUBSYSTEMS.md`）
- [x] 韌體標頭解析器定位（`analyze_firmware_bin_head_main` @ 0xC04CED60），
      支援的 key：`LENGTH= LOADADDRESS= OFFSET= VER= DVR= SUM= PID=`

- [x] IPL 基址確定（= 0x0）、開機流程、mask ROM 呼叫（0x2E000428）
- [x] **安全/簽章分析定案** → `notes/research/firmware/SECURITY.md`（無密碼學簽章，僅 byte-sum/CRC32/BCH-ECC）

待辦：
- [ ] IPL「載入→搬移到 0xFFFxxxxx→跳轉」逐指令重建（需互動式 Ghidra；不影響安全結論）
- [ ] 段 1（method 0x11）語意確認 — 目前用同一套 LZSS 解出，長度吻合但方式碼不同
- [ ] PTBL entry 單位與 id→分割區名稱對應（名稱表已在 IPL 中找到）
- [ ] DAT1 (1 MB) 內容解析
- [ ] Debug shell 的啟用條件與存取管道
- [ ] 821 個「ambiguous」`__func__` 字串的消歧義（可再命名數百函式）
