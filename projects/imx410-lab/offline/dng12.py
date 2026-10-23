"""Minimal CinemaDNG (IFD0, 12-bit packed MSB-first) reader -> (array, tags)."""
import struct
import numpy as np


def read(path):
    b = open(path, 'rb').read()
    bo = '<' if b[:2] == b'II' else '>'
    off = struct.unpack(bo + 'I', b[4:8])[0]
    n = struct.unpack(bo + 'H', b[off:off + 2])[0]
    t = {}
    for i in range(n):
        tag, typ, cnt, val = struct.unpack(bo + 'HHI4s', b[off + 2 + 12 * i:off + 14 + 12 * i])
        if typ in (3, 4) and cnt == 1:
            t[tag] = struct.unpack(bo + ('H' if typ == 3 else 'I'), val[:2 if typ == 3 else 4])[0]
    w, h, bits, so = t[256], t[257], t[258], t[273]
    raw = np.frombuffer(b, np.uint8, offset=so, count=w * h * bits // 8)
    x = raw.reshape(-1, 3).astype(np.uint16)
    a = np.empty(x.shape[0] * 2, np.uint16)
    a[0::2] = (x[:, 0] << 4) | (x[:, 1] >> 4); a[1::2] = ((x[:, 1] & 15) << 8) | x[:, 2]
    return a.reshape(h, w).astype(np.float32), t
