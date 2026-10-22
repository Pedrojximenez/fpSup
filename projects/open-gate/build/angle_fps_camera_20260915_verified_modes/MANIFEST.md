# Verified FHD / OG3K idle-live-view evidence — 2026-09-15

This directory contains the first pair from this session whose active
resolution was independently confirmed by the camera's second QS draw and its
loaded native UI assets. No recording was started; both observations were made
while idle in live view.

| Active mode | Native QS evidence | Camera screenshot | Local file | Imager state | Displayed EV |
| --- | --- | --- | --- | --- | --- |
| FHD (`SetMovRecSize = 2`) | `font_menu_MB_resolution_2.xci`, `qs_resolution_2_S.xci` | `SS__0485.JPG` | `fhd_qs2_iso800_2997_angle180_idle.jpg` | shutter `16663 us`, gain `936` | `+2.3 EV` |
| OG3K (`SetMovRecSize = 4`) | `OG3K_FONT.xci`, `OG3K_QS.xci` | `SS__0486.JPG` | `og3k_qs4_iso800_2997_angle180_idle.jpg` | shutter `6411 us`, gain `936` | `+1.0 EV` |

Shared test settings visible in both frames were ISO800, 29.97 fps, 180°,
F2.0, 5500 K, and `STBY`. The identical gain value isolates the observed
change to shutter timing rather than an HCG/LCG transition.

At unchanged settings, OG3K used `6411 / 16663` of the FHD exposure time:

```text
log2(6411 / 16663) = -1.378 EV
16663 / 6411 = 2.599x
```

This reproduces the reported approximately `-1.3` to `-2 EV` OG3K
shutter-angle defect and rejects the earlier apparent pass. It is a failure
result for the installed single-callsite candidate, not acceptance evidence for
the revised four-callsite/cache-synchronized candidate.

The three images in `../angle_fps_camera_20260915/` are explicitly invalid:
the requested resolution transition did not occur there.
