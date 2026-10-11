import numpy as np
def phase_slope_shift(A,B,fmax=0.15):
    """Unbiased sub-pixel shift of B relative to A from low-frequency phase slope."""
    A=A-A.mean(); B=B-B.mean(); h,w=A.shape
    wy=np.hanning(h)[:,None]; wx=np.hanning(w)[None,:]
    FA=np.fft.fft2(A*wy*wx); FB=np.fft.fft2(B*wy*wx)
    R=FA*np.conj(FB)
    fy=np.fft.fftfreq(h)[:,None]*np.ones((1,w))
    fx=np.ones((h,1))*np.fft.fftfreq(w)[None,:]
    m=(np.abs(fy)<fmax)&(np.abs(fx)<fmax)&~((fy==0)&(fx==0))
    ph=np.angle(R[m]); wgt=np.abs(R[m])
    X=np.stack([fy[m],fx[m]],1)
    # iterative reweighted LS with unwrapping via residual
    beta=np.zeros(2)
    for _ in range(12):
        pred=X@beta
        d=np.angle(np.exp(1j*(ph-pred)))
        W=wgt
        sol,*_=np.linalg.lstsq(X*W[:,None],(d)*W,rcond=None)
        beta=beta+sol
    # R = FA conj(FB); if B(x)=A(x-s) then FB=FA e^{-i2pi f s} -> R=|FA|^2 e^{+i2pi f s}
    return beta[0]/(2*np.pi), beta[1]/(2*np.pi)

def phase_slope_shift_q(A,B,fmax=0.2):
    A=A-A.mean(); B=B-B.mean(); h,w=A.shape
    wy=np.hanning(h)[:,None]; wx=np.hanning(w)[None,:]
    FA=np.fft.fft2(A*wy*wx); FB=np.fft.fft2(B*wy*wx)
    R=FA*np.conj(FB)
    fy=np.fft.fftfreq(h)[:,None]*np.ones((1,w)); fx=np.ones((h,1))*np.fft.fftfreq(w)[None,:]
    m=(np.abs(fy)<fmax)&(np.abs(fx)<fmax)&~((fy==0)&(fx==0))
    ph=np.angle(R[m]); wgt=np.abs(R[m]); X=np.stack([fy[m],fx[m]],1)
    beta=np.zeros(2)
    for _ in range(15):
        d=np.angle(np.exp(1j*(ph-X@beta)))
        sol,*_=np.linalg.lstsq(X*wgt[:,None],d*wgt,rcond=None); beta=beta+sol
    d=np.angle(np.exp(1j*(ph-X@beta)))
    # coherence: weighted cos of residual phase
    q=float((wgt*np.cos(d)).sum()/wgt.sum())
    return beta[0]/(2*np.pi), beta[1]/(2*np.pi), q, float(wgt.sum())
