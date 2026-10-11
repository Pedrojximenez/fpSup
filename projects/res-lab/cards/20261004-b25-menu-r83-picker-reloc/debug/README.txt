Sensor Lab r83 B2_5 debug non-Fast test card (2026-10-04)

Standalone Sensor Lab card with USB diagnostic shell. The USER cave migration,
recording-picker profile ID fix, and MODE FILTER FPS correction are included.

Status: offline candidate only. It has not been written to fpSup2 or retested
on camera. The last written fpSup2 card is r81, which the user reports freezes
immediately when REC is pressed. Do not use r81 for recording acceptance.

Offline verification: eight build combinations, exact artifact inspection,
15 corrupt-artifact mutations, full loader/USER/UI boot and journal restoration,
and packed recording picker execution. The r83 picker writes profile ID 87;
the r81 binary writes 0xC0BE3FA4. Factory C073 data is unchanged in simulation.
This does not establish camera recording or warm-start stability.

Boot files:
AutoRun.txt  32768 bytes   SHA-256 5dc89b8506e8ce408276a9eab61fbb9fda94d4a194b65f2fd17c9e410b8fe642
fpSup.BIN    426280 bytes  SHA-256 37bcf712af5d152f12561f42d4e617c2e0b5c9a4b9fdde4eab9434c7ea95a73f

Keep AutoRun.txt and fpSup.BIN from this same directory together.
