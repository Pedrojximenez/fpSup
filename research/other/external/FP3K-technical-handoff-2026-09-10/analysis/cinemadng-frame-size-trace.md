# CinemaDNG frame sizing and recording handoff — fp 5.02

## Result

Executed the stock RAW size callback in an offline ARM emulator. It exactly
matches `StripByteCounts` for all ten returned UHD24 DNGs. Adding the observed
78,848-byte header to the RAW byte count rounded up to 512 also matches every
12,630,528-byte file. This is a byte-count result, not proof of RAM allocation
or successful full-height recording.

| Raster | Packed pixels, 12-bit | Stock size callback | Rounded to 512 |
|---|---:|---:|---:|
| 3856×2170 | 12,551,280 | 12,551,292 | 12,551,680 |
| 3032×2020 candidate | 9,186,960 | 9,186,968 | 9,187,328 |
| 3000×2000 | 9,000,000 | 9,000,000 | 9,000,448 |
| 6064×4042 | 36,766,032 | 36,766,044 | 36,766,208 |

The candidate's header size is not yet established. If the observed stock
header size were retained, a candidate DNG would occupy 9,266,176 bytes.
Do not hardcode that assumption into a patch.

## Reproducible verification

Run `analysis/venv/bin/python tools/verify_raw_frame_size_emulated.py` from the
workspace. Unicorn requires its JIT to run outside the macOS sandbox here.
The script has no camera access, verifies the MAIN SHA-256, maps firmware
read/execute, permits emulated writes only to a private stack, and limits
execution to 10,000 instructions per call. It stubs no firmware functions.
Twelve geometry/boundary cases and all ten captured DNG metadata records pass.
Machine-readable results: `firmware/raw-frame-size-emulation.json`.

## Byte-count call chain

* `C0020830` registers callback `C03D9630` through `C02DA818` in the registry
  returned by `C0021318` at `C307490C`.
* `C02DA770` obtains this registry and dispatches through `C02DA830`.
* `C03D9630` takes a descriptor, converts format at +20 via `C03D9668`,
  and passes width +0, height +4 and converted format to Thumb `C01AAA30`.
* `C01AAA30` calls Thumb `C0135D40`; its row helper is `C0135DB8`.
* For format0, ordinary row bytes are `align4(floor(width*3/2))`.
  The final row first rounds width up to a multiple of 12 pixels, then applies
  the same byte calculation. Total is `(height-1)*row + final_row`.
  Zero width or height returns zero. Other formats have different branches.

For stock width3856 the final row is12 bytes longer. For candidate width3032
it is8 bytes longer. Ordinary candidate row stride4548 agrees with the earlier
independent register-programming test of `C0630E90`. This does not prove the
peripheral's behavior or the buffer's capacity.

## Explicit CinemaDNG recording state

RTTI name `MovRecFuncStateCinemaDng` is at `C0B9C238`. Its constructor
`C038B258` installs table `C0B9C260` at object+10; singleton getter `C038B1B8`
returns `C358DC80`. `C038BC50` dispatches event+C=5 to `C038BD98` and
event+C=8/9 to `C038C058`.

These handlers resolve event+E8 through `C03753C0` using the manager returned
by `C0374220` (`C351FF44`). Lookup accepts indices below96 and reads
manager+4+4*index. Creation routine `C0374268` allocates a0x111C-byte frame
object. This is the control object, **not** the multi-megabyte pixel buffer.

The non-error event5 path calls `C038C5F8`, then invokes slot+10 on the object
returned by `C037DD08`, passing the frame's +10FC handle. `C038C5F8` uses
frame+4C and frame+14C in its handoff. The exact virtual target and pixel-buffer
allocation remain to be resolved.

The descriptor copied to frame+10 by `C02E5B78` is0x48 bytes. A nearby recording
path at `C0379FC0..C037A018` compares the size callback for controller+ A4 with
that for frame+10. If unequal, it calls `C030CFF0(…,0)`, sets controller+78,
and releases the frame handle. Therefore changing only one descriptor copy is
insufficient. Whether that branch runs in the user's exact CinemaDNG route
still needs confirmation; this is not an explanation of their stock stops.

## CinemaDNG file path

`C03A5348`, in the region referencing `CinemaDngFile.cpp`, obtains a descriptor
through input object's table+14 / slot+48. At `C03A540C` it calls `C02DA770`
and rounds the result up to512 at `C03A5418..C03A5424`.
At `C03A5490` it calls `C069ADE0` with the assembled file description.
`C069ADE0` walks a linked list rooted at file-description+8C; each node contains
next+0, data pointer+4, length+8. It builds pointer/length pairs and invokes
`C0366168`. Resolve the input object's slot+54 and list construction next to
connect the descriptor size to the actual write buffers.

`C03A4B00` also uses the size callback and adds alignment/overhead. Its consumer
`C03A4660` subtracts from a64-bit balance; this must not be presented as proof
of a pixel-buffer allocator. Likewise `C031A0F8` leads to a ten-entry history
with sensor-related values; the saved `record-raw-controller.asm` filename is
a working label, not a verified class identity.

## Still required for a usable full-height patch

1. Trace pixel-buffer ownership and descriptor propagation through the exact
   CinemaDNG acquisition/writer route; retain byte-count and alignment checks.
2. Establish full-height24 sensor timing and receiver configuration. Static
   table similarity to full-height30/25 does not prove dynamic setup equivalence.
3. Establish what the ratio2048 reduction hardware does to Bayer samples.
   Geometry and bandwidth alone do not prove that every pixel contributes.
4. Only then prepare a bounded reversible RAM prototype and a camera test.

No AutoRun package, sensor modification, flash image, or remote-control change
was produced by this step. No additional camera recording is needed for the
offline work above.
