# fpLossless private-variable native probe (offline only)

This executes pinned fp V5.02 **original Thumb instructions** for variable
registration, lookup, vector growth, name hashing, map insertion/sort/lookup.
It is not a camera program, hook, deployment artifact, or complete UI builder.

The entire supplied seg0 is read/execute-only during emulation. Writes are
restricted to synthetic RAM `0x10000000..0x10040000`; stub trampolines are RX.
Every executed instruction must belong to an explicit native interval or one of
five stub service addresses. Unknown execution fails closed. Every native call
has a 20,000-instruction / 250 ms limit and must return with SP restored.

Input: exactly 49,245,696 bytes, SHA-256
`aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`.

## Run

The existing local Unicorn 2.1.4 cache can be used without installation:

```sh
PYTHONPATH=/private/tmp/raw14-unicorn-cache/archive-v0/NzmDie5Nzfbv0-EL/lib/python3.9/site-packages \
/usr/bin/python3 -B \
/Users/dido/Developer.localized/SIGMAfp_re/projects/lossless-sup/probes/fplossless_registry_probe/test_registry_probe.py \
--seg0 /Users/dido/Developer.localized/SIGMAfp_re/out/seg0_c0000000.bin
```

This temporary dependency path may expire; missing Unicorn is an error, not a
skipped success. On this Mac the desktop sandbox allowed engine construction
but terminated the first JIT execution with exit 132; the same narrowly scoped
offline command ran after explicit execution escalation. No download, camera,
USB transport, network client, or firmware writes are involved.

## What is native and what is not

Native address intervals are in `registry_probe.py:NATIVE` and repeated in JSON
test output. In particular, these are **not stubbed**:

- `C05DB308`: register variable definitions.
- `C05DB418` / `C05DCA88`: registry/app lookup.
- `C05D9EB0`: derive shared registry address.
- `C05D74A8`, `C05D7528`, `C05D75B8`: vector append/get/grow.
- `C05ED1F0`, `C05ED248`, `C05ED298`, `C05ED2B0`, `C05ED3B8`: map reserve,
  append, sort-key, sort and lookup.
- `C05E9DE8`: original FNV-1a name hash.

The following services are explicitly **stubbed**:

- `C05DB868`: Lua Variable wrapper, configurable success/failure. A successful
  stub merely records the name; it does not create a real Lua object.
- `C0013E2C`: bounded ASCII byte-string comparison.
- Synthetic `20000000/20000010/20000020`: allocator allocate/free/reallocate.
  Allocation failures are injected by call index. These are not original heap
  functions, and no real allocator concurrency/fragmentation is tested.

The initialized app/registry/allocator objects are **synthetic**. Original
resource parsing, VarData initialization, Lua, variable notifications, UI
binding, teardown and persistence are not executed. Source-level expectations
about those components must not be promoted to runtime success by these tests.

## Verified call shape

All four functions below are Thumb: native function pointers must be `EA | 1`.
These tested signatures use only r0-r2 and no caller stack arguments:

```c
struct VariableDefinition { uint32_t type; const char *name; uint32_t value; };
int Register(App *app, uint32_t count, const VariableDefinition *definitions);
// C05DB309; definition stride 12, integer type 0.

int LookupRegistry(Registry *registry, const char *name, Descriptor **out);
// C05DB419; returns 0 both for hit and miss; miss writes NULL.

int LookupApp(App *app, const char *name, Descriptor **out);
// C05DCA89; app/arguments/Lua marker checked before LookupRegistry.

int MapAppend(Map *map, const char *name, Descriptor *value);
// C05ED249; original success epilogue at C05ED28E explicitly sets r0=0.
```

`Registry = *(app + 0x888) + 0x60`; `Map = Registry + 0x14`.
The 32-byte descriptor stores type/name/value/index at +0/+4/+8/+12; the
remaining four words initialize to zero. **Name pointers are borrowed** by both
descriptor and map, not duplicated. Stable storage is mandatory; mutating a
name would also invalidate the stored hash and is not a supported rename.

## Findings and publication boundaries

The 15-case suite covers default OFF, initial ON, borrowed name identity,
direct/app lookups and miss semantics, native map return value, six distinct
names with successful native vector/map growth and sort, invalid arguments,
and these fault boundaries:

| Failure | Return | Visible native state |
|---|---:|---|
| Initial map-reserve allocation | 1 | No descriptor / Lua call / vector publish |
| Descriptor allocation | 1 | No new descriptor / Lua call / vector publish |
| Lua wrapper returns 3 | 3 | Allocated descriptor is **not freed**, vector/map untouched |
| Vector growth allocation | 1 | Descriptor freed; successful Lua stub was **not rolled back** |
| Map entry-array growth | 1 | Descriptor already published in vector; absent from name map |
| Map index-array growth | 1 | Vector already published; entry pointer changed but capacity/index pointer remain old |

The latter two cases seed a full synthetic map to reach the exact map-growth
boundary; seed descriptors are inert synthetic pointers and are not claimed to
be a complete original registry. Each allocation failure leaves the old
allocation alive as a normal failed realloc would; this is the explicit stub
contract, not a measurement of the camera allocator.

Consequently `Register` is **not transactional**. A nonzero return does not mean
"nothing happened" and must not trigger blind retries. This probe deliberately
does not implement recovery, unlinking, original Lua rollback or a loader.
Duplicate names, string/float registration, concurrent access and original
resource-lifetime hooks remain outside this bounded suite.

Source mapping: `out/decomp/full/blk_c05.c`, registration line 173633,
lookup 173719, app lookup 175311, original resource caller 185538–185561,
map insertion 192503. Decompiler's `void` type for map insertion is disproved by
its original success epilogue and these machine-code tests.
