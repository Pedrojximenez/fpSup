import numpy as np
def upsampled_shift(A,B,usf=100,maxshift=2.0):
    """returns (dy,dx): shift of B relative to A, in samples, sub-pixel."""
    A=A-A.mean(); B=B-B.mean()
    h,w=A.shape
    wy=np.hanning(h)[:,None]; wx=np.hanning(w)[None,:]
    FA=np.fft.fft2(A*wy*wx); FB=np.fft.fft2(B*wy*wx)
    R=FA*np.conj(FB)
    fy=np.fft.fftfreq(h)[:,None]; fx=np.fft.fftfreq(w)[None,:]
    n=int(maxshift*usf)
    ys=np.arange(-n,n+1)/usf; xs=np.arange(-n,n+1)/usf
    Ey=np.exp(2j*np.pi*ys[:,None]*fy.ravel()[None,:])   # (ny, h)
    Ex=np.exp(2j*np.pi*xs[:,None]*fx.ravel()[None,:])   # (nx, w)
    C=np.real(Ey@R@Ex.T.conj().T.conj().T) if False else None
    # do it explicitly: c(ys,xs) = sum_{u,v} R[u,v] exp(2pi i (fy[u]*ys + fx[v]*xs))
    M=Ey@R            # (ny, w)
    C=np.real(M@Ex.T) # (ny, nx)
    i=np.unravel_index(np.argmax(C),C.shape)
    return ys[i[0]], xs[i[1]], C[i]/np.abs(C).max()
