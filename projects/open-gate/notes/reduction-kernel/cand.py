import sys; sys.path.insert(0,'bin')
from common import *; from routes2 import taps_at, samp, lanczos
from coh import decompose
import numpy as np
TAPS=np.arange(-5,6); M=16; th=1/3.
def load_true(nm):
    W=np.load(nm); W=W/W.sum(1,keepdims=True)
    return np.array([W[(9*q)%16] for q in range(16)])
Wv=load_true('fhd_Wv.npy'); Wh=load_true('fhd_Wh.npy')
def rwzm(A,R,C,n,ax,W):
    """general polyphase: true phase from frac(m)"""
    m=R*np.arange(n)+C; b=np.floor(m).astype(int)
    ph=np.floor(16*(m-b)).astype(int)%16
    o=None
    for ti,j in enumerate(TAPS):
        idx=np.clip(b+j,0,A.shape[ax]-1); src=A[idx] if ax==0 else A[:,idx]
        w=W[ph,ti]; c=(w[:,None]*src) if ax==0 else (w[None,:]*src)
        o=c if o is None else o+c
    return o,m
def bin2(sub,ph):
    H,W=sub.shape
    py=np.arange(M+ph,H-M-2,2.0); px=np.arange(M+ph,W-M-2,2.0)
    a=taps_at(sub,py,[0,1],[.5,.5],0); return taps_at(a,px,[0,1],[.267,.733],1),py+0.5,px+0.733
def bin3(sub,ph):
    H,W=sub.shape
    py=np.arange(M+ph,H-M-4,3.0); px=np.arange(M+ph,W-M-4,3.0)
    a=taps_at(sub,py,[0,1],[.5,.5],0); return taps_at(a,px,[-1,0,1],[.25,.5,.25],1),py,px
def idbox(k):
    def f(sub,ph):
        H,W=sub.shape; w=[1./k]*k; t=list(range(k))
        py=np.arange(M+ph,H-M-k-1,float(k)); px=np.arange(M+ph,W-M-k-1,float(k))
        a=taps_at(sub,py,t,w,0); return taps_at(a,px,t,w,1),py+(k-1)/2.,px+(k-1)/2.
    return f
def direct(R):                       # full 6K read -> RWZM R, no sensor reduction
    def f(sub,ph):
        n=int((sub.shape[0]-2*M)/R)-4; m2=int((sub.shape[1]-2*M)/R)-4
        Y,my=rwzm(sub,R,float(M+ph),n,0,Wv); Y,mx=rwzm(Y,R,float(M+ph),m2,1,Wh); return Y,my,mx
    return f
def after2(R):                       # sensor /2 then RWZM R
    def f(sub,ph):
        S,cy,cx=bin2(sub,ph)
        n=int((S.shape[0]-6)/R)-3; m2=int((S.shape[1]-6)/R)-3
        Y,my=rwzm(S,R,3.0,n,0,Wv); Y,mx=rwzm(Y,R,3.0,m2,1,Wh)
        return Y,np.interp(my,np.arange(len(cy)),cy),np.interp(mx,np.arange(len(cx)),cx)
    return f
B=((0.05,0.15),(0.15,0.25),(0.25,0.35),(0.35,0.45))
PATCH=[(560,1560,900,2100),(420,760,950,2050),(1500,1990,450,2550)]
six=load('6K'); I=plane(six,0,1)
def audit(lbl,fn,rat,neff):
    al=[];mt=[]
    for (y0,y1,x0,x1) in PATCH:
        sub=I[y0:y1,x0:x1]; v=[]
        for ph in range(3):
            X,cy,cx=fn(sub,ph)
            Rf=samp(sub,cy,cx,lambda x:lanczos(x,3,rat),3*rat+2)
            m=5; d=decompose(Rf[m:-m,m:-m],X[m:-m,m:-m],n=48,step=32)
            v.append(100*d['incoh']/d['sig'])
        al.append(np.median(v))
        X,cy,cx=fn(sub,0); Rf=samp(sub,cy,cx,lambda x:lanczos(x,3,rat),3*rat+2)
        m=5; d=decompose(Rf[m:-m,m:-m],X[m:-m,m:-m],n=64,step=40)
        H,fr,S=np.abs(d['H']),d['fr'],d['Srr']
        mt.append([float(np.average(H[(fr>=a)&(fr<b)],weights=S[(fr>=a)&(fr<b)])) for a,b in B])
    mt=np.mean(mt,0)
    print(f'{lbl:34s}{al[0]:6.1f}{al[1]:6.1f}{al[2]:6.1f}   '+' '.join(f'{v:.2f}' for v in mt)
          +f'   {neff:6.2f}  x{1/np.sqrt(neff):.2f}')
    return al,mt
def neff_of(fn,rat,k=41):
    """impulse-response N_eff: feed deltas, read back the effective kernel energy"""
    n=180; tot=[]
    for d0 in range(0,6):
        A=np.zeros((n,n)); A[n//2+d0,n//2+d0]=1.0
        X,cy,cx=fn(A,0); s=X.sum()
        if s<=0: continue
        tot.append(s*s/np.sum(X**2)) if False else None
    return None
