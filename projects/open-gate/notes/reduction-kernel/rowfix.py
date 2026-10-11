import numpy as np
def cr_shift_rows(P,d):
    """Catmull-Rom fractional shift of plane P along rows by +d (samples). Output[s]=P[s-d]... 
    we want new[s] = value at position s+d  ->  sample P at s+d."""
    n=P.shape[0]; s=np.arange(n)+d
    i0=np.floor(s).astype(int); f=(s-i0)[:,None]
    w=np.concatenate([-0.5*f**3+f**2-0.5*f, 1.5*f**3-2.5*f**2+1.0,
                      -1.5*f**3+2*f**2+0.5*f, 0.5*f**3-0.5*f**2],axis=1)
    out=np.zeros_like(P,dtype=np.float64)
    for k in range(4):
        idx=np.clip(i0-1+k,0,n-1)
        out+=w[:,k:k+1]*P[idx]
    return out
def fix_pairing(raw,mode='split'):
    """raw: HxW CFA (RGGB-ish, row0=R/G1, row1=G2/B). Odd output rows sit 0.5 output px
    above a uniform grid -> correct it. Plane step = 2 output rows, so 0.5 output px = 0.25 plane."""
    R=raw.astype(np.float64)
    E=R[0::2].copy(); O=R[1::2].copy()
    if mode=='split':
        E2=cr_shift_rows(E,-0.125); O2=cr_shift_rows(O,+0.125)
    elif mode=='odd':
        E2=E; O2=cr_shift_rows(O,+0.25)
    else:
        return raw
    out=R.copy(); out[0::2]=E2; out[1::2]=O2
    return np.clip(np.round(out),0,65535).astype(raw.dtype)
