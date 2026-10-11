# AF collector capture-state correction — offline-verified, live validation pending

2026-09-16. This staging directory does not alter maintained tools, installed
skills, historical captures, camera RAM or USB state. The AF/USB-shell skills
were read and used to preserve scratch ownership, record provenance and the
code-size limit. No live validation was performed.

## Source correction

`C00178D8()` returns `0xC3033834`; `C0017AC8()` adds `0x18`, yielding actual
system status **S = 0xC303384C**. Sources: `out/decomp/full/blk_c00.c` lines
21475–21488 and 21558–21564.

The native state producer `C04873D8` tests five bytes and returns enum 1 when all
are zero (`blk_c04.c:101470–101503`). The enum formatter `C04EF710` supplies the
capture-state names (`blk_c04.c:177298–177331`). `C00180A0` passes singleton+18
to the registered observer (`blk_c00.c:21941–21957`); a direct query also uses
`C00178D8 -> C0017AC8 -> C04873D8` (`blk_c04.c:101615–101619`).

| Address | Width | Meaning |
| --- | --- | --- |
| `C3033A6C` | u32 | Native PTP shutter-sequence gate, S+220; require zero |
| `C30338C8` | byte | StillExposing, S+7C |
| `C30338C9` | byte | StillSaving, S+7D |
| `C30338CA` | byte | MovieSaving, S+7E |
| `C30338CB` | byte | StillImageProcessing, S+7F |
| `C30338D0` | byte | MovieRecording, S+84 |

`C04F5AE8` tests S+220 and S+7C before native PTP focus
(`blk_c04.c:181133–181145`). This does not establish that S+220 is itself a
movie-recording flag or a general capture enum.

Old `C3033A54` reads missed the +18 status adjustment. Old `C347E08F` is a lens
synchronization movie-speed/protocol setting; the audit does not prove that it
exactly indicates active capture. Consequently, old `movie_recording=false`
cannot establish that a historical run was not recording.

## Binary v3 / JSON v6

- Record size: **212 bytes**, formerly 208. Old v1/v2 records remain 208 bytes.
- +BC: full u32 PTP shutter-sequence gate from `C3033A6C`.
- +C0: zero-extended actual MovieRecording byte from `C30338D0`.
- +D0: raw packed four bytes S+7C..7F, decoded in little-endian order.
- Existing trailer +C4, sequence complement +C8 and copied nonce +CC remain.
- Nonce seed moves from `C072F7D0` to **`C072F7D4`**, outside the new record.
- Shared status base removes an address load; handler remains **1000 bytes**.
- Handler SHA-256:
  `38d121bdf2fdd0653a779070a09fb1c3b93e9594719895a2ffe4e4b98eb757c0`.

New exposure fields are `ptp_capture_state_raw`, `movie_recording_raw`,
`movie_recording`, `capture_flags_raw`, `capture_busy_word_raw`, `capture_busy`,
`capture_guard_known`, and `capture_idle_for_af`. The old misleading
`capture_state_raw` field is no longer emitted.

Decoding old records preserves original bytes under `legacy_capture_raw`
(`c3033a54_u16`, `c347e08f_u8`, `flag_bit5`), sets recording/busy/idle/PTP state
to **null**, and marks `capture_guard_known=false`. v1 additionally retains its
legacy gain mapping; v2 retains its valid IMX410 gain mapping. Mixed-size binary
streams are decoded by validated version/length headers. No raw files are
rewritten. Live collection accepts only v3 from its installed handler.

## AF trial gate and remaining limits

Before S1ON, require a fresh coherent v3 observation (host sample age 0–250 ms),
actual MovieRecording false, every capture byte zero, and the full PTP gate
zero. Unknown/legacy/busy state is refused before setting release-needed or
dispatching S1ON. Once S1ON was attempted, the existing unconditional paired
S1OFF cleanup remains, including failed logging or uncertain start replies.

These are sampled predicates, **not an atomic ownership/idle lock**. A user or
firmware state change after the snapshot can race the host action. They do not
prove optical focus completion or H/position exposure alignment.

The corrected handler is not yet hardware-validated. `FP_NATIVE_FOCUS_CONTROL_2026-09-16.md` also found
that publishing new ARM code requires both the ROM data-cache maintenance and
instruction-cache invalidation helpers before first execution. The staged
installer now addresses that ordering explicitly; it still needs hardware
validation, and no code in this task was uploaded to the camera.

## Instruction publication and owned cleanup

The installer no longer calls `shell.put`: that path can execute a freshly
written RAM bulk loader/raw reader before the required instruction publication.
Instead it uploads all 250 code words using bounded read/write/readback repair,
checks echo ownership before each word, and verifies the complete code.
It then verifies record invalidation and the independent nonce seed.

Only these two audited no-argument ROM functions may be temporarily called
through echo, in this order:

1. `C000E91C`: data-cache clean/invalidate maintenance.
2. `C000EABC`: instruction-cache invalidation.

Each call requires original echo ownership, verified handler-pointer transition,
one bounded `TMO 1000 SHL echo` exchange with exact `OK \n` response, and guarded
restoration/readback to `C03D99A0`. Uncertain dispatch responses are not retried.
After publication, the installer rechecks code and both parameter words before
arming the snapshot. A matching previously installed snapshot is first restored
to original echo and then republished; matching RAM bytes alone are not accepted
as proof of instruction-cache freshness.

One outer cleanup scope covers partial upload, parameters, cache calls, arming
and normal handler use. It restores only original or specifically owned
temporary handlers. An observed foreign echo pointer is reported and left
untouched, even during cleanup. Restoration failure is fatal, never a warning.
Echo transitions use bounded retries for idempotent writes only; a failed ROM
restoration can receive one further bounded attempt from the outer cleanup.
The collector still borrows its established scratch region without restoring
its prior bytes; this change does not silently expand that lease.

The host lock cannot exclude another client that ignores it, and separate
read/write ownership checks are not an atomic camera-side compare-and-swap.
The ROM calls have bounded host waits, not a claimed hardware watchdog. Existing
memory-read/write transport behavior is otherwise unchanged.

## Offline verification

50 collector tests pass, including legacy unknown-state migration, mixed-size
framing, every busy-byte refusal, full-width PTP rejection, freshness, nonce
placement, paired release and ownership checks; upload/parameter failures,
publication order, exact responses, no cache-call retries, uncertain arming,
foreign owners, failed restoration and known-snapshot republishing are mocked.
`inspect` still assembles to 1000 bytes with the same SHA-256 and does not touch
the camera. Read-only replay of all 592 historical `s1-right-b` records succeeds;
all are correctly marked recording-unknown. Existing evidence is untouched.
