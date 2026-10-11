#!/usr/bin/env python3
"""Faithful re-implementation of FUN_c0435588 (LiveView FieldAngle buffer sizing).

Column bases are transcribed from FUN_c0439d18, which is the authoritative
profile-row loader: canvas word i <- COL[i][row].
"""
import struct, sys
IMG = open('/Users/dido/Developer.localized/SIGMAfp_re/out/MAIN_c0000000.bin','rb').read()
B = 0xC0000000
def w32(a): return struct.unpack_from('<I', IMG, a-B)[0]
MAP = 0xC0BD05D4

COL = [0xc0be3adc,0xc0be3fa4,0xc0bdbe8c,0xc0bdc354,0xc0bdc81c,0xc0bd4bcc,0xc0bd63b4,
0xc0bd2a54,0xc0bdb4fc,0xc0be27bc,0xc0bdb9c4,0xc0be2c84,0xc0bd4704,0xc0bd720c,
0xc0be0644,0xc0be0b0c,0xc0bd8064,0xc0bd2f1c,0xc0bd33e4,0xc0bd555c,0xc0bd687c,
0xc0bd5a24,0xc0bd8ebc,0xc0be1e2c,0xc0bd984c,0xc0be149c,0xc0bde4cc,0xc0bde994,
0xc0bddb3c,0xc0bde004,0xc0bd38ac,0xc0be017c,0xc0bd1734,0xc0be0fd4,0xc0bdb034,
0xc0bdab6c,0xc0bd6d44,0xc0bd20c4,0xc0bdd674,0xc0bd3d74,0xc0bd5eec,0xc0bd423c,
0xc0bdf324,0xc0bdf7ec,0xc0bd7b9c,0xc0bd126c,0xc0bdee5c,0xc0bdfcb4,0xc0bd5094,
0xc0bd9384,0xc0be22f4,0xc0bd0da4,0xc0bd9d14,0xc0be1964,0xc0bda1dc,0xc0be314c,
0xc0bda6a4,0xc0be3614,0xc0bd76d4,0xc0bd258c,0xc0bd1bfc,0xc0bdcce4,0xc0bdd1ac,
0xc0bd852c,0xc0bd89f4]

def canvas(row):
    c = [w32(base + row*4) for base in COL] + [0x17b0, 0xfca]
    return c

def g(c, off):            # canvas byte offset -> value
    assert off % 4 == 0
    return c[off//4]
def gf(c, off):
    return struct.unpack('<f', struct.pack('<I', c[off//4] & 0xFFFFFFFF))[0]

def s32(v): return v-0x100000000 if v & 0x80000000 else v

# ---- the helpers, byte-for-byte from the decompilation ----------------------
def c04358d0(c):                                   # RAW-plane height
    h = s32(g(c,0x10))
    if g(c,0xe0) != 0: h = s32(g(c,0xe0))
    return h + s32(g(c,0x88)) + s32(g(c,0x8c))

def bpp_of(code):
    if code in (7, 0x10007): return 12
    if code in (9, 0x10009): return 10
    if code in (10, 0x1000a): return 8
    return 16

def c04356b0(c, which):                            # bytes of ONE plane
    if which == 0:
        wid, hgt, fmt, extra = s32(g(c,0x0c)), c04358d0(c), s32(g(c,0x80)), g(c,0xd8)
    else:
        wid, hgt, fmt, extra = s32(g(c,0x00)), s32(g(c,0x04)), s32(g(c,0x84)), g(c,0xdc)
    bpp = bpp_of(fmt)
    v = bpp * hgt * ((wid + 15)//16) * 16 + 0x1f
    v = (v >> 5) * 4
    return v + (0x28 if extra else 0x18)

EPS = 1e-6
def c04357e0(c):                                   # PLANE COUNT
    if s32(g(c,0xa4)) == 1: return 2
    a4 = s32(g(c,0xa4))
    if a4 in (9, 10) or abs(gf(c,0x30) - (-1.0)) < EPS: return 0
    return 3

def c0436300(c):  return gf(c,0x30) < 0.0

def c0435af8(c, which):
    if which == 0: wid, hgt = s32(g(c,0x0c)), c04358d0(c)
    else:          wid, hgt = s32(g(c,0x00)), s32(g(c,0x04))
    w4 = ((wid + 11)//12)*12
    f80 = s32(g(c,0x80))
    if (f80 == 10 or f80 == 0x1000a) and s32(g(c,0x60)) > 0x3ff:
        w4 += 12
    w4 = ((w4 + 15)//16)*16
    if g(c,0x44) == 0: return 0
    rem = w4 - (w4 & 0xffffffe0)
    m = s32(g(c,0x44)); half = rem >> 1
    if m == 1:
        v = (w4 >> 5)*0xb9
        v = v + (0x10 if 0 < rem < 4 else 0) if rem < 4 else (half-1)*0xb + v + 0x14
    elif m == 2:
        v = (w4 >> 5)*0xb1
        v = v + (0x10 if 0 < rem < 4 else 0) if rem < 4 else v + (rem>>2) + half*10 + 9
    elif m == 3:
        v = (w4 >> 5)*0xa1
        v = v + (0x10 if 0 < rem < 4 else 0) if rem < 4 else v + ((rem>>2)-1)*3 + 0x14 + (half-1)*8
    else:
        v = bpp_of(s32(g(c,0x80))) * w4
    return (hgt + 0x50) * ((v + 0x1f) >> 5) * 4

def c0435978(c, which, dimw):
    if g(c,0xb4) != 1: return 0
    if which == 0: wid, hgt = s32(g(c,0x0c)), c04358d0(c)
    else:          wid, hgt = s32(g(c,0x00)), s32(g(c,0x04))
    if wid < dimw:
        if g(c,0xf0) != 0 and s32(g(c,0xa4)) != 6:
            wid = min((wid*3)//2, dimw)
    elif dimw < wid//2: wid = wid//2
    else:               wid = dimw
    u = (wid + 1) & 0xfffffffe
    f0 = g(c,0xf0)
    if f0 in (2,4): v = ((hgt + 7) & ~7) * ((u + 15) & ~15)
    else:           v = hgt * u * 2
    v = (v*8) >> 3
    return v + (8 if f0 in (2,4) else 4)

def c0435d78(c):
    a,bq = s32(g(c,0x70)), s32(g(c,0x74)); e,d = s32(g(c,0x68)), s32(g(c,0x6c))
    if e == 0 or d == 0:
        return bq*a*2 if (a and bq) else 0
    return d*e*2

def c0435df8(c, dw, dh):
    a4 = s32(g(c,0xa4))
    return dw*dh*2 if (a4-0x18) in (0,1,0x11) or a4 == 0x1a else 0

def c0435e38(c):
    u = g(c,0xa4) & 0xffffffff
    if u < 0x18: return 0
    if u != 0x18:
        if u-0x18 < 2: return 2
        if u == 0x1a: return 3
        if u-0x18 != 0x11: return 0
    return 8 if g(c,0xb0) == 1 else 6

def c0435ea8(c, dw, dh):
    v = 0x1e000 if g(c,0x7c) != 0 else 0
    if g(c,0x7c) in (2,3):
        v += ((dw + 7) & ~7) * dh * 2 + 0x40
        a, b = dw, dh
        for _ in range(15):
            a = (((a+7) >> 3) << 6)//10 + 1 & 0xfffffffe
            b = ((b << 3)//10) + 1 & 0xfffffffe
            v += b * ((a + 7) & ~7) + 0x20
    return v

# ---- FUN_c0435428 + FUN_c0435588 -------------------------------------------
def total(c, dw, dh, verbose=False):
    o = {}
    o[4]    = c04357e0(c)            # +0x10  plane count
    o[5]    = c04356b0(c, 0)         # +0x14  preview-plane bytes
    o[8]    = 1;  o[9]  = c0435af8(c, 0)
    o[0xc]  = 4;  o[0xd] = c0435d78(c)
    o[0xe]  = c0435e38(c); o[0xf] = c0435df8(c, dw, dh)
    o[0x10] = 1;  o[0x11] = c0435ea8(c, dw, dh)
    o[0x12] = 2;  o[0x13] = c0435978(c, 0, dw)
    if g(c,0x3c) == 0:
        o[6]=o[7]=o[10]=o[11]=0
    else:
        o[6] = c04357e0(c); o[7] = c04356b0(c, 1)
        o[10] = 1; o[11] = c0435af8(c, 1)

    t1 = 0 if c0436300(c) else o[5]*o[4]
    parts = [("RAW/preview plane x count", t1),
             ("0x4C x2", o[0x13]*o[0x12]),
             ("0x3C x 0x38", o[0xf]*o[0xe]),
             ("0x34 x4", o[0xd]*o[0xc]),
             ("0x24 x1", o[9]*o[8])]
    v = sum(p[1] for p in parts)
    dbl = g(c,0xcc) == 1
    if dbl: v *= 2
    tail = [("0x44 x1", o[0x11]*o[0x10]), ("0x2C x1", o[0xb]*o[10]),
            ("RAW plane(1) x count", o[7]*o[6])]
    v += sum(p[1] for p in tail)
    if verbose:
        for n,x in parts: print(f"      {n:<28} {x:>12,}")
        if dbl: print(f"      {'(x2 because +0xCC==1)':<28}")
        for n,x in tail: print(f"      {n:<28} {x:>12,}")
    return v
