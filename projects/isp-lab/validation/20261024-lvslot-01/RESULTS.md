# 20261024-lvslot-01 — LV slot register + movie objects, read-only, standby (CINE, LCD)

- `[0xC31DF8D8]` = 0 → channel 2 → register 0x301832E8. LCD descriptor: 1620×911, n=4, slots 0x49801000 + k·0x3FC000.
- The register has three fields (20 reads, ~10 ms apart): **byte2 = slot being written, byte1 = last finished (always byte2−1 mod 4),
  byte0 = slot on screen** (the firmware's `&0x1F`; flips from byte1 to byte2 some time after the write moves).
  byte2 steps about every 33 ms (≈30 fps). Channels 1 and 8 show the same layout.
- So the sampler pushes byte1 (sup/ix_wr.c `ix_lv_step`, unicorn LvTests updated, mutant = use byte2).
- `0xC358DCC0[0..7]` all 0 in standby (expected: the movie objects only exist during/after a take; check after a take later).
- Raw: ro_check.out; script: ro_check.py.
