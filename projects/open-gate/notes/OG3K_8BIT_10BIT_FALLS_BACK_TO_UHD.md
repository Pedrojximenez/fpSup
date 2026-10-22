# v0.2.1a 缺陷:CinemaDNG 選 8-bit / 10-bit 時 OG3K 會錄成 UHD30

2026-09-15。使用者回報。**原因已在源碼層確定;修法已實作(§7),尚未上機。**

信心:**[C]** 反編/表格 dump 確認 · **[I]** 推論 · **[?]** 未解。

---

## 1. 症狀 —— 2026-09-15 實機量化重現

`rec log-out` 會印出**上一段錄影的 `file-size`**(每幀位元組數)、幀數與 MB/s,
不用碰卡上的檔案,是這一題最好用的非破壞性探針。

v0.2.1a、OG3K 選著,只改 CinemaDNG 品質:

```
quality 0 (12-bit) →  9,196,544  = 3024x2010 x 1.5 + 79,184   ✔ OG3K
quality 3 (10-bit) → 12,630,528  = 3856x2170 x 1.5 + 79,248   ← UHD30
quality 4 ( 8-bit) → 12,631,552  = 3856x2170 x 1.5 + 80,272   ← UHD30
```

退回去的是 **1.5 bytes/px**,也就是 UHD30 的 **12-bit** profile p171 ——
連使用者選的位元深度都一起丟掉。與 §2 的 `e = &DAT_c0be5b50` 完全吻合。

### 1a. `menu SetMovCinemaDNGQuality` 的值就是 `eRawBitType` 本身 [C]

不是選單序號。同一天在原廠 FHD 上量:

```
quality 0 → 3,244,544   1936x1090 x 1.50 + 79,184    12-bit
quality 1 → 3,244,544   ← 14-bit,錄影管線沒有 → else 分支當 12-bit
quality 2 → 3,244,544   ← 16-bit,同上
quality 3 → 2,716,672   1936x1090 x 1.25 + 78,872    10-bit
quality 4 → 2,190,336   1936x1090 x 1.00 + 80,096     8-bit
```

這同時**實測確認了錄影管線沒有 14-bit**(選 1 出來的還是 12-bit),
與 `OG14_FEASIBILITY.md` §2 的離線結論一致。
第一輪用 quality 1 去測,所以看起來像「切換失敗」—— 那是選錯值,不是機制沒作用。

## 1b. 原始症狀描述

選了 OG3K,再把 CinemaDNG 品質改成 8-bit 或 10-bit,錄出來是 UHD。
選單、QS、live view 仍然顯示 OG3K。

---

## 2. 原因:picker 有三張表,我們只註冊在第三張 [C]

`FUN_c043b828`(組鍵並查表)的反編:

```c
if      (*(int *)(param_2 + 0x20) == 4) e = FUN_c043ccf8(o, &DAT_c0be5810, key);
else if (*(int *)(param_2 + 0x20) == 3) e = FUN_c043ccf8(o, &DAT_c0be59b0, key);
else                                    e = FUN_c043ccf8(o, &DAT_c0be5b50, key);
if (e == NULL) { log_error(...); e = &DAT_c0be5b50; }   /* ← 表3 第 0 筆 */
return e;
```

`param_2 + 0x20` 就是 **`eRawBitType`**(`FUN_c02DA870` 的列舉
`0→12bit, 1→14bit, 2→16bit, 3→10bit, 4→8bit`),與回放端 `FUN_c043bc68`
用同一個欄位選 8/10/12-bit 表的行為一致。所以:

| `+0x20` | 品質 | picker 表 | UHD30 的 profile |
|---|---|---|---|
| 4 | **8-bit** | `0xC0BE5810`(表1) | p131 |
| 3 | **10-bit** | `0xC0BE59B0`(表2) | p151 |
| 0 | 12-bit | `0xC0BE5B50`(表3) | p171 |

> 舊筆記 `FORMAT_REGISTRY_DESIGN.md` §2 寫「三張表 = 三種錄影格式,表3 是
> CinemaDNG」—— **不準確,收回**。三張都是 CinemaDNG,差別是**位元深度**。

`fmttable.S` 開頭就寫死只接表3:

```asm
LDA  ip, TAB3          @ 0xC0BE5B50
cmp  r1, ip
bne  pass              @ 其他表完整走原廠
```

於是 8/10-bit 時 `"OG3K30"` 在表1/表2 查不到 → 回傳 NULL →
原廠的錯誤退回路徑給出 **`&DAT_c0be5b50` = 表3 第 0 筆 = `UHD30`,profile 171,
感測器模式 7**。

三張表 26 筆已完整 dump,表3 第 0 筆確認是 `UHD30 / p171 / mode 7`。

### 2a. 為什麼畫面不是「壞掉」而是乾淨的 UHD

`og3kcanvas.S` 的錄影 case 守衛是 `r5 == 83`(profile id)。退回 p171 之後
這個守衛不成立,畫布 hook 不動作 → 錄出來是完整正常的 UHD30 片子。

但 `og3kaspect` / `og3kout` / `og3kgs` / `og3kfps` / `og3kname` / GTAB 的預覽組
都只看 **`FLAG`(選單狀態)**,不看實際解析到的 profile。所以:

- 選單、QS、HUD 仍寫 OG3K —— **UI 與實際錄的東西不一致**;
- `og3kfps` 會把 OG3K 的 nominal fps 套到一段 UHD**30** 的片子上
  → 快門角度換算錯誤 [I];
- 而且不論選了哪個格率,退回的永遠是 **30p**。

---

## 3. 位元深度在 profile 裡只有兩個字 [C]

把 8/10/12-bit 的同名 profile 三胞胎逐欄比對(65 欄全比),
**三組都只差兩個字**:

```
                +0x080 (預覽平面)   +0x084 (RAW 平面)
UHD30   p131/p151/p171     0xA / 0xA / 0x7      0xA / 0x9 / 0x7
FHD30   p135/p155/p175     0xA / 0xA / 0x7      0xA / 0x9 / 0x7
FHD60   p133/p153/p173     0xA / 0xA / 0x7      0xA / 0x9 / 0x7
```

格式碼(`FUN_c04356b0` 的 `bpp_of`):**7 = 12-bit,9 = 10-bit,0xA = 8-bit**。

而我們借的 **p83 原廠是 `+0x080 = 0xA`(8-bit)、`+0x084 = 0x7`(12-bit)** ——
這正是 `og3kcanvas.S` 已經在補 `PUT 0x80, 7` 的那一欄。

**所以 8/10-bit OG3K 在資料上只差這兩個字。**

---

## 3a. DNG 的 `BitsPerSample` 來自設定,不是 profile [C]

影片 DNG 的 IFD 由 `FUN_c06a5290` 寫:

```c
local_58 = *puVar3;                       FUN_c00ba378(p,0,0x100,...)  // ImageWidth
local_54 = puVar3[1];                     FUN_c00ba378(p,0,0x101,...)  // ImageLength
local_4e = FUN_c02da870(puVar3[9]);       FUN_c00ba378(p,0,0x102,...)  // BitsPerSample
```

`FUN_c02da870` 就是 `eRawBitType` 列舉轉位元數(`0→12, 1→14, 2→16, 3→10, 4→8`)。
**所以標籤跟著品質設定走,資料跟著 profile 的 `+0x084` 走。**

兩個推論:

1. **不能只讓 `fmttable` 接三張表就收工。** 那樣資料仍是 p83 的 12-bit 打包,
   標籤卻寫 8 或 10 → **檔案損毀**,比現在退回 UHD 更糟。
2. 反過來說,只要把 `+0x084` 設成與 `eRawBitType` 相符,**標籤與資料會自動一致**,
   不需要再去找 DNG writer。

---

## 4. 修法(未實機驗證)

### 4a. 安全修(必須做):UI 與實際不一致要先消掉

現況最糟的地方不是「不能錄 8-bit」,而是**畫面說 OG3K、錄的是 UHD30**。
最小修法是讓 `FLAG` 只在「解析度 = OG3K **且** 品質 = 12-bit」時為 1:

- `og3ksel` 已經是一個 transaction,加一個條件即可;
- 但品質是另一個 setter,使用者可以事後單獨改 → **必須同時 hook
  `eRawBitType` 的 setter**,在那裡重跑同一段 FLAG/GTAB 發布邏輯。

### 4b. 完整修:把 OG3K 註冊進三張表

1. `fmttable.S` 改成比對三個表基底,並把命中的表號鎖存到一個 RAM 字
   (例:`0xC0731C10`,0 = 12-bit / 3 = 10-bit / 4 = 8-bit)。
2. `og3kcanvas.S` 的錄影 case 依鎖存值寫平面格式:

   ```
   12-bit:  +0x80 = 7      +0x84 = 7    (= 現況;p83 的 +0x84 原廠就是 7)
   10-bit:  +0x80 = 0xA    +0x84 = 9    (+0x80 = p83 原廠值,等於不用改)
    8-bit:  +0x80 = 0xA    +0x84 = 0xA
   ```

3. 增益分派要跟著走:`FUN_c039dde8` **依位元深度**決定 gain_state
   (12-bit → 7,門檻 ISO 3200)。8/10-bit 的門檻要確認是哪一個 [?] ——
   原廠 8/10-bit CinemaDNG 的 gain_state 是 `movie_raw_8bit` / `_10bit`,
   不是 7,所以 `og3kgs.S` 直接回 1 的做法在 8/10-bit 下是否仍正確**未驗證**。
4. 機內回放:`FUN_c043bc68` 同樣用 `+0x20` 選 8/10/12-bit 回放表,
   `og3kpb` / `og3kpbrow` 的守衛要一起擴。

### 4c. 也可以直接照 fp 的設計「互斥」

韌體本來就有 `EXCL_CinemaDNGQuality` 資源(選單互斥表)。
讓「選了 OG3K 就把品質鎖在 12-bit」是最貼近原廠設計的做法,
也省掉 4b 的全部驗證成本。若不打算做 8/10-bit OG3K,這是首選。

---

## 5. 建議 —— 直接做 4b 的 1+2,不要先做 4a

原本建議「先止血再說」,查完 §3a 之後**改變**:

- **4a 反而比較貴。** FLAG 要跟品質連動,就得 hook 品質的 setter
  (`og3ksel` 掛的是解析度 setter,抓不到事後單獨改品質),而那個 setter
  還沒定位;4c 的 EXCL 互斥表是 UI 資源工程,成本更高。
- **4b 的 1+2 只有約 30 條指令**,而且兩個 hook 都已經存在,不用新掛任何東西:
  - `fmttable.S`:`cmp r1, TAB3` → 比三個表基底,命中時把表號鎖存;
  - `og3kcanvas.S`:把 `PUT 0x80, 7` 換成依鎖存值寫 `+0x80`/`+0x84` 的三選一。
- 而且 §3a 保證標籤與資料會自動一致。

**副作用是好的:** 8-bit OG3K 一幀只有 `3024×2010 = 6.08 MB`(12-bit 是 9.12 MB),
24p 只要 **146 MB/s**。慢一點的卡就錄得動 OG3K 了。

剩下的 3、4 兩步(增益分派、回放)是**實機驗證題,不是實作題** ——
先做 1+2 上機看,壞了再處理;真的壞而且難修,再退回 4a/4c 鎖定 12-bit。

---

## 6. 待驗

- 4b 第 3 步:8/10-bit 的 gain_state 與雙原生門檻 [?]。
- 退回 UHD30 時 `og3kfps` 的角度換算實際偏多少 [?]。
- 本文全部來自離線反編與表格 dump,**尚未實機驗證**。

---

## 7. 修法已實作並實機通過(2026-09-15)

照 §5 做了 4b 的第 1、2 步。**沒有新掛任何 hook,沒有改任何原廠資料。**

### 7z. 實機結果 —— 三個位元深度全部正確

冷開機裝入 v0.2.2bd 之後,`og3k_load.py --check` 判定「同一份 resident 已完整安裝」。
同一支 `rec log-out` 探針:

```
              修正前(v0.2.1a)        修正後(v0.2.2bd)      正確值
12-bit         9,196,544  ✔          9,196,544  ✔        3024x2010x1.50 + 79,184
10-bit        12,630,528  ✘ UHD30     7,676,928  ✔        3024x2010x1.25 + 79,128
 8-bit        12,631,552  ✘ UHD30     6,158,336  ✔        3024x2010x1.00 + 80,096
```

- 12-bit **零退步**(回歸通過)。
- **12,630,528 完全消失** —— 退回 UHD30 的路徑斷掉了。
- 錄影中截圖(SS__0534/0535/0536)三個深度的中央區色彩比例
  G/R = 0.951 / 0.962 / 0.962,**沒有綠偏**;3:2 滿幅、HUD 正常、29.97p。
  平面格式碼 `+0x080`/`+0x084` 寫對了。

卡片更新是**用 `fpSup/fp_usb_shell/putfile.py` 直接經相機寫卡**的,
不用讀卡機:`putfile.py <local> '\VSHL.BIN'`,再 `getfile.py` 讀回比對 sha256。
舊版備份在 `build/card_backups/pre_bitdepth_20260915/`。

### 7a. 改了什麼

| 檔案 | 改動 |
|---|---|
| `build/fmttable.S` | `cmp r1, TAB3` → 依序比 TAB3/TAB2/TAB1,用 **r1**(比完就沒用了)把位元深度碼帶到 `hit`;`hit` 開頭 `str r1, [BITLATCH]` |
| `build/og3kcanvas.S` | 錄影 case 的 `PUT 0x80, 7` → 依 `BITLATCH` 三選一,兩欄都寫滿 |
| `build/og3k_plan.py` | `BITLATCH = 0xC0731C14`、`CANVAS_PLANE`、兩個 hook 的 `OWNED`、開機初始化、兩條新的靜態檢查、`EXPECTED_PLAN_WORDS 710 → 749` |

```
BITLATCH (0xC0731C14) = eRawBitType    0 = 12-bit   3 = 10-bit   4 = 8-bit

平面格式碼        +0x080   +0x084
   8-bit            10       10
  10-bit            10        9
  12-bit             7        7
```

鎖存**只在命中 OG3K 時寫**,所以不會被別的 picker 查詢污染;開機值 0(12-bit)。
`fmttable` 原有的 `dmb ish` 一併把它發布出去。

### 7b. 驗證(離線)

- `og3k_plan.py` 靜態檢查全過,749 words。
- 兩個 payload 反組譯逐條確認:三個表比對的條件旗標正確、
  `bd8` 落尾自然接 `out`、三條路都寫滿兩欄。
- 空間:`fmttable` 240B(上限 512)、`og3kcanvas` 432B
  (上限 512 —— `ROW_LOG` 在 +0x200,剩 80B 餘裕)。
- 卡片已產出:`projects/open-gate/build/og3k_bitdepth_candidate/`
  (含 USB shell 的 debug 版,banner `fpSup-OG3K-v0.2.2bd!`)。
  出貨版:`build_og3k_ui_candidate.py --release --out <dir>`。

### 7c. 上機要測的順序

1. **12-bit 沒有退步** —— 這是回歸測試,先做。錄一段解檔,
   標頭仍是 3024x2010、`BitsPerSample` 12、`StripByteCounts` 9,117,360。
2. **10-bit** 錄一段:`BitsPerSample` 應為 10,
   `StripByteCounts` 應為 `3024 × 2010 × 10/8 = 7,597,800`。
3. **8-bit** 錄一段:`BitsPerSample` 8,`StripByteCounts` = `6,078,240`。
4. 每一段都要看**錄影預覽有沒有變綠/閃爍**(平面格式碼寫錯的徵狀)。
5. 增益:8/10-bit 下 `og3kgs` 仍無條件回 1,確認高光餘裕沒有
   回到 ISO 640 門檻(比對原廠 8/10-bit FHD 的 `BaselineExposure`)。
6. 機內回放:`FUN_c043bc68` 也用 `+0x20` 分三張表,`og3kpb` 的守衛可能要擴。
   這一項**預期會壞**,壞了不算意外。
7. 拍一張 S 尺寸 12-bit 照片,確認 p83 沒有被污染(尺寸仍是 3032x2012)。

第 6 項若難修,退路是 §4c:把品質鎖在 12-bit。

**2026-09-15 進度:1、2、3、4 已通過(見 §7z)。5、6、7 仍未測。**
