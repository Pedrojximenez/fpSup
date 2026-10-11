#!/usr/bin/env python3
"""rv_ring.py — 離線分析 SIG 環形緩衝槽(待機 LV RAW,8-bit Bayer)。

    python3 rv_ring.py ../captures/<label>/sigring_slot0_*.bin [...]

每個 Bayer 格位印:最小值、頂端(最大值)、頂端 8 個碼值內的像素數、
最高碼值的點數、第 50/99/99.9 百分位。頂端在曝光改變時固定不動才算飽和。
--png 另存縮圖。
"""
import argparse, pathlib
import numpy as np

W, H = 2016, 1344


def load(p):
    b = np.fromfile(p, np.uint8)
    return b[:W * H].reshape(H, W)


def stats(img):
    rows = []
    for name, (y, x) in (('G00', (0, 0)), ('X01', (0, 1)), ('X10', (1, 0)), ('G11', (1, 1))):
        v = img[y::2, x::2].ravel()
        top = int(v.max())
        h = np.bincount(v, minlength=256)
        p50, p99, p999 = np.percentile(v, [50, 99, 99.9])
        rows.append(f'{name} min {v.min():3d} top {top:3d} n@top {h[top]:6d} '
                    f'n in top8 {h[top - 7:top + 1].sum():7d}  p50 {p50:5.1f} p99 {p99:5.1f} p99.9 {p999:5.1f}')
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--png', action='store_true')
    a = ap.parse_args()
    for f in a.files:
        img = load(f)
        print(pathlib.Path(f).parent.name + '/' + pathlib.Path(f).name)
        print('  ' + '\n  '.join(stats(img)))
        if a.png:
            from PIL import Image
            Image.fromarray(img).resize((W // 2, H // 2)).save(str(f).replace('.bin', '.png'))


if __name__ == '__main__':
    main()
