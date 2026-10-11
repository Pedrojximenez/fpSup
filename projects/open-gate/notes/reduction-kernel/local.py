import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *; from kernel import fit
import numpy as np
def local_kernel(I,O,N,seed,box,taps,rng=3):
    best=None
    for oy in range(seed[0]-rng,seed[0]+rng+1):
        for ox in range(seed[1]-rng,seed[1]+rng+1):
            r=fit(I,O,N,oy,ox,list(range(N)),list(range(N)),box=box)
            if r and (best is None or r['rms']<best[0]['rms']): best=(r,oy,ox)
    r,oy,ox=best
    rw=fit(I,O,N,oy,ox,taps,taps,box=box)
    return rw,oy,ox
