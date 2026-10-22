#!/usr/bin/env python3
"""把 fp 的未壓縮 12-bit CinemaDNG 影格解成可看的 PNG。

沒有外部相依:自己拆 IFD、解 12-bit packed、2x2 拜耳合成 RGB。
mode 12 是 3x6 非對稱縮減,所以最後把高度拉伸 2x 還原正確比例。
"""
import struct, sys, zlib

path, out = sys.argv[1], sys.argv[2]
d = open(path, 'rb').read()
bo = '<' if d[:2] == b'II' else '>'
ifd = struct.unpack_from(bo + 'I', d, 4)[0]
tags = {}
n = struct.unpack_from(bo + 'H', d, ifd)[0]
for i in range(n):
    e = ifd + 2 + i * 12
    tag, typ, cnt = struct.unpack_from(bo + 'HHI', d, e)
    size = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 11: 4, 12: 8}.get(typ, 1) * cnt
    vo = e + 8 if size <= 4 else struct.unpack_from(bo + 'I', d, e + 8)[0]
    if typ == 3:
        tags[tag] = [struct.unpack_from(bo + 'H', d, vo + j * 2)[0] for j in range(cnt)]
    elif typ == 4:
        tags[tag] = [struct.unpack_from(bo + 'I', d, vo + j * 4)[0] for j in range(cnt)]
    elif typ == 1:
        tags[tag] = list(d[vo:vo + cnt])

W, H = tags[256][0], tags[257][0]
off, cnt = tags[273][0], tags[279][0]
cfa = tags.get(33422, [0, 1, 1, 2])          # CFAPattern,預設 RGGB
print(f"{W}x{H} 12-bit  strip @{off} {cnt}B  CFA={cfa}")

raw = d[off:off + cnt]
BITS = tags.get(258, [12])
BITS = BITS[0] if isinstance(BITS, list) else BITS
MAXV = (1 << BITS) - 1
row_bytes = cnt // H
print(f"  {BITS}-bit,列距 {row_bytes} bytes")

def unpack_row(y):
    """一列 W 個樣本。12-bit 是兩個像素三個位元組;8-bit 直接一個位元組。"""
    b = raw[y * row_bytes:(y + 1) * row_bytes]
    if BITS == 8:
        return list(b[:W])
    px = []
    for i in range(0, len(b) - 2, 3):
        b0, b1, b2 = b[i], b[i + 1], b[i + 2]
        px.append(b0 | ((b1 & 0x0F) << 8))
        px.append((b1 >> 4) | (b2 << 4))
    return px

# 2x2 合成:每個拜耳方塊給一個 RGB 像素。輸出 W/2 x H/2,再垂直拉 2x。
ow, oh = W // 2, H // 2
rows = []
for by in range(oh):
    r0 = unpack_row(by * 2)
    r1 = unpack_row(by * 2 + 1)
    rows.append((r0, r1))

# 白平衡:AsShotNeutral(50728)是 R/G/B 的中性值,倒數就是增益。
asn = tags.get(50728)
if asn and len(asn) >= 6:
    # RATIONAL:上面只解了 SHORT/LONG,這裡直接從檔案再讀一次
    for i in range(n):
        e = ifd + 2 + i * 12
        tg, typ, cn = struct.unpack_from(bo + 'HHI', d, e)
        if tg == 50728:
            vo = struct.unpack_from(bo + 'I', d, e + 8)[0]
            asn = [struct.unpack_from(bo + 'II', d, vo + j * 8) for j in range(cn)]
            asn = [a / b for a, b in asn]
            break
gains = [1.0 / v if v else 1.0 for v in (asn or [1, 1, 1])][:3] or [1, 1, 1]
g0 = max(gains)
gains = [g / g0 for g in gains]

# 曝光:用 99.5 百分位當白點,而不是中位數 —— 中位數會把亮場沖爆。
samples = sorted(v for r0, r1 in rows[::4] for v in r0[::4])
white = samples[int(len(samples) * 0.995)] or 4095
print(f"AsShotNeutral -> 增益 {[round(x,3) for x in gains]}   白點 {white}/4095")

px = bytearray()
for r0, r1 in rows:
    line = bytearray()
    for bx in range(ow):
        x = bx * 2
        R, G1, G2, B = r0[x], r0[x + 1], r1[x], r1[x + 1]
        g = (G1 + G2) / 2
        for v, k in ((R, gains[0]), (g, gains[1]), (B, gains[2])):
            u = (v / white) * k
            u = min(1.0, max(0.0, u)) ** (1 / 2.2)
            line.append(max(0, min(255, int(u * 255))))
    px += b'\x00' + bytes(line)
    px += b'\x00' + bytes(line)          # 垂直 2x 還原比例

def png(w, h, data):
    def chunk(t, b):
        c = t + b
        return struct.pack('>I', len(b)) + c + struct.pack('>I', zlib.crc32(c))
    hdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', hdr)
            + chunk(b'IDAT', zlib.compress(bytes(data), 6)) + chunk(b'IEND', b''))

open(out, 'wb').write(png(ow, oh * 2, px))
print(f"寫出 {out}  {ow}x{oh*2}(已還原 2x 垂直拉伸)")
