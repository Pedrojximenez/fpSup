import numpy as np
from load import load

def green(k, bl, sc=1.0):
    a,_,_ = load(k)
    return (a[0::2,1::2].astype(np.float64)-bl)/sc

def zoom(a, s):
    H,W=a.shape; h,w=int(H*s),int(W*s)
    yi=np.linspace(0,H-1,h); xi=np.linspace(0,W-1,w)
    y0=np.floor(yi).astype(int); x0=np.floor(xi).astype(int)
    y1=np.minimum(y0+1,H-1); x1=np.minimum(x0+1,W-1)
    fy=(yi-y0)[:,None]; fx=(xi-x0)[None,:]
    return ((a[np.ix_(y0,x0)]*(1-fy)*(1-fx) + a[np.ix_(y1,x0)]*fy*(1-fx)
            + a[np.ix_(y0,x1)]*(1-fy)*fx + a[np.ix_(y1,x1)]*fy*fx))

def ncc_best(A,B):
    """normalised cross-correlation over shifts via FFT; A,B mean-removed, windowed"""
    n=(min(A.shape[0],B.shape[0]), min(A.shape[1],B.shape[1]))
    A=A[:n[0],:n[1]].copy(); B=B[:n[0],:n[1]].copy()
    A-=A.mean(); B-=B.mean()
    A/=A.std(); B/=B.std()
    w=np.outer(np.hanning(n[0]),np.hanning(n[1]))
    A*=w; B*=w
    c=np.fft.irfft2(np.fft.rfft2(A)*np.conj(np.fft.rfft2(B)), s=n)/(n[0]*n[1])
    i=np.unravel_index(np.argmax(c),c.shape)
    dy=i[0] if i[0]<n[0]//2 else i[0]-n[0]
    dx=i[1] if i[1]<n[1]//2 else i[1]-n[1]
    return c.max(), dy, dx

F=green("fhd",256.); O=green("og2k",256.)
print(f"{'scale':>7}{'ncc':>9}{'dy':>6}{'dx':>6}")
best=None
for s in np.arange(0.94,1.10,0.01):
    v,dy,dx = ncc_best(F, zoom(O,s))
    print(f"{s:7.3f}{v:9.4f}{dy:6d}{dx:6d}")
    if best is None or v>best[0]: best=(v,s,dy,dx)
print("best:", best)
