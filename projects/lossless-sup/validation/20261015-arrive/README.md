# 2026-10-15 MRecMgr 的 arrive 細分（診斷版，FHD 29.97p，2 段）

預開已還原（程式在 `../20261015-preopen/preopen-source/`），一般建置 = `4057e2ae…`。
診斷版 `--time-hooks` 新增 frame_hold 分段計時（`FPL_DIAG_HOOK_TIME` 才編入；一般建置不變）。`arrive-*.json`：

| 每幀（MRecMgr） | µs |
|---|---|
| arrive 全部 | 570–573 |
| collect（交還上一幀） | 553–560 |
| └ 檔頭 DMA 0x15400 B（`C00FBB90`，換緩衝） | 237–247 |
| └ 原廠 enqueue `C037DD50` | 297–300 |
| take（接手新幀） | 11–12 |
| 第 1 幀（原廠路徑）的 enqueue | 481–502 |

**這些時間大多是等待，不是 CPU**：arrive 570 µs × 30 幀 ≈ 17 ms/s（1.7%），但 tskmon 的 MRecMgr ON 2.5%、OFF 2.2–2.4%
（`../20261015-camsch`），LOSS 在 MRecMgr 實際多用約 0.2 點。DMA 與 enqueue 內部的等待不算 CPU。

結論：MRecMgr 沒有值得省的 CPU；LOSS 在 29.97p 的約 1.5 點主要是 FPLCODE（每幀 open 170 µs＋收尾約 80 µs），open 已確認省不掉。
相機換回 `../20261015-nosync/deploy-on`（`420c231f…` ON）。
