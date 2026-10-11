# captures

`A001_083_FHD_f07_compressed_288x368.DNG` — 一幀 fp FHD CinemaDNG,由
`../mkcompressed.py` 壓成 `Compression=7`(288×368 tile,21 個),
LibRaw 解開後與原檔 `projects/open-gate/captures/opengate_ev_bug_20260914/dng/A001_083_FHD_f07.DNG`
逐樣本完全相同。3,244,544 → 1,250,148 bytes(2.595:1)。

可重現:
```sh
../mkcompressed.py <原檔> out.DNG 288 368
```
