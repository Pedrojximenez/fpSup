---
name: fp-unicorn-emulation
description: Running SIGMA fp card code under unicorn before it goes on the camera — the real loader, stage2 and payload sections against the real firmware image (out/MAIN_c0000000.bin), with the firmware routines they call replaced by Python. Use before any loader/stage2/hook/probe change is written to a card, when a test "passes first time" and needs proving, or when deciding what a camera result means. Covers the harness in fp_usb_shell/test_loader_hook.py, how to stub, what the image does NOT tell you, and the mutation check that proves a test can fail.
---

> **設定區風險（2026-10-04 更新）**：原廠在 loader 前讀取持久設定；
> 不支援的值可能使開機或選單失效，拔卡本身不會清除該值。使用者已指出現在有還原手段，
> 因此不再把這類故障描述成不可恢復。上機前確認會保存的值、可能症狀及適用的還原流程；
> 未確認還原條件時，優先把自訂狀態留在 RAM。240 fps 與 14-bit 的處理不同，
> 詳見 `research/SETTINGS_AREA_FIRST_RULE.md`。
> *(Stock firmware reads persistent settings before the loader. A recovery
> method now exists; check its applicability before a live trial.)*

# Emulating card code before it reaches the camera

A card that is wrong at boot can freeze the camera with no shell left to look
with. Everything below runs on the host in seconds; the camera is for what the
emulator cannot know (timing, the IPL, the UI, real I/O).

## The harness

`fpSup/fp_usb_shell/test_loader_hook.py` — class `Camera` is reusable:

```python
import test_loader_hook as T            # run from fpSup/fp_usb_shell, sys.argv=['x']
loader, binf = T.build(['--store-boot'])            # or read a card: see below
cam = T.Camera(loader, binf)                         # maps image, BSS, heap, stack
cam.call(T.CAVE_LOW + 4, r0=0xC0BABDD8, r1=1,        # the loader hook entry
         lr=T.AR_RET, sp=T.STACK - 0x1004)           # sp 4 off, like the real caller
cam.call(T.CAVE_LOW)                                  # the AutoRun/echo entry
cam.word(addr); cam.calls; cam.draws; cam.registered; cam.ar_started
```

To run a **card on disk** instead of a fresh build, take the loader from its
AutoRun `mem set` lines in `0xC072DE64..+0x200` and the BIN as bytes:

```python
sets = re.findall(r'^mem set (0x\w+) (0x\w+)', text, re.M)
loader = {int(a,16): int(v,16) for a, v in sets if T.CAVE_LOW <= int(a,16) < T.CAVE_LOW+0x200}
```

What `Camera` does: maps `0xC0000000..0xC3000000` from the image, zeroed BSS
`0xC3000000..`, a heap at `0x45000000`, a stack; one `UC_HOOK_CODE` catches
every stubbed address, performs the effect in Python and returns by writing
`pc = lr`. File API reads come from the BIN; `MEM_GET` bumps a heap pointer;
`POFF_ADD` records `(obj, forced)`; `TICK` returns `cam.now`, and `D_SLEEP`
advances it — so a wait loop terminates.

## Stubbing: three rules learned the hard way

1. **Register the stub; do not reassign the method.** `cam._hook = f` after
   construction does nothing — the bound method was already given to unicorn.
   A stub that silently is not there lets the real firmware routine run from
   the image and hands back its garbage (a probe's "return value" read 0 this
   way). Either add the address to `F`/`by_addr` before building `Camera`, or
   write a tiny ARM stub into emulated memory:
   `mu.mem_write(addr, struct.pack('<II', 0xE3A00055, 0xE12FFF1E))  # mov r0,#0x55; bx lr`.
2. **Stub through the path the code really uses.** stage2 calls non-cache
   routines through r3/r7/r8, not ip, because `verify_stage2_cache_publish`
   counts every `movw/movt/blx ip`. A stub keyed on the address works either
   way; a check keyed on the instruction pattern does not.
3. **Fail loudly on anything unmocked.** `test_splash.ArmHarness` raises on
   execution outside staging/loader; prefer that when adding new firmware calls
   — a new call (allocator, power-off manager) shows up as an immediate error
   instead of a wrong answer.

## The image is not the running camera

The file is the firmware as flashed, not as it runs. Runtime data areas hold
build-time leftovers:

- `0xC2F20FC0 + 0x21C` (AutoRun registration depth) reads **0x38357C54** in the
  image. Code that walks that table ran off the end in emulation — and would on
  a camera whose table was ever that value. Set the state the test means
  (`depth = 0` for "no script", `1` + `+36+4 = 0xC03DA7A8` for "AutoRun
  running") and bound the walk in the code (depth ≤ 15).
- Warm restart keeps the image **as the last boot left it**, so a test that
  starts from stock only covers a cold boot. Seed the leftovers explicitly
  (e.g. an armed hook site, a stale word at a patch site) for the warm case.

## Proving a test can fail (do this every time)

A new emulation test that passes on the first run has not shown anything yet.
In an isolated copy of the current source and test inputs, mutate one
instruction or constant in `fpSup/fp_usb_shell/asm/stage2.S` and require the
relevant test to fail. Then run the unmodified source and require it to pass.
Do not edit the working copy in place and rely on a later `cp` to restore it;
an interrupted test can otherwise leave the build source corrupted.

Mutations that caught real gaps on 2026-09-25: skip the journal write, make
the restore write nothing, always start the AutoRun, never report success,
drop the foreign-loader check, journal the cave too, skip the forced list,
arm the abort unconditionally, drop the depth bound, skip the wait before the
banner, draw text with argc 0. A mutation that does not fail means the test
checks less than its name says.

## What to assert (and what not)

- Assert **effects in memory**, decoded independently: parse the VBIN yourself,
  compare journal entries with `cam.stock[addr-0xC0000000:]`, read the site
  word, walk the table. Do not assert on the code's own bookkeeping only.
- Check the stack comes back where it started (`sp` after the call) and that
  every firmware call saw an 8-aligned `sp` (the harness in `test_splash`
  enforces it).
- Check the fallback: remove the file (`have_file=False`) and require the
  original routine to be reached with the firmware's own `r0/r1/lr`.

## What emulation cannot tell you

Timing (when the UI redraws, when the SD is ready), whether a power switch
restart keeps the image (the IPL decides), whether a drawn frame survives the
GUI, and anything the real firmware routines would have done that the stub
did not. Say "emulated" and "on the camera" separately in every report.

## Where the tests are

- `fp_usb_shell/test_loader_hook.py` — loader hook, journal/power-off restore,
  three-way boot, four-box on the hook path, plain cards.
- `fp_usb_shell/test_splash.py` — stage2 under a strict harness, splash frames.
- `fp_usb_shell/test_boot_chain.py` — instruction-level checks of the loader.
- `projects/open-gate/build/test_boot_entry_chain.py` — builds × entries.
