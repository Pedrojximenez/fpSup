# Resolved: the DWC3 bus-address alias for raw-push (bei's open [P], RAW_PUSH §3.1)

**Question (bei):** when pushing the raw Bayer frame at `0x50000000` out over the vendor bulk endpoint,
does `0x50000000` go into the TRB `bufptr` as-is, or does it need the `−0x40000000` (CPU→bus) conversion
the other contexts use?

**Answer: `0x50000000` goes into the TRB `bufptr` UNCHANGED.** No `−0x40000000`, no `+0x40000000`.

## Where this comes from (firmware ground truth, not inference)
The DWC3 init path contains the camera's own CPU→bus address normalizer, applied to every pointer it
hands the controller (event buffer, scratchpad, and each endpoint-context buffer base). It runs ~8×
between `0xC01E3030` and `0xC01E315E` (Thumb; VA, image base 0xC0000000). The canonical form:

```
cmp   addr, #0x40000000
blo   .leave                 ; addr < 0x40000000
cmp   addr, #0xC0000000
bhs   .high                  ; addr >= 0xC0000000
sub   addr, #0x40000000      ; 0x40000000 <= addr < 0xC0000000
b     .add
.high: sub addr, #0xC0000000
.add:  add addr, #0x40000000
.leave:
```

Worked through, bus = f(CPU):
| CPU address range | result (bus/DMA address the controller uses) |
|---|---|
| `0x00000000 – 0x3FFFFFFF` (low alias) | **CPU + 0x40000000** |
| `0x40000000 – 0xBFFFFFFF` (bus window) | **CPU unchanged (identity)** |
| `0xC0000000 – 0xFFFFFFFF` (cached window, firmware lives here) | **CPU − 0x80000000** (e.g. 0xC0000000→0x40000000) |

So the three CPU-visible aliases of the same physical DRAM all normalize into the controller's bus
window **[0x40000000, 0xBFFFFFFF]**. The firmware stores both views per context: it normalizes the CPU
base (e.g. field `+0x38`) into the bus base (`+0x64`), and `+0x28`→`+0x54`, for the 7+4 contexts.

## Why `0x50000000` is identity-mapped
`0x50000000` already lies inside `[0x40000000, 0xBFFFFFFF]`, which is the controller's own bus window —
i.e. it is already a bus/DMA address (the imaging pipeline writes the Bayer frame there as a DMA target).
Running it through the normalizer returns it unchanged. So:
- point the TRB `bufptr` straight at `0x50000000 + offset`; **do not** apply any conversion.
- the thing that DID need conversion is her TRB *table* / any staging buffer in the `0xC0000000` cached
  window — that normalizes by `−0x80000000` (0xC31E32C0 → 0x431E32C0). If bei saw a "+0x40000000"
  relationship, her buffer was in the LOW alias (`<0x40000000`), where the rule is `+0x40000000`.
  Either way, apply the table above per the window the buffer is actually in; `0x50000000` is identity.

## Belt-and-braces confirmation test (optional, one-shot, no risk)
Program one TRB: `bufptr=0x50000000`, `size=0x1000`, `ctrl=0x813`; StartTransfer; on the host, compare
the 4 KB received against the top-left of a simultaneously-recorded internal CinemaDNG frame. Match ⇒
identity confirmed (expected). Zeros/garbage ⇒ the buffer was a different alias — apply the table.

## Provenance
Thumb disassembly of `F:\Claude\SigmaFP\fw\image_C0000000.bin` (our own decode, verified byte-exact in
notes/firmware-recon.md) with llvm-objdump, 2026-10-11. DWC3 register base confirmed in the same pass:
DEPCMD family at `0x2100C800` (ep-indexed `<<4`), matching bei's DALEPENA `0x2100C720` / context area
`0xC31E32xx`.
