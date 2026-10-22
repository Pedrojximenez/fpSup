# MainB2 lazy page boundary — pinned offline evidence

2026-09-16. Shared UI research staging only. No camera, USB, network, firmware
patch, native installation, resource publication or production hooks.

## Result

The missing lazy boundary is **Thumb `C05E82F1(app, screen)`**, not the whole-NBU
initializer `C05E6311`. The native parser table at `C2E00360` contains its pointer
at `+0C` (`C2E0036C`). `C05D90F0` calls `[app+0C]+0C` with `r0=app`, `r1=screen`.
`C05D9391(screen)` routes through that wrapper; ARM `C0560B08` calls it from the
UI runtime's page-load path. `C0560A80` first obtains the named screen through
`C05E0758`, then calls `C0560B08`. This names a **runtime screen descriptor**,
not the C++ UicGuiMenuB2 object and not handler ID `1F`.

The test harness executes pinned original Thumb instructions with synthetic
RAM and explicit service substitutes. It proves selector/record behavior,
not real renderer or allocator integration. It rejects any firmware except
49,245,696-byte `out/seg0_c0000000.bin`, SHA-256
`aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`.

## Screen declaration, not an NBR file index

The NBU top-level sequence starts:

| Address | Tag | Bytes | Meaning in observed parser |
| --- | --- | ---: | --- |
| `C18C046C` | `1` | 176160 | string pool |
| `C18EB48C` | `10001` | 7088 | 221 screen declarations |
| `C18ED03C` | `FFFFFFFF` | 8 | stop top-level registration pass |
| `C18ED044` | `10002` | 1092 | first serialized page allocation header |

`C18EC77C` is one 32-byte **screen declaration** inside tag `10001`; it is not
the separate NBR resource lookup structure handled by `C05E8D50`.
Its BE fields are:

```
BDD26684 0001A3B8 00000001 0076FF04 00000000 00000000 00000400 000002AA
hash/name-offset/flags/page-offset/x/y/width/height
```

The original `10001` branch (`C05E6618..C05E6772`) resolves `MainB2` against
`reader+14`, creates a 100-byte screen descriptor and stores its NBU reader at
`screen+24` (`C05E671E`). It builds `reader+A8` count / `reader+AC` array of
**44-byte runtime entries**:

```
+00 hash     +04 resolved name pointer     +08 NBU-relative page offset
+0C..+28 copied eight-word app resource context (app+54..+70)
```

The MainB2 offset is `76FF04`, thus `C18C0460 + 76FF04 = C2030364`.
One exact MainB2 declaration is exercised inside a bounded one-entry synthetic
declaration record; original `C05D9080`, parser entry construction, string
resolution and flag setting execute. Screen registry publication, arena,
geometry application and existing-screen lookup are substituted.

## Exact first-parse boundary

`C05E82F1` has two register arguments and no observed caller stack argument:

1. `C05E82F8`: read `screen+0C`. If nonzero, bypass all parsing and preflight,
   retain this root with `C05CFAE0`, and return **0**. An already-cached stock
   page cannot gain another row from a later per-record hook.
2. On a null cache, call an opaque preflight callback at `[[app]+0C]`
   (`C05E8304`). **Do not invent its prototype**: observed incoming registers
   are `r0=[app]`, `r1=callback address`, `r2=app`; result zero returns 2.
3. `screen+08` is the resolved name and `screen+24` is the shared NBU reader.
   Null reader returns 2. `C05E61F0(reader)` releases/zeros parser scratch arrays
   `+7C..+9C` before the runtime screen table is searched.
4. Search `reader+A8/+AC` in 44-byte steps, comparing names with `C0013E2C`.
   It does not search a GUI numeric ID and does not use the hash here.
5. For a matching entry: `C05E8342` writes `reader+0C=entry+0C`;
   `C05E8346` writes `reader+04=entry+08`.
6. **Immediately before BL at `C05E834A`:** `r0=reader`, `r4=reader`,
   `r5=screen`, `r6=matching entry`. Reader source `+24` remains the complete NBU
   `C18C0460`, cursor `+04=76FF04`, pool `+14=C18C0474`, and pool length
   `+10=176152`. This is the proven record-entry normalization point for the
   separate lease model. The selector-entry cursor itself is not this point.
7. Loop `C05E8348..8350` calls `C05E6401(reader)` while return is exactly 0.
   The parser has no meaningful r1-r3 input contract in this callsite.
8. After any nonzero stop, require `reader+50 != 0` (constructed object count)
   and `reader+B4 != 0` (root); otherwise return 2. With both nonzero, version
   `>=01060000` skips the old geometry inference path. `C05D9A48` stores root
   into `screen+0C` and retains it, then root release is called and temporary
   object-pointer array `reader+54` is freed. This leaves the native page cached.

Successful parse does **not** restore the shared reader source/pool/cursor. A
private source lease must do that deliberately without freeing strings still
borrowed by constructed objects. The native selector is not a scoped reader
lease and performs no source provenance or MainB2 fingerprint validation.

## Return behavior and unsafe assumptions

Original-instruction tests prove:

- Ordinary/unknown record returns **0 = continue**, with cursor advanced at
  least its declared size. Unknown tags are silently skipped.
- Exact `FFFFFFFF / 8` returns **1 = stop**, after consuming eight bytes.
- A malformed unknown record whose declared length is zero is not rejected;
  it still consumes eight bytes and returns 0. The native memory-reader BE32
  callback contains no source-bound check.
- A real stock MainB2 header consumes 3028 bytes, records object capacity 193
  and returns 0. Component sizes and arena calls are substituted; this proves
  field/cursor interpretation, **not** genuine native arena size/capacity.
- A scripted per-record result `0xBAD` still leads to selector success and root
  publication when count/root are nonzero. **Never return a lease error code
  directly through the `C05E6400` hook expecting native rollback.**
- A missing name returns **0 with screen+0C still null** after freeing the
  temporary pointer array. Therefore loader return 0 alone is not proof of
  MainB2 identity, first parse, completed resource or a valid root.
- Failure after stopping without count/root does not perform complete partial
  object teardown and does not clear the temporary pointer-array field.
  A second stock retry is not established as safe.

For a real hook the validated private page must be selected **before** any
private component construction. Ordinary and terminal record results must be
checked alongside exact cursor/tag/count and native root state. A poisoned
partial parse needs explicit outer-loader quarantine/unwind; returning 2 to
the inner parser caller is unsafe. The existing C lease intentionally does not
pretend to implement that native unwind.

## Cache release: static, not lifetime proof

`C05D91A0` calls `[app+0C]+10` (`C05E83F1`) while holding the app's conditional
lock (`app+888 -> +130/+134` callbacks +2C/+30). The latter releases the root.
If `C05D00D8(root)==1`, it locates the matching screen entry, frees its arena
from entry `+18`, clears `reader+0C`, clears entry `+18`, and sets `screen+0C=0`.
Otherwise it returns without clearing that cache. This is **not a general safe
cache-reset API**, and pending callbacks/lazy text references are not proven
drained. Do not force this path or modify cache fields while the camera is in use.

The C++ GUI object lifecycle and runtime screen cache are separate: closing the
menu does not prove destruction of all native page objects and strings.

## Reproduction and scope

```
PYTHONPATH=/path/to/unicorn/site-packages /usr/bin/python3 -B \
  /absolute/path/test_page_probe.py --seg0 /absolute/path/seg0_c0000000.bin \
  --report /absolute/path/evidence.json
```

Only `page_probe.py`, `test_page_probe.py`, `README.md` and generated evidence
are added under this staging folder. The imported pinned support module is
`research/ui/tools/native_variable_probe/registry_probe.py`. If relocated,
adjust that explicit import rather than changing firmware pins.

Selector tests script the record parser to isolate return/cache behavior. Other
tests execute the original record parser, memory BE32/seek, string resolution,
screen descriptor constructor/flags and root retain/publication. Service stubs:
opaque app preflight, strcmp, heap alloc/free, arena, existing screen lookup,
screen registration, geometry application, component-size lookup, root owner
assignment and root release. No native OS, Lua, renderer or allocator is run.
Firmware is RX, synthetic writes are RAM-bounded, instruction/time budgets are
enforced, and unknown native execution is rejected. VFP is enabled only in the
emulator because the original record parser saves/restores d8/d9. No camera
readiness, native hook composability, page lifetime or deployment is implied.
