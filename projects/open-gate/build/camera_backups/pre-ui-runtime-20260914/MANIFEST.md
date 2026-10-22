# Pre-OG3K-UI camera-card backup — 2026-09-14

Captured over the vetted USB-shell file reader before replacing either root
file.  Both reads reported full byte counts and success.

| file | bytes | SHA-256 |
|---|---:|---|
| `AutoRun.txt` | 32772 | `014b178a818635d1184547fefe52753974e0a307d1c471c7e70b3716ee8fec90` |
| `VSHL.BIN` | 32768 | `230b080b44643f05bf11a83f49406a2ead55bce0de7aebdfc217c91cc823d126` |

The VSHL hash matches `projects/open-gate/build/ui_boot_probe/VSHL.BIN`; that
probe owns `0xC0733000..0xC0734000` and is mutually exclusive with the new UI
resident.  The root AutoRun is the standard `fpSup-Shell-v3.1.0` loader variant,
not byte-identical to the local probe AutoRun.

Restore both files together and perform a full battery-out cold boot before
using this backup.  Do not hot-load either resident over the other.
