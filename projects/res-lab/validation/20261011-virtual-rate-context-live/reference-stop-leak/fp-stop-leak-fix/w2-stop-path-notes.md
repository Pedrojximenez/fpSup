# W2: overflow / vbuf stop leaks descriptors and RAW — independent trace and fix design (2026-10-09)

Status: **design only. Nothing built, nothing run.** Confirms bei's diagnosis (opengate/HSW_DEVELOPMENT_STATUS.md
§7.3, §8.3) from our own disassembly of FW 5.02 and adds the mechanism. Needs coordination with bei
(the user decides) and camera tests (the user's permission).

## What the code does (llvm-objdump of our decoded image)

| function | what it is |
|---|---|
| `FUN_c0381008(q)` | locked pop-front of a request queue; next-link at node+0x110C; returns node or 0 |
| `FUN_c0381090(q,n)` | locked push-back |
| **`FUN_c0377118(obj)`** | `while (pop(obj+16)) ;` — **drops every queued node, returns nothing**; then returns 1 |
| `FUN_c0374220()` | request-manager singleton getter |
| `FUN_c0375030(mgr,id)` | **ref-counted release by id**: if mgr+0x190 (busy) → defer; node=lookup(id) (`0xC03753C0`), none → return; if node+0x1118 (parent id) ≠ −1: free(id) (`0xC03768D8`), parent+0x1110 (refcount) −1, at 0 free(parent+0x10FC); else free(id) when its refcount is 0 |

Node layout (pool `MPoolFixed<4380,96>` @ 0xC2F1F3D8, stride 0x1128, free count at +0x112C):
+0x10FC id, +0x110C queue link, +0x1110 refcount, +0x1118 parent id (−1 = top level).

Stop sequence (e.g. 0xC03840A4…0xC03840F8): for each sub-pipeline: lock, **`FUN_c0377118` flush**, unlock,
then exactly one `FUN_c0375030(mgr, cur->id)` for the current request. Flushed children never decrement
their parent → parents' refcounts never reach 0 → their descriptors and RAW (1,441,792 B each) are
stranded until a battery pull. Measured by bei: 44 × 1,441,792 = 63.4 MB, free count 96 → 52.

## Fix: ONE WORD (traced 2026-10-09)

The firmware already contains the correct flush. Debug-log tags name them:

| function | log tag | body |
|---|---|---|
| `FUN_c0377620` | "raw stop" | ... then `FUN_c0377118(obj)` = pop-and-DROP |
| `FUN_c03776A0` | "raw del" | `mgr = FUN_c0374220(); while (n = pop(obj+16)) FUN_c0375030(mgr, n->id)` = pop-and-RELEASE |

**Patch: 0xC0377118  E92D4030 (push {r4,r5,lr})  ->  EA000160 (b 0xC03776A0)**, i.e. the leaky flush
tail-jumps into the firmware's own releasing flush. Same argument (obj in r0), no stack touched yet.

Why it is safe, each point checked in the disassembly:
1. **Queue obj+16 holds only PENDING nodes.** Submit (0xC03774F0..0xC0377580) pushes a node there only
   when the stage could not start it (0xC037A990 returned 0), and pops it before starting it. So no
   flushed node is under DMA.
2. **Return value unused.** The 12 call sites (0xC0377688, 0xC03840C0/D8, 0xC03841BC, 0xC03842E8/0300,
   0xC038F3F8/410/51C/524, 0xC0398D34/3C) are each followed by an argument-free singleton getter
   (0xC037AED8 / 0xC037D580 / 0xC037DD08 / 0xC0374220 all load their own r0) or by `mov r1,#1; mov r0,r1`.
   Raw del returns 0 where the drop returned 1; nobody reads it.
3. **Double release is a no-op.** lookup `0xC03753C0` = `id<96 ? mgr->slot[id] : 0`; free `0xC03768D8`
   returns at once when `slot[id]==0`, and ends with `slot[id]=0` (0xC0376AEC). So the stop site's own
   release of `cur` after the flush cannot double-free, and a child released twice cannot
   decrement its parent twice.
4. Free notifies all three stages (0xC037B1F0, 0xC037D880, 0xC037E008) to drop the node, returns it to
   the pool (0xC0380580(node,3)), and decrements the in-use count (mgr+0x18C): the full stock path.
5. mgr+0x190 (the "defer" byte) is **never set for the record manager**: across the whole code region
   only four byte-stores hit +0x190; the manager's is its constructor writing 0 (0xC037420C); the
   others (0xC00A507C, 0xC031A0E4, setter 0xC031ABB0 called only from 0xC0313xxx–0xC031Cxxx) belong
   to a different class. So releases are not deferred.

Packaging (when the user and bei agree): a Loader v3 sup that `claim()`s [0xC0377118,4) SL_EXCL with stock
E92D4030, writes EA000160, `publish()`es, returns SL_KEEP; power-off write-back restores stock.

## Test protocol (needs the user's go-ahead; SD-only, no SSD first)
- Read pool free count (0xC2F1F3D8+0x112C) and RAW used, via the USB shell, before/after.
- Stock: provoke an overflow stop (SD, high-rate format) → expect 96 → ~52 (reproduce bei).
- Patched: same → expect back to 96 and RAW used unchanged; repeat start/stop 10× with no drift.
- Then SSD with a forced stall (stall-injection C5) to see whether USB/MscHost survives.

## Cross-check with Ghidra's decompiler (2026-10-09, F:\Claude\SigmaFP\work\decomp\*.c)
Independent second read; matches the hand trace line for line:
- `FUN_c0377118`: `do { n = FUN_c0381008(obj+0x10); } while (n); return 1;`
- `FUN_c03776a0` ("raw del"): pop loop with `FUN_c0375030(FUN_c0374220(), *(n+0x10fc))`.
- `FUN_c0375030`: skips when mgr+400 (0x190) set; child → free(id) + parent refcount−1 → free(parent);
  top-level → free only when refcount 0.
- `FUN_c03768d8` (free): under the manager lock; returns early if `slot[id]==0`; calls release(3) on the
  node's three attached objects (+0x13C..+0x148 — the RAW/strip buffers), tells raw/stage2/stage3/writer
  (`FUN_c03777b8`, `FUN_c037b1f0`, `FUN_c037d880`, `FUN_c037e008`) to forget it, returns the node to
  the pool (`FUN_c0380580(node,3)`), in-use −1, `slot[id]=0`.
- `FUN_c0377620` ("raw stop") drops its own lock (+0x84) BEFORE calling the flush, so the release's
  manager lock cannot deadlock against it at this site.

## All four stages checked line by line (Ghidra decompiler, 2026-10-09)
The stages are recMgr's create pipeline (asserts name `src/framework/recMgr/src/StillCr…`):
`FUN_c0377390` "cre_raw", `FUN_c037af20` "cre_yuv", `FUN_c037d5c8` "cre_jpg", `FUN_c037dd50` (writer;
busy while obj+0x1C ≠ −1). In every one, a node is `push`ed to obj+0x10 only when the stage cannot start
it, and the node that does get started is `pop`ped first (its byte +0 set to 1). **No queued node has
been started in any stage**, so releasing queued nodes cannot free a buffer under DMA.
The firmware also has a stage-4-specific releasing flush, `FUN_c037dee0` (pop → `FUN_c037e008` forget →
release), called at 0xC0398D44 right after a leaky flush — more evidence that pop-and-release is the
intended semantics and the drop is the bug.

## Built artefact (offline only)
`build/w2/fpSup/05STOPFX.BIN` — 316 B, id `STFX`, sha256 in `build/w2/MANIFEST.txt`.
Made by `tools/build_w2.js` from the repo's unmodified `patch_sup.S` (no relocations; matches
`build_v3.patch_sup()` layout: table at file 0x11C, row {0xC0377118, 4, SL_EXCL, stock, new}).
NOT put on any card. Needs: the user's go-ahead, and ideally bei's review (bei owns the loader rules).
