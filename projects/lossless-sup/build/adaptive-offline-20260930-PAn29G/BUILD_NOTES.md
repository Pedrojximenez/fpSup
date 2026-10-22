# Adaptive lossless policy — offline build, 2026-09-30

This directory contains **ARM relocatable objects, not an installable product**.
There is no native source-hold/defer/handoff adapter, entry, installed hook,
`fpSup.BIN`, AutoRun, card write or camera test. `camera_ready=false`.
The existing shared builder/composer remains mandatory for a future card;
this compilation does not introduce an alternative loader or packaging path.
Follow `fpSup/SUP_BUILD_RULES.md`; notify the user and obtain that run's
authorization before camera work. No commit, push or release was performed.

Working tree: `/Users/dido/Developer.localized/SIGMAfp_re/fpSup` (dirty before
this work; unrelated edits preserved). Main record: `../../notes/PROGRESS_20260930.md`,
§10. Exact source/artifact digests are in `ledger.json` in this directory;
these are host-side provenance, never runtime BIN/AutoRun version pairing.

## Reproduce objects

Run from `/Users/dido/Developer.localized/SIGMAfp_re`. For a rerun, create a
new local output directory first; do not overwrite this snapshot or a card.

```sh
build_out=$(mktemp -d projects/lossless-sup/build/adaptive-offline-20260930-XXXXXX)
for unit in control ui_control frame_pipeline; do
  /usr/bin/clang --target=armv7-none-eabi -mcpu=cortex-a9 -marm \
    -mfloat-abi=soft -mfpu=none -std=c11 -O2 -ffreestanding -fno-builtin \
    -fno-unwind-tables -fno-asynchronous-unwind-tables -Wall -Wextra -Werror \
    -c "fpSup/lossless/${unit}.c" -o "${build_out}/${unit}.o" || exit 1
done
```

The recorded run used `projects/lossless-sup/build/adaptive-offline-20260930-PAn29G`
for `build_out`. Clang: Apple 21.0.0 (`clang-2100.3.27.1`); Python 3.9.6;
host ARM64; Unicorn 2.1.4. Produced `control.o` (2388 B), `ui_control.o`
(2012 B), `frame_pipeline.o` (3896 B). Objects may contain normal link
relocations; no packaging, link or entry installation was attempted.
The independently executed pipeline text alone is 2680 B, extracted using
the existing strict `research/ui/tools/arm_text/elf_text.py` (no text relocations
or unapproved external helpers). Its hash is recorded separately from the ELF.

## Final verification commands/results

From the `fpSup` directory:

```sh
python3 -B -m unittest discover -s lossless/tests -v
python3 -B -m unittest discover -s lossless/binding -v
python3 -B -m unittest discover -s lossless/native -p test_native_port.py -v
```

From `fpSup/raw/lossless_codec`:

```sh
python3 -B -m unittest -v test_inline_compress test_inline_geometry \
  test_inline_deployment_gate test_native_writer_contract
```

| Suite | Final result | What it does not prove |
|---|---|---|
| lossless/tests | 64 passed, 0 skipped; 5.242 s | Native hold, UI installation, real codec/DMA |
| nested actual ARM policy worker | 8 cases, 0 skipped, inside one of the 64 tests | Synthetic handoff is not a firmware writer |
| lossless/binding | 30 passed, 0 skipped; 0.450 s | Native drawing/event quiescence |
| lossless/native/test_native_port.py | 23 passed, 0 skipped; 1.291 s | Production UI readiness remains false |
| focused codec/driver/stock writer | 129 passed, 0 skipped; 0.557 s | Whole movie pipeline or new live pass |

246 top-level tests total. Do not add the eight nested ARM cases again.
The 129 include tests of historical unsafe probe structure, plus the new arm
refusal; their passing result does not approve deployment of that old probe.
The stock writer runner executes bounded real firmware paths, with declared
logging/memcpy/observer/constructor substitutes, and stops before opening a file.
Firmware image SHA-256 is pinned in the ledger; no camera or USB calls occur.

Coverage includes 10,000 control transitions, 1,200-frame compiled-C pipeline,
64 selected + 128 busy RAW arrivals in ARM, same-source identity, stop without
a next frame, stale notifications, reentrant handoff refusal, OFF/ON integration,
and equal/larger valid results returning the original RAW before continuing.
Eight isolated pipeline mutations, three format-gate mutations and an ARM
output-ownership mutation are detected; native result-branch inversion is also
caught for zero and nonzero cases. Mutations affect temporary copies/emulator
memory only. The agent also ran pipeline host and ARM entry points under `-O`.

The initial sandboxed ARM workload aborted with SIGILL; a reviewed host
execution succeeded. Final ARM results were obtained outside that sandbox,
not inferred from compilation. A later permission-review timeout was retried
once successfully; no failed or skipped run is being counted as a pass.

## Next gate

Prove a native whole-frame lease and a legal creator completion split:
later RAW frames must advance while the selected original remains held, and
its eventual completion must not advance the FIFO a second time. The current
flush-local writer is stack storage, a zero flush return is failure, and a
mailbox ID is not a lease. Do not fake terminal state or increment clone refs.
Then implement that adapter, validate FHD identity/stop/batch behavior, connect
the actual menu, and establish each 10/12-bit format's safe output capacity.
6K eligibility alone is not a DMA bound or format pass.

No AutoRun update is needed for this offline increment. Future compatible
payload builds still verify that their shared AutoRun remains unchanged.
