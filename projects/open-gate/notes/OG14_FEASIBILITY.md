# 有 14-bit OpenGate 嗎? —— 三層各自的答案

2026-09-15。姊妹文件:`research/imx410/notes/SENSOR_MODE_METADATA.md`(70 筆模式)、
`research/imaging-hw/notes/REDUCTION_INVENTORY.md`(三層縮減)、
`research/imx410/notes/ISO_DR_UNDERSTANDING.md` §7(已據本文訂正)。

信心:**[C]** 反編/字串交叉驗證 · **[I]** 推論 · **[?]** 未解。

> **2026-10-03 外部實作:** Julien supmod R120 已做出 16:9 裁切 14-bit 23.976p(原廠 M100 + 平面碼 8,兩個值),
> 不牴觸本文的開閘結論。見 `research/other/external/sigma-fp-supmod-R120/JULIEN_14BIT_AND_MODES.md`。

> **2026-10-04 Sensor Lab 訂正:** 本文原題是「29.97p 全高開閘能否成立」，
> 不是 Sensor Lab 的模式白名單。Sensor Lab 要開放原廠**全部八個 RAW14 mode**
> 與可求解的輸出軸；M100 只是一條外部公開聲稱可錄的管線。現有 23.976p 起的
> 格率表可求解六個 RAW14 mode；M0/M141 全高 6064×4042 的上限約 19.3p
> （含最低消隱），須有私有低格率路徑，18p 已通過離線時序模型。
> `A_MODE=0x100` 已在來源表示明確 M0、與自動值 0 分開；保存的 r83 卡
> 尚不含這項修正。r81 按 REC 立即凍結，r83 的 picker 修正仍只通過離線驗證，
> 未寫卡上機複驗。詳見 [RAW14 核對紀錄](../../res-lab/validation/20261004-raw14/RESULTS.md)
> 與 [低格率審計](IMX410_RAW14_LOWRATE.md)。

---

## 0. 一句話

**感測器有 14-bit 全片幅 3:2,但 M0 只有19.127p、Sony 官方上限19.20p;
依已知 HMAX 計算的零 blanking 天花板也僅19.55p。電影管線沒有14-bit profile。
已知模式與下游縮放做不出14-bit OpenGate 29.97p;只剩未證實的 sensor-side
RAW14 2x reduction 可作高風險研究。**

M6 確實證明 sensor/receiver 可連續處理 4176x2174 RAW14 @29.97p,但那是
16:9 中央 crop。把 12-bit 數值裝進 14-bit DNG 容器也不算 14-bit acquisition。

---

## 1. 感測器層:14-bit 開閘是有的,但已知表中只在「零縮減」家族

70 筆模式裡 RAW14 共 8 筆,**全部** `+0x44/+0x48 = 1/1`、`+0x4C/+0x50 = 1/1`、
`+0x60 = 16`、`hmax = 911`:

| mode | 名稱 | 光柵 | fps | 比例 |
|---|---|---|---|---|
| 0 | `ACQ` | 6064x4042 | 19.127 | 3:2 **全開閘** |
| 141 | `ACQ_CONTINUOUS` | 6064x4042 | 18.003 | 3:2 **全開閘** |
| 129 | `ACQ_CROP` | 3968x2640 | 19.202 | 3:2(裁切) |
| 144 | `ACQ_CONTINUOUS_CROP` | 3968x2640 | 18.003 | 3:2(裁切) |
| 95 | `MONIT1_24_HD` | 5712x3216 | 23.976 | 16:9 |
| 6 | `MONIT1_30_HD` | 4176x2174 | 29.970 | 16:9 |
| 122 | `MONIT1_25_HD` | 4176x2174 | 25.000 | 16:9 |
| 100 | `MONIT1_24_HD_LOWP` | 4176x2174 | 23.976 | 16:9 |

正常 full-frame RAW still 由 M0 / M141 提供 6064x4042 RAW14 開閘讀出;
M129 / M144 則是 3968x2640 RAW14 crop still,不能概括成每張 DNG 都是開閘。

### 1a. RAW14 與較長線時完全相關 [C];因果仍是推論 [I]

四種 RAW14 主光柵中有三種存在同光柵 RAW12 雙胞胎;M95 的
5712x3216 是例外。三組可直接比較的幾何如下:

```
6064x4042   RAW14 hmax 911 (M0/M141)      RAW12 hmax 445 (M97/M3/M121/M142)
4176x2174   RAW14 hmax 911 (M6/M122/M100) RAW12 hmax 445/450 (M102/M124/M108/M152)
3968x2640   RAW14 hmax 911 (M129/M144)    RAW12 hmax 445 (M130/M145)
```

70 筆零例外:**RAW14 → hmax 911;RAW12 → hmax ≤ 450。** 這個約 2.05x 的線時
相關性符合 14-bit ADC 需要較慢讀出的解釋,但尚未獨立證明因果。後面的格率上限
只依賴已確認的 HMAX,不需要先假定其電路原因。

### 1b. 感測器沒有 stock 14-bit geometry-reduction mode [C]

70 筆 metadata 中所有 RAW14 mode 的有效 geometry scale 都是 1x1;
2x2、3x3、3x6 mode 全部是 RAW12。名稱表 250 格全掃,所有帶 `_MIX`
的名稱也一律帶 `_12BIT`:

```
ACQ_12BIT_MIX            ACQ_12BIT_MIX_CROP        ACQ_12BIT_MIX2
ACQ_12BIT_CONTINUOUS_MIX ACQ_12BIT_CONTINUOUS_MIX_CROP  ACQ_12BIT_CONTINUOUS_MIX2
```

**不存在 `ACQ_MIX`。** 但 `MIX` 只和 2x2 geometry scale 相關,
仍不足以證明 charge binning。能確認的是 Sony/SIGMA 現有 mode 都沒有
RAW14 reduction;是 sensor 硬限制或 SIGMA 未實作,離線資料無法完全區分 [?]。

---

## 2. Stock CinemaDNG 錄影管線:沒有 14-bit profile [C]

> **2026-10-04 訂正:** 這個標題指原廠**影片資料表沒有可直接選的 RAW14
> profile**，不代表 DNG 標籤或封裝相關函式完全不存在。原廠
> `eRawBitType=1` 能映成 `BitsPerSample=14`；`Qual:14bit` 也存在於另一份
> 品質字串表。Julien R120 的 M100／23.976p 錄影可作管線先例，不能把
> 它擴張成所有 RAW14 mode、格率、增益與回放已驗證。

三組獨立證據:

1. **CDNG 品質只有三檔。** 韌體裡的品質字串只有 `Qual:8bit` / `Qual:10bit` /
   `Qual:12bit`(0x748318 與 0xBA12DC 兩處各一份)。沒有 14-bit。
2. **RAW14 目前會被錯分到 8-bit 影片增益狀態。** `FUN_c039dde8` 的 raw-movie
   分支只特判 enum 4→state 5、enum 3→state 6、enum 0→state 7;enum 1 走 default,
   結果也是 **state 5 (`movie_raw_8bit`)**,不是 generic state 4。ISO100 可暫作
   sensor/link discovery,但必須同時確認 HCG=0、兩項 digital gain=100 且穩定;
   這不能當畫質或動態範圍驗證。任何 writer 或 ISO>100 測試前,都要另外定義並
   驗證 guarded RAW14 gain policy,不能靜默沿用 state 5。
3. **回放只認 12 和 10。** `FUN_c05c1a58` 讀 `0x0102 BitsPerSample` 時映射為
   `12 → 0,10 → 3,其他 → 4`(`OG3K_PLAYBACK_PROFILE_CLASSES.md` §12)。
   位深 enum 4 是 RAW8,所以 14-bit 目前會被誤分成 RAW8。這證明 stock 回放不支援
   RAW14,但分類可另行修補,不是感測器 capture 的物理障礙。

> **訂正:** `imager createraw <rawbit> [0:12bit 1:14bit 2:16bit 3:10bit 4:8bit]`
> 是**除錯指令的參數**,不是選單選項。`ISO_DR_UNDERSTANDING.md` 舊版把它當成
> 「CDNG 可選 14-bit」是錯的,已訂正。

---

## 3. 29.97p 的硬邊界

全幅 RAW14 的 active-row readout 已經是:

```
911 cycles/line × 4042 lines / 72 MHz = 51.14 ms
零 blanking 理論上限 = 19.55 fps
stock M0 = 19.127 fps
```

29.97p 一格只有 33.37 ms;即使 VMAX 與 blanking 全砍掉也塞不進去。要達成它,
HMAX 必須低於約 594 cycles,但 70 個 RAW14 mode 全部固定 911。Sony 官方
IMX410 basic-drive 表的 6064x4040/14-bit 上限也只有 19.20 fps。

RWZM 與 CRCT 都在 sensor 讀出之後,只能減少後段畫布/寫入量,不能把 51.14 ms
讀出變成 33.37 ms。提高 sensor clock 到約 110 MHz 以上則是規格外超頻,
不是可由現有 mode 安全支持的參數調整。

### 路線 A —— 14-bit full read + RWZM:只能約 18–19p

前一版誤寫成 `CRCT hbin2/vbin2`;**CRCT 沒有 ÷2**。已確認的 H/V 合法抽頭
是 H=1/3/5、V=1/3,而且錄影側未驗證。要把 full RAW14 做成 3K 應使用
RWZM 2048:

```
M141 ACQ_CONTINUOUS 6064x4042 RAW14 @18.003
    → RWZM 2048
    → 幾何商約3032x2021;producer 候選3032x2020 RAW14 @18.003
```

同理,約 4K 可用 RWZM 1.5x、約 2K 可用 RWZM 3x,但格率仍只有 18–19p。
這些都只是 sensor/downstream 概念可行;RAW14 輸入能否走 recording RWZM、
14-bit CinemaDNG writer、增益校正與回放仍全部待開發。3032x2020 是沿用已驗證
RAW12 full-height+RWZM2 路徑的畫布候選,RAW14 實際尺寸仍須 readback 定案。

### 路線 B —— 自造 RAW14 2x sensor reduction:只列高風險發現實驗

若 sensor 本身能在 RAW14 做 2x reduction,行數變短後 29.97p 才可能成立。
但 SIGMA 70 modes 沒有任何一筆,Sony 官方 reduced basic-drive modes 也全是
12-bit。這不是改 metadata/RAW enum 就會出現的模式,而是未知的 sensor ADC、
transport 與 reduction 組合。

數學上唯一值得保留的候選,是用同一 continuous family 做四角拆解:

```
M141 = RAW14 1x       M142 = RAW12 1x
未知 = RAW14 2x       M143 = RAW12 2x
```

M6 只捐贈已知可工作的 RAW14 exact-29.97 timing。四組真正的 Q12 ACQ sibling
(M97→M98、M142→M143、M130→M131、M145→M146)有29個完全一致的 1x→2x
register delta;去掉 `reg 0x0001` 後,可得到28個有表內先例的 reduction core。
假設感測器真的能接受未知組合並輸出3032x2012 RAW14:

```
active read = 911 × 2012 / 72 MHz = 25.46 ms
29.97p frame = 33.37 ms
餘裕約 7.91 ms ≈ 625 行
3032 × 2012 × 14 / 8 × 29.97 ≈ 319.95 MB/s
```

M6 的 HMAX=911 / VMAX=2636 / tail=1915 是精確29.97p時序先例。SIGMA 的38-register
RAW-depth block 與上述29-register reduction block 的交集**只有 `reg 0x0001`**;
Sony A7 III 的47-register depth block 與31-register reduction block 也恰好只在
`reg 0x0001` 相交。這支持兩塊大致可分,卻把唯一衝突集中在最不能猜的 selector:
已知只有 RAW14 1x=`0x29`、RAW12 1x=`0x2A`、RAW12 2x=`0x39`;兩份 firmware
都沒有 RAW14 2x 值。`0x38` 只是代數外插,不列為可執行計畫;`0x39` 更會讓
sensor 走 RAW12、下游卻按 RAW14 配置,明確禁止。

M141 與 M143 是同一 continuous family;把 M141 的 receiver 非 ID 欄位改成 M143
幾何後,離線執行原廠 `FUN_c0320ab0` 已確認:在相同、可重現的 synthetic
config 下,兩個 receiver consumer 的 receiver-derived bytes 與 stock M143 一致。
這只證明 receiver table mapping,不是完整實機 payload 驗證,也不證明 RAW14
transport、timing、sensor writes、packer 或 allocator。

因此沒有完整 donor。Sony 基本驅動表與 SIGMA 70 modes 的 reduction 全為 RAW12,
強烈顯示**沒有已知或已發布的 RAW14 reduction 支援**,但還不能證明 silicon 一定
拒絕。這只能做 guarded、可回復的 discovery experiment,不能當可交付方案。

候選表格也不能直接改共享 M141 sensor/metadata/timing/receiver rows;那會波及
原廠 M141/still path。目前的合成結果只能是 logical/emulator overlay。將來若要實機,
必須先實作 private scratch rows 與精確 caller guard,不能匯出共享表位址當 patch。

目前仍不能實機啟動 candidate:idle live view 通常只跑 preview mode;內建
`imager createraw` 的 no-write 分支不可達、會進 writer,且等待 frame 的 timeout
是無限。必須先新增「單幀 RAM sink + 獨立 watchdog + writer hard gate + redzone +
可完成 cleanup」的 bounded probe,並先通過 stock M143 正常與刻意 timeout 兩種測試。
RAW14 還必須有獨立 enum1 canvas/profile-copy 路徑,以免現有分支寫成
`+0x80/+0x84=7/7`;目標是 runtime `+0x80=10/+0x84=8`。同時 metadata
`+0x60` 沒有 RAW14 2x 先例,和 sensor `reg 0x0001` 一樣是 hard gate。

### 路線 C —— 12-bit full-read supersampling:目前可做

若重點是 full-FOV、細節與抗疊紋,可用已驗證的 M151-full24 / M3 full-read
搭配 RWZM 2x、1.5x、3x,但記錄仍是 12-bit。2x/3x sensor geometry reduction
究竟是 charge binning、skipping 或其他 reduction 尚未解,不能宣稱每個輸出像素
已合併 4 或 9 個 photodiode。

> **2026-09-22 已解 —— 見 `REDUCTION_KERNEL_MEASURED.md`。** 從像素量出來了:
> 垂直是真的併列(÷2 併 2 列、÷3 也只併 2 列),水平不是合併而是數位重取樣。
> 每個輸出像素實際合併 **3.2**(÷2)與 **5.33**(÷3)個 photodiode,不是 4 和 9。
> 本段原本的保留是對的,現在可以換成具體數字。
> RWZM 的核也解了(半寬 1.2 的固定三角核),所以路線 C 的「RWZM 2x、1.5x、3x」
> 三個選項不再等價 —— **÷3 一步做是最差的一條**,詳見該文 §7。

把 12-bit sample 左移後寫成 `BitsPerSample=14` 只會製造較大的檔案;
不會增加 ADC 精度、動態範圍或真實階調,不列為 14-bit OpenGate。

---

## 4. 待驗

- M141/M0 RAW14 full-read 能否進 recording RWZM,以及 RWZM 的內部位寬、
  飽和、Bayer phase 與輸出 packing [?]。
- RAW14 應採哪個 guarded gain policy;現況 enum1 會誤走 state5(8-bit),而 state4/5/7
  的 HCG、digital ladder、黑階/白階仍須 A/B;writer/packing、DNG 標頭與回放分類
  也都待補 [?]。
- M6 已證明既有 sensor/receiver path 可連續跑 RAW14 crop 29.97p;它的 timing、
  receiver 與 packing 有多少能重用在未知的 full-FOV reduced 路徑 [?]。
- M204 `ACQ_12BIT_MIX2` / M217 `ACQ_12BIT_CONTINUOUS_MIX2` 有名稱但不在 70 筆
  metadata 裡 —— `MIX2` 是什麼縮減比例,值得單獨追 [?]。
- 12-bit reduction 輸出實際是否被量化限制,需要實拍暗部階梯驗證。

---

## 5. 決策

- **14-bit OG 29.97p 已知 full-read/downstream 路線:停止,不可交付。** 現有
  full-read line time 已超過一格;RWZM/CRCT 無法補救。
- **RAW14 + sensor-side 2x:只留高風險發現實驗。** 數學 budget 足夠,但沒有
  stock/官方支援證據,不得先當成能做出的 mode;bounded no-writer probe 完成前
  不得啟動實機 candidate。
- **14-bit OG 18p:研究案。** 可從 M141 full RAW14 + downstream RWZM 開始,
  但首先要補 movie 14-bit pipeline,不是只改 mode。
- **24/25/29.97p OpenGate:維持 RAW12。** 畫質提升優先測 quiet readout 與
  full-read RWZM supersampling。

---

## 6. RAW14 ÷3 路線(2026-09-16)—— §5 的決定不涵蓋這條

§5 判「停止」的是 **full-read + downstream** 路線:6064×4042 的 RAW14 有效讀出
就要 51.14 ms,一格 29.97p 只有 33.37 ms,RWZM/CRCT 在讀出之後,補不了。

本節是另一條:**在感測器端就做 ÷3**,行數砍到 1344,讀出時間隨之砍掉三分之二。
這條 §5 當時沒有評估過。

### 6a. 時序模型已用實機驗到微秒 [C]

`imager mode_list` 會報每個模式的有效讀出時間。拿它對 `hmax × rows / 72 MHz`:

| 模式 | hmax | 相機報告 | 模型 |
|---|---|---|---|
| `ACQ` RAW14 1× 6064×4042 | 911 | 51,142 µs | 51.142 ms |
| `ACQ_12BIT` 1× 6064×4042 | 445 | 24,982 µs | 24.981 ms |
| `MONIT1_60` ÷3 2016×1344 | 330 | 6,160 µs | 6.160 ms |
| `MONIT1_60_LOWP5` ÷3 | 445 | 8,306 µs | 8.307 ms |
| `MONIT1_100_LOWP` ÷3 | 395 | 7,373 µs | 7.373 ms |

三個 hmax 等級、兩種位深全部吻合。**模型不再是推估。**
(順帶確定:M139 走 hmax 445,OG2K 的實際捲簾是 **8.31 ms**,比 OG3K 的 9.22 ms 短。)

### 6b. 預測 [C 模型 / I 結論]

```
RAW14 ÷3 2016×1344 有效讀出 = 911 × 1344 / 72 MHz = 17.005 ms
```

| 目標 | 一格 | 結果 |
|---|---|---|
| 25p | 40,000 µs | 過 |
| **29.97p** | 33,366 µs | **過**,餘裕 16.4 ms |
| 50p | 20,000 µs | 過,餘裕 3.0 ms |
| 60p | 16,683 µs | **差 322 µs,不過** |

資料率(16-bit 容器,見 §6d):5.50 MB/幀 → 24p 132 MB/s、29.97p 165 MB/s。
對照 §3 路線 A 的「18p / 193 MB/s」,這條更高幀率、更低資料率。

### 6c. 生死關:`reg 0x0001` 是索引,不是參數 [C]

70 個模式的 `reg 0x0001` 與 `(位深, 縮減)` **完美一對一,零例外**:

| 值 | n | 位深 | 縮減 |
|---|---|---|---|
| `0x29` | 8 | RAW14 | 1/1 |
| `0x2A` | 15 | RAW12 | 1/1 |
| `0x2F` | 8 | RAW12 | 3/3 |
| `0x30` | 3 | RAW12 | 3/6 |
| `0x39` | 36 | RAW12 | 2/2 |

**這否掉了本文 §3 路線 B 的 `0x29 + 0x0F = 0x38` 外插。** 數值不是算術的:
1/1→2/2 是 +0x0F,1/1→3/3 是 **+5**,3/3→3/6 是 +1。3/3 的值比 2/2 還小。

候選是 `0x2E`(未被使用,且符合「RAW14 比同縮減的 RAW12 少 1」),但那條規則
**只有一個觀測對(0x29/0x2A)支撐**。這是探測,不是計畫。

`imager mode_list` 的活體表已確認:**感測器自己回報的就是那 70 個模式、
8 個 RAW14、全部 1×1。** 沒有隱藏的 RAW14 縮減模式可用,`0x2E` 不是偷懶的結果。

### 6d. 訂正:管線根本沒有 14-bit 封裝 [C]

> **2026-10-04 再訂正:** 下方 9/16 推論把兩層混在一起。
> `FUN_c04356b0` 的 code 8 / 0xB = 16 bpp 證明**引擎 RAW 平面配置**可放
> RAW14，不決定寫入 DNG 的位元封裝。原廠另有 enum 1 → 每像素 7/4 bytes
> 的大小計算、`BitsPerSample=14` 與 `WhiteLevel=16383` 路徑。
> 所以「管線根本沒有 14-bit 封裝」「DNG 應標 16」「packed 14-bit 少見」
> 都不能由 plane code 推出。實際錄影的 descriptor、`StripByteCounts`、
> 黑白位和像素資料尚未實測；下方原推理保留為歷史紀錄。

`FUN_c04356b0` 的 plane format code → 位元數完整對照:

```
7 → 12    8 → 16    9 → 10    0xA → 8    0xB → 16(預設)
0x10007 → 12    0x10009 → 10    0x1000A → 8
```

**沒有 14-bit。** 所以「寫一個 14-bit CinemaDNG writer」這個講法是錯的 ——
不是要寫,是這條管線沒有這個封裝模式。錄影端和回放端都一樣。

正確做法是 **16-bit 容器**:code 8 / 0xB 是一等公民,寫入端 enum 2 → 16 bits
也已存在。14-bit 感測器資料放進 16-bit 字,是業界常態,packed 14-bit DNG 反而少見。

回放端因此縮小成一行:`FUN_c05c1a58` 目前是 `10→3, 12→0, 其他→4(RAW8)`,
要讓 `BitsPerSample == 16` 映射到對應 16-bit 的 class(依寫入端 enum 推測是 2),
並確認 class 2 解析成 plane code 8 或 0xB [?]。

### 6e. 現況

`../build/raw14_3x_probe/` 有 bounded probe 的設計、負載、產生器與 20 個測試。
產生器在三個 hook 位址(錄影寫檔入列點、畫格就緒回呼、毫秒來源)綁定之前
**拒絕輸出任何可執行負載**;把 `0x2E` 寫進計畫還要另一道明確同意。

`FUN_c06a4bd0` 已排除為寫檔點 —— 它在 `XC_StillFileFormatDngTh`,是靜態 DNG
標頭建構,不是錄影路徑。

### 6f. 存檔點(2026-09-17)

離線準備完成,實機一步都沒走,沒有寫過任何記憶體。暫停原因不是卡住,
而是同一輪算出 **Super 16 2K** 是更好的路線:

```
IMX410 像素間距 5.920 µm
Super 16 (12.52 x 7.41 mm) -> 2115 x 1252 px   原生 2K,1:1,不需縮減
```

S16 的 selector 是 **RAW14 1/1 = `0x29`,已存在於 8 個原廠模式** —— 不需要
賭 `0x2E`。而且 1:1 讀出沒有 Bayer 縮減,§6c 那個偽色問題根本不會發生;
RAW14 讀出只要 15.84 ms,連 60p 都放得下(÷3 的 17.005 ms 放不下)。

要做的只是把既有 1:1 裁切模式(`ACQ_CROP` 3968x2640 RAW14、
`ACQ_12BIT_CROP`、`MONIT1_24_HD_LOWP` 4176x2174)的視窗縮到 2115x1252,
那是 OG3K/OG2K 做過兩次的操作,不是合成新模式。

完整狀態、可重跑的合成程式與候選寫入清單:
`../build/raw14_3x_probe/STATE.md`。

---

## 2026-09-26 補:Z CAM 的 Sony 參考讀出表、其他 IMX410 相機、14-bit 3:2 候選

### A. Z CAM 保留了 Sony 的完整 IMX410 讀出清單 [C]

`imvt_camera` 尺寸表(file `0xF1C278`,33 × `{u32 w,h,bits,?; u64 0, ptr}`)配暫存器表同欄的 `0x0001`,
連 Z CAM 自己沒用的欄都在 —— 看起來是 Sony 參考表整份照搬 [?]。`0x0001` 即讀出模式編號:

| `0x0001` | 尺寸 | bits | 合併 | Z CAM 用 |
|---:|---|---:|---|---|
| **41** | 6064×4040 | **14** | 無 | — |
| 42 | 6064×4040(及 3260/2560/1728/1188 等視窗) | 12 | 無 | ✓ |
| **43** | 4160×2160 | **14** | 無 | — |
| 44 | 4160×2160 / 1728 / 1188 | 12 | 無 | ✓ |
| 47 | 2020×1342 / 1080 | 12 | ÷3 | 1080 ✓ |
| 48 | 2020×672 / 336 | 12 | ÷3/÷12 | — |
| 49 | 6064×672 | 12 | — | — |
| 52–54 | 2020×136/112/96 | 12 | — | — |
| 57 | 3032×2012 | 12 | ÷2 | — |
| 59 | 3032×4040 | 12 | 只水平 ÷2 | — |
| 42 | 6064×2012 | 12 | 只垂直 ÷2 | — |

**Sony 參考清單裡 14-bit 只有 41、43 兩種,都不合併。** 比「fp 與 A7 III 都沒有」更強:
連廠商拿到的清單都沒有 RAW14 縮減。空號 45/46/50/51/55/56/58 存在,內容不可推 [?]。
§3 路線 B(自造 RAW14 2x)因此再降一級。

### B. 其他 IMX410 相機:錄影 RAW 全是 12-bit,14-bit 只用在靜態 [C 公開規格]

- Blackmagic Cinema Camera 6K:6048×4032 3:2 open gate 最高 36 fps,12-bit Blackmagic RAW。
- Panasonic S5(S1/S1H 同感測器):5.9K RAW 12-bit(外錄)。
- Nikon Z6:12-bit NEF 12 fps、14-bit 9 fps;Z6 II:14 / 10 fps —— 14-bit 讀出較慢,與 fp 的 hmax 911 對 445 一致。
- IMX410 官方:14-bit 全像素 19.2 fps(靜態),12-bit 用於高速 4K 動態。

沒有任何一台 IMX410 相機錄 14-bit 影片;這是整個產業的一致選擇,符合「14-bit 只在 1x、線時約 2 倍」的限制。

> **2026-10-04 訂正:** 這是 9/26 當時找到的公開商品規格範圍，不能再作
> 「沒有任何實例」的絕對結論。Julien supmod R120 公開聲稱支援 SIGMA fp
> M100／23.976p RAW14 裁切錄影；本專案尚無其實錄 DNG 可獨立量測封裝與增益。
> 全高 29.97p 的行時間限制仍成立。

### C. 14-bit 3:2 的實際候選:用「列數」換格率 [C 時序 / ? 管線]

RAW14 線時 = 911 / 72 MHz = 12.65 µs/列,與寬度無關(hmax 對 6064/4176/3968 寬都是 911)。
每格可讀的列數上限 ≈ 格期 / 12.65 µs:

| 格率 | 格期 | 最多列數 | 3:2 光柵 | 裁切倍率 | 原廠先例 |
|---|---:|---:|---|---:|---|
| 29.97p | 33.37 ms | 2637 | ~3954×2636 | 1.53 | M129 3968×2640 RAW14(2640 列 = 33.40 ms,超 0.03 ms,零 blanking)|
| 25p | 40.0 ms | 3162 | ~4743×3162 | 1.28 | — |
| 23.976p | 41.7 ms | 3296 | **4824×3216** | 1.26 | **M95 5712×3216 RAW14 @23.976**(只需水平裁窄)|
| ≤19.55p | — | 4042 | 6064×4042 全開閘 | 1.00 | M0/M141 |

資料率(RAW14 packed 1.75 B/px)全都超過 fp 原廠上限(UHD 12-bit 29.97 ≈ 373 MB/s):

> **2026-10-04 口徑補充:** 此處 1.75 B/px 是**假設 packed 14** 的流量
> 估算，不是已錄片段的 `StripByteCounts`；引擎 plane code 8 按 2 B/px
> 配置。以兩種口徑估算緩衝與媒體壓力，待 DNG 實測決定寫檔口徑。

4824×3216@23.976 = 651 MB/s;3968×2640@29.97 = 549 MB/s。要落地就得在機內縮:

| 候選 | 輸出 | 資料率 |
|---|---|---:|
| M95 裁成 4824×3216 → RWZM 1.5 | 3216×2144 RAW14 @23.976 | 289 MB/s |
| 同上 → RWZM 2 | 2412×1608 @23.976 | 163 MB/s |
| M129 3968×2640 → RWZM 1.5 | 2645×1760 @24p(29.97 需砍 4 列) | 196 MB/s |
| M0/M141 全開閘 → RWZM 2(§3 路線 A) | 3032×2021 @18–19p | 188 MB/s |
| 不縮、只裁到資料率上限 | ~3636×2424 @24p(裁 1.67)/ ~3252×2168 @29.97(裁 1.86)| ~370 MB/s |

- **最有先例的一條:M95 裁窄成 3:2(4824×3216、1.26× 裁切、23.976p)+ RWZM 1.5**。
  M95 已證明 3216 列 RAW14 能跑 23.976,裁窄不改線時。
- 所有候選共同的未解問題(見 §2):沒有 14-bit CDNG profile、RAW14 被錯分到 8-bit 增益狀態、回放只認 10/12、
  RAW14 輸入能否走 RWZM 未驗證。這些是管線工作,不是感測器限制。
- 這些都是**裁切或低格率**的 14-bit 3:2,不是 29.97p 全開閘;後者依 §3 仍不可能。

## 2026-10-15：使用者指定真 14-bit Open Gate、至少 30fps

本次目標保留完整感光視角與真正 RAW14，不以低格率或 3:2 中央裁切替代。
重新掃描 Ver.5.02 的 70 個模式，八個 RAW14 模式全部為 1×1；只有 M0/M141
覆蓋全感光面積，兩者在 29.97p 與 30.000p 都無解。依各模式消隱需求計算，
M0/M141 上限分別約 19.409/19.314fps。下游 RWZM/CRCT 不能縮短其
51.142ms 的有效行讀出時間。

同一韌體映像與 CSV 交叉核對 11,270 個 sensor-register 欄位，原有 RAW14×2
planner 的 17 個核心測試通過。未操作相機、未產生或部署可執行 payload。
完整數據見 [本次離線稽核](../../res-lab/validation/20261015-raw14-opengate-30p/audit.json)。

若感光元件確實支援未知的 RAW14×2，3032×2012 輸入的有效行時間在
HMAX=911 假設下約 25.457ms，30.000p 尚餘 7.876ms；3024×2010 對齊後
record plane 的 packed-14 算術流量約 319.108MB/s，16bpp 緩衝流量約
364.694MB/s。這些是**條件式時序與容量計算**，不是硬體支援或實錄結果。
RAW14×3 同樣只有條件式算術，不能把未使用的 selector 編號視為可用功能。

既有 `raw14_2x_plan.py` 仍回報 `BLOCKED_REFERENCE_ONLY`。必要前提包括
RAW14 reduced selector、對應的 readout/receiver class，以及有界 RAM 單幀探針
的正常完成與強制 timeout 還原驗證；其後才有像素位深、增益、DNG 封裝與
持續錄影核對。現行 res-custom virtual RCD consumer 也尚未支援 RAW14。
**目前沒有符合此次 30fps Open Gate 要求的可交付版本；不改寫現有模式表來冒充支援。**
