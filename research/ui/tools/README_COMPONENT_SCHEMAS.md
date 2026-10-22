# Native UI component property schemas (fp V5.02)

Offline-only extraction of the 18 ordinary component schemas used by the
MainB2 row candidate. This is shared UI knowledge, not product code, a page
loader, camera tool or renderer.

Input must be the original `out/seg0_c0000000.bin`, exactly 49,245,696 bytes,
SHA-256 `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`.
Do not substitute the similarly named MAIN image.

## Evidence and limitations

- Native Thumb name getters identify the component plugins. Fourteen original
  constructor prefixes are executed in Unicorn against synthetic zeroed RAM.
  Execution stops **before** `C05D5E30` property registration.
- Four constructors (`controlAnimation`, `drawImage`, `drawRect`, `drawText`)
  require additional context or renderer setup. Their original MOV/MOVW/MOVT
  argument windows and final BL target are checked using Capstone instead.
  Those constructors are **not** claimed to have executed.
- The per-component JSON records which method was used. Native descriptors
  are little-endian 12-byte `{type, name pointer, default raw}` entries.
  A default raw value may itself be a pointer and is not decoded as an integer.
- Drawable component type 4 has two extra properties added by
  `C05D5E30`. Original `C05D5670` resolves `count-2` to
  `C2DFFC00: rect/type5` and `count-1` to
  `C2DFFBF4: layout/type10`. Thus drawText declares 30 properties but has
  **32** serialized properties. Omitting that tail misparses masks and values.
  This common-tail finding is explicitly a pinned static instruction trace.
- Animation clip records (`0x1000a`) have a custom structure. They are not
  one of these ordinary property lists.

The source image is mapped RX; only synthetic RAM is writable. Each emulated
call has a 1,000-instruction / 100 ms bound. The scanner may execute bounded
getter/prefix code inside the pinned image; it is not the explicit native
interval allowlist used by the separate variable-registry probe. There is no
camera, USB or network code. Allocators, renderer, property registration,
events, lifecycle and actual menu display remain untested.

## Serialized values

The reader at `C05E7B78` consumes values only for set bits in each 32-bit
property mask. Integers, floats and references are big-endian in resources:

| Native type | Bytes per present value |
| --- | ---: |
| 0, 1, 2, 3, 9, 10, 14 | 4 |
| 4, 5, 8 | 16 |
| 6 | 8 |
| 7 | 12 |
| 11 (string + resolver flag) | 5 |
| 12, 13 (string) | 4 |

Type 14 is an object reference. Type 11's fifth byte can make the following
field unaligned. Literal labels require resolver flag 0; a string-pool change
alone does not disable localized/resource-name lookup. Validate masks,
property counts and exact record extent; never globally replace matching
integers. Component-record offsets and animation records are separate schemas.

## Run

Requires Python 3, Unicorn 2.1.4 and Capstone 5.x in the chosen environment.
Missing dependencies are an error, not skipped success. On macOS Unicorn's
JIT may require narrowly scoped execution permission outside the desktop
sandbox; it does not require camera access. Do not pin a transient cache path.

From this directory:

```sh
python3 -B native_component_schema.py --seg0 /absolute/path/to/seg0_c0000000.bin --output /new/path/component-schemas.json
python3 -B test_native_component_schema.py --seg0 /absolute/path/to/seg0_c0000000.bin --report /new/path/test-report.json
```

Outputs refuse to overwrite an existing file. The 13-test suite covers all
18 schemas, provenance, drawable tails, reference types, bounds, exact image
pinning and count/call tampering. A schema extraction pass is not proof of
navigation, callbacks or safe runtime installation.
