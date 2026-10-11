# Public research relevant to Sigma fp full-height recording

Reviewed 2026-09-09. Repository descriptions are leads, not camera validation. Our supplied firmware is fp 5.02, SHA-256 `c9fa76f32f523bb2dc9a3fbda39418c31573cab6a1aa5c56d28c371862066ed8`.

## Most useful findings

| Source | Useful material | Evidence and limits |
|---|---|---|
| [fpSup](https://github.com/ijigen/fpSup) | RAM payloads, gyro logging, shell commands, sensor mode CSVs, RAW/compression research | Directly relevant to this firmware. Our independent extraction exactly matches its published tables; individual interpretations and proposed features still require verification. |
| [Sigma fp open-gate plan](https://github.com/julienacquaviva/FP/blob/main/Sigma-fp-open-gate-plan.md) | Same 5.02 image hash, table addresses, proposed 3000×2000 mode and recording changes | Static plan without camera validation. Starts from reduced-resolution mode 98, which does not establish the requested all-pixel processing outcome. No working open-gate release found here. |
| [Sony IMX410 official flyer](https://www.sony-semicon.com/files/62/pdf/p-13_IMX410CQK_Flyer.pdf) | Full-height 6064×4040, 12-bit modes listed at 39.30 and 40.58 fps; 72 MHz input; SLVS-EC interface | Supports sensor feasibility in principle at 24–30 fps. Does not document the fp ISP, register programming, or Bayer resizing. Firmware raster has two additional rows. This is a two-page flyer, not the complete register datasheet. |
| [Sigma resources and Camera Control SDK](https://www.sigma-global.com/en/support/catalog/) | Official host control SDK and documentation | Useful for command semantics. Public camera-control interfaces do not establish availability of the imaging firmware source. |

The practical distinction: there is substantial open-source tooling around the fp and useful firmware reverse engineering. I have not located a published source tree for the camera's complete imaging firmware, or a demonstrated all-pixel 3000×2000 CinemaDNG patch.

## Independent table verification

Local fpSup snapshot: `8c70895cb2b817690bd4c3ddb433bd3cc3e567bf`.

Run `python3 tools/compare_upstream_sensor_tables.py`. Result saved in `analysis/firmware/upstream-table-verification.json`:

- All 70 mode IDs and indices agree for the register table.
- All 11,270 register values agree (70 × 161).
- All 1,680 geometry words agree (70 × 24, excluding mode ID).
- All 210 HMAX, tail, and VMAX parameters agree (70 × 3).

This validates agreement between two extraction paths. It does not prove every field's meaning, measured rates, or downstream recording compatibility. Our register extraction also validates the instruction blocks that associate row fields with sensor register addresses.

Useful fpSup entry points:

- [Sensor extraction script](https://github.com/ijigen/fpSup/blob/main/gyro/analyze_imx410_modes.py) and [published data](https://github.com/ijigen/fpSup/tree/main/gyro/analysis_imx410).
- [Shell capabilities](https://github.com/ijigen/fpSup/blob/main/docs/SHELL_CAPABILITIES.md) and [commands](https://github.com/ijigen/fpSup/blob/main/docs/SHELL_COMMANDS.md).
- [RAW research](https://github.com/ijigen/fpSup/blob/main/projects/raw-sup.md): lossless JPEG engine and RAW path leads. Its sustained video compression throughput remains unmeasured. The document retracts earlier DMA assumptions and reports a hanging still-RAW command; those routes should not be reused casually.

The independent open-gate plan is preserved in `research/julien-FP` at `f231387fac12ee5f859e299ba45593bdf1a81570`. Its agreement with table locations is useful corroboration, but it also builds on fpSup, so this is not an independent hardware demonstration.

## Control and validation projects

| Project | Potential use here | Limit |
|---|---|---|
| [sigma-ptpy](https://github.com/makanikai/sigma-ptpy) | Python PTP exposure, settings, capture and live-view control; protocol examples | Host control, not sensor firmware. Documents some event timeout and metadata issues. |
| [tethr](https://github.com/baku89/tethr) | Browser camera control using WebUSB; reusable protocol implementation | Does not demonstrate arbitrary sensor recording dimensions. |
| [sigma-fp-bridge](https://github.com/ijigen/sigma-fp-bridge) | Embedded USB control bridge and focus-control examples | Useful control transport work; separate from our image pipeline changes. |
| [OCTOPUS RAW Player](https://github.com/octopuscinema/raw-player) | MIT-licensed CinemaDNG player, including 12-bit Bayer and compressed sequences; lists Sigma fp among tested cameras | Useful independent decoder for eventual output tests. Successful playback alone would not prove full sensor contribution. |
| [CinemaDNG storage benchmark](https://github.com/kurikaesu/sigma-fp-cinema-dng-storage-benchmark) | Small Go program writing individual frame-sized files at a target cadence | Source review found limitations below; not a definitive camera or SSD diagnosis. |

Storage benchmark snapshot: `82bcabdf1caae1513f5ce64f2d87c6f900b87e81`, in `research/storage-benchmark`. Its fixed 12,630,528-byte frame size exactly matches our UHD sample. It writes random bytes through `os.WriteFile` with no explicit flush, uses integer-millisecond pacing, and runs without a duration bound. Thus host write caching and pacing affect the result. The files are not valid DNG images, and its reported MiB/GiB calculations are each off by a factor of 1024. I inspected it but did not run it on any storage device.

## Related camera reverse engineering

- [Georg Lukas's Samsung M7MU firmware analysis](https://op-co.de/blog/posts/samsung_m7mu_firmware/) and [samsung-nx-hacks](https://github.com/ge0rg/samsung-nx-hacks): Fujitsu/Milbeaut camera firmware layout and LZSS reverse-engineering methods. These are useful methodological references; their container offsets and patches cannot be transferred to the fp.
- [Ricoh GR3(x) firmware exploration](https://github.com/hhornbacher/gr3x-fw-hack): unpacking and analysis tooling for another camera family. Treat as a tooling reference; it is not evidence that the fp runs the same OS or accepts the same patches.

## Effect on our implementation plan

1. Reuse verified mode data and shell knowledge, with firmware hashes and instruction checks. Keep upstream speculation labeled.
2. Prioritize full-height modes 3/121 and the downstream UHD reduction path. Our own extraction shows the same 161 table-fed sensor register values as observed UHD mode 151, with a different receiver input window; other dynamic configuration still differs.
3. Trace raw geometry, reduction parameters, buffer allocation and DNG packing together. Changing only dimensions or using mode 98 does not meet the all-pixel requirement.
4. If more live state is required, design a bounded RAM capture that saves after recording stops, avoiding the previous diagnostic's writes to the active SSD during recording.
5. Keep compression as a separate optional research route. At exactly 3000×2000, packed 12-bit payload is 9 MB/frame: 216/225/270 MB/s at 24/25/30 fps, before borders, metadata, audio and filesystem overhead. Full-resolution 6000×4000 is 36 MB/frame and 864 MB/s at 24 fps. These are arithmetic payload estimates, not measured camera throughput or proof that USB alone determines feasibility.

No resolution patch has been built or deployed. No camera action is needed for this source audit.
