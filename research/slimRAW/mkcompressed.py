#!/usr/bin/env python3
"""把一幀未壓縮的 fp CinemaDNG 壓成 Compression=7 —— 照機身端要走的做法。

保留原本 78,848 byte 的表頭原封不動,在它的零區裡「重建」一份 IFD
(Compression 1->7、三個 strip 標籤換成四個 tile 標籤),再改寫檔頭 offset 4
指向新 IFD。既有標籤的 out-of-line 值全部原地不動,所以只寫進 padding、
不移動任何東西 —— 這正是 hook 在 FUN_c069ac88 能做的事。

用法: ./mkcompressed.py <in.DNG> <out.DNG> [tileW tileH] [--predictor 1..7]
      [--file-align 512]
"""
import sys, os, struct, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tiff import parse, TYPESZ
from tilegeom import pad_image
from ljenc import encode_tile

DROP = {273, 278, 279}                    # StripOffsets / RowsPerStrip / StripByteCounts

def largest_zero_run(d, lo, hi, occupied=()):
    blocked = bytearray(hi - lo)
    for a, b in occupied:
        a = max(a, lo); b = min(b, hi)
        if a < b:
            blocked[a-lo:b-lo] = b'\x01' * (b-a)
    best = (0, 0); s = None
    for i in range(lo, hi):
        if d[i] == 0 and not blocked[i-lo]:
            if s is None: s = i
        else:
            if s is not None and i - s > best[0]: best = (i - s, s)
            s = None
    if s is not None and hi - s > best[0]: best = (hi - s, s)
    return best[1], best[0]

def build(src, dst, tw, th, predictor=1, file_align=1):
    if file_align < 1 or file_align & (file_align - 1):
        raise ValueError("file-align 必須是正的 2 次方")
    d, e, end, ifds = parse(src)
    assert e == '<', "目前只支援 fp 的 little-endian DNG"
    t = ifds[0]
    W = t[256][2][0]; H = t[257][2][0]; bps = t[258][2][0]
    off = t[273][2][0]; n = t[279][2][0]
    assert t[259][2][0] == 1 and bps == 12, "來源必須是未壓縮 12-bit"

    b = np.frombuffer(d, np.uint8, count=W*H*3//2, offset=off).reshape(-1, 3).astype(np.uint16)
    px = np.empty(W*H, np.uint16)
    px[0::2] = (b[:, 0] << 4) | (b[:, 1] >> 4)
    px[1::2] = ((b[:, 1] & 0xF) << 8) | b[:, 2]
    img = px.reshape(H, W)

    pad, ntiles, padpx = pad_image(img, tw, th)
    blobs = [encode_tile(pad[y:y+th, x:x+tw], bps, predictor)
             for y in range(0, pad.shape[0], th) for x in range(0, pad.shape[1], tw)]

    hdr = bytearray(d[:off])
    ifd0 = struct.unpack_from(e + 'I', hdr, 4)[0]
    occupied = [(0, 8), (ifd0, ifd0 + 2 + len(t) * 12 + 4)]
    for typ, cnt, vals, vo in t.values():
        sz = TYPESZ.get(typ, 1) * cnt
        if sz > 4:
            occupied.append((vo, vo + sz))
    free_at, free_len = largest_zero_run(hdr, 0, off, occupied)
    ntags = len([k for k in t if k not in DROP]) + 4
    ifd_sz = 2 + ntags * 12 + 4
    need = ifd_sz + 8 * ntiles
    assert free_len >= need, f"零區不足:有 {free_len},要 {need}"
    ifd_at = free_at
    toff_at = ifd_at + ifd_sz
    tcnt_at = toff_at + 4 * ntiles

    offs = []; p = off
    for bl in blobs: offs.append(p); p += len(bl)

    ent = {}
    raw = d[ifd0+2:ifd0+2+len(t)*12]
    # TIFF 通常會把 tag 排序,但不要用它來推回 entry 的位置。直接從每個
    # 12-byte entry 讀 tag,才能原封不動保留未排序或帶私有 tag 的來源。
    for i in range(len(t)):
        entry = raw[i*12:(i+1)*12]
        tag = struct.unpack_from(e + 'H', entry)[0]
        if tag not in DROP:
            ent[tag] = bytearray(entry)
    ent[259][8:12] = struct.pack('<HH', 7, 0)                       # Compression = 7
    def mk(tag, typ, cnt, val): return bytearray(struct.pack('<HHI I', tag, typ, cnt, val))
    ent[322] = mk(322, 4, 1, tw)
    ent[323] = mk(323, 4, 1, th)
    ent[324] = mk(324, 4, ntiles, toff_at if ntiles > 1 else offs[0])
    ent[325] = mk(325, 4, ntiles, tcnt_at if ntiles > 1 else len(blobs[0]))

    body = bytearray(struct.pack('<H', ntags))
    for tag in sorted(ent): body += ent[tag]
    body += struct.pack('<I', 0)
    assert len(ent) == ntags and len(body) == ifd_sz, (len(ent), ntags, len(body), ifd_sz)
    hdr[ifd_at:ifd_at+len(body)] = body
    hdr[toff_at:toff_at+4*ntiles] = struct.pack('<%dI' % ntiles, *offs)
    hdr[tcnt_at:tcnt_at+4*ntiles] = struct.pack('<%dI' % ntiles, *[len(x) for x in blobs])
    hdr[4:8] = struct.pack('<I', ifd_at)                            # 第一個 IFD 改指新的

    with open(dst, 'wb') as f:
        f.write(hdr)
        for bl in blobs: f.write(bl)
        if file_align > 1:
            pad_bytes = (-f.tell()) & (file_align - 1)
            f.write(b'\0' * pad_bytes)
    logical_size = off + sum(len(x) for x in blobs)
    stored_size = (logical_size + file_align - 1) & -file_align
    return dict(W=W, H=H, tiles=ntiles, tile=(tw, th), ifd_at=ifd_at, free=free_len,
                need=need, insize=len(d), outsize=logical_size,
                stored_size=stored_size, predictor=predictor, padpx=padpx)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('tileW', nargs='?', type=int, default=256)
    ap.add_argument('tileH', nargs='?', type=int, default=256)
    ap.add_argument('--predictor', type=int, choices=range(1, 8), default=1)
    ap.add_argument('--file-align', type=int, default=1)
    a = ap.parse_args()
    r = build(a.src, a.dst, a.tileW, a.tileH, a.predictor, a.file_align)
    print(f"{r['W']}x{r['H']}  tile {r['tile'][0]}x{r['tile'][1]}  {r['tiles']} 個  predictor {r['predictor']}")
    print(f"  新 IFD 寫在 {r['ifd_at']}(零區 {r['free']:,} bytes,用掉 {r['need']})")
    print(f"  {r['insize']:,} -> logical DNG {r['outsize']:,} / stored file {r['stored_size']:,} bytes"
          f"   {r['insize']/r['stored_size']:.3f}:1")
