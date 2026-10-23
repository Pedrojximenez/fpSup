"""BUFA 12-bit packing (firmware getter FUN_c031e6b0): an MSB-first bit stream
inside little-endian 32-bit words, 8 pixels per 3 words.  decode12(raw, rows, words_per_row)."""
import numpy as np


def decode12(raw, rows, wpr):
    w = np.frombuffer(raw, dtype='<u4')[:rows * wpr].reshape(rows, wpr)
    b = w.byteswap().view(np.uint8).reshape(rows, wpr * 4).astype(np.uint16)   # big-endian byte stream
    b = b[:, :(wpr * 4 // 3) * 3].reshape(rows, -1, 3)
    p0 = (b[..., 0] << 4) | (b[..., 1] >> 4)
    p1 = ((b[..., 1] & 0xF) << 8) | b[..., 2]
    img = np.empty((rows, p0.shape[1] * 2), np.uint16)
    img[:, 0::2], img[:, 1::2] = p0, p1
    return img
