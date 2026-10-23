# Stop hang with expanded slots: static analysis (2026-10-13)

Source: static analysis of the decompilation (`out/decomp/full/blk_c03.c`) plus a capstone disassembly of `MAIN_c0000000.bin`, done by a subagent.
Nothing here has been confirmed on the camera yet. The patch words are unbuilt and have not been emulated.

Observed: HS280 119.88p for 4 s on a card that fell back to UHS-I (87 MB/s). With expanded slots (560), the stop hung:
- LOSS 440, writer 434, finished 398;
- control take with the gate off: 456 / 449 / 398.

On UHS-II (241 MB/s) the same take finished 442/442.

## Mechanism (inferred)

**Counters and batch flush**
- `req_cnt` (`_DAT_c359be68`) is incremented by C03A59A8 inside the per-file write C03A5348, which runs in the writer `XC_StillCreateFile::v4` (C037E0F8).
- `fin_cnt` (`_DAT_c359bea0`) is incremented by C03A59E8, called from the SD batch completion callback C03A55D0.
- The partial batch is flushed by `C03A5190(bulk,0)` and the full close is `C03A5190(bulk,1)`. Both are called only from C0398D88, which is gated by `C0376300(mgr,session)`:
  - 0: a frame is still in the raw/yuv stages;
  - 1: a frame is in state **0xB** (handed to the writer but not requested);
  - 2: only 0xC/0xD frames remain, so flush;
  - 3: nothing remains, so finalize.
- C0398D88 is re-run only from the event 8/9 handler C038C058 (at C038C288). There is no timer.

**How frames get stranded**
- C037DD50 pops a frame, sets byte0 = 1 and +0x1C = id, then calls C0377008.
- C0377008 needs a message ticket from `MPoolFixed<8,128>` at 0xC35202B4 (pointer at [0xC2F1F3D4], free count at +0x18).
- When the pool is empty it logs "lack TSC" and returns 0. No caller checks this, so the frame stays in 0xB and is in no queue.

**Why tickets run out**
- C037DF40 (events 8 and 9) re-dispatches the writer through C0376F20 without checking that +0x1C is the finishing frame. While there is a backlog, the writer is therefore dispatched twice per frame.
- At 131 MB/s in and 87 MB/s out, the backlog passes 128 tickets in about 3 s.
- Stock firmware never reaches this, because admission (C0374268) caps live frames at about 94.

**Why the stop hangs**
- The 0xB orphans make C0376300 return 1, so the flush never runs and fin_cnt stops at 398.
- No further events arrive, so C0398D88 is never re-run.
- MRecMgr waits on its mailbox, CamSch waits on flag 55, and the XMP object at C358E140 is never closed.

## Stock overflow stop

C0374268 refuses admission when free ≤ 1 (the "vbuf" path). Error branch C038BD98 then:
1. releases the failed frame;
2. runs `C037DD08(); C037DEE0()` to purge the writer queue;
3. calls cDevt_stop.

This never hangs, because ≤94 live frames always stay under 128 tickets.

## Fix options, safest first

1. **(d) No double dispatch.** On event 9, re-dispatch the writer only if creator+0x1C is -1 or equals the finishing id; otherwise only release (C037E008).
   - It can be patched in place at C037DF50..C037DF88 (the 15-word debug-log block), or only for CinemaDNG through a cave stub on the call at C038C1E8 (stock word EBFFC754).
   - File contents are unchanged. It needs an emulation check of the event-9 error path.
2. **(b) Safety limit.** Refuse admission through the stock vbuf path when live or 0xB frames reach about 110, to stay under the 128 tickets. Add this on top of (d).
3. **(c′) Larger ticket pool.** Needs its own vtable, because the 128 bound is hard-coded. Second choice.
4. **Rejected:**
   - treating 0xB as result 2, because the batch is turned off while files are still pending;
   - re-queuing orphans, because it is racy.

## Camera reads to confirm (read-only)

1. Ticket free count `u32 @ 0xC35202B4+0x18`: 128 when idle, 0 if this is the cause.
2. Search the system log for "lack TSC".
3. Count registry frames with 0x1104 == 0xB, byte0 == 1, not equal to the writer's +0x1C (`0xC3520268+0x1C`) and not in the writer queue. Expect 6 in the first take and 7 in the second.

## Separate finding

C0398D18 (mode-exit cleanup) releases only ids 0..0x5F (`cmp r4,#0x60` at C0398D7C). It is not in `slot_sites.json`, so ids ≥ 96 leak on that path.

## 上機證實與修正（2026-10-13 下午）

- 第二次卡死（M12 第一版修正，慢複製造成積壓→`vbuf/558` 自停）當下讀取：擴充 registry 113 幀，**99 幀 0x1104 = 0xB 且 byte0 = 1**
  （已被寫入器取出、不在任何佇列）、14 幀 0xC；寫入器 `0xC3520268+0x1C = −1`（閒置）、佇列空；票池事後已回到 128。
  與上面推論的「重複派送 → 票用完 → C0377008 丟棄 → 0xB 孤兒 → C0376300 回 1 → 永不 flush」一致。
  原始資料：`../20261013-m12-source/stuck-registry-walk.txt`。
- 修正 (d) 已實作於擴充槽建置：`native/slot_sites.json` 的 `writer_guard`（15 word，C037DF50..C037DF88，原 C037DF40 的除錯紀錄區），
  由 `slot_patches.py` 產生獨佔宣告與寫入；開機時逐 word 驗證原廠值，關機由 loader 還原。副作用：該除錯紀錄（tag 0x66006600）不再輸出。
- 驗證（Unicorn 執行真韌體）：`test_writer_completion_redispatches_only_for_its_active_frame`（非 active 幀完成：只釋放、不派送、回 1；
  active 幀／寫入器閒置／event 8：照原廠），`test_mutation_stock_writer_completion_dispatches_twice`（原廠字確實重複派送）。整合 80 項 OK。
- 尚未上機。安全限制 (b) 未實作：有 (d) 後積壓只受 RAM 限制，RAM 用完時走原廠 vbuf 停錄（清寫入器佇列→收尾）；此路徑在擴充槽版尚未上機驗證。
