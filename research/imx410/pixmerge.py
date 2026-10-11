#!/usr/bin/env python3
"""感光元件像素合併量測 —— 從同場景的 RAW 反推「一個輸出像素由幾個感光點合成」

    ./pixmerge.py <full-res .DNG> <mode .DNG> [...]

第一個檔當基準(全解析度、1 感光點 = 1 像素)。對每個檔在最平坦的亮區量
sigma^2/mu(散粒雜訊的每電子增益),N_eff = 基準值 / 該模式值。

前提:各檔同 ISO(⇒ 同類比增益)。曝光時間可以不同 —— sigma^2/mu 與曝光無關。
另外印出雜訊頻譜:白雜訊 = 各頻帶都 1.0;低於 1 表示相鄰輸出像素共用輸入樣本
(合併視窗重疊,或之後經過多抽頭縮放)。
"""
import sys, numpy as np, rawpy

def plane(path, cy=0, cx=1):
    r = rawpy.imread(path)
    a = r.raw_image_visible.astype(np.float64)
    bl = float(np.mean(r.black_level_per_channel))
    scale = (r.white_level + 1) / 4096.0          # 正規化到 12-bit 當量
    return (a[cy::2, cx::2] - bl) / scale, r

def detrend(blk, order=3):
    h, w = blk.shape
    y, x = np.mgrid[0:h, 0:w]; y = y/h - 0.5; x = x/w - 0.5
    A = np.array([(x**i * y**j).ravel() for i in range(order+1)
                                        for j in range(order+1-i)]).T
    c, *_ = np.linalg.lstsq(A, blk.ravel(), rcond=None)
    return (blk.ravel() - A @ c).reshape(h, w), A.shape[1]

def flattest(c, size, nkeep=8):
    """找 sigma^2/mu 最小的亮區 —— 真正的平場,不靠人工挑"""
    out = []
    H, W = c.shape
    for y in range(0, int(H*0.45) - size, size//2):
        for x in range(0, W - size, size//2):
            b = c[y:y+size, x:x+size]
            mu = b.mean()
            if mu < 300 or b.max() > 3600: continue
            r, k = detrend(b)
            v = r.var(ddof=k)
            out.append((v/mu, mu, v, y, x))
    out.sort()
    return out[:nkeep]

def noise_bands(r, nb=8):
    r = r - r.mean(); var = r.var()
    w = np.outer(np.hanning(r.shape[0]), np.hanning(r.shape[1]))
    P = np.fft.fftshift(np.abs(np.fft.fft2(r*w))**2 / (r.size * (w**2).mean()))
    n = r.shape[0]; c = n//2
    yy, xx = np.mgrid[0:n, 0:n]
    fr = np.sqrt((yy-c)**2 + (xx-c)**2) / n
    ed = np.linspace(0.02, 0.5, nb+1)
    return np.array([P[(fr>=ed[i]) & (fr<ed[i+1])].mean()/var for i in range(nb)]), \
           0.5*(ed[:-1] + ed[1:])

if __name__ == "__main__":
    ref = None
    print(f"{'file':<34}{'geom':>12}{'sigma2/mu':>11}{'N_eff':>8}")
    rows = []
    for p in sys.argv[1:]:
        c, r = plane(p)
        size = max(16, int(round(c.shape[1]/40)) & ~1)   # 區塊要涵蓋相近的"場景面積"
        b = flattest(c, size)
        k = float(np.median([t[0] for t in b]))
        if ref is None: ref = k
        name = p.split("/")[-1]
        print(f"{name:<34}{f'{r.sizes.raw_width}x{r.sizes.raw_height}':>12}{k:11.5f}{ref/k:8.2f}")
        acc = None
        for _, mu, v, y, x in b:
            rr, _ = detrend(c[y:y+size, x:x+size])
            bb, f = noise_bands(rr)
            acc = bb if acc is None else acc + bb
        rows.append((name, acc/len(b), f))
    print(f"\n雜訊頻譜(PSD/變異數;白雜訊 = 各頻帶 1.0)")
    print(f"{'file':<34}" + "".join(f"{v:7.2f}" for v in rows[0][2]))
    for name, a, _ in rows:
        print(f"{name:<34}" + "".join(f"{v:7.3f}" for v in a))
