"""Diagnostic preview only; exact v39 artifact and eight existing pair values.

Derived with the existing visible-region/margin formula and an isotropic 2x
preview. This is a hypothesis to test, not a validated bandwidth limit or fix.
RAW raster/crop, recording zoom/bin, bit depth, sensor window/timing stay intact.
"""
EXPECTED_SHA = '650c6fa0f27d216adba551cbec777741d42b39f4374e8b76db0f71dfbfe1cb85'
CHANGES = {
    0x0c: (2000, 992), 0x10: (672, 336),
    0x20: (1984, 976), 0x28: (662, 326),
    0x60: (1023, 2048), 0xd0: (1023, 2048),
    0xd8: (2000, 992), 0xe0: (672, 336),
}
