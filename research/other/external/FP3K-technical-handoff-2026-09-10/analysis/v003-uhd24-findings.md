# Incomplete UHD24 diagnostic return

The SSD return contains the prior idle POOL.BIN, LOADED.BIN and STATE.BIN byte-for-byte, with their previous timestamps. New POOL000.BIN and LOADED000.BIN have camera timestamp 2050-03-16 04:36:14. LOADED000.BIN matches the verified 1020-byte payload; POOL000.BIN matches the earlier 12-byte allocation descriptor. No STATE000.BIN exists. SD contains only INFO.TXT.

The user pressed REC and reports the camera operated normally while FPD003_LOADING remained displayed. The banner is not sufficient to diagnose a hang. Loading reached the code/allocation readbacks; sampler invocation, capture completion, and idle-gate outcome remain unknown.

Stock saves use numbered output filenames. The checker previously selected unsuffixed files blindly; it now rejects incomplete/multiple file sets, checks allocation against the capture header, and cautions that contents alone do not prove boot identity. Verified against the original successful idle return, this mixed return (rejected), and a deliberately mismatched allocation (rejected).

Next: idle-only script with unchanged payload and handler readbacks before arming, after arming, and immediately after echo returns. Fresh output folders required. No inference about recording geometry can be drawn from this return.
