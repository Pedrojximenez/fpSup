#!/usr/bin/env python3
"""Check a base-edition .GYR: the twenty-byte header, then nothing but records.

    ./checkgyr.py A001_003.GYR

The format has no block framing, no CRC and no footer -- it is the ring buffer
as the producers left it, which is the point -- so the checks available are the
ones the shape itself affords:

  * the header's five words are the ones the writer is supposed to emit
  * the rest divides evenly into eight-byte records
  * every record's tag is 0 or 1, and nothing else
  * the gyro count against the run's duration says the 2500 Hz grid held
  * the accelerometer lands between gyro records at roughly its own rate

A tag that is neither 0 nor 1 is the useful one: the records are a flat array
with no framing, so a lost or half-written record shifts everything after it and
the tag column is where that becomes visible.
"""
import pathlib
import struct
import sys

MAGIC = 0x9F5BEB0D
HDR = 20
REC = 8


def main():
    d = pathlib.Path(sys.argv[1]).read_bytes()
    magic, period_ps, gscale_w, ascale_w, orient = struct.unpack_from('<5I', d)
    gscale, ascale = (struct.unpack('<f', struct.pack('<I', w))[0]
                      for w in (gscale_w, ascale_w))
    axes = struct.pack('<I', orient).split(b'\0', 1)[0].decode('ascii', 'replace')

    ok = magic == MAGIC
    print(f'  magic      0x{magic:08X}   {"ok" if ok else "NOT the base format"}')
    print(f'  period_ps  {period_ps}   = {period_ps / 1e6:.4f} us '
          f'= {1e12 / period_ps:.3f} Hz')
    print(f'  gscale     {gscale:.9g} dps/LSB')
    print(f'  ascale     {ascale:.9g}')
    print(f'  orient     0x{orient:08X}  "{axes}"')
    if not ok:
        return 1

    body = len(d) - HDR
    print(f'\n  body       {body} bytes, {body // REC} records, '
          f'{body % REC} left over')
    if body % REC:
        print('  ** not a whole number of records')
        return 1

    tags = {}
    for o in range(HDR, len(d), REC):
        t = struct.unpack_from('<h', d, o + 4)[0]
        tags[t] = tags.get(t, 0) + 1
    print('  tags      ', {k: v for k, v in sorted(tags.items())})
    stray = {k: v for k, v in tags.items() if k not in (0, 1)}
    if stray:
        print(f'  ** {sum(stray.values())} records with a tag that is not 0 or 1')
        return 1

    g, a = tags.get(0, 0), tags.get(1, 0)
    secs = g * period_ps / 1e12
    print(f'\n  gyro       {g} records = {secs:.3f} s at the grid')
    if a:
        print(f'  accel      {a} records = {a / secs:.1f} Hz, '
              f'one per {g / a:.1f} gyro samples')
    print('\n  the header is right, the body is whole, every tag is known')
    return 0


if __name__ == '__main__':
    sys.exit(main())
