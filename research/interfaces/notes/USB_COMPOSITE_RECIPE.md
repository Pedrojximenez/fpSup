# SIGMA fp Ver.5.02 — USB COMPOSITE RECIPE (PTP class-0x06 + vendor class-0xFF on one cable)

<!-- index-stamp -->
> 這份寫的是 EP 0x05 OUT / EP 0x84 IN。現行 build 用 EP 0x01 / 0x82 / 0x83(`host/fpshd.c:31-32`、`patches.py:15-20`),EP84 在現行描述元下不存在。
> 先看 [`USB_SHELL_INDEX.md`](../../../projects/usb-shell-sup/notes/USB_SHELL_INDEX.md)。


Firmware: `out/MAIN_c0000000.bin`, ARM32 LE, base `0xC0000000` (file_off = addr − 0xC0000000).
Decomp: `out/decomp/full/blk_c00.c` (FUN_c00xxxxx), `blk_c01.c` (FUN_c01xxxxx), `blk_c04.c`.
Method: read-only static analysis + descriptor-byte extraction. Builds on `notes/research/interfaces/USB_COMPOSITE_MAP.md`.

Legend: **[C]** = CONFIRMED from code/bytes. **[I]** = INFERRED (consistent but not fully traced). **[P]** = needs a LIVE PROBE to close.

---

## 0. TL;DR

- **Composite is FEASIBLE. [C for machinery / I for the exact final wiring]** The descriptor-object model and its registrar (`FUN_c00328b8`) are multi-interface by construction — the CDC gadget (2 interfaces) and UVC gadget (4 interfaces) already exercise the same registrar. Nothing structurally forbids a config that pairs the PTP interface with the vendor interface.
- **There are TWO layers that must both agree:**
  - **Layer A — the descriptor object** (what the host reads): a linked RAM struct built per mode by a template-copy builder, finalized by `FUN_c00328b8`. `bNumInterfaces` and `wTotalLength` are **literal template bytes** copied in, *not computed*.
  - **Layer B — the function-slot / endpoint-hardware table** at `0xC31E3888` (stride 0x10, slots 0..6): which physical DWC3 endpoints get allocated. Programmed either by the `0x2a` "add-interface" op (CDC does this) or from a default seed table (`DAT_c07e27d0`).
- **The `0x2a` you saw is an OPCODE, not a length.** `FUN_c00338a8(devid, 0x2a, &{slot,X,Y})` = "register/enable function slot". The 3-byte struct is **{slot#, subtype, type}**, NOT endpoint counts.
- **Hard blocker to fix: endpoint-address COLLISION. [C]** PTP uses EP `0x01`(OUT bulk), `0x82`(IN bulk), `0x83`(IN int). Vendor uses EP `0x01`(OUT bulk), `0x82`(IN bulk). Both claim `0x01`/`0x82` → the vendor pair **must be remapped** (recommend OUT `0x04`, IN `0x84`). These are descriptor bytes we can `mem set`.
- **Recommended recipe:** inject a builder that (1) calls the PTP builder `FUN_c04e9148()` to lay down a PTP object that *already reserves room for a 2nd interface*, (2) fills the reserved 2nd interface slot with a remapped vendor interface + endpoints, (3) bumps `bNumInterfaces`→2 and `wTotalLength`, (4) registers via `FUN_c00328b8`, (5) registers the vendor bulk pair in Layer B. Exact structs below.

---

## 1. The add-interface ABI (Task 1) — **[C]**

### 1.1 Entry wrapper `FUN_c00338a8` (`blk_c00.c:42598`)
```c
undefined4 FUN_c00338a8(u32 devid, char opcode, u32 arg3, u32 arg4){
  uStack_8 = arg3; uStack_4 = arg4;         // pack args into an 8-byte stack struct
  return FUN_c01e88a0(devid, (int)opcode, &uStack_8);  // &{arg3,arg4}
}
```
Thin shim. It copies `arg3,arg4` into a local pair and passes its address as the arg-pointer.
So for `FUN_c00338a8(8, 0x2a, &local_14)`: `arg3 = &local_14` (pointer to the {ifnum,X,Y} bytes),
`arg4` = garbage; the dispatcher dereferences once to recover `&local_14`.

### 1.2 Dispatcher `FUN_c01e88a0(devid, opcode, argptr)` (`blk_c01.c:139267`) — **[C]**
- **`devid`** is a device/function id, range-gated: accepted iff `devid∈{3..9, 10, 0xc, 0xd, 0xf, 0x10, 0x12}`. (For CDC the call uses `devid=8`. The value only gates; it is NOT forwarded to `0x2a`.)
- **`opcode`** selects a command via `switch`. `0x2a` and `0x2c` are the two we see used here:
  - `case 0x2a: FUN_c01e5dc0(*argptr)` → returns 0 on success, else −4. **This is ADD/ENABLE-INTERFACE.**
  - `case 0x2c: FUN_c01e3558()` (used by `FUN_c0031db0(3,0x2c)` — a different, param-less op).
  So **the `0x2a` in the CDC path is the opcode, not the `0x2a`=42 "length" the task hypothesized.**

### 1.3 The primitive `FUN_c01e5dc0(byte *p)` (`blk_c01.c:136777`) — **[C]**
```c
undefined4 FUN_c01e5dc0(byte *p){          // p -> {b0=slot, b1=X(subtype), b2=Y(type)}
  if (p[0]==0 || p[2]==0) return -1;       // slot must be !=0, type must be !=0
  cur = FUN_c01e60e0();                     // find current "control" slot (type==1 && sub==0)
  if (p[0]==cur && _DAT_c31e3974==1) FUN_c01e6d48(p[0]);   // tear down if reusing active slot
  *(u32*)(0xC31E3888 + p[0]*0x10 + 0x00) = p[2];   // entry.type    = Y
  *(u32*)(0xC31E3888 + p[0]*0x10 + 0x04) = p[1];   // entry.subtype = X
  *(u32*)(0xC31E3888 + p[0]*0x10 + 0x0C) |= 1;     // entry.flags  |= 1 (EXPLICITLY-configured)
  FUN_c01e62a8(p[0]);                              // program the endpoints for this slot
  return 0;
}
```
- **The 3-byte struct is `{slot#, subtype, type}`** — an index into the function-slot table plus a
  2-field endpoint "personality" selector. It is **not** ifnum/altsettings/endpoint-count.
  (CDC passes `{1,1,1}` then `{2,1,1}` → slots 1 and 2, both personality (type=1,sub=1).)
- **Table @`0xC31E3888`, stride 0x10, slots 0..6** (`FUN_c01e60e0/6110/6140/6170` scan slots 1..6):
  `+0x00 type`, `+0x04 subtype`, `+0x08 epcfg`, `+0x0C flags(bit0=explicit,bit? =valid)`.
- **Where endpoints come from:** `FUN_c01e62a8(slot)` (`blk_c01.c:137200`) reads per-slot endpoint
  templates (`DAT_c07e27b0/c0`) and issues DWC3 endpoint commands via `FUN_c01e6a48(ep,cmd,buf)`.
  The (type,subtype) pair keys the endpoint personality; the physical EP number is derived
  internally (`FUN_c01e4d58/4d70` remap slot↔ep). **Exact (type,subtype)→(epnum,dir,bulk/int) map is not fully traced statically → [P].**
- **Does it touch bNumInterfaces/wTotalLength?** **NO.** `0x2a` only touches Layer B (endpoint HW).
  The config-descriptor `bNumInterfaces`/`wTotalLength` are Layer A (see §2). This is why the CDC
  path calls `0x2a` **twice** *and* separately builds a 2-interface descriptor via `FUN_c003f4a8/FUN_c003ecb0`.

### 1.4 Default seed table `DAT_c07e27d0` (stride 0x10) — **[C]**
On reset (`blk_c01.c:137440`) every slot whose `flags.bit0==0` is seeded from `DAT_c07e27d0`:
```
slot0: type=0 sub=2     slot1: type=1 sub=0    slot2: type=1 sub=1
slot3: type=2 sub=1     slot4: type=3 sub=? ...
```
So single-function modes (PTP/vendor/MSC) that never call `0x2a` still get endpoints from these
defaults. **This pre-seeded multi-slot table is one of the "spare capacity" levers (see §7).**

---

## 2. How a builder assembles a config end-to-end (Task 2) — **[C]**

Two builder *styles* exist:
- **Template-copy object style** (PTP `FUN_c04e9148`, vendor `FUN_c00333d0`, MSC): copies a static
  descriptor blob into a linked RAM object, then `FUN_c00328b8(&object)`.
- **Dynamic style** (CDC `FUN_c003ecb0/FUN_c003f4a8`, UVC): builds descriptors procedurally and
  registers Layer-B slots with `0x2a`. (CDC is why the task saw the two `0x2a` calls.)

### 2.1 The descriptor OBJECT model (template-copy) — **[C]**
Vendor object base `0xC3079354`, PTP object base `0xC37748C0`. Field-for-field copy from template.
The object is a set of linked sub-blocks:

```
OBJECT (base):
  +0x00  device-descriptor dwords (bcdUSB/VID/PID… ; +0x08 idProduct patched at register time)
  +0x20  ptr -> CONFIG entry array (speed A)
  +0x48  ptr -> CONFIG entry array (speed B)
CONFIG entry (stride 0x24):
  +0x00  the literal config-descriptor bytes:  09 02 <wTotalLo> <wTotalHi> <bNumIf> <cfgVal> <iCfg> <attr> <maxPwr>
         => byte+2/+3 = wTotalLength, byte+4 = bNumInterfaces   [C, verified against template bytes]
  +0x04  (overlays bNumInterfaces)         [C]
  +0x08  (overlays bMaxPower; patched dynamically by FUN_c00328b8 to 0x32/0xFA)  [C]
  +0x20  ptr -> ENDPOINT/interface array (stride 0x14), count = byte+4
INTERFACE/EP entry (stride 0x14):
  +0x00  interface-descriptor dword(s)  09 04 <ifnum> <alt>  (byte+4 area = bNumEndpoints, class…)
  +0x0C  ptr -> actual endpoint-descriptor bytes (speed A)
  +0x10  ptr -> actual endpoint-descriptor bytes (speed B)
```

### 2.2 Registrar `FUN_c00328b8(obj)` (`blk_c00.c:42004`) — **[C]**
```c
_DAT_c30792c4 = obj;                       // stash object
if first-time: seed dev-desc VID=0x296B PID=0xFFFE, strings "OEM"/"Default Camera"/"0000…"
else:          patch idProduct at obj+0x08/+0x0a/+0x0c and +0x30/+0x32/+0x34 from DAT_c2efad70..
// Two passes program per-endpoint maxpacket for both speeds:
for i in 0..*(byte*)(cfg+ b8*0x24 +4):  FUN_c00327b8(0, epentry[i]);   // speed A
for i in 0..*(byte*)(cfg+ b8*0x24 +4):  FUN_c00327b8(2, epentry[i]);   // speed B
```
- **It does NOT compute `bNumInterfaces` or `wTotalLength`** — those are the literal template bytes
  in the CONFIG entry (verified: `09 02 39 00 01 …` for PTP SS = wTotalLength 57, nIf 1). It only
  patches idProduct + bMaxPower + per-endpoint maxpacket. **[C]**
- `FUN_c00327b8(speed, epentry)` (`blk_c00.c:41961`) writes wMaxPacketSize into the endpoint bytes
  at `*(epentry+0xc)` (SS bulk=0x400, HS bulk=0x200, other=0x40) and, for SS, the companion
  bytes at +0x14/+0x16 (bMaxBurst). **[C]**
- **The actual GET_DESCRIPTOR serialization** (walking the object to emit the concatenated config
  descriptor the host reads) lives in the EP0 handler (blk_c01 `FUN_c01e8xxx` family; accessors
  `FUN_c0032aa0`=endpoint-count, `FUN_c0032ad0`=bEndpointAddress). The precise walk that discovers
  interface #1 and appends its endpoint descriptors is **not byte-traced → [P]** (close with a
  config-descriptor sniff after injection).

---

## 3. PTP builder `FUN_c04e9148` (func_id 5) (Task 3) — **[C]**

`blk_c04.c:174295`. Template-copy from blob `0xC0CF373C–0xC0CF3820` into object `0xC37748C0`.
Registers via `FUN_c00328b8(&DAT_c37748c0)`. Single interface, class 0x06.

Key allocation sizes (from the `FUN_c0015058` memsets at the top):
```
0xC37748C0  memset 0x50   main object
0xC3774910  memset 0x6c   config entries
0xC3774820  memset 0x28   INTERFACE array  <-- 0x28 = 2 * 0x14 => ROOM FOR 2 INTERFACE ENTRIES  [C]
0xC3774848  memset 0x18   endpoint block
0xC3774860  memset 0x18   endpoint block
0xC3774878  memset 0x18   endpoint block
0xC3774890  memset 0x30   trailing block
```
**The PTP builder over-allocates the interface array to hold two entries but only fills entry [0].**
Entry [1] at `0xC3774834` is left zeroed — a ready-made slot for a second interface. This is the
single most convenient injection lever.

PTP interface + endpoints (template bytes, **[C]**):
| desc | addr | bytes | meaning |
|---|---|---|---|
| iface | 0xC0CF373C | `09 04 00 00 03 06 01 01 00` | ifnum 0, alt 0, **nEP 3**, class 06/01/01 (PTP) |
| cfg SS | 0xC0CF37B8 | `09 02 39 00 01 …` | wTotalLength **0x39=57**, nIf **1** |
| cfg HS | 0xC0CF37D0 | `09 02 27 00 01 …` | wTotalLength **0x27=39**, nIf **1** |
| EP SS | 0xC0CF3770 | `07 05 01 02 00 04` | **0x01 OUT bulk** mps 1024 |
| EP SS | 0xC0CF3778 | `07 05 82 02 00 04` | **0x82 IN bulk** mps 1024 |
| EP SS | 0xC0CF3780 | `07 05 83 03 40 00` | **0x83 IN int** mps 64 |
| EP HS | 0xC0CF3788/90/98 | `07 05 01 02 40 00`/`82…`/`83…` | same addresses, mps 64 |

Note the func_id-5 dispatcher `FUN_c04dc4c0` (`blk_c04.c:165918`, hook site 0xC04DC618) calls
`FUN_c04e9148()` then spawns two transfer tasks (`FUN_c01f88ec`) — it does NOT itself call `0x2a`;
PTP endpoints come from the Layer-B default seed.

---

## 4. Vendor builder `FUN_c00333d0` (default func_id) (Task 4) — **[C]**

`blk_c00.c:42412`. Template-copy from `0xC072AFC0–0xC072B0A8` into object `0xC3079354`.
Registers via `FUN_c00328b8(&DAT_c3079354)`. Single interface, class 0xFF.
Interface-array alloc is only `0x14` (one entry) — so the vendor object is a *worse* base than PTP.

Vendor interface + endpoints (template bytes, **[C]**):
| desc | addr | bytes | meaning |
|---|---|---|---|
| iface | 0xC072B030 | `09 04 00 00 02 ff ff ff 00` | ifnum 0, alt 0, **nEP 2**, class FF/FF/FF |
| cfg SS | 0xC072B048 | `09 02 32 00 01 …` | wTotalLength **0x32=50**, nIf **1** |
| cfg HS | 0xC072B060 | `09 02 20 00 01 …` | wTotalLength **0x20=32**, nIf **1** |
| EP SS | 0xC072B000 | `07 05 01 02 00 04` | **0x01 OUT bulk** mps 1024 |
| EP SS | 0xC072B008 | `07 05 82 02 00 04` | **0x82 IN bulk** mps 1024 |
| EP HS | 0xC072AFD8 | `07 05 01 02 40 00` | 0x01 OUT bulk mps 64 |
| EP HS | 0xC072AFE0 | `07 05 82 02 40 00` | 0x82 IN bulk mps 64 |

(The stray `07 05 83 03 …` at 0xC072B010 / 0xC072AFE8 belongs to the region but the vendor iface
declares nEP=2, so only 0x01/0x82 are in play.)

---

## 5. ENDPOINT MAP + collision (Tasks 3/4/5 core constraint) — **[C]**

| function | OUT bulk | IN bulk | IN int |
|---|---|---|---|
| PTP (class 06) | **0x01** | **0x82** | **0x83** |
| vendor (class FF) as-is | **0x01** ⟵clash | **0x82** ⟵clash | — |
| vendor **remapped (recipe)** | **0x04** | **0x84** | — |

Composite must use **distinct EP addresses**. PTP occupies physical EPs: OUT-1, IN-2, IN-3.
Give vendor OUT-4 / IN-4 → addresses `0x04` / `0x84`. No overlap with PTP's {1out,2in,3in}.
(Alternatively vendor could reuse OUT-2 = `0x02` since PTP only uses IN-2, but distinct numbers
are cleaner and avoid any shared-context surprises.)

---

## 6. THE RECIPE (Task 5) — inject a composite builder, base = PTP object — **[I], with [P] closers**

Rationale for choice: option (b)-style (extend the PTP builder), because the PTP object already
**reserves a second interface entry** (§3) and PTP is the interface we most want to keep host-standard.
We append the vendor interface into that reserved slot rather than fighting the vendor object's
single-entry allocation.

### Step 0 — pick the injection point
Add a new case (or hijack an unused func_id) in `FUN_c0031c10` (`blk_c00.c:41329`) that calls the
composite builder below instead of the plain PTP/vendor builder. (You control code injection +
`mem set`, so this can be an injected function called in place of `FUN_c04e9148()` on the func_id-5
branch, or via a fresh func_id.)

### Step 1 — lay down the PTP base object
```c
FUN_c04e9148();   // fills object @0xC37748C0: iface[0]=PTP, 3 EPs, cfg nIf=1
```

### Step 2 — build the vendor interface into the reserved 2nd slot
Interface entry [1] lives at `0xC3774834` (stride 0x14 after iface[0]@0xC3774820). Also carve a
scratch region (any free RAM, e.g. just past the object, or a `mem set` buffer) for the vendor
endpoint descriptors, remapped.

Vendor endpoint bytes to write (SS; add HS variant with mps 0x40 in the +0x10 array):
```
07 05 04 02 00 04 00   ; EP 0x04 OUT bulk mps 1024
06 30 00 00 00 00 00   ; SS EP companion (copy from 0xC072AFC8-style companion)
07 05 84 02 00 04 00   ; EP 0x84 IN  bulk mps 1024
06 30 00 00 00 00 00   ; SS EP companion
```
Vendor interface descriptor bytes (bInterfaceNumber = **1**):
```
09 04 01 00 02 ff ff ff 00     ; ifnum 1, alt 0, nEP 2, class FF/FF/FF
```
Fill interface entry [1] @0xC3774834 to mirror the PTP entry [0] shape:
```
+0x00 : 09 04 01 00           (iface desc dword-0/1)
+0x04 : 02 ff ff ff           (nEP=2, class/sub/proto FF)
+0x08 : <iInterface> 00 00 00
+0x0C : ptr -> vendor SS EP array (0x04 OUT, 0x84 IN)
+0x10 : ptr -> vendor HS EP array (0x04 OUT, 0x84 IN, mps 0x40)
```

### Step 3 — fix the CONFIG descriptor header bytes (both speed entries)
`bNumInterfaces` 1→2 and `wTotalLength` bumped. New lengths **[C-computed]**:
- SS: `9(cfg) + [9 + 3×(7+6)] (PTP) + [9 + 2×(7+6)] (vendor)` = `9 + 48 + 35` = **92 = 0x5C**
- HS: `9 + [9 + 3×7] + [9 + 2×7]` = `9 + 30 + 23` = **62 = 0x3E**

Patch (object addresses; via `mem set` or in the injected builder):
| field | addr (SS entry 0xC3774?..) | old | new |
|---|---|---|---|
| wTotalLength lo (SS) | config-SS +0x02 | `39` | `5C` |
| bNumInterfaces (SS) | config-SS +0x04 | `01` | `02` |
| wTotalLength lo (HS) | config-HS +0x02 | `27` | `3E` |
| bNumInterfaces (HS) | config-HS +0x04 | `01` | `02` |
(The SS config entry first dword = `_DAT_c3774910` region; HS = `_DAT_c3774958`. Confirm the two
config-entry base addresses from the running object with a `mem read` before patching — [P].)

Also set the endpoint-count field the registrar loops on (CONFIG entry +0x04-count used by
`FUN_c00328b8`) so both interfaces' endpoints (3+2 = 5) get maxpacket-programmed. If that count is
per-interface rather than per-config in the object, ensure iface[1]'s own count=2 is set — **[P]**.

### Step 4 — register Layer A
```c
FUN_c00328b8(0xC37748C0);   // finalizes idProduct/bMaxPower/maxpacket for all 5 endpoints
```

### Step 5 — register Layer B (allocate the vendor bulk pair in hardware)
The vendor bulk OUT/IN must exist as physical endpoints. Register a function slot:
```c
u8 s[3] = { /*slot*/ 2, /*subtype X*/ 1, /*type Y*/ 1 };   // {slot, X, Y}
FUN_c00338a8(5 /*devid, gated set*/, 0x2a, s);              // -> FUN_c01e5dc0
```
- Slot must be nonzero and not collide with PTP's slot usage. PTP uses the default seed (slots
  from `DAT_c07e27d0`); pick a free slot (2..6). **The (type,subtype) that yields exactly one bulk
  OUT + one bulk IN at ep4 is not statically resolved → [P]:** iterate (type,subtype) live and read
  back which physical EP got enabled (via DALEPENA / a `mem read` of the DWC3 DALEPENA bitmap), or
  copy whatever (type,subtype) the CDC data interface uses for its bulk pair (CDC slot2 = `{1,1}`,
  which is a bulk OUT+IN personality — a strong candidate).
- If, after a live config-descriptor sniff, Layer A's registrar already enables all 5 endpoints
  (i.e. the object walk in §2.2 drives DALEPENA), Step 5 may be unnecessary — **[P] resolves this**.

### Step 6 — device descriptor class
Leave bDeviceClass = 0x00 (composite by per-interface binding; PTP + vendor bind independently).
No IAD needed for two single-interface functions. **[I]** (Windows PTP driver binds the class-06
interface; libusb/WinUSB binds the class-FF interface.)

---

## 7. Endpoint capacity / DWC3 limits (Task 6) — **[I]/[P]**

- **Function-slot table supports 7 slots (0..6)**; slot 0 = control/ep0, leaving 6 data slots. **[C]**
- Existing gadgets already run multiple endpoints: UVC = 4 interfaces, CDC = 3 endpoints across 2
  interfaces. 5 total endpoints (PTP 3 + vendor 2) is well within a normal DWC3's physical EP count
  (DWC3 typically exposes ≥8 bidirectional physical endpoints). **[I]**
- `_DAT_2100c720` (written `=3` at `blk_c01.c:135549/137239`) is a DWC3 control register the code
  toggles during connect; it is **not** an endpoint-count cap. No static evidence of a 5-endpoint
  ceiling. **[C that no cap is coded here]**
- The definitive check is the **DALEPENA enable bitmap** after enumeration: **[P]** — `mem read` the
  DWC3 DALEPENA register once the composite enumerates and confirm bits for {ep0, out-1, in-2, in-3,
  out-4, in-4} are all set. If DALEPENA has room (it is a 32-bit bitmap, 2 bits per physical EP dir),
  5+control endpoints fit trivially.

---

## 8. "Spare bits" angle (Task 7) — **[C] for the mechanism, [I] for "intended"**

There is no unused bit inside the `func_id` value itself: `FUN_c0031c10` treats it as a small enum
(4/5/8/0xc/default) and `FUN_c0032230→FUN_c002dd10` merely validates it. **BUT** the "spare capacity"
the user recalls is real and lives in two places:

1. **The function-slot table is pre-seeded for multiple concurrent functions.** `DAT_c07e27d0`
   defines slots 1..4 with distinct (type,subtype) personalities, and `FUN_c01e5dc0` (`0x2a`) lets
   you *add another interface at runtime by writing one 3-byte struct*. Stock single-function modes
   simply never use more than their one slot. **This `0x2a` add-interface op is the intended lever
   for a second function** — CDC already uses it to stand up 2 interfaces. **[C]**
2. **The PTP descriptor object over-allocates its interface array to two entries** (`memset 0x28`
   at `0xC3774820`, §3) while only filling one. That reserved second interface entry is a spare slot
   in Layer A that a composite fills with no reallocation. **[C]**

Together these two are exactly the "compose a second function without restructuring" affordance:
Layer B via `0x2a`, Layer A via the reserved interface entry.

---

## 9. What must be closed by a LIVE PROBE (honest gaps)

| # | Gap | How to resolve live |
|---|---|---|
| P1 | Exact GET_DESCRIPTOR serialization of interface #1 + its endpoints (does the object walk auto-append them?) | Inject Steps 1–4, enumerate, `usb` sniff the config descriptor; confirm it shows 2 interfaces, 5 endpoints, correct wTotalLength. |
| P2 | (type,subtype)→(epnum,dir,bulk) map for `0x2a` | Call `0x2a` with candidate {slot, X, Y}, `mem read` DALEPENA + read back which EP enabled. Start with CDC's data personality {1,1}. |
| P3 | Whether Layer-A registrar alone enables DALEPENA (making Step 5 unnecessary) | After Steps 1–4 (no Step 5), read DALEPENA; if vendor EP4 bits absent, Step 5 is required. |
| P4 | Live config-entry base addresses for the SS/HS byte patches in Step 3 | `mem read` object @0xC37748C0, follow +0x20 / +0x48 pointers. |
| P5 | 5-endpoint capacity | `mem read` DALEPENA after composite enumerates; verify all 6 dir-endpoints (incl ep0) enabled. |

All Layer-A edits (§6 Steps 2–3) are plain descriptor bytes → doable with `mem set`. Steps 1,4,5 are
existing firmware calls → doable with injected code that calls them by address.
