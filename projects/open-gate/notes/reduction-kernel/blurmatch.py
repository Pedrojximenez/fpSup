"""「低光用 FHD 比較好」的檢定。REDUCTION_KERNEL_MEASURED.md §7.9。

N_eff 說 FHD 平均的 photodiode 是 OG2K 的兩倍(= 半級),算術沒錯。
但「平均更多樣本」同時就是畫面變軟的原因,而軟的畫面看起來就是比較不吵。
所以把對照組逐步模糊到紋理對比等於 FHD,再讀它此時的雜訊底。

兩個場景都得到同一個答案:銳利度對齊後持平(×1.01)。
"""
import numpy as np
import rawpy

def gplane(path, black=256.0):
    r = rawpy.imread(path)
    return (r.raw_image_visible.astype(float) - black)[0::2, 1::2]

def boxblur(a, k):
    ker = np.ones(k) / k
    s = np.apply_along_axis(lambda r: np.convolve(r, ker, mode='same'), 1, a)
    return np.apply_along_axis(lambda r: np.convolve(r, ker, mode='same'), 0, s)

def highpass(c, k=5):
    return c - boxblur(c, k)

def texture_and_noise(P, tex_box, flat_box, bright_pct=70):
    """紋理對比(扣掉同亮度換算的雜訊底)與雜訊底本身。"""
    y0, y1, x0, x1 = tex_box
    c = P[y0:y1, x0:x1].astype(float)
    h = highpass(c)
    m = c > np.percentile(c, bright_pct)
    m[:3] = m[-3:] = False; m[:, :3] = m[:, -3:] = False
    sig, lvl = np.sqrt(np.mean(h[m] ** 2)), c[m].mean()

    y0, y1, x0, x1 = flat_box
    d = P[y0:y1, x0:x1].astype(float)
    hn = highpass(d)
    n, nl = np.sqrt(np.mean(hn[3:-3, 3:-3] ** 2)), d[3:-3, 3:-3].mean()

    nn = n * np.sqrt(lvl / max(nl, 1e-6))          # 把雜訊底換算到紋理區的亮度
    real = np.sqrt(max(sig * sig - nn * nn, 0))
    return 100 * real / lvl, n

def sweep(ref, tex_box, flat_box, target_tex, weights=(0, .25, .5, .75, 1.)):
    """把 ref 逐步模糊,回報紋理追平 target_tex 時的雜訊底。"""
    out = []
    for w in weights:
        Q = ref if w == 0 else (1 - w) * ref + w * boxblur(ref, 3)
        t, n = texture_and_noise(Q, tex_box, flat_box)
        out.append((w, t, n, abs(t - target_tex) < 0.35))
    return out
