#!/usr/bin/env python3
"""讀回 Resolve 渲出的 16-bit TIFF,量測每個 profile tag 對畫面的實際影響。

輸出 results.json。所有數字都是從檔案算出來的,沒有手打。
"""
import struct, glob, os, json, sys
import numpy as np

SETS = {
    'default_project': '/Users/dido/Movies/fpSup/color area/looktag_ab/renders_default',
    'user_project':    '/Users/dido/Movies/fpSup/color area/looktag_ab/renders_user',
}
PAIRS = [
    ('A_stdOriginal', 'B_stdNoToneCurve',        'ToneCurve 標籤的影響(同一幀 RAW)'),
    ('A_stdOriginal', 'C_stdNoHueSatMap',        'HueSatMap 標籤的影響(同一幀 RAW)'),
    ('A_stdOriginal', 'D_stdNoLook',             '兩個 look 標籤合計(同一幀 RAW)'),
    ('E_offOriginal', 'F_offNormalMatrix',       '只換 ColorMatrix1/2(同一幀 RAW)'),
    ('E_offOriginal', 'A_stdOriginal',           'OFF 原樣 vs Standard(不同 take)'),
    ('A_stdOriginal', 'G_offFullStandardProfile', '完整 profile 移植 vs 真 Standard(不同 take)'),
    ('D_stdNoLook',   'F_offNormalMatrix',       '兩支不同 take 的底線差異'),
]


def read_tiff16(path):
    d = open(path, 'rb').read()
    bo = '<' if d[:2] == b'II' else '>'
    off = struct.unpack(bo + 'I', d[4:8])[0]
    n = struct.unpack(bo + 'H', d[off:off + 2])[0]
    sz = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 11: 4, 12: 8}
    t = {}
    for i in range(n):
        e = off + 2 + i * 12
        tag, ty, c = struct.unpack(bo + 'HHI', d[e:e + 8])
        nb = c * sz.get(ty, 1)
        vo = struct.unpack(bo + 'I', d[e + 8:e + 12])[0] if nb > 4 else e + 8
        fmt = {1: 'B', 3: 'H', 4: 'I'}.get(ty)
        t[tag] = struct.unpack(bo + str(c) + fmt, d[vo:vo + nb]) if fmt else d[vo:vo + nb]
    assert t[259][0] == 1 and set(t[258]) == {16}, 'expect uncompressed 16-bit'
    H, W, spp = t[257][0], t[256][0], t[277][0]
    buf = b''.join(d[o:o + c] for o, c in zip(t[273], t[279]))
    return np.frombuffer(buf, dtype=bo + 'u2').reshape(H, W, spp).astype(np.float64) / 65535.0


S_RGB2XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                      [0.2126729, 0.7151522, 0.0721750],
                      [0.0193339, 0.1191920, 0.9503041]])
D65 = np.array([0.95047, 1.0, 1.08883])


def _lin(x):
    return np.where(x < 0.081, x / 4.5, ((x + 0.099) / 1.099) ** (1 / 0.45))


def lab(rgb):
    """把 Rec.709 顯示值轉 CIELAB。只用於 ΔE 的量級比較,不是絕對色度測量。"""
    xyz = _lin(np.clip(rgb, 0, 1)) @ S_RGB2XYZ.T / D65
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], -1)


def saturation(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1)
    return np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0.0)


def compare(A, B):
    d = B - A
    a, b = A.reshape(-1, 3), B.reshape(-1, 3)
    M, *_ = np.linalg.lstsq(a, b, rcond=None)
    M = M.T
    res = np.abs(a @ M.T - b)
    dE = np.linalg.norm(lab(B) - lab(A), axis=-1).ravel()
    s = saturation(A).ravel()
    buckets = {}
    for lo, hi in ((0, .05), (.05, .10), (.10, .20), (.20, .35), (.35, 1.01)):
        m = (s >= lo) & (s < hi)
        if m.sum() < 100:
            continue
        buckets['%.2f-%.2f' % (lo, hi)] = {
            'pixel_fraction': round(float(m.mean()), 4),
            'dE76_mean': round(float(dE[m].mean()), 3),
            'dE76_p99': round(float(np.percentile(dE[m], 99)), 3)}
    return {
        'rgb_abs_diff': {'mean': round(float(np.abs(d).mean()), 6),
                         'p99': round(float(np.percentile(np.abs(d), 99)), 6),
                         'max': round(float(np.abs(d).max()), 6)},
        'dE76': {'mean': round(float(dE.mean()), 3),
                 'p50': round(float(np.percentile(dE, 50)), 3),
                 'p90': round(float(np.percentile(dE, 90)), 3),
                 'p99': round(float(np.percentile(dE, 99)), 3),
                 'max': round(float(dE.max()), 3)},
        'dE76_by_saturation': buckets,
        'best_fit_3x3': [[round(float(v), 4) for v in row] for row in M],
        'fit_row_sums': [round(float(v), 4) for v in M.sum(1)],
        'fit_max_offdiagonal': round(float(np.abs(M - np.diag(M.diagonal())).max()), 4),
        'fit_residual_mean': round(float(res.mean()), 6),
        'fit_residual_max': round(float(res.max()), 6),
    }


def main():
    out = {}
    for setname, d in SETS.items():
        img = {}
        for p in sorted(glob.glob(os.path.join(d, '*.tif'))):
            key = os.path.basename(p).split('.tif')[0].rstrip('0123456789')
            img[key] = read_tiff16(p)
        out[setname] = {
            'frame_means': {k: [round(float(v), 5) for v in a.reshape(-1, 3).mean(0)]
                            for k, a in sorted(img.items())},
            'saturation_percentiles_E': {p: round(float(v), 4) for p, v in zip(
                ('p50', 'p90', 'p99', 'max'),
                np.percentile(saturation(img['E_offOriginal']), [50, 90, 99, 100]))},
            'pairs': {'%s->%s' % (x, y): dict(note=n, **compare(img[x], img[y]))
                      for x, y, n in PAIRS},
        }
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(out, open(os.path.join(here, 'results.json'), 'w'), indent=1, ensure_ascii=False)
    for s in out:
        print('===', s)
        for k, v in out[s]['pairs'].items():
            print('  %-42s meanΔ %.4f  ΔE mean %.2f  非對角 %.4f  殘差 %.5f' % (
                k, v['rgb_abs_diff']['mean'], v['dE76']['mean'],
                v['fit_max_offdiagonal'], v['fit_residual_mean']))


if __name__ == '__main__':
    main()
