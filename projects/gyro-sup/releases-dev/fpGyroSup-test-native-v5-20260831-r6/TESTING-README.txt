fpGyroSup native lifecycle r6 — SD/CinemaDNG 40-SECOND CONTROL

Use release-card first. Do not use debug-card for the first test.

r6 changes one timing decision from r5. Native CDNG/MOV lifecycle still owns
the exact clip id, volume and final boundary, but XMP allocation alone may no
longer start GYR collection or media access. The camera's proven real recording
flag must also be live. Stop still waits for native finalize.

The original bounded streaming design remains in place. Gyro data is written in
16 KiB blocks throughout an arbitrarily long recording; it is not accumulated
for the whole take in RAM.

Test:
1. Remove the camera battery for at least 30 seconds and keep USB unplugged.
2. Install AutoRun.txt, VSHL.BIN and PGEN.BIN from release-card as one set.
3. Cold boot and confirm fpSup! appears.
4. Start one CinemaDNG recording to SD and let it pass 30 seconds.
5. Manually stop at about 40 seconds. Do not start another take.
6. Leave the camera on until SD activity and recording protection are fully
   released, then power off and return the card to the reader.

If the camera stops itself near 20 seconds, do not retry; return the card. Do not
test MOV, USB SSD, rapid consecutive takes or boot recovery in this pass.
