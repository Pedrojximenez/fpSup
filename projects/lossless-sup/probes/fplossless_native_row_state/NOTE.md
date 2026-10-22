# Native row-state consumer and fixed-popup isolation

Host-only static research, 2026-09-16. No camera, USB, network, event dispatch,
native allocator, firmware execution, or recording was used. This note supersedes
the unresolved event-table interpretation in the previous menu trace; it does
not supersede the remaining native UI/resource/lifetime gates.

## Inputs and reproducibility

- `out/seg0_c0000000.bin`: 49,245,696 bytes, SHA-256
  `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`.
- `out/seg1_c2ef6e00.bin`: 236,032 bytes, SHA-256
  `0dcaca8f5441fe4ddc6ed801cb888e325df4e76006e4f53a1c3219809b22ce7b`.
- Donor `[C216C8B8,C2172BC6)`: SHA-256
  `33eca8104f7ab0630c7544e9769f6daaa7d0bc6c62856805379ea9ef0d70b48b`.

`verify_recipe.py --seg0 <explicit file> --seg1 <explicit file> --output <new JSON>`
reads only the two pinned files and writes a new evidence JSON, refusing overwrite.
`evidence.json` is the resulting static extraction. The native trace uses Capstone
only for disassembly. The fixed-popup recipe itself uses the Python standard
library and is imported by the separate candidate builder.

## The event callback is initialized by ordinary code, not missing relocation

Raw seg1 has 70 active eight-byte `(event_id, callback)` records beginning at
`C2F23848`, followed by the zero-event sentinel `C2F23A78`. The on-disk callback
words are zero, but `C05123D8..C0512738` is an initializer consisting entirely of
MOVW/MOVT, STR, and BX LR. It writes 71 callback words, including the sentinel's
unused callback. No native code was executed to extract these values: the
verifier accepts only this bounded immediate-store instruction sequence.

For event `0x44`, the entry is `C2F23A70`, and the callback slot is `C2F23A74`:

```text
C051271C MOVW r3, #0x1BB0
C0512720 MOVT r3, #0xC051
C0512724 STR  r3, [r0, #0x22C]    ; r0 = C2F23848
```

`C0510DA0` and `C0510EB8` really do advance by eight bytes and BLX the word at
entry +4. They do not use a C++ member-function adjustment or a second-word
virtual-offset encoding. The callback zero in the original file therefore was
not evidence of a missing consumer. This is static code evidence, not a claim
that the initializer or dispatch was run during this experiment.

## Bounded consumer / data contract

The existing `C048BE80` listener first updates width through
`C04B63F8 -> C04B6238 -> C04B6308`; it then passes `{1, request_string, 0}` to
`C0515560 -> C05170F8`, which queues event `0x44`.

The event envelope begins with four words:

| Offset | Meaning |
| --- | --- |
| +0 | Event ID `0x44` |
| +4 | Payload type `1` |
| +8 | Request-string pointer |
| +12 | Auxiliary value `0` |

`C0511BB0` receives `r0 = handler`, `r1 = event envelope`, loads the handler's
vtable pointer at handler +8, and invokes vtable +`0x124` with
`r1 = envelope +4`. `MenuRec2Handler` constructor `C0474778` installs vtable
`C0CD1C1C`. Its +`0x124` slot at `C0CD1D40` is `C0451C08`.

For payload type 1, `C0451C90..C0451CAC` calls vtable +`0x160` with the request
pointer as the second argument. MainRec2's slot `C0CD1D7C` is `C0453248`, which
only returns 1. Thus the intended MainRec2 branch itself does not write a camera
setting for this request. Logging and general dispatch still occur.

This does **not** establish that all runtime consumers are inert:
`EventMessageMgr::v1 C0510C38` can dispatch to up to four earlier handler slots
from owner +`0xB2C` through `C0510DA0`, before the current handler's `C0510EB8`
route. The queue also carries a borrowed request pointer, not a duplicated
string. Reusing stock sync solely to get width would retain unnecessary runtime
dispatch and lifetime coupling. The candidate below sends no such request.

## Minimal independent popup: fixed geometry, no additional private variable

The new default profile is `pure-fixed-gated`. `pure-select-gated` remains an
explicit historical comparison; `audio-gated` also remains unchanged.

Width **320** is an explicit UI design choice in the resource's 1024-wide
coordinate space. It is not a measured original width or a font-fit guarantee.
The donor's width clips establish these geometry relationships:

- List x = `1024 - width`; List size.w = `1024`.
- Three background drawables rect.w = `width`.
- OFF/ON text-object x = `81`; text drawable rect.w = `width - 140`.

The output's base properties are initialized directly, so correctness does not
depend on a first variable-change notification or a page-state callback.

| Source record | Typed field | Original | Fixed |
| --- | --- | ---: | ---: |
| C216D3A7 | +32 objectBase position.x | 532 | 704 |
| C216D3A7 | +40 objectBase size.w | 492 | 1024 |
| C216DB92, C21700DD, C2172574 | +44 drawRect rect.w | 492 | 320 |
| C216DD36, C21701CD | +32 objectBase position.x | -15 | 81 |
| C216DD72, C2170209 | +45 drawText rect.w | 444 | 180 |

The unaligned +45 is intentional: the preceding text property is a four-byte
pool reference plus one flag byte. It is decoded and source-pinned, not a scan
for numbers that happen to match.

For defense against a future accidental local animation, **all** relevant float
keys in six clips are frozen to the same base geometry: `C216D565`, `C216DBC6`,
`C216DDA7`, `C2170111`, `C217023E`, `C21725A8`. Their times/counts/properties are
unchanged. The retained local group at `C216D1FF` has its group/state names
renamed consistently to `fpLossless_FixedWidth`. It is no longer driven by a
shared-width event.

The donor's other `changePropertyByControl` actions touch only opacity,
is-visible, or controlValue; its other clips do not restore these width fields.
Those stock local show/hide/focus actions remain intact.

### Disconnect shared width and explicitly disable this sync action

Remove exactly two donor records:

- `C216CF50`, the `appVariableChangeEvent` watching `submenu_width`.
- `C216CF7D`, its `controlAnimation` action, operation 7 (ApplyFrame).

Operation 7 is **not** a numeric-expression setter. `C05F1170..C05F11EE` obtains
the `apply-frame` string, then looks it up as an application-variable name via
`C05DCA88`/`C05DCAB8`. Replacing the name with the text `"320"` would not establish
a literal frame value and is deliberately not used.

Preserve the focus action at `C216CA4D`, including owner/event/action IDs and
component kind, but change its body to `mask=0x22, prop1=0, prop5=0`, length 44.
These mean `app-sync-request=false` and `view-state-event=false`. No sync-request
string property is selected or created.

This explicit mask matters: native initializer `C05F1440` defaults prop1 to
**true**. Clearing the mask alone is unsafe. Action `C05F1398` gates both sync
routes (`C05DC8E0`/`C05DC9A0`) on prop1 and the view-state route (`C05DCB40`) on
prop5; both false prevents all three sends. Other framework actions, including
the ESC action `C216CE63`, are unchanged.

Budget/bookkeeping consequences:

- `C216C948` MenuItem_Select declared component capacity: 16 -> 15.
- Donor header contribution: appVariableChangeEvent -1, controlAnimation -1.
- Total serialized records -2; object count unchanged.
- Group/clip/key counts unchanged; frozen keys preserve allocated shapes.
- Focus event still has all five original actions; its no-op action is retained.
- Original MainB2 records change only in the existing three structural places:
  page header, ModeChange group, and B2 root child count. Stock Audio is untouched.

## Output and tests

`candidate-fixed/` contains only the gated page fragment, private string pool,
and manifest. It has **179,725 bytes / 1,538 records / 214 objects**.

- Page SHA-256: `33946d01b1fd9bca7cba72ef55ef53e16a0469a00e5a29f35896a46e43023633`.
- Pool SHA-256: `ea773283be884f8c40ca1f08d759d94157d3d58200398a92805ef3f8cd09ad96`.
- Builder suite: **35 unique tests PASS**, including 9 new fixed-profile tests.
- Recipe suite: **8 tests PASS**, including source/geometry tampering,
  reenabled sync, restored shared watcher, and width-restoring animation rejection.

For integration copy `build_menu_candidate.py`, `verify_recipe.py` and
`test_menu_candidate.py` together; `test_recipe.py` supplies optional additional
negative tests with explicit `FPLOSSLESS_SEG0`. The helper is resolved relative
to the builder file, not the caller's working directory. Original source SHA
was checked unchanged after the trace. No canonical file was edited here.

The specific `PRIVATE_ROW_STATE_UNRESOLVED` static gate can be removed for this
profile because it no longer emits the unknown shared request or reads shared
width. Five gates remain: private setting registration, navigation, literal
font/layout rendering, runtime resource adapter, and native allocation. This
artifact is still explicitly **BLOCKED_NOT_DEPLOYABLE**; there is no claim of
camera rendering, runtime focus, codec readiness, playback, or recording success.
