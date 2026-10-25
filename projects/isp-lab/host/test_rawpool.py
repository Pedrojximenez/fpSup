#!/usr/bin/env python3
"""Offline tests for rawpool.py.  python3 -B -m unittest test_rawpool"""
import struct, unittest

import rawpool as R


def dng(w=64, h=32, payload=b'', tiles=None):
    """A minimal little-endian DNG: header, IFD0 with width/length/strips."""
    body = payload or bytes(range(256)) * (w * h * 2 // 256 + 1)
    body = body[:w * h * 2]
    tags = [(256, 4, 1, w), (257, 4, 1, h), (258, 3, 1, 16)]
    ifd_at = 8
    n = len(tags) + 2
    data_at = ifd_at + 2 + 12 * n + 4
    if tiles:
        offs, cnts = [], []
        pos = data_at + 8 * len(tiles)            # two arrays of u32 before the data
        for t in tiles:
            offs.append(pos); cnts.append(t); pos += t
        arr_o, arr_c = data_at, data_at + 4 * len(tiles)
        tags += [(324, 4, len(tiles), arr_o), (325, 4, len(tiles), arr_c)]
        extra = struct.pack(f'<{len(tiles)}I', *offs) + struct.pack(f'<{len(tiles)}I', *cnts)
        body = bytes(sum(tiles))
    else:
        tags += [(273, 4, 1, data_at), (279, 4, 1, len(body))]
        extra = b''
    b = b'II*\0' + struct.pack('<I', ifd_at) + struct.pack('<H', n)
    for t in sorted(tags):
        b += struct.pack('<HHII', *t)
    return b + b'\0\0\0\0' + extra + body


class Parse(unittest.TestCase):
    def test_size_is_the_end_of_the_strip(self):
        d = dng()
        self.assertEqual(R.dng_size(d), len(d))

    def test_tiles(self):
        d = dng(tiles=[100, 200, 50])
        self.assertEqual(R.dng_size(d), len(d))

    def test_not_a_dng(self):
        for b in (b'MM\0*' + bytes(100), b'II*\0' + struct.pack('<I', 3) + bytes(64), bytes(64)):
            self.assertIsNone(R.dng_size(b))

    def test_missing_dimensions(self):
        d = bytearray(dng())
        d[10:12] = struct.pack('<H', 255)           # tag 256 -> 255
        self.assertIsNone(R.dng_size(bytes(d)))


class Scan(unittest.TestCase):
    def test_finds_aligned_dngs_only(self):
        a, b = dng(payload=b'\x11' * 4096), dng(w=32, payload=b'\x22' * 4096)
        mem = bytearray(0x10000)
        mem[0x2040:0x2040 + len(a)] = a              # allocation + 0x2000, aligned
        mem[0x8000:0x8000 + len(b)] = b
        mem[0xC004:0xC004 + len(a)] = a              # not 0x40-aligned: not a buffer start
        self.assertEqual(R.find_dngs(bytes(mem), base=0x50000000), [(0x2040, len(a)), (0x8000, len(b))])

    def test_chain_walk_stops_on_bad_magic(self):
        mem = {0x100: [R.BLOCK_MAGIC, 0x1000, 0, 0x1100], 0x1100: [R.BLOCK_MAGIC, 0x2000, 0, 0x3100],
               0x3100: [0x12345678, 0, 0, 0]}
        ch = R.walk_chain(lambda a, n: mem[a], 0x100)
        self.assertEqual([c['at'] for c in ch], [0x100, 0x1100, 0x3100])
        self.assertEqual(ch[-1]['bad_magic'], 0x12345678)
        self.assertEqual(R.arena({'chain': ch}), (0x100, 0x3100))


if __name__ == '__main__':
    unittest.main()
