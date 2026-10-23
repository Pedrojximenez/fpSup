# fpLossless — standalone lossless RAW compression

## 2026-10-12: RAW memory admission guard (experimental)

The `--expand-slots` candidate now checks actual primary RAW headroom before
admitting each new compression job. Compressed files keep their full RAW
allocations: extra descriptor positions alone cannot prevent RAM exhaustion.
The native **64 MiB byte target stays unchanged**. Ruari's **STOPFX remains a
separate, unchanged sup**.

The guard leaves room for two full batches of RAW fallback files, arrivals
during the measured completion budget, four pipeline frames and two stop
frames. It charges the full native allocation, allocator header and alignment:

```text
raw_file = 0x13400 + align512(native_raster_bytes)
frame_charge = align1024(0x15400 + align512(native_raster_bytes) + 64)
reserve_frames = 2 * ceil(64 MiB / raw_file)
               + ceil(ceil(FPS) * completion_budget_us / 1,000,000) + 6
reserve_bytes = reserve_frames * frame_charge
```

The completion budget starts at 100 ms and can increase during a take. At or
below the reserve, or if the memory map/counters/budget are unknown, new frames
go RAW. Larger RAW files reach the same byte threshold with fewer retained
allocations. Already finished lanes are collected before a new RAW fallback;
running jobs retain the existing bounded stop/drain path. Compression can
resume when headroom returns. The snapshot reads four words at most under the
native IRQ exclusion; it does not walk allocation lists or allocate memory.

The RAW_SUB fallback is not added to the primary RAW allowance. Current frames,
both spares and tables are already included in the native used counter. This
guard is a conservative admission budget, not a guarantee against fragmented
memory, an indefinitely stalled medium, or unrelated high-FPS scheduling bugs.
In particular, the previous 119.88p freeze remains unproven as a RAM failure.
Exact candidate bytes and validation: [RAW memory guard](../../projects/lossless-sup/validation/20261012-raw-memory-guard/).

Validation passed 177 host test methods (including targeted mutations), 14
exact-BIN ARM tests, the independent STOPFX test in both load orders, and two
default-loader regressions. Candidate `10LOSS.BIN` is 79,200 bytes; its resident
block is 5,976,064 bytes, 4 KiB above the previous candidate. SHA-256 before
the normal on-camera setting save:
`1baa14dc4bb4275e52969fe7e891801be2dc531523afd79a2c9318e6438a940d`.
The file-write reply timed out; native completion status and full readback
confirmed success before one normal reboot. No write was replayed.

On-camera M12240 trials then completed 136/136 frames at 29.97p and 220/220 at
59.94p. All 832/844 positions respectively returned, both codec spares were
released after each take, and the native RAW used counter returned to zero.
Both clips were entirely RAW; first/last DNG samples from the 29.97p clip decode.
Minimum sampled primary RAW headroom was 635.42/625.95 MiB, above the respective
145.28/153.70 MiB reserves. The low-memory branch was therefore exercised only
offline, not by these camera trials. No new 119.88p/239.76p trial or local merge
update was performed. See [structured results](../../projects/lossless-sup/validation/20261012-raw-memory-guard/status.json).

## 2026-10-12: M12240 start-refusal correction

The initial expanded-slot candidate below reserved at most 768 positions.
M12240's **RAW 1008×672** geometry needs **832 positions at 29.97p** or
**852 at 239.76p**, even with the initial 100 ms completion budget. Its smaller
files make two full 64 MiB batches require more positions; reducing FPS did
not bring the plan below 768. The exact original BIN reproduces this refusal
in ARM emulation.

The explicit `--expand-slots` build now reserves **1016** positions for the
descriptor pool, registry, completion cookies and both metadata rings. This
is the largest four-aligned capacity covered by the existing native imm12
registry-control instructions; larger layouts need a separately reviewed
instruction change. The generator rejects out-of-range offsets instead of
silently corrupting an instruction. The active count still follows the same
formula and the **64 MiB byte target is unchanged**. Neither STOPFX nor the
shared loader/AutoRun is changed.

The corrected resident block is 5,971,968 bytes (about 5.70 MiB), 1,425,408 bytes
more than the 768-position candidate. At 239.76p, M12240 fits a completion
budget through 783,333 microseconds; larger plans still refuse. Extra positions
do not supply frame-payload RAM or resolve the mode's earlier `vbuf` stops.
The local merge artifact remains unchanged. Exact bytes and hardware results:
[`20261012-m12240-slot-capacity`](../../projects/lossless-sup/validation/20261012-m12240-slot-capacity/).

Resumed hardware trials passed M12240 29.97p (169/169 written, 832 positions
recovered) and 59.94p (279/279, 844 recovered), with the original 64 MiB target.
Both takes wrote only RAW fallbacks; two 29.97p DNG samples decode. At 119.88p,
USB queries timed out and the user reported an unresponsive physical stop
button, then manually powered off. Clean stop, allocation release and clip
integrity remain unverified for that take. No further 239.76p trial was run;
this remains an experimental candidate, not a stable release.

The follow-up [memory audit](../../projects/lossless-sup/validation/20261012-m12240-slot-capacity/MEMORY_AUDIT.md)
measured a 708.12 MiB CinemaDNG RAW pool, a 71.65 MiB peak in a short M12240
29.97p take, and RAW used=0 after stop. It also confirmed a capacity-model gap:
compressed frames retain full-sized RAW allocations, so the 822-frame
two-batch worst-case slot budget would require about 864.95 MiB just for
frames. Slot sufficiency is not a RAM capacity guarantee. The current test
readiness callback in that older candidate did not check actual RAW headroom; the 119.88p hang has
not been proven to be memory exhaustion. Descriptor placement in the USER
NonCacheBuffer block also needs a separate performance check.

## 2026-10-12: expanded positions, original 64 MiB batching

The initial **768-position experimental candidate** was selected with `--expand-slots`.
It replaces the earlier 39–42-frame early-flush approach by enlarging the
native descriptor pool, frame registry, completion-cookie storage and both
compression-metadata rings. It keeps the native **64 MiB** byte trigger, its
fragmentation/scatter-arena flushes, and the independent STOPFX module.

For each admitted LOSS take, before dispatching REC:

```text
S = 0x13400 + ceil(width * height / 8)       # compressed-file lower bound
B = ceil(64 MiB / S)
A = ceil(ceil(fps_num / fps_den) * completion_budget_us / 1,000,000)
N = max(96, round_up_to_4(2 * B + A + 4 pipeline + 2 stop))
```

The bound uses at least one Huffman code bit per Bayer pixel plus the retained
DNG header. It intentionally covers highly compressible frames; RAW fallbacks
are larger, so cannot require more positions to accumulate 64 MiB. The host
planner also supports uncompressed size (`width * height * bit_depth` bits).
Mean compression ratio remains a diagnostic, not the capacity guarantee.
Only idle frames enter the codec; arrivals while both lanes are busy retain
the existing RAW fallback. FPS reserves arrivals regardless of compression.

With the initial **100 ms** completion budget:

| Actual RAW geometry | FPS | Max files to reach 64 MiB | Active positions |
| --- | ---: | ---: | ---: |
| 1936 × 1090 | 29.97 | 196 | 404 |
| 1936 × 1090 | 59.94 | 196 | 404 |
| 3024 × 2010 | 100 | 81 | 180 |
| 3840 × 2160 | 30 | 61 | 132 |

The last row is an arithmetic example, not newly enabled mode support.
A measured batch-completion return longer than the budget increases it for
the **next** take. The active pool never resizes while frames or cookies are
live. Plans above 768 positions, invalid inputs, or a budget above one second
are refused; they do not lower the byte target. 100 ms is an initial assumption,
not a measured worst-case medium latency. Only actual near-exhaustion (two free
positions) or the enlarged cookie limit can request an additional early flush.

The loader reserves the maximum backing storage once, avoiding a recording-time
allocation. This candidate's total resident block is **4,546,560 bytes**
(about 4.34 MiB), including 768-slot backing and both metadata rings. Active
descriptor bytes are `0x1130 + N * 0x1128`; FHD uses 1,778,768 bytes of that
backing. The original empty pool remains allocated for restoration. This is
descriptor/metadata space, **not a newly allocated 128 MiB image buffer**;
actual frame payload RAM and media throughput still limit recording.

```sh
python3 -B lossless/build_v3_lossless.py --expand-slots --out /absolute/new/directory
# Run expanded tests in their own process (different build-time capacities).
cd lossless
FPL_SLOT_CANDIDATE=/absolute/new/directory python3 -B -m unittest -v test_slot_expansion
```

Exact bytes, formula checks, native ARM tests and limits are recorded in
[`20261012-slot-expansion`](../../projects/lossless-sup/validation/20261012-slot-expansion/).
`card_status.py` accepts the candidate's matching `layout.json` and reports
active positions, file lower bound, completion budget and refused plans.
The local merge page retains its previous hardware-tested artifact. Hardware
testing of the expanded candidate on 2026-10-12 verified 404/416-position FHD
pools and complete tracked ownership recovery after ten 3K automatic stops.
However, FHD59.94 stopped with `mem, raw2`, and a later take developed a lagging
recording timer and USB timeouts requiring a manual stop. This candidate
**must not be promoted as a stable build**. Replugging USB recovered the same
boot: the final take's 16,911 frames were all written and its 428 positions
fully returned. This does not resolve the observed UI/USB faults. Four DNG
samples decoded; a middle-frame file read timed out, limiting validation.
Full evidence and limitations are in
[`20261012-camera-expanded-slots/RESULTS.md`](../../projects/lossless-sup/validation/20261012-camera-expanded-slots/RESULTS.md).
Ruari's `05STOPFX.BIN` is unchanged and remains optional and independent.

## Earlier 2026-10-12 revision: adaptive batch count

Without `--expand-slots`, builders retain the earlier batch-count policy.
Its archived hardware evidence is in
[`20261012-camera-lossless-stopfx`](../../projects/lossless-sup/validation/20261012-camera-lossless-stopfx/).
Those results do not validate the new expanded-slot candidate above.

- Keep the stock **64 MiB** byte target. A second native flush trigger limits
  frames in a batch to half the available descriptor budget, after reserving
  two stop slots, four pipeline slots, and arrivals during a writer return.
  FPS is rounded upward; the initial return allowance is **100 ms**, then only
  increases to the longest observed return in that take. These reserves are
  policy assumptions pending hardware measurement, not a no-stall guarantee.
- Actual mixed RAW/compressed bytes drive the existing byte trigger. A rolling
  32-file sample reports compression fraction, mean file size and the estimated
  frames needed for 64 MiB. The estimate never relaxes the count/free-slot
  guards. Resolution and RAW fallbacks are thus reflected in actual file sizes.
- The count hook applies only to the current admitted lossless writer frame
  with the stock CinemaDNG callback. Low/unknown free descriptor counts force
  an earlier native flush. OFF and unrelated filesystem calls retain their
  original count decision.
- Flush metadata now checks the native frame pointer and generation as well
  as the file buffer address; reused addresses retire mismatched metadata
  without freeing live memory or applying a previous frame's compressed header.

The batch hook is guarded, journaled, exclusively claimed in v3 and restored on
shutdown. LOSS builds, loads and runs its tests independently of other optional
sup modules. The module package contains `10LOSS.BIN` and its build/layout
metadata. Cross-module checks are maintained separately in `integration_tests/`.

Build from `fpSup/` into a new empty directory:

```sh
python3 -B lossless/build_v3_lossless.py --out /absolute/new/directory
# Add --trace for diagnostics, or --card for a complete shared-loader card.
```

Focused offline tests:

```sh
cd lossless/native
python3 -B -m unittest test_bulk_policy test_frame_hold test_record_diag
cd ..
python3 -B -X faulthandler -m unittest test_bulk_native test_v3_lossless test_card_emulation
```

`card_status.py` reads the matching build's `layout.json` and reports batch cap,
FPS reserve, pool pressure, mixed file statistics and retired stale metadata.
Source changes, exact candidate bytes, validation logs and hardware limitations:
[`20261012-lossless-independent`](../../projects/lossless-sup/validation/20261012-lossless-independent/).
The updated mechanism is also recorded in
[`EARLY_STOP_94.md`](../../projects/lossless-sup/notes/EARLY_STOP_94.md).

## Historical status — 2026-09-30

Development source, **not an installable recording product**. No AutoRun,
VSHL, firmware patch or camera deployment is emitted by this directory yet.
The current development entry (2026-09-30, §14), evidence limits and next gates are in
[`PROGRESS_20260930.md`](../../projects/lossless-sup/notes/PROGRESS_20260930.md).
The adjacent `IMPLEMENTATION.md` is a chronological history, not the current
verdict.
Buffer/lifetime notes and historical design alternatives are in
[`BUFFER_DESIGN.md`](../../projects/lossless-sup/notes/BUFFER_DESIGN.md).
The 2026-09-29 synchronous probe wrote decodable compressed DNGs. The historical
async probe copied earlier-frame output into a later frame; its driver now
unconditionally refuses `arm`, including direct API calls. The new
`frame_pipeline.c` implements a single-pending-frame adaptive policy with saved
source/file identity, but has no native hold/defer/handoff adapter. Source
lifetime, source-tail coverage, safe release and all-format capacity remain
integration gates. Busy frames pass as RAW; no source frame is deliberately
dropped. Submit return is not a buffer-release fence.
Follow [`SUP_BUILD_RULES.md`](../SUP_BUILD_RULES.md) for builds; notify the user
before camera testing and obtain authorization for that run. This increment
includes host and ARM-emulated tests, not a card build or camera validation.

Current requested test card: **direct compression + current USB shell + Fast
Start 2**, without menu, OG or gyro. `fpl_begin_direct` is implemented for the
real REC boundary: it omits only UI readiness and preserves every capture
proof. It does not install a recorder hook or make unverified geometry ready.
There is not yet a deployable card; `requested_test_build` in the manifest is
the requested scope, not an artifact receipt. USB shell must remain enabled in
the shared build; a shell-only card is not a Lossless build.

The REC-before-frame workspace is now implemented in `native/rec_workspace.c`,
with geometry-derived layout and native RAW/class 10 allocation wrappers. It
calls original REC preparation before reserving, rechecks producer facts and
source headroom after reserving, and separates stop from quiescent release.
This adapter has compiled-C integration tests and ARM object builds; the RAW
wrapper additionally executes original descriptor instructions in Unicorn.
It is **not installed at the REC call site**, has no native facts provider or
compression worker, and does not prove DMA output limits. Layout arithmetic
includes 14-bit, but the recording control still rejects 14-bit. Reproduce with
`native/build_workspace_offline.py`; see [native details](native/README.md).

Deferred UI: **SHOOT page 2 (CINE)**, alongside DC crop, recording settings
and audio recording, with a dedicated **Lossless RAW / 無損壓縮: OFF / ON**
row. Existing entries retain their original meanings. The private binding name
is `MV_fpLossless`. An offline fourth-row resource builder now exists in
`menu/`; `native/` contains executable ARM variable-call wrappers and, in
`native_port.c`, the `fpl_binding_ops` adapter that routes a native variable
event into policy. The opt-in `native-permission-gated` resource adds separate
private Cursor and Confirm bindings; the port refreshes confirmation permission
without treating a cursor move as a saved preference. `loader/native_reader.c`
now bridges real ARM32 reader fields to the original parser. Native row
installation, rendered-view publication, outer reader lifetime protection and
the exclusion/quiescence providers remain pending. No menu is installed on a
camera by these changes, and this port still refuses to supply `FPL_READY_UI`.

This is an independent product. It does not select a sensor mode, alter crop,
exposure or bit depth, or include OpenGate patches. Future OG2K/OG3K combinations
must be produced exclusively by `tools/card-composer` (fp-Merge). File/range
compatibility alone will not certify recording or playback compatibility.

## Implemented control core

`control.c` is a portable, freestanding C core for a future firmware adapter:

- private OFF/ON state, default OFF after a quiescent boot reset;
- no setting changes while a take is active;
- actual 10/12-bit CinemaDNG geometry candidates, including representative
  1K/2K/4K/6K sizes, positive frame rate and SD; bounded to 160 tiles;
- separate UI, codec, writer, header, playback, storage and REC-gate proofs;
- a second eligibility check at REC, catching mode changes after ON was chosen;
- a separate no-menu `fpl_begin_direct` REC entry; no fabricated UI bit and no
  UI binding instance in that build, with the same capture/format/fault checks;
- no implicit OFF when ON fails readiness; during a ready adaptive ON take,
  busy frames intentionally pass as RAW and keep their original identity;
- sticky error and explicit completion/cleanup before returning to idle.

The core does not itself provide atomic locking, DMA ownership, codec unwind,
menu drawing, parameter persistence, recording interception or playback. Its
caller must serialize access and derive readiness from verified adapters. No
production adapter currently supplies those proofs; ON must therefore remain
unavailable on an actual camera, rather than claim to compress while writing RAW.

The capability check deliberately uses the producer's actual dimensions and
packing rather than `M139`, `M98`, or an OpenGate display label. Additional
validated geometries can be added without building a separate compression
product per resolution. FHD is the first test case, not the product identity.
Candidate eligibility is not per-format support: the adapter must recompute
all readiness proofs for the exact geometry/packing/rate/media tuple. This
increment does not add 14-bit support or change sensor modes.

`frame_pipeline.c` is the small task-context policy behind adaptive compression:
one saved lease, no pending-frame queue or full-frame pool, no 40-frame stop.
OFF is all RAW. ON selects an idle arrival only after same-frame hold/defer
proof; busy arrivals pass untouched. Completion cannot release the lease until
codec quiescence and same-frame native handoff are proven. A valid result that
does not reduce the **complete DNG** size instead hands off the unchanged source
as RAW and continues. Real errors retain ownership and require cleanup.
Stop drains the last selected frame without requiring another incoming frame;
old take/session callbacks and inline handoff reentry are rejected. Counters
saturate without ending recording. The adapter must serialize calls, preserve
source metadata/filename, and never retain the stack-local stock writer at
`C03A5490`. None of those native adapter proofs are fabricated by the policy.

`ui_control.c` provides the corresponding lifecycle policy: CINE/MainB2-only
visibility, explicit confirmed OFF/ON events, stale-owner/generation/session
rejection, duplicate-attach protection, and recording-time lockout. A new boot
session invalidates old callbacks even if an owner address is reused. The native
adapter must supply non-reused tokens and actually unsubscribe/drain events;
this core cannot prove that on its own. It does not create the row.

## Offline checks

`python3 -B -m unittest discover -s tests -v` compiles this exact core for the
host, executes state transitions, and cross-compiles for ARMv7 with clang
(`-mfloat-abi=soft -mfpu=none`; no FP/NEON dependency). The view API uses an
explicit output pointer rather than an aggregate-return ABI. The initial
control/lifecycle suite covers all 128 readiness combinations and a 10,000-frame
control run. Compiled-C pipeline tests include a 1,200-frame run, OFF/ON
integration, error cleanup, stale tokens and mutation controls.
`tests/test_frame_pipeline_arm.py` additionally runs the actual compiled ARM
instructions with strict external-call checks, saved-register/SP checks and
an explicitly synthetic handoff. It uses the existing checked ELF extractor,
not a new linker or loader. A failed JIT is a test failure, not a silent pass.
These are not execution on the camera CPU or native buffer ownership proof.
It performs no camera or USB operations and fails if the compiler is missing.

Common codec research remains in `research/slimRAW` and `research/imaging-hw`.
Integration evidence and product decisions belong in `projects/lossless-sup`;
`notes/ROADMAP.md` is canonical for current gates.

The shared `research/ui/tools/native_ui_audit.py` verifies the pinned stock
MainB2 page and reports its row/allocation structure. It passes 15 additional
tests with the explicit pinned firmware, but does not add the fourth row.
The `menu/` builder now emits a complete expanded MainB2 resource fragment and
private string pool, **not a firmware image or installable card**. Its default
`pure-fixed-gated` profile adds a generic two-choice stock control as the fourth
CINE row, with literal **Lossless RAW / OFF / ON** and five private variable
references. It preserves the original three rows, stock string offsets and
allocation reserves, and remaps only typed object references. The original
Audio-clone profile remains a gated structural comparison, not the product UI.

The shared component-schema tooling covers all 18 ordinary kinds used by the
row, including unaligned strings and drawable common fields. The native
variable probe additionally passes 15 original-instruction tests with explicit
Lua/allocator substitutes. It confirms that registration failures are **not
transactional**; retries require a real recovery design.

The default row uses fixed popup geometry and explicitly disables its stock
sync request; it no longer reads shared popup width. The menu/recipe suites
pass 35 + 8 tests. Width 320 is a design choice, not measured camera rendering.

`binding/` adds a tested coordinator for registration ownership, private value
publication, rejected-choice restoration and subscription retirement. Native
callback return does not veto assignment; failed publication can leave ON
visible. The `FPL_BLOCK_REC` context bit therefore blocks RAW as well as lossless
REC while state is uncertain. In a UI-enabled build use the mandatory
`fpl_binding_begin` entry; do not bypass that binding with a separately
constructed context. The separate no-menu test build must not attach this UI
binding and uses `fpl_begin_direct` with fresh producer facts. Its 30 tests use mock
port operations plus ARM compilation, not the native GUI.

`loader/` adds a normalized reader-view lease with 53 sanitizer-tested groups,
exact candidate pins and retained string-pool lifetime. It is not a native
parser struct, hook or cache adapter. The original-instruction binding probe
adds 18 tests with explicit substitutes; actual widget callbacks are not run.
Rendering, navigation, native port functions, loader ownership and actual
allocation remain unverified. An offline
structural pass must not enable ON or bypass any codec/writer/playback gate.
The native call layer passes 23 compiled-ARM-to-original-instruction tests.
`native/native_port.c` implements the port contract over it: 22 scenarios run
twice each (host -O2 and an ASan/UBSan executable) against the real
coordinator, UI policy and control sources, plus an ARMv7 Thumb soft-float
compile with no libc, FP or compiler-runtime dependency. This port can never
claim `FPL_READY_UI`, so ON stays unselectable; without caller-supplied
exclusion and quiescence providers it reports FPL_BUSY and refuses to retire a
live subscription. Four injected defects each fail the suite.
Further shared probes cover lazy page selection (16 cases) and input/property
boundaries (14 cases). These expose two integration hazards: parser nonzero
returns can publish an incomplete root, and disabling a key does not cancel an
already-active repeat. The current page candidate is intentionally unchanged.
See `native/README.md`, `menu/README.md`, the canonical
`projects/lossless-sup/notes/ROADMAP.md`, and the historical
`projects/lossless-sup/notes/IMPLEMENTATION.md`.
