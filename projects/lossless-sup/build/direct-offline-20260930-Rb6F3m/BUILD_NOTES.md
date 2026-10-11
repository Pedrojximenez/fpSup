# Lossless direct control and native buffer contracts

2026-09-30. Requested card: direct Lossless activation, current USB shell and
Fast Start 2, without menu, OG or gyro. This directory contains offline control
objects and verification evidence, **not an installable card**. No recorder
adapter, AutoRun or BIN was produced; no camera, card, commit, push or release
operation was performed. Current development direction is PROGRESS_20260930 §12.

## Reproduce the offline increment

Working directory: `/Users/dido/Developer.localized/SIGMAfp_re`.
Use a fresh output directory when repeating, rather than overwriting this one.
Tools used: Python 3.9.6, Apple clang 21.0.0, Unicorn 2.1.4.

Commands and final logs, all exit 0 and 0 skips:

```sh
python3 -B -m unittest discover -s fpSup/lossless/tests -p 'test_*.py' -v
python3 -B fpSup/lossless/native/test_native_port.py
python3 -B -m unittest discover -s fpSup/lossless/binding -p 'test_*.py' -v
python3 -B fpSup/raw/lossless_codec/test_native_codec_contract.py -v
python3 -B fpSup/raw/lossless_codec/test_native_defer_contract.py -v
python3 -B fpSup/raw/lossless_codec/test_inline_deployment_gate.py -v
```

Logs in that order: `core-final.log` (73), `native-port.log` (23), `binding.log`
(30), `native-codec.log` (16), `native-defer.log` (22), `disabled-probe.log` (16).
Total **180 top-level tests**. The core's 11 direct-control ARM cases and 8
pipeline ARM cases run inside two of those tests, not counted again. `core.log`
is the earlier 72-test run before adding the explicit requested-card scope
regression; it is retained but not used for the final total. Scope tests verify
the manifest, not the presence of a merged artifact.

The real Unicorn workloads require approved host execution on this machine;
sandbox JIT failure is not success. New direct/codec/defer tests fail explicitly
when compilation, pinned images or actual JIT execution are unavailable.

Compile the actual current source into offline ARM objects:

```sh
clang --target=armv7-none-eabi -mcpu=cortex-a9 -marm -mfloat-abi=soft -mfpu=none -std=c11 -O3 -ffreestanding -fno-builtin -fno-addrsig -fno-unwind-tables -fno-asynchronous-unwind-tables -Wall -Wextra -Werror -IfpSup/lossless -c fpSup/lossless/control.c -o projects/lossless-sup/build/direct-offline-20260930-Rb6F3m/control.o
clang --target=armv7-none-eabi -mcpu=cortex-a9 -marm -mfloat-abi=soft -mfpu=none -std=c11 -O2 -ffreestanding -fno-builtin -fno-addrsig -fno-unwind-tables -fno-asynchronous-unwind-tables -Wall -Wextra -Werror -IfpSup/lossless -c fpSup/lossless/frame_pipeline.c -o projects/lossless-sup/build/direct-offline-20260930-Rb6F3m/frame_pipeline.o
```

`control.o`: 3160 B; strict text 2076 B, SHA-256
`47a308e615f52ede4349388c367cf41bab37c48c2cb82240982d73e66a332313`.
`frame_pipeline.o`: 3844 B; strict text 2680 B, SHA-256
`727f0d49e18d22f34e03478163e596284a61a1992e6a2e72ac52356ca40c9f81`.
Both were checked with the existing `research/ui/tools/arm_text/elf_text.py`.
Control at -O2 is a valid relocatable object but has two internal menu-call
relocations, so the strict extractor correctly rejects it as standalone text.
At -O3 clang legitimately inlines those calls. No relocation was discarded or
silently applied, and no production source was changed to trick extraction.
The first -O2 control object in this new, unfrozen build directory was replaced
by the final -O3 object above; no historical artifact was overwritten.

Source/artifact hashes and pinned firmware are in `SHA256SUMS`, relative to the
working directory. Verify with:

```sh
shasum -a 256 -c projects/lossless-sup/build/direct-offline-20260930-Rb6F3m/SHA256SUMS
```

## What the evidence does and does not establish

The direct entry executes the actual compiled control C without a UI binding;
facts are read-only synthetic context, not hardware readiness. All 128 direct
and menu readiness combinations are covered, plus format/fault/stop/cleanup,
1200 frames, saturated counters, ABI and PC checks. The pipeline's callback
remains synthetic. Tests cannot grant a native lease by supplying held=1.

The defer suite executes the real creator, registry, FIFO, ordinary stop,
THR-state exit dispatch and codec IRQ callback. Native mutex/kernel receive,
mailbox send and destructive/resource boundaries have explicit substitutes.
It proves a useful sequential pending-prefix/re-enqueue candidate, plus the
counterexamples that make state B alone insufficient ownership. IRQ completion
does not use the movie task, but scheduler liveness and DMA quiescence are not
emulated. Waiting for final native file completion on that task may deadlock.

The codec suite executes original init/encode/size/postprocess/close instructions
with bounded OS, submit/start and power-control substitutes. Submitted JPEG
markers are synthetic, not encoded pixels. Alignment checks stop before MMIO;
source-tail arithmetic is not proof of native allocation capacity. Success
postprocessing/close, indefinite timeout retry, incomplete failure cleanup,
unchanged pointer aliases and zero-height geometry are tested. Four isolated
codec mutations and three defer mutations are caught. Native legacy SP mod8=4
boundaries are explicitly measured, not presented as an ABI model for new code.

The existing unsafe previous-frame inline arm entry remains unconditionally
disabled. No force escape or replacement deployment route was introduced.
Native port/binding regressions protect the deferred UI code from the shared
control refactor; passing them does not install or render a menu.

## Remaining integration and packaging

Implement real same-source ownership, padded source/output capacity, serialized
worker/handoff and stop/error/teardown drain before enabling runtime hooks.
Per-format encode and DNG/metadata validation remain required. Passing a control
format predicate does not establish support for every 1K/2K/4K/6K 10/12-bit tuple.

Then follow SUP_BUILD_RULES with the maintained shared loader and composer:
USB shell worker before a returning Lossless launcher, independently retained
resident memory, D-before-I publication, each runtime firmware hook journaled
with its original 4-byte word, and one coherent Fast Start 2 packaging run.
Do not use --no-shell, omit required entries, include unrelated products, or
ship a shell-only card as Lossless. Do not alter existing user-owned stage2
changes. Fast settings are persistent; exact artifact boot tests and product
installation tests are distinct. There is no AutoRun update for this offline
increment. Notify the user before hardware testing, stating the artifact,
bounded trial and recovery method.
