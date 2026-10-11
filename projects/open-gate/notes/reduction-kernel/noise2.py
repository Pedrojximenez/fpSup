import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
import numpy as np
def diag_hp(P):
    """2x2 diagonal high-pass: kills any bilinear scene component. Var(d)=sigma^2"""
    return (P[:-1,:-1]-P[:-1,1:]-P[1:,:-1]+P[1:,1:])/2.0
def curve(P,tile=16,nbin=12,pct=8.0,lo=10,hi=2000):
    d=diag_hp(P)
    h=(d.shape[0]//tile)*tile; w=(d.shape[1]//tile)*tile
    D=d[:h,:w].reshape(h//tile,tile,w//tile,tile)
    M=P[:h,:w].reshape(h//tile,tile,w//tile,tile).mean(axis=(1,3)).ravel()
    V=(D**2).mean(axis=(1,3)).ravel()
    ok=(M>lo)&(M<hi)
    M,V=M[ok],V[ok]
    edges=np.exp(np.linspace(np.log(max(M.min(),lo)),np.log(M.max()),nbin+1))
    xs=[];ys=[];ns=[]
    for i in range(nbin):
        s=(M>=edges[i])&(M<edges[i+1])
        if s.sum()<25: continue
        xs.append(np.median(M[s])); ys.append(np.percentile(V[s],pct)); ns.append(int(s.sum()))
    return np.array(xs),np.array(ys),ns
def fitline(x,y):
    A=np.stack([x,np.ones_like(x)],1)
    sol,*_=np.linalg.lstsq(A,y,rcond=None)
    return sol
