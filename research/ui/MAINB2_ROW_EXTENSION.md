# MainB2: extending the native SHOOT page 2

2026-09-15. Shared static UI evidence for firmware 5.02. No camera execution.
This describes native resource structure, not a verified installation recipe.
Product policy and testing belong under `projects/lossless-sup`.

## Pinned resource input

Use `out/seg0_c0000000.bin` (49,245,696 bytes), SHA-256
`aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`.
Do not substitute the differently hashed `MAIN_c0000000.bin` or loosen a hash
guard. Addresses below are runtime addresses; file offset = address − C0000000.

| Region | Address / length | SHA-256 |
| --- | --- | --- |
| MainB2 | C2030364..C2055DB0 / 154188 | `10ed690e589bf7899ca022a3f108116d6a25ff9579081cd637e6ba8bcc99bc41` |
| Allocation header | C2030364 / 3028 | `4ffde39e76ffc7ee23933b0b84416e688a1f10866ba4889544894e0f1a82bf8c` |
| Audio-row donor | C204DACA..C205460A / 27456 | `006113cce5bb460973e5934e02e1fe8d3d32c7fb325160cd8bbd46abd3cf3fb3` |

NBU screen declaration C18EC77C (inside tag 10001, not an NBR index) identifies MainB2 (hash BDD26684, string-pool offset
1A3B8, page-relative offset 76FF04). NBU starts C18C0460; string pool C18C0474.
The page contains 1392 length-delimited records; records are not necessarily
word-aligned. The root B2 object ID is 116, at C2037C1B.

## Native class and binding path

GUI page ID **10** (`MainB2`, C0D0DB70) is not event-handler ID **1F**
(`MainB2`, C0CDEE28). GUI factory C054A510 case 10 constructs UicGuiMenuB2.
Constructor C0583430 sets vtable C0D1DF1C and owner global C37B75D8;
destructor C0583470 clears the owner. Binding context is `this+1C`.

Attach C05834D8 subscribes to CM_DCCrop, ST_AspectRatio and MV_AudioRecord;
detach C0583538 unsubscribes them. C0560FB0/C0561080 are subscription wrappers,
**not widget or app-variable creation APIs**. C05DCB18 looks up a named variable
using C05DB418, then attaches a callback. Missing variables return an error.
C0593F30 queues GUI variable updates; it does not create a private variable.

The stock callbacks C0583598/C05835F0/C0583648 convert UI values and call factory
settings setters. A new independent feature must not reuse those setters or
their storage. Preserve stock attach/detach behavior and give new callbacks
separate ownership/lifetime checks. Verify callback calling convention from
instructions, not just decompiler argument recovery, before installation.

Sources: `out/decomp/full/blk_c05.c`, functions above; native allocation-header
parser is around line 185834. The archived
`research/other/external/FP3K-technical-handoff-2026-09-10/tools/inspect_uic_resources.py`
provides the pinned resource parser. Its raw string candidates are not a typed
field schema and cannot justify global word replacement.

### Private-variable registration candidate

A registration primitive does exist: C05DB308 accepts an app context, a count,
and 12-byte definitions `{type, borrowed_name_pointer, initial_value}`. The
stock parser's `0x2FFFE` branch calls it one definition at a time after registry
initialization (decomp lines 185538–185561). Type 0 is an integer. Its descriptor
is 32 bytes: type/name/value/index at +00/+04/+08/+0C; UI lists at +10/+14;
subscription at +18; calculated dependency list at +1C.

A candidate sequence is: after stock initialization, lookup a private name;
if absent, register one integer defaulting to 0; lookup again and validate its
type and descriptor; only then bind the private row. Do not reinitialize the
whole registry with C05DB198/VarData. C05DB418 returns success with a null output
when absent, so a zero return code alone is not proof of existence.

This is **not a callable camera adapter yet**. The name pointer is
borrowed, not copied; it must outlive the registry. C05DB868 creates a Lua
Variable wrapper, and vector/map publication is multi-stage without a proven
atomic rollback. No single-variable removal counterpart is established.
C05DB268/C05DB218 tear down the registry, so descriptors must not be cached
across resource reload or warm reboot. Allocator capacity for late insertion,
synchronized timing and failure cleanup must be verified before calling it.
The offline original-instruction probe below now resolves the integer
registration/lookup ABI and C05ED248 return; that does not prove native Lua,
heap or page-lifetime integration.

### Original-instruction registry probe (offline)

`tools/native_variable_probe/` executes pinned original Thumb instructions
with synthetic app/registry/RAM and explicit allocator, Lua-wrapper and strcmp
service substitutes. Fifteen tests pass, with no skipped cases. The native
registration, lookup, vector/map growth, hashing and sorting paths are executed;
original initialization, Lua, allocator and callbacks are not.

| Thumb entry | Tested registers r0/r1/r2 |
| --- | --- |
| C05DB309 | app / definition count / `{type,name,value}*` |
| C05DB419 | registry / name / descriptor output pointer |
| C05DCA89 | app / name / descriptor output pointer |
| C05ED249 | map / name / descriptor |

All tested shapes have no caller stack arguments. Lookup returns zero for both
hit and miss; a miss sets the output pointer to NULL. C05ED248 actually returns
zero on successful insertion, despite the decompiler's `void` signature.
These Thumb entrypoints must not be confused with ARM MainB2 attach/detach.

**Registration is not transactional.** Injected Lua failure leaks the new
descriptor; vector-growth failure does not undo the Lua wrapper; map-growth
failure can leave the descriptor in the vector but absent from the name map.
Do not assume a nonzero return means no mutation and blindly retry. The
probe does not implement recovery. Its README lists all stub boundaries and
the instruction allowlist. Product evidence belongs in
`projects/lossless-sup/build/native-variable-probe-20260915.json`.

## CINE rows and a fourth-row structural candidate

| Row | Root ID / address | CINE y |
| --- | --- | --- |
| DC crop: B2_1_CINE | 21878 / C2040830 | 0 |
| Recording settings: B2_5 | 121 / C204CB21 | 81 |
| Audio: B2_6 | 122 / C204DACA | 162 |

B2_2/B2_3 are real STILL rows, not unused entries. A fourth CINE row at y=243
would fit within B2's 486-pixel height, but fit does not prove focus traversal.
The audio subtree contains 187 records and 23 objects. Footer starts C205460A,
the candidate insertion point for another complete subtree in a private page.

A complete donor clone would require:

- Schema-aware remapping of all 23 object IDs, parent/owner/group references
  and packed focus destinations. New IDs must be collision-checked.
- Root B2 record C2037C1B, BE32 +16 child count 6→7.
- Donor geometry clip C204DB16: preserve time 0 invisible / time 66 visible,
  change CINE y=162 (43220000) to y=243 (43730000).
- ModeChange group C20318F7: clip-reference count at +16 is 6; insert
  `(newRootId, 1)` before +118, retaining its final 8 bytes. Count 6→7,
  record length 126→134. Header group index 3 already reserves (2,0,7).
- Expand allocation header budgets and object lookup capacity, not just the
  serialized records. Preserve existing unused capacity.

For the unchanged full donor, expected allocation-header changes are:

| Budget | Original | Full clone |
| --- | ---: | ---: |
| Header bytes | 3028 | 3352 |
| Objects | 193 | 216 |
| Component kinds | 23 | 23 |
| Animation groups | 52 | 60 |
| Clip budget | 180 | 200 |
| Property budget | 366 | 403 |

Donor header group entries are original entries 41..48:
`(2,0,3),(2,0,2),(1,0,4),(2,0,1),(1,0,2),(1,0,7),(2,0,1),(2,0,1)`.
Donor clips have property counts
`2,4,1,1,2,1,1,1,1,1,2,1,2,1,5,4,1,1,1,4`.
There are 37 properties / 1839 keys: two properties have 885 keys each,
34 have two, one has one. Retain them until their purpose is proven.
Serialized page clips/properties total 159/364, less than header 180/366;
recomputing header totals from records would discard stock reserved capacity.

## Unresolved behavior: do not deploy a raw audio clone

The donor is **MenuItem_SelectJump**, not a pure OFF/ON control. These typed
references and actions require isolation, not merely a label change:

| Reference | Record + field offset |
| --- | --- |
| MV_AudioRecord | C204E14D+40, C204E187+36, C204E1B4+54, C204F183+36, C204F23C+36 |
| B2_6 jump target | C204E6C6+36 |
| SUB_MV_AudioRecord | C204EC7A+36, C204ED97+36 |
| Audio label 0326_C | C2054060 |

JumpEvent subtree is C204E5A5..C204E85F. Removing only that subtree does not
remove remaining submenu actions. Pure OFF/ON does not require a stock submenu
ID; do not invent one. MENU_Level1 at C204DC51 contains a packed focus value.
Up/Down controlFocus at C204DD87/C204DE0D needs actual traversal verification.

Before native use, prove private variable registration, pure selection events,
value refresh, enabled-state behavior, cursor navigation, strings, complete
page allocation, startup timing and page rebuild/lifetime. A 512-byte
record-copy scratch buffer cannot hold the existing 3028-byte page header or
add a new subtree. A late parser hook cannot be assumed to replay an already
parsed page. Existing OpenGate hooks at C05E6400/C05E84D8/C05E5B58 require shared
ownership or explicit merge refusal; a second branch at the same address is
not a compatible independent module.

## Typed component schemas: 18 ordinary kinds

The reusable extractor and its evidence are
`tools/native_component_schema.py`, `tools/component-schemas-v502.json` and
`tools/README_COMPONENT_SCHEMAS.md`. The 13-test suite passes without skips.
Fourteen property tables were captured by executing original constructor
prefixes with synthetic RAM; four were recovered by checking original
argument-setting instructions, without running renderer-dependent setup.
The JSON distinguishes these evidence types. No property registration,
renderer, events, camera display or device transport was executed.

Descriptors are LE `{type,name-pointer,default-raw}`, 12 bytes each; serialized
values are BE and present only for set property-mask bits. Type 11 consumes
five bytes (string offset plus resolver flag), so subsequent fields may be
unaligned. Type 14 is an object reference. This allows reference remapping
without altering numeric enums, local component IDs or float values that
coincidentally equal an object ID.

`drawImage`, `drawRect` and `drawText` have two common trailing fields. Native
`C05D5E30` adds them for component type 4; `C05D5670` returns `rect`/type5
at count−2 (`C2DFFC00`) and `layout`/type10 at count−1 (`C2DFFBF4`). Thus
drawText's 30 declared fields become 32 serialized fields. The separate
`animationClip` record format must not be parsed as an ordinary property list.

For literal OFF/ON or a new English row label, type-11 resolver flag must be
zero. `C05D6D00` routes resolver-enabled text through `C05EC220`; appending
English text to the pool while keeping that flag enabled is insufficient.
Text-animation keys must be updated as well as the initial drawText value.

## Pure two-choice donor (preferred over Audio SelectJump)

MainY4 contains a generic two-item `MenuItem_Select` for ST_CableRelease:
`C216C8B8..C2172BC6`, 25358 bytes, 148 records, 21 objects,
SHA-256 `33eca8104f7ab0630c7544e9769f6daaa7d0bc6c62856805379ea9ef0d70b48b`.
It has no Audio jump subtree. Its initial labels are 1304 / 1305 (summary
animation uses 1304_R / 1305), not proof of
OFF/ON semantics; replace both with literal product choices. Its five setting
references need a separate private binding. The List controlValue needs an
explicit binary min/max/value of 0/1/0; the outer controlValue maximum is a
UI-animation state index and must not be changed to 1.

This donor crosses pages. Reparenting its root 196→116, mapping its internal
objects, changing y=162→243 and switching STILL/CINE visibility are only the
structural part. External Footer/Header animation references and app-state
requests must be checked separately; matching numeric IDs are not sufficient
proof that two pages share the same objects or behavior. Product-specific
transformation and evidence live in `fpSup/lossless/menu/` and
`projects/lossless-sup/build/`, not in this shared research note.

### Allocation vector order and page-dependent requests

Native `C05E6400` tag 0x10002 reduces the header's component/group/clip/key
vectors to an arena byte total; it does not retain a per-record budget vector
cursor. `C05E8EF8` creates the arena, whose bump allocator is `C05E8DC0`.
Group construction at `C05E2988` and key construction at `C05E2738` use the
counts from their own records. Therefore adding budget entries at the end
while inserting row records before Footer does not inherently misalign slots.
All stock reserve contributions must still be preserved; this is static
allocator evidence, not execution of a rebuilt page's allocation path.

`submenu_05` is a real width-table entry on MainB2 even though its stock row
records do not use it. `C04B8E30` selects `C0CE80C0 + language*56`; the first
three `_05` widths are 518/468/556, unlike MainY4's 274/356/341. Moving a row
between pages changes that sizing recipe. The sync listener also queues an
event, whose complete downstream behavior remains unproved. Do not treat the
name as inert or approve it based only on the width lookup. Cross-page
Footer/Header dependencies likewise need source/target identity and exact
record checks, not merely equal object IDs.

## 2026-09-16: subscription, dispatch and fixed-width findings

The [original-instruction binding probe](tools/native_variable_probe/README_BINDING.md)
adds 18 bounded tests using synthetic RAM and explicit Lua/allocator/callback
substitutes. Native named setters write before notification and ignore callback
error: rejecting a boolean choice requires explicitly restoring its value.
Unsubscribe immediately frees the copied callback pair and does not exclude
concurrent notification. A safe owner must exclude notifications before removal
and drain queued/active users afterward; retaining only callback context is
insufficient. These are constructed instruction interleavings, not camera OS
scheduling measurements.

Static callback-table initialization is ordinary ARM code at
C05123D8..C0512738, not a missing relocation. It fills 70 active event slots
plus the sentinel callback. Event 0x44 uses C0511BB0, forwards payload at +4 to
handler vtable +0x124. MainRec2's C0451C08 dispatches type 1 to +0x160,
C0453248, which returns 1. Earlier manager handlers are not proven inert.

A stock controlAppState action defaults app-sync-request to true. A no-send
action must explicitly select prop1 and prop5 as false (mask 0x22), not merely
clear its property mask. controlAnimation operation 7 interprets ApplyFrame
text as an app-variable name, not a numeric literal. These are shared native
semantics; the fixed-popup design choice and product-specific source pins live
in `projects/lossless-sup/notes/FIXED_POPUP.md`.

## 2026-09-16: outer loader and actual choice-control boundary

See [lazy-page selector evidence](tools/native_page_probe/README.md) for the
actual C05E82F1 route, cache bypass and first-parse register contract. Sixteen
bounded tests distinguish ordinary return 0, terminal return 1, missing-name
outer 0 and unsafe nonzero-error publication. A per-record hook must not return
a lease error as if the stock loader would roll back.

See [choice-control evidence](tools/native_control_probe/README.md) for separate
saved/cursor controls, A2P permission bindings, float-property s0 ABI and the
pending-repeat counterexample. Fourteen bounded cases run original instruction
slices with named substitutes, not a complete renderer. Root max-value must
not be changed to simulate disabling ON.
