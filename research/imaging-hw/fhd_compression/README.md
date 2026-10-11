# Exact CinemaDNG writer probe

This is a one-shot diagnostic for the live FHD call at `0xC0722AFC` to
`0xC069AC88`. It records the first call, restores the firmware instruction from
inside the probe, and then passes the untouched call to the real writer.

The earlier candidate at `0xC0722A58` belongs to a v18 path that did not run in
the FHD recording test. The actual path was identified at `0xC0722AFC`, whose
original word is `0xEBFDE061` and whose expected return address is
`0xC0722B00`.

The installer also requires the surrounding six-word sequence before it writes
anything: `mov r1,sp; mov r0,r10; mov r2,#2; bl; add sp,#8; pop`. This guards
against applying the probe to a different firmware build or nearby call site.

It deliberately uses the shell template region at `0xC072F800` and state at
`0xC072F700`; it does not overwrite the gyro logger resident at
`0xC072E064..0xC072EFAC`.

Build and inspect without touching the camera:

```sh
./exact_dng_writer_probe.py arm --dry-run
```

Live sequence, after `fpshd` is connected and `fpsh ping` works:

```sh
./exact_dng_writer_probe.py arm
# Record 1-2 seconds of FHD CinemaDNG, then stop recording.
./exact_dng_writer_probe.py status
./exact_dng_writer_probe.py restore
```

The first hit should leave `count` at 1, `first_lr` at `0xC0722B00`, `done` at
`0x454E4F44`, and both the live hook and `restored_word` at `0xEBFDE061`.
`count` above 1 means the already-fetched hook instruction ran again; those
extra entries still tail-call the original function and do not overwrite the
first record.

## Live validation — 2026-08-31

A short 1920x1080, 12-bit CinemaDNG recording produced the expected one-shot
result:

```text
hook            0xEBFDE061  original/restored
count           0x00000001
first_r0        0xC3A6F3BC
first_r1        0xC3A6F37C
first_r2        0x00000002
first_lr        0xC0722B00
segment_buffer  0x53B02C00
segment_length  0x00318200
done            0x454E4F44
restored_word   0xEBFDE061
```

This confirms that `0xC0722AFC` is the live FHD CinemaDNG call which registers
one complete 3,244,544-byte DNG segment with `0xC069AC88`. The probe restored
the original instruction itself; no host-side restore write was needed.

Do not run `putfile.py`, `getfile.py`, or another template helper while the
probe is armed: those tools share `0xC072F700/0xC072F800`. If the camera becomes
unresponsive, pull the battery; all changes are RAM-only.

## Exact-writer codec preflight and encode design

`single_frame_codec_probe.py` shares the same verified live call site and the
same six-word context guard as the exact argument probe. It has five actions:

```sh
./single_frame_codec_probe.py preflight --dry-run
./single_frame_codec_probe.py scratch --dry-run
./single_frame_codec_probe.py encode --dry-run
./single_frame_codec_probe.py status --dry-run
./single_frame_codec_probe.py restore --dry-run
```

The `preflight` image is a power/clock-only one-shot. On its first entry it
restores `0xC0722AFC`, then performs this balanced sequence from the exact
writer task:

```text
power domain 3 on -> clock domain 5 on -> clock domain 5 off -> power domain 3 off
```

Every return value and any cleanup error are recorded. Cleanup follows the reviewed firmware policy: a
failed power-on releases nothing; a failed clock-on releases power; after a
successful clock-on, clock-off is attempted, and a failed clock-off does not cut
power underneath a clock that may still be enabled. Before those calls it reads
the segment and DNG only to enforce the observed FHD shape, verifies the codec
mode is idle, and records the source address. It never modifies the DNG or
segment, allocates memory, calls a codec wrapper, or writes codec globals. A
complete success leaves magic `0x52575050` (`PPWR`) at state offset `+0xD4`.

Live on 2026-08-31, this exact writer context passed: one hit, the original hook
restored, codec mode zero, aligned source `0x53B16000`, and all four power/clock
returns plus cleanup error equal to zero. The resulting `PPWR` magic was read
back successfully.

The `scratch` image is the next isolated phase. Its live installer first reads
and validates the complete `PPWR` state, then carries only that proof magic into
a new state block. On the first FHD frame it requests one 4 MiB non-cache block
with 1 KiB alignment, validates the low DMA handle and all arithmetic/ranges,
checks that it cannot overlap the DNG segment, and writes/reads four guards. It
does not call power, clock, or codec functions and does not modify the DNG or
segment. A complete result leaves `0x434F4C41` (`ALOC`) at `+0xD8`.

The successful scratch allocation is intentionally retained for exactly one
following encode-and-discard run. The installer refuses another power or scratch
preflight while it is retained, preventing a second 4 MiB allocation or loss of
the only handle. Do not load any other template during that interval. If the
encode/free phase cannot be completed, power-cycle the camera to reclaim it.

The common installer retains the exact probe's safety properties:

- it verifies the six firmware words at `0xC0722AF0..0xC0722B04`;
- code and the 256-byte state block are written and read back before the hook;
- the hook is the final write;
- an immediate first hit is recognized and never re-armed;
- restore accepts only this probe's armed word with a valid surrounding context.

The reviewed preflight images extend into known helper slots (`power` ends at
`0xC072FAAC`; `scratch` ends at `0xC072FBF4`). Do not run `putfile`, `getfile`,
bulk-loader, dump, or another template helper while either is loaded or armed.

The `encode` action is deliberately **dry-run only**. It assembles the proposed
single-frame encode-and-discard image and reports its layout, but refuses before
opening the camera transport if `--dry-run` is omitted. Its current image spans
helper sub-slots above `0xC072FC00`, and live encode must also be gated on a
successful exact-writer power and retained-scratch preflights.

The reviewed 4 MiB encode layout is:

```text
base + 0x000000 .. 0x304FFF   codec compressed output/work (cap 0x305000)
base + 0x305000               overrun guard
base + 0x306000 .. 0x30602F   final 12-word size table (init[7])
base + 0x306030               size-table guard
base + 0x306400 .. 0x30642F   codec temporary size table
base + 0x306430               temporary-table guard
```

`F_GET` requests 1 KiB alignment directly. The codec receives the low allocator
handle, not the cached alias. In the dry-run encode source, `init[6]` is the
compressed output/work base and `init[7]` is the size-table base; the original
DNG is source-only, and neither its header nor `seg[1]` is written.

Offline verification:

```sh
python3 -m unittest -v \
  test_exact_dng_writer_probe.py \
  test_single_frame_codec_probe.py
```
