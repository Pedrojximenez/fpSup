import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *; from freefit import solve, OFF
import numpy as np
def refine(I,py,px,Sv,Tv,Osub,p0,steps=(0.004,0.4,0.004,0.4),maxit=25):
    p=list(p0); _,_,cur=solve(I,py,px,Sv,Tv,p,Osub); st=list(steps)
    for it in range(maxit):
        imp=False
        for i in range(4):
            for s in (st[i],-st[i]):
                q=list(p); q[i]+=s
                _,_,v=solve(I,py,px,Sv,Tv,q,Osub)
                if v>cur+1e-5: p,cur=q,v; imp=True; break
        if not imp:
            st=[x/2 for x in st]
            if st[0]<3e-4: break
    return p,cur
