# IMX410 Lab —— 研究用 sup 設計(草案 2026-10-20,未經使用者確認)

目標：把 IMX410 的參數**全部**破譯成可驗證的規則。做法是一個研究用 sup 加一個主機端腳本，
讓「設定參數 → 取幀 → 拉回 → 分析」整套自動跑完，不用人按相機。
**不走 CinemaDNG、不寫卡**,RAW 幀直接經 USB shell 串回主機，每次只取幾秒。

---

## 1. 參數現況(三份盤點的彙整)

| 類別 | 已解 | 未解／矛盾 | 證據 |
|---|---|---|---|
| 模式暫存器 blob(161 筆,`0xC0B5FDAC`,70 模式) | 150/161:合併 `0x001C`/`0x0717`/`0x0058`、vblank `0x0016`、class `0x0001`、位深 10 筆、速度 `0x0062`/`0x007E` | `0x0003 0x0022-25 0x0056 0x0057 0x008A 0x0726 0x0790 0x079C`;`0x0726/0790/079C` 的「無效果」可能是 vtap_test 把 `%02X` 誤解析造成的(§7.54) | `research/imaging-hw/notes/SENSOR_REGISTER_DECODE.md` |
| 他牌才寫的暫存器 | — | Sony/Z CAM 合計 377 個位址,其中 **216 個 fp 從來不寫**(`0x0006-0x0015`、`0x0026-0x0041`、`0x04xx`、`0x07BA-07D2`…) | `sony_a7m3/.../sony_a7iii_imx410_operational_union.csv` |
| 時序(hmax/vmax/tail/視窗) | 表 `0xC0B59500`;frame = hmax·(vmax−1)+tail @72 MHz,70 模式全部吻合 | **vmax/hmax 怎麼送到感光元件完全不知道**,blob 裡沒有它們。視窗寫進 SoC 接收端 `0x30100024` | `research/imx410/notes/FRAME_RATE_IS_VMAX.md` |
| 快門 | `FUN_c03257d0` 寫 `0x0005/0x0006`,範圍 2..0x3FFE | 單位、每幀排程、第二個參數都未解;跟「`0x0005` = 幀高等級」的說法互相矛盾 | `out/decomp/full/blk_c03.c:25780` |
| 增益 | 類比 `0x3D-0x40`(線性 = 4095/(4095−code))、CG `0x05E1`、高類比 `0x05E2/0x041F`、gain_state 0-8 | OTP 校正值(0xC00 起 0x1FE bytes)全是離線推論;A/B 兩組增益的實際用途 | `research/imx410/notes/ISO_FIRMWARE_COMPLETE.md` |
| 黑位／clamp | DNG 從 `+0x208` 取;RAW12 約 256、RAW14 是 1024 | clamp 位元只做過離線分析 | `projects/open-gate/notes/VIDEO_CLAMP_V3.md` |
| SLVS-EC 通道與 embedded data | — | **完全未解**,只有唯讀 dump 腳本 | `research/imx410/probe_slvsec_*` |
| 匯流排 | `FUN_c0322c70(reg,val)` → 3 byte 封包 → `0xC0126550` | `0xC0126550` 沒研究過;`i2c list` 列不出 imager 這個裝置 | — |

最大的兩個盲點是「vmax 怎麼到感光元件」和「SLVS-EC／embedded data」。
這兩個問題都**不能再靠反組譯猜**,要在匯流排上看實際寫入了什麼。

## 2. sup 的三個功能

### A. 匯流排記錄器(解答「規則」用)
- hook `FUN_c0322c70`(必要時再加 `0xC0126550` 這一層)。每次寫入記成一筆
  `{時間 µs, reg, val, 呼叫者 LR, 當前模式 0xC343B58C}`,放進環形緩衝。
- 主機用 MEM1 拉回。這不是即時資料，不需要 EP83。
- 一次就能回答的問題：換模式、換格率(只改 vmax)、換 ISO、換快門、按 REC 的時候，感光元件各收到哪些寫入。
  如果改 vmax 時匯流排上**沒有任何寫入**,就證明感光元件是被 SoC 的 XVS 同步訊號從外面驅動的。

### B. 參數注入
- 沿用韌體原生的 `imager mode_reg_add/mode_reg_test`(上限 10 格，已實機驗證)。sup 只補一條
  「任意數量、任意位址」的直寫路徑：直接呼叫 `FUN_c0322c70`,不受 10 格限制,
  也能寫那 216 個 fp 從來不寫的位址。
- 每筆注入都先記進 A 的記錄器。實驗結束要能把全部值寫回原值，或要求重開機。
- **第一守則**:這些全部只動感光元件的暫存器和 RAM,絕不經過設定區。

### C. RAW 串流(不寫卡)—— 2026-10-20 使用者定:走錄影，只取消後段寫卡

做法：從 rec-core 的 Unlocked Writer(ULWR)分出一個「USB 收」版本，新 sup ID 是 `IMXL`。
- ULWR 已經把原廠的批次送出 `C063F140` 接管成「封塊 → 交給寫入 task」,並在 2026-10-15 上機通過。
  寫入 task 原本呼叫 `C01EB790` 寫 SD,這裡改成**不寫卡**:把資料搬到 DRAM 或推到 USB,
  然後照原樣呼叫 `C03A55D0` 回呼 cookie(status 0)。這樣原廠的錄影狀態機和 RAW 池都照常運轉。
- 送進來的已經是 DNG 格式(檔頭 + RAW),檔頭本身就帶這一幀的參數。
- 副作用：檔案系統仍會在卡上建立片段的檔案與目錄，但資料磁區沒寫，所以內容是垃圾，研究結束後要刪掉。
  要完全不碰卡，得在更前面攔截(MRecMgr 層),那是第二階段的選項。

USB 那一段要分兩步，因為「錄影中的 USB 傳輸」有凍結和空白輸出的前科
(`projects/usb-shell-sup/notes/RECORD_SHELL_COEXIST_RESOLVED.md`):
1. **C-a 先錄進 DRAM,停錄後再拉**:錄影期間 USB 完全不動。幾秒的量受限於可配置的 DRAM
   (FHD 12-bit 約 3.1 MB/幀,24p 3 秒約 224 MB),要先量可用量。這一步只驗證「取消寫卡」本身。
2. **C-b 錄影中由相機經 EP83 推送**:錄影的開始與停止由 sup 自己觸發(主機事先下一個指令，之後只被動 bulk-IN),
   主機在 record-start 那一刻不發任何交易。該筆記推測，衝突的根源是寫卡的 IRQ;不寫卡的話衝突可能消失，但要多次重複驗證。

舊的候選(保留作為參考):
完整 CFA Bayer 只在三種情況會進 DRAM:拍照、CinemaDNG 錄影、HDMI RAW 輸出。

| 候選 | 狀態 | 優點 | 代價 |
|---|---|---|---|
| **C1 HDMI RAW liveview** | 開啟條件只有「選單選 RAW + HPD」,但**從沒實機試過**取 framebuffer | 連續幀、不是錄影狀態;可以用 EP83 即時推，或先放 DRAM 再一次拉 | 要接 HDMI(或假造 HPD);格式是 12-bit,幾何要另外確認 |
| **C2 `imager createraw`** | 單次曝光加 RAWOUT,`line=0` 時不寫檔;安全性未驗證 | 每個參數點拿一張全解析度 RAW,最適合自動掃描 | 不是連續幀;6 個參數，要用 trampoline 呼叫 |

建議兩個都做：先做 C2(掃描主力)，再做 C1(看時序、滾動快門、逐幀變化)。
每一幀都附帶 A 的寫入記錄和當下的模式與增益，主機收到的是「幀 + 這一幀的完整參數」。

## 3. 主機端

`imx410lab.py`:實驗用 YAML 描述(模式 × 暫存器值 × 增益 × 快門)。依序執行：注入 → 取幀 → 拉回 → 存
`run/<日期>/<點>.raw + .json`,最後交給分析器(黑位、雜訊、亮度線性度、幾何、行列差)。
所有傳輸走現有的 `putfile.py`(MEM1)。安靜期的規則在 transport 層統一強制執行。

## 4. 平台(要使用者決定)

- loader v4:架構是定案的方向，但**還沒上過機**,頁面 UI 也還沒移植。
- v3:已在線上，但跟 v4 定案的方向偏離([[rebuild-first-principles]]、[[loader-v4-decisions]])。

研究 sup 本身不需要選單 UI,USB shell 就是它的介面。

## 4b. 2026-10-20 使用者改向：在進管線之前攔截

寫卡層(C-a)看到的已經是處理過的資料：OB 和 embedded 列被裁掉、寬度對齊過、RWZM 已經做完，
而且 liveview 同時在跑，每一幀跟暫存器狀態對不準。使用者指示：**在接收端把幀寫進 DRAM 的那一刻就攔下，
後段(RWZM、DNG、寫卡、liveview)一律不做**。C-a 不再上機驗證(使用者說「直接做」);
`sup/` 裡的 sink 程式碼留著，用來借 DRAM 和拉回資料。
上機紀錄:IMXL.BIN 已在 v4 載入過一次(`0A C504A080 IMXL.BIN`,3 claims),之後從卡上刪除。

## 5. 里程碑(使用者 2026-10-20 定：平台 v4、RAW 串流優先)

1. C-a:從 ULWR 分出 IMXL,移植到 v4,寫入 task 改成寫 DRAM。離線 unicorn 測試 + mutation → 上機錄 3 秒 → 停錄 10 秒後用 MEM1 拉回 → 解碼。
2. C-b:EP83 即時推送 + sup 自己觸發開始與停止錄影。
3. A 匯流排記錄器。
4. B 直寫 + 自動掃描那 11 個未解暫存器(重做 vtap_test 誤解析過的部分)。
5. 掃描那 216 個 fp 不寫的位址(每次只改一個，碰到卡死就記下來跳過)。

注意:v4 還沒上過機。IMXL 會是第一個在 v4 上機的 sup,出問題時要先分清楚是 loader 還是 sup 的問題。
