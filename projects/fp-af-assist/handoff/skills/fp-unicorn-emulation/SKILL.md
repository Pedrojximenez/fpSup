---
name: fp-unicorn-emulation
description: "Validate SIGMA fp loader, stage2, hook and probe code offline with the repository's Unicorn harness and firmware image. Use for ARM execution, boot fallback, journal restoration, ABI checks and meaningful mutation tests before an authorized camera trial."
---

# SIGMA fp offline emulation

Adapted from the project's Claude Code skill on 2026-09-27. Default repository: `/Users/dido/Developer.localized/SIGMAfp_re`; respect an explicit alternate checkout. All code paths below are repository-relative.

For a loader/stage2/card change, first read `fpSup/AGENTS.md` and the full `fpSup/SUP_BUILD_RULES.md` (or English counterpart). The shared loader is authoritative; a skill example is not a separate build contract. Emulation does not require USB, a daemon, or camera memory access.

## Existing harness

`fpSup/fp_usb_shell/test_loader_hook.py` provides `build(extra=(), hook=True)` and `Camera(loader, binfile, have_file=True)`:

```python
# Run from fpSup/fp_usb_shell with an appropriate Python/Unicorn environment.
import test_loader_hook as T
loader, payload = T.build(['--store-boot'])
cam = T.Camera(loader, payload)
cam.call(T.CAVE_LOW + 4, r0=0xC0BABDD8, r1=1,
         lr=T.AR_RET, sp=T.STACK - 0x1004)
cam.call(T.CAVE_LOW)
```

Review the current test setup and entry arguments before adapting this sketch. `T.build()` creates temporary build artifacts; it does not operate a camera. The harness reads `out/MAIN_c0000000.bin`, maps firmware at `C0000000..C3000000`, zeroed BSS, heap at `45000000`, and stack. Its firmware call stubs return through LR. `TICK` returns `cam.now`; sleep advances simulated time.

This harness executes the real loader and stage2 but **stubs the payload's own entry**. It does not validate the full worker or AF payload. Check the runner's skipped-test report: missing Unicorn or the ROM image can skip tests, which is unverified rather than a passing emulation result.

To validate a specific card, load its exact `fpSup.BIN` and reconstruct the loader from its AutoRun `mem set` words within `T.CAVE_LOW..T.CAVE_LOW+0x200`. Do not rebuild and call the rebuilt bytes the tested card. Record original artifact hashes with results.

## Stub real call paths

- The constructor registers a bound `_hook` with Unicorn. Reassigning `cam._hook` afterwards does not replace that callback. Add the stub to the current address map before execution, register the intended callback properly, or write a deliberate ARM stub into emulated memory.
- Stub by the called address, not an assumed scratch register. stage2 may call through r3/r7/r8 rather than ip; instruction-pattern checks alone miss real calls.
- Prefer the strict pattern in `test_splash.ArmHarness` for new firmware calls: execution outside approved code/stubs must fail. Unmocked ROM can execute and return plausible nonsense.
- A stub proves only its declared effects. A USB completion stub cannot prove endpoint ownership or hardware timing.

## Initialize runtime state explicitly

The flashed image is not a running camera. Runtime structures may contain build-time leftovers. For example, AutoRun depth at `C2F20FC0+21C` was `38357C54` in the image: seed a valid scenario (depth 0, or an explicitly constructed active registration), and test rejection of out-of-range values. Production code must bound walks; a convenient seed does not remove that requirement.

Cover cold and warm initial states separately. Warm tests need deliberately seeded armed sites, previous journals, ownership and stale data; restarting an all-stock emulator covers only cold initialization. Do not infer the IPL's real warm-start behavior from the model.

## Assertions and mutation checks

Assert memory effects independently: decode VBIN, check installed words and journals against `cam.stock`, inspect registration tables, and verify original continuation on missing-file/error paths. Do not rely exclusively on a function's own success flag or counters.

Check preserved registers/flags required by the hook ABI, stack restoration and 8-byte alignment at firmware calls. For no-file fallback, verify the native routine receives its original arguments and return semantics.

For a new safety-critical test, prove it fails when the relevant behavior is broken: e.g. omit a journal write, skip restore, corrupt a hook guard, remove a depth bound, or fail to preserve the stack. Use an isolated temporary copy/worktree or an injected test variant; do not mutate shared source and rely on a later restore while others are working. Keep mutations bounded and tied to the changed behavior; ordinary documentation edits do not require mutation tests.

Run the focused relevant suite after restoring the intended variant. An undetected mutation means the assertion needs investigation, not a passing safety result.

## Maintained test locations

- `fpSup/fp_usb_shell/test_loader_hook.py`: loader hook, journal/restore, boot paths, missing-file fallback.
- `fpSup/fp_usb_shell/test_splash.py`: strict stage2 harness and display calls.
- `fpSup/fp_usb_shell/test_boot_chain.py`: loader instruction checks.
- `projects/open-gate/build/test_boot_entry_chain.py`: build/entry combinations.
- For AF observers, inspect the existing `fpSup/focus/geometry/` tests and native hook manifest rather than assuming the loader harness already covers every AF ABI.

Report emulated and on-camera results separately. Emulation does not establish sensor/exposure alignment, real DMA/USB completion, scheduling deadlines, optical focus, GUI lifetime or the IPL's retained-RAM decisions. Preserve those as explicit hardware validation items.
