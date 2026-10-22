# r86 RAW14 recording descriptor audit (offline)

## Exact artifact and result

`test_sensor_lab_raw14_descriptor_card.py` boots the sealed r86 debug card's
actual `AutoRun.txt` and `fpSup.BIN`, executes its relocated picker for M100 at
23.976p with native `eRawBitType=1`, then enters stock `C0437140` with the
class-4 arguments used by the `C0374268` kind-9 recording branch.  The stock
FieldAngle constructor executes the card's installed canvas hook.  The stock
RAW descriptor constructor, `C02E5B78` frame copy and `C03D9630` size function
also execute.

| Exact file | SHA-256 |
| --- | --- |
| `MANIFEST.json` | `ca82441fe8314c939d210462baddfe91aad8b44e2d6fd1403a7c52bb9548b45b` |
| `fpSup.BIN` | `28ac9adb81a0070b979066a43aa81d7d8f5b71f240c2ea092b181ffc19db81ce` |
| `AutoRun.txt` | `5dc89b8506e8ce408276a9eab61fbb9fda94d4a194b65f2fd17c9e410b8fe642` |

Observed result: the picker entry's profile is **87**, the constructed
FieldAngle's RAW plane code at canvas `+0x84` is **8**, and the native RAW
descriptor words `+0x20` (pixel-size enum) and `+0x24` (eRawBitType enum) are
**both 1**.  The 0x48-byte copy into `frame+0x10` equals the descriptor's first
0x48 bytes.  Native strip byte count is **15,887,592** for 4176×2174 RAW14,
matching independent packed-14 arithmetic.

As a sensitivity control, a separate emulator boots the same exact card and
replaces only the in-memory `C043A19C` canvas BL with its pinned stock MOV
before constructing the FieldAngle.  Its RAW plane code is **7** and both
descriptor enums are **0**.  The sealed card files are never changed.

## Fixture boundary

The test substitutes the unavailable runtime settings snapshot (`C0436B80`),
profile selector (`C04396B0` and its virtual method), two heap allocations
(`C0439C10`, `C0438980`), log calls (`C0019DC0`, `C001A0D8`) and two disposal
calls (`C0438828`, `C022ED50`).  The selector fixture takes profile 87 from
the actual picker entry; it does not seed that value independently.  The
native FieldAngle, canvas, format mapping, descriptor construction and size
instructions remain real.  The test does not run the full `C0374268` caller,
live global profile selection, sensor/DMA, compressed writer, or a recording.
An on-camera recording and DNG inspection remain necessary before claiming
hardware RAW14 support.

Run with `/usr/bin/python3 -B -m unittest -q
test_sensor_lab_raw14_descriptor_card` from `projects/open-gate/build`.
Unicorn needs an execution context that permits its ARM JIT mapping.

## Julien DATA+ / LJ92 applicability

The exact r86 manifest has **no** `C037DD50` writer hook, **no** `C04A1788`
predicate hook, and no lossless component source.  Its appended menu block
starts with `SLMP`; there is no `FPLM` block.  The Sensor Lab builder packages
the Sensor Lab plan and private menu, without the separate `fpSup/lossless`
component.  Julien's report describes an **added** LJEnc task reached through
his `C037DD50` hook and a compression flag/length injection before the stock
DNG writer.  His `C04A1788` patch forces DATA+ for RAW14 in that added
compression configuration.  Sensor Lab r86 does not install that task or
compressed-frame injection, so adding his predicate hook to this card would
not address a present LJ92 route.  The stock still-photo compression capability
does not by itself establish that Sensor Lab movie frames use it.
