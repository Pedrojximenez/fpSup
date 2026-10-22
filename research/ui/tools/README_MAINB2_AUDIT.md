# MainB2 native-menu evidence audit

Read-only, standalone Python 3.9+ audit of the **stock MainB2 CINE page**.
The actual fourth OFF/ON row is **not connected**. This audit does not build
firmware, emit deployment payloads, use camera transport, or install hooks.

## Run

The input is required explicitly. There is no firmware search, default path,
hash override, external dependency, or working-directory requirement.

```sh
python3 /absolute/path/to/native_ui_audit.py --seg0 /absolute/path/to/seg0_c0000000.bin
python3 /absolute/path/to/test_native_ui_audit.py
python3 /absolute/path/to/test_native_ui_audit.py --seg0 /absolute/path/to/seg0_c0000000.bin
```

The audit prints JSON to stdout; failures print an error to stderr and exit 2.
It opens the input read-only and does not save any output file. Tests without
`--seg0` exercise synthetic parser cases; firmware integration tests explicitly
report a skip. Integration tests also reject a same-size, altered input.

Required input: 49,245,696 bytes, SHA-256
`aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`.
Do not substitute another file merely because it is named `MAIN_c0000000.bin`.

## Evidence extracted

- MainB2 `C2030364..C2055DB0`: SHA-256, 1392 records, tag counts, 193 objects.
- B2 object `C2037C1B`: ID 116, six direct children; existing CINE-visible rows
  are IDs 21878, 121, 122. Row names are serialized internal names, not translated
  UI labels. A null `modechange_y_keys` means this clip does not change y;
  it does not claim the row's absolute y coordinate is zero.
- Audio donor `C204DACA..C205460A`: SHA-256, 187 records, 23-object parent tree.
- ModeChange `C20318F7`: six active clip references against capacity seven in
  allocation-header group entry 3.
- Entire original allocation header, plus the unmodified Audio donor's
  component/group/clip/property allocation increments.

Addresses use firmware runtime base `C0000000`; `file_offset` is zero-based.
NBU base is `C18C0460`, string pool starts `C18C0474` and ends `C18EB48C`.
Records have big-endian tag/length words and are not necessarily aligned.

## Meaning and limits of the budget calculation

The hypothetical full clone keeps all original budgets and adds 23 objects,
8 groups, 20 serialized clips and 37 properties. Header size becomes 3352 bytes;
object count 216, group budget entries 60, clip entries 200, property entries 403.
These numbers describe an **unmodified donor clone only**, not a finished toggle.
The original budgets include reservations absent from serialized records, so
they must not be replaced with a simple recount of those records.

The firmware allocation-header path at `FUN_c05e6400` sums these budgets and
allocates the object lookup table (local decompilation `blk_c05.c`, around lines
185834–185889). The audit does not execute that allocator or prove heap capacity.

## Hard gates before a real fourth row

The Audio donor is `MenuItem_SelectJump`, not a pure OFF/ON widget. It retains
`MV_AudioRecord`, `B2_6` and `SUB_MV_AudioRecord` actions. Copying it unchanged
would control or open Audio settings. Object IDs and embedded references need
schema-aware remapping, not global integer replacement. Private-variable
creation, action isolation, text, focus navigation, lifecycle and page insertion
remain unimplemented and unverified. No free IDs are selected by this tool.

The existing 512-byte record-copy method does not itself support the 3028-byte
stock allocation header or adding an entire subtree. fp-Merge hook composition
and parser lifetime must be handled separately. All JSON readiness flags remain
false; this output must never be interpreted as installation permission.
