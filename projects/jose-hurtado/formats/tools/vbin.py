"""Read Jose's fpSup.BIN (VBIN): header, {dest,len} table, word-aligned data.

Which package: FMT_VERSION (environment), default the newest one converted.
The originals are projects/jose-hurtado/formats-v<VERSION>/original/."""
import os, struct, pathlib

VERSIONS = ('0.6.0', '0.6.1')
VERSION = os.environ.get('FMT_VERSION', VERSIONS[-1])
if VERSION not in VERSIONS:
    raise SystemExit(f'FMT_VERSION={VERSION}: one of {", ".join(VERSIONS)}')
PKG = pathlib.Path(__file__).resolve().parents[2] / f'formats-v{VERSION}'
ORIG = PKG / 'original'
FORMATS = {n: f'fpsup-fmt-{n}-v{VERSION}' for n in ('s16', 'og35k', 'og4k')}


def parse(data):
    magic, count, entry, nbytes = struct.unpack_from('<4sIII', data, 0)
    assert magic == b'VBIN'
    tbl = [struct.unpack_from('<II', data, 16 + 8 * i) for i in range(count)]
    off = 16 + 8 * count
    secs = []
    for dest, n in tbl:
        off = (off + 3) & ~3
        secs.append((dest, data[off:off + n]))
        off += n
    return entry, secs, off


def load(name):
    return parse((ORIG / FORMATS[name] / 'fpSup.BIN').read_bytes())
