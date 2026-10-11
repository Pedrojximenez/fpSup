#!/usr/bin/env python3
"""OG2K 3x3 卡的第一批成品判讀(2026-09-24,A001_009–012)。

    python3 og2k3x3_judge.py <clip 目錄的上層>

四支同一次開機、29.97p、1/60、ISO 100:009/010/012 = 3x3 卡(M139 5/4/4),
011 = 同卡以 mode_reg 蓋回 3/2/2(原廠對照)。量:

1. 逐平面亮度(減黑階,全片時間平均)
2. 逐平面時間雜訊:每像素跨影格標準差,按亮度分箱後在共同亮度範圍比中位數
3. 逐平面垂直位移(對原廠對照的時間平均):低頻(|f|<0.15 cyc/plane-px)
   相位差最小平方,單位 = CFA 平面列;奇偶差 = mean(G2,B) − mean(R,G1)
4. 末四列的列平均(§7.51 缺陷一)
"""
import glob, os, sys
import numpy as np
import rawpy

ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
CLIPS = {'A001_009': '3x3', 'A001_010': '3x3', 'A001_011': 'stock', 'A001_012': '3x3'}
REF = 'A001_011'
# 其他批:og2k3x3_judge.py <root> <ref> <clip>=<label> ...(第一個 clip 前的參數是參考片)
if len(sys.argv) > 3:
    REF = sys.argv[2]
    CLIPS = dict(a.split('=', 1) for a in sys.argv[3:])
FMAX = 0.15


def load(clip):
    fs = sorted(glob.glob(os.path.join(ROOT, clip, '*.DNG')))
    st, pat, blk = [], None, None
    for f in fs:
        with rawpy.imread(f) as r:
            st.append(r.raw_image_visible.astype(np.float32))
            pat = r.raw_pattern.copy(); blk = np.array(r.black_level_per_channel)
    return np.stack(st), pat, blk


def planes(a, pat):
    """{name: plane},名字依 raw_pattern;兩個 G 依列序稱 G1(偶列)/G2(奇列)。"""
    color = {0: 'R', 1: 'G', 2: 'B', 3: 'G'}
    out = {}
    for y in (0, 1):
        for x in (0, 1):
            c = color[pat[y, x]]
            if c == 'G':
                c = 'G1' if y == 0 else 'G2'
            out[c] = a[..., y::2, x::2]
    return out


def vshift(a, b):
    """a 相對 b 的垂直位移(平面列)。二維 [fy,fx] 相位最小平方(§7.58.6-2:只擬合 fy
    會讓水平漂移+斜向紋理投影到 dy)。正 = a 的內容在 b 的下方。"""
    a = a - a.mean(); b = b - b.mean()
    h, w = a.shape
    win = np.hanning(h)[:, None] * np.hanning(w)[None, :]
    X = np.fft.fft2(a * win) * np.conj(np.fft.fft2(b * win))
    fy = np.broadcast_to(np.fft.fftfreq(h)[:, None], X.shape)
    fx = np.broadcast_to(np.fft.fftfreq(w)[None, :], X.shape)
    m = (np.abs(fy) < FMAX) & (np.abs(fx) < FMAX) & ((fy != 0) | (fx != 0))
    wt = np.sqrt(np.abs(X[m]))
    A = np.stack([fy[m], fx[m]], 1) * wt[:, None]
    y = -np.angle(X[m]) / (2 * np.pi) * wt       # 相位 = −2π(fy·dy + fx·dx)
    return np.linalg.lstsq(A, y, rcond=None)[0][0]


def noise_curve(stack):
    mu = stack.mean(0); sd = stack.std(0, ddof=1)
    return mu.ravel(), sd.ravel()


def main():
    data = {}
    for c in CLIPS:
        st, pat, blk = load(c)
        data[c] = (st, pat, blk)
        print('%s %-10s  %d 影格  %dx%d  黑階 %s' % (c, CLIPS[c], st.shape[0],
              st.shape[2], st.shape[1], blk.tolist()))
    names = ('R', 'G1', 'G2', 'B')

    print('\n1. 亮度(減黑階,全片平均)')
    for c, (st, pat, blk) in data.items():
        P = planes(st, pat)
        print('   %s %-10s ' % (c, CLIPS[c]) +
              '  '.join('%s %7.1f' % (n, P[n].mean() - blk[0]) for n in names))

    print('\n2. 時間雜訊(共同亮度範圍內,中位數 σ/同亮度原廠 σ)')
    ref_st, ref_pat, blk = data[REF]
    refP = planes(ref_st - blk[0], ref_pat)
    for c, (st, pat, blk) in data.items():
        if c == REF:
            continue
        P = planes(st - blk[0], pat)
        row = []
        for n in names:
            mr, sr = noise_curve(refP[n]); mc, sc = noise_curve(P[n])
            lo = max(np.percentile(mr, 10), np.percentile(mc, 10), 20)
            hi = min(np.percentile(mr, 90), np.percentile(mc, 90), 3500)
            edges = np.geomspace(lo, hi, 13)
            rat = []
            for a, b in zip(edges[:-1], edges[1:]):
                ir = (mr >= a) & (mr < b); ic = (mc >= a) & (mc < b)
                if ir.sum() > 500 and ic.sum() > 500:
                    rat.append(np.median(sc[ic]) / np.median(sr[ir]))
            row.append('%s %+6.1f%%' % (n, 100 * (np.median(rat) - 1)) if rat else '%s   n/a ' % n)
        print('   %s %-10s ' % (c, CLIPS[c]) + '  '.join(row))

    print('\n3. 垂直位移(對 %s 時間平均,單位 CFA 平面列)與奇偶差' % REF)
    refM = {n: p.mean(0) for n, p in refP.items()}
    for c, (st, pat, blk) in data.items():
        M = {n: p.mean(0) for n, p in planes(st - blk[0], pat).items()}
        d = {n: vshift(M[n], refM[n]) for n in names}
        par = (d['G2'] + d['B']) / 2 - (d['R'] + d['G1']) / 2
        print('   %s %-10s ' % (c, CLIPS[c]) +
              '  '.join('%s %+.3f' % (n, d[n]) for n in names) + '   奇偶差 %+.4f' % par)
    # 同條件底線:原廠對照前後半
    h = ref_st.shape[0] // 2
    a = planes(ref_st[:h] - blk[0], ref_pat); b = planes(ref_st[h:] - blk[0], ref_pat)
    d = {n: vshift(a[n].mean(0), b[n].mean(0)) for n in names}
    print('   底線 011 前半對後半 ' + '  '.join('%s %+.3f' % (n, d[n]) for n in names))

    print('\n5. 跨色混入(32x32 區塊平均;X_c ≈ a·S_c + k·S_其他色,報 k/(a+k),不混色 = 0)')
    def tiles(p, t=32):
        h, w = p.shape[0] // t * t, p.shape[1] // t * t
        return p[:h, :w].reshape(h // t, t, w // t, t).mean((1, 3)).ravel()
    refT = {n: tiles(m) for n, m in refM.items()}
    others = {'R': ('G1', 'G2'), 'G1': ('R', 'B'), 'G2': ('R', 'B'), 'B': ('G1', 'G2')}
    for c, (st, pat, blk) in data.items():
        M = {n: tiles(p.mean(0)) for n, p in planes(st - blk[0], pat).items()}
        row = []
        for n in names:
            o = (refT[others[n][0]] + refT[others[n][1]]) / 2
            A = np.stack([refT[n], o, np.ones_like(o)], 1)
            (a, k, _), *_ = np.linalg.lstsq(A, M[n], rcond=None)
            row.append('%s %+.3f' % (n, k / (a + k)))
        print('   %s %-10s ' % (c, CLIPS[c]) + '  '.join(row))

    print('\n4. 末四列列平均(減黑階)')
    for c, (st, pat, blk) in data.items():
        m = st.mean(0)[-4:].mean(1) - blk[0]
        print('   %s %-10s ' % (c, CLIPS[c]) + '  '.join('%7.1f' % v for v in m))


main()
