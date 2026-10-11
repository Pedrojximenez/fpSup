# RAW14 ×2 OpenGate experiment

Status on 2026-09-15: **offline preflight complete; every record-mode hardware
stage is intentionally blocked until a bounded one-frame RAM-sink probe exists.**

No script in this directory can connect to the camera or write live memory.
`raw14_2x_plan.py` only reads the pinned firmware image and research CSVs, emits
JSON, and refuses to produce an executable RAW14 hybrid.

## What the offline experiment established

- The best factorial is M141 (RAW14 1× continuous), M142 (RAW12 1× continuous),
  M143 (RAW12 2× continuous), with M6 donating exact-29.97 timing only.
- Four true ACQ sibling pairs — M97→M98, M142→M143, M130→M131 and
  M145→M146 — share 29 identical 1×→2× changes. After removing `reg 0x0001`,
  28 register changes form a well-supported reduction block.
- `reg 0x0001` is the sole common address between the established RAW-depth and
  reduction blocks. Known values are RAW14+1×=`0x29`, RAW12+1×=`0x2A`, and
  RAW12+2×=`0x39`. Neither the SIGMA 70-mode table nor the Sony 19-column table
  contains RAW14+2×. `0x38` is therefore not accepted as a plan value, and
  `0x39` is explicitly rejected for a RAW14 hybrid.
- Native Unicorn execution of firmware function `0xC0320AB0` confirms that an
  M141 record carrying the candidate receiver fields produces the same
  receiver-derived bytes as stock M143 for both 68-byte driver arguments under
  the same deterministic synthetic config. This proves only the receiver-table
  mapping; it does not exercise a sensor, timing, packing, allocation, or writer.
- The 18p hybrid timing cleanly preserves M141 HMAX/tail/VMAX while using the
  M143 input window. The 29.97 timing is exactly 2,402,400 clocks, or
  30000/1001 fps.

## Why hardware activation is still blocked

The stock recording registry treats `eRawBitType=1` as the RAW12 picker table,
and the present canvas code also falls through to its RAW12 branch. Without a
private enum-1 latch/canvas path and a simultaneous runtime profile change to
`+0x80=10/+0x84=8`, the DMA side can pack RAW14 into a RAW12-sized allocation. At
3024×2010, the RAW14 payload is 10,636,920 bytes; format 7 reserves only
9,117,360 payload bytes, short by 1,519,560 bytes per frame.

The record plane must stay 3024×2010. The RAW14 pitch calculation truncates
3032 pixels by two bytes per row, while 3024 gives an exact 5292-byte row.
Sensor/receiver/input remains 3032×2012 and active crop remains 3008×2000.

`imager createraw` is prohibited. Its apparent no-write branch is unreachable,
it always reaches a file writer for an actual capture, and its frame wait has
an infinite timeout. Ordinary idle live view also cannot validate this work:
it normally reports the preview mode rather than the recording sensor mode.

## Experiment ladder

1. `q12_control_18`: stock M143 sensor/receiver data inside the existing
   OG3K/p83 integration, retaining stock 18p timing.
2. `q12_control_2997`: the same M143 path, changing only to M6-style line/frame
   timing. Stage 1 must pass first.
3. `r14x2_18`: a logical/emulator-only overlay based on M141 RAW14, the proven
   28-register 2× block, and M143 receiver geometry, preserving the 18.003p
   frame period. This is not a private camera row and must never be applied to
   the shared M141 tables. It remains blocked by unknown `reg 0x0001`, unknown
   metadata `+0x60`, and the missing RAW14 movie pipeline.
4. `r14x2_2997`: add only M6 exact-29.97 timing after stage 3 proves physical
   RAW14+2× data.

Writer testing is a separate future experiment, not part of this ladder and not
yet authorized or designed. If it is later approved, UHD/OG3K recording remains
limited to one second.

Stages 1–4 require a new bounded probe first: one preallocated RAM frame,
writer enqueue hard-disabled, an independent watchdog, redzones, a one-frame
callback that pauses/releases immediately, and a cleanup state machine. The
probe must pass both stock M143 and forced-timeout fault injection before it is
allowed to arm a candidate.

Every candidate pass must verify the actual mode commit, both receiver
consumers' 68-byte payloads, cadence within ±1% with no gap above two periods,
and that the same runtime descriptor reads `+0x20=1` at both packer callsites.
It must also verify private latch 1, an explicit enum-1 canvas path, runtime
profile `+0x80=10/+0x84=8`, RAW14 packer state, allocation redzones, 5292 bytes
per row, nonzero low two-bit entropy, and the ISO100 gain baseline. ISO100 may
isolate sensor/link discovery only; it does not validate gain behavior, dynamic
range, or authorize recording. A missing item is a no-go, not a retry in the
same boot.

Before any future camera/USB use, explicitly warn the user and wait until they
say the camera is free. Each ad-hoc live-memory read also requires a separate
address-specific approval. No warm reboot, preset save, STILL operation, or
in-camera RAW14 playback is part of this experiment.

## Offline commands

```sh
python3 -B raw14_2x_plan.py summary
python3 -B raw14_2x_plan.py q12_control_18
python3 -B raw14_2x_plan.py q12_control_2997
python3 -B raw14_2x_plan.py r14x2_18 --require-ready
python3 -B -m unittest discover -s . -p 'test_*.py' -v
UV_PYTHON_DOWNLOADS=never uv run --offline --with unicorn python verify_receiver_native.py
```

The optional Unicorn command is host-only and succeeds only when its dependency
is already cached; it must not download anything. Blocked reports are
`armable:false` and reference/emulator-only. The blocked RAW14 command returns
status `BLOCKED_REFERENCE_ONLY`; with `--require-ready`, it also exits with
status 2. The current offline suite contains 24 tests; the checked native report
also pins the firmware, CSV/register order, planner, verifier, config, and
receiver-fixture hashes.
