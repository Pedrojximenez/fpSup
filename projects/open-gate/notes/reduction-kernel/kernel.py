import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
import numpy as np, itertools

def fit(I,O,N,oy,ox,taps_y,taps_x,box=None,ret_w=False):
    """O[s,t] ~ sum w_jk I[N s+oy+j, N t+ox+k] + b, over valid s,t (optionally restricted to box)"""
    S0,T0 = 0,0
    S1,T1 = O.shape
    # valid range so all taps inside I
    jmin,jmax=min(taps_y),max(taps_y); kmin,kmax=min(taps_x),max(taps_x)
    S0=max(S0, int(np.ceil((-oy-jmin)/N))); S1=min(S1, (I.shape[0]-1-oy-jmax)//N+1)
    T0=max(T0, int(np.ceil((-ox-kmin)/N))); T1=min(T1, (I.shape[1]-1-ox-kmax)//N+1)
    if box:
        S0=max(S0,box[0]); S1=min(S1,box[1]); T0=max(T0,box[2]); T1=min(T1,box[3])
    if S1-S0<8 or T1-T0<8: return None
    y=O[S0:S1,T0:T1].ravel()
    cols=[]
    for j in taps_y:
        for k in taps_x:
            cols.append(I[N*S0+oy+j : N*(S1-1)+oy+j+1 : N, N*T0+ox+k : N*(T1-1)+ox+k+1 : N].ravel())
    cols.append(np.ones_like(y))
    X=np.stack(cols,1)
    # subsample for speed
    if X.shape[0]>400000:
        idx=np.random.default_rng(0).choice(X.shape[0],400000,replace=False)
        Xs=X[idx]; ys=y[idx]
    else: Xs,ys=X,y
    sol,res,rank,sv=np.linalg.lstsq(Xs,ys,rcond=None)
    pred=Xs@sol
    rms=float(np.sqrt(np.mean((ys-pred)**2)))
    r2=1-np.var(ys-pred)/np.var(ys)
    w=sol[:-1].reshape(len(taps_y),len(taps_x)); b=sol[-1]
    return dict(rms=rms,r2=r2,w=w,b=b,n=len(ys))

def search(I,O,N,rng=6,taps=None):
    taps=taps or list(range(N))
    best=None
    for oy in range(-rng,rng+1):
        for ox in range(-rng,rng+1):
            r=fit(I,O,N,oy,ox,taps,taps)
            if r and (best is None or r['rms']<best[0]['rms']): best=(r,oy,ox)
    return best
