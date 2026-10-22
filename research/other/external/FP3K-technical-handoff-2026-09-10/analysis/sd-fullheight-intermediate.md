# Full-height SD-sized intermediate assessment

The user accepts a smaller full-sensor-area image as an intermediate milestone.
This relaxes output resolution; it does not establish permission to describe
unknown sensor sampling as all-pixel processing.

## Recording bandwidth

[Sigma's official media list](https://www.sigma-global.com/en/cameras/download/fp_recommend_list_en.pdf)
supports stock FHD12-bit CinemaDNG through59.94fps on UHS-II SD, and UHD8-bit
through25fps. These are supported combinations, not measured maxima for this
camera/card and not automatic support for arbitrary dimensions. Recording uses
SD **write** bandwidth. The exact maximum custom-mode throughput is unknown.

Executed stock descriptor constructor C0438018, path selector C0325228 and
byte-count callback C03D9630 for the following cases, with firmware read/execute,
bounded execution, guarded writes and no function stubs. See
`firmware/sd-intermediate-emulation.json`; reproduce using
`tools/verify_sd_intermediate_emulated.py` (Unicorn JIT needs sandbox exemption).

| Visible candidate | RAW raster | Required ratio | RAW MB/s24 | RAW MB/s30 |
|---|---|---:|---:|---:|
| Stock1920×1080 |1936×1090|1600 with3032×1708 input|75.969|94.961|
|1920×1280|1936×1290|3200 with6064×4042 input|89.908|112.385|
|1728×1152|1744×1162|3550 with6064×4042 input|72.955|91.194|

Rates exclude DNG metadata, file alignment, filesystem traffic and audio. These
are computed demands, not measured card performance. Both candidates have3:2
visible crops. Tiny border cropping remains; full sensor coverage and exact
field of view must ultimately be measured from camera images.

The1920×1280 case was tested from two bases. UHD profile429 retains the stock
preview descriptor2016×1135 with factors3/3, and path enable bytes[0,0,1].
FHD profile431 keeps preview1936×1090 but raises both preview ratios to3200;
path enable bytes stay[0,1,0], as in stock FHD. In both cases the RAW descriptor
is1936×1290, format0, ratios3200/3200, integer reduction factors1/1, and its size
callback returns3,746,172 bytes. The assumed full-resolution sensor raster
reduces arithmetically to1940×1293, large enough for that RAW rectangle.

## Why this is not yet a simpler camera patch

The65-column stock processing tables contain RAW ratios only1023,1500,1600.
Preview ratios extend to3072. Thus3200/3550 are new RAW scaling configurations;
passing the software selector does not validate the hardware filter or its
range. Even the original3K candidate's2048 RAW ratio remains unverified in
hardware, but it requires less reduction.

Keeping the UHD route could also retain UHD media eligibility checks despite
smaller output dimensions. Their dependence on route versus actual geometry
has not been traced. Using the FHD route avoids assuming that an unchanged UHD
menu path supports12-bit SD, but introduces a change from its reduced3032-wide
sensor input to the full6064-wide input. Neither is a free dimension substitution.

Decision: retain1920×1280 as an SD-sized fallback and1728×1152 as a roughly
stock-FHD-bandwidth alternative. Continue common sensor/RAW-buffer work; do not
switch the project to an unproven reduced-readout mode solely for convenience.

## Sensor setup progress

New test `tools/verify_sensor_table_sequence_emulated.py` executes the complete
table routine C03258C8 for modes3,121,151,98,106,218,11,8 and two initial toggle
states. It verifies all165 register requests in each of16 cases. Sensor I/O
C0322C70 and functions C0125030/C0125058 are explicitly mocked; this does not
test hardware or elapsed timing.

After161 table writes, C0326D18 writes CE=0. It then writes D1–D3 from a software
word at C2F1E7B0: set0x2FFFA unless already0x2FFFA, in which case set0x2FFFB.
This tail does not add a mode-dependent timing difference. The optional override
path in C03234A0 uses sensor-object+58 enable, +5C mode and ten address/value
slots at+60/+88. The existing UHD capture has enable0 in all120 snapshots,
including all19 recording snapshots. This excludes overrides at sampled times,
not at every instruction of the transition.

Table comparisons remain favorable for full-resolution readout: modes151 and3
or121 have identical161-register tables. Reduced FHD218 versus full-height
reduced98 differs only at register0x16 (35 versus20), but mode98 also has different
timing. Modes11 and8 differ from218 at78 and99 registers respectively; selecting
an existing idle/high-speed mode is not an obviously simpler substitute.

This resolves the previously uncertain CE/D1–D3 tail. Other timing, exposure,
receiver setup, DMA allocation, metadata propagation and image quality remain
unverified. No installable AutoRun or modified flash firmware was produced.
