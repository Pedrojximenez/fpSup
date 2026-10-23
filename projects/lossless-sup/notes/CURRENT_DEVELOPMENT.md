# 當前開發指引 — 2026-10-13

**現行方式（下午起）**：以正式版 v0.2.0test 為基準逐項推進，每項上機確認有進步才做下一項；第一項是共用檔頭。
詳見 [PROGRESS_20261013.md](PROGRESS_20261013.md) 補記 5。`fpSup/lossless` 目前＝正式版原始碼（重建 `ad984ce6…`）；
今天的改動存於 `validation/20261013-work-snapshot/`。相機：正式版 `ad984ce6…`、UHS-II、LOSS 關。

現行入口是 [PROGRESS_20261013.md](PROGRESS_20261013.md)：主線是降低 CinemaDNG 緩存管線的 CPU，讓 119.88p 可用（使用者已禁止再試 240p）。
相機目前是正式版 LOSS v0.2.0test（`ad984ce6…`）＋RES-Lab，Lossless RAW 已開、HS280 119.88p；尾表字組化已省下約 70% 尾表 CPU。`890210a9…`（120p 工作區）與預備雙 IFD 檔頭都只完成離線驗證。

最新（補記 3、4）：registry 掃描修正與新格數公式已上機，CPU 差異不大；HS280／M12240 每幀被引擎拒絕，與切法、位址、位元順序無關，
最可能是到達 hook 時畫面尚未寫入。已實作通用的**拒絕閘門**（連續 8 幀無較小檔案就停送引擎，每 120 幀試探），離線測試全過，
候選 `7e920525…` 待使用者同意後上機（[20261013-refusal-gate](../validation/20261013-refusal-gate/README.md)）。
不做執行期 CPU 預算閘門（機身相同）。拒絕閘門依實際壓縮結果決定，不是 CPU 預算。

## 2026-10-04 入口（已被上方取代）

[PROGRESS_20261004.md](PROGRESS_20261004.md)：Lossless 已出貨，本輪保留雙 lane／單 codec 架構，修正 HELD 取消、未知 codec 狀態下誤啟動另一 lane、REC 堆疊對齊，並加最小原生停錄診斷。後續 SD 自動停錄缺幀與批次問題見 [EARLY_STOP_94.md](EARLY_STOP_94.md)。發布／選單整合歷史見 [10/03 筆記](PROGRESS_20261003.md)。

## 以下為 2026-09-27 歷史快照，不作現行開發指令

本段寫在 copy-back 基線時代；之後改成寫回相機自己的 buffer、再改成非同步＋零輸入拷貝。「只維持 FHD 1936×1090」及後續舊限制已被 [9/30](PROGRESS_20260930.md) 與更晚的逐日進度取代。以下保留原始紀錄；衝突時以 10/04 的現行入口為準。

本頁是短版工作入口；與本輪之前的「下一步」衝突時，以本頁及 ROADMAP §16 為準。
本輪只核對本機 source、既有實驗紀錄與離線測試；未操作相機、未改 runtime、未改卡或部署。
`[L]` 實機紀錄、`[H]` 主機驗證、`[C]` 程式事實、`[P]` 待做項目不可互換。

## 1. 方向：保留 copy-back 基線，先補雙區探針，不開新框架

**C2 單幀 copy-back 已成功，因此不再把「先做自有 output pool＋release callback」列為共同前置。**
現行基線：同步 encode 到自有 scratch → 組完整 DNG → 確定放得下 → 複製回原生 DNG 區域，
只改 `seg[1]`，不改 `seg[0]`。下游持有原生 frame，不持有我們的 scratch。

目前仍是 `development-only / camera_ready=false`；先維持 FHD RAW12、1936×1090、
512×368 tiles、predictor 1、SD／23.976 目標。不擴充 worker、通用 pool、SSD、UI ON 或動態抽幀。
zero-copy 是獨立研究：**減少一次 copy 的效益尚未實測，不足以跳過原地覆寫的安全證明。**

## 2. 哪些已成立，哪些還沒有

| 證據 | 已成立的範圍 | 尚未成立 |
|---|---|---|
| [C1](../build/ledger-c1-frame-survey-20260926.json) [L] | 同模式兩次，clone counters=0，owner=`0xFFFFFFFF`，frame kind=1；`seg[0]=allocation base+0x2000` | 其他模式／每一幀都無其他讀者 |
| [C2](../build/ledger-c2-copyback-20260926.json) [L/H] | 單幀 copy-back 寫出 1,476,608 B、12 tiles、可解碼；本次 alias 可見性成立 | sustained、同幀 bit-exact、copy 耗時與完整 call 預算 |
| [PHASE 9：9/26](../build/ledger-phase9-refused-20260926.json) [L] | 縮小 geometry＋生成來源：init=1、encode=0 | 沒寫出有效輸出，不是 bound pass |
| [PHASE 9：9/27](../build/ledger-phase9-geometry-20260927.json) [L] | 正式 geometry＋原生 frame：init/encode/size=1，輸出遠小於宣告長度 | 未觸界；總長還有下述帳差 |
| `bound-probe-two` [C] | host 命令與 ARM `PROBE_TWO` 分支存在 | 完整雙區 ownership／release、端到端測試與實機結果 |
| [壓縮預判](../build/ledger-precheck-prototype-20260926.json) [H] | host 原型存在；構造反例可低估 91.72% | 可用門檻、ARM 成本、批准 zero-copy 的能力 |

C2 的 **13,753 µs 只有 encode**，不是 encode+copy。現行 source 已加 post-encode 計時及
模擬測試，但新增欄位尚無對應實機證據；先核對它涵蓋 header/copy 的範圍，再量完整成本。
C2 仍用了 retained 4 MiB scratch；「不需額外 output slots」不等於「不需額外記憶體」。

### 兩筆必須保留的證據訂正

1. 9/27 ledger 的 12 個 tile sizes 實際加總 **790,656 B (`0xC1080`)**，總長欄卻為
   **790,528 B (`0xC1000`)**，差 128 B。專案內未找到原始 dump/log 可消解矛盾；原 ledger
   不改，不任選一個值。推導的 870,400 B、3.73× 與「sum checks out」暫不採用。
2. 9/26 → 9/27 同時改了 geometry、tile count 及來源（生成資料 → 原生 frame）。
   只能說後一組成功，不能把「非 sensor geometry 一律拒絕」寫成已隔離的根因。

C2 與鄰幀的統計／差值不能替代同幀原始像素比對。header 的 stock/control 比較支持已檢查
位置的保留，不是所有 metadata 語意或全檔 byte-exact 的證明。

## 3. 下一個 patch：雙區 bound probe 的離線閉環 [P]

只做以下四項，不同時加 C3、zero-copy 或預測器上機：

1. **讓兩個 allocation 都有可追溯的生命週期。** 少量兩筆紀錄即可：allocator、handle、
   實際容量、同 boot 的取得／仍持有證據、用途與回收責任。現在第二 handle 由參數手填，
   地址範圍／對齊／不重疊只證明形狀，不證明它屬於我們。`release` 目前只管理第一區。
   「run scratch twice」與現行 gate 衝突：第一次 scratch 後不再是 power-preflight，
   重新 preflight 又被 retained-state gate 擋住。**不清 state、不手抄歷史地址繞過。**
2. **把失敗分類補全。** PHASE 9 已拒絕 `F_ENC != 1`；`F_SIZE` 返回只保存、未檢查即加總，
   必須补 gate。encode 失敗分支只讀兩個 guards，其餘不可沿用舊值。結果的宣告長度欄目前
   是 `PROBE_DECLARED` 常數；若聲稱 hardware readback，須另存實際讀值與來源。
   codec 逾時／所有權不明時，兩區都不能直接 free、覆寫或重新 arm。
3. **補行為測試，不只組譯／文字斷言。** FakeShell＋ARM 模擬涵蓋第二配置失敗、錯誤／
   重疊 handle、重入、部分初始化、encode/size 失敗、完整結果與安全回收。機身端目前
   沒有重做 host 的不重疊檢查。現有 PHASE 9 五項主要是 source/組譯檢查，沒有其 Unicorn
   執行覆蓋，也沒有 `arm_bound_probe_two` 的完整 host 行為測試。
4. **先定義什麼才叫觸界。** 用相同生成 pattern 對照 host encoder，確認它確實造成超限需求；
   保存原始 state、全部 tile sizes、return codes、guards、variant、source/binary hash。
   編碼被拒、size 無效、輸出太小、帳差或僅五個 words 沒變，都不能報 bound PASS。

完成定義：兩區取得到回收可追溯，失敗不孤立配置／不產生假陽性，相關離線測試有清楚
pass/fail/skip。這只是下一輪另行授權實驗的前置，**不是硬體上界成立**。
自有來源與目的區可避免刻意覆寫原生 frame，仍不能消除未知 DMA overrun 風險；canary 是偵測，
不是寫入上限。雙 4 MiB 只是候選實驗版面，不是所有輸入的安全容量 proof。

## 4. 隨後才補 C2 成本與 C3 八幀 [P]

- 先量 encode、post-encode/header+copy、完整 writer wrapper 的時間；不要把 G4a 反向
  mirror 速率或 C2 encode 時間回填成 copy 成本。正式 23.976 每幀約 41,708 µs。
- 保持每幀原生 frame 身分與有效範圍檢查；採當幀 header，不複製舊幀動態欄位。
- `copy-back-sustained` 目前不存在。實作前先確認容量、原生 ownership、時間及停止條件。
  有界八幀須逐幀匹配 length、metadata、記錄與读回資料，並觀察 batch 回收進度。
  不要求靜態場景所有 hash 必然不同；八幀成功也不等於 sustained／熱穩定。
- copy-back 避免自有 output arena 被 SD 持有，**沒有消除原生 batch policy**。
  壓縮檔較小可能改變批次回收節奏；不要以推算 28 格或固定 ~48 幀當正式 sizing。

## 5. 三種容量與產品邊界不能混在一起

| 數字／規則 | 意義 |
|---|---|
| 4 MiB scratch，compressed payload 可用 4,048,896 B | 現行實驗版面；14-bit 模型 3,957,888 B 仍不含完整 hardware/stuffing proof |
| `file_bytes <= original seg[1]` = 3,244,544 B | copy-back 的目的範圍上限；含 79,872 B 新 header，payload 最多 3,164,672 B |
| engine 宣告長度 `0x305000` = 3,166,208 B | 已定位的長度值；硬體是否強制、超限時回報／輸出是否有效仍未知 |

C1 顯示 allocation 是 3,252,736 B，DNG 從 base+8,192 開始。原 pixel 起點後剩
3,165,696 B，比上述 engine 長度少 512 B。**allocation 外那 512 B 間隙不是自有空間**；
也不借用 DNG 前的 8 KiB。copy-back 仍只用被交付的 `seg` 範圍。

硬體即使會停寫，也不等於 zero-copy 安全：原地編碼可能先毀掉 RAW，再因超限停止／截斷。
還須分開證明讀寫不追越、完整 DNG layout、成功／超限結果與不可恢復來源的處置。
PHASE 8 有片段不等於完整功能，不批准在原生 RAW 上試寫。

PHASE 7 的「放不下，原幀留 RAW」是研究探針的 mixed 行為，不是 fixed-lossless 產品承諾。
固定模式仍不得片中靜默 fallback；若選擇產品化 mixed，另定模式與相容性，不在此默認切換。
簡易預測器最多選擇已各自驗證的可恢復路徑，不是容量、ownership 或 zero-copy 的安全門檻。

## 6. 本輪離線核對與入口

- `test_single_frame_codec_probe`：本輪 **94 tests OK，未報 skip**。
- `test_codec_emulation`：第一項程序 **exit 132，無 Python traceback**，未完成；原因未定位，
  不列通過，也不視作原生 ARM 行為的失敗證據。先排查本機模擬執行環境，再重新取得結果。
- 舊 ledger 與既有 runtime source 不修改。測試記錄不是本輪相機驗證。
- [`BUFFER_DESIGN.md`](BUFFER_DESIGN.md)：當前 buffer 方向及自有 slots 備案。
- [`LIVE_TEST_PACKAGE.md`](LIVE_TEST_PACKAGE.md)：已訂正的 C1/C2 門檻；所有實機操作仍需另行授權。
- [`NATIVE_BUFFER_PATTERNS.md`](NATIVE_BUFFER_PATTERNS.md)：原生 cache、callback 與 frame owner。
- [`COMPRESSION_PRECHECK.md`](COMPRESSION_PRECHECK.md)：原型與反例邊界。
- [`single_frame_codec_probe.py`](../../../fpSup/raw/lossless_codec/single_frame_codec_probe.py)、
  [`ARM probe`](../../../fpSup/raw/lossless_codec/single_frame_encode_discard_probe.S)：本輪核對的 source。

未來抽幀只保留 `source_seq`、`source_pts`、encode 前選取位置；跳過壓縮不等於丟掉一幀。
