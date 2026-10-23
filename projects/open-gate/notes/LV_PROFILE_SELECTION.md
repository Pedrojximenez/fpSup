# 畫布 pid 是誰選的(2026-10-19,靜態逆向,只讀)

韌體 5.02,映像 `out/MAIN_c0000000.bin`。反編譯行號指 `out/decomp/full/blk_c0X.c`。
[驗] = 看過反編譯或組語;[推] = 推論。

---

## 0. 一句話結論

**pid 不是寫死的,也不是算出來的:是查表查出來的,而且是用「名字字串」查表。**
`LiveViewModeMgr`(單例 0xC375D840)持有一把「鍵」(0xC375D7D4,0x64 bytes:mode、AF 碼、EIS/CROP/放大鏡等旗標),
把鍵交給選擇器 `XC_LiveViewConfiguratorW71c1::v3`(**FUN_c043be68**,vtable 槽 0xC0BE44E4),
v3 依 mode 選表,把 `"MOV"` + `"AF120"` + `"EIS"` + `"CROP"` 這樣串成名字,
再到 16 bytes 一項的表裡用名字比對,回傳**表項指標**。表項 +4 就是 pid。

- 待機 = mode 1、AF 碼 0 → 名字 `"MOV"` → 表項 0xC0BE4990 → **pid 5**。
- 半按 = 同一個 mode 1,只把鍵的 AF 碼(鍵 +4)改掉(FUN_c0436978)→ `"MOVAF120"`=210、`"MOVAF100"`=227、
  `"MOVAF90"`=259、`"MOVAF80"`=258、`"MOVAF70"`=257。`"MOVAF60"` 的表項 pid 也是 5(0xC0BE49F4)。

---

## 1. 物件與資料結構

### 1.1 LiveViewModeMgr(0xC375D840,`src/library/LiveViewState/src/LiveViewModeMgr.cpp`)
建構:FUN_c0436608(blk_c04.c:36838)[驗]

| 位移 | 內容 | 誰寫的 |
|---|---|---|
| +0x00 | 選擇器 = `FUN_c04396b0(3)` = W71c1 單例 0xC375E8DC | c0436608 |
| +0x04 | 鍵指標 = `FUN_c04364a0()` = 0xC375D7D4 | c0436608 |
| +0x08 | 目前畫布(holder)。建構時 `FUN_c04362b8(+8, pid=1, 3)`,**寫死 pid 1**;之後換成 c0437630 產的畫布 | c0436608、c04368f8、c0436978(`FUN_c04386e8(+8, …)`) |
| +0x0C | 第二個畫布 | c0437668 |
| +0x10 | **選中的表項指標**(v3 回傳) | c0436608、FUN_c04369d8(36990 附近) |
| +0x14 | 選中的 DispParam 物件(v5 回傳) | 同上 |
| +0x18 | 4 個緩衝槽,每槽 0x34 | c0436d98 |
| +0xE8/+0xF8 | 依表項 +0 類別配置的緩衝池 | c04371f0 |

FUN_c04375c8 = 取 +8(目前畫布);FUN_c04376e0 = 取 +0xC;FUN_c0437060 = `*(+0x10)+8` = 表項的感測器模式。

### 1.2 鍵(0xC375D7D4,0x64 bytes)
建構 FUN_c0439428(39138);暫用鍵 FUN_c0439478(39162);旗標由 FUN_c0436b80(37110)從設定結構(FUN_c0021c40)填 [驗]

| 鍵位移 | 意義 | 來源 |
|---|---|---|
| +0x00 | **mode**:0 靜態 LV、1 影片 LV、2 錄影、3/4 靜態擷取、5 回放、6 assert | FUN_c04368f8 參數 2 |
| +0x04 | **AF 碼**:0/1/10 = 無後綴;2 AF240、3 AF120、4 AF100、5 AF90、6 AF80、7 AF70、8 AF60、9 AF30;mode 1 下其他值 → AF120 | FUN_c04368f8 參數 4、FUN_c0436978 參數 2 |
| +0x14 (byte) | EIS(設定 +0x33D) | c0436b80 |
| +0x17 (byte) | CROP(設定 [0xCD]==1) | c0436b80 |
| +0x20 | 錄影格式類型:==4 → 表 5810、==3 → 59B0、其他 → 5B50 | 設定 [9] 或 [2] |
| +0x24/+0x25/+0x26/+0x45/+0x47 | 錄影表的分支旗標 | c0436b80 |
| +0x28 | 放大鏡(≠0 走 MAG 表;==2 加 `PINP`) | 設定 [0x163] |
| +0x30/+0x40 | 放大倍率比 ×10:30..79 → MAG4、80..89 → MAG8 | 設定 [0x168]/[0x16C] |
| +0x50 | v5 選 DispParam 的另一個分支(意義依據不足) | 設定 [0xEC] |
| +0x60 | 覆蓋結構指標(類型 5:回放用寬高等) | FUN_c04368f8 參數 5 |

### 1.3 選擇器 XC_LiveViewConfiguratorW71c1(0xC375E8DC,vtable 0xC0BE44D0,`config/w71c1/LiveViewConfig_w71c1.cpp`)
建構 FUN_c043a2d8(39752)。vtable(從 +8 算起):v2 c043caf0(格率字串)、**v3 c043be68(選表項,槽 +0x14)**、v4 c043c078、**v5 c043c090(選 DispParam,槽 +0x1C)**、v6 c043afb0、v8 c043be58、v10 c043c778、v11 c043c7a8 [驗]

**v3 FUN_c043be68(blk_c04.c:40477)[驗]**:
```
if (key.mode-3 < 3  ||  picker[0] < 1) {        // picker[0] = 除錯強制 pid
    mode 0: key+0x28==0 ? c043b038 (表 4870) : c043b238 (MAG 表 4BD0)
    mode 1: key+0x28==0 ? c043b408 (表 4990) : c043b638 (MAG 表 4C50)
    mode 2: c043b828 (5810/59B0/5B50) 或 c043b988 (4D50/5050/5150/5450/5610)
    mode 3,4: c043bb20 (mode 4 → 5D70,否則 5CF0)
    mode 5: c043bc68 (4508/4548/4588)
    找不到 → 4870[0]
} else  return FUN_c043c800(picker, picker[0], 0);  // 以 pid 回查任一表
```
mode 1 名字組法(c043b408,40080 附近):`"MOV"` + AF 後綴 + (`+0x14`?`"EIS"`) + (`+0x17`?`"CROP"`),以 FUN_c043cf98 在 4990 表中做名字完全比對 [驗]。
另有 `picker[1]`(+4)= 除錯強制 AF pid:名字以 `"MOVAF"` 開頭時改用 `FUN_c043c800(picker, picker[1], "MOVAF")`(mode 0 用 `"AF"`)[驗]。
picker[0]/[1] 只由 FUN_c04395a8 / FUN_c0439608(39223/39245)寫,呼叫者是除錯殼指令 FUN_c040e828(`debugMode_On`)[驗]。

**v5 FUN_c043c090(40563)[驗]**:先呼叫 v3 拿表項,再用**表項指標落在哪張表的位址範圍**(FUN_c043d058…)決定 DispParam 物件(this+0x268…+0x560)。
→ **如果 hook 讓 v3 回傳表外的假表項,v5 會落到預設 +0x268,還會記錯誤 0x511。**

### 1.4 表項格式(16 bytes)[驗]
| +0 | +4 | +8 | +C |
|---|---|---|---|
| 緩衝類別索引(1=LV、3/4/5=影片、6=回放;c04371f0 以 3/4 分池) | **pid** | 感測器模式(FUN_c0437078 回傳此值給 `setChangeSensorMode`) | 名字字串指標 |

---

## 2. 選擇表全部內容(位址:名字 → pid / 感測器模式)[驗,由映像直接傾印]

**mode 0 靜態 LV,0xC0BE4870(18 項)**
`""`→1/8、`CROP`→3/8、`AF240`→201/0xC、`AF120`→202/0x38、`AF60`→1/8、`AF30`→204/3、`AF100`→225/0x93、`AF70`→251/0x94、`AF80`→252/0x95、`AF90`→253/0x96、`AF240CROP`→205、`AF120CROP`→206、`AF60CROP`→3、`AF30CROP`→208、`AF100CROP`→231、`AF70CROP`→254、`AF80CROP`→255、`AF90CROP`→256

**mode 1 影片 LV(待機/半按),0xC0BE4990(36 項)**
| 名字 | pid | sm | 名字 | pid | sm |
|---|---|---|---|---|---|
| MOV | **5** | 8 | MOVCROP | **7** | 8 |
| MOVEIS | **9** | 8 | MOVEISCROP | **11** | 8 |
| MOVAF240 | 209 (0xD1) | 0xC | MOVAF240CROP | 213 (0xD5) | 0xC |
| MOVAF120 | **210 (0xD2)** | 0x38 | MOVAF120CROP | 214 (0xD6) | 0x38 |
| MOVAF60 | **5** | 8 | MOVAF60CROP | 7 | 8 |
| MOVAF30 | 212 (0xD4) | 3 | MOVAF30CROP | 216 (0xD8) | 3 |
| MOVAF100 | **227** | 0x93 | MOVAF100CROP | 228 | 0x93 |
| MOVAF70 | **257** | 0x94 | MOVAF70CROP | 260 | 0x94 |
| MOVAF80 | **258** | 0x95 | MOVAF80CROP | 261 | 0x95 |
| MOVAF90 | **259** | 0x96 | MOVAF90CROP | 262 | 0x96 |
| MOVAF240EIS | 217 | | MOVAF240EISCROP | 223 | |
| MOVAF120EIS | 218 | | MOVAF120EISCROP | 224 | |
| MOVAF60EIS | 9 | | MOVAF60EISCROP | 11 | |
| MOVAF30EIS | 220 | | MOVAF30EISCROP | 226 | |
| MOVAF100EIS | 229 | | MOVAF100EISCROP | 230 | |
| MOVAF70/80/90EIS | 263/264/265 | | …EISCROP | 266/267/268 | |

(項位址 = 0xC0BE4990 + 16×序號;依序為 MOV, MOVCROP, MOVEIS, MOVEISCROP, MOVAF240, MOVAF120, MOVAF60, MOVAF30, MOVAF100, MOVAF70, MOVAF80, MOVAF90, 再來 …CROP 8 項、…EIS 8 項、…EISCROP 8 項。)
→ Jose 改的 0xD1/D2/D4/D5/D6/D8 = MOVAF240/120/30 與其 CROP;5/7/11 = MOV/MOVCROP/MOVEISCROP;21–24 是下面的 MAG PINP。

**放大鏡**:mode 0 → 0xC0BE4BD0(MAG4 29、MAG8 30、MAG4CROP 31、MAG8CROP 32、MAG4PINP 17、MAG8PINP 19、MAG4CROPPINP 18、MAG8CROPPINP 20);
mode 1 → 0xC0BE4C50(MAG4 29、MAG8 30、MAG4EIS 37、MAG8EIS 38、MAG4CROP 31、MAG8CROP 32、MAG4EISCROP 39、MAG8EISCROP 40、MAG4PINP 21、MAG8PINP 23、MAG4EISPINP 25、MAG8EISPINP 27、MAG4CROPPINP 22、MAG8CROPPINP 24、MAG4EISCROPPINP 26、MAG8EISCROPPINP 28)

**mode 2 錄影**:4D50(48 項,101–129、191–198、401–412)、5050(301–312、413–416)、5150(同 4D50 但 FHD120/100 → 361–364)、5450(DCI4K/… 365–390、443–448)、5610(類別 4,321–356、435–442)、5810(131–150、417–422)、59B0(151–170、423–428)、5B50(171–190、429–434)。全部內容在本次傾印中都有,需要時重跑 `scratchpad/tabs.py`。

**mode 3/4 靜態擷取**:5CF0 = `""`/LOW→41、12B→42、12BLOW→43、CROP/LOWCROP→44、12BCROP→45、12BLOWCROP→46;5D70 = 81…86 同構。

**mode 5 回放**:4508 = UHD 51、FHD 53、UHDCROP 371、FHDCROP 373;4548 = 61/63/381/383;4588 = 71/73/391/393(依鍵 +0x20 ==4/3/其他)。

---

## 3. 誰設 mode 與 AF 碼(=誰決定待機 / 半按)

| 呼叫點 | 函式 | 做什麼 | 角色 |
|---|---|---|---|
| blk_c03.c:114372–114389 | **FUN_c03a6570**(LiveView 模式控制) | 狀態 1→mode 0;2/0/其他→**mode 1**;3→mode 2(AF 碼取 `obj[4]+0xC`);4→mode 3;5→mode 4。AF 碼一律 0 [驗] | 進入待機/錄影/擷取。「狀態 1=STILL、2=CINE」是 [推] |
| blk_c03.c:109066 | FUN_c039ea58 | `FUN_c0436978(state, FUN_c0388238(af))`,只改鍵 +4 [驗] | **半按/AF 起動** [推:這函式處理 AF 狀態與 S1] |
| blk_c02.c:57992/57997 | FUN_c0257ee8 | AF 碼 = FUN_c0257b80(AE 程式表,每項 0x14 bytes,依曝光取 `+0/+4` 與 `+0xC/+0x10`)→ FUN_c0257d80(除錯表 DAT_c091da44 可強制,印 "change to the specified sensor mode");`obj+0x20C8==4` 時設 0 [驗] | AE 改變驅動速率時切 AF 碼 [推] |
| blk_c02.c:34632 | FUN_c022e058 | `c0436978` + `c0437078` 回感測器模式;呼叫者:AfOffSet 校正(39332)、FUN_c029bea8 "check sensor mode"(97801)[驗] | AF 偏移校正/感測器模式檢查 |
| blk_c04.c:9391 | FUN_c040e828 | `c04368f8(…,5,…)`,除錯 `rawPlay_On` [驗] | 除錯回放 |
| blk_c05.c:144085 | FUN_c05be080 | mode 5 + 覆蓋結構(類型 5,帶寬高等)[驗] | 回放 [推] |
| blk_c05.c:24238/24305/24414 | XC_SensorAdjustmentCaptureConcrete::v1 | mode 3、mode 0 [驗] | 工廠感測器調整 |

**結論**:待機 pid 5 = `mode 1 + AF 0` 查 4990 表 `"MOV"`;半按的 210/227/257/258/259 = 同表 `"MOVAF<rate>"`,
rate 是 AF 碼,由 AF/AE 程式依目前驅動速率給(FUN_c0388238 / FUN_c0257b80)[驗:查表路徑;推:AF 碼的實際語意]。
AF60 跟待機用同一個 pid 5,所以「只看 pid」分不出待機和 AF60 半按。

---

## 4. 每個建畫布呼叫點

### 4.1 FUN_c0436288(kind 3,dims = 呼叫者 +0x10)
| 呼叫點 | 函式 | pid 從哪來 | 角色 |
|---|---|---|---|
| c0437658 | **FUN_c0437630**(blk_c04.c:37634) | `*(state[+0x10] + 4)` = 目前選中表項的 pid;dims = 緩衝槽 0 的 +4 [驗] | **目前 LV 畫布**:角色跟著目前 mode,包括待機、半按、錄影、放大鏡、回放 mode 5 |

c0437630 的 15 個呼叫者:FUN_c04368f8 / c0436978(換 mode 或 AF 後重建 state+8)、c0437668(state+0xC,由 MovSigProcess FUN_c0428ab8 呼叫)、
c022e3b8、c02bad08、c02bc468、c02bc638、c0311de8、c0312158、PreExpos_s(c0316ca8)、c03eb8c8、c0686800、c0686d38、c06876b8、c0688548 [驗:呼叫關係;這些消費者各自的用途沒有逐一看]。

### 4.2 FUN_c04362b8(dims = 常數 DAT_c0bcf7b0/b4,kind 由呼叫者給)
| 呼叫點 | 函式 | pid | kind | 角色 |
|---|---|---|---|---|
| c0436644 | FUN_c0436608(LiveViewModeMgr 建構,36849) | **寫死 1** [驗] | 3 | 開機時的初始畫布(之後第一次 mode 設定就被換掉) |
| c04371ac | **FUN_c0437140(out, mode, settings, kind)**(37414) | 用 `(mode, AF=0)` 臨時建鍵 → c0436b80 → **v3** → 表項 +4 [驗] | 參數 | 「如果是 mode X,畫布長怎樣」的查詢,不改目前狀態 |
| c030fb78 | FUN_c030fb20(blk_c03.c:12418,ImagerDefect.cpp) | 參數 2:由 FUN_c030cdd0 傳入 = 擷取物件 +0x64,而它在 StillCreateFunc(FUN_c0374268,blk_c03.c:80450 一帶)寫成 `畫布 +0xB8` = PARAM +0x5C(除錯印成 `tableNo`)[驗] | 3 | PDAF/缺陷修正表。PARAM+0x5C 本身就是一個 pid [推] |

FUN_c0437140 的呼叫者 [驗]:
- FUN_c0374268(StillCreateFunc,blk_c03.c:80450/80465/80509):mode 2 / 4 / 3 → 錄影中拍照、靜態擷取的畫布
- FUN_c03755e8(80996):mode 3
- FUN_c03a0df0(110648):mode 2,算錄影相關比例
- FUN_c06a4808(blk_c06.c:133577):mode 2 或 3
- FUN_c040ef50(blk_c04.c:9650):除錯 `tableNo` 印出 pid/尺寸,mode 由指令給
- **FUN_c02d4f28(blk_c02.c:135224):kind = 2** → 走 W91c1 選擇器(0xC375F8BC)與 `XC_LiveViewFieldAngleTableModel`(FUN_c043db90 → FUN_c043dae8,**自己的 mapping 0xC0BE6540、自己的類別函式 FUN_c043dd70**,不經過 c043a158/c043a19c)。上游 FUN_c02c89b8 只在 0xC096FC24 被當成字面值引用。角色依據不足。

### 4.3 FUN_c0437af8(cfg, dims):全都是「緩衝尺寸查詢」,pid = `*(cfg+4)` = 表項 pid
建畫布 → FUN_c0435588 算尺寸 → 立刻解構。
| 呼叫點 | 函式 | 用途 |
|---|---|---|
| c0436ef0 | FUN_c0436ec8(37250) | 目前表項(state+0x10)要多大緩衝 → FUN_c04371f0 配置/檢查(超過已配置就在 LiveViewModeMgr.cpp:0x1A8 assert)[驗] |
| c043aa5c…c043ad5c、c043d30c…c043d64c | W71c1 建構 FUN_c043a2d8 與 FUN_c043d298/368/438/508/5d8 | 開機掃**所有**表項,依表項 +0 類別記錄最大值(picker[3+cls])[驗] |
| c043ec24…c043efb0、c044104c、c044111c | W91c1 建構 FUN_c043e2d8 與 FUN_c0440fd8/c04410a8 | 同上,W91c1 的表 [驗] |

→ 沒有一個 c0437af8 呼叫點產生「真正被顯示的畫布」。

---

## 5. 有沒有單一的、角色可辨的選 pid 點?

**沒有一個點同時「所有角色都經過」又「看得到角色、而且回傳值可以隨便換」。** 分析:

1. **v3 FUN_c043be68** 是 kind 3 所有「依角色選 pid」的必經點(state 更新、c0437140 查詢、c0437078 查感測器模式),而且輸入的鍵帶有完整角色(mode、AF 碼、EIS、CROP、MAG)。
   但它回傳**表項指標**,下游有三個限制:
   - v5 用表項**位址落在哪張表**選 DispParam → 表外的假表項會壞;
   - 表項 +8 = 感測器模式,會餵給 `setChangeSensorMode`;
   - 緩衝大小在 W71c1 建構時,依開機當下表項 +4 的 pid 算好,之後 c04371f0 只檢查不重算。
   v3 不經過的路徑:建構時寫死的 pid 1(c0436644)、PDAF(c030fb78,pid 來自 PARAM+0x5C)、kind 2 / W91c1 / Model 整條路。
2. 所有 kind 3 畫布最後都經過 **FUN_c043a158**(唯一的呼叫者是 c0439cec),既有的 hook 點 **c043A19C** 也在這裡。這裡只看得到 pid(r5)和 dims,看不到角色;單看 pid 也分不出待機 5 和 AF60 半按的 5。
   kind 2 的 Model 畫布不經過這裡。

### 建議做法(兩點,不改程式邏輯)
- **(A) 改表項的 pid 欄位(資料,RAM 裡的映像)**:每個表項各自獨立,同樣是 pid 5,`"MOV"`(0xC0BE4994)和 `"MOVAF60"`(0xC0BE49F4)可以分開改。
  把要區分的角色改成虛擬 pid(例如待機 `MOV`→6),v3、v5、sizing、c0437630 全部自動一致,因為表項位址沒變。
  - 時機:**要在 W71c1 單例建構(第一次呼叫 FUN_c043cc50,guard 0xC375EE64)之前改**,不然尺寸是用舊 pid 算的。
    如果虛擬 pid 借 donor 的同一列,尺寸不變,建構之後改也安全 [推]。
  - mapping 0xC0BD05D4[虛擬 pid] 要填 donor 的 PARAM 列號(否則讀到 0xFFFFFFFF),類別也要對(見 §6)。
- **(B) 依虛擬 pid 改畫布內容**:沿用 c043A19C 的 hook(r4=obj、r5=pid),針對虛擬 pid 覆寫幾何。
  虛擬 pid 本身就代表角色,所以這個 hook 不必再去猜角色。

所以**最少 1 個 code hook(c043A19C)+ 一次表資料修改(表項 pid + mapping 槽)**。
如果一定要用 code hook 判斷角色:hook v3 的回傳(vtable 槽 0xC0BE44E4,或 c043be68 的 epilogue),
按鍵(mode、+4)回傳**同一張表裡**的別的表項。不可以造表外的表項。
kind 2(c02d4f28)如果也要管,要另外 hook FUN_c043dae8(Model,mapping 0xC0BE6540)。

> 注意:0xC0BD05D4 / 0xC0BE4870… 是韌體映像在 RAM 裡的資料,不是設定區;但仍是「上機前要說明」的改動。
> 內建的除錯強制 pid(picker[0] / picker[1],FUN_c04395a8 / c0439608)對 mode 0–2 全部生效,不分角色,只適合拿來測試。

---

## 6. FUN_c043a1c8 類別(obj+0x168)— 以組語確認 [驗,c043a1c8–c043a2cc]

| 位元 | 條件 | 查詢函式(`vt+0x18` = c04397c8 讀 +0x168) |
|---|---|---|
| bit0 (1) | 1 ≤ pid ≤ 3 | FUN_c0436008 |
| bit1 (2) | 5 ≤ pid ≤ 11 | FUN_c0436030 |
| bit2 (4) | 101–129、191–198、301–312、401–416 | FUN_c0436058 |
| bit3 (8) | 131–190、417–434 | FUN_c0436080 |
| bit4 (0x10) | 29–40 | FUN_c04360a8 |
| bit5 (0x20) | 17–28 | FUN_c04360d0 |
| bit8 (0x100) | obj+0xE0(=PARAM+0x84)== 11 | FUN_c04360f8 |

筆記寫的範圍正確,只修正一處:bit0 是 **1..3**(不含 0;pid 4 沒有類別)。
**半按的 201–268 全部是類別 0**(不是 bit1),跟待機 5 不同類 [驗]。

### mapping 0xC0BD05D4(500 槽)各類別內的空號 [驗]
- bit0 1..3:**2**
- **bit1 5..11(待機類):6、8、10** ← 可以當「待機類虛擬 pid」
- bit2:**115**(191–198、301–312、401–416 沒有空號)
- bit3:無
- bit4 29..40:**33、34、35、36**
- bit5 17..28:無
- 類別 0 的空號(可當半按類虛擬 pid):0、4、12、15、16、47–50、52、54–60、62、64–70、72、74–80、87–90、95–100、130、199、200、203、207、**211、215、219**、232–250、269–300、313–320、323–326、337–340、343–346、357–360、392、394–400、449–499(共 194 個空槽)

已用槽:5→列 2、7→3、9→4、11→5、210→153、227→167、257→178、258→179、259→180、209→152、212→154、213→155、214→156、216→157。

---

## 7. 畫布建好之後,誰讀 obj+0(pid)或 obj+0x168(類別)

**讀類別(經由上面那 7 個查詢函式)[驗:呼叫點]**
- FUN_c0436008(bit0):FUN_c04293a8(MovSigProcess,blk_c04.c:27323)×2
- FUN_c0436030(bit1):**XC_DisplayAspectFrameW71c1::v2**(blk_c02.c:162864,用目前畫布 c04376e0 決定要不要畫外框)、FUN_c04293a8 ×2
- FUN_c0436058(bit2):FUN_c03a6db8
- FUN_c0436080(bit3):FUN_c03a66b0、FUN_c03a6df8 一帶
- FUN_c04360a8(bit4 MAG)/ FUN_c04360d0(bit5 PinP):c0239f48、c029ff28、c02a2838、c02a4580、c02a9128、c02a9ca0、c02bc8f0、c031acd8/c031b3a0、c03a66b0、c03a6db8、c04293a8、c042a570(各 13 處)
- FUN_c04360f8(bit8):c02a4d08、AfMgrOffsetCaf_w71c1::v1、AfMgrOffsetSaf_w71c1::v1、c02c6870、c03a6df8
- FUN_c04293a8 的邏輯:新舊畫布在「bit0/4/5 ↔ bit1」之間切換時呼叫 `skipClone`。**虛擬待機 pid 留在 5..11(bit1)才不會改變這個行為** [驗:條件;推:對畫面的影響]

**讀 obj+0 pid 數值**
- FUN_c0428ab8(MovSigProcess.cpp,blk_c04.c:27011):`*state[+0xC] 的畫布 != *目前畫布` 時在 0xE0 行 assert,並記錄 pid 與感測器模式 [驗]。兩個畫布都來自 c0437630,虛擬 pid 兩邊一致就沒事。
- FUN_c040ef50(除錯 `tableNo`)印 obj[0] [驗];FUN_c0434e08 建構時記 log [驗]。
- 全映像 `ldr …,#0x168` 只有 33 處,和畫布有關的只有 c04397cc(W71c1 畫布 v4)與 c043dc1c(Model v4);其餘的基底暫存器不是畫布 [驗:列表;推:其餘無關]。
  直接讀 obj+0 的地方沒辦法用樣式掃乾淨(`ldr rX,[rY]` 太多),**除了上面幾處,不保證沒有別的** [依據不足]。

---

## 8. 未完成 / 不確定
- AF 碼由 FUN_c0388238 / FUN_c0257b80 算出的實際語意(和格率、快門的關係)沒有追 [推]。
- c0437630 的 15 個消費者各自的用途沒有逐一確認。
- HDMI:v3 不讀任何看起來像 HDMI 的鍵欄位,所以 HDMI 不會另外選 pid [驗:v3 程式碼];v5 的 key+0x50 分支會換 DispParam,但 +0x50 是不是 HDMI 屬於 [推]。
- kind 2 / W91c1 / Model 路徑(c02d4f28)的角色依據不足。
- 表項陣列與 mapping 在 RAM 中可寫,是依先前上機改 PARAM 欄成功推得 [推]。
