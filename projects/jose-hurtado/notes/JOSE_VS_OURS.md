# Jose 的 fpSup-Formats vs 我們的 OpenGate(OG3K / OG2K)—— 全面比較

2026-10-07,**純離線**(沒碰相機、沒寫卡、沒 commit、沒改任何原始碼)。
目的:使用者在考慮「所有 OG 相關的東西都改以 Jose 的做法為基礎」,先把兩邊攤開比。

**標記**

| 標記 | 意思 |
|---|---|
| **[驗]** | 本次從位元組/原始碼讀出來的(他的 VBIN、我們的 `.S`/`.py`、韌體映像 `out/MAIN_c0000000.bin`) |
| **[引]** | 引自文件(他的 README/CHANGELOG/MANIFEST,或我們的筆記);相機結果都屬這類,本次沒有重測 |
| **[推]** | 推論,沒有直接證據 |

**來源**

- Jose v0.6.1 **五個**格式包:`~/Downloads/fpSup-Formats-v0.6.1/releases/fpsup-fmt-{s16,og2k,og3k,og35k,og4k}-v0.6.1/`。
  ⚠ **樹裡的 `formats-v0.6.1/original/` 只有 S16/OG3.5K/OG4K 三包**;OG2K(slot 2,`fpSup.BIN` sha256 `344383fc…`)
  與 OG3K(slot 3,`b0e80d98…`)只在 Downloads。五包的核心 115 段逐位元組相同 **[驗]**(本次腳本比對)。
- 他的反組譯:以 `formats/tools/fmt_layout.py` 對 v0.6.1 跑遞迴下降(1,872 條指令、33 個入口)**[驗]**。
  資料表(picker、registry、regapply 48 格、canvas 清單)用 scratchpad 腳本以 `python3 -I` 讀五包得到。
- 我們:`projects/open-gate/build/og3k_plan.py`(以 `OG_TARGET=og3k|og2k` 實際實例化 `Plan` 取得時序與 hook 表)、
  各 `.S`、`og_v3.c`/`build_v3_og.py`、`projects/open-gate/notes/*`、`projects/usb-shell-sup/notes/LOADER_V3.md`。

---

## 0. 一段話結論

1. **他的核心是從我們的 OG3K 長出來的**,不是另起爐灶 **[驗]+[引]**:cave 裡的 routine 位址與我們逐一相同
   (picker `C0730800`、fps `C0730A00`、setter `C0731800`、name `C0731A00`、aspect2 `C0731B40`、out `C0731D00`、
   pbsel `C0732200`、canvas `C0732400`、gs `C0732900`、旗標 `C0731C00..`),picker 每筆 48 B 的格式與我們 `fmttable.S`
   完全相同,他的 OG3K / OG2K 八個格率的時序 **與我們 `og3k_plan` 算出的值逐字相同**;v0.3.0a README 也寫明
   「the OG2K / OG3K open gates this card grew out of」。差別在他把「一個目標寫死」**泛化成 6 個 slot + registry 資料列**,
   並且在上面加了很多 UI 與格式。
2. **他贏的是廣度與 UI 行為**:5 個格式(S16、OG3.5K、OG4K 是我們沒有的,而且在他的相機上錄過)、Crop Mode、
   格率/裁切反灰、一張卡多格式、v0.6.1 的 video clamp(高 ISO 暗部黑位逐格跳一階)。
3. **我們贏的是正確性的深度與可維護性**:原始碼、測試與 mutation、MOV 凍結守衛(他**沒有**)、
   引擎組態三欄(他的 OG3K/OG2K **沒有**)、全部 payload 堆疊 8 對齊(他有 4 處不對齊)、v3 PIC 與 OG_CHAIN 層。
4. **「以 Jose 為基礎」在沒有原始碼的前提下,只能是 31FMT 那種二進位搬家**,之後每個修正都是改他的二進位。
   建議:**先向 Jose 要原始碼**(MANIFEST 點名了 `build_reg.py`、`formats_rel.py`、`build_ui6.py`、`pack_release.py`,
   放在他那份 `projects/open-gate/build/registry/`);拿到就**以他的 registry 資料模型 + 我們的原始碼核心合併**;
   拿不到就**保留我們的核心**,把他的資料(各格式的時序、48 格、canvas 清單)與機制(clamp、反灰、Crop)在原始碼層移植(§8)。

---

## 1. 架構

### 1.1 形狀

| | 我們 | Jose v0.6.1 |
|---|---|---|
| 格式單位 | **一個 sup 一個格式**,每個都是完整核心(`30OG3K.BIN`、`30OG2K.BIN`) | **一個核心 + 6 個 slot**;每個格式包 = 同一份核心(115 段)+ 自己的 slot 段 |
| 格式描述 | 目標寫在建置期:`og3k_plan.TARGETS[...]`(profile、donor 模式、時序、要寫的畫布欄)→ 組進 payload 的 `#define` | **執行期資料**:registry `C0731240 + 0x40×slot`、picker `C072FB00 + 0x180×(slot−1)`、48 格值表、canvas 清單 |
| 多格式共存 | AutoRun 版:OG3K 與 OG2K **互斥**(同 enum 4、同 hook)。v3 + `OG_CHAIN`(2026-10-07,離線):每個 hook 點變成一層,「不是我的就往下」,OG3K+OG2K 同卡模擬通過;**enum 還沒分開,不能上機同卡**(LOADER_V3 第 4 步之後) | 核心依 slot 集中處理,所有格式天生共存;compositor(`C0793C30`)每次載入依卡上有哪些 slot 組選單 |
| 程式來源 | 原始碼(`.S` + Python 計畫 + C entry),可重建 | **只有二進位**(PR #7 與他的 fork 都只有 release BIN) |
| 載入 | AutoRun 卡(固定 cave)與 Loader v3(`og_pic.inc` PC 相對,兩原點組譯逐位元組相同) | AutoRun 卡 stage2(固定座標);我們搬成 v3 `31FMT.BIN`(120 MOVW/MOVT + 143 字 fixup,雙胞胎 528 次執行相同,**只做了 S16/OG3.5K/OG4K 三格**) |

### 1.2 錄影當下怎麼選感光元件模式

兩邊都掛同一個點:**`C043CCF8`(`FUN_c043ccf8`,picker 的字串鍵查表)**,三張 CinemaDNG 表
`C0BE5810/59B0/5B50` = 8/10/12-bit。

| 步驟 | 我們 `fmttable.S`(`0xC0730800`) | Jose regfmt(`0xC0730800`)**[驗]** |
|---|---|---|
| 認表 | r1 是哪張表 → 位元深度碼存 `BITLATCH C0731C14` | 同,存 `C0731C14` |
| 找鍵 | 掃自己的格式表(`0xC0731000`,每筆 48 B,比前 8 B) | 掃 `C072FB00..C0730400`(6 slot × 8 格,每筆 48 B,比對 key 兩字並遮罩) |
| 命中後 | 寫 donor 時序記錄 `+4/+8`(hmax\|tail、vmax\|x);鎖存引擎格率(`FPSLATCH`,+0x2C 欄);回傳 entry | 寫 donor 時序 `+4/+8`,**另寫 `+0xC/+0x10`(感光元件讀出視窗,值取 registry `+0x30/+0x34`)**;**設 video clamp**(§5.1);格率 index 存 `C0731C20`;slot 變了就呼叫 regapply(48 格) |
| Crop | — | slot 有 `+0x38`(crop 變體列)且 Crop getter `C005BB98` 非 0 → 改用 crop 列(OG4K → 列 7、OG3.5K → 列 8) |
| 沒命中 | 回原廠迴圈 | 同 |

**格式在 setter 端**:兩邊都掛 `C005C020`(解析度 setter)。
我們 `og3ksel` 設 `FLAG`(要求「選了本目標**且**錄影格式是 CinemaDNG」)、GTAB 六個預覽高、donor 時序還原/寫入、`OGSAVE`;
Jose regsel 依 enum 找 slot → 先把 5 筆 donor 時序寫回原廠(表 `C0730470`)→ 清 4 筆 clamp → 選中就寫時序並設 clamp →
regapply(slot) 在關中斷下把 48 格 PARAM 寫成該 slot 的值(slot 0 = 原廠值)。**[驗]**

### 1.3 Jose 的 registry 列(`C0731240 + 0x40×slot`)**[驗]**

| 欄 | S16 | OG2K | OG3K | OG3.5K | OG4K | 意思(推讀) |
|---|---|---|---|---|---|---|
| +0x00 enum | **5** | **7** | **4** | **9** | **8** | 解析度設定值 |
| +0x04 profile | 13 | 13 | 83 | 171 | 171 | 借的 PARAM profile |
| +0x08 | 3 | 2 | 2 | 2 | 2 | 長寬比 enum(2 = 3:2,3 = 16:9) |
| +0x10 | 48 格值表 | 〃 | 〃 | 〃 | 〃 | regapply 的來源 |
| +0x14 / +0x18 | 錄影 / 回放 canvas 清單 | | | | | `{off,val}`,`-1` 結尾、`-2` = 「格率 index < 7 就停」 |
| +0x1C/+0x20 | 2096×1238 | 2000×1334 | 3008×2000 | 3456×2304 | 3840×2560 | DNG 有效尺寸 |
| +0x28 | 6 | 6 | 5 | 3 | 3 | **最高格率 enum**(6 = 100、5 = 59.94、3 = 29.97),反灰用 |
| +0x2C | 待機 S16 裁切清單 | – | – | – | crop 待機清單 | |
| +0x30/+0x34 | 0x0028\|1000 / 1290 | 14\|2022 / 1358 | 20\|3036 / 2032 | 40\|6072 / 4082 | 同左 | 寫進時序記錄 `+0xC/+0x10`(讀出視窗) |
| +0x38 | 0 | 0 | 0 | 8 | 7 | crop 變體列 |
| +0x3C | `FMT1`…`FMT5` | | | | | magic |

---

## 2. 逐格式比較

### 2.1 總表

| 格式 | 誰有 | 感光元件模式(donor 時序記錄) | 讀出 | profile | 錄影 raster → DNG | 格率 | 捲簾 |
|---|---|---|---|---|---|---|---|
| **OG3K** | 兩邊 | 98 `ACQ_12BIT_MIX`(`C0B59540`);100p 用 117 `MONIT1_100`(`C0B59A20`) | 感光元件 2×2 合併 | p83 | 3024×2010 → 3008×2000 | 我們 23.98–59.94 + 100(117);Jose 只到 59.94(registry `+0x28`=5,100 與 119.88 反灰,但 picker 表仍有 OG3K100 那筆) | 12.4 ms |
| **OG2K** | 兩邊 | 139 `MONIT1_60_LOWP5`(`C0B599A0`) | 3×3 合併 | p13 | 2016×1344 → 2000×1334 | 23.98–100 | 8.3 ms |
| **S16** | Jose | 121(`C0B59580`),x_start 1984,另改模式表 `C0B59F54..C0B607F0`(感光元件視窗) | **1:1 感光元件視窗** 2112×1250(crop 2.87) | p13 | 2112×1250 → 2096×1238 | 23.98–59.94、100 | ≈7.7 ms **[推]**(445×1250/72 MHz) |
| **OG3.5K** | Jose | 3 `MONIT1_30`(`C0B59560`),視窗 6062×4032 | 全 1:1 讀出,ISP ÷1.75(RAW RWZM 1792) | p171(UHD 12-bit) | 3464×2304 → 3456×2304 | 23.98–29.97 | ≈25 ms |
| **OG4K** | Jose | 3,視窗 6030×4020 | 全讀出,ISP ÷1.570(RAW RWZM 1608) | p171 | 3840×2560 → 3840×2560(**無邊**) | 23.98–29.97,354 MB/s @24p | ≈25 ms |
| OG3.5K / OG4K **Crop** | Jose | 同模式,crop 列(RAW RWZM 1023 = unity、預覽 RWZM 2048) | 中央 1:1 | p171 | 同 DNG 尺寸 | 同 | |
| OG4K-4000 | 我們(**只有離線核心**) | 151 full-height | RWZM 1536 | p429 | 4016×2676 → 4000×2666 | 24p | — |
| OG6K | 我們(錄影側 target,給 HDMI RAW,**未上機**) | 3(`C0B59560`)| 全 1:1 | p14 | 6064×4042 → 6048×4032 | ≤29.97 | 25 ms |
| HSW | 我們(**研究原型,已上機,未發布**) | 12 `MONIT1_240`(3×6 非對稱) | | p13 | 2016×672 → 2000×662 | 239.76 | 3.1 ms |

(S16/OG3.5K/OG4K 的格率與用途描述引自他的 v0.6.1 README **[引]**;donor、時序、尺寸、RWZM 值 **[驗]**。)
注意 OG6K 與他的 OG3.5K/OG4K 是**同一個 donor 時序記錄 `C0B59560` 同一組時序**(445/585/6748/8 等)—— 兩邊各自獨立走到同一處。

### 2.2 OG3K / OG2K:兩邊相同與不同的地方 **[驗]**

**相同**:picker 鍵、donor 模式、時序(八格逐字相同,例 OG3K24 = 445/1145/6740/4、OG3K25 = 450/450/6400/4、
OG3K100 = 117 的 330/270/2182/4;OG2K 八格 = `OG2K_TIMING`)、profile(p83 / p13)、錄影矩陣、回放 canvas 清單
(`+1C=2`、raster、可見、`+F4/+F8`、四個 RWZM 1024)、六個預覽高(`C0BDB9CC` 等 p5/p210/p227/p257/p258/p259 `+0x28`:1125 → 1334)。

**不同**

| 項目 | 我們 | Jose |
|---|---|---|
| 錄影 canvas 引擎三欄(`OG3K_ENGINE_CONFIG_THREE_FIELDS.md`) | 寫 `+0x30`(原廠在同格宣告的格率,FHD100 是 50.0)、`+0x90 = 1`、`+0xC0 = 0` | **不寫**。OG3K 清單只有 `+0/+4`,OG2K 多 producer/preview 幾何,**沒有** 0x30/0x90/0xC0 —— 等於我們 2026-09-27 之前的狀態 |
| >60p 的 hirate 欄 | OG3K/OG2K 一律寫 `+0x90/+0xC0`(`write_hirate`) | 只有 S16 在格率 index ≥ 7(100p)時寫 `+90/+B0/+C0/+DC/+E4/+FC/+100`;OG2K 100p 什麼都不寫(他 v0.3.0a 回報 OG2K 100p 在 SSD 上錄得穩 **[引]**) |
| OG2K 的幾何寫在哪 | 只改 canvas 的 RAM 複本 | canvas 清單 **加上** regapply 直接改 p13 的 PARAM 格(`+F4/+F8`、`+0C/+10`、`+20/+28`)—— 選擇期間原廠 p13 列是改過的 |
| video clamp | 沒有(§5.1) | 有:mode 98 → 記錄 `C0B5C6A8`、mode 139 → `C0B5CE50` |
| MOV 守衛 | 有(`og3kfmt` 掛 `C005BE58`) | **沒有**(§7.1) |
| 119.88 | 不反灰;顯示鏈改聽 picker(`MATCH C0731C44`)→ 退成 UHD 但不變形 | 反灰(regfrclass/regfrmax) |
| Super35 / Crop | README:要使用者手動關 | 反灰並實質關掉(regcropstate/regcropeff) |
| 解析度 enum | AutoRun:OG3K、OG2K **都是 4**(互斥);v3 CHAIN 計畫 OG3K 4、OG2K 7 | OG3K 4、OG2K **7** |

### 2.3 預覽高(我們的 GTAB)vs 他的等價物

- 我們:`og3ksel` 的 GTAB 一組 = 六個預覽 profile 的 `+0x28`(1125 ↔ 1334),選中/離開時交易式切換;開機由 og3krestore 讓 LV 重讀。
- Jose:同樣六個位址放在 regapply 48 格的最後 6 格,值依 slot:S16 留 1125(16:9),其餘 1334 **[驗]**。
  S16 與 OG4K/OG3.5K Crop 另有待機 canvas 清單(registry `+0x2C`),在 canvas hook 依 profile 號(`0xD1..0xD8` 與一個位元遮罩)套用,
  讓待機/AF/放大鏡顯示錄影的框。

### 2.4 RWZM / 畫布

- 我們:`WITH_RWZM = False`;OG3K/OG2K 是感光元件合併,RAW 不縮放;畫布只改 RAM 複本(`og3kcanvas`),原廠 PARAM 列不動。
- Jose:OG3.5K/OG4K **改原廠 p171 的 PARAM 格**(`+F4/+F8` 視窗、`+64/+D4` RAW RWZM 1792/1608、`+00..+E4` 幾何、`+58/+C4/+38`),
  這些是 p171 = **原廠 UHD 12-bit 的 profile**;選擇期間 UHD 列是改過的,離開時 regapply(slot 0) 寫回 **[驗]**。
  他靠「選格式 = 換 slot」的時機保證 UHD 錄影時已寫回;沒有我們那種「只動 RAM 複本」的隔離。

---

## 3. Hook 對照表 **[驗]**

我們的列 = `og3k_plan.HOOKS`(`OG_TARGET=og3k`,14 個 ARM)+ `build_og3k_ui_candidate.THUMB_HOOKS`;
Jose = `fmt_layout.firmware_sections()`(20 ARM B/BL + 3 Thumb B.W)。

| 站點 | 韌體角色 | 我們 | Jose v0.6.1 |
|---|---|---|---|
| `C043CCF8` | picker 查表 | fmttable `C0730800`(最後武裝) | regfmt `C0730800` |
| `C005C020` | 解析度 setter | og3ksel `C0731800` | regsel `C0731800` |
| `C005BE58` | 錄影格式 setter | **og3kfmt `C0731400`(MOV 撤旗標)** | — |
| `C005BB60` | Crop setter | — | `C0730AA0`:Crop 切換時換 crop 列、寫時序、regapply(v0.6.0 起) |
| `C005C054` | 解析度 setter 尾 | — | regseltail `C0732760`:apply + change;待機外觀會變時翻 Crop 一次逼 LV 重建 |
| `C043A19C`(BL) | canvas 建構 | og3kcanvas `C0732400` | regcanvas `C0732400`(清單式;另含開機輪詢/套用) |
| `C0437B48` | 解析度名 | og3kname `C0731A00` | regname `C0731A00` |
| `C0306EA0` / `C0306EEC` | 長寬比 | `C0731B00` / `C0731B40` | `C0731F00` / `C0731B40` |
| `C0437E98` | `XC_LiveViewDispParam::v5` 輸出描述 | og3kout `C0731D00` | regout `C0731D00` |
| `C043BE68` | 回放管線選擇 | og3kpbsel `C0732200` | `C0732200` |
| `C03A6DD8` | 增益分派(raw movie 判斷) | og3kgs `C0732900` | reggs `C0732900` |
| `C02092CC` `C0218AEC` `C0219260` `C03AA568`(BL) | 快門角度 nominal fps | og3kfps `C0730A00` | regnom `C0730A00` |
| `C043B6A4` | `FUN_c043b638` 內(MOVAF / AF、放大鏡的 picker) | — | `C07323A0`:crop 列的 AF/放大框 **[推]** |
| `C04A121C` | 格率清單狀態 | — | regfrclass `C07322A0`(依 `+0x28` 回 0/1/3/5) |
| `C00A87E4` | 格率正規化上限 | — | regfrmax `C0730500` |
| `C04A1788` | Crop Mode 狀態(反灰) | — | regcropstate `C0730680` |
| `C00A93BC` | Crop Mode 生效值 | — | regcropeff `C0730600` |
| `C05E5B58`(Thumb) | NBU 字串解析 | 舊版 ui_string;UISHARE 版改 uishare 字串層 | 自己的 hook(31FMT 換成 `uis_layer_fixed`) |
| `C05E84D8`(Thumb) | NBR 載入 | ui_load / uishare QS 層 | `C0732C84` |
| `C05E6400`(Thumb) | NBU 記錄解譯 | ui_record(360 筆) | `C0732DD0`(379 筆) |
| `C05D90F0`(Thumb) | QS 佈局載入 | ui_layout(丟棄舊佈局) | — (改靠 regseltail 翻 Crop) |
| `C07426F8`(函式指標) | crop 描述 vtable | — | → `C07304E0`(`mov r0,#0; bx lr`) |
| `C06BDA3C/40/48` | 列 ↔ enum 配對表 | uishare(`QS_SITES`) | 指到自己的表 `C0731C40` |
| `C0437AF8`、`C043D258` | 回放 profile 替換、範圍檢查 | 兩邊都**已停用**(我們 `WITH_PLAYBACK/RANGE=False`;他 v0.6.1 只剩寫回原廠的 cleaner) | |

**重疊**:15 個 ARM 點(picker、setter、canvas、name、aspect×2、out、pbsel、gs、fps×4)與 3 個 UI Thumb 點完全同站點 ——
兩者**不可能同卡**(31FMT 與 30OG3K 同卡只載入先者,FORMATS_V3 §4)。
**他獨有**:7 個(Crop setter、regseltail、MOVAF picker、四個反灰點)。**我們獨有**:`C005BE58`(MOV 守衛)、`C05D90F0`。

另外他的值補丁:CSV `C12C7CF8`(512 B,整檔替換)與 `C0F8E7EC`(92 B)、controller max `C1A709BC`、資源目錄改指 `C0D4DE04`、
解析度刷新清單 `C0CDC058`、S16 的感光元件模式表。執行期另寫 donor 時序 5 筆、clamp 8 字、48 格 PARAM。

---

## 4. UI

### 4.1 Settings 列

| | 我們 | Jose |
|---|---|---|
| 解析度列表 | v0.2.8a 起 `add_option`:開機經共用 CSV 處理器**追加**一列(含 Popup 欄)、上限 +1、摘要 **[引]**(v0.2.8a 未上機) | 原地**整檔替換** CSV `C12C7CF8`,`3,S16 2096x1238 / 4,OG3.5K… / 5,OG4K…` 文字直接寫在 CSV;上限 `C1A709BC` 依格式數 |
| 列 ↔ enum | 用原廠空著的 `(4,2)`;v3 交給 uishare 的共用配對表 | 改指 `C06BDA3C/40` 到自己的表,`C06BDA48` 改組數 |
| 原廠配對表 | `C2E4020C`:`{3→0, 2→1, 4→2}`,3 組 **[驗]** | |

### 4.2 QS 記錄:360 vs 379 **[驗]**

`build_og3k_ui_candidate.selected_plans()` 的 360 個位址**全部**在他的表 `C073321C`(379 × 12 B)裡。
兩者 kind 1(315)、kind 2(36)、kind 0(2)、kind 3(1)相同;差別全在 kind 4 literal-delta(6 → 25)。**多出的 19 筆**:

| 群 | 位址 | 筆數 |
|---|---|---|
| B2_5(Settings)popup 位移 | `C1A70827` | 1 |
| B2_5 每列摘要 | `C1A725AC` `C1A726ED` `C1A7282E` `C1A7296A` `C1A72AA6` | 5 |
| B2_5 popup 列值 | `C1A74F57` | 1 |
| QS 底列位置曲線 / 時間終點 | `C2358981`、`C234E465` | 2 |
| QS_CINE 底列第 3–7 格標籤 | `C2354087` `C2354AF3` `C2355569` `C2355F8F` `C2356A55` | 5 |
| QS_STILLlike 底列第 3–7 格 | `C25BAA2F` `C25BB4EB` `C25BBF61` `C25BC9D7` `C25BD4C5` | 5 |

QS max:我們 2.0、他 7.0;游標 clip:我們 `Cursor3`、他 `Cursor7`(QS_SHARE §1)。

### 4.3 字串 / 別名

- 我們:舊版 `C05E5B58` hook 解 `FFFFFFF2..F6`;UISHARE 版改成 uishare 巢狀字串層(id 由 `0x40000000` 起開機發)。
  ⚠ 底列兩筆 kind 4(`C23535A3`/`C25B9EF1`)仍寫死 `FFFFFFF3` → v3 OG3K 上機 QS 底列缺圖(LOADER_V3,刻意等 QS 共用層)。
- Jose:寫死 `FFFFFFD0..F6`(39 個 id),自己的 `C05E5B58` hook 解,沒命中重放原廠(不交給下一層)。31FMT 改成 `uis_layer_fixed`。
  他的 379 筆裡也寫死 `FFFFFFD0..D4`、`F3`、`E1/E4/E7/EA/ED`(QS_SHARE §1.1)。

### 4.4 反灰

- 格率:他 regfrclass(`C04A121C`)依 registry `+0x28` 回清單狀態類別、regfrmax(`C00A87E4`)夾正規化上限,
  所以 popup 與 QS 都灰掉做不到的格率,且**保留使用者存的格率**(OG3K 存 50 → 去 OG3.5K 顯示 29.97 → 回來仍 50)**[引]**。
  我們沒有反灰;OG3K 119.88 由 MATCH 讓顯示鏈聽 picker(退成乾淨的 UHD 檔),SD 卡上設定層本來就擋 100/119.88(ENGINE 筆記 §7d)。
- Crop Mode:他在新列灰掉並實質關閉(存的值保留),OG3.5K/OG4K 例外 —— 跟著 Crop Mode 走 1:1 中央裁切。我們:README 要使用者手動關。

### 4.5 開機重套

| | 我們 og3krestore | Jose |
|---|---|---|
| 觸發 | loader 的 entry(v3:`og_v3.c` 第 8 步),**每次載入一次、立即** | canvas hook 每格輪詢:讀設定的解析度 enum,是 registry 裡的就 regapply(最多前 600 格);第 600 格時若已套用再 apply 一次 |
| 記錄來源 | `OGSAVE`(`XC_CommonSaveData +0x290`)+ 真實錄影格式(`C005BE90`)+ 三個「正在錄」訊號 | 直接用設定裡存的 enum(5/7/4/9/8) |
| 套用 | 呼叫原廠 setter `C005C020`(走 og3ksel 的同一段交易) | regapply + `C0091288/C00911A0` apply/change |
| LV 重建 | CamSch1 狀態切 6 → `C0423D28` stop → `C0423C88` start → 還原狀態(2026-09-24 實機:1125 → 1334 無閃爍)**[引]** | 自建 task `C0794034`:每 100 ms 輪詢至多 15 s,條件(已選格式、canvas ≥ 30 格、`[C30338D0]` = 0、MovSigProcess 狀態 3)成立就 stop → 200 ms → start;**之後永遠 `sleep(0xF000)` 不結束** **[驗]** |
| 錄影中 | 三訊號任一非 0 就跳過 | `[C30338D0]` 非 0 就不重建 **[推:這是「錄影中」旗標]** |

regseltail 的 Crop 翻轉:`[[0xC30751D4]+0x5C]+0x334 ^= 1` 夾在兩次 apply 之間,第二次 apply 由 `MenuItemCropMode::v3` 寫回真值(FORMATS_V3 §7)。
代價:不同長寬比之間切換時閃一格 Super35 裁切 **[引]**。我們改用 `C05D90F0` 丟棄舊 QS 佈局,沒有這個閃。

---

## 5. 畫質 / 正確性

### 5.1 Video clamp(他 v0.6.1)—— 我們**很可能也有這個問題**

他的說明 **[引]**:3:2 用的模式 3/98/121/139 是靜態/LV 模式,黑位走 stills clamp,高 ISO 時黑位逐格跳一階、DNG 仍寫 BlackLevel 256 →
暗部閃(Resolve deflicker 會藏住)。v0.6.0 的 OG4K 約三分之一的格跳一階;v0.6.1 五個格式 ISO 1250 皆 0 跳。

本次從韌體映像核對 **[驗]**:每個模式的 clamp 記錄 = `C0B5C638 + (時序記錄 − C0B59500) × 7/4`,
原廠影片模式(如 6、7、100、106、123、27、115)`+4` bit 3 = 1 且 `+0x18` bit 14–15 = 1;
**我們用的 98(`C0B5C6A8`)、139(`C0B5CE50`)、117(`C0B5CF30`)三個都是 0**。
所以我們的 OG3K(98/117)與 OG2K(139)在高 ISO 暗部**應該有同樣的黑位跳動** **[推,強]**:他的 OG3K/OG2K 用的模式、時序與我們逐字相同,而他量到修前有跳。
我們 `OG3K_ENGINE_CONFIG_THREE_FIELDS.md` §7 量的是 **LV 顯示**的閃,而且原廠 UHD 也有 —— 那是另一件事,不能拿來排除這一件。
**要確認**:拿我們的 OG3K ISO 1250 暗場 DNG,逐格比較暗區均值是否以一階跳。
✎ 2026-10-07:v3 鏈式 OG3K/OG2K 已加上 clamp(離線,未上機),見 `projects/open-gate/notes/VIDEO_CLAMP_V3.md`。

他的實作細節 **[驗]**(`C07318E8..C07319A4` 與 picker 內 `C0730940..`):每次 regsel 先把字面表 `C07319E0` 的 4 筆
(`C6E0`=mode 3、`C6A8`=98、`CE50`=139、`C718`=121)`+4 &= ~8`、`+0x18 &= ~0xC000`,選中格式再 `|=` 回去。

⚠ **他的一個漏洞 [驗]**:OG3K100 的 donor 是 mode 117(`C0B59A20`),picker 與 regsel 都會依公式對 `C0B5CF30` 設 clamp 位元,
但 `C0B5CF30` **不在**清除清單、也**不在**他 VBIN 宣告的段裡 → 錄過 OG3K100 之後 mode 117 的 video clamp 一直開著,
loader 的 journal 也不會關機寫回。mode 117 不在任何原廠 CinemaDNG picker 表裡(本次掃三張表 0 筆),其他用途未查,影響未知 **[推]**。
同類的既有問題兩邊都有:mode 117 的時序(原廠 330/330/2184 → 330/270/2182)過去從不還原;我們 v3 已 claim 讓關機寫回(LOADER_V3 第 4 步),他的沒有。

另:FORMATS_V3 §9 寫「OG3K/OG2K 用的 `C0B59620` 會對到 `C830`,不在清單裡」—— **不對** [驗]:他的 OG3K/OG2K slot 用 `C0B59540`/`C0B599A0`
(都在清單內);`C0B59620` 是 mode 7(原廠 UHD)的時序記錄,只出現在 regsel 的「寫回原廠」表 `C0730470`(寫的就是原廠值,無害)。

### 5.2 黑位 / 增益

兩邊都有 `C03A6DD8` 增益分派 hook(讓 OG 走 raw movie 的 gain_state 7、HCG 門檻 3200)—— 他的 reggs 與我們 og3kgs 同址同功能。
BlackLevel 逐格:他說 v0.6.1 之後 DNG 帶逐格 BlackLevel、與原廠 UHD 一樣 **[引]**。

### 5.3 首格

- 他:v0.3.0a OG3.5K 第 1 格 Bayer 相位翻轉,改視窗 6062×4040 修掉;v0.5.0 OG4K 10/10 首格乾淨;**crop 長序列首格未驗** **[引]**。
- 我們:沒有對應的首格問題紀錄(OG3K/OG2K 是感光元件合併,不經 ISP 縮放)。

### 5.4 其他

- OG2K 清晰度(使用者實拍,記憶 `og2k-sharpness-ranking`):全讀出 RWZM 0.33 > bin 3×3 > **M139**;兩邊的 OG2K 都用 M139(最軟、疊紋最少)。
  他 v0.3.0a 拿掉「OG2K+」(全讀出 ÷3)正是因為疊紋 **[引]**。
- 8/10-bit:我們 v0.2.2a 起三張表都註冊並依位元深度寫平面格式碼(上機量過檔案大小);他的 canvas hook 同樣依 `C0731C14` 寫 `+0x80/+0x84`(7/7、10/9、10/10)**[驗]**,
  但他 v0.3.0a 自己列 S16/OG3.5K 的 8/10-bit 未驗 **[引]**。
- 他的 OG4K DNG 3840×2560 = raster,沒有原廠「+16/+10」的邊;OG3.5K 只有寬度留邊(3464 → 3456)**[驗]**。是否影響任何軟體未知。

---

## 6. 設定區 / 持久化(第一守則)

| | 我們 | Jose |
|---|---|---|
| 解析度設定值 | AutoRun:OG3K、OG2K 都存 **4**(原廠配對表有 `{4,2}` 的隱藏 CUSTOM)。v3 CHAIN 計畫 enum = k+2(OG2K → 7)| 存 **5 / 7 / 4 / 9 / 8**;**5、7、8、9 原廠配對表沒有**(原廠只有 3、2、4)**[驗]** |
| 私有持久字 | `OGSAVE` = `XC_CommonSaveData +0x290`(`0xC30754CC`):0/1(CHAIN 下存 enum)。該區實測 60/60 字跨電源存活、韌體不用(`PERSISTENT_STORE_COMMONSAVE.md`) | 沒有 |
| `XC_UserSetting` 錄影寬高 | setter 收到 4 時 `MenuItemMovieRecSize` 查不到 → **保持原值**(og3ksel 註解,實測)。`og3ksel.S` 宣告了 `PAIR 0xC074222C` 但**從未使用** [驗] —— QS_SHARE §12.10「OG 改原廠尺寸表」的說法與目前原始碼不符,應更正 | 不碰 `0xC074222C`;5/8/9 查不到 → 同樣保持原廠值 |
| `XC_UserSetting +0x334`(Crop) | 不碰 | regseltail 暫時翻轉再由 apply 寫回;翻轉中正好關機會存下翻轉值(仍是原廠合法 0..3)|
| 拔卡後 | 設定區留 4 與 OGSAVE;OG 長期出貨有實際佐證但未做逐項調查(第一守則表) | 設定區留 5/7/8/9。他 README「delete AutoRun.txt…camera is stock」只對 RAM 成立 —— **選單設定在 flash 裡** **[推]**;原廠帶著這些值開機的行為**沒有任何人查過** |

第一守則把「原廠根本沒定義的列舉值」列為比 4 更嚴重的一類。使用者 2026-10-06 表示不在意 Jose 的 5/8/9(QS_SHARE §6);
若以他為基礎,這件事會擴大到「所有 OG 格式都存原廠未定義的值」,應改走 QS_SHARE §12.10 的「做法 1」(只存原廠值 + 記憶體記號)。

---

## 7. 穩健性

### 7.1 Jose 的已知問題 / 風險

| # | 問題 | 證據 |
|---|---|---|
| J1 | **沒有 MOV 守衛**:aspect(`C0731B40`/`C0731F00`)、regout(`C0731D00`)、regnom、reggs 只看 `C0731C08`(選中 slot);全部 1,872 條指令沒有讀錄影格式(`C005BE90`)、沒掛 `C005BE58`。我們 `FLAG_AND_PICKER_DISAGREE.md` §10/§38 在 OG3K **與** OG2K 都實測:這組只看旗標的 hook 在 MOV 錄影時仍開著 → 按錄影**硬凍結、要拔電池** | [驗] 程式;後果 [推,強];他 v0.3.0a 自列「MOV with a new row selected」未驗 |
| J2 | **4 處堆疊不對齊**(FORMATS_V3.md 目前版本未記載,本次重驗):`C0730500` regfrmax `push{r0,r2,r3,r5,lr}`(5 字,且在不對齊下呼叫韌體 `C005C058`);`C0731F60` regapply `push{r4-r7,lr}`(5 字,接著關中斷,葉函式);`C0732400` regcanvas `push` 7 字(整個 hook 本體不對齊);`C073246c` 再 `push{r4,r5,r7}` —— 累計 10 字,**這一段反而回到對齊**,裡面的韌體呼叫是對齊的。另有 3 處奇數 push(`C07309DC`、`C0731ED4`、Thumb `C0732D54`)是重放原廠序言,不算 | [驗];後果依記憶 `arm-stack-alignment`(中斷把上下文 STRD 進被中斷任務的堆疊,我們因此凍過)[推] |
| J3 | mode 117 clamp 漏清(§5.1) | [驗] |
| J4 | 引擎組態三欄缺(§2.2) | [驗] |
| J5 | 寫死字串 id、沒命中不交給下一層(31FMT 已修) | [驗] FORMATS_V3 §6 |
| J6 | 原廠未定義 enum 進設定區(§6) | [驗] 值;後果未查 |
| J7 | 開機 task 永不結束(每次載入佔一個任務與堆疊) | [驗] |
| J8 | 改原廠 PARAM 列(p13、p171 = UHD 12-bit),靠 slot 切換寫回;關機由 loader journal 寫回 | [驗] |
| J9 | CSV 整檔替換、資源目錄改指 `C0D4DE04`、controller max:與其他 UI sup 不相容,除非改 uishare 形狀(QS_SHARE §5 列為「必須換掉」) | [驗]/[引] |
| J10 | 中央 slot:「一格式一檔」需要加載器服務或拆 hook(FORMATS_V3 §3、§8.2) | [引] |

### 7.2 我們的已知問題(歷史與現況)

| 問題 | 狀態 |
|---|---|
| MOV + OG 按錄影硬凍結 | 已修(og3kfmt + FMTLATCH,§10/§38) |
| 8/10-bit 落到 UHD30 | v0.2.2a 修 |
| v0.2.2a fmttable 借 r1 | v0.2.3a 修 + 建置期防護 |
| 119.88 → 檔案變 UHD、畫面拉長 | MATCH 修(§7d) |
| p43 拍照凍結、p221 回放當機 | 回到 p83 |
| HSW 22 格請求不完成 | 研究原型 |
| 引擎三欄錯配 | 修(真缺陷),但 LV 閃爍症狀沒消(§7 of 該筆記) |
| v3 OG3K QS 底列缺圖 | 已查明,刻意等 QS 共用層 |
| 高 ISO 黑位逐格跳(§5.1) | **沒處理,應該有** [推] |
| payload 堆疊對齊 | 本次 grep 我們所有 OG payload 的 `push`:只有兩處奇數,都是重放原廠序言(`fmttable.S:180`、`og3kout.S:190`)[驗] |

### 7.3 上機驗證狀態

| | 我們 | Jose |
|---|---|---|
| 錄影核心 | OG3K/OG2K 大量 A001_* 素材解檔;v3 `30OG3K` 2026-10-06 上機錄 A001_035(231 格,DNG 尺寸沒讀)[引] | 作者相機:五格式同卡切換、OG4K 10/10、v0.6.1 黑位 5 格式 0 跳、Crop 4×/8× 放大一致、開機刷新 [引] |
| UI | v0.2.7a 上機;v0.2.8a(add_option)未上機;OG_CHAIN 離線 | N=8 QS 上機 [引] |
| 我們這邊對他的驗證 | — | 31FMT:離線雙胞胎 528 次執行、14 項測試;**從未上機**;只含 3/5 格式 |
| 他自己列未驗 | — | 所有組合、長序列、crop 長序列首格;S16/OG2K 100p + Gyro 不錄(Gyro-Data OFF 才錄)[引] |

---

## 8. 「以 Jose 為基礎」具體代表什麼

### 8.1 沒有原始碼時能做的只有一件事

31FMT 的做法:把他的位元組整塊搬家(MOVW/MOVT + 字 fixup,他從不用 B/BL 跨 piece,所以可行),用雙胞胎模擬證明行為不變。
**任何行為改變 = 改他的二進位**:每個修正都要逐指令手寫、再做雙胞胎 + mutation(字串層那一次就是例子,FORMATS_V3 §6)。
要補 §7.1 的 J1(MOV 守衛:新增 `C005BE58` hook + 改 4 個 hook 的閘)、J2(4 個序言/收尾改寫,本體要挪)、J3、J4(OG3K/OG2K 清單加 3 對)、
J6(enum 改原廠值 + 記號,QS_SHARE 估 1–2 天)—— 每一項都是二進位手術,而且 Jose 下一版一出,全部重來。

### 8.2 會得到 / 會失去

| 得到(他有、我們沒有) | 失去(我們有、他沒有,或要重做) |
|---|---|
| S16(感光元件 1:1 視窗)、OG3.5K、OG4K(都在他相機上錄過) | 原始碼、建置期檢查、測試、mutation 習慣 |
| Crop Mode 支援(OG3.5K/OG4K 1:1 中央裁切) | MOV 守衛(J1) |
| 格率反灰 + 保留存的格率;Crop 反灰/強制關 | 引擎組態三欄(J4) |
| video clamp | 全部對齊的堆疊(J2) |
| 一個核心多格式、registry 資料驅動;N=8 的 QS 實測值 | v3 PIC(兩原點逐位元組相同的證明)與 OG_CHAIN 層、uishare 形狀(add_option、巢狀字串、QS 共用層) |
| 不需 OGSAVE 的開機重套 | 研究目標:HSW 240p(已上機)、OG6K、OG4K-4000、res-lab/Sensor Lab |
| | 「只動 RAM 複本、不改原廠 PARAM 列」的隔離 |
| | 一切修正的速度(改原始碼 vs 改他的二進位) |

### 8.3 值得互相移植的

**他 → 我們(原始碼層重寫,值從他的位元組讀,致謝並先徵得同意)**
1. **video clamp**:最便宜、價值最高。我們的 mode 98 → `C0B5C6A8`、139 → `C0B5CE50`;mode 117 要決定(OG3K100 開/關,離開時一定要清)。
   claim 8 字 EXCL,離開/關機寫回(他的 8 字在映像裡 bit 都是 0)。
2. 格率反灰(`C04A121C`/`C00A87E4`)與 Crop 反灰(`C04A1788`/`C00A93BC`),取代「README 叫使用者手動關 Super35」。
3. S16/OG3.5K/OG4K 的資料:時序、讀出視窗(+0xC/+0x10)、S16 模式表補丁、48 格值、canvas 與待機清單、crop 列 —— 本筆記 §1.3、§2 已全部讀出。
   用我們的形狀實作時,改 p171(UHD)PARAM 列那一招要重新評估(我們的慣例是只改 canvas RAM 複本)。
4. registry 的資料模型本身(一列描述一個格式),配上我們的 OG_CHAIN「一格式一層」。

**我們 → 他(若他有原始碼,建議直接交給他)**
1. MOV 守衛(J1)—— 這是會讓相機硬凍結的已知路徑。
2. 引擎三欄 `+0x30/+0x90/+0xC0`(J4)。
3. 堆疊對齊(J2)、mode 117 clamp 清除(J3)。
4. 設定區只存原廠值(J6,做法 1)。
5. uishare 形狀(他已經在用 uishare 的 Merge 頁,31FMT 也已掛 uishare 字串層)。

### 8.4 建議路徑

1. **先問 Jose 要原始碼**(他的 MANIFEST 點名 `build_reg.py`、`formats_rel.py`、`build_ui6.py`、`pack_release.py`,
   放在他那份 `projects/open-gate/build/registry/`,而那份樹是從我們的樹分出去的)。同時把 §7.1 的 J1–J4、J6 寄給他 —— 不論誰當基礎,這些都要修。
   也請他確認授權(包裝沒有 license 檔,README「Do not republish without his agreement」)。
2. **拿到原始碼**:合併成一份 —— **他的 registry/slot 資料模型 + 我們的核心修正與 v3/uishare 形狀**。
   落地順序:我們的 OG3K/OG2K 以 registry 列重寫並證明逐位元組等於今天的錄影行為 → 加入他的 S16/OG3.5K/OG4K 列 → clamp、反灰、Crop →
   拆成一格式一層(OG_CHAIN 的做法)→ 設定區做法 1。
3. **拿不到原始碼**:**不要**以他的二進位為基礎。保留我們的核心,依 §8.3 在原始碼層移植(先 clamp,再反灰,再新格式)。
   過渡期若使用者要 S16/OG3.5K/OG4K,可以出 31FMT(把 Downloads 裡 OG2K/OG3K 兩包補進 `formats-v0.6.1/original/` 後也能做五格式版),
   但它與我們的 OG3K 互斥,且帶著 J1–J4。
4. 不論哪條路,**上機前**先做:我們 OG3K 高 ISO 暗場黑位逐格檢查(§5.1)、他的格式在 MOV 下按錄影的行為(J1,要使用者同意且備好拔電池)。

---

## 9. 本次附帶發現(建議更正其他筆記,本次未改)

- `FORMATS_V3.md` §9:「OG3K/OG2K 用 `C0B59620`」不對,實為 `C0B59540`/`C0B599A0`(§5.1)。
- `FORMATS_V3.md` 與 `formats/tools`:只涵蓋 3 包;v0.6.1 實有 5 包(slot 2 OG2K、slot 3 OG3K 在 `~/Downloads/fpSup-Formats-v0.6.1/releases/`)。
- `QS_SHARE.md` §12.10:「OG 改原廠尺寸表 `0xC074222C`」與 `og3ksel.S`(PAIR 宣告未使用)不符。
- mode 117(OG3K100)兩邊都沒有 video clamp;他的會設而不清。
