import numpy as np, os
S=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BL={'6K':1024.0,'4K':256.0,'4K_set2':256.0,'OG3K':256.0,'OG2K':256.0,'FHD':256.0,'FHD_set2':256.0}
SC={'6K':4.0}  # 14-bit -> 12-bit
def load(n):
    a=np.load(f'{S}/{n}.npy').astype(np.float64)-BL[n]
    return a/SC.get(n,1.0)
def plane(a,py,px): return a[py::2,px::2]
def boxdown(a,N):
    h=(a.shape[0]//N)*N; w=(a.shape[1]//N)*N
    return a[:h,:w].reshape(h//N,N,w//N,N).mean(axis=(1,3))
def pcorr(A,B):
    """integer shift that best aligns B onto A (A,B same-ish size). returns (dy,dx) s.t. A[y,x]~B[y-dy,x-dx]"""
    h=min(A.shape[0],B.shape[0]); w=min(A.shape[1],B.shape[1])
    a=A[:h,:w]-A[:h,:w].mean(); b=B[:h,:w]-B[:h,:w].mean()
    wy=np.hanning(h)[:,None]; wx=np.hanning(w)[None,:]
    FA=np.fft.rfft2(a*wy*wx); FB=np.fft.rfft2(b*wy*wx)
    R=FA*np.conj(FB); R/=np.abs(R)+1e-12
    c=np.fft.irfft2(R,s=(h,w))
    i=np.unravel_index(np.argmax(c),c.shape)
    dy=i[0]-(h if i[0]>h//2 else 0); dx=i[1]-(w if i[1]>w//2 else 0)
    return dy,dx,c[i]
