# Retired 2026-08-25 — superseded by ../usbshell

The old USB shell transport. It bolted endpoints 0x84/0x05 onto the PTP gadget by
hooking the descriptor builder at 0xC04DC618, then enabled and maintained those
endpoints by hand (CTX4_MODE, FUN_c01e62a9, DALEPENA). The firmware did not know
they existed, so a record-mode reconfiguration tore them down — which is why it
needed a REC_FLAG gate and still broke recording.

`../usbshell` replaces it: the PTP gadget is left as the firmware builds it and
only its class handler is removed, so the endpoints are firmware-owned.

Kept for reference only. Nothing current reads these files.
