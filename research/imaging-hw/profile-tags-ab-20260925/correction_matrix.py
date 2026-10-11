#!/usr/bin/env python3
"""從實拍檔的 ColorMatrix 推導「OFF → 應有渲染」的修正矩陣。

Michael Garrett 的 fp color workflow feedback(2023-10-14)第 11 頁要求 SIGMA 公布
一張能把 fp OFF 從 Resolve 的 P3D60/Linear 轉到 ACES AP0/D60 或 Rec2020/D65 的矩陣。
這支腳本就是那張矩陣 —— 但用的是 fp 韌體自己的 normal ColorMatrix,不是外部擬合。

做法:對同一個 as-shot neutral,分別算 OFF 與 normal 兩條 camera→輸出空間的鏈
(Bradford 把該次拍攝的中性適應到輸出白點),再相除。結果列和恆為 1,中性不動。

⚠ 這不是「一張」矩陣:A 與 D65 兩個端點差很多,實際要用的是依當次白平衡在兩者之間
內插的結果。單一矩陣只在該色溫附近成立。
"""
import struct, json, os
import numpy as np

OFF = '/Users/dido/Movies/fpSup/color area/A001_297/A001_297_20260924_000001.DNG'
STD = '/Users/dido/Movies/fpSup/color area/A001_298/A001_298_20260924_000001.DNG'

BRADFORD = np.array([[0.8951, 0.2664, -0.1614],
                     [-0.7502, 1.7135, 0.0367],
                     [0.0389, -0.0685, 1.0296]])
D60 = np.array([0.95265, 1.0, 1.00883])
D65 = np.array([0.95047, 1.0, 1.08883])


def rational_tag(path, tag):
    d = open(path, 'rb').read()
    bo = '<' if d[:2] == b'II' else '>'
    o = struct.unpack(bo + 'I', d[4:8])[0]
    for i in range(struct.unpack(bo + 'H', d[o:o + 2])[0]):
        e = o + 2 + i * 12
        t, ty, c = struct.unpack(bo + 'HHI', d[e:e + 8])
        if t != tag:
            continue
        vo = struct.unpack(bo + 'I', d[e + 8:e + 12])[0]
        fmt = 'i' if ty == 10 else 'I'
        v = struct.unpack(bo + str(2 * c) + fmt, d[vo:vo + 8 * c])
        return np.array([v[k] / v[k + 1] for k in range(0, 2 * c, 2)])


def bradford(src, dst):
    s, d = BRADFORD @ src, BRADFORD @ dst
    return np.linalg.inv(BRADFORD) @ np.diag(d / s) @ BRADFORD


def xyz_to_rgb(prim, white):
    (xr, yr), (xg, yg), (xb, yb) = prim
    M = np.array([[xr / yr, xg / yg, xb / yb], [1, 1, 1],
                  [(1 - xr - yr) / yr, (1 - xg - yg) / yg, (1 - xb - yb) / yb]])
    return np.linalg.inv(M * np.linalg.solve(M, white))


SPACES = {
    'Rec.709 (D65)':   (xyz_to_rgb([(.64, .33), (.30, .60), (.15, .06)], D65), D65),
    'P3-D60':          (xyz_to_rgb([(.680, .320), (.265, .690), (.150, .060)], D60), D60),
    'ACES AP0 (D60)':  (xyz_to_rgb([(.7347, .2653), (0.0, 1.0), (.0001, -.077)], D60), D60),
    'Rec.2020 (D65)':  (xyz_to_rgb([(.708, .292), (.170, .797), (.131, .046)], D65), D65),
}


def main():
    asn = rational_tag(OFF, 50728)
    assert np.allclose(asn, rational_tag(STD, 50728)), 'AsShotNeutral 不同,兩檔不可比'
    cm = {'off':  {'A': rational_tag(OFF, 50721).reshape(3, 3), 'D65': rational_tag(OFF, 50722).reshape(3, 3)},
          'norm': {'A': rational_tag(STD, 50721).reshape(3, 3), 'D65': rational_tag(STD, 50722).reshape(3, 3)}}

    def cam_to_out(c, T, wout):
        return T @ bradford(np.linalg.inv(c) @ asn, wout) @ np.linalg.inv(c)

    out = {'as_shot_neutral': [round(float(x), 6) for x in asn],
           'source': {'off': os.path.basename(OFF), 'normal': os.path.basename(STD)},
           'note': '線性域。正確渲染 = M · 目前(OFF)渲染。列和恆為 1。',
           'matrices': {}}
    for sp, (T, wout) in SPACES.items():
        out['matrices'][sp] = {}
        print('---', sp)
        for ill in ('A', 'D65'):
            M = cam_to_out(cm['norm'][ill], T, wout) @ np.linalg.inv(cam_to_out(cm['off'][ill], T, wout))
            out['matrices'][sp][ill] = [[round(float(v), 5) for v in row] for row in M]
            print('  %-4s' % ill, ' '.join('%8.4f' % v for v in M.ravel()),
                  ' 列和', np.round(M.sum(1), 4))
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(out, open(os.path.join(here, 'correction_matrices.json'), 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
