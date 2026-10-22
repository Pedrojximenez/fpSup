# fpLossless render/selection boundary — 2026-09-16

Offline evidence, not a renderer implementation or installable hook. No camera,
USB, network, stock settings writes, Lua execution or resource mutation. Pinned
seg0 SHA-256: `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`.

## Result: keep saved value, cursor and permission separate

The MainY4 donor is **one input widget**, not two independently selectable
OFF/ON buttons. Therefore disabling the ON visual object's `is-active` does
not stop selecting ON. Do not claim `publish(value)` implements
`fpl_view.off_enabled/on_enabled/reason`.

| Stock donor role | Object / component | Exact record |
| --- | --- | --- |
| Saved/summary value | MenuItem_Select 19459, controlValue 13 | C216CE8B |
| Popup cursor value | List 19463, controlValue 3 | C216D3EB |
| Sole keyboard handler | ListItem 19464 | C216D5C7 |
| Confirm Right / Enter | ListItem keyEvent 10 / 12 | C216D8CA / C216D95E |
| OFF / ON visual subtree | 33316 / 33318 | C216DCC6 / C2170155 |
| OFF / ON text | 19465 / 33319, drawText 1 | C216DD72 / C2170209 |

The builder remaps object IDs; these are original addresses/IDs, not runtime
candidate IDs. Popup up/down execute `dst - 1` / `dst + 1` on List controlValue
(C216D7E0/C216D83F). Opening copies the root saved value into List value
(C216CC80/C216CD70). Confirmation reads List value and writes the named
variable (C216D8F2/C216D986), then returns focus to the root. Visual children
`00` / `01` do not each receive the keyboard events.

MainB2 attach/detach C05834D8/C0583538 merely subscribe/unsubscribe stock
CM_DCCrop, ST_AspectRatio, MV_AudioRecord. Their callbacks
C0583598/C05835F0/C0583648 convert values and invoke factory setting setters;
they are not render-enable setters. C0593F30 queues a variable update and is
not synchronous proof that widgets reflect the new permission state.

## Rejected shortcut: restrict max-value on the saved control

Original controlValue update callback C05FAD49 changes private min/max/current
storage, clamps current value, and requests property synchronization at
C05FAFF2 -> C0601140. The offline tests execute this callback and establish:

- min=max=0 clamps requests -1/0/1/2 to 0, with loop off or on;
- lowering max from 1 to 0 clamps an existing current value of 1 to 0.

This is a **value mutation**, not just visual disabling. Never change the
root's max=7 to implement the ON gate. It participates in UI state/animation,
and its A2P+P2A binding could propagate a changed value to the saved preference.
The tests stub property synchronization and do not execute P2A propagation, so
that last consequence is a source-supported risk, not a completed UI test.

Limiting only popup List.max avoids directly modifying the saved control (the
stock List has no P2A saved-variable binding). But opening an existing ON
preference then clamps its popup cursor to OFF; confirming without moving would
save OFF. It also does not grey ON or explain why. This is not the preferred UI.

## Feasible next resource design, not yet implemented

Keep saved `MV_fpLossless` unchanged until accepted confirmation. Keep popup
range 0..1. Add a separate private cursor variable and a private integer
confirmation permission, both initially fail-closed:

1. Bind popup List.value to a **different** private cursor variable, using
   A2P+P2A, never the saved preference. Native C recomputes permission from the
   current cursor plus fresh `off_enabled` / `on_enabled` facts.
2. Set permission to 1 only if `(cursor==0 && off_enabled)` or
   `(cursor==1 && on_enabled)`; otherwise 0. A2P-bind it to property `type` of
   the two ListItem confirmation keyEvents. OFF can remain selectable while
   ON confirmation is denied, without clamping the saved or cursor value.
3. Grey disabled option text separately and render a reason. This still needs
   a theme/animation-aware resource recipe: existing donor animations write
   text/color, so one direct color write is not persistent proof. A private
   integer reason -> literal-text animation mapping avoids a borrowed dynamic
   string, but is a design proposal, not verified rendering.
4. Preserve ESC/Left and navigation. Gate newly arriving confirms, but keep
   the core fresh-context rejection + explicit canonical rewrite as the
   authoritative guard. Retire pending source events during detach/failure.

This adds private UI variables, ownership and notification dependencies. It
must be integrated transactionally with the coordinator and page lifecycle;
do not install isolated resource bindings before private registration succeeds.
Do not write stock EXCL_CableRelease, MENU or factory settings as a shortcut.

## Native A2P mechanism and exact setter ABI

The appVariableEvent property table C2E000A0 explicitly enumerates:
`type=0: A2P`, `type=1: A2P+P2A`. Its target fields are `component-id`,
`property-name`, `property-subindex`; the event is owned by the same object as
the target component. Use `type=0` for read-only permission bindings, otherwise
widget writes may feed back into the permission variable.

Static original source: C05E4670 attaches the event to descriptor component
vector +0x10 and calls C05E3F60 for types below 2. Only type 1 adds the reverse
component callback C05E4288. C05E3F60 resolves the component/property and converts
integer variables into integer/boolean/enum or float properties. These binding
lifecycle paths were read/disassembled, **not executed** by this probe.

Exact original wrapper instructions, exercised to a stubbed core boundary:

```c
// Thumb C05D63A9: r0=component, r1=property index, r2=value.
int SetIntegerProperty(Component *, unsigned property, unsigned value);
// Thumb C05D6879: r0=component, r1=property index, s0=float value.
// NOT the decompiler's three-core-register argument shape.
// Do not call with an ordinary soft-float C function declaration.
```

Integer wrapper delegates C05D6038(component,0,1,0,index,&value).
Float wrapper delegates C05D64E0(component,0,1,0,index,&float_value).
Both cores are stubbed in this suite; no complete property mutation, redraw,
object lookup, renderer or component callback graph is claimed.

## Important negative test: type=0 does not cancel repeat

keyEvent C05FBFB8 uses the `type` bitmask (bit0 press, bit1 down, bit2 up).
Original C05FC078..C05FC098 skips a new press when type=0. In the synthetic
character Enter case, type=1 dispatches 0x2500 and type=0 does not.

However its **phase=3** pending-repeat branch C05FBFF6..C05FC04C examines held
keys and sets dispatch 0x2500 **before** the type checks. With a synthetic held
Enter key, phase=3 still dispatches 0x2500 when type=0. This is an original-code
counterexample, not a claim of actual camera scheduling. Thus a disabled visual
or key mask is not a queue-drain/recording safety proof. The existing coordinator
must still reject stale/unsupported ON and explicitly restore canonical state.

## Tests and boundaries

`test_native_render.py` passes **14 cases, zero skipped**, captured in
`render-probe-20260916.json`. It maps pinned firmware RX and only synthetic RAM
RW, checks every executed PC against listed native intervals/stubs, and bounds
each call to 5,000 instructions / 250 ms with SP restoration. Host Unicorn JIT
needs approved execution on this Mac. Example:

```sh
PYTHONPATH=/private/tmp/raw14-unicorn-cache/archive-v0/NzmDie5Nzfbv0-EL/lib/python3.9/site-packages /usr/bin/python3 -B test_native_render.py --report render-probe-20260916.json
```

Explicit stubs: property read, widget action dispatch, timer, held-key list,
integer/float property core, component userdata lookup, controlValue property
sync/event, memset. Float normalization C06011F0 is stubbed only for exact small
integer values -1/0/1/2; the original compare wrapper and original clamp callback
execute. No arbitrary float behavior or formatting correctness is claimed.

`inspect_render.py` dumps typed donor properties and object relationships using
the pinned existing resource schemas. It is read-only and does not build a
candidate. Neither script is a camera adapter.
