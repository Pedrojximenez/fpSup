# SPDX-License-Identifier: GPL-3.0-or-later
#!/usr/bin/env python3
"""Bit-exact Python model of the RAW-View v0.3.0 display-LUT builder
(file 0x508..0x6b0): phase 1 builds log2(fp) Q16 for fp=1..2047 minus the
reference word at data+0x404; phase 2 builds, per record, a 2048-entry u16 LUT
from (gain, bias, row, linA, linB, thr). Used to (a) check the model against
the explainer's per-ISO columns and (b) verify patched BINs. Read-only."""
import struct
DATA_BASE, REC_BASE, ROWS_BASE, STRIDE = 0x2aac, 0x2eb4, 0x3ad0, 0x124

def s32(x): x &= 0xffffffff; return x - (1 << 32) if x & 0x80000000 else x

def build_lut(d):
    tab = struct.unpack_from('<257I', d, DATA_BASE)
    sb = struct.unpack_from('<i', d, DATA_BASE + 0x404)[0]
    lut = [-0x200000] + [0] * 0x7ff
    for fp in range(1, 0x800):
        clz = 32 - fp.bit_length()
        r3 = (fp << (clz - 11)) - 0x100000          # 20-bit mantissa
        i8 = r3 >> 12
        frac = tab[i8] + (((tab[i8 + 1] - tab[i8]) * (r3 & 0xfff)) >> 12)
        lut[fp] = s32(frac + ((31 - clz) << 16) - sb)
    return lut, sb

def record(d, i):
    return struct.unpack_from('<IiiiIi', d, REC_BASE + i * 0x18)

def build_record_lut(d, i, lut=None, maxv=None):
    if lut is None: lut, _ = build_lut(d)
    if maxv is None: maxv = struct.unpack_from('<I', d, REC_BASE + 0xba0)[0]
    gain, bias, row, linA, linB, thr = record(d, i)
    rowv = struct.unpack_from('<146H', d, ROWS_BASE + row * STRIDE) if row >= 0 else None
    out = []
    for fp in range(0x800):
        r0 = s32(((lut[fp] * gain) >> 16) & 0xffffffff) + bias
        r0 = s32(r0)
        if r0 < 0:
            out.append(0); continue
        r1 = -0x80000000
        if rowv is not None:
            r2 = r0 * 10
            ip = (r2 >> 16) & 0xffffffff
            fr = r2 & 0xffff
            if ip >= 0x91: ip, fr = 0x91, 0
            a, b = rowv[ip], rowv[ip + 1] if ip + 1 < 146 else rowv[ip]
            r1 = a + (((b - a) * fr) >> 16)
        if r0 < thr:
            ip = s32((linA * r0) >> 24) + s32(linB)
            if ip > r1: r1 = ip
        r1 = max(0, min(r1, maxv))
        out.append(r1)
    return out

def stops_to_fp(s, W, sb):
    # fp = white * 2^(s - W); white = 2^(sb/65536)
    import math
    return 2 ** (sb / 65536 + s - W)
