import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import numpy as np
def lanczos2(x):
    x=np.abs(x); out=np.zeros_like(x)
    m=x<1e-8; out[m]=1.0
    n=(~m)&(x<2)
    xx=x[n]*np.pi
    out[n]=2*np.sin(xx)*np.sin(xx/2)/(xx*xx/2)/2
    return out
def down2(img):
    """downscale by 2 with lanczos2, centres at 2i+0.5"""
    H,W=img.shape[:2]
    def axis(a,ax):
        n=a.shape[ax]//2
        c=2*np.arange(n)+0.5
        lo=np.floor(c-2).astype(int)+1
        idx=lo[:,None]+np.arange(4)[None,:]
        w=lanczos2((idx-c[:,None])/2.0); w/=w.sum(1,keepdims=True)
        idx=np.clip(idx,0,a.shape[ax]-1)
        if ax==0: return np.einsum('nk,nkjc->njc',w,a[idx])
        else:     return np.einsum('nk,ink c->inc',w,a[:,idx].transpose(0,2,3,1)[...,None][...,0])
    a=axis(img,0)
    b=axis(a.transpose(1,0,2),0).transpose(1,0,2)
    return b
def pcorr_int(A,B,rng=12):
    """best integer shift dy,dx so that A[y,x] ~ B[y-dy,x-dx]; brute force on luma"""
    best=None
    a=A-A.mean(); 
    for dy in range(-rng,rng+1):
        for dx in range(-rng,rng+1):
            bb=B[200+dy:500+dy,300+dx:700+dx]
            aa=A[200:500,300:700]
            if bb.shape!=aa.shape: continue
            c=np.corrcoef(aa.ravel(),bb.ravel())[0,1]
            if best is None or c>best[0]: best=(c,dy,dx)
    return best
def metrics(R,T):
    """R ref RGB, T test RGB, same shape. Gain-normalise per channel, return luma & chroma rms"""
    out={}
    Tn=np.empty_like(T)
    for c in range(3):
        g=np.sum(R[...,c]*T[...,c])/np.sum(T[...,c]**2)
        Tn[...,c]=T[...,c]*g
    Yr=R.mean(2); Yt=Tn.mean(2)
    out['luma_rms_pct']=100*np.sqrt(np.mean((Yt-Yr)**2))/Yr.mean()
    Cr=np.stack([R[...,0]-R[...,1],R[...,2]-R[...,1]],-1)
    Ct=np.stack([Tn[...,0]-Tn[...,1],Tn[...,2]-Tn[...,1]],-1)
    out['chroma_rms_pct']=100*np.sqrt(np.mean((Ct-Cr)**2))/Yr.mean()
    return out
