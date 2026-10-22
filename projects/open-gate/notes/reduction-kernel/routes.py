import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import numpy as np
R=25.0/16.0; TAPS=np.arange(-5,6)
def rwzm_proto():
    Wv=np.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'rwzm_Wv2.npy'))
    Cy,_=np.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'rwzm_C2.npy'))
    ds=[];ws=[]
    for p in range(16):
        m=R*p+Cy; f=m-np.floor(m); w=Wv[p]/Wv[p].sum()
        for j,wj in zip(TAPS,w): ds.append(j-f); ws.append(wj)
    ds=np.array(ds); ws=np.array(ws)
    delta=np.sum(ws*ds)/16.0; d=ds-delta
    o=np.argsort(d)
    return d[o],ws[o]
_PD,_PW=None,None
def K_rwzm(x,scale=1.0):
    global _PD,_PW
    if _PD is None: _PD,_PW=rwzm_proto()
    xx=np.asarray(x,float)/scale
    out=np.interp(xx,_PD,_PW,left=0.0,right=0.0)/scale
    return out
def K_tri(x,w=1.0):
    x=np.abs(np.asarray(x,float)); return np.maximum(0.0,1-x/w)/w
def K_lanczos(x,a=3,w=1.0):
    x=np.asarray(x,float)/w
    out=np.where(np.abs(x)<a, np.sinc(x)*np.sinc(x/a), 0.0)
    return out/w
def resample_axis(I,ratio,K,axis,phase=0.0,half=4.0):
    n=int((I.shape[axis]-2*half)/ratio)
    pos=ratio*np.arange(n)+half+phase
    lo=np.floor(pos-half).astype(int); m=int(2*half)+1
    idx=lo[:,None]+np.arange(m)[None,:]
    w=K(idx-pos[:,None]); w/=w.sum(1,keepdims=True)
    idx=np.clip(idx,0,I.shape[axis]-1)
    if axis==0:
        return np.einsum('nk,nkw->nw',w,I[idx])
    else:
        return np.einsum('nk,hnk->hn',w,I[:,idx])
def taps_axis(I,ratio,taps,wts,axis,off=0):
    n=int((I.shape[axis]-8)/ratio)
    base=(ratio*np.arange(n)).astype(int)+4+off
    out=None
    for t,wv in zip(taps,wts):
        idx=np.clip(base+t,0,I.shape[axis]-1)
        s=I[idx] if axis==0 else I[:,idx]
        out=wv*s if out is None else out+wv*s
    return out
