"""Decode a few real .xci icons from the firmware image (LZ4 frames) for use as
realistic pixel data in the tests.  Pure Python; no camera."""
import pathlib, struct

ROOT = pathlib.Path(__file__).resolve().parents[3]
B = 0xC0000000


def lz4_block(src):
    o = bytearray(); i = 0
    while i < len(src):
        t = src[i]; i += 1; L = t >> 4
        if L == 15:
            while True:
                b = src[i]; i += 1; L += b
                if b != 255: break
        o += src[i:i + L]; i += L
        if i >= len(src): break
        off = src[i] | src[i + 1] << 8; i += 2; M = t & 15
        if M == 15:
            while True:
                b = src[i]; i += 1; M += b
                if b != 255: break
        M += 4
        for _ in range(M): o.append(o[-off])
    return bytes(o)


def decode(rom, i):
    w, h = struct.unpack_from('<HH', rom, i + 8)
    p = i + 0x20
    if struct.unpack_from('<I', rom, p)[0] != 0x184D2204:
        return None
    flg = rom[p + 4]; q = p + 6 + (8 if flg & 8 else 0) + 1
    out = bytearray()
    while True:
        bs = struct.unpack_from('<I', rom, q)[0]
        if bs == 0: break
        if bs & 0x80000000:
            n = bs & 0x7FFFFFFF; out += rom[q + 4:q + 4 + n]; q += 4 + n
        else:
            out += lz4_block(rom[q + 4:q + 4 + bs]); q += 4 + bs
        if flg & 0x10: q += 4
    return w, h, bytes(out)


def sample_icons(n=12):
    rom = (ROOT / 'out' / 'seg0_c0000000.bin').read_bytes()
    icons = []
    i = rom.find(b'XC\x00\x00', 0x1240000)
    step = 0
    while 0 <= i < 0x1600000 and len(icons) < n:
        w, h = struct.unpack_from('<HH', rom, i + 8)
        if 8 <= w <= 400 and 8 <= h <= 400 and step % 97 == 0:
            d = decode(rom, i)
            if d and len(d[2]) >= 2 * d[0] * d[1] // 2:
                icons.append(d[2])
        step += 1
        i = rom.find(b'XC\x00\x00', i + 4)
    return icons


if __name__ == '__main__':
    ic = sample_icons(12)
    print(len(ic), [len(x) for x in ic])
