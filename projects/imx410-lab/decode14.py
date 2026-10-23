"""BUFA 14-bit packing (firmware getter FUN_c031e800, chosen by FUN_c031e370 for bit enum 1): the same MSB-first
bit stream inside little-endian 32-bit words as the 12-bit format (decode12.py), 16 pixels per 7 words
(4 px per 7 bytes of the big-endian byte stream).  Line length set by FUN_c06306e0: 0x30182114 = width*7 >> 4 words.
decode14(raw, rows, words_per_row).   Self-test against a literal port of the getter: python3 decode14.py"""
import numpy as np


def decode14(raw, rows, wpr):
    w = np.frombuffer(raw, dtype='<u4')[:rows * wpr].reshape(rows, wpr)
    b = w.byteswap().view(np.uint8).reshape(rows, wpr * 4).astype(np.uint32)   # big-endian byte stream
    n = (wpr * 4 // 7) * 7
    b = b[:, :n].reshape(rows, -1, 7)
    p0 = (b[..., 0] << 6) | (b[..., 1] >> 2)
    p1 = ((b[..., 1] & 0x3) << 12) | (b[..., 2] << 4) | (b[..., 3] >> 4)
    p2 = ((b[..., 3] & 0xF) << 10) | (b[..., 4] << 2) | (b[..., 5] >> 6)
    p3 = ((b[..., 5] & 0x3F) << 8) | b[..., 6]
    img = np.empty((rows, p0.shape[1] * 4), np.uint16)
    img[:, 0::4], img[:, 1::4], img[:, 2::4], img[:, 3::4] = p0, p1, p2, p3
    return img


def _getter(words, x, y, width):
    """Literal port of FUN_c031e800(_, x, y, base, &width, &out) (blk_c03.c:21180)."""
    i = ((y * width * 7) & 0xFFFFFFFF) >> 4
    i += (x >> 4) * 7
    W = lambda k: int(words[i + k])
    c = x & 0xF
    return [W(0) >> 18, W(0) >> 4 & 0x3FFF, (W(0) & 0xF) << 10 | W(1) >> 22, W(1) >> 8 & 0x3FFF,
            (W(1) & 0xFF) << 6 | W(2) >> 26, W(2) >> 12 & 0x3FFF, (W(2) & 0xFFF) << 2 | W(3) >> 30,
            W(3) >> 16 & 0x3FFF, W(3) >> 2 & 0x3FFF, (W(3) & 3) << 12 | W(4) >> 20, W(4) >> 6 & 0x3FFF,
            (W(4) & 0x3F) << 8 | W(5) >> 24, W(5) >> 10 & 0x3FFF, (W(5) & 0x3FF) << 4 | W(6) >> 28,
            W(6) >> 14 & 0x3FFF, W(6) & 0x3FFF][c]


if __name__ == '__main__':
    rng = np.random.default_rng(1)
    width, rows = 64, 3                         # width multiple of 16 so the getter's row offset is exact
    wpr = width * 7 >> 4
    raw = rng.integers(0, 2**32, rows * wpr, dtype=np.uint32).astype('<u4').tobytes()
    words = np.frombuffer(raw, '<u4')
    img = decode14(raw, rows, wpr)
    ref = np.array([[_getter(words, x, y, width) for x in range(width)] for y in range(rows)])
    assert img.shape == ref.shape and (img == ref).all(), 'decode14 != FUN_c031e800'
    print('decode14 matches FUN_c031e800 on', img.size, 'pixels')
