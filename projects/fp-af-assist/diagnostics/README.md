# fpshd short-IN-frame diagnostic build — offline preparation

Prepared 2026-09-16. **No daemon was started, stopped, replaced, or connected to
the camera during this preparation.** Deployment requires the main task's
separate approval and exact owned-daemon transition. These binaries are not
installed over the maintained tools.

## Narrow change

`fpshd-diagnostic.c` is a copy of the maintained host source plus the small
`fpshd-frame-log.patch`. With `FPSH_DIAGNOSTIC_FRAME_LOG` defined, the existing
64-byte IN-frame error branch writes one line to **stderr**, before its unchanged
error/clear-halt/drain/return handling. It records:

- A process-local diagnostic count, transmitted request sequence, frame index,
  libusb return code, moved/expected byte counts, and captured length.
- `CLOCK_MONOTONIC_RAW` seconds/nanoseconds and the clock call's result. This is
  a numeric monotonic timestamp, not UTC or a camera tick.
- Exact hex bytes `[0, min(max(moved, 0), 64))`; the uninitialized tail of a short
  receive buffer is never inspected. A zero-byte failure has empty `hex=`.

The logger also records a failed transfer that reports all 64 bytes. It does not
log ordinary successful frames, bad-magic/CRC errors on successful full frames,
raw-block errors, or drain contents. It preserves `errno` and introduces no USB
calls, new retries, altered drain policy, packet acceptance, worker or card
changes. **Writing stderr can perturb timing or block on its sink**; this is
diagnostic instrumentation, not a transport fix or timing-neutral measurement.

Without the macro, preprocessing is byte-for-byte identical to the frozen
upstream copy. Normal builds' machine-code text sections also compare equal.
Complete executable hashes differ (Mach-O metadata/signing); they are not
claimed to be byte-identical executables.

## Provenance and SHA-256

Maintained source:
`/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/host/fpshd.c`

| Artifact | SHA-256 |
| --- | --- |
| Original / `fpshd.upstream.c` | `0ef089fcc296a84016622e0bbf3e8a45a8f3852ef2c782a4b6fab58c29c8ed4f` |
| `fpshd-diagnostic.c` | `36041ca0ebb685790e519ac1dbc2a1a43b043e8da75ba6075242766524449c34` |
| `fpshd-frame-log.patch` | `91c32b29e89ae91b9cf93d18e653d3dbac2251f37fa3b948e20bf027ea75ecc6` |
| Official `include/libusb.h` | `8c77e192d53960966c42d5f6ef204e3be88c9ff3ca431acdd5c6039689b3fe0b` |
| Existing libusb dylib | `56cadf8d15add08d145a363d7cd6f62b3aa9702edc5274ab4f45562744900b3b` |
| `fpshd-diag` | `9da2a00a2aa6109a119a61b822fd63623a68b02f97f1d35e821660abc6be5795` |
| `fpshd-normal-check` | `71d8b6902a67cf623dce20bc91c909c8506d7d99d6ca3fa722740b65d4f20b65` |
| `fpshd-upstream-check` | `8e2c41fa602fc845916c2cfb2ac01ab2089bec472017a09057639c330ce6aab4` |
| `test-frame-log` | `a17745decba607b07e2b2f209663f59047d32af12512ee3a64f23916f2c890d4` |

The installed library was identified by calling only `libusb_get_version()` via
local library introspection: **1.0.29.11953**, empty rc, description
`https://libusb.info`. No `libusb_init` or device call was used. Its path is
`/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib/libusb-1.0.dylib`;
`projects/usb-shell-sup/lib/libusb-1.0.dylib` is the existing symlink to it.

No header was installed locally. The matching, unmodified official header was
retrieved from [libusb v1.0.29](https://raw.githubusercontent.com/libusb/libusb/v1.0.29/libusb/libusb.h),
matching the [official release tag](https://github.com/libusb/libusb/releases/tag/v1.0.29).
Its upstream copyright/license notices remain intact. No replacement library,
package installation, or invented ABI declarations were used.

## Build check

Compiler: Apple clang 21.0.0 (`clang-2100.3.27.1`), target arm64-apple-darwin27.0.0.
The maintained Makefile's `-O2 -Wall -Wextra` flags were used, with the verified
existing library path/rpath and the official header. All four builds completed
with no warnings or errors. From this directory:

```sh
cc -O2 -Wall -Wextra fpshd.upstream.c -Iinclude -L/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -lusb-1.0 -Wl,-rpath,/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -o fpshd-upstream-check
cc -O2 -Wall -Wextra fpshd-diagnostic.c -Iinclude -L/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -lusb-1.0 -Wl,-rpath,/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -o fpshd-normal-check
cc -O2 -Wall -Wextra -DFPSH_DIAGNOSTIC_FRAME_LOG=1 fpshd-diagnostic.c -Iinclude -L/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -lusb-1.0 -Wl,-rpath,/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -o fpshd-diag
cc -O2 -Wall -Wextra test_frame_log.c -Iinclude -L/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -lusb-1.0 -Wl,-rpath,/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -o test-frame-log
python3 -B -m unittest -v test_diagnostic_build.py
```

Two offline tests pass:

1. Macro-disabled preprocessed source equals the frozen upstream source.
2. The fixture invokes **only the formatter**, never the renamed daemon entrypoint.
   It verifies exact 12-byte/64-byte data, zero/negative counts, the 64-byte cap,
   sequence/count metadata, a valid raw timestamp, and preserved errno.

`otool -L fpshd-diag` resolves the same `@rpath/libusb-1.0.dylib` and system C
library as the existing daemon. This is build/format verification, **not a live
USB validation or authorization to launch the binary**.
