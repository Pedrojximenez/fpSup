# 壓縮前的簡易收益預判

日期：2026-09-27。狀態：host 原型已存在；門檻、相機實作與成本未成立。  
適用：FHD RAW12、predictor 1、兩個 CFA column components、512×368 tiles。  
相關：[`BUFFER_DESIGN.md`](BUFFER_DESIGN.md)、[`PROGRESS_20260930.md`](PROGRESS_20260930.md)。

9/30 實作更新：收益預判維持離線研究，不阻擋當前 FHD 生命週期修正。新增的單工作槽 policy
先比較 encode 後的**完整 DNG** 實際長度，不更小便同來源 RAW 交回並繼續；這不是壓縮前
預測，也不能保護 DMA 輸出容量。原生交接尚未接入，見 PROGRESS §10。
原本「零輸入拷貝」仍有
獨立 codec 輸出區與 copy-back，並非下文警告的 PHASE 8 codec 原地覆寫；兩者不可混稱。

## 1. 結論

**不要過度設計：保留現有 host 原型作離線評估，不把它升格為安全閘門，也不擴大預測框架。**

9/26 已有 [`compression_precheck.py`](../tools/compression_precheck.py)、
[`calibrate_precheck.py`](../tools/calibrate_precheck.py) 與
[原型紀錄](../build/ledger-precheck-prototype-20260926.json)。實作使用 residual category histogram
估 Huffman 成本，不是下方原先提議的純 `mean(k)` 分數。現有 11 個案例僅約兩種獨立真實條件，
沒有可採用門檻；構造反例低估 **91.72%**，輪換抽樣位置不能消除這個風險。

原型可回答「值得進一步校準嗎」，不能保證某幀會壓小。host encoder 的少量貼合不代表
所有硬體輸入的 ground truth；payload／JPEG tiles／完整 DNG bytes 必須分清後比較。
codec 原地覆寫的安全性並未成立，原型註解中的「預測好就走 zero-copy」不作開發授權或當前設計。

若之後需要更簡單的機身版本，再比較單分數／單門檻是否足夠：

1. 在畫面分散取少量 RAW 小段，算 `abs(raw[x] - raw[x-2])` 的 bit-length 平均值。
2. 先用現有影像離線對照實際壓縮大小，確認這個分數能否分出「值得壓／不值得壓」。
3. 能分開才設一個固定門檻；分不開就先不用，不追加模型來湊精度。

不追加信心模型、三區 hysteresis、scene-cut 偵測或動態調參；也不為了符合舊提案重寫現有 host 原型。
現有抽樣約 12,288 residuals；門檻未定，先前 90%／98% 仍只是候選，不是首版規格。
目前先記錄、不改 fixed-lossless 行為。未來 mixed mode 才用它決定是否略過壓縮；不是丟幀。

安全界線：抽樣可能猜錯，不能縮小輸出緩衝區或批准原地覆寫。
copy-back 可在 encode 後以真實尺寸決策，但 scratch 的容量安全仍须獨立成立。
目前優先工作見 [`PROGRESS_20260930.md`](PROGRESS_20260930.md)，不讓預判阻擋 buffer 修復。

**以下 §2–8 保留為推導／備查，不是待全部實作的清單；若與本節衝突，以本節為準。**

## 2. 抽樣什麼：同一 component 的 predictor residual

JPEG predictor 1 使用同 component 左鄰，並將差值依 magnitude category 編碼，再加上表示差值的
bits。標準依據是 [ITU-T T.81 Annex H.1.2（W3C 保存的標準全文）](https://www.w3.org/Graphics/JPEG/itu-t81.pdf)。
本專案的兩 component 排列見 [`ljenc.py`](../../../research/slimRAW/ljenc.py) 與
[`ljcost.py`](../../../research/slimRAW/ljcost.py)。

在目前 RAW 排列的 tile 內部，應算：

```text
d = raw[y][x] - raw[y][x-2]     # 偶/奇欄各是一個 component
k = 0                         if d == 0
    floor(log2(abs(d))) + 1    otherwise
hist[component][k]++           # RAW12 / P1: k = 0..12
```

**不是直接 `x-1`**：那會跨 CFA component，估到不同的差值分布。sample window 的左緣若不是
真正 tile 左緣，要另外讀它左方兩個 pixels，不能把每個抽樣窗口當成 codec restart。
真正 tile 起點、列首與 restart 邊界依 codec predictor 規則另處理。

第一版不需要浮點運算或真正輸出 JPEG：`k` 可由 integer bit-length／小 lookup 算出；兩 component
各 13 個 uint32 counters 僅 104 B。逐 tile 處理，或保留 12 組約 1.2 KiB histograms。

## 3. 最小抽樣配置 [P]

候選：每個 tile 分四個空間區域，各取一對相鄰掃描線、每條 128 個 RAW samples。

```text
12 tiles * 4 windows * 2 rows * 128 samples = 12,288 residual samples
```

約占 active frame 0.58%；每窗口再讀左鄰，packed RAW12 約 18–20 KiB 的資料量，未計 cache-line
與邊界額外讀取。這是資料量估算，不是相機時間保證。採連續小窗口避免隨機逐 pixel 存取。

- 覆蓋所有 12 tiles、兩個 column components、兩種 row parity。
- 位置依 `source_seq` 以 deterministic offset 輪替，避免固定格點永遠漏掉同一紋理。
- 避開越界；right/bottom edge tiles 按 active dimensions 處理。
- padded pixels 與邊界成本單獨建模；不可默認全部 512×368 padding 都是免費零差值。
- 不只抽中心，不只看上一幀，不只靠 ISO。scene cut、曝光變動或跨 tile 分布差異大時降為 UNKNOWN。

目標是將 estimator 成本控制在少量整數統計；是否值得每幀執行，必須量測 `precheck_us`。
目前每次 encode 約 13.6 ms 的少量證據不能推导 CPU 抽樣一定只花某個固定微秒數。

## 4. 從 histogram 估大小

對每個 tile/component 分開估，保留 local entropy 差異：

```text
p[k] = hist[k] / sample_count
estimated_bits_per_sample = sum(p[k] * (estimated_huffman_length[k] + k))
estimated_file_bytes = expanded_header_bytes
                     + estimated_entropy_bytes
                     + estimated_stuffing_bytes
                     + marker/restart/padding_bytes
```

只有 13 bins，建立一個小 Huffman cost table 很便宜；也可先用已校準的碼長表。不可直接把
histogram Shannon entropy 當成全部 bytes：還有 magnitude bits、Huffman 限制、byte stuffing、
DHT/markers 及 padding。`ljcost.py` 可重用思路，但其約 96 B markers／未計 stuffing 的結果不能
原樣當作精準預估或安全上界。

更簡的 prototype 可先用 `mean(k)`、`P(k>=10)`、`P(k=0)`、各 tile 差異做三區 classifier；
這些 threshold 必須用同幀 camera output 校準，不能直接聲稱 `mean(k)<某常數` 必定壓小。

估計器輸出 `{pred_bytes, estimated_error, confidence, reason, sample_count, precheck_us}`。
預測區間是經 held-out fixtures 校準的經驗區間，不是對任意影像成立的數學 bound。

## 5. 簡單三區門檻 [P，初值待校準]

比較 **完整檔案**，不是只比 payload；stock 為 3,244,544 B，compressed header 為 79,872 B。
以下以「值得省空間」作第一個目標：

| 條件 | 預判 | adaptive mixed 的建議 |
|---|---|---|
| 預估區間上緣 ≤ stock 的 90% | 很可能可省至少約 10% | 可進 KEEP_COMP resource admission |
| 預估區間下緣 ≥ stock 的 98% | 很可能省不到約 2%，或更大 | KEEP_RAW 候選，仍需 RAW 路徑有資源 |
| 其他／信心不足 | UNKNOWN | 明示模式決定；不要宣称一定變小 |

90%/98% 是 hysteresis/最低收益的初始政策範例，不是已從本機訓練出的最佳門檻。
「省不到 2% 不值得」也不等於「絕對不會變小」。若使用者只在意任何 byte saving，可另設
最小收益，但接近 100% 時最容易誤判，且通常最不值得付 encode 成本。

## 6. 省空間與省時間是兩個問題

壓小 5% 不代表端到端較快。用串行、穩定 throughput 的粗略模型：

```text
saved_bytes = stock_bytes - predicted_compressed_file_bytes
write_time_saved = saved_bytes / effective_storage_bytes_per_second
壓縮較快的候選条件：write_time_saved > encode_time + extra_header/submit_cost
```

若兩個 action 都要跑 precheck，其共同成本比較時可消去，但仍占整個 pipeline budget。
若與「完全不跑 precheck 的 RAW」比較，則還要計入 precheck 成本。
此模型只作排序；已有 codec/storage overlap 時，應看真正 bottleneck、queued bytes 與 release
latency，不能把兩段時間直接相加。G3 的 372 µs 不是 storage throughput 的估計基礎。

因此 `should_compress` 不只看預估 bytes，至少還要看 output slot、codec admission、RAW source
ownership、ordered cursor 與儲存水位。**卡片已壅塞時跳過壓縮改 RAW 可能更糟**，不能把
「skip codec」當成普遍降載方式。

## 7. 接到動態抽幀，但不可把兩種 skip 混在一起

```text
identity/time + journal credit
  -> cadence/pressure 決定 DROP: 不抽樣、不copy、不codec、不配置大buffer
  -> 需要保留該幀: cheap precheck
       -> policy選 KEEP_COMP / KEEP_RAW / UNKNOWN
       -> all-or-none resource admission -> ordered submit
```

- fixed lossless：每幀壓縮的契約不改；預判只作 telemetry／preflight，不能偷偷 RAW fallback。
- adaptive mixed：可跳過「壓縮」，但 frame 仍輸出 RAW；需要 mixed compatibility gate。
- VFR：跳過「frame」是獨立政策，要有合法 recorder skip 接口及 journal 時間軸；不能由低壓縮率
  直接決定丟幀，除非使用者啟用的明確策略如此規定。
- UNKNOWN 不可在 codec 進入後再假裝未處理；任何後驗改判仍受原 ownership/failure rules 約束。

預判不需要完整 input copy 或第二個 image pool；在 source 仍合法可讀時讀小窗口即可。
frame ticket 只增加少量預測欄位，output allocation 仍由 capacity proof 決定，不採 predicted bytes。

## 8. 最小研究路徑

1. host prototype：分層抽樣 + 13-bin residual hist + 三區判定，先不加入 runtime policy。
2. 用同幀 camera encoded bytes 當 ground truth，記錄預估／實際大小、false-compress、false-skip。
3. 場景含平滑、細節、正確曝光高 ISO、暗部雜訊、局部紋理、scene cut、合成反例。
   訓練／校準／測試依 clip/scene 分組，不能以相鄰 frame 隨機切分冒充泛化。
4. 驗證 sample budget 與位置，量 CPU/DRAM/cache 開銷；若 precheck 自身昂貴則減量或停用。
5. 在已解決 buffers／metadata／writer identity 的 pipeline 中先 shadow-mode 記錄，才啟用 mixed action。

輸出品質不受預判本身影響，因 RAW 與 lossless 都保留樣本；錯誤主要影響空間、效能與 profile
相容性。安全容量、來源 ownership、release fence 與 true-drop 時間軸仍是獨立硬 gate。
