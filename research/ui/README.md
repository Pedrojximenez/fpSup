# SIGMA fp — GUI resource system (Ver.5.02)

How the camera's menus and Quick Set screens decide what to draw, where the
icons live, and which parts of it can be changed at runtime.

Most of this was measured on a live camera over the USB shell during
2026-09-14.  The parser-copy path in §6 has a hardware precedent in the
archived FP3K v0.3.2 work on the same Ver.5.02 firmware.  That precedent does
not guarantee that a slower current AutoRun still precedes every target NBU
record.  Where something is inference rather than measurement it says so.

2026-10-01: a whole new Settings row (fpLossless, SHOOT 2 CINE) by swapping
the MainB2 page at runtime, its strings in the **shared FSPL string pool**, and
OG accepting that pool so both merge on one card --
[NATIVE_ROW_AND_SHARED_POOL.md](NATIVE_ROW_AND_SHARED_POOL.md).

2026-09-29: **any resource can be replaced with an 8-byte write** -- see
[RESOURCE_REPLACEMENT.md](RESOURCE_REPLACEMENT.md). The NBR directory at
0xC0D4D9BC is 2259 sorted entries of {fnv1a(path), name offset, data offset,
size}; the whole menu is 195 `.cvm` CSV files, and the Resolution list is an
89-byte one. No hook is involved.

2026-09-29: the record interpreter now runs offline --
[tools/nbu_probe](tools/nbu_probe/README.md). It shows that the 20 MB record area
is **not** one linear container: the top level is the string pool plus a
221-entry index of separate resource sets ([nbu_sets.json](nbu_sets.json)), and
it decodes the tag-0x10002 allocation header.

2026-09-29: pressing right to open a submenu is the CSV's **Popup column** --
it names the destination page -- plus a `MenuItem_Jump` / `MenuItem_SelectJump`
object carrying a `JumpEvent`. [SUBMENUS.md](SUBMENUS.md).

2026-09-29: a third Resolution row in Settings is **three writes, 133 bytes and
no hook** -- `tools/menu_row_patch.py`, recipe in
[RESOURCE_REPLACEMENT.md](RESOURCE_REPLACEMENT.md).

2026-09-29: the Quick Set is a different problem from the menu --
[QUICK_SET.md](QUICK_SET.md). It has no CSV at all; a third resolution state
touches **218 records**, 152 of them in the QS sets and only 6 in Settings.

2026-09-29: a row that selects but then draws nothing is the enum -> display
state converter, and moving one is **three ARM immediates, not a hook** --
[BLANK_AFTER_SELECT.md](BLANK_AFTER_SELECT.md), tools/enum_converters.py.

2026-09-29: patched but nothing changed on the camera? The six causes and how
to tell them apart, with a one-byte experiment that settles the first two:
[WHY_NOTHING_CHANGED.md](WHY_NOTHING_CHANGED.md).

2026-09-29: what a new UI costs, by scope --
[UI_COST_BY_SCOPE.md](UI_COST_BY_SCOPE.md). OG3K's real bill was 360 records and
almost all of it was the Quick Set; a Settings-only list row is three writes.

2026-09-29: when a change takes effect -- three layers, three answers --
[HOW_CHANGES_TAKE_EFFECT.md](HOW_CHANGES_TAKE_EFFECT.md).

2026-09-29: "can a page hold a seventh row?" -- two different answers for the
tab pages and the lists you enter. [MENU_LAYOUT.md](MENU_LAYOUT.md).

2026-09-29, **camera**: "selectable" and "visible" are two different things --
a data-only change can make an option logically complete (right enum, right
gate, right error message) while nothing is drawn.  Two negative rounds on the
NBU set-index redirect, and why R2 has the shape it has.
[SELECTABLE_VS_VISIBLE.md](SELECTABLE_VS_VISIBLE.md).

The format itself now has a single reference:
[NBU_RECORD_FORMAT.md](NBU_RECORD_FORMAT.md) -- both containers, the record
framing, the parse context, the four reader methods and the per-tag token
grammar, each line marked with whether it was executed, read from the decompile,
or not read at all.

**Start at [UI_NAVIGATOR.md](UI_NAVIGATOR.md)** (2026-09-29): the layer model, the six
intervention routes with their cost and verification status, the nine traps, and
`tools/uinav.py` -- a query tool over [ui_map.json](ui_map.json) plus the string
pool, GUI page table and icon manifest read live from the pinned image.
Who has modified what is in [UI_MODS_INVENTORY.md](UI_MODS_INVENTORY.md).

For adding an independent setting to SHOOT page 2, see
[MainB2 row extension](MAINB2_ROW_EXTENSION.md) and the
[pinned, read-only audit](tools/README_MAINB2_AUDIT.md). These are offline
structure/registration findings, not a verified on-camera fourth row.

New offline tooling: [typed component schemas](tools/README_COMPONENT_SCHEMAS.md)
and [original-instruction variable registry probe](tools/native_variable_probe/README.md).
They separate native execution from static evidence and service substitutes;
neither is a camera-ready row installer. The additional
[subscription/setter and cancellation probe](tools/native_variable_probe/README_BINDING.md)
proves why callback errors cannot veto native assignment and why unsubscribe
alone cannot safely retire callback storage (18 offline instruction tests).
Additional shared probes: [lazy page loading](tools/native_page_probe/README.md)
(16 cases), [choice-control permissions](tools/native_control_probe/README.md)
(14 cases), and [strict ARM text extraction](tools/arm_text/README.md) (20 tests).
Product-specific native C wrappers remain in `fpSup/lossless/native/`.

---

## 1. The three layers

| Layer | Where | Read when |
|---|---|---|
| Sorted string pool | `0xC18C0474` | on demand |
| Serialised UI records | `0xC1900000` – `0xC2D80000` (20 MB) | interpreted by `FUN_c05e6400` |
| Embedded Lua | above `0xC2D80000` | GUI binding / expressions |

Records reference strings by **big-endian pool offset**:
`pool offset = string address − 0xC18C0474` (verified against three names).

The GUI layer really is Lua: `gui gc` prints `LUA_GCSTOP / LUA_GCRESTART /
LUA_GCCOLLECT`, and the record area contains Lua chunks with an
`<!icon_name,CENTER>` directive for embedding icons inside text (305 of them —
**none** referencing a resolution icon).

## 2. Icon storage — the XCI format

2004 icon blobs live in the static firmware image at
**`0xC1240014` – `0xC151C348`**, so at runtime they sit in writable DRAM.
(2026-09-29: walking the archive by the size formula below reaches `0xC151C348`
exactly after 2004 blobs, and a magic scan finds the same 2004. The earlier
"2005" was wrong; against 2006 manifest paths that means **two** gaps, not one,
so an index alone does not identify a blob -- confirm by dimensions.
`tools/uinav.py icons <name>` prints every candidate with its w x h.)
They are LZ4-compressed, which is why searching for pixel dimensions finds
nothing.

```
+0x00  "XC\0\0"
+0x04  u32  frame length = block + 23
+0x08  u16  width
+0x0A  u16  height
+0x0C  u32  0x00000400
+0x10  u16  0x0202
+0x20  LZ4 frame: magic 04 22 4D 18, FLG 0x88, BD 0x10,
       8-byte content size at +0x26, HC at +0x2E,
       block length u32 at +0x2F, block data at +0x33
tail   00 00 00 00    LZ4 EndMark
```

Payload is **16 bpp**: little-endian u16 per pixel, low byte = luminance,
high byte = alpha. Stock icons are white antialiased text, so L == A ==
coverage. Decoded sizes are exactly `w × h × 2` for every sample tested.

Size relationships, consistent across all samples:
`content = block + 19`, `frame length = content + 4`,
`blob total = 0x33 + block + 4`.

`tools/xci.py` implements both directions. **Round-trip is pixel-exact**:
decoding a stock icon and re-encoding reproduces both planes byte for byte.

Blob order matches the 2006 `.xci` build-manifest paths at `0xC0D24968` with
two gaps, so a name can be mapped to a blob by index plus a dimension check.

## 3. How a Quick Set tile animates its icon

Each tile draws a **label plate plus a value icon**:

```
menu_cine_format_qs.xci      150x74   FORMAT plate
font_menu_MB_format_1.xci    150x38     text line
qs_formatQuality_3_S.xci      86x49     icon
```

The icon name's numeric suffix tracks the widget's states, but the serialized
form is an **animation curve**, not a direct index array. Every animation
property has a 20-byte header followed by ten-byte keys:

```
property header (20 bytes, big-endian):
    key_count:u32, type:u32, component:u32,
    property_name_pool_offset:u32, dimension:u32

each key (10 bytes, big-endian):
    flag_a:u8, flag_b:u8, time:u32, value:u32
```

For an `image` property (`type == 2`), `value` is the string-pool offset of the
XCI resource name. Stock two-state resolution curves have keys at times 0 and
33; the working third state is time 66. `key_count` is therefore 20 bytes
before the first key.

`FUN_c05e2280` compares the curve against the evaluator's current floating
time at `eval + 0x1C` and returns the bracketing key objects (`r2` lower,
`r3` upper). Before the first key both outputs are first; after or exactly at
the last key both are last. Between them, lower is the final key with
`key.time <= t` (including the last of duplicate times), and upper is the first
key with `key.time > t`. It does not index past the array.
`FUN_c05e2970` returns the selected lower key's value at `key + 0x18`.

This corrects the earlier `[prefix, ref, last]` interpretation: bytes 0/1 are
flags, bytes 2..5 are the time, and bytes 6..9 are the value. There is no
terminator field. Raising only the image property's count cannot create a UI
state: the controller maximum, group endpoint and every companion property
must have matching time-66 keys as well.

## 4. What can and cannot be changed at runtime

This is the useful result, and it is not about *where* the data is but about
*when it is read*:

| Data | Read when | Runtime patch |
|---|---|---|
| enum→state pair table `0xC2E4020C` | every evaluation, by `FUN_c06ccd10` | **works, immediately** |
| Serialised UI records | interpreted, but not re-read after the screen is built | no effect |
| Parsed element objects on the GUI heap | built during resource-set interpretation; later freed with their owner screen | fixed-address edits do not persist |

Three direct edits made to the serialized `image` bytes produced **zero**
measurable change, while changing one word of the pair table took effect on the
next screen draw. The experiments still prove the caching boundary, but their
original labels (`terminator`, direct state index) came from the obsolete key
interpretation corrected in §3 and must not be reused as format semantics.

The parsed objects are not stable-address data: eight copies were located,
patched and read back correct, and a later sweep of 144 MB found **none** of
them. Later tracing showed that they were not rebuilt by each draw; the screen
object that owned them had been freed. The resolution arrays themselves are
built during the one startup resource pass and are not rebuilt by normal screen
or setting transitions.

### The enum→state table

```c
/* MenuValueConverterBase__v21 @ 0xC06BDA30 */
*param_2 = &DAT_c2e4020c;
return 3;                      /* count, hard-coded */
```

```
0xC2E4020C  {3, 0}   UHD
0xC2E40214  {2, 1}   FHD
0xC2E4021C  {4, 2}   ← stock firmware already defines a third state
```

Display state 2 is **SIGMA's own**, not something added by a modification.
What is missing is the artwork: `qs_resolution`, `set_resolution` and
`font_menu_MB_resolution` each ship exactly two members, while every other
family that needs more has them (`qs_aspect` 7, `qs_mode` 7, `qs_iso` 43),
and numbering need not be contiguous (`qs_drive` has no `_2`).

## 5. The interpreter

`FUN_c05e6400` is a bytecode interpreter for the record format. It reads tokens
through `param_1[0xe]` and dispatches on values like `0x20001`, `0x20002`,
`0x30001`. The `0x20001` branch reads a count and then loops building elements,
calling `FUN_c05edc40`, which allocates **0x34 bytes** — exactly the element
size seen on the heap.

It is Thumb-2, as is everything in that region.

Parsed element layout (0x34 bytes):

```
+0x00  prefix value (0x00, 0x21, 0x42 …)
+0x0C  0xC05EDC39
+0x10  shared object pointer
+0x18  pointer to the icon's name string
+0x1C  four floats: 0.25, 1.0, 0.25, 0.1
```

Because fixed heap addresses do not survive their owner objects, **the durable
intervention point is construction inside this interpreter**, while the
resource set is being parsed. For the resolution arrays measured here, that
construction happens once during startup rather than once per draw.

## 5b. Hooking Thumb code

Everything in the GUI region is Thumb-2, so the ARM hook machinery used
elsewhere in this project does not apply. What works:

- `armasm.py` drives clang, so a `.thumb` source assembles fine. Avoid `bl`
  between local labels — that emits `R_ARM_THM_CALL`, which the relocation
  handler does not implement. Branches and pc-relative literals are fine.
- Enter with **`B.W` (T4), not `BL`**, so `lr` still holds the original
  caller's return address and the displaced instructions can run unchanged.
- Encoding, verified against clang in both directions:

```python
off = target - (site + 4)
s  = (off >> 24) & 1
i1 = (off >> 23) & 1
i2 = (off >> 22) & 1
j1 = (~i1 ^ s) & 1
j2 = (~i2 ^ s) & 1
hw1 = 0xF000 | (s << 10) | ((off >> 12) & 0x3FF)
hw2 = 0x9000 | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7FF)
word = hw1 | (hw2 << 16)          # hw1 goes at the lower address
```

- Return with `bx` through a register the displaced code is about to overwrite
  anyway, to a Thumb address (bit 0 set).

`tools/elemobs.S` is a working example: it hooks `FUN_c05edc40`, logs
`(r0, lr)` plus a slice of the caller's stack, then runs the two displaced
instructions and returns to `0xC05EDC45`.

Measured with it: **one QS draw constructs 314 elements, every one of them from
the single call site `0xC05E7300`, with the same allocator object in r0.** So a
hook there cannot tell one widget from another by call site — the discriminator
has to come from somewhere else. The interpreter's stack at that point contains
fields that vary in groups (about ten distinct values across fifty-eight
records) but none that obviously names the property.

## 5c. Where the image array is actually built

`FUN_c05e6400`'s `case 10` is the image-array builder. Reconstructed from the
decompile and confirmed by hooking:

```c
case 10:
    count = read();  ...
    container = FUN_c05e2988(alloc, name, count, ...);
    for (i = 0; i < count; i++) {
        name = FUN_c05e5b58(param_1, read());   /* pool offset → string address */
        elem = FUN_c05edc40(alloc);             /* allocates 0x34 bytes        */
        FUN_c05edb68(elem, name);               /* writes the name to +0x18    */
        FUN_c05edd20(elem, read(), 0, read(), 0);
        elem[0x24] = read();
        FUN_c05e2ca8(container, elem);          /* append                      */
        FUN_c05edb10(elem);                     /* drop our reference          */
    }
```

`FUN_c05e2ca8(container, elem)` is the natural intervention point: the element
is fully populated there, so `elem+0x18` identifies the widget, and the
container is in hand. A hook on it decodes names correctly (`OFF`, `Blk1` …
`Blk15` for one container), so the read is sound.

`FUN_c05edd40` clones an element and takes its allocator from the source
element's `+0x10`, so a third entry can be produced without needing the
interpreter's allocator object.

**But the resolution array is never rebuilt after boot.** Every screen-level
transition was tried with the filtered hook armed, and every one produced zero
hits:

| trigger | appends matching `qs_resolution_*` |
|---|---|
| one Quick Set draw (314 appends total) | 0 |
| `gui scr set 1_03_CINE` | 0 |
| resolution changed away and back | 0 |
| MENU opened / closed | 0 |
| `SetRecMode` stills ↔ movie | 0 |
| `STILL` / `CINESW` keys | 0 |

(The playback key wedged the USB worker before it could be tested — entering
playback does card I/O, which is the known livelock.)

This also corrects an earlier reading. The eight parsed arrays that were located
and then vanished were not being rebuilt per draw; the screen object that owned
them was freed. Each array is built **once per resource-set interpretation**, not
once per frame. Some screen-specific sets may be interpreted lazily, but a hook
cannot change a target record that was already consumed and is never parsed
again.

That makes timing a per-record question, not one global "AutoRun before/after"
answer. A later stock NBU call proves that the parser still runs; only an exact
hit for the target address and fingerprint proves that a particular UI repair
was applied.

## 6. The guarded late-registration route

AutoRun is later than the stock NBR/resource pass.  That closes the simple
"observe the first image-array construction" route, but it does **not** close
native UI extension altogether.

The archived FP3K v0.3.2 work used this route successfully on a real camera with
the same Ver.5.02 image:

1. Hook the native NBR loader at `0xC05E84D8` and the NBU record interpreter at
   `0xC05E6400`.
2. If the stock NBR was loaded before AutoRun, use the live resource context
   carried by a later NBU parse to register a small private NBR exactly once.
3. Match a source record by both its exact address and FNV-1a of all original
   bytes.  Copy it to a bounded 512-byte temporary buffer, append the new state
   and all companion layout keys there, then let SIGMA's original interpreter
   parse the copy.
4. Restore the reader base and advance by the original record length.  The
   firmware's serialized records and stock image resources remain untouched.
5. Hook `0xC05E5B58` only for the stock NBU pool so synthetic offsets can resolve
   to names from the private NBR; all ordinary string lookups retain stock
   behavior.

Late private-NBR registration avoids depending on the initial **NBR** pass, but
does not replay an already-consumed **NBU record**. The v0.3.2 result therefore
proves its own scheduling margin (or later lazy screen parsing), not the current
larger AutoRun's margin. The OpenGate candidate records a persistent one-bit hit
for each of its 360 sorted target records; evaluate that bitmap after opening
each target screen. A ready pack with zero target hits is a timing miss, not a
drawing failure.

The path also explains why patching only `qs_resolution` is insufficient: the
new state must be cloned into visibility, rectangle, position, collapse, cursor
and timeline properties as well as the image property, or the tile overlaps and
appears corrupted.

If the target bitmap proves that a screen was already parsed, the narrow
post-parse tile fallback needs **three** layers; the image decoder alone is not a
draw hook:

1. Observe `0xC05E37F8` to verify that the live `20_MV_Resolution` or
   `21_MV_Resolution` container receives time 66 after its stock endpoint 33.
   Only after that observation, map 66 to 33 for those exact group names so the
   stock FHD companion geometry remains valid.
2. Hook the selected-key value reader at `0xC05E2970` after its stock result.
   For OpenGate plus those exact groups, replace only the two `_2` image names
   with unique `OG3K_FONT` / `OG3K_QS` names. A unique name is required to make
   the cached image backend request a reload.
3. Serve those two synthetic names at the aligned image-open path
   `0xC0602098` with bounded XCI descriptors.

Using only steps 1 and 3 leaves the FHD `_2` name unchanged, so the cached
backend may never decode again. This fallback covers only the active 20/21
tiles; a third footer slot/cursor/range and the collapsed Settings summary need
separate live-property work. It is a traced next experiment, not a
camera-validated implementation.

The artwork is complete. `tools/xci.py` provides a pixel-exact L8A8/LZ4
round-trip, `captures/og3k_86x49.xci` is the reviewed Quick Set tile, and
`tools/nbr.py` builds and structurally validates small NBR 1.5 resource packs.

`tools/build_appendobs_boot_probe.py` is retained as a timing/observer research
instrument. It is not safe to combine with the OpenGate UI resident because its
`0xC0733000..0xC0734000` scratch/log range overlaps resident code. The product
candidate uses its own per-record bitmap instead.

## 7. Files

```
tools/uinav.py         the navigator: addresses, pages, string pool, icons,
tools/test_uinav.py    resource sets, owners, routes, traps (19 offline tests)
tools/nbu_probe/       FUN_c05e6400 itself under unicorn, plus nbu_format.py:
                       the record framing, the tag catalogue and the image
                       array decoded field by field (37 tests)
tools/xci.py           XCI decode/encode, and a text-tile renderer
tools/render_xci.py    renders normal XCI resources and full-screen
                       `display capture` L8A8/L8 planes as PNG
tools/nbr.py           project-neutral NBR 1.5 builder and structural validator
tools/menu_row_patch.py  the data-only menu row: three writes, no hook
tools/test_menu_row_patch.py                              (16 offline tests)
tools/nbr_stock.py     the STOCK NBR container: every resource, and the 8-byte
tools/test_nbr_stock.py  write that repoints one, the menu CSVs, the 17
                         .nloc string tables and the submenu jumps (34 tests)
tools/xcitrace.S       hooks the gui image-log callback, copies the caller's
tools/xcitrace_ctl.py  stack — this is what located the icon archive
tools/qsprobe.py       measures which icons a screen actually loads
tools/elemobs.S        Thumb hook on the element constructor — the worked
tools/elemobs_ctl.py   example of the B.W technique
tools/appendobs.S      Thumb hook on the append, with a name filter; this is
tools/appendobs_ctl.py the one to put in an AutoRun
tools/build_appendobs_boot_probe.py
                       builds the startup timing observer plus a later USB
                       shell; retained as a diagnostic, not the OpenGate path
```

Addresses used by these tools are Ver.5.02 only.

## 8. Measuring, and a trap in it

`gui image log 1` logs every `.xci` load with its dimensions (call sites
`0xc055fdf4` name, `0xc055fe14` dimensions). The GUI log channel is flooded by
`ERR` entries from `0xc055fa14` / `0xc055fa30`; filter them or the real entries
are invisible.

**The log window spans more than one frame, and the first draw after a state
change still carries the previous state's icons.** A naive probe reports the old
state's artwork as if it belonged to the new one. This produced two wrong
conclusions in a row here. The method that works:

```
close the screen → change the setting → wait ~3 s
→ open  (first draw — discard)
→ close → clear the log
→ open  (second draw — this is the measurement)
```

and cross-check by probing a different state first: if the state under test
reports the *other* state's icon, that is pollution, not a result.

### Capturing an overlay without closing it

The normal `key CAPTUREON` / `key CAPTUREOFF` screenshot path can dismiss the
Quick Set overlay.  The display shell has a separate framebuffer capture that
does not send a camera key:

```python
sh('display get_out')
sh(r'display capture \QS_TEST.XCI 3 2', retries=0)
```

The arguments are destination path, plane selection (`1` main, `2` sub, `3`
both), and compression (`0` none, `1` RLE, `2` LZ4).  Selection 3 can create
the requested file plus numbered companions.  The unsuffixed 1024x682 L8A8
file is the directly viewable UI layer; companions can be L8 or additional
L8A8 planes.  Render either form with:

```
python3 tools/render_xci.py QS_TEST.XCI
```

> ⚠️ 2026-09-19:`render_xci.py` 把檔案當 L8A8 解 —— 對**圖示**是對的,對**全螢幕主層
> capture 是錯的**。主層是 ARGB4444(每像素 2 bytes,高 nibble 是 alpha),用 L8A8 解會變灰階。
> 見 [`SPLASH_BAND.md`](../display/notes/SPLASH_BAND.md) §2。

`display capture` takes long enough that the USB request commonly reports
`LIBUSB_ERROR_TIMEOUT` even though the card files were written.  Do not retry
the command blindly: use `retries=0`, wait for the write, and confirm the exact
file and size with `dir`.  The same no-retry rule matters for `key QSON`, since
a lost reply does not prove that the toggle was lost.  Quick Set also closes
after an idle timeout, so open it, verify the image log changed, select the
target tile, and capture immediately.
- [MENU_PAGE_SWITCH.md](MENU_PAGE_SWITCH.md) — 選單裡換頁：`gui scr set` 會讓快速連按掉鍵；v4 改走原廠狀態機（變數改變事件 → controlAppState）。2026-10-25 實機。
