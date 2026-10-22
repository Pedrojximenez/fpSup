# 上游截斷：既有實機素材稽核

2026-09-24。只讀現有檔案，沒有操作相機。本次搜尋範圍為 `/Users/dido/Developer.localized/SIGMAfp_re` 及使用者舊研究 `/Users/dido/Documents/Codex/2026-08-16/4`；沒有擴搜 home、Downloads 或外接裝置。

## 可下的結論

**現存素材不能證明目前 LCD 的第一個截斷點；也不能排除 tone 之前已發生截斷。** 這次有三個可重算的結果：

1. 舊 OFF 與 T&O 的完整 PQ RAM dump 逐 byte 完全相同，四份 20-byte tone block 均為零。它們不能提供「兩模式 pre-tone 設定不同／相同且已在硬體生效」的證據。
2. GammaDump 的四類 MMIO 成果檔在指定範圍沒有找到；不能把讀取脚本或擬定的測試當成實測結果。
3. 有一組可信的 idle LiveView 狀態報告：sensor enum **8**，2016×1344、12-bit、`gain_state: through`，`raw_zoom=1024/1024`、`hvbin=1/1`。**這個狀態不支持「所有 LiveView 均由 CRCT hbin/vbin ÷3 產生」**。感測器自身已是縮減讀出，與 CRCT 的 hbin/vbin 是不同層。

可用 [audit_capture_evidence.py](audit_capture_evidence.py) 重算；詳細來源、byte 數及完整 SHA256 保存在 [capture-evidence-audit.json](capture-evidence-audit.json)。可用 `--output /tmp/fp-capture-audit.json` 寫到指定位置，或提供已存在的目錄。

## 1. 八月 PQ 與 gamma 素材

來源目錄：`/Users/dido/Documents/Codex/2026-08-16/4/outputs/`。

| 素材 | 重算結果 | 證据意義 |
|---|---|---|
| `OFF/PQP844.bin`、`T&O/PQP844.bin` | 各 2116 bytes；不同 byte = **0**；各有 **335 個 nonzero byte** | 是兩份相同的物件 snapshot；不是全零空檔，但缺少 timestamp／mode／active-bank 配對 |
| 兩模式 `TONE_CH0.bin` | 各 20 bytes，全零；吻合 PQ `+0x140..153` | 沒有取得 2048 點主 tone LUT；這 20 bytes 是另一個控制 block |
| 兩模式 `TONE_CH1.bin` | 各 20 bytes，全零；吻合 PQ `+0x55C..56F` | 無法由全零判定 bypass、生效曲線或像素是否 clip |
| `GAM158*`、`PST15E*`、`CEQ1D0*`、`YUV1E0*` | 指定兩根各查到 **0 個** | 只有 `AutoRun_GammaDump*.txt` 及說明，無可重算的 active MMIO 值 |

PQ 的完整 SHA256：

```text
6bd7d08b94f7a44043d5c40f3d21c52ed198f6220d0121dd3da1967917cdfd86
```

四份 20-byte tone block 的共同 SHA256：

```text
de47c9b27eb8d300dbb5f2c353e632c393262cf06340c4fa7f1b40c4cbd36f90
```

`AutoRun_PQPrePstDump.txt` 的來源確為 `0xC3824258`、`0xC3824398`、`0xC38247B4`。來源脚本只記錄 RAM，沒有寫入操作。但是「資料吻合 script 指定的 slice」不等於這一塊 RAM 已經成為該幀 hardware configuration；舊素材沒有留下其 active context 的佐證。

不能因 OFF/T&O 兩檔相同就推導「創作模式不改上游」，也不能因其 tone block 為零就推導「linear 已生效」。兩次執行時機、mode 切換是否完成、物件是否是 live context，都尚無資料。

## 2. 真正留下的 through 狀態與增益

來源：`projects/fp-af-assist/notes/evidence/capture-af-fusion-2026-09-16-iso100-v5.md` 的原生 `imager mode_now` 回覆，並以同目錄 `samples.jsonl` 重算 60 筆快照。

```text
No 053, MONIT1_60, enum 0008, 12-bit, 2016x1344, 60 fps, 3:2 full
shutter:00016663,gain:000117
gain_state: through
small_raw
base_size 2016x1344
raw_zoom  1024/1024
hvbin     1/1
bef_size  2016x1344
v_down_sample 1
```

這裡的 **No 053 是模式列表序號，enum 8 是 sensor mode**。它們均不是預览 PARAM profile **5**，更不是錄影 PARAM profile **429**。不能用名稱、幾何相同或数字接近把這幾個編號互換。

兩組 v5 JSONL 的重算：

| capture | record／coherent | movie_recording | relative gain | analog code | analog ratio ×100 | HCG RAM flag |
|---|---:|---|---:|---:|---:|---:|
| `2026-09-16-iso100-v5` | 60／60，seq 0–59 | 全 false | 117 | 985 | 131 | 0 |
| `2026-09-16-iso12800-c` | 60／60，seq 0–59 | 全 false | 14976 | 3840 | 1606 | 1 |

每組上述 gain 都只有一種值。JSONL SHA256 分別為：

```text
a0da73560897b14a23c2d5fc4870841b520bc0d461fc3ac7d6bdbef639b935f1
cdb8b92bb7dcdf3dcc94d74f9d865bbe9ead9f702cfd1bf685b4894c1887d378
```

這些是 sensor-driver RAM 的實測；不是 I2C latch 的直接讀回。它們證明 LiveView 的 gain/HCG state 有值得同步保存的動態值，**沒有 paired RAW／pre-tone pixel／LCD pixel，也沒有等曝光 record state 的同場景對照，因此不能推出 through 比 record 少幾檔、或哪個通道已飽和**。AF H/L 的數字不能代替像素 histogram。

`research/other/notes/CAMERA_STATE_SOURCES.md` 還留有 ISO800 下 sensor shutter 16663µs、AF shutter copy 8333 的差異。這足以提醒不能拿 AF-side 曝光欄位當逐幀 sensor 曝光真值；不能將兩倍差直接解釋成 LCD 被額外放大一檔。

## 3. bin/vbin 與 profile 5 的證據分級

### 有記錄的路由證據

- `projects/open-gate/notes/LIVE_VIEW_DISPLAY_CHAIN.md:103` 起留有待機／半按時 profile 與引擎 geometry 的差異：profile 5 表值更新後，引擎仍會取得兄弟 profile 的 2000×1125。`§5` 明確記錄錄影期預覽使用 recording profile 的預覽半部。這是**狀態切換／geometry**的證據，不是 code-value clipping 測量。
- `research/imaging-hw/notes/CRCT_PATH_SELECTOR_SOLVED.md` 將 306 個 PARAM profile 靜態分為 B 172、C 36、D 81、E 17；E 的 17 個 UHD profile 同時包含 record RWZM 與 preview hbin/vbin 的配置。不能沿用舊 `REDUCTION_INVENTORY.md` 本體仍保留的「RWZM 完全沒開」與「兩者互斥」敘述；其開頭已明示被後文推翻。
- 上節實際 idle `mode_now` 的 `hvbin 1/1` 只約束那個當下，不否定 UHD recording profile 可能啟用另一條 bin/vbin 預覽支線。

### 看起來像實測、實際是模擬的素材

`research/other/external/FP3K-technical-handoff-2026-09-10/analysis/reduction-method/native-trace.json` 在原生 ARM/Thumb code 上跑 Unicorn，周邊 MMIO 使用普通 RAM 替身。

| trace fixture | recording A0/A7/A1 | route |
|---|---|---|
| Stock UHD24，profile429 | 0/0/1 | CrctRwzmToBufA，ratio 1600/1600 |
| 舊 FP3K，profile429 | 0/0/1 | CrctRwzmToBufA，ratio 2048/2048 |
| UHD DC Crop，profile432 | 1/0/0 | CrctCrmfToBufA |

這份資料很適合驗證 firmware selector 與 driver 寫了什麼；**它沒有模擬 silicon pixel arithmetic，不能證明真实 hbin/vbin 累加、normalize、rounding、飽和或 clipping threshold**。也不應稱它為相機實拍的 bin/vbin 活動值。

### 既有 reduction 影像對本題的限制

`projects/open-gate/notes/REDUCTION_KERNEL_MEASURED.md:443–467` 明示 S4/S4b（全讀出 + hbin/vbin）的數值只有 firmware table／模擬，hbin/vbin 本身沒有實拍素材。`§2204` 再列為未決。OG3K/OG2K 的既有實拍被用來量 sensor reduction，而 RWZM 另有量測；這些不能當成 CRCT hbin/vbin 飽和測試。

其附件 README 指定的七個原始 DNG 在 `~/Downloads/quality-tests-frames-public`，本輪未擴搜該處，亦沒有藉既有降噪／kernel 結論聲稱它們是亮度階梯或 LiveView 配對。

`projects/open-gate/captures/opengate_ev_bug_20260914/compare_083_084/result.json` 是 recording FHD／OG3K 曝光對照：ISO800、f/2、1/60s，匹配區域 ratio median **1.00909（0.0131 stop）**。這支持該 recording 配對沒有巨大的曝光偏差；沒有 LiveView 幀，不支持推論 LCD 中的 pre-tone headroom。

## 4. 這些素材能否直接回答「上游還有截斷」

| 要回答的命題 | 現有 evidence |
|---|---|
| CRCT bin/vbin 在所有 live 狀態都啟用 | **否**；已見 through 的 hvbin 1/1；其他 profile 必須分別判定 |
| bin/vbin 可在某些 UHD profile 被原生配置 | **是，靜態 selector／driver 支持**；須與 sensor reduction 分開 |
| bin/vbin 實際因累加 overflow 提前剪高光 | **沒有測到**；缺 input/output pixel 或亮度階梯 |
| through 與 record 使用同一個採集／gain 狀態 | **未建立**；既有資料已顯示 through 狀態與可變 HCG，但沒有同場景 record 配對 |
| 現在 tone 之前像素已到上限 | **沒有足夠 pixel evidence**；原 AutoRun 效果沒有當幀 RAW/tone/input/output 配對 |

**截至這份既有 capture 稽核，應停在「缺少像素配對，不能判有也不能判無」。** 下一次有價值的資料必須按待機、半按、錄影分開，至少把當幀 sensor enum／gain state、PARAM profile、active route、bin/vbin／RWZM、active pre-tone 配置與該路來源像素綁在一起。光保存另一張 DNG、另一個 OSD 截圖，或另一份未驗 active context 的 register dump，仍不能定位第一個截斷点。
