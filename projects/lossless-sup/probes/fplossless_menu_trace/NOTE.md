# fpLossless private two-option row: static trace

Host-only read-only firmware research, 2026-09-15. No camera connection, USB,
renderer, event, native allocator, or recording was executed for this trace.

Input: `out/seg0_c0000000.bin`, 49,245,696 bytes, SHA-256
`aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`.
Addresses below are runtime addresses; subtract `0xC0000000` for file offsets.
Decompiler citations refer to `out/decomp/full/blk_c04.c` and `blk_c05.c`.

## Two-option donor

MainY4 page `[C214A0C0,C217CDEE)`, SHA-256
`8f5008dd58b5dcaef14226245f78822c6b05c038e939b56bb1ff5939238189be`.
Its 3,320-byte allocation header has SHA-256
`a5d5df18308248df0902c200d3aa111d69200b63b0473b1c5648d5b27b61bdb8`.

Use `[C216C8B8,C2172BC6)`, 25,358 bytes, 21 objects, SHA-256
`33eca8104f7ab0630c7544e9769f6daaa7d0bc6c62856805379ea9ef0d70b48b`.
It is the `Y4_4_STILL` wrapper (19457, parent 196), containing
`MenuItem_Select` (19459), not `MenuItem_SelectJump`. There is no JumpEvent.
This is a generic two-item donor; its stock text identifiers are **not evidence
that its original user-facing choices are OFF and ON**.

Private-row recipe, all fields individually pinned:

- Reparent wrapper 19457 from 196 to MainB2 root 116; remap all internal IDs.
- Wrapper objectBase `C216C8DC`: position x/y at +32/+36 is `(0,162)`;
  change y to 243. Visibility clip `C216C904`, owner 19457/id 1, has
  `(time 0,value 1),(time 66,value 0)`; invert values to CINE-only `(0,0),(66,1)`.
- Bind `ST_CableRelease` to a private variable at `C216CEB3+40`,
  `C216CEE8+36`, `C216CF15+54`, `C216D8F2+36`, `C216D986+36`.
  `ST_CableReleaseAj` and `ST_CableReleaseFix` are local animation-group names,
  not separate camera-variable writes.
- Popup OFF drawText `C216DD72+32` is stock `1304`; ON `C2170209+32`
  is `1305`. Replace with literal OFF/ON and set the following byte flag to 0.
- Row title `C2172640+32` is `1303_S`; replace with literal fpLossless and
  flag 0. Its text animation `C2172735` must also use fpLossless for both keys.
- Row summary `C21727CD+32` is `1304`; replace with literal OFF and flag 0.
  Summary text animation `C21728BE` uses `1304_R`/`1305` at time 0/66;
  replace with OFF/ON. This also avoids later animation restoring stock text.
- Actual choice value is List object 19463, controlValue `C216D3EB`.
  Its original mask 0x08 only makes loop=true explicit. Make min=0, max=1,
  value=0, loop=true explicit (mask 0x0F) instead of relying on omitted defaults.
  Do not change root 19459's max=7: that control is a UI-state/animation index.
- Confirm writes at `C216D8F2` and `C216D986` read the List's `controlValue.value`
  using source-type 2 (Property), then return focus locally.
- Up `C216CB41`: Previous (operation 1), loop=true. Down `C216CBC7`:
  default Next (operation 0), loop=true. Neither contains a destination object ID.

The builder must consume each donor property body completely using native
schemas, rather than scanning arbitrary words for matching IDs. Runtime focus
behavior is still unverified.

## Explicit shared-animation dependencies

Do not preserve arbitrary matching IDs across pages. The following dependencies
were checked by identity and exact source/target record bytes:

| Dependency | MainY4 | MainB2 | Bytes | SHA-256 |
| --- | --- | --- | ---: | --- |
| Footer group, owner 37 | C217B6A4 | C205465E | 1207 | `6f8b51030a8860ffc4827b3191e5778e4288eb5ac26053fbd125751b48ae08d8` |
| Footer clip owner 19499/id 2 | C217BD26 | C2054CE0 | 538 | `965edff2eeaea03e4066c3774af3612125d24a7881d0a3517c9e5a3f3715d62e` |
| Footer clip owner 19500/id 2 | C217BFCD | C2054F87 | 598 | `93e2b07d2ecd8d1563e2bdd4df4f8d69eda97e5f87c8bb4d0143ca25895ca4d1` |
| Header UpDown group, owner 55 | C215002B | C20360F7 | 65 | `3705817b07268d6b43a5b4b050caf50d312563ee9765e5cac8340aaf28e849b4` |
| Header UpDown clip owner 55/id 29 | C214FE1A | C2035EE6 | 188 | `365b09cac659d39414d4b68d51763ca84ccd850c3714985daf8546e85799523c` |

Owner 37 is Footer, parent 1, child count 2, at Y4 `C217B650` and B2 `C205460A`.
Owner 55 is HeaderActiveTab, parent 56, child count 3, at Y4 `C214EDFD` and
B2 `C2034EF7`. The donor's only external animation-owner fields are
`C216CA1B+36` and `C216D533+36` → 37, and `C216CB0F+36` and `C216CB95+36` → 55.

## `submenu_05` is real, but page-dependent

The donor's `controlAppState` at `C216CA4D+36` requests `submenu_05`.
Although MainB2's current row records do not use that string, its width table
does contain it; absence in stock row records is not an invalid-state proof.

`CommonAppSyncReqListener::v1` at `C048BE80` (`blk_c04.c:106390`) calls
`C04B63F8` → `C04B6238` → `C04B6308`. The last function searches the current
screen's `(request-name,width)` table. The width is passed through notifier
v492 at `C059B330` (`blk_c05.c:117163`) to the `submenu_width` variable.

MainB2 screen descriptor `C0CDEE28` is `{MainB2,0x1F,C04B8E30}`. ARM code at
`C04B8E30` returns `C0CE80C0 + language_index*56`. Each language has six entries
`submenu_01` through `submenu_06`, then the null/zero sentinel. First three
language rows give `_05` widths 518/468/556 and `_06` widths 197/184/212.
MainY4 uses `C04B8F70` → `C0CE9600 + language_index*48`, and its `_05` widths
are 274/356/341. Therefore moving `_05` changes sizing to the B2 recipe.

The same listener also sends `{1,request,0}` through `C0515560` → `C05170F8`
as queued event 0x44. Its downstream behavior has **not** been fully proved by
this trace. Do not call the request generally inert, substitute another stock
request solely because its width looks better, or remove the runtime gate on
the strength of the width branch alone.

## Allocation-header ordering is not a per-record ordinal contract

`FUN_c05e6400` parses tag 0x10002 in `case 1` after subtracting 0x10001
(`blk_c05.c:185831`). The header's group/clip/key vectors are read and reduced
to one byte total; individual entries and array-order cursors are not retained.

- Component entries: `native_component_size * count`, plus 4 bytes per component.
- Group entry `(states,transitions,clip_refs)` contributes
  `0xA0 + states*0x38 + transitions*0x4C + clip_refs*8`, plus 4 bytes per group.
- Clip-property entries contribute `property_count*0x24`.
- Property-key entries contribute `0x20 + key_count*0x38`.
- Trailing entries contribute `count*0x20`.
- Object/special-object terms are `objects*0x128 + special_objects*0x160`.
  The final expression also has the native `-4` adjustment.

The only retained result is the arena allocator returned by `C05E8EF8`, stored
at page-context +0x0C (`blk_c05.c:185871`); object bookkeeping is separate.
`C05E8EF8` allocates requested arena bytes +0x50 and initializes the allocator
with `C05E8F50` (`blk_c05.c:187476`). Its allocate callback `C05E8DC0` is a
four-byte-aligned bump allocator; exhaustion delegates to the backing allocator.

Group parsing (tag 0x1000B, switch case 10) calls `C05E2988` with counts read
from the group record itself. That constructor (`blk_c05.c:181733`) requests
0xA0 plus state/transition/reference containers from the arena; it does not
look up a header ordinal. Clip-property construction similarly calls
`C05E2738` with the record's key count (`blk_c05.c:181539`).

Conclusion: appending additive budget entries while inserting cloned records
before Footer does not itself misalign allocation slots. Preserve all original
budget/reserve contributions and verify the candidate's total demand. This is
not proof that any resource candidate is deployable or that its runtime hooks,
private-variable lifetime, navigation, or recording behavior work.
