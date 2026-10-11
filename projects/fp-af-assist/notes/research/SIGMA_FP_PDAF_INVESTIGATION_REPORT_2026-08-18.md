# SIGMA fp 相位像素／PDAF 原始資料調查報告

> **2026-09-27 重審更正：** [新版原始資料核對](CROSSCAM_PDAF_FEASIBILITY_2026-09-27.md) 確認 `PdafCorrect` helper 的 runtime vtable `+A8` 實際為 v40 `C0322228` 返回 0，並重新計算 RAW／DNG 全幅相關係數為 0.9999658557，未精確重現下文舊值。未取得 phase pair 不代表已證明所有模式的相位資料「已消失」或物理上不存在；以下保留 8/18 當時的報告，当前判定、限制與停止規則以新版為準。

日期：2026-08-18  
目標機種：SIGMA fp，韌體 Ver.5.02  
感光元件路徑：`XC_ImageSensorIMX410`  
研究範圍：韌體靜態分析、AutoRun RAM patch、DNG 比較、StillCreateRaw 前 RAW 擷取、IMX410 mode table、SLVS-EC receiver／packet assembler 探針

## 1. 最終結論

目前證據不支持「SIGMA fp 的正常 IMX410 readout 中存在可供外部 PDAF 使用的遮罩相位像素資料」。更精確地說：

1. fp 的自動對焦執行路徑是 CDAF。AF model vtable 的 PDAF capability slot `+0x184` 在 fp subclass 指向 `0xC029BA08`，無條件回傳 0；因此 PdCaf setup、PDAF defocus、相位式連續對焦驅動均被 gate 掉。
2. Ver.5.02 是 fp 與 fp L 共用框架。韌體包含完整的 PDAF manager、鏡頭 PDAF 校正、shell 命令和 `PdafCorrect`，不能單憑這些符號斷言 fp 本身有相位像素。
3. `PdafCorrect @ 0xC030FB20` 確實存在，也有 `imager pdaf_cor_off <flag>`；但它會向 active sensor subclass 查詢 PDAF 幾何。IMX410 對應的 vtable slot 42（`+0xA8`）是空實作，IMX455 路徑才會計算幾何並呼叫 correction backend。
4. 直接 bypass `PdafCorrect`、關閉相鄰 WDD/BDD defect-table 參數後拍攝，DNG 中沒有出現新的固定週期遮罩圖樣。
5. 我們成功在 RAW DMA 完成後、`StillCreateRaw` 開始前，從 `0x5F900C00` 擷取 48 MiB。有效影像為 6064×4042、tightly-packed、MSB-first RAW14；此資料與同次曝光 DNG raw plane 的相關係數為 `0.99998646`。
6. 在這份真正的 pre-StillCreateRaw Bayer 中，掃描多種週期及四個 CFA phase，未找到可辨識的規律半遮罩像素殘差。這排除了「相位點在 CPU 的 StillCreateRaw/DNG 階段才被抹掉」這個主要假設。
7. 仍不能從軟體證據絕對證明晶圓上沒有相位結構。若特殊 sensor variant 在像素、列 ADC、sensor DSP 或 SLVS-EC 封包化之前已經屏蔽／替換它，機身端永遠看不到。但這種資料也就無法由 fp 韌體或外部演算法取回。

因此，工程判決應寫成：

> fp 5.02 的可觀測正常 readout 沒有可用 PDAF pair；共用韌體中的 PDAF 工具主要屬於 fp L／其他 sensor subclass。尚無證據證明 fp 晶圓物理上完全沒有遮罩，但即使有，也已在機身可截取點之前消失，不能作為可發布的外部 PDAF 功能基礎。

## 2. 為什麼最初會判斷「可能有相位像素」

### 2.1 IMX410 sensor family 的誘因

fp 使用 IMX410 路徑，而同 sensor family／相近 die 的其他相機常被認為具有 on-sensor phase detection。這使「SIGMA 採用特殊版本，但可能只是關閉 PDAF 使用」成為合理的研究假設。

不過，sensor family、die 名稱或像素總數相同，只能證明底層設計有親緣關係。Sony 可以透過 mask option、金屬層、microlens、color filter、片上 correction、OTP、mode register 或輸出封包配置，交付不同功能版本。它不能單獨證明 fp 成品上的相位遮罩存在。

### 2.2 韌體裡確實有大量 PDAF 元件

韌體字串及具名原始檔資訊包含：

- `AfMgrPhaseDetection.cpp`
- `AfMgrMeasurePdafDefocus.cpp`
- `LmountPdaf.cpp`
- `CafMode5_CheckPdaf`
- `defocusImpl`
- `PdafCorrect`
- `PDAF size=%u, %u, line=(...), interval=%u, sensor=%u`
- `imager pdaf_cor_off <flag>`
- `pdaf_cor_check`
- 鏡頭端 `DefocusPerPulse`、`PDAF Cor`、marginal correction coefficient

此外，PDAF configuration 看起來有 line、interval、區域和隨鏡頭條件改變的校正係數。這類結構的確符合相位系統，而非隨機壞點表。

早期判斷錯誤的關鍵，是把「共用韌體具備 PDAF framework」進一步推論為「IMX410 subclass 一定提供相位像素座標，而且 PdafCorrect 正在 fp 上執行插值」。後續 dispatch 分析顯示，framework 與 sensor-specific implementation 必須分開看。

### 2.3 「DNG 看不到圖樣，可能已被修掉」假設

最初對一般 DNG 做 FFT／週期分析看不到相位像素圖樣。當時提出的解釋是：

```text
sensor RAW → PdafCorrect 插值 → StillCreateRaw → DNG
```

若此模型成立，DNG 當然不會保留相位點；所以必須關掉 correction 或在它之前截取。這個假設促成了後續所有實驗，而且是合理、可否證的假設。最終 pre-StillCreateRaw dump 正是用來否證它。

## 3. 韌體靜態分析

### 3.1 AF 使用路徑

fp AF model subclass 的 vtable `0xC092B8D0` 中，PDAF capability slot `+0x184` 指向 `0xC029BA08`。該函式直接 `return 0`。

`CalcCafDriveSpeed` 及相關 PdCaf 狀態的唯一入口在前一層先檢查此 slot；回傳 0 時不會進入：

- PDAF setup；
- PDAF 可用性判定；
- phase defocus 寫入；
- pkcnt／phase tracking；
- PdCaf drive calculation。

無有效資料時，`measured_defocus` 使用 `-0x80000000` sentinel。這證明「相位對焦功能路徑」在 fp 正常配置中是死的，但當時尚不能獨立證明 sensor output 沒有隱藏 phase samples。

### 3.2 `PdafCorrect` 的真實角色

入口：`0xC030FB20`。原始首指令 word 為 `0xE92D4DF0`。實驗時以 `0xE12FFF1E`（`BX LR`）暫時 bypass，冷開機即可恢復。

shell handler 可接受 `imager pdaf_cor_off <flag>`，韌體列出的狀態包括：

- correct all off；
- acquisition correction off；
- acquisition software correction off；
- through correction off；
- correction on。

這證明 correction framework 真實存在且可控制，但仍不能證明每個 sensor subclass 都提供資料。

最重要的 cross-check 是 `PdafCorrect` 透過 sensor vtable slot 42（offset `+0xA8`）索取幾何／執行 sensor-specific setup：

- IMX410：對應實作為空，不產生座標圖；
- IMX455：計算 PDAF geometry，並進一步呼叫 correction backend。

因此先前把 stride `0x5C`、line／interval geometry 直接歸屬到 IMX410，是越過 dispatch 邊界的誤判。那些結構屬於共用框架或 IMX455 可達路徑。

### 3.3 一般 defect correction 與 PDAF correction

韌體中 WDD／BDD 與 `PdafCorrect` 是不同概念。為避免「雖關掉 PdafCorrect，但相位點被一般 defect table 清掉」的反駁，實驗也修改了 acquisition path 的三個 table-enable call arguments：

- `0xC03183F4`: 第三參數改為 0；
- `0xC0318414`: 第三參數改為 0；
- `0xC0318434`: 第三參數改為 0。

保存的 `DEFORIG.BIN`／`DEFPOST.BIN` 證實三處 authoritative code 與 patch readback。這不是永久刷機，只是 executable RAM patch。

## 4. 實機實驗時間線

### 4.1 一般 DNG：FFT 與規律殘差搜尋

先用正常 DNG 搜尋固定週期弱點、條紋或遮罩點。結果沒有清楚的 PDAF lattice。

此輪不能下結論，因為 DNG 可能已經經過：

- sensor-side correction；
- acquisition／ISP defect correction；
- CPU `PdafCorrect`；
- StillCreateRaw 的 Bayer conversion；
- DNG encoding 前的色平面處理。

所以它只建立 baseline，沒有排除相位像素。

### 4.2 關閉 `PdafCorrect` 再拍 DNG

AutoRun：`autorun_previous_pdaf_bypass.txt`。

步驟：

1. 保存 `0xC030FB20` 前 16 bytes 到 `PDPRE.BIN`；
2. 將入口改成 `BX LR`；
3. 回讀到 `PDPST.BIN`；
4. 寫入 `PDBYP.BIN` marker；
5. 拍攝 DNG，比較正常／bypass 組。

卡上證據：

- `PDPRE.BIN` 以 `f0 4d 2d e9` 開頭，即 `0xE92D4DF0`；
- `PDPST.BIN` 以 `1e ff 2f e1` 開頭，即 `BX LR`；
- `PDBYP.BIN` 同時保存原始／patch word。

結果：沒有因 bypass 而出現規律 phase-pixel pattern。這降低「CPU PdafCorrect 正在抹除」的可能性，但仍可能是 PdafCorrect 原本在此 mode 就沒做事，或更早的 stage 已經清除。

### 4.3 對焦距離控制與鏡頭問題

曾嘗試以不同對焦距離比較，因 PDAF marginal correction 可能隨焦距或鏡頭狀態改變。實驗遇到一個重要限制：原鏡頭關機時對焦位置會歸零，而 AutoRun 只在機身第一次插卡／開機時執行，難以保證兩組 capture 的光學狀態完全相同。

之後改用手動對焦方式，約設在 1 m，再拍兩組。影像外觀可以略有差異，但沒有形成固定 sensor-coordinate lattice。因場景、對焦面及微小移動不完全受控，這部分只能算輔助觀察，不能單獨證實或否定 PDAF。

### 4.4 直接定位 Still RAW buffer

AutoRun：`autorun_card_probe_used.txt`／`autorun_pre_stillraw_probe.txt`。

研究目的：找出完成 DMA 的 Bayer buffer，而不是再分析 DNG。

在 normal single-frame path 的 `AcqEndTrans` 周圍建立 ARM wrapper：

- 保留原呼叫；
- 從 request `+0x30` 取 RAW pointer；
- 記錄 request pointer、sensor mode、bit type、frame count；
- 以 `0xDEADBEEF` 作未命中 sentinel；
- 最後才 patch callsite `0xC0315DD4`，避免半安裝狀態被執行。

`PREPROBE.BIN` 的結果解析為：

- RAW pointer：`0x5F900C00`；
- request pointer：`0xC343940C`；
- sensor mode：0；
- bit type：1（RAW14）；
- frame count：1；
- marker：`PRB1`。

這證明 hook 命中真正的單張靜態 RAW acquisition，而不是猜測一段影像狀記憶體。

### 4.5 在 `StillCreateRaw` 前凍結 capture task

AutoRun：`autorun_pre_stillraw_hold_dump.txt`。

wrapper 先呼叫原始 `AcqEndTrans`，記錄 metadata，然後以 100 ms interval 等待 release flag。AutoRun task 與 capture task 分離，因此 capture task 被 hold 時，AutoRun 仍可把 RAW buffer 寫到 SD。

同時採取兩層 bypass：

- acquisition path 的 WDD／BDD table-enable argument 設為 0；
- `PdafCorrect @ 0xC030FB20` 設成 `BX LR`。

成功輪的 `HOLDMETA000.BIN`／`HOLDEND000.BIN` 顯示：

- raw pointer `0x5F900C00`；
- hold entered = 1；
- dump 時 release = 0；
- mode = 0；
- bit type = 1；
- frame count = 1；
- 之後 release 變為 1，正常 DNG processing 繼續。

輸出：

- `PRESHOT000.BIN`：48 MiB pre-StillCreateRaw memory；
- `_SDI0042.DNG`：同一曝光正常完成的 DNG；
- `HOLDMETA000.BIN`、`HOLDEND000.BIN`：時序證據。

早一輪的 `PRESHOT.BIN` 對應 metadata 仍是 sentinel，表示沒有在正確拍攝窗口命中，不應當作有效影像證據。報告分析使用的是成功輪 `PRESHOT000.BIN`。

### 4.6 RAW14 layout 反解

從 pre-Still buffer 與 DNG 對齊得到：

- raster：6064×4042；
- bit depth：14；
- packed：每 4 pixels = 7 bytes；
- ordering：MSB-first，連續 14-bit field；
- row bytes：`6064 × 14 / 8 = 10612`；
- 無額外 per-line padding。

第一組 7 bytes 解出 `1195, 1411, 1212, 1413`，與 DNG 對應像素一致。全 frame 與 DNG raw plane 的 correlation 為 `0.99998646`，證明 packing、offset 和 frame identity 均正確。

比較結果：

- 兩個 green CFA plane pixel-for-pixel 相同；
- red／blue 有小幅、廣域、依亮度／空間而變的差值；
- R/B 差異影響大多數該色像素，而不是少數固定座標。

因此這些差異更像 broad color-plane processing，不像 PDAF masked sites 的 sparse interpolation。

### 4.7 pre-Still RAW 的週期圖樣搜尋

為避免單純 FFT 被場景紋理掩蓋，另建立 same-colour local predictor，使用 CFA 同色、對稱 offset 2 與 4 的鄰點預測，再分析 residual。

對四個 CFA phase 分開，依 `(y mod P, x mod P)` 聚合。測試週期：

`4, 8, 12, 16, 20, 24, 28, 32, 40, 46, 48, 64, 92, 128`

結果：

- local residual MAD 約 8–12 DN，依 CFA plane 而異；
- period ≤64 時，最強 residue-cell median displacement 僅 0–1 DN；
- period 92／128 時最大約 1–2 DN；
- 沒有 coherent repeated mask，也沒有一組座標在不同局部持續表現為單側遮罩／插值殘差。

若正常 readout 中存在足以計算相位差的規律 masked pair，預期至少會在正確 CFA phase、固定 stride／line interval 上留下超過局部雜訊的重複殘差。此資料未出現。

### 4.8 IMX410 runtime object 與 70 組 mode table

唯讀 AutoRun：`probe_embedded_runtime_AutoRun.txt`。

保存：

- `IMXOBJ00.BIN`：`0xC343B500`, 4 KiB；
- `IMXCFG00.BIN`：`0xC2F1E000`, 4 KiB；
- `IMXTBL00.BIN`：`0xC0B5F800`, 48 KiB，涵蓋 IMX410 static configuration 與 70 個 register modes。

目標是尋找：

- embedded-data enable；
- PDAF statistics／phase channel enable；
-額外 virtual channel／packet datatype；
- 正常 mode 未啟用但可切換的 sensor output。

靜態表中沒有找到一條可以有把握標成「IMX410 PDAF payload」的現成 alternate mode。這不等於所有未具名 register 都已理解，但沒有足夠證據安全地開啟某一 bit。

### 4.9 SLVS-EC receiver／assembler 唯讀探針

保存區域：

- `0x300E1000`：SLVS-EC PHY／protocol receiver；
- `0x30100000`：sensor timing、line/frame assembler、protocol status／link control。

檔案：`SLVPHY00.BIN`、`SLVPHY01.BIN`、`SLVASM00.BIN`、`SLVSTL00.BIN`、`PKPHY*`、`PKASM*`。

先比較 idle baseline 與 still frame 完成、且 `StillCreateRaw` 被 hold 時的狀態。`PKMETA.BIN` 證明 capture hook 命中。這些 snapshot 顯示 receiver 在不同模式有 raster／frame 狀態變化，但沒有辨識出獨立的 phase payload buffer、第二 virtual channel 或可直接讀出的 embedded PDAF block。

限制是 MMIO snapshot 只能看到當下寄存器；若 embedded lines 在 frame start 短暫出現並被硬體丟棄，frame 完成後讀取可能看不到。因此後續才嘗試改 source window。

### 4.10 將 source window 往上移：找正常影像上方的隱藏行

假設 sensor 輸出包含不進入正常 4042-line Bayer 的 top embedded lines，assembler 可能以 source window `[40, 4082]` 裁掉前 40 行。因此建立兩個實驗：

- `top1`：`[40,4082] → [39,4081]`，上移 1 行；
- `top40`：`[40,4082] → [0,4042]`，上移 40 行。

在 `AcqStartExp` 前寫 receiver register `0x30100024`，並保留 post-DMA hold hook，計畫保存 top RAW 與 assembler state。

這兩條 active receiver modification 路線造成相機卡住，沒有形成可採信的 top-line RAW 輸出，之後停用並保存為 `AutoRun.disabled.top1.txt`／`AutoRun.disabled.top40.txt`。

卡機本身不能證明上方有 phase data。更可能的原因包括：

- source window 與 DMA stride／height descriptor 不一致；
- frame boundary／CRC／line count 不符合；
- 寫入值對 register bitfield 的解讀不完整；
- receiver 必須在更早初始化階段成組更新，而不能在 AcqStartExp 單點改寫。

所以這輪結論只能是「此修改方法不安全／不可用」，不能把 hang 當作 embedded PDAF 的正證據。

### 4.11 其他 embedded／alternate-output 嘗試

我們也沿著「開另一種 PDAF／embedded-data 輸出模式」研究 IMX410 mode table 與 SLVS-EC packet state。風險評估後先做唯讀 dump，再嘗試最小變更。部分 active probes 出現卡機，均以拔電池、冷開機恢復；沒有寫 PROM 或永久 firmware。

截至目前，未找到同時滿足以下條件的 mode：

- 在 fp 的 IMX410 table 中可達；
- receiver descriptor 能接受；
- 產生額外可定位 payload；
- 不破壞 frame／DMA pipeline；
- payload 隨對焦距離或左右視差呈相位特徵。

## 5. 關於「多出來的像素」與 6000×4000

### 5.1 6064×4042 不代表多出的都是相位像素

有效 RAW acquisition 為 6064×4042，而成品照片約 6000×4000。外圍差值可包含：

- optical black／dark reference；
- active margin；
- Bayer phase／裁切對齊；
- lens shading、distortion、demosaic 所需邊界；
- sensor readout／DMA alignment。

僅憑「比照片多 64×42」不能認定是 PDAF。實際 pre-Still analysis 沒顯示這些區域形成另一份 phase channel。

### 5.2 有相位遮罩為何仍能輸出完整解析度

其他相機即使有 masked phase pixels，也常在固定點以鄰近同色像素插值，最後仍輸出名義上的完整 6000×4000 raster；「完整尺寸」本身不能反證 PDAF。

真正有判別力的是：在 correction 前是否能看到固定 sensor-coordinate 的弱點／左右 mask pair，以及 firmware 是否持有該 sensor 的 geometry。fp 的 pre-Still frame與 IMX410 subclass 均沒有提供這項正證據。

## 6. 哪些曾經的判斷需要撤回或降級

### 6.1 應撤回

「IMX410 確實帶遮罩相位像素，而且 fp 韌體正在 RAW buffer 上用 PdafCorrect 抹掉」不能作為已證實結論。

原因：

- sensor family 類比不是 fp 個體證據；
- PdafCorrect 是共用 framework；
- IMX410 的 geometry slot 為空；
- bypass 後沒有圖樣；
- correction 前 Bayer 也沒有圖樣。

### 6.2 仍成立

- fp 韌體含完整 PDAF 共用程式；
- fp 的 autofocus PDAF route 被 capability gate 關閉；
- `PdafCorrect` 與 shell control 真實存在；
- fp L／IMX455 路徑可提供 PDAF geometry；
- fp 的 sensor DMA RAW 可以在 StillCreateRaw 前抓取；
- 正常 fp still readout 中沒有可辨識、可利用的 phase lattice。

### 6.3 尚未證明

- fp 的 IMX410 晶圓物理上完全沒有任何遮罩／分光結構；
- Sony 是否在 sensor 內部先校正再輸出；
- 是否存在未列入 70 組正常 mode table、需要 undocumented register sequence 才能輸出的 factory mode；
- SLVS-EC 是否曾傳送極短命的 embedded metadata，後來被 receiver 丟棄。

這些都屬於「理論上未封死」，但目前沒有工程上可用的入口。

## 7. 為何現有資料不能拿來提高 ISO

曾提出「如果被清除的那些像素能拿回，是否可增加有效感光／提高 ISO」。即使真有遮罩 PDAF pixel，也不會直接提高整體 ISO：

- 遮罩像素收到的光通常更少，SNR 較差；
- 數量只占總像素的一小部分；
- 它們的主要價值是左右瞳孔視差，不是額外曝光面積；
- 把它們當一般亮度樣本，往往需要增益與校正，反而增加固定圖樣噪聲。

而目前抓到的 pre-Still RAW 沒有一組被 CPU 清除前的相位樣本可回收。因此這條路不構成 fp 擴展 ISO／動態範圍的方法。

## 8. 風險、失敗模式與安全處理

實驗均使用 RAM-only patch，沒有覆寫 firmware flash／PROM。冷開機可恢復 authoritative code。採取的基本安全措施包括：

- patch 前保存原始指令；
- 將 hook callsite 最後才寫入；
- 使用 marker 與 readback 檔確認 patch 是否完成；
- capture task hold 後由 AutoRun task釋放；
- 遇到 hang 拔電池，不在卡機狀態繼續寫 register；
- 對不確定的 sensor／receiver register 先做 read-only dump。

觀察到的主要失敗：

- 使用者沒有在 AutoRun capture window 內拍照，metadata 保持 sentinel；
- 電子鏡頭重開機歸零，妨礙嚴格的 focus-distance A/B；
- 更改 source window／embedded receiver configuration 後卡機；
- 大型 `mem save` 與 capture task 時序容易錯開；
- AutoRun 只在機身特定首次插卡／開機時執行，使分段測試操作複雜。

這些失敗已在後續版本以手動鏡頭、明確彩條 cue、hold/release flag、metadata sentinel 和 disabled script archive 處理。

## 9. 證據檔案索引

主要原始資料保存在：

`card_backups/NIKON_D80_preformat_2026-08-17/`

關鍵檔案：

| 檔案 | 用途 |
|---|---|
| `PDPRE.BIN` / `PDPST.BIN` | PdafCorrect bypass 前後 readback |
| `PDBYP.BIN` | 原始及替換指令 marker |
| `DEFORIG.BIN` / `DEFPOST.BIN` | WDD/BDD call arguments patch 證據 |
| `PREPROBE.BIN` | RAW pointer、mode、bit type、frame count |
| `HOLDMETA000.BIN` / `HOLDEND000.BIN` | StillCreateRaw 前 hold／release 成功證據 |
| `PRESHOT000.BIN` | 48 MiB pre-StillCreateRaw memory dump |
| `DCIM/100SIGMA/_SDI0042.DNG` | 對應完成後 DNG |
| `IMXOBJ00.BIN` / `IMXCFG00.BIN` | IMX410 runtime object／configuration |
| `IMXTBL00.BIN` | IMX410 static configuration 與 70 modes |
| `SLVPHY00.BIN` / `SLVPHY01.BIN` | SLVS-EC PHY snapshots |
| `SLVASM00.BIN` / `SLVSTL00.BIN` | assembler idle／still snapshots |
| `PKPHY*.BIN` / `PKASM*.BIN` / `PKMETA.BIN` | packet-state comparison 與 hook metadata |
| `AutoRun.disabled.top1.txt` | 上移一行、造成 hang 的停用探針 |
| `AutoRun.disabled.top40.txt` | 上移 40 行、造成 hang 的停用探針 |

分析摘要另見 `PDAF_RAW_PATTERN_ANALYSIS_2026-08-17.md`。

## 10. 若未來仍要追，唯一有意義的方向

繼續從 DNG、StillCreateRaw、CPU PdafCorrect 往後找，邊際價值已很低。若要把「晶圓有但 sensor 內部隱藏」查到底，只剩更底層且成本更高的方向：

1. 取得可靠的 IMX410 register documentation，逐一識別 70 組 mode table 中的 embedded／VC／data-type controls；
2. 在不改 raster window 的前提下，以邏輯分析儀或 FPGA 直接觀察 SLVS-EC link；
3. 在 frame start／line IRQ 即時 trace packet headers，而不是 frame 完成後 snapshot；
4. 找到同 pinout、同 package、已知 PDAF-enabled 的 IMX410 variant 做 register table diff；
5. 顯微鏡／光學 pupil-mask 實驗，從物理層直接確認固定像素的方向性響應。

在沒有 datasheet、link capture 或對照 sensor 的情況下，再盲寫 receiver／sensor register，風險高而資訊增益低，不建議作為目前主線。

## 11. 一句話總結

我們已經從「DNG 看不到」一路往前追到「DMA 完成、StillCreateRaw 尚未開始」的正確 RAW14 Bayer，並同時 bypass CPU PDAF correction 與一般 defect-table 入口；仍然沒有看到相位像素 lattice，而韌體 dispatch 又顯示 IMX410 的 PDAF geometry implementation 為空。故 fp 可用相位資料的機會，在目前軟硬體邊界內應視為沒有。
