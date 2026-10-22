import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
import numpy as np
def cubic_sample(I,yy,xx):
    """Catmull-Rom sample of plane I at fractional lattice coords yy,xx (arrays broadcastable)."""
    y0=np.floor(yy).astype(int); x0=np.floor(xx).astype(int)
    fy=yy-y0; fx=xx-x0
    def wts(f):
        f=f[...,None]
        return np.concatenate([-0.5*f**3+f**2-0.5*f, 1.5*f**3-2.5*f**2+1.0,
                               -1.5*f**3+2*f**2+0.5*f, 0.5*f**3-0.5*f**2],axis=-1)
    wy=wts(fy); wx=wts(fx)
    H,W=I.shape; out=0.0
    for a in range(4):
        ya=np.clip(y0-1+a,0,H-1)
        row=0.0
        for b in range(4):
            xb=np.clip(x0-1+b,0,W-1)
            row=row+wx[...,b]*I[ya[:,None],xb[None,:]] if False else row
        # do properly below
    acc=np.zeros((len(yy),len(xx)))
    for a in range(4):
        ya=np.clip(y0-1+a,0,H-1)
        for b in range(4):
            xb=np.clip(x0-1+b,0,W-1)
            acc+=wy[:,a][:,None]*wx[:,b][None,:]*I[np.ix_(ya,xb)]
    return acc
def predict(I,py,px,S,T,ay,by,ax,bx,vt,ht):
    """vt/ht: list of (sensor_offset, weight). Output positions in SENSOR coords."""
    Y=ay*S+by; X=ax*T+bx
    acc=np.zeros((len(S),len(T)))
    for dy,wy in vt:
        for dx,wx in ht:
            yy=(Y+dy-py)/2.0; xx=(X+dx-px)/2.0
            acc+=wy*wx*cubic_sample(I,yy,xx)
    return acc
def r2_of(O,P):
    y=O.ravel(); x=P.ravel()
    A=np.stack([x,np.ones_like(x)],1); sol,*_=np.linalg.lstsq(A,y,rcond=None)
    r=y-A@sol; return 1-r.var()/y.var()
