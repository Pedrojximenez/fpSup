# FPD003 idle preflight findings

Returned files: `diagnostics/v003-idle/SSD/FPD003`; SD contains INFO.TXT only. Stock file routing chose the SSD again.

- STATE.BIN is exactly 99,904 bytes with valid FPR3 header, completion state 1 and all 120 sequence numbers.
- LOADED.BIN exactly matches the tested 1,020-byte payload, SHA-256 `c03eac8185417b4c99dc1f72061fb9efc31d59dfe9c801af7ed333f88ebfcd40`.
- POOL.BIN reports base 1157017024, size 131072, type 0. Its base and size exactly match the capture header.
- Every sample has sensor mode 8 before and after, processing profile 5, copy flag 1, and both recording flags zero. No source-pointer or mode changes were detected.
- All 67 copied parameter words match stock profile 5 in every sample. RAW output/crop dimensions are zero for this standby profile; that is not a failed memory read.
- Camera setting dimensions are 3840×2160. Acquisition output geometry remains zero while idle.

This validates this camera's first idle load, RAM capture, pointer traversal and delayed native file output. It does not validate execution during recording, all-pixel scaling, or recording stability.

Next: one UHD true24 / 12-bit CinemaDNG recording lasting about five seconds, using the identical payload. Start about two seconds after FPD003_SAMPLING appears. If it stops early, do not restart; let the diagnostic finish. No second take during the same boot. Return both FPD003 directories to the already-created `diagnostics/v003-uhd24/SD/FPD003` and `diagnostics/v003-uhd24/SSD/FPD003` folders.

Machine-readable detail: `analysis/v003-idle.json`.
