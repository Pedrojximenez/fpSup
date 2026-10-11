#!/usr/bin/env python3
"""3D .cube → 3×3 矩陣 + 每通道 1D 曲線近似模型,並報告逼近誤差。

這裡只評估「矩陣＋曲線」模型。機內多個原生區塊的能力仍在研究，
不將這個模型當成 fp 整顆 ISP 的上限。可用候選:
  顯示端   3×3 矩陣(bank 0x30190870 / 0x30190810 / 0x30190C80,係數尺度 256)
           + 每通道 16 點 gamma(0x30190940 / 0x30190CB0)
  ISP 端   MAT_TOP RGBLMAT 3×3(shadow 0x30210CB0..CE4,兩組 9×11-bit;MMIO 0x30115100..34)
           + 88 條 2048 點 tone 資源(0xC0971F34)
  以上路由、生效 bank 與通道語意須另驗,不將本模型稱為已驗證的 native backend。
  ΔE76 假定输出為 sRGB;技術 LUT 的其他输出編碼不能直接用此數字作色準判定。

模型: out = G( M · in ),M 列和固定為 1。
  因為列和=1,灰色進去還是灰色,所以 G 可以直接從 LUT 自己的灰階軸讀出來,
  不需要迭代擬合 —— 只剩 M 是一次最小平方解。良態,不會發散。

用法:
  python3 cube2fp.py look.cube                # 報告 + 輸出 look.fp.json
  python3 cube2fp.py look.cube --scale 256    # 指定矩陣定點尺度
  python3 cube2fp.py look.cube --knots 16     # 曲線節點數(顯示端 gamma 是 16)

⚠ 未證實的部分:顯示端 gamma 表的實際數值範圍與 3×3 的暫存器編碼尚未量到。
  本腳本輸出的是「浮點結果 + 依指定尺度的定點版本」,上機前要先用一組已知值回讀驗證。
"""
import argparse, json, os, re, sys
import numpy as np

# ---------- .cube ----------

def read_cube(path):
    # One maintained importer: never silently ignore domain, invalid headers,
    # channel ordering or a shaper when comparing this approximate model.
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'fpSup/lut'))
    from cube import Cube
    cube = Cube.read(path)
    if cube.table3d is None or cube.table1d is not None:
        raise ValueError('此近似工具只處理純 3D；完整 1D/shaper 匯入使用 fpSup/lut')
    if cube.range3d != ((0., 0., 0.), (1., 1., 1.)):
        raise ValueError('此模型要求 0..1 domain，不能忽略自訂輸入範圍')
    n = len(cube.table3d)
    a = cube.table3d.reshape(-1, 3)
    g = np.linspace(0, 1, n); idx = np.arange(n ** 3)
    inp = np.stack([g[idx % n], g[(idx // n) % n], g[idx // (n * n)]], -1)
    return inp, a, n, g


# ---------- 色度 ----------
S = np.array([[0.4124564, 0.3575761, 0.1804375],
              [0.2126729, 0.7151522, 0.0721750],
              [0.0193339, 0.1191920, 0.9503041]])
W = np.array([0.95047, 1.0, 1.08883])


def lab(rgb):
    rgb = np.clip(rgb, 0, 1)
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    x = lin @ S.T / W
    f = np.where(x > 0.008856, np.cbrt(x), 7.787 * x + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], -1)


def saturation(v):
    mx, mn = v.max(-1), v.min(-1)
    return np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)


# ---------- 健檢 ----------

def sanity(inp, out, n, g):
    di = np.arange(n) * (1 + n + n * n)
    grey = out[di]
    issues = []
    for c, ch in enumerate('RGB'):
        if np.any(np.diff(grey[:, c]) < -1e-6):
            issues.append('灰階軸 %s 通道非單調 → 曲線不可逆,擬合會失真' % ch)
    sat_at = np.argmax(grey.max(1) >= 0.999) if np.any(grey.max(1) >= 0.999) else None
    if sat_at is not None and sat_at < n * 0.8:
        issues.append('灰階軸在輸入 %.2f 就到頂 → 這個 LUT 預期的輸入不是 0–1 顯示域(domain 不合)'
                      % g[sat_at])
    dev = float(np.abs(grey - grey.mean(1, keepdims=True)).max())
    return grey, issues, dev


# ---------- 擬合 ----------

def fit(inp, out, grey, g, wsat=2.5):
    w = np.exp(-wsat * saturation(inp))
    t = np.empty_like(out)
    for c in range(3):
        y = np.maximum.accumulate(grey[:, c])
        t[:, c] = np.interp(out[:, c], y, g)          # G 的反函式
    A = np.stack([inp[:, 0] - inp[:, 2], inp[:, 1] - inp[:, 2]], -1) * w[:, None]
    M = np.zeros((3, 3))
    for c in range(3):
        b = (t[:, c] - inp[:, 2]) * w
        m12, *_ = np.linalg.lstsq(A, b, rcond=None)
        M[c] = [m12[0], m12[1], 1 - m12[0] - m12[1]]
    return M


def apply_model(inp, M, grey, g, knots=None):
    y = inp @ M.T
    if knots:
        kx = np.linspace(0, 1, knots)
        return np.stack([np.interp(y[:, c], kx,
                                   np.interp(kx, g, np.maximum.accumulate(grey[:, c])))
                         for c in range(3)], -1)
    return np.stack([np.interp(y[:, c], g, np.maximum.accumulate(grey[:, c]))
                     for c in range(3)], -1)


def report(inp, out, pred):
    sat = saturation(inp)
    dE = np.linalg.norm(lab(pred) - lab(out), axis=-1)
    rows = []
    for lo, hi in ((0, .15), (.15, .35), (.35, .60), (.60, 1.01)):
        m = (sat >= lo) & (sat < hi)
        rows.append({'saturation': '%.2f-%.2f' % (lo, hi),
                     'grid_fraction': round(float(m.mean()), 4),
                     'dE76_mean': round(float(dE[m].mean()), 2),
                     'dE76_p95': round(float(np.percentile(dE[m], 95)), 2),
                     'dE76_max': round(float(dE[m].max()), 2)})
    return rows, dE


def quantise(M, grey, g, knots, scale):
    Mi = np.round(M * scale).astype(int)
    for r in range(3):                                # 保住列和 = scale
        Mi[r, np.argmax(np.abs(M[r]))] += scale - Mi[r].sum()
    kx = np.linspace(0, 1, knots)
    curves = [[float(v) for v in np.interp(kx, g, np.maximum.accumulate(grey[:, c]))]
              for c in range(3)]
    return Mi, kx, curves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cube'); ap.add_argument('--scale', type=int, default=256)
    ap.add_argument('--knots', type=int, default=16)
    ap.add_argument('--wsat', type=float, default=2.5,
                    help='擬合時低飽和的權重(越大越偏重中性附近,真實影像建議 2–3)')
    a = ap.parse_args()

    inp, out, n, g = read_cube(a.cube)
    grey, issues, dev = sanity(inp, out, n, g)
    M = fit(inp, out, grey, g, a.wsat)
    pred_full = apply_model(inp, M, grey, g)
    pred_q = apply_model(inp, M, grey, g, knots=a.knots)
    rows_full, _ = report(inp, out, pred_full)
    rows_q, dEq = report(inp, out, pred_q)
    Mi, kx, curves = quantise(M, grey, g, a.knots, a.scale)

    print('== %s  (%d³)' % (os.path.basename(a.cube), n))
    if issues:
        print('  ⚠ 健檢:')
        for s in issues: print('     ' + s)
    else:
        print('  健檢通過(灰階軸單調、domain 合理,最大偏離中性 %.4f)' % dev)
    print('  3×3(列和=1):')
    for r in M: print('     ' + '  '.join('%8.4f' % v for v in r))
    print('  定點(尺度 %d,列和保持 %d):' % (a.scale, a.scale))
    for r in Mi: print('     ' + '  '.join('%6d' % v for v in r) + '   (和 %d)' % r.sum())
    print('  誤差(曲線 %d 點,即顯示端 gamma 規格):' % a.knots)
    for r in rows_q:
        print('     飽和 %-9s 佔格點 %5.1f%%  ΔE mean %5.2f  p95 %6.2f  max %6.2f'
              % (r['saturation'], 100 * r['grid_fraction'], r['dE76_mean'], r['dE76_p95'], r['dE76_max']))
    verdict = ('需先確認 LUT 輸入／灰軸，不建議直接部署' if issues else
               '此近似模型適合轉' if rows_q[0]['dE76_mean'] < 2 and rows_q[1]['dE76_mean'] < 5
               else '此近似模型勉強' if rows_q[1]['dE76_mean'] < 10 else '此近似模型誤差過大，需評估其他區塊')
    print('  判定:%s' % verdict)

    outp = os.path.splitext(a.cube)[0] + '.fp.json'
    json.dump({'source': os.path.basename(a.cube), 'lut_size': n,
               'model': 'out = G(M @ in), M 列和 = 1',
               'sanity_issues': issues, 'grey_axis_max_neutral_deviation': round(dev, 5),
               'matrix_float': [[round(float(v), 6) for v in r] for r in M],
               'matrix_fixed': {'scale': a.scale, 'rows': Mi.tolist()},
               'curves': {'knots': a.knots, 'x': [round(float(v), 6) for v in kx],
                          'R': [round(v, 6) for v in curves[0]],
                          'G': [round(v, 6) for v in curves[1]],
                          'B': [round(v, 6) for v in curves[2]]},
               'error_by_saturation_full_res': rows_full,
               'error_by_saturation_quantised': rows_q,
               'verdict': verdict,
               'unverified': ['顯示端 gamma 表的數值範圍', '顯示端 3×3 的暫存器編碼']},
              open(outp, 'w'), indent=1, ensure_ascii=False)
    print('  → %s' % outp)


if __name__ == '__main__':
    main()
