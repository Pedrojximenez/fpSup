import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import numpy as np
def samp(I,posy,posx,K,half):
    """Sample I at the given fractional positions with kernel K (separable)."""
    def ax(A,pos,axis):
        lo=np.floor(pos-half).astype(int)+1; m=int(2*half)
        idx=lo[:,None]+np.arange(m)[None,:]
        w=K(idx-pos[:,None]); w/=w.sum(1,keepdims=True)
        idx=np.clip(idx,0,A.shape[axis]-1)
        return np.einsum('nk,nkw->nw',w,A[idx]) if axis==0 else np.einsum('nk,hnk->hn',w,A[:,idx])
    return ax(ax(I,posy,0),posx,1)
def taps_at(I,pos,taps,wts,axis):
    """Discrete taps at integer positions pos+tap (pos must be integral)."""
    p=np.round(pos).astype(int); out=None
    for t,wv in zip(taps,wts):
        idx=np.clip(p+t,0,I.shape[axis]-1)
        s=I[idx] if axis==0 else I[:,idx]
        out=wv*s if out is None else out+wv*s
    return out
def lanczos(x,a,w):
    x=np.asarray(x,float)/w
    return np.where(np.abs(x)<a, np.sinc(x)*np.sinc(x/a), 0.0)/w
