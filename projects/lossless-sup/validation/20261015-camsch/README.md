# 2026-10-15 「CamSch 只在 LOSS 開啟時偏高」排查

## 方法

診斷建置 `build_v3_lossless.py --time-hooks`（`FPL_DIAG_HOOK_TIME`，只在此選項下編入；一般建置仍是 `e82c1e12…`）：
每個 hook 的 C 入口包一層，記呼叫次數、累計／最長 µs、最後一次的堆疊指標；原廠 enqueue（`C037DD50`）另計時間。
堆疊指標用任務表（`research/autofocus/captures/native-preflight/20260927-121028/native-stack-check.json` 的 istk／stksz）對應任務。
`hook_take.py` = `cpu_short.py`（第 1.0–3.0 s tskmon，第 4 s 停）＋前後讀計數。卡上有 FCAP（每批 40 幀），UHS-II。

## 1. LOSS 的程式跑在哪個任務

| hook | 任務 |
|---|---|
| arrive、observe、stop、event | **MRecMgr** |
| flush、written | **SRecFile** |
| rec | RecPMgr |

**沒有任何 LOSS 程式在 CamSch 裡執行。**

## 2. FHD 29.97p，同一輪（OFF：診斷版 OFF；ON：診斷版 ON）

| | 總 CPU | CamSch | MRecMgr | SRecFile | FPLCODE |
|---|---|---|---|---|---|
| OFF ×3 | 19.3 / 19.2 / 19.2 | **6.0 / 6.0 / 6.1** | 2.4 / 2.2 / 2.2 | 0.9 / 0.8 / 0.9 | — |
| ON ×3 | 21.0 / 20.9 / 21.2 | **5.9 / 5.8 / 6.1** | 2.6 / 2.6 / 2.6 | 1.1 / 1.1 / 1.1 | 1.1 / 1.1 / 1.1 |

**29.97p 時 CamSch 開關 LOSS 沒有差別。** LOSS 的 +1.8 點是 FPLCODE 1.1、MRecMgr 0.3、SRecFile 0.2。

每幀（ON，29.97p）：arrive 約 570 µs，其中原廠 enqueue 約 308 µs（OFF 時原廠 enqueue 約 113 µs），LOSS 自己約 260 µs（接手、送引擎）；
observe 約 45 µs（每幀同步 inline 值）；flush 約 14 µs；event 1.6 µs。

## 3. FHD 59.94p

ON ×3：總 41.5 / 39.5 / 39.7、CamSch 15.9 / 14.1 / 14.4、MRecMgr 5.7–5.8、FPLCODE 2.2、SRecFile 1.9–2.2；
arrive 約 540 µs、observe 約 62 µs。
OFF 在這張卡（V60）59.94p 約 134 幀就以 `vbuf` 自停（RAW 約 195 MB/s 寫不完），窗口內含停錄，**無法當對照**。

## 結論

- CamSch 偏高不是 LOSS 程式直接造成的：沒有 hook 在 CamSch 裡，29.97p 開關 LOSS 的 CamSch 相同。
- 59.94p 是否仍偏高，這張卡量不了 OFF 對照；10/13 的「高 3–5 點」也可能來自不同開機之間的差（同日記錄：開機間 CamSch 差 3–8 點）。
- 可以省的地方都在 MRecMgr：observer 每幀 45–62 µs（逐 byte 讀寫 IFD 欄位，可改整字）、送引擎約 260 µs（10/12 記過引擎設定 0.30 ms／幀可每段快取）。
- 原廠 enqueue 在 ON 時每次約 300 µs、OFF 時約 110 µs，原因未查（推測：釋放的幀遇到寫入器空閒，會在 enqueue 裡直接派送）。

相機最後：tag 版 ON（`75b02a9b…`），FCAP 生效，29.97p。
