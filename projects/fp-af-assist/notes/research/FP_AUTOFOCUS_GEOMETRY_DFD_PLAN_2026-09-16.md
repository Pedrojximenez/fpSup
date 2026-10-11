# fpFocus：幾何估距 + DFD + CDAF 的自動對焦改進方案

日期：2026-09-16  
對象：SIGMA fp Ver.5.02  
狀態：四輪六點原生掃焦曲線與峰值重建已驗證；H/L 方向歧義、增益處理與驅動 gate 更正已完成；閉環與 DFD 尚未驗證

## 0. 依新目錄規則的歸屬

這份工作的核心是「fp 本身有哪些 AF 訊號、如何把它們結合」，即使日後換掉產品介面仍然成立，
所以放在：

```text
research/autofocus/notes/       結論、架構、實驗結果
research/autofocus/captures/    每次實測的 telemetry、曲線、影像與量測素材
research/autofocus/<散檔>       取得上述證據的 collector、replay、probe、AutoRun
```

只有當它成為一個有明確交付邊界的實作時，才新增 `projects/<project>/`；驗證完成、要給使用者使用的
程式才進 `fpSup/focus/`。舊 `sigma-fp-bridge/focus-ai` 是一個已停止的專案，原始程式保持在它自己的
repo；本筆記只抽取其中可以跨專案沿用的相機事實、量測與方法。

## 1. 結論

**目前最合理的路線不是讓 fp 模仿 PDAF，而是把三個各有缺口的訊號疊起來：**

1. **幾何估距**給出主體往哪裡走、粗略應到哪個焦點位置。
2. **DFD／焦點曲線**在移動途中用 Bayer-green AF 統計修正粗估，求局部峰位。
3. **原廠 CDAF 的高／低頻帶與峰值規則**負責最後收斂、可信度與失敗退場。

這樣不需要相位遮罩，也不必從單張影像硬猜前焦或後焦。幾何先提供正負方向，鏡頭本來就要做的
那次移動同時成為 DFD 採樣；若沿路已包住峰值，只需零次或一次小修正，不必可見地來回 hunting。

舊 `focus-ai` 的最新本地量測也修正了一個過時印象：**幾何法不是必然很弱。** 在乾淨、同主體、
同鏡頭的四組校正資料上，線性模型留一驗證中位誤差 35、最壞 53 個鏡頭位置單位；當次局部景深
半寬約 145，也就是中位 0.2、最壞 0.4 個景深。較早資料曾差六倍，說明主要風險是校正真值、
座標正規化與主體一致性，不是投影幾何本身。

## 2. 證據標記

- **[F]**：fp 韌體靜態分析已確認。
- **[M]**：舊 `focus-ai` 實測或可離線重播的量測；仍受當時鏡頭與相機設定限制。
- **[P]**：本方案的工程推論。
- **[V]**：必須用目前的 fp／USB shell 路線重新上機驗證。

## 3. 已經具備的三組輸入

### 3.1 幾何與主體追蹤

**[F]** fp 內部已有固定座標的 face／eye 結果：

- `DetectionResultMgr = 0xC37CCA9C`
- 最多五張臉；每組 `0x9C` bytes
- face 子記錄的 `x/y/w/h` 在 `+0x10/+0x14/+0x18/+0x1C`
- 座標域固定為 `320×213`
- AF-facing rect 在 manager `+0x3E0...+0x3EC`
- tracking mode 在 `+0x3D0`
- AAT 當前框 `0xC3033E00`，confidence `0xC3033E26`

這條內部路線比舊主機 Vision 更適合幾何估距：不會因錄影時 Live View 從 1620×911 變成
640×360，就把主體尺寸誤讀為縮小三倍。若仍用外部偵測器，所有尺寸必須先化成 `w / frame_width`
或統一到校正時的參考寬度，不能保存原始像素數。

**[M]** 舊 `focus-ai` 的有效幾何模型是兩層：

```text
p = a d² + b d + c          p = 鏡頭位置，d = 1 / 距離（屈光度）
s = k d                     s = 主體在畫面中的大小，k = 主體尺度
```

代入後也能直接學：

```text
p = A s² + B s + C
```

整體距離尺度即使未知也會被 `k` 吸收；真正重要的是曲線形狀。配對只能由 DFD／CDAF 確認過的峰位
產生，不能拿「當時下令的位置」自我訓練。

### 3.2 Bayer-green AF 統計

**[F]** fp 的 SIG 硬體在 debayer 前對 Bayer 綠通道計算逐 ROI 的雙頻帶高頻能量：

| 訊號 | 位址 | 用途 |
|---|---:|---|
| `saf_jdat_h[]` | `0xC32985E8` | 近峰時的細銳度 |
| `saf_jdat_l[]` | `0xC32986B4` | 嚴重失焦時仍有反應的粗銳度 |
| `mposm[]` | `0xC3291958` | 曝光時刻對應的鏡頭位置，DFD x 軸 |
| H/L area index | `0xC3291534` | 選 `saf_jdat_h/l[]` 的 AF 區域；有效範圍 0–50 |
| `mposm[]` sample index | `0xC329153C` | strategy-dependent：Fast 可為已完成索引；Near 可指向尚未填寫的下一格 |
| aggregate bands（舊 JSON 名稱 peak_now/max/min） | `0xC32915C4/C8/CC` | small H / main H / small L；D0 是 main L，不是極值狀態 |
| `g_afpos` | `0xC32914E0` | AF 位置／目標域 |

這比舊 `focus-ai` 的縮小 MJPEG + Tenengrad 更乾淨，也避開「鏡頭移動中 PTP 回報的是命令位置」
的混淆。真正要驗的是 `mposm` 在我們自己的 drive 路徑、錄影中與各 sensor mode 下是否仍準確對齊
曝光時刻。

**[F/M] 2026-09-16 索引更正：** `0xC3291534` 只選 H/L 的 AF 區域；不能拿它索引
`mposm[]`。`AfMgrProcessFast::v5 @ 0xC025CD30` 把當次 exposure-centre 位置寫到
`0xC3291958 + 4*uVar9`，再把同一個 `uVar9` 寫到 `0xC329153C`。因此 collector 分別讀
area index 與 sweep-sample index，並在資料收集後重讀兩者；任一索引在 snapshot 中途改變，該筆
`snapshot_coherent=false`。但 **Near::v6 會先發布下一格索引**，所以穩定索引仍可能讀到尚未填好的
位置，且 idle 時歷史不更新。`usable_for_dfd` 保留 null，不能只靠完整度自動批准擬合。

**[M] 第一組可靠位置／銳度配對已取得：** 原廠 AF 完成後讀取歷史 H/L 與 mposm，再核對
Near 的 `n=6,d=1,completion=1` 和 descriptor `count=6`，得到六個同索引樣本。H 峰附近三點
重算頂點約 10013，與原廠保存的頂點相符。即時欄位的跨策略配對仍待修正，詳見
[原廠 AF 實測紀錄](FP_ORIGINAL_AF_TRIAL_2026-09-16.md)。

### 3.3 鏡頭位置、距離與驅動

**[F]** 韌體和鏡頭資料已提供：

- 單一絕對 focus-position domain
- 位置與 `1 / distance` 的分段線性支撐點
- 每顆鏡頭的 `DefocusPerPulse` 資料／相關換算路徑
- focus min/max、目前位置與候選絕對／相對驅動入口

因此新系統不必永遠靠主體走四個站點重學鏡頭。SIGMA 鏡頭可先嘗試讀原廠表；沒有相同 DFD block
的 LUMIX／其他鏡頭，再退回離線 characterisation。

**[V]** 最大的控制阻塞仍是錄影中驅動。PTP handler 會在 capture-state 非 idle 時拒絕；要先證明一條
內部 drive 路徑能在錄影期間安全完成一次受限位移，才可以做 movie AF 閉環。

## 4. 舊幾何方案中應直接保留的部分

來源：本機 `sigma-fp-bridge/focus-ai`，commit
`1bca1b9c805974c0d9fa887bd9eda9eb87b7a237`（2026-08-26）。

### 4.1 保留：倒數尺寸上的運動預測

對固定實際大小的主體：

```text
s ∝ 1 / Z
1 / s ∝ Z
```

主體若沿光軸近似等速，`1 / s` 對時間近似直線。應在這個座標做速度擬合與前瞻，再經鏡頭曲線
換成位置；不要直接在非線性的 focus-position domain 外推。

舊主機端前瞻模型是：

```text
lead_time = image_age + motor_dead_time + travel / motor_speed
```

其中 28mm F1.4 Art 舊量測約為 image age 0.14 s、dead time 0.06 s、22,000 units/s。
**[V] 這些數字不可直接搬到機身內迴圈**；內部 detector、telemetry 與 drive 的延遲都不同，必須重測。

### 4.2 保留：只用被光學確認的樣本學習

幾何模型的 `(size, position)` 配對只接受：

- DFD 擬合有低殘差，而且峰在實際採樣區間內；或
- CDAF 確認已進入峰頂平台；或
- 完整校正掃描的雙向峰位一致。

絕不使用 commanded position、未到位位置或幾何自己的輸出回訓。這會避免模型把控制誤差當真值。

### 4.3 保留：模型複雜度由跨度決定

舊量測顯示，四點且尺寸跨度只有 1.4× 時，二次式會嚴重過擬合；7.1×、五個屈光度錨點時二次式
才明顯勝過線性。初版規則應為：

- 少於五個可靠點，或尺寸跨度不足 5×：只擬線性。
- 有至少五點且跨度足夠：才開二次項。
- 每次都做 leave-one-out／held-out 驗證，不報樣本內 RMS 當準度。

### 4.4 保留：主體線索可以平順換手

舊量測的 `body_width / face_width ≈ 2.85`，散布約 3.9%；臉消失時人體框可以維持幾何方向。
換線索時不能直接切換，應用兩者共同可見期間估得的比例對齊，再以數秒時間常數慢慢回到長期平均。

## 5. 舊方案中不應直接搬用的部分

1. **不使用原始 pixel width。** 一律固定在內部 320×213 domain，或用正規化尺寸。
2. **不把眼距當更準的距離尺。** 舊量測顯示眼距雜訊與覆蓋率沒有勝過臉寬；它只在臉框被裁掉時
   可能還存在。
3. **不直接做 `1/cos(yaw)` 修正。** 兩種線索都顯示這會過度修正；初版把 yaw 當 confidence gate，
   不當精確幾何補償。
4. **不從單張失焦影像判正負方向。** 28mm、45mm 上的軸向色差、球差與像散都沒有提供可靠符號。
5. **不把高／低頻帶比值直接當峰。** 遠離合焦時會受雜訊底影響；應擬合局部曲線並檢查殘差。
6. **不相信移動中的一般位置回讀。** 舊 PTP 路徑回報命令位置；新路線優先用 exposure-aligned
   `mposm`，並另做 drive-end 真位置核對。

## 6. 融合迴圈

### 6.1 正常追蹤

```text
face / eye / subject ROI
        ↓
正規化幾何 s(t) ──→ 在 1/s domain 估速度與未來位置
        ↓
鏡頭曲線換成 coarse target + 明確方向
        ↓
單向受控移動；沿路同步收集 {t, mposm, H, L, AE, ROI}
        ↓
三點以上局部 DFD 擬合／平台停止判斷
        ↓
0 或 1 次細修正 → CDAF 指標確認 → 更新可信模型
```

這裡最重要的設計是：**幾何移動本身就是 DFD 掃描。** 不另外做一次可見 hunting。

### 6.2 DFD 擬合

兩個位置的銳度比可以消掉場景本身的對比尺度，但可能有鏡像解；初版至少用三個 exposure-aligned
樣本。擬合時：

- 高、低頻帶分開保留，不先壓成一個 ratio。
- 對數域消掉乘法尺度，或顯式擬合 amplitude／floor。
- 峰位必須落在已採樣區間內；禁止外插峰。
- 用 fit residual、兩頻帶一致性、峰是否被 bracket、ROI confidence 產生 DFD confidence。
- 曲線寬度按鏡頭、焦距、光圈與 focus domain 分桶；不直接沿用 HDMI YUV 的 Lorentzian 寬度。

### 6.3 控制規則

| 幾何 confidence | DFD confidence | 行為 |
|---|---|---|
| 高 | 高 | 直達擬合峰；近峰減速；最多一次小修正 |
| 高 | 低 | 依幾何方向慢移並收集更多點；不得反向亂找 |
| 低 | 高 | 沿已知曲線到峰；暫停模型學習 |
| 低 | 低 | 保持原位；等主體恢復，或在使用者允許時才掃描 |

近峰時可以測試「局部景深 10–15%」的不可見 wobble，作為長時間鎖定的正負梯度觀察器。
舊離線量測顯示 1–4 幀可能達到 3σ，但它在動態主體、錄影、現行驅動路徑下尚未驗證，所以不是
第一版必要條件。

## 7. 第一版 telemetry schema

每個 AF evaluation frame 至少記錄：

```text
t_camera, t_host
sensor_mode, fps, recording
roi_id, track_id, roi_x, roi_y, roi_w, roi_h, roi_confidence
face_w_norm, body_w_norm, cue_source
saf_h, saf_l, peak_now, peak_max, peak_min
mposm, drive_target, drive_state, drive_direction
gain, shutter, f_number
geometry_target, geometry_confidence
dfd_peak, dfd_residual, dfd_confidence
commanded_target, command_time, drive_end_time
```

素材按 session 放在：

```text
research/autofocus/captures/af-fusion/<YYYY-MM-DD-session>/
```

收集器與 replay 是取得這些證據的工具，依新規則直接放在 `research/autofocus/`，不要塞進 `notes/`。

## 8. 實驗順序與通過條件

### A. 離線統一舊資料

1. 讓舊 `focus-ai` replay 輸出上述 schema 的可得子集。
2. 把幾何模型改成正規化尺寸／固定 320 domain。
3. 比較 geometry-only、DFD-only、fusion 三條路，不只看位置誤差，也看反向次數與總行程。

### B. 非錄影靜態主體

1. 先釘住 ROI index、`mposm` 對齊與 H/L 更新 cadence。
2. 同一顆鏡頭至少取遠／中／近、兩個光圈；每點雙向低速掃描取得真峰。
3. 留出部分位置完全不參與建模，驗證 geometry coarse target 與 DFD peak。

初版驗收：

- held-out 中位峰位誤差 ≤ 0.5 個局部景深；95th ≤ 1.0 個景深。
- geometry 有效時，可見反向搜尋次數為 0；允許最後一次小修正。
- 所有模型更新都能追溯到一個被 bracket 的峰或明確 CDAF 平台。

### C. 移動人物

用同一次動作交錯 A/B：geometry-only、原廠 AF-C、fusion。記錄：

- time-to-platform
- 影格落在 ±0.5／±1.0 局部景深內的比例
- 最大連續失焦時間
- 鏡頭總行程、反向次數與可見 pumping 次數
- 主體轉頭、遮擋、換人與重新出畫的恢復時間

### D. 錄影中閉環

只有在「一次受限位移不毀錄影、不破壞檔案、可可靠讀到 drive end」通過後才開始。先跑低速、單人、
小範圍；任何 capture-state、buffer、寫檔或 USB 異常都歸到實際承載控制路徑的 project，而不是寫回
一般 AF 事實。

## 9. 最近的五個可執行里程碑

1. **採集已實測，光學／逐點曝光對齊待驗。** DMA-copy AF-fusion collector 已完成四輪原廠 AF；
   完成 Near history 可重算原廠峰位，即時 `mposm` 仍不可任意配對。
2. 釘住 ROI index 和 `mposm` 的 exposure alignment，包含鏡頭移動中與錄影中。
3. 用一顆鏡頭完成五個以上跨度足夠的 focus-position／sharpness 曲線，保留 held-out 點。
4. 把舊幾何模型接上新 telemetry，先離線證明 geometry target 能把 DFD 搜尋窗縮小。
5. 在非錄影 Live View 完成「幾何單向移動 → 沿路 DFD → 一次修正」閉環，再處理錄影 drive gate。

### 9.1 第一個里程碑的落地狀態（2026-09-16）

新增三個研究工具，依目錄規則放在 `research/autofocus/` 根目錄：

- `af_fusion_snapshot.S`：暫借現代 USB shell 的 `echo` handler；只讀固定狀態與 monotonic tick，
  在機內生成一筆 208-byte `AFF1` record，再由現有 EP0x82 reply 送回。不使用已退役的 EP0x84，
  不呼叫 focus drive 或 exposure setter。
- `af_fusion_collector.py`：驗證／裝載／finally 嘗試並核對還原 handler（斷線等仍可使清理失敗），按 session 同時保存 `samples.bin`、
  `samples.jsonl`、`manifest.json`；也能離線 decode 與產生 mock fixture。
- `test_af_fusion_collector.py`：覆蓋 framing、sequence complement、索引穩定性、320×213 正規化、
  gain 解碼與 truncated-tail 拒收。

記錄包含 snapshot 前後的 area/sweep index、camera tick 前後值與 host request 前後時間。只有 record
完整、兩個 index 都在範圍內且前後未變，才標為 `snapshot_coherent=true`。這能拒絕 collector 剛好
跨過 AF evaluation 更新邊界的樣本；它不宣稱 USB request 與 sensor frame 同步，也不會僅憑
snapshot coherence 宣稱樣本可用於 DFD。

舊 `projects/usb-shell-sup/fpshell_tool/monitor` 的 telemetry V2 不可當此工具的前身：

1. 它固定讀 H/L 第 0 格，忽略 `0xC3291534` area index。
2. 它完全沒有收 `mposm`，也沒有區分 `0xC329153C` sweep-sample index。
3. 它把四個 32-bit consolidated face rect 欄位當成連續 16-bit 數字，會錯讀 x/y/w/h。
4. 它把 `G+0x2C` 直接命名為 analog gain 並除以 65,536；首輪 live mapping 顯示這個欄位連
   analog-gain 身分都尚未釘住。
5. 相機端推送走已不存在的 EP0x84 / physical endpoint 9；第一次啟用已有 worker 死亡紀錄。

新 collector 不修改那份歷史程式，也不碰 `fpSup/` 的未完成工作樹。離線狀態已確認：8 個 unit
tests 通過；當時的 ARM handler 成功組譯為 944 bytes，放在 shell 保留的
`0xC072FC00–0xC0730000` 1 KiB 工作格。當時主機沒有 `/tmp/fpshd.sock`，因此尚無真機 capture，
也不能把 address semantics 或 20 Hz cadence 標成 live-validated。

第一輪實機命令（不驅動鏡頭）：

```sh
python3 research/autofocus/af_fusion_collector.py inspect
python3 research/autofocus/af_fusion_collector.py collect --duration 10 --hz 20
```

`inspect` 只組譯、不碰相機；`collect` 預設寫到
`research/autofocus/captures/af-fusion/<timestamp>/`。第一輪要在 idle Live View 依序改 AF area、開／關
face detect、改 ISO，再只觀察值是否同步；這一輪仍不要移動鏡頭。通過後才做低速單向 sweep，驗證
`mposm` 和 H/L 的曝光對齊。

### 9.2 第一輪 fp 實機 baseline（2026-09-16 03:25 +08:00）

Capture：`captures/af-fusion/2026-09-16-032506/`。相機在 idle Live View、沒有送 focus drive：

- 10 秒／20 Hz，保存 199 筆；199/199 framing 與兩組 index 前後值都一致。
- 2 次 USB reply 無效、1 個 camera sequence gap、0 duplicate；有效率約 99.5%。
- camera tick 的相鄰平均 50,264 µs，對應 19.90 Hz；snapshot 本體 4–376 µs。
- USB round trip 0.387–6.717 ms。
- 結束後 `ping` 正常，`echo` slot 已復原為 `0xC03D99A0`。
- H/L 持續微幅更新（H 54,517–54,702；L 109,660–109,958），area index 固定 0。
- sweep-sample index 固定 3、`mposm[3]` 固定 9,622；同時 `mposm[0]=9,946`、
  `g_afpos=9,741`。這證明 idle 時 `mposm[]` 是上次 sweep 的歷史，不是每幀「目前鏡頭位置」。

因此 JSON schema 升為 v2：`indices_stable` 只代表 snapshot coherent；`usable_for_dfd` 改為 `null`，必須由
session analyser 證明 sweep index／位置確實隨受控移動產生新點後才能決定。舊 baseline JSONL 保留原樣
作為生成當時的證據；`samples.bin` 才是可用新版 decoder 重新解釋的權威資料。

曝光也有一個靜態筆記更正。首輪 live raw dump 的 `0xC343A6A0..DF` 為：

```text
75 FFFFFFFF 0 0 FFFFFFFF 1 1 0 0 0 400 0 3F4D0 0 8 1
```

所以 `G+0x18=1` 不能直接標成 literal ISO，`G+0x2C=0` 也不能標成 analog-gain ×100；collector
現在只保存 `G+0x0C/+0x18/+0x2C/+0x34` raw。AF-side copies 同時是
`rgb_gain=117, sensitivity=236, shutter=8333, f_number=2164`，這組才是下一輪 ISO／快門／光圈 A/B
要比對的主要候選。capture-state raw 為 1 而 `MovieRecording=false`，故舊「capture-state 0=idle」也
不能直接套用到 Live View。

第一次 ISO 100 A/B capture 又找出一個純傳輸問題：daemon 會先交回上一個 handler lease 尚未消化的
raw reply，再交付新 session 從 sequence 0 開始的記錄。舊 collector 把 `200 → 0` 誤算成
4,294,967,096 個 sequence gaps，也把那筆舊 ISO 狀態混入新檔。schema v3 因此在 record `+0xCC`
加入每次安裝唯一的 session nonce；相機 handler 原樣保留，主機只接受 nonce 相符的 reply，並另計
`stale_session_replies`。sequence 的反向跳動也不再當成 32-bit 正向缺口。這只修正 host/session
歸屬，不改任何 AF 或曝光狀態。移除原本把 `+0xCC` 清零的兩條 ARM 指令後，新 handler 為
936 bytes，SHA-256 為 `a74dd63fb378ee22e5711023e5001259d26e4fb36158f780cde90115c442cab5`。

修正後的固定 ISO 100 baseline 為
`captures/af-fusion/2026-09-16-iso100-b/`：3 秒內收下 56 筆，56/56 snapshot coherent；一筆舊
session reply 被 nonce 正確拒收，沒有再污染資料或造成 32-bit 巨大 gap。有效 session 只有
`sensitivity=219, rgb_gain=117, shutter=8333, f_number=2164`；四個 G-region raw 仍為
`0, 1, 0, 0`。首輪自動／未釘住 ISO 的 `sensitivity=236` 不是受控對照，不能據此把 sensitivity
命名為 ISO；後續固定 ISO 800 對照已顯示它維持 219。此輪 sweep index 9、`mposm[9]=11068`
固定不動，仍是 idle 歷史，不能把 ISO 切換和先前發生的對焦 sweep 混為因果。

固定 ISO 800 capture 為 `captures/af-fusion/2026-09-16-iso800-a/`：同樣收下 56 筆且 56/56
snapshot coherent，一筆舊 session reply 被拒收。唯一穩定的曝光欄位差異是
`rgb_gain: 117 → 936`，恰為 ISO 比值 `800/100 = 8.000×`；`sensitivity=219`、
`shutter=8333`、`f_number=2164` 與四個 G-region raw `0,1,0,0` 全部不變。據此可把
`0xC32915B4` 從泛稱 raw 候選提升為「AF pipeline 的線性 ISO/gain scale」；目前兩點支持
`ISO ≈ rgb_gain × 100/117`，但 117 的定點基準、取整與跨 conversion-gain 區段行為仍需中間 ISO
及高 ISO 驗證，不能直接把 raw 117 命名成百分比或硬體 analog code。

同一構圖下 H 的中值約由 24.8k 增至 34.7k（約 1.40×），L 約由 57.9k 增至 79.1k（約
1.37×），沒有跟 ISO 一起放大 8 倍。這支持 H/L 已經過 AF 專用正規化／noise-floor／clamp 路徑，
而非直接的感光後像素振幅；因此 DFD 跨 ISO 時必須把 `rgb_gain` 納入校正，不能假設 contrast score
天然與 ISO 無關。這仍只是兩個 idle session 的差分，不是完整 response curve。

ISO 800 保持期間，原廠唯讀 `imager mode_now` 另釘住實際 AF/Live View sensor feed：mode 53
`MONIT1_60`、enum 8、2016×1344、12-bit、60 fps、3:2 full、`gain_state=through`，base/Bef 尺寸
同為 2016×1344。它回報 `gain=936`，與 `0xC32915B4` 完全相等，故後者不只與 ISO 成比例，還是
imager 當前使用的同一個 gain-domain 值。`mode_now` 的 sensor shutter 為 16663 µs，而 AF-side
`0xC329169C` 是 8333，約一半；所以 AF-side shutter 也不能直接當主 sensor exposure time，較可能是
AF 統計正規化／子週期使用的值。

一般 `i2c` shell 沒有註冊 imager device，無法透過該介面直接讀 `0x05E1`。原廠診斷命令
`imager check_convert_abs_gain` 以目前 `through` gain state 掃描，且實際套用每個測試 gain
（事後更正：並非唯讀，見 §9.4）：ISO 800 得 `analog=3317, digital=100, high=0`；
無參數 `high_gain_off` 會設定 normal，不能把其輸出當作原狀態查詢。掃描顯示 `high` 最後為 0 的
點是約 ISO 10939，第一個為 1 的點約 ISO 10949，故這台機身目前 MONIT1/through 的計算 HCG 門檻
落在這兩個已列印 ISO 值之間；它受當時 calibration、gain state 與強制 LCG 設定影響，並非 UI
所有模式共用的精確門檻。沒有直接讀 `0x05E1` latch；後續 v5 capture 另驗证了正確 IMX410 物件
在 ISO 12800 的 HCG RAM flag 為 1。

第一個 ISO 12800 telemetry session `2026-09-16-iso12800-a/` **不得用於曝光／AF 結論**：它只收下
一筆上一輪 ISO 800 的 sequence 60，接著把新 handler 的 sequence 0–55 全判為反向／out-of-order。
這揭露 daemon 的延遲 raw reply 保存的是 camera record pointer，而非已複製的 208-byte payload；v3
由主機直接把新 nonce 寫進 record，會把舊指標所指的舊 record 誤標成新 session。獨立執行的
`imager mode_now` 不受此問題影響，仍有效地顯示 ISO 12800 時 `gain=14976`。

schema v4 把 nonce seed 移到 record 外的 `0xC072F7D0`。主機只寫 seed，舊 record 保持舊 nonce；
只有新的 ARM handler 真正執行時，才把 seed 複製到回傳 record `+0xCC`。因此舊 pointer reply 會被
nonce mismatch 拒收，而新 sequence 0 可以成為第一筆。這次更正後必須重拍 ISO 12800；a session
只保留為 transport regression evidence。v4 handler 為 952 bytes，SHA-256
`846064940ea5ff91b9f80bd255b95b09338e707d9dd2bf0669ce0fecae2f5c58`。

重拍的 `2026-09-16-iso12800-b/` 證明 v4 transport 修正有效：60/60 筆、sequence 0–59 無缺口，
一筆舊 pointer reply 被 nonce mismatch 拒收。AF-side `rgb_gain=14976 = 117×128`，與獨立
`mode_now gain=14976` 完全一致；`sensitivity=219, af_shutter=8333, f_number=2164` 仍不變。
H 中值由 ISO 800 的 34711 降到 3671.5，L 由 79133 降到 9175。ISO 提高後 contrast 反而崩落，
可能是固定畫面高光 clipping 使紋理消失，也可能含 HCG/AF normalization 的不連續；沒有同步 RAW
histogram 時不能把這個下降單獨歸因於 HCG。

同時重新核對 getter 修正了一個更根本的靜態誤認：`FUN_c0312ee0` 確實返回
`0xC343A6A0`，但其 ctor `FUN_c0312e98` 只建立較小的 RGB/digital-gain helper；它不是
`XC_ImageSensorIMX410::v8` 的 `param_1`。真正的 IMX410 singleton 由 `FUN_c03255f8` 建於
`0xC343B588`，live `+0xD0` 也驗證為 vtable `0xC0B5FCC0`。ISO 12800 的前 0x40 bytes 為：

```text
C2F1E654 00000008 00000008 00000034 00000034 00000034 00003A80 00003A80
00000F00 00000F00 00000F00 00000646 00000064 00010101 000000C8 0000410F
```

因此真正可釘住的欄位是 `+0x18 relative_gain=14976`、`+0x20 applied analog code=0xF00`、
`+0x2C linear analog ratio=1606 (×100)`、`+0x30 overflow digital=100 (unity)`、`+0x34 HCG=1`、
`+0x38 inter-node trim=200`。舊 collector 所讀的 A6A0 `+0x34=0` 沒有 HCG 意義。

schema v5／binary record version 2 把四個 legacy slots 改讀正確 IMX410 物件的
relative gain、analog code、analog ratio 與 HCG。decoder 仍接受舊 binary version 1，但明確輸出
`legacy_gain_helper_raw`，絕不套用新語意。v5 handler 仍為 952 bytes，SHA-256
`677e8049d72dec927c2ad960077c58cead8fe407eeb8953984df80142b9988cb`；ISO 12800 需再取一個短 session
驗證 record-version 與四個新欄位。

最終 `2026-09-16-iso12800-c/` 驗證通過：60/60 筆、sequence 0–59、record version 2，四欄固定為
`relative_gain=14976, analog_code=3840, analog_ratio_x100=1606, hcg=true`；AF-side RGBgain 亦為
14976。這同時確認正確 singleton、v5 record layout，以及這台 fp 的 MONIT1/through 在 ISO 12800
確已進 HCG。H/L 中值為 4102.5／10216，仍遠低於 ISO 800，但如上所述不能在沒有亮度 histogram
的情況下把差額分解成 HCG 與 clipping。

### 9.3 v5 回到 ISO 100 的基線（2026-09-16 04:23 +08:00）

Capture：`captures/af-fusion/2026-09-16-iso100-v5/`。3 秒、60/60 筆 snapshot coherent，
sequence 0–59，無缺口、無無效回覆；一筆舊 session reply 被拒收。原 `echo` handler 已回讀確認
復原為 `0xC03D99A0`。

| 正確 IMX410 欄位 | ISO 100（本輪） | ISO 12800（v5，前輪） |
|---|---:|---:|
| relative gain，`+0x18` | 117 | 14976 |
| applied analog code，`+0x20` | 985 (`0x3D9`) | 3840 (`0xF00`) |
| analog ratio ×100，`+0x2C` | 131 | 1606 |
| HCG RAM flag，`+0x34` | 0 | 1 |
| AF RGBgain | 117 | 14976 |

另一次直接讀 RAM 的前 64 bytes：

```text
C2F1E654 00000008 00000008 00000034 00000034 00000034 00000075 00000075
000003D9 000003D9 000003D9 00000083 00000064 00000000 00000064 0000410F
```

因此 overflow digital `+0x30=100`、inter-node trim `+0x38=100`、force-LCG byte `+0x37=0`。
本輪 H/L 中值為 24718.5／57894，與先前 ISO100-b 的 24776.5／57955 相差約 −0.234%／−0.105%；
這支持回到低 ISO 後對比統計大致恢復，但沒有同步影像仍不能量化高 ISO 的 clipping 或雜訊效應。
`sensitivity=219, af_shutter=8333, f_number=2164` 不變。

當前 area index 0、AF drive mode 2；face/AAT 框皆為零。sweep index 9、`mposm=11068` 仍未更新，
DFD eligibility 保留未判定。下一步先用使用者移動單點 AF 框做區域對照，再測有臉／無臉與框尺寸；
必須另外量到 sweep 更新後才能開始 DFD 擬合。

### 9.4 診斷命令副作用更正與 ISO 校正域

前輪對 `check_convert_abs_gain` 與無參數 `high_gain_off` 的「唯讀」描述有誤：

- `FUN_c03ec308`（`blk_c03.c:164460` 附近）：有參數時暫停正常 scheduler，對每個測試值呼叫
  `FUN_c030c878(...,gain,1)`；這會走到感光元件 gain setter。保存／尾端恢復的是 **sensor mode ID**，
  `FUN_c030ce00` 會等待 `SetImgMode_s` 完成，但命令未保存原 gain，而模式重建又使用已被掃描修改的
  gain helper。因此不得保證命令結束就完整恢復原曝光。沒有檔案參數時不輸出檔案，仍會套用 gain。
- `FUN_c03ec210`（`blk_c03.c:164425`）：即使無參數，也呼叫 `FUN_c0320ca0(sensor,0)` 清除
  force-LCG byte `+0x37`。`high gain ctrl normal` 是 setter 的結果，不是既有狀態。
- 這些操作已在前輪執行，不能追溯宣稱全程唯讀。使用者後續手動選 ISO12800／ISO100 的 v5 captures
  及本輪直接 RAM 讀取確認當前 gain 正確；原 force-LCG 值沒有事前快照，無法回推。本輪量到 `+0x37=0`。
- 後续狀態驗證使用固定 RAM 讀取；`mode_now` 的 `FUN_c03eb8c8` 已核對為模式與 gain 資訊列印。

ROM ISO 校正表 descriptor `0xC0746728` 的 11 對錨點全部是 nominal ISO ×1.17。
`FUN_c00b8860` 做 ISO→relative gain，`FUN_c00b8840` 做反向顯示換算；所以 117/936/14976 的
來源現在有靜態表與實測雙重支持。先前約 10939–10949 的數字来自診斷器的反向 ISO 顯示與整數取整，
只能保留為當時設定下的門檻區間，不能擴張成所有 Live View 或錄影模式的硬體規格。

## 10. 當前工程判決

- **已證實**：fp 沒有可用的 PDAF readout，但有可讀的 Bayer-green 雙頻帶 AF 統計、內部 face/eye
  固定座標與完整 CDAF 驅動模型。
- **舊實測支持**：校正乾淨時，幾何估焦能達到小於半個景深的樣本外誤差；在 `1/size` domain
  做運動預測比直接外推 focus position 合理。
- **最值得現在做的事**：不是再找一個單張影像的相位替代品，而是把幾何當 feed-forward，
  把 Bayer-green DFD 當 observer，讓兩者共用同一次鏡頭移動。
- **尚未證實**：內部 H/L + `mposm` 是否足以在真人、錄影、不同鏡頭與不同光圈下穩定做到上述精度；
  這正是下一輪 collector 與 held-out 實驗要回答的問題。

## 相關資料

- `DFD_VIA_AF_STATS.md`
- `AF_DESIGN_REFERENCE.md`
- `AF_LIVE_STATE_MAP.md`
- `FOCUS_DISTANCE_PRINCIPLE.md`
- `FOCUS_POSITION_DOMAIN.md`
- `FACE_EYE_AF.md`
- `PTP_FOCUS_RECORDING.md`
- `../../lens/notes/LENS_CALIBRATION.md`
- 舊專案：`sigma-fp-bridge/focus-ai/FINDINGS.md`、`DESIGN.md`、`focus/model.py`、`focus/predict.py`
