# fpSup fixes — Ruari → bei (2026-10-11)

For bei's Claude. Two fixes, both from an independent reverse-engineer of the 5.02 image
(`image_C0000000.bin`, base 0xC0000000, Thumb/ARM). Fallible like any RE — flag anything that doesn't
match on your side. Nothing was run from bei's tree.

Contents of this zip:
- `05STOPFX.BIN` — built W2 record-pool stop-leak fix (a Loader sup). **[BUILT, UNTESTED ON CAMERA]**
- `dma-alias-resolved.md` — full derivation + provenance for fix 1.
- `HANDOVER.md` — this file.

---

## 1. DMA bus-address alias for raw-push — RESOLVED  [FIRMWARE-TRACED]
Answers the open `[P]` in `RAW_PUSH §3.1`: when pushing the raw Bayer frame at `0x50000000` over the
vendor bulk endpoint, **`0x50000000` goes into the TRB `bufptr` UNCHANGED** — no `−0x40000000`, no
`+0x40000000`.

The camera's own CPU→bus normalizer runs ~8× in DWC3 init (Thumb, VA `0xC01E3030`–`0xC01E315E`),
applied to the event buffer, scratchpad and each endpoint-context buffer base:

```
cmp addr,#0x40000000 ; blo .leave          ; addr < 0x40000000  -> +0x40000000 (at .add)
cmp addr,#0xC0000000 ; bhs .high           ; addr >= 0xC0000000 -> -0xC0000000 then +0x40000000 (= -0x80000000)
sub addr,#0x40000000 ; b .add              ; else (0x40000000..0xBFFFFFFF) -> -0x40000000 then +0x40000000 (= identity)
.high: sub addr,#0xC0000000
.add:  add addr,#0x40000000
.leave:
```

bus = f(CPU):
| CPU range | bus/DMA address the controller uses |
|---|---|
| `0x00000000–0x3FFFFFFF` (low alias) | CPU + 0x40000000 |
| `0x40000000–0xBFFFFFFF` (bus window) | CPU (identity) |
| `0xC0000000–0xFFFFFFFF` (cached window) | CPU − 0x80000000 |

`0x50000000` is inside `[0x40000000, 0xBFFFFFFF]` → identity. It is already a bus/DMA address (the imaging
pipeline writes the Bayer frame there as a DMA target), so point the TRB `bufptr` straight at
`0x50000000 + off`. Buffers that DO need conversion: TRB table / staging in the `0xC0000000` cached window
(→ `−0x80000000`, e.g. `0xC31E32C0`→`0x431E32C0`); a low-alias buffer (`<0x40000000`) is `+0x40000000`.

Optional one-shot confirm (no risk): TRB `bufptr=0x50000000, size=0x1000, ctrl=0x813`, StartTransfer;
diff the 4 KB received on the host against the top-left of a simultaneously-recorded internal CinemaDNG.
Match ⇒ identity confirmed (expected).

DWC3 register base confirmed same pass: DEPCMD family at `0x2100C800` (ep-indexed `<<4`), consistent with
DALEPENA `0x2100C720` and context area `0xC31E32xx`. Full derivation in `dma-alias-resolved.md`.

---

## 2. W2 record-pool stop-leak fix — `05STOPFX.BIN`  [BUILT, UNTESTED ON CAMERA]
Matches the EARLY_STOP_94 symptom. `FUN_c0377118` drops queued record nodes without releasing them, so
the 96-slot pool `MPoolFixed<4380,96>` @`0xC2F1F3D8` bleeds down (observed ~96→~52) and subsequent takes
degrade / stop.

Fix = one word at VA `0xC0377118`: `E92D4030` → `EA000160`. That turns the `push {..}` prologue into
`b FUN_c03776A0`, the "raw del" path that properly releases the flush (returns nodes to the pool).

Packaging: a 316-byte Loader sup (prefix `05`).
sha256 `f9f26a092c5676ead5771ba8be4aac9c3734e9ed0cd144002a73b3f6b657c9d9`.
**Not yet tested on camera** — treat as a candidate. Suggested check: log the pool free-count across
repeated start/stop and confirm it no longer trends down.

Provenance: Thumb/ARM disassembly of `image_C0000000.bin` (decode verified byte-exact against fpSup
stock-word asserts), llvm-objdump, 2026-10-11.
