# Gyro2 release status (2026-10-07)

For whoever runs `fpSup/tools/release_v3.py`. Not yet released, no commit or push.

**Row to add to `PRODUCTS`.** This session did not edit fpSup:

```python
'gyro2':      ([ROOT / 'projects' / 'gyro2-sup' / 'build.py'], '20GYR2.BIN', 'GYR2', 'Gyro2'),
```

| | |
|---|---|
| builder | `projects/gyro2-sup/build.py --out DIR` writes `DIR/20GYR2.BIN` and `build.json` |
| sup | `20GYR2.BIN`: 4,208 B, sup_id `GYR2`, header version 4, block 56,696 B |
| sha256 | `cbf91f8c36efb6481329000b6736cda26eb0781fe9c8acfa1cd5f7c073a0f8d5` |
| on the camera | yes. These exact bytes have been on the card since 2026-10-07 (LOAD.LOG confirmed) |
| recorded with these bytes | A001_017/018/019: OG3K 29.97p, Lossless on, 1/50. A001_023–025: OG2K 29.97p, manual lens (Nokton 28) |
| not tried with these bytes | FHD/UHD, 59.94p, 120p. An earlier test build worked at FHD 59.94p |
| claims | header DMA `C038C77C` CHAIN, level `C050D4C8` CHAIN, Vd IRQ word `C0125480` EXCL (required) |
| offline | 32 emulator tests pass, mutation 43/43 |
| suggested version | `fpsup-gyro2-v0.1.0` (no test suffix: the bytes ran on the camera) |
| README draft | `release/README.txt` (EN + zh, plain, no firmware addresses) |

## Blockers

1. Users also need the **Gyroflow (fpSup)** Resolve plugin. It is in the user's
   gyroflow-plugins fork (`tools/gyroflow-plugins`, branch `feature/cdng-makernote`),
   with all commits local and nothing pushed. Its first release (`fpsup-v1`) needs a
   push and a tag, which the user decides.
2. The global fpSup blocker: the `lossless/two-lanes-dma` branch has uncommitted
   paths and must be merged back to main before a release.
