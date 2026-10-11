# SIGMA fp USB 模式完整解析 (Ver 5.02) — 2026-08-25

全部靜態分析,未動相機。工具:`out/MAIN_c0000000.bin` (@0xC0000000) + `out/seg1_c2ef6e00.bin`
(`.data` @0xC2EF6E00)。**注意:`.data` 不在 MAIN 影像裡,讀 0xC2EF6E00 以上一定要用 seg1,
否則會讀到垃圾。**

---

## 0. 兩個獨立的列舉,不要混

過去筆記把它們混成一個,是錯的。

### (a) 使用者面的「USB 設定值」
`usb` 指令表在 **RAM 0xC2F20CF8**,7 × 8 bytes `{name*, handler}`。
名稱字串是 `char[7][4]` @ **0xC0BC7B9C**(`msc\0uvc\0ptp\0cdc\0off\0chg\0on\0\0`,4-byte stride)。
Handler 由 **FUN_c0418850** 開機時填入(所以 ROM 裡找不到指向它們的指標)。

| 關鍵字 | handler | 動作 |
|---|---|---|
| `msc` | 0xC0418938 | `FUN_c005fee0(obj, **1**, 1)` → `FUN_c0066970` 寫設定 |
| `uvc` | 0xC0418950 | `FUN_c005fee0(obj, **2**, 1)` |
| `ptp` | 0xC0418968 | `FUN_c005fee0(obj, **3**, 1)` |
| `chg` | 0xC04189A8 | `FUN_c005fee0(obj, **4**, 1)` |
| `cdc` | 0xC0418980 | `FUN_c002c268()` + `FUN_c002c420(obj, **2**)` + 開一個 console task |
| `off` | 0xC0418990 | `FUN_c002c268()` + `FUN_c002c420(obj, **1**)` |
| `on`  | 0xC04189C0 | `FUN_c002c268()` + `FUN_c002c420(obj, **0**)` |

前四個寫的是**選單設定**(Mass Storage / Webcam / Camera Control / 充電);
後三個繞過設定直接驅動 gadget(`FUN_c002c420` → `FUN_c002dbb8` → `FUN_c002c850`)。

### (b) gadget 選擇器的「模式號」
`FUN_c0031910(mode)` → `FUN_c0031a40` → `FUN_c0031c10`,兩處相同的 switch:

| mode | 建構路徑 | 類別 | 每模式 class handler |
|---|---|---|---|
| **4** | FUN_c0034270 → **FUN_c003b7b0** | MSC | 0xC0034398 |
| **5** | FUN_c04dc4c0 → **FUN_c04e9148** | PTP | 0xC04DBC10 |
| **8** | FUN_c003f4a8 + FUN_c003ecb0 → **FUN_c003e1c8** + **FUN_c003f9d0** | UVC + UAC | 0xC003E028 |
| **12** | FUN_c003c410 → **FUN_c003bab8** | CDC | 0xC003C4A0 |
| **0x11** | 無 gadget(`FUN_c0031858` 直接卸載) | — | — |
| 其他 | **FUN_c00333d0** | Vendor ff/ff/ff | 0 |

> 舊筆記 `USB_GADGET_REGISTRATION.md` 寫「PTP=5, MSC/CDC=8, UVC=0xc」——**錯的**,已修正。

註冊入口 `FUN_c00328b8(desc_set)`:掛到 `0xC3078BB0+0x714`;若 `[+0x704]!=0` 就用
`0xC2EFAD70` 的 {VID, PID, bcdDevice} 覆寫描述元(ROM 範本一律是佔位的 0x296B/0xFFFE)。

---

## 1. 六組描述元集合(完整內容)

ROM 範本池:**0xC072AF00–0xC072B480**(除 PTP 外全部),PTP 自己一份在 **0xC0CF3700–0xC0CF3820**。
每組由對應 builder 用 `ldm/stm` 逐段組出來,再呼叫 `FUN_c00328b8` 註冊。

三種速度都備齊:
* **FS** bcdUSB 0x0200、mps0 64、bulk mps 64
* **HS** bcdUSB 0x0200(SS 硬體時改寫成 0x0210)、bulk mps 512
* **SS** bcdUSB **0x0320**、mps0 = 2^9 = 512、bulk mps **1024**、每個端點後面接
  `SS_EP_COMPANION`(`06 30 03 00 ...`,bMaxBurst=3)
* **BOS** 42 bytes / 3 caps:USB 2.0 Extension(type 2)、SuperSpeed(type 3,
  speeds bitmap 0x0e = FS/HS/SS,U1=0x0a,U2=0x03ff)、Container ID(type 4,
  UUID `00112233-4455-4677-8899-aabbccddeeff`)

### MSC — mode 4 (builder FUN_c003b7b0, staging 0xC307A0C0)
* 裝置類別 `00/00/00`(per-interface)
* **1 個介面**:#0 alt0,`08/06/50` = Mass Storage / SCSI transparent / **Bulk-Only**
* **2 個端點**:`0x01 OUT bulk`、`0x82 IN bulk`
* config:FS/HS **32** = 9+9+7+7;SS **44** = 9+9+2×(7+6)

### PTP — mode 5 (builder FUN_c04e9148, staging 0xC3774820)
* 裝置類別 `00/00/00`
* **1 個介面**:#0 alt0,`06/01/01` = Image / Still Image Capture / **PIMA 15740**
* **3 個端點**:`0x01 OUT bulk`、`0x82 IN bulk`、`0x83 IN interrupt`(事件通道)
* config:FS/HS **39** = 9+9+7×3;SS **57** = 9+9+3×(7+6)
* 這是相機平常的模式,也是我們 vendor 通道寄生的宿主。

### UVC + UAC — mode 8 (builders FUN_c003e1c8 + FUN_c003f9d0)
* 裝置類別 `ef/02/01` = Miscellaneous / Common Class / **IAD**
* **IAD #1** first=0 count=2,`0e/03/00` Video Interface Collection
  * iface **#0** `0e/01/00` VideoControl,**0 端點**
  * iface **#1** `0e/02/00` VideoStreaming,1 端點
* **IAD #2** first=2 count=2,`01/02/00` Audio
  * iface **#2** `01/01/00` AudioControl,0 端點
  * iface **#3** `01/02/00` AudioStreaming,0 端點(等時端點掛在 alt setting 上)
* config **156** bytes,**nIface = 4**
* mode 8 的 dispatcher 先 `FUN_c00338a8(mode, 0x2a, {1,1,1})` 再 `(mode, 0x2a, {2,1,1})`,
  也就是註冊兩個 function 再組描述元。

### CDC — mode 12 (builder FUN_c003bab8, staging 0xC307A0C0,與 MSC 共用)
* 裝置類別 `02/00/00` Communications
* iface **#0** `02/02/01` = CDC / **Abstract Control Model** / AT-command
  * 1 端點:`0x83 IN interrupt` mps 64 interval 11
* iface **#1** `0a/00/00` = **CDC-Data**
  * 2 端點:`0x01 OUT bulk`、`0x82 IN bulk`(HS mps **512**)
* 類別功能描述元 @0xC072B298:
  ```
  04 24 02 00        ACM,            bmCapabilities = 0
  05 24 06 00 01     Union,          master=0  slave=1
  05 24 01 00 01     Call Management, bmCap=0  dataIface=1
  05 24 00 10 01     Header,         bcdCDC = 0x0110
  ```
* config **67** bytes,**nIface = 2**
* 主機端就是 CDC-ACM(`USB_DEBUG`,VID 0x296B / PID 0x9998)。

### Vendor — 預設 (builder FUN_c00333d0, staging 0xC30792C8)
* 裝置類別 `ff/ff/ff`,iface #0 也是 `ff/ff/ff`
* 端點範本:`0x01 OUT bulk`、`0x82 IN bulk`、`0x83 IN interrupt`
* config:FS/HS **32**(2 端點);SS **50**

---

## 2. ★ 韌體的 gadget 從不使用 EP 0x84 / EP 0x05

把兩個 ROM 描述元池裡**每一個** 7-byte 端點描述元都列舉過(22 個):

```
使用到的端點位址 = { 0x01 OUT, 0x82 IN, 0x83 IN }
EP 0x84: 不存在      EP 0x05: 不存在
```

我們 USB shell 的 `EP 0x84 IN` / `EP 0x05 OUT` **不屬於任何韌體註冊的 gadget**。
它們是 hook `0xC04DC618`(PTP builder 的呼叫點)插進去的第 2 個介面,端點靠 worker
自己 `FUN_c01e62a9(4)/(5)` + `DALEPENA |= 0x600` 手動啟用。

**這就是為什麼錄影模式的重設(`FUN_c01e62a8(0)` 把 DALEPENA 打回 0x3)會殺掉我們、
而 PTP 和 CDC 活得好好的** —— 它們的端點在韌體自己的表裡,重設之後韌體會自己重建;
我們的不在,沒人幫我們重建。

---

## 3. 充電模式的實作

充電**不是一個 gadget 類別**,是 config 描述元的電源欄位。依 `*(0xC3078BAC)` 這個
速度/電源等級索引查兩張表:

```
FUN_c0032320() → 0xC072AF6C[idx]  = bMaxPower
FUN_c0032348() → 0xC072AF80[idx]  = bmAttributes

idx      0         1         2         3         4
bMaxPower 1        0         0x32      0xFA      0x1C2
          (2mA)    (0mA)     100mA     500mA     900mA
bmAttr   0xC0     0xC0      0x80      0x80      0x80
         self     self      bus       bus       bus
```
* `0xC0` = self-powered(相機吃電池,不跟主機要電)
* `0x80` = bus-powered → 主機才會撥電流
* 500 mA = USB 2.0 上限,900 mA = USB 3.0 SuperSpeed 上限

**降級規則** @0xC0032E34:輸出 *other-speed* config 時,`bMaxPower` 若是 `0x1C2` 或
`0xFA` 一律改寫成 `0x32`(100 mA)—— 另一個速度不保證拿得到那麼多電。

`usb chg` 把選單設定寫成 4,相機就選 bus-powered 的高電流等級;
gadget 那邊走 mode **0x11**(`FUN_c0031858`,只做卸載不註冊任何 gadget),
所以連接埠只剩「取電」用途。

### 另外兩張跟電有關的表(不同指令,別混)
**USB Type-C 資料角色** @0xC0BC7BD8,4 × 12 bytes `{short, long, value}`,
handler `FUN_c0418a38` → `FUN_c01f5138(value)`:

| 短 | 長 | 值 | 意義 |
|---|---|---|---|
| `d` | `device` | 0 | 固定當裝置(UFP) |
| `h` | `host15` | 0x0a | 當主機(DFP),1.5 A |
| `r` | `drp15` | 0x0c | **DRP** 雙角色 |
| `t` | `trysnk15` | 0x10c | **Try.SNK**,偏好當受電端 |

**USB host 模式** @0xC0BC7BB8,2 × 8 bytes,handler `FUN_c002fb10`:`hmsc`(=1)/`hoff`(=0)。
—— 相機自己當 USB host 掛隨身碟的能力。

---

## 4. 為什麼一個模式要兩個介面?哪些模式真的用了?

**用了兩個(含以上)的:CDC(2)、UVC 模式(4)。**
MSC、PTP、vendor 各只有一個。

### CDC 一定要兩個 —— 規格強制
USB CDC 規格把一個序列埠功能拆成兩個介面:
* **Communications Class 介面(#0)** 掛類別功能描述元(Header / Union / Call Management /
  ACM),並提供一個 **interrupt IN 端點**,專門送 *serial state notification*
  (DCD、DSR、break、parity/overrun error)。它不搬資料。
* **Data Class 介面(#1)** 才是真正的資料管線:bulk OUT + bulk IN。

兩者靠 **Union functional descriptor**(`05 24 06 00 01`,master=0、slave=1)綁定。
主機的 CDC-ACM 驅動找不到這組配對就不會 bind —— 所以不能省。

### UVC 也一定要兩個 —— 同樣是規格
* **VideoControl 介面(#0)** 描述裝置內部拓樸(Input Terminal / Processing Unit /
  Output Terminal),沒有資料端點。
* **VideoStreaming 介面(#1)** 帶格式/影格描述元和實際的影像端點,而且靠 **alt setting**
  切換頻寬(等時傳輸的經典作法:alt 0 = 0 頻寬,alt 1..n = 不同 payload 大小)。

因為裝置同時還有音訊,兩組介面各用一個 **IAD** 包起來,裝置類別才會是 `ef/02/01`。
fp 的 webcam 模式因此是 **4 個介面**:VideoControl + VideoStreaming +
AudioControl + AudioStreaming —— 網路攝影機**帶麥克風**。

### 一句話總結
介面數量不是設計選擇,是**類別規格規定的**:
需要「控制通道與資料通道分離」的類別(CDC、UVC、UAC)就必須拆介面;
單純搬 blob 的類別(MSC、PTP、vendor)一個就夠。

---

## 5. 這次分析用到的方法(可重用)
* `/Users/dido/.claude/jobs/aad32072/tmp/fw.py` — MAIN 影像讀取 + capstone 反組譯 +
  **movw/movt 配對搜尋**(ROM 常數不在 literal pool,一般 xref 找不到)
* `fw2.py` — 正確的記憶體映射(≥0xC2EF6E00 走 seg1)
* `calls.py` — numpy 掃全影像建 **BL/BLX 呼叫索引**(34 萬個目標),這是找 builder 的關鍵
* `extract.py` — 在函式範圍內模擬 ARM movw/movt,自動抽出它引用的所有 ROM 片段位址
