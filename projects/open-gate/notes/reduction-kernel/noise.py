import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
import numpy as np
def tile_stats(P,tile=24,minfrac=0.0):
    """P: single colour plane. returns (means, vars) per tile using 2nd-difference estimator
    along x and y, which rejects linear gradients."""
    h=(P.shape[0]//tile)*tile; w=(P.shape[1]//tile)*tile
    Q=P[:h,:w]
    # second difference along x: (a -2b + c)/sqrt(6)
    dx=np.zeros_like(Q); dx[:,1:-1]=(Q[:,:-2]-2*Q[:,1:-1]+Q[:,2:])/np.sqrt(6)
    dy=np.zeros_like(Q); dy[1:-1,:]=(Q[:-2,:]-2*Q[1:-1,:]+Q[2:,:])/np.sqrt(6)
    dx[:,0]=dx[:,1]; dx[:,-1]=dx[:,-2]; dy[0,:]=dy[1,:]; dy[-1,:]=dy[-2,:]
    def blk(A,t):
        hh=(A.shape[0]//t)*t; ww=(A.shape[1]//t)*t
        return A[:hh,:ww].reshape(hh//t,t,ww//t,t)
    m=blk(Q,tile).mean(axis=(1,3))
    vx=(blk(dx,tile)**2).mean(axis=(1,3))
    vy=(blk(dy,tile)**2).mean(axis=(1,3))
    # robustness: use the min of x/y estimates (rejects tiles with texture in one direction)
    v=np.minimum(vx,vy)
    # flatness: also require local range small -> use std of tile vs v
    s=blk(Q,tile).std(axis=(1,3))
    return m.ravel(), v.ravel(), s.ravel()
def slope(m,v,s,lo=20,hi=1500):
    ok=(m>lo)&(m<hi)&(s<np.sqrt(v)*3.0)
    if ok.sum()<30: ok=(m>lo)&(m<hi)&(s<np.sqrt(v)*6.0)
    M,V=m[ok],v[ok]
    A=np.stack([M,np.ones_like(M)],1)
    sol,*_=np.linalg.lstsq(A,V,rcond=None)
    return sol[0],sol[1],ok.sum()
