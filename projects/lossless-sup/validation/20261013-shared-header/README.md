# 2026-10-13: release baseline and the "staged trailer" step (rejected)

Working rule (the user's): start from the release build v0.2.0test (`ad984ce6…`) and change one item at a time. Each step is compared on the camera against the previous one, and the next step starts only if this one is an improvement. The user set the order as "先做2 在做1" (do 2 first, then 1):

1. Item 2: find out why the writer task is about 5 points higher with LOSS on.
2. Item 1: the shared header (prepared dual IFD).

## How each measurement was taken

`cpu_take.py LABEL LAYOUT` makes one take on the camera:

- FHD, 59.94p, UHS-II.
- MOVON, then a 2 s `tskmon` window starting at 1 s.
- A stop pulse at 4 s.
- It saves the task table, the LOSS hold counters and the stock record log.

It writes no LOSS state. All builds measured here are plain builds without diagnostics.

## Results

| Build | Total CPU | CamSch | MRecMgr | SRecFile (writer task) | FPLCODE |
|---|---|---|---|---|---|
| Release, LOSS off (`cpu-base-fhd60-off`) | 76.6 | 43.3 | 13.4 | 3.7 | — |
| Release, LOSS on, 3 takes (`cpu-base-fhd60*`) | 91.3 / 89.5 / 90.5 | 46.3 / 43.8 / 43.8 | 15.2 / 15.2 / 15.8 | **8.7 / 8.9 / 9.2** | 6.1 / 6.4 / 6.1 |
| Step 2: staged trailer, 3 takes (`cpu-step2-fhd60*`) | 94.7 / 93.1 / 92.8 | 47.3 / 43.7 / 44.4 | 15.3 / 16.3 / 16.2 | **12.4 / 13.2 / 12.5** | 5.6 / 5.3 / 5.2 |

Every LOSS-on take compressed every frame it held: 182 to 198 frames in about 3 s.

Step 2 used the staged path for all 189 trailers (`flush.trailer_cached` = 189, `flush.trailer_direct` = 0).

## Conclusions

**Item 2.** In the release, `fpl_flush_before` (`flush_site.c`) rewrites the trailer inside the writer task SRecFile. It calls `fpl_trailer_write_all`, which reads and writes the DNG one word at a time through the uncached file. So the extra ~5 points in the writer task (8.9 vs 3.7) are the trailer.

**Step 2 (rejected).** I swapped in the staged `fpl_trailer_write_cached` (the "字組化" trailer from the work snapshot) without changing the architecture:

- the trailer stays in the writer task;
- the 4 KiB scratch lives in `fpl_flush_stats`.

The writer task went **up by about 3.8 points** instead of down. The staged version reads the whole source IFD and writes the whole new tail, while the release version only touches what it changes. The "70% saving" from the snapshot was measured with a different architecture (trailer done before enqueue) and does not carry over.

The change is reverted: `fpSup/lossless` equals the release again and rebuilds to `ad984ce6…`. The candidate is kept as `step2-candidate/` (`22c17f07…`).

**Next step: item 1, the shared header.** It removes the trailer from the writer task altogether: at completion only the tile tables and the root pointer are written.

## Camera notes

- Restoring the release once hit an echo timeout on `fl del`; the old 10LOSS.BIN had in fact been deleted. I did not resend. I listed `\fpSup` to confirm, then wrote the release again and deploy_v3 verified it.
- `\fpSup` contains **`05STOPFX.BIN`** (316 B). I had said it was missing; that was wrong, because my earlier listing showed only the last 15 lines.
- Camera now: release `ad984ce6…`, FHD 59.94p, LOSS on, UHS-II.

## 補記：第 2 項的計時，以及更根本的原因（同日）

- 計時版（`timed-release/`，`37b07b02…`）：writer hook 199 次，套用 196 次，套用時平均 **1,177.5 µs**／幀，最長 3.5 ms。約佔 7% CPU（59.94p）。
- 後續發現 LOSS 整塊（程式＋狀態）位在 loader 的非快取記憶體，每條指令都從 DRAM 取。改成從快取別名執行後，
  trailer 降到 394 µs，總 CPU 90.4 → 85.7。step 2 變慢也是這個原因（指令數翻倍）。
  詳見 [20261013-cached-alias](../20261013-cached-alias/README.md)。共用檔頭順延為下一步。
