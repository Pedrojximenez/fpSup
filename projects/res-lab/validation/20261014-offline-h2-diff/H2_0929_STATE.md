# 2026-09-29 H2 RAM 狀態重建（A001_193 當下）與今日 consumer 的差異

離線研究，沒有碰相機、USB、fpshd/fpsh，也沒有執行任何會連到硬體的腳本。

- 來源 transcript：`~/.claude/projects/-Users-dido-Developer-localized-SIGMAfp-re-projects-open-gate/5acbf12f-3568-4c49-9959-d190b5001045.jsonl`
- 下文的 `L####` 是 JSONL 的行號（從 1 起算），時間都是 UTC。當地時間 +08:00。
- **[F]** 表示 transcript 或檔案裡直接看得到的事實。**[I]** 表示推論，每一條都附上理由。

---

## 0. 時間線：A001_193 錄製當下，相機上裝的是什麼

| UTC | 行 | 事件 |
|---|---|---|
| 00:47:41 | L2738/L2739 | 第一次裝 H2：`imx410_load.py --disarm --axis-preset H2`。計畫 1423 筆，改了 102 字 [F] |
| 00:48:05 | L2743/L2744 | 推 H2，讀回 25 對畫布（見 §2.4）[F] |
| 00:48:16 | L2749/L2752 | SD 上的 A001_170，94 格乾淨停。DNG 1008x672、`StripByteCounts` 1016064、`FrameRate` 30000/1001、1/250（L2764）[F] |
| 00:51–00:54 | L2808/L2823 | 長寬比修正（`aspect_enum` 與 `og3krecipe.S` 加上 RWZM），`og3krecipe` 從 1728 B 變成 1772 B（L2828）[F] |
| **00:55:10** | **L2834/L2840** | **最後一次成功安裝**：`imx410_load.py --disarm --axis-preset H2`，接著 `menu SetMovRecFormat 0`、`menu SetMovRecSize 4`、`push(Registry(),'H2')`。輸出「已解除:13 個 hook 回原廠」、「計畫 1434 筆；改了 268 字；payload 與 hook 都讀回過」、相機端 `rec 1008x672 act 992x662 valid 1 mode 12 bin_e 0/0 rwzm 2048/1024`、「RECIPE 27 字逐字比對:相同」、aspect enum = 2 (3:2) [F] |
| 00:56:05 | L2857/L2858 | `key S1ON/S1OFF` 加截圖，沒有錄影 [F] |
| 00:56:11 → 01:16:19 | L2858–L3050 | 主機**完全沒有**對相機發指令，全部是離線改碼（L2965 的 `R._w` 讀的是韌體映像檔，不是相機）[F] |
| ~01:13:25 | （先前 audit） | 使用者錄下 A001_193（SSD）。這個時間是先前 audit 推出來的 [I] |
| 01:16:19 | L3050/L3051 | 想裝 rate-hook 版，但「★ 預檢讀取失敗；零寫入：0xC005BE58: 沒有回應」[F] |
| 01:16:40–49 | L3058/L3063 | `shl open ... failed`，`ioreg` 找不到 SIGMA fp，相機從 USB 上消失 [F] |
| 01:17:02 | L3065 | Claude 確認：「相機上是上一版的 H2（沒有 rate hook）」[F] |
| 01:28:07 | L3073/L3077 | 使用者說「重插了」。`mem get 0xC005BE58` = `0xEA1B5568`，仍是我們的 hook，RAM 沒有被清掉，期間沒有重開機 [F] |

**結論 [F]：** A001_193 錄製時，相機上就是 00:55:10 那一次安裝（L2840），加上當時推進去的 H2 AXIS。中間沒有任何寫入。01:16 那次安裝是零寫入（L3051）。直到 01:28 重插後，舊的 hook 仍然在（L3077/L3080）。

---

## 1. H2 原型的所有寫入、patch 與 hook

### 1.1 安裝工具與原始碼

- 安裝指令：`cd projects/open-gate/build && python3 imx410_load.py --disarm --axis-preset H2`（L2834）。接著透過 `fpSup/fp_usb_shell/putfile.py` 的 `sh` 和 `mem_get`，以及 `imx410_axis.push(Registry(),'H2')` 推 AXIS（L2834）[F]
- 安裝流程：`imx410_load.apply()` 做預檢讀取，然後 `PL.plan()` 產生 (位址, 值, 註解) 清單並 mem 寫入，最後讀回（L1189 是 `imx410_load.py` 片段）[F]
- Payload 是在記憶體裡由 `armasm.assemble`（`PL.blobs()`）組譯出來的，**沒有 payload 二進位檔** [I：`imx410_plan.py` 有 `from armasm import assemble`、`blobs()`，見 L2581/L2828 的呼叫方式]
- **磁碟上的檔案都已經不是 9/29 版本。** 整個 repo 不是 git，所有相關檔的 mtime 都晚於 2026-09-29。下表是現在的 sha256，只當作「今天的檔案是什麼」的指紋：

| 路徑（repo 相對） | 現在 sha256 | mtime |
|---|---|---|
| projects/open-gate/build/imx410_load.py | d8254c00fd5742f90224c2f5de27b2dd7d49c4298e65b96651d51c2a3132f15c | 2026-10-07 |
| projects/open-gate/build/imx410_plan.py | 997f961340aeeaf2e10c48b8707f776ff3056870e33c7cff422562810328e27b | 2026-10-07 |
| projects/open-gate/build/imx410_block.py | f330ddde0b0166e7195c0bb484af19d651db9fe8788fccd57e36484314959659 | 2026-10-05 |
| projects/open-gate/build/imx410_full.py | 73527ae3edb414ed60efe20d6be223ff0175434181884435e2682641bca62845 | 2026-10-05 |
| projects/open-gate/build/imx410_axis.py | 5c2b01db6864e0cb7d0b6af336ad5b6f27fe56ade0c62f29eaf211047a99b35f | 2026-10-04 |
| projects/open-gate/build/og3krecipe.S | 692cf03bedcb0183b051b3087f70f933f2e5cad0b5c30eb457c50bb30e9f989f | 2026-10-06 |
| projects/open-gate/build/imx410_fmt.S | 0e003cacaef73cea965d9b714871c1a5337ab12c35c8bfde07aa06f5f39b2c61 | 2026-10-06 |
| projects/open-gate/build/imx410_canvas.S | 7361fe9d1c0cf9067f318746987d6be7b402673383339372c0ddd1852707ddde | 2026-10-06 |
| projects/open-gate/build/imx410_aspect.S | 6cc8e07c6904a55b3ccc857b9272884de9465f53524dc980acc3ae39fdc29096 | 2026-10-06 |
| projects/open-gate/build/imx410_fps.S | f0a02e2b44bd7e94944755505e8d2dbfe46add01ba4d1c1824c1286fcb5ff472 | 2026-10-06 |
| projects/open-gate/build/og3kgs.S | 66e9368e4b9c6233fad7f4d6ece0fc2415d52035a839b4fa54b32212a9bbbba3 | 2026-10-07 |
| projects/open-gate/build/og3ksel.S | 810930e2664b8b51ddfe8bd2aa36152cc77fb067dfbd26b96a5b2d2a49cf6d6a | 2026-10-07 |
| projects/open-gate/build/og3kname.S | 3e202e0e07368925d59aa7d9cd2baf7fbbdcc07a38df680ee9f2fb0741379b20 | 2026-10-07 |
| projects/open-gate/build/og3kfmt.S | 9ff6a62342d40fbf3c2a1189b2f90bfc5d6a686df1dff59547864eada9f27272 | 2026-10-07 |
| projects/open-gate/build/og3krestore.S | 193ba9770d7f3f8a9e99031a3c88fc6ea462f70b1f5b3eb46fed3382f9ec7976 | 2026-10-07 |
| projects/open-gate/build/og3kout.S | 4e8ca1635e657f6d438bdca21287eca1272446f2b293f3696004d5c172524c27 | 2026-10-07 |
| projects/open-gate/build/armasm.py | fb3206b1492f0729e88571c1990969acaa78db45401bd4d06e3d95ece4bb7cb6 | 2026-09-13（**唯一早於 9/29 的檔**） |
| fpSup/fp_usb_shell/putfile.py | ebe4257833fe27c67919766bcb23844c41d039b35b6d44a3b6fe157dd7b9c0bd | 2026-10-11 |
| projects/open-gate/build/imx410_rate.S（9/29 01:07 新建，**沒裝上**） | 295509611b0ba79fb89965d15c2dc2bbd7c90ca84e5385c24e44d00dfb8550bc | 2026-10-06 |
| 最早的歸檔快照 archive/codex-worklog/sensor-lab-240-menu-20260930/before/projects/open-gate/build/imx410_plan.py | e3eb2bbd738780985bc72fe334dd9c4dbcce0be0fee5a53ee5ff48ad65aec38a | 2026-09-30 08:08（已含 9/29 下午之後的功能） |
| archive/codex-worklog/sensor-lab-closeout-20260930/before/projects/open-gate/build/imx410_fmt.S | （9/30 04:00 版本，含 9/29 20:00 之後才加的 rate-from-menu） | |
| out/MAIN_c0000000.bin（韌體映像，用來查原廠字） | 92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4 | 2026-08-12 |

Claude 的 file-history 只備份到 9/28 Edit 時的版本；9/29 的修改都是用 Bash 跑 python 做的，沒有備份。**00:55 那份 `imx410_plan.py` 已經無法逐字還原。** 下面的位址都來自 transcript 裡的輸出，再拿 9/30 的快照交叉核對。

### 1.2 13 個 hook（已確認：L2840 寫「13 個」，L2961/L2981/L2986 是當時的定義與 stage）

當時 `WITH_RANGE = False`、還沒有 `WITH_RATE`（01:07 才加，L3010/L3040）。stage 順序是 canvas → display → fps → menu → picker，最後才武裝 picker（L2986）。

| 站點 | 原廠字 | 9/29 新字 | 型 → 目標 | Payload | 作用 |
|---|---|---|---|---|---|
| 0xC043A19C | 0xE1A00004 (`mov r0,r4`) | 0xEB0BE097 | BL → 0xC0732400 | imx410_canvas | 畫布（PARAM profile 列）寫入 |
| 0xC0306EA0 | 0xE3A00003 | 0xEA10A5E6 | B → 0xC0730640 | imx410_aspect | XC_DisplayZoomParameterW71C1，長寬比 1 |
| 0xC0306EEC | 0xE3A00003 | 0xEA10A5EF | B → 0xC07306B0 | imx410_aspect (2) | 長寬比 2 |
| 0xC03A6DD8 | 0xE92D4010 | 0xEA0E2EC8 | B → 0xC0732900 | og3kgs | 增益分派（p13 不在 raw movie 帶 131..190 之內） |
| 0xC02092CC | 0xEB048D1F | 0xEB149DCB | BL → 0xC0730A00 | imx410_fps | 快門角度：main exposure property |
| 0xC0218AEC | 0xEB044F17 | 0xEB145FC3 | BL → 0xC0730A00 | imx410_fps | angle metadata A |
| 0xC0219260 | 0xEB044D3A | 0xEB145DE6 | BL → 0xC0730A00 | imx410_fps | angle metadata B |
| 0xC03AA568 | 0xEBFE0878 | 0xEB0E1924 | BL → 0xC0730A00 | imx410_fps | resolution reconfiguration sync |
| 0xC005C020 | 0xE92D4070 | 0xEA1B55F6 | B → 0xC0731800 | og3ksel | 解析度 setter |
| 0xC0437B48 | 0xE92D4BF0 | 0xEA0BE7AC | B → 0xC0731A00 | og3kname | 解析度名發射器 |
| 0xC005BE58 | 0xE92D4070 | **0xEA1B5568** | B → 0xC0731400 | og3kfmt | 錄影格式 setter |
| 0xC0437E98 | 0xE92D4030 | 0xEA0BE798 | B → 0xC0731D00 | og3kout | 主輸出描述子 |
| 0xC043CCF8 | 0xE92D4CF0 | **0xEA0BCEC0** | B → 0xC0730800 | imx410_fmt | picker 查表 FUN_c043ccf8 |

- 新字是用 `(site, target)` 算出來的。目標位址取自 L97（9/28 的 `--map`）、L3143（「0xC0730800 = FMT_CODE」），並與 9/30 快照逐一比對過 [I]
- 有兩個字有實機讀回佐證 [F]：`0xC005BE58 = 0xEA1B5568`（L3077，01:28，仍是 00:55 那次的安裝）；`0xC043CCF8 = 0xEA0BCEC0`（L3130，01:30 重裝後讀回，位址相同）

### 1.3 Payload（cave 0xC0730000..0xC0732C84）

| Payload | 原始檔 | 位址 | 大小與證據 |
|---|---|---|---|
| og3krecipe | og3krecipe.S | 0xC0730C20 | 1772 B（L2828；1728 → 1772 B 的變化見 L2591/L2828） |
| imx410_fmt | imx410_fmt.S | 0xC0730800 | 9/28 是 396 B（L97）；FMT_CODE 見 L3143 |
| imx410_canvas | imx410_canvas.S | 0xC0732400 | 9/29 原始碼全文在 L2552（83 行） |
| imx410_aspect / aspect2 | imx410_aspect.S | 0xC0730640 / 0xC07306B0 | L97 |
| imx410_fps | imx410_fps.S | 0xC0730A00 | 原始碼見 L2961 |
| og3kgs | og3kgs.S | 0xC0732900 | L97、L2973 |
| og3ksel / og3kname / og3kfmt / og3krestore / og3kout | 同名 .S | 0xC0731800 / 0xC0731A00 / 0xC0731400 / 0xC0731600 / 0xC0731D00 | payload 清單見 L2973，位址見 L97 |

### 1.4 資料區與狀態字（全部在 cave 內）

位址來源：L97、L2721（AXIS）、L3007（RATETAB）。內容依 9/30 快照 `plan()` 第 1–6 段的結構 [I：分類相同，數量吻合，見 1.5]。

- `RATETAB` 0xC0730400：11 筆，每筆 (週期數, 標稱, 引擎 float)。第 9 筆（240）= (300300, 240, 0x436FC29F)，見 L2950 [F]
- `TMGTAB` 0xC0730490：264 B，每格 `vmax|tail<<16`（L97、L2950）
- `CTMPL` 0xC07305A0：畫布模板，帶閘門（CG_OVER60/CG_ZOOM 在相機端判斷，L2573/L2592）
- `ASPTAB` 0xC0730620；`NAME` 0xC0730C00 = "CUST"
- `AXIS` 0xC0732490：9 字（L2721）
- `RECIPE` 0xC07324C0：27 字
- `ENTRY` 0xC0732530：48 B 的 picker 表項
- `CANVAS` 0xC0732560：1 + 24×2 字
- `HITS` 0xC0732668
- `GTAB` 0xC0732100：1 組，六個預覽 profile 的可見高
- 狀態字：0xC0731C00 og3ksel 計次 / 0xC0731C04 最後 enum / **0xC0731C08 FLAG** / 0xC0731C0C PBFLAG / 0xC0731C14 BITLATCH / 0xC0731C20 FMTLATCH=0xFFFFFFFF / 0xC0731C24..3C og3krestore 紀錄 / **0xC0731C40 FPSLATCH** / 0xC0731C44 PICKOK=1 / 0xC0732000..70 og3kout / 0xC07328C0 og3kgs 計次 / 0xC0732A00.. 畫布紀錄（L97）

### 1.5 cave 以外的韌體寫入（完整清單）

**安裝時寫入 [F/I]：**

- 上面那 13 個 hook 字
- 選單 CSV 0xC0F8E7EC：92 B 的槽（UHD/FHD 設成 Enabled=0,0，第 3 列是 CUSTOM）
- 清單控制器上限 0xC1A709BC = 0x00000040（BE float 2.0）

後兩項證據：L97 的 MISSING 段寫了「CSV 用 Enabled=0,0 關掉 UHD/FHD」；9/30 快照第 441–457、785–786 行；9/30 的註解說 9/29 版是舊格式（`\n` 換行、IMAGE 欄留空、留著原廠尾巴）。

**執行期寫入 [I]：**

- imx410_fmt 在 picker 命中時，把 RECIPE TW0/TW1 寫進 donor 的時序記錄。mode 12 是第 42 列，位址 `0xC0B59A40`，寫 `+4`、`+8`。依據：L4505 那段 `expected_recipe` 原始碼「donor 的時序記錄…og3krecipe 跑在 imx410_fmt 寫入之前」；9/30 版 imx410_fmt 的命中路徑。**寫進去的值與原廠完全相同**，見 §2.1。
- og3ksel / og3krestore 依 FLAG 套用 GTAB，把六個預覽 PARAM `+0x28`（0xC0BDB9CC、0xC0BDBC28、0xC0BDBC60、0xC0BDBC8C、0xC0BDBC90、0xC0BDBC94）設成 1334 [I：9/30 快照 413–439、766–782 行]

**沒有寫入的項目 [F/I]：**

- 0xC06BDA3C/40/48、0xC06BDB0C/10/18、0xC06CB6DC/E0/E8 三個配對表轉換器都沒寫。`RATE_PAIR`（C06CB6DC）到 L5474（05:30Z）才加進來。
- 格率 CSV 第十列、14-bit 列要到 L4103（03:58Z）、L5031（04:55Z）才有。
- `WITH_RATE_FROM_MENU`（imx410_fmt 依選單改 AXIS rate）最早出現在 L6947（20:00Z）。
- 0xC00C9BD0（rate hook）沒有寫入，見 §4。
- 0xC0189440 沒有寫入。

**筆數交叉驗證 [I]：** unity 時是 1415 筆（L2672）。H2 是 1423 筆（L2739），多出的 8 筆是 fill 模板多 8 欄。00:55 是 1434 筆（L2840），多出的 11 筆正好是 og3krecipe 增加的 44 B = 11 字。這些差額只有模板與 payload 的變化，沒有空間容納配對表（20 + 3 字）或 CSV 列（每份約 65 字）這類額外類別。

---

## 2. 240 是怎麼來的

### 2.1 感測器時序：直接用原廠 mode 12（MONIT1_240）[F]

- 求解器輸出 `hmax 330 tail 330 vmax 910 → 239.76024 fps (0.000 ppm)`、捲簾 3080 us、指紋 F12、候選 mode 12（MONIT1_240），見 L2708/L2728。相機讀回 `mode 12`，見 L2840。
- 韌體映像裡 mode 12 是時序表第 42 列，位址 0xC0B59A40：`+4 = 0x014A014A`（hmax 330 | tail 330<<16）、`+8 = 0x0006038E`（vmax 910 | x 6<<16）。metadata 的 raw 2016x672、`+0x40` 標稱 = 240（離線讀 MAIN_c0000000.bin）[F]
- 主機模型的 RECIPE word[21] R_SAVE0 = 0x014A014A、word[22] R_SAVE1 = 0x0006038E（L3119）。這兩個字是 donor 原廠時序。
- TW0/TW1 = `m.hmax | tail<<16`、`vmax | x_start<<16`（L4505 的程式碼）。代入解出來的值，就是 0x014A014A 和 0x0006038E [I]
- **所以 9/29 寫進時序記錄的值等於原廠值，感測器時序本身沒有被改** [I，很強]

### 2.2 AXIS（推到 0xC0732490 的 9 個字）[F]（L2744、L3051、L3130）

`[12, 9, 2016, 672, 65537, 2048, 1024, 43385824, 0]`

| 欄位 | 值 | 解讀 |
|---|---|---|
| bit | 12 | |
| rate | 9 | RATE_KEYS[9] = '240'（L2950） |
| raster | 2016 x 672 | |
| bin | 65537 | 1 \| 1<<16，即 ÷1/÷1 |
| RWZM | 2048 / 1024 | |
| crop | 43385824 | 992 \| 662<<16 |
| mode | 0 | 讓相機自己挑 |

### 2.3 引擎格率與 FPSLATCH

- og3krecipe 從 RATETAB[9] 取出 `R_EFPS` = 0x436FC29F（239.76f）。主機模型的 RECIPE word[19] = 1131397791 = 0x436FC29F（L3119）。相機的 RECIPE 與主機逐字相同（L2840）[F]
- imx410_fmt 在命中時寫 `FPSLATCH(0xC0731C40) = RECIPE[R_EFPS]`。依據：L2552 的 imx410_canvas.S 註解「imx410_fmt 命中時寫的引擎格率 float bits」；9/30 版 imx410_fmt 第 179–181 行 [I]
- imx410_canvas 對 profile 13 寫 `canvas +0x30 = FPSLATCH`，非零才寫（L2552 原始碼，`strne ip,[r1,#0x30]`）[F]
- R_NOM（word[18]）= 240（L3119）。imx410_fps 在 mode 12 回傳 240，等於原廠 mode 12 的 `+0x40` = 240，所以這組快門角度 hook 在 H2 上實際沒有改變任何值 [I]
- **A001_193 開錄時的 FPSLATCH 從來沒有被讀回** [F：transcript 裡沒有任何讀回]

### 2.4 25 對畫布（profile 13，r4+0x5C）[F]（L2744 是 00:48 的實機讀回）

| 位移 | 值 | 位移 | 值 | 位移 | 值 |
|---|---|---|---|---|---|
| +0x000 | 1008 | +0x080 | 7 | +0x0D8 | 1008 |
| +0x004 | 672 | +0x084 | 7 | +0x0DC | 1008 |
| +0x00C | 1008 | +0x090 | 1 | +0x0E0 | 672 |
| +0x010 | 672 | +0x0B0 | 1 | +0x0E4 | 672 |
| +0x020 | 992 | +0x0C0 | 0 | +0x0F4 | 1008 |
| +0x024 | 992 | +0x0D0 | 1024 | +0x0F8 | 672 |
| +0x028 | 662 | +0x0D4 | 1024 | +0x0FC | 0x40000000 |
| +0x02C | 662 | | | +0x100 | 0x40000000 |
| +0x060 | 2048 | | | | |
| +0x064 | 2048 | | | | |

- 加上 `+0x030 = FPSLATCH`，這一欄在陣列之外單獨寫。
- 其餘 39 欄保留 p13（第 6 列）的原廠預設，例如 `+0x88 = 0`。先前 audit 指出這一欄 p83 是 4。
- 00:55 重裝後畫布沒有再 dump，只看到「畫布命中 91 -> 165」與 RECIPE 相同（L2840）。中間唯一的改動是 R_ASPECT 的算法（L2823），而 R_ASPECT 不影響 CTMPL 閘門，所以 **25 對應該不變** [I]
- donor 選擇：`pick_profile` 得到 (13, fill=True)（L2721）
- 長寬比 enum = 2 (3:2)（L2840）；預覽可見高 1334 [I，見 §1.5]

---

## 3. 卡上的其他模組、媒體與狀態

- **SD 卡根目錄**（L1415，9/28 18:19Z 的 `dir`）[F]：
  - `fpSup.BIN` 32768 B、`AutoRun.txt` 32768 B（兩者 mtime 都是 2025/12/31 08:00，fpSup 建卡工具的固定時間）
  - `FPSUPUI/`、`og2k/`、`CINEMA/`、`DCIM/`、`README.txt` 1367 B、`raw_live_test.zip`
  - 9/27 18:48 有 `._*` 檔，表示從 Mac 複製上來
  - **卡上是哪個產品、哪個版本，transcript 沒有記錄**
- 09-28 23:35Z 重開機後裝 imx410，狀態判定為 `stock`（L2131）。也就是說，卡上的 AutoRun 產品沒有碰到 imx410 載入器監看的約 1455 個位址：hook 站點、計畫位址、`foreign_addresses()`（L1189）[F]
- 之後到 A001_193 為止都沒有重開機。09-29 的每次安裝都判定為 `foreign`，原因是上一次 imx410 安裝留下的 13 個 hook（L2376/L2382）[F]
- **USB shell 常駐**：開機由卡片 AutoRun 帶起來（L3260 的 skill 文字；L7103）。L2127 之後一直可用；01:28 重插後立刻能用而且 RAM 沒清（L3077），所以錄 A001_193 時 shell 的程式碼與 task 仍在 RAM 裡 [F/I]
- **錄影時 USB 線沒接**：01:16 相機從 USB 消失（L3063），01:28 使用者重插（L3073）。fp 只有一個 USB-C 口，「接了 SSD 就沒有 USB shell」（L3937 引用 og3k_plan 的註解）[I：與 SSD 錄影一致]。也就是 shell 在 RAM 裡，但沒有主機連線
- **SSD**：transcript 沒有直接說。A001_193 原檔是 SSD 錄的，這是使用者的證據加上先前 audit。至於 Claude 的 A001_169/170，是用 `dir \CINEMA` 讀到的，表示寫在 shell 看得到的那張卡上（SD）[F：L2692/L2752]
- **SSD 寫入模式、HDMI 狀態**：transcript 沒有記錄，**未知**
- **Gyro / Gyro2 / lossless / 00SHELL / RES-Custom**：transcript 在 01:17 之前沒有任何載入或寫入它們的紀錄（grep：0 次）。Gyro 的 C038C77C 是否被別的產品掛著，**無法從 transcript 判定**。可以確定的只有一件事：卡上的產品與 imx410 監看的位址沒有交集 [F]
- **原生設定**：
  - `menu SetMovRecFormat 0`（CinemaDNG）、`menu SetMovRecSize 4`（CUSTOM），見 L2834，讀回 `0 / 4` 見 L2676/L2739 [F]
  - 原生格率選單沒有被改過，一直是 29.97（DNG 30000/1001，L2764，先前 audit 也這樣說）
  - 12-bit
- **240 不跟選單走**：00:55 那一版沒有 rate-from-menu，所以 AXIS rate 9 不會被選單的 29.97 改掉 [F：A001_170 在 29.97 選單下錄出 240 時序與 1/250；rs_hit 到 L6947 才出現]

---

## 4. 錄影路徑相關項目（逐項）

| 項目 | 9/29 H2 是否碰到 | 證據 |
|---|---|---|
| MovRec 任何站點 | **沒有** | 13 個 hook 清單（L2981/L2986）裡沒有 MovRec |
| DMA header / CPU header copy（C00FBB90、C038C77C） | **沒有** | 同上 |
| bulk size（C03A5144 / 64 MiB 批次） | **沒有**，原廠 64 MiB | 同上 |
| DNG FrameRate 標籤（C00C9BD0） | **沒有** | 01:07 才寫好 imx410_rate.S（L2992/L3010/L3040）；01:16 安裝零寫入（L3051）；01:17 Claude 確認「沒有 rate hook」（L3065）；A001_193 的標籤是 30000/1001（先前 audit），三者一致 |
| CRCT route / bin 路徑 | **沒有** | bin ÷1/÷1（AXIS 65537）；CG_BIN 不在執行期閘門內，「CRCT 對 CDNG 只是個宣告」（L2592） |
| 時鐘閘門 0x30110440（C0189440） | **沒有寫入**，原廠字 0x2C49F241 不變 | 不在 13 hook 裡，也不在 plan 類別裡（§1.5） |
| 感測器時序記錄 | 寫入，但值等於原廠 | §2.1 |
| 引擎格率 canvas +0x30 | 寫 0x436FC29F | §2.3 |
| 間接相關：快門角度四站（C02092CC/C0218AEC/C0219260/C03AA568） | 有，但值等於原廠 | §2.3 |
| 間接相關：og3kgs 增益分派（C03A6DD8） | 有 | §1.2 |

**C0189440 的推論 [I]：** 韌體 `FUN_c0189298` 在描述子 `+4 & 0x1000` 時，把 channel 0 設成 0x1249（5/16）。build 註解說這個條件就是「>99 fps」，imx410_canvas 註解也說 `FUN_c01cec08` 的 >99 閘門看的是 canvas `+0x30`。9/29 的 `+0x30` = 239.76，所以 **9/29 很可能是在原廠 5/16 閘門下錄滿 20 秒**。這一點沒有實機證據。

---

## 5. 使用者在那次 session 對這段錄影說過什麼

- 01:17 之前的使用者訊息：L2703「測試一下240禎」、L2917「把容器格率補上」、L3073「重插了」、L3106「不用半按啊 那是看idle live才要半按」、L3112「重裝吧」[F]
- **整個 session（到 L7461）都沒有提到 A001_193、SSD 錄了 20 秒、4809 格這類內容** [F]
- L11638（10-01 15:40Z）「240已經完成錄影，結果很好」說的是 10/01 那張卡，不是 A001_193 [F]

---

## 6. 與今日 consumer 的差異

今日的依據：
- `projects/open-gate/build/res-custom/build_v3_rescustom.py`（sha 2bf8b0ce…，v21）
- `ogc_layout.py`
- `ogc.c`（sha 99e5bd3f…）
- `H2S240.RCD`（sha 835d214c…）
- `projects/res-lab/validation/20261014-carrier-ab/h2-selected.json`（當時的實機快照，consumer v19）

| # | 項目 | 9/29 | 今天（H2S240） | 值相同？ |
|---|---|---|---|---|
| 1 | 感測器模式 id | **原廠 mode 12** 直接用（L2840） | **虛擬 mode 230**，donor 12。七張感測器表被 clone 到 consumer 緩衝，經 8 個 lookup hook（lk_tim C0320BA0、lk_meta C0320B38、lk_r28 C0320E90、lk_r38 C0320F60、lk_r14 C0320EF8、lk_r68 C0320C00、lk_reg C0326DB8、lk_r10 C031FFA0）回傳假索引（ogc.c 733/753/845；h2-selected.json `MODE 230`、`donor 12`） | 時序字相同，**id 與取得路徑不同** |
| 2 | PARAM profile id | **p13**（真 id，L2721） | **虛擬 p74**，base 第 6 列（= p13 的列，MAPPING[13]=6），見 h2-selected.json `PID 74`、`variant [74,6,0,0]` | 預設值同源，**id 不同** |
| 3 | 時序記錄 0xC0B59A44/48 | 寫入原廠同值（imx410_fmt） | TT 宣告 EXCL 但從不寫（build L59 `TT ... never written`）；值由 VM clone 的 TW0/TW1 = 0x014A014A / 0x0006038E 提供（ogc_pick 899） | 值相同 |
| 4 | 引擎格率 FPSLATCH / canvas +0x30 | 0x436FC29F [I] | `ENT_ENGFPS` = 0x436FC29F（h2-selected.json `FPSLATCH 1131397791`）；ogc_canvas 寫 +0x30（ogc.c 1115） | 相同 |
| 5 | 25 對畫布 | L2744 | RCD `canvas_rec` 逐對相同（manifest.json） | 相同 |
| 6 | canvas +0x80/+0x84 | 7/7（在 25 對裡） | 由 BITLATCH 決定：BD12 時 7/7（ogc.c 1115） | 相同 |
| 7 | m12_legacy_canvas（+0x88=4 等） | 無 | 只對 p83 base 生效（m12_p83_entry），H2S240 是 p13 base，所以不觸發（h2-selected.json `M12_LEGACY_HITS 0`） | 無變化 |
| 8 | 預覽可見高 | GTAB 改六個 PARAM +0x28 = 1334（寫韌體欄表）[I] | RCD prev_h 1334，用 apply_standby 寫進畫布，不寫欄表（ogc.c 1064） | 值相同，**機制不同** |
| 9 | picker 表項 | 1 筆 ENTRY，key「CUST…」，mode 12，PROFILE 13 | 14 筆（NENT 14），key「H2S24030」，PID 74 / MODE 230 | 不同 |
| 10 | 原生格率載體 | 29.97 選單 | 29.97 carrier（h2-selected.json `frame_rate_getter "3"`） | 相同 |
| 11 | 13 個共同 hook 站點 | 有（§1.2） | picker / setter / fmtset / canvas / name / aspect / aspect2 / out / gs / fps1–4 全都有（ogc_layout.py 238–247），payload 邏輯不同 | 站點相同，程式不同 |
| 12 | hdrcopy C00FBB90（tw） | **無** | **有**。每次呼叫都經過 veneer 加 shim；`caller != 0xC038C780` 時直接返回，239.76 也返回 0（只有 280 才複製），但每個符合 caller 的呼叫都會累加計數並跑 m12_header_entry 檢查（ogc.c 547） | 多一層路徑 |
| 13 | bulk C03A5144（bl） | **無**，原廠 64 MiB | **有**；239.76 保留 64 MiB，只在 280 改成 4 MiB（ogc.c 536） | 239.76 值相同，多一個 hook |
| 14 | recrate C00C9BD0（b） | **無**（§4） | **有**；VRATE=0 時返回 0，標籤維持 30000/1001（ogc.c 451） | 標籤相同，多一個 hook（每個 DNG 都會呼叫）[I] |
| 15 | PAIR_SITES 解析度轉換器 C06BDA3C/40/48 | **原廠**（原廠字 0xE300220C / 0xE34C22E4 / 0xE3A02003） | 改成指向 S.PAIRS（ogc.c 約 2770） | 不同 |
| 16 | PAIR_SITES 格率轉換器 C06BDB0C/10/18 | **原廠**（0xE3002224 / 0xE34C22E4 / 0xE3A0200A） | 改成指向 S.RPAIRS | 不同 |
| 17 | PAIR_SITES 格率摘要 C06CB6DC/E0/E8 | **原廠**（0xE3042EE4 / 0xE34C22E4 / 0xE3A02009）；這一項 9/29 05:30Z 才在 imx410 加入（L5474） | 改成指向 S.SPAIRS（export → state） | 不同 |
| 18 | 時鐘閘門 C0189440 | **原廠** 0x2C49F241（movw ip,#0x1249），推論 5/16 有作用（§4） | **一律改成 0x7CFFF64F**（#0xFFFF），ogc.c 2788 | **相反** |
| 19 | 其餘今日 hook（9/29 都沒有） | — | vpro C043A18C、cmt_set C057A6A0、cmt_qs C05824D0、save C0088C60、ac38 C031AC38、acd8 C031ACD8、zg C031B660、v32 C03249A0、qsrec C05E6400、qslay C05D90F0、qsload C05E84D8、cropst C04A1788、cropeff C00A93BC、frmax C00A87E4、frclass C04A121C、mag C043B6A4、rcmt1 C057A6F8、rcmt2 C05821B8、tvmin C007F5B4、tvmin2 C0553CDC、tvdisp C00A075C、anglist C0554768、angtv C052DCFC、ratio C02DAFA0、vrcgui C056461C、binpath C0325228、binkernel1 C032DDF0、binkernel2 C032DE70、bitclass C04A13E4、bitnorm C00A7FFC（ogc_layout.py 233–290；加上表中其他項，今天共 59 個 hook，9/29 是 13 個） | 9/29 沒有 |
| 20 | bin / CRCT 路徑 | 完全沒碰 | binpath、binkernel1/2 有掛 hook（bin=1 時是否 pass-through 未驗證） | 9/29 沒有 |
| 21 | 載入方式 | USB shell 的 mem 寫入，RAM only；卡上是不明的 fpSup 產品，加上 shell 的 AutoRun | Loader v3 加 32RESCUS.BIN v21 加 RCD；Gyro2 / lossless / 00SHELL 是否在卡上，要看該次卡片 | 不同 |
| 22 | USB shell | 常駐 RAM，USB 線拔掉（接 SSD）[I] | 正式 SSD 測試時關掉（res-lab memory） | **9/29 反而更多** |
| 23 | 選單 CSV / 控制器上限 | 寫 0xC0F8E7EC 與 0xC1A709BC | 走 uishare 套娃（ui_rows） | 不同（UI 層） |

---

## 7. 對持續錄影最可能重要的差異（排序）

1. **今天的時鐘閘門 C0189440 被強制開到全速（0x7CFFF64F）；9/29 沒動，維持原廠 0x1249，推論 5/16 有作用。**
   - 9/29 是在原廠閘門下 SSD 錄滿約 20 秒，今天開全速只把 12-bit 延長到 36–40 秒。v21 預設對 H2S240 也生效（ogc.c 2788），這是目前**唯一一個與 9/29 方向相反**的寫入。
   - 證據：§4；transcript 沒有任何 C0189440 寫入（L2981/L2986 的 hook 清單、L2840）；build_v3_rescustom.py 56–58。
2. **虛擬 sensor mode 230 與虛擬 profile 74，取代原廠 mode 12 與 p13。**
   - 9/29 韌體看到的是原生 id，時序表與 PARAM 走原廠查表。今天七張感測器表經過 8 個 lk_* hook 用假索引回 clone 緩衝，profile 也是不在原廠映射裡的 74。
   - 任何依 id 做特例或每格查表的錄影端程式碼，兩天會走不同的路。
   - 證據：L2840「mode 12」、L2721「donor 13」；h2-selected.json；ogc.c 733–870。
3. **錄影熱路徑上多出來的 hook：hdrcopy C00FBB90、bulk C03A5144、recrate C00C9BD0。**
   - 對 239.76 都設計成不改值，但都在 MovRec 或 DNG 寫入路徑上加了 veneer、shim 和計數；hdrcopy 掛的是被多個 caller 共用的內層複製入口。
   - 9/29 這三處全是原廠字，見 §4（L2981/L2986/L3051/L3065）。
4. **三組 PAIR_SITES 轉換器被改寫（解析度、格率 row↔internal、格率摘要 export→state）。**
   - 9/29 全是原廠字，原生格率狀態完全由原廠表推出；今天由 S.RPAIRS / S.SPAIRS 決定。在 29.97 carrier 下理論上等價，但沒有逐對驗證。
   - 證據：§1.5；L5474（RATE_PAIR 05:30Z 才首次出現）。
5. **另外 30 多個 UI、快門、bin 相關 hook，以及卡上的其他模組。**
   - 9/29 只有 13 個 hook，卡上產品沒有碰 imx410 監看的位址（L2131 `stock`）。今天 59 個 hook，Gyro2 / lossless 等是否在卡上要另外核對。
6. **相同、可以排除的項目：** 感測器時序字（0x014A014A / 0x0006038E）、引擎格率 0x436FC29F、25 對畫布、+0x80/+0x84 = 7/7、預覽高 1334、29.97 carrier、12-bit、FrameRate 標籤 30000/1001、64 MiB 批次（239.76 時）、沒有 CPU header copy。證據見 §2 與 §6 第 3–7、10、13、14 列。

### 仍然未知（transcript 沒有，不要當成已知）

- A001_193 的 HDMI 狀態、SSD 寫入模式
- 卡上 fpSup.BIN / AutoRun.txt 是哪個產品，是否含 Gyro
- A001_193 開錄時實際的 FPSLATCH 與完整 65 欄畫布
- 00:55 那份 imx410_plan.py / og3krecipe.S / imx410_fmt.S 的逐字內容
