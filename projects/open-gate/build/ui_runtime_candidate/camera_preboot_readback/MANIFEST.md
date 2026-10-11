# OG3K UI candidate — camera preboot staging record

Date: 2026-09-14  
Camera: SIGMA fp, firmware `5.02.0.V91`

## Runtime-cave gate

`0xC0793060..0xC0793EF4` (end-exclusive, 3732 bytes) was read in four bounded
chunks with exact address-coverage checks.  All 933 words were zero in each of
three live states:

- standby/live view;
- Quick Set open;
- main menu open.

The first unchunked shell attempt was response-truncated and is not counted as
evidence.  `../check_og3k_ui_cave.py` is the reproducible bounded reader.

## Card staging

The prior root files were fully backed up at
`../../camera_backups/pre-ui-runtime-20260914/` before either file was changed.
The new files were written with the vetted USB-shell file writer and then read
back in full from the card:

| file | bytes | source SHA-256 | card-readback SHA-256 |
|---|---:|---|---|
| `AutoRun.txt` | 32772 | `3a2a58c9b7f20db8a2f47d0a62774fd1aabb8c396e734fe4780fac0e6b5f7c53` | `3a2a58c9b7f20db8a2f47d0a62774fd1aabb8c396e734fe4780fac0e6b5f7c53` |
| `VSHL.BIN` | 32768 | `583190c93bc56aa5b1429d9a61a22d72d5dd6715314c5d26005c7fd32f22ab06` | `583190c93bc56aa5b1429d9a61a22d72d5dd6715314c5d26005c7fd32f22ab06` |

Status: **staged on the card, byte-verified, not yet executed**.

The previously active VSHL was the old `ui_boot_probe`, whose
`0xC0733000..0xC0734000` region overlaps this resident.  Do not use a warm
reboot or forward `reboot`/`poff` through the USB worker.  Disconnect USB and
all external power, remove the battery for at least 30 seconds, reinstall it,
boot with USB unplugged, and attach USB only after startup finishes.
