# 20261025-rawpool-01 — CinemaDNG left in the RAW class after a stock take (read only)

Card: v4 merged card as left by sigmafp-re-a9/e4 (Lossless on). Take: user pressed REC ~2 s in CINE FHD 12-bit → `\CINEMA\A001_020`, 53 frames.
Host: `host/rawpool.py` (probe / scan / match). No camera code, nothing written, no reboot. USB only 10 s after the stop.

| step | result |
|---|---|
| probe before (standby) | mode STILL_REC; class obj 0xC3073C3C; chain = 2 sentinel blocks 0x5F900900 / 0x7FF1FEC0 (0x40 each); RAW total 543,290,880 = obj word 2 |
| probe after the take | mode **MOVIE_REC_DNG**; arena 0x53B00900..0x7FF1FF00 (742,520,320); RAW used **0**, used(max) 65,149,312 |
| scan | 742 MB over MEM1 in ~3 s (≈400 MB/s, 16 MiB windows); **31 DNG headers** at 0x40 alignment |
| match | **14 byte-identical to card files: frames 40–53 = the last 14 frames of the take** |

Details:
- Today's take: 17 buffers in slots 0x31A400 apart from 0x53B18400 (≈17 × 3.25 MB ≈ used(max)). 14 exact; 3 (0x55a1f800 uncompressed 3,248,316 B,
  0x55d39c00 / 0x56054000 compressed 759,808 B) carry the take's DateTime but match no card file (differ from byte 4 = IFD offset on). Unexplained — Lossless
  intermediates are the first suspect.
- 14 more DNGs from **A001_017 (10-24 03:06, OG3K 3024×2010)** sit above 0x58155000, slots 0x8C7800 apart: higher than today's smaller take reached, and they
  survived the reboots in between (warm restart keeps DRAM). So a camera-side scan must tell takes apart (DateTime / size / the newest clip), not take every DNG.
- Slots were reused round-robin; the survivors are exactly the last frames written, i.e. "the CDNG still in the cache" the user's push idea asks for.

Consequence: "push CDNG after stop" needs no hook and no allocator: after the stop the control task scans the RAW arena (chain from 0xC30739DC[10]),
keeps the newest take's DNGs and pushes them (FPP1 source 4, fmt 5). Expected yield ≈ used(max) / slot ≈ last 14–17 frames at FHD.
