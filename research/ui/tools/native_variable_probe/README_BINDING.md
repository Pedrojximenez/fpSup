# Private integer binding: original-instruction probe

Offline research only. **`runtime_ready=false`**: no camera, USB, network,
firmware modification, deployment, actual Lua, actual heap or actual UI loader.
This extends the shared native-variable registration probe by import; the product-specific
coordinator lives separately in `fpSup/lossless/binding/`.

## Run and containment

Use Python with Unicorn 2.1.4 available, for example:

```sh
python3 -B /Users/dido/Developer.localized/SIGMAfp_re/research/ui/tools/native_variable_probe/test_binding_probe.py \
  --seg0 /Users/dido/Developer.localized/SIGMAfp_re/out/seg0_c0000000.bin
```

An existing environment/PYTHONPATH may supply Unicorn; no dependency is
downloaded. On this Mac, actual emulation needs separately approved host JIT
execution. The firmware remains RX; permissions are not weakened to enable JIT.
Pinned seg0: 49,245,696 bytes, SHA-256
`aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`.
Every executed PC must be in a named original interval or explicit stub service.
Only synthetic RAM is writable. Each invocation/resume is bounded to 20,000
instructions / 250 ms and must restore SP. Interleaving cancellation uses a
separate synthetic stack, preserving the paused native frame.

## Native and stubbed boundaries

Native instructions execute subscription wrappers/mutation, notification
dispatch, named/indexed integer assignment wrappers and core, temporary-vector
initialization/destruction, and the original component-dispatch loop.
Registration, name lookup/hash/map/vector operations reuse the shared harness.
Exact intervals appear in `binding_probe.py:EXTRA_NATIVE` and test JSON output.

Explicit stubs: original Lua registration wrapper `C05DB868`, ASCII strcmp
`C0013E2C`, synthetic alloc/free/realloc, synthetic lock/unlock, and two callback
service trampolines. The lock stub captures calls; it does **not** implement an
OS mutex. Callback stubs capture descriptor/context/value, return an injected
status, or once-only tail-delegate to the **original** unsubscribe/no-app-callback
setter. Those tail calls preserve the original notification return address.

The registry/layout and allocator are synthetic. For this private integer,
descriptor component vectors +0x10/+0x14 and calculation vector +0x1C are null.
Thus the original component-dispatch loop executes, but no original component
callback, widget rendering, Lua judgment/calculation or UI queue consumer runs.
Do not report “actual UI notification works” from this suite.

## ABI established by original instructions and tests

All functions below are **Thumb**, so function pointers use the odd addresses
shown. Do not apply this convention to unrelated ARM functions.

```c
struct Descriptor; // 32 bytes; integer type at +0, name +4, value +8, index +12.
typedef int (*VariableCallback)(struct Descriptor *changed, void *context);
struct CallbackPair { VariableCallback callback; void *context; }; // 8 bytes

int Subscribe(App *app, const char *name, const struct CallbackPair *pair);
// 0xC05DCB19; r0-r2, no stack arguments. name == NULL means global slot.
int Unsubscribe(App *app, const char *name);
// 0xC05DCB31; r0-r1, no stack arguments. No callback identity/token argument.
int Notify(App *app, struct Descriptor *descriptor);
// 0xC05D9F91; internal dispatcher, NOT a setter.

struct NamedAssignment { uint32_t type; const char *name; uint32_t value; };
int SetNamedNotify(App *app, uint32_t fallback_arg, uint32_t count,
                   const struct NamedAssignment *assignments);
// 0xC05DC7C9; r0-r3, no caller stack arguments; tested fallback_arg=0 only.
int SetNamedWithoutAppCallback(App *app, uint32_t fallback_arg, uint32_t count,
                              const struct NamedAssignment *assignments);
// 0xC05DC779; still dispatches bound component updates.

struct IndexedAssignment {
    uint32_t type; const char *name; uint32_t value; int32_t index;
};
int SetIndexed(App *app, uint32_t count,
               const struct IndexedAssignment *assignments);
// 0xC05DC819; r0-r2, no caller stack arguments.
// index >= 0 uses registry vector; negative index resolves the supplied name.
```

Integer type is 0. These are arrays with **12- or 16-byte stride**, not scalar
setter APIs. The second named-wrapper argument is unused on the tested active
registry route; its fallback semantics/type are not established here.
The batch core `C05DC179` has a fifth argument `notify` at caller SP;
the native wrappers construct it. Core reads this at its SP+0x84 (`C05DC28C`),
after saving 36 bytes of registers and reserving 96 bytes. Use a verified wrapper
rather than inventing a scalar call shape. Type selection uses the existing
descriptor; adapters must independently check descriptor type/ownership.

Reading: native `LookupApp 0xC05DCA89(app,name,&descriptor)` is the tested route;
check BOTH status==0 AND descriptor!=NULL, then type==0 before reading +8.
The +8 value is directly observed after original set instructions. No separate
safe scalar getter is claimed. Original ARM getter `C055FA50` loads +8 at
`C055FA88`; its wrapper `C055FB58` treats successful lookup as found without a
descriptor-null check, so it is unsuitable for an unregistered private name.
This ARM getter was disassembled, **not executed** by this Thumb probe.

## Ownership and notifications

`Registry = *(app+0x888)+0x60`. A per-variable pair pointer is descriptor+0x18;
global pair is registry+0x5C. Subscription allocates/copies the 8-byte pair;
caller pair storage can change afterward, but callback code and context remain
borrowed and require stable lifetime. Only one subscriber per variable/global
slot is supported; duplicate subscription returns 2 and preserves the owner.
Name and descriptor lifetime are inherited from registration: stable names and
registry-owned descriptors, not teardown-owned callback ticket memory.

Mutation uses allocator +0/+4 for alloc/free and optional app root +0x134 lock
with root +0x130 service-table +0x2C/+0x30 lock/unlock services. Subscription/unsubscription
success=0; missing name=3; duplicate/absent slot=2; allocation failure=1;
null app=6; null subscribe pair=4; inactive Lua marker=2. Unsubscribe clears/frees
the pair only: it does not remove the variable, free context or unregister Lua.
There is no expected-owner check on unsubscribe; serialization is necessary to
avoid canceling someone else's newly installed callback (ABA/ownership risk).

Integer assignment compares exact 32-bit values (`C05DC240..C05DC248`). Changed
value is written **before** synchronous notification (`C05DC29A`), followed by
component dispatch under its optional lock. Same-value set does not notify or
dispatch components. Values are not clamped to 0/1: 7 and -1 are accepted.
The OFF/ON policy belongs in the adapter/core, not this native integer variable.

Notification invokes private first then global, even if private returns error.
`Notify` returns the first nonzero callback result. **The setter discards this
result**, so callback return cannot veto ON. A nonzero setter result must not be
assumed to mean rollback: writes precede later component dispatch, whose actual
callbacks are outside this suite. A tested callback can synchronously
re-enter the no-app-callback setter to restore OFF before the outer set returns;
the component vectors are empty in this test, so a real UI may still introduce
additional reentrancy. Native depth +0x44 increments only **after** callback
dispatch (`C05DC2BA`); it is not direct callback-recursion protection.

## Cancellation boundary: success is not quiescence

Notify has no matching subscription mutex acquisition. Its original code loads
pair pointer at `C05D9F94`, loads callback/context at `C05D9F9C`, calls at
`C05D9FA4`, and does not reread that pair after private callback returns.

Deterministic native pause/cancel/resume tests establish two counterexamples:

- Pause just before `C05D9FA4`, unsubscribe successfully, resume: the already
  loaded callback still executes with the old context.
- Pause before `C05D9F9C` after pointer load, unsubscribe, resume: the original
  instruction attempts to read the freed pair; the freed-allocation read guard
  rejects it. Retaining only the callback ticket cannot prevent this pair UAF.

A callback stub that tail-delegates to native unsubscribe can safely complete
that one serial call path; private notification continues to global. This does
not establish concurrency safety, queued-event drainage, or safe ticket release.
These are constructed valid instruction interleavings, **not a claim that the
camera OS actually permits those scheduling points**.

Adapter gate: serialize setters/notification/subscription mutations on a proven
owner executor, invalidate generation first, and require **pre-unsubscribe
notification exclusion** plus post-unsubscribe quiescence/queue drainage before
releasing callback code/context. Post-unsubscribe waiting alone is insufficient
if the pair can be freed while another thread has loaded its pointer. Descriptor
and name storage must survive independently with the registry. Never destroy
them as part of callback-ticket retirement without a separately proven API.

## Test scope and remaining gates

18 cases cover pair ownership, single-slot behavior, argument/error boundaries,
allocation failure, named/indexed set, exact-value change detection, callback
order/status, no-app-callback semantics, unrestricted integers, synchronous
revert, cancellation interleavings and self-unsubscribe. Test output is JSON;
`binding-probe-20260916.json` records the verified run.

Remaining gates: actual app/resource startup and shutdown; original Lua/heap and
mutex contract; original UI component and event-queue consumers; scheduling/
quiescence and queued context lifetime; generation/reentrancy coordination;
descriptor/type/name ownership on collisions; registration failure rollback;
bound boolean policy and core acceptance. The uninitialized-registry fallback
in SetNamed wrappers, strings/floats, invalid vector indices, derived variables,
real concurrent threads, persistence and resource-loader installation are not
executed. Native APIs are call-shape evidence, not permission to deploy.

Source anchors: `out/decomp/full/blk_c05.c`: notification line 172113; integer
batch core 174658; wrappers 175085/175115/175145; lookup 175317; subscription
175382; unsubscribe 175460. Original-address evidence above takes precedence
over decompiler parameter/type guesses.
