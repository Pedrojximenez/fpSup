# 虛擬 mode 230／p74 與原生 M12／p13 的等價性稽核（靜態、離線）— 2026-10-14

範圍：SIGMA fp 5.02 韌體映像 `out/MAIN_c0000000.bin`（初始化資料在 `out/seg1_c2ef6e00.bin`），Ghidra 全反編譯 `out/decomp/full/*.c`，以及 RES-Custom consumer 原始碼 `projects/open-gate/build/res-custom/`（ogc_layout.py、ogc_shims.S、ogc.c、ogc_virtual.c、VIRTUAL_RCD.md）。
全程沒有碰相機、USB、fpshd/fpsh，也沒有執行任何連到硬體的腳本。

- **[F]** 事實：反組譯、反編譯或資料裡直接看得到，附位址。
- **[I]** 推論：附理由。
- 掃描工具都放在 session scratchpad：BL/BLX 與 Thumb BL 交叉引用、movw/movt 常數引用、表格 inline scan 偵測。這些不是專案檔。

---

## 0. 結論先講

1. **[F/I] mode id 這一層，8 個 hook 之外沒有任何路徑會讓 230 和 12 走出不同、而且碰得到 DMA、匯流排、時脈、buffer、writer、優先權或閘控的設定。**
   - 未覆蓋的 mode 消費點，每一個對 12 和 230 都給出相同結果，原因有三種：
     - 12 本身也沒命中（放大鏡表只有 mode 3 和 10）；
     - 只做「等於」或「有沒有變」的比較；
     - 只比對 {58,89}、{102,108,124,152} 這類 12 不在其中的集合。
   - 唯一真正不同的地方：除錯／shell 用的 mode 名稱表 `PTR_ACQ_c2f1e2dc[mode]` 只有 222 筆，230 會讀過表尾。這只在開啟除錯列印時才會發生。
2. **[F/I] profile id 這一層，p74 和 p13 也沒有可量測的差異。**
   - pid 只用在三個地方：MAPPING 索引（已 hook，vpro）、class 位元（p13 和 p74 都是 0），以及「是否相等」的比較或 log。
   - 沒有其他以 pid 直接索引的陣列，也沒有其他 pid 範圍判斷。
3. **[F] 頻率閘門不看 mode 或 pid。**
   - C0189440 那一類 `>99 fps` 閘門看的是引擎 cadence，也就是 canvas +0x30 → 通道 fps。
   - 另有一條看「錄影設定的格率 enum」的路徑（錄影開始時關掉 LV 顯示管線，C03A1558）。這是 29.97 和 119.88 載體之間唯一的差別來源。
4. **[I] 所以「36–40 s 自停」不是因為某個 lookup 漏接了 mode 或 profile id。**
   - 9/29 原型用的是 29.97 載體（H2_0929_STATE.md）。今天同樣用 29.97 載體（20261014-carrier-ab），0.6–0.85 s 就停了；9/29 卻錄了 20 s。
   - 在 mode／pid／rate 這三層，9/29 和今天的韌體行為相同。
   - 因此差異應該在「表格內容」以及「consumer 額外做的事」。§5 列出還沒有逐字比對過的項目，那才是下一步的重點。

### 統計

| 類別 | 個數 | 說明 |
|---|---|---|
| mode：(a) 經 8 個 lookup 或其 wrapper | 約 60 處 | 含 IMAGER +0xC/+0x10/+0x14 的快取 index，由 FUN_c0321290 經已 hook 的 lookup 算出 |
| mode：(b) 其他 hook 覆蓋 | 6 處 | ac38、acd8、zg、v32、fps1–4 |
| mode：log、no-op、callee 不吃這個參數 | 約 25 處 | |
| mode：只做相等或「有沒有變」比較 | 約 20 處 | 全程同一個 id，230 和 12 語意相同 |
| mode：(c) 未覆蓋 | 11 類 | 會影響錄影的差異：0；唯一不同是除錯名稱表越界 |
| pid：hook 覆蓋 | 3 處 | vpro C043A18C、canvas C043A19C、gs C03A6DD8 |
| pid：未覆蓋 | 3 個 obj+0 讀者、38 個 class 位元呼叫點、1 個開機 buffer 上限迴圈 | p13 和 p74 全部相同 |
| 頻率閘門鍵在 mode 或 pid 上 | 0 | |

---

## 1. mode id 與 profile id 存放在哪裡

### 1.1 感測器物件與描述子

- **[F] IMAGER = 0xC343B588**，建構在 FUN_c03255f8 → FUN_c031fe08。
  - +0 = 描述子指標，指向 **0xC2F1E654**（FUN_c0322e88 以 movw/movt 帶入）。
  - +4 = 現在的 mode，初值 0x78。setter 是 FUN_c03212e0，getter 是 FUN_c03212f8、FUN_c032c720。
  - +8 = 前一個 mode。setter 是 FUN_c0321308，getter 是 FUN_c0321320、FUN_c032c738。
  - +0xC、+0x10、+0x14 = TIM、R28、R14 的快取 index，由 FUN_c0321290 呼叫 lk_tim、lk_r28、lk_r14 算出，在 setMode FUN_c0314708（C0314830）裡呼叫。
  - +0xD0 = vtable 0xC0B5FCC0（XC_ImageSensorIMX410）。
  - +0x58、+0x5C、+0x60.. = 除錯用的暫存器 override，見 §2 (c)-8。
- **[F] 第二份 mode：ImgMode 物件 0xC343A6D8 +0**，由 FUN_c0314708 寫入（`*param_1 = mode`）。
  - 經 FUN_c030cea0、FUN_c03151c0 讀，約 118 處，分布在 AF、AE、PDAF、adjust、ContSet、PreExpos。
  - 這些讀者最後都進到 lookup wrapper，或只做相等比較（fork A 的分類）。
- **[F] 其他 mode 快取：**
  - _DAT_C31D8A04/08/0C，由 FUN_c01257e0 寫、FUN_c01257b0 讀，下游都已覆蓋。
  - DAT_C2F1E1E0（c0312ac8）、AE 物件 +0x48（c020bef8）、C2F186AC（c0289e78）、setChangeSensorMode +0x12c。
  - 全部只拿來做「有沒有變」的比較，或傳給已覆蓋的 lookup。
- **[F] 描述子 0xC2F1E654 的表格欄位**（初值在 seg1，每張 70 列，列 ID 完全一致，含 mode 12）：

| 欄位（base／count） | 位址／列數 | stride | 讀取方式 | 覆蓋 |
|---|---|---|---|---|
| +0x00／+0x04 TIM | 0xC0B59500／70 | 0x20 | lk_tim C0320BA0；快取 +0xC | 已覆蓋 |
| +0x08／+0x0C META | 0xC0B59DC0／70 | 100 | lk_meta C0320B38（c0321028 與 c032c7xx 系列） | 已覆蓋 |
| +0x10／+0x14 R10 {value, mode} | 0xC0B5B918／70 | 8 | lk_r10 C031FFA0 | 已覆蓋 |
| +0x24／+0x28 R28 | 0xC0B5BB48／70 | 0x28 | lk_r28；快取 +0x10（c0320270、c03205f8、c03206b0） | 已覆蓋 |
| +0x40／+0x44 R38 | 0xC0B5C638／70 | 0x38 | lk_r38（c0320ab0） | 已覆蓋 |
| +0x48／+0x4C R14 | 0xC0B5D588／70 | 0x14 | lk_r14；快取 +0x14（v24 c0324c20 等） | 已覆蓋 |
| +0xF4／+0xF8 R68 | 0xC0B5DB00／70 | 0x68 | lk_r68（c0321100） | 已覆蓋 |
| +0x114／+0x118（未命名） | 0xC0B5F770／**2** | 0x38 | 只有 FUN_c032d9a0（經 c0320af0）讀，**index 是呼叫端給的 0 或 1，不看 mode** | 不需要 |
| +0x128／+0x12C ZOOM | 0xC0B5F7E0／**2**，列 ID 是 **10 和 3** | 0x5C | inline scan（§2 (c)-6） | 部分 hook；12 本身沒有列 |
| REGDESC 0xC0B5FDA4 {base, count} | | 0x288 | lk_reg C0326DB8，miss 時回 0xFFFFFFFF | 已覆蓋 |

- **[F] 描述子其他欄位都是純量，不分 mode。** +0x50..+0x140 由 FUN_c0322ea0 從 0xC0B5F898..F96C 複製（含 +0x74 時脈、+0x89、+0xFC 旗標）。
- **[F] MAPPING 0xC0BD05D4 全映像只有一個讀取點：C043A18C**（FUN_c043a158，已 hook 為 vpro）。FUN_c0439d18 用到的 65 個 PARAM 欄陣列，也只有 FUN_c0439d18 自己引用。
- **[F] 描述子各表的 base 位址在 code 裡沒有任何直接引用**（literal 與 movw/movt 都查過），只透過描述子間接取得。

### 1.2 profile

- **[F] picker 表項 {5, pid, mode, keyptr}，stride 0x10。**
  - 原廠 CinemaDNG 三張表 0xC0BE5810、59B0、5B50 用的是 pid 131..190 和 417..434。
  - M12 對應的是 p13。
- **[F] profile 物件 XC_LiveViewFieldAngleTable 由 FUN_c043a158(obj, pid) 建立。**
  - obj+0 = pid。
  - obj+0x5C = 65 字的 PARAM 記錄，由 FUN_c0439d18 以 `MAPPING[pid]` 當欄 index 填入。
  - obj+0x168 = class 位元，由 FUN_c043a1c8 計算（C043A1C8..C043A2D4）：
    - pid 1..4 → bit0；5..11 → bit1；
    - 101..129、191..197、301..312、401..416 → bit2；
    - 131..190、417..434 → bit3（raw movie）；
    - 29..40 → bit4；17..28 → bit5；
    - 記錄 +0x84 == 0xB → 0x100。
  - **p13 和 p74 都得到 0。**
- **[F] canvas hook 在 C043A19C**，位於 FUN_c0439d18 之後、FUN_c043a1c8 之前，所以 class 是用 hook 過的記錄算出來的。

---

## 2. mode 消費點：未覆蓋項目 (c)

| # | 位址 | 內容 | mode 12 | mode 230 | 子系統 | 可能性 |
|---|---|---|---|---|---|---|
| 1 | FUN_c031fd70 = `PTR_ACQ_c2f1e2dc[mode]`（222 筆）；呼叫端 c0314ee8、c0314f30、FrameExpos_s c03161dc、c03eb8c8..c03f34b0 的 shell dump（約 30 處） | 直接以 mode 當 index 查名稱表 | "MONIT1_240" | 讀過表尾，[I] 落在 desc 區附近，可能拿到 NULL | 除錯 log、shell 診斷 | 低（要開除錯旗標才會跑；[I] 最壞是印字出錯） |
| 2 | IMX410 v33 c0324fd8 | mode ∈ {102,108,124,152} → 1 | 0 | 0 | 感測器 | 無差異 |
| 3 | IMX410 v34 c03248e8 | mode ∈ {58,89}（FHD120、FHD100）→ 1 | 0 | 0 | 感測器 | 無差異 |
| 4 | FUN_c03543f8（c0354400） | {153,154}、{166..174}、{183} 三段範圍 | 範圍外 | 範圍外 | | 無差異 |
| 5 | AF：c0293a64（#0x1b、#6）、c02a4bd8、c023f354（#0xb）、c027eb34（#0x3e） | 常數 `==` | 不等 | 不等 | AF | 無差異 |
| 6 | 放大鏡表未 hook 的 inline scan：c030e7f0、c030f1a8（FUN_c030e2a0）、FUN_c030fd68（c030fde0）、FUN_c0310120（c0310184）、FUN_c032df88（c032e048）、FUN_c031b3a0 第二段 c031b940 | 掃 desc+0x128 | **miss**（只有 3 和 10 有列） | miss | 放大窗、缺陷像素座標裁切 | 無差異（[F] FUN_c030fd68 miss 時用 index 0xFFFFFFFF 讀 row −1，但 12 也一樣） |
| 7 | desc+0xFC 閘控路徑：FUN_c030f698、c0312d18、c0312ac8、c0312d70 → FUN_c051f550、c030f710、c030f880 | | 初值 0，沒找到寫入點 | 同左 | | 低 |
| 8 | 除錯 override：IMX410 v6 c03234a0（`imager+0x58` 旗標、`+0x5C == mode`）、FUN_c0320740（+0x45、+0x54） | 以 mode 為鍵的額外暫存器寫入 | 旗標預設關；**shell 指令 `imager_reg_add_flag`（FUN_c03eaec0）才會打開** | 同左；若有人以 12 為鍵打開，230 會漏掉 | 感測器暫存器 | 低（預設關） |
| 9 | AF 鏡頭物件 vtable+0x58，傳入 mode（c023d17c、c027b928、c027b964、c02a3c84、FUN_c0253b50） | 沒追到底 | — | — | AF | 低（[I] MF 錄影不相關） |
| 10 | desc+0x114 表（FUN_c032d9a0） | index 0 或 1 | — | — | 讀出設定 | 無差異（不看 mode） |
| 11 | FUN_c032ce30 和 0xC2F1E918 的表（stride 0x1C） | 鍵是 HPF 設定 id（1..40） | — | — | | 無差異（不是 mode） |

- **[F] 旁注：** lk_reg（FUN_c0326db8）miss 時回 0xFFFFFFFF，其他 lookup miss 時回 0。
  - 假如 consumer 的 REG clone 失敗而退回原廠 lookup，FUN_c03258c8 會從 `base − 0x288` 寫 160 多個感測器暫存器。
  - 一般狀況下不會發生，因為 donor 12 一定有 REG 列。
- **[F] 掃描也找到兩個以 R68（+0xF4）為對象的 inline 迴圈：FUN_c05211b0（c052148c）、FUN_c0523728（c0523a48）。**
  - [I] 兩者都在工廠調整、缺陷像素的程序區（c051..c052，CamSch1 → 6、清緩衝），不在錄影路徑上。
  - 它們如果是「列舉全部 mode」，虛擬列不在原生表裡，本來就看不到。可能性：低。

---

## 3. profile id 消費點

- **[F] 表項 +4（pid）全映像只有一個讀者：FUN_c0437630（C0437658）。**
  - 路徑：FUN_c0436288（ubfx 截成 16 位元，對 74 無影響）→ FUN_c0439668 → FUN_c0439740 → FUN_c043a158。
  - 另外兩個用表項 pid 建 profile 物件的地方：FUN_c0437140（8 個呼叫端，錄影與 LV 路徑）、FUN_c030fb20（只用於靜態 YUV/RAW）。
- **[F] 現行 profile 物件放在 LVstate+8（FUN_c04375c8）。** 23 個呼叫端中只有 3 個讀 obj+0：
  - C03A6238（FUN_c03a6228）：把 pid 複製到 LiveViewFuncModeChanged 快照 0xC359BF20。FUN_c03a0300 只比較相等，用來決定要不要重啟 LV。
  - C040ECEC（LiveViewModeChangedLogger）：只寫 log。
  - C0428B84（FUN_c0428ab8，影片訊號設定）：assert 兩個 profile 指標的 pid 相同，並寫 log。
- **[F] 全映像掃描 131/190、417/434 的立即值**（cmp/mov/rsb/sub），只命中兩處：
  - FUN_c043a1c8（class 計算）；
  - WaitEnc C044C380..C044C89C：誤報，是暫存器寫入的參數，不是 pid 判斷。
- **[F] class 位元的消費者，共 39 個呼叫點**（vtable +0x18 回 obj+0x168；各 bit 的 accessor 在 C0436008..C04360F8）：
  - bit3（raw movie，C0436080）2 處：C03A6734（FUN_c03a66b0，**未 hook**）、C03A6DE8（FUN_c03a6dd8，已 hook 為 gs）。
  - 其餘各 bit 共 37 處。
  - p13 和 p74 都是 0，結果相同。
  - **[I] C03A6734 這一點值得記下：p13/p74 和原廠 raw movie pid（131..190）在這裡不同，但 9/29 有同樣的缺口，仍然錄得很穩，所以不是今天和 9/29 的差異。**
- **[F] 開機時的 buffer 上限：** configurator 建構子 FUN_c043a2d8（C043AA5C..C043AD5C）取原廠表項的 FUN_c0435588 最大值（3856×2170 等級）。
  - p13 和 p74 都不在這個迴圈裡，1008×672 遠低於上限。可能性：低。
- **[F] FUN_c0429910（MovSigProcess）把 pid 寫進通道設定第 0 字**，FUN_c01d1630 再存到 0xC31DF3BC。
  - 反編譯文字裡只看到這一次寫入，沒找到讀者。
  - [I] 可能經由 base+offset 間接讀取，Thumb 側的 literal 引用還沒查完。要等確認沒有讀者，才能把 p74 的這條線完全結案。

---

## 4. 頻率閘門（C0189440 那一類），以及會不會鍵在 mode／pid 上

- **[F] FUN_c0189298（Thumb）：** `(cfg+4) & 0x1000` 時，ch0 的時脈是 0x1249（C0189440，現已改為 0xFFFF），ch1 是 0xFFFF。
  - bit 12 由 FUN_c01caba0 依 FUN_c01cec08(ch) 設定，條件是 `chfps(ch) > 99.0f`（常數在 C01CEF80）。
  - chfps 放在 0xC31DF574 + ch*0x1B0，由 FUN_c01d1630 從 cfg+0x10 寫入。
  - cfg+0x10 的來源是 **PARAM 記錄 +0x30**（FUN_c0434ef8，經 MovSigProcess FUN_c0429910）。
  - **所以這組閘門看的是 canvas +0x30，不看 mode 或 pid。** 9/29（FPSLATCH 0x436FC29F）和今天（ENT_ENGFPS）都是 239.76，兩者相同。
- **[F] 同一個 bit12 或 FUN_c01cec08 的其他消費者，都沒有 patch：**
  - FUN_c0179b38（blk_c01 約 L66763/66917/66955/67048/67140）
  - FUN_c01d6980
  - FUN_c01302f8（>99 時跳過 FUN_c019e270(ch)）
  - FUN_c01ca138 → FUN_c019bee8
  - FUN_c01cb9b8（param+0x100 存 1 而不是 2）
  - FUN_c01ca5a0、FUN_c01c3d38、FUN_c01c4708、FUN_c01c7968、FUN_c01cc868、FUN_c01cdbe0
  - FUN_c01c9e38（239.76 掉到顯示格率 30.0）
  - [I] 9/29 時這些也全部是原廠狀態，所以不能解釋今天和 9/29 的差距。可以當作待測的手段，但不要盲目 patch。
- **[F] 看錄影設定格率 enum（FUN_c0021c40()+0x14）的路徑：** XC_RecMgrImpl v46 C0372278 → FUN_c03a1558。
  - 條件：CinemaDNG、某設定值不是 0/3/4、enum 6–10（100 或 119.88 載體）。
  - 成立時呼叫 FUN_c0423e60，經 FUN_c042a6d8 → FUN_c01d88a0 **在錄影期間停掉 LV 顯示管線的一個通道**；v47 C0372298 → FUN_c03a1608 → FUN_c01d8928 再恢復。
  - enum ≤4（29.97）完全跳過。
  - [I] 這可以解釋今天「119.88 載體 36–40 s，29.97 載體 0.6–0.85 s」。但 9/29 是 29.97 載體、顯示管線照跑，仍錄了 20 s，所以它不是 9/29 和今天之間的差異。它和 mode／pid 無關。
- **[F] 其他看載體 enum 的路徑都和吞吐無關：** 時間碼（FUN_c037ff70、FUN_c01fed68）、DNG FrameRate（C00C9BD0，已 hook 為 recrate）、音訊重設、MOV 位元率表 C0B9BA08（[I] H.264 路徑）。
- **[F] writer 批次（C03A5144，bulk）和 96 個描述子池（cmp #0x60，在 C03753CC 等）不看格率，也不看 mode 或 pid。**
- **結論 [F]：沒有找到任何以 mode id 或 profile id 為鍵的時脈、DMA、buffer 閘門。**

---

## 5. clone 是否完整，以及還沒逐字比對的差異（下一步）

### 5.1 per-mode 表

- **[F] 韌體依 mode 讀的表：** TIM、META、R10、R28、R38、R14、R68、REG、ZOOM。consumer 全部有 clone：
  - ogc.c `vm_fill`、`vm_fill_reg`、`vm_zoom`；
  - R10 存成值（VM_R10）；
  - ZOOM 在 donor 12 沒有列時不 clone（ZFILLED=2），和原生行為一致。
- **[F] desc+0x114 不分 mode，不需要 clone。**
- **[F] 快取 index（IMAGER +0xC/+0x10/+0x14）是 fake index。** 反編譯裡沒有看到任何拿它和 count 做邊界檢查的地方。
- **[I] 唯一可能的不同：** `vm_apply` 會把選取表項的 TW0/TW1 寫進 TIM 的 +4/+8，`vm_override` 會套用 RCD 的 override，clamp 會改 R38 的 +0x04/+0x18。
  - VIRTUAL_RCD.md 說 M12240 的 239.76 TW0/TW1 和原廠完全相同。如果沒有 override，clone 會和 donor 逐字相同。
  - **建議拿實機讀回的 230 七張 clone 列和 REG 列，與 mode 12 原生列做逐字 diff。** 這是最便宜、也最能排除這一層的檢查。

### 5.2 PARAM 記錄（profile）

- **[F] vpro 把 p74 對到 p13 的 MAPPING 列（index 6），ogc_canvas 再套 ROW_REC 和 variant 的配對**（M12240 的 24 對，來自 9/29 的讀回），並設定 +0x30 = FPSLATCH；12-bit 時另設 +0x80 = 7、+0x84 = 7。
- **[F] 依 p13 原值保留、但和原廠 raw movie p171 不同的欄位：** +0x38 = 1（p171 是 0x10）、+0x58 = 0（1）、+0xC4 = 0（1）、+0x88 = 0。
  - [I] 如果 9/29 的 25 對讀回已涵蓋它的完整模板，今天和 9/29 會相同。但 9/29 的模板（og3krecipe／CTMPL，帶 CG_OVER60／CG_ZOOM 閘門）已經無法逐字還原（H2_0929_STATE.md §1.1）。
- **[F] 9/29 另外依 FLAG 對六個預覽 PARAM（0xC0BDB9CC、0xC0BDBC28、0xC0BDBC60、0xC0BDBC8C、0xC0BDBC90、0xC0BDBC94）的 +0x28 寫 1334**（GTAB，H2_0929_STATE.md §1.5）。
  - 今天對應的是 standby groups（ROW_SBY）。要核對 M12240 是否帶了相同的 6 個 pid 和值。
- **[I] PARAM +0xA4（buffer class，FUN_c0435E38）由 profile 記錄決定。** p74 繼承 p13 的值。要確認 9/29 的 p13 和今天的 p74 在 +0xA4 上相同。
- **[I] 缺口（中低）：** vpro 對 p74 無條件換成 base 列，但 ogc_canvas 只在 `S_FLAG && CUR`、而且 `VAR_ROW == CUR−1` 時才覆寫。
  - 在這個時間窗之外建立的 p74 物件，會拿到裸的 p13 記錄（raw 寬高 0×0）。[I] 後果比較可能是壞檔，而不是變慢。

### 5.3 consumer 額外做、9/29 沒做的事

- 9/29 只有 13 個 hook（H2_0929_STATE.md §1.2）。今天另外有 hdrcopy、bulk、lk_* ×8、ac38/acd8/zg/v32、binpath/binkernel、bitclass/bitnorm、frmax/frclass、C0189440 等。
- carrier-ab 讀回 `HDR_COPY_HITS 0`、`BULK_HITS 0`，所以這兩個沒有作用。
- hookcnt 顯示 hook 的 CPU 負擔可以忽略。
- [I] 剩下的差異候選是「內容」，不是「呼叫次數」：binkernel 對 CRCT 係數的修改、bitclass 的 12-bit 正規化，以及 §5.1、§5.2 的表格內容。

---

## 6. 嫌疑排序（針對 240p 12-bit 錄影吞吐與穩定度）

| 名次 | 項目 | 位址 | 理由 | 可能性 |
|---|---|---|---|---|
| 1 | PARAM 記錄內容與 9/29 不同（+0xA4 buffer class、+0x38/+0x58/+0xC4、預覽 +0x28 的 GTAB 對 standby group） | C043A19C canvas、ogc_canvas、FUN_c0435E38 | mode／pid／rate 三層都和 9/29 相同，剩下的自由度就是記錄內容；9/29 模板無法逐字還原 | 中（[I]） |
| 2 | consumer 的 clone 列和 override 是否與 mode 12 原生列逐字相同 | ogc.c vm_fill/vm_apply/vm_override | 理論上相同，但沒有實機 diff | 中低（[I]） |
| 3 | 錄影期間 LV 顯示管線的關閉 | C03A1558 / C03A1608 / C042A6D8 | 只看載體 enum；能解釋今天 29.97 和 119.88 的差異，不能解釋和 9/29 的差異；可以當手段（對虛擬高格率強制呼叫 FUN_c0423e60(obj,3,1)） | 對「載體敏感」是高，對「9/29 差異」是低 |
| 4 | 沒 patch 的 `>99` 閘門家族 | FUN_c0179b38、FUN_c01d6980、FUN_c01302f8、FUN_c01cb9b8 等 | 看 canvas +0x30；9/29 也是原廠狀態 | 低 |
| 5 | pid 進到通道設定 0xC31DF3BC | FUN_c0429910 → FUN_c01d1630 | 還沒找到讀者 | 低（待查完） |
| 6 | 未 hook 的 raw movie class 判斷 | C03A6734（FUN_c03a66b0） | p13 和 p74 相同，和 9/29 也相同 | 低 |
| 7 | 除錯名稱表越界 | FUN_c031fd70 | 只在除錯列印時 | 低 |

---

## 7. 證據檔與方法

- 描述子內容：`seg1_c2ef6e00.bin` 位移 0xC2F1E654（初值），再加上 FUN_c0322ea0 執行期複製的純量。
- 表項傾印：0xC0BE5810/59B0/5B50，每筆 {5, pid, mode, key 字串}。
- inline scan 偵測：條件分支往回跳，前面有 `ldr cnt,[r,#F+4]; cmp`，迴圈體內有 `ldr [r,#F]`。結果中描述子相關的就是 §2 (c)-6 和 R68 的兩處。
- 分類工作分給三個並行的子分析：mode、pid、rate。各自的結論已併入 §2–§4。
