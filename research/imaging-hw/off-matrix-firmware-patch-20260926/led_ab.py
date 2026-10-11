#!/usr/bin/env python3
"""藍色 LED A/B:量測 OFF 矩陣 vs normal 矩陣在飽和窄頻光源上的差,
並驗證「位元組補丁」與「韌體補丁」是否等價。

三個受測檔(都在 /Users/dido/Movies/fpSup/off_test/ab/):
  L1 A001_074 第 151 幀原樣          —— 未補丁韌體,OFF 矩陣
  L2 同一幀,CM1/CM2 換成 normal      —— 只改 46 bytes,RAW SHA-256 不變
  L3 A001_075 第 151 幀原樣          —— 已補丁韌體,相機自己寫 normal 矩陣

渲染由 Resolve 完成(使用者專案副本設定),本腳本只做建檔與回讀分析。
"""
import struct, os, json, glob, hashlib
import numpy as np

SRC = '/Users/dido/Movies/fpSup/off_test'
AB = os.path.join(SRC, 'ab')
FRAME = 150            # 0-based
CM = {'CM1': (1042, 72), 'CM2': (1114, 72)}


def raw_sha(d):
    bo = '<'
    o = struct.unpack(bo + 'I', d[4:8])[0]
    so = sc = None
    for i in range(struct.unpack(bo + 'H', d[o:o + 2])[0]):
        e = o + 2 + i * 12
        t, ty, c = struct.unpack(bo + 'HHI', d[e:e + 8])
        if t == 273: so = struct.unpack(bo + 'I', d[e + 8:e + 12])[0]
        if t == 279: sc = struct.unpack(bo + 'I', d[e + 8:e + 12])[0]
    return hashlib.sha256(d[so:so + sc]).hexdigest()


def build():
    a = open(sorted(glob.glob(SRC + '/A001_074/*.DNG'))[FRAME], 'rb').read()
    b = open(sorted(glob.glob(SRC + '/A001_075/*.DNG'))[FRAME], 'rb').read()
    p = bytearray(a)
    for k in CM:
        o, n = CM[k]
        p[o:o + n] = b[o:o + n]
    p = bytes(p)
    assert raw_sha(p) == raw_sha(a), 'RAW 被動到了'
    man = {}
    for name, d in (('L1_offOriginal', a), ('L2_offNormalMatrix', p), ('L3_camNormalMatrix', b)):
        os.makedirs(os.path.join(AB, name), exist_ok=True)
        open(os.path.join(AB, name, name + '.DNG'), 'wb').write(d)
        man[name] = {'sha256': hashlib.sha256(d).hexdigest(), 'raw_sha256': raw_sha(d)}
    man['L2_offNormalMatrix']['bytes_changed_vs_L1'] = sum(1 for x, y in zip(p, a) if x != y)
    return man


def read_tiff16(path):
    d = open(path, 'rb').read()
    bo = '<' if d[:2] == b'II' else '>'
    off = struct.unpack(bo + 'I', d[4:8])[0]
    sz = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 11: 4, 12: 8}
    t = {}
    for i in range(struct.unpack(bo + 'H', d[off:off + 2])[0]):
        e = off + 2 + i * 12
        tag, ty, c = struct.unpack(bo + 'HHI', d[e:e + 8])
        nb = c * sz.get(ty, 1)
        vo = struct.unpack(bo + 'I', d[e + 8:e + 12])[0] if nb > 4 else e + 8
        fmt = {1: 'B', 3: 'H', 4: 'I'}.get(ty)
        t[tag] = struct.unpack(bo + str(c) + fmt, d[vo:vo + nb]) if fmt else d[vo:vo + nb]
    H, W, spp = t[257][0], t[256][0], t[277][0]
    buf = b''.join(d[o:o + c] for o, c in zip(t[273], t[279]))
    return np.frombuffer(buf, dtype=bo + 'u2').reshape(H, W, spp).astype(np.float64) / 65535.0


S = np.array([[0.4124564, 0.3575761, 0.1804375],
              [0.2126729, 0.7151522, 0.0721750],
              [0.0193339, 0.1191920, 0.9503041]])
D65 = np.array([0.95047, 1.0, 1.08883])


def lab(rgb):
    x = np.where(rgb < 0.081, rgb / 4.5, ((rgb + 0.099) / 1.099) ** (1 / 0.45)) @ S.T / D65
    f = np.where(x > 0.008856, np.cbrt(x), 7.787 * x + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], -1)


def analyse():
    d = os.path.join(AB, 'renders_user')
    img = {os.path.basename(p).split('.tif')[0].rstrip('0123456789'): read_tiff16(p)
           for p in sorted(glob.glob(os.path.join(d, '*.tif')))}
    L1, L2, L3 = img['L1_offOriginal'], img['L2_offNormalMatrix'], img['L3_camNormalMatrix']
    m = L1.max(-1) > 0.3                     # LED 燈芯
    ys, xs = np.nonzero(m)
    sat = lambda v: ((v.max(-1) - v.min(-1)) / np.maximum(v.max(-1), 1e-4))
    out = {'led_mask': {'threshold_on_L1_max_channel': 0.3, 'pixels': int(m.sum()),
                        'bbox_xyxy': [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]},
           'led_mean_rgb': {}, 'led_saturation': {}, 'pairs': {}}
    for n, a in (('L1_offOriginal', L1), ('L2_offNormalMatrix', L2), ('L3_camNormalMatrix', L3)):
        out['led_mean_rgb'][n] = [round(float(v), 4) for v in a[m].mean(0)]
        out['led_saturation'][n] = round(float(sat(a[m]).mean()), 4)
    for x, X, y, Y in (('L1_offOriginal', L1, 'L2_offNormalMatrix', L2),
                       ('L1_offOriginal', L1, 'L3_camNormalMatrix', L3),
                       ('L2_offNormalMatrix', L2, 'L3_camNormalMatrix', L3)):
        dE = np.linalg.norm(lab(Y) - lab(X), axis=-1)
        out['pairs']['%s->%s' % (x, y)] = {
            'led_dE76': {k: round(float(v), 3) for k, v in
                         zip(('mean', 'p50', 'p99', 'max'),
                             (dE[m].mean(), *np.percentile(dE[m], [50, 99, 100])))},
            'frame_dE76_mean': round(float(dE.mean()), 4)}
    return out


if __name__ == '__main__':
    res = {'build': build(), 'measure': analyse()}
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(res, open(os.path.join(here, 'led_results.json'), 'w'), indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))
