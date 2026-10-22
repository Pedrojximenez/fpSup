import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *; from noise2 import diag_hp
import numpy as np
def decim(I,N,oy,ox,ky,kx,H,W):
    out=np.zeros((H,W))
    for j,wy in enumerate(ky):
        for k,wx in enumerate(kx):
            out+=wy*wx*I[oy+j:oy+j+N*H:N, ox+k:ox+k+N*W:N]
    return out
def psd_axes(a,noisevar=0.0):
    a=a-a.mean(); h,w=a.shape
    wy=np.hanning(h)[:,None]; wx=np.hanning(w)[None,:]
    aw=a*wy*wx
    # white-noise PSD level through the same window
    wsum=float(((wy*wx)**2).sum())
    Fx=np.abs(np.fft.rfft(aw,axis=1))**2; px=Fx.mean(axis=0)
    Fy=np.abs(np.fft.rfft(aw,axis=0))**2; py=Fy.mean(axis=1)
    if noisevar>0:
        # expected flat level per bin for white noise variance nv
        px=px-noisevar*float((wy**2).mean())*float((wx**2).sum())*1.0
        py=py-noisevar*float((wx**2).mean())*float((wy**2).sum())*1.0
    px=np.clip(px,1e-9,None); py=np.clip(py,1e-9,None)
    return px/px[1:].sum(), py/py[1:].sum()
def bands(p,nb=10):
    n=len(p)-1
    return np.array([p[1+int(i*n/nb):1+int((i+1)*n/nb)].sum() for i in range(nb)])
def estvar(P):
    d=diag_hp(P); 
    t=16; h=(d.shape[0]//t)*t; w=(d.shape[1]//t)*t
    V=(d[:h,:w].reshape(h//t,t,w//t,t)**2).mean(axis=(1,3)).ravel()
    return float(np.percentile(V,10))
