import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
import numpy as np
R=25.0/16.0; NPH=16
TAPS=list(range(-3,5))
def phase_fit(I,O,Cy,Cx,plist=None,qlist=None,taps=TAPS):
    """s = 16a+p -> m_y = R*s+Cy = 25a + (R*p+Cy). Base row advances by exactly 25 per a."""
    plist=range(NPH) if plist is None else plist
    qlist=range(NPH) if qlist is None else qlist
    res={}; H,W=O.shape
    for p in plist:
        my=R*p+Cy; b0=int(np.floor(my)); fy=my-b0
        for q in qlist:
            mx=R*q+Cx; c0=int(np.floor(mx)); fx=mx-c0
            amin=max(1,int(np.ceil((-b0-min(taps))/25.0))+1); amax=min((H-1-p)//NPH,(I.shape[0]-1-b0-max(taps))//25)-1
            bmin=max(1,int(np.ceil((-c0-min(taps))/25.0))+1); bmax=min((W-1-q)//NPH,(I.shape[1]-1-c0-max(taps))//25)-1
            if amax-amin<8 or bmax-bmin<8: continue
            A=np.arange(amin,amax); B=np.arange(bmin,bmax)
            y=O[np.ix_(p+NPH*A,q+NPH*B)].ravel()
            cols=[I[np.ix_(b0+25*A+j,c0+25*B+k)].ravel() for j in taps for k in taps]
            cols.append(np.ones_like(y)); X=np.stack(cols,1)
            sol,*_=np.linalg.lstsq(X,y,rcond=None); r=y-X@sol
            res[(p,q)]=dict(w=sol[:-1].reshape(len(taps),len(taps)),b=sol[-1],
                            r2=1-r.var()/y.var(),fy=fy,fx=fx,n=len(y))
    return res
