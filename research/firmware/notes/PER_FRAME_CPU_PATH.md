# 錄影時每幀的 CPU 工作：CamSch 是每幀排程器(2026-10-16，離線)

只讀 `out/seg0_c0000000.bin`。沒有相機 I/O。[靜] = 反組譯直接看到；[推] = 推論；[量] = 引用既有量測。

## 0. 先看既有量測(不重做)

| 來源 | 數字 |
|---|---|
| `projects/lossless-sup/validation/20261015-camsch` [量] | FHD 29.97p:CamSch **6.0%**；59.94p:**14–16%**；LOSS 程式**沒有**跑在 CamSch 裡 |
| 換算 [推] | CamSch ≈ **2.0 ms/幀 @30p、2.4–2.7 ms/幀 @60p** → 大致與幀率成正比，是原廠每幀成本最大的一塊 |
| 記憶 mrecmgr-per-frame-cost [量] | MRecMgr 邊際約 0.12 ms/幀；未歸屬的「其他」約 0.22 ms/幀(來源未知) |
| 同上 [量] | 原廠 enqueue `C037DD50`:LOSS ON 約 308 µs、OFF 約 113 µs，原因未查 |

⚠ 10/12 量到的 CamSch 44–48%(`20261012-early-dng-handoff`)跟上面差很多。同日的紀錄顯示不同開機之間 CamSch 會差 3–8 點，但仍解釋不了這麼大的差距，需要用同一次開機重量。

## 1. CamSch 的結構 [靜]

- 任務 = XC_Thread id 0x0D，建構在 `C0207AD0`。Runnable vtable 是 `C090EF54`，run 方法 `C02070D0` 進到主迴圈 `C0207620`(`CameraMgrScheduler.cpp`)。
- `C02074B0` 透過 `C0321508` 註冊到每幀回呼表 `0xC343B474`(IRQ 0x79 那條路)，每幀設一個 event flag。主迴圈用 `C036D818` 等這個 flag(timeout −1)，**是事件驅動，不是輪詢**。
- 每次醒來會掃 **9 個 job 槽**(物件在 `+0x18` 起，每槽 0x14 bytes)。由 `C02072B8(sched, job, slot)` 註冊，job 的 vtable+0xC 就是要跑的工作。
- 每槽有一張週期表：`C090F0AC + slot*64`；當 `C0126010()>0` 時改用 `C090F2EC + slot*64`。
  - 表的格式：`{off, sel, 7 組 (period, phase) 依模式 0..6}`。
  - 執行條件：period==1 每次都跑；period>1 則要 `counter % period == phase+off`。另外 `sel` 要等於 `C0125870()`。
  - `C0125870()` 是硬體子幀計數 `0x30100588 & 0x7FF`(讀兩次直到一致)。`C0126010()` 是 `0x30100048` 的 bits 16–26 [推：每個輸出幀包含幾個感光元件子幀]。
- 模式 `[sched+4]` 由 `C02073B8` 設定：幾乎都是 1(運作)或 6(停止)。

### 模式 1 時各槽頻率(表 `C090F0AC`)

| 槽 | 模組(依附近 assert 檔名 [推]) | 模式 1 週期 |
|---|---|---|
| 0、1 | AeTag / AeFlckComparison(`C022B414` / `C022B4A8`) | 每幀 / 每幀 |
| 2 | AeDevCtrl(`C020A36C`) | 每幀 |
| 3 | AwbMgr(`C02AB8F4`) | 每 3 幀 |
| 4、5 | StrbMgr GvCalculator(`C02B9B90` 等) | 每幀 / 每 3 幀 |
| 6 | `C0206E40` 註冊(CameraMgrScheduler 檔區) | 每幀 |
| 7 | **CameraMgrDebugObs**(vtable `C090F678`，run `C02080C8`) | 每幀，但只有設定 +0x354≠0(除錯模式)時才會註冊 → 不是槓桿 |
| 8 | StrbMgr | 每 9 幀 |

另一張表(`C090F2EC`，高子幀數時用)靠 `sel` 讓 job 只在特定子幀跑。也就是說，**原廠在高格率時已經有做降頻**；但一般模式下 AE 類 job 每幀都跑。

## 2. 現成的量測工具 [靜，未上機]

原廠 shell 的 `cam` 指令(handler `C03DB748`)有 `start / stop / ls / le`(說明文字："camera scheduler start log / end log"，輸出格式 `%6d : %5lu ms`)。
主迴圈每個 job 前後都會呼叫 `C0207F58`：開啟 log 時，用計時器 `C002B940` 把各槽的耗時記到 `log+0x32D0[(幀*9+槽)*2]`。
**這就是 CamSch 的每槽 profiler，不必自己寫。** 上機只要 `cam ls` → 錄 2 秒 → `cam le`，就能知道是哪個槽在吃時間。單位與輸出格式要上機確認。

## 3. 排除的嫌疑 [靜]

- 「≥10 KB 就整個快取清除」的包裝 `C0500A68` / `C0500AA8`：呼叫者全在 `ptpcmd`(PTP vendor 指令)，**不在錄影路徑上**。只有 USB 連線傳輸時才相關。
- 整快取清除 `C000E91C` 的其他呼叫者：靜止 JPEG Exif(`XC_StillFileFormatExifTHJpeg` 的 vtable)、Cinemagraph、CinemaDNG **播放**、鏡頭資料、MovRec/StillRec 一次性路徑(`C0386EB0`)。
  直接 BL 呼叫圖裡**沒看到每個錄影幀都會走到的整快取清除**。限制：虛擬呼叫(blx rN)沒有展開。

## 4. 可優化候選

| # | 改法 | 預估收益 | 風險 | 上機要驗什麼 |
|---|---|---|---|---|
| A | **調整 CamSch 週期表**(`C090F0AC` 是資料，執行期在 RAM)：在 ≥59.94p 時把 AE 類槽 0/1/2/6 從每幀改成每 2 幀 | 若這幾槽佔 CamSch 大半，60p 約可省 1–1.3 ms/幀 ≈ **6–8 點 CPU** [推] | AE、防閃爍的收斂變慢，每 2 幀更新一次 = 30p 時的反應速度；跨幀狀態機可能假設每幀都會被呼叫 | 先用 `cam ls/le` 拿到各槽耗時；改表後錄 60p，看曝光有沒有閃爍、AE 追不追得上 |
| B | 槽 4(Strobe GV)在錄影時每幀跑 | 未知 | 錄影時理應不需要閃光燈計算 [推] | 同上，先看它實際耗時多少 |
| C | 原廠 enqueue `C037DD50` 在 LOSS ON 時多出約 195 µs/幀 | 60p 約 1.2 點 | 低(只是查原因) | 逐段計時，確認是不是 enqueue 裡直接派送給 writer |
| D | 未歸屬的 0.22 ms/幀 | 60p 約 1.3 點 | — | 推測是 IRQ 時間被算到被打斷的任務頭上；要用 PC 取樣 profiler 看(`PC_SAMPLER_HOOKPOINTS.md`) |

⚠ A 會改原廠的行為(曝光更新頻率)，依 [改設計前先問] 原則，**要使用者同意才能做**；這只動 RAM，不碰設定區。

重現：`python3 armdis.py c0207620 478`(CamSch 主迴圈)；週期表的傾印腳本附在本次 scratchpad 的 perf/ 目錄，邏輯就是第 1 節。
