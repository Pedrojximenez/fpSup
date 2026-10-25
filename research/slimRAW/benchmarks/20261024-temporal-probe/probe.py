"""Offline exploratory RAW predictor benchmark. Does not access camera hardware.

Measures residual payloads only, not a complete archival format or sustained codec.
All Zstandard variants use level 3, a fixed byte shuffle, and exact reconstruction.
"""
import ctypes as ct
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path('/Users/dido/Developer.localized/SIGMAfp_re')
sys.path.insert(0, str(ROOT / 'research/slimRAW'))
from tiff import parse
from ljpeg import decode_tile

OUT = Path(__file__).resolve().parent
z = ct.CDLL('/opt/homebrew/lib/libzstd.dylib')
z.ZSTD_compressBound.argtypes = [ct.c_size_t]
z.ZSTD_compressBound.restype = ct.c_size_t
for name in ('ZSTD_compress', 'ZSTD_decompress'):
    fn = getattr(z, name)
    fn.argtypes = [ct.c_void_p, ct.c_size_t, ct.c_void_p, ct.c_size_t] + ([ct.c_int] if name.endswith('compress') and name != 'ZSTD_decompress' else [])
    fn.restype = ct.c_size_t
z.ZSTD_isError.argtypes = [ct.c_size_t]
z.ZSTD_isError.restype = ct.c_uint


def compressed(data):
    dst = ct.create_string_buffer(z.ZSTD_compressBound(len(data)))
    n = z.ZSTD_compress(dst, len(dst), data, len(data), 3)
    assert not z.ZSTD_isError(n)
    blob = dst.raw[:n]
    check = ct.create_string_buffer(len(data))
    m = z.ZSTD_decompress(check, len(check), blob, len(blob))
    assert not z.ZSTD_isError(m) and m == len(data) and check.raw == data
    return blob


def read_raw(path):
    data, endian, _, ifds = parse(str(path))
    t = ifds[0]
    get = lambda k: t[k][2][0]
    w, h, bps, comp = (get(k) for k in (256, 257, 258, 259))
    assert endian == '<' and bps == 12 and comp == 7
    tw, th = get(322), get(323)
    a = np.zeros((h, w), dtype=np.int32)
    counts = t[325][2]
    actual_jpeg_sizes = []
    for k, (offset, count) in enumerate(zip(t[324][2], counts)):
        blob = data[offset:offset+count]
        actual = blob.rfind(b'\xff\xd9')+2
        assert actual >= 2 and not any(blob[actual:])
        actual_jpeg_sizes.append(actual)
        p, x, y, nf, rows = decode_tile(blob)
        assert p == bps and (x*nf, y) == (tw, th)
        yy, xx = (k // ((w+tw-1)//tw))*th, (k % ((w+tw-1)//tw))*tw
        tile = np.asarray(rows, dtype=np.int32)
        hh, ww = min(th, h-yy), min(tw, w-xx)
        a[yy:yy+hh, xx:xx+ww] = tile[:hh, :ww]
    assert a.min() >= 0 and a.max() < 2**bps
    # Four distinct CFA phase planes. No white balance, crop or demosaicking.
    planes = np.stack([a[dy::2, dx::2] for dy, dx in [(0,0),(0,1),(1,0),(1,1)]])
    back = np.empty_like(a)
    for plane, (dy, dx) in zip(planes, [(0,0),(0,1),(1,0),(1,1)]):
        back[dy::2, dx::2] = plane
    assert np.array_equal(back, a)
    return planes, dict(file=str(path), sha256=hashlib.sha256(data).hexdigest(),
        raw_sha256_le16=hashlib.sha256(a.astype('<u2').tobytes()).hexdigest(),
        shape=list(a.shape), bps=bps, cfa=t[33422][2], mean=float(a.mean()),
        min=int(a.min()), max=int(a.max()), source_bytes=len(data),
        jpeg_payload_bytes=sum(actual_jpeg_sizes), tile_storage_bytes=sum(counts))


def med(a):
    p = np.full_like(a, 2048)
    p[:, 0, 1:] = a[:, 0, :-1]
    p[:, 1:, 0] = a[:, :-1, 0]
    left, up, ul = a[:, 1:, :-1], a[:, :-1, 1:], a[:, :-1, :-1]
    p[:, 1:, 1:] = np.clip(left + up - ul, np.minimum(left,up), np.maximum(left,up))
    return p


def measure(a, pred):
    r = a - pred
    zz = np.where(r >= 0, 2*r, -2*r-1).astype('<u2')
    wire = zz.view(np.uint8).reshape(-1,2).T.copy().tobytes()
    blob = compressed(wire)
    # Decode wire representation, then invert the prediction without clipping.
    invzz = np.frombuffer(wire, np.uint8).reshape(2,-1).T.copy().view('<u2').reshape(r.shape).astype(np.int32)
    invr = (invzz >> 1) ^ -(invzz & 1)
    assert np.array_equal(invr+pred, a)
    return len(blob)


def motion(a, prev, block=32, radius=4):
    # Integer Bayer-grid motion: radius 4 = +/-8 mosaic pixels.
    # Green-only SAD estimates one vector for all four CFA phases.
    assert a.shape == prev.shape
    h,w = a.shape[1:]
    gcur = (a[1]+a[2])//2
    gprev = (prev[1]+prev[2])//2
    p = np.empty_like(a)
    vectors = []
    for y in range(0,h,block):
        for x in range(0,w,block):
            hh,ww = min(block,h-y), min(block,w-x)
            patch = gcur[y:y+hh,x:x+ww]
            best = None
            for dy in range(max(-radius,-y),min(radius,h-y-hh)+1):
                for dx in range(max(-radius,-x),min(radius,w-x-ww)+1):
                    sad = int(np.abs(patch-gprev[y+dy:y+dy+hh,x+dx:x+dx+ww]).sum())
                    key = (sad, abs(dy)+abs(dx), dy,dx)
                    if best is None or key < best:
                        best = key
            _,_,dy,dx = best
            p[:,y:y+hh,x:x+ww] = prev[:,y+dy:y+dy+hh,x+dx:x+dx+ww]
            vectors.append([dy,dx])
    # Byte cost includes a deliberately simple fixed int8 pair per block.
    return p, len(vectors)*2, sum(dy != 0 or dx != 0 for dy,dx in vectors)


def main():
    folder = ROOT/'projects/rec-core/writer/validation/20261015-live/frames-A001_070'
    arrays, inputs = [], []
    for n in (8,9,10):
        a, info = read_raw(folder/f'{n:06d}.DNG')
        arrays.append(a); inputs.append(info)
        print('decoded',n,info['mean'],flush=True)
    report = dict(scope='Exploratory residual-payload comparison on 3 adjacent frames from one existing clip; no full archive or real-time claim.',
        limitations=[
            'One low-signal clip only; unknown ISO and scene content. Not a representative video dataset.',
            'Prediction residual payloads only. Initial reference frames, DNG headers, audio and archival metadata excluded.',
            'No JXL, JPEG-LS, FFV1 or optimized Rice/rANS codec measured.',
            'MC uses green SAD, 32x32 phase-plane blocks and integer +/-4 phase-grid samples only.',
            'Adaptive payload includes mode/length and selected motion-vector byte counts, but is not a serialized end-to-end archive.',
            'Intra MED prediction can reference earlier decoded samples outside the selected tile; no independent tile decoding claim.',
            'Entropy roundtrip and residual inverse are checked separately; no original-DNG byte reconstruction claim.',
        ],
        inputs=inputs, zstd_level=3, representation='4 phase planes, signed residual zigzag uint16, byte shuffle', frames=[])
    for i in (1,2):
        a, prev = arrays[i], arrays[i-1]
        pmed = med(a)
        preds = {'intra_med_zstd':pmed, 'previous_frame_delta_zstd':prev}
        if i >= 2:
            preds['previous_2_mean_zstd'] = (prev+arrays[i-2])//2
        start = time.perf_counter()
        pmc, mvbytes, moving = motion(a,prev)
        preds['integer_motion_zstd'] = pmc
        row = dict(number=i+8, mean_abs_frame_delta=float(np.abs(a-prev).mean()),
            unchanged_samples_pct=float(np.mean(a == prev)*100),
            packed12_bytes=a.size*12//8, camera_ljpeg_payload_bytes=inputs[i]['jpeg_payload_bytes'],
            motion_search_seconds=time.perf_counter()-start, motion_nonzero_blocks=moving,
            motion_vector_bytes=mvbytes, payload_bytes={})
        for name,pred in preds.items():
            row['payload_bytes'][name] = measure(a,pred)+(mvbytes if name == 'integer_motion_zstd' else 0)
        # Same tile geometry for intra-only and adaptive coding; includes a
        # one-byte mode and four-byte length per tile, motion vectors where used.
        adaptive, intra, modes = 0,0,{}
        for y in range(0,a.shape[1],32):
            for x in range(0,a.shape[2],32):
                sl = np.s_[:,y:y+32,x:x+32]
                costs = {name:measure(a[sl],p[sl])+(2 if name == 'integer_motion_zstd' else 0)
                         for name,p in preds.items()}
                name = min(costs,key=costs.get)
                adaptive += costs[name]+5
                intra += costs['intra_med_zstd']+5
                modes[name] = modes.get(name,0)+1
        row['payload_bytes']['tiled_intra_med_zstd'] = intra
        row['payload_bytes']['tiled_adaptive_zstd'] = adaptive
        row['adaptive_modes'] = modes
        row['all_residual_roundtrips_exact'] = True
        report['frames'].append(row)
        print(json.dumps(row),flush=True)
    (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
