import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
import numpy as np
def build(six,N,Hout,Wout,ypos,xpos,vmode,hmode,oy=0.0,ox=0.0):
    """Build a synthetic Bayer output of size (2*Hout,2*Wout) plane-wise.
    ypos(v)/xpos(u): function giving the sensor-row/col CENTRE for output row v / col u.
    vmode/hmode: 'bin' (average the N same-colour samples nearest, spaced 2) or 'lin' (2-tap linear interp)
    Returns dict of planes."""
    out={}
    for (py,px) in [(0,0),(0,1),(1,0),(1,1)]:
        I=plane(six,py,px)   # sensor row 2m+py, col 2n+px
        H,W=Hout,Wout
        s=np.arange(H); t=np.arange(W)
        yc=ypos(2*s+py)      # sensor row centre of output row (2s+py)
        xc=xpos(2*t+px)
        A=np.zeros((H,W))
        # vertical then horizontal, separable
        def taps(c,phase_off,mode):
            # c: sensor coords of centres; sources at 2*k+phase_off
            m=(c-phase_off)/2.0   # in source-lattice units
            if mode=='bin':
                k0=np.round(m).astype(int)
                return [(k0+d-(N-1)//2,np.full_like(m,1.0/N)) for d in range(N)] if N%2 else \
                       [(k0+d-N//2,np.full_like(m,1.0/N)) for d in range(N)]
            else:
                f=np.floor(m).astype(int); fr=m-f
                return [(f,1-fr),(f+1,fr)]
        vt=taps(yc,py,vmode); ht=taps(xc,px,hmode)
        for (ky,wy) in vt:
            for (kx,wx) in ht:
                ky2=np.clip(ky,0,I.shape[0]-1); kx2=np.clip(kx,0,I.shape[1]-1)
                A+=wy[:,None]*wx[None,:]*I[np.ix_(ky2,kx2)]
        out[(py,px)]=A
    return out
