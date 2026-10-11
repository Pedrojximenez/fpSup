import numpy as np
from load import load

def detrend_var(blk, order=3):
    """remove a smooth 2-D polynomial, return (mean, residual variance)"""
    h,w = blk.shape
    y,x = np.mgrid[0:h,0:w]
    y = (y/h-0.5); x = (x/w-0.5)
    cols=[]
    for i in range(order+1):
        for j in range(order+1-i):
            cols.append((x**i * y**j).ravel())
    A=np.array(cols).T
    b=blk.ravel()
    coef,*_ = np.linalg.lstsq(A,b,rcond=None)
    r = b - A@coef
    return blk.mean(), r.var(ddof=A.shape[1])

def best_flat(a, black, scale, cy, cx, size, nkeep=6):
    c = (a[cy::2, cx::2].astype(np.float64) - black)/scale
    H,W = c.shape
    out=[]
    for y in range(0, int(H*0.45)-size, size//2):
        for x in range(0, W-size, size//2):
            blk = c[y:y+size, x:x+size]
            mu = blk.mean()
            if mu < 300 or blk.max() > 3600: continue
            m,v = detrend_var(blk)
            out.append((v/m, m, v, y, x))
    out.sort()
    return out[:nkeep]

cfg = {"fhd":(256.,1.,24), "og2k":(256.,1.,24), "still":(1024.,4.,72)}
CH = {"R":(0,0),"G1":(0,1),"G2":(1,0),"B":(1,1)}
res={}
print(f"{'file':<6}{'ch':>4}{'mu':>9}{'sigma^2':>10}{'sig2/mu':>10}   best flat blocks (sig2/mu)")
for k,(bl,sc,sz) in cfg.items():
    a,_,_=load(k)
    for nm,(cy,cx) in CH.items():
        b = best_flat(a,bl,sc,cy,cx,sz)
        ratios=[t[0] for t in b]
        med = float(np.median(ratios))
        res[(k,nm)]=med
        print(f"{k:<6}{nm:>4}{b[0][1]:9.1f}{b[0][2]:10.3f}{med:10.5f}   "
              + " ".join(f"{r:.4f}" for r in ratios))
print()
for nm in CH:
    print(f"  {nm}:  N_eff(fhd) = {res[('still',nm)]/res[('fhd',nm)]:6.2f}   "
          f"N_eff(og2k) = {res[('still',nm)]/res[('og2k',nm)]:6.2f}")
