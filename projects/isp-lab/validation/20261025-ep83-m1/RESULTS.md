# 20261025-ep83-m1 — push engine milestone 1: blocked before the camera ran anything

- `host/ep83_m1.py` → fpshd 3.2.0 `EP83 16384 echo` → `ERR ep83 requires iface0 alt0 bulk EP01/82/83 MPS64/512/1024`.
  The daemon refused before sending the trigger: sender `done = 0` (never ran), echo handler restored and checked (0xC03D99A0), shell answers.
- Why: the cached config descriptor of this card (v4 merged, 2026-10-25), read without opening the device:
  `iface 0 alt 0 class 6 (PTP)`, `EP01 bulk 1024`, `EP82 bulk 1024`, **`EP83 attr 03 (interrupt) MPS 64 interval 11`**.
  The `PUSH` descriptor patches in fpSup/fp_usb_shell/patches.py (EP83 → bulk 1024, burst 3) and even `IFACE` (class ff) are applied only by the
  old AutoRun cards; the v4 shell sup applies none (ptpcamerad is held off by the host kill loop instead).
- So EP83 cannot carry the push on this card. Needs: the PUSH patches written before USB enumeration (v4 shell sup / loader), or another channel.
