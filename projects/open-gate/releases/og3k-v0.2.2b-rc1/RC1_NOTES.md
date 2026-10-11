# OG3K v0.2.2b-RC1 validation notes

## Status

This is an **offline-only release candidate**. The exact package has not been installed or camera-tested. The camera was deliberately left untouched because it was in use. Do not publish or distribute this as a final release.

The functional payload was frozen at 20:30:49 local time. Unrelated canvas-diagnostic source files changed afterward; RC1 predates and does not contain those changes. For that reason this artifact is being preserved rather than rebuilt from the now-drifted working tree.

## Confirmed v0.2.2a defect and fix

At 25 fps and 180 degrees, v0.2.2a can let an FHD/UHD format lookup miss and fall back to a 30 fps table entry. The angle path then computes 1/60 second even though the recorded clip remains marked as 25 fps.

RC1 preserves the stock format-table pointer on the non-OG3K path by moving the temporary bit-depth value from `r1` to preserved register `r5`. The shutter-angle calculation is not changed.

Compared with v0.2.2a, exactly seven 32-bit words differ, all in the `fmttable` section at `0xC0730800`:

| Address | v0.2.2a | v0.2.2b-RC1 |
|---|---:|---:|
| `0xC0730800` | `E92D5018` | `E92D5078` |
| `0xC0730810` | `03A01000` | `03A05000` |
| `0xC0730824` | `03A01003` | `03A05003` |
| `0xC073083C` | `E3A01004` | `E3A05004` |
| `0xC0730880` | `E5841000` | `E5845000` |
| `0xC07308D4` | `E8BD5018` | `E8BD5078` |
| `0xC07308DC` | `E8BD5018` | `E8BD5078` |

The release payload has 80 sections, entry point 0, and no USB worker or USB shell.

An independent artifact comparison confirms that v0.2.2a and RC1 have identical section addresses, order, sizes, loader entry, and non-`fmttable` payloads. `AutoRun.txt` retains the same 135 commands; its only changes are the RC banner/comments and equal-length padding.

## Offline verification completed

- At build time, before the unrelated source drift, the format-table guard and Angle/FPS package verification passed.
- Native UI package structural verification: PASS
- At build time, the paired debug-versus-release verification passed; the release is the paired build with only the USB shell removed.
- Independent post-freeze allowlist audit against public v0.2.2a: PASS; exactly the seven documented `fmttable` words differ and all other sections are byte-identical.
- Loader regression suite: 10/10 PASS

Offline checks establish that the intended defect is corrected in the binary and that no unrelated functional payload changed. They do not replace a camera test.

## Hardware A/B plan — only after the camera is free

1. Use CINE M, fixed ISO, 25.00 fps, 180 degrees, the same lens/aperture and 50 Hz light source throughout. Disable crop/Super35 zoom and leave USB disconnected.
2. With the test card removed or the loader files disabled, perform a complete battery-out cold boot into stock firmware. Do not reinstall v0.2.2a merely to reproduce the known defect.
3. Record short FHD and UHD CinemaDNG clips and confirm the stock baseline is 1/50 second.
4. With USB disconnected, place only `AutoRun.txt` and `VSHL.BIN` from this folder at the card root. Perform another complete battery-out cold boot and confirm the `v0.2.2b-RC1` banner.
5. Record OG3K, FHD, and UHD at 25 fps / 180 degrees so the test also covers both exits from OG3K. The first, middle, and last DNG of every clip must report 25 fps and 1/50 second. Expected active/crop dimensions are:
   - FHD: 1936 x 1090, crop 1920 x 1080
   - UHD: 3856 x 2170, crop 3840 x 2160
   - OG3K: 3024 x 2010, crop 3008 x 2000
6. If the 12-bit gate passes, repeat OG3K at 10- and 8-bit and verify the selected bit depth and geometry.
7. If any check fails, stop. Remove or rename the loader files, or use a clean card, and perform a complete battery-out cold boot. Confirm the OG3K banner/option is absent and record one stock FHD 25 fps / 180-degree clip at 1/50 second. Do not hot-reinstall or warm-restart.

The RC can be promoted only after this A/B passes.
