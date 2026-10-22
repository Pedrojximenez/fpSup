import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *; from warpfit import cubic_sample, r2_of
import numpy as np
OFF=[-4,-2,0,2,4]
def design(I,py,px,Sv,Tv,p):
    ay,by,ax,bx=p
    Y=ay*Sv/2*0+ay*Sv+by if False else ay*Sv+by
    X=ax*Tv+bx
    cols=[]
    for dy in OFF:
        for dx in OFF:
            cols.append(cubic_sample(I,(Y+dy-py)/2.0,(X+dx-px)/2.0).ravel())
    cols.append(np.ones_like(cols[0]))
    return np.stack(cols,1)
def solve(I,py,px,Sv,Tv,p,Osub):
    Xd=design(I,py,px,Sv,Tv,p); y=Osub.ravel()
    sol,*_=np.linalg.lstsq(Xd,y,rcond=None)
    r=y-Xd@sol
    W=sol[:-1].reshape(len(OFF),len(OFF))
    return W,sol[-1],1-r.var()/y.var()
def predW(I,py,px,Sv,Tv,p,W,b):
    ay,by,ax,bx=p; Y=ay*Sv+by; X=ax*Tv+bx
    acc=np.zeros((len(Sv),len(Tv)))
    for i,dy in enumerate(OFF):
        for j,dx in enumerate(OFF):
            acc+=W[i,j]*cubic_sample(I,(Y+dy-py)/2.0,(X+dx-px)/2.0)
    return acc+b
