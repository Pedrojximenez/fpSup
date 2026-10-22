"""橫向痕跡的量化與評分。REDUCTION_KERNEL_MEASURED.md §7.7–7.8。

做法:用該路線「實際會叫到的相位」重取樣真實影格得 Yp,再用「那些相位自己的
平均」得 Yu,D = Yp - Yu 就是相位單獨造成的貢獻。不需要對齊任何東西。

要看的是兩個數字:D 佔輸出對比多少,以及它每幾列重複一次 ——
隔列交替的誤差看起來是顆粒,每十六列重複一次的才看起來是條帶。
"""
import numpy as np
from common import load, plane

TAPS = np.arange(-5, 6)

def load_true(nm):
    """存檔是用 ph = n%16 擬合的;比例 25/16 之下真正的相位是 (9n)%16。"""
    W = np.load(nm); W = W / W.sum(1, keepdims=True)
    return np.array([W[(9 * q) % 16] for q in range(16)])

def used_phases(R, n=4096):
    return sorted(set(int(np.floor(16 * ((k * R) % 1.0))) % 16 for k in range(n)))

def rwzm(X, R, C, n, ax, W, uniform=False):
    m = R * np.arange(n) + C
    b = np.floor(m).astype(int)
    ph = np.floor(16 * (m - b)).astype(int) % 16
    Wu = W[used_phases(R)].mean(0)
    o = None
    for ti, j in enumerate(TAPS):
        idx = np.clip(b + j, 0, X.shape[ax] - 1)
        src = X[idx] if ax == 0 else X[:, idx]
        w = np.full(n, Wu[ti]) if uniform else W[ph, ti]
        c = (w[:, None] * src) if ax == 0 else (w[None, :] * src)
        o = c if o is None else o + c
    return o

def phase_term(sub, R, Wv, Wh):
    n = int((sub.shape[0] - 16) / R) - 2
    m = int((sub.shape[1] - 16) / R) - 2
    Yp = rwzm(sub, R, 6., n, 0, Wv); Yp = rwzm(Yp, R, 6., m, 1, Wh)
    Yu = rwzm(sub, R, 6., n, 0, Wv, True); Yu = rwzm(Yu, R, 6., m, 1, Wh, True)
    D = Yp - Yu
    P = len(used_phases(R))
    def uneven(ax):
        if P < 2:
            return 1.0
        e = (D ** 2).mean(1 - ax)
        pr = np.array([e[i::P].mean() for i in range(P)])
        return pr.max() / max(pr.min(), 1e-12)
    return 100 * D.std() / Yp.std(), uneven(0), uneven(1), P

if __name__ == '__main__':
    Wv = load_true('fhd_Wv.npy'); Wh = load_true('fhd_Wh.npy')
    I = plane(load('OG3K'), 0, 1).astype(float)
    sub = I[300:1500, 600:2400]
    print('  感測器 ÷2 / ÷3 直出 相位數 1  D 0.00%  列 1.0x  欄 1.0x  →  A')
    for lbl, R in (('FHD / UHD  RWZM 25/16', 25 / 16.),
                   ('3/2', 1.5), ('整數 2', 2.0)):
        d, rr, cc, P = phase_term(sub, R, Wv, Wh)
        print(f'  {lbl:24s} 相位數 {P:2d}  D {d:5.2f}%  列 {rr:5.1f}x  欄 {cc:4.1f}x')
