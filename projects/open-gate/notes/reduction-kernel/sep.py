import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
import numpy as np
R=25.0/16.0; NPH=16; TAPS=np.arange(-3,5)
def base_frac(C,n):
    m=R*np.arange(n)+C
    return np.floor(m).astype(int), m-np.floor(m)
def apply_axis(I,W,C,nout,axis):
    """W: (NPH,len(TAPS)). resample along `axis` to nout samples."""
    b,_=base_frac(C,nout)
    ph=np.arange(nout)%NPH
    out=None
    for ti,j in enumerate(TAPS):
        idx=np.clip(b+j,0,I.shape[axis]-1)
        src=I[idx] if axis==0 else I[:,idx]
        w=W[ph,ti]
        contrib=(w[:,None]*src) if axis==0 else (w[None,:]*src)
        out=contrib if out is None else out+contrib
    return out
def solve_axis(V,O,C,axis):
    """LS for W given the other axis already applied. V is the partially-resampled image."""
    n=O.shape[axis]
    b,_=base_frac(C,n)
    W=np.zeros((NPH,len(TAPS)))
    for p in range(NPH):
        idx=np.arange(p,n,NPH)
        ok=(b[idx]+TAPS.min()>=0)&(b[idx]+TAPS.max()<V.shape[axis])
        idx=idx[ok]
        if len(idx)<5: continue
        cols=[]
        for j in TAPS:
            src=V[b[idx]+j] if axis==0 else V[:,b[idx]+j]
            cols.append(src.ravel())
        y=(O[idx] if axis==0 else O[:,idx]).ravel()
        X=np.stack(cols,1)
        sol,*_=np.linalg.lstsq(X,y,rcond=None)
        W[p]=sol
    return W
