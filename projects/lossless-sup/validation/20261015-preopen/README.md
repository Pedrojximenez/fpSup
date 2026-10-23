# 2026-10-15 預先開引擎（preopen）：功能正確，但沒有效益

做法：完成一個工作、close 之後立刻完整 open；送引擎時引擎已開就不 open；段落結束／回放前 close。
正式版 `425c17c0…`，診斷版 `1d373663…`（`build-plain`、`build-diag`）。離線：codec_job 38（含 preopen 4 項）、frame_hold、card_emulation、v3 全過。

上機（診斷版 ON，FHD 29.97p，1 段，`diag30-1.json`）：103/103 壓縮、0 拒絕、preopened 103、送引擎時 open 3.1 µs、
停錄後引擎關閉（300D0074 bit0 = 0，release 0）。

**但 MRecMgr 的 arrive 每幀仍約 558 µs（之前 570）。** 雙通道模式下送引擎（`fpl_hold_kick`）與收尾（`check`）本來就在
壓縮任務 FPLCODE（`fpl_lanes_task_wait`），不在 MRecMgr；open 的 170 µs 一直在 FPLCODE。preopen 只在同一任務裡挪位置。
（更正 `../20261015-engine` 與先前回報「送引擎約 260 µs 在 MRecMgr」的說法。）

MRecMgr 的 arrive ≈ 原廠 enqueue ～300 µs（ON 比 OFF 的 ～110 µs 貴，原因未查）＋ collect／handoff／admit ～250 µs（未細分）。

相機已換回 `../20261015-nosync/deploy-on`（`420c231f…` ON）。原始碼的 preopen 待使用者決定是否還原。
