# 機身端 GCSV 產生 + 主機端 lens profile 產生器 (2026-08-24)

目標:**讓其他 fp 使用者只要放 AutoRun.txt、錄影、拔卡,就直接得到 Gyroflow 能吃的檔案。**
不需要 USB shell、不需要主機端解析器、不需要自己填朝向和焦距。

前置定案在 `GYROFLOW_ORIENTATION_SOLVED.md`(朝向 `xyz`、gscale、焦距)。
這份記錄的是**工具鏈**本身。

---

## 1. 機身端:停止錄影時直接產生 `.CSV`

`codex/stage5_gyro_timestamp_hook.S`(掛在 0xC00D0794,2500 Hz 陀螺執行緒)。

錄影停止時除了寫 `A000_0NN.GYR`(二進位),再跑 `build_gcsv` 把同一份
buffer 就地轉成 Gyroflow 的 gcsv 文字,寫成 `A000_0NN.CSV`。

```
code_size 0x974 / 0xF9C   (cave 上限)
```

### v4 檔頭 (48 bytes, `<4s11I`)
```
+0x00  'GFS5'
+0x04  version = 4
+0x08  period  = 2500        陀螺取樣週期
+0x10  start                 起始時戳
+0x20  exposure_us           第一次 drain 時抓
+0x24  mode_a                ← 見下面「未解」
+0x28  mode_b
```
批次是 `GFT2`(24-byte header,含加速度三軸),樣本 `int16 X,Y,pad,Z`。

### 資料搬到 code space 的位址
```
STATE_ACTIVE  0xC072EE80    STATE_COUNT   0xC072EE84    STATE_HEAD    0xC072EE88
STATE_STARTVD 0xC072EE8C    STATE_ACCELINIT 0xC072EE90  STATE_GCSVLEN 0xC072EE94
FILE_OBJECT   0xC072EE00    FILE_PATH     0xC072EF00    GCSV_PATH     0xC072EF40
```

### 驗證(機身輸出 vs 主機解析器,逐列比對)
```
A001_015   32,823 列   不一致 0
A001_018   20,555 列   不一致 0
A001_020..025  1,935 ~ 20,451 列   全部不一致 0   (六段連拍)
A001_026/027   56,143 / 55,993 列  不一致 0       (最大單段)
```
**機身產生的 CSV 與主機解析同一份 GYR 的結果位元級一致。**

---

## 2. 主機端:`codex/make_gyroflow_lens_profile.py`

從韌體的 IMX410 模式表產生 Gyroflow lens profile,不做任何實機量測。

```python
SENSOR_ACTIVE_W = 6000 ; SENSOR_ACTIVE_MM = 35.9 ; SENSOR_TOTAL_W = 6064
covered_w  = readout_w * bin_h          # binning 是全寬取樣,不是裁切
covered_mm = 35.9 * min(covered_w, 6000) / 6000
focal_px   = out_w * focal_mm / covered_mm
```

輸出範例(FHD / 40mm):
```
clip     1936 x 1090 @ 29.970 fps
mode     106  readout 3032x1708  binning 2x2  12-bit
covers   6064 sensor columns (全寬)
focal    40.0 mm -> 2157 px   (FOV 48.3 deg)
readout  10.556 ms
```

### ✅ 已解決(2026-08-26):是 mode 106,捲簾 10.556 ms

`FUN_c032c720()`(無參數)回傳當前感光元件模式 enum —— 就是 `imager mode_now`
印出來的那個值,閒置時兩邊都回 8,實機對照過。logger 在錄影開始時呼叫它,
一段 CDNG 1080p29.97 12bit 的 clip 讀到 **106**。

所以 `GYROFLOW_ORIENTATION_SOLVED.md` 寫的 111(7.828 ms)是錯的,
差 35%。以下是當時的分析,保留紀錄。

### ⚠️ 原本的歧義
`GYROFLOW_ORIENTATION_SOLVED.md` 寫「1080p29.97 = mode 111,捲簾 7.828 ms」。
**那是把兩個候選當成一個。** 同解析度同幀率有 **兩個模式(106 與 111)**:

| | readout |
|---|---|
| mode 106 | 10.556 ms |
| mode 111 | 7.828 ms |

**焦距兩者相同**(同幾何族),所以焦距的結論不受影響;
**只有捲簾未定**。產生器現在會誠實印出兩個候選而不是挑一個。

---

## 3. 模式索引(已解決,見上)

以下是走過的兩條錯路,留著避免重走:

- `*(0xC375D840+8)` 的 field 0 給 175 = `MONIT1_60_FHD_CROP`。韌體認得這個名字,
  但它**不在那七十行的時序表裡**,所以從來不是感光元件模式。舊 logger 的註解
  把那個物件叫做模式表,它不是。
- `FUN_c0322e48(0)` 的物件:+4 是監看模式,+8 閒置時 106、錄影時 56。
  56 屬於 `2016x1344` 家族,而**那個家族沒有任何 29.97 的模式**,
  所以那是錄影時監看被拉到 120 Hz,不是感光元件。

### 原本的記錄

為了消歧義,我在 hook 裡讀 `*(0xC375D840+8)` 的 field 0 與 0x10 存進檔頭。
實機拿到:
```
mode_a 175   mode_b 3
```
**175 不在模式 id 清單裡**(0,97,98,3,121,6,...,218,219,220,221)。
所以那個欄位不是模式表索引 —— 得另外找。

`HdmiLimit` 的除錯字串印 "table %d" 用同一個指標,但顯然是不同 slot。

**影響有限**:焦距不受影響,只有捲簾停在兩個候選。

---

## 4. 今天踩到的坑:停止處理變太重 → 漏掉開始事件

`A001_019.GYR` 有 157 KB 資料,但**檔頭全是零**(version 0 / period 0 / start 0),
只有 `+0x20` 之後的曝光與 mode 有值。

→ `recording_started` 沒跑,`drain_ring` 跑了。

**原因是我自己改出來的**:停止路徑現在要建 ~700 KB 文字再寫兩個檔,
而它跑在陀螺執行緒上。在那期間又按錄影,開始事件就被吃掉。

`.CSV` 只有 202 bytes(只有表頭)其實是**正確行為** ——
`build_gcsv` 檢查 batch magic,發現是零就停,沒有硬解垃圾。

### 已加的防護
`drain_ring` 開頭檢查 `USER_BASE[0] == 'GFS5'`,不符就直接 `return_original`。
**漏掉開始事件的那一段變成沒有檔案,而不是產生一個看起來正常、解析時才爆的檔。**

### 真正的解法(未做)
Stage-6 的獨立 writer thread —— 把寫檔搬到背景,停止路徑只要交棒。
codex 裡已經寫好但沒實機測過。

### 目前的迴避方式
**停止錄影後等 2–3 秒再錄下一段。**

### 風險是有界的 (2026-08-25 實測)
相機在 **648 張 / 約 2.0 GB** 自動停止錄影(機身端分段上限,與 hook 無關 ——
陀螺資料涵蓋完整 22.46s,buffer 只用了 476 KB / 8 MB)。

所以**單段能產生的最大 payload 已知且已測過**:
```
A001_026 / A001_027   56,143 / 55,993 樣本
  → GYR 476 KB + CSV 2.06 MB    逐列差異 0
```
停止路徑處理得了最大的一段;GYR 與 CSV 的寫入時戳相差約 1 秒
(FAT 時戳只有 2 秒解析度,看不更細)。

**仍未測到的**是「大 payload + 1 秒內重錄」。風險窗口約 1–2 秒,
撞到時該段沒有檔案(防護生效),資料仍會遺失。

---

## 現況與待辦

已完成:
- 機身端 GYR + GCSV,逐列驗證一致
- 主機端 lens profile 產生器(焦距來自韌體,非量測)

待辦:
- [ ] 找到真正的模式索引欄位 → 消捲簾歧義
- [ ] 機身端 lens profile JSON(要另開 task 讀 L-mount block 0x0d 焦距;
      376 ms/read 不能放在 2500 Hz 的陀螺執行緒上)
- [ ] 畸變係數(從鏡頭自己的校正表)
- [ ] Stage-6 writer thread,消掉上面那個 race
