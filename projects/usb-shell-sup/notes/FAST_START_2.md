# Fast Start 2 — fast start and instant start, technical notes

2026-09-26. SIGMA fp firmware Ver.5.02 only; every address below is meaningful for that image alone.

Fast Start 2 gives one card three boot paths. A power-switch restart loads the payload
**~1.3–1.4 s after power-on without running the AutoRun** (instant). A cold start copies the
loader out of the settings block instead of spelling it out (fast). The first boot, or a
fingerprint mismatch, spells it out and stores it (slow). All three paths end in the same
loader and the same stage2.

Build flags: `--store-boot --loader-hook --four-box-bar` in one `build_autorun.py` run. The
fpSup-Merge page exposes this as the off-by-default **Fast Start 2** switch. Single-product
releases never carry it (`release_card.py` refuses a card with the abort).

Sources: `LOADER_V2.md` (design, camera log, the open case), `AUTORUN_STORE_BOOT.md`
(store-boot, 09-18), `WARM_BOOT_GATE.md` (first loader-hook test), `BOOT_TIMING.md`,
`fpSup/HOOKS_AT_POWER_OFF.md`, `fpSup/fp_usb_shell/asm/{loader,stage2,store_boot}.S`,
skill `fp-merged-card`.

---

## 1. The three paths

| path | taken when | what the screen shows | `LOAD_DONE_US` @ `0xC072F6F8` |
|---|---|---|---|
| **instant** | power-switch restart, USB unplugged, firmware image kept in DRAM | no progress bar; four-box screen at ~3 s, holds 2 s, native UI returns | ~1.3–1.5 s (measured 1.322, 1.356, 1.391, 1.402 s) |
| **fast** | image reloaded: cold start, battery pull, **USB attached at power-off**, some unplugged restarts anyway | boxes fill one by one, short script (~26 commands executed) | ~11–12 s |
| **slow** | first boot, or the stored loader's magic does not match this card | long progress; full script (148 commands in the FS2 AutoRun) | ~15–16 s |

For comparison, an ordinary `--loader` card runs a 112-command AutoRun on every boot. The
camera's own boot before the AutoRun is ~8.9 s; reading `fpSup.BIN` and placing sections
takes 3.5 ms.

Telling instant from fast by eye: both show boxes. Fast **fills them one by one**; instant
makes them appear already finished.

## 2. Why instant works: a power-switch restart is warm

Measured 2026-09-17 with 128 address-derived markers in an 8 MB allocation, and again on
2026-09-25 with the og patches (memory `warm-restart-keeps-the-cave`):

| region | after the power switch | after a battery pull |
|---|---|---|
| firmware image + cave `0xC0000000..0xC2F30800` | **kept**: patches, cave code, cave words (og: 30/30 patched words still present) | reloaded from NAND |
| BSS `0xC3000000..0xC38D6FB0` | zeroed: registrations, pool pointer `0xC3757A7C` | zeroed |
| heap above BSS | 128/128 markers kept | 0/128 (`FFFFFFFF`) |
| heap / pool allocations | allocator starts over, addresses differ | — |

Retention also held after 5 and 10 min off; at 25 min everything was gone. The edge between
10 and 25 min is steep and not pinned down.

Whether the image is kept is decided by the IPL, not by us. **Plugged USB at power-off always
gives a cold start.** Unplugged restarts fell back to cold 10–30 % of the time one afternoon and
far more on another; the cause is unknown.

## 3. The loader hook (instant path)

### 3.1 The site

Static read of `out/MAIN_c0000000.bin`:

```
0xC03DA3F8  push {r4,r5,lr}               ; XC_ShellScriptAutoRun virtual
            ldrb r3,[r1] ; ldrb r2,[r1,#3] ; tst r2,r3 ; beq  (no AutoRun this time)
0xC03DA414  movw/movt r0, 0xC0BABDD8      ; "\AutoRun.txt"
0xC03DA41C  mov  r1, #1
0xC03DA420  bl   0xC03DA758               ; ★ stock word 0xEB0000CC — starts the AutoRun
0xC03DA424  mov  r2, #0                   ; return value ignored
```

This is the only call that starts the AutoRun. At this point the firmware has already decided
to run a script and is about to open a file and allocate a context here. File I/O and
allocation are therefore legal at this point, which is not true of an arbitrary hook.

### 3.2 What stage2 writes

stage2 (`#ifdef LOADER_HOOK`) replaces `0xC03DA420` with `bl LOADER_BASE+4` (`LH_BL`, encoded
at build time), and only when all of these hold:

1. The power-off callback registered (`r9 != 0` after `lh_setup`; see §5). **No callback → no
   hook**, rule carried over from `HOOKS_AT_POWER_OFF.md`.
2. The word at the loader's `+4` (`LH_ENTRY_AT`) equals `LH_ENTRY_WORD`, the `b lhook` this
   build expects. A loader left in the cave by another card's cold boot fails this check.
   The next boot then simply runs the AutoRun.

It then publishes the caches (`s2_publish`: D-cache `0xC000E91C`, I-cache `0xC000EABC`).

`0xC03DA420` is **not journaled**. It is the one patch meant to outlive the boot.

### 3.3 `lhook` (loader `+4`)

```
lhook:  push {r0,r1,r4,lr}          ; the AutoRun's two arguments
        mov r4,sp ; bic sp,sp,#7    ; caller pushed 3 words: realign to 8 (ARM rule)
        bl  load                    ; same load as every other path
        mov sp,r4
        cmp r0,#0
        pop {r0,r1,r4,lr}
        movne r0,#0 ; bxne lr       ; loaded → return; the AutoRun never starts
        JUMP AR_START               ; 0xC03DA758 with the original r0/r1 and lr
```

`load` returns 1 or 0. It returns 0 when there is no file, the file is not `VBIN`, or the card
comes from somewhere else. In that case the firmware's own call is completed as a tail jump,
and that card's AutoRun takes over. A blank card, or a card without `fpSup.BIN`, therefore
boots normally.

The loader lives at `CAVE_LOW 0xC072DE64`. Its `CALL` macro is baked to that address, so it
cannot move.

## 4. The settings-block store (fast path)

### 4.1 Where

`XC_CommonSaveData` @ `0xC307523C`, 0x410 bytes, flash-backed. The firmware writes it back
without any save command. Measured 2026-09-17: 206 of 207 words survived a power cycle. The
exception is a u16 at `+0x024` that the firmware owns. The store therefore starts past it:

```
STORE = 0xC3075264            ; 0xC307523C + 0x28
  +0x00  magic   sha256(loader bytes)[0:4]   ; baked into the card as STORE_MAGIC
  +0x04  body    the loader, verbatim        ; STORE_LEN baked in, never read from the store
contiguous usable: 468 B (0xC3075268..0xC307543C); the loader is 468 B — no room left
```

Two more fragments exist (`+0x210..+0x280` 112 B, `+0x290..+0x380` 240 B) if the loader ever
has to grow. `build_autorun.py` exits instead of emitting a loader that does not fit.

### 4.2 `store_boot.S` (26 words at `BOOT_AT 0xC072F700`)

It runs as the borrowed `echo` handler `(ctx, argc, argv)`:

1. `[STORE] == STORE_MAGIC`? If not, return 0 and touch nothing: the script carries on down the
   slow path.
2. Copy `STORE_LEN` bytes from `STORE+4` to `CAVE_LOW`.
3. D-cache and I-cache publish.
4. Tail-jump to the loader in the echo handler's context.

It must not live at `CAVE_LOW`: the first draft copied the loader over itself mid-loop.

**Why the magic is a hash.** It is `sha256(loader)[0:4]`, computed by the build. Change the
loader by one instruction and the magic changes, so the store stops matching and the card
re-seeds. A hand-bumped string (`'fpLD'` → `'fpL2'`) went stale four times in one night.
The reference comes from the card, never from the store, so a self-consistent store cannot
pass. It identifies the loader build only. It is not an integrity check of the stored body
or of `fpSup.BIN`. A compatible payload update can therefore replace `fpSup.BIN` alone.

**Why a half-written store is safe.** stage2 (`#ifdef STORE_PROVISION`) writes the body first
and the magic last. If the stored magic already equals this build's, it leaves flash alone.

### 4.3 Stopping the rest of the script (`ARM_ABORT`)

On the fast path the loader has already loaded everything, but the interpreter would still
read the remaining ~120 commands. stage2 redirects the `echo` slot to an abort routine. It does
this only if a live AutoRun registration exists. It scans the table at `0xC2F20FC0` (depth at
`+0x21C`, 36-byte entries) for the per-line callback `0xC03DA7A8`. A depth > 15 is treated as
a garbage table, since the image holds `0x38357C54` there. The instant path starts no script,
so it arms nothing. The next `echo`
line pops the registration and clears `[ctx+0x90]`, and the interpreter stops.

**The pop is owed.** The completion callback `0xC03DA700` skips its own
`bl 0xC0420D90` (pop, depth −1) when `[ctx+0x90] == 0`. Clearing the byte without popping
left the depth above 0, and the camera believed a script was still running. Only shell cards
died of it: the worker was alive but could not answer (`ERR shl frame0 moved=0/64`). Rule:
whoever clears that byte owes the pop (memory `autorun-abort-owes-a-pop`).

One `echo` line serves both paths. On the fast path it is the abort point; on the slow path
the store check fails once more and the script continues. AutoRun has no conditionals, so this
is the only way to express the branch.

## 5. Power-off write-back (`LH_RESTORE`, every `--loader` card)

Instant boot means the previous boot's patches are still in the image. Without write-back,
a hook pointing into last boot's pool is a dangling branch: that is the gyro v1.13 freeze in
`HOOKS_AT_POWER_OFF.md`. So every `--loader` card, not only Fast Start 2, journals and restores.

### 5.1 Setup, before any section is placed

`lh_setup` sizes a block from the section table: code, a 16-byte header, and 8 B plus the data
per journaled section, and 12 B more with the splash. It gets the block from the allocator
(class 0, `MEM_HEAP 0xC001CF78` / `MEM_GET 0xC001D038`, never freed):

```
X+0   X-8          vtable pointer; the manager calls [vtbl+0xC] = [X+4]
X+4   X+12         the routine
X+8   journal      where entries start
X+12  lh_unhook    copied here, position-independent (movw/movt only, no literal pool)
...   journal:     { address, bytes, original words... }..., 0
```

It registers the block on **both** power-off lists: `POFF_MGR 0xC0023A98`, then
`POFF_ADD 0xC0024118(mgr, obj, forced)` with forced = 0 and forced = 1. The manager runs the
forced list instead of the ordinary one on its fast path. The unhook may therefore run twice,
and writing an original word back twice is harmless. If the allocation or registration fails,
nothing is journaled and no hook is armed.

### 5.2 What gets journaled

`lh_want`: a destination is journaled if it is ≥ `0x40000000` (an absolute firmware address)
and outside the cave `0xC072D000..0xC0735000`. The cave holds hook bodies and the loader, not
hook sites. Writing it back at power-off, while the firmware may still branch into it, is the
wrong order. Once the sites are stock, nothing reaches the cave anyway.

`lh_record` copies the original words just before `s2_place` writes the section. Order: data,
then the new terminator, then the length, and the address last. A power-off mid-record sees
either the old journal or the new one, never half an entry. Hooks installed later by a
payload's entry go through the same record-then-write path (gyro's four hook sites are declared
as sections; its own `poff_disarm` is gone).

### 5.3 Measured

og3k writes 55 runs, ~4 KB, and its journal is ~14 KB. After the unhook ran twice, the next
boot recorded 7 original words, all equal to stock. On the three-way card, after a fast boot,
the journal read back **63/63 equal to the stock image**.

## 6. The four-box screen (`--four-box-bar`)

The instant path skips the AutoRun, so there is no progress bar or banner, and the user cannot
tell loading finished. Drawing at 1.35 s works, but the native UI repaints over it 0.2 s later
(`NORMAL OSD DISP` at 1.561 s). So the instant path waits:

1. Wait until `F_TICK_US 0xC002B6E0` ≥ 3 s (`LH_BANNER_AT_US`).
2. Journal the draw routine's first word, then pause redraw: `0xC0528700` ← `bx lr` (`0xE12FFF1E`).
3. `display osdfile` handler `0xC03E4270`, called directly without the shell dispatcher:
   `\FPSUPUI\0.BIN`, 1024×56, three times.
4. `splash_finish`: `4.BIN`, hold 2 s, restore the draw word, force a full redraw.

If redraw is already paused, the AutoRun did it, which means this is a script path and the
step is not repeated. The instant path does not clear the layer first: clearing it erased the
UI icons. The card needs the `FPSUPUI/` folder (`0.BIN`..`4.BIN`) next to the two files;
`putfile` does not create folders.

## 7. Boot flows, end to end

```
cold start / image reloaded
  0xC03DA420 stock → AutoRun
    ├─ store magic matches   → store_boot copies loader → load → stage2 → abort   (fast)
    └─ no match              → mem set ×N spells loader  → load → stage2
                               → STORE_PROVISION writes body, then magic         (slow)
  stage2 (every path): lh_setup → place sections, journal each → entries
                       → [LOADER_HOOK] arm 0xC03DA420 = bl loader+4

power-switch restart, image kept
  0xC03DA420 → lhook → load → stage2 (same as above, re-arms the hook) → return 0  (instant)
        load failed → b 0xC03DA758: that card's AutoRun runs

power-off
  PowerOffMgr → lh_unhook: journal written back in reverse; caches published
  image left = stock + loader in cave + 0xC03DA420 hook
```

## 8. Reading back which path a boot took

- A `--loader-hook-mark 0xC072E040` build plus `python3 -B loader_hook_check.py` reports:
  - whether the hook is armed or stock;
  - the journal entries compared against the stock image;
  - power-off runs since the image was last reloaded;
  - `LOAD_DONE_US`.
- `runs` survives only a warm restart. A fast boot with `runs=0` means the image was reloaded
  **or** the power-off never ran; it is not proof on its own. A canary word written from the
  shell is.
- To see the instant path, power off with the **USB cable unplugged** and plug in only after
  boot to read.
- **Recovery card:** only an `AutoRun.txt` containing `mem set 0xC03DA420 0xEB0000CC`, with
  **no `fpSup.BIN`**. With a BIN present, the hook loads it and the AutoRun never runs. See
  `cards/warm-boot-2026-09-25/fpsup-loader-hook-1/recovery-noBIN/`.

## 9. Rules

- **One build owns every piece.** `store_boot`, the provisioning stage2, the abort, the magic
  and the `+4` entry word must all come from one `--store-boot --loader-hook` run. Mixed from
  two builds, they disagree at boot, and there is no shell to recover with.
- **Never feed an already-Fast card back into the merger.** Compose ordinary cards, then enable
  Fast on the final output.
- **The settings block is the only persistent write.** It survives a battery pull and deleting
  `AutoRun.txt`, which is why it is opt-in. A menu settings reset *should* clear it; this is
  untested.
- A payload update that keeps the same loader and packaging needs only a new `fpSup.BIN`.
  Keep the banner, and `AutoRun.txt` stays byte-identical. A changed loader, filename, Fast
  configuration or boot contract means `AutoRun.txt` and `fpSup.BIN` change together once.

## 10. Open issues

1. **⏸ Residual patch recorded as "original" (user deferred, 2026-09-25).** If a power-off
   callback did not run (crash, pulled power), the patch is still in the image on the next
   warm boot. stage2 records what memory holds, so it journals the patch as the original,
   restores it at power-off, and it persists until a cold start.
   - og3k: harmless (it points into og code in the image).
   - gyro: the leftover is a `bl` into **last boot's pool**; firing before 1.4 s can crash.

   Three candidate fixes, none implemented:
   1. declare gyro sites twice;
   2. a "this is stock" flag bit on a section;
   3. build-time stock words for every firmware section, from the reference image, costing ~4 KB for og3k.

   Do not pick one without the user.
2. Unplugged warm restarts sometimes come up cold; the rate varies by day, cause unknown (IPL).
3. Whether a hot card insert re-triggers `0xC03DA3F8`, and so the hook, is unverified.
4. The exact retention limit when powered off is between 10 and 25 min.
5. A settings reset from the menu clearing the store is untested.
