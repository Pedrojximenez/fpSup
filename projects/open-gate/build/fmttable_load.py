#!/usr/bin/env python3
"""把格式表寫進 cave。profile 抄原廠表3 同幀率的 FHD,時序抄原廠同幀率的模式。"""
import struct, sys
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import mem_get, mem_set

IMG = open('/Users/dido/Developer.localized/SIGMAfp_re/out/MAIN_c0000000.bin','rb').read()
B = 0xC0000000
TT, T3 = 0xC0B59500, 0xC0BE5B50
TABLE, REC = 0xC0731000, 48
order = [struct.unpack_from('<I', IMG, TT-B+i*0x20)[0] for i in range(70)]
idx = {m: i for i, m in enumerate(order)}

def img(a): return struct.unpack_from('<I', IMG, a-B)[0]
def timing_of(mode):
    o = TT - B + idx[mode]*0x20
    return struct.unpack_from('<HHHH', IMG, o+4)          # hmax, tail, vmax, x
def profile_of(slot):
    return img(T3 + slot*0x10 + 4)

#  key          donor  幀率時序抄自   picker 表3 的 slot
FMT = [("OG3K23_98",  98, 109, 10),
       ("OG3K24",     98, 218,  9),
       ("OG3K25",     98, 125,  8),
       ("OG3K30",     98, 106,  7),
       ("OG3K48",     98, 220,  6),
       ("OG3K50",     98, 115,  5),
       ("OG3K60",     98,  27,  4),
       ("OG3K100",   117,  89, 12)]

def rd(a, t=8):
    for _ in range(t):
        w = mem_get(a)
        if w and w[0] is not None: return w[0]
    raise SystemExit(f"read failed 0x{a:08X}")
def wr(a, v, t=12):
    for _ in range(t):
        if rd(a) == v: return True
        mem_set(a, v)
    return rd(a) == v

print(f"{'key':<12}{'donor':>6}{'hmax':>6}{'tail':>6}{'vmax':>7}{'fps':>10}{'捲簾ms':>9}{'profile':>9}")
words = []
for n, (key, donor, src, slot) in enumerate(FMT):
    hm, tl, vm, x = timing_of(src)
    if key == "OG3K100":
        hm, tl, vm, x = 330, 270, 2182, timing_of(117)[3]     # 精確 100.000
    cyc = hm*(vm-1) + tl
    prof = profile_of(slot)
    base = TABLE + n*REC
    kb = key.encode() + b'\x00'*(16-len(key))
    rec = [5, prof, donor, base+0x14, TT + idx[donor]*0x20] \
        + list(struct.unpack('<4I', kb)) + [hm | (tl << 16), vm | (x << 16), 0]
    words.append((base, rec))
    print(f"{key:<12}{donor:>6}{hm:>6}{tl:>6}{vm:>7}{72e6/cyc:>10.4f}{hm*2012/72e6*1000:>9.3f}{prof:>9}")
    assert hm*2012 < cyc, f"{key} 讀出塞不進一格"

print(f"\n寫入 {len(words)} 筆 × {REC} bytes = {len(words)*REC} bytes @ 0x{TABLE:08X}")
bad = 0
for base, rec in words:
    for i, v in enumerate(rec):
        if not wr(base + i*4, v): bad += 1
for i in range(12):                                  # 表尾
    wr(TABLE + len(words)*REC + i*4, 0)
print(f"  {len(words)*12-bad}/{len(words)*12} 字正確" + ("  ✓" if not bad else "  ✗"))
wr(0xC0730700, 0)
print("  命中計數歸零")
