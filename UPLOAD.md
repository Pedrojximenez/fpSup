# Research and development snapshot — 2026-10-12

This upload preserves `research/` and `projects/` from the local SIGMA fp development workspace.

- Files included: **18,765**.
- Original included content: **14.10 GiB**.
- Stored content: **13.82 GiB** before Git compression.
- Large files preserved with lossless gzip compression: **10**.
- Symbolic links copied as their target bytes for portability: **10**.
- Oversized files omitted after compression: **54**, totaling **17.68 GiB**.

## Finding material

Start with [the original workspace index](INDEX.md), or browse [research](research/) and [projects](projects/).
The index and source code retain references to the larger local workspace. Paths into `fpSup/`, firmware images, host tools, and other-camera research outside the two requested roots are not part of this snapshot.
`projects/open-gate/build/armasm.py` was copied from its linked source so that this entry does not become a broken link.

## Compressed files

Files larger than 50 MiB were losslessly compressed when the result fits below 95 MiB. Their original directory and filename are preserved with an additional `.gz` suffix. Files that already fit GitHub's 100 MiB limit may instead remain in their original format.
For example, `commands.jsonl.gz` restores to `commands.jsonl` using a gzip-compatible archive utility, or:

```sh
gzip -dk path/to/commands.jsonl.gz
```

[`UPLOAD_MANIFEST.json`](UPLOAD_MANIFEST.json) lists every included original path, original size, SHA-256, stored size, and stored SHA-256. It also records original symbolic-link targets and every omission.

## Omitted oversized captures

These files remain in the original local workspace. They exceeded the per-file upload cap even after lossless compression.

| Original path | Size (GiB) |
| --- | ---: |
| `research/imaging-hw/color-characterisation/exports/13a_2d - 00000002.tif` | 0.134 |
| `research/imaging-hw/color-characterisation/exports/13p3d60_2d - 00000002.tif` | 0.134 |
| `research/imaging-hw/color-characterisation/exports/output - 00000002.tif` | 0.134 |
| `projects/res-lab/validation/20261011-m12-rate-reload-live/reload-120-control/hdmi.mkv` | 0.143 |
| `projects/res-lab/validation/20261011-m12-rate-reload-live/reload-120-observe/hdmi.mkv` | 0.136 |
| `projects/res-lab/validation/20261011-m12-rate-reload-live/reload-120-quiet/hdmi.mkv` | 0.136 |
| `projects/res-lab/validation/20261011-m12-rate-reload-live/reload-240-a/hdmi.mkv` | 0.143 |
| `projects/res-lab/validation/20261011-m12-rate-reload-live/reload-240-bulk16-quiet/hdmi.mkv` | 0.136 |
| `projects/res-lab/validation/20261011-m12-rate-reload-live/reload-240-quiet/hdmi.mkv` | 0.136 |
| `projects/res-lab/validation/20261011-m12-rate-reload-live/reload-280-a/hdmi.mkv` | 0.143 |
| `projects/res-lab/validation/20261011-m12-rate-reload-live/reload-280-eightbit-a/hdmi.mkv` | 0.134 |
| `projects/res-lab/validation/20261011-m12-rate-reload-live/reload-280-eightbit-observe/hdmi.mkv` | 0.134 |
| `projects/res-lab/validation/20261011-m12-recurrence/user-rollback-v38-120-check/hdmi.rgb` | 0.396 |
| `projects/res-lab/validation/20261011-m12-recurrence/v39-120-chronology/hdmi.rgb` | 0.396 |
| `projects/res-lab/validation/20261011-m12-recurrence/v39-280-chronology/hdmi.rgb` | 0.396 |
| `projects/res-lab/validation/20261011-m12-recurrence/v39-engine30-240-chronology/hdmi.rgb` | 0.396 |
| `projects/res-lab/validation/20261011-m12-recurrence/v39-engine30-280-firstbatch/hdmi.rgb` | 0.396 |
| `projects/res-lab/validation/20261011-m12-recurrence/v40-engine30-280-firstwrite/hdmi.mkv` | 0.106 |
| `projects/res-lab/validation/20261011-m12-recurrence/v40-matching-280-firstwrite/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/h2-native30-v16-quiet/hdmi.mkv` | 0.108 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/native-m12-identity-quiet20/hdmi.rgb` | 1.483 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/sensor-only-native30-quiet20/hdmi.rgb` | 1.483 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/ssd-240-manual/hdmi.mkv` | 0.842 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/ssd-240-sensorlab-v15-manual/hdmi.mkv` | 2.861 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/ssd-240-v14-manual/hdmi.mkv` | 1.961 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-120-inner-v14-quiet/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-120-planes-early/hdmi.mkv` | 0.134 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-120-quiet/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-120-repeat/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-240-inner-v14-quiet/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-240-planes/hdmi.mkv` | 0.134 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-240-planes-early/hdmi.mkv` | 0.134 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-240-quiet/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-240-sensorlab-v15-quiet/hdmi.mkv` | 0.107 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-240-small-lossless-v17-quiet/hdmi.rgb` | 1.483 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-audiooff/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-bulk1-gyro2off-quiet/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-bulk1-inner-v14-gyro2off-quiet/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-bulk1-native-trace/hdmi.mkv` | 0.134 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-bulk1-quiet/hdmi.mkv` | 0.134 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-gyro2off-native-trace/hdmi.mkv` | 0.109 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-gyro2off-quiet-selected/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-inner-v13-quiet/hdmi.mkv` | 0.109 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-inner-v14-gyro2off-native-trace/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-inner-v14-gyro2off-quiet/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-inner-v14-native-trace/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-inner-v14-quiet/hdmi.mkv` | 0.109 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-native-trace/hdmi.mkv` | 0.134 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-planes-early/hdmi.mkv` | 0.134 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-quiet/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-280-sensorlab-v15-quiet/hdmi.mkv` | 0.106 |
| `projects/res-lab/validation/20261011-virtual-rate-context-live/tagged-h2-cpu-header-v17-quiet/hdmi.rgb` | 0.494 |
| `projects/res-lab/validation/20261011-virtual-rate-live/tagged-120-quiet/hdmi.mkv` | 0.110 |
| `projects/res-lab/validation/20261011-virtual-rate-live/tagged-240-quiet/hdmi.mkv` | 0.109 |

## Local-only material

Installed dependencies, Git administration folders/files, operating-system metadata, Python bytecode, and generated caches were omitted. Original source, lockfiles, notes, development binaries, and validation data were retained where they fit.

No original local files were edited or removed. This is a dated development snapshot; inclusion does not imply that an experimental build passed camera validation.
