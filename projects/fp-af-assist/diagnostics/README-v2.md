# Drain observation diagnostic v2 — offline build

2026-09-16. Prepared under the USB-shell skill's offline/ownership boundaries.
No process, daemon, device, worker, or card action was performed for this build.
The existing `fpshd-diag` v1 binary and `fpshd-diagnostic.c` remain byte-for-byte
unchanged. The new executable is **`fpshd-diag2`**; no running inode was replaced.

## Purpose and scope

The main task reported a 12-byte receive with hex
`0c00000003000320c1000000` for transmitted sequence 193. This build does not
assume its origin or treat it as an accepted FPSH packet. It can reveal whether
the daemon's already-existing `drain_in()` subsequently discards a matching
FPSH reply. That conclusion requires new actual diagnostic records; the fixture
below is synthetic and cannot establish what the camera did.

Relative to v1, `fpshd-drain-log-v2.patch` adds one #ifdef-only helper and one
#ifdef-only call immediately after the existing drain transfer. The transfer,
20 ms timeout, eight-iteration bound, clear-halt, continue, break and return
conditions are unchanged. There is no additional USB call or retry.

Each existing drain result emits one stderr line:

```text
FPSH_DIAG_DRAIN source=drain count=... seq=... drain_iteration=... rc=... moved=... expected=16384 captured=... clock=MONOTONIC_RAW clock_rc=... raw_sec=... raw_nsec=... hex=...
```

- `seq` is the current transmitted request's `g_seq`, not a decoded response
  transaction number. Decode a received FPSH sequence independently from `hex`.
- `drain_iteration` is zero-based, 0–7, exactly matching the existing loop.
- `count` is process-local to **drain** diagnostics, separate from v1's unchanged
  frame-error counter and output format.
- `moved` and `rc` retain the actual libusb return values. `captured` is clipped
  to 0–64; only those returned bytes are inspected. Empty timeouts are logged
  with empty `hex=` and do not expose previous buffer contents.
- `expected=16384` is the unchanged drain receive capacity, not a promise that
  16384 bytes should arrive. A shorter successful drain is normal.
- Numeric `CLOCK_MONOTONIC_RAW` is host time, not camera exposure time or UTC.

As in v1, `errno` is restored after logging. Stderr can block or perturb timing;
the diagnostic is not timing-neutral or a transport repair. It does not accept,
skip differently, reinterpret, or resend either PTP-shaped or FPSH packets.

## Build and verification

The official libusb header/library provenance and compiler details remain in
[README.md](README.md). Built warning-free with the same flags/library:

```sh
cc -O2 -Wall -Wextra -DFPSH_DIAGNOSTIC_FRAME_LOG=1 fpshd-diagnostic-v2.c -Iinclude -L/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -lusb-1.0 -Wl,-rpath,/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -o fpshd-diag2
cc -O2 -Wall -Wextra test_drain_log.c -Iinclude -L/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -lusb-1.0 -Wl,-rpath,/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/lib -o test-drain-log
python3 -B -m unittest -v test_diagnostic_v2.py test_diagnostic_build.py
```

All four tests pass. Macro-disabled v2 preprocessing remains exactly identical
to frozen upstream. The drain fixture **never invokes daemon main** and replaces
every bulk transfer with a mock. It tests the existing loop receives a synthetic
valid-CRC FPSH frame with sequence 193 followed by a zero-byte timeout, with
exactly two transfers, unchanged endpoint/size/timeout, and no extra attempt.
It also checks exact 64-byte output, a 128-byte result clipped to 64, metadata,
raw timestamps, and preserved errno. Existing v1 formatter tests also pass.

## SHA-256

| Artifact | SHA-256 |
| --- | --- |
| `fpshd-diagnostic-v2.c` | `ec28e7c740c44b4186333e9da6e17b00be16914bf12b502f4330e65005bea729` |
| `fpshd-diag2` | `9e7375c71d448fe0a4ff52ce61f36489c2446783da7474aba679b66333e7cb4a` |
| `fpshd-drain-log-v2.patch` | `ad0f5e34979d81e090e58ec2bc19f8654b5a2abce5d1d6271a31947e571b268a` |
| `test_drain_log.c` | `2245de3539f8dc4cca3615e5c9ce28c93d4d269578a1792bb94363a5d6f07347` |
| `test-drain-log` | `a81e817416ee890f4c29b3099452c9cb5c71ddcdad6376bc5e8382725e5d8f21` |
| Unchanged `fpshd-diag` v1 | `9da2a00a2aa6109a119a61b822fd63623a68b02f97f1d35e821660abc6be5795` |
| Unchanged v1 source | `36041ca0ebb685790e519ac1dbc2a1a43b043e8da75ba6075242766524449c34` |
